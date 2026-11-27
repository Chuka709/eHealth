#!/usr/bin/env bash
# One-time (and safe to repeat) set-up of the production configuration on the server
# (docs/SERVER_INSTALL_PLAN.md §4, docs/SERVER_INSTALL_MANUAL.md). Run as root:
#
#   sudo infra/prod/prod-init.sh --domain app.example.mn --acme-email ops@example.mn \
#     --admin-cidr 203.0.113.10/32 --openbao-hostname bao.example.internal \
#     --openbao-upstream 10.0.0.5:8200 --backup-dir /srv/labtrack-backups
#
# Writes /etc/labtrack/labtrack.env (0600) from .env.production.example and the secret files in
# /etc/labtrack/secrets (folders 0700, files 0444 - bind-mounted into containers that run as
# their own users). Never overwrites a value or a file that is already there: running it again
# only fills what is missing. Prints no secret.
#
# Not made here: the OpenBao role ids and secret ids (`labtrack openbao-setup --out
# /etc/labtrack/secrets/openbao`, §3; this script then copies the role ids into the env file),
# openbao/ca.pem (from whoever runs OpenBao), BACKUP_AGE_RECIPIENT (the age public key, made
# offline - OPS_RUNBOOK §2).
set -euo pipefail
umask 077

ETC="${LABTRACK_ETC:-/etc/labtrack}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="$ETC/labtrack.env"
SECRETS="$ETC/secrets"

die() { echo "prod-init: $*" >&2; exit 1; }

domain="" email="" cidrs=() bao_host="" bao_up="" backup_dir=""
while [ $# -gt 0 ]; do
	case "$1" in
		--domain) domain="$2"; shift 2 ;;
		--acme-email) email="$2"; shift 2 ;;
		--admin-cidr) cidrs+=("$2"); shift 2 ;;
		--openbao-hostname) bao_host="$2"; shift 2 ;;
		--openbao-upstream) bao_up="$2"; shift 2 ;;
		--backup-dir) backup_dir="$2"; shift 2 ;;
		*) die "unknown option $1" ;;
	esac
done

# the office/VPN's public address: never a private (Docker's own) range or everyone - the API
# refuses those too (config.py, security review S2 M2)
for c in "${cidrs[@]}"; do
	case "$c" in
		*/*) ;;
		*) die "--admin-cidr $c: give a CIDR, e.g. 203.0.113.10/32" ;;
	esac
	case "$c" in
		10.*|192.168.*|172.1[6-9].*|172.2[0-9].*|172.3[01].*|0.0.0.0/*|127.*|*:*)
			die "--admin-cidr $c: a public IPv4 range only (not private, loopback, IPv6 or 0.0.0.0/0)" ;;
	esac
done

[ "${LABTRACK_ETC:-}" != "" ] || [ "$(id -u)" = 0 ] || die "run as root (sudo)"
command -v openssl >/dev/null || die "openssl is missing"

# --- helpers ------------------------------------------------------------------------------
# letters and digits only (hex): they go into URLs and SeaweedFS's JSON as they are. No pipe
# (`tr </dev/urandom | head` dies of SIGPIPE under pipefail); 4 bits per character.
rand() { local v; v="$(openssl rand -hex "$(( ($1 + 1) / 2 ))")"; printf '%s' "${v:0:$1}"; }

env_get() { grep -E "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2- || true; }

# sets KEY only when it is empty or absent - an existing value is never replaced
env_fill() {
	local key="$1" value="$2"
	if grep -qE "^$key=" "$ENV_FILE"; then
		[ -n "$(env_get "$key")" ] && return 0
		local tmp
		tmp="$(mktemp "$ETC/.env.XXXXXX")"
		awk -v k="$key" -v v="$value" 'BEGIN{FS=OFS="="} $1==k && !done {print k "=" v; done=1; next} {print}' \
			"$ENV_FILE" >"$tmp"
		chmod 600 "$tmp"
		mv "$tmp" "$ENV_FILE"
	else
		printf '%s=%s\n' "$key" "$value" >>"$ENV_FILE"
	fi
}

secret_fill() {  # secret_fill <relative path> <command that prints the value>
	local path="$SECRETS/$1"
	[ -s "$path" ] && { chmod 444 "$path"; return 0; }
	mkdir -p "$(dirname "$path")"
	chmod 700 "$(dirname "$path")"
	local tmp
	tmp="$(mktemp "$(dirname "$path")/.new.XXXXXX")"
	"${@:2}" >"$tmp"
	chmod 444 "$tmp"
	mv "$tmp" "$path"
	echo "  made $1"
}

empty_file() {  # a secret that stays empty until its feature is on
	local path="$SECRETS/$1"
	[ -e "$path" ] && return 0
	: >"$path"
	chmod 444 "$path"
	echo "  made $1 (empty)"
}

es256_key() { openssl ecparam -name prime256v1 -genkey -noout | openssl pkcs8 -topk8 -nocrypt; }

# --- the env file ---------------------------------------------------------------------------
mkdir -p "$ETC" "$SECRETS"
chmod 700 "$ETC" "$SECRETS"
if [ ! -e "$ENV_FILE" ]; then
	grep -vE '^\s*#|^\s*$' "$REPO/.env.production.example" >"$ENV_FILE"
	chmod 600 "$ENV_FILE"
	echo "made $ENV_FILE"
fi

for key in POSTGRES_PASSWORD LABTRACK_OWNER_PASSWORD LABTRACK_APP_PASSWORD LABTRACK_ADMIN_PASSWORD \
	LABTRACK_ADMIN_LOGIN_PASSWORD LABTRACK_MAINT_PASSWORD LABTRACK_PUSH_PASSWORD \
	LABTRACK_BACKUP_PASSWORD VALKEY_PASSWORD VALKEY_AI_PASSWORD; do
	env_fill "$key" "$(rand 40)"
done
for who in API WORKER MAINT BACKUP; do
	env_fill "S3_${who}_ACCESS_KEY" "lt$(rand 18)"
done
env_fill LABTRACK_SECRETS_DIR "$SECRETS"
[ -n "$domain" ] && env_fill LABTRACK_DOMAIN "$domain"
[ -n "$email" ] && env_fill ACME_EMAIL "$email"
if [ "${#cidrs[@]}" -gt 0 ]; then
	env_fill ADMIN_ALLOWLIST "${cidrs[*]}"
	env_fill ADMIN_ALLOWED_NETWORKS "[$(printf '"%s",' "${cidrs[@]}" | sed 's/,$//')]"
fi
[ -n "$bao_host" ] && env_fill OPENBAO_HOSTNAME "$bao_host"
[ -n "$bao_up" ] && env_fill OPENBAO_UPSTREAM "$bao_up"
[ -n "$backup_dir" ] && env_fill BACKUP_DIR "$backup_dir"
# role ids from `labtrack openbao-setup --out $SECRETS/openbao` (not secret: they name the role)
for who in api worker maint; do
	f="$SECRETS/openbao/$who.role_id"
	[ -s "$f" ] && env_fill "OPENBAO_${who^^}_ROLE_ID" "$(cat "$f")"
done

# --- the secret files -------------------------------------------------------------------------
secret_fill jwt_private_key.pem es256_key
secret_fill identity_pepper rand 48
for who in api worker maint backup; do
	secret_fill "s3/$who" rand 40
done
mkdir -p "$SECRETS/openbao" && chmod 700 "$SECRETS/openbao"
# openbao-setup writes its files 0600 for root; the containers need to read them
for f in "$SECRETS"/openbao/*.secret_id "$SECRETS"/openbao/ca.pem; do
	[ -e "$f" ] && chmod 444 "$f"
done
empty_file expo_access_token
empty_file anthropic_api_key

# --- what is still missing ------------------------------------------------------------------
missing=()
while IFS='=' read -r key value; do
	case "$key" in
		SENTRY_DSN|EXTRACTION_MODEL|LABTRACK_RELEASE|ALERT_*|OFFSITE_SYNC) continue ;;  # optional / by deploy
	esac
	[ -z "$value" ] && missing+=("$key")
done <"$ENV_FILE"
for f in openbao/api.secret_id openbao/worker.secret_id openbao/maint.secret_id openbao/ca.pem; do
	[ -s "$SECRETS/$f" ] || missing+=("secrets/$f")
done
if [ "${#missing[@]}" -gt 0 ]; then
	echo "still to fill in (by hand, or with the steps in docs/SERVER_INSTALL_MANUAL.md):"
	printf '  %s\n' "${missing[@]}"
	exit 3
fi
echo "prod-init: complete"
