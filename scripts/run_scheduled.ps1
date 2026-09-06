param([ValidateSet('startup', 'morning', 'evening')][string]$Trigger = 'startup')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:PYTHONIOENCODING = 'utf-8'
$logDirectory = Join-Path $projectRoot 'output\automation'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$logPath = Join-Path $logDirectory ((Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + $Trigger + '-launcher.log')
try {
    & "$projectRoot\.venv\Scripts\python.exe" -m tonghoptin.automation --trigger $Trigger *> $logPath
    exit $LASTEXITCODE
} catch {
    $_ | Out-String | Add-Content -LiteralPath $logPath
    exit 1
}
