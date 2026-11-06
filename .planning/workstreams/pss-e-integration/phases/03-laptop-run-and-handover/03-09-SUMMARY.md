---
phase: 03-laptop-run-and-handover
plan: 09
subsystem: psse-launcher
tags: [psse, launcher, environment-helper, gap-closure, laptop]
requires: [03-01, 03-04, 03-06]
provides:
  - "optional config key PSSE_ENV_MODULE (kind module) and launcher.is_plain_module_name"
  - "load_psspy imports the configured PSS/E environment helper before psspy"
  - "gated fake psspy folder (write_env_gated_psspy_folder) that reproduces the laptop's DLL-load failure"
  - "guide and runbook carry the key; U01 corrected, U07 observation, U33 and U34 registered"
affects: [03-07, 03-08]
tech-stack:
  added: []
  patterns: ["one dynamic import in the entry script, name from configuration only, class-only failure lines"]
key-files:
  created: []
  modified:
    - backend/psse_job/launcher.py
    - backend/psse_run_hourly.py
    - backend/tests/psse_fake_launch.py
    - backend/tests/psse_entry_test.py
    - backend/tests/psse_launcher_test.py
    - backend/tests/psse_setup_doc_test.py
    - docs/data-science/decisions/psse_laptop_setup.md
    - docs/data-science/decisions/psse_laptop_runbook.md
decisions:
  - "PSSE_ENV_MODULE: optional, no default, plain module name rule, no required psse prefix (a prefix would guess other versions' names, U34)"
  - "SystemExit from the helper import is caught and reported by class name only (plan-check addendum)"
metrics:
  duration: "about 1 hour of wall time including a 6 minute full-glob run"
  completed: 2026-11-05
status: complete
actuals:
  tokens: 8650
  tasks: 3
  commits: 3
plan_head_before: 270831398c9542d1ae18f2bfb6ae5655ea0fc549
plan_head_after: 9aafe1ad6c1d915766d1b9ffa1ca15fae1a95b5f
requirements: [TST-02, SCH-01]
---

# Phase 3 Plan 09: PSSE_ENV_MODULE gap closure Summary

The launcher can now import PSS/E's environment helper (named only by the new optional key `PSSE_ENV_MODULE`, `psse3604` on 36.4) after the search folders are appended and before `psspy`, which is what session A showed real `psspy` needs on PSS/E 36.4 with Python 3.14; with the key unset every existing proof is unchanged.

`commits: 3` counts the three code and documentation commits made before this SUMMARY was written (measured from the plan ledger); the SUMMARY's own commit comes after.

## Resume point (what the user does next)

1. On the laptop, pull the repository copy.
2. Add the line `PSSE_ENV_MODULE=psse3604` to the existing configuration file (it is the whole configuration; keep its restricted access).
3. Resume plan 03-07 at runbook step 2 (`selftest`); steps 3 to 6 follow as written. Step 1 is recorded as passed and is not repeated. If `selftest` still stops, its failure line now says which import failed: `the module named by PSSE_ENV_MODULE could not be imported (<Class>)` means the name is wrong or the module is not in the configured `psspy` folder; `psspy could not be imported (<Class>)` after the helper succeeded is a new finding for another gap-closure plan.

This plan did not touch the laptop, `03-07-LAPTOP-RECORD.md` or `03-07-PLAN.md`.

## Success criteria

- Met (Mac-proven): the laptop's failure is reproduced on a gated fake folder through a real `-I` process (exit 6, `psspy could not be imported (ImportError)`, pointer `PSSE_ENV_MODULE is not set`) and closed by the key (exit 0, six PASS rows, import log `helper` then `psspy`); a malformed name is exit 2 before the lock and before any import.
- Met: the helper's name is never in code (AST test: the one `import_module` argument is not a constant), is validated at configuration reading and again in `load_psspy`, is imported once between the search-folder appends and `import psspy`, and a failure names only the class (checked for a missing module, a RuntimeError carrying a path and a licence file, a no-op helper and `sys.exit()`).
- Met: the guide's table (14 keys, order of `CONFIG_KEYS`), both example blocks, the prerequisites rows, the troubleshooting rows, runbook steps 0 to 2 and the register carry the key; U01 corrected, U07 observation added, U33 and U34 new; no tag was removed.
- Not closed by design: TST-02 and SCH-01 are supported, not closed. U33 (the launcher's own helper import works on the laptop) is cleared only by plan 03-07 step 2.
- No identifier entered git (added lines checked for user, drive-path and download-folder text; the doc and secret-scan gates pass).

## Files changed

See `key-files`. `psse_job/launcher.py` gained the key row, `_MODULE_NAME_RE`, `is_plain_module_name`, the `module` branch of `_value_problems` and two comment updates (no behaviour change in `add_search_dirs`). `psse_run_hourly.py` gained `import importlib` and the helper import in `load_psspy`. `importlib` was not added to the `psse_job` allow-list; the contract gate is unchanged and green.

## Test counts

| Scope | Before | After |
|---|---|---|
| `psse_entry_test.py` | 6 | 12 |
| `psse_launcher_test.py` | 26 | 28 |
| `psse_setup_doc_test.py` | 15 | 17 |
| `psse_laptop_modes_test.py`, `psse_contract_test.py`, `psse_rehearsal_test.py` | 16, 10, 2 | unchanged |
| Full glob `psse_*_test.py` and `secret_scan_test.py` (wave-end gate) | 646 collected | 656 passed, 0 skipped |

The plan expected 655: it counted 5 new entry tests and the addendum's sys.exit test is a sixth (`test_entry_helper_that_exits_is_reported_by_class_only`).

The Task 1 verify commands passed at the Task 1 commit (entry 8 passed, modes plus launcher 42 passed, contract 10 passed). The guide's key-table gate was red between the Task 1 and Task 2 commits by design (the guide had 13 rows against 14 keys) and is green from the Task 2 commit.

## Mutation results

Each fault was planted by exact-text replacement from a scratch harness outside the repository, the named tests were run, and the file was restored byte for byte (a path-limited `git diff --quiet` passed for each file after each restore).

| Mutation | Result |
|---|---|
| M1 remove the helper import | red: tracer |
| M2 import the helper after psspy | red: tracer, AST test |
| M3 default helper name when unset | red: tracer |
| M4a skip the module branch of `_value_problems` | red: key validation test, entry refusal test |
| M4b remove the re-check in `load_psspy` | red: re-check/order test |
| M5 allow a dot in the name rule | red: name rule, entry refusal test, tracer |
| M6 `\Z` replaced by `$` | red: name rule |
| M7 print the helper exception text | red: class-only failures test |
| M8 catch only ImportError | red: class-only failures test, sys.exit test |
| M9 module-level hard-coded import | red: no-import-time test |
| M10 `load_psspy` appends the folders itself | red: re-check/order test |
| M11 drop the `PSSE_ENV_MODULE is not set` pointer | red: tracer |
| M12a delete the guide table row | red: key-table gate |
| M12b delete the runbook step 1 line | red: example-block gate |
| M12c restore the stale 36.x claim | red: claims gate |
| M12d delete the U33 register row | red: tag/register gate |

Every planted fault turned its named test red.

## Deviations from Plan

**1. [Addendum, Rule 2] SystemExit handling.** The helper import is caught with `except (Exception, SystemExit)` and reports the class only; one extra test (`test_entry_helper_that_exits_is_reported_by_class_only`) uses a fake helper that calls `sys.exit()`. This is the user-approved plan-check addendum, hence entry 12 and full glob 656 rather than 11 and 655. It is also mutation-checked (M8).

**2. [Process] Doc tests not run red before the doc edits.** Task 2 asked for the three doc tests to be run red before editing the documents. They were written first but the documents were edited before the first run. Their sensitivity is shown instead by M12a to M12d (each doc gate goes red when its document change is undone).

**3. [Scope] No other deviation.** `launcher.CONFIG_KEYS` meaning text and the guide's meaning cell differ slightly in wording (the guide's table gate checks only that a meaning is present).

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model: the new dynamic import (T-03-47 to T-03-49) is mitigated by the name rule checked twice and the class-only failure lines, each with a named test.

## UNVERIFIED items handed to plan 03-07

- U33 (new, step 2): the launcher's own helper import makes real `psspy` load on the laptop.
- U07 (reworded, step 2): whether the DLL folder (`PSSE_BIN_DIR`) is still needed once the helper has run; run `selftest` with and without it.
- U34 (new, step 0): other PSS/E versions' helper name.
- U01 now carries the observed fact that 36.4 ships Python 3.13 and 3.14; its 35.x and 34.x parts keep the tag.

Left to plan 03-07 task 6: the guide's interpreter and psycopg decision table still stops at Python 3.12 although the laptop runs 3.14.

## Self-Check: PASSED

Files named above exist; commits `7ef1b50`, `811eda4` and `9aafe1a` are on the branch; the own-changes gate exits 0; no `(03-09)` commit touches 03-07's plan or record.
