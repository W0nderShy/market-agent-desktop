param([string]$CheckoutPath)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$dshRoot = Join-Path $projectRoot 'vendor/deepseek-harness'
if ($CheckoutPath) { $dshRoot = [IO.Path]::GetFullPath($CheckoutPath) }
$patchPath = Join-Path $projectRoot 'patches/dsh-market-home.patch'
if (!(Test-Path -LiteralPath $patchPath)) { throw 'Missing Desktop integration patch.' }
$previousPreference = $ErrorActionPreference
try {
    $ErrorActionPreference = 'Continue'
    & git -C $dshRoot apply --reverse --check $patchPath 2>$null
    $reverseResult = $LASTEXITCODE
} finally { $ErrorActionPreference = $previousPreference }
if ($reverseResult -eq 0) { Write-Output 'Desktop integration patch already applied.'; exit 0 }
& git -C $dshRoot apply --check $patchPath
if ($LASTEXITCODE -ne 0) { throw 'Patch does not match the checkout; preserve local edits and inspect manually.' }
& git -C $dshRoot apply $patchPath
if ($LASTEXITCODE -ne 0) { throw 'Could not apply Desktop integration patch.' }
Write-Output 'Desktop integration patch applied.'
