"""Statistical confidence indicators for changepoints."""

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy import stats


@dataclass
class ConfidenceResult: # pylint: disable=too-many-instance-attributes
    """Statistical confidence for a single changepoint."""

    p_value: Optional[float]
    cohens_d: Optional[float]
    confidence_label: str
    sufficient_data: bool
    sample_size_before: int
    sample_size_after: int
    mean_before: Optional[float] = None
    mean_after: Optional[float] = None
    std_before: Optional[float] = None
    std_after: Optional[float] = None
    ci_95: Optional[tuple] = None

    def to_dict(self):
        """Return dict suitable for JSON/regression-data output."""
        return {
            "p_value": self.p_value,
            "cohens_d": self.cohens_d,
            "label": self.confidence_label,
            "sufficient_data": self.sufficient_data,
            "sample_size_before": self.sample_size_before,
            "sample_size_after": self.sample_size_after,
            "mean_before": self.mean_before,
            "mean_after": self.mean_after,
            "std_before": self.std_before,
            "std_after": self.std_after,
            "ci_95": list(self.ci_95) if self.ci_95 is not None else None,
        }


def _map_label(p_value, cohens_d):
    """Map Cohen's d to a human-readable effect-size label.

    Cohen's d drives the label tier. p-value is included as
    descriptive context only — it is NOT calibrated for post-selection
    inference (the changepoint was selected from this same data).
    """
    if cohens_d is None:
        return "Degenerate variance — shift detected but effect size undefined"

    d_str = f"{cohens_d:.2f}"
    p_str = f"{p_value:.2g}" if p_value is not None else "n/a"
    if cohens_d >= 0.8:
        return f"Large shift (d={d_str}, p={p_str})"
    if cohens_d >= 0.5:
        return f"Moderate shift (d={d_str}, p={p_str})"
    if cohens_d >= 0.2:
        return f"Small shift (d={d_str}, p={p_str})"
    return f"Negligible shift (d={d_str}, p={p_str})"


def _get_segments(data, changepoint_index,
                  prev_boundary=0, next_boundary=None):
    """Split data into before/after segments.

    Segments are bounded by neighboring changepoints to prevent
    a later recovery from masking an earlier genuine shift.
    """
    if next_boundary is None:
        next_boundary = len(data)
    return data[prev_boundary:changepoint_index], data[changepoint_index:next_boundary]


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
            mean_before=float(np.mean(before)) if n_before > 0 else None,
            mean_after=float(np.mean(after)) if n_after > 0 else None,
            std_before=float(np.std(before, ddof=1)) if n_before > 1 else None,
            std_after=float(np.std(after, ddof=1)) if n_after > 1 else None,
        )

    mean_before = np.mean(before)
    mean_after = np.mean(after)
    std_before = np.std(before, ddof=1)
    std_after = np.std(after, ddof=1)
    pooled_std = math.sqrt(
        ((n_before - 1) * std_before ** 2 + (n_after - 1) * std_after ** 2)
        / (n_before + n_after - 2)
    )

    if pooled_std == 0 and mean_before != mean_after:
        p_value = None
        cohens_d = None
    elif pooled_std == 0:
        p_value = 1.0
        cohens_d = 0.0
    elif std_before == 0 or std_after == 0:
        se = math.sqrt(std_before ** 2 / n_before + std_after ** 2 / n_after)
        t_stat = abs(mean_after - mean_before) / se
        if std_before == 0:
            welch_df = n_after - 1
        else:
            welch_df = n_before - 1
        p_value = float(2 * stats.t.sf(t_stat, welch_df))
        cohens_d = abs(mean_after - mean_before) / pooled_std
        if math.isnan(p_value):
            p_value = 1.0
    else:
        _, p_value = stats.ttest_ind(before, after, equal_var=False)
        cohens_d = abs(mean_after - mean_before) / pooled_std
        if math.isnan(p_value):
            p_value = 1.0

    label = _map_label(p_value, cohens_d)

    ci_95 = None
    se = math.sqrt(std_before ** 2 / n_before + std_after ** 2 / n_after)
    if se > 0:
        mean_diff = float(mean_after - mean_before)
        df_num = (std_before ** 2 / n_before + std_after ** 2 / n_after) ** 2
        df_den = (
            (std_before ** 2 / n_before) ** 2 / (n_before - 1)
            + (std_after ** 2 / n_after) ** 2 / (n_after - 1)
        )
        welch_df = df_num / df_den if df_den > 0 else 1.0
        t_crit = stats.t.ppf(0.975, welch_df)
        ci_95 = (mean_diff - t_crit * se, mean_diff + t_crit * se)

    return ConfidenceResult(
        p_value=p_value,
        cohens_d=cohens_d,
        confidence_label=label,
        sufficient_data=True,
        sample_size_before=n_before,
        sample_size_after=n_after,
        mean_before=float(mean_before),
        mean_after=float(mean_after),
        std_before=float(std_before),
        std_after=float(std_after),
        ci_95=ci_95,
    )


def compute_confidence(dataframe, change_points_by_metric,
                       raw_change_points_by_metric=None):
    """Compute confidence indicators for all changepoints.

    raw_change_points_by_metric: unfiltered detector boundaries. When
    provided, segment boundaries are derived from ALL detector-found
    changepoints so that a filtered recovery still bounds the window.

    Returns dict keyed by metric name, index-aligned with
    change_points_by_metric.
    """
    result = {}

    for metric, cps in change_points_by_metric.items():
        if metric not in dataframe.columns:
            result[metric] = [
                ConfidenceResult(
                    p_value=None, cohens_d=None,
                    confidence_label="Insufficient data",
                    sufficient_data=False,
                    sample_size_before=0, sample_size_after=0,
                ) for _ in cps
            ]
            continue

        data = dataframe[metric].values
        raw_cps = (raw_change_points_by_metric or {}).get(metric, cps)
        all_boundaries = sorted(set(cp.index for cp in raw_cps))

        metric_results = []
        for cp in cps:
            prev_boundary = 0
            next_boundary = len(data)
            for b in all_boundaries:
                if b < cp.index:
                    prev_boundary = b
                elif b > cp.index:
                    next_boundary = b
                    break
            before, after = _get_segments(
                data, cp.index, prev_boundary, next_boundary
            )
            before = before[~np.isnan(before)]
            after = after[~np.isnan(after)]
            metric_results.append(_compute_stats(before, after))
        result[metric] = metric_results
    return result
