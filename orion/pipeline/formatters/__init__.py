"""Pipeline output formatters."""

import sys


def validate_output(logger, results, results_pull, is_pull):
    """Validate output exists and resolve pull request output.

    Calls sys.exit(0) if results have no output.

    Returns:
        dict: The pull request output dict, or an empty dict if not applicable.
              Returns dict (not list) so callers can safely use .get().
    """
    if not results.output:
        logger.error("Terminating test")
        sys.exit(0)
    if is_pull and results_pull.pr:
        return results_pull.output
    return {}
