# Ruliad Engine: Implementation Roadmap

**What this is:** The remaining ideas from the Ruliad Engine vision that aren't built yet.
Everything below applies the same categorical math (OPTIMUS, Yoneda, Kan, structural holes)
to the **system's own architecture** instead of just the knowledge graph.

**Author:** James Ray Hawkins
**Date:** 2026-04-05 (updated 2026-04-07, Post Formal Yoneda + Higher-Order OPTIMUS)

## Implementation Status

| # | Component | Status | File | Tests |
|---|-----------|--------|------|-------|
| 1 | Runtime Telemetry Collector | ✅ **DONE** | `bridges/telemetry_plugin.py` | 3/3 |
| 2 | Capability Graph Builder | ✅ **DONE** | `core/capability_graph.py` | 2/2 |
| 3 | Git History Analyzer | ✅ **DONE** | `core/architect.py` (GitArchitectureAnalyzer) | 2/2 |
| 4 | Linear Independence Test | ✅ **DONE** | `core/independence.py` | 3/3 |
| 5 | Fibration Lift Strategy | ✅ **DONE** | `oracle/fibration.py` | Integrated |
| 6 | Architectural Advisor | ✅ **DONE** | `core/architect.py` | Via integration tests |
| 7 | Platform Protocol Design | 🆕 Future | -- | -- |
| 8 | **InfinityCosmos Layer** | ✅ **DONE** | `core/cosmos.py` | 39/39 |
| 9 | **Higher-Order OPTIMUS** | ✅ **DONE (Levels 1-2)** | `core/higher_order_optimus.py` | 5/5 |
| 10 | **Formal Yoneda Proof** | ✅ **DONE** | `core/formal_yoneda.py` | 12/12 |

**Total: 8 of 8 buildable items completed (6 original + ∞-Cosmos + Higher-Order + Formal Yoneda).** 116/116 tests pass (zero regressions).

---

## 1. Runtime Telemetry Collector

**The idea:** Track what capabilities actually do at runtime so the system can observe itself.

**What to collect:**
- Capability co-occurrence: which plugins fire together in workflows
- Error co-location: which plugin boundaries produce errors
- Performance traces: latency per plugin per workflow
- Event co-subscription: which plugins listen to the same events
- Composition frequency: which capability chains get used most

**Implementation:**

```python
# bridges/telemetry_plugin.py

class TelemetryPlugin(Plugin):
    """Collect runtime signals for architectural self-observation."""

    def __init__(self, core, category: Category):
        super().__init__(core, name="telemetry", provides={"telemetry"})
        self.category = category  # Store telemetry AS a Category
        self.co_occurrence = {}   # (plugin_a, plugin_b) -> count
        self.error_log = []
        self.latency_log = []

    @hook("*", priority=0)  # Intercept ALL hooks
    async def trace_hook(self, data):
        """Record which plugin handled what, when, how long."""
        plugin_name = data.get("_plugin")
        event_name = data.get("_event")
        start = time.monotonic()
        # ... let it pass through ...
        elapsed = time.monotonic() - start

        # Store as morphism: plugin --handles--> event (confidence = 1/latency)
        self.category.connect(
            plugin_name, event_name,
            name=f"handles_{plugin_name}_{event_name}",
            confidence=1.0,
            metadata={"latency": elapsed, "count": 1}
        )

    @on("*.error")
    async def trace_error(self, event):
        """Record error boundaries."""
        self.error_log.append({
            "source_plugin": event.data.get("plugin"),
            "error": str(event.data.get("error")),
            "timestamp": time.time(),
        })

    def co_occurrence_matrix(self) -> dict:
        """Which plugins fire together in the same workflow?"""
        # Built from hook trace windows
        return self.co_occurrence

    def error_boundaries(self) -> list:
        """Which plugin boundaries produce the most errors?"""
        # Aggregate error_log by (source_plugin, target_plugin) pairs
        return self.error_log
```

**Key point:** Store telemetry AS a Category. Then OPTIMUS can operate on it directly.

---

## 2. Capability Graph Builder

**The idea:** Construct a Category from Orion's plugin metadata so categorical strategies can analyze the system's own structure.

**What goes in the graph:**
- Objects = plugins (capabilities)
- Morphisms = dependency edges (requires/provides)
- Co-occurrence morphisms from telemetry (weighted by frequency)
- Git co-modification morphisms (weighted by commit count)
- Error morphisms (weighted negatively)

**Implementation:**

```python
# core/capability_graph.py

class CapabilityGraphBuilder:
    """Build a Category representing the system's own architecture."""

    def __init__(self, orion_core, telemetry_category=None):
        self.orion = orion_core
        self.telemetry = telemetry_category
        self.graph = Category(db_path=":memory:")

    async def build(self) -> Category:
        """Snapshot current architecture as a Category."""
        plugins = await self.orion.list()

        # Objects = capabilities
        for plugin in plugins:
            self.graph.add(plugin.name, type_name="capability",
                           metadata={"provides": list(plugin.provides)})

        # Morphisms = declared dependencies (requires -> provides)
        for plugin in plugins:
            for required in plugin.requires:
                # Find who provides this
                providers = [p for p in plugins if required in p.provides]
                for provider in providers:
                    self.graph.connect(
                        plugin.name, provider.name,
                        name=f"requires_{required}",
                        confidence=1.0,
                        metadata={"relation": "requires", "capability": required}
                    )

        # Morphisms from telemetry (co-occurrence, weighted)
        if self.telemetry:
            for mor in self.telemetry.morphisms():
                self.graph.connect(
                    mor.source, mor.target,
                    name=f"cooccurs_{mor.name}",
                    confidence=mor.confidence,
                    metadata={"relation": "co_occurrence"}
                )

        return self.graph

    def add_git_signals(self, git_comod: dict):
        """Add git co-modification signals.

        git_comod: {("plugin_a", "plugin_b"): commit_count}
        """
        max_count = max(git_comod.values()) if git_comod else 1
        for (a, b), count in git_comod.items():
            self.graph.connect(
                a, b,
                name=f"git_comod_{a}_{b}",
                confidence=count / max_count,
                metadata={"relation": "git_co_modification", "commits": count}
            )
```

---

## 3. Git History Analyzer

**The idea:** Parse git history to find architectural signals -- which files change together, what experiments failed, where refactors happened.

**Implementation:**

```python
# tools/git_analyzer.py

import subprocess
import json
from collections import defaultdict

class GitArchitectureAnalyzer:
    """Extract architectural signals from git history."""

    def __init__(self, repo_path="."):
        self.repo_path = repo_path

    def co_modification_matrix(self, since="6 months ago") -> dict:
        """Which files/modules change together across commits?

        Returns: {("module_a", "module_b"): commit_count}
        """
        # git log --name-only --format="" --since="6 months ago"
        result = subprocess.run(
            ["git", "log", "--name-only", "--format=COMMIT_SEP",
             f"--since={since}"],
            capture_output=True, text=True, cwd=self.repo_path
        )

        commits = result.stdout.split("COMMIT_SEP")
        comod = defaultdict(int)

        for commit in commits:
            files = [f.strip() for f in commit.strip().split("\n") if f.strip()]
            modules = set(self._file_to_module(f) for f in files)
            modules.discard(None)
            for a in modules:
                for b in modules:
                    if a < b:
                        comod[(a, b)] += 1

        return dict(comod)

    def abandoned_experiments(self, since="6 months ago") -> list:
        """Find branches/commits that were reverted or abandoned."""
        # git log --diff-filter=D to find deleted files
        result = subprocess.run(
            ["git", "log", "--diff-filter=D", "--name-only",
             "--format=%H %s", f"--since={since}"],
            capture_output=True, text=True, cwd=self.repo_path
        )
        return result.stdout.strip().split("\n")

    def refactor_frequency(self) -> dict:
        """Which modules get refactored most? (proxy: rename/move operations)"""
        result = subprocess.run(
            ["git", "log", "--diff-filter=R", "--name-status", "--format="],
            capture_output=True, text=True, cwd=self.repo_path
        )
        # Parse rename operations
        renames = defaultdict(int)
        for line in result.stdout.strip().split("\n"):
            if line.startswith("R"):
                parts = line.split("\t")
                if len(parts) >= 3:
                    module = self._file_to_module(parts[2])
                    if module:
                        renames[module] += 1
        return dict(renames)

    def _file_to_module(self, filepath: str) -> str:
        """Map a file path to its top-level module."""
        parts = filepath.split("/")
        if len(parts) >= 2 and parts[0] in (
            "core", "cog", "bridges", "categorical", "oracle",
            "domains", "topology", "geometry", "hott", "zfc",
            "cubical", "game", "data", "aimo"
        ):
            return parts[0]
        if filepath.endswith(".py") and "/" not in filepath:
            return filepath.replace(".py", "")
        return None
```

---

## 4. Architectural Self-Correction (OPTIMUS on Capability Graph)

**The idea:** Run the same OPTIMUS engine on the capability graph to find wrong boundaries, missing primitives, and redundant capabilities.

**Implementation:**

```python
# core/architect.py

from core.optimus import OptimusEngine
from core.capability_graph import CapabilityGraphBuilder
from tools.git_analyzer import GitArchitectureAnalyzer

class ArchitecturalAdvisor:
    """The self-correction loop from the Ruliad essay.

    observe -> identify wrong boundaries -> propose -> validate -> repeat
    """

    def __init__(self, orion_core, telemetry_category=None, repo_path="."):
        self.orion = orion_core
        self.telemetry = telemetry_category
        self.git = GitArchitectureAnalyzer(repo_path)

    async def analyze(self) -> dict:
        """Run one cycle of architectural self-observation."""

        # 1. Build capability graph from all signal sources
        builder = CapabilityGraphBuilder(self.orion, self.telemetry)
        cap_graph = await builder.build()
        builder.add_git_signals(self.git.co_modification_matrix())

        # 2. Run OPTIMUS on the capability graph
        engine = OptimusEngine(cap_graph, max_depth=3)

        # Structural holes = missing capabilities
        gaps = engine.find_structural_gaps()

        # Factorization = redundant capabilities (can be expressed as composition)
        refinement = engine.refine(max_steps=20, depth=2)

        # Yoneda = capabilities that should share an interface
        duplicates = []
        objects = list(cap_graph.objects())
        for i, a in enumerate(objects):
            for b in objects[i+1:]:
                sim = engine.yoneda_similarity(a.name, b.name)
                if sim > 0.8:
                    duplicates.append({
                        "a": a.name, "b": b.name,
                        "similarity": sim,
                        "recommendation": f"{a.name} and {b.name} may be the same primitive"
                    })

        # Git: capabilities that always change together = wrong boundary
        comod = self.git.co_modification_matrix()
        coupled = [
            {"a": a, "b": b, "commits": count,
             "recommendation": f"{a} and {b} always change together -- missing shared primitive?"}
            for (a, b), count in sorted(comod.items(), key=lambda x: -x[1])[:10]
            if count > 5
        ]

        return {
            "structural_gaps": gaps[:20],
            "factorization_improvements": refinement,
            "yoneda_duplicates": duplicates,
            "git_coupling": coupled,
            "recommendations": self._synthesize(gaps, duplicates, coupled),
        }

    def _synthesize(self, gaps, duplicates, coupled) -> list:
        """Turn raw signals into actionable recommendations."""
        recs = []

        for gap in gaps[:5]:
            recs.append({
                "type": "missing_primitive",
                "description": f"No direct {gap['source']}->{gap['target']} capability. "
                               f"Currently requires going through {gap['via']}. "
                               f"Consider adding a direct capability.",
                "confidence": gap["path_confidence"],
            })

        for dup in duplicates:
            recs.append({
                "type": "redundant_capability",
                "description": f"{dup['a']} and {dup['b']} are structurally equivalent "
                               f"(Yoneda similarity {dup['similarity']:.2f}). "
                               f"Consider merging or sharing an interface.",
                "confidence": dup["similarity"],
            })

        for coup in coupled:
            recs.append({
                "type": "wrong_boundary",
                "description": f"{coup['a']} and {coup['b']} are modified together in "
                               f"{coup['commits']} commits. A shared primitive may be missing.",
                "confidence": min(coup["commits"] / 20, 1.0),
            })

        return sorted(recs, key=lambda r: -r["confidence"])
```

**Usage:**
```python
advisor = ArchitecturalAdvisor(agent.orion, telemetry_cat, repo_path=".")
report = await advisor.analyze()

for rec in report["recommendations"]:
    print(f"[{rec['type']}] {rec['description']} (conf={rec['confidence']:.2f})")
```

---

## 5. Fibration Lift Strategy

**The idea:** Predict edges by lifting structure from a simpler domain (type-level) into a richer one (instance-level). Patterns that hold at the capability-type level should hold at specific implementations.

**Implementation:**

```python
# oracle/fibration.py

class FibrationLiftStrategy:
    """Predict morphisms by lifting from a base category to a fiber category.

    If a pattern holds at the type level (e.g., "all search plugins
    connect to storage plugins"), it should hold at the instance level
    (e.g., "arxiv_search should connect to vector_store").

    The base category is the type-level graph (capability types).
    The fiber category is the instance-level graph (specific plugins).
    The fibration is the type assignment: plugin -> its capability type.
    """

    def __init__(self, base_category: Category, fiber_category: Category,
                 projection: dict):
        """
        Args:
            base_category: Type-level graph (objects = capability types)
            fiber_category: Instance-level graph (objects = specific plugins)
            projection: {instance_name: type_name} mapping
        """
        self.base = base_category
        self.fiber = fiber_category
        self.proj = projection

    def lift_predictions(self, min_confidence=0.5) -> list:
        """Predict missing instance-level edges from type-level patterns.

        For each morphism T_A -> T_B in the base:
            For each instance a of T_A and b of T_B:
                If no morphism a -> b exists in fiber:
                    Predict it, with confidence = base morphism confidence.
        """
        predictions = []
        inv_proj = {}
        for inst, typ in self.proj.items():
            inv_proj.setdefault(typ, []).append(inst)

        for base_mor in self.base.morphisms():
            if base_mor.confidence < min_confidence:
                continue

            sources = inv_proj.get(base_mor.source, [])
            targets = inv_proj.get(base_mor.target, [])

            for src_inst in sources:
                for tgt_inst in targets:
                    # Check if this edge already exists
                    existing = self.fiber.morphisms_from(src_inst)
                    has_edge = any(m.target == tgt_inst for m in existing)

                    if not has_edge:
                        predictions.append({
                            "source": src_inst,
                            "target": tgt_inst,
                            "lifted_from": base_mor.name,
                            "type_source": base_mor.source,
                            "type_target": base_mor.target,
                            "confidence": base_mor.confidence,
                        })

        return sorted(predictions, key=lambda p: -p["confidence"])
```

---

## 6. Linear Independence Test

**The idea:** Automatically test whether a new capability is truly primitive or just a composition of existing ones.

**Implementation:**

```python
# core/independence.py

class LinearIndependenceTest:
    """Test whether a capability is a genuine primitive or a derived pattern.

    From the Ruliad essay:
        Can this be expressed as a composition of existing capabilities?
        Yes -> it's a pattern (document it, don't add it as a primitive)
        No  -> it's a new primitive (add it to the basis)
    """

    def __init__(self, capability_graph: Category):
        self.graph = capability_graph

    def is_independent(self, new_cap_source: str, new_cap_target: str,
                       max_path_length: int = 4) -> dict:
        """Test if a proposed capability is linearly independent.

        Args:
            new_cap_source: What the capability takes as input
            new_cap_target: What the capability produces as output
            max_path_length: Max composition length to search

        Returns:
            {"independent": bool, "existing_paths": [...], "recommendation": str}
        """
        paths = self.graph.find_paths(
            new_cap_source, new_cap_target, max_length=max_path_length
        )

        if not paths:
            return {
                "independent": True,
                "existing_paths": [],
                "recommendation": "NEW PRIMITIVE: No existing composition reaches this. Add it."
            }

        best_path = max(paths, key=lambda p: p.weight)

        if best_path.weight > 0.8:
            return {
                "independent": False,
                "existing_paths": [
                    {"morphisms": p.morphism_ids, "weight": p.weight}
                    for p in paths
                ],
                "recommendation": f"PATTERN: Already reachable via "
                                  f"{' -> '.join(best_path.morphism_ids)} "
                                  f"(confidence {best_path.weight:.2f}). "
                                  f"Document as named pattern, don't add as primitive."
            }

        return {
            "independent": True,  # Exists but weak -- new primitive fills a real gap
            "existing_paths": [
                {"morphisms": p.morphism_ids, "weight": p.weight}
                for p in paths
            ],
            "recommendation": f"WEAK COVERAGE: Existing paths are low-confidence "
                              f"(best={best_path.weight:.2f}). "
                              f"New primitive would strengthen the basis."
        }
```

---

## 7. The Platform (Future)

**The idea:** Scale from single-agent to collective exploration. This is the long-term vision. Not buildable now, but the interfaces should be designed.

**Key components to design later:**

### 7a. Shared Category Protocol
```python
class SharedCategoryProtocol:
    """Protocol for contributing morphisms to a shared global Category."""
    def publish_morphism(self, morphism, privacy_budget): ...
    def subscribe_to_domain(self, domain_filter): ...
    def query_global(self, source, target): ...
```

### 7b. Differential Privacy Layer
```python
class PrivacyPreservingContributor:
    """Add noise to morphism confidence before sharing."""
    def contribute(self, morphism, epsilon=1.0):
        noised_confidence = morphism.confidence + laplace_noise(epsilon)
        return sanitized_morphism(morphism, noised_confidence)
```

### 7c. Collective OPTIMUS
```python
class CollectiveOptimus:
    """Run OPTIMUS on the aggregate graph from all users."""
    def aggregate_and_refine(self, user_categories: list[Category]):
        merged = merge_categories(user_categories)
        engine = OptimusEngine(merged)
        return engine.refine()  # Discoveries benefit everyone
```

### 7d. Demand Signal Aggregator
```python
class DemandAggregator:
    """Aggregate failed compositions across users to find missing primitives."""
    def record_failure(self, user_id, source_cap, target_cap, error): ...
    def missing_primitive_specs(self, min_users=10) -> list:
        """Return specs for capabilities that multiple users need but don't exist."""
        ...
```

---

## Implementation Order

| Priority | Component | Depends On | Effort | Status |
|----------|-----------|------------|--------|--------|
| 1 | Runtime Telemetry Collector | Orion hooks | 1-2 days | ✅ DONE |
| 2 | Capability Graph Builder | Telemetry + Orion plugin API | 1-2 days | ✅ DONE |
| 3 | Git History Analyzer | git CLI | 1 day | ✅ DONE |
| 4 | Linear Independence Test | Capability Graph | 1 day | ✅ DONE |
| 5 | Fibration Lift Strategy | Two Categories (base + fiber) | 1-2 days | ✅ DONE |
| 6 | Architectural Advisor | Items 1-5 | 2-3 days | ✅ DONE |
| 7 | Platform Protocol Design | Everything above | Weeks-months | 🆕 Future |
| 8 | **InfinityCosmos Layer** | Category + Riehl-Verity | 2-3 weeks | ✅ DONE (Phase 1) |
| 9 | **Higher-Order OPTIMUS** | InfinityCosmos + TwoCategory | 1-2 weeks | ✅ DONE (Levels 1-2, 3-4 placeholders) |
| 10 | **Formal Yoneda Proof** | InfinityCosmos + PresheafTopos | 1 week | ✅ DONE |

Items 1-6 are complete. Item 7 is the long-term play. Item 8 (∞-Cosmos) Phase 1 is complete. Items 9-10 (Higher-Order OPTIMUS, Formal Yoneda) are complete.

---

## How It All Connects

```
Git History ──────┐
                  v
Runtime Telemetry ──> Capability Graph Builder ──> Category (of capabilities)
                  ^                                       |
Orion Plugins ────┘                                       v
                                                   OptimusEngine.refine()
                                                   OptimusEngine.find_structural_gaps()
                                                   FibrationLiftStrategy.lift_predictions()
                                                   LinearIndependenceTest.is_independent()
                                                          |
                                                          v
                                                   ArchitecturalAdvisor.analyze()
                                                          |
                                                          v
                                                   Recommendations:
                                                   - Missing primitives
                                                   - Redundant capabilities
                                                   - Wrong boundaries
                                                   - Predicted edges (fibration)
```

**The key insight:** OPTIMUS already does all the hard math. The remaining work is
feeding it the right graph (capabilities instead of knowledge) and collecting the
right signals (git + runtime instead of manual input).

Same engine. Different target. That's the Ruliad vision.
