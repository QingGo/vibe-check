#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE_DIR="${WORKSPACE_DIR:-$PWD}"
HOME_DIR="${HOME:-/root}"
IMAGE_TAG="${CODEX_PODMAN_IMAGE:-vc-fcst/codex:0.104}"

podman run --rm -i \
  -v "${WORKSPACE_DIR}:/workspace" \
  -w /workspace \
  -v "${HOME_DIR}/.codex:/root/.codex" \
  --env-file "${ROOT_DIR}/.env" \
  "${IMAGE_TAG}" \
  codex exec - --json --skip-git-repo-check --ephemeral --dangerously-bypass-approvals-and-sandbox
