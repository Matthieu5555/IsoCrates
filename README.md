# IsoCrates

IsoCrates is a technical documentation platform that keeps your engineering knowledge organized, searchable, and current. Deploy it inside your organization and it becomes the single place where developers find authoritative documentation — generated from your actual codebases, enriched by human editors, and protected by the same access controls you use for everything else.

## What It Does for Your Firm

Every engineering organization accumulates documentation across wikis, READMEs, Confluence pages, and Notion databases. Over time, that documentation drifts from the code it describes. People stop trusting it, so they read the source directly — which is slow, doesn't scale across teams, and leaves tribal knowledge locked in the heads of the engineers who wrote the code.

IsoCrates solves this by connecting directly to your Git repositories. When code changes, documentation regenerates automatically, producing structured multi-page docs with accurate cross-references and diagrams. Human editors can refine the output at any time, and the system remembers their work — it won't overwrite manual improvements unless the underlying codebase changes substantially. The version priority engine tracks authorship (AI versus human) and makes intelligent decisions about when regeneration is warranted, achieving roughly a 70% skip rate on unchanged repositories and keeping LLM costs to around $0.50-2.00 per repo per cycle.

The result is a living documentation library that stays current without anyone maintaining it as a full-time job.

## What It Enables

**AI-generated documentation that respects human work.** Point the agent at a repository and it produces comprehensive technical documentation — architecture overviews, API references, getting-started guides — with tables, Mermaid diagrams, and wikilinks between pages. When a human edits a page, the system protects that work during subsequent regeneration cycles. Because the version priority engine distinguishes AI-authored content from human-authored content, it can regenerate stale AI pages while leaving recent human edits untouched, even within the same repository.

**Path-based access control.** Documents live in a folder hierarchy, and administrators grant access by path prefix. Give a team editor access to `backend-product-a/` and they can read and edit everything underneath it, while documents in `backend-product-b/` remain invisible to them. Permission checks run on every request — when auth is enabled, unauthenticated users see nothing rather than everything, because the system filters results by the caller's grants before returning data.

**Semantic and full-text search.** Every document carries a short AI-generated description that gets embedded as a vector. Search combines traditional full-text matching with semantic similarity through Reciprocal Rank Fusion, so developers find the right page whether they remember the exact terminology or just the general concept. The same search is exposed through an MCP server, which means AI coding assistants like Claude Code can query your documentation library directly from the IDE.

**GitHub webhook integration.** Configure a webhook on any repository and documentation regenerates on every push. The version priority engine evaluates whether regeneration is actually needed — skipping when docs are fresh and the repo hasn't changed meaningfully — so you pay only for genuine updates.

**Personal workspaces.** Each authenticated user can organize document references into their own folder structure without affecting the shared organizational tree. These personal trees are lenses into the same underlying documents, not copies, so they always reflect the latest content. Because personal folders are scoped to the user's token, one user's workspace is invisible to everyone else.

## How to Deploy

### Development

```bash
cp .env.example .env           # Configure LLM provider and API key
cd backend && uv run uvicorn app.main:app --reload   # Terminal 1
cd frontend && npm run dev                            # Terminal 2
```

The frontend serves at http://localhost:3000, the backend API at http://localhost:8000, and interactive API docs at http://localhost:8000/docs. Authentication is off by default so you can explore immediately.

### Production

```bash
cp .env.example .env
# Set: LLM_API_KEY, JWT_SECRET_KEY, AUTH_ENABLED=true,
#       CORS_ALLOWED_ORIGINS, GITHUB_WEBHOOK_SECRET
docker compose up -d --build
```

Place a reverse proxy (Caddy, nginx) in front for TLS. The [deployment guide](docs/DEPLOYING_AT_YOUR_ORGANIZATION.md) walks through secrets management, CORS, user provisioning, webhook setup, database options, and a complete security checklist.

### Verify

```bash
curl http://localhost:8000/health
# {"status":"healthy","database":"connected","uptime_seconds":...,"document_count":...}
```

## Technology

- **Backend:** Python, FastAPI, SQLAlchemy (SQLite for development, PostgreSQL for production)
- **Frontend:** Next.js 14, React, TypeScript, Tailwind CSS
- **Agent:** OpenHands SDK with configurable LLM providers (OpenRouter, Ollama, any OpenAI-compatible endpoint)
- **Search:** FTS5/PostgreSQL full-text + LiteLLM vector embeddings (pgvector)
- **Infrastructure:** Docker Compose, with optional Caddy for TLS

## Documentation

| Document | Purpose |
|----------|---------|
| [Architecture](ARCHITECTURE.md) | System design, data model, service layer, security model, and coding standards |
| [Deployment Guide](docs/DEPLOYING_AT_YOUR_ORGANIZATION.md) | Step-by-step production setup: secrets, auth, webhooks, database, and security checklist |
| [Usage Guide](USAGE_GUIDE.md) | How to use the product: folders, documents, search, personal trees, and API examples |
| [Changelog](CHANGELOG.md) | Version history and release notes |
| [Further Development](docs/FURTHER_DEVELOPMENT.md) | Roadmap and open tasks |
| [Frontend Style Guide](frontend/STYLE_GUIDE.md) | Design system and component variants |

## License

This project is licensed under the [MIT License](LICENSE).
