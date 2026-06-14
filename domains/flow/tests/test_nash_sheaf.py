# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Phase 3 tests: the Nash sheaf cross-market gaming detector."""

import domains  # noqa: F401  (path bootstrap)
from core.category import Category

from domains.flow.nash_sheaf import (
    local_nash_intensity, inspection_game, MarketObs, NashSheaf,
    synthetic_observations, MAX_UPCODE,
)


def test_local_nash_monotone_in_incentives():
    low = local_nash_intensity(benchmark_headroom=0.02, audit_pressure=0.9)
    high = local_nash_intensity(benchmark_headroom=0.24, audit_pressure=0.1)
    assert 1.0 <= low < high <= 1.0 + MAX_UPCODE + 1e-9


def test_no_headroom_means_honest():
    assert abs(local_nash_intensity(0.0, 0.5) - 1.0) < 1e-9


def test_inspection_game_has_no_pure_nash():
    # classic inspection game -> mixed only
    g = inspection_game(benchmark_headroom=0.2, audit_pressure=0.1)
    assert g.find_pure_nash() == []


def test_honest_plan_has_zero_h1():
    obs = [MarketObs("H", f"m{i}", 1.05, 50_000,
                     benchmark_headroom=0.02 * i, audit_pressure=0.9)
           for i in range(1, 6)]
    r = NashSheaf().analyze_plan(obs)
    assert r.h1_energy < 1e-6
    assert r.gaming_score < 1e-6
    assert r.strategic is False


def test_strategic_gamer_flagged():
    results = {r.plan_id: r for r in NashSheaf().analyze(synthetic_observations())}
    gamer = results["GamerMax"]
    assert gamer.strategic is True
    assert gamer.incentive_alignment > 0.5
    assert gamer.h1_energy > 0


def test_noisy_plan_not_strategic_despite_variance():
    """The key property: high variance but incentive-UNaligned != strategic."""
    results = {r.plan_id: r for r in NashSheaf().analyze(synthetic_observations())}
    noisy = results["NoisyPlan"]
    gamer = results["GamerMax"]
    assert noisy.gaming_score > 0.1          # genuinely high variance
    assert noisy.h1_energy >= gamer.h1_energy  # even higher than the gamer
    assert noisy.strategic is False          # but NOT flagged -- not aligned
    assert abs(noisy.incentive_alignment) < 0.3


def test_h1_invariant_to_constant_shift():
    base = [MarketObs("P", f"m{i}", 1.0 + 0.05 * i, 10_000) for i in range(5)]
    shifted = [MarketObs("P", o.market_id, o.observed_intensity + 0.5,
                         o.enrollment) for o in base]
    r1 = NashSheaf().analyze_plan(base)
    r2 = NashSheaf().analyze_plan(shifted)
    assert abs(r1.h1_energy - r2.h1_energy) < 1e-6  # coboundary ignores constants


def test_worst_markets_localized():
    results = {r.plan_id: r for r in NashSheaf().analyze(synthetic_observations())}
    gamer = results["GamerMax"]
    assert len(gamer.worst_markets) > 0
    # extreme-incentive markets (m1 lowest, m5 highest) drive the inconsistency
    names = {m for m, _ in gamer.worst_markets[:2]}
    assert "m5" in names or "m1" in names


def test_writeback_strategic_only():
    cat = Category(db_path=":memory:")
    NashSheaf(category=cat).analyze(synthetic_observations())
    sg = [m for m in cat.morphisms() if m.name == "strategic_gaming"]
    assert len(sg) == 1  # only GamerMax
    plays = [m for m in cat.morphisms() if m.name == "plays_in"]
    assert len(plays) == 15  # 3 plans x 5 markets
