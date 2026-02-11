"""Scout agent orchestration: topic scouts, module scouts, diff scouts, compression.

Tier 0 of the three-tier pipeline. Scouts explore the repository and
produce structured intelligence reports for the planner.
"""

import dataclasses
import logging
import os
from pathlib import Path

from prompts import (
    CONTENT_SNIPPET_LENGTH,
    ENTRY_POINT_PATTERNS,
    FILE_ASSIGNMENT_LIMIT,
    SCOUT_DEFINITIONS,
    SCOUT_FOCUS,
)
from repo_analysis import ModuleInfo, analyze_repository

logger = logging.getLogger("isocrates.agent")


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class ScoutResult:
    """Output from a scout run (topic or module based)."""
    reports_by_key: dict[str, str]
    compressed_reports_by_key: dict[str, str]
    combined_text: str
    compressed_text: str
    repo_metrics: dict
    module_map: dict[str, ModuleInfo]
    budget_ratio: float


# ---------------------------------------------------------------------------
# Scout Runner
# ---------------------------------------------------------------------------

class ScoutRunner:
    """Runs scout agents against a repository.

    Requires OpenHands SDK objects (*scout_agent*, *planner_llm*,
    *Conversation*, *Message*, *TextContent*) to be injected so that
    this module can be tested independently.
    """

    def __init__(
        self,
        scout_agent: object,
        planner_llm: object,
        repo_path: Path,
        crate: str,
        scout_context_window: int,
        # SDK types injected to avoid top-level import
        conversation_cls: type,
        message_cls: type,
        text_content_cls: type,
        planner_context_window: int = 131_072,
        scout_pool: "ScoutPool | None" = None,
    ) -> None:
        self.scout_agent = scout_agent
        self.planner_llm = planner_llm
        self.repo_path = repo_path
        self.crate = crate
        self._context_window = scout_context_window
        self._planner_context_window = planner_context_window
        self._scout_pool = scout_pool
        self._Conversation = conversation_cls
        self._Message = message_cls
        self._TextContent = text_content_cls
        self._max_iters = 60

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run_area(self, area: "DocumentationArea") -> ScoutResult:
        """Run scouts scoped to a single documentation area.

        Filters the repo's module map to only the area's modules, then
        delegates to module-based scouting.  The full repo is still
        analysed (so cross-module import edges are preserved), but
        scouts only explore files belonging to this area.

        For areas with a single module, falls back to topic-based
        scouting for broader coverage.

        Args:
            area: A ``DocumentationArea`` from the partitioner.

        Returns:
            ``ScoutResult`` with reports focused on this area's modules.
        """
        from partitioner import DocumentationArea  # deferred to avoid circular import

        full_metrics = self._estimate_repo(self.repo_path, self.crate)
        full_module_map: dict[str, ModuleInfo] = full_metrics.get("module_map", {})

        # Filter to area's modules
        area_names = set(area.module_names)
        area_module_map = {
            name: info for name, info in full_module_map.items()
            if name in area_names
        }
        if not area_module_map:
            area_module_map = full_module_map  # safety fallback

        area_tokens = sum(m.token_estimate for m in area_module_map.values())
        budget_ratio = area_tokens / self._context_window

        print(f"\n[Area Scout] {area.name}: {len(area_module_map)} modules, "
              f"~{area_tokens:,} tokens (budget_ratio={budget_ratio:.2f})")

        if len(area_module_map) >= 2:
            reports = self._run_module_scouts(area_module_map, budget_ratio)
        else:
            # Single module — topic scouts give better breadth
            area_metrics = dict(full_metrics)
            area_metrics["module_map"] = area_module_map
            area_metrics["token_estimate"] = area_tokens
            area_metrics["file_manifest"] = list(area.files)
            area_metrics["file_count"] = len(area.files)
            reports = self._run_topic_scouts(area_metrics, budget_ratio)

        combined = "\n\n---\n\n".join(reports.values())
        print(f"[Area Scout] {area.name}: {len(combined):,} chars total")

        # Lighter compression — areas are sized to fit the planner's context
        compression_target = int(self._planner_context_window * 0.5 * 4)
        compression_target = max(compression_target, 15_000)

        if len(combined) > compression_target:
            print(f"[Area Scout] Compressing ({len(combined):,} → ~{compression_target // 1000}K)...")
            compressed_by_key = self._compress_reports(reports, target_chars=compression_target)
            compressed_text = "\n\n---\n\n".join(compressed_by_key.values())
        else:
            compressed_by_key = reports
            compressed_text = combined

        return ScoutResult(
            reports_by_key=reports,
            compressed_reports_by_key=compressed_by_key,
            combined_text=combined,
            compressed_text=compressed_text,
            repo_metrics=full_metrics,
            module_map=area_module_map,
            budget_ratio=budget_ratio,
        )

    def run(self) -> ScoutResult:
        """Run full scout exploration (topic or module-based).

        Chooses strategy based on repo size vs scout context window.
        """
        metrics = self._estimate_repo(self.repo_path, self.crate)
        module_map = metrics.get("module_map", {})
        budget_ratio = metrics["token_estimate"] / self._context_window

        if module_map:
            print(f"[Modules] {len(module_map)} modules detected:")
            for mod_name, mod_info in sorted(
                module_map.items(), key=lambda x: -x[1].total_bytes
            ):
                imports = f" → imports: {', '.join(sorted(mod_info.imports_from))}" if mod_info.imports_from else ""
                print(f"   {mod_name}: {len(mod_info.files)} files, "
                      f"~{mod_info.token_estimate:,} tokens{imports}")

        print(f"\n[Sizing] ~{metrics['token_estimate']:,} tokens, "
              f"{metrics['file_count']} files, {metrics['total_bytes']:,} bytes "
              f"→ {metrics['size_label']} (budget_ratio={budget_ratio:.2f})")
        top3 = list(metrics["top_dirs"].items())[:3]
        if top3:
            top_str = ", ".join(f"{d} ({s // 1024}KB)" for d, s in top3)
            print(f"[Sizing] Top dirs: {top_str}")

        use_module_scouts = budget_ratio > 1.0 and len(module_map) >= 4

        if use_module_scouts:
            print(f"[Scouts] Large repo with {len(module_map)} modules — using module-based scouting")
            reports = self._run_module_scouts(module_map, budget_ratio)
        else:
            reports = self._run_topic_scouts(metrics, budget_ratio)

        combined = "\n\n---\n\n".join(reports.values())
        print(f"\n[Scouts] All reports collected: {len(combined)} chars total")

        # Adaptive compression target: reserve ~50% of planner context for
        # the prompt template, convert remaining tokens to chars (× 4).
        compression_target = int(self._planner_context_window * 0.5 * 4)
        compression_target = max(compression_target, 15_000)  # floor

        if len(combined) > compression_target:
            print(f"[Scouts] Compressing reports for writers "
                  f"({len(combined)} chars → ~{compression_target // 1000}K)...")
            compressed_by_key = self._compress_reports(reports, target_chars=compression_target)
            compressed_text = "\n\n---\n\n".join(compressed_by_key.values())
            print(f"[Scouts] Compressed: {len(compressed_text)} chars")
        else:
            compressed_by_key = reports
            compressed_text = combined

        return ScoutResult(
            reports_by_key=reports,
            compressed_reports_by_key=compressed_by_key,
            combined_text=combined,
            compressed_text=compressed_text,
            repo_metrics=metrics,
            module_map=module_map,
            budget_ratio=budget_ratio,
        )

    def run_diff(self, regen_ctx: dict) -> ScoutResult:
        """Run a diff-focused scout for regeneration.

        Also fetches repo metrics (needed by later stages).
        """
        metrics = self._estimate_repo(self.repo_path, self.crate)
        module_map = metrics.get("module_map", {})
        budget_ratio = metrics["token_estimate"] / self._context_window

        report = self._run_diff_scout(regen_ctx)
        reports = {"diff": report}

        return ScoutResult(
            reports_by_key=reports,
            compressed_reports_by_key=reports,
            combined_text=report,
            compressed_text=report,
            repo_metrics=metrics,
            module_map=module_map,
            budget_ratio=budget_ratio,
        )

    # ------------------------------------------------------------------
    # Internals: repo estimation
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_repo(repo_path: Path, crate: str) -> dict:
        analysis = analyze_repository(repo_path, crate)
        return {
            "file_manifest": analysis.file_manifest,
            "token_estimate": analysis.token_estimate,
            "file_count": analysis.file_count,
            "total_bytes": analysis.total_bytes,
            "size_label": analysis.size_label,
            "top_dirs": analysis.top_dirs,
            "module_map": analysis.module_map,
            "module_count": analysis.module_count,
        }

    # ------------------------------------------------------------------
    # Internals: topic-based scouting
    # ------------------------------------------------------------------

    def _run_topic_scouts(self, metrics: dict, budget_ratio: float) -> dict[str, str]:
        if budget_ratio < 0.3:
            scouts_to_run = ["structure", "architecture"]
        elif budget_ratio < 1.0:
            scouts_to_run = [k for k, v in SCOUT_DEFINITIONS.items() if v["always_run"]]
        else:
            scouts_to_run = list(SCOUT_DEFINITIONS.keys())

        print(f"[Scouts] Running {len(scouts_to_run)} scouts: {', '.join(scouts_to_run)} "
              f"(max {self._max_iters} iters each)")

        # Build prompts for all scouts up front
        scout_tasks: list[dict] = []
        for scout_key in scouts_to_run:
            scout_def = SCOUT_DEFINITIONS[scout_key]
            manifest_section = build_file_manifest_section(
                metrics["file_manifest"], scout_key,
                budget_ratio=budget_ratio,
                total_files=metrics["file_count"],
            )
            prompt = scout_def["prompt"].format(
                repo_path=self.repo_path,
                file_manifest=manifest_section,
                constraints=build_constraints(budget_ratio),
            )
            scout_tasks.append({
                "key": scout_key,
                "name": scout_def["name"],
                "prompt": prompt,
            })

        # Parallel path: use ScoutPool when available and >= 3 scouts
        if self._scout_pool and len(scout_tasks) >= 3:
            return self._scout_pool.run_parallel(
                scout_tasks=scout_tasks,
                run_one_fn=self._run_single_topic_scout,
            )

        # Sequential path: original behavior
        reports: dict[str, str] = {}
        for idx, task in enumerate(scout_tasks, 1):
            print(f"\n[Scout {idx}/{len(scout_tasks)}] {task['name']}...")
            _, report = self._run_single_topic_scout(task, self.scout_agent)
            reports[task["key"]] = report

        return reports

    def _run_single_topic_scout(
        self, task: dict, agent: object,
    ) -> tuple[str, str]:
        """Run one topic scout. Used by both sequential and parallel paths.

        Args:
            task: Dict with "key", "name", "prompt".
            agent: Agent instance (shared in sequential, independent in parallel).

        Returns:
            (scout_key, report_text).
        """
        import uuid
        scout_key = task["key"]
        scout_name = task["name"]
        prompt = task["prompt"]
        # Thread-safe report path with unique suffix
        uid = uuid.uuid4().hex[:8]
        report_path = Path(f"/tmp/scout_report_{scout_key}_{uid}.md")

        # Rewrite the prompt to use the unique report path
        generic_path = f"/tmp/scout_report_{scout_key}.md"
        prompt = prompt.replace(generic_path, str(report_path))

        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            try:
                conversation = self._Conversation(
                    agent=agent,
                    workspace=str(self.repo_path),
                    max_iteration_per_run=self._max_iters,
                )
                conversation.send_message(prompt)
                conversation.run()

                if report_path.exists():
                    report_text = report_path.read_text()
                    lines = len(report_text.strip().split("\n"))
                    print(f"   [Done] {scout_name}: {lines} lines")
                    return scout_key, report_text
                else:
                    print(f"   [Warning] Scout {scout_key} did not produce a report")
                    return scout_key, (
                        f"## Scout Report: {scout_name}\n"
                        f"### Key Findings\nNo report produced.\n"
                        f"### Status: INCOMPLETE\n"
                    )

            except Exception as e:
                if attempt < max_attempts:
                    import time
                    wait = 2 ** attempt
                    logger.warning("Scout %s attempt %d failed, retrying in %ds: %s",
                                   scout_key, attempt, wait, e)
                    print(f"   [Retry] {scout_name} failed, retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    logger.error("Scout %s failed after %d attempts: %s",
                                 scout_key, max_attempts, e)
                    return scout_key, (
                        f"## Scout Report: {scout_name}\n"
                        f"### Key Findings\nScout failed after {max_attempts} attempts: {e}\n"
                        f"### Status: FAILED\n"
                    )

        # Should not reach here, but just in case
        return scout_key, f"## Scout Report: {scout_name}\n### Status: UNKNOWN\n"

    # ------------------------------------------------------------------
    # Internals: module-based scouting
    # ------------------------------------------------------------------

    def _run_module_scouts(
        self,
        module_map: dict[str, ModuleInfo],
        budget_ratio: float,
    ) -> dict[str, str]:
        assignments = assign_module_scouts(module_map, budget_ratio=budget_ratio)
        print(f"[Module Scouts] {len(assignments)} scouts for {len(module_map)} modules:")
        for a in assignments:
            print(f"   {a['name']}: {a['focus_description']}")

        # Build tasks for parallel/sequential execution
        scout_tasks: list[dict] = []
        for assignment in assignments:
            scout_key = f"module_{assignment['name']}"
            prompt = build_module_scout_prompt(assignment, budget_ratio)
            scout_tasks.append({
                "key": scout_key,
                "name": ", ".join(assignment["modules"]),
                "prompt": prompt,
                "assignment": assignment,
            })

        # Parallel path
        if self._scout_pool and len(scout_tasks) >= 3:
            return self._scout_pool.run_parallel(
                scout_tasks=scout_tasks,
                run_one_fn=self._run_single_module_scout,
            )

        # Sequential path
        reports: dict[str, str] = {}
        for idx, task in enumerate(scout_tasks, 1):
            print(f"\n[Scout {idx}/{len(scout_tasks)}] Module: {task['name']}...")
            _, report = self._run_single_module_scout(task, self.scout_agent)
            reports[task["key"]] = report

        return reports

    def _run_single_module_scout(
        self, task: dict, agent: object,
    ) -> tuple[str, str]:
        """Run one module scout. Used by both sequential and parallel paths."""
        import uuid
        scout_key = task["key"]
        prompt = task["prompt"]
        modules_str = task["name"]
        uid = uuid.uuid4().hex[:8]
        report_path = Path(f"/tmp/scout_report_{scout_key}_{uid}.md")

        # Rewrite prompt to use thread-safe report path
        generic_path = f"/tmp/scout_report_{scout_key}.md"
        prompt = prompt.replace(generic_path, str(report_path))

        try:
            conversation = self._Conversation(
                agent=agent,
                workspace=str(self.repo_path),
                max_iteration_per_run=self._max_iters,
            )
            conversation.send_message(prompt)
            conversation.run()

            if report_path.exists():
                report_content = report_path.read_text()
                print(f"   Report: {len(report_content)} chars")
                return scout_key, report_content
            else:
                print(f"   [Warning] No report file found at {report_path}")
                return scout_key, (
                    f"## Module Scout Report: {modules_str}\n"
                    f"### Key Findings\nNo report produced.\n"
                )

        except Exception as e:
            logger.error("Module scout failed: %s", e)
            return scout_key, (
                f"## Module Scout Report: {modules_str}\n"
                f"### Key Findings\nScout failed: {e}\n"
            )

    # ------------------------------------------------------------------
    # Internals: diff scout
    # ------------------------------------------------------------------

    def _run_diff_scout(self, regen_ctx: dict) -> str:
        existing_doc_summaries = ""
        for doc in regen_ctx["existing_docs"]:
            content_snippet = doc["content"][:CONTENT_SNIPPET_LENGTH]
            if len(doc["content"]) > CONTENT_SNIPPET_LENGTH:
                content_snippet += "\n... [truncated]"
            existing_doc_summaries += f"\n### Existing: {doc['title']} ({doc['doc_type']})\n{content_snippet}\n"

        diff_prompt = f"""You are a repository scout specializing in CHANGE ANALYSIS. Documentation
already exists for this repository. Your job is to understand what has changed
since the last documentation was generated and identify what needs updating.

EXISTING DOCUMENTATION (current versions):
{existing_doc_summaries}

GIT LOG (commits since last documentation):
{regen_ctx['git_log']}

GIT DIFF (changes since last documentation):
{regen_ctx['git_diff']}

YOUR MISSION:
1. Read the git diff carefully to understand what files changed and how
2. For each changed file, read the NEW version to understand the current state
3. Cross-reference changes against existing documentation to identify:
   - Facts that are now WRONG (outdated info in docs)
   - New features/endpoints/configs that are MISSING from docs
   - Removed features that should be DELETED from docs
   - Structural changes that affect architecture descriptions
4. Check if any new files were added that introduce new concepts

Write your report to /tmp/scout_report_diff.md with this format:

## Scout Report: Change Analysis
### Summary of Changes
Brief overview of what changed in the codebase.

### Impact on Documentation
For each existing document, list what needs updating:

#### [Document Title]
- OUTDATED: [specific fact that is now wrong]
- MISSING: [new feature/endpoint/config not in docs]
- REMOVE: [feature that was deleted]
- OK: [section that is still accurate]

### New Files & Features
List any new files/features that may need documentation.

### Raw Data
- Files changed: [count]
- Commits since last gen: [count]
- Key changed files with brief descriptions

Be thorough but concise. Focus on WHAT CHANGED, not on describing the whole codebase."""

        print("\n[Scout] Running diff-focused change analysis...")
        try:
            conversation = self._Conversation(
                agent=self.scout_agent,
                workspace=str(self.repo_path),
                max_iteration_per_run=self._max_iters,
            )
            conversation.send_message(diff_prompt)
            conversation.run()

            report_path = Path("/tmp/scout_report_diff.md")
            if report_path.exists():
                report = report_path.read_text()
                print(f"   [Done] Diff scout: {len(report.splitlines())} lines")
                return report
            else:
                print("   [Warning] Diff scout did not produce a report")
                return "## Scout Report: Change Analysis\n### Key Findings\nNo report produced.\n"
        except Exception as e:
            logger.error("Diff scout failed: %s", e)
            return f"## Scout Report: Change Analysis\n### Key Findings\nScout failed: {e}\n"

    # ------------------------------------------------------------------
    # Internals: compression
    # ------------------------------------------------------------------

    def _compress_reports(
        self,
        reports_by_key: dict[str, str],
        target_chars: int = 15000,
    ) -> dict[str, str]:
        """Multi-pass report compression.

        Each pass can reliably compress ~2-3×. For very large report sets
        (100K+ chars), multiple passes are used with progressively stricter
        instructions to reach the target without losing critical facts.
        """
        if not reports_by_key:
            return reports_by_key

        total_chars = sum(len(r) for r in reports_by_key.values())
        if total_chars <= target_chars * 1.5:
            return reports_by_key

        # Determine passes needed (each pass compresses ~3×)
        compression_ratio = total_chars / target_chars
        if compression_ratio <= 3:
            passes = 1
        elif compression_ratio <= 9:
            passes = 2
        else:
            passes = 3  # 27× max (3^3)

        print(f"   [Compression] {total_chars:,} chars → ~{target_chars:,} target "
              f"({compression_ratio:.1f}× ratio, {passes} pass{'es' if passes > 1 else ''})")

        current = dict(reports_by_key)
        for pass_num in range(1, passes + 1):
            # Geometric progression: each pass targets an intermediate size
            remaining_passes = passes - pass_num
            pass_target = int(target_chars * (3 ** remaining_passes))
            pass_target = min(pass_target, sum(len(r) for r in current.values()))

            if pass_num > 1:
                current_total = sum(len(r) for r in current.values())
                print(f"   [Pass {pass_num}/{passes}] {current_total:,} → ~{pass_target:,} chars")

            current = self._compress_single_pass(current, pass_target, pass_num, passes)

        return current

    def _compress_single_pass(
        self,
        reports_by_key: dict[str, str],
        target_chars: int,
        pass_num: int = 1,
        total_passes: int = 1,
    ) -> dict[str, str]:
        """Single compression pass across all reports."""
        per_report_budget = target_chars // max(len(reports_by_key), 1)
        compressed: dict[str, str] = {}

        # Stricter instructions for later passes
        if pass_num >= total_passes and total_passes > 1:
            instruction = (
                f"Aggressively compress this report to ~{per_report_budget} characters. "
                f"Keep ONLY: file names, function/class names, endpoint paths, config keys, "
                f"architectural patterns, and technology choices. "
                f"Remove ALL prose descriptions, commentary, and examples. "
                f"Use terse notation: 'FastAPI REST, JWT auth, SQLAlchemy ORM' not full sentences."
            )
        elif pass_num > 1:
            instruction = (
                f"Compress this report to ~{per_report_budget} characters. "
                f"Preserve specific facts: file names, function names, endpoints, config keys. "
                f"Remove redundant phrasing and merge related points. Keep tables compact."
            )
        else:
            instruction = (
                f"Compress this scout report to ~{per_report_budget} characters. "
                f"Preserve ALL specific facts: file names, function names, endpoint paths, "
                f"config keys, library names, architecture decisions. "
                f"Remove general commentary and redundant phrasing. Keep tables and lists."
            )

        for key, report in reports_by_key.items():
            if len(report) <= per_report_budget * 1.5:
                compressed[key] = report
                continue

            try:
                prompt = f"{instruction}\n\n{report}"
                response = self.planner_llm.completion(
                    messages=[self._Message(role="user", content=[self._TextContent(text=prompt)])],
                )
                text = ""
                for block in response.message.content:
                    if hasattr(block, "text"):
                        text += block.text
                if text.strip():
                    compressed[key] = text.strip()
                    print(f"   [{key}] {len(report)} → {len(compressed[key])} chars")
                else:
                    compressed[key] = report
            except Exception as e:
                logger.warning("Compression failed for %s (%s), keeping original", key, e)
                compressed[key] = report

        return compressed


# ---------------------------------------------------------------------------
# Free functions (used by both ScoutRunner and the orchestrator)
# ---------------------------------------------------------------------------

def build_file_manifest_section(
    manifest: list[tuple[str, int]],
    scout_key: str,
    max_lines: int | None = None,
    budget_ratio: float = 1.0,
    total_files: int = 0,
) -> str:
    """Format the file manifest into a prompt section with focus hints.

    Files matching the scout's focus patterns are marked with ★.

    When *max_lines* is ``None`` (default), the limit is computed
    dynamically from *budget_ratio* so that larger repos get a
    proportionally larger view while still fitting in context.
    """
    if not manifest:
        return "FILE MANIFEST: (empty repository)\n"

    # Dynamic max_lines based on budget_ratio when not explicitly set
    if max_lines is None:
        n = total_files or len(manifest)
        if budget_ratio < 0.3:
            max_lines = min(n, 500)
        elif budget_ratio < 1.0:
            max_lines = min(n, 300)
        elif budget_ratio < 3.0:
            max_lines = min(n, 200)
        else:
            max_lines = min(n, 150)

    focus = SCOUT_FOCUS.get(scout_key, {})
    focus_patterns = focus.get("patterns", [])
    focus_desc = focus.get("description", "relevant files")

    def _is_focus(path: str) -> bool:
        path_lower = path.lower()
        return any(p.lower() in path_lower for p in focus_patterns)

    def _is_entry(path: str) -> bool:
        fname = Path(path).name
        return any(fname.startswith(p.rstrip(".")) or fname == p for p in ENTRY_POINT_PATTERNS)

    def _fmt_size(b: int) -> str:
        if b < 1024:
            return f"{b} B"
        elif b < 1024 * 1024:
            return f"{b / 1024:.1f} KB"
        return f"{b / (1024 * 1024):.1f} MB"

    lines = []
    focus_count = 0
    for path, size in manifest:
        is_f = _is_focus(path)
        if is_f:
            focus_count += 1
        marker = "★ " if is_f else "  "
        lines.append(f"  {marker}{path} — {_fmt_size(size)}")

    total_tokens = sum(s for _, s in manifest) // 4
    header = (
        f"FILE MANIFEST ({len(manifest)} files, ~{total_tokens:,} tokens total)\n"
        f"★ = FOCUS files for this scout ({focus_count} files matching: {focus_desc})\n"
    )

    if len(lines) > max_lines:
        # Priority order: focus files → entry points → largest files →
        # one representative per top-level directory
        focus_lines = [l for l in lines if l.strip().startswith("★")]
        remaining = max_lines - len(focus_lines) - 2

        # Entry points (not already in focus)
        entry_entries = [
            (p, s) for p, s in manifest
            if _is_entry(p) and not _is_focus(p)
        ]
        entry_entries.sort(key=lambda x: -x[1])
        entry_lines = [f"  ▸ {p} — {_fmt_size(s)}" for p, s in entry_entries[:max(0, remaining)]]
        remaining -= len(entry_lines)

        # Largest non-focus, non-entry files
        other_entries = [
            (p, s) for p, s in manifest
            if not _is_focus(p) and not _is_entry(p)
        ]
        other_entries.sort(key=lambda x: -x[1])

        # Reserve slots for directory representatives
        dir_reserve = min(remaining // 3, 20) if remaining > 10 else 0
        size_slots = max(0, remaining - dir_reserve)
        size_lines = [f"    {p} — {_fmt_size(s)}" for p, s in other_entries[:size_slots]]

        # One representative per top-level directory not yet covered
        covered_dirs: set[str] = set()
        for p, _ in manifest:
            if _is_focus(p) or _is_entry(p):
                td = p.split(os.sep)[0] if os.sep in p else "."
                covered_dirs.add(td)
        for p, s in other_entries[:size_slots]:
            td = p.split(os.sep)[0] if os.sep in p else "."
            covered_dirs.add(td)

        dir_lines: list[str] = []
        for p, s in other_entries[size_slots:]:
            td = p.split(os.sep)[0] if os.sep in p else "."
            if td not in covered_dirs and len(dir_lines) < dir_reserve:
                dir_lines.append(f"    {p} — {_fmt_size(s)}")
                covered_dirs.add(td)

        all_selected = focus_lines + entry_lines + size_lines + dir_lines
        omitted = len(lines) - len(all_selected)
        body = "\n".join(all_selected)
        if omitted > 0:
            body += f"\n  ... and {omitted} more files"
    else:
        body = "\n".join(lines)

    return header + body + "\n"


def build_constraints(budget_ratio: float) -> str:
    """Build context-aware constraints based on budget ratio."""
    lines = ["\nCONSTRAINTS:"]
    lines.append("- You already have the full file tree above. Do NOT run `find` or `ls -R` to discover files.")

    if budget_ratio < 0.3:
        lines.append("- Read files freely. The repo is small relative to your context.")
    elif budget_ratio < 1.0:
        lines.append("- Use `head -200 <file>` for files larger than 20 KB.")
        lines.append("- Focus on ★-marked files first. You may read other files to trace imports/dependencies.")
    else:
        lines.append("- Use `head -100 <file>` for files larger than 10 KB.")
        lines.append("- Do NOT read more than 8 files total. Focus strictly on ★-marked files.")
        lines.append("- The repo exceeds your context window. Be extremely selective.")

    lines.append("- Write your report before running out of turns.")
    return "\n".join(lines) + "\n"


def assign_module_scouts(
    module_map: dict[str, ModuleInfo],
    max_scouts: int | None = None,
    budget_ratio: float = 1.0,
) -> list[dict]:
    """Create per-module scout assignments using locality-aware bin-packing.

    When *max_scouts* is ``None``, the count is computed dynamically
    from the module count and ``SCOUT_PARALLEL`` env var so that the
    number of scouts scales with repository complexity.
    """
    if max_scouts is None:
        parallel_limit = int(os.getenv("SCOUT_PARALLEL", "4"))
        # Allow up to 3 waves of parallel scouts
        max_scouts = min(len(module_map), parallel_limit * 3)
        max_scouts = max(4, max_scouts)  # floor of 4

    sorted_modules = sorted(
        module_map.items(), key=lambda x: -x[1].total_bytes
    )

    if len(sorted_modules) <= max_scouts:
        return [
            {
                "name": mod_name.replace("/", "_"),
                "modules": [mod_name],
                "files": mod_info.files,
                "focus_description": (
                    f"Module '{mod_name}': {len(mod_info.files)} files, "
                    f"~{mod_info.token_estimate:,} tokens. "
                    f"Languages: {', '.join(sorted(mod_info.languages.keys()))}. "
                    + (f"Entry points: {', '.join(mod_info.entry_points[:3])}." if mod_info.entry_points else "")
                ),
            }
            for mod_name, mod_info in sorted_modules
        ]

    # Locality-aware bin-packing: prefer grouping modules that share
    # a parent directory into the same bucket for better coherence.
    buckets: list[dict] = [
        {"name": "", "modules": [], "files": [], "total_bytes": 0,
         "focus_description": "", "parents": set()}
        for _ in range(max_scouts)
    ]

    for mod_name, mod_info in sorted_modules:
        parent = mod_name.split("/")[0] if "/" in mod_name else mod_name

        # First try: find a bucket that already has a module from the same parent
        # AND is not the largest bucket (avoid overloading)
        best = None
        for b in buckets:
            if parent in b["parents"]:
                if best is None or b["total_bytes"] < best["total_bytes"]:
                    best = b

        # If no locality match or the matched bucket is already too large
        # (> 2× average), use the smallest bucket instead
        avg_bytes = sum(b["total_bytes"] for b in buckets) / max(len(buckets), 1)
        if best is None or (best["total_bytes"] > avg_bytes * 2 and avg_bytes > 0):
            best = min(buckets, key=lambda b: b["total_bytes"])

        best["modules"].append(mod_name)
        best["files"].extend(mod_info.files)
        best["total_bytes"] += mod_info.total_bytes
        best["parents"].add(parent)

    assignments = []
    for bucket in buckets:
        if not bucket["modules"]:
            continue
        primary = bucket["modules"][0]
        bucket["name"] = primary.replace("/", "_")
        mod_names = ", ".join(bucket["modules"])
        bucket["focus_description"] = (
            f"Modules: {mod_names} ({len(bucket['files'])} files, "
            f"~{bucket['total_bytes'] // 4:,} tokens)"
        )
        # Remove internal tracking field before returning
        bucket.pop("parents", None)
        assignments.append(bucket)

    return assignments


def build_module_scout_prompt(assignment: dict, budget_ratio: float) -> str:
    """Build a scout prompt focused on specific modules."""
    modules_str = ", ".join(assignment["modules"])
    file_list = ""
    for fpath, fsize in sorted(assignment["files"], key=lambda x: -x[1])[:FILE_ASSIGNMENT_LIMIT]:
        size_str = f"{fsize:,}" if fsize < 1024 else f"{fsize // 1024}KB"
        fname = Path(fpath).name
        is_entry = any(fname.startswith(p.rstrip(".")) or fname == p for p in ENTRY_POINT_PATTERNS)
        marker = "★ " if is_entry else "  "
        file_list += f"  {marker}{fpath} — {size_str}\n"
    if len(assignment["files"]) > 50:
        file_list += f"  ... and {len(assignment['files']) - 50} more files\n"

    constraints = build_constraints(budget_ratio)

    return f"""You are a documentation scout analyzing specific modules of a codebase.

YOUR ASSIGNED MODULES: {modules_str}
{assignment['focus_description']}

FILE MANIFEST (★ = entry points):
{file_list}

YOUR MISSION:
Explore these modules and write a comprehensive intelligence report covering:
1. **Structure**: How the module is organized, key directories, entry points
2. **Architecture**: Core abstractions, design patterns, data flow
3. **API Surface**: Public interfaces, endpoints, exported functions
4. **Dependencies**: What this module imports from and what imports it

CONSTRAINTS:
{constraints}

Write your report to: /tmp/scout_report_module_{assignment['name']}.md

FORMAT:
## Module Scout Report: {modules_str}

### Structure
(directory layout, key files, organization pattern)

### Architecture
(core classes/functions, design patterns, data flow)

### Public Interface
(exported APIs, endpoints, key functions users interact with)

### Dependencies
(what it depends on, what depends on it)

### Key Implementation Details
(notable algorithms, important constants, gotchas)
"""
