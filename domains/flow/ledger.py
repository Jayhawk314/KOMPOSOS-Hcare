# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""The unified leak ledger — assemble every detector into one ranked output.

Each detector finds a different shape of problem and reports in its own units.
The ledger normalizes them into a single :class:`Finding` schema, attaches a
**confidence** (how likely this is real waste vs an explained artifact /
association), ranks by a review-priority score (dollars x confidence), totals by
detector and by confidence tier, and writes a CSV/JSON artifact. This is the
"yesterday's leak, every morning" product surface.

Honesty is structural, not decorative:
  * ``dollars`` is the amount *at stake / associated* with the finding, not a
    proven loss.
  * ``confidence`` is a review-priority weight in [0,1], NOT a probability of
    recovery. A one-directional data artifact (the billing-suppression gap) gets
    a deliberately low confidence so it sinks to the bottom; the MedPAC-validated
    MA estimate gets a high one.
  * priority = dollars x confidence is for *ordering* the work queue, nothing
    more.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List


# Per-detector base confidence (documented review-priority weights, not
# probabilities). Tuned to how defensible each signal is today.
CONF = {
    "ma_overpayment": 0.70,      # validated to 1.12x MedPAC; modeled MA risk
    "drug_conflict": 0.55,       # drug-controlled association
    "npi_conflict": 0.40,        # association, not drug-controlled
    "outlier": 0.45,             # peer-relative, review
    "nash_gaming": 0.50,         # novel strategic signal
    "hospital_price": 0.45,      # paid above same-state peer; case-mix caveat
    "billing_conservation": 0.12,  # 2024 gap is a one-directional data artifact
}


def tier(confidence: float) -> str:
    if confidence >= 0.65:
        return "HIGH"
    if confidence >= 0.40:
        return "MEDIUM"
    return "LOW"


@dataclass
class Finding:
    detector: str
    entity: str                  # the actor/unit (state:CA, drug:FARXIGA, npi:..)
    category: str                # human label of the problem
    dollars: float               # amount at stake / associated
    confidence: float            # review-priority weight in [0,1]
    basis: str = ""              # one-line why
    caveat: str = ""             # the honest limitation

    @property
    def priority(self) -> float:
        return self.dollars * self.confidence

    @property
    def tier(self) -> str:
        return tier(self.confidence)


class Ledger:
    """Collects findings from all detectors and emits the ranked ledger."""

    def __init__(self) -> None:
        self.findings: List[Finding] = []

    def add(self, f: Finding) -> None:
        self.findings.append(f)

    def extend(self, fs) -> None:
        self.findings.extend(fs)

    def ranked(self) -> List[Finding]:
        return sorted(self.findings, key=lambda f: -f.priority)

    def by_detector(self) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        for f in self.findings:
            d = out.setdefault(f.detector, {"count": 0, "dollars": 0.0})
            d["count"] += 1
            d["dollars"] += f.dollars
        return out

    def by_tier(self) -> Dict[str, float]:
        out: Dict[str, float] = {"HIGH": 0.0, "MEDIUM": 0.0, "LOW": 0.0}
        for f in self.findings:
            out[f.tier] += f.dollars
        return out

    def to_csv(self, path: str) -> None:
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["detector", "entity", "category", "dollars",
                        "confidence", "tier", "priority", "basis", "caveat"])
            for f in self.ranked():
                w.writerow([f.detector, f.entity, f.category, round(f.dollars, 2),
                            f.confidence, f.tier, round(f.priority, 2),
                            f.basis, f.caveat])

    def to_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump([asdict(f) for f in self.ranked()], fh, indent=2)


# ---------------------------------------------------------------------------
# Adapters: detector results -> Findings
# ---------------------------------------------------------------------------
def from_ma(results) -> List[Finding]:
    """Medicare Advantage per-state overpayments."""
    out = []
    for r in results:
        if r.overpayment <= 0:
            continue
        out.append(Finding(
            detector="ma_overpayment", entity=f"state:{r.contract_id}",
            category="MA paid above FFS-equivalent",
            dollars=r.overpayment, confidence=CONF["ma_overpayment"],
            basis=f"{r.ratio:.0%} of paid; coding+benchmark split",
            caveat="economic estimate; MA risk score modeled",
        ))
    return out


def from_drug_conflict(report) -> List[Finding]:
    """Per-drug excess prescribing associated with industry payments."""
    out = []
    for l in report.lifts:
        if l.lift <= 1.0:
            continue
        excess = (l.mean_paid - l.mean_unpaid) * l.n_paid   # $ above unpaid baseline
        if excess <= 0:
            continue
        out.append(Finding(
            detector="drug_conflict", entity=f"drug:{l.drug}",
            category="prescribing excess of a paid-about drug",
            dollars=excess, confidence=CONF["drug_conflict"],
            basis=f"lift {l.lift:.2f}x ({l.n_paid:,} paid prescribers)",
            caveat="association, not causation; drug-controlled",
        ))
    return out


def from_conservation(pair_results) -> List[Finding]:
    """Billing line-items vs aggregate. 2024 = one-directional data artifact:
    one low-confidence rolled-up finding, deliberately ranked to the bottom."""
    out = []
    for r in pair_results:
        contra = r.contradictions()
        if not contra:
            continue
        gap = sum(abs(v.value_a - v.value_b) for v in contra)
        a_exceeds = sum(1 for v in contra if v.value_a > v.value_b and v.value_b > 0)
        b_exceeds = sum(1 for v in contra if v.value_b > v.value_a and v.value_a > 0)
        one_dir = (a_exceeds == 0) or (b_exceeds == 0)
        out.append(Finding(
            detector="billing_conservation",
            entity=f"{r.source_a}~{r.source_b}",
            category="billing line-items vs aggregate gap",
            dollars=gap,
            confidence=0.05 if one_dir else CONF["billing_conservation"],
            basis=f"{len(contra):,} contradictions",
            caveat=("one-directional -> small-cell suppression artifact, not waste"
                    if one_dir else "two-sided residual; investigate"),
        ))
    return out


def from_hospital(report) -> List[Finding]:
    """Hospitals paid above same-state peers for the same DRG (excess dollars)."""
    out = []
    for o in report.outliers:
        out.append(Finding(
            detector="hospital_price", entity=f"ccn:{o.ccn}|drg:{o.drg}",
            category="paid above same-state peers for the same DRG",
            dollars=o.excess, confidence=CONF["hospital_price"],
            basis=f"{o.ratio:.1f}x peer median, {int(o.discharges)} discharges "
                  f"({o.name[:24]}, {o.state})",
            caveat="case-mix/teaching/DSH/wage-index may explain; review",
        ))
    return out


def from_outliers(results) -> List[Finding]:
    """Yoneda peer-outlier providers (billing mix unlike peers). dollars = the
    provider's total billing now under review (not the waste amount)."""
    out = []
    for r in results:
        if not getattr(r, "is_outlier", False):
            continue
        out.append(Finding(
            detector="outlier", entity=f"npi:{r.npi}",
            category="billing mix unlike specialty peers",
            dollars=getattr(r, "total_billed", 0.0) or 0.0,
            confidence=CONF["outlier"],
            basis=f"Yoneda distance {getattr(r, 'distance', 0.0):.2f} "
                  f"({getattr(r, 'specialty', '')})",
            caveat="billing under review, not the waste amount; peer-relative",
        ))
    return out


def from_nash(results) -> List[Finding]:
    """Nash-sheaf flagged plans (incentive-aligned cross-market gaming).
    No dollar model yet -> dollars 0 (counts as a review flag, not a $ at stake)."""
    out = []
    for r in results:
        if not getattr(r, "strategic", False):
            continue
        out.append(Finding(
            detector="nash_gaming", entity=f"plan:{r.plan_id}",
            category="incentive-aligned cross-market coding swings",
            dollars=0.0, confidence=CONF["nash_gaming"],
            basis=f"gaming {getattr(r, 'gaming_score', 0.0):.2f}, aligned; "
                  f"{getattr(r, 'enrollment', 0):,} enrollees",
            caveat="strategic-gaming flag; no dollar model yet",
        ))
    return out


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def summarize(ledger: Ledger, top: int = 20) -> str:
    lines = []
    lines.append("THE LEAK LEDGER -- unified findings across all detectors")
    lines.append("=" * 78)
    bd = ledger.by_detector()
    total = sum(d["dollars"] for d in bd.values())
    lines.append(f"  {len(ledger.findings):,} findings   "
                 f"${total:,.0f} total dollars at stake/associated")
    lines.append("")
    lines.append("  by detector:")
    for det, d in sorted(bd.items(), key=lambda kv: -kv[1]["dollars"]):
        lines.append(f"    {det:<22} {int(d['count']):>7,} findings   "
                     f"${d['dollars']:>16,.0f}   (conf {CONF.get(det, 0):.2f})")
    lines.append("")
    lines.append("  dollars by confidence tier (review priority):")
    for t, v in ledger.by_tier().items():
        lines.append(f"    {t:<8} ${v:,.0f}")
    lines.append("")
    lines.append(f"  top {top} findings by priority (dollars x confidence):")
    for f in ledger.ranked()[:top]:
        lines.append(
            f"    [{f.tier:<6}] {f.detector:<18} {f.entity:<26} "
            f"${f.dollars:>14,.0f}  {f.basis}")
    lines.append("-" * 78)
    lines.append("  confidence = review-priority weight, NOT probability of "
                 "recovery.\n  dollars = at stake / associated, NOT proven loss. "
                 "Every line is a hypothesis\n  for review; the MA total is "
                 "validated to ~1.12x MedPAC, the billing-gap line\n  is a known "
                 "data artifact ranked to the bottom by design.")
    return "\n".join(lines)
