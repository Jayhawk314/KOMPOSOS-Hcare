# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Phase 2 tests: the Medicare Advantage paid-vs-consumed 2-cell."""

import domains  # noqa: F401  (path bootstrap)
from core.category import Category

from domains.flow.medicare_advantage import (
    MAContract, MedicareAdvantageTwoCell, summarize, synthetic_contracts,
    DEFAULT_CODING_ADJUSTMENT, assemble_contracts_from_geovar,
    MEDPAC_BENCHMARK_RATIO, MEDPAC_MA_CODING_RISK,
)
from domains.flow.ingest import (
    write_fixtures, load_ma_contracts, load_ma_enrollment, load_ffs_geovar,
)


def test_decomposition_identity():
    """coding_intensity + benchmark_spread must equal overpayment exactly."""
    c = MAContract("H1", 100, benchmark_per_capita=12000,
                   ffs_per_capita=11000, risk_score=1.2)
    r = MedicareAdvantageTwoCell().evaluate(c)
    assert abs((r.coding_intensity + r.benchmark_spread) - r.overpayment) < 1e-6


def test_coding_adjustment_applied():
    c = MAContract("H1", 1000, benchmark_per_capita=10000,
                   ffs_per_capita=10000, risk_score=1.10)
    # With benchmark == ffs and ffs_risk=1.0, overpayment is purely coding:
    # paid = E*bm*(risk*(1-adj)); consumed = E*ffs*1.0
    eng = MedicareAdvantageTwoCell()
    r = eng.evaluate(c)
    er = 1.10 * (1 - DEFAULT_CODING_ADJUSTMENT)
    assert abs(r.paid - 1000 * 10000 * er) < 1e-6
    assert abs(r.benchmark_spread) < 1e-6  # bm == ffs


def test_fair_plan_has_negligible_overpayment():
    c = MAContract("H1", 1000, benchmark_per_capita=11000,
                   ffs_per_capita=11000, risk_score=1.0)
    r = MedicareAdvantageTwoCell().evaluate(c)
    # risk 1.0 with the statutory haircut means paid slightly BELOW consumed.
    assert r.ratio == 0.0
    assert r.overpayment <= 0.0


def test_ratio_clamped_unit_interval():
    for c in synthetic_contracts():
        r = MedicareAdvantageTwoCell().evaluate(c)
        assert 0.0 <= r.ratio <= 1.0


def test_writes_parallel_morphisms_and_overpays_edge():
    cat = Category(db_path=":memory:")
    eng = MedicareAdvantageTwoCell(category=cat)
    eng.evaluate(MAContract("H2002", 120000, 12000, 11000, 1.21))
    names = [m.name for m in cat.morphisms()]
    assert any(n.startswith("paid::") for n in names)
    assert any(n.startswith("consumed::") for n in names)
    overpays = [m for m in cat.morphisms() if m.name == "overpays"]
    assert len(overpays) == 1
    assert overpays[0].metadata.get("coding_intensity") is not None


def test_cosmos_two_cells_one_per_contract():
    from core.cosmos import InfinityCosmos
    cat = Category(db_path=":memory:")
    cosmos = InfinityCosmos(cat)
    eng = MedicareAdvantageTwoCell(category=cat, cosmos=cosmos)
    eng.evaluate_all(synthetic_contracts())
    h2k = cosmos.homotopy_2_category(rebuild=True)
    assert len(h2k.two_cells) == len(synthetic_contracts())


def test_loaders_from_fixtures(tmp_path):
    paths = write_fixtures(str(tmp_path))
    contracts = load_ma_contracts(paths["ma_contracts"])
    assert {c.contract_id for c in contracts} == {"H1001", "H2002", "H3003"}
    h2002 = next(c for c in contracts if c.contract_id == "H2002")
    assert h2002.risk_score == 1.21
    enr = load_ma_enrollment(paths["ma_enrollment"])
    assert enr["H1001"] == 40000  # summed across two plan rows


def test_summarize_runs():
    results = MedicareAdvantageTwoCell().evaluate_all(synthetic_contracts())
    text = summarize(results)
    assert "OVERPAYMENT" in text
    assert "coding intensity" in text


def test_assemble_from_geovar_uses_real_consumed_side(tmp_path):
    """The consumed side must be the real FFS per-capita x real MA enrollment."""
    paths = write_fixtures(str(tmp_path))
    geo = load_ffs_geovar(paths["ffs_geovar"], year=2024, geo_level="State")
    contracts = assemble_contracts_from_geovar(geo)
    by_id = {c.contract_id: c for c in contracts}
    # PR is a territory in the skip set; CA and TX remain.
    assert set(by_id) == {"CA", "TX"}
    ca = by_id["CA"]
    assert ca.enrollment == 3_466_321                 # real MA count
    assert ca.ffs_per_capita == 13_254.0              # real standardized FFS p.c.
    assert ca.benchmark_per_capita == 13_254.0 * MEDPAC_BENCHMARK_RATIO
    assert ca.risk_score == MEDPAC_MA_CODING_RISK
    # consumed in the 2-cell == enrollment * real FFS per-capita (ffs_risk=1).
    r = MedicareAdvantageTwoCell().evaluate(ca)
    assert abs(r.consumed - 3_466_321 * 13_254.0) < 1.0
    assert r.overpayment > 0
    assert abs((r.coding_intensity + r.benchmark_spread) - r.overpayment) < 1e-3


def test_assemble_from_geovar_overrides(tmp_path):
    """Real per-geo ratebook/risk inputs can replace the modeled defaults."""
    paths = write_fixtures(str(tmp_path))
    geo = load_ffs_geovar(paths["ffs_geovar"], year=2024, geo_level="State")
    contracts = assemble_contracts_from_geovar(
        geo, overrides={"CA": {"benchmark_per_capita": 15_000.0, "risk_score": 1.10}})
    ca = next(c for c in contracts if c.contract_id == "CA")
    assert ca.benchmark_per_capita == 15_000.0
    assert ca.risk_score == 1.10
    # TX keeps the modeled defaults.
    tx = next(c for c in contracts if c.contract_id == "TX")
    assert tx.risk_score == MEDPAC_MA_CODING_RISK
