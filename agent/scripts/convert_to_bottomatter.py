#!/usr/bin/env python3
"""
Convert existing docs from frontmatter to bottomatter format.
"""
import logging
import re
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

def convert_document(file_path):
    """Convert a document from frontmatter to bottomatter."""
    content = Path(file_path).read_text()

    # Parse frontmatter
    if not content.startswith("---\n"):
        logger.info("No frontmatter in %s", file_path)
        return

    # Extract frontmatter
    end_match = re.search(r'\n---\n', content[4:])
    if not end_match:
        logger.warning("Malformed frontmatter in %s", file_path)
        return

    end_pos = end_match.end() + 4
    frontmatter_text = content[4:end_pos-4]
    body = content[end_pos:]

    # Parse metadata
    metadata = {}
    for line in frontmatter_text.split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            metadata[key.strip()] = value.strip().strip('"\'')

    # Extract generated_at for header
    generated_at = metadata.get('generated_at', '')
    if generated_at:
        try:
            dt = datetime.fromisoformat(generated_at)
            timestamp = dt.strftime("%d/%m/%Y at %I:%M%p")
        except Exception:
            timestamp = "Unknown Date"
    else:
        timestamp = "Unknown Date"

    # Strip any existing footer
    footer_pattern = r'\n---\n\n\*Documentation.*$'
    body = re.sub(footer_pattern, '', body, flags=re.DOTALL)

    # Build new format: header + body + bottomatter
    header = f"*Documentation Written by IsoCrates on {timestamp}*\n\n"

    # Build bottomatter
    bottomatter_lines = ["\n---"]
    for key in ['id', 'repo_url', 'repo_name', 'doc_type', 'collection', 'generated_at', 'generator', 'version', 'agent', 'model']:
        if key in metadata:
            value = metadata[key]
            if ' ' in value or ':' in value:
                bottomatter_lines.append(f'{key}: "{value}"')
            else:
                bottomatter_lines.append(f'{key}: {value}')
    bottomatter_lines.append("---")

    new_content = header + body.lstrip() + '\n'.join(bottomatter_lines)

    # Write back
    Path(file_path).write_text(new_content)
    logger.info("Converted: %s", file_path)
    logger.info("  Header: %s", timestamp)
    logger.info("  Metadata keys: %s", list(metadata.keys()))

# Convert main docs
for doc_file in ['/notes/DerivativesGPT-client.md', '/notes/DerivativesGPT-softdev.md']:
    if Path(doc_file).exists():
        convert_document(doc_file)

logger.info("Done!")
