# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""KOMPOSOS-HCARE domain packages.

Importing this package puts the categorical runtime (``src/komposos_core``)
on ``sys.path`` so domain modules can ``from core.category import Category``
exactly like the reference ``grid`` domain does, regardless of the current
working directory.
"""

from __future__ import annotations

import os
import sys

# repo_root/domains/__init__.py  ->  repo_root
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RUNTIME = os.path.join(_REPO_ROOT, "src", "komposos_core")
_PRONOIA = os.path.join(_REPO_ROOT, "src", "pronoia")

for _p in (_RUNTIME, _PRONOIA):
    # Front of path so `core`, `categorical`, `cog`, `zfc`, `pronoia`, ... resolve.
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)
