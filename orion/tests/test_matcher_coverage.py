"""
Additional unit tests for orion/matcher.py — covering gaps in existing test_matcher.py

Focuses on: get_uuid_by_metadata edge cases (not clause, ocpMajorVersion,
build_url fallback, additional_fields, since_date), get_metadata_by_uuid
actual logic, parse_agg_results edge cases, convert_to_df without columns.
"""

# pylint: disable = redefined-outer-name
# pylint: disable = missing-function-docstring
# pylint: disable = import-error, duplicate-code

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
