# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Catalog of public datasets in the U.S. healthcare money-flow graph.

Each :class:`DataSource` is one section of a presheaf over the money graph.
``layer`` says which edge of the chain it covers; ``join_key`` is how it is
glued to the others. ``status`` is honest about what is freely public versus
restricted (we use public aggregates as proxies where patient-level data is
not available).

The whole point of the flow domain: these sources are supposed to describe
the same dollars. Sheaf coherence (``domains.flow.coherence``) finds where
they do not agree -- and that gap is the leak.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

# Layers of the money chain (top = source of money, bottom = consumption).
LAYER_FEDERAL = "0-federal"          # Treasury -> CMS appropriations / obligations
LAYER_PROGRAM = "1-program"          # CMS program-level spend (Medicare A/B/C/D, Medicaid)
LAYER_INSURER = "2-insurer"          # CMS -> private plans (Medicare Advantage / managed Medicaid)
LAYER_PROVIDER = "3-provider"        # Plan/CMS -> hospital / provider (billing, claims)
LAYER_PHARMA = "4-pharma"            # Drug manufacturer -> provider (conflict of interest)
LAYER_PRICE = "5-price"              # Hospital -> patient (transparency prices)
LAYER_KEYS = "key"                   # identity / join registries (not money, the glue)


@dataclass(frozen=True)
class DataSource:
    """One public dataset = one section of the money-graph presheaf."""

    name: str
    layer: str
    granularity: str          # the object type it is keyed by
    join_key: str             # the identifier used to glue it to other sources
    url: str
    status: str               # "public", "public-aggregate", or "restricted"
    cpu_ok: bool              # fits comfortably on a 32 GB CPU laptop?
    notes: str = ""
    formats: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# The catalog. Ordered top-of-chain to bottom, keys last.
# ---------------------------------------------------------------------------
SOURCES: List[DataSource] = [
    # --- Layer 0: federal appropriations / obligations -------------------
    DataSource(
        name="USASpending HHS/CMS obligations",
        layer=LAYER_FEDERAL,
        granularity="award / agency obligation",
        join_key="recipient_uei + CFDA/program",
        url="https://api.usaspending.gov/",
        status="public",
        cpu_ok=True,
        formats=["api", "bulk-csv"],
        notes="Top edge: Treasury -> CMS. Filter to HHS (agency 075) / CMS.",
    ),
    DataSource(
        name="National Health Expenditure (NHE)",
        layer=LAYER_PROGRAM,
        granularity="program-year aggregate",
        join_key="program + year",
        url="https://www.cms.gov/data-research/statistics-trends-reports/national-health-expenditure-data",
        status="public-aggregate",
        cpu_ok=True,
        formats=["xlsx", "csv"],
        notes="The conservation check's top-line totals per program per year.",
    ),

    # --- Layer 2: the insurance link (federal $ -> private plans) --------
    DataSource(
        name="Medicare Advantage enrollment",
        layer=LAYER_INSURER,
        granularity="plan (contract + plan id) x county x month",
        join_key="contract_id + plan_id",
        url="https://www.cms.gov/data-research/statistics-trends-reports/medicare-advantagepart-d-contract-and-enrollment-data",
        status="public",
        cpu_ok=True,
        formats=["csv"],
        notes="WHO the federal dollars flow to via private insurers.",
    ),
    DataSource(
        name="Medicare Advantage plan payment / rate book",
        layer=LAYER_INSURER,
        granularity="plan / county benchmark",
        join_key="contract_id + plan_id",
        url="https://www.cms.gov/medicare/payment/medicare-advantage-rates-statistics",
        status="public-aggregate",
        cpu_ok=True,
        formats=["xlsx"],
        notes="HOW MUCH CMS pays plans (capitated, risk-adjusted benchmarks).",
    ),
    DataSource(
        name="RADV / risk-adjustment audit findings",
        layer=LAYER_INSURER,
        granularity="contract",
        join_key="contract_id",
        url="https://www.cms.gov/data-research/monitoring-programs/medicare-part-c-d/risk-adjustment-data-validation-radv",
        status="public-aggregate",
        cpu_ok=True,
        formats=["pdf", "xlsx"],
        notes="Published MA overpayment estimates. The headline-number target.",
    ),

    # --- Layer 3: provider billing / claims -----------------------------
    DataSource(
        name="Medicare Physician & Other Practitioners",
        layer=LAYER_PROVIDER,
        granularity="provider (NPI) x HCPCS code",
        join_key="npi",
        url="https://data.cms.gov/provider-summary-by-type-of-service",
        status="public",
        cpu_ok=True,
        formats=["csv", "api"],
        notes="Fee-for-service billing. Yoneda fingerprint = a provider's "
              "bag of HCPCS codes vs peers.",
    ),
    DataSource(
        name="Medicare Part D Prescriber",
        layer=LAYER_PROVIDER,
        granularity="provider (NPI) x drug",
        join_key="npi",
        url="https://data.cms.gov/provider-summary-by-type-of-service/medicare-part-d-prescribers",
        status="public",
        cpu_ok=True,
        formats=["csv", "api"],
        notes="Prescribing patterns. Pairs with Open Payments as a 2-cell.",
    ),
    DataSource(
        name="Hospital cost reports (HCRIS)",
        layer=LAYER_PROVIDER,
        granularity="hospital (CCN)",
        join_key="ccn",
        url="https://www.cms.gov/data-research/statistics-trends-reports/cost-reports",
        status="public",
        cpu_ok=True,
        formats=["csv"],
        notes="Independent measurement pathway for hospital-level dollars.",
    ),

    # --- Layer 4: pharma -> provider (conflict of interest) -------------
    DataSource(
        name="CMS Open Payments",
        layer=LAYER_PHARMA,
        granularity="payment (manufacturer -> NPI)",
        join_key="npi",
        url="https://openpaymentsdata.cms.gov/",
        status="public",
        cpu_ok=True,
        formats=["csv", "api"],
        notes="~GB/yr. The conflict-of-interest 2-cell partner to Part D.",
    ),

    # --- Layer 5: hospital -> patient prices ----------------------------
    DataSource(
        name="Hospital price transparency (MRF)",
        layer=LAYER_PRICE,
        granularity="hospital (CCN) x code x payer",
        join_key="ccn + code",
        url="https://www.cms.gov/hospital-price-transparency",
        status="public",
        cpu_ok=True,
        formats=["json", "csv"],
        notes="Messy per-hospital files. 'Same DRG, different price' is a "
              "sheaf coherence problem. Stay on hospital MRFs (payer TiC "
              "files are TB-scale).",
    ),

    # --- Keys: the glue -------------------------------------------------
    DataSource(
        name="NPPES NPI registry",
        layer=LAYER_KEYS,
        granularity="provider (NPI)",
        join_key="npi",
        url="https://download.cms.gov/nppes/NPI_Files.html",
        status="public",
        cpu_ok=True,
        formats=["csv"],
        notes="Maps NPI -> name, specialty (taxonomy), location. The "
              "provider->peer-group functor's source of truth.",
    ),

    # --- Restricted (documented, used via public proxies) ----------------
    DataSource(
        name="T-MSIS Medicaid claims",
        layer=LAYER_PROVIDER,
        granularity="patient-level claim",
        join_key="npi / beneficiary",
        url="https://www.medicaid.gov/dq-atlas/",
        status="restricted",
        cpu_ok=False,
        notes="Patient-level not freely public. Use state/program aggregates "
              "as proxy; flag the gap honestly.",
    ),
    DataSource(
        name="Medicare Advantage encounter data",
        layer=LAYER_INSURER,
        granularity="patient-level encounter",
        join_key="contract_id / beneficiary",
        url="https://www.cms.gov/",
        status="restricted",
        cpu_ok=False,
        notes="Not freely public. The MA paid-vs-consumed 2-cell uses public "
              "rate book + FFS-equivalent proxies instead.",
    ),
]


def by_layer(layer: str) -> List[DataSource]:
    """All sources covering one edge of the money chain."""
    return [s for s in SOURCES if s.layer == layer]


def public_sources() -> List[DataSource]:
    """Sources we can actually pull freely today (public or public-aggregate)."""
    return [s for s in SOURCES if s.status != "restricted"]


def print_registry() -> None:
    """Human-readable dump of the catalog, grouped by layer."""
    order = [
        LAYER_FEDERAL, LAYER_PROGRAM, LAYER_INSURER,
        LAYER_PROVIDER, LAYER_PHARMA, LAYER_PRICE, LAYER_KEYS,
    ]
    print("flow domain -- data source registry")
    print("=" * 72)
    for layer in order:
        rows = by_layer(layer)
        if not rows:
            continue
        print(f"\n[{layer}]")
        for s in rows:
            flag = {"public": "OK ", "public-aggregate": "agg", "restricted": "RES"}[s.status]
            cpu = "cpu" if s.cpu_ok else "BIG"
            print(f"  {flag} {cpu}  {s.name}")
            print(f"            key={s.join_key}  <{s.granularity}>")
    pub = len(public_sources())
    print(f"\n{pub}/{len(SOURCES)} sources freely pullable today.")


if __name__ == "__main__":
    print_registry()
