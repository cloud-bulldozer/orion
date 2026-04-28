"""
run test
"""
import sys
import copy
import concurrent.futures
from typing import Any, Dict, NamedTuple, Tuple
from orion.matcher import Matcher
from orion.logger import SingletonLogger
from orion.algorithms import AlgorithmFactory
import orion.constants as cnsts
from orion.utils import Utils, get_subtracted_timestamp
from orion.github_client import GitHubClient
from orion.visualization import VizData
from orion.pipeline.analysis_result import AnalysisResult


class TestResults(NamedTuple):
    """Return type for run() results tuples."""
    __test__ = False
    analyses: list
    regression_flag: bool
    pr: int
    viz_data: list


def get_algorithm_type(kwargs):
    """Switch Case of getting algorithm name

    Args:
        kwargs (dict): passed command line arguments

    Returns:
        str: algorithm name
    """
    if kwargs["hunter_analyze"]:
        algorithm_name = cnsts.EDIVISIVE
    elif kwargs["anomaly_detection"]:
        algorithm_name = cnsts.ISOLATION_FOREST
    elif kwargs['cmr']:
        algorithm_name = cnsts.CMR
    else:
        algorithm_name = None
    return algorithm_name

# pylint: disable=too-many-locals
def run(**kwargs: dict[str, Any]) -> Tuple[TestResults, TestResults]:
    """Run tests and return raw analysis results.

    Returns two TestResults: (standard_results, pull_request_results).
    """
    config = kwargs["config"]
    pr_analysis = kwargs["pr_analysis"]

    logger = SingletonLogger.get_logger("Orion")
    analyses = []
    analyses_pull = []
    regression_flag = False
    regression_flag_pull = False
    all_viz_data = []
    all_viz_data_pull = []
    pr = 0

    for test in config["tests"]:
        if "metadata" in test:
            if pr_analysis:
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=2
                ) as executor:
                    logger.info("Executing tasks in parallel...")
                    logger.info("Ensuring jobType is set to pull")
                    test["metadata"]["jobType"] = "pull"
                    futures_pull = executor.submit(
                        analyze, test, kwargs, True
                    )
                    pr = test["metadata"]["pullNumber"]
                    test_periodic = copy.deepcopy(test)
                    test_periodic["metadata"]["jobType"] = "periodic"
                    test_periodic["metadata"]["pullNumber"] = 0
                    test_periodic["metadata"]["organization"] = ""
                    test_periodic["metadata"]["repository"] = ""
                    futures_periodic = executor.submit(
                        analyze, test_periodic, kwargs, False
                    )
                    concurrent.futures.wait(
                        [futures_pull, futures_periodic]
                    )
                    pull_result_tuple = futures_pull.result()
                    periodic_result_tuple = futures_periodic.result()

                    pull_analysis, pull_viz = pull_result_tuple
                    periodic_analysis, periodic_viz = periodic_result_tuple

                    if pull_analysis is not None:
                        analyses_pull.append(pull_analysis)
                        if pull_analysis.regression_flag:
                            regression_flag_pull = True
                    if periodic_analysis is not None:
                        analyses.append(periodic_analysis)
                        if periodic_analysis.regression_flag:
                            regression_flag = True
                    if pull_viz is not None:
                        all_viz_data_pull.append(pull_viz)
                    if periodic_viz is not None:
                        all_viz_data.append(periodic_viz)
            else:
                result_tuple = analyze(test, kwargs)
                analysis, viz_data = result_tuple
                if analysis is not None:
                    analyses.append(analysis)
                    if analysis.regression_flag:
                        regression_flag = True
                if viz_data is not None:
                    all_viz_data.append(viz_data)

    results_pull = TestResults(
        analyses=analyses_pull,
        regression_flag=regression_flag_pull,
        pr=pr,
        viz_data=all_viz_data_pull,
    )
    results = TestResults(
        analyses=analyses,
        regression_flag=regression_flag,
        pr=0,
        viz_data=all_viz_data,
    )
    return results, results_pull


def get_start_timestamp(kwargs: Dict[str, Any], test: Dict[str, Any], is_pull: bool) -> str:
    """Get the start timestamp if lookback is provided."""
    logger = SingletonLogger.get_logger("Orion")
    # Window expansion: unbounded lookback only for non-PR. For PR we keep PR creation.
    if kwargs.get("_unbounded_lookback"):
        return ""
    if is_pull:
        logger.info("Getting start timestamp from pull request creation date")
        client = GitHubClient(repositories=[])
        creation_date = client.get_pr_creation_date(test["metadata"]["organization"],
                                                    test["metadata"]["repository"],
                                                    test["metadata"]["pullNumber"])
        if creation_date:
            logger.info("Start timestamp from pull request creation date: %s",
                        creation_date.strftime("%Y-%m-%dT%H:%M:%SZ"))
            return creation_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    if kwargs["since"] != "" and kwargs["since"] is not None:
        if kwargs.get("lookback"):
            return get_subtracted_timestamp(kwargs["lookback"], kwargs["since"])
        return ""
    return (
        get_subtracted_timestamp(kwargs["lookback"]) if kwargs.get("lookback") else ""
    )

def has_early_changepoint_raw(
    change_points_by_metric: dict,
    max_early_index: int = 5,
) -> bool:
    """Check if any direction-filtered changepoint is in the first N data points."""
    for metric_cps in change_points_by_metric.values():
        for cp in metric_cps:
            if cp.index < max_early_index:
                return True
    return False


def clear_early_changepoints_raw(
    change_points_by_metric: dict,
    max_early_index: int,
) -> dict:
    """Return a copy with early changepoints removed."""
    cleaned = {}
    for metric, cps in change_points_by_metric.items():
        cleaned[metric] = [cp for cp in cps if cp.index >= max_early_index]
    return cleaned


def analyze(test, kwargs, is_pull=False):
    """Analyze a test and return raw results without formatting.

    Returns:
        Tuple[Optional[AnalysisResult], Optional[VizData]]:
            (None, None) for PR paths with no data.
            Calls sys.exit(3) for non-PR paths with no data.
    """
    matcher = Matcher(
        index=kwargs["metadata_index"] or test["metadata_index"],
        es_server=kwargs["es_server"],
        verify_certs=False,
        version_field=test["version_field"],
        uuid_field=test["uuid_field"],
    )
    utils = Utils(test["uuid_field"], test["version_field"])
    logger = SingletonLogger.get_logger("Orion")
    start_timestamp = get_start_timestamp(kwargs, test, is_pull)
    fingerprint_matched_df, metrics_config = utils.process_test(
        test, matcher, kwargs, start_timestamp
    )

    if fingerprint_matched_df is None:
        if is_pull:
            return None, None
        sys.exit(3)

    metrics = list(metrics_config.keys())

    algorithm_name = get_algorithm_type(kwargs)
    if algorithm_name is None:
        logger.error("No algorithm configured")
        return None, None

    logger.info("Comparison algorithm: %s", algorithm_name)

    if algorithm_name == cnsts.ISOLATION_FOREST:
        fingerprint_matched_df = fingerprint_matched_df.dropna().reset_index()

    avg_values = fingerprint_matched_df[metrics].mean()

    algorithm_factory = AlgorithmFactory()
    algorithm = algorithm_factory.instantiate_algorithm(
        algorithm_name,
        fingerprint_matched_df,
        test,
        kwargs,
        metrics_config,
    )

    _, change_points_by_metric = algorithm.get_analysis_results()
    regression_flag = algorithm.regression_flag
    final_algorithm = algorithm
    expanded_algorithm = None

    if regression_flag and has_early_changepoint_raw(
        change_points_by_metric, max_early_index=cnsts.CHANGEPOINT_BUFFER
    ):
        logger.info(
            "Changepoint in buffer (first %d points): attempting "
            "window expansion for test=%s",
            cnsts.CHANGEPOINT_BUFFER,
            test["name"],
        )
        expanded_kwargs = copy.deepcopy(kwargs)
        expanded_kwargs["lookback"] = ""
        if not is_pull:
            expanded_kwargs["_unbounded_lookback"] = True
        current_points = len(fingerprint_matched_df)
        required_lookback_size = current_points + cnsts.EXPAND_POINTS
        expanded_kwargs["lookback_size"] = required_lookback_size
        logger.info(
            "Window expansion: unbounded lookback, lookback_size -> %d",
            required_lookback_size,
        )

        expanded_start_timestamp = get_start_timestamp(
            expanded_kwargs, test, is_pull
        )
        matcher.index = expanded_kwargs.get("metadata_index") or test.get(
            "metadata_index"
        )
        expanded_fingerprint_matched_df, _ = utils.process_test(
            test, matcher, expanded_kwargs, expanded_start_timestamp
        )

        expanded_points = (
            len(expanded_fingerprint_matched_df)
            if expanded_fingerprint_matched_df is not None
            else 0
        )

        if (
            expanded_fingerprint_matched_df is not None
            and expanded_points > len(fingerprint_matched_df)
        ):
            if algorithm_name == cnsts.ISOLATION_FOREST:
                expanded_fingerprint_matched_df = (
                    expanded_fingerprint_matched_df.dropna().reset_index()
                )

            expanded_algorithm = algorithm_factory.instantiate_algorithm(
                algorithm_name,
                expanded_fingerprint_matched_df,
                test,
                expanded_kwargs,
                metrics_config,
            )

            _, expanded_change_points = (
                expanded_algorithm.get_analysis_results()
            )
            expanded_flag = expanded_algorithm.regression_flag

            if expanded_flag:
                logger.info(
                    "Window expansion: expanded run still has changepoint; "
                    "using expanded results (test=%s)",
                    test["name"],
                )
                change_points_by_metric = expanded_change_points
                regression_flag = True
                final_algorithm = expanded_algorithm
            else:
                logger.info(
                    "Window expansion: expanded run has no changepoint; "
                    "clearing regression (test=%s)",
                    test["name"],
                )
                change_points_by_metric = expanded_change_points
                regression_flag = False
                final_algorithm = expanded_algorithm
        else:
            logger.info(
                "Window expansion: no additional data (original=%d, "
                "expanded=%d); skipping early changepoint (test=%s)",
                current_points,
                expanded_points,
                test["name"],
            )
            change_points_by_metric = clear_early_changepoints_raw(
                change_points_by_metric, cnsts.CHANGEPOINT_BUFFER
            )
            regression_flag = False

    viz_data = None
    if kwargs.get("viz"):
        viz_algorithm = (
            expanded_algorithm
            if expanded_algorithm is not None
            else algorithm
        )
        _, viz_change_points = viz_algorithm.get_analysis_results()
        acked_entries = []
        ack_map = viz_algorithm.options.get("ackMap")
        if ack_map is not None:
            acked_entries = ack_map.get("ack", [])
        viz_data = VizData(
            test_name=test["name"],
            dataframe=viz_algorithm.dataframe.copy(),
            metrics_config=metrics_config,
            change_points_by_metric=viz_change_points,
            uuid_field=test["uuid_field"],
            version_field=test["version_field"],
            acked_entries=acked_entries,
        )

    series = final_algorithm.setup_series()

    analysis_result = AnalysisResult(
        test_name=test["name"],
        test=test,
        dataframe=final_algorithm.dataframe.copy(),
        metrics_config=metrics_config,
        change_points_by_metric=change_points_by_metric,
        series=series,
        regression_flag=regression_flag,
        avg_values=avg_values,
        collapse=kwargs["collapse"],
        display_fields=kwargs.get("display", []),
        column_group_size=kwargs.get("column_group_size", 5),
        uuid_field=test["uuid_field"],
        version_field=test["version_field"],
        sippy_pr_search=kwargs.get("sippy_pr_search", False),
        github_repos=kwargs.get("github_repos", []),
    )
    return analysis_result, viz_data
