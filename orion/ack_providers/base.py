"""
orion.ack_providers.base

Abstract base class for ACK providers.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class AckProvider(ABC):
    """
    Abstract base class for acknowledgment providers.

    Providers are responsible for retrieving and creating acknowledgments
    for performance regressions detected by Orion.
    """

    @abstractmethod
    def get_acks(
        self,
        version: Optional[str] = None,
        test_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve acknowledgment entries, optionally filtered by version and test type.

        Args:
            version: Optional version filter (e.g., '4.22')
            test_type: Optional test type filter (e.g., 'node-density-cni')

        Returns:
            List of acknowledgment dictionaries with keys:
            - uuid: str - Test run UUID
            - metric: str - Metric name
            - reason: str - Reason for acknowledgment
            - version: str - OpenShift version
            - test: str - Test type
            - (optional) jira_key: str - JIRA issue key if applicable
        """

    @abstractmethod
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
        Create a new acknowledgment for a regression.

        Args:
            uuid: Test run UUID
            metric: Metric name that regressed
            reason: Reason for acknowledgment (e.g., bug URL, explanation)
            version: OpenShift version
            test: Test type
            **kwargs: Provider-specific additional arguments

        Returns:
            True if acknowledgment was created successfully, False otherwise
        """

    def merge_acks(self, ack_lists: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """
        Merge multiple acknowledgment lists, removing duplicates.

        Args:
            ack_lists: List of acknowledgment lists to merge

        Returns:
            Merged list with duplicates removed (based on uuid + metric)
        """
        seen = set()
        merged = []

        for ack_list in ack_lists:
            for entry in ack_list:
                key = (entry.get("uuid"), entry.get("metric"))
                if key not in seen:
                    seen.add(key)
                    merged.append(entry)

        return merged
