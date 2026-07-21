# pylint: disable=protected-access
"""Tests for OrigEDivisive algorithm and its integration."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from otava.series import AnalysisOptions
import orion.constants as cnsts
from orion.algorithms.edivisive.edivisive import EDivisive
from orion.algorithms.edivisive.origEdivisive import OrigEDivisive
from orion.algorithms.algorithmFactory import AlgorithmFactory
from orion.run_test import get_algorithm_type
from orion.tests.conftest import make_change_point


def test_orig_edivisive_options_has_orig_flag():
    """OrigEDivisive._get_analysis_options() should return options with orig_edivisive=True."""
    algo = object.__new__(OrigEDivisive)
    options = algo._get_analysis_options()
    assert isinstance(options, AnalysisOptions)
    assert options.orig_edivisive is True


def test_edivisive_options_has_default():
    """EDivisive._get_analysis_options() should return default AnalysisOptions."""
    algo = object.__new__(EDivisive)
    options = algo._get_analysis_options()
    assert isinstance(options, AnalysisOptions)
    assert options.orig_edivisive is False


def test_factory_resolves_orig_edivisive():
    """AlgorithmFactory should resolve ORIG_EDIVISIVE to OrigEDivisive."""
    factory = AlgorithmFactory()
    with patch.object(OrigEDivisive, '__init__', return_value=None):
        algo = factory.instantiate_algorithm(
            cnsts.ORIG_EDIVISIVE,
            MagicMock(),
            {},
            {},
            {},
        )
    assert isinstance(algo, OrigEDivisive)


def test_get_algorithm_type_orig_analyze():
    """get_algorithm_type should return ORIG_EDIVISIVE when orig_analyze is True."""
    kwargs = {
        "hunter_analyze": False,
        "anomaly_detection": False,
        "cmr": False,
        "orig_analyze": True,
    }
    assert get_algorithm_type(kwargs) == cnsts.ORIG_EDIVISIVE


def test_get_algorithm_type_no_algorithm():
    """get_algorithm_type should return None when no algorithm flag is set."""
    kwargs = {
        "hunter_analyze": False,
        "anomaly_detection": False,
        "cmr": False,
        "orig_analyze": False,
    }
    assert get_algorithm_type(kwargs) is None


def _make_changepoint_without_metric(index, mean_1=100.0, mean_2=200.0):
    """Create a ChangePoint-like object without a .metric attribute.

    The original E-Divisive algorithm in otava can return ChangePoint
    objects that lack the .metric attribute (see GitHub issue #433).
    """
    cp = make_change_point("_placeholder", index, mean_1, mean_2)
    return SimpleNamespace(index=cp.index, qhat=cp.qhat, time=cp.time, stats=cp.stats)


def test_is_acked_without_metric_attribute():
    """_is_acked should work when ChangePoint has no .metric attribute (issue #433)."""
    algo = object.__new__(EDivisive)
    cp = _make_changepoint_without_metric(index=3)
    ack_set = {"3_some_metric"}

    assert algo._is_acked(ack_set, "some_metric", [cp], 0) is True
    assert algo._is_acked(ack_set, "other_metric", [cp], 0) is False


def test_is_acked_matches_index_and_metric():
    """_is_acked should match on both index and metric name."""
    algo = object.__new__(EDivisive)
    cp_at_5 = _make_changepoint_without_metric(index=5)
    ack_set = {"5_cpu_usage", "3_memory_usage"}

    assert algo._is_acked(ack_set, "cpu_usage", [cp_at_5], 0) is True
    assert algo._is_acked(ack_set, "memory_usage", [cp_at_5], 0) is False

    cp_at_3 = _make_changepoint_without_metric(index=3)
    assert algo._is_acked(ack_set, "memory_usage", [cp_at_3], 0) is True
