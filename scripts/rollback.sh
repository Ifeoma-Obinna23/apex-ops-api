#!/usr/bin/env bash
# Roll back to the version that was running before the last successful deploy.
# Usage: ./scripts/rollback.sh          (or ./scripts/rollback.sh 1.0.0 to choose)
set -euo pipefail
cd "$(dirname "$0")/.."

TARGET="${1:-$(cat .previous_version 2>/dev/null || true)}"
if [ -z "$TARGET" ]; then
  echo "No previous version recorded. Usage: ./scripts/rollback.sh <version>" >&2
  exit 1
fi

echo "Rolling back to $TARGET"
./scripts/deploy.sh "$TARGET"
