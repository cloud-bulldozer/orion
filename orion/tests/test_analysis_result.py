"""Tests for AnalysisResult and group_change_points_by_time."""

import pandas as pd
from otava.series import Series, Metric

from orion.tests.conftest import make_change_point


def _make_series():
    return Series(
        test_name="test",
        branch=None,
        time=[1000, 2000, 3000, 4000],
        metrics={"cpu": Metric(1, 1.0)},
        data={"cpu": pd.Series([10, 20, 30, 40])},
        attributes={"uuid": pd.Series(["a", "b", "c", "d"])},
    )


def test_analysis_result_creation():
    from orion.pipeline.analysis_result import AnalysisResult

    df = pd.DataFrame({"uuid": ["a"], "timestamp": [1000], "cpu": [10.0]})
    series = _make_series()

    result = AnalysisResult(
        test_name="test",
        test={"name": "test", "uuid_field": "uuid", "version_field": "ver"},
        dataframe=df,
        metrics_config={"cpu": {"direction": 1, "labels": []}},
        change_points_by_metric={},
        series=series,
        regression_flag=False,
        avg_values=pd.Series({"cpu": 10.0}),
        collapse=False,
        display_fields=[],
        column_group_size=5,
        uuid_field="uuid",
        version_field="ver",
        sippy_pr_search=False,
        github_repos=[],
    )

    assert result.test_name == "test"
    assert result.regression_flag is False
    assert result.collapse is False


def test_group_change_points_by_time_groups_same_index():
    from orion.pipeline.analysis_result import group_change_points_by_time

    series = _make_series()
    cp1 = make_change_point("cpu", index=2)
    cp2 = make_change_point("memory", index=2)
    change_points = {"cpu": [cp1], "memory": [cp2]}

    groups = group_change_points_by_time(series, change_points)

    assert len(groups) == 1
    assert groups[0].index == 2
    assert len(groups[0].changes) == 2


def test_group_change_points_by_time_different_indices():
    from orion.pipeline.analysis_result import group_change_points_by_time

    series = _make_series()
    cp1 = make_change_point("cpu", index=1)
    cp2 = make_change_point("cpu", index=3)
    change_points = {"cpu": [cp1, cp2]}

    groups = group_change_points_by_time(series, change_points)

    assert len(groups) == 2
    assert groups[0].index == 1
    assert groups[1].index == 3


def test_group_change_points_by_time_empty():
    from orion.pipeline.analysis_result import group_change_points_by_time

    series = _make_series()
    change_points = {"cpu": []}

    groups = group_change_points_by_time(series, change_points)

    assert len(groups) == 0
