# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Hospital price coherence -- "same DRG, different price".

A DRG (diagnosis-related group) is supposed to be one priced unit of inpatient
care. So for a given DRG, the price section *over hospitals* should roughly glue:
similar care, similar price, once you control for region (wage index). Where it
does NOT glue -- where one hospital is paid far above its same-state peers for
the identical DRG, or charges a wildly higher sticker price -- that dispersion is
the obstruction, and it localizes to specific hospitals.

Two views:
  * **Chargemaster dispersion** (public-resonant): for each DRG, how far apart
    are hospitals' submitted charges (the "$50k here, $200k there" story).
    Charges are sticker prices, not what Medicare pays -- flagged as such.
  * **Payment excess** (leak-relevant, the ledger contribution): a hospital paid
    above its same-state peer median for the same DRG. Excess = (payment - peer
    median) x discharges. Honest caveat: case complexity within a DRG, teaching/
    DSH add-ons, and wage index explain some of it -- it is an anomaly to review.

Keyed by CCN, this starts the hospital (CCN) spine.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class DRGDispersion:
    drg: str
    drg_desc: str
    n_hospitals: int
    median_charge: float
    median_payment: float
    charge_p90_p10: float        # 90th/10th percentile charge ratio (dispersion)


@dataclass
class HospitalOutlier:
    ccn: str
    name: str
    state: str
    drg: str
    drg_desc: str
    payment: float
    peer_median: float
    ratio: float                 # payment / same-state peer median
    discharges: float
    excess: float                # (payment - peer_median) * discharges


@dataclass
class HospitalPriceReport:
    n_records: int
    n_hospitals: int
    n_drgs: int
    total_excess: float
    dispersed_drgs: List[DRGDispersion] = field(default_factory=list)
    outliers: List[HospitalOutlier] = field(default_factory=list)


def _p90_p10(values: List[float]) -> float:
    vs = sorted(v for v in values if v > 0)
    if len(vs) < 10:
        return (vs[-1] / vs[0]) if vs and vs[0] > 0 else 1.0
    q = statistics.quantiles(vs, n=10)        # 9 cut points (deciles)
    return q[8] / q[0] if q[0] > 0 else 1.0


class HospitalPriceCoherence:
    """'Same DRG, different price' detector over the Medicare Inpatient PUF."""

    def __init__(self, category=None, *,
                 ratio_threshold: float = 1.5,   # payment vs peer median
                 min_discharges: float = 11,
                 min_peers: int = 5,
                 max_writes: int = 500) -> None:
        self.category = category
        self.ratio_threshold = ratio_threshold
        self.min_discharges = min_discharges
        self.min_peers = min_peers
        self.max_writes = max_writes

    def analyze(self, records: List[dict]) -> HospitalPriceReport:
        by_drg = defaultdict(list)               # drg -> [record]
        by_drg_state = defaultdict(list)         # (drg, state) -> [payment]
        hospitals = set()
        for r in records:
            by_drg[r["drg"]].append(r)
            by_drg_state[(r["drg"], r["state"])].append(r["total_pymt"])
            hospitals.add(r["ccn"])

        # Per-DRG (national) chargemaster dispersion.
        dispersed: List[DRGDispersion] = []
        for drg, rs in by_drg.items():
            if len(rs) < self.min_peers:
                continue
            charges = [r["charge"] for r in rs]
            pays = [r["total_pymt"] for r in rs]
            dispersed.append(DRGDispersion(
                drg=drg, drg_desc=rs[0]["drg_desc"], n_hospitals=len(rs),
                median_charge=statistics.median(charges),
                median_payment=statistics.median(pays),
                charge_p90_p10=_p90_p10(charges),
            ))
        dispersed.sort(key=lambda d: -d.charge_p90_p10)

        # Same-state peer-median payment -> outliers + excess.
        peer_median = {k: statistics.median(v)
                       for k, v in by_drg_state.items() if len(v) >= self.min_peers}
        outliers: List[HospitalOutlier] = []
        total_excess = 0.0
        for r in records:
            med = peer_median.get((r["drg"], r["state"]))
            if med is None or med <= 0:
                continue
            if r["discharges"] < self.min_discharges:
                continue
            ratio = r["total_pymt"] / med
            if ratio < self.ratio_threshold:
                continue
            excess = (r["total_pymt"] - med) * r["discharges"]
            if excess <= 0:
                continue
            total_excess += excess
            outliers.append(HospitalOutlier(
                ccn=r["ccn"], name=r["name"], state=r["state"], drg=r["drg"],
                drg_desc=r["drg_desc"], payment=r["total_pymt"], peer_median=med,
                ratio=ratio, discharges=r["discharges"], excess=excess))
        outliers.sort(key=lambda o: -o.excess)

        report = HospitalPriceReport(
            n_records=len(records), n_hospitals=len(hospitals),
            n_drgs=len(by_drg), total_excess=total_excess,
            dispersed_drgs=dispersed, outliers=outliers)
        if self.category is not None:
            for o in outliers[:self.max_writes]:
                self._to_category(o)
        return report

    def _to_category(self, o: HospitalOutlier) -> None:
        cat = self.category
        h = f"ccn:{o.ccn}"
        d = f"drg:{o.drg}"
        if cat.get(h) is None:
            cat.add(h, type_name="hospital")
        if cat.get(d) is None:
            cat.add(d, type_name="drg")
        cat.connect(h, d, name=f"overpriced_for::{o.ccn}::{o.drg}",
                    confidence=round(min(1.0, o.ratio / 5.0), 4),
                    payment=round(o.payment, 2), peer_median=round(o.peer_median, 2),
                    excess=round(o.excess, 2), discharges=o.discharges)


def summarize(report: HospitalPriceReport, top: int = 15) -> str:
    lines = []
    lines.append("Hospital price coherence -- 'same DRG, different price'")
    lines.append("=" * 76)
    lines.append(f"  {report.n_records:,} (hospital, DRG) records   "
                 f"{report.n_hospitals:,} hospitals   {report.n_drgs:,} DRGs")
    lines.append(f"  total payment ABOVE same-state peer median for the same DRG: "
                 f"${report.total_excess:,.0f}")
    lines.append("")
    lines.append("  most price-dispersed DRGs (chargemaster p90/p10, sticker price):")
    for d in report.dispersed_drgs[:top]:
        lines.append(
            f"    DRG {d.drg} {d.drg_desc[:40]:<40} {d.charge_p90_p10:>6.1f}x  "
            f"median charge ${d.median_charge:>11,.0f}  pay ${d.median_payment:>9,.0f}")
    lines.append("")
    lines.append("  top hospitals paid above same-state peers for the same DRG:")
    for o in report.outliers[:top]:
        lines.append(
            f"    {o.name[:26]:<26} ({o.state}) DRG {o.drg}  "
            f"${o.payment:>10,.0f} vs peer ${o.peer_median:>9,.0f} "
            f"({o.ratio:.1f}x, n={int(o.discharges)})  excess ${o.excess:>13,.0f}")
    lines.append("-" * 76)
    lines.append("  charges are sticker prices, not what Medicare pays. Payment "
                 "excess is an\n  anomaly to review: case complexity, teaching/DSH "
                 "add-ons, and wage index\n  explain some of it. Association, not "
                 "proven waste.")
    return "\n".join(lines)


def synthetic_records() -> List[dict]:
    """Hospitals x DRGs with one planted overpriced hospital and a wide charge
    spread for one DRG."""
    recs = []
    # DRG 470 (joint replacement) in TX: 6 peers ~ $15k payment, one at $40k.
    base = [14000, 15000, 16000, 15500, 14500, 15200]
    for i, p in enumerate(base):
        recs.append(dict(ccn=f"45000{i}", name=f"TX Hosp {i}", state="TX",
                         drg="470", drg_desc="MAJOR JOINT REPLACEMENT",
                         discharges=100, charge=p * 4, total_pymt=p, mdcr_pymt=p * 0.9))
    recs.append(dict(ccn="450099", name="TX Pricey Joint", state="TX",
                     drg="470", drg_desc="MAJOR JOINT REPLACEMENT",
                     discharges=200, charge=300000, total_pymt=40000, mdcr_pymt=36000))
    # DRG 247 (stent) in CA: similar payments, wildly different charges.
    for i, chg in enumerate([60000, 120000, 250000, 90000, 400000, 75000]):
        recs.append(dict(ccn=f"05000{i}", name=f"CA Hosp {i}", state="CA",
                         drg="247", drg_desc="PERC CARDIOVASC PROC W DRUG-ELUTING STENT",
                         discharges=80, charge=chg, total_pymt=20000, mdcr_pymt=18000))
    return recs
