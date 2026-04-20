"""JSON output formatter for Orion pipeline."""

import json
import os
import sys

from orion.utils import get_output_extension


class JsonFormatter:
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
            output_file_name = (
                f"{os.path.splitext(kwargs['save_output_path'])[0]}"
                f"_{test_name}.{get_output_extension(kwargs['output_format'])}"
            )
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
