FROM python:3.13-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies from lockfile
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy application
COPY app/ ./app/

# Expose port
EXPOSE 8000

# Run the application via uv so it uses the managed venv.
# WEB_CONCURRENCY controls worker count (default 1 for dev, set higher in production).
CMD ["sh", "-c", "uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-1}"]
