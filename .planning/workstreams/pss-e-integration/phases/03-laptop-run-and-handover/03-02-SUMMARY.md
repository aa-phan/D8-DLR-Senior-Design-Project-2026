---
phase: 03-laptop-run-and-handover
plan: 02
subsystem: database
tags: [gap-check, sql, sch-02, postgres, read-only, psycopg, independent-oracle]

requires:
  - phase: 01-writer-and-contract
    provides: psse_run table, slot_time hour check, dlr_psse_writer role with select grant and policy, writer.connect, redaction
provides:
  - docs/data-science/schema/psse_run_gaps.sql, the read-only SCH-02 statement (no_run and failed_only hours)
  - psse_job.gaps (GapRow, load_sql, fetch_gaps, fetch_summary, format_report, run, EXIT_OK 0, EXIT_GAPS 5, EXIT_CHECK_FAILED 6)
affects: [03-04 launcher gaps mode, 03-06 guide, 03-08 induced-gap laptop step]

actuals:
  tokens: 7200
  tasks: 3
  commits: 3
plan_head_before: d967e48236e362f63ff19dd321014b774f19ecb4
plan_head_after: cc3d843cd3a78c738c3b7a38aa19d6104fef169e

tech-stack:
  added: []
  patterns:
    - "SQL file is the only gap logic; Python runs it, filters rows by since/until and formats them"
    - "independent pure-Python oracle compared with the SQL over seeded random histories, with hour-roll retry"
    - "recording connection proxy that asks the server (show transaction_read_only) before each statement"

key-files:
  created:
    - docs/data-science/schema/psse_run_gaps.sql
    - backend/psse_job/gaps.py
    - backend/tests/psse_gaps_pg_test.py
  modified: []

key-decisions:
  - "The planning-time SQL was kept unchanged (only a header comment added); no logic edit was needed"
  - "gaps.run sets conn.autocommit = False before conn.read_only = True (see Deviations)"
  - "Header says 'N runs recorded'; the window, when since or until is given, is stated on the gap-count line"

patterns-established:
  - "Mutation harness outside the repository (scratchpad mutate_0302.py): exact-text replace, named tests, byte-for-byte restore"

requirements-completed: [SCH-02]

duration: about 45 min
completed: 2026-10-29
status: complete
---

# Phase 3 Plan 02: Gap statement and gap check Summary

**One read-only SQL statement lists every UTC hour with no complete result set (no_run or failed_only), and `gaps.run` runs it on a really read-only writer session; both are held to an independent pure-Python oracle on local Postgres 18.6.**

## Commits

| Commit | Subject |
|--------|---------|
| cc4e5d0 | feat(03-02): tracer - the gap statement and gaps.run list the missing hours of a seeded run history |
| 4d124d3 | test(03-02): the gap statement equals an independent reference over seeded random histories and every edge case |
| cc3d843 | test(03-02): the gap check is read-only, behaves the same under the writer role and prints no secret or identifier |

`commits: 3` is measured (`git rev-list --count d967e48..cc3d843`); the docs commit of this SUMMARY is not counted.

## Accomplishments

- `psse_run_gaps.sql`: header (purpose, columns, two gap kinds, the five rules, SELECT only, no percent sign) and one statement; the planning-time text is unchanged.
- `gaps.py`: standard library plus psse_job, Python 3.7 syntax, no psycopg import; exit codes 0, 5, 6; since inclusive, until exclusive, filtered in Python; failure prints one redacted line "gap check could not run: ...".
- 13 tests in `psse_gaps_pg_test.py`: tracer, 30 random histories against `reference_gaps`, empty table, current hour only, single closed slot, duplicates and failed-plus-complete, since/until, and six `test_gap_safe_*` proofs.

## Test results

- `psse_gaps_pg_test.py` (PG prefix, PSSE_REQUIRE_PG=1): 13 passed, 0 skipped.
- `psse_contract_test.py` plus `secret_scan_test.py`: 13 passed.
- Own-changes gate (PLAN=03-02): exit 0 after each commit.
- No postgres process left running after the last run.

## Mutation results (each planted, named test red, restored byte for byte; `git diff --quiet` on both files passed afterwards)

| Planted fault | Red tests |
|---------------|-----------|
| SQL: drop "minus one hour" (current hour included) | test_gap_sql_matches_independent_reference_over_random_histories, test_gap_only_current_hour_has_no_gaps |
| SQL: failed-only slot treated as complete | the reference test, test_gap_single_closed_slot_complete_and_failed_only |
| SQL: slot with more than one row listed | test_gap_duplicates_and_failed_plus_complete_are_not_gaps |
| SQL: generate_series starts at a fixed past date | the reference test |
| gaps.py: skip `conn.read_only = True` | test_gap_safe_session_is_read_only |
| gaps.py: skip `conn.autocommit = False` | test_gap_safe_session_is_read_only |
| gaps.py: print the case label | test_gap_safe_report_holds_only_times_kinds_and_counts |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `conn.read_only = True` alone does not make the session read-only on writer.connect's autocommit connection**
- **Found during:** Task 3 (a control test inserted a row through a connection with only `read_only = True` set and it succeeded)
- **Issue:** psycopg applies `read_only` to the transactions it opens itself (BEGIN READ ONLY), never to autocommit statements. The plan's D-03 assumed the flag was enough; as written, the gap check would have run writable, with INSERT held by the writer role.
- **Fix:** `gaps.run` sets `conn.autocommit = False` first, then `conn.read_only = True`, so both statements run inside one `BEGIN READ ONLY` transaction (rolled back on close). The statement count stays two. The session test uses a recording proxy that asks the server `show transaction_read_only` before each statement, and a second part shows a read-only insert is refused with ReadOnlySqlTransaction. Mutation "skip autocommit line" turns it red.
- **Files modified:** backend/psse_job/gaps.py, backend/tests/psse_gaps_pg_test.py
- **Commit:** cc3d843

**2. [Rule 1 - Test sensitivity] test_gap_only_current_hour_has_no_gaps first used a complete run in the current hour**
- **Found during:** mutation check (the "include current hour" fault left it green)
- **Fix:** the test seeds a failed row in the current hour only, which the faulty statement lists as failed_only. Re-run: both named tests go red.
- **Commit:** the test came in 4d124d3 and was corrected in cc3d843

The `connect` seam now has to accept `autocommit` and `read_only` attribute assignment (a real psycopg connection does; a fake only needs to tolerate it). Plan 03-04 and 03-06 should keep that in mind.

## Authentication gates

None.

## Known Stubs

None.

## Threat Flags

None. The statement is SELECT only and now runs in a read-only transaction (T-03-10); output holds slot times, kinds and counts (T-03-11); T-03-09 is covered by the oracle and the mutations above.

## Honest scope (UNVERIFIED until runbook step 10, plan 03-08)

Proved on local Postgres 18.6 only. Not proved: the live table with the real laptop's hours, laptop clock agreement with the database, daylight-saving effects, an induced gap.

## Self-Check: PASSED

- Files exist: psse_run_gaps.sql, gaps.py, psse_gaps_pg_test.py
- Commits cc4e5d0, 4d124d3, cc3d843 are ancestors of HEAD
