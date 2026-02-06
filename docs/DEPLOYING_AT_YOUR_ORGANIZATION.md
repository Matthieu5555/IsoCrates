# Deploying IsoCrates at Your Organization

This guide walks teams through adopting IsoCrates from the open-source repository. It separates what the project provides from what you must configure for your environment, so that nothing falls through the cracks between the two.

---

## Prerequisites

You will need Docker 20.10+ with Docker Compose 2.0+, Git, an API key from an LLM provider (OpenRouter, Ollama, or any OpenAI-compatible endpoint), a domain name with DNS control for production, and a reverse proxy capable of TLS termination (Caddy, nginx, or Traefik). The application itself does not handle TLS, so the reverse proxy is essential for any deployment beyond localhost.

---

## 1. Clone and Configure Secrets

```bash
git clone https://github.com/<your-fork>/IsoCrates.git
cd IsoCrates
cp .env.example .env
```

Edit `.env` and set every value. Do not leave defaults in production — the application validates configuration at startup and will refuse to start in production mode with insecure defaults.

### Required secrets

| Variable | What to put | Where it's used |
|----------|-------------|-----------------|
| `LLM_API_KEY` | Your LLM provider API key | Agent uses this to generate documentation |
| `JWT_SECRET_KEY` | A random 64+ character string (`openssl rand -hex 32`) | Signs all authentication tokens |
| `GITHUB_WEBHOOK_SECRET` | A random string you also set in GitHub webhook config | Verifies incoming webhook payloads |

### Production: use Docker secrets instead of env vars

For production deployments, Docker secrets are strongly preferred over plain environment variables because they are mounted as files rather than stored in the process environment, reducing the risk of accidental exposure through logs or process inspection.

```bash
mkdir -p secrets
openssl rand -hex 32 > secrets/jwt_secret.txt
echo "sk-or-v1-your-key" > secrets/openrouter_api_key.txt
openssl rand -hex 20 > secrets/github_webhook_secret.txt
chmod 600 secrets/*.txt
```

Uncomment the `secrets` section in `docker-compose.yml`. The agent already supports `OPENROUTER_API_KEY_FILE` for file-based secret loading, so no code changes are needed.

### Never commit `.env` or `secrets/`

Both are already listed in `.gitignore`, but you should verify before pushing:

```bash
git status  # .env and secrets/ should NOT appear
```

---

## 2. Configure CORS

In `.env`, set `CORS_ALLOWED_ORIGINS` to the exact origin(s) your users will access:

```bash
CORS_ALLOWED_ORIGINS=https://docs.yourcompany.com
```

Wildcards (`*`) are rejected at startup — the application validates CORS configuration eagerly rather than silently accepting an insecure default. Multiple origins are comma-separated. Include only origins that actually need browser-based API access, since every additional origin widens the attack surface.

---

## 3. Enable Authentication

Authentication is off by default for development convenience. Before exposing the service to your network, enable it — otherwise every endpoint is accessible without credentials.

```bash
AUTH_ENABLED=true
JWT_SECRET_KEY=<your-generated-secret>
```

### Auth model

IsoCrates uses JWT bearer tokens with HMAC-SHA256 signing, backed by a built-in permission system that enforces access control on every request.

Three roles govern what users can do: admins manage users and grants, editors can create and modify documents within their granted paths, and viewers have read-only access. Access is scoped through folder grants — path-prefix based rules where a grant on `backend-product-a` gives access to all documents under that path. When multiple grants overlap, the longest prefix match wins, which means you can grant broad read access and narrow write access to the same user.

Permission enforcement runs on every request, including read-only ones. When `AUTH_ENABLED=true`, all endpoints filter results by the caller's grants before returning data. Unauthenticated requests receive empty results or 404 responses rather than seeing everything — there is no "public read" mode when auth is enabled. This design means that forgetting to attach a token produces a silent empty response rather than a data leak.

Personal tree isolation adds another layer: each user's personal folder structure is scoped to their token, so users cannot access one another's personal workspaces regardless of their role.

The first user to register is automatically promoted to admin with root access. Subsequent registrations require admin authentication. Tokens expire after 24 hours, and rate limiting (60 requests per minute per client, configurable via `RATE_LIMIT_PER_MINUTE`) protects against abuse.

### Setting up users

Start the application with `AUTH_ENABLED=true`, then register the first user — they become admin automatically:

```bash
curl -X POST https://docs.yourcompany.com/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@company.com", "password": "your-secure-password", "display_name": "Admin"}'
```

Log in to obtain a JWT:

```bash
curl -X POST https://docs.yourcompany.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@company.com", "password": "your-secure-password"}'
```

Then use the admin token to register other users and assign folder grants:

```bash
# Register a user
curl -X POST https://docs.yourcompany.com/api/auth/register \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email": "dev@company.com", "password": "their-password", "display_name": "Developer"}'

# Grant editor access to a subtree
curl -X POST https://docs.yourcompany.com/api/auth/users/$USER_ID/grants \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"path_prefix": "backend-product-a", "role": "editor"}'
```

### Customizing the permission model

All permission checks flow through a single pure function: `backend/app/services/permission_service.py:check_permission()`. To implement a different model — team-based access, time-limited grants, deny lists — replace this one function. Everything else in the system delegates to it, so a single change propagates everywhere.

### Generating a service token for the agent

The doc-generation agent needs a token to write documents to the backend. Generate one and pass it as `DOC_API_TOKEN`:

```bash
cd backend
python -c "
from app.core.token_factory import create_token
import os
token = create_token(
    subject='doc-agent',
    role='service',
    secret_key=os.environ['JWT_SECRET_KEY']
)
print(token)
"
```

Set the output as `DOC_API_TOKEN` in the agent's environment.

---

## 4. Set Up the Reverse Proxy

IsoCrates does not handle TLS itself, so you need a reverse proxy in front of the application to terminate HTTPS connections.

### Example: Caddy

Caddy is the simplest option because it automatically provisions and renews TLS certificates via Let's Encrypt:

```
docs.yourcompany.com {
    handle /api/* {
        reverse_proxy localhost:8000
    }
    handle /health {
        reverse_proxy localhost:8000
    }
    handle /* {
        reverse_proxy localhost:3001
    }
}
```

### Example: nginx

If you already run nginx, add a server block:

```nginx
server {
    listen 443 ssl;
    server_name docs.yourcompany.com;

    ssl_certificate     /etc/ssl/certs/your-cert.pem;
    ssl_certificate_key /etc/ssl/private/your-key.pem;

    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass http://localhost:3001;
        proxy_set_header Host $host;
    }
}
```

### Important: set `X-Forwarded-For`

Rate limiting uses the `X-Forwarded-For` header to identify clients behind a proxy. Without it, all users share one rate limit bucket and hit the limit much sooner than expected.

---

## 5. Configure GitHub Webhooks

To trigger automatic documentation regeneration whenever code is pushed:

1. Go to your GitHub repository > Settings > Webhooks > Add webhook
2. Set **Payload URL** to `https://docs.yourcompany.com/api/webhooks/github`
3. Set **Content type** to `application/json`
4. Set **Secret** to the same value as `GITHUB_WEBHOOK_SECRET` in your `.env`
5. Select **Just the push event**

Repeat for each repository you want IsoCrates to track. The version priority engine evaluates each incoming webhook and skips regeneration when the repository hasn't changed meaningfully, so adding many repositories does not proportionally increase LLM costs.

### Manual generation (without webhooks)

```bash
docker exec doc-agent python openhands_doc.py --repo https://github.com/your-org/your-repo
```

---

## 6. Frontend Configuration

Create `frontend/.env.local`:

```bash
NEXT_PUBLIC_API_URL=https://docs.yourcompany.com
NEXT_PUBLIC_API_URL_INTERNAL=http://localhost:8000  # For SSR (stays internal)
NEXT_PUBLIC_API_TOKEN=<optional-bearer-token>
```

If you need a custom base path (for example, `https://yourcompany.com/docs` instead of the root), edit `frontend/next.config.js` and set `basePath: '/docs'`.

---

## 7. Start Services

### Docker (recommended for production)

```bash
docker compose up -d --build
```

This starts the backend API, frontend, doc agent, and doc worker. The backend applies any pending database migrations automatically on startup, so you do not need to run migrations manually.

### Verify

```bash
curl https://docs.yourcompany.com/health
# Should return: {"status":"healthy","database":"connected",...}
```

---

## 8. Database Considerations

### SQLite (default)

SQLite is fine for small teams with fewer than 10 concurrent users. Its single-writer limitation means concurrent writes queue up, but for most documentation workloads this is rarely noticeable. The database file lives at `backend/isocrates.db`.

For backups, a simple file copy works when the backend is idle. If the backend is running, use the SQLite backup API to avoid copying a file mid-transaction:

```bash
cp backend/isocrates.db backups/isocrates_$(date +%Y%m%d).db
sqlite3 backups/isocrates_$(date +%Y%m%d).db "PRAGMA integrity_check;"
```

### PostgreSQL (recommended for teams)

For teams with concurrent users or production deployments, switch to PostgreSQL by changing `DATABASE_URL` in `.env`:

```bash
DATABASE_URL=postgresql://user:password@localhost:5432/isocrates
```

SQLAlchemy handles the rest — no code changes are needed. You gain concurrent writes, proper connection pooling, production-grade backup tooling (`pg_dump`), and support for pgvector if you enable semantic search with embeddings.

---

## 9. Security Checklist

Before exposing IsoCrates to your network, walk through this checklist. Each item addresses a specific attack vector, and skipping any one of them can undermine the others.

- [ ] `AUTH_ENABLED=true` — without this, every endpoint is accessible to anyone
- [ ] `JWT_SECRET_KEY` is a unique, random value (not the default) — a predictable secret lets anyone forge tokens
- [ ] `GITHUB_WEBHOOK_SECRET` is set — this is **required** when `AUTH_ENABLED=true`; the server rejects unsigned webhooks to prevent unauthorized regeneration triggers
- [ ] `CORS_ALLOWED_ORIGINS` lists only your actual domain(s) — overly broad CORS lets malicious pages make authenticated API requests from a user's browser
- [ ] `.env` is not committed to version control
- [ ] `secrets/` directory contains no committed files (check with `git ls-files secrets/`)
- [ ] Reverse proxy enforces HTTPS and forwards `X-Forwarded-For`
- [ ] Agent container has no direct network exposure (only talks to backend internally)
- [ ] Database file (if SQLite) is not in a web-accessible directory
- [ ] LLM API key is loaded via Docker secret, not plain env var

### What the project already handles

The following security concerns are built into IsoCrates and require no additional configuration on your part. CORS whitelist validation rejects wildcards at startup. Rate limiting uses a token bucket algorithm (60 requests per minute per client, configurable) and returns 429 with a `Retry-After` header. Input validation runs through Pydantic schemas on all request bodies. GitHub webhook signatures are verified with HMAC-SHA256 and rejected when invalid (mandatory when auth is enabled).

Permission filtering runs on all endpoints — both read and write — including versions, dependencies, jobs, and folder metadata. This means there is no endpoint that leaks data to unauthorized callers. Personal tree user isolation ensures each user can only access their own folders and refs, regardless of their role. Docker container hardening drops all capabilities, enables no-new-privileges, and sets memory and PID limits on the agent container. Path traversal prevention in the agent's repository validator blocks attempts to escape the sandboxed workspace. SQL injection prevention comes from the SQLAlchemy ORM, which parameterizes all queries. Structured JSON logging with request-ID tracing provides an audit trail for every request. Soft delete with 30-day auto-purge gives users a recovery window before data is permanently removed.

### What the project does NOT handle (your responsibility)

The following are outside the scope of the application and must be handled by your infrastructure team: TLS termination and certificate management, network segmentation and firewall rules, user provisioning and identity management (IsoCrates has its own user table but no SSO or LDAP integration), audit log monitoring and alerting (logging is built-in but monitoring dashboards are not), database encryption at rest, backup scheduling and disaster recovery, and production monitoring and alerting.

---

## 10. Updating

```bash
git pull origin main
docker compose down
docker compose up -d --build
```

Migrations are applied automatically on startup by the built-in migrator (`backend/app/core/migrator.py`). Check the backend logs to confirm new migrations were applied successfully — the migrator logs each migration it runs and skips those already applied.

---

## 11. Customizing Documentation Style

The documentation the agent produces — its writing style, page structure, diagram usage, wikilink density — is controlled entirely by prompt constants in `agent/prompts.py` and prompt templates in `agent/planner.py`. These are designed to be edited without touching any pipeline logic. For a complete walkthrough of what each prompt controls and how to modify it safely, see [`docs/PROMPT_ENGINEERING.md`](../docs/PROMPT_ENGINEERING.md).

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| 401 on all requests | Is `AUTH_ENABLED=true`? Is your token valid and not expired? |
| CORS errors in browser | Is your domain in `CORS_ALLOWED_ORIGINS`? |
| Webhook not triggering | Is `GITHUB_WEBHOOK_SECRET` the same in `.env` and GitHub? Check backend logs. |
| Agent can't reach backend | Is `DOC_API_URL` set to the correct internal URL? (e.g., `http://backend-api:8000` in Docker) |
| Rate limited (429) | Default is 60/min. Adjust `RATE_LIMIT_PER_MINUTE` or check for misconfigured proxy (all traffic from one IP). |
| Database locked errors | SQLite single-writer limit. Consider PostgreSQL for concurrent users. |

For detailed operational procedures specific to your environment, create your own `PERSONAL_OPERATIONS.md` based on this guide.
