# PSS/E laptop setup guide

**Date:** 2026-10-29
**From:** pss-e-integration Phase 3 (plan 03-06, DOC-01)
**To:** whoever installs the hourly PSS/E job on the licensed laptop
**Status:** Mac-rehearsed. The commands and tables below were checked against the code, a fake psspy and a local database; nobody has followed this guide on the laptop yet. Every claim about real PSS/E, the licence, Windows or Task Scheduler is tagged `[UNVERIFIED until step N]` with a short id such as `(U05)`; the step is a step of [the runbook](psse_laptop_runbook.md), whose register lists each id with the evidence that clears it.

## Purpose and scope

The job runs one PSS/E study every hour on the licensed laptop and writes the result into the project's private result tables. Each run writes one record in `psse_run` and, when the study completes, four rows in `psse_dispatched_capacity`, four in `psse_voltage_margin` and the rows of `psse_contingency_result`. The tables, their columns and the reading rules are in [the schema specification](../schema/psse_results_v1.md); what the study computes is in [the study-definitions note](psse_study_definitions.md).

The position of this guide is that the job runs only while the laptop is on, awake and signed in. A missed hour is a gap, not a failure: the gap check lists every hour with no complete result set, so a gap is visible. There is no always-on guarantee; that is out of scope for this milestone.

Also out of scope: running the job as a Windows service or as another account, public results, a full N-1 study (the screen covers line outages near the mapped branches only), and any change to the production pipeline. Until production-pipeline Phase 7 gives its go, every rating the job reads is provisional, so every run uses the static ratings and its outcome is `fallback`. Do not present a result as a dispatch the grid operator should rely on until Power Systems has reviewed the definitions and answered the questions in the study-definitions note.

How to read the tags: `[UNVERIFIED until step N]` means the Mac cannot show the statement, and step N of the runbook is where the laptop (or the live database) will. The tag stays until someone records evidence and updates the register. The guide's questions section lists the open decisions; none is answered here.

## Prerequisites and how to read each

Read each item before installing. Write the answers in the hand-over record at the end of this guide, without any path, host or user name.

| Item | How to read it | Why it matters |
|---|---|---|
| PSS/E version and edition (full, free, university) | PSS/E's about box; `selftest` prints the version | picks the interpreter and the psycopg pin; an edition with a small bus limit may not fit the real case |
| Licence type: local, dongle or network | ask the teammate | a network licence may need a VPN; a signed-out session may have no licence `[UNVERIFIED until step 0]` (U30) |
| Python path and bitness | `<PYTHON> -c "import sys, struct; print(sys.version); print(struct.calcsize('P') * 8)"` | must be 64-bit and must match the `psspy` folder |
| The `psspy` folder | the PSS/E install folder (`PSSPY39` for Python 3.9, and so on) | PSS/E 35.x is reported to ship Python 3.9, 34.x to be 32-bit and 36.x to ship Python 3.11 `[UNVERIFIED until step 0]` (U01) |
| Administrator status | ask the teammate | the guide needs none; a missing right changes who registers the task |
| Windows version | `winver` | Windows 11 laptops usually use Modern Standby, which affects wake |
| Power settings | `powercfg /a` | shows which sleep states exist and whether wake timers can work |
| Clock | `w32tm /query /status` | the laptop clock sets each run's hour; a skew shows as a false gap |
| Outbound access to the database pooler | `Test-NetConnection <pooler-host> -Port <port>` (the host and port come from the owner) | a campus or hotel network may block the port |
| Task Scheduler registration | step 6 of the runbook | a standard user may not be allowed to register a task `[UNVERIFIED until step 6]` (U15) |

<!-- cmd: manual -->
```
Test-NetConnection <pooler-host> -Port <port>
```

## Interpreter and psycopg decision table

The job's own code needs only the Python standard library. Only the database write uses psycopg, which is not part of PSS/E's Python, so it is installed into a folder the user owns. Choose the pin from the interpreter that matches PSS/E's `psspy` folder.

| Interpreter | Pin | Wheel | Note |
|---|---|---|---|
| 3.7 | `psycopg[binary]==3.1.20` | `cp37-cp37m-win_amd64` | needs `typing-extensions` and, for Python before 3.9, `backports.zoneinfo`, plus `tzdata` |
| 3.8 | `psycopg[binary]==3.2.13` | `cp38-cp38-win_amd64` | psycopg 3.3 dropped Python 3.8, so stay on 3.2.13 |
| 3.9 | `psycopg[binary]==3.2.13` | `cp39-cp39-win_amd64` | psycopg 3.3 dropped Python 3.9, so stay on 3.2.13 |
| 3.10 to 3.12 | `psycopg[binary]==3.3.6` | `cp310`, `cp311`, `cp312` (`win_amd64`) | the repository pin in `requirements.txt`; this row follows that file |
| 32-bit (any version) | none | none | not supported: no win32 wheel exists for these versions, and a 32-bit libpq would be needed |

`psycopg-binary` must equal psycopg's version; the `[binary]` extra pulls the matching one. Whether psycopg 3.1.x and 3.2.x run the job's `writer.py` on Python 3.7 to 3.9 is `[UNVERIFIED until step 8]` (U26): `selftest` and the dry run never import psycopg, step 1 shows only that the pinned version imports from the site folder `[UNVERIFIED until step 1]` (U04), and the first connection to a real database is the credential proof of step 8. The job's code has been syntax-checked for Python 3.7 and run only on Python 3.12 here `[UNVERIFIED until step 2]` (U31).

Install without administrator rights. On any machine with internet, download the wheels for the target interpreter (they are tagged for the target, not for the machine that downloads them). On the laptop, install them from that folder into the user's own folder, never into Program Files. The example below is for Python 3.9; change the pin and `--python-version` from the table.

<!-- cmd: manual -->
```
python -m pip download "psycopg[binary]==3.2.13" -d wheelhouse --only-binary=:all: --platform win_amd64 --python-version 3.9 --implementation cp
python -m pip install --no-index --find-links wheelhouse --target "%LOCALAPPDATA%\dlr-psse\site" "psycopg[binary]==3.2.13"
```

The launcher does not search that folder by itself: put it in the configuration file as `PSSE_SITE_DIR`, and the launcher appends it to the end of the module search path (never the front, so a planted module cannot shadow the standard library). A wheel is a zip file; if the interpreter has no pip, the wheels can be unpacked into the folder.

Package legitimacy. Five packages are involved: `psycopg`, `psycopg-binary`, `typing-extensions`, `tzdata` and (only before Python 3.9) `backports.zoneinfo`. Each is a declared dependency of psycopg. The automatic check flagged all five only because it had no download statistics, not for their content. Before installing on the laptop, open each package's page on [PyPI](https://pypi.org/) and check the name, then record each downloaded wheel's sha256 and compare it with the value PyPI lists:

<!-- cmd: manual -->
```
Get-FileHash -Algorithm SHA256 "<wheel file>"
```

If a package cannot be found or an install fails, do not substitute a similarly named package: stop and ask the owner. Pin `tzdata` to the downloaded version.

## Install

1. Choose a folder in the user's own area, for example under `%LOCALAPPDATA%\dlr-psse`. Never use Downloads or Program Files: Downloads is often synced or scanned and Program Files needs an administrator right.
2. Put the repository copy there: clone it, or unpack a ZIP. A ZIP has no commit to read, so set `PSSE_JOB_VERSION` in the configuration file; it is stored with each run.
3. Keep Power Systems' case file and mapping file in a private folder outside the repository. Never commit them. The repository ignores a `psse_local/` folder and the case file extensions as a safety net, not as a place to keep them.
4. Nothing secret goes into the repository, ever. The only place a secret is written is the configuration file, which stays on the laptop.
5. Install psycopg as described above, then write the configuration file as described next.
6. A freshly unpacked script, a compiled module in the site folder or a task action that points at a new path can be blocked or quarantined by antivirus or application control. If the first run exits at once with nothing in the log, ask the owner of the machine to allow the folder.

## Configuration file

The configuration file is the whole configuration. The launcher reads every setting from it and from nothing else; `--config FILE` is required for every command, and there is no default location. The process environment is never read for a setting, so a stray variable cannot point the unattended job at another database.

| Key | Required for | Secret | Default | Meaning |
|---|---|---|---|---|
| `SUPABASE_PSSE_DB_URL` | run, gaps, credcheck | yes | none | postgres URL of the `dlr_psse_writer` role (session pooler) |
| `SUPABASE_URL` | run, credcheck (REST leg) | yes | none | Supabase project URL, for the ratings read |
| `SUPABASE_PUBLISHABLE_KEY` | run, credcheck (REST leg) | yes | none | publishable key, for the ratings read |
| `PSSE_CASE_PATH` | run, run --dry-run, probe | no | none | absolute path of Power Systems' case file (a copy for the first checks) |
| `PSSE_MAPPING_PATH` | run, run --dry-run | no | none | absolute path of the mapping file |
| `PSSE_PSSPY_DIR` | run, run --dry-run, selftest, probe | no | none | folder holding `psspy` for the installed PSS/E |
| `PSSE_BIN_DIR` | none | no | none | PSS/E program folder, added to the DLL search path |
| `PSSE_SITE_DIR` | none | no | none | folder with extra Python packages (psycopg) |
| `PSSE_LOG_DIR` | none | no | `logs` next to the file | local log folder |
| `PSSE_LOCK_PATH` | none | no | `psse_job.lock` next to the file | the run lock file |
| `PSSE_MAX_BUSES` | none | no | `20000` | bus limit passed to `psseinit` |
| `PSSE_JOB_VERSION` | none | no | none | job version label stored with each run |
| `PSSE_PREFLIGHT` | none | no | `1` | 1 checks that the database host answers before PSS/E starts, 0 skips the check |

Where the table says "none" in the Required for column, the key is optional for every command. A mode needs only its own keys: `selftest` needs the `psspy` folder, `probe` needs the case and the folder, a dry run needs the case, the mapping and the folder, and `hold-lock` needs no key at all.

Format rules. One `KEY=VALUE` per line. Blank lines and lines that start with `#` are ignored. One pair of matching quotes around a value is removed. An empty value counts as absent. An unknown key, a repeated key, a line that is not in that form, a relative path where an absolute one is needed, or a file larger than 65536 bytes is an error (exit 2). The error names keys and line numbers, never a value or a line's text. The file is UTF-8 (a byte-order mark is accepted).

An example, with placeholders only (write the real values on the laptop, never in the repository):

```text
SUPABASE_PSSE_DB_URL=postgresql://dlr_psse_writer.<project-ref>:<password>@<pooler-host>:5432/postgres?sslmode=require
SUPABASE_URL=<the project's API URL>
SUPABASE_PUBLISHABLE_KEY=<the publishable key>
PSSE_CASE_PATH=<absolute path of the case file>
PSSE_MAPPING_PATH=<absolute path of the mapping file>
PSSE_PSSPY_DIR=<the psspy folder of the PSS/E install>
PSSE_BIN_DIR=<the PSS/E program folder>
PSSE_SITE_DIR=<the site folder with psycopg>
PSSE_JOB_VERSION=<short label>
```

The Phase 2 study-definitions note, [psse_study_definitions.md](psse_study_definitions.md), says the launcher will read `PSSE_CASE_PATH` and `PSSE_MAPPING_PATH` from environment variables. That sentence is superseded: both are keys of this configuration file, the process environment is not read for them, and that note is not edited.

libpq reads its own PG* environment variables itself (`PGSSLMODE`, `PGSERVICE`, `PGPASSFILE`, `PGPASSWORD` and others), and the launcher does not isolate them: they are not isolated, so none of them should be set on the laptop.

The database URL rule. A host other than the local machine needs `sslmode=require`, `sslmode=verify-ca` or `sslmode=verify-full` in the URL. libpq's default (`prefer`) falls back to a plaintext connection, so the launcher refuses a URL without one of the three. `require` is the minimum. Use `sslmode=verify-full` wherever a CA certificate is available (add `sslrootcert=<path of the CA certificate file>` to the URL); it also checks the server's name.

Protect the file with `icacls`. Limit the configuration file to the user and check the result:

<!-- cmd: manual -->
```
icacls "<CONFIG>" /inheritance:r /grant:r "%USERNAME%:(R,W)"
icacls "<CONFIG>"
```

The command removes inherited permissions and leaves the file readable and writable by the user only `[UNVERIFIED until step 1]` (U03). That keeps other accounts on the laptop out. It does not protect against the user's own programs, an administrator, malware that runs as the user, or a copy of the folder in a backup. This is why only the scoped role's credential and the publishable key may be in the file.

## First checks, in order

These are steps 2 to 5 of [the runbook](psse_laptop_runbook.md) in short; follow the runbook for the stop rules and the full expected output. Run them by hand before any task is registered.

1. `selftest` starts PSS/E from the configured folder and reports the interpreter, the version and the launch functions:

<!-- cmd: selftest -->
```
<PYTHON> -X utf8 "<REPO>\backend\psse_run_hourly.py" selftest --config "<CONFIG>"
```

It prints `Python <version>, 64-bit`, `PSS/E started`, four notes (`<function>: redirected to the log folder`), six `PASS` rows (the version and five launch functions) and `6 PASS, 0 FAIL, 0 SKIP`, with exit 0. Whether `psseinit` takes the bus limit and 20000 is enough is `[UNVERIFIED until step 2]` (U05); that the four output functions accept a redirect to a file is `[UNVERIFIED until step 2]` (U06); that `os.add_dll_directory` cures a DLL load failure on Python 3.8 or newer is `[UNVERIFIED until step 2]` (U07); that importing `psspy` needs no registry write for a standard user is `[UNVERIFIED until step 2]` (U08).

2. `probe` checks the real `psspy` against the adapter's call surface on a copy of one of PSS/E's own example cases. Its default report holds no identifier. The parameter list of `branch_chng_3` is `[UNVERIFIED until step 3]` (U10); the example case's folder, size and usable lines are `[UNVERIFIED until step 3]` (U09).

<!-- cmd: probe -->
```
<PYTHON> -X utf8 "<REPO>\backend\psse_run_hourly.py" probe --config "<CONFIG>"
```

3. `probe --write-check` changes a rating and a load in memory and reloads the case; it never saves. Use a copy. The combined `scal_2` form is `[UNVERIFIED until step 4]` (U11).

<!-- cmd: probe_write_check -->
```
<PYTHON> -X utf8 "<REPO>\backend\psse_run_hourly.py" probe --config "<CONFIG>" --write-check
```

4. A dry run on a throwaway mapping (a copy of the placeholder example with four lines you chose from PSS/E's own listing of the example case, which is `[UNVERIFIED until step 5]` (U12)). `--allow-placeholder` is accepted only together with `--dry-run`: a real run always refuses a placeholder mapping. The dry run writes nothing and prints counts only.

<!-- cmd: dry_run_smoke -->
```
<PYTHON> -X utf8 "<REPO>\backend\psse_run_hourly.py" run --config "<CONFIG>" --dry-run --allow-placeholder
```

Its first line is `dry run: nothing was written to the database`; it ends with `validation: ok`.

## Task Scheduler

The Task Scheduler definition is the committed template [psse_hourly_task.xml](../ops/psse_hourly_task.xml). Do not edit it by hand. The renderer fills four placeholders from paths that exist and writes a copy elsewhere; the XML holds no secret and no user name, because the job reads its settings from the configuration file. Render the smoke task first (it runs `--dry-run --allow-placeholder`), and the real task only after the proof write of runbook step 9.

<!-- cmd: render_task_dry_run -->
```
<PYTHON> -X utf8 "<REPO>\backend\psse_render_task.py" --config "<CONFIG>" --work-dir "<WORKDIR>" --out "<OUT>" --dry-run --allow-placeholder
```

<!-- cmd: render_task -->
```
<PYTHON> -X utf8 "<REPO>\backend\psse_render_task.py" --config "<CONFIG>" --work-dir "<WORKDIR>" --out "<OUT>"
```

The working folder is one only you can write, not Downloads. The start minute is 15 by default (`--minute N` or `--start YYYY-MM-DDTHH:MM:SS` change it). The renderer refuses a value it cannot quote safely and never overwrites an existing output without `--force`. The interpreter it writes into the task is the one that runs the renderer (or `--python`), so render with the interpreter that matches `psspy`.

Register, check, test, change, disable and remove, with typed PowerShell cmdlets. Import the XML as a string so the encoding is not guessed `[UNVERIFIED until step 6]` (U17). Whether Task Scheduler accepts the XML is `[UNVERIFIED until step 6]` (U14).

<!-- cmd: manual -->
```
$xml = Get-Content -Raw -Encoding UTF8 "<OUT>"
Register-ScheduledTask -TaskName "DLR-PSSE-Hourly" -Xml $xml
Get-ScheduledTaskInfo -TaskName "DLR-PSSE-Hourly" | Format-List LastRunTime, LastTaskResult, NextRunTime, NumberOfMissedRuns
Start-ScheduledTask -TaskName "DLR-PSSE-Hourly"
Disable-ScheduledTask -TaskName "DLR-PSSE-Hourly"
Enable-ScheduledTask -TaskName "DLR-PSSE-Hourly"
Unregister-ScheduledTask -TaskName "DLR-PSSE-Hourly" -Confirm:$false
```

To change the minute, render again with `--minute N --force`, unregister the task and register the new file. `schtasks /create /tn "DLR-PSSE-Hourly" /xml "<OUT>" /f` is an alternative to `Register-ScheduledTask`. Whether a standard user may register the task for their own account is `[UNVERIFIED until step 6]` (U15); if not, the teammate registers it from their own session.

The settings, each pinned by a test against the template:

| Element | Value | What it does |
|---|---|---|
| `MultipleInstancesPolicy` | `IgnoreNew` | a start made while a run is going is dropped and shows as a gap; this is pinned as text only, and the run lock is the observed no-overlap guarantee `[UNVERIFIED until step 6]` (U20) |
| `DisallowStartIfOnBatteries` | `false` | a laptop on battery still runs the job |
| `StopIfGoingOnBatteries` | `false` | unplugging does not stop a run |
| `AllowHardTerminate` | `true` | the time limit may kill a hung run |
| `StartWhenAvailable` | `false` | no catch-up run after a missed start: a missed hour stays a visible gap |
| `RunOnlyIfNetworkAvailable` | `false` | the launcher checks the network itself before it connects |
| `WakeToRun` | `true` | asks the laptop to wake for the run; it is unreliable on Modern Standby hardware `[UNVERIFIED until step 6]` (U16) |
| `Enabled` | `true` | the trigger and the task are on |
| `Hidden` | `false` | the task is visible in Task Scheduler |
| `ExecutionTimeLimit` | `PT45M` | 45 minutes: under the hour and above the study's 1500 second budget; a hard kill may leave a licence seat held `[UNVERIFIED until step 10]` (U28) |
| `Interval` | `PT1H` | one start every hour, with no end time `[UNVERIFIED until step 10]` (U27) |
| `LogonType` | `InteractiveToken` | runs for the user who registered it, only while that user is signed in `[UNVERIFIED until step 6]` (U32) |
| `RunLevel` | `LeastPrivilege` | no administrator right is used or needed |

Do not run the task as SYSTEM, and do not choose "Run whether user is logged on or not": that needs a stored password or the batch logon right a standard user lacks, and the PSS/E licence may not be available to a session that is not interactive. The interactive token is deliberate.

Why :15. The live pipeline writes the hour's rating row a few minutes after the hour. A job that starts after about half past can find the previous row older than 90 minutes and then uses the static ratings with the reason `stale`. A start at :15 leaves the previous row 75 minutes old, still fresh, and a study of up to 25 minutes ends before :45. A run started late after a wake (after :30) shows as `stale` in `ratings_used`.

Notes. Windows 11 laptops with Modern Standby may not wake for the task even with `WakeToRun`; the gap check shows the hour as missed. A daylight-saving change moves local time by an hour, the XML uses a fixed wall-clock minute and the gap check works in UTC, so a change may cost at most one doubled or missed slot `[UNVERIFIED until step 10]` (U29). The no-catch-up choice (`StartWhenAvailable` false) is question 7 of the questions section.

## Reading results and the gap check

The gap check lists every UTC hour between the first recorded run and the last closed hour that has no complete result set. It reads the database only and changes nothing. The statement is [psse_run_gaps.sql](../schema/psse_run_gaps.sql); the command runs it as the job's own role:

<!-- cmd: gaps -->
```
<PYTHON> -X utf8 "<REPO>\backend\psse_run_hourly.py" gaps --config "<CONFIG>"
<PYTHON> -X utf8 "<REPO>\backend\psse_run_hourly.py" gaps --config "<CONFIG>" --since 2026-11-03T00:00:00Z --fail-on-gaps
```

`--since` (included) and `--until` (excluded) need an ISO 8601 time with a UTC offset. `--fail-on-gaps` makes the exit code 5 while a gap exists. The output starts with `gap check (UTC): N runs recorded` and then one line per gap with its kind:

| gap_kind | Meaning |
|---|---|
| `no_run` | no `psse_run` row at all for that hour (laptop off or asleep, database unreachable, process killed before the record was written) |
| `failed_only` | rows exist for that hour but every one is failed (the job ran, the study or the write did not complete) |

An hour with several rows is not a gap, the current hour is never listed, and hours before the first run are not gaps. The check works in UTC and `slot_time` is the UTC hour of the laptop's start time, so a laptop clock far from the database's clock shows as a false gap plus a doubled slot. Check the clock with `w32tm /query /status` and compare it with the database as below; that the clock agrees with the database is `[UNVERIFIED until step 6]` (U19).

The reading rules say the result set of an hour is the newest `ok` or `fallback` run for that slot. This statement returns it (run it as the owner in the SQL editor, or as the writer role):

```sql
select distinct on (slot_time)
       slot_time, run_id, outcome, started_at, finished_at,
       n_contingencies, n_contingencies_with_results
from public.psse_run
where outcome in ('ok', 'fallback')
order by slot_time desc, started_at desc, run_id desc
limit 3;
```

`created_at` is set by the database and `finished_at` by the laptop, so their difference is the write delay plus the clock difference. Seconds are normal; minutes, or a negative value, mean the laptop clock is off.

```sql
select run_id, started_at, finished_at, created_at,
       created_at - finished_at as write_delay
from public.psse_run
order by created_at desc
limit 5;
```

Check that a run is complete with the completeness checks, [psse_results_v1_checks.sql](../schema/psse_results_v1_checks.sql): run the whole file; every `ok` must be true before a result set is trusted. Never combine values across cities: there is no corridor minimum and no bottleneck value.

## Exit codes and where to look

Every command returns one of these codes. Task Scheduler shows the same number as `LastTaskResult`; that the code reaches the scheduler unchanged is `[UNVERIFIED until step 6]` (U18).

| Code | Name | Meaning |
|---|---|---|
| 0 | `ok` | an ok or fallback run was written, or the run was already recorded |
| 1 | `failed_recorded` | the run failed and a failed record exists (dry-run: the study or its validation failed) |
| 2 | `usage` | usage or configuration error; nothing ran |
| 3 | `not_recorded` | no record could be written (the gap SCH-02 detects) |
| 4 | `locked` | another instance holds the run lock; skipped, nothing recorded |
| 5 | `gaps` | gaps found with --fail-on-gaps |
| 6 | `check_failed` | a check mode (selftest, probe, credcheck, gaps) could not complete or found a failure |
| 7 | `unexpected` | unexpected launcher error (redacted log line, nothing recorded) |

Where to look first:

| Exit code | Look first at |
|---|---|
| 0 | nothing for the run itself; confirm the hour with the gap check |
| 1 | the run's own record: `failed_stage` and `error` in `psse_run` (statement below), then `psse_job.log` |
| 2 | the lines on the console that start `configuration error:` or `usage error:`; they name keys and line numbers |
| 3 | the console line `database host did not answer (<class>); no run was started`, then the network and the credential |
| 4 | whether an earlier run is still going or a `hold-lock` is open; nothing was recorded for this start |
| 5 | the `no_run` and `failed_only` lines of the gap check |
| 6 | the `FAIL` rows printed by `selftest`, `probe` or `credcheck` |
| 7 | the console line `unexpected launcher error (<class>); see the log`, then `psse_job.log` |

The log folder (`PSSE_LOG_DIR`, a `logs` folder next to the configuration file by default) holds `psse_job.log` (rotated at 1 MB, five copies kept, secrets redacted) and `psse_output.log` (PSS/E's own console output, redirected). The failed runs and their reasons:

```sql
select run_id, started_at, outcome, failed_stage, error
from public.psse_run
where outcome = 'failed'
order by started_at desc
limit 5;
```

## Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| A licence dialog or a demo banner appears | the licence or dongle is not available to this session; a demo fallback may start `[UNVERIFIED until step 0]` (U02) | stop; read the edition string in the `selftest` version row; check the dongle or the VPN; the 45 minute limit ends a run that waits for a click |
| `Bad magic number` | the interpreter's minor version differs from the `psspy` folder's | use the interpreter that matches the folder (step 0) |
| `DLL load failed` | PSS/E's DLL folder is not on the search path, or the bitness differs | set `PSSE_BIN_DIR`; the launcher registers it with `os.add_dll_directory` on Python 3.8 or newer `[UNVERIFIED until step 2]` (U07) |
| The task runs and exits at once, nothing in the log | antivirus or application control blocks the new folder, a path with a space is not quoted, or the XML was imported in the wrong encoding | run the same command by hand first; ask the machine's owner to allow the folder; render again and import the XML as a UTF-8 string `[UNVERIFIED until step 6]` (U17) |
| The task is killed after 45 minutes | a hung licence request or a study that overran | read `psse_output.log`; the study has its own 1500 second budget; a hard kill may leave a licence seat held `[UNVERIFIED until step 10]` (U28) |
| Exit 2 | the configuration file is wrong or a key is missing for the mode | read the `configuration error:` lines; fix the keys they name |
| Exit 3 | the database host does not answer, or no record could be written | check the network and the credential; the 5 second preflight timeout bounds the TCP connect only and does not bound DNS resolution, so a slow name lookup can take longer |
| Exit 4 | another instance holds the run lock: the previous run is still going, or a `hold-lock` is open | check Task Manager for a Python process; nothing was recorded for this start |
| A repeated `stale` fallback | runs start after :30, so the previous rating row is older than 90 minutes | check the start minute and any late start after wake |
| A gap after sleep | the laptop was asleep or the lid was closed at :15; `WakeToRun` may not wake it `[UNVERIFIED until step 6]` (U16) | expected; the gap check shows it; keep the laptop on and plugged in |
| A probe FAIL on a signature | the real `psspy` differs from the adapter's call surface | stop; open a gap-closure plan for the adapter; do not edit on the laptop |
| A mapping failure | the mapping file is a placeholder on a real run, a city has mixed base kV, or the file cannot be read | run `probe` locally with `--show-identifiers` to see why (never paste that output); fix the mapping file |
| Task registration is refused | a standard user may not register a task `[UNVERIFIED until step 6]` (U15) | ask the teammate to register it from their own session |

## Credential hygiene

The job's only database credential is the `dlr_psse_writer` role, which can insert into and read the four result tables and nothing else. The ratings read uses the publishable key. A service_role key or a secret key never goes on the laptop, and neither does the database owner's password; the job refuses such a key.

- What the job never logs or prints: the connection string, the password, the pooler user and project reference, the host, the publishable key and any token-shaped text. Every printed line and every log record passes the redaction filter, and a failure line names a class and a text with absolute paths replaced.
- Do not use `setx` for a secret. It stores the value as plain text in the user's registry area, visible to every program of that user. The job does not read the environment for a setting anyway.
- The secrets live only in the configuration file, limited to the user (see "Configuration file"). The file is never committed.
- Never paste output made with identifiers shown (`probe --show-identifiers`), or a log that holds an identifier, into the repository, a chat or an issue.
- To rotate, ask the owner to reset the role's password; then replace the line in the configuration file.
- If the file leaks, tell the owner at once: reset the role's password, and replace the publishable key if the owner says so. The role can only insert and read the result tables, which limits the harm.

## Uninstall

1. Stop the task: `Disable-ScheduledTask -TaskName "DLR-PSSE-Hourly"`, then `Unregister-ScheduledTask -TaskName "DLR-PSSE-Hourly" -Confirm:$false`. Rows already written stay; the writer role has no DELETE.
2. Delete the install folder (the configuration file, the logs and the site folder).
3. Remove the repository copy and the private copies of the case and mapping, as Power Systems' rules require.
4. Ask the owner to reset the role's password so the old credential is dead.

## Hand-over record

Fill each row when it is known. All rows are pending; no identifier goes in this table.

| Item | Value | Date | Status |
|---|---|---|---|
| PSS/E version and edition | pending | pending | pending |
| Licence type | pending | pending | pending |
| Python version and bitness | pending | pending | pending |
| psycopg pin used | pending | pending | pending |
| Wheel sha256 values (kept in the laptop record, not here) | pending | pending | pending |
| Runbook step 0 passed | pending | pending | pending |
| Runbook step 1 passed | pending | pending | pending |
| Runbook step 2 passed | pending | pending | pending |
| Runbook step 3 passed | pending | pending | pending |
| Runbook step 4 passed | pending | pending | pending |
| Runbook step 5 passed | pending | pending | pending |
| Runbook step 6 passed | pending | pending | pending |
| Runbook step 7 passed | pending | pending | pending |
| Runbook step 8 passed | pending | pending | pending |
| Runbook step 9 passed | pending | pending | pending |
| Runbook step 10 passed | pending | pending | pending |
| Someone other than the author followed this guide through step 10 | pending | pending | pending |

## Questions for the user, the teammate and the owner

Each question says who answers it and what this guide assumes meanwhile. None of these is answered here; the answers go in the hand-over record.

1. **Teammate.** Which PSS/E version and edition (full, free or university), which licence type (local, dongle or network, and whether a VPN is needed), which Python interpreter (path and bitness), which `psspy` folder, and does the teammate have administrator rights? Meanwhile: assume a 64-bit interpreter that matches the `psspy` folder and a local licence, and stop at step 0 if not.
2. **Teammate.** Can the teammate register a scheduled task for their own account, does wake work (`powercfg /a`), and is the laptop plugged in and awake at :15? Meanwhile: assume registration works and wake does not, so a missed hour is a gap.
3. **The user and Power Systems.** Is the real case the IEEE 39-bus New England system, when do the case and the mapping arrive, and does Power Systems supply a PSS/E saved case (.sav) or a raw file? Meanwhile: do not wait; the smoke runs are dry-runs on one of PSS/E's own example cases with a throwaway mapping.
4. **The owner.** Does production-pipeline Phase 6 take the migration, when, who sets the `dlr_psse_writer` password and how is the connection string delivered privately, and does the session pooler accept the role in the form `ROLE.PROJECT-REF`? Meanwhile: every database proof runs on local Postgres only; steps 8 to 10 wait for Phase 6.
5. **The user.** Smoke runs are dry-runs only. Is one permanent live row set acceptable for the single proof write, and may the case file's base name be stored as `case_id` (rename the file first if not)? And, once the unattended real task is enabled (a second decision, after the proof write), is it acceptable that each hourly start appends a permanent row set (the writer has no DELETE) until someone disables the task? Meanwhile: no live write is made and the task is not enabled.
6. **The teammate and the owner.** Is a PSS/E licence available to a signed-out or non-interactive session? Meanwhile: assume not; the task uses the interactive token and runs only while the user is signed in.
7. **The user.** Is a :15 start with no catch-up run after a wake acceptable (`StartWhenAvailable` false)? Meanwhile: yes; a missed hour stays a visible gap.
8. **The user and the owner.** May `credcheck --write-proof` run on the live database (it inserts one synthetic run inside a transaction that is rolled back, which leaves dead tuples)? Meanwhile: it is not run; step 8 uses `credcheck` without it.
9. **Power Systems.** The eight open questions of `psse_study_definitions.md` (the mapping, the rate set, the static overwrite, the margin transfer, base-case violations, licensed modules, case size and run time, and the limits) remain open and are answered in that note's own section. Meanwhile: the documented defaults apply and every result is labelled not a full N-1 study.
10. **The owner.** Is unattended gap monitoring wanted later (exit code 5 exists for it, with `gaps --fail-on-gaps`)? Meanwhile: the gap check is run by hand.
11. **The teammate.** Is BitLocker on, and will antivirus or application control block a new script folder? Meanwhile: assume a new folder may be blocked, and run the commands by hand first.
12. **The user.** Where should the repository copy live on the laptop, and who owns the install? Meanwhile: a folder under the user's own area, owned by the teammate who runs the laptop.
