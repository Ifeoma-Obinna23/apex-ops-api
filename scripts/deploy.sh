#!/usr/bin/env bash
# Deploy a specific, CI-built version of the API.
# Usage: ./scripts/deploy.sh 1.1.0
# If the new version fails its checks, it automatically rolls back to the previous one.
set -euo pipefail
cd "$(dirname "$0")/.."

NEW="${1:?usage: ./scripts/deploy.sh <version>   e.g. 1.1.0}"
IMAGE="$(grep '^API_IMAGE=' .env | cut -d= -f2)"
OLD="$(grep '^API_TAG=' .env | cut -d= -f2)"

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" | tee -a deploy.log; }

switch_to() {
  sed -i "s|^API_TAG=.*|API_TAG=$1|" .env
  docker compose up -d --wait --wait-timeout 60 api
}

verify() {
  curl -fsS localhost:8000/readyz >/dev/null &&
    curl -fsS localhost:8000/version | grep -q "\"$1\""
}

log "deploy requested: $OLD -> $NEW ($IMAGE)"
docker pull "$IMAGE:$NEW"            # fail early if CI never published this version

if switch_to "$NEW" && verify "$NEW"; then
  echo "$OLD" > .previous_version
  log "deploy OK: now running $NEW (previous: $OLD)"
else
  log "deploy FAILED: $NEW did not pass checks, rolling back to $OLD"
  switch_to "$OLD"
  verify "$OLD" && log "auto-rollback OK: running $OLD"
  exit 1
fi
