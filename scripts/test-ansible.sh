#!/bin/sh
# Canonical Ansible test entrypoint (used locally and by Bitbucket Pipelines).
# Runs: ansible-lint, deploy playbook syntax-check, inventory validation, and
# an offline assertion playbook — no hosts, cluster, or secrets required.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

if ! command -v ansible-playbook >/dev/null 2>&1; then
    echo "ERROR: ansible-playbook not found. Install with: pip install ansible-core" >&2
    exit 1
fi

if ! command -v ansible-lint >/dev/null 2>&1; then
    echo "ERROR: ansible-lint not found. Install with: pip install ansible-lint" >&2
    exit 1
fi

echo "==> ansible-lint"
(cd ansible && ansible-lint .)

echo "==> ansible-playbook --syntax-check (deploy.yml)"
(cd ansible && ansible-playbook --syntax-check -i inventory/hosts.yml playbooks/deploy.yml)

echo "==> ansible-inventory --list"
ansible-inventory -i ansible/inventory/hosts.yml --list > /dev/null

echo "==> ansible-playbook test_config.yml (offline assertions)"
(cd ansible && ansible-playbook -i inventory/hosts.yml playbooks/test_config.yml)

echo "PASS: all ansible checks succeeded"
