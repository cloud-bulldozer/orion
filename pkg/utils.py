# pylint: disable=cyclic-import, R0914
# pylint: disable = line-too-long, too-many-arguments, consider-using-enumerate, broad-exception-caught
"""
module for all utility functions orion uses
"""
# pylint: disable = import-error

import os
import re
import sys
import xml.etree.ElementTree as ET
import xml.dom.minidom
from datetime import datetime, timedelta, timezone
from typing import  Any, Dict
from fmatch.logrus import SingletonLogger
from tabulate import tabulate
import pandas as pd



def extract_metadata_from_test(test: Dict[str, Any]) -> Dict[Any, Any]:
    """Gets metadata of the run from each test

    Args:
        test (dict): test dictionary

    Returns:
        dict: dictionary of the metadata
    """
    logger_instance = SingletonLogger.getLogger("Orion")
    metadata = test["metadata"]
    metadata = {key: str(value) for key, value in metadata.items()}
    logger_instance.debug("metadata" + str(metadata))
    return metadata

def get_datasource(data: Dict[Any, Any]) -> dict:
    """Gets es url from config or env

    Args:
        data (_type_): config file data
        logger (_type_): logger

    Returns:
        str: es url
    """
    logger_instance = SingletonLogger.getLogger("Orion")
    if data["datasource"]["type"].lower() == "telco":
        datasource = data["datasource"]
        datasource_config = {"host": os.environ.get("SPLUNK_HOST", datasource.get("host","")),
                             "port": os.environ.get("SPLUNK_PORT", datasource.get("port","")),
                             "username": os.environ.get("SPLUNK_USERNAME", datasource.get("username","")),
                             "password": os.environ.get("SPLUNK_PASSWORD", datasource.get("password","")),
                             "indice": os.environ.get("SPLUNK_INDICE", datasource.get("indice",""))}
        datasource.update(datasource_config)
        return datasource
    if data["datasource"]["type"].lower() == "perfscale":
        if "ES_SERVER" in data["datasource"].keys():
            return data["datasource"]
        if "ES_SERVER" in os.environ:
            datasource = data["datasource"]
            datasource.update({"ES_SERVER":os.environ.get("ES_SERVER")})
            return datasource

    logger_instance.error("Datasurce variable/config variable not set")
    sys.exit(1)


def shorten_url(shortener: any, uuids: str) -> str:
    """Shorten url if there is a list of buildUrls

    Args:
        shortener (any): shortener object to use tinyrl.short on
        uuids (List[str]): List of uuids to shorten

    Returns:
        str: a combined string of shortened urls
    """
    short_url_list = []
    for buildUrl in uuids.split(","):
        short_url_list.append(shortener.tinyurl.short(buildUrl))
    short_url = ','.join(short_url_list)
    return short_url


def json_to_junit(
    test_name: str,
    data_json: Dict[Any, Any],
    metrics_config: Dict[Any, Any],
    options: Dict[Any, Any],
) -> str:
    """Convert json to junit format

    Args:
        test_name (_type_): _description_
        data_json (_type_): _description_

    Returns:
        _type_: _description_
    """
    testsuites = ET.Element("testsuites")
    testsuite = ET.SubElement(
        testsuites, "testsuite", name=f"{test_name} nightly compare"
    )
    failures_count = 0
    test_count = 0
    for metric, value in metrics_config.items():
        test_count += 1
        labels = value.get("labels",[])
        label_string = " ".join(labels) if labels else ""
        testcase = ET.SubElement(
            testsuite,
            "testcase",
            name=f"{label_string} {metric} regression detection",
            timestamp=str(int(datetime.now().timestamp())),
        )
        if [
            run
            for run in data_json
            if not run["metrics"][metric]["percentage_change"] == 0
        ]:
            failures_count += 1
            failure = ET.SubElement(testcase, "failure")
            failure.text = (
                "\n"
                + generate_tabular_output(
                    data_json, metric_name=metric, collapse=options["collapse"]
                )
                + "\n"
            )

    testsuite.set("failures", str(failures_count))
    testsuite.set("tests", str(test_count))
    xml_str = ET.tostring(testsuites, encoding="utf8", method="xml").decode()
    dom = xml.dom.minidom.parseString(xml_str)
    pretty_xml_as_string = dom.toprettyxml()
    return pretty_xml_as_string


def generate_tabular_output(data: list, metric_name: str, collapse: bool) -> str:
    """converts json to tabular format

    Args:
        data (list):data in json format
        metric_name (str): metric name
    Returns:
        str: tabular form of data
    """
    records = []
    create_record = lambda record: {  # pylint: disable = C3001
        "uuid": record["uuid"],
        "timestamp": datetime.fromtimestamp(record["timestamp"], timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "buildUrl": record["buildUrl"],
        metric_name: record["metrics"][metric_name]["value"],
        "is_changepoint": bool(record["metrics"][metric_name]["percentage_change"]),
        "percentage_change": record["metrics"][metric_name]["percentage_change"],
    }
    if collapse:
        for i in range(1, len(data)):
            if data[i]["metrics"][metric_name]["percentage_change"] != 0:
                records.append(create_record(data[i - 1]))
                records.append(create_record(data[i]))
                if i + 1 < len(data):
                    records.append(create_record(data[i + 1]))
    else:
        for i in range(0, len(data)):
            records.append(create_record(data[i]))

    df = pd.DataFrame(records).drop_duplicates().reset_index(drop=True)
    table = tabulate(df, headers="keys", tablefmt="psql")
    lines = table.split("\n")
    highlighted_lines = []
    if lines:
        highlighted_lines += lines[0:3]
    for i, line in enumerate(lines[3:-1]):
        if df["percentage_change"][i]:  # Offset by 3 to account for header and separator
            highlighted_line = f"{lines[i+3]} -- changepoint"
            highlighted_lines.append(highlighted_line)
        else:
            highlighted_lines.append(line)
    highlighted_lines.append(lines[-1])

    # Join the lines back into a single string
    highlighted_table = "\n".join(highlighted_lines)

    return highlighted_table


def get_subtracted_timestamp(time_duration: str) -> datetime:
    """Get subtracted datetime from now

    Args:
        time_duration (str): time_gap in XdYh format

    Returns:
        datetime: return datetime of given timegap from now
    """
    logger_instance = SingletonLogger.getLogger("Orion")
    reg_ex = re.match(r"^(?:(\d+)d)?(?:(\d+)h)?$", time_duration)
    if not reg_ex:
        logger_instance.error("Wrong format for time duration, please provide in XdYh")
    days = int(reg_ex.group(1)) if reg_ex.group(1) else 0
    hours = int(reg_ex.group(2)) if reg_ex.group(2) else 0
    duration_to_subtract = timedelta(days=days, hours=hours)
    current_time = datetime.now(timezone.utc)
    timestamp_before = current_time - duration_to_subtract
    return timestamp_before
