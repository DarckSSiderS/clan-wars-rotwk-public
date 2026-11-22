#!/usr/bin/env bash
set -euo pipefail

release_name="${1:?Usage: release-existing-server.sh RELEASE_NAME ARCHIVE_PATH}"
archive_path="${2:?Usage: release-existing-server.sh RELEASE_NAME ARCHIVE_PATH}"
app_root="/home/clanwar/apps/clanwar"
release="$app_root/releases/$release_name"
current="$app_root/current"
shared="$app_root/shared"
previous="$(readlink -f "$current")"
replay_storage="$shared/replays"
map_preview_storage="$shared/map_previews"
database_backup="${DATABASE_BACKUP_PATH:-}"
migration_attempted=0
services_stopped=0

rollback_failed_release() {
  exit_code=$?
  trap - ERR
  if [[ "$migration_attempted" -eq 1 ]]; then
    sudo systemctl stop clanwar clanwar-worker || true
    echo "Schema migration was attempted; automatic database/code rollback is unsafe." >&2
    echo "Services remain stopped. Inspect the release and restore only by an explicit recovery procedure." >&2
    echo "Pre-release backup: $database_backup" >&2
  else
    ln -sfn "$previous" "$current"
    if [[ "$services_stopped" -eq 1 ]]; then
      sudo systemctl restart clanwar clanwar-worker || true
    fi
  fi
  exit "$exit_code"
}

trap rollback_failed_release ERR

if [[ -e "$release" ]]; then
  echo "Release already exists: $release" >&2
  exit 1
fi
if [[ ! -f "$archive_path" ]]; then
  echo "Archive does not exist: $archive_path" >&2
  exit 1
fi
if [[ ! -f "$database_backup" ]] || [[ ! -s "$database_backup" ]]; then
  echo "Set DATABASE_BACKUP_PATH to a nonempty, verified pre-release database backup." >&2
  exit 1
fi

mkdir -p "$release"
mkdir -p "$replay_storage"
mkdir -p "$map_preview_storage"
tar -xzf "$archive_path" -C "$release"
"$previous/.venv/bin/python" -m venv "$release/.venv"

# Apply pinned dependency changes inside the release-specific virtualenv.
"$release/.venv/bin/python" -m pip install \
  --disable-pip-version-check \
  --quiet \
  --requirement "$release/requirements.txt"
"$release/.venv/bin/python" -m pip_audit --progress-spinner off

ln -s "$shared/.env" "$release/.env"
ln -s "$map_preview_storage" "$release/map_previews"

cd "$release"
# A failed migration can leave a partially changed schema. Never run the old
# application against that schema, even when upgrade did not return success.
services_stopped=1
sudo systemctl stop clanwar clanwar-worker
migration_attempted=1
"$release/.venv/bin/python" -m alembic upgrade head
if [[ "${SKIP_TESTS:-0}" == "1" ]]; then
  echo "Skipping tests for this deployment"
else
  # Release tests must not publish fixture events into the live Redis channel.
  ENVIRONMENT=test REDIS_URL="" "$release/.venv/bin/python" -m pytest -q
fi
"$release/.venv/bin/python" -m app.bootstrap

# Optional release-specific, read-only data verification before switching traffic.
if [[ -n "${RELEASE_VERIFY_SCRIPT:-}" ]]; then
  "$release/.venv/bin/python" "$RELEASE_VERIFY_SCRIPT"
fi

ln -sfn "$release" "$current"
sudo systemctl restart clanwar clanwar-worker

healthy=0
for _ in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:8000/health/ready >/dev/null; then
    healthy=1
    break
  fi
  sleep 1
done

if [[ "$healthy" -ne 1 ]]; then
  echo "Health check failed" >&2
  false
fi

sudo systemctl is-active --quiet clanwar
sudo systemctl is-active --quiet clanwar-worker
trap - ERR

for old_release in "$app_root/releases"/*; do
  [[ -d "$old_release" ]] || continue
  old_release_resolved="$(readlink -f "$old_release")"
  if [[ "$old_release_resolved" != "$release" && "$old_release_resolved" != "$previous" ]]; then
    rm -rf -- "$old_release"
  fi
done
rm -f -- "$archive_path"
trap - ERR

echo "Deployment complete: $release"
