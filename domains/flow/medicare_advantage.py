# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Medicare Advantage paid-vs-consumed 2-cell -- the headline overpayment.

The insurance edge of the money graph is where federal dollars become private
dollars. CMS pays MA plans a *capitated, risk-adjusted* amount; the plan then
covers care. There are two parallel ways to value a contract's year:

    paid:      plan ==(capitated benchmark x risk score)==>  coverage
    consumed:  plan ==(FFS-equivalent cost of care)=======>  coverage

These are PARALLEL 1-morphisms (same source ``plan:<contract>``, same target
``coverage:<contract>``). The **2-cell** between them is exactly the
overpayment -- a morphism-of-morphisms measuring how much ``paid`` exceeds
``consumed``. The categorical runtime's ``InfinityCosmos`` auto-detects the
parallel pair and materializes the 2-cell in the homotopy 2-category (COG
Tier 4 reasoning); this module computes its magnitude and decomposition.

Honest data note
----------------
MA encounter data (what was actually consumed) is restricted. We use the
public FFS-equivalent proxy: county FFS per-capita x enrollment, at the
demographic (non-coding) risk baseline. The gap then splits cleanly into:

    overpayment = coding_intensity + benchmark_spread

  coding_intensity : risk score above the FFS baseline, priced at FFS rates
                     (the documented MA upcoding mechanism; MedPAC ~8-20%).
  benchmark_spread : the benchmark being set above local FFS cost.

CMS applies a statutory minimum coding-intensity adjustment (5.9% in recent
years); we apply it by default so the estimate is conservative, not inflated.

Exact identity (so the decomposition is provable, not hand-waved):
    paid - consumed = E*(bm*er - ffs*fr)
    coding_intensity = E*ffs*(er - fr)
    benchmark_spread = E*(bm - ffs)*er
    coding_intensity + benchmark_spread = E*(bm*er - ffs*fr)   [QED]
  where E=enrollment, bm=benchmark p.c., ffs=FFS p.c., er=effective MA risk
  (risk_score after coding adjustment), fr=FFS demographic risk.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

# Statutory minimum MA coding-intensity adjustment (recent years ~5.9%).
DEFAULT_CODING_ADJUSTMENT = 0.059


@dataclass
class MAContract:
    """One Medicare Advantage contract's inputs for the paid/consumed 2-cell."""

    contract_id: str
    enrollment: int
    benchmark_per_capita: float       # annual capitated benchmark, per member
    ffs_per_capita: float             # county FFS per-capita (consumed proxy)
    risk_score: float = 1.0           # MA risk score (coding intensity lives here)
    ffs_risk: float = 1.0             # FFS demographic risk baseline (usually ~1.0)
    name: str = ""                    # optional plan/insurer name


@dataclass
class OverpaymentResult:
    contract_id: str
    enrollment: int
    paid: float
    consumed: float
    overpayment: float
    ratio: float                      # overpayment / paid, clamped to [0, 1]
    coding_intensity: float           # portion from risk-score excess
    benchmark_spread: float           # portion from benchmark > FFS
    name: str = ""


class MedicareAdvantageTwoCell:
    """Compute the MA overpayment 2-cell and record it in the Category.

    Parameters
    ----------
    category:
        Optional KOMPOSOS Category to write structure into.
    cosmos:
        Optional ``InfinityCosmos`` over that category; when present, the
        parallel paid/consumed morphisms are formally registered as a 2-cell.
    coding_adjustment:
        Statutory coding-intensity haircut applied to the MA risk score.
    """

    def __init__(self, category=None, cosmos=None,
                 coding_adjustment: float = DEFAULT_CODING_ADJUSTMENT) -> None:
        self.category = category
        self.cosmos = cosmos
        self.coding_adjustment = coding_adjustment

    # -- core computation ------------------------------------------------
    def evaluate(self, c: MAContract) -> OverpaymentResult:
        E = float(c.enrollment)
        bm = c.benchmark_per_capita
        ffs = c.ffs_per_capita
        er = c.risk_score * (1.0 - self.coding_adjustment)   # effective MA risk
        fr = c.ffs_risk

        paid = E * bm * er
        consumed = E * ffs * fr
        overpayment = paid - consumed
        coding_intensity = E * ffs * (er - fr)
        benchmark_spread = E * (bm - ffs) * er
        ratio = max(0.0, min(1.0, overpayment / paid)) if paid > 0 else 0.0

        result = OverpaymentResult(
            contract_id=c.contract_id, enrollment=c.enrollment,
            paid=paid, consumed=consumed, overpayment=overpayment, ratio=ratio,
            coding_intensity=coding_intensity, benchmark_spread=benchmark_spread,
            name=c.name,
        )
        if self.category is not None:
            self._to_category(result)
        return result

    def evaluate_all(self, contracts: Iterable[MAContract]) -> List[OverpaymentResult]:
        return [self.evaluate(c) for c in contracts]

    # -- write the 2-cell into the Category ------------------------------
    def _to_category(self, r: OverpaymentResult) -> None:
        cat = self.category
        plan = f"plan:{r.contract_id}"
        cover = f"coverage:{r.contract_id}"
        cat.add(plan, type_name="ma_contract")
        cat.add(cover, type_name="coverage")

        # Parallel 1-morphisms; confidence carries a normalized magnitude,
        # raw dollars live in metadata. Names are contract-unique so the
        # cosmos' auto-detection materializes a distinct 2-cell per contract
        # (it names 2-cells after the morphism names).
        scale = max(r.paid, r.consumed) or 1.0
        paid_mor = cat.connect(plan, cover, name=f"paid::{r.contract_id}",
                               confidence=round(min(1.0, r.paid / scale), 4),
                               kind="paid", amount=round(r.paid, 2))
        consumed_mor = cat.connect(plan, cover, name=f"consumed::{r.contract_id}",
                                   confidence=round(min(1.0, r.consumed / scale), 4),
                                   kind="consumed", amount=round(r.consumed, 2))

        # Summary edge: how much this plan overpays Medicare.
        cat.add("medicare", type_name="program")
        cat.connect(plan, "medicare", name="overpays",
                    confidence=round(r.ratio, 4),
                    overpayment=round(r.overpayment, 2),
                    coding_intensity=round(r.coding_intensity, 2),
                    benchmark_spread=round(r.benchmark_spread, 2))

        # Formally register the 2-cell (consumed => paid) when a cosmos exists.
        if self.cosmos is not None:
            try:
                self.cosmos.add_two_cell(
                    f"overpay::{r.contract_id}",
                    consumed_mor.id, paid_mor.id,
                    data={"overpayment": r.overpayment, "ratio": r.ratio,
                          "coding_intensity": r.coding_intensity,
                          "benchmark_spread": r.benchmark_spread},
                )
            except Exception:
                # Cosmos auto-detects parallel morphisms anyway; explicit
                # registration is best-effort.
                pass


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def summarize(results: List[OverpaymentResult], top: int = 15) -> str:
    lines: List[str] = []
    lines.append("Medicare Advantage paid-vs-consumed 2-cell (overpayment)")
    lines.append("=" * 72)
    total_paid = sum(r.paid for r in results)
    total_consumed = sum(r.consumed for r in results)
    total_over = sum(r.overpayment for r in results)
    total_coding = sum(r.coding_intensity for r in results)
    total_spread = sum(r.benchmark_spread for r in results)
    enr = sum(r.enrollment for r in results)

    for r in sorted(results, key=lambda x: -x.overpayment)[:top]:
        tag = r.name or r.contract_id
        lines.append(
            f"  {tag:<22} enr={r.enrollment:>8,}"
            f"  paid ${r.paid:>14,.0f}  consumed ${r.consumed:>14,.0f}"
            f"  overpay ${r.overpayment:>13,.0f} ({r.ratio:.0%})"
        )
    lines.append("-" * 72)
    lines.append(f"  contracts: {len(results)}   enrollees: {enr:,}")
    lines.append(f"  paid:      ${total_paid:,.0f}")
    lines.append(f"  consumed:  ${total_consumed:,.0f}")
    lines.append(f"  OVERPAYMENT: ${total_over:,.0f}")
    if total_over:
        lines.append(
            f"    = coding intensity ${total_coding:,.0f} "
            f"({total_coding / total_over:.0%})"
            f"  +  benchmark spread ${total_spread:,.0f} "
            f"({total_spread / total_over:.0%})"
        )
    if enr:
        lines.append(f"  overpayment per enrollee: ${total_over / enr:,.0f}/yr")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Synthetic contracts for the demo (plausible, illustrative numbers)
# ---------------------------------------------------------------------------
def synthetic_contracts() -> List[MAContract]:
    """A few contracts spanning clean, coding-heavy, and benchmark-heavy cases."""
    return [
        # Roughly fair plan: risk ~ FFS, benchmark ~ FFS.
        MAContract("H1001", 40_000, benchmark_per_capita=11_500,
                   ffs_per_capita=11_200, risk_score=1.02, name="FairCare HMO"),
        # Heavy upcoding: risk score well above FFS baseline.
        MAContract("H2002", 120_000, benchmark_per_capita=12_000,
                   ffs_per_capita=11_000, risk_score=1.21, name="MaxRisk Health"),
        # Benchmark-driven: rich benchmark county, modest coding.
        MAContract("H3003", 80_000, benchmark_per_capita=13_800,
                   ffs_per_capita=10_500, risk_score=1.06, name="HighBench Plan"),
        # Large national plan, moderate coding.
        MAContract("H4004", 300_000, benchmark_per_capita=12_400,
                   ffs_per_capita=11_300, risk_score=1.13, name="National MA Co"),
    ]
