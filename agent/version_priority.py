"""
Version Priority Engine for intelligent documentation regeneration.

Implements decision logic to respect human edits while keeping
AI-generated documentation fresh.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from api_client import DocumentAPIClient
from repo_monitor import has_significant_changes, get_repo_unchanged_status

logger = logging.getLogger("isocrates.agent")


class VersionPriorityEngine:
    """
    Decision engine for determining when to regenerate documentation.

    Rules:
    1. No existing doc → GENERATE
    2. Human edit < 7 days → SKIP (respect fresh human edits)
    3. Human edit >= 7 days, repo unchanged → SKIP
    4. Human edit >= 7 days, minor changes (< 5 commits) → SKIP
    5. Human edit >= 7 days, major changes (>= 5 commits) → REGENERATE
    6. AI doc < 30 days, repo unchanged → SKIP
    7. AI doc >= 30 days OR repo changed → REGENERATE
    """

    def __init__(self, api_client: DocumentAPIClient, repo_path: Path):
        """
        Initialize priority engine.

        Args:
            api_client: API client for fetching document data
            repo_path: Path to the git repository
        """
        self.api_client = api_client
        self.repo_path = repo_path
        self.human_recent_threshold_days = 7
        self.ai_stale_threshold_days = 30
        self.commit_threshold = 5

    def should_regenerate(
        self,
        doc_id: str,
        current_commit_sha: str
    ) -> tuple[bool, str]:
        """
        Determine if documentation should be regenerated.

        Args:
            doc_id: Document ID
            current_commit_sha: Current commit SHA of the repository

        Returns:
            Tuple of (should_regenerate: bool, reason: str)
        """
        logger.info("[VersionPriority] Checking if regeneration needed...")
        logger.info("   Doc ID: %s", doc_id)
        logger.info("   Current commit: %s", current_commit_sha[:8])

        # Rule 1: Check if document exists
        existing_doc = self.api_client.get_document(doc_id)

        if not existing_doc:
            return True, "No existing document found"

        # Rule 1b: Check if document has actual content (not empty shell from failed generation)
        content = existing_doc.get("content", "")
        if not content or not content.strip():
            return True, "Existing document is empty (failed previous generation)"

        logger.info("   Found existing document")

        # Get version history
        versions = self.api_client.get_document_versions(doc_id)

        if not versions:
            # Document exists but no version history - regenerate to create version
            return True, "Document exists but no version history"

        # Get latest version
        latest_version = versions[0]  # Assuming sorted by created_at desc
        author_type = latest_version.get("author_type", "ai")
        created_at_str = latest_version.get("created_at")

        logger.info("   Latest version author: %s", author_type)
        logger.info("   Latest version created: %s", created_at_str)

        # Parse creation timestamp
        if not created_at_str:
            return True, "No timestamp on latest version, regenerating to be safe"
        try:
            created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
            age_days = (datetime.now(created_at.tzinfo) - created_at).days
        except (ValueError, AttributeError) as e:
            logger.warning("[VersionPriority] Could not parse timestamp: %s", e)
            # Can't determine age - regenerate to be safe
            return True, "Cannot determine document age, regenerating to be safe"

        logger.info("   Document age: %s days", age_days)

        # Get last commit SHA from metadata
        author_metadata = latest_version.get("author_metadata", {})
        last_commit_sha = author_metadata.get("repo_commit_sha", "unknown")

        logger.info("   Last documented commit: %s", last_commit_sha[:8] if last_commit_sha != "unknown" else "unknown")

        # Check repo changes
        if last_commit_sha != "unknown":
            is_unchanged, change_reason = get_repo_unchanged_status(
                self.repo_path,
                last_commit_sha
            )
            logger.info("   Repo status: %s", change_reason)
        else:
            is_unchanged = False
            change_reason = "Previous commit SHA unknown, assuming changes"
            logger.info("   Repo status: %s", change_reason)

        # Apply decision rules based on author type
        if author_type == "human":
            return self._evaluate_human_version(
                age_days,
                is_unchanged,
                last_commit_sha
            )
        else:  # author_type == "ai" or unknown
            return self._evaluate_ai_version(
                age_days,
                is_unchanged,
                last_commit_sha
            )

    def _evaluate_human_version(
        self,
        age_days: int,
        is_unchanged: bool,
        last_commit_sha: str
    ) -> tuple[bool, str]:
        """
        Evaluate whether to regenerate a human-authored version.

        Args:
            age_days: Age of the document in days
            is_unchanged: Whether repository is unchanged
            last_commit_sha: Last documented commit SHA

        Returns:
            Tuple of (should_regenerate: bool, reason: str)
        """
        # Rule 2: Human edit < 7 days → SKIP
        if age_days < self.human_recent_threshold_days:
            return False, f"Recent human edit ({age_days} days old), preserving their work"

        # Human edit >= 7 days
        # Rule 3: Repo unchanged → SKIP
        if is_unchanged:
            return False, f"Human edit is {age_days} days old but repository unchanged, no need to regenerate"

        # Repo has changed - check if changes are significant
        if last_commit_sha == "unknown":
            # Can't determine significance - regenerate with warning
            return True, f"Human edit is {age_days} days old and repository changed (commit SHA unknown), regenerating with note for human review"

        # Rule 4 & 5: Check commit count
        is_significant = has_significant_changes(
            self.repo_path,
            last_commit_sha,
            self.commit_threshold
        )

        if is_significant:
            # Rule 5: Major changes → REGENERATE
            return True, f"Human edit is {age_days} days old and repository has significant changes, regenerating with note for human review"
        else:
            # Rule 4: Minor changes → SKIP
            return False, f"Human edit is {age_days} days old but repository changes are minor, preserving human version"

    def _evaluate_ai_version(
        self,
        age_days: int,
        is_unchanged: bool,
        last_commit_sha: str
    ) -> tuple[bool, str]:
        """
        Evaluate whether to regenerate an AI-authored version.

        Args:
            age_days: Age of the document in days
            is_unchanged: Whether repository is unchanged
            last_commit_sha: Last documented commit SHA

        Returns:
            Tuple of (should_regenerate: bool, reason: str)
        """
        # Rule 6: AI doc < 30 days AND repo unchanged → SKIP
        if age_days < self.ai_stale_threshold_days and is_unchanged:
            return False, f"AI documentation is fresh ({age_days} days old) and repository unchanged"

        # Rule 7: AI doc >= 30 days OR repo changed → REGENERATE
        if age_days >= self.ai_stale_threshold_days:
            return True, f"AI documentation is stale ({age_days} days old), regenerating"

        # Repo must have changed (since we already checked unchanged above)
        return True, f"Repository changed since last AI generation ({age_days} days ago), updating documentation"

    def should_regenerate_targeted(
        self,
        doc_id: str,
        current_source_hashes: dict[str, str],
    ) -> tuple[bool, str, list[str]]:
        """Targeted regeneration: compare stored source file hashes against current.

        This is a faster check than should_regenerate() — it skips version/commit
        analysis and directly checks if the source files a doc was generated from
        have changed.

        Args:
            doc_id: Document ID
            current_source_hashes: {file_path: sha256_hex} computed from current files

        Returns:
            (should_regenerate, reason, changed_files)
        """
        if not current_source_hashes:
            return True, "No source files to check", []

        # Get stored source hashes from latest version
        versions = self.api_client.get_document_versions(doc_id)
        if not versions:
            return True, "No version history", []

        latest = versions[0]
        author_metadata = latest.get("author_metadata", {})
        stored_hashes = author_metadata.get("source_hashes", {})

        if not stored_hashes:
            # Legacy doc without provenance — fall through to commit-level check
            return True, "No stored source hashes (legacy doc)", []

        # Compare hashes
        changed = []
        for fpath, current_hash in current_source_hashes.items():
            stored_hash = stored_hashes.get(fpath)
            if stored_hash != current_hash:
                changed.append(fpath)

        # Check for new files not in stored hashes
        new_files = [f for f in current_source_hashes if f not in stored_hashes]
        changed.extend(new_files)

        if not changed:
            return False, f"All {len(current_source_hashes)} source files unchanged", []

        return True, f"{len(changed)} source file(s) changed: {', '.join(changed[:3])}", changed
