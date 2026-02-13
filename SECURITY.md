# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in IsoCrates, please report it responsibly. Do not open a public GitHub issue for security vulnerabilities. Instead, email the maintainers or use GitHub's private vulnerability reporting feature. Navigate to the repository's **Security** tab, click **Report a vulnerability**, and provide a description of the issue, steps to reproduce, and any relevant context.

## What to include

Your report should contain a description of the vulnerability, steps to reproduce it, which versions or components are affected, the potential impact, and a suggested fix if you have one.

## Response timeline

| Stage | Timeframe |
|-------|-----------|
| Acknowledgement | Within 48 hours of receiving your report |
| Assessment | Within 1 week (we confirm the issue and begin working on a fix) |
| Fix release | Security patches are prioritised and released as soon as practical |

## Scope

The following categories are in scope: authentication and authorization bypass, SQL injection or other injection attacks, cross-site scripting (XSS) in the frontend, secrets exposure (API keys, credentials), container escape or privilege escalation in the agent sandbox, and prompt injection that causes the agent to exfiltrate data or perform unintended actions.

The following are out of scope: denial of service (rate limiting is configurable), issues in dependencies (report those upstream), and social engineering.

## Security architecture

IsoCrates has several built-in security mechanisms documented in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Think of it as layers of locked doors, where each layer stops a different kind of intruder. JWT authentication uses HMAC-SHA256 to verify identity. Path-based folder grants control who can access which folders. CORS origin validation rejects unknown origins (no wildcards). Rate limiting throttles each client independently. Pydantic validates all input at the boundary. Docker container hardening drops all capabilities and sets no-new-privileges. The agent pipeline includes prompt injection detection, and repository URLs are checked against a whitelist.
