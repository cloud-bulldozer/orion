"""AnalysisResult dataclass and standalone utility functions."""

from dataclasses import dataclass
from itertools import groupby
from typing import Dict, List
import pandas as pd
from otava.series import Series, ChangePoint, ChangePointGroup


@dataclass
class AnalysisResult: # pylint: disable=too-many-instance-attributes
    """Carries all raw analysis results without formatting.

    No algorithm or infrastructure references - pure data.
    """

    test_name: str
    test: dict
    dataframe: pd.DataFrame
    metrics_config: dict
    change_points_by_metric: dict
    series: Series
    regression_flag: bool
    avg_values: pd.Series

    collapse: bool
    display_fields: list
    column_group_size: int
    uuid_field: str
    version_field: str
    sippy_pr_search: bool
    github_repos: list


def group_change_points_by_time(
    series: Series,
    change_points: Dict[str, List[ChangePoint]],
) -> List[ChangePointGroup]:
    """Group change points from different metrics that occur at the same index.

    Extracted from Algorithm.group_change_points_by_time() - same logic,
    no self dependency.
    """
    changes: List[ChangePoint] = []
    for metric in change_points.keys():
        changes += change_points[metric]

    changes.sort(key=lambda c: c.index)
    points = []
    for k, g in groupby(changes, key=lambda c: c.index):
        cp = ChangePointGroup(
            index=k,
            time=series.time[k],
            prev_time=series.time[k - 1],
            attributes=series.attributes_at(k),
            prev_attributes=series.attributes_at(k - 1),
            changes=list(g),
        )
        points.append(cp)

    return points
