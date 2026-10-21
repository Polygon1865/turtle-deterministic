param(
    [string]$Caddy = "C:\Tools\caddy\caddy.exe",
    [string]$Config = "C:\Tools\caddy\Caddyfile"
)

# Caddy is the origin for the Cloudflare tunnel: it serves
# site\current on 127.0.0.1:8080. If this process is gone, cloudflared logs
# "dial tcp 127.0.0.1:8080: connectex: ... actively refused it" and the site
# returns 502/1033 even though the tunnel service itself is healthy.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "caddy.log"

if (-not (Test-Path $Caddy)) {
    Write-Error "caddy not found: $Caddy"
    exit 2
}
if (-not (Test-Path $Config)) {
    Write-Error "caddy config not found: $Config"
    exit 2
}

# Do not start a second instance that would fight for the port; the task can
# be started more than once (logon + manual) without breaking the running one.
$inUse = netstat -ano -p tcp |
    Select-String "LISTENING" |
    Select-String ":8080\s"
if ($inUse) {
    Write-Output "127.0.0.1:8080 is already listening; nothing to do"
    exit 0
}

# Redirect through cmd.exe: PowerShell 5.1 turns every native stderr line into
# an ErrorRecord, which would spray "NativeCommandError" blocks into the log.
& cmd.exe /d /c "`"$Caddy`" run --config `"$Config`" >> `"$log`" 2>&1"
exit $LASTEXITCODE
