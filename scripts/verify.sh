#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# IsoCrates Post-Deploy Verification
#
# Checks that every service is running and reachable after a deployment.
# Run this after deploy.sh or after any docker compose up.
#
# Usage:
#   ./scripts/verify.sh                          Auto-detect domain from .env.production
#   DOMAIN=docs.example.com ./scripts/verify.sh  Explicit domain
#   ./scripts/verify.sh --local                  Check localhost (development)
# =============================================================================

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PASS=0
FAIL=0

pass() { echo -e "  ${GREEN}PASS${NC}  $*"; PASS=$((PASS + 1)); }
fail() { echo -e "  ${RED}FAIL${NC}  $*"; FAIL=$((FAIL + 1)); }
skip() { echo -e "  ${YELLOW}SKIP${NC}  $*"; }

# --- Resolve base URL --------------------------------------------------------

if [ "${1:-}" = "--local" ]; then
    BASE_URL="http://localhost:8000"
    FRONTEND_URL="http://localhost:3001"
elif [ -n "${DOMAIN:-}" ]; then
    BASE_URL="https://${DOMAIN}"
    FRONTEND_URL="https://${DOMAIN}"
else
    ENV_FILE="$SCRIPT_DIR/.env.production"
    if [ -f "$ENV_FILE" ]; then
        DOMAIN=$(grep -E '^DOMAIN=' "$ENV_FILE" | cut -d'=' -f2- || true)
    fi
    if [ -z "${DOMAIN:-}" ]; then
        echo "No DOMAIN found. Pass --local for dev or set DOMAIN."
        exit 1
    fi
    BASE_URL="https://${DOMAIN}"
    FRONTEND_URL="https://${DOMAIN}"
fi

echo ""
echo "  IsoCrates Verification"
echo "  ======================"
echo "  Target: ${BASE_URL}"
echo ""

# --- 1. Docker containers ----------------------------------------------------

echo "Containers:"

if command -v docker >/dev/null 2>&1; then
    for svc in isocrates-postgres backend-api frontend; do
        if docker ps --format '{{.Names}}' | grep -q "^${svc}$"; then
            pass "$svc is running"
        else
            fail "$svc is not running"
        fi
    done

    # Agent containers are optional (--profile agent)
    for svc in doc-agent doc-worker; do
        if docker ps --format '{{.Names}}' | grep -q "^${svc}$"; then
            pass "$svc is running"
        else
            skip "$svc not running (agent profile may not be enabled)"
        fi
    done
else
    skip "Docker not available locally (remote deploy?)"
fi

echo ""

# --- 2. Health endpoint -------------------------------------------------------

echo "Health:"

HEALTH_RESPONSE=$(curl -sf --max-time 10 "${BASE_URL}/health" 2>/dev/null || true)

if [ -n "$HEALTH_RESPONSE" ]; then
    pass "Health endpoint reachable"

    if echo "$HEALTH_RESPONSE" | grep -q '"healthy"'; then
        pass "Status is healthy"
    else
        fail "Status is not healthy: $HEALTH_RESPONSE"
    fi

    if echo "$HEALTH_RESPONSE" | grep -q '"connected"'; then
        pass "Database is connected"
    else
        fail "Database is not connected"
    fi
else
    fail "Health endpoint unreachable at ${BASE_URL}/health"
fi

echo ""

# --- 3. Frontend --------------------------------------------------------------

echo "Frontend:"

FRONTEND_RESPONSE=$(curl -sf --max-time 10 -o /dev/null -w "%{http_code}" "${FRONTEND_URL}" 2>/dev/null || true)

if [ "$FRONTEND_RESPONSE" = "200" ]; then
    pass "Frontend is reachable"
else
    fail "Frontend returned HTTP ${FRONTEND_RESPONSE:-timeout} (expected 200)"
fi

echo ""

# --- 4. Webhook endpoint ------------------------------------------------------

echo "Webhook:"

WEBHOOK_CODE=$(curl -sf --max-time 10 -o /dev/null -w "%{http_code}" "${BASE_URL}/api/webhooks/github" 2>/dev/null || true)

# GET should return 405 (Method Not Allowed) — that means the route exists
if [ "$WEBHOOK_CODE" = "405" ] || [ "$WEBHOOK_CODE" = "401" ] || [ "$WEBHOOK_CODE" = "422" ]; then
    pass "Webhook endpoint is live (HTTP $WEBHOOK_CODE)"
else
    fail "Webhook endpoint returned HTTP ${WEBHOOK_CODE:-timeout} (expected 405/401/422)"
fi

echo ""

# --- 5. TLS -------------------------------------------------------------------

if [[ "$BASE_URL" == https://* ]]; then
    echo "TLS:"

    CERT_EXPIRY=$(echo | openssl s_client -servername "${DOMAIN}" -connect "${DOMAIN}:443" 2>/dev/null \
        | openssl x509 -noout -enddate 2>/dev/null \
        | cut -d'=' -f2- || true)

    if [ -n "$CERT_EXPIRY" ]; then
        pass "TLS certificate valid (expires: $CERT_EXPIRY)"
    else
        fail "Could not verify TLS certificate"
    fi

    echo ""
fi

# --- Summary ------------------------------------------------------------------

echo "  ----------------------"
echo -e "  ${GREEN}${PASS} passed${NC}, ${RED}${FAIL} failed${NC}"
echo ""

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
