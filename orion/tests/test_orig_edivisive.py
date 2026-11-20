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


def test_edivisive_default_options_match_analyze_defaults():
    """EDivisive._get_analysis_options() must match the defaults of Series.analyze().

    series.analyze() and series.analyze(AnalysisOptions()) must produce
    identical results so that the refactored call path (_get_analysis_options)
    does not silently change behavior for the base EDivisive algorithm.
    """
    from otava.series import Series, Metric  # pylint: disable=import-outside-toplevel

    times = list(range(1, 21))
    values = [10.0] * 10 + [20.0] * 10
    metrics = {"cpu": Metric(direction=1, scale=1.0)}
    data = {"cpu": values}
    attrs = {"uuid": [f"uuid-{i}" for i in range(20)]}

    series = Series("test", None, times, metrics, data, attrs)

    algo = object.__new__(EDivisive)
    result_no_args = series.analyze()
    result_explicit = series.analyze(algo._get_analysis_options())

    assert result_no_args.change_points == result_explicit.change_points


def test_orig_edivisive_options_differ_from_default():
    """OrigEDivisive._get_analysis_options() must differ from the base default.

    Ensures the orig_edivisive flag is the only difference, confirming the
    subclass override is intentional and targeted.
    """
    base_algo = object.__new__(EDivisive)
    orig_algo = object.__new__(OrigEDivisive)

    base_opts = base_algo._get_analysis_options()
    orig_opts = orig_algo._get_analysis_options()

    assert base_opts.orig_edivisive is False
    assert orig_opts.orig_edivisive is True
    assert base_opts.window_len == orig_opts.window_len
    assert base_opts.max_pvalue == orig_opts.max_pvalue
    assert base_opts.min_magnitude == orig_opts.min_magnitude


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
        "orig_analyze": True,
    }
    assert get_algorithm_type(kwargs) == cnsts.ORIG_EDIVISIVE


def test_get_algorithm_type_no_algorithm():
    """get_algorithm_type should return None when no algorithm flag is set."""
    kwargs = {
        "hunter_analyze": False,
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
