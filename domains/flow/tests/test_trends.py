# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Tests: the time dimension (multi-year trends)."""

import domains  # noqa: F401  (path bootstrap)

from domains.flow.trends import compute_trend, MATrendEngine, summarize
from domains.flow.ingest import write_fixtures


def test_compute_trend_cagr_and_direction():
    t = compute_trend("x", {2020: 100.0, 2021: 110.0, 2022: 121.0})
    assert t.years == [2020, 2021, 2022]
    assert abs(t.cagr - 0.10) < 1e-9          # 100 -> 121 over 2 yrs = 10%/yr
    assert t.direction == "GROWING"
    assert abs(t.yoy_latest - 0.10) < 1e-9


def test_trend_shrinking_and_flat():
    assert compute_trend("d", {2020: 100.0, 2022: 81.0}).direction == "SHRINKING"
    assert compute_trend("f", {2020: 100.0, 2022: 100.5}).direction == "FLAT"


def test_accelerating_flag():
    # latest YoY (50%) exceeds long-run CAGR -> accelerating
    t = compute_trend("a", {2020: 100.0, 2021: 105.0, 2022: 157.5})
    assert t.accelerating


def test_ma_trend_engine_on_fixture(tmp_path):
    paths = write_fixtures(str(tmp_path))
    rep = MATrendEngine().analyze(paths["ffs_geovar"], list(range(2014, 2025)))
    # Fixture has CA & TX for 2022-2024 (and PR, which is skipped as a territory).
    assert rep.years == [2022, 2023, 2024]
    assert len(rep.national_overpayment.values) == 3
    assert set(rep.state_trends) == {"CA", "TX"}
    assert len(rep.state_trends["CA"].years) == 3
    # Enrollment grows over the window -> national overpayment grows.
    assert rep.national_overpayment.latest > rep.national_overpayment.first
    assert rep.national_overpayment.direction == "GROWING"


def test_summary_runs(tmp_path):
    paths = write_fixtures(str(tmp_path))
    rep = MATrendEngine().analyze(paths["ffs_geovar"], list(range(2022, 2025)))
    text = summarize(rep)
    assert "the time dimension" in text
    assert "CAGR" in text
