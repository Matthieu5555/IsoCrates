"""Content processing utilities - deep helper module."""

CONTENT_PREVIEW_LENGTH = 500
"""
Maximum length of content preview.

Rationale: 500 chars is ~3-4 sentences, enough for meaningful preview,
small enough to keep responses fast. Changing this value affects all
document list views and metadata displays.
"""


def generate_content_preview(content: str) -> str:
    """
    Generate preview excerpt from content.

    DEEP MODULE: Hides preview generation logic.
    Future: could enhance to break at sentence boundary, strip markdown, etc.

    Args:
        content: The full document content

    Returns:
        Preview string (truncated if necessary)
    """
    if len(content) <= CONTENT_PREVIEW_LENGTH:
        return content
    return content[:CONTENT_PREVIEW_LENGTH]
