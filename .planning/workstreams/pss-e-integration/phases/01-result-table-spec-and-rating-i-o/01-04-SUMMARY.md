---
phase: 01-result-table-spec-and-rating-i-o
plan: 04
subsystem: database
tags: [postgres, psycopg, writer, run-record, atomic-write, idempotency, redaction, psse, pytest]

requires:
  - phase: 01-01
    provides: the reference DDL, the completeness checks and the local-Postgres harness (psse_local_pg.py)
  - phase: 01-02
    provides: psse_job constants, ratings (Selection, ratings_used), units and redaction
provides:
  - psse_job.contract, the Python mirror of the reference DDL (column tuples, INSERT-only SQL, RunContext, StudyResults, Failure, StudyFailed, ResultsInvalid) and the study contract for Phase 2
  - psse_job.run_record, which builds the one psse_run row of a run (ok, fallback or failed), the result-table parameter rows, and refuses malformed study results
  - psse_job.writer, which writes a run and all its rows in one transaction as dlr_psse_writer, rolls back and records a failed run on any error, and never updates or deletes
  - psse_fakes.fake_fetch, fake_results and FakeStudy for the later plans
affects: [01-05, pss-e-integration Phase 2, pss-e-integration Phase 3]

actuals:
  tokens: 20900
  tasks: 3
  commits: 3
plan_head_before: a21617180bcf1ae0b69a39140e888c522d019db6
plan_head_after: 344f8362d15fbd17739de508786687400572cb33

tech-stack:
  added: []
  patterns:
    - "One conn.transaction() holds the run row (insert ... on conflict (run_id) do nothing returning run_id) and then every result row; a failure rolls the whole attempt back, then a second transaction records a failed run"
    - "SQL is built only from fixed column tuples that a test equates with the reference DDL; every value is a bound parameter; no UPDATE or DELETE string exists in the job"
    - "Errors are redacted, cut to 1000 characters after redaction, and raised outside any except block so nothing is chained"

key-files:
  created:
    - backend/psse_job/contract.py
    - backend/psse_job/run_record.py
    - backend/psse_job/writer.py
    - backend/tests/psse_writer_test.py
    - backend/tests/psse_run_record_test.py
  modified:
    - backend/tests/psse_fakes.py

key-decisions:
  - "write_run raises WriteFailed after a rolled-back write and RecordFailed only when the failure record cannot be written either, so an unrecorded run can never look successful (T-01-24)"
  - "validate_results also rejects the city_rating link columns on a static city and a link that differs from the row that was read, so the plan 01-02 link-rule fact is enforced before the database sees the row"
  - "validate_results mirrors the DDL's dispatch identities and the contingency shape rules, so a bad study fails at validate_results rather than as a late write failure"
  - "result_rows rejects a study row that supplies run_id or run_outcome; both come only from the record"

patterns-established:
  - "Mutation check per plan: the failure-injection and run-record tests were each proven to bite by planting a defect (transaction removed, hour floor removed, identity guards removed) and watching a test fail"

requirements-completed: [WB-01, WB-02]

coverage:
  - id: D1
    description: "One write_run call, connected as dlr_psse_writer, writes the psse_run row and all result rows of a completed run in one transaction and every completeness check reports ok"
    requirement: "WB-02"
    verification:
      - kind: integration
        ref: "backend/tests/psse_writer_test.py#test_tracer_write_one_fallback_run_round_trip"
        status: pass
    human_judgment: false
  - id: D2
    description: "A failure on statement 1, 2, 6 or the last, or a real duplicate key, leaves zero result rows and a failed record with failed_stage write; an unreachable database raises RecordFailed with no row"
    requirement: "WB-02"
    verification:
      - kind: integration
        ref: "backend/tests/psse_writer_test.py -k atomic (5 tests)"
        status: pass
      - kind: integration
        ref: "backend/tests/psse_writer_test.py#test_failed_record_unreachable_database_raises_record_failed"
        status: pass
    human_judgment: false
  - id: D3
    description: "A retry with the same run_id never duplicates or overwrites a stored run, and a late failure record leaves a good run untouched"
    requirement: "WB-02"
    verification:
      - kind: integration
        ref: "backend/tests/psse_writer_test.py -k idempotent (2 tests)"
        status: pass
    human_judgment: false
  - id: D4
    description: "A failed run is recorded alone with start and end time, case identifier, per-city rating and source (all four cities), outcome and a non-empty redacted error"
    requirement: "WB-01"
    verification:
      - kind: integration
        ref: "backend/tests/psse_writer_test.py#test_failed_record_alone_has_no_results"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_run_record_test.py -k record (10 tests)"
        status: pass
    human_judgment: false
  - id: D5
    description: "No URL, password, user, project reference or host reaches a raised message, psse_run.error or psse_run.ratings_read_error; connect() chains no exception"
    requirement: "WB-01"
    verification:
      - kind: integration
        ref: "backend/tests/psse_writer_test.py -k redact (2 tests)"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_run_record_test.py -k redact (2 tests)"
        status: pass
    human_judgment: false
  - id: D6
    description: "A study that applies a rating other than the selected one, breaks a DDL identity or returns a malformed result is refused before any write; the Python column tuples cannot drift from the DDL; the job holds no UPDATE or DELETE SQL"
    requirement: "WB-02"
    verification:
      - kind: unit
        ref: "backend/tests/psse_run_record_test.py#test_validate_results_rejects (30 cases)"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_run_record_test.py#test_contract_columns_match_reference_ddl"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_run_record_test.py#test_contract_sql_never_updates_or_deletes"
        status: pass
    human_judgment: false

duration: 11min
completed: 2026-10-28
status: complete
---

# Phase 1 Plan 04: Run Record and All-or-Nothing Writer Summary

**A run is written as one transaction of one psse_run row plus 4 + 4 + N result rows by the INSERT-only `dlr_psse_writer` role; any failure rolls back, records the run as `failed` (stage `write`), and a retry of the same run_id can never duplicate or overwrite.**

## Performance

- **Duration:** about 11 min
- **Started:** 2026-10-28T10:53Z
- **Completed:** 2026-10-28T11:05Z
- **Tasks:** 3 (one tracer, two auto/tdd)
- **Files modified:** 6 (5 created, 1 extended)

## Accomplishments

- `contract.py` holds the table names, the four client column tuples in DDL order, and `INSERT_RUN_SQL` / `INSERT_RESULT_SQL`, built only from those tuples; `test_contract_columns_match_reference_ddl` parses the DDL and fails if a tuple drifts. The Phase 2 study contract (`study(selection, context)` returning `StudyResults` or raising `StudyFailed`) lives here.
- `run_record.build_run_record` returns exactly the 17 `psse_run` client columns for ok, fallback and failed runs. A failed ratings read stays `fallback` (D-02). `ratings_used` always holds the four cities, in `CITIES` order and `RATINGS_USED_KEYS` order, with each city's kV and MVA merged in from the study.
- `writer.write_run` is the only write path: run row first, then dispatch, margin, contingency rows, one `conn.transaction()`; `already_recorded` when the run_id exists; on any error the failure is recorded in a new transaction and `WriteFailed` is raised, or `RecordFailed` when that also fails. Proven against local Postgres 18.6 with failure injected on statements 1, 2, 6 and last, and with a real `UniqueViolation`.
- `validate_results` refuses a study that does not apply exactly the selected rating (a static city can never become a DLR one), breaks any dispatch identity, returns a malformed margin or contingency row, or is over 5000 contingency rows.

## Task Commits

1. **Task 1 (tracer): build a fallback run record and write it with its results** - `c1be4aa` (feat)
2. **Task 2: rollback, failed record, idempotency and redaction on local Postgres** - `188f933` (feat)
3. **Task 3: run-record rules, study-result validation and the DDL column contract** - `344f836` (feat)

The tracer gate: auto-mode was not active and the tracer's `<verify>` is automated only, so `<verify>` was re-run (1 passed) before expansion.

## Decisions Made

- `RecordFailed` is the single signal for "no record exists", distinct from `WriteFailed` (rolled back and recorded). Plan 01-05 maps `RecordFailed` to a non-zero exit.
- If a commit succeeds but its acknowledgement is lost, `write_run` raises `WriteFailed` and the failure record insert returns `already_recorded` (nothing changes); the rows are present and a retry with the same run_id returns `already_recorded`. This is the documented trade-off of an INSERT-only design.
- The failure path of `write_run` and the whole of `record_failure` were written with the tracer (they share one module and one SQL constant); Task 2 then proved them.

## Deviations from Plan

### Auto-fixed Issues

None needed fixing. The following are additions inside the plan's intent, recorded for the verifier:

**1. [Rule 2 - Missing critical functionality] validate_results also enforces the city_rating link and the remaining DDL identities**
- **Found during:** Task 3
- **Issue:** The plan's list names the source, amps, subconductor, MVA and limiting-factor checks. Carry-over fact (a) from plan 01-02 says the link columns must be NULL unless the rating source is city_rating, and the DDL also pins dispatched_amps_circuit, dispatched_amps_per_conductor, dispatched_mw, the contingency shape and the exceeded_by arithmetic. Without them a bad study would fail late as a 'write' failure instead of as a `validate_results` failure.
- **Fix:** `_check_dispatch` also compares the link to the row that was read (static: both None) and the three remaining identities; `_check_contingency` mirrors the kind/shape/value rules.
- **Files modified:** `backend/psse_job/run_record.py`, `backend/tests/psse_run_record_test.py`
- **Verification:** `test_validate_results_rejects` (30 cases) and `test_validate_results_accepts_zero_violations`
- **Commit:** `344f836`

**2. [Rule 2 - Missing critical functionality] result_rows rejects study-supplied run_id and run_outcome; build_run_record maps an unknown stage to internal**
- **Found during:** Task 1
- **Issue:** A study row that carried its own run_id or run_outcome could write rows under another run, and an unknown failure stage would violate `psse_run_failed_stage_ck` and turn a recordable failure into an unrecorded one.
- **Fix:** `result_rows` raises `ValueError` for either key; `build_run_record` and `as_failed` apply the same 'internal' mapping as `failure_from_exception`.
- **Files modified:** `backend/psse_job/run_record.py`
- **Verification:** `test_result_rows_columns_and_values`, `test_record_unknown_stage_maps_to_internal`
- **Commit:** `c1be4aa`

**Total deviations:** 2 additions (both Rule 2, hardening inside the plan's scope). **Impact:** none on the plan's interfaces; Phase 2's study must pass `city_rating_valid_time` and `city_rating_computed_at` equal to the selection's row for a city_rating choice and None otherwise (see the notes below).

## Notes for the next plans

- **01-05 (job entry point):** call order is `select_ratings` -> study (inside try) -> `validate_results` -> `build_run_record` -> `result_rows` -> `write_run`. Map a study or validation exception through `failure_from_exception(stage, exc)` (stage `validate_results` for `ResultsInvalid`) and `build_run_record(..., failure=...)` then `record_failure`. `RecordFailed` means no row exists: exit non-zero. `WriteFailed` means a failed record exists: also non-zero. Stamp `run_id = new_run_id(started_at)` once and reuse it on a retry; `job_version()` never raises and `case_label()` keeps `case_id` a label.
- **Phase 2 study contract:** dispatch rows must carry `city_rating_valid_time` / `city_rating_computed_at` equal to the choice's `row_valid_time` / `row_computed_at` for a city_rating choice, and None for a static choice (even a stale or provisional one, which still carries the row link in memory). `psse_fakes.fake_results` shows the exact row shapes.
- **Test-harness facts:** the PG tests take about 25 seconds for `psse_writer_test.py` (cluster start dominates); `test_redact_connect_failure_carries_no_url_or_identity` needs psycopg but no database and takes about 10 seconds (the refused connection retries on Windows).
- **Python 3.7 proof is still syntactic** (`psse_contract_test.py`); the new modules use `subprocess`, `hashlib`, `uuid`, `json` from the allow-list, and `psycopg` only inside `writer.connect`.

## Authentication Gates

None. The only database is a private local cluster that trusts loopback connections; no Supabase project or credential was touched.

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model; T-01-20 to T-01-26 each have a named test (redact_*, atomic_*, idempotent_*, failed_record_unreachable_*, validate_results_rejects, test_contract_*).

## Verification Results

Environment: Windows 11 Git Bash, Python 3.12 venv (`.venv/Scripts/python.exe`), pytest 9.0.3, psycopg 3.3.6, local Postgres 18.6 portable binaries on PATH for the commands only. Postgres started by the fixtures (private cluster under pytest's temp dir) and stopped by them; `tasklist` shows no postgres process afterwards.

- `PSSE_REQUIRE_PG=1 DLR_TEST_PG_AUTOSTART=1 .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider -rs backend/tests/psse_writer_test.py -k tracer` - 1 passed (RED first: collection failed on the missing run_record module)
- `... backend/tests/psse_writer_test.py` - 13 passed, 0 skipped
- `... backend/tests/psse_writer_test.py -k "atomic or idempotent or failed"` - 10 passed
- `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider backend/tests/psse_writer_test.py -k redact_connect` (no PSSE_REQUIRE_PG) - 1 passed
- `PSSE_REQUIRE_PG=1 DLR_TEST_PG_AUTOSTART=1 ... backend/tests/psse_writer_test.py backend/tests/psse_schema_pg_test.py` - 58 passed, 0 skipped
- `... backend/tests/psse_run_record_test.py` - 49 passed; `-k "redact or contract"` - 4 passed
- `... backend/tests/psse_contract_test.py backend/tests/psse_ratings_test.py backend/tests/secret_scan_test.py` - 96 passed
- `... psse_schema_doc_test.py supabase_schema_doc_test.py psse_contract_test.py secret_scan_test.py psse_run_record_test.py` - 89 passed
- `python -c "... print(run_record.MAX_CONTINGENCY_ROWS)"` prints 5000; `grep -c "on conflict (run_id) do nothing returning run_id" contract.py` prints 1; `grep -c "conn.transaction()" writer.py` prints 2; `grep -c "class RecordFailed" writer.py` prints 1
- `git diff --quiet -- docs/data-science/schema/psse_results_v1.sql` exits 0; `git status --porcelain -- backend/config.py supabase/migrations .planning/workstreams/production-pipeline` prints nothing
- Mutation checks: removing the transaction from `write_run` fails 4 atomic tests; eleven plants in run_record.py and contract.py (hour floor, finished-before-started, source check, empty-error label, power-factor guard, row cap, outcome rule, redaction cut, applied_mva identity, column order, `do update`) were all caught after two test cases were tightened (the power-factor guard and the applied_mva identity had survived at first); all files restored byte-for-byte.

## Self-Check: PASSED

- FOUND: backend/psse_job/contract.py, run_record.py, writer.py; backend/tests/psse_fakes.py, psse_writer_test.py, psse_run_record_test.py
- FOUND commits c1be4aa, 188f933, 344f836 (ancestors of HEAD); `git rev-list --count a216171..HEAD` was 3 before this SUMMARY commit
