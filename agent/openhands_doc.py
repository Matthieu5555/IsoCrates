#!/usr/bin/env python3
"""
Three-Tier Autonomous Documentation Generator using OpenHands SDK

Architecture:
  Tier 0 — Scout Agents (Devstral × 3-5):
    Explore the repository in parallel-ish passes, producing structured
    intelligence reports about structure, architecture, APIs, infra, tests.

  Tier 1 — Planner (Kimi K2 Thinking × 1):
    Pure reasoning call (no tools). Reads scout reports and designs the
    optimal documentation architecture: what documents, what sections,
    what format (diagram/table/prose/code) best serves each piece of info.

  Tier 2 — Writer Agents (Devstral × 1 per document):
    Each receives a focused brief from the planner plus relevant scout
    reports and writes one document in flowing professional prose.

Usage:
    python openhands_doc.py --repo https://github.com/user/repo
    python openhands_doc.py --repo https://github.com/user/repo --crate backend/
"""

import json
import logging
import os
import re
import sys
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Any

from dotenv import load_dotenv

logger = logging.getLogger("isocrates.agent")

# OpenHands SDK imports
from openhands.sdk import LLM, Agent, Conversation, Tool
from openhands.sdk.llm import Message, TextContent
from openhands.sdk.context.condenser import LLMSummarizingCondenser
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.task_tracker import TaskTrackerTool
from openhands.tools.terminal import TerminalTool

# Static repo analysis
from repo_analysis import ModuleInfo, RepoAnalysis, analyze_repository

# Document lifecycle (discovery, snapshot, cleanup)
from document_lifecycle import DocumentLifecycle, get_current_commit_sha

# Scout orchestration
from scout import ScoutRunner, ScoutResult

# Planner (Tier 1)
from planner import DocumentPlanner, get_relevant_reports, sanitize_wikilinks

# Prompt templates, taxonomy, and pipeline constants
from prompts import (
    COMPLEXITY_ORDER,
    DOCUMENT_TYPES,
    EXISTING_SUMMARY_TRUNCATION,
    PLANNER_OUTPUT_CAP,
    SCOUT_CONDENSER_DIVISOR,
    WRITER_CONDENSER_DIVISOR,
    PROSE_REQUIREMENTS,
    TABLE_REQUIREMENTS,
    DIAGRAM_REQUIREMENTS,
    WIKILINK_REQUIREMENTS,
    DESCRIPTION_REQUIREMENTS,
    SELF_CONTAINED_REQUIREMENTS,
)

# Document registry for ID-based tracking
from doc_registry import (
    generate_doc_id,
    create_document_with_metadata,
    DocumentRegistry,
    parse_frontmatter,
    parse_bottomatter,
)

# API client for posting to backend
from api_client import DocumentAPIClient

# Version priority logic for intelligent regeneration
from version_priority import VersionPriorityEngine

# Security modules
from security import RepositoryValidator, PathValidator

# Model constraint resolution
from model_config import resolve_model_config

# Extracted concerns
from provenance import ProvenanceTracker
from writer_pool import WriterPool

# Prevent interactive pagers from trapping agents in git commands
os.environ.setdefault("GIT_PAGER", "cat")
os.environ.setdefault("PAGER", "cat")

# ---------------------------------------------------------------------------
# Model Configuration
# ---------------------------------------------------------------------------
# Global defaults — override per-tier with SCOUT_BASE_URL, PLANNER_API_KEY, etc.
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("OPENROUTER_API_KEY")
LLM_NATIVE_TOOL_CALLING = os.getenv("LLM_NATIVE_TOOL_CALLING", "true").lower() == "true"

SCOUT_MODEL = os.getenv("SCOUT_MODEL", "")
PLANNER_MODEL = os.getenv("PLANNER_MODEL", "")
WRITER_MODEL = os.getenv("WRITER_MODEL", "")


def _resolve_api_key(tier: str) -> str | None:
    """Resolve API key: tier-specific → global → Docker secrets."""
    key = os.getenv(f"{tier}_API_KEY") or LLM_API_KEY
    if not key:
        key_file = os.getenv("OPENROUTER_API_KEY_FILE")
        if key_file and os.path.exists(key_file):
            with open(key_file) as f:
                key = f.read().strip()
    return key


def _llm_kwargs(tier: str) -> dict:
    """Build LLM constructor kwargs for a tier with fallback to globals."""
    base_url = os.getenv(f"{tier}_BASE_URL") or LLM_BASE_URL
    api_key = _resolve_api_key(tier)
    kwargs = {"base_url": base_url}
    if api_key:
        kwargs["api_key"] = api_key
    return kwargs




# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def clone_repo(repo_url: str, destination: Path) -> Path:
    """Clone or update a GitHub repository."""
    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    repo_path = destination / repo_name

    if repo_path.exists():
        print(f"[Update] Updating: {repo_name}")
        try:
            subprocess.run(
                ["git", "pull"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError:
            print("[Warning] Pull failed, using existing version")
    else:
        print(f"[Cloning] Cloning: {repo_url}")
        subprocess.run(
            ["git", "clone", repo_url, str(repo_path)],
            check=True,
            capture_output=True,
        )

    return repo_path


# ===================================================================
# Main Generator Class
# ===================================================================

class OpenHandsDocGenerator:
    """
    Three-tier documentation generator.

    Tier 0 (Scouts):   Explore the repo, produce intelligence reports.
    Tier 1 (Planner):  Pure reasoning, designs doc architecture.
    Tier 2 (Writers):  Write each document from planner briefs.
    """

    def __init__(self, repo_path: Path, repo_url: str, crate: str = ""):
        self.repo_path = repo_path.resolve()
        self.repo_url = repo_url
        self.repo_name = repo_path.name
        self.crate = (
            crate + "/"
            if crate and not crate.endswith("/")
            else crate
        )

        # Configurable output directory
        self.notes_dir = Path(os.getenv("NOTES_DIR", "./notes")).resolve()
        self.notes_dir.mkdir(parents=True, exist_ok=True)

        # Registry & API client
        self.registry = DocumentRegistry()
        self.api_client = DocumentAPIClient()

        # Document lifecycle (discovery, snapshot, cleanup)
        self.lifecycle = DocumentLifecycle(
            api_client=self.api_client,
            repo_url=self.repo_url,
            repo_path=self.repo_path,
            crate=self.crate,
        )

        # Load environment
        load_dotenv()

        # Validate required config
        missing = [name for name, val in [
            ("SCOUT_MODEL", SCOUT_MODEL),
            ("PLANNER_MODEL", PLANNER_MODEL),
            ("WRITER_MODEL", WRITER_MODEL),
            ("LLM_BASE_URL", LLM_BASE_URL),
        ] if not val]
        if missing:
            raise ValueError(
                f"Missing required LLM configuration: {', '.join(missing)}. "
                "Set them in .env or as environment variables. See .env.example."
            )

        # ---- Resolve model constraints --------------------------------------
        self._scout_config = resolve_model_config(SCOUT_MODEL)
        self._planner_config = resolve_model_config(PLANNER_MODEL)
        self._writer_config = resolve_model_config(WRITER_MODEL)

        # ---- Tier 0: Scout Agent -------------------------------------------
        scout_kwargs = _llm_kwargs("SCOUT")
        self.scout_llm = LLM(
            model=SCOUT_MODEL,
            native_tool_calling=LLM_NATIVE_TOOL_CALLING,
            timeout=900,
            max_output_tokens=self._scout_config.max_output_tokens,
            litellm_extra_body=self._scout_config.extra_body or {},
            **self._scout_config.extra_llm_kwargs,
            **scout_kwargs,
        )
        # Condenser max_size derived from context window:
        # larger context → more events before condensing
        scout_condenser_size = max(20, self._scout_config.context_window // SCOUT_CONDENSER_DIVISOR)
        scout_condenser = LLMSummarizingCondenser(
            llm=self.scout_llm,
            max_size=scout_condenser_size,
            keep_first=2,
        )
        self.scout_agent = Agent(
            llm=self.scout_llm,
            tools=[
                Tool(name=TerminalTool.name),
                Tool(name=FileEditorTool.name),
            ],
            condenser=scout_condenser,
        )

        # ---- Tier 1: Planner LLM (direct completion, no tools) ------------
        # Planner output cap: use model limit but cap at 16K (plans don't need more)
        planner_output = min(self._planner_config.max_output_tokens, PLANNER_OUTPUT_CAP)
        self.planner_llm = LLM(
            model=PLANNER_MODEL,
            timeout=900,
            max_output_tokens=planner_output,
            litellm_extra_body=self._planner_config.extra_body or {},
            **self._planner_config.extra_llm_kwargs,
            **_llm_kwargs("PLANNER"),
        )

        # ---- Tier 2: Writer Agent ------------------------------------------
        writer_kwargs = _llm_kwargs("WRITER")
        self.writer_llm = LLM(
            model=WRITER_MODEL,
            native_tool_calling=LLM_NATIVE_TOOL_CALLING,
            timeout=900,
            max_output_tokens=self._writer_config.max_output_tokens,
            litellm_extra_body=self._writer_config.extra_body or {},
            **self._writer_config.extra_llm_kwargs,
            **writer_kwargs,
        )
        writer_condenser_size = max(20, self._writer_config.context_window // WRITER_CONDENSER_DIVISOR)
        writer_condenser = LLMSummarizingCondenser(
            llm=self.writer_llm,
            max_size=writer_condenser_size,
            keep_first=2,
        )
        self.writer_agent = Agent(
            llm=self.writer_llm,
            tools=[
                Tool(name=TerminalTool.name),
                Tool(name=FileEditorTool.name),
                Tool(name=TaskTrackerTool.name),
            ],
            condenser=writer_condenser,
        )

        # Provenance tracker (source file hash/reference tracking)
        self.provenance = ProvenanceTracker(repo_path=self.repo_path)

        # Writer pool (parallel writer agent creation and orchestration)
        self.writer_pool = WriterPool(
            writer_config=self._writer_config,
            writer_model=WRITER_MODEL,
            native_tool_calling=LLM_NATIVE_TOOL_CALLING,
            llm_kwargs_fn=_llm_kwargs,
        )

        # Scout runner
        self.scout_runner = ScoutRunner(
            scout_agent=self.scout_agent,
            planner_llm=self.planner_llm,
            repo_path=self.repo_path,
            crate=self.crate,
            scout_context_window=self._scout_config.context_window,
            conversation_cls=Conversation,
            message_cls=Message,
            text_content_cls=TextContent,
        )

        # Planner
        self.planner = DocumentPlanner(
            planner_llm=self.planner_llm,
            repo_name=self.repo_name,
            crate=self.crate,
            notes_dir=self.notes_dir,
            message_cls=Message,
            text_content_cls=TextContent,
            get_repo_metrics=lambda: ScoutRunner._estimate_repo(self.repo_path, self.crate),
        )

        print("[Agent] Three-Tier Documentation Generator Configured:")
        print(f"   Scout:   {SCOUT_MODEL} ({self._scout_config})")
        print(f"   Planner: {PLANNER_MODEL} ({self._planner_config})")
        print(f"   Writer:  {WRITER_MODEL} ({self._writer_config})")
        print(f"   Condenser: scout={scout_condenser_size}, writer={writer_condenser_size}")
        print(f"   Native tool calling: {LLM_NATIVE_TOOL_CALLING}")
        print(f"   Workspace: {self.repo_path}")
        print(f"   Output:    {self.notes_dir}")

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _discover_existing_documents(self) -> dict[str, dict[str, Any]]:
        """Delegate to lifecycle.discover()."""
        return self.lifecycle.discover()

    def _build_document_context(self, discovery: dict[str, dict[str, Any]]) -> str:
        """Delegate to lifecycle.build_context()."""
        return self.lifecycle.build_context(discovery)

    # ------------------------------------------------------------------
    # Regeneration context
    # ------------------------------------------------------------------

    def _get_regeneration_context(self) -> dict | None:
        """Delegate to lifecycle.get_regeneration_context()."""
        return self.lifecycle.get_regeneration_context()

    def _run_diff_scout(self, regen_ctx: dict) -> str:
        """Delegate to scout_runner.run_diff()."""
        result = self.scout_runner.run_diff(regen_ctx)
        self._apply_scout_result(result)
        return result.combined_text

    def _run_scouts(self) -> str:
        """Delegate to scout_runner.run()."""
        result = self.scout_runner.run()
        self._apply_scout_result(result)
        return result.combined_text

    def _apply_scout_result(self, result: ScoutResult) -> None:
        """Store scout results on self for backward-compatible access."""
        self._repo_metrics = result.repo_metrics
        self._module_map = result.module_map
        self._budget_ratio = result.budget_ratio
        self._scout_reports_by_key = result.reports_by_key
        self._compressed_reports_by_key = result.compressed_reports_by_key
        self._compressed_scout_reports = result.compressed_text

    # ------------------------------------------------------------------
    # Tier 1: Planner (pure reasoning, no tools)
    # ------------------------------------------------------------------

    def _planner_think(self, scout_reports: str, existing_docs: list[dict] | None = None) -> dict:
        """Delegate to planner.plan()."""
        return self.planner.plan(scout_reports, existing_docs)

    def _sanitize_wikilinks(self, content: str, valid_titles: set[str], repo_url: str) -> str:
        """Delegate to planner.sanitize_wikilinks()."""
        return sanitize_wikilinks(content, valid_titles, repo_url)

    def _fallback_plan(self, crate_path: str) -> dict:
        """Delegate to planner.fallback_plan()."""
        return self.planner.fallback_plan(crate_path)

    def _get_relevant_scout_reports(self, doc_type: str) -> str:
        """Get scout reports relevant to a specific doc type."""
        reports = getattr(self, "_scout_reports_by_key", {})
        return get_relevant_reports(doc_type, reports)

    # ------------------------------------------------------------------
    # Tier 2: Writers
    # ------------------------------------------------------------------

    def _build_writer_brief(
        self,
        doc_spec: dict[str, Any],
        blueprint: dict[str, Any],
        discovery: dict[str, dict[str, Any]],
        scout_reports: str,
    ) -> str:
        """
        Build a focused brief for a Writer agent based on the planner's
        blueprint for a single document. Includes relevant scout context
        so writers don't need to re-explore everything.
        """
        doc_type = doc_spec["doc_type"]
        title = doc_spec["title"]
        sections = doc_spec.get("sections", [])
        key_files = doc_spec.get("key_files_to_read", [])
        wikilinks_out = doc_spec.get("wikilinks_out", [])

        # Build full wiki page list for wikilink context
        all_page_titles = [d["title"] for d in blueprint["documents"]]
        wikilink_targets = doc_spec.get("wikilinks_out", [])
        # Combine explicit targets with all sibling titles
        all_link_targets = list(set(wikilink_targets + [
            t for t in all_page_titles if t != title
        ]))

        sibling_section = "ALL WIKI PAGES (link to these using [[Title]]):\n"
        for t in sorted(all_link_targets):
            sibling_section += f"  - [[{t}]]\n"

        # Build section directives (with format rationale from planner)
        section_directives = ""
        for sec in sections:
            heading = sec["heading"]
            rich = sec.get("rich_content", [])
            rationale = sec.get("format_rationale", "")
            section_directives += f"\n### {heading}\n"
            if rationale:
                section_directives += f"Format guidance: {rationale}\n"
            if rich:
                section_directives += "Required rich content:\n"
                for item in rich:
                    if item.startswith("table:"):
                        section_directives += f"  - Include a GFM TABLE: {item[6:]}\n"
                    elif item.startswith("diagram:"):
                        section_directives += f"  - Include a MERMAID DIAGRAM: {item[8:]}\n"
                    elif item.startswith("code:"):
                        section_directives += f"  - Include a CODE EXAMPLE: {item[5:]}\n"
                    elif item.startswith("wikilinks:"):
                        section_directives += f"  - Include WIKILINKS to: {item[10:]}\n"
            section_directives += "Write 1-3 concise prose paragraphs for this section.\n"

        # Build key files directive
        files_directive = ""
        if key_files:
            files_directive = "\nKEY FILES TO READ (start your exploration here):\n"
            for f in key_files:
                files_directive += f"  - {f}\n"

        # Existing doc context
        doc_context = self._build_document_context(discovery)

        # Output path supports nested folders from planner
        doc_path = doc_spec.get("path", f"{self.crate}{self.repo_name}".rstrip("/"))
        safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '-').lower()
        output_filename = f"{safe_title}.md"
        output_path = self.notes_dir / doc_path / output_filename
        # Absolute path for file_editor (requires absolute paths starting with /)
        absolute_output = self.repo_path / "notes" / doc_path / output_filename

        brief = f"""You are a technical documentation writer. Write ONE short, focused wiki page:
"{title}" for the project at {self.repo_path}.

THIS PAGE MUST BE SHORT: 1-2 printed pages maximum. This is a wiki page, not
a book chapter. If you find yourself writing more than ~800 words of prose,
you are writing too much. Be concise. Link to other pages for details.

REPOSITORY CONTEXT:
{blueprint.get('repo_summary', 'A software project.')}

PRE-DIGESTED INTELLIGENCE (from repository scouts — filtered for this page):
{self._get_relevant_scout_reports(doc_type) or scout_reports}

{PROSE_REQUIREMENTS}

{TABLE_REQUIREMENTS}

{DIAGRAM_REQUIREMENTS}

{WIKILINK_REQUIREMENTS}

{DESCRIPTION_REQUIREMENTS}

{SELF_CONTAINED_REQUIREMENTS}

{doc_context}

{sibling_section}

EXPLORATION STRATEGY:
- The scout reports above contain detailed intelligence about the repo
- Use terminal commands to VERIFY specific details and read source files
- Use terminal ONLY for read-only commands: ls, cat, grep, find, tree, git log
- DO NOT run tests, execute scripts, or start applications
{files_directive}

DOCUMENT STRUCTURE:
Write a markdown page titled "# {title}"
with the following sections:
{section_directives}

DO NOT add a "See Also" section. All wikilinks must be inline in prose.

OUTPUT:
- Write the COMPLETE markdown page to this EXACT path: {absolute_output}
- The directory already exists — just write the file.
- CRITICAL: You MUST use the file_editor tool with command="create" and this EXACT path.
  Example: file_editor command=create path={absolute_output} file_text="# Title..."
  Do NOT use touch, echo, or cat. Do NOT modify the path.
- WRITE THE FILE EARLY. Read the key files marked above, then write a COMPLETE,
  high-quality page. After writing, you may read additional files and overwrite
  the page with an improved version. But the file MUST exist on disk within your
  first 10 commands. Never spend many turns exploring before writing.
- Keep it SHORT — this is one page in a larger wiki
- Link to other pages liberally using [[Page Title]] for anything worth expanding on
- Base everything on verified facts from the code you read
- After writing the content, append a bottomatter block with your description:
  ---
  description: Your 2-3 sentence description of what this page actually covers.
  ---
- Work AUTONOMOUSLY — do not ask for permission
"""
        return brief

    # ------------------------------------------------------------------
    # Source file provenance tracking (delegated to ProvenanceTracker)
    # ------------------------------------------------------------------

    def _extract_source_references(
        self, content: str, key_files: list[str] | None = None
    ) -> list[str]:
        """Extract source file paths referenced in generated documentation."""
        return self.provenance.extract_source_references(content, key_files)

    def _compute_source_hashes(self, file_paths: list[str]) -> dict[str, str]:
        """Compute SHA-256 hashes of source files for change detection."""
        return self.provenance.compute_source_hashes(file_paths)

    # ------------------------------------------------------------------
    # Orphan cleanup
    # ------------------------------------------------------------------

    def _snapshot_existing_docs(self) -> dict:
        """Delegate to lifecycle.snapshot()."""
        return self.lifecycle.snapshot()

    def _cleanup_orphaned_docs(self, snapshot: dict, generated_ids: set, failed_ids: set) -> dict:
        """Delegate to lifecycle.cleanup_orphans()."""
        return self.lifecycle.cleanup_orphans(snapshot, generated_ids, failed_ids)

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def _get_current_commit_sha(self) -> str:
        """Delegate to get_current_commit_sha()."""
        return get_current_commit_sha(self.repo_path)

    def generate_document(
        self,
        doc_spec: dict,
        blueprint: dict,
        discovery: dict,
        scout_reports: str,
        title_to_doc_id: dict | None = None,
        snapshot_by_id: dict | None = None,
        writer_agent: "Agent | None" = None,
    ) -> dict:
        """
        Generate a single document using a Writer agent.

        Args:
            doc_spec:        One entry from blueprint["documents"]
            blueprint:       The full planner blueprint
            discovery:       Existing documents for cross-referencing
            scout_reports:   Concatenated scout intelligence reports
            title_to_doc_id: Optional map of existing title → doc_id for reuse
            snapshot_by_id:  Optional map of doc_id → doc summary from snapshot
            writer_agent:    Optional independent Agent for parallel execution

        Returns:
            Result dict with status, doc_id, etc.
        """
        doc_type = doc_spec["doc_type"]
        title = doc_spec["title"]
        path = doc_spec.get("path", f"{self.crate}{self.repo_name}".rstrip("/"))

        # Title-based ID resolution: reuse existing doc IDs to prevent duplicates.
        # api_path/api_title are what we send to the backend (must match existing ID).
        # path/title stay as the planner intended (used for output files and writer briefs).
        doc_id = None
        resolved_from = None
        api_path = path
        api_title = title

        if title_to_doc_id:
            # Direct title match
            if title in title_to_doc_id:
                doc_id = title_to_doc_id[title]
                resolved_from = f"title match: \"{title}\""

            # replaces_title: planner is renaming an existing doc
            if not doc_id:
                replaces = doc_spec.get("replaces_title")
                if replaces and replaces in title_to_doc_id:
                    doc_id = title_to_doc_id[replaces]
                    resolved_from = f"replaces: \"{replaces}\" → \"{title}\""

        if doc_id and snapshot_by_id and doc_id in snapshot_by_id:
            # Override API path/title so the backend computes the same doc_id
            existing = snapshot_by_id[doc_id]
            api_path = existing.get("path", path)
            api_title = existing.get("title", title)

        if not doc_id:
            doc_id = generate_doc_id(self.repo_url, path, title, doc_type)
            resolved_from = "computed (new)"

        commit_sha = self._get_current_commit_sha()

        print(f"\n{'='*70}")
        print(f"[Writer] GENERATING: {doc_spec['title']} ({doc_type})")
        print(f"{'='*70}")
        print(f"   Doc ID: {doc_id} ({resolved_from})")

        # Check version priority
        priority_engine = VersionPriorityEngine(
            api_client=self.api_client, repo_path=self.repo_path
        )
        # Fast path: source-level check (skips commit analysis if source files unchanged)
        key_files = doc_spec.get("key_files_to_read", [])
        if key_files:
            current_hashes = self._compute_source_hashes(key_files)
            if current_hashes:
                should_gen, src_reason, changed = priority_engine.should_regenerate_targeted(
                    doc_id, current_hashes
                )
                if not should_gen:
                    print(f"   [Skip] {src_reason} (source-level)")
                    return {"status": "skipped", "reason": src_reason, "doc_id": doc_id, "resolved_from": resolved_from}

        # Full version priority check (commit-level)
        should_generate, reason = priority_engine.should_regenerate(
            doc_id=doc_id, current_commit_sha=commit_sha
        )
        if not should_generate:
            print(f"   [Skip] {reason}")
            return {"status": "skipped", "reason": reason, "doc_id": doc_id, "resolved_from": resolved_from}

        print(f"   [Generate] {reason}")

        # Build writer brief (now includes scout reports)
        brief = self._build_writer_brief(doc_spec, blueprint, discovery, scout_reports)

        # Compute output path matching what the writer brief specifies
        doc_path = doc_spec.get("path", f"{self.crate}{self.repo_name}".rstrip("/"))
        safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '-').lower()
        output_filename = f"{safe_title}.md"
        output_file = self.notes_dir / doc_path / output_filename
        # Path the agent will write to (inside workspace)
        workspace_write_path = self.repo_path / "notes" / doc_path / output_filename

        try:
            # Ensure output directories exist BEFORE agent runs
            output_file.parent.mkdir(parents=True, exist_ok=True)
            workspace_write_path.parent.mkdir(parents=True, exist_ok=True)

            # Maximum agent turns before forcing termination. Writers are told
            # to write early (within 10 commands), so this is a safety net.
            # Higher = more time for revision passes; lower = faster failure.
            # 100 iterations ≈ 15-20 min at typical LLM latency.
            writer_max_iters = 100
            agent = writer_agent or self.writer_agent
            conversation = Conversation(
                agent=agent,
                workspace=str(self.repo_path),
                max_iteration_per_run=writer_max_iters,
            )
            conversation.send_message(brief)
            conversation.run()

            # Find output — writers write relative to workspace (self.repo_path)
            # Primary location: workspace/notes/doc_path/filename.md
            workspace_output_file = self.repo_path / "notes" / doc_path / output_filename
            if workspace_output_file.exists():
                output_file = workspace_output_file
            elif not output_file.exists():
                # Also try notes_dir name instead of "notes"
                workspace_relative = self.repo_path / self.notes_dir.name / doc_path / output_filename
                if workspace_relative.exists():
                    output_file = workspace_relative
                else:
                    # Recursive search for the filename in workspace
                    candidates = list(self.repo_path.rglob(output_filename))
                    if not candidates:
                        candidates = list(self.repo_path.rglob(f"*{safe_title}*.md"))
                    if not candidates:
                        candidates = list(self.repo_path.rglob(f"*{doc_type}*.md"))
                    if candidates:
                        output_file = candidates[0]

            if not output_file.exists():
                print(f"   [Warning] Output file not found")
                return {
                    "status": "warning",
                    "message": f"Output file not found for {title}",
                    "doc_id": doc_id,
                    "resolved_from": resolved_from,
                }

            # Read and clean content
            raw_content = output_file.read_text()
            metadata, body = parse_bottomatter(raw_content)
            if not metadata:
                metadata, body = parse_frontmatter(raw_content)

            writer_description = (metadata or {}).get("description", "")

            body = re.sub(r"^\*Documentation Written by.*?\*\n+", "", body)
            clean_content = re.sub(
                r"\n---\n\n\*Documentation.*$", "", body, flags=re.DOTALL
            )

            # Sanitize wikilinks: keep valid, convert files to GitHub, strip rest
            valid_titles = {d["title"] for d in blueprint.get("documents", [])}
            clean_content = self._sanitize_wikilinks(clean_content, valid_titles, self.repo_url)

            # Check for empty content (writer failed to write file properly)
            if not clean_content.strip():
                print(f"   [Error] Writer produced empty file — agent likely used touch instead of file_editor")
                return {
                    "status": "error",
                    "doc_id": doc_id,
                    "error": "empty_content",
                    "message": "Writer agent created empty file. It may have output content to stdout instead of using file_editor create.",
                    "resolved_from": resolved_from,
                }

            # Verify rich content
            has_table = "|" in clean_content and "---" in clean_content
            has_mermaid = "```mermaid" in clean_content
            wikilink_count = len(re.findall(r"\[\[.+?\]\]", clean_content))

            print(f"   [Content] Tables: {'yes' if has_table else 'no'} | Diagrams: {'yes' if has_mermaid else 'no'} | Wikilinks: {wikilink_count}")
            if wikilink_count < 5:
                print(f"   [Content] Warning: low wikilink count ({wikilink_count}) — pages should have 10-20+")

            keywords = DOCUMENT_TYPES.get(doc_type, {}).get("keywords", [])

            # Source file provenance tracking
            key_files = doc_spec.get("key_files_to_read", [])
            source_files = self._extract_source_references(clean_content, key_files)
            source_hashes = self._compute_source_hashes(source_files)

            # POST to API — use api_path/api_title so the backend computes
            # the same doc_id as our resolved one (prevents duplicates)
            doc_data = {
                "repo_url": self.repo_url,
                "repo_name": self.repo_name,
                "path": api_path,
                "title": api_title,
                "doc_type": doc_type,
                "content": clean_content,
                "description": writer_description or doc_spec.get("description", ""),
                "keywords": keywords,
                "author_type": "ai",
                "author_metadata": {
                    "generator": "openhands-three-tier",
                    "scout_model": SCOUT_MODEL,
                    "planner_model": PLANNER_MODEL,
                    "writer_model": WRITER_MODEL,
                    "repo_commit_sha": commit_sha,
                    "source_files": source_files,
                    "source_hashes": source_hashes,
                },
            }

            try:
                api_result = self.api_client.create_or_update_document(
                    doc_data=doc_data, fallback_path=output_file
                )
                content_size = len(clean_content.encode("utf-8"))

                if api_result.get("method") == "filesystem":
                    print(f"   [Fallback] Saved to file (API unavailable)")
                else:
                    print(f"   [Success] Posted to API")
                    print(f"   ID: {api_result.get('id', doc_id)}")

                print(f"   Size: {content_size:,} bytes")

                return {
                    "status": "success",
                    "doc_id": api_result.get("id", doc_id),
                    "method": api_result.get("method", "api"),
                    "size": content_size,
                    "api_result": api_result,
                    "resolved_from": resolved_from,
                }

            except Exception as e:
                logger.error("Failed to post document: %s", e)
                return {
                    "status": "error_fallback",
                    "doc_id": doc_id,
                    "error": str(e),
                    "file": str(output_file),
                    "resolved_from": resolved_from,
                }

        except Exception as e:
            logger.error("Generation failed: %s", e, exc_info=True)
            return {"status": "error", "error": str(e), "resolved_from": resolved_from}

    # ------------------------------------------------------------------
    # Parallel writer support (delegated to WriterPool)
    # ------------------------------------------------------------------

    def _create_writer_agent(self) -> Agent:
        """Create an independent Writer Agent + LLM for thread-safe parallel use."""
        return self.writer_pool.create_writer_agent()

    def _run_writers_parallel(
        self,
        documents: list[dict],
        blueprint: dict,
        discovery: dict,
        scout_reports: str,
        title_to_doc_id: dict[str, str] | None,
        snapshot_by_id: dict | None,
        max_workers: int = 3,
    ) -> tuple[dict[str, dict], set, set, dict]:
        """Run writer agents in parallel using ThreadPoolExecutor.

        Returns:
            (results_dict, generated_ids, failed_ids, id_stats)
        """
        # Build a closure that adapts generate_document to the signature
        # expected by WriterPool.run_parallel: (doc_spec, agent) -> result
        def _generate_fn(doc_spec: dict, writer_agent: Agent | None) -> dict:
            return self.generate_document(
                doc_spec, blueprint, discovery, scout_reports,
                title_to_doc_id=title_to_doc_id,
                snapshot_by_id=snapshot_by_id,
                writer_agent=writer_agent,
            )

        return self.writer_pool.run_parallel(
            documents=documents,
            generate_fn=_generate_fn,
            max_workers=max_workers,
        )

    def generate_all(self, force: bool = False) -> dict:
        """
        Full pipeline: Scouts explore → Planner thinks → Writers execute.
        """
        results = {}

        print("\n" + "=" * 70)
        print("[Pipeline] THREE-TIER DOCUMENTATION GENERATION")
        print("=" * 70)

        # Pre-generation snapshot for orphan cleanup
        snapshot = self._snapshot_existing_docs()

        # Phase 0: Check if this is a regeneration (docs already exist)
        regen_ctx = self._get_regeneration_context()

        if regen_ctx:
            # Check if repo has actually changed
            if not regen_ctx["git_diff"].strip() and not regen_ctx["git_log"].strip():
                # Repo hasn't moved — check if any doc is actually stale
                current_sha = self._get_current_commit_sha()
                if regen_ctx["last_commit_sha"] == current_sha and not force:
                    print("\n[Pipeline] Repository unchanged since last generation — nothing to do.")
                    return results

            # REGENERATION PATH: docs exist, focus on what changed
            print("\n[Phase 1] DIFF SCOUT — Analyzing changes since last generation...")
            scout_reports = self._run_diff_scout(regen_ctx)

            # Append existing doc content summaries for planner context
            existing_summary = "\n\n---\n\n## Existing Documentation Content\n"
            for doc in regen_ctx["existing_docs"]:
                existing_summary += f"\n### {doc['title']} ({doc['doc_type']})\n"
                existing_summary += doc["content"][:EXISTING_SUMMARY_TRUNCATION]
                if len(doc["content"]) > EXISTING_SUMMARY_TRUNCATION:
                    existing_summary += "\n... [truncated]"
                existing_summary += "\n"
            scout_reports += existing_summary
        else:
            # FIRST-TIME PATH: full exploration
            print("\n[Phase 1] SCOUTS — Exploring repository...")
            scout_reports = self._run_scouts()

        # Phase 2: Planner designs documentation architecture
        print("\n[Phase 2] PLANNER — Designing documentation architecture...")
        planner_existing = regen_ctx["existing_docs"] if regen_ctx else None
        blueprint = self._planner_think(scout_reports, existing_docs=planner_existing)

        documents = blueprint.get("documents", [])

        # Build title → doc_id map from snapshot for title-based ID resolution
        title_to_doc_id: dict[str, str] = {}
        if snapshot["by_id"]:
            for doc_id, doc_info in snapshot["by_id"].items():
                doc_title = doc_info.get("title", "")
                if doc_title:
                    if doc_title in title_to_doc_id:
                        print(f"[Warning] Title collision: \"{doc_title}\" — keeping first match")
                    else:
                        title_to_doc_id[doc_title] = doc_id
            if title_to_doc_id:
                print(f"[ID Resolution] Built title→ID map with {len(title_to_doc_id)} entries")

        total = len(documents)

        # Discover existing docs (once, shared across all writers)
        discovery = self._discover_existing_documents()
        print(f"   Existing documents in system: {discovery['count']}")

        # Use compressed scout reports for writers (planner already got full reports)
        writer_scout_reports = getattr(self, '_compressed_scout_reports', scout_reports)

        # Phase 3: Writers execute (parallel or sequential based on WRITER_PARALLEL)
        max_workers = int(os.getenv("WRITER_PARALLEL", "3"))
        print(f"\n[Phase 3] WRITERS — Generating {total} documents "
              f"(max {max_workers} parallel, detail first, hub last)...")

        if max_workers > 1:
            results, generated_doc_ids, failed_doc_ids, id_stats = self._run_writers_parallel(
                documents=documents,
                blueprint=blueprint,
                discovery=discovery,
                scout_reports=writer_scout_reports,
                title_to_doc_id=title_to_doc_id if title_to_doc_id else None,
                snapshot_by_id=snapshot["by_id"] if snapshot["by_id"] else None,
                max_workers=max_workers,
            )
        else:
            # Sequential fallback (WRITER_PARALLEL=1)
            generated_doc_ids = set()
            failed_doc_ids = set()
            id_stats = {"reused": 0, "new": 0, "renamed": 0}

            # Reorder: detail first, hub last
            _HUB_TYPES = {"overview", "capabilities", "quickstart"}
            detail_docs = [d for d in documents if d.get("doc_type") not in _HUB_TYPES]
            hub_docs = [d for d in documents if d.get("doc_type") in _HUB_TYPES]
            documents = detail_docs + hub_docs

            for idx, doc_spec in enumerate(documents, 1):
                print(f"\n[{idx}/{total}] Dispatching writer for: {doc_spec['title']}")
                result = self.generate_document(
                    doc_spec, blueprint, discovery, writer_scout_reports,
                    title_to_doc_id=title_to_doc_id if title_to_doc_id else None,
                    snapshot_by_id=snapshot["by_id"] if snapshot["by_id"] else None,
                )
                results[doc_spec["title"]] = result

                doc_id = result.get("doc_id")
                if doc_id:
                    status = result.get("status", "")
                    if status in ("success", "skipped"):
                        generated_doc_ids.add(doc_id)
                    elif status in ("error", "error_fallback", "warning"):
                        failed_doc_ids.add(doc_id)

                resolved = result.get("resolved_from", "")
                if "replaces:" in resolved:
                    id_stats["renamed"] += 1
                elif "title match:" in resolved:
                    id_stats["reused"] += 1
                else:
                    id_stats["new"] += 1

        # Summary
        print("\n" + "=" * 70)
        print("[Summary] GENERATION COMPLETE")
        print("=" * 70)

        successes = sum(1 for r in results.values() if r.get("status") == "success")
        skipped = sum(1 for r in results.values() if r.get("status") == "skipped")
        errors = sum(
            1 for r in results.values()
            if r.get("status") in ("error", "error_fallback", "warning")
        )

        print(f"   Pages: {total}  Success: {successes}  Skipped: {skipped}  Errors: {errors}")
        if any(v > 0 for v in id_stats.values()):
            print(f"   ID Resolution: {id_stats['reused']} reused, {id_stats['new']} new, {id_stats['renamed']} renamed")

        for title, result in results.items():
            status = result.get("status", "unknown")
            doc_id = result.get("doc_id", "")
            resolved = result.get("resolved_from", "")
            id_info = f" [{resolved}]" if resolved else ""
            print(f"   {title}: {status} ({doc_id}){id_info}")

        # Phase 4: Orphan cleanup
        if snapshot["count"] > 0:
            print("\n[Phase 4] CLEANUP — Removing orphaned documents...")
            cleanup = self._cleanup_orphaned_docs(snapshot, generated_doc_ids, failed_doc_ids)
            if cleanup["deleted"] or cleanup["preserved_human"] or cleanup.get("preserved_user_organized", 0):
                print(f"   Deleted: {cleanup['deleted']}  Preserved (human): {cleanup['preserved_human']}  "
                      f"Preserved (user-organized): {cleanup.get('preserved_user_organized', 0)}  "
                      f"Preserved (failed): {cleanup['preserved_failed']}")

        return results


# ===================================================================
# CLI Entry Point
# ===================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Three-tier documentation generator (Scouts + Planner + Writers)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --repo https://github.com/facebook/react
  %(prog)s --repo https://github.com/django/django --crate backend
  %(prog)s --repo https://github.com/user/repo --doc-type quickstart
        """,
    )
    parser.add_argument("--repo", required=True, help="GitHub repository URL")
    parser.add_argument(
        "--crate",
        default="",
        help="Optional crate prefix (e.g., 'backend')",
    )
    parser.add_argument(
        "--doc-type",
        default="auto",
        help="Document type to generate, or 'auto' for full pipeline (default: auto)",
    )
    parser.add_argument(
        "--planner-model",
        default=None,
        help="Override planner model",
    )
    parser.add_argument(
        "--writer-model",
        default=None,
        help="Override writer model",
    )
    parser.add_argument(
        "--scout-model",
        default=None,
        help="Override scout model",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Override global LLM base URL (default: http://localhost:11434)",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Override global LLM API key",
    )
    parser.add_argument(
        "--no-native-tools",
        action="store_true",
        help="Disable native tool calling (use text-based fallback)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force regeneration even if repo is unchanged since last run",
    )
    args = parser.parse_args()

    # Override config if specified via CLI
    if args.planner_model:
        os.environ["PLANNER_MODEL"] = args.planner_model
    if args.writer_model:
        os.environ["WRITER_MODEL"] = args.writer_model
    if args.scout_model:
        os.environ["SCOUT_MODEL"] = args.scout_model
    if args.base_url:
        os.environ["LLM_BASE_URL"] = args.base_url
    if args.api_key:
        os.environ["LLM_API_KEY"] = args.api_key
    if args.no_native_tools:
        os.environ["LLM_NATIVE_TOOL_CALLING"] = "false"

    # SECURITY: Validate repository URL
    validator = RepositoryValidator()
    is_valid, error, sanitized_url = validator.validate_repo_url(args.repo)
    if not is_valid:
        print(f"[Security] Repository URL validation failed: {error}")
        sys.exit(1)

    # SECURITY: Validate crate path
    path_validator = PathValidator()
    is_valid, error, sanitized_crate = path_validator.validate_collection(
        args.crate
    )
    if not is_valid:
        print(f"[Security] Crate validation failed: {error}")
        sys.exit(1)

    print("=" * 70)
    print("[IsoCrates] THREE-TIER AUTONOMOUS DOCUMENTATION GENERATOR")
    print("=" * 70)
    print(f"Repository: {sanitized_url}")
    if sanitized_crate:
        print(f"Crate: {sanitized_crate}")
    print()

    # Clone repository
    repos_dir = Path(os.getenv("REPOS_DIR", "./repos"))
    repos_dir.mkdir(exist_ok=True)

    try:
        repo_path = clone_repo(sanitized_url, repos_dir)
    except subprocess.CalledProcessError as e:
        print(f"[Error] Failed to clone repository: {e}")
        sys.exit(1)

    # Generate
    generator = OpenHandsDocGenerator(repo_path, sanitized_url, sanitized_crate)

    if args.doc_type == "auto":
        results = generator.generate_all(force=args.force)
    else:
        # Single doc mode — run scouts + planner for context, then one writer
        scout_reports = generator._run_scouts()
        blueprint = generator._planner_think(scout_reports)

        # Find the requested doc in the blueprint, or build a minimal spec
        crate_path = f"{sanitized_crate}/{repo_path.name}".strip("/")
        doc_spec = None
        for doc in blueprint.get("documents", []):
            if doc["doc_type"] == args.doc_type:
                doc_spec = doc
                break

        if not doc_spec:
            title = DOCUMENT_TYPES.get(args.doc_type, {}).get(
                "title", args.doc_type.replace("-", " ").title()
            )
            doc_spec = {
                "doc_type": args.doc_type,
                "title": title,
                "path": f"{crate_path}/{args.doc_type}",
                "sections": [
                    {"heading": "Overview", "rich_content": []},
                   ],
                "key_files_to_read": ["README.md"],
                "wikilinks_out": [],
            }
            blueprint = {
                "repo_summary": blueprint.get("repo_summary", f"Repository {repo_path.name}"),
                "complexity": blueprint.get("complexity", "medium"),
                "documents": [doc_spec],
            }

        discovery = generator._discover_existing_documents()
        result = generator.generate_document(
            doc_spec, blueprint, discovery, scout_reports
        )
        results = {doc_spec["title"]: result}

    # Check for failures and exit with appropriate code.
    # The worker (backend/worker.py) uses the exit code to determine job status:
    #   exit 0 → job marked "completed"
    #   exit 1 → job marked "failed", stderr captured as error_message
    error_count = sum(
        1 for r in results.values()
        if r.get("status") in ("error", "error_fallback")
    )
    total_count = len(results)

    if error_count > 0 and error_count == total_count:
        # All documents failed — hard failure
        print(f"\n[Error] All {error_count} document(s) failed to generate.", file=sys.stderr)
        for title, result in results.items():
            if result.get("status") in ("error", "error_fallback"):
                print(f"  - {title}: {result.get('error', 'unknown error')}", file=sys.stderr)
        sys.exit(1)

    if error_count > 0:
        # Partial failure — some succeeded, some failed. Report but exit 0
        # so the worker marks the job completed (partial docs are still useful).
        print(f"\n[Warning] {error_count}/{total_count} document(s) failed:", file=sys.stderr)
        for title, result in results.items():
            if result.get("status") in ("error", "error_fallback"):
                print(f"  - {title}: {result.get('error', 'unknown error')}", file=sys.stderr)

    # Final output
    api_url = os.getenv("DOC_API_URL", "http://localhost:8000")
    print(f"\n[Info] Documentation available at:")
    print(f"   API: {api_url}/api/docs")
    print(f"   Frontend: http://localhost:3000\n")


if __name__ == "__main__":
    main()
