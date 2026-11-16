# PSS/E laptop cleanup, run before the laptop is returned.
#
# Preview (changes nothing):
#   powershell -ExecutionPolicy Bypass -File .\psse_laptop_cleanup.ps1
# Apply:
#   powershell -ExecutionPolicy Bypass -File .\psse_laptop_cleanup.ps1 -Apply
#
# With -Apply it:
#   1. disables and removes the scheduled tasks DLR-PSSE-Hourly and DLR-PSSE-Stop;
#   2. blanks every secret value (SUPABASE_*, *KEY*, *PASSWORD*, *SECRET*, *TOKEN*) in config.txt
#      and its backups, keeping the key names and the non-secret lines;
#   3. removes lines that hold a connection string or key from the PowerShell history.
# It never deletes mapping_real.json: copy that somewhere private first. It never prints a file's
# contents. Other files that still match a secret pattern are only reported, never changed.
# It writes one report, psse_cleanup.txt, on the Desktop. Send that file back.

param([switch]$Apply)

$Base = 'C:\Ben_Meunier Laptop\dlr-psse'
$Repo = 'C:\Ben_Meunier Laptop\Senior Design\repo'
$Tasks = @('DLR-PSSE-Hourly', 'DLR-PSSE-Stop')
$SecretPattern = 'postgres(ql)?://|sb_publishable_|sb_secret_|eyJ[A-Za-z0-9_\-]{10,}|(?i)password='
$SecretKeyPattern = 'SUPABASE|PASSWORD|SECRET|TOKEN|KEY'
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

$Out = Join-Path ([Environment]::GetFolderPath('Desktop')) 'psse_cleanup.txt'

function Section($title) { ''; "==== $title ===="; }
function HitCount($path) {
    try { @(Select-String -Path $path -Pattern $SecretPattern -ErrorAction Stop).Count } catch { -1 }
}

$report = & {
    Section 'mode'
    if ($Apply) { 'APPLY: changes are made' } else { 'PREVIEW: nothing is changed; run again with -Apply' }
    "local: $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))"

    Section 'mapping file (never touched by this script)'
    $map = Join-Path $Base 'mapping_real.json'
    if (Test-Path $map) { 'mapping_real.json is present. Copy it somewhere private before the laptop is wiped.' }
    else { 'mapping_real.json not found' }

    Section 'scheduled tasks'
    foreach ($name in $Tasks) {
        $t = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        if (-not $t) { "$name  not found (nothing to do)"; continue }
        if (-not $Apply) { "$name  state=$($t.State)  would disable and remove"; continue }
        try {
            Disable-ScheduledTask -TaskName $name -ErrorAction Stop | Out-Null
            Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction Stop
            "$name  disabled and removed"
        } catch { "$name  FAILED: $($_.Exception.Message)" }
    }

    Section 'config files: blank secret values'
    $configs = Get-ChildItem -Path $Base -Filter 'config.txt*' -File -ErrorAction SilentlyContinue
    if (-not $configs) { 'no config.txt files found' }
    foreach ($f in $configs) {
        $lines = [IO.File]::ReadAllLines($f.FullName)
        $blanked = @()
        $new = foreach ($line in $lines) {
            if ($line -match '^\s*([A-Z_][A-Z0-9_]*)\s*=(.*)$') {
                $key = $Matches[1]
                $value = $Matches[2].Trim()
                if ($value -ne '' -and $key -match $SecretKeyPattern) { $blanked += $key; "$key="; continue }
            }
            $line
        }
        if ($blanked.Count -eq 0) { "$($f.Name)  no secret values"; continue }
        if ($Apply) {
            [IO.File]::WriteAllLines($f.FullName, [string[]]$new, $Utf8NoBom)
            "$($f.Name)  blanked: $($blanked -join ', ')"
        } else { "$($f.Name)  would blank: $($blanked -join ', ')" }
    }

    Section 'PowerShell history: remove lines with a connection string or key'
    $hist = $null
    try { $hist = (Get-PSReadLineOption).HistorySavePath } catch { }
    if (-not $hist) { $hist = Join-Path $env:APPDATA 'Microsoft\Windows\PowerShell\PSReadLine\ConsoleHost_history.txt' }
    if (Test-Path $hist) {
        $lines = [IO.File]::ReadAllLines($hist)
        $keep = @($lines | Where-Object { $_ -notmatch $SecretPattern })
        $removed = $lines.Count - $keep.Count
        if ($removed -eq 0) { 'no matching lines' }
        elseif ($Apply) { [IO.File]::WriteAllLines($hist, [string[]]$keep, $Utf8NoBom); "removed $removed line(s)" }
        else { "would remove $removed line(s)" }
    } else { 'no history file found' }

    Section 'remaining matches (report only; counts, never contents)'
    $scan = @()
    $scan += Get-ChildItem -Path $Base -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -ne '.sav' }
    # In the repo, only files git does not track (tracked files are already public on GitHub).
    if (Test-Path $Repo) {
        $untracked = @(git -C $Repo ls-files --others 2>$null)
        foreach ($rel in $untracked) {
            $p = Join-Path $Repo $rel
            if ((Test-Path $p) -and (Get-Item $p).Length -lt 5MB) { $scan += Get-Item $p }
        }
        "repo: $($untracked.Count) untracked file(s) scanned"
    }
    $any = $false
    foreach ($f in $scan) {
        $n = HitCount $f.FullName
        if ($n -ne 0) { $any = $true; "$n  $($f.FullName)" }
    }
    if (-not $any) { 'no file under the folder or the repo matches a secret pattern' }
} 2>&1 | Out-String -Width 400

# Mask identifiers and anything that looks like a secret.
$report = $report -replace 'postgres(ql)?://\S+', '[url masked]'
$report = $report -replace '(sb_publishable_|sb_secret_|eyJ)[A-Za-z0-9_.\-]+', '[key masked]'
$report = $report -replace '(?i)password=\S+', 'password=[masked]'
foreach ($id in @($env:USERNAME, $env:COMPUTERNAME, $env:USERDOMAIN)) {
    if ($id) { $report = $report -replace [regex]::Escape($id), '[masked]' }
}

$report | Out-File -FilePath $Out -Encoding utf8
"Done. Send this file back: $Out"
