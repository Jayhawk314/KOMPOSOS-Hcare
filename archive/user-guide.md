# KOMPOSOS-IV User Guide

## Quick Start

```python
from core import Category

# Create a category (in-memory SQLite by default)
cat = Category("my_project", db_path=":memory:")

# Add objects
cat.add("Alice", type_name="person")
cat.add("Bob", type_name="person")
cat.add("Server", type_name="system")

# Connect with morphisms (confidence = enriched hom-value)
f = cat.connect("Alice", "Server", name="authenticates", confidence=0.95)
g = cat.connect("Server", "Bob", name="notifies", confidence=0.8)

# Compose: the pipeline Alice -> Server -> Bob
h = cat.compose(f, g)
print(h.confidence)  # 0.76 (0.95 * 0.8 via multiplicative quantale)
print(h.id)          # "notifies.authenticates:Alice->Bob"

# Find optimal path
path, weight = cat.optimal_path("Alice", "Bob")
print(path)    # ["Alice", "Server", "Bob"]
print(weight)  # 0.76
```

## Objects and Morphisms

### Object Fields

```python
from core import Object

obj = Object(
    name="sensor_1",            # required, unique identifier
    type_name="IoT",            # categorization (default "Object")
    metadata={"location": "B3"},# arbitrary key-value data
    embedding=np.array([...]),  # optional 768d vector for semantic ops
    provenance="field_deploy",  # where this came from
)
cat.add_object(obj)

# Or use the shorthand:
cat.add("sensor_1", type_name="IoT", metadata={"location": "B3"})
```

### Morphism Fields

```python
from core import Morphism

mor = Morphism(
    name="reads",
    source="sensor_1",
    target="dashboard",
    confidence=0.9,              # enriched hom-value
    metadata={"protocol": "MQTT"},
)
cat.add_morphism(mor)

# Or use the shorthand:
cat.connect("sensor_1", "dashboard", name="reads", confidence=0.9, protocol="MQTT")
```

### Callable Morphisms

Morphisms can carry executable functions:

```python
def encrypt(data):
    return data[::-1]  # toy example

def compress(data):
    return data.strip()

f = cat.connect("raw", "encrypted", name="encrypt", fn=encrypt)
g = cat.connect("encrypted", "compressed", name="compress", fn=compress)

# Compose creates a new callable
h = cat.compose(f, g)
result = h("hello world")  # compress(encrypt("hello world"))
```

### Querying

```python
cat.get("Alice")                   # get object by name
cat.get_morphism("f:Alice->Bob")   # get morphism by ID
cat.morphisms_from("Alice")        # all morphisms out of Alice
cat.morphisms_to("Bob")            # all morphisms into Bob
cat.objects()                      # list all objects
cat.morphisms()                    # list all morphisms
cat.neighbors("Alice")            # {"outgoing": [...], "incoming": [...]}
```

## Enrichment

### Choosing a Quantale

```python
from core import Category, get_quantale

# Default: multiplicative (confidence, probability)
cat = Category("default")  # quantale = multiplicative

# Cost/distance optimization
cat = Category("logistics", quantale=get_quantale("additive"))

# Risk analysis
cat = Category("risk", quantale=get_quantale("probabilistic"))

# Bottleneck analysis
cat = Category("network", quantale=get_quantale("min"))
```

### What Confidence Means Per Quantale

| Quantale | Confidence means | Composition does | Best path has |
|----------|-----------------|------------------|---------------|
| Multiplicative | Probability of success | Multiplies | Highest product |
| Additive | Cost to traverse | Sums | Lowest sum |
| Probabilistic | Risk of failure | P(at least one) | Lowest risk |
| Max | Peak load | Takes maximum | Lowest peak |
| Min | Capacity | Takes minimum | Highest minimum |

### Checking Enrichment Axioms

```python
# Hom(A,B) tensor Hom(B,C) <= Hom(A,C)?
cat.verify_composition_axiom("A", "B", "C")

# Get raw hom-value
cat.hom("Alice", "Bob")  # 0.76

# Compute weight along a path
cat.path_weight(["Alice", "Server", "Bob"])  # 0.76
```

## Path Finding

```python
# All simple paths up to length 10
paths = cat.find_paths("Alice", "Bob", max_length=10)
for p in paths:
    print(p.morphism_ids, p.weight)

# Optimal path (Dijkstra with quantale semantics)
result = cat.optimal_path("Alice", "Bob")
if result:
    path, weight = result
    print(path, weight)

# Top-k paths (Yen's algorithm)
results = cat.top_k_paths("Alice", "Bob", k=3)
for path, weight in results:
    print(path, weight)

# For additive quantale, minimize:
cat_cost = Category("cost", quantale=get_quantale("additive"))
# ... add objects/morphisms ...
cat_cost.optimal_path("start", "end", maximize=False)
```

## Hooks

Seven events fire automatically during category operations:

```python
def on_new_object(object, **kw):
    print(f"New object: {object.name}")

def on_composed(f, g, result, **kw):
    print(f"Composed {f.name} and {g.name} -> {result.name}")

cat.on("object_added", on_new_object)
cat.on("composed", on_composed)

# Available events:
#   object_added, object_removed
#   morphism_added, morphism_removed
#   composed, path_found, bulk_loaded

# Unregister:
cat.off("object_added", on_new_object)
```

## ∞-Cosmos Layer (Higher Categorical Reasoning)

### Homotopy 2-Category

```python
from core.cosmos import InfinityCosmos
from core.two_cell_bridge import TwoCellBridge

cosmos = InfinityCosmos(cat)
h2k = cosmos.homotopy_2_category()  # Auto-detects 2-cells

# Check statistics
stats = cosmos.statistics()
print(f"Objects: {stats['objects']}")
print(f"Morphisms: {stats['morphisms']}")
print(f"Two-cells: {stats['two_cells']}")
print(f"Isofibrations: {stats['isofibrations']}")
print(f"Fibrations: {stats['fibrations']}")
```

### 2-Cell Verification (COG Tier 4)

```python
bridge = TwoCellBridge(cosmos)

# Verify a claim using 2-cell reasoning
result = bridge.tier4_verify("Alice", "Bob", "knows")
print(result["verdict"])           # AGREE, REJECT, ORPHAN, HOLLOW, EQUIVALENT
print(result["two_cell_witness"])  # Name of the 2-cell that witnesses equivalence
print(result["confidence"])        # Confidence from 2-cell analysis

# Check interchange law coherence
coherence = bridge.verify_interchange_coherence()
print(coherence["coherent"])  # True if 2-category satisfies interchange law
```

### Cartesian Fibrations

```python
fibrations = cosmos.cartesian_fibrations()
for name, fib in fibrations.items():
    print(f"{name}: {len(fib.total_objects)} objects, "
          f"{len(fib.cartesian_lifts)} cartesian lifts")
```

### Yoneda Embedding

```python
yoneda = cosmos.yoneda_embedding()
print(f"Faithful: {yoneda.is_fully_faithful}")
print(f"Score: {yoneda.faithfulness_score}")
```

## Bridges

Load domain data into a Category by subclassing Bridge:

```python
from core import Bridge, Object, Morphism

class TeamBridge(Bridge):
    def get_objects(self):
        return [
            Object(name="Alice", type_name="engineer"),
            Object(name="Bob", type_name="designer"),
            Object(name="Carol", type_name="manager"),
        ]

    def get_morphisms(self):
        return [
            Morphism(name="reports_to", source="Alice", target="Carol", confidence=1.0),
            Morphism(name="reports_to", source="Bob", target="Carol", confidence=1.0),
            Morphism(name="collaborates", source="Alice", target="Bob", confidence=0.8),
        ]

    def score_pair(self, source, target):
        return {"compatibility": 0.9}

bridge = TeamBridge("team")
bridge.load()  # returns {"objects": 3, "morphisms": 3}

# Use the category
bridge.category.optimal_path("Alice", "Carol")

# Capture loading as a verified functor
F = bridge.as_functor()
print(F.verify())  # checks all functor laws hold
```

## Functors

Map one category to another while preserving structure:

```python
from core import Category, Functor

# Source category: code modules
code = Category("code", db_path=":memory:")
code.add("auth"); code.add("db"); code.add("api")
code.connect("api", "auth", name="uses", confidence=0.9)
code.connect("auth", "db", name="queries", confidence=0.8)

# Target category: deployed services
deploy = Category("deploy", db_path=":memory:")
deploy.add("auth_svc"); deploy.add("db_svc"); deploy.add("api_gw")
deploy.connect("api_gw", "auth_svc", name="calls", confidence=0.9)
deploy.connect("auth_svc", "db_svc", name="connects", confidence=0.8)

# Create functor (morphism map auto-inferred)
F = code.functor_to(deploy, {
    "auth": "auth_svc",
    "db": "db_svc",
    "api": "api_gw",
})

# Verify it preserves structure
v = F.verify()
print(v)  # {"objects": True, "morphisms": True, "composition": True, "identity": True}

# Apply the functor
print(F(code.get("auth")).name)  # "auth_svc"

# Check properties
F.is_faithful()   # injective on hom-sets?
F.is_full()       # surjective on hom-sets?
F.is_embedding()  # both?

# Compose functors
G = deploy.functor_to(another_cat, {...})
H = G.compose(F)  # H: code -> another_cat
```

## Natural Transformations

Transform one functor into another while respecting structure:

```python
from core import Functor, NaturalTransformation

# Two functors F, G: C -> D
# F maps A->X1, B->Y1
# G maps A->X2, B->Y2

# Natural transformation eta: F => G
# Components: for each object in C, a morphism in D
eta = NaturalTransformation("upgrade", F, G, {
    "A": "eta_a:X1->X2",   # morphism ID in D
    "B": "eta_b:Y1->Y2",   # morphism ID in D
})

# Verify naturality squares commute
eta.verify()  # True if eta_B . F(f) = G(f) . eta_A for all f

# Vertical composition: F => G => H
mu = NaturalTransformation("patch", G, H, {...})
composed = mu.compose(eta)  # F => H

# Horizontal composition: (F => G) * (H => K)
horizontal = mu.horizontal_compose(eta)
```

## Limits and Colimits

### Product

```python
cone = cat.product("A", "B")
print(cone.apex)  # "A*B"  (uses x character)
print(cone.legs)  # {"A": "pi1:A*B->A", "B": "pi2:A*B->B"}
```

### Coproduct

```python
cocone = cat.coproduct("A", "B")
print(cocone.apex)  # "A+B"
print(cocone.legs)  # {"A": "iota1:A->A+B", "B": "iota2:B->A+B"}
```

### Pullback

```python
# Given f: A->C and g: B->C (cospan)
f = cat.connect("A", "C", name="f")
g = cat.connect("B", "C", name="g")
cone = cat.pullback(f.id, g.id)
print(cone.apex)  # "A*_CB"
# pi1: P->A, pi2: P->B such that f.pi1 = g.pi2
```

### Pushout

```python
# Given f: C->A and g: C->B (span)
f = cat.connect("C", "A", name="f")
g = cat.connect("C", "B", name="g")
cocone = cat.pushout(f.id, g.id)
print(cocone.apex)  # "A+_CB"
# iota1: A->P, iota2: B->P such that iota1.f = iota2.g
```

### Equalizer

```python
from core import equalizer

# f, g: A -> B (parallel morphisms)
f = cat.connect("A", "B", name="f")
g = cat.connect("A", "B", name="g")
eq_obj, eq_mor = equalizer(cat, f.id, g.id)
# eq_obj: "Eq(f,g)", eq_mor: "e:Eq(f,g)->A" where f.e = g.e
```

### Terminal and Initial

```python
t = cat.terminal()  # creates terminal object, morphisms from all objects
i = cat.initial()   # creates initial object, morphisms to all objects
```

## Adjunctions

```python
from core import Adjunction, free_forgetful

# Build a free-forgetful adjunction
adj = free_forgetful(
    C=plain_cat, D=rich_cat,
    embed_obj={...}, embed_mor={...},
    project_obj={...}, project_mor={...},
)

# Verify triangle identities
v = adj.verify()
print(v["left_triangle"])   # True
print(v["right_triangle"])  # True

# Check if it's an equivalence
adj.is_equivalence()
```

## Dual Engine Verification (ZFC + CAT)

```python
from zfc.store_adapter import StoreAdapter
from zfc.bridge import DualEngineBridge

# Build the dual engine from any Category
adapter = StoreAdapter(cat)
bridge = DualEngineBridge(adapter, category=cat)

# Verify a claim through both ZFC and CAT
result = bridge.query("Alice", "Bob", "knows", domain="social")

print(result.delta_type)        # AGREE, ORPHAN, HOLLOW, or REJECT
print(result.zfc_says)          # Did ZFC prove it?
print(result.zfc_confidence)    # ZFC confidence
print(result.cat_says)          # Did CAT confirm it?
print(result.cat_confidence)    # CAT confidence
print(result.meta_prediction)   # System 3 prediction

# Ask System 3 before running both engines
should_run, reason = bridge.should_run_both("Alice", "Bob", "knows")
print(should_run)  # True if both engines are needed
print(reason)      # Why

# Record ground truth to improve System 3
from zfc.meta_kan import Resolution
bridge.resolve(result.episode_id, Resolution.CONFIRMED)
```

## Oracle: Multi-Strategy Inference

```python
from oracle import CategoricalOracle

oracle = CategoricalOracle(cat)
predictions = oracle.predict()  # Runs all 17 strategies

# Predictions are ranked by confidence
for pred in predictions[:10]:
    print(f"{pred.source} --[{pred.predicted_relation}]--> {pred.target}")
    print(f"  Confidence: {pred.confidence:.2f}")
    print(f"  Strategy: {pred.strategy_name}")
    print(f"  Reasoning: {pred.reasoning}")
```

### Individual Strategy Use

```python
from oracle.fibration import FibrationLiftStrategy
from oracle.topos_strategy import ToposLogicStrategy
from oracle.natural_transformation import NaturalTransformationStrategy
from oracle.operadic_decomposition import OperadicDecompositionStrategy
from oracle.evidence_combination import EvidenceCombinationStrategy
from oracle.streaming_forecast import StreamingForecastStrategy
from oracle.topological_anomaly import TopologicalAnomalyStrategy
from oracle.activity_analysis import ActivityAnalysisStrategy
from oracle.boundary_detection import BoundaryDetectionStrategy
from oracle.cellular_dynamics import CellularDynamicsStrategy

# Each strategy implements predict(source, target) -> List[Prediction]
fib = FibrationLiftStrategy(cat)
topos = ToposLogicStrategy(cat)
nt = NaturalTransformationStrategy(cat)

# Combine evidence from multiple strategies
ec = EvidenceCombinationStrategy(cat)
combined = ec.combine_predictions([pred1, pred2, pred3])
```

## Self-Observation (Ruliad Engine)

### Capability Graph Builder

```python
from core.capability_graph import CapabilityGraphBuilder

# Build a Category representing the system's own architecture
builder = CapabilityGraphBuilder(orion_core, telemetry_category=telem_cat)
cap_graph = await builder.build()
builder.add_git_signals(git_co_modification_matrix)

print(builder.summary())
```

### Linear Independence Test

```python
from core.independence import LinearIndependenceTest

test = LinearIndependenceTest(cap_graph)
result = test.is_independent("search", "store")

print(result["recommendation"])
# "NEW PRIMITIVE: No existing composition reaches this. Add it."
# or
# "PATTERN: Already reachable via search->index->store (confidence 0.72)"
```

### Architectural Advisor

```python
from core.architect import ArchitecturalAdvisor

advisor = ArchitecturalAdvisor(orion_core, telemetry_cat, repo_path=".")
report = await advisor.analyze()

# The report includes:
for rec in report["recommendations"]:
    print(f"[{rec['type']}] {rec['description']} (conf={rec['confidence']:.2f})")

# Types: missing_primitive, redundant_capability, wrong_boundary,
#        two_cell_equivalence, fibration_pattern,
#        dual_engine_agree, dual_engine_orphan, dual_engine_hollow
```

## Math Modules Quick Reference

### categorical/ — Pure Category Theory

```python
from categorical.kan_extensions import left_kan, right_kan
from categorical.grothendieck import grothendieck_construction
from categorical.presheaf_topos import PresheafTopos
from categorical.topos_logic import perspectival_truth
from categorical.streaming_kan import StreamingKan
from categorical.operads import Operad
from categorical.dempster_shafer import combine_evidence
from categorical.cellular_automata import CellularAutomaton
```

### cubical/ — Cubical Type Theory

```python
from cubical.paths import Path, Interval
from cubical.kan_ops import hcomp, hfill, transport
# All interpolation filled -- no longer placeholder
```

### game/ — Compositional Game Theory

```python
from game.open_games import OpenGame, compose_games
from game.nash import find_nash_equilibria
```

### topology/ — Topological Data Analysis

```python
from topology.persistent_homology import compute_betti, persistence_pairs
from topology.temporal_sheaves import TemporalSheaf, check_coherence
from topology.persistent_sheaves import sheaf_cohomology
```

### hott/ — Homotopy Type Theory

```python
from hott.identity import IdentityType, refl
from hott.path_induction import j_eliminator, transport  # transport now computational
from hott.homotopy import paths_homotopic
from hott.geometric_homotopy import geometric_homotopy_check
```

### geometry/ — Discrete Differential Geometry

```python
from geometry.ricci import ollivier_ricci_curvature
from geometry.flow import ricci_flow
from geometry.spectral import laplacian_spectrum, spectral_clustering
from geometry.fast_ricci import fast_curvature_estimate
```

### zfc/ — Set-Theoretic Reasoning

```python
from zfc.universe import ZFSet
from zfc.logic import Formula, satisfies
from zfc.proof_engine import DualVerifiedProof
from zfc.bridge import DualEngineBridge  # ZFC + CAT verification
```

### oracle/ — Categorical Oracle

```python
from oracle import CategoricalOracle
oracle = CategoricalOracle(category)
predictions = oracle.predict()  # runs all 17 strategies, merges, verifies
```

### data/ — Embeddings

```python
from data.embeddings import CategoryEmbedder
embedder = CategoryEmbedder(category)
embedder.embed_all()
similar = embedder.nearest("concept_name", k=5)
```

## Extended: Possibilities

### Supply Chain Modeling

```python
cat = Category("supply_chain", quantale=get_quantale("additive"))

# Objects = facilities, morphisms = shipping routes with cost
cat.add("Factory_CN", type_name="factory")
cat.add("Port_SH", type_name="port")
cat.add("Warehouse_LA", type_name="warehouse")
cat.add("Store_NYC", type_name="retail")

cat.connect("Factory_CN", "Port_SH", name="truck", confidence=50.0)   # $50
cat.connect("Port_SH", "Warehouse_LA", name="ship", confidence=200.0) # $200
cat.connect("Warehouse_LA", "Store_NYC", name="rail", confidence=80.0) # $80

# Cheapest route
path, cost = cat.optimal_path("Factory_CN", "Store_NYC", maximize=False)
# path = ["Factory_CN", "Port_SH", "Warehouse_LA", "Store_NYC"], cost = 330.0

# Product: combined facility handling both east and west coast
cone = cat.product("Warehouse_LA", "Warehouse_NJ")
```

### Social Network Analysis

```python
cat = Category("social")

# People as objects, relationships as enriched morphisms
cat.add("Alice"); cat.add("Bob"); cat.add("Carol")
cat.connect("Alice", "Bob", name="friends", confidence=0.9)
cat.connect("Bob", "Carol", name="colleagues", confidence=0.6)

# Geometric analysis: find communities
from geometry.ricci import ollivier_ricci_curvature
curvatures = ollivier_ricci_curvature(cat)
# Positive curvature = tight community
# Negative curvature = bridge between communities

# Spectral clustering
from geometry.spectral import spectral_clustering
clusters = spectral_clustering(cat, k=3)
```

### Code Dependency Analysis

```python
# Model imports as morphisms
code = Category("codebase")
code.add("main.py"); code.add("utils.py"); code.add("db.py")
code.connect("main.py", "utils.py", name="imports")
code.connect("main.py", "db.py", name="imports")
code.connect("utils.py", "db.py", name="imports")

# Find circular dependencies via path finding
paths = code.find_paths("db.py", "main.py")  # any cycles?

# Pullback: what do two modules share?
f = code.connect("main.py", "db.py", name="uses_db")
g = code.connect("api.py", "db.py", name="uses_db")
shared = code.pullback(f.id, g.id)  # common dependency structure
```

### Biological Pathway Modeling

```python
cat = Category("metabolism", quantale=get_quantale("multiplicative"))

# Enzymes as morphisms with reaction efficiency
cat.add("Glucose"); cat.add("Pyruvate"); cat.add("ATP")
cat.connect("Glucose", "Pyruvate", name="glycolysis", confidence=0.95)
cat.connect("Pyruvate", "ATP", name="krebs", confidence=0.85)

# Pathway efficiency
path, efficiency = cat.optimal_path("Glucose", "ATP")
# efficiency = 0.95 * 0.85 = 0.8075

# Oracle: predict missing pathways
from oracle import CategoricalOracle
oracle = CategoricalOracle(cat)
predictions = oracle.predict()  # suggests missing enzyme links
```

### Security Architecture Verification

```python
sec = Category("security")

# Zones and trust boundaries
sec.add("Internet", type_name="zone")
sec.add("DMZ", type_name="zone")
sec.add("Internal", type_name="zone")
sec.add("Database", type_name="zone")

sec.connect("Internet", "DMZ", name="firewall_1", confidence=0.7)
sec.connect("DMZ", "Internal", name="firewall_2", confidence=0.9)
sec.connect("Internal", "Database", name="acl", confidence=0.95)

# Verify: can anything reach Database from Internet?
path, trust = sec.optimal_path("Internet", "Database")
print(f"Attack path trust: {trust}")  # 0.7 * 0.9 * 0.95 = 0.5985

# Temporal sheaves: detect impossible access patterns
from topology.temporal_sheaves import TemporalSheaf
sheaf = TemporalSheaf(sec)
# Flags: user accessed Database from two zones simultaneously

# Dual Engine: verify security claim through both ZFC and CAT
from zfc.store_adapter import StoreAdapter
from zfc.bridge import DualEngineBridge
adapter = StoreAdapter(sec)
bridge = DualEngineBridge(adapter, category=sec)
result = bridge.query("Internet", "Database", "can_reach", domain="security")
print(result.delta_type)  # AGREE means both ZFC and CAT confirm the attack path
```

### Multi-Domain Reasoning

```python
# Map between two different knowledge domains
physics = Category("physics", db_path=":memory:")
physics.add("force"); physics.add("mass"); physics.add("acceleration")
physics.connect("force", "mass", name="F=ma")

biology = Category("biology", db_path=":memory:")
biology.add("selection_pressure"); biology.add("population"); biology.add("adaptation")
biology.connect("selection_pressure", "population", name="drives")

# Functor: structural analogy between domains
F = physics.functor_to(biology, {
    "force": "selection_pressure",
    "mass": "population",
    "acceleration": "adaptation",
})

# If functor verifies, the analogy is structurally sound
print(F.verify())
```

### Event-Driven Reactive Systems

```python
cat = Category("events")

# Hooks make the category reactive
def send_alert(morphism, **kw):
    if morphism.confidence < 0.5:
        print(f"LOW CONFIDENCE: {morphism.id}")

def log_composition(f, g, result, **kw):
    print(f"Pipeline: {f.name} | {g.name} -> {result.confidence}")

cat.on("morphism_added", send_alert)
cat.on("composed", log_composition)

# Now every structural change triggers real-time reactions
cat.connect("sensor", "alert", name="threshold", confidence=0.3)
# Prints: LOW CONFIDENCE: threshold:sensor->alert
```

### Self-Observing System

```python
# The system observes its own architecture
from core.architect import ArchitecturalAdvisor

advisor = ArchitecturalAdvisor(orion_core, telemetry_cat)
report = await advisor.analyze()

# Finds:
# - Missing primitives (capabilities that can't be composed from existing ones)
# - Redundant capabilities (Yoneda-equivalent capabilities that should merge)
# - Wrong boundaries (modules that always change together)
# - Fibration patterns (recurring structural patterns)
# - Dual Engine verdicts (ZFC/CAT agreement on recommendations)
# - System 3 insights (learned patterns from past disagreements)

for rec in report["recommendations"]:
    print(f"[{rec['type']}] {rec['description']}")
```
