# Choosing an LLM Provider

IsoCrates uses LLMs for three jobs: **scouting** (fast scan of repo files), **planning** (outlining which docs to write), and **writing** (producing the actual documentation). Each job can use a different model, or they can all share one. This page helps you pick a setup and estimate costs.

---

## Provider Comparison

| Provider | Setup | Cost | Latency | Best for |
|----------|-------|------|---------|----------|
| [OpenRouter](https://openrouter.ai/) | Sign up, get API key | Pay-per-token | Low | Getting started fast. One key gives access to dozens of models. |
| [Ollama](https://ollama.com/) (self-hosted) | Install on a machine with a GPU | Free (you pay for hardware) | Depends on GPU | Teams that cannot send code to external APIs. |
| OpenAI-compatible endpoint | Varies | Varies | Varies | Organizations already running vLLM, TGI, or a similar inference server. |

If you are deploying IsoCrates for the first time and just want it to work, **start with OpenRouter**. You can switch providers later without changing any application code — only the environment variables change.

---

## Recommended Starter Configuration (OpenRouter)

These models balance cost, speed, and output quality. The scout and writer use a fast coding model; the planner uses a stronger reasoning model since it makes the structural decisions that determine doc quality.

```bash
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=sk-or-v1-your-key-here
SCOUT_MODEL=openrouter/mistralai/devstral-2512
PLANNER_MODEL=openrouter/mistralai/mistral-medium-latest
WRITER_MODEL=openrouter/mistralai/devstral-2512
```

### Cost estimate

A typical documentation run costs **$0.50 to $2.00 per repository**, depending on repo size. The version priority engine skips roughly 70% of content each cycle because it has not changed meaningfully, so subsequent runs after the initial generation cost less. A team with 10 repositories running daily would spend roughly $50 to $150 per month, though most of that concentrates on the first run.

---

## Self-Hosted Configuration (Ollama)

If your code cannot leave your network, run models locally with Ollama. You need a machine with at least 24 GB of VRAM for the 30B-parameter models below. Smaller models (7B) work on less hardware but produce noticeably lower quality documentation.

```bash
LLM_BASE_URL=http://your-gpu-server:11434
SCOUT_MODEL=ollama_chat/qwen3-coder:30b
PLANNER_MODEL=ollama_chat/mistral-small:24b
WRITER_MODEL=ollama_chat/qwen3-coder:30b
```

Pull the models first:

```bash
ollama pull qwen3-coder:30b
ollama pull mistral-small:24b
```

---

## Mixing Providers

You can point each tier at a different provider. A common pattern is to run scouts and writers locally (where speed matters more than reasoning) and use a cloud model for the planner (where reasoning quality matters most):

```bash
# Local scouts and writers
LLM_BASE_URL=http://localhost:11434
SCOUT_MODEL=ollama_chat/qwen3-coder:30b
WRITER_MODEL=ollama_chat/qwen3-coder:30b

# Cloud planner
PLANNER_MODEL=openrouter/anthropic/claude-sonnet-4-20250514
PLANNER_BASE_URL=https://openrouter.ai/api/v1
PLANNER_API_KEY=sk-or-v1-your-key-here
```

Each tier accepts its own `*_BASE_URL` and `*_API_KEY` overrides. If a tier does not specify its own, it falls back to the global `LLM_BASE_URL` and `LLM_API_KEY`.

---

## Adding a New Model

Models must be recognized by either LiteLLM's registry or the override table in `agent/model_config.py`. If you try to use an unrecognized model, the agent will fail at startup with a clear error listing the known models.

To add a model that LiteLLM does not know about, add an entry to `MODEL_OVERRIDES` in `agent/model_config.py`:

```python
"your-org/your-model": ModelConfig(
    context_window=131_072,
    max_output_tokens=8_192,
    supports_tool_calling=True,
),
```

The key is the model identifier without the provider prefix (e.g., `mistralai/devstral-2512`, not `openrouter/mistralai/devstral-2512`).

---

## Embedding Providers (Semantic Search)

Embeddings power the vector similarity half of search. They are optional — full-text search works without them. If you enable embeddings, you need PostgreSQL with the pgvector extension (the Docker Compose setup handles this automatically).

| Provider | Model string | Dimensions | Notes |
|----------|-------------|------------|-------|
| OpenAI | `openai/text-embedding-3-small` | 1536 | Good default, low cost |
| Cohere | `cohere/embed-english-v3.0` | 1024 | Strong multilingual support |
| Ollama | `ollama/nomic-embed-text` | 768 | Free, runs locally |

```bash
EMBEDDING_MODEL=openai/text-embedding-3-small
EMBEDDING_API_KEY=sk-your-openai-key
```

---

## Testing Your Configuration

The agent validates its model configuration at startup. If a model is unreachable or not recognized by either LiteLLM or the override table in `agent/model_config.py`, the agent logs a clear error with the model name and endpoint it tried to contact. To trigger this validation without waiting for a webhook, run a manual generation against a small repository:

```bash
docker exec doc-agent python openhands_doc.py \
  --repo https://github.com/a-small-public-repo
```

Watch the logs for errors: `docker compose logs -f doc-agent`.
