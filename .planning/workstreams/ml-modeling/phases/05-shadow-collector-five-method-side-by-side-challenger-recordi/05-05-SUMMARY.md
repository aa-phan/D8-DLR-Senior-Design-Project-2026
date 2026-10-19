---
phase: 05-shadow-collector-five-method-side-by-side-challenger-recordi
plan: 05
subsystem: data-science
tags: [shadow-collector, jsonl-schema, markdown-render, github-actions, runbook]

# Dependency graph
requires:
  - phase: 05-shadow-collector-five-method-side-by-side-challenger-recordi
    provides: "The approved schema_version:2 nested-per-candidate shape and no-migration historical-data strategy (05-01); the five-candidate orchestration wired at both corridors (05-03); the real reference_ml_refit_24h artifact and live predict path (05-04)"
provides:
  - "forecast_shadow_render_table.py renders both the pre-cutover flat shape and the new schema_version:2 nested shape forever, per-line, in the same mixed file"
  - "forecast_shadow_healthcheck.py proven (by a new test, not just argued) to need zero code change against the new shape"
  - "A dated D-08 runbook note stating when five-method collection started and its relationship to the Nov 1/Nov 24 protocol"
  - "A real, confirmed GitHub Actions dispatch (run 37693876732) producing the five-candidate schema_version:2 shape on shadow-collection-data for both corridors"
  - "A runbook subsection naming the exact command to confirm the next cron-triggered run, honestly distinguished from today's manual dispatch"
affects: []

# Actuals (#2632)
actuals:
  tokens: 9500
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-line shape detection: entry.get('schema_version', 1) >= 2 branches rendering without ever assuming a corridor file is shape-homogeneous"
    - "Regression-pin by independent reconstruction: the old-shape byte-identical test hand-reconstructs the expected table text rather than calling the new code, so it is a real pin, not a tautology"

key-files:
  created: []
  modified:
    - backend/forecast_shadow_render_table.py
    - backend/tests/forecast_shadow_render_table_test.py
    - backend/tests/forecast_shadow_healthcheck_test.py
    - docs/data-science/decisions/shadow_collection_runbook.md
    - ACKNOWLEDGEMENTS.md

key-decisions:
  - "CANDIDATE_METHOD_NAMES duplicated as a local tuple in forecast_shadow_render_table.py rather than imported from forecast_shadow_pipeline.py, to keep this pure-function, network-free render script from pulling in pandas/scikit-learn/dotenv it doesn't otherwise need."
  - "Mixed-shape rendering reopens/closes the legacy table around interleaved new-shape blocks (tracked via a legacy_table_open flag) rather than grouping by shape, preserving true most-recent-first order across both shapes in one document."

requirements-completed: [D-06, D-08, D-09, D-10, D-11]

coverage:
  - id: D1
    description: "render_markdown renders old-shape rows byte-identically (regression-pinned) and new-shape rows with all five candidates, their reasons, and escaping discipline; mixed-shape files render both correctly in one document"
    requirement: "D-06"
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_render_table_test.py (6 new tests: byte-identical regression pin, new-shape-all-five, unavailable-reason, mixed-shape)"
        status: pass
      - kind: other
        ref: "RENDER_BOTH_SHAPES_OK printed by the plan's own verification script"
        status: pass
    human_judgment: false
  - id: D2
    description: "forecast_shadow_healthcheck.py requires zero code change and reports the correct verdict against a new-shape row, proven by a test"
    requirement: "D-06"
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_healthcheck_test.py::test_check_reports_the_same_verdict_for_a_new_shape_schema_version_2_row"
        status: pass
      - kind: other
        ref: "git diff --quiet HEAD -- backend/forecast_shadow_healthcheck.py -> HEALTHCHECK_UNCHANGED_OK"
        status: pass
    human_judgment: false
  - id: D3
    description: "shadow_collection_runbook.md carries a dated D-08 note stating when five-method recording began, naming all five candidates, and stating its relationship to the Nov 1/Nov 24 protocol in language consistent with forecast_correction_followup_audit.md's own carve-out"
    requirement: "D-08"
    verification:
      - kind: other
        ref: "RUNBOOK_D08_NOTE_OK and FROZEN_AUDIT_RECORD_UNTOUCHED_OK both printed by the plan's own verification scripts"
        status: pass
    human_judgment: false
  - id: D4
    description: "A real gh workflow run dispatch confirmed the full pipeline end to end on the actual CI runner, within the 15-minute budget, producing the new five-candidate shape on shadow-collection-data; the next-scheduled-run confirmation is documented as an honest, dated follow-up"
    requirement: "D-10"
    verification:
      - kind: other
        ref: "gh run 37693876732 (workflow_dispatch), completed success in ~1m2s; git fetch origin shadow-collection-data + direct JSONL parse -> WORKFLOW_DISPATCH_PRODUCED_NEW_SHAPE_OK; NEXT_SCHEDULED_RUN_DOC_OK printed"
        status: pass
    human_judgment: false
  - id: D5
    description: "This plan's own SUMMARY describes operational completeness and physical plausibility only, with no comparative accuracy/reliability/safety claim between candidates"
    requirement: "D-11"
    verification: []
    human_judgment: true
    rationale: "Whether the SUMMARY's own language stays inside the D-11 boundary is a textual/judgment question about THIS document, not something a test asserts against; reviewed manually against D-11's exact wording before writing the sections below."

duration: ~13 min
completed: 2026-10-07
status: complete
---

# Phase 5 Plan 5: Both JSONL Shapes Forever, D-08 Runbook Note, Real GitHub Actions Confirmation Summary

**`forecast_shadow_render_table.py` now renders both the pre-cutover flat shape and the new `schema_version:2` nested shape forever (byte-identical for old rows, all-five-candidate blocks for new rows), `forecast_shadow_healthcheck.py` is proven to need zero change, the runbook carries a dated D-08 note, and a real `gh workflow run` dispatch (run `37693876732`) confirmed the expanded five-candidate shape persists end to end on the actual CI runner in ~1m2s.**

## Performance

- **Duration:** ~13 min
- **Started:** 2026-10-07T21:58:03Z
- **Completed:** 2026-10-07T22:11:00Z
- **Tasks:** 3/3 completed
- **Files modified:** 5 (`backend/forecast_shadow_render_table.py`, 2 test files, the runbook, `ACKNOWLEDGEMENTS.md`)

## Accomplishments

- `render_markdown` branches per-line on `entry.get("schema_version", 1) >= 2`: old-shape rows render via the exact, unchanged legacy single-row logic (proven byte-identical via a hand-reconstructed regression pin, not merely re-running the new code against itself); new-shape rows render a dedicated all-five-candidate sub-section with status/ampacity/fallback/model_version/reason per candidate, using the same pipe/newline/100-char escaping discipline the legacy branch already used. A file mixing both shapes (the real situation from the cutover forward) renders both correctly, in true most-recent-first order, in one document.
- Added one new test to `forecast_shadow_healthcheck_test.py` that constructs a real `schema_version: 2` fixture entry and confirms `check` reports the identical healthy verdict and status string it would for an equivalent old-shape row — `forecast_shadow_healthcheck.py` itself carries zero diff, confirmed via `git diff --quiet`.
- Added a dated "Five-method collection (D-08)" section to `shadow_collection_runbook.md` naming the exact start date (2026-10-07), all five candidate names, and quoting `forecast_correction_followup_audit.md`'s own mechanical-health-check carve-out verbatim — stating plainly that this shadow data is additional observational evidence, independent of and not a substitute for the Nov 1/Nov 24 fresh-basis confirmation protocol. `forecast_correction_followup_audit.md` itself carries zero diff.
- Dispatched the real "Shadow Collection" GitHub Actions workflow (`gh workflow run`), watched it complete (`gh run watch`), and confirmed via `git fetch origin shadow-collection-data` plus a direct JSONL parse that the newly committed lines for both corridors carry `schema_version: 2` with all five candidate names. Added a "Confirming the next SCHEDULED run" runbook subsection naming the exact command and the exact next cron boundary (2026-10-08T06:00:00 UTC), explicitly distinguishing it from today's manual-dispatch confirmation.

## Task Commits

1. **Task 1: Render both shapes correctly, forever -- and prove the legacy health check needs no change** - `45da693` (feat) -- 20/20 tests pass; `HEALTHCHECK_UNCHANGED_OK` and `RENDER_BOTH_SHAPES_OK` both confirmed.
2. **Task 2: Document when five-method collection started and how it relates to the Nov 1/Nov 24 protocol (D-08)** - `301e0af` (docs) -- `RUNBOOK_D08_NOTE_OK` and `FROZEN_AUDIT_RECORD_UNTOUCHED_OK` both confirmed.
3. **Task 3: Confirm the real GitHub Actions run end to end, and document the next-scheduled-run confirmation honestly** - `29d8a2d` (docs) -- real `gh workflow run` dispatch (run `37693876732`) completed success in ~1m2s; `WORKFLOW_DISPATCH_PRODUCED_NEW_SHAPE_OK` and `NEXT_SCHEDULED_RUN_DOC_OK` both confirmed.

**Plan metadata:** recorded in the closing docs commit (see final commit for this plan).

## Files Created/Modified

- `backend/forecast_shadow_render_table.py` — added `CANDIDATE_METHOD_NAMES` (duplicated, not imported, to stay dependency-light), `_escape_note`, `_render_legacy_row`, `_render_new_shape_block`; `render_markdown`'s per-corridor loop restructured to branch per-entry on `schema_version`.
- `backend/tests/forecast_shadow_render_table_test.py` — 6 new tests (byte-identical old-shape regression pin, new-shape all-five-candidates, unavailable-candidate reason visibility, mixed-shape-in-one-file).
- `backend/tests/forecast_shadow_healthcheck_test.py` — 1 new test proving zero-code-change compatibility against a new-shape row.
- `docs/data-science/decisions/shadow_collection_runbook.md` — new "Five-method collection (D-08)" section, an input-contract-table addendum naming the four new candidates' accrual, and a new "Confirming the next SCHEDULED run (D-10)" subsection.
- `ACKNOWLEDGEMENTS.md` — AI-use disclosure entry for this session, per ECE 464 policy.

## Decisions Made

- `CANDIDATE_METHOD_NAMES` is duplicated as a local tuple in `forecast_shadow_render_table.py` rather than imported from `forecast_shadow_pipeline.py`, matching this module's own "network-free, dependency-light, pure function" design goal — importing the pipeline module would pull in pandas/scikit-learn/dotenv the render script never otherwise needs.
- Mixed-shape rendering tracks a `legacy_table_open` flag so consecutive old-shape rows share one continuous table (byte-identical to the pre-task behavior when the file is old-shape-only) while a new-shape row in between closes it and opens its own block, preserving true most-recent-first interleaving across both shapes rather than grouping all old rows before all new rows.

## Deviations from Plan

None — plan executed exactly as written. All three tasks' `<action>`/`<verify>` blocks matched this implementation with no architectural changes, no missing-package blockers, and no checkpoint required (`gh` was already authenticated in this environment).

## Issues Encountered

None. `gh auth status` confirmed an authenticated session before Task 3 began, so the plan's own documented contingency (report a blocker if `gh` auth is unavailable) did not apply.

## User Setup Required

None — no external service configuration required. The real GitHub Actions dispatch used this environment's existing `gh` CLI authentication; no new secrets or credentials were configured by this plan.

## Next Phase Readiness

This is the phase's final plan. All five D-10 verification components are now satisfied except the one D-10 itself defines as necessarily deferred: the next **scheduled** (cron-triggered) GitHub Actions run's confirmation. That boundary is **2026-10-08T06:00:00 UTC** — the runbook's own "Confirming the next SCHEDULED run" subsection names the exact command (`git fetch origin shadow-collection-data && git log -1 --format=%cI origin/shadow-collection-data`, plus a `gh run list` filter for `"event": "schedule"`) for whoever checks it after that boundary passes. **This confirmation has NOT happened yet and must not be read as already satisfied** — today's work confirms only the manual dispatch.

Per D-11, this plan's own report is strictly operational: all three real/plausible candidates (`ml_wind_corrected`, `ml_cooling_corrected`, `raw_forecast`) returned positive ampacity values at both corridors on today's dispatch; `persistence_24h` and `reference_ml_refit_24h` both reported honest, specifically-named `unavailable` reasons (a decision-time-available anchor not yet within tolerance, and no usable live station row within the truth-proxy window's tolerance, respectively) — expected, not defects. No claim is made, here or anywhere else in this plan's artifacts, about which candidate is more accurate, better-calibrated, or safer than another; that question remains reserved for the Nov 1/Nov 24 fresh-basis confirmation protocol on its own fixed schedule.

Per this project's standard conventions, whether phase-level verification (a VERIFICATION.md or equivalent cross-plan check for Phase 5) should now run is a decision for the orchestrating workflow, not this plan — flagging it here rather than attempting it as part of this plan's own scope.

---
*Phase: 05-shadow-collector-five-method-side-by-side-challenger-recordi*
*Completed: 2026-10-07*

## Self-Check: PASSED

- `backend/forecast_shadow_render_table.py` - FOUND
- `backend/tests/forecast_shadow_render_table_test.py` - FOUND
- `backend/tests/forecast_shadow_healthcheck_test.py` - FOUND
- `docs/data-science/decisions/shadow_collection_runbook.md` - FOUND
- This SUMMARY.md - FOUND
- Commit `45da693` - FOUND in `git log --oneline --all`
- Commit `301e0af` - FOUND in `git log --oneline --all`
- Commit `29d8a2d` - FOUND in `git log --oneline --all`
