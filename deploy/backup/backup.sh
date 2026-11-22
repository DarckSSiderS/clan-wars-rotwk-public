#!/usr/bin/env bash
set -Eeuo pipefail

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${BACKUP_DESTINATION:?BACKUP_DESTINATION is required}"

RETENTION_DAYS="${RETENTION_DAYS:-14}"
UPLOAD_DIR="${UPLOAD_DIR:-/home/clanwar/apps/clanwar/current/frontend/public/images}"
REPLAY_STORAGE_DIR="${REPLAY_STORAGE_DIR:-/home/clanwar/apps/clanwar/shared/replays}"
MAP_PREVIEW_STORAGE_DIR="${MAP_PREVIEW_STORAGE_DIR:-/home/clanwar/apps/clanwar/shared/map_previews}"

mkdir -p -- "$BACKUP_DESTINATION"
destination="$(readlink -f -- "$BACKUP_DESTINATION")"
if [[ -z "$destination" || "$destination" == "/" ]]; then
  echo "BACKUP_DESTINATION must resolve to a dedicated directory" >&2
  exit 2
fi
if ! [[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] || (( RETENTION_DAYS < 1 )); then
  echo "RETENTION_DAYS must be a positive integer" >&2
  exit 2
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_name="clanwar-${timestamp}"
work_dir="$(mktemp -d "${destination}/.clanwar-backup.XXXXXX")"
bundle_dir="${work_dir}/${backup_name}"
cleanup() {
  rm -rf -- "$work_dir"
}
trap cleanup EXIT
mkdir -p -- "$bundle_dir"

pg_dump "$DATABASE_URL" \
  --format=custom \
  --no-owner \
  --no-privileges \
  --file="${bundle_dir}/database.dump"

archive_directory() {
  local source_path="$1"
  local archive_name="$2"
  if [[ -d "$source_path" ]]; then
    tar -czf "${bundle_dir}/${archive_name}.tar.gz" \
      -C "$(dirname -- "$source_path")" \
      "$(basename -- "$source_path")"
  else
    printf 'Directory was absent during backup: %s\n' "$source_path" \
      > "${bundle_dir}/${archive_name}.missing.txt"
  fi
}

archive_directory "$UPLOAD_DIR" "uploads"
archive_directory "$REPLAY_STORAGE_DIR" "replays"
archive_directory "$MAP_PREVIEW_STORAGE_DIR" "map-previews"

(
  cd "$bundle_dir"
  find . -maxdepth 1 -type f ! -name manifest.sha256 -print0 \
    | sort -z \
    | xargs -0 sha256sum > manifest.sha256
)

partial_archive="${destination}/.${backup_name}.tar.gz.partial"
final_archive="${destination}/${backup_name}.tar.gz"
tar -czf "$partial_archive" -C "$work_dir" "$backup_name"
mv -- "$partial_archive" "$final_archive"
sha256sum "$final_archive" > "${final_archive}.sha256.partial"
mv -- "${final_archive}.sha256.partial" "${final_archive}.sha256"

find "$destination" -mindepth 1 -maxdepth 1 -type f \
  \( -name 'clanwar-*.tar.gz' -o -name 'clanwar-*.tar.gz.sha256' \) \
  -mtime "+${RETENTION_DAYS}" -delete

printf 'Backup created: %s\n' "$final_archive"
