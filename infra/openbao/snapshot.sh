#!/usr/bin/env bash
# Daily OpenBao snapshot on the OpenBao VM (SERVER_INSTALL_PLAN §3.7; SERVER_INSTALL_MANUAL.md §4),
# from cron. Settings in /etc/openbao/snapshot.env (root 0600):
#   BAO_ADDR=https://<host>:8200  BAO_CACERT=/etc/openbao/tls/ca.crt  BAO_TOKEN_FILE=/root/.bao-snapshot
#   BACKUP_AGE_RECIPIENT=age1...  SNAPSHOT_DIR=/srv/bao-snapshots
#   OFFSITE_SYNC=/etc/openbao/offsite-sync   (optional: a root script, called with the new file)
#   ALERT_TELEGRAM_TOKEN= ALERT_TELEGRAM_CHAT= ALERT_WEBHOOK_URL=   (optional: where a failure goes)
#
# The snapshot holds every key - the KEK and each user's: it is encrypted to the backup age key,
# kept 35 days at most here and off-site (a destroyed user key lives on in every older
# snapshot, so a longer retention would undo crypto-shredding), and its token (read
# sys/storage/raft/snapshot only) is renewed on every run so it never lapses.
# Losing every snapshot and the VM's disk means losing every key, so every document: a failed
# run is an alert, not a log line.
set -Eeuo pipefail
umask 077
CONF="${SNAPSHOT_ENV:-/etc/openbao/snapshot.env}"
# shellcheck disable=SC1090 # root's own settings file
set -a && . "$CONF" && set +a
CACERT="${BAO_CACERT:-/etc/openbao/tls/ca.crt}"
KEEP_DAYS=35

alert() {  # the check's name only; secrets go to curl on stdin, never in its arguments
	local text
	text="[LabTrack OpenBao $(hostname -s)] $1"
	echo "snapshot: $1" >&2
	if [ -n "${ALERT_TELEGRAM_TOKEN:-}" ] && [ -n "${ALERT_TELEGRAM_CHAT:-}" ]; then
		printf 'url = "https://api.telegram.org/bot%s/sendMessage"\n' "$ALERT_TELEGRAM_TOKEN" \
			| curl -fsS --max-time 10 -o /dev/null -K - --data-urlencode "chat_id=$ALERT_TELEGRAM_CHAT" \
				--data-urlencode "text=$text" || true
	fi
	if [ -n "${ALERT_WEBHOOK_URL:-}" ]; then
		printf 'url = "%s"\n' "$ALERT_WEBHOOK_URL" \
			| curl -fsS --max-time 10 -o /dev/null -K - -H 'Content-Type: application/json' \
				--data "$(jq -cn --arg t "$text" '{text: $t}')" || true
	fi
}

out=""
on_error() {
	[ -n "$out" ] && rm -f "$out.partial"
	alert "PROBLEM: daily OpenBao snapshot failed"
}
trap on_error ERR

# a missing setting or tool is a failed snapshot too: it must alert, not just exit
for v in BAO_ADDR BAO_TOKEN_FILE BACKUP_AGE_RECIPIENT SNAPSHOT_DIR; do
	[ -n "${!v:-}" ] || { echo "snapshot: $v is not set" >&2; false; }
done
command -v age >/dev/null || { echo "snapshot: install age" >&2; false; }

# --check (a second cron line): the newest snapshot is under 26 hours old - catches a cron
# that never ran, which no failure trap can
if [ "${1:-}" = "--check" ]; then
	trap - ERR
	newest="$(find "$SNAPSHOT_DIR" -maxdepth 1 -name 'bao-*.snap.age' -mmin -$((26 * 60)) | head -1)"
	if [ -z "$newest" ]; then
		alert "PROBLEM: no OpenBao snapshot in the last 26 h"
		exit 1
	fi
	echo "snapshot check ok"
	exit 0
fi

mkdir -p "$SNAPSHOT_DIR"
# old ones go first, whatever happens to today's
find "$SNAPSHOT_DIR" -maxdepth 1 -name 'bao-*.snap.age' -mtime +$((KEEP_DAYS - 1)) -delete
find "$SNAPSHOT_DIR" -maxdepth 1 -name '*.partial' -mmin +60 -delete

bao() {  # bao <method> <path>: the token travels on stdin (not in `ps`)
	printf 'header = "X-Vault-Token: %s"\n' "$(cat "$BAO_TOKEN_FILE")" \
		| curl -fsS --max-time 300 --cacert "$CACERT" -K - -X "$1" "$BAO_ADDR/v1/$2"
}

bao POST auth/token/renew-self >/dev/null
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="$SNAPSHOT_DIR/bao-$stamp.snap.age"
bao GET sys/storage/raft/snapshot | age -r "$BACKUP_AGE_RECIPIENT" -o "$out.partial"
[ -s "$out.partial" ]
mv "$out.partial" "$out"

if [ -n "${OFFSITE_SYNC:-}" ]; then
	# the operator's script: copy the file, and keep 35 days at most there too
	"$OFFSITE_SYNC" "$out"
fi
echo "snapshot ok: $(basename "$out")"
