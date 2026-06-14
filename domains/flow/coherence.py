# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Sheaf coherence for the healthcare money-flow graph.

Sheaf-theoretic framing
------------------------
Take the discrete site whose points are entities (providers keyed by NPI,
hospitals by CCN, plans by contract id). Each public dataset is a *section*
of the dollars presheaf over the subset of entities it covers. The gluing
condition -- sections agree on overlaps -- is the precise statement of
"these datasets describe the same money".

Level 0 (this module, :class:`FlowCoherenceChecker`):
    pairwise overlap agreement at entity granularity.

Level 1 (:func:`pushforward`):
    aggregate an entity-level section along a functor
    ``entity -> group`` (provider -> specialty/region, plan -> parent
    insurer) -- a pushforward / left Kan extension along the projection --
    and compare against an independent coarse measurement. Disagreement
    *there* but not at level 0 localizes the leak to the aggregation map
    itself (e.g. mis-attributed dollars), not the line items.

This is the money-conservation principle: dollars must conserve along
composition. Where the composite != sum of parts, that gap is the leak.

Verdicts per overlapping entity, by relative discrepancy:
    GLUE       <= tolerance         sections agree; gluable
    TENSION    <= 5x tolerance      known-adjustment territory
    CONTRADICT  > 5x tolerance      at least one source is wrong / a leak

When a Category is supplied, results are written back as structure:
    source:A -coheres_with-> source:B   confidence = agreement rate
    source:A -disputes->     entity:X   confidence = discrepancy
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Tuple

GLUE = "GLUE"
TENSION = "TENSION"
CONTRADICT = "CONTRADICT"

# A section maps entity id -> dollar amount.
Dollars = Dict[str, float]


@dataclass
class Section:
    """One dataset's view of the money graph: entity id -> dollars."""

    source: str
    values: Dollars
    layer: str = ""

    def entities(self) -> set:
        return set(self.values)

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self.values)


@dataclass
class EntityVerdict:
    entity: str
    source_a: str
    source_b: str
    value_a: float
    value_b: float
    discrepancy: float  # relative, in [0, 1+]
    verdict: str


@dataclass
class PairResult:
    source_a: str
    source_b: str
    overlap: int
    agreement_rate: float           # fraction of overlap that GLUEs
    verdicts: List[EntityVerdict] = field(default_factory=list)

    def contradictions(self) -> List[EntityVerdict]:
        return [v for v in self.verdicts if v.verdict == CONTRADICT]


def _relative_discrepancy(a: float, b: float) -> float:
    """Symmetric relative gap in [0, 1+]. 0 = identical."""
    denom = max(abs(a), abs(b))
    if denom == 0.0:
        return 0.0
    return abs(a - b) / denom


def _classify(disc: float, tol: float) -> str:
    if disc <= tol:
        return GLUE
    if disc <= 5.0 * tol:
        return TENSION
    return CONTRADICT


class FlowCoherenceChecker:
    """Pairwise sheaf-gluing check across money-graph sections.

    Parameters
    ----------
    tolerance:
        Relative discrepancy at or below which two sources are said to GLUE.
    category:
        Optional KOMPOSOS Category; when supplied, results are written back
        as ``coheres_with`` / ``disputes`` morphisms.
    max_disputes:
        Cap on how many ``disputes`` edges to persist per pair (the most
        significant by discrepancy). The Category backend commits per insert,
        so writing all contradictions does not scale to ~10^6 providers -- and
        only the largest divergences are useful as queryable structure anyway.
        Use ``None`` for no cap (small / synthetic data only).
    """

    def __init__(self, tolerance: float = 0.02, category=None,
                 max_disputes: Optional[int] = 200) -> None:
        self.tolerance = tolerance
        self.category = category
        self.max_disputes = max_disputes

    # -- core check ------------------------------------------------------
    def check_pair(self, a: Section, b: Section) -> PairResult:
        overlap = sorted(a.entities() & b.entities())
        verdicts: List[EntityVerdict] = []
        glued = 0
        for e in overlap:
            va, vb = a.values[e], b.values[e]
            disc = _relative_discrepancy(va, vb)
            verdict = _classify(disc, self.tolerance)
            if verdict == GLUE:
                glued += 1
            verdicts.append(
                EntityVerdict(e, a.source, b.source, va, vb, disc, verdict)
            )
        rate = glued / len(overlap) if overlap else 0.0
        result = PairResult(a.source, b.source, len(overlap), rate, verdicts)
        if self.category is not None:
            self._write_back(result)
        return result

    def check_all(self, sections: Iterable[Section]) -> List[PairResult]:
        secs = list(sections)
        results: List[PairResult] = []
        for i in range(len(secs)):
            for j in range(i + 1, len(secs)):
                results.append(self.check_pair(secs[i], secs[j]))
        return results

    # -- write-back to the Category -------------------------------------
    def _write_back(self, result: PairResult) -> None:
        cat = self.category
        sa = f"source:{result.source_a}"
        sb = f"source:{result.source_b}"
        cat.add(sa)
        cat.add(sb)
        cat.connect(
            sa, sb, name="coheres_with",
            confidence=round(result.agreement_rate, 4),
            overlap=result.overlap,
        )
        # Persist only the most significant disputes: the backend commits per
        # insert, so writing every contradiction does not scale, and the small
        # divergences are noise. Cap to the largest by discrepancy.
        contras = result.contradictions()
        if self.max_disputes is not None and len(contras) > self.max_disputes:
            contras = sorted(contras, key=lambda v: -v.discrepancy)[:self.max_disputes]
        for v in contras:
            ent = f"entity:{v.entity}"
            cat.add(ent)
            cat.connect(
                sa, ent, name="disputes",
                confidence=round(v.discrepancy, 4),
                value_a=v.value_a, value_b=v.value_b, against=result.source_b,
            )


# ---------------------------------------------------------------------------
# Level 1: pushforward along a functor entity -> group (money conservation)
# ---------------------------------------------------------------------------
def pushforward(
    section: Section,
    mapping: Mapping[str, str],
    *,
    source_suffix: str = "@group",
    layer: str = "",
) -> Section:
    """Aggregate an entity-level section along ``entity -> group``.

    This is the left Kan extension along the projection: dollars are summed
    into their group. Comparing ``pushforward(fine)`` against an independent
    coarse section is the money-conservation test.
    """
    grouped: Dollars = {}
    for entity, value in section.values.items():
        group = mapping.get(entity)
        if group is None:
            continue
        grouped[group] = grouped.get(group, 0.0) + value
    return Section(
        source=section.source + source_suffix,
        values=grouped,
        layer=layer or section.layer,
    )


def sections_from_records(
    records: Iterable[Mapping],
    *,
    source: str,
    key_field: str,
    value_field: str,
    layer: str = "",
    value_fn: Optional[Callable[[Mapping], float]] = None,
) -> Section:
    """Build a :class:`Section` from row dicts (CSV/JSON ingestion helper).

    Repeated keys are summed (e.g. one NPI with many HCPCS line items).
    """
    values: Dollars = {}
    for row in records:
        key = str(row[key_field])
        amount = float(value_fn(row)) if value_fn else float(row[value_field])
        values[key] = values.get(key, 0.0) + amount
    return Section(source=source, values=values, layer=layer)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def summarize(results: List[PairResult], *, top: int = 10) -> str:
    """Human-readable ledger. Reports the total gap over ALL contradictions
    (not just the displayed top-N) plus a direction breakdown that separates a
    source-coverage artifact (one side ~0) from genuine two-sided divergence.
    """
    lines: List[str] = []
    lines.append("flow coherence ledger")
    lines.append("=" * 64)
    total_contra = 0
    total_gap = 0.0          # over every contradiction, not just the displayed ones
    a_missing = b_missing = 0    # one side is 0 (coverage / suppression artifact)
    a_exceeds = b_exceeds = 0    # both nonzero, which side is larger
    for r in results:
        contra = r.contradictions()
        total_contra += len(contra)
        for v in contra:
            total_gap += abs(v.value_a - v.value_b)
            if v.value_a == 0.0:
                a_missing += 1
            elif v.value_b == 0.0:
                b_missing += 1
            elif v.value_a > v.value_b:
                a_exceeds += 1
            else:
                b_exceeds += 1
        lines.append(
            f"\n{r.source_a}  vs  {r.source_b}"
            f"   overlap={r.overlap:,}  agreement={r.agreement_rate:.0%}"
            f"  contradictions={len(contra):,}"
        )
        for v in sorted(contra, key=lambda x: -abs(x.value_a - x.value_b))[:top]:
            gap = abs(v.value_a - v.value_b)
            lines.append(
                f"   CONTRADICT  {v.entity:<16}"
                f"  {v.value_a:>14,.0f} vs {v.value_b:>14,.0f}"
                f"  (gap ${gap:,.0f}, {v.discrepancy:.0%})"
            )
    lines.append("\n" + "-" * 64)
    lines.append(f"contradictions: {total_contra:,}   total gap: ${total_gap:,.0f}")
    if total_contra:
        lines.append(
            f"  direction:  src-A=0 (B-only): {a_missing:,}   "
            f"src-B=0 (A-only): {b_missing:,}   "
            f"A>B: {a_exceeds:,}   B>A: {b_exceeds:,}"
        )
        lines.append(
            "  (one side ~0 = coverage/suppression artifact; a one-directional "
            "gap = systematic methodology, not fraud)"
        )
    return "\n".join(lines)
