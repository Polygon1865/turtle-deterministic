param(
    [string]$Caddy = "C:\Tools\caddy\caddy.exe",
    [string]$Config = "C:\Tools\caddy\Caddyfile",
    [int]$Port = 8080,
    [string]$Log = "",
    [switch]$Supervise
)

# Caddy is the origin for the Cloudflare tunnel: it serves
# site\current on 127.0.0.1:8080. If this process is gone, cloudflared logs
# "dial tcp 127.0.0.1:8080: connectex: ... actively refused it" and the site
# returns 502/1033 even though the tunnel service itself is healthy.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
# cmd.exe keeps the redirect target open, so caddy.log is locked while Caddy
# runs. A second launcher (e.g. a test config on another port) must pass -Log
# with its own file or cmd exits before Caddy even starts.
$log = if ($Log -ne "") { $Log } else { Join-Path $logDir "caddy.log" }
$launchLog = Join-Path $logDir "caddy-launch.log"

function Test-OriginListening {
    $found = netstat -ano -p tcp | Select-String "LISTENING" | Select-String ":${Port}\s"
    return [bool]$found
}

function Write-LaunchLog {
    param([string]$Message)
    $line = "{0} pid={1} {2}" -f (Get-Date -Format "yyyy-MM-ddTHH:mm:sszzz"), $PID, $Message
    # Two launchers can race here (logon + daily pipeline); retry instead of
    # losing the record, then give up silently rather than break the origin.
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

if (-not (Test-Path $Caddy)) {
    Write-Error "caddy not found: $Caddy"
    exit 2
}
if (-not (Test-Path $Config)) {
    Write-Error "caddy config not found: $Config"
    exit 2
}

# Do not start a second instance that would fight for the port; the launcher can
# be invoked more than once (logon + manual + daily pipeline) without breaking
# the running one.
if (Test-OriginListening) {
    Write-LaunchLog "no-op: 127.0.0.1:8080 already listening"
    Write-Output "127.0.0.1:8080 is already listening; nothing to do"
    exit 0
}

Write-LaunchLog ("start (supervise={0})" -f $Supervise.IsPresent)

$exitCode = 0
$attempt = 0
while ($true) {
    $attempt += 1
    if ($attempt -gt 1) { Write-LaunchLog ("restart attempt {0}" -f $attempt) }
    $started = Get-Date
    # Redirect through cmd.exe: PowerShell 5.1 turns every native stderr line
    # into an ErrorRecord, which would spray "NativeCommandError" blocks into
    # the log.
    & cmd.exe /d /c "`"$Caddy`" run --config `"$Config`" >> `"$log`" 2>&1"
    $exitCode = $LASTEXITCODE
    $ran = ((Get-Date) - $started).TotalSeconds
    Write-LaunchLog ("caddy exited code={0} after={1:n0}s" -f $exitCode, $ran)

    if (-not $Supervise) { break }
    if (Test-OriginListening) {
        Write-LaunchLog "another instance took the port; supervisor stops"
        break
    }
    # A crash loop with a broken config should not spin: back off when the
    # process died immediately, stay responsive when it served for a while.
    if ($ran -lt 5) { Start-Sleep -Seconds 30 } else { Start-Sleep -Seconds 5 }
}

exit $exitCode
