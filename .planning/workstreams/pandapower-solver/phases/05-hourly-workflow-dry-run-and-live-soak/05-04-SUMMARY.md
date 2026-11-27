---
phase: 05-hourly-workflow-dry-run-and-live-soak
plan: 04
subsystem: ops
tags: [soak, gap-check, dry-run, postgres, throwaway-database, read-only, counts-only]
status: complete

requires:
  - phase: 05-hourly-workflow-dry-run-and-live-soak
    provides: "05-01 hourly.main run command and fixture; 05-02 soak.trailing_slots, soak.soak_passed and the size query"
  - phase: 03-solver-tag-migration-and-per-solver-gaps
    provides: "gaps.run_by_solver, gaps.fetch_runs, gaps.fetch_current_slot and the solver-tag schema"
provides:
  - "backend/pandapower_job/hourly.py: the soak command (gap_lines, parse_since, read_runs, run_soak, SOLVER_WORDS, five new vocabulary patterns, COMMAND_FLAGS soak)"
  - "backend/tests/pandapower_hourly_pg_test.py: database tier of the runner (dry unchanged with a live positive control, refusals as stored, soak on Postgres, size query)"
  - "backend/tests/pandapower_hourly_test.py: seven soak and gap_lines unit tests on a fake connection"
affects: [05-05, 05-06, 05-07, 05-08, workflow, owner-closing-check]

actuals:
  tokens: 9800
  tasks: 3
  commits: 3
plan_head_before: 6413aaa1d3debbdbcba05337762943008c6c935f
plan_head_after: aa70104b1e552e32d2302e5d94a638c0bc87696e

tech-stack:
  added: []
  patterns:
    - "database fingerprint (count and md5 of every row's text) before and after, with a live positive control so 'unchanged' can fail"
    - "the soak step reads twice on read-only connections (autocommit False, then read_only True, before any statement) and prints counts only"
    - "the hourly check reports and exits 0; only the owner's --since check is strict"

key-files:
  created:
    - backend/tests/pandapower_hourly_pg_test.py
  modified:
    - backend/pandapower_job/hourly.py
    - backend/tests/pandapower_hourly_test.py

key-decisions:
  - "With --since the printed gaps are the ones in the window (the gap check filters them), so a gap older than the window shows gaps=0 and does not fail the closing check; the run count is never windowed"
  - "A failure of either read of the soak (the check itself or the second read) is one line, gap check: could not run, exit 6, with no error text, and the writer variable's name is not printed either"
  - "The mapping-refusal test looks for the runner's own temporary folder by prefix, because capfd keeps its capture files in the same scratch folder"

requirements-completed: []

coverage:
  - id: D1
    description: "on a throwaway Postgres a dry run with a writer URL present and every connect made fatal leaves the four tables unchanged; the same inputs made live add exactly 1 run, 4 dispatch, 4 margin and the printed contingency rows, tagged pandapower with the installed version and a pp- id"
    requirement: OPS-03
    verification:
      - kind: integration
        ref: "backend/tests/pandapower_hourly_pg_test.py#test_tracer_dry_run_leaves_the_four_tables_unchanged_and_live_adds_one_tagged_set"
        status: pass
    human_judgment: false
  - id: D2
    description: "a live placeholder is refused with the tables unchanged; a duplicated outage is stored as one failed pandapower run with no result rows and its bus key, in both orientations, is printed nowhere"
    requirement: OPS-03
    verification:
      - kind: integration
        ref: "backend/tests/pandapower_hourly_pg_test.py#test_live_placeholder_refusal_leaves_the_tables_unchanged"
        status: pass
      - kind: integration
        ref: "backend/tests/pandapower_hourly_pg_test.py#test_live_mapping_refusal_is_stored_as_a_failed_pandapower_run_and_prints_no_bus_key"
        status: pass
    human_judgment: false
  - id: D3
    description: "soak calls the per-solver gap check with expected pandapower, prints counts only, reads again read-only, exits 0 whatever the gaps are and 6 with one fixed line when the check cannot run; --since is the strict closing check (0 or 5) and a value that is not a whole UTC hour is a usage error"
    requirement: OPS-05
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_hourly_test.py#test_soak_calls_run_by_solver_with_the_pandapower_expectation"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_hourly_test.py#test_soak_second_read_is_read_only"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_hourly_test.py#test_soak_exits_6_and_prints_no_error_text_when_the_check_cannot_run"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_hourly_test.py#test_soak_since_closing_check_exit_rule"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_hourly_test.py#test_soak_since_must_be_a_whole_hour"
        status: pass
    human_judgment: false
  - id: D4
    description: "24 consecutive pandapower slots before the database's current hour read as consecutive_slots=24 and pass on Postgres, removing one reads not yet, and the soak writes nothing"
    requirement: OPS-05
    verification:
      - kind: integration
        ref: "backend/tests/pandapower_hourly_pg_test.py#test_soak_reads_24_consecutive_slots_from_postgres"
        status: pass
    human_judgment: false
  - id: D5
    description: "the owner's size query is read-only text and returns its six rows on the throwaway cluster, matching the seeded counts"
    requirement: OPS-04
    verification:
      - kind: integration
        ref: "backend/tests/pandapower_hourly_pg_test.py#test_result_size_sql_runs_on_the_local_cluster"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_hourly_pg_test.py#test_result_size_sql_is_read_only_text"
        status: pass
    human_judgment: false

duration: about 1h 15min (estimated; the database tier alone runs about 90 s)
completed: 2026-11-26
---

# Phase 5 Plan 04: Database proofs of the runner and the soak command Summary

**A dry run is shown on a throwaway Postgres to leave the four result tables unchanged (with a live positive control that adds exactly one pandapower-tagged run set), and a new `soak` command reports per-solver gap counts and the trailing 24-slot count each hour without failing on gaps, with a strict `--since` closing check for the owner.**

## Performance

- **Tasks:** 3 of 3
- **Files:** 1 created, 2 modified
- **Database tier:** `pandapower_hourly_pg_test.py` 6 passed in 90.7 s (the tracer alone is about 109 s when run by itself, because it runs the real four-city study twice); the pure tier `pandapower_hourly_test.py` 85 passed in about 60 s (78 earlier plus 7 new); regression set (study job, solver tag, writer, per-solver gaps) 42 passed in 411 s. Nothing was skipped (`PSSE_REQUIRE_PG=1`).

## Accomplishments

- **Tracer (Task 1).** With a writer URL in the environment, `PANDAPOWER_LIVE` absent and `writer.connect` and `psycopg.connect` both replaced by functions that record a call and raise, a dry `run` on the real engine exits 0, prints `dry run: nothing was written to the database` and the per-table count and md5 fingerprint is identical; the replacements were never called. The same inputs with `PANDAPOWER_LIVE=true` print `run status: written`, the counts rise by exactly the numbers on the printed `rows:` line (1, 4, 4 and the contingency number), every table's fingerprint changes, the new run row has solver `pandapower`, solver version `3.5.6`, a `pp-` id and no PSS/E version, every `CHECKS_SQL` check is ok and the two seeded runs (one PSS/E, one pandapower) are byte-for-byte unchanged by their own fingerprint.
- **The soak command (Task 2).** `pandapower_hourly.py soak [--since YYYY-MM-DDTHH:00:00Z]`. `run_soak` calls `gaps.run_by_solver(..., expected=(engine.SOLVER,))` once with the report going to a text buffer, turns the report into counts-only lines (`gap_lines`), reads the runs again with `read_runs` (autocommit off, then read-only, before its first statement, closed in `finally`) and prints `soak: consecutive_slots=N of 24 fallback_slots=M` and `soak: pass` or `soak: not yet`. Without `--since` it exits 0 whatever the gaps are; with it, 0 only when `run_by_solver` returned 0 and the count is at least 24, else 5. A failed connect, a failed second read or a failed report prints only `gap check: could not run` and exits 6; the planted password and host in the test never appear.
- **Refusals as stored, soak on Postgres, size query (Task 3).** A live placeholder prints `placeholder: refused`, exits 2 and leaves the fingerprint unchanged with the fetch and connect stand-ins uncalled. A mapping listing one outage twice is stored as one failed pandapower run (stage `mapping`, no result rows, solver version NULL, `pp-` id) and the branch key, in both orientations, is absent from the printed lines, the captured descriptors and the log, while the stored error does hold it (so the test has teeth). 24 seeded pandapower slots before the database's current hour read as `consecutive_slots=24` and `pass`; skipping the slot 12 hours back reads `consecutive_slots=11` and `not yet`, the hourly exit is 0 both times, the closing check is 0 then 5, and the table fingerprint is unchanged by the soak. The size query is one `select` with none of the words of a data or rights change, and returns its six rows with counts equal to the seeded `[2, 8, 8, 4]`.

## Final vocabulary additions (`HOURLY_LINE_PATTERNS`, each ends `\Z`)

```
gap check: solver (psse|pandapower|unknown|other) runs=N gaps=N
gap check: solver (psse|pandapower|unknown|other) no runs recorded
gap check: could not run
soak: consecutive_slots=N of 24 fallback_slots=N
soak: (pass|not yet)
```

`24` is built from `soak.SOAK_SLOTS`. Exit codes of `soak`: 0, 2 (usage, including a `--since` that is not a whole UTC hour), 5 (`--since` check not met), 6 (the check could not run).

## Task Commits

1. **Task 1: Tracer, a dry run leaves the four tables unchanged and the same run made live adds one pandapower-tagged set** - `87817aa` (test)
2. **Task 2: The soak command and its seven unit tests** - `e266e84` (feat)
3. **Task 3: Refusals as stored, the soak on Postgres and the size query** - `aa70104` (test)

**Plan metadata:** the docs commit that follows this file.

## Files Created/Modified

- `backend/pandapower_job/hourly.py` - soak command, parser entry, vocabulary, dispatch
- `backend/tests/pandapower_hourly_test.py` - seven soak and `gap_lines` tests with a copied fake connection
- `backend/tests/pandapower_hourly_pg_test.py` - new database tier (6 tests, `_fingerprint`)

## Decisions Made

- With `--since`, the gaps shown by the gap check are the ones in the window, so `gaps=N` is windowed while `runs=N` is not. A gap older than the window therefore does not fail the owner's closing check; the 24-slot count already covers the last 24 hours.
- Both reads of the soak step, and the report parse, sit inside one guard: any failure is the same single fixed line and exit 6, so no error text, host or variable name can be printed.

## Deviations from Plan

### Auto-fixed Issues

None in `hourly.py`'s live or dry path: the database tier found no defect there, so the only changes to `hourly.py` are the planned soak additions.

Two test-side corrections while writing Task 2 and Task 3 (no plan rule triggered, noted for honesty):

- The first draft of the closing-check test expected `gaps=5` for a window that excludes the five older gaps; the gap check correctly reports the in-window count (`gaps=0`). The expectation was changed to match the documented window behaviour (recorded under Decisions Made).
- The mapping-refusal test first asserted the whole scratch folder empty; `capfd` keeps its capture files there, so the assertion now looks for the runner's own folder prefix.

## Known Stubs

None.

## Threat Flags

None. The soak step opens read-only connections and issues two `select` statements; it adds no endpoint, no write path and no new file access.

## Issues Encountered

None. `git` printed LF-to-CRLF warnings on the touched files; no test pins file bytes or asserts file modes. The pre-existing Windows-only failures named in the task brief were not touched and not run into by this plan's tests.

## Next Phase Readiness

- Plan 05-05 adds `bundle` and `scan-log` to `COMMAND_FLAGS`; the usage line already names them.
- The workflow plan can run `pandapower_hourly.py soak` after `run`; it exits 0 on gaps and 6 only when the check cannot run. The owner's closing command is `pandapower_hourly.py soak --since <first live hour>`: exit 0 means no pandapower gap since then and at least 24 consecutive slots.
- OPS-03 and OPS-05 stay Pending in REQUIREMENTS.md by the orchestrator's instruction until the owner steps and the live soak are done.

## Self-Check: PASSED

- FOUND: backend/pandapower_job/hourly.py (soak command, `expected=(engine.SOLVER,)` present once)
- FOUND: backend/tests/pandapower_hourly_pg_test.py (6 tests)
- FOUND: backend/tests/pandapower_hourly_test.py (7 soak and gap_lines tests, 85 in the file)
- FOUND commits: 87817aa, e266e84, aa70104
- Database tier 6 passed; pure tier 85 passed; regression set 42 passed; import gate and soak tests 11 passed; file-scope gate exit 0 after each commit; staged leak scan exit 0 before each commit; no change under backend/psse_job
