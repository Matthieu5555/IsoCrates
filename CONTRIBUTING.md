# Contributing to IsoCrates

Thank you for your interest in contributing to IsoCrates! This guide will help you get started.

## Development setup

### Prerequisites

- Python 3.13+ (backend)
- Node.js 18+ (frontend)
- PostgreSQL 16+ or SQLite (database)
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Docker (optional, for the agent container)

### Getting started

```bash
# Clone the repository
git clone https://github.com/nicobailon/IsoCrates.git
cd IsoCrates

# Backend
cp backend/.env.example backend/.env
cd backend
uv sync
uv run uvicorn app.main:app --reload

# Frontend (in a separate terminal)
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

The backend runs at `http://localhost:8000` and the frontend at `http://localhost:3000`.

## How to contribute

### Reporting bugs

Open a GitHub issue with:
- Steps to reproduce
- Expected vs actual behaviour
- Environment details (OS, Python/Node version, browser)

### Suggesting features

Open a GitHub issue describing:
- The problem you're trying to solve
- Your proposed solution
- Any alternatives you considered

### Submitting code

1. Fork the repository
2. Create a feature branch from `main`
3. Make your changes
4. Run tests (see below)
5. Open a pull request

### Pull request guidelines

- Keep PRs focused on a single change
- Write descriptive commit messages
- Add tests for new functionality
- Update documentation if behaviour changes
- Ensure all tests pass before requesting review

## Running tests

```bash
# Backend tests
cd backend
uv run pytest -v

# Frontend tests
cd frontend
npm run test
```

## Code style

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for detailed coding conventions. Key points:

- **Backend:** Follow the deep module pattern — business logic lives in services, endpoints are thin (5-15 lines)
- **Frontend:** Use Tailwind CSS via variant objects from `lib/styles/`, no inline styles
- **General:** No `print()` in backend code (use `logging`), no `alert()` in frontend code (use toast notifications)

## Project structure

```
backend/     # FastAPI REST API + SQLAlchemy
frontend/    # Next.js 14 React application
agent/       # OpenHands-based documentation generator
mcp-server/  # MCP server for Claude Code integration
docs/        # Deployment and development guides
```

## Questions?

If you're unsure about anything, open an issue and we'll be happy to help.
