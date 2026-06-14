# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Tests: Open Payments x Part D conflict-of-interest 2-cell."""

import domains  # noqa: F401  (path bootstrap)
from core.category import Category

from domains.flow.conflict import (
    ConflictDetector, summarize, synthetic_inputs, _spearman, _percentiles,
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
