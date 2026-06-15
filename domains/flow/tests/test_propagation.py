# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Phase C tests: national levers -> per-state deterrence via right Kan.

The two properties that make the extension real (not decorative):
  1. the cone CONSERVES the national budget exactly, and the UNIFORM policy
     reduces to the constant functor (every state gets the budget multiplier);
  2. for the SAME budget, targeting the leak yields strictly less overpayment
     than uniform -- a result the Phase-A uniform model cannot produce.
"""

import domains  # noqa: F401  (path bootstrap)

from domains.flow.medicare_advantage import MedicareAdvantageTwoCell, MAContract
from domains.flow.scenario import (
    BehavioralModel, ScenarioEngine, PolicyLevers, synthetic_markets,
)
from domains.flow.propagation import (
    NationalLever, allocate, run_national, compare_allocations,
    UNIFORM, TARGETED, EQUAL_PER_STATE,
)


def _engine():
    mkts = synthetic_markets()
    contracts = [MAContract(m.geo, m.enrollment, m.benchmark_per_capita,
                            m.ffs_per_capita, risk_score=1.20) for m in mkts]
    target = sum(r.overpayment
                 for r in MedicareAdvantageTwoCell().evaluate_all(contracts))
    model = BehavioralModel.calibrate(mkts, target_overpayment=target)
    return ScenarioEngine(mkts, model), mkts, model


# -- the cone (conservation) law --------------------------------------------
def test_uniform_policy_is_the_constant_functor():
    eng, mkts, model = _engine()
    alloc = allocate(NationalLever(audit_budget=2.0, policy=UNIFORM), mkts, model)
    assert all(abs(v - 2.0) < 1e-9 for v in alloc.values())


def test_allocation_conserves_the_budget():
    eng, mkts, model = _engine()
    total_enr = sum(m.enrollment for m in mkts)
    for policy in (UNIFORM, TARGETED, EQUAL_PER_STATE):
        for budget in (1.0, 2.0, 5.0):
            alloc = allocate(NationalLever(audit_budget=budget, policy=policy),
                             mkts, model)
            effort = sum(m.enrollment * alloc[m.geo] for m in mkts)
            assert abs(effort - budget * total_enr) / (budget * total_enr) < 1e-9


def test_targeted_is_differentiated_not_uniform():
    """The terminal cone spreads audit unevenly across states (it equalizes
    MARGINAL returns, not raw exposure -- so it does not simply pile onto the
    worst offender; that's the non-obvious part diminishing returns force)."""
    eng, mkts, model = _engine()
    alloc = allocate(NationalLever(audit_budget=1.0, policy=TARGETED), mkts, model)
    mults = list(alloc.values())
    assert max(mults) - min(mults) > 1e-3            # genuinely differentiated
    assert not all(abs(v - 1.0) < 1e-3 for v in mults)  # not the uniform cone


# -- the payoff: targeting beats uniform at equal budget --------------------
def test_targeting_beats_uniform_for_same_budget():
    eng, _, _ = _engine()
    uni = run_national(eng, NationalLever(audit_budget=2.0, policy=UNIFORM))
    tgt = run_national(eng, NationalLever(audit_budget=2.0, policy=TARGETED))
    assert tgt.overpayment < uni.overpayment


def test_uniform_national_matches_phase_a_uniform_audit():
    """A uniform national budget B must equal the Phase-A audit_multiplier=B run."""
    eng, _, _ = _engine()
    nat = run_national(eng, NationalLever(audit_budget=3.0, policy=UNIFORM))
    phase_a = eng.run(PolicyLevers(audit_multiplier=3.0))
    assert abs(nat.overpayment - phase_a.overpayment) / phase_a.overpayment < 1e-9


def test_more_budget_reduces_overpayment_under_targeting():
    eng, _, _ = _engine()
    overs = [run_national(eng, NationalLever(audit_budget=b, policy=TARGETED)).overpayment
             for b in (1.0, 2.0, 5.0)]
    assert all(overs[i] > overs[i + 1] for i in range(len(overs) - 1))


def test_compare_allocations_table_runs():
    eng, _, _ = _engine()
    text = compare_allocations(eng, budget=2.0)
    assert "Right Kan" in text
    assert "uniform" in text and "targeted" in text
    assert "conserves the budget" in text
