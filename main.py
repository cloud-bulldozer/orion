"""
This is the cli file for orion, tool to detect regressions using hunter
"""

# pylint: disable = import-error, line-too-long, no-member
import json
import logging
import os
from pathlib import Path
import re
import sys
import warnings
from typing import Any, Optional
import xml.etree.ElementTree as ET
import xml.dom.minidom
import click
from orion.logger import SingletonLogger
from orion.run_test import run, TestResults
from orion.utils import get_output_extension
from orion import constants as cnsts
from orion.config import load_config, auto_detect_ack_file_with_vars
from orion.visualization import generate_test_html
from orion.reporting.standalone import load_json_files, generate_report
from orion.reporting.summary import print_regression_summary
from orion.ack_providers import AckProvider, FileAckProvider, JiraAckProvider
from version import __version__

warnings.filterwarnings("ignore", message="Unverified HTTPS request.*")
warnings.filterwarnings(
    "ignore", category=UserWarning, message=".*Connecting to.*verify_certs=False.*"
)


def build_viz_output_file(
    output_base_path: str, test_name: str, run_type: str = ""
) -> str:
    """Build the output path for a visualization HTML file."""
    suffix = f"_{run_type}" if run_type else ""
    return f"{output_base_path}_{test_name}{suffix}_viz.html"


def _format_pr_section(prs: list, prev_ver: str, bad_ver: str) -> str:
    """Format the PR section of JIRA description."""
    if not prs:
        return ""

    section = "h3. Related Pull Requests\n"
    section += f"PRs introduced between {prev_ver} and {bad_ver}:\n\n"
    for pr in prs:
        if isinstance(pr, str):
            section += f"* {pr}\n"
        elif isinstance(pr, dict):
            pr_url = pr.get("url", pr.get("html_url", ""))
            pr_title = pr.get("title", "")
            if pr_url and pr_title:
                section += f"* [{pr_title}|{pr_url}]\n"
            elif pr_url:
                section += f"* {pr_url}\n"
    section += "\n"
    return section


def _format_github_context(github_context: dict) -> str:
    """Format the GitHub context section (commits and releases)."""
    if not github_context:
        return ""

    repos = github_context.get("repositories", {})
    if not repos:
        return ""

    section = "h3. GitHub Context\n"
    for repo_name, repo_data in repos.items():
        commits = repo_data.get("commits", {})
        if commits.get("count", 0) > 0:
            section += f"h4. {repo_name} - Commits ({commits['count']})\n"
            for commit in commits.get("items", [])[:10]:
                msg = commit.get("message", "").split("\n")[0][:80]
                url = commit.get("html_url", "")
                date = commit.get("commit_timestamp", "")
                author = commit.get("commit_author", {}).get("email", "")
                if url:
                    section += f"* [{msg}|{url}] - {author} - {date}\n"
                else:
                    section += f"* {msg} - {author} - {date}\n"
            if commits.get("count", 0) > 10:
                section += f"* _... and {commits['count'] - 10} more commits_\n"
            section += "\n"

        releases = repo_data.get("releases", {})
        if releases.get("count", 0) > 0:
            section += f"h4. {repo_name} - Releases ({releases['count']})\n"
            for release in releases.get("items", [])[:5]:
                name = release.get("name", release.get("tag_name", ""))
                url = release.get("html_url", "")
                date = release.get("published_at", "")
                if url:
                    section += f"* [{name}|{url}] - {date}\n"
                else:
                    section += f"* {name} - {date}\n"
            section += "\n"

    return section


def format_jira_description(regression: dict, metric_name: str, pct_change: float) -> str:
    """
    Format a rich JIRA description with all regression details.

    Args:
        regression: Regression data dictionary
        metric_name: Name of the specific metric for this issue
        pct_change: Percentage change for this metric

    Returns:
        Formatted JIRA description text
    """
    # Build description using JIRA markup
    desc = "h2. Performance Regression Detected by Orion\n\n"

    # Basic info
    desc += "h3. Changepoint Details\n"
    desc += f"*Test:* {regression.get('test_name')}\n"
    desc += f"*UUID:* {{{regression.get('uuid')}}}\n"
    desc += f"*Version Change:* {regression.get('prev_ver')} → {regression.get('bad_ver')}\n"
    if regression.get("timestamp"):
        desc += f"*Timestamp:* {regression.get('timestamp')}\n"
    if regression.get("buildUrl"):
        desc += f"*Build URL:* [View Build|{regression.get('buildUrl')}]\n"
    desc += "\n"

    # Primary metric for this issue
    desc += "h3. Primary Regression\n"
    desc += f"*Metric:* {metric_name}\n"
    desc += f"*Change:* {pct_change:+.2f}%\n"
    desc += "\n"

    # All affected metrics
    metrics_with_change = regression.get("metrics_with_change", [])
    if len(metrics_with_change) > 1:
        desc += "h3. All Affected Metrics\n"
        desc += "|| Metric || Change || Value ||\n"
        for metric in metrics_with_change:
            labels = metric.get("labels", [])
            label_str = f" ({', '.join(labels)})" if labels else ""
            desc += f"| {metric.get('name')}{label_str} | {metric.get('percentage_change', 0):+.2f}% | {metric.get('value', 'N/A')} |\n"
        desc += "\n"

    # Add PR and GitHub context sections
    desc += _format_pr_section(
        regression.get("prs", []),
        regression.get("prev_ver", ""),
        regression.get("bad_ver", "")
    )
    desc += _format_github_context(regression.get("github_context"))

    # Footer
    desc += "----\n"
    desc += "_This issue was automatically created by Orion regression detection._\n"

    return desc


def auto_create_jira_issues(regression_data: list, provider: AckProvider, logger) -> int:
    """
    Automatically create JIRA issues for detected regressions.

    Args:
        regression_data: List of regression dictionaries from run()
        provider: JIRA ACK provider to use for creation
        logger: Logger instance

    Returns:
        Number of JIRA issues successfully created
    """
    if not regression_data:
        return 0

    created_count = 0
    skipped_count = 0

    for regression in regression_data:
        uuid = regression.get("uuid")
        if not uuid:
            logger.warning("Skipping JIRA creation: no UUID in regression data")
            continue

        # Create JIRA issue for each regressed metric
        for metric_info in regression.get("metrics_with_change", []):
            metric_name = metric_info.get("name")
            if not metric_name:
                continue

            pct_change = metric_info.get("percentage_change", 0)

            logger.info(
                "Creating JIRA issue for regression: test=%s, uuid=%s, metric=%s, change=%+.2f%%",
                regression.get("test_name"), uuid[:8], metric_name, pct_change
            )

            try:
                # Normalize versions to short format (e.g., "4.22" from "4.22.0-ec.3")
                bad_ver = regression.get("bad_ver")
                prev_ver = regression.get("prev_ver")

                success = provider.create_ack(
                    uuid=uuid,
                    metric=metric_name,
                    reason=format_jira_description(regression, metric_name, pct_change),
                    version=str(bad_ver)[:4].rstrip('.') if bad_ver else None,
                    test=regression.get("benchmark_type") or regression.get("test_name"),
                    build_url=regression.get("buildUrl", ""),
                    pct_change=f"{pct_change:+.2f}",
                    prev_version=str(prev_ver)[:4].rstrip('.') if prev_ver else None
                )

                if success:
                    created_count += 1
                    logger.info("✓ Created JIRA issue for %s / %s", uuid[:8], metric_name)
                else:
                    skipped_count += 1
                    logger.debug("Skipped (likely already exists): %s / %s", uuid[:8], metric_name)

            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("Failed to create JIRA issue for %s / %s: %s", uuid[:8], metric_name, e)
                skipped_count += 1

    if created_count > 0:
        logger.info("📝 Created %d JIRA issue(s) for regressions", created_count)
    if skipped_count > 0:
        logger.debug("Skipped %d issue(s) (already exist or failed)", skipped_count)

    return created_count


class Dictionary(click.ParamType):
    """Class to define a custom click type for dictionaries

    Args:
        click (ParamType):
    """
    name = "dictionary"
    def convert(self, value: Any, param: Any, ctx: Any) -> dict:
        return json.loads(value)

class List(click.ParamType):
    """Class to define a custom click type for lists

    Args:
        click (ParamType):
    """
    name = "list"
    def convert(self, value: Any, param: Any, ctx: Any) -> list:
        if isinstance(value, list):
            return value
        return value.split(",") if value else []

class MutuallyExclusiveOption(click.Option):
    """Class to implement mutual exclusivity between options in click

    Args:
        click (Option): _description_
    """

    def __init__(self, *args: tuple, **kwargs: dict[str, dict]) -> None:
        self.mutually_exclusive = set(kwargs.pop("mutually_exclusive", []))
        help = kwargs.get("help", "")  # pylint: disable=redefined-builtin
        if self.mutually_exclusive:
            ex_str = ", ".join(self.mutually_exclusive)
            kwargs["help"] = help + (
                " NOTE: This argument is mutually exclusive with "
                " arguments: [" + ex_str + "]."
            )
        super().__init__(*args, **kwargs)

    def handle_parse_result(self, ctx, opts, args):
        if self.mutually_exclusive.intersection(opts) and self.name in opts:
            raise click.UsageError(
                f"Illegal usage: `{self.name}` is mutually exclusive with "
                f"arguments `{', '.join(self.mutually_exclusive)}`."
            )
        return super().handle_parse_result(ctx, opts, args)


def validate_anomaly_options(ctx, param, value: Any) -> Any: # pylint: disable = W0613
    """ validate options so that can only be used with certain flags
    """
    if value or (
        ctx.params.get("anomaly_window") or ctx.params.get("min_anomaly_percent")
    ):
        if not ctx.params.get("anomaly_detection"):
            raise click.UsageError(
                "`--anomaly-window` and `--min-anomaly-percent` can only be used when `--anomaly-detection` is enabled."
            )
    return value


def _resolve_template_variable(value: str, input_vars: dict) -> str:
    """Resolve template variable like {{VERSION}} from input_vars."""
    if not value or "{{" not in str(value):
        return str(value).strip('"')

    match = re.search(r'\{\{\s*(\w+)\s*\}\}', str(value))
    if match:
        var_name = match.group(1)
        return input_vars.get(var_name) or input_vars.get(var_name.lower())
    return value


def _extract_version_and_test(config: dict, input_vars: dict) -> tuple:
    """Extract version and test type from config."""
    if "tests" not in config or not config["tests"]:
        return None, None

    test = config["tests"][0]
    metadata = test.get("metadata", {})

    # Resolve version
    version_field = test.get("version_field", "ocpVersion")
    version = _resolve_template_variable(metadata.get(version_field, ""), input_vars)

    # Resolve test type
    test_type = _resolve_template_variable(metadata.get("benchmark.keyword", ""), input_vars)

    return version, test_type


def _create_jira_provider(kwargs: dict, config: dict, logger) -> JiraAckProvider:
    """Create and initialize a JIRA ACK provider."""
    jira_url = kwargs.get("jira_url") or config.get("jira_url")
    if not jira_url:
        logger.error("JIRA URL required when --jira-ack is enabled. Use --jira-url or set JIRA_URL env var")
        sys.exit(1)

    try:
        provider = JiraAckProvider(
            jira_url=jira_url,
            project=kwargs.get("jira_project", "PERFSCALE"),
            component=kwargs.get("jira_component", "CPT_ISSUES"),
            token=kwargs.get("jira_token") or config.get("jira_token"),
            email=kwargs.get("jira_email") or config.get("jira_email"),
            uuid_field=config.get("jira_uuid_field", "description"),
            metric_field=config.get("jira_metric_field", "labels")
        )
        logger.info("✓ JIRA ACK provider initialized: %s/%s",
                   provider.project, provider.component)
        return provider
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Failed to initialize JIRA provider: %s", e)
        logger.error("See JIRA_PERMISSIONS_TROUBLESHOOTING.md for help")
        sys.exit(1)


def get_ack_providers(kwargs: dict, config: dict, logger) -> tuple[list[AckProvider], Optional[str], Optional[str]]:
    """
    Factory function to create ACK providers based on configuration.

    Args:
        kwargs: CLI arguments
        config: Loaded configuration dict
        logger: Logger instance

    Returns:
        Tuple of (list of ACK provider instances, version string, test type string)
    """
    providers = []

    # Extract version and test type from config
    version, test_type = _extract_version_and_test(config, kwargs["input_vars"])

    # JIRA provider
    if kwargs.get("jira_ack"):
        providers.append(_create_jira_provider(kwargs, config, logger))

    # File-based provider (auto-detect unless disabled or JIRA-only mode)
    jira_only_mode = kwargs.get("jira_ack") and not kwargs.get("ack")

    if jira_only_mode:
        logger.info("JIRA-only mode: skipping default file-based ACKs (use --ack to enable hybrid mode)")
    elif not kwargs.get("no_default_ack"):
        auto_ack_file = auto_detect_ack_file_with_vars(
            config,
            kwargs["input_vars"],
            ack_dir="ack"
        )
        if auto_ack_file:
            providers.append(FileAckProvider(auto_ack_file))
            logger.info("✓ File ACK provider initialized: %s", auto_ack_file)
    else:
        logger.info("default ACK loading disabled")

    # Manual ACK files (always processed if provided)
    if kwargs.get("ack"):
        for ack_file in [f.strip() for f in kwargs["ack"].split(",") if f.strip()]:
            providers.append(FileAckProvider(ack_file))
            logger.info("✓ Manual file ACK provider initialized: %s", ack_file)

    return providers, version, test_type


# pylint: disable=too-many-locals
@click.version_option(version=__version__, message="%(prog)s %(version)s")
@click.command(context_settings={"show_default": True, "max_content_width": 180})
@click.option(
    "--cmr",
    is_flag=True,
    help="Generate percent difference in comparison",
    cls=MutuallyExclusiveOption,
    mutually_exclusive=["anomaly_detection","hunter_analyze"],
)
@click.option("--filter", is_flag=True, help="Generate percent difference in comparison")
@click.option("--config", help="Path to the configuration file", required=False, default=None)
@click.option("--ack", default="", help="Optional ack YAML to ack known regressions (can specify multiple files separated by comma)")
@click.option("--no-default-ack", is_flag=True, default=False, help="Disable automatic default ACK file detection and loading (manual --ack files are still loaded)")
@click.option("--jira-ack", is_flag=True, default=False, help="Use JIRA to track and retrieve acknowledgments instead of YAML files")
@click.option("--jira-url", default="https://issues.redhat.com", envvar="JIRA_URL", help="JIRA instance URL (e.g., https://issues.redhat.com). Can be set via JIRA_URL env var")
@click.option("--jira-project", default="PERFSCALE", help="JIRA project key for acknowledgments")
@click.option("--jira-component", default="CPT_ISSUES", help="JIRA component name for acknowledgments (use empty string '' to skip component)")
@click.option("--jira-token", default="", envvar="JIRA_TOKEN", help="JIRA API token (Cloud) or personal access token (on-premise). Can be set via JIRA_TOKEN env var")
@click.option("--jira-email", default="", envvar="JIRA_EMAIL", help="Email address for Atlassian Cloud authentication (required for *.atlassian.net). Can be set via JIRA_EMAIL env var")
@click.option("--jira-auto-create", is_flag=True, default=False, help="Automatically create JIRA issues for detected regressions (requires --jira-ack)")
@click.option(
    "--save-data-path", default="data.csv", help="Path to save the output file"
)
@click.option(
    "--github-repos",
    type=List(),
    default=[""],
    help="List of GitHub repositories (owner/repo) to enrich changepoint output with release and commit info",
)
@click.option("--sippy-pr-search", is_flag=True, help="Search for PRs in sippy")
@click.option("--debug", default=False, is_flag=True, help="log level")
@click.option(
    "--hunter-analyze",
    is_flag=True,
    help="run hunter analyze",
    cls=MutuallyExclusiveOption,
    mutually_exclusive=["anomaly_detection","cmr"],
)
@click.option("--anomaly-window", type=int, callback=validate_anomaly_options, help="set window size for moving average for anomaly-detection")
@click.option("--min-anomaly-percent", type=int, callback=validate_anomaly_options, help="set minimum percentage difference from moving average for data point to be detected as anomaly")
@click.option(
    "--anomaly-detection",
    is_flag=True,
    help="run anomaly detection algorithm powered by isolation forest",
    cls=MutuallyExclusiveOption,
    mutually_exclusive=["hunter_analyze","cmr"],
)
@click.option(
    "-o",
    "--output-format",
    type=click.Choice([cnsts.JSON, cnsts.TEXT, cnsts.JUNIT]),
    default=cnsts.TEXT,
    help="Choose output format (json, text or junit)",
)
@click.option("--save-output-path", default="output.txt", help="path to save output file with regressions")
@click.option("--column-group-size", type=int, default=5, help="Number of metrics per column group in text report")
@click.option("--uuid", default="", help="UUID to use as base for comparisons")
@click.option(
    "--baseline", default="", help="Baseline UUID(s) to to compare against uuid"
)
@click.option("--lookback", help="Get data from last X days and Y hours. Format in XdYh")
@click.option("--since", help="End date to bound the time range. When used with --lookback, creates a time window ending at this date. Format: YYYY-MM-DD")
@click.option("--convert-tinyurl", is_flag=True, help="Convert buildUrls to tiny url format for better formatting")
@click.option("--collapse", is_flag=True, help="For text output: only print regression summary to stdout (full table always saved to file). For JSON output: only include changepoint context rows.")
@click.option("--node-count", default=False, help="Match any node iterations count")
@click.option("--lookback-size", type=int, default=10000, help="Maximum number of entries to be looked back")
@click.option("--es-server", type=str, envvar="ES_SERVER", help="Elasticsearch endpoint where test data is stored, can be set via env var ES_SERVER", default="")
@click.option("--benchmark-index", type=str, envvar="es_benchmark_index",  help="Index where test data is stored, can be set via env var es_benchmark_index", default="")
@click.option("--metadata-index", type=str, envvar="es_metadata_index",  help="Index where metadata is stored, can be set via env var es_metadata_index", default="")
@click.option("--input-vars", type=Dictionary(), default="{}", help='Arbitrary input variables to use in the config template, for example: {"version": "4.18"}')
@click.option("--display", type=List(), default=["buildUrl"], help="Add metadata field as a column in the output (e.g. ocpVirt, upstreamJob)")
@click.option("--pr-analysis", is_flag=True, help="Analyze PRs for regressions", default=False)
@click.option("--viz", is_flag=True, default=False, help="Generate interactive HTML visualizations alongside output")
@click.option(
    "--report",
    default=None,
    help="Generate standalone regression report from comma-separated JSON file paths.",
)
def main(**kwargs):
    """
    Orion runs on command line mode, and helps in detecting regressions
    """
    # Handle standalone report mode (--report with file paths)
    report_value = kwargs.pop("report", None)
    if report_value:
        level = logging.DEBUG if kwargs["debug"] else logging.INFO
        logger = SingletonLogger(debug=level, name="Orion")
        logger.info("Orion version: %s", __version__)
        files = [f.strip() for f in report_value.split(",") if f.strip()]
        data = load_json_files(files)
        has_regression = generate_report(data)
        sys.exit(2 if has_regression else 0)

    # --config is required for normal operation
    if not kwargs.get("config"):
        click.echo("Error: --config is required (unless using --report with JSON file paths).", err=True)
        sys.exit(1)

    level = logging.DEBUG if kwargs["debug"] else logging.INFO
    if kwargs['output_format'] == cnsts.JSON :
        level = logging.ERROR
    logger = SingletonLogger(debug=level, name="Orion")
    logger.info("🏹 Starting Orion (%s) in command-line mode", __version__)

    # Load config first (needed for auto-detection)
    kwargs["config"] = load_config(kwargs["config"], kwargs["input_vars"])

    # Validate --jira-auto-create requires --jira-ack
    if kwargs.get("jira_auto_create") and not kwargs.get("jira_ack"):
        logger.error("--jira-auto-create requires --jira-ack to be enabled")
        sys.exit(1)

    # Handle ACK loading using provider system
    providers, version, test_type = get_ack_providers(kwargs, kwargs["config"], logger)

    # Save JIRA provider reference for auto-creation later
    jira_provider = None
    if providers:
        for provider in providers:
            if isinstance(provider, JiraAckProvider):
                jira_provider = provider
                break

    if providers:
        # Collect ACKs from all providers
        all_acks = []
        for provider in providers:
            try:
                acks = provider.get_acks(version=version, test_type=test_type)
                if acks:
                    all_acks.extend(acks)
                    logger.info(
                        "✓ Loaded %d ACK entries from %s (version=%s, test=%s)",
                        len(acks),
                        provider.__class__.__name__,
                        version or "all",
                        test_type or "all"
                    )
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("Failed to load ACKs from %s: %s", provider.__class__.__name__, e)

        # Merge and deduplicate
        if all_acks:
            # Use the base provider's merge method to deduplicate
            merged_acks = providers[0].merge_acks([all_acks])
            kwargs["ackMap"] = {"ack": merged_acks}
            logger.info("✓ Total ACK entries loaded: %d (after deduplication)", len(merged_acks))
        else:
            kwargs["ackMap"] = None
            logger.debug("No ACK entries loaded")
    else:
        kwargs["ackMap"] = None
        if not kwargs.get("no_default_ack"):
            logger.info("No ACK providers configured")

    if not kwargs["metadata_index"] or not kwargs["es_server"]:
        logger.error("metadata-index and es-server flags must be provided")
        sys.exit(1)
    if kwargs["pr_analysis"]:
        input_vars = kwargs["input_vars"]
        missing_vars = []
        if "jobtype" not in input_vars:
            missing_vars.append("jobtype")
        if "pull_number" not in input_vars:
            missing_vars.append("pull_number")
        if "organization" not in input_vars:
            missing_vars.append("organization")
        if "repository" not in input_vars:
            missing_vars.append("repository")
        if missing_vars:
            logger.error("Missing required input variables: %s", ", ".join(missing_vars))
            sys.exit(1)
    results, results_pull = run(**kwargs)
    is_pull = False
    if results_pull.output:
        is_pull = True

    # Auto-create JIRA issues for regressions if enabled
    if kwargs.get("jira_auto_create") and jira_provider:
        if results.regression_flag and results.regression_data:
            logger.info("Auto-creating JIRA issues for detected regressions...")
            created = auto_create_jira_issues(results.regression_data, jira_provider, logger)
            if created == 0 and results.regression_data:
                logger.warning(
                    "No JIRA issues were created. This may be due to permissions. "
                    "See JIRA_PERMISSIONS_TROUBLESHOOTING.md for help."
                )
        if is_pull and results_pull.regression_flag and results_pull.regression_data:
            logger.info("Auto-creating JIRA issues for pull request regressions...")
            created = auto_create_jira_issues(results_pull.regression_data, jira_provider, logger)
            if created == 0 and results_pull.regression_data:
                logger.warning(
                    "No JIRA issues were created. This may be due to permissions. "
                    "See JIRA_PERMISSIONS_TROUBLESHOOTING.md for help."
                )
    if kwargs['output_format'] == cnsts.JSON:
        has_regression = print_json(logger, kwargs, results, results_pull, is_pull)
    elif kwargs['output_format'] == cnsts.JUNIT:
        has_regression = print_junit(logger, kwargs, results, results_pull, is_pull)
    else:
        has_regression = print_output(logger, kwargs, results, is_pull)
        if is_pull:
            print_output(logger, kwargs, results_pull, is_pull)
    if kwargs.get("viz"):
        try:
            output_base_path = str(Path(kwargs['save_output_path']).with_suffix(''))
            for viz_data in results.viz_data:
                run_type = "periodic" if is_pull else ""
                output_file = build_viz_output_file(
                    output_base_path, viz_data.test_name, run_type
                )
                generate_test_html(viz_data, output_file)
            if is_pull:
                for viz_data in results_pull.viz_data:
                    output_file = build_viz_output_file(
                        output_base_path, viz_data.test_name, "pull"
                    )
                    generate_test_html(viz_data, output_file)
        except Exception as e:  # pylint: disable=broad-except
            logger.warning("Visualization generation failed: %s", e)

    if has_regression:
        sys.exit(2) ## regression detected

def save_text_table(test_name, result_table, save_output_path):
    """Save the text table to a file."""
    output_file_name = f"{os.path.splitext(save_output_path)[0]}_table_{test_name}.txt"
    with open(output_file_name, 'w', encoding="utf-8") as file:
        file.write(str(result_table))


def print_output(
        logger,
        kwargs,
        results: TestResults,
        is_pull: bool = False) -> bool:
    """
    Print the output of the tests

    Args:
        logger: logger object
        kwargs: keyword arguments
        results: results of the tests
        is_pull: whether the tests are pull requests
    """
    output = results.output
    regression_flag = results.regression_flag
    regression_data = results.regression_data
    average_values = results.average_values
    pr = results.pr if is_pull else 0
    if not output:
        logger.error("Terminating test")
        sys.exit(0)
    for test_name, result_table in output.items():
        save_text_table(test_name, result_table, kwargs['save_output_path'])
        if not kwargs['collapse']:
            text = test_name
            if pr > 0:
                text = test_name + " | Pull Request #" + str(pr)
            print(text)
            print("=" * len(text))
            print(result_table)
            if is_pull and pr < 1:
                text = test_name + " | Average of above Periodic runs"
                print("\n" + text)
                print("=" * len(text))
                print(average_values)
    if regression_flag:
        print_regression_summary(regression_data)
        if not is_pull:
            return True
    else:
        print("No regressions found")
    return False


def print_json(logger, kwargs, results: TestResults, results_pull: TestResults, is_pull):
    """
    Print the output of the tests in json format
    """
    logger.info("Printing json output")
    output = results.output
    regression_flag = results.regression_flag
    average_values = results.average_values
    output_pull = []
    if not output:
        logger.error("Terminating test")
        sys.exit(0)
    if is_pull and results_pull.pr:
        output_pull = results_pull.output
    for test_name, result_table in output.items():
        output_file_name = f"{os.path.splitext(kwargs['save_output_path'])[0]}_{test_name}.{get_output_extension(kwargs['output_format'])}"
        if is_pull:
            results_json = {
                "periodic": json.loads(result_table),
                "periodic_avg": json.loads(average_values),
                "pull": json.loads(output_pull.get(test_name)),
            }
            print(json.dumps(results_json, indent=2))
            with open(output_file_name, 'w', encoding="utf-8") as file:
                file.write(json.dumps(results_json, indent=2))
        else:
            print(result_table)
            with open(output_file_name, 'w', encoding="utf-8") as file:
                file.write(str(result_table))
        logger.info("Output saved to %s", output_file_name)
        if regression_flag:
            return True
    return False

def print_junit(logger, kwargs, results: TestResults, results_pull: TestResults, is_pull):
    """
    Print the output of the tests in junit format
    """
    logger.info("Printing junit output")
    output = results.output
    regression_flag = results.regression_flag
    average_values = results.average_values
    output_pull = []
    if not output:
        logger.error("Terminating test")
        sys.exit(0)
    if is_pull and results_pull.pr:
        output_pull = results_pull.output
    testsuites = ET.Element("testsuites")
    for test_name, result_table in output.items():
        if not is_pull:
            testsuites.append(result_table)
        else:
            testsuites.append(result_table)
            average_values.tag = "periodic_avg"
            testsuites.append(average_values)
            output_pull.get(test_name).tag = "pull"
            testsuites.append(output_pull.get(test_name))
        xml_str = ET.tostring(testsuites, encoding="utf8", method="xml").decode()
        dom = xml.dom.minidom.parseString(xml_str)
        pretty_xml_as_string = dom.toprettyxml()
        print(pretty_xml_as_string)
        output_file_name = f"{os.path.splitext(kwargs['save_output_path'])[0]}.{get_output_extension(kwargs['output_format'])}"
        with open(output_file_name, 'w', encoding="utf-8") as file:
            file.write(str(pretty_xml_as_string))
        logger.info("Output saved to %s", output_file_name)
        if regression_flag:
            return True
    return False
