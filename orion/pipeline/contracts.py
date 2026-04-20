"""Typed contracts for inter-stage data in the Orion pipeline."""

# pylint: disable=too-many-instance-attributes

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ESClientConfig:
    """ES/OpenSearch connection parameters."""

    server: str
    metadata_index: str
    benchmark_index: str
    verified: bool


@dataclass(frozen=True)
class GitHubClientConfig:
    """GitHub API connection parameters."""

    token: str
    repos: list[str]
    verified: bool


@dataclass(frozen=True)
class PRAnalysisVars:
    """PR-specific metadata filters for PR analysis mode."""

    job_type: str
    pull_number: str
    organization: str
    repository: str


@dataclass(frozen=True)
class CLIOptions:
    """All CLI options passed through the pipeline."""

    output_format: str
    save_output_path: str | None
    collapse: bool
    viz: bool
    debug: bool
    lookback: str | None
    since: str | None
    lookback_size: int | None
    uuid: str | None
    baseline: str | None
    pr_analysis: bool
    pr_vars: PRAnalysisVars | None
    convert_tinyurl: bool
    display: bool
    node_count: int | None
    filter_args: str | None
    anomaly_window: int
    min_anomaly_percent: float
    ack_map: dict[str, list[str]]
    no_default_ack: bool


@dataclass(frozen=True)
class MetricConfig:
    """Single metric definition from the YAML config."""

    name: str
    metric_name: str
    metric_of_interest: str
    direction: int
    threshold: float
    labels: list[str]
    correlation: str | None
    context: int | None
    agg: dict[str, Any] | None


@dataclass(frozen=True)
class TestConfig:
    """Validated test definition with metadata filters and metrics."""

    name: str
    metadata: dict[str, Any]
    metrics: list[MetricConfig]
    metadata_index: str
    benchmark_index: str


@dataclass(frozen=True)
class ValidationResult:
    """Output of the Validation stage."""

    config: dict[str, Any]
    tests: list[TestConfig]
    es_client: ESClientConfig
    github_client: GitHubClientConfig | None
    algorithm_type: str
    cli_options: CLIOptions


@dataclass(frozen=True)
class LookbackParams:
    """Lookback window configuration, carried for expansion decisions."""

    lookback: str | None
    since: str | None
    lookback_size: int | None
    unbounded: bool
    pr_creation_date: str | None


@dataclass(frozen=True)
class GatheredData:
    """Output of the Gathering stage."""

    test_name: str
    test_config: TestConfig
    dataframe: pd.DataFrame
    metrics: list[MetricConfig]
    uuids: list[str]
    lookback_params: LookbackParams


@dataclass(frozen=True)
class RawChangePoint:
    """Algorithm output before percent_change is computed."""

    metric: str
    index: int
    timestamp: datetime
    mean_before: float
    mean_after: float
    uuid: str


@dataclass(frozen=True)
class ChangePoint:
    """Computed from RawChangePoint with percent_change and direction."""

    metric: str
    index: int
    timestamp: datetime
    percent_change: float
    direction: int
    uuid: str
    mean_before: float
    mean_after: float


@dataclass(frozen=True)
class AnalysisResult:
    """Output of the Analysis stage."""

    test_name: str
    test_config: TestConfig
    algorithm_type: str
    changepoints: list[ChangePoint]
    series_data: pd.DataFrame
    average_values: dict[str, float]
    needs_expansion: bool
    expanded: bool


@dataclass(frozen=True)
class TransformedResult:
    """Output of the Transformation stage."""

    test_name: str
    changepoints: list[ChangePoint]
    series_data: pd.DataFrame
    average_values: dict[str, float]
    github_context: dict[str, Any] | None
    collapsed: bool
    has_regression: bool


@dataclass(frozen=True)
class PRAnalysisResult:
    """Combined result for PR analysis mode."""

    test_name: str
    periodic: TransformedResult | None
    periodic_avg: dict[str, float]
    pull: TransformedResult | None
    has_regression: bool
