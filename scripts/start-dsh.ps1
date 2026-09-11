$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:DSH_HOME = Join-Path $projectRoot 'runtime/dsh'
$env:DSH_DESKTOP_OPEN_DEVTOOLS = '0'
$env:DSH_MARKET_ROOT = $projectRoot
$dshRoot = Join-Path $projectRoot 'vendor/deepseek-harness'
$commandFile = Join-Path $projectRoot 'scripts/dsh-worker.ps1'
New-Item -ItemType Directory -Force -Path (Join-Path $projectRoot 'runtime') | Out-Null
$worker = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-File',('"'+$commandFile+'"')) -WorkingDirectory $dshRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot 'runtime/dsh.out.log') -RedirectStandardError (Join-Path $projectRoot 'runtime/dsh.err.log')
$worker.Id | Set-Content -LiteralPath (Join-Path $projectRoot 'runtime/dsh-worker.pid')
Write-Output 'Starting source-built dsh Desktop. Startup diagnostics: runtime/dsh.err.log (private; do not upload raw logs).'
