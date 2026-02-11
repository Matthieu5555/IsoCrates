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
import signal
import shutil
import sys
import argparse
import subprocess
import uuid
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
from repo_analysis import ModuleInfo, RepoAnalysis, analyze_repository, detect_crates

# Area-based partitioning for large repos
from partitioner import DocumentationArea, partition_for_documentation

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
    MERMAID_FIX_PROMPT,
    PLANNER_OUTPUT_CAP,
    SCOUT_CONDENSER_DIVISOR,
    WRITER_CONDENSER_DIVISOR,
    WRITER_CONVERSATION_TIMEOUT,
    PROSE_REQUIREMENTS,
    TABLE_REQUIREMENTS,
    DIAGRAM_REQUIREMENTS,
    WIKILINK_REQUIREMENTS,
    DESCRIPTION_REQUIREMENTS,
    SELF_CONTAINED_REQUIREMENTS,
    SOURCE_CITATION_REQUIREMENTS,
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
from model_config import ModelConfigError, resolve_model_config

# Extracted concerns
from mermaid_validator import validate_mermaid_blocks, format_errors_for_prompt
from provenance import ProvenanceTracker
from scout_pool import ScoutPool
from writer_pool import WriterPool
from circuit_breaker import run_with_timeout, CircuitBreakerOpen

# Prevent interactive pagers from trapping agents in git commands
os.environ.setdefault("GIT_PAGER", "cat")
os.environ.setdefault("PAGER", "cat")


# ---------------------------------------------------------------------------
# Graceful shutdown — checked between pipeline phases
# ---------------------------------------------------------------------------

_shutdown_requested = False


def _handle_shutdown_signal(signum: int, frame: Any) -> None:
    """Signal handler for graceful shutdown (SIGTERM / SIGINT)."""
    global _shutdown_requested
    sig_name = signal.Signals(signum).name
    logger.warning("Received %s — requesting graceful shutdown", sig_name)
    print(f"\n[Shutdown] Received {sig_name} — stopping after current phase completes...")
    _shutdown_requested = True


def _check_shutdown(phase: str) -> bool:
    """Return True and log if shutdown was requested before *phase*."""
    if _shutdown_requested:
        logger.warning("Shutdown requested before %s phase — exiting gracefully", phase)
        print(f"[Shutdown] Stopping before {phase} phase — partial results may be available")
        return True
    return False


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
        try:
            self._scout_config = resolve_model_config(SCOUT_MODEL)
            self._planner_config = resolve_model_config(PLANNER_MODEL)
            self._writer_config = resolve_model_config(WRITER_MODEL)
        except ModelConfigError as e:
            print(f"[Error] Model configuration failed: {e}")
            raise

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

        # Scout pool (parallel scout agent creation and orchestration)
        self.scout_pool = ScoutPool(
            scout_config=self._scout_config,
            scout_model=SCOUT_MODEL,
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
            planner_context_window=self._planner_config.context_window,
            scout_pool=self.scout_pool,
        )

        # Planner
        self.planner = DocumentPlanner(
            planner_llm=self.planner_llm,
            repo_name=self.repo_name,
            crate=self.crate,
            notes_dir=self.notes_dir,
            message_cls=Message,
            text_content_cls=TextContent,
            context_budget=self._planner_config.context_window,
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
        """Route to single-pass or hierarchical planner based on report size."""
        reports_by_key = getattr(self, "_scout_reports_by_key", {})
        # Use hierarchical planning when individual reports are available
        # and their combined size exceeds the planner's context budget
        if reports_by_key:
            total_tokens = sum(len(r) for r in reports_by_key.values()) // 4
            threshold = int(self._planner_config.context_window * 0.7)
            if total_tokens > threshold:
                return self.planner.plan_hierarchical(reports_by_key, existing_docs)
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
        writer_tmp_dir: str = "",
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

        # Output path supports nested folders from planner.
        # Each writer uses an isolated temp subdir to prevent parallel writers
        # from reading each other's output and getting confused about their topic.
        doc_path = doc_spec.get("path", f"{self.crate}{self.repo_name}".rstrip("/"))
        safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '-').lower()
        output_filename = f"{safe_title}.md"
        output_path = self.notes_dir / doc_path / output_filename
        # Isolated workspace path — caller provides writer_tmp_dir so that
        # generate_document() knows where to find the output afterwards.
        if not writer_tmp_dir:
            writer_tmp_dir = f".writer-{uuid.uuid4().hex[:8]}"
        absolute_output = self.repo_path / "notes" / writer_tmp_dir / doc_path / output_filename

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

{DESCRIPTION_REQUIREMENTS.replace('{title}', title)}

{SELF_CONTAINED_REQUIREMENTS}

{SOURCE_CITATION_REQUIREMENTS}

{doc_context}

{sibling_section}

EXPLORATION STRATEGY:
- The scout reports above contain detailed intelligence about the repo
- Use terminal commands to VERIFY specific details and read source files
- Use terminal ONLY for read-only commands: ls, cat, grep, find, tree, git log
- DO NOT run tests, execute scripts, or start applications
- DO NOT read or explore the notes/ directory — it contains other writers' output
  and will confuse you about YOUR assignment. Only read source code files.
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

    @staticmethod
    def _fallback_description(title: str, content: str) -> str:
        """Generate a description from content when writer omits bottomatter.

        Extracts the first non-heading, non-empty paragraph from the markdown
        body, prefixed with the page title for context.
        """
        for line in content.split("\n"):
            stripped = line.strip()
            # Skip headings, blank lines, tables, code fences, images
            if not stripped or stripped.startswith(("#", "|", "```", "![", "---")):
                continue
            # Use first prose paragraph (trim to ~250 chars)
            text = stripped[:250].rstrip()
            if len(stripped) > 250:
                text = text.rsplit(" ", 1)[0] + "..."
            return f"{title}: {text}"
        return title

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

        # Compute output path matching what the writer brief specifies
        doc_path = doc_spec.get("path", f"{self.crate}{self.repo_name}".rstrip("/"))
        safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '-').lower()
        output_filename = f"{safe_title}.md"
        output_file = self.notes_dir / doc_path / output_filename

        # Isolated workspace path — writer writes here, we move to final location after.
        # The same writer_id/writer_tmp_dir is passed to _build_writer_brief so the
        # agent is told to write to the same path we look for afterwards.
        writer_id = uuid.uuid4().hex[:8]
        writer_tmp_dir = f".writer-{writer_id}"
        absolute_output = self.repo_path / "notes" / writer_tmp_dir / doc_path / output_filename

        # Build writer brief (now includes scout reports)
        brief = self._build_writer_brief(
            doc_spec, blueprint, discovery, scout_reports,
            writer_tmp_dir=writer_tmp_dir,
        )

        try:
            # Ensure isolated output directory exists BEFORE agent runs.
            # Each writer writes to notes/.writer-{id}/ so parallel writers
            # can't see each other's output during exploration.
            absolute_output.parent.mkdir(parents=True, exist_ok=True)

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
            run_with_timeout(
                conversation.run,
                timeout=WRITER_CONVERSATION_TIMEOUT,
                label=f"writer:{title}",
            )

            # Find output in the writer's isolated temp directory
            writer_tmp_base = self.repo_path / "notes" / writer_tmp_dir
            isolated_output = writer_tmp_base / doc_path / output_filename
            if isolated_output.exists():
                # Move from temp dir to final location
                output_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(isolated_output), str(output_file))
                print(f"   [Output] Moved from isolated dir to {output_file}")
            else:
                # Writer may have ignored the temp path — search for the file
                candidates = list(writer_tmp_base.rglob(output_filename))
                if not candidates:
                    # Also check if writer wrote to the non-isolated notes path
                    direct_path = self.repo_path / "notes" / doc_path / output_filename
                    if direct_path.exists():
                        output_file = direct_path
                    else:
                        candidates = list(self.repo_path.rglob(output_filename))
                if candidates:
                    output_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(candidates[0]), str(output_file))

            # Clean up the writer's temp directory
            if writer_tmp_base.exists():
                shutil.rmtree(writer_tmp_base, ignore_errors=True)

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
            if not writer_description:
                print(f"   [Warning] Writer did not include description in bottomatter")

            body = re.sub(r"^\*Documentation Written by.*?\*\n+", "", body)
            clean_content = re.sub(
                r"\n---\n\n\*Documentation.*$", "", body, flags=re.DOTALL
            )

            # Validate mermaid diagrams and retry once if any have syntax errors.
            # The writer conversation is still alive — we can send a follow-up
            # message with the parse errors and let it fix the broken blocks.
            mermaid_errors = validate_mermaid_blocks(clean_content)
            if mermaid_errors:
                error_details = format_errors_for_prompt(mermaid_errors)
                print(f"   [Mermaid] {len(mermaid_errors)} diagram(s) have syntax errors, sending fix prompt...")
                for err in mermaid_errors:
                    print(f"      Block {err.block_index + 1} (line {err.line_number}): {err.error[:120]}")

                # Save pre-fix content in case the fix times out and leaves
                # a partial/corrupt file on disk.
                pre_fix_content = clean_content
                pre_fix_description = writer_description

                fix_prompt = MERMAID_FIX_PROMPT.format(
                    count=len(mermaid_errors),
                    error_details=error_details,
                    output_path=output_file,
                )
                conversation.send_message(fix_prompt)
                mermaid_fix_timed_out = False
                try:
                    run_with_timeout(
                        conversation.run,
                        timeout=120,  # mermaid fix should be quick
                        label=f"writer-mermaid-fix:{title}",
                    )
                except (TimeoutError, CircuitBreakerOpen) as e:
                    logger.warning("Mermaid fix timed out for %s: %s — using original content", title, e)
                    mermaid_fix_timed_out = True

                if mermaid_fix_timed_out:
                    # Keep the original content — the file on disk may be
                    # partially written by the timed-out agent.
                    clean_content = pre_fix_content
                    writer_description = pre_fix_description
                elif output_file.exists():
                    # Re-read the corrected file
                    raw_content = output_file.read_text()
                    metadata_retry, body_retry = parse_bottomatter(raw_content)
                    if not metadata_retry:
                        metadata_retry, body_retry = parse_frontmatter(raw_content)
                    if metadata_retry and metadata_retry.get("description"):
                        writer_description = metadata_retry["description"]
                    body = re.sub(r"^\*Documentation Written by.*?\*\n+", "", body_retry)
                    clean_content = re.sub(
                        r"\n---\n\n\*Documentation.*$", "", body, flags=re.DOTALL,
                    )
                    # Check if retry fixed the errors
                    remaining = validate_mermaid_blocks(clean_content)
                    if remaining:
                        print(f"   [Mermaid] {len(remaining)} diagram(s) still broken after retry — continuing anyway")
                    else:
                        print(f"   [Mermaid] All diagrams fixed after retry")

            # Sanitize wikilinks: keep valid, convert files to GitHub, strip rest.
            # NOTE: This first pass uses planned titles so writers referencing
            # each other's pages keep their links during generation. A second
            # pass in generate_all() re-sanitizes using *actually generated*
            # titles so any pages that failed to generate get their links
            # stripped to plain text.
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
                "description": writer_description or doc_spec.get("description") or self._fallback_description(title, clean_content),
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
            return {"status": "error", "doc_id": doc_id, "error": str(e), "resolved_from": resolved_from}

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

    # ------------------------------------------------------------------
    # Static analysis (for partitioning decisions)
    # ------------------------------------------------------------------

    def _analyze_repo(self) -> RepoAnalysis:
        """Run static analysis on the repository.  Pure filesystem, no LLM."""
        return analyze_repository(self.repo_path, self.crate)

    # ------------------------------------------------------------------
    # Post-generation cleanup (shared by single-area and partitioned paths)
    # ------------------------------------------------------------------

    def _post_generation_cleanup(
        self,
        results: dict[str, dict],
        planned_titles: set[str],
        generated_doc_ids: set[str],
        failed_doc_ids: set[str],
        id_stats: dict[str, int],
        snapshot: dict,
    ) -> None:
        """Wikilink re-sanitization, dangling report, summary, orphan cleanup.

        Extracted so both ``_generate_single_area`` and ``_generate_partitioned``
        share the same post-generation logic.
        """
        # Wikilink re-sanitization
        actually_generated_titles = {
            title for title, result in results.items()
            if result.get("status") in ("success", "skipped")
        }
        dangling_titles = planned_titles - actually_generated_titles

        # Pre-fetch documents from API once — both the re-sanitization and
        # dangling-wikilink loops need the same content.
        doc_cache: dict[str, dict] = {}
        for title, result in results.items():
            if result.get("status") != "success":
                continue
            doc_id = result.get("doc_id")
            api_result = result.get("api_result", {})
            if not doc_id or api_result.get("method") == "filesystem":
                continue
            try:
                doc = self.api_client.get_document(doc_id)
                if doc:
                    doc_cache[doc_id] = doc
            except Exception as e:
                logger.warning("Failed to fetch doc %s for cleanup: %s", doc_id, e)

        if dangling_titles:
            print(f"\n[Wikilink Cleanup] {len(dangling_titles)} planned page(s) were never generated:")
            for dt in sorted(dangling_titles):
                print(f"   - {dt}")
            print(f"   Re-sanitizing {len(results)} documents to strip broken wikilinks...")

            resanitized_count = 0
            for title, result in results.items():
                if result.get("status") != "success":
                    continue
                doc_id = result.get("doc_id")
                if not doc_id or doc_id not in doc_cache:
                    continue
                doc = doc_cache[doc_id]
                content = doc.get("content", "")
                has_dangling = any(
                    f"[[{dt}]]" in content or f"[[{dt}|" in content
                    for dt in dangling_titles
                )
                if not has_dangling:
                    continue
                clean = self._sanitize_wikilinks(content, actually_generated_titles, self.repo_url)
                if clean != content:
                    try:
                        self.api_client.update_document(doc_id, {"content": clean})
                        resanitized_count += 1
                        # Update cache so the dangling report sees sanitized content
                        doc_cache[doc_id] = {**doc, "content": clean}
                    except Exception as e:
                        logger.warning("Failed to re-sanitize doc %s: %s", doc_id, e)

            if resanitized_count:
                print(f"   Re-sanitized {resanitized_count} document(s)")

        # Broken wikilink validation report
        wikilink_pattern = re.compile(r'\[\[(.+?)\]\]')
        dangling_report: dict[str, list[str]] = {}
        for title, result in results.items():
            if result.get("status") != "success":
                continue
            doc_id = result.get("doc_id")
            if not doc_id or doc_id not in doc_cache:
                continue
            content = doc_cache[doc_id].get("content", "")
            for m in wikilink_pattern.finditer(content):
                inner = m.group(1)
                target = inner.split("|")[0].strip() if "|" in inner else inner.strip()
                if target not in actually_generated_titles:
                    dangling_report.setdefault(title, []).append(target)

        if dangling_report:
            print(f"\n[Wikilink Report] Dangling wikilinks found in {len(dangling_report)} document(s):")
            for doc_title, targets in sorted(dangling_report.items()):
                unique_targets = sorted(set(targets))
                print(f"   {doc_title}: {', '.join(unique_targets)}")

        # Summary
        total = len(results)
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

        # Orphan cleanup
        if snapshot["count"] > 0:
            print("\n[Phase 4] CLEANUP — Removing orphaned documents...")
            cleanup = self._cleanup_orphaned_docs(snapshot, generated_doc_ids, failed_doc_ids)
            if cleanup["deleted"] or cleanup["preserved_human"] or cleanup.get("preserved_user_organized", 0):
                print(f"   Deleted: {cleanup['deleted']}  Preserved (human): {cleanup['preserved_human']}  "
                      f"Preserved (user-organized): {cleanup.get('preserved_user_organized', 0)}  "
                      f"Preserved (failed): {cleanup['preserved_failed']}")

    # ------------------------------------------------------------------
    # Writer dispatch (shared helper for running writers + collecting stats)
    # ------------------------------------------------------------------

    def _run_writers(
        self,
        documents: list[dict],
        blueprint: dict,
        discovery: dict,
        scout_reports: str,
        title_to_doc_id: dict[str, str] | None,
        snapshot_by_id: dict | None,
    ) -> tuple[dict[str, dict], set[str], set[str], dict[str, int]]:
        """Dispatch writers (parallel or sequential) and collect results.

        Returns ``(results, generated_ids, failed_ids, id_stats)``.
        """
        max_workers = int(os.getenv("WRITER_PARALLEL", "3"))
        total = len(documents)
        print(f"\n[Writers] Generating {total} documents "
              f"(max {max_workers} parallel, detail first, hub last)...")

        if max_workers > 1:
            return self._run_writers_parallel(
                documents=documents,
                blueprint=blueprint,
                discovery=discovery,
                scout_reports=scout_reports,
                title_to_doc_id=title_to_doc_id,
                snapshot_by_id=snapshot_by_id,
                max_workers=max_workers,
            )

        # Sequential fallback (WRITER_PARALLEL=1)
        results: dict[str, dict] = {}
        generated_ids: set[str] = set()
        failed_ids: set[str] = set()
        id_stats: dict[str, int] = {"reused": 0, "new": 0, "renamed": 0}

        _HUB_TYPES = {"overview", "capabilities", "quickstart"}
        detail_docs = [d for d in documents if d.get("doc_type") not in _HUB_TYPES]
        hub_docs = [d for d in documents if d.get("doc_type") in _HUB_TYPES]
        ordered = detail_docs + hub_docs

        for idx, doc_spec in enumerate(ordered, 1):
            print(f"\n[{idx}/{total}] Dispatching writer for: {doc_spec['title']}")
            result = self.generate_document(
                doc_spec, blueprint, discovery, scout_reports,
                title_to_doc_id=title_to_doc_id,
                snapshot_by_id=snapshot_by_id,
            )
            results[doc_spec["title"]] = result

            doc_id = result.get("doc_id")
            if doc_id:
                status = result.get("status", "")
                if status in ("success", "skipped"):
                    generated_ids.add(doc_id)
                elif status in ("error", "error_fallback", "warning"):
                    failed_ids.add(doc_id)

            resolved = result.get("resolved_from", "")
            if "replaces:" in resolved:
                id_stats["renamed"] += 1
            elif "title match:" in resolved:
                id_stats["reused"] += 1
            else:
                id_stats["new"] += 1

        return results, generated_ids, failed_ids, id_stats

    # ------------------------------------------------------------------
    # generate_all: dispatcher
    # ------------------------------------------------------------------

    def generate_all(self, force: bool = False) -> dict:
        """Full pipeline: Scouts explore → Planner thinks → Writers execute.

        Automatically partitions large repositories into documentation areas
        when the codebase exceeds the planner's context window and has enough
        module structure to split meaningfully.  Small repos go through the
        original single-area pipeline unchanged.
        """
        print("\n" + "=" * 70)
        print("[Pipeline] THREE-TIER DOCUMENTATION GENERATION")
        print("=" * 70)

        snapshot = self._snapshot_existing_docs()
        regen_ctx = self._get_regeneration_context()

        # Regeneration always uses single-area path (targeted updates)
        if regen_ctx:
            return self._generate_single_area(
                force=force, regen_ctx=regen_ctx, snapshot=snapshot,
            )

        # First-time generation: check if partitioning is warranted
        analysis = self._analyze_repo()
        areas = partition_for_documentation(
            analysis, context_budget=self._planner_config.context_window,
        )

        if len(areas) == 1:
            return self._generate_single_area(
                force=force, regen_ctx=None, snapshot=snapshot,
            )

        print(f"\n[Partitioner] Repository split into {len(areas)} documentation areas:")
        for area in areas:
            mods = ", ".join(area.module_names[:5])
            suffix = f"... +{len(area.module_names) - 5}" if len(area.module_names) > 5 else ""
            print(f"   {area.name}: {len(area.module_names)} modules, "
                  f"~{area.token_estimate:,} tokens ({mods}{suffix})")

        return self._generate_partitioned(
            areas=areas, snapshot=snapshot, force=force,
        )

    # ------------------------------------------------------------------
    # Single-area pipeline (original flow, extracted verbatim)
    # ------------------------------------------------------------------

    def _generate_single_area(
        self,
        force: bool,
        regen_ctx: dict | None,
        snapshot: dict,
    ) -> dict:
        """Execute the full pipeline for a single (un-partitioned) repository.

        This is the original ``generate_all()`` body, extracted so the
        dispatcher can route to it.  Behavior is identical to the
        pre-partitioning code.
        """
        results: dict[str, dict] = {}

        if regen_ctx:
            # Check if repo has actually changed
            if not regen_ctx["git_diff"].strip() and not regen_ctx["git_log"].strip():
                current_sha = self._get_current_commit_sha()
                if regen_ctx["last_commit_sha"] == current_sha and not force:
                    print("\n[Pipeline] Repository unchanged since last generation — nothing to do.")
                    return results

            print("\n[Phase 1] DIFF SCOUT — Analyzing changes since last generation...")
            scout_reports = self._run_diff_scout(regen_ctx)

            existing_summary = "\n\n---\n\n## Existing Documentation Content\n"
            for doc in regen_ctx["existing_docs"]:
                existing_summary += f"\n### {doc['title']} ({doc['doc_type']})\n"
                existing_summary += doc["content"][:EXISTING_SUMMARY_TRUNCATION]
                if len(doc["content"]) > EXISTING_SUMMARY_TRUNCATION:
                    existing_summary += "\n... [truncated]"
                existing_summary += "\n"
            scout_reports += existing_summary
        else:
            print("\n[Phase 1] SCOUTS — Exploring repository...")
            scout_reports = self._run_scouts()

        if _check_shutdown("planner"):
            return results

        print("\n[Phase 2] PLANNER — Designing documentation architecture...")
        planner_existing = regen_ctx["existing_docs"] if regen_ctx else None
        blueprint = self._planner_think(scout_reports, existing_docs=planner_existing)

        documents = blueprint.get("documents", [])

        # Build title → doc_id map from snapshot
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

        discovery = self._discover_existing_documents()
        print(f"   Existing documents in system: {discovery['count']}")

        if _check_shutdown("writers"):
            return results

        writer_scout_reports = getattr(self, '_compressed_scout_reports', scout_reports)

        print(f"\n[Phase 3] WRITERS — Generating {len(documents)} documents...")
        results, generated_doc_ids, failed_doc_ids, id_stats = self._run_writers(
            documents=documents,
            blueprint=blueprint,
            discovery=discovery,
            scout_reports=writer_scout_reports,
            title_to_doc_id=title_to_doc_id or None,
            snapshot_by_id=snapshot["by_id"] or None,
        )

        planned_titles = {d["title"] for d in documents}
        self._post_generation_cleanup(
            results, planned_titles, generated_doc_ids, failed_doc_ids,
            id_stats, snapshot,
        )
        return results

    # ------------------------------------------------------------------
    # Partitioned pipeline (area-based generation + integration pass)
    # ------------------------------------------------------------------

    def _generate_partitioned(
        self,
        areas: list[DocumentationArea],
        snapshot: dict,
        force: bool = False,
    ) -> dict:
        """Execute the pipeline with area-based partitioning.

        Each area gets its own scout → planner → writer pipeline with
        focused, uncompressed reports.  After all areas complete, an
        integration pass generates cross-cutting hub pages (Overview,
        Getting Started, Architecture) that wikilink into area pages.
        """
        all_results: dict[str, dict] = {}
        all_generated_ids: set[str] = set()
        all_failed_ids: set[str] = set()
        all_id_stats: dict[str, int] = {"reused": 0, "new": 0, "renamed": 0}
        area_summaries: list[dict[str, Any]] = []
        all_planned_titles: set[str] = set()

        # Build title → doc_id map from snapshot
        title_to_doc_id: dict[str, str] = {}
        if snapshot["by_id"]:
            for doc_id, doc_info in snapshot["by_id"].items():
                doc_title = doc_info.get("title", "")
                if doc_title and doc_title not in title_to_doc_id:
                    title_to_doc_id[doc_title] = doc_id

        discovery = self._discover_existing_documents()
        print(f"   Existing documents in system: {discovery['count']}")

        # === Process each content area ===
        for area_idx, area in enumerate(areas, 1):
            print(f"\n{'='*70}")
            print(f"[Area {area_idx}/{len(areas)}] {area.name}")
            print(f"{'='*70}")

            # Phase 1: Area-scoped scouts
            print(f"\n[Phase 1] Scouting area: {area.name}...")
            scout_result = self.scout_runner.run_area(area)
            self._apply_scout_result(scout_result)

            # Phase 2: Area-scoped planner (uncompressed reports — the key
            # quality improvement over the single-area path for large repos)
            print(f"\n[Phase 2] Planning area: {area.name}...")
            area_reports = scout_result.combined_text
            blueprint = self.planner.plan(area_reports)

            documents = blueprint.get("documents", [])
            area_doc_titles = [d["title"] for d in documents]
            all_planned_titles.update(area_doc_titles)

            area_summaries.append({
                "name": area.name,
                "summary": blueprint.get("repo_summary", f"Area covering {area.name}"),
                "modules": list(area.module_names),
                "doc_titles": area_doc_titles,
            })

            # Phase 3: Writers for this area
            writer_reports = scout_result.compressed_text
            print(f"\n[Phase 3] Writing {len(documents)} documents for {area.name}...")

            area_results, gen_ids, fail_ids, stats = self._run_writers(
                documents=documents,
                blueprint=blueprint,
                discovery=discovery,
                scout_reports=writer_reports,
                title_to_doc_id=title_to_doc_id or None,
                snapshot_by_id=snapshot["by_id"] or None,
            )

            all_results.update(area_results)
            all_generated_ids.update(gen_ids)
            all_failed_ids.update(fail_ids)
            for k in all_id_stats:
                all_id_stats[k] += stats.get(k, 0)

        # === Integration pass: cross-cutting hub pages ===
        print(f"\n{'='*70}")
        print("[Integration] Cross-cutting documentation")
        print(f"{'='*70}")

        # Collect all titles generated so far (for the integration planner
        # to reference in wikilinks)
        all_generated_titles = [
            title for title, result in all_results.items()
            if result.get("status") in ("success", "skipped")
        ]

        integration_blueprint = self.planner.plan_integration(
            area_summaries=area_summaries,
            all_titles=all_generated_titles,
        )

        integration_docs = integration_blueprint.get("documents", [])
        all_planned_titles.update(d["title"] for d in integration_docs)

        # Build lightweight scout context for integration writers (area
        # summaries, not deep module reports)
        integration_scout_text = "## Repository Areas\n\n"
        for area_sum in area_summaries:
            integration_scout_text += f"### {area_sum['name']}\n{area_sum['summary']}\n\n"
            integration_scout_text += f"Pages: {', '.join(area_sum['doc_titles'])}\n\n"

        print(f"\n[Phase 3] Writing {len(integration_docs)} integration documents...")
        int_results, int_gen, int_fail, int_stats = self._run_writers(
            documents=integration_docs,
            blueprint=integration_blueprint,
            discovery=discovery,
            scout_reports=integration_scout_text,
            title_to_doc_id=title_to_doc_id or None,
            snapshot_by_id=snapshot["by_id"] or None,
        )

        all_results.update(int_results)
        all_generated_ids.update(int_gen)
        all_failed_ids.update(int_fail)
        for k in all_id_stats:
            all_id_stats[k] += int_stats.get(k, 0)

        # === Post-generation cleanup ===
        self._post_generation_cleanup(
            all_results, all_planned_titles, all_generated_ids, all_failed_ids,
            all_id_stats, snapshot,
        )
        return all_results


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
    parser.add_argument(
        "--auto-crates",
        action="store_true",
        help="Automatically detect and process independent sub-projects (crates)",
    )
    args = parser.parse_args()

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _handle_shutdown_signal)
    signal.signal(signal.SIGINT, _handle_shutdown_signal)

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

    # Auto-crate detection: when --auto-crates is set and no explicit --crate,
    # detect sub-projects and run the pipeline once per crate.
    if args.auto_crates and not sanitized_crate:
        crates = detect_crates(repo_path)
        if len(crates) > 1:
            print(f"[Auto-Crates] Detected {len(crates)} independent sub-projects:")
            for c in crates:
                print(f"   {c['path']} ({c['marker']})")
            print()

            all_results = {}
            for crate_info in crates:
                crate_path = crate_info["path"]
                print(f"\n{'='*70}")
                print(f"[Auto-Crates] Processing crate: {crate_path}")
                print(f"{'='*70}")
                gen = OpenHandsDocGenerator(repo_path, sanitized_url, crate_path)
                crate_results = gen.generate_all(force=args.force)
                for title, result in crate_results.items():
                    all_results[f"{crate_path}/{title}"] = result

            results = all_results
        else:
            if crates:
                print(f"[Auto-Crates] Only 1 sub-project detected ({crates[0]['path']}), "
                      f"processing as single repo")
            generator = OpenHandsDocGenerator(repo_path, sanitized_url, sanitized_crate)
            results = generator.generate_all(force=args.force) if args.doc_type == "auto" else {}
    else:
        generator = OpenHandsDocGenerator(repo_path, sanitized_url, sanitized_crate)
        results = {}

    # Generate (single-crate path or doc-type mode)
    if not results and args.doc_type == "auto":
        results = generator.generate_all(force=args.force)
    elif not results:
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
