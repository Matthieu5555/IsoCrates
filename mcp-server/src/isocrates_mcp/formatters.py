"""Format API responses as markdown for LLM consumption."""


def format_search_results(results: list[dict]) -> str:
    """Format search results as a numbered markdown list."""
    if not results:
        return "No documents found."

    lines = [f"Found {len(results)} result(s):\n"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "Untitled")
        path = r.get("path", "")
        doc_id = r.get("id", "")
        snippet = r.get("snippet") or r.get("content_preview") or ""
        keywords = ", ".join(r.get("keywords", []))

        lines.append(f"### {i}. {title}")
        lines.append(f"- **Path:** {path}")
        lines.append(f"- **ID:** `{doc_id}`")
        if keywords:
            lines.append(f"- **Keywords:** {keywords}")
        if snippet:
            # Truncate long snippets
            text = snippet[:500].rstrip()
            lines.append(f"- **Snippet:** {text}")
        lines.append("")
    return "\n".join(lines)


def format_document(doc: dict) -> str:
    """Format a full document with metadata header and content."""
    title = doc.get("title", "Untitled")
    path = doc.get("path", "")
    doc_id = doc.get("id", "")
    content = doc.get("content", "")
    keywords = ", ".join(doc.get("keywords", []))
    updated = doc.get("updated_at", "")
    doc_type = doc.get("doc_type", "")

    header = [f"# {title}\n"]
    header.append(f"**Path:** {path}  ")
    header.append(f"**ID:** `{doc_id}`  ")
    if doc_type:
        header.append(f"**Type:** {doc_type}  ")
    if keywords:
        header.append(f"**Keywords:** {keywords}  ")
    if updated:
        header.append(f"**Updated:** {updated}  ")
    header.append("\n---\n")
    header.append(content)
    return "\n".join(header)


def format_document_list(docs: list[dict]) -> str:
    """Format a document list with titles, paths, and content previews."""
    if not docs:
        return "No documents found."

    lines = [f"Found {len(docs)} document(s):\n"]
    for i, doc in enumerate(docs, 1):
        title = doc.get("title", "Untitled")
        path = doc.get("path", "")
        doc_id = doc.get("id", "")
        doc_type = doc.get("doc_type", "")
        updated = (doc.get("updated_at") or "")[:10]
        preview = doc.get("content_preview") or ""

        lines.append(f"### {i}. {title}")
        lines.append(f"- **Path:** {path}")
        lines.append(f"- **ID:** `{doc_id}`")
        if doc_type:
            lines.append(f"- **Type:** {doc_type}")
        lines.append(f"- **Updated:** {updated}")
        if preview:
            lines.append(f"- **Preview:** {preview[:200].rstrip()}")
        lines.append("")
    return "\n".join(lines)


def format_related(doc_title: str, deps: dict, title_cache: dict[str, str]) -> str:
    """Format dependency graph as incoming/outgoing wikilinks."""
    outgoing = deps.get("outgoing", [])
    incoming = deps.get("incoming", [])

    lines = [f"## Related documents for \"{doc_title}\"\n"]

    if outgoing:
        lines.append(f"### Links from this document ({len(outgoing)})")
        for dep in outgoing:
            target_id = dep.get("to_doc_id", "")
            link_text = dep.get("link_text", "")
            target_title = title_cache.get(target_id, target_id)
            display = link_text or target_title
            lines.append(f"- [[{display}]] (`{target_id}`)")
        lines.append("")

    if incoming:
        lines.append(f"### Links to this document ({len(incoming)})")
        for dep in incoming:
            source_id = dep.get("from_doc_id", "")
            link_text = dep.get("link_text", "")
            source_title = title_cache.get(source_id, source_id)
            display = source_title or link_text
            lines.append(f"- [[{display}]] (`{source_id}`)")
        lines.append("")

    if not outgoing and not incoming:
        lines.append("No related documents found.")

    return "\n".join(lines)
