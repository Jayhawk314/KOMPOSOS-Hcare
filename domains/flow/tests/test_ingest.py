# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Phase 2 tests: real-schema loaders (run on generated fixtures)."""

import gzip
import os

import domains  # noqa: F401  (path bootstrap)
from core.category import Category

from domains.flow.ingest import (
    load_provider_service, load_provider_summary, load_part_d,
    load_open_payments, load_usaspending, load_nppes, specialty_map,
    FlowCategoryBuilder, write_fixtures, load_ffs_geovar, load_ma_ratebook,
    load_ma_risk, _to_float, _resolve,
)
from domains.flow.coherence import FlowCoherenceChecker, pushforward


def _fixtures(tmp_path):
    return write_fixtures(str(tmp_path))


def test_to_float_handles_money_strings():
    assert _to_float("$1,200,000") == 1_200_000.0
    assert _to_float("") == 0.0
    assert _to_float("N/A") == 0.0
    assert _to_float(None) == 0.0


def test_resolve_is_case_and_space_insensitive():
    assert _resolve(["Rndrng_NPI", "Tot_Srvcs"], ["rndrng_npi"]) == "Rndrng_NPI"
    assert _resolve([" NPI "], ["npi"]) == " NPI "
    assert _resolve(["X"], ["y"]) is None


def test_provider_service_sums_line_items_to_npi(tmp_path):
    paths = _fixtures(tmp_path)
    sec = load_provider_service(paths["service"])
    # NPI ...001 had two line items: 1000*50 + 500*20 = 60,000
    assert sec.values["1000000001"] == 60000.0
    # outlier ...099: 9000*300 = 2,700,000
    assert sec.values["1000000099"] == 2_700_000.0
    assert sec.layer == "3-provider"


def test_summary_loads_aggregate(tmp_path):
    paths = _fixtures(tmp_path)
    sec = load_provider_summary(paths["summary"])
    assert sec.values["1000000099"] == 300_000.0


def test_conservation_finds_the_leak(tmp_path):
    paths = _fixtures(tmp_path)
    service = load_provider_service(paths["service"])
    summary = load_provider_summary(paths["summary"])
    res = FlowCoherenceChecker(tolerance=0.02).check_all([service, summary])
    contra = [v for r in res for v in r.contradictions()]
    assert any(v.entity == "1000000099" for v in contra)


def test_part_d_and_open_payments(tmp_path):
    paths = _fixtures(tmp_path)
    pd = load_part_d(paths["part_d"])
    op = load_open_payments(paths["open_payments"])
    assert pd.values["1000000099"] == 980_000.0
    assert op.values["1000000099"] == 45_000.0
    assert op.layer == "4-pharma"


def test_usaspending_keyed_by_uei(tmp_path):
    paths = _fixtures(tmp_path)
    us = load_usaspending(paths["usaspending"])
    assert us.values["UEI0000ABC"] == 2_500_000.0
    assert us.layer == "0-federal"


def test_nppes_specialty_map_and_pushforward(tmp_path):
    paths = _fixtures(tmp_path)
    nppes = load_nppes(paths["nppes"])
    assert nppes["1000000001"]["state"] == "TX"
    spec = specialty_map(nppes)
    service = load_provider_service(paths["service"])
    grp = pushforward(service, spec)
    # ...002 (60k) + ...099 (2.7M) share taxonomy 207RX0202X
    assert grp.values["207RX0202X"] == 2_760_000.0


def test_gzip_is_transparent(tmp_path):
    paths = _fixtures(tmp_path)
    gz = str(tmp_path / "cms_summary.csv.gz")
    with open(paths["summary"], "rb") as src, gzip.open(gz, "wb") as dst:
        dst.write(src.read())
    sec = load_provider_summary(gz)
    assert sec.values["1000000099"] == 300_000.0


def test_builder_writes_provenance(tmp_path):
    paths = _fixtures(tmp_path)
    cat = Category(db_path=":memory:")
    builder = FlowCategoryBuilder(cat)
    n = builder.add_section(load_provider_summary(paths["summary"]))
    assert n == 3
    reports = [m for m in cat.morphisms() if m.name == "reports"]
    assert len(reports) == 3
    builder.add_nppes(load_nppes(paths["nppes"]))
    assert any(m.name == "has_specialty" for m in cat.morphisms())


def test_load_ffs_geovar_filters_year_level_age(tmp_path):
    paths = _fixtures(tmp_path)
    geo = load_ffs_geovar(paths["ffs_geovar"], year=2024, geo_level="State")
    # Only the 2024 / State / All rows: CA, TX, PR (National excluded by level;
    # the <65 and 2023 CA rows excluded by age/year filters).
    assert set(geo) == {"CA", "TX", "PR"}
    assert geo["CA"]["ma_cnt"] == 3_466_321
    assert geo["CA"]["ffs_stdzd_pc"] == 13_254.0
    assert geo["TX"]["ffs_pc"] == 13_500.0  # unstandardized retained too


def test_load_ffs_geovar_national(tmp_path):
    paths = _fixtures(tmp_path)
    geo = load_ffs_geovar(paths["ffs_geovar"], year=2024, geo_level="National")
    assert geo["National"]["ma_cnt"] == 33_677_969
    assert geo["National"]["ffs_stdzd_pc"] == 12_553.26


def test_load_ma_ratebook_county_mean_annualized(tmp_path):
    paths = _fixtures(tmp_path)
    rb = load_ma_ratebook(paths["ma_ratebook"], bonus="5%")
    # CA: mean monthly 5% rate = (1100+1300)/2 = 1200 -> annual 14,400.
    assert rb["CA"] == 14_400.0
    # TX: single county monthly 1000 -> annual 12,000.
    assert rb["TX"] == 12_000.0
    # Puerto Rico is not in the 50-state+DC map -> excluded.
    assert "PR" not in rb


def test_load_ma_ratebook_bonus_tier(tmp_path):
    paths = _fixtures(tmp_path)
    rb0 = load_ma_ratebook(paths["ma_ratebook"], bonus="0%")
    # CA 0% tier: (1000+1200)/2 = 1100 -> annual 13,200.
    assert rb0["CA"] == 13_200.0


def test_load_ma_risk(tmp_path):
    paths = _fixtures(tmp_path)
    risk = load_ma_risk(paths["ma_risk"])
    assert risk["CA"] == 1.15
    assert risk["TX"] == 1.25
