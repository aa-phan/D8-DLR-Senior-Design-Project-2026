# PSS/E laptop session for the pandapower reference work: the one command.
#
# Run from PowerShell, no admin needed, from anywhere:
#   powershell -ExecutionPolicy Bypass -File .\psse_pandapower_session.ps1 -Python <PYTHON> -Config <CONFIG> -Mapping <MAPPING COPY>
# Add -Check for a quick trial that writes no zip. Add -Only <section> only when the owner asks.
#
# It changes nothing in PSS/E's files and never saves the case. It opens no network connection and
# no database. The only file it leaves is one zip on the Desktop; the Python program writes it, this
# wrapper writes nothing itself. The summary the Python program prints is already masked: it holds
# counts, versions and fixed words only. Send the zip to the owner by the private channel, then
# delete it from the Desktop.
#
# This wrapper does three things: finds the repository and the Desktop, makes one call of the
# Python program, and removes a work folder that appeared on the Desktop during this run (PSS/E's
# console log can keep that folder alive after Python exits). It never removes a file, and never a
# folder that was already there before the run.

param(
    [Parameter(Mandatory = $true)][string]$Python,
    [Parameter(Mandatory = $true)][string]$Config,
    [Parameter(Mandatory = $true)][string]$Mapping,
    [switch]$Check,
    [string]$Only
)

# This file lives in docs\data-science\ops, three folders below the repository root.
$Repo = Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent
$Desktop = [Environment]::GetFolderPath('Desktop')

# The session work folders that were on the Desktop before this run; those are never touched.
$Before = @(Get-ChildItem -LiteralPath $Desktop -Directory -Filter 'psse_pp_session_*' -ErrorAction SilentlyContinue |
    ForEach-Object { $_.FullName })

$Mode = if ($Check) { 'check' } else { 'run' }
$Arguments = @($Mode, '--config', $Config, '--mapping', $Mapping, '--out-dir', $Desktop)
if ($Only) { $Arguments += @('--only', $Only) }

'==== copy from the next line ===='
& $Python -I -X utf8 -B (Join-Path $Repo 'backend\psse_pandapower_session.py') @Arguments
$code = $LASTEXITCODE

$New = @(Get-ChildItem -LiteralPath $Desktop -Directory -Filter 'psse_pp_session_*' -ErrorAction SilentlyContinue |
    Where-Object { $Before -notcontains $_.FullName })
foreach ($Folder in $New) {
    Remove-Item -LiteralPath $Folder.FullName -Recurse -Force -ErrorAction SilentlyContinue
}

"Exit code: $code"
'==== copy up to the line above ===='
exit $code
