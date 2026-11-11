---
phase: 04-per-city-scaling-of-the-39-bus-case
plan: 05
subsystem: psse-probe-and-docs
tags: [pss-e, probe, scale_to_target, runbook, study-note, doc-tests, unverified-register, fake-psspy, python37]

requires:
  - phase: 04-per-city-scaling-of-the-39-bus-case
    provides: "PsseApi.read_totals and scale_case with SCALE_LAYOUT, the fake's whole-case scal_2 (04-02); the per-city study with study.SCALE_TOLERANCE, SCALE_FACTOR_BOUNDS, SCALING_METHOD (04-03); the combined failure text (04-04)"
provides:
  - "probe._PROBE_SCALE_FRACTION and _Probe.scale_to_target, registered as the last write-check row: totals read, whole case scaled to 90 percent of its own load and generation, totals read back, case reloaded in a finally block, totals compared; PASS, FAIL or SKIP with a detail that prints no figure; never saves"
  - "A study-note section '## Per-city scaling (SCL-01 to SCL-06)' pinned to study.py by test_doc_scaling_section_matches_study_constants, with the failure stages, A13 (increment form only), new A19 to A22, the fake's limits and the representability note brought up to date"
  - "Runbook step 4 (how to read the scaling call's layout, what scale_to_target must show, stop rules) and step 5 (version 2 throwaway-mapping recipe with placeholder targets, study_seconds of the four-city dry run), register rows U35 to U38, a pasting rule for layout notes; setup guide first checks and troubleshooting rows; test_scaling_claims_are_registered_and_cited"
affects: [04-06-laptop-check]

actuals:
  tokens: 7900
  tasks: 3
  commits: 3
plan_head_before: 53706ddbb38def661c27eac79ab5268ee9b12928
plan_head_after: 746f246a06a90596b143cbfdb8756c7644c3b15c

tech-stack:
  added: []
  patterns:
    - "A probe row that uses the case's own totals as its targets, so it needs and prints no city figure"
    - "Doc numbers computed in the test from the code's constants (tolerance as a percent, bounds, method text, schema version, bases) so they cannot drift"
    - "Register rows U35 to U38 cited by tags at the step that clears them; a layout read from documentation is recorded as read, with the unproven details left open"

key-files:
  created: []
  modified:
    - backend/psse_job/probe.py
    - backend/tests/psse_probe_test.py
    - backend/tests/psse_laptop_modes_test.py
    - backend/tests/psse_rehearsal_test.py
    - docs/data-science/decisions/psse_study_definitions.md
    - backend/tests/psse_study_doc_test.py
    - docs/data-science/decisions/psse_laptop_runbook.md
    - docs/data-science/decisions/psse_laptop_setup.md
    - backend/tests/psse_setup_doc_test.py

key-decisions:
  - "scale_to_target compares the read-back with each target using the study's own SCALE_TOLERANCE and the same inverted form (not abs(read - target) <= tol * target), so a NaN would count as a miss; the reload check uses the probe's existing _RATING_TOLERANCE and takes priority over a missed target, as rating_write does"
  - "Both FAIL details name the quantity but no figure: 'the load total read back differs from the target by more than the tolerance' (or generation), and 'reloading the case did not restore the totals'"
  - "The documentation reading of 2026-11-10 (PSS/E 36.4, scal_2 marked obsolete and implemented by scal_4) is stated in the note (A19) and in runbook step 4 and register row U35 as read and matching, with the bare-totals-read and all-default-read details kept open; psse_api.py's UNVERIFIED marking was not touched (not in this plan's files)"
  - "Runbook steps stay 0 to 10 and the study note keeps eight numbered questions; the Phase 4 questions are plain bullets inside the new section"

requirements-completed: [SCL-06, SCL-02, SCL-04, SCL-05]

coverage:
  - id: D1
    description: "With the write check, the probe has a scale_to_target row right after scale_load that reads totals, scales the whole case to 90 percent, reads back, reloads and compares; the case is never saved and its sha256 is unchanged; without the write check there is no such row"
    requirement: "SCL-06"
    verification:
      - kind: unit
        ref: "backend/tests/psse_probe_test.py#test_scale_to_target_scales_reads_back_and_restores"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_probe_test.py#test_report_write_check_off_by_default"
        status: pass
      - kind: integration
        ref: "backend/tests/psse_laptop_modes_test.py#test_probe_mode_write_check_and_exit_codes and backend/tests/psse_rehearsal_test.py (probe write-check rehearsal)"
        status: pass
    human_judgment: false
  - id: D2
    description: "The row fails when the whole-case call is ignored or when a reload keeps the scaling, skips a case without generation, and prints none of the case's or the targets' figures in a passing or failing report"
    requirement: "SCL-06"
    verification:
      - kind: unit
        ref: "backend/tests/psse_probe_test.py#test_scale_to_target_detects_an_ignored_scaling"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_probe_test.py#test_scale_to_target_detects_a_reload_that_keeps_the_scaling"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_probe_test.py#test_scale_to_target_skips_a_case_without_generation"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_probe_test.py#test_scale_to_target_prints_no_figure"
        status: pass
    human_judgment: false
  - id: D3
    description: "The study note's per-city scaling section quotes SCALING_METHOD verbatim and the tolerance, bounds, schema version, bases, contingency id form, the never-run .idv rule, power factor kept and the combined failure text, and the failure stages, A13, A19 to A22, the fake's limits and the representability note are updated; still eight numbered questions and no identifier"
    requirement: "SCL-02"
    verification:
      - kind: unit
        ref: "backend/tests/psse_study_doc_test.py#test_doc_scaling_section_matches_study_constants"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_study_doc_test.py#test_doc_has_required_sections"
        status: pass
    human_judgment: false
  - id: D4
    description: "Runbook steps 4 and 5 and the guide tell the laptop session how to read the scaling layout (installed documentation or a placeholder recording on the example copy, never a city script), what scale_to_target must show, how to build the version 2 throwaway mapping and what to record; register rows U35 to U38 are cited at steps 4 and 5; the step headings stay 0 to 10"
    requirement: "SCL-06"
    verification:
      - kind: unit
        ref: "backend/tests/psse_setup_doc_test.py#test_scaling_claims_are_registered_and_cited"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_setup_doc_test.py#test_unverified_tags_cite_existing_runbook_steps"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_setup_doc_test.py#test_docs_hold_no_secret_identifier_or_real_path"
        status: pass
    human_judgment: false
  - id: D5
    description: "Whether real PSS/E scales the whole case as SCALE_LAYOUT says (including a bare APIOPT 1 totals read leaving scaling usable and an all-default read being accepted), whether a reload undoes it, whether the mode keeps each load's power factor, and whether a four-city dry run fits the 1500 s budget"
    requirement: "SCL-06"
    verification: []
    human_judgment: true
    rationale: "The probe row and the four-city run pass on the fake by construction; only plan 04-06's laptop session turns U35 to U38 into evidence"

duration: about 1h 10min of wall-clock, of which about 10 min were the plan-end gate run
completed: 2026-11-11
status: complete
---

# Phase 4 Plan 05: Probe row and written checks for the per-city scaling Summary

**`probe --write-check` now ends with a `scale_to_target` row that scales the whole case to 90 percent of its own load and generation with the adapter's call, reads the totals back, reloads the case and checks the totals are restored (no figure printed, never saved), and the study note, runbook (steps 4 and 5, register rows U35 to U38) and setup guide say how the laptop session proves the layout and times a four-city dry run, with the note's numbers pinned to `study.py`.**

## Performance

- **Duration:** about 1h 10min wall-clock (about 10 min of it the plan-end gate)
- **Tasks:** 3 (the first a tracer)
- **Files:** 9 modified, none created (302 insertions, 25 deletions)

## Accomplishments

- `_Probe.scale_to_target` (PD-1): `read_totals`; SKIP "the case has no load or no generation to scale" unless both are above 0; in try/finally (the finally always reloads the case) `scale_case(0.9 x load, 0.9 x generation)` then `read_totals`, a problem per quantity when the relative error exceeds `study.SCALE_TOLERANCE`; after the reload the totals must equal the originals within `_RATING_TOLERANCE` relative, else FAIL "reloading the case did not restore the totals"; PASS "the whole case was scaled to 90 percent of its own load and generation, read back at the targets and restored by reloading the case". Registered right after `scale_load`, under `write_check` only. The module docstring's write-check list has the sentence the plan asked for.
- Tests: `WRITE_CHECKS` gains the row; `test_report_write_check_off_by_default` now expects one increment call then four whole-case calls with the write check and none without; five new probe tests (restore and call log, ignored scaling, reload that keeps the scaling, no generation, no figure in a passing or failing report with or without identifiers); the launcher and rehearsal probe write-check tests expect the row (and its absence without `--write-check`).
- Study note: new `## Per-city scaling (SCL-01 to SCL-06)` between the dispatched-capacity and failure-stage sections (one fresh copy per city, the version 2 block, the job's own call and no script ever run, power factor kept, the guards, what is stored, one failed run naming every city, what the fake proves, and three plain bullets "Open with Power Systems": the same lines in every copy, El Paso's basis, the base power factor). `mapping`, `apply_ratings` and `load_flow` stage rows mention the scaling causes, a sentence under the table says one failure fails the run once, A13 says increment form only, A19 to A22 are new, and the fake's limits and the representability bullet are updated.
- Runbook: step 4 explains how to read `SCALE_LAYOUT` against the installed API documentation (SCAL_2, and SCAL_4 if listed) or, on the example copy only, with a recorded call using placeholder numbers, and says never to open, run or paste a recorded city script; it states what `scale_to_target` must show and gives two stop rules for its FAIL details. Step 5 gives the version 2 throwaway-mapping recipe (placeholder targets as round fractions of the example case's own totals, `basis` average, never a city's figure) and asks for `study_seconds` of the four-city run. Register rows U35 to U38 are added per PD-3; "Pasting results safely" gains the positions-and-meanings rule. The step table's rows 4 and 5 are updated. The guide's first checks and troubleshooting carry the same facts.

## How the 2026-11-10 documentation reading was used

Recorded as read and matching, nowhere as verified on the engine. The note (A19), runbook step 4 and register row U35 say the installed PSS/E 36.4 documentation was read on 2026-11-10, that every position of `SCALE_LAYOUT` matches, and that `scal_2` is marked obsolete there and implemented by `scal_4`, which exists. Two details are kept explicitly open: whether a bare totals read (APIOPT 1, not followed by APIOPT 2) leaves scaling half-initialised, and whether an all-default read is accepted. U35 to U38 all stay in the register as pending; `psse_api.py` (not one of this plan's files) still carries its UNVERIFIED marking. No documentation text is quoted: positions and meanings only.

## TDD record

Plan type is `execute` with `tdd="true"` tasks; `workflow.tdd_mode` is not enabled, so RED evidence was not submitted to `gsd_run check tdd-red-evidence`. The plan specifies one commit per task.

- **Task 1 RED:** with the probe, launcher and rehearsal tests written, `psse_probe_test.py` ran 26 tests and 7 failed on the planned assertion: the `scale_to_target` row was missing (`KeyError: 'scale_to_target'` in five tests, the no-row `assert "scale_to_target" in passing`, the tracer's all-PASS loop and the changed call-list pin). No import, collection or fixture fault. **GREEN:** `26 passed` (`psse_probe_test.py` plus `psse_contract_test.py`), and the two Postgres files `18 passed`. One test-author slip was caught on the way: my first rehearsal edit put an `else` before an existing `assert "in memory only"`, which made the non-write-check probe run fail that assertion; it was fixed before the GREEN run and no production code was involved.
- **Task 2 RED:** the heading in `REQUIRED_HEADINGS` and the new constants test failed because the section did not exist (`ValueError: substring not found` in `_section`, 2 failed, 6 passed). **GREEN:** `8 passed`.
- **Task 3 RED:** `test_scaling_claims_are_registered_and_cited` failed with `KeyError: 'U35'` (no register row yet). **GREEN:** `20 passed` for `psse_setup_doc_test.py` plus `psse_rehearsal_test.py`, no skips.
- No REFACTOR commit.

## Task Commits

1. **Task 1: Tracer, the probe's scale_to_target row** - `344bc98` (feat)
2. **Task 2: Per-city scaling section in the study note** - `d99ee9d` (docs)
3. **Task 3: Runbook and guide, register rows U35 to U38** - `746f246` (docs)

**Plan metadata:** the commit holding this SUMMARY (docs). STATE.md, ROADMAP.md and REQUIREMENTS.md are not edited here (the orchestrator owns them).

## Mutation checks (plant, see red, restore byte for byte; SHA-256 equal after each)

| Planted fault | Result |
|---|---|
| skip the reload in `scale_to_target` (the finally does nothing) | red: `test_scale_to_target_scales_reads_back_and_restores` and the tracer `test_tracer_probe_against_fake_all_pass`. `test_scale_to_target_detects_a_reload_that_keeps_the_scaling` stays green by design: it already expects FAIL from a fake whose own reload is a no-op, so it guards the check, not the reload call. The no-save assertion is not the one that catches this mutation; the totals-restored check does |
| print the case's load total in the PASS detail | red: `test_scale_to_target_prints_no_figure` (and the exact-detail assertion in the restore test) |
| change `SCALING_METHOD` by one word without the doc (study.py planted, then restored; SHA-256 `c43240ce...` equal) | red: `test_doc_scaling_section_matches_study_constants` |
| drop the U38 tag from step 5 only | red: `test_scaling_claims_are_registered_and_cited` (step 5 must hold `(U38)`). `test_unverified_tags_cite_existing_runbook_steps` stays green because the guide's first check cites U38 too, so the row is still cited; the plan expected that test to go red, it does not for this plant |

## Deviations from Plan

None - plan executed as written, with these notes that are not behaviour changes:

- The two mutation expectations above differ from the plan's wording (which test catches which plant); the planted faults are caught, by the tests named in the table.
- Test pins touched beyond the plan's list: the `names.count("case")` bound in `psse_laptop_modes_test.py` rose from 3 to 4 (the load plus three reloads) and gained an assertion that a whole-case scale call was made; `test_report_write_check_off_by_default` now also asserts no whole-case call without the write check.
- The runbook header "From" line and rows 4 and 5 of the step table were updated to name the new content; no step heading and no command block changed.

## Issues Encountered

- **Plan-end gate** (`backend/tests/psse_*_test.py` plus `secret_scan_test.py`, plan PATH and flags): `2 failed, 735 passed, 1 skipped, 19 errors` in 587 s. `backend/tests/psse_results_migration_test.py` run alone gives `2 failed, 4 passed, 19 errors`, so that file is the only one with failures or errors: the known unrelated problem (core.autocrlf rewrites `supabase/migrations/20261109233541_psse_results.sql` to CRLF so its pinned SHA-256 differs, and its Postgres fixture then errors on `pg_ctl start`). The one skip is `secret_scan_test.py:316`, the owner-local check that needs `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` and `SUPABASE_DB_URL`. The plan-end wording "exits 0 with no skipped test" therefore does not hold on this machine, for reasons that predate this plan. Each task's own `<automated>` commands passed with no skip: Task 1 `26 passed` and `18 passed`, Task 2 `8 passed`, Task 3 `20 passed`.
- A Bash heredoc holding Python with apostrophes inside triple quotes failed to parse once (nothing was written); the runbook and guide edits were redone with scripts written through the Write tool. `psse_laptop_setup.md` is CRLF in the working tree (core.autocrlf); the edit script preserved that.
- `git` warns that LF will be replaced by CRLF in some edited files; no content effect.

## Known Stubs

None. The probe row and the documents hold no placeholder that flows into an output. The placeholder figures 1111, 2222 and 3333 in runbook step 4 are deliberate, obvious dummies for a recording on PSS/E's own example copy.

## Threat Flags

None beyond the plan's register. T-04-14 (the probe altering or saving the case): mitigated; the row reloads in a finally block, checks the totals are restored, the restore test asserts no save call, `fake_saved_paths == []` and an unchanged file sha256, and the skip-reload plant turns two tests red. T-04-15 (a case total or city figure in probe output or pasted notes): mitigated; no row detail holds a figure (`test_scale_to_target_prints_no_figure` covers a passing and a failing report, with and without identifiers), the runbook adds "positions and meanings only", and the doc identifier gates still pass. T-04-16 (an instruction leading to a recorded city script): mitigated; step 4 says never to open, run or paste a recorded city script and allows a recording only on the example copy with placeholder numbers, and `test_scaling_claims_are_registered_and_cited` checks the wording.

## Register rows handed to plan 04-06 (all pending, none cleared)

| Row | Step | Claim | Evidence that clears it |
|---|---|---|---|
| U35 | 4 | The whole-case scaling layout of `SCALE_LAYOUT` is right on PSS/E 36.4 (documentation read 2026-11-10 and matching on every position; a bare totals read and an all-default read are the open details) | the documentation or a recorded call line with placeholder numbers matching `SCALE_LAYOUT`, and `scale_to_target` PASS |
| U36 | 4 | Reloading the case undoes a whole-case scaling | `scale_to_target` PASS |
| U37 | 4 | The scaling mode keeps each load's power factor | the load-type status slot's documentation, or one load's P and Q read before and after a recorded scaling of the example copy |
| U38 | 5 | A four-city dry run on the example case with a version 2 throwaway mapping completes within the 1500 s budget | the dry run exit 0 with four dispatch rows, `validation: ok` and `study_seconds` recorded |

## Next Phase Readiness

- Plan 04-06 (laptop check) has its instructions: run step 4 (read the layout, then `probe --write-check` and look for `scale_to_target` PASS) and step 5 (the version 2 throwaway mapping, `study_seconds`). A FAIL row has a written stop rule: a "differs from the target" detail means correct `SCALE_LAYOUT` (one table) on the Mac, a "did not restore the totals" detail means a gap-closure plan for the per-city load.
- If U35 to U38 clear, `psse_api.py`'s `SCALE_LAYOUT` evidence and confidence can be updated in that plan, together with the register rows and the note's A19 to A21.

## Self-Check: PASSED

- Files exist: `backend/psse_job/probe.py`, `backend/tests/psse_probe_test.py`, `backend/tests/psse_laptop_modes_test.py`, `backend/tests/psse_rehearsal_test.py`, `docs/data-science/decisions/psse_study_definitions.md`, `backend/tests/psse_study_doc_test.py`, `docs/data-science/decisions/psse_laptop_runbook.md`, `docs/data-science/decisions/psse_laptop_setup.md`, `backend/tests/psse_setup_doc_test.py`.
- Commits `344bc98`, `d99ee9d`, `746f246` are ancestors of HEAD; `git rev-list --count 53706dd..HEAD` was 3 before this summary's commit (no deleted files in any of them).
- `grep -c "def scale_to_target" backend/psse_job/probe.py` is 1 (baseline 0); `grep -c "^## Per-city scaling (SCL-01 to SCL-06)$"` on the study note is 1; `grep -c "^| U3[5-8] "` on the runbook is 4; `grep -c "^| A19 \|^| A2[0-2] "` on the note is 4.
- Own-changes gate (PLAN=04-05) exited 0 after each task commit.
- STATE.md, ROADMAP.md, REQUIREMENTS.md, `.planning/config.json` and `milestone.lock` untouched by this plan.
- No real city figure or base-case total appears in any committed file; only the placeholder case's synthetic totals, and those only in test files.

---
*Phase: 04-per-city-scaling-of-the-39-bus-case*
*Completed: 2026-11-11*
