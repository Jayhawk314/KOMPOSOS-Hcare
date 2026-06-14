# flow — Categorical Analysis of the U.S. Healthcare Money Graph

Domain package built on the KOMPOSOS-HCARE categorical runtime
(`core.category`). It treats federal healthcare spending, provider billing,
the insurance industry, and hospital prices as **one category**, not four
datasets — because the dollars literally flow along a chain of morphisms:

```
Treasury ──appropriates──▶ CMS ──pays──▶ Insurer (Medicare Advantage)
                                │                       │
                                │ (fee-for-service)     │ (capitated)
                                ▼                       ▼
                             Hospital / Provider (NPI) ──prescribes──▶ Patient
                                ▲
                                │ pays
                         Drug Manufacturer (Open Payments)
```

**Money conserves along composition.** Where the composite ≠ the sum of its
parts, that gap is the leak (waste / overpayment / fraud). This is the same
trick the `grid` domain used for energy waste — applied to dollars.

## Quick start

```bash
# planted-leak demo (no downloads):
python -m domains.flow.run_coherence --synthetic

# the data catalog we glue:
python -m domains.flow.run_coherence --registry

# Medicare Advantage paid-vs-consumed 2-cell (headline overpayment):
python -m domains.flow.run_coherence --ma              # synthetic
python -m domains.flow.run_coherence --ma contracts.csv

# Yoneda peer-outlier billing detection:
python -m domains.flow.run_coherence --outliers        # synthetic
python -m domains.flow.run_coherence --outliers cms_by_provider_and_service.csv

# Nash sheaf -- cross-market strategic-gaming detection:
python -m domains.flow.run_coherence --nash-sheaf      # synthetic

# real-schema loaders on generated fixtures (no downloads):
python -m domains.flow.run_coherence --demo-real

# tests:
python -m pytest domains/flow/tests/ -q
```

The synthetic demo plants two leaks and the engine finds them:
- `npi_over` — bills 9× what was federally obligated (overbilling outlier)
- `npi_ghost` — money obligated, ~nothing billed (ghost / vanished dollars)

## How the math maps on

| Engine piece | What it finds |
|---|---|
| **Sheaf gluing** (`coherence.FlowCoherenceChecker`) | same entity in two datasets that CONTRADICT → a leak |
| **Pushforward / left Kan** (`coherence.pushforward`) | aggregate provider → specialty; composite ≠ sum localizes the leak to the map |
| **2-cell reconciliation** (Phase 2) | MA *paid* vs *consumed* gap (insurance overpayment); Part D vs Open Payments (conflict of interest) |
| **Yoneda fingerprint** (Phase 3) | a provider's bag of HCPCS codes vs peers → overbilling outliers |
| **OPTIMUS** (Phase 4) | discovers unnamed intermediaries (PBM rebate layers, shell billers) |

## Verdicts

Per overlapping entity, by relative discrepancy:

- `GLUE` — ≤ tolerance; sources agree.
- `TENSION` — ≤ 5× tolerance; known-adjustment territory.
- `CONTRADICT` — > 5× tolerance; at least one source is wrong / a leak.

Results are written back into the `Category`:
- `source:A -coheres_with-> source:B`, confidence = agreement rate.
- `source:A -disputes-> entity:X`, confidence = discrepancy.

## Data sources

The full catalog with access notes and public/restricted status is in
`sources/registry.py`. All currently-wired sources are free and fit a 32 GB
CPU laptop. Patient-level T-MSIS Medicaid and MA encounter data are
restricted — we use public aggregates as proxies and flag the gap honestly.

## Status

Phase 1 (this scaffold) is complete: source registry + Level-0/Level-1
sheaf coherence + write-back + tests. The full roadmap is in `PLAN.md`.
