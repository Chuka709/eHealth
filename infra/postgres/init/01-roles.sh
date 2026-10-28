#!/bin/sh
# Runs once on an empty data directory. Creates the least-privilege roles (docs/03_DATA_MODEL.md)
# and the dev + test databases. Grants on tables/functions are made by Alembic migrations.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v owner_pw="$LABTRACK_OWNER_PASSWORD" \
  -v app_pw="$LABTRACK_APP_PASSWORD" \
  -v admin_pw="$LABTRACK_ADMIN_PASSWORD"   -v admin_login_pw="$LABTRACK_ADMIN_LOGIN_PASSWORD" \
  -v maint_pw="$LABTRACK_MAINT_PASSWORD" <<'SQL'
create role labtrack_owner login password :'owner_pw';
create role labtrack_app   login password :'app_pw'   nobypassrls;
create role labtrack_admin login password :'admin_pw' nobypassrls;
-- admin sign-in only: reads admin password hashes, creates admin sessions (migration 0006)
create role labtrack_admin_login login password :'admin_login_pw' nobypassrls;
create role labtrack_maint login password :'maint_pw' nobypassrls;

create database labtrack      owner labtrack_owner;
create database labtrack_test owner labtrack_owner;

revoke all on database labtrack      from public;
revoke all on database labtrack_test from public;
grant connect on database labtrack      to labtrack_app, labtrack_admin, labtrack_admin_login, labtrack_maint;
grant connect on database labtrack_test to labtrack_app, labtrack_admin, labtrack_admin_login, labtrack_maint;
SQL
