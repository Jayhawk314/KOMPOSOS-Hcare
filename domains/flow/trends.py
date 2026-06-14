# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""The time dimension -- turn snapshots into trends.

A single year tells you the size of a leak; a series tells you whether it is
growing, and how fast. This module runs a detector across years and reports the
trend (level, year-over-year change, CAGR, direction, acceleration), and flags
the entities whose leak is growing fastest. That is what makes the ledger a
*daily/yearly* product rather than a one-off snapshot.

v1 wires the Medicare Advantage overpayment trend, because the FFS Geographic
Variation PUF already carries 2014-2024 in one file -- the real consumed side
(FFS per-capita x MA enrollment) varies per year; the paid-side benchmark
multiplier is held at the documented MedPAC ratio across years (a consistent
modeled assumption, stated). The same engine generalizes to any per-year metric
(billing, drug-conflict, hospital prices) as those years are ingested.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Trend:
    entity: str
    years: List[int]
    values: List[float]

    @property
    def first(self) -> float:
        return self.values[0] if self.values else 0.0

    @property
    def latest(self) -> float:
        return self.values[-1] if self.values else 0.0

    @property
    def span(self) -> int:
        return (self.years[-1] - self.years[0]) if len(self.years) > 1 else 0

    @property
    def cagr(self) -> float:
        """Compound annual growth rate over the series."""
        if self.span <= 0 or self.first <= 0:
            return 0.0
        return (self.latest / self.first) ** (1.0 / self.span) - 1.0

    @property
    def yoy_latest(self) -> float:
        if len(self.values) < 2 or self.values[-2] <= 0:
            return 0.0
        return self.values[-1] / self.values[-2] - 1.0

    @property
    def direction(self) -> str:
        c = self.cagr
        if c > 0.02:
            return "GROWING"
        if c < -0.02:
            return "SHRINKING"
        return "FLAT"

    @property
    def accelerating(self) -> bool:
        """Latest year-over-year growth exceeds the long-run CAGR."""
        return self.yoy_latest > self.cagr > 0


def compute_trend(entity: str, year_value: Dict[int, float]) -> Trend:
    years = sorted(year_value)
    return Trend(entity=entity, years=years, values=[year_value[y] for y in years])


# ---------------------------------------------------------------------------
# Medicare Advantage overpayment trend (real consumed side, 2014-2024)
# ---------------------------------------------------------------------------
@dataclass
class MATrendReport:
    years: List[int]
    national_overpayment: Trend
    national_enrollment: Trend
    national_consumed: Trend
    state_trends: Dict[str, Trend] = field(default_factory=dict)
    fastest_growing: List[Trend] = field(default_factory=list)


class MATrendEngine:
    """Compute the MA overpayment series across years from the GeoVar PUF."""

    def __init__(self, *, benchmark_ratio: float = 1.08,
                 ma_risk: float = 1.20, min_overpay: float = 5e8) -> None:
        self.benchmark_ratio = benchmark_ratio
        self.ma_risk = ma_risk
        self.min_overpay = min_overpay   # floor for "fastest growing" eligibility

    def analyze(self, geovar_path: str, years: List[int]) -> MATrendReport:
        from domains.flow.ingest import load_ffs_geovar
        from domains.flow.medicare_advantage import (
            assemble_contracts_from_geovar, MedicareAdvantageTwoCell,
        )
        engine = MedicareAdvantageTwoCell()
        nat_over: Dict[int, float] = {}
        nat_enr: Dict[int, float] = {}
        nat_cons: Dict[int, float] = {}
        per_state: Dict[str, Dict[int, float]] = {}
        present: List[int] = []
        for y in years:
            geo = load_ffs_geovar(geovar_path, year=y, geo_level="State")
            if not geo:
                continue
            present.append(y)
            contracts = assemble_contracts_from_geovar(
                geo, benchmark_ratio=self.benchmark_ratio, ma_risk_score=self.ma_risk)
            results = engine.evaluate_all(contracts)
            nat_over[y] = sum(r.overpayment for r in results)
            nat_enr[y] = sum(r.enrollment for r in results)
            nat_cons[y] = sum(r.consumed for r in results)
            for r in results:
                per_state.setdefault(r.contract_id, {})[y] = r.overpayment

        state_trends = {s: compute_trend(s, yv) for s, yv in per_state.items()
                        if len(yv) >= 2}
        fastest = sorted(
            (t for t in state_trends.values() if t.latest >= self.min_overpay),
            key=lambda t: -t.cagr)
        return MATrendReport(
            years=present,
            national_overpayment=compute_trend("national", nat_over),
            national_enrollment=compute_trend("national", nat_enr),
            national_consumed=compute_trend("national", nat_cons),
            state_trends=state_trends, fastest_growing=fastest,
        )


def summarize(report: MATrendReport, top: int = 12) -> str:
    lines = []
    lines.append("Medicare Advantage overpayment -- the time dimension")
    lines.append("=" * 74)
    no = report.national_overpayment
    ne = report.national_enrollment
    lines.append(f"  years: {report.years[0]}-{report.years[-1]}")
    lines.append("")
    lines.append("  national MA overpayment by year (real FFS consumed side):")
    for y, v in zip(no.years, no.values):
        bar = "#" * int(40 * v / max(no.values)) if max(no.values) else ""
        lines.append(f"    {y}  ${v:>16,.0f}  {bar}")
    lines.append("")
    lines.append(f"  overpayment: ${no.first:,.0f} -> ${no.latest:,.0f}   "
                 f"CAGR {no.cagr:+.1%}   {no.direction}"
                 f"{'  (ACCELERATING)' if no.accelerating else ''}")
    lines.append(f"  MA enrollment: {ne.first:,.0f} -> {ne.latest:,.0f}   "
                 f"CAGR {ne.cagr:+.1%}")
    lines.append("")
    lines.append(f"  fastest-growing state overpayments (CAGR, latest >= "
                 f"${report.fastest_growing and 5e8 or 0:,.0f}):"
                 if report.fastest_growing else "  (no states above floor)")
    for t in report.fastest_growing[:top]:
        lines.append(f"    {t.entity:<4} {t.cagr:+6.1%}/yr   "
                     f"${t.first:>14,.0f} -> ${t.latest:>14,.0f}"
                     f"{'  ACCEL' if t.accelerating else ''}")
    lines.append("-" * 74)
    lines.append("  consumed side (FFS per-capita x MA enrollment) is real per "
                 "year; the paid-side\n  benchmark multiplier is held at the "
                 "MedPAC ratio across years (stated assumption).")
    return "\n".join(lines)
