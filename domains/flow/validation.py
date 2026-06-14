# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Cross-check the flow domain's MA overpayment estimate against published
authoritative figures (MedPAC, CMS RADV, HHS-OIG).

Why this matters: a categorical estimate is only credible if it lands in the
neighborhood of the numbers the oversight bodies publish. This module encodes
those figures (with citations) and scores our estimate against them.

Two different KINDS of number, not to be conflated:
  * ECONOMIC overpayment (MedPAC): what the program pays MA above what the same
    enrollees would cost in fee-for-service. This is what our 2-cell estimates.
  * ENFORCEMENT recoveries (RADV / OIG): the auditable subset CMS can actually
    claw back from unsupported diagnoses. Orders of magnitude smaller, and the
    RADV extrapolation rule was vacated by a federal court in Sept 2025.

Our estimate should be compared to MedPAC; RADV/OIG are shown as the much lower
enforcement floor for context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass(frozen=True)
class Benchmark:
    """One published reference figure for MA overpayment."""

    key: str
    year: int
    kind: str                     # "economic" or "enforcement"
    total_usd: float              # headline dollars (annual unless noted)
    pct_above_ffs: Optional[float] = None
    components: Dict[str, float] = field(default_factory=dict)
    source: str = ""
    url: str = ""
    note: str = ""


# ---------------------------------------------------------------------------
# Published figures (annual, unless the note says otherwise).
# ---------------------------------------------------------------------------
PUBLISHED: Dict[str, Benchmark] = {
    "medpac_2025": Benchmark(
        key="medpac_2025", year=2025, kind="economic",
        total_usd=84e9, pct_above_ffs=0.20,
        components={"coding_intensity": 40e9, "favorable_selection": 44e9},
        source="MedPAC, Report to Congress, March 2025, Ch. 11",
        url="https://www.medpac.gov/wp-content/uploads/2025/03/Mar25_Ch11_MedPAC_Report_To_Congress_SEC.pdf",
        note="MA paid ~20% above FFS; coding raises risk ~16% (net +10% after "
             "the 5.9% statutory cut) = $40B; favorable selection = $44B.",
    ),
    "medpac_2024": Benchmark(
        key="medpac_2024", year=2024, kind="economic",
        total_usd=83e9, pct_above_ffs=0.22,
        source="MedPAC, Report to Congress, March 2024, Ch. 11",
        url="https://www.medpac.gov/document/march-2024-report-to-the-congress-medicare-payment-policy/",
        note="MA paid ~122% of FFS in 2024.",
    ),
    "radv_finalrule": Benchmark(
        key="radv_finalrule", year=2025, kind="enforcement",
        total_usd=0.479e9, pct_above_ffs=None,
        source="CMS RADV Final Rule (CMS-4185-F2), Jan 2023",
        url="https://www.cms.gov/newsroom/fact-sheets/medicare-advantage-risk-adjustment-data-validation-final-rule-cms-4185-f2-fact-sheet",
        note="~$4.7B total recoveries 2023-2032 (~$0.479B/yr, PY2018 start). "
             "Extrapolation VACATED by a federal district court Sept 2025 -- "
             "currently near-zero enforceable. Enforcement floor, not economic.",
    ),
    "oig_2023": Benchmark(
        key="oig_2023", year=2023, kind="enforcement",
        total_usd=7.5e9, pct_above_ffs=None,
        source="HHS-OIG risk-adjustment reports (chart reviews + HRAs, 2018 DOS)",
        url="https://oig.hhs.gov/oei/reports/OEI-03-17-00474.asp",
        note="Estimated MA payments from unsupported/HRA-only diagnoses; a "
             "documented-overpayment subset, between RADV and the MedPAC total.",
    ),
}


@dataclass
class CrossCheck:
    our_total: float
    our_pct_above_ffs: float
    benchmark: Benchmark
    dollar_ratio: float           # our_total / benchmark.total
    pct_point_diff: Optional[float]
    verdict: str


def _verdict(dollar_ratio: float) -> str:
    if 0.85 <= dollar_ratio <= 1.20:
        return "CONSISTENT"
    if 0.6 <= dollar_ratio <= 1.5:
        return "SAME ORDER (high)" if dollar_ratio > 1 else "SAME ORDER (low)"
    return "OUT OF RANGE (high)" if dollar_ratio > 1 else "OUT OF RANGE (low)"


def cross_check(paid: float, consumed: float, *,
                against: str = "medpac_2025") -> CrossCheck:
    """Score our (paid, consumed) totals against a published benchmark."""
    b = PUBLISHED[against]
    our_total = paid - consumed
    our_pct = (paid / consumed - 1.0) if consumed else 0.0
    ratio = our_total / b.total_usd if b.total_usd else float("inf")
    ppd = (our_pct - b.pct_above_ffs) if b.pct_above_ffs is not None else None
    return CrossCheck(our_total, our_pct, b, ratio, ppd, _verdict(ratio))


def summarize_cross_check(paid: float, consumed: float,
                          coding_intensity: Optional[float] = None) -> str:
    """Full ledger-vs-published cross-check, primary against MedPAC."""
    our_total = paid - consumed
    our_pct = (paid / consumed - 1.0) if consumed else 0.0
    lines = []
    lines.append("cross-check vs published authoritative figures")
    lines.append("=" * 72)
    lines.append(f"  our estimate:   overpayment ${our_total:,.0f}  "
                 f"({our_pct:.1%} above FFS)")
    if coding_intensity is not None:
        lines.append(f"                  of which coding intensity "
                     f"${coding_intensity:,.0f}")
    lines.append("")
    # Economic benchmarks (the right comparison).
    for key in ("medpac_2025", "medpac_2024"):
        cc = cross_check(paid, consumed, against=key)
        b = cc.benchmark
        extra = ""
        if cc.pct_point_diff is not None:
            extra = (f"; {b.pct_above_ffs:.0%} above FFS "
                     f"(us {cc.pct_point_diff:+.1%} pts)")
        lines.append(f"  [{b.kind:11}] {b.source}")
        lines.append(f"      ${b.total_usd:,.0f}{extra}")
        lines.append(f"      -> our $ / theirs = {cc.dollar_ratio:.2f}x   "
                     f"verdict: {cc.verdict}")
        if b.components and coding_intensity is not None:
            cr = coding_intensity / b.components["coding_intensity"]
            lines.append(f"      coding intensity: ours ${coding_intensity:,.0f}"
                         f" vs ${b.components['coding_intensity']:,.0f} "
                         f"({cr:.2f}x)")
    lines.append("")
    # Enforcement floor (context only).
    for key in ("oig_2023", "radv_finalrule"):
        b = PUBLISHED[key]
        mult = our_total / b.total_usd if b.total_usd else float("inf")
        lines.append(f"  [{b.kind:11}] {b.source}")
        lines.append(f"      ${b.total_usd:,.0f}/yr  -> our estimate is "
                     f"{mult:,.0f}x this enforcement figure")
        lines.append(f"      {b.note}")
    lines.append("-" * 72)
    lines.append("  MedPAC is the economic benchmark to match; RADV/OIG are the "
                 "much smaller\n  recoverable floor. A modest overshoot vs MedPAC"
                 " is expected from the\n  uniform MA risk parameter + benchmark"
                 "-vs-standardized-FFS normalization.")
    return "\n".join(lines)
