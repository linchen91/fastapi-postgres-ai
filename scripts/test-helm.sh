#!/bin/sh
# Canonical Helm chart test entrypoint (used locally and by Bitbucket Pipelines).
# Runs: helm lint and helm template with dummy secrets — no cluster required.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

if ! command -v helm >/dev/null 2>&1; then
  echo "ERROR: helm binary not found in PATH" >&2
  exit 1
fi

echo "==> helm lint helm/"
helm lint helm/

echo "==> helm template helm/ (dummy secrets)"
helm template fastapi-postgres-ai helm/ \
  --set secret.postgresPassword=ci-password \
  --set secret.secretKey=ci-secret-key \
  --set secret.openrouterApiKey=ci-openrouter-key \
  --set secret.tavilyApiKey=ci-tavily-key >/dev/null

echo "PASS: all helm checks succeeded"
