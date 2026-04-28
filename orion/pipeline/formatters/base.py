"""Base formatter ABC with shared regression data extraction."""

from abc import ABC, abstractmethod
from typing import Any, Optional

from orion.pipeline.analysis_result import AnalysisResult
from orion.github_client import GitHubClient
from orion.utils import Utils


class BaseFormatter(ABC):
    """Abstract base for all output formatters."""

    @abstractmethod
    def format(self, data: AnalysisResult) -> dict:
        """Format analysis results. Returns {test_name: formatted_output}."""

    @abstractmethod
    def format_average(self, data: AnalysisResult) -> Any:
        """Format average values for this output type."""

    @abstractmethod
    def save(self, test_name: str, formatted: Any,
             save_output_path: str) -> None:
        """Save formatted output to file."""

    @abstractmethod
    def print_output(self, test_name: str, formatted: Any,
                     data: AnalysisResult, pr: int = 0,
                     is_pull: bool = False) -> None:
        """Print formatted output to stdout."""

    @abstractmethod
    def print_and_save_pr(self, periodic: AnalysisResult,
                          pull: Optional[AnalysisResult],
                          save_output_path: str,
                          pr: int = 0) -> None:
        """Format, print, and save combined PR output (periodic + pull)."""

    def extract_regression_data(self, data: AnalysisResult) -> list:
        """Extract regression data from raw change points and dataframe."""
        if not data.regression_flag:
            return []

        regression_data = []
        seen_indices = set()
        github_client = self._get_github_client(data.github_repos)

        for metric, cps in data.change_points_by_metric.items():
            for cp in cps:
                index = cp.index
                percentage_change = (
                    (cp.stats.mean_2 - cp.stats.mean_1)
                    / cp.stats.mean_1
                ) * 100

                if index in seen_indices:
                    for reg in regression_data:
                        if reg["uuid"] == data.dataframe.iloc[index][data.uuid_field]:
                            reg["metrics_with_change"].append({
                                "name": metric,
                                "value": data.dataframe.iloc[index][metric],
                                "percentage_change": percentage_change,
                                "labels": data.metrics_config[metric].get(
                                    "labels") or [],
                            })
                    continue

                seen_indices.add(index)
                row = data.dataframe.iloc[index]
                bad_ver = row.get(data.version_field, "unknown")
                prev_ver = None
                if index > 0:
                    prev_row = data.dataframe.iloc[index - 1]
                    prev_ver = prev_row.get(data.version_field, "unknown")

                benchmark_type = data.test.get(
                    "metadata", {}).get("benchmark.keyword", "")

                doc = {
                    "test_name": data.test_name,
                    "benchmark_type": benchmark_type if benchmark_type else None,
                    "prev_ver": prev_ver,
                    "bad_ver": bad_ver,
                    "buildUrl": row.get("buildUrl"),
                    "metrics_with_change": [{
                        "name": metric,
                        "value": row.get(metric),
                        "percentage_change": percentage_change,
                        "labels": data.metrics_config[metric].get("labels") or [],
                    }],
                    "prs": [],
                    "github_context": None,
                    "uuid": row.get(data.uuid_field),
                    "timestamp": row.get("timestamp"),
                }
                prs = row.get("prs")
                if prs is not None:
                    doc["prs"] = prs

                if data.sippy_pr_search and prev_ver and bad_ver:
                    sippy_prs = Utils().sippy_pr_diff(prev_ver, bad_ver)
                    if sippy_prs:
                        doc["prs"] = sippy_prs

                if github_client:
                    previous_row = (
                        data.dataframe.iloc[index - 1] if index > 0 else None
                    )
                    context = github_client.get_change_context(
                        previous_timestamp=(
                            previous_row.get("timestamp")
                            if previous_row is not None else None
                        ),
                        current_timestamp=row.get("timestamp"),
                        previous_version=(
                            previous_row.get(data.version_field)
                            if previous_row is not None else None
                        ),
                        current_version=row.get(data.version_field),
                    )
                    if context:
                        doc["github_context"] = context

                regression_data.append(doc)

        return regression_data

    @staticmethod
    def _get_github_client(
        github_repos: list,
    ) -> Optional[GitHubClient]:
        repositories = github_repos or []
        if not repositories or repositories == [""]:
            return None
        return GitHubClient(list(repositories))
