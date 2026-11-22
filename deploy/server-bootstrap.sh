#!/usr/bin/env bash
set -euo pipefail

release="${1:?Usage: server-bootstrap.sh RELEASE_DIRECTORY}"
app_root="/home/clanwar/apps/clanwar"
shared="$app_root/shared"

if [[ ! -d "$release" ]]; then
  echo "Release directory does not exist: $release" >&2
  exit 1
fi

mkdir -p "$shared/images"
mkdir -p "$shared/replays"

if [[ ! -f "$shared/clanwar_local.db" ]]; then
  cp "$release/clanwar_local.db" "$shared/clanwar_local.db"
fi

if [[ -d "$release/frontend/public/images" ]]; then
  cp -an "$release/frontend/public/images/." "$shared/images/"
fi

if [[ ! -f "$shared/.env" ]]; then
  secret=$("$release/.venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(48))')
  cat > "$shared/.env" <<EOF
APP_NAME=ClanWar API
APP_VERSION=1.0.0
ENVIRONMENT=production
DEBUG=False
DATABASE_URL=sqlite:///./clanwar_local.db
SECRET_KEY=$secret
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480
CORS_ORIGINS=["http://89.169.183.66"]
UPLOAD_DIR=$shared/images
MAX_FILE_SIZE=10485760
ALLOWED_IMAGE_TYPES=["image/jpeg", "image/png", "image/gif", "image/webp"]
SCHEDULER_UPDATE_INTERVAL=600
EOF
  chmod 600 "$shared/.env"
fi

ln -sfn "$shared/.env" "$release/.env"
ln -sfn "$shared/clanwar_local.db" "$release/clanwar_local.db"
ln -sfn "$release" "$app_root/current"

sudo tee /etc/systemd/system/clanwar.service >/dev/null <<'EOF'
[Unit]
Description=Clan Wars ROTWK FastAPI application
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=darcks
Group=darcks
WorkingDirectory=/home/clanwar/apps/clanwar/current
EnvironmentFile=/home/clanwar/apps/clanwar/shared/.env
ExecStart=/home/clanwar/apps/clanwar/current/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
Restart=always
RestartSec=5
TimeoutStopSec=30
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/nginx/sites-available/clanwar >/dev/null <<'EOF'
log_format clanwar_sanitized '$remote_addr - $remote_user [$time_local] '
    '"$request_method $uri $server_protocol" $status $body_bytes_sent '
    '"$http_user_agent"';

server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name 89.169.183.66 _;
    access_log /var/log/nginx/access.log clanwar_sanitized;

    client_max_body_size 12m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }
}
EOF

sudo ln -sfn /etc/nginx/sites-available/clanwar /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable --now clanwar
sudo systemctl restart nginx

echo "Deployment configured: $release"
