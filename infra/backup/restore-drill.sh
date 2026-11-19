#!/bin/sh
# Restore drill (Phase 8.2; docs/OPS_RUNBOOK.md): prove a backup can be brought back.
#
#   restore-drill.sh [<backup name>]     (default: the newest)
#
# Runs in its own container with NO network and a throwaway Postgres on tmpfs (never the live
# cluster: a tampered dump restored by a superuser there could reach the server's OS). Checks
# the checksums, decrypts with the identity mounted at BACKUP_AGE_IDENTITY_FILE (the private key -
# kept offline, mounted only for a drill or a real restore), creates the roles from the globals,
# restores the database and compares the migration head, every table's row count, the tables
# under FORCE row security, the number of policies and the number of stored objects with the
# manifest. Nothing decrypted touches a disk: the database and temp files live on tmpfs and are
# gone with the container. Prints numbers only.
set -euo pipefail
umask 077

IDENTITY="${BACKUP_AGE_IDENTITY_FILE:-/run/secrets/backup-identity}"
[ -r "$IDENTITY" ] || { echo "no identity at $IDENTITY (mount the private key for the drill)" >&2; exit 2; }

stamp="${1:-$(ls -1 /backups | grep -E '^20[0-9]{6}T[0-9]{6}Z$' | sort | tail -n 1 || true)}"
[ -n "$stamp" ] || { echo "no backup found in /backups" >&2; exit 2; }
case "$stamp" in
  20[0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z) ;;
  *) echo "not a backup name: use the folder name" >&2; exit 2 ;;
esac
dir="/backups/$stamp"
[ -f "$dir/manifest.json" ] || { echo "backup $stamp is incomplete" >&2; exit 2; }

PGDATA="${DRILL_PGDATA:-/var/lib/postgresql/drill/data}"
export PGHOST=/tmp PGUSER=postgres PGOPTIONS="-c client_min_messages=warning"
cleanup() {
  pg_ctl -D "$PGDATA" -m immediate stop >/dev/null 2>&1 || true
  rm -rf "$PGDATA"
}
trap cleanup EXIT INT TERM HUP
started="$(date -u +%s)"

(cd "$dir" && sha256sum -c --quiet SHA256SUMS)
echo "checksums ok"

dec() { age -d -i "$IDENTITY" "$1"; }

initdb -D "$PGDATA" -U postgres --auth=trust --no-instructions -E UTF8   --locale-provider=builtin --builtin-locale=C.UTF-8 > /tmp/initdb.log 2>&1   || { cat /tmp/initdb.log >&2; exit 1; }
pg_ctl -D "$PGDATA" -w -l /tmp/drill.log \
  -o "-c listen_addresses='' -c unix_socket_directories=/tmp" start >/dev/null

# roles (no passwords in the backup: a real restore sets them from the secret store)
dec "$dir/globals.sql.age" | psql -X -q -d postgres >/dev/null 2>&1 || true
for role in labtrack_owner labtrack_app labtrack_admin labtrack_admin_login labtrack_maint \
            labtrack_push labtrack_backup; do
  [ "$(psql -X -At -d postgres -c "select count(*) from pg_roles where rolname = '$role'")" = 1 ] \
    || { echo "globals lack role $role" >&2; exit 1; }
done
echo "roles ok"

psql -X -q -d postgres -v ON_ERROR_STOP=1 -c "create database labtrack owner labtrack_owner"
dec "$dir/db.dump.age" | pg_restore --exit-on-error -d labtrack
db_seconds=$(( $(date -u +%s) - started ))

q() { psql -X -At -d labtrack -c "$1"; }
want_head="$(jq -r .alembic_head "$dir/manifest.json")"
got_head="$(q "select version_num from alembic_version")"
[ "$want_head" = "$got_head" ] || { echo "migration head $got_head, expected $want_head" >&2; exit 1; }

got_counts="$(q "
  select coalesce(json_object_agg(t, n), '{}') from (
    select c.relname as t,
           (xpath('/row/n/text()', query_to_xml(format('select count(*) as n from public.%I', c.relname), false, true, '')))[1]::text::bigint as n
    from pg_class c join pg_namespace s on s.oid = c.relnamespace
    where s.nspname = 'public' and c.relkind = 'r' order by c.relname) x")"
diff="$(jq -rn --argjson a "$(jq .row_counts "$dir/manifest.json")" --argjson b "$got_counts" \
  '[($a + $b) | keys[] as $k | select($a[$k] != $b[$k]) | $k] | join(",")')"
[ -z "$diff" ] || { echo "row counts differ in: $diff" >&2; exit 1; }
tables="$(jq '.row_counts | length' "$dir/manifest.json")"

# the row security came back exactly (a restore without it would expose every row)
got_forced="$(q "select coalesce(json_agg(c.relname order by c.relname), '[]') from pg_class c
  join pg_namespace s on s.oid = c.relnamespace
  where s.nspname = 'public' and c.relkind = 'r' and c.relrowsecurity and c.relforcerowsecurity")"
[ "$(jq -c .forced_rls_tables "$dir/manifest.json")" = "$(echo "$got_forced" | jq -c .)" ] \
  || { echo "tables under FORCE row security differ" >&2; exit 1; }
got_policies="$(q "select count(*) from pg_policies where schemaname = 'public'")"
[ "$(jq .policies "$dir/manifest.json")" = "$got_policies" ] \
  || { echo "policies $got_policies, expected $(jq .policies "$dir/manifest.json")" >&2; exit 1; }
echo "database ok: head=$got_head tables=$tables forced_rls=$(echo "$got_forced" | jq length) policies=$got_policies seconds=$db_seconds"

# the documents: counted from the archive, never unpacked
want_objects="$(jq .objects "$dir/manifest.json")"
got_objects="$(dec "$dir/files.tar.age" | tar -tf - | grep -vc '/$' || true)"
[ "$want_objects" = "$got_objects" ] || { echo "objects $got_objects, expected $want_objects" >&2; exit 1; }
echo "files ok: objects=$got_objects"

echo "restore drill ok: backup=$stamp total_seconds=$(( $(date -u +%s) - started ))"
