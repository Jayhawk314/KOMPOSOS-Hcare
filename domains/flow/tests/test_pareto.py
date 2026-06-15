# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Tests for Phase I: The Pareto Optimizer."""

import pytest
from domains.flow.pareto import (
    generate_grid, get_pareto_frontier, EvaluatedState,
    build_optimization_category, is_adjacent
)
from domains.flow.scenario import PolicyLevers


def test_pareto_dominance():
    """Verify that the Pareto filter correctly drops dominated states."""
    
    # State A is mediocre
    s_a = EvaluatedState(
        levers=PolicyLevers(coding_adjustment=0.1, audit_multiplier=1.0),
        overpayment=100.0, enrollment=100, rebate_total=100.0,
        saving_vs_base=10.0, enrollment_vs_base=0, rebate_vs_base=0.0
    )
    
    # State B is strictly better than A on all fronts
    s_b = EvaluatedState(
        levers=PolicyLevers(coding_adjustment=0.2, audit_multiplier=1.0),
        overpayment=80.0, enrollment=110, rebate_total=110.0,
        saving_vs_base=30.0, enrollment_vs_base=10, rebate_vs_base=10.0
    )
    
    # State C is better than B on saving, but worse on enrollment
    s_c = EvaluatedState(
        levers=PolicyLevers(coding_adjustment=0.2, audit_multiplier=2.0),
        overpayment=50.0, enrollment=90, rebate_total=90.0,
        saving_vs_base=60.0, enrollment_vs_base=-10, rebate_vs_base=-10.0
    )
    
    assert s_b.dominates(s_a)
    assert not s_a.dominates(s_b)
    
    assert not s_c.dominates(s_b) # C is worse on enr/rebate
    assert not s_b.dominates(s_c) # B is worse on saving
    
    states = [s_a, s_b, s_c]
    frontier = get_pareto_frontier(states)
    
    # A should be dropped, B and C should remain
    assert len(frontier) == 2
    assert s_b in frontier
    assert s_c in frontier
    assert s_a not in frontier


def test_grid_adjacency():
    """Verify that adjacent states are correctly identified."""
    base = PolicyLevers(coding_adjustment=0.059, audit_multiplier=1.0, penalty_multiplier=1.0, benchmark_cap=None)
    
    # One step: change coding adj
    step1 = PolicyLevers(coding_adjustment=0.10, audit_multiplier=1.0, penalty_multiplier=1.0, benchmark_cap=None)
    assert is_adjacent(base, step1)
    
    # Two steps: change coding adj and audit
    step2 = PolicyLevers(coding_adjustment=0.10, audit_multiplier=2.0, penalty_multiplier=1.0, benchmark_cap=None)
    assert not is_adjacent(base, step2)
    assert is_adjacent(step1, step2)


def test_optimization_category_structure():
    """Verify that the KOMPOSOS-IV Category is built correctly with distance penalties."""
    states = [
        EvaluatedState(
            levers=PolicyLevers(coding_adjustment=0.1),
            overpayment=100.0, enrollment=100, rebate_total=100.0,
            saving_vs_base=10.0, enrollment_vs_base=0, rebate_vs_base=0.0
        ),
        EvaluatedState(
            levers=PolicyLevers(coding_adjustment=0.2),
            overpayment=50.0, enrollment=100, rebate_total=100.0,
            saving_vs_base=60.0, enrollment_vs_base=0, rebate_vs_base=0.0
        )
    ]
    
    # Target: 50 saving, 100 enrollment. State 2 beats this.
    cat = build_optimization_category(states, target_saving=50.0, min_enrollment=100)
    
    object_names = [obj.name for obj in cat.objects()]
    assert "Target" in object_names
    assert len(cat.objects()) == 3
    
    # State 1 is far from target
    m_reaches_1 = cat.get_morphism(f"reaches_{states[0].key}:{states[0].key}->Target")
    assert m_reaches_1 is not None
    assert m_reaches_1.confidence < 0.8
    
    # State 2 achieves target
    m_achieves_2 = cat.get_morphism(f"achieves_{states[1].key}:{states[1].key}->Target")
    assert m_achieves_2 is not None
    assert m_achieves_2.confidence == 0.99