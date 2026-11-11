# Run the turtle-daily Cloudflare Tunnel connector in the foreground.
#
# Used by the "turtle-daily-cloudflared" scheduled task (logon trigger) because
# the Windows service "Cloudflared agent" has no usable active connection on
# this machine and restarting it needs an elevated shell.
#
# Logs: %USERPROFILE%\.cloudflared\tunnel.log

$ErrorActionPreference = "Stop"

$cloudflared = "C:\Tools\cloudflared\cloudflared.exe"
$config = Join-Path $env:USERPROFILE ".cloudflared\config.yml"
$log = Join-Path $env:USERPROFILE ".cloudflared\tunnel.log"
$tunnel = "b3e163be-d910-4fe7-aaba-876a66cf12b3"

if (-not (Test-Path $cloudflared)) {
    throw "cloudflared not found: $cloudflared"
}
if (-not (Test-Path $config)) {
    throw "cloudflared config not found: $config"
}

& $cloudflared tunnel --config $config --no-autoupdate run $tunnel *>> $log
