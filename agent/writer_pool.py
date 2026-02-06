"""
Parallel writer agent pool for Tier 2 document generation.

Manages the creation of independent writer Agent instances and orchestrates
their parallel execution using ThreadPoolExecutor. Writers are divided into
two waves: detail pages first (parallel), then hub pages (also parallel)
after detail pages complete since hub pages reference them.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from openhands.sdk import LLM, Agent, Tool
from openhands.sdk.context.condenser import LLMSummarizingCondenser
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.task_tracker import TaskTrackerTool
from openhands.tools.terminal import TerminalTool

from model_config import ModelConfig

logger = logging.getLogger("isocrates.agent.writer_pool")

# Hub page types that should run after detail pages
_HUB_TYPES = frozenset({"overview", "capabilities", "quickstart"})


class WriterPool:
    """Creates and orchestrates parallel writer agents.

    Responsibilities:
      - Create independent Agent/LLM/Condenser instances per thread
      - Run detail pages in parallel, then hub pages in parallel after
      - Collect and aggregate results, tracking IDs and stats

    Args:
        writer_config: Resolved ModelConfig for the writer model.
        writer_model: Model name string (e.g. "mistralai/devstral-2512").
        native_tool_calling: Whether to use native tool calling.
        llm_kwargs_fn: Callable that returns LLM constructor kwargs for a tier.
            Signature: (tier: str) -> dict. Called with "WRITER".
    """

    def __init__(
        self,
        writer_config: ModelConfig,
        writer_model: str,
        native_tool_calling: bool,
        llm_kwargs_fn: Callable[[str], dict],
    ) -> None:
        self._writer_config = writer_config
        self._writer_model = writer_model
        self._native_tool_calling = native_tool_calling
        self._llm_kwargs_fn = llm_kwargs_fn

    def create_writer_agent(self) -> Agent:
        """Create an independent Writer Agent + LLM for thread-safe parallel use.

        Each parallel writer thread needs its own Agent/LLM/Condenser
        to avoid shared state between concurrent conversations.

        Returns:
            A new Agent instance with its own LLM and condenser.
        """
        writer_kwargs = self._llm_kwargs_fn("WRITER")
        llm = LLM(
            model=self._writer_model,
            native_tool_calling=self._native_tool_calling,
            timeout=900,
            max_output_tokens=self._writer_config.max_output_tokens,
            litellm_extra_body=self._writer_config.extra_body or {},
            **self._writer_config.extra_llm_kwargs,
            **writer_kwargs,
        )
        condenser_size = max(20, self._writer_config.context_window // 4000)
        condenser = LLMSummarizingCondenser(
            llm=llm, max_size=condenser_size, keep_first=2,
        )
        return Agent(
            llm=llm,
            tools=[
                Tool(name=TerminalTool.name),
                Tool(name=FileEditorTool.name),
                Tool(name=TaskTrackerTool.name),
            ],
            condenser=condenser,
        )

    def run_parallel(
        self,
        documents: list[dict[str, Any]],
        generate_fn: Callable[[dict, Agent | None], dict],
        max_workers: int = 3,
    ) -> tuple[dict[str, dict], set[str], set[str], dict[str, int]]:
        """Run writer agents in parallel using ThreadPoolExecutor.

        Writers are divided into two waves:
          Wave 1: Detail/leaf pages (can all run in parallel)
          Wave 2: Hub pages (overview, capabilities, quickstart) -- run in
                  parallel after wave 1 completes since they reference detail pages

        Args:
            documents: List of doc specs from the planner blueprint.
            generate_fn: Callable(doc_spec, writer_agent) -> result dict.
                This is the per-document generation function (e.g.
                OpenHandsDocGenerator.generate_document bound with other args).
            max_workers: Maximum number of parallel writer threads.

        Returns:
            Tuple of (results_dict, generated_ids, failed_ids, id_stats).
        """
        detail_docs = [d for d in documents if d.get("doc_type") not in _HUB_TYPES]
        hub_docs = [d for d in documents if d.get("doc_type") in _HUB_TYPES]

        results: dict[str, dict] = {}
        generated_ids: set[str] = set()
        failed_ids: set[str] = set()
        id_stats: dict[str, int] = {"reused": 0, "new": 0, "renamed": 0}
        total = len(documents)

        def _process_result(doc_title: str, result: dict) -> None:
            """Track a single result (called from main thread)."""
            results[doc_title] = result
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

        def _run_one(
            doc_spec: dict, idx: int, agent: Agent
        ) -> tuple[str, dict]:
            """Run a single writer in a thread. Returns (title, result)."""
            print(f"\n[{idx}/{total}] Dispatching writer for: {doc_spec['title']}")
            result = generate_fn(doc_spec, agent)
            return doc_spec["title"], result

        # Wave 1: Detail pages in parallel
        if detail_docs:
            print(
                f"\n[Wave 1] {len(detail_docs)} detail pages "
                f"(max {max_workers} parallel)..."
            )
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {}
                for idx, doc_spec in enumerate(detail_docs, 1):
                    agent = self.create_writer_agent()
                    future = executor.submit(_run_one, doc_spec, idx, agent)
                    futures[future] = doc_spec["title"]

                for future in as_completed(futures):
                    try:
                        title, result = future.result()
                        _process_result(title, result)
                    except Exception as e:
                        title = futures[future]
                        logger.error(
                            "Writer thread failed for %s: %s", title, e
                        )
                        _process_result(
                            title, {"status": "error", "error": str(e)}
                        )

        # Wave 2: Hub pages after detail pages complete (they reference everything).
        # Hub pages can run in parallel with each other — cross-references are
        # resolved at upload time, not generation time.
        if hub_docs:
            offset = len(detail_docs)
            print(
                f"\n[Wave 2] {len(hub_docs)} hub pages "
                f"(max {max_workers} parallel, after detail pages)..."
            )
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {}
                for idx, doc_spec in enumerate(hub_docs, offset + 1):
                    agent = self.create_writer_agent()
                    future = executor.submit(_run_one, doc_spec, idx, agent)
                    futures[future] = doc_spec["title"]

                for future in as_completed(futures):
                    try:
                        title, result = future.result()
                        _process_result(title, result)
                    except Exception as e:
                        title = futures[future]
                        logger.error(
                            "Writer thread failed for %s: %s", title, e
                        )
                        _process_result(
                            title, {"status": "error", "error": str(e)}
                        )

        return results, generated_ids, failed_ids, id_stats
