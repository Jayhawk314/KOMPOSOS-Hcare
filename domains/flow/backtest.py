# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Phase G -- backtest & sensitivity: make the engine *trustworthy*.

The baseline is pinned by calibration; the engine's VALUE is the behavioral
response to a lever, which rides on assumed elasticities. So the scientific
question is "are the elasticities right, and are the conclusions robust to them?"
This module answers it four ways (see ``VALIDATION_PLAN.md`` Phase G):

  G1 bootstrap_calibration  -- is base_deter structural or driven by a few states?
  G2 state_holdout_cv       -- does a model fit on some states reproduce others?
  G3 sensitivity            -- do scenario RANKINGS survive parameter sweeps?
  G4 directional_checks     -- does the model agree with published experiments?

THE HONEST LIMIT, stated up front: there is no public ground-truth per-state MA
coding intensity (it is restricted encounter data -- the same wall the Nash
detector hits). So we cannot backtest the coding mechanism against measured
behavior. What G1/G2 test is INTERNAL generalization -- that one ``base_deter``
fits the real cross-state heterogeneity. That heterogeneity exists only where
benchmarks are REAL (the 2024 ratebook); a modeled 1.08x benchmark makes headroom
a constant 0.08 in every state, which would make the test vacuous -- so the
cross-STATE split must run on real-benchmark markets. G3 (robustness) and G4
(published direction) are the substantive checks. None of this validates against
truth; it shows the conclusions are internally robust and directionally sound.
"""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from domains.flow.medicare_advantage import (
    MedicareAdvantageTwoCell, MAContract, MEDPAC_MA_CODING_RISK,
)
from domains.flow.scenario import (
    Market, PolicyLevers, BehavioralModel, ScenarioEngine, v1_scenarios,
    DEFAULT_KAPPA,
)

# kappa (the coding ceiling: risk -> 1+kappa for an all-out gamer) is NOT
# identified from the public aggregate -- the baseline mean is pinned by
# calibration regardless of kappa, and per-contract coding is restricted data.
# We therefore PIN it to the literature rather than fit it: MedPAC documents
# coding raising MA risk scores ~16-20% on average (gross, before the 5.9%
# statutory cut), with the most aggressive contracts materially higher. The
# ceiling must sit STRICTLY above the calibrated mean coding (~0.20) -- at
# kappa=0.20 every plan is already maxed (base_deter -> 0, audit cannot bite),
# a degenerate boundary, not a real regime. The defensible band is therefore
# [0.25, 0.35] around the 0.30 anchor; conclusions are reported across it
# (uncertainty_bands), not as a false point estimate. The band itself reveals
# that AUDIT-lever efficacy is the most kappa-sensitive conclusion (how much
# headroom exists between current coding and the ceiling).
KAPPA_RANGE: Tuple[float, float] = (0.25, 0.35)
KAPPA_GRID: Tuple[float, ...] = (0.25, 0.30, 0.35)
ELASTICITY_GRID: Tuple[float, ...] = (0.5, 1.0, 2.0)


def forensic_overpayment(markets: Sequence[Market]) -> float:
    """The fixed-MedPAC-risk (1.20) overpayment for a set of markets -- the
    forensic target the endogenous baseline is calibrated to reproduce."""
    contracts = [MAContract(m.geo, m.enrollment, m.benchmark_per_capita,
                            m.ffs_per_capita, risk_score=MEDPAC_MA_CODING_RISK,
                            ffs_risk=m.ffs_risk) for m in markets]
    return sum(r.overpayment
               for r in MedicareAdvantageTwoCell().evaluate_all(contracts))


# ---------------------------------------------------------------------------
# G1. Bootstrap calibration stability (resample states)
# ---------------------------------------------------------------------------
@dataclass
class StabilityReport:
    base_deters: List[float]
    mean: float
    cv: float                        # coefficient of variation (std/mean)

    @property
    def stable(self) -> bool:
        return self.cv < 0.25        # < 25% spread == structural, not a few states


def bootstrap_calibration(markets: Sequence[Market], *, trials: int = 40,
                          frac: float = 0.7, seed: int = 0,
                          elasticity: float = 1.0,
                          kappa: float = DEFAULT_KAPPA) -> StabilityReport:
    """Resample a fraction of states, recompute the forensic target on the
    subset, recalibrate ``base_deter``; report the spread. A calibration driven
    by a handful of states is fragile; a stable one is structural."""
    rng = random.Random(seed)
    mkts = list(markets)
    k = max(2, int(frac * len(mkts)))
    bds: List[float] = []
    for _ in range(trials):
        sub = rng.sample(mkts, k)
        target = forensic_overpayment(sub)
        if target <= 0:
            continue
        model = BehavioralModel.calibrate(sub, target_overpayment=target,
                                          elasticity=elasticity, kappa=kappa)
        bds.append(model.base_deter)
    mean = sum(bds) / len(bds) if bds else 0.0
    var = sum((b - mean) ** 2 for b in bds) / len(bds) if bds else 0.0
    cv = (var ** 0.5 / mean) if mean else 0.0
    return StabilityReport(base_deters=bds, mean=mean, cv=cv)


# ---------------------------------------------------------------------------
# G2. State hold-out cross-validation (fit on some states, test on the rest)
# ---------------------------------------------------------------------------
@dataclass
class OutOfSampleReport:
    folds: int
    errors: List[float]              # |endogenous - forensic| / forensic per fold
    max_error: float
    mean_error: float


def state_holdout_cv(markets: Sequence[Market], *, folds: int = 5, seed: int = 0,
                     elasticity: float = 1.0,
                     kappa: float = DEFAULT_KAPPA) -> OutOfSampleReport:
    """K-fold over states: calibrate ``base_deter`` on the training states, apply
    it to the held-out states, and measure how well it reproduces the held-out
    forensic overpayment. Tests whether one behavioral parameter generalizes
    across the real cross-state headroom heterogeneity (needs real benchmarks)."""
    rng = random.Random(seed)
    mkts = list(markets)
    rng.shuffle(mkts)
    errors: List[float] = []
    for f in range(folds):
        test = [m for i, m in enumerate(mkts) if i % folds == f]
        train = [m for i, m in enumerate(mkts) if i % folds != f]
        if not test or not train:
            continue
        ttarget = forensic_overpayment(train)
        if ttarget <= 0:
            continue
        model = BehavioralModel.calibrate(train, target_overpayment=ttarget,
                                          elasticity=elasticity, kappa=kappa)
        got = ScenarioEngine(test, model).run(PolicyLevers.baseline()).overpayment
        truth = forensic_overpayment(test)
        if truth > 0:
            errors.append(abs(got - truth) / truth)
    return OutOfSampleReport(
        folds=len(errors), errors=errors,
        max_error=max(errors) if errors else 0.0,
        mean_error=sum(errors) / len(errors) if errors else 0.0)


# ---------------------------------------------------------------------------
# G3. Sensitivity / robustness -- do scenario RANKINGS survive?
# ---------------------------------------------------------------------------
@dataclass
class SensitivityReport:
    param: str
    values: List[float]
    rankings: List[List[str]]        # scenario order (best->worst) per value
    headline_deltas: List[float]     # the headline scenario's delta per value
    ranking_stable: bool             # exact-order preserved across the sweep
    rank_agreement: float            # fraction of pairwise orderings preserved
    swaps: List[Tuple[str, str]]     # adjacent pairs that swap (the instability)


def _ranking(engine: ScenarioEngine,
             scenarios: Sequence[PolicyLevers]) -> List[str]:
    base = engine.run(PolicyLevers.baseline()).overpayment
    scored = [(lev.label, engine.run(lev).overpayment - base) for lev in scenarios]
    scored.sort(key=lambda x: x[1])            # most negative (biggest cut) first
    return [name for name, _ in scored]


def _rank_agreement(rankings: Sequence[List[str]]) -> Tuple[float, List[Tuple[str, str]]]:
    """Fraction of pairwise orderings preserved vs the central ranking (a graded
    Kendall-tau-style measure -- a near-tie swap of two adjacent scenarios scores
    near 1.0, not 0), plus the specific pairs that ever swap."""
    ref = rankings[0]
    pairs = list(itertools.combinations(ref, 2))
    pos_ref = {n: i for i, n in enumerate(ref)}
    worst = 1.0
    swaps: set = set()
    for r in rankings[1:]:
        pos = {n: i for i, n in enumerate(r)}
        concord = 0
        for a, b in pairs:
            same = (pos_ref[a] < pos_ref[b]) == (pos[a] < pos[b])
            if same:
                concord += 1
            else:
                swaps.add(tuple(sorted((a, b))))
        worst = min(worst, concord / len(pairs))
    return worst, sorted(swaps)


def sensitivity(markets: Sequence[Market], target: float, *,
                param: str, values: Sequence[float],
                scenarios: Optional[Sequence[PolicyLevers]] = None,
                headline: str = "coding adj 20%") -> SensitivityReport:
    """Vary one exposed parameter; recalibrate base_deter each time so the gate
    holds; report the headline scenario's delta range, exact-ranking stability,
    and the GRADED rank agreement (so a near-tie at the top is not mislabeled a
    catastrophic flip)."""
    scenarios = list(scenarios or v1_scenarios())
    rankings: List[List[str]] = []
    deltas: List[float] = []
    for v in values:
        kw = {"elasticity": 1.0, "kappa": DEFAULT_KAPPA}
        if param in kw:
            kw[param] = v
        model = BehavioralModel.calibrate(markets, target_overpayment=target, **kw)
        eng = ScenarioEngine(markets, model)
        rankings.append(_ranking(eng, scenarios))
        base = eng.run(PolicyLevers.baseline()).overpayment
        hl = next((lev for lev in scenarios if lev.label == headline), None)
        deltas.append((eng.run(hl).overpayment - base) if hl else 0.0)
    agreement, swaps = _rank_agreement(rankings)
    return SensitivityReport(
        param=param, values=list(values), rankings=rankings,
        headline_deltas=deltas, ranking_stable=all(r == rankings[0] for r in rankings),
        rank_agreement=agreement, swaps=swaps)


# ---------------------------------------------------------------------------
# Uncertainty bands -- every scenario delta as a range over the parameter grid
# ---------------------------------------------------------------------------
@dataclass
class ScenarioBand:
    label: str
    lo: float                        # min overpayment delta across the grid
    mid: float                       # central (kappa=0.30, elasticity=1.0)
    hi: float                        # max overpayment delta across the grid


def uncertainty_bands(markets: Sequence[Market], target: float, *,
                      scenarios: Optional[Sequence[PolicyLevers]] = None,
                      kappa_values: Sequence[float] = KAPPA_GRID,
                      elasticity_values: Sequence[float] = ELASTICITY_GRID
                      ) -> List[ScenarioBand]:
    """Each scenario's overpayment delta vs baseline, as a BAND over the
    (kappa, elasticity) uncertainty grid -- recalibrating base_deter at every
    grid point so the baseline gate always holds. This is the honest CBO-style
    output: a range, not a point, so near-ties read as overlapping bands."""
    scenarios = list(scenarios or v1_scenarios())
    deltas = {lev.label: [] for lev in scenarios}
    mids = {lev.label: 0.0 for lev in scenarios}
    for k in kappa_values:
        for e in elasticity_values:
            model = BehavioralModel.calibrate(markets, target_overpayment=target,
                                              kappa=k, elasticity=e)
            eng = ScenarioEngine(markets, model)
            base = eng.run(PolicyLevers.baseline()).overpayment
            for lev in scenarios:
                d = eng.run(lev).overpayment - base
                deltas[lev.label].append(d)
                if abs(k - DEFAULT_KAPPA) < 1e-9 and abs(e - 1.0) < 1e-9:
                    mids[lev.label] = d
    return [ScenarioBand(label=lev.label, lo=min(deltas[lev.label]),
                         mid=mids[lev.label], hi=max(deltas[lev.label]))
            for lev in scenarios]


def summarize_bands(bands: Sequence[ScenarioBand]) -> str:
    rows = [("scenario", "overpayment delta vs baseline (band over kappa x elasticity)")]
    lines = ["Scenario uncertainty bands -- delta range over the parameter grid",
             "=" * 74]
    width = max(len(b.label) for b in bands)
    for b in bands:
        if b.label == "baseline":
            continue
        lines.append(f"  {b.label:<{width}}  "
                     f"${b.lo/1e9:+6,.1f}B .. ${b.hi/1e9:+6,.1f}B  "
                     f"(central ${b.mid/1e9:+,.1f}B)")
    lines.append("-" * 74)
    lines.append("  Bands span the MedPAC-anchored kappa [0.25-0.35] x elasticity "
                 "grid, each point\n  recalibrated to the baseline gate. Overlapping "
                 "bands = a near-tie, not a\n  robust ranking -- read the ranges, "
                 "not the point estimates.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# G4. Published-anchor directional checks
# ---------------------------------------------------------------------------
@dataclass
class DirectionalCheck:
    claim: str
    published: str
    predicted: str
    agrees: bool


def directional_checks(engine: ScenarioEngine) -> List[DirectionalCheck]:
    """Assert the model agrees in DIRECTION with published natural experiments."""
    base = engine.run(PolicyLevers.baseline())
    checks: List[DirectionalCheck] = []

    cap = engine.run(PolicyLevers(benchmark_cap=1.0, label="cap"))
    checks.append(DirectionalCheck(
        claim="benchmark cut lowers overpayment & federal paid",
        published="ACA phase-down: plan bids fell 102%->87% of FFS (2009-2021)",
        predicted=f"overpayment {base.overpayment/1e9:,.0f}B -> "
                  f"{cap.overpayment/1e9:,.0f}B; paid "
                  f"{base.paid/1e9:,.0f}B -> {cap.paid/1e9:,.0f}B",
        agrees=cap.overpayment < base.overpayment and cap.paid < base.paid))

    adj = engine.run(PolicyLevers(coding_adjustment=0.20, label="adj"))
    checks.append(DirectionalCheck(
        claim="higher statutory coding adjustment lowers coding & overpayment",
        published="MedPAC: the 5.9% statutory cut exists to offset coding intensity",
        predicted=f"mean risk {base.mean_risk:.3f} -> {adj.mean_risk:.3f}; "
                  f"overpayment {base.overpayment/1e9:,.0f}B -> "
                  f"{adj.overpayment/1e9:,.0f}B",
        agrees=adj.overpayment < base.overpayment
        and adj.mean_risk <= base.mean_risk + 1e-9))

    aud = engine.run(PolicyLevers(audit_multiplier=5.0, label="audit"))
    checks.append(DirectionalCheck(
        claim="stronger audit/RADV lowers coding intensity",
        published="RADV is designed to recover & deter unsupported coding",
        predicted=f"mean risk {base.mean_risk:.3f} -> {aud.mean_risk:.3f}",
        agrees=aud.mean_risk < base.mean_risk))
    return checks


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def summarize_backtest(stability: Optional[StabilityReport] = None,
                       oos: Optional[OutOfSampleReport] = None,
                       sens: Optional[Sequence[SensitivityReport]] = None,
                       checks: Optional[Sequence[DirectionalCheck]] = None) -> str:
    lines = ["Backtest & sensitivity -- is the behavioral response trustworthy?",
             "=" * 74]
    if stability is not None:
        lines.append("")
        lines.append("  G1 bootstrap calibration stability (resampled states, "
                     f"{len(stability.base_deters)} trials):")
        verdict = "STRUCTURAL (stable)" if stability.stable else "FRAGILE (few-state driven)"
        lines.append(f"     base_deter mean={stability.mean:.5f}  "
                     f"CV={stability.cv:.1%}  -> {verdict}")
    if oos is not None:
        lines.append("")
        lines.append(f"  G2 state hold-out cross-validation ({oos.folds} folds, "
                     "fit on train states, test on held-out):")
        lines.append(f"     reproduction error  max {oos.max_error:.2%}, "
                     f"mean {oos.mean_error:.2%}")
    if sens:
        lines.append("")
        lines.append("  G3 sensitivity (recalibrated each sweep; graded rank agreement):")
        for s in sens:
            lo, hi = min(s.headline_deltas), max(s.headline_deltas)
            tag = (f"{s.rank_agreement:.0%} of orderings hold"
                   + ("" if s.ranking_stable else
                      "; swaps: " + ", ".join(f"{a}~{b}" for a, b in s.swaps[:2])))
            lines.append(f"     {s.param:<10} in [{s.values[0]:g}..{s.values[-1]:g}] "
                         f"-> headline delta ${lo/1e9:,.0f}B..${hi/1e9:,.0f}B")
            lines.append(f"                  rank agreement: {tag}")
    if checks:
        lines.append("")
        lines.append("  G4 published-anchor directional checks:")
        for c in checks:
            mark = "OK " if c.agrees else "XX "
            lines.append(f"     [{mark}] {c.claim}")
            lines.append(f"           published: {c.published}")
            lines.append(f"           model:     {c.predicted}")
    lines.append("-" * 74)
    lines.append("  No public ground-truth coding data exists, so this is not a "
                 "truth test; it\n  shows the conclusions are INTERNALLY robust "
                 "(stable calibration, preserved\n  rankings) and DIRECTIONALLY "
                 "consistent with published experiments.")
    return "\n".join(lines)
