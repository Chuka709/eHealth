#!/usr/bin/env bash
# Deploy a release on the production server (docs/SERVER_INSTALL_PLAN.md §6; manual:
# docs/SERVER_INSTALL_MANUAL.md §6). Run as root from the repository checkout:
#
#   sudo infra/prod/deploy.sh <tag>                     # a signed release tag (git verify-tag)
#   sudo infra/prod/deploy.sh --allow-unsigned <ref>    # beta without signing keys: says so loudly
#   sudo infra/prod/deploy.sh --rollback                # the release before the current one
#
# Order: images built and tagged with the commit -> a backup of the running database (when
# there is one) -> migrations -> every service up and healthy -> the public healthcheck. Only
# then is the release written to the env file and the release log: a failure anywhere leaves
# the env file naming the release that was running (security review S3 M4).
# Rollback starts the previous images again but does NOT undo migrations: only for a release
# whose migrations the previous code still works with (each migration's notes say so).
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
LT="$REPO/infra/prod/lt.sh"
ENV_FILE="${LABTRACK_ENV_FILE:-/etc/labtrack/labtrack.env}"
STATE="${LABTRACK_STATE:-/var/lib/labtrack}"
RELEASES="$STATE/releases.log"   # a stack: the running release is the last line

die() { echo "deploy: $*" >&2; exit 1; }
step() { echo "--- $*"; }

[ "$(id -u)" = 0 ] || die "run as root (sudo)"
[ -r "$ENV_FILE" ] || die "$ENV_FILE missing - run infra/prod/prod-init.sh first"
mkdir -p "$STATE" && chmod 700 "$STATE"

get() { grep -E "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2- || true; }

set_release() {
	local tmp
	tmp="$(mktemp "$(dirname "$ENV_FILE")/.env.XXXXXX")"
	if grep -qE '^LABTRACK_RELEASE=' "$ENV_FILE"; then
		sed "s/^LABTRACK_RELEASE=.*/LABTRACK_RELEASE=$1/" "$ENV_FILE" >"$tmp"
	else
		{ cat "$ENV_FILE"; echo "LABTRACK_RELEASE=$1"; } >"$tmp"
	fi
	chmod 600 "$tmp"
	mv "$tmp" "$ENV_FILE"
}

public_health() {
	local domain
	domain="$(get LABTRACK_DOMAIN)"
	step "https://$domain/api/v1/healthz"
	for _ in $(seq 1 30); do
		curl -fsS --max-time 5 "https://$domain/api/v1/healthz" >/dev/null 2>&1 && return 0
		sleep 5
	done
	return 1
}

current="$(get LABTRACK_RELEASE)"

if [ "${1:-}" = "--rollback" ]; then
	[ "$(tail -1 "$RELEASES" 2>/dev/null)" = "$current" ] || die "$RELEASES does not end with $current"
	previous="$(tail -2 "$RELEASES" | head -1)"
	[ "$(wc -l <"$RELEASES")" -ge 2 ] && [ -n "$previous" ] || die "no earlier release in $RELEASES"
	docker image inspect "labtrack-backend:$previous" >/dev/null 2>&1 \
		|| die "image labtrack-backend:$previous is gone"
	step "rolling back $current -> $previous (migrations stay as they are)"
	LABTRACK_RELEASE="$previous" "$LT" up -d --no-build --wait --remove-orphans
	set_release "$previous"
	# pop: a second rollback goes one further back, never forward again
	sed -i '$ d' "$RELEASES"
	public_health || die "rolled back to $previous, but the public site does not answer"
	echo "deploy: rolled back to $previous"
	exit 0
fi

signed=1
if [ "${1:-}" = "--allow-unsigned" ]; then
	signed=0
	shift
fi
ref="${1:?a release tag (or --allow-unsigned <ref>, or --rollback)}"
cd "$REPO"
[ -z "$(git status --porcelain --untracked-files=no)" ] || die "the checkout has local changes"
step "fetching $ref"
git fetch --quiet --tags origin
if git rev-parse --verify --quiet "refs/tags/$ref" >/dev/null; then
	target="refs/tags/$ref"
	if [ "$signed" = 1 ]; then
		git verify-tag "$ref" || die "tag $ref is not signed by a trusted key (or --allow-unsigned)"
	fi
elif [ "$signed" = 0 ] && git rev-parse --verify --quiet "refs/remotes/origin/$ref" >/dev/null; then
	target="refs/remotes/origin/$ref"  # the remote's branch, never a stale local one
elif [ "$signed" = 0 ] && git rev-parse --verify --quiet "$ref^{commit}" >/dev/null; then
	target="$ref"
else
	die "$ref is not a release tag"
fi
[ "$signed" = 1 ] || echo "deploy: WARNING - $ref is deployed without a signature check" >&2
git checkout --quiet --detach "$target"
release="$(git rev-parse --short=12 HEAD)"
step "release $release (running now: ${current:-none})"

# the new release only in this process's environment (it wins over --env-file) until it is live
export LABTRACK_RELEASE="$release"
step "building images"
"$LT" build --pull api web bao-gateway ai-proxy backup

if LABTRACK_RELEASE="${current:-$release}" "$LT" ps --status running --services 2>/dev/null \
	| grep -qx postgres; then
	step "backup before migrating"
	"$LT" --profile ops run --rm backup backup.sh || die "backup failed - nothing changed"
fi

step "database, queue, storage, scanner, keys"
"$LT" up -d --wait postgres valkey seaweedfs freshclam clamav bao-gateway
"$LT" up --exit-code-from s3-init s3-init
step "migrations"
"$LT" run --rm migrate
step "everything else"
"$LT" up -d --wait --remove-orphans

public_health || die "the stack is up but the public site does not answer (DNS, 80/443, certificate?) - the env file still names ${current:-no release}"
set_release "$release"
echo "$release" >>"$RELEASES"
echo "deploy: $release is live"
