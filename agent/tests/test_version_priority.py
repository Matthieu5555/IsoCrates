"""Tests for the version priority decision engine.

Tests the decision logic via should_regenerate() and should_regenerate_targeted()
with mocked API responses. No network calls.
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from version_priority import VersionPriorityEngine


@pytest.fixture
def mock_api():
    return MagicMock()


@pytest.fixture
def engine(mock_api, tmp_path):
    return VersionPriorityEngine(api_client=mock_api, repo_path=tmp_path)


def _make_version(author_type: str = "ai", days_ago: int = 0,
                  commit_sha: str = "abc123", source_hashes: dict | None = None) -> dict:
    """Build a mock version dict."""
    created = datetime.now(timezone.utc) - timedelta(days=days_ago)
    meta = {"repo_commit_sha": commit_sha}
    if source_hashes is not None:
        meta["source_hashes"] = source_hashes
    return {
        "author_type": author_type,
        "created_at": created.isoformat(),
        "author_metadata": meta,
    }


# ---------------------------------------------------------------------------
# Rule 1: No existing doc → GENERATE
# ---------------------------------------------------------------------------


class TestNoExistingDoc:
    def test_no_document_returns_generate(self, engine, mock_api):
        mock_api.get_document.return_value = None
        should, reason = engine.should_regenerate("doc-1", "sha-current")
        assert should is True
        assert "No existing document" in reason

    def test_empty_content_returns_generate(self, engine, mock_api):
        mock_api.get_document.return_value = {"content": ""}
        should, reason = engine.should_regenerate("doc-1", "sha-current")
        assert should is True
        assert "empty" in reason.lower()

    def test_no_versions_returns_generate(self, engine, mock_api):
        mock_api.get_document.return_value = {"content": "some content"}
        mock_api.get_document_versions.return_value = []
        should, reason = engine.should_regenerate("doc-1", "sha-current")
        assert should is True


# ---------------------------------------------------------------------------
# Rule 2: Human edit < 7 days → SKIP
# ---------------------------------------------------------------------------


class TestRecentHumanEdit:
    def test_human_edit_1_day_ago_skips(self, engine, mock_api):
        mock_api.get_document.return_value = {"content": "content"}
        mock_api.get_document_versions.return_value = [
            _make_version("human", days_ago=1, commit_sha="old-sha"),
        ]
        with patch("version_priority.get_repo_unchanged_status", return_value=(False, "changed")):
            should, reason = engine.should_regenerate("doc-1", "new-sha")
        assert should is False
        assert "Recent human edit" in reason

    def test_human_edit_6_days_ago_skips(self, engine, mock_api):
        mock_api.get_document.return_value = {"content": "content"}
        mock_api.get_document_versions.return_value = [
            _make_version("human", days_ago=6, commit_sha="old-sha"),
        ]
        with patch("version_priority.get_repo_unchanged_status", return_value=(True, "unchanged")):
            should, reason = engine.should_regenerate("doc-1", "sha")
        assert should is False


# ---------------------------------------------------------------------------
# Rules 3-5: Human edit >= 7 days
# ---------------------------------------------------------------------------


class TestOlderHumanEdit:
    def test_human_edit_old_repo_unchanged_skips(self, engine, mock_api):
        """Rule 3: Human edit >= 7 days, repo unchanged → SKIP."""
        mock_api.get_document.return_value = {"content": "content"}
        mock_api.get_document_versions.return_value = [
            _make_version("human", days_ago=14, commit_sha="same-sha"),
        ]
        with patch("version_priority.get_repo_unchanged_status", return_value=(True, "unchanged")):
            should, reason = engine.should_regenerate("doc-1", "same-sha")
        assert should is False
        assert "unchanged" in reason.lower()

    def test_human_edit_old_minor_changes_skips(self, engine, mock_api):
        """Rule 4: Human edit >= 7 days, minor changes → SKIP."""
        mock_api.get_document.return_value = {"content": "content"}
        mock_api.get_document_versions.return_value = [
            _make_version("human", days_ago=14, commit_sha="old-sha"),
        ]
        with (
            patch("version_priority.get_repo_unchanged_status", return_value=(False, "changed")),
            patch("version_priority.has_significant_changes", return_value=False),
        ):
            should, reason = engine.should_regenerate("doc-1", "new-sha")
        assert should is False
        assert "minor" in reason.lower()

    def test_human_edit_old_major_changes_regenerates(self, engine, mock_api):
        """Rule 5: Human edit >= 7 days, major changes → REGENERATE."""
        mock_api.get_document.return_value = {"content": "content"}
        mock_api.get_document_versions.return_value = [
            _make_version("human", days_ago=14, commit_sha="old-sha"),
        ]
        with (
            patch("version_priority.get_repo_unchanged_status", return_value=(False, "changed")),
            patch("version_priority.has_significant_changes", return_value=True),
        ):
            should, reason = engine.should_regenerate("doc-1", "new-sha")
        assert should is True
        assert "significant" in reason.lower()


# ---------------------------------------------------------------------------
# Rules 6-7: AI-authored versions
# ---------------------------------------------------------------------------


class TestAIVersion:
    def test_fresh_ai_doc_repo_unchanged_skips(self, engine, mock_api):
        """Rule 6: AI doc < 30 days AND repo unchanged → SKIP."""
        mock_api.get_document.return_value = {"content": "content"}
        mock_api.get_document_versions.return_value = [
            _make_version("ai", days_ago=10, commit_sha="same-sha"),
        ]
        with patch("version_priority.get_repo_unchanged_status", return_value=(True, "unchanged")):
            should, reason = engine.should_regenerate("doc-1", "same-sha")
        assert should is False
        assert "fresh" in reason.lower()

    def test_stale_ai_doc_regenerates(self, engine, mock_api):
        """Rule 7: AI doc >= 30 days → REGENERATE."""
        mock_api.get_document.return_value = {"content": "content"}
        mock_api.get_document_versions.return_value = [
            _make_version("ai", days_ago=31, commit_sha="same-sha"),
        ]
        with patch("version_priority.get_repo_unchanged_status", return_value=(True, "unchanged")):
            should, reason = engine.should_regenerate("doc-1", "same-sha")
        assert should is True
        assert "stale" in reason.lower()

    def test_ai_doc_repo_changed_regenerates(self, engine, mock_api):
        """Rule 7: repo changed → REGENERATE even if doc is fresh."""
        mock_api.get_document.return_value = {"content": "content"}
        mock_api.get_document_versions.return_value = [
            _make_version("ai", days_ago=5, commit_sha="old-sha"),
        ]
        with patch("version_priority.get_repo_unchanged_status", return_value=(False, "changed")):
            should, reason = engine.should_regenerate("doc-1", "new-sha")
        assert should is True
        assert "changed" in reason.lower()


# ---------------------------------------------------------------------------
# Targeted regeneration (source hash comparison)
# ---------------------------------------------------------------------------


class TestTargetedRegeneration:
    def test_no_source_hashes_regenerates(self, engine, mock_api):
        should, reason, changed = engine.should_regenerate_targeted("doc-1", {})
        assert should is True

    def test_no_versions_regenerates(self, engine, mock_api):
        mock_api.get_document_versions.return_value = []
        should, reason, changed = engine.should_regenerate_targeted(
            "doc-1", {"main.py": "abc123"}
        )
        assert should is True

    def test_unchanged_files_skip(self, engine, mock_api):
        mock_api.get_document_versions.return_value = [
            _make_version(source_hashes={"main.py": "abc123", "utils.py": "def456"}),
        ]
        should, reason, changed = engine.should_regenerate_targeted(
            "doc-1", {"main.py": "abc123", "utils.py": "def456"}
        )
        assert should is False
        assert len(changed) == 0

    def test_changed_file_triggers_regeneration(self, engine, mock_api):
        mock_api.get_document_versions.return_value = [
            _make_version(source_hashes={"main.py": "abc123"}),
        ]
        should, reason, changed = engine.should_regenerate_targeted(
            "doc-1", {"main.py": "DIFFERENT"}
        )
        assert should is True
        assert "main.py" in changed

    def test_new_file_triggers_regeneration(self, engine, mock_api):
        mock_api.get_document_versions.return_value = [
            _make_version(source_hashes={"main.py": "abc123"}),
        ]
        should, reason, changed = engine.should_regenerate_targeted(
            "doc-1", {"main.py": "abc123", "new_file.py": "xyz789"}
        )
        assert should is True
        assert "new_file.py" in changed

    def test_legacy_doc_without_hashes_regenerates(self, engine, mock_api):
        mock_api.get_document_versions.return_value = [
            _make_version(source_hashes=None),
        ]
        # source_hashes key won't exist in author_metadata
        should, reason, changed = engine.should_regenerate_targeted(
            "doc-1", {"main.py": "abc123"}
        )
        assert should is True
        assert "legacy" in reason.lower()
