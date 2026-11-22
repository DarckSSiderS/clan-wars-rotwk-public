param(
    [Parameter(Mandatory = $true)]
    [string]$ReleaseName
)

$ErrorActionPreference = "Stop"
$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$archivePath = Join-Path $PSScriptRoot "$ReleaseName.tar.gz"

if (Test-Path -LiteralPath $archivePath) {
    Remove-Item -LiteralPath $archivePath -Force
}

$excludeArguments = @(
    "--exclude=.git",
    "--exclude=.worktrees",
    "--exclude=worktrees",
    "--exclude=work",
    "--exclude=.env*",
    "--exclude=*/.env*",
    "--exclude=.venv",
    "--exclude=venv",
    "--exclude=frontend/node_modules",
    "--exclude=frontend/playwright-report",
    "--exclude=frontend/test-results",
    "--exclude=deploy/*.tar.gz",
    "--exclude=scripts/bfmeladder-com-api-replays.json",
    "--exclude=__pycache__",
    "--exclude=*.pyc",
    "--exclude=.pytest_cache",
    "--exclude=.test-tmp",
    "--exclude=.tmp",
    "--exclude=*.db",
    "--exclude=*.log",
    "--exclude=*.sql",
    "--exclude=map_previews",
    "--exclude=replays"
)

Push-Location $projectRoot
try {
    & tar -czf $archivePath @excludeArguments .
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the release archive."
    }

    $forbiddenEntries = @(
        & tar -tf $archivePath |
            Where-Object { $_ -match '(^|/)\.env($|\.)' }
    )
    if ($forbiddenEntries.Count -gt 0) {
        Remove-Item -LiteralPath $archivePath -Force
        throw "Archive rejected: an environment file was found."
    }
}
finally {
    Pop-Location
}

Get-ChildItem -LiteralPath $PSScriptRoot -Filter "*.tar.gz" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 2 |
    Remove-Item -Force

$archive = Get-Item -LiteralPath $archivePath
Write-Output "Ready: $($archive.FullName) ($($archive.Length) bytes), no .env files."
