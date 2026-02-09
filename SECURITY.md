# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in IsoCrates, please report it responsibly.

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, please email the maintainers or use GitHub's private vulnerability reporting feature:

1. Go to the repository's **Security** tab
2. Click **Report a vulnerability**
3. Provide a description of the issue, steps to reproduce, and any relevant context

## What to include

- Description of the vulnerability
- Steps to reproduce
- Affected versions or components
- Potential impact
- Suggested fix (if any)

## Response timeline

- **Acknowledgement:** Within 48 hours of receiving your report
- **Assessment:** Within 1 week we will confirm the issue and begin working on a fix
- **Fix release:** Security patches are prioritised and released as soon as practical

## Scope

The following are in scope:

- Authentication and authorization bypass
- SQL injection or other injection attacks
- Cross-site scripting (XSS) in the frontend
- Secrets exposure (API keys, credentials)
- Container escape or privilege escalation in the agent sandbox
- Prompt injection that causes the agent to exfiltrate data or perform unintended actions

The following are out of scope:

- Denial of service (rate limiting is configurable)
- Issues in dependencies (report these upstream)
- Social engineering

## Security architecture

IsoCrates has several built-in security mechanisms documented in `ARCHITECTURE.md`:

- JWT authentication with HMAC-SHA256
- Path-based folder grants for authorization
- CORS origin validation (no wildcards)
- Rate limiting per client
- Input validation via Pydantic
- Docker container hardening (cap_drop ALL, no-new-privileges)
- Prompt injection detection in the agent pipeline
- Repository URL whitelisting
