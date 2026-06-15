# Validation & Scientific-Rigor Plan — the Policy-Scenario Engine

### From "a model" to "a *validated* model" (resume-here document)

Written 2026-06-14, after Phases A–E built the engine (see `SCENARIO_PLAN.md`).
The engine now *computes* counterfactuals; this plan makes it *trustworthy* and
then extends it toward the multi-actor, multi-objective vision. It also records,
in writing, the honest stance on which math is load-bearing vs decorative — the
discipline the whole project rests on.

---

## 0. The honest framing

The engine's baseline is *pinned by construction* (calibrated to the validated
forensic ~$107B). Its value is the **behavioral response to a lever** — and that
response rides on assumed elasticities. So the scientific question is not "is the
baseline right" (it is, by calibration) but **"are the elasticities right, and
are the conclusions robust to them?"** Everything below serves that question.

We are fortunate: the behavioral responses we model have **published natural
experiments and elasticities** to check against (MedPAC; Health Affairs).

---

## 1. The math-discipline stance (load-bearing vs decorative)

Recorded so we don't repeat the sheaf mistake in the other direction.

- **LOAD-BEARING (keep building):**
  - **Game theory / open games** — a rule change shifts payoffs → equilibrium
    shifts → outcome changes. The validated spine. (`scenario.py`, `chain.py`.)
  - **Kan extension** — whole↔part consistency (national↔state under a
    conservation cone). Genuinely load-bearing. (`propagation.py`.)
  - **Categorical orchestration** — each actor is an open game (object+strategy);
    relationships are morphisms; a "constitution" is a particular *wiring* of
    which levers couple which actors, i.e. a composite in the category of open
    games. This IS the novel contribution and it is real.
  - **Coherence = conservation/consistency LAWS** (national = Σ states; payoffs
    that must reconcile). Load-bearing only in this concrete sense.
  - **Activity theory** — the actor/lever/contradiction *frame*, not a number
    cruncher. (`actors.py`.) Keep as framing.
- **DEFER (decorative risk — do not force in):**
  - **HoTT / ∞-category 2-cells** — a foundation for *proof*, no load-bearing
    role in an economic simulation yet. Admit only if a concrete need appears
    (e.g. *proving* two computation paths through the category agree — a genuine
    coherence theorem). Until then, out.
  - **Unconstrained CAS / agent-based models** — healthcare *is* a complex
    adaptive system, but ABMs are notoriously unfalsifiable. Admit CAS only where
    it is **testable**: multi-year *dynamics with feedback* (this year's coding →
    next year's benchmark → next year's coding) checked against the real
    2014–2024 series — never as a free-floating emergence engine.
- **THE DATA BOUNDARY (the whole vs the individual):** Kan serves the
  *geographic* whole↔part. The *individual patient's* health/equity needs
  patient-level outcome data that is **not in the money graph**. Distributional
  analysis across states/plans is in scope; individual health outcomes are not.

---

## 2. Phase G — Backtest & sensitivity ✅ DONE (2026-06-14)

`domains/flow/backtest.py` + `--backtest`. **Honest findings (real 2024 data) —
this surfaced real weaknesses, not fake passes:**
- **G1 bootstrap calibration: CV ≈ 26% → FRAGILE.** `base_deter` is somewhat
  driven by a few large states; not rock-solid. Flagged, not hidden.
- **G2 state hold-out CV: ~19% mean / ~63% max reproduction error.** One
  `base_deter` fit on a subset of states does not cleanly generalize to held-out
  states — the aggregate calibration is good but per-subset prediction is loose.
- **G3 sensitivity: elasticity ranking PRESERVED (robust); `kappa` ranking
  FLIPS.** The actionable result: conclusions survive the gain-elasticity
  assumption but are sensitive to the coding *ceiling* `kappa` → `kappa` must be
  pinned to data (MedPAC coding-intensity bound), not chosen.
- **G4 directional checks: all 3 agree** with published experiments (benchmark
  cut↓, coding-adj↑ deters, audit↑ deters).
- **The vacuous test we caught and removed:** a first cut did calibration
  *across years* with the modeled `1.08×ffs` benchmark — but that makes headroom a
  constant 0.08 everywhere, so it trivially reported "CV 0.0%, 0.00% error."
  Replaced with the **cross-STATE** split on real-ratebook markets (the only place
  real headroom heterogeneity exists). Recorded so we don't reintroduce it.
- **The standing limit, stated in the module:** no public per-state coding-
  intensity ground truth (restricted encounter data — the Nash wall), so G1/G2
  test internal generalization, not truth; G3/G4 are the substantive checks.
- 7 tests; suite **146 passed**. CLI `--backtest`.

**G-hardening ✅ DONE (2026-06-14), from the G3 finding:**
- **`kappa` pinned to a literature anchor, not a free knob.** `KAPPA_RANGE =
  [0.25, 0.35]` around the 0.30 ceiling, documented from MedPAC's coding-intensity
  figures. Caught that `kappa = 0.20` is a *degenerate boundary* (ceiling = the
  calibrated mean coding ⇒ every plan maxed ⇒ `base_deter → 0` ⇒ audit can't
  bite), so the band sits strictly above it.
- **Graded rank agreement replaces the binary "FLIPS".** The kappa sweep holds
  **86%** of pairwise orderings; the only instability is a **near-tie among the
  most aggressive reforms** (named in output), not a policy reversal.
- **Uncertainty bands on every scenario** (`uncertainty_bands` / `--backtest`),
  recalibrated at each (kappa × elasticity) grid point. The honest CBO-style
  output. It reveals the real structure: **coding-adjustment and benchmark-cap
  conclusions are robust** (tight bands, e.g. coding-adj 20% −$80B to −$83B),
  while **audit/penalty efficacy is genuinely uncertain** (audit 5× spans −$22B
  to −$48B, depending on headroom-to-ceiling). Benchmark-cap and combined-reform
  bands overlap → the top "ranking" is a true near-tie, shown honestly.
- 4 more tests; suite **149 passed**.

**Still open (lower priority):** make `base_deter` calibration more robust to
state subsampling (G1 CV ~26%) — but the main all-states calibration is
deterministic and fine; the bootstrap CV is a diagnostic, not a bug. Defer.

### Original spec (for reference)

The deliverable: `domains/flow/backtest.py` + `--backtest`, doing three things.

- **G1. Calibration stability across years.** Calibrate `base_deter`
  independently for each year 2014–2024 (real FFS consumed side; modeled
  benchmark ratio held constant for cross-year comparability). Report the spread
  (CV). A *stable* `base_deter` = the behavioral parameter is structural, not
  per-year curve-fitting. A wandering one = honest red flag.
- **G2. Out-of-sample reproduction.** Calibrate on ONE anchor year, apply that
  frozen model to every other year *without refit*, and measure the reproduction
  error of that year's forensic overpayment. Low error = the model generalizes
  across the real cross-year variation in headroom/enrollment.
- **G3. Sensitivity / robustness (the CBO/MedPAC standard).** Sweep each exposed
  elasticity (`elasticity`, `kappa`, `bid_to_ffs`, provider params) over
  plausible ranges, recalibrating `base_deter` each time so the gate always
  holds. Report (i) the range of each headline scenario delta, and (ii) whether
  the **scenario ranking is preserved**. Robust ranking = conclusions survive the
  assumptions; flipped ranking = flagged as assumption-driven.
- **G4. Published-anchor directional checks.** Encode the literature facts and
  assert the model agrees in *direction* (and, where possible, rough magnitude):
  - ACA benchmark phase-down: plan bids fell 102%→87% of FFS (2009→2021) as
    benchmarks fell ⇒ our `benchmark_cap` must lower overpayment & paid. ✓
  - rebate share ≈ 65% (we use 0.65 — match); benchmark ≈ 108% FFS (1.08 — match).
  - coding-intensity pass-through: $1 coding revenue → $0.10–0.19 bid cut,
    $0.11–0.16 premium cut, larger under competition (Health Affairs Scholar
    2024) ⇒ target for Phase H's bid/competition model.

Validation discipline: state predictions *before* checking; report failures.

---

## 3. Phase H — Add the patient & market actors (makes objectives real)

To optimize for *desired outcomes* we need outcomes beyond federal cost. Compose
two more open games onto the chain:

- **Patient / beneficiary** — enrollment responds to premium/benefit generosity
  (a demand elasticity); this turns "access" into a real objective and lets
  rebate cuts feed back into take-up.
- **Market / competition** — plans compete; the published result (coding
  pass-through is *stronger* in competitive counties) is the calibration anchor.
  Competition sets how much of a lever's effect reaches beneficiaries vs profit.

Each new actor MUST be calibrated to data or have its assumption exposed and
sensitivity-tested (Phase G), or the grand composite becomes an elaborate
opinion. This is the non-negotiable price of adding actors.

---

## 4. Phase I — Multi-objective Pareto frontier (the "spread for outcomes")

The thing the vision actually asks for. With objectives `f₁` federal cost, `f₂`
beneficiary value, `f₃` access/enrollment, `f₄` equity (distributional spread):

- sweep the lever space (grid, then an optimizer);
- compute the **Pareto frontier** — lever settings where no objective improves
  without another worsening;
- for any desired outcome, read the lever setting off the frontier.

This is standard multi-objective optimization — validatable, not hand-wavy — and
it is the natural home for "different constitutions → different equilibria."
Depends on Phase H for `f₃`/`f₄` to be meaningful.

---

## 5. Phase J — (gated) Multi-year dynamics with feedback

The disciplined slice of complexity theory: a *dynamical* model where each year's
equilibrium sets next year's benchmark (benchmarks are built from lagged FFS/MA
behavior), producing the coding-intensity ratchet seen historically. Admitted
ONLY because it is checkable against the real 2014–2024 series. Not an ABM.

---

## 6. Order of execution

G (validate what exists) → H (patient+market actors) → I (Pareto optimizer) →
J (dynamics, gated). G first: it makes everything after it trustworthy.

**Start at Phase G: `backtest.py` — calibration stability, out-of-sample
reproduction, sensitivity, and the published-anchor directional checks.**
