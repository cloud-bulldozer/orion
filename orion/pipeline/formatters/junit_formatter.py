"""JUnit XML output formatter."""

import json
import os
import xml.dom.minidom
import xml.etree.ElementTree as ET
from typing import Any

from orion.pipeline.analysis_result import AnalysisResult
from orion.pipeline.formatters.base import BaseFormatter
from orion.pipeline.formatters.json_formatter import JsonFormatter
from orion.utils import json_to_junit


class JUnitFormatter(BaseFormatter):
    """Formats analysis results as JUnit XML."""

    def format(self, data: AnalysisResult) -> dict:
        json_formatter = JsonFormatter()
        json_result = json_formatter.format(data)
        data_json = json.loads(json_result[data.test_name])
        data_junit = json_to_junit(
            test_name=data.test_name,
            data_json=data_json,
            metrics_config=data.metrics_config,
            uuid_field=data.uuid_field,
            display_fields=data.display_fields,
        )
        return {data.test_name: data_junit}

    def format_average(self, data: AnalysisResult) -> ET.Element:
        avg_json = data.avg_values.to_json()
        return json_to_junit(
            test_name=data.test_name + "_average",
            data_json=avg_json,
            metrics_config=data.metrics_config,
            uuid_field=data.uuid_field,
            average=True,
        )

    def save(self, test_name: str, formatted: Any,
             save_output_path: str) -> None:
        base = os.path.splitext(save_output_path)[0]
        output_file = f"{base}.xml"
        testsuites = ET.Element("testsuites")
        testsuites.append(formatted)
        xml_str = ET.tostring(
            testsuites, encoding="utf8", method="xml"
        ).decode()
        dom = xml.dom.minidom.parseString(xml_str)
        pretty_xml = dom.toprettyxml()
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(pretty_xml)

    def print_output(self, test_name: str, formatted: Any,
                     data: AnalysisResult, pr: int = 0,
                     is_pull: bool = False) -> None:
        testsuites = ET.Element("testsuites")
        testsuites.append(formatted)
        xml_str = ET.tostring(
            testsuites, encoding="utf8", method="xml"
        ).decode()
        dom = xml.dom.minidom.parseString(xml_str)
        print(dom.toprettyxml())
