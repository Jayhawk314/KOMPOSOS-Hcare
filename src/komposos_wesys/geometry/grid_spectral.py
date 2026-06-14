# SPDX-License-Identifier: Apache-2.0 OR KOMPOSOS-III-Commercial
# Copyright (c) 2024-2026 James Ray Hawkins

"""
Spectral Graph Theory for Energy Grid Analysis
=============================================

Analyzes grid connectivity and health via Laplacian eigenvalues.
"""

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
import numpy as np

try:
    from scipy.linalg import eigh
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

@dataclass
class SpectralResult:
    """Results of spectral analysis."""
    eigenvalues: np.ndarray
    eigenvectors: np.ndarray
    node_names: List[str]
    algebraic_connectivity: float
    coupling_strength: str
    equilibration_time: float
    analysis: str


class SpectralGraphAnalyzer:
    """
    Spectral graph theory analyzer for categorical networks.
    """

    def __init__(self, category=None):
        self.category = category
        self.laplacian = None
        self.eigenvalues = None
        self.eigenvectors = None
        self.node_names = None

    def build_laplacian(self) -> np.ndarray:
        """
        Build graph Laplacian from category morphisms.
        """
        if self.category is None:
            raise ValueError("No category provided")

        # Get node names from internal dict
        self.node_names = list(self.category._objects.keys())
        n = len(self.node_names)

        if n == 0:
            raise ValueError("Category has no objects")

        node_to_idx = {name: i for i, name in enumerate(self.node_names)}

        # Build adjacency matrix
        A = np.zeros((n, n))

        for mor in self.category.morphisms():
            source_name = mor.source
            target_name = mor.target

            if source_name not in node_to_idx or target_name not in node_to_idx:
                continue

            i, j = node_to_idx[source_name], node_to_idx[target_name]
            weight = mor.confidence
            A[i, j] += weight
            A[j, i] += weight

        # Degree matrix
        D = np.diag(np.sum(A, axis=1))

        # Laplacian
        self.laplacian = D - A
        return self.laplacian

    def compute_spectrum(self) -> Tuple[np.ndarray, np.ndarray]:
        if self.laplacian is None:
            self.build_laplacian()

        # Fallback to numpy
        eigenvalues, eigenvectors = np.linalg.eigh(self.laplacian)

        # Sort by eigenvalue
        idx = eigenvalues.argsort()
        eigenvalues = eigenvalues[idx]
        eigenvectors = eigenvectors[:, idx]

        self.eigenvalues = eigenvalues
        self.eigenvectors = eigenvectors

        return eigenvalues, eigenvectors

    def analyze_coupling(self) -> Dict:
        if self.eigenvalues is None:
            self.compute_spectrum()

        # First eigenvalue is always 0 (or close to it)
        # Second smallest is the algebraic connectivity (Fiedler value)
        lambda_1 = self.eigenvalues[1] if len(self.eigenvalues) > 1 else 0

        if lambda_1 < 0.1:
            coupling_str = "very weak"
        elif lambda_1 < 0.3:
            coupling_str = "weak"
        elif lambda_1 < 0.7:
            coupling_str = "moderate"
        else:
            coupling_str = "strong"

        eq_time = 1.0 / lambda_1 if lambda_1 > 1e-6 else float('inf')

        return {
            "algebraic_connectivity": lambda_1,
            "coupling_strength": coupling_str,
            "equilibration_time": eq_time,
        }

    def full_analysis(self) -> SpectralResult:
        eigenvalues, eigenvectors = self.compute_spectrum()
        coupling = self.analyze_coupling()

        analysis_text = (
            f"Spectral Health Report\n"
            f"----------------------\n"
            f"Algebraic Connectivity: {coupling['algebraic_connectivity']:.4f}\n"
            f"Coupling Strength: {coupling['coupling_strength']}\n"
            f"Equilibration Time: {coupling['equilibration_time']:.1f} units"
        )

        return SpectralResult(
            eigenvalues=eigenvalues,
            eigenvectors=eigenvectors,
            node_names=self.node_names,
            algebraic_connectivity=coupling["algebraic_connectivity"],
            coupling_strength=coupling["coupling_strength"],
            equilibration_time=coupling["equilibration_time"],
            analysis=analysis_text
        )
