---
phase: 01-land-pr-7
plan: 05
subsystem: testing
tags: [verification, read-only, git-diff, pytest, offline-tests, evidence]

requires:
  - phase: 01-land-pr-7
    provides: "01-01..01-04 offline test files for observation_composer, city_pipeline, dlr_orchestrator, backfill_archive"
provides:
  - "Current, reproducible evidence for LAND-01..04 and PIPE-01 on the final Phase 1 tree (HEAD fb6431f)"
  - "ROADMAP success-criterion-4 re-review checklist answered item by item"
  - "Flagged observations for Phases 2, 3 and 5"
affects: [02-data-cleaning, 03-real-data-validation, 05-scheduled-collection]

actuals:
  tokens: 3200
  tasks: 2
  commits: 0
plan_head_before: fb6431ff42a9ea8123df41a743d4d7c0a4f0e7dc
plan_head_after: fb6431ff42a9ea8123df41a743d4d7c0a4f0e7dc

tech-stack:
  added: []
  patterns:
    - "Phase-close verification: re-run git and pytest evidence on the final tree and cite out-of-band live evidence from STATE.md instead of repeating it"

key-files:
  created: []
  modified: []

key-decisions:
  - "Read-only plan: no source, test, doc or workflow file was touched; the only artifact is this SUMMARY"
  - "PIPE-01 live evidence is cited from STATE.md (owner's 2026-10-19 run), not re-run: a live run needs .env and would hit live providers"

requirements-completed: [LAND-01, LAND-02, LAND-03, LAND-04, PIPE-01]

coverage:
  - id: D1
    description: "LAND-01: PR #7 delta is backend/** plus the two amendment docs only, no root-level file, no backup/, dlr_pipeline.py unchanged and not tracked at root, all touched files LF"
    requirement: LAND-01
    verification:
      - kind: other
        ref: "git diff --name-status 2ec2bfd 5efe97d; git ls-files --eol (12 files, all i/lf); LAND01_OK"
        status: pass
    human_judgment: false
  - id: D2
    description: "LAND-02: full suite 1286 passed (1236 + 50 new) with no failed or error; city_rating tests, wind-projection tests and the cron dispatch test pass"
    requirement: LAND-02
    verification:
      - kind: unit
        ref: "python -m pytest -q -p no:cacheprovider (1286 passed); 53 selected tests passed"
        status: pass
    human_judgment: false
  - id: D3
    description: "LAND-03: the four new test files (50 tests) pass together with credentials unset and nothing under data/ or outputs/ written"
    requirement: LAND-03
    verification:
      - kind: unit
        ref: "backend/tests/{observation_composer,city_pipeline,dlr_orchestrator,backfill_archive}_test.py (50 passed); LAND03_OFFLINE_OK"
        status: pass
    human_judgment: false
  - id: D4
    description: "LAND-04: both amendments present, frontend PRD silent on the composer, amendment files unchanged by this phase"
    requirement: LAND-04
    verification:
      - kind: other
        ref: "grep + git diff --quiet 5efe97d HEAD over the two docs; LAND04_OK"
        status: pass
    human_judgment: false
  - id: D5
    description: "PIPE-01: offline tracer and default-cities ordering tests pass, orchestrator --help exits 0 without credentials and lists --no-archive; live run cited from STATE.md"
    requirement: PIPE-01
    verification:
      - kind: unit
        ref: "backend/tests/backfill_archive_test.py::test_backfill_rates_through_the_composed_stack_offline_and_a_rerun_skips_archived_steps; backend/tests/dlr_orchestrator_test.py::test_cities_run_in_the_order_given_and_default_to_config_locations"
        status: pass
    human_judgment: false

duration: 9min
completed: 2026-10-20
status: complete
---

# Phase 1 Plan 5: Phase-close Evidence Summary

**Read-only re-verification of LAND-01..04 and PIPE-01 on the final tree: PR #7 delta confined to backend/ and two amendment docs, full suite 1286 passed (1236 + 50 new), four new test files green offline, orchestrator CLI exits 0 without credentials, live run cited from STATE.md.**

## Performance

- **Duration:** 9 min (the full-suite run alone took 6 min 14 s)
- **Started:** 2026-10-20T00:51:30Z
- **Completed:** 2026-10-20T01:00:00Z
- **Tasks:** 2
- **Files modified:** 0 (only this SUMMARY and tracking files are committed)

All commands ran from `/Users/aphan/Senior_Design` at HEAD `fb6431f`, with the venv interpreter `/Users/aphan/Senior_Design/.venv/bin/python`. Dates are UTC.

## Evidence table

| Req | Check | Command (abridged) | Output | Verdict |
|-----|-------|--------------------|--------|---------|
| Precondition | Both landing commits in history | `git merge-base --is-ancestor 5efe97d HEAD`; `git cat-file -e 2ec2bfd^{commit}` | both exit 0 | PASS |
| LAND-01 | PR delta paths | `git diff --name-status 2ec2bfd 5efe97d` | exactly 10 paths: A backfill_archive.py, A city_pipeline.py, M city_rating.py, A dlr_orchestrator.py, A observation_composer.py (all `backend/`), M tests/city_rating_test.py, A tests/city_rating_wind_projection_test.py, M tests/forecast_shadow_collect_test.py, M docs/data-science/PRD.md, M docs/data-science/decisions/data_provider.md; 0 names outside `backend/` and the two docs | PASS |
| LAND-01 | No root-level file added | `git diff --name-only --diff-filter=A 2ec2bfd 5efe97d` filtered to names with no slash | 5 added paths, all contain a slash; filter result empty | PASS |
| LAND-01 | No `backup/` at HEAD | `git ls-tree -r --name-only HEAD` filtered by `^backup/` | no match | PASS |
| LAND-01 | `dlr_pipeline.py` unchanged and not at root | `git diff --quiet 2ec2bfd 5efe97d -- backend/dlr_pipeline.py`; `git ls-files -- dlr_pipeline.py` | no diff; root listing empty | PASS |
| LAND-01 | LF endings | `git ls-files --eol` over 12 files (5 PR #7 modules incl. city_rating.py, wind-projection test, 2 amended docs, 4 new test files) | 12 lines, every one `i/lf  w/lf` | PASS |
| LAND-04 | Amendment text | `grep` for "Pipeline-level composition (amendment, 2026-10-16)" in `decisions/data_provider.md`; "Amendment (2026-10-16)" in `docs/data-science/PRD.md` | both found | PASS |
| LAND-04 | Frontend PRD silent on composer | `grep -q observation_composer docs/frontend/PRD.md` | no match | PASS |
| LAND-04 | Amendment files untouched by this phase | `git diff --quiet 5efe97d HEAD -- <both docs>` | empty diff | PASS |
| Scope | No backend module or frozen file changed since 5efe97d | `git diff --quiet 5efe97d HEAD -- backend ':(exclude)backend/tests'`; same over `forecast_experiment.py`, `forecast_experiment_audit.py`, `legacy_corridor.py`, `.github/workflows/shadow_collect.yml` | both quiet | PASS |
| Scope | Only four test files and `.planning/` changed | `git diff --name-only 5efe97d HEAD` minus `.planning/` | `backend/tests/{backfill_archive,city_pipeline,dlr_orchestrator,observation_composer}_test.py` and nothing else | PASS |
| Scope | Wave-2 files_modified pairwise disjoint | `files_modified` of 01-02, 01-03, 01-04 | `observation_composer_test.py`, `city_pipeline_test.py`, `dlr_orchestrator_test.py` respectively | PASS |
| LAND-03 | Four new files together, credentials unset, data/outputs untouched | `env -u SYNOPTIC_TOKEN -u NREL_API_KEY -u NREL_API_EMAIL pytest -q -p no:cacheprovider <4 files>`; `find data outputs -newer <marker>` | `50 passed in 2.45s`; find lists nothing | PASS |
| LAND-02 | New-file test count | `pytest --collect-only -q <4 files>` | NEW = 50 (6 backfill + 16 composer + 10 city_pipeline + 18 orchestrator) | recorded |
| LAND-02 | Full suite | `pytest -q -p no:cacheprovider` | `1286 passed, 78 warnings in 373.84s (0:06:13)` (= 1236 + 50; no failed, no error) | PASS |
| LAND-02 | Named tests | `pytest -q` over `city_rating_test.py`, `city_rating_wind_projection_test.py` (8 collected), the cron test `test_workflow_is_dispatched_externally_four_times_a_day_and_documents_the_revert`, the tracer and the ordering test | `53 passed in 1.50s` (50 + 1 + 1 + 1) | PASS |
| PIPE-01 | Offline evidence | tracer `backfill_archive_test.py::test_backfill_rates_through_the_composed_stack_offline_and_a_rerun_skips_archived_steps`; ordering `dlr_orchestrator_test.py::test_cities_run_in_the_order_given_and_default_to_config_locations` | both inside the 53 passed | PASS |
| PIPE-01 | CLI help offline | `env -u SYNOPTIC_TOKEN python backend/dlr_orchestrator.py --help` | exit 0; lists `--no-archive` and `--archive-path` | PASS |
| PIPE-01 | Live run (cited, not repeated) | STATE.md, Phase 1 Progress | 2026-10-19 ~04:25Z `dlr_orchestrator --no-archive`, run by the owner: all 4 cities rated through composed weather, projection and G1-G6 | CITED |

STATE.md's Phase 1 evidence the re-run checks sit next to: 151aac2 (LAND-01 paths, LF, root `dlr_pipeline.py` dropped), b1e1d7b (19 `city_rating_test` fixtures get `wind_direction`), e330570 (cron test checks the cron-job.org dispatch), 5efe97d (`backup/` removed; main's tree equals the restructured branch).

## ROADMAP success criterion 4: re-review checklist

| Item | Evidence |
|------|----------|
| Relocation to real paths | Paths row above: 10 paths, all under `backend/` or the two amendment docs; no root file added |
| CRLF | LF row above: 12 files all `i/lf  w/lf` |
| `dlr_pipeline.py` unchanged | No diff between 2ec2bfd and 5efe97d; no root-level `dlr_pipeline.py` tracked |
| 19 fixture failures | `city_rating_test.py` passes inside the 53-test run and the 1286-test suite (fixes in b1e1d7b) |
| Uncollected wind-projection test | `city_rating_wind_projection_test.py` collects 8 tests and passes |
| Misplaced PRD amendment | LAND-04 rows: amendment in `docs/data-science/PRD.md` and `decisions/data_provider.md`; frontend PRD does not mention the composer |

## Discrepancies

Merged from the 01-01..01-04 SUMMARYs.

| Plan | Discrepancy |
|------|-------------|
| 01-01 | none |
| 01-02 | none |
| 01-03 | none (`city_pipeline.py` matched the plan's description in every tested respect) |
| 01-04 | none (a station-discovery failure raising out of the run is a pinned behavior, listed under observations below) |

## Flagged assumptions and observations

Recorded for the owners of Phases 2, 3 and 5. None is a work item in Phase 1.

- `observation_composer._by_hour` filters rows only by `<= end`. Historical runs (end more than 2 days old) request whole UTC days, so a historical reading can align on an hour older than `LOOKBACK_HOURS`, although the module docstring says the reading "can be up to this many hours old". No test pins this, so Phase 2 or 3 can change it freely.
- Repeated `run_dlr_pipeline` runs over the same window append duplicate archive rows; only `backfill` skips already-archived slots. This is CLEAN-03 (Phase 2) and no test pins it.
- Station discovery failure (composed mode, no `SYNOPTIC_TOKEN`) raises `EnvironmentError` out of `run_dlr_pipeline` and `main()` rather than being recorded per city. 01-04 pins this (`test_composed_mode_without_stations_or_token_raises_before_any_city`), so Phase 5 (SCHED-01) must update that test if it changes the behavior.
- Within one UTC hour, when two provider rows share a timestamp, which one wins is unspecified (`sort_values` defaults to a non-stable sort). No test depends on it.
- Pre-planned and deferred by the owner (STATE.md "Integration Items"): `load_dotenv` in the orchestrator, NSRDB skip for current windows, print-to-logging, anomaly-model provisioning (Phases 4-5).

## Accomplishments

- Re-verified LAND-01, LAND-02, LAND-03, LAND-04 on the final tree with reproducible commands and recorded outputs.
- Confirmed the phase changed nothing but four new test files and `.planning/` files since 5efe97d: no backend module, frozen module or shadow-collect workflow was touched.
- Confirmed the full suite at 1286 passed (1236 baseline + 50 new), 0 failed, 0 errors.
- Confirmed PIPE-01 offline and cited the owner's live run from STATE.md.

## Task Commits

This plan modifies no source files, so there are no per-task commits (`commits: 0` in the frontmatter counts task commits; `plan_head_before` equals `plan_head_after`).

**Plan metadata:** the `docs(01-05)` commit that adds this SUMMARY and updates STATE.md, ROADMAP.md and REQUIREMENTS.md.

## Files Created/Modified

None outside this SUMMARY. `git status --porcelain -- backend docs .github` was empty after both tasks.

## Decisions Made

None - followed plan as specified. The live run was not repeated, as the plan prohibits.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. The only observed change in tracked files during the plan was `.DS_Store` churn that predates it and is not committed.

## Known Stubs

None.

## Threat Flags

None. Mitigations T-01-14, T-01-15 and T-01-16 held: scope check passed, no write under `data/` or `outputs/` during the offline run, and only `--help` was invoked on the orchestrator.

## Next Phase Readiness

Phase 1 is complete: all five plans have summaries and LAND-01..04 and PIPE-01 are marked complete. Phase 2 (Data Cleaning) can start; it edits fixture data in `city_pipeline_test.py` and `predictive_tracer_test.py` as noted in STATE.md.

## Self-Check: PASSED

- Required markers all produced in this run: LAND01_OK, LAND04_OK, PHASE_SCOPE_OK, LAND03_OFFLINE_OK, LAND02_SUITE_OK, PIPE01 and LAND02 named tests (53 passed) plus `--help` exit 0.
- `git status --porcelain -- backend docs .github` is empty.

---
*Phase: 01-land-pr-7*
*Completed: 2026-10-20*
