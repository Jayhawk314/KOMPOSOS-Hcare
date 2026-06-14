# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Tests: NPI co-load joins the NPI-keyed datasets into one category."""

import domains  # noqa: F401  (path bootstrap)
from core.category import Category

from domains.flow.spine import NPISpine, summarize, synthetic_sections


def _spine(category=None):
    billing, part_d, open_pay, nppes = synthetic_sections()
    sp = NPISpine(category=category)
    sp.add_money_source(billing).add_money_source(part_d)
    sp.add_money_source(open_pay).set_nppes(nppes)
    return sp


def test_coverage_counts_and_overlaps():
    cov = _spine().coverage()
    assert cov.total_npis == 7                 # union of 100..106
    assert cov.per_source["cms_summary"] == 5
    assert cov.per_source["part_d"] == 4
    assert cov.per_source["open_payments"] == 3
    # 100 and 102 are in all three.
    assert cov.all_sources_overlap == 2
    assert cov.in_k_sources[3] == 2
    assert cov.multi_source == 3               # 100,102 (x3) + 104 (x2)
    assert cov.with_specialty == 3


def test_pairwise_overlap():
    cov = _spine().coverage()
    assert cov.pair_overlap["cms_summary&part_d"] == 3      # 100,102,104
    assert cov.pair_overlap["cms_summary&open_payments"] == 2  # 100,102


def test_build_writes_bounded_joined_graph():
    cat = Category(db_path=":memory:")
    sp = _spine(category=cat)
    n = sp.build(min_sources=2, limit=500)
    assert n == 3                              # only multi-source providers
    # The biggest (102) must be present with all three reports edges.
    reports = [m for m in cat.morphisms()
               if m.name == "reports" and m.target == "npi:102"]
    assert {m.source for m in reports} == {
        "source:cms_summary", "source:part_d", "source:open_payments"}


def test_build_limit_caps_nodes():
    cat = Category(db_path=":memory:")
    n = _spine(category=cat).build(min_sources=2, limit=1)
    assert n == 1                              # only the top provider by money


def test_profile_is_unified_view():
    cat = Category(db_path=":memory:")
    sp = _spine(category=cat)
    sp.build(min_sources=2, limit=500)
    prof = sp.profile("102")
    assert prof["specialty"] == "Oncology"
    assert prof["state"] == "FL"
    assert prof["money"]["cms_summary"] == 1_200_000
    assert prof["money"]["part_d"] == 980_000
    assert prof["money"]["open_payments"] == 120_000


def test_summarize_mentions_join():
    text = summarize(_spine().coverage())
    assert "one category on the NPI spine" in text
    assert "pairwise overlaps" in text
