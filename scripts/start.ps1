param([switch]$MonitorOnly, [switch]$WithDsh)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonExe = Join-Path $projectRoot '.venv/Scripts/python.exe'
$electronExe = Join-Path $projectRoot 'vendor/deepseek-harness/apps/desktop/node_modules/electron/dist/electron.exe'
if (!(Test-Path -LiteralPath $pythonExe) -or !(Test-Path -LiteralPath $electronExe)) { throw 'Run scripts/setup.ps1 first.' }
New-Item -ItemType Directory -Force -Path (Join-Path $projectRoot 'runtime') | Out-Null
$startupLock = [IO.File]::Open((Join-Path $projectRoot 'runtime/startup.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
try {
$connected = $false
$tokenPath = Join-Path $projectRoot 'runtime/api-token'
if (Test-Path -LiteralPath $tokenPath) {
    try {
        $tokenValue = (Get-Content -LiteralPath $tokenPath -Raw).Trim()
        $null = Invoke-RestMethod 'http://127.0.0.1:8765/api/status' -Headers @{'X-Monitor-Token'=$tokenValue} -TimeoutSec 2
        $connected = $true
    } catch { }
}
if (!$connected) {
    $service = Start-Process -FilePath $pythonExe -ArgumentList @('-m','market_monitor.cli','serve','--port','8765') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot 'runtime/service.out.log') -RedirectStandardError (Join-Path $projectRoot 'runtime/service.err.log')
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        Start-Sleep -Milliseconds 500
        $service.Refresh()
        if ($service.HasExited) { throw 'Monitor failed to start. Check runtime/service.err.log.' }
        try {
            $tokenValue = (Get-Content -LiteralPath $tokenPath -Raw).Trim()
            $null = Invoke-RestMethod 'http://127.0.0.1:8765/api/status' -Headers @{'X-Monitor-Token'=$tokenValue} -TimeoutSec 1
            $connected = $true
            break
        } catch { }
    }
    if (!$connected) { throw 'Service startup timed out. Check runtime/service.err.log.' }
    $service.Id | Set-Content -LiteralPath (Join-Path $projectRoot 'runtime/service.pid')
}
# Visible Electron window is the requested interactive desktop application.
if ($MonitorOnly) { Start-Process -FilePath $electronExe -ArgumentList ('"' + (Join-Path $projectRoot 'desktop') + '"') -WorkingDirectory $projectRoot }
else { & (Join-Path $PSScriptRoot 'start-dsh.ps1') }
Write-Output 'Desktop launch requested. Backend continues until scripts/stop.ps1 is run.'
} finally { $startupLock.Dispose() }
