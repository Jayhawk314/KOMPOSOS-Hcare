# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Phase E tests: the CMS -> provider -> plan chain (open-game backward induction).

The load-bearing properties:
  - baseline (site_neutral=0) is identity (reproduces the calibrated outcome);
  - the generic OpenGame composition agrees with the hand-rolled induction;
  - FIXED benchmarks: a provider-side efficiency reform RAISES federal cost
    (plans code into the freed headroom) -- the non-obvious chain result;
  - REBASED benchmarks: the same reform LOWERS it. Direction flips on the regime.
"""

import domains  # noqa: F401  (path bootstrap)
from dataclasses import replace

from domains.flow.medicare_advantage import MedicareAdvantageTwoCell, MAContract
from domains.flow.scenario import (
    BehavioralModel, ScenarioEngine, PolicyLevers, synthetic_markets,
)
from domains.flow.chain import (
    ProviderModel, provider_response, run_chain, chain_open_game,
    compare_site_neutral, _effective_ffs,
)


def _engine():
    mkts = synthetic_markets()
    contracts = [MAContract(m.geo, m.enrollment, m.benchmark_per_capita,
                            m.ffs_per_capita, risk_score=1.20) for m in mkts]
    target = sum(r.overpayment
                 for r in MedicareAdvantageTwoCell().evaluate_all(contracts))
    return ScenarioEngine(mkts, BehavioralModel.calibrate(
        mkts, target_overpayment=target))


# -- provider best response -------------------------------------------------
def test_provider_response_bounds_and_monotonicity():
    pm = ProviderModel()
    assert abs(provider_response(0.0, pm) - pm.hopd_share_base) < 1e-12
    assert abs(provider_response(1.0, pm)) < 1e-12
    assert provider_response(0.3, pm) > provider_response(0.7, pm)


def test_effective_ffs_identity_at_baseline():
    pm = ProviderModel()
    assert abs(_effective_ffs(11_000.0, 0.0, pm) - 11_000.0) < 1e-9
    assert _effective_ffs(11_000.0, 1.0, pm) < 11_000.0   # site-neutral lowers cost


# -- the chain ---------------------------------------------------------------
def test_chain_baseline_is_identity():
    eng = _engine()
    base = eng.run(PolicyLevers.baseline()).overpayment
    chained = run_chain(eng, PolicyLevers.baseline(), site_neutral=0.0).result.overpayment
    assert abs(chained - base) / base < 1e-9


def test_open_game_matches_manual_backward_induction():
    eng = _engine()
    pm = ProviderModel()
    m = eng.markets[0]
    lev = PolicyLevers.baseline()
    og = chain_open_game(m, lev, eng.model, 0.5, pm)
    mm = replace(m, ffs_per_capita=_effective_ffs(m.ffs_per_capita, 0.5, pm))
    er = eng.model.risk_score(mm, lev) * (1.0 - lev.coding_adjustment)
    manual = mm.enrollment * (mm.benchmark_per_capita * er
                              - mm.ffs_per_capita * mm.ffs_risk)
    assert abs(og - manual) < 1e-3


def test_fixed_benchmark_site_neutral_raises_cost():
    """The non-obvious chain result: provider efficiency, captured by plans."""
    eng = _engine()
    base = run_chain(eng, PolicyLevers.baseline(), site_neutral=0.0,
                     rebase_benchmark=False).result
    sn = run_chain(eng, PolicyLevers.baseline(), site_neutral=1.0,
                   rebase_benchmark=False).result
    assert sn.overpayment > base.overpayment
    assert sn.mean_risk > base.mean_risk            # plan codes harder


def test_rebased_benchmark_site_neutral_lowers_cost():
    eng = _engine()
    base = run_chain(eng, PolicyLevers.baseline(), site_neutral=0.0,
                     rebase_benchmark=True).result
    sn = run_chain(eng, PolicyLevers.baseline(), site_neutral=1.0,
                   rebase_benchmark=True).result
    assert sn.overpayment < base.overpayment
    assert sn.paid < base.paid
    assert abs(sn.mean_risk - base.mean_risk) < 1e-6   # headroom preserved


def test_compare_site_neutral_runs_ascii():
    eng = _engine()
    text = compare_site_neutral(eng)
    assert "site-neutral" in text and "rebased" in text
    text.encode("cp1252")
