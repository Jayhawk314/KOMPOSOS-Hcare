# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Open Payments x Part D conflict-of-interest 2-cell.

Two parallel evidence pathways reach the same provider:

    payment:     pharma  ==(Open Payments $)==>  provider
    prescribing: provider ==(Part D drug $)====>  drugs

Composed, money and influence run pharma -> provider -> drugs. The
conflict-of-interest signal is the **alignment** of the two pathways: a provider
who both receives large industry payments AND prescribes at the high end is a
conflict candidate. As parallel 1-morphisms ``provider -> influence`` (the
payment-evidence morphism and the prescribing-evidence morphism), the
``InfinityCosmos`` materializes a **2-cell** per flagged provider (COG Tier 4) --
the same construction as the Medicare Advantage paid-vs-consumed 2-cell.

This is the NPI-level detector (v1): payment magnitude vs prescribing magnitude
per provider. It runs on the NPI spine (``spine.py``), which already joins
billing + Part D; Open Payments is the third real source on that spine. A
drug-level refinement (match a payment's manufacturer to the specific drugs it
makes, then to that provider's prescribing of those drugs) is a documented
next step.

Honest note: association is not causation. A flag means "industry payment and
high prescribing co-occur for this provider" -- a hypothesis for review, exactly
like every other flow finding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional


@dataclass
class ConflictResult:
    npi: str
    payment: float
    prescribing: float
    payment_pct: float          # percentile rank in [0,1] among providers
    prescribing_pct: float
    score: float                # geometric mean of the two percentiles
    specialty: str = ""


@dataclass
class ConflictReport:
    n_providers: int            # providers present in BOTH sources
    correlation: float          # Spearman rank corr(payment, prescribing)
    flagged: List[ConflictResult] = field(default_factory=list)
    total_payment: float = 0.0
    total_prescribing: float = 0.0


# ---------------------------------------------------------------------------
# Small stdlib stats (no numpy/scipy dependency)
# ---------------------------------------------------------------------------
def _average_ranks(values: List[float]) -> List[float]:
    """Ranks with ties averaged (1-based)."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0          # average of 1-based ranks i+1..j+1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson(xs: List[float], ys: List[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return 0.0
    return sxy / (sxx ** 0.5 * syy ** 0.5)


def _spearman(xs: List[float], ys: List[float]) -> float:
    return _pearson(_average_ranks(xs), _average_ranks(ys))


def _percentiles(values: List[float]) -> List[float]:
    """Fraction of entries <= each value (in [0,1])."""
    n = len(values)
    if n <= 1:
        return [1.0] * n
    ranks = _average_ranks(values)
    return [(r - 0.5) / n for r in ranks]


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------
class ConflictDetector:
    """Open Payments x Part D conflict-of-interest detector + 2-cell writer."""

    def __init__(self, category=None, cosmos=None, *,
                 flag_pct: float = 0.90,
                 min_payment: float = 1_000.0,
                 min_prescribing: float = 10_000.0,
                 max_writes: int = 500) -> None:
        self.category = category
        self.cosmos = cosmos
        self.flag_pct = flag_pct
        self.min_payment = min_payment
        self.min_prescribing = min_prescribing
        # Cap Category writes (the backend commits per insert): persist only the
        # highest-score flagged providers. The report still counts them all.
        self.max_writes = max_writes

    def analyze(self, payments: Mapping[str, float],
                prescribing: Mapping[str, float],
                specialty: Optional[Mapping[str, str]] = None) -> ConflictReport:
        specialty = specialty or {}
        common = sorted(set(payments) & set(prescribing))
        if not common:
            return ConflictReport(0, 0.0)

        pay = [float(payments[n]) for n in common]
        rx = [float(prescribing[n]) for n in common]
        corr = _spearman(pay, rx)
        pay_pct = _percentiles(pay)
        rx_pct = _percentiles(rx)

        flagged: List[ConflictResult] = []
        for n, p, r, pp, rp in zip(common, pay, rx, pay_pct, rx_pct):
            if (pp >= self.flag_pct and rp >= self.flag_pct
                    and p >= self.min_payment and r >= self.min_prescribing):
                res = ConflictResult(
                    npi=n, payment=p, prescribing=r,
                    payment_pct=pp, prescribing_pct=rp,
                    score=(pp * rp) ** 0.5,
                    specialty=specialty.get(n, ""),
                )
                flagged.append(res)
        flagged.sort(key=lambda x: -x.score)

        report = ConflictReport(
            n_providers=len(common), correlation=corr, flagged=flagged,
            total_payment=sum(pay), total_prescribing=sum(rx),
        )
        if self.category is not None:
            for res in flagged[:self.max_writes]:
                self._to_category(res)
        return report

    def _to_category(self, r: ConflictResult) -> None:
        cat = self.category
        prov = f"npi:{r.npi}"
        infl = f"influence:{r.npi}"
        cat.add("pharma", type_name="industry")
        if cat.get(prov) is None:
            cat.add(prov, type_name="provider")
        cat.add(infl, type_name="influence")

        # pharma -> provider (the payment fact).
        cat.connect("pharma", prov, name="pays",
                    confidence=round(r.payment_pct, 4), amount=round(r.payment, 2))
        # Parallel evidence morphisms provider -> influence; names contract-unique
        # so the cosmos materializes a distinct 2-cell per provider.
        pay_mor = cat.connect(prov, infl, name=f"payment_evidence::{r.npi}",
                              confidence=round(r.payment_pct, 4),
                              kind="payment", amount=round(r.payment, 2))
        rx_mor = cat.connect(prov, infl, name=f"prescribing_evidence::{r.npi}",
                             confidence=round(r.prescribing_pct, 4),
                             kind="prescribing", amount=round(r.prescribing, 2))
        # Summary conflict edge.
        cat.add("pharma_influence", type_name="risk")
        cat.connect(prov, "pharma_influence", name="conflict_risk",
                    confidence=round(r.score, 4),
                    payment=round(r.payment, 2), prescribing=round(r.prescribing, 2))

        if self.cosmos is not None:
            try:
                self.cosmos.add_two_cell(
                    f"conflict::{r.npi}", pay_mor.id, rx_mor.id,
                    data={"score": r.score, "payment": r.payment,
                          "prescribing": r.prescribing})
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def summarize(report: ConflictReport, top: int = 15) -> str:
    lines = []
    lines.append("Open Payments x Part D conflict-of-interest 2-cell")
    lines.append("=" * 72)
    lines.append(f"  providers in BOTH sources: {report.n_providers:,}")
    lines.append(f"  total pharma payments:     ${report.total_payment:,.0f}")
    lines.append(f"  total Part D prescribing:  ${report.total_prescribing:,.0f}")
    lines.append(f"  payment<->prescribing rank correlation (Spearman): "
                 f"{report.correlation:+.3f}")
    lines.append(f"  flagged (top decile of BOTH): {len(report.flagged):,}")
    lines.append("")
    for r in report.flagged[:top]:
        tag = f"{r.npi}" + (f" [{r.specialty}]" if r.specialty else "")
        lines.append(
            f"  {tag:<34} pharma ${r.payment:>12,.0f}  "
            f"Rx ${r.prescribing:>14,.0f}  score {r.score:.2f}")
    lines.append("-" * 72)
    lines.append("  association, not causation: each flag is a hypothesis for "
                 "review.\n  positive correlation = paid providers tend to "
                 "prescribe more.")
    return "\n".join(lines)


@dataclass
class DrugLift:
    drug: str
    lift: float                 # mean prescribing (paid) / mean prescribing (unpaid)
    n_paid: int
    n_unpaid: int
    mean_paid: float
    mean_unpaid: float
    total_rx: float
    total_pay: float


@dataclass
class DrugConflictResult:
    npi: str
    drug: str
    payment: float
    prescribing: float
    drug_lift: float            # the lift for this pair's drug


@dataclass
class DrugConflictReport:
    n_matched_pairs: int        # (npi, drug) present in BOTH sources
    n_drugs: int                # drugs with enough paid & unpaid prescribers
    correlation: float          # Spearman over matched pairs
    median_lift: float
    weighted_lift: float        # prescribing-weighted mean lift
    top_drugs: List[DrugLift] = field(default_factory=list)
    lifts: List[DrugLift] = field(default_factory=list)   # all qualifying drugs
    flagged: List[DrugConflictResult] = field(default_factory=list)


class DrugLevelConflict:
    """Drug-level conflict: does a payment ABOUT a drug track prescribing OF it?

    Sharper than the NPI-level detector: it matches a payment's specific drug to
    that provider's prescribing of the *same* drug, and compares — per drug —
    providers paid about it against unpaid prescribers of it (the **lift**).
    A lift > 1 means paid providers prescribe that drug more. Categorically, for
    a (provider, drug) pair the *payment* and *prescribing* morphisms are
    parallel `provider → drug:<d>` (same source AND target), so the cosmos
    materializes a genuine 2-cell per flagged pair.
    """

    def __init__(self, category=None, cosmos=None, *,
                 min_group: int = 5, min_payment: float = 100.0,
                 min_prescribing: float = 10_000.0, max_writes: int = 500) -> None:
        self.category = category
        self.cosmos = cosmos
        self.min_group = min_group
        self.min_payment = min_payment
        self.min_prescribing = min_prescribing
        self.max_writes = max_writes

    def analyze(self, payments_by_drug: Mapping[tuple, float],
                prescribing_by_drug: Mapping[tuple, float]) -> DrugConflictReport:
        import statistics
        from collections import defaultdict

        rx_by_drug = defaultdict(dict)        # drug -> {npi: prescribing $}
        for (npi, drug), cost in prescribing_by_drug.items():
            rx_by_drug[drug][npi] = cost
        paid_by_drug = defaultdict(set)       # drug -> {npi paid about it}
        pay_for_drug = defaultdict(float)
        for (npi, drug), amt in payments_by_drug.items():
            paid_by_drug[drug].add(npi)
            pay_for_drug[drug] += amt

        lifts: List[DrugLift] = []
        for drug, rx in rx_by_drug.items():
            paid = paid_by_drug.get(drug, set())
            paid_vals = [c for n, c in rx.items() if n in paid]
            unpaid_vals = [c for n, c in rx.items() if n not in paid]
            if len(paid_vals) < self.min_group or len(unpaid_vals) < self.min_group:
                continue
            mp = statistics.fmean(paid_vals)
            mu = statistics.fmean(unpaid_vals)
            if mu <= 0:
                continue
            lifts.append(DrugLift(drug, mp / mu, len(paid_vals), len(unpaid_vals),
                                  mp, mu, sum(rx.values()), pay_for_drug.get(drug, 0.0)))

        matched = [k for k in payments_by_drug if k in prescribing_by_drug]
        if matched:
            corr = _spearman([payments_by_drug[k] for k in matched],
                             [prescribing_by_drug[k] for k in matched])
        else:
            corr = 0.0

        median_lift = statistics.median([l.lift for l in lifts]) if lifts else 0.0
        tot_w = sum(l.total_rx for l in lifts)
        weighted_lift = (sum(l.lift * l.total_rx for l in lifts) / tot_w) if tot_w else 0.0

        flagged = [
            DrugConflictResult(npi, drug, payments_by_drug[(npi, drug)],
                               prescribing_by_drug[(npi, drug)],
                               next((l.lift for l in lifts if l.drug == drug), 0.0))
            for (npi, drug) in matched
            if payments_by_drug[(npi, drug)] >= self.min_payment
            and prescribing_by_drug[(npi, drug)] >= self.min_prescribing
        ]
        flagged.sort(key=lambda r: -r.prescribing)

        report = DrugConflictReport(
            n_matched_pairs=len(matched),
            n_drugs=len(lifts), correlation=corr,
            median_lift=median_lift, weighted_lift=weighted_lift,
            top_drugs=sorted(lifts, key=lambda l: -l.total_pay)[:25],
            lifts=lifts,
            flagged=flagged,
        )
        if self.category is not None:
            for r in flagged[:self.max_writes]:
                self._to_category(r)
        return report

    def _to_category(self, r: DrugConflictResult) -> None:
        cat = self.category
        prov = f"npi:{r.npi}"
        drug = f"drug:{r.drug}"
        if cat.get(prov) is None:
            cat.add(prov, type_name="provider")
        if cat.get(drug) is None:
            cat.add(drug, type_name="drug")
        # Parallel morphisms provider -> drug:<d>: payment-about vs prescribing-of.
        # Names are (npi, drug)-unique so the cosmos materializes a distinct
        # 2-cell per pair (it keys auto-detected 2-cells by morphism name).
        tag = f"{r.npi}::{r.drug}"
        pay_mor = cat.connect(prov, drug, name=f"paid_about::{tag}",
                              confidence=1.0, kind="payment",
                              amount=round(r.payment, 2))
        rx_mor = cat.connect(prov, drug, name=f"prescribes::{tag}",
                             confidence=1.0, kind="prescribing",
                             amount=round(r.prescribing, 2))
        cat.add("pharma_influence", type_name="risk")
        cat.connect(prov, "pharma_influence", name="drug_conflict_risk",
                    confidence=round(min(1.0, r.drug_lift / 10.0), 4),
                    drug=r.drug, payment=round(r.payment, 2),
                    prescribing=round(r.prescribing, 2), drug_lift=round(r.drug_lift, 3))
        if self.cosmos is not None:
            try:
                self.cosmos.add_two_cell(
                    f"drug_conflict::{r.npi}::{r.drug}", rx_mor.id, pay_mor.id,
                    data={"drug": r.drug, "payment": r.payment,
                          "prescribing": r.prescribing, "lift": r.drug_lift})
            except Exception:
                pass


def summarize_drug(report: DrugConflictReport, top: int = 20) -> str:
    lines = []
    lines.append("Drug-level Open Payments x Part D conflict (payment ABOUT a drug")
    lines.append("vs prescribing OF that drug)")
    lines.append("=" * 72)
    lines.append(f"  matched (provider, drug) pairs: {report.n_matched_pairs:,}")
    lines.append(f"  drugs with paid & unpaid prescriber groups: {report.n_drugs:,}")
    lines.append(f"  payment<->prescribing rank corr on matched pairs: "
                 f"{report.correlation:+.3f}")
    lines.append(f"  MEDIAN per-drug lift (paid vs unpaid prescribing): "
                 f"{report.median_lift:.2f}x")
    lines.append(f"  prescribing-weighted lift: {report.weighted_lift:.2f}x")
    lines.append("")
    lines.append("  top drugs by industry payment  (lift = paid/unpaid mean Rx $):")
    for l in report.top_drugs[:top]:
        lines.append(
            f"    {l.drug[:28]:<28} lift {l.lift:>6.2f}x  "
            f"paid n={l.n_paid:>6,} (${l.mean_paid:>12,.0f})  "
            f"unpaid n={l.n_unpaid:>7,} (${l.mean_unpaid:>11,.0f})")
    lines.append("-" * 72)
    lines.append("  lift > 1 means providers paid about a drug prescribe MORE of "
                 "it than\n  unpaid prescribers of the same drug. Association, not "
                 "causation.")
    return "\n".join(lines)


def synthetic_drug_inputs():
    """Payments-by-drug + prescribing-by-drug with a planted lift for one drug."""
    # DRUGX: paid providers (p1,p2,p3) prescribe much more than unpaid (u1..u6).
    payments = {("p1", "DRUGX"): 5000, ("p2", "DRUGX"): 8000,
                ("p3", "DRUGX"): 6000, ("p1", "DRUGY"): 1000}
    prescribing = {
        ("p1", "DRUGX"): 900_000, ("p2", "DRUGX"): 800_000, ("p3", "DRUGX"): 850_000,
        ("u1", "DRUGX"): 90_000, ("u2", "DRUGX"): 80_000, ("u3", "DRUGX"): 70_000,
        ("u4", "DRUGX"): 100_000, ("u5", "DRUGX"): 60_000, ("u6", "DRUGX"): 75_000,
        ("p1", "DRUGY"): 50_000,
    }
    return payments, prescribing


def synthetic_inputs():
    """Payments + prescribing with a deliberate paid-and-high-prescribing set."""
    payments = {
        "200": 5_000, "201": 250_000, "202": 800, "203": 120_000,
        "204": 40_000, "205": 0.0, "206": 95_000, "207": 12_000,
    }
    prescribing = {
        "200": 60_000, "201": 4_200_000, "202": 30_000, "203": 3_800_000,
        "204": 250_000, "205": 90_000, "206": 3_100_000, "208": 75_000,
    }
    specialty = {n: "Internal Medicine" for n in payments}
    return payments, prescribing, specialty
