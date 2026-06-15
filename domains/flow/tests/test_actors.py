# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Phase E tests: the activity-theory actor / lever map (the scenario frame)."""

import domains  # noqa: F401  (path bootstrap)

from categorical.activity_system import ActivityComponent
from domains.flow.actors import (
    build_activity_system, build_actor_map, summarize_actor_map,
    LEVER_OWNERS, ACTOR_OBJECTIVES,
)


def test_map_has_the_six_activity_components():
    s = build_activity_system()
    kinds = {c.component_type for c in s.components.values()}
    assert ActivityComponent.SUBJECT in kinds
    assert ActivityComponent.OBJECT in kinds
    assert ActivityComponent.TOOL in kinds
    assert ActivityComponent.COMMUNITY in kinds


def test_plan_gap_is_grounded_in_overpayment_ratio():
    """The plan<->program misalignment must track the measured overpayment ratio."""
    s_lo = build_activity_system(0.10)
    s_hi = build_activity_system(0.30)
    plan_lo = next(m.confidence for m in s_lo.morphisms
                   if m.source == "plan" and m.target == "efficient_coverage")
    plan_hi = next(m.confidence for m in s_hi.morphisms
                   if m.source == "plan" and m.target == "efficient_coverage")
    assert plan_lo > plan_hi                      # more overpayment = worse alignment
    assert abs(plan_hi - 0.70) < 1e-9


def test_contradictions_detected():
    amap = build_actor_map(0.20)
    assert len(amap.contradictions) >= 1
    assert all(c.tension > 0 for c in amap.contradictions)


def test_levers_and_objectives_present():
    assert "site_neutral" in LEVER_OWNERS
    assert "coding_intensity" in LEVER_OWNERS         # the plan's own lever
    assert "plan" in ACTOR_OBJECTIVES and "provider" in ACTOR_OBJECTIVES


def test_summary_runs_ascii():
    text = summarize_actor_map(build_actor_map(0.20))
    assert "actor / lever map" in text
    assert "contradictions detected" in text
    text.encode("cp1252")
