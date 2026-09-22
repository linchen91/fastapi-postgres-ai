#!/bin/sh
# Canonical Terraform test entrypoint (used locally and by Bitbucket Pipelines).
# Runs: fmt -check, init -backend=false, validate, and native terraform test
# (plan assertions with a dummy kubeconfig — no cluster or secrets required).
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

TF_DIR="terraform"
DUMMY_KUBECONFIG="/tmp/fastapi-postgres-ai-dummy-kubeconfig"

echo "==> Creating dummy kubeconfig at ${DUMMY_KUBECONFIG}"
cat > "${DUMMY_KUBECONFIG}" <<'EOF'
apiVersion: v1
kind: Config
clusters:
- name: dummy
  cluster:
    server: https://127.0.0.1:6443
    insecure-skip-tls-verify: true
contexts:
- name: dummy
  context:
    cluster: dummy
    user: dummy
current-context: dummy
users:
- name: dummy
  user:
    token: dummy-token
EOF
export TF_VAR_config_path="${DUMMY_KUBECONFIG}"

echo "==> terraform fmt -check"
terraform -chdir="${TF_DIR}" fmt -check -recursive

echo "==> terraform init -backend=false"
terraform -chdir="${TF_DIR}" init -backend=false -input=false

echo "==> terraform validate"
terraform -chdir="${TF_DIR}" validate

echo "==> terraform test"
terraform -chdir="${TF_DIR}" test

echo "PASS: all terraform checks succeeded"
