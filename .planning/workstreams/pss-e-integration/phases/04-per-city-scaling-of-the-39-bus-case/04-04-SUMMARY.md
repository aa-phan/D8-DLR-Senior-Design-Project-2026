---
phase: 04-per-city-scaling-of-the-39-bus-case
plan: 04
subsystem: psse-study
tags: [pss-e, study, failure-handling, all-or-nothing, run-time-budget, fake-psspy, python37]

requires:
  - phase: 04-per-city-scaling-of-the-39-bus-case
    provides: "make_study as four independent per-city studies, prepare_city_base, scale_city_case with per-city StudyFailed messages that name the city and no figure (04-03)"
provides:
  - "study.combined_failure, CITY_OK, _CLAUSE_TEXT_CHARS, _clause_text and the collecting per-city loop of make_study (_study_city)"
  - "A failed city no longer hides the others: all four are attempted, then one StudyFailed names every city's outcome and run_once stores one failed psse_run row with no result row"
  - "A run-time budget shared by the four cities, with cities that cannot start reported as not attempted"
  - "Tests for the combined text, long messages, the shared budget, index failures, stray exceptions and the absence of a target figure in the stored error, the log and the dry-run output"
affects: [04-05-probe-row, 04-06-laptop-check]

actuals:
  tokens: 7200
  tasks: 3
  commits: 3
plan_head_before: 16ff58152a4d32f7ba7f07b10b150e077b34c57b
plan_head_after: 63f1f633552816d462d3427242318dbb14c88174

tech-stack:
  added: []
  patterns:
    - "Collect-then-fail: every city's StudyFailed is remembered, one combined StudyFailed is raised after the loop, so the existing run_once failure path (record_failure, exit 1, no rows) is reused unchanged"
    - "Fixed per-city share of the error text (180 characters) so the 1000-character error limit can never drop a city"
    - "Only StudyFailed is collected; any other exception is a bug and propagates at once"

key-files:
  created: []
  modified:
    - backend/psse_job/study.py
    - backend/tests/psse_scaling_test.py
    - backend/tests/psse_study_test.py
    - backend/tests/psse_study_job_test.py
    - backend/tests/psse_launcher_test.py

key-decisions:
  - "Stage of the combined failure is the first failed city's stage in CITIES order; load_case when no city failed but one was not attempted (the stage vocabulary is closed by the DDL CHECK, C-3)"
  - "make_study's per-city work moved into a private _study_city so the try/except StudyFailed wraps exactly one city's whole step; the dispatch ValueError to StudyFailed('dispatch') conversion stays inside it"
  - "The run-wide contingency row cap applies only after all four cities succeeded (PD-3); a combined failure is raised before it"
  - "The not-attempted check is made before each city with budget.elapsed() > budget.max_seconds; a budget that runs out inside a city is that city's own failure (the existing Budget.check in screen and margin)"

requirements-completed: [SCL-04, SCL-05]

coverage:
  - id: D1
    description: "When one city's scaled study fails, the other three are still attempted and run_once stores one failed run whose error names all four cities, with no result row for any city and exit code 1"
    requirement: "SCL-04"
    verification:
      - kind: integration
        ref: "backend/tests/psse_study_job_test.py#test_tracer_one_city_fails_all_attempted_one_failed_record"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_scaling_test.py#test_failure_several_cities_first_stage_wins"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_study_test.py#test_full_study_dispatch_failure_is_stage_dispatch"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every city stays named in the stored error however long each city's message is, and the whole message fits the 1000-character limit after redaction"
    requirement: "SCL-04"
    verification:
      - kind: unit
        ref: "backend/tests/psse_scaling_test.py#test_failure_long_messages_keep_every_city"
        status: pass
    human_judgment: false
  - id: D3
    description: "The run-time budget is shared by the four cities; cities that cannot start are reported as not attempted (stage load_case when no city failed), and a budget spent inside a city fails that city at its own stage"
    requirement: "SCL-04"
    verification:
      - kind: unit
        ref: "backend/tests/psse_scaling_test.py#test_budget_spent_between_cities_marks_the_rest_not_attempted"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_scaling_test.py#test_budget_spent_inside_a_city"
        status: pass
    human_judgment: false
  - id: D4
    description: "A case that cannot be indexed or a mapping that does not match it still fails at once (no city attempted, no scaling call), a non-StudyFailed exception surfaces as itself, and the private temp directory is empty after every path"
    requirement: "SCL-04"
    verification:
      - kind: unit
        ref: "backend/tests/psse_scaling_test.py#test_index_failures_stay_immediate"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_scaling_test.py#test_other_exceptions_surface_as_themselves"
        status: pass
    human_judgment: false
  - id: D5
    description: "No synthetic target figure appears in the stored error, a log record, the dry-run output or the launcher's log file, for a failing run or a successful one"
    requirement: "SCL-05"
    verification:
      - kind: integration
        ref: "backend/tests/psse_launcher_test.py#test_dry_run_city_failure_names_each_city_without_figures"
        status: pass
      - kind: integration
        ref: "backend/tests/psse_launcher_test.py#test_dry_run_success_prints_no_figure"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_scaling_test.py#test_combined_failure_text_never_holds_a_figure"
        status: pass
    human_judgment: false

duration: 19min
completed: 2026-11-11
status: complete
---

# Phase 4 Plan 04: Attempt every city, fail once naming each Summary

**One city's failure no longer hides the other three: `make_study` now attempts all four cities, collects each city's `StudyFailed`, and raises one `combined_failure` (`<n> of 4 cities failed; AUSTIN: ok; CORPUS_CHRISTI: failed at <stage>: <text>; ...`) that `run_once` stores as one failed run with no result rows, each clause cut to 180 characters so no city can fall off the 1000-character error limit.**

## Performance

- **Duration:** about 19 min of wall-clock, of which about 9 min were the plan-end gate run
- **Started:** 2026-11-11T04:02Z (22:02 local, 2026-11-10)
- **Completed:** 2026-11-11T04:21Z
- **Tasks:** 3 (the first a tracer)
- **Files:** 5 modified, none created (422 insertions, 34 deletions under `backend/`)

## Accomplishments

- `study.combined_failure(outcomes, max_seconds)` builds the one `StudyFailed`: header `"<n> of 4 cities failed"` (failed and not attempted together), then one clause per city in `constants.CITIES` order: `<CITY>: ok`, `<CITY>: failed at <stage>: <text>` or `<CITY>: not attempted: run-time budget of <s> s exceeded`. `_clause_text` drops a leading `"scaling: <CITY>: "` (keeping `"scaling: "`), `"<CITY>: "` or `"<CITY> "` and cuts to `_CLAUSE_TEXT_CHARS = 180`. The stage is the first failed city's; `load_case` when no city failed but one was not attempted.
- `make_study` loops over the cities calling a new private `_study_city` (prepare_city_base, screen, margin, dispatch row, the details additions), wrapped in `try/except StudyFailed`. Before each city it checks `budget.elapsed() > budget.max_seconds` and marks the city not attempted. Only `StudyFailed` is collected; anything else propagates at once and the `finally` still removes the temp directory. `index_case` failures (`load_case`, `mapping`) are raised before the loop, as before.
- When all four cities succeed the result is exactly the plan 04-03 result (same rows, same run-wide row cap, applied only then, PD-3). `job.py`, `run_record.py`, `launcher.py`, `writer.py`, the DDL and the migrations are untouched (C-3): the combined error rides the existing `record_failure` path.
- The module and `make_study` docstrings now say every city is attempted, one failure fails the run once naming each city, and there is no partial result set (CD-8, WB-02).

### Stored combined error text (tracer; synthetic data only)

From `test_tracer_one_city_fails_all_attempted_one_failed_record`, the `psse_run.error` the real writer stored in local Postgres, with `failed_stage = apply_ratings` and `_counts == [1, 0, 0, 0]`:

```
1 of 4 cities failed; AUSTIN: ok; CORPUS_CHRISTI: failed at apply_ratings: scaling: psspy.scal_2 failed: ierr=6 (error code not listed in the manual excerpt); MIDLAND: ok; EL_PASO: ok
```

## TDD record

Plan type is `execute` with `tdd="true"` tasks; `workflow.tdd_mode` is not enabled, so RED evidence was not submitted to `gsd_run check tdd-red-evidence`. The plan specifies one `feat` commit for Task 1 and one `test` commit each for Tasks 2 and 3.

- **Task 1 RED:** with the tracer and the updated 04-03 failure assertions written, 7 tests failed. The target test `test_tracer_one_city_fails_all_attempted_one_failed_record` executed, ran through `run_once` into Postgres and failed on the planned assertion: the stored error was `scaling: CORPUS_CHRISTI: psspy.scal_2 failed: ierr=6 (...)` where `error.startswith("1 of 4 cities failed; AUSTIN: ok; ")` was expected (the old first-failure behaviour; no import, collection or fixture fault). The other six reds were the updated pins in `psse_scaling_test.py` and `psse_study_test.py`. **GREEN:** the same three files, `75 passed`, and `psse_contract_test.py`, `10 passed`.
- **Task 2 and Task 3:** the tests were written after Task 1's implementation, which already contains the loop, the clause cut and the budget rule, so all of them passed on first run (6 of 6, then 3 of 3). There was no separate RED. That is a plan-ordering fact; the mutation checks below stand in for it. Task 2 needed no change to `study.py`, so its commit holds the test file only (the plan allowed for a fix there).
- No REFACTOR commit.
- One test-author trap caught while writing the tracer: the fake records a `scal_2` call with keyword names only when called with keywords, so the subclass forwards to `super().scal_2(sid=..., ...)`. With positional forwarding the recorded call has empty kwargs and the "4 whole-case scale calls" count read 1. (The pre-existing `_ScaleIgnored` forwards positionally, which makes the `_scale_calls` helper blind to its calls; no test of mine relies on that combination.)

## Task Commits

1. **Task 1: Tracer, one city's failure recorded once naming all four** - `e24f2db` (feat)
2. **Task 2: Several failures, long messages, shared budget, index failures, stray exceptions** - `2cd8cea` (test)
3. **Task 3: No target figure in dry-run output, logs or stored errors** - `63f1f63` (test)

**Plan metadata:** the commit holding this SUMMARY (docs). STATE.md, ROADMAP.md and REQUIREMENTS.md are not edited here (the orchestrator owns them).

## Pins changed (old to new)

| Where | Old | New |
|-------|-----|-----|
| `psse_scaling_test.py` `_ScaleIgnored` and `_ScaleRefused` tests | `startswith("scaling: AUSTIN")` | `"4 of 4 cities failed; AUSTIN: failed at apply_ratings: scaling:"` and four such clauses |
| `psse_scaling_test.py` factor-bound test | `startswith("scaling: AUSTIN")`, no scal_2 call at all | `"1 of 4 cities failed; AUSTIN: failed at apply_ratings: scaling: the load target is outside"`, the other three `ok`, 3 whole-case scale calls |
| `psse_scaling_test.py` case-without-generation test | `startswith("scaling: AUSTIN")` | `"4 of 4 cities failed; AUSTIN: failed at apply_ratings: scaling: the case has no generation"` (not named in the plan's behaviour block, but it asserted the first-failure text) |
| `psse_scaling_test.py` MIDLAND non-convergence test | saved `["AUSTIN.sav", "CORPUS_CHRISTI.sav"]` | saved `[..., "EL_PASO.sav"]` too (EL_PASO is now attempted), plus the combined message |
| `psse_study_test.py` dispatch-refusal message | `"AUSTIN: inconsistent search"` | the four-clause combined text from the plan |

## Mutation checks (plant, see red, restore byte for byte; SHA-256 of `study.py` equal after each)

| Planted fault | Test that went red |
|---|---|
| drop the clause cut | `test_failure_long_messages_keep_every_city` (message length 8174) |
| count only failed cities in the header (not the not-attempted ones) | `test_budget_spent_between_cities_marks_the_rest_not_attempted` and `test_budget_spent_inside_a_city` (`0 of 4` and `1 of 4` instead of `3 of 4` and `4 of 4`) |
| collect `KeyError` too | `test_other_exceptions_surface_as_themselves` (the run raised `StudyFailed` instead of `KeyError`) |
| re-raise the first city's `StudyFailed` | the four updated 04-03 failure tests (message is the bare `scaling: AUSTIN: ...`, no combined text) and the tracer |
| return results for the three good cities (no failure when a city failed) | the tracer, at its first assertion (`failed_stage`), so no partial result set can be stored unnoticed |
| put the load target into the scaling refusal text | `test_dry_run_city_failure_names_each_city_without_figures` and `test_combined_failure_text_never_holds_a_figure` (`test_dry_run_success_prints_no_figure` stays green, as it has no failure text to leak into) |

The plan's mutation list names the re-raise and the three-good-cities cases against "the tracer"; both do turn the tracer red, the re-raise also through the scaling tests.

## Deviations from Plan

None - plan executed exactly as written, with two small notes that are not behaviour changes: the case-without-generation test in `psse_scaling_test.py` also needed its pin updated (listed above), and Task 2 needed no production-code change.

## Issues Encountered

- **Plan-end gate** (`backend/tests/psse_*_test.py` plus `secret_scan_test.py`, plan PATH and flags): `2 failed, 728 passed, 1 skipped, 19 errors` in 510 s. Running `backend/tests/psse_results_migration_test.py` alone gives `2 failed, 4 passed, 19 errors`, so that file is the only one with failures or errors: the known unrelated problem (core.autocrlf rewrites `supabase/migrations/20261109233541_psse_results.sql` to CRLF so its pinned SHA-256 differs, and its Postgres fixture then errors on `pg_ctl start`). The one skip is `secret_scan_test.py:316`, the owner-local check that needs `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` and `SUPABASE_DB_URL`. The plan-end wording "exits 0 with no skipped test" therefore does not hold on this machine, for reasons that predate this plan (as plans 04-01 and 04-03 also reported). Each task's own `<automated>` command passed with no skip: Task 1 `75 passed` plus `10 passed`, Task 2 `122 passed` and `6 passed` for the `-k` selection, Task 3 `50 passed` and `3 passed` for the `-k` selection, and the tracer alone `1 passed`.
- A Bash heredoc holding a Python script with triple-quoted strings and apostrophes failed to parse in this shell once (nothing was written); the edit was redone with the Edit tool. No file was left half-written.
- `git` warns that LF will be replaced by CRLF in some edited files (core.autocrlf); no content effect.

## Known Stubs

None. No placeholder flows into any output; the synthetic targets are the committed example's own.

## Threat Flags

None beyond the plan's register. T-04-11 (partial result set under a run that lost a city): mitigated; the combined failure is raised before any result object is built, `run_once` writes the failed record alone, the tracer asserts `_counts == [1, 0, 0, 0]` and all owner checks ok, and the three-good-cities mutation turns it red. T-04-12 (figure in the stored error, a log record or the dry-run output): mitigated; the clause builder only trims text, and the three figure tests plus the tracer's caplog check cover the stored error, the log records, the dry-run streams and the launcher's log file. T-04-13 (four studies exhausting the shared budget and hiding who ran): mitigated; one shared `Budget`, cities that cannot start are named as not attempted, and both budget tests plus the header mutation cover it. `launcher.py` and `job.py` needed no change, so no leak there is open.

## Next Phase Readiness

- Plan 04-05 (probe row) and 04-06 (laptop check) are not affected by this plan's logic; a real run now reports every city's outcome in one stored error, which will make a laptop scaling problem visible for all four cities at once.
- The fake still proves call order, isolation and failure handling only; whether real PSS/E reads the `SCALE_LAYOUT` slots as the adapter sends them, and whether a fresh `case()` undoes a scaling, is for plans 04-05 and 04-06.

## Self-Check: PASSED

- Files exist: `backend/psse_job/study.py`, `backend/tests/psse_scaling_test.py`, `backend/tests/psse_study_test.py`, `backend/tests/psse_study_job_test.py`, `backend/tests/psse_launcher_test.py`.
- Commits `e24f2db`, `2cd8cea`, `63f1f63` are ancestors of HEAD; `git rev-list --count 16ff581..HEAD` was 3 before this summary's commit (no deleted files in any of them).
- `grep -c "def combined_failure" backend/psse_job/study.py` is 1 (baseline 0).
- Own-changes gate (PLAN=04-04) exited 0 after each task commit.
- STATE.md, ROADMAP.md, REQUIREMENTS.md, `.planning/config.json` and `milestone.lock` untouched by this plan.
- No real city figure or base-case total appears in any committed file; only the plan's synthetic targets.

---
*Phase: 04-per-city-scaling-of-the-39-bus-case*
*Completed: 2026-11-11*
