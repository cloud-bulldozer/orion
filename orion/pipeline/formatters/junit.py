"""JUnit XML output formatter for Orion pipeline."""

import os
import xml.dom.minidom
import xml.etree.ElementTree as ET

from orion.pipeline.formatters import validate_output
from orion.utils import get_output_extension


class JUnitFormatter: # pylint: disable=too-few-public-methods
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
        output_pull = validate_output(logger, results, results_pull, is_pull)
        testsuites = ET.Element("testsuites")
        ext = get_output_extension(kwargs['output_format'])
        # TODO: XML serialization inside the loop causes duplicate stdout output  # pylint: disable=fixme
        # on multi-test runs. Move serialization/writing after the loop in Phase 6.
        for test_name, result_table in results.output.items():
            testsuites.append(result_table)
            if is_pull:
                results.average_values.tag = "periodic_avg"
                testsuites.append(results.average_values)
                output_pull.get(test_name).tag = "pull"
                testsuites.append(output_pull.get(test_name))
            xml_str = ET.tostring(testsuites, encoding="utf8", method="xml").decode()
            dom = xml.dom.minidom.parseString(xml_str)
            pretty_xml_as_string = dom.toprettyxml()
            print(pretty_xml_as_string)
            output_file_name = (
                f"{os.path.splitext(kwargs['save_output_path'])[0]}.{ext}"
            )
            with open(output_file_name, 'w', encoding="utf-8") as file:
                file.write(str(pretty_xml_as_string))
            logger.info("Output saved to %s", output_file_name)
            if results.regression_flag:
                return True
        return False
