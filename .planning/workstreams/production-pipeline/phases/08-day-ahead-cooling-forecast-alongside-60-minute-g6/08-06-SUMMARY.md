---
phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6
plan: 06
subsystem: infra
tags: [day-ahead, verification, read-only, redaction, runbook, postgres, pytest]

requires:
  - phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6
    provides: "08-01 day_ahead_forecast (due_targets, serving_model_path, refit_cities), day_ahead_band.BAND_ARTIFACT_PATH, day_ahead_contract; 08-02 pipeline_run.day_ahead shape and stage constants; 08-04 the write-side table; 08-05 the 13-entry live manifest"
  - phase: 04-supabase-store-and-writer
    provides: "supabase_store.connect, begin_read_only, redact, rating_config_fingerprint"
provides:
  - "backend/day_ahead_verify.py --check-store --since --json-out: the owner's read-only first-slot check (D-17) with ten named checks and redacted JSON evidence"
  - "backend/tests/day_ahead_verify_test.py: 30 tests (pass, each failure, nothing, config, redaction, read-only) on local Postgres"
  - "Runbook section 17 (the day-ahead stage), section 4 step 6 and the warning-tier pre-flight, section 9 manifest groups and the D-13 promotion step"
  - "One runbook test pinning section 17 to the stage constants, flags and tool names"
affects: [08-07, 08-08, 08-10, 08-12]

actuals:
  tokens: 14500
  tasks: 2
  commits: 2
plan_head_before: 2be463074e85975648efc9309b9559554ff172f1
plan_head_after: c15b78eb0fc9d29d4d149ed104a1704a0c09ea23

tech-stack:
  added: []
  patterns:
    - "Pure evaluate(rows, runs, manifest) separated from the single read-only fetch, so states the table's own CHECKs refuse to store are still tested on rows held in memory"
    - "Connection secrets (URL, password, host, pooler user, project reference) redacted by the script's own list through the public supabase_store.redact, with no private store name read"
    - "Evidence JSON built from redacted strings only; a connection failure is a failed check in the report, not a crash"

key-files:
  created:
    - backend/day_ahead_verify.py
    - backend/tests/day_ahead_verify_test.py
  modified:
    - docs/data-science/decisions/dlr_live_runbook.md
    - backend/tests/dlr_live_runbook_test.py

key-decisions:
  - "The plan's 'rows of the run equal due_targets(issued_at)' is split across two checks: first_run_covers_every_due_target fails on a missing due target, issue_lead_at_most_18h fails on a row for a target that was not yet due. Together they enforce equality, and each failure flips exactly its own check (a row beyond 18 h cannot also be a missing-target failure)"
  - "With no first run at all every dependent check fails ('no first run to check') instead of passing vacuously; with only some cities missing, first_run_found names them and the other checks judge the cities that have a run"
  - "A database that cannot be reached is exit 1 with a failed database_read check written to the JSON (so the evidence exists and is redacted); only a missing SUPABASE_DB_URL, a bad --since or an unreadable manifest is exit 2"
  - "TEST_BAND_N = 196 is a constant in the verifier, as in the plan; the manifest supplies the band and cooling hashes"

patterns-established:
  - "Verify-script session pinned read only with begin_read_only and rolled back, proven by a spy that the connection was rolled back and by a write attempt inside the script's own session raising ReadOnlySqlTransaction for a role that holds INSERT"

requirements-completed: [DAY-08, DAY-04]

coverage:
  - id: D1
    description: "The first-slot check passes on a correct first run (12 rows, all ten checks ok, exit 0) and each failure (missing due target, wrong label, wrong weather run age, live-rolling at launch, band hash not in the manifest, cooling hash different, config fingerprint or version not the code's, lead over 18 h, no pipeline_run record, issued list differing from the rows, a city with no row) flips exactly its own check with exit 1; no row since T0 fails first_run_found and every other check"
    requirement: "DAY-08"
    verification:
      - kind: integration
        ref: "backend/tests/day_ahead_verify_test.py (30 tests, local Postgres, none skipped)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Read-only and redaction: the session is BEGIN READ ONLY and rolled back, a write inside the script's connection raises, the table counts are unchanged; a connection failure carrying the URL, password, host and project reference prints and stores none of them; SUPABASE_DB_URL unset is exit 2 naming only the variable"
    requirement: "DAY-08"
    verification:
      - kind: integration
        ref: "backend/tests/day_ahead_verify_test.py#test_the_session_is_read_only_changes_nothing_and_is_rolled_back"
        status: pass
      - kind: integration
        ref: "backend/tests/day_ahead_verify_test.py#test_a_write_inside_the_scripts_connection_is_refused"
        status: pass
      - kind: integration
        ref: "backend/tests/day_ahead_verify_test.py#test_a_connection_failure_prints_and_stores_no_url_host_or_password"
        status: pass
    human_judgment: false
  - id: D3
    description: "The runbook documents the day-ahead stage (due times, catch-up, shared budget, outcomes, where they are recorded, never changes the exit code), the warning-tier pre-flight, the 13 manifest entries and the D-13 promotion step, and states that '24 h' is the weather run's age with the TEST, shadow and live anchor leads; pinned strings are kept and one new test ties section 17 to the code"
    requirement: "DAY-04"
    verification:
      - kind: unit
        ref: "backend/tests/dlr_live_runbook_test.py#test_runbook_section_17_matches_the_day_ahead_stage_constants_and_tools"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_runbook_test.py"
        status: pass
    human_judgment: false
  - id: D4
    description: "The runbook reads correctly to the owner in plain English (clarity of the outcome table and the check instructions)"
    requirement: "DAY-04"
    human_judgment: true
    rationale: "Wording adequacy for a human reader is not asserted by any test; the test pins constants and tool names only"

duration: 11min
completed: 2026-11-08
status: complete
---

# Phase 8 Plan 06: First-Slot Verification and Runbook Summary

**`backend/day_ahead_verify.py --check-store` reads the live write side in one read-only, rolled-back transaction and judges the first issuing run with ten named checks (all 12 due rows, label, band, hashes, config identity, lead, run-log record) into redacted JSON, and runbook section 17 documents the day-ahead stage, its failure policy and the D-13 promotion step.**

## Performance

- **Duration:** about 11 min (2026-11-08, about 10:22Z to 10:33Z)
- **Tasks:** 2 (one TDD-marked, one docs)
- **Files modified:** 4 (2 created, 2 edited)

## Accomplishments

- **The check (D-17).** `--check-store --since <ISO UTC> [--json-out PATH]`. It selects every `day_ahead_forecast` row written at or after `--since` and the `pipeline_run.day_ahead` of the run ids found, takes each city's earliest `issued_at` as its first issue, and evaluates `first_run_found`, `first_run_covers_every_due_target`, `label_is_the_d11_label`, `method_horizon_and_weather_run`, `band_is_the_test_split_artifact`, `cooling_model_matches_the_manifest`, `config_identity_matches_the_code`, `band_brackets_the_value`, `issue_lead_at_most_18h` and `pipeline_run_records_the_stage`. It prints one PASS or FAIL line per check (a FAIL names the city and target) and one line per row, and writes `{checks, rows, since, exit_code}`. Exit 0 all ok, 1 a check failed, 2 configuration.
- **Never writes, never leaks.** The session goes through `supabase_store.begin_read_only` and is rolled back and closed in a `finally`. Every printed or stored string passes through `supabase_store.redact` with the URL, password, host, pooler user and project reference from the environment. A connection failure becomes a failed `database_read` check in the report, not a crash.
- **Tests (30, local Postgres, none skipped).** Seeded as the administrator with `INSERT_COLUMNS` and a matching run record, read as `dlr_writer`. Beyond the plan's list: a wrong weather-run age, a wrong method or horizon, a non-bracketing band (these three are proven on rows held in memory because the table's own CHECKs refuse to store them), a config version mismatch, a recorded `issued` list that differs from the rows, a city with no row, a refit city served as frozen, a hostile URL inside a text column, a bad `--since` (four cases), an offset `--since`, an unreadable manifest, and `--help`.
- **Runbook.** Section 17 (plain English first): what the stage publishes and that it never sets a rating or gates G6; `"24 h"` is the weather run's age and rows are issued 0 to 18 h before their target; the TEST (24 h), shadow (about 12 h) and live (up to 18 h) anchor leads; the due rule and the 06:05, 12:05, 18:05, 00:05 UTC runs (12:05 AM, 6:05 AM, 12:05 PM, 6:05 PM Central standard time) that issue one new target per city, and up to 3 per city on the first run; catch-up from the table; the budget (`DAY_AHEAD_CITY_TIMEOUT_S` = 150 s, `DAY_AHEAD_MIN_START_S` = 60 s of the shared 1200 s); an outcome table (none_due, issued, partial, error, timeout, skipped_budget); where outcomes go (`pipeline_run.day_ahead`, the step summary table and counter); D-15 and D-16; the band; and how to check, dry-run one city (`--no-store`) and run the ratings without the stage (`--no-day-ahead`). Section 4 gains the warning-tier pre-flight sentence, step 6 and the "`finished_at` means ratings finished" sentence; section 9 lists the 13 entries by group and gives the D-13 promotion step (bump `DAY_AHEAD_REFIT_VERSION` with the refit, regenerate the manifest, run the day-ahead tests, ask before pushing; graded pairs restart after a config or model change).
- Full suite with local Postgres: **2894 passed** (2863 after 08-05, plus 30 verifier tests and 1 runbook test), 0 failed.

## Task Commits

1. **Task 1: read-only first-slot check** - `42a12c7` (feat)
2. **Task 2: runbook day-ahead stage** - `c15b78e` (docs)

**Plan metadata:** recorded in the docs commit that follows this summary.

## TDD Notes

Task 1 carries `tdd="true"` but the plan is `type: execute` and prescribes one `feat(08-06)` commit per task, so there is no separate `test(08-06)` commit (same arrangement as 08-01 to 08-05).

- **Order, stated honestly:** I drafted `day_ahead_verify.py` before the test file. To get a real RED I moved the module aside, wrote the tests and ran them: collection failed with `ModuleNotFoundError: No module named 'day_ahead_verify'`. That is an import-level failure, not an assertion on planned behavior, so it would not satisfy a strict INVALID_RED classifier (same note as 08-01 and 08-04). I then restored the module; a first GREEN run had 8 failures, all in the tests themselves (`**` with tuple keys), fixed in the test helper; the second run was 30 of 30.
- **Mutation checks by hand (both restored):** removing the `begin_read_only` call failed the read-only and write-refused tests; making `_clean` return text unchanged failed both redaction tests. The tests discriminate.
- **Task 2 RED:** the new section-17 test failed on the planned assertion (`no '## ' section with 'Day-ahead forecast stage' in its heading`). After the section was written the first run failed on one missing needle (`DAY_AHEAD_REFIT_VERSION`), which led to adding the short "later conductor refit" paragraph to section 17 as the plan lists it there.

## Files Created/Modified

- `backend/day_ahead_verify.py` - CLI and `main(argv, manifest_path)`, `fetch`, pure `evaluate`, `first_runs`, `parse_since`, redaction helpers
- `backend/tests/day_ahead_verify_test.py` - 30 tests (see above)
- `docs/data-science/decisions/dlr_live_runbook.md` - section 17 appended; sections 4, 5 (one clause) and 9 edited; every previously pinned string kept
- `backend/tests/dlr_live_runbook_test.py` - one new function (18 added lines, 0 removed)

## Decisions Made

See `key-decisions` above: the equality rule split across the coverage and lead checks, no vacuous passes, connection failure as exit 1 with evidence, `TEST_BAND_N = 196`.

## Deviations from Plan

### Plan interpretation (no code defect)

**1. Coverage "equal" split into coverage and lead checks**
- **Found during:** Task 1 (designing the lead-over-18-h failure case)
- **Issue:** the plan defines `first_run_covers_every_due_target` as the run's rows *equal* `due_targets(issued_at)` and also requires "a lead over 18 h" to flip exactly its own check. A row more than 18 h ahead is by definition not in `due_targets(issued_at)`, so with set equality it would flip both.
- **Resolution:** the coverage check fails on a due target with no row; the lead check fails on any row outside (0, 18 h]. Equality holds when both pass. Each listed failure flips exactly one check, shown by the tests.
- **Files:** backend/day_ahead_verify.py, backend/tests/day_ahead_verify_test.py
- **Commit:** 42a12c7

### Auto-fixed Issues

None - the 8 first-run failures were defects in my own new test helper before the first commit, not in committed code.

### Notes (no code change)

- The plan's verify for Task 2 includes `secret_scan_test.py`; one test in it (the owner-local exact-value scan) is skipped unless the three Supabase variables are exported. That is its standing behavior, not a skip in this plan's own tests.
- `SUPABASE_DB_URL` is read with `os.environ` after the manifest is read, so `--help` and bad-argument paths work without it.

---

**Total deviations:** 0 auto-fixed; 1 plan-interpretation note above. **Impact on plan:** none; all must-have truths hold.

## Issues Encountered

None beyond the test-helper defect already described.

## Known Stubs

None. No hardcoded empty value, placeholder or unwired data source in the new files.

## Threat Flags

None. The new surface (a read of the live write side with the writer connection, evidence JSON, runbook text) is in the plan's threat model: T-08-17 (redaction tested with a planted URL, password, host and project reference, including a hostile value in a row; the secret scan passes), T-08-18 (read-only session proven by a spy and by a refused write for a role that holds INSERT) and T-08-19 (the runbook test pins constants, flags and tool names).

## User Setup Required

None for this plan. The owner runs `day_ahead_verify.py --check-store` only after 08-07 and 08-08 (apply the migration, push, first live run). Nothing here touched the live Supabase project or the live job, and nothing was pushed.

## Next Phase Readiness

- 08-08 can use the check as the go-live evidence step: `PYTHONPATH=backend .venv/bin/python backend/day_ahead_verify.py --check-store --since <PUSH_TIME_UTC> --json-out <EVIDENCE_FILE>`, then the secret scan over the committed evidence.
- 08-10 adds `--check-rest` to the same script; `main` currently refuses a call without `--check-store` with exit 2 and a one-line message, which is the place to extend.
- The expose migration (08-09) does not change what this script reads: it uses the writer connection, not the public key.

## Self-Check: PASSED

- Files present: `backend/day_ahead_verify.py`, `backend/tests/day_ahead_verify_test.py`, `docs/data-science/decisions/dlr_live_runbook.md`, `backend/tests/dlr_live_runbook_test.py`.
- Commits `42a12c7` and `c15b78e` are ancestors of HEAD; `git rev-list --count 2be4630..HEAD` = 2 before this summary.
- Task 1 acceptance: `day_ahead_verify_test.py` 30 passed, none skipped; `--help` exits 0 and names `--check-store`, `--since`, `--json-out`; `secret_scan_test.py` and `supabase_load_backfill_test.py` (private-name guard) pass.
- Task 2 acceptance: `dlr_live_runbook_test.py` and `secret_scan_test.py` 10 passed, 1 skipped (owner-local scan); `grep -c "^## 17. Day-ahead forecast stage (Phase 8)"` prints 1; the removed-line check on `dlr_live_runbook_test.py` prints 0 and exits 0.
- Full suite with `DLR_TEST_PG_AUTOSTART=1`: 2894 passed.

---
*Phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6*
*Completed: 2026-11-08*
