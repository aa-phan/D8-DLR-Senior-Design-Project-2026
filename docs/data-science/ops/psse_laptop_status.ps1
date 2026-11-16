# PSS/E laptop status check (read-only).
#
# Run from PowerShell, no admin needed:
#   powershell -ExecutionPolicy Bypass -File .\psse_laptop_status.ps1
#
# It changes nothing. It never opens config.txt, task_real.xml or mapping_real.json.
# It writes one file, psse_status.txt, on the Desktop. Send that file back.
# User and computer names, database URLs and keys are masked in the output.

$Base = 'C:\Ben_Meunier Laptop\dlr-psse'
$Tasks = @('DLR-PSSE-Hourly', 'DLR-PSSE-Stop')
# The window to explain (local Central time): the hourly task's whole run.
$From = Get-Date '2026-11-11 14:00'
$To = Get-Date '2026-11-12 11:00'
# The two missed hours, 11-12 12:00Z and 14:00Z, are 06:15 and 08:15 local.
$LogPattern = '^2026-11-12 (0[5-9]|10):'

$Out = Join-Path ([Environment]::GetFolderPath('Desktop')) 'psse_status.txt'

function Section($title) { ''; "==== $title ===="; }
function FirstLine($text) { if ($text) { ($text -split "`r?`n")[0] } }

$report = & {
    Section 'run time'
    "local: $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))"
    "utc:   $((Get-Date).ToUniversalTime().ToString('yyyy-MM-dd HH:mm:ss'))"

    Section 'clock vs web'
    try {
        $web = [DateTime]::Parse((Invoke-WebRequest -UseBasicParsing -Method Head https://www.microsoft.com).Headers.Date).ToUniversalTime()
        $diff = ((Get-Date).ToUniversalTime() - $web).TotalSeconds
        "web utc: $($web.ToString('yyyy-MM-dd HH:mm:ss'))  laptop minus web: $([math]::Round($diff, 1)) s"
    } catch { "web check failed: $($_.Exception.GetType().Name)" }

    Section 'scheduled tasks'
    foreach ($name in $Tasks) {
        try {
            $t = Get-ScheduledTask -TaskName $name -ErrorAction Stop
            $i = Get-ScheduledTaskInfo -TaskName $name -ErrorAction Stop
            "$name  state=$($t.State)  lastRun=$($i.LastRunTime)  lastResult=$($i.LastTaskResult)  nextRun=$($i.NextRunTime)  missed=$($i.NumberOfMissedRuns)"
        } catch { "$name  not found" }
    }

    Section 'task scheduler history (DLR-PSSE only)'
    try {
        Get-WinEvent -FilterHashtable @{ LogName = 'Microsoft-Windows-TaskScheduler/Operational'; StartTime = $From; EndTime = $To } -ErrorAction Stop |
            Where-Object { $_.Message -like '*DLR-PSSE*' } |
            Sort-Object TimeCreated |
            ForEach-Object { "$($_.TimeCreated.ToString('MM-dd HH:mm:ss'))  id=$($_.Id)  $(FirstLine $_.Message)" }
    } catch { "not available: $($_.Exception.Message)" }

    Section 'sleep, wake and power events'
    try {
        Get-WinEvent -FilterHashtable @{ LogName = 'System'; StartTime = $From; EndTime = $To;
                ProviderName = 'Microsoft-Windows-Kernel-Power', 'Microsoft-Windows-Power-Troubleshooter' } -ErrorAction Stop |
            Where-Object { $_.Id -in 1, 41, 42, 107, 105, 506, 507 } |
            Sort-Object TimeCreated |
            ForEach-Object { "$($_.TimeCreated.ToString('MM-dd HH:mm:ss'))  id=$($_.Id)  $(FirstLine $_.Message)" }
    } catch { "none found or not available: $($_.Exception.Message)" }

    Section 'sleep states supported (powercfg /a)'
    powercfg /a 2>&1

    Section 'job log, 11-12 05:00 to 10:59 local'
    $logs = Get-ChildItem -Path $Base -Recurse -Filter 'psse_job.log*' -ErrorAction SilentlyContinue
    if (-not $logs) { "no psse_job.log found under the folder" }
    foreach ($f in $logs) {
        "-- $($f.Name)"
        Select-String -Path $f.FullName -Pattern $LogPattern | ForEach-Object { $_.Line }
    }

    Section 'files in the folder (names, sizes and dates only)'
    Get-ChildItem -Path $Base -Recurse -Depth 1 -ErrorAction SilentlyContinue |
        ForEach-Object { "$($_.LastWriteTime.ToString('yyyy-MM-dd HH:mm'))  $('{0,10}' -f $_.Length)  $($_.FullName.Substring($Base.Length))" }
} 2>&1 | Out-String -Width 400

# Mask identifiers and anything that looks like a secret.
$report = $report -replace 'postgres(ql)?://\S+', '[url masked]'
$report = $report -replace '(sb_publishable_|sb_secret_|eyJ)[A-Za-z0-9_.\-]+', '[key masked]'
$report = $report -replace '(?i)password=\S+', 'password=[masked]'
$report = $report -replace 'user "[^"]*"', 'user "[masked]"'
foreach ($id in @($env:USERNAME, $env:COMPUTERNAME, $env:USERDOMAIN)) {
    if ($id) { $report = $report -replace [regex]::Escape($id), '[masked]' }
}

$report | Out-File -FilePath $Out -Encoding utf8
"Done. Send this file back: $Out"
