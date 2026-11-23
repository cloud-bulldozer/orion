"""Tests for acceptable value range filtering."""

import pandas as pd
import pytest

from orion.algorithms.edivisive.edivisive import EDivisive
from orion.tests.conftest import make_change_point
from orion.utils import Utils


def _algorithm(metric_config):
    """Create an EDivisive instance with a small metric dataframe."""
    algorithm = object.__new__(EDivisive)
    algorithm.metrics_config = {"metric": metric_config}
    algorithm.dataframe = pd.DataFrame({"metric": [5.0, 11.0]})
    return algorithm


def test_steps_outside_acceptable_range():
    """Report a changepoint whose actual value is above the maximum."""
    algorithm = _algorithm({"acceptable_range": (0.0, 10.0)})
    change_point = make_change_point("metric", 1, mean_1=5.0, mean_2=6.0)

    assert algorithm._steps_outside_acceptable_range("metric", change_point)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_acceptable_range_rejects_non_finite_bounds(value):
    """Reject bounds that cannot produce meaningful range comparisons."""
    with pytest.raises(ValueError, match="finite"):
        Utils._parse_acceptable_range([0.0, value])


def test_actual_value_inside_range_is_ignored_even_if_mean_is_outside():
    """Ignore an in-range actual value even when the segment mean is outside."""
    algorithm = _algorithm({"acceptable_range": (0.0, 10.0)})
    change_point = make_change_point("metric", 1, mean_1=5.0, mean_2=100.0)

    algorithm.dataframe.loc[1, "metric"] = 8.0
    assert not algorithm._steps_outside_acceptable_range("metric", change_point)


@pytest.mark.parametrize(
    ("mean_1", "mean_2", "actual_value", "expected"),
    [
        (0.0, 100.0, 0.0, False),
        (10.0, -100.0, 10.0, False),
        (5.0, 0.0, 0.0, False),
        (5.0, 10.0, 10.0, False),
        (5.0, 10.0, -0.1, True),
        (5.0, 10.0, 10.1, True),
    ],
)
def test_range_bounds_are_inclusive(mean_1, mean_2, actual_value, expected):
    """Use actual changepoint values when checking inclusive range bounds."""
    algorithm = _algorithm({"acceptable_range": (0.0, 10.0)})
    algorithm.dataframe.loc[1, "metric"] = actual_value
    change_point = make_change_point("metric", 1, mean_1=mean_1, mean_2=mean_2)

    assert bool(algorithm._steps_outside_acceptable_range("metric", change_point)) is expected


def test_edivisive_irrelevant_filter_uses_actual_value():
    """EDivisive keeps range violations even when means suggest otherwise."""
    algorithm = _algorithm({
        "direction": 1,
        "threshold": 100,
        "acceptable_range": (0.0, 10.0),
    })
    algorithm.dataframe.loc[1, "metric"] = -1.0
    change_point = make_change_point("metric", 1, mean_1=5.0, mean_2=100.0)

    assert not algorithm._is_irrelevant_changepoint("metric", [change_point], 0)
