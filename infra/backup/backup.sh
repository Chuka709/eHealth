#!/bin/sh
# One encrypted backup of the database and the document store (Phase 8.2; docs/OPS_RUNBOOK.md).
#
# /backups/<UTC time>/
#   db.dump.age       pg_dump -Fc of labtrack, encrypted to BACKUP_AGE_RECIPIENT
#   globals.sql.age   roles and grants (pg_dumpall --globals-only --no-role-passwords), encrypted
#   files.tar.age     every object of the document bucket (already sealed by the app), encrypted
#   manifest.json     what a restore must find: migration head, row counts, the tables under
#                     FORCE row security, the number of policies and of stored objects - numbers
#                     and table names only, no values (CLAUDE.md rule 3)
#   SHA256SUMS
# The dump and the manifest come from one exported snapshot, so they always agree. Runs as
# labtrack_backup (BYPASSRLS + pg_read_all_data; infra/postgres/init/03-backup-role.sh), its
# password from a compose secret into a pgpass file on tmpfs - never in the environment.
# A backup is written under a hidden name and renamed when complete. Backups are kept for
# BACKUP_RETENTION_DAYS (35, as the privacy policy says) counted from their name.
set -euo pipefail
umask 077

: "${BACKUP_AGE_RECIPIENT:?set BACKUP_AGE_RECIPIENT (the age public key) in .env}"
case "$BACKUP_AGE_RECIPIENT" in age1*) ;; *) echo "BACKUP_AGE_RECIPIENT is not an age public key" >&2; exit 2 ;; esac
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-35}"
case "$RETENTION_DAYS" in '' | *[!0-9]*) echo "BACKUP_RETENTION_DAYS must be a number" >&2; exit 2 ;; esac
DB="${BACKUP_DB:-labtrack}"
SECRET="${BACKUP_DB_PASSWORD_FILE:-/run/secrets/backup_db_password}"
[ -r "$SECRET" ] || { echo "no database password at $SECRET" >&2; exit 2; }

work="$(mktemp -d)"   # /tmp is tmpfs (compose)
psql_pid=""
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
partial="/backups/.$stamp.partial"
cleanup() {
  [ -n "$psql_pid" ] && kill "$psql_pid" 2>/dev/null || true
  rm -rf "$work" "$partial"
}
trap cleanup EXIT INT TERM HUP

export PGHOST="${PGHOST:-postgres}" PGUSER=labtrack_backup
printf '%s:5432:*:labtrack_backup:%s\n' "$PGHOST" "$(cat "$SECRET")" > "$work/pgpass"
export PGPASSFILE="$work/pgpass"
mkdir -p "$partial"
started="$(date -u +%s)"
enc() { age -r "$BACKUP_AGE_RECIPIENT" -o "$1"; }

# --- one snapshot for the dump and the manifest: a session that holds it open ---
mkfifo "$work/sql"
psql -X -q -At --no-password -d "$DB" -o "$work/session.out" < "$work/sql" &
psql_pid=$!
exec 3> "$work/sql"
echo "begin isolation level repeatable read, read only; select pg_export_snapshot();" >&3
i=0
until [ -s "$work/session.out" ]; do
  sleep 0.2; i=$((i + 1))
  [ "$i" -lt 150 ] || { echo "no snapshot from the database" >&2; exit 1; }
done
snapshot="$(head -n 1 "$work/session.out")"

pg_dump -Fc --no-password --snapshot="$snapshot" -d "$DB" | enc "$partial/db.dump.age"

cat >&3 <<'SQL'
select version_num from alembic_version;
select coalesce(json_object_agg(t, n), '{}') from (
  select c.relname as t,
         (xpath('/row/n/text()', query_to_xml(format('select count(*) as n from public.%I', c.relname), false, true, '')))[1]::text::bigint as n
  from pg_class c join pg_namespace s on s.oid = c.relnamespace
  where s.nspname = 'public' and c.relkind = 'r' order by c.relname) x;
select coalesce(json_agg(c.relname order by c.relname), '[]') from pg_class c
  join pg_namespace s on s.oid = c.relnamespace
  where s.nspname = 'public' and c.relkind = 'r' and c.relrowsecurity and c.relforcerowsecurity;
select count(*) from pg_policies where schemaname = 'public';
commit;
SQL
exec 3>&-
wait "$psql_pid"
psql_pid=""
[ "$(wc -l < "$work/session.out")" -eq 5 ] || { echo "manifest queries failed" >&2; exit 1; }
head="$(sed -n 2p "$work/session.out")"
counts="$(sed -n 3p "$work/session.out")"
forced="$(sed -n 4p "$work/session.out")"
policies="$(sed -n 5p "$work/session.out")"

pg_dumpall --globals-only --no-role-passwords --no-password | enc "$partial/globals.sql.age"

# --- document store over S3 (the objects are already sealed by the app) ---
export RCLONE_CONFIG_STORE_TYPE=s3 RCLONE_CONFIG_STORE_PROVIDER=Other \
  RCLONE_CONFIG_STORE_ENDPOINT="${S3_ENDPOINT_URL:?}" \
  RCLONE_CONFIG_STORE_ACCESS_KEY_ID="${S3_ACCESS_KEY:?}" \
  RCLONE_CONFIG_STORE_SECRET_ACCESS_KEY="${S3_SECRET_KEY:?}"
bucket="${S3_BUCKET:-labtrack-documents}"
mkdir -p "$partial/.files"
rclone copy --quiet "store:$bucket" "$partial/.files"
objects="$(find "$partial/.files" -type f | wc -l | tr -d ' ')"
tar -C "$partial/.files" -cf - . | enc "$partial/files.tar.age"
rm -rf "$partial/.files"

jq -n --arg stamp "$stamp" --arg db "$DB" --arg head "$head" --argjson counts "$counts" \
  --argjson forced "$forced" --argjson policies "$policies" --argjson objects "$objects" \
  '{stamp: $stamp, database: $db, alembic_head: $head, row_counts: $counts,
    forced_rls_tables: $forced, policies: $policies, objects: $objects}' \
  > "$partial/manifest.json"
(cd "$partial" && sha256sum db.dump.age globals.sql.age files.tar.age manifest.json > SHA256SUMS)
mv "$partial" "/backups/$stamp"

# --- retention by name: with a daily run no backup is older than RETENTION_DAYS ---
cutoff="$(date -u -d "@$(( $(date -u +%s) - (RETENTION_DAYS - 1) * 86400 ))" +%Y%m%dT%H%M%SZ)"
for d in /backups/20*Z; do
  [ -d "$d" ] || continue
  name="$(basename "$d")"
  # older than the cutoff: sorts first (the names are fixed-width UTC times)
  if [ "$name" != "$cutoff" ] && [ "$(printf '%s\n%s\n' "$name" "$cutoff" | sort | head -n 1)" = "$name" ]; then
    rm -rf "$d"
  fi
done
# a run that died before renaming leaves a hidden partial: gone after a day
find /backups -mindepth 1 -maxdepth 1 -type d -name '.*.partial' -mmin +1440 -exec rm -rf {} +

size="$(du -sh "/backups/$stamp" | cut -f1)"
echo "backup ok: $stamp head=$head objects=$objects size=$size seconds=$(( $(date -u +%s) - started ))"
