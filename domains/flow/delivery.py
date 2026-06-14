# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""The delivery layer -- "yesterday's leak, every morning".

Wraps the unified ledger as a re-runnable job that (1) assembles every detector
into one ledger, (2) writes a dated artifact set, (3) diffs against the previous
run so the headline is *what changed*, and (4) emits a human-readable digest
suitable for email / dashboard / a daily routine. Schedule it (cron, Windows
Task Scheduler, or a Claude Code routine) and it becomes the product surface.

`assemble()` is the single shared ledger-assembly path used by both the CLI
`--ledger` and the daily job; each detector runs on real data when its path is
supplied and (optionally) falls back to synthetic for a demo.
"""

from __future__ import annotations

import datetime
import json
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from domains.flow import ledger as L


@dataclass
class DataPaths:
    ma_geovar: Optional[str] = None
    ma_ratebook: Optional[str] = None
    ma_crosswalk: Optional[str] = None
    ma_year: int = 2024
    ma_bonus: str = "5%"
    open_payments: Optional[str] = None
    part_d_drug: Optional[str] = None
    service: Optional[str] = None
    summary: Optional[str] = None
    hospital: Optional[str] = None


def _paths_from_args(args) -> "DataPaths":
    """Build DataPaths from an argparse namespace (CLI glue)."""
    return DataPaths(
        ma_geovar=getattr(args, "ma_geovar", None),
        ma_ratebook=getattr(args, "ma_ratebook", None),
        ma_crosswalk=getattr(args, "ma_crosswalk", None),
        ma_year=getattr(args, "ma_year", 2024),
        ma_bonus=getattr(args, "ma_bonus", "5%"),
        open_payments=getattr(args, "open_payments", None),
        part_d_drug=getattr(args, "part_d_drug", None),
        service=getattr(args, "service", None),
        summary=getattr(args, "summary", None),
        hospital=(getattr(args, "hospital", None) or None),
    )


def _noop(*_a, **_k):
    pass


def assemble(paths: DataPaths, *, allow_synthetic: bool = True,
             log: Callable = _noop) -> L.Ledger:
    """Run every detector (real where its path is given) into one Ledger.

    With ``allow_synthetic=False`` (production daily job), detectors lacking real
    inputs are skipped rather than demoed.
    """
    led = L.Ledger()

    # -- Medicare Advantage overpayment -------------------------------------
    from domains.flow.medicare_advantage import (
        MedicareAdvantageTwoCell, assemble_contracts_from_geovar, synthetic_contracts,
    )
    if paths.ma_geovar:
        from domains.flow.ingest import (
            load_ffs_geovar, load_ma_ratebook, load_ssa_fips_crosswalk,
            load_county_ma_enrollment,
        )
        log("assemble: MA overpayment (real)...")
        geo = load_ffs_geovar(paths.ma_geovar, year=paths.ma_year, geo_level="State")
        overrides: Dict[str, dict] = {}
        if paths.ma_ratebook:
            weights = None
            if paths.ma_crosswalk:
                xw = load_ssa_fips_crosswalk(paths.ma_crosswalk)
                enr = load_county_ma_enrollment(paths.ma_geovar, year=paths.ma_year)
                weights = {s: enr.get(f, 0) for s, f in xw.items()}
            for s, bm in load_ma_ratebook(paths.ma_ratebook, bonus=paths.ma_bonus,
                                          weights=weights).items():
                overrides.setdefault(s, {})["benchmark_per_capita"] = bm
        contracts = assemble_contracts_from_geovar(geo, overrides=overrides)
        led.extend(L.from_ma(MedicareAdvantageTwoCell().evaluate_all(contracts)))
    elif allow_synthetic:
        log("assemble: MA overpayment (synthetic)...")
        led.extend(L.from_ma(
            MedicareAdvantageTwoCell().evaluate_all(synthetic_contracts())))

    # -- Drug-level conflict of interest ------------------------------------
    from domains.flow.conflict import DrugLevelConflict, synthetic_drug_inputs
    if paths.open_payments and paths.part_d_drug:
        from domains.flow.ingest import load_open_payments_by_drug, load_part_d_by_drug
        log("assemble: drug-level conflict (real, slow)...")
        pay = load_open_payments_by_drug(paths.open_payments)
        rx = load_part_d_by_drug(paths.part_d_drug, keep_drugs={d for _n, d in pay})
        led.extend(L.from_drug_conflict(DrugLevelConflict().analyze(pay, rx)))
    elif allow_synthetic:
        log("assemble: drug-level conflict (synthetic)...")
        pay, rx = synthetic_drug_inputs()
        led.extend(L.from_drug_conflict(DrugLevelConflict(min_group=3).analyze(pay, rx)))

    # -- Billing conservation -----------------------------------------------
    if paths.service and paths.summary:
        from domains.flow.coherence import FlowCoherenceChecker
        from domains.flow.ingest import load_provider_service, load_provider_summary
        log("assemble: billing conservation (real)...")
        secs = [load_provider_service(paths.service), load_provider_summary(paths.summary)]
        led.extend(L.from_conservation(
            FlowCoherenceChecker(tolerance=0.02).check_all(secs)))

    # -- Hospital price coherence -------------------------------------------
    from domains.flow.hospital import HospitalPriceCoherence, synthetic_records
    if paths.hospital:
        from domains.flow.ingest import load_inpatient
        log("assemble: hospital price coherence (real)...")
        led.extend(L.from_hospital(
            HospitalPriceCoherence().analyze(load_inpatient(paths.hospital))))
    elif allow_synthetic:
        led.extend(L.from_hospital(
            HospitalPriceCoherence().analyze(synthetic_records())))

    # -- Outliers + Nash (synthetic demos only) -----------------------------
    if allow_synthetic:
        from domains.flow.outliers import YonedaOutlierEngine, synthetic_fingerprints
        fps, specs = synthetic_fingerprints()
        led.extend(L.from_outliers(
            YonedaOutlierEngine(min_peers=3, min_billed=50_000).analyze(fps, specs)))
        from domains.flow.nash_sheaf import NashSheaf, synthetic_observations
        led.extend(L.from_nash(NashSheaf().analyze(synthetic_observations())))

    return led


# ---------------------------------------------------------------------------
# Delta vs the previous run -- the "what changed" headline
# ---------------------------------------------------------------------------
@dataclass
class Delta:
    prior_date: Optional[str]
    total_current: float
    total_prior: float
    new: List[L.Finding] = field(default_factory=list)
    increased: List[tuple] = field(default_factory=list)   # (Finding, prior$, delta$)
    resolved: List[dict] = field(default_factory=list)      # prior findings gone

    @property
    def total_change(self) -> float:
        return self.total_current - self.total_prior


def _key(detector: str, entity: str) -> tuple:
    return (detector, entity)


def diff_ledgers(current: L.Ledger, prior_findings: Optional[List[dict]],
                 prior_date: Optional[str] = None, *, eps: float = 0.01) -> Delta:
    cur_total = sum(f.dollars for f in current.findings)
    if not prior_findings:
        return Delta(prior_date=None, total_current=cur_total, total_prior=0.0,
                     new=list(current.findings))
    prior = {_key(p["detector"], p["entity"]): p for p in prior_findings}
    prior_total = sum(p.get("dollars", 0.0) for p in prior_findings)
    new, increased = [], []
    seen = set()
    for f in current.findings:
        k = _key(f.detector, f.entity)
        seen.add(k)
        if k not in prior:
            new.append(f)
        else:
            pd = prior[k].get("dollars", 0.0)
            if f.dollars > pd * (1 + eps):
                increased.append((f, pd, f.dollars - pd))
    resolved = [p for k, p in prior.items() if k not in seen]
    new.sort(key=lambda f: -f.priority)
    increased.sort(key=lambda t: -t[2])
    return Delta(prior_date=prior_date, total_current=cur_total,
                 total_prior=prior_total, new=new, increased=increased,
                 resolved=resolved)


# ---------------------------------------------------------------------------
# Digest (markdown) -- the daily email / dashboard surface
# ---------------------------------------------------------------------------
def digest(ledger: L.Ledger, delta: Delta, date: str, top: int = 10) -> str:
    bd = ledger.by_detector()
    tiers = ledger.by_tier()
    total = sum(d["dollars"] for d in bd.values())
    md = []
    md.append(f"# The Leak Ledger — {date}")
    md.append("")
    chg = ""
    if delta.prior_date:
        sign = "+" if delta.total_change >= 0 else "-"
        chg = (f"  (Δ {sign}${abs(delta.total_change):,.0f} vs {delta.prior_date})")
    md.append(f"**{len(ledger.findings):,} findings · "
              f"${total:,.0f} at stake/associated**{chg}")
    md.append("")
    md.append("| tier | dollars |")
    md.append("|---|---|")
    for t in ("HIGH", "MEDIUM", "LOW"):
        md.append(f"| {t} | ${tiers.get(t, 0):,.0f} |")
    md.append("")
    md.append("## By detector")
    md.append("| detector | findings | dollars |")
    md.append("|---|---|---|")
    for det, d in sorted(bd.items(), key=lambda kv: -kv[1]["dollars"]):
        md.append(f"| {det} | {int(d['count']):,} | ${d['dollars']:,.0f} |")
    md.append("")
    md.append(f"## Top {top} by priority")
    md.append("| tier | detector | entity | dollars | basis |")
    md.append("|---|---|---|---|---|")
    for f in ledger.ranked()[:top]:
        md.append(f"| {f.tier} | {f.detector} | {f.entity} | "
                  f"${f.dollars:,.0f} | {f.basis} |")
    if delta.prior_date:
        md.append("")
        md.append(f"## What changed since {delta.prior_date}")
        md.append(f"- **New findings:** {len(delta.new):,}")
        md.append(f"- **Grown:** {len(delta.increased):,}")
        md.append(f"- **Resolved/dropped:** {len(delta.resolved):,}")
        if delta.new:
            md.append("")
            md.append(f"### 🆕 New (top {min(top, len(delta.new))})")
            for f in delta.new[:top]:
                md.append(f"- {f.detector} `{f.entity}` ${f.dollars:,.0f} — {f.basis}")
        if delta.increased:
            md.append("")
            md.append(f"### 📈 Biggest increases (top {min(top, len(delta.increased))})")
            for f, pd, dl in delta.increased[:top]:
                md.append(f"- {f.detector} `{f.entity}` +${dl:,.0f} "
                          f"(${pd:,.0f} → ${f.dollars:,.0f})")
    md.append("")
    md.append("---")
    md.append("_dollars = at stake/associated, not proven loss; confidence = "
              "review priority, not recovery probability. Findings are hypotheses "
              "for review._")
    return "\n".join(md)


# ---------------------------------------------------------------------------
# The daily job
# ---------------------------------------------------------------------------
def run_daily(paths: DataPaths, out_dir: str = "data/ledger", *,
              allow_synthetic: bool = True, date: Optional[str] = None,
              log: Callable = _noop) -> dict:
    """Assemble, diff vs the previous run, and write the dated artifact set.

    Writes (in ``out_dir``): leak_ledger_<date>.csv/.json, digest_<date>.md,
    latest.json/.csv/.md (pointers to the newest), and appends history.jsonl.
    Returns a small run-summary dict.
    """
    os.makedirs(out_dir, exist_ok=True)
    date = date or datetime.date.today().isoformat()

    led = assemble(paths, allow_synthetic=allow_synthetic, log=log)

    # Load the previous run (latest.json), if any and not from today.
    prior_findings = prior_date = None
    latest_json = os.path.join(out_dir, "latest.json")
    if os.path.exists(latest_json):
        try:
            with open(latest_json, encoding="utf-8") as fh:
                prev = json.load(fh)
            if prev.get("date") and prev["date"] != date:
                prior_findings = prev.get("findings")
                prior_date = prev.get("date")
        except Exception:
            pass

    delta = diff_ledgers(led, prior_findings, prior_date)
    md = digest(led, delta, date)

    csv_path = os.path.join(out_dir, f"leak_ledger_{date}.csv")
    json_path = os.path.join(out_dir, f"leak_ledger_{date}.json")
    md_path = os.path.join(out_dir, f"digest_{date}.md")
    led.to_csv(csv_path)
    led.to_json(json_path)
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(md)

    # latest.* pointers (latest.json embeds the findings for next run's diff).
    from dataclasses import asdict
    with open(latest_json, "w", encoding="utf-8") as fh:
        json.dump({"date": date,
                   "findings": [asdict(f) for f in led.ranked()]}, fh, indent=2)
    led.to_csv(os.path.join(out_dir, "latest.csv"))
    with open(os.path.join(out_dir, "latest.md"), "w", encoding="utf-8") as fh:
        fh.write(md)

    total = sum(f.dollars for f in led.findings)
    record = {"date": date, "findings": len(led.findings), "total": total,
              "prior_date": delta.prior_date,
              "new": len(delta.new), "increased": len(delta.increased),
              "resolved": len(delta.resolved), "total_change": delta.total_change}
    with open(os.path.join(out_dir, "history.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    return record
