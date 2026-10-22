param(
    [string]$Date = "",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Extra
)

# Native commands may write progress/risk-free notices to stderr. Keep
# ErrorActionPreference at Continue so PowerShell 5.1 does not turn those
# notices into terminating errors; the exit code is checked explicitly.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

# Task Scheduler may start with a stale environment block. Fall back to the
# persisted user variables so the daily LLM step can see the key without
# storing secrets in this script.
foreach ($name in @("TURTLE_LLM_API_KEY", "TURTLE_LLM_BASE_URL", "TURTLE_LLM_MODEL")) {
    if (-not [Environment]::GetEnvironmentVariable($name, "Process")) {
        $value = [Environment]::GetEnvironmentVariable($name, "User")
        if ($value) {
            Set-Item -Path "Env:$name" -Value $value
        }
    }
}

$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$log = Join-Path $logDir "daily-$stamp.log"

if (-not (Test-Path $python)) {
    Write-Error "Python not found: $python"
    exit 2
}

# The site is only reachable while the Caddy origin is up. Heal it before the
# pipeline publishes a new release under site\current, otherwise a dead origin
# keeps serving 502 long after a successful build.
$originUp = netstat -ano -p tcp |
    Select-String "LISTENING" |
    Select-String ":8080\s"
if (-not $originUp) {
    $launcher = Join-Path $PSScriptRoot "run_caddy.ps1"
    try {
        Start-Process -FilePath "powershell.exe" `
            -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", $launcher, "-Supervise") `
            -WindowStyle Hidden -ErrorAction Stop
        Write-Output "Caddy origin was not listening; started $launcher -Supervise"
    }
    catch {
        Write-Warning "Caddy origin is not listening and could not be started: $($_.Exception.Message)"
    }
}

$pipelineArgs = @()
if ($Date -ne "") {
    $pipelineArgs += @("--date", $Date)
}
if ($Extra) {
    $pipelineArgs += $Extra
}

Push-Location $root
try {
    & $python (Join-Path $root "scripts\daily_pipeline.py") @pipelineArgs 2>&1 |
        Tee-Object -FilePath $log -Append
    $code = $LASTEXITCODE
}
finally {
    Pop-Location
}

if ($code -ne 0) {
    Write-Error "Daily pipeline failed with exit code $code; log: $log"
}
exit $code
