#!/usr/bin/env bash
# Health of the production server, every 5 minutes (systemd labtrack-monitor.timer;
# SERVER_INSTALL_PLAN §6). A check that starts failing, or recovers, sends one message; one
# that stays failing is repeated every 6 hours. Messages name the check only - never a user,
# a value, a log line.
#
# Where messages go (SERVER_INSTALL_PLAN question 10), from /etc/labtrack/labtrack.env:
#   ALERT_TELEGRAM_TOKEN + ALERT_TELEGRAM_CHAT   a Telegram bot and chat
#   ALERT_WEBHOOK_URL                            any webhook taking JSON {"text": "..."}
# With neither, problems go to the journal only (journalctl -u labtrack-monitor).
#
#   infra/prod/monitor.sh            run the checks (what the timer does)
#   infra/prod/monitor.sh --test     send a test message
#   infra/prod/monitor.sh --remind <text>   send a reminder (the monthly restore drill)
set -uo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${LABTRACK_ENV_FILE:-/etc/labtrack/labtrack.env}"
STATE="${LABTRACK_STATE:-/var/lib/labtrack}"
REPEAT_S=$((6 * 3600))

get() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || true; }
host="$(hostname -s)"

send() {
	local text="[LabTrack $host] $1" token chat hook
	token="$(get ALERT_TELEGRAM_TOKEN)" chat="$(get ALERT_TELEGRAM_CHAT)" hook="$(get ALERT_WEBHOOK_URL)"
	echo "monitor: $1"
	# the bot token and the webhook URL (a secret too) reach curl on stdin, never in `ps`
	if [ -n "$token" ] && [ -n "$chat" ]; then
		printf 'url = "https://api.telegram.org/bot%s/sendMessage"\n' "$token" \
			| curl -fsS --max-time 10 -o /dev/null -K - \
				--data-urlencode "chat_id=$chat" --data-urlencode "text=$text" \
			|| echo "monitor: telegram failed" >&2
	fi
	if [ -n "$hook" ]; then
		printf 'url = "%s"\n' "$hook" \
			| curl -fsS --max-time 10 -o /dev/null -K - -H 'Content-Type: application/json' \
				--data "$(jq -cn --arg t "$text" '{text: $t}')" \
			|| echo "monitor: webhook failed" >&2
	fi
}

if [ "${1:-}" = "--test" ]; then
	send "test message - alerts reach you"
	exit 0
fi
if [ "${1:-}" = "--remind" ]; then  # a scheduled reminder (labtrack-restore-drill.timer)
	send "REMINDER: ${2:?}"
	exit 0
fi

mkdir -p "$STATE/monitor"
now="$(date -u +%s)"
failed=0

# check <name> <command...>: alert on a change, repeat while it lasts
check() {
	local name="$1" mark
	mark="$STATE/monitor/$(printf '%s' "$1" | tr -c 'A-Za-z0-9' '_')"
	shift
	if "$@" >/dev/null 2>&1; then
		if [ -e "$mark" ]; then
			rm -f "$mark"
			send "OK again: $name"
		fi
	else
		failed=1
		if [ ! -e "$mark" ] || [ $((now - $(stat -c %Y "$mark"))) -ge "$REPEAT_S" ]; then
			touch "$mark"
			send "PROBLEM: $name"
		fi
	fi
}

domain="$(get LABTRACK_DOMAIN)"
backup_dir="$(get BACKUP_DIR)"

public_health() { curl -fsS --max-time 10 "https://$domain/api/v1/healthz"; }
# every long-running service is up, and healthy where it has a healthcheck
SERVICES="postgres valkey seaweedfs freshclam clamav bao-gateway api worker maint-worker
push-worker ai-worker ai-proxy beat web caddy"
containers_healthy() {
	local listed service state health
	# a stack that is down, or a `ps` that fails, fails too
	listed="$("$REPO/infra/prod/lt.sh" ps --all --format '{{.Service}} {{.State}} {{.Health}}')" \
		|| return 1
	for service in $SERVICES; do
		state="" health=""
		read -r state health < <(printf '%s\n' "$listed" | awk -v s="$service" '$1 == s {print $2, $3}')
		[ "$state" = "running" ] || return 1
		[ -z "$health" ] || [ "$health" = "healthy" ] || return 1
	done
}
# the API's own readiness: database, queue and the key service (OpenBao sealed = not ready)
api_ready() {
	"$REPO/infra/prod/lt.sh" exec -T api python -c "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/readyz', timeout=10).status != 200)"
}
# OpenBao's own certificate (825 days, infra/openbao/make-tls.sh): expired, every key call fails
bao_cert_valid_30_days() {
	local upstream ca
	upstream="$(get OPENBAO_UPSTREAM)" ca="$(get LABTRACK_SECRETS_DIR)/openbao/ca.pem"
	echo | openssl s_client -servername "$(get OPENBAO_HOSTNAME)" -connect "$upstream" -CAfile "$ca" \
		-verify_return_error 2>/dev/null | openssl x509 -noout -checkend $((30 * 86400))
}
cert_valid_14_days() {
	echo | openssl s_client -servername "$domain" -connect "$domain:443" 2>/dev/null \
		| openssl x509 -noout -checkend $((14 * 86400))
}
disk_below() {  # disk_below <path> <percent>
	local used
	used="$(df --output=pcent "$1" | tail -1 | tr -dc '0-9')"
	[ "$used" -lt "$2" ]
}
fresh() {  # fresh <file> <seconds>
	[ -e "$1" ] && [ $((now - $(stat -c %Y "$1"))) -lt "$2" ]
}
raid_whole() {  # no md array with a missing member ([U_] in /proc/mdstat)
	[ ! -e /proc/mdstat ] || ! grep -qE '\[U*_+U*\]' /proc/mdstat
}

check "public site https://$domain" public_health
check "containers running and healthy" containers_healthy
check "API ready (database, queue, keys)" api_ready
check "TLS certificate valid 14+ days" cert_valid_14_days
check "OpenBao certificate valid 30+ days" bao_cert_valid_30_days
check "disk / below 80%" disk_below / 80
check "docker disk below 80%" disk_below /var/lib/docker 80
[ -n "$backup_dir" ] && check "backup disk below 80%" disk_below "$backup_dir" 80
check "daily backup in the last 26 h" fresh "$STATE/backup-ok" $((26 * 3600))
[ -x /etc/labtrack/offsite-sync ] && check "off-site copy in the last 26 h" fresh "$STATE/offsite-ok" $((26 * 3600))
check "RAID arrays complete" raid_whole

exit "$failed"
