"""
Git repository change detection utilities.

Provides functions to detect and quantify repository changes
for intelligent documentation regeneration.
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger("isocrates.agent")


def get_commit_count_since(repo_path: Path, since_sha: str) -> Optional[int]:
    """
    Count commits between since_sha and HEAD.

    Args:
        repo_path: Path to the git repository
        since_sha: Starting commit SHA (exclusive)

    Returns:
        Number of commits, or None if comparison fails
    """
    try:
        # Check if since_sha exists in the repo
        check_sha = subprocess.run(
            ["git", "cat-file", "-e", since_sha],
            cwd=repo_path,
            capture_output=True
        )

        if check_sha.returncode != 0:
            # SHA doesn't exist (maybe repo was rebased or force-pushed)
            return None

        # Count commits between since_sha and HEAD
        result = subprocess.run(
            ["git", "rev-list", "--count", f"{since_sha}..HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )

        count = int(result.stdout.strip())
        return count

    except (subprocess.CalledProcessError, ValueError) as e:
        logger.error("[RepoMonitor] Failed to count commits: %s", e)
        return None


def has_significant_changes(
    repo_path: Path,
    since_sha: str,
    threshold: int = 5
) -> bool:
    """
    Check if repository has significant changes since a commit.

    Args:
        repo_path: Path to the git repository
        since_sha: Starting commit SHA
        threshold: Minimum number of commits considered "significant"

    Returns:
        True if changes are significant, False otherwise
    """
    commit_count = get_commit_count_since(repo_path, since_sha)

    if commit_count is None:
        # Can't determine - assume significant to trigger regeneration
        logger.info("[RepoMonitor] Cannot compare to commit %s, assuming significant changes", since_sha[:8])
        return True

    if commit_count >= threshold:
        logger.info("[RepoMonitor] Significant changes detected: %s commits since %s", commit_count, since_sha[:8])
        return True
    else:
        logger.info("[RepoMonitor] Minor changes: %s commits since %s (threshold: %s)", commit_count, since_sha[:8], threshold)
        return False


def get_repo_unchanged_status(repo_path: Path, last_sha: str) -> tuple[bool, str]:
    """
    Check if repository is unchanged since last_sha.

    Args:
        repo_path: Path to the git repository
        last_sha: Last documented commit SHA

    Returns:
        Tuple of (is_unchanged: bool, reason: str)
    """
    try:
        # Get current commit
        current_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        current_sha = current_result.stdout.strip()

        # Check if SHAs match
        if current_sha == last_sha:
            return True, f"Repository unchanged (still at {current_sha[:8]})"

        # Different SHAs - repo has changed
        commit_count = get_commit_count_since(repo_path, last_sha)

        if commit_count is None:
            return False, f"Repository history changed (cannot compare {last_sha[:8]} to {current_sha[:8]})"

        return False, f"Repository changed: {commit_count} new commits since {last_sha[:8]}"

    except subprocess.CalledProcessError as e:
        logger.error("[RepoMonitor] Error checking repo status: %s", e)
        return False, "Repository status unknown"
