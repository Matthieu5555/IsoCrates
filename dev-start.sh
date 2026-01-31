#!/bin/bash
# Development startup script - runs backend/frontend locally, agent in Docker

set -e

echo "🚀 Starting IsoCrates Development Environment"
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if required commands exist
command -v python3 >/dev/null 2>&1 || { echo "❌ Python 3 is required but not installed."; exit 1; }
command -v node >/dev/null 2>&1 || { echo "❌ Node.js is required but not installed."; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "❌ Docker is required but not installed."; exit 1; }

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  No .env file found. Creating from .env.example..."
    cp .env.example .env
    echo "⚠️  Please edit .env and add your OPENROUTER_API_KEY"
    exit 1
fi

# Start the agent container
echo -e "${BLUE}📦 Starting Doc Agent container...${NC}"
docker compose -f docker-compose.dev.yml up -d --build
echo -e "${GREEN}✓ Agent container started${NC}"
echo ""

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Stopping services..."
    docker compose -f docker-compose.dev.yml down
    exit 0
}
trap cleanup INT TERM

echo -e "${YELLOW}📝 To start development servers, run in separate terminals:${NC}"
echo ""
echo -e "${BLUE}Terminal 1 - Backend:${NC}"
echo "  cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
echo ""
echo -e "${BLUE}Terminal 2 - Frontend:${NC}"
echo "  cd frontend && npm run dev"
echo ""
echo -e "${GREEN}Backend will be on:${NC} http://localhost:8000"
echo -e "${GREEN}Frontend will be on:${NC} http://localhost:3000"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop the agent container${NC}"

# Keep script running
wait
