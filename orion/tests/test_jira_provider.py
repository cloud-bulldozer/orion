# pylint: disable=missing-function-docstring,import-outside-toplevel
"""
Tests for JiraAckProvider: status filter, issue creation, and removed auto-detect functions.
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

    def test_comma_separated_status_filter_in_jql(self):
        provider = self._make_provider(status="Done,In Progress")
        provider.jira.search_issues = MagicMock(return_value=[])

        provider.get_acks(version="4.22")

        jql = provider.jira.search_issues.call_args[0][0]
        assert 'statusCategory IN ("Done", "In Progress")' in jql

    def test_single_status_uses_equals(self):
        provider = self._make_provider(status="Done")
        provider.jira.search_issues = MagicMock(return_value=[])

        provider.get_acks(version="4.22")

        jql = provider.jira.search_issues.call_args[0][0]
        assert 'statusCategory = "Done"' in jql
        assert "IN" not in jql


class TestCreateAck:
    """Tests for create_ack() issue creation."""

    @pytest.fixture(autouse=True)
    def _no_sleep(self):
        with patch("time.sleep"):
            yield

    def _make_provider(self, component="CPT_ISSUES"):
        """Create a JiraAckProvider with mocked JIRA client."""
        with patch("orion.ack_providers.jira_provider.JIRA") as mock_jira_cls:
            mock_jira_cls.return_value = MagicMock()
            from orion.ack_providers.jira_provider import JiraAckProvider
            provider = JiraAckProvider(
                jira_url="https://test.atlassian.net",
                project="PERFSCALE",
                component=component,
                email="test@test.com",
                token="fake-token",
            )
        # No existing issue found (so creation proceeds)
        provider._find_existing_issue = MagicMock(return_value=None)  # pylint: disable=protected-access
        # Mock create_issue to return a fake issue
        mock_issue = MagicMock()
        mock_issue.key = "PERFSCALE-999"
        provider.jira.create_issue = MagicMock(return_value=mock_issue)
        # Skip verification delay
        provider._find_existing_issue.side_effect = [None, mock_issue]  # pylint: disable=protected-access
        return provider

    def _get_created_fields(self, provider):
        """Extract the fields dict passed to jira.create_issue()."""
        return provider.jira.create_issue.call_args[1]["fields"]

    def test_labels_include_version_test_metric(self):
        provider = self._make_provider()
        provider.create_ack(
            uuid="abc-123",
            metric="etcdCPU_avg",
            reason="regression detected",
            version="4.22",
            test="crd-scale",
        )
        fields = self._get_created_fields(provider)
        assert fields["labels"] == ["4.22", "crd-scale", "etcdCPU_avg"]

    def test_labels_without_version(self):
        provider = self._make_provider()
        provider.create_ack(
            uuid="abc-123",
            metric="etcdCPU_avg",
            reason="regression detected",
            test="crd-scale",
        )
        fields = self._get_created_fields(provider)
        assert fields["labels"] == ["crd-scale", "etcdCPU_avg"]

    def test_labels_without_test(self):
        provider = self._make_provider()
        provider.create_ack(
            uuid="abc-123",
            metric="etcdCPU_avg",
            reason="regression detected",
            version="4.22",
        )
        fields = self._get_created_fields(provider)
        assert fields["labels"] == ["4.22", "etcdCPU_avg"]

    def test_labels_metric_only(self):
        provider = self._make_provider()
        provider.create_ack(
            uuid="abc-123",
            metric="etcdCPU_avg",
            reason="regression detected",
        )
        fields = self._get_created_fields(provider)
        assert fields["labels"] == ["etcdCPU_avg"]

    def test_summary_includes_metric_and_version(self):
        provider = self._make_provider()
        provider.create_ack(
            uuid="abc-123",
            metric="etcdCPU_avg",
            reason="regression detected",
            version="4.22",
        )
        fields = self._get_created_fields(provider)
        assert fields["summary"] == "Regression in etcdCPU_avg (4.22)"

    def test_summary_without_version(self):
        provider = self._make_provider()
        provider.create_ack(
            uuid="abc-123",
            metric="etcdCPU_avg",
            reason="regression detected",
        )
        fields = self._get_created_fields(provider)
        assert fields["summary"] == "Regression in etcdCPU_avg"

    def test_issue_type_is_bug(self):
        provider = self._make_provider()
        provider.create_ack(
            uuid="abc-123",
            metric="etcdCPU_avg",
            reason="regression detected",
            version="4.22",
            test="crd-scale",
        )
        fields = self._get_created_fields(provider)
        assert fields["issuetype"] == {"name": "Bug"}

    def test_project_key(self):
        provider = self._make_provider()
        provider.create_ack(
            uuid="abc-123",
            metric="etcdCPU_avg",
            reason="regression detected",
        )
        fields = self._get_created_fields(provider)
        assert fields["project"] == {"key": "PERFSCALE"}

    def test_component_added_when_valid(self):
        provider = self._make_provider(component="CPT_ISSUES")
        mock_comp = MagicMock()
        mock_comp.name = "CPT_ISSUES"
        provider.jira.project_components = MagicMock(return_value=[mock_comp])
        provider.create_ack(
            uuid="abc-123",
            metric="etcdCPU_avg",
            reason="regression detected",
        )
        fields = self._get_created_fields(provider)
        assert fields["components"] == [{"name": "CPT_ISSUES"}]

    def test_component_skipped_when_invalid(self):
        provider = self._make_provider(component="NONEXISTENT")
        mock_comp = MagicMock()
        mock_comp.name = "CPT_ISSUES"
        provider.jira.project_components = MagicMock(return_value=[mock_comp])
        provider.create_ack(
            uuid="abc-123",
            metric="etcdCPU_avg",
            reason="regression detected",
        )
        fields = self._get_created_fields(provider)
        assert "components" not in fields

    def test_component_skipped_when_empty(self):
        provider = self._make_provider(component="")
        provider.create_ack(
            uuid="abc-123",
            metric="etcdCPU_avg",
            reason="regression detected",
        )
        fields = self._get_created_fields(provider)
        assert "components" not in fields

    def test_simple_description_includes_all_fields(self):
        provider = self._make_provider()
        provider.create_ack(
            uuid="abc-123-def",
            metric="etcdCPU_avg",
            reason="threshold exceeded",
            version="4.22",
            test="crd-scale",
            build_url="https://prow.ci/build/123",
            build_id="123",
            pct_change="+44.42",
        )
        fields = self._get_created_fields(provider)
        desc = fields["description"]
        assert "UUID: abc-123-def" in desc
        assert "Metric: etcdCPU_avg" in desc
        assert "Reason: threshold exceeded" in desc
        assert "Version: 4.22" in desc
        assert "Test: crd-scale" in desc
        assert "Build URL: https://prow.ci/build/123" in desc
        assert "Build ID: 123" in desc
        assert "Change: +44.42%" in desc

    def test_rich_description_used_when_jira_markup(self):
        provider = self._make_provider()
        rich_desc = "h2. Performance Regression\nDetails here"
        provider.create_ack(
            uuid="abc-123",
            metric="etcdCPU_avg",
            reason=rich_desc,
        )
        fields = self._get_created_fields(provider)
        assert fields["description"] == rich_desc

    def test_skips_creation_when_issue_exists(self):
        provider = self._make_provider()
        existing = MagicMock()
        existing.key = "PERFSCALE-100"
        provider._find_existing_issue = MagicMock(return_value=existing)  # pylint: disable=protected-access
        result = provider.create_ack(
            uuid="abc-123",
            metric="etcdCPU_avg",
            reason="regression detected",
        )
        assert result is None
        provider.jira.create_issue.assert_not_called()

    def test_returns_issue_key_on_success(self):
        provider = self._make_provider()
        result = provider.create_ack(
            uuid="abc-123",
            metric="etcdCPU_avg",
            reason="regression detected",
            version="4.22",
            test="crd-scale",
        )
        assert result == "PERFSCALE-999"


class TestRemovedAutoDetectFunctions:
    """Verify that removed functions are no longer importable."""

    def test_fetch_remote_ack_file_removed(self):
        with pytest.raises(ImportError):
            from orion.config import fetch_remote_ack_file  # noqa: F401 # pylint: disable=no-name-in-module,unused-import,import-outside-toplevel

    def test_auto_detect_ack_file_with_vars_removed(self):
        with pytest.raises(ImportError):
            from orion.config import auto_detect_ack_file_with_vars  # noqa: F401 # pylint: disable=no-name-in-module,unused-import,import-outside-toplevel

    def test_remote_ack_url_removed(self):
        from orion import config  # pylint: disable=import-outside-toplevel
        assert not hasattr(config, "REMOTE_ACK_URL")
