"""Windows-first environment setup."""

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
$root = Get-Location

Write-Host "=== Turtle Framework setup ==="
Write-Host "Project root: $root"

$venv = Join-Path $root ".venv"
$venvPy = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $venvPy)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        Write-Host "[1/4] creating venv with py -3"
        & py -3 -m venv $venv
    } else {
        Write-Host "[1/4] creating venv with python"
        & python -m venv $venv
    }
} else {
    Write-Host "[1/4] venv already exists"
}

if (-not (Test-Path $venvPy)) {
    throw "venv creation failed: $venvPy not found"
}

Write-Host "[2/4] installing package (editable) and dev/pdf/hk dependencies"
& $venvPy -m pip install --upgrade pip --quiet
& $venvPy -m pip install -e ".[dev,pdf,hk]" --quiet

Write-Host "[3/4] checking Tushare token"
$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
    Write-Host "  found .env"
} elseif ($env:TUSHARE_TOKEN) {
    Write-Host "  TUSHARE_TOKEN is set in the environment"
} else {
    Write-Warning "  TUSHARE_TOKEN is not set. Copy .env.sample to .env and fill it in."
}

New-Item -ItemType Directory -Force (Join-Path $root ".runs") | Out-Null

Write-Host "[4/4] running tests"
& $venvPy -m pytest -q

Write-Host ""
Write-Host "Done. Try:"
Write-Host "  .\.venv\Scripts\python.exe -m turtlefw.cli analyze 600887 --demo"
