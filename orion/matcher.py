"""metadata matcher"""

# pylint: disable = invalid-name, invalid-unary-operand-type, no-member
from datetime import datetime
from typing import List, Dict, Any


# pylint: disable=import-error
import pandas as pd
from opensearchpy import OpenSearch
from opensearch_dsl import Search, Q
from orion.logger import SingletonLogger


class Matcher:
    """
    A class used to match or interact with an Elasticsearch index for performance scale testing.

    Attributes:
        index (str): Name of the Elasticsearch index to interact with.
        es_url (str): Elasticsearch endpoint
        verify_certs (bool): Whether to verify SSL certificates when connecting to Elasticsearch.
        version_field (str): Name of the field containing the OpenShift version.
        uuid_field (str): Name of the field containing the UUID.
    """

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        index: str = "ospst-perf-scale-ci",
        es_server: str = "https://localhost:9200",
        verify_certs: bool = True,
        version_field: str = "ocpVersion",
        uuid_field: str = "uuid"
    ):
        self.index = index
        self.search_size = 10000
        self.logger = SingletonLogger.get_logger("Orion")
        self.es = OpenSearch(es_server,
                             timeout=30,
                             verify_certs=verify_certs,
                             http_compress=True,
                             max_retries=3,
                             retry_on_timeout=True,
                             pool_maxsize=5)
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

    def query_index(self, search: Search, return_all: bool = False, max_hits: int = 0):
        """Query index using search_after

        Args:
            search (Search): Search object with query
            return_all (bool): Returns full list of documents (optional)
            max_hits (int): When > 0 and return_all is True, stop collecting
                after this many hits. Defaults to 0 (no limit).
        """
        self.logger.info("Executing query against index: %s", self.index)
        self.logger.debug("Executing query \r\n%s", search.to_dict())

        all_hits = []
        search_after = None
        while True:
            if search_after:
                search = search.extra(search_after=search_after)

            response = search.execute()
            hits = response.hits.hits

            if not hits:
                break

            if not return_all:
                return response

            all_hits.extend(hits)

            if 0 < max_hits <= len(all_hits):
                all_hits = all_hits[:max_hits]
                break

            search_after = response.hits[-1].meta.sort
        return all_hits

    # pylint: disable=too-many-locals
    def get_uuid_by_metadata(
        self,
        metadata: Dict[str, Any],
        lookback_date: datetime = None,
        lookback_size: int = 10000,
        timestamp_field: str = "timestamp",
        since_date: datetime = None,
        additional_fields: List[str] = None
    ) -> List[Dict[str, str]]:
        """gets uuid by metadata

        Args:
            metadata (Dict[str, Any]): metadata of the runs
            lookback_date (datetime, optional):
            The cutoff date to get the uuids from. Defaults to None.
            lookback_size (int, optional):
            Maximum number of runs to get, gets the latest. Defaults to 10000.

            lookback_size and lookback_date get the data on the
            precedency of whichever cutoff comes first.
            Similar to a car manufacturer's warranty limits.
            timestamp_field (str): timestamp field in data
            since_date (datetime, optional):
            The end date to bound the range to. If provided, results will be 
            bounded between lookback_date and since_date. Defaults to None.
            additional_fields (List[str], optional): Additional fields to include
            in the result. Defaults to None.

        Returns:
            List[Dict[str, str]]: List of dictionaries with uuid, buildURL and ocpVersion as keys
        """
        must_clause = []
        must_not_clause = []
        filter_clause = []

        for field, value in metadata.items():
            if field in [self.version_field, "ocpMajorVersion"]:
                continue
            if field == "pullNumber" and value == 0 :
                continue
            if field in ("not", "wildcard"):
                continue
            must_clause.append(Q("match", **{field: str(value)}))
        for not_field, not_value in metadata.get("not", {}).items():
            values = not_value if isinstance(not_value, list) else [not_value]
            for val in values:
                must_not_clause.append(Q("match", **{not_field: str(val)}))
        for field, value in metadata.get("wildcard", {}).items():
            filter_clause.append(Q("wildcard", **{field: {"value": f"{value}"}}))
        if isinstance(lookback_date, datetime):
            lookback_date = lookback_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        if isinstance(since_date, datetime):
            since_date = since_date.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Build the range query based on available dates
        if lookback_date and since_date:
            # Bound the range between lookback_date and since_date
            range_query = {"gt": lookback_date, "lt": since_date}
            filter_clause.append(Q("range", **{timestamp_field: range_query}))
        elif lookback_date:
            # Only lower bound with lookback_date
            filter_clause.append(Q("range", **{timestamp_field: {"gt": lookback_date}}))
        elif since_date:
            # Only upper bound with since_date
            filter_clause.append(Q("range", **{timestamp_field: {"lt": since_date}}))
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
        all_hits = self.query_index(s, return_all=True, max_hits=lookback_size)
        uuids_docs = []
        for hit in all_hits:
            doc= {self.uuid_field: hit.to_dict()["_source"][self.uuid_field]}
            if "." in self.version_field:
                value = self.dotDictFind(hit.to_dict()["_source"], self.version_field)
                doc[self.version_field] = value
            elif self.version_field in hit.to_dict()["_source"]:
                doc[self.version_field] = hit.to_dict()["_source"][self.version_field]
            else :
                doc[self.version_field] = "No Version"
            source_data = hit.to_dict()["_source"]

            # Handle buildUrl with fallback to build_url
            if "buildUrl" in source_data:
                doc["buildUrl"] = source_data["buildUrl"]
            elif "build_url" in source_data:
                doc["buildUrl"] = source_data["build_url"]
            else:
                doc["buildUrl"] = "http://bogus-url"

            # Add additional fields if requested
            if additional_fields:
                for field in additional_fields:
                    doc[field] = source_data.get(field, "N/A")

            uuids_docs.append(doc)
        return uuids_docs

    def match_kube_burner(self, uuids: List[str],
                          timestamp_field: str = "timestamp") -> List[Dict[str, Any]]:
        """match kube burner runs
        Args:
            uuids (list): list of uuids
            timestamp_field (str): timestamp field in data
        Returns:
            list : list of runs
        """
        query = Q(
            "bool",
            filter=[
                Q("terms", **{self.uuid_field+".keyword": uuids}),
                Q("match", metricName="jobSummary"),
                ~Q("match", **{"jobName.keyword": "garbage-collection"}),
            ],
        )
        search = (
            Search(using=self.es, index=self.index)
            .query(query)
            .extra(size=self.search_size)
            .sort({timestamp_field: {"order": "desc"}})
        )
        all_hits = self.query_index(search, return_all=True)
        runs = [hit.to_dict()["_source"] for hit in all_hits]
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
        self,
        uuid: str,
        uuids: List[str],
        metrics: Dict[str, Any],
        exists_fields: List[str] = None,
        timestamp_field: str = "timestamp"
    ) -> Dict[Any, Any]:
        """
        Get results of elasticsearch data query based on uuid(s) and defined metrics

        Args:
            uuid (str): uuid of the run
            uuids (list): list of uuids
            metrics (dict): metrics to query for
            exists_fields (list): list of fields that need to exist in the document
            timestamp_field (str): timestamp field in data

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
            if metric_key not in ["name", "metric_of_interest", "not", "type"]
        ]
        exists_queries = []
        if exists_fields:
            exists_queries = [
                Q("exists", **{"field": field})
                for field in exists_fields
            ]
        exist_query = Q("bool", must=exists_queries)
        metric_query = Q("bool", must=metric_queries + not_queries)
        query = Q(
            "bool",
            must=[
                Q("terms", **{self.uuid_field+".keyword": uuids}),
                metric_query,
                exist_query
            ],
        )
        search = (
            Search(using=self.es, index=self.index)
            .query(query)
            .extra(size=self.search_size)
            .sort({timestamp_field: {"order": "desc"}})
        )
        all_hits = self.query_index(search, return_all=True)
        runs = [hit.to_dict()["_source"] for hit in all_hits]
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
            timestamp_field (str): timestamp field in data

        """
        metric_queries = []
        not_queries = [
            ~Q("match", **{not_item_key: not_item_value})
            for not_item_key, not_item_value in metrics.get("not", {}).items()
        ]
        metric_queries = [
            Q("match", **{metric_key: metric_value})
            for metric_key, metric_value in metrics.items()
            if metric_key not in ["name", "metric_of_interest", "not", "agg", "type"]
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
            .extra(size=0)
            .sort({timestamp_field: {"order": "desc"}})
        )
        metric_of_interest = metrics["metric_of_interest"]
        agg_type = metrics["agg"]["agg_type"]
        uuid_bucket = search.aggs.bucket("uuid", "terms", field=self.uuid_field+".keyword", size=len(uuids))
        uuid_bucket.metric("time", "avg", field=timestamp_field)
         # Handle percentile aggregations differently from single-value aggregations
        if agg_type == "percentiles":
            percents = metrics["agg"].get("percents")
            if not percents:
                self.logger.error(
                    "Metric '%s' has agg_type 'percentiles' but no 'percents' list — skipping",
                    metrics["name"]
                )
                return []
            uuid_bucket.metric(
                metric_of_interest, "percentiles",
                field=metrics["metric_of_interest"],
                percents=percents
            )
        elif agg_type == "count":
            # Count aggregation uses value_count in OpenSearch
            uuid_bucket.metric(metric_of_interest, "value_count", field=metrics["metric_of_interest"])
        else:
            # Standard aggregations (sum, avg, max, min)
            uuid_bucket.metric(metric_of_interest, agg_type, field=metrics["metric_of_interest"])
        result = search.execute()
        self.logger.info("Executing aggregated query for metric %s against index %s",
            metrics["name"], self.index)
        self.logger.debug("Executing query \r\n%s", search.to_dict())
        data = self.parse_agg_results(result, agg_type, timestamp_field, metrics)
        return data

    def parse_agg_results(
        self, data: Dict[Any, Any],
        agg_type: str,
        timestamp_field: str = "timestamp",
        metrics: Dict[str, Any] = None
    ) -> List[Dict[Any, Any]]:
        """parse out CPU data from kube-burner query
        Args:
            data (dict): Aggregated data from Elasticsearch DSL query
            agg_type (str): Aggregation type (e.g., 'avg', 'sum', 'percentiles', etc.)
            timestamp_field (str): Timestamp field name
            metrics (dict): Metrics configuration (needed for percentile target)
        Returns:
            list: List of parsed results
        """
        res = []
        if "aggregations" not in data:
            return res
        metric_of_interest = metrics["metric_of_interest"]
        uuids = data.aggregations.uuid.buckets

        for uuid in uuids:
            data = {
                self.uuid_field: uuid.key,
                timestamp_field: uuid.time.value_as_string,
            }
            value_key = metric_of_interest + "_" + agg_type
            if agg_type == "percentiles":
                self.logger.info("AC agg_type == percentiles")
                percentile_dict = uuid.get(metric_of_interest).to_dict().get("values", {})
                if metrics and "agg" in metrics and "target_percentile" in metrics["agg"]:
                    target_percentile = float(metrics["agg"]["target_percentile"])
                    percentile_key = str(target_percentile)
                    self.logger.info("found target_percentile %s", target_percentile)
                    value_key = metric_of_interest + "_" + agg_type + "_" + percentile_key
                    data[value_key] = percentile_dict.get(percentile_key)
                else:
                    self.logger.info("no target_percentile found, using all percentiles")
                    for key, val in percentile_dict.items():
                        self.logger.info("percentile_values value %s", key)
                        data[metric_of_interest + "_" + agg_type + "_" + str(key)] = val
            else:
                # Standard single-value aggregations
                data[value_key] = uuid.get(metric_of_interest).value
            res.append(data)
        return res

    def get_agg_metrics_batch(
        self, uuids: List[str],
        metrics_list: List[Dict[str, Any]],
        timestamp_field: str = "timestamp"
    ) -> Dict[str, List[Dict[Any, Any]]]:
        """Execute a single ES query with multiple sub-aggregations, one per metric.

        Args:
            uuids: List of UUIDs to filter on.
            metrics_list: List of metric config dicts, each with 'name',
                          'metric_of_interest', 'agg' block, and filter fields.
            timestamp_field: Timestamp field name.

        Returns:
            Dict mapping metric name -> list of parsed result dicts.
        """
        if not metrics_list:
            return {}

        query = Q(
            "bool",
            must=[Q("terms", **{self.uuid_field + ".keyword": uuids})],
        )
        search = (
            Search(using=self.es, index=self.index)
            .query(query)
            .extra(size=0)
            .sort({timestamp_field: {"order": "desc"}})
        )

        uuid_bucket = search.aggs.bucket(
            "uuid", "terms", field=self.uuid_field + ".keyword", size=len(uuids)
        )
        uuid_bucket.metric("time", "avg", field=timestamp_field)

        for metric in metrics_list:
            agg_name = metric["name"]
            agg_type = metric["agg"]["agg_type"]
            field = metric["metric_of_interest"]

            metric_filter_clauses = [
                Q("match", **{k: v})
                for k, v in metric.items()
                if k not in ("name", "metric_of_interest", "not", "agg", "type")
            ]
            not_clauses = [
                ~Q("match", **{k: v})
                for k, v in metric.get("not", {}).items()
            ]
            metric_filter = Q("bool", must=metric_filter_clauses + not_clauses)
            filtered_bucket = uuid_bucket.bucket(agg_name, "filter", metric_filter)

            if agg_type == "percentiles":
                percents = metric["agg"].get("percents")
                if not percents:
                    self.logger.error(
                        "Metric '%s' has agg_type 'percentiles' but no 'percents' list — skipping",
                        metric["name"]
                    )
                    continue
                filtered_bucket.metric(field, "percentiles", field=field, percents=percents)
            elif agg_type == "count":
                filtered_bucket.metric(field, "value_count", field=field)
            else:
                filtered_bucket.metric(field, agg_type, field=field)

        self.logger.info(
            "Executing batched aggregation query for %d metrics against index %s",
            len(metrics_list), self.index,
        )
        self.logger.debug("Executing query \r\n%s", search.to_dict())

        result = search.execute()
        return self.parse_batch_agg_results(result, metrics_list, timestamp_field)

    def parse_batch_agg_results(
        self, data, metrics_list: List[Dict[str, Any]],
        timestamp_field: str = "timestamp"
    ) -> Dict[str, List[Dict[Any, Any]]]:
        """Parse a batched multi-aggregation response into per-metric result lists.

        Args:
            data: ES response object.
            metrics_list: Same list passed to get_agg_metrics_batch.
            timestamp_field: Timestamp field name.

        Returns:
            Dict mapping metric name -> list of result dicts (one per UUID).
        """
        results = {m["name"]: [] for m in metrics_list}

        if "aggregations" not in data:
            return results

        uuid_buckets = data.aggregations.uuid.buckets

        for uuid_bucket in uuid_buckets:
            uuid_val = uuid_bucket.key
            ts_val = uuid_bucket.time.value_as_string

            for metric in metrics_list:
                agg_name = metric["name"]
                agg_type = metric["agg"]["agg_type"]
                field = metric["metric_of_interest"]
                filtered = uuid_bucket[agg_name]

                if filtered.doc_count == 0:
                    continue

                row = {
                    self.uuid_field: uuid_val,
                    timestamp_field: ts_val,
                }

                if agg_type == "percentiles":
                    pct_dict = filtered[field].to_dict().get("values", {})
                    if "target_percentile" in metric.get("agg", {}):
                        target = str(float(metric["agg"]["target_percentile"]))
                        col = f"{field}_{agg_type}_{target}"
                        row[col] = pct_dict.get(target)
                    else:
                        for k, v in pct_dict.items():
                            row[f"{field}_{agg_type}_{k}"] = v
                else:
                    col = f"{field}_{agg_type}"
                    row[col] = filtered[field].value

                results[agg_name].append(row)

        return results

    def get_results_batch(
        self,
        uuids: List[str],
        metrics_list: List[Dict[str, Any]],
        timestamp_field: str = "timestamp"
    ) -> Dict[str, List[Dict[Any, Any]]]:
        """Fetch multiple standard metrics in a single ES query using an OR filter.

        Args:
            uuids: List of UUIDs.
            metrics_list: List of metric config dicts.
            timestamp_field: Timestamp field name.

        Returns:
            Dict mapping metric name -> list of hit _source dicts.
        """
        if not metrics_list:
            return {}

        excluded_keys = {"name", "metric_of_interest", "not", "type"}
        filter_fields_by_metric = []
        should_clauses = []
        for metric in metrics_list:
            match_fields = {
                k: v for k, v in metric.items()
                if k not in excluded_keys
            }
            filter_clauses = [Q("match", **{k: v}) for k, v in match_fields.items()]
            not_clauses = [
                ~Q("match", **{k: v})
                for k, v in metric.get("not", {}).items()
            ]
            should_clauses.append(Q("bool", must=filter_clauses + not_clauses))
            not_fields = metric.get("not", {})
            filter_fields_by_metric.append((metric["name"], match_fields, not_fields))

        query = Q(
            "bool",
            must=[Q("terms", **{self.uuid_field + ".keyword": uuids})],
            should=should_clauses,
            minimum_should_match=1,
        )
        search = (
            Search(using=self.es, index=self.index)
            .query(query)
            .extra(size=self.search_size)
            .sort({timestamp_field: {"order": "desc"}})
        )

        self.logger.info(
            "Executing batched standard query for %d metrics against index %s",
            len(metrics_list), self.index,
        )

        all_hits = self.query_index(search, return_all=True)
        runs = [hit.to_dict()["_source"] for hit in all_hits]

        results = {m["name"]: [] for m in metrics_list}
        for doc in runs:
            matched = False
            for metric_name, match_fields, not_fields in filter_fields_by_metric:
                matches_positive = all(
                    self._get_nested(doc, k.replace(".keyword", "")) == v
                    for k, v in match_fields.items()
                )
                matches_negative = all(
                    self._get_nested(doc, k.replace(".keyword", "")) != v
                    for k, v in not_fields.items()
                )
                if matches_positive and matches_negative:
                    results[metric_name].append(doc)
                    matched = True
                    break
            if not matched:
                self.logger.debug(
                    "Document did not match any metric filter: %s",
                    doc.get(self.uuid_field)
                )

        return results

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

    @staticmethod
    def _get_nested(doc: dict, key: str):
        """Retrieve a value from a nested dict using dot-notation key.

        Falls back to flat key lookup so plain (non-nested) fields still work.
        """
        if "." in key:
            parts = key.split(".", 1)
            sub = doc.get(parts[0])
            if isinstance(sub, dict):
                return Matcher._get_nested(sub, parts[1])
        return doc.get(key)

    def dotDictFind(self, data: dict, find: str) -> str:
        """
        Navigate through nested dictionary using dot notation.

        Args:
            data: The dictionary to search
            find: Dot-separated path (e.g., "tags.sw_version")

        Returns:
            str: The value found at the specified path
        """
        keys = find.split('.')
        v = {}
        for val in keys:
            if not v:
                v = data[val]
            else:
                v = v[val]
            if not isinstance(v, dict):
                return v
        return v
