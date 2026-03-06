"""
orion.report

Module for generating regression reports from orion JSON output files.
Supports both standalone mode (reading pre-existing JSON files) and
integrated mode (processing results from an orion run).
"""

import json
import os
import sys

from tabulate import tabulate

# Box-drawing characters for report formatting
_BOX_TOP_LEFT = "\u2554"
_BOX_TOP_RIGHT = "\u2557"
_BOX_BOTTOM_LEFT = "\u255a"
_BOX_BOTTOM_RIGHT = "\u255d"
_BOX_HORIZONTAL = "\u2550"
_BOX_VERTICAL = "\u2551"
_SECTION_DASH = "\u2500"


def load_json_files(file_paths: list[str]) -> dict[str, list]:
    """Load multiple orion JSON output files.

    Args:
        file_paths: list of paths to JSON files

    Returns:
        dict mapping workload name to parsed JSON array
    """
    data = {}
    for path in file_paths:
        if not os.path.exists(path):
            print(f"Warning: file not found: {path}", file=sys.stderr)
            continue
        workload = _derive_workload_name(path)
        with open(path, "r", encoding="utf-8") as f:
            try:
                parsed = json.load(f)
                if isinstance(parsed, list):
                    data[workload] = parsed
                else:
                    print(f"Warning: expected JSON array in {path}, skipping", file=sys.stderr)
            except json.JSONDecodeError as e:
                print(f"Warning: invalid JSON in {path}: {e}", file=sys.stderr)
    return data


def _derive_workload_name(file_path: str) -> str:
    """Derive a human-readable workload name from a JSON file path."""
    name = os.path.splitext(os.path.basename(file_path))[0]
    for prefix in ["orion-", "junit_", "output_"]:
        if name.startswith(prefix):
            name = name[len(prefix):]
    if name.endswith("-junit"):
        name = name[:-len("-junit")]
    return name


def extract_changepoints(data: list[dict]) -> list[dict]:
    """Extract changepoint entries with regressed metrics from orion JSON data.

    Args:
        data: parsed orion JSON array (list of data point dicts)

    Returns:
        list of changepoint dicts with regressed metric details
    """
    changepoints = []
    for i, entry in enumerate(data):
        if not entry.get("is_changepoint"):
            continue

        regressed = {
            name: info for name, info in entry.get("metrics", {}).items()
            if info.get("percentage_change", 0) != 0
        }
        if not regressed:
            continue

        github_ctx = entry.get("github_context", {})
        current_version = (github_ctx.get("current_version", "")
                          or entry.get("ocpVersion", "unknown"))
        previous_version = github_ctx.get("previous_version", "")
        if not previous_version and i > 0:
            previous_version = data[i - 1].get("ocpVersion", "unknown")

        changepoints.append({
            "current_version": current_version,
            "previous_version": previous_version,
            "build_url": entry.get("buildUrl", ""),
            "prs": entry.get("prs", []),
            "regressed_metrics": regressed,
        })

    return changepoints


def _format_metric_value(value) -> str:
    """Format a metric value for display."""
    if not isinstance(value, float):
        return str(value)
    if abs(value) >= 1000000:
        return f"{value:,.0f}"
    if abs(value) >= 1:
        return f"{value:.4f}"
    return f"{value:.10f}".rstrip("0").rstrip(".")


def _extract_components(regressed_metrics: dict) -> set[str]:
    """Extract component names from regressed metrics' labels.

    Parses labels like '[Jira: Networking / ovn-kubernetes]' into
    component names like {'networking', 'ovn-kubernetes'}.
    """
    components = set()
    for metric_info in regressed_metrics.values():
        label = metric_info.get("labels", "")
        for part in label.replace("[", "").replace("]", "").split("/"):
            part = part.strip().lower()
            if part and part != "jira:":
                components.add(part)
    return components


def _sort_prs_by_relevance(prs: list[str], components: set[str]) -> tuple[list[str], list[str]]:
    """Split PRs into component-related and others.

    Returns:
        tuple of (matching_prs, other_prs)
    """
    matching, others = [], []
    for pr_url in prs:
        parts = pr_url.rstrip("/").split("/")
        repo_name = parts[-3].lower() if len(parts) >= 4 else ""
        if any(comp in repo_name or repo_name in comp for comp in components):
            matching.append(pr_url)
        else:
            others.append(pr_url)
    return matching, others


def _print_changepoint(cp: dict) -> None:
    """Print a single changepoint's details."""
    print(f"  Changepoint at: {cp['current_version']}")
    if cp["previous_version"]:
        print(f"  Previous:       {cp['previous_version']}")
    if cp["build_url"]:
        print(f"  Build:          {cp['build_url']}")
    print()

    # Metrics table
    table_data = []
    for metric_name, metric_info in cp["regressed_metrics"].items():
        pct = metric_info.get("percentage_change", 0)
        sign = "+" if pct > 0 else ""
        table_data.append([
            metric_name,
            _format_metric_value(metric_info.get("value", "N/A")),
            f"{sign}{pct:.2f}%",
            metric_info.get("labels", "").strip("[]"),
        ])
    print(tabulate(table_data, headers=["Metric", "Value", "Change", "Owner"], tablefmt="grid"))
    print()

    # PRs sorted by relevance
    if cp["prs"]:
        components = _extract_components(cp["regressed_metrics"])
        matching_prs, other_prs = _sort_prs_by_relevance(cp["prs"], components)

        if matching_prs:
            print(f"  Related PRs ({len(matching_prs)}):")
            for pr_url in matching_prs:
                print(f"    * {pr_url}")
        if other_prs:
            print(f"  Other PRs in payload ({len(other_prs)}):")
            for pr_url in other_prs:
                print(f"    - {pr_url}")
        print()


def generate_report(json_data_by_workload: dict[str, list]) -> bool:
    """Generate a regression report from orion JSON data.

    Args:
        json_data_by_workload: dict mapping workload name to parsed JSON array

    Returns:
        True if any regressions were found, False otherwise
    """
    print()
    print(_BOX_TOP_LEFT + _BOX_HORIZONTAL * 52 + _BOX_TOP_RIGHT)
    print(_BOX_VERTICAL + "Orion Regression Report".center(52) + _BOX_VERTICAL)
    print(_BOX_BOTTOM_LEFT + _BOX_HORIZONTAL * 52 + _BOX_BOTTOM_RIGHT)
    print()

    regression_count = 0
    pass_count = 0
    skip_count = 0

    for workload, data in sorted(json_data_by_workload.items()):
        if not data:
            print(f"{_SECTION_DASH*3} {workload} {_SECTION_DASH*3} SKIP (no data)")
            print()
            skip_count += 1
            continue

        changepoints = extract_changepoints(data)

        if not changepoints:
            print(f"{_SECTION_DASH*3} {workload} {_SECTION_DASH*3} PASS (no changepoints)")
            print()
            pass_count += 1
            continue

        print(f"{_SECTION_DASH*3} {workload} {_SECTION_DASH*3} REGRESSION DETECTED")
        print()
        regression_count += 1

        for cp in changepoints:
            _print_changepoint(cp)

    total = regression_count + pass_count + skip_count
    print(_BOX_HORIZONTAL * 54)
    print(
        f" Summary: {total} workloads | "
        f"{regression_count} REGRESSION | "
        f"{pass_count} PASS | "
        f"{skip_count} SKIP"
    )
    print(_BOX_HORIZONTAL * 54)
    print()

    return regression_count > 0
