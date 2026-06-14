# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""flow -- the U.S. healthcare money-flow domain for KOMPOSOS-HCARE.

One category, not four datasets. Federal healthcare dollars flow along a
chain of morphisms:

    Treasury --appropriates--> CMS --pays--> Insurer (Medicare Advantage)
                                  |                       |
                                  | (fee-for-service)     | (capitated)
                                  v                       v
                               Hospital / Provider (NPI) --prescribes--> Patient
                                  ^
                                  | pays
                           Drug Manufacturer (Open Payments)

Money conserves along composition. Where the composite does not equal the
sum of its parts, that gap is the leak (waste / overpayment / fraud).

Phase 1 (this scaffold): sheaf coherence at the provider/program level --
do the public datasets that describe the same entity agree? See
``domains.flow.coherence`` and run ``python -m domains.flow.run_coherence
--synthetic``.
"""

from __future__ import annotations

# Ensure the categorical runtime is importable (see domains/__init__.py).
import domains  # noqa: F401
