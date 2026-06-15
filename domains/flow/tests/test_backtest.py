# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Phase G tests: backtest & sensitivity.

We assert STRUCTURE and the robust properties (directional agreement, elasticity
ranking stability), not the fragile numbers -- the whole point of the module is
to surface where the model is and isn't robust, so the tests must not pretend a
fragile result is solid.
"""

import domains  # noqa: F401  (path bootstrap)

from domains.flow.scenario import (
    BehavioralModel, ScenarioEngine, PolicyLevers, synthetic_markets,
)
from domains.flow.backtest import (
    forensic_overpayment, bootstrap_calibration, state_holdout_cv,
    sensitivity, directional_checks, summarize_backtest, DEFAULT_KAPPA,
)


def _markets_target():
    mkts = synthetic_markets()
    return mkts, forensic_overpayment(mkts)


def test_forensic_overpayment_positive():
    mkts, target = _markets_target()
    assert target > 0


def test_bootstrap_returns_sane_spread():
    mkts, _ = _markets_target()
    rep = bootstrap_calibration(mkts, trials=20, frac=0.75, seed=1)
    assert rep.base_deters
    assert rep.mean > 0
    assert rep.cv >= 0.0


def test_holdout_cv_runs_and_reports_error():
    mkts, _ = _markets_target()
    rep = state_holdout_cv(mkts, folds=2, seed=1)
    assert rep.folds >= 1
    assert rep.mean_error >= 0.0
    assert rep.max_error >= rep.mean_error - 1e-12


def test_sensitivity_elasticity_ranking_is_robust():
    """The headline conclusions should survive the gain-elasticity assumption."""
    mkts, target = _markets_target()
    rep = sensitivity(mkts, target, param="elasticity", values=[0.5, 1.0, 2.0, 4.0])
    assert rep.ranking_stable
    assert len(rep.headline_deltas) == 4
    assert all(d < 0 for d in rep.headline_deltas)   # coding-adj always cuts cost


def test_sensitivity_reports_a_ranking_per_value():
    mkts, target = _markets_target()
    rep = sensitivity(mkts, target, param="kappa", values=[0.20, 0.30, 0.40])
    assert len(rep.rankings) == 3
    assert all(isinstance(r, list) and r for r in rep.rankings)


def test_directional_checks_all_agree():
    mkts, target = _markets_target()
    eng = ScenarioEngine(mkts, BehavioralModel.calibrate(
        mkts, target_overpayment=target))
    checks = directional_checks(eng)
    assert len(checks) == 3
    assert all(c.agrees for c in checks)             # model matches published direction


def test_summary_runs_ascii():
    mkts, target = _markets_target()
    eng = ScenarioEngine(mkts, BehavioralModel.calibrate(
        mkts, target_overpayment=target))
    text = summarize_backtest(
        bootstrap_calibration(mkts, trials=10, seed=2),
        state_holdout_cv(mkts, folds=2, seed=2),
        [sensitivity(mkts, target, param="elasticity", values=[0.5, 1.0, 2.0])],
        directional_checks(eng))
    assert "backtest" in text.lower()
    assert "directional" in text.lower()
    text.encode("cp1252")
