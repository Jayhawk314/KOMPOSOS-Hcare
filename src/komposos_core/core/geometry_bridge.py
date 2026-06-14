# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-KOMPOSOS-IV-Commercial
# Copyright (c) 2024-2026 James Ray Hawkins

"""
Geometry Bridge: Category → geometry.Graph converter

Converts a KOMPOSOS-IV Category into a geometry.Graph for spectral analysis
and Ricci flow computation.

This unlocks:
  - geometry/spectral.py: algebraic connectivity, spectral clustering,
    Cheeger constant, random walk analysis
  - geometry/flow.py: discrete Ricci flow for geometric decomposition

Activation: spectral.py and flow.py were previously dead code because
they had no path from Category. This bridge provides that path.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from core.category import Category


def category_to_graph(category: "Category") -> Any:
    """
    Convert a KOMPOSOS-IV Category to a geometry.Graph.

    Objects become graph nodes.
    Morphisms become weighted edges (weight = confidence).

    Args:
        category: The source Category.

    Returns:
        A geometry.Graph instance with all objects and morphisms.
    """
    from geometry.spectral import Graph

    graph = Graph(nodes=[], edges=[])

    # Add all objects as nodes
    for obj in category.objects():
        graph.nodes.append(obj.name)

    # Add all morphisms as weighted edges
    for mor in category.morphisms():
        if mor.source != mor.target:  # Skip self-loops (identity morphisms)
            graph.edges.append((mor.source, mor.target, mor.confidence))

    return graph


def category_to_ricci_input(category: "Category") -> Dict[str, Any]:
    """
    Convert Category to the format expected by Ollivier-Ricci curvature.

    The Ricci module expects a category-like object with .morphisms()
    that returns objects with .source, .target, and .confidence.
    The Category already satisfies this interface directly.

    For modules that need raw edge lists, this provides the conversion.

    Args:
        category: The source Category.

    Returns:
        Dict with "edges" list of (source, target, weight) tuples.
    """
    edges = category.as_edges()  # Already provides (source, target, weight)
    return {"edges": edges}


def enrich_category_with_curvature(category: "Category",
                                   curvature_results: Dict[str, Any]) -> None:
    """
    Enrich Category objects with curvature metadata from geometry analysis.

    Args:
        category: The Category to enrich.
        curvature_results: Results from geometry.ricci or geometry.spectral analysis.
    """
    if "node_curvatures" in curvature_results:
        for node_name, curvature in curvature_results["node_curvatures"].items():
            obj = category.get(node_name)
            if obj:
                obj.metadata["ricci_curvature"] = curvature

    if "geometry_classification" in curvature_results:
        for region_name, classification in curvature_results["geometry_classification"].items():
            obj = category.get(region_name)
            if obj:
                obj.metadata["geometry_type"] = classification

    if "spectral_cluster" in curvature_results:
        for node_name, cluster in curvature_results["spectral_cluster"].items():
            obj = category.get(node_name)
            if obj:
                obj.metadata["spectral_cluster"] = cluster
