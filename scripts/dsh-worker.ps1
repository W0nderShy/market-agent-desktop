$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:DSH_HOME = Join-Path $projectRoot 'runtime/dsh'
$env:DSH_DESKTOP_OPEN_DEVTOOLS = '0'
$env:DSH_MARKET_ROOT = $projectRoot
$env:pnpm_config_public_hoist_pattern = '["react","react-dom","@types/react","@types/react-dom"]'
$presetTarget = Join-Path $env:DSH_HOME '.agent-presets/market-research'
New-Item -ItemType Directory -Force -Path $presetTarget | Out-Null
Copy-Item -LiteralPath (Join-Path $projectRoot 'desktop/presets/market-research/agent.cordis.yml') -Destination $presetTarget -Force
Copy-Item -LiteralPath (Join-Path $projectRoot 'desktop/presets/market-research/preset.yml') -Destination $presetTarget -Force
Set-Location -LiteralPath (Join-Path $projectRoot 'vendor/deepseek-harness')
$nodeExe = Join-Path $env:ProgramFiles 'nodejs/node.exe'
if (!(Test-Path -LiteralPath $nodeExe)) { $nodeExe = (Get-Command node.exe -ErrorAction Stop).Source }
$pnpmEntry = Join-Path $projectRoot 'vendor/deepseek-harness/apps/desktop/node_modules/pnpm/bin/pnpm.cjs'
$env:PATH = (Split-Path -Parent $nodeExe) + ';' + $env:PATH
& $nodeExe $pnpmEntry --dir (Join-Path $projectRoot 'vendor/deepseek-harness/apps/desktop') run start
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
