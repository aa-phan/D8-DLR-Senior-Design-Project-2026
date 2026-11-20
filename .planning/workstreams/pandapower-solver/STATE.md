---
gsd_state_version: "1.0"
milestone: v1.7
milestone_name: pandapower Solver
current_phase: 02
current_phase_name: PandapowerApi and Study Engine
current_plan: 7
status: verifying
stopped_at: "Phase 2 plans 02-01 to 02-07 complete (ENG-05 closed 2026-11-20); ready for Phase 2 verification; ENG-06 and the database proofs need a Postgres"
last_updated: "2026-11-20T22:48:53.555Z"
last_activity: 2026-11-20
last_activity_desc: Phase 1 complete, transitioned to Phase 02
state_head: 0ef35dca620672a9613221399be8e1866042d3d7
progress:
  total_phases: 6
  completed_phases: 1
  total_plans: 23
  completed_plans: 23
---

# Project State

## Project Reference

See: .planning/PROJECT.md (shared). Builds on the pss-e-integration workstream (v1.6, complete 2026-11-16).

**Core value:** The dashboard always has fresh hourly power-flow results for each city's rating, without depending on a licensed PSS/E machine.
**Current focus:** Phase 01 — PSS/E Reference Session and Network Parity

## Accumulated Context

### Decisions (milestone start, 2026-11-16, by the owner)

- pandapower is the always-on source of results for the dashboard; PSS/E stays the industry reference and is unchanged.
- Runs hourly in GitHub Actions.
- Results go into the same four `psse_*` tables with a new `solver` column (existing 19 rows tagged `psse`); one migration.
- Writes as the existing `dlr_psse_writer` role; its password and the private per-city mapping become GitHub secrets.
- Agreement is checked by replaying the recorded PSS/E runs (their stored ratings) through pandapower: same overload and voltage-violation set per outage, bus voltages within 0.01 pu, flows and capacities within 2%.
- Done: results land every hour for a full day and the agreement check passes.
- Dashboard read access: the four tables stay private; one read-only view (newest result per city: dispatched capacity, limiting factor, solver, study time) becomes readable with the dashboard's key, and the dashboard doc's DEF-01 (software-dashboard workstream, DASHBOARD-REQUIREMENTS.md ch. 10) is updated to say it is unblocked.
- 2026-11-16 (owner): the read-only view was taken early, before pandapower. `public.latest_grid_study` (migration `20261116200000_expose_latest_grid_study.sql`) is live and readable with the dashboard's key; `solver` is the constant `psse` and the column list is one-way. Phase 6 now *replaces* this view to read the real `solver` column (one row per city per solver) instead of creating it; VIEW-02 (exposure checks) and VIEW-03 (DEF-01 text) are already done for the PSS/E-only view and need only the pandapower update.
- Out of scope: building the dashboard (Software team).
- Research for this milestone lives in `.planning/workstreams/pandapower-solver/research/` (not the shared `.planning/research/`).

### Blockers/Concerns

- pandapower's built-in 39-bus case comes from MATPOWER; the PSS/E copy used on the laptop may differ. Matching the network data is likely the first real work.
- Each hourly run adds one permanent row set (24 a day); no retention rule exists yet.

## Current Position

Phase: 02 — PandapowerApi and Study Engine
Plan: 7 of 7
Status: Phase complete — ready for verification
Last activity: 2026-11-20 — Phase 1 complete, transitioned to Phase 02

## Progress

**Phases Complete:** 1 of 6
**Current Plan:** 7

## Session Continuity

**Last session:** 2026-11-18T22:04:27.368Z

**Stopped At:** Phase 1 complete, ready to execute Phase 02
**Resume File:** .planning/workstreams/pandapower-solver/phases/01-pss-e-reference-session-and-network-parity/01-11-PLAN.md

To resume:
1. The teammate runs the session per `docs/data-science/decisions/psse_pandapower_session_guide.md`. Laptop paths are in `.planning/workstreams/pss-e-integration/HANDOFF.md`. Pass `-Mapping` a COPY of `dlr-psse\mapping_real.json`, because the session deletes the file it is given, and the original is the hourly job's mapping.
2. Put the zip in `data/private/pandapower/incoming/` and the mapping at `data/private/pandapower/mapping.json` (both git-ignored).
3. Run `/gsd-execute-phase 1 --ws pandapower-solver`. Plans 01-01 to 01-09 have SUMMARYs and are skipped. Then resume 01-10 at Task 2 with the pasted session summary.

Known items from execution:
- `backend/tests/pandapower_fixture.py` `reference_from_solved` reads `res_trafo` with line column names. Tests in 01-08 and 01-09 work around it.
- The fake session's network is refused by the builder (`machine_at_load_bus`). The real RAW may need parser or builder iteration in 01-10 Task 2.
- numba is not installed (pandapower warns that it may be slow). Installing it would need its own package-legitimacy check.

## Performance Metrics

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 02 P01 | 5min | 2 tasks | 3 files |
| Phase 02 P02 | 25min | 3 tasks | 3 files |
| Phase 02 P03 | 30min | 3 tasks | 4 files |
| Phase 02 P04 | 35min | 3 tasks | 3 files |
| Phase 02 P05 | 20min | 2 tasks | 1 files |
| Phase 02 P06 | 25min | 2 tasks | 1 files |
| Phase 03 P01 | 35min | 3 tasks | 5 files |
| Phase 03 P02 | 30min | 3 tasks | 5 files |
| Phase 03 P03 | 25min | 3 tasks | 2 files |
| Phase 03 P04 | 13min | 3 tasks | 5 files |
| Phase 03 P05 | 30min | 3 tasks | 4 files |

## Decisions

- [Phase 02]: 02-01: solver chosen by name through study.API_FACTORIES/register_solver (D-02 deviation in form: string resolved via registry because the laptop import gate flags any other import; owner to confirm, not blocking)
- [Phase 02]: 02-01: register_solver refuses to replace a registered name with a different factory; unknown or unregistered solver fails at load_case before any adapter call
- [Phase 02]: 02-02: adapter accepts RAW or converted JSON by suffix (assumption Q2, owner to confirm, reversible); a snapshot saved failed or stale reloads FRESH; ENG-02 to ENG-04 stay Pending until the study-level plans 02-04 and 02-05
- [Phase 02]: 02-03: scale_load spreads the increment over the subsystem's in-service loads in proportion to P (assumption A2, settles with PSE-02); Q follows only when q_scales_with_p is yes, inconclusive is refused, a subsystem without load is a no-op
- [Phase 02]: 02-03: ENG-04 left Pending (scaling half done; study-level outage and failed-solve proof is 02-05); ENG-01 complete for the adapter; one Phase 1 CLI test fails on Windows only (0o600 mode), logged in deferred-items.md
- [Phase 02]: 02-04: Q1 an undecided enforce_q_lims is refused at stage mapping; Q4 voltage.source case is refused; Q6 solve_settings record in every dispatch row's details; A3 the real mapping uses the defaults (owner to confirm at 02-07, all reversible)
- [Phase 02]: 02-04: psse_version is None for a pandapower run (version in solve_settings.solver_version until Phase 3 adds solver columns); Phase 5 must refuse a live write when engine.is_placeholder(backend) is True and add the public-log filter (RESEARCH Pitfall 10)
- [Phase 02]: 02-04: ENG-02 complete (refusal half closed); ENG-05 stays Pending until 02-07, ENG-06 until 02-06; recorded settings must not carry a placeholder source or placeholder evidence
- [Phase 02]: 02-05: ENG-03 and ENG-04 proven at the study level through the unchanged psse_job loops on the real solver; no production change was needed (island is one non_convergence row, order and a failed outage change no other row, no read after a failed solve, fresh copy per solve, master unchanged, two runs equal)
- [Phase 02]: 02-06: database tier of ENG-06 written (5 tests); only skipped on this Windows checkout (no Postgres), never run green anywhere; ENG-06 stays Pending until the owner's Mac or CI run with DLR_TEST_PG_AUTOSTART=1 PSSE_REQUIRE_PG=1 passes with nothing skipped
- [Phase 02]: 02-06: tests assert nothing about a solver or solver_version column (Phase 3 extends them once its migration exists); leak list built from targets actually written to the generated mapping
- [Phase 03]: 03-01: A5 two constraints (psse_run_run_id_ck widened, psse_run_solver_run_id_ck tie) not one combined; A8 no new index; no NOT VALID; migration text proven here, database tier only SKIPPED (DB-01 stays Pending until the Mac run)
- [Phase 03]: 03-01: pre-migration test database is created fresh per test inside the module cluster (migration cannot be undone); Mac command: DLR_TEST_PG_AUTOSTART=1 PSSE_REQUIRE_PG=1 pytest over solver_tag_migration_test and the migration/writer/schema files, 0 skipped
- [Phase 03]: 03-02: registry contract.register_solver_tag filled by the solver package on import (no re-bind of a name or prefix, PSS/E included); a tagged PSS/E record is refused so PSS/E always uses the 17-column insert; a second-solver study run with the default tag is stored as one failed psse run with no results, Phase 5's runner passes its tag
- [Phase 03]: 03-02: a non-text solver_version from a study is stored as text (Rule 2, so the writer never refuses a built record); DB-02 left Pending: Python half done, database tie only skipped here, pandapower job itself is plan 03-04/Phase 5
- [Phase 03]: 03-03: A6 the laptop gaps command stays the pooled legacy check this phase; run_by_solver (per-solver, each solver from its own first slot, read-only, prints times/tags/kinds/counts) is library-level, Phase 5 wires it in for OPS-05 as gaps.run_by_solver(env, expected=(engine.SOLVER,), fail_on_gaps=True)
- [Phase 03]: 03-03: exit rule recommendation (owner may change): PSS/E gaps listed but not failing by default (offline machine is the known state), every other present or expected solver fails on a gap or on no rows, failing=(...) overrides; DB-03 left Pending: the two statements and the read-only refusal are database-only and only SKIPPED here
- [Phase 03]: 03-04: importing pandapower_job.api registers tag pandapower with prefix pp; engine._recording_study stamps solver and solver_version (bare adapter version, A7) and psse_version stays None; the runner must call job.run_once(..., solver=engine.SOLVER), the default tag is refused at validate_results and never stored as PSS/E
- [Phase 03]: 03-04: DB-02 left Pending: Python half and vocabulary parity with the migration proven here, tagged database rehearsal (3 test_db_* plus 4 study-job tests) only SKIPPED here; Mac command: DLR_TEST_PG_AUTOSTART=1 PSSE_REQUIRE_PG=1 pytest over pandapower_solver_tag_test and pandapower_study_job_test, 0 skipped
- [Phase 03]: 03-05: D-03 answered by the owner on 2026-11-18 (interactive question): guard. The solver-tag migration ends with latest_grid_study replaced by its earlier statement plus one predicate (solver psse), 20 columns, order, owner rights, grants and comments unchanged; the dashboard never shows a pandapower result as PSS/E, Phase 5's live write no longer waits on Phase 6 for that reason
- [Phase 03]: 03-05: owner's live steps: supabase db push, then verify_solver_tag.sql (seven checks), verify_psse_results.sql and verify_exposure.sql all ok; DB-01 left Pending (database proofs of the migration, the check and the guard only SKIPPED here); Mac command: DLR_TEST_PG_AUTOSTART=1 PSSE_REQUIRE_PG=1 pytest over solver_tag_owner_check_test, solver_tag_migration_test, grid_study_expose_test, expose_migration_test, psse_results_migration_test, 0 skipped
