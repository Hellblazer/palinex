#!/usr/bin/env bash
# Install palinex git hooks by pointing core.hooksPath at .githooks/
#
# Idempotent. Safe to re-run after pulling new hooks.
#
# Usage:
#   scripts/install-hooks.sh

set -e

cd "$(git rev-parse --show-toplevel)"

chmod +x .githooks/pre-commit .githooks/pre-push 2>/dev/null || true

current=$(git config --get core.hooksPath 2>/dev/null || echo "")
target=".githooks"

if [ "$current" = "$target" ]; then
  echo "✓ core.hooksPath already set to $target"
else
  git config core.hooksPath "$target"
  echo "✓ core.hooksPath set to $target"
fi

echo
echo "Active hooks:"
ls -l .githooks/ | grep -E '^-' | awk '{print "  ", $NF}'
echo
echo "Skip with: git commit --no-verify  /  git push --no-verify"
