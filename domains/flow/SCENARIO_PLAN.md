# Grand Plan — The HCARE Policy-Scenario Engine

### From forensic detection to predictive simulation (resume-here document)

Written 2026-06-14. This is the master plan for the **pivot**: from "find what
the money did" (forensic) to "predict what the money *would* do under different
rules and resource distributions" (counterfactual / scenario simulation). If a
session is lost, start here.

---

## 0. The one-paragraph pitch

The flow domain proved we can reproduce, from public data, the official waste
numbers (MA overpayment ≈$107B, validated to 1.12× MedPAC; drug-conflict DiD
≈$1.5B; hospital price dispersion; a $141B unified ledger). But that is
*forensic* — it assumes behavior is fixed, and there the category theory was
decorative (arithmetic wins). The real goal is a **policy-scenario engine**: set
different "foundations" (payment rules, audit intensity, benchmark caps, resource
distributions), let the actors **re-optimize**, and compute the **likely
outcome** (federal cost, overpayment, a premium/rebate proxy) — displayed as a
side-by-side comparison of scenarios. This is where the heavy math is genuinely
load-bearing, because the *behavioral response to a rule change* is exactly what
arithmetic cannot produce and game theory can.

---

## 1. The load-bearing decision (honest, with negative results)

**What is decorative (do NOT lean on it for findings):**
- The categorical vocabulary in the forensic detectors (2-cells, Yoneda, sheaf
  language) wrapped operations that are really arithmetic, group-by, ratios,
  correlation, and a diff-in-differences.
- **Sheaf / H¹ cohomology is NOT load-bearing for flow's money reconciliation.**
  Ported and run on real data: the scalar sheaf's gauge collapsed to the trivial
  eigenvector on the 2-source conservation (reproduced the threshold), and the
  3-source charge/allowed/payment gauge came out nonsensical (ratio 1.46 > 1)
  because the linear model `x_v = ratio·x_u` only fits same-quantity sources with
  ratios ≈ 1 (grid's regime), not money ratios spanning 0.05–0.8. Keep
  `domains/flow/sheaf.py` only for a future ≥3-source *same-quantity cyclic*
  case (e.g. the vertical chain); it is not the engine.

**What IS load-bearing for the predictive goal:**
- **Game theory (open games / Nash)** — THE engine. A rule change alters payoffs
  → the equilibrium strategy shifts → the outcome changes. Arithmetic can't do
  this; it's the whole point. Assets present: `src/komposos_core/game/nash.py`,
  `open_games.py`; the **inspection game** + continuous `local_nash_intensity`
  already in `domains/flow/nash_sheaf.py`.
- **Kan extensions** — consistency glue. Right Kan = constrained downward
  allocation: a national lever (audit budget, benchmark policy) extended to
  per-state/county levels consistent with the national constraint, so one knob
  propagates coherently to the granularity where we have real data. Asset:
  `src/komposos_core/categorical/kan_extensions.py`.
- **Activity theory** — the actor/lever map (subject, object, rules, community,
  division of labor; contradictions = where change is driven). Structures the
  *scenario space* (who can pull which lever), not a number cruncher. Asset:
  `src/komposos_core/categorical/activity_system.py`.

---

## 2. The core architecture

```
PolicyLevers (the "foundations" CMS/regulator sets)
        │
        ▼
Behavioral response  ──  game-theoretic equilibrium (load-bearing)
  each plan best-responds with a coding intensity u* that solves its
  inspection game vs CMS, given (audit rate, penalty, benchmark headroom,
  statutory coding adjustment).  u* is ENDOGENOUS to the levers, not a fixed 1.20.
        │
        ▼
Outcome recompute  ──  on REAL data (GeoVar + ratebook, per state)
  paid = E·bm·er(u*),  consumed = E·ffs·fr,  overpayment = paid − consumed
        │
        ▼
Kan propagation  ──  national lever  →  per-state/county consistent allocation
        │
        ▼
Derived outcomes  ──  federal cost, per-enrollee, premium/rebate proxy
        │
        ▼
Scenario display  ──  baseline vs each policy, side by side (table / ledger row)
```

The single conceptual shift: **coding intensity `er` stops being a constant and
becomes `er(levers)` — the Nash best response.** Everything else (the real-data
overpayment math in `medicare_advantage.py`) is reused; the game makes it
predictive.

---

## 3. The game model (the heart)

Per market (state/county), an **inspection game** between a plan and CMS:
- Plan chooses upcoding intensity `u ∈ [0,1]`.
  - gain(u)   = benchmark_headroom · u · E · bm        (extra capitated $)
  - exp.cost  = audit_rate · penalty · u · (clawback)  (detected & recovered)
- CMS chooses audit rate `q` (or it's a fixed policy lever).
- Continuous Nash: `u* = clip( gain_slope / (q · penalty · slope) ... )` — the
  form already in `nash_sheaf.local_nash_intensity`; lift/generalize it.
- The statutory coding adjustment (5.9%) and any benchmark cap enter the payoff,
  so each lever shifts `u*` and hence overpayment.

Honest note: the *magnitude* of response depends on assumed behavioral
elasticities (slopes). Expose them as explicit parameters; calibrate so the
**baseline (status-quo levers) reproduces the known ≈$84–107B** (validation
gate). Then relative/directional scenario effects are credible — the same class
of object as CBO/MedPAC microsimulation, a transparent model, not a forecast of
truth.

---

## 4. Policy levers (v1 set)

| Lever | Current | Scenario examples |
|---|---|---|
| Statutory coding adjustment | 5.9% | 10%, 20% |
| RADV audit rate | ~low | 2×, 5× |
| RADV penalty / extrapolation | vacated (2025) | reinstated, ×N |
| Benchmark ratio / cap | ~108% FFS | cap at 100% FFS |
| Quality-bonus pool | on | off / reformed |
| (later) provider-side levers | — | site-neutral pay, etc. |

---

## 5. Outcomes computed (and the honest boundary)

- **Money (credible):** federal MA spending, overpayment, per-enrollee, by state
  and national, under each scenario. This is the engine's solid output.
- **Premiums/rebates (proxy):** MA rebate = (benchmark − bid)·rebate% funds
  supplemental benefits / lower premiums; map overpayment change → rebate/premium
  change as a STATED proxy model, clearly labeled.
- **Patient health / "healthier public" (OUT of scope):** outcome data is not in
  the money graph. The engine predicts dollars and incentives, not health. Do
  not claim health outcomes; flag the inferential gap explicitly.

---

## 6. Phased roadmap

- **Phase A — Scenario core. ✅ DONE (2026-06-14).** `domains/flow/scenario.py`:
  `PolicyLevers` dataclass; `BehavioralModel` with `upcoding()/risk_score()`
  (generalizes `local_nash_intensity` — `p* = g/(g+d)`, `er = 1+κ·p*`) making the
  MA risk score **endogenous** to the levers; `ScenarioEngine.run(levers)` reuses
  the validated 2-cell math in `medicare_advantage.py`. `BehavioralModel.calibrate`
  solves `base_deter` by bisection so the **baseline reproduces the forensic
  number** — the gate. CLI: `--scenario` (synthetic) /
  `--scenario --ma-geovar … --ma-ratebook … --ma-crosswalk …` (real).
  - **Gate PASSED on real 2024 data:** forensic baseline (fixed risk 1.20) =
    **$107.3B**; calibrated endogenous baseline = **$107.3B, mean coding
    intensity 1.200, gate error 0.00%** (`base_deter≈0.034`, κ=0.30, elasticity=1).
  - **Directional responses (real data, equilibrium deltas vs baseline):**
    coding adj 20% −$81.5B · audit 5× −$40.1B (mean risk 1.20→1.11) · RADV
    penalty ×3 −$26.5B · benchmark cap @100% FFS −$133.8B (headroom→0 ⇒ coding
    incentive vanishes, risk→1.00, MA falls below FFS) · combined −$135.9B.
  - Honest decomposition surfaced: the statutory **coding-adjustment** lever acts
    mostly through the *mechanical haircut* on realized `er` (big $ move, small
    `p*` move), while **audit/penalty** act through *behavioral deterrence* (move
    `p*`/mean risk directly). The model separates the two — a feature, not a bug.
  - 11 new tests in `tests/test_scenario.py` (gate + monotonicity per lever);
    suite **114 passed**.
  - **Next (Phase B):** the lever set and `compare()` already exist; remaining is
    real per-market deterrence (Kan, Phase C) and the premium proxy (Phase D).

- **Phase A (original spec).** `scenario.py`: `PolicyLevers` dataclass; a
  `best_response(levers, market)` Nash solver (generalize `local_nash_intensity`)
  making `er` endogenous; recompute MA outcomes on real GeoVar/ratebook;
  **calibrate baseline to the known number** (validation gate). Tests.
- **Phase B — Levers + comparison.** Implement the lever set; a
  `compare(scenarios)` that returns the side-by-side table (national overpayment,
  Δ vs baseline, per-enrollee, equilibrium coding). CLI `--scenario`.
- **Phase C — Kan propagation. ✅ DONE (2026-06-14).** `domains/flow/propagation.py`:
  a `NationalLever` (one national audit budget + an allocation `policy`) is pushed
  to per-state audit multipliers by a **right Kan extension** — the per-state
  allocation is the cone over the national aggregate, conserving the budget
  exactly (`Σ_s E_s·mult_s = budget·Σ_s E_s`). That conservation law is the
  load-bearing categorical content; the `TARGETED` policy returns the **terminal
  (overpayment-minimizing) cone** via marginal-equalizing water-filling.
  - **Proof it's not decorative (real 2024 data, same 2× budget, 3 allocations):**
    uniform $91.4B · **targeted (optimal) $87.6B (−$3.8B for the same
    auditor-hours)** · equal-per-state $100.9B (+$9.5B) — a ~$13B spread that the
    budget scalar alone cannot express and uniform Phase-A deterrence structurally
    could not produce.
  - **Non-obvious finding:** the optimum does *not* pile audits on the
    worst-offender state — diminishing returns (`p*=g/(g+d)` convex) make that
    wasteful; it equalizes *marginal* returns, spreading effort. Refutes "audit
    the worst hardest."
  - We deliberately did **not** route through the generic `RightKanExtension`
    class (its numeric limit is a conservative *minimum*, wrong for a conserved
    budget) — that would have been the decorative-wrapper mistake; the cone is
    built explicitly. CLI: `--propagate [--audit-budget N]`. `ScenarioEngine.run`
    now takes an optional `audit_by_geo`. 7 new tests; suite **121 passed**.
- **Phase D — Premium/rebate proxy + display.** The derived-outcome layer + a
  comparison display (table now; dashboard later). Optionally a ledger
  "scenario" view.
- **Phase E — Multi-actor open games + activity map.** Compose CMS→plan→provider
  as an open game (`open_games.py`); activity-theory actor/lever map as the
  framing/UX. Counterfactuals across the chain.
- **Phase F — (stretch) outcome linkage.** Only if external outcome data is
  brought in; explicitly gated, not promised.

---

## 7. Validation discipline (non-negotiable, the lesson learned)

- **Baseline calibration:** status-quo levers must reproduce the validated
  forensic number (≈$84–107B, 1.0–1.2× MedPAC). If it doesn't, the model is
  wrong before any scenario is run.
- **Directional checks:** scenario responses must match published sensitivities
  (e.g. MedPAC on coding-intensity response to the statutory adjustment).
- **Expose every behavioral assumption** as a labeled parameter. No hidden
  elasticities. State "model, not forecast" on every scenario output.

---

## 8. Current assets (what exists on resume)

- **Real data on disk (gitignored `data/`):** `cms_d24_service.csv` 3.25GB,
  `cms_d24_summary.csv`, `cms_d24_partd.csv`, `cms_d24_partd_bydrug.csv` 4GB,
  `cms_d23_partd_bydrug.csv`, `cms_op_2024.csv` 8.9GB, `cms_op_2023.csv` 8.2GB,
  `ffs_geovar_2014_2024.csv` (2014–2024 in one file), `2024-ma-rate-book.zip`,
  `ssa_fips_2024.csv`, `cms_inpatient_2024.csv`.
- **Forensic detectors (real, validated):** `medicare_advantage.py` (overpayment
  + decomposition), `conflict.py` (NPI / drug / **DiD**), `outliers.py`
  (rank-based rarity), `hospital.py`, `coherence.py`, `nash_sheaf.py`
  (inspection game + Nash sheaf), `ledger.py` + `delivery.py` (unified ledger
  + daily job), `validation.py` (MedPAC/RADV/OIG), `trends.py` (multi-year).
- **Math modules (in `src/komposos_core`):** `game/nash.py`, `game/open_games.py`,
  `categorical/kan_extensions.py`, `categorical/activity_system.py`,
  `geometry/grid_ricci.py`, `geometry/grid_spectral.py`,
  `komposos_wesys/validation/thermodynamic_probe.py` (sheaf solver — kept, not
  the engine).
- **Repo:** github.com/Jayhawk314/KOMPOSOS-Hcare (pushed). 103 tests pass.
- **Other KOMPOSOS systems with portable math:** `KOMPOSOS-SEC-master`
  (gray_coherence, spectral_anomaly_detection, persistent_homology, ricci),
  `KOMPOSOS-IV-PHARM-master` (horns / horns_retrodiction / horns_vs_composition,
  gray_category), `KOMPOSOS-GRID` (sheaf_audit, grid_ricci/spectral). PORT into
  this repo as needed; do not cross-wire repos.

---

## 9. The honest north star

This engine's realistic value: a **transparent policy what-if calculator** for
the Medicare-Advantage money game — set the rules, see how plans re-optimize and
what it costs — credible as a model, validated at baseline, honest about its
limits (money yes; premiums as a proxy; health out of scope). It does not "fix"
healthcare; it lets someone with standing (CMS, MedPAC, CBO, a state, a
journalist) *see the consequence of a rule before enacting it*. That is a real,
defensible, math-load-bearing contribution — unlike the forensic re-derivation,
which the experts already publish.

**Start at Phase A: make coding intensity endogenous via the Nash best response,
and calibrate the baseline to the validated number.**
