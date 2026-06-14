# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Yoneda-distance peer-outlier detection for provider billing.

The Yoneda perspective: a provider is fully determined by how it relates to
everything else -- here, the bag of HCPCS codes it bills and how much. That is
the co-Yoneda fingerprint Hom(provider, -). Two providers are structurally the
same when their fingerprints coincide; an **outlier bills a mix unlike its
specialty peers**, which is a billing-fraud / overbilling signal.

Distance metric (the formal Yoneda distance, weighted)
------------------------------------------------------
``core/formal_yoneda.py`` proves d(y(A), y(B)) = |y(A) Δ y(B)| / |y(A) ∪ y(B)|
is a metric with d = 0 iff A ≅ B. We use its weighted generalization on
normalized fingerprints (so a provider's *mix* matters, not raw volume):

    d(p, q) = 1 - sum_c min(p_c, q_c) / sum_c max(p_c, q_c)        (weighted Jaccard)

with p, q probability vectors over codes. d in [0, 1], d = 0 iff identical mix.

A provider is scored against its **specialty consensus** (the mean normalized
fingerprint of its peers) -- the categorical "fibration": compare each point of
the fiber to the fiber's norm. High distance + material billing = flag.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional

Fingerprint = Mapping[str, float]


# ---------------------------------------------------------------------------
# Metric
# ---------------------------------------------------------------------------
def normalize(fp: Fingerprint) -> Dict[str, float]:
    total = sum(v for v in fp.values() if v > 0)
    if total <= 0:
        return {}
    return {k: v / total for k, v in fp.items() if v > 0}


def yoneda_distance(p: Fingerprint, q: Fingerprint) -> float:
    """Weighted Jaccard (formal Yoneda) distance on normalized fingerprints."""
    pn, qn = normalize(p), normalize(q)
    keys = set(pn) | set(qn)
    if not keys:
        return 0.0
    inter = sum(min(pn.get(k, 0.0), qn.get(k, 0.0)) for k in keys)
    union = sum(max(pn.get(k, 0.0), qn.get(k, 0.0)) for k in keys)
    return 1.0 - (inter / union) if union > 0 else 0.0


def consensus(fps: List[Fingerprint]) -> Dict[str, float]:
    """Mean normalized fingerprint of a peer group (the specialty norm)."""
    acc: Dict[str, float] = {}
    n = 0
    for fp in fps:
        nfp = normalize(fp)
        if not nfp:
            continue
        n += 1
        for k, v in nfp.items():
            acc[k] = acc.get(k, 0.0) + v
    if n == 0:
        return {}
    return {k: v / n for k, v in acc.items()}


def peer_prevalence(fps: List[Fingerprint]) -> Dict[str, float]:
    """Fraction of peers that bill each code (the peer-support presheaf).

    This is what makes outlier detection discriminating at national scale: the
    weighted-Jaccard distance to a consensus averaged over ~100k providers
    saturates near 1 for everyone, but *prevalence* stays informative -- it says
    how unusual each code is among peers.
    """
    n = 0
    cnt: Dict[str, int] = {}
    for fp in fps:
        if not normalize(fp):
            continue
        n += 1
        for k, v in fp.items():
            if v > 0:
                cnt[k] = cnt.get(k, 0) + 1
    if n == 0:
        return {}
    return {k: c / n for k, c in cnt.items()}


def rarity_score(fp: Fingerprint, prevalence: Mapping[str, float]) -> float:
    """Share of a provider's billing in codes that are rare among peers.

    score = sum_c share_p(c) * (1 - prevalence(c)),  in [0, 1].
    High = the provider concentrates its billing in codes few peers use -- the
    genuine outlier signal (e.g. skin-substitute codes billed by a handful of
    providers), which the saturating distance-to-consensus could not surface.
    """
    nfp = normalize(fp)
    return sum(share * (1.0 - prevalence.get(c, 0.0)) for c, share in nfp.items())


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
@dataclass
class OutlierResult:
    npi: str
    specialty: str
    distance: float                 # Yoneda distance to specialty consensus (reported)
    total_billed: float
    peers: int
    rarity: float = 0.0             # share of billing in codes rare among peers (flag basis)
    driver_codes: List[str] = field(default_factory=list)  # rare codes the provider over-bills

    @property
    def is_outlier(self) -> bool:
        return self._flag

    _flag: bool = False


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
class YonedaOutlierEngine:
    """Flag providers whose billing mix is far from their specialty consensus.

    Parameters
    ----------
    distance_threshold:
        Yoneda distance above which a provider is flagged (default 0.6).
    min_billed:
        Ignore providers below this total billing (focus on material cases).
    min_peers:
        Require at least this many peers for a stable consensus.
    category:
        Optional Category to write ``outlier_in`` / ``bills`` structure into.
    """

    def __init__(self, distance_threshold: float = 0.6, min_billed: float = 50_000.0,
                 min_peers: int = 3, category=None, max_writes: int = 500,
                 rarity_threshold: float = 0.5) -> None:
        self.distance_threshold = distance_threshold
        self.min_billed = min_billed
        self.min_peers = min_peers
        self.category = category
        # Cap Category write-back (backend commits per insert) to the top flagged.
        self.max_writes = max_writes
        # Flag basis at scale: share of billing in codes rare among peers. The
        # distance-to-consensus saturates over huge specialty groups, so it is
        # reported but not used as the gate.
        self.rarity_threshold = rarity_threshold

    def analyze(self, fingerprints: Mapping[str, Fingerprint],
                specialties: Mapping[str, str]) -> List[OutlierResult]:
        # Group providers by specialty (the fibration's fibers).
        by_spec: Dict[str, List[str]] = {}
        for npi in fingerprints:
            by_spec.setdefault(specialties.get(npi, "unknown"), []).append(npi)

        results: List[OutlierResult] = []
        for spec, npis in by_spec.items():
            peers = len(npis)
            group = [fingerprints[n] for n in npis]
            cons = consensus(group)
            prev = peer_prevalence(group)
            for npi in npis:
                fp = fingerprints[npi]
                total = sum(v for v in fp.values() if v > 0)
                dist = yoneda_distance(fp, cons)        # reported (saturates at scale)
                rar = rarity_score(fp, prev)            # flag basis (discriminating)
                drivers = self._driver_codes(fp, prev)
                r = OutlierResult(npi=npi, specialty=spec, distance=dist,
                                  total_billed=total, peers=peers, rarity=rar,
                                  driver_codes=drivers)
                r._flag = (
                    rar >= self.rarity_threshold
                    and total >= self.min_billed
                    and peers >= self.min_peers
                )
                results.append(r)
        results.sort(key=lambda x: (-x.rarity, -x.total_billed))
        # Write back only the top flagged (bounded; backend commits per insert).
        if self.category is not None:
            written = 0
            for r in results:
                if r._flag and written < self.max_writes:
                    self._write_back(r)
                    written += 1
        return results

    def _driver_codes(self, fp: Fingerprint, prevalence: Mapping[str, float],
                      top: int = 5) -> List[str]:
        """Rare codes (low peer prevalence) the provider concentrates billing in."""
        nfp = normalize(fp)
        contrib = {k: share * (1.0 - prevalence.get(k, 0.0)) for k, share in nfp.items()}
        ranked = sorted(contrib.items(), key=lambda kv: -kv[1])
        return [k for k, v in ranked[:top] if v > 0]

    def _write_back(self, r: OutlierResult) -> None:
        cat = self.category
        npi = f"npi:{r.npi}"
        spec = f"specialty:{r.specialty}"
        cat.add(npi, type_name="provider")
        cat.add(spec, type_name="specialty")
        cat.connect(npi, spec, name="outlier_in",
                    confidence=round(r.distance, 4),
                    total_billed=round(r.total_billed, 2),
                    peers=r.peers, drivers=",".join(r.driver_codes))


def summarize(results: List[OutlierResult], top: int = 15) -> str:
    flagged = [r for r in results if r.is_outlier]
    lines = ["Yoneda peer-outlier billing report", "=" * 72]
    exposure = sum(r.total_billed for r in flagged)
    for r in flagged[:top]:
        drv = ("  drivers=" + ",".join(r.driver_codes)) if r.driver_codes else ""
        lines.append(
            f"  {r.npi:<14} {r.specialty:<22} rarity={r.rarity:.2f}"
            f"  ${r.total_billed:>13,.0f}  peers={r.peers}{drv}"
        )
    lines.append("-" * 72)
    lines.append(f"  flagged {len(flagged)}/{len(results)} providers; "
                 f"billing exposure ${exposure:,.0f}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Synthetic demo data: a peer group with one clear outlier
# ---------------------------------------------------------------------------
def synthetic_fingerprints():
    """Cardiology peers billing a normal mix + one upcoding outlier."""
    fps = {
        "1000000001": {"99213": 60_000, "93000": 30_000, "99214": 20_000},
        "1000000002": {"99213": 55_000, "93000": 28_000, "99214": 25_000},
        "1000000003": {"99213": 62_000, "93000": 33_000, "99215": 12_000},
        "1000000004": {"99213": 58_000, "93000": 31_000, "99214": 18_000},
        # outlier: almost everything in a single high-reimbursement code.
        "1000000099": {"93799": 1_900_000, "99215": 90_000},
    }
    specs = {n: "Cardiology" for n in fps}
    return fps, specs
