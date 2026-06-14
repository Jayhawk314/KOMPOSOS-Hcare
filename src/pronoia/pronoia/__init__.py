# PRONOIA — interpretable, non-LLM prediction stack (prototype).
# Working codename; see PRONOIA_PREDICTION_STACK.md for the full vision.
#
# L5 CERTIFY  -> honesty_mdl  (honesty as compression fidelity)
# L1 FUSE     -> sheaf_probe  (cellular sheaf; H^1 = contradiction alarm)

from .honesty_mdl import (
    ReasoningStep,
    SincerityReport,
    sincerity,
    most_sincere,
    description_bits,
)
from .sheaf_probe import (
    Sheaf,
    SheafEdge,
    ContradictionReport,
)
from .mdl_ranker import (
    Hypothesis,
    RankedHypothesis,
    rank,
    compression_gain,
)
from .tsetlin import (
    TsetlinMachine,
    Clause,
)
from .vsa import (
    HDComputing,
)
from .scm import (
    SCM,
)

__all__ = [
    "ReasoningStep",
    "SincerityReport",
    "sincerity",
    "most_sincere",
    "description_bits",
    "Sheaf",
    "SheafEdge",
    "ContradictionReport",
    "Hypothesis",
    "RankedHypothesis",
    "rank",
    "compression_gain",
    "TsetlinMachine",
    "Clause",
    "HDComputing",
    "SCM",
]
