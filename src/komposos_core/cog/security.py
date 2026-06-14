# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-KOMPOSOS-IV-Commercial
# Copyright (c) 2024-2026 James Ray Hawkins
#
# This file is dual-licensed. You may use it under either:
# 1. Apache License 2.0 (see LICENSE file), OR
# 2. KOMPOSOS-IV Commercial License (see LICENSE-COMMERCIAL file)

"""
COG Security — Code security analysis via knowledge graph verification.

Security flaws are graph properties:
  - SQL injection = path from data_source to sink without sanitizer
  - Broken auth = exposed component without auth_check guard
  - Privilege escalation = transitive trust chain bypassing auth

Uses the existing 5-tier verification engine:
  - Tier 1 (Composition): taint propagation via path finding
  - Tier 2 (Sheaf): sanitizer coherence across overlapping flows
  - Tier 3 (Dual Engine): HOLLOW = vulnerability candidate
  - Tier 4 (Topology): circular auth dependencies via Betti numbers
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from data.store import KomposOSStore

from .schema import (
    CogConcept, CogRelation, CogClaim, CheckResult,
    ConceptType, RelationType, VerificationStatus,
)
from .engine import CogEngine

logger = logging.getLogger(__name__)

# OWASP Top 10 mapping for violations
OWASP_MAP = {
    "taint_flow": "A03:2021 Injection",
    "missing_auth": "A01:2021 Broken Access Control",
    "trust_boundary": "A04:2021 Insecure Design",
    "privilege_escalation": "A01:2021 Broken Access Control",
    "contradictory_trust": "A04:2021 Insecure Design",
    "circular_auth": "A01:2021 Broken Access Control",
    # Supply chain
    "unaudited_path": "A03:2025 Software Supply Chain Failures",
    "cve_exposure": "A03:2025 Software Supply Chain Failures",
    "concentration_risk": "A03:2025 Software Supply Chain Failures",
    "diamond_dependency": "A03:2025 Software Supply Chain Failures",
    "dead_dependency": "A03:2025 Software Supply Chain Failures",
    "stale_dependency": "A03:2025 Software Supply Chain Failures",
    "dev_dependency_cve": "A03:2025 Software Supply Chain Failures",
    "unmaintained_critical_path": "A03:2025 Software Supply Chain Failures",
    "vex_contradiction": "A03:2025 Software Supply Chain Failures",
    "provenance_gap": "A03:2025 Software Supply Chain Failures",
}

ALL_RULES = [
    "taint_flow", "missing_auth", "trust_boundary",
    "privilege_escalation", "contradictory_trust", "circular_auth",
    "unaudited_path", "cve_exposure", "concentration_risk",
    "diamond_dependency", "dead_dependency", "stale_dependency",
    "dev_dependency_cve",
    "unmaintained_critical_path", "vex_contradiction", "provenance_gap",
]

SUPPLY_CHAIN_RULES = {
    "unaudited_path", "cve_exposure", "concentration_risk",
    "diamond_dependency", "dead_dependency", "stale_dependency",
    "dev_dependency_cve",
    "unmaintained_critical_path", "vex_contradiction", "provenance_gap",
}


@dataclass
class SecurityViolation:
    """A security flaw detected in the knowledge graph."""
    rule: str
    severity: str  # critical, high, medium, low
    source: str
    sink: str
    path: List[str]
    explanation: str
    owasp: Optional[str] = None
    check_status: Optional[str] = None


class SecurityEngine:
    """
    Code security analysis engine built on CogEngine.

    Provides pre-built security rules that query the knowledge graph
    for vulnerability patterns. Each rule uses the existing tiered
    verification (composition, dual engine, topology).
    """

    def __init__(self, engine: CogEngine):
        self.engine = engine
        self.store = engine.store

    # ================================================================
    # Public API
    # ================================================================

    def scan(
        self,
        rules: Optional[List[str]] = None,
        scope: Optional[List[str]] = None,
        depth: int = 1,
    ) -> List[SecurityViolation]:
        """
        Run security rules against the knowledge graph.

        Args:
            rules: List of rule names to run (None = all)
            scope: Limit scan to these concepts (None = entire graph)
            depth: Verification tier for checks (0-4)
        """
        active_rules = rules or ALL_RULES
        violations: List[SecurityViolation] = []

        rule_funcs = {
            "taint_flow": self._rule_taint_flow,
            "missing_auth": self._rule_missing_auth,
            "trust_boundary": self._rule_trust_boundary,
            "privilege_escalation": self._rule_privilege_escalation,
            "contradictory_trust": self._rule_contradictory_trust,
            "circular_auth": self._rule_circular_auth,
        }

        # Delegate supply chain rules to SupplyChainEngine
        sc_active = [r for r in active_rules if r in SUPPLY_CHAIN_RULES]
        if sc_active:
            try:
                from .supply_chain import SupplyChainEngine
                sc = SupplyChainEngine(self.engine)
                for rule_name in sc_active:
                    violations.extend(sc.run_rule(rule_name, scope, depth))
            except Exception as e:
                logger.warning(f"Supply chain rules failed: {e}")

        for rule_name in active_rules:
            if rule_name in SUPPLY_CHAIN_RULES:
                continue  # Already handled above
            func = rule_funcs.get(rule_name)
            if func:
                try:
                    results = func(scope, depth)
                    violations.extend(results)
                except Exception as e:
                    logger.warning(f"Security rule {rule_name} failed: {e}")

        return violations

    def taint_analysis(
        self, source: Optional[str] = None
    ) -> List[SecurityViolation]:
        """Find all taint flows from a specific source (or all sources)."""
        if source:
            scope = [source]
        else:
            scope = None
        return self._rule_taint_flow(scope, depth=1)

    def model_from_dict(self, model: dict) -> dict:
        """
        Bulk assert a security threat model.

        Expected keys:
            sources: List[str] — untrusted data sources
            sinks: List[str] — sensitive sinks
            sanitizers: Dict[str, str] — {sanitizer_name: sink_it_protects}
            auth_checks: Dict[str, List[str]] — {check_name: [guarded_components]}
            components: List[str] — modules/services/functions
            boundaries: List[str] — trust boundaries
            flows: List[List[str]] — data flow chains [[a, b, c], ...]
        """
        stats = {"concepts": 0, "relations": 0}

        # Assert sources
        for name in model.get("sources", []):
            self.engine.assert_knowledge(CogConcept(
                name=name, concept_type=ConceptType.DATA_SOURCE,
                description="Untrusted data source",
            ))
            stats["concepts"] += 1

        # Assert sinks
        for name in model.get("sinks", []):
            self.engine.assert_knowledge(CogConcept(
                name=name, concept_type=ConceptType.SINK,
                description="Sensitive sink",
            ))
            stats["concepts"] += 1

        # Assert sanitizers with sanitizes relations
        for san_name, sink_name in model.get("sanitizers", {}).items():
            self.engine.assert_knowledge(CogConcept(
                name=san_name, concept_type=ConceptType.SANITIZER,
                description=f"Sanitizer for {sink_name}",
            ))
            stats["concepts"] += 1
            self.engine.assert_knowledge(CogRelation(
                source=san_name, target=sink_name,
                relation_type=RelationType.SANITIZES,
                confidence=0.9,
            ))
            stats["relations"] += 1

        # Assert auth checks with guards relations
        for check_name, guarded in model.get("auth_checks", {}).items():
            self.engine.assert_knowledge(CogConcept(
                name=check_name, concept_type=ConceptType.AUTH_CHECK,
                description="Authentication/authorization gate",
            ))
            stats["concepts"] += 1
            for target in guarded:
                self.engine.assert_knowledge(CogRelation(
                    source=check_name, target=target,
                    relation_type=RelationType.GUARDS,
                    confidence=0.9,
                ))
                stats["relations"] += 1

        # Assert components
        for name in model.get("components", []):
            self.engine.assert_knowledge(CogConcept(
                name=name, concept_type=ConceptType.COMPONENT,
            ))
            stats["concepts"] += 1

        # Assert trust boundaries
        for name in model.get("boundaries", []):
            self.engine.assert_knowledge(CogConcept(
                name=name, concept_type=ConceptType.TRUST_BOUNDARY,
            ))
            stats["concepts"] += 1

        # Assert flows as flows_to chains
        for flow_chain in model.get("flows", []):
            for i in range(len(flow_chain) - 1):
                self.engine.assert_knowledge(CogRelation(
                    source=flow_chain[i], target=flow_chain[i + 1],
                    relation_type=RelationType.FLOWS_TO,
                    confidence=0.85,
                ))
                stats["relations"] += 1

        return stats

    # ================================================================
    # Security Rules
    # ================================================================

    def _rule_taint_flow(
        self, scope: Optional[List[str]], depth: int
    ) -> List[SecurityViolation]:
        """
        Rule 1: Taint Flow (Injection Flaws)

        Find paths from data_source to sink without a sanitizer in between.
        OWASP A03 (Injection), A07 (XSS).
        """
        violations = []
        sources = self._get_concepts_by_type("data_source", scope)
        sinks = self._get_concepts_by_type("sink")

        # Build set of (sanitizer, sink) pairs
        sanitizer_coverage = self._get_sanitizer_coverage()

        for src in sources:
            for sink in sinks:
                paths = self.store.find_paths(src, sink, max_length=5)
                if not paths:
                    continue

                for path in paths:
                    nodes = self._extract_path_nodes(path)
                    # Check if any sanitizer for this sink is in the path
                    protected = False
                    for node in nodes:
                        if node in sanitizer_coverage.get(sink, set()):
                            protected = True
                            break

                    if not protected:
                        violations.append(SecurityViolation(
                            rule="taint_flow",
                            severity="critical",
                            source=src,
                            sink=sink,
                            path=nodes,
                            explanation=(
                                f"Unsanitized data flow: {' -> '.join(nodes)}. "
                                f"No sanitizer protects {sink} on this path."
                            ),
                            owasp=OWASP_MAP["taint_flow"],
                        ))
                        break  # One violation per (source, sink) pair

        return violations

    def _rule_missing_auth(
        self, scope: Optional[List[str]], depth: int
    ) -> List[SecurityViolation]:
        """
        Rule 2: Missing Authentication

        Find exposed components without an auth_check guard.
        OWASP A01 (Broken Access Control).
        """
        violations = []
        components = self._get_all_concepts()

        # Find components that are exposed
        for comp in components:
            incoming = self.store.get_morphisms_to(comp)
            is_exposed = any(m.name == "exposes" for m in incoming)

            if not is_exposed:
                continue

            # Check if any auth_check guards this component
            has_guard = any(m.name == "guards" for m in incoming)

            if not has_guard:
                exposer = next(
                    (m.source_name for m in incoming if m.name == "exposes"), "unknown"
                )
                violations.append(SecurityViolation(
                    rule="missing_auth",
                    severity="high",
                    source=exposer,
                    sink=comp,
                    path=[exposer, comp],
                    explanation=(
                        f"{comp} is exposed by {exposer} but has no auth_check guard."
                    ),
                    owasp=OWASP_MAP["missing_auth"],
                ))

        return violations

    def _rule_trust_boundary(
        self, scope: Optional[List[str]], depth: int
    ) -> List[SecurityViolation]:
        """
        Rule 3: Trust Boundary Crossing

        Find flows_to edges that connect concepts on different sides
        of a trust_boundary without auth/sanitization at the crossing.
        OWASP A04 (Insecure Design).
        """
        violations = []
        boundaries = self._get_concepts_by_type("trust_boundary")

        for boundary in boundaries:
            # A boundary has incoming and outgoing flows
            incoming = self.store.get_morphisms_to(boundary)
            outgoing = self.store.get_morphisms_from(boundary)

            incoming_flows = [m for m in incoming if m.name == "flows_to"]
            outgoing_flows = [m for m in outgoing if m.name == "flows_to"]

            # For each pair crossing the boundary
            for inf in incoming_flows:
                for outf in outgoing_flows:
                    # Check if there's auth/sanitization at the boundary
                    boundary_incoming = self.store.get_morphisms_to(boundary)
                    has_guard = any(m.name == "guards" for m in boundary_incoming)
                    has_sanitizer = any(m.name == "sanitizes" for m in boundary_incoming)

                    if not has_guard and not has_sanitizer:
                        violations.append(SecurityViolation(
                            rule="trust_boundary",
                            severity="high",
                            source=inf.source_name,
                            sink=outf.target_name,
                            path=[inf.source_name, boundary, outf.target_name],
                            explanation=(
                                f"Data flows across trust boundary '{boundary}' "
                                f"from {inf.source_name} to {outf.target_name} "
                                f"without auth check or sanitization."
                            ),
                            owasp=OWASP_MAP["trust_boundary"],
                        ))

        return violations

    def _rule_privilege_escalation(
        self, scope: Optional[List[str]], depth: int
    ) -> List[SecurityViolation]:
        """
        Rule 4: Privilege Escalation Chain

        Find transitive trusts chains > 2 hops. Each hop is implicit
        trust delegation — long chains indicate potential escalation.
        """
        violations = []
        all_concepts = self._get_all_concepts()

        seen_chains: Set[tuple] = set()
        for concept in all_concepts:
            chains = self._follow_trust_chain(concept, max_depth=5)
            for chain in chains:
                # Deduplicate by sorted endpoints to avoid reporting
                # sub-chains of already-reported chains
                key = tuple(chain)
                if key in seen_chains:
                    continue
                seen_chains.add(key)
                violations.append(SecurityViolation(
                    rule="privilege_escalation",
                    severity="medium",
                    source=chain[0],
                    sink=chain[-1],
                    path=chain,
                    explanation=(
                        f"Transitive trust chain ({len(chain)} hops): "
                        f"{' -> '.join(chain)}. "
                        f"Each hop delegates trust without re-verification."
                    ),
                    owasp=OWASP_MAP["privilege_escalation"],
                ))

        return violations

    def _rule_contradictory_trust(
        self, scope: Optional[List[str]], depth: int
    ) -> List[SecurityViolation]:
        """
        Rule 5: Contradictory Trust

        Detect contradictions:
        - A trusts B AND A sanitizes input from B (why sanitize trusted input?)
        - A guards B AND data flows directly to B bypassing A
        """
        violations = []
        all_concepts = self._get_all_concepts()

        for concept in all_concepts:
            outgoing = self.store.get_morphisms_from(concept)
            targets_by_rel: Dict[str, Set[str]] = {}
            for m in outgoing:
                targets_by_rel.setdefault(m.name, set()).add(m.target_name)

            # Check: trusts X AND sanitizes X's output
            trusted = targets_by_rel.get("trusts", set())
            sanitized_targets = set()
            for m in outgoing:
                if m.name == "sanitizes":
                    # Find what flows from the sanitized thing
                    sanitized_targets.add(m.target_name)

            # Check incoming: who flows into this concept?
            incoming = self.store.get_morphisms_to(concept)
            for m in incoming:
                if m.name == "flows_to" and m.source_name in trusted:
                    # concept trusts the source, but source also flows through sanitizer
                    san_out = self.store.get_morphisms_from(concept)
                    for s in san_out:
                        if s.name == "sanitizes":
                            violations.append(SecurityViolation(
                                rule="contradictory_trust",
                                severity="medium",
                                source=concept,
                                sink=m.source_name,
                                path=[concept, m.source_name],
                                explanation=(
                                    f"{concept} trusts {m.source_name} but also "
                                    f"sanitizes its output — contradictory security posture."
                                ),
                                owasp=OWASP_MAP["contradictory_trust"],
                            ))

        return violations

    def _rule_circular_auth(
        self, scope: Optional[List[str]], depth: int
    ) -> List[SecurityViolation]:
        """
        Rule 6: Circular Dependencies in Auth

        Find cycles in trusts/guards relationships.
        A trusts B trusts C trusts A = circular delegation.
        """
        violations = []
        all_concepts = self._get_all_concepts()
        visited_cycles: Set[tuple] = set()

        for start in all_concepts:
            cycles = self._find_cycles(start, ["trusts", "guards"], max_depth=5)
            for cycle in cycles:
                key = tuple(sorted(cycle))
                if key not in visited_cycles:
                    visited_cycles.add(key)
                    violations.append(SecurityViolation(
                        rule="circular_auth",
                        severity="medium",
                        source=cycle[0],
                        sink=cycle[-1],
                        path=cycle,
                        explanation=(
                            f"Circular auth/trust dependency: {' -> '.join(cycle)}. "
                            f"Circular trust can be exploited for auth bypass."
                        ),
                        owasp=OWASP_MAP["circular_auth"],
                    ))

        return violations

    # ================================================================
    # Helpers
    # ================================================================

    def _get_concepts_by_type(
        self, type_name: str, scope: Optional[List[str]] = None
    ) -> List[str]:
        """Get all concept names of a given type."""
        objects = self.store.list_objects(limit=10000)
        result = [
            o.name for o in objects
            if o.type_name == type_name
        ]
        if scope:
            result = [r for r in result if r in scope]
        return result

    def _get_all_concepts(self) -> List[str]:
        """Get all concept names."""
        objects = self.store.list_objects(limit=10000)
        return [o.name for o in objects]

    def _get_sanitizer_coverage(self) -> Dict[str, Set[str]]:
        """
        Build a map: sink_name -> set of sanitizer names that protect it.
        """
        coverage: Dict[str, Set[str]] = {}
        sanitizers = self._get_concepts_by_type("sanitizer")
        for san in sanitizers:
            outgoing = self.store.get_morphisms_from(san)
            for m in outgoing:
                if m.name == "sanitizes":
                    coverage.setdefault(m.target_name, set()).add(san)
        return coverage

    def _extract_path_nodes(self, stored_path) -> List[str]:
        """Extract node names from a StoredPath's morphism_ids."""
        nodes = []
        for mid in stored_path.morphism_ids:
            # morphism_ids are like "relation:source->target"
            if "->" in mid:
                parts = mid.split("->")
                source_part = parts[0].split(":")[-1] if ":" in parts[0] else parts[0]
                target_part = parts[1]
                if not nodes:
                    nodes.append(source_part)
                nodes.append(target_part)
        return nodes if nodes else [stored_path.morphism_ids[0]] if stored_path.morphism_ids else []

    def _follow_trust_chain(self, start: str, max_depth: int = 5) -> List[List[str]]:
        """BFS along trusts edges, return ALL chains > 2 hops from start."""
        chains: List[List[str]] = []

        def dfs(node: str, path: List[str], visited: Set[str]):
            if len(path) > max_depth:
                return
            outgoing = self.store.get_morphisms_from(node)
            trust_targets = [
                m.target_name for m in outgoing
                if m.name == "trusts" and m.target_name not in visited
            ]
            if not trust_targets:
                # End of chain — record if long enough
                if len(path) > 2:
                    chains.append(list(path))
                return
            for target in trust_targets:
                visited.add(target)
                path.append(target)
                dfs(target, path, visited)
                path.pop()
                visited.discard(target)

        dfs(start, [start], {start})
        return chains

    def _find_cycles(
        self, start: str, relation_names: List[str], max_depth: int = 5
    ) -> List[List[str]]:
        """Find cycles starting from start, following given relation types."""
        cycles = []

        def dfs(node: str, path: List[str], visited: Set[str]):
            if len(path) > max_depth:
                return
            outgoing = self.store.get_morphisms_from(node)
            for m in outgoing:
                if m.name not in relation_names:
                    continue
                if m.target_name == start and len(path) > 1:
                    cycles.append(path + [start])
                elif m.target_name not in visited:
                    visited.add(m.target_name)
                    dfs(m.target_name, path + [m.target_name], visited)
                    visited.discard(m.target_name)

        dfs(start, [start], {start})
        return cycles
