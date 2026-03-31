"""
Additional unit tests for orion/matcher.py — covering gaps in existing test_matcher.py

Focuses on: get_uuid_by_metadata edge cases (not clause, ocpMajorVersion,
build_url fallback, additional_fields, since_date), get_metadata_by_uuid
actual logic, parse_agg_results edge cases, convert_to_df without columns.
"""

# pylint: disable = redefined-outer-name
# pylint: disable = missing-function-docstring
# pylint: disable = import-error, duplicate-code
# pylint: disable = missing-class-docstring
# pylint: disable = import-outside-toplevel

import logging
from unittest.mock import patch

import pandas as pd
import pytest
from opensearch_dsl import Search
from opensearch_dsl.response import Response

from orion.logger import SingletonLogger
from orion.matcher import Matcher


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

class FakeHit:
    """Mock hit simulating OpenSearch results."""
    def __init__(self, doc):
        self._doc = doc

    def to_dict(self):
        return {"_source": self._doc["_source"]}

    def __getitem__(self, key):
        return self._doc[key]


def _make_matcher(index="perf-scale-ci", uuid_field="uuid", version_field="ocpVersion"):
    sample_output = {
        "hits": {
            "hits": [
                {"_source": {uuid_field: "uuid1", "field1": "value1"}},
            ]
        }
    }
    with patch("orion.matcher.OpenSearch") as mock_es:
        mock_es_instance = mock_es.return_value
        mock_es_instance.search.return_value = Response(
            search=Search(), response=sample_output
        )
        SingletonLogger(debug=logging.DEBUG, name="Orion")
        return Matcher(
            index=index,
            uuid_field=uuid_field,
            version_field=version_field,
        )


@pytest.fixture(autouse=True)
def _init_logger():
    SingletonLogger(debug=logging.DEBUG, name="Orion")


@pytest.fixture
def matcher():
    return _make_matcher()


# ---------------------------------------------------------------------------
# get_metadata_by_uuid — actual method logic
# ---------------------------------------------------------------------------

class TestGetMetadataByUuid:
    def test_returns_source_dict(self, matcher, monkeypatch):
        fake_response = type("R", (), {
            "hits": type("H", (), {
                "hits": [FakeHit({"_source": {"uuid": "u1", "platform": "aws"}})]
            })()
        })()
        monkeypatch.setattr(matcher, "query_index", lambda *a, **k: fake_response)
        result = matcher.get_metadata_by_uuid("u1")
        assert result["platform"] == "aws"

    def test_empty_hits_returns_empty(self, matcher, monkeypatch):
        fake_response = type("R", (), {
            "hits": type("H", (), {"hits": []})()
        })()
        monkeypatch.setattr(matcher, "query_index", lambda *a, **k: fake_response)
        result = matcher.get_metadata_by_uuid("missing")
        assert result == {}


# ---------------------------------------------------------------------------
# get_uuid_by_metadata — edge cases
# ---------------------------------------------------------------------------

class TestGetUuidByMetadataEdgeCases:
    def test_build_url_fallback(self, matcher, monkeypatch):
        """When buildUrl is missing, fall back to build_url."""
        hits = [FakeHit({
            "_source": {
                "uuid": "u1",
                "build_url": "http://fallback-url",
                "ocpVersion": "4.15",
            }
        })]
        monkeypatch.setattr(matcher, "query_index", lambda *a, **k: hits)
        result = matcher.get_uuid_by_metadata({"ocpVersion": "4.15"})
        assert result[0]["buildUrl"] == "http://fallback-url"

    def test_no_build_url_at_all(self, matcher, monkeypatch):
        """When neither buildUrl nor build_url exist, use bogus fallback."""
        hits = [FakeHit({
            "_source": {
                "uuid": "u1",
                "ocpVersion": "4.15",
            }
        })]
        monkeypatch.setattr(matcher, "query_index", lambda *a, **k: hits)
        result = matcher.get_uuid_by_metadata({"ocpVersion": "4.15"})
        assert result[0]["buildUrl"] == "http://bogus-url"

    def test_additional_fields(self, matcher, monkeypatch):
        """Additional fields from source are included in result."""
        hits = [FakeHit({
            "_source": {
                "uuid": "u1",
                "buildUrl": "http://url",
                "ocpVersion": "4.15",
                "jobType": "periodic",
            }
        })]
        monkeypatch.setattr(matcher, "query_index", lambda *a, **k: hits)
        result = matcher.get_uuid_by_metadata(
            {"ocpVersion": "4.15"},
            additional_fields=["jobType"],
        )
        assert result[0]["jobType"] == "periodic"

    def test_additional_fields_missing_gets_na(self, matcher, monkeypatch):
        """Missing additional fields get N/A."""
        hits = [FakeHit({
            "_source": {
                "uuid": "u1",
                "buildUrl": "http://url",
                "ocpVersion": "4.15",
            }
        })]
        monkeypatch.setattr(matcher, "query_index", lambda *a, **k: hits)
        result = matcher.get_uuid_by_metadata(
            {"ocpVersion": "4.15"},
            additional_fields=["missingField"],
        )
        assert result[0]["missingField"] == "N/A"

    def test_version_field_missing_in_source(self, matcher, monkeypatch):
        """If version field not in source, use 'No Version'."""
        hits = [FakeHit({
            "_source": {
                "uuid": "u1",
                "buildUrl": "http://url",
            }
        })]
        monkeypatch.setattr(matcher, "query_index", lambda *a, **k: hits)
        result = matcher.get_uuid_by_metadata({"platform": "aws"})
        assert result[0]["ocpVersion"] == "No Version"

    def test_dotted_version_field(self, monkeypatch):
        """Dotted version field uses dotDictFind."""
        m = _make_matcher(version_field="tags.sw_version")
        hits = [FakeHit({
            "_source": {
                "uuid": "u1",
                "buildUrl": "http://url",
                "tags": {"sw_version": "4.18.17"},
            }
        })]
        monkeypatch.setattr(m, "query_index", lambda *a, **k: hits)
        result = m.get_uuid_by_metadata({"platform": "aws"})
        assert result[0]["tags.sw_version"] == "4.18.17"

    def test_not_clause_in_metadata(self, matcher, monkeypatch):
        """The 'not' key in metadata generates must_not queries."""
        hits = [FakeHit({
            "_source": {
                "uuid": "u1",
                "buildUrl": "http://url",
                "ocpVersion": "4.15",
            }
        })]
        monkeypatch.setattr(matcher, "query_index", lambda *a, **k: hits)
        metadata = {
            "ocpVersion": "4.15",
            "not": {"jobType": "pull"},
        }
        # Should not raise — just exercises the query-building code path
        result = matcher.get_uuid_by_metadata(metadata)
        assert len(result) == 1

    def test_not_clause_with_list_values(self, matcher, monkeypatch):
        """The 'not' clause handles list values (multiple exclusions)."""
        hits = [FakeHit({
            "_source": {
                "uuid": "u1",
                "buildUrl": "http://url",
                "ocpVersion": "4.15",
            }
        })]
        monkeypatch.setattr(matcher, "query_index", lambda *a, **k: hits)
        metadata = {
            "ocpVersion": "4.15",
            "not": {"jobType": ["pull", "rehearsal"]},
        }
        result = matcher.get_uuid_by_metadata(metadata)
        assert len(result) == 1

    def test_ocp_major_version(self, matcher, monkeypatch):
        """ocpMajorVersion triggers wildcard on ocpMajorVersion field."""
        hits = [FakeHit({
            "_source": {
                "uuid": "u1",
                "buildUrl": "http://url",
                "ocpVersion": "4.15.3",
            }
        })]
        monkeypatch.setattr(matcher, "query_index", lambda *a, **k: hits)
        result = matcher.get_uuid_by_metadata({"ocpMajorVersion": "4.15"})
        assert len(result) == 1

    def test_pull_number_zero_skipped(self, matcher, monkeypatch):
        """pullNumber=0 should not be added to must clause."""
        hits = [FakeHit({
            "_source": {
                "uuid": "u1",
                "buildUrl": "http://url",
                "ocpVersion": "4.15",
            }
        })]
        monkeypatch.setattr(matcher, "query_index", lambda *a, **k: hits)
        result = matcher.get_uuid_by_metadata({
            "ocpVersion": "4.15",
            "pullNumber": 0,
        })
        assert len(result) == 1

    def test_no_version_field_in_metadata(self, matcher, monkeypatch):
        """When no version field in metadata, no wildcard filter added."""
        hits = [FakeHit({
            "_source": {
                "uuid": "u1",
                "buildUrl": "http://url",
            }
        })]
        monkeypatch.setattr(matcher, "query_index", lambda *a, **k: hits)
        result = matcher.get_uuid_by_metadata({"platform": "aws"})
        assert len(result) == 1


# ---------------------------------------------------------------------------
# parse_agg_results edge cases
# ---------------------------------------------------------------------------

class TestParseAggResults:
    def test_no_aggregations_returns_empty(self, matcher):
        """No aggregations key → empty list."""
        fake_data = Response(response={
            "hits": {"hits": []},
        }, search=Search())
        result = matcher.parse_agg_results(fake_data, "cpu", "avg")
        assert result == []

    def test_empty_buckets(self, matcher):
        """Empty uuid buckets → empty list."""
        fake_data = Response(response={
            "aggregations": {"uuid": {"buckets": []}},
            "hits": {"hits": []},
        }, search=Search())
        result = matcher.parse_agg_results(fake_data, "cpu", "avg")
        assert result == []


# ---------------------------------------------------------------------------
# convert_to_df edge cases
# ---------------------------------------------------------------------------

class TestConvertToDf:
    def test_without_columns(self, matcher):
        """When columns=None, all fields are preserved."""
        data = [
            {"uuid": "u1", "timestamp": "2024-01-01T00:00:00", "value": 10, "extra": "x"},
        ]
        result = matcher.convert_to_df(data)
        assert "extra" in result.columns
        assert "value" in result.columns

    def test_with_columns_filters(self, matcher):
        """When columns specified, only those columns remain."""
        data = [
            {"uuid": "u1", "timestamp": "2024-01-01T00:00:00", "value": 10, "extra": "x"},
        ]
        result = matcher.convert_to_df(data, columns=["uuid", "timestamp", "value"])
        assert "extra" not in result.columns

    def test_sorted_by_timestamp(self, matcher):
        """Results should be sorted ascending by timestamp."""
        data = [
            {"uuid": "u2", "timestamp": "2024-01-02T00:00:00", "value": 20},
            {"uuid": "u1", "timestamp": "2024-01-01T00:00:00", "value": 10},
        ]
        result = matcher.convert_to_df(data)
        assert result.iloc[0]["uuid"] == "u1"
        assert result.iloc[1]["uuid"] == "u2"


# ---------------------------------------------------------------------------
# save_results edge cases
# ---------------------------------------------------------------------------

class TestSaveResults:
    def test_save_with_column_filter(self, matcher, tmp_path):
        """save_results with columns filters the output."""
        df = pd.DataFrame({
            "uuid": ["u1"],
            "timestamp": ["2024-01-01"],
            "value": [10],
            "extra": ["x"],
        })
        path = tmp_path / "out.csv"
        matcher.save_results(df, csv_file_path=str(path), columns=["uuid", "value"])
        saved = pd.read_csv(str(path))
        assert "extra" not in saved.columns

    def test_save_without_columns(self, matcher, tmp_path):
        """save_results without columns saves everything."""
        df = pd.DataFrame({
            "uuid": ["u1"],
            "value": [10],
        })
        path = tmp_path / "out.csv"
        matcher.save_results(df, csv_file_path=str(path))
        saved = pd.read_csv(str(path))
        assert "uuid" in saved.columns
        assert "value" in saved.columns


# ---------------------------------------------------------------------------
# get_uuid_by_metadata — since_date / lookback_date range queries
# ---------------------------------------------------------------------------

class TestGetUuidByMetadataDateRanges:
    def test_since_date_only(self, matcher, monkeypatch):
        """since_date alone creates an upper-bound range filter."""
        from datetime import datetime
        hits = [FakeHit({
            "_source": {"uuid": "u1", "buildUrl": "http://url", "ocpVersion": "4.15"},
        })]
        captured = {}
        def spy_query_index(search, **_kwargs):
            captured["query"] = search.to_dict()
            return hits
        monkeypatch.setattr(matcher, "query_index", spy_query_index)
        matcher.get_uuid_by_metadata(
            {"ocpVersion": "4.15"},
            since_date=datetime(2024, 6, 15, 12, 0, 0),
        )
        query_str = str(captured["query"])
        assert "lt" in query_str

    def test_lookback_and_since_date(self, matcher, monkeypatch):
        """Both lookback_date and since_date create a bounded range."""
        from datetime import datetime
        hits = [FakeHit({
            "_source": {"uuid": "u1", "buildUrl": "http://url", "ocpVersion": "4.15"},
        })]
        captured = {}
        def spy_query_index(search, **_kwargs):
            captured["query"] = search.to_dict()
            return hits
        monkeypatch.setattr(matcher, "query_index", spy_query_index)
        matcher.get_uuid_by_metadata(
            {"ocpVersion": "4.15"},
            lookback_date=datetime(2024, 1, 1),
            since_date=datetime(2024, 6, 15),
        )
        query_str = str(captured["query"])
        assert "gt" in query_str
        assert "lt" in query_str

    def test_lookback_date_only(self, matcher, monkeypatch):
        """lookback_date alone creates a lower-bound range filter."""
        from datetime import datetime
        hits = [FakeHit({
            "_source": {"uuid": "u1", "buildUrl": "http://url", "ocpVersion": "4.15"},
        })]
        captured = {}
        def spy_query_index(search, **_kwargs):
            captured["query"] = search.to_dict()
            return hits
        monkeypatch.setattr(matcher, "query_index", spy_query_index)
        matcher.get_uuid_by_metadata(
            {"ocpVersion": "4.15"},
            lookback_date=datetime(2024, 1, 1),
        )
        # Check that range has 'gt' but not 'lt'
        filters = captured["query"]["query"]["bool"]["filter"]
        range_filter = [f for f in filters if "range" in f][0]
        range_val = range_filter["range"]["timestamp"]
        assert "gt" in range_val
        assert "lt" not in range_val


# ---------------------------------------------------------------------------
# get_results — edge cases
# ---------------------------------------------------------------------------

class TestGetResults:
    def test_single_uuid_removal(self, matcher, monkeypatch):
        """When uuid is in uuids list (len>1), it gets removed."""
        captured = {}
        def spy_query_index(search, **_kwargs):
            captured["query"] = search.to_dict()
            return []
        monkeypatch.setattr(matcher, "query_index", spy_query_index)
        uuids = ["u1", "u2", "u3"]
        matcher.get_results("u2", uuids, {"metricName": "jobSummary"})
        # u2 should have been removed from the list
        assert "u2" not in uuids
        # Query should use the modified list
        terms = captured["query"]["query"]["bool"]["must"][0]["terms"]["uuid.keyword"]
        assert "u2" not in terms

    def test_single_uuid_not_removed_when_alone(self, matcher, monkeypatch):
        """When uuids has only one entry, uuid is NOT removed even if it matches."""
        captured = {}
        def spy_query_index(search, **_kwargs):
            captured["query"] = search.to_dict()
            return []
        monkeypatch.setattr(matcher, "query_index", spy_query_index)
        uuids = ["u1"]
        matcher.get_results("u1", uuids, {"metricName": "jobSummary"})
        assert "u1" in uuids

    def test_empty_metrics(self, matcher, monkeypatch):
        """Metrics with only name/metric_of_interest produce no metric match queries."""
        captured = {}
        def spy_query_index(search, **_kwargs):
            captured["query"] = search.to_dict()
            return []
        monkeypatch.setattr(matcher, "query_index", spy_query_index)
        matcher.get_results("u1", ["u1", "u2"], {
            "name": "test_metric",
            "metric_of_interest": "value",
        })
        # The metric bool query should have no match clauses for name/metric_of_interest
        query_str = str(captured["query"])
        assert "test_metric" not in query_str
        assert "'value'" not in query_str or "metric_of_interest" not in query_str

    def test_not_queries_in_metrics(self, matcher, monkeypatch):
        """'not' key in metrics generates must_not-style ~Q queries."""
        captured = {}
        def spy_query_index(search, **_kwargs):
            captured["query"] = search.to_dict()
            return []
        monkeypatch.setattr(matcher, "query_index", spy_query_index)
        matcher.get_results("u1", ["u1", "u2"], {
            "metricName": "jobSummary",
            "not": {"jobConfig.name": "garbage-collection"},
        })
        # The not query generates a must_not inside the metric bool
        query_str = str(captured["query"])
        assert "garbage-collection" in query_str

    def test_exists_fields(self, matcher, monkeypatch):
        """exists_fields generates exists queries."""
        captured = {}
        def spy_query_index(search, **_kwargs):
            captured["query"] = search.to_dict()
            return []
        monkeypatch.setattr(matcher, "query_index", spy_query_index)
        matcher.get_results("u1", ["u1", "u2"], {"metricName": "cpu"}, exists_fields=["field_a"])
        query_str = str(captured["query"])
        assert "field_a" in query_str
        assert "exists" in query_str

    def test_returns_source_data(self, matcher, monkeypatch):
        """get_results returns _source dicts from hits."""
        hits = [
            FakeHit({"_source": {"uuid": "u1", "value": 42}}),
            FakeHit({"_source": {"uuid": "u2", "value": 99}}),
        ]
        monkeypatch.setattr(matcher, "query_index", lambda *a, **k: hits)
        result = matcher.get_results("u1", ["u1", "u2"], {"metricName": "cpu"})
        assert len(result) == 2
        assert result[0]["value"] == 42


# ---------------------------------------------------------------------------
# filter_runs — different iterations filtering
# ---------------------------------------------------------------------------

class TestFilterRuns:
    def test_filters_different_iterations(self, matcher):
        """UUIDs with different jobIterations are filtered out."""
        pdata = [{"uuid": "pick", "jobConfig": {"jobIterations": 100}}]
        data = [
            {"uuid": "u1", "jobConfig": {"jobIterations": 100}},
            {"uuid": "u2", "jobConfig": {"jobIterations": 200}},
            {"uuid": "u3", "jobConfig": {"jobIterations": 100}},
        ]
        result = matcher.filter_runs(pdata, data)
        assert "u1" in result
        assert "u3" in result
        assert "u2" not in result

    def test_all_same_iterations(self, matcher):
        """All UUIDs kept when iterations match."""
        pdata = [{"uuid": "pick", "jobConfig": {"jobIterations": 50}}]
        data = [
            {"uuid": "u1", "jobConfig": {"jobIterations": 50}},
            {"uuid": "u2", "jobConfig": {"jobIterations": 50}},
        ]
        result = matcher.filter_runs(pdata, data)
        assert len(result) == 2

    def test_none_matching(self, matcher):
        """No UUIDs kept when none match."""
        pdata = [{"uuid": "pick", "jobConfig": {"jobIterations": 100}}]
        data = [
            {"uuid": "u1", "jobConfig": {"jobIterations": 200}},
        ]
        result = matcher.filter_runs(pdata, data)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# match_kube_burner — custom timestamp field
# ---------------------------------------------------------------------------

class TestMatchKubeBurner:
    def test_custom_timestamp_field(self, matcher, monkeypatch):
        """Custom timestamp_field is used in the sort."""
        captured = {}
        def spy_query_index(search, **_kwargs):
            captured["query"] = search.to_dict()
            return []
        monkeypatch.setattr(matcher, "query_index", spy_query_index)
        matcher.match_kube_burner(["u1"], timestamp_field="custom_ts")
        sort_field = list(captured["query"]["sort"][0].keys())[0]
        assert sort_field == "custom_ts"

    def test_returns_source_dicts(self, matcher, monkeypatch):
        """Returns _source dicts from all hits."""
        hits = [
            FakeHit({"_source": {"uuid": "u1", "metricName": "jobSummary", "value": 10}}),
        ]
        monkeypatch.setattr(matcher, "query_index", lambda *a, **k: hits)
        result = matcher.match_kube_burner(["u1"])
        assert len(result) == 1
        assert result[0]["value"] == 10


# ---------------------------------------------------------------------------
# get_agg_metric_query — different agg types
# ---------------------------------------------------------------------------

class TestGetAggMetricQuery:
    def _make_agg_response(self, agg_value, agg_type, value=42.0):
        """Build a fake aggregation response."""
        if agg_type == "percentiles":
            agg_data = {agg_value: {"values": {"95.0": value}}}
        elif agg_type == "count":
            agg_data = {agg_value: {"value": value}}
        else:
            agg_data = {agg_value: {"value": value}}
        return Response(response={
            "hits": {"hits": [], "total": {"value": 0, "relation": "eq"}},
            "aggregations": {
                "uuid": {
                    "buckets": [
                        {
                            "key": "test-uuid",
                            "doc_count": 5,
                            "time": {"value": 1704067200000, "value_as_string": "2024-01-01T00:00:00Z"},
                            **agg_data,
                        }
                    ]
                }
            },
        }, search=Search())

    def test_avg_agg_type(self, matcher, monkeypatch):
        """Standard avg aggregation works."""
        resp = self._make_agg_response("cpu_pct", "avg", 85.5)
        monkeypatch.setattr(matcher, "query_index", lambda *a, **k: resp)
        # Mock execute on Search to return our response
        monkeypatch.setattr(Search, "execute", lambda self: resp)
        metrics = {
            "name": "cpu",
            "metric_of_interest": "cpuUsage",
            "agg": {"agg_type": "avg", "value": "cpu_pct"},
        }
        result = matcher.get_agg_metric_query(["test-uuid"], metrics)
        assert len(result) == 1
        assert result[0]["cpu_pct_avg"] == 85.5

    def test_sum_agg_type(self, matcher, monkeypatch):
        """Sum aggregation type."""
        resp = self._make_agg_response("total", "sum", 1000.0)
        monkeypatch.setattr(Search, "execute", lambda self: resp)
        metrics = {
            "name": "throughput",
            "metric_of_interest": "bytes",
            "agg": {"agg_type": "sum", "value": "total"},
        }
        result = matcher.get_agg_metric_query(["test-uuid"], metrics)
        assert result[0]["total_sum"] == 1000.0

    def test_max_agg_type(self, matcher, monkeypatch):
        """Max aggregation type."""
        resp = self._make_agg_response("peak", "max", 99.9)
        monkeypatch.setattr(Search, "execute", lambda self: resp)
        metrics = {
            "name": "latency",
            "metric_of_interest": "latMs",
            "agg": {"agg_type": "max", "value": "peak"},
        }
        result = matcher.get_agg_metric_query(["test-uuid"], metrics)
        assert result[0]["peak_max"] == 99.9

    def test_percentiles_agg_type(self, matcher, monkeypatch):
        """Percentiles aggregation extracts target percentile."""
        resp = self._make_agg_response("lat", "percentiles", 12.5)
        monkeypatch.setattr(Search, "execute", lambda self: resp)
        metrics = {
            "name": "latency",
            "metric_of_interest": "latMs",
            "agg": {"agg_type": "percentiles", "value": "lat",
                    "percents": [50, 95, 99],
                    "target_percentile": "95.0"},
        }
        result = matcher.get_agg_metric_query(["test-uuid"], metrics)
        assert result[0]["lat_percentiles"] == 12.5

    def test_count_agg_type(self, matcher, monkeypatch):
        """Count aggregation uses value_count."""
        resp = self._make_agg_response("num", "count", 42)
        monkeypatch.setattr(Search, "execute", lambda self: resp)
        metrics = {
            "name": "events",
            "metric_of_interest": "eventId",
            "agg": {"agg_type": "count", "value": "num"},
        }
        result = matcher.get_agg_metric_query(["test-uuid"], metrics)
        assert result[0]["num_count"] == 42

    def test_custom_timestamp_field(self, matcher, monkeypatch):
        """Custom timestamp field used in sort and aggregation."""
        resp = self._make_agg_response("cpu", "avg", 50.0)
        captured = {}
        def spy_execute(self):
            captured["query"] = self.to_dict()
            return resp
        monkeypatch.setattr(Search, "execute", spy_execute)
        metrics = {
            "name": "cpu",
            "metric_of_interest": "cpuUsage",
            "agg": {"agg_type": "avg", "value": "cpu"},
        }
        matcher.get_agg_metric_query(["test-uuid"], metrics, timestamp_field="custom_ts")
        sort_field = list(captured["query"]["sort"][0].keys())[0]
        assert sort_field == "custom_ts"


# ---------------------------------------------------------------------------
# dotDictFind
# ---------------------------------------------------------------------------

class TestDotDictFind:
    def test_single_level(self, matcher):
        assert matcher.dotDictFind({"key": "val"}, "key") == "val"

    def test_two_levels(self, matcher):
        assert matcher.dotDictFind({"a": {"b": "deep"}}, "a.b") == "deep"

    def test_three_levels(self, matcher):
        assert matcher.dotDictFind({"a": {"b": {"c": 42}}}, "a.b.c") == 42

    def test_returns_first_non_dict(self, matcher):
        """Stops traversal at first non-dict value."""
        data = {"a": {"b": "stop"}}
        assert matcher.dotDictFind(data, "a.b") == "stop"


# ---------------------------------------------------------------------------
# query_index — return_all=False returns response directly
# ---------------------------------------------------------------------------

class TestQueryIndex:
    def test_return_all_false_returns_response_object(self, matcher):
        """When return_all=False, query_index should return the raw response
        from the first execute() call, not a list of hits."""
        fake_response = type("R", (), {
            "hits": type("H", (), {"hits": [{"_source": {"uuid": "u1"}}]})()
        })()

        class FakeSearch:
            def to_dict(self):
                return {}
            def extra(self, **_kw):
                return self
            def execute(self):
                return fake_response

        result = matcher.query_index(FakeSearch(), return_all=False)
        # Must be the exact response object, not a list
        assert result is fake_response
        assert not isinstance(result, list)

    def test_return_all_true_returns_list(self, matcher):
        """When return_all=True, query_index should return a list of hits."""
        class FakeMeta:
            sort = ["sort_val"]
        class FakeHitObj:
            meta = FakeMeta()
            def to_dict(self):
                return {"_source": {"uuid": "u1"}}
        class FakeHits:
            hits = [FakeHitObj()]
            def __getitem__(self, idx):
                return self.hits[idx]

        call_count = {"n": 0}
        class FakeSearch:
            def to_dict(self):
                return {}
            def extra(self, **_kw):
                return self
            def execute(self_inner):  # noqa: N805
                call_count["n"] += 1
                if call_count["n"] == 1:
                    return type("R", (), {"hits": FakeHits()})()
                # Second call returns empty hits to break the loop
                return type("R", (), {"hits": type("H", (), {"hits": []})()})()

        result = matcher.query_index(FakeSearch(), return_all=True)
        assert isinstance(result, list)
        assert len(result) == 1
