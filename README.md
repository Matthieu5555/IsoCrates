# IsoCrates

IsoCrates auto-generates and maintains technical documentation from your Git repositories. Deploy it internally and every push keeps your docs current, with access controls, semantic search, and an MCP server your AI coding tools can query directly.

## Why Deploy This

Documentation drifts from code the way a printed map drifts from a growing city. People stop trusting it and read source directly, but that is slow, does not scale, and locks knowledge in the heads of whoever wrote the code. IsoCrates connects to your Git repos and regenerates docs automatically when code changes. Think of it like a translator sitting between your codebase and your team: code goes in, readable docs come out, and they stay up to date on their own.

Human edits are preserved. The version priority engine tells AI-authored content apart from human-authored content and only regenerates what is actually stale (roughly 70% of content is skipped each cycle, costing about $0.50 to $2.00 per repo per run).

## Features

IsoCrates produces architecture overviews, API references, and getting-started guides complete with tables, Mermaid diagrams, and cross-reference wikilinks. Human edits survive regeneration cycles because the system knows which paragraphs a person wrote and leaves them alone.

Access control is path-based. You grant access by folder prefix (e.g. `backend-product-a/`), and when auth is enabled users only see the documents they have been granted. Think of it like file-system permissions but for your documentation tree.

Search combines full-text search with vector similarity through Reciprocal Rank Fusion, giving you results that match both keywords and meaning. This is exposed through an MCP server so AI coding assistants (like Cursor or Claude Code) can query your docs from the IDE without switching context.

Docs regenerate on push via GitHub webhooks. The version priority engine checks whether a repo has changed meaningfully before spending tokens, so unchanged repos are skipped automatically.

Users can also organize document references into personal folder trees, a private workspace that does not affect the shared hierarchy.

## How to Deploy

### Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.13+ | Backend runtime |
| [uv](https://docs.astral.sh/uv/) | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js | 18+ | Frontend runtime |
| LLM API key | any | OpenRouter, OpenAI, or local Ollama |
| Docker & Compose | latest | Production only |
| PostgreSQL | 15+ | Production only (dev uses SQLite) |

### Development

```bash
cp .env.example .env                                  # Defaults work; LLM key only needed for doc generation
cd backend && uv sync && cd ..                        # Install Python dependencies
cd frontend && npm install && cd ..                   # Install JS dependencies
```

Then, in two separate terminals (both from repo root):

```bash
cd backend && uv run uvicorn app.main:app --reload    # Terminal 1: API on localhost:8000
cd frontend && npm run dev                            # Terminal 2: UI on localhost:3000
```

Frontend at `localhost:3000`, API at `localhost:8000`, interactive docs at `localhost:8000/docs`. Auth is off by default. The app runs without an LLM key; you just cannot generate docs until you configure one in `.env`.

### Production

The interactive deploy script handles secrets, Caddyfile generation, and TLS:

```bash
./scripts/deploy.sh
```

Or manually:

```bash
cp .env.example .env
# Required - the app refuses to start in production without these:
#   ENVIRONMENT=production
#   LLM_API_KEY           - your LLM provider key
#   JWT_SECRET_KEY        - generate with: openssl rand -hex 32
#   AUTH_ENABLED=true
#   CORS_ALLOWED_ORIGINS  - your frontend URL (e.g. https://docs.yourcompany.com)
#   GITHUB_WEBHOOK_SECRET - generate with: openssl rand -hex 20
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

To include AI documentation generation, add `--profile agent`:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile agent up -d --build
```

See the [deployment guide](docs/DEPLOYING_AT_YOUR_ORGANIZATION.md) for DNS, user provisioning, webhooks, and the full walkthrough.

### Verify

```bash
# Development:
curl http://localhost:8000/health

# Production (behind Caddy):
curl https://your-domain.com/health

# Expected:
# {"status":"healthy","database":"connected","uptime_seconds":...}
```

## Technology

The backend is Python with FastAPI and SQLAlchemy (SQLite in development, PostgreSQL in production). The frontend is Next.js 14 with React, TypeScript, and Tailwind CSS. The documentation agent uses the OpenHands SDK and supports configurable LLM providers including OpenRouter, Ollama, and any OpenAI-compatible endpoint. Search uses FTS5 (or PostgreSQL full-text) combined with LiteLLM embeddings stored in pgvector. Infrastructure runs on Docker Compose with optional Caddy for TLS.

## Documentation

| Document | Purpose |
|----------|---------|
| [Architecture](docs/ARCHITECTURE.md) | System design, data model, security model |
| [Deployment Guide](docs/DEPLOYING_AT_YOUR_ORGANIZATION.md) | Production setup: secrets, auth, webhooks, database, security checklist |
| [Usage Guide](docs/USAGE_GUIDE.md) | Folders, documents, search, personal trees, API examples |
| [Changelog](docs/CHANGELOG.md) | Version history and release notes |
| [Further Development](docs/FURTHER_DEVELOPMENT.md) | Roadmap and open tasks |

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError` on backend start | Dependencies missing | `cd backend && uv sync` |
| `npm ERR!` on frontend start | Dependencies missing | `cd frontend && npm install` |
| Port 8000/3000 in use | Conflicting process | `lsof -ti:8000 \| xargs kill` |
| Model errors on agent run | LLM config missing in `.env` | Set `LLM_BASE_URL`, `LLM_API_KEY`, `SCOUT_MODEL`, `PLANNER_MODEL`, `WRITER_MODEL` (see `.env.example`) |
| `Unrecognized model` at startup | Model string not in LiteLLM registry | Use a supported string (e.g. `openrouter/mistralai/devstral-2512`) or add to `agent/model_config.py` |
| CORS errors in browser | Frontend origin not in allowlist | Add your origin to `CORS_ALLOWED_ORIGINS` in `.env` |
| 401/403 on every request | Auth on, no user created | `POST /api/auth/register` to create a user, or set `AUTH_ENABLED=false` for dev |
| Webhooks not triggering | Server unreachable or secret mismatch | Check public reachability and that `GITHUB_WEBHOOK_SECRET` matches GitHub |
| DB migration errors after update | Schema changed | `cd backend && uv run alembic upgrade head` |
| Semantic search returns nothing | Embeddings not configured | Set `EMBEDDING_MODEL` + `EMBEDDING_API_KEY` (requires PostgreSQL with pgvector) |

For production issues (TLS, Docker networking, user provisioning), see the [Deployment Guide](docs/DEPLOYING_AT_YOUR_ORGANIZATION.md).

## License

[MIT License](LICENSE)
