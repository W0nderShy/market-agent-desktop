$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:DSH_HOME = Join-Path $projectRoot 'runtime/dsh'
$env:DSH_DESKTOP_OPEN_DEVTOOLS = '0'
$env:DSH_MARKET_ROOT = $projectRoot
$env:pnpm_config_public_hoist_pattern = '["react","react-dom","@types/react","@types/react-dom"]'
Set-Location -LiteralPath (Join-Path $projectRoot 'vendor/deepseek-harness')
& pnpm run start:desktop
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
