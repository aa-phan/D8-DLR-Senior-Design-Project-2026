# PSS/E laptop runbook

**Date:** 2026-10-29
**From:** pss-e-integration Phase 3 (plan 03-06: TST-02, SCH-01, SCH-02, DBX-02); Phase 4 plan 04-05 (SCL-06) for steps 4 and 5
**To:** the person at the licensed laptop, and the owner of the live database for steps 8 to 10
**Status:** rehearsed on the Mac against a fake psspy and a local database; nothing in it has been run on the laptop, so every statement about real PSS/E, the licence, Windows or Task Scheduler is tagged `[UNVERIFIED until step N]`

## How to use this runbook

The runbook is the list of things that only the laptop can show. Each step gives the command, what it should print, when to stop, which requirement it can close, and what the Mac already proved. The setup guide, [psse_laptop_setup.md](psse_laptop_setup.md), says how to install the job and explains every setting; read it first. The two documents use the same commands.

Run the steps in order. Do not skip a step because the one after it looks easier. A step that fails stops the session (see "Stop rules"); nobody edits code on the laptop to make a step pass.

Placeholders in the command blocks:

| Placeholder | Meaning |
|---|---|
| `<PYTHON>` | The Python interpreter that matches PSS/E's `psspy` folder (see step 0). Quote it if its path has a space. |
| `<REPO>` | The folder holding this repository's copy on the laptop. |
| `<CONFIG>` | The job's configuration file (see the guide, "Configuration file"). |
| `<SITE>` | The folder in the user's own area that holds the extra Python packages. |
| `<WORKDIR>` | A folder only you can write, used as the scheduled task's working folder. |
| `<OUT>` | A file name that does not exist yet, for the filled Task Scheduler XML. |

A command block marked `<!-- cmd: NAME -->` in the Markdown source is run by `backend/tests/psse_rehearsal_test.py` on the Mac, against the fake psspy and a local database, so a flag that does not exist or a result line that changed fails the test suite. A block marked `manual` cannot run on the Mac (PowerShell, pip, icacls).

Two columns in the table below keep the claims honest. **Mac-proven** says what the rehearsal and the earlier plans showed with fakes. **Laptop-proven** says what only the laptop can show; it stays pending until someone does the step and the evidence is in the record. A claim about the laptop carries a tag `[UNVERIFIED until step N]` and a short id such as `(U05)`; the register at the end of this runbook lists each id with the evidence that clears it.

Steps 0 to 6 need only the laptop and one of PSS/E's own example cases. Steps 7 to 10 need production-pipeline Phase 6 (the live tables and the role), Power Systems' case and mapping, and two decisions by the project owner. Results are pasted back into the repository record without identifiers (see "Pasting results safely"). The result tables are append-only and the job's role has no DELETE, so a write in step 9 or 10 is permanent.

## Steps

| Step | What | Needs | Closes | Mac-proven | Laptop-proven |
|---|---|---|---|---|---|
| 0 | Ask the teammate: PSS/E version and edition, licence, Python, rights | the teammate | none | the question list is written (guide questions 1, 2, 6, 11) | pending: the answers |
| 1 | Install: repository copy, wheelhouse, configuration file with its ACL | a Python that matches `psspy` | none | the wheelhouse pins equal `requirements.txt`; the configuration reader and its refusals | pending: pip, the import and `icacls` on the laptop |
| 2 | `selftest`: start PSS/E, print the version and the launch functions | the licence | none | run on a stub and a fake psspy; exit codes and the six rows | pending: real `psseinit`, the output redirect, the environment helper and the DLL folder |
| 3 | `probe`, read only, on a copy of an example case | step 2 green | none | run on the fake psspy; default report holds no identifier | pending: the real signatures and bulk reads |
| 4 | Read the scaling call's layout, then `probe --write-check` on the same copy | step 3 green | none (SCL-06 in part) | run on the fake psspy; the case file is never saved; `scale_to_target` passes on the fake by construction | pending: the real rating write, `scal_2` and the whole-case `scale_to_target` row |
| 5 | Dry run on a throwaway version 2 mapping, marked placeholder, with `study_seconds` of the four-city run | step 4 green | none (SCL-06 in part) | dry run equals a real run up to the connect; counts only; four scaled copies on the fake | pending: a four-city study on a real case and its time |
| 6 | Task Scheduler with the dry-run task: three hourly starts, a held-lock overlap, unregister | steps 0 to 5 | SCH-01 | the XML is rendered, parsed and its arguments accepted; the lock refuses a second process (exit 4) | pending: the real scheduler |
| 7 | The real case: probe and dry run with the real mapping, the engineer's review, one hand-check | Power Systems' case and mapping | none | the same commands on the fake psspy | pending: units and values on the real network |
| 8 | The credential proof: `credcheck` (role and REST legs; write proof only if the owner agrees) | Phase 6 applied, the role's password | DBX-02 | run on local Postgres and a loopback stand-in; every planted fault is caught | pending: the live pooler, grants and key |
| 9 | The proof write (decision 1): exactly one real run, then the read-back | step 8 and decision 1 | TST-02 | one run of 1 + 4 + 4 + 10 rows on local Postgres, every completeness check ok | pending: the live write |
| 10 | The real task (decision 2): hourly runs, a next-day gap check, one induced gap, the stop | step 9 and decision 2 | SCH-02 (confirms SCH-01); DOC-01 after the final guide edit | the gap check equals an independent reference; an induced gap exits 5 | pending: a day of unattended runs |

## Step details

### Step 0: Ask the teammate

**Needs:** the teammate who owns the laptop. No command runs on the laptop yet beyond the read-only checks below.

Ask the questions of the guide's question list (1, 2, 6 and 11) and write the answers in the hand-over record. No path, host, user name or licence number goes into the repository.

| Ask or read | How |
|---|---|
| PSS/E version and edition (full, free, university) | PSS/E's about box; `selftest` prints the version in step 2 |
| Licence type: local, dongle or network, and whether a VPN is needed | the teammate |
| Python path and bitness (the interpreter that matches PSS/E's `psspy` folder) | the first block below |
| The `psspy` folder (`PSSPY39` or the one for the installed version) | the PSS/E install folder |
| The environment helper (a module in the `psspy` folder whose header says it sets the PSS/E environment, `psse3604` for PSS/E 36.4; another version's helper may have another name `[UNVERIFIED until step 0]` (U34)) | read the folder's module names, not its path |
| Administrator rights, and whether the teammate can register a scheduled task for their own account | the teammate |
| Wake and sleep support, plugged in at :15 | `powercfg /a` |
| Clock synchronisation | `w32tm /query /status` |
| BitLocker, antivirus or application control that could block a new script folder | the teammate |

<!-- cmd: manual -->
```
<PYTHON> -c "import sys, struct; print(sys.version); print(struct.calcsize('P') * 8)"
```

<!-- cmd: manual -->
```
powercfg /a
w32tm /query /status
```

**Should show:** a 64-bit interpreter, and a PSS/E version whose `psspy` folder matches that interpreter. PSS/E 35.x is reported to ship Python 3.9 with a `PSSPY39` folder and 34.x to be 32-bit `[UNVERIFIED until step 0]` (U01); PSS/E 36.4 was seen to ship Python 3.13 and 3.14 (folders `PSSPY313` and `PSSPY314`) in the first laptop session. The licence is expected to work in an interactive session without a VPN `[UNVERIFIED until step 0]` (U02). The default assumption is that a licence is not available to a signed-out or non-interactive session, so the task runs only while the user is signed in `[UNVERIFIED until step 0]` (U30).

**Stop if:** the interpreter is 32-bit (no psycopg wheel exists; the job does not support it), the licence needs a VPN that will not be up at :15, or the teammate cannot say which Python matches PSS/E.

### Step 1: Install

**Needs:** step 0 answered; a folder in the user's own area (for example under `%LOCALAPPDATA%\dlr-psse`), never Downloads or Program Files.

1. Put the repository copy in `<REPO>` (clone, or unpack a ZIP and set `PSSE_JOB_VERSION` in the configuration file). Put Power Systems' files, the copy of the example case and the mapping in a private folder outside the repository.
2. Choose the psycopg pin from the guide's decision table for the interpreter of step 0. On a machine with internet, download the wheels for the target interpreter, then install them from the downloaded folder into `<SITE>`. The wheelhouse needs a human decision first: the five packages are new to this project, so check each name on PyPI and record each wheel's sha256 against PyPI before installing. If an install fails, do not try a similarly named package; stop and tell the owner.

<!-- cmd: manual -->
```
python -m pip download "psycopg[binary]==<PIN>" -d wheelhouse --only-binary=:all: --platform win_amd64 --python-version <X.Y> --implementation cp
python -m pip install --no-index --find-links wheelhouse --target "<SITE>" "psycopg[binary]==<PIN>"
```

3. Check that the pinned version imports from the site folder (the import only; nothing connects):

<!-- cmd: manual -->
```
<PYTHON> -c "import sys; sys.path.append(r'<SITE>'); import psycopg; print(psycopg.__version__)"
```

4. Write the configuration file `<CONFIG>` with the keys needed so far, and nothing secret yet:

```text
PSSE_CASE_PATH=<absolute path of the copy of the example case>
PSSE_PSSPY_DIR=<the psspy folder of the PSS/E install>
PSSE_ENV_MODULE=<the helper module in the psspy folder, for PSS/E 36.4 psse3604>
PSSE_BIN_DIR=<the PSS/E program folder>
PSSE_SITE_DIR=<SITE>
PSSE_JOB_VERSION=<short label>
```

`PSSE_ENV_MODULE` names PSS/E's environment helper, a module in the `psspy` folder that the launcher imports before `psspy`. On PSS/E 36.4 `selftest` stops without it; leave it out only when the install has no such module `[UNVERIFIED until step 0]` (U34).

5. Limit the file to the user and check the result:

<!-- cmd: manual -->
```
icacls "<CONFIG>" /inheritance:r /grant:r "%USERNAME%:(R,W)"
icacls "<CONFIG>"
```

**Should show:** pip reports success; the import prints the pinned version, for example `3.2.13` `[UNVERIFIED until step 1]` (U04); `icacls` lists only the user, with no other account and no inherited entry `[UNVERIFIED until step 1]` (U03). Whether the older psycopg lines run `writer.py` is not shown here: the import proves the package loads, and the first connection is step 8.

**Stop if:** a package cannot be installed or a hash differs from PyPI (the owner decides; never substitute another package), or `icacls` still lists other accounts.

### Step 2: selftest

**Needs:** step 1; the licence available in the signed-in session; `PSSE_ENV_MODULE` set in `<CONFIG>` when the install ships an environment helper (PSS/E 36.4 does). If you already stopped here before the key existed: pull the repository copy, add the line to `<CONFIG>` and run this step again.

<!-- cmd: selftest -->
```
<PYTHON> -X utf8 "<REPO>\backend\psse_run_hourly.py" selftest --config "<CONFIG>"
```

**Should show:** exit 0 and these lines, in this order:

- `Python <version>, 64-bit`
- `PSS/E started`
- four notes of the form `<function>: redirected to the log folder`, one each for `report_output`, `progress_output`, `alert_output` and `prompt_output`
- six `PASS` rows: `version` (with `PSS/E <version>`) and one `launch:` row each for `psseinit`, `report_output`, `progress_output`, `alert_output` and `prompt_output`
- the count line `6 PASS, 0 FAIL, 0 SKIP`

No licence dialog and no demo banner appear. The tags for what this proves on the real PSS/E: `psseinit` takes the bus limit and 20000 is enough `[UNVERIFIED until step 2]` (U05); the four output functions accept a redirect to a file `[UNVERIFIED until step 2]` (U06); `os.add_dll_directory` of the program folder is needed, or enough, for `psspy` to load on Python 3.8 or newer `[UNVERIFIED until step 2]` (U07); importing `psspy` needs no registry write for a standard user `[UNVERIFIED until step 2]` (U08); the job's code runs on the laptop's older Python (never run on a version below 3.12 here, only syntax-checked for 3.7) `[UNVERIFIED until step 2]` (U31).

The first laptop session saw this step stop on PSS/E 36.4 with `PSS/E could not be started: PsseUnavailable: psspy could not be imported (ImportError)`, because `import psspy` failed with `DLL load failed while importing psscommon` even with the folders on the module search path and registered as DLL folders, and saw `psspy` load after PSS/E's environment helper (`psse3604`) was imported by hand. When `PSSE_ENV_MODULE` is set, the launcher imports that module first, after the search folders are appended and before `psspy`; that this launcher import works on the laptop is `[UNVERIFIED until step 2]` (U33). The failure line names only the exception class, never its text.

**Stop if:** any FAIL row, or exit 6. A failure line reads `PSS/E could not be started: <Class>: <text>` with absolute paths replaced by `<path>`. "Bad magic number" means the interpreter does not match the `psspy` folder; "DLL load failed" means check `PSSE_ENV_MODULE` and then `PSSE_BIN_DIR`. `psspy could not be imported (<Class>)` ending in `PSSE_ENV_MODULE is not set` means add the key; `the module named by PSSE_ENV_MODULE could not be imported (<Class>)` means the name is wrong or the module is not in the configured `psspy` folder (read the folder's module names); `psspy could not be imported (<Class>)` after the helper succeeded is a new finding for a gap-closure plan. A name that is not a plain module name (letters, digits and underscores, not starting with a digit, no dot, slash, space or `.py`) is exit 2 before anything starts. A FAIL on a `launch:` row is a gap-closure item for the launcher, not something to fix on the laptop.

### Step 3: probe, read only

**Needs:** step 2 green. `PSSE_CASE_PATH` points at a copy of one of PSS/E's own example cases (from the install's `EXAMPLE` folder), copied to your private folder. The case's folder, size and number of usable lines are not known in advance `[UNVERIFIED until step 3]` (U09).

<!-- cmd: probe -->
```
<PYTHON> -X utf8 "<REPO>\backend\psse_run_hourly.py" probe --config "<CONFIG>"
```

**Should show:** exit 0. Every `signature:` row is `PASS` or `SKIP`. The rows `version`, `load_case`, `branch_table`, `bus_table`, `column_alignment`, `circuit_id_padding`, `option_strings` and `load_flow` are `PASS`. The last line is a count line with `0 FAIL`. The default report holds no bus number, circuit id, path or error text, so it is safe to paste.

The row to watch is `signature:branch_chng_3`: its parameter list is unconfirmed (Phase 2 left it open) `[UNVERIFIED until step 3]` (U10). A FAIL there is expected-risk, not a surprise: the fix is in the adapter, on the Mac.

**Stop if:** any FAIL. Open a gap-closure plan for the Phase 2 adapter; do not edit on the laptop. One FAIL has a known cause that is not an adapter bug: `load_flow` failing with `fnsl ierr 2: generators are converted` means the case was saved after PSS/E converted it for dynamics (a case whose name often ends in `cnv`). Every other probe row passes on such a case and the exit code is 6. Use the same system saved before conversion; the second laptop session saw 26 PASS and 1 FAIL on a converted case and 27 PASS and 0 FAIL on the unconverted one. The case Power Systems supplies must be unconverted for the same reason. The free Xplore edition also limits a case to 50 buses (the banner reads "50 BUS POWER SYSTEM SIMULATOR"); the 39-bus case fits.

### Step 4: probe with the write check

**Needs:** step 3 green, on the same copy. The write check changes a rating, a load and then the whole case's totals in memory and reloads the case from disk after each; it never saves. Use a copy, never Power Systems' own file.

**Read the scaling call's layout first.** The job scales each city's copy with one `scal_2` call over all buses in new-total mode. The positions it fills in are one table, `SCALE_LAYOUT` in `psse_api.py`: status position 2 set to 1 (new totals), status position 4 set to 1 (constant P and Q), target positions 1 and 2 for the load and generation in MW, totals positions 2 and 3 for the totals read, APIOPT 0 to scale and APIOPT 1 to read the totals only. Check it against the installed PSS/E API documentation: open the entry for SCAL_2, and for SCAL_4 if it is listed, and note what each position of STATUS, SCALVAL and TOTALS means and what APIOPT 0, 1 and 2 do. If the documentation cannot be opened, record the Scale dialog as a Python script on the example copy only, with obvious placeholder numbers (1111, 2222 and 3333), and note the recorded call line; never open, run or paste a recorded city script, because Power Systems' own recordings hold real figures and are executable, and the job never runs one. The first laptop session read the documentation for PSS/E 36.4 on 2026-11-10 and found every position above as listed; it also found that `scal_2` is marked obsolete there and implemented by `scal_4`, which exists (the job still calls `scal_2`). That the layout works on the engine is `[UNVERIFIED until step 4]` (U35): the probe run of 2026-11-11 found a rule the documentation does not state. A totals read (APIOPT 1) only opens scaling, and it stays open, even across a case load, until an APIOPT 2 call closes it; a second APIOPT 1 while one is open fails with ierr 5 (the manual lists no such code, so this is inferred from three experiments). The job therefore closes every totals read at once with an APIOPT 2 call that scales nothing. That fix has not yet run on the laptop, so a fresh `scale_to_target` PASS is still the proof. That the constant P and Q setting keeps each load's power factor is `[UNVERIFIED until step 4]` (U37). Paste any such note as positions and meanings only (see "Pasting results safely").

<!-- cmd: probe_write_check -->
```
<PYTHON> -X utf8 "<REPO>\backend\psse_run_hourly.py" probe --config "<CONFIG>" --write-check
```

**Should show:** exit 0. The first line is the notice that the write check changes the case in memory only and that the file is never saved. `rating_write` is `PASS` (RATEA changed by one MVA, read back and restored by reloading the case). `scale_load` is `PASS` (a subsystem defined and 1 MW of load added; the case reloaded). The combined `scal_2` call form is what `scale_load` exercises `[UNVERIFIED until step 4]` (U11). `scale_to_target` is `PASS` (the whole case was scaled to 90 percent of its own load and generation, read back at the targets and restored by reloading the case); it uses the case's own totals as targets, so it needs no city's figure and prints none. That the call scales the whole case as `SCALE_LAYOUT` says is `[UNVERIFIED until step 4]` (U35), and that loading the case again undoes the scaling, so that every city's copy starts from the file, is `[UNVERIFIED until step 4]` (U36). A `SKIP` on that row means the case has no load or no generation; use a case with both. Seen on 2026-11-11 (Phase 4 laptop record): the probe ended with 0 FAIL and exit code 0, and `scale_to_target` was PASS.

**Stop if:** `rating_write`, `scale_load` or `scale_to_target` is FAIL. The case file must be unchanged; check its size and date if in doubt. A `scale_to_target` detail saying a total "differs from the target" means the call did not scale as the layout says: compare the layout with the documentation again and open a gap-closure plan to correct `SCALE_LAYOUT` (one table, edited on the Mac). A detail saying "reloading the case did not restore the totals" means loading the case does not undo a scaling, so a city's copy could start from another city's scaling: stop and open a gap-closure plan for the study's per-city load.

### Step 5: dry run on a throwaway mapping

**Needs:** step 4 green.

The probe prints counts only, by design, so the installer picks the four lines from PSS/E's own tools. Open the example case in PSS/E's branch spreadsheet or branch data report. Note four in-service lines whose two end buses share a base kV and, for each of the four cities, one end bus as the sink. That PSS/E's own tools list the in-service branches with their base kV is `[UNVERIFIED until step 5]` (U12). The bus numbers stay on the laptop.

Copy the placeholder example, [psse_mapping_example.json](../schema/psse_mapping_example.json), to your private folder, keep `"placeholder": true`, replace the four lines (from bus, to bus, circuit id, sink bus) with the ones you noted, and add the line `PSSE_MAPPING_PATH=<path of that file>` to `<CONFIG>`. The throwaway mapping is version 2 (`schema_version` 2, which the example already is): every city carries a `scaling` block of `load_mw`, `gen_mw` and `basis`. Set each city's `scaling` to placeholder targets that are round fractions (for example 0.90, 0.95, 1.00 and 1.05, one per city) of the example case's own load and generation totals as PSS/E's totals report shows them, and `basis` to `average`. They are placeholders for a plumbing run, never a city's figure; keep them inside 0.05 to 20 times the case's own totals, which fractions of the totals always are. This is documentation, not a new launcher listing mode: the probe is frozen, the example case is PSS/E's own sample, and a listing flag would add code and a route for identifiers into logs.

<!-- cmd: dry_run_smoke -->
```
<PYTHON> -X utf8 "<REPO>\backend\psse_run_hourly.py" run --config "<CONFIG>" --dry-run --allow-placeholder
```

**Should show:** exit 0 and, in order: `dry run: nothing was written to the database`; a `rows:` line with `psse_run=1`, `psse_dispatched_capacity=4`, `psse_voltage_margin=4` and a contingency count that depends on the case; a `contingencies:` line; a `ratings:` line (all four cities on the static rating, because no ratings service is configured or every row is provisional); `outcome: fallback`; `rate_set`, `psse_version` and `study_seconds:` lines; and `validation: ok`. The study ran four times, once on each city's own scaled copy of the case; the four dispatch rows are the evidence. Record `study_seconds` for this four-city run on the example case: it is only the example's time, and it must stay under the 1500 second budget, which is `[UNVERIFIED until step 5]` (U38). Nothing is written to the database. Seen on 2026-11-11 (Phase 4 laptop record): exit 0, `psse_dispatched_capacity=4`, `validation: ok` and `study_seconds: 2.0` on the 39-bus example.

**Stop if:** exit 1 with `study failed at stage mapping` (pick other lines and try again; a missing or invalid `scaling` block is also a mapping failure), or any other stage (gap-closure plan). A failure at `apply_ratings` with a clause starting `scaling:` is a stop: the scaling did not take or errored, which points back to step 4's `scale_to_target` and the layout. If PSS/E's own tools cannot give the list of lines, step 5 stops here and a flag-gated listing mode becomes a gap-closure item.

### Step 6: Task Scheduler with the dry-run task

**Needs:** steps 0 to 5 passed; the laptop plugged in, awake and signed in for about three hours. Question 7 of the guide (a :15 start with no catch-up run) should be answered or its default accepted.

Render the XML for the smoke task. It runs `--dry-run --allow-placeholder`, so it writes nothing; `--allow-placeholder` appears only with `--dry-run`, never on a real run.

<!-- cmd: render_task_dry_run -->
```
<PYTHON> -X utf8 "<REPO>\backend\psse_render_task.py" --config "<CONFIG>" --work-dir "<WORKDIR>" --out "<OUT>" --dry-run --allow-placeholder
```

Register it for your own account with typed cmdlets. Import the XML as a string so the file encoding is not guessed, and rewrite its declaration to UTF-16 first: the template declares UTF-8, but PowerShell passes the string in memory as UTF-16, and without the rewrite `Register-ScheduledTask` stops with "The task XML is malformed ... unable to switch the encoding" (seen on the second laptop session; with the rewrite it registered) (U17).

<!-- cmd: manual -->
```
$xml = (Get-Content -Raw -Encoding UTF8 "<OUT>") -replace '^<\?xml[^>]*\?>', '<?xml version="1.0" encoding="UTF-16"?>'
Register-ScheduledTask -TaskName "DLR-PSSE-Hourly-DryRun" -Xml $xml
Get-ScheduledTaskInfo -TaskName "DLR-PSSE-Hourly-DryRun" | Format-List LastRunTime, LastTaskResult, NextRunTime, NumberOfMissedRuns
```

Let three hourly starts pass, then read the task again with the last command. For the overlap test, hold the run lock in one window and start the task from another:

<!-- cmd: hold_lock -->
```
<PYTHON> -X utf8 "<REPO>\backend\psse_run_hourly.py" hold-lock --config "<CONFIG>" --seconds 60
```

<!-- cmd: manual -->
```
Start-ScheduledTask -TaskName "DLR-PSSE-Hourly-DryRun"
Get-ScheduledTaskInfo -TaskName "DLR-PSSE-Hourly-DryRun" | Format-List LastRunTime, LastTaskResult
```

Finish by removing the smoke task:

<!-- cmd: manual -->
```
Unregister-ScheduledTask -TaskName "DLR-PSSE-Hourly-DryRun" -Confirm:$false
```

**Should show:** `Register-ScheduledTask` accepts the XML `[UNVERIFIED until step 6]` (U14); a standard user can register an interactive-only task for their own account `[UNVERIFIED until step 6]` (U15), and if not, the teammate registers it from their own session; `NextRunTime` is the next :15. After three hours there are three `LastRunTime` values at :15 and `LastTaskResult` is 0, because the exit code reaches the scheduler `[UNVERIFIED until step 6]` (U18). A successful dry run writes nothing to `psse_job.log`: it prints its counts to the console, which the scheduler discards, and the log only receives a warning (for example an unusable mapping) or, on a real run, the run's own record. So for this smoke task `LastRunTime` and `LastTaskResult` are the evidence, not the log (seen on the second laptop session). The task stays tied to the signed-in user and runs only while that user is signed in `[UNVERIFIED until step 6]` (U32). `hold-lock` prints `locked`; the task started meanwhile ends with `LastTaskResult` 4, because the run lock refuses a second instance on this machine's filesystem `[UNVERIFIED until step 6]` (U13). The observed no-overlap guarantee is the run lock; `IgnoreNew` is pinned as text in the XML and is never shown here by an observed skip `[UNVERIFIED until step 6]` (U20). `WakeToRun` may or may not wake a Modern Standby laptop `[UNVERIFIED until step 6]` (U16): note whether it did, and treat any missed hour as a gap, not a failure. Compare the laptop clock with a trusted source with `w32tm /query /status`; the comparison with the database comes after the first live write in step 9 `[UNVERIFIED until step 6]` (U19).

**Stop if:** registration is refused (ask the teammate to register it from their own session; if that fails too, stop), `LastTaskResult` is not 0 for a dry run (run the same dry-run command by hand in a console for the full output; `psse_job.log` holds warnings only), or two runs overlap.

### Step 7: the real case

**Needs:** Power Systems' case and mapping as private files; steps 2 to 6 passed; a Power Systems engineer to review the numbers. Neither file is ever committed, pasted or emailed into the repository.

Set `PSSE_CASE_PATH` and `PSSE_MAPPING_PATH` in `<CONFIG>` to the real files. Run the probe without the write check (the real case file is never the target of a write check), then the dry run without `--allow-placeholder`, so a placeholder mapping is refused.

<!-- cmd: probe -->
```
<PYTHON> -X utf8 "<REPO>\backend\psse_run_hourly.py" probe --config "<CONFIG>"
```

<!-- cmd: dry_run_real -->
```
<PYTHON> -X utf8 "<REPO>\backend\psse_run_hourly.py" run --config "<CONFIG>" --dry-run
```

**Should show:** the probe exits 0 with a `mapping` row of the form `0 problems` followed by each city and its base kV; no FAIL. The dry run exits 0, prints `validation: ok` and a `study_seconds:` value under 1500, the study's own time budget `[UNVERIFIED until step 7]` (U22). The engineer reviews the numbers on the laptop and answers the eight questions of [the study-definitions note](psse_study_definitions.md) in that note's own section. Hand-check one branch's written rating and one percent-of-rating value against the formulas of that note: units and values on the real network are not yet shown `[UNVERIFIED until step 7]` (U21). The record holds the outcome of the check, not the numbers.

**Stop if:** the mapping row reports problems, a city has mixed base kV, the study time is over the budget, or the hand-check disagrees. Nothing is written to the database in this step.

### Step 8: the credential proof

**Needs:** production-pipeline Phase 6 applied (the owner confirms this first), the role `dlr_psse_writer` with a password set by the owner out of band, and the connection string delivered privately. Put the three secrets in `<CONFIG>` only: `SUPABASE_PSSE_DB_URL` (with `sslmode=require` or stronger), `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY`. A service_role or secret key never touches the laptop.

<!-- cmd: credcheck -->
```
<PYTHON> -X utf8 "<REPO>\backend\psse_run_hourly.py" credcheck --config "<CONFIG>"
```

Run the write proof only if the owner agrees (guide question 8). It inserts one synthetic run inside a transaction that is rolled back, so nothing survives:

<!-- cmd: credcheck_write_proof -->
```
<PYTHON> -X utf8 "<REPO>\backend\psse_run_hourly.py" credcheck --config "<CONFIG>" --write-proof
```

**Should show:** exit 0 and every row `PASS`. The rehearsal printed `16 PASS, 0 FAIL, 0 SKIP` (thirteen role-leg rows and three REST rows), and `18 PASS, 0 FAIL, 0 SKIP` with the write proof; the live counts should match. The session pooler accepts the role in the form `ROLE.PROJECT-REF` `[UNVERIFIED until step 8]` (U23). Phase 6's live grants are as the reference DDL says `[UNVERIFIED until step 8]` (U24). The publishable key reads the ratings view and is refused with 401 or 403 when it tries to change `city_rating` `[UNVERIFIED until step 8]` (U25). The first connection is also the first time `writer.connect` runs against a real database on the laptop's older psycopg: psycopg 3.1.20 and 3.2.13 run `writer.py` (connect, transaction, write_run) on Python 3.7 to 3.9 `[UNVERIFIED until step 8]` (U26).

**Stop if:** any FAIL. A REST write that is not refused is a stop to tell the owner at once. A refused role goes to the owner. A repeated exit 3 means network or credential. Step 9 does not start.

### Step 9: the proof write and the read-back

**Needs:** step 8 passed, and **decision 1 of plan 03-08** answered by the user: write one, or defer. A write-one answer authorises exactly one real run and nothing else. It does not enable the hourly task and it does not authorise any other manual real run. The run's rows are permanent: the tables are append-only and `dlr_psse_writer` has no DELETE, so only the database owner can remove them. The run uses static ratings (every `city_rating` row is provisional until production-pipeline Phase 7's go), so its outcome is `fallback`; it is a line-outage screen near the mapped branches and a load-transfer margin, not a full N-1 study. The stored `case_id` is the case file's base name; rename the file first if that name should not appear in the private table.

<!-- cmd: real_run -->
```
<PYTHON> -X utf8 "<REPO>\backend\psse_run_hourly.py" run --config "<CONFIG>"
```

**Should show:** exit 0 and one line, `run_id=<id> outcome=fallback status=written exit=0` (`outcome=ok` is also correct if a trusted rating row exists). Copy the `run_id` (not into the repository). Then read the results back as the owner in the Supabase SQL editor, or as the writer role in `psql` (never paste a connection string anywhere). The completeness checks are in [psse_results_v1_checks.sql](../schema/psse_results_v1_checks.sql): run the whole file; every `ok` must be true.

The reading rules of [the schema specification](../schema/psse_results_v1.md) say the result set of an hour is the newest `ok` or `fallback` run for that slot, ordered by `started_at desc, run_id desc`. A failed run never has results.

#### Read back the newest complete run per hour

```sql
select distinct on (slot_time)
       slot_time, run_id, outcome, started_at, finished_at,
       n_contingencies, n_contingencies_with_results
from public.psse_run
where outcome in ('ok', 'fallback')
order by slot_time desc, started_at desc, run_id desc
limit 3;
```

#### Read back one run's rows

Replace `<run_id>` with the id the run printed. The first statement counts the rows of each table (1, 4, 4 and the contingency count the dry run showed); the second lists the four cities' dispatch rows.

```sql
select
  (select count(*) from public.psse_run where run_id = '<run_id>') as run_rows,
  (select count(*) from public.psse_dispatched_capacity where run_id = '<run_id>') as dispatch_rows,
  (select count(*) from public.psse_voltage_margin where run_id = '<run_id>') as margin_rows,
  (select count(*) from public.psse_contingency_result where run_id = '<run_id>') as contingency_rows;
```

```sql
select city, applied_mva, voltage_limit_mva, dispatched_mva, limiting_factor
from public.psse_dispatched_capacity
where run_id = '<run_id>'
order by city;
```

#### Compare the laptop clock with the database

`created_at` is set by the database and `finished_at` by the laptop, so their difference is the write delay plus the clock difference. Seconds are normal; minutes, or a negative value, mean the laptop clock is off and runs can land in the wrong hour.

```sql
select run_id, started_at, finished_at, created_at,
       created_at - finished_at as write_delay
from public.psse_run
order by created_at desc
limit 5;
```

**Stop if:** the run exits other than 0 (exit 1 is a recorded failed run: read `failed_stage` and `error` in `psse_run`; exit 3 is no record), the checks file has an `ok` that is false, or the read-back does not return the new run. Do not run `real_run` a second time to "try again": decision 1 covers one write.

### Step 10: the real task, the gap check and the stop

**Needs:** step 9 passed, and **decision 2 of plan 03-08** answered by the user, separately from decision 1: enable-observe, enable-and-keep or do-not-enable. Decision 2 alone authorises the unattended real task. Once it runs, each scheduled start at :15, only while the laptop is on and awake, appends one permanent record: a complete run (1 + 4 + 4 + the contingency rows), or one failed run row if the study or the write fails, or nothing at all (a gap) if the database cannot be reached. At one start per hour that is about 24 row sets a day, with no retention rule in this milestone.

Render the real task (no `--dry-run`, no `--allow-placeholder`):

<!-- cmd: render_task -->
```
<PYTHON> -X utf8 "<REPO>\backend\psse_render_task.py" --config "<CONFIG>" --work-dir "<WORKDIR>" --out "<OUT>"
```

<!-- cmd: manual -->
```
$xml = Get-Content -Raw -Encoding UTF8 "<OUT>"
Register-ScheduledTask -TaskName "DLR-PSSE-Hourly" -Xml $xml
Get-ScheduledTaskInfo -TaskName "DLR-PSSE-Hourly" | Format-List LastRunTime, LastTaskResult, NextRunTime, NumberOfMissedRuns
```

Leave the laptop on and awake. After at least three starts, run the gap check; run it again the next day over the whole period:

<!-- cmd: gaps -->
```
<PYTHON> -X utf8 "<REPO>\backend\psse_run_hourly.py" gaps --config "<CONFIG>"
<PYTHON> -X utf8 "<REPO>\backend\psse_run_hourly.py" gaps --config "<CONFIG>" --fail-on-gaps
```

To show that a gap is visible, induce one on purpose: disable the task for two full hours, enable it again, and run the gap check once those hours are closed.

<!-- cmd: manual -->
```
Disable-ScheduledTask -TaskName "DLR-PSSE-Hourly"
Enable-ScheduledTask -TaskName "DLR-PSSE-Hourly"
```

**How to stop the task** (at any time, and as decision 2's scope says): `Disable-ScheduledTask` first, which ends further starts and leaves the rows already written; then `Unregister-ScheduledTask` to remove the task. For enable-observe, disable it after the next-day check. For enable-and-keep, leave it enabled and record that decision 2 allowed it.

<!-- cmd: manual -->
```
Disable-ScheduledTask -TaskName "DLR-PSSE-Hourly"
Unregister-ScheduledTask -TaskName "DLR-PSSE-Hourly" -Confirm:$false
```

**Should show:** `NextRunTime` is the next :15. `LastTaskResult` is 0 for runs that completed; 3 means the database was unreachable that hour, 4 a second instance held the lock, 1 a recorded failed run, and each is explained. The gap check prints a header `gap check (UTC): N runs recorded` and a `no_run` row only for each hour the laptop was off or asleep, each explained, plus the induced hours; with `--fail-on-gaps` the exit code is 5 while a gap exists. The lock, not the scheduler's `IgnoreNew`, is the observed no-overlap guarantee. The repetition continues for a day and more with no end `[UNVERIFIED until step 10]` (U27); a hard kill at the 45 minute limit may leave a licence seat held until the licence server times out `[UNVERIFIED until step 10]` (U28); a daylight-saving change costs at most one doubled or missed slot `[UNVERIFIED until step 10]` (U29). Wake is an observation: note whether the laptop woke overnight.

**Stop if:** exit 1 or exit 3 for several hours in a row (disable the task at once and tell the owner), an unexplained pattern of gaps (record it as an open question, not a pass), or two runs that overlapped.

## Pasting results safely

Results go back into the repository record as words and counts, never as output copied from a run made with identifiers shown.

- Paste only the default report of `probe` and `selftest`, the `PASS`, `FAIL` and `SKIP` rows, count lines, exit codes and the gap check's times and kinds. Never paste output from `probe --show-identifiers`.
- Never paste a path, a host name, a user name, a licence number, a connection string, a key, a case or mapping file name, a bus number or a circuit id. Say "the private folder" and "the real mapping".
- A note on the scaling call's layout is pasted as positions and meanings only (which position of each array means what, and what each APIOPT value does), never a number from a city's script or from a recorded call on any copy but the example's.
- Write results as a pass, a fail or a stop, with the date and who ran it by role. Do not write numeric study results (ratings, dispatched values, margins); they belong to Power Systems' review.
- If a log or a screenshot shows an identifier, do not attach it. If a secret was pasted anywhere, ask the owner to reset the role's password and rotate the keys.
- A configuration file, a case file and a mapping file are never committed. A configuration file with secrets stays only on the laptop.

## UNVERIFIED register

Each row is one claim that only the laptop (or the live database) can show. The tag `[UNVERIFIED until step N]` in the guide and this runbook names the step; the id links the sentence to its row. Plans 03-07 and 03-08 remove or replace a tag only with evidence, and update the row in the same edit.

| Claim | Tag step | Evidence that clears it |
|---|---|---|
| U01 PSS/E 35.x ships Python 3.9 and a `PSSPY39` folder and 34.x is 32-bit (research assumption A1; the first laptop session saw PSS/E 36.4 ship Python 3.13 and 3.14, with `PSSPY313` and `PSSPY314` folders, not 3.11) | 0 | the teammate's answers and `selftest` showing the interpreter and the PSS/E version that match |
| U02 The licence works in an interactive session without a VPN (A10) | 0 | the teammate's answer and `selftest` starting with no dialog from the signed-in session |
| U03 `icacls` limits the configuration file to the user | 1 | `icacls "<CONFIG>"` listing only the user after the command |
| U04 The pinned psycopg version imports from the site folder on the laptop's interpreter (the import only) | 1 | the import printing the pinned version |
| U05 `psseinit` takes the maximum bus count and 20000 is enough (A2) | 2 | `selftest` showing `PSS/E started` and the `launch:psseinit` row PASS, and the real case loading in step 7 |
| U06 The four output functions accept a redirect to a file (A3) | 2 | the four notes reading `redirected` and `psse_output.log` holding the PSS/E banner |
| U07 `os.add_dll_directory` of the program folder is needed, or enough, for `psspy` to load on Python 3.8 or newer (A4; on PSS/E 36.4 the first laptop session saw it not enough: the environment helper module had to be imported as well) | 2 | `selftest` succeeding with `PSSE_ENV_MODULE` set, run once with `PSSE_BIN_DIR` set and once without it, which shows whether the folder is needed once the helper has run |
| U08 Importing `psspy` needs no registry write for a standard user (A11) | 2 | `selftest` succeeding from a standard user's session |
| U09 The example case's folder, size and usable same-kV lines (A5) | 3 | the probe's `branch_table` and `bus_table` rows and step 5's choice of four lines |
| U10 The `branch_chng_3` signature (a Phase 2 unverified item) | 3 | `signature:branch_chng_3` PASS in the probe |
| U11 The combined `scal_2` form (Phase 2 assumption A13) | 4 | `scale_load` PASS in the probe with the write check |
| U12 PSS/E's own tools list the example case's in-service branches with their base kV | 5 | the installer choosing four lines from that listing and the dry run completing |
| U13 The Windows byte lock behaves as on the development machine | 6 | a task started while `hold-lock` runs ending with `LastTaskResult` 4, and the lock free again after the holder exits |
| U14 Task Scheduler accepts the XML | 6 | `Register-ScheduledTask -Xml` succeeding with the rendered file |
| U15 A standard user can register an interactive-only task for their own account (A8) | 6 | the registration succeeding without administrator rights, or the recorded fallback of the teammate registering it |
| U16 `WakeToRun` wakes a Modern Standby laptop (A9) | 6 | a scheduled start made while the laptop slept, or a note that none was woken (then the hour is a gap) |
| U17 A quoted Command with spaces and a UTF-8 string import work | 6 | the registered task starting and `LastTaskResult` showing the launcher's own exit code |
| U18 The launcher's exit code reaches `LastTaskResult` | 6 | `LastTaskResult` 0 after a dry run and 4 after a start under a held lock |
| U19 The laptop clock agrees with the database | 6 | `w32tm /query /status` synchronised, then a write delay of seconds in the step 9 clock statement |
| U20 `IgnoreNew` drops a start made while an instance runs | 6 | Task Scheduler's history showing a start refused as already running; until then the run lock is the only observed guarantee |
| U21 Units and percent-of-rating values on the real network | 7 | the engineer's review and the hand-check of one rating and one percent-of-rating value |
| U22 A study time under the 1500 second budget on the real case | 7 | `study_seconds` in the real dry run under 1500 |
| U23 The session pooler accepts the role in the form `ROLE.PROJECT-REF` | 8 | `credcheck` connecting and the role-leg rows PASS |
| U24 Phase 6's live grants are as the reference DDL says | 8 | the 13 role-leg rows PASS on the live database |
| U25 The live key reads the ratings view and is refused at 401 or 403 on a write | 8 | the three REST rows PASS |
| U26 psycopg 3.1.20 and 3.2.13 run `writer.py` on Python 3.7 to 3.9 (A12) | 8 | the first `writer.connect` and `credcheck` completing on the laptop's interpreter |
| U27 A repetition with an Interval and no Duration repeats indefinitely (A7) | 10 | a day-long observation of hourly starts with `NextRunTime` still set |
| U28 A hard kill at the time limit may leave a licence seat held (A17) | 10 | a run killed at 45 minutes, if one happens, and whether the next start finds a seat |
| U29 Daylight-saving changes cost at most one doubled or missed slot (A18) | 10 | the gap check across a changeover, if one is observed |
| U30 A licence is not available to a signed-out or non-interactive session | 0 | the teammate's answer; the default assumption is that it is not |
| U31 The job's code runs on the laptop's older Python (never run below 3.12 here) | 2 | `selftest` and the dry run completing on that interpreter |
| U32 An interactive-token task runs only while its user is signed in | 6 | no run starting while the user is signed out, observed or stated by the teammate |
| U33 With `PSSE_ENV_MODULE` set to the PSS/E environment helper (`psse3604` for 36.4), the launcher's own import of the helper and then `psspy` succeeds and `selftest` starts PSS/E (importing the helper and then `psspy` by hand worked in the first laptop session) | 2 | `selftest` printing `PSS/E started` and six `PASS` rows with the key set, where it stopped with `psspy could not be imported (ImportError)` without it |
| U34 A PSS/E install other than 36.4 ships an environment helper module of the same kind, named after its version (35.x is assumed to; its name is not known here) | 0 | the helper's name read from that install's `psspy` folder, or a note that the only install in use is 36.4 |
| U35 The whole-case scaling layout of `SCALE_LAYOUT` is right on PSS/E 36.4 (read from the installed documentation on 2026-11-10 and matching on every position; the laptop probe of 2026-11-11 found that every totals read must be closed with an APIOPT 2 call, a fix not yet run on the laptop) | 4 | the scaling call's documentation or a recorded call line with placeholder numbers matching `SCALE_LAYOUT`, and `scale_to_target` PASS. Seen on PSS/E 36.4 on 2026-11-11 (Phase 4 laptop record). |
| U36 Reloading the case undoes a whole-case scaling, so every city's copy starts from the file | 4 | `scale_to_target` PASS. Seen on PSS/E 36.4 on 2026-11-11 (Phase 4 laptop record). |
| U37 The scaling mode keeps each load's power factor | 4 | the documentation of the load-type status slot, or one load's P and Q read before and after a recorded scaling of the example copy. Documented on PSS/E 36.4 on 2026-11-10 (status position 4 = constant P/Q ratio; Phase 4 laptop record), not measured. |
| U38 A four-city dry run on the example case with a version 2 throwaway mapping completes within the 1500 s budget | 5 | the dry run exit 0 with four dispatch rows, `validation: ok` and `study_seconds` recorded. Seen on PSS/E 36.4 on 2026-11-11 (Phase 4 laptop record). |

## Stop rules

- Any FAIL in steps 2 to 4 stops the session. Open a gap-closure plan for the Phase 2 adapter or the launcher; do not edit code on the laptop.
- A credential check FAIL stops before step 9. A REST write that is not refused is reported to the owner at once.
- A repeated exit 3 means network or credential: check the connection and ask the owner; do not retry in a loop.
- Step 9 writes once. Step 10 writes only after decision 2 and only while the task is enabled. No other manual real run writes.
- Exit 1 or exit 3 for several hours in a row: disable the task at once with `Disable-ScheduledTask` and tell the owner.
- Never paste output run with identifiers shown, and never a secret. If something sensitive was pasted, stop, tell the owner, and rotate.
- A step that cannot be done (no case yet, Phase 6 not applied) is recorded as pending, never as passed.
