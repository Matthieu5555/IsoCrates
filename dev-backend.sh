#!/bin/bash
# Start backend development server

set -e

echo "Starting Backend Development Server"

cd "$(dirname "$0")/backend"

# Check for .env
if [ ! -f .env ]; then
    echo "Creating .env file..."
    cat > .env << EOF
DATABASE_URL=sqlite:///./alto_isocrates.db
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3001
LOG_LEVEL=DEBUG
EOF
fi

echo "Backend ready"
echo "Starting server on http://localhost:8000"
echo "API docs: http://localhost:8000/docs"
echo ""

# Start server
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
