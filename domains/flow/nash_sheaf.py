# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Nash sheaf -- cross-market strategic-gaming detection (game theory (x) sheaf).

The novel detector. Every other flow tool looks at one entity at a time; this
one finds gaming that is *invisible in any single market* and only shows up as
an inconsistency across markets.

Construction
------------
A plan operates in many markets (counties). In each market it chooses a coding
strategy. Local incentives (benchmark headroom, audit pressure) make the
*locally rational* strategy differ market to market -- this is the **inspection
game** between the plan (comply / upcode) and CMS (audit / trust), whose mixed
equilibrium gives a continuous local aggressiveness in [0, 1]:

    indifference conditions (2x2 inspection game, Tsebelis/standard):
        audit rate that deters:   q* = g / f          (gain g, penalty f)
        equilibrium upcoding:     p* = c / (b + L)     (audit cost c, detect
                                                        benefit b, social loss L)

A plan's strategy across its markets is a **section of a sheaf** over the
market-overlap graph. The gluing condition: an honest plan plays ONE coherent
policy, so its strategy section is (near) constant -- a global section exists,
H^1 = 0. A plan that games plays the local best response everywhere; those
local strategies **cannot glue** into one policy -> H^1 != 0.

We reuse pronoia's scalar cellular ``Sheaf`` (signed Laplacian L; for same-plan
overlap edges sign = +1, so the coboundary energy is

    H1_energy = x^T L x = sum_e w_e (x_v - x_u)^2

which is zero for a constant section and grows with cross-market variance. The
sheaf Laplacian also *localizes* which markets break the policy.

Strategic vs noisy
------------------
High variance alone is not gaming -- it could be noise. The Nash sheaf flags a
plan only when its cross-market variance is **aligned with local incentives**
(observed strategy correlates with the local Nash aggressiveness): it games
*where it pays to*. That alignment is what separates strategic upcoding from
random measurement noise, and it is the reason this detector needs both the
game and the sheaf.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from pronoia.sheaf_probe import Sheaf
from game.nash import TwoPlayerGame

MAX_UPCODE = 0.30  # max coding-intensity premium an all-out gamer adds (+30%)


# ---------------------------------------------------------------------------
# Local inspection game -> continuous Nash aggressiveness
# ---------------------------------------------------------------------------
def local_nash_intensity(benchmark_headroom: float, audit_pressure: float,
                         penalty: float = 1.0) -> float:
    """Local equilibrium coding intensity (>= 1.0) for one market.

    Reduced form of the inspection-game equilibrium: upcoding propensity rises
    with the gain from headroom and falls with expected punishment
    (audit_pressure x penalty). Returns 1.0 (honest) .. 1+MAX_UPCODE.
    """
    g = max(0.0, benchmark_headroom)
    deter = max(0.0, audit_pressure) * max(0.0, penalty)
    p_star = g / (g + deter + 1e-9)        # equilibrium upcoding propensity [0,1)
    return 1.0 + MAX_UPCODE * p_star


def inspection_game(benchmark_headroom: float, audit_pressure: float,
                    penalty: float = 1.0) -> TwoPlayerGame:
    """The discrete 2x2 inspection game (for display / pure-Nash inspection).

    Note: like all inspection games this typically has only a MIXED equilibrium
    (``find_pure_nash()`` returns []); the continuous strategy comes from
    ``local_nash_intensity``.
    """
    g, f = max(0.0, benchmark_headroom), max(1e-9, penalty)
    p1 = {  # plan payoff
        ("upcode", "trust"): g,
        ("upcode", "audit"): g - f,
        ("comply", "trust"): 0.0,
        ("comply", "audit"): 0.0,
    }
    c = max(0.0, audit_pressure)
    p2 = {  # CMS payoff
        ("upcode", "trust"): -g,
        ("upcode", "audit"): f - c,
        ("comply", "trust"): 0.0,
        ("comply", "audit"): -c,
    }
    return TwoPlayerGame("inspection", ["comply", "upcode"],
                         ["trust", "audit"], p1, p2)


# ---------------------------------------------------------------------------
# Inputs / outputs
# ---------------------------------------------------------------------------
@dataclass
class MarketObs:
    """A plan's behavior + incentives in one market."""

    plan_id: str
    market_id: str
    observed_intensity: float       # observed coding intensity / risk score
    enrollment: int                 # population weight in this market
    benchmark_headroom: float = 0.1  # local gain incentive (benchmark over FFS)
    audit_pressure: float = 0.2      # local deterrent in [0,1]


@dataclass
class PlanGamingResult:
    plan_id: str
    markets: int
    enrollment: int
    mean_intensity: float
    h1_energy: float                 # sheaf coboundary energy x^T L x
    gaming_score: float              # [0,1] cross-market inconsistency
    incentive_alignment: float       # corr(observed, local Nash) in [-1,1]
    strategic: bool                  # gaming_score high AND aligned with incentives
    worst_markets: List[Tuple[str, float]] = field(default_factory=list)


class NashSheaf:
    """Detect strategic cross-market gaming via the Nash sheaf's H^1."""

    def __init__(self, gaming_threshold: float = 0.10,
                 alignment_threshold: float = 0.3, category=None) -> None:
        self.gaming_threshold = gaming_threshold
        self.alignment_threshold = alignment_threshold
        self.category = category

    def analyze(self, observations: List[MarketObs]) -> List[PlanGamingResult]:
        by_plan: Dict[str, List[MarketObs]] = {}
        for o in observations:
            by_plan.setdefault(o.plan_id, []).append(o)
        results = [self.analyze_plan(obs) for obs in by_plan.values()]
        results.sort(key=lambda r: (-int(r.strategic), -r.gaming_score))
        return results

    def analyze_plan(self, obs: List[MarketObs]) -> PlanGamingResult:
        plan = obs[0].plan_id
        x = np.array([o.observed_intensity for o in obs], dtype=float)
        w = np.array([max(1.0, o.enrollment) for o in obs], dtype=float)
        nash = np.array([local_nash_intensity(o.benchmark_headroom, o.audit_pressure)
                         for o in obs], dtype=float)
        n = len(obs)
        wmean = float(np.average(x, weights=w))

        # --- build the Nash sheaf over the plan's markets -----------------
        sheaf = Sheaf()
        for o in obs:
            sheaf.add_node(o.market_id)
        # same-plan overlap edges: a coherent single policy => strategies agree.
        for i in range(n):
            for j in range(i + 1, n):
                weight = float(np.sqrt(w[i] * w[j]))
                sheaf.add_edge(obs[i].market_id, obs[j].market_id, sign=1, weight=weight)

        h1_energy = 0.0
        worst: List[Tuple[str, float]] = []
        if n >= 2:
            L = sheaf.laplacian()
            h1_energy = float(x @ L @ x)            # = sum_e w (x_v - x_u)^2
            contrib = x * (L @ x)                   # per-market coboundary load
            order = np.argsort(-np.abs(contrib))
            worst = [(obs[k].market_id, float(contrib[k])) for k in order[:5]]

        total_w = float(w.sum())
        # dimensionless inconsistency ~ weighted coefficient of variation.
        rms_dev = float(np.sqrt(max(0.0, h1_energy) / max(total_w, 1.0)))
        gaming_score = min(1.0, rms_dev / max(wmean, 1e-9))

        alignment = _weighted_corr(x, nash, w)
        strategic = (gaming_score >= self.gaming_threshold
                     and alignment >= self.alignment_threshold)

        result = PlanGamingResult(
            plan_id=plan, markets=n, enrollment=int(w.sum()),
            mean_intensity=wmean, h1_energy=h1_energy, gaming_score=gaming_score,
            incentive_alignment=alignment, strategic=strategic, worst_markets=worst,
        )
        if self.category is not None:
            self._write_back(result, obs)
        return result

    def _write_back(self, r: PlanGamingResult, obs: List[MarketObs]) -> None:
        cat = self.category
        plan = f"plan:{r.plan_id}"
        cat.add(plan, type_name="ma_contract")
        for o in obs:
            mk = f"market:{o.market_id}"
            cat.add(mk, type_name="market")
            cat.connect(plan, mk, name="plays_in",
                        confidence=round(min(1.0, o.observed_intensity / 2.0), 4),
                        intensity=round(o.observed_intensity, 4))
        if r.strategic:
            cat.add("medicare", type_name="program")
            cat.connect(plan, "medicare", name="strategic_gaming",
                        confidence=round(r.gaming_score, 4),
                        h1_energy=round(r.h1_energy, 2),
                        alignment=round(r.incentive_alignment, 3),
                        worst=",".join(m for m, _ in r.worst_markets[:3]))


def _weighted_corr(x: np.ndarray, y: np.ndarray, w: np.ndarray) -> float:
    mx = np.average(x, weights=w)
    my = np.average(y, weights=w)
    cov = np.average((x - mx) * (y - my), weights=w)
    vx = np.average((x - mx) ** 2, weights=w)
    vy = np.average((y - my) ** 2, weights=w)
    denom = np.sqrt(vx * vy)
    return float(cov / denom) if denom > 1e-12 else 0.0


def summarize(results: List[PlanGamingResult], top: int = 15) -> str:
    lines = ["Nash sheaf -- cross-market strategic-gaming report", "=" * 72]
    strategic = [r for r in results if r.strategic]
    for r in results[:top]:
        tag = "GAMING" if r.strategic else ("noisy " if r.gaming_score >= 0.1 else "ok    ")
        worst = (" worst=" + ",".join(m for m, _ in r.worst_markets[:2])) if r.strategic else ""
        lines.append(
            f"  [{tag}] {r.plan_id:<16} markets={r.markets:>3} "
            f"enr={r.enrollment:>8,}  H1={r.h1_energy:>12,.0f}"
            f"  score={r.gaming_score:.2f}  align={r.incentive_alignment:+.2f}{worst}"
        )
    lines.append("-" * 72)
    lines.append(f"  strategic gamers: {len(strategic)}/{len(results)} "
                 f"(high cross-market H^1 AND incentive-aligned)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Synthetic demo: honest vs strategic gamer vs noisy plan
# ---------------------------------------------------------------------------
def synthetic_observations() -> List[MarketObs]:
    """Three plans across the same 5 markets with varying headroom/audit.

    Market incentives (headroom, audit): m1 low/high .. m5 high/low.
    - HonestHealth : flat ~1.05 everywhere (a single policy)        -> H^1 ~ 0
    - GamerMax     : tracks local Nash (aggressive where it pays)   -> strategic
    - NoisyPlan    : high variance but uncorrelated with incentives -> noisy only
    """
    markets = [
        ("m1", 0.02, 0.9), ("m2", 0.06, 0.7), ("m3", 0.10, 0.5),
        ("m4", 0.16, 0.3), ("m5", 0.24, 0.1),
    ]
    obs: List[MarketObs] = []
    for mk, head, audit in markets:
        obs.append(MarketObs("HonestHealth", mk, 1.05, 50_000, head, audit))
        nash = local_nash_intensity(head, audit)
        obs.append(MarketObs("GamerMax", mk, round(nash, 3), 60_000, head, audit))
    # NoisyPlan: same markets, intensities shuffled vs incentives.
    noisy = [1.22, 1.03, 1.27, 1.04, 1.20]
    for (mk, head, audit), inten in zip(markets, noisy):
        obs.append(MarketObs("NoisyPlan", mk, inten, 40_000, head, audit))
    return obs
