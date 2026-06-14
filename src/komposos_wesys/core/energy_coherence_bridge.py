# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-KOMPOSOS-IV-Commercial
# SPDX-FileCopyrightText: 2026 James Hawkins / Komposos-Labs

"""
Gray Coherence Bridge
=====================

Wires together the four existing systems that already partially cover
3-cell coherence, and adds the Gray-category formal certificate layer
on top:

    conjecture.py        →  proactive missing-edge discovery
    zfc_verifier.py      →  HOLLOW verdict = structurally plausible but
                            logically unsound = inefficiency candidate
    gray_coherence.py    →  formal 3-cell certificate for each gap
    learner.py           →  Bayesian feedback so detection improves

Data flow
---------

    ConjectureEngine.conjecture()
            │
            │  Conjecture (missing edge candidates)
            ▼
    OracleZFCBridge.verify_predictions()
            │
            │  DualResult — extract HOLLOW verdicts
            ▼
    GrayCategoryLayer.check_modification_coherence()
            │
            │  Modification — is_coherent=False + gap_type
            ▼
    CoherenceVulnerabilityMapper.classify()
            │
            │  EfficiencyViolation (vuln_class, severity,
            │                          MITRE id, proof, remediation)
            ▼
    OracleLearner.record_outcome()   ←── patch confirmed? feed back
            │
            ▼
    GridShield.report()  /  Orion event bus

Why HOLLOW verdicts map to vulnerabilities
------------------------------------------
A HOLLOW prediction means:
  - CAT says: this morphism is structurally plausible (high confidence)
  - ZFC says: this morphism is logically unsound (fails set-theoretic proof)

In software terms: a code path the type system would allow but that
violates its own invariants at runtime. That is the definition of a
memory-safety or logic inefficiency.

Gray 3-cell coherence gives the formal certificate: *which* interchange
law fails, and *why*. That certificate is directly patchable.

Integration
-----------
Drop alongside gray_coherence.py in komposos/core/.

Minimal usage:

    from komposos.core.gray_coherence_bridge import GridShield

    shield = GridShield(oracle, zfc_bridge, learner)
    report = shield.scan(top_k=100)
    shield.print_report(report)

Orion bridge:

    # In your CyberBridge or a new GrayCoherenceBridgePlugin:
    shield = GridShield(oracle, zfc_bridge, learner)
    agent.capabilities["gray.scan"] = shield.scan
    agent.capabilities["gray.continuous"] = shield.run_continuous
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

# ---------------------------------------------------------------------------
# Local imports — graceful degradation if any layer is missing
# ---------------------------------------------------------------------------

try:
    from oracle.conjecture import ConjectureEngine, Conjecture, ConjectureResult
    CONJECTURE_AVAILABLE = True
except ImportError:
    CONJECTURE_AVAILABLE = False

try:
    from oracle.zfc_verifier import OracleZFCBridge
    ZFC_AVAILABLE = True
except ImportError:
    ZFC_AVAILABLE = False

try:
    from oracle.learner import OracleLearner
    LEARNER_AVAILABLE = True
except ImportError:
    LEARNER_AVAILABLE = False

# Gray coherence — companion module
from .gray_coherence import (
    GrayCategoryLayer,
    CoherenceVulnerabilityMapper,
    CoherenceGapType,
    TwoCellProxy,
    EfficiencyViolation,
    Modification,
)

from oracle.prediction import Prediction, PredictionType


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class GapFinding:
    """
    One confirmed gap: a conjecture that is HOLLOW under ZFC
    and incoherent under Gray 3-cell checking.

    This is the unified output of all four layers.
    """
    # From conjecture layer
    conjecture_source: str
    conjecture_target: str
    conjecture_confidence: float
    conjecture_generators: List[str]   # which generators surfaced it

    # From ZFC layer
    zfc_verdict: str                   # "HOLLOW", "ORPHAN", "AGREE", "REJECT"
    zfc_confidence: float

    # From Gray coherence layer
    inefficiency: EfficiencyViolation

    # Computed
    combined_severity: float = 0.0     # geometric mean of zfc + gray severity

    def __post_init__(self):
        # Combined severity: weighted blend
        # ZFC hollowness × gray severity × conjecture confidence
        self.combined_severity = (
            self.inefficiency.severity
            * self.conjecture_confidence
            * (1.0 if self.zfc_verdict == "HOLLOW" else 0.7)
        )

    @property
    def is_critical(self) -> bool:
        return self.combined_severity >= 0.75

    @property
    def is_chainable(self) -> bool:
        return self.inefficiency.is_chainable

    def __repr__(self) -> str:
        return (
            f"GapFinding({self.conjecture_source} → {self.conjecture_target} "
            f"| {self.inefficiency.vuln_class} "
            f"| severity={self.combined_severity:.2f} "
            f"| zfc={self.zfc_verdict} "
            f"| chainable={self.is_chainable})"
        )


@dataclass
class ShieldReport:
    """
    Full output of one GridShield scan.

    Contains all GapFindings sorted by combined_severity,
    plus diagnostic breakdowns.
    """
    findings: List[GapFinding]
    scan_time_ms: float
    conjectures_evaluated: int
    hollow_count: int
    gray_gap_count: int

    # Breakdown by inefficiency class
    by_vuln_class: Dict[str, int] = field(default_factory=dict)
    # Breakdown by gap type
    by_gap_type: Dict[str, int] = field(default_factory=dict)

    @property
    def critical(self) -> List[GapFinding]:
        return [f for f in self.findings if f.is_critical]

    @property
    def chainable(self) -> List[GapFinding]:
        """
        The findings Mythos would chain.
        Patching any one of these breaks a potential chain.
        """
        return [f for f in self.findings if f.is_chainable]

    def summary(self) -> str:
        lines = [
            f"ShieldReport: {len(self.findings)} gaps "
            f"({len(self.critical)} critical, "
            f"{len(self.chainable)} chainable) "
            f"in {self.scan_time_ms:.0f}ms",
            f"  Conjectures evaluated : {self.conjectures_evaluated}",
            f"  HOLLOW verdicts       : {self.hollow_count}",
            f"  Gray gaps confirmed   : {self.gray_gap_count}",
        ]
        if self.by_vuln_class:
            lines.append("  By inefficiency class:")
            for cls, count in sorted(
                self.by_vuln_class.items(), key=lambda x: -x[1]
            ):
                lines.append(f"    {cls:<30} {count}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# HOLLOW → TwoCellProxy translation
# ---------------------------------------------------------------------------

def _hollow_to_twocell_pair(
    conjecture: Conjecture,
    hollow_predictions: List[Prediction],
) -> Tuple[TwoCellProxy, TwoCellProxy]:
    """
    Translate a HOLLOW conjecture into a pair of TwoCellProxy objects
    suitable for Gray coherence checking.

    A HOLLOW edge (src → tgt) means:
      - CAT sees a high-confidence structural path (alpha)
      - ZFC finds no logical support (beta — the logically-required path
        that should exist but whose composition breaks down)

    We model this as two parallel 2-cells:
      alpha = the CAT-plausible path (high confidence, from conjecture)
      beta  = the ZFC-required path  (low confidence — it's missing)

    The interchange failure between them is the inefficiency.
    """
    # alpha: the structurally plausible path CAT found
    top_pred = hollow_predictions[0] if hollow_predictions else None
    alpha = TwoCellProxy(
        source_morphism=conjecture.source,
        target_morphism=conjecture.target,
        label=f"cat_path_{conjecture.source}_{conjecture.target}",
        confidence=conjecture.top_confidence,
        # Privilege inferred from prediction type
        privilege_level=_infer_privilege(top_pred),
    )

    # beta: the logically-required path ZFC says should exist but doesn't
    # Low confidence because ZFC rejected it
    beta = TwoCellProxy(
        source_morphism=conjecture.source,
        target_morphism=conjecture.target,
        label=f"zfc_required_{conjecture.source}_{conjecture.target}",
        confidence=0.1,   # hollow — ZFC says no
        privilege_level=_infer_privilege(top_pred) + 1,  # ZFC path crosses boundary
    )

    return alpha, beta


def _infer_privilege(pred: Optional[Prediction]) -> int:
    """Heuristic privilege level from prediction type."""
    if pred is None:
        return 0
    pt = pred.prediction_type
    if pt in (PredictionType.CARTESIAN_LIFT, PredictionType.FIBER_PREDICTION):
        return 2   # fibration lifts cross containment boundaries
    if pt in (PredictionType.CURVATURE_BRIDGE,):
        return 1   # bridges between clusters = privilege boundary
    return 0


# ---------------------------------------------------------------------------
# Main bridge
# ---------------------------------------------------------------------------

class GridShield:
    """
    Pre-emptive Mythos defense layer.

    Combines:
      - ConjectureEngine  (proactive gap discovery)
      - OracleZFCBridge   (HOLLOW = vuln candidate)
      - GrayCategoryLayer (formal 3-cell certificate)
      - OracleLearner     (Bayesian improvement from patch feedback)

    The scan() method finds structural gaps that Mythos would exploit,
    maps them to inefficiency classes, and returns patchable reports.

    Continuous mode races Mythos to your own gaps.
    """

    def __init__(
        self,
        oracle,                              # CategoricalOracle
        zfc_bridge: Optional[OracleZFCBridge] = None,
        learner: Optional[OracleLearner] = None,
        scan_interval_seconds: float = 3600.0,
    ):
        self.oracle = oracle
        self.zfc_bridge = zfc_bridge         # None → graceful degradation
        self.learner = learner               # None → no Bayesian feedback
        self.scan_interval = scan_interval_seconds

        self.conjecture_engine = (
            ConjectureEngine(oracle) if CONJECTURE_AVAILABLE else None
        )
        self.gray_layer = GrayCategoryLayer()
        self.mapper = CoherenceVulnerabilityMapper()

        self._findings_history: List[GapFinding] = []

    # -----------------------------------------------------------------------
    # Primary API
    # -----------------------------------------------------------------------

    def scan(
        self,
        top_k: int = 100,
        min_confidence: float = 0.4,
        hollow_only: bool = True,
    ) -> ShieldReport:
        """
        Run one full pre-emptive scan.

        Steps:
          1. ConjectureEngine finds missing edges (proactive)
          2. OracleZFCBridge classifies each — extract HOLLOWs
          3. GrayCategoryLayer checks each HOLLOW for 3-cell coherence
          4. CoherenceVulnerabilityMapper maps gaps → CVE classes
          5. OracleLearner records outcomes for Bayesian updating

        Args:
            top_k:          Max conjectures to evaluate.
            min_confidence: Minimum conjecture confidence to consider.
            hollow_only:    If True, only process HOLLOW verdicts.
                            If False, also process ORPHAN verdicts
                            (logically forced but structurally missing).

        Returns:
            ShieldReport sorted by combined_severity.
        """
        start = time.time()

        # -- Step 1: conjecture -----------------------------------------------
        conjectures = self._get_conjectures(top_k, min_confidence)

        # -- Step 2-4: ZFC + Gray coherence -----------------------------------
        findings: List[GapFinding] = []
        hollow_count = 0
        gray_gap_count = 0

        for conj in conjectures:
            verdict, zfc_conf, hollow_preds = self._zfc_classify(conj)

            # Filter by verdict
            if hollow_only and verdict not in ("HOLLOW", "ORPHAN"):
                continue
            if verdict in ("HOLLOW", "ORPHAN"):
                hollow_count += 1

            # Build TwoCellProxy pair from the hollow/orphan conjecture
            alpha, beta = _hollow_to_twocell_pair(conj, hollow_preds)

            # Gray coherence check
            modification = self.gray_layer.check_modification_coherence(
                alpha, beta
            )

            if not modification.is_coherent:
                gray_gap_count += 1
                vuln = self.mapper.classify(
                    modification,
                    location=f"{conj.source} → {conj.target}",
                )
                finding = GapFinding(
                    conjecture_source=conj.source,
                    conjecture_target=conj.target,
                    conjecture_confidence=conj.top_confidence,
                    conjecture_generators=conj.candidate_sources,
                    zfc_verdict=verdict,
                    zfc_confidence=zfc_conf,
                    inefficiency=vuln,
                )
                findings.append(finding)

                # Learner feedback: hollow + gray gap = prediction was correct
                if self.learner and conj.predictions:
                    self.learner.record_outcome(
                        conj.predictions[0],
                        was_correct=True,   # gap confirmed = good prediction
                    )

        # Sort by combined severity
        findings.sort(key=lambda f: f.combined_severity, reverse=True)
        self._findings_history.extend(findings)

        elapsed_ms = (time.time() - start) * 1000

        # Build breakdowns
        by_class: Dict[str, int] = {}
        by_gap: Dict[str, int] = {}
        for f in findings:
            by_class[f.inefficiency.vuln_class] = (
                by_class.get(f.inefficiency.vuln_class, 0) + 1
            )
            by_gap[f.inefficiency.gap_type.value] = (
                by_gap.get(f.inefficiency.gap_type.value, 0) + 1
            )

        return ShieldReport(
            findings=findings,
            scan_time_ms=elapsed_ms,
            conjectures_evaluated=len(conjectures),
            hollow_count=hollow_count,
            gray_gap_count=gray_gap_count,
            by_vuln_class=by_class,
            by_gap_type=by_gap,
        )

    def record_patch(
        self,
        source: str,
        target: str,
        patched: bool = True,
    ):
        """
        Feed patch outcome back to OracleLearner.

        Call this after a inefficiency is patched (or confirmed false positive).
        The Bayesian updater will adjust future gap detection confidence.

        Args:
            source:  Conjecture source (as in GapFinding.conjecture_source)
            target:  Conjecture target
            patched: True if the gap was real and patched,
                     False if it was a false positive.
        """
        if not self.learner:
            return

        # Find matching findings and record outcome
        for finding in self._findings_history:
            if (finding.conjecture_source == source and
                    finding.conjecture_target == target):
                # Synthesise a minimal Prediction for the learner
                # (learner only needs prediction_type, strategy_name,
                #  predicted_relation, confidence)
                pred = _make_synthetic_prediction(finding)
                self.learner.record_outcome(pred, was_correct=patched)

    # -----------------------------------------------------------------------
    # Continuous mode
    # -----------------------------------------------------------------------

    async def run_continuous(self, top_k: int = 100):
        """
        Continuous pre-emptive scan loop.

        Races Mythos to structural gaps in your own knowledge graph.
        Emits findings to stdout; override _emit() to connect to your
        patch pipeline or Orion event bus.
        """
        print(f"[GridShield] Continuous scan started "
              f"(interval={self.scan_interval}s, top_k={top_k})")
        while True:
            report = self.scan(top_k=top_k)
            await self._emit(report)
            await asyncio.sleep(self.scan_interval)

    async def _emit(self, report: ShieldReport):
        """
        Emit findings. Override to connect to Orion event bus:

            await self.core.emit("gray.gaps.found", {
                "critical": len(report.critical),
                "chainable": len(report.chainable),
                "findings": [...],
            })
        """
        print(report.summary())
        for f in report.critical:
            print(f"  [CRITICAL] {f}")
        for f in report.chainable:
            if not f.is_critical:
                print(f"  [CHAINABLE] {f}")

    # -----------------------------------------------------------------------
    # Reporting helpers
    # -----------------------------------------------------------------------

    def print_report(self, report: ShieldReport):
        """Pretty-print a ShieldReport to stdout."""
        print("=" * 70)
        print(report.summary())
        print("=" * 70)

        if not report.findings:
            print("  No gaps found — systems clean.")
            return

        print(f"\n  TOP FINDINGS (by combined severity):\n")
        for i, f in enumerate(report.findings[:20], 1):
            tag = ""
            if f.is_critical:
                tag = " [CRITICAL]"
            if f.is_chainable:
                tag += " [CHAINABLE]"
            print(f"  {i:>2}. {f.conjecture_source} → {f.conjecture_target}{tag}")
            print(f"      vuln    : {f.inefficiency.vuln_class}")
            print(f"      gap     : {f.inefficiency.gap_type.value}")
            print(f"      severity: {f.combined_severity:.2f}")
            print(f"      zfc     : {f.zfc_verdict} (conf={f.zfc_confidence:.2f})")
            print(f"      mitre   : {f.inefficiency.mitre_id}")
            print(f"      fix     : {f.inefficiency.remediation}")
            print(f"      sources : {', '.join(f.conjecture_generators)}")
            print()

    @property
    def all_findings(self) -> List[GapFinding]:
        return list(self._findings_history)

    @property
    def chainable_findings(self) -> List[GapFinding]:
        return [f for f in self._findings_history if f.is_chainable]

    # -----------------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------------

    def _get_conjectures(
        self, top_k: int, min_confidence: float
    ) -> List[Conjecture]:
        """Run ConjectureEngine or fall back to empty list."""
        if not CONJECTURE_AVAILABLE or self.conjecture_engine is None:
            return []
        try:
            result: ConjectureResult = self.conjecture_engine.conjecture(
                top_k=top_k,
                min_confidence=min_confidence,
            )
            return result.conjectures
        except Exception as exc:
            print(f"[GridShield] ConjectureEngine error: {exc}")
            return []

    def _zfc_classify(
        self, conjecture: Conjecture
    ) -> Tuple[str, float, List[Prediction]]:
        """
        Run ZFC verification on a conjecture.

        Returns:
            (verdict, zfc_confidence, hollow_predictions)

        Verdicts: "HOLLOW", "ORPHAN", "AGREE", "REJECT", "UNKNOWN"
        """
        if not ZFC_AVAILABLE or self.zfc_bridge is None:
            # No ZFC — treat all conjectures as HOLLOW candidates
            # (conservative: assume gap until proved otherwise)
            return "HOLLOW", 0.5, conjecture.predictions

        try:
            dual = self.zfc_bridge.verify_predictions(
                source=conjecture.source,
                target=conjecture.target,
                predictions=conjecture.predictions,
            )

            # Extract HOLLOW predictions (CAT yes, ZFC no)
            hollow_preds = list(dual.hollows) if hasattr(dual, "hollows") else []
            orphan_preds = list(dual.orphans) if hasattr(dual, "orphans") else []

            if hollow_preds:
                # Severity: hollow confidence = CAT confidence (structurally
                # plausible) minus ZFC confidence (logically absent)
                zfc_conf = hollow_preds[0].zfc_confidence if hasattr(
                    hollow_preds[0], "zfc_confidence") else 0.0
                return "HOLLOW", zfc_conf, hollow_preds

            if orphan_preds:
                zfc_conf = orphan_preds[0].zfc_confidence if hasattr(
                    orphan_preds[0], "zfc_confidence") else 0.5
                return "ORPHAN", zfc_conf, orphan_preds

            agree_preds = list(dual.agrees) if hasattr(dual, "agrees") else []
            if agree_preds:
                return "AGREE", 1.0, []

            return "REJECT", 0.0, []

        except Exception as exc:
            print(f"[GridShield] ZFC verify error: {exc}")
            return "UNKNOWN", 0.0, conjecture.predictions


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _make_synthetic_prediction(finding: GapFinding) -> Prediction:
    """
    Build a minimal Prediction from a GapFinding for learner feedback.
    The learner only needs prediction_type, strategy_name,
    predicted_relation, and confidence.
    """
    # Map gap type to closest PredictionType
    _GAP_TO_PRED_TYPE: Dict[CoherenceGapType, PredictionType] = {
        CoherenceGapType.INTERCHANGE_FAILURE:   PredictionType.STRUCTURAL_SIMILARITY,
        CoherenceGapType.COMPOSITION_BOUNDARY:  PredictionType.COMPOSED_MORPHISM,
        CoherenceGapType.LIFETIME_VIOLATION:    PredictionType.TRANSITIVE_CLOSURE,
        CoherenceGapType.PRIVILEGE_NON_COMMUTE: PredictionType.CARTESIAN_LIFT,
        CoherenceGapType.FUNCTOR_ESCAPE:        PredictionType.FIBER_PREDICTION,
        CoherenceGapType.MODIFICATION_MISSING:  PredictionType.STRUCTURAL_HOLE,
        CoherenceGapType.GRAY_TENSOR_FAILURE:   PredictionType.CURVATURE_BRIDGE,
        CoherenceGapType.SIEVE_COLLAPSE:        PredictionType.YONEDA_ANALOGY,
    }
    pred_type = _GAP_TO_PRED_TYPE.get(
        finding.inefficiency.gap_type,
        PredictionType.STRUCTURAL_SIMILARITY,
    )
    return Prediction(
        source=finding.conjecture_source,
        target=finding.conjecture_target,
        predicted_relation=finding.inefficiency.vuln_class,
        prediction_type=pred_type,
        strategy_name="gray_coherence_bridge",
        confidence=finding.combined_severity,
    )


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def build_shield(
    oracle,
    category=None,
    domain: str = "cyber",
    scan_interval: float = 3600.0,
) -> GridShield:
    """
    Build a GridShield with all available layers.

    Gracefully skips ZFC and Learner if not importable.

    Usage:
        oracle = CategoricalOracle(category, embeddings)
        shield = build_shield(oracle, category=category)
        report = shield.scan()
        shield.print_report(report)
    """
    zfc_bridge = None
    if ZFC_AVAILABLE and category is not None:
        try:
            zfc_bridge = OracleZFCBridge(category, domain=domain)
        except Exception:
            pass

    learner = None
    if LEARNER_AVAILABLE:
        try:
            learner = OracleLearner()
        except Exception:
            pass

    return GridShield(
        oracle=oracle,
        zfc_bridge=zfc_bridge,
        learner=learner,
        scan_interval_seconds=scan_interval,
    )


# ---------------------------------------------------------------------------
# Quick demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("GridShield — Gray Coherence Bridge")
    print("=====================================")
    print()
    print("This module wires:")
    print("  conjecture.py     → proactive missing-edge discovery")
    print("  zfc_verifier.py   → HOLLOW = structurally plausible but logically unsound")
    print("  gray_coherence.py → formal 3-cell certificate")
    print("  learner.py        → Bayesian improvement from patch feedback")
    print()
    print("Usage:")
    print()
    print("  from komposos.core.gray_coherence_bridge import build_shield")
    print()
    print("  shield = build_shield(oracle, category=category)")
    print("  report = shield.scan(top_k=100)")
    print("  shield.print_report(report)")
    print()
    print("  # After patching a gap:")
    print("  shield.record_patch('module.fn_a', 'module.fn_b', patched=True)")
    print()
    print("  # Continuous pre-emptive mode:")
    print("  await shield.run_continuous(top_k=100)")
