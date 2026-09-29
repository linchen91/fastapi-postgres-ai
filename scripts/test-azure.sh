#!/bin/sh
# Canonical Azure deployment smoke test. Run on demand — deliberately NOT wired
# into bitbucket-pipelines.yml: it hits the live Container Apps URL, which is
# scaled to zero when idle and lives on a Free Trial subscription that Azure
# pauses when its credit runs out, so it must not gate pull requests.
#
# Usage:   ./scripts/test-azure.sh
# Env:     AZURE_BASE_URL              target (default: the deployed FQDN)
#          AZURE_ADMIN_ACCOUNT         default 'admin'
#          AZURE_ADMIN_PASSWORD        default 'admin123'
#          AZURE_SMOKE_RETRIES         cold-start attempts (default 10)
#          AZURE_SMOKE_RETRY_DELAY     seconds between attempts (default 6)
#          AZURE_SMOKE_TIMEOUT         per-request seconds (default 90)
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

if ! command -v curl >/dev/null 2>&1; then
    echo "ERROR: curl not found in PATH" >&2
    exit 1
fi

BASE_URL=${AZURE_BASE_URL:-https://ca-fastapi-ai.jollywave-3dee1d3c.germanywestcentral.azurecontainerapps.io}
BASE_URL=${BASE_URL%/}
ADMIN_ACCOUNT=${AZURE_ADMIN_ACCOUNT:-admin}
ADMIN_PASSWORD=${AZURE_ADMIN_PASSWORD:-admin123}
RETRIES=${AZURE_SMOKE_RETRIES:-10}
RETRY_DELAY=${AZURE_SMOKE_RETRY_DELAY:-6}
TIMEOUT=${AZURE_SMOKE_TIMEOUT:-90}

BODY=$(mktemp)
HDRS=$(mktemp)
trap 'rm -f "$BODY" "$HDRS"' EXIT

PASS=0
FAIL=0
CODE=000

pass() {
    PASS=$((PASS + 1))
    echo "    ok   $1"
}

fail() {
    FAIL=$((FAIL + 1))
    echo "    FAIL $1 — $2"
}

fetch() {
    CODE=$(curl -sS -o "$BODY" -D "$HDRS" -w '%{http_code}' \
        --max-time "$TIMEOUT" "$@" 2>/dev/null) || CODE=000
}

check() {
    label=$1
    expected=$2
    shift 2
    fetch "$@"
    if [ "$CODE" = "$expected" ]; then
        pass "$label (HTTP $CODE)"
    else
        fail "$label" "expected HTTP $expected, got $CODE"
    fi
}

body_contains() {
    if grep -q "$2" "$BODY"; then
        pass "$1"
    else
        fail "$1" "response body does not contain '$2'"
    fi
}

header_absent() {
    if grep -qi "^$2:" "$HDRS"; then
        fail "$1" "unexpected '$2' header present: $(grep -i "^$2:" "$HDRS" | tr -d '\r')"
    else
        pass "$1"
    fi
}

header_starts_with() {
    value=$(grep -i "^$2:" "$HDRS" | head -1 | tr -d '\r' | sed "s/^[^:]*:[[:space:]]*//")
    case "$value" in
        "$3"*) pass "$1" ;;
        *) fail "$1" "expected $2 to start with '$3', got '$value'" ;;
    esac
}

echo "==> Azure smoke test against $BASE_URL"

echo "==> waiting for the app (cold start: $RETRIES attempt(s) x ${RETRY_DELAY}s)"
attempt=1
while [ "$attempt" -le "$RETRIES" ]; do
    fetch -H 'Accept: text/html' "$BASE_URL/"
    [ "$CODE" = "200" ] && break
    echo "        attempt $attempt/$RETRIES -> HTTP $CODE"
    sleep "$RETRY_DELAY"
    attempt=$((attempt + 1))
done
if [ "$CODE" != "200" ]; then
    echo "ERROR: $BASE_URL/ never became reachable (last HTTP $CODE)" >&2
    exit 1
fi
pass "SPA reachable (HTTP $CODE)"

ASSET=$(grep -o '/assets/[A-Za-z0-9._-]*\.js' "$BODY" | head -1 || true)
if [ -n "$ASSET" ]; then
    check "SPA bundle $ASSET" 200 "$BASE_URL$ASSET"
else
    fail "SPA bundle" "index.html references no /assets/*.js"
fi

check "runtime config" 200 "$BASE_URL/config.json"
body_contains "runtime config defines API_BASE_URL" 'API_BASE_URL'

check "swagger ui" 200 "$BASE_URL/docs"
check "openapi schema" 200 "$BASE_URL/openapi.json"
body_contains "openapi schema is not null (cold-start regression)" '"openapi"'
body_contains "openapi schema declares BearerAuth" 'BearerAuth'

check "GET /news serves directly" 200 "$BASE_URL/news"
header_absent "GET /news does not redirect (mixed-content regression)" 'location'
check "GET /news/ also serves" 200 "$BASE_URL/news/"
check "GET /news?force=true" 200 "$BASE_URL/news?force=true"
header_absent "force refresh does not redirect" 'location'

check "slash-less path redirects" 307 "$BASE_URL/roles"
header_starts_with "redirect keeps the https scheme (proxy-headers regression)" 'location' 'https://'

check "unauthenticated /events is rejected" 401 "$BASE_URL/events"

check "admin login" 200 -X POST -H 'Content-Type: application/json' \
    -d "{\"account\":\"$ADMIN_ACCOUNT\",\"password\":\"$ADMIN_PASSWORD\"}" \
    "$BASE_URL/auth/token"
body_contains "login returns a bearer token" '"access_token"'

TOKEN=$(sed -n 's/.*"access_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$BODY")
if [ -n "$TOKEN" ]; then
    check "authenticated read" 200 -H "Authorization: Bearer $TOKEN" "$BASE_URL/users/"
    body_contains "authenticated read returns data for $ADMIN_ACCOUNT" "$ADMIN_ACCOUNT"
else
    fail "authenticated read" "could not extract access_token — login likely failed"
fi

echo "==> $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
    echo "FAIL: Azure deployment smoke test found $FAIL problem(s)" >&2
    exit 1
fi
echo "PASS: Azure deployment smoke test succeeded"
