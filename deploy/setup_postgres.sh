#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/home/clanwar/apps/clanwar"
PASSWORD_FILE="$APP_ROOT/shared/.postgres-password"
DB_NAME="clanwar"
DB_USER="clanwar_user"

if [[ ! -f "$PASSWORD_FILE" ]]; then
  umask 077
  openssl rand -hex 24 > "$PASSWORD_FILE"
fi

DB_PASSWORD="$(<"$PASSWORD_FILE")"

if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname = '$DB_USER'" | grep -q 1; then
  printf "CREATE ROLE %s LOGIN PASSWORD '%s';\n" "$DB_USER" "$DB_PASSWORD" \
    | sudo -u postgres psql
else
  printf "ALTER ROLE %s WITH LOGIN PASSWORD '%s';\n" "$DB_USER" "$DB_PASSWORD" \
    | sudo -u postgres psql
fi

if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1; then
  sudo -u postgres createdb --owner="$DB_USER" "$DB_NAME"
fi

sudo -u postgres psql -d "$DB_NAME" -c "GRANT ALL ON SCHEMA public TO $DB_USER" >/dev/null
echo "PostgreSQL database and role are ready."
