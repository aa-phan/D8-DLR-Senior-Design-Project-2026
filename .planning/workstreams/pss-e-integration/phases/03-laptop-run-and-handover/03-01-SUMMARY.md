---
phase: 03-laptop-run-and-handover
plan: 01
subsystem: infra
tags: [launcher, run-lock, msvcrt, fcntl, argparse, exit-codes, dry-run, secret-hygiene, postgres]

requires:
  - phase: 01-writer-and-contract
    provides: job.run_once and its exit codes, writer, redaction, run_record
  - phase: 02-study-on-power-systems-case
    provides: study.prepare_run, study.failing_study, the fake psspy and the local-Postgres harness
provides:
  - psse_job.lock.RunLock, a non-blocking OS byte lock released by the OS on exit
  - psse_job.launcher, the psspy-free launcher core (run and run --dry-run, config file, exit codes 0 to 7)
  - the Phase 1 import allow-list extended by argparse, fcntl and msvcrt (own commit)
affects: [03-04 launcher modes and entry script, 03-05 Task Scheduler template, 03-06 guide, 03-07 laptop session]

actuals:
  tokens: 19700
  tasks: 3
  commits: 4
plan_head_before: cc6c59a2ff7050acfe92ae1eb018728b02b04884
plan_head_after: 039b929e62eb250fe407291ea67ace4d0e172ca8

tech-stack:
  added: []
  patterns:
    - "injected psspy loader (psspy never imported in psse_job)"
    - "configuration is one dict read from a file; the process environment is never a setting"
    - "module-level RUNNERS table keyed by mode, LOCK_MODES set, Deps namedtuple"
    - "redacting logging filter on the handler plus explicit redact(..., []) for every printed line"

key-files:
  created:
    - backend/psse_job/lock.py
    - backend/psse_job/launcher.py
    - backend/tests/psse_lock_test.py
    - backend/tests/psse_launcher_test.py
  modified:
    - backend/tests/psse_contract_test.py

key-decisions:
  - "D-01 to D-11 of the plan implemented as written (config file only, one command with subcommands, exit codes 0 to 7, lock before PSS/E, TCP preflight, load_case failure recorded, dry-run mirrors run_once, sslmode rule, --allow-placeholder only with --dry-run, search dirs appended, case and mapping existence not checked by the reader)"
  - "read_config gained an optional mode argument so required-key problems are reported together with the other problems in one ConfigError"
  - "the summary line is exactly: run_id=<id> outcome=<o> status=<s> exit=<n>"

patterns-established:
  - "Second-process lock proofs: sys.executable -I -B -c with the backend folder inserted by the child, 30 s timeout, killed in a finally block"
  - "Mutation harness outside the repository that replaces exact text, runs the named tests and restores the original bytes"

requirements-completed: [SCH-01, TST-02]

duration: 30min
completed: 2026-10-29
status: complete
---

# Phase 3 Plan 01: Launcher core and run lock Summary

**A psspy-free launcher (`main(["run", "--config", FILE], loader)`) with an OS-released run lock, a config file as the only configuration, documented exit codes 0 to 7, a TCP preflight, recorded load_case failures and a counts-only dry-run, proved on the fake psspy and a local Postgres.**

## Performance

- **Duration:** about 30 min (start time was not captured at spawn; taken from the commit times, 23:55 to 00:25)
- **Tasks:** 3 of 3, no checkpoint reached (context use was well below the 60 percent stop point after Task 2)
- **Files:** 4 created, 1 modified (the allow-list line set only)

## Commits

| Commit | Subject |
|--------|---------|
| 74bb63f | test(03-01): allow argparse, fcntl and msvcrt in the Phase 1 import allow-list (touches only backend/tests/psse_contract_test.py) |
| 217fd64 | feat(03-01): tracer - a config file through the lock, the launcher and the fake psspy into local Postgres |
| 346a102 | test(03-01): the exit-code matrix, the lock in depth and secret hygiene |
| 039b929 | feat(03-01): dry-run equal to a real run up to the connect, and the append-only search-folder rule |

`commits: 4` is measured (`git rev-list --count cc6c59a..039b929`); the docs commit of this SUMMARY is not counted.

## Accomplishments

- `lock.RunLock`: a non-blocking lock on byte 0 of an empty file (never a PID file), msvcrt on Windows and fcntl elsewhere, each imported inside a function. The operating system releases it when the holder returns, raises or is killed.
- `launcher`: `ConfigError`, `ConfigKey`, the 13 `CONFIG_KEYS` with `required_for` as data, `read_config`, `EXIT_CODES` (all eight codes), `build_parser`, `RUNNERS`, `Deps`, `PsseUnavailable`, `add_search_dirs`, `main` (never raises except KeyboardInterrupt).
- One run from a config file writes 1 + 4 + 4 + 10 rows into local Postgres with every completeness check ok, through the lock, the injected fake loader, `study.prepare_run` and Phase 1's unchanged `job.run_once`.
- Failures before or around the study are never silent: bad configuration is exit 2 (keys and line numbers only), an unreachable database is exit 3 before PSS/E starts, a loader that raises is one recorded failed run at stage load_case (class name and a path-scrubbed text, case sha256 set, mapping sha256 NULL), a held lock is exit 4, an unexpected error is exit 7 with a redacted log line.
- `run --dry-run` runs the real study, `validate_results`, `build_run_record` and `result_rows`, never preflights or connects, and prints counts only; the counts equal a real run's (differential test).

## Test results

| Command | Result |
|---------|--------|
| PG command over psse_lock_test.py and psse_launcher_test.py | 34 passed, 0 skipped (lock 8, launcher 26) |
| PG command, `-k "tracer or dll"` (Task 1 gate) | 4 passed |
| PG command, `-k "exit4 or hygiene"` | 4 passed |
| psse_contract_test.py + secret_scan_test.py (files staged first) | 13 passed |
| EXIT_CODES / CONFIG_KEYS acceptance one-liner | prints ok |
| Own-changes gate (PLAN=03-01), after Task 1, 2 and 3 | exit 0 |

Red first, actually run: Task 1 tests failed at import (no `launcher` or `lock` module). Task 2: 8 of the new tests failed against the Task 1 launcher (relative paths, bad numbers, sslmode, allow-placeholder, preflight, the two load_case recordings, handler/preflight log), 13 passed. Task 3: the four dry-run tests failed ("mode not available", exit 2). `test_paths_dirs_appended_never_prepended` passed on first run because the append-only rule was already in Task 1's `add_search_dirs`; it is guarded by mutation 9 below.

## Mutation results (plant, see the named test go red, restore, `git diff --quiet` rc 0 each time)

| # | Fault planted | Test that went red |
|---|---------------|--------------------|
| 1 | `RunLock.__enter__` always reports acquired | test_tracer_lock_second_process_refused_then_acquires_after_release and test_exit4_second_instance_skipped_writes_nothing |
| 2 | lock released before `run_once` runs | test_exit4_lock_held_during_start_and_write |
| 3 | preflight skipped | test_exit3_unreachable_database_never_starts_psspy |
| 4 | a configuration problem message includes the line text | test_exit2_malformed_lines_name_no_value |
| 5 | redacting log filter dropped | test_hygiene_secrets_never_reach_output_or_log (confirmed: the unredacted log record is the failure) |
| 6 | database URL read from os.environ when present | test_tracer_environment_is_not_configuration |
| 7 | path scrub dropped | test_failure_psse_unavailable_recorded_as_load_case |
| 8 | connect called inside the dry run | test_dry_run_never_connects_and_prints_counts_only |
| 9 | prepend instead of append in `add_search_dirs` | test_paths_dirs_appended_never_prepended |
| 10 | sslmode rule removed | test_exit2_sslmode_rule |
| 11 | `--allow-placeholder` allowed on a real run (check removed and flag passed to prepare_run) | test_exit2_allow_placeholder_needs_dry_run |

The harness lives outside the repository (scratchpad `mutate_0301.py`); it replaces exact text, runs the named tests with Postgres and writes the original bytes back.

## Lock branches

- Native on this machine: **msvcrt** (Windows). Proved against a real second Python process (refused while held, acquired after release, released when the holder is killed, released after an exception) and against a second handle in the same process (refused).
- Faked: **fcntl**, through a fake module and a forced `_backend_name`. This proves the call shape (LOCK_EX | LOCK_NB, BlockingIOError means held, LOCK_UN on exit) and nothing about a POSIX kernel. The msvcrt call shape (one byte, LK_NBLCK, position 0) is also checked through a fake.

## Deviations from Plan

None that change behaviour or scope. Small notes:

1. **[Plan wording] `read_config(path, mode=None)`**: the interface block gives `read_config(path)`. An optional `mode` argument was added so that missing required keys are reported in the same ConfigError as the other problems; `read_config(path)` still works as specified.
2. **[Test config, not code] `test_failure_unexpected_error_is_exit7`** sets `PSSE_PREFLIGHT=0`: once Task 2 added the preflight, the default local URL (port 5432, nothing listening) made the run exit 3 before the injected failure point. The test target is `launcher._prepare`.
3. **Cross-test import**: `psse_launcher_test.py` imports `Holder` and `probe` from `psse_lock_test.py` so one second-process helper serves both files.
4. **Task split of the launcher**: Task 1's launcher implemented the Task 1 text (format-level config reading, log filter, lock, loader, run_once, exit 7, search dirs); value rules, the preflight, `--allow-placeholder` refusal and the load_case recording came in Task 2 after their tests were seen red.

No Phase 1 or Phase 2 module or test helper changed; `psse_contract_test.py` changed only by the three allow-list names and their comments, in its own commit. No package was installed; psspy is not imported anywhere.

## Things the next plans rely on (names and shapes)

- `launcher.RUNNERS` (mode to `runner(args, cfg, deps)`), `launcher.LOCK_MODES` (frozenset; 03-04 adds selftest, probe, hold-lock), `launcher.Deps(out, err, psspy_loader, clock, connect, fetch, modes)` with `modes` None until 03-04, `launcher.build_parser()` with `dest="mode"` and the `run` subparser attributes `config`, `dry_run`, `allow_placeholder`. `main` has no `modes` parameter yet (03-04 adds it).
- Helpers 03-04 can reuse: `_say(stream, text, secrets)` (always pass an explicit list: `redact(text, None)` reads the process environment), `_prepare(deps, cfg, allow_placeholder)`, `_scrub_paths`, `_db_address(url)`, `_attach_log`/`_detach_log`, `_mode_of(args)`.
- The summary line of a real run is exactly `run_id=<id> outcome=<o> status=<s> exit=<n>` on stdout; a dry run prints a report whose first line is `dry run: nothing was written to the database`.
- During a `main` call the `psse_job` logger gets one rotating file handler (`<PSSE_LOG_DIR>/psse_job.log`), level INFO and `propagate=False`; all three are restored afterwards.
- The reader does not require `PSSE_PREFLIGHT`, `PSSE_MAX_BUSES`, `PSSE_LOG_DIR` or `PSSE_LOCK_PATH`; D-01 defaults are filled in.

## Known limitations (stated, not hidden)

- The path scrub (`launcher._PATH_RE`) is a heuristic: a drive-path segment never crosses a colon, semicolon or comma, and the final file name stops at the first space. A folder name containing a comma or a file name containing a space can leave a fragment of the path in the recorded message. Case and mapping paths themselves are never printed by the launcher.
- The preflight's 5 second timeout bounds the TCP connect only, not name resolution (D-05).
- libpq's own PG* environment variables are not isolated (D-01); the guide (plan 03-06) must say so.
- The tests ran on the repository's Python 3.12; Python 3.7 is covered by the syntax gate only, not by running the launcher on a 3.7 interpreter.

## UNVERIFIED, handed to plan 03-07 (the laptop session)

- That the msvcrt lock behaves the same on the laptop's Python and filesystem (runbook step 6), including a killed holder and a second Task Scheduler start.
- That Task Scheduler passes the launcher's exit code through and that `IgnoreNew` prevents overlap (plans 03-05 and 03-07).
- That `os.add_dll_directory` is needed or enough for PSS/E's DLLs, and that `PSSE_PSSPY_DIR` is the right folder.
- Anything about real `psspy`, the licence, the real case and the PSS/E bus limit (the default `PSSE_MAX_BUSES` is 20000).
- Questions carried to the guide's question section (plan 03-06): (1) which PSS/E version, edition, licence type and Python the laptop has, and what bus count the licence allows; (2) whether the stored `case_id` (the case file's base name) may appear in a private table or the file should be renamed first.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register: the TCP preflight (T-03-02 context) and the local log file are the surfaces the plan already names.

## Self-Check: PASSED

- Files found: backend/psse_job/lock.py, backend/psse_job/launcher.py, backend/tests/psse_lock_test.py, backend/tests/psse_launcher_test.py, backend/tests/psse_contract_test.py.
- Commits found as ancestors of HEAD: 74bb63f, 217fd64, 346a102, 039b929.
- No postgres process left running after the last test and mutation runs.
