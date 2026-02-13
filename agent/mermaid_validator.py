"""Mermaid diagram syntax validation via Node.js subprocess.

Extracts ```mermaid blocks from markdown content and validates each one
using the real mermaid parser (mermaid.parse()). Requires Node.js and
the mermaid package — uses the frontend's node_modules if available.

If Node.js or mermaid aren't available, validation is skipped with a
logged warning. This is a best-effort check, not a hard gate.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("isocrates.agent")

# Regex to extract ```mermaid ... ``` blocks with their line numbers.
# Captures the content between the fences (group 1).
_MERMAID_BLOCK_RE = re.compile(
    r"^```mermaid\s*\n(.*?)^```",
    re.MULTILINE | re.DOTALL,
)

# Embedded Node.js ESM script that validates mermaid blocks.
# Reads JSON array of {index, source} from stdin, writes JSON array of
# {index, error} to stdout for blocks that fail to parse.
_VALIDATE_SCRIPT = """\
import mermaid from 'mermaid';

// 'loose' avoids DOMPurify dependency — Node.js has no DOM, so 'strict'
// produces false positives ("DOMPurify.addHook is not a function") that
// mask real parse errors. Content is trusted (our own agent output).
mermaid.initialize({ startOnLoad: false, securityLevel: 'loose' });

const input = await new Promise(resolve => {
    let data = '';
    process.stdin.on('data', chunk => data += chunk);
    process.stdin.on('end', () => resolve(data));
});

const blocks = JSON.parse(input);
const errors = [];

for (const block of blocks) {
    try {
        await mermaid.parse(block.source.trim());
    } catch (e) {
        const msg = e.message || String(e);
        // Categorize: DOMPurify/DOM errors are runtime environment issues,
        // not diagram syntax problems. Flag them so callers can distinguish.
        const category = (msg.includes('DOMPurify') || msg.includes('document is not defined'))
            ? 'runtime'
            : 'parse';
        errors.push({ index: block.index, error: msg, category });
    }
}

process.stdout.write(JSON.stringify(errors));
"""


@dataclass(frozen=True)
class MermaidError:
    """A single mermaid block that failed syntax validation."""

    block_index: int   # 0-based index among all mermaid blocks in the document
    line_number: int   # 1-based line number where the block starts in the markdown
    source: str        # the raw mermaid source (without fences)
    error: str         # parse error message from mermaid
    category: str = "parse"  # "parse" = real syntax error, "runtime" = Node.js environment issue


def extract_mermaid_blocks(content: str) -> list[tuple[int, str]]:
    """Extract all mermaid blocks from markdown content.

    Returns:
        List of (line_number, source) tuples. line_number is 1-based,
        source is the content between the ``` fences.
    """
    results: list[tuple[int, str]] = []
    for match in _MERMAID_BLOCK_RE.finditer(content):
        # Count newlines before the match to get the line number
        line_number = content[:match.start()].count("\n") + 1
        results.append((line_number, match.group(1)))
    return results


def _find_node() -> str | None:
    """Find the node binary, or None if unavailable."""
    return shutil.which("node")


def _resolve_frontend_dir() -> Path | None:
    """Try to find the frontend directory with mermaid installed.

    Checks relative to this file's location (agent/ is a sibling of frontend/).
    """
    agent_dir = Path(__file__).resolve().parent
    frontend = agent_dir.parent / "frontend"
    if (frontend / "node_modules" / "mermaid").is_dir():
        return frontend
    return None


def validate_mermaid_blocks(
    content: str,
    frontend_dir: str | Path | None = None,
) -> list[MermaidError]:
    """Validate all mermaid blocks in markdown content.

    Uses Node.js with the mermaid package for real syntax validation.
    Returns a list of MermaidError for blocks that fail to parse.
    Returns empty list if all blocks are valid or if validation cannot run.

    Args:
        content: Full markdown document content.
        frontend_dir: Path to the frontend directory containing node_modules/mermaid.
            If None, auto-detected from this file's location.
    """
    blocks = extract_mermaid_blocks(content)
    if not blocks:
        return []

    node_bin = _find_node()
    if not node_bin:
        logger.warning("[Mermaid] Skipping validation: node not found in PATH")
        return []

    # Resolve frontend dir for mermaid package
    if frontend_dir is None:
        resolved = _resolve_frontend_dir()
    else:
        resolved = Path(frontend_dir)

    if resolved is None or not (resolved / "node_modules" / "mermaid").is_dir():
        logger.warning("[Mermaid] Skipping validation: mermaid package not found in %s", resolved)
        return []

    # Build input JSON for the validation script
    script_input = json.dumps([
        {"index": i, "source": source}
        for i, (_, source) in enumerate(blocks)
    ])

    # Write the validation script to a temp file inside the frontend directory
    # so Node ESM resolves the mermaid import from frontend/node_modules (ESM
    # uses the script's location for package resolution, not cwd).
    import tempfile
    script_path = None
    try:
        fd, script_path = tempfile.mkstemp(
            suffix=".mjs", prefix=".mermaid_validate_", dir=str(resolved)
        )
        with os.fdopen(fd, "w") as f:
            f.write(_VALIDATE_SCRIPT)

        result = subprocess.run(
            [node_bin, script_path],
            input=script_input,
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "NODE_NO_WARNINGS": "1"},
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            logger.warning("[Mermaid] Validation script failed (exit %d): %s", result.returncode, stderr[:500])
            return []

        raw_errors = json.loads(result.stdout)

    except subprocess.TimeoutExpired:
        logger.warning("[Mermaid] Validation timed out after 30s")
        return []
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("[Mermaid] Validation failed: %s", e)
        return []
    finally:
        if script_path:
            try:
                os.unlink(script_path)
            except OSError:
                pass

    # Map raw errors back to MermaidError with line numbers and source.
    # Runtime errors (DOMPurify, missing DOM) are logged but filtered out —
    # they're Node.js environment issues, not diagram problems.
    errors: list[MermaidError] = []
    for err in raw_errors:
        idx = err["index"]
        category = err.get("category", "parse")
        if 0 <= idx < len(blocks):
            line_number, source = blocks[idx]
            if category == "runtime":
                logger.debug(
                    "[Mermaid] Block %d (line %d): runtime error ignored: %s",
                    idx, line_number, err["error"][:200],
                )
                continue
            errors.append(MermaidError(
                block_index=idx,
                line_number=line_number,
                source=source.strip(),
                error=err["error"],
                category=category,
            ))

    return errors


def format_errors_for_prompt(errors: list[MermaidError]) -> str:
    """Format validation errors into a string suitable for an LLM fix prompt."""
    parts: list[str] = []
    for err in errors:
        # Truncate very long sources to keep the prompt focused
        source_preview = err.source[:500]
        if len(err.source) > 500:
            source_preview += "\n... [truncated]"
        parts.append(
            f"### Diagram {err.block_index + 1} (line {err.line_number})\n"
            f"**Error:** {err.error}\n"
            f"**Source:**\n```\n{source_preview}\n```"
        )
    return "\n\n".join(parts)
