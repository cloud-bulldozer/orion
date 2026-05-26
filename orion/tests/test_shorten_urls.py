"""
Unit tests for Utils.shorten_urls_batch
"""

# pylint: disable = redefined-outer-name
# pylint: disable = missing-function-docstring
# pylint: disable = missing-class-docstring

import logging
from unittest.mock import patch, MagicMock

import requests
import pytest

from orion.logger import SingletonLogger
from orion.utils import Utils


@pytest.fixture(autouse=True)
def _init_logger():
    SingletonLogger(debug=logging.DEBUG, name="Orion")


@pytest.fixture
def utils():
    return Utils()


class TestShortenUrlsBatch:
    def test_shortens_all_urls(self, utils):
        urls_by_uuid = {
            "uuid-1": "https://example.com/build/1",
            "uuid-2": "https://example.com/build/2",
        }
        with patch.object(requests.Session, "get") as mock_get:
            mock_get.side_effect = lambda *a, **kw: MagicMock(
                text=f"https://tinyurl.com/{kw['params']['url'][-1]}",
                raise_for_status=MagicMock(),
            )
            result = utils.shorten_urls_batch(urls_by_uuid)

        assert result["uuid-1"] == "https://tinyurl.com/1"
        assert result["uuid-2"] == "https://tinyurl.com/2"

    def test_deduplicates_urls(self, utils):
        same_url = "https://example.com/build/1"
        urls_by_uuid = {"uuid-1": same_url, "uuid-2": same_url}

        with patch.object(requests.Session, "get") as mock_get:
            mock_get.return_value = MagicMock(
                text="https://tinyurl.com/short",
                raise_for_status=MagicMock(),
            )
            result = utils.shorten_urls_batch(urls_by_uuid)

        assert mock_get.call_count == 1
        assert result["uuid-1"] == "https://tinyurl.com/short"
        assert result["uuid-2"] == "https://tinyurl.com/short"

    def test_timeout_falls_back_to_original(self, utils):
        urls_by_uuid = {"uuid-1": "https://example.com/build/1"}

        with patch.object(requests.Session, "get", side_effect=requests.Timeout("timed out")):
            result = utils.shorten_urls_batch(urls_by_uuid)

        assert result["uuid-1"] == "https://example.com/build/1"

    def test_http_error_falls_back_to_original(self, utils):
        urls_by_uuid = {"uuid-1": "https://example.com/build/1"}

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
        with patch.object(requests.Session, "get", return_value=mock_resp):
            result = utils.shorten_urls_batch(urls_by_uuid)

        assert result["uuid-1"] == "https://example.com/build/1"

    def test_connection_error_falls_back_to_original(self, utils):
        urls_by_uuid = {"uuid-1": "https://example.com/build/1"}

        with patch.object(requests.Session, "get", side_effect=requests.ConnectionError("refused")):
            result = utils.shorten_urls_batch(urls_by_uuid)

        assert result["uuid-1"] == "https://example.com/build/1"

    def test_partial_failure_shortens_rest(self, utils):
        urls_by_uuid = {
            "uuid-1": "https://example.com/build/1",
            "uuid-2": "https://example.com/build/2",
        }

        def side_effect(*_args, **kwargs):
            url = kwargs["params"]["url"]
            if url.endswith("/1"):
                raise requests.Timeout("timed out")
            return MagicMock(
                text="https://tinyurl.com/short2",
                raise_for_status=MagicMock(),
            )

        with patch.object(requests.Session, "get", side_effect=side_effect):
            result = utils.shorten_urls_batch(urls_by_uuid)

        assert result["uuid-1"] == "https://example.com/build/1"
        assert result["uuid-2"] == "https://tinyurl.com/short2"

    def test_empty_response_falls_back_to_original(self, utils):
        urls_by_uuid = {"uuid-1": "https://example.com/build/1"}

        with patch.object(requests.Session, "get") as mock_get:
            mock_get.return_value = MagicMock(
                text="   ",
                raise_for_status=MagicMock(),
            )
            result = utils.shorten_urls_batch(urls_by_uuid)

        assert result["uuid-1"] == "https://example.com/build/1"

    def test_empty_input(self, utils):
        result = utils.shorten_urls_batch({})
        assert result == {}
