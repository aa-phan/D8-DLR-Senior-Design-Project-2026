---
phase: 03-laptop-run-and-handover
plan: 04
subsystem: infra
tags: [entry-script, selftest, probe, hold-lock, gaps, credcheck, launcher, psspy, argparse, mutation-tested]

requires:
  - phase: 03-laptop-run-and-handover
    provides: plan 03-01 launcher core and run lock, 03-02 gaps.run, 03-03 credcheck.run
  - phase: 02-study-on-power-systems-case
    provides: probe.run_probe, format_report, probe_ok, ProbeRow, psse_api.PsseApi, the fake psspy
provides:
  - backend/psse_run_hourly.py, the entry script and the only code that imports psspy (inside load_psspy)
  - launcher.LAUNCH_SURFACE, check_launch_signatures, start_psspy, LAST_START_NOTES
  - launcher modes selftest, probe, hold-lock, gaps and credcheck, and the modes argument of main
  - backend/tests/psse_fake_launch.py (FakeLaunchPsspy), psse_laptop_modes_test.py, psse_entry_test.py
affects: [03-05 Task Scheduler template (reads the parser), 03-06 guide and rehearsal, 03-07 laptop session]

actuals:
  tokens: 19500
  tasks: 3
  commits: 4
plan_head_before: ac245a16dc049e6e9de548b02f76e8767ec8500c
plan_head_after: ef27e46970844e5bd3f02897abb1e82cedceace4

tech-stack:
  added: []
  patterns:
    - "entry script inserts its own folder into sys.path so it works under python -I; psspy imported only inside load_psspy"
    - "launcher modes dict of zero-argument loaders (lazy import of gaps and credcheck), overridable through main(modes=...)"
    - "FakeLaunchPsspy as a subclass in its own helper file, because the Phase 2 fake and its drift test are frozen"
    - "real second-process proofs: two python -I entry-script processes, one holding the lock with hold-lock"

key-files:
  created:
    - backend/psse_run_hourly.py
    - backend/tests/psse_fake_launch.py
    - backend/tests/psse_laptop_modes_test.py
    - backend/tests/psse_entry_test.py
  modified:
    - backend/psse_job/launcher.py

key-decisions:
  - "D-01 to D-08 of the plan implemented as written; selftest and probe print their report on stdout (one stream), usage and lock refusals on stderr"
  - "start_psspy raises PsseUnavailable naming only the exception class; output-function problems are notes (missing, or failed with the class), never fatal"
  - "probe loads the mapping before starting PSS/E, so a bad mapping costs no licence checkout"
  - "read_config and _missing accept a tuple of mode names so credcheck without --skip-rest requires the credcheck and credcheck-rest keys in one error"

patterns-established:
  - "Mutation harness outside the repository (scratchpad mutate_0304.py): exact-text replace, named tests, byte-for-byte restore"

requirements-completed: [SCH-01, TST-02]

duration: about 1 h 25 min (start time not captured at spawn; taken from the last commit of plan 03-03 at 01:06 to the last task commit)
completed: 2026-10-29
status: complete
---

# Phase 3 Plan 04: Entry script and the laptop's own commands Summary

**`python -I backend/psse_run_hourly.py selftest|probe|hold-lock|gaps|credcheck|run --config FILE` is the one command set for the laptop: a selftest that starts a (stub) psspy from the configured folder and prints the Python line, start notes and exactly six rows, a probe whose default report holds no identifier, a hold-lock that makes an overlapping start exit 4 through two real processes, and gaps and credcheck reaching the real modules with parsed arguments. psspy is imported in one place only.**

## Commits

| Commit | Subject |
|--------|---------|
| 1adf4f9 | feat(03-04): tracer - the entry script's selftest finds a stub psspy in the configured folder and reports its version and launch functions |
| 5d805b6 | test(03-04): selftest failures, probe, hold-lock and the entry script's failure modes through real processes |
| f67034a | test(03-04): gaps and credcheck reach the real modules through the launcher with parsed arguments and per-mode required keys |
| ef27e46 | test(03-04): the start failure line stays path-free for an error psspy raises at import |

`commits: 4` is measured (`git rev-list --count ac245a1..ef27e46`); the docs commit of this SUMMARY is not counted. The fourth commit is a test strengthening found by the scrub mutation (Deviation 2).

## Accomplishments

- `backend/psse_run_hourly.py`: sys.path gets the script's own folder (works under `-I`), stdout and stderr are reconfigured to UTF-8 with replacement and a None stream (pythonw) is replaced by a devnull writer, `load_psspy(cfg)` imports psspy (ImportError and OSError become `PsseUnavailable` naming the class) and calls `launcher.start_psspy`, `main` hands both to `launcher.main`.
- `launcher`: `LAUNCH_SURFACE` (five rows, each UNVERIFIED), `check_launch_signatures` (the rules of `probe.check_signatures`, repeated because probe.py is frozen), `start_psspy` (psseinit with the bus limit, then `(2, log file, [0, 0])` on the four output functions, notes in `LAST_START_NOTES`), the `selftest`, `probe`, `hold-lock`, `gaps` and `credcheck` subcommands and runners, `DEFAULT_MODES` and the `modes` argument of `main`, `--seconds` capped at 1 to 600, `--since` and `--until` parsed by `ratings.parse_ts` at argument-parsing time.
- `selftest`: Python version and bitness line, "PSS/E started", the four start notes, then six rows (version and the five launch rows) and a count line over exactly those six; exit 0, or 6 for a FAIL row or a failed start (`PSS/E could not be started: Class: text`, absolute paths replaced).
- `probe`: Phase 2's `run_probe` and `format_report` unchanged; notices for `--write-check` (case changed in memory only, never saved, use a copy) and `--show-identifiers` (must not be pasted); a bad or placeholder mapping is one line `mapping file not usable` and exit 6.
- `hold-lock`: takes the lock, prints `locked`, sleeps in one-second steps, exit 0; a refused lock is exit 4.
- `gaps` and `credcheck`: no lock, no loader call; their integer is the exit code; required keys per mode come from `CONFIG_KEYS` (the pseudo-mode `credcheck-rest` unless `--skip-rest`).

## Test results

| Command | Result |
|---------|--------|
| PG command over psse_laptop_modes_test.py and psse_entry_test.py | 22 passed, 0 skipped (modes 16, entry 6) |
| `-k "overlapping or imports_psspy_only"` | 2 passed |
| psse_contract_test.py | 10 passed |
| psse_contract_test.py + secret_scan_test.py (files staged first) | 13 passed |
| PG command over psse_launcher_test.py and psse_lock_test.py (after the launcher extension) | 34 passed |
| Full `psse_*_test.py` + secret_scan_test.py (wave-end gate, run once by the executor) | 617 passed, 0 skipped, 4 min 25 s |
| Acceptance one-liner (`gaps --since ...Z` parses, aware datetime) | prints ok |
| Own-changes gate (PLAN=03-04), after Tasks 1, 2 and 3 | exit 0 |

Red first, actually run: Task 1's tests failed at collection (no `LAUNCH_SURFACE`, no entry script) before any code. Task 2: 6 of 16 failed (selftest failure paths, probe, hold-lock, the overlapping start) before the probe and hold-lock code. Task 3: the six new tests failed against the Task 2 launcher (see Deviation 3 for how the red run was done), 10 passed.

## Mutation results (plant, see the named test go red, restore, `git diff --quiet` rc 0 each time)

| # | Fault planted | Red tests |
|---|---------------|-----------|
| 1 | `import psspy` at module level of the entry script | test_entry_imports_psspy_only_in_load_psspy |
| 2 | absolute-path scrub skipped in a start failure | test_selftest_failures_exit6 and test_entry_selftest_without_psse_exit6_names_no_path (the latter only after the fourth commit, Deviation 2) |
| 3 | psseinit failure made non-fatal | test_launch_start_failure_is_psse_unavailable |
| 4 | a missing launch function treated as PASS | test_launch_check_signatures_rows |
| 5 | probe passes show_identifiers=True by default | test_probe_mode_hides_identifiers_by_default |
| 6 | selftest removed from LOCK_MODES | test_selftest_takes_the_lock |
| 7 | the 600 second cap removed | test_hold_lock_seconds_are_capped (sleeps are faked there, so the fault shows as a wrong code, never a ten minute hang) |
| 8 | a `--since` without an offset let through | test_modes_since_until_parse_or_exit2 |
| 9 | gaps added to LOCK_MODES | test_modes_gaps_and_credcheck_take_no_lock |
| 10 | probe prints the mapping error text without the flag | test_probe_mode_write_check_and_exit_codes |
| 11 | the write-check notice dropped | test_probe_mode_write_check_and_exit_codes |
| 12 | credcheck REST keys not required without --skip-rest | test_modes_required_keys_per_mode and test_modes_real_credcheck_module_through_the_launcher |
| 13 | run removed from LOCK_MODES | test_entry_overlapping_start_exits_4_through_two_processes |

Mutations 1 to 9 are the plan's list; 10 to 13 are extras. The harness is outside the repository (scratchpad `mutate_0304.py`).

## Lock branch

Native on this machine: **msvcrt** (Windows). The overlapping start (`hold-lock --seconds 20` in one entry process, `run --config` in another, exit 4 within seconds, the holder still alive, lock acquired after the holder is killed) and the second-process refusals ran on that branch. The fcntl branch is covered only by plan 03-01's fake-module test.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `--allow-placeholder` check of plan 03-01 widened to the probe**
- **Found during:** Task 2 (the plan gives `probe` an `--allow-placeholder` option, but `_main` refused the flag for every mode but `dry-run`)
- **Fix:** `_PLACEHOLDER_MODES = {dry-run, probe}`; the refusal text names both. A real run still refuses the flag; plan 03-01's `test_exit2_allow_placeholder_needs_dry_run` (which checks only that `--allow-placeholder` is in the message) stays green (34 passed in the launcher and lock files).
- **Files modified:** backend/psse_job/launcher.py
- **Commit:** 5d805b6

**2. [Rule 1 - Test sensitivity] the entry test could not see a missing path scrub**
- **Found during:** mutation 2. The real `load_psspy` turns ImportError into a class name only, so removing the scrub left `test_entry_selftest_without_psse_exit6_names_no_path` green.
- **Fix:** the test gained a second scenario: a stub `psspy.py` that raises a RuntimeError naming its own file and a licence path at import (a type `load_psspy` does not convert). The start failure line must show `<path>` and no tmp folder. Re-run: both named tests go red.
- **Commit:** ef27e46

**3. [Process] Task 3 code was written before its tests were seen red**
- The launcher part of Task 3 was written first by mistake. To keep red-first honest, the Task 3 tests were run against the committed Task 2 launcher (`git show HEAD:` copy placed in the working file, then the Task 3 file restored and checked with `cmp`): 6 red, 10 green. Then the Task 3 launcher was restored and the tests went green.

### Small notes

- `read_config` and `_missing` accept a tuple of mode names (plan 03-01's functions); `read_config(path)` and `read_config(path, "run")` behave as before.
- The path scrub (plan 03-01's heuristic) swallows text between two paths when only a space or a slash separates them, and `redact` drops a semicolon in the message; the tests use two paths separated by a semicolon and count `<path>` markers. Safe direction (it removes more than needed), no leak.
- `redact` is applied per printed line; the probe and selftest reports go line by line through `_say` so a long report is not cut at `ERROR_MAX_CHARS`.
- One test-file append used a shell heredoc (it worked in this shell); every other file was written with Write or Edit.
- No `STATE.md`, `ROADMAP.md` or `REQUIREMENTS.md` edit, as instructed; the orchestrator marks SCH-01 and TST-02 after reading this SUMMARY.

## Authentication gates

None.

## Known Stubs

None. The stub `psspy.py` used by the entry tests is written into pytest tmp folders and never committed.

## Threat Flags

None beyond the plan's register: T-03-42 (path-free start failures: mutations 2 and the two path tests), T-03-43 (`--show-identifiers` explicit with a notice: mutation 5), T-03-44 (write check never saves, case sha256 unchanged: asserted on the fake), T-03-45 (hold-lock capped and released: mutation 7 and the killed-holder check).

## Honest scope: UNVERIFIED, handed to plan 03-07 (runbook step 2 unless noted)

Proved here with a stub psspy module and `FakeLaunchPsspy` only. Not proved:

- That real psspy has `psseinit`, `report_output`, `progress_output`, `alert_output` and `prompt_output` with the parameter names `buses`, `islct`, `filarg`, `options` (research A2 and A3 are forum and vendor-blog sources). `selftest` prints a launch row for each; a FAIL there is a gap-closure item, not a laptop problem to improvise around.
- That `(2, log file, [0, 0])` really moves the console output into a file, and that `psseinit` returning a non-zero error code is not hidden (the loader treats only an exception as failure; a non-zero return value is ignored).
- That `os.add_dll_directory` (registered by `launcher.add_search_dirs`, which `main` calls before the loader) is needed or enough, and that `PSSE_PSSPY_DIR` is the right folder (research A4).
- That `import psspy` works from a folder appended to the end of sys.path on the laptop's Python (3.7 to 3.11); this code never ran on a Python older than 3.12 except through the 3.7 syntax gate.
- The probe on a real case and mapping (runbook steps 3 and 4), including the write check on a copy.
- The real Task Scheduler showing `hold-lock` blocking a start with exit 4 (runbook step 6); the two-process proof ran on this machine's msvcrt lock.
- The questions carried forward: which PSS/E version, Python and licence the laptop has (`selftest` reads it off), and whether a `psseinit` bus count of 20000 (`PSSE_MAX_BUSES`) is accepted by the licence and large enough for the real case.

## Notes for plans 03-05 to 03-07

- `launcher.build_parser()` now has subcommands `run`, `selftest`, `probe`, `hold-lock`, `gaps`, `credcheck`; every one keeps `--config` required. `hold-lock --seconds` default 60, range 1 to 600; `gaps --since/--until` need an ISO time with an offset.
- `launcher.main(argv, loader, out=None, err=None, clock=None, connect=None, fetch=None, modes=None)`; `launcher.DEFAULT_MODES`, `launcher.RUNNERS` and `launcher.LOCK_MODES` (run, dry-run, selftest, probe, hold-lock).
- Output lines the guide can quote: selftest `Python 3.12.10, 64-bit`, `PSS/E started`, `<function>: redirected to the log folder`, rows `PASS  version  PSS/E 35.6.0`, count line `6 PASS, 0 FAIL, 0 SKIP`; hold-lock `locked`; a refused lock `another instance holds the run lock; this run is skipped` on stderr with exit 4.
- The entry script writes PSS/E's redirected output to `<PSSE_LOG_DIR>/psse_output.log`.

## Self-Check: PASSED

- Files found: backend/psse_run_hourly.py, backend/psse_job/launcher.py, backend/tests/psse_fake_launch.py, backend/tests/psse_laptop_modes_test.py, backend/tests/psse_entry_test.py.
- Commits found as ancestors of HEAD: 1adf4f9, 5d805b6, f67034a, ef27e46.
- No postgres process left running after the last test and mutation runs (tasklist count 0).
