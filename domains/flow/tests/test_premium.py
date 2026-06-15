# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Phase D tests: the rebate/premium proxy and the reform tradeoff.

The proxy is accounting, not a forecast -- so the tests assert its STRUCTURE
(the tradeoff direction and the relative efficiency of the levers), not exact
dollars. The load-bearing insight: cutting the benchmark hits beneficiaries hard
(the rebate is benchmark-linked), while the coding adjustment is efficient (big
federal cut, small beneficiary cost).
"""

import domains  # noqa: F401  (path bootstrap)

from domains.flow.medicare_advantage import MedicareAdvantageTwoCell, MAContract
from domains.flow.scenario import (
    BehavioralModel, ScenarioEngine, PolicyLevers, synthetic_markets,
)
from domains.flow.premium import (
    RebateModel, beneficiary_outcome, compare_tradeoff, summarize_baseline_rebate,
)


def _engine():
    mkts = synthetic_markets()
    contracts = [MAContract(m.geo, m.enrollment, m.benchmark_per_capita,
                            m.ffs_per_capita, risk_score=1.20) for m in mkts]
    target = sum(r.overpayment
                 for r in MedicareAdvantageTwoCell().evaluate_all(contracts))
    return ScenarioEngine(mkts, BehavioralModel.calibrate(
        mkts, target_overpayment=target))


def test_baseline_rebate_positive_and_split_consistent():
    eng = _engine()
    ben = beneficiary_outcome(eng, PolicyLevers.baseline())
    assert ben.rebate_total > 0
    assert ben.rebate_per_enrollee > 0
    # premium relief + supplemental must reconstruct the whole rebate.
    assert abs((ben.premium_relief_total + ben.supplemental_total)
               - ben.rebate_total) < 1.0


      # linear in rebate_share


def test_benchmark_cap_cuts_beneficiary_value():
    eng = _engine()
    base = beneficiary_outcome(eng, PolicyLevers.baseline())
    capped = beneficiary_outcome(eng, PolicyLevers(benchmark_cap=1.0))
    assert capped.rebate_total < base.rebate_total      # enrollees lose benefits


def test_coding_adjustment_is_the_efficient_lever():
    """Coding adj cuts federal cost far more than it cuts beneficiary rebate;
    a benchmark cut hits beneficiaries proportionally much harder."""
    eng = _engine()
    base_res = eng.run(PolicyLevers.baseline())
    base_ben = beneficiary_outcome(eng, PolicyLevers.baseline())

    coding = PolicyLevers(coding_adjustment=0.20)
    cap = PolicyLevers(benchmark_cap=1.0)

    fed_coding = base_res.overpayment - eng.run(coding).overpayment
    ben_coding = base_ben.rebate_total - beneficiary_outcome(eng, coding).rebate_total
    fed_cap = base_res.overpayment - eng.run(cap).overpayment
    ben_cap = base_ben.rebate_total - beneficiary_outcome(eng, cap).rebate_total

    # coding adjustment: federal saving dwarfs the beneficiary cost.
    assert fed_coding > 5 * ben_coding
    # benchmark cap hits beneficiaries far harder per federal dollar saved.
    assert (ben_cap / fed_cap) > (ben_coding / fed_coding)


def test_compare_tradeoff_shows_both_sides():
    eng = _engine()
    text = compare_tradeoff(eng, [
        PolicyLevers.baseline(),
        PolicyLevers(coding_adjustment=0.20, label="coding 20%"),
        PolicyLevers(benchmark_cap=1.0, label="bench cap"),
    ])
    assert "fed chg" in text and "benef chg" in text
    assert "free lunch" in text
    # ASCII-only output (the console-encoding lesson).
    text.encode("cp1252")


def test_summarize_baseline_rebate_runs():
    eng = _engine()
    assert "rebate proxy" in summarize_baseline_rebate(eng)
