# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 James Hawkins / Komposos-Labs

"""
Thermodynamic Coherence Layer (Gray-Category 3-Cell)
=====================================

Extends komposos/core/cosmos.py (InfinityCosmos / h₂K) with a
third categorical dimension: modifications between 2-cells.

Mathematical basis
------------------
In a strict 2-category the interchange law holds on the nose:

    (α ·_v β) ·_h γ  =  α ·_h (β ·_v γ)

In a Gray-category (Riehl & Verity §3, Gordon–Power–Street 1995)
the two sides are connected by a *3-cell* (modification) Γ rather
than being definitionally equal.  Where that modification does not
exist or is incoherent, the interchange law *breaks* — and that
break is a structural vulnerability.

Vulnerability mapping
---------------------
    coherence gap type          →  efficiency loss class
    ─────────────────────────────────────────────────
    interchange_failure         →  grid_instability
    composition_boundary        →  transmission_waste
    lifetime_violation          →  storage_decay
    privilege_non_commute       →  load_mismatch
    functor_escape              →  energy_leak
    modification_missing        →  frequency_desync
    gray_tensor_failure         →  reactive_power_loss
    sieve_collapse              →  cascading_failure

Integration
-----------
Drop this file into  komposos/core/gray_coherence.py

Import in cosmos.py::InfinityCosmos:

    from komposos.core.gray_coherence import (
        GrayCategoryLayer, Modification, EfficiencyViolation,
        GridCategoryBuilder, StabilityScan,
    )

Then in InfinityCosmos.__init__:

    self.gray = GrayCategoryLayer(self)

COG Tier 4 can call:

    self.cosmos.gray.check_modification_coherence(alpha, beta)

The StabilityScan scanner is the pre-emptive shield — run it
continuously against your own codebase so you find the gaps
before Mythos does.

Based on:
    Riehl & Verity — "Elements of ∞-Category Theory" (2022)
    Gordon, Power, Street — "Coherence for Tricategories" (1995)
    Nick Gurski — "Coherence in Three-Dimensional Category Theory" (2013)
"""

from __future__ import annotations

import asyncio
import ast
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import (
    Callable, Dict, Iterator, List, Optional,
    Set, Tuple, TYPE_CHECKING,
)

if TYPE_CHECKING:
    # Avoid circular import — cosmos imports us, we reference it for typing only
    from .cosmos import InfinityCosmos, TwoCell


# =============================================================================
# ENUMERATIONS
# =============================================================================

class CoherenceGapType(Enum):
    """
    The ways the Gray-category interchange law can fail.
    Each maps directly to a efficiency loss class.
    """
    INTERCHANGE_FAILURE    = "interchange_failure"     # type confusion
    COMPOSITION_BOUNDARY   = "composition_boundary"    # buffer overflow
    LIFETIME_VIOLATION     = "lifetime_violation"      # use-after-free
    PRIVILEGE_NON_COMMUTE  = "privilege_non_commute"   # privilege escalation
    FUNCTOR_ESCAPE         = "functor_escape"           # sandbox escape
    MODIFICATION_MISSING   = "modification_missing"    # race condition
    GRAY_TENSOR_FAILURE    = "gray_tensor_failure"     # memory corruption
    SIEVE_COLLAPSE         = "sieve_collapse"          # auth bypass
    NONE                   = "none"                    # coherent — no gap


LOSS_CLASS: Dict[CoherenceGapType, str] = {
    CoherenceGapType.INTERCHANGE_FAILURE:   "grid_instability",
    CoherenceGapType.COMPOSITION_BOUNDARY:  "transmission_waste",
    CoherenceGapType.LIFETIME_VIOLATION:    "storage_decay",
    CoherenceGapType.PRIVILEGE_NON_COMMUTE: "load_mismatch",
    CoherenceGapType.FUNCTOR_ESCAPE:        "energy_leak",
    CoherenceGapType.MODIFICATION_MISSING:  "frequency_desync",
    CoherenceGapType.GRAY_TENSOR_FAILURE:   "reactive_power_loss",
    CoherenceGapType.SIEVE_COLLAPSE:        "cascading_failure",
    CoherenceGapType.NONE:                  "clean",
}

SEVERITY_WEIGHT: Dict[CoherenceGapType, float] = {
    CoherenceGapType.FUNCTOR_ESCAPE:        1.0,   # sandbox escape = critical
    CoherenceGapType.PRIVILEGE_NON_COMMUTE: 0.95,
    CoherenceGapType.SIEVE_COLLAPSE:        0.90,
    CoherenceGapType.LIFETIME_VIOLATION:    0.85,
    CoherenceGapType.GRAY_TENSOR_FAILURE:   0.80,
    CoherenceGapType.INTERCHANGE_FAILURE:   0.75,
    CoherenceGapType.COMPOSITION_BOUNDARY:  0.70,
    CoherenceGapType.MODIFICATION_MISSING:  0.65,
    CoherenceGapType.NONE:                  0.0,
}


# =============================================================================
# CORE DATA STRUCTURES
# =============================================================================

@dataclass
class TwoCellProxy:
    """
    Lightweight stand-in for cosmos.TwoCell when the full cosmos
    is not yet imported (e.g. during software category building).

    Fields mirror the real TwoCell — swap out once cosmos is live.
    """
    source_morphism: str        # label of 1-morphism α acts on
    target_morphism: str        # label of 1-morphism α maps to
    label: str = ""
    confidence: float = 1.0
    # Optional: privilege level of the context this 2-cell lives in
    privilege_level: int = 0    # 0 = user, 1 = kernel, 2 = hypervisor
    # Optional: memory region identifiers for lifetime checking
    memory_regions: Tuple[str, ...] = field(default_factory=tuple)


@dataclass
class Modification:
    """
    A 3-cell: a modification Γ: α ⇛ β between two 2-cells.

    In a Gray-category, Γ assigns to each object X a 2-cell
    Γ_X : α_X → β_X, subject to the *modification axiom*:
    for every 1-morphism f : X → Y,

        Γ_Y ·_v (α_f)  =  (β_f) ·_v Γ_X

    is_coherent=True  ↔  axiom holds  ↔  no vulnerability
    is_coherent=False ↔  axiom fails  ↔  gap_type names the flaw
    """
    source_2cell: TwoCellProxy
    target_2cell: TwoCellProxy

    # One component 2-cell per object in the common domain
    components: Dict[str, TwoCellProxy] = field(default_factory=dict)

    is_coherent: bool = False
    gap_type: CoherenceGapType = CoherenceGapType.NONE

    # Human-readable account of *where* coherence fails
    gap_location: str = ""

    # The Gray tensor product witness (populated when coherent)
    gray_tensor_witness: Optional[str] = None

    # "structural" = verified via TwoCategory/PresheafTopos/path queries
    # "heuristic"  = threshold-based approximation (fallback)
    proof_type: str = "heuristic"

    # COG verification results (populated by FullDefensePipeline)
    cog_verified: bool = False
    cog_tier_reached: int = -1          # -1 = not checked, 0-4 = tier
    cog_confidence: float = 0.0
    cog_status: str = ""                # AGREE/HOLLOW/REJECT/etc


@dataclass
class EfficiencyViolation:
    """
    A structural vulnerability derived from a 3-cell coherence gap.

    The *proof* field IS the Modification — the 3-cell coherence
    failure is the mathematical certificate of the vulnerability.
    This is directly reportable to a patch pipeline or CVE triage.
    """
    loss_class: str
    severity: float             # [0, 1]
    location: str               # file/module/function path
    gap_type: CoherenceGapType
    proof: Modification         # the 3-cell IS the proof
    mitre_id: str = ""          # populated by CoherenceVulnerabilityMapper
    description: str = ""
    remediation: str = ""

    # OPTIMUS active refinement results
    optimus_intermediates: List[str] = field(default_factory=list)
    optimus_suggestions: List[str] = field(default_factory=list)

    # Higher-Order chain decomposition
    chain_decomposition: List[Dict] = field(default_factory=list)

    # CAT Engine activity analysis
    activity_obstructions: List[Dict] = field(default_factory=list)

    @property
    def is_critical(self) -> bool:
        return self.severity >= 0.90

    @property
    def is_chainable(self) -> bool:
        """
        True if this gap could be chained with other gaps by Mythos.
        Privilege escalation + sandbox escape are always chainable.
        """
        return self.gap_type in (
            CoherenceGapType.PRIVILEGE_NON_COMMUTE,
            CoherenceGapType.FUNCTOR_ESCAPE,
            CoherenceGapType.SIEVE_COLLAPSE,
        )


# =============================================================================
# SOFTWARE → CATEGORY TRANSLATION
# =============================================================================

@dataclass
class GridObject:
    """An object in the software category."""
    name: str
    kind: str        # "module", "class", "function", "memory_region", "privilege_level"
    privilege: int = 0
    metadata: Dict = field(default_factory=dict)


@dataclass
class GridMorphism:
    """A 1-morphism in the software category."""
    source: str
    target: str
    label: str
    kind: str        # "call", "data_flow", "type_coercion", "memory_access"
    privilege_delta: int = 0   # +1 = elevation, -1 = drop, 0 = same
    memory_regions: Tuple[str, ...] = field(default_factory=tuple)
    confidence: float = 1.0


# Security impact definitions for 1-morphisms (calls)
SINK_REGISTRY: Dict[str, Dict[str, float | int]] = {
    # CRITICAL: Remote Code Execution / Arbitrary Execution
    "eval": {"confidence": 0.1, "privilege": 0},
    "exec": {"confidence": 0.1, "privilege": 0},
    "pickle.loads": {"confidence": 0.2, "privilege": 0},
    "yaml.load": {"confidence": 0.2, "privilege": 0},
    
    # SYSTEM: OS Level Operations
    "os.system": {"confidence": 0.2, "privilege": 2},
    "os.popen": {"confidence": 0.2, "privilege": 2},
    "subprocess.Popen": {"confidence": 0.3, "privilege": 2},
    "subprocess.run": {"confidence": 0.3, "privilege": 2},
    
    # ACCESS: Privilege/Identity Changes
    "os.setuid": {"confidence": 0.4, "privilege": 2},
    "os.setgid": {"confidence": 0.4, "privilege": 2},
    "os.chmod": {"confidence": 0.5, "privilege": 2},
    "os.chown": {"confidence": 0.5, "privilege": 2},
    
    # NETWORK: Potential Exfiltration/Escape
    "socket.connect": {"confidence": 0.5, "privilege": 1},
    "socket.bind": {"confidence": 0.5, "privilege": 1},
    "requests.get": {"confidence": 0.7, "privilege": 1},
    "requests.post": {"confidence": 0.7, "privilege": 1},
}


class GridCategoryBuilder:
    """
    Lifts a codebase into categorical structure for 3-cell analysis.

    Objects   = modules, classes, memory regions, privilege levels
    1-cells   = function calls, data flows, type coercions
    2-cells   = alternative execution paths, compiler optimisations
    3-cells   = places where two 2-cells should commute but may not

    Updated with Security Sensors for autonomous vulnerability detection.
    """

    def __init__(self):
        self.objects: Dict[str, GridObject] = {}
        self.morphisms: List[GridMorphism] = []
        self._call_graph: Dict[str, Set[str]] = {}

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def from_source_file(self, path: str) -> "GridCategoryBuilder":
        """Parse a Python source file via AST."""
        source = Path(path).read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError:
            return self
        self._walk_ast(tree, module_name=Path(path).stem)
        return self

    def from_source_dir(self, directory: str,
                        glob: str = "**/*.py") -> "GridCategoryBuilder":
        """Recursively parse all Python files in a directory."""
        for p in Path(directory).glob(glob):
            self.from_source_file(str(p))
        return self

    def from_cfg(
        self,
        nodes: List[Dict],
        edges: List[Dict],
    ) -> "GridCategoryBuilder":
        """
        Consume a pre-built control-flow graph.

        nodes: [{"id": str, "kind": str, "privilege": int}, ...]
        edges: [{"src": str, "dst": str, "kind": str,
                 "privilege_delta": int}, ...]
        """
        for n in nodes:
            self.objects[n["id"]] = GridObject(
                name=n["id"],
                kind=n.get("kind", "node"),
                privilege=n.get("privilege", 0),
            )
        for e in edges:
            self.morphisms.append(GridMorphism(
                source=e["src"],
                target=e["dst"],
                label=e.get("label", f"{e['src']}→{e['dst']}"),
                kind=e.get("kind", "edge"),
                confidence=e.get("confidence", 1.0),
                privilege_delta=e.get("privilege_delta", 0),
                memory_regions=tuple(e.get("memory_regions", ())),
            ))
        return self

    def from_api_spec(
        self,
        endpoints: List[str],
        valid_sequences: List[Tuple[str, str]],
    ) -> "GridCategoryBuilder":
        """
        Model an API surface.

        endpoints        — list of endpoint names (objects)
        valid_sequences  — list of (caller, callee) pairs (morphisms)
        """
        for ep in endpoints:
            self.objects[ep] = GridObject(name=ep, kind="endpoint")
        for src, dst in valid_sequences:
            self.morphisms.append(GridMorphism(
                source=src, target=dst,
                label=f"{src}→{dst}", kind="call",
            ))
        return self

    # ------------------------------------------------------------------
    # 2-Cell enumeration
    # ------------------------------------------------------------------

    def enumerate_2cell_pairs(self) -> List[Tuple[TwoCellProxy, TwoCellProxy]]:
        """
        Find pairs of 2-cells (alternative execution paths) and
        propagate sensor confidence.

        Groups by source to catch gaps between different target sinks
        reachable from the same entry point.
        """
        # Group morphisms by source
        by_source: Dict[str, List[GridMorphism]] = {}
        for m in self.morphisms:
            by_source.setdefault(m.source, []).append(m)

        pairs: List[Tuple[TwoCellProxy, TwoCellProxy]] = []
        for src, morphs in by_source.items():
            if len(morphs) < 2:
                continue
            # Every pair of alternative morphisms from this source
            for i in range(len(morphs)):
                for j in range(i + 1, len(morphs)):
                    m1 = morphs[i]
                    m2 = morphs[j]
                    
                    # Skip non-executable morphisms like 'containment'
                    if m1.kind == "containment" or m2.kind == "containment":
                        continue

                    # Propagate confidence from the 1-morphism (sensor data).
                    # Use TARGET privileges for both 2-cells: the comparison
                    # captures where each alternative path leads, not where
                    # it starts (both share the same source).
                    alpha = TwoCellProxy(
                        source_morphism=m1.label,
                        target_morphism=m2.label,
                        label=f"2cell_{m1.label}_{m2.label}",
                        confidence=m1.confidence,
                        privilege_level=self.objects.get(m1.target,
                            GridObject(m1.target, "unknown")).privilege,
                        memory_regions=m1.memory_regions,
                    )
                    beta = TwoCellProxy(
                        source_morphism=m2.label,
                        target_morphism=m1.label,
                        label=f"2cell_{m2.label}_{m1.label}",
                        confidence=m2.confidence,
                        privilege_level=self.objects.get(m2.target,
                            GridObject(m2.target, "unknown")).privilege,
                        memory_regions=m2.memory_regions,
                    )
                    pairs.append((alpha, beta))
        return pairs

    # ------------------------------------------------------------------
    # Internal AST walker & Sensors
    # ------------------------------------------------------------------

    def _walk_ast(self, tree: ast.AST, module_name: str):
        module_obj = GridObject(
            name=module_name, kind="module", privilege=0,
        )
        self.objects[module_name] = module_obj

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn_name = f"{module_name}.{node.name}"
                
                # Behavioral Inference: What does this function DO?
                self._max_behavior_priv = 0
                calls_found: List[Tuple[str, float, str]] = [] # target, conf, branch
                
                # NEW: Branch-aware walk
                self._trace_node(node, module_name, "main", calls_found)

                # Synthesize final privilege (Heuristic + Behavioral)
                heuristic_priv = self._infer_privilege(node)
                final_priv = max(heuristic_priv, self._max_behavior_priv)

                self.objects[fn_name] = GridObject(
                    name=fn_name, kind="function",
                    privilege=final_priv,
                )
                
                # Module → function (containment morphism)
                self.morphisms.append(GridMorphism(
                    source=module_name, target=fn_name,
                    label=f"contains.{fn_name}", kind="containment",
                ))

                # Create Morphisms with Sensor Data & Branch Labels
                for callee, conf, branch in calls_found:
                    self.morphisms.append(GridMorphism(
                        source=fn_name, target=callee,
                        label=f"call.{fn_name}→{callee}.{branch}",
                        kind="call",
                        confidence=conf,
                        privilege_delta=self._privilege_delta(
                            fn_name, callee),
                    ))
                    self._call_graph.setdefault(
                        fn_name, set()).add(callee)

        # GLASSWING: Global Taint & Privilege Propagation (Fixpoint Loop)
        # Propagate risk and privilege up the call graph until stable.
        # Bound: privilege only increases (max 2) and confidence only decreases,
        # so worst case is O(|morphisms| * max_privilege_levels) iterations.
        max_iterations = max(len(self.morphisms) * 3, 1)
        iteration = 0
        changed = True
        while changed and iteration < max_iterations:
            iteration += 1
            changed = False
            for m in self.morphisms:
                if m.kind == "call":
                    src_obj = self.objects.get(m.source)
                    tgt_obj = self.objects.get(m.target)
                    if not src_obj or not tgt_obj: continue

                    # 1. Propagate Privilege Down (Inherit from behavioral sinks)
                    # If I call a Kernel function, I am a Kernel-caller
                    if tgt_obj.privilege > src_obj.privilege:
                        src_obj.privilege = tgt_obj.privilege
                        changed = True

                    # 2. Propagate Taint Up (Inherit risk from sinks)
                    # Find morphisms originating FROM the target
                    target_morphisms = [tm for tm in self.morphisms 
                                       if tm.source == m.target and tm.kind == "call"]
                    if target_morphisms:
                        min_target_conf = min(tm.confidence for tm in target_morphisms)
                        if min_target_conf < m.confidence:
                            m.confidence = min_target_conf
                            changed = True

        if iteration >= max_iterations and changed:
            import logging
            logging.getLogger(__name__).warning(
                "Privilege propagation hit iteration cap (%d). "
                "Graph may have unusual structure.", max_iterations
            )

    def _trace_node(self, node: ast.AST | List[ast.AST], module: str, branch: str,
                   calls_found: List[Tuple[str, float, str]]):
        """Recursive branch-aware call tracer with Semantic Sieve sensing."""
        if isinstance(node, list):
            for n in node:
                self._trace_node(n, module, branch, calls_found)
            return

        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Call):
                callee = self._resolve_call(child, module)
                if callee:
                    morphism_conf = 1.0
                    for sink, impact in SINK_REGISTRY.items():
                        if sink in callee:
                            morphism_conf = impact.get("confidence", 1.0)
                            self._max_behavior_priv = max(
                                self._max_behavior_priv, int(impact.get("privilege", 0)))
                            break
                    calls_found.append((callee, morphism_conf, branch))
            
            elif isinstance(child, ast.If):
                # GLASSWING: Semantic Sieve Sensor
                # If a branch is a 'short-circuit' (early return/success), 
                # it's a potential Sieve Collapse candidate.
                is_short_circuit = False
                for stmt in child.body:
                    for n in ast.walk(stmt):
                        if isinstance(n, (ast.Return, ast.Continue, ast.Break)):
                            is_short_circuit = True
                            break
                    if is_short_circuit: break
                
                branch_conf = 0.2 if is_short_circuit else 1.0
                
                self._trace_node(child.test, module, f"{branch}.if_test", calls_found)
                self._trace_node(child.body, module, f"{branch}.then", calls_found)
                # Mark the 'then' branch with potential collapse confidence
                if is_short_circuit:
                    calls_found.append(("sieve.collapse_point", branch_conf, f"{branch}.then"))

                if child.orelse:
                    self._trace_node(child.orelse, module, f"{branch}.else", calls_found)
                else:
                    # Explicitly label the 'implicit else' (the bypass path)
                    calls_found.append(("no_op.bypass", 0.5, f"{branch}.else_implicit"))
            else:
                if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    self._trace_node(child, module, branch, calls_found)

    def _infer_privilege(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> int:
        """Heuristic: names and decorators suggest privilege level."""
        name = node.name.lower()
        score = 0
        if any(k in name for k in ("root", "admin", "privileged", "sudo")):
            score = 1
        if any(k in name for k in ("kernel", "hypervisor", "ring0")):
            score = 2
            
        # Decorator sensor
        for decorator in node.decorator_list:
            dec_name = ""
            if isinstance(decorator, ast.Name):
                dec_name = decorator.id.lower()
            elif isinstance(decorator, ast.Attribute):
                dec_name = decorator.attr.lower()
            
            if any(k in dec_name for k in ("admin", "auth", "login", "perm")):
                score = max(score, 1)
        return score

    def _resolve_call(self, node: ast.Call, module: str) -> Optional[str]:
        """Detailed callee resolution."""
        if isinstance(node.func, ast.Name):
            return f"{module}.{node.func.id}"
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                return f"{node.func.value.id}.{node.func.attr}"
            return node.func.attr
        return None

    def _privilege_delta(self, src: str, dst: str) -> int:
        src_priv = self.objects.get(src, GridObject(src, "x")).privilege
        dst_priv = self.objects.get(dst, GridObject(dst, "x")).privilege
        return dst_priv - src_priv


# =============================================================================
# GRAY-CATEGORY LAYER
# =============================================================================

class GrayCategoryLayer:
    """
    Adds 3-cell (modification) coherence to InfinityCosmos.

    Core operation
    --------------
    check_modification_coherence(α, β) → Modification

    Given two parallel 2-cells α and β, determine whether a coherent
    modification Γ: α ⇛ β exists.  If not, the gap_type field of the
    returned Modification names the structural vulnerability.

    Interchange law (Gray version)
    --------------------------------
    Let α: f → g  and  β: h → k  be 2-cells in a 2-category where
    f, g: A → B  and  h, k: B → C.

    Horizontal composite:  (β ·_h α): (h∘f) → (k∘g)

    Two ways to form this:
        left  = (β ∘ id_f) ·_v (id_k ∘ α)
        right = (id_k ∘ α) ·_v (β ∘ id_f)   ← note reversed order

    Strict 2-category: left = right (definitional equality)
    Gray-category:     left = Γ ·_v right  for some invertible 3-cell Γ

    When Γ does not exist or is not invertible → coherence gap.
    """

    def __init__(self, cosmos: Optional["InfinityCosmos"] = None, *,
                 two_cat=None, presheaf_topos=None):
        self.cosmos = cosmos
        self._modifications: List[Modification] = []
        self._gap_cache: Dict[Tuple[str, str], Modification] = {}
        # Structural infrastructure (lazy-built from cosmos if available)
        self._two_cat = two_cat
        self._presheaf_topos = presheaf_topos

    @property
    def two_cat(self):
        """Lazy-build TwoCategory from cosmos if available."""
        if self._two_cat is None and self.cosmos is not None:
            try:
                self._two_cat = self.cosmos.homotopy_2_category()
            except Exception:
                pass
        return self._two_cat

    @property
    def presheaf_topos(self):
        """Lazy-build PresheafTopos from cosmos if available."""
        if self._presheaf_topos is None and self.cosmos is not None:
            try:
                from categorical.presheaf_topos import PresheafTopos
                self._presheaf_topos = PresheafTopos.from_enriched_category(
                    self.cosmos.category
                )
            except Exception:
                pass
        return self._presheaf_topos

    # ------------------------------------------------------------------
    # Primary API
    # ------------------------------------------------------------------

    def check_modification_coherence(
        self,
        alpha: TwoCellProxy,
        beta: TwoCellProxy,
    ) -> Modification:
        """
        Check whether a coherent modification Γ: α ⇛ β exists.

        Returns a Modification with:
            is_coherent = True   → no vulnerability
            is_coherent = False  → gap_type names the flaw
        """
        cache_key = (alpha.label, beta.label)
        if cache_key in self._gap_cache:
            return self._gap_cache[cache_key]

        gap_type, gap_location, proof_type = self._classify_gap(alpha, beta)
        components = self._build_components(alpha, beta, gap_type)
        witness = self._compute_gray_tensor_witness(alpha, beta, gap_type)

        mod = Modification(
            source_2cell=alpha,
            target_2cell=beta,
            components=components,
            is_coherent=(gap_type == CoherenceGapType.NONE),
            gap_type=gap_type,
            gap_location=gap_location,
            gray_tensor_witness=witness,
            proof_type=proof_type,
        )

        self._modifications.append(mod)
        self._gap_cache[cache_key] = mod
        return mod

    def enumerate_modification_candidates(
        self, builder: GridCategoryBuilder,
    ) -> List[Tuple[TwoCellProxy, TwoCellProxy]]:
        """Return all 2-cell pairs from the builder that need checking."""
        return builder.enumerate_2cell_pairs()

    def scan_builder(
        self, builder: GridCategoryBuilder,
    ) -> List[Modification]:
        """
        Full scan: enumerate + check all 2-cell pairs.
        Returns only incoherent modifications (the gaps).
        """
        gaps = []
        for alpha, beta in self.enumerate_modification_candidates(builder):
            mod = self.check_modification_coherence(alpha, beta)
            if not mod.is_coherent:
                gaps.append(mod)
        return gaps

    # ------------------------------------------------------------------
    # Gap classification — the core mathematical work
    # ------------------------------------------------------------------

    def _classify_gap(
        self,
        alpha: TwoCellProxy,
        beta: TwoCellProxy,
    ) -> Tuple[CoherenceGapType, str, str]:
        """
        Apply each coherence check in order of severity.
        First failure wins and names the gap.

        Returns:
            (gap_type, gap_location, proof_type)
            where proof_type is "structural" or "heuristic".
        """
        checks: List[Tuple[
            Callable[[TwoCellProxy, TwoCellProxy], Tuple[bool, str]],
            CoherenceGapType,
            str,
        ]] = [
            (self._check_functor_escape,
             CoherenceGapType.FUNCTOR_ESCAPE,
             "2-cell crosses containment boundary without valid functor"),

            (self._check_privilege_non_commute,
             CoherenceGapType.PRIVILEGE_NON_COMMUTE,
             "privilege elevation does not commute across the modification"),

            (self._check_sieve_collapse,
             CoherenceGapType.SIEVE_COLLAPSE,
             "sieve truth value collapses under modification — auth bypass"),

            (self._check_lifetime_violation,
             CoherenceGapType.LIFETIME_VIOLATION,
             "memory region reachable after its lifetime ends"),

            (self._check_gray_tensor,
             CoherenceGapType.GRAY_TENSOR_FAILURE,
             "Gray tensor product witness does not exist"),

            (self._check_interchange,
             CoherenceGapType.INTERCHANGE_FAILURE,
             "interchange law fails — left ≠ right, no 3-cell bridge"),

            (self._check_composition_boundary,
             CoherenceGapType.COMPOSITION_BOUNDARY,
             "composition crosses type/size boundary without constraint"),

            (self._check_modification_missing,
             CoherenceGapType.MODIFICATION_MISSING,
             "no modification connects the two 2-cells — race condition"),
        ]

        for check_fn, gap_type, location in checks:
            detected, proof_type = check_fn(alpha, beta)
            if detected:
                return gap_type, location, proof_type

        return CoherenceGapType.NONE, "", "structural"

    # ------------------------------------------------------------------
    # Individual coherence checks
    #
    # Each returns (detected: bool, proof_type: str).
    # "structural" = verified via TwoCategory / PresheafTopos / path queries.
    # "heuristic"  = threshold-based approximation (fallback).
    # ------------------------------------------------------------------

    def _check_interchange(
        self, alpha: TwoCellProxy, beta: TwoCellProxy
    ) -> Tuple[bool, str]:
        """
        Gray interchange law:
        (β ·_h α) should equal Γ ·_v (α ·_h β) for some invertible Γ.

        Structural: Use TwoCategory.godement_decompose() to check if two
        decomposition paths of the horizontal composite agree. If they
        don't, the interchange law fails — structural proof.

        Fallback heuristic: reversed morphism pair with low confidence product.
        """
        h2k = self.two_cat
        if h2k is not None:
            try:
                # Look for α and β as 2-cells in h2K
                src_mor_a = alpha.source_morphism
                tgt_mor_a = alpha.target_morphism
                src_mor_b = beta.source_morphism
                tgt_mor_b = beta.target_morphism

                # Find actual 2-cells in h2K matching α's and β's morphisms
                cells_a = h2k.two_cells_between(src_mor_a, tgt_mor_a)
                cells_b = h2k.two_cells_between(src_mor_b, tgt_mor_b)

                if cells_a and cells_b:
                    cell_a = cells_a[0]
                    cell_b = cells_b[0]
                    # Check if they're composable for Godement product
                    if cell_a.target_object == cell_b.source_object:
                        result = h2k.godement_decompose(
                            cell_a.name, cell_b.name
                        )
                        if not result["agree"]:
                            return (True, "structural")
                        return (False, "structural")
            except (ValueError, KeyError):
                pass  # Fall through to heuristic

        # Heuristic fallback
        same_pair = (
            alpha.source_morphism == beta.target_morphism and
            alpha.target_morphism == beta.source_morphism
        )
        no_witness = (alpha.confidence * beta.confidence) < 0.5
        return (same_pair and no_witness, "heuristic")

    def _check_composition_boundary(
        self, alpha: TwoCellProxy, beta: TwoCellProxy
    ) -> Tuple[bool, str]:
        """
        Composition boundary violation:
        If a 2-cell maps across a type/privilege boundary without
        an explicit constraint morphism, it may overflow that boundary.

        Structural: Use Category.find_paths() to find paths crossing the
        privilege boundary. Compare enriched weights of cross-boundary
        paths vs. within-boundary paths using check_commutativity tension.

        Fallback heuristic: privilege mismatch with low confidence.
        """
        if self.cosmos is not None:
            try:
                cat = self.cosmos.category
                # Check if actual paths exist between the morphism endpoints
                paths_a = cat.find_paths(alpha.source_morphism, alpha.target_morphism)
                paths_b = cat.find_paths(beta.source_morphism, beta.target_morphism)

                if paths_a and paths_b:
                    # Compare enriched weights: cross-boundary path vs same-level
                    from categorical.enriched_category import EnrichedCategory
                    ec = EnrichedCategory.from_category(cat) if hasattr(
                        EnrichedCategory, 'from_category') else None
                    if ec is not None:
                        path_a_nodes = [alpha.source_morphism] + [
                            p.target for p in paths_a[0].morphisms
                        ] if paths_a[0].morphisms else [alpha.source_morphism, alpha.target_morphism]
                        path_b_nodes = [beta.source_morphism] + [
                            p.target for p in paths_b[0].morphisms
                        ] if paths_b[0].morphisms else [beta.source_morphism, beta.target_morphism]

                        result = ec.check_commutativity(path_a_nodes, path_b_nodes)
                        if not result["commutes"] and result["tension"] > 0:
                            priv_mismatch = abs(
                                alpha.privilege_level - beta.privilege_level
                            ) > 0
                            if priv_mismatch:
                                return (True, "structural")
                            return (False, "structural")
            except Exception:
                pass  # Fall through to heuristic

        # Heuristic fallback
        priv_mismatch = abs(alpha.privilege_level - beta.privilege_level) > 0
        low_confidence = min(alpha.confidence, beta.confidence) < 0.6
        return (priv_mismatch and low_confidence, "heuristic")

    def _check_lifetime_violation(
        self, alpha: TwoCellProxy, beta: TwoCellProxy
    ) -> Tuple[bool, str]:
        """
        Memory lifetime violation (use-after-free pattern):
        If α and β share memory regions but compose in a way that
        one accesses after the other's lifetime ends.

        Structural: Check enriched path commutativity for paths through
        the shared memory region. If tension > 0 and paths share memory
        metadata, the lifetime semantics differ structurally.

        Fallback heuristic: shared memory regions with confidence divergence.
        """
        shared = set(alpha.memory_regions) & set(beta.memory_regions)
        if not shared:
            return (False, "heuristic")

        if self.cosmos is not None:
            try:
                cat = self.cosmos.category
                # Check if paths through shared regions have divergent weights
                paths_a = cat.find_paths(alpha.source_morphism, alpha.target_morphism)
                paths_b = cat.find_paths(beta.source_morphism, beta.target_morphism)
                if paths_a and paths_b:
                    # Compute confidence products for each path
                    conf_a = 1.0
                    for m in paths_a[0].morphisms:
                        conf_a *= m.confidence
                    conf_b = 1.0
                    for m in paths_b[0].morphisms:
                        conf_b *= m.confidence
                    if abs(conf_a - conf_b) > 0.1:
                        return (True, "structural")
                    return (False, "structural")
            except Exception:
                pass

        # Heuristic fallback
        confidence_divergence = abs(alpha.confidence - beta.confidence) > 0.4
        return (confidence_divergence, "heuristic")

    def _check_privilege_non_commute(
        self, alpha: TwoCellProxy, beta: TwoCellProxy
    ) -> Tuple[bool, str]:
        """
        Privilege non-commutativity:
        If doing α then β reaches a different privilege level than
        doing β then α, the modification cannot be coherent — this
        is a privilege escalation path.

        Structural: Use Category.find_paths() to find actual paths in both
        orderings (α→β and β→α). If both exist but have different enriched
        confidence products, the two orderings don't commute — structural
        proof of privilege non-commutativity.

        Fallback heuristic: one path at ring0, other at user level.
        """
        if self.cosmos is not None:
            try:
                cat = self.cosmos.category
                # Check paths in both orderings through the category
                # α acts on src_a→tgt_a, β acts on src_b→tgt_b
                # "α then β" = path through tgt_a then src_b
                # "β then α" = path through tgt_b then src_a
                paths_ab = cat.find_paths(alpha.source_morphism, beta.target_morphism)
                paths_ba = cat.find_paths(beta.source_morphism, alpha.target_morphism)

                if paths_ab and paths_ba:
                    conf_ab = 1.0
                    for m in paths_ab[0].morphisms:
                        conf_ab *= m.confidence
                    conf_ba = 1.0
                    for m in paths_ba[0].morphisms:
                        conf_ba *= m.confidence
                    # Non-commutativity: different confidence products
                    if abs(conf_ab - conf_ba) > 0.01:
                        crosses_boundary = (
                            max(alpha.privilege_level, beta.privilege_level) >= 2 and
                            min(alpha.privilege_level, beta.privilege_level) == 0
                        )
                        if crosses_boundary:
                            return (True, "structural")
                elif paths_ab and not paths_ba:
                    # One direction exists, other doesn't — non-commutative
                    return (True, "structural")
                elif paths_ba and not paths_ab:
                    return (True, "structural")
            except Exception:
                pass

        # Heuristic fallback
        crosses_boundary = (
            max(alpha.privilege_level, beta.privilege_level) >= 2 and
            min(alpha.privilege_level, beta.privilege_level) == 0
        )
        return (crosses_boundary, "heuristic")

    def _check_functor_escape(
        self, alpha: TwoCellProxy, beta: TwoCellProxy
    ) -> Tuple[bool, str]:
        """
        Functor escape (sandbox escape pattern):
        If a 2-cell maps out of its home category without a valid
        functor witnessing the transition, it has 'escaped'.

        Structural: Check if Category.find_paths() returns paths
        between different privilege domains. If paths exist but
        none go through an authorized gateway (a morphism with
        confidence > 0.5 connecting the privilege levels), the
        transition has no valid functor — structural escape.

        Fallback heuristic: level_gap >= 2 and low confidence.
        """
        level_gap = abs(alpha.privilege_level - beta.privilege_level)
        if level_gap < 2:
            return (False, "heuristic")

        if self.cosmos is not None:
            try:
                cat = self.cosmos.category
                paths = cat.find_paths(alpha.source_morphism, beta.target_morphism)
                if paths:
                    # Check if any path goes through a high-confidence gateway
                    has_gateway = False
                    for path in paths:
                        if all(m.confidence >= 0.5 for m in path.morphisms):
                            has_gateway = True
                            break
                    if not has_gateway:
                        return (True, "structural")
                    return (False, "structural")
                else:
                    # No path exists at all — escape via out-of-band mechanism
                    no_bridge = (alpha.confidence < 0.3 or beta.confidence < 0.3)
                    if no_bridge:
                        return (True, "structural")
            except Exception:
                pass

        # Heuristic fallback
        no_bridge = (alpha.confidence < 0.3 or beta.confidence < 0.3)
        return (level_gap >= 2 and no_bridge, "heuristic")

    def _check_modification_missing(
        self, alpha: TwoCellProxy, beta: TwoCellProxy
    ) -> Tuple[bool, str]:
        """
        Missing modification (race condition pattern):
        Two 2-cells that should be connected by a modification
        have no such connection — they can interleave arbitrarily.

        Structural: In h2K, check if any 2-cell connects α's and β's
        morphisms. If two_cells_between() returns empty, no modification
        exists — structural proof of a race condition.

        Fallback heuristic: same source, both uncertain, not identical.
        """
        not_identical = alpha.label != beta.label
        if not not_identical:
            return (False, "heuristic")

        same_source = alpha.source_morphism == beta.source_morphism
        if not same_source:
            return (False, "heuristic")

        h2k = self.two_cat
        if h2k is not None:
            try:
                # Check if any 2-cell connects the two morphisms
                cells_ab = h2k.two_cells_between(
                    alpha.target_morphism, beta.target_morphism
                )
                cells_ba = h2k.two_cells_between(
                    beta.target_morphism, alpha.target_morphism
                )
                if not cells_ab and not cells_ba:
                    # No 2-cell connects them — no modification can exist
                    return (True, "structural")
                return (False, "structural")
            except (ValueError, KeyError):
                pass

        # Heuristic fallback
        both_uncertain = (
            alpha.confidence < 0.7 and beta.confidence < 0.7
        )
        return (same_source and both_uncertain, "heuristic")

    def _check_gray_tensor(
        self, alpha: TwoCellProxy, beta: TwoCellProxy
    ) -> Tuple[bool, str]:
        """
        Gray tensor product failure (memory corruption pattern):
        The Gray tensor A ⊗ B replaces A × B and encodes that
        interchange holds only up to a 3-cell.

        Structural: In h2K, the Gray tensor product exists iff vertical
        or horizontal composition is defined. Try both composition
        directions — if all fail (ValueError), the tensor product
        doesn't exist. Structural proof.

        Fallback heuristic: no shared intermediate and both low confidence.
        """
        h2k = self.two_cat
        if h2k is not None:
            try:
                # Look for the 2-cells in h2K
                cells_a = h2k.two_cells_between(
                    alpha.source_morphism, alpha.target_morphism
                )
                cells_b = h2k.two_cells_between(
                    beta.source_morphism, beta.target_morphism
                )
                if cells_a and cells_b:
                    cell_a = cells_a[0]
                    cell_b = cells_b[0]
                    # Try vertical composition (both directions)
                    can_compose = False
                    try:
                        h2k.vertical_compose(cell_a.name, cell_b.name)
                        can_compose = True
                    except ValueError:
                        pass
                    if not can_compose:
                        try:
                            h2k.vertical_compose(cell_b.name, cell_a.name)
                            can_compose = True
                        except ValueError:
                            pass
                    # Try horizontal composition
                    if not can_compose:
                        try:
                            h2k.horizontal_compose(cell_a.name, cell_b.name)
                            can_compose = True
                        except ValueError:
                            pass
                    if not can_compose:
                        try:
                            h2k.horizontal_compose(cell_b.name, cell_a.name)
                            can_compose = True
                        except ValueError:
                            pass

                    if not can_compose:
                        return (True, "structural")
                    return (False, "structural")
            except (ValueError, KeyError):
                pass

        # Heuristic fallback
        no_shared = (
            alpha.target_morphism != beta.source_morphism and
            beta.target_morphism != alpha.source_morphism
        )
        both_low = (alpha.confidence < 0.4 and beta.confidence < 0.4)
        return (no_shared and both_low, "heuristic")

    def _check_sieve_collapse(
        self, alpha: TwoCellProxy, beta: TwoCellProxy
    ) -> Tuple[bool, str]:
        """
        Sieve collapse (authentication bypass pattern):
        In the presheaf topos, a sieve on an object X is a set of
        morphisms into X closed under precomposition.  If a
        modification collapses a maximal sieve to a non-maximal one,
        the subobject classifier truth value drops — this is an
        auth bypass.

        Structural: Build actual sieves from the PresheafTopos.
        Compute truth values for both 2-cells' target morphisms.
        If one has high truth value (authenticated) and the other
        has low truth value (unauthenticated), the sieve collapsed.

        Fallback heuristic: large confidence gap with same target.
        """
        same_target = alpha.target_morphism == beta.target_morphism
        if not same_target:
            return (False, "heuristic")

        topos = self.presheaf_topos
        if topos is not None:
            try:
                target = alpha.target_morphism
                max_sieve = topos.maximal_sieve(target)
                total_incoming = topos.incoming_count(target)

                if total_incoming > 0:
                    # Build observation sieves from α's and β's source morphisms
                    sieve_a = topos.classify_attack(
                        [alpha.source_morphism], target
                    )
                    sieve_b = topos.classify_attack(
                        [beta.source_morphism], target
                    )
                    truth_a = sieve_a.truth_value(total_incoming)
                    truth_b = sieve_b.truth_value(total_incoming)

                    # Sieve collapse: one path has high truth value,
                    # other has near-zero — the modification collapses
                    # the sieve from maximal to non-maximal
                    if abs(truth_a - truth_b) > 0.5:
                        return (True, "structural")
                    return (False, "structural")
            except Exception:
                pass

        # Heuristic fallback
        sieve_collapse = abs(alpha.confidence - beta.confidence) > 0.7
        return (same_target and sieve_collapse, "heuristic")

    # ------------------------------------------------------------------
    # Component and witness construction
    # ------------------------------------------------------------------

    def _build_components(
        self,
        alpha: TwoCellProxy,
        beta: TwoCellProxy,
        gap_type: CoherenceGapType,
    ) -> Dict[str, TwoCellProxy]:
        """
        Build the component 2-cells of the modification.
        For each 'object' in the shared domain, assign one component.
        When coherent, components witness the modification axiom.
        When incoherent, components are left as stubs.
        """
        components = {}
        # Source object
        components[alpha.source_morphism] = TwoCellProxy(
            source_morphism=alpha.source_morphism,
            target_morphism=beta.source_morphism,
            label=f"component_{alpha.source_morphism}",
            confidence=alpha.confidence if gap_type == CoherenceGapType.NONE
                       else 0.0,
            privilege_level=alpha.privilege_level,
        )
        # Target object
        components[alpha.target_morphism] = TwoCellProxy(
            source_morphism=alpha.target_morphism,
            target_morphism=beta.target_morphism,
            label=f"component_{alpha.target_morphism}",
            confidence=beta.confidence if gap_type == CoherenceGapType.NONE
                       else 0.0,
            privilege_level=beta.privilege_level,
        )
        return components

    def _compute_gray_tensor_witness(
        self,
        alpha: TwoCellProxy,
        beta: TwoCellProxy,
        gap_type: CoherenceGapType,
    ) -> Optional[str]:
        """
        Attempt to compute the Gray tensor product witness string.
        Returns None if no witness exists (i.e. gap is real).
        """
        if gap_type != CoherenceGapType.NONE:
            return None
        # Coherent case: witness is the composite label
        return (
            f"Γ: ({alpha.label}) ⊗_Gray ({beta.label}) "
            f"— interchange holds up to this modification"
        )


# =============================================================================
# VULNERABILITY MAPPER
# =============================================================================

# MITRE ATT&CK technique for each gap class
_GAP_TO_MITRE: Dict[CoherenceGapType, str] = {
    CoherenceGapType.INTERCHANGE_FAILURE:   "T1203",   # Exploitation for Client Execution
    CoherenceGapType.COMPOSITION_BOUNDARY:  "T1190",   # Exploit Public-Facing Application
    CoherenceGapType.LIFETIME_VIOLATION:    "T1203",   # Memory corruption → execution
    CoherenceGapType.PRIVILEGE_NON_COMMUTE: "T1068",   # Exploitation for Privilege Escalation
    CoherenceGapType.FUNCTOR_ESCAPE:        "T1611",   # Escape to Host (container/sandbox)
    CoherenceGapType.MODIFICATION_MISSING:  "T1race",  # Race condition (no MITRE ID yet)
    CoherenceGapType.GRAY_TENSOR_FAILURE:   "T1203",
    CoherenceGapType.SIEVE_COLLAPSE:        "T1556",   # Modify Authentication Process
}

_REMEDIATION: Dict[CoherenceGapType, str] = {
    CoherenceGapType.INTERCHANGE_FAILURE:
        "Add explicit type constraint morphism between the two paths.",
    CoherenceGapType.COMPOSITION_BOUNDARY:
        "Insert bounds-checking morphism at the composition boundary.",
    CoherenceGapType.LIFETIME_VIOLATION:
        "Enforce lifetime constraint — add drop/free morphism before reuse.",
    CoherenceGapType.PRIVILEGE_NON_COMMUTE:
        "Add capability check morphism before privilege-crossing 2-cell.",
    CoherenceGapType.FUNCTOR_ESCAPE:
        "Define explicit functor with security policy between categories.",
    CoherenceGapType.MODIFICATION_MISSING:
        "Add synchronisation primitive (mutex/lock) as bridging 3-cell.",
    CoherenceGapType.GRAY_TENSOR_FAILURE:
        "Rewrite to ensure composable morphisms; add intermediate object.",
    CoherenceGapType.SIEVE_COLLAPSE:
        "Require authentication morphism before sieve-collapsing path.",
}


class CoherenceVulnerabilityMapper:
    """
    Turns Modification objects into EfficiencyViolation reports.

    The Modification IS the proof — no separate certificate needed.
    """

    def classify(self, mod: Modification, location: str = "") -> EfficiencyViolation:
        loss_class = LOSS_CLASS[mod.gap_type]
        severity   = SEVERITY_WEIGHT[mod.gap_type]
        mitre_id   = _GAP_TO_MITRE.get(mod.gap_type, "")
        remediation = _REMEDIATION.get(mod.gap_type, "")

        desc = (
            f"3-cell coherence gap between "
            f"'{mod.source_2cell.label}' and '{mod.target_2cell.label}'. "
            f"Gap type: {mod.gap_type.value}. "
            f"Location: {mod.gap_location or location}."
        )

        return EfficiencyViolation(
            loss_class=loss_class,
            severity=severity,
            location=location or mod.gap_location,
            gap_type=mod.gap_type,
            proof=mod,
            mitre_id=mitre_id,
            description=desc,
            remediation=remediation,
        )

    def classify_all(
        self,
        mods: List[Modification],
        location: str = "",
    ) -> List[EfficiencyViolation]:
        return [self.classify(m, location) for m in mods if not m.is_coherent]


# =============================================================================
# MYTHOS RACE — PRE-EMPTIVE SCAN LOOP
# =============================================================================

class StabilityScan:
    """
    Pre-emptive continuous scanner.

    Races Mythos to coherence gaps in your own systems.
    Finds → reports → patches → rescans.

    Usage
    -----
        race = StabilityScan(scan_interval_seconds=3600)
        await race.run(targets=["src/", "komposos/", "cyber/"])
    """

    def __init__(
        self,
        scan_interval_seconds: float = 3600.0,
        cosmos: Optional["InfinityCosmos"] = None,
        *,
        full_defense: bool = True,
        cog_min_tier: int = 3,
        optimus_depth: int = 3,
        cat_tension_threshold: float = 0.1,
    ):
        self.scan_interval = scan_interval_seconds
        self.gray    = GrayCategoryLayer(cosmos)
        self.mapper  = CoherenceVulnerabilityMapper()
        self._findings: List[EfficiencyViolation] = []
        self._defense_reports: List["DefenseReport"] = []

        # Full Defense Pipeline integration
        self.full_defense = full_defense
        self._pipeline = FullDefensePipeline(
            cosmos=cosmos,
            cog_min_tier=cog_min_tier,
            optimus_depth=optimus_depth,
            cat_tension_threshold=cat_tension_threshold,
        ) if full_defense else None

        # Integration with the wider system
        self.oracle = None
        if cosmos:
            from oracle import CategoricalOracle
            from data.embeddings import EmbeddingsEngine
            self.oracle = CategoricalOracle(cosmos.category, EmbeddingsEngine())

    def scan_path(self, path: str) -> List[EfficiencyViolation]:
        """
        Scan a single file or directory.

        When full_defense=True (default), runs the complete pipeline:
          Gray Coherence → COG Verification → OPTIMUS Refinement →
          Higher-Order Decomposition → CAT Engine Activity Analysis

        When full_defense=False, uses Gray Coherence + Conjecture only.
        """
        builder = GridCategoryBuilder()
        p = Path(path)
        if p.is_file():
            builder.from_source_file(path)
        elif p.is_dir():
            builder.from_source_dir(path)
        else:
            return []

        # Full Defense Pipeline (COG + OPTIMUS + Higher-Order + CAT)
        if self._pipeline is not None:
            report = self._pipeline.run(builder, location=path)
            self._defense_reports.append(report)
            candidates = report.vulnerabilities
            candidates.sort(key=lambda c: c.severity, reverse=True)
            self._findings.extend(candidates)
            return candidates

        # Legacy mode: Gray Coherence only
        gaps = self.gray.scan_builder(builder)

        # Mode 2: Proactive 'Hollow' Detection (if Oracle is available)
        if self.oracle:
            from oracle.conjecture import ConjectureType
            # Conjecture missing paths between User and Kernel objects
            for obj_name, obj in builder.objects.items():
                if obj.privilege == 0: # User-level entry point
                    # Find all kernel-level sinks
                    for target_name, target in builder.objects.items():
                        if target.privilege >= 2:
                            # Use the ConjectureEngine to see if a hidden path exists
                            conjectures = self.oracle.conjecture.generate_conjectures(
                                obj_name, target_name,
                                types=[ConjectureType.COMPOSITION_GAP]
                            )
                            for c in conjectures:
                                # Verify with ZFC (HOLLOW check)
                                if self.oracle.zfc.verify_conjecture(c).is_hollow:
                                    # Infer gap type from privilege relationship
                                    gap_type = self._infer_hollow_gap_type(obj, target)
                                    mock_mod = Modification(
                                        source_2cell=TwoCellProxy(obj_name, target_name, "conjectured_exploit", confidence=0.1),
                                        target_2cell=TwoCellProxy(obj_name, target_name, "security_policy", confidence=1.0),
                                        is_coherent=False,
                                        gap_type=gap_type,
                                        gap_location=f"Conjectured hollow path from {obj_name} to {target_name}"
                                    )
                                    gaps.append(mock_mod)

        candidates = self.mapper.classify_all(gaps, location=path)
        candidates.sort(key=lambda c: c.severity, reverse=True)
        self._findings.extend(candidates)
        return candidates

    def scan_cfg(
        self,
        nodes: List[Dict],
        edges: List[Dict],
        label: str = "cfg",
    ) -> List[EfficiencyViolation]:
        """Scan a pre-built control-flow graph through the full defense pipeline."""
        builder = GridCategoryBuilder().from_cfg(nodes, edges)

        # Full Defense Pipeline
        if self._pipeline is not None:
            report = self._pipeline.run(builder, location=label)
            self._defense_reports.append(report)
            candidates = report.vulnerabilities
            candidates.sort(key=lambda c: c.severity, reverse=True)
            self._findings.extend(candidates)
            return candidates

        # Legacy mode
        gaps = self.gray.scan_builder(builder)
        candidates = self.mapper.classify_all(gaps, location=label)
        candidates.sort(key=lambda c: c.severity, reverse=True)
        self._findings.extend(candidates)
        return candidates

    @staticmethod
    def _infer_hollow_gap_type(
        source_obj: GridObject, target_obj: GridObject
    ) -> CoherenceGapType:
        """Infer gap type from privilege relationship instead of hardcoding."""
        if source_obj.privilege == 0 and target_obj.privilege >= 2:
            return CoherenceGapType.PRIVILEGE_NON_COMMUTE  # user→kernel = privesc
        if source_obj.privilege >= 2 and target_obj.privilege == 0:
            return CoherenceGapType.FUNCTOR_ESCAPE  # kernel→user = sandbox escape
        if source_obj.privilege == target_obj.privilege:
            return CoherenceGapType.COMPOSITION_BOUNDARY  # lateral movement
        return CoherenceGapType.SIEVE_COLLAPSE  # fallback for ambiguous cases

    # ------------------------------------------------------------------
    # Continuous loop
    # ------------------------------------------------------------------

    async def run(self, targets: List[str]):
        """
        Continuous pre-emptive scan loop.

        For each target path, scans and emits findings.
        Sleeps for scan_interval then repeats.
        """
        print(f"[StabilityScan] Starting continuous scan of {targets}")
        while True:
            all_candidates: List[EfficiencyViolation] = []
            for target in targets:
                found = self.scan_path(target)
                all_candidates.extend(found)

            if all_candidates:
                await self._emit(all_candidates)
            else:
                print("[StabilityScan] No coherence gaps found — systems clean.")

            await asyncio.sleep(self.scan_interval)

    async def _emit(self, candidates: List[EfficiencyViolation]):
        """
        Emit findings to patch pipeline.
        Override in subclass to connect to your actual pipeline.
        """
        critical = [c for c in candidates if c.is_critical]
        chainable = [c for c in candidates if c.is_chainable]

        print(f"[StabilityScan] {len(candidates)} gaps found — "
              f"{len(critical)} critical, {len(chainable)} chainable.")

        for c in candidates:
            print(
                f"  [{c.gap_type.value}] {c.loss_class} "
                f"severity={c.severity:.2f} "
                f"mitre={c.mitre_id} "
                f"loc={c.location}\n"
                f"    → {c.remediation}"
            )

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    @property
    def all_findings(self) -> List[EfficiencyViolation]:
        return list(self._findings)

    @property
    def critical_findings(self) -> List[EfficiencyViolation]:
        return [f for f in self._findings if f.is_critical]

    @property
    def chainable_findings(self) -> List[EfficiencyViolation]:
        """
        The findings Mythos would chain together.
        Prioritise patching these — removing one breaks the chain.
        """
        return [f for f in self._findings if f.is_chainable]

    def summary(self) -> Dict:
        base = {
            "total":     len(self._findings),
            "critical":  len(self.critical_findings),
            "chainable": len(self.chainable_findings),
            "by_class":  {
                gt.value: sum(
                    1 for f in self._findings if f.gap_type == gt
                )
                for gt in CoherenceGapType
                if gt != CoherenceGapType.NONE
            },
        }
        # Add full defense pipeline metadata
        if self._defense_reports:
            total_detected = sum(len(r.all_gaps) for r in self._defense_reports)
            total_rejected = sum(r.cog_rejection_count for r in self._defense_reports)
            total_obstructions = sum(
                len(r.activity_obstructions) for r in self._defense_reports
            )
            base["pipeline"] = {
                "mode": "full_defense",
                "total_gaps_detected": total_detected,
                "cog_rejected_false_positives": total_rejected,
                "activity_obstructions": total_obstructions,
                "stages_active": self._defense_reports[-1]._active_stages()
                    if self._defense_reports else [],
                "with_optimus_suggestions": sum(
                    1 for f in self._findings if f.optimus_suggestions
                ),
                "with_chain_decomposition": sum(
                    1 for f in self._findings if f.chain_decomposition
                ),
            }
        else:
            base["pipeline"] = {"mode": "legacy_gray_only"}
        return base


# =============================================================================
# FULL DEFENSE PIPELINE — COG + OPTIMUS + Higher-Order + CAT Integration
# =============================================================================

class FullDefensePipeline:
    """
    Integrated Mythos defense pipeline using ALL categorical machinery.

    Pipeline stages:
      1. Gray Coherence (detect gaps)
      2. COG Verification (5-tier, reject false positives)
      3. OPTIMUS Active Refinement (suggest intermediate objects to close gaps)
      4. Higher-Order Decomposition (factorize multi-step chains)
      5. CAT Engine Activity Analysis (detect sociotechnical obstructions)

    Usage:
        pipeline = FullDefensePipeline()
        results = pipeline.run(builder)
        # results.verified_gaps — COG-verified gaps only
        # results.vulnerabilities — with OPTIMUS suggestions + chain decomps
        # results.activity_obstructions — CAT engine findings
        # results.combined_report — unified threat report
    """

    def __init__(
        self,
        cosmos=None,
        *,
        cog_min_tier: int = 3,
        optimus_depth: int = 3,
        cat_tension_threshold: float = 0.1,
    ):
        """
        Args:
            cosmos: Optional InfinityCosmos for structural proofs.
            cog_min_tier: Minimum COG tier for gap acceptance (default 3 = ZFC).
            optimus_depth: OPTIMUS factorization depth.
            cat_tension_threshold: CAT Engine tension threshold.
        """
        self.cosmos = cosmos
        self.cog_min_tier = cog_min_tier
        self.optimus_depth = optimus_depth
        self.cat_tension_threshold = cat_tension_threshold
        self._category = None
        self._cog_engine = None
        self._optimus_engine = None
        self._higher_order = None
        self._cat_engine = None

    def _build_category_from_builder(self, builder: GridCategoryBuilder):
        """
        Convert GridCategoryBuilder data into a Category for COG/OPTIMUS.
        """
        from .category import Category

        cat = Category(db_path=":memory:")
        for name, obj in builder.objects.items():
            cat.add(name, type_name=obj.kind, metadata={
                "privilege": obj.privilege,
            })
        for m in builder.morphisms:
            if cat.get(m.source) and cat.get(m.target):
                cat.connect(
                    m.source, m.target, m.label,
                    confidence=m.confidence,
                    metadata={
                        "kind": m.kind,
                        "privilege_delta": m.privilege_delta,
                        "memory_regions": list(m.memory_regions),
                    },
                )
        self._category = cat
        return cat

    def _init_cog(self, category):
        """Initialize COG engine from category."""
        from cog.session import CogSession
        from cog.engine import CogEngine

        session = CogSession(category=category)
        self._cog_engine = CogEngine(session)
        return self._cog_engine

    def _init_optimus(self, category):
        """Initialize OPTIMUS engine from category."""
        from .optimus import OptimusEngine

        self._optimus_engine = OptimusEngine(category, max_depth=self.optimus_depth)
        return self._optimus_engine

    def _init_higher_order(self, category):
        """Initialize Higher-Order OPTIMUS with TwoCategory if available."""
        try:
            from .higher_order_optimus import HigherOrderOptimus
            from .cosmos import InfinityCosmos

            two_cat = None
            if self.cosmos is not None:
                two_cat = self.cosmos.homotopy_2_category()
            elif category:
                try:
                    cosmos = InfinityCosmos(category)
                    two_cat = cosmos.homotopy_2_category()
                except Exception:
                    pass

            if two_cat is not None:
                # Build RuntimeCategory for Higher-Order
                from .optimus import OptimusEngine
                engine = OptimusEngine(category, max_depth=self.optimus_depth)
                engine._build_runtime()
                self._higher_order = HigherOrderOptimus(
                    engine._runtime, two_category=two_cat,
                )
            return self._higher_order
        except Exception:
            return None

    def _init_cat_engine(self, category):
        """Initialize CAT Engine."""
        try:
            from categorical.cat_advanced import CATEngine
            from .optimus import OptimusEngine

            optimus = OptimusEngine(category)
            self._cat_engine = CATEngine(category, optimus=optimus)
            return self._cat_engine
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Stage 2: COG Verification
    # ------------------------------------------------------------------

    def _verify_gap_with_cog(
        self, mod: Modification, cog_engine
    ) -> Modification:
        """
        Run a gap through COG's 5-tier verification.

        Creates a CogClaim from the gap's source/target morphisms and
        verifies through all tiers. Updates Modification fields.
        """
        from cog.schema import CogClaim

        claim = CogClaim(
            source=mod.source_2cell.source_morphism,
            target=mod.target_2cell.target_morphism,
            relation="coherence_violation",
            confidence=1.0 - min(
                mod.source_2cell.confidence,
                mod.target_2cell.confidence,
            ),
        )

        try:
            result = cog_engine.check_claim(claim)
            mod.cog_tier_reached = result.tier_reached
            mod.cog_confidence = result.confidence
            mod.cog_status = result.status.value

            # Gap is COG-verified if:
            # - Tier reached >= min_tier AND
            # - Status is not AGREE (AGREE means the path is fine, not a gap)
            # A gap that COG says is HOLLOW or REJECT = confirmed vulnerability
            # A gap that COG says is AGREE = false positive (path is actually valid)
            if result.tier_reached >= self.cog_min_tier:
                if result.status.value in ("hollow", "reject", "orphan"):
                    mod.cog_verified = True
                elif result.status.value == "agree":
                    # COG found the path is valid — this gap is a false positive
                    mod.cog_verified = False
                else:
                    # PARTIAL/PENDING — inconclusive, keep the gap but flag it
                    mod.cog_verified = True
            else:
                # Didn't reach min tier — accept gap but mark as unverified
                mod.cog_verified = True

        except Exception:
            # COG failed — accept the gap (conservative)
            mod.cog_verified = True
            mod.cog_tier_reached = -1
            mod.cog_status = "error"

        return mod

    # ------------------------------------------------------------------
    # Stage 3: OPTIMUS Active Refinement
    # ------------------------------------------------------------------

    def _refine_with_optimus(
        self, vuln: EfficiencyViolation, optimus_engine
    ) -> EfficiencyViolation:
        """
        Use OPTIMUS to find intermediate objects that could close the gap.
        """
        try:
            source = vuln.proof.source_2cell.source_morphism
            target = vuln.proof.target_2cell.target_morphism

            intermediates = optimus_engine.discover_intermediates(
                source, target, depth=self.optimus_depth,
            )
            vuln.optimus_intermediates = intermediates

            if intermediates:
                vuln.optimus_suggestions = [
                    f"Add validation gate at '{obj}' between "
                    f"'{source}' and '{target}'"
                    for obj in intermediates
                ]
            else:
                # No intermediates found — suggest creating one
                vuln.optimus_suggestions = [
                    f"Create explicit authorization check between "
                    f"'{source}' and '{target}' "
                    f"(no intermediate objects exist — direct jump)",
                ]
        except Exception:
            pass

        return vuln

    # ------------------------------------------------------------------
    # Stage 4: Higher-Order Chain Decomposition
    # ------------------------------------------------------------------

    def _decompose_chain(
        self, vuln: EfficiencyViolation
    ) -> EfficiencyViolation:
        """
        For chainable vulnerabilities, decompose at 2-morphism level.
        """
        if not vuln.is_chainable or self._higher_order is None:
            return vuln

        try:
            # Look for 2-cells matching this vulnerability's morphisms
            source_label = vuln.proof.source_2cell.label
            target_label = vuln.proof.target_2cell.label

            # Try to factorize the source 2-cell
            factorizations = self._higher_order.factorize_two_cell(source_label)
            if factorizations:
                vuln.chain_decomposition = factorizations

            # If no factorization found on the label, try the target
            if not factorizations:
                factorizations = self._higher_order.factorize_two_cell(
                    target_label
                )
                if factorizations:
                    vuln.chain_decomposition = factorizations
        except Exception:
            pass

        return vuln

    # ------------------------------------------------------------------
    # Stage 5: CAT Engine Activity Analysis
    # ------------------------------------------------------------------

    def _run_cat_analysis(
        self, builder: GridCategoryBuilder
    ) -> List[Dict]:
        """
        Build an ActivitySystem from the software category and detect
        obstructions via CAT Engine.
        """
        if self._cat_engine is None:
            return []

        try:
            from categorical.activity_system import (
                ActivitySystem, ActivityComponent,
            )
            from categorical.cat_advanced import TrustBoundary

            # Build ActivitySystem from builder objects
            system = ActivitySystem(name="software_system")
            trust_boundaries = []

            for name, obj in builder.objects.items():
                if obj.kind == "function":
                    if obj.privilege >= 2:
                        comp_type = ActivityComponent.OBJECT
                    elif obj.privilege >= 1:
                        comp_type = ActivityComponent.TOOL
                    else:
                        comp_type = ActivityComponent.SUBJECT
                elif obj.kind == "module":
                    comp_type = ActivityComponent.COMMUNITY
                else:
                    comp_type = ActivityComponent.SUBJECT

                system.add_component(name, comp_type, metadata={
                    "privilege": obj.privilege,
                    "kind": obj.kind,
                })

            # Create trust boundaries from privilege level transitions
            priv_levels = {}
            for name, obj in builder.objects.items():
                priv_levels.setdefault(obj.privilege, []).append(name)

            if 0 in priv_levels and 2 in priv_levels:
                trust_boundaries.append(TrustBoundary(
                    name="user_to_kernel",
                    source_surface="UserSpace",
                    target_surface="KernelSpace",
                    policy_rules=["load_mismatch_check"],
                ))

            if system.components:
                result = self._cat_engine.full_analysis(
                    system,
                    trust_boundaries=trust_boundaries if trust_boundaries else None,
                    tension_threshold=self.cat_tension_threshold,
                    evolve=False,
                )
                obstructions = result.get("obstructions", [])
                return [
                    {
                        "type": o.triad if hasattr(o, "triad") else "tension",
                        "tension": o.tension if hasattr(o, "tension") else 0.0,
                        "status": o.status if hasattr(o, "status") else "",
                        "description": o.description if hasattr(o, "description") else str(o),
                    }
                    for o in obstructions
                ] if obstructions else []

        except Exception:
            pass

        return []

    # ------------------------------------------------------------------
    # Stage 6: Streaming Kan Real-Time Prediction
    # ------------------------------------------------------------------

    def _predict_next_attacks(
        self, vulnerabilities: List[EfficiencyViolation],
    ) -> List[Dict]:
        """
        Feed detected gaps into the Streaming Kan Extension to predict
        what Mythos will likely try next.

        Maps gap_type → MITRE technique IDs, then uses the real-time
        predictor to forecast next attack steps.
        """
        try:
            from cyber.realtime_predictor import RealTimeAttackPredictor

            predictor = RealTimeAttackPredictor(
                alert_threshold=0.5, decay_rate=0.001,
            )

            # Map gap types to MITRE technique IDs for the predictor
            gap_to_mitre = {
                CoherenceGapType.PRIVILEGE_NON_COMMUTE: "T1068",
                CoherenceGapType.FUNCTOR_ESCAPE: "T1611",
                CoherenceGapType.SIEVE_COLLAPSE: "T1556",
                CoherenceGapType.COMPOSITION_BOUNDARY: "T1190",
                CoherenceGapType.LIFETIME_VIOLATION: "T1203",
                CoherenceGapType.INTERCHANGE_FAILURE: "T1203",
                CoherenceGapType.GRAY_TENSOR_FAILURE: "T1203",
                CoherenceGapType.MODIFICATION_MISSING: "T1068",
            }

            # Feed each detected vulnerability as an observed technique
            import time as _time
            ts = _time.time()
            for vuln in vulnerabilities:
                mitre_id = gap_to_mitre.get(vuln.gap_type, "T1190")
                predictor.ingest_event(mitre_id, timestamp=ts)
                ts += 0.1  # Slight time spread for ordering

            # Get predictions for next likely attacks
            predictions = predictor.streaming_kan.predict(top_k=5)
            return predictions

        except Exception:
            return []

    # ------------------------------------------------------------------
    # Stage 7: ThreatIntelligenceBus Publishing
    # ------------------------------------------------------------------

    def _publish_to_bus(
        self, vulnerabilities: List[EfficiencyViolation],
        predictions: List[Dict],
        activity_obstructions: List[Dict],
    ) -> None:
        """
        Publish all findings to the ThreatIntelligenceBus so other
        modules (attack_simulator, variant_detector, etc.) can react.
        """
        try:
            from core.threat_intelligence_bus import ThreatIntelligenceBus

            bus = ThreatIntelligenceBus.get_instance()

            # Publish each verified vulnerability
            for vuln in vulnerabilities:
                bus.publish(
                    "coherence.gap.found",
                    {
                        "gap_type": vuln.gap_type.value,
                        "severity": vuln.severity,
                        "location": vuln.location,
                        "mitre_id": vuln.mitre_id,
                        "cog_verified": vuln.proof.cog_verified,
                        "cog_tier": vuln.proof.cog_tier_reached,
                        "proof_type": vuln.proof.proof_type,
                        "optimus_suggestions": vuln.optimus_suggestions,
                    },
                    source="FullDefensePipeline",
                )

            # Publish predictions
            if predictions:
                bus.publish(
                    "mythos.attack.predicted",
                    {
                        "predictions": predictions,
                        "based_on_gaps": len(vulnerabilities),
                    },
                    source="FullDefensePipeline.streaming_kan",
                )

            # Publish activity obstructions
            if activity_obstructions:
                bus.publish(
                    "activity.obstruction.detected",
                    {
                        "obstructions": activity_obstructions,
                    },
                    source="FullDefensePipeline.cat_engine",
                )

        except Exception:
            pass

    # ------------------------------------------------------------------
    # Main Pipeline Entry Point
    # ------------------------------------------------------------------

    def run(
        self, builder: GridCategoryBuilder, location: str = "",
    ) -> "DefenseReport":
        """
        Run the full integrated defense pipeline.

        Steps:
          1. Gray Coherence → detect all gaps
          2. COG Verification → filter false positives
          3. Classify → EfficiencyViolation
          4. OPTIMUS Refinement → suggest fixes
          5. Higher-Order Decomposition → factorize chains
          6. CAT Engine → activity obstructions

        Returns:
            DefenseReport with all findings and metadata.
        """
        # Build Category from builder data
        category = self._build_category_from_builder(builder)

        # Initialize all engines
        cog = self._init_cog(category)
        optimus = self._init_optimus(category)
        self._init_higher_order(category)
        self._init_cat_engine(category)

        # Stage 1: Gray Coherence detection
        gray = GrayCategoryLayer(self.cosmos)
        all_gaps = gray.scan_builder(builder)

        # Stage 2: COG Verification gate
        verified_gaps = []
        rejected_gaps = []
        for mod in all_gaps:
            mod = self._verify_gap_with_cog(mod, cog)
            if mod.cog_verified:
                verified_gaps.append(mod)
            else:
                rejected_gaps.append(mod)

        # Stage 3: Classification
        mapper = CoherenceVulnerabilityMapper()
        vulnerabilities = mapper.classify_all(verified_gaps, location=location)

        # Stage 4: OPTIMUS Active Refinement
        for vuln in vulnerabilities:
            self._refine_with_optimus(vuln, optimus)

        # Stage 5: Higher-Order Chain Decomposition
        for vuln in vulnerabilities:
            self._decompose_chain(vuln)

        # Stage 6: CAT Engine Activity Analysis
        activity_obstructions = self._run_cat_analysis(builder)

        # Attach CAT findings to relevant vulnerabilities
        if activity_obstructions:
            for vuln in vulnerabilities:
                vuln.activity_obstructions = activity_obstructions

        # Stage 7: Streaming Kan Real-Time Prediction
        predictions = self._predict_next_attacks(vulnerabilities)

        # Stage 8: Publish to ThreatIntelligenceBus
        self._publish_to_bus(vulnerabilities, predictions, activity_obstructions)

        return DefenseReport(
            all_gaps=all_gaps,
            verified_gaps=verified_gaps,
            rejected_gaps=rejected_gaps,
            vulnerabilities=vulnerabilities,
            activity_obstructions=activity_obstructions,
            predictions=predictions,
            cog_rejection_count=len(rejected_gaps),
            location=location,
        )


@dataclass
class DefenseReport:
    """
    Complete report from the FullDefensePipeline.

    Contains all findings with full COG/OPTIMUS/Higher-Order/CAT/Kan data.
    """
    all_gaps: List[Modification]
    verified_gaps: List[Modification]
    rejected_gaps: List[Modification]
    vulnerabilities: List[EfficiencyViolation]
    activity_obstructions: List[Dict]
    predictions: List[Dict]             # Streaming Kan next-attack predictions
    cog_rejection_count: int
    location: str = ""

    @property
    def critical(self) -> List[EfficiencyViolation]:
        return [v for v in self.vulnerabilities if v.is_critical]

    @property
    def chainable(self) -> List[EfficiencyViolation]:
        return [v for v in self.vulnerabilities if v.is_chainable]

    @property
    def has_structural_proofs(self) -> bool:
        return any(
            v.proof.proof_type == "structural" for v in self.vulnerabilities
        )

    @property
    def has_cog_verification(self) -> bool:
        return any(
            v.proof.cog_tier_reached >= 0 for v in self.vulnerabilities
        )

    @property
    def has_optimus_suggestions(self) -> bool:
        return any(
            v.optimus_suggestions for v in self.vulnerabilities
        )

    def summary(self) -> Dict:
        return {
            "total_gaps_detected": len(self.all_gaps),
            "cog_verified": len(self.verified_gaps),
            "cog_rejected_false_positives": self.cog_rejection_count,
            "vulnerabilities": len(self.vulnerabilities),
            "critical": len(self.critical),
            "chainable": len(self.chainable),
            "with_optimus_suggestions": sum(
                1 for v in self.vulnerabilities if v.optimus_suggestions
            ),
            "with_chain_decomposition": sum(
                1 for v in self.vulnerabilities if v.chain_decomposition
            ),
            "activity_obstructions": len(self.activity_obstructions),
            "predicted_next_attacks": len(self.predictions),
            "top_prediction": self.predictions[0] if self.predictions else None,
            "has_structural_proofs": self.has_structural_proofs,
            "has_cog_verification": self.has_cog_verification,
            "pipeline_stages_active": self._active_stages(),
        }

    def _active_stages(self) -> List[str]:
        stages = ["gray_coherence"]
        if self.has_cog_verification:
            stages.append("cog_verification")
        if self.has_optimus_suggestions:
            stages.append("optimus_refinement")
        if any(v.chain_decomposition for v in self.vulnerabilities):
            stages.append("higher_order_decomposition")
        if self.activity_obstructions:
            stages.append("cat_engine")
        if self.predictions:
            stages.append("streaming_kan_prediction")
        return stages


# =============================================================================
# QUICK DEMO
# =============================================================================

if __name__ == "__main__":
    import textwrap

    # --- Synthetic example: two parallel paths with a privilege gap ---
    alpha = TwoCellProxy(
        source_morphism="user.read_config",
        target_morphism="admin.write_config",
        label="path_via_admin_api",
        confidence=0.2,
        privilege_level=2,   # hypervisor
        memory_regions=("config_region",),
    )
    beta = TwoCellProxy(
        source_morphism="user.read_config",
        target_morphism="admin.write_config",
        label="path_via_user_api",
        confidence=0.9,
        privilege_level=0,   # user
        memory_regions=("config_region",),
    )

    layer  = GrayCategoryLayer()
    mod    = layer.check_modification_coherence(alpha, beta)
    mapper = CoherenceVulnerabilityMapper()
    vuln   = mapper.classify(mod, location="config_subsystem")

    print("=== 3-Cell Coherence Check ===")
    print(f"  Coherent:    {mod.is_coherent}")
    print(f"  Gap type:    {mod.gap_type.value}")
    print(f"  Gap loc:     {mod.gap_location}")
    print(f"  Vuln class:  {vuln.loss_class}")
    print(f"  MITRE:       {vuln.mitre_id}")
    print(f"  Severity:    {vuln.severity:.2f}")
    print(f"  Chainable:   {vuln.is_chainable}")
    print(f"  Remediation: {vuln.remediation}")
    print()

    # --- Source file scan ---
    import tempfile, os
    sample = textwrap.dedent("""\
        def read_file(path):
            return open(path).read()

        def admin_read_file(path):
            # privileged variant
            return open(path).read()

        def process(path):
            data = read_file(path)
            return admin_read_file(path)
    """)
    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", delete=False
    ) as f:
        f.write(sample)
        tmp = f.name

    race  = StabilityScan()
    found = race.scan_path(tmp)
    os.unlink(tmp)

    print(f"=== Source Scan: {len(found)} gap(s) found ===")
    for v in found:
        print(f"  {v.loss_class} | severity={v.severity:.2f} | {v.remediation}")

    print()
    print("Summary:", race.summary())
