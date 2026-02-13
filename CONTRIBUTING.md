# Contributing to IsoCrates

Thank you for your interest in contributing. This guide covers the development setup, contribution workflow, and code style expectations.

## Development setup

You will need Python 3.13 or later for the backend, Node.js 18 or later for the frontend, PostgreSQL 16 or later (or SQLite) for the database, [uv](https://docs.astral.sh/uv/) as the Python package manager, and optionally Docker for the agent container.

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

Open a GitHub issue describing the steps to reproduce the problem, the expected versus actual behaviour, and your environment details (OS, Python/Node version, browser).

### Suggesting features

Open a GitHub issue that explains the problem you are trying to solve, your proposed solution, and any alternatives you considered.

### Submitting code

Fork the repository and create a feature branch from `main`. Make your changes, run the tests (see below), and open a pull request. Keep each PR focused on a single change, write descriptive commit messages, add tests for new functionality, and update documentation if behaviour changes. Make sure all tests pass before requesting review.

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

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for detailed coding conventions. Think of it like a restaurant kitchen: services handle the cooking (business logic), and endpoints are the waiters that carry plates to the table (5 to 15 lines each). On the frontend, use Tailwind CSS via variant objects from `lib/styles/` with no inline styles. Never use `print()` in backend code (use `logging` instead), and never use `alert()` in frontend code (use toast notifications).

## Project structure

```
backend/     # FastAPI REST API + SQLAlchemy
frontend/    # Next.js 14 React application
agent/       # OpenHands-based documentation generator
mcp-server/  # MCP server for Claude Code integration
docs/        # Deployment and development guides
```

## Questions?

If you are unsure about anything, open an issue and we will help.
