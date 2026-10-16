param([switch]$CopyToParent)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
if (!(Test-Path -LiteralPath $compiler)) { throw 'The Windows .NET Framework C# compiler is required.' }
& $compiler /nologo /target:winexe /optimize+ /reference:System.Windows.Forms.dll ('/out:' + (Join-Path $projectRoot 'Trading_Terminal.exe')) (Join-Path $PSScriptRoot 'launcher/Launcher.cs')
if ($LASTEXITCODE -ne 0) { throw 'Launcher build failed.' }
if ($CopyToParent) {
    $parentRoot = Split-Path -Parent $projectRoot
    Copy-Item -LiteralPath (Join-Path $projectRoot 'Trading_Terminal.exe') -Destination (Join-Path $parentRoot 'Trading_Terminal.exe') -Force
    Write-Output (Join-Path $parentRoot 'Trading_Terminal.exe')
}
