# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Phase E -- the activity-theory actor / lever map (the scenario-space frame).

This is FRAMING, not a number cruncher (the plan is explicit about that). It
documents the structure the whole engine rests on: who the actors are, what each
optimizes, which lever each can pull, and -- the load-bearing idea from activity
theory -- where the *contradictions* are, because contradictions are what drive
the system to change (and what each scenario lever tries to resolve).

We model the MA money game as an Engestrom activity system
    SUBJECT             CMS / the regulator (sets the rules, pursues the object)
    OBJECT              efficient, adequate Medicare coverage (the motive)
    TOOLS               the levers: coding adjustment, audit/RADV, benchmark
                        policy, site-neutral payment
    RULES               statute (5.9% coding floor, RADV rule, benchmark formula)
    COMMUNITY           plans, providers, beneficiaries
    DIVISION OF LABOR   risk coding (plan), care delivery (provider)

and run the categorical ``ContradictionDetector`` over it. The central
contradiction is grounded in the engine's real number: the plan pursues
exchange-value (revenue via coding) while the program pursues use-value
(coverage), and the size of that misalignment is set to the measured overpayment
ratio -- so the map is data-connected, not a static diagram.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from categorical.activity_system import (
    ActivitySystem, ActivityComponent, MorphismClass, ContradictionDetector,
)


# Who controls which lever (the scenario space: who can pull what).
LEVER_OWNERS: Dict[str, str] = {
    "coding_adjustment": "CMS (statutory)",
    "audit_rate": "CMS / RADV",
    "radv_penalty": "CMS / courts",
    "benchmark_policy": "CMS / Congress",
    "site_neutral": "CMS / Congress",
    "coding_intensity": "plan (best response)",
    "care_setting": "provider (best response)",
}

# What each actor optimizes (the divergence that creates the contradictions).
ACTOR_OBJECTIVES: Dict[str, str] = {
    "CMS": "efficient, adequate coverage at least federal cost (use-value)",
    "plan": "capitated revenue minus care cost and clawback (exchange-value)",
    "provider": "service revenue (favors higher-paid care settings)",
    "beneficiary": "low premiums + rich supplemental benefits (rebate-funded)",
}


@dataclass
class ActorMap:
    system: ActivitySystem
    contradictions: list
    overpayment_ratio: float


def build_activity_system(overpayment_ratio: float = 0.20) -> ActivitySystem:
    """The MA money game as an activity system, with the plan/program
    misalignment grounded in the measured overpayment ratio."""
    s = ActivitySystem("medicare_advantage_money_game")

    s.add_component("CMS", ActivityComponent.SUBJECT)
    s.add_component("efficient_coverage", ActivityComponent.OBJECT)
    for tool in ("coding_adjustment", "audit", "benchmark_policy", "site_neutral"):
        s.add_component(tool, ActivityComponent.TOOL)
    s.add_component("statute", ActivityComponent.RULE)
    for member in ("plan", "provider", "beneficiary"):
        s.add_component(member, ActivityComponent.COMMUNITY)
    s.add_component("risk_coding", ActivityComponent.DIVISION_OF_LABOR)
    s.add_component("care_delivery", ActivityComponent.DIVISION_OF_LABOR)

    # CMS pursues the object directly (the intent: full alignment == 1.0).
    s.add_morphism("CMS", "efficient_coverage", MorphismClass.PRODUCTION, 1.0)

    # Each lever is a tool mediating CMS -> object; its weight is how aligned
    # the lever's USE is with the program (CMS wields it) ...
    for tool in ("coding_adjustment", "audit", "benchmark_policy", "site_neutral"):
        s.add_morphism("CMS", tool, MorphismClass.PRODUCTION, 0.9)
    # ... and how much of the object that lever actually delivers. The shortfall
    # vs CMS's direct intent is the contradiction the lever leaves on the table.
    s.add_morphism("coding_adjustment", "efficient_coverage", MorphismClass.PRODUCTION, 0.85)
    s.add_morphism("audit", "efficient_coverage", MorphismClass.PRODUCTION, 0.55)
    s.add_morphism("benchmark_policy", "efficient_coverage", MorphismClass.PRODUCTION, 0.80)
    s.add_morphism("site_neutral", "efficient_coverage", MorphismClass.PRODUCTION, 0.70)

    # The community's alignment with efficient coverage DIVERGES -- the primary
    # contradiction. The plan's exchange-value motive pulls it away by exactly
    # the measured overpayment ratio; providers favor costly settings; the
    # beneficiary is well-aligned on coverage but pulled by rebate-funded perks.
    s.add_morphism("plan", "efficient_coverage", MorphismClass.DISTRIBUTION,
                   max(0.0, 1.0 - overpayment_ratio))
    s.add_morphism("provider", "efficient_coverage", MorphismClass.DISTRIBUTION, 0.6)
    s.add_morphism("beneficiary", "efficient_coverage", MorphismClass.DISTRIBUTION, 0.9)

    # Rules regulate the community; labor distributes the object.
    s.add_morphism("statute", "plan", MorphismClass.REGULATION, 0.7)
    s.add_morphism("risk_coding", "efficient_coverage", MorphismClass.DISTRIBUTION, 0.6)
    s.add_morphism("care_delivery", "efficient_coverage", MorphismClass.DISTRIBUTION, 0.7)
    return s


def build_actor_map(overpayment_ratio: float = 0.20) -> ActorMap:
    s = build_activity_system(overpayment_ratio)
    contradictions = ContradictionDetector().detect_all(s)
    return ActorMap(system=s, contradictions=contradictions,
                    overpayment_ratio=overpayment_ratio)


def summarize_actor_map(amap: ActorMap) -> str:
    lines = ["Activity-theory actor / lever map -- the MA money game (frame, "
             "not a calculator)", "=" * 78]
    lines.append("  actors and what each optimizes:")
    for actor, obj in ACTOR_OBJECTIVES.items():
        lines.append(f"    {actor:<12} {obj}")
    lines.append("")
    lines.append("  levers and who can pull them:")
    for lever, owner in LEVER_OWNERS.items():
        lines.append(f"    {lever:<18} <- {owner}")
    lines.append("")
    summ = amap.system.summary()
    lines.append(f"  system: {summ['num_components']} components, "
                 f"{summ['num_morphisms']} morphisms; "
                 f"overpayment ratio grounding the plan<->program gap: "
                 f"{amap.overpayment_ratio:.0%}")
    lines.append("")
    lines.append(f"  contradictions detected ({len(amap.contradictions)}) -- "
                 "where the system is under tension\n  (activity theory: "
                 "contradictions are what drive change; the levers target them):")
    if not amap.contradictions:
        lines.append("    (none above threshold)")
    for c in sorted(amap.contradictions, key=lambda x: -x.tension):
        comps = " ".join(c.components_involved)
        lines.append(f"    [L{c.level} tension={c.tension:.2f}] {comps}")
        lines.append(f"        {c.description}")
    lines.append("-" * 78)
    lines.append("  Read it as the scenario space: a reform is a move by an actor "
                 "on a lever to\n  relax a contradiction. The numeric engine "
                 "(scenario/propagation/chain) then\n  computes how the community "
                 "re-optimizes and what it costs.")
    return "\n".join(lines)
