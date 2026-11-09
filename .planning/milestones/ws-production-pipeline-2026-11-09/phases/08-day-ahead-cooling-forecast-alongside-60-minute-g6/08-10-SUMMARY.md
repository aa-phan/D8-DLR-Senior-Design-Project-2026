---
phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6
plan: 10
subsystem: docs
tags: [day-ahead, consumer-contract, rest-api, postgrest, runbook, doc-tests, redaction, tdd]

requires:
  - phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6
    provides: "08-06 day_ahead_verify.py (--check-store, main, CheckResult); 08-08 verified first live slot (published out-of-range values); 08-09 day_ahead_upcoming (26 columns), day_ahead_status (7), SELECT-only grants, assert_fresh day_ahead_late / day_ahead_armed, verify_exposure.sql (29 checks)"
provides:
  - "docs/data-science/schema/day_ahead_forecast_v1.md: the consumer schema doc for the day-ahead table and views (label, owner paragraph, '24 h' meaning, issue lead, band and late rules)"
  - "docs/integration/rest-api.md: three endpoint rows, the assert_fresh day_ahead_late / day_ahead_armed clause, a Day-ahead forecast section and two parsed column tables"
  - "backend/day_ahead_verify.py --check-rest: eight consumer-side checks with the publishable key only, two refused-write probes, recovery SQL, redacted JSON"
  - "Runbook section 14 alarm clause, section 16 re-check for the post-expose surface, section 3 dlr_writer grants derived from the migrations by a test"
affects: [08-11, 08-12]

actuals:
  tokens: 18000
  tasks: 2
  commits: 4
plan_head_before: 4de381aded39c76cd6b4a811363448d66b76ceb4
plan_head_after: a83316cbe5815525e7284bed992b23f3a3c4b79a

tech-stack:
  added: []
  patterns:
    - "Doc column tables parsed by tests and compared with the contract module (UPCOMING_COLUMNS, STATUS_COLUMNS, TABLE_COLUMNS), so a contract change without the docs fails"
    - "In-process fake PostgREST handed to main() as the opener: no socket, no database, no network; every failure flips exactly its own named check"
    - "Runbook text tied to the migrations: a test derives dlr_writer's table grants from supabase/migrations/*.sql and compares the runbook row, clause by clause"

key-files:
  created:
    - docs/data-science/schema/day_ahead_forecast_v1.md
  modified:
    - docs/integration/rest-api.md
    - docs/data-science/decisions/pss_e_handoff.md
    - docs/data-science/decisions/dlr_live_runbook.md
    - backend/day_ahead_verify.py
    - backend/tests/rest_api_doc_test.py
    - backend/tests/day_ahead_verify_test.py
    - backend/tests/dlr_live_runbook_test.py

key-decisions:
  - "The docs state that out-of-range day-ahead values are published as computed (the live rating falls back to the static rating outside its bounds; the day-ahead value never does), citing the two MIDLAND values below 1250 A from the first live slot, so no consumer reads the live rating's bounds as a promise about this feed"
  - "--check-rest and --check-store are separate runs (exit 2 if both are given): one needs the writer connection, the other the publishable key, and one JSON report should describe one proof"
  - "An empty upcoming view or an empty table answer fails its checks instead of passing vacuously: an empty 200 is exactly how a missing read policy looks"
  - "The anon insert and view write are classified with e2e_verify_readonly's own classifiers, so an insert refused only by row-level security (a write grant still present) or by a bare 401 'Invalid API key' is a failure, which is stricter than the plan's '401 or 403 with 42501' wording"
  - "Both write probes use the year-2000 sentinel key; the view write is a PATCH on that key, which the view never shows, so even an accepted write cannot change a published value"

patterns-established:
  - "A RED commit (test) then a GREEN commit (docs or feat) per task, as in 08-09"

requirements-completed: [DAY-06, DAY-07, DAY-08]

coverage:
  - id: D1
    description: "The day-ahead consumer contract (rest-api.md, the new schema doc, the PSS/E note) carries the D-11 label and the owner paragraph verbatim, cites the +23 A / ~1.7% figures as exploratory, says '24 h' is the age of the weather run and a value is issued 0 to 18 hours before its target, and states the band, issue and late rules"
    requirement: "DAY-06"
    verification:
      - kind: unit
        ref: "backend/tests/rest_api_doc_test.py#test_day_ahead_docs_carry_the_label_and_the_owner_paragraph"
        status: pass
      - kind: unit
        ref: "backend/tests/rest_api_doc_test.py#test_day_ahead_docs_say_what_24_h_means_and_state_the_band_and_late_rules"
        status: pass
      - kind: unit
        ref: "backend/tests/rest_api_doc_test.py#test_day_ahead_docs_link_to_each_other_and_to_the_pss_e_note"
        status: pass
    human_judgment: false
  - id: D2
    description: "The two new REST column tables equal UPCOMING_COLUMNS and STATUS_COLUMNS and the schema doc's table equals TABLE_COLUMNS, column for column, with a type, a unit and a meaning on every row"
    requirement: "DAY-06"
    verification:
      - kind: unit
        ref: "backend/tests/rest_api_doc_test.py#test_doc_upcoming_table_matches_the_contract"
        status: pass
      - kind: unit
        ref: "backend/tests/rest_api_doc_test.py#test_doc_status_table_matches_the_contract"
        status: pass
      - kind: unit
        ref: "backend/tests/rest_api_doc_test.py#test_schema_doc_table_matches_the_contract"
        status: pass
    human_judgment: false
  - id: D3
    description: "day_ahead_verify.py --check-rest passes against healthy post-expose answers (eight checks, exit 0) and each failure (a past or unordered upcoming row, a missing, extra or reordered column, three cities, a late city, an empty table, assert_fresh 503, day_ahead_armed false or missing, an accepted or RLS-only or bare-401 insert, an accepted or bare-403 view write, a readable run log) flips exactly its own check with exit 1"
    requirement: "DAY-08"
    verification:
      - kind: unit
        ref: "backend/tests/day_ahead_verify_test.py#test_rest_check_passes_against_the_healthy_post_expose_answers"
        status: pass
      - kind: unit
        ref: "backend/tests/day_ahead_verify_test.py#test_rest_each_failure_flips_exactly_its_own_check_and_exits_one"
        status: pass
    human_judgment: false
  - id: D4
    description: "The check never prints or stores the URL, host, project reference or key (an error body and a connection failure that echo them, and a hostile served value), refuses a secret key and a missing variable with exit 2 before any request, sends the key in apikey only, and writes only the two year-2000 probes; an accepted insert prints the sentinel recovery SQL"
    requirement: "DAY-08"
    verification:
      - kind: unit
        ref: "backend/tests/day_ahead_verify_test.py#test_rest_neither_the_url_nor_the_key_reaches_stdout_stderr_or_the_json"
        status: pass
      - kind: unit
        ref: "backend/tests/day_ahead_verify_test.py#test_rest_a_hostile_value_inside_a_row_is_redacted_in_the_report_and_the_json"
        status: pass
      - kind: unit
        ref: "backend/tests/day_ahead_verify_test.py#test_rest_requests_use_the_key_in_apikey_only_and_write_only_the_two_probes"
        status: pass
      - kind: unit
        ref: "backend/tests/day_ahead_verify_test.py#test_rest_an_accepted_anon_insert_prints_the_recovery_sql_for_the_sentinel_row"
        status: pass
    human_judgment: false
  - id: D5
    description: "Runbook section 14 states the day-ahead alarm clause, section 16 describes the post-expose public surface (five objects, 29 rows, the --check-rest command, the 08-11 comparison) with exactly five table rows, and section 3 states dlr_writer's four grants as the migrations define them"
    requirement: "DAY-07"
    verification:
      - kind: unit
        ref: "backend/tests/dlr_live_runbook_test.py#test_runbook_section_14_states_the_day_ahead_alarm_clause"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_runbook_test.py#test_permission_recheck_states_the_day_ahead_surface"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_runbook_test.py#test_secrets_section_states_the_writer_grants_from_the_migrations"
        status: pass
      - kind: unit
        ref: "backend/tests/monitoring_runbook_test.py"
        status: pass
    human_judgment: false
  - id: D6
    description: "The documents read correctly to a dashboard or PSS/E engineer, and the --check-rest check passes against the live project after the expose migration"
    requirement: "DAY-08"
    verification: []
    human_judgment: true
    rationale: "Wording adequacy for a human reader is not asserted by any test, and the live run is the owner's step in 08-11 after the expose migration is applied; nothing here touched the live project"

duration: 14min
completed: 2026-11-09
status: complete
---

# Phase 8 Plan 10: Day-Ahead Consumer Contract and REST Check Summary

**The day-ahead forecast now has a consumer contract (a new schema doc, rest-api.md endpoints, alarm clause and two parsed column tables, all carrying the label, the owner's paragraph and the honest "24 h" lead and band notes) and `day_ahead_verify.py --check-rest`, an eight-check anon proof of the exposed objects with refused-write probes, all guarded by tests against the contract module; nothing was applied or pushed.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-11-09T01:26:57Z
- **Completed:** 2026-11-09T01:41Z
- **Tasks:** 2 (both TDD: a failing-test commit then a GREEN commit each)
- **Files:** 1 created, 7 modified

## Accomplishments

- **Schema doc** `docs/data-science/schema/day_ahead_forecast_v1.md` (ten headings, plain English first): the label, the D-11 paragraph verbatim once, the +23 A / ~1.7% figures cited as exploratory with a link to the horizon comparison REPORT.md, the 25-column table, the two views, when values appear, the band (16 bands, TEST at launch against reanalysis with a 24 h anchor, live rolling from 60 graded pairs of the newest 120 against the station-composed rating with static-fallback hours excluded), the late rule armed by the first value, identity, MW conversion, versioning. It states that "24 h" is the age of the weather run and a value is issued 0 to 18 hours before its target, and that the anchor reading is 24 h ahead in TEST, about 12 h in the shadow and up to 18 h live.
- **Honest live fact (from 08-08):** the schema doc and rest-api.md say out-of-range values are published as computed, not withheld (two MIDLAND values were below the 1250 A floor), and that the live rating's fallback bounds do not apply to this feed.
- **rest-api.md:** three endpoint rows, the Connecting sentence, the assert_fresh bullet, the PT503 row and the Monitoring sentence extended with `day_ahead_late=...`, `day_ahead_armed` and "armed by the first value" (no new cron job), then `## Day-ahead forecast`, ``## `day_ahead_upcoming` columns`` (26 rows) and ``## `day_ahead_status` columns`` (7 rows, `timestamptz[]` for `missing_targets`). The existing 16 headings and their order are untouched. `pss_e_handoff.md` gained a two-sentence `## Day-ahead forecast (2026-11)` section before its footer. `city_rating_v1.md` is unchanged.
- **`--check-rest`:** `rest_upcoming_rows_are_future_and_ordered`, `rest_upcoming_columns_match_the_contract`, `rest_status_has_four_cities_none_late`, `rest_table_is_readable`, `rest_assert_fresh_ok_and_armed`, `rest_anon_insert_into_table_refused`, `rest_anon_write_to_upcoming_view_refused`, `rest_pipeline_run_hidden`. Publishable key only (`config_from_env` refuses a secret key before any request); one sentinel insert (AUSTIN, 2000-01-01T00:00:00Z, every column valid) and one PATCH of that key on the view, each classified with `e2e_verify_readonly`'s classifiers; if the insert is accepted the output prints the exact `delete from public.day_ahead_forecast ...` for the owner and the script deletes nothing. Report and JSON `{checks, attempts, exit_code}`, every text through `redact_rest`.
- **Runbook:** section 14 paragraph (day-ahead clause, what to do), section 16 brought up to the post-expose surface (Database permission list names the five objects and 29 rows, Writes and Writer smoke rows name exactly what their tools probe, "either table" gone, a `--check-rest` command, expected results compared with 06-09 and 08-11's evidence, SELECT on the three objects "expected since 08-11 and not a discrepancy", still exactly five rows), section 3 `SUPABASE_DB_URL` row states `dlr_writer`'s four grants.
- Full suite with local Postgres: **2977 passed**, 0 failed (2933 after 08-09, plus 44 new: 9 doc tests, 32 REST-check tests, 3 runbook tests).

## Task Commits

1. **Task 1 RED:** `6c7ce41` test(08-10): add failing tests for the day-ahead consumer contract
2. **Task 1 GREEN:** `b1f9d9a` docs(08-10): day-ahead consumer contract
3. **Task 2 RED:** `13053d6` test(08-10): add failing tests for the REST check and the runbook alarm, re-check and grant text
4. **Task 2 GREEN:** `a83316c` feat(08-10): REST check for the exposed day-ahead objects

**Plan metadata:** recorded in the docs commit that follows this summary.

## TDD Gate Compliance

RED then GREEN for both tasks; no refactor commit was needed.

- **Task 1 RED (`6c7ce41`):** 9 of the 19 tests in `rest_api_doc_test.py` failed, the 10 pre-existing ones passed. Failures were the planned assertions: `day_ahead_forecast_v1.md` did not exist (FileNotFoundError), and the new headings, tables, endpoint rows and clauses were absent from rest-api.md and pss_e_handoff.md. Semantic assessment: the target tests executed and failed because the planned documents and text were missing, not on an import, syntax or fixture fault.
- **Task 2 RED (`13053d6`):** 31 failed in the REST selection of `day_ahead_verify_test.py` (`main` took no `opener` and had no `--check-rest`), and 3 runbook tests failed on the planned strings (section 14 lacked `day_ahead_late`, section 16 lacked `city_rating` in the permission row, the section 3 row still said "the two tables"). The writer-grants test's first assertion (the map derived from the migrations equals the four expected entries) already passed and its failure was the runbook row, as intended. Semantic assessment: valid RED on the planned assertions; the REST failures are interface-level (unknown keyword and flag), the same kind of RED as 08-01 and 08-06.
- Mutation checks by hand: removing the report-layer redaction failed the hostile-value test (restored); a temporary migration granting `dlr_writer` DELETE, one revoking from it, and one granting inside a `do` block each failed the writer-grants test, and a commented grant was ignored (the probe file was removed).
- The `gsd check tdd-red-evidence` classifier was not run: pytest's console output is not one of its supported formats and `TDD_MODE` was not enabled.

## Files Created/Modified

- `docs/data-science/schema/day_ahead_forecast_v1.md` - new consumer schema doc
- `docs/integration/rest-api.md` - endpoints, alarm clause, Day-ahead forecast section, two parsed column tables
- `docs/data-science/decisions/pss_e_handoff.md` - short day-ahead section with pointers (08-12 expands it)
- `docs/data-science/decisions/dlr_live_runbook.md` - sections 3, 14 and 16
- `backend/day_ahead_verify.py` - `--check-rest`, `check_rest`, `main(argv, manifest_path, opener, now)`
- `backend/tests/rest_api_doc_test.py` - `_column_rows(heading, path)`, `timestamptz[]` allowed, 9 new tests (existing tests unedited)
- `backend/tests/day_ahead_verify_test.py` - in-process `FakeRest` and 32 REST tests (existing tests unedited)
- `backend/tests/dlr_live_runbook_test.py` - 3 new tests and a grant parser (existing tests unedited)

## Decisions Made

See `key-decisions`: out-of-range values stated plainly, separate `--check-store` / `--check-rest` runs, no vacuous passes on empty answers, the stricter e2e classifiers for the write probes, year-2000 keys for both probes.

## Deviations from Plan

### Plan interpretation (no code defect)

**1. Write probes use the e2e classifiers, which are stricter than the plan's sentence**
- **Found during:** Task 2 (designing the insert check)
- **Issue:** the plan says the insert passes "only on 401 or 403 with code 42501" and the view write on a named set of codes. `e2e_verify_readonly._classify_table_write` additionally fails a 42501 whose message says "row-level security" (a write grant is still present) and needs "permission denied". That is the Phase 6 rule for the same kind of probe.
- **Resolution:** reused the classifiers (the plan also says "as e2e_verify_readonly classifies"); a refusal by privilege is what D-09 promises, an RLS-only refusal would hide a stray grant. Tests cover the RLS-only and bare-401 cases.
- **Files:** backend/day_ahead_verify.py, backend/tests/day_ahead_verify_test.py
- **Commit:** a83316c

**2. `--check-store` plus `--check-rest` is refused**
- **Issue:** the plan only says to add `--check-rest` where a call without `--check-store` exited 2. Running both would need two different credentials and produce one mixed report.
- **Resolution:** both together is exit 2 with a one-line message; each is its own run. Tested.

**3. `timestamptz[]` added to `ALLOWED_TYPES`**
- The plan allows this "only if the parser needs it for missing_targets"; it does (the status table's `missing_targets`). The existing latest_rating test still passes.

**4. Section 3 row cites migration stamps, not line numbers**
- The plan lists line numbers (110, 70-71); the row names the three migration stamps and says a test derives the grants again, because line numbers go stale and the test is the real check.

### Additions beyond the plan (not defects)

- One extra test, `test_rest_a_hostile_value_inside_a_row_is_redacted_in_the_report_and_the_json`, proving the report layer redacts on its own (an unredacted print failed it).
- The upcoming check also fails a target that is not on the 00/06/12/18 UTC grid, and allows 2 minutes of clock difference between the owner's machine and the server for "future".

### Auto-fixed Issues

None.

**Total deviations:** 0 auto-fixed; 4 plan-interpretation notes above. **Impact:** none on the must-have truths; all hold.

## Issues Encountered

- Between the RED commits and their GREEN commits the suite is red by design (same as 08-09); the plan's verify commands run at the GREEN commits.
- The owner-local scan in `secret_scan_test.py` (needs the three Supabase values exported) was not exercised here, as in 08-08 and 08-09; the repository-wide secret scan and the doc and runbook secret tests pass.

## Known Stubs

None. No hardcoded empty value, placeholder or unwired data source in the new files.

## Threat Flags

None. The new surface is the planned one: T-08-30 (angle-bracket stand-ins only; `secret_scan_test.py`, the doc no-connection-details test for the new docs and the runbook secret test pass), T-08-31 (config refuses a secret key; every text through `redact_rest`; three redaction tests), T-08-32 (year-2000 sentinel key for both probes, recovery SQL printed if ever accepted, one POST and one PATCH sent in a healthy run), T-08-33 (label and paragraph verbatim, "24 h" and band notes, guarded by doc tests against the contract module).

## User Setup Required

None for this plan. The owner applies the expose migration and runs `--check-rest` in 08-11, then pushes the docs. Nothing here touched the live Supabase project, read `.env` or was pushed.

## Next Phase Readiness

- **08-11** can apply `20261108120100_expose_day_ahead_forecast.sql`, run `verify_exposure.sql` (29 rows) and `PYTHONPATH=backend .venv/bin/python backend/day_ahead_verify.py --check-rest --json-out <08-11-live-checks.json>`, then publish these committed docs with its push. Section 16 already says what to compare it with.
- **08-12** expands the PSS/E note's `## Day-ahead forecast (2026-11)` section for next-day studies (D-18).
- Docs and runbook are committed locally and describe the post-expose state; they must not be pushed before the expose migration is applied.

## Self-Check: PASSED

- Files found: `docs/data-science/schema/day_ahead_forecast_v1.md`, `docs/integration/rest-api.md`, `docs/data-science/decisions/pss_e_handoff.md`, `backend/day_ahead_verify.py`, `backend/tests/rest_api_doc_test.py`, `backend/tests/day_ahead_verify_test.py`, `backend/tests/dlr_live_runbook_test.py`, `docs/data-science/decisions/dlr_live_runbook.md`.
- Commits found as ancestors of HEAD: `6c7ce41`, `b1f9d9a`, `13053d6`, `a83316c`; `git rev-list --count 4de381a..HEAD` = 4 before this summary.
- Task 1 acceptance: verify command (31 passed, 1 skipped owner-local scan) ; owner paragraph count 1 in each of the two docs; `git diff --quiet -- docs/data-science/schema/city_rating_v1.md` exits 0.
- Task 2 acceptance: verify command 169 passed; `--help` names `--check-rest`; `grep -c day_ahead_late` runbook = 3; `grep -c "day_ahead_verify.py --check-rest"` = 1; permission-recheck test 1 passed; writer-grants test 1 passed; `monitoring_runbook_test.py` 7 passed and unedited; the section 3 row check prints ok.
- Full suite with `DLR_TEST_PG_AUTOSTART=1`: 2977 passed.

---
*Phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6*
*Completed: 2026-11-09*
