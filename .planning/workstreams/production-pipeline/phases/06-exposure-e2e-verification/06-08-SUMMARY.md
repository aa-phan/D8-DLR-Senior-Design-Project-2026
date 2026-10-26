---
phase: 06-exposure-e2e-verification
plan: 08
subsystem: testing
tags: [e2e-trace, cron-job-org, github-actions, gh-cli, postgrest, psycopg, read-only, redaction, stdlib]

requires:
  - phase: 06-exposure-e2e-verification
    provides: "supabase_rest (config_from_env, get_all, parse_ts, redact_rest), fake_postgrest.FakePostgrest and make_rating_rows (06-04); latest_rating_contract.STORED_COLUMNS and is_provisional (06-01)"
  - phase: 05-hourly-live-run
    provides: "dlr_live.yml / workflow name 'DLR Live Ratings', dlr_live_window_check.fetch_runs, the hourly cron-job.org dispatch at minute 05"
  - phase: 04-supabase-store
    provides: "supabase_store.connect(), StoreError, redact; city_rating run_id = GITHUB_RUN_ID; pipeline_run.cities_ok"
provides:
  - "backend/e2e_trace.py: one read-only command that ties a cron-job.org execution to one Actions run, its city_rating rows (SQL) and the REST response, as a four-way table and JSON evidence"
  - "backend/tests/e2e_trace_test.py: 18 test functions (25 cases), all offline (fake gh, recording fake connection, FakePostgrest)"
affects: [06-11, 06-12, 06-13]

# Actuals (#2632): same estimateTokens scale (chars/4 over the realized diff)
actuals:
  tokens: 15900
  tasks: 2
  commits: 2
plan_head_before: 832e7504d648dfe119b4efaf16e36e85c55af48f
plan_head_after: 555246fb1e8cdccc4a0afbc4e2a5dd258285320d

tech-stack:
  added: []
  patterns:
    - "Walk a chain link by link, record each as {name, ok, detail}, and always render every city in config.LOCATIONS order, so a failure names the link and a partial chain still gives evidence"
    - "Read-only DB session (set default_transaction_read_only = on before the first statement), bound parameters only, failures re-raised as StoreError with the exception type plus redacted text and no chaining"
    - "Compare an independent SQL read against the REST read per city on the 31 stored columns; a city absent from both sides is a mismatch, so empty never matches empty"
    - "Superseded-row detection: only when fewer than four rows come back, one bound SELECT of city and run_id at the run's slot names the run that overwrote them (OD-7)"

key-files:
  created:
    - backend/e2e_trace.py
    - backend/tests/e2e_trace_test.py
  modified: []

key-decisions:
  - "Correlation uses exactly one workflow_dispatch run created from execution - 60 s to execution + 300 s (both ends inclusive; 301 s is out); zero or several candidates fail loudly, and an explicit --run-id must agree with the correlated run (nothing is traced for either when it does not)"
  - "--execution-time must carry an explicit UTC offset (Z or +00:00); a bare time is a usage error (exit 2) so an owner's local time is never silently read as UTC"
  - "latest_rating is read only for the current-or-superseded column and the is_provisional word-rule check; the compared rows come from city_rating?run_id=eq.<id>, so a run landing during the trace cannot cause a false mismatch"
  - "A later slot replacing the run's row in latest_rating is informational ('superseded by a later slot', still a match); the same slot overwritten by another run is a failure ('superseded by run <id>') and never a match"
  - "main() takes injectable fetch_runs_fn, run_cmd, connect_fn and opener so every dependency is faked offline; the owner runs it with the defaults (06-11)"

patterns-established:
  - "Test fixtures build each secret-shaped string from pieces so secret_scan_test.py never matches the test file"
  - "A recording fake connection answers the three SELECTs from a table filtered on the BOUND parameters, so a test sees both the statements and what a real database would return"

requirements-completed: [E2E-01]

coverage:
  - id: D1
    description: "Happy-path trace: one execution maps to one successful dispatch run, whose four city_rating rows (SQL) equal the REST rows for all 31 stored columns, listed in config.LOCATIONS order, exit 0, with a markdown table and JSON evidence"
    requirement: E2E-01
    verification:
      - kind: integration
        ref: "backend/tests/e2e_trace_test.py#test_full_chain_matches"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_trace_test.py#test_row_order_does_not_matter"
        status: pass
    human_judgment: false
  - id: D2
    description: "Comparison rules: Z and +00:00 are the same instant, floats compared exactly (1e-9 is a mismatch naming city and column), arrays element by element, null only with null, booleans never equal numbers"
    requirement: E2E-01
    verification:
      - kind: unit
        ref: "backend/tests/e2e_trace_test.py#test_timestamp_forms_and_exact_floats"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_trace_test.py#test_arrays_and_nulls_are_compared_exactly"
        status: pass
    human_judgment: false
  - id: D3
    description: "is_provisional agrees with the word rule on rating_basis and config_version; the current-or-superseded column separates 'current', 'superseded by a later slot' (informational) from overwritten rows"
    requirement: E2E-01
    verification:
      - kind: unit
        ref: "backend/tests/e2e_trace_test.py#test_is_provisional_is_checked_against_the_labels"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_trace_test.py#test_current_or_superseded_column"
        status: pass
      - kind: integration
        ref: "backend/tests/e2e_trace_test.py#test_a_run_landing_during_the_trace_is_not_a_mismatch"
        status: pass
    human_judgment: false
  - id: D4
    description: "Every failing link is named: candidate window edges (-60 s and +300 s in, 301 s out, zero or two candidates), conclusion, event and workflow name, superseded rows naming the newer run, empty or one-sided rows, incomplete pipeline_run, non-2xx execution status, disagreeing --run-id, usage and configuration errors as exit 2"
    requirement: E2E-01
    verification:
      - kind: unit
        ref: "backend/tests/e2e_trace_test.py#test_candidate_window_edges"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_trace_test.py#test_run_must_be_a_successful_dispatch_of_the_live_workflow"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_trace_test.py#test_superseded_rows_fail_with_the_newer_run_named"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_trace_test.py#test_empty_or_one_sided_rows_fail"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_trace_test.py#test_incomplete_pipeline_run_or_bad_status_fails"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_trace_test.py#test_explicit_run_id_must_agree"
        status: pass
    human_judgment: false
  - id: D5
    description: "Read-only and leak-free: the first statement is the read-only setting, run_id is a bound parameter, REST is GET only, no database URL, project URL, host or key reaches any output, file or exception text, and re-runs give byte-identical evidence"
    requirement: E2E-01
    verification:
      - kind: unit
        ref: "backend/tests/e2e_trace_test.py#test_sql_read_is_read_only_and_bound"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_trace_test.py#test_failures_never_leak_url_or_key"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_trace_test.py#test_evidence_is_deterministic_and_clean"
        status: pass
    human_judgment: false
  - id: D6
    description: "The live trace against the real cron-job.org history, GitHub and Supabase (owner runs it in 06-11)"
    requirement: E2E-01
    verification: []
    human_judgment: true
    rationale: "Per D-06 this plan is offline build work. The cron-job.org execution time and HTTP status come from the owner's console, and the live database, REST service and gh authentication are only exercised in 06-11."

# Metrics
duration: 10min
completed: 2026-10-26
status: complete
---

# Phase 6 Plan 08: E2E Trace Summary

**One read-only command, `backend/e2e_trace.py`, traces a cron-job.org execution to its single GitHub dispatch run, to the four `city_rating` rows read over SQL, to the same rows read over REST with the publishable key, and fails with a named link for every way the chain can break.**

In plain English: one scheduled trigger produced one run, the run wrote one row per city, and the public interface returns exactly those values. Nothing was run against the live project (D-06); the owner runs it in 06-11.

## Performance

- **Duration:** about 10 min
- **Started:** 2026-10-26T22:09:04Z
- **Completed:** 2026-10-26T22:19:00Z
- **Tasks:** 2
- **Files modified:** 2 (both new)

## The command as built

```
python backend/e2e_trace.py --execution-time 2026-10-19T14:05:02Z --execution-status 204 \
    [--run-id 123456789] [--out trace.md] [--json-out trace.json]
```

It runs from the owner's main checkout and needs `SUPABASE_DB_URL` (Phase 4's `connect()`), `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY`, and an authenticated `gh`; `.env` is loaded only under `if __name__ == "__main__"`.

| Flag | Meaning |
|---|---|
| `--execution-time` (required) | The execution's actual UTC time from the cron-job.org history. Needs `Z` or an explicit offset; a bare time is exit 2 |
| `--execution-status` (required) | The execution's HTTP status from the history; anything outside 2xx fails the first link |
| `--run-id` (optional, digits only) | Must agree with the correlated run; a disagreement fails and nothing is traced for either id |
| `--out FILE.md` | Table, link results and verdict line |
| `--json-out FILE` | The evidence: run id, times and values for the 31 stored columns, both sides, per city |

Exit codes: `0` traced and every link matched, `1` a link failed (each printed as `PASS` or `FAIL <link>: <reason>`), `2` usage or configuration.

Links, in order: `cron-job.org execution`, `Actions run` (exactly one `workflow_dispatch` created in `[execution - 60 s, execution + 300 s]`), `Actions run result` (`gh run view`: databaseId, event, conclusion `success`, workflowName `DLR Live Ratings`), `SQL rows` (one per city, or `<city> superseded by run <id>`), `pipeline_run` (`cities_ok` lists all four), `REST rows` (`city_rating?run_id=eq.<id>`), `SQL equals REST`, `is_provisional`.

The four-way table has one row per city in `config.LOCATIONS` order with the columns cron-job.org execution, Actions run, SQL row, REST row, match, current or superseded.

Public functions: `find_run`, `view_run`, `sql_rows`, `rest_rows`, `compare_rows`, `Mismatch`, `trace`, `render_table`, `main`; constants `WORKFLOW_FILE`, `WORKFLOW_NAME`, `WINDOW_BEFORE_S = 60`, `WINDOW_AFTER_S = 300`, `GH_VIEW_FIELDS`.

## Accomplishments

- Tracer: execution to run to SQL rows to REST rows to a four-way table, exit 0 only when all four cities match on all 31 stored columns, with the provisional flag checked against its word rule (D-03)
- Exact comparison: `...Z` and `...+00:00` are the same instant, a 1e-9 float difference is a mismatch that names the city and the column, arrays compare element by element, null equals only null, a boolean never equals a number
- Ambiguity never passes: zero or two candidate runs, a candidate at 301 s, a run whose rows a later run overwrote in the same hourly slot (named `superseded by run <id>` through one bound slot lookup), empty or one-sided rows, and empty against empty all fail with a named reason
- Read-only and leak-free (T-06-27, T-06-28, T-06-29): `set default_transaction_read_only = on` is the first statement, `run_id` is bound, REST is GET only, every printed line and file passes through `redact_rest` and `redact`, and re-runs give byte-identical evidence

## Task Commits

1. **Task 1: tracer, execution to REST four-way table** - `cc97c9b` (feat)
2. **Task 2: every failing link named** - `555246f` (test)

**Plan metadata:** recorded in the docs commit that follows this summary.

## Files Created/Modified

- `backend/e2e_trace.py` - the E2E-01 trace command
- `backend/tests/e2e_trace_test.py` - 18 test functions, 25 cases, all offline

## Decisions Made

See `key-decisions` above. The two that matter most to the owner: correlation is by time only and refuses to guess (exactly one candidate, else fail), and a time without an offset is rejected rather than assumed to be UTC.

## TDD record

Task 1: the test file was written first and failed at import (`ModuleNotFoundError: e2e_trace`), then the module made all 6 pass. Task 2: the new tests were written first; 5 of the 11 new cases failed (view checks, superseded lookup, one-sided rows, pipeline_run and status checks, explicit run id) before the implementation made all pass. The read-only, redaction and determinism tests passed immediately because Task 1 already built those behaviours in; a mutation run confirmed they bite (dropping the read-only statement, widening either window edge by one second and loosening float equality each fail a test). Each task is one commit with both files, as the plan specifies, not separate RED and GREEN commits.

## Deviations from Plan

None - plan executed exactly as written, apart from the points under Discrepancies.

## Discrepancies

- `main` takes keyword arguments (`fetch_runs_fn`, `run_cmd`, `connect_fn`, `opener`) beyond the `main(argv=None)` in the plan's wording, so the fakes can be injected; the CLI defaults are the plan's. A `trace()` function carries the chain walk and returns the evidence dict; `main` only parses, prints and writes.
- The plan listed the `latest_rating` select as `city, valid_time, run_id, is_provisional`; the build also selects `rating_basis` and `config_version` so the word rule can be checked against the labels of whichever row the view is showing, including a later slot.
- `--execution-time` and `--execution-status` are required, and a time without a UTC offset is exit 2. The plan only said the status "must be 2xx".
- Commit messages end with `Co-Authored-By: Claude Sonnet 5.5` and the session line from the harness attribution, not the plan's "Claude Opus 5.5" line.

## Issues Encountered

- A test of my own had an id mix-up (the in-window candidate was given a different id from the fixture rows); fixed in the test before any commit.
- `gh run list` returns at most 400 runs (about 16 days of hourly runs). An execution older than that finds zero candidates and fails with the window named; `dlr_live_window_check.fetch_runs` prints its own warning in that case. 06-11 traces a fresh execution, so this does not bite.

## User Setup Required

None - no external service configuration required. The live run (06-11) needs the owner's `.env` values and `gh` authentication, which already exist.

## Known Stubs

None.

## Threat Flags

None - the only surfaces are the ones in the plan's threat model (owner connection read-only, REST GET with the publishable key, evidence redacted).

## Next Phase Readiness

06-11 can run the trace live: read the execution time and status from the cron-job.org job history, then run the command right after an hourly run (a later run replaces `latest_rating`, which the trace tolerates, but the owner should still note whether the column says `current`). `E2E-01` stays open in REQUIREMENTS.md until the plans that still declare it have summaries.

## Self-Check: PASSED

- `backend/e2e_trace.py` and `backend/tests/e2e_trace_test.py` exist
- Commits `cc97c9b` and `555246f` are on `main`
- `grep` acceptance criteria hold (one `def compare_rows(`, `WINDOW_AFTER_S = 300`, `latest_rating_contract.STORED_COLUMNS` used, `load_dotenv()` only under `__main__`, `default_transaction_read_only` present, 18 test functions)
- `backend/tests/e2e_trace_test.py`: 25 passed; full suite: 1931 passed, 81 skipped, 0 failed
- Nothing contacted cron-job.org, GitHub Actions or the live Supabase project; nothing pushed

---
*Phase: 06-exposure-e2e-verification*
*Completed: 2026-10-26*
