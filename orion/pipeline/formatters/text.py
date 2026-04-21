"""Text/tabular output formatter for Orion pipeline."""

import os
import sys

from orion.reporting.summary import print_regression_summary


def save_text_table(test_name, result_table, save_output_path, run_type=""):
    """Save the text table to a file."""
    suffix = f"_{run_type}" if run_type else ""
    output_file_name = f"{os.path.splitext(save_output_path)[0]}_table_{test_name}{suffix}.txt"
    with open(output_file_name, 'w', encoding="utf-8") as file:
        file.write(str(result_table))


class TextFormatter: # pylint: disable=too-few-public-methods
    """Formats test results as text tables and prints to stdout/file."""

    def format(self, logger, kwargs, results, results_pull, is_pull) -> bool:
        """Format and output text results.

        Args:
            logger: logger instance
            kwargs: CLI keyword arguments
            results: periodic TestResults
            results_pull: pull request TestResults
            is_pull: whether PR analysis mode is active

        Returns:
            bool: True if regression detected
        """
        has_regression = self._print_results(logger, kwargs, results, is_pull)
        if is_pull:
            self._print_results(logger, kwargs, results_pull, is_pull)
        return has_regression

    def _print_results(self, logger, kwargs, results, is_pull) -> bool:
        """Print results for a single TestResults object."""
        output = results.output
        regression_flag = results.regression_flag
        regression_data = results.regression_data
        average_values = results.average_values
        # results.pr may be a string from YAML/Jinja templates
        try:
            pr = int(results.pr) if is_pull else 0
        except (ValueError, TypeError):
            pr = 0
        if not output:
            logger.error("Terminating test")
            sys.exit(0)
        for test_name, result_table in output.items():
            if is_pull:
                run_type = f"pull_{pr}" if pr > 0 else "periodic"
            else:
                run_type = ""
            save_text_table(test_name, result_table, kwargs['save_output_path'], run_type)
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
