"""
orion.ack_providers.jira_provider

JIRA-based ACK provider for tracking regressions in JIRA.
"""

import time
from typing import List, Dict, Any, Optional, NamedTuple
import re

from orion.ack_providers.base import AckProvider
from orion.logger import SingletonLogger


class JiraConfig(NamedTuple):
    """Configuration for JIRA field mapping and query settings."""
    uuid_field: str = "description"
    metric_field: str = "labels"
    max_results: int = 1000
    retry_attempts: int = 3
    retry_delay: int = 2

try:
    from jira import JIRA
    from jira.exceptions import JIRAError
    JIRA_AVAILABLE = True
except ImportError:
    JIRA_AVAILABLE = False


class JiraAckProvider(AckProvider):
    """
    JIRA-based acknowledgment provider.

    Tracks regressions as JIRA issues in a specified project/component.
    """

    def __init__(
        self,
        jira_url: str,
        project: str = "PERFSCALE",
        component: str = "CPT_ISSUES",
        uuid_field: str = "description",  # Can be custom field like 'customfield_12345'
        metric_field: str = "labels",  # Can be custom field
        auth: Optional[tuple] = None,
        token: Optional[str] = None,
        email: Optional[str] = None,  # For Atlassian Cloud
        max_results: int = 1000,
        retry_attempts: int = 3,
        retry_delay: int = 2
    ):
        """
        Initialize JIRA ACK provider.

        Args:
            jira_url: JIRA instance URL (e.g., 'https://issues.redhat.com')
            project: JIRA project key (default: 'PERFSCALE')
            component: JIRA component name (default: 'CPT_ISSUES')
            uuid_field: Field name for storing UUID (default: 'description')
            metric_field: Field name for storing metric (default: 'labels')
            auth: Tuple of (username, password) for basic auth
            token: Personal access token for authentication
            max_results: Maximum results to fetch per query
            retry_attempts: Number of retry attempts for failed operations
            retry_delay: Delay in seconds between retries
        """
        if not JIRA_AVAILABLE:
            raise ImportError(
                "jira library not installed. Install with: pip install jira"
            )

        self.jira_url = jira_url
        self.project = project
        self.component = component
        self.config = JiraConfig(
            uuid_field=uuid_field,
            metric_field=metric_field,
            max_results=max_results,
            retry_attempts=retry_attempts,
            retry_delay=retry_delay
        )
        self.logger = SingletonLogger.get_or_create_logger("Orion")

        # Initialize JIRA client
        try:
            # Detect if this is Atlassian Cloud or on-premise
            is_cloud = "atlassian.net" in jira_url.lower()

            if is_cloud:
                # Atlassian Cloud requires email + API token
                if email and token:
                    self.logger.debug("Using Atlassian Cloud auth (email + API token)")
                    self.jira = JIRA(server=jira_url, basic_auth=(email, token))
                elif auth and len(auth) == 2:
                    # auth tuple is (email, api_token) for cloud
                    self.logger.debug("Using Atlassian Cloud auth from tuple")
                    self.jira = JIRA(server=jira_url, basic_auth=auth)
                else:
                    self.logger.error(
                        "Atlassian Cloud (%s) requires email + API token. "
                        "Set JIRA_EMAIL and JIRA_TOKEN environment variables.",
                        jira_url
                    )
                    raise ValueError("Missing email or API token for Atlassian Cloud")
            else:
                # On-premise JIRA
                if token:
                    self.logger.debug("Using personal access token auth")
                    self.jira = JIRA(server=jira_url, token_auth=token)
                elif auth:
                    self.logger.debug("Using basic auth")
                    self.jira = JIRA(server=jira_url, basic_auth=auth)
                else:
                    # Try Kerberos or session-based auth
                    self.logger.debug("Trying Kerberos/session auth")
                    self.jira = JIRA(server=jira_url)

            self.logger.info("Connected to JIRA: %s", jira_url)

            # Verify permissions
            self._verify_permissions()

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("Failed to connect to JIRA: %s", e)
            if "atlassian.net" in jira_url.lower():
                self.logger.error(
                    "For Atlassian Cloud, use: export JIRA_EMAIL=your@email.com JIRA_TOKEN=your_api_token"
                )
            raise

    def _verify_permissions(self):
        """
        Verify that the user has necessary permissions.
        Provides helpful error messages if permissions are missing.
        """
        try:
            # Check if user can access the project
            try:
                project = self.jira.project(self.project)
                self.logger.debug("✓ Can access project: %s", self.project)
            except JIRAError as e:
                if e.status_code == 404:
                    self.logger.warning(
                        "Project '%s' not found or not accessible. "
                        "Check --jira-project setting.",
                        self.project
                    )
                elif e.status_code in (401, 403):
                    self.logger.warning(
                        "No permission to access project '%s'. "
                        "Contact your JIRA admin to grant access.",
                        self.project
                    )
                return

            # Try to get current user
            try:
                current_user = self.jira.current_user()
                self.logger.debug("Connected as JIRA user: %s", current_user)
            except Exception:  # pylint: disable=broad-exception-caught
                pass

            # Check for component
            try:
                components = self.jira.project_components(project)
                component_names = [c.name for c in components]
                if self.component not in component_names:
                    self.logger.warning(
                        "Component '%s' not found in project '%s'.",
                        self.component,
                        self.project
                    )
                    if component_names:
                        self.logger.info(
                            "Available components: %s",
                            ", ".join(component_names[:10])
                        )
                        self.logger.info(
                            "Use --jira-component to specify a valid component, "
                            "or issues will be created without one."
                        )
                else:
                    self.logger.debug("✓ Component '%s' exists", self.component)
            except Exception:  # pylint: disable=broad-exception-caught
                pass

            # Note: We can't reliably check create permission without attempting to create
            # The actual create attempt will provide the definitive error if permissions are missing

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.debug("Permission check completed with warnings: %s", e)

    def get_acks(
        self,
        version: Optional[str] = None,
        test_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Query JIRA for acknowledged regressions.

        Args:
            version: Optional version filter (added as label filter)
            test_type: Optional test type filter (added as label filter)

        Returns:
            List of acknowledgment entries parsed from JIRA issues
        """
        try:
            # Build JQL query
            jql_parts = [f"project = {self.project}"]

            # Only add component filter if component is specified
            if self.component:
                jql_parts.append(f"component = {self.component}")

            # Add label filters for version and test type
            if version:
                jql_parts.append(f"labels = '{version}'")
            if test_type:
                jql_parts.append(f"labels = '{test_type}'")

            jql = " AND ".join(jql_parts)
            self.logger.debug("JIRA JQL query: %s", jql)

            # Execute query
            issues = self.jira.search_issues(
                jql,
                maxResults=self.config.max_results,
                fields="summary,description,labels,customfield_*"
            )

            self.logger.info(
                "Retrieved %d JIRA issues for ACK from %s",
                len(issues),
                self.project
            )

            if len(issues) > 0:
                self.logger.debug("Sample issue keys: %s", [i.key for i in issues[:5]])

            # Parse issues into ACK entries
            acks = []
            for issue in issues:
                try:
                    self.logger.debug("Parsing issue: %s", issue.key)
                    ack_entry = self._parse_issue(issue, version, test_type)
                    if ack_entry:
                        acks.append(ack_entry)
                        self.logger.debug(
                            "Successfully parsed %s: uuid=%s, metric=%s",
                            issue.key,
                            ack_entry.get("uuid", "")[:8],
                            ack_entry.get("metric")
                        )
                    else:
                        self.logger.debug("Failed to parse %s (UUID or metric not found)", issue.key)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    self.logger.warning(
                        "Failed to parse JIRA issue %s: %s",
                        issue.key, e
                    )
                    continue

            self.logger.info("Parsed %d valid ACK entries from JIRA", len(acks))
            return acks

        except JIRAError as e:
            self.logger.error("JIRA query failed: %s", e)
            return []
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("Failed to retrieve ACKs from JIRA: %s", e)
            return []

    def _parse_issue(
        self,
        issue,
        version: Optional[str] = None,
        test_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Parse a JIRA issue into an ACK entry.

        Expected formats:
        - UUID in description or custom field
        - Metric in labels or custom field
        - Version in labels
        - Test type in labels

        Args:
            issue: JIRA issue object
            version: Version for fallback
            test_type: Test type for fallback

        Returns:
            ACK entry dict or None if parsing fails
        """

        # Extract UUID
        uuid = None
        if self.config.uuid_field.startswith("customfield_"):
            uuid = getattr(issue.fields, self.config.uuid_field, None)
        elif self.config.uuid_field == "description":
            # Try to extract UUID from description
            desc = getattr(issue.fields, "description", "")
            if desc:
                # Look for UUID pattern in description (case-insensitive, allows letters and numbers)

                # First try to find UUID: prefix pattern (most specific)
                # Handles JIRA markup: *UUID:* {{uuid}} or UUID: uuid
                uuid_line_match = re.search(r"\*?UUID:\*?\s*\{\{?([a-zA-Z0-9-]+)\}?\}?", desc, re.IGNORECASE)
                if uuid_line_match:
                    uuid = uuid_line_match.group(1)
                    self.logger.debug("Extracted UUID from 'UUID:' line: %s", uuid[:8] + "...")
                else:
                    # Fallback: flexible UUID pattern - any alphanumeric segments with dashes
                    uuid_pattern = r"[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+"
                    match = re.search(uuid_pattern, desc)
                    if match:
                        uuid = match.group(0)
                        self.logger.debug("Extracted UUID from description pattern: %s", uuid[:8] + "...")

        if not uuid:
            self.logger.warning("No UUID found in issue %s (description preview: %s)",
                              issue.key,
                              str(getattr(issue.fields, "description", ""))[:100])
            return None

        # Extract metric
        metric = None
        if self.config.metric_field.startswith("customfield_"):
            metric = getattr(issue.fields, self.config.metric_field, None)
        elif self.config.metric_field == "labels":
            # Try to find metric in labels (look for metric-like labels)
            labels = getattr(issue.fields, "labels", [])
            self.logger.debug("Issue %s has labels: %s", issue.key, labels)

            # Known metric patterns (e.g., ovnCPU_avg, kubelet_avg, etc.)
            # Look for labels with common metric patterns
            for label in labels:
                # Skip version labels (e.g., "4.22", "4.21")
                if re.match(r'^\d+\.\d+$', label):
                    continue
                # Skip known test type patterns
                if label == test_type:
                    continue
                # Look for metric patterns: contains underscore or common suffixes
                if "_" in label or label.endswith(("CPU", "Mem", "Memory", "Latency")):
                    metric = label
                    self.logger.debug("Extracted metric from labels: %s", metric)
                    break

            # If still no metric, check the summary for metric name
            if not metric:
                summary = getattr(issue.fields, "summary", "")
                # Summary format: "Regression in {metric} ({version})"
                metric_match = re.match(r"Regression in ([^\s(]+)", summary)
                if metric_match:
                    metric = metric_match.group(1)
                    self.logger.debug("Extracted metric from summary: %s", metric)

        if not metric:
            self.logger.warning("No metric found in issue %s (labels: %s, summary: %s)",
                              issue.key,
                              getattr(issue.fields, "labels", []),
                              getattr(issue.fields, "summary", ""))
            return None

        # Extract reason (summary)
        reason = getattr(issue.fields, "summary", "")

        # Extract labels for version/test
        labels = getattr(issue.fields, "labels", [])
        issue_version = version
        issue_test = test_type

        # Try to identify version and test from labels
        for label in labels:
            if label.startswith("4."):  # Version pattern
                issue_version = label
            elif label not in [metric] and label != issue_version:
                # Assume it's test type
                issue_test = label

        return {
            "uuid": uuid,
            "metric": metric,
            "reason": reason,
            "version": issue_version,
            "test": issue_test,
            "jira_key": issue.key
        }

    def create_ack(
        self,
        uuid: str,
        metric: str,
        reason: str,
        version: Optional[str] = None,
        test: Optional[str] = None,
        **kwargs
    ) -> bool:
        """
        Create a new JIRA issue for a regression acknowledgment.

        Args:
            uuid: Test run UUID
            metric: Metric name
            reason: Reason for acknowledgment
            version: OpenShift version
            test: Test type
            **kwargs: Additional fields (e.g., build_url, pct_change)

        Returns:
            True if issue created successfully, False otherwise
        """
        # Check if issue already exists
        existing = self._find_existing_issue(uuid, metric)
        if existing:
            self.logger.info(
                "JIRA issue already exists for uuid=%s, metric=%s: %s",
                uuid[:8], metric, existing.key
            )
            return False

        # Build issue fields
        labels = []
        if version:
            labels.append(version)
        if test:
            labels.append(test)
        if metric:
            labels.append(metric)

        summary = f"Regression in {metric}"
        if version:
            summary += f" ({version})"

        # Check if reason contains rich JIRA markup (from format_jira_description)
        # If so, use it as the full description; otherwise build simple format
        if reason and reason.startswith(("h2.", "h3.", "h4.")):
            description = reason
        else:
            # Build simple description format
            description = "Performance regression detected:\n\n"
            description += f"UUID: {uuid}\n"
            description += f"Metric: {metric}\n"
            description += f"Reason: {reason}\n"
            if version:
                description += f"Version: {version}\n"
            if test:
                description += f"Test: {test}\n"

            # Add additional context from kwargs
            if "build_url" in kwargs:
                description += f"Build URL: {kwargs['build_url']}\n"
            if "pct_change" in kwargs:
                description += f"Change: {kwargs['pct_change']}%\n"

        issue_dict = {
            "project": {"key": self.project},
            "summary": summary,
            "description": description,
            "issuetype": {"name": "Bug"},
            "labels": labels
        }

        # Only add component if it exists and is valid
        if self.component:
            # Try to verify component exists first
            try:
                components = self.jira.project_components(self.project)
                component_names = [c.name for c in components]
                if self.component in component_names:
                    issue_dict["components"] = [{"name": self.component}]
                    self.logger.debug("Adding component: %s", self.component)
                else:
                    self.logger.warning(
                        "Component '%s' not found in project '%s'. Creating issue without component. "
                        "Available: %s",
                        self.component, self.project, ", ".join(component_names[:5])
                    )
            except Exception as e:  # pylint: disable=broad-exception-caught
                self.logger.debug("Could not verify component, creating issue without it: %s", e)

        # Honor custom field configuration for UUID and metric storage
        if self.config.uuid_field.startswith("customfield_"):
            issue_dict[self.config.uuid_field] = uuid
            self.logger.debug("Storing UUID in custom field: %s", self.config.uuid_field)

        if self.config.metric_field.startswith("customfield_"):
            issue_dict[self.config.metric_field] = metric
            self.logger.debug("Storing metric in custom field: %s", self.config.metric_field)

        # Attempt creation with retry logic
        for attempt in range(self.config.retry_attempts):
            try:
                new_issue = self.jira.create_issue(fields=issue_dict)
                self.logger.info(
                    "Created JIRA issue %s for uuid=%s, metric=%s",
                    new_issue.key, uuid[:8], metric
                )

                # Verify creation
                time.sleep(1)  # Brief delay for JIRA indexing
                verify = self._find_existing_issue(uuid, metric)
                if verify:
                    self.logger.info("Verified JIRA issue creation: %s", verify.key)
                    return True

                self.logger.warning("JIRA issue created but verification failed")
                return True  # Issue was created even if verification failed

            except JIRAError as e:
                # Check for permission errors specifically
                if e.status_code in (401, 403):
                    self.logger.error(
                        "JIRA permission denied (HTTP %d): %s",
                        e.status_code,
                        e.text
                    )
                    self.logger.error(
                        "You don't have permission to create issues in project '%s'. "
                        "Please contact your JIRA admin to grant 'Create Issues' permission.",
                        self.project
                    )
                    # Don't retry permission errors
                    return False
                if e.status_code == 400 and "component" in e.text.lower():
                    self.logger.error(
                        "JIRA component error (HTTP %d): %s",
                        e.status_code,
                        e.text
                    )
                    self.logger.error(
                        "Component '%s' may not exist in project '%s'. "
                        "Run 'python test_jira_auth.py' to see available components, "
                        "or use --jira-component '' to skip component.",
                        self.component,
                        self.project
                    )
                    # Don't retry component errors
                    return False
                self.logger.warning(
                    "JIRA creation attempt %d/%d failed: %s",
                    attempt + 1, self.config.retry_attempts, e
                )
                if attempt < self.config.retry_attempts - 1:
                    time.sleep(self.config.retry_delay)
                continue
            except Exception as e:  # pylint: disable=broad-exception-caught
                self.logger.error("Unexpected error creating JIRA issue: %s", e)
                break

        self.logger.error("Failed to create JIRA issue after %d attempts", self.config.retry_attempts)
        return False

    def _find_existing_issue(self, uuid: str, metric: str):
        """
        Search for existing JIRA issue matching UUID and metric.

        Args:
            uuid: Test run UUID
            metric: Metric name

        Returns:
            JIRA issue object or None
        """
        try:
            # Build JQL query based on configured field mappings
            jql_parts = [f'project = {self.project}']

            # Only add component filter if component is specified
            if self.component:
                jql_parts.append(f'component = {self.component}')

            # Search UUID field (description or custom field)
            if self.config.uuid_field.startswith("customfield_"):
                jql_parts.append(f'{self.config.uuid_field} ~ "{uuid}"')
            else:
                # Default to description search
                jql_parts.append(f'description ~ "{uuid}"')

            # Search metric field (labels or custom field)
            if self.config.metric_field.startswith("customfield_"):
                jql_parts.append(f'{self.config.metric_field} ~ "{metric}"')
            elif self.config.metric_field == "labels":
                jql_parts.append(f'labels = "{metric}"')

            jql = ' AND '.join(jql_parts)
            issues = self.jira.search_issues(jql, maxResults=10)

            for issue in issues:
                # Verify it's the right issue
                parsed = self._parse_issue(issue)
                if parsed and parsed.get("uuid") == uuid and parsed.get("metric") == metric:
                    return issue

            return None

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.debug("Error searching for existing issue: %s", e)
            return None
