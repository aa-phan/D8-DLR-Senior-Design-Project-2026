---
phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6
plan: 12
subsystem: docs
tags: [day-ahead, consumer-examples, handoff-docs, pss-e, supabase-js, curl, fake-postgrest, tdd]

requires:
  - phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6
    provides: "08-01 day_ahead_contract (DAY_AHEAD_LABEL, UPCOMING_COLUMNS, STATUS_COLUMNS); 08-09 day_ahead_upcoming and day_ahead_status views; 08-10 consumer contract text in rest-api.md, day_ahead_forecast_v1.md and a short PSS/E section"
provides:
  - "read_ratings.py Part 3, curl.sh section 3 and supabase_js.mjs part (3): upcoming day-ahead targets per city and the per-city stall status, read-only, label printed"
  - "backend/tests/fake_postgrest.py: make_day_ahead_view_rows and the day_ahead_upcoming / day_ahead_status routes (FakePostgrest(day_ahead_upcoming=, day_ahead_status=))"
  - "Day-ahead handoff text for the Software team, the frontend api-contract, the PSS/E team and the rest-api Examples section"
  - "backend/tests/day_ahead_consumer_docs_test.py: 10 text guards against the contract module"
affects: [08-11]

actuals:
  tokens: 11200
  tasks: 3
  commits: 6
plan_head_before: da88688683a4e0bb2783ea92fe1c06e6f9ec59d2
plan_head_after: fa170c35562df3d33c5d71dea870f56e5a2ad6b4

tech-stack:
  added: []
  patterns:
    - "Select lists parsed out of each example (Python constant, curl URL, supabase-js call) and compared with the contract module and with each other"
    - "Existing example tests extended by added functions only; the one edited line is the curl invocation count (3 to 5)"
    - "Fake server serves new relations through the existing _read path, with caller-supplied lists or defaults built from the fake's clock"

key-files:
  created:
    - backend/tests/day_ahead_consumer_docs_test.py
  modified:
    - docs/integration/examples/read_ratings.py
    - docs/integration/examples/curl.sh
    - docs/integration/examples/supabase_js.mjs
    - backend/tests/fake_postgrest.py
    - backend/tests/example_read_ratings_test.py
    - docs/integration/software-team-handoff.md
    - docs/frontend/specs/api-contract.md
    - docs/data-science/decisions/pss_e_handoff.md
    - docs/integration/rest-api.md

key-decisions:
  - "The empty-feed label line in read_ratings.py falls back to the contract label constant, so every run prints the label even with no upcoming rows; with rows it shows the distinct labels actually served"
  - "A late feed is printed (a stdout line naming the city and missing targets in UTC) and exits 0; only a failed read or a status without all four cities exits 1, matching the plan"
  - "The PSS/E note adds one sentence the plan did not ask for: El Paso keeps Mountain time, one hour earlier than the Central table, so a four-city study should state its hour in UTC"
  - "Both TDD tasks that touch examples use a RED commit (tests plus fake) then a GREEN commit, as in 08-09 and 08-10, instead of one commit per task"

patterns-established:
  - "Indented output lines for any new example part, so they can never match Part 1's city-line pattern"

requirements-completed: [DAY-06, DAY-08, DAY-09]

coverage:
  - id: D1
    description: "read_ratings.py prints the upcoming day-ahead targets (12 lines, three per city in config order, UTC Z, amps, band, lead, source) and four status lines after Parts 1 and 2, on /usr/bin/python3 (3.9) and the repository interpreter, with empty stderr, no file written and Parts 1 and 2 unchanged"
    requirement: "DAY-09"
    verification:
      - kind: unit
        ref: "backend/tests/example_read_ratings_test.py#test_day_ahead_tracer_read_ratings_prints_targets_and_status"
        status: pass
      - kind: unit
        ref: "backend/tests/example_read_ratings_test.py#test_tracer_read_ratings_runs_against_the_fake"
        status: pass
    human_judgment: false
  - id: D2
    description: "Empty upcoming prints a notice and exits 0; a late city prints a LATE line and exits 0; a three-row status exits 1 naming the city; a 404 on day_ahead_upcoming exits 1 after Parts 1 and 2 with neither key nor URL printed"
    requirement: "DAY-09"
    verification:
      - kind: unit
        ref: "backend/tests/example_read_ratings_test.py#test_day_ahead_empty_upcoming_prints_a_notice_and_exits_0"
        status: pass
      - kind: unit
        ref: "backend/tests/example_read_ratings_test.py#test_day_ahead_late_city_is_printed_and_is_not_an_error"
        status: pass
      - kind: unit
        ref: "backend/tests/example_read_ratings_test.py#test_day_ahead_status_missing_a_city_exits_1_and_names_it"
        status: pass
      - kind: unit
        ref: "backend/tests/example_read_ratings_test.py#test_day_ahead_http_error_on_upcoming_exits_1_after_the_rating_parts"
        status: pass
    human_judgment: false
  - id: D3
    description: "curl.sh and supabase_js.mjs read the two views read-only with the same select lists as the Python example (all subsets of the contract columns); curl exits non-zero on a 404; the supabase-js file passes node --check, sets exitCode on a short status and never installs a package; the read-only, one-header and no-project-value tests pass on the extended files"
    requirement: "DAY-09"
    verification:
      - kind: unit
        ref: "backend/tests/example_read_ratings_test.py#test_curl_day_ahead_reads_upcoming_and_status_after_the_paging_output"
        status: pass
      - kind: unit
        ref: "backend/tests/example_read_ratings_test.py#test_curl_and_js_day_ahead_select_lists_are_subsets_of_the_contract"
        status: pass
      - kind: unit
        ref: "backend/tests/example_read_ratings_test.py#test_curl_day_ahead_error_on_the_status_view_exits_non_zero"
        status: pass
      - kind: unit
        ref: "backend/tests/example_read_ratings_test.py#test_supabase_js_day_ahead_part_contract"
        status: pass
      - kind: unit
        ref: "backend/tests/example_read_ratings_test.py#test_examples_are_read_only_and_send_one_credential_header"
        status: pass
    human_judgment: false
  - id: D4
    description: "The four consumer docs carry the day-ahead handoff text (Software section with a column-checked dashboard table, easy mistakes, key, readable and 503 rows; three api-contract rows; PSS/E next-day guidance with the UTC to CST and CDT table; the Examples sentence) and hold no secret, project host or URL"
    requirement: "DAY-06"
    verification:
      - kind: unit
        ref: "backend/tests/day_ahead_consumer_docs_test.py"
        status: pass
      - kind: unit
        ref: "backend/tests/rest_api_doc_test.py"
        status: pass
    human_judgment: false
  - id: D5
    description: "The handoff wording reads clearly to a dashboard developer and a PSS/E engineer, and the extended examples work against the live project after the expose migration"
    requirement: "DAY-08"
    verification: []
    human_judgment: true
    rationale: "Wording adequacy is not asserted by any test; the live example run is 08-11's step after the expose apply, and nothing here contacted the live project"

duration: 51min
completed: 2026-11-09
status: complete
---

# Phase 8 Plan 12: Day-Ahead Consumer Examples and Handoff Docs Summary

**All three consumer examples (Python 3.7+ stdlib, curl, supabase-js) now also read the upcoming day-ahead targets and the per-city stall status, read-only with one credential header and the label printed, and the Software, frontend and PSS/E handoff docs explain what to read, how to show it and how to use it in next-day studies; everything is committed locally and nothing was pushed or applied.**

## Performance

- **Duration:** 51 min
- **Started:** 2026-11-09T01:43:08Z
- **Completed:** 2026-11-09T02:35Z
- **Tasks:** 3 (all TDD: a failing-test commit then a GREEN commit each)
- **Files:** 1 created, 9 modified (765 lines added, 11 removed)

## Accomplishments

- **Fake server:** `make_day_ahead_view_rows(now, cities, per_city)` builds the 26-column upcoming rows and 7-column status rows from `day_ahead_contract`; `FakePostgrest` takes `day_ahead_upcoming=` and `day_ahead_status=` (None means defaults from the fake's clock at request time), serves GET and HEAD through the existing `_read` path (default order city then valid_time), and refuses writes with 401 42501. Other routes are unchanged; `e2e_readonly_test.py` and `e2e_trace_test.py` (111 tests) pass unedited.
- **read_ratings.py (tracer):** Part 3 after Parts 1 and 2, inside the same try. Prints a heading, the label line, a "not the live rating" line, one two-space-indented line per target and one per city status, a "day-ahead feed is LATE for ..." line when a city is late, and exits 1 only on a failed read or a status missing a city. Verified on Python 3.9 (`/usr/bin/python3 -I`, ast feature_version 3.7 clean) and 3.12.
- **curl.sh and supabase_js.mjs:** the same two reads with identical select lists and orders; curl uses two more `curl -fsS` lines (count pin 3 to 5, the only edited existing test line); supabase-js sets `process.exitCode = 1` on an error or a status with other than 4 rows and prints the label and any late city.
- **Docs:** `software-team-handoff.md` gets `## Day-ahead forecast` (what to read, dashboard table, six easy mistakes, polling note, links) plus a key-table row, three "What you can read" rows and `day_ahead_late` in the 503 row; `api-contract.md` gets three rows right after `latest_rating`; `pss_e_handoff.md` gets five `###` subsections (target hour with the CST and CDT table, read the band, what it is not, empty or late targets, running the example and the MW conversion); `rest-api.md` Examples names part (3).
- **Tests:** 12 new example tests (7 for Python, 4 for curl and supabase-js, plus the parametrized interpreter run counted once per interpreter) and 10 in the new `day_ahead_consumer_docs_test.py`. Full suite with local Postgres: **2999 passed** (2977 after 08-10, plus 22 new).

## Task Commits

1. **Task 1 RED:** `9e03430` test(08-12): add failing tests for the day-ahead part of read_ratings.py (includes the fake extension)
2. **Task 1 GREEN:** `6174a48` feat(08-12): read_ratings.py reads the day-ahead views
3. **Task 2 RED:** `44bf867` test(08-12): add failing tests for the day-ahead part of curl.sh and supabase_js.mjs
4. **Task 2 GREEN:** `7889827` feat(08-12): curl and supabase-js examples read the day-ahead views
5. **Task 3 RED:** `c527613` test(08-12): add failing tests for the day-ahead handoff text in the consumer docs
6. **Task 3 GREEN:** `fa170c3` docs(08-12): day-ahead handoff for the Software and PSS/E teams

**Plan metadata:** recorded in the docs commit that follows this summary.

## TDD Gate Compliance

RED then GREEN for all three tasks; no refactor commit was needed.

- **Task 1 RED (`9e03430`):** 7 of the 8 new tests failed on planned assertions (day-ahead text absent from the output, `DAY_AHEAD_UPCOMING_SELECT` missing, exit 0 where 1 was planned); the fake-views test passed because the fake extension is in the same commit. The first collection attempt (before the fake helper existed) was an ImportError and was not used as RED. Semantic assessment: the target tests ran and failed on the planned behaviour, not on import or fixture faults.
- **Task 2 RED (`44bf867`):** 5 failed: the edited curl count (3 vs 5), and four new tests that failed because neither example had the day-ahead part (regex not found, exit 0 on a 404 override, `'day_ahead_upcoming'` absent).
- **Task 3 RED (`c527613`):** 7 failed because the docs lacked the section, rows, table and sentence; 3 guard tests (original headings and footer, hygiene, planted-value checks) passed as intended.
- The `gsd check tdd-red-evidence` classifier was not run: pytest console output is not one of its supported formats and `TDD_MODE` was not enabled.

## Files Created/Modified

- `docs/integration/examples/read_ratings.py` - Part 3, `DAY_AHEAD_UPCOMING_SELECT`, `DAY_AHEAD_STATUS_SELECT`, docstring items
- `docs/integration/examples/curl.sh` - section 3 and header comment
- `docs/integration/examples/supabase_js.mjs` - part (3) and header comment
- `backend/tests/fake_postgrest.py` - day-ahead views, `make_day_ahead_view_rows`, docstring route list
- `backend/tests/example_read_ratings_test.py` - new tests, import lines added, one assertion edited
- `backend/tests/day_ahead_consumer_docs_test.py` - new
- `docs/integration/software-team-handoff.md`, `docs/frontend/specs/api-contract.md`, `docs/data-science/decisions/pss_e_handoff.md`, `docs/integration/rest-api.md` - handoff text

## Decisions Made

See `key-decisions`: label fallback on an empty feed, a late feed is printed and not an error, an El Paso Mountain-time note, RED then GREEN commits per task.

## Deviations from Plan

### Plan interpretation (no code defect)

**1. Two commits per task instead of one**
- The plan's done lines name one commit per task; I followed the 08-09 and 08-10 pattern (a RED test commit, then the GREEN commit). The plan's "only additions" and "only the curl count line edited" checks hold against the plan's base commit `da88688` (diff shows exactly one removed line, the curl count) and, task by task, against each RED commit.

**2. El Paso Mountain-time sentence in the PSS/E note**
- The plan's UTC to Central table is kept as written; one sentence notes that El Paso keeps Mountain time. Added because a four-city study could otherwise misread the Central table for that city.

### Auto-fixed Issues

None.

**Total deviations:** 0 auto-fixed; 2 plan-interpretation notes above. **Impact:** none on the must-have truths; all hold.

## Issues Encountered

- Between each RED commit and its GREEN commit the suite is red by design; the plan's verify commands run at the GREEN commits.
- The one `-rs` skip in the verify runs is the owner-local exact-value secret scan (needs the three Supabase values exported), not a bash, curl, node or oldest-python case; those all ran.
- The supabase-js example is only syntax-checked (`node --check`); supabase-js is never installed in the repository, so its day-ahead reads are exercised live by 08-11.

## Known Stubs

None. No hardcoded empty value, placeholder or unwired data source in the new files; the fake's stand-in hashes are test data only.

## Threat Flags

None. T-08-40 (credentials only from the two variables, apikey header only; example no-URL-or-key test and the new hygiene test pass, secret scan passes), T-08-41 (GET and HEAD only; the read-only pattern test passes on the extended files and the fake records only GET and HEAD), T-08-42 (label and "not the live rating" printed by every example; doc tests assert the phrases), T-08-43 (nothing pushed), T-08-44 (Parts 1 and 2 unchanged, Python 3.7 grammar and stdlib-only tests pass, tracer ran on /usr/bin/python3) all held.

## User Setup Required

None. Nothing here touched the live Supabase project, read `.env`, applied a migration or was pushed.

## Next Phase Readiness

- **08-11** runs the three extended examples live after the expose apply (`day_ahead_upcoming` and `day_ahead_status` must exist), runs the REST checks, then publishes these and 08-10's commits with its push. It edits none of this plan's files.
- The new docs describe the post-expose state and must not be pushed before the expose migration is applied.

## Self-Check: PASSED

- Files found: all ten files in `key-files` exist on disk.
- Commits found as ancestors of HEAD: `9e03430`, `6174a48`, `44bf867`, `7889827`, `c527613`, `fa170c3`; `git rev-list --count da88688..HEAD` = 6 before this summary.
- Task 1 acceptance: verify command passed (134 tests at the GREEN commit); no removed lines in the test file at that point; `grep -c day_ahead_upcoming read_ratings.py` = 3.
- Task 2 acceptance: verify command passed; the only removed line of an existing test since `da88688` is `len(invocations) == 3`; `grep -c day_ahead_status` = 3 in each of curl.sh and supabase_js.mjs.
- Task 3 acceptance: 10 passed in `day_ahead_consumer_docs_test.py`; `grep -c "^## Day-ahead forecast$"` = 1; `grep -c "public.day_ahead_"` in api-contract.md = 3; `city_rating_v1.md` unchanged since `da88688`.
- Plan verification: 179 passed, 1 skipped (owner-local scan) across the example, e2e, doc and secret-scan tests; full suite with `DLR_TEST_PG_AUTOSTART=1`: 2999 passed.

---
*Phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6*
*Completed: 2026-11-09*
