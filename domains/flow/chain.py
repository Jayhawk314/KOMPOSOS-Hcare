# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Phase E -- the CMS -> plan -> provider chain as a composed open game.

Phases A-D held the cost of care (the ``consumed`` / FFS-equivalent side) fixed
and let only the PLAN re-optimize (coding intensity). But CMS can also pull
PROVIDER-side levers, and providers re-optimize too. The classic one is
**site-neutral payment**: Medicare pays more for the same service in a hospital
outpatient department (HOPD) than in a physician office, so health systems shift
shiftable care into the higher-paid setting. Site-neutral payment equalizes the
rate, removing that incentive and lowering the cost basis.

The chain is a sequential (open) game, solved by backward induction
-----------------------------------------------------------------
    CMS (sets levers, incl. site_neutral)
        -> Provider best-responds: HOPD share phi*(site_neutral)  -> cost basis
            -> Plan best-responds: coding intensity p*(headroom)  -> overpayment
                -> CMS outcome: federal cost, rebate, the tradeoff

Open games compose exactly this way: forward ``play`` threads CMS -> provider ->
plan; backward ``coplay`` threads the payoff plan -> provider -> CMS. We solve it
by explicit backward induction (provider first, since it sets the basis the plan
then optimizes against) and ALSO mirror one market through the generic
``OpenGame`` composition as a structural check that the categorical composition
reproduces the hand-rolled induction (see ``chain_open_game`` and its test).

The non-obvious result the chain produces (and A-D could not)
------------------------------------------------------------
With benchmarks FIXED for the plan year (short run), site-neutral lowers the FFS
cost basis but not the benchmark, so headroom = benchmark/ffs - 1 *rises*, the
plan codes *harder*, and federal cost goes UP -- a provider-side "efficiency"
reform captured by plans, not taxpayers. Only when benchmarks are **re-based** on
the lower FFS (long run) does site-neutral actually save federal money. The
engine shows both regimes; the lesson -- site-neutral helps taxpayers only with
rebasing -- is a chain result, invisible to any single-actor model.

Honest data limit (like the Nash detector)
-------------------------------------------
The HOPD share and the site-of-service premium are not in the MA money graph
(they need claim-level place-of-service data). The provider layer is therefore a
MODELED response with exposed parameters, calibrated so the baseline
(``site_neutral=0``) reproduces the validated outcome exactly (identity). Only the
directional, relative effects of the provider lever are claimed.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import List, Optional, Sequence

from domains.flow.scenario import (
    Market, PolicyLevers, BehavioralModel, ScenarioEngine, ScenarioResult,
)


@dataclass(frozen=True)
class ProviderModel:
    """Exposed provider-behavior parameters (modeled -- no place-of-service data).

    Defaults reflect the MedPAC/CBO site-neutral literature: HOPD rates run
    ~10-15% above office for shiftable services, and a meaningful share of care
    is site-shiftable."""

    hopd_premium: float = 0.14       # HOPD cost over office for the same service
    shiftable: float = 0.30          # fraction of care that is site-shiftable
    hopd_share_base: float = 0.50    # baseline HOPD share of shiftable care


def provider_response(site_neutral: float, pm: ProviderModel) -> float:
    """Provider's best-response HOPD share of shiftable care, phi*(site_neutral).

    The provider captures the HOPD premium only on the share that site-neutral
    has NOT equalized, so the incentive -- and the realized HOPD share -- fall
    linearly as the rule tightens. phi*(0)=baseline, phi*(1)=0."""
    s = min(1.0, max(0.0, site_neutral))
    return pm.hopd_share_base * (1.0 - s)


def _effective_ffs(ffs_observed: float, site_neutral: float,
                   pm: ProviderModel) -> float:
    """FFS cost basis after the provider re-optimizes under the site-neutral rule.

    The observed FFS already embeds the baseline HOPD premium; we strip it to the
    pure-office basis, then re-apply the premium at the provider's new HOPD share.
    At site_neutral=0 this returns ffs_observed exactly (identity calibration)."""
    base_load = pm.shiftable * pm.hopd_premium * pm.hopd_share_base
    ffs_office = ffs_observed / (1.0 + base_load)
    load = pm.shiftable * pm.hopd_premium * provider_response(site_neutral, pm)
    return ffs_office * (1.0 + load)


@dataclass
class ChainResult:
    site_neutral: float
    rebase_benchmark: bool
    result: ScenarioResult
    hopd_share: float                # provider equilibrium phi*
    ffs_factor: float                # ffs_eff / ffs_observed (enrollment-weighted)


def run_chain(engine: ScenarioEngine, levers: PolicyLevers, *,
              site_neutral: float = 0.0, rebase_benchmark: bool = False,
              provider: Optional[ProviderModel] = None) -> ChainResult:
    """Backward-induction equilibrium of the CMS->provider->plan chain.

    ``rebase_benchmark=False`` (short run): benchmarks fixed for the year ->
    site-neutral raises headroom -> plan codes harder. ``True`` (long run):
    benchmarks re-based on the lower FFS -> headroom preserved -> federal saving.
    """
    pm = provider or ProviderModel()
    new_markets: List[Market] = []
    tot_e = sum(m.enrollment for m in engine.markets) or 1
    fsum = 0.0
    for m in engine.markets:
        ffs_eff = _effective_ffs(m.ffs_per_capita, site_neutral, pm)
        factor = ffs_eff / m.ffs_per_capita if m.ffs_per_capita else 1.0
        bm = m.benchmark_per_capita * factor if rebase_benchmark \
            else m.benchmark_per_capita
        new_markets.append(replace(m, ffs_per_capita=ffs_eff,
                                   benchmark_per_capita=bm))
        fsum += factor * m.enrollment
    # The plan re-optimizes on the new cost basis (its Phase-A best response).
    sub = ScenarioEngine(new_markets, engine.model)
    res = sub.run(levers)
    return ChainResult(site_neutral=site_neutral, rebase_benchmark=rebase_benchmark,
                       result=res, hopd_share=provider_response(site_neutral, pm),
                       ffs_factor=fsum / tot_e)


# ---------------------------------------------------------------------------
# Structural check: the generic OpenGame composition reproduces the induction
# ---------------------------------------------------------------------------
def chain_open_game(market: Market, levers: PolicyLevers, model: BehavioralModel,
                    site_neutral: float, pm: ProviderModel):
    """Build provider and plan stages as composed :class:`OpenGame`s for ONE
    market, returning that market's overpayment. Used to verify the categorical
    composition agrees with :func:`run_chain` (which is vectorized over markets).

    ``play`` threads CMS->provider->plan (forward); ``coplay`` threads the payoff
    back to CMS. Composition = backward induction, exactly the open-game story."""
    from game.open_games import OpenGame, OpenGameCategory

    def provider_play(sn: float) -> Market:
        ffs_eff = _effective_ffs(market.ffs_per_capita, sn, pm)
        return replace(market, ffs_per_capita=ffs_eff)

    def plan_play(m: Market) -> float:
        return model.risk_score(m, levers)                # plan's coding response

    def plan_coplay(m: Market, _r) -> float:
        er = model.risk_score(m, levers) * (1.0 - levers.coding_adjustment)
        E = float(m.enrollment)
        return E * m.benchmark_per_capita * er - E * m.ffs_per_capita * m.ffs_risk

    provider = OpenGame("provider", float, Market, Market, float,
                        play=provider_play, coplay=lambda sn, y: y)
    plan = OpenGame("plan", Market, float, float, float,
                    play=plan_play, coplay=plan_coplay)
    chain = OpenGameCategory().compose(provider, plan)    # plan o provider
    _, overpayment = chain.evaluate(site_neutral, None)
    return overpayment


# ---------------------------------------------------------------------------
# Comparison: the two regimes side by side (the policy lesson)
# ---------------------------------------------------------------------------
def compare_site_neutral(engine: ScenarioEngine,
                         levels: Sequence[float] = (0.0, 0.5, 1.0),
                         base: Optional[PolicyLevers] = None,
                         provider: Optional[ProviderModel] = None) -> str:
    base = base or PolicyLevers.baseline()
    rows = [("site-neutral", "regime", "overpayment", "federal paid",
             "mean risk", "HOPD share")]
    baseline_over = run_chain(engine, base, site_neutral=0.0,
                              provider=provider).result.overpayment
    for rebase in (False, True):
        regime = "rebased" if rebase else "fixed bm"
        for sn in levels:
            cr = run_chain(engine, base, site_neutral=sn,
                           rebase_benchmark=rebase, provider=provider)
            r = cr.result
            rows.append((
                f"{sn:.0%}", regime, f"${r.overpayment/1e9:,.1f}B",
                f"${r.paid/1e9:,.0f}B", f"{r.mean_risk:.3f}",
                f"{cr.hopd_share:.0%}"))
    w = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    lines = ["CMS -> provider -> plan chain -- site-neutral payment "
             "(model; provider layer not data-backed)", "=" * 78]
    for i, row in enumerate(rows):
        lines.append("  " + "  ".join(c.ljust(w[j]) for j, c in enumerate(row)))
        if i == 0:
            lines.append("  " + "  ".join("-" * w[j] for j in range(len(w))))
    lines.append("-" * 78)
    lines.append(
        "  FIXED benchmark (short run): site-neutral lowers the cost basis but "
        "not the\n  benchmark, so headroom and coding RISE -- federal cost goes "
        "UP (plans capture it).\n  REBASED benchmark (long run): the saving "
        "reaches the benchmark, so federal cost\n  falls. Site-neutral helps "
        "taxpayers only with rebasing -- a chain result.")
    return "\n".join(lines)
