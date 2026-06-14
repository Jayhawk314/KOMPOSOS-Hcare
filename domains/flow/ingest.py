# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Phase 2 loaders: real public healthcare datasets -> flow Sections.

Stdlib only (``csv`` + ``gzip`` + ``zipfile``) so it stays dependency-free and
CPU-light. Each loader streams rows and returns a
:class:`domains.flow.coherence.Section` keyed by the dataset's join key, with
column names resolved across year vintages (CMS renames columns between years).

Object naming convention for the Category builder (one namespace per type):
    npi:<npi>            type_name="provider"
    org:<uei>            type_name="recipient_org"
    specialty:<code>     type_name="specialty"
    state:<abbrev>       type_name="state"
    source:<name>        type_name="data_source"

Datasets and their canonical join key (see sources/registry.py):
    CMS Physician & Other Practitioners (by Provider and Service)  -> npi
    CMS Physician & Other Practitioners (by Provider, aggregate)   -> npi
    Medicare Part D Prescriber (by Provider)                       -> npi
    CMS Open Payments (general payments)                           -> npi
    NPPES NPI registry                                             -> npi
    USASpending HHS obligations                                    -> recipient_uei
"""

from __future__ import annotations

import csv
import gzip
import io
import os
import zipfile
from contextlib import contextmanager
from typing import Dict, Iterator, List, Mapping, Optional

from core.category import Category

from domains.flow.coherence import Section

# csv fields in these files can be large (free-text descriptions).
csv.field_size_limit(10_000_000)


# ---------------------------------------------------------------------------
# Robust file + column handling
# ---------------------------------------------------------------------------
@contextmanager
def _open_text(path: str) -> Iterator[io.TextIOBase]:
    """Open .csv, .csv.gz, or a single-member .zip transparently as text."""
    lower = path.lower()
    if lower.endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as fh:
            yield fh
    elif lower.endswith(".zip"):
        with zipfile.ZipFile(path) as zf:
            members = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not members:
                raise ValueError(f"no .csv inside {path}")
            with zf.open(members[0]) as raw:
                yield io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
    else:
        with open(path, "rt", encoding="utf-8-sig", newline="") as fh:
            yield fh


def _resolve(fieldnames: List[str], aliases: List[str]) -> Optional[str]:
    """Return the actual header matching any alias (case/space-insensitive)."""
    norm = {f.strip().lower(): f for f in fieldnames if f}
    for a in aliases:
        hit = norm.get(a.strip().lower())
        if hit:
            return hit
    return None


def _require(fieldnames: List[str], aliases: List[str], label: str) -> str:
    col = _resolve(fieldnames, aliases)
    if col is None:
        raise KeyError(
            f"could not find {label} column; tried {aliases}; "
            f"available: {fieldnames[:12]}{'...' if len(fieldnames) > 12 else ''}"
        )
    return col


def _to_float(s: object) -> float:
    if s is None:
        return 0.0
    t = str(s).strip().replace(",", "").replace("$", "")
    if not t or t.upper() in {"NA", "N/A", "NULL"}:
        return 0.0
    try:
        return float(t)
    except ValueError:
        return 0.0


# Column aliases by concept (recent CMS vintage first, older PUF names after).
_NPI = ["Rndrng_NPI", "Prscrbr_NPI", "Covered_Recipient_NPI", "Physician_NPI",
        "NPI", "National Provider Identifier", "npi"]
_SPECIALTY = ["Rndrng_Prvdr_Type", "Prscrbr_Type", "provider_type",
              "Healthcare Provider Taxonomy Code_1"]
_STATE = ["Rndrng_Prvdr_State_Abrvtn", "Prscrbr_State_Abrvtn",
          "Provider Business Practice Location Address State Name",
          "Provider Business Mailing Address State Name", "nppes_provider_state"]


# ---------------------------------------------------------------------------
# CMS Medicare Physician & Other Practitioners  -- by Provider and Service
# ---------------------------------------------------------------------------
def load_provider_service(path: str, *, source: str = "cms_service") -> Section:
    """Line-item billing -> Section keyed by NPI (Medicare $ summed).

    Row Medicare payment = Avg_Mdcr_Pymt_Amt x Tot_Srvcs. Summing all rows for
    an NPI is the pushforward of the line-item presheaf to provider level; it
    must equal the 'by Provider' aggregate (see load_provider_summary).
    """
    values: Dict[str, float] = {}
    with _open_text(path) as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        npi_c = _require(fields, _NPI, "NPI")
        avg_c = _require(fields, ["Avg_Mdcr_Pymt_Amt", "average_Medicare_payment_amt"],
                         "avg Medicare payment")
        srv_c = _require(fields, ["Tot_Srvcs", "line_srvc_cnt"], "total services")
        for row in reader:
            npi = str(row.get(npi_c, "")).strip()
            if not npi:
                continue
            pay = _to_float(row.get(avg_c)) * _to_float(row.get(srv_c))
            values[npi] = values.get(npi, 0.0) + pay
    return Section(source=source, values=values, layer="3-provider")


def load_provider_fingerprints(path: str):
    """Line-item billing -> Yoneda fingerprints for outlier detection.

    Returns ``(fingerprints, specialties)`` where
      fingerprints[npi] = {hcpcs_code: medicare_dollars}   (the hom-out set)
      specialties[npi]  = provider type (peer-group key)

    A provider's fingerprint is the co-Yoneda data Hom(provider, -): which
    codes it bills and how much. Two providers are structurally similar when
    these fingerprints overlap; an outlier bills a mix unlike its peers.
    """
    fingerprints: Dict[str, Dict[str, float]] = {}
    specialties: Dict[str, str] = {}
    with _open_text(path) as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        npi_c = _require(fields, _NPI, "NPI")
        hc_c = _require(fields, ["HCPCS_Cd", "hcpcs_code"], "HCPCS code")
        avg_c = _require(fields, ["Avg_Mdcr_Pymt_Amt", "average_Medicare_payment_amt"],
                         "avg Medicare payment")
        srv_c = _require(fields, ["Tot_Srvcs", "line_srvc_cnt"], "total services")
        sp_c = _resolve(fields, _SPECIALTY)
        for row in reader:
            npi = str(row.get(npi_c, "")).strip()
            code = str(row.get(hc_c, "")).strip()
            if not npi or not code:
                continue
            pay = _to_float(row.get(avg_c)) * _to_float(row.get(srv_c))
            fp = fingerprints.setdefault(npi, {})
            fp[code] = fp.get(code, 0.0) + pay
            if sp_c and npi not in specialties:
                specialties[npi] = str(row.get(sp_c, "")).strip() or "unknown"
    return fingerprints, specialties


# ---------------------------------------------------------------------------
# CMS Medicare Physician & Other Practitioners  -- by Provider (aggregate)
# ---------------------------------------------------------------------------
def load_provider_summary(path: str, *, source: str = "cms_summary") -> Section:
    """Provider-aggregate billing -> Section keyed by NPI (total Medicare $)."""
    values: Dict[str, float] = {}
    with _open_text(path) as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        npi_c = _require(fields, _NPI, "NPI")
        tot_c = _require(fields, ["Tot_Mdcr_Pymt_Amt", "total_Medicare_payment_amt"],
                         "total Medicare payment")
        for row in reader:
            npi = str(row.get(npi_c, "")).strip()
            if not npi:
                continue
            values[npi] = values.get(npi, 0.0) + _to_float(row.get(tot_c))
    return Section(source=source, values=values, layer="3-provider")


# ---------------------------------------------------------------------------
# Medicare Part D Prescriber  -- by Provider
# ---------------------------------------------------------------------------
def load_part_d(path: str, *, source: str = "part_d") -> Section:
    """Part D prescribing -> Section keyed by NPI (total drug cost)."""
    values: Dict[str, float] = {}
    with _open_text(path) as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        npi_c = _require(fields, _NPI, "NPI")
        cost_c = _require(fields, ["Tot_Drug_Cst", "total_drug_cost"], "total drug cost")
        for row in reader:
            npi = str(row.get(npi_c, "")).strip()
            if not npi:
                continue
            values[npi] = values.get(npi, 0.0) + _to_float(row.get(cost_c))
    return Section(source=source, values=values, layer="3-provider")


# ---------------------------------------------------------------------------
# CMS Open Payments  -- general payments (pharma -> provider)
# ---------------------------------------------------------------------------
def load_open_payments(path: str, *, source: str = "open_payments") -> Section:
    """Pharma payments -> Section keyed by NPI (total $ received)."""
    values: Dict[str, float] = {}
    with _open_text(path) as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        npi_c = _require(fields, _NPI, "NPI")
        amt_c = _require(fields, ["Total_Amount_of_Payment_USDollars",
                                  "total_amount_of_payment_usdollars"], "payment amount")
        for row in reader:
            npi = str(row.get(npi_c, "")).strip()
            if not npi:
                continue
            values[npi] = values.get(npi, 0.0) + _to_float(row.get(amt_c))
    return Section(source=source, values=values, layer="4-pharma")


# ---------------------------------------------------------------------------
# USASpending HHS obligations  -- keyed by recipient org (UEI)
# ---------------------------------------------------------------------------
def load_usaspending(path: str, *, source: str = "usaspending_hhs") -> Section:
    """Federal obligations -> Section keyed by recipient_uei.

    NOTE: USASpending is org-level (UEI), not NPI. The join to provider NPI is
    approximate (org -> facility -> NPIs) and is handled in Phase 2b; this
    loader keeps the honest org-level key.
    """
    values: Dict[str, float] = {}
    with _open_text(path) as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        uei_c = _require(fields, ["recipient_uei", "recipient_duns", "awardee_uei"],
                         "recipient UEI")
        obl_c = _require(fields, ["federal_action_obligation", "total_obligated_amount",
                                  "obligated_amount"], "obligation amount")
        for row in reader:
            uei = str(row.get(uei_c, "")).strip()
            if not uei:
                continue
            values[uei] = values.get(uei, 0.0) + _to_float(row.get(obl_c))
    return Section(source=source, values=values, layer="0-federal")


# ---------------------------------------------------------------------------
# Medicare Advantage  -- enrollment + assembled contract inputs
# ---------------------------------------------------------------------------
_CONTRACT = ["Contract Number", "Contract ID", "contract_id", "Contract_Number",
             "CONTRACT_ID", "contractid"]


def load_ma_enrollment(path: str) -> Dict[str, int]:
    """CMS MA monthly enrollment -> {contract_id: total enrollment}.

    Source: CMS 'Medicare Advantage/Part D Contract and Enrollment Data'
    (CPSC enrollment files). Enrollment is summed across plans/counties in the
    contract. Values of '*' (suppressed small cells) are treated as 0.
    """
    out: Dict[str, int] = {}
    with _open_text(path) as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        c_col = _require(fields, _CONTRACT, "contract id")
        e_col = _require(fields, ["Enrollment", "enrollment", "Enrolled"], "enrollment")
        for row in reader:
            cid = str(row.get(c_col, "")).strip()
            if not cid:
                continue
            out[cid] = out.get(cid, 0) + int(_to_float(row.get(e_col)))
    return out


def load_ma_contracts(path: str):
    """Assembled per-contract inputs -> list[MAContract].

    Expects a CSV with the columns needed for the paid/consumed 2-cell. This is
    the assembly point for public pieces that live in different CMS files:
    enrollment (CPSC), benchmark per-capita (MA rate book / county rates),
    county FFS per-capita (Geographic Variation PUF), and risk score. Columns
    (aliases accepted):
        contract_id, enrollment, benchmark_per_capita, ffs_per_capita,
        risk_score [, ffs_risk, name]
    """
    from domains.flow.medicare_advantage import MAContract

    out = []
    with _open_text(path) as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        c_col = _require(fields, _CONTRACT, "contract id")
        enr_col = _require(fields, ["enrollment", "Enrollment"], "enrollment")
        bm_col = _require(fields, ["benchmark_per_capita", "benchmark_pc",
                                   "benchmark"], "benchmark per-capita")
        ffs_col = _require(fields, ["ffs_per_capita", "ffs_pc", "ffs"],
                           "FFS per-capita")
        rs_col = _require(fields, ["risk_score", "risk", "raf"], "risk score")
        fr_col = _resolve(fields, ["ffs_risk", "demographic_risk"])
        nm_col = _resolve(fields, ["name", "plan_name", "organization_name"])
        for row in reader:
            cid = str(row.get(c_col, "")).strip()
            if not cid:
                continue
            out.append(MAContract(
                contract_id=cid,
                enrollment=int(_to_float(row.get(enr_col))),
                benchmark_per_capita=_to_float(row.get(bm_col)),
                ffs_per_capita=_to_float(row.get(ffs_col)),
                risk_score=_to_float(row.get(rs_col)) or 1.0,
                ffs_risk=_to_float(row.get(fr_col)) if fr_col else 1.0,
                name=str(row.get(nm_col, "")).strip() if nm_col else "",
            ))
    return out


# ---------------------------------------------------------------------------
# NPPES registry  -- the provider -> peer-group functor's source of truth
# ---------------------------------------------------------------------------
def load_nppes(path: str) -> Dict[str, Dict[str, str]]:
    """NPI -> {specialty, state, entity_type}. Used for pushforward + identity."""
    out: Dict[str, Dict[str, str]] = {}
    with _open_text(path) as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        npi_c = _require(fields, ["NPI", "npi"], "NPI")
        tax_c = _resolve(fields, ["Healthcare Provider Taxonomy Code_1"]) \
            or _resolve(fields, _SPECIALTY)
        st_c = _resolve(fields, _STATE)
        ent_c = _resolve(fields, ["Entity Type Code", "entity_type_code"])
        for row in reader:
            npi = str(row.get(npi_c, "")).strip()
            if not npi:
                continue
            out[npi] = {
                "specialty": str(row.get(tax_c, "")).strip() if tax_c else "",
                "state": str(row.get(st_c, "")).strip() if st_c else "",
                "entity_type": str(row.get(ent_c, "")).strip() if ent_c else "",
            }
    return out


def specialty_map(nppes: Mapping[str, Mapping[str, str]]) -> Dict[str, str]:
    """NPI -> specialty group label for the Level-1 pushforward."""
    return {npi: (rec.get("specialty") or "unknown") for npi, rec in nppes.items()}


# ---------------------------------------------------------------------------
# Optional: write ingested sections into the Category (mirrors grid builder)
# ---------------------------------------------------------------------------
class FlowCategoryBuilder:
    """Record provenance: source -reports-> npi:<id>, plus identity edges."""

    def __init__(self, category: Category) -> None:
        self.category = category

    def _ensure(self, name: str, type_name: str, **metadata) -> None:
        if self.category.get(name) is None:
            self.category.add(name, type_name=type_name, metadata=metadata)

    def add_section(self, section: Section, *, key_prefix: str = "npi") -> int:
        src = f"source:{section.source}"
        self._ensure(src, "data_source")
        n = 0
        for entity, value in section.values.items():
            obj = f"{key_prefix}:{entity}"
            self._ensure(obj, "provider" if key_prefix == "npi" else key_prefix)
            self.category.connect(src, obj, name="reports", confidence=1.0,
                                  amount=round(value, 2))
            n += 1
        return n

    def add_nppes(self, nppes: Mapping[str, Mapping[str, str]]) -> int:
        n = 0
        for npi, rec in nppes.items():
            obj = f"npi:{npi}"
            self._ensure(obj, "provider")
            spec = rec.get("specialty")
            state = rec.get("state")
            if spec:
                self._ensure(f"specialty:{spec}", "specialty")
                self.category.connect(obj, f"specialty:{spec}", name="has_specialty")
            if state:
                self._ensure(f"state:{state}", "state")
                self.category.connect(obj, f"state:{state}", name="in_state")
            n += 1
        return n


# ---------------------------------------------------------------------------
# Test/demo fixtures -- tiny real-schema CSVs so loaders run without downloads
# ---------------------------------------------------------------------------
def write_fixtures(directory: str) -> Dict[str, str]:
    """Write minimal CSVs using the real column names. Returns {kind: path}."""
    os.makedirs(directory, exist_ok=True)
    paths: Dict[str, str] = {}

    def _w(name: str, header: List[str], rows: List[List[object]]) -> str:
        p = os.path.join(directory, name)
        with open(p, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(rows)
        return p

    # by Provider and Service (line items): npi_over has a giant line item.
    paths["service"] = _w(
        "cms_service.csv",
        ["Rndrng_NPI", "Rndrng_Prvdr_Type", "HCPCS_Cd", "Tot_Srvcs", "Avg_Mdcr_Pymt_Amt"],
        [
            ["1000000001", "Cardiology", "99213", 1000, 50.0],   # 50,000
            ["1000000001", "Cardiology", "93000", 500, 20.0],    # 10,000 -> 60,000
            ["1000000002", "Oncology", "96413", 200, 300.0],     # 60,000
            ["1000000099", "Oncology", "96413", 9000, 300.0],    # 2,700,000 (outlier)
        ],
    )
    # by Provider (aggregate): npi_over's aggregate disagrees with line items.
    paths["summary"] = _w(
        "cms_summary.csv",
        ["Rndrng_NPI", "Rndrng_Prvdr_Type", "Tot_Mdcr_Pymt_Amt"],
        [
            ["1000000001", "Cardiology", 60000.0],
            ["1000000002", "Oncology", 60000.0],
            ["1000000099", "Oncology", 300000.0],   # vs 2.7M in line items -> leak
        ],
    )
    paths["part_d"] = _w(
        "part_d.csv",
        ["Prscrbr_NPI", "Prscrbr_Type", "Tot_Drug_Cst"],
        [["1000000001", "Cardiology", 120000.0], ["1000000099", "Oncology", 980000.0]],
    )
    paths["open_payments"] = _w(
        "open_payments.csv",
        ["Covered_Recipient_NPI", "Total_Amount_of_Payment_USDollars"],
        [["1000000099", 45000.0], ["1000000001", 1200.0]],
    )
    paths["nppes"] = _w(
        "nppes.csv",
        ["NPI", "Entity Type Code", "Healthcare Provider Taxonomy Code_1",
         "Provider Business Practice Location Address State Name"],
        [
            ["1000000001", "1", "207RC0000X", "TX"],
            ["1000000002", "1", "207RX0202X", "NY"],
            ["1000000099", "1", "207RX0202X", "FL"],
        ],
    )
    paths["usaspending"] = _w(
        "usaspending.csv",
        ["recipient_uei", "awarding_agency_name", "assistance_listing_number",
         "federal_action_obligation"],
        [["UEI0000ABC", "Department of Health and Human Services", "93.778", 2_500_000.0]],
    )
    # Medicare Advantage contracts: one fair, one upcoding, one benchmark-rich.
    paths["ma_contracts"] = _w(
        "ma_contracts.csv",
        ["contract_id", "name", "enrollment", "benchmark_per_capita",
         "ffs_per_capita", "risk_score"],
        [
            ["H1001", "FairCare HMO", 40000, 11500, 11200, 1.02],
            ["H2002", "MaxRisk Health", 120000, 12000, 11000, 1.21],
            ["H3003", "HighBench Plan", 80000, 13800, 10500, 1.06],
        ],
    )
    paths["ma_enrollment"] = _w(
        "ma_enrollment.csv",
        ["Contract Number", "Plan ID", "Enrollment"],
        [["H1001", "001", 25000], ["H1001", "002", 15000], ["H2002", "001", 120000]],
    )
    return paths
