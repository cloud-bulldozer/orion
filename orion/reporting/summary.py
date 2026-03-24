"""
Regression summary formatting.

Prints changepoint details: affected metrics, PRs, and GitHub context.
Used by both the normal orion run output and the standalone --report mode.
"""

from tabulate import tabulate


def print_regression_summary(regression_data) -> None:
    """Print regression summary: affected metrics, PRs, and GitHub context tables.

    Args:
        regression_data: list of regression dicts, each with keys:
            - test_name (str)
            - bad_ver (str): version where changepoint was detected
            - prev_ver (str): previous version
            - build_url (str, optional): build URL for the changepoint
            - metrics_with_change (list[dict]): each with name, value, percentage_change, labels
            - prs (list[str]): PR URLs
            - github_context (dict|None): repository commits/releases info
    """
    print("Regression(s) found :")
    for regression in regression_data:
        print("-" * 50)
        print(f"Test: {regression.get('test_name')}:")
        print(f"{'Changepoint at:':<20} {regression['bad_ver']}")
        print(f"{'Previous version:':<20} {regression['prev_ver']}")
        if regression.get("build_url"):
            print(f"{'Build:':<20} {regression['build_url']}")
        print("\nAffected Metrics")
        if regression['metrics_with_change']:
            table = [
                [m['name'], m['value'], f"{m['percentage_change']:.2f}%", m.get('labels', '')]
                for m in regression['metrics_with_change']
            ]
            print(tabulate(
                table,
                headers=["Metric", "Value", "Percentage change", "Labels"],
                tablefmt="outline"
            ))

        prs = regression.get("prs", [])
        if prs:
            components = _extract_components(regression['metrics_with_change'])
            related, other = _sort_prs_by_relevance(prs, components)
            if related:
                print(f"\nRelated PRs ({len(related)}):")
                for pr_url in related:
                    print(f"  * {pr_url}")
            if other:
                print(f"\nOther PRs in payload ({len(other)}):")
                for pr_url in other:
                    print(f"  - {pr_url}")
        else:
            print("\nRelated PRs:")
            print("N/A")

        if "github_context" in regression and regression["github_context"] is not None:
            _print_github_context(regression["github_context"])


def _extract_components(metrics_with_change: list) -> set:
    """Extract component names from metrics labels.

    Parses labels like '[Jira: Networking / ovn-kubernetes]' into
    component names like {'networking', 'ovn-kubernetes'}.
    """
    components = set()
    for metric in metrics_with_change:
        label = metric.get("labels", "")
        if isinstance(label, list):
            label = " ".join(label)
        for part in label.replace("[", "").replace("]", "").split("/"):
            part = part.strip().lower()
            if part and part != "jira:":
                components.add(part)
    return components


def _sort_prs_by_relevance(prs: list, components: set) -> tuple:
    """Split PRs into component-related and others.

    Returns:
        tuple of (matching_prs, other_prs)
    """
    matching, others = [], []
    for pr_url in prs:
        parts = pr_url.rstrip("/").split("/")
        repo_name = parts[-3].lower() if len(parts) >= 4 else ""
        if any(comp in repo_name for comp in components):
            matching.append(pr_url)
        else:
            others.append(pr_url)
    return matching, others


def _print_github_context(ctx: dict) -> None:
    """Print GitHub context: commits and releases per repository."""
    repos = ctx.get("repositories") or None
    if repos is None or len(repos) == 0:
        print("No GitHub context found")
        return
    for repo_name, repo_data in repos.items():
        commits = repo_data.get("commits") or {}
        releases = repo_data.get("releases") or {}
        if (commits.get("count") or 0) > 0 or (releases.get("count") or 0) > 0:
            print(f"\nRepository: {repo_name}")
            rows = []
            for item in (commits.get("items") or []):
                date = item.get("commit_timestamp", "")
                msg = item.get("message", "")
                email = (item.get("commit_author") or {}).get("email", "")
                url = item.get("html_url", "")
                rows.append([date, msg.split("\n")[0], email, url])
            if len(rows) > 0:
                print("Commits:")
                print(tabulate(rows,
                    headers=["Date", "Message", "Author email", "URL"],
                    tablefmt="outline"))
            rows = []
            for item in (releases.get("items") or []):
                date = item.get("published_at") or item.get("timestamp") or item.get("date") or ""
                msg = item.get("body") or item.get("message") or item.get("name") or ""
                email = (item.get("author") or item.get("commit_author") or {})
                if isinstance(email, dict):
                    email = email.get("email", "")
                else:
                    email = str(email)
                url = item.get("html_url", "")
                rows.append([date, msg.split("\n")[0], email, url])
            if len(rows) > 0:
                print("Releases:")
                print(tabulate(rows,
                    headers=["Date", "Message", "Author email", "URL"],
                    tablefmt="outline"))
