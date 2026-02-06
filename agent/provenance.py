"""
Source file provenance tracking for generated documentation.

Tracks which source files a generated document references and computes
content hashes for change detection. Used by the version priority engine
to skip regeneration when source files haven't changed.
"""

import hashlib
import logging
import re
from pathlib import Path

from prompts import FILE_HASH_LENGTH

logger = logging.getLogger("isocrates.agent.provenance")


class ProvenanceTracker:
    """Tracks source file references and content hashes for generated docs.

    Responsibilities:
      - Extract file paths referenced in markdown content
      - Compute SHA-256 hashes of source files for change detection
      - Filter references to files that actually exist in the repo

    Args:
        repo_path: Absolute path to the repository root.
    """

    def __init__(self, repo_path: Path) -> None:
        self.repo_path = repo_path

    def extract_source_references(
        self, content: str, key_files: list[str] | None = None
    ) -> list[str]:
        """Extract source file paths referenced in generated documentation.

        Looks for:
          - Code block annotations: ```python title="path/to/file.py"
          - Inline file references: `path/to/file.py`
          - key_files_to_read from the doc spec (planner-directed)

        Args:
            content: Markdown content of the generated document.
            key_files: Optional list of key files from the planner spec.

        Returns:
            Sorted list of unique relative file paths that exist in the repo.
        """
        refs: set[str] = set()

        # key_files_to_read from the planner spec
        if key_files:
            refs.update(key_files)

        # Code block title annotations
        for match in re.finditer(r'```\w*\s+title="([^"]+)"', content):
            refs.add(match.group(1))

        # Inline code that looks like file paths (must contain / or end with known ext)
        for match in re.finditer(r'`([^`]+\.\w{1,4})`', content):
            candidate = match.group(1)
            if "/" in candidate or candidate.endswith(
                (".py", ".ts", ".tsx", ".js", ".go", ".rs")
            ):
                # Skip things that look like code, not paths
                if " " not in candidate and not candidate.startswith(("http", "/")):
                    refs.add(candidate)

        # Filter to files that actually exist in the repo
        valid_refs = []
        for ref in refs:
            if (self.repo_path / ref).exists():
                valid_refs.append(ref)

        return sorted(valid_refs)

    def compute_source_hashes(self, file_paths: list[str]) -> dict[str, str]:
        """Compute SHA-256 hashes of source files for change detection.

        Args:
            file_paths: Relative paths within self.repo_path.

        Returns:
            Dict mapping relative_path to sha256 hex prefix (FILE_HASH_LENGTH chars).
        """
        hashes: dict[str, str] = {}
        for fpath in file_paths:
            full = self.repo_path / fpath
            if not full.exists():
                continue
            try:
                content = full.read_bytes()
                hashes[fpath] = hashlib.sha256(content).hexdigest()[:FILE_HASH_LENGTH]
            except OSError:
                logger.debug("Could not hash file: %s", fpath)
        return hashes
