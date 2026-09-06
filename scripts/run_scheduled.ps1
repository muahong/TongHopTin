param([ValidateSet('startup', 'morning', 'evening')][string]$Trigger = 'startup')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:PYTHONIOENCODING = 'utf-8'
$logDirectory = Join-Path $projectRoot 'output\automation'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$logPath = Join-Path $logDirectory ((Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + $Trigger + '-launcher.log')
try {
    # Windows PowerShell 5 treats native stderr as terminating errors when
    # ErrorActionPreference=Stop; capture both streams without truncating them.
    $process = Start-Process -FilePath "$projectRoot\.venv\Scripts\python.exe" -ArgumentList "-m tonghoptin.automation --trigger $Trigger" -WorkingDirectory $projectRoot -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput $logPath -RedirectStandardError ($logPath + '.stderr')
    exit $process.ExitCode
} catch {
    $_ | Out-String | Add-Content -LiteralPath $logPath
    exit 1
}
