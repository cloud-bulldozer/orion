"""JSON output formatter for Orion pipeline."""

import json
import os

from orion.pipeline.formatters import validate_output
from orion.utils import get_output_extension


class JsonFormatter: # pylint: disable=too-few-public-methods
    """Formats test results as JSON and prints to stdout/file."""

    def format(self, logger, kwargs, results, results_pull, is_pull) -> bool:
        """Format and output JSON results.

        Args:
            logger: logger instance
            kwargs: CLI keyword arguments
            results: periodic TestResults
            results_pull: pull request TestResults
            is_pull: whether PR analysis mode is active

        Returns:
            bool: True if regression detected
        """
        logger.info("Printing json output")
        output_pull = validate_output(logger, results, results_pull, is_pull)
        ext = get_output_extension(kwargs['output_format'])
        for test_name, result_table in results.output.items():
            output_file_name = (
                f"{os.path.splitext(kwargs['save_output_path'])[0]}"
                f"_{test_name}.{ext}"
            )
            if is_pull:
                combined = {
                    "periodic": json.loads(result_table),
                    "periodic_avg": json.loads(results.average_values),
                    "pull": json.loads(output_pull.get(test_name)),
                }
                formatted = json.dumps(combined, indent=2)
            else:
                formatted = str(result_table)
            print(formatted)
            with open(output_file_name, 'w', encoding="utf-8") as file:
                file.write(formatted)
            logger.info("Output saved to %s", output_file_name)
            if results.regression_flag:
                return True
        return False
