#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/home/clanwar/apps/clanwar"
CURRENT="$APP_ROOT/current"
SHARED="$APP_ROOT/shared"
ENV_FILE="$SHARED/.env"
PASSWORD_FILE="$SHARED/.postgres-password"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
ENV_BACKUP="$SHARED/.env.pre-postgres-$STAMP"
SQLITE_BACKUP="$SHARED/clanwar_local.db.pre-postgres-$STAMP"

DB_PASSWORD="$(<"$PASSWORD_FILE")"
POSTGRES_URL="postgresql://clanwar_user:${DB_PASSWORD}@127.0.0.1:5432/clanwar"

rollback() {
  echo "Cutover failed; restoring the previous environment."
  sudo -n systemctl stop clanwar-worker.service >/dev/null 2>&1 || true
  if [[ -f "$ENV_BACKUP" ]]; then
    cp -a "$ENV_BACKUP" "$ENV_FILE"
  fi
  sudo -n systemctl restart clanwar.service || true
}
trap rollback ERR

cp -a "$ENV_FILE" "$ENV_BACKUP"
cp -a "$SHARED/clanwar_local.db" "$SQLITE_BACKUP"
sudo -n systemctl stop clanwar.service
sudo -n systemctl stop clanwar-worker.service >/dev/null 2>&1 || true

cd "$CURRENT"
export DATABASE_URL="$POSTGRES_URL"
.venv/bin/alembic upgrade head
.venv/bin/python deploy/migrate_sqlite_to_postgres.py \
  --sqlite-url "sqlite:///$SHARED/clanwar_local.db" \
  --postgres-url "$POSTGRES_URL"
.venv/bin/python -m deploy.verify_database

if grep -q '^DATABASE_URL=' "$ENV_FILE"; then
  sed -i "s|^DATABASE_URL=.*|DATABASE_URL=$POSTGRES_URL|" "$ENV_FILE"
else
  printf '\nDATABASE_URL=%s\n' "$POSTGRES_URL" >> "$ENV_FILE"
fi
chmod 600 "$ENV_FILE"

sudo -n install -m 0644 \
  "$CURRENT/deploy/clanwar.service" \
  /etc/systemd/system/clanwar.service
sudo -n install -m 0644 \
  "$CURRENT/deploy/clanwar-worker.service" \
  /etc/systemd/system/clanwar-worker.service
sudo -n systemctl daemon-reload

.venv/bin/python -m app.bootstrap
sudo -n systemctl enable --now clanwar.service clanwar-worker.service
sleep 5
systemctl is-active clanwar.service
systemctl is-active clanwar-worker.service

trap - ERR
echo "PostgreSQL cutover completed."
