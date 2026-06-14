# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Tests: the unified leak ledger (assembly, ranking, scoring, output)."""

import json

import domains  # noqa: F401  (path bootstrap)

from domains.flow.ledger import (
    Ledger, Finding, tier, summarize,
    from_ma, from_drug_conflict, from_conservation, from_did,
)
from domains.flow.medicare_advantage import (
    MedicareAdvantageTwoCell, synthetic_contracts,
)
from domains.flow.conflict import (
    DrugLevelConflict, synthetic_drug_inputs, DiDConflict, synthetic_did_inputs,
)


def test_finding_priority_and_tier():
    f = Finding("d", "e", "c", dollars=1000.0, confidence=0.7)
    assert f.priority == 700.0
    assert f.tier == "HIGH"
    assert tier(0.5) == "MEDIUM" and tier(0.1) == "LOW"


def test_from_ma_only_positive_overpayments():
    results = MedicareAdvantageTwoCell().evaluate_all(synthetic_contracts())
    fs = from_ma(results)
    assert fs and all(f.dollars > 0 for f in fs)
    assert all(f.detector == "ma_overpayment" for f in fs)
    assert all(f.tier == "HIGH" for f in fs)        # conf 0.70


def test_from_drug_conflict_excess_dollars():
    pay, rx = synthetic_drug_inputs()
    rep = DrugLevelConflict(min_group=3).analyze(pay, rx)
    fs = from_drug_conflict(rep)
    assert len(fs) == 1                              # DRUGX
    f = fs[0]
    assert f.entity == "drug:DRUGX"
    # excess = (mean_paid - mean_unpaid) * n_paid = (850000 - 79166.67) * 3
    assert abs(f.dollars - (850000 - (475000/6)) * 3) < 1.0
    assert f.tier == "MEDIUM"


def test_from_did_attributable_findings():
    rx_prior, rx_post, paid_post, paid_prior = synthetic_did_inputs()
    rep = DiDConflict(min_group=25).analyze(rx_prior, rx_post, paid_post, paid_prior)
    fs = from_did(rep)
    assert len(fs) == 1 and fs[0].detector == "conflict_did"
    assert fs[0].entity == "drug:DRUGX"
    assert abs(fs[0].dollars - 150_000 * 30) < 1.0       # DiD * n_treat
    assert fs[0].tier == "MEDIUM"                          # conf 0.60


def test_conservation_one_directional_is_low_confidence():
    # Build a fake pair result where the line side is always < aggregate.
    from domains.flow.coherence import FlowCoherenceChecker, Section
    a = Section("cms_service", {"1": 100, "2": 50, "3": 10}, layer="3-provider")
    b = Section("cms_summary", {"1": 1000, "2": 800, "3": 600}, layer="3-provider")
    pr = FlowCoherenceChecker(tolerance=0.02).check_all([a, b])
    fs = from_conservation(pr)
    assert len(fs) == 1
    # one-directional -> confidence driven to 0.05 (ranked to the bottom)
    assert fs[0].confidence <= 0.05
    assert "artifact" in fs[0].caveat


def test_ledger_ranks_and_totals():
    led = Ledger()
    led.extend(from_ma(MedicareAdvantageTwoCell().evaluate_all(synthetic_contracts())))
    pay, rx = synthetic_drug_inputs()
    led.extend(from_drug_conflict(DrugLevelConflict(min_group=3).analyze(pay, rx)))
    ranked = led.ranked()
    # ranked by priority descending
    priorities = [f.priority for f in ranked]
    assert priorities == sorted(priorities, reverse=True)
    bd = led.by_detector()
    assert "ma_overpayment" in bd and "drug_conflict" in bd
    assert "THE LEAK LEDGER" in summarize(led)


def test_ledger_writes_csv_and_json(tmp_path):
    led = Ledger()
    led.extend(from_ma(MedicareAdvantageTwoCell().evaluate_all(synthetic_contracts())))
    csv_p = str(tmp_path / "led.csv")
    json_p = str(tmp_path / "led.json")
    led.to_csv(csv_p)
    led.to_json(json_p)
    rows = open(csv_p, encoding="utf-8").read().splitlines()
    assert rows[0].startswith("detector,entity,category,dollars")
    assert len(rows) == len(led.findings) + 1
    data = json.load(open(json_p, encoding="utf-8"))
    assert len(data) == len(led.findings)
    assert {"detector", "entity", "dollars", "confidence"} <= set(data[0])
