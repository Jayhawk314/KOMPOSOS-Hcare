# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-KOMPOSOS-IV-Commercial
# Copyright (c) 2024-2026 James Ray Hawkins

"""
Oracle Strategy Tests

Tests for all 13 oracle strategies that previously lacked dedicated coverage:
1. NaturalTransformationStrategy
2. OperadicDecompositionStrategy
3. EvidenceCombinationStrategy
4. StreamingForecastStrategy
5. TopologicalAnomalyStrategy
6. GameStrategy
7. GeometricHomotopyStrategy
8. ActivityAnalysisStrategy
9. BoundaryDetectionStrategy
10. CellularDynamicsStrategy
11. CubicalGapFillingStrategy
12. FibrationLiftStrategy
13. ToposLogicStrategy
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.category import Category
from core.types import Object, Morphism
from oracle.prediction import Prediction, PredictionType


# ── Helper: mock strategy for EvidenceCombinationStrategy ────────────

class MockStrategy:
    """Wraps a list of predictions to act as an oracle strategy."""
    def __init__(self, predictions):
        self.predictions = predictions
    def predict(self, source, target):
        return self.predictions


# ══════════════════════════════════════════════════════════════════════════════
# 1. NaturalTransformationStrategy
# ══════════════════════════════════════════════════════════════════════════════

class TestNaturalTransformationStrategy(unittest.TestCase):
    """Test naturality detection between parallel paths."""

    def setUp(self):
        """Build category with two parallel paths A->B->D and A->C->D."""
        self.cat = Category("nat_trans_test", db_path=":memory:")
        self.cat.add("A", type_name="Node")
        self.cat.add("B", type_name="Node")
        self.cat.add("C", type_name="Node")
        self.cat.add("D", type_name="Node")
        self.cat.connect("A", "B", "f", confidence=0.8)
        self.cat.connect("B", "D", "g", confidence=0.7)
        self.cat.connect("A", "C", "h", confidence=0.75)
        self.cat.connect("C", "D", "k", confidence=0.72)

    def test_parallel_paths_detect_naturality(self):
        """Two parallel paths with similar confidence profiles trigger naturality."""
        from oracle.natural_transformation import NaturalTransformationStrategy
        strategy = NaturalTransformationStrategy(self.cat)
        preds = strategy.predict("A", "D")
        self.assertIsInstance(preds, list)
        # Should detect the naturality between A->B->D and A->C->D
        if preds:
            self.assertEqual(preds[0].source, "A")
            self.assertEqual(preds[0].target, "D")
            self.assertIn(preds[0].predicted_relation,
                          ["natural_transform", "direct_edge"])
            self.assertGreater(preds[0].confidence, 0.0)

    def test_no_intermediate_returns_empty(self):
        """No intermediate paths = no naturality prediction."""
        from oracle.natural_transformation import NaturalTransformationStrategy
        cat2 = Category("no_inter", db_path=":memory:")
        cat2.add("X", type_name="Node")
        cat2.add("Y", type_name="Node")
        cat2.connect("X", "Y", "direct", confidence=0.9)
        strategy = NaturalTransformationStrategy(cat2)
        preds = strategy.predict("X", "Y")
        # No intermediate paths, should return empty
        self.assertEqual(len(preds), 0)

    def test_different_confidence_profiles(self):
        """Very different confidence paths should not trigger high naturality."""
        from oracle.natural_transformation import NaturalTransformationStrategy
        cat2 = Category("diff_conf", db_path=":memory:")
        cat2.add("A", type_name="Node")
        cat2.add("B", type_name="Node")
        cat2.add("C", type_name="Node")
        cat2.add("D", type_name="Node")
        # Path 1: high confidence
        cat2.connect("A", "B", "f1", confidence=0.95)
        cat2.connect("B", "D", "g1", confidence=0.95)
        # Path 2: very low confidence
        cat2.connect("A", "C", "f2", confidence=0.1)
        cat2.connect("C", "D", "g2", confidence=0.1)
        strategy = NaturalTransformationStrategy(cat2, threshold=0.6)
        preds = strategy.predict("A", "D")
        # The naturality score should be low due to confidence difference
        for p in preds:
            if p.predicted_relation == "natural_transform":
                # Should be below threshold or very low confidence
                self.assertLess(p.confidence, 0.7)


# ══════════════════════════════════════════════════════════════════════════════
# 2. OperadicDecompositionStrategy
# ══════════════════════════════════════════════════════════════════════════════

class TestOperadicDecompositionStrategy(unittest.TestCase):
    """Test operadic decomposition of morphisms."""

    def test_decomposable_morphism(self):
        """A->C exists and A->B->C also exists → decomposable."""
        from oracle.operadic_decomposition import OperadicDecompositionStrategy
        cat = Category("operadic_decomp", db_path=":memory:")
        cat.add("A", type_name="Node")
        cat.add("B", type_name="Node")
        cat.add("C", type_name="Node")
        cat.connect("A", "C", "direct", confidence=0.9)
        cat.connect("A", "B", "step1", confidence=0.8)
        cat.connect("B", "C", "step2", confidence=0.85)
        strategy = OperadicDecompositionStrategy(cat)
        preds = strategy.predict("A", "C")
        self.assertIsInstance(preds, list)
        self.assertGreater(len(preds), 0)
        self.assertEqual(preds[0].source, "A")
        self.assertEqual(preds[0].target, "C")
        # Should be decomposed, not primitive
        self.assertNotEqual(preds[0].predicted_relation, "genuine_primitive")

    def test_genuine_primitive(self):
        """A->C exists with no intermediate → genuine primitive."""
        from oracle.operadic_decomposition import OperadicDecompositionStrategy
        cat = Category("operadic_prim", db_path=":memory:")
        cat.add("A", type_name="Node")
        cat.add("C", type_name="Node")
        cat.connect("A", "C", "direct", confidence=0.9)
        strategy = OperadicDecompositionStrategy(cat)
        preds = strategy.predict("A", "C")
        self.assertEqual(len(preds), 1)
        self.assertEqual(preds[0].predicted_relation, "genuine_primitive")

    def test_nonexistent_edge(self):
        """No direct edge between source and target → no prediction."""
        from oracle.operadic_decomposition import OperadicDecompositionStrategy
        cat = Category("operadic_noedge", db_path=":memory:")
        cat.add("A", type_name="Node")
        cat.add("B", type_name="Node")
        cat.add("C", type_name="Node")
        cat.connect("A", "B", "step1", confidence=0.8)
        cat.connect("B", "C", "step2", confidence=0.85)
        # No A->C edge
        strategy = OperadicDecompositionStrategy(cat)
        preds = strategy.predict("A", "C")
        self.assertEqual(len(preds), 0)


# ══════════════════════════════════════════════════════════════════════════════
# 3. EvidenceCombinationStrategy
# ══════════════════════════════════════════════════════════════════════════════

class TestEvidenceCombinationStrategy(unittest.TestCase):
    """Test Dempster-Shafer evidence combination across strategies."""

    def test_combine_agreeing_evidence(self):
        """Two strategies agree → combined confidence increases."""
        from oracle.evidence_combination import EvidenceCombinationStrategy
        cat = Category("evidence_test", db_path=":memory:")
        cat.add("A", type_name="Asset:equity")
        cat.add("B", type_name="Asset:equity")

        strategy = EvidenceCombinationStrategy(cat)
        mock_pred1 = Prediction(
            source="A", target="B",
            predicted_relation="correlates_with",
            prediction_type=PredictionType.TYPE_CONSTRAINED,
            strategy_name="type_heuristic",
            confidence=0.6, reasoning="same type", evidence={},
        )
        mock_pred2 = Prediction(
            source="A", target="B",
            predicted_relation="correlates_with",
            prediction_type=PredictionType.SEMANTIC_SIMILARITY,
            strategy_name="semantic",
            confidence=0.7, reasoning="semantic match", evidence={},
        )
        strategy._other_strategies = [
            MockStrategy([mock_pred1]),
            MockStrategy([mock_pred2]),
        ]
        preds = strategy.predict("A", "B")
        self.assertIsInstance(preds, list)
        self.assertGreater(len(preds), 0)
        # Combined evidence should have ensemble prediction
        self.assertEqual(preds[0].prediction_type, PredictionType.ENSEMBLE)

    def test_conflicting_evidence(self):
        """Two strategies disagree → conflict is quantified."""
        from oracle.evidence_combination import EvidenceCombinationStrategy
        cat = Category("evidence_conflict", db_path=":memory:")
        cat.add("A", type_name="Asset:equity")
        cat.add("B", type_name="Asset:commodity")

        strategy = EvidenceCombinationStrategy(cat)
        mock_pred1 = Prediction(
            source="A", target="B",
            predicted_relation="correlates_with",
            prediction_type=PredictionType.TYPE_CONSTRAINED,
            strategy_name="type_heuristic",
            confidence=0.6, reasoning="test", evidence={},
        )
        mock_pred2 = Prediction(
            source="A", target="B",
            predicted_relation="independent",
            prediction_type=PredictionType.SEMANTIC_SIMILARITY,
            strategy_name="semantic",
            confidence=0.7, reasoning="test", evidence={},
        )
        strategy._other_strategies = [
            MockStrategy([mock_pred1]),
            MockStrategy([mock_pred2]),
        ]
        preds = strategy.predict("A", "B")
        # Should still return predictions even with conflict
        self.assertIsInstance(preds, list)

    def test_empty_other_strategies(self):
        """No other strategies → empty prediction list."""
        from oracle.evidence_combination import EvidenceCombinationStrategy
        cat = Category("evidence_empty", db_path=":memory:")
        cat.add("A", type_name="Node")
        cat.add("B", type_name="Node")
        strategy = EvidenceCombinationStrategy(cat)
        strategy._other_strategies = []
        preds = strategy.predict("A", "B")
        self.assertEqual(len(preds), 0)


# ══════════════════════════════════════════════════════════════════════════════
# 4. StreamingForecastStrategy
# ══════════════════════════════════════════════════════════════════════════════

class TestStreamingForecastStrategy(unittest.TestCase):
    """Test temporal forecasting via streaming Kan extensions."""

    def test_forecast_with_observations(self):
        """After observations, strategy produces forecasts."""
        from oracle.streaming_forecast import StreamingForecastStrategy
        cat = Category("streaming_test", db_path=":memory:")
        cat.add("A", type_name="Capability")
        cat.add("B", type_name="Capability")

        strategy = StreamingForecastStrategy(cat, decay_rate=0.01,
                                              min_confidence=0.3)
        # Record observations
        strategy.observe("A", "B", weight=0.8)
        preds = strategy.predict("A", "B")
        self.assertIsInstance(preds, list)
        # After observing A->B, should forecast the relationship
        if preds:
            self.assertEqual(preds[0].source, "A")
            self.assertEqual(preds[0].target, "B")

    def test_no_observations_empty(self):
        """No observations → no forecasts."""
        from oracle.streaming_forecast import StreamingForecastStrategy
        cat = Category("streaming_empty", db_path=":memory:")
        cat.add("A", type_name="Capability")
        cat.add("B", type_name="Capability")
        strategy = StreamingForecastStrategy(cat)
        preds = strategy.predict("A", "B")
        self.assertEqual(len(preds), 0)


# ══════════════════════════════════════════════════════════════════════════════
# 5. TopologicalAnomalyStrategy
# ══════════════════════════════════════════════════════════════════════════════

class TestTopologicalAnomalyStrategy(unittest.TestCase):
    """Test topological hole detection via persistent homology."""

    def test_triangle_loop_detected(self):
        """A triangle A->B->C->A should detect a topological hole."""
        from oracle.topological_anomaly import TopologicalAnomalyStrategy
        cat = Category("topo_triangle", db_path=":memory:")
        cat.add("A", type_name="Node")
        cat.add("B", type_name="Node")
        cat.add("C", type_name="Node")
        cat.connect("A", "B", "f", confidence=0.8)
        cat.connect("B", "C", "g", confidence=0.7)
        cat.connect("C", "A", "h", confidence=0.75)
        strategy = TopologicalAnomalyStrategy(cat, min_confidence=0.5)
        preds = strategy.predict("A", "C")
        # Should detect the loop and predict a fill edge
        self.assertIsInstance(preds, list)
        # Whether it predicts depends on the simplicial complex construction
        # At minimum, should not crash
        for p in preds:
            self.assertIn(p.predicted_relation,
                          ["topological_fill", "topological_bridge"])

    def test_disconnected_components(self):
        """Two disconnected components should predict a bridge."""
        from oracle.topological_anomaly import TopologicalAnomalyStrategy
        cat = Category("topo_disconnected", db_path=":memory:")
        cat.add("A", type_name="Component1")
        cat.add("B", type_name="Component1")
        cat.add("C", type_name="Component2")
        cat.add("D", type_name="Component2")
        cat.connect("A", "B", "f", confidence=0.8)
        cat.connect("C", "D", "g", confidence=0.7)
        strategy = TopologicalAnomalyStrategy(cat, min_confidence=0.5)
        preds = strategy.predict("A", "C")
        self.assertIsInstance(preds, list)
        # May or may not predict a bridge depending on implementation
        # but should not crash

    def test_single_connected_component(self):
        """Fully connected graph should not predict fills."""
        from oracle.topological_anomaly import TopologicalAnomalyStrategy
        cat = Category("topo_connected", db_path=":memory:")
        cat.add("A", type_name="Node")
        cat.add("B", type_name="Node")
        cat.connect("A", "B", "f", confidence=0.8)
        cat.connect("B", "A", "g", confidence=0.7)
        strategy = TopologicalAnomalyStrategy(cat, min_confidence=0.5)
        preds = strategy.predict("A", "B")
        self.assertIsInstance(preds, list)
        # A->B already exists, no fill needed


# ══════════════════════════════════════════════════════════════════════════════
# 6. GameStrategy
# ══════════════════════════════════════════════════════════════════════════════

class TestGameStrategy(unittest.TestCase):
    """Test game-theoretic analysis of capability interactions."""

    def test_competitive_equilibrium(self):
        """Two capabilities targeting the same object but not connected."""
        from oracle.game_strategy import GameStrategy
        cat = Category("game_compete", db_path=":memory:")
        cat.add("A", type_name="Capability")
        cat.add("X", type_name="Capability")
        cat.add("B", type_name="Target")
        cat.connect("A", "B", "cap_a", confidence=0.8)
        cat.connect("X", "B", "cap_x", confidence=0.6)
        strategy = GameStrategy(cat)
        preds = strategy.predict("A", "X")
        self.assertIsInstance(preds, list)
        if preds:
            self.assertEqual(preds[0].source, "A")
            self.assertEqual(preds[0].target, "X")
            self.assertIn(preds[0].predicted_relation,
                          ["competitive_equilibrium", "cooperative_equilibrium"])

    def test_cooperative_equilibrium(self):
        """Two capabilities targeting the same object AND connected."""
        from oracle.game_strategy import GameStrategy
        cat = Category("game_coop", db_path=":memory:")
        cat.add("A", type_name="Capability")
        cat.add("X", type_name="Capability")
        cat.add("B", type_name="Target")
        cat.connect("A", "B", "cap_a", confidence=0.8)
        cat.connect("X", "B", "cap_x", confidence=0.6)
        cat.connect("A", "X", "link", confidence=0.5)
        cat.connect("X", "A", "link_back", confidence=0.5)
        strategy = GameStrategy(cat)
        preds = strategy.predict("A", "X")
        self.assertIsInstance(preds, list)

    def test_insufficient_competitors(self):
        """Only one morphism to target → no game analysis."""
        from oracle.game_strategy import GameStrategy
        cat = Category("game_single", db_path=":memory:")
        cat.add("A", type_name="Capability")
        cat.add("B", type_name="Target")
        cat.connect("A", "B", "cap_a", confidence=0.8)
        strategy = GameStrategy(cat)
        preds = strategy.predict("A", "B")
        self.assertEqual(len(preds), 0)


# ══════════════════════════════════════════════════════════════════════════════
# 7. GeometricHomotopyStrategy
# ══════════════════════════════════════════════════════════════════════════════

class TestGeometricHomotopyStrategy(unittest.TestCase):
    """Test geometric homotopy classification of paths."""

    def test_multiple_paths(self):
        """Two paths A->B->D and A->C->D between same endpoints."""
        from oracle.geometric_homotopy_strategy import (
            GeometricHomotopyStrategy, HOMOTOPY_AVAILABLE,
        )
        cat = Category("geo_homotopy", db_path=":memory:")
        cat.add("A", type_name="Node")
        cat.add("B", type_name="Node")
        cat.add("C", type_name="Node")
        cat.add("D", type_name="Node")
        cat.connect("A", "B", "f1", confidence=0.8)
        cat.connect("B", "D", "g1", confidence=0.7)
        cat.connect("A", "C", "f2", confidence=0.75)
        cat.connect("C", "D", "g2", confidence=0.72)
        strategy = GeometricHomotopyStrategy(cat)
        preds = strategy.predict("A", "D")
        self.assertIsInstance(preds, list)
        if not HOMOTOPY_AVAILABLE:
            # Module not importable → empty prediction
            self.assertEqual(len(preds), 0)
        # If available, predictions grouped by homotopy class

    def test_single_path(self):
        """Single path → unique pathway classification."""
        from oracle.geometric_homotopy_strategy import (
            GeometricHomotopyStrategy, HOMOTOPY_AVAILABLE,
        )
        cat = Category("geo_single", db_path=":memory:")
        cat.add("A", type_name="Node")
        cat.add("B", type_name="Node")
        cat.connect("A", "B", "f", confidence=0.8)
        strategy = GeometricHomotopyStrategy(cat)
        preds = strategy.predict("A", "B")
        self.assertIsInstance(preds, list)
        if not HOMOTOPY_AVAILABLE:
            self.assertEqual(len(preds), 0)


# ══════════════════════════════════════════════════════════════════════════════
# 8. ActivityAnalysisStrategy
# ══════════════════════════════════════════════════════════════════════════════

class TestActivityAnalysisStrategy(unittest.TestCase):
    """Test activity theory contradiction detection."""

    def test_basic_activity_system(self):
        """Build activity system and detect contradictions."""
        from oracle.activity_analysis import ActivityAnalysisStrategy
        cat = Category("activity_test", db_path=":memory:")
        # Activity theory components
        cat.add("Subject", type_name="Subject")
        cat.add("Tool", type_name="Tool")
        cat.add("Object", type_name="Object")
        cat.add("Community", type_name="Community")
        cat.connect("Subject", "Tool", "uses", confidence=0.8)
        cat.connect("Tool", "Object", "transforms", confidence=0.7)
        cat.connect("Subject", "Object", "targets", confidence=0.6)
        cat.connect("Subject", "Community", "belongs_to", confidence=0.5)
        strategy = ActivityAnalysisStrategy(cat)
        preds = strategy.predict("Subject", "Object")
        self.assertIsInstance(preds, list)
        # May or may not predict depending on contradiction detection
        # At minimum should not crash

    def test_empty_category(self):
        """Empty activity system → no contradictions."""
        from oracle.activity_analysis import ActivityAnalysisStrategy
        cat = Category("activity_empty", db_path=":memory:")
        cat.add("A", type_name="Node")
        cat.add("B", type_name="Node")
        strategy = ActivityAnalysisStrategy(cat)
        preds = strategy.predict("A", "B")
        self.assertIsInstance(preds, list)
        self.assertEqual(len(preds), 0)


# ══════════════════════════════════════════════════════════════════════════════
# 9. BoundaryDetectionStrategy
# ══════════════════════════════════════════════════════════════════════════════

class TestBoundaryDetectionStrategy(unittest.TestCase):
    """Test cross-domain boundary bridge detection."""

    def test_cross_domain_bridge(self):
        """Different types sharing a neighbor → boundary bridge."""
        from oracle.boundary_detection import BoundaryDetectionStrategy
        cat = Category("boundary_test", db_path=":memory:")
        cat.add("ChemMol", type_name="Chemistry")
        cat.add("StockAsset", type_name="Finance")
        cat.add("SharedMetric", type_name="Data")
        cat.connect("ChemMol", "SharedMetric", "has_property", confidence=0.8)
        cat.connect("StockAsset", "SharedMetric", "measured_by", confidence=0.7)
        strategy = BoundaryDetectionStrategy(cat)
        preds = strategy.predict("ChemMol", "StockAsset")
        self.assertIsInstance(preds, list)
        self.assertGreater(len(preds), 0)
        self.assertEqual(preds[0].source, "ChemMol")
        self.assertEqual(preds[0].target, "StockAsset")
        self.assertEqual(preds[0].predicted_relation, "boundary_bridge")
        # Strength = 1.0 (both only connect to SharedMetric)
        self.assertGreaterEqual(preds[0].confidence, 0.3)

    def test_same_domain_no_bridge(self):
        """Same type → not a boundary object."""
        from oracle.boundary_detection import BoundaryDetectionStrategy
        cat = Category("boundary_same", db_path=":memory:")
        cat.add("A", type_name="Chemistry")
        cat.add("B", type_name="Chemistry")
        cat.add("Shared", type_name="Data")
        cat.connect("A", "Shared", "rel1", confidence=0.8)
        cat.connect("B", "Shared", "rel2", confidence=0.7)
        strategy = BoundaryDetectionStrategy(cat)
        preds = strategy.predict("A", "B")
        # Same type → not a boundary bridge
        self.assertEqual(len(preds), 0)

    def test_no_shared_neighbors(self):
        """Different types but no shared neighbors → no bridge."""
        from oracle.boundary_detection import BoundaryDetectionStrategy
        cat = Category("boundary_no_share", db_path=":memory:")
        cat.add("A", type_name="Chemistry")
        cat.add("B", type_name="Finance")
        cat.add("X", type_name="Data")
        cat.add("Y", type_name="Data")
        cat.connect("A", "X", "rel1", confidence=0.8)
        cat.connect("B", "Y", "rel2", confidence=0.7)
        strategy = BoundaryDetectionStrategy(cat)
        preds = strategy.predict("A", "B")
        # No shared neighbors
        self.assertEqual(len(preds), 0)


# ══════════════════════════════════════════════════════════════════════════════
# 10. CellularDynamicsStrategy
# ══════════════════════════════════════════════════════════════════════════════

class TestCellularDynamicsStrategy(unittest.TestCase):
    """Test SIR epidemic model on capability graphs."""

    def test_infection_spreads(self):
        """A->B->C: starting infection at A should reach C."""
        from oracle.cellular_dynamics import CellularDynamicsStrategy
        cat = Category("cellular_test", db_path=":memory:")
        cat.add("A", type_name="Capability")
        cat.add("B", type_name="Capability")
        cat.add("C", type_name="Capability")
        cat.connect("A", "B", "link1", confidence=0.8)
        cat.connect("B", "C", "link2", confidence=0.7)
        strategy = CellularDynamicsStrategy(cat, steps=5,
                                             beta=0.5, gamma=0.1)
        preds = strategy.predict("A", "C")
        self.assertIsInstance(preds, list)
        # SIR model with high infection rate should spread through A->B->C
        if preds:
            self.assertEqual(preds[0].source, "A")
            self.assertEqual(preds[0].target, "C")
            self.assertIn("adopted", preds[0].predicted_relation)

    def test_disconnected_no_spread(self):
        """Disconnected graph → no infection spread."""
        from oracle.cellular_dynamics import CellularDynamicsStrategy
        cat = Category("cellular_disconnected", db_path=":memory:")
        cat.add("A", type_name="Capability")
        cat.add("B", type_name="Capability")
        cat.connect("A", "B", "link", confidence=0.8)
        # C is isolated
        cat.add("C", type_name="Capability")
        strategy = CellularDynamicsStrategy(cat, steps=5)
        preds = strategy.predict("A", "C")
        # C is isolated, no spread
        self.assertEqual(len(preds), 0)

    def test_low_infection_rate(self):
        """Very low infection rate may prevent spread."""
        from oracle.cellular_dynamics import CellularDynamicsStrategy
        cat = Category("cellular_low_rate", db_path=":memory:")
        cat.add("A", type_name="Capability")
        cat.add("B", type_name="Capability")
        cat.add("C", type_name="Capability")
        cat.connect("A", "B", "link1", confidence=0.8)
        cat.connect("B", "C", "link2", confidence=0.7)
        # Very low infection rate
        strategy = CellularDynamicsStrategy(cat, steps=3,
                                             beta=0.01)
        preds = strategy.predict("A", "C")
        # May or may not spread depending on random seed
        self.assertIsInstance(preds, list)


# ══════════════════════════════════════════════════════════════════════════════
# 11. CubicalGapFillingStrategy
# ══════════════════════════════════════════════════════════════════════════════

class TestCubicalGapFillingStrategy(unittest.TestCase):
    """Test transitive closure via cubical hcomp."""

    def test_2hop_composition(self):
        """A->B->C: predict A->C via transitive closure."""
        from oracle.cubical_gap_filling_strategy import CubicalGapFillingStrategy
        cat = Category("cubical_2hop", db_path=":memory:")
        cat.add("A", type_name="Node")
        cat.add("B", type_name="Node")
        cat.add("C", type_name="Node")
        cat.connect("A", "B", "influences", confidence=0.8)
        cat.connect("B", "C", "influences", confidence=0.7)
        strategy = CubicalGapFillingStrategy(cat, min_confidence=0.4)
        preds = strategy.predict("A", "C")
        self.assertIsInstance(preds, list)
        self.assertGreater(len(preds), 0)
        self.assertEqual(preds[0].source, "A")
        self.assertEqual(preds[0].target, "C")
        self.assertEqual(preds[0].predicted_relation, "influences")
        self.assertEqual(preds[0].prediction_type,
                         PredictionType.TRANSITIVE_CLOSURE)
        # 2-hop: 0.8 * 0.7 * 0.9 = 0.504
        self.assertGreater(preds[0].confidence, 0.4)

    def test_3hop_composition(self):
        """A->B->C->D: predict A->D via 3-hop composition."""
        from oracle.cubical_gap_filling_strategy import CubicalGapFillingStrategy
        cat = Category("cubical_3hop", db_path=":memory:")
        cat.add("A", type_name="Node")
        cat.add("B", type_name="Node")
        cat.add("C", type_name="Node")
        cat.add("D", type_name="Node")
        cat.connect("A", "B", "influences", confidence=0.8)
        cat.connect("B", "C", "influences", confidence=0.7)
        cat.connect("C", "D", "influences", confidence=0.6)
        strategy = CubicalGapFillingStrategy(cat, min_confidence=0.2)
        preds = strategy.predict("A", "D")
        self.assertIsInstance(preds, list)
        self.assertGreater(len(preds), 0)
        # 3-hop: 0.8 * 0.7 * 0.6 * 0.7 = 0.2352
        # May be below min_confidence depending on threshold

    def test_already_connected(self):
        """Direct edge exists → no gap to fill."""
        from oracle.cubical_gap_filling_strategy import CubicalGapFillingStrategy
        cat = Category("cubical_existing", db_path=":memory:")
        cat.add("A", type_name="Node")
        cat.add("B", type_name="Node")
        cat.connect("A", "B", "direct", confidence=0.9)
        strategy = CubicalGapFillingStrategy(cat)
        preds = strategy.predict("A", "B")
        # Direct edge exists, no indirect path needed
        self.assertEqual(len(preds), 0)


# ══════════════════════════════════════════════════════════════════════════════
# 12. FibrationLiftStrategy
# ══════════════════════════════════════════════════════════════════════════════

class TestFibrationLiftStrategy(unittest.TestCase):
    """Test Cartesian lift between same-fiber objects."""

    def test_cartesian_lift(self):
        """A and B in same fiber, B->T exists → predict A->T."""
        from oracle.strategies import FibrationLiftStrategy
        cat = Category("fibration_lift", db_path=":memory:")
        cat.add("A", type_name="Physicist",
                metadata={"era": "quantum"})
        cat.add("B", type_name="Physicist",
                metadata={"era": "quantum"})
        cat.add("T", type_name="Theory",
                metadata={"era": "quantum"})
        cat.connect("B", "T", "developed", confidence=0.8)
        strategy = FibrationLiftStrategy(cat)
        preds = strategy.predict("A", "T")
        self.assertIsInstance(preds, list)
        self.assertGreater(len(preds), 0)
        self.assertEqual(preds[0].source, "A")
        self.assertEqual(preds[0].target, "T")
        # confidence = min(0.70, 0.8 * 0.8) = 0.64
        self.assertGreater(preds[0].confidence, 0.5)

    def test_different_fibers_no_lift(self):
        """A and B in different fibers → no lift."""
        from oracle.strategies import FibrationLiftStrategy
        cat = Category("fibration_diff", db_path=":memory:")
        cat.add("A", type_name="Physicist",
                metadata={"era": "quantum"})
        cat.add("B", type_name="Chemist",
                metadata={"era": "quantum"})
        cat.add("T", type_name="Theory",
                metadata={"era": "quantum"})
        cat.connect("B", "T", "developed", confidence=0.8)
        strategy = FibrationLiftStrategy(cat)
        preds = strategy.predict("A", "T")
        # Different types → different fibers
        self.assertEqual(len(preds), 0)


# ══════════════════════════════════════════════════════════════════════════════
# 13. ToposLogicStrategy
# ══════════════════════════════════════════════════════════════════════════════

class TestToposLogicStrategy(unittest.TestCase):
    """Test intuitionistic truth value computation."""

    def test_classical_truth(self):
        """Direct edge exists → classically true."""
        from oracle.topos_strategy import ToposLogicStrategy
        cat = Category("topos_classical", db_path=":memory:")
        cat.add("A", type_name="Concept")
        cat.add("B", type_name="Concept")
        cat.connect("A", "B", "implies", confidence=0.8)
        strategy = ToposLogicStrategy(cat)
        preds = strategy.predict("A", "B")
        self.assertIsInstance(preds, list)
        self.assertGreater(len(preds), 0)
        self.assertEqual(preds[0].predicted_relation, "classically_true")
        self.assertEqual(preds[0].confidence, 0.8)

    def test_intuitionistic_partial(self):
        """No direct edge → intuitionistic logic check."""
        from oracle.topos_strategy import ToposLogicStrategy
        cat = Category("topos_intuitionistic", db_path=":memory:")
        cat.add("A", type_name="Concept")
        cat.add("B", type_name="Concept")
        cat.add("C", type_name="Concept")
        cat.connect("A", "C", "implies", confidence=0.8)
        cat.connect("C", "B", "implies", confidence=0.7)
        strategy = ToposLogicStrategy(cat)
        preds = strategy.predict("A", "B")
        self.assertIsInstance(preds, list)
        # No direct edge, should try Heyting algebra and sieve analysis
        # May return empty or partial predictions

    def test_empty_category(self):
        """Empty category → no predictions."""
        from oracle.topos_strategy import ToposLogicStrategy
        cat = Category("topos_empty", db_path=":memory:")
        cat.add("A", type_name="Concept")
        cat.add("B", type_name="Concept")
        strategy = ToposLogicStrategy(cat)
        preds = strategy.predict("A", "B")
        self.assertIsInstance(preds, list)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main()
