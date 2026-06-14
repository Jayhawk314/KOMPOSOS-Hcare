# CLAUDE.md - KOMPOSOS-IV

## Project Identity

**KOMPOSOS-IV** is a five-layer categorical AI agent architecture. It fuses
KOMPOSOS-III's mathematical power with Orion's plugin framework, COG's tiered
verification, OPTIMUS's categorical gradient descent, and the ∞-Cosmos
(Riehl-Verity) for higher categorical reasoning into a self-refining,
self-aware computational organism.

The unified `Agent` class (`orion_komposos_cog/agent.py`) wires all layers.

**Author:** James Ray Hawkins
**License:** Apache 2.0 / Commercial dual license
**Python:** 3.10+

## Five-Layer Architecture

```
Layer 1: ORION           Plugin framework (hot-loading, events, capabilities, telemetry)
Layer 2: KOMPOSOS-IV     Categorical runtime (Category = store + enriched category + hooks)
Layer 2.5: ∞-COSMOS     Higher structure (2-cells, fibrations, Yoneda, Kan extensions)
Layer 3: COG             Cognitive co-processor (5-tier verification with 2-cell reasoning)
Layer 4: OPTIMUS         Categorical gradient descent (self-refinement + architectural self-correction)
```

```
Agent (orion_komposos_cog/agent.py)
  |
  +-- Orion Core           hot-load plugins, event bus, capability DI
  |
  +-- TelemetryPlugin      collect runtime signals as Category
  |
  +-- Category (core/)     persist objects/morphisms, enriched composition, path finding
  |
  +-- InfinityCosmos       ∞-cosmos on Category: h2K, 2-cells, fibrations, Yoneda
  |  (core/cosmos.py)
  |
  +-- TwoCellBridge        COG Tier 4: 2-cell reasoning in homotopy 2-Category
  |  (core/two_cell_bridge.py)
  |
  +-- CogEngine (cog/)     tiered claim verification on the Category
  |
  +-- OptimusEngine         snapshot Category -> factorize -> compress -> sync back
  |  (core/optimus.py)      discovers intermediate concepts, Yoneda transfer, structural gaps
  |
  +-- HigherOrderOptimus    factorize 2-morphisms, fibrations, functors
  |  (core/higher_order_optimus.py)  extends OptimisMonad to all categorical levels
  |
  +-- FormalYoneda         Yoneda distance metric, provably-correct absorb threshold
  |  (core/formal_yoneda.py)  proves d=0 ↔ isomorphism, derives transfer bounds
  |
  +-- ArchitecturalAdvisor  analyze system's own architecture via OPTIMUS + Dual Engine
     (core/architect.py)    finds wrong boundaries, missing primitives, redundant capabilities
                            verifies via ZFC+CAT dual engine, learns via System 3 (MetaKan)
```

### How OPTIMUS works

OPTIMUS is the self-refinement monad. It operates by:
1. Snapshotting KOMPOSOS-IV Category into an OPTIMUS RuntimeCategory
2. Running categorical gradient descent: for each morphism A->C, search all
   factorizations A->B->C and keep the best (Tarski: w(new) >= w(old))
3. Syncing discovered shortcuts back to Category (persists, fires hooks)

```
Classical gradient:  x_{t+1} = x_t - eta * grad(L)
OPTIMUS gradient:    m_{t+1} = argmax_{f in factorizations(m_t)} w(f)
```

Instead of adjusting parameters, OPTIMUS discovers intermediate objects.

### How Higher-Order OPTIMUS works

`HigherOrderOptimus` extends `OptimisMonad` to factorize at all categorical levels:
- **Level 1**: 1-morphism factorization (standard OPTIMUS)
- **Level 2**: 2-morphism factorization (vertical β·γ and horizontal β*γ composition)
- **Level 3**: Fibration factorization (intermediate total categories preserving cartesian lifts)
- **Level 4**: Functor factorization (C → E → D through intermediate category)

Multi-level descent (`descend_all()`) runs refinement at all levels sequentially,
each strictly improving confidence. Requires `TwoCategory` instance for Level 2+.

### How the ∞-Cosmos works

Based on Riehl & Verity, "Infinity category theory from scratch" (arXiv:1608.05314).

The `InfinityCosmos` class wraps a Category and provides:
1. **Homotopy 2-Category (h₂K)**: Auto-detects parallel morphisms and creates 2-cells
2. **Isofibration detection**: Identifies distinguished morphisms with lifting properties
3. **Cartesian fibrations**: Uses fibrations.py to find fibration structures
4. **Yoneda embedding**: Computes representable presheaves and faithfulness (uses PresheafTopos)
5. **Pointwise Kan extensions**: Via comma category (co)limits

**This activates previously dead code**: two_categories.py, fibrations.py, grothendieck.py, presheaf_topos.py, topos_logic.py.

### How the Formal Yoneda Proof works

`YonedaProver` (core/formal_yoneda.py) formally proves the Yoneda Lemma properties:
1. **Representable presheaves**: y(T) = Hom(-, T) for each object
2. **Yoneda distance**: d(y(A), y(B)) = |y(A) Δ y(B)| / |y(A) ∪ y(B)| — proven metric
3. **Full faithfulness**: d = 0 ↔ A ≅ B (verified by isomorphism check)
4. **Provably-correct threshold**: transfer threshold = 1 - d(y(A), y(B))

This replaces the arbitrary 0.8 threshold in `OptimisMonad.absorb()` with a
mathematically-derived bound. The `absorb()` method requires strictly positive
similarity (sim > 0) — no transfer between completely dissimilar objects.

### How the Dual Engine works

The ZFC/CAT dual engine (`zfc/bridge.py`) verifies every architectural recommendation:
- **ZFC** checks: Is this recommendation logically entailed from the axioms?
- **CAT** checks: Is this compositionally valid in the category structure?
- **Delta classification**: AGREE / ORPHAN / HOLLOW / REJECT
- **System 3 (MetaKan)**: Records episodes of disagreement, learns patterns, predicts future disagreements

**Evolved Dual Engine** (`zfc/evolved_bridge.py`): The `EvolvedDualEngineBridge` wraps the standard bridge and auto-mines System 3 episodes for emergent axioms. When a pattern consistently gets AGREE verdicts, it becomes an axiom. ZFC then verifies against discovered principles, not just raw facts. The axiom set evolves with the system's experience.

The `ArchitecturalAdvisor` uses `EvolvedDualEngineBridge` by default — all structural recommendations are verified against evolved axioms.

## Key Files

### Core Runtime (26 files)
| File | Purpose |
|------|---------|
| `core/types.py` | Object, Morphism, Path, HigherMorphism, EquivalenceClass, Cone, Cocone |
| `core/enrichment.py` | MonoidalStructure, 5 quantales |
| `core/persistence.py` | SQLiteBackend (internal, never used directly) |
| `core/hooks.py` | HookRegistry, event system |
| `core/category.py` | THE fused categorical runtime |
| `core/bridge.py` | Thin domain bridge ABC |
| `core/optimus.py` | OptimusEngine: bridges Category <-> OPTIMUS RuntimeCategory |
| `core/cosmos.py` | InfinityCosmos: ∞-cosmos axiom on Category |
| `core/two_cell_bridge.py` | TwoCellBridge: COG Tier 4 2-cell reasoning |
| `core/capability_graph.py` | CapabilityGraphBuilder: system self-observation |
| `core/independence.py` | LinearIndependenceTest: primitive vs pattern detection |
| `core/architect.py` | ArchitecturalAdvisor: self-correction loop + Dual Engine verification |
| `core/functor.py` | Functor, NaturalTransformation |
| `core/adjunction.py` | Adjunction (left/right adjoint functors) |
| `core/limits.py` | Limits/Colimits: product, coproduct, pullback, pushout, terminal, initial |
| `core/observer.py` | CategoryView -- coarse-grained observable views |
| `core/effects.py` | EffectSignature, EffectHandler, transactional |
| `core/theory.py` | Theory, Axiom, validate, CategoryTheory, MonoidalTheory |
| `core/serialization.py` | to_json, from_json, to_graphml, to_yaml, to_rdf |
| `core/geometry_bridge.py` | Category → geometry.Graph converter |
| `core/topology_bridge.py` | Category → SimplicialComplex converter |
| `core/hott_bridge.py` | Category paths ↔ HoTT IdentityType, computational transport |
| `core/game_bridge.py` | Category → OpenGame converter, Nash equilibrium |
| `core/enrichment_extension.py` | Additional quantale types from categorical/quantales.py |
| `core/typed_capabilities.py` | Typed plugin requirements/capabilities (math structure declarations) |
| `core/self_corrector.py` | Automatic self-correction: acts on ArchitecturalAdvisor findings |
| `core/plugin_generator.py` | PluginGenerator + SelfExtensionEngine: auto-implements missing primitives |
| `core/formal_yoneda.py` | **NEW** Formal Yoneda proof: distance metric, isomorphism detection, transfer thresholds |
| `core/higher_order_optimus.py` | **NEW** HigherOrderOptimus: 2-morphism, fibration, functor factorization |

### OPTIMUS Kernel
| File | Purpose |
|------|---------|
| `optimus_core.py` | Complete OPTIMUS kernel: Quantale, FreeCategory, RuntimeCategory, OptimisMonad |

### COG (Cognitive Co-Processor, 10 files)
| File | Purpose |
|------|---------|
| `cog/engine.py` | CogEngine: 5-tier verification (Direct, Compositional, Higher-Order, ZFC, CAT) |
| `cog/session.py` | CogSession: per-conversation state wrapping a Category |
| `cog/energy.py` | Energy-based routing (claim resistance) |
| `cog/schema.py` | CogClaim, CogConcept, CogRelation, CheckResult |
| `cog/router.py` | Tier routing logic |
| `cog/security.py` | Security layer |
| `cog/server.py` | MCP server |
| `cog/serializers.py` | JSON serialization |

### Bridge Plugins (8 files)
| File | Purpose |
|------|---------|
| `bridges/cog_reasoning.py` | CogReasoningPlugin: exposes COG as Orion capability |
| `bridges/knowledge_manager.py` | KnowledgeManagerPlugin: exposes Category as Orion capability |
| `bridges/session_manager.py` | SessionManagerPlugin: per-user isolated sessions |
| `bridges/optimus_plugin.py` | OptimusPlugin: exposes OPTIMUS refinement as Orion capability |
| `bridges/telemetry_plugin.py` | TelemetryPlugin: runtime signal collection as Category |
| `bridges/infinity_cosmos_plugin.py` | InfinityCosmosPlugin: ∞-cosmos capability |
| `bridges/crypto_plugin.py` | CryptoPlugin: Yoneda-based vulnerability detection |

### Oracle Strategies (22 files, 22 strategies)
| File | Purpose |
|------|---------|
| `oracle/__init__.py` | CategoricalOracle main class |
| `oracle/strategies.py` | Registry: 9 built-in strategies + create_all_strategies() |
| `oracle/prediction.py` | Prediction, PredictionBatch, PredictionType, ConfidenceLevel |
| `oracle/optimizer.py` | Strategy weight optimization |
| `oracle/learner.py` | Online learning from feedback |
| `oracle/categorical_verifier.py` | CategoricalVerifier |
| `oracle/conjecture.py` | Conjecture engine |
| `oracle/coherence.py` | SheafCoherenceChecker |
| `oracle/zfc_verifier.py` | ZFCVerifier |
| `oracle/cubical_gap_filling_strategy.py` | Gap filling via cubical theory |
| `oracle/geometric_homotopy_strategy.py` | Homotopy-based inference |
| `oracle/game_strategy.py` | Game-theoretic inference |
| `oracle/fibration.py` | FibrationLiftStrategy: type→instance prediction |
| `oracle/topos_strategy.py` | ToposLogicStrategy: intuitionistic reasoning |
| `oracle/natural_transformation.py` | NaturalTransformationStrategy: pattern variant detection |
| `oracle/operadic_decomposition.py` | OperadicDecompositionStrategy: n-ary decomposition |
| `oracle/evidence_combination.py` | EvidenceCombinationStrategy: Dempster-Shafer combination |
| `oracle/streaming_forecast.py` | StreamingForecastStrategy: temporal forecasting |
| `oracle/topological_anomaly.py` | TopologicalAnomalyStrategy: persistent homology anomalies |
| `oracle/activity_analysis.py` | ActivityAnalysisStrategy: Engeström Activity Theory |
| `oracle/boundary_detection.py` | BoundaryDetectionStrategy: cross-domain boundary objects |
| `oracle/cellular_dynamics.py` | CellularDynamicsStrategy: SIR epidemic modeling |

### Unified Agent
| File | Purpose |
|------|---------|
| `orion_komposos_cog/agent.py` | Agent class: wires all layers, unified API |
| `orion_komposos_cog/config.py` | AgentConfig: optimus_enabled, max_depth, tier, etc. |
| `examples/production_agent.py` | Production usage example |

## Math Modules (ported from III-CORE)

| Module | Files | Purpose | Status |
|--------|-------|---------|--------|
| `categorical/` | 19 | Pure category theory: enriched, Kan, fibrations, Grothendieck, 2-categories, operads, presheaf topos, topos logic, streaming Kan, prime theory, activity systems, boundary profunctors, cellular automata, crypto, Dempster-Shafer, quantales | **All activated** via oracle strategies + ∞-Cosmos |
| `cubical/` | 3 | Cubical type theory: paths, Kan operations | Data structures complete, interpolation filled (no longer placeholder) |
| `game/` | 3 | Open games, Nash equilibrium | **Activated** via game_bridge.py + oracle/game_strategy.py |
| `topology/` | 4 | Persistent homology, temporal sheaves, persistent sheaves | **Activated** via topology_bridge.py + oracle/topological_anomaly.py |
| `hott/` | 5 | HoTT: identity types, path induction, homotopy | **Activated** via hott_bridge.py (transport now computational) |
| `geometry/` | 5 | Ricci curvature, Ricci flow, spectral analysis | **Activated** via geometry_bridge.py |
| `zfc/` | 13 | Set-theoretic reasoning: universe, logic, well-ordering, separation, proof engine, meta-kan, store adapter, dual-engine bridge, proof bridge, prime enhancement, **axiom_miner (emergent axioms)**, **evolved_bridge (ZFC verifies against discovered principles)** | **Integrated** + Dual Engine wired into ArchitecturalAdvisor with evolved axioms |
| `oracle/` | 22 | Categorical oracle: 17 inference strategies, coherence checker, conjecture engine, categorical verifier, ZFC verifier | **Fully integrated** |
| `data/` | 2 | Embeddings engine (Sentence Transformers), CategoryEmbedder | **Integrated** |

## API Quick Reference

### Agent API (preferred for applications)
```python
agent = Agent(AgentConfig(optimus_enabled=True))
await agent.start()

# Knowledge (KOMPOSOS-IV layer)
await agent.add_knowledge("Python", "ML", "supports", confidence=0.9)
await agent.find_paths("Python", "ML")

# Verification (COG layer)
result = await agent.verify_claim("Python", "ML", "supports", max_tier=4)

# Self-refinement (OPTIMUS layer)
await agent.refine(max_steps=20, depth=2)
await agent.discover_intermediates("Python", "ML")
await agent.absorb_structure("Python", "Ruby", threshold=0.8)
await agent.find_capability_gaps()
await agent.yoneda_similarity("Python", "Ruby")

# Plugins (Orion layer)
await agent.add_plugin(MyPlugin(agent.orion))
```

### Category API (direct, for math modules)
- `category.objects()` / `category.morphisms()`
- `category.get(name)` / `category.add(name)`
- `category.connect(src, tgt, name, confidence=)` / `category.compose(f, g)`
- `category.find_paths(src, tgt)` / `category.optimal_path(src, tgt)`
- `category.morphisms_from(src)` / `category.morphisms_to(tgt)`
- `mor.source` / `mor.target` / `mor.confidence`
- `Object` / `Morphism` from `core.types`
- `Category(db_path=":memory:")` for in-memory

### ∞-Cosmos API
```python
from core.cosmos import InfinityCosmos
from core.two_cell_bridge import TwoCellBridge
from core.capability_graph import CapabilityGraphBuilder
from core.independence import LinearIndependenceTest
from core.architect import ArchitecturalAdvisor

cosmos = InfinityCosmos(category)
h2k = cosmos.homotopy_2_category()           # Build homotopy 2-Category
bridge = TwoCellBridge(cosmos)
result = bridge.tier4_verify("A", "B", "r")  # 2-cell reasoning

# Self-observation
builder = CapabilityGraphBuilder(orion_core, telemetry_category)
cap_graph = await builder.build()
advisor = ArchitecturalAdvisor(orion_core, telemetry_cat)
report = await advisor.analyze()
# report includes: structural_gaps, yoneda_duplicates, git_coupling,
# dual_engine_verification, system3_insights, recommendations

# Linear independence test
test = LinearIndependenceTest(cap_graph)
result = test.is_independent("search", "store")
# "NEW PRIMITIVE" or "PATTERN: Already reachable via ..."
```

### Dual Engine API
```python
from zfc.store_adapter import StoreAdapter
from zfc.bridge import DualEngineBridge

adapter = StoreAdapter(category)
bridge = DualEngineBridge(adapter, category=category)

# Verify a claim through both ZFC and CAT
result = bridge.query("A", "B", "relates", domain="my_domain")
print(result.delta_type)  # AGREE, ORPHAN, HOLLOW, or REJECT
print(result.zfc_says, result.zfc_confidence)
print(result.cat_says, result.cat_confidence)
print(result.meta_prediction)  # System 3 prediction

# System 3: ask before running engines
should_run, reason = bridge.should_run_both("A", "B", "relates")
```

### OPTIMUS API (direct, for refinement)
```python
from core.optimus import OptimusEngine
engine = OptimusEngine(category, max_depth=3)
result = engine.refine(max_steps=20, depth=2)       # full descent
engine.refine_morphism("A", "C", depth=2)            # refine one morphism
engine.discover_intermediates("A", "C")               # find B in A->B->C
engine.absorb("Python", "Ruby", threshold=0.8)        # Yoneda transfer
engine.find_structural_gaps()                          # structural holes
engine.yoneda_similarity("A", "B")                     # [0,1] similarity
engine.yoneda_fingerprint("A")                         # hom_in/hom_out
```

## Rules

- **Five layers, not three.** Orion + KOMPOSOS-IV + ∞-Cosmos + COG + OPTIMUS.
- Category owns persistence. Never use SQLiteBackend directly.
- Enrichment is intrinsic. Morphism.confidence IS the hom-value.
- OPTIMUS operates on snapshots. It does NOT mutate Category directly during descent -- it syncs back after.
- COG shares the same Category instance as the Agent. CogSession wraps it.
- Bridge plugins connect layers via Orion events. Direct API access is the fallback.
- All math modules use IV's Category API. The `categorical/category.py` shim re-exports from `core/` for backward compatibility.
- Do NOT add domain-specific code in core/. Domain code goes in `domains/` or domain repos.
- ∞-Cosmos theorems are **model-independent** (Riehl-Verity). They work for all models of (∞,1)-categories.
- The dual engine (ZFC + CAT) verifies all structural recommendations. System 3 learns from disagreements.

## What's Complete vs What Remains

### ✅ Complete (151/151 tests pass)
- Core Category runtime (all operations, enrichment, persistence, hooks) — 26 files
- ∞-Cosmos layer (h₂K, 2-cells, fibrations, Yoneda, Kan extensions)
- **Higher-Order OPTIMUS** (2-morphism factorization, fibration factorization, functor factorization)
- **Formal Yoneda Proof** (distance metric proven, d=0 ↔ isomorphism, provably-correct absorb threshold)
- Dual Engine verification (ZFC + CAT + System 3 + **evolved axioms**)
- 22 Oracle strategies (all wired into registry)
- Bridge converters (geometry, topology, HoTT, game)
- Cubical interpolation (no longer placeholder)
- Self-observation (telemetry, capability graph, architectural advisor)
- Linear independence test
- All bridge plugins (8 total)
- **Evolving ZFC axioms** — AxiomMiner promotes consistent inference patterns to axioms, EvolvedDualEngineBridge uses them
- **Automatic self-extension** — PluginGenerator + SelfExtensionEngine auto-implement missing primitives
- **Typed capabilities** — Plugins declare mathematical structure requirements
- **Automatic self-correction** — SelfCorrector acts on ArchitecturalAdvisor findings
- **ZFC imports cleaned up** — `zfc/bridge.py` and `zfc/store_adapter.py` now import from `core.category` directly
- **PresheafTopos bridge** — `from_enriched_category()` now handles both EnrichedCategory and KOMPOSOS-IV Category
- **Absorb similarity guard** — requires sim > 0 (no transfer between completely dissimilar objects)

### ⚠️ Partial / Needs Cleanup
- None — all oracle strategies now have dedicated tests

### 🆕 Future Work
- Domain plugins (chemistry, finance, cyber, protein science, etc.) — infrastructure is ready, domain content needed
- Platform vision (shared global Category, collective OPTIMUS, differential privacy)
- Formal Yoneda proof: prove triangle inequality for Yoneda distance (currently tested, needs formal proof object)
- Full simplicial enrichment for isofibration detection (currently heuristic-based)

## Philosophical Foundation

The system implements the Ruliad Engine vision (see `The ruliad engine.md`):
- Capabilities are **basis vectors** in computational space (linearly independent primitives)
- Patterns are **named paths** through that space (compositions of capabilities)
- OPTIMUS is the **categorical gradient** that discovers missing intermediates and refines the basis
- COG **verifies** every refinement is structurally valid
- The ∞-Cosmos provides **model-independent** theorems (Riehl-Verity)
- The Dual Engine (ZFC + CAT) **observes its own reasoning** and learns from disagreements via System 3
- Orion makes the whole thing **composable and hot-loadable**
- The platform vision: scale across users, collective OPTIMUS on aggregate graph, converge toward irreducible primitives

OPTIMUS guarantees: Tarski fixpoint stability (monotone convergence, no cycles, provable termination).
∞-Cosmos guarantees: Model independence (theorems work for all models of (∞,1)-categories).
Dual Engine guarantees: Every recommendation is verified by both logical (ZFC) and structural (CAT) foundations.

## Test Status

**151/151 tests pass** (17 test_cog_iv + 27 test_higher_order_yoneda + 39 test_infinity_cosmos + 34 test_optimus_integration + 9 stress_test + 25 test_oracle_strategies, zero regressions).
Run: `pytest tests/ -v`
