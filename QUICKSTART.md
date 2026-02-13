# Quickstart: Zero to Production

This is the linear path from a fresh server to a running IsoCrates instance. Every step has one command and one outcome. For the full walkthrough — auth model, security checklist, customization — see the [Deployment Guide](docs/DEPLOYING_AT_YOUR_ORGANIZATION.md).

---

**Prerequisites:** A Linux server with Docker and Docker Compose installed, a domain name you control, and an API key from an LLM provider ([OpenRouter](https://openrouter.ai/) is the easiest start — one key, many models. See [LLM Providers](docs/LLM_PROVIDERS.md) for alternatives).

### 1. Clone

```bash
git clone https://github.com/Matthieu5555/IsoCrates.git && cd IsoCrates
```

### 2. Point DNS

Create an A record for your domain (e.g. `docs.yourcompany.com`) pointing to your server's IP address. Caddy needs this to provision a TLS certificate automatically, so the record must be live before you deploy.

### 3. Deploy

```bash
./scripts/deploy.sh
```

The script asks for your domain, generates all secrets (JWT signing key, database password, webhook secret), writes a Caddyfile for automatic HTTPS via Let's Encrypt, and starts the core services (PostgreSQL, backend API, frontend, Caddy). Re-running is safe — existing values are preserved.

### 4. Configure LLM

The deploy script sets up the platform but not the AI documentation agent. Edit the generated `scripts/.env.production` and add your LLM provider settings:

```bash
# Append to scripts/.env.production:
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=sk-or-v1-your-key-here
OPENROUTER_API_KEY=sk-or-v1-your-key-here
SCOUT_MODEL=openrouter/mistralai/devstral-2512
PLANNER_MODEL=openrouter/mistralai/mistral-medium-latest
WRITER_MODEL=openrouter/mistralai/devstral-2512
```

Or copy from [`.env.production.example`](.env.production.example) for a complete template with all optional settings.

### 5. Restart with the agent

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --env-file scripts/.env.production \
  --profile agent up -d --build
```

The `--profile agent` flag adds the documentation generation pipeline (doc-agent and doc-worker). Without it, IsoCrates works as a documentation viewer but does not generate anything.

### 6. Register your admin

The first user to register is automatically promoted to admin with full access. Subsequent registrations require an admin token.

```bash
curl -X POST https://docs.yourcompany.com/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"display_name":"Admin", "email":"admin@yourcompany.com", "password":"a-strong-password"}'
```

### 7. Add a GitHub webhook

In your GitHub repository: **Settings > Webhooks > Add webhook**

| Field | Value |
|-------|-------|
| Payload URL | `https://docs.yourcompany.com/api/webhooks/github` |
| Content type | `application/json` |
| Secret | The `GITHUB_WEBHOOK_SECRET` value from `scripts/.env.production` |
| Events | Just the push event |

Repeat for each repository you want IsoCrates to document. The version priority engine evaluates each push and skips regeneration when the code has not changed meaningfully, so adding many repositories does not proportionally increase costs.

### 8. Verify

```bash
./scripts/verify.sh
```

Or manually:

```bash
curl https://docs.yourcompany.com/health
# {"status":"healthy","database":"connected","uptime_seconds":...}
```

---

**Next:** Push code to a webhook-connected repository and watch IsoCrates generate documentation automatically. Read the [Usage Guide](docs/USAGE_GUIDE.md) for search, personal trees, and API examples.
