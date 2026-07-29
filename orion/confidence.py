"""Statistical confidence indicators for changepoints."""

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy import stats

import orion.constants as cnsts


@dataclass
class ConfidenceResult:
    """Statistical confidence for a single changepoint."""

    p_value: Optional[float]
    cohens_d: Optional[float]
    confidence_label: str
    sufficient_data: bool
    sample_size_before: int
    sample_size_after: int

    def to_dict(self):
        """Return dict suitable for JSON/regression-data output."""
        return {
            "p_value": self.p_value,
            "cohens_d": self.cohens_d,
            "label": self.confidence_label,
            "sufficient_data": self.sufficient_data,
            "sample_size_before": self.sample_size_before,
            "sample_size_after": self.sample_size_after,
        }


def _map_label(p_value, cohens_d):
    """Map p-value and Cohen's d to a human-readable confidence label."""
    d_str = f"{cohens_d:.2f}" if not math.isinf(cohens_d) else "inf"
    p_str = f"{p_value:.2f}"
    if p_value >= 0.05:
        return f"Noise [{d_str}] (trivial shift [{p_str}])"
    if cohens_d >= 0.8:
        return f"Likely real [{d_str}] (large shift [{p_str}])"
    if cohens_d >= 0.5:
        return f"Likely real [{d_str}] (moderate shift [{p_str}])"
    if cohens_d >= 0.2:
        return f"Possible [{d_str}] (small shift [{p_str}])"
    return f"Statistically significant [{d_str}] but trivial [{p_str}]"


def _get_segments(algorithm_name, data, changepoint_index):
    """Split data into before/after segments based on algorithm type."""
    if algorithm_name == cnsts.CMR:
        return data[:-1], data[-1:]
    return data[:changepoint_index], data[changepoint_index:]


def _compute_stats(before, after):
    """Compute Welch's t-test and Cohen's d for two data segments."""
    n_before = len(before)
    n_after = len(after)

    if n_before < 2 or n_after < 2:
        return ConfidenceResult(
            p_value=None,
            cohens_d=None,
            confidence_label="Insufficient data",
            sufficient_data=False,
            sample_size_before=n_before,
            sample_size_after=n_after,
        )

    _, p_value = stats.ttest_ind(before, after, equal_var=False)

    mean_before = np.mean(before)
    mean_after = np.mean(after)
    std_before = np.std(before, ddof=1)
    std_after = np.std(after, ddof=1)
    pooled_std = math.sqrt(
        ((n_before - 1) * std_before ** 2 + (n_after - 1) * std_after ** 2)
        / (n_before + n_after - 2)
    )

    if pooled_std == 0:
        cohens_d = (
            float("inf") if mean_before != mean_after else 0.0
        )
    else:
        cohens_d = abs(mean_after - mean_before) / pooled_std

    if math.isnan(p_value):
        p_value = 1.0

    label = _map_label(p_value, cohens_d)

    return ConfidenceResult(
        p_value=p_value,
        cohens_d=cohens_d,
        confidence_label=label,
        sufficient_data=True,
        sample_size_before=n_before,
        sample_size_after=n_after,
    )


def compute_confidence(algorithm_name, dataframe, change_points_by_metric):
    """Compute confidence indicators for all changepoints.

    Returns dict keyed by metric name, index-aligned with
    change_points_by_metric.
    """
    result = {}
    for metric, cps in change_points_by_metric.items():
        metric_results = []
        if metric not in dataframe.columns:
            for _ in cps:
                metric_results.append(ConfidenceResult(
                    p_value=None, cohens_d=None,
                    confidence_label="Insufficient data",
                    sufficient_data=False,
                    sample_size_before=0, sample_size_after=0,
                ))
            result[metric] = metric_results
            continue

        data = dataframe[metric].values
        for cp in cps:
            before, after = _get_segments(
                algorithm_name, data, cp.index
            )
            before = before[~np.isnan(before)]
            after = after[~np.isnan(after)]
            metric_results.append(_compute_stats(before, after))
        result[metric] = metric_results
    return result
