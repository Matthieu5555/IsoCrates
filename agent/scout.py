"""Scout agent orchestration: topic scouts, module scouts, diff scouts, compression.

Tier 0 of the three-tier pipeline. Scouts explore the repository and
produce structured intelligence reports for the planner.
"""

import dataclasses
import logging
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
    ) -> None:
        self.scout_agent = scout_agent
        self.planner_llm = planner_llm
        self.repo_path = repo_path
        self.crate = crate
        self._context_window = scout_context_window
        self._Conversation = conversation_cls
        self._Message = message_cls
        self._TextContent = text_content_cls
        self._max_iters = 60

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

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

        if len(combined) > 20000:
            print(f"[Scouts] Compressing reports for writers ({len(combined)} chars → ~15K)...")
            compressed_by_key = self._compress_reports(reports)
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

        reports: dict[str, str] = {}
        for idx, scout_key in enumerate(scouts_to_run, 1):
            scout_def = SCOUT_DEFINITIONS[scout_key]
            report_path = Path(f"/tmp/scout_report_{scout_key}.md")

            print(f"\n[Scout {idx}/{len(scouts_to_run)}] {scout_def['name']}...")

            manifest_section = build_file_manifest_section(
                metrics["file_manifest"], scout_key
            )
            prompt = scout_def["prompt"].format(
                repo_path=self.repo_path,
                file_manifest=manifest_section,
                constraints=build_constraints(budget_ratio),
            )

            try:
                conversation = self._Conversation(
                    agent=self.scout_agent,
                    workspace=str(self.repo_path),
                    max_iteration_per_run=self._max_iters,
                )
                conversation.send_message(prompt)
                conversation.run()

                if report_path.exists():
                    report_text = report_path.read_text()
                    reports[scout_key] = report_text
                    lines = len(report_text.strip().split("\n"))
                    print(f"   [Done] {scout_def['name']}: {lines} lines")
                else:
                    print(f"   [Warning] Scout {scout_key} did not produce a report")
                    reports[scout_key] = f"## Scout Report: {scout_def['name']}\n### Key Findings\nNo report produced.\n"

            except Exception as e:
                logger.error("Scout %s failed: %s", scout_key, e)
                reports[scout_key] = f"## Scout Report: {scout_def['name']}\n### Key Findings\nScout failed: {e}\n"

        return reports

    # ------------------------------------------------------------------
    # Internals: module-based scouting
    # ------------------------------------------------------------------

    def _run_module_scouts(
        self,
        module_map: dict[str, ModuleInfo],
        budget_ratio: float,
    ) -> dict[str, str]:
        assignments = assign_module_scouts(module_map)
        print(f"[Module Scouts] {len(assignments)} scouts for {len(module_map)} modules:")
        for a in assignments:
            print(f"   {a['name']}: {a['focus_description']}")

        reports: dict[str, str] = {}
        for idx, assignment in enumerate(assignments, 1):
            scout_key = f"module_{assignment['name']}"
            report_path = Path(f"/tmp/scout_report_{scout_key}.md")

            print(f"\n[Scout {idx}/{len(assignments)}] Module: {', '.join(assignment['modules'])}...")

            prompt = build_module_scout_prompt(assignment, budget_ratio)

            try:
                conversation = self._Conversation(
                    agent=self.scout_agent,
                    workspace=str(self.repo_path),
                    max_iteration_per_run=self._max_iters,
                )
                conversation.send_message(prompt)
                conversation.run()

                if report_path.exists():
                    report_content = report_path.read_text()
                    reports[scout_key] = report_content
                    print(f"   Report: {len(report_content)} chars")
                else:
                    print(f"   [Warning] No report file found at {report_path}")
                    reports[scout_key] = (
                        f"## Module Scout Report: {', '.join(assignment['modules'])}\n"
                        f"### Key Findings\nNo report produced.\n"
                    )

            except Exception as e:
                logger.error("Module scout failed: %s", e)
                reports[scout_key] = (
                    f"## Module Scout Report: {', '.join(assignment['modules'])}\n"
                    f"### Key Findings\nScout failed: {e}\n"
                )

        return reports

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
        if not reports_by_key:
            return reports_by_key

        per_report_budget = target_chars // max(len(reports_by_key), 1)
        compressed: dict[str, str] = {}

        for key, report in reports_by_key.items():
            if len(report) <= per_report_budget * 1.5:
                compressed[key] = report
                continue

            try:
                prompt = (
                    f"Compress this scout report to ~{per_report_budget} characters. "
                    f"Preserve ALL specific facts: file names, function names, endpoint paths, "
                    f"config keys, library names, architecture decisions. "
                    f"Remove general commentary and redundant phrasing. Keep tables and lists.\n\n"
                    f"{report}"
                )
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
    max_lines: int = 100,
) -> str:
    """Format the file manifest into a prompt section with focus hints.

    Files matching the scout's focus patterns are marked with ★.
    """
    if not manifest:
        return "FILE MANIFEST: (empty repository)\n"

    focus = SCOUT_FOCUS.get(scout_key, {})
    focus_patterns = focus.get("patterns", [])
    focus_desc = focus.get("description", "relevant files")

    def _is_focus(path: str) -> bool:
        path_lower = path.lower()
        return any(p.lower() in path_lower for p in focus_patterns)

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
        focus_lines = [l for l in lines if l.strip().startswith("★")]
        other_entries = [(p, s) for p, s in manifest if not _is_focus(p)]
        other_entries.sort(key=lambda x: -x[1])
        remaining = max_lines - len(focus_lines) - 2
        other_lines = [f"    {p} — {_fmt_size(s)}" for p, s in other_entries[:max(0, remaining)]]
        omitted = len(lines) - len(focus_lines) - len(other_lines)
        body = "\n".join(focus_lines + other_lines)
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
    max_scouts: int = 8,
) -> list[dict]:
    """Create per-module scout assignments using bin-packing."""
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

    buckets: list[dict] = [
        {"name": "", "modules": [], "files": [], "total_bytes": 0, "focus_description": ""}
        for _ in range(max_scouts)
    ]

    for mod_name, mod_info in sorted_modules:
        smallest = min(buckets, key=lambda b: b["total_bytes"])
        smallest["modules"].append(mod_name)
        smallest["files"].extend(mod_info.files)
        smallest["total_bytes"] += mod_info.total_bytes

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
