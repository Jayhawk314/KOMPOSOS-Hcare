# flow domain — Master Plan (for future sessions)

Written 2026-06-13. This is the resume-here document. The session memory at
`~/.claude/projects/.../memory/` points back to this file.

## The pitch in one paragraph

KOMPOSOS-HCARE (the repo currently on disk as `komposos-power`, being renamed
to **HCARE**) applies the categorical waste-finding engine — proven on energy
in `KOMPOSOS-GRID` — to the **U.S. healthcare money graph**. Federal spending,
provider/hospital billing, the **insurance industry** (Medicare Advantage,
the edge where federal dollars become private dollars), and hospital prices
are modeled as **one category**. Dollars conserve along composition; where the
composite ≠ the sum of its parts, that gap is the leak. Output: a
"yesterday's leak, every morning" ledger, monetizable to payers, auditors,
qui-tam attorneys, and journalists. Money at stake nationally: improper
Medicare payments ~$50–100B/yr; MA overpayment debated at tens of $B/yr.

## Why categorical, not just a dashboard

"It's all linked" *is* categorical composition. The same NPI/CCN/contract-id
appears across datasets that must agree (sheaf gluing); money summed along a
functor must match independent coarse measurements (pushforward / Kan); two
parallel evidence pathways that disagree are a 2-cell (MA paid-vs-consumed,
prescribing-vs-payments). The grid domain already proved this template prints
real numbers ($251M → national scale).

## Architecture (mirrors `KOMPOSOS-GRID/domains/grid`)

```
domains/
  __init__.py            # path bootstrap: puts src/komposos_core on sys.path
  flow/
    __init__.py
    README.md
    PLAN.md              # this file
    sources/registry.py  # dataset catalog + join keys + public/restricted status
    coherence.py         # FlowCoherenceChecker, Section, pushforward, verdicts, write-back
    run_coherence.py     # CLI: --synthetic, --registry, (Phase 2) real loaders
    tests/test_coherence.py
```

Imports use `from core.category import Category` (resolves because
`domains/__init__.py` adds `src/komposos_core` to `sys.path`).

## Phased roadmap

### ✅ Phase 1 — Spine (DONE, this session)
- [x] Source registry covering all 6 layers + join keys (NPI, CCN, contract_id).
- [x] Level-0 sheaf coherence (pairwise GLUE/TENSION/CONTRADICT) with write-back.
- [x] Level-1 pushforward along provider → specialty (money conservation).
- [x] Synthetic planted-leak demo + 7 passing tests.

### Phase 2 — Real data + the insurance 2-cell (the headline)
1. **Loaders** for the public CSVs in `registry.py` — ✅ DONE (`ingest.py`,
   stdlib only, handles `.csv`/`.gz`/`.zip`, resolves real column names across
   year vintages):
   - `load_provider_service` / `load_provider_summary` (CMS billing, by NPI).
   - `load_part_d`, `load_open_payments` (by NPI).
   - `load_usaspending` (by recipient UEI — org-level, see 2b).
   - `load_nppes` + `specialty_map` (NPI → specialty/state for pushforward).
   - `FlowCategoryBuilder` writes provenance (`reports`/`has_specialty`/`in_state`).
   - `write_fixtures()` + `run_coherence.py --demo-real` exercise it without
     downloads; 10 ingest tests pass.
   - **Headline real-data check wired:** CMS publishes billing as both line
     items AND a per-provider aggregate; summing line items to NPI is a
     pushforward that must equal the aggregate. `--service`/`--summary` runs it
     (real conservation check, same NPI key, no fabricated joins).
2. **Run Level-0/1 on one real year** (start 2022 or 2023) — NEXT. Download the
   two CMS files, run `python -m domains.flow.run_coherence --service <f>
   --summary <f> --nppes <f>`. Expect the provider→specialty pushforward to
   surface real CONTRADICT entities.
   - **2b. USASpending→NPI join**: USASpending is org-level (UEI), not NPI.
     Build org→facility(CCN)→NPI bridge before gluing the federal layer to
     providers; until then keep it as an org-level section.
3. **Medicare Advantage paid-vs-consumed 2-cell** — ✅ DONE
   (`medicare_advantage.py`). The novel, biggest number:
   - `paid` and `consumed` are parallel 1-morphisms `plan → coverage`; the
     `InfinityCosmos` auto-detects the pair and materializes the **2-cell** per
     contract (verified: N contracts → N 2-cells in h₂K). COG Tier 4.
   - paid = E·benchmark_pc·(risk·(1−coding_adj)); consumed = E·ffs_pc·ffs_risk.
   - **Provable decomposition**: overpayment = coding_intensity + benchmark_spread
     (exact identity, tested). Applies the statutory 5.9% coding haircut so the
     estimate is conservative.
   - Writes `paid::<c>`/`consumed::<c>` parallel morphisms + `plan -overpays->
     medicare` (confidence = overpayment ratio, dollars in metadata).
   - Run: `python -m domains.flow.run_coherence --ma` (synthetic) or
     `--ma <contracts.csv>`. Loaders: `load_ma_contracts`, `load_ma_enrollment`.
   - **REAL consumed side DONE** (`load_ffs_geovar` + `assemble_contracts_from_geovar`,
     `--ma-geovar <ffs_geovar.csv>`): per-state `ffs_per_capita` =
     `TOT_MDCR_STDZD_PYMT_PC` and `enrollment` = `BENES_MA_CNT` are now REAL CMS
     data (Original Medicare Geographic Variation PUF, 2014–2024). The denominator
     of the overpayment claim — the FFS baseline — is no longer assumed. On 2024:
     51 states, 33.0M enrollees, consumed $417.5B, paid $509.2B (MedPAC params),
     **overpayment ≈ $91.7B (~22% of FFS, $2,778/enrollee)** — matches MedPAC's
     ~122%-of-FFS finding; cosmos materializes 51 2-cells in h₂K.
   - **REAL benchmark DONE** (`load_ma_ratebook`, `--ma-ratebook <zip>`): the
     CMS MA ratebook ships county Parts A&B monthly capitation benchmarks as
     CSV inside `/files/zip/<year>-ma-rate-book.zip` (no xlsx parsing needed).
     Loader picks the quality-bonus tier (`--ma-bonus`, default 5% — most MA
     enrollment is in 4+ star plans), annualizes (x12), aggregates county→state.
   - **Enrollment-weighting DONE** (`load_ssa_fips_crosswalk` +
     `load_county_ma_enrollment`, `--ma-crosswalk <csv>`): ratebook is SSA-keyed,
     GeoVar county MA enrollment is FIPS-keyed; the NBER SSA↔FIPS crosswalk
     (`data.nber.org/ssa-fips-state-county-crosswalk/<year>/`) bridges them, so
     county benchmarks are weighted by real county MA enrollment (falls back to
     unweighted mean per state where enrollment is suppressed). 2024 results:
     unweighted paid $519.5B / overpay **$102.0B**; enrollment-weighted paid
     $524.9B / overpay **$107.3B** ($3,252/enrollee) — weighting shifts toward
     high-enrollment urban counties whose benchmarks sit further above FFS.
     Per-state ratios vary realistically (FL 8%, WA 36%, OR 39%).
   - **MA risk score: the one genuinely non-public input.** Per-geo MA risk is
     not a free public file (CMS uses restricted encounter/RAPS data; MedPAC
     estimates coding intensity nationally). `load_ma_risk` + `--ma-risk-file`
     slot real scores in when obtained; default stays the documented MedPAC
     1.20, with a loud note.
   - **Cross-check vs MedPAC/RADV/OIG DONE** (`validation.py`, auto-printed by
     `--ma-geovar`): encodes the published figures with citations — MedPAC 2025
     $84B (=$40B coding + $44B favorable selection, 20% above FFS), MedPAC 2024
     ~$83B/~22%; RADV ~$0.479B/yr (vacated by court Sept 2025) and HHS-OIG ~$7.5B
     as the much-smaller *enforcement* floor (not the economic total). Result:
     our default $107.3B = 1.28× MedPAC (SAME ORDER, high). **Calibrated** to
     MedPAC's net +10% coding (`--ma-risk 1.169`): **$93.8B = 1.12× MedPAC →
     CONSISTENT**, coding $41.8B ≈ MedPAC's $40B. i.e. an independent
     computation from real CMS data reproduces MedPAC within 12% using their
     coding parameter. **NEXT**: obtain real per-geo MA risk (the last
     non-public input); residual gap is benchmark-spread≠favorable-selection +
     benchmark-vs-standardized-FFS normalization.

### Phase 3 — Conflict of interest + outliers
4. **Open Payments ↔ Part D 2-cell**: correlate pharma payments to an NPI with
   that NPI's prescribing of the payer's drugs.
5. **Yoneda fingerprint outliers**: a provider's HCPCS/drug bag vs peer
   sheaf-section (specialty + region); flag divergence as overbilling risk.
   Reuse `core/formal_yoneda.py` (`yoneda_similarity`, transfer threshold).

### Phase 4 — Prices, OPTIMUS, product
6. **Hospital MRF coherence**: "same DRG, different price" across hospitals
   (stay on hospital files; payer TiC files are TB-scale).
7. **OPTIMUS** (`core/optimus.py`): factorize money morphisms to discover
   unnamed intermediaries (PBM rebate layers, intermediary billers).
8. **Ledger product**: daily job (CMS/USASpending updates) → re-emit ledger +
   dashboard. "Yesterday's leak, every morning." Candidate for a scheduled
   agent once stable.

### Phase 5 — Make it ONE graph, real, and verified (completing the picture)

The Phase 1–4 detectors are real but currently **isolated islands running on
synthetic data**. Phase 5 is the integration phase that turns them into one
connected, real, validated system — the actual categorical thesis.

**5a. The joins (highest value — this is the whole "it's all linked" claim).**
Today each layer is keyed by a different ID and they don't touch, so the graph
is 4 disconnected components, not one category. Build the bridges:
   - **NPI co-load**: load provider billing + Part D + Open Payments + NPPES
     into ONE `Category` on the shared NPI spine (keys already align; just not
     co-loaded). *Natural next build.*
   - **UEI → CCN → NPI**: federal (USASpending, org-level) → facility → provider.
     Without it the federal layer floats free (Phase 2b carried forward).
   - **contract_id → NPI**: MA plan → its provider network (network data is
     hard; may stay approximate).
   - **CCN spine**: hospital cost reports ↔ price transparency.

**5b. Vertical conservation (the real leak engine).** Today's check is
*horizontal* (two measurements of the same layer: line items vs aggregate). The
money shot is *vertical*: federal obligated → program spend → MA payment →
provider billing must reconcile DOWN the chain via pushforward/Kan along the
layer functor. Composite ≠ sum of parts across layers = the leak. Needs 5a first.

**5c. Real data for the still-synthetic layers.**
   - MA 2-cell: assemble real inputs (CPSC enrollment + rate-book benchmarks +
     Geographic Variation PUF FFS + risk scores); cross-check vs RADV/MedPAC.
   - Federal: run USASpending loader once the org→provider bridge exists.
   - Hospital (cost reports + MRF prices): no code yet; "same DRG, different
     price" is a sheaf-coherence problem.
   - Part D / Open Payments: loaders exist, never run on real files.

**5d. Detectors still to build or port** (see Math Arsenal below for what each
finds):
   - Open Payments ↔ Part D conflict-of-interest 2-cell (designed, not built).
   - Ricci curvature (bottleneck intermediaries) — port from GRID/III-CORE.
   - Persistent homology (anomalies over time) — port; needs multi-year data.
   - Horn-filling / retrodiction (infer missing transactions) — port PHARM/SEC.
   - Right Kan allocation (budget-constrained downward allocation) — in
     `categorical/`, wire to flow.
   - OPTIMUS factorization of money morphisms (PBM rebate layers) — Phase 4 item 7.
   - HoTT transport (carry a finding to all equivalent actors) — present, wire it.

**5e. Validation against ground truth (credibility = monetization).** Findings
are "hypotheses for review." Build a validation harness that scores flagged
entities against KNOWN published numbers — RADV recoveries, OIG/GAO improper-
payment reports, DOJ qui-tam settlements. This turns "interesting math" into a
trustworthy ledger. **STARTED**: `validation.py` cross-checks the MA national
total against MedPAC/RADV/OIG (calibrated estimate is CONSISTENT with MedPAC,
1.12×). Extend the same pattern to the provider/outlier/Nash detectors.

**5f. Wire the domain into the unified Agent.** Detectors currently call
`Category`/`cosmos` directly. Expose each as an Orion plugin so **COG verifies
every finding** (Tier 4 on the 2-cells) and **OPTIMUS refines the money graph**
automatically — closing the five-layer loop described in the root `CLAUDE.md`.

### Phase 6 — Time + product

Everything is single-year (currently D24 = 2024 CMS). Phase 6 adds the temporal
dimension and the delivery layer:
   - Multi-year ingestion (CMS publishes yearly; pull 2015–2024).
   - Temporal sheaves / streaming Kan for change detection year-over-year.
   - The delivery layer: daily job → ledger artifact → dashboard, packaged for
     the four buyers (payers, auditors, qui-tam attorneys, journalists).
     "Yesterday's leak, every morning."

**Fastest path to "complete picture":** (1) 5a NPI co-load + UEI→CCN→NPI — turns
4 islands into one category; (2) 5c real MA inputs + 5e cross-check vs
RADV/MedPAC — produces the validated headline number; (3) 5b vertical
conservation across the now-connected layers — the leak detector at full scope.

## Math arsenal — what each tool finds in the money graph

Each module detects a *different shape* of fraud/waste. They stack from
dimension 0 (find the suspect) up to dimension 3 (cross-layer interaction).

| Tool | In HCARE? | What it finds |
|---|---|---|
| **Sheaves** | yes (`coherence.py`, pronoia `sheaf_probe`) | H¹ ≠ 0 = a global contradiction sources can't reconcile; localizes the breaking entity. |
| **Yoneda distance** | yes (`core/formal_yoneda.py`) | Provider fingerprint = its bag of codes/drugs/payers. Far from the specialty centroid = bills unlike every peer = overbilling outlier. d≈0 across IDs = same actor (dedup). |
| **Fibrations** | yes (`cosmos`, `categorical/fibrations.py`) | `provider → specialty` fibration; cartesian lift transports the specialty norm down to each provider = properly risk-adjusted peer comparison. |
| **Right Kan ext.** | yes (`categorical/kan_extensions.py`) | Left Kan = pushforward (sum-up, used in conservation). Right Kan = constrained allocation downward: finest per-contract value consistent with a known budget; gap vs actual = anomaly. |
| **Nash equilibrium** | yes (`game/nash.py`, `open_games.py`) | Upcoding is a best response to CMS's payment rule. Observed coding ≫ Nash-honest = strategic gaming. Open games compose CMS→plan→provider; test policy counterfactuals. |
| **HoTT** | yes (`hott/`) | Entities equal up to a path (equivalence). Transport carries a proven finding to an equivalent actor; path induction proves a property over all equivalents. |
| **Ricci curvature** | port (have `grid_ricci`) | Ollivier-Ricci on the flow graph: negatively-curved edges = bottlenecks where money funnels through few intermediaries (PBM/shell billers). |
| **Horns** | port (PHARM/SEC) | Horn = partial simplex missing a face. Horn-filling/retrodiction infers the transaction that *should* exist but isn't recorded; `horns_vs_composition` flags inferred ≠ actual. |
| **Nash sheaves** | ✅ DONE (`nash_sheaf.py`) | NOVEL. Each market has a local equilibrium (a section). H¹ of the Nash sheaf = obstruction to a coherent global strategy = a plan playing inconsistent games across markets (strategic fraud invisible locally). |

Stacking: dim 0–1 (Sheaves → Yoneda → Fibrations → Ricci) finds + risk-adjusts
+ localizes the suspect; inference (Horns retrodict, Right Kan allocate, HoTT
transport) fills gaps; dim 2–3 (MA 2-cell + Level-2 OPTIMUS + SCM →
Nash/Nash-sheaf → gray-coherence 3-cell) explains *why* and catches cross-layer
interaction. See [[hcare-math-port-map]] in memory for source repos.

## Math to port into HCARE (not yet present in src/komposos_core)

HCARE currently has: `categorical` (19), `core` (26), `cog` (10), `hott` (5),
`game` (3), `zfc` (13), `cubical` (3), plus energy-specific
`komposos_wesys/geometry` (`grid_ricci`, `grid_spectral`). Port these generic
modules as the relevant phases need them:

| Math | Use in flow | Best source repo |
|---|---|---|
| `geometry/ricci.py`, `fast_ricci.py` | curvature of the money graph (bottlenecks) | `KOMPOSOS-III-CORE`, `KOMPOSOS-IV` |
| `geometry/spectral.py` | spectral anomaly on payment graph | `KOMPOSOS-III-CORE`, `KOMPOSOS-IV` |
| `topology/persistent_homology.py`, `persistent_sheaves.py` | persistent anomalies over time | `KOMPOSOS-III-CORE` |
| `core/gray_coherence*.py`, `categorical/gray_category.py` | gray-tensor coherence for multi-pathway reconciliation | `KOMPOSOS-MATH`, `KOMPOSOS-SEC` (richest) |
| `oracle/horns.py`, `horns_retrodiction.py`, `horns_vs_composition.py` | horn-filling retrodiction (infer missing edges) | `KOMPOSOS-IV-PHARM` (3 files), `KOMPOSOS-SEC` |
| `categorical/activity_system.py` + `oracle/activity_analysis.py` | Engeström activity theory on actors | `KOMPOSOS-IV-PHARM` |
| full `oracle/` (22 strategies) | inference / prediction layer | `KOMPOSOS-IV`, `KOMPOSOS-IV-PHARM` |
| `game/nash.py`, `open_games.py` | already present — verify vs PHARM version | (have it) |

**Reuse, don't rewrite, the sheaf machinery:** GRID's Phase-0 coherence ran on
`pronoia/sheaf_probe.py` + `domains/grid/sheaf_audit.py`; PHARM has
`operadum/.../sheaf_on_pharm_graph.py`. Phase 2 should lift those rather than
reinventing the gluing logic.

## Honest constraints

- 32 GB CPU laptop (no GPU). All wired sources are CPU-sized; avoid payer TiC
  files and patient-level T-MSIS/MA encounter data (restricted + huge).
- Findings are **hypotheses for review**, like grid's footprint candidates —
  CONTRADICT means "a source is wrong or a leak", not a proven fraud claim.
- The repo on disk is `komposos-power`; when the folder is renamed to HCARE,
  update paths. The package layout (`src/komposos_core`) is unchanged.

## How to resume

```bash
cd <repo>
python -m domains.flow.run_coherence --synthetic   # confirm Phase 1 works
python -m pytest domains/flow/tests/ -q
# then start Phase 2: write domains/flow/ingest.py loaders against registry.py
```
