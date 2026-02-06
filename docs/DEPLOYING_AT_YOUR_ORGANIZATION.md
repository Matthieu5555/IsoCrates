# Deploying IsoCrates at Your Organization

A step-by-step guide for teams adopting IsoCrates from the open-source repository. This document separates what the project provides from what you must configure for your environment.

---

## Prerequisites

- **Docker** 20.10+ and **Docker Compose** 2.0+
- **Git**
- An **OpenRouter API key** from https://openrouter.ai/keys (or compatible LLM provider)
- A domain name with DNS control (for production)
- A reverse proxy capable of TLS termination (Caddy, nginx, Traefik)

---

## 1. Clone and Configure Secrets

```bash
git clone https://github.com/<your-fork>/IsoCrates.git
cd IsoCrates
cp .env.example .env
```

Edit `.env` and set **every** value. Do not leave defaults in production.

### Required secrets

| Variable | What to put | Where it's used |
|----------|-------------|-----------------|
| `OPENROUTER_API_KEY` | Your LLM API key | Agent uses this to generate documentation |
| `JWT_SECRET_KEY` | A random 64+ character string (`openssl rand -hex 32`) | Signs all authentication tokens |
| `GITHUB_WEBHOOK_SECRET` | A random string you also set in GitHub webhook config | Verifies incoming webhook payloads |

### Production: use Docker secrets instead of env vars

```bash
mkdir -p secrets
openssl rand -hex 32 > secrets/jwt_secret.txt
echo "sk-or-v1-your-key" > secrets/openrouter_api_key.txt
openssl rand -hex 20 > secrets/github_webhook_secret.txt
chmod 600 secrets/*.txt
```

Uncomment the `secrets` section in `docker-compose.yml`. The agent already supports `OPENROUTER_API_KEY_FILE` for file-based secret loading.

### Never commit `.env` or `secrets/`

Both are in `.gitignore`. Verify before pushing:

```bash
git status  # .env and secrets/ should NOT appear
```

---

## 2. Configure CORS

In `.env`, set `CORS_ALLOWED_ORIGINS` to the exact origin(s) your users will access:

```bash
CORS_ALLOWED_ORIGINS=https://docs.yourcompany.com
```

Wildcards (`*`) are rejected at startup. Multiple origins are comma-separated. Include only origins that need browser-based API access.

---

## 3. Enable Authentication

Authentication is **off by default** for development convenience. Enable it before exposing the service:

```bash
AUTH_ENABLED=true
JWT_SECRET_KEY=<your-generated-secret>
```

### Auth model

IsoCrates uses JWT bearer tokens with HMAC-SHA256 signing and a built-in permission system:

- **Three roles**: admin, editor, viewer
- **Folder grants**: Path-prefix based access control — a grant on `backend-product-a` gives access to all documents under that path
- **First user is admin**: The first `POST /api/auth/register` call creates an admin with root access. Subsequent registrations require admin auth.
- **Token lifetime**: 24 hours
- **Rate limiting**: 60 requests/minute per client (configurable via `RATE_LIMIT_PER_MINUTE`)

### Setting up users

1. Start the application with `AUTH_ENABLED=true`
2. Register the first user (becomes admin automatically):
   ```bash
   curl -X POST https://docs.yourcompany.com/api/auth/register \
     -H "Content-Type: application/json" \
     -d '{"email": "admin@company.com", "password": "your-secure-password", "display_name": "Admin"}'
   ```
3. Log in to get a JWT:
   ```bash
   curl -X POST https://docs.yourcompany.com/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email": "admin@company.com", "password": "your-secure-password"}'
   ```
4. Use the admin token to register other users and assign folder grants:
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

All permission checks go through one function: `backend/app/services/permission_service.py:check_permission()`. To implement a different model (team-based, time-limited grants, deny lists), replace this function. Everything else in the system calls it.

### Generating a service token for the agent

The doc-generation agent needs a token to write documents to the backend. Generate one and pass it as `DOC_API_TOKEN`:

```bash
# Generate a token using the backend's token factory
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

IsoCrates does not handle TLS itself. You need a reverse proxy in front of it.

### Example: Caddy

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

Caddy automatically provisions and renews TLS certificates via Let's Encrypt.

### Example: nginx

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

Rate limiting uses the `X-Forwarded-For` header to identify clients behind a proxy. Without it, all users share one rate limit bucket.

---

## 5. Configure GitHub Webhooks

To trigger automatic documentation regeneration when code is pushed:

1. Go to your GitHub repository > Settings > Webhooks > Add webhook
2. Set **Payload URL** to `https://docs.yourcompany.com/api/webhooks/github`
3. Set **Content type** to `application/json`
4. Set **Secret** to the same value as `GITHUB_WEBHOOK_SECRET` in your `.env`
5. Select **Just the push event**

Repeat for each repository you want IsoCrates to track.

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

If you need a custom base path (e.g., `https://yourcompany.com/docs` instead of the root):

Edit `frontend/next.config.js` and set `basePath: '/docs'`.

---

## 7. Start Services

### Docker (recommended for production)

```bash
docker compose up -d --build
```

This starts the backend API, frontend, doc agent, and doc worker.

### Verify

```bash
curl https://docs.yourcompany.com/health
# Should return: {"status":"healthy","database":"connected",...}
```

---

## 8. Database Considerations

### SQLite (default)

Fine for small teams (< 10 concurrent users). Single-writer limitation means concurrent writes queue up. The database file lives at `backend/isocrates.db`.

**Backups:**

```bash
# Simple file copy (while backend is idle or using SQLite backup API)
cp backend/isocrates.db backups/isocrates_$(date +%Y%m%d).db
sqlite3 backups/isocrates_$(date +%Y%m%d).db "PRAGMA integrity_check;"
```

### PostgreSQL (recommended for teams)

Change `DATABASE_URL` in `.env`:

```bash
DATABASE_URL=postgresql://user:password@localhost:5432/isocrates
```

SQLAlchemy handles the rest. No code changes needed. You gain concurrent writes, proper connection pooling, and production-grade backup tooling (`pg_dump`).

---

## 9. Security Checklist

Before exposing IsoCrates to your network:

- [ ] `AUTH_ENABLED=true`
- [ ] `JWT_SECRET_KEY` is a unique, random value (not the default)
- [ ] `GITHUB_WEBHOOK_SECRET` is set (empty = signature verification skipped with a warning)
- [ ] `CORS_ALLOWED_ORIGINS` lists only your actual domain(s)
- [ ] `.env` is not committed to version control
- [ ] `secrets/` directory contains no committed files (check with `git ls-files secrets/`)
- [ ] Reverse proxy enforces HTTPS and forwards `X-Forwarded-For`
- [ ] Agent container has no direct network exposure (only talks to backend internally)
- [ ] Database file (if SQLite) is not in a web-accessible directory
- [ ] OpenRouter API key is loaded via Docker secret, not plain env var

### What the project already handles

- CORS whitelist validation (rejects wildcards at startup)
- Rate limiting (token bucket, 60 req/min per client, configurable)
- Input validation (Pydantic schemas on all request bodies)
- GitHub webhook HMAC-SHA256 signature verification
- Docker container hardening (cap_drop ALL, no-new-privileges, memory/PID limits)
- Path traversal prevention in the agent's repository validator
- SQL injection prevention via SQLAlchemy ORM
- Structured JSON logging with request-ID tracing
- Soft delete with 30-day auto-purge

### What the project does NOT handle (your responsibility)

- TLS termination and certificate management
- Network segmentation and firewall rules
- User provisioning and identity management
- Audit log monitoring and alerting (logging is built-in, monitoring is not)
- Database encryption at rest
- Backup scheduling and disaster recovery
- Monitoring and alerting

---

## 10. Updating

```bash
git pull origin main
docker compose down
docker compose up -d --build
```

Migrations are applied automatically on startup by the built-in migrator (`backend/app/core/migrator.py`). Check the backend logs to confirm new migrations were applied successfully.

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
