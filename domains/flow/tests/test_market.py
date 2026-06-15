# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Phase H tests: the Market and Patient actors (competition and demand elasticity)."""

import pytest

from domains.flow.market import MarketModel, PatientModel
from domains.flow.scenario import (
    Market, PolicyLevers, BehavioralModel, ScenarioEngine,
)
from domains.flow.chain import run_chain


def test_market_pass_through():
    """Test that competition index scales the pass-through rate correctly."""
    base_market = MarketModel()
    assert base_market.effective_pass_through == 0.15
    
    comp_market = MarketModel(competition_index=2.0)
    assert comp_market.effective_pass_through == 0.30
    
    max_market = MarketModel(competition_index=10.0)
    assert max_market.effective_pass_through == 1.0 # Capped at 1.0


def test_patient_enrollment_elasticity():
    """Test that patient enrollment responds correctly to rebate changes."""
    patient = PatientModel(demand_elasticity=2.0) # 2% enr change per 1% rebate/ffs change
    
    base_enr = 100_000
    base_rebate = 1000.0
    ffs_cost = 10_000.0
    
    # No change in rebate -> no change in enrollment
    assert patient.calculate_enrollment(base_enr, base_rebate, base_rebate, ffs_cost) == base_enr
    
    # +$100 rebate = +1% of ffs_cost -> +2% enrollment
    new_rebate_up = 1100.0
    assert patient.calculate_enrollment(base_enr, base_rebate, new_rebate_up, ffs_cost) == 102_000
    
    # -$100 rebate = -1% of ffs_cost -> -2% enrollment
    new_rebate_down = 900.0
    assert patient.calculate_enrollment(base_enr, base_rebate, new_rebate_down, ffs_cost) == 98_000


def test_bidirectional_feedback_loop():
    """Integration test: Verify the Bidirectional Nash solver.
    
    A plan with an elastic patient market should code more aggressively (higher p*)
    than a plan with an inelastic market, because the extra margin funds rebates
    which attract more enrollees, multiplying the total profit.
    """
    m = Market("test", 100_000, ffs_per_capita=10_000, benchmark_per_capita=11_000)
    markets = [m]
    
    # A standard model
    b_model = BehavioralModel(base_deter=0.05)
    engine = ScenarioEngine(markets, b_model)
    levers = PolicyLevers.baseline()
    
    # Inelastic (Phase G behavior)
    market_inelastic = MarketModel(competition_index=1.0)
    patient_inelastic = PatientModel(demand_elasticity=0.0)
    
    # Elastic (Phase H behavior)
    market_elastic = MarketModel(competition_index=2.0) # High pass-through needed to attract
    patient_elastic = PatientModel(demand_elasticity=5.0) # Highly sensitive to rebate
    
    # Run the chain with both
    res_inelastic = run_chain(engine, levers, market_model=market_inelastic, patient_model=patient_inelastic)
    res_elastic = run_chain(engine, levers, market_model=market_elastic, patient_model=patient_elastic)
    
    p_inelastic = res_inelastic.result.mean_risk
    p_elastic = res_elastic.result.mean_risk
    
    # The elastic plan should code slightly harder to fund the rebate and capture volume
    assert p_elastic >= p_inelastic
    
    # The elastic plan should have gained enrollment due to the higher rebate
    # Actually at baseline levers, base_rebate == new_rebate so enr is unchanged.
    # We must test a lever that *cuts* margin to see the elasticity bite.
    
    cut_levers = PolicyLevers(coding_adjustment=0.20)
    res_inelastic_cut = run_chain(engine, cut_levers, market_model=market_inelastic, patient_model=patient_inelastic)
    res_elastic_cut = run_chain(engine, cut_levers, market_model=market_elastic, patient_model=patient_elastic)
    
    # The inelastic plan's enrollment doesn't change
    assert res_inelastic_cut.result.enrollment == 100_000
    
    # The elastic plan's enrollment should fall because the cut reduced rebates
    assert res_elastic_cut.result.enrollment < 100_000
