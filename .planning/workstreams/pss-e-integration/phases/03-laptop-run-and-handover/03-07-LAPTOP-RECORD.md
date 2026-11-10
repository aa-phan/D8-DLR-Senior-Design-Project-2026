# 03-07 Laptop record (session A)

Versions, types and outcomes only. No path, host, user name, case or file name, connection string or key.

## Laptop facts

| Item | Value |
|------|-------|
| Windows | 10 |
| PSS/E | 36.4, free Xplore edition; the banner reads "50 BUS POWER SYSTEM SIMULATOR", so the bus limit is 50 (confirmed in session B; matters for plan 03-08) |
| PSS/E Python bindings folders | PSSPY313 and PSSPY314, plus psspy |
| Python | 3.14.0, 64-bit (matches PSSPY314) |
| Administrator rights | yes |
| Sleep states | Standby (S0 low power idle, network connected), hibernate, fast startup |
| Clock source | time.windows.com (type 0x9) |
| Licence type, VPN need | open |
| Pooler port 5432 reachable | open |
| BitLocker, antivirus or application control | open |
| Can the user register a scheduled task | open |

## psycopg pin and wheel hashes

Pin: `psycopg[binary]==3.3.6` (the repository pin in requirements.txt). The guide's decision table stops at Python 3.12; Python 3.14 is not in it. PyPI lists a `cp314-cp314-win_amd64` wheel for psycopg-binary 3.3.6, and `requires_python` is 3.10 or newer.

Wheelhouse for this laptop: three packages, not five. typing-extensions is a dependency of psycopg 3.3.6 only for Python before 3.13, and backports.zoneinfo only applies before 3.9, so neither is needed on 3.14. tzdata is needed on Windows.

Package check on PyPI (task 3, blocking-human): approved by the user. Hashes noted from PyPI before any download:

| Package | Version | File | sha256 from PyPI | Wheel as downloaded |
|---------|---------|------|------------------|---------------------|
| psycopg-binary | 3.3.6 | cp314-cp314-win_amd64 | 1fbd30e537dab22cafdf080608f10148fe2a5f3a61294ddb5113caac8a623840 | matched |
| psycopg | 3.3.6 | py3-none-any | a1db9f7148b06a28606767efaca51fa6f9398c5c0a3810519be69d7000bdb631 | matched |
| tzdata | 2026.6 | py2.py3-none-any | 0a10eec6e13ef16b627fabed9a5f2ba61a62b1c67f327305f4e7e412a70b4aec | matched |

The wheelhouse held exactly these three files, nothing else.

## Step results

| Step | Status |
|------|--------|
| Step 1 | pass: wheelhouse hashes matched, psycopg 3.3.6 imports from the site folder, config file limited to one account (icacls lists only the user) |
| Step 2 | session A: stopped, selftest exit nonzero, "PSS/E could not be started: PsseUnavailable: psspy could not be imported (ImportError)"; see "Finding from step 2". Session B (after gap-closure 03-09, `PSSE_ENV_MODULE=psse3604`): pass, 6 PASS 0 FAIL 0 SKIP, exit 0 |
| Step 3 | session B: first run on a converted case, 26 PASS 1 FAIL (`load_flow`, exit 6), see "Finding from session B"; run on an unconverted case, 27 PASS 0 FAIL 0 SKIP, exit 0 |
| Step 4 | session B: pass, 29 PASS 0 FAIL 0 SKIP, exit 0 (`rating_write` and `scale_load` PASS) |
| Step 5 | session B: pass, exit 0, `validation: ok`, 28 of 28 contingencies screened, rows planned 1 run, 4 dispatched capacity, 4 voltage margin, 225 contingency result. Without the Supabase read settings: outcome `fallback`, `city_rating=0 static=4`. With `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` set: outcome `ok`, `city_rating=4 static=0` (live ratings read). Nothing written to the database either time |
| Step 6 | session B, in progress: render pass (exit 0); first registration refused with `The task XML is malformed ... unable to switch the encoding` (HRESULT 0x8004131a), see "Finding from step 6"; with the declaration rewritten to UTF-16 in the string, registration passed, task state Ready, `LastTaskResult 267011` (not yet run), `NextRunTime` 15 seconds past the :15 mark, `NumberOfMissedRuns 0`. Three-hour run check, overlap test and removal pending |
| Step 8 | session B: pass. psycopg 3.3.6 imports from the site folder on Python 3.14; `credcheck` 16 PASS 0 FAIL 0 SKIP, exit 0 (the writer login connects through the session pooler, the REST read works). `credcheck --write-proof` 18 PASS 0 FAIL 0 SKIP, exit 0 (one synthetic run inserted inside a transaction and rolled back; nothing kept) |
| Step 9 | deferred by the user's decision 1 of plan 03-08 (2026-11-09): rolled-back proof only. No real run was written to the live tables. The real proof write waits for the real mapping and case |

## Finding from step 2 (gap-closure item, C-4: no code edited on the laptop)

Importing `psspy` directly, as the launcher does, fails on PSS/E 36.4 with Python 3.14:
`ImportError: DLL load failed while importing psscommon: The specified module could not be found.`

Evidence, all read-only experiments run by hand on the laptop:

1. Appending the PSSPY314 and PSSBIN folders to `sys.path` and importing `psspy`: same ImportError.
2. Additionally registering both folders with `os.add_dll_directory`: same ImportError. So the launcher's current handling (append to the path, register PSSE_BIN_DIR as a DLL folder) is not enough.
3. Appending the PSSPY314 folder, then `import psse3604`, then `import psspy`: `psspy` imported. The PSS/E 36.4 helper `psse3604.py` documents this as the way to set the PSS/E environment before `psspy` from any interpreter ("Use import psse3604 to set PSSE 36.4.x Environment"); it delegates to `psseloc`.

Consequence: the launcher and the Phase 2 adapter (and the probe) must import the version helper (psse3604 for 36.4) before `psspy`. That is a code change for a gap-closure plan (`/gsd-plan-phase 3 --gaps`), not something to edit on the laptop. Steps 2 to 6 wait for it. Open: how the launcher should choose the helper module for other PSS/E versions (the name follows the version, for example psse3604 for 36.4).

Also found: PSS/E 36.4 ships bindings for Python 3.13 and 3.14 (PSSPY313, PSSPY314), not 3.11 as the runbook assumed (U01); the PSS/E program folder is PSSBIN and the bindings folder PSSPY314, both under the install's 36.4 folder.

## Finding from session B (2026-11-09)

Case setup used: the public IEEE 39-bus New England system (39 buses, 34 lines, 12 transformers, all lines in the mapping at 345 kV) and a throwaway mapping marked `placeholder`, four in-service non-transformer lines with a loaded sink bus each. Case, mapping and configuration stayed outside the repository.

1. **A converted case fails the load flow.** A saved case that PSS/E had already converted for dynamics (generators converted, the usual `cnv` kind) loads and passes every other probe row, but `load_flow` FAILS with `fnsl ierr 2: generators are converted`. The probe's message is clear and the exit code is 6. The same system saved unconverted passes all 27 rows. No code change is needed for the smoke case; the practical rule is that the case Power Systems supplies must be an unconverted saved case. Open for the in-person conversation: confirm theirs is unconverted. Whether the job should unconvert a converted case itself is not decided.
2. **A saved case from PSS/E 33 loads directly in 36.4** (the plain 39-bus case was saved by an older release; `load_case` PASS).
3. **`signature:branch_chng_3` PASS** (7 parameters present, one extra parameter not in the table). The expected-risk row did not fail, so `SURFACE` and the adapter need no change.
4. **The dry run reads live ratings** with only the two read settings; no database login is needed. With them absent the read counts as a failed read and every city falls back to the static rating.

## Finding from step 6 (2026-11-09)

The runbook's registration command, `Register-ScheduledTask -Xml` with the file read as a UTF-8 string, fails on this laptop: the template's declaration says `encoding="UTF-8"` while the in-memory string is UTF-16. Rewriting the declaration to `encoding="UTF-16"` in the string (a `-replace` on the first line, no file edited) lets the XML register. The runbook command is updated. Open: whether the renderer should emit a UTF-16 declaration itself (a code change for a later gap-closure plan; the replace works meanwhile). Registration worked for the laptop's own account; the account has administrator rights, so U15 (a standard user can register) is not isolated. `NextRunTime` came back 15 seconds past :15, not exactly :15; to be compared with the actual start times.

First scheduled run: the task started at :15:15 (15:15:15 local), `LastTaskResult 0`, no missed run, so the exit code reaches the scheduler (U18, first of three runs). The log file did not change: a successful dry run logs nothing (the launcher's file handler is attached for every mode, but the only log calls on the run path are a run's own record and warnings), so the runbook now names `LastRunTime` and `LastTaskResult` as the evidence for the dry-run task.

## Claims cleared

Cleared on the real PSS/E 36.4, Python 3.14.0, free Xplore edition:

- U05 `psseinit` is accepted and PSS/E starts (selftest `PSS/E started`, `launch:psseinit` PASS).
- U06 the four output functions accept a redirect (the four `redirected to the log folder` notes, four `launch:` PASS rows).
- U09 the example case's size and usable same-kV lines (34 lines, 12 transformers, 39 buses, `branch_table` and `bus_table` PASS).
- U10 `signature:branch_chng_3` (PASS, see finding 3).
- U11 the combined `scal_2` form (`scale_load` PASS with the write check).
- U31 the job's code runs on the laptop's Python (3.14.0): selftest, probe and dry run complete.
- U23 the session pooler accepts the role as `ROLE.PROJECT-REF` (the `credcheck` role rows PASS).
- U24 the live grants are as the reference DDL says (the grant rows PASS; the owner's own checker also passed 7 of 7).
- U25 the publishable key reads the ratings view and is refused on a write (the three REST rows PASS).
- psycopg 3.3.6 (wheelhouse pin) imports and connects on Python 3.14.0 (the question the guide's decision table left open for 3.14).
- U33 with `PSSE_ENV_MODULE=psse3604`, the launcher's own import of the helper and then `psspy` succeeds (selftest PASS; gap-closure 03-09 confirmed on the laptop).

## Claims still UNVERIFIED

- U07 (`os.add_dll_directory` of the program folder needed or enough) and U08 (importing `psspy` needs no registry write for a standard user): not isolated. `PSSE_BIN_DIR` was set throughout, and the session ran on an account with administrator rights, so neither is separated out. The planned selftest without `PSSE_BIN_DIR` has not been run.
- U12 (PSS/E's own tools list in-service branches with their base kV): not tested. The four lines for the throwaway mapping were read from the public case's text listing, not from PSS/E's branch spreadsheet.
- Step 6 (Task Scheduler with the dry-run task) and everything in plan 03-08 (credential proof, proof write, the real task) are pending. The writes need the `psse_*` tables and the `dlr_psse_writer` login, which do not exist in production yet.

## Open questions

- Licence type and whether a VPN is needed.
- Whether the real case Power Systems supplies is unconverted, and whether it fits within 50 buses (the 39-bus case fits).
- Whether a scheduled task can be registered for the user's own account.
- Whether the laptop sleeps at :15 (S0 low power idle is available).
