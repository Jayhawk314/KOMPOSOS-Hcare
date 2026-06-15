# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Phase I: The Pareto Optimizer.

Sweeps the policy lever space, calculates the multi-objective outcomes
(federal saving, enrollment, beneficiary value) using the Phase H
bidirectional OpenGames, and uses OPTIMUS categorical gradient descent
to find the optimal path of reforms to a target goal.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Set

from core.category import Category
from core.optimus import OptimusEngine

from domains.flow.scenario import PolicyLevers, ScenarioEngine
from domains.flow.market import MarketModel, PatientModel
from domains.flow.chain import run_chain
from domains.flow.premium import beneficiary_outcome, RebateModel


@dataclass
class EvaluatedState:
    levers: PolicyLevers
    overpayment: float
    enrollment: int
    rebate_total: float
    
    # Deltas vs baseline
    saving_vs_base: float
    enrollment_vs_base: int
    rebate_vs_base: float
    
    @property
    def key(self) -> str:
        b_cap = f"{self.levers.benchmark_cap:.2f}" if self.levers.benchmark_cap else "None"
        return f"c{self.levers.coding_adjustment:.3f}_a{self.levers.audit_multiplier:.1f}_p{self.levers.penalty_multiplier:.1f}_b{b_cap}"

    def dominates(self, other: "EvaluatedState") -> bool:
        """True if this state is >= on all objectives and > on at least one.
        Objectives: Maximize saving, Maximize enrollment, Maximize rebate.
        """
        # We allow a tiny epsilon for floating point math
        eps = 1e-5
        
        save_geq = self.saving_vs_base >= other.saving_vs_base - eps
        enr_geq = self.enrollment_vs_base >= other.enrollment_vs_base
        reb_geq = self.rebate_vs_base >= other.rebate_vs_base - eps
        
        save_gt = self.saving_vs_base > other.saving_vs_base + eps
        enr_gt = self.enrollment_vs_base > other.enrollment_vs_base
        reb_gt = self.rebate_vs_base > other.rebate_vs_base + eps
        
        return (save_geq and enr_geq and reb_geq) and (save_gt or enr_gt or reb_gt)


def generate_grid() -> List[PolicyLevers]:
    """Generate a bounded grid of policy levers to explore."""
    coding_adjs = [0.059, 0.10, 0.15, 0.20]
    audits = [1.0, 2.0, 3.0, 5.0]
    penalties = [1.0, 2.0, 3.0]
    benchmarks = [None, 1.05, 1.00]
    
    grid = []
    for c, a, p, b in itertools.product(coding_adjs, audits, penalties, benchmarks):
        # Skip absurd combinations to save time (e.g. baseline coding but max penalty)
        # We'll just build the full grid for the optimizer to search
        grid.append(PolicyLevers(
            coding_adjustment=c, audit_multiplier=a, 
            penalty_multiplier=p, benchmark_cap=b,
            label=f"c{c:.3f}_a{a}_p{p}_b{b}"
        ))
    return grid


def evaluate_grid(engine: ScenarioEngine, grid: List[PolicyLevers],
                  market_model: MarketModel, patient_model: PatientModel) -> List[EvaluatedState]:
    """Evaluate every point in the grid to find its outcomes."""
    base_levers = PolicyLevers.baseline()
    rb = RebateModel()
    
    # Baseline
    base_res = run_chain(engine, base_levers, market_model=market_model, patient_model=patient_model).result
    base_ben = beneficiary_outcome(engine, base_levers, rb, market_model=market_model, patient_model=patient_model)
    
    states = []
    for levers in grid:
        res = run_chain(engine, levers, market_model=market_model, patient_model=patient_model).result
        ben = beneficiary_outcome(engine, levers, rb, market_model=market_model, patient_model=patient_model)
        
        saving = base_res.overpayment - res.overpayment
        enr_chg = ben.enrollment - base_ben.enrollment
        reb_chg = ben.rebate_total - base_ben.rebate_total
        
        states.append(EvaluatedState(
            levers=levers, overpayment=res.overpayment,
            enrollment=ben.enrollment, rebate_total=ben.rebate_total,
            saving_vs_base=saving, enrollment_vs_base=enr_chg, rebate_vs_base=reb_chg
        ))
    return states


def _aggressiveness(levers: PolicyLevers) -> tuple:
    """Sort key for 'simplest/least aggressive' policy (fewer, smaller lever moves
    from baseline). Used to pick a canonical representative among ties."""
    base = PolicyLevers.baseline()
    moves = sum([
        levers.coding_adjustment != base.coding_adjustment,
        levers.audit_multiplier != base.audit_multiplier,
        levers.penalty_multiplier != base.penalty_multiplier,
        levers.benchmark_cap is not None,
    ])
    cap_pen = (1.0 - levers.benchmark_cap) if levers.benchmark_cap is not None else 0.0
    return (moves, levers.coding_adjustment, levers.audit_multiplier,
            levers.penalty_multiplier, cap_pen)


def get_pareto_frontier(states: List[EvaluatedState]) -> List[EvaluatedState]:
    """Filter the evaluated grid to the non-dominated Pareto frontier, then
    collapse degenerate ties (lever combos producing the SAME outcome because the
    extra levers don't bind -- e.g. audit/penalty under a benchmark cap that
    already minimizes coding) to their simplest representative."""
    frontier = [s for s in states
                if not any(other.dominates(s) for other in states)]

    # Collapse only TRULY identical outcomes (non-binding levers produce
    # bit-identical results), keeping the simplest lever combo.
    best: Dict[tuple, EvaluatedState] = {}
    for s in frontier:
        key = (round(s.saving_vs_base, 2), s.enrollment_vs_base,
               round(s.rebate_vs_base, 2))
        cur = best.get(key)
        if cur is None or _aggressiveness(s.levers) < _aggressiveness(cur.levers):
            best[key] = s
    return sorted(best.values(), key=lambda s: s.saving_vs_base)


def recommend(frontier: List[EvaluatedState], target_saving: float,
              min_enrollment: int) -> Optional[EvaluatedState]:
    """The honest answer: among frontier policies that MEET the constraints
    (>= target saving AND >= min enrollment), pick the one with the least
    beneficiary harm (smallest rebate loss), tie-broken by simplicity. No
    'confidence' theater -- just the feasible, least-harm policy."""
    feasible = [s for s in frontier
                if s.saving_vs_base >= target_saving and s.enrollment >= min_enrollment]
    if not feasible:
        return None
    return min(feasible, key=lambda s: (-s.rebate_vs_base, _aggressiveness(s.levers)))


# ---------------------------------------------------------------------------
# OPTIMUS Integration
# ---------------------------------------------------------------------------

def is_adjacent(s1: PolicyLevers, s2: PolicyLevers) -> bool:
    """Define adjacency in the grid (can we move from s1 to s2 in one step?)."""
    diffs = 0
    if s1.coding_adjustment != s2.coding_adjustment: diffs += 1
    if s1.audit_multiplier != s2.audit_multiplier: diffs += 1
    if s1.penalty_multiplier != s2.penalty_multiplier: diffs += 1
    if s1.benchmark_cap != s2.benchmark_cap: diffs += 1
    return diffs == 1


def build_optimization_category(states: List[EvaluatedState], 
                                target_saving: float, 
                                min_enrollment: int) -> Category:
    """Build a KOMPOSOS-IV Category mapping the policy space for OPTIMUS."""
    cat = Category("pareto_search", db_path=":memory:")
    
    # 1. Add all states as objects
    for state in states:
        cat.add(state.key)
        
    cat.add("Target")
    
    # 2. Add adjacency morphisms (the possible paths)
    for s1 in states:
        for s2 in states:
            if is_adjacent(s1.levers, s2.levers):
                # We want the optimizer to prefer paths that don't destroy value
                # Confidence = 0.9 if the step is Pareto-improving (or flat), else 0.5
                if s2.saving_vs_base >= s1.saving_vs_base and s2.enrollment_vs_base >= s1.enrollment_vs_base:
                    conf = 0.9
                else:
                    conf = 0.5
                cat.connect(s1.key, s2.key, f"step_{s1.key}_to_{s2.key}", confidence=conf)
                
    # 3. Connect states to Target based on how close they are to the goal
    for state in states:
        # Distance penalty
        saving_gap = max(0.0, target_saving - state.saving_vs_base)
        enr_gap = max(0, min_enrollment - state.enrollment)
        
        if saving_gap == 0 and enr_gap == 0:
            # Hit the target exactly
            cat.connect(state.key, "Target", f"achieves_{state.key}", confidence=0.99)
        else:
            # Scale confidence down based on distance. 
            # E.g., if we are 10B short on a 50B goal, that's a 20% penalty.
            saving_penalty = saving_gap / max(1.0, target_saving)
            enr_penalty = enr_gap / max(1.0, min_enrollment)
            
            total_penalty = saving_penalty + enr_penalty
            # Confidence falls from 0.8 down to 0.1
            conf = max(0.1, 0.8 - (total_penalty * 0.7))
            cat.connect(state.key, "Target", f"reaches_{state.key}", confidence=conf)
            
    return cat


def run_optimus_search(engine: ScenarioEngine, market_model: MarketModel, 
                       patient_model: PatientModel, target_saving: float, 
                       min_enrollment: int) -> Tuple[List[EvaluatedState], Optional[str]]:
    """Run categorical gradient descent to find the optimal reform path."""
    grid = generate_grid()
    states = evaluate_grid(engine, grid, market_model, patient_model)
    frontier = get_pareto_frontier(states)
    
    cat = build_optimization_category(states, target_saving, min_enrollment)
    
    # Use OPTIMUS to find the best path from baseline to Target
    base_key = PolicyLevers.baseline().label
    
    # We must ensure the baseline key exists in the category exactly as formatted
    # The grid generator uses "c0.059_a1.0_p1.0_bNone" for baseline, but the default
    # PolicyLevers.baseline().label is just "baseline".
    # Let's find the state that matches baseline levers
    base_state = next((s for s in states if 
                      s.levers.coding_adjustment == 0.059 and 
                      s.levers.audit_multiplier == 1.0 and 
                      s.levers.penalty_multiplier == 1.0 and 
                      s.levers.benchmark_cap is None), None)
                      
    if not base_state:
        return frontier, None

    opt = OptimusEngine(cat)
    # Refine the path from baseline to Target. 
    # Depth=3 allows it to find paths up to 4 hops long.
    result = opt.refine_morphism(base_state.key, "Target", depth=3)
    
    optimal_path_summary = None
    if result and result.provenance == "optimus":
        # OPTIMUS found a shortcut. 
        # The metadata["optimus_provenance"] contains the chain of morphisms it compressed.
        if "optimus_provenance" in result.metadata:
            path_names = result.metadata["optimus_provenance"]
            optimal_path_summary = f"OPTIMUS categorical gradient descent found a path (Confidence: {result.confidence:.2f}):\n"
            for step in path_names:
                optimal_path_summary += f"  -> {step}\n"
        
    return frontier, optimal_path_summary


def _lever_label(levers: PolicyLevers) -> str:
    b_cap = f"cap={levers.benchmark_cap:.2f}" if levers.benchmark_cap else "no cap"
    return (f"adj={levers.coding_adjustment:.2f}, audit={levers.audit_multiplier}x, "
            f"pen={levers.penalty_multiplier}x, {b_cap}")


def summarize_pareto(frontier: List[EvaluatedState], *,
                     target_saving: float, min_enrollment: int,
                     optimal_path: Optional[str] = None) -> str:
    """Format the Pareto frontier, leading with the honest recommendation (the
    feasible least-harm policy). ``optimal_path`` is an OPTIONAL experimental
    appendix, not the headline."""
    rows = [("policy levers", "fed saving", "enrollment", "rebate chg")]
    below_ffs = False
    for s in frontier:
        # A "saving" larger than baseline overpayment means overpayment went
        # negative -- MA below FFS, an out-of-validation regime; flag it.
        flag = ""
        if s.overpayment < 0:
            below_ffs = True
            flag = " *"
        rows.append((
            _lever_label(s.levers),
            f"${s.saving_vs_base/1e9:+,.1f}B{flag}",
            f"{s.enrollment:,} ({s.enrollment_vs_base:+,})",
            f"${s.rebate_vs_base/1e9:+,.1f}B"
        ))

    w = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    lines = ["Multi-objective Pareto frontier (federal saving x enrollment x rebate)",
             "=" * (sum(w) + len(w) * 2)]
    for i, row in enumerate(rows):
        lines.append("  " + "  ".join(c.ljust(w[j]) for j, c in enumerate(row)))
        if i == 0:
            lines.append("  " + "  ".join("-" * w[j] for j in range(len(w))))
    lines.append("-" * (sum(w) + len(w) * 2))
    if below_ffs:
        lines.append("  * saving exceeds baseline overpayment -> that row prices MA "
                     "BELOW FFS, an\n    out-of-validation regime (extreme "
                     "extrapolation); read those rows with caution.")

    # The honest recommendation -- no confidence theater.
    rec = recommend(frontier, target_saving, min_enrollment)
    lines.append(f"\nGoal: >= ${target_saving/1e9:,.1f}B saving AND "
                 f">= {min_enrollment:,} enrollment.")
    if rec is None:
        lines.append("RECOMMENDATION: no policy on the frontier meets BOTH "
                     "constraints -- they trade off; relax one.")
    else:
        lines.append(f"RECOMMENDATION (feasible, least beneficiary harm): "
                     f"{_lever_label(rec.levers)}")
        cav = "  [below-FFS regime -- caution]" if rec.overpayment < 0 else ""
        lines.append(f"  -> federal saving ${rec.saving_vs_base/1e9:+,.1f}B, "
                     f"enrollment {rec.enrollment:,} ({rec.enrollment_vs_base:+,}), "
                     f"rebate {rec.rebate_vs_base/1e9:+,.1f}B{cav}")
    if optimal_path:
        lines.append("\n[experimental] OPTIMUS categorical pathfinder (illustrative "
                     "only; the confidence\n  weights are heuristic, not "
                     "calibrated -- not a result):\n" + optimal_path)
    return "\n".join(lines)

