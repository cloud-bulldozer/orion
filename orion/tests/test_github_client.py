"""
Unit tests for orion/github_client.py
"""

# pylint: disable = redefined-outer-name
# pylint: disable = missing-function-docstring
# pylint: disable = import-error

import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests

from orion.github_client import GitHubClient
from orion.logger import SingletonLogger


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _init_logger():
    SingletonLogger(debug=logging.DEBUG, name="Orion")


@pytest.fixture
def client():
    """Client with no auth token and one repo."""
    with patch.dict("os.environ", {}, clear=True):
        return GitHubClient(["org/repo"])


@pytest.fixture
def client_multi():
    """Client with two repos."""
    with patch.dict("os.environ", {}, clear=True):
        return GitHubClient(["org/repo1", "org/repo2"])


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------

class TestConstructor:
    def test_strips_whitespace_from_repos(self):
        with patch.dict("os.environ", {}, clear=True):
            c = GitHubClient(["  org/repo  ", " ", ""])
        assert c.repositories == ["org/repo"]

    def test_picks_up_github_token(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": "tok123"}, clear=True):
            c = GitHubClient(["org/repo"])
        assert c.session.headers["Authorization"] == "Bearer tok123"

    def test_picks_up_gh_token_fallback(self):
        with patch.dict("os.environ", {"GH_TOKEN": "ghfallback"}, clear=True):
            c = GitHubClient(["org/repo"])
        assert c.session.headers["Authorization"] == "Bearer ghfallback"

    def test_explicit_token_overrides_env(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": "envtok"}, clear=True):
            c = GitHubClient(["org/repo"], token="explicit")
        assert c.session.headers["Authorization"] == "Bearer explicit"

    def test_no_token(self):
        with patch.dict("os.environ", {}, clear=True):
            c = GitHubClient(["org/repo"])
        assert "Authorization" not in c.session.headers


# ---------------------------------------------------------------------------
# _coerce_timestamp
# ---------------------------------------------------------------------------

class TestCoerceTimestamp:
    def test_none(self, client):
        assert client._coerce_timestamp(None) is None

    def test_empty_string(self, client):
        assert client._coerce_timestamp("") is None

    def test_datetime_passthrough(self, client):
        dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        result = client._coerce_timestamp(dt)
        assert result == dt

    def test_naive_datetime_gets_utc(self, client):
        dt = datetime(2024, 1, 1)
        result = client._coerce_timestamp(dt)
        assert result.tzinfo is not None

    def test_int_epoch(self, client):
        result = client._coerce_timestamp(1704067200)
        assert result == datetime(2024, 1, 1, tzinfo=timezone.utc)

    def test_float_epoch(self, client):
        result = client._coerce_timestamp(1704067200.5)
        assert result.year == 2024

    def test_string_digits(self, client):
        result = client._coerce_timestamp("1704067200")
        assert result == datetime(2024, 1, 1, tzinfo=timezone.utc)

    def test_string_float(self, client):
        result = client._coerce_timestamp("1704067200.5")
        assert result.year == 2024

    def test_iso_string(self, client):
        result = client._coerce_timestamp("2024-06-15T12:00:00Z")
        assert result.year == 2024
        assert result.month == 6

    def test_invalid_string(self, client):
        assert client._coerce_timestamp("not-a-date") is None

    def test_whitespace_string(self, client):
        assert client._coerce_timestamp("   ") is None

    def test_overflow_int(self, client):
        assert client._coerce_timestamp(99999999999999) is None

    def test_unsupported_type(self, client):
        assert client._coerce_timestamp([1, 2, 3]) is None


# ---------------------------------------------------------------------------
# _parse_iso_datetime
# ---------------------------------------------------------------------------

class TestParseIsoDatetime:
    def test_valid_z_suffix(self):
        result = GitHubClient._parse_iso_datetime("2024-01-15T10:30:00Z")
        assert result.year == 2024
        assert result.month == 1
        assert result.tzinfo == timezone.utc

    def test_valid_offset(self):
        result = GitHubClient._parse_iso_datetime("2024-01-15T10:30:00+00:00")
        assert result is not None

    def test_none(self):
        assert GitHubClient._parse_iso_datetime(None) is None

    def test_empty(self):
        assert GitHubClient._parse_iso_datetime("") is None

    def test_invalid(self):
        assert GitHubClient._parse_iso_datetime("not-a-date") is None


# ---------------------------------------------------------------------------
# _normalize_timestamp
# ---------------------------------------------------------------------------

class TestNormalizeTimestamp:
    def test_returns_iso_with_z(self, client):
        result = client._normalize_timestamp(1704067200)
        assert result == "2024-01-01T00:00:00Z"

    def test_none_returns_none(self, client):
        assert client._normalize_timestamp(None) is None


# ---------------------------------------------------------------------------
# _prepare_interval
# ---------------------------------------------------------------------------

class TestPrepareInterval:
    def test_valid_interval(self, client):
        result = client._prepare_interval(1704067200, 1704153600, "s", "e")
        assert result["error"] is None
        assert result["start_dt"] is not None
        assert result["end_dt"] is not None

    def test_end_none(self, client):
        result = client._prepare_interval(1704067200, None, "s", None)
        assert "current timestamp" in result["error"]

    def test_start_none(self, client):
        result = client._prepare_interval(None, 1704153600, None, "e")
        assert "previous timestamp" in result["error"]

    def test_start_after_end(self, client):
        result = client._prepare_interval(1704153600, 1704067200, "s", "e")
        assert "not earlier" in result["error"]

    def test_start_equals_end(self, client):
        result = client._prepare_interval(1704067200, 1704067200, "s", "e")
        assert "not earlier" in result["error"]


# ---------------------------------------------------------------------------
# _make_cache_key / _build_collection_entry (static helpers)
# ---------------------------------------------------------------------------

class TestStaticHelpers:
    def test_make_cache_key(self):
        key = GitHubClient._make_cache_key("org/repo", "2024-01-01", "2024-01-02")
        assert key == ("org/repo", "2024-01-01", "2024-01-02")

    def test_make_cache_key_none_values(self):
        key = GitHubClient._make_cache_key("org/repo", None, None)
        assert key == ("org/repo", "__none__", "__none__")

    def test_build_collection_entry(self):
        entry = GitHubClient._build_collection_entry(
            [{"a": 1}], "start", "end"
        )
        assert entry["count"] == 1
        assert entry["items"] == [{"a": 1}]
        assert "reason" not in entry

    def test_build_collection_entry_with_reason(self):
        entry = GitHubClient._build_collection_entry(
            [], "s", "e", reason="no data"
        )
        assert entry["count"] == 0
        assert entry["reason"] == "no data"


# ---------------------------------------------------------------------------
# _request_json
# ---------------------------------------------------------------------------

class TestRequestJson:
    def test_success(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.json.return_value = [{"id": 1}]
        client.session.get = MagicMock(return_value=mock_resp)
        data, error = client._request_json("https://api.github.com/test")
        assert data == [{"id": 1}]
        assert error is None

    def test_404(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        client.session.get = MagicMock(return_value=mock_resp)
        data, error = client._request_json("https://api.github.com/test")
        assert data is None
        assert "404" in error

    def test_403_rate_limit(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.headers = {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "123456"}
        client.session.get = MagicMock(return_value=mock_resp)
        data, error = client._request_json("https://api.github.com/test")
        assert data is None
        assert "rate limited" in error

    def test_500(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.ok = False
        client.session.get = MagicMock(return_value=mock_resp)
        data, error = client._request_json("https://api.github.com/test")
        assert data is None
        assert "500" in error

    def test_request_exception(self, client):
        client.session.get = MagicMock(
            side_effect=requests.ConnectionError("timeout")
        )
        data, error = client._request_json("https://api.github.com/test")
        assert data is None
        assert "request failed" in error

    def test_invalid_json(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.json.side_effect = ValueError("bad json")
        client.session.get = MagicMock(return_value=mock_resp)
        data, error = client._request_json("https://api.github.com/test")
        assert data is None
        assert "invalid JSON" in error


# ---------------------------------------------------------------------------
# _build_url
# ---------------------------------------------------------------------------

class TestBuildUrl:
    def test_releases_url(self, client):
        url = client._build_url("org/repo", "releases", 1, None, None)
        assert "repos/org/repo/releases" in url
        assert "page=1" in url

    def test_commits_url_with_timestamps(self, client):
        url = client._build_url("org/repo", "commits", 2, "2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z")
        assert "repos/org/repo/commits" in url
        assert "page=2" in url
        assert "since=" in url
        assert "until=" in url

    def test_commits_url_no_timestamps(self, client):
        url = client._build_url("org/repo", "commits", 1, None, None)
        assert "since=" not in url
        assert "until=" not in url


# ---------------------------------------------------------------------------
# _process_releases / _process_commits
# ---------------------------------------------------------------------------

class TestProcessItems:
    def test_process_releases_in_range(self, client):
        start_dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_dt = datetime(2024, 1, 31, tzinfo=timezone.utc)
        payload = [
            {
                "published_at": "2024-01-15T00:00:00Z",
                "name": "v1.0",
                "html_url": "https://github.com/org/repo/releases/1",
                "created_at": "2024-01-15T00:00:00Z",
                "target_commitish": "main",
            }
        ]
        collected = []
        stop = client._process_releases(payload, start_dt, end_dt, collected)
        assert not stop
        assert len(collected) == 1
        assert collected[0]["name"] == "v1.0"

    def test_process_releases_before_start_stops(self, client):
        start_dt = datetime(2024, 1, 10, tzinfo=timezone.utc)
        end_dt = datetime(2024, 1, 31, tzinfo=timezone.utc)
        payload = [
            {"published_at": "2024-01-05T00:00:00Z", "name": "old"},
        ]
        collected = []
        stop = client._process_releases(payload, start_dt, end_dt, collected)
        assert stop
        assert len(collected) == 0

    def test_process_releases_after_end_skipped(self, client):
        start_dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_dt = datetime(2024, 1, 15, tzinfo=timezone.utc)
        payload = [
            {"published_at": "2024-02-01T00:00:00Z", "name": "future"},
        ]
        collected = []
        client._process_releases(payload, start_dt, end_dt, collected)
        assert len(collected) == 0

    def test_process_commits_in_range(self, client):
        start_dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_dt = datetime(2024, 1, 31, tzinfo=timezone.utc)
        payload = [
            {
                "html_url": "https://github.com/org/repo/commit/abc",
                "commit": {
                    "author": {
                        "name": "dev",
                        "email": "dev@example.com",
                        "date": "2024-01-15T12:00:00Z",
                    },
                    "message": "fix bug",
                },
            }
        ]
        collected = []
        client._process_commits(payload, start_dt, end_dt, collected)
        assert len(collected) == 1
        assert collected[0]["message"] == "fix bug"

    def test_process_commits_outside_range_skipped(self, client):
        start_dt = datetime(2024, 1, 10, tzinfo=timezone.utc)
        end_dt = datetime(2024, 1, 20, tzinfo=timezone.utc)
        payload = [
            {
                "html_url": "url",
                "commit": {
                    "author": {"name": "dev", "email": "e", "date": "2024-01-05T00:00:00Z"},
                    "message": "too early",
                },
            },
            {
                "html_url": "url2",
                "commit": {
                    "author": {"name": "dev", "email": "e", "date": "2024-01-25T00:00:00Z"},
                    "message": "too late",
                },
            },
        ]
        collected = []
        client._process_commits(payload, start_dt, end_dt, collected)
        assert len(collected) == 0

    def test_process_items_dispatches_releases(self, client):
        start_dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_dt = datetime(2024, 1, 31, tzinfo=timezone.utc)
        payload = [{"published_at": "2024-01-15T00:00:00Z", "name": "v1"}]
        collected = []
        client.process_items(payload, "releases", start_dt, end_dt, collected)
        assert len(collected) == 1

    def test_process_items_dispatches_commits(self, client):
        start_dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_dt = datetime(2024, 1, 31, tzinfo=timezone.utc)
        payload = [
            {"html_url": "u", "commit": {"author": {"name": "d", "email": "e", "date": "2024-01-15T00:00:00Z"}, "message": "m"}}
        ]
        collected = []
        client.process_items(payload, "commits", start_dt, end_dt, collected)
        assert len(collected) == 1


# ---------------------------------------------------------------------------
# _get_items_between (releases/commits with mocked HTTP)
# ---------------------------------------------------------------------------

class TestGetItemsBetween:
    def test_caches_results(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.json.return_value = []
        client.session.get = MagicMock(return_value=mock_resp)

        result1 = client._get_releases_between("org/repo", 1704067200, 1704153600)
        result2 = client._get_releases_between("org/repo", 1704067200, 1704153600)
        assert result1 is result2
        # Only one HTTP call because second is cached
        assert client.session.get.call_count == 1

    def test_invalid_interval_returns_error(self, client):
        result = client._get_releases_between("org/repo", None, 1704153600)
        assert result["reason"] is not None
        assert result["count"] == 0

    def test_request_error_returns_reason(self, client):
        client.session.get = MagicMock(
            side_effect=requests.ConnectionError("fail")
        )
        result = client._get_commits_between("org/repo", 1704067200, 1704153600)
        assert "request failed" in result["reason"]


# ---------------------------------------------------------------------------
# get_change_context
# ---------------------------------------------------------------------------

class TestGetChangeContext:
    def test_no_repos_returns_none(self):
        with patch.dict("os.environ", {}, clear=True):
            c = GitHubClient([])
        result = c.get_change_context(1704067200, 1704153600)
        assert result is None

    def test_invalid_repo_format(self, client):
        with patch.dict("os.environ", {}, clear=True):
            c = GitHubClient(["no-slash-repo"])
        result = c.get_change_context(1704067200, 1704153600)
        assert result is not None
        repo_data = result["repositories"]["no-slash-repo"]
        assert "invalid repository" in repo_data["releases"]["reason"]

    def test_valid_context_structure(self, client):
        # Mock HTTP to return empty lists
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.json.return_value = []
        client.session.get = MagicMock(return_value=mock_resp)

        result = client.get_change_context(
            1704067200, 1704153600,
            previous_version="4.14.0", current_version="4.14.1"
        )
        assert result is not None
        assert "previous_timestamp" in result
        assert "current_timestamp" in result
        assert "repositories" in result
        assert "org/repo" in result["repositories"]
        repo = result["repositories"]["org/repo"]
        assert "releases" in repo
        assert "commits" in repo

    def test_context_cached(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.json.return_value = []
        client.session.get = MagicMock(return_value=mock_resp)

        result1 = client.get_change_context(1704067200, 1704153600)
        result2 = client.get_change_context(1704067200, 1704153600)
        assert result1 is result2


# ---------------------------------------------------------------------------
# get_pr_creation_date
# ---------------------------------------------------------------------------

class TestGetPrCreationDate:
    def test_success(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "created_at": "2024-06-15T10:00:00Z",
            "number": 42,
        }
        client.session.get = MagicMock(return_value=mock_resp)
        result = client.get_pr_creation_date("org", "repo", 42)
        assert result is not None
        assert result.year == 2024
        assert result.month == 6

    def test_not_found(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        client.session.get = MagicMock(return_value=mock_resp)
        result = client.get_pr_creation_date("org", "repo", 999)
        assert result is None

    def test_missing_created_at(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.json.return_value = {"number": 42}
        client.session.get = MagicMock(return_value=mock_resp)
        result = client.get_pr_creation_date("org", "repo", 42)
        assert result is None
