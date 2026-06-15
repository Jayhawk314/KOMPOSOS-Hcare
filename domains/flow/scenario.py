# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Policy-scenario engine -- coding intensity as the Nash best response.

This is the pivot from FORENSIC (find what the money did, behavior fixed) to
PREDICTIVE (what would the money do under different rules, behavior endogenous).
See ``SCENARIO_PLAN.md`` for the full design; this module is Phase A.

The single conceptual shift
---------------------------
In the forensic 2-cell (``medicare_advantage.py``) the MA risk score is a fixed
constant (MedPAC's ~1.20). Here it stops being a constant and becomes the
**equilibrium of an inspection game** between the plan and CMS, given the policy
levers. A plan in a market with a rich benchmark (large headroom) and weak audit
pressure best-responds by coding more aggressively; tighten the audit, reinstate
the RADV penalty, or cap the benchmark and the same plan re-optimizes downward.
Arithmetic cannot produce that response; a game can -- which is the whole point.

The behavioral model (generalizes ``nash_sheaf.local_nash_intensity``)
----------------------------------------------------------------------
Per market *m* with real benchmark headroom ``h_m = benchmark/ffs - 1``:

    gain slope     g_m = elasticity * h_m * (1 - coding_adjustment)
    deterrence     d   = base_deter * audit_multiplier * penalty_multiplier
    upcoding       p*_m = g_m / (g_m + d)              in [0, 1)
    risk score     er_m = 1 + kappa * p*_m            in [1, 1+kappa]

Every lever moves ``p*`` in the documented direction:
  * coding_adjustment up   -> g down            -> less upcoding (and haircut up)
  * audit / penalty up     -> d up              -> less upcoding
  * benchmark cap          -> h down            -> less upcoding AND less spread
  * richer benchmark       -> h up              -> more upcoding

The HONEST part: the *magnitude* of the response rides on ``elasticity`` and
``kappa`` (behavioral assumptions). They are not free knobs we tuned to a story
-- ``base_deter`` is **calibrated** so the status-quo levers reproduce the
validated forensic overpayment (~$107B / mean risk ~1.20). Only after that gate
passes are the relative, directional scenario effects credible. This is the
CBO/MedPAC class of object: a transparent model calibrated at baseline, not a
forecast of truth.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Sequence

from domains.flow.medicare_advantage import (
    MAContract, MedicareAdvantageTwoCell, OverpaymentResult,
    DEFAULT_CODING_ADJUSTMENT,
)

# Max coding-intensity premium an all-out gamer adds (risk ceiling 1 + KAPPA).
# MedPAC documents gross coding raising MA risk ~16-20%; 0.30 leaves headroom
# for the calibrated baseline mean to land near the documented ~1.20.
DEFAULT_KAPPA = 0.30


# ---------------------------------------------------------------------------
# The "foundations" a regulator sets
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PolicyLevers:
    """The rules CMS / Congress can change. Baseline == today's status quo.

    Audit and penalty are expressed as MULTIPLIERS on the calibrated baseline
    deterrence (baseline == 1.0), because the absolute audit/penalty level is
    folded into the calibration anchor -- what a scenario changes is the
    *relative* enforcement intensity, which is what published sensitivities are
    stated in.
    """

    coding_adjustment: float = DEFAULT_CODING_ADJUSTMENT  # statutory haircut
    audit_multiplier: float = 1.0        # RADV audit rate vs baseline
    penalty_multiplier: float = 1.0      # RADV penalty / extrapolation vs baseline
    benchmark_cap: Optional[float] = None  # cap benchmark at this x FFS (None=off)
    label: str = "baseline"

    @classmethod
    def baseline(cls) -> "PolicyLevers":
        return cls()

    def deterrence_factor(self) -> float:
        return max(0.0, self.audit_multiplier) * max(0.0, self.penalty_multiplier)


# ---------------------------------------------------------------------------
# A market the plan operates in (real FFS + benchmark inputs)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Market:
    """One geography's real money inputs for the scenario game."""

    geo: str
    enrollment: int
    ffs_per_capita: float
    benchmark_per_capita: float
    ffs_risk: float = 1.0

    @property
    def headroom(self) -> float:
        """Benchmark over local FFS -- the real per-market gain incentive."""
        if self.ffs_per_capita <= 0:
            return 0.0
        return max(0.0, self.benchmark_per_capita / self.ffs_per_capita - 1.0)


def markets_from_contracts(contracts: Sequence[MAContract]) -> List[Market]:
    """Adapt the existing real-data :class:`MAContract`s into scenario markets."""
    return [
        Market(geo=c.contract_id, enrollment=c.enrollment,
               ffs_per_capita=c.ffs_per_capita,
               benchmark_per_capita=c.benchmark_per_capita, ffs_risk=c.ffs_risk)
        for c in contracts
    ]


# ---------------------------------------------------------------------------
# The behavioral model: endogenous coding intensity
# ---------------------------------------------------------------------------
from domains.flow.market import MarketModel, PatientModel

@dataclass(frozen=True)
class BehavioralModel:
    """Calibrated inspection-game response. ``base_deter`` is the anchor set by
    :meth:`calibrate`; ``elasticity`` and ``kappa`` are exposed assumptions."""

    base_deter: float
    elasticity: float = 1.0
    kappa: float = DEFAULT_KAPPA

    def upcoding(self, market: Market, levers: PolicyLevers,
                 audit_override: Optional[float] = None,
                 patient_model: Optional[PatientModel] = None,
                 market_model: Optional[MarketModel] = None,
                 base_rebate_pc: float = 0.0,
                 ffs_cost: float = 0.0) -> float:
        """Equilibrium upcoding propensity p* in [0, 1) for this market+levers.

        ``audit_override`` replaces the uniform national ``audit_multiplier`` with
        a per-market value -- this is the hook the Phase C Kan propagation uses to
        push a national audit budget down to state-specific deterrence.
        
        If patient_model and market_model are provided, solves the Nash equilibrium
        considering the volume boost from rebate-induced enrollment.
        """
        h = self._effective_headroom(market, levers)
        g = self.elasticity * h * (1.0 - levers.coding_adjustment)
        audit = levers.audit_multiplier if audit_override is None else audit_override
        d = self.base_deter * max(0.0, audit) * max(0.0, levers.penalty_multiplier)
        
        if patient_model is None or market_model is None or patient_model.demand_elasticity <= 0.0:
            # Phase A linear baseline
            return g / (g + d + 1e-12)
            
        # Phase H Bidirectional Nash Solver
        # The plan optimizes total margin: Margin = M_per_capita * Enrollment
        # Where Enrollment is a function of Rebate, and Rebate is a function of Margin.
        # This requires an iterative best-response to find the stable p*.
        
        # Helper to compute rebate given a p*
        def _rebate(p_star: float) -> float:
            er = 1.0 + self.kappa * p_star
            bm = market.benchmark_per_capita
            if levers.benchmark_cap is not None:
                bm = min(bm, levers.benchmark_cap * market.ffs_per_capita)
            # Proxy bid to calculate margin (Phase D defaults)
            bid = 0.83 * market.ffs_per_capita
            margin_pc = max(0.0, bm * er - bid)
            return market_model.effective_pass_through * margin_pc

        p_current = g / (g + d + 1e-12) # Start at linear baseline
        for _ in range(50): # Iterative best response
            r_current = _rebate(p_current)
            enr_mult = 1.0 + patient_model.demand_elasticity * ((r_current - base_rebate_pc) / max(1e-9, ffs_cost))
            
            # The marginal value of coding increases if enrollment is elastic
            # We approximate the new marginal gain
            g_elastic = g * max(0.1, enr_mult)
            p_next = g_elastic / (g_elastic + d + 1e-12)
            
            if abs(p_next - p_current) < 1e-5:
                return p_next
            p_current = p_next
            
        return p_current

    def risk_score(self, market: Market, levers: PolicyLevers,
                   audit_override: Optional[float] = None,
                   patient_model: Optional[PatientModel] = None,
                   market_model: Optional[MarketModel] = None,
                   base_rebate_pc: float = 0.0,
                   ffs_cost: float = 0.0) -> float:
        """Endogenous MA risk score er = 1 + kappa * p* (the former fixed 1.20)."""
        return 1.0 + self.kappa * self.upcoding(
            market, levers, audit_override, patient_model, market_model, base_rebate_pc, ffs_cost)

    def _effective_headroom(self, market: Market, levers: PolicyLevers) -> float:
        h = market.headroom
        if levers.benchmark_cap is not None:
            capped_bm = min(market.benchmark_per_capita,
                            levers.benchmark_cap * market.ffs_per_capita)
            h = max(0.0, capped_bm / market.ffs_per_capita - 1.0)
        return h

    # -- calibration: pin the baseline to the validated forensic number ----
    @classmethod
    def calibrate(cls, markets: Sequence[Market], *,
                  target_overpayment: float,
                  baseline: Optional[PolicyLevers] = None,
                  elasticity: float = 1.0, kappa: float = DEFAULT_KAPPA,
                  coding_adjustment: Optional[float] = None) -> "BehavioralModel":
        """Solve ``base_deter`` so baseline-lever overpayment == target.

        ``target_overpayment`` is the validated forensic total (the same real
        pipeline run with the fixed MedPAC risk score). Overpayment is monotone
        decreasing in ``base_deter`` (more deterrence -> less coding -> less
        overpayment), so a bisection converges. This IS the validation gate: if
        no ``base_deter`` reproduces the number the model is wrong before any
        scenario runs.
        """
        base = baseline or PolicyLevers.baseline()
        if coding_adjustment is not None:
            base = replace(base, coding_adjustment=coding_adjustment)

        def total(bd: float) -> float:
            model = cls(base_deter=bd, elasticity=elasticity, kappa=kappa)
            return ScenarioEngine(markets, model).run(base).overpayment

        lo, hi = 1e-9, 1e6
        # Expand hi until overpayment(hi) <= target (deterrence kills coding).
        for _ in range(200):
            if total(hi) <= target_overpayment:
                break
            hi *= 2.0
        for _ in range(200):
            mid = (lo * hi) ** 0.5 if lo > 0 else hi / 2.0  # geometric bisection
            if total(mid) > target_overpayment:
                lo = mid
            else:
                hi = mid
            if hi / max(lo, 1e-30) < 1.0 + 1e-9:
                break
        return cls(base_deter=(lo * hi) ** 0.5, elasticity=elasticity, kappa=kappa)


# ---------------------------------------------------------------------------
# Running a scenario: endogenous risk -> reuse the real-data 2-cell math
# ---------------------------------------------------------------------------
@dataclass
class ScenarioResult:
    label: str
    levers: PolicyLevers
    paid: float
    consumed: float
    overpayment: float
    mean_risk: float                 # enrollment-weighted equilibrium coding
    per_geo: List[OverpaymentResult]

    @property
    def enrollment(self) -> int:
        return sum(r.enrollment for r in self.per_geo)

    @property
    def per_enrollee(self) -> float:
        e = self.enrollment
        return self.overpayment / e if e else 0.0

    @property
    def pct_above_ffs(self) -> float:
        return (self.paid / self.consumed - 1.0) if self.consumed else 0.0


class ScenarioEngine:
    """Compute the equilibrium outcome of a lever setting on real markets."""

    def __init__(self, markets: Sequence[Market], model: BehavioralModel) -> None:
        self.markets = list(markets)
        self.model = model

    def run(self, levers: PolicyLevers,
            audit_by_geo: Optional[Dict[str, float]] = None) -> ScenarioResult:
        """Equilibrium outcome under ``levers``.

        ``audit_by_geo`` (from :mod:`domains.flow.propagation`) supplies a
        per-state audit multiplier -- a national audit budget allocated down to
        states. When ``None`` the uniform national ``audit_multiplier`` is used.
        """
        contracts: List[MAContract] = []
        for m in self.markets:
            au = audit_by_geo.get(m.geo) if audit_by_geo else None
            er = self.model.risk_score(m, levers, au)        # ENDOGENOUS now
            bm = m.benchmark_per_capita
            if levers.benchmark_cap is not None:
                bm = min(bm, levers.benchmark_cap * m.ffs_per_capita)
            contracts.append(MAContract(
                contract_id=m.geo, enrollment=m.enrollment,
                benchmark_per_capita=bm, ffs_per_capita=m.ffs_per_capita,
                risk_score=er, ffs_risk=m.ffs_risk, name=m.geo))
        # Reuse the validated 2-cell math; coding_adjustment is now a lever.
        engine = MedicareAdvantageTwoCell(coding_adjustment=levers.coding_adjustment)
        results = engine.evaluate_all(contracts)

        paid = sum(r.paid for r in results)
        consumed = sum(r.consumed for r in results)
        over = sum(r.overpayment for r in results)
        enr = sum(m.enrollment for m in self.markets) or 1
        mean_risk = sum(
            self.model.risk_score(m, levers,
                                  audit_by_geo.get(m.geo) if audit_by_geo else None)
            * m.enrollment for m in self.markets) / enr
        return ScenarioResult(
            label=levers.label, levers=levers, paid=paid, consumed=consumed,
            overpayment=over, mean_risk=mean_risk, per_geo=results)


# ---------------------------------------------------------------------------
# Comparison (Phase B preview -- the side-by-side the engine exists to produce)
# ---------------------------------------------------------------------------
def compare(engine: ScenarioEngine, scenarios: Sequence[PolicyLevers],
            *, baseline: Optional[PolicyLevers] = None) -> str:
    base = baseline or PolicyLevers.baseline()
    base_res = engine.run(base)
    rows = [("scenario", "overpayment", "vs base", "per enrollee", "mean risk")]
    out: List[ScenarioResult] = []
    for lev in scenarios:
        r = engine.run(lev)
        out.append(r)
        delta = r.overpayment - base_res.overpayment
        rows.append((
            lev.label,
            f"${r.overpayment/1e9:,.1f}B",
            f"{delta/1e9:+,.1f}B" if lev.label != base.label else "--",
            f"${r.per_enrollee:,.0f}",
            f"{r.mean_risk:.3f}",
        ))
    w = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    lines = ["Policy-scenario comparison -- MA overpayment (model, not forecast)",
             "=" * 72]
    for i, row in enumerate(rows):
        lines.append("  " + "  ".join(c.ljust(w[j]) for j, c in enumerate(row)))
        if i == 0:
            lines.append("  " + "  ".join("-" * w[j] for j in range(len(w))))
    lines.append("-" * 72)
    lines.append("  baseline calibrated to the validated forensic overpayment; "
                 "deltas are\n  the equilibrium response of coding intensity to "
                 "each rule change.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Synthetic markets + a v1 scenario set (for tests / the demo)
# ---------------------------------------------------------------------------
def synthetic_markets() -> List[Market]:
    """Markets spanning lean to rich benchmarks (the real headroom spread)."""
    return [
        Market("lean",   500_000, ffs_per_capita=10_000, benchmark_per_capita=10_300),
        Market("mid",  1_200_000, ffs_per_capita=11_000, benchmark_per_capita=11_900),
        Market("rich",   900_000, ffs_per_capita=12_000, benchmark_per_capita=13_600),
        Market("max",    400_000, ffs_per_capita=13_000, benchmark_per_capita=15_300),
    ]


def v1_scenarios() -> List[PolicyLevers]:
    """The plan's v1 lever set as labeled scenarios."""
    return [
        PolicyLevers.baseline(),
        PolicyLevers(coding_adjustment=0.10, label="coding adj 10%"),
        PolicyLevers(coding_adjustment=0.20, label="coding adj 20%"),
        PolicyLevers(audit_multiplier=2.0, label="audit 2x"),
        PolicyLevers(audit_multiplier=5.0, label="audit 5x"),
        PolicyLevers(penalty_multiplier=3.0, label="RADV penalty reinstated x3"),
        PolicyLevers(benchmark_cap=1.0, label="benchmark cap @100% FFS"),
        PolicyLevers(audit_multiplier=5.0, penalty_multiplier=3.0,
                     coding_adjustment=0.20, label="combined reform"),
    ]
