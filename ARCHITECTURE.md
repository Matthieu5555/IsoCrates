# IsoCrates Architecture

## System Overview

IsoCrates is an AI-powered technical documentation platform with three layers:

1. **Frontend** (Next.js 14) -- document viewer, tree navigation, CMD+K search, version history
2. **Backend** (FastAPI + SQLite) -- REST API with deep module services, structured error handling, configuration validation
3. **Agent** (OpenHands SDK in Docker) -- autonomous documentation generator with security hardening

```
Frontend (Next.js) :3001
    | REST API (validated CORS)
Backend (FastAPI) :8000
    | Service Layer (Deep Modules)
SQLite Database
    - documents, versions, dependencies
    - folder_metadata, users
    - personal_folders, personal_document_refs

Doc Agent (Sandboxed Container)
    - Security validators
    - OpenHands SDK
    - Hardened Docker
```

---

## Data Model

### documents
```sql
id              TEXT PRIMARY KEY          -- doc-{hash}-{type} or doc-standalone-{hash}
repo_url        TEXT                      -- Nullable (for standalone docs)
repo_name       VARCHAR(255)              -- Nullable
path            VARCHAR(500) NOT NULL     -- Full path (first segment = crate)
doc_type        TEXT NOT NULL             -- client, softdev, etc. (legacy, retained)
title           TEXT NOT NULL
content         TEXT
created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
generation_count INTEGER DEFAULT 0
```

### versions
```sql
id              INTEGER PRIMARY KEY
doc_id          TEXT NOT NULL             -- FK to documents.id (CASCADE)
content         TEXT
author_type     TEXT NOT NULL             -- "ai" or "human"
author_metadata JSON                      -- Contains repo_commit_sha, etc.
created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
```

### dependencies
```sql
id              INTEGER PRIMARY KEY
source_doc_id   TEXT NOT NULL             -- Document containing the [[wikilink]]
target_doc_id   TEXT NOT NULL             -- Document being linked to
link_text       TEXT                      -- The wikilink text
created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
UNIQUE(source_doc_id, target_doc_id)
```

### folder_metadata
```sql
id              VARCHAR(50) PRIMARY KEY
path            VARCHAR(500) NOT NULL UNIQUE  -- First segment = crate
description     TEXT
icon            VARCHAR(50)
sort_order      INTEGER DEFAULT 0
created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
```

### users
```sql
user_id         TEXT PRIMARY KEY         -- UUID prefix (8 chars)
display_name    TEXT NOT NULL
email           TEXT UNIQUE              -- Login credential
password_hash   TEXT                     -- bcrypt via passlib
role            TEXT NOT NULL DEFAULT 'viewer'  -- admin, editor, viewer
is_active       BOOLEAN NOT NULL DEFAULT true
created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
```

### folder_grants
```sql
user_id         TEXT NOT NULL            -- FK to users.user_id (CASCADE)
path_prefix     TEXT NOT NULL DEFAULT '' -- '' = root (all docs). Longest match wins.
role            TEXT NOT NULL DEFAULT 'viewer'  -- Overrides user.role for this subtree
granted_by      TEXT                     -- FK to users.user_id (who granted this)
created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
PRIMARY KEY (user_id, path_prefix)
```

### audit_log
```sql
id              INTEGER PRIMARY KEY AUTOINCREMENT
user_id         TEXT                     -- FK to users.user_id
action          TEXT NOT NULL            -- create, update, delete, login, role_change, grant_create, grant_revoke
resource_type   TEXT NOT NULL            -- document, user, folder, grant
resource_id     TEXT
details         TEXT                     -- JSON string with additional context
ip_address      TEXT
created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
```

### personal_folders
```sql
folder_id       TEXT PRIMARY KEY         -- pf-{hash}
user_id         TEXT NOT NULL            -- FK to users.user_id
name            TEXT NOT NULL
parent_id       TEXT                     -- FK to personal_folders.folder_id (CASCADE)
sort_order      INTEGER DEFAULT 0
created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
UNIQUE(user_id, parent_id, name)
```

### personal_document_refs
```sql
ref_id          TEXT PRIMARY KEY         -- pr-{hash}
user_id         TEXT NOT NULL            -- FK to users.user_id
folder_id       TEXT NOT NULL            -- FK to personal_folders.folder_id (CASCADE)
document_id     TEXT NOT NULL            -- FK to documents.id (CASCADE)
sort_order      INTEGER DEFAULT 0
created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
UNIQUE(user_id, folder_id, document_id)
```

### Relationships

- Documents have a `path` field where the first segment is the "crate" (top-level category).
- Document IDs are generated from `repo_url + path + title` (hierarchical) or `repo_url + doc_type` (legacy).
- Creating a nested folder (e.g. `a/b/c`) automatically creates metadata records for all ancestors (`a`, `a/b`).
- Personal tree uses references (not copies) -- deleting a document cascades to its personal refs.

---

## Service Layer

### DocumentService (Deep Module)

Orchestrates all document operations behind a simple interface. Endpoints are 5-15 lines; all complexity lives here.

**Before (shallow):**
```python
@router.put("/api/docs/{doc_id}")
def update_document(doc_id, data, db):
    doc = db.query(Document).filter_by(id=doc_id).first()
    if not doc: raise HTTPException(404)
    doc.content = data.content
    version = Version(...)
    db.add(version)
    dep_service.replace_document_dependencies(doc_id, data.content)
    db.commit()
    return doc
```

**After (deep):**
```python
@router.put("/api/docs/{doc_id}")
def update_document(doc_id, data, db):
    return document_service.update_document(db, doc_id, data)
```

Public methods:
- `create_or_update_document()` -- Upsert with version tracking and dependency extraction
- `update_document()` -- Update with automatic versioning
- `get_document()` / `list_documents()` / `delete_document()`
- `move_document()` -- Move to different folder path
- `update_keywords()` / `update_repo_url()` -- Metadata management
- `search_documents()` -- Full-text search
- `resolve_wikilink()` -- Cross-reference resolution (delegates to DependencyService)

### FolderService (Deep Module)

Single class handling all folder and tree operations. All path validation, ancestor creation, and tree construction are private internals.

Public methods: `create_folder`, `delete_folder`, `move_folder`, `get_tree`, `update_folder`, `get_folder`, `list_folders`, `cleanup_orphans`.

Key behaviors:
- Creating folder `a/b/c` auto-creates ancestors `a` and `a/b`.
- Deletion modes: `move_up` (re-parent contents) or `delete_all` (remove everything).
- Tree building: 2-level hierarchy with `is_crate=True` for top-level folders.

### DependencyService (Deep Module)

Manages document-to-document relationships:
- `create_dependency()` -- Validates both docs exist, prevents self-links, detects circular dependencies (DFS), idempotent creation.
- `replace_document_dependencies()` -- Extracts wikilinks from content, resolves targets, recreates all outgoing deps. Called by DocumentService on every save.
- `get_all_dependencies()` -- Full graph for visualization.

### PersonalTreeService

Per-user document organization with references (not copies). Manages personal folders and document refs for the `personal_*` tables.

### Repository Pattern

All data access goes through repository classes (`DocumentRepository`, `FolderRepository`, `VersionRepository`, `DependencyRepository`). Services never touch the ORM directly.

### Exception Hierarchy

```python
class DocumentNotFoundError(BaseException):
    error_code = "DOCUMENT_NOT_FOUND"

class CircularDependencyError(BaseException):
    error_code = "CIRCULAR_DEPENDENCY"

class InvalidInputError(BaseException):
    error_code = "INVALID_INPUT"

class AuthenticationError(BaseException):
    error_code = "UNAUTHORIZED"      # status 401

class ForbiddenError(BaseException):
    error_code = "FORBIDDEN"         # status 403
```

Error responses:
```json
{
  "error": "DOCUMENT_NOT_FOUND",
  "message": "Document not found: doc-abc123",
  "details": {"doc_id": "doc-abc123"}
}
```

Middleware catches all custom exceptions and converts them to structured JSON responses. Frontend displays errors as toast notifications (not `alert()`).

### Authentication & Permission System

**`backend/app/core/auth.py`** -- Three FastAPI dependencies:

```python
require_auth(credentials, db) -> AuthContext   # 401 if invalid; anonymous admin if AUTH_ENABLED=False
optional_auth(credentials, db) -> Optional[AuthContext]  # None if no token, never raises
require_admin(auth) -> AuthContext             # 403 if not admin role
```

`AuthContext` is a frozen dataclass containing `user_id`, `role`, and `grants` (list of FolderGrant objects loaded from DB). When `AUTH_ENABLED=false`, returns an anonymous admin context with a root grant.

**`backend/app/core/token_factory.py`** -- Pure functions for JWT:

```python
create_token(subject, role, secret, algorithm="HS256", expires_hours=24) -> str
decode_token(token, secret, algorithm="HS256") -> Optional[TokenPayload]  # None on any failure
```

Hand-rolled HMAC-SHA256 using stdlib only (no python-jose dependency). `decode_token` returns `None` on bad signature, expired, or malformed tokens -- never raises.

**`backend/app/services/permission_service.py`** -- Single pure function for all permission checks:

```python
check_permission(grants: list[FolderGrant], doc_path: str, action: str) -> bool
```

Finds the longest matching `path_prefix` from the user's grants and checks whether the grant's role permits the action. Role hierarchy: admin > editor > viewer. Actions: read, edit, delete, admin. No matching grant = no access (documents return 404, not 403, to prevent information leakage).

Adopters who want a different permission model replace this one function.

**`backend/app/services/auth_service.py`** -- User lifecycle:

- `register_user()` -- First user auto-promoted to admin with root grant. bcrypt password hashing.
- `authenticate()` -- Email/password validation, returns User or raises.
- `create_grant()` / `revoke_grant()` -- Admin-only folder grant management.

**`backend/app/api/auth_routes.py`** -- Auth endpoints:

- `POST /api/auth/register` -- Open for first user, admin-only after.
- `POST /api/auth/login` -- Returns JWT + user info + grants.
- `GET /api/auth/me` -- Current user context.
- `GET /api/auth/users` -- List users (admin-only).
- `PUT /api/auth/users/{id}/role` -- Change role (admin-only).
- `POST /api/auth/users/{id}/grants` -- Add folder grant (admin-only).
- `DELETE /api/auth/users/{id}/grants/{path}` -- Revoke grant (admin-only).

### Request Context Middleware

**`backend/app/middleware/request_context.py`** -- Single deep middleware handling four concerns:

1. **Request ID**: generates/reads `X-Request-ID`, stores in `contextvars.ContextVar`
2. **Timing**: records start time, sets `X-Response-Time` header
3. **Rate limiting**: calls `check_rate_limit()` pure function; returns 429 if denied
4. **Structured logging**: logs `{method, path, status_code, duration_ms, request_id}` per request

Rate limiter is a pure function testable without HTTP:
```python
def check_rate_limit(bucket: dict, key: str, max_per_minute: int, now: float) -> tuple[bool, float]
```

Token bucket algorithm with refill. Health/docs/OpenAPI paths exempt.

---

## Security

### Input Validation

```python
# agent/security/validators.py
class RepositoryValidator:
    ALLOWED_HOSTS = ['github.com', 'gitlab.com', 'bitbucket.org']

    def validate_repo_url(self, url: str):
        # HTTPS only, host whitelist, no path traversal
```

### Prompt Injection Defense

```python
# agent/security/prompt_safety.py
class PromptSanitizer:
    DANGEROUS_PATTERNS = [r'ignore previous', r'disregard .* instructions', ...]

    def sanitize_filename(self, name: str):
        # Remove injection patterns, prevent directory traversal
```

### Docker Hardening

```yaml
doc-agent:
  cap_drop: [ALL]
  security_opt: [no-new-privileges:true]
  deploy:
    resources:
      limits:
        memory: 4G
        pids: 200
```

### Secrets Management

- Development: `OPENROUTER_API_KEY` in `.env`
- Production: Docker secrets (`OPENROUTER_API_KEY_FILE=/run/secrets/openrouter_api_key`)
- Agent loads from file first, falls back to env var

### CORS Validation

Pydantic settings reject wildcard CORS at startup:

```python
class Settings(BaseSettings):
    cors_allowed_origins: List[str]

    @field_validator('cors_allowed_origins')
    def validate_origins(cls, v):
        if "*" in v:
            raise ValueError("Wildcard CORS not allowed")
        return v
```

---

## Agent System

### How openhands_doc.py Works

1. Validates repository URL via `RepositoryValidator`
2. Clones repository in sandboxed Docker container
3. Uses OpenHands SDK to autonomously explore the codebase
4. Generates comprehensive documentation (markdown with wikilinks)
5. Sanitizes output via `PromptSanitizer`
6. POSTs each document to `POST /api/docs` (upsert)

### Multi-Page Generation

The agent runs a planning phase, exploring the repo and outputting a document tree (list of pages with paths and titles). It then loops `generate_documentation()` over that tree. Each sub-page prompt receives the list of sibling pages for accurate wikilinks.

### Version Priority Engine

`agent/version_priority.py` checks commit SHA to decide whether regeneration is needed:
- Skips regeneration if repo unchanged and docs are fresh
- Respects human edits (won't overwrite `author_type: "human"` versions)
- ~70% skip rate on unchanged repos

### Webhook Regeneration Pipeline

`POST /api/webhooks/github` accepts GitHub push events, validates payload signature, and enqueues a regeneration job. The `generation_jobs` table tracks status (queued, running, completed, failed). Duplicate webhooks for the same commit SHA are deduplicated.

---

## Frontend Architecture

### Next.js App Structure

App Router with Tailwind CSS and TypeScript. Pages under `app/`, components under `components/`, API client under `lib/api/`.

Key directories:
- `components/tree/` -- DocumentTree, PersonalTree, TreeTabs, ContextMenu, dialogs
- `components/document/` -- DocumentView, MetadataDigest, MetadataDetails
- `components/search/` -- SearchCommand (CMD+K)
- `components/markdown/` -- MarkdownRenderer, MermaidBlock, WikiLink
- `components/graph/` -- DependencyGraph (ReactFlow + dagre)
- `lib/styles/` -- Centralized variant system (`button-variants.ts`)
- `lib/store/` -- Zustand stores (uiStore, treeStore, searchStore)
- `lib/notifications/` -- Toast notification system

### Key Components

**DocumentTree** -- react-arborist tree with context menus, drag-and-drop for folders and documents, root-level drop zone. Top-level folders ("crates") get a blue Layers icon, sub-folders get amber Folder icons, documents get gray FileText icons.

**PersonalTree** -- Per-user document organization with references (not copies). Tab switching via TreeTabs component.

**MarkdownRenderer** -- Renders markdown with GFM tables (`remark-gfm`), syntax highlighting, Mermaid diagrams (`MermaidBlock`), and wikilinks (`WikiLink` component).

**SearchCommand** -- CMD+K palette with Zustand state management, keyboard navigation, real-time results.

**DependencyGraph** -- Interactive graph visualization using ReactFlow + dagre auto-layout. Filters ghost nodes. Clicking a node navigates to the document.

### State Management

Zustand stores for UI state (sidebar, dialogs), tree state (selection, expansion), and search state. No Redux -- Zustand is simpler for this scale.

### Style System

All UI elements use shared variant objects from `lib/styles/button-variants.ts` (buttonVariants, badgeVariants, inputVariants, dialogVariants, tableVariants, scrollContainerVariants, etc.). New UI should use these variants rather than inline Tailwind classes. See `frontend/STYLE_GUIDE.md`.

### Error Boundaries

`error.tsx` and `not-found.tsx` under `app/docs/[docId]/` handle failed document loads and 404s gracefully.

### Portal Pattern

All dialogs and context menus use `createPortal(el, document.body)` to escape overflow clipping in scrollable containers.

---

## Coding Standards

### Backend (Python / FastAPI)

1. **Deep modules** -- Endpoints 5-15 lines max. Delegate to services. Services return data or raise custom exceptions.
2. **Custom exceptions** -- Use `DocumentNotFoundError`, `CircularDependencyError`, etc. Never `HTTPException` with bare status codes.
3. **Structured logging** -- `logger.info("msg", extra={...})`. Never `print()`.
4. **Type hints** -- All function signatures typed.
5. **Pydantic schemas** -- All request/response bodies validated.

### Frontend (TypeScript / React)

1. **Toast notifications** -- `toast.success()` / `toast.error()`. Never `alert()`.
2. **Error handling** -- Try/catch around API calls, structured error display.
3. **Type safety** -- Interfaces for all data shapes. Never `any`.
4. **Variant system** -- Use `buttonVariants`, `dialogVariants`, etc. from `lib/styles/button-variants.ts`.
5. **Portals** -- All overlays via `createPortal`.

### Agent (Python / OpenHands SDK)

1. **Security first** -- Always validate via `RepositoryValidator` and `PromptSanitizer`.
2. **Use API client** -- `DocumentAPIClient` for all backend communication. Never write to filesystem.
3. **Sanitize prompts** -- All user-derived strings go through `PromptSanitizer`.

### Common Tasks

**Add a new API endpoint:**
1. Create Pydantic schema in `backend/app/schemas/`
2. Add service method in `backend/app/services/`
3. Create thin endpoint in `backend/app/api/`
4. Register router in `backend/app/main.py`

**Add a frontend component:**
1. Update TypeScript types in `frontend/types/`
2. Add API client function in `frontend/lib/api/`
3. Create React component in `frontend/components/`
4. Use toast notifications for feedback, variant system for styling

**Add a database migration:**
1. Create SQL file in `backend/migrations/`
2. Create rollback SQL file
3. Test on database copy: `cp backend/isocrates.db backup.db`
4. Apply: `python backend/migrations/apply_migration.py <file>.sql`

### Codebase Navigation

| Task | Location |
|------|----------|
| Document CRUD | `backend/app/services/document_service.py` |
| API endpoints | `backend/app/api/documents.py` |
| Tree building (org) | `backend/app/services/folder_service.py` |
| Dependency validation | `backend/app/services/dependency_service.py` |
| Error handling | `backend/app/middleware/exception_handler.py` |
| Configuration | `backend/app/core/config.py` |
| Authentication | `backend/app/core/auth.py` |
| Permission checks | `backend/app/services/permission_service.py` |
| User lifecycle & grants | `backend/app/services/auth_service.py` |
| Auth endpoints | `backend/app/api/auth_routes.py` |
| Audit logging | `backend/app/services/audit_service.py` |
| JWT tokens | `backend/app/core/token_factory.py` |
| Rate limiting & request context | `backend/app/middleware/request_context.py` |
| Frontend document view | `frontend/components/document/DocumentView.tsx` |
| Tree navigation (org) | `frontend/components/tree/DocumentTree.tsx` |
| Tree navigation (personal) | `frontend/components/tree/PersonalTree.tsx` |
| Personal tree service | `backend/app/services/personal_tree_service.py` |
| Personal tree API | `backend/app/api/personal.py` |
| Tree tab switching | `frontend/lib/store/treeStore.ts` |
| Search UI | `frontend/components/search/SearchCommand.tsx` |
| Toast notifications | `frontend/lib/notifications/toast.ts` |
| Login page | `frontend/app/login/page.tsx` |
| Auth state (frontend) | `frontend/lib/store/authStore.ts` |
| Auth API (frontend) | `frontend/lib/api/auth.ts` |
| Agent security | `agent/security/validators.py` |
| Content preview | `backend/app/services/content_utils.py` |

---

## Testing Strategy

### What to Test

**Unit tests** (pytest):
- Service layer methods (DocumentService, DependencyService, FolderService)
- Validators (URL, path, prompt sanitization)
- Exception hierarchy
- ID generation stability (same inputs -> same ID)

**Integration tests** (pytest + httpx):
- All API endpoints (happy path + error cases)
- Database operations and migrations
- Dependency cycle detection with 3+ document cycles

**Frontend tests** (vitest + React Testing Library):
- MarkdownRenderer (table rendering, mermaid, wikilinks)
- DocumentView (edit/save flow)
- DocumentTree (navigation)

**Security tests:**
- Path traversal attempts rejected
- Non-whitelisted hosts rejected
- Prompt injection patterns caught
- CORS validation

### Hierarchical Folder Testing

Key scenarios to verify:
- Unlimited folder nesting (5+ levels)
- Color-coded icons (blue crate, amber folder, gray document)
- Cross-crate folder moves
- Folder deletion with `move_up` and `delete_all` modes
- Automatic ancestor creation on nested folder create
- Orphaned metadata cleanup

### Migration Testing

```bash
# Always test on a copy first
cp backend/isocrates.db backup.db
python backend/migrations/apply_migration.py <migration>.sql

# Verify
sqlite3 backend/isocrates.db ".schema documents"
sqlite3 backend/isocrates.db "PRAGMA integrity_check"
```

### Manual Smoke Tests

Before committing changes:
- Backend starts without errors
- Frontend compiles without errors
- `curl http://localhost:8000/health` returns 200
- Frontend loads at http://localhost:3001
- Feature works as expected
- Toast notifications appear (not `alert()`)
- Logs show structured messages (not `print()`)

---

## File Structure

```
IsoCrates/
├── backend/
│   └── app/
│       ├── api/            # Thin endpoints (5-15 lines) + auth_routes
│       ├── core/           # Configuration, logging, auth (AuthContext), token_factory
│       ├── middleware/      # Exception handler, request context (rate limit, request-id, timing)
│       ├── models/         # SQLAlchemy models (document, version, dependency, folder_metadata, user, personal)
│       ├── repositories/   # Data access layer
│       ├── schemas/        # Pydantic request/response schemas
│       ├── services/       # Business logic (deep modules) + permission_service, auth_service, audit_service
│       ├── database.py     # DB engine and session
│       ├── exceptions.py   # Custom exception hierarchy
│       └── main.py         # FastAPI app assembly
│   ├── tests/              # pytest suite (34 tests, in-memory SQLite)
│   └── migrations/         # SQL migrations with rollback support
│
├── frontend/
│   ├── app/                # Next.js pages (App Router)
│   │   ├── docs/[docId]/   # Document page with error.tsx + not-found.tsx
│   │   └── graph/          # Dependency graph page
│   ├── components/
│   │   ├── tree/           # DocumentTree, PersonalTree, TreeTabs, dialogs
│   │   ├── document/       # DocumentView, MetadataDigest, MetadataDetails
│   │   ├── editor/         # MarkdownEditor with Mermaid + Wikilink extensions
│   │   ├── markdown/       # MarkdownRenderer, MermaidBlock, WikiLink
│   │   ├── search/         # SearchCommand (CMD+K)
│   │   ├── graph/          # DependencyGraph, GraphNode, GraphControls
│   │   └── layout/         # AppShell, Sidebar, TopBar
│   ├── lib/
│   │   ├── api/            # API client (documents.ts, dependencies.ts, personal.ts, auth.ts)
│   │   ├── store/          # Zustand stores (uiStore, treeStore, searchStore, authStore)
│   │   ├── styles/         # Centralized style variants (button-variants.ts)
│   │   └── notifications/  # Toast notification system
│   └── types/              # TypeScript type definitions
│
├── agent/
│   ├── security/           # URL & path validation, prompt safety
│   ├── openhands_doc.py    # Main agent entry point
│   ├── api_client.py       # REST API client
│   └── version_priority.py # Version priority engine
│
└── secrets/                # Docker secrets (not in git)
```
