"""
Parallel scout agent pool for Tier 0 repository exploration.

Manages the creation of independent scout Agent instances and orchestrates
their parallel execution using ThreadPoolExecutor. Mirrors the WriterPool
pattern: each thread gets its own Agent/LLM/Condenser to avoid shared state.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from openhands.sdk import LLM, Agent, Tool
from openhands.sdk.context.condenser import LLMSummarizingCondenser
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.terminal import TerminalTool

from model_config import ModelConfig
from prompts import SCOUT_CONDENSER_DIVISOR

logger = logging.getLogger("isocrates.agent.scout_pool")

# Default parallelism for scouts
SCOUT_PARALLEL_DEFAULT = 4


class ScoutPool:
    """Creates and orchestrates parallel scout agents.

    Responsibilities:
      - Create independent Agent/LLM/Condenser instances per thread
      - Run scout tasks in parallel, collecting reports by key
      - Handle per-scout failures without aborting the entire pool

    Args:
        scout_config: Resolved ModelConfig for the scout model.
        scout_model: Model name string (e.g. "mistralai/devstral-2512").
        native_tool_calling: Whether to use native tool calling.
        llm_kwargs_fn: Callable that returns LLM constructor kwargs for a tier.
            Signature: (tier: str) -> dict. Called with "SCOUT".
    """

    def __init__(
        self,
        scout_config: ModelConfig,
        scout_model: str,
        native_tool_calling: bool,
        llm_kwargs_fn: Callable[[str], dict],
    ) -> None:
        self._scout_config = scout_config
        self._scout_model = scout_model
        self._native_tool_calling = native_tool_calling
        self._llm_kwargs_fn = llm_kwargs_fn

    def create_scout_agent(self) -> Agent:
        """Create an independent Scout Agent + LLM for thread-safe parallel use.

        Each parallel scout thread needs its own Agent/LLM/Condenser
        to avoid shared state between concurrent conversations.

        Returns:
            A new Agent instance with its own LLM and condenser.
        """
        scout_kwargs = self._llm_kwargs_fn("SCOUT")
        llm = LLM(
            model=self._scout_model,
            native_tool_calling=self._native_tool_calling,
            timeout=900,
            max_output_tokens=self._scout_config.max_output_tokens,
            litellm_extra_body=self._scout_config.extra_body or {},
            **self._scout_config.extra_llm_kwargs,
            **scout_kwargs,
        )
        condenser_size = max(20, self._scout_config.context_window // SCOUT_CONDENSER_DIVISOR)
        condenser = LLMSummarizingCondenser(
            llm=llm, max_size=condenser_size, keep_first=2,
        )
        return Agent(
            llm=llm,
            tools=[
                Tool(name=TerminalTool.name),
                Tool(name=FileEditorTool.name),
            ],
            condenser=condenser,
        )

    def run_parallel(
        self,
        scout_tasks: list[dict[str, Any]],
        run_one_fn: Callable[[dict, Agent], tuple[str, str]],
        max_workers: int | None = None,
    ) -> dict[str, str]:
        """Run scout tasks in parallel using ThreadPoolExecutor.

        Args:
            scout_tasks: List of scout task dicts. Each must have a "key" field
                used to identify the report in the results.
            run_one_fn: Callable(task_dict, agent) -> (key, report_text).
                Executed in a worker thread with an independent agent.
            max_workers: Maximum parallel threads. Defaults to SCOUT_PARALLEL env var.

        Returns:
            Dict mapping scout key → report text.
        """
        if max_workers is None:
            max_workers = int(os.getenv("SCOUT_PARALLEL", str(SCOUT_PARALLEL_DEFAULT)))

        total = len(scout_tasks)
        reports: dict[str, str] = {}

        logger.info("Running %d scouts (max %d parallel)...", total, max_workers)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for task in scout_tasks:
                agent = self.create_scout_agent()
                future = executor.submit(run_one_fn, task, agent)
                futures[future] = task.get("key", "unknown")

            for future in as_completed(futures):
                task_key = futures[future]
                try:
                    key, report_text = future.result()
                    reports[key] = report_text
                    logger.info("Scout %s: %d chars", key, len(report_text))
                except Exception as e:
                    logger.error("Scout thread failed for %s: %s", task_key, e)
                    reports[task_key] = (
                        f"## Scout Report: {task_key}\n"
                        f"### Key Findings\nScout failed: {e}\n"
                        f"### Status: FAILED\n"
                    )

        return reports
