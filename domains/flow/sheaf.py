# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Cohomological coherence -- the LOAD-BEARING version of the conservation check.

`coherence.py` compares sources pairwise with an arbitrary tolerance and, on the
2024 billing data, flagged ~615k providers simply because the line-item side is
systematically below the aggregate (small-cell suppression). That is a threshold
artifact, not a finding.

This module replaces the threshold with a *cellular sheaf* (ported from the grid
domain's sheaf_audit, running on the in-repo scalar sheaf solver
`komposos_wesys.validation.thermodynamic_probe`):

  * one gauge node per data source / money view;
  * one edge per shared entity asserting  value_low = ratio * value_high.

The sheaf Laplacian's smallest eigenvalue is the **H1 obstruction**: it is ~0
iff a SINGLE global calibration reconciles every entity's ratio (the sources
glue up to one gauge), and the minimizing eigenvector IS that calibration. So:

  * a systematic, source-wide scale (e.g. the suppression that makes line-items
    ~0.81 x aggregate) is absorbed into the GAUGE, not flagged;
  * per-edge residuals localize exactly the entities that no global gauge can
    reconcile -- the genuine outliers -- with NO tolerance parameter;
  * with >=3 sources forming a cycle, this detects a global inconsistency that
    pairwise comparison provably cannot see.

The eigendecomposition does the work; nothing here is decorative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from komposos_wesys.validation.thermodynamic_probe import ThermodynamicSheaf

from domains.flow.coherence import Section


@dataclass
class SheafOffender:
    entity: str
    source_high: str
    source_low: str
    ratio: float          # value_low / value_high in (0, 1]
    gauge_ratio: float    # the global gauge's expected low/high ratio
    residual: float       # energy contribution: how far this entity breaks the gauge


@dataclass
class SheafResult:
    energy_leak: float                 # H1 obstruction (0 = one global gauge fits all)
    stable: bool
    n_edges: int
    n_skipped: int
    gauge: Dict[str, float]            # source -> fused calibration value (eigenvector)
    offenders: List[SheafOffender] = field(default_factory=list)

    def summary(self, top: int = 12) -> str:
        lines = []
        lines.append("Sheaf coherence -- H1 gauge over the money views")
        lines.append("=" * 72)
        verdict = ("one global gauge reconciles all sources (stable)"
                   if self.stable else "NO global gauge fits -- real obstruction")
        lines.append(f"  H1 energy leak: {self.energy_leak:.3e}  ({verdict})")
        lines.append(f"  {self.n_edges:,} ratio edges, {self.n_skipped:,} skipped "
                     "(non-positive)")
        lines.append("  gauge (calibration eigenvector): "
                     + ", ".join(f"{s}={v:+.4f}" for s, v in sorted(self.gauge.items())))
        lines.append("")
        lines.append(f"  top {top} obstruction entities (deviate most from the "
                     "global gauge):")
        for o in self.offenders[:top]:
            lines.append(
                f"    {o.entity:<16} {o.source_low}/{o.source_high} ratio "
                f"{o.ratio:.3f} vs gauge {o.gauge_ratio:.3f}  residual {o.residual:.2e}")
        lines.append("-" * 72)
        lines.append("  systematic source-wide scale is absorbed into the gauge; "
                     "only deviations\n  from it are flagged -- parameter-free, "
                     "unlike the tolerance threshold.")
        return "\n".join(lines)


def sheaf_coherence(sections: List[Section], *,
                    stable_leak: float = 1e-8) -> SheafResult:
    """Audit Sections for a single global gauge; localize H1 obstructions.

    Each pair of sources contributes one edge per shared entity asserting
    value_low = ratio * value_high (ratio in (0,1]). Returns the H1 energy leak,
    the gauge (eigenvector), and entities ranked by how badly they break it.
    """
    sheaf = ThermodynamicSheaf()
    for s in sections:
        sheaf.add_node(s.source)

    edge_meta = []     # (entity, high, low, ratio)
    n_skipped = 0
    for i in range(len(sections)):
        for j in range(i + 1, len(sections)):
            a, b = sections[i], sections[j]
            for entity in a.entities() & b.entities():
                va, vb = a.values[entity], b.values[entity]
                if va <= 0 or vb <= 0:
                    n_skipped += 1
                    continue
                if vb <= va:
                    high, low, ratio = a.source, b.source, vb / va
                else:
                    high, low, ratio = b.source, a.source, va / vb
                sheaf.add_flow(high, low, efficiency=ratio)
                edge_meta.append((entity, high, low, ratio))

    audit = sheaf.audit()
    # The minimal-disagreement section / gauge eigenvector. Field name differs
    # across solver vintages (assignment vs the typo'd asefficiencyment alias).
    gauge = getattr(audit, "assignment", None)
    if gauge is None:
        gauge = getattr(audit, "asefficiencyment", {})
    by_id = {id(edge): meta for edge, meta in zip(sheaf._edges, edge_meta)}

    offenders: List[SheafOffender] = []
    for edge, residual in audit.edge_residuals:
        entity, high, low, ratio = by_id[id(edge)]
        xh, xl = gauge.get(high, 0.0), gauge.get(low, 0.0)
        gauge_ratio = (xl / xh) if abs(xh) > 1e-12 else 0.0
        offenders.append(SheafOffender(
            entity=entity, source_high=high, source_low=low, ratio=ratio,
            gauge_ratio=gauge_ratio, residual=residual))

    return SheafResult(
        energy_leak=audit.energy_leak,
        stable=audit.energy_leak < stable_leak,
        n_edges=len(edge_meta), n_skipped=n_skipped,
        gauge=gauge, offenders=offenders)


def synthetic_sections() -> List[Section]:
    """Two views of the same quantity (the conservation regime) with a SYSTEMATIC
    scale + two planted deviants.

    `audited` = 0.8 x `reported` for everyone (a systematic effect, like
    small-cell suppression). A tolerance threshold would flag ALL of them; the
    sheaf absorbs the 0.8 into the gauge and flags only the two real deviants:
    npi_under (audited far below reported) and npi_over (audited == reported,
    i.e. no scale at all).
    """
    reported, audited = {}, {}
    for i in range(20):
        n = f"npi_{i:02d}"
        reported[n] = 100_000 + i * 1000
        audited[n] = reported[n] * 0.8         # systematic scale -> the gauge
    reported["npi_under"] = 120_000
    audited["npi_under"] = 120_000 * 0.2       # collapses vs the 0.8 gauge
    reported["npi_over"] = 110_000
    audited["npi_over"] = 110_000 * 1.0        # no scale -> deviates up
    return [
        Section("reported", reported, layer="3-provider"),
        Section("audited", audited, layer="3-provider"),
    ]
