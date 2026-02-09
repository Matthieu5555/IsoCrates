"""Planner: Tier 1 reasoning — designs the documentation blueprint.

Reads scout reports and outputs a structured JSON blueprint specifying
what documents to write, their sections, and cross-references.
"""

import json
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any

from prompts import DOCUMENT_TYPES

logger = logging.getLogger("isocrates.agent")


# ---------------------------------------------------------------------------
# Scout → Writer relevance mapping
# ---------------------------------------------------------------------------

SCOUT_RELEVANCE: dict[str, list[str]] = {
    "overview":      ["structure", "architecture"],
    "quickstart":    ["structure", "infra"],
    "architecture":  ["architecture", "structure"],
    "api":           ["api", "architecture"],
    "config":        ["infra", "structure"],
    "guide":         ["api", "architecture", "structure"],
    "data-model":    ["architecture", "api"],
    "component":     ["architecture", "api"],
    "contributing":  ["tests", "structure", "infra"],
    "capabilities":  ["structure", "api", "architecture"],
    "security":      ["api", "architecture"],
    "reference":     ["api", "architecture"],
    "operations":    ["infra", "structure"],
    "runbook":       ["infra", "structure"],
}


def get_relevant_reports(
    doc_type: str,
    reports_by_key: dict[str, str],
) -> str:
    """Return scout reports relevant to *doc_type*, falling back to all."""
    if not reports_by_key:
        return ""
    relevant_keys = SCOUT_RELEVANCE.get(doc_type, list(reports_by_key.keys()))
    parts = []
    for key in relevant_keys:
        if key in reports_by_key:
            parts.append(reports_by_key[key])
    if "structure" not in relevant_keys and "structure" in reports_by_key:
        parts.append(reports_by_key["structure"])
    return "\n\n---\n\n".join(parts) if parts else ""


# ---------------------------------------------------------------------------
# Wikilink sanitization (also reused by writer)
# ---------------------------------------------------------------------------

def sanitize_wikilinks(content: str, valid_titles: set[str], repo_url: str) -> str:
    """Replace invalid [[wikilinks]] with plain text."""
    def _replace(match: re.Match) -> str:
        inner = match.group(1)
        if "|" in inner:
            target, display = inner.split("|", 1)
        else:
            target = display = inner
        target, display = target.strip(), display.strip()
        if target in valid_titles:
            return match.group(0)
        return display

    return re.sub(r'\[\[(.+?)\]\]', _replace, content)


# ---------------------------------------------------------------------------
# DocumentPlanner
# ---------------------------------------------------------------------------

class DocumentPlanner:
    """Tier 1 planner that converts scout reports into a blueprint.

    Requires the planner LLM and SDK message types to be injected.
    """

    def __init__(
        self,
        planner_llm: object,
        repo_name: str,
        crate: str,
        notes_dir: Path,
        # SDK types injected
        message_cls: type,
        text_content_cls: type,
        context_budget: int = 131_072,
    ) -> None:
        self.planner_llm = planner_llm
        self.repo_name = repo_name
        self.crate = crate
        self.notes_dir = notes_dir
        self._Message = message_cls
        self._TextContent = text_content_cls
        self._context_budget = context_budget

    def plan(
        self,
        scout_reports: str,
        existing_docs: list[dict] | None = None,
    ) -> dict:
        """Design a documentation blueprint from scout reports.

        Returns a dict with *repo_summary*, *complexity*, *documents*.
        Falls back to a deterministic plan on failure.
        """
        crate_path = f"{self.crate}{self.repo_name}".rstrip("/")

        doc_types_desc = "\n".join(
            f'  - "{k}": {v["title"]}'
            for k, v in sorted(DOCUMENT_TYPES.items())
        )

        existing_docs_section = ""
        if existing_docs:
            existing_docs_section = """
EXISTING DOCUMENTS (from previous runs):
You MUST reuse these exact titles and paths unless you have a strong reason
to reorganize. Consistency across runs is critical — changing titles or paths
causes duplicate documents. If you need to rename or move a document, include
a "replaces_title" field with the OLD title so the system can update in place.

"""
            for doc in existing_docs:
                existing_docs_section += f'  - title: "{doc["title"]}"\n'
                existing_docs_section += f'    path: "{doc["path"]}"\n'
                existing_docs_section += f'    doc_type: "{doc["doc_type"]}"\n'
            existing_docs_section += "\n"

        planner_prompt = f"""You are a documentation architect designing a WIKI — not a book.

You have received intelligence reports from scouts who explored a codebase.
Design a rich, interconnected documentation wiki with many SHORT focused pages
organized in a logical folder structure.

SCOUT REPORTS:
{scout_reports}

{existing_docs_section}DESIGN PHILOSOPHY:
Think like a human who spent quality time organizing a knowledge base:
- Each page is SHORT: 1-2 printed pages max. If a topic is big, split it.
- Pages are organized in FOLDERS that mirror the project's architecture.
- Pages are DENSELY WIKILINKED — every page references 10-20+ other pages.
- The structure feels like navigating a well-crafted wiki, not reading a PDF.

FOLDER STRUCTURE:
Use the path field to organize pages. The base path is "{crate_path}".
The path is the FOLDER the document lives in — a file named after the title
will be created inside it.

Rules:
- Use folders to GROUP related documents (2+ docs per folder).
- Standalone pages go directly in "{crate_path}" (no subfolder needed).
- Max 2 levels deep. Never create a subfolder that holds only 1 document.

GOOD example:
  "{crate_path}"                    → Overview
  "{crate_path}"                    → Getting Started
  "{crate_path}"                    → Deployment
  "{crate_path}/architecture"       → Architecture Overview
  "{crate_path}/architecture"       → Backend Architecture
  "{crate_path}/architecture"       → Frontend Architecture
  "{crate_path}/architecture"       → Data Model
  "{crate_path}/api"                → API Overview
  "{crate_path}/api"                → Authentication
  "{crate_path}/api"                → Endpoints Reference
  "{crate_path}/config"             → Configuration
  "{crate_path}/config"             → Environment Variables

BAD (one subfolder per doc):
  "{crate_path}/architecture/backend/backend-architecture"
  "{crate_path}/features/wiki-links/wikilink-system"
  "{crate_path}/deployment/docker/docker-deployment"

MANDATORY PAGES (always include these, no exceptions):
  1. "Overview" at "{crate_path}" — what the project is, key components, system diagram
  2. "Getting Started" at "{crate_path}" — prerequisites, install, run in 5 minutes
  3. "Capabilities & User Stories" at "{crate_path}" — business-facing document describing
     what a user can DO with this tool. Written from the user's perspective, NOT the
     developer's. Include:
     - User stories in "As a [role], I can [action], so that [benefit]" format
     - A functional capability matrix (feature → what it does → who it's for)
     - End-to-end workflows a user would follow
     - Client-facing descriptions suitable for product docs or onboarding material
     This page should read like product documentation, not engineering docs.

These three pages MUST appear first in the documents list. Every other page is up
to your judgement based on the scout reports.

PAGE COUNT GUIDELINES:
  - Small repos (< 10 source files): 5-8 pages
  - Medium repos (10-50 files): 8-15 pages
  - Large repos (50+ files): 15-25 pages
Each page should cover ONE focused topic. When in doubt, split.

WIKILINKS ARE THE MOST IMPORTANT THING:
For each page, list ALL other pages it should link to in wikilinks_out.
Every page should link to 5-15 other pages. The wikilink graph should be
DENSE — a reader should be able to navigate the entire wiki by clicking
through links. Think of it as a dependency/relationship map.

DESCRIPTION FIELD:
Every document MUST have a "description" — a 2-3 sentence summary of what the
document covers and who it's for. This is stored in the database and used by:
  - MCP tools (LLMs read descriptions to decide which document to fetch)
  - Semantic search (descriptions are embedded for vector similarity)
  - Document discovery (shown in search results and document lists)
Write descriptions as if explaining to a colleague what they'll find in this page.

FORMAT CHOICES:
For each section, specify what format best serves comprehension:
  "table:..." — structured data, comparisons, specifications
  "diagram:..." — architecture, flows, relationships, data models
  "code:..." — examples, setup commands, API usage
  "wikilinks:..." — navigation to related pages

OUTPUT INSTRUCTIONS:
Output ONLY a valid JSON object (no markdown fences, no commentary).

{{
  "repo_summary": "One paragraph describing the project",
  "complexity": "small|medium|large",
  "reader_journey": "Overview → Getting Started → Architecture → API → Config",
  "documents": [
    {{
      "doc_type": "overview",
      "title": "Overview",
      "path": "{crate_path}",
      "description": "High-level overview of the project, its purpose, and how its components fit together. Start here to orient yourself.",
      "rationale": "Index page — orients the reader and links to everything",
      "sections": [
        {{
          "heading": "What is this project?",
          "format_rationale": "Prose intro with diagram for immediate mental model",
          "rich_content": ["diagram:high-level system overview"]
        }},
        {{
          "heading": "Key Components",
          "format_rationale": "Table linking to each component's dedicated page",
          "rich_content": ["table:components with links to their pages"]
        }}
      ],
      "key_files_to_read": ["README.md"],
      "wikilinks_out": ["Getting Started", "Architecture", "Backend API", "Configuration"]
    }},
    {{
      "doc_type": "component",
      "title": "Document Service",
      "path": "{crate_path}/architecture",
      "description": "Explains the Document Service: CRUD operations, version tracking, and wikilink dependency management. Covers the public interface and internal design.",
      "rationale": "Focused page on one core service — keeps pages short",
      "sections": [
        {{
          "heading": "Purpose",
          "format_rationale": "Brief prose explaining what this service does",
          "rich_content": []
        }},
        {{
          "heading": "Interface",
          "format_rationale": "Table of public methods is scannable",
          "rich_content": ["table:public methods with signatures"]
        }}
      ],
      "key_files_to_read": ["app/services/document_service.py"],
      "wikilinks_out": ["Document Repository", "Version Service", "API Endpoints"]
    }},
    {{
      "doc_type": "guide",
      "title": "Deployment Guide",
      "path": "{crate_path}",
      "description": "Step-by-step instructions for deploying the application in production, including Docker setup, environment configuration, and reverse proxy.",
      "replaces_title": "Deploy Instructions",
      "rationale": "Renaming existing doc — replaces_title ensures update instead of duplicate",
      "sections": [],
      "key_files_to_read": ["Dockerfile"],
      "wikilinks_out": ["Configuration", "Getting Started"]
    }}
  ]
}}

NOTE ON replaces_title:
Include "replaces_title" ONLY when you are renaming an existing document.
The value must be the EXACT old title from the EXISTING DOCUMENTS list.
This tells the system to update the existing doc instead of creating a duplicate.
Omit this field entirely for new documents or documents you're keeping as-is.

SPLITTING RULE — LARGE TOPICS MUST BE SPLIT:
If a topic has more than ~5 distinct items (endpoints, services, config sections,
models), it MUST be split into multiple pages. Examples:
  - "API Reference" with 12 endpoints → split by resource: "Users API", "Documents API", "Auth API"
  - "Architecture" covering frontend + backend + infra → split: "Backend Architecture", "Frontend Architecture", "Infrastructure"
  - "Configuration" with 20+ env vars → split by concern: "Database Config", "Auth Config", "Deployment Config"
ONE page should NEVER try to cover more than one resource group or domain.
The parent/overview page links to the sub-pages with a brief summary table.

CRITICAL RULES:
- Create MANY small pages (see page count guidelines), NOT few large ones
- Each page: 2-4 sections max. Keep it SHORT.
- Every page must have wikilinks_out with 5-15 other page titles
- Use nested paths for folder organization
- doc_type is a loose tag (overview, architecture, api, component, guide, config, data-model, capabilities, etc.)
- When EXISTING DOCUMENTS are provided, prefer reusing their titles and paths
- Use "replaces_title" only when renaming an existing doc (value = exact old title)
- Output ONLY the JSON object
"""

        print("[Planner] Analyzing scout reports and designing blueprint...")
        max_retries = 3
        last_error = None
        last_raw = ""

        for attempt in range(1, max_retries + 1):
            try:
                messages = [
                    self._Message(role="user", content=[self._TextContent(text=planner_prompt)])
                ]
                # On retry, feed back the failed response and ask for valid JSON
                if attempt > 1 and last_raw:
                    messages.append(self._Message(role="assistant", content=[self._TextContent(text=last_raw)]))
                    messages.append(self._Message(role="user", content=[self._TextContent(
                        text=f"Your response was not valid JSON. Error: {last_error}\n\n"
                             "Please output ONLY a valid JSON object with the exact schema requested. "
                             "No markdown fences, no commentary, no text before or after the JSON."
                    )]))

                response = self.planner_llm.completion(messages=messages)

                raw_text = ""
                for block in response.message.content:
                    if hasattr(block, "text"):
                        raw_text += block.text

                json_text = raw_text.strip()
                if json_text.startswith("```"):
                    json_text = re.sub(r"^```(?:json)?\s*\n?", "", json_text)
                    json_text = re.sub(r"\n?```\s*$", "", json_text)

                from json_repair import repair_json
                blueprint = json.loads(repair_json(json_text))

                if isinstance(blueprint, dict) and "documents" in blueprint:
                    docs = blueprint["documents"]
                    for doc in docs:
                        if "path" not in doc:
                            doc["path"] = crate_path
                    docs = _flatten_single_doc_folders(docs, crate_path)
                    blueprint["documents"] = docs
                    print(f"[Planner] Blueprint ready: {len(docs)} documents")
                    print(f"   Complexity: {blueprint.get('complexity', 'unknown')}")
                    print(f"   Journey: {blueprint.get('reader_journey', 'N/A')}")
                    for doc in docs:
                        rationale = doc.get("rationale", "")
                        print(f"   - {doc['title']} ({doc['doc_type']}): {rationale[:60]}...")
                    return blueprint

                last_raw = raw_text
                last_error = "Response was valid JSON but missing 'documents' key"
                print(f"[Planner] Attempt {attempt}/{max_retries}: invalid blueprint structure, retrying...")

            except json.JSONDecodeError as e:
                last_raw = raw_text
                last_error = str(e)
                print(f"[Planner] Attempt {attempt}/{max_retries}: JSON parse error ({e}), retrying...")
            except Exception as e:
                last_error = str(e)
                last_raw = ""
                print(f"[Planner] Attempt {attempt}/{max_retries}: {e}, retrying...")

        raise RuntimeError(
            f"Planner failed after {max_retries} attempts. Last error: {last_error}"
        )

    def plan_hierarchical(
        self,
        reports_by_key: dict[str, str],
        existing_docs: list[dict] | None = None,
    ) -> dict:
        """Two-phase planning for large report sets that exceed context budget.

        Phase 1: Groups reports into chunks that fit within ~50% of context,
                 producing per-group mini-plans (partial document lists).
        Phase 2: Merges mini-plans into a coherent global blueprint,
                 deduplicating and ensuring mandatory pages exist.

        Falls back to single-pass ``plan()`` if report set is small enough.
        """
        total_report_tokens = sum(len(r) for r in reports_by_key.values()) // 4
        threshold = int(self._context_budget * 0.7)

        # If reports fit in context, delegate to single-pass plan()
        if total_report_tokens <= threshold:
            combined = "\n\n---\n\n".join(reports_by_key.values())
            return self.plan(combined, existing_docs)

        print(f"[Planner] Reports exceed context ({total_report_tokens:,} tokens > "
              f"{threshold:,} threshold) — using hierarchical planning")

        crate_path = f"{self.crate}{self.repo_name}".rstrip("/")

        # Phase 1: Group reports into chunks and produce mini-plans
        chunk_budget_chars = int(self._context_budget * 0.5 * 4)  # 50% of context in chars
        chunks: list[list[str]] = []
        current_chunk: list[str] = []
        current_size = 0

        for key, report in reports_by_key.items():
            if current_size + len(report) > chunk_budget_chars and current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_size = 0
            current_chunk.append(report)
            current_size += len(report)
        if current_chunk:
            chunks.append(current_chunk)

        print(f"[Planner] Phase 1: {len(chunks)} report groups → mini-plans")

        mini_plans: list[list[dict]] = []
        for i, chunk in enumerate(chunks, 1):
            chunk_text = "\n\n---\n\n".join(chunk)
            mini_prompt = f"""You are a documentation architect. Based on these scout reports about
a SUBSET of a codebase, suggest 3-8 focused wiki pages that should be written.

SCOUT REPORTS (subset {i}/{len(chunks)}):
{chunk_text}

Base path for documents: "{crate_path}"

Output ONLY a JSON array of document specs. Each spec must have:
  "doc_type", "title", "path", "description" (2-3 sentences),
  "sections" (list of {{"heading": "...", "rich_content": []}}),
  "key_files_to_read" (list of file paths)

Output ONLY the JSON array — no markdown fences, no commentary.
"""
            try:
                response = self.planner_llm.completion(
                    messages=[self._Message(role="user", content=[self._TextContent(text=mini_prompt)])],
                )
                raw = ""
                for block in response.message.content:
                    if hasattr(block, "text"):
                        raw += block.text
                raw = raw.strip()
                if raw.startswith("```"):
                    raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
                    raw = re.sub(r"\n?```\s*$", "", raw)

                from json_repair import repair_json
                docs = json.loads(repair_json(raw))
                if isinstance(docs, list):
                    mini_plans.append(docs)
                    print(f"   [Group {i}] {len(docs)} document specs")
                elif isinstance(docs, dict) and "documents" in docs:
                    mini_plans.append(docs["documents"])
                    print(f"   [Group {i}] {len(docs['documents'])} document specs")
                else:
                    print(f"   [Group {i}] Unexpected response format, skipping")
            except Exception as e:
                logger.warning("Mini-plan %d failed: %s", i, e)
                print(f"   [Group {i}] Failed: {e}")

        if not mini_plans:
            print("[Planner] All mini-plans failed, falling back to single-pass")
            combined = "\n\n---\n\n".join(reports_by_key.values())
            return self.plan(combined, existing_docs)

        # Phase 2: Merge mini-plans into a coherent global blueprint
        all_specs = [doc for group in mini_plans for doc in group]
        specs_json = json.dumps(all_specs, indent=2)

        existing_section = ""
        if existing_docs:
            existing_section = "\nEXISTING DOCUMENTS (reuse titles/paths where possible):\n"
            for doc in existing_docs:
                existing_section += f'  - "{doc["title"]}" at "{doc["path"]}" ({doc["doc_type"]})\n'

        merge_prompt = f"""You are a documentation architect. Multiple scouts explored different parts
of a large codebase and produced these document suggestions independently.
Merge them into ONE coherent documentation blueprint.

DOCUMENT SUGGESTIONS FROM SCOUTS:
{specs_json}
{existing_section}
YOUR TASKS:
1. DEDUPLICATE: Remove duplicate or overlapping document specs
2. ENSURE MANDATORY PAGES: Must include "Overview", "Getting Started",
   "Capabilities & User Stories" at path "{crate_path}"
3. ADD WIKILINKS: For each document, add "wikilinks_out" listing 5-15
   other page titles it should reference
4. HARMONIZE PATHS: Ensure consistent folder structure under "{crate_path}"
5. ADD REPO SUMMARY: One paragraph describing the whole project

Output ONLY a valid JSON object:
{{
  "repo_summary": "...",
  "complexity": "large",
  "reader_journey": "Overview → Getting Started → ...",
  "documents": [ ... ]
}}

Each document must have: doc_type, title, path, description, sections,
key_files_to_read, wikilinks_out. Output ONLY JSON — no fences, no commentary.
"""
        print(f"[Planner] Phase 2: Merging {len(all_specs)} specs into global blueprint...")
        max_retries = 3
        last_error = None
        last_raw = ""

        for attempt in range(1, max_retries + 1):
            try:
                messages = [
                    self._Message(role="user", content=[self._TextContent(text=merge_prompt)])
                ]
                if attempt > 1 and last_raw:
                    messages.append(self._Message(role="assistant", content=[self._TextContent(text=last_raw)]))
                    messages.append(self._Message(role="user", content=[self._TextContent(
                        text=f"Your response was not valid JSON. Error: {last_error}\n\n"
                             "Please output ONLY a valid JSON object with the exact schema requested. "
                             "No markdown fences, no commentary, no text before or after the JSON."
                    )]))

                response = self.planner_llm.completion(messages=messages)
                raw = ""
                for block in response.message.content:
                    if hasattr(block, "text"):
                        raw += block.text
                raw = raw.strip()
                if raw.startswith("```"):
                    raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
                    raw = re.sub(r"\n?```\s*$", "", raw)

                from json_repair import repair_json
                blueprint = json.loads(repair_json(raw))

                if isinstance(blueprint, dict) and "documents" in blueprint:
                    docs = blueprint["documents"]
                    for doc in docs:
                        if "path" not in doc:
                            doc["path"] = crate_path
                    docs = _flatten_single_doc_folders(docs, crate_path)
                    blueprint["documents"] = docs
                    print(f"[Planner] Hierarchical blueprint ready: {len(docs)} documents")
                    return blueprint

                last_raw = raw
                last_error = "Response was valid JSON but missing 'documents' key"
                print(f"[Planner] Merge attempt {attempt}/{max_retries}: invalid structure, retrying...")

            except json.JSONDecodeError as e:
                last_raw = raw
                last_error = str(e)
                print(f"[Planner] Merge attempt {attempt}/{max_retries}: JSON parse error ({e}), retrying...")
            except Exception as e:
                last_error = str(e)
                last_raw = ""
                print(f"[Planner] Merge attempt {attempt}/{max_retries}: {e}, retrying...")

        raise RuntimeError(
            f"Planner merge failed after {max_retries} attempts. Last error: {last_error}"
        )



# ---------------------------------------------------------------------------
# Free functions
# ---------------------------------------------------------------------------

def _flatten_single_doc_folders(docs: list[dict], base_path: str) -> list[dict]:
    """Move docs out of folders that contain only one document."""
    folder_counts = Counter(doc.get("path", base_path) for doc in docs)
    for doc in docs:
        path = doc.get("path", base_path)
        if path != base_path and folder_counts[path] == 1:
            parent = "/".join(path.split("/")[:-1]) or base_path
            old = path
            doc["path"] = parent
            print(f"   [Flatten] {doc['title']}: {old} → {parent}")
    return docs
