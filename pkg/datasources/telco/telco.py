# pylint: disable = R0903, E0211, W0236
"""
Telco datasource
"""

from datetime import datetime, timedelta
import hashlib
import json
from typing import Dict, Any, Tuple
import uuid

import pandas as pd
from fmatch.logrus import SingletonLogger
from pkg.datasources.datasource import Datasource
from pkg.utils import extract_metadata_from_test


class TelcoDatasource(Datasource):
    """Telco datasource

    Args:
        Datasource (_type_): _description_
    """

    async def process_test(self) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """processing splunk data

        Args:
            test (Dict[str, Any]): splunk test
            match (SplunkMatcher): splunk matcher
            options (Dict[str, Any]): options for further use

        Returns:
            Tuple[pd.DataFrame, Dict[str, Any]]: _description_
        """

        logger = SingletonLogger.getLogger("Orion")
        logger.info("The test %s has started", self.test["name"])
        metadata = extract_metadata_from_test(self.test)
        logger.debug(f"Collected metadata {metadata}")
        start_timestamp = None
        if isinstance(self.start_timestamp, datetime):
            start_timestamp = self.start_timestamp
        else:
            start_timestamp = (
                datetime.strptime(self.start_timestamp, "%Y-%m-%d %H:%M:%S")
                if self.start_timestamp
                else datetime.now() - timedelta(days=30)
            )
        logger.debug(f"start timestamps for the test is {start_timestamp}")
        searchList = " AND ".join(
            [f'{key}="{value}"' for key, value in metadata.items()]
        )
        query = {
            "earliest_time": f"{start_timestamp.strftime('%Y-%m-%d')}T00:00:00",
            "latest_time": f"{datetime.now().strftime('%Y-%m-%d')}T23:59:59",
            "output_mode": "json",
        }
        logger.debug(f"Executing query {searchList}")
        data = await self.match.query(
            query=query, searchList=searchList, max_results=10000
        )
        seen = set()
        unique_data = []
        for d in data:
            # Serialize the dictionary into a JSON string (sorted for consistency)
            serialized = json.dumps(d, sort_keys=True)
            if serialized not in seen:
                seen.add(serialized)
                unique_data.append(d)
        data = unique_data
        # print(json.dumps(data[1],indent =4))
        logger.debug(f"Collected data {data}")
        metrics = self.test["metrics"]
        dataframe_list, metrics_config = get_splunk_metrics(data, metrics)

        return dataframe_list, metrics_config


def generate_uuid(record):
    """Generates uuid based on hash value of record

    Args:
        record (dict): _description_

    Returns:
        _type_: _description_
    """
    # Convert the record to a string format suitable for hashing
    record_string = str(record)
    # Create a hash of the record string
    hash_object = hashlib.md5(
        record_string.encode("utf-8")
    )  # You can use other hash functions if needed
    # Create a UUID from the hash
    return uuid.UUID(hash_object.hexdigest())


def get_splunk_metrics(data: dict, metrics: dict) -> Tuple[pd.DataFrame, dict]:
    """gets metrics from splunk data

    Args:
        data (dict): data with all the metrics
        metrics (dict): metrics needed to extracted

    Returns:
        Tuple[pd.DataFrame, dict]: _description_
    """
    logger_instance = SingletonLogger.getLogger("Orion")
    dataframe_rows = []
    metrics_config = {}

    for metric in metrics:
        logger_instance.info(f"Collecting metric {metric['name']}")

    for record in data:
        timestamp = int(record["timestamp"])
        record = record["data"]
        record_uuid = generate_uuid(record)
        row_data = {
            "uuid": record_uuid,
            "timestamp": timestamp,
            "buildUrl": "https://placeholder.com/"
            + record["cluster_artifacts"]["ref"]["jenkins_build"],
        }

        for metric in metrics:
            metric_name = metric["name"]
            metric_value_field = metric["metric_of_interest"]
            metric_value = get_nested_value(record, metric_value_field)
            row_data[metric_name] = metric_value
            metrics_config[metric_name] = metric

        dataframe_rows.append(row_data)

    df = pd.DataFrame(dataframe_rows)
    df.dropna(inplace=True)
    df.sort_values(by="timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)

    logger_instance.info(f"Generated DataFrame with {len(df)} rows")
    return df, metrics_config


def get_nested_value(record, keys, default=None):
    """Recursively traverse a nested dictionary/list to get a value based on dot-separated keys."""
    keys = keys.split(".")
    for key in keys:
        if isinstance(record, dict):
            record = record.get(key, default)
        elif isinstance(record, list):
            # For lists, we assume the user wants to filter based on some condition
            key_parts = key.split("==")
            if len(key_parts) == 2:
                filter_key, filter_value = key_parts[0], key_parts[1].strip('"')
                # Look for a matching dict in the list
                record = next(
                    (item for item in record if item.get(filter_key) == filter_value),
                    default,
                )
            else:
                return default  # Key format is incorrect, return default
        else:
            return default  # If it's neither dict nor list, return default
    return record
