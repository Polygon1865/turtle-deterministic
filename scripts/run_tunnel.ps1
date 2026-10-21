param()

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$cloudflared = "C:\Tools\cloudflared\cloudflared.exe"
$config = Join-Path $env:USERPROFILE ".cloudflared\config.yml"
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "cloudflared.log"

if (-not (Test-Path $cloudflared)) {
    Write-Error "cloudflared not found: $cloudflared"
    exit 2
}
if (-not (Test-Path $config)) {
    Write-Error "cloudflared config not found: $config"
    exit 2
}

# The Windows service installed without arguments looks for config under the
# SYSTEM profile and therefore never connects. This logon task uses the user
# config explicitly.
& $cloudflared tunnel --config $config --logfile $log run turtle-daily
exit $LASTEXITCODE
