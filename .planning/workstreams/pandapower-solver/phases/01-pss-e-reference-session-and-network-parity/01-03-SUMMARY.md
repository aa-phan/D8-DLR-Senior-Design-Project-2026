---
phase: 01-pss-e-reference-session-and-network-parity
plan: 03
subsystem: testing
tags: [pss-e, laptop-session, reference-solution, contingency, voltage-margin, raw-snapshot, stdlib, python37]

requires:
  - phase: 01-pss-e-reference-session-and-network-parity
    provides: "plan 01-02: SessionContext, SectionResult, SECTION_FUNCTIONS table, WorkFolder members, call gate, raw_writer, FakeSessionPsspy"
provides:
  - "backend/psse_session/reference.py: run(ctx), the reference section; per city presolve.raw, solved.raw, base.json, outages.json, outage_<nnn>.raw, margin.json, margin_last_good.raw, margin_first_bad.raw"
  - "ctx.results['reference']: city -> status, detail, notes, margin_increments (increment_mw, first_bad_mw), sink_buses (for plan 01-04's stressed fingerprints)"
  - "backend/tests/psse_session_reference_test.py: 14 tests (PSE-03 on the fake)"
affects: [01-04, 01-09, 01-10]

plan_head_before: cc5c6abf982c42fea5c011a04a11f2a7f4d556db
plan_head_after: 5f6e26c5850f280dc010d4137ed10315e5831fcd

actuals:
  tokens: 13000
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "The reference is the job's own study: study.scale_city_case, study.prepare_city_base, contingency.select_outages and margin.city_margin are called directly, never re-implemented"
    - "Every outage and margin point starts from a fresh reload of the saved solved base; every outage of the job's list has exactly one record (converged, non-converged, or call_failed)"
    - "Extended reads go through the call gate directly and are recorded as status ok or unavailable with function and class or ierr, never silently missing"
    - "A failing city is recorded by the StudyFailed stage word (or exception class) only; its message, which can hold branch keys, is never stored"
    - "The saved .sav copies live in tmp_sav inside the work folder, are never members, and are removed with study.cleanup_base plus a per-city folder removal on every path"

key-files:
  created:
    - backend/psse_session/reference.py
    - backend/tests/psse_session_reference_test.py
  modified: []

key-decisions:
  - "A missing case index makes the reference section failed with ('no case index', stage), not skipped as the plan text said: plan 01-02's entry-script test and its documented interface guidance require failed, and 'skipped' is reserved for --only"
  - "The machine selection flag is tried as 2, 4, then 1 and the one that worked is recorded in machine_outputs.flag; the plan assumed 4 only, but the fake (frozen) models 1 and 2, and which flag real PSS/E accepts is unknown until plan 01-10"
  - "select_outages refusing is none_selected unless the message says the count exceeded contingency.max, which fails the city (both are stage contingency)"
  - "A city that fails at preparation gets a base.json with status failed and the stage word only, so a reader sees the failure inside the zip"
  - "Non-converged outages keep solve with the stale solved() code the adapter returns; the meaning text says solved() is not trusted after a failed fnsl"

requirements-completed: [PSE-03, PSE-01]

coverage:
  - id: D1
    description: "For each city in order, the pre-solve snapshot, the solved base, every outage of the job's own list and the margin limit points reach the zip, all produced by the job's own functions"
    requirement: "PSE-03"
    verification:
      - kind: unit
        ref: "backend/tests/psse_session_reference_test.py#test_tracer_reference_one_city_base_outages_and_margin_in_the_zip"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_session_reference_test.py#test_outage_list_equals_the_jobs_own_selection"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_session_reference_test.py#test_four_cities_in_order_with_integer_summary_counts"
        status: pass
    human_judgment: false
  - id: D2
    description: "A non-converged or islanded outage is recorded with its ierr and meaning and null states, never dropped; a refused extended read is recorded as unavailable"
    requirement: "PSE-03"
    verification:
      - kind: unit
        ref: "backend/tests/psse_session_reference_test.py#test_islanded_outage_is_recorded_not_dropped"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_session_reference_test.py#test_extended_read_refusals_are_recorded_as_unavailable"
        status: pass
    human_judgment: false
  - id: D3
    description: "Edges: parallel circuits are separate records, none selected is an empty list, members are sorted inside, no RAW export still writes the JSON, a missing index is a failure"
    requirement: "PSE-03"
    verification:
      - kind: unit
        ref: "backend/tests/psse_session_reference_test.py#test_parallel_circuits_are_separate_records"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_session_reference_test.py#test_none_selected_is_written_as_an_empty_list"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_session_reference_test.py#test_members_are_sorted_inside"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_session_reference_test.py#test_without_a_raw_export_the_json_members_are_still_written"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_session_reference_test.py#test_a_missing_case_index_is_a_failure_not_a_skip"
        status: pass
    human_judgment: false
  - id: D4
    description: "A failing city is isolated and named by stage only; no saved case copy is left or zipped; budget exhaustion keeps the records so far"
    requirement: "PSE-03"
    verification:
      - kind: unit
        ref: "backend/tests/psse_session_reference_test.py#test_a_failing_city_is_isolated_and_named_by_stage_only"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_session_reference_test.py#test_no_saved_case_copy_is_left_or_zipped"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_session_reference_test.py#test_budget_exhaustion_keeps_the_records_so_far"
        status: pass
    human_judgment: false
  - id: D5
    description: "The extended reads (abrn flag 4 with P, Q and MAXMVA; amachint, amachchar and amachreal and the machine selection flag), the RAW snapshots and the PSS/E solved numbers against REAL PSS/E 36.4"
    requirement: "PSE-03"
    verification:
      - kind: manual_procedural
        ref: "the session of plan 01-10 on the PSS/E laptop"
        status: unknown
    human_judgment: true
    rationale: "Only a fake psspy exists here. Whether the extended reads and the machine flag work on 36.4 and what PSS/E's solved numbers are can only be learned on the laptop."

duration: not captured
completed: 2026-11-17
status: complete
---

# Phase 1 Plan 03: The reference section Summary

**The session's reference section: for each city's scaled copy, PSS/E's full solved base, every outage the job screens and the voltage-margin limit points, all produced by the job's own study functions into the zip, with every non-converged outage and every refused read recorded instead of dropped.**

## Performance

- **Duration:** not captured (no start time was recorded at the beginning of this run)
- **Completed:** 2026-11-17T01:03Z (UTC)
- **Tasks:** 2 of 2
- **Files:** 2 created (1047 lines), none modified

## Accomplishments

- `reference.run(ctx)` plugs into `session.SECTION_FUNCTIONS["reference"]` with no edit to `session.py`. For each city in `constants.CITIES` order it loads the case, calls `study.scale_city_case` and writes `presolve.raw`, calls `study.prepare_city_base` into `tmp_sav/<city>` inside the work folder, and writes `solved.raw` and `base.json` (solve, buses, line flows, extended all-branch P, Q and MAXMVA, machine P and Q, `rating_source` static).
- `outages.json` has one record per outage of `contingency.select_outages(base)` in that order. Each outage reloads the saved solved base, trips the branch and solves; a converged outage gets `outage_<nnn>.raw`; an islanded outage (fnsl ierr 3) keeps its ierr and meaning with null states and no RAW file. On the placeholder case the keys and order equal an independent `select_outages` on a second fake (T-01-10).
- `margin.json` holds the row's details from `margin.city_margin` plus the solved state at the last good and (when it exists) first bad transfer, re-solved from the saved base with the sink subsystem and `scale_load`, each with a RAW snapshot. EL_PASO of the placeholder is bounded by the rating and has no first bad point; the other three have one.
- Edges: parallel circuits (keys ending -1 and -2) are separate records; `none_selected` is an empty list with the base kept; a count over `contingency.max` fails the city instead; members are sorted inside; with no RAW export every JSON member is still written with null snapshots.
- Isolation and cleanup: a city whose preparation fails is recorded by the stage word (or exception class) only, its other cities still run, the section is failed and the exit is 1, and a planted branch key appears in no output, manifest or member. No `.sav` file is left or zipped even with the work folder kept and even when a city fails after its copy was saved (T-01-11, T-01-13).
- The run-time budget is checked before each outage; running out records the outages already done, marks outages.json failed and fails the city at stage contingency.

## Task Commits

1. **Task 1: Tracer - reference answers for one city from the job's own functions** - `e41d038` (feat)
2. **Task 2: Four cities, edges and isolation for the reference answers** - `5f6e26c` (test)

**Plan metadata:** the SUMMARY commit that follows this file (docs).

Tracer feedback gate: after `e41d038` the tracer `<verify>` was re-run end to end (3 passed; the acceptance import check printed `ok`; the combined run with `psse_session_test.py` 30 passed after the fix noted in deviation 1) before Task 2 expanded.

## Verification Results

- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs backend/tests/psse_session_reference_test.py backend/tests/psse_session_test.py`: `41 passed in 1.34s` (no skips; 14 reference tests plus the 27 of plan 01-02, whose import and syntax gate now covers `reference.py`).
- Task 1 verify: the plan's "3 passed" is `3 passed` for the reference file at that commit.
- Acceptance import check `.venv/bin/python -I -B -c "import sys; sys.path.insert(0, 'backend'); from psse_session import reference; ..."`: prints `ok`.
- Frozen-job regression `psse_contract_test.py psse_api_test.py psse_entry_test.py psse_study_test.py private_data_guard_test.py -k "not owner_local"`: `148 passed, 1 deselected in 3.79s`.
- `.venv/bin/python -I -B backend/private_leak_scan.py --staged` before each commit: exit 0. Working-tree scan after Task 2: exit 0.
- Frozen-file gate (the plan's file list, checked per commit with `git diff-tree`): empty for both commits. Post-commit deletion check: no deletions.
- Two mutations were applied by hand and reverted to prove the tests bite: removing the per-city folder, tmp root and `cleanup_base` removal fails `test_no_saved_case_copy_is_left_or_zipped`; dropping the budget check and putting the failure message into the detail fails `test_none_selected_is_written_as_an_empty_list`, `test_a_failing_city_is_isolated_and_named_by_stage_only` and `test_budget_exhaustion_keeps_the_records_so_far`.

## Files Created

- `backend/psse_session/reference.py` - the section, its per-city, per-outage and margin-point helpers, the extended-read reader
- `backend/tests/psse_session_reference_test.py` - 14 tests; scenario solver `island_when_tie_two_is_out` and the `RefusesTheAllBranchRead` fake subclass live there

## Decisions Made

See `key-decisions` in the frontmatter. Interface notes for later plans:

- `ctx.results["reference"]` is an `OrderedDict` city -> `{"status", "detail", "notes", "margin_increments", "sink_buses"}`; `margin_increments` is `(increment_mw, first_bad_mw)` as floats or None and is None for a city whose margin step did not complete.
- Reference RAW members are registered by the session's own `raw_writer`, which files every export under the manifest section `network`, so manifest `sections[reference].members` lists only the JSON members. Plan 01-09's reader should locate RAW files by member name, not by manifest section.
- JSON extras beyond the plan's shapes: `status` in `base.json`, `failed_stage` in a failed `base.json` or `margin.json`, `flag` in `branch_flows` and `machine_outputs`, and `solve` and `call_failed` in margin points.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] A missing case index is `failed`, not `skipped`**
- **Found during:** Task 1 (first combined run with `psse_session_test.py`)
- **Issue:** The plan says `run(ctx)` returns `SectionResult("skipped", ("no case index",), {})` when `ctx.index` is None. With that, `test_entry_script_runs_under_isolated_mode_with_a_stub_psspy` (plan 01-02, case index fails on the stub) failed: it requires every section to be failed with a detail. Plan 01-02's summary also documents the convention (`("no case index", stage)`, failed), and `skipped` is the word `--only` uses.
- **Fix:** return `failed` with `("no case index", ctx.index_stage or "internal")`, as the network section does; added `test_a_missing_case_index_is_a_failure_not_a_skip`.
- **Files modified:** `backend/psse_session/reference.py`, `backend/tests/psse_session_reference_test.py`
- **Commit:** `e41d038` (the fix landed before Task 1's commit), test in `5f6e26c`

**2. [Rule 3 - Blocking] Machine selection flag tried as 2, 4, then 1**
- **Found during:** Task 1 (reading the frozen fake)
- **Issue:** The plan reads machines with `flag=4`, "assumed to mean all machines as for abrn". The frozen `FakeSessionPsspy` models machine flags 1 and 2 only and answers 4 with ierr 4, so with flag 4 alone every machine read would be unavailable on the fake and the plan's own "machine_outputs have status ok" behavior could not hold. The fake cannot be edited by this plan.
- **Fix:** `_Reader.machine_outputs` tries the flags in `MACHINE_FLAGS = (2, 4, 1)`, uses the first for which all three calls return ierr 0, caches it, records it in `machine_outputs.flag` and, when none works, records every refusal in `reason`. The plan's assumption (4) stays in the list. Flag 2 is "all machines" (in service or not), matching the `in_service` column.
- **Files modified:** `backend/psse_session/reference.py`
- **Commit:** `e41d038`

### Process notes

**3. Tests were not observed failing first.** As in plan 01-02, `reference.py` was written before the test file, so the first run was already green. The tests' ability to fail was checked afterwards by the two hand-made mutations above. The one test failure seen on first run (a wrong expectation that `solved_code` is None for an islanded outage; the adapter keeps the stale `solved()` code and the meaning says it is not trusted) was a test expectation, fixed in the test.

**4. Plan 01-03's "Task 2: fix reference.py wherever a test fails" needed no change:** all nine Task 2 tests passed against the Task 1 module, so the Task 2 commit touches only the test file.

**5. Branch allow-list and ledger.** The `agent-*` branch allow-list was not applied (sequential run on `feature/pandapower-solver` as dispatched); detached-HEAD and protected-branch checks and the supplied-root pin were run before the writes and each commit. The plan commit ledger is the scratchpad file `gsd-plan-head-before-01-03` (the sandbox refuses compound git forms); `commits: 2` was measured with `git rev-list --count cc5c6ab..HEAD`. The frozen-file gate script was run as simple separate commands for the same reason. No start time was captured, so no duration is given.

**Total deviations:** 1 Rule 1, 1 Rule 3, 3 process notes. **Impact:** none on the plan's outputs; the fixes keep the section aligned with plan 01-02's tests and the fake.

## Issues Encountered

None blocking. Two compound Bash commands were refused by the sandbox and rerun as plain separate commands.

## Known Stubs

None. (The settings and scaling sections of `session.SECTION_FUNCTIONS` still import modules that plan 01-04 adds; that is plan 01-02's stated design.)

## Threat Flags

None. No new network endpoint, auth path or schema; the section only reads through the call gate and writes inside the work folder.

## Threat Model Coverage

- T-01-10 (outage list and scaled copy): the section calls `study.scale_city_case`, `study.prepare_city_base`, `contingency.select_outages` and `margin.city_margin` directly; `test_outage_list_equals_the_jobs_own_selection` compares against an independent run.
- T-01-11 (temporary .sav copies): `tmp_sav` inside the work folder, `study.cleanup_base` plus a folder removal in `finally`, never a member; `test_no_saved_case_copy_is_left_or_zipped` keeps the work folder and finds no copy.
- T-01-12 (non-converged outages): one record per outage with ierr, code, meaning or call failure; `test_islanded_outage_is_recorded_not_dropped`.
- T-01-13 (StudyFailed messages): stage word or class only; `test_a_failing_city_is_isolated_and_named_by_stage_only` plants a fake branch key and checks every output.
- T-01-SC: nothing was installed.

## Open Items For Later Plans

- Everything about real PSS/E (D5 above) is for the session of plan 01-10: whether `abrnreal` accepts `Q` with flag 4, which `amach*` flag works, whether the RAW snapshots of a solved case carry the solved voltages, and PSS/E's numbers themselves.
- Plan 01-04's stressed fingerprints can read `ctx.results["reference"][city]["margin_increments"]` and `["sink_buses"]`; a city whose margin step failed has `margin_increments` None.
- A refused extended read is retried for every solved state (about 134 states per city set); on real PSS/E that is cheap, but if it proves slow a first-state cache of refusals is a one-line change.

## Next Phase Readiness

Ready for plan 01-04 (settings and scaling probes) and, later, plan 01-09's reader: the member layout and JSON shapes in this summary are final.

## Self-Check: PASSED

- FOUND: `backend/psse_session/reference.py`, `backend/tests/psse_session_reference_test.py`
- FOUND commits: `e41d038`, `5f6e26c` (both ancestors of HEAD)
