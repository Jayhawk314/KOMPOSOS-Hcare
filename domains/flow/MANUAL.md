# The Healthcare Money Map — A Manual

### Finding waste in the U.S. healthcare money system by treating it as one connected map

**What this is:** a manual for a working tool that reads public U.S. healthcare
spending data and finds where the money doesn't add up. It explains, side by
side, (a) the plain-English idea anyone can follow and (b) the exact math
underneath, so a curious 12-year-old and a health economist can both use it.

---

## 0. How to read this manual (two tracks)

Every important section has two parts:

- 🟢 **In plain words** — no math, no jargon. Read just these and you'll
  understand the whole thing.
- 🔵 **The math** — the precise version for engineers, economists, and
  mathematicians.

You can read only the green parts and still "get it." The blue parts are there
when you want to check the work or build on it.

There is a **Glossary** at the end (Section 12) that defines every technical
word in one plain sentence.

---

## 1. The one-sentence idea

🟢 **In plain words:** All the money in U.S. healthcare — what the government
pays, what hospitals and doctors bill, what insurance companies receive, what
drug companies pay — is really *one big connected web*, not separate piles. If
you lay it out as one map and add the money up along every path, the places
where the totals *don't match* are where money is being wasted, overpaid, or
lost. This tool builds that map and points at the mismatches.

🔵 **The math:** We model the healthcare money system as a single **category**.
Objects are entities (a provider, a plan, a county, a data source); morphisms
are money relationships between them; composition is "following the money along
a path." Each public dataset is a **section of a presheaf** (a partial view) of
the same underlying money. The **sheaf gluing condition** says these partial
views must agree where they overlap. **Money conservation** is the statement
that the value of a composite morphism equals the appropriate sum of its parts
(a functor preserves the monoidal sum). Wherever *composite ≠ sum of parts*,
that gap is the leak.

---

## 2. The problem, and why it's worth tens of billions of dollars

🟢 **In plain words:** The U.S. spends about $1.5 trillion a year through
Medicare and Medicaid. Independent government watchdogs estimate that **$80–100
billion every year** is improper — overpayments, billing that doesn't match the
records, or payment rules that quietly favor insurers. The data to *see* a lot
of this is already public. The problem is that it's scattered across dozens of
separate files that nobody connects. So the waste hides in the seams *between*
the datasets.

🔵 **The math:** The information-theoretic problem is that each dataset is a
*local* observation; fraud and waste live in the *global* inconsistencies that
no single local view reveals. Detecting them requires gluing local sections
into a global object and measuring the **obstruction to gluing** (formally, a
nonzero first sheaf cohomology class, H¹ ≠ 0). The categorical framing makes
those obstructions computable and *localizable* — it tells you *which entity*
breaks the gluing, not just that something is wrong.

---

## 3. The core insight: money is a category

🟢 **In plain words:** Think of every doctor, hospital, insurance plan, and
government program as a *dot*. Whenever money flows from one dot to another,
draw an *arrow* and write the dollar amount on it. Now you have a map made of
dots and arrows. The magic rule: **if you follow arrows in a chain, the money
should be consistent the whole way.** Government pays a plan, the plan pays
doctors, doctors bill for care — follow that chain and the numbers should line
up. When they don't, you've found something.

The same doctor shows up in many datasets (their billing, their prescriptions,
the payments drug companies gave them). Those are the *same dot* seen from
different angles. Connecting them is what turns scattered files into one map.

🔵 **The math:** Let **𝒞** be the money category. For objects A, B, a morphism
*f: A → B* carries a dollar value *w(f)* (the enrichment / hom-value, here a
quantale-valued weight). Composition `g ∘ f: A → C` combines weights under the
monoidal product. A **functor** *F: 𝒞 → 𝒟* coarse-grains the map (e.g.
provider → specialty, county → state) and must preserve the relevant sums
(a **left Kan extension / pushforward** along the projection). The identity that
"the same doctor across datasets is one object" is enforced by keying every
section on a shared identifier (NPI, CCN, contract-id) — the join is literally
the categorical identification of objects.

This is implemented on top of a general categorical runtime (`core/category.py`)
that stores objects, weighted morphisms, composition, and path-finding.

---

## 4. The conservation principle (and our first real finding)

🟢 **In plain words:** Here's the simplest version of the rule. Medicare
publishes doctors' billing two ways: as a big itemized list (every service), and
as a per-doctor total. If you add up the itemized list for a doctor, it should
equal that doctor's published total. We did this for **all 1.2 million doctors
in 2024**. The itemized lists added to **$97.3 billion**; the official totals
said **$120.1 billion**. A **$20 billion gap.**

But here's the honest part — and why honesty is built into the tool: the gap is
*entirely one-directional*. The itemized list is *never* bigger than the total;
it's *always* smaller. That one-sidedness is the fingerprint of a known data
rule (Medicare hides any line used by fewer than 11 patients for privacy), not
fraud. Real fraud would be messy and go both ways. So the tool flags the gap
**and tells you it's a data artifact, not theft.** That trustworthiness is the
whole point: a tool that cries fraud at everything is useless.

🔵 **The math:** Two sections *s_line, s_agg : NPI → ℝ≥0* of the billing
presheaf. The line-item section pushed forward to provider level is
Σ_HCPCS (avg_payment × services). Conservation requires *s_line(npi) =
s_agg(npi)* up to tolerance τ. We classify each NPI by relative discrepancy
*d = |a−b| / max(a,b)*: GLUE (d ≤ τ), TENSION (τ < d ≤ 5τ), CONTRADICT (d > 5τ).
For 2024: 199k GLUE, 394k TENSION, 615k CONTRADICT, total gap ≈ $20B. The
**direction test** — sign of (a−b) across all contradictions — returned
*B>A: 614,815; A>B: 0*. A strictly one-signed residual is diagnostic of a
*systematic* mechanism (small-cell suppression: the line-item presheaf omits
sections with <11 beneficiaries), distinguishable from the two-sided noise that
genuine billing fraud produces. (Code: `coherence.py`; the `summarize()`
direction breakdown encodes exactly this test.)

---

## 5. The detectors

Each detector finds a *different shape* of problem. Think of them as different
specialist doctors examining the same patient (the money system).

### 5.1 Sheaf coherence — "do the receipts add up?"

🟢 **In plain words:** Checks whether two datasets that describe the same money
actually agree. Disagreements are flagged and ranked by dollar size.
**Status: working on real national data.** (See Section 4.)

🔵 **The math:** Pairwise gluing check across presheaf sections at entity
granularity (Level 0) and after pushforward along a functor (Level 1, e.g.
provider→specialty). Disagreement at Level 1 but not Level 0 localizes the leak
to the *aggregation map* (mis-attributed dollars) rather than the line items.

### 5.2 The Medicare Advantage "paid vs consumed" 2-cell — the headline number

🟢 **In plain words:** Medicare Advantage is private insurance paid by the
government. There are two ways to value a plan's year: **what the government
paid the plan**, and **what that same care would have cost** under regular
Medicare. These are two arrows between the same two dots. The *gap between the
two arrows* is the overpayment.

We computed it for **all 51 states using real 2024 data**: the government paid
about **$525 billion**; the same people would have cost about **$418 billion**
under regular Medicare. That's a **~$107 billion overpayment** — about **$3,250
per enrollee per year.** And the gap isn't the same everywhere: it's 8% in
Florida but 35–39% in Washington and Oregon, because the payment formula treats
regions differently. That variation is real signal, not noise.

🔵 **The math:** `paid` and `consumed` are *parallel 1-morphisms*
`plan → coverage`. The system's ∞-cosmos layer (Riehl–Verity) auto-detects the
parallel pair and materializes the **2-cell** (a morphism-of-morphisms) between
them — one per contract/state, verified in the homotopy 2-category h₂𝒦 (COG
Tier 4 reasoning). Magnitudes:

```
paid     = E · bm · er,   er = risk · (1 − coding_adj)     (coding_adj = 5.9%, statutory)
consumed = E · ffs · fr
overpayment = paid − consumed
```

with E = enrollment, bm = benchmark per-capita (real CMS ratebook), ffs = FFS
per-capita (real Geographic Variation PUF), risk = MA risk score, fr = FFS risk
baseline. The overpayment **decomposes exactly** (a provable identity, unit-
tested):

```
overpayment = coding_intensity + benchmark_spread
coding_intensity = E · ffs · (er − fr)
benchmark_spread = E · (bm − ffs) · er
```

**Status: real consumed side, real benchmark (enrollment-weighted via an
SSA↔FIPS crosswalk), validated.** The one non-public input is the per-geography
MA risk score (CMS computes it from restricted encounter data); it defaults to
the documented MedPAC figure and accepts a real file when available.

### 5.3 Yoneda peer outliers — "which doctor bills unlike everyone else?"

🟢 **In plain words:** Give each doctor a "fingerprint" = the mix of services
and drugs they bill. Compare each doctor to the typical fingerprint for their
specialty and region. A doctor whose fingerprint is wildly different from every
peer is an overbilling risk worth a look. (The same trick spots when two
ID numbers are secretly the *same* actor — their fingerprints are identical.)

🔵 **The math:** A provider's fingerprint is its co-Yoneda data
*Hom(provider, −)* = the set {HCPCS code ↦ dollars}. Distance is the formal
**Yoneda distance** (weighted Jaccard): *d(y(A), y(B)) = |y(A) △ y(B)| /
|y(A) ∪ y(B)|*, a proven metric with *d = 0 ⇔ A ≅ B* (isomorphism). Outliers are
providers far from their specialty's fiber consensus (the fibration transports
the specialty norm down to each provider — proper risk-adjusted peer
comparison). **Status: working; demonstrated on synthetic peers (real-data run
is wired through `load_provider_fingerprints`).**

### 5.4 Nash sheaf — "is a plan gaming the system on purpose?"

🟢 **In plain words:** In each local market, there's a "smart" amount of
aggressive coding a plan can do given how often it gets audited. If a plan's
coding swings wildly across markets **and** those swings line up with where
gaming pays off, that's not noise — that's strategy. The clever part: a plan
that's just *noisy* everywhere is **not** flagged; only a plan whose
inconsistency is *incentive-aligned* is. This separates real strategic fraud
from random variation.

🔵 **The math:** Per market, a plan-vs-CMS inspection game yields a continuous
local Nash coding intensity. A plan's strategy across markets is a **section of
a sheaf**; the obstruction to a globally coherent strategy is the sheaf-Laplacian
energy *H¹ = xᵀLx = Σ w(x_v − x_u)²* (zero for a constant/coherent policy). A
plan is flagged only when cross-market variance is high **and** correlation with
the local Nash intensity is high — i.e. the incoherence is strategic, not
stochastic. This is a genuinely novel detector (game theory ⊗ sheaf theory).
**Status: working on synthetic markets.**

### 5.5 NPI co-load — the join that makes it one map

🟢 **In plain words:** This is the step that connects the islands. A doctor's
billing, their drug prescriptions, and the payments drug companies gave them are
three separate files — but the *same doctor*. We put them on one map keyed by
the doctor's ID number. On real 2024 data: **1.3 million doctors bill Medicare,
1.4 million prescribe drugs, and 861,300 do both** — that overlap is the proof
that it really is one connected system. The doctors who appear in *all* the
money files (bill + prescribe + take drug-company money) are exactly the ones
worth examining for conflicts of interest.

🔵 **The math:** Co-load identifies objects across sections by shared NPI key
(the categorical identification). `coverage()` computes the join purely as set
operations at full scale (no persistence cost): per-source cardinalities,
pairwise intersections, the in-k-sources distribution, and the global
intersection. `build()` writes only a bounded, high-value subgraph (multi-source
providers ranked by money) to keep the persistence backend's per-insert cost
sane; `profile(npi)` returns the unified per-provider view from the joined
graph. **Status: working on real national data (billing + Part D).**

### 5.6 Conflict-of-interest — "do paid doctors prescribe more?"

🟢 **In plain words:** Drug companies report the money they give doctors (Open
Payments); Medicare reports what each doctor prescribes (Part D). Put both on the
same doctor and ask: do the doctors who take the most industry money also
prescribe the most? On **real 2024 data across 734,802 doctors who appear in
both**, the answer is yes — there's a clear positive link, and **19,291 doctors
land in the top tenth of BOTH** (most money received *and* most prescribing).
Those are the conflict-of-interest candidates worth a closer look. The tool is
careful to say this is an *association*, not proof that the money caused the
prescribing.

🔵 **The math (NPI-level):** Two parallel evidence morphisms reach each provider
— *payment* (pharma → provider, Open Payments $) and *prescribing* (provider →
drugs, Part D $). As parallel 1-morphisms `provider → influence`, the cosmos
materializes a **2-cell** per flagged provider. The population signal is the
**Spearman rank correlation** between payment and prescribing (+0.305 over
734,802 providers in 2024 — robust at that n). Providers in the top decile of
*both* are flagged (19,291 in 2024).

🟢 **The sharper, drug-level version (built):** The NPI-level link could be
explained away (paid doctors might just have sicker patients). So we tightened
it: for *each specific drug*, compare doctors the maker **paid about that drug**
against doctors who prescribe the same drug but **weren't paid**. Across **396
drugs in 2024, the paid doctors prescribe a median 1.25× more — and 1.79× more
weighted by volume.** For big-name drugs: FARXIGA 1.70×, JARDIANCE 1.68×,
MOUNJARO 1.47×, antipsychotics like CAPLYTA 1.51× and REXULTI 1.46×. Because it
holds the drug fixed, this is the textbook conflict-of-interest pattern.

🔵 **The math (drug-level):** Aggregate to `{(npi, drug): payment}` (Open
Payments primary product, Drug/Biological only) and `{(npi, drug): cost}` (Part
D by Provider and Drug, brand-normalized). For each drug *d*, the **lift** is
mean prescribing over paid providers ÷ mean over unpaid providers of *d*. For a
matched (provider, drug) pair the payment and prescribing morphisms are parallel
`provider → drug:⟨d⟩` (same source **and** target), so the cosmos materializes a
genuine 2-cell per pair. 2024: 475,443 matched pairs, 396 drugs, median lift
1.25×, prescribing-weighted lift 1.79×, 127,821 flagged pairs. **Status: working
on real national data, both NPI-level and drug-level.**

### 5.7 Hospital price coherence — "same procedure, wildly different price"

🟢 **In plain words:** A DRG is a standard bucket of hospital care (e.g. "joint
replacement"). For the same bucket, hospitals should charge and be paid roughly
the same once you account for region. They don't. On **real 2024 data (2,906
hospitals, 540 DRGs)** the *sticker* price for the same DRG varies up to **23×**
across hospitals, and hospitals were paid **$4.0 billion above their same-state
peers for the identical DRG**. The honest catch: the top of that list is big
teaching hospitals doing the most complex cases (ECMO, severe sepsis) — so the
tool flags it for review and *says* case complexity may explain a lot, rather
than crying waste.

🔵 **The math:** Over the Medicare Inpatient PUF (CCN × DRG), each DRG's price
is a section over hospitals; coherence = it glues (low dispersion after regional
adjustment). Two readouts: (1) **chargemaster dispersion** = p90/p10 of submitted
charge per DRG; (2) **payment excess** = a hospital above its same-state peer
median for the DRG, excess = (payment − peer median) × discharges (the
ledger-contributing metric). Keyed by CCN, this starts the **hospital (CCN)
spine**. **Status: working on real national data** (centralized Inpatient PUF;
per-hospital negotiated-rate MRFs are a future ingestion refinement).

---

## 6. The findings ledger (real numbers)

| Finding | Number | Status | Honest caveat |
|---|---|---|---|
| Billing line-items vs per-doctor totals (2024) | $97.3B vs $120.1B, ~$20B gap | **real, national** | One-directional → data-suppression artifact, **not** fraud |
| Medicare Advantage overpayment (2024) | **~$107B** ($3,250/enrollee) | **real consumed + real benchmark** | MA risk score is the one modeled input |
| Same, calibrated to MedPAC's coding figure | **$93.8B = 1.12× MedPAC** → CONSISTENT | **validated** | within 12% of the official estimate |
| Doctors who both bill & prescribe (2024) | **861,300** of 1.85M | **real, national** | the join that makes it one map |
| Pharma payment ↔ prescribing link (2024, NPI-level) | **+0.305** Spearman over 734,802 doctors; **19,291** flagged | **real, national** | association, not causation |
| Drug-level lift: paid vs unpaid prescribers of the *same drug* (2024) | **1.25× median, 1.79× weighted** across 396 drugs; 127,821 flagged pairs | **real, national** | drug-controlled; still association, not causation |
| Hospital price: paid above same-state peers, same DRG (2024) | **$4.0B**; charge dispersion up to 23x | **real, national** | case-mix/teaching/DSH/wage-index may explain; review |
| Peer-outlier & strategic-gaming detectors | — | **working, synthetic data** | wired for real data, not yet run at scale |

**The point of the ledger is not one big scary number.** It's a *repeatable,
auditable, honest* pipeline: every figure is reproducible from public files with
one command, and every figure carries its own caveat.

### 6.1 The unified ledger — the product surface

🟢 **In plain words:** One command (`--ledger`) runs every detector, puts all
their findings into a single ranked list, scores each by how confident we are,
and writes one file. The 2024 run produced **387 findings totaling $146 billion
at stake**, sorted so the most important, most-trustworthy items are on top and
the known data-artifact sinks to the bottom. The top rows are the 51 state-level
Medicare Advantage overpayments and the biggest drug conflicts — **ELIQUIS
$3.3B, OZEMPIC $2.1B, JARDIANCE $1.5B** of prescribing-excess associated with
industry payments — each line tagged HIGH/MEDIUM/LOW and carrying its own
caveat. This is the "yesterday's leak, every morning" artifact.

🔵 **The math/output:** `ledger.py` normalizes each detector into a `Finding`
(detector, entity, dollars, confidence, basis, caveat), ranks by
priority = dollars × confidence, totals by detector and confidence tier, and
emits CSV + JSON. Confidence is a documented review-priority weight (MA 0.70
validated; drug-conflict 0.55; one-directional billing gap auto-driven to 0.05).
2024 assembled: HIGH $107.3B (MA), MEDIUM $18.8B (333 drugs), LOW $20.0B
(artifact). Run: `python -m domains.flow.run_coherence --ledger <data flags>`.

---

## 7. Validation — does it match the official watchdogs?

🟢 **In plain words:** A tool that invents numbers is worthless. So we check our
numbers against the official ones. The government's own advisory body (MedPAC)
estimated Medicare Advantage was overpaid by **$84 billion** in 2025. Our
independent calculation, using their published coding figure, lands at **$93.8
billion — within 12%.** We arrived there from raw public files, completely
separately. That agreement is the credibility.

We're also careful about a trap: the amount *overpaid* (~$84B) is very different
from the amount auditors can legally *claw back* (the RADV audit program, about
$0.5B/year — and even that was struck down in court in 2025). The tool keeps
those two ideas separate so nobody confuses "economic waste" with "recoverable
dollars."

🔵 **The math:** `validation.py` encodes published benchmarks with citations and
scores our estimate by dollar-ratio and percentage-point bands, distinguishing
*economic* (MedPAC) from *enforcement* (RADV/OIG) figures. Calibrating the one
free parameter (MA risk) to MedPAC's net +10% coding yields total $93.8B
(ratio 1.12, verdict CONSISTENT) with coding component $41.8B vs MedPAC's $40B.
The residual is attributable to a decomposition difference (our *benchmark
spread* vs MedPAC's *favorable selection*) plus benchmark-vs-standardized-FFS
normalization — both documented, neither hidden.

---

## 8. The data (all public, all free)

| Layer | Dataset | Key | Used for |
|---|---|---|---|
| Provider billing | CMS Physician & Other Practitioners (by Provider, by Service) | NPI | conservation, outliers |
| Prescribing | Medicare Part D Prescribers | NPI | co-load, (future) conflict 2-cell |
| Pharma payments | CMS Open Payments | NPI | (future) conflict 2-cell |
| Insurance | MA ratebook (county benchmarks) + FFS Geographic Variation PUF | state/county | MA 2-cell |
| Identity | NPPES, SSA↔FIPS crosswalk (NBER) | NPI / county | specialty join, benchmark weighting |
| Federal | USASpending HHS obligations | UEI | (future) vertical conservation |

Everything fits on a normal laptop. The full catalog with download URLs and
join keys lives in `sources/registry.py`.

---

## 9. How to run it

```bash
# Confirm everything works (no downloads needed)
python -m pytest domains/flow/tests/ -q          # 88 tests

# Each detector on built-in demo data:
python -m domains.flow.run_coherence --synthetic     # conservation
python -m domains.flow.run_coherence --ma            # MA overpayment
python -m domains.flow.run_coherence --outliers      # Yoneda peer outliers
python -m domains.flow.run_coherence --nash-sheaf    # strategic gaming
python -m domains.flow.run_coherence --coload        # the NPI join
python -m domains.flow.run_coherence --conflict      # Open Payments x Part D (NPI-level)
python -m domains.flow.run_coherence --conflict-drug # ... drug-level (paid vs unpaid per drug)
python -m domains.flow.run_coherence --hospital      # hospital price coherence (same DRG, diff price)
python -m domains.flow.run_coherence --ledger        # THE UNIFIED LEDGER (all detectors -> one file)

# On real downloaded data (examples):
python -m domains.flow.run_coherence --service <by-service.csv> --summary <by-provider.csv>
python -m domains.flow.run_coherence --ma-geovar <ffs_geovar.csv> \
       --ma-ratebook <ma-rate-book.zip> --ma-crosswalk <ssa_fips.csv>
python -m domains.flow.run_coherence --coload --summary <billing.csv> --part-d <partd.csv>
```

Every real run prints its data provenance and, for the MA run, the automatic
cross-check against MedPAC/RADV/OIG.

---

## 10. How to expand it — toward solutions for the whole system

🟢 **In plain words:** Right now this maps Medicare money and finds overpayments.
The same map can do a lot more, because *every* kind of healthcare problem is
some version of "the numbers don't line up" or "this actor behaves unlike its
peers." Here's what plugging in more data unlocks:

🔵 **The math + the build path:**

1. **Conflict-of-interest 2-cell (✅ built, Section 5.6).** Done on real national
   data at both NPI level and drug level (paid-vs-unpaid prescribing of the same
   drug, 396 drugs). *Further refinement:* causal designs (difference-in-
   differences around payment timing, provider fixed effects). *Solution it
   enables:* flag prescribing driven by payments, not need.

2. **Vertical conservation (the big one).** Today's checks are *horizontal* (two
   views of one layer). Connect the layers — federal $ → program → plan →
   provider — via the bridges (UEI→CCN→NPI) and push money down the chain with
   Kan extensions. *Solution:* catch dollars that enter the top and vanish before
   reaching care.

3. **Hospital prices.** Hospital price-transparency files make "same procedure,
   wildly different price" a sheaf-coherence problem across hospitals.
   *Solution:* a public fair-price reference.

4. **Curvature & bottlenecks (Ricci flow).** Ollivier–Ricci curvature on the
   money graph finds edges where dollars funnel through a few intermediaries
   (PBMs, shell billers). *Solution:* expose hidden middlemen.

5. **Time & forecasting.** Multi-year ingestion + temporal sheaves /
   persistent homology detect anomalies that persist or emerge over time.
   *Solution:* "yesterday's leak, every morning" — a daily ledger.

6. **Retrodiction (horn-filling).** Infer transactions that *should* exist but
   aren't recorded (a missing simplex face). *Solution:* surface ghost billing.

7. **Self-refinement (OPTIMUS) + verification (COG).** The system can factorize
   its own money-morphisms to discover unnamed intermediaries, and verify every
   finding through tiered reasoning (up to category-theoretic and set-theoretic
   proof). *Solution:* findings that come with their own audit trail.

**Beyond Medicare:** the exact same engine works for Medicaid, commercial
insurance, drug-supply pricing, hospital cost reports, even non-healthcare money
graphs (energy, defense procurement) — anywhere money flows through a network
that *should* conserve. The grid-energy version of this engine already printed
real numbers; healthcare is the same template on a different dataset.

---

## 11. Honest limitations (read this before quoting any number)

- **Findings are hypotheses for review, not proven fraud.** CONTRADICT means
  "a source is wrong, or money leaked," which includes innocent explanations
  (data rules, timing, legitimate adjustments).
- The big billing gap (Section 4) is **mostly a privacy-suppression artifact**,
  by the tool's own one-directional test. We say so loudly.
- The MA overpayment uses **one modeled input** (per-geography MA risk score)
  because CMS doesn't publish it; the number moves with that assumption, and the
  tool shows the calibration explicitly.
- Two detectors (outliers, Nash sheaf) are **proven in code but not yet run at
  national scale**.
- Restricted data (patient-level claims, MA encounter data) is deliberately
  **not** used; we use public aggregates and say where that limits precision.

---

## 12. Glossary (one plain sentence each)

- **Category** — a map of dots (objects) and arrows (relationships) where arrows
  can be chained.
- **Morphism** — an arrow; here, a money relationship between two things.
- **Composition** — following arrows in a chain (e.g. money flowing along a path).
- **Functor** — a consistent way to zoom out the map (provider → specialty)
  that preserves structure.
- **Pushforward / Kan extension** — adding money up when you zoom out; the result
  must match an independent total.
- **Sheaf / gluing** — the rule that overlapping partial views of the same thing
  must agree; failure to agree localizes a problem.
- **Cohomology (H¹)** — a measure of how badly the views *can't* be reconciled;
  nonzero means a real global contradiction.
- **2-cell** — an arrow *between two arrows*; here, the gap between "paid" and
  "consumed."
- **Yoneda distance** — how different two things are by the company they keep
  (their relationships); zero means they're effectively identical.
- **Fibration** — structure that lets you compare each provider against the norm
  for its own peer group (risk-adjusted).
- **Nash equilibrium** — the "smart play" each actor settles into given everyone
  else's behavior.
- **Quantale / enrichment** — the bookkeeping that lets arrows carry weights
  (dollars, confidence) and combine correctly.
- **NPI / CCN / contract-id** — the ID numbers that let us recognize the same
  doctor / hospital / plan across different files.
- **FFS (fee-for-service)** — traditional Medicare, the cost yardstick we compare
  private plans against.
- **MedPAC / RADV / OIG** — the official bodies whose published numbers we check
  ourselves against.

---

*Built on KOMPOSOS — a categorical AI runtime. The healthcare money map lives in
`domains/flow/`. Roadmap and component status: `domains/flow/PLAN.md`. This
manual describes what is built and run as of June 2026; every real number here
is reproducible from public data with the commands in Section 9.*
