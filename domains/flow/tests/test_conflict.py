# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Tests: Open Payments x Part D conflict-of-interest 2-cell."""

import domains  # noqa: F401  (path bootstrap)
from core.category import Category

from domains.flow.conflict import (
    ConflictDetector, summarize, synthetic_inputs, _spearman, _percentiles,
    DrugLevelConflict, summarize_drug, synthetic_drug_inputs,
    DiDConflict, summarize_did, synthetic_did_inputs,
)


def test_spearman_monotone_is_one():
    xs = [1, 2, 3, 4, 5]
    ys = [10, 20, 30, 40, 50]
    assert abs(_spearman(xs, ys) - 1.0) < 1e-9
    assert abs(_spearman(xs, [50, 40, 30, 20, 10]) + 1.0) < 1e-9


def test_percentiles_monotone():
    pct = _percentiles([5, 1, 3, 2, 4])
    # smallest value (1) gets the lowest percentile, largest (5) the highest
    assert pct[1] < pct[3] < pct[2] < pct[4] < pct[0]


def test_analyze_flags_high_high_and_positive_corr():
    payments, prescribing, spec = synthetic_inputs()
    rep = ConflictDetector(flag_pct=0.6).analyze(payments, prescribing, spec)
    assert rep.n_providers == 7           # NPIs present in both sources
    assert rep.correlation > 0.5          # paid providers prescribe more
    flagged = {r.npi for r in rep.flagged}
    assert {"201", "203", "206"} <= flagged
    # 205 (no payment) and 202 (tiny) must not be flagged.
    assert "205" not in flagged and "202" not in flagged


def test_no_overlap_returns_empty():
    rep = ConflictDetector().analyze({"1": 100.0}, {"2": 100.0})
    assert rep.n_providers == 0
    assert rep.flagged == []


def test_writes_two_cell_per_flagged_provider():
    payments, prescribing, spec = synthetic_inputs()
    cat = Category(db_path=":memory:")
    cosmos = None
    try:
        from core.cosmos import InfinityCosmos
        cosmos = InfinityCosmos(cat)
    except Exception:
        pass
    rep = ConflictDetector(category=cat, cosmos=cosmos, flag_pct=0.6).analyze(
        payments, prescribing, spec)
    risks = [m for m in cat.morphisms() if m.name == "conflict_risk"]
    assert len(risks) == len(rep.flagged)
    if cosmos is not None:
        h2k = cosmos.homotopy_2_category(rebuild=True)
        assert len(h2k.two_cells) == len(rep.flagged)


def test_summarize_runs():
    payments, prescribing, spec = synthetic_inputs()
    rep = ConflictDetector(flag_pct=0.6).analyze(payments, prescribing, spec)
    text = summarize(rep)
    assert "conflict-of-interest" in text
    assert "Spearman" in text


# -- drug-level ------------------------------------------------------------
def test_drug_level_lift_detects_planted_signal():
    payments, prescribing = synthetic_drug_inputs()
    rep = DrugLevelConflict(min_group=3).analyze(payments, prescribing)
    assert rep.n_drugs == 1                       # only DRUGX has both groups
    drugx = rep.top_drugs[0]
    assert drugx.drug == "DRUGX"
    # paid mean 850k / unpaid mean ~79k -> lift ~10.7x
    assert drugx.lift > 5.0
    assert rep.median_lift > 5.0


def test_drug_level_flags_and_2cells():
    payments, prescribing = synthetic_drug_inputs()
    cat = Category(db_path=":memory:")
    cosmos = None
    try:
        from core.cosmos import InfinityCosmos
        cosmos = InfinityCosmos(cat)
    except Exception:
        pass
    rep = DrugLevelConflict(category=cat, cosmos=cosmos, min_group=3,
                            min_payment=100, min_prescribing=10_000).analyze(
        payments, prescribing)
    # The three paid DRUGX prescribers are flagged (p1,p2,p3).
    flagged_npis = {r.npi for r in rep.flagged}
    assert {"p1", "p2", "p3"} <= flagged_npis
    # One summary risk edge per flagged PROVIDER (p1 flagged for 2 drugs -> 1 edge).
    risks = [m for m in cat.morphisms() if m.name == "drug_conflict_risk"]
    assert len(risks) == len(flagged_npis)
    # One 2-cell per flagged (provider, drug) PAIR.
    if cosmos is not None:
        h2k = cosmos.homotopy_2_category(rebuild=True)
        assert len(h2k.two_cells) == len(rep.flagged)


def test_drug_summary_runs():
    payments, prescribing = synthetic_drug_inputs()
    rep = DrugLevelConflict(min_group=3).analyze(payments, prescribing)
    assert "per-drug lift" in summarize_drug(rep)


# -- difference-in-differences --------------------------------------------
def test_did_nets_out_the_secular_trend():
    rx_prior, rx_post, paid_post, paid_prior = synthetic_did_inputs()
    rep = DiDConflict(min_group=25).analyze(rx_prior, rx_post, paid_post, paid_prior)
    assert rep.n_drugs == 1
    d = rep.drugs[0]
    assert d.drug == "DRUGX"
    assert d.n_treat == 30 and d.n_control == 30          # 'already paid' excluded
    assert abs(d.mean_delta_treat - 200_000) < 1.0
    assert abs(d.mean_delta_control - 50_000) < 1.0
    assert abs(d.did - 150_000) < 1.0                     # 200k - 50k trend
    assert abs(d.attributable - 150_000 * 30) < 1.0
    assert abs(rep.total_attributable - 150_000 * 30) < 1.0


def test_did_min_group_filters():
    rx_prior, rx_post, paid_post, paid_prior = synthetic_did_inputs()
    rep = DiDConflict(min_group=40).analyze(rx_prior, rx_post, paid_post, paid_prior)
    assert rep.n_drugs == 0                                # groups are 30 < 40


def test_did_summary_runs():
    rx_prior, rx_post, paid_post, paid_prior = synthetic_did_inputs()
    rep = DiDConflict(min_group=25).analyze(rx_prior, rx_post, paid_post, paid_prior)
    assert "diff-in-differences" in summarize_did(rep).lower()
