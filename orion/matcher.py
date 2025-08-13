"""metadata matcher"""

# pylint: disable = invalid-name, invalid-unary-operand-type, no-member
import os
import logging
from datetime import datetime
from typing import List, Dict, Any

# pylint: disable=import-error
from elasticsearch import Elasticsearch


# pylint: disable=import-error
import pandas as pd
from elasticsearch_dsl import Search, Q
from elasticsearch_dsl.response import Response
from orion.logger import SingletonLogger


class Matcher:
    # pylint: disable=too-many-instance-attributes
    """
    A class used to match or interact with an Elasticsearch index for performance scale testing.

    Attributes:
        index (str): Name of the Elasticsearch index to interact with.
        level (int): Logging level (e.g., logging.INFO).
        es_url (str): Elasticsearch endpoint, can be specified by the environment variable ES_SERVER
        verify_certs (bool): Whether to verify SSL certificates when connecting to Elasticsearch.
        version_field (str): Name of the field containing the OpenShift version.
        uuid_field (str): Name of the field containing the UUID.
    """

    def __init__(
        self,
        index: str = "ospst-perf-scale-ci",
        level: int = logging.INFO,
        es_url: str = os.getenv("ES_SERVER"),
        verify_certs: bool = True,
        version_field: str = "ocpVersion",
        uuid_field: str = "uuid"
    ):
        self.index = index
        self.search_size = 10000
        self.logger = SingletonLogger(debug=level, name="Matcher")
        self.es = Elasticsearch([es_url], timeout=30, verify_certs=verify_certs)
        self.data = None
        self.version_field = version_field
        self.uuid_field = uuid_field

    def get_metadata_by_uuid(self, uuid: str) -> dict:
        """Returns back metadata when uuid is given

        Args:
            uuid (str): uuid of the run

        Returns:
            _type_: _description_
        """
        query = Q("match",  **{self.uuid_field: f"{uuid}"})
        result = {}
        s = Search(using=self.es, index=self.index).query(query)
        res = self.query_index(s)
        hits = res.hits.hits
        if hits:
            result = dict(hits[0].to_dict()["_source"])
        return result

    def query_index(self, search: Search) -> Response:
        """generic query function

        Args:
            search (Search) : Search object with query
        """
        self.logger.info("Executing query against index: %s", self.index)
        self.logger.debug("Executing query \r\n%s", search.to_dict())
        return search.execute()

    def get_uuid_by_metadata(
        self,
        meta: Dict[str, Any],
        lookback_date: datetime = None,
        lookback_size: int = 10000,
        timestamp_field: str = "timestamp"
    ) -> List[Dict[str, str]]:
        """gets uuid by metadata

        Args:
            meta (Dict[str, Any]): metadata of the runs
            lookback_date (datetime, optional):
            The cutoff date to get the uuids from. Defaults to None.
            lookback_size (int, optional):
            Maximum number of runs to get, gets the latest. Defaults to 10000.

            lookback_size and lookback_date get the data on the
            precedency of whichever cutoff comes first.
            Similar to a car manufacturer's warranty limits.

        Returns:
            List[Dict[str, str]]: _description_
        """
        must_clause = []
        must_not_clause = []
        version = str(meta[self.version_field])[:4]

        for field, value in meta.items():
            if field in [self.version_field, "ocpMajorVersion"]:
                continue
            if field != "not":
                must_clause.append(Q("match", **{field: str(value)}))
            else:
                for not_field, not_value in meta["not"].items():
                    must_not_clause.append(Q("match", **{not_field: str(not_value)}))

        if "ocpMajorVersion" in meta:
            version = meta["ocpMajorVersion"]
            filter_clause = [
                Q("wildcard", ocpMajorVersion=f"{version}*"),
            ]
        else:
            filter_clause = [
                Q("wildcard", **{self.version_field: {"value": f"{version}*"}}),
            ]

        if isinstance(lookback_date, datetime):
            lookback_date = lookback_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        if lookback_date:
            filter_clause.append(Q("range", **{timestamp_field: {"gt": lookback_date}}))
        query = Q(
            "bool",
            must=must_clause,
            must_not=must_not_clause,
            filter=filter_clause,
        )
        s = (
            Search(using=self.es, index=self.index)
            .query(query)
            .sort({timestamp_field: {"order": "desc"}})
            .extra(size=lookback_size)
        )
        result = self.query_index(s)
        hits = result.hits.hits
        uuids_docs = []
        for hit in hits:
            if "buildUrl" in hit["_source"]:
                uuids_docs.append(
                    {
                        self.uuid_field: hit.to_dict()["_source"][self.uuid_field],
                        "buildUrl": hit.to_dict()["_source"]["buildUrl"],
                        self.version_field: hit.to_dict()["_source"][self.version_field],
                    }
                )
            else:
                uuids_docs.append(
                    {
                        self.uuid_field: hit.to_dict()["_source"][self.uuid_field],
                        "buildUrl": "http://bogus-url",
                        self.version_field: hit.to_dict()["_source"][self.version_field],
                    }
                )
        return uuids_docs

    def match_kube_burner(self, uuids: List[str]) -> List[Dict[str, Any]]:
        """match kube burner runs
        Args:
            uuids (list): list of uuids
        Returns:
            list : list of runs
        """
        query = Q(
            "bool",
            filter=[
                Q("terms", **{self.uuid_field+".keyword": uuids}),
                Q("match", metricName="jobSummary"),
                ~Q("match", **{"jobConfig.name": "garbage-collection"}),
            ],
        )
        search = (
            Search(using=self.es, index=self.index)
            .query(query)
            .extra(size=self.search_size)
        )
        result = self.query_index(search)
        runs = [item.to_dict()["_source"] for item in result.hits.hits]
        return runs

    def filter_runs(self, pdata: Dict[Any, Any], data: Dict[Any, Any]) -> List[str]:
        """filter out runs with different jobIterations
        Args:
            pdata (_type_): _description_
            data (_type_): _description_
        Returns:
            _type_: _description_
        """
        columns = [self.uuid_field, "jobConfig.jobIterations"]
        pdf = pd.json_normalize(pdata)
        pick_df = pd.DataFrame(pdf, columns=columns)
        iterations = pick_df.iloc[0]["jobConfig.jobIterations"]
        df = pd.json_normalize(data)
        ndf = pd.DataFrame(df, columns=columns)
        ids_df = ndf.loc[df["jobConfig.jobIterations"] == iterations]
        return ids_df[self.uuid_field].to_list()

    def get_results(
        self, uuid: str,
        uuids: List[str],
        metrics: Dict[str, Any]
    ) -> Dict[Any, Any]:
        """
        Get results of elasticsearch data query based on uuid(s) and defined metrics

        Args:
            uuid (str): _description_
            uuids (list): _description_
            metrics (dict): _description_

        Returns:
            dict: Resulting data from query
        """
        if len(uuids) > 1 and uuid in uuids:
            uuids.remove(uuid)
        metric_queries = []
        not_queries = [
            ~Q("match", **{not_item_key: not_item_value})
            for not_item_key, not_item_value in metrics.get("not", {}).items()
        ]
        metric_queries = [
            Q("match", **{metric_key: metric_value})
            for metric_key, metric_value in metrics.items()
            if metric_key not in ["name", "metric_of_interest", "not"]
        ]
        metric_query = Q("bool", must=metric_queries + not_queries)
        query = Q(
            "bool",
            must=[
                Q("terms", **{self.uuid_field+".keyword": uuids}),
                metric_query
            ],
        )
        search = (
            Search(using=self.es, index=self.index)
            .query(query)
            .extra(size=self.search_size)
        )
        result = self.query_index(search)
        runs = [item.to_dict()["_source"] for item in result.hits.hits]
        return runs

    def get_agg_metric_query(
        self, uuids: List[str],
        metrics: Dict[str, Any],
        timestamp_field: str = "timestamp"
    ):
        """burner_metric_query will query for specific metrics data.

        Args:
            uuids (list): List of uuids
            metrics (dict): metrics defined in es index metrics
        """
        metric_queries = []
        not_queries = [
            ~Q("match", **{not_item_key: not_item_value})
            for not_item_key, not_item_value in metrics.get("not", {}).items()
        ]
        metric_queries = [
            Q("match", **{metric_key: metric_value})
            for metric_key, metric_value in metrics.items()
            if metric_key not in ["name", "metric_of_interest", "not", "agg"]
        ]
        metric_query = Q("bool", must=metric_queries + not_queries)
        query = Q(
            "bool",
            must=[
                Q("terms", **{self.uuid_field + ".keyword": uuids}),
                metric_query,
            ],
        )
        search = (
            Search(using=self.es, index=self.index)
            .query(query)
            .extra(size=self.search_size)
        )
        agg_value = metrics["agg"]["value"]
        agg_type = metrics["agg"]["agg_type"]
        search.aggs.bucket(
            "time", "terms", field=self.uuid_field+".keyword", size=self.search_size
        ).metric("time", "avg", field=timestamp_field)
        search.aggs.bucket(
            "uuid", "terms", field=self.uuid_field+".keyword", size=self.search_size
        ).metric(agg_value, agg_type, field=metrics["metric_of_interest"])
        result = self.query_index(search)
        data = self.parse_agg_results(result, agg_value, agg_type, timestamp_field)
        return data

    def parse_agg_results(
        self, data: Dict[Any, Any],
        agg_value: str,
        agg_type: str,
        timestamp_field: str = "timestamp"
    ) -> List[Dict[Any, Any]]:
        """parse out CPU data from kube-burner query
        Args:
            data (dict): Aggregated data from Elasticsearch DSL query
            agg_value (str): Aggregation value field name
            agg_type (str): Aggregation type (e.g., 'avg', 'sum', etc.)
        Returns:
            list: List of parsed results
        """
        res = []
        stamps = data.aggregations.time.buckets
        agg_buckets = data.aggregations.uuid.buckets

        for stamp in stamps:
            dat = {}
            dat[self.uuid_field] = stamp.key
            dat[timestamp_field] = stamp.time.value_as_string
            agg_values = next(
                (item for item in agg_buckets if item.key == stamp.key), None
            )
            if agg_values:
                dat[agg_value + "_" + agg_type] = agg_values[agg_value].value
            else:
                dat[agg_value + "_" + agg_type] = None
            res.append(dat)
        return res

    def convert_to_df(
        self, data: Dict[Any, Any],
        columns: List[str] = None,
        timestamp_field: str = "timestamp"
    ) -> pd.DataFrame:
        """convert to a dataframe
        Args:
            data (_type_): _description_
            columns (_type_, optional): _description_. Defaults to None.
        Returns:
            _type_: _description_
        """
        odf = pd.json_normalize(data)
        odf = odf.sort_values(by=[timestamp_field])
        if columns is not None:
            odf = pd.DataFrame(odf, columns=columns)
        return odf

    def save_results(
        self,
        df: pd.DataFrame,
        csv_file_path: str = "output.csv",
        columns: List[str] = None,
    ) -> None:
        """write results to CSV
        Args:
            df (_type_): _description_
            csv_file_path (str, optional): _description_. Defaults to "output.csv".
            columns (_type_, optional): _description_. Defaults to None.
        """
        if columns is not None:
            df = pd.DataFrame(df, columns=columns)
        df.to_csv(csv_file_path)
