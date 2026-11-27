---
phase: 04-replay-and-agreement-check
plan: 03
subsystem: replay-and-commands
tags: [pandapower, replay, agreement-check, deliberate-mismatch, closed-vocabulary, ci-mode, writes-nothing]
status: complete

requires:
  - phase: 04 plan 01 (pandapower-solver)
    provides: pandapower_job.recorded (ingest_export, load_snapshot, by_run, complete, profile, profile_lines, ExportRefused) and the shared replay fixture
  - phase: 04 plan 02 (pandapower-solver)
    provides: pandapower_job.agree (side_from_recorded, side_from_results, compare_run, replay_failed, gate, Summary, Detail, tolerance_header)
  - phase: 02 (pandapower-solver)
    provides: engine.prepare_run, load_recorded_backend, is_placeholder, settings_record, RecordsRefused
  - phase: 01 (pandapower-solver)
    provides: pandapower_job.private, cli.REPORT_MARKER and exit codes, compare tolerances (by import)
provides:
  - backend/pandapower_job/replay.py - REFUSAL_REASONS, ReplayRefused, selection_from_ratings_used, configuration_key, plan, replay_snapshot, RunOutcome, ReplayResult, Plan
  - backend/pandapower_job/replay_cli.py - CLI_LINE_PATTERNS, main, render_summary_lines, report_document (the owner's ingest and replay commands)
  - backend/pandapower_replay.py - the entry script
  - backend/pandapower_job/engine.py - load_session_hashes (additive, 26 inserted lines, none changed)
  - backend/tests/pandapower_replay_fixture.py - FIXED_NOW, CASE_SHA, STAMP, StandIn, Layout, write_mapping, stress_selection, standin, light_standin, private_layout, ingest_standins, ingest_standins_result, snapshot_of_bundles, perturbed_bundle, perturbed_snapshot
  - four test files (pandapower_replay_test.py, pandapower_replay_study_test.py, pandapower_replay_cli_test.py, pandapower_replay_readonly_test.py)
affects: [04-04 first real replay (waits for the owner's export file; uses these names unchanged)]

actuals:
  tokens: 28900
  tasks: 3
  commits: 3
plan_head_before: eebb3e2
plan_head_after: 89bd54fcb434ebd119df101bce671bd2d2ec9ab2

tech-stack:
  added: []
  patterns:
    - "One runner seam: engine.prepare_run(...).study(selection, None) is the default runner and tests supply cached or raising runners; the unchanged psse_job study loops do the work"
    - "Closed-vocabulary printer copied from cli._Printer: a line outside CLI_LINE_PATTERNS raises, an argument parser that raises instead of echoing"
    - "Stand-in recorded run: the unchanged study on the public 39-bus fixture presented as a PSS/E run through run_record.build_run_record and result_rows"
    - "Deliberate-mismatch matrix: one perturbed copy of a stand-in's rows per case, sent through export file, ingest and loader, with the value just inside and just outside each tolerance"

key-files:
  created:
    - backend/pandapower_job/replay.py
    - backend/pandapower_job/replay_cli.py
    - backend/pandapower_replay.py
    - backend/tests/pandapower_replay_test.py
    - backend/tests/pandapower_replay_study_test.py
    - backend/tests/pandapower_replay_cli_test.py
    - backend/tests/pandapower_replay_readonly_test.py
  modified:
    - backend/pandapower_job/engine.py
    - backend/tests/pandapower_replay_fixture.py

key-decisions:
  - "A configuration (mapping hash plus, per city, source, fallback reason, amps and count) is replayed once, with the ratings stored in its first run, and its results are validated once against that representative selection; the row times of another run in the same configuration may differ and are not compared by agree"
  - "replay.replay_snapshot keeps the plan's allow_placeholder parameter (default False, only lets the mapping loader read a file whose own flag says placeholder); the owner's command never sets it and placeholder settings are always refused, so no override reaches the owner"
  - "render_summary_lines returns the verdict line first (replay: WORD) followed by the count lines; the CLI prints it unchanged in both modes and adds report: written only in local mode"
  - "The report is written before anything is printed, so a refused report folder (same second) prints only the private path line and exits 2"
  - "In ingest, an existing but unreadable check folder is treated as not checked for the session-case count rather than a refusal (a missing mapping or folder is not checked, as the plan says)"

requirements-completed: []
requirements-progress:
  - id: AGR-01
    note: "replay half done and proven on the public fixture (stored ratings, hash match, no write, no connection); the real recorded runs wait for the owner's export (plan 04-04)"
  - id: AGR-02
    note: "matrix proves the rules fail outside and pass inside every tolerance on the real solver; agreement on real data is plan 04-04"
  - id: AGR-03
    note: "gate counts, not exercised kinds, exclusions with reasons and the largest deviation (private report) built and tested; the real report is plan 04-04"
  - id: AGR-04
    note: "closed vocabulary, CI mode that writes nothing, report only under data/private; plan 04-04 repeats the scanned-output test with planted identifiers on the real replay"

coverage:
  - id: D1
    description: "a stand-in recorded run goes export file, ingest, snapshot, hash match, stored-rating rebuild, the unchanged study on the real solver, comparison and gate, and passes with non-empty voltage_high and non_convergence comparisons and zero deviation"
    requirement: "AGR-01, AGR-02"
    verification:
      - kind: integration
        ref: "backend/tests/pandapower_replay_study_test.py#test_tracer_self_replay_passes_on_the_real_solver"
        status: pass
    human_judgment: false
  - id: D2
    description: "only input mismatches exclude (every one of the seven reasons is produced, in the closed order); a raising study, invalid results and a mapping the engine cannot run are failed runs, never exclusions; refusals carry a reason word"
    requirement: "AGR-01, AGR-02"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_replay_test.py#test_every_exclusion_reason_is_produced_and_never_replayed"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_replay_test.py#test_a_raising_study_is_a_failed_run_never_an_exclusion"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_replay_test.py#test_a_mapping_the_engine_cannot_run_is_a_stage_mapping_failure_not_a_disagreement"
        status: pass
    human_judgment: false
  - id: D3
    description: "the check can fail: perturbations inside each tolerance pass (non-zero deviation) and outside fail on the real fixture, one-sided rows are borderline only within the band, an altered mapping is excluded, empty comparisons are incomplete"
    requirement: "AGR-02, AGR-03"
    verification:
      - kind: integration
        ref: "backend/tests/pandapower_replay_study_test.py#test_mismatch_*"
        status: pass
    human_judgment: false
  - id: D4
    description: "every printed line is counts and fixed words (out-of-vocabulary lines raise), CI mode writes no file or folder and prints the local lines without the report line, the report holds the detail and the terminal none of it"
    requirement: "AGR-04"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_replay_cli_test.py#test_an_out_of_vocabulary_line_raises"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_replay_cli_test.py#test_ci_mode_writes_no_file_and_no_folder"
        status: pass
      - kind: integration
        ref: "backend/tests/pandapower_replay_cli_test.py#test_a_real_local_replay_prints_counts_only_and_its_output_scans_clean"
        status: pass
    human_judgment: false
  - id: D5
    description: "the replay writes nothing and connects to nothing: import walk of five modules with a planted-import check, fresh interpreter loading no writer-side module, and a full real replay with connections blocked and writer and job entry points recorded (zero calls)"
    requirement: "AGR-01"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_replay_readonly_test.py#test_a_full_real_replay_makes_no_connection_and_calls_no_writer"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_replay_readonly_test.py#test_a_fresh_interpreter_importing_the_phase_loads_no_writer_side_module"
        status: pass
    human_judgment: false
---

# Phase 4 Plan 03: Replay, Agreement Check Commands and the Deliberate-Mismatch Matrix Summary

**The recorded PSS/E runs are replayed through the unchanged pandapower study with each run's stored ratings and the hash-matched mapping, judged by plan 04-02's rules, and driven by two owner commands that print counts and fixed words only; the check is shown to pass inside every tolerance and fail outside it on the real solver, and to write and connect to nothing.**

The recorded run used for all of this is a stand-in built from the public 39-bus fixture. It proves the wiring and the failure detection only. Nothing in this plan shows that PSS/E and pandapower agree on real data; plan 04-04 does that, once the owner's export file arrives.

## Accomplishments

- Tracer (Task 1): a stand-in PSS/E run (the unchanged study on the real solver, presented through `run_record.build_run_record` and `result_rows`) goes through an export file, `ingest_export`, `load_snapshot`, the hash match, the stored-rating rebuild, the real study, `agree.compare_run` and `agree.gate`, and passes with non-empty voltage_high and non_convergence comparisons, thermal_overload and voltage_low listed as not exercised, and a zero largest deviation.
- Plan stage and failure semantics (Task 2): `replay.plan` (pure) excludes by the closed list in order (failed_run, mapping_hash_missing, mapping_hash_differs, case_hash_missing, case_hash_differs, ratings_unusable, rows_incomplete); one study per distinct configuration; `StudyFailed` and `ResultsInvalid` make every run of the configuration a failed run with the stage word only; a mapping the engine's preflight rejects is a stage-mapping failure counted under `failed_stages["mapping"]`, not a disagreement and not an exclusion; refusals (placeholder_settings, network_missing, mapping_missing, mapping_unusable) carry a reason word and no override exists. `engine.load_session_hashes` reads the session's case and mapping hashes strictly.
- The commands (Task 3): `ingest` and `replay` through one closed-vocabulary printer, a private report (local mode only) with the settings in force, the tolerance rules, the largest deviation even on a pass, the exclusions with run ids, and every finding with its values; CI mode (the flag, or GITHUB_ACTIONS equal to the text true whatever the flag) creates no file and no folder.
- Writes-nothing proofs: no module of the phase imports a driver, a network module or a writer-side module (walk of five modules, with 20 planted imports shown to fire); a fresh interpreter importing the phase loads none of psse_job.writer, job, gaps, credcheck, launcher, probe; a full real replay with socket and psycopg connections made to raise and writer.connect, write_run, record_failure and job.run_once replaced by recorders finishes with `replay: pass` and zero calls.

## The real-solver matrix (public fixture, stand-in recorded run)

Two stand-ins were built once per module on the real solver: the default ratings (42 outages, voltage-bound margins, a recorded island outage as non_convergence rows) and a stress one (every rating at 10 percent: thermal_overload, voltage_high and non_convergence rows, rating-bound margins). The unperturbed side of each case is the stand-in's own results through a cached runner (the real-solver self replay in the tracer shows the replay reproduces them exactly); one case, the changed stored rating, runs the real solver.

| Case | Inside tolerance | Outside tolerance |
|------|------------------|-------------------|
| self replay, both stand-ins | pass, largest utilisation 0; stress exercises thermal_overload | |
| thermal value (stress, largest row) | +1 percent: pass, utilisation above 0 and below 1 | +3 percent: fail (value_thermal) |
| voltage_high value (largest row) | +0.005 pu: pass, non-zero deviation, utilisation below 1 | +0.02 pu: fail (value_voltage) |
| dispatched_mva (biggest city) | +1 percent: pass, utilisation below 1 | +3 percent: fail (dispatch_value) |
| margin_mw, voltage-bound (default) | 0.9 of its allowance: pass | 1.1 of its allowance: fail (margin_value) |
| margin_mw, rating-bound (stress) | 0.9 of its allowance (stored step): pass | 1.1 of its allowance: fail (margin_value) |
| n_contingencies | | +1: fail (n_contingencies) |
| largest voltage_high row removed (excess above the band, asserted) | | fail (set_one_sided) |
| smallest voltage_high row removed (excess inside the band, asserted) | pass, one borderline | |
| bogus voltage row | 0.004 pu over: pass, one borderline | 0.05 pu over: fail |
| bogus thermal row (stress, real limit, band computed in the test) | 0.5 of the band over: pass, one borderline | 5 bands over: fail |
| recorded non_convergence for an outage that converged | | fail (convergence_one_sided) |
| recorded island rows removed | | fail (convergence_one_sided) |
| limiting factor changed, applied and voltage limit far apart (asserted) | within the band (voltage limit set to 1.001 times applied): pass, one borderline | far apart: fail (limiting_factor) |
| a stored rating changed (stress, AUSTIN times 10) | | real solver replays another configuration: fail on rating_data and dispatch_value |
| altered mapping file (one byte) | excluded mapping_hash_differs, zero runs replayed, word incomplete | (never a pass) |
| different session case hash | every run excluded case_hash_differs, word incomplete | |
| snapshot of only a failed run | excluded failed_run, word incomplete | |
| n_contingencies_with_results broken on purpose | excluded rows_incomplete, word incomplete | |
| both sides emptied of every violation row | word incomplete (one run replayed, zero non-empty comparisons) | |

No case was skipped; each one that depends on the fixture asserts its precondition and fails with a message naming it. No perturbation passed that should have failed, and none failed that should have passed, so no change to `agree.py` or `replay.py` was needed. The only runs excluded in the matrix are the four designed exclusion cases (altered mapping, different case hash, failed run, broken count); every other case replays its run.

## Task Commits

1. **Task 1: Tracer, stand-in run exported, ingested, replayed on the real solver and passed** - `30f2b56` (feat)
2. **Task 2: Exclusions, configurations, failure semantics, refusals, `load_session_hashes` and the mismatch matrix** - `aa13149` (feat)
3. **Task 3: The owner's two commands, private report, CI mode, closed vocabulary and the writes-nothing proofs** - `89bd54f` (feat)

## Verification results

All with `.venv/Scripts/python.exe`, pandapower 3.5.6 confirmed first:

| File | Result | Wall time |
|------|--------|-----------|
| `pandapower_replay_test.py` | 62 passed, 0 skipped | 7.3 s |
| `pandapower_replay_study_test.py` | 22 passed, 0 skipped | 45.8 s (expected under 120 s) |
| `pandapower_replay_cli_test.py` | 138 passed, 0 skipped | 34.3 s |
| `pandapower_replay_readonly_test.py` | 30 passed, 0 skipped | 16.2 s |
| `pandapower_recorded_test.py`, `pandapower_agree_test.py`, `pandapower_engine_test.py` (unchanged regression, 21 tests), `pandapower_import_gate_test.py` | 268 passed, 0 skipped | 28.3 s |

Total over the plan's verification list: **520 passed, 0 skipped, 0 failed.** No Postgres tier test is in this list (plan 04-01's database items live in `pandapower_replay_pg_test.py` and stay skipped here, as reported in `04-01-SUMMARY.md`).

- `grep -c "def load_session_hashes" backend/pandapower_job/engine.py` prints 1 (baseline 0); the diff of `engine.py` is 26 insertions and no deletion; `pandapower_engine_test.py` still passes unchanged (21 tests).
- File-scope gate (PLAN=04-03) exits 0; `private_leak_scan.py --staged` exited 0 before each of the three commits and the whole-tree scan exits 0.
- Post-commit deletion check: no deletion in any commit.
- The measured commit count is `git rev-list --count --grep="(04-03)" eebb3e2..HEAD` = 3.

## Deviations from Plan

### Auto-fixed Issues

None: no bug, missing-critical or blocking issue was found in `agree.py`, `recorded.py` or the engine.

### Notes

**1. Commit ledger.** `.git/gsd-plan-head-before-04-03` was not used (an older workstream may have left it); `plan_head_before` is `eebb3e2` and `commits` is measured with git as the lead instructed.

**2. Validation once per configuration (plan wording).** The plan says each run's results are checked with `run_record.validate_results`. Two runs in one configuration can carry different city_rating row times in their stored ratings (the key ignores times, as the plan specifies), and the study stamps the times of the selection it ran on; validating the cached results against another run's selection would flag a false mismatch. The results are therefore validated once against the selection that produced them, and every run of the configuration is compared with those results (`agree` does not compare the row times). Test: `test_the_configuration_key_ignores_times_and_depends_on_ratings_and_mapping`.

**3. `allow_placeholder` kept in the signature.** The plan's Task 1 text lists it; the plan's must-haves say there is no override. It is kept (default False), only lets the mapping loader read a file whose flag says placeholder, is never set by the owner's command, and placeholder settings are refused regardless. `test_no_override_exists` pins the signature and the refusal reasons.

**4. Ingest hint line.** The plan names the line "ingest hint: narrow the psse-% prefix to a date prefix" while 04-01's fixed sentence is the longer `EXPORT_REFUSAL_HINTS` text. The printer accepts exactly `"ingest hint: " + recorded.EXPORT_REFUSAL_HINTS[...]` (both hinted reasons have the same text) and refuses the same text with anything appended.

**5. More fixture helpers than the plan listed.** `light_standin` (files and hashes of a stand-in without a solve, for the stubbed command tests), `snapshot_of_bundles`, `perturbed_bundle`, `ingest_standins_result`, `stress_selection`, `STAMP` and `Layout` were added next to the listed names, all in `pandapower_replay_fixture.py`. Plan 04-04 can use every listed name unchanged.

**6. Test-first discipline.** The `<behavior>` tests were written together with the code of each task and run after it; I did not capture a separate failing run before writing each implementation. The mismatch matrix has paired inside and outside assertions plus asserted preconditions, so a vacuous pass is not possible.

## Known Stubs

None. The only synthetic data are the public fixture rows and the stub comparisons built in the command tests, by design.

## Threat Flags

None beyond the plan's register. T-04-10 (ratings rebuilt only from `ratings_used`, hash match with no override, placeholder refused, altered-mapping and wrong-case-hash and changed-rating tests), T-04-11 (import walk, fresh interpreter, blocked connections with recorders), T-04-12 (raising runners, invalid results and the stage-mapping preflight are failed runs; zero compared runs is incomplete), T-04-13 (closed vocabulary, no verbose flag, no exception text printed, CI writes nothing, report only through `private.py`), T-04-14 (every input and the report folder pass `private.require_private`, exclusive creation) are mitigated as the plan says. T-04-SC met: nothing installed.

## Next Phase Readiness

- Plan 04-04 waits for the owner's export file (the SQL is `supabase/ops/export_psse_runs_for_replay.sql`, preferably proven on a Postgres host first, see `04-01-SUMMARY.md`). Its steps use the two commands: `.venv/Scripts/python.exe -I -B backend/pandapower_replay.py ingest --export PATH` then `... replay`.
- The orchestrator owns STATE.md, state.json, ROADMAP.md and REQUIREMENTS.md; AGR-01 to AGR-04 are not marked complete here because no real recorded run has been replayed (plan 04-04).

## Self-Check: PASSED

- Files exist: `backend/pandapower_job/replay.py`, `backend/pandapower_job/replay_cli.py`, `backend/pandapower_replay.py`, `backend/tests/pandapower_replay_test.py`, `backend/tests/pandapower_replay_study_test.py`, `backend/tests/pandapower_replay_cli_test.py`, `backend/tests/pandapower_replay_readonly_test.py` (all FOUND), `backend/pandapower_job/engine.py` and `backend/tests/pandapower_replay_fixture.py` modified.
- Commits are ancestors of HEAD: `30f2b56`, `aa13149`, `89bd54f` (verified below).
