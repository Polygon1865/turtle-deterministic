param(
    [string]$Cloudflared = "C:\Tools\cloudflared\cloudflared.exe",
    [string]$Config = "",
    [string]$Log = "",
    [switch]$Supervise,
    [switch]$Force
)

# The tunnel is the other half of the site: cloudflared connects to the Cloudflare
# edge and forwards daily.polygon1865.com to Caddy on 127.0.0.1:8080. When this
# process is gone, Access login succeeds and the browser then gets Error 1033.
#
# The Windows service (sc qc Cloudflared) runs the bare exe under LocalSystem, so
# it reads C:\Windows\System32\config\systemprofile\.cloudflared\config.yml, not
# the user's config. With only a user config it starts, finds nothing, and exits.
# This launcher passes the user config explicitly and is meant to run at logon
# from scripts\startup\turtle-tunnel.vbs.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
if ($Config -eq "") { $Config = Join-Path $env:USERPROFILE ".cloudflared\config.yml" }
# cloudflared appends JSON lines here; cmd.exe redirection keeps the file in the
# process's own encoding (PowerShell Tee-Object would write UTF-16 and make the
# log unreadable to anything that expects UTF-8).
if ($Log -eq "") { $Log = Join-Path $logDir "cloudflared.log" }
$launchLog = Join-Path $logDir "tunnel-launch.log"

function Write-LaunchLog {
    param([string]$Message)
    $line = "{0} pid={1} {2}" -f (Get-Date -Format "yyyy-MM-ddTHH:mm:sszzz"), $PID, $Message
    for ($i = 0; $i -lt 3; $i++) {
        try {
            Add-Content -LiteralPath $launchLog -Value $line -Encoding UTF8 -ErrorAction Stop
            return
        }
        catch {
            Start-Sleep -Milliseconds 200
        }
    }
}

if (-not (Test-Path $Cloudflared)) {
    Write-Error "cloudflared not found: $Cloudflared"
    exit 2
}
if (-not (Test-Path $Config)) {
    Write-Error "cloudflared config not found: $Config"
    exit 2
}

# The launcher is invoked from the logon item and can also be run by hand; never
# start a second connector just because someone double-clicked again.
#
# Only processes that have been up for a while count: the broken service starts
# a bare cloudflared that dies within a second, and a check that catches that
# short-lived process would refuse to start the real connector. -Force skips the
# check entirely for a service instance that is alive but not connected (the SCM
# can keep reporting RUNNING with a PID that owns no sockets at all).
$running = @()
if (-not $Force) {
    $running = @(Get-Process -Name "cloudflared" -ErrorAction SilentlyContinue | Where-Object {
        try { ((Get-Date) - $_.StartTime).TotalSeconds -ge 15 } catch { $false }
    })
}
if ($running.Count -gt 0) {
    Write-LaunchLog ("no-op: cloudflared already running (pid {0})" -f $running[0].Id)
    Write-Output "cloudflared is already running (pid $($running[0].Id)); nothing to do"
    exit 0
}

Write-LaunchLog ("start (supervise={0})" -f $Supervise.IsPresent)

$exitCode = 0
$attempt = 0
while ($true) {
    $attempt += 1
    if ($attempt -gt 1) { Write-LaunchLog ("restart attempt {0}" -f $attempt) }
    $started = Get-Date
    & cmd.exe /d /c "`"$Cloudflared`" --no-autoupdate --config `"$Config`" tunnel run >> `"$Log`" 2>&1"
    $exitCode = $LASTEXITCODE
    $ran = ((Get-Date) - $started).TotalSeconds
    Write-LaunchLog ("cloudflared exited code={0} after={1:n0}s" -f $exitCode, $ran)

    if (-not $Supervise) { break }
    # Edge connections drop when the network sleeps; reconnect quickly, but do
    # not spin if the binary dies instantly (bad config, revoked credentials).
    if ($ran -lt 10) { Start-Sleep -Seconds 30 } else { Start-Sleep -Seconds 10 }
}

exit $exitCode
