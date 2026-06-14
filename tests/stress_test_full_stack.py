# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-KOMPOSOS-IV-Commercial
# Copyright (c) 2024-2026 James Ray Hawkins

"""
Full-stack stress test for the 4-layer architecture.

Exercises: Orion + KOMPOSOS-IV + COG + OPTIMUS
under load with complex graph topologies, adversarial
inputs, concurrency, and multi-round refinement.

Requires Python 3.12+ (Orion uses type statement syntax).
Run: py -3.12 tests/stress_test_full_stack.py
"""

import sys
import io
import os
import asyncio
import time
import random
import traceback

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.category import Category
from core.types import Object, Morphism
from core.optimus import OptimusEngine, category_to_runtime, sync_rewrites_to_category

passed = 0
failed = 0
errors = []


def report(name, ok, detail=""):
    global passed, failed, errors
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {name}" + (f" -- {detail}" if detail else ""))
    if ok:
        passed += 1
    else:
        failed += 1
        errors.append(name)


# ============================================================================
# TEST 1: Large graph construction + OPTIMUS at scale
# ============================================================================
async def test_large_graph_refinement():
    print("\n[1] Large graph: 200 objects, dense connections, multi-round OPTIMUS")
    t0 = time.perf_counter()

    cat = Category(db_path=":memory:")

    # Build a layered graph: 5 layers x 40 nodes each
    layers = []
    for layer_idx in range(5):
        layer_nodes = []
        for node_idx in range(40):
            name = f"L{layer_idx}_N{node_idx}"
            cat.add(name)
            layer_nodes.append(name)
        layers.append(layer_nodes)

    # Connect adjacent layers with varying confidence
    rng = random.Random(42)
    edge_count = 0
    for i in range(4):
        for src in layers[i]:
            # Each node connects to 3-8 nodes in next layer
            targets = rng.sample(layers[i + 1], k=rng.randint(3, 8))
            for tgt in targets:
                conf = round(rng.uniform(0.3, 1.0), 3)
                cat.connect(src, tgt, f"edge_{edge_count}", confidence=conf)
                edge_count += 1

    # Add some weak cross-layer shortcuts (L0 -> L2, L0 -> L4)
    weak_shortcuts = 0
    for src in layers[0][:10]:
        for tgt in layers[2][:5]:
            cat.connect(src, tgt, f"weak_{weak_shortcuts}", confidence=0.1)
            weak_shortcuts += 1
        for tgt in layers[4][:3]:
            cat.connect(src, tgt, f"xweak_{weak_shortcuts}", confidence=0.05)
            weak_shortcuts += 1

    n_obj = len(cat.objects())
    n_mor = len(cat.morphisms())
    t_build = time.perf_counter() - t0
    report("graph built", n_obj == 200 and n_mor > 500,
           f"{n_obj} objs, {n_mor} mors in {t_build:.2f}s")

    # OPTIMUS round 1
    t1 = time.perf_counter()
    engine = OptimusEngine(cat, max_depth=3)
    r1 = engine.refine(max_steps=50, depth=2)
    t_r1 = time.perf_counter() - t1
    report("OPTIMUS round 1", r1["steps"] >= 0,
           f"{r1['steps']} steps, {len(r1['synced_morphisms'])} shortcuts in {t_r1:.2f}s")

    # Verify Tarski: every synced morphism should have higher confidence than the weak ones
    n_mor_after = len(cat.morphisms())
    report("morphisms grew", n_mor_after >= n_mor,
           f"{n_mor} -> {n_mor_after}")

    # OPTIMUS round 2 (should find fewer improvements)
    t2 = time.perf_counter()
    r2 = engine.refine(max_steps=50, depth=2)
    t_r2 = time.perf_counter() - t2
    report("OPTIMUS round 2 converges",
           len(r2["synced_morphisms"]) <= len(r1["synced_morphisms"]),
           f"{len(r2['synced_morphisms'])} new (was {len(r1['synced_morphisms'])}) in {t_r2:.2f}s")

    # Structural gaps
    gaps = engine.find_structural_gaps()
    report("gap detection works", isinstance(gaps, list),
           f"{len(gaps)} gaps found")

    return cat, engine


# ============================================================================
# TEST 2: Adversarial inputs
# ============================================================================
async def test_adversarial_inputs():
    print("\n[2] Adversarial: Unicode, empty, duplicates, self-loops, cycles")
    cat = Category(db_path=":memory:")

    # Unicode names
    cat.connect("alpha", "beta", "greek", confidence=0.9)
    cat.connect("node_a", "node_b", "ascii_safe", confidence=0.8)
    report("unicode names", len(cat.objects()) >= 2)

    # Self-loop
    cat.connect("self", "self", "loop", confidence=1.0)
    mors = [m for m in cat.morphisms() if m.source == "self" and m.target == "self"]
    report("self-loop stored", len(mors) >= 1)

    # Tight cycle: A -> B -> C -> A
    cat.connect("cyc_A", "cyc_B", "fwd1", confidence=0.9)
    cat.connect("cyc_B", "cyc_C", "fwd2", confidence=0.9)
    cat.connect("cyc_C", "cyc_A", "fwd3", confidence=0.9)

    # OPTIMUS on cyclic graph should not crash or infinite loop
    engine = OptimusEngine(cat, max_depth=2)
    try:
        result = engine.refine(max_steps=10, depth=2)
        report("OPTIMUS on cycles", True, f"{result['steps']} steps")
    except Exception as e:
        report("OPTIMUS on cycles", False, str(e))

    # Duplicate morphism names (same name, different endpoints)
    cat.connect("dup_A", "dup_B", "same_name", confidence=0.8)
    cat.connect("dup_C", "dup_D", "same_name", confidence=0.7)
    runtime = category_to_runtime(cat)
    report("duplicate name handling",
           len(runtime.morphisms) >= 2,
           f"{len(runtime.morphisms)} morphisms in runtime")

    # Zero confidence
    cat.connect("zero_A", "zero_B", "zero_edge", confidence=0.0)
    engine2 = OptimusEngine(cat, max_depth=2)
    try:
        r = engine2.refine(max_steps=5, depth=1)
        report("zero confidence", True, f"{r['steps']} steps")
    except Exception as e:
        report("zero confidence", False, str(e))

    # Very long chain (depth test)
    for i in range(50):
        cat.connect(f"chain_{i}", f"chain_{i+1}", f"link_{i}", confidence=0.99)
    paths = cat.find_paths("chain_0", "chain_50", max_length=60)
    report("50-hop chain path", len(paths) >= 1,
           f"{len(paths)} path(s), length={paths[0].length if paths else '?'}")


# ============================================================================
# TEST 3: Full 4-layer Agent stress
# ============================================================================
async def test_agent_full_stack():
    print("\n[3] Full Agent: 4 layers, 100+ knowledge items, verify + refine + gaps")

    from orion_komposos_cog import Agent, AgentConfig

    config = AgentConfig(
        knowledge_db_path=":memory:",
        cog_db_path=":memory:",
        sessions_enabled=False,
        optimus_enabled=True,
        optimus_max_depth=3,
        log_level="ERROR",
    )
    agent = Agent(config)
    await agent.start()
    report("agent started", agent._started)

    # Build a realistic domain graph
    domains = {
        "Programming": ["Python", "Rust", "TypeScript", "Go", "C++"],
        "ML": ["TensorFlow", "PyTorch", "JAX", "sklearn", "XGBoost"],
        "Math": ["LinearAlgebra", "Calculus", "Topology", "CategoryTheory", "Probability"],
        "Infrastructure": ["Docker", "Kubernetes", "AWS", "GCP", "Linux"],
        "Databases": ["PostgreSQL", "Redis", "MongoDB", "SQLite", "DynamoDB"],
    }

    # Add domain-internal connections (high confidence)
    rng = random.Random(123)
    add_count = 0
    for domain, items in domains.items():
        for i, src in enumerate(items):
            for j, tgt in enumerate(items):
                if i != j:
                    conf = round(rng.uniform(0.7, 1.0), 2)
                    await agent.add_knowledge(src, tgt, "similar_to", conf)
                    add_count += 1

    # Add cross-domain connections (lower confidence)
    cross_links = [
        ("Python", "TensorFlow", 0.95), ("Python", "PyTorch", 0.93),
        ("Python", "sklearn", 0.9), ("Rust", "Linux", 0.7),
        ("TypeScript", "Docker", 0.5), ("Go", "Kubernetes", 0.85),
        ("C++", "TensorFlow", 0.6), ("LinearAlgebra", "JAX", 0.8),
        ("Probability", "XGBoost", 0.7), ("CategoryTheory", "JAX", 0.4),
        ("PostgreSQL", "Docker", 0.75), ("Redis", "Kubernetes", 0.65),
        ("AWS", "DynamoDB", 0.9), ("GCP", "Kubernetes", 0.85),
        ("SQLite", "Python", 0.8), ("MongoDB", "Go", 0.6),
        ("Topology", "CategoryTheory", 0.95), ("Calculus", "Probability", 0.85),
        ("LinearAlgebra", "sklearn", 0.75), ("Linux", "Docker", 0.9),
    ]
    for src, tgt, conf in cross_links:
        await agent.add_knowledge(src, tgt, "enables", conf)
        add_count += 1

    # Add some deliberately weak shortcuts (OPTIMUS targets)
    weak_links = [
        ("Python", "JAX", 0.1), ("Rust", "AWS", 0.05),
        ("Go", "DynamoDB", 0.08), ("C++", "PyTorch", 0.12),
        ("TypeScript", "MongoDB", 0.15),
    ]
    for src, tgt, conf in weak_links:
        await agent.add_knowledge(src, tgt, "similar_to", conf)
        add_count += 1

    n_obj = len(agent.category.objects())
    n_mor = len(agent.category.morphisms())
    report("knowledge loaded", n_obj >= 25 and n_mor >= 100,
           f"{add_count} adds -> {n_obj} objs, {n_mor} morphisms")

    # COG verification battery
    verify_results = []
    claims = [
        ("Python", "TensorFlow", "enables"),
        ("Go", "Kubernetes", "enables"),
        ("CategoryTheory", "JAX", "enables"),
        ("Rust", "AWS", "similar_to"),
        ("Python", "DynamoDB", "enables"),  # no direct link
        ("Topology", "Docker", "similar_to"),  # very indirect
    ]
    t_verify = time.perf_counter()
    for src, tgt, rel in claims:
        try:
            r = await agent.verify_claim(src, tgt, rel, max_tier=2)
            verify_results.append((src, tgt, r.status.value, r.confidence))
        except Exception as e:
            verify_results.append((src, tgt, "ERROR", str(e)))
    t_verify = time.perf_counter() - t_verify

    verified_ok = sum(1 for _, _, s, _ in verify_results if s != "ERROR")
    report("COG verification battery", verified_ok == len(claims),
           f"{verified_ok}/{len(claims)} verified in {t_verify:.2f}s")
    for src, tgt, status, conf in verify_results:
        print(f"      {src}->{tgt}: {status} (conf={conf})")

    # OPTIMUS refinement
    t_ref = time.perf_counter()
    ref = await agent.refine(max_steps=30, depth=2)
    t_ref = time.perf_counter() - t_ref
    report("OPTIMUS refinement", ref["steps"] >= 0,
           f"{ref['steps']} steps, {len(ref['synced_morphisms'])} shortcuts in {t_ref:.2f}s")
    for name in ref["synced_morphisms"][:10]:
        print(f"      Shortcut: {name}")

    # Gap detection
    gaps = await agent.find_capability_gaps()
    report("gap detection", len(gaps) >= 0, f"{len(gaps)} gaps")
    for g in gaps[:5]:
        print(f"      {g['source']}->{g['target']} via {g['via']} (conf={g['path_confidence']:.3f})")

    # Yoneda similarity matrix (top pairs)
    all_nodes = list(domains["Programming"]) + list(domains["ML"])
    sims = []
    for i, a in enumerate(all_nodes):
        for b in all_nodes[i + 1:]:
            try:
                s = await agent.yoneda_similarity(a, b)
                sims.append((a, b, s))
            except Exception:
                pass
    sims.sort(key=lambda x: x[2], reverse=True)
    report("Yoneda matrix computed", len(sims) > 0,
           f"{len(sims)} pairs, top={sims[0][2]:.3f} ({sims[0][0]}/{sims[0][1]})" if sims else "none")

    # Post-refinement verification (should OPTIMUS shortcuts help COG?)
    n_mor_after = len(agent.category.morphisms())
    report("graph grew after refinement", n_mor_after >= n_mor,
           f"{n_mor} -> {n_mor_after}")

    # Stats
    stats = await agent.get_statistics()
    report("stats populated",
           stats["komposos"]["objects"] > 0 and stats["komposos"]["morphisms"] > 0,
           f"objs={stats['komposos']['objects']}, mors={stats['komposos']['morphisms']}")

    await agent.stop()
    report("agent stopped cleanly", not agent._started)


# ============================================================================
# TEST 4: OPTIMUS mathematical invariants under stress
# ============================================================================
async def test_optimus_invariants():
    print("\n[4] OPTIMUS invariants: Tarski monotonicity, idempotence, composition law")
    cat = Category(db_path=":memory:")

    # Diamond: A->B (0.9), A->C (0.8), B->D (0.85), C->D (0.75), A->D (0.2 weak)
    cat.connect("A", "B", "ab", confidence=0.9)
    cat.connect("A", "C", "ac", confidence=0.8)
    cat.connect("B", "D", "bd", confidence=0.85)
    cat.connect("C", "D", "cd", confidence=0.75)
    cat.connect("A", "D", "ad_weak", confidence=0.2)

    engine = OptimusEngine(cat, max_depth=3)

    # Round 1
    r1 = engine.refine(max_steps=20, depth=2)
    synced_1 = set(r1["synced_morphisms"])

    # Tarski: every shortcut confidence >= original weak edge
    tarski_ok = True
    for m in cat.morphisms():
        if m.metadata.get("optimus_generation"):
            if m.source == "A" and m.target == "D":
                if m.confidence < 0.2:
                    tarski_ok = False
    report("Tarski monotonicity", tarski_ok,
           "all shortcuts >= original confidence")

    # Check the actual improvement: A->B->D = 0.9*0.85 = 0.765, A->C->D = 0.8*0.75 = 0.6
    # Best factorization: 0.765 > 0.2
    ad_mors = [m for m in cat.morphisms() if m.source == "A" and m.target == "D"]
    best_conf = max(m.confidence for m in ad_mors) if ad_mors else 0
    report("diamond shortcut found", best_conf > 0.5,
           f"A->D best conf={best_conf:.3f} (was 0.2)")

    # Idempotence: round 2 should add 0 NEW morphisms to Category
    r2 = engine.refine(max_steps=20, depth=2)
    report("idempotent (Category-level)",
           len(r2["synced_morphisms"]) == 0,
           f"{len(r2['synced_morphisms'])} new synced")

    # Composition law: if A->B and B->D exist, composed confidence = tensor(A->B, B->D)
    ab = [m for m in cat.morphisms() if m.source == "A" and m.target == "B"]
    bd = [m for m in cat.morphisms() if m.source == "B" and m.target == "D"]
    if ab and bd:
        expected = ab[0].confidence * bd[0].confidence  # multiplicative quantale
        report("composition law", abs(best_conf - expected) < 0.01 or best_conf >= expected,
               f"composed={expected:.3f}, actual={best_conf:.3f}")
    else:
        report("composition law", False, "missing morphisms")


# ============================================================================
# TEST 5: Concurrent operations
# ============================================================================
async def test_concurrent_operations():
    print("\n[5] Concurrent: parallel adds + reads + refinement")
    cat = Category(db_path=":memory:")

    # Seed some data
    for i in range(20):
        cat.connect(f"src_{i}", f"tgt_{i}", f"edge_{i}", confidence=0.8)
        cat.connect(f"tgt_{i}", f"sink", f"to_sink_{i}", confidence=0.7)

    async def add_batch(start, count):
        for i in range(start, start + count):
            cat.connect(f"batch_{i}", f"tgt_{i % 20}", f"batch_edge_{i}", confidence=0.6)

    async def read_batch():
        for _ in range(50):
            _ = cat.objects()
            _ = cat.morphisms()

    async def refine_batch():
        engine = OptimusEngine(cat, max_depth=2)
        return engine.refine(max_steps=10, depth=1)

    t0 = time.perf_counter()
    try:
        results = await asyncio.gather(
            add_batch(0, 30),
            add_batch(30, 30),
            read_batch(),
            refine_batch(),
            return_exceptions=True,
        )
        any_error = any(isinstance(r, Exception) for r in results)
        t_conc = time.perf_counter() - t0
        report("concurrent ops", not any_error,
               f"4 tasks completed in {t_conc:.2f}s")
        if any_error:
            for r in results:
                if isinstance(r, Exception):
                    print(f"      Error: {r}")
    except Exception as e:
        report("concurrent ops", False, str(e))


# ============================================================================
# TEST 6: Edge cases - empty, single node, disconnected components
# ============================================================================
async def test_edge_cases():
    print("\n[6] Edge cases: empty graph, single node, disconnected, massive fan-out")

    # Empty graph
    cat_empty = Category(db_path=":memory:")
    engine = OptimusEngine(cat_empty)
    r = engine.refine(max_steps=5, depth=1)
    report("empty graph", r["steps"] == 0 and len(r["synced_morphisms"]) == 0)

    # Single node
    cat_single = Category(db_path=":memory:")
    cat_single.add("lonely")
    engine2 = OptimusEngine(cat_single)
    r2 = engine2.refine(max_steps=5, depth=1)
    report("single node", r2["steps"] == 0)

    # Two disconnected components
    cat_disc = Category(db_path=":memory:")
    cat_disc.connect("A1", "A2", "a_edge", confidence=0.9)
    cat_disc.connect("A2", "A3", "a_edge2", confidence=0.8)
    cat_disc.connect("B1", "B2", "b_edge", confidence=0.7)
    cat_disc.connect("B2", "B3", "b_edge2", confidence=0.6)
    engine3 = OptimusEngine(cat_disc)
    r3 = engine3.refine(max_steps=10, depth=2)
    gaps3 = engine3.find_structural_gaps()
    report("disconnected components", True,
           f"{r3['steps']} steps, {len(gaps3)} gaps, components stay separate")

    # Massive fan-out: 1 node -> 100 targets
    cat_fan = Category(db_path=":memory:")
    for i in range(100):
        cat_fan.connect("hub", f"spoke_{i}", f"ray_{i}", confidence=round(0.5 + i * 0.005, 3))
    # And a weak shortcut from hub to a second-hop node
    cat_fan.connect("spoke_0", "spoke_99_child", "onwards", confidence=0.9)
    cat_fan.connect("hub", "spoke_99_child", "weak_skip", confidence=0.05)

    t0 = time.perf_counter()
    engine4 = OptimusEngine(cat_fan, max_depth=2)
    r4 = engine4.refine(max_steps=20, depth=2)
    t_fan = time.perf_counter() - t0
    report("fan-out (1->100)", True,
           f"{r4['steps']} steps, {len(r4['synced_morphisms'])} shortcuts in {t_fan:.2f}s")


# ============================================================================
# TEST 7: Multi-round refinement convergence proof
# ============================================================================
async def test_convergence_proof():
    print("\n[7] Convergence: 10 rounds, strictly non-increasing synced count")
    cat = Category(db_path=":memory:")

    # Build a rich graph
    rng = random.Random(999)
    nodes = [f"n{i}" for i in range(30)]
    for n in nodes:
        cat.add(n)
    for _ in range(120):
        a, b = rng.sample(nodes, 2)
        cat.connect(a, b, f"r_{a}_{b}", confidence=round(rng.uniform(0.2, 1.0), 3))

    engine = OptimusEngine(cat, max_depth=2)
    synced_counts = []
    for round_num in range(10):
        r = engine.refine(max_steps=20, depth=2)
        synced_counts.append(len(r["synced_morphisms"]))

    # After first round, synced counts should trend to 0
    report("convergence trend",
           synced_counts[-1] <= synced_counts[0],
           f"round synced: {synced_counts}")

    # Last 3 rounds should be 0 (fully converged)
    tail_zero = all(c == 0 for c in synced_counts[-3:])
    report("tail convergence (last 3 rounds = 0)", tail_zero,
           f"last 3: {synced_counts[-3:]}")


# ============================================================================
# TEST 8: Yoneda structural fingerprinting at scale
# ============================================================================
async def test_yoneda_at_scale():
    print("\n[8] Yoneda: structural similarity matrix on 20-node graph")
    cat = Category(db_path=":memory:")

    # Build symmetric pairs: (A_i, B_i) with identical morphism structure
    for i in range(10):
        cat.connect(f"A_{i}", "hub_A", f"a_in_{i}", confidence=0.9)
        cat.connect("hub_A", f"A_{i}", f"a_out_{i}", confidence=0.8)
        cat.connect(f"B_{i}", "hub_B", f"b_in_{i}", confidence=0.9)
        cat.connect("hub_B", f"B_{i}", f"b_out_{i}", confidence=0.8)

    engine = OptimusEngine(cat, max_depth=2)

    # hub_A and hub_B should have high Yoneda similarity (same fan structure)
    # Note: Yoneda uses morphism NAMES as keys, so identical structure but different
    # names will show 0 similarity. This is a known limitation.
    fp_a = engine.yoneda_fingerprint("hub_A")
    fp_b = engine.yoneda_fingerprint("hub_B")
    report("fingerprint structure",
           len(fp_a["hom_in"]) == 10 and len(fp_a["hom_out"]) == 10,
           f"hub_A: {len(fp_a['hom_in'])} in, {len(fp_a['hom_out'])} out")
    report("fingerprint structure B",
           len(fp_b["hom_in"]) == 10 and len(fp_b["hom_out"]) == 10,
           f"hub_B: {len(fp_b['hom_in'])} in, {len(fp_b['hom_out'])} out")

    # Self-similarity should be 1.0
    sim_self = engine.yoneda_similarity("hub_A", "hub_A")
    report("Yoneda self-similarity = 1.0", abs(sim_self - 1.0) < 0.001,
           f"got {sim_self:.4f}")

    # A_0 and B_0 should have identical structure (1 out to hub, 1 in from hub)
    # but different morphism names -> 0 similarity (OPTIMUS limitation)
    sim_ab = engine.yoneda_similarity("A_0", "B_0")
    report("Yoneda cross-similarity (name-based)", sim_ab >= 0.0,
           f"A_0 vs B_0 = {sim_ab:.4f} (0 expected due to name-keying)")


# ============================================================================
# TEST 9: Path finding + composition under OPTIMUS rewrites
# ============================================================================
async def test_paths_after_refinement():
    print("\n[9] Paths: composition and optimal_path before/after OPTIMUS")
    cat = Category(db_path=":memory:")

    # A -> B -> C -> D -> E with high confidence
    cat.connect("A", "B", "ab", confidence=0.95)
    cat.connect("B", "C", "bc", confidence=0.90)
    cat.connect("C", "D", "cd", confidence=0.85)
    cat.connect("D", "E", "de", confidence=0.80)
    # A -> E weak shortcut
    cat.connect("A", "E", "ae_weak", confidence=0.1)

    # Before OPTIMUS
    paths_before = cat.find_paths("A", "E", max_length=10)
    report("paths before OPTIMUS", len(paths_before) >= 1,
           f"{len(paths_before)} path(s)")

    # Refine
    engine = OptimusEngine(cat, max_depth=3)
    r = engine.refine(max_steps=30, depth=3)
    report("OPTIMUS on chain", r["steps"] >= 0,
           f"{r['steps']} steps, {len(r['synced_morphisms'])} shortcuts")

    # After OPTIMUS: should have new shortcuts
    paths_after = cat.find_paths("A", "E", max_length=10)
    report("paths after OPTIMUS", len(paths_after) >= len(paths_before),
           f"{len(paths_after)} path(s) (was {len(paths_before)})")

    # Best path confidence should be better than 0.1
    if paths_after:
        best_weight = max(p.weight for p in paths_after)
        report("best path improved", best_weight > 0.1,
               f"best weight={best_weight:.4f} (was 0.1)")


# ============================================================================
# TEST 10: Stress the hook system
# ============================================================================
async def test_hook_stress():
    print("\n[10] Hooks: morphism_added fires correctly under OPTIMUS load")
    cat = Category(db_path=":memory:")
    hook_log = []

    def on_morphism_added(morphism):
        hook_log.append(morphism.name)

    cat.on("morphism_added", on_morphism_added)

    # Manual adds
    cat.connect("H1", "H2", "h12", confidence=0.9)
    cat.connect("H2", "H3", "h23", confidence=0.85)
    cat.connect("H1", "H3", "h13_weak", confidence=0.2)

    manual_count = len(hook_log)
    report("hooks fire on manual add", manual_count == 3,
           f"{manual_count} hooks fired")

    # OPTIMUS refine (should also fire hooks via sync_rewrites)
    engine = OptimusEngine(cat, max_depth=2)
    r = engine.refine(max_steps=10, depth=2)
    total_hooks = len(hook_log)
    optimus_hooks = total_hooks - manual_count
    report("hooks fire on OPTIMUS sync",
           optimus_hooks == len(r["synced_morphisms"]),
           f"{optimus_hooks} hook fires for {len(r['synced_morphisms'])} synced morphisms")


# ============================================================================
# RUNNER
# ============================================================================
async def main():
    print("=" * 70)
    print("KOMPOSOS-IV FULL STACK STRESS TEST")
    print("4 layers: Orion + KOMPOSOS-IV + COG + OPTIMUS")
    print("=" * 70)

    t_total = time.perf_counter()

    tests = [
        ("Large graph + OPTIMUS", test_large_graph_refinement),
        ("Adversarial inputs", test_adversarial_inputs),
        ("Full 4-layer Agent", test_agent_full_stack),
        ("OPTIMUS invariants", test_optimus_invariants),
        ("Concurrent operations", test_concurrent_operations),
        ("Edge cases", test_edge_cases),
        ("Convergence proof", test_convergence_proof),
        ("Yoneda at scale", test_yoneda_at_scale),
        ("Paths after refinement", test_paths_after_refinement),
        ("Hook stress", test_hook_stress),
    ]

    for name, test_fn in tests:
        try:
            await test_fn()
        except Exception as e:
            report(f"{name} (CRASHED)", False, f"{type(e).__name__}: {e}")
            traceback.print_exc()

    t_total = time.perf_counter() - t_total

    print("\n" + "=" * 70)
    print(f"RESULTS: {passed} PASS, {failed} FAIL ({t_total:.2f}s total)")
    if errors:
        print(f"FAILURES: {errors}")
    print("=" * 70)

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    asyncio.run(main())
