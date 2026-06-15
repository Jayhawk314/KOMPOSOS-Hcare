# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Run the healthcare money-flow coherence check.

Demo on synthetic data (no downloads needed):
    python -m domains.flow.run_coherence --synthetic

List the data sources we glue:
    python -m domains.flow.run_coherence --registry

Real data (Phase 2 -- loaders are stubs for now):
    python -m domains.flow.run_coherence \\
        --provider data/medicare_physician_2023.csv \\
        --usaspending data/usaspending_hhs_2023.csv

Datasets:
    CMS provider summary: https://data.cms.gov/provider-summary-by-type-of-service
    USASpending:          https://api.usaspending.gov/
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional

# Bootstrap the categorical runtime onto sys.path (see domains/__init__.py).
import domains  # noqa: F401
from core.category import Category

from domains.flow.coherence import (
    FlowCoherenceChecker,
    Section,
    pushforward,
    summarize,
)
from domains.flow.sources import print_registry


def _synthetic_sections():
    """Three sections of the same money graph, with planted leaks.

    - usaspending : top-of-chain federal obligations per provider
    - cms_billing : what each provider actually billed Medicare
    - These should glue. Two providers are planted as leaks:
        npi_over   : bills far more than was obligated (overbilling outlier)
        npi_ghost  : obligated money, ~nothing billed (possible ghost/fraud)
    """
    usaspending = Section(
        source="usaspending_hhs",
        layer="0-federal",
        values={
            "npi_0001": 1_200_000, "npi_0002": 880_000, "npi_0003": 2_400_000,
            "npi_0004": 540_000,  "npi_over": 300_000,  "npi_ghost": 1_000_000,
            "npi_0007": 760_000,  "npi_0008": 1_500_000,
        },
    )
    cms_billing = Section(
        source="cms_billing",
        layer="3-provider",
        values={
            "npi_0001": 1_188_000, "npi_0002": 894_000, "npi_0003": 2_376_000,
            "npi_0004": 545_000,  "npi_over": 2_700_000,  # 9x the obligation
            "npi_ghost": 12_000,                           # money vanished
            "npi_0007": 752_000,  "npi_0008": 1_512_000,
        },
    )
    # provider -> specialty, for the Level-1 pushforward demo.
    specialty = {
        "npi_0001": "cardiology", "npi_0002": "cardiology",
        "npi_0003": "oncology",   "npi_0004": "oncology",
        "npi_over": "oncology",   "npi_ghost": "primary",
        "npi_0007": "primary",    "npi_0008": "radiology",
    }
    return usaspending, cms_billing, specialty


def run_synthetic() -> int:
    usaspending, cms_billing, specialty = _synthetic_sections()
    cat = Category(db_path=":memory:")
    checker = FlowCoherenceChecker(tolerance=0.02, category=cat)

    # Level 0: do the two sources agree per provider?
    results = checker.check_all([usaspending, cms_billing])
    print(summarize(results))

    # Level 1: push both forward along provider -> specialty and re-check.
    print("\n" + "=" * 64)
    print("Level 1: pushforward provider -> specialty (money conservation)")
    us_grp = pushforward(usaspending, specialty)
    cms_grp = pushforward(cms_billing, specialty)
    grp_results = FlowCoherenceChecker(tolerance=0.02).check_all([us_grp, cms_grp])
    print(summarize(grp_results))

    # Show the structure written back into the Category.
    disputes = [m for m in cat.morphisms() if m.name == "disputes"]
    print("\n" + "=" * 64)
    print(f"written to Category: {len(cat.objects())} objects, "
          f"{len(cat.morphisms())} morphisms ({len(disputes)} disputes)")
    for m in sorted(disputes, key=lambda x: -x.confidence):
        print(f"   {m.source} -disputes-> {m.target}  (conf={m.confidence})")
    return 0


def run_real(args) -> int:
    """Phase 2: real CMS data coherence.

    The headline real-data check needs no fabricated joins: CMS publishes the
    SAME billing both as line items ('by Provider and Service') and as a
    per-provider aggregate ('by Provider'). Summing the line items to NPI is a
    pushforward that MUST equal the aggregate. Where it does not glue, a source
    is wrong (a real conservation check on the same NPI key).
    """
    from domains.flow.ingest import (
        load_provider_service, load_provider_summary,
        load_nppes, specialty_map, FlowCategoryBuilder,
    )

    if not (args.service and args.summary):
        print("Phase 2 conservation check needs --service AND --summary "
              "(CMS by-Provider-and-Service + by-Provider).")
        print("See domains/flow/sources/registry.py for download URLs.")
        return 1

    cat = Category(db_path=":memory:")
    checker = FlowCoherenceChecker(tolerance=0.02, category=cat)

    print("Loading CMS line items (by Provider and Service)...")
    service = load_provider_service(args.service)
    print(f"  {len(service)} providers, ${sum(service.values.values()):,.0f} billed")
    print("Loading CMS aggregate (by Provider)...")
    summary = load_provider_summary(args.summary)
    print(f"  {len(summary)} providers, ${sum(summary.values.values()):,.0f} billed")

    # Conservation: sum-of-line-items per NPI must equal the aggregate.
    print("\nLevel 0: line-item pushforward to NPI  vs  provider aggregate")
    results = checker.check_all([service, summary])
    print(summarize(results))

    # Optional Level-1 pushforward along NPI -> specialty (needs NPPES, or the
    # specialty column already present in the CMS files in a later step).
    if args.nppes:
        print("\nLoading NPPES for NPI -> specialty pushforward...")
        nppes = load_nppes(args.nppes)
        spec = specialty_map(nppes)
        FlowCategoryBuilder(cat).add_nppes(nppes)
        svc_grp = pushforward(service, spec, source_suffix="@specialty")
        sum_grp = pushforward(summary, spec, source_suffix="@specialty")
        print("Level 1: provider -> specialty (money conservation)")
        print(summarize(FlowCoherenceChecker(tolerance=0.02).check_all([svc_grp, sum_grp])))

    disputes = [m for m in cat.morphisms() if m.name == "disputes"]
    print(f"\nwritten to Category: {len(cat.objects())} objects, "
          f"{len(cat.morphisms())} morphisms ({len(disputes)} disputes)")
    return 0


def run_ma(contracts_path: Optional[str] = None) -> int:
    """Medicare Advantage paid-vs-consumed 2-cell (the headline overpayment).

    With no path, runs on synthetic contracts. The cosmos auto-detects the
    parallel paid/consumed morphisms and materializes the 2-cell.
    """
    from domains.flow.medicare_advantage import (
        MedicareAdvantageTwoCell, summarize as ma_summarize, synthetic_contracts,
    )

    if contracts_path:
        from domains.flow.ingest import load_ma_contracts
        contracts = load_ma_contracts(contracts_path)
        print(f"loaded {len(contracts)} MA contracts from {contracts_path}\n")
    else:
        contracts = synthetic_contracts()
        print("synthetic MA contracts (use --ma <csv> for real data)\n")

    cat = Category(db_path=":memory:")
    cosmos = None
    try:
        from core.cosmos import InfinityCosmos
        cosmos = InfinityCosmos(cat)
    except Exception:
        pass  # 2-cell still computed; formal registration skipped.

    engine = MedicareAdvantageTwoCell(category=cat, cosmos=cosmos)
    results = engine.evaluate_all(contracts)
    print(ma_summarize(results))

    overpays = [m for m in cat.morphisms() if m.name == "overpays"]
    two_cells = 0
    if cosmos is not None:
        try:
            # rebuild so auto-detection sees every paid/consumed parallel pair
            two_cells = len(cosmos.homotopy_2_category(rebuild=True).two_cells)
        except Exception:
            two_cells = 0
    print(f"\nCategory: {len(cat.objects())} objects, {len(cat.morphisms())} "
          f"morphisms ({len(overpays)} overpays edges); "
          f"{two_cells} 2-cells in h2K")
    return 0


def run_ma_geovar(geovar_path: str, year=2024,
                  benchmark_ratio: Optional[float] = None,
                  ma_risk: Optional[float] = None,
                  ratebook_path: Optional[str] = None,
                  bonus: str = "5%",
                  risk_path: Optional[str] = None,
                  crosswalk_path: Optional[str] = None) -> int:
    """MA paid-vs-consumed 2-cell on REAL FFS Geographic Variation data.

    The consumed side (FFS per-capita x real MA enrollment, per state) is real
    CMS data. The paid side uses the REAL CMS ratebook benchmark when
    ``ratebook_path`` is given (else a documented MedPAC ratio), and real MA
    risk scores when ``risk_path`` is given (else the documented MedPAC coding
    parameter -- per-geo MA risk is not freely public).
    Cross-check the national total against MedPAC's published MA overpayment.
    """
    from domains.flow.ingest import (
        load_ffs_geovar, load_ma_ratebook, load_ma_risk,
        load_ssa_fips_crosswalk, load_county_ma_enrollment,
    )
    from domains.flow.medicare_advantage import (
        MedicareAdvantageTwoCell, assemble_contracts_from_geovar,
        summarize as ma_summarize,
        MEDPAC_BENCHMARK_RATIO, MEDPAC_MA_CODING_RISK,
    )

    br = benchmark_ratio if benchmark_ratio is not None else MEDPAC_BENCHMARK_RATIO
    rs = ma_risk if ma_risk is not None else MEDPAC_MA_CODING_RISK
    print(f"loading FFS Geographic Variation PUF (year {year}, by state)...")
    geovar = load_ffs_geovar(geovar_path, year=year, geo_level="State")

    # Build per-state overrides from real sources where available.
    overrides: dict = {}
    bm_src = f"MedPAC ratio {br}"
    if ratebook_path:
        weights = None
        weighting = "unweighted county mean"
        if crosswalk_path:
            crosswalk = load_ssa_fips_crosswalk(crosswalk_path)       # ssa -> fips
            county_enr = load_county_ma_enrollment(geovar_path, year=year)  # fips -> cnt
            weights = {ssa: county_enr.get(fips, 0)
                       for ssa, fips in crosswalk.items()}
            weighting = (f"MA-enrollment-weighted via SSA<->FIPS crosswalk "
                         f"({len(crosswalk)} counties, {len(county_enr)} with enrollment)")
        ratebook = load_ma_ratebook(ratebook_path, bonus=bonus, weights=weights)
        for st, bm in ratebook.items():
            overrides.setdefault(st, {})["benchmark_per_capita"] = bm
        bm_src = (f"REAL ratebook ({len(ratebook)} states, {bonus} bonus tier, "
                  f"{weighting})")
    risk_src = f"MedPAC {rs}"
    if risk_path:
        riskmap = load_ma_risk(risk_path)
        for st, r in riskmap.items():
            overrides.setdefault(st, {})["risk_score"] = r
        risk_src = f"REAL risk file ({len(riskmap)} geos)"

    contracts = assemble_contracts_from_geovar(
        geovar, benchmark_ratio=br, ma_risk_score=rs, overrides=overrides)
    print(f"  {len(contracts)} states  (consumed=REAL FFS per-capita x REAL MA "
          f"enrollment;\n   benchmark={bm_src}; MA risk={risk_src})\n")

    cat = Category(db_path=":memory:")
    cosmos = None
    try:
        from core.cosmos import InfinityCosmos
        cosmos = InfinityCosmos(cat)
    except Exception:
        pass
    engine = MedicareAdvantageTwoCell(category=cat, cosmos=cosmos)
    results = engine.evaluate_all(contracts)
    print(ma_summarize(results))

    # Cross-check the national total against MedPAC / RADV / OIG.
    from domains.flow.validation import summarize_cross_check
    total_paid = sum(r.paid for r in results)
    total_consumed = sum(r.consumed for r in results)
    total_coding = sum(r.coding_intensity for r in results)
    print("\n" + summarize_cross_check(total_paid, total_consumed, total_coding))

    overpays = [m for m in cat.morphisms() if m.name == "overpays"]
    two_cells = 0
    if cosmos is not None:
        try:
            two_cells = len(cosmos.homotopy_2_category(rebuild=True).two_cells)
        except Exception:
            two_cells = 0
    print(f"\nCategory: {len(cat.objects())} objects, {len(cat.morphisms())} "
          f"morphisms ({len(overpays)} overpays edges); {two_cells} 2-cells in h2K")
    if not risk_path:
        print("\nNOTE: MA risk score is the documented MedPAC parameter -- "
              "per-geo MA risk is not freely public (CMS uses restricted "
              "encounter data). Supply --ma-risk-file <csv> to use real scores.")
    return 0


def run_scenario(args) -> int:
    """THE POLICY-SCENARIO ENGINE (the pivot): coding intensity is endogenous.

    Builds real markets (FFS GeoVar + ratebook benchmark), calibrates the
    inspection-game baseline to the validated forensic overpayment (the gate),
    then shows the equilibrium response of overpayment to each policy lever.
    With --ma-geovar present it runs on REAL data; else a synthetic-market demo.
    """
    from domains.flow.medicare_advantage import (
        MedicareAdvantageTwoCell, assemble_contracts_from_geovar,
    )
    from domains.flow.scenario import (
        markets_from_contracts, synthetic_markets, BehavioralModel,
        ScenarioEngine, PolicyLevers, v1_scenarios, compare,
    )

    if args.ma_geovar:
        from domains.flow.ingest import (
            load_ffs_geovar, load_ma_ratebook, load_ssa_fips_crosswalk,
            load_county_ma_enrollment,
        )
        print("loading real markets (FFS GeoVar + MA ratebook)...", flush=True)
        geo = load_ffs_geovar(args.ma_geovar, year=args.ma_year, geo_level="State")
        overrides: dict = {}
        if args.ma_ratebook:
            weights = None
            if args.ma_crosswalk:
                xw = load_ssa_fips_crosswalk(args.ma_crosswalk)
                enr = load_county_ma_enrollment(args.ma_geovar, year=args.ma_year)
                weights = {s: enr.get(f, 0) for s, f in xw.items()}
            for s, bm in load_ma_ratebook(args.ma_ratebook, bonus=args.ma_bonus,
                                          weights=weights).items():
                overrides.setdefault(s, {})["benchmark_per_capita"] = bm
        contracts = assemble_contracts_from_geovar(geo, overrides=overrides)
        markets = markets_from_contracts(contracts)
        src = f"REAL ({len(markets)} states, 2024 GeoVar + ratebook)"
    else:
        markets = synthetic_markets()
        src = "synthetic markets (use --ma-geovar [...] for real data)"

    # The validation gate: the forensic total on these exact markets (fixed 1.20).
    forensic = MedicareAdvantageTwoCell().evaluate_all(
        assemble := [m_to_contract(m) for m in markets])
    target = sum(r.overpayment for r in forensic)
    print(f"  markets: {src}")
    print(f"  forensic baseline (fixed MedPAC risk 1.20): "
          f"${target/1e9:,.1f}B  <- calibration target\n", flush=True)

    model = BehavioralModel.calibrate(markets, target_overpayment=target)
    engine = ScenarioEngine(markets, model)
    base = engine.run(PolicyLevers.baseline())
    gate_err = abs(base.overpayment - target) / target if target else 0.0
    print(f"  calibrated base_deter={model.base_deter:.5f}  "
          f"(elasticity={model.elasticity}, kappa={model.kappa})")
    print(f"  baseline equilibrium: ${base.overpayment/1e9:,.1f}B, "
          f"mean coding intensity {base.mean_risk:.3f}  "
          f"[gate error {gate_err:.2%}]\n", flush=True)
    if gate_err > 0.01:
        print("  WARNING: baseline does not reproduce the forensic number; "
              "the model is mis-calibrated.\n")

    print(compare(engine, v1_scenarios()))

    # Phase D: the beneficiary side -- the rebate/premium proxy + the tradeoff.
    from domains.flow.premium import compare_tradeoff, summarize_baseline_rebate
    print("\n" + summarize_baseline_rebate(engine))
    print("\n" + compare_tradeoff(engine, v1_scenarios()))

    print("\nHonest boundary: dollars + incentives are the credible output; the "
          "rebate/premium\nbeneficiary side is a STATED proxy (transparent "
          "accounting, parameters exposed);\npatient health is out of scope (no "
          "outcome data in the money graph). This is a\nwhat-if calculator, "
          "calibrated at baseline -- a model, not a forecast.")
    return 0


def run_propagate(args) -> int:
    """PHASE C: a national audit budget propagated to states via right Kan.

    Calibrates as in --scenario, then holds one national audit budget fixed and
    allocates it three ways (uniform / targeted-optimal / equal-per-state),
    showing that the allocation cone -- not just the budget -- moves the outcome.
    """
    from domains.flow.medicare_advantage import (
        MedicareAdvantageTwoCell, assemble_contracts_from_geovar,
    )
    from domains.flow.scenario import (
        markets_from_contracts, synthetic_markets, BehavioralModel, ScenarioEngine,
    )
    from domains.flow.propagation import compare_allocations

    if args.ma_geovar:
        from domains.flow.ingest import (
            load_ffs_geovar, load_ma_ratebook, load_ssa_fips_crosswalk,
            load_county_ma_enrollment,
        )
        print("loading real markets (FFS GeoVar + MA ratebook)...", flush=True)
        geo = load_ffs_geovar(args.ma_geovar, year=args.ma_year, geo_level="State")
        overrides: dict = {}
        if args.ma_ratebook:
            weights = None
            if args.ma_crosswalk:
                xw = load_ssa_fips_crosswalk(args.ma_crosswalk)
                enr = load_county_ma_enrollment(args.ma_geovar, year=args.ma_year)
                weights = {s: enr.get(f, 0) for s, f in xw.items()}
            for s, bm in load_ma_ratebook(args.ma_ratebook, bonus=args.ma_bonus,
                                          weights=weights).items():
                overrides.setdefault(s, {})["benchmark_per_capita"] = bm
        markets = markets_from_contracts(
            assemble_contracts_from_geovar(geo, overrides=overrides))
        src = f"REAL ({len(markets)} states)"
    else:
        markets = synthetic_markets()
        src = "synthetic markets (use --ma-geovar [...] for real data)"

    target = sum(r.overpayment for r in MedicareAdvantageTwoCell().evaluate_all(
        [m_to_contract(m) for m in markets]))
    model = BehavioralModel.calibrate(markets, target_overpayment=target)
    engine = ScenarioEngine(markets, model)
    budget = args.audit_budget
    print(f"  markets: {src}; baseline calibrated to ${target/1e9:,.1f}B\n",
          flush=True)
    print(compare_allocations(engine, budget=budget))
    print("\nThe national knob is ONE number (the audit budget); the right Kan "
          "extension\nallocates it to states under the conservation constraint. "
          "Targeting the\nmarginal leak beats uniform for the same auditor-hours "
          "-- a model result,\nnot a forecast.")
    return 0


def _scenario_engine_from_args(args):
    """Build a calibrated ScenarioEngine from the data flags (shared by the
    scenario / propagate / chain entrypoints). Real if --ma-geovar, else synthetic."""
    from domains.flow.medicare_advantage import (
        MedicareAdvantageTwoCell, assemble_contracts_from_geovar,
    )
    from domains.flow.scenario import (
        markets_from_contracts, synthetic_markets, BehavioralModel, ScenarioEngine,
    )
    if args.ma_geovar:
        from domains.flow.ingest import (
            load_ffs_geovar, load_ma_ratebook, load_ssa_fips_crosswalk,
            load_county_ma_enrollment,
        )
        geo = load_ffs_geovar(args.ma_geovar, year=args.ma_year, geo_level="State")
        overrides: dict = {}
        if args.ma_ratebook:
            weights = None
            if args.ma_crosswalk:
                xw = load_ssa_fips_crosswalk(args.ma_crosswalk)
                enr = load_county_ma_enrollment(args.ma_geovar, year=args.ma_year)
                weights = {s: enr.get(f, 0) for s, f in xw.items()}
            for s, bm in load_ma_ratebook(args.ma_ratebook, bonus=args.ma_bonus,
                                          weights=weights).items():
                overrides.setdefault(s, {})["benchmark_per_capita"] = bm
        markets = markets_from_contracts(
            assemble_contracts_from_geovar(geo, overrides=overrides))
        src = f"REAL ({len(markets)} states)"
    else:
        markets = synthetic_markets()
        src = "synthetic markets (use --ma-geovar [...] for real data)"
    target = sum(r.overpayment for r in MedicareAdvantageTwoCell().evaluate_all(
        [m_to_contract(m) for m in markets]))
    model = BehavioralModel.calibrate(markets, target_overpayment=target)
    return ScenarioEngine(markets, model), target, src


def run_backtest_cli(args) -> int:
    """PHASE G: backtest & sensitivity -- is the behavioral response trustworthy?"""
    from domains.flow.backtest import (
        forensic_overpayment, bootstrap_calibration, state_holdout_cv,
        sensitivity, directional_checks, summarize_backtest,
        uncertainty_bands, summarize_bands,
    )
    eng, target, src = _scenario_engine_from_args(args)
    mkts = eng.markets
    print(f"  markets: {src}; forensic target ${target/1e9:,.1f}B\n", flush=True)
    stab = bootstrap_calibration(mkts)
    oos = state_holdout_cv(mkts, folds=min(5, max(2, len(mkts) // 4)))
    sens = [
        sensitivity(mkts, target, param="elasticity", values=[0.5, 1.0, 2.0, 4.0]),
        sensitivity(mkts, target, param="kappa", values=[0.20, 0.25, 0.30, 0.40]),
    ]
    checks = directional_checks(eng)
    print(summarize_backtest(stab, oos, sens, checks))
    print("\n" + summarize_bands(uncertainty_bands(mkts, target)))
    return 0


def run_chain_cli(args) -> int:
    """PHASE E: the CMS -> provider -> plan chain (site-neutral payment)."""
    from domains.flow.chain import compare_site_neutral
    eng, target, src = _scenario_engine_from_args(args)
    print(f"  markets: {src}; baseline calibrated to ${target/1e9:,.1f}B\n",
          flush=True)
    print(compare_site_neutral(eng))
    print("\nProvider layer is MODELED (no place-of-service data in the MA money "
          "graph),\ncalibrated to identity at baseline -- only directional, "
          "relative effects are claimed.")
    return 0


def run_actors_cli(args) -> int:
    """PHASE E: the activity-theory actor / lever map (the scenario frame)."""
    from domains.flow.actors import build_actor_map, summarize_actor_map
    from domains.flow.scenario import PolicyLevers
    eng, target, src = _scenario_engine_from_args(args)
    base = eng.run(PolicyLevers.baseline())
    ratio = base.pct_above_ffs / (1.0 + base.pct_above_ffs)   # overpay / paid
    print(f"  markets: {src}; grounding overpayment ratio {ratio:.0%}\n", flush=True)
    print(summarize_actor_map(build_actor_map(ratio)))
    return 0


def m_to_contract(m):
    """A scenario Market at the fixed MedPAC risk -- the forensic comparison point."""
    from domains.flow.medicare_advantage import MAContract, MEDPAC_MA_CODING_RISK
    return MAContract(m.geo, m.enrollment, m.benchmark_per_capita,
                      m.ffs_per_capita, risk_score=MEDPAC_MA_CODING_RISK,
                      ffs_risk=m.ffs_risk, name=m.geo)


def run_outliers(service_path: Optional[str] = None) -> int:
    """Yoneda peer-outlier detection on provider billing fingerprints.

    With no path, runs on synthetic cardiology peers + one outlier.
    """
    from domains.flow.outliers import (
        YonedaOutlierEngine, summarize as out_summarize, synthetic_fingerprints,
    )

    if service_path:
        from domains.flow.ingest import load_provider_fingerprints
        fps, specs = load_provider_fingerprints(service_path)
        print(f"loaded {len(fps)} provider fingerprints from {service_path}\n")
        engine = YonedaOutlierEngine()
    else:
        fps, specs = synthetic_fingerprints()
        print("synthetic fingerprints (use --outliers <service.csv> for real data)\n")
        # small synthetic group: relax the peer floor so the demo flags.
        engine = YonedaOutlierEngine(min_peers=3, min_billed=50_000)

    cat = Category(db_path=":memory:")
    engine.category = cat
    results = engine.analyze(fps, specs)
    print(out_summarize(results))
    flags = [m for m in cat.morphisms() if m.name == "outlier_in"]
    print(f"\nCategory: {len(cat.objects())} objects, {len(cat.morphisms())} "
          f"morphisms ({len(flags)} outlier_in edges)")
    return 0


def run_coload(args) -> int:
    """NPI co-load: join billing + Part D + Open Payments + NPPES into one
    category on the shared NPI spine. Real files if given, else synthetic demo.
    """
    from domains.flow.spine import (
        NPISpine, summarize as sp_summarize, synthetic_sections,
        SRC_BILLING, SRC_PART_D, SRC_OPEN_PAY,
    )
    labels = {SRC_BILLING: "billing (CMS by-Provider)",
              SRC_PART_D: "Part D prescribing",
              SRC_OPEN_PAY: "Open Payments (pharma)"}

    cat = Category(db_path=":memory:")
    spine = NPISpine(category=cat)
    real = any([args.summary, args.part_d, args.open_payments])
    if real:
        from domains.flow.ingest import (
            load_provider_summary, load_part_d, load_open_payments,
            load_nppes, specialty_map,
        )
        if args.summary:
            print(f"loading billing {args.summary} ...", flush=True)
            spine.add_money_source(load_provider_summary(args.summary))
        if args.part_d:
            print(f"loading Part D {args.part_d} ...", flush=True)
            spine.add_money_source(load_part_d(args.part_d))
        if args.open_payments:
            print(f"loading Open Payments {args.open_payments} ...", flush=True)
            spine.add_money_source(load_open_payments(args.open_payments))
        if args.nppes:
            print(f"loading NPPES {args.nppes} ...", flush=True)
            spine.set_nppes(load_nppes(args.nppes))
        print()
    else:
        billing, part_d, open_pay, nppes = synthetic_sections()
        spine.add_money_source(billing).add_money_source(part_d)
        spine.add_money_source(open_pay).set_nppes(nppes)
        print("synthetic NPI sections (use --summary/--part-d/--open-payments "
              "for real data)\n")

    report = spine.coverage()
    print(sp_summarize(report, source_labels=labels))

    # Write the most cross-linked providers into the Category and show a profile.
    written = spine.build(min_sources=2, limit=args.coload_limit)
    print(f"\nwrote {written} multi-source providers into the Category "
          f"({len(cat.objects())} objects, {len(cat.morphisms())} morphisms)")
    # Show one fully-joined provider as the unified view.
    sets = {s: set(v) for s, v in spine._money.items()}
    if sets:
        common = set.intersection(*sets.values())
        if common:
            sample = sorted(common, key=lambda n: -sum(
                spine._money[s].get(n, 0) for s in spine._money))[0]
            prof = spine.profile(sample)
            print(f"\nunified profile (appears in all sources): {prof}")
    return 0


def run_conflict(args) -> int:
    """Open Payments x Part D conflict-of-interest 2-cell.

    Real files if given (--open-payments + --part-d [+ --nppes]), else synthetic.
    """
    from domains.flow.conflict import (
        ConflictDetector, summarize as cf_summarize, synthetic_inputs,
    )
    cat = Category(db_path=":memory:")
    cosmos = None
    try:
        from core.cosmos import InfinityCosmos
        cosmos = InfinityCosmos(cat)
    except Exception:
        pass

    if args.open_payments and args.part_d:
        from domains.flow.ingest import (
            load_open_payments, load_part_d, load_nppes, specialty_map,
        )
        print(f"loading Open Payments {args.open_payments} ...", flush=True)
        payments = load_open_payments(args.open_payments).values
        print(f"loading Part D {args.part_d} ...", flush=True)
        prescribing = load_part_d(args.part_d).values
        spec = {}
        if args.nppes:
            spec = specialty_map(load_nppes(args.nppes))
        print(f"  payments: {len(payments):,} NPIs; prescribing: "
              f"{len(prescribing):,} NPIs\n", flush=True)
        engine = ConflictDetector(category=cat, cosmos=cosmos)
    else:
        payments, prescribing, spec = synthetic_inputs()
        print("synthetic conflict inputs (use --open-payments + --part-d for "
              "real data)\n")
        # Tiny demo group: relax the percentile gate so it flags the
        # paid-and-high-prescribing cluster, not just the single top provider.
        engine = ConflictDetector(category=cat, cosmos=cosmos, flag_pct=0.6)

    report = engine.analyze(payments, prescribing, specialty=spec)
    print(cf_summarize(report))

    two_cells = 0
    if cosmos is not None:
        try:
            two_cells = len(cosmos.homotopy_2_category(rebuild=True).two_cells)
        except Exception:
            two_cells = 0
    risks = [m for m in cat.morphisms() if m.name == "conflict_risk"]
    print(f"\nCategory: {len(cat.objects())} objects, {len(cat.morphisms())} "
          f"morphisms ({len(risks)} conflict_risk edges); {two_cells} 2-cells in h2K")
    return 0


def run_ledger(args) -> int:
    """The unified leak ledger: run every detector (real where data paths are
    given, synthetic otherwise), assemble into one ranked, scored output, and
    write a CSV/JSON artifact. This is the 'yesterday's leak, every morning'
    product surface.
    """
    import datetime, os
    from domains.flow import ledger as L
    from domains.flow.delivery import assemble, _paths_from_args

    led = assemble(_paths_from_args(args), allow_synthetic=True, log=_logflush)
    print("\n" + L.summarize(led))

    stamp = datetime.date.today().isoformat()
    os.makedirs("data", exist_ok=True)
    csv_path = f"data/leak_ledger_{stamp}.csv"
    json_path = f"data/leak_ledger_{stamp}.json"
    led.to_csv(csv_path)
    led.to_json(json_path)
    print(f"\nwrote {len(led.findings):,} findings -> {csv_path} + {json_path}")
    return 0


def _logflush(msg):
    print(msg, flush=True)


def run_daily(args) -> int:
    """The daily delivery job: assemble the ledger, diff vs the previous run,
    write the dated artifact set + digest, append run history."""
    from domains.flow.delivery import run_daily as _run_daily, _paths_from_args
    out_dir = args.out_dir or "data/ledger"
    record = _run_daily(_paths_from_args(args), out_dir=out_dir,
                        allow_synthetic=not args.real_only, log=_logflush)
    print(f"\nleak ledger for {record['date']}: {record['findings']:,} findings, "
          f"${record['total']:,.0f}")
    if record.get("prior_date"):
        print(f"  vs {record['prior_date']}: {record['new']:,} new, "
              f"{record['increased']:,} grown, {record['resolved']:,} resolved, "
              f"change ${record['total_change']:,.0f}")
    print(f"  artifacts in {out_dir}/ (digest_{record['date']}.md, latest.*)")
    return 0


def run_conflict_drug(args) -> int:
    """Drug-level Open Payments x Part D conflict (payment about a drug vs
    prescribing of that drug). Real files if given, else synthetic.
    """
    from domains.flow.conflict import (
        DrugLevelConflict, summarize_drug, synthetic_drug_inputs,
    )
    cat = Category(db_path=":memory:")
    cosmos = None
    try:
        from core.cosmos import InfinityCosmos
        cosmos = InfinityCosmos(cat)
    except Exception:
        pass

    if args.open_payments and args.part_d_drug:
        from domains.flow.ingest import (
            load_open_payments_by_drug, load_part_d_by_drug,
        )
        print(f"loading Open Payments by drug {args.open_payments} ...", flush=True)
        payments = load_open_payments_by_drug(args.open_payments)
        drugs = {d for (_n, d) in payments}
        print(f"  {len(payments):,} (npi,drug) payment pairs; {len(drugs):,} drugs",
              flush=True)
        print(f"loading Part D by drug {args.part_d_drug} (filtered to paid drugs) ...",
              flush=True)
        prescribing = load_part_d_by_drug(args.part_d_drug, keep_drugs=drugs)
        print(f"  {len(prescribing):,} (npi,drug) prescribing pairs\n", flush=True)
        engine = DrugLevelConflict(category=cat, cosmos=cosmos)
    else:
        payments, prescribing = synthetic_drug_inputs()
        print("synthetic drug-level inputs (use --open-payments + --part-d-drug "
              "for real data)\n")
        engine = DrugLevelConflict(category=cat, cosmos=cosmos, min_group=3,
                                   min_payment=100, min_prescribing=10_000)

    report = engine.analyze(payments, prescribing)
    print(summarize_drug(report))

    two_cells = 0
    if cosmos is not None:
        try:
            two_cells = len(cosmos.homotopy_2_category(rebuild=True).two_cells)
        except Exception:
            two_cells = 0
    risks = [m for m in cat.morphisms() if m.name == "drug_conflict_risk"]
    print(f"\nflagged (provider,drug) pairs: {len(report.flagged):,}  "
          f"(wrote {len(risks)} to Category, {two_cells} 2-cells in h2K)")
    return 0


def run_conflict_did(args) -> int:
    """Diff-in-differences conflict: prescribing change for providers NEWLY paid
    about a drug vs never-paid. Needs 2 years of Open Payments + Part D by-drug.
    """
    from domains.flow.ingest import load_open_payments_by_drug, load_part_d_by_drug
    from domains.flow.conflict import DiDConflict, summarize_did

    print(f"loading Open Payments POST {args.open_payments} ...", flush=True)
    paid_post = load_open_payments_by_drug(args.open_payments)
    print(f"loading Open Payments PRIOR {args.op_prior} ...", flush=True)
    paid_prior = load_open_payments_by_drug(args.op_prior)
    keep = {d for _n, d in paid_post} | {d for _n, d in paid_prior}
    print(f"  {len(keep):,} drugs with payments in either year", flush=True)
    print(f"loading Part D POST {args.part_d_drug} ...", flush=True)
    rx_post = load_part_d_by_drug(args.part_d_drug, keep_drugs=keep)
    print(f"loading Part D PRIOR {args.partd_drug_prior} ...", flush=True)
    rx_prior = load_part_d_by_drug(args.partd_drug_prior, keep_drugs=keep)
    print(f"  rx pairs: prior {len(rx_prior):,}, post {len(rx_post):,}\n", flush=True)

    report = DiDConflict().analyze(rx_prior, rx_post,
                                   set(paid_post), set(paid_prior))
    print(summarize_did(report))
    return 0


def run_trend_ma(geovar_path: str, years=None) -> int:
    """Multi-year MA overpayment trend from the FFS GeoVar PUF (2014-2024)."""
    from domains.flow.trends import MATrendEngine, summarize as tr_summarize
    yrs = years or list(range(2014, 2025))
    print(f"computing MA overpayment trend {yrs[0]}-{yrs[-1]} from {geovar_path} ...\n",
          flush=True)
    report = MATrendEngine().analyze(geovar_path, yrs)
    print(tr_summarize(report))
    return 0


def run_sheaf(args) -> int:
    """Cohomological coherence (H1 gauge). With --service+--summary: the
    conservation pair (gauge absorbs suppression, residuals localize real
    deviants). With --service only: the charge/allowed/payment 3-view gauge.
    Else: synthetic 3-view demo with two planted offenders.
    """
    from domains.flow.sheaf import sheaf_coherence, synthetic_sections
    if args.service and args.summary:
        from domains.flow.ingest import load_provider_service, load_provider_summary
        print(f"loading {args.service} (line items) + {args.summary} (aggregate)...",
              flush=True)
        secs = [load_provider_service(args.service), load_provider_summary(args.summary)]
        mode = "conservation pair (line-items vs aggregate)"
    elif args.service:
        from domains.flow.ingest import load_provider_money_views
        print(f"loading charge/allowed/payment views from {args.service} ...",
              flush=True)
        secs = list(load_provider_money_views(args.service).values())
        mode = "charge/allowed/payment 3-view"
    else:
        secs = synthetic_sections()
        mode = "synthetic 3-view (2 planted offenders)"
        print("synthetic sheaf demo (use --service [--summary] for real data)")
    print(f"  mode: {mode}; {len(secs)} sources\n", flush=True)

    res = sheaf_coherence(secs)
    print(res.summary())

    # Contrast with the naive threshold (only meaningful for the conservation pair).
    if len(secs) == 2:
        from domains.flow.coherence import FlowCoherenceChecker
        contra = sum(len(r.contradictions())
                     for r in FlowCoherenceChecker(tolerance=0.02).check_all(secs))
        gr = next(iter(res.offenders)).gauge_ratio if res.offenders else 0.0
        print(f"\n  naive 0.02-tolerance check flags {contra:,} entities; the sheaf "
              f"absorbs the\n  systematic scale (gauge ratio ~{gr:.2f}) and ranks "
              "deviants by residual instead.")
    return 0


def run_hospital(path: Optional[str] = None) -> int:
    """Hospital price coherence ('same DRG, different price'). Real Inpatient
    PUF if a path is given, else synthetic."""
    from domains.flow.hospital import (
        HospitalPriceCoherence, summarize as hp_summarize, synthetic_records,
    )
    cat = Category(db_path=":memory:")
    if path:
        from domains.flow.ingest import load_inpatient
        print(f"loading Medicare Inpatient PUF {path} ...", flush=True)
        records = load_inpatient(path)
        print(f"  {len(records):,} (hospital, DRG) records\n", flush=True)
    else:
        records = synthetic_records()
        print("synthetic hospital records (use --hospital <inpatient.csv> for real)\n")
    engine = HospitalPriceCoherence(category=cat)
    report = engine.analyze(records)
    print(hp_summarize(report))
    edges = [m for m in cat.morphisms() if m.name.startswith("overpriced_for")]
    print(f"\nCategory: {len(cat.objects())} objects, {len(cat.morphisms())} "
          f"morphisms ({len(edges)} overpriced_for edges)")
    return 0


def run_nash_sheaf() -> int:
    """Nash sheaf: cross-market strategic-gaming detection (synthetic demo)."""
    from domains.flow.nash_sheaf import (
        NashSheaf, summarize as ns_summarize, synthetic_observations,
    )
    obs = synthetic_observations()
    print("synthetic: 3 plans x 5 markets (honest / strategic gamer / noisy)\n")
    cat = Category(db_path=":memory:")
    engine = NashSheaf(category=cat)
    results = engine.analyze(obs)
    print(ns_summarize(results))
    flags = [m for m in cat.morphisms() if m.name == "strategic_gaming"]
    print(f"\nCategory: {len(cat.objects())} objects, {len(cat.morphisms())} "
          f"morphisms ({len(flags)} strategic_gaming edges)")
    return 0


def run_demo_real() -> int:
    """Exercise the real loaders on generated real-schema fixtures."""
    import tempfile
    from domains.flow.ingest import write_fixtures

    tmp = tempfile.mkdtemp(prefix="flow_fixtures_")
    paths = write_fixtures(tmp)
    print(f"wrote real-schema fixtures to {tmp}\n")

    class _Args:
        service = paths["service"]
        summary = paths["summary"]
        nppes = paths["nppes"]
    return run_real(_Args())


def run_pareto(args) -> int:
    """PHASE I: The Pareto Optimizer.
    
    Sweeps the policy space to find non-dominated outcomes, then uses OPTIMUS
    categorical gradient descent to find the optimal path to a specified target.
    """
    from domains.flow.pareto import run_optimus_search, summarize_pareto
    from domains.flow.market import MarketModel, PatientModel
    
    eng, target, src = _scenario_engine_from_args(args)
    print(f"  markets: {src}; baseline calibrated to ${target/1e9:,.1f}B\n", flush=True)
    
    market_model = MarketModel(competition_index=args.market_competition)
    patient_model = PatientModel(demand_elasticity=args.patient_elasticity)
    
    # Defaults: Aim for 5B saving with no enrollment drop
    target_saving = args.target_saving if args.target_saving is not None else 5_000_000_000.0
    
    # Enrollment baseline needs to be calculated to set default min_enrollment
    base_enr = sum(m.enrollment for m in eng.markets)
    min_enrollment = args.min_enrollment if args.min_enrollment is not None else base_enr
    
    print(f"Optimizing for Target: >${target_saving/1e9:,.1f}B saving, >= {min_enrollment:,} enrollment...")
    print(f"Using Patient elasticity = {args.patient_elasticity}, Market competition = {args.market_competition}\n")
    
    frontier, opt_path = run_optimus_search(eng, market_model, patient_model, target_saving, min_enrollment)
    
    print(summarize_pareto(frontier, opt_path))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="flow domain coherence check")
    p.add_argument("--synthetic", action="store_true",
                   help="run the planted-leak demo (no downloads)")
    p.add_argument("--registry", action="store_true",
                   help="print the data source catalog and exit")
    p.add_argument("--service", help="CMS 'by Provider and Service' CSV/zip/gz")
    p.add_argument("--summary", help="CMS 'by Provider' aggregate CSV/zip/gz")
    p.add_argument("--nppes", help="NPPES NPI registry CSV (for specialty pushforward)")
    p.add_argument("--ma", nargs="?", const="", metavar="CSV",
                   help="Medicare Advantage paid-vs-consumed 2-cell; optional "
                        "contracts CSV, else synthetic")
    p.add_argument("--ma-geovar", metavar="CSV",
                   help="MA 2-cell on REAL data: CMS FFS Geographic Variation "
                        "PUF (consumed=real FFS per-capita x real MA enrollment)")
    p.add_argument("--ma-year", default=2024, type=int,
                   help="year for --ma-geovar (default 2024)")
    p.add_argument("--ma-benchmark-ratio", type=float, default=None,
                   help="paid-side benchmark/FFS ratio (default MedPAC 1.08)")
    p.add_argument("--ma-risk", type=float, default=None,
                   help="paid-side MA risk score (default MedPAC 1.20)")
    p.add_argument("--ma-ratebook", metavar="ZIP/CSV",
                   help="REAL CMS MA ratebook (county rates) for the paid-side "
                        "benchmark, per state (zip or CountyRate CSV)")
    p.add_argument("--ma-bonus", default="5%", choices=["5%", "3.5%", "0%"],
                   help="ratebook quality-bonus tier (default 5%)")
    p.add_argument("--ma-crosswalk", metavar="CSV",
                   help="SSA<->FIPS county crosswalk (NBER ssa_fips_state_county); "
                        "enables MA-enrollment-weighting of the ratebook benchmark")
    p.add_argument("--ma-risk-file", metavar="CSV",
                   help="real MA risk scores by geo (geo,risk_score); per-geo "
                        "MA risk is not freely public")
    p.add_argument("--outliers", nargs="?", const="", metavar="CSV",
                   help="Yoneda peer-outlier billing detection; optional CMS "
                        "by-Provider-and-Service CSV, else synthetic")
    p.add_argument("--nash-sheaf", action="store_true",
                   help="cross-market strategic-gaming detection (Nash sheaf)")
    p.add_argument("--scenario", action="store_true",
                   help="THE POLICY-SCENARIO ENGINE: coding intensity endogenous "
                        "(Nash best response to the levers), calibrated to the "
                        "forensic baseline, then policy-lever comparison. Real "
                        "with --ma-geovar [--ma-ratebook --ma-crosswalk], else synthetic")
    p.add_argument("--pareto", action="store_true",
                   help="PHASE I: The Pareto Optimizer. Sweeps policy space and uses OPTIMUS to find optimal path to target.")
    p.add_argument("--target-saving", type=float, default=None,
                   help="Phase I: Target federal saving constraint (dollars) for --pareto.")
    p.add_argument("--min-enrollment", type=int, default=None,
                   help="Phase I: Minimum enrollment constraint for --pareto.")
    p.add_argument("--patient-elasticity", type=float, default=0.0,
                   help="Phase H: Enrollment change % per 1% change in rebate ratio. "
                        "Default 0.0 (inelastic). Set >0 to enable bidirectional feedback.")
    p.add_argument("--market-competition", type=float, default=1.0,
                   help="Phase H: Multiplier on margin pass-through rate. Default 1.0.")
    p.add_argument("--propagate", action="store_true",
                   help="PHASE C: a national audit budget propagated to per-state "
                        "deterrence via right Kan extension; compares uniform vs "
                        "targeted-optimal vs equal-per-state allocation of the SAME "
                        "budget. Real with --ma-geovar [...], else synthetic")
    p.add_argument("--audit-budget", dest="audit_budget", type=float, default=2.0,
                   help="national audit budget multiplier for --propagate (default 2.0)")
    p.add_argument("--chain", action="store_true",
                   help="PHASE E: the CMS->provider->plan chain as a composed open "
                        "game; a provider-side site-neutral lever re-optimized "
                        "through the plan, fixed vs rebased benchmark regimes. "
                        "Real with --ma-geovar [...], else synthetic")
    p.add_argument("--actors", action="store_true",
                   help="PHASE E: the activity-theory actor/lever map -- who "
                        "optimizes what, who pulls which lever, and the "
                        "contradictions the levers target (the scenario frame)")
    p.add_argument("--backtest", action="store_true",
                   help="PHASE G: backtest & sensitivity -- bootstrap calibration "
                        "stability, state hold-out cross-validation, parameter "
                        "sensitivity (ranking stability), and published-anchor "
                        "directional checks. Real with --ma-geovar [...], else synthetic")
    p.add_argument("--hospital", nargs="?", const="", metavar="CSV",
                   help="hospital price coherence ('same DRG, different price'); "
                        "optional Medicare Inpatient PUF CSV, else synthetic")
    p.add_argument("--trend-ma", dest="trend_ma", metavar="GEOVAR_CSV",
                   help="multi-year MA overpayment trend from the FFS Geographic "
                        "Variation PUF (2014-2024 in one file)")
    p.add_argument("--sheaf", action="store_true",
                   help="cohomological coherence (H1 gauge): parameter-free, "
                        "absorbs systematic scale, localizes real obstructions. "
                        "Uses --service[+--summary], else synthetic")
    p.add_argument("--ledger", action="store_true",
                   help="THE UNIFIED LEAK LEDGER: run every detector (real where "
                        "data paths are given), assemble + rank + score + write "
                        "data/leak_ledger_<date>.csv/.json")
    p.add_argument("--daily", action="store_true",
                   help="THE DAILY JOB: assemble the ledger, diff vs the previous "
                        "run, write dated artifacts + digest.md + latest.* + "
                        "history.jsonl (schedule this)")
    p.add_argument("--out-dir", dest="out_dir", metavar="DIR",
                   help="output directory for --daily (default data/ledger)")
    p.add_argument("--real-only", dest="real_only", action="store_true",
                   help="for --daily: skip detectors lacking real data (no "
                        "synthetic fallback)")
    p.add_argument("--conflict", action="store_true",
                   help="Open Payments x Part D conflict-of-interest 2-cell "
                        "(uses --open-payments + --part-d, else synthetic)")
    p.add_argument("--conflict-drug", action="store_true",
                   help="DRUG-level conflict: payment about a drug vs prescribing "
                        "of that drug (uses --open-payments + --part-d-drug)")
    p.add_argument("--part-d-drug", dest="part_d_drug", metavar="CSV",
                   help="Part D Prescribers by Provider AND Drug CSV")
    p.add_argument("--conflict-did", action="store_true",
                   help="DIFF-IN-DIFF conflict: prescribing change for providers "
                        "newly paid about a drug vs never-paid (needs 2 years)")
    p.add_argument("--op-prior", dest="op_prior", metavar="CSV",
                   help="prior-year Open Payments general CSV (for --conflict-did)")
    p.add_argument("--partd-drug-prior", dest="partd_drug_prior", metavar="CSV",
                   help="prior-year Part D by Provider AND Drug CSV (for --conflict-did)")
    p.add_argument("--coload", action="store_true",
                   help="NPI co-load: join billing + Part D + Open Payments + "
                        "NPPES into one category on the NPI spine (uses "
                        "--summary/--part-d/--open-payments/--nppes, else synthetic)")
    p.add_argument("--part-d", dest="part_d", metavar="CSV",
                   help="Medicare Part D Prescriber by-Provider CSV (for --coload)")
    p.add_argument("--open-payments", dest="open_payments", metavar="CSV",
                   help="CMS Open Payments CSV (for --coload)")
    p.add_argument("--coload-limit", type=int, default=500,
                   help="max multi-source providers to write into the Category")
    p.add_argument("--demo-real", action="store_true",
                   help="generate real-schema fixtures and run the real path on them")
    args = p.parse_args(argv)

    if args.registry:
        print_registry()
        return 0
    if args.synthetic:
        return run_synthetic()
    # The ledger orchestrates several detectors and reuses their data flags
    # (--ma-geovar, --service/--summary, --open-payments, ...), so it must be
    # dispatched BEFORE the individual-detector checks below.
    if args.daily:
        return run_daily(args)
    if args.ledger:
        return run_ledger(args)
    if args.backtest:
        return run_backtest_cli(args)
    if args.chain:
        return run_chain_cli(args)
    if args.actors:
        return run_actors_cli(args)
    if args.propagate:
        return run_propagate(args)
    if args.scenario:
        return run_scenario(args)
    if args.pareto:
        return run_pareto(args)
    if args.ma_geovar:
        return run_ma_geovar(args.ma_geovar, year=args.ma_year,
                             benchmark_ratio=args.ma_benchmark_ratio,
                             ma_risk=args.ma_risk,
                             ratebook_path=args.ma_ratebook,
                             bonus=args.ma_bonus,
                             risk_path=args.ma_risk_file,
                             crosswalk_path=args.ma_crosswalk)
    if args.ma is not None:
        return run_ma(args.ma or None)
    if args.outliers is not None:
        return run_outliers(args.outliers or None)
    if args.conflict_did:
        return run_conflict_did(args)
    if args.conflict_drug:
        return run_conflict_drug(args)
    if args.conflict:
        return run_conflict(args)
    if args.coload:
        return run_coload(args)
    if args.sheaf:
        return run_sheaf(args)
    if args.trend_ma:
        return run_trend_ma(args.trend_ma)
    if args.hospital is not None:
        return run_hospital(args.hospital or None)
    if args.nash_sheaf:
        return run_nash_sheaf()
    if args.demo_real:
        return run_demo_real()
    if args.service or args.summary or args.nppes:
        return run_real(args)
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())


if __name__ == "__main__":
    sys.exit(main())
