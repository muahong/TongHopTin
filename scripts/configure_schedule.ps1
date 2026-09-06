param([switch]$InspectOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$names = @('TongHopTin Startup', 'TongHopTin 9PM')
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupDirectory = Join-Path $projectRoot "output\automation\scheduler-backup-$stamp"
if (-not $InspectOnly) {
    New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null
    foreach ($name in $names) {
        $task = Get-ScheduledTask -TaskName $name
        if ($task.State -eq 'Running') { throw "$name is running; retry after completion." }
        Export-ScheduledTask -TaskName $name | Set-Content -LiteralPath (Join-Path $backupDirectory "$name.xml") -Encoding Unicode
    }
    foreach ($name in $names) {
        [xml]$xml = Export-ScheduledTask -TaskName $name
        $ns = New-Object System.Xml.XmlNamespaceManager($xml.NameTable)
        $ns.AddNamespace('t', $xml.DocumentElement.NamespaceURI)
        function Set-TaskNode([string]$parentPath, [string]$child, [string]$value) {
            $parent = $xml.SelectSingleNode($parentPath, $ns)
            $node = $parent.SelectSingleNode("t:$child", $ns)
            if ($null -eq $node) {
                $node = $xml.CreateElement($child, $xml.DocumentElement.NamespaceURI)
                [void]$parent.AppendChild($node)
            }
            $node.InnerText = $value
        }
        Set-TaskNode '/t:Task/t:Settings' 'ExecutionTimeLimit' 'PT4H'
        Set-TaskNode '/t:Task/t:Settings' 'WakeToRun' 'true'
        Set-TaskNode '/t:Task/t:Settings' 'StartWhenAvailable' 'true'
        Set-TaskNode '/t:Task/t:Settings' 'MultipleInstancesPolicy' 'IgnoreNew'
        Set-TaskNode '/t:Task/t:Settings/t:RestartOnFailure' 'Interval' 'PT15M'
        Set-TaskNode '/t:Task/t:Settings/t:RestartOnFailure' 'Count' '3'
        Set-TaskNode '/t:Task/t:Settings/t:IdleSettings' 'StopOnIdleEnd' 'false'
        $trigger = 'evening'
        if ($name -eq 'TongHopTin Startup') {
            $trigger = 'startup'
            $triggers = $xml.SelectSingleNode('/t:Task/t:Triggers', $ns)
            foreach ($old in @($triggers.SelectNodes('t:CalendarTrigger', $ns))) { [void]$triggers.RemoveChild($old) }
            $calendar = $xml.CreateElement('CalendarTrigger', $xml.DocumentElement.NamespaceURI)
            $firstMorning = (Get-Date).AddDays(1).ToString('yyyy-MM-dd') + 'T09:00:00+07:00'
            $boundary = $xml.CreateElement('StartBoundary', $xml.DocumentElement.NamespaceURI)
            $boundary.InnerText = $firstMorning
            [void]$calendar.AppendChild($boundary)
            $daily = $xml.CreateElement('ScheduleByDay', $xml.DocumentElement.NamespaceURI)
            $interval = $xml.CreateElement('DaysInterval', $xml.DocumentElement.NamespaceURI)
            $interval.InnerText = '1'
            [void]$daily.AppendChild($interval)
            [void]$calendar.AppendChild($daily)
            [void]$triggers.AppendChild($calendar)
        }
        Set-TaskNode '/t:Task/t:Actions/t:Exec' 'Command' "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
        Set-TaskNode '/t:Task/t:Actions/t:Exec' 'Arguments' "-NoProfile -NonInteractive -WindowStyle Hidden -File `"$PSScriptRoot\run_scheduled.ps1`" -Trigger $trigger"
        Set-TaskNode '/t:Task/t:Actions/t:Exec' 'WorkingDirectory' $projectRoot
        Set-TaskNode '/t:Task/t:RegistrationInfo' 'Description' 'TongHopTin: morning at first logon or 09:00, evening at 21:00 UTC+7. Shared lock, resumable retries, success only after live verification. Requires signed-in Windows user and network.'
        $xml.Save((Join-Path $backupDirectory "$name-proposed.xml"))
        Register-ScheduledTask -TaskName $name -Xml $xml.OuterXml -Force -ErrorAction Stop | Out-Null
    }
}
foreach ($name in $names) {
    $task = Get-ScheduledTask -TaskName $name
    $info = Get-ScheduledTaskInfo -TaskName $name
    [pscustomobject]@{TaskName=$name; State=[string]$task.State; LastRunTime=$info.LastRunTime; LastTaskResult=$info.LastTaskResult; NextRunTime=$info.NextRunTime; MissedRuns=$info.NumberOfMissedRuns; WakeToRun=$task.Settings.WakeToRun; RetryCount=$task.Settings.RestartCount; RetryInterval=$task.Settings.RestartInterval; ExecutionTimeLimit=$task.Settings.ExecutionTimeLimit; LogonType=[string]$task.Principal.LogonType}
}
