"""GitHub scanner — extract commits, issues, and branches from GitHub repos.

Authenticates with PAT (stored in ~/.iuxis/github.token), uses GitHub REST API,
and writes activity to user_knowledge as source='github', category='github_activity'.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from pathlib import Path

import requests

from iuxis.db import get_connection
from iuxis.knowledge_manager import add_knowledge

logger = logging.getLogger("iuxis.github_scanner")

GITHUB_API_BASE = "https://api.github.com"
TOKEN_PATH = Path.home() / ".iuxis" / "github.token"


def get_github_token() -> Optional[str]:
    """Read GitHub PAT from ~/.iuxis/github.token."""
    try:
        if TOKEN_PATH.exists():
            return TOKEN_PATH.read_text().strip()
    except Exception as e:
        logger.error(f"Failed to read GitHub token: {e}")
    return None


def save_github_token(token: str):
    """Save GitHub PAT to ~/.iuxis/github.token."""
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(token.strip())
    TOKEN_PATH.chmod(0o600)  # Restrict to user read/write only
    logger.info("GitHub token saved to ~/.iuxis/github.token")


def test_github_connection() -> Dict[str, any]:
    """Test GitHub API connection and return user info."""
    token = get_github_token()
    if not token:
        return {"success": False, "error": "No GitHub token found"}

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        response = requests.get(f"{GITHUB_API_BASE}/user", headers=headers, timeout=10)
        response.raise_for_status()
        user = response.json()
        return {
            "success": True,
            "username": user.get("login"),
            "name": user.get("name"),
            "email": user.get("email"),
        }
    except requests.exceptions.RequestException as e:
        logger.error(f"GitHub connection test failed: {e}")
        return {"success": False, "error": str(e)}


def _make_github_request(endpoint: str, params: Optional[Dict] = None) -> Optional[List[Dict]]:
    """Make authenticated GitHub API request."""
    token = get_github_token()
    if not token:
        logger.error("No GitHub token available")
        return None

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        url = f"{GITHUB_API_BASE}/{endpoint}"
        response = requests.get(url, headers=headers, params=params or {}, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"GitHub API request failed ({endpoint}): {e}")
        return None


def scan_commits(repo: str, project_id: int, since_date: Optional[datetime] = None) -> int:
    """Scan commits from a GitHub repository and write to knowledge base.

    Args:
        repo: Full repo name (e.g., 'owner/repo')
        project_id: Project ID to associate with
        since_date: Only fetch commits after this date

    Returns:
        Number of commits ingested
    """
    params = {}
    if since_date:
        params["since"] = since_date.isoformat()

    commits = _make_github_request(f"repos/{repo}/commits", params)
    if not commits:
        return 0

    count = 0
    for commit in commits:
        commit_data = commit.get("commit", {})
        author = commit_data.get("author", {})
        message = commit_data.get("message", "")
        sha = commit.get("sha", "")[:7]
        commit_url = commit.get("html_url", "")

        # Skip merge commits
        if message.lower().startswith("merge"):
            continue

        # Format as knowledge entry
        content = f"Commit {sha} by {author.get('name', 'unknown')} in {repo}: {message.split(chr(10))[0]}"
        if commit_url:
            content += f" [{commit_url}]"

        try:
            add_knowledge(
                category="github_activity",
                content=content,
                source="github",
                project_id=project_id,
                source_file=f"{repo}/commit/{sha}",
                confidence="high",
                status="approved",
            )
            count += 1
        except Exception as e:
            logger.warning(f"Failed to add commit {sha}: {e}")

    logger.info(f"Ingested {count} commits from {repo}")
    return count


def scan_issues(repo: str, project_id: int, since_date: Optional[datetime] = None) -> int:
    """Scan issues/PRs from a GitHub repository and write to knowledge base.

    Args:
        repo: Full repo name (e.g., 'owner/repo')
        project_id: Project ID to associate with
        since_date: Only fetch issues updated after this date

    Returns:
        Number of issues ingested
    """
    params = {"state": "all", "sort": "updated", "direction": "desc"}
    if since_date:
        params["since"] = since_date.isoformat()

    issues = _make_github_request(f"repos/{repo}/issues", params)
    if not issues:
        return 0

    count = 0
    for issue in issues:
        number = issue.get("number")
        title = issue.get("title", "")
        state = issue.get("state", "")
        is_pr = "pull_request" in issue
        issue_type = "PR" if is_pr else "issue"
        issue_url = issue.get("html_url", "")

        # Format as knowledge entry
        content = f"GitHub {issue_type} #{number} in {repo} ({state}): {title}"
        if issue_url:
            content += f" [{issue_url}]"

        try:
            add_knowledge(
                category="github_activity",
                content=content,
                source="github",
                project_id=project_id,
                source_file=f"{repo}/issues/{number}",
                confidence="high",
                status="approved",
            )
            count += 1
        except Exception as e:
            logger.warning(f"Failed to add issue #{number}: {e}")

    logger.info(f"Ingested {count} issues/PRs from {repo}")
    return count


def scan_branches(repo: str, project_id: int) -> int:
    """Scan branches from a GitHub repository and write to knowledge base.

    Args:
        repo: Full repo name (e.g., 'owner/repo')
        project_id: Project ID to associate with

    Returns:
        Number of branches ingested
    """
    branches = _make_github_request(f"repos/{repo}/branches")
    if not branches:
        return 0

    count = 0
    for branch in branches:
        name = branch.get("name", "")
        protected = branch.get("protected", False)

        # Only record non-default branches or protected branches
        if name not in ["main", "master"] or protected:
            content = f"Branch '{name}' in {repo}"
            if protected:
                content += " (protected)"

            try:
                add_knowledge(
                    category="github_activity",
                    content=content,
                    source="github",
                    project_id=project_id,
                    source_file=f"{repo}/branch/{name}",
                    confidence="medium",
                    status="approved",
                )
                count += 1
            except Exception as e:
                logger.warning(f"Failed to add branch {name}: {e}")

    logger.info(f"Ingested {count} branches from {repo}")
    return count


def scan_repository(project_id: int, repo: str, backfill_days: int = 60) -> Dict[str, int]:
    """Full scan of a GitHub repository.

    Args:
        project_id: Project ID to associate with
        repo: Full repo name (e.g., 'owner/repo')
        backfill_days: How many days of history to fetch

    Returns:
        Dict with counts of commits, issues, branches ingested
    """
    conn = get_connection()

    # Check if backfill already done
    row = conn.execute(
        "SELECT github_last_scanned, github_backfill_done FROM projects WHERE id = ?",
        (project_id,)
    ).fetchone()

    if not row:
        logger.error(f"Project {project_id} not found")
        return {"commits": 0, "issues": 0, "branches": 0}

    last_scanned, backfill_done = row

    # Determine since_date
    if backfill_done and last_scanned:
        # Incremental scan — only fetch since last scan
        since_date = datetime.fromisoformat(last_scanned)
        logger.info(f"Incremental scan for {repo} since {since_date}")
    else:
        # Initial backfill
        since_date = datetime.now() - timedelta(days=backfill_days)
        logger.info(f"Backfill scan for {repo} from {since_date}")

    # Scan all sources
    commits_count = scan_commits(repo, project_id, since_date)
    issues_count = scan_issues(repo, project_id, since_date)
    branches_count = scan_branches(repo, project_id)

    # Update project metadata
    conn.execute(
        """UPDATE projects
           SET github_last_scanned = CURRENT_TIMESTAMP,
               github_backfill_done = 1
           WHERE id = ?""",
        (project_id,)
    )
    conn.commit()

    logger.info(
        f"Scan complete for {repo}: "
        f"{commits_count} commits, {issues_count} issues, {branches_count} branches"
    )

    return {
        "commits": commits_count,
        "issues": issues_count,
        "branches": branches_count,
    }


def get_scan_status() -> Dict[str, any]:
    """Get GitHub scan status for all projects with GitHub repos configured."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, name, github_repo, github_last_scanned, github_backfill_done
        FROM projects
        WHERE github_repo IS NOT NULL
        ORDER BY github_last_scanned DESC NULLS LAST
    """).fetchall()

    token_available = get_github_token() is not None

    projects = []
    for row in rows:
        last_scanned = row[3]
        staleness = None
        if last_scanned:
            last_scanned_dt = datetime.fromisoformat(last_scanned)
            hours_ago = (datetime.now() - last_scanned_dt).total_seconds() / 3600
            staleness = "fresh" if hours_ago < 24 else "stale" if hours_ago < 72 else "very_stale"

        projects.append({
            "id": row[0],
            "name": row[1],
            "repo": row[2],
            "last_scanned": last_scanned,
            "backfill_done": bool(row[4]),
            "staleness": staleness,
        })

    return {
        "token_available": token_available,
        "projects": projects,
    }
