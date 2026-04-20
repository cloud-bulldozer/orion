"""JUnit XML output formatter for Orion pipeline."""

import os
import sys
import xml.dom.minidom
import xml.etree.ElementTree as ET

from orion.utils import get_output_extension


class JUnitFormatter:
    """Formats test results as JUnit XML and prints to stdout/file."""

    def format(self, logger, kwargs, results, results_pull, is_pull) -> bool:
        """Format and output JUnit XML results.

        Args:
            logger: logger instance
            kwargs: CLI keyword arguments
            results: periodic TestResults
            results_pull: pull request TestResults
            is_pull: whether PR analysis mode is active

        Returns:
            bool: True if regression detected
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
            output_file_name = (
                f"{os.path.splitext(kwargs['save_output_path'])[0]}"
                f".{get_output_extension(kwargs['output_format'])}"
            )
            with open(output_file_name, 'w', encoding="utf-8") as file:
                file.write(str(pretty_xml_as_string))
            logger.info("Output saved to %s", output_file_name)
            if regression_flag:
                return True
        return False
