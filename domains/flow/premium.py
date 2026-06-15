# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Phase D -- the premium / rebate proxy and the honest reform tradeoff.

What this layer is (and is NOT)
-------------------------------
This is NOT game theory. The equilibrium (endogenous coding intensity, the
benchmark response) is produced by ``scenario.py`` and ``propagation.py``. This
module is a transparent ACCOUNTING proxy on top of that equilibrium: it maps the
benchmark / coding outcome to the MA rebate that funds beneficiary value
(supplemental benefits, $0-premium plans, reduced cost-sharing). Premiums are a
STATED PROXY, clearly labeled -- per the plan's honest boundary, not a forecast.

The MA rebate mechanism (the real accounting)
---------------------------------------------
A plan submits a standardized ``bid`` (its cost to provide Part A/B benefits). If
the bid is below the county ``benchmark``, the plan keeps a **rebate**:

    rebate_per_capita = rebate_share * max(0, benchmark - bid)          (standardized)
    rebate_dollars    = rebate_per_capita * er * enrollment             (risk-adjusted)

``rebate_share`` is set by the plan's star rating (50% / 65% / 70%); the rebate
must be spent on supplemental benefits, Part B/D premium buy-downs, or reduced
cost-sharing -- i.e. it is BENEFICIARY value. We model the bid as a fraction of
local FFS cost (managed-care efficiency: bids run ~83% of FFS; MedPAC 2024).

Why this matters -- the tradeoff the engine exists to surface
-------------------------------------------------------------
Because the rebate is risk-adjusted, **coding intensity partly funds beneficiary
benefits**, and because it is ``benchmark - bid``, **richer benchmarks fund more
benefits**. So a reform that cuts overpayment (lower benchmark, less coding) also
cuts the rebate-funded benefits enrollees see. That is the central, politically
load-bearing tension in MA reform, and the credible thing this engine adds: it
shows BOTH the federal saving AND the beneficiary cost of the same lever, instead
of pretending a cut is free.

Defaults (overridable, exposed -- no hidden assumptions)
--------------------------------------------------------
    rebate_share = 0.65   typical 4-star plan (CMS: 50/65/70% by rating)
    bid_to_ffs   = 0.83   avg MA bid as a share of FFS A/B cost (MedPAC 2024)
    premium_share= 0.30   share of the rebate going to premium / cost-sharing
                          buy-down vs other supplemental benefits (illustrative)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from domains.flow.scenario import (
    Market, PolicyLevers, BehavioralModel, ScenarioEngine, ScenarioResult,
)
from domains.flow.market import MarketModel, PatientModel


@dataclass(frozen=True)
class RebateModel:
    """Exposed accounting parameters mapping the equilibrium to beneficiary value."""

    rebate_share: float = 0.65       # statutory star-rating rebate % of (benchmark-bid)
    bid_to_ffs: float = 0.83         # standardized bid as a share of FFS cost
    premium_share: float = 0.30      # rebate share to premium/cost-sharing buydown


@dataclass
class BeneficiaryOutcome:
    label: str
    rebate_total: float              # total risk-adjusted rebate dollars
    enrollment: int
    rebate_per_enrollee: float
    premium_relief_total: float      # rebate share to premium / cost-sharing
    premium_relief_per_enrollee: float
    supplemental_total: float        # rebate share to other supplemental benefits


def beneficiary_outcome(engine: ScenarioEngine, levers: PolicyLevers,
                        rebate: Optional[RebateModel] = None,
                        audit_by_geo: Optional[Dict[str, float]] = None,
                        market_model: Optional[MarketModel] = None,
                        patient_model: Optional[PatientModel] = None,
                        ) -> BeneficiaryOutcome:
    """Rebate-funded beneficiary value under a scenario.

    The reported rebate VALUE is the Phase-D statutory accounting (restored, so
    the baseline reproduces the ~$93.5B / ~$2,800-per-enrollee anchor):
    ``rebate_share * max(0, benchmark - bid)`` per enrollee, risk-adjusted. The
    Phase-H demand side then makes ENROLLMENT respond to the change in that rebate
    vs baseline, with market competition amplifying how strongly patients respond
    (competitive markets are more elastic). The two concerns are kept separate --
    competition does NOT inflate the rebate level (the bug it replaced)."""
    rb = rebate or RebateModel()
    mm = market_model or MarketModel()
    ptm = patient_model or PatientModel()
    # Competition amplifies demand elasticity (competitive markets are more elastic).
    ptm_eff = PatientModel(
        demand_elasticity=ptm.demand_elasticity * max(0.0, mm.competition_index))
    base_levers = PolicyLevers.baseline()

    def _rebate_pc(lev: PolicyLevers, audit: Optional[float]) -> float:
        """Statutory rebate per enrollee, risk-adjusted (Phase-D accounting)."""
        er = engine.model.risk_score(m, lev, audit)
        bm = m.benchmark_per_capita
        if lev.benchmark_cap is not None:
            bm = min(bm, lev.benchmark_cap * m.ffs_per_capita)
        bid = rb.bid_to_ffs * m.ffs_per_capita
        return rb.rebate_share * max(0.0, bm - bid) * er

    total_rebate = 0.0
    total_enr = 0
    for m in engine.markets:
        au = audit_by_geo.get(m.geo) if audit_by_geo else None
        base_rebate_pc = _rebate_pc(base_levers, None)
        rebate_pc = _rebate_pc(levers, au)
        # Enrollment responds to the change in rebate generosity vs baseline.
        enr = ptm_eff.calculate_enrollment(
            m.enrollment, base_rebate_pc, rebate_pc, m.ffs_per_capita)
        total_rebate += rebate_pc * enr
        total_enr += enr

    enr = total_enr or 1
    premium = total_rebate * rb.premium_share
    return BeneficiaryOutcome(
        label=levers.label, rebate_total=total_rebate, enrollment=total_enr,
        rebate_per_enrollee=total_rebate / enr,
        premium_relief_total=premium, premium_relief_per_enrollee=premium / enr,
        supplemental_total=total_rebate - premium)


# ---------------------------------------------------------------------------
# The honest tradeoff table: federal saving AND beneficiary cost, side by side
# ---------------------------------------------------------------------------
def compare_tradeoff(engine: ScenarioEngine, scenarios: Sequence[PolicyLevers],
                     *, baseline: Optional[PolicyLevers] = None,
                     rebate: Optional[RebateModel] = None,
                     market_model: Optional[MarketModel] = None,
                     patient_model: Optional[PatientModel] = None) -> str:
    """For each scenario: federal overpayment Δ (taxpayer) vs rebate value Δ
    (beneficiary). The point is that the two move TOGETHER -- a cut is not free.
    """
    base = baseline or PolicyLevers.baseline()
    rb = rebate or RebateModel()
    
    # We use run_chain to get the proper feedback if patient/market models are provided
    from domains.flow.chain import run_chain
    base_res = run_chain(engine, base, market_model=market_model, patient_model=patient_model).result
    base_ben = beneficiary_outcome(engine, base, rb, market_model=market_model, patient_model=patient_model)

    rows = [("scenario", "overpayment", "fed chg", "rebate value",
             "benef chg", "benef/enr", "enrollment")]
    for lev in scenarios:
        res = run_chain(engine, lev, market_model=market_model, patient_model=patient_model).result
        ben = beneficiary_outcome(engine, lev, rb, market_model=market_model, patient_model=patient_model)
        
        d_fed = res.overpayment - base_res.overpayment       # <0 = taxpayer saves
        d_ben = ben.rebate_total - base_ben.rebate_total     # <0 = enrollees lose
        d_ben_pe = ben.rebate_per_enrollee - base_ben.rebate_per_enrollee
        is_base = lev.label == base.label
        
        enr_display = f"{ben.enrollment:,}"
        if not is_base and ben.enrollment != base_ben.enrollment:
            d_enr = ben.enrollment - base_ben.enrollment
            enr_display += f" ({d_enr:+,})"
            
        rows.append((
            lev.label,
            f"${res.overpayment/1e9:,.1f}B",
            "--" if is_base else f"{d_fed/1e9:+,.1f}B",
            f"${ben.rebate_total/1e9:,.1f}B",
            "--" if is_base else f"{d_ben/1e9:+,.1f}B",
            "--" if is_base else f"${d_ben_pe:+,.0f}",
            enr_display
        ))
    w = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    lines = ["Reform tradeoff -- taxpayer saving vs beneficiary cost "
             "(rebate proxy, not a forecast)", "=" * (sum(w) + len(w) * 2)]
    for i, row in enumerate(rows):
        lines.append("  " + "  ".join(c.ljust(w[j]) for j, c in enumerate(row)))
        if i == 0:
            lines.append("  " + "  ".join("-" * w[j] for j in range(len(w))))
    lines.append("-" * (sum(w) + len(w) * 2))
    lines.append(
        "  fed chg < 0 = taxpayer saves; benef chg < 0 = enrollees lose "
        "rebate-funded\n  benefits ($0 premiums, supplemental dental/vision, "
        "lower cost-sharing). The MA\n  rebate is risk-adjusted and "
        "benchmark-linked, so cutting coding/benchmarks cuts\n  beneficiary "
        "value too -- the engine shows both sides; it does not claim a free lunch.")
    return "\n".join(lines)


def summarize_baseline_rebate(engine: ScenarioEngine,
                              rebate: Optional[RebateModel] = None) -> str:
    """A sanity line: the baseline rebate proxy vs the real ~$60-70B MA total."""
    rb = rebate or RebateModel()
    ben = beneficiary_outcome(engine, PolicyLevers.baseline(), rb)
    return (f"baseline rebate proxy: ${ben.rebate_total/1e9:,.1f}B "
            f"(${ben.rebate_per_enrollee:,.0f}/enrollee) "
            f"[real MA rebates ~$60-70B / ~$2,000/enrollee, 2024 -- same order]")
