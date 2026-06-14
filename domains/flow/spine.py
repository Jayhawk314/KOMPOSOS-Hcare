# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""NPI co-load: join the NPI-keyed datasets into one category on the spine.

The flow domain's claim is that healthcare money is ONE category, not four
disconnected datasets. The NPI-keyed sources -- provider billing, Part D
prescribing, Open Payments pharma money -- are each a section of the money
presheaf over providers; NPPES gives the provider -> specialty/state functor.
Loading them on the shared NPI key turns four islands into one connected graph,
which is the precondition for every cross-source detector (the Open Payments x
Part D conflict-of-interest 2-cell, vertical conservation, Yoneda dedup).

Two separate concerns, deliberately split (the lesson from the 1.2M-provider
conservation run: per-insert SQLite does not scale):

  * coverage()  -- pure set math over the section keys. Full national scale,
    fast, no Category writes. This is the "it's all linked" evidence: how many
    NPIs appear in >=2 / all sources.
  * build()     -- writes a BOUNDED, interesting subset (multi-source providers,
    ranked by total money) into the Category as the joined structure detectors
    query via profile().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, List, Mapping, Optional

from domains.flow.coherence import Section

# Canonical money-source labels (match the ingest loaders' default `source=`).
SRC_BILLING = "cms_summary"
SRC_PART_D = "part_d"
SRC_OPEN_PAY = "open_payments"


@dataclass
class CoverageReport:
    total_npis: int
    per_source: Dict[str, int]
    in_k_sources: Dict[int, int]            # NPIs appearing in exactly k sources
    pair_overlap: Dict[str, int]            # "a&b" -> count
    all_sources_overlap: int                # in every money source
    with_specialty: int                     # also resolved in NPPES

    @property
    def multi_source(self) -> int:
        return sum(n for k, n in self.in_k_sources.items() if k >= 2)


class NPISpine:
    """Co-load NPI-keyed sections + NPPES into one Category on the NPI spine."""

    def __init__(self, category=None) -> None:
        self.category = category
        self._money: Dict[str, Dict[str, float]] = {}
        self._nppes: Mapping[str, Mapping[str, str]] = {}

    # -- ingestion (in-memory; no Category writes yet) -------------------
    def add_money_source(self, section: Section) -> "NPISpine":
        self._money[section.source] = dict(section.values)
        return self

    def set_nppes(self, nppes: Mapping[str, Mapping[str, str]]) -> "NPISpine":
        self._nppes = nppes
        return self

    # -- the join evidence (pure set math, full scale) ------------------
    def all_npis(self) -> set:
        out: set = set()
        for vals in self._money.values():
            out |= set(vals)
        return out

    def coverage(self) -> CoverageReport:
        sources = list(self._money)
        sets = {s: set(v) for s, v in self._money.items()}
        union = set().union(*sets.values()) if sets else set()

        in_k: Dict[int, int] = {}
        for npi in union:
            k = sum(1 for s in sources if npi in sets[s])
            in_k[k] = in_k.get(k, 0) + 1

        pair = {f"{a}&{b}": len(sets[a] & sets[b])
                for a, b in combinations(sources, 2)}
        all_ovl = len(set.intersection(*sets.values())) if sets else 0
        with_spec = len(union & set(self._nppes)) if self._nppes else 0

        return CoverageReport(
            total_npis=len(union),
            per_source={s: len(sets[s]) for s in sources},
            in_k_sources=in_k,
            pair_overlap=pair,
            all_sources_overlap=all_ovl,
            with_specialty=with_spec,
        )

    # -- write a bounded joined subgraph into the Category --------------
    def build(self, *, min_sources: int = 2, limit: int = 500) -> int:
        """Write the most cross-linked providers into the Category.

        Picks NPIs appearing in >= ``min_sources`` money sources, ranks them by
        total money across sources, keeps the top ``limit``, and writes for each:
        ``source:<s> -reports-> npi:<id>`` (amount in metadata) plus the NPPES
        ``has_specialty`` / ``in_state`` edges. Bounded so the per-insert backend
        stays fast. Returns the number of NPIs written.
        """
        if self.category is None:
            raise ValueError("build() needs a Category; pass one to NPISpine(...)")
        sources = list(self._money)
        sets = {s: set(v) for s, v in self._money.items()}
        union = set().union(*sets.values()) if sets else set()

        scored = []
        for npi in union:
            k = sum(1 for s in sources if npi in sets[s])
            if k < min_sources:
                continue
            total = sum(self._money[s].get(npi, 0.0) for s in sources)
            scored.append((total, npi))
        scored.sort(reverse=True)
        chosen = [npi for _, npi in scored[:limit]]

        cat = self.category
        for s in sources:
            cat.add(f"source:{s}", type_name="data_source")
        n = 0
        for npi in chosen:
            obj = f"npi:{npi}"
            if cat.get(obj) is None:
                cat.add(obj, type_name="provider")
            for s in sources:
                amt = self._money[s].get(npi)
                if amt is None:
                    continue
                cat.connect(f"source:{s}", obj, name="reports",
                            confidence=1.0, amount=round(amt, 2))
            rec = self._nppes.get(npi)
            if rec:
                spec = rec.get("specialty")
                state = rec.get("state")
                if spec:
                    sp = f"specialty:{spec}"
                    if cat.get(sp) is None:
                        cat.add(sp, type_name="specialty")
                    cat.connect(obj, sp, name="has_specialty")
                if state:
                    st = f"state:{state}"
                    if cat.get(st) is None:
                        cat.add(st, type_name="state")
                    cat.connect(obj, st, name="in_state")
            n += 1
        return n

    # -- unified per-provider view (reads the joined Category) ----------
    def profile(self, npi: str) -> Dict[str, object]:
        """One provider's joined view: money per source + specialty/state."""
        if self.category is None:
            raise ValueError("profile() needs a Category")
        obj = f"npi:{npi}"
        money: Dict[str, float] = {}
        for m in self.category.morphisms_to(obj):
            if m.name == "reports":
                src = m.source.replace("source:", "")
                money[src] = (m.metadata or {}).get("amount", 0.0)
        specialty = state = None
        for m in self.category.morphisms_from(obj):
            if m.name == "has_specialty":
                specialty = m.target.replace("specialty:", "")
            elif m.name == "in_state":
                state = m.target.replace("state:", "")
        return {"npi": npi, "money": money,
                "specialty": specialty, "state": state}


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def summarize(report: CoverageReport, *, source_labels: Optional[Dict[str, str]] = None) -> str:
    labels = source_labels or {}
    lines = []
    lines.append("NPI co-load: four islands -> one category on the NPI spine")
    lines.append("=" * 72)
    for s, n in report.per_source.items():
        lines.append(f"  {labels.get(s, s):<28} {n:>10,} NPIs")
    lines.append("-" * 72)
    lines.append(f"  union of all sources:        {report.total_npis:>10,} NPIs")
    lines.append(f"  appear in >=2 money sources: {report.multi_source:>10,}  "
                 f"({report.multi_source / report.total_npis:.1%} of union)"
                 if report.total_npis else "  (empty)")
    lines.append(f"  appear in ALL money sources: {report.all_sources_overlap:>10,}")
    if report.with_specialty:
        lines.append(f"  resolved to a specialty:     {report.with_specialty:>10,}")
    lines.append("")
    lines.append("  pairwise overlaps (the joins that make it one category):")
    for pair, n in sorted(report.pair_overlap.items(), key=lambda kv: -kv[1]):
        a, b = pair.split("&")
        lines.append(f"    {labels.get(a, a)} & {labels.get(b, b)}: {n:,}")
    lines.append("")
    lines.append("  in-k-sources distribution:")
    for k in sorted(report.in_k_sources):
        lines.append(f"    in {k} source(s): {report.in_k_sources[k]:,}")
    return "\n".join(lines)


def synthetic_sections():
    """Three small money sections + NPPES with deliberate overlap for the demo."""
    billing = Section("cms_summary", {
        "100": 500_000, "101": 300_000, "102": 1_200_000, "103": 80_000,
        "104": 640_000,
    }, layer="3-provider")
    part_d = Section("part_d", {
        "100": 220_000, "102": 980_000, "104": 410_000, "105": 60_000,
    }, layer="3-provider")
    open_pay = Section("open_payments", {
        "100": 45_000, "102": 120_000, "106": 5_000,
    }, layer="4-pharma")
    nppes = {
        "100": {"specialty": "Cardiology", "state": "TX"},
        "102": {"specialty": "Oncology", "state": "FL"},
        "104": {"specialty": "Internal Medicine", "state": "NY"},
    }
    return billing, part_d, open_pay, nppes
