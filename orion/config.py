# pylint: disable = line-too-long
"""
Module file for config reading and loading
"""

import sys
import os
import time
import tempfile
from typing import Any, Dict, List
from collections import Counter
from urllib.request import urlopen
from urllib.error import URLError
import jinja2
import yaml
from orion.logger import SingletonLogger

REMOTE_ACK_URL = (
    "https://raw.githubusercontent.com/cloud-bulldozer/orion/main/ack/all_ack.yaml"
)


def load_config(config_path: str, input_vars: Dict[str, Any]) -> Dict[str, Any]:
    """Loads config file

    Args:
        config_path (str): file path to config file
        input_vars (Dict[str, Any]): dictionary of input variables

    Returns:
        Dict[str, Any]: dictionary of the config file
    """
    logger = SingletonLogger.get_logger("Orion")
    env_vars = {k.lower(): v for k, v in os.environ.items()}
    env_vars.update(input_vars)
    template_content = load_read_file(config_path, logger)
    rendered_config = render_template(template_content, env_vars, logger)

    # Get the directory of the config file for resolving relative paths
    config_dir = os.path.dirname(os.path.abspath(config_path))

    parent_config = {}
    if "parentConfig" in rendered_config:
        parent_config = load_config_file(
            rendered_config["parentConfig"],
            config_dir,
            env_vars,
            logger
        )

    parent_metrics = {}
    if "metricsFile" in rendered_config:
        parent_metrics = load_config_file(
            rendered_config["metricsFile"],
            config_dir,
            env_vars,
            logger
        )

    metrics = []
    for test in rendered_config["tests"]:
        skip_global_config = False
        skip_global_metrics = False
        local_config = {}
        local_metrics = {}
        if "IgnoreGlobal" in test:
            skip_global_config = test["IgnoreGlobal"]
        if "IgnoreGlobalMetrics" in test:
            skip_global_metrics = test["IgnoreGlobalMetrics"]
        if "uuid_field" not in test:
            test["uuid_field"] = "uuid"
        if "version_field" not in test:
            test["version_field"] = "ocpVersion"
        if "local_config" in test:
            local_config = load_config_file(test["local_config"], config_dir, env_vars, logger)
            test["metadata"] = merge_configs(test["metadata"], local_config["metadata"])
        if "local_metrics" in test:
            local_metrics = load_config_file(test["local_metrics"], config_dir, env_vars, logger)
            test["metrics"] = merge_lists(test["metrics"], local_metrics)
        if parent_config and not skip_global_config:
            test["metadata"] = merge_configs(test["metadata"], parent_config["metadata"])
        if parent_metrics and not skip_global_metrics:
            test["metrics"] = merge_lists(test["metrics"], parent_metrics)

        for metric in test["metrics"]:
            metric_name = test["name"] + ":" + metric["name"]
            if "agg" in metric:
                metric_name = f"{metric_name}:{metric['agg']['agg_type']}"
            elif "metric_of_interest" in metric:
                metric_name = f"{metric_name}:{metric['metric_of_interest']}"
            metrics.append(metric_name)
        metric_counts = Counter(metrics)
        duplicated_metrics = [name for name, count in metric_counts.items() if count > 1]
        if duplicated_metrics:
            logger.error("Duplicate metric names in config for test %s, \
please fix metric to avoid unexpected behavior: %s", test["name"], [x.split(":")[1] for x in duplicated_metrics])
            sys.exit(1)
    return rendered_config


def load_ack(ack: str, version: str = None, test_type: str = None) -> Dict[str,Any]:
    """Loads acknowledgment file content, optionally filtering by version and test type.

    Args:
        ack (str): path to the acknowledgment file
        version (str, optional): OCP version to filter by (e.g., "4.22")
        test_type (str, optional): Test type to filter by (e.g., "node-density")

    Returns:
        dict: dictionary of the acknowledgment file, filtered if version/test_type provided
    """
    logger = SingletonLogger.get_logger("Orion")
    template_content = load_read_file(ack, logger)
    try:
        rendered_config = yaml.safe_load(template_content)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("An error occurred: %s", e)
        sys.exit(1)
    # Empty rendered config
    if rendered_config is None:
        return rendered_config
    # Ensure the ack file is properly setup.
    if "ack" not in rendered_config:
        logger.error("Ack file not setup properly")
        sys.exit(1)

    # Filter by version and test type if provided
    if version or test_type:
        filtered_acks = []
        for entry in rendered_config["ack"]:
            # Include entry if:
            # 1. No version/test metadata (backward compatible with old format)
            # 2. Matches provided version (if version provided)
            # 3. Matches provided test_type (if test_type provided)
            entry_version = entry.get("version")
            entry_test = entry.get("test")

            version_match = not version or entry_version == version or entry_version is None
            test_match = not test_type or entry_test == test_type or entry_test is None

            if version_match and test_match:
                filtered_acks.append(entry)

        rendered_config["ack"] = filtered_acks
        if version or test_type:
            logger.debug("Filtered ACK entries: version=%s, test_type=%s, found %d entries",
                        version, test_type, len(filtered_acks))

    return rendered_config


def merge_ack_files(ack_maps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Merges multiple ACK file dictionaries into a single ACK map.

    Args:
        ack_maps: List of ACK dictionaries to merge

    Returns:
        dict: Merged ACK dictionary with all entries combined
    """
    logger = SingletonLogger.get_logger("Orion")
    merged_acks = []
    seen_entries = set()

    for ack_map in ack_maps:
        if ack_map and "ack" in ack_map:
            for entry in ack_map["ack"]:
                # Create a unique key for deduplication (uuid + metric)
                entry_key = (entry.get("uuid"), entry.get("metric"))
                if entry_key not in seen_entries:
                    seen_entries.add(entry_key)
                    merged_acks.append(entry)
                else:
                    logger.debug("Skipping duplicate ACK entry: uuid=%s, metric=%s",
                                entry.get("uuid"), entry.get("metric"))

    return {"ack": merged_acks}


def fetch_remote_ack_file() -> str:
    """Fetch the latest consolidated ACK file from the GitHub main branch.

    Downloads ack/all_ack.yaml from the orion repository and writes it to a
    temporary file.

    Returns:
        str: Path to the downloaded temp file, or None if the fetch failed.
    """
    logger = SingletonLogger.get_logger("Orion")
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            logger.info("Fetching latest ACK file from GitHub main branch (attempt %d/%d)...",
                        attempt, max_attempts)
            with urlopen(REMOTE_ACK_URL, timeout=10) as response:  # noqa: S310
                data = response.read()
            tmp = tempfile.NamedTemporaryFile(  # pylint: disable=consider-using-with
                suffix=".yaml", prefix="orion_ack_", delete=False
            )
            tmp.write(data)
            tmp.close()
            logger.info("Successfully fetched remote ACK file (%d bytes)", len(data))
            return tmp.name
        except (URLError, OSError) as exc:
            logger.warning("Attempt %d/%d failed to fetch remote ACK file: %s",
                           attempt, max_attempts, exc)
            if attempt < max_attempts:
                time.sleep(2)
    logger.warning("All %d attempts to fetch remote ACK file failed", max_attempts)
    return None


def auto_detect_ack_file_with_vars(_config: Dict[str, Any], _input_vars: Dict[str, Any],
                                   ack_dir: str = "ack") -> str:
    """Auto-detect consolidated ACK file.

    Tries to fetch the latest ACK file from the GitHub main branch first.
    Falls back to the local consolidated ACK file (all_ack.yaml) if the
    remote fetch fails.

    Args:
        _config: Loaded config dictionary (not used, kept for compatibility)
        _input_vars: Input variables dictionary (not used, kept for compatibility)
        ack_dir: Directory containing ACK files (default: "ack")

    Returns:
        str: Path to consolidated ACK file if found, None otherwise
    """
    logger = SingletonLogger.get_logger("Orion")

    # Try fetching the latest ACK file from GitHub
    remote_path = fetch_remote_ack_file()
    if remote_path:
        logger.info("Using remote ACK file from GitHub main branch")
        return remote_path

    # Fall back to local consolidated ACK file
    consolidated_path = os.path.join(ack_dir, "all_ack.yaml")
    if os.path.exists(consolidated_path):
        logger.info("Using local ACK file: %s", consolidated_path)
        return consolidated_path

    return None


def load_config_file(config_file: str,
                    config_dir: str,
                    env_vars: Dict[str, Any],
                    logger: SingletonLogger) -> Dict[str, Any]:
    """Loads parent config file content.

    Args:
        config_file (str): path to the config file
        config_dir (str): directory of the config file
        env_vars (Dict[str, Any]): dictionary of input variables
        logger (SingletonLogger): logger instance
    """
    # Determine if path is absolute or relative
    if os.path.isabs(config_file):
        config_path = config_file
    else:
        # Resolve relative path relative to config file directory
        config_path = os.path.join(config_dir, config_file)
    config_content = load_read_file(config_path, logger)
    # Load YAML content from config file
    # Render with Jinja2 if it contains templates
    return render_template(config_content, env_vars, logger)


def load_read_file(file_path: str, logger: SingletonLogger) -> str:
    """Loads file content.

    Args:
        file_path (str): path to the file
        logger (SingletonLogger): logger instance
    """
    try:
        with open(file_path, "r", encoding="utf-8") as template_file:
            template_content = template_file.read()
            logger.debug("The %s file has successfully loaded", file_path)
            return template_content
    except FileNotFoundError as e:
        logger.error("File %s not found: %s", file_path, e)
        sys.exit(1)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("An error occurred with file %s: %s", file_path, e)
        sys.exit(1)


def render_template(template: str, env_vars: Dict[str, Any], logger: SingletonLogger) -> Dict[str, Any]:
    """Renders a template with Jinja2.

    Args:
        template (str): template to render
        env_vars (Dict[str, Any]): dictionary of input variables
        logger (SingletonLogger): logger instance
    """
    template = jinja2.Template(template, undefined=jinja2.StrictUndefined)
    try:
        rendered_config_yaml = template.render(env_vars)
    except jinja2.exceptions.UndefinedError as e:
        logger.critical("Jinja rendering error: %s, define it through the input-variables flag", e)
        sys.exit(1)
    return yaml.safe_load(rendered_config_yaml)


def merge_configs(config: Dict[str, Any], inherited_config: Dict[str, Any]) -> Dict[str, Any]:
    """Merges two config dictionaries with config taking precedence.

    If a key exists in config, it will be used instead of the same key from
    inherited_config. Keys that only exist in inherited_config will be included.

    Args:
        config (Dict[str, Any]): The primary config dictionary (takes precedence)
        inherited_config (Dict[str, Any]): The inherited config dictionary to merge from

    Returns:
        Dict[str, Any]: Merged dictionary with config values taking precedence
    """
    logger = SingletonLogger.get_logger("Orion")
    if inherited_config is None:
        inherited_config = {}
    if config is None:
        config = {}

    logger.debug(f"config: {config}")
    logger.debug(f"inherited_config: {inherited_config}")
    # Start with a copy of inherited_config
    merged = inherited_config.copy()

    # Iterate through config keys and add them, overriding inherited_config values
    # If a key exists in config, skip adding it from inherited_config (config takes precedence)
    for key in config:
        logger.info("Adding key %s with value %s", key, config[key])
        merged[key] = config[key]

    logger.debug(f"merged config: {merged}")
    return merged

def merge_lists(metrics: List[Any], inherited_metrics: List[Any]) -> List[Any]:
    """Merges two lists with list1 taking precedence.

    Args:
        list1 (List[Any]): The primary list (takes precedence)
        list2 (List[Any]): The inherited list to merge from

    Returns:
        List[Any]: Merged list with list1 values taking precedence
    """
    logger = SingletonLogger.get_logger("Orion")
    if inherited_metrics is None:
        inherited_metrics = []
    if metrics is None:
        metrics = []

    logger.debug(f"metrics: {metrics}")
    logger.debug(f"inherited_metrics: {inherited_metrics}")
    merged = []

    # Iterate through metrics keys and add them, overriding inherited_metrics values
    for m in inherited_metrics:
        found = False
        for metric in metrics:
            if metric["name"] == m["name"]:
                if "metricName" in metric and "metricName" in m and metric["metricName"] == m["metricName"]:
                    logger.info("Use metric in lower level config file %s - %s", m["name"], m["metricName"])
                    found = True
                if "metricName.keyword" in metric and "metricName.keyword" in m and metric["metricName.keyword"] == m["metricName.keyword"]:
                    logger.info("Use metric in lower level config file %s - %s", m["name"], m["metricName.keyword"])
                    found = True
        if not found:
            merged.append(m)
    merged.extend(metrics)

    logger.debug(f"merged metrics: {merged}")
    return merged
