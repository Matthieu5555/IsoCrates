"""
Model configuration and constraint resolution.

Single source of truth for LLM model limits and provider-specific parameters.
Litellm's model registry is often wrong for OpenRouter-hosted models (e.g.,
reporting 262K max_output for kimi-k2.5 which only supports 8K). This module
provides an override table for known models and falls back to litellm.

If a model is not in the override table AND litellm cannot resolve it,
resolve_model_config() raises ModelConfigError rather than silently returning
conservative defaults. Wrong context_window values cascade into incorrect
budget ratios, condenser sizing, and scout constraints — silent fallback
here causes subtle quality degradation with no indication of the cause.

Provider-specific quirks (e.g., Kimi's thinking mode) live here — not in the
agent code. The agent constructs LLMs using config values, so swapping models
never requires touching agent code.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("isocrates.agent")


class ModelConfigError(ValueError):
    """Model not found in override table or litellm registry.

    Raised by resolve_model_config() when a model string cannot be resolved
    to a known configuration. The error message includes the model name,
    available overrides, and instructions for adding a new entry.
    """


@dataclass(frozen=True)
class ModelConfig:
    """Constraints and provider quirks for a specific LLM model."""

    context_window: int        # max input tokens the model accepts
    max_output_tokens: int     # actual provider limit for completions
    supports_tool_calling: bool

    # Provider-specific request body params → litellm_extra_body on LLM()
    extra_body: dict[str, Any] = field(default_factory=dict)

    # Additional LLM() constructor kwargs (e.g., reasoning_effort)
    extra_llm_kwargs: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        parts = [
            f"ctx={self.context_window:,}",
            f"out={self.max_output_tokens:,}",
            f"tools={'yes' if self.supports_tool_calling else 'no'}",
        ]
        if self.extra_body:
            parts.append(f"extra_body={self.extra_body}")
        if self.extra_llm_kwargs:
            parts.append(f"extra_kwargs={self.extra_llm_kwargs}")
        return " ".join(parts)


# ──────────────────────────────────────────────────────────────────────
# Override table for models where litellm reports incorrect values or
# that require provider-specific parameters.
# Keys are the model identifier WITHOUT the provider prefix
# (e.g., "moonshotai/kimi-k2.5" not "openrouter/moonshotai/kimi-k2.5").
# ──────────────────────────────────────────────────────────────────────

MODEL_OVERRIDES: dict[str, ModelConfig] = {
    # Kimi K2.5: litellm says 262K output, OpenRouter actually supports 8K.
    # Moonshot AI auto-enables "thinking mode" which breaks multi-turn tool
    # calling — disable it via extra_body.
    "moonshotai/kimi-k2.5": ModelConfig(
        context_window=131_072,
        max_output_tokens=8_192,
        supports_tool_calling=True,
        extra_body={"thinking": {"type": "disabled"}},
        extra_llm_kwargs={"reasoning_effort": "none", "enable_encrypted_reasoning": False},
    ),
    # Kimi K2 Thinking: thinking mode is intentional here — no override needed
    "moonshotai/kimi-k2-thinking": ModelConfig(
        context_window=131_072,
        max_output_tokens=64_000,
        supports_tool_calling=True,
    ),
    # Devstral
    "mistralai/devstral-2512": ModelConfig(
        context_window=131_072,
        max_output_tokens=8_192,
        supports_tool_calling=True,
    ),
    # MiniMax M2.1
    "minimax/minimax-m2.1": ModelConfig(
        context_window=1_048_576,
        max_output_tokens=16_384,
        supports_tool_calling=True,
    ),
    # Qwen3 Coder (Ollama, common local model)
    "qwen3-coder:30b": ModelConfig(
        context_window=32_768,
        max_output_tokens=8_192,
        supports_tool_calling=True,
    ),
    # Mistral Small 24B (Ollama)
    "mistral-small:24b": ModelConfig(
        context_window=32_768,
        max_output_tokens=8_192,
        supports_tool_calling=True,
    ),
}

# Conservative fallback when model is completely unknown
_DEFAULT_CONFIG = ModelConfig(
    context_window=32_768,
    max_output_tokens=4_096,
    supports_tool_calling=True,
)


def _strip_provider_prefix(model: str) -> str:
    """Strip provider routing prefixes like 'openrouter/' or 'ollama/'.

    Examples:
        'openrouter/moonshotai/kimi-k2.5' → 'moonshotai/kimi-k2.5'
        'ollama/qwen3-coder:30b'          → 'qwen3-coder:30b'
        'mistralai/devstral-2512'         → 'mistralai/devstral-2512'
    """
    PROVIDER_PREFIXES = ("openrouter/", "openai/", "ollama/", "ollama_chat/", "litellm_proxy/", "hosted_vllm/")
    for prefix in PROVIDER_PREFIXES:
        if model.startswith(prefix):
            return model[len(prefix):]
    return model


def resolve_model_config(model: str) -> ModelConfig:
    """Resolve the actual constraints for a model.

    Resolution order:
    1. Check override table (exact match after stripping provider prefix)
    2. Query litellm's model registry
    3. Raise ModelConfigError — no silent defaults

    Raises:
        ModelConfigError: If the model is not in the override table and
            litellm cannot resolve it. Lists available models in the message.
    """
    bare = _strip_provider_prefix(model)

    # 1. Override table
    if bare in MODEL_OVERRIDES:
        return MODEL_OVERRIDES[bare]

    # 2. Litellm lookup
    try:
        import litellm
        info = litellm.get_model_info(model)
        if info:
            ctx = info.get("max_input_tokens") or info.get("max_tokens") or _DEFAULT_CONFIG.context_window
            out = info.get("max_output_tokens") or _DEFAULT_CONFIG.max_output_tokens
            # Sanity: max_output should never exceed context window
            if out > ctx:
                out = min(out, ctx // 2)
            return ModelConfig(
                context_window=ctx,
                max_output_tokens=out,
                supports_tool_calling=info.get("supports_function_calling", True),
            )
    except Exception as e:
        logger.warning("litellm lookup failed for '%s': %s", model, e)

    # 3. No silent defaults — fail explicitly so the user knows.
    available = ", ".join(sorted(MODEL_OVERRIDES.keys()))
    raise ModelConfigError(
        f"Model '{model}' (bare: '{bare}') not found in override table or litellm registry. "
        f"The system cannot determine context_window and max_output_tokens for this model.\n"
        f"Add an entry to MODEL_OVERRIDES in agent/model_config.py.\n"
        f"Known models: {available}"
    )
