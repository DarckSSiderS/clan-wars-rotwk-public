#!/usr/bin/env bash
set -Eeuo pipefail

: "${BACKUP_ARCHIVE:?BACKUP_ARCHIVE is required}"
: "${PRODUCTION_DATABASE_URL:?PRODUCTION_DATABASE_URL is required}"
: "${RESTORE_DATABASE_URL:?RESTORE_DATABASE_URL is required}"

if [[ "$RESTORE_DATABASE_URL" == "$PRODUCTION_DATABASE_URL" ]]; then
  echo "RESTORE_DATABASE_URL must differ from PRODUCTION_DATABASE_URL" >&2
  exit 2
fi
if [[ ! -f "$BACKUP_ARCHIVE" ]]; then
  echo "Backup archive not found" >&2
  exit 2
fi

work_dir="$(mktemp -d)"
cleanup() {
  rm -rf -- "$work_dir"
}
trap cleanup EXIT

production_identity="$(psql "$PRODUCTION_DATABASE_URL" -v ON_ERROR_STOP=1 -Atqc \
  "SELECT current_database() || '@' || COALESCE(inet_server_addr()::text, 'local') || ':' || inet_server_port()")"
restore_identity="$(psql "$RESTORE_DATABASE_URL" -v ON_ERROR_STOP=1 -Atqc \
  "SELECT current_database() || '@' || COALESCE(inet_server_addr()::text, 'local') || ':' || inet_server_port()")"
if [[ "$restore_identity" == "$production_identity" ]]; then
  echo "RESTORE_DATABASE_URL must differ from PRODUCTION_DATABASE_URL" >&2
  exit 2
fi

tar -xzf "$BACKUP_ARCHIVE" -C "$work_dir"
bundle_dir="$(find "$work_dir" -mindepth 1 -maxdepth 1 -type d -name 'clanwar-*' -print -quit)"
if [[ -z "$bundle_dir" || ! -f "${bundle_dir}/manifest.sha256" ]]; then
  echo "Backup manifest not found" >&2
  exit 3
fi

(
  cd "$bundle_dir"
  sha256sum --check manifest.sha256
)
for archive in "$bundle_dir"/*.tar.gz; do
  [[ -e "$archive" ]] || continue
  tar -tzf "$archive" >/dev/null
done

pg_restore \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  --exit-on-error \
  --dbname="$RESTORE_DATABASE_URL" \
  "${bundle_dir}/database.dump"
psql "$RESTORE_DATABASE_URL" -v ON_ERROR_STOP=1 \
  -c 'SELECT COUNT(*) AS alembic_rows FROM alembic_version;'

printf 'Restore smoke passed for the isolated target database.\n'
