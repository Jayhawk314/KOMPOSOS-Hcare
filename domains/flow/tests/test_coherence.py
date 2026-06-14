# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Phase 1 tests for the flow domain sheaf-coherence engine."""

import domains  # noqa: F401  (path bootstrap)
from core.category import Category

from domains.flow.coherence import (
    GLUE, TENSION, CONTRADICT,
    FlowCoherenceChecker, Section,
    pushforward, sections_from_records,
)
from domains.flow.sources import SOURCES, public_sources


def test_glue_when_sources_agree():
    a = Section("a", {"x": 100.0, "y": 200.0})
    b = Section("b", {"x": 101.0, "y": 199.0})
    res = FlowCoherenceChecker(tolerance=0.02).check_pair(a, b)
    assert res.overlap == 2
    assert res.agreement_rate == 1.0
    assert all(v.verdict == GLUE for v in res.verdicts)


def test_contradiction_is_flagged():
    a = Section("a", {"leak": 1_000_000.0})
    b = Section("b", {"leak": 10_000.0})
    res = FlowCoherenceChecker(tolerance=0.02).check_pair(a, b)
    assert len(res.contradictions()) == 1
    assert res.contradictions()[0].verdict == CONTRADICT


def test_tension_band():
    # discrepancy ~0.05 -> between tol (0.02) and 5*tol (0.10) -> TENSION
    a = Section("a", {"x": 100.0})
    b = Section("b", {"x": 105.0})
    res = FlowCoherenceChecker(tolerance=0.02).check_pair(a, b)
    assert res.verdicts[0].verdict == TENSION


def test_pushforward_conserves_dollars():
    fine = Section("fine", {"p1": 10.0, "p2": 20.0, "p3": 5.0})
    mapping = {"p1": "g1", "p2": "g1", "p3": "g2"}
    grp = pushforward(fine, mapping)
    assert grp.values["g1"] == 30.0
    assert grp.values["g2"] == 5.0
    assert sum(grp.values.values()) == sum(fine.values.values())


def test_sections_from_records_sums_repeats():
    rows = [
        {"npi": "n1", "amt": 100},
        {"npi": "n1", "amt": 50},   # same provider, second line item
        {"npi": "n2", "amt": 200},
    ]
    sec = sections_from_records(rows, source="s", key_field="npi", value_field="amt")
    assert sec.values["n1"] == 150.0
    assert sec.values["n2"] == 200.0


def test_writeback_to_category():
    cat = Category(db_path=":memory:")
    checker = FlowCoherenceChecker(tolerance=0.02, category=cat)
    a = Section("a", {"x": 100.0, "leak": 1_000_000.0})
    b = Section("b", {"x": 100.0, "leak": 1.0})
    checker.check_pair(a, b)
    names = {m.name for m in cat.morphisms()}
    assert "coheres_with" in names
    assert "disputes" in names
    disputes = [m for m in cat.morphisms() if m.name == "disputes"]
    assert any("leak" in m.target for m in disputes)


def test_registry_has_join_keys_and_public_subset():
    assert len(SOURCES) >= 10
    assert all(s.join_key for s in SOURCES)
    pub = public_sources()
    assert 0 < len(pub) < len(SOURCES)  # some restricted sources documented
