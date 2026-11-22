param(
    [string]$HostName = "192.0.2.10",
    [string]$Domain = "bfmecw.online",
    [string]$SshUser = "clanwar",
    [string]$IdentityFile = (Join-Path $env:USERPROFILE ".ssh\clanwar_deploy_ed25519"),
    [ValidateRange(1, 120)]
    [int]$RecentLogMinutes = 10
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $IdentityFile -PathType Leaf)) {
    throw "SSH identity file not found: $IdentityFile"
}

$remoteScript = @'
set -euo pipefail

current="$(readlink -f /home/clanwar/apps/clanwar/current)"
case "$current" in
  /home/clanwar/apps/clanwar/releases/*) ;;
  *) echo "Unexpected current release: $current" >&2; exit 1 ;;
esac

test "$(systemctl is-active clanwar)" = "active"
test "$(systemctl is-active clanwar-worker)" = "active"
curl -fsS http://127.0.0.1:8000/health/live >/dev/null
curl -fsS http://127.0.0.1:8000/health/ready >/dev/null

cd "$current"
revision="$(.venv/bin/python -m alembic current 2>/dev/null | head -n 1)"
case "$revision" in
  *"(head)"*) ;;
  *) echo "Alembic is not at head: $revision" >&2; exit 1 ;;
esac

error_count="$(
  journalctl -u clanwar -u clanwar-worker \
    --since "__RECENT_LOG_MINUTES__ minutes ago" --no-pager 2>/dev/null \
    | grep -Eci 'traceback|(^|[^a-z])error([^a-z]|$)|critical|exception' \
    || true
)"
test "$error_count" = "0"

guest_status="$(
  curl -sS -o /dev/null -w '%{http_code}' \
    http://127.0.0.1:8000/api/v1/auth/session
)"
test "$guest_status" = "401"

printf 'CURRENT=%s\n' "$current"
printf 'REVISION=%s\n' "$revision"
printf 'RECENT_ERROR_LINES=%s\n' "$error_count"
printf 'GUEST_SESSION_LOCAL_STATUS=%s\n' "$guest_status"
'@
$remoteScript = $remoteScript.Replace(
    "__RECENT_LOG_MINUTES__",
    $RecentLogMinutes.ToString()
).Replace("`r", "")

$remoteOutput = $remoteScript | & ssh `
    -o BatchMode=yes `
    -o IdentitiesOnly=yes `
    -i $IdentityFile `
    "$SshUser@$HostName" `
    bash -s
if ($LASTEXITCODE -ne 0) {
    throw "Remote post-deploy smoke failed."
}
$remoteOutput | Write-Output

$baseUrl = "https://$Domain"
$ready = Invoke-RestMethod -Uri "$baseUrl/health/ready" -TimeoutSec 20
if ($ready.status -ne "ready") {
    throw "Public readiness status is not ready."
}
foreach ($component in @("database", "campaign_rules", "worker", "redis")) {
    if ($ready.components.$component -ne "up") {
        throw "Public readiness component is down: $component"
    }
}

$homepageResponse = Invoke-WebRequest -Uri "$baseUrl/" -UseBasicParsing -TimeoutSec 20
if ($homepageResponse.StatusCode -ne 200) {
    throw "Public homepage returned HTTP $($homepageResponse.StatusCode)."
}
if (-not $homepageResponse.Headers["Strict-Transport-Security"]) {
    throw "Public homepage is missing Strict-Transport-Security."
}

$guestStatus = & curl.exe `
    --connect-timeout 10 `
    --max-time 20 `
    -sS `
    -o NUL `
    -w "%{http_code}" `
    "$baseUrl/api/v1/auth/session"
if ($LASTEXITCODE -ne 0 -or $guestStatus -ne "401") {
    throw "Public guest session boundary returned HTTP $guestStatus instead of 401."
}

Write-Output "READY_PUBLIC=$($ready.status)"
Write-Output "HOME_PUBLIC_STATUS=$($homepageResponse.StatusCode)"
Write-Output "GUEST_SESSION_PUBLIC_STATUS=$guestStatus"
Write-Output "POST_DEPLOY_SMOKE_OK"
