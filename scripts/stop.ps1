$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pidPath = Join-Path $projectRoot 'runtime/service.pid'
if (!(Test-Path -LiteralPath $pidPath)) { Write-Output 'No launcher-owned service PID recorded.'; exit 0 }
$servicePid = [int](Get-Content -LiteralPath $pidPath -Raw).Trim()
$process = Get-CimInstance Win32_Process -Filter "ProcessId = $servicePid"
if ($process) {
    $expectedExe = [IO.Path]::GetFullPath((Join-Path $projectRoot '.venv/Scripts/python.exe'))
    if (!$process.ExecutablePath -or ![string]::Equals($process.ExecutablePath,$expectedExe,[StringComparison]::OrdinalIgnoreCase) -or $process.CommandLine -notmatch 'market_monitor\.cli\s+serve') { throw 'PID does not belong to this project monitor; refusing to stop it.' }
    $tokenPath = Join-Path $projectRoot 'runtime/api-token'
    $tokenValue = (Get-Content -LiteralPath $tokenPath -Raw).Trim()
    $null = Invoke-RestMethod 'http://127.0.0.1:8765/api/shutdown' -Method Post -Headers @{'X-Monitor-Token'=$tokenValue} -TimeoutSec 5
    $stopped = $false
    for ($attempt=0; $attempt -lt 120; $attempt++) {
        if (!(Get-Process -Id $servicePid -ErrorAction SilentlyContinue)) { $stopped=$true; break }
        Start-Sleep -Milliseconds 500
    }
    if (!$stopped) { throw 'Service is still finishing a request; retry stop after it exits. State has not been deleted.' }
}
Remove-Item -LiteralPath $pidPath
Write-Output 'Monitor service stopped. SQLite state remains available for restart. Close desktop windows normally.'
