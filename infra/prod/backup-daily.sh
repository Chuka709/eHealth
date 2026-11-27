#!/usr/bin/env bash
# The daily backup (systemd labtrack-backup.timer, 02:00 Ulaanbaatar; OPS_RUNBOOK §3): the
# encrypted dump and documents (`backup.sh` in its container), then the off-site copy, then a
# success mark the monitor checks (monitor.sh: older than 26 h = an alert).
#
# Off-site (SERVER_INSTALL_PLAN question 11): an executable root script at
# /etc/labtrack/offsite-sync (0700), called with the new backup folder as its one argument.
# It must keep no more than BACKUP_RETENTION_DAYS (35) there either - an older copy would keep
# a deleted account's data past what the privacy policy promises (SERVER_INSTALL_MANUAL §7 has
# an rclone example). The backups are age-encrypted: the far side cannot read them.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${LABTRACK_ENV_FILE:-/etc/labtrack/labtrack.env}"
STATE="${LABTRACK_STATE:-/var/lib/labtrack}"
SYNC="${LABTRACK_OFFSITE_SYNC:-/etc/labtrack/offsite-sync}"

get() { grep -E "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2- || true; }
mkdir -p "$STATE" && chmod 700 "$STATE"

out="$("$REPO/infra/prod/lt.sh" --profile ops run --rm -T backup backup.sh)"
printf '%s\n' "$out"
line="$(printf '%s\n' "$out" | grep -E '^backup ok: ' | tail -1 || true)"
[ -n "$line" ] || { echo "backup-daily: no 'backup ok' line" >&2; exit 1; }

stamp="$(printf '%s' "$line" | sed -E 's/^backup ok: ([0-9TZ]+) .*/\1/')"
folder="$(get BACKUP_DIR)/$stamp"
[ -d "$folder" ] || { echo "backup-daily: $folder is not there" >&2; exit 1; }
touch "$STATE/backup-ok"

if [ -x "$SYNC" ]; then
	"$SYNC" "$folder"
	touch "$STATE/offsite-ok"
fi
echo "backup-daily: done"
