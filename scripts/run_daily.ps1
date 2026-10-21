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
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$log = Join-Path $logDir "daily-$stamp.log"

if (-not (Test-Path $python)) {
    Write-Error "Python not found: $python"
    exit 2
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
