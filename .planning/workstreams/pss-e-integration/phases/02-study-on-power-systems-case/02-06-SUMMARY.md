---
phase: 02-study-on-power-systems-case
plan: 06
subsystem: psse-job-study-assembly
tags: [pss-e, study-assembly, prepare-run, write-back, local-postgres, golden-call-surface, stdlib, python37]
requires:
  - phase: 01
    provides: "job.run_once, writer.write_run and record_failure, run_record.validate_results, case_label, file_sha256 and finite, contract.StudyResults and StudyFailed, the local Postgres harness"
  - phase: 02
    provides: "plan 02-01 load_mapping and MappingError; 02-02 PsseApi, SURFACE and the fake psspy; 02-03 prepare_base, cleanup_base, Budget; 02-04 contingency.screen; 02-05 margin.city_margin and dispatch.build_dispatch_row"
provides:
  - "psse_job.study: PreparedRun, failing_study, json_safe, make_study, prepare_run (the one entry point the Phase 3 launcher calls)"
  - "backend/tests/psse_study_job_test.py: 13 Postgres write-back tests (TST-01)"
  - "backend/tests/psse_study_test.py: 11 whole-study tests without a database"
  - "backend/tests/data/psse_call_surface.json: golden ordered call surface of the happy path (19 entries)"
affects: [02-07]
tech-stack:
  added: []
  patterns:
    - "one study per call: a new Budget, a new PsseApi and a fresh case() load every time, cleanup_base in a finally"
    - "a mapping that cannot be loaded becomes a study that raises StudyFailed('mapping'), so run_once records the failure and the mapping hash stays NULL"
    - "golden call-surface file regenerated only with PSSE_UPDATE_CALL_SURFACE=1 and reviewed as a diff"
key-files:
  created:
    - backend/tests/psse_study_job_test.py
    - backend/tests/data/psse_call_surface.json
  modified:
    - backend/psse_job/study.py
    - backend/tests/psse_study_test.py
key-decisions:
  - "prepare_run stores the MappingError text in PreparedRun.mapping_error and the study message is 'mapping file not usable: <text>'; the text names the mapping file by base name only (mapping.py), so no directory reaches the stored error"
  - "make_study turns a ValueError from build_dispatch_row into StudyFailed('dispatch', '<city>: <message>'); CaseProtected and every other exception pass through and are recorded by run_once as stage internal"
  - "json_safe is applied to the details of every dispatch, margin and contingency row at the end of make_study, not inside the producing modules"
  - "The golden file records only keyword names, and the study mostly calls positionally, so most entries have an empty keyword list; that is what the file pins (function order and the keyword shape of the calls that use keywords)"
requirements-completed: [IN-02, STU-01, STU-02, STU-03, STU-04, TST-01]
duration: about 1h 15m
completed: 2026-10-28
status: complete
commits: 3
plan_head_before: 7686d072fed2065672550b05f65796cec64263ea
plan_head_after: 7ca938822b4f639417b8583a0cc8b2068ac4c4e7
actuals:
  tokens: 10100
  tasks: 3
  commits: 3
---

# Phase 2 Plan 06: Whole-study assembly and write-back proofs Summary

**`study.prepare_run(psspy, case_path, mapping_path)` gives the launcher the study, the case label and both hashes; `make_study` runs base, N-1, margins and dispatch into `StudyResults`, and Phase 1's unchanged `run_once` writes it to local Postgres 18.6 as 1 + 4 + 4 + 10 rows (or one failed row and nothing else for each of the seven failure stages), with the happy path's psspy call order pinned in a reviewed golden file.**

## Accomplishments
- `study.make_study(psspy_module, case_path, mapping, clock=None)`: per call a new `Budget`, `prepare_base` (a new `PsseApi`), then `contingency.screen`, `margin.city_margin` for the four cities and `dispatch.build_dispatch_row` with the margin's `voltage_limit_mva`, its `details` from `dispatch_details` and `bounded_by` always passed (tripwire on). `ValueError` from it becomes `StudyFailed("dispatch", "<city>: ...")`. `cleanup_base` runs in a `finally`; every row's `details` goes through `json_safe`. `n_contingencies` comes from `ContingencyResult`.
- `study.prepare_run(psspy_module, case_path, mapping_path, allow_placeholder=False, clock=None) -> PreparedRun(study, case_id, case_sha256, mapping_sha256, mapping_error)`. A refused placeholder or an unreadable, unparsable or invalid mapping returns `failing_study("mapping", ...)` with `mapping_sha256` None; a mapping that loads keeps its hash even when it does not match the case.
- `failing_study` and `json_safe` (NaN and infinity to None, datetimes and dates to ISO text, dict keys to text, tuples to lists, other objects to text).
- Tracer and write-back (Task 1 and 2), through `run_once` with the real writer and local Postgres 18.6: a provisional-rows run is `fallback`/`written`/exit 0 with 1 + 4 + 4 + 10 rows, `n_contingencies` 16, `n_contingencies_with_results` 7, rate set RATEA, version 35.6.0, AUSTIN `ratings_used` 345.0 kV and 2181.1 MVA, AUSTIN `voltage_stability` and EL_PASO `dlr_rating`, margin method `pv_curve` on all four, `thermal_overload` and `voltage_low` rows present, every `CHECKS_SQL` row ok, the case file's sha256 unchanged and no saved temp file left.
- Seven failure cases each leave one `failed` run row, zero result rows, exit 1, status `failure_recorded`, the right stage and all checks ok: mapped branch missing (`mapping`, stored mapping hash equals the copy's hash, no `branch_chng_3`, `fnsl` or `save` seen), load flow solved=1 (`load_flow`, "iteration limit exceeded", no save), refused placeholder and nonexistent mapping (`mapping`, mapping hash NULL, no psspy call at all), unloadable case (`load_case`, only the base name in the error), `contingency.max` 3 (`contingency`), frozen-load solver (`voltage_margin`, "does not load the mapped branches"), fresh rows with `transfer.extra_steps` 0 (`voltage_margin`, names `transfer.max_mw`, `transfer.extra_steps` and EL_PASO).
- Four successful variants, every check ok: fresh rows (`ok`, `city_rating` with the row's valid and computed times, 1.1 x static amps, EL_PASO `applied_mva` 867.65 dispatched in full as `dlr_rating`, margin details `bounded_by` `dlr_rating` and `extended_past_cap` true, AUSTIN still `voltage_stability`); provisional rows (static_fallback/provisional on all four dispatch rows and `ratings_used`); a fetch that raises (`read_failed` on all four, `ratings_read_error` stored, study still written); 200 MW sink loads (1 + 4 + 4 + 0, 16 contingencies, 0 with results, EL_PASO `dlr_rating` at 788.8 MVA after extending past the cap).
- Task 3, no database: the results validate, calls stay inside `SURFACE` (names and keywords), `case()` gets the case path once per run and `save()` never targets it, a second call of the same callable reloads the case and gives equal results, a new `PsseApi` per run, no temp directory survives success or a `voltage_margin` failure, hostile `details` (NaN, infinity, datetime, tuple and int keys) come out JSON-safe, a `ValueError` from `build_dispatch_row` is stage `dispatch`, `prepare_run` labels and hashes, a bad mapping gives a stage-mapping study with no psspy call. The golden file has 19 entries; every name is a `SURFACE` name and the order follows the stages (version and sentinels, index reads, rating reads and writes, base solve and indicators, loading read, save, then `bsys` and `scal_2` from the margin loop).

## Task Commits
1. Task 1 (tracer): `0882abd` feat(02-06): tracer - prepare_run with the fake psspy through run_once into local Postgres, one complete fallback run
2. Task 2: `230b461` test(02-06): every study failure is one recorded failed run with no results, every successful variant complete
3. Task 3: `7ca9388` test(02-06): the whole study without a database - SURFACE-only calls, golden call surface, case integrity, temp cleanup, JSON-safe details

## Verification
- Tracer: `psse_study_job_test.py -k tracer` with the Postgres prefix: 1 passed, no skip; `psse_contract_test.py`: 10 passed.
- Task 2: `-k "recorded or written"`: 12 passed, no skip; `-k "mapping_missing_branch or non_converging_load_flow"`: 2 passed; `psse_study_job_test.py psse_job_test.py psse_writer_test.py`: 46 passed, no skip.
- Task 3: `psse_study_test.py -k "full or call_surface or prepare_run or json_safe"` without `PSSE_UPDATE_CALL_SURFACE`: 11 passed; the seven non-database PSS/E files: 257 passed; the golden-file check prints 19.
- Full phase gate (`backend/tests/psse_*_test.py backend/tests/secret_scan_test.py` with the Postgres prefix): 503 passed, no skipped, no failed. No postgres process was left running (checked after every Postgres run).
- Own-changes gates (Phase 1 modules, DDL, config, migrations, production-pipeline plans) exit 0 before each commit; none of those paths appear in this plan's commits.
- Red first: the tracer failed with `AttributeError: module 'psse_job.study' has no attribute 'prepare_run'` before the implementation. Task 2's tests describe behaviour the Task 1 implementation already provided, so they passed on first run; their sensitivity is shown by the mutation checks below. In Task 3 the golden test was run before the file existed (FileNotFoundError) and `test_full_study_new_adapter_per_run` first failed on a bug in the test (recursion through the monkeypatched class), fixed in the test.
- Mutation checks (harness `scratchpad/mutate_0206.py`, run with `-B`; each plant restored byte for byte, `git diff` empty on `backend/` afterwards; control run green): drop `cleanup_base` (test_full_study_cleans_temp_dir_on_success_and_failure red); reuse one `PsseApi` (test_full_study_new_adapter_per_run red); skip `json_safe` (test_full_study_details_are_json_safe red on NaN); mapping hash for a refused placeholder (test_recorded_placeholder_refused red); swallow a contingency `StudyFailed` and return empty rows (test_recorded_contingency_cap red); stop the margin walk at `transfer_max_mw` and pass the cap flow on as the voltage limit (test_written_fresh_rows_are_ok_with_link red, EL_PASO 852.63 instead of 867.65). Dropping `bounded_by` from the `build_dispatch_row` call alone left the test green, because with a correct margin search the tripwire can never fire (see Notes); combined with a margin plant that labels a cap-ended search `dlr_rating`, the tripwire (bounded_by passed) turned the test red through stage `dispatch`, and with `bounded_by` dropped as well it was red through the EL_PASO figure.

## Deviations from Plan

### Auto-fixed Issues
None. No gap in `study.py` was exposed by Task 2 or Task 3, so the module was changed only in Task 1.

### Notes (choices inside the plan's latitude, not deviations of behaviour)
- **Dropping `bounded_by` alone is an equivalent mutation.** The plan lists it as a plant that must turn test_written_fresh_rows_are_ok_with_link red "through the dispatch tripwire". The tripwire only fires when the margin search reports `dlr_rating` with a limit below the applied rating, which the correct search never does, so the plant is observable only together with a broken search. The test that guards the real failure (an understated `voltage_stability` figure) is red under every plant that creates it (the cap-stop plant above, and the combined plants); no test asserts that the call site passes `bounded_by`. If the orchestrator wants that pinned directly, a one-line spy on `dispatch.build_dispatch_row` in a later plan would do it.
- **The failed-fnsl message with a stale `solved=` number was left as 02-03 wrote it.** The hand-off note says the plan may drop the number when `ierr` is non-zero; plan 02-06 does not ask for it and the 02-03 tests pin the current text, so `study.solve_base` is unchanged.
- **Golden file contents.** It stores `[name, sorted keyword names]` per first-seen pair as the plan specifies. The study calls most functions positionally, so most pairs have an empty keyword list, and the outage loop adds no new pair (`set_status` reuses the `branch_chng_3` keyword set), so the file pins the function order and keyword shapes, not every argument.
- **New directory `backend/tests/data/`** was created by the plan's golden file (the only file in it). The golden test creates the directory only when `PSSE_UPDATE_CALL_SURFACE=1`.
- **Test-level choices.** `_private_temp` (autouse) redirects `tempfile.tempdir` to `tmp_path/scratch` in both test files so a leaked temp directory shows; the Postgres test file adds `test_recorded_unreadable_mapping` assertions that the stored error names the mapping file by base name only.
- **Bash.** One empty heredoc (`cat >> file <<'EOF'` with no body) was run by mistake; it appended nothing. All file content went through Write and Edit. STATE.md, ROADMAP.md and REQUIREMENTS.md were not updated, per the user's rules; `.planning/config.json`, `milestone.lock` and `state.json` remain uncommitted.

## Known Stubs
None.

## Threat Flags
None. The assembly adds no network, auth or filesystem surface beyond what plans 02-03 to 02-05 already have: the one temporary directory per run (removed in `finally`), and a read of the mapping and case files for hashing. T-02-27 (a failed study never leaves results: test_recorded_* assert [1, 0, 0, 0] and exit 1), T-02-38 (test_written_fresh_rows_are_ok_with_link, test_recorded_transfer_not_bounded), T-02-28 (test_prepare_run_hashes_and_labels, test_recorded_placeholder_refused), T-02-29 (error names only the base name: test_recorded_case_not_loadable, test_recorded_unreadable_mapping), T-02-30 (sha256 assertions, test_full_study_never_saves_or_changes_the_case) and T-02-31 (test_full_study_new_adapter_per_run) are mitigated with the named tests. The residual gap between hashing the case and loading it (T-02-28) is unchanged and is for plan 02-07 to document.

## Hand-off notes for plan 02-07 and Phase 3
- Launcher: `prepared = study.prepare_run(psspy, case_path, mapping_path)` then `job.run_once(fetch, prepared.study, connect, prepared.case_id, prepared.case_sha256, prepared.mapping_sha256)`; `prepared.mapping_error` carries the mapping problems for the launcher's own log. One study per process: `make_study` builds a new `PsseApi` per call but PSS/E state is process-global.
- The `clock` argument is the budget's clock (monotonic seconds); `run_once`'s `clock` is a separate wall-clock datetime source.
- Run proofs against the fake only: units and margins are not validated on Power Systems' network (C-8). The fake placeholder numbers (16 contingencies, 10 rows, EL_PASO 867.65 MVA dispatched in full with fresh rows) are arithmetic and control-flow proofs.
- Any change to the study's call pattern fails `test_call_surface_matches_golden`; regenerate with `PSSE_UPDATE_CALL_SURFACE=1` and review the diff.

## Self-Check: PASSED
- FOUND: backend/psse_job/study.py, backend/tests/psse_study_job_test.py, backend/tests/psse_study_test.py, backend/tests/data/psse_call_surface.json
- FOUND commits: 0882abd, 230b461, 7ca9388 (each an ancestor of HEAD); measured `git rev-list --count` from the ledger base is 3
