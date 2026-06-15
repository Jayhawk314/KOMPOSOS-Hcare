# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Phase C -- national levers propagated to states via a right Kan extension.

The problem Phase A left open
-----------------------------
In Phase A deterrence ``d = base_deter * audit_multiplier * penalty_multiplier``
is the SAME in every state. But a regulator does not set 51 audit rates; it sets
ONE national policy -- "double the RADV audit budget" -- which then has to be
*allocated* to states. Auditors are finite, so the allocation is constrained:
the per-state audit effort must aggregate back to the national budget. How you
spread a fixed budget changes the outcome, and uniform deterrence cannot express
that.

Why this is genuinely a right Kan extension (not decoration)
------------------------------------------------------------
Set up the two categories:

    C = (*)          the one-object "national" category (the apex)
    E = {states}     the discrete category of the 51 markets
    K: C -> E        embeds the nation as the cone over the states

A national quantity is a functor ``F`` on ``C``. Extending it to the states
"from above" is the **right Kan extension** ``Ran_K F``, whose value at the fine
level is the pointwise *limit* -- the terminal cone. Concretely, a per-state
allocation ``mult_s`` is a cone over the national budget exactly when it
**conserves** it:

    sum_s  E_s * mult_s  =  budget * sum_s E_s            (the cone condition)

That conservation law is the load-bearing categorical content: it is the
constraint that makes the extension canonical and ties the granular knobs back
to the one national knob. Among all cones satisfying it, the *targeting functor*
(how marginal audit dollars are valued) selects the universal one. The proof
this is not decorative: for the SAME national budget, a targeted cone yields
strictly LESS overpayment than the uniform cone -- a decision-relevant result
that the uniform Phase-A model structurally cannot produce (shown in the tests
and the demo).

We deliberately do NOT route this through the generic ``RightKanExtension`` in
``categorical/kan_extensions.py``: its numeric limit is a conservative *minimum*
(right for "what do all paths share"), whereas a budget limit is a *conserved
distribution*. Using it would be the decorative-wrapper mistake the project
already learned from with the sheaf. We build the cone explicitly instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from domains.flow.scenario import (
    Market, PolicyLevers, BehavioralModel, ScenarioEngine, ScenarioResult,
)

# Allocation policies (which cone the right Kan extension selects).
UNIFORM = "uniform"            # same multiplier everywhere (the trivial cone)
TARGETED = "targeted"          # the TERMINAL cone: overpayment-minimizing
EQUAL_PER_STATE = "equal_per_state"  # same absolute effort per state (naive)


@dataclass(frozen=True)
class NationalLever:
    """A lever a regulator actually sets: ONE national number + how it spreads.

    ``audit_budget`` is the national average audit multiplier (1.0 == today's
    calibrated baseline; 2.0 == "double the national audit budget"). ``policy``
    is the allocation cone. ``penalty_multiplier`` is a genuinely national knob
    (a statutory penalty applies everywhere) and is passed through unweighted.
    """

    audit_budget: float = 1.0
    policy: str = UNIFORM
    penalty_multiplier: float = 1.0
    coding_adjustment: Optional[float] = None   # None -> keep scenario default
    benchmark_cap: Optional[float] = None
    label: str = "national baseline"


def _state_overpayment(market: Market, audit_mult: float,
                       model: BehavioralModel, levers: PolicyLevers) -> float:
    """Overpayment in one state at a given per-state audit multiplier.

    Mirrors the 2-cell math in ``medicare_advantage.py`` so the allocator
    optimizes exactly the quantity the engine reports."""
    er = model.risk_score(market, levers, audit_mult)
    er_eff = er * (1.0 - levers.coding_adjustment)
    bm = market.benchmark_per_capita
    if levers.benchmark_cap is not None:
        bm = min(bm, levers.benchmark_cap * market.ffs_per_capita)
    E = float(market.enrollment)
    return E * bm * er_eff - E * market.ffs_per_capita * market.ffs_risk


def _waterfill(markets: Sequence[Market], total_effort: float,
               model: BehavioralModel, levers: PolicyLevers,
               steps: int = 4000) -> Dict[str, float]:
    """The terminal (overpayment-minimizing) cone via marginal-equalizing
    water-filling. Overpayment is convex-decreasing in each state's audit
    multiplier (deterrence has diminishing returns: p*=g/(g+d)), so the total is
    separable-convex and greedily handing each effort increment to the state with
    the largest marginal overpayment reduction reaches the global optimum -- and
    is necessarily <= the uniform cone (which is one feasible allocation)."""
    enr = {m.geo: float(m.enrollment) for m in markets}
    effort = {m.geo: 0.0 for m in markets}              # effort = E_s * mult_s
    inc = total_effort / steps
    # probe step in multiplier space, per state (effort increment / enrollment)
    for _ in range(steps):
        best_geo, best_gain = None, -1.0
        for m in markets:
            a = effort[m.geo] / max(enr[m.geo], 1.0)
            a2 = (effort[m.geo] + inc) / max(enr[m.geo], 1.0)
            gain = (_state_overpayment(m, a, model, levers)
                    - _state_overpayment(m, a2, model, levers))
            if gain > best_gain:
                best_geo, best_gain = m.geo, gain
        effort[best_geo] += inc
    return {g: effort[g] / max(enr[g], 1.0) for g in enr}


def allocate(national: NationalLever, markets: Sequence[Market],
             model: BehavioralModel,
             base_levers: Optional[PolicyLevers] = None) -> Dict[str, float]:
    """Right Kan extension: national audit budget -> per-state audit multipliers.

    Returns ``{geo: audit_multiplier}`` satisfying the cone (conservation) law
        sum_s E_s * mult_s = audit_budget * sum_s E_s
    exactly. UNIFORM returns ``audit_budget`` everywhere (the constant functor --
    a check the construction reduces correctly); TARGETED returns the terminal
    cone that minimizes overpayment for that budget; EQUAL_PER_STATE spends the
    same absolute effort in every state regardless of size (a naive contrast).
    """
    levers = base_levers or PolicyLevers.baseline()
    enr = {m.geo: float(m.enrollment) for m in markets}
    total_enr = sum(enr.values()) or 1.0
    budget = national.audit_budget * total_enr        # total audit effort to spend
    n = len(markets) or 1

    if national.policy == UNIFORM:
        return {g: national.audit_budget for g in enr}
    if national.policy == EQUAL_PER_STATE:
        per = budget / n                               # equal effort per state
        return {g: per / max(enr[g], 1.0) for g in enr}
    if national.policy == TARGETED:
        return _waterfill(markets, budget, model, levers)
    raise ValueError(f"unknown allocation policy: {national.policy!r}")


def to_levers(national: NationalLever,
              base: Optional[PolicyLevers] = None) -> PolicyLevers:
    """The non-audit parts of a national lever as a Phase-A :class:`PolicyLevers`
    (audit is applied per-state via :func:`allocate`)."""
    base = base or PolicyLevers.baseline()
    ca = national.coding_adjustment
    return PolicyLevers(
        coding_adjustment=base.coding_adjustment if ca is None else ca,
        audit_multiplier=1.0,                       # superseded by audit_by_geo
        penalty_multiplier=national.penalty_multiplier,
        benchmark_cap=national.benchmark_cap if national.benchmark_cap is not None
        else base.benchmark_cap,
        label=national.label,
    )


def run_national(engine: ScenarioEngine, national: NationalLever,
                 base: Optional[PolicyLevers] = None) -> ScenarioResult:
    """Run a scenario whose audit lever is a national budget allocated by cone."""
    levers = to_levers(national, base)
    audit_by_geo = allocate(national, engine.markets, engine.model, levers)
    return engine.run(levers, audit_by_geo=audit_by_geo)


# ---------------------------------------------------------------------------
# Allocation comparison: same budget, different cone -> different outcome
# ---------------------------------------------------------------------------
def compare_allocations(engine: ScenarioEngine, budget: float,
                        policies: Sequence[str] = (UNIFORM, TARGETED,
                                                   EQUAL_PER_STATE)) -> str:
    """Hold the national audit budget fixed; vary only the allocation cone.

    This is the Phase-C payoff: targeting the same auditor-hours at the states
    where coding leaks most buys overpayment reduction for free, which uniform
    deterrence cannot represent.
    """
    rows = [("allocation", "audit budget", "overpayment", "vs uniform",
             "mean risk")]
    results: Dict[str, ScenarioResult] = {}
    for pol in policies:
        nat = NationalLever(audit_budget=budget, policy=pol,
                            label=f"{pol} @ {budget:g}x budget")
        results[pol] = run_national(engine, nat)
    ref = results.get(UNIFORM)
    for pol in policies:
        r = results[pol]
        delta = (r.overpayment - ref.overpayment) if ref else 0.0
        rows.append((
            pol,
            f"{budget:g}x",
            f"${r.overpayment/1e9:,.1f}B",
            "--" if pol == UNIFORM else f"{delta/1e9:+,.1f}B",
            f"{r.mean_risk:.3f}",
        ))
    w = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    lines = [f"Right Kan propagation -- one national audit budget ({budget:g}x), "
             f"allocated 3 ways", "=" * 72]
    for i, row in enumerate(rows):
        lines.append("  " + "  ".join(c.ljust(w[j]) for j, c in enumerate(row)))
        if i == 0:
            lines.append("  " + "  ".join("-" * w[j] for j in range(len(w))))
    lines.append("-" * 72)
    lines.append("  every row spends the SAME total audit effort (the cone "
                 "conserves the budget);\n  only the allocation differs. "
                 "Targeting the leak is a free overpayment cut --\n  structure "
                 "the uniform Phase-A deterrence could not express.")
    return "\n".join(lines)
