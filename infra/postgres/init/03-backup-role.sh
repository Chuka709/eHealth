#!/bin/sh
# labtrack_backup: the backup job's role (Phase 8.2; docs/OPS_RUNBOOK.md) - reads everything
# (pg_read_all_data + BYPASSRLS, which pg_dump needs past FORCE row security), writes nothing,
# not a superuser. Idempotent: runs on an empty data directory after 02-push-role.sh, and on an
# existing one through `just db-roles`. The password is read from the environment inside psql
# (never on the command line) and kept out of the server log.
set -eu

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER:-postgres}" --dbname postgres <<'SQL'
set log_statement = 'none';
set log_min_error_statement = 'panic';
\getenv backup_pw LABTRACK_BACKUP_PASSWORD
select format('create role labtrack_backup login password %L', :'backup_pw')
  where not exists (select 1 from pg_roles where rolname = 'labtrack_backup') \gexec
select format('alter role labtrack_backup login nosuperuser nocreatedb nocreaterole noreplication'
              ' bypassrls inherit connection limit 3 password %L', :'backup_pw') \gexec
grant pg_read_all_data to labtrack_backup;
select format('grant connect on database %I to labtrack_backup', datname)
  from pg_database where datname = 'labtrack' \gexec
SQL
