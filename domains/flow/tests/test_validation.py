# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Tests: cross-check the MA estimate against published MedPAC/RADV/OIG figures."""

import domains  # noqa: F401  (path bootstrap)

from domains.flow.validation import (
    PUBLISHED, Benchmark, cross_check, summarize_cross_check,
)


def test_published_has_economic_and_enforcement_with_citations():
    assert PUBLISHED["medpac_2025"].kind == "economic"
    assert PUBLISHED["radv_finalrule"].kind == "enforcement"
    # Every benchmark must carry a source + url (this is a credibility module).
    for b in PUBLISHED.values():
        assert isinstance(b, Benchmark)
        assert b.source and b.url
    # MedPAC 2025 decomposition adds up to the headline total.
    m = PUBLISHED["medpac_2025"]
    assert abs(sum(m.components.values()) - m.total_usd) < 1e-6


def test_cross_check_ratio_and_pct():
    # paid/consumed chosen so overpayment = $84B and pct above FFS = 20%.
    consumed = 420e9
    paid = consumed * 1.20            # 504e9 -> overpayment 84e9
    cc = cross_check(paid, consumed, against="medpac_2025")
    assert abs(cc.our_total - 84e9) < 1e6
    assert abs(cc.dollar_ratio - 1.0) < 1e-3
    assert abs(cc.our_pct_above_ffs - 0.20) < 1e-6
    assert cc.verdict == "CONSISTENT"


def test_verdict_bands():
    # Verdict keys on the dollar ratio vs the $84B benchmark.
    consumed = 420e9
    # overpayment ~ $84B -> 1.0x -> CONSISTENT
    assert cross_check(consumed + 84e9, consumed, against="medpac_2025").verdict \
        == "CONSISTENT"
    # overpayment ~ $107B -> 1.28x -> same order, high
    assert "SAME ORDER" in cross_check(consumed + 107e9, consumed,
                                       against="medpac_2025").verdict
    # overpayment ~ $300B -> 3.6x -> out of range
    assert "OUT OF RANGE" in cross_check(consumed + 300e9, consumed,
                                         against="medpac_2025").verdict


def test_summary_mentions_medpac_and_enforcement():
    text = summarize_cross_check(524.9e9, 417.5e9, coding_intensity=53.9e9)
    assert "MedPAC" in text
    assert "RADV" in text
    assert "our estimate" in text
    # Enforcement figures are flagged as a multiple, not a match.
    assert "x this enforcement figure" in text
