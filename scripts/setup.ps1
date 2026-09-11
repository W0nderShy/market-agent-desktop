param([switch]$SkipDshBuild)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
function Assert-Exit { if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE)." } }
& git submodule update --init --recursive
Assert-Exit
& (Join-Path $PSScriptRoot 'apply-dsh-patch.ps1')
if (!(Test-Path -LiteralPath '.venv/Scripts/python.exe')) { & python -m venv .venv; Assert-Exit }
& ./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
Assert-Exit
& ./.venv/Scripts/python.exe -m pip install --no-deps -e .
Assert-Exit
$dshRoot = Join-Path $projectRoot 'vendor/deepseek-harness'
Push-Location -LiteralPath $dshRoot
try {
    # Explicit local React links prevent resolving a parent project's React version.
    $env:pnpm_config_public_hoist_pattern = '["react","react-dom","@types/react","@types/react-dom"]'
    $env:CI = 'true'
    & pnpm install --frozen-lockfile
    Assert-Exit
    & node apps/desktop/node_modules/electron/install.js
    Assert-Exit
    if (!$SkipDshBuild) {
        & pnpm run build
        Assert-Exit
        & pnpm run build:desktop
        Assert-Exit
    }
} finally { Pop-Location }
Write-Output 'Setup completed. Run scripts/start.ps1 to open the integrated Desktop.'
