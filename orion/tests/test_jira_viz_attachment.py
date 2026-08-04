"""
Test that _attach_viz_to_jira scopes attachments per PR.

The fix (main.py) calls auto_create_jira_issues once per PR and stores
results in issue_keys_by_test_pull_by_pr keyed by pr_num. Each PR's
viz files are then attached only to that PR's JIRA issues.

CodeRabbit review: https://github.com/cloud-bulldozer/orion/pull/421
"""

import os
import tempfile
from unittest.mock import MagicMock, call

from main import auto_create_jira_issues, _attach_viz_to_jira, build_viz_output_file


def _make_regression(test_name, uuid, metric, pct_change=-10.0):
    return {
        "test_name": test_name,
        "uuid": uuid,
        "metrics_with_change": [
            {"name": metric, "percentage_change": pct_change}
        ],
        "bad_ver": "4.18",
        "prev_ver": "4.17",
    }


class TestPerPRAttachmentScoping:  # pylint: disable=too-few-public-methods
    """Verify that per-PR viz attachments are scoped correctly."""

    def test_viz_attached_only_to_own_pr_issues(self):
        """Each PR's viz should only attach to JIRA issues created from
        that PR's regressions, not to issues from other PRs.
        """
        provider = MagicMock()

        pr1_regression = _make_regression("node-density", "uuid-pr1111", "podLatency")
        pr2_regression = _make_regression("node-density", "uuid-pr2222", "podLatency")

        provider.create_ack = MagicMock(side_effect=["PERF-100", "PERF-200"])

        # Mirror the fixed flow: call auto_create_jira_issues once per PR
        _, pr1_issue_keys = auto_create_jira_issues(
            [pr1_regression], provider, MagicMock()
        )
        _, pr2_issue_keys = auto_create_jira_issues(
            [pr2_regression], provider, MagicMock()
        )

        issue_keys_by_test_pull_by_pr = {
            1111: pr1_issue_keys,
            2222: pr2_issue_keys,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            base = os.path.join(tmpdir, "output")
            pull_numbers = [1111, 2222]

            for pr_num in pull_numbers:
                viz_path = build_viz_output_file(base, "node-density", f"pull_{pr_num}")
                with open(viz_path, "w", encoding="utf-8") as f:
                    f.write(f"<html>viz for PR {pr_num}</html>")

            provider.attach_file = MagicMock(return_value=True)
            for pr_num in pull_numbers:
                issue_keys_for_pr = issue_keys_by_test_pull_by_pr.get(pr_num, {})
                _attach_viz_to_jira(
                    provider, issue_keys_for_pr, base,
                    f"pull_{pr_num}", MagicMock()
                )

            attach_calls = provider.attach_file.call_args_list

            pr1_viz = build_viz_output_file(base, "node-density", "pull_1111")
            pr2_viz = build_viz_output_file(base, "node-density", "pull_2222")

            pr1_to_wrong_issue = call("PERF-200", pr1_viz) in attach_calls
            pr2_to_wrong_issue = call("PERF-100", pr2_viz) in attach_calls

            assert not pr1_to_wrong_issue, (
                "PR 1111 viz was attached to PERF-200 (PR 2222's issue) — cross-contamination!"
            )
            assert not pr2_to_wrong_issue, (
                "PR 2222 viz was attached to PERF-100 (PR 1111's issue) — cross-contamination!"
            )

            assert call("PERF-100", pr1_viz) in attach_calls, (
                "PR 1111 viz should be attached to PERF-100"
            )
            assert call("PERF-200", pr2_viz) in attach_calls, (
                "PR 2222 viz should be attached to PERF-200"
            )
