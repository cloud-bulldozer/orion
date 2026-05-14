"""
orion.reporting.standalone

Module for generating standalone regression reports from orion JSON output files.
"""

import json
import os

from orion.logger import SingletonLogger
from .summary import print_regression_summary

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
    logger = SingletonLogger.get_logger("Orion")
    data = {}
    for path in file_paths:
        if not os.path.exists(path):
            logger.warning("File not found: %s", path)
            continue
        workload = _derive_workload_name(path)
        with open(path, "r", encoding="utf-8") as f:
            try:
                parsed = json.load(f)
                if isinstance(parsed, list):
                    data[workload] = parsed
                else:
                    logger.warning("Expected JSON array in %s, skipping", path)
            except json.JSONDecodeError as e:
                logger.warning("Invalid JSON in %s: %s", path, e)
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


def extract_regression_data(workload: str, data: list[dict]) -> list[dict]:
    """Extract regression data from orion JSON in the canonical regression_data format.

    Converts raw JSON changepoint entries into the same dict format used by
    orion's normal run path (run_test.py), so print_regression_summary can
    render them identically.

    Args:
        workload: workload/test name
        data: parsed orion JSON array (list of data point dicts)

    Returns:
        list of regression_data dicts compatible with print_regression_summary
    """
    regressions = []
    for i, entry in enumerate(data):
        if not entry.get("is_changepoint"):
            continue

        metrics_with_change = []
        for name, info in entry.get("metrics", {}).items():
            if info.get("percentage_change", 0) != 0:
                metrics_with_change.append({
                    "name": name,
                    "value": info.get("value"),
                    "percentage_change": info.get("percentage_change", 0),
                    "labels": info.get("labels", ""),
                })

        if not metrics_with_change:
            continue

        github_ctx = entry.get("github_context") or {}
        current_version = (github_ctx.get("current_version", "")
                          or entry.get("ocpVersion", "unknown"))
        previous_version = github_ctx.get("previous_version", "")
        if not previous_version and i > 0:
            previous_version = data[i - 1].get("ocpVersion", "unknown")

        regressions.append({
            "test_name": workload,
            "bad_ver": current_version,
            "prev_ver": previous_version,
            "build_url": entry.get("buildUrl", ""),
            "metrics_with_change": metrics_with_change,
            "prs": entry.get("prs", []),
            "github_context": entry.get("github_context"),
        })

    return regressions


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

        regressions = extract_regression_data(workload, data)

        if not regressions:
            print(f"{_SECTION_DASH*3} {workload} {_SECTION_DASH*3} PASS (no changepoints)")
            print()
            pass_count += 1
            continue

        print(f"{_SECTION_DASH*3} {workload} {_SECTION_DASH*3} REGRESSION DETECTED")
        print()
        regression_count += 1

        print_regression_summary(regressions)
        print()

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
