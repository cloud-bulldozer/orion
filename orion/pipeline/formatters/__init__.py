"""Pipeline output formatters."""

import sys


def validate_output(logger, results, results_pull, is_pull):
    """Validate output exists and resolve pull request output.

    Calls sys.exit(0) if results have no output.

    Returns:
        The pull request output dict, or an empty list if not applicable.
    """
    if not results.output:
        logger.error("Terminating test")
        sys.exit(0)
    if is_pull and results_pull.pr:
        return results_pull.output
    return []
