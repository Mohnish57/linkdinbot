#!/usr/bin/env bash
set -euo pipefail

# Usage: ./scripts/push_to_github.sh <remote-url> [branch]
# If no remote-url provided, reads GIT_REMOTE from environment.

REMOTE_URL=${1:-${GIT_REMOTE:-}}
BRANCH=${2:-main}

if [ -z "$REMOTE_URL" ]; then
  echo "No remote URL provided. Set GIT_REMOTE in environment or pass as first arg."
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "git not found in PATH"
  exit 1
fi

# Ensure we're at repo root (script is in scripts/)
ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT_DIR"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "This directory is not a git repo. Initialize first with 'git init' and commit."
  exit 1
fi

# Add remote if missing
if ! git remote get-url origin >/dev/null 2>&1; then
  git remote add origin "$REMOTE_URL"
  echo "Added remote origin -> $REMOTE_URL"
else
  echo "Remote origin already exists. Setting URL to $REMOTE_URL"
  git remote set-url origin "$REMOTE_URL"
fi

# Push
git add -A
git commit -m "chore: make configurable + add runner and helper scripts" || true
git push -u origin "$BRANCH"

echo "Pushed to $REMOTE_URL ($BRANCH)"
