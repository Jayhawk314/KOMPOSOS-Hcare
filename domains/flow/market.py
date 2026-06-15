# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Phase H -- Patient and Market actors for the bidirectional open game.

This module models the demand side (Patient) and the pass-through mechanism
(Market/Competition). It provides the models needed to close the feedback loop
where coding -> margin -> rebate -> enrollment -> more margin.

The Calibration Anchor (Health Affairs 2024):
-------------------------------------------
Published data shows that $1 of coding revenue leads to ~$0.10-$0.19 in bid cuts
or premium reductions, and this pass-through is STRONGER in competitive counties.
The MarketModel ensures this pass-through rate is respected and scaled by a
competition index.

The Patient Demand Model:
-----------------------
Beneficiaries respond to the generosity of the rebate (premium cuts, extra
benefits). We model enrollment as elastic to the rebate value relative to
the FFS cost basis.

HONEST STATUS (read before trusting magnitudes):
------------------------------------------------
Unlike the Phase A coding response (calibrated so the baseline reproduces the
validated ~$107B), the Phase H demand/competition layer is **modeled, not
calibrated**: the enrollment elasticity and competition index are exposed
ASSUMPTIONS, not fit to data, and the bidirectional coding<->volume feedback is
a second-order effect not yet run through the Phase G uncertainty bands. Only the
DIRECTION is claimed (lower rebate -> lower enrollment; more competition -> more
elastic). The pass-through floor (0.15) is anchored to the Health Affairs
finding; sweep the rest before quoting any magnitude. The reported rebate DOLLARS
remain the Phase D statutory accounting -- this layer moves enrollment, it does
NOT set the rebate level.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MarketModel:
    """Models market competition and its effect on pass-through rates."""
    # The baseline pass-through of margin to rebate. If a plan gains $1 of margin,
    # what fraction must it spend on beneficiaries to remain competitive?
    # Anchored to the Health Affairs finding of ~0.15 average.
    baseline_pass_through: float = 0.15
    
    # A multiplier >= 0. 1.0 is average competition. Higher means stronger pass-through.
    competition_index: float = 1.0

    @property
    def effective_pass_through(self) -> float:
        """The fraction of margin passed to beneficiaries as rebate."""
        return min(1.0, self.baseline_pass_through * self.competition_index)


@dataclass(frozen=True)
class PatientModel:
    """Models beneficiary enrollment response to rebate generosity."""
    # Percentage change in enrollment per 1% change in (rebate/ffs_cost)
    demand_elasticity: float = 0.0

    def calculate_enrollment(self, base_enrollment: int, base_rebate: float,
                             new_rebate: float, ffs_cost: float) -> int:
        """Calculate the new enrollment given a change in rebate."""
        if self.demand_elasticity <= 0.0 or ffs_cost <= 0.0:
            return base_enrollment
            
        rebate_delta_pct = (new_rebate - base_rebate) / ffs_cost
        enrollment_multiplier = 1.0 + (self.demand_elasticity * rebate_delta_pct)
        
        return max(0, int(base_enrollment * enrollment_multiplier))
