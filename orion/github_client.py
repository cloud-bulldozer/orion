"""
GitHub client helpers to enrich changepoint output with release and commit details.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import requests

from orion.logger import SingletonLogger


class GitHubClient:
    """
    Lightweight GitHub API client with caching for release and commit lookups.
    """

    def __init__(
        self,
        repositories: List[str],
        token: Optional[str] = None,
        timeout: int = 15,
    ) -> None:
        cleaned_repos = [repo.strip()
                         for repo in repositories if repo and repo.strip()]
        self.repositories: List[str] = cleaned_repos
        self.logger = SingletonLogger.get_logger("Orion")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/vnd.github+json"})
        auth_token = token or os.getenv(
            "GITHUB_TOKEN") or os.getenv("GH_TOKEN")
        if auth_token:
            self.session.headers.update(
                {"Authorization": f"Bearer {auth_token}"})

        self._release_cache: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        self._commit_cache: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        self._context_cache: Dict[Tuple[str, str,
                                        str, str], Optional[Dict[str, Any]]] = {}

    def _request_json(self, url: str) -> Tuple[Optional[Any], Optional[str]]:
        try:
            response = self.session.get(url, timeout=self.timeout)
        except requests.RequestException as exc:
            self.logger.warning("GitHub request failed for %s: %s", url, exc)
            return None, f"request failed: {exc}"

        if response.status_code == 404:
            return None, "not found (404)"

        if response.status_code == 403:
            limit = response.headers.get("X-RateLimit-Remaining", "unknown")
            reset = response.headers.get("X-RateLimit-Reset")
            self.logger.warning(
                "GitHub API rate limited (remaining=%s, reset=%s) for %s",
                limit,
                reset,
                url,
            )
            reset_hint = f", reset={reset}" if reset else ""
            return None, f"rate limited or forbidden (remaining={limit}{reset_hint})"

        if not response.ok:
            self.logger.warning(
                "GitHub request returned unexpected status %s for %s",
                response.status_code,
                url,
            )
            return None, f"unexpected status {response.status_code}"
        try:
            return response.json(), None
        except ValueError:
            self.logger.debug("GitHub response was not valid JSON for %s", url)
            return None, "invalid JSON payload"

    @staticmethod
    def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace(
                "Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return None

    # pylint: disable=too-many-return-statements
    def _coerce_timestamp(self, value: Optional[Any]) -> Optional[datetime]:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc)
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(value, tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                return None
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            if stripped.isdigit():
                try:
                    return datetime.fromtimestamp(
                        int(stripped), tz=timezone.utc)
                except (OverflowError, OSError, ValueError):
                    return None
            try:
                numeric = float(stripped)
                return datetime.fromtimestamp(numeric, tz=timezone.utc)
            except (ValueError, OverflowError, OSError):
                pass
            return self._parse_iso_datetime(stripped)
        return None

    def _normalize_timestamp(self, value: Optional[Any]) -> Optional[str]:
        coerced = self._coerce_timestamp(value)
        if coerced is None:
            return None
        return coerced.astimezone(
            timezone.utc).isoformat().replace(
            "+00:00", "Z")

    def _prepare_interval(
        self,
        start_timestamp: Optional[Any],
        end_timestamp: Optional[Any],
        normalized_start: Optional[str],
        normalized_end: Optional[str],
    ) -> Dict[str, Any]:
        start_dt = self._coerce_timestamp(start_timestamp)
        end_dt = self._coerce_timestamp(end_timestamp)
        if end_dt is None:
            error = "current timestamp not provided or invalid"
        elif start_dt is None:
            error = "previous timestamp not provided or invalid"
        elif start_dt >= end_dt:
            error = "previous timestamp is not earlier than current timestamp"
        else:
            error = None
        return {
            "start_dt": start_dt,
            "end_dt": end_dt,
            "normalized_start": normalized_start,
            "normalized_end": normalized_end,
            "error": error,
        }

    @staticmethod
    def _make_cache_key(repo: str,
                        normalized_start: Optional[str],
                        normalized_end: Optional[str]) -> Tuple[str,
                                                                str,
                                                                str]:
        return (
            repo,
            normalized_start or "__none__",
            normalized_end or "__none__",
        )

    @staticmethod
    def _build_collection_entry(
        items: List[Dict[str, Any]],
        start: Optional[str],
        end: Optional[str],
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        entry: Dict[str, Any] = {
            "start": start,
            "end": end,
            "count": len(items),
            "items": items,
        }
        if reason:
            entry["reason"] = reason
        return entry

    def _build_url(
        self,
        repo: str,
        item_type: str,
        page: int,
        normalized_start: Optional[str],
        normalized_end: Optional[str]
    ) -> str:
        """Build API URL based on item type."""
        if item_type == 'releases':
            return f"https://api.github.com/repos/{repo}/releases?per_page=100&page={page}"
        query_parts = ["per_page=100", f"page={page}"]
        if normalized_start:
            query_parts.append(f"since={quote(normalized_start, safe='')}")
        if normalized_end:
            query_parts.append(f"until={quote(normalized_end, safe='')}")
        query = "&".join(query_parts)
        return f"https://api.github.com/repos/{repo}/commits?{query}"

    def process_items(
        self,
        payload: List[Dict[str, Any]],
        item_type: str,
        start_dt: Any,
        end_dt: Any,
        collected: List[Dict[str, Any]]
    ) -> bool:
        """
        Process items from payload and add to collected list.
        Returns True if we should stop pagination (for releases only).
        """
        if item_type == 'releases':
            return self._process_releases(payload, start_dt, end_dt, collected)
        self._process_commits(payload, start_dt, end_dt, collected)
        return False

    def _process_releases(
        self,
        payload: List[Dict[str, Any]],
        start_dt: Any,
        end_dt: Any,
        collected: List[Dict[str, Any]]
    ) -> bool:
        """Process releases and return True if we've gone past start_dt."""
        for release in payload:
            published_at = release.get(
                "published_at") or release.get("created_at")
            release_dt = self._parse_iso_datetime(published_at)

            if release_dt is None or release_dt > end_dt:
                continue

            if release_dt <= start_dt:
                return True  # Signal to stop pagination

            collected.append({
                "name": release.get("name"),
                "html_url": release.get("html_url"),
                "published_at": release.get("published_at"),
                "created_at": release.get("created_at"),
                "target_commitish": release.get("target_commitish"),
            })
        return False

    def _process_commits(
        self,
        payload: List[Dict[str, Any]],
        start_dt: Any,
        end_dt: Any,
        collected: List[Dict[str, Any]]
    ) -> None:
        """Process commits and add to collected list."""
        for commit in payload:
            commit_info = commit.get("commit", {})
            author_info = commit_info.get("author", {})
            commit_date = self._parse_iso_datetime(author_info.get("date"))

            if commit_date is None or commit_date <= start_dt or commit_date > end_dt:
                continue

            collected.append({
                "html_url": commit.get("html_url"),
                "commit_author": {
                    "name": author_info.get("name"),
                    "email": author_info.get("email"),
                },
                "commit_timestamp": author_info.get("date"),
                "message": commit_info.get("message"),
            })

    def _get_items_between(
        self,
        repo: str,
        start_timestamp: Optional[Any],
        end_timestamp: Optional[Any],
        item_type: str,  # 'releases' or 'commits'
    ) -> Dict[str, Any]:
        """Generic method to fetch releases or commits between timestamps."""
        # Setup and caching
        normalized_start = self._normalize_timestamp(start_timestamp)
        normalized_end = self._normalize_timestamp(end_timestamp)
        cache = self._release_cache if item_type == 'releases' else self._commit_cache
        cache_key = self._make_cache_key(
            repo, normalized_start, normalized_end)

        if cache_key in cache:
            return cache[cache_key]

        # Validate interval
        interval = self._prepare_interval(
            start_timestamp,
            end_timestamp,
            normalized_start,
            normalized_end)
        if interval["error"]:
            entry = self._build_collection_entry(
                [], normalized_start, normalized_end, interval["error"])
            cache[cache_key] = entry
            return entry

        start_dt = interval["start_dt"]
        end_dt = interval["end_dt"]

        # Fetch items with pagination
        collected = []
        page = 1
        more_pages = True

        while more_pages:
            url = self._build_url(
                repo,
                item_type,
                page,
                normalized_start,
                normalized_end)
            payload, error = self._request_json(url)

            if error:
                entry = self._build_collection_entry(
                    [], normalized_start, normalized_end, error)
                cache[cache_key] = entry
                return entry

            if not payload:
                break

            if not isinstance(payload, list):
                entry = self._build_collection_entry(
                    [],
                    normalized_start,
                    normalized_end,
                    f"unexpected response payload for {item_type}")
                cache[cache_key] = entry
                return entry

            # Process items
            finished = self.process_items(
                payload, item_type, start_dt, end_dt, collected
            )

            more_pages = not finished and len(payload) >= 100
            if more_pages:
                page += 1

        # Build final entry
        error_msg = f"no {item_type} between timestamps" if not collected else None
        entry = self._build_collection_entry(
            collected, normalized_start, normalized_end, error_msg)
        cache[cache_key] = entry
        return entry

    # Original API methods delegate to the generic method
    def _get_releases_between(
        self,
        repo: str,
        start_timestamp: Optional[Any],
        end_timestamp: Optional[Any],
    ) -> Dict[str, Any]:
        return self._get_items_between(
            repo, start_timestamp, end_timestamp, 'releases')

    def _get_commits_between(
        self,
        repo: str,
        start_timestamp: Optional[Any],
        end_timestamp: Optional[Any],
    ) -> Dict[str, Any]:
        return self._get_items_between(
            repo, start_timestamp, end_timestamp, 'commits')

    def get_change_context(
        self,
        previous_timestamp: Optional[Any],
        current_timestamp: Optional[Any],
        previous_version: Optional[str] = None,
        current_version: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fetches GH context w.r.t changepoints"""
        if not self.repositories:
            return None

        normalized_previous = self._normalize_timestamp(previous_timestamp)
        normalized_current = self._normalize_timestamp(current_timestamp)
        cache_key = (
            normalized_previous or "",
            normalized_current or "",
            previous_version or "",
            current_version or "",
        )
        if cache_key in self._context_cache:
            return self._context_cache[cache_key]

        context: Dict[str, Any] = {
            "previous_timestamp": normalized_previous,
            "current_timestamp": normalized_current,
            "previous_version": previous_version,
            "current_version": current_version,
            "repositories": {},
        }

        for repo in self.repositories:
            if "/" not in repo:
                reason = f"invalid repository format '{repo}', expected owner/repo"
                context["repositories"][repo] = {
                    "releases": self._build_collection_entry(
                        [], normalized_previous, normalized_current, reason
                    ),
                    "commits": self._build_collection_entry(
                        [], normalized_previous, normalized_current, reason
                    ),
                }
                continue

            releases_entry = self._get_releases_between(
                repo, previous_timestamp, current_timestamp
            )
            commits_entry = self._get_commits_between(
                repo, previous_timestamp, current_timestamp
            )
            context["repositories"][repo] = {
                "releases": releases_entry,
                "commits": commits_entry,
            }

        if not context["repositories"]:
            self._context_cache[cache_key] = None
            return None

        self._context_cache[cache_key] = context
        return context

    def get_pr_creation_date(
        self,
        organization: str,
        repository: str,
        pr_number: int,
    ) -> Optional[datetime]:
        """
        Returns the creation date of a PR.

        Args:
            organization: The GitHub organization/owner name
            repository: The repository name
            pr_number: The pull request number

        Returns:
            The creation date as a datetime object in UTC, or None if the PR
            cannot be found or an error occurs.
        """
        repo = f"{organization}/{repository}"

        url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
        payload, error = self._request_json(url)

        if error or not payload:
            self.logger.warning(
                "Failed to fetch PR #%d from %s: %s",
                pr_number,
                repo,
                error or "empty response",
            )
            return None

        created_at_str = payload.get("created_at")
        if not created_at_str:
            self.logger.warning(
                "PR #%d from %s does not have a created_at field",
                pr_number,
                repo,
            )
            return None

        creation_date = self._parse_iso_datetime(created_at_str)
        return creation_date
