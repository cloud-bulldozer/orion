"""
Interactive wizard for Orion CLI.

Guides the user through all configuration options conversationally,
then returns a kwargs dict that is drop-in compatible with the Click
command parameters in main.py.

Usage (called from main.py when --interactive / -i is passed):
    from orion.interactive import run_interactive
    kwargs.update(run_interactive())
"""

import json
import os
from pathlib import Path
import re

try:
    import questionary
    from questionary import Style
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "The 'questionary' package is required for interactive mode.\n"
        "Install it with:  pip install questionary>=2.0.0"
    ) from exc

from orion import constants as cnsts

# ─────────────────────────────────────────────────────────────────────────────
# Colour theme
# ─────────────────────────────────────────────────────────────────────────────

ORION_STYLE = Style(
    [
        ("qmark", "fg:#00b4d8 bold"),
        ("question", "bold"),
        ("answer", "fg:#00b4d8 bold"),
        ("pointer", "fg:#00b4d8 bold"),
        ("highlighted", "fg:#00b4d8 bold"),
        ("selected", "fg:#00b4d8"),
        ("separator", "fg:#6c757d"),
        ("instruction", "fg:#6c757d italic"),
    ]
)

_CUSTOM_PATH = "[Enter custom path…]"

# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _discover_config_files() -> list:
    """Return a deduplicated, sorted list of YAML files from common locations."""
    search_dirs = ["examples", "."]
    seen: set = set()
    result: list = []
    for directory in search_dirs:
        base = Path(directory)
        if not base.is_dir():
            continue
        for pattern in ("*.yaml", "*.yml"):
            for fp in sorted(base.glob(pattern)):
                # Normalize lexically so equivalent references (e.g. examples/x.yaml
                # and ./examples/x.yaml) are listed only once, without collapsing
                # distinct directory labels via symlink resolution.
                key = os.path.normpath(fp.as_posix())
                if key not in seen:
                    seen.add(key)
                    result.append(key)
    return result


def _ask(prompt_fn, *args, **kwargs):
    """
    Thin wrapper around any questionary prompt function.
    Raises KeyboardInterrupt (instead of returning None) if the user
    cancels with Ctrl-C, so the caller loop can exit cleanly.
    """
    value = prompt_fn(*args, **kwargs).ask()
    if value is None:
        raise KeyboardInterrupt
    return value


def _ask_int(message: str, default: int, style) -> int:
    """Ask for an integer value with validation."""
    raw = _ask(
        questionary.text,
        message,
        default=str(default),
        style=style,
        validate=lambda v: v.isdigit() or "Must be a positive integer",
    )
    return int(raw)


def _get_env_default(var_name: str) -> str:
    """Return first matching env default for a template/input variable."""
    upper = var_name.upper()
    candidates = [
        upper,
        var_name,
    ]
    for key in candidates:
        val = os.environ.get(key)
        if val is not None and str(val).strip() != "":
            return str(val).strip()
    return ""


def _get_env_default_with_key(var_name: str) -> tuple[str, str]:
    """Return first matching env value and the env key name for a template var."""
    upper = var_name.upper()
    candidates = [
        upper,
        var_name,
    ]
    for key in candidates:
        val = os.environ.get(key)
        if val is not None and str(val).strip() != "":
            return str(val).strip(), key
    return "", ""


def _get_first_env_with_key(keys: list[str], fallback: str = "") -> tuple[str, str]:
    """Return first non-empty env value and the env key name from a list."""
    for key in keys:
        val = os.environ.get(key)
        if val is not None and str(val).strip() != "":
            return str(val).strip(), key
    return fallback, ""


def _is_sensitive_name(name: str) -> bool:
    """Best-effort detector for secret-like variable names."""
    return re.search(
        r"(secret|token|es_server|password|passwd|api[_-]?key|client[_-]?secret|access[_-]?key|private[_-]?key)",
        name.lower(),
    ) is not None


def _ask_with_hidden_env_default(
    message: str,
    env_keys: list[str],
    *,
    required: bool = False,
    sensitive: bool = False,
) -> str:
    """
    Ask for a value without exposing ENV-backed defaults in terminal output.

    If an ENV value exists, this shows only the ENV key name and lets the user
    press Enter to keep the hidden ENV value or type an override.
    """
    env_value, env_key = _get_first_env_with_key(env_keys)
    if env_key:
        print(f"    Using value from ENV {env_key} (hidden)")
        prompt_fn = questionary.password if sensitive else questionary.text
        typed = _ask(
            prompt_fn,
            f"{message} (press Enter to keep ENV value):",
            style=ORION_STYLE,
        ).strip()
        return typed or env_value

    if required:
        return _ask(
            questionary.text,
            message,
            style=ORION_STYLE,
            validate=lambda v: len(v.strip()) > 0 or "Required",
        ).strip()

    return _ask(
        questionary.text,
        message,
        style=ORION_STYLE,
    ).strip()


def _mask_option_value_for_display(option_key: str, value: str) -> str:
    """
    Mask displayed option values when they come from known ENV sources.

    Returns "$ENV_KEY" when value matches known env var content, otherwise
    returns the original value unchanged.
    """
    if not value:
        return value

    env_map = {
        "es_server": ["ES_SERVER", "es_server"],
        "benchmark_index": ["ES_BENCHMARK_INDEX", "es_benchmark_index"],
        "metadata_index": ["ES_METADATA_INDEX", "es_metadata_index"],
    }
    env_keys = env_map.get(option_key, [])
    env_value, env_key = _get_first_env_with_key(env_keys)
    if env_key and env_value == value:
        return f"${env_key}"
    return value


def _mask_input_vars_for_display(input_vars: dict) -> dict:
    """Mask input vars from ENV; redact sensitive manually typed values."""
    masked = {}
    for key, value in input_vars.items():
        env_value, env_key = _get_env_default_with_key(key)
        if env_key and str(value) == env_value:
            masked[key] = f"${env_key}"
        elif _is_sensitive_name(key):
            masked[key] = "<redacted>"
        else:
            masked[key] = value
    return masked


def _extract_template_variables(config_path: str) -> list[tuple[str, bool]]:
    """
    Extract Jinja-style template vars from config text.

    Returns list of tuples: (var_name, is_required)
    where is_required=False when expression includes a default filter.
    """
    path = Path(config_path)
    if not path.is_file():
        return []

    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return []

    found: dict[str, bool] = {}
    ordered: list[str] = []

    for expr in re.findall(r"\{\{\s*(.*?)\s*\}\}", content, flags=re.DOTALL):
        match = re.match(r"([a-zA-Z_][\w]*)", expr.strip())
        if not match:
            continue
        var_name = match.group(1)
        has_default = "default(" in expr
        is_required = not has_default

        if var_name not in found:
            found[var_name] = is_required
            ordered.append(var_name)
        else:
            # If any occurrence is required, keep it required.
            found[var_name] = found[var_name] or is_required

    return [(name, found[name]) for name in ordered]


def _header(title: str) -> None:
    width = 60
    print(f"\n\033[1m{'─' * width}\033[0m")
    print(f"\033[1m  {title}\033[0m")
    print(f"\033[1m{'─' * width}\033[0m")


# ─────────────────────────────────────────────────────────────────────────────
# CLI command builder (for the "Equivalent CLI command" echo)
# ─────────────────────────────────────────────────────────────────────────────


def _build_cli_command(params: dict) -> str:  # pylint: disable=too-many-branches
    """Construct an equivalent orion CLI invocation from collected params."""
    parts = ["orion"]

    # Boolean flags
    flag_map = {
        "hunter_analyze": "--hunter-analyze",
        "cmr": "--cmr",
        "anomaly_detection": "--anomaly-detection",
        "filter": "--filter",
        "node_count": "--node-count",
        "no_default_ack": "--no-default-ack",
        "sippy_pr_search": "--sippy-pr-search",
        "convert_tinyurl": "--convert-tinyurl",
        "collapse": "--collapse",
        "pr_analysis": "--pr-analysis",
        "viz": "--viz",
        "debug": "--debug",
    }
    for key, flag in flag_map.items():
        if params.get(key):
            parts.append(flag)

    # String / path options
    str_map = {
        "config": "--config",
        "ack": "--ack",
        "uuid": "--uuid",
        "baseline": "--baseline",
        "lookback": "--lookback",
        "since": "--since",
        "es_server": "--es-server",
        "benchmark_index": "--benchmark-index",
        "metadata_index": "--metadata-index",
        "save_output_path": "--save-output-path",
        "save_data_path": "--save-data-path",
        "output_format": "--output-format",
    }
    for key, flag in str_map.items():
        val = params.get(key)
        display_val = _mask_option_value_for_display(key, str(val)) if val else val
        if val and val not in ("output.txt", "data.csv", cnsts.TEXT):
            # Only emit non-default values to keep the command concise
            parts.append(f'{flag} "{display_val}"')
        elif val and key in ("es_server", "benchmark_index", "metadata_index", "config"):
            parts.append(f'{flag} "{display_val}"')

    # Integer options (only if non-default)
    int_map = {
        "anomaly_window": ("--anomaly-window", None),
        "min_anomaly_percent": ("--min-anomaly-percent", None),
        "column_group_size": ("--column-group-size", 5),
        "lookback_size": ("--lookback-size", 10000),
    }
    for key, (flag, default) in int_map.items():
        val = params.get(key)
        if val is not None and val != default:
            parts.append(f"{flag} {val}")

    # List options
    repos = params.get("github_repos", [""])
    if repos and repos != [""]:
        parts.append(f'--github-repos "{",".join(repos)}"')

    display = params.get("display", ["buildUrl"])
    if display and display != ["buildUrl"]:
        parts.append(f'--display "{",".join(display)}"')

    # Dict option
    if params.get("input_vars"):
        safe_input_vars = _mask_input_vars_for_display(params["input_vars"])
        parts.append(f"--input-vars '{json.dumps(safe_input_vars)}'")

    return " \\\n    ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Wizard sections
# ─────────────────────────────────────────────────────────────────────────────


def _section_config(params: dict) -> None:
    _header("1 / 7  —  Configuration")

    config_files = _discover_config_files()
    if config_files:
        choices = config_files + [_CUSTOM_PATH]
        selection = _ask(
            questionary.select,
            "Config file:",
            choices=choices,
            style=ORION_STYLE,
        )
        if selection == _CUSTOM_PATH:
            params["config"] = _ask(
                questionary.path,
                "Custom config file path:",
                style=ORION_STYLE,
                validate=lambda v: (
                    Path(v.strip()).is_file() or f"File not found: {v.strip()}"
                ),
            )
        else:
            params["config"] = selection
    else:
        params["config"] = _ask(
            questionary.path,
            "Config file path:",
            style=ORION_STYLE,
            validate=lambda v: (
                Path(v.strip()).is_file() or f"File not found: {v.strip()}"
            ),
        )

    # Template variables
    params["input_vars"] = {}
    detected_vars = _extract_template_variables(params["config"])
    if detected_vars:
        print("  Detected template variables in config:")
        print("    " + ", ".join(name for name, _ in detected_vars))
        print()

        for var_name, is_required in detected_vars:
            existing = str(params["input_vars"].get(var_name, "")).strip()
            env_default, env_key = _get_env_default_with_key(var_name)

            if is_required:
                if existing:
                    value = _ask(
                        questionary.text,
                        f"  Value for '{var_name}':",
                        default=existing,
                        style=ORION_STYLE,
                        validate=lambda v, vn=var_name: len(v.strip()) > 0 or f"{vn} is required",
                    ).strip()
                elif env_default:
                    print(f"    Using env default for '{var_name}' from {env_key} (hidden)")
                    prompt_fn = questionary.password if _is_sensitive_name(var_name) else questionary.text
                    typed = _ask(
                        prompt_fn,
                        f"  Value for '{var_name}' (press Enter to keep ENV value):",
                        style=ORION_STYLE,
                    ).strip()
                    value = typed or env_default
                else:
                    value = _ask(
                        questionary.text,
                        f"  Value for '{var_name}':",
                        style=ORION_STYLE,
                        validate=lambda v, vn=var_name: len(v.strip()) > 0 or f"{vn} is required",
                    ).strip()
            else:
                if existing:
                    value = _ask(
                        questionary.text,
                        f"  Value for '{var_name}' (optional, Enter to use template default):",
                        default=existing,
                        style=ORION_STYLE,
                    ).strip()
                elif env_default:
                    print(f"    Using env default for '{var_name}' from {env_key} (hidden)")
                    prompt_fn = questionary.password if _is_sensitive_name(var_name) else questionary.text
                    typed = _ask(
                        prompt_fn,
                        f"  Value for '{var_name}' (optional, Enter to keep ENV value):",
                        style=ORION_STYLE,
                    ).strip()
                    value = typed or env_default
                else:
                    value = _ask(
                        questionary.text,
                        f"  Value for '{var_name}' (optional, Enter to use template default):",
                        style=ORION_STYLE,
                    ).strip()

            if value:
                params["input_vars"][var_name] = value


def _section_algorithm(params: dict) -> None:
    _header("2 / 7  —  Analysis Algorithm")

    algorithm = _ask(
        questionary.select,
        "Algorithm:",
        choices=[
            questionary.Choice(
                "Hunter Analyze  — changepoint detection  (default)", "hunter_analyze"
            ),
            questionary.Choice(
                "CMR             — comparative metric regression", "cmr"
            ),
            questionary.Choice(
                "Anomaly Detect  — isolation forest", "anomaly_detection"
            ),
            questionary.Choice(
                "Filter          — percent difference only", "filter"
            ),
        ],
        style=ORION_STYLE,
    )

    params["hunter_analyze"] = algorithm == "hunter_analyze"
    params["cmr"] = algorithm == "cmr"
    params["anomaly_detection"] = algorithm == "anomaly_detection"
    params["filter"] = algorithm == "filter"
    params["anomaly_window"] = None
    params["min_anomaly_percent"] = None

    if params["anomaly_detection"]:
        params["anomaly_window"] = _ask_int(
            "  Moving-average window size:", default=5, style=ORION_STYLE
        )
        params["min_anomaly_percent"] = _ask_int(
            "  Minimum anomaly percentage:", default=5, style=ORION_STYLE
        )


def _section_datasource(params: dict) -> None:
    _header("3 / 7  —  Data Source")

    params["es_server"] = _ask_with_hidden_env_default(
        "Elasticsearch server URL:",
        ["ES_SERVER", "es_server"],
        required=True,
        sensitive=True,
    )
    params["benchmark_index"] = _ask_with_hidden_env_default(
        "Benchmark index:",
        ["ES_BENCHMARK_INDEX", "es_benchmark_index"],
        required=False,
        sensitive=False,
    )
    params["metadata_index"] = _ask_with_hidden_env_default(
        "Metadata index:",
        ["ES_METADATA_INDEX", "es_metadata_index"],
        required=False,
        sensitive=False,
    )

    range_mode = _ask(
        questionary.select,
        "Data range mode:",
        choices=[
            questionary.Choice(
                "Lookback  — last X days / Y hours  (e.g. 7d0h)", "lookback"
            ),
            questionary.Choice("UUID / Baseline  — specific run UUIDs", "uuid"),
        ],
        style=ORION_STYLE,
    )

    params["uuid"] = ""
    params["baseline"] = ""
    params["lookback"] = None
    params["since"] = None

    if range_mode == "lookback":
        params["lookback"] = _ask(
            questionary.text,
            "  Lookback period (XdYh, e.g. 7d0h):",
            style=ORION_STYLE,
            validate=lambda v: len(v.strip()) > 0 or "Required",
        )
        if _ask(
            questionary.confirm,
            "  Set an end-date boundary (--since)?",
            default=False,
            style=ORION_STYLE,
        ):
            params["since"] = _ask(
                questionary.text,
                "  End date (YYYY-MM-DD):",
                style=ORION_STYLE,
            )
    else:
        params["uuid"] = (
            _ask(questionary.text, "  Base UUID:", style=ORION_STYLE) or ""
        )
        params["baseline"] = (
            _ask(
                questionary.text,
                "  Baseline UUID(s) (comma-separated):",
                style=ORION_STYLE,
            )
            or ""
        )

    params["lookback_size"] = 10000
    if _ask(
        questionary.confirm,
        "Change max lookback size (default 10 000)?",
        default=False,
        style=ORION_STYLE,
    ):
        params["lookback_size"] = _ask_int(
            "  Max lookback size:", default=10000, style=ORION_STYLE
        )

    params["node_count"] = _ask(
        questionary.confirm,
        "Filter by node count?",
        default=False,
        style=ORION_STYLE,
    )


def _section_ack(params: dict) -> None:
    _header("4 / 7  —  ACK / Acknowledgements")

    use_default_ack = _ask(
        questionary.confirm,
        "Auto-load default ACK file (ack/all_ack.yaml)?",
        default=True,
        style=ORION_STYLE,
    )
    params["no_default_ack"] = not use_default_ack
    params["ack"] = ""

    if params["no_default_ack"]:
        # Manual ACKs are required when default auto-load is disabled.
        params["ack"] = _ask(
            questionary.text,
            "  ACK file path(s) (required; comma-separated for multiple):",
            style=ORION_STYLE,
            validate=lambda v: len(v.strip()) > 0 or "Provide at least one ACK file path",
        ).strip()
    else:
        # Even with default ACK, allow adding extra manual ACK files.
        if _ask(
            questionary.confirm,
            "  Add extra ACK files alongside the default?",
            default=False,
            style=ORION_STYLE,
        ):
            params["ack"] = _ask(
                questionary.text,
                "  Extra ACK file path(s) (comma-separated):",
                style=ORION_STYLE,
            ).strip()


def _section_output(params: dict) -> None:
    _header("5 / 7  —  Output")

    params["output_format"] = _ask(
        questionary.select,
        "Output format:",
        choices=[cnsts.TEXT, cnsts.JSON, cnsts.JUNIT],
        default=cnsts.TEXT,
        style=ORION_STYLE,
    )
    params["save_output_path"] = (
        _ask(
            questionary.text,
            "Save output to:",
            default="output.txt",
            style=ORION_STYLE,
        )
        or "output.txt"
    )
    params["save_data_path"] = (
        _ask(
            questionary.text,
            "Save data CSV to:",
            default="data.csv",
            style=ORION_STYLE,
        )
        or "data.csv"
    )

    params["column_group_size"] = 5
    if _ask(
        questionary.confirm,
        "Change column group size (default 5)?",
        default=False,
        style=ORION_STYLE,
    ):
        params["column_group_size"] = _ask_int(
            "  Column group size:", default=5, style=ORION_STYLE
        )

    params["collapse"] = _ask(
        questionary.confirm,
        "Collapse output — print only regression summary to stdout?",
        default=False,
        style=ORION_STYLE,
    )
    params["convert_tinyurl"] = _ask(
        questionary.confirm,
        "Convert build URLs to TinyURLs?",
        default=False,
        style=ORION_STYLE,
    )
    params["viz"] = _ask(
        questionary.confirm,
        "Generate interactive HTML visualizations?",
        default=False,
        style=ORION_STYLE,
    )


def _section_enrichment(params: dict) -> None:
    _header("6 / 7  —  Enrichment (optional)")

    params["github_repos"] = [""]
    if _ask(
        questionary.confirm,
        "Add GitHub repos for commit/release enrichment?",
        default=False,
        style=ORION_STYLE,
    ):
        repos_str = (
            _ask(
                questionary.text,
                "  Repos (owner/repo, comma-separated):",
                style=ORION_STYLE,
            )
            or ""
        )
        params["github_repos"] = (
            [r.strip() for r in repos_str.split(",") if r.strip()] or [""]
        )

    params["pr_analysis"] = _ask(
        questionary.confirm,
        "Enable PR analysis?",
        default=False,
        style=ORION_STYLE,
    )
    if params["pr_analysis"]:
        params.setdefault("input_vars", {})
        for key in ("jobtype", "pull_number", "organization", "repository"):
            if not str(params["input_vars"].get(key, "")).strip():
                env_val = _get_env_default(key)
                if env_val:
                    params["input_vars"][key] = env_val

    params["sippy_pr_search"] = _ask(
        questionary.confirm,
        "Enable Sippy PR search?",
        default=False,
        style=ORION_STYLE,
    )

    params["display"] = ["buildUrl"]
    if _ask(
        questionary.confirm,
        "Customise metadata display columns (default: buildUrl)?",
        default=False,
        style=ORION_STYLE,
    ):
        disp_str = (
            _ask(
                questionary.text,
                "  Display fields (comma-separated):",
                default="buildUrl",
                style=ORION_STYLE,
            )
            or "buildUrl"
        )
        params["display"] = [d.strip() for d in disp_str.split(",") if d.strip()]


def _section_debug(params: dict) -> None:
    _header("7 / 7  —  Logging")

    params["debug"] = _ask(
        questionary.confirm,
        "Enable debug logging?",
        default=False,
        style=ORION_STYLE,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────


def run_interactive() -> dict:
    """
    Launch the interactive configuration wizard.

    Returns a dict whose keys match the Click parameter names used in
    main() so the caller can do ``kwargs.update(run_interactive())``.

    Raises KeyboardInterrupt if the user cancels at any prompt.
    """
    print("\n\033[1m🏹  Orion — Interactive Mode\033[0m")
    print(
        "Answer the questions below to build your regression-analysis run.\n"
        "Press Ctrl-C at any time to abort.\n"
    )

    params: dict = {}

    _section_config(params)
    _section_algorithm(params)
    _section_datasource(params)
    _section_ack(params)
    _section_output(params)
    _section_enrichment(params)
    _section_debug(params)

    # ── Review & Confirm ──────────────────────────────────────────────────────
    separator = "─" * 60
    cli_cmd = _build_cli_command(params)
    print(f"\n{separator}")
    print("\033[1mEquivalent CLI command (save this for automation):\033[0m\n")
    print(f"  {cli_cmd}")
    print(f"{separator}\n")

    proceed = _ask(
        questionary.confirm,
        "Proceed with this configuration?",
        default=True,
        style=ORION_STYLE,
    )
    if not proceed:
        raise KeyboardInterrupt

    return params
