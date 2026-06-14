# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Phase 3 tests: Yoneda-distance peer-outlier billing detection."""

import domains  # noqa: F401  (path bootstrap)
from core.category import Category

from domains.flow.outliers import (
    yoneda_distance, normalize, consensus,
    YonedaOutlierEngine, synthetic_fingerprints,
)
from domains.flow.ingest import write_fixtures, load_provider_fingerprints


def test_distance_zero_for_identical_mix():
    a = {"x": 10, "y": 30}
    b = {"x": 1, "y": 3}  # same proportions, different scale
    assert yoneda_distance(a, b) == 0.0


def test_distance_one_for_disjoint_codes():
    assert yoneda_distance({"x": 5}, {"y": 5}) == 1.0


def test_distance_is_symmetric_and_unit_interval():
    a, b = {"x": 7, "y": 3}, {"x": 1, "z": 9}
    d1, d2 = yoneda_distance(a, b), yoneda_distance(b, a)
    assert abs(d1 - d2) < 1e-9
    assert 0.0 <= d1 <= 1.0


def test_normalize_sums_to_one():
    n = normalize({"a": 2, "b": 2})
    assert abs(sum(n.values()) - 1.0) < 1e-9


def test_consensus_is_mean_of_peers():
    c = consensus([{"a": 1}, {"b": 1}])
    assert abs(c["a"] - 0.5) < 1e-9 and abs(c["b"] - 0.5) < 1e-9


def test_synthetic_flags_the_upcoder():
    fps, specs = synthetic_fingerprints()
    eng = YonedaOutlierEngine(min_peers=3, min_billed=50_000)
    results = eng.analyze(fps, specs)
    flagged = [r for r in results if r.is_outlier]
    assert len(flagged) == 1
    assert flagged[0].npi == "1000000099"
    assert "93799" in flagged[0].driver_codes


def test_normal_peers_not_flagged():
    fps, specs = synthetic_fingerprints()
    eng = YonedaOutlierEngine(min_peers=3, min_billed=50_000)
    results = {r.npi: r for r in eng.analyze(fps, specs)}
    assert results["1000000001"].is_outlier is False


def test_min_peers_guard_suppresses_tiny_groups():
    fps = {"n1": {"a": 100_000}, "n2": {"b": 100_000}}
    specs = {"n1": "S", "n2": "S"}
    eng = YonedaOutlierEngine(min_peers=3)  # only 2 peers -> no flags
    assert not any(r.is_outlier for r in eng.analyze(fps, specs))


def test_writeback_to_category():
    fps, specs = synthetic_fingerprints()
    cat = Category(db_path=":memory:")
    eng = YonedaOutlierEngine(min_peers=3, min_billed=50_000, category=cat)
    eng.analyze(fps, specs)
    edges = [m for m in cat.morphisms() if m.name == "outlier_in"]
    assert len(edges) == 1
    assert edges[0].confidence >= 0.6


def test_fingerprint_loader_from_fixture(tmp_path):
    paths = write_fixtures(str(tmp_path))
    fps, specs = load_provider_fingerprints(paths["service"])
    # NPI ...001 billed two codes in the fixture.
    assert set(fps["1000000001"]) == {"99213", "93000"}
    assert specs["1000000099"] == "Oncology"
