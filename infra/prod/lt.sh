#!/usr/bin/env bash
# `docker compose` for the production stack (both files, the production env file):
#   infra/prod/lt.sh ps | logs -f api | run --rm migrate python -m labtrack.cli ...
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${LABTRACK_ENV_FILE:-/etc/labtrack/labtrack.env}"
[ -r "$ENV_FILE" ] || { echo "lt: $ENV_FILE is not readable (sudo?)" >&2; exit 1; }
exec docker compose --project-name labtrack \
	-f "$REPO/infra/docker-compose.yml" -f "$REPO/infra/docker-compose.prod.yml" \
	--env-file "$ENV_FILE" "$@"
