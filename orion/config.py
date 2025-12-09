# pylint: disable = line-too-long
"""
Module file for config reading and loading
"""

import sys
import os
import jinja2
import yaml
from typing import Any, Dict, List
from orion.logger import SingletonLogger


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
        parent_config = load_parent_config(
            rendered_config["parentConfig"],
            config_dir,
            env_vars,
            logger
        )

    metrics = {}
    if "metricsFile" in rendered_config:
        metrics = load_metrics_file(
            rendered_config["metricsFile"],
            config_dir,
            env_vars,
            logger
        )

    for test in rendered_config["tests"]:
        if parent_config:
            test["metadata"] = merge_configs(test["metadata"], parent_config["metadata"])
        if metrics:
            test["metrics"] = merge_lists(test["metrics"], metrics)

    return rendered_config


def load_ack(ack: str) -> Dict[str,Any]:
    """Loads acknowledgment file content.

    Args:
        ack (str): path to the acknowledgment file

    Returns:
        dict: dictionary of the acknowledgment file
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
    return rendered_config


def load_parent_config(parent_config: str,
                    config_dir: str,
                    env_vars: Dict[str, Any],
                    logger: SingletonLogger) -> Dict[str, Any]:
    """Loads parent config file content.

    Args:
        parent_config (str): path to the parent config file
        config_dir (str): directory of the config file
        env_vars (Dict[str, Any]): dictionary of input variables
        logger (SingletonLogger): logger instance
    """
    # Determine if path is absolute or relative
    if os.path.isabs(parent_config):
        parent_config_path = parent_config
    else:
        # Resolve relative path relative to config file directory
        parent_config_path = os.path.join(config_dir, parent_config)
    parent_config_content = load_read_file(parent_config_path, logger)
    # Load YAML content from parentConfig file
    return render_template(parent_config_content, env_vars, logger)


def load_metrics_file(metrics_file: str,
                    config_dir: str,
                    env_vars: Dict[str, Any],
                    logger: SingletonLogger) -> Dict[str, Any]:
    """Loads metrics file content.

    Args:
        metrics_file (str): path to the metrics file
        config_dir (str): directory of the config file
        env_vars (Dict[str, Any]): dictionary of input variables
        logger (SingletonLogger): logger instance
    """
    # Determine if path is absolute or relative
    if os.path.isabs(metrics_file):
        metrics_file_path = metrics_file
    else:
        # Resolve relative path relative to config file directory
        metrics_file_path = os.path.join(config_dir, metrics_file)
    metrics_file_content = load_read_file(metrics_file_path, logger)
    # Load YAML content from metricsFile
    # Render with Jinja2 if it contains templates
    return render_template(metrics_file_content, env_vars, logger)


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
    if inherited_config is None:
        inherited_config = {}
    if config is None:
        config = {}

    # Start with a copy of inherited_config
    merged = inherited_config.copy()
    print("merged", merged)

    # Iterate through config keys and add them, overriding inherited_config values
    # If a key exists in config, skip adding it from inherited_config (config takes precedence)
    for key in config:
        merged[key] = config[key]

    return merged

def merge_lists(metrics: List[Any], inherited_metrics: List[Any]) -> List[Any]:
    """Merges two lists with list1 taking precedence.

    Args:
        list1 (List[Any]): The primary list (takes precedence)
        list2 (List[Any]): The inherited list to merge from

    Returns:
        List[Any]: Merged list with list1 values taking precedence
    """
    if inherited_metrics is None:
        inherited_metrics = []
    if metrics is None:
        metrics = []

    # Start with a copy of inherited_metrics
    merged = inherited_metrics.copy()

    # Iterate through metrics keys and add them, overriding inherited_metrics values
    for metric in metrics:
        if metric not in merged:
            merged.append(metric)

    return merged