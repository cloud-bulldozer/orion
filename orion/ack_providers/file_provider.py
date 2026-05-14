"""
orion.ack_providers.file_provider

File-based ACK provider using YAML files.
"""

import os
from typing import List, Dict, Any, Optional

import yaml

from orion.ack_providers.base import AckProvider
from orion.config import load_ack
from orion.logger import SingletonLogger


class FileAckProvider(AckProvider):
    """
    File-based acknowledgment provider.

    Loads acknowledgments from YAML files on the filesystem.
    Supports the existing all_ack.yaml format.
    """

    def __init__(self, ack_file: str):
        """
        Initialize file-based ACK provider.

        Args:
            ack_file: Path to the acknowledgment YAML file
        """
        self.ack_file = ack_file
        self.logger = SingletonLogger.get_or_create_logger("Orion")

    def get_acks(
        self,
        version: Optional[str] = None,
        test_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Load acknowledgments from YAML file.

        Args:
            version: Optional version filter
            test_type: Optional test type filter

        Returns:
            List of acknowledgment entries
        """
        if not os.path.exists(self.ack_file):
            self.logger.warning("ACK file not found: %s", self.ack_file)
            return []

        try:
            ack_map = load_ack(self.ack_file, version=version, test_type=test_type)
            if ack_map and "ack" in ack_map:
                self.logger.debug(
                    "Loaded %d ACK entries from %s",
                    len(ack_map["ack"]),
                    self.ack_file
                )
                return ack_map["ack"]
            return []
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("Failed to load ACK file %s: %s", self.ack_file, e)
            return []

    def create_ack(
        self,
        uuid: str,
        metric: str,
        reason: str,
        version: Optional[str] = None,
        test: Optional[str] = None,
        **kwargs
    ) -> Optional[str]:
        """
        Append a new acknowledgment to the YAML file.

        Args:
            uuid: Test run UUID
            metric: Metric name
            reason: Reason for acknowledgment
            version: OpenShift version
            test: Test type
            **kwargs: Additional fields to include

        Returns:
            UUID on success, None on failure
        """
        try:
            # Load existing acks
            existing_acks = {"ack": []}
            if os.path.exists(self.ack_file):
                with open(self.ack_file, "r", encoding="utf-8") as f:
                    existing_acks = yaml.safe_load(f) or {"ack": []}

            # Create new entry
            new_entry = {
                "uuid": uuid,
                "metric": metric,
                "reason": reason
            }
            if version:
                new_entry["version"] = version
            if test:
                new_entry["test"] = test

            # Add any additional fields from kwargs
            new_entry.update(kwargs)

            # Check for duplicates
            for existing in existing_acks.get("ack", []):
                if existing.get("uuid") == uuid and existing.get("metric") == metric:
                    self.logger.warning(
                        "ACK entry already exists for uuid=%s, metric=%s",
                        uuid, metric
                    )
                    return None

            # Append and save
            existing_acks.setdefault("ack", []).append(new_entry)

            with open(self.ack_file, "w", encoding="utf-8") as f:
                yaml.dump(existing_acks, f, default_flow_style=False, sort_keys=False)

            self.logger.info(
                "Created ACK entry: uuid=%s, metric=%s, file=%s",
                uuid[:8], metric, self.ack_file
            )
            return uuid

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("Failed to create ACK entry: %s", e)
            return None
