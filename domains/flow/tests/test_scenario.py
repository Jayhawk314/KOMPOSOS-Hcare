# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Phase A tests: the policy-scenario engine (endogenous coding intensity).

The non-negotiable gate (SCENARIO_PLAN.md s7): baseline levers must reproduce
the validated forensic overpayment. The rest assert each lever moves the
equilibrium in the documented direction.
"""

import domains  # noqa: F401  (path bootstrap)

from domains.flow.medicare_advantage import MedicareAdvantageTwoCell
from domains.flow.scenario import (
    PolicyLevers, Market, BehavioralModel, ScenarioEngine, compare,
    markets_from_contracts, synthetic_markets, v1_scenarios, DEFAULT_KAPPA,
)


def _forensic_target(markets, risk=1.20):
    """Same 2-cell math the forensic pipeline runs, with the fixed MedPAC risk."""
    from domains.flow.medicare_advantage import MAContract
    contracts = [MAContract(m.geo, m.enrollment, m.benchmark_per_capita,
                            m.ffs_per_capita, risk_score=risk, ffs_risk=m.ffs_risk)
                 for m in markets]
    res = MedicareAdvantageTwoCell().evaluate_all(contracts)
    return sum(r.overpayment for r in res)


def _calibrated(markets):
    target = _forensic_target(markets)
    return target, BehavioralModel.calibrate(markets, target_overpayment=target)


# -- the validation gate ----------------------------------------------------
def test_baseline_reproduces_forensic_number():
    mkts = synthetic_markets()
    target, model = _calibrated(mkts)
    base = ScenarioEngine(mkts, model).run(PolicyLevers.baseline())
    assert abs(base.overpayment - target) / target < 1e-3   # the gate


def test_baseline_mean_risk_near_medpac():
    """Calibrating to the dollar gate should land mean coding intensity ~1.20."""
    mkts = synthetic_markets()
    _, model = _calibrated(mkts)
    base = ScenarioEngine(mkts, model).run(PolicyLevers.baseline())
    assert 1.15 <= base.mean_risk <= 1.25


# -- structural properties of the best response -----------------------------
def test_risk_score_within_bounds():
    mkts = synthetic_markets()
    _, model = _calibrated(mkts)
    for m in mkts:
        er = model.risk_score(m, PolicyLevers.baseline())
        assert 1.0 <= er <= 1.0 + DEFAULT_KAPPA + 1e-9


def test_more_headroom_means_more_upcoding():
    """A plan codes harder where the benchmark is richer -- the core mechanism."""
    _, model = _calibrated(synthetic_markets())
    lev = PolicyLevers.baseline()
    lean = Market("lean", 1, ffs_per_capita=10_000, benchmark_per_capita=10_200)
    rich = Market("rich", 1, ffs_per_capita=10_000, benchmark_per_capita=13_000)
    assert model.upcoding(rich, lev) > model.upcoding(lean, lev)


# -- directional lever responses (the whole point) --------------------------
def test_audit_reduces_overpayment_and_coding():
    mkts = synthetic_markets()
    _, model = _calibrated(mkts)
    eng = ScenarioEngine(mkts, model)
    base = eng.run(PolicyLevers.baseline())
    audited = eng.run(PolicyLevers(audit_multiplier=5.0, label="audit"))
    assert audited.overpayment < base.overpayment
    assert audited.mean_risk < base.mean_risk


def test_penalty_reduces_overpayment():
    mkts = synthetic_markets()
    _, model = _calibrated(mkts)
    eng = ScenarioEngine(mkts, model)
    base = eng.run(PolicyLevers.baseline())
    pen = eng.run(PolicyLevers(penalty_multiplier=4.0))
    assert pen.overpayment < base.overpayment


def test_higher_coding_adjustment_reduces_overpayment():
    mkts = synthetic_markets()
    _, model = _calibrated(mkts)
    eng = ScenarioEngine(mkts, model)
    base = eng.run(PolicyLevers.baseline())
    cut = eng.run(PolicyLevers(coding_adjustment=0.20))
    assert cut.overpayment < base.overpayment


def test_benchmark_cap_reduces_headroom_and_overpayment():
    mkts = synthetic_markets()
    _, model = _calibrated(mkts)
    eng = ScenarioEngine(mkts, model)
    base = eng.run(PolicyLevers.baseline())
    capped = eng.run(PolicyLevers(benchmark_cap=1.0))
    assert capped.overpayment < base.overpayment
    # at a 100% FFS cap there is no headroom, so coding incentive vanishes.
    assert capped.mean_risk < base.mean_risk
    assert abs(capped.mean_risk - 1.0) < 1e-6


def test_monotone_in_audit_multiplier():
    mkts = synthetic_markets()
    _, model = _calibrated(mkts)
    eng = ScenarioEngine(mkts, model)
    overs = [eng.run(PolicyLevers(audit_multiplier=a)).overpayment
             for a in (1.0, 2.0, 5.0, 10.0)]
    assert all(overs[i] > overs[i + 1] for i in range(len(overs) - 1))


# -- plumbing ---------------------------------------------------------------
def test_markets_from_contracts_roundtrip():
    from domains.flow.medicare_advantage import synthetic_contracts
    mkts = markets_from_contracts(synthetic_contracts())
    assert len(mkts) == len(synthetic_contracts())
    assert all(m.headroom >= 0.0 for m in mkts)


def test_compare_table_runs():
    mkts = synthetic_markets()
    _, model = _calibrated(mkts)
    text = compare(ScenarioEngine(mkts, model), v1_scenarios())
    assert "scenario" in text
    assert "baseline" in text
    assert "model, not forecast" in text
