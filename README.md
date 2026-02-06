# IsoCrates

AI-powered technical documentation platform with version tracking, intelligent regeneration, and enterprise-grade security.

## What It Does

IsoCrates generates comprehensive technical documentation using AI agents (OpenHands), stores it in a REST API backend (FastAPI + SQLite), and provides a web interface (Next.js) for viewing, editing, and organizing documentation. It tracks versions with AI vs human authorship and respects human edits during regeneration.

## Quick Start

```bash
# Development (recommended -- local backend/frontend, Docker agent)
./dev-backend.sh     # Terminal 1
./dev-frontend.sh    # Terminal 2
docker compose -f docker-compose.dev.yml up -d   # Terminal 3 (agent)

# Production (all services in Docker)
cp .env.example .env   # Configure OPENROUTER_API_KEY, CORS_ALLOWED_ORIGINS
docker compose up -d --build
```

Frontend: http://localhost:3000 (dev) or http://localhost:3001 (Docker)
Backend: http://localhost:8000
Health: `curl http://localhost:8000/health` (returns status, db, uptime, version, document_count)
API Docs: http://localhost:8000/docs (Swagger UI)

## Component Status

### Backend (100%)

| Component | Status | Notes |
|-----------|--------|-------|
| Database Models | Done | Document, Version, Dependency, FolderMetadata, User, Personal* |
| API Endpoints | Done | Documents, Versions, Dependencies, Folders, Tree, Search, Personal |
| Business Logic | Done | Deep module pattern, service layer abstraction |
| Error Handling | Done | 8 exception classes, structured JSON responses |
| Configuration | Done | Pydantic validation, CORS protection |
| Authentication | Done | JWT (HMAC-SHA256), require_auth/optional_auth, dev-mode bypass |
| Rate Limiting | Done | Token bucket (60 req/min/client), 429 with Retry-After |
| Logging | Done | Structured JSON logging, request-id propagation via contextvars |
| Middleware | Done | Request-ID, timing, rate limiting, structured request logs |
| Database Indexes | Done | All key columns indexed, idempotent migration |
| OpenAPI | Done | Descriptions, examples, security scheme on all endpoints |
| Testing | Done | 34 pytest tests, in-memory SQLite, per-test rollback |
| Migrations | Done | SQL migrations with rollback support |
| Security | Done | Input validation, Docker hardening |

### Frontend (100%)

| Component | Status | Notes |
|-----------|--------|-------|
| Document Viewer | Done | Markdown rendering, syntax highlighting, Mermaid diagrams |
| Tree Navigation | Done | Drag-and-drop, context menus, visual hierarchy |
| Personal Tree | Done | Org/Personal tab switching, document references |
| Search UI | Done | CMD+K command palette, keyboard navigation |
| Version History | Done | Version list with author tracking |
| Folder Management | Done | Create, move, delete with confirmations |
| Design System | Done | Centralized variant library |
| Notifications | Done | Toast notifications (non-blocking) |

### Agent (100%)

| Component | Status | Notes |
|-----------|--------|-------|
| Documentation Generation | Done | Multi-page with wikilinks |
| API Integration | Done | POST to backend with retry logic |
| Version Priority | Done | Intelligent regeneration decisions |
| Security | Done | URL validation, prompt injection defense, hardened container |

## Technology Stack

- **Backend**: Python 3.11, FastAPI, SQLAlchemy, SQLite
- **Frontend**: Next.js 14, React, TypeScript, Tailwind CSS
- **Agent**: OpenHands SDK, OpenRouter API
- **Infrastructure**: Docker, Docker Compose, Caddy (production)

## Documentation

| Document | Purpose |
|----------|---------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design, data model, services, security, coding standards |
| [CHANGELOG.md](CHANGELOG.md) | Version history |
| [USAGE_GUIDE.md](USAGE_GUIDE.md) | How to use the product |
| [docs/DEPLOYING_AT_YOUR_ORGANIZATION.md](docs/DEPLOYING_AT_YOUR_ORGANIZATION.md) | Setup, deployment, configuration, troubleshooting |
| [docs/FURTHER_DEVELOPMENT.md](docs/FURTHER_DEVELOPMENT.md) | Roadmap and future tasks |
| [frontend/STYLE_GUIDE.md](frontend/STYLE_GUIDE.md) | Frontend design system |

## Costs

- **Infrastructure**: Free (self-hosted with Docker)
- **LLM API**: ~$0.50-2.00 per repository (OpenRouter)

## License

[Add license information]
