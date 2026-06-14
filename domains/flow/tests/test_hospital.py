# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Tests: hospital price coherence ('same DRG, different price')."""

import domains  # noqa: F401  (path bootstrap)
from core.category import Category

from domains.flow.hospital import (
    HospitalPriceCoherence, summarize, synthetic_records,
)
from domains.flow.ingest import write_fixtures, load_inpatient


def test_load_inpatient(tmp_path):
    paths = write_fixtures(str(tmp_path))
    recs = load_inpatient(paths["inpatient"])
    assert len(recs) == 6
    pricey = next(r for r in recs if r["ccn"] == "450099")
    assert pricey["total_pymt"] == 40000.0
    assert pricey["drg"] == "470"


def test_flags_payment_outlier_above_peers():
    recs = synthetic_records()
    rep = HospitalPriceCoherence().analyze(recs)
    # The planted pricey joint hospital is flagged.
    flagged = {o.ccn for o in rep.outliers}
    assert "450099" in flagged
    o = next(o for o in rep.outliers if o.ccn == "450099")
    assert o.ratio > 1.5
    assert o.excess > 0
    assert rep.total_excess >= o.excess


def test_equal_payments_not_flagged_despite_charge_spread():
    """DRG 247 has a huge charge spread but identical payments -> no payment
    outlier (charges are sticker prices, not what is paid)."""
    recs = synthetic_records()
    rep = HospitalPriceCoherence().analyze(recs)
    assert not any(o.drg == "247" for o in rep.outliers)
    # ...but it IS the most charge-dispersed DRG.
    assert rep.dispersed_drgs[0].drg == "247"
    assert rep.dispersed_drgs[0].charge_p90_p10 > 5.0


def test_writes_ccn_spine_edges():
    recs = synthetic_records()
    cat = Category(db_path=":memory:")
    rep = HospitalPriceCoherence(category=cat).analyze(recs)
    edges = [m for m in cat.morphisms() if m.name.startswith("overpriced_for")]
    assert len(edges) == len(rep.outliers)
    # CCN-keyed hospital objects exist (the hospital spine).
    assert cat.get("ccn:450099") is not None


def test_summarize_runs():
    rep = HospitalPriceCoherence().analyze(synthetic_records())
    text = summarize(rep)
    assert "same DRG, different price" in text
    assert "peer median" in text
