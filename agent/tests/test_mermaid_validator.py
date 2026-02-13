"""Tests for mermaid block extraction and error formatting.

Tests the pure functions: extract_mermaid_blocks() and format_errors_for_prompt().
Validation itself requires Node.js so we test the extraction pipeline separately.
"""

import pytest

from mermaid_validator import (
    MermaidError,
    extract_mermaid_blocks,
    format_errors_for_prompt,
)


# ---------------------------------------------------------------------------
# extract_mermaid_blocks
# ---------------------------------------------------------------------------


class TestExtractMermaidBlocks:
    def test_empty_content(self):
        assert extract_mermaid_blocks("") == []

    def test_no_mermaid_blocks(self):
        content = "# Hello\n\nSome text\n\n```python\nprint('hi')\n```\n"
        assert extract_mermaid_blocks(content) == []

    def test_single_block(self):
        content = "# Doc\n\n```mermaid\ngraph TD\n  A-->B\n```\n"
        blocks = extract_mermaid_blocks(content)
        assert len(blocks) == 1
        line_num, source = blocks[0]
        assert line_num == 3  # 1-based, block starts on line 3
        assert "graph TD" in source
        assert "A-->B" in source

    def test_multiple_blocks(self):
        content = (
            "# Doc\n\n"
            "```mermaid\ngraph TD\n  A-->B\n```\n\n"
            "Some text between blocks.\n\n"
            "```mermaid\nsequenceDiagram\n  Alice->>Bob: Hello\n```\n"
        )
        blocks = extract_mermaid_blocks(content)
        assert len(blocks) == 2
        assert "graph TD" in blocks[0][1]
        assert "sequenceDiagram" in blocks[1][1]

    def test_line_numbers_are_correct(self):
        # Line 1: heading, Line 2: blank, Line 3: fence open
        content = "# Heading\n\n```mermaid\ngraph LR\n```\n"
        blocks = extract_mermaid_blocks(content)
        assert blocks[0][0] == 3

    def test_block_at_start_of_file(self):
        content = "```mermaid\ngraph TD\n  A-->B\n```\n"
        blocks = extract_mermaid_blocks(content)
        assert len(blocks) == 1
        assert blocks[0][0] == 1

    def test_non_mermaid_code_blocks_ignored(self):
        content = (
            "```javascript\nconsole.log('hi')\n```\n\n"
            "```mermaid\ngraph TD\n```\n\n"
            "```python\nprint('hi')\n```\n"
        )
        blocks = extract_mermaid_blocks(content)
        assert len(blocks) == 1
        assert "graph TD" in blocks[0][1]

    def test_multiline_complex_diagram(self):
        content = """# Architecture

```mermaid
graph TD
    subgraph Frontend
        A[React App]
        B[API Client]
    end
    subgraph Backend
        C[FastAPI]
        D[Database]
    end
    A --> B
    B --> C
    C --> D
```

More text here.
"""
        blocks = extract_mermaid_blocks(content)
        assert len(blocks) == 1
        source = blocks[0][1]
        assert "subgraph Frontend" in source
        assert "subgraph Backend" in source


# ---------------------------------------------------------------------------
# format_errors_for_prompt
# ---------------------------------------------------------------------------


class TestFormatErrorsForPrompt:
    def test_empty_errors(self):
        assert format_errors_for_prompt([]) == ""

    def test_single_error(self):
        errors = [
            MermaidError(
                block_index=0,
                line_number=5,
                source="graph TD\n  A-->",
                error="Expected node identifier",
            )
        ]
        result = format_errors_for_prompt(errors)
        assert "Diagram 1" in result
        assert "line 5" in result
        assert "Expected node identifier" in result
        assert "graph TD" in result

    def test_multiple_errors(self):
        errors = [
            MermaidError(block_index=0, line_number=3, source="graph TD", error="err1"),
            MermaidError(block_index=1, line_number=15, source="sequenceDiagram", error="err2"),
        ]
        result = format_errors_for_prompt(errors)
        assert "Diagram 1" in result
        assert "Diagram 2" in result
        assert "err1" in result
        assert "err2" in result

    def test_long_source_is_truncated(self):
        long_source = "x" * 1000
        errors = [
            MermaidError(block_index=0, line_number=1, source=long_source, error="err"),
        ]
        result = format_errors_for_prompt(errors)
        assert "[truncated]" in result
        # First 500 chars should be present
        assert "x" * 100 in result
