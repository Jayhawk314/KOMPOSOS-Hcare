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
# Provider money views (charge / allowed / payment) for the sheaf gauge
# ---------------------------------------------------------------------------
def load_provider_money_views(path: str):
    """CMS by-Provider-and-Service -> three Sections over NPIs, one pass:

        charge   = sum(Avg_Sbmtd_Chrg     x Tot_Srvcs)   (chargemaster)
        allowed  = sum(Avg_Mdcr_Alowd_Amt x Tot_Srvcs)   (Medicare-allowed)
        payment  = sum(Avg_Mdcr_Pymt_Amt  x Tot_Srvcs)   (Medicare-paid)

    These are three measurements that should reconcile up to ONE global gauge
    (the canonical charge->allowed->payment markup chain). The sheaf finds that
    gauge and localizes providers whose chain breaks it -- a genuine 3-source
    coherence question that pairwise ratios cannot answer.
    """
    charge: Dict[str, float] = {}
    allowed: Dict[str, float] = {}
    payment: Dict[str, float] = {}
    with _open_text(path) as fh:
        reader = csv.DictReader(fh)
        f = reader.fieldnames or []
        npi_c = _require(f, _NPI, "NPI")
        srv_c = _require(f, ["Tot_Srvcs", "line_srvc_cnt"], "total services")
        chg_c = _require(f, ["Avg_Sbmtd_Chrg", "average_submitted_chrg_amt"], "submitted charge")
        alw_c = _require(f, ["Avg_Mdcr_Alowd_Amt", "average_Medicare_allowed_amt"], "allowed")
        pay_c = _require(f, ["Avg_Mdcr_Pymt_Amt", "average_Medicare_payment_amt"], "payment")
        for row in reader:
            npi = str(row.get(npi_c, "")).strip()
            if not npi:
                continue
            srv = _to_float(row.get(srv_c))
            charge[npi] = charge.get(npi, 0.0) + _to_float(row.get(chg_c)) * srv
            allowed[npi] = allowed.get(npi, 0.0) + _to_float(row.get(alw_c)) * srv
            payment[npi] = payment.get(npi, 0.0) + _to_float(row.get(pay_c)) * srv
    return {
        "charge": Section(source="charge", values=charge, layer="3-provider"),
        "allowed": Section(source="allowed", values=allowed, layer="3-provider"),
        "payment": Section(source="payment", values=payment, layer="3-provider"),
    }


# ---------------------------------------------------------------------------
# Medicare Inpatient Hospitals by Provider and Service (CCN x DRG)
# ---------------------------------------------------------------------------
def load_inpatient(path: str):
    """Medicare Inpatient PUF -> list of per (CCN, DRG) records (dicts).

    The price layer's real entry point: each row is a hospital (CCN) x DRG with
    discharges, chargemaster charge, total payment, and Medicare payment. Keyed
    by CCN, this starts the hospital (CCN) spine. Fields:
        ccn, name, state, drg, drg_desc, discharges, charge, total_pymt, mdcr_pymt
    """
    out = []
    with _open_text(path) as fh:
        reader = csv.DictReader(fh)
        f = reader.fieldnames or []
        ccn_c = _require(f, ["Rndrng_Prvdr_CCN", "provider_id", "ccn"], "CCN")
        nm_c = _resolve(f, ["Rndrng_Prvdr_Org_Name", "provider_name"])
        st_c = _resolve(f, ["Rndrng_Prvdr_State_Abrvtn", "provider_state"])
        drg_c = _require(f, ["DRG_Cd", "DRG_Definition", "drg_code"], "DRG code")
        dd_c = _resolve(f, ["DRG_Desc", "DRG_Definition"])
        dsc_c = _require(f, ["Tot_Dschrgs", "total_discharges"], "discharges")
        chg_c = _require(f, ["Avg_Submtd_Cvrd_Chrg",
                             "average_covered_charges"], "avg covered charge")
        tot_c = _require(f, ["Avg_Tot_Pymt_Amt", "average_total_payments"],
                         "avg total payment")
        mdc_c = _resolve(f, ["Avg_Mdcr_Pymt_Amt", "average_medicare_payments"])
        for row in reader:
            ccn = str(row.get(ccn_c, "")).strip()
            drg = str(row.get(drg_c, "")).strip()
            if not ccn or not drg:
                continue
            out.append({
                "ccn": ccn,
                "name": str(row.get(nm_c, "")).strip() if nm_c else "",
                "state": str(row.get(st_c, "")).strip() if st_c else "",
                "drg": drg,
                "drg_desc": str(row.get(dd_c, "")).strip() if dd_c else "",
                "discharges": _to_float(row.get(dsc_c)),
                "charge": _to_float(row.get(chg_c)),
                "total_pymt": _to_float(row.get(tot_c)),
                "mdcr_pymt": _to_float(row.get(mdc_c)) if mdc_c else 0.0,
            })
    return out


# ---------------------------------------------------------------------------
# Drug-level joins: Open Payments (by drug) and Part D (by Provider and Drug)
# ---------------------------------------------------------------------------
def _norm_drug(s: object) -> str:
    """Normalize a drug/brand name for cross-source matching."""
    t = " ".join(str(s or "").strip().upper().split())
    return t


def load_open_payments_by_drug(path: str, *, only_drug: bool = True):
    """Open Payments general payments -> ``{(npi, drug): payment_usd}``.

    Uses the primary associated product (slot 1). When ``only_drug`` is set,
    keeps rows flagged as Drug/Biological (skips devices/supplies, which have no
    Part D analogue). Drug names are normalized for matching to Part D brands.
    """
    out: Dict[tuple, float] = {}
    with _open_text(path) as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        npi_c = _require(fields, _NPI, "NPI")
        amt_c = _require(fields, ["Total_Amount_of_Payment_USDollars",
                                  "total_amount_of_payment_usdollars"], "payment amount")
        name_c = _require(fields, [
            "Name_of_Drug_or_Biological_or_Device_or_Medical_Supply_1"], "drug name")
        ind_c = _resolve(fields, [
            "Indicate_Drug_or_Biological_or_Device_or_Medical_Supply_1"])
        for row in reader:
            npi = str(row.get(npi_c, "")).strip()
            if not npi:
                continue
            if only_drug and ind_c:
                kind = str(row.get(ind_c, "")).strip().lower()
                if kind not in ("drug", "biological"):
                    continue
            drug = _norm_drug(row.get(name_c))
            if not drug:
                continue
            key = (npi, drug)
            out[key] = out.get(key, 0.0) + _to_float(row.get(amt_c))
    return out


def load_part_d_by_drug(path: str, *, keep_drugs=None):
    """Part D Prescribers by Provider and Drug -> ``{(npi, drug): drug_cost}``.

    ``keep_drugs`` (a set of normalized brand names) restricts the load to drugs
    that appear in Open Payments -- keeps memory bounded and the join relevant.
    Brand names are normalized to match ``load_open_payments_by_drug``.
    """
    out: Dict[tuple, float] = {}
    with _open_text(path) as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        npi_c = _require(fields, _NPI, "NPI")
        brnd_c = _require(fields, ["Brnd_Name", "brand_name"], "brand name")
        cost_c = _require(fields, ["Tot_Drug_Cst", "total_drug_cost"],
                          "total drug cost")
        for row in reader:
            npi = str(row.get(npi_c, "")).strip()
            if not npi:
                continue
            drug = _norm_drug(row.get(brnd_c))
            if not drug:
                continue
            if keep_drugs is not None and drug not in keep_drugs:
                continue
            key = (npi, drug)
            out[key] = out.get(key, 0.0) + _to_float(row.get(cost_c))
    return out


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
# Original Medicare (FFS) Geographic Variation PUF -- the consumed baseline
# ---------------------------------------------------------------------------
def load_ffs_geovar(path: str, *, year, geo_level: str = "State",
                    age_level: str = "All") -> Dict[str, Dict[str, float]]:
    """CMS Original Medicare Geographic Variation PUF -> per-geo FFS baseline.

    This is the REAL consumed-side input for the Medicare Advantage 2-cell:
    FFS per-capita is what an MA enrollee would have cost under fee-for-service,
    measured directly by CMS. Returns ``{geo_desc: {...}}`` with:
        ffs_pc        TOT_MDCR_PYMT_PC          (FFS Medicare payment per capita)
        ffs_stdzd_pc  TOT_MDCR_STDZD_PYMT_PC    (price-standardized per capita)
        ma_cnt        BENES_MA_CNT              (MA enrollees in the geo -- real)
        ffs_cnt       BENES_OM_CNT              (Original Medicare/FFS enrollees)
        ma_rate       MA_PRTCPTN_RATE           (MA participation rate)

    ``geo_level`` is one of National / State / County; ``age_level`` one of
    All / <65 / >=65. State descriptors are 2-letter codes (CA, TX, ...).
    """
    out: Dict[str, Dict[str, float]] = {}
    with _open_text(path) as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        y_c = _require(fields, ["YEAR"], "year")
        lvl_c = _require(fields, ["BENE_GEO_LVL"], "geo level")
        desc_c = _require(fields, ["BENE_GEO_DESC"], "geo description")
        age_c = _require(fields, ["BENE_AGE_LVL"], "age level")
        ma_c = _require(fields, ["BENES_MA_CNT"], "MA bene count")
        pc_c = _require(fields, ["TOT_MDCR_PYMT_PC"], "FFS payment per capita")
        spc_c = _resolve(fields, ["TOT_MDCR_STDZD_PYMT_PC"])
        om_c = _resolve(fields, ["BENES_OM_CNT"])
        rate_c = _resolve(fields, ["MA_PRTCPTN_RATE"])
        ystr = str(year)
        for row in reader:
            if str(row.get(y_c, "")).strip() != ystr:
                continue
            if str(row.get(lvl_c, "")).strip() != geo_level:
                continue
            if str(row.get(age_c, "")).strip() != age_level:
                continue
            geo = str(row.get(desc_c, "")).strip()
            if not geo:
                continue
            ffs_pc = _to_float(row.get(pc_c))
            out[geo] = {
                "ffs_pc": ffs_pc,
                "ffs_stdzd_pc": _to_float(row.get(spc_c)) if spc_c else ffs_pc,
                "ma_cnt": int(_to_float(row.get(ma_c))),
                "ffs_cnt": int(_to_float(row.get(om_c))) if om_c else 0,
                "ma_rate": _to_float(row.get(rate_c)) if rate_c else 0.0,
            }
    return out


# ---------------------------------------------------------------------------
# MA ratebook -- real county benchmark rates (the paid-side benchmark)
# ---------------------------------------------------------------------------
_STATE_NAME_TO_CODE = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR",
    "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE",
    "DISTRICT OF COLUMBIA": "DC", "FLORIDA": "FL", "GEORGIA": "GA",
    "HAWAII": "HI", "IDAHO": "ID", "ILLINOIS": "IL", "INDIANA": "IN",
    "IOWA": "IA", "KANSAS": "KS", "KENTUCKY": "KY", "LOUISIANA": "LA",
    "MAINE": "ME", "MARYLAND": "MD", "MASSACHUSETTS": "MA", "MICHIGAN": "MI",
    "MINNESOTA": "MN", "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT",
    "NEBRASKA": "NE", "NEVADA": "NV", "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ",
    "NEW MEXICO": "NM", "NEW YORK": "NY", "NORTH CAROLINA": "NC",
    "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK", "OREGON": "OR",
    "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT",
    "VERMONT": "VT", "VIRGINIA": "VA", "WASHINGTON": "WA",
    "WEST VIRGINIA": "WV", "WISCONSIN": "WI", "WYOMING": "WY",
}

# Map the requested quality-bonus tier to the substring in the rate column name.
_BONUS_COL = {"5%": "5% Bonus", "3.5%": "3.5% Bonus", "0%": "0% Bonus"}


def _ratebook_rows(path: str) -> Iterator[List[str]]:
    """Yield rows from the CMS ratebook county CSV (inside a .zip or direct).

    The ratebook ships a few CSVs; pick the all-plans CountyRate file (not PACE
    / EGWP / regional). The file has several title/note rows before the header
    that starts with ``Code,State,County Name,...``.
    """
    if path.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as zf:
            members = [n for n in zf.namelist()
                       if n.lower().endswith(".csv") and "countyrate" in n.lower()
                       and "pace" not in n.lower()]
            if not members:
                raise ValueError(f"no CountyRate CSV inside {path}")
            data = zf.read(members[0])
        fh = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8-sig", newline="")
        yield from csv.reader(fh)
    else:
        with _open_text(path) as fh:
            yield from csv.reader(fh)


def load_ma_ratebook(path: str, *, bonus: str = "5%",
                     weights: Optional[Mapping[str, float]] = None) -> Dict[str, float]:
    """CMS MA county ratebook -> per-state ANNUAL benchmark per-capita (real).

    The county rates are CMS's published Parts A&B monthly capitation
    benchmarks (risk-normalized to a 1.0 beneficiary). We pick the quality-bonus
    tier (``bonus`` in {"5%","3.5%","0%"}; most MA enrollment is in 4+ star
    plans receiving the 5% bonus) and convert monthly->annual (x12).

    County->state aggregation:
      * ``weights`` None  -> simple county mean (state assignment exact by name).
      * ``weights`` given -> MA-enrollment-weighted mean, where ``weights`` maps
        the ratebook county SSA code (zero-padded 5-digit) to a weight (county
        MA enrollment). Build it from ``load_ssa_fips_crosswalk`` +
        ``load_county_ma_enrollment``. Counties with no/zero weight fall back to
        the unweighted mean for that state, so no state is dropped.

    Returns ``{state_code: annual_benchmark_per_capita}``.
    """
    want = _BONUS_COL.get(bonus, "5% Bonus")
    # Unweighted accumulators (also the fallback when a state has no weights).
    u_sum: Dict[str, float] = {}
    u_n: Dict[str, int] = {}
    # Weighted accumulators.
    w_sum: Dict[str, float] = {}
    w_wt: Dict[str, float] = {}
    header = None
    state_i = rate_i = None
    for row in _ratebook_rows(path):
        if header is None:
            if row and row[0].strip().lower() == "code":
                header = [c.strip() for c in row]
                state_i = header.index("State")
                rate_i = next(i for i, c in enumerate(header) if want in c)
            continue
        if not row or len(row) <= rate_i:
            continue
        code = _STATE_NAME_TO_CODE.get(row[state_i].strip().upper())
        if not code:
            continue
        rate = _to_float(row[rate_i])
        if rate <= 0:
            continue
        annual = rate * 12.0
        u_sum[code] = u_sum.get(code, 0.0) + annual
        u_n[code] = u_n.get(code, 0) + 1
        if weights is not None:
            w = float(weights.get(str(row[0]).strip().zfill(5), 0.0))
            if w > 0:
                w_sum[code] = w_sum.get(code, 0.0) + annual * w
                w_wt[code] = w_wt.get(code, 0.0) + w
    out: Dict[str, float] = {}
    for code in u_sum:
        if weights is not None and w_wt.get(code, 0.0) > 0:
            out[code] = w_sum[code] / w_wt[code]
        else:
            out[code] = u_sum[code] / u_n[code]
    return out


def load_ssa_fips_crosswalk(path: str) -> Dict[str, str]:
    """SSA<->FIPS county crosswalk -> ``{ssa_code: fips_code}`` (both 5-digit).

    The MA ratebook is keyed by SSA county code; the GeoVar PUF is keyed by
    FIPS. This bridges them. Source: NBER ``ssa_fips_state_county_<year>.csv``
    (columns ``ssa_code`` / ``fipscounty``). First mapping per SSA code wins
    (the rare many-to-many border cases are negligible for enrollment weights).
    """
    out: Dict[str, str] = {}
    with _open_text(path) as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        ssa_c = _require(fields, ["ssa_code", "ssacounty", "ssa"], "SSA code")
        fips_c = _require(fields, ["fipscounty", "fips_code", "fips"], "FIPS code")
        for row in reader:
            ssa = str(row.get(ssa_c, "")).strip().zfill(5)
            fips = str(row.get(fips_c, "")).strip().zfill(5)
            if ssa and fips and ssa not in out:
                out[ssa] = fips
    return out


def load_county_ma_enrollment(path: str, *, year,
                              age_level: str = "All") -> Dict[str, int]:
    """County MA enrollment by FIPS from the FFS GeoVar PUF -> ``{fips: ma_cnt}``.

    Used as the weight for enrollment-weighting the ratebook county->state.
    Suppressed cells ('*') count as 0.
    """
    out: Dict[str, int] = {}
    with _open_text(path) as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        y_c = _require(fields, ["YEAR"], "year")
        lvl_c = _require(fields, ["BENE_GEO_LVL"], "geo level")
        cd_c = _require(fields, ["BENE_GEO_CD"], "geo code")
        age_c = _require(fields, ["BENE_AGE_LVL"], "age level")
        ma_c = _require(fields, ["BENES_MA_CNT"], "MA bene count")
        ystr = str(year)
        for row in reader:
            if str(row.get(y_c, "")).strip() != ystr:
                continue
            if str(row.get(lvl_c, "")).strip() != "County":
                continue
            if str(row.get(age_c, "")).strip() != age_level:
                continue
            fips = str(row.get(cd_c, "")).strip().zfill(5)
            if not fips or fips == "00000":
                continue
            out[fips] = int(_to_float(row.get(ma_c)))
    return out


def load_ma_risk(path: str) -> Dict[str, float]:
    """Optional user-supplied MA risk score by geo -> {geo: risk_score}.

    Per-geography MA risk scores are NOT published as a free public file (CMS
    computes them from restricted encounter/RAPS data; MedPAC estimates coding
    intensity nationally). This loader lets real risk scores be slotted in when
    obtained from any source. CSV columns (aliases): geo/state/contract_id and
    risk_score/risk/raf.
    """
    out: Dict[str, float] = {}
    with _open_text(path) as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        g_c = _require(fields, ["geo", "state", "contract_id", "STATE"], "geo")
        r_c = _require(fields, ["risk_score", "risk", "raf"], "risk score")
        for row in reader:
            g = str(row.get(g_c, "")).strip()
            if not g:
                continue
            out[g] = _to_float(row.get(r_c))
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
    # FFS Geographic Variation PUF (real consumed baseline for the MA 2-cell).
    paths["ffs_geovar"] = _w(
        "ffs_geovar.csv",
        ["YEAR", "BENE_GEO_LVL", "BENE_GEO_DESC", "BENE_GEO_CD", "BENE_AGE_LVL",
         "BENES_OM_CNT", "BENES_MA_CNT", "MA_PRTCPTN_RATE",
         "TOT_MDCR_PYMT_PC", "TOT_MDCR_STDZD_PYMT_PC"],
        [
            ["2024", "National", "National", "", "All", 27732177, 33677969, 0.5484, 13605.51, 12553.26],
            ["2024", "State", "CA", "06", "All", 2000000, 3466321, 0.60, 14000.0, 13254.0],
            ["2024", "State", "TX", "48", "All", 1800000, 2505775, 0.55, 13500.0, 14056.0],
            ["2024", "State", "PR", "72", "All", 50000, 400000, 0.85, 9000.0, 11000.0],  # territory -> skipped
            ["2024", "State", "CA", "06", "<65", 300000, 400000, 0.50, 16000.0, 15000.0],# wrong age -> ignored
            # Prior years (for the multi-year trend engine): CA & TX 2022-2023.
            ["2023", "State", "CA", "06", "All", 2050000, 3200000, 0.59, 13600.0, 12900.0],
            ["2022", "State", "CA", "06", "All", 2100000, 3000000, 0.58, 13200.0, 12500.0],
            ["2023", "State", "TX", "48", "All", 1850000, 2350000, 0.54, 13200.0, 13700.0],
            ["2022", "State", "TX", "48", "All", 1900000, 2200000, 0.53, 12900.0, 13400.0],
            # County rows (FIPS-keyed MA enrollment) for enrollment weighting:
            ["2024", "County", "CA-Alpha", "06001", "All", 5000, 1000, 0.50, 13000.0, 12000.0],
            ["2024", "County", "CA-Beta", "06003", "All", 8000, 3000, 0.60, 14500.0, 13800.0],
            ["2024", "County", "TX-Gamma", "48001", "All", 6000, 2000, 0.55, 13500.0, 14056.0],
        ],
    )
    # MA ratebook county rates (real CMS schema: title rows, then Code,State,...
    # with monthly Parts A&B benchmarks at three quality-bonus tiers).
    rb = os.path.join(directory, "CountyRate2024.csv")
    with open(rb, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Medicare Advantage Monthly Capitation Rates for 2024", "", "", "", "", "", ""])
        w.writerow(["Note: illustrative fixture", "", "", "", "", "", ""])
        w.writerow(["Code", "State", "County Name",
                    "Parts A&B 5% Bonus 2024 Rate", "Parts A&B 3.5% Bonus 2024 Rate",
                    "Parts A&B 0% Bonus 2024 Rate", "Parts A&B ESRD 2024 Rate"])
        # CA: two counties, mean monthly 5%-rate = 1,200 -> annual 14,400.
        w.writerow(["05000", "CALIFORNIA", "ALPHA", "1,100.00", "1,080.00", "1,000.00", "8,300.00"])
        w.writerow(["05010", "CALIFORNIA", "BETA", "1,300.00", "1,280.00", "1,200.00", "8,300.00"])
        # TX: one county, monthly 5%-rate 1,000 -> annual 12,000.
        w.writerow(["45000", "TEXAS", "GAMMA", "1,000.00", "980.00", "900.00", "8,300.00"])
        # Territory not in the state map -> skipped.
        w.writerow(["72000", "PUERTO RICO", "SANJUAN", "900.00", "880.00", "800.00", "8,300.00"])
    paths["ma_ratebook"] = rb
    paths["ma_risk"] = _w(
        "ma_risk.csv",
        ["state", "risk_score"],
        [["CA", 1.15], ["TX", 1.25]],
    )
    # Open Payments with drug detail (for the drug-level conflict join).
    paths["op_by_drug"] = _w(
        "op_by_drug.csv",
        ["Covered_Recipient_NPI", "Total_Amount_of_Payment_USDollars",
         "Indicate_Drug_or_Biological_or_Device_or_Medical_Supply_1",
         "Name_of_Drug_or_Biological_or_Device_or_Medical_Supply_1"],
        [
            ["100", 5000, "Drug", "Eliquis"],
            ["100", 1000, "Drug", "Eliquis"],          # summed -> 6000 for (100,ELIQUIS)
            ["101", 8000, "Drug", "Eliquis"],
            ["102", 2000, "Device", "SomeStent"],       # device -> skipped
        ],
    )
    # Part D by Provider AND Drug (brand-keyed).
    paths["partd_by_drug"] = _w(
        "partd_by_drug.csv",
        ["Prscrbr_NPI", "Brnd_Name", "Gnrc_Name", "Tot_Drug_Cst"],
        [
            ["100", "ELIQUIS", "apixaban", 900000],
            ["101", "Eliquis", "apixaban", 800000],
            ["103", "eliquis", "apixaban", 90000],      # unpaid prescriber
            ["104", "Ozempic", "semaglutide", 500000],  # different drug
        ],
    )
    # Medicare Inpatient PUF (hospital CCN x DRG) for the price layer.
    paths["inpatient"] = _w(
        "inpatient.csv",
        ["Rndrng_Prvdr_CCN", "Rndrng_Prvdr_Org_Name", "Rndrng_Prvdr_State_Abrvtn",
         "DRG_Cd", "DRG_Desc", "Tot_Dschrgs", "Avg_Submtd_Cvrd_Chrg",
         "Avg_Tot_Pymt_Amt", "Avg_Mdcr_Pymt_Amt"],
        [
            ["450001", "TX Hosp A", "TX", "470", "JOINT REPL", 100, 60000, 15000, 13500],
            ["450002", "TX Hosp B", "TX", "470", "JOINT REPL", 100, 64000, 16000, 14400],
            ["450003", "TX Hosp C", "TX", "470", "JOINT REPL", 100, 56000, 14000, 12600],
            ["450004", "TX Hosp D", "TX", "470", "JOINT REPL", 100, 62000, 15500, 13950],
            ["450005", "TX Hosp E", "TX", "470", "JOINT REPL", 100, 58000, 14800, 13320],
            ["450099", "TX Pricey", "TX", "470", "JOINT REPL", 200, 300000, 40000, 36000],
        ],
    )
    # SSA<->FIPS crosswalk: ratebook SSA codes -> GeoVar county FIPS codes.
    paths["ssa_fips"] = _w(
        "ssa_fips.csv",
        ["ssa_code", "fipscounty", "state", "countyname_fips"],
        [
            ["05000", "06001", "CA", "ALPHA"],
            ["05010", "06003", "CA", "BETA"],
            ["45000", "48001", "TX", "GAMMA"],
        ],
    )
    return paths
