#!/bin/bash
# Start frontend development server

set -e

echo "🚀 Starting Frontend Development Server"

cd "$(dirname "$0")/frontend"

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    npm install
fi

# Check for .env.local
if [ ! -f .env.local ]; then
    echo "⚠️  Creating .env.local file..."
    cat > .env.local << EOF
NEXT_PUBLIC_API_URL=http://localhost:8000
EOF
fi

echo "✓ Frontend ready"
echo "🌐 Starting server on http://localhost:3000"
echo ""

# Start server
npm run dev -- -H 0.0.0.0
