# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-KOMPOSOS-IV-Commercial
# Copyright (c) 2024-2026 James Ray Hawkins
#
# This file is dual-licensed. You may use it under either:
# 1. Apache License 2.0 (see LICENSE file), OR
# 2. KOMPOSOS-IV Commercial License (see LICENSE-COMMERCIAL file)

"""
KOMPOSOS-IV-COG MCP Server

Exposes the cognitive co-processor as MCP tools for AI agents.

Tools:
  cog_assert               — Add a concept or relation to the knowledge graph
  cog_assert_batch         — Batch-assert multiple concepts/relations in one call
  cog_check                — Verify a claim (AGREE/ORPHAN/HOLLOW/REJECT/PARTIAL/PENDING)
  cog_query                — Find paths, relationships, or neighbors
  cog_coherence            — Check multi-source consistency
  cog_energy               — Graph resistance score for a claim
  cog_explain              — Detailed explanation of a check result
  cog_threat_model         — Bulk-assert a security threat model
  cog_scan                 — Scan for security vulnerabilities (16 rules)

Run:
  python -m cog.server
"""

from __future__ import annotations

import json
import sys
import os
from typing import Optional

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP

from .schema import (
    CogConcept, CogRelation, CogClaim,
    ConceptType, RelationType,
)
from .session import CogSession
from .engine import CogEngine
from .security import SecurityEngine
from .serializers import cog_json_default

# Singleton session and engine per server process
_session: Optional[CogSession] = None
_engine: Optional[CogEngine] = None
_security: Optional[SecurityEngine] = None


def _get_engine() -> CogEngine:
    """Get or create the singleton engine. Uses persistent DB in project root."""
    global _session, _engine
    if _engine is None:
        # Persist the graph so knowledge survives across conversations
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "cog_store.db",
        )
        _session = CogSession(db_path=db_path)
        _engine = CogEngine(_session)
    return _engine


def _get_security() -> SecurityEngine:
    """Get or create the singleton security engine."""
    global _security
    if _security is None:
        _security = SecurityEngine(_get_engine())
    return _security


mcp = FastMCP(
    "komposos-cog",
    instructions="KOMPOSOS-IV Cognitive Co-processor: category-theoretic knowledge layer for AI agents",
)


@mcp.tool()
def cog_assert(
    name: str,
    type: str = "concept",
    target: Optional[str] = None,
    relation: Optional[str] = None,
    confidence: float = 0.7,
    description: str = "",
) -> str:
    """Add a concept or relation to the knowledge graph.

    To add a concept: provide name and type.
    To add a relation: provide name (as source), target, and relation.

    Concept types: concept, claim, evidence, rule, context, goal,
                   data_source, sink, sanitizer, auth_check, trust_boundary, component
    Relation types: supports, contradicts, entails, requires, similar_to,
                    part_of, causes, precedes, instantiates, refines,
                    flows_to, sanitizes, guards, trusts, exposes, mitigates,
                    depends_on

    Args:
        name: Concept name, or source of the relation
        type: Object type (default: concept)
        target: Target concept (required for relations)
        relation: Relation type (required for relations)
        confidence: Confidence 0.0-1.0 (default: 0.7)
        description: Optional description or evidence
    """
    engine = _get_engine()

    if target and relation:
        try:
            rel_type = RelationType(relation)
        except ValueError:
            return json.dumps({"error": f"Unknown relation type: {relation}. Valid: {[r.value for r in RelationType]}"})

        cog_relation = CogRelation(
            source=name,
            target=target,
            relation_type=rel_type,
            confidence=confidence,
            evidence=description,
        )
        result = engine.assert_knowledge(cog_relation)
    else:
        try:
            concept_type = ConceptType(type)
        except ValueError:
            concept_type = ConceptType.CONCEPT

        cog_concept = CogConcept(
            name=name,
            concept_type=concept_type,
            description=description,
        )
        result = engine.assert_knowledge(cog_concept)

    return json.dumps(result, indent=2, default=cog_json_default)


@mcp.tool()
def cog_check(
    source: str,
    target: str,
    relation: str = "entails",
    confidence: float = 0.5,
    depth: Optional[int] = None,
) -> str:
    """Verify a claim using tiered mathematical verification.

    Returns a status: agree, orphan, hollow, reject, partial, or pending.

    Tiers (auto-selected based on energy, or specify with depth):
      0: Graph lookup (~1ms)
      1: Composition + paths (~10ms)
      2-4: Higher tiers (Phase 2+)

    Args:
        source: Source concept name
        target: Target concept name
        relation: Relation to check (default: entails)
        confidence: Expected confidence 0.0-1.0
        depth: Explicit tier (0-4), or omit for auto-routing
    """
    engine = _get_engine()

    claim = CogClaim(
        source=source,
        target=target,
        relation=relation,
        confidence=confidence,
    )

    result = engine.check_claim(claim, depth=depth)

    return json.dumps({
        "status": result.status.value,
        "tier_reached": result.tier_reached,
        "confidence": result.confidence,
        "energy": result.energy,
        "explanation": result.explanation,
        "supporting_paths": result.supporting_paths,
        "contradictions": result.contradictions,
        "dual_result": result.dual_result,
        "topology": result.topology,
        "computation_time_ms": round(result.computation_time_ms, 2),
    }, indent=2, default=cog_json_default)


@mcp.tool()
def cog_query(
    source: str,
    target: Optional[str] = None,
    relation: Optional[str] = None,
    max_results: int = 20,
) -> str:
    """Find paths, relationships, or neighbors in the knowledge graph.

    Three modes:
      1. source + target: Find paths between them
      2. source + relation: Find all targets via that relation
      3. source only: Full neighborhood (incoming + outgoing)

    Args:
        source: Starting concept
        target: End concept (optional)
        relation: Filter by relation type (optional)
        max_results: Max results (default: 20)
    """
    engine = _get_engine()
    result = engine.query(source, target, relation, max_results)
    return json.dumps(result, indent=2, default=cog_json_default)


@mcp.tool()
def cog_coherence(concepts: str) -> str:
    """Check whether a set of concepts is mutually consistent.

    Detects contradictions and confidence inconsistencies between
    all morphisms connecting the given concepts.

    Args:
        concepts: Comma-separated list of concept names
    """
    engine = _get_engine()
    concept_list = [c.strip() for c in concepts.split(",") if c.strip()]

    if len(concept_list) < 2:
        return json.dumps({"error": "Need at least 2 concepts"})

    result = engine.check_coherence(concept_list)

    return json.dumps({
        "is_coherent": result.is_coherent,
        "coherence_score": result.coherence_score,
        "violations": result.violations,
        "explanation": result.explanation,
    }, indent=2, default=cog_json_default)


@mcp.tool()
def cog_energy(
    source: str,
    target: str,
    relation: str = "entails",
    confidence: float = 0.5,
) -> str:
    """Compute how much the graph resists a claim.

    Returns energy (0 = fits naturally, 1+ = high resistance) with
    a breakdown of 5 components: novelty, path_resistance,
    contradiction, confidence_gap, type_mismatch.

    Args:
        source: Source concept
        target: Target concept
        relation: Relation type (default: entails)
        confidence: Proposed confidence 0.0-1.0
    """
    engine = _get_engine()
    claim = CogClaim(source=source, target=target, relation=relation, confidence=confidence)
    result = engine.compute_energy(claim)

    return json.dumps({
        "total_energy": result.total_energy,
        "components": result.components,
        "interpretation": result.interpretation,
    }, indent=2, default=cog_json_default)


@mcp.tool()
def cog_explain(
    source: str,
    target: str,
    relation: str = "entails",
    confidence: float = 0.5,
) -> str:
    """Detailed explanation of why a check returned what it did.

    Runs the full pipeline and returns verbose output: energy breakdown,
    tier routing decision, verification results, and graph context.

    Args:
        source: Source concept
        target: Target concept
        relation: Relation type (default: entails)
        confidence: Proposed confidence 0.0-1.0
    """
    engine = _get_engine()
    claim = CogClaim(source=source, target=target, relation=relation, confidence=confidence)
    result = engine.explain(claim)
    return json.dumps(result, indent=2, default=cog_json_default)


@mcp.tool()
def cog_threat_model(model: str) -> str:
    """Bulk-assert a security threat model into the knowledge graph.

    Accepts a JSON string describing data flows, trust boundaries,
    sanitizers, and auth checks. Creates all concepts and relations
    in one call instead of many individual cog_assert calls.

    Concept types used: data_source, sink, sanitizer, auth_check,
    trust_boundary, component.
    Relation types used: flows_to, sanitizes, guards.

    Example model JSON:
    {
        "sources": ["user_input", "file_upload"],
        "sinks": ["sql_query", "shell_exec", "html_render"],
        "sanitizers": {"param_binding": "sql_query", "html_escape": "html_render"},
        "auth_checks": {"jwt_verify": ["admin_panel", "user_api"]},
        "components": ["api_handler", "parser"],
        "boundaries": ["network_edge"],
        "flows": [
            ["user_input", "api_handler", "sql_query"],
            ["file_upload", "parser", "html_render"]
        ]
    }

    Args:
        model: JSON string with sources, sinks, sanitizers, auth_checks,
               components, boundaries, and flows
    """
    security = _get_security()

    try:
        model_dict = json.loads(model)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON: {e}"})

    stats = security.model_from_dict(model_dict)
    return json.dumps({
        "status": "ok",
        "concepts_added": stats["concepts"],
        "relations_added": stats["relations"],
    }, indent=2)


@mcp.tool()
def cog_scan(
    rules: str = "all",
    scope: str = "",
    depth: int = 1,
) -> str:
    """Scan the knowledge graph for security vulnerabilities.

    Runs pre-built security rules and returns violations with
    severity, OWASP category, affected paths, and explanations.

    Available rules:
      taint_flow          — Unsanitized data flow from source to sink (OWASP A03)
      missing_auth        — Exposed component without auth guard (OWASP A01)
      trust_boundary      — Data crossing boundary without protection (OWASP A04)
      privilege_escalation — Transitive trust chain > 2 hops (OWASP A01)
      contradictory_trust — Conflicting trust/sanitize on same target (OWASP A04)
      circular_auth       — Circular trust/guard dependencies (OWASP A01)
      unaudited_path      — HOLLOW dependency paths (OWASP A03:2025)
      cve_exposure        — CVE-affected packages reachable from app (OWASP A03:2025)
      concentration_risk  — Hub dependencies (single points of failure)
      diamond_dependency  — Same package at different versions
      dead_dependency     — Declared but unreachable packages
      stale_dependency    — Unmaintained packages (>2 years)
      dev_dependency_cve  — CVEs in dev-only dependencies (lower severity)
      unmaintained_critical_path — Low Scorecard + hub dependency (cross-signal)
      vex_contradiction   — Conflicting VEX assessments for same CVE
      provenance_gap      — Hub packages with no signed releases

    Args:
        rules: Comma-separated rule names, or "all" (default: all)
        scope: Comma-separated concept names to limit scan (empty = full graph)
        depth: Verification tier for checks, 0-4 (default: 1)
    """
    security = _get_security()

    rule_list = None if rules == "all" else [r.strip() for r in rules.split(",")]
    scope_list = [s.strip() for s in scope.split(",") if s.strip()] or None

    violations = security.scan(rules=rule_list, scope=scope_list, depth=depth)

    return json.dumps({
        "violations_found": len(violations),
        "violations": [
            {
                "rule": v.rule,
                "severity": v.severity,
                "source": v.source,
                "sink": v.sink,
                "path": v.path,
                "explanation": v.explanation,
                "owasp": v.owasp,
            }
            for v in violations
        ],
    }, indent=2, default=cog_json_default)




@mcp.tool()
def cog_assert_batch(assertions: str) -> str:
    """Batch-assert multiple concepts and relations in one call.

    Accepts a JSON string with an "assertions" array. Each entry is either
    a concept (name + type) or a relation (name + target + relation).

    Example:
    {
      "assertions": [
        {"name": "A", "type": "concept", "description": "..."},
        {"name": "A", "target": "B", "relation": "requires", "confidence": 0.9},
        {"name": "C", "type": "component"}
      ]
    }

    Args:
        assertions: JSON string with an "assertions" array
    """
    engine = _get_engine()

    try:
        data = json.loads(assertions)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON: {e}"})

    items = data.get("assertions", data) if isinstance(data, dict) else data
    if not isinstance(items, list):
        return json.dumps({"error": "Expected a JSON array or object with 'assertions' key"})

    stats = {"concepts_added": 0, "relations_added": 0, "errors": []}

    for i, item in enumerate(items):
        try:
            name = item.get("name", "")
            target = item.get("target")
            relation = item.get("relation")
            confidence = item.get("confidence", 0.7)
            description = item.get("description", "")
            type_str = item.get("type", "concept")

            if not name:
                stats["errors"].append(f"Item {i}: missing 'name'")
                continue

            if target and relation:
                try:
                    rel_type = RelationType(relation)
                except ValueError:
                    stats["errors"].append(f"Item {i}: unknown relation '{relation}'")
                    continue

                engine.assert_knowledge(CogRelation(
                    source=name,
                    target=target,
                    relation_type=rel_type,
                    confidence=confidence,
                    evidence=description,
                ))
                stats["relations_added"] += 1
            else:
                try:
                    concept_type = ConceptType(type_str)
                except ValueError:
                    concept_type = ConceptType.CONCEPT

                engine.assert_knowledge(CogConcept(
                    name=name,
                    concept_type=concept_type,
                    description=description,
                ))
                stats["concepts_added"] += 1

        except Exception as e:
            stats["errors"].append(f"Item {i}: {e}")

    return json.dumps(stats, indent=2, default=cog_json_default)


def main():
    """Run the KOMPOSOS-IV-COG MCP server via stdio."""
    print("Starting KOMPOSOS-IV-COG MCP Server...", file=sys.stderr)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
