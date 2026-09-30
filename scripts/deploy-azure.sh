#!/bin/sh
# Canonical Azure Container Apps deployment entrypoint — the same script runs
# locally and in Bitbucket Pipelines (mirrors scripts/test-*.sh: one entrypoint
# for both environments).
#
# Usage:  ./scripts/deploy-azure.sh [build|update|verify|all]
#
#   build    docker build + push the image to ACR        (needs docker + ACR_* vars)
#   update   point Container App ca-fastapi-ai at it     (needs az  + AZ_RESOURCE_GROUP/CA_NAME)
#   verify   live smoke test of the deployed URL         (wraps scripts/test-azure.sh)
#   all      build -> update -> verify                   (default; local use)
#
# Env (defaults are loaded from ~/.config/fastapi-postgres-ai/azure.env when present):
#   ACR_LOGIN_SERVER   default acrfastapiai001.azurecr.io
#   ACR_USERNAME / ACR_PASSWORD     ACR push credentials (optional: reuses an
#                                   existing `docker login` when unset — e.g. after
#                                   `az acr login --name $ACR_NAME`)
#   AZ_RESOURCE_GROUP  default rg-fastapi-postgres-ai
#   CA_NAME            default ca-fastapi-ai
#   IMAGE_NAME         default fastapi-postgres-ai
#   TAG                default: $BITBUCKET_COMMIT[:7] in CI, else git short SHA
#   AZURE_TENANT_ID + AZURE_CLIENT_ID + AZURE_CLIENT_SECRET
#                                  when all three are set, `update` logs in as that
#                                  service principal (CI); otherwise an already
#                                  logged-in az context is used (local)
#   AZURE_SUBSCRIPTION_ID  optional subscription to select after az login
#   DRY_RUN=1          print the docker/az commands instead of running them
#   AZURE_SMOKE_*      forwarded to scripts/test-azure.sh (verify raises the
#                      cold-start retries to 20x6s by default)
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

ACTION=${1:-all}

case "$ACTION" in
    -h|--help|help)
        sed -n '2,/^set -eu/p' "$0" | sed -e '/^set -eu/d' -e 's/^# \{0,1\}//'
        exit 0
        ;;
    build|update|verify|all) ;;
    *)
        echo "ERROR: unknown action '$ACTION' (expected build|update|verify|all)" >&2
        exit 2
        ;;
esac

# Secrets live outside the repo (AZURE_RUNBOOK.md); CI has no such file.
AZURE_ENV_FILE=${AZURE_ENV_FILE:-$HOME/.config/fastapi-postgres-ai/azure.env}
if [ -f "$AZURE_ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$AZURE_ENV_FILE"
    set +a
fi

ACR_LOGIN_SERVER=${ACR_LOGIN_SERVER:-acrfastapiai001.azurecr.io}
AZ_RESOURCE_GROUP=${AZ_RESOURCE_GROUP:-rg-fastapi-postgres-ai}
CA_NAME=${CA_NAME:-ca-fastapi-ai}
IMAGE_NAME=${IMAGE_NAME:-fastapi-postgres-ai}

ACR_USERNAME=${ACR_USERNAME:-}
ACR_PASSWORD=${ACR_PASSWORD:-}
AZURE_TENANT_ID=${AZURE_TENANT_ID:-}
AZURE_CLIENT_ID=${AZURE_CLIENT_ID:-}
AZURE_CLIENT_SECRET=${AZURE_CLIENT_SECRET:-}
AZURE_SUBSCRIPTION_ID=${AZURE_SUBSCRIPTION_ID:-}

DRY_RUN=${DRY_RUN:-0}

run() {
    if [ "$DRY_RUN" = "1" ]; then
        # Never print credential values, even in dry-run output.
        line=
        for arg in "$@"; do
            case "$arg" in
                "${AZURE_CLIENT_SECRET:-__unset__}"|"${ACR_PASSWORD:-__unset__}") arg='***' ;;
            esac
            line="$line $arg"
        done
        echo "DRY-RUN:$line"
    else
        "$@"
    fi
}

die() {
    echo "ERROR: $*" >&2
    exit 1
}

image_ref() {
    printf '%s/%s:%s' "$ACR_LOGIN_SERVER" "$IMAGE_NAME" "$1"
}

resolve_tag() {
    if [ -n "${TAG:-}" ]; then
        printf '%s' "$TAG"
    elif [ -n "${BITBUCKET_COMMIT:-}" ]; then
        # Checked before git: every CI step must derive the same tag, and some
        # step images (docker:xx-cli) ship no git at all.
        printf '%s' "$BITBUCKET_COMMIT" | cut -c1-7
    elif command -v git >/dev/null 2>&1 && git rev-parse --short HEAD >/dev/null 2>&1; then
        git rev-parse --short HEAD
    else
        die "cannot derive an image tag (no git, no BITBUCKET_COMMIT) — set TAG=..."
    fi
}

build() {
    command -v docker >/dev/null 2>&1 || die "docker not found in PATH (build step needs a Docker daemon)"
    TAG=$(resolve_tag)
    IMG=$(image_ref "$TAG")
    LATEST=$(image_ref latest)

    if [ -n "$ACR_USERNAME" ] && [ -n "$ACR_PASSWORD" ]; then
        printf '%s' "$ACR_PASSWORD" | run docker login "$ACR_LOGIN_SERVER" \
            --username "$ACR_USERNAME" --password-stdin
    else
        echo "ACR_USERNAME/ACR_PASSWORD not set — reusing existing docker credentials"
    fi

    echo "==> docker build -t $IMG -t $LATEST"
    run docker build -t "$IMG" -t "$LATEST" "$ROOT"

    echo "==> docker push $IMG"
    run docker push "$IMG"
    echo "==> docker push $LATEST"
    run docker push "$LATEST"

    echo "BUILT_IMAGE=$IMG"
}

update() {
    command -v az >/dev/null 2>&1 || die "az CLI not found in PATH (deploy step needs mcr.microsoft.com/azure-cli)"

    if [ -n "$AZURE_CLIENT_ID" ] && [ -n "$AZURE_CLIENT_SECRET" ] && [ -n "$AZURE_TENANT_ID" ]; then
        echo "==> az login --service-principal ($AZURE_CLIENT_ID)"
        run az login --service-principal \
            --username "$AZURE_CLIENT_ID" \
            --password "$AZURE_CLIENT_SECRET" \
            --tenant "$AZURE_TENANT_ID" \
            --only-show-errors --output none
        if [ -n "$AZURE_SUBSCRIPTION_ID" ]; then
            run az account set --subscription "$AZURE_SUBSCRIPTION_ID" --only-show-errors
        fi
    elif ! az account show --only-show-errors >/dev/null 2>&1; then
        die "az is not logged in and AZURE_CLIENT_ID/AZURE_CLIENT_SECRET/AZURE_TENANT_ID are not all set"
    fi

    TAG=$(resolve_tag)
    IMG=$(image_ref "$TAG")

    echo "==> az containerapp update -g $AZ_RESOURCE_GROUP -n $CA_NAME --image $IMG"
    # --image alone: env vars, ingress and scaling are left untouched.
    run az containerapp update \
        --resource-group "$AZ_RESOURCE_GROUP" \
        --name "$CA_NAME" \
        --image "$IMG" \
        --only-show-errors --output none

    echo "UPDATED_IMAGE=$IMG"
}

verify() {
    # New revision starts from zero replicas — allow a longer cold start than
    # scripts/test-azure.sh uses locally.
    AZURE_SMOKE_RETRIES=${AZURE_SMOKE_RETRIES:-20}
    export AZURE_SMOKE_RETRIES
    echo "==> scripts/test-azure.sh (cold-start retries: $AZURE_SMOKE_RETRIES)"
    exec "$ROOT/scripts/test-azure.sh"
}

case "$ACTION" in
    build)  build ;;
    update) update ;;
    verify) verify ;;
    all)    build; update; verify ;;
esac
