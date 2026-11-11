#!/bin/sh
# labtrack_push: the push worker's role (migration 0028, Phase 2.11b) - delivery functions and
# push_receipts only. Idempotent: runs on an empty data directory after 01-roles.sh, and on an
# existing one through `just db-roles` (then `just migrate`). The password is read from the
# environment inside psql (never on the command line) and kept out of the server log.
set -eu

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER:-postgres}" --dbname postgres <<'SQL'
set log_statement = 'none';
set log_min_error_statement = 'panic';
\getenv push_pw LABTRACK_PUSH_PASSWORD
select format('create role labtrack_push login password %L', :'push_pw')
  where not exists (select 1 from pg_roles where rolname = 'labtrack_push') \gexec
select format('alter role labtrack_push login nosuperuser nocreatedb nocreaterole noreplication'
              ' nobypassrls inherit connection limit 10 password %L', :'push_pw') \gexec
select format('grant connect on database %I to labtrack_push', datname)
  from pg_database where datname in ('labtrack', 'labtrack_test') \gexec
SQL
