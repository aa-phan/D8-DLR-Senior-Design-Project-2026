---
phase: 05-scheduled-live-runs
plan: 05
subsystem: infra
tags: [runbook, cron-job-org, github-actions, actions-minutes, window-check, gh-cli, pytest]

requires:
  - phase: 05-scheduled-live-runs
    provides: "05-01 dlr_live.yml and dlr_live_run (CITY_TIMEOUT_S, REQUIRED_ENV, --fault-city); 05-02 NSRDB_SKIP_YEARS_BEFORE_CURRENT; 05-03 pipeline_run run log and --no-run-log; 05-04 model manifest and the --write-manifest procedure"
  - phase: 04-supabase-store-writer
    provides: "public.city_rating and public.pipeline_run, supabase_store.connect() and redact, the dlr_writer role with SELECT on both tables, secret_scan_test.py"
provides:
  - "docs/data-science/decisions/dlr_live_runbook.md: 13-section operating runbook for the live workflow (cron-job.org job and token scope, secrets, one run, results, pause/resume, cadence, drills, models, NSRDB, failure modes, Actions-minutes budget, window check)"
  - "backend/dlr_live_window_check.py: read-only slot-by-slot verdict (ok / incomplete / failed-visible / missing) for an N-hour window of live runs, plus measured billed minutes and a 30-day projection"
  - "backend/tests/dlr_live_runbook_test.py: runbook-vs-code consistency checks and the phase-wide secret-pattern scan over 21 text files"
affects: [05-06, 05-07, 05-08, phase-06]

actuals:
  tokens: 13281
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns:
    - "A pure evaluate_window plus two thin fetchers (gh run list via subprocess without a shell; read-only SELECTs with %(name)s bound parameters) so everything but I/O is tested offline"
    - "Runbook constants are read back from the code and the workflow by a test, so a drift fails the suite instead of misleading an operator"
    - "Secret-pattern scan that plants a control line per pattern (assembled from pieces) before scanning, so a pattern that stops matching cannot pass vacuously"

key-files:
  created:
    - backend/dlr_live_window_check.py
    - backend/tests/dlr_live_window_check_test.py
    - docs/data-science/decisions/dlr_live_runbook.md
    - backend/tests/dlr_live_runbook_test.py
  modified: []

key-decisions:
  - "A slot's rating rows count when their run_id belongs to ANY run placed in that slot, so a later drill or re-run that overwrote some cities' rows in the same hour (OD-7) does not turn an earlier good run into a failure"
  - "A run whose conclusion is neither success nor red (in progress, skipped, startup_failure and so on) is not visible evidence: a slot with only such runs is 'missing', which fails the window rather than passing it silently"
  - "Billed minutes per run = max(1, ceil((updatedAt - startedAt) / 60 s)); the window report covers every finished run placed in the window, red ones included, because they bill"
  - "The runbook states the shadow job fires at minute 00 of its hours and notes, as an observation only, that recent shadow runs were created at 05/11/17/23 UTC rather than the 00/06/12/18 UTC its runbook lists"

patterns-established:
  - "Runbook sections that later plans edit (section 12 quota row, live-minutes row) carry explicit markers ('Not yet measured. To be filled in at 05-06', 'Estimate until 05-08') that the editing plans replace"

requirements-completed: [SCHED-02, SCHED-01]

coverage:
  - id: D1
    description: "evaluate_window gives ok / incomplete / failed-visible / missing per hourly slot: a full window passes; red runs (failure, timed_out, cancelled) are visible failures; a slot with no run, an empty window, or a successful run missing a city fails; rows overwritten later in the same slot still pass; runs outside the window are ignored"
    requirement: SCHED-01
    verification:
      - kind: unit
        ref: "backend/tests/dlr_live_window_check_test.py#test_full_window_of_successful_runs_passes"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_window_check_test.py#test_red_runs_count_as_visible_failures"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_window_check_test.py#test_a_slot_with_no_run_fails_the_window"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_window_check_test.py#test_a_successful_run_missing_a_city_is_incomplete"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_window_check_test.py#test_overwritten_rows_from_a_later_run_in_the_same_slot_still_pass"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_window_check_test.py#test_empty_window_reports_every_slot_missing"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_window_check_test.py#test_run_without_a_pipeline_run_row_is_placed_by_its_start_time"
        status: pass
    human_judgment: false
  - id: D2
    description: "Billed minutes per run round up (at least 1) and the report gives count, median, max and the 30-day projection at 24 runs/day; fetch_rows issues two read-only SELECTs with bound parameters and leaves a passed-in connection open"
    requirement: SCHED-02
    verification:
      - kind: unit
        ref: "backend/tests/dlr_live_window_check_test.py#test_billed_minutes_round_up_per_run"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_window_check_test.py#test_fetch_rows_binds_parameters"
        status: pass
    human_judgment: false
  - id: D3
    description: "The runbook quotes only constants that match the code and the workflow (CITY_TIMEOUT_S, REQUIRED_ENV, timeout-minutes, concurrency group, manifest path, the NSRDB constant, fault_city, the window-check script) and documents the dispatch URL, body, 204, schedule, UTC, pause, OD-1 and OD-4, and the minutes section covers both workflows and 2026-11-24"
    requirement: SCHED-02
    verification:
      - kind: unit
        ref: "backend/tests/dlr_live_runbook_test.py#test_runbook_constants_match_the_code_and_workflow"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_runbook_test.py#test_runbook_documents_the_external_trigger_pause_and_cadence"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_runbook_test.py#test_runbook_minutes_section_covers_both_workflows"
        status: pass
    human_judgment: false
  - id: D4
    description: "None of the 21 text files this phase creates or edits holds a token, key, JWT or credentialed database URL; the scan names path, line and pattern only, proves each pattern with a planted control, and fails if a listed file is missing"
    requirement: SCHED-02
    verification:
      - kind: unit
        ref: "backend/tests/dlr_live_runbook_test.py#test_phase5_files_contain_no_secret_values"
        status: pass
    human_judgment: false
  - id: D5
    description: "The runbook is accurate and sufficient for the owner to create the cron-job.org job, scope its token, pause, change cadence and read the minutes budget; the Actions-minutes figures are estimates and the quota is unverified until 05-06 and 05-08"
    requirement: SCHED-02
    verification: []
    human_judgment: true
    rationale: "Whether the instructions match cron-job.org's real form fields, and what the owner's real quota is, can only be judged against the live services. Backstopped by plan 05-07 Task 1 (creates the job exactly as section 2 says), 05-06 Task 1 (reads the quota) and 05-08 (measured minutes)."

duration: 14 min
completed: 2026-10-24
status: complete
plan_head_before: 8269519321b2ecaffd52614a25758d650d16b570
plan_head_after: efd2930289d17d41a993d4eaefbad324b52706f3
commits: 3
---

# Phase 5 Plan 05: Live runbook and 24 h window check Summary

**A 13-section operating runbook for the hourly live workflow (cron-job.org dispatch job and token scope, pause, cadence, drills, models, failure modes, Actions-minutes budget with shadow measured and live estimated) plus `dlr_live_window_check.py`, which turns ROADMAP SC 2 into one command that gives a slot-by-slot verdict and measured billed minutes.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-10-24T08:59:37Z
- **Completed:** 2026-10-24T09:13:37Z
- **Tasks:** 2 (3 commits: TDD RED test, TDD GREEN feat, docs)
- **Files modified:** 4 (all new)

## Accomplishments

- `backend/dlr_live_window_check.py`: `evaluate_window` (pure) places each run in a slot by its `pipeline_run` `window_end` truncated to the hour (else its start time) and gives each of the N slots one verdict. `ok` needs a successful run whose row lists all four cities and four `city_rating` rows at the slot from that slot's runs. `incomplete` is a successful run that fails that. `failed-visible` is no success but a red run. `missing` is no usable run. It also returns billed minutes (count, median, max, 30-day projection at 24 runs/day) and `passed` (no `missing` or `incomplete` slot). `format_report` prints the table, the minutes line and the window verdict; `main` exits 0 or 1.
- `fetch_runs` runs `gh run list --workflow dlr_live.yml --limit 400 --json ...` with an argv list (no shell), filters to the window plus one hour, and warns on stderr when the 400-run limit may have cut off early slots. `fetch_rows` runs two SELECTs with `%(start)s` / `%(end)s` bound parameters through Phase 4's `supabase_store.connect()`, and re-raises a database error as a redacted `StoreError`.
- `docs/data-science/decisions/dlr_live_runbook.md`: all 13 sections the plan lists. Section 2 gives the exact job (dispatches URL, POST, three headers, body `{"ref":"main"}`, 204, `5 * * * *` in UTC, notifications on) and a token limited to this repository with only Actions read and write, an expiry, separate from the shadow token, kept in cron-job.org only. Section 12 holds the formula, the shadow row (measured), the live row (estimate until 05-08), the total, a clearly marked "not yet measured" quota row, the exhaustion warning that includes Shadow Collection before 2026-11-24, and four levers with none chosen.
- `backend/tests/dlr_live_runbook_test.py`: 4 tests. Three tie the runbook to the code and workflow (mutation spot-check: changing `300 s`, `timeout-minutes`, the schedule, the section heading or planting a token each failed one test). The fourth scans the 21 phase files with a planted control per pattern (7 patterns: the plan's six plus Phase 4's literal role-password form).

## Task Commits

1. **Task 1 RED: failing tests for the live window check** - `8f39343` (test; a behavior-less skeleton module so RED is an assertion failure)
2. **Task 1 GREEN: window check for hourly live slots** - `c7bf4d9` (feat)
3. **Task 2: live workflow runbook with cron-job.org setup and Actions-minutes budget** - `efd2930` (docs)

**Plan metadata:** recorded in the docs commits that follow this file (SUMMARY, then STATE/ROADMAP/REQUIREMENTS). Nothing was pushed.

## TDD Gate Compliance (Task 1, `tdd="true"`)

- **RED:** `8f39343`. 11 of 11 cases failed against the skeleton. `gsd-tools check tdd-red-evidence` on the pytest JUnit XML for the target `test_overwritten_rows_from_a_later_run_in_the_same_slot_still_pass` returned `RED_EVIDENCE_OK` (`target_test_failed`, format `junit`). Semantic assessment: the target ran and failed at its first read of the planned verdict (`result["slots"][4]`, an `IndexError` because the skeleton returns no slots), not at a collection, import or fixture fault; the other ten failed on their own first assertions (`fetch_rows` on `0 == 2` stub calls). Evidence record: `.planning/tmp/05-05-t1-red-evidence.json` (untracked, like the rest of `.planning/tmp`).
- **GREEN:** `c7bf4d9`. All 11 cases (9 functions) pass. Two assertions were added to the full-window test after a mutation check showed two survivors (a runs-outside-the-window guard and `any` versus `all` over successful runs); both now fail the mutant.
- **REFACTOR:** none needed.
- **Mutation spot-check:** removing the same-slot rating filter, rounding down instead of up, dropping a red conclusion, removing the window bound, `any` to `all`, ignoring the `pipeline_run` row, and removing the 1-minute floor each made at least one test fail (the window bound and `any`/`all` after the two added assertions).

## Files Created/Modified

- `backend/dlr_live_window_check.py` - `billed_minutes`, `evaluate_window`, `format_report`, `fetch_runs`, `fetch_rows`, `main`; constants `RED_CONCLUSIONS`, `PIPELINE_RUN_SQL`, `CITY_RATING_SQL`
- `backend/tests/dlr_live_window_check_test.py` - 9 test functions (11 cases) with fixture runs and rows and a stub connection
- `docs/data-science/decisions/dlr_live_runbook.md` - the runbook (13 `## ` sections)
- `backend/tests/dlr_live_runbook_test.py` - 4 test functions; `PHASE5_TEXT_FILES` lists the 21 scanned files

## Decisions Made

- Rating rows count for a slot when their `run_id` belongs to any run of that slot (the plan's rule), which is what keeps a same-hour drill from invalidating the run it overwrote.
- A run that is not finished, or has a conclusion other than success, failure, timed_out or cancelled, is not evidence the slot was attempted: such a slot is `missing` with the conclusion named in its note. This fails closed; `startup_failure` therefore reads `missing` rather than `failed-visible` (see Discrepancies).
- The window check takes `--start` only on an exact UTC hour (argparse error otherwise), because slots are hour-aligned and a half-hour start would silently shift every slot boundary.

## Deviations from Plan

### Auto-fixed Issues

None.

### Plan-vs-instruction differences (not defects)

- **Commit shape for Task 1:** the plan says one commit; the canonical TDD reference for a `tdd="true"` task gives `test(...)` then `feat(...)`, so there are two (`8f39343`, `c7bf4d9`). The `feat` message is the one the plan specifies. The RED commit carries a behavior-less skeleton module so RED is an assertion failure.
- **Commit trailer:** `Co-Authored-By: Claude Sonnet 5.5` instead of the plan's `Claude Opus 5.5`, per the attribution instruction for this run.
- **Full-suite command:** the plan's last `pytest` call has no path; it was run as `.venv/bin/python -m pytest -q -p no:cacheprovider backend/tests` as the run instructions require.
- **Extra pieces:** `billed_minutes` and `format_report` are public functions (the plan names `evaluate_window`, `fetch_runs`, `fetch_rows`, `main`); the report is where the "report names the slot" behavior lives. The secret scan also covers Phase 4's literal role-password pattern (the plan allows merging Phase 4's patterns), and the runbook test asserts two more quoted facts than the plan lists (`` `CITY_TIMEOUT_S` = 300 s `` and `4 cities x 300 s`), because the bare `300 s` is satisfied by any occurrence.
- **WINDOWS.md not appended:** the runbook's two marked placeholders (quota row, live-minutes estimate) are planned, dated stubs that 05-06 and 05-08 replace, not defects; `.planning/WINDOWS.md` is a tracked project-wide file outside this plan's `files_modified`, and no earlier plan of this phase wrote to it.

---

**Total deviations:** 0 auto-fixed
**Impact on plan:** none; every change is inside the four planned files.

## Discrepancies

- **Shadow job hours differ from what its runbook (and this plan) says.** The plan and `shadow_collection_runbook.md` give 00/06/12/18 UTC. `gh run list --workflow shadow_collect.yml` shows runs created at 05:00, 11:00, 17:00 and 23:00 UTC (second 04 to 06) from 2026-10-21 to 2026-10-24, so the cron-job.org job appears to be set about one hour earlier than documented (a time-zone or offset setting is the usual cause; not verified). It does not affect the live job (minute 05 versus the shadow job's minute 00, different concurrency groups), so the runbook states "minute 00 of its hours" and records the observation in one sentence with no instruction to change it. The owner may want to check the shadow job's setting.
- **Shadow measurement reproduced, with a caveat.** From `gh run list` (ceil of `updatedAt - startedAt`, at least 1), 25 runs created 2026-10-16 to 2026-10-19 give median 5, range 4 to 17 (one 17-minute run); since 2026-10-16 (43 runs) the median is still 5. The plan's "4 runs/day" is the scheduled count; the 25 runs in those four days include manual dispatches and the pre-2026-10-17-21:00Z `schedule` events, which is why the runbook tells the reader to count actual runs. The most recent five runs (2026-10-23 to 24) were 3, 6, 5, 8 and 5 minutes.
- **Section 12 projection is an estimate throughout for live.** Nothing in this plan measures a live run. The live row is labelled "Estimate until 05-08" and the quota row "Not yet measured. To be filled in at 05-06"; the 2,000 and 3,000 minute figures are GitHub's published plan allowances, stated as context only, not the owner's quota.
- **`startup_failure` is not "visible red" here.** The plan names failure, timed_out and cancelled. GitHub also shows `startup_failure` as a red run; it is treated as inconclusive (slot `missing`, failing the window) rather than passing silently. If the owner wants it to count as visible, add it to `RED_CONCLUSIONS` in `backend/dlr_live_window_check.py`.
- **`cities_failed` documentation lags the code.** As 05-03 noted, the schema document and the column comment list `error` and `degraded`; the runner also stores `timeout` and extra keys. The runbook records the full set (section 5) but `docs/data-science/schema/city_rating_v1.md` is outside this plan and unchanged. Also recorded in the runbook: a history-cleaning failure is invisible in the run log.
- **The model promotion reference now resolves.** 05-04's `.gitignore` comment pointed at this runbook before it existed; section 9 now holds the procedure (`--write-manifest`, commit artifacts and manifest together).
- Everything else matched the plan and the four earlier SUMMARYs (constants, secret names, exit codes, the `pipeline_run` key being `run_id` alone so a re-run attempt replaces the row, `NSRDB_SKIP_YEARS_BEFORE_CURRENT = 0`).

## Issues Encountered

- **A stale bytecode file briefly made one test fail after my mutation checks.** The `any` to `all` mutant has the same file size as the original, and restoring the file within the same second left Python's `.pyc` (validated by source mtime in whole seconds plus size) compiled from the mutant. The committed source was correct throughout (`git status` clean, `diff` against the backup identical); deleting `backend/__pycache__/dlr_live_window_check*.pyc` fixed it, and the full suite then passed (1727 passed, 48 skipped, 0 failed; baseline before this plan 1712 passed, 48 skipped; +11 window-check cases and +4 runbook tests). `__pycache__` is git-ignored, so nothing stale is tracked.
- The pre-existing untracked and modified files in the working tree (`.DS_Store`, `.obsidian/`, `graphify-out/`, the phase 07 directory, `.planning/config.json` and so on) were left unstaged; every commit used explicit paths.

## Known Stubs

- `docs/data-science/decisions/dlr_live_runbook.md` section 12, quota row: "Not yet measured. To be filled in at 05-06 from Settings, Billing". Intentional; plan 05-06 Task 1 replaces it with the owner's real figures.
- Same section, live row: "Estimate until 05-08". Intentional; plan 05-08 Task 1 replaces it with measured figures from `dlr_live_window_check.py`.

No other placeholder, TODO or FIXME text, and no hardcoded empty data flows to a consumer.

## Threat Flags

None. The surface added is the one in the plan's threat model (T-05-21 to T-05-25): secrets in committed text (phase-wide scan), the dispatch token's scope (documented as repository-limited, Actions only, with expiry), minutes exhaustion (documented with levers; quota to be read at 05-06), SQL injection in the window check (bound parameters only, read-only SELECTs, stub-connection test) and runbook drift (consistency test).

## User Setup Required

None in this plan - no external service configuration was performed. The runbook is what the owner follows in plan 05-07 to create the cron-job.org job and token, and in plan 05-06 to read the Actions quota.

## Next Phase Readiness

- Ready for 05-06 (owner reads the quota from Settings, Billing and the executor fills section 12's quota row; first dispatch updates the live row with the first run's billed minutes), 05-07 (create the cron-job.org job exactly as section 2 says; drill with `-f fault_city=...`) and 05-08 (run `dlr_live_window_check.py --start <hour> --hours 24` and replace "Estimate until 05-08" with measured minutes).
- `dlr_live_window_check.py` needs `gh` authentication and `SUPABASE_DB_URL` in `.env`, so it runs from the owner's main checkout only.
- Nothing pushed; `shadow_collect.yml` and `shadow_collection_runbook.md` are unchanged from `origin/main`.

## Self-Check: PASSED

- FOUND: `backend/dlr_live_window_check.py`, `backend/tests/dlr_live_window_check_test.py`, `docs/data-science/decisions/dlr_live_runbook.md`, `backend/tests/dlr_live_runbook_test.py`
- FOUND commits: `8f39343`, `c7bf4d9`, `efd2930` (all ancestors of HEAD; `check evaluation-scope --plan 05-05 --commits-only` resolves the plan; `git rev-list --count 8269519..HEAD` = 3)
- Acceptance criteria re-run: `def evaluate_window(` and `def fetch_rows(` present; 9 test functions in the window-check file and the targeted file passes; 13 `## ` sections in the runbook; 4 test functions in the runbook test and `def test_phase5_files_contain_no_secret_values` present; `git diff --quiet origin/main` on `shadow_collection_runbook.md` and `shadow_collect.yml` exits 0; targeted tests (runbook, workflow, shadow collect) 21 passed; full `backend/tests` 1727 passed, 48 skipped, 0 failed.

---
*Phase: 05-scheduled-live-runs*
*Completed: 2026-10-24*
