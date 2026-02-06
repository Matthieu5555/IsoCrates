"""Planner: Tier 1 reasoning — designs the documentation blueprint.

Reads scout reports and outputs a structured JSON blueprint specifying
what documents to write, their sections, and cross-references.
"""

import json
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any, Callable

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
        # For fallback plan — repo metrics
        get_repo_metrics: Callable[[], dict[str, Any]],
    ) -> None:
        self.planner_llm = planner_llm
        self.repo_name = repo_name
        self.crate = crate
        self.notes_dir = notes_dir
        self._Message = message_cls
        self._TextContent = text_content_cls
        self._get_repo_metrics = get_repo_metrics

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
        try:
            response = self.planner_llm.completion(
                messages=[
                    self._Message(role="user", content=[self._TextContent(text=planner_prompt)])
                ],
            )

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

            print("[Planner] Response was not a valid blueprint, using fallback")
        except json.JSONDecodeError as e:
            print(f"[Planner] Failed to parse JSON ({e}), using fallback")
        except Exception as e:
            logger.error("Planning failed (%s), using fallback", e)

        return self.fallback_plan(crate_path)

    def fallback_plan(self, crate_path: str) -> dict:
        """Deterministic fallback when planner fails."""
        metrics = self._get_repo_metrics()
        complexity = metrics["size_label"]

        all_titles: list[str] = []
        documents: list[dict] = []

        core_pages = [
            {"doc_type": "overview", "title": "Overview", "path": crate_path,
             "sections": [
                 {"heading": "What is this project?", "rich_content": ["diagram:system overview"]},
                 {"heading": "Key Components", "rich_content": ["table:components"]},
             ], "key_files_to_read": ["README.md"]},
            {"doc_type": "capabilities", "title": "Capabilities & User Stories", "path": crate_path,
             "sections": [
                 {"heading": "User Stories", "rich_content": []},
                 {"heading": "Feature Matrix", "rich_content": ["table:capabilities"]},
                 {"heading": "Key Workflows", "rich_content": ["diagram:user workflows"]},
             ], "key_files_to_read": ["README.md"]},
            {"doc_type": "quickstart", "title": "Getting Started", "path": f"{crate_path}/getting-started",
             "sections": [
                 {"heading": "Prerequisites", "rich_content": ["table:requirements"]},
                 {"heading": "Installation", "rich_content": ["code:install"]},
             ], "key_files_to_read": ["README.md"]},
            {"doc_type": "architecture", "title": "Architecture", "path": f"{crate_path}/architecture",
             "sections": [
                 {"heading": "System Design", "rich_content": ["diagram:architecture"]},
                 {"heading": "Components", "rich_content": ["table:components"]},
             ], "key_files_to_read": ["README.md"]},
            {"doc_type": "api", "title": "API Reference", "path": f"{crate_path}/api",
             "sections": [
                 {"heading": "Endpoints", "rich_content": ["table:endpoints"]},
             ], "key_files_to_read": ["README.md"]},
        ]

        if complexity in ("medium", "large"):
            core_pages.extend([
                {"doc_type": "config", "title": "Configuration", "path": f"{crate_path}/config",
                 "sections": [
                     {"heading": "Environment Variables", "rich_content": ["table:env vars"]},
                 ], "key_files_to_read": ["README.md"]},
                {"doc_type": "guide", "title": "User Guide", "path": f"{crate_path}/guide",
                 "sections": [
                     {"heading": "Core Workflow", "rich_content": ["diagram:workflow"]},
                 ], "key_files_to_read": ["README.md"]},
            ])

        if complexity == "large":
            core_pages.extend([
                {"doc_type": "data-model", "title": "Data Model", "path": f"{crate_path}/architecture/data-model",
                 "sections": [
                     {"heading": "Schema", "rich_content": ["diagram:ER diagram"]},
                 ], "key_files_to_read": ["README.md"]},
                {"doc_type": "contributing", "title": "Contributing", "path": f"{crate_path}/contributing",
                 "sections": [
                     {"heading": "Development Setup", "rich_content": ["code:setup"]},
                 ], "key_files_to_read": ["README.md"]},
            ])

        all_titles = [p["title"] for p in core_pages]
        for page in core_pages:
            page["wikilinks_out"] = [t for t in all_titles if t != page["title"]]
            documents.append(page)

        return {
            "repo_summary": f"Repository {self.repo_name}",
            "complexity": complexity,
            "documents": documents,
        }


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
