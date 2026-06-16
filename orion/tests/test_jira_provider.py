"""
Tests for JiraAckProvider status filter and removed auto-detect functions.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestJiraStatusFilter:
    """Tests for --jira-status-filter JQL construction."""

    def _make_provider(self, status=None, project="PERFSCALE", component="CPT_ISSUES"):
        """Create a JiraAckProvider with mocked JIRA client."""
        with patch("orion.ack_providers.jira_provider.JIRA") as mock_jira_cls:
            mock_jira_cls.return_value = MagicMock()
            from orion.ack_providers.jira_provider import JiraAckProvider
            provider = JiraAckProvider(
                jira_url="https://test.atlassian.net",
                project=project,
                component=component,
                email="test@test.com",
                token="fake-token",
                status=status,
            )
        return provider

    def test_no_status_filter_jql(self):
        provider = self._make_provider(status=None)
        provider.jira.search_issues = MagicMock(return_value=[])

        provider.get_acks(version="4.18")

        jql = provider.jira.search_issues.call_args[0][0]
        assert "statusCategory" not in jql
        assert "project = PERFSCALE" in jql
        assert "labels = '4.18'" in jql

    def test_status_filter_done_in_jql(self):
        provider = self._make_provider(status="Done")
        provider.jira.search_issues = MagicMock(return_value=[])

        provider.get_acks(version="4.18")

        jql = provider.jira.search_issues.call_args[0][0]
        assert 'statusCategory = "Done"' in jql
        assert "project = PERFSCALE" in jql
        assert "labels = '4.18'" in jql

    def test_status_filter_with_version_and_test_type(self):
        provider = self._make_provider(status="Done")
        provider.jira.search_issues = MagicMock(return_value=[])

        provider.get_acks(version="4.18", test_type="cluster-density")

        jql = provider.jira.search_issues.call_args[0][0]
        assert 'statusCategory = "Done"' in jql
        assert "labels = '4.18'" in jql
        assert "labels = 'cluster-density'" in jql

    def test_empty_status_string_not_added(self):
        provider = self._make_provider(status="")
        provider.jira.search_issues = MagicMock(return_value=[])

        provider.get_acks(version="4.18")

        jql = provider.jira.search_issues.call_args[0][0]
        assert "statusCategory" not in jql

    def test_no_component_jql(self):
        provider = self._make_provider(status="Done", component="")
        provider.jira.search_issues = MagicMock(return_value=[])

        provider.get_acks()

        jql = provider.jira.search_issues.call_args[0][0]
        assert "component" not in jql
        assert 'statusCategory = "Done"' in jql

    def test_status_filter_stored_on_init(self):
        provider = self._make_provider(status="Done")
        assert provider.status_filter == "Done"

    def test_none_status_filter_stored_on_init(self):
        provider = self._make_provider(status=None)
        assert provider.status_filter is None


class TestRemovedAutoDetectFunctions:
    """Verify that removed functions are no longer importable."""

    def test_fetch_remote_ack_file_removed(self):
        with pytest.raises(ImportError):
            from orion.config import fetch_remote_ack_file  # noqa: F401

    def test_auto_detect_ack_file_with_vars_removed(self):
        with pytest.raises(ImportError):
            from orion.config import auto_detect_ack_file_with_vars  # noqa: F401

    def test_remote_ack_url_removed(self):
        from orion import config
        assert not hasattr(config, "REMOTE_ACK_URL")
