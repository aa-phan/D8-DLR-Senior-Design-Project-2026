---
phase: 04-supabase-store-writer
plan: 02
subsystem: database
tags: [postgres, supabase, orchestrator, pipeline-run, forecast-status, history-validation, upsert]

requires:
  - phase: 04-supabase-store-writer
    provides: "04-01: SupabaseStore (read_history, write_rating), build_rating_row with the DB-06 identity columns, the migration with public.pipeline_run"
  - phase: 02-data-cleaning
    provides: "clean_history applied to the Postgres frame; historical_archive row validation reused"
provides:
  - "run_city_pipeline(..., history_reader=None) seam and pipeline['forecast_status'] ('ok' | 'cold_start' | 'failed', OD-3)"
  - "run_dlr_pipeline(..., store=None, record_run=True): reads history from, writes one rating row per rated city to, and records one pipeline_run row for the run in a store"
  - "dlr_orchestrator CLI --store {csv,postgres} and --no-run-row"
  - "supabase_store.PIPELINE_RUN_COLUMNS, PIPELINE_RUN_JSONB, build_run_row, upsert_run, SupabaseStore.record_run"
  - "historical_archive.validate_history_frame(df, source), shared by the CSV reader and the Postgres store"
affects: [04-03 backfill loader and smoke test, 04-04 consumer doc, 04-05 owner migration push, 05 scheduled runner (05-01, 05-02, 05-03), 06 read view]

actuals:
  tokens: 20000
  tasks: 3
  commits: 3
plan_head_before: e166695843c1d290eba743434ab7c9e23efb013c
plan_head_after: bde0499066ec0db9d513cb72af699192e8f9ce44

tech-stack:
  added: []
  patterns:
    - "Orchestrator store seam: None keeps the CSV path byte-for-byte; 'postgres' or any object with read_history, write_rating and record_run selects the store; anything else is a ValueError before any city runs"
    - "OD-9: a city that raises, or whose write raises, gets no rating row; the pipeline_run row is its only record (outcome 'error')"
    - "pipeline_run identifiers come only from the PIPELINE_RUN_COLUMNS allow-list; values are bound parameters; jsonb values are JSON text cast in the statement"
    - "Per-city provider-error deltas (Counter differences, keys redacted) and per-city source counts from the city's slice of fetcher.provenance"

key-files:
  created:
    - backend/tests/supabase_orchestrator_test.py
    - backend/tests/supabase_run_log_test.py
  modified:
    - backend/city_pipeline.py
    - backend/dlr_orchestrator.py
    - backend/supabase_store.py
    - backend/historical_archive.py
    - backend/tests/city_pipeline_test.py
    - backend/tests/supabase_store_test.py

key-decisions:
  - "forecast_status describes the forecast call (ok / cold_start / failed), not whether G6 used it; a forecast withheld by the gap guard or a zero-width band is still 'ok' with forecast_used_by_g6 False"
  - "With a store, run_city_pipeline is always called with archive=False and history_reader=store.read_history; the rating row is written by the orchestrator after the pipeline returns, and result['archived'] is whether that row was written"
  - "cities_ok means written AND forecast_status in (ok, cold_start) AND anomaly model loaded; written otherwise is 'degraded'; not written is 'error'"
  - "pipeline_run.provider_errors and sources are dicts keyed by city, with an entry (possibly empty) for every city the run reached; None when the provider has no composed fetcher"
  - "A run-log (pipeline_run) write failure never stops a city: it is logged redacted, stored in out['run_log_error'], and main returns 1"
  - "'csv' is not an accepted value of run_dlr_pipeline(store=...); the CLI maps --store csv to no store argument at all"

patterns-established:
  - "Phase 5 children: STORE_ARGS = ('--store', 'postgres', '--no-run-row'); WRITE_FLAG_KEY = 'archived'; read pipeline['forecast_status']"
  - "upsert_run(conn, row) accepts any subset of PIPELINE_RUN_COLUMNS that includes run_id and updates every given non-key column on conflict"

requirements-completed: [DB-02, DB-06]

coverage:
  - id: D1
    description: "run_city_pipeline accepts a history reader (called with city and run end) in place of the CSV archive; the CSV path is unchanged without one"
    requirement: DB-02
    verification:
      - kind: unit
        ref: "backend/tests/city_pipeline_test.py#test_history_reader_replaces_the_archive_read"
        status: pass
      - kind: unit
        ref: "backend/tests/city_pipeline_test.py#test_without_a_history_reader_the_csv_archive_is_read"
        status: pass
    human_judgment: false
  - id: D2
    description: "OD-3 forecast_status per run: ok, cold_start, failed; a forecast withheld from G6 still reports ok"
    requirement: DB-02
    verification:
      - kind: unit
        ref: "backend/tests/city_pipeline_test.py#test_forecast_status_reports_ok_cold_start_and_failed"
        status: pass
      - kind: unit
        ref: "backend/tests/city_pipeline_test.py#test_a_forecast_withheld_by_the_gap_guard_is_still_status_ok"
        status: pass
    human_judgment: false
  - id: D3
    description: "The orchestrator reads history through the store, writes one rating row per rated city with the rated station's provenance, writes no CSV anywhere, and reports archived as the row-written flag"
    requirement: DB-02
    verification:
      - kind: unit
        ref: "backend/tests/supabase_orchestrator_test.py#test_store_path_reads_and_writes_through_the_store_and_writes_no_csv"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_orchestrator_test.py#test_provenance_of_the_rated_station_reaches_the_writer"
        status: pass
    human_judgment: false
  - id: D4
    description: "OD-9: a failing city or failed write gets no rating row and is recorded in pipeline_run.cities_failed as outcome error with redacted text; the other cities still write"
    requirement: DB-02
    verification:
      - kind: unit
        ref: "backend/tests/supabase_orchestrator_test.py#test_a_failing_city_writes_no_rating_row_and_is_recorded_in_the_run_row"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_orchestrator_test.py#test_a_store_write_failure_is_a_city_error_and_the_others_still_write"
        status: pass
    human_judgment: false
  - id: D5
    description: "One pipeline_run upsert per run keyed by run_id, in the shape Phase 5's runner writes; ok / degraded / error classification, per-city provider errors and sources; --no-run-row skips it; a run-row failure is logged redacted and makes main return 1"
    requirement: DB-02
    verification:
      - kind: unit
        ref: "backend/tests/supabase_orchestrator_test.py#test_run_row_classifies_ok_degraded_and_error_with_per_city_provider_counts"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_run_log_test.py#test_upsert_run_rejects_unknown_columns_and_a_missing_run_id"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_orchestrator_test.py#test_run_log_failure_is_logged_redacted_and_main_returns_one"
        status: pass
    human_judgment: false
  - id: D6
    description: "CLI --store postgres / --no-run-row; without --store (or --store csv) main passes exactly the eight keyword arguments Phase 1 pins; --store postgres --no-archive reads and writes nothing"
    requirement: DB-02
    verification:
      - kind: unit
        ref: "backend/tests/supabase_orchestrator_test.py#test_main_store_flags_extend_the_pinned_arguments_only_for_postgres"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_orchestrator_test.py#test_no_archive_with_a_store_writes_nothing"
        status: pass
    human_judgment: false
  - id: D7
    description: "SC2 on a local Postgres: running one window twice leaves one city_rating row per city and one pipeline_run row for the run id (the second attempt replaces it); AUSTIN's history_rows equals the rows Postgres held before the slot"
    requirement: DB-02
    verification:
      - kind: integration
        ref: "backend/tests/supabase_orchestrator_test.py#test_orchestrator_rerun_against_postgres_keeps_one_row_per_city_and_one_run_row"
        status: pass
      - kind: integration
        ref: "backend/tests/supabase_orchestrator_test.py#test_orchestrator_reads_its_history_from_postgres"
        status: pass
    human_judgment: false
  - id: D8
    description: "DB-06 through the production seam: each row written by the orchestrator carries its own city's config_fingerprint (the two cities differ), forecast_model_sha256 NULL for naive, and anomaly_model_sha256 equal to the sha256 of the detector model file the run loaded"
    requirement: DB-06
    verification:
      - kind: integration
        ref: "backend/tests/supabase_orchestrator_test.py#test_orchestrator_rerun_against_postgres_keeps_one_row_per_city_and_one_run_row"
        status: pass
    human_judgment: false
  - id: D9
    description: "Postgres history passes the CSV archive's row validation (one WARNING per call), an empty or fully-rejected history logs one cold-start WARNING naming the city, and the 30-day window boundary is pinned (slot-30d read, one hour older and the slot itself not)"
    requirement: DB-02
    verification:
      - kind: unit
        ref: "backend/tests/supabase_store_test.py#test_db_history_is_validated_like_the_csv_archive"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_store_test.py#test_empty_db_history_logs_one_cold_start_warning_naming_the_city"
        status: pass
      - kind: integration
        ref: "backend/tests/supabase_orchestrator_test.py#test_history_window_boundary_against_postgres"
        status: pass
    human_judgment: false

duration: ~10min
completed: 2026-10-21
status: complete
---

# Phase 4 Plan 02: Orchestrator store seam, run row and validated Postgres history Summary

**`dlr_orchestrator --store postgres` reads each city's history from Postgres, upserts one idempotent rating row per rated city, records every city (ok, degraded, error) in one `pipeline_run` row, and reports the OD-3 forecast status; the CSV path is unchanged**

## Performance

- **Duration:** about 10 min of executor wall clock (22:59Z to 23:09Z)
- **Started:** 2026-10-21T22:59:29Z
- **Completed:** 2026-10-21T23:09Z
- **Tasks:** 3
- **Files modified:** 8 (2 created, 6 modified)

## Accomplishments

- `run_city_pipeline` takes `history_reader=fn` (called with the city and the run end, replacing the CSV read; `None` keeps the archive) and reports `pipeline["forecast_status"]`: `ok` when `forecast_ampacity` returned a forecast, `cold_start` when it returned None, `failed` when it raised.
- `run_dlr_pipeline(store=..., record_run=...)` runs each city with `archive=False` and `history_reader=store.read_history`, writes one row per rated city through `store.write_rating` with the last composer record for the rated station since that city started, and sets `result["archived"]` (summarize's `archived`) to whether that row was written. A city that raises, or whose write raises `StoreError`, gets no row (OD-9) and is recorded in `pipeline_run.cities_failed` with outcome `error`, `written` false and redacted text.
- The run ends with one `pipeline_run` upsert keyed by `run_id`: `cities_ok` in `config.LOCATIONS` order, `cities_failed` objects (`outcome` error or degraded, `written`, `forecast_status`, `detector_model_loaded`, redacted `error`), `provider_errors` and `sources` keyed by city. `--no-run-row` skips it; a failure to write it is logged redacted, never stops a city, and makes `main` return 1.
- `supabase_store.build_run_row` (pure) and `upsert_run` (identifiers from an allow-list, bound values, `on conflict (run_id) do update`, redacted `StoreError`) and `SupabaseStore.record_run`.
- Postgres history now goes through `historical_archive.validate_history_frame` (the CSV reader's row check, factored out unchanged) and logs one cold-start WARNING naming the city when nothing usable is left, so a writer that RLS hides from its rows is visible.
- Proven on a throwaway Postgres 16: two runs of AUSTIN and EL_PASO for one window leave one `city_rating` row per city at the slot and one `pipeline_run` row (the second attempt replaced the first, `run_attempt` 2); AUSTIN's `history_rows` was the 3 rows Postgres held; each row's `config_fingerprint` equals `rating_config_fingerprint(city)` and the two differ; `anomaly_model_sha256` equals `file_sha256` of the detector model file the run loaded.

## Task Commits

Each task was committed atomically (one `feat` commit per task, as the plan specifies; the failing-test state was observed before each implementation but not committed separately):

1. **Task 1: city_pipeline history reader and forecast status (OD-3)** - `e364a92` (feat)
2. **Task 2: orchestrator store seam, run row and CLI** - `d78b8ad` (feat)
3. **Task 3: validated Postgres history, cold-start warning, 30-day boundary** - `bde0499` (feat)

**Plan metadata:** the `docs(04-02)` commit that adds this SUMMARY and the STATE/ROADMAP/REQUIREMENTS updates.

## Files Created/Modified

- `backend/city_pipeline.py` - `history_reader` parameter; `forecast_status` in the `pipeline` dict
- `backend/dlr_orchestrator.py` - `store` / `record_run`, `_run_cities_with_store`, `_rated_station_provenance`, `--store`, `--no-run-row`, run-log error line and exit status
- `backend/supabase_store.py` - `PIPELINE_RUN_COLUMNS`, `PIPELINE_RUN_JSONB`, `build_run_row`, `upsert_run`, `SupabaseStore.record_run`; `read_history` validates and warns
- `backend/historical_archive.py` - `validate_history_frame(df, source)`; `read_history` calls it
- `backend/tests/city_pipeline_test.py` - 4 new tests (13 functions), `forecast_status` in the pinned key-set literal
- `backend/tests/supabase_orchestrator_test.py` - 11 tests (8 offline fake-store, 3 live)
- `backend/tests/supabase_run_log_test.py` - 10 functions for `build_run_row`, `upsert_run` and the store-argument validation (not in the plan's file list; see Deviations)
- `backend/tests/supabase_store_test.py` - 3 new tests (19 functions); one 04-01 test adjusted (see Deviations)

## State for Phase 5 (its 05-01 precondition reads these)

- **Store selection:** `--store postgres`; children use `STORE_ARGS = ("--store", "postgres", "--no-run-row")`. Without `--no-run-row`, the orchestrator writes the run row itself.
- **Row-written flag:** `summary[i]["archived"]` is True only when the rating row was written; a failed city has no summary row at all and appears in `run["errors"]`.
- **Database secret:** `SUPABASE_DB_URL` is the only one.
- **Run context:** `supabase_store.run_context()` reads `GITHUB_RUN_ID`, `GITHUB_RUN_ATTEMPT` and `GITHUB_SHA` (first 7 characters).
- **`upsert_run(conn, row)`:** accepts any subset of `PIPELINE_RUN_COLUMNS` that includes `run_id` and updates every given non-key column on conflict. A column outside the list raises `ValueError`; with only `run_id` it does nothing on conflict. Phase 5's `live_run_log` can delegate to it, with `started_at` set once and `finished_at` filled later.
- **`forecast_status` values:** `ok`, `cold_start`, `failed` (in `result["pipeline"]` and stored per rating row).
- **Per-row identity (DB-06):** every rating row carries `config_fingerprint`, `forecast_model_sha256` (filled for `--forecast-method ml` when a forecast is produced; the ML branch is exercised by 04-01's unit tests, the live runs here use `naive`) and `anomaly_model_sha256`, so the models Phase 5 commits (OD-10) are identified per row.
- **Run-row shape written here:** `cities_failed[city]` = `{outcome, written, forecast_status, detector_model_loaded, error}`. Phase 5's own row additionally holds `exit_code`, `duration_s`, `forecast_error` and `fault_injected`; it writes through the same keys of `PIPELINE_RUN_COLUMNS`, which are the table's columns.

## Decisions Made

See `key-decisions` in the frontmatter. In short: the status describes the forecast call, the store path always runs the city pipeline with `archive=False` and writes the row itself so a failed write is a city error, and a run-row failure is non-fatal but makes the process exit 1.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] A 04-01 history test used a row the archive's row check rejects**
- **Found during:** Task 3
- **Issue:** `test_history_frame_has_archive_columns_and_csv_spelling` (plan 04-01, not a Phase 1 or 2 test) used a fallback row with a missing `air_temp`. `air_temp` is required by `units_def.PIPELINE_SCHEMA`, so the newly shared validation drops that row, exactly as the CSV reader would. A missing `air_temp` cannot occur for a history row in practice (it is NULL only when the station observation is absent, i.e. exhausted rows, which `HISTORY_SQL` excludes).
- **Fix:** the row now has a missing `solar_radiation` (an optional column) and the NaN assertion checks that column; the comment says why.
- **Files modified:** `backend/tests/supabase_store_test.py`
- **Verification:** the test and the CSV-parity test pass; full suite green.
- **Committed in:** `bde0499`

**2. [Rule 2 - Missing critical] Separate offline tests for `build_run_row` and `upsert_run`**
- **Found during:** Task 2
- **Issue:** the plan lists exactly 10 test functions in `supabase_orchestrator_test.py` (its acceptance count is `grep -c "^def test_"` = 10, then 11) and none for the new public functions that build SQL from an allow-list and redact error text (T-04-08 mitigation), nor for the store-argument validation.
- **Fix:** a new file `backend/tests/supabase_run_log_test.py` (10 functions): column order against the migration text, classification, redaction and the 1000-character bound, SQL shape with bound values, subset updates, the allow-list `ValueError` (including an injection-shaped key), a redacted `StoreError` without chained context, and rejection of an unusable `store` before any city runs.
- **Files modified:** `backend/tests/supabase_run_log_test.py` (created)
- **Verification:** 10 passed; the plan's two function counts (11 and 19) still hold.
- **Committed in:** `d78b8ad`

---

**Total deviations:** 2 auto-fixed (1 bug in a 04-01 test, 1 missing test coverage). **Impact on plan:** none on behavior; the second adds a test file outside the plan's `files_modified`.

## Discrepancies

- **Task 1 acceptance criterion 3 cannot pass as written.** It requires that no `assert` line in the commit's diff of `city_pipeline_test.py` lacks `forecast_status`, but the three new tests necessarily add `assert` lines. Measured instead, which is the criterion's evident intent: the commit removes no `assert` line, and the only edit to an existing test is the added `"forecast_status"` entry inside the set literal of `test_pipeline_key_reports_history_forecast_and_detector` (the `assert set(pipeline) == {` line itself is unchanged). The git-diff check printed the three added assert lines of the new test `test_history_reader_replaces_the_archive_read`.
- **Test literals extended with `"forecast_status"`:** one, in `backend/tests/city_pipeline_test.py`. `backend/tests/cleaning_pipeline_test.py` does not pin the exact pipeline key set and is untouched. `dlr_orchestrator_test.py` and `historical_archive_test.py` are byte-identical to before this plan (their `git diff` against the plan's start is empty).
- **Task 3 pin tests that passed on first run:** `test_history_window_starts_exactly_thirty_days_before_the_slot` (and the live boundary test) pin behavior that 04-01's `read_history` already had, so they could not fail before the implementation; they are regression pins, as the plan words it ("pinned"). The other two Task 3 tests failed first (no validation and no warning existed).
- The plan asks for `Co-Authored-By: Claude Opus 5.5`; the commits carry `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`, the attribution the harness specifies for this session (as in 04-01).
- The live orchestrator run uses stand-in anomaly model files (a stub estimator under a temporary `ANOMALY_ML_MODEL_DIR`) so `anomaly_model_sha256` is non-null and the cities count as healthy; the real `data/models/*.joblib` files (git-ignored) are not used by any test.
- The forecast-model hash for `--forecast-method ml` is not exercised end to end through the orchestrator here (the live runs use `naive`, as the plan's behavior list says); it is covered by 04-01's `model_identity` unit tests.

## TDD Gate Compliance

The plan is `type: execute` with `tdd="true"` tasks and one `feat` commit per task. For every task the new tests were written first and run against the old code: Task 1 showed 6 failures (`TypeError` on `history_reader`, `KeyError` on `forecast_status`), Task 2 showed 21 failures (`TypeError`/`AttributeError`, no `store`, no `build_run_row`), Task 3 showed 2 failures (no validation warning, no cold-start warning; the third offline test and the live test pin existing behavior). No separate RED commit exists because the plan specifies a single commit per task.

## Issues Encountered

- A test fixture's pipeline version `abc1234` contains the string `abc123` that the first version of the redaction test used as its secret, so the "secret absent from the row" assertion failed; the test now uses a secret that cannot appear in a version label.
- The owner's Homebrew PostgreSQL service was left alone; the live tests start and stop only their own cluster on a free loopback port, and no `pytest-of` postgres process remained afterwards.

## User Setup Required

None - no external service configuration required. Nothing is applied to the real Supabase project; that remains plans 04-05 and 04-06.

## Known Stubs

None.

## Threat Flags

None. The surface added (`pipeline_run` upsert from the orchestrator, error text going only to `pipeline_run` after `redact()`) is the one in the plan's threat model (T-04-07 to T-04-11); nothing outside it was introduced. No error text, file path or provider detail reaches `public.city_rating` (the rating row builder is unchanged and stores only labels).

## Next Phase Readiness

- Ready for 04-03 (backfill loader and smoke test): `validate_history_frame` and the store seam exist; the smoke test should assert the RLS policy that the empty-history WARNING points at (T-04-11).
- Ready for Phase 5: the flags, the `archived` flag, `forecast_status`, `upsert_run` and the run-row shape are in place (see the State for Phase 5 section).
- Verification: full suite 1484 passed, 37 skipped (the three live orchestrator tests plus the 34 live tests of 04-01 without the gate), 0 failed; with `DLR_TEST_PG_AUTOSTART=1` the two live files give 45 passed, none skipped; no path under `data/` or `outputs/` changed during the run.

## Self-Check: PASSED

- FOUND: backend/tests/supabase_orchestrator_test.py, backend/tests/supabase_run_log_test.py, backend/city_pipeline.py, backend/dlr_orchestrator.py, backend/supabase_store.py, backend/historical_archive.py
- FOUND commits: e364a92, d78b8ad, bde0499 (all ancestors of HEAD)
- Plan checks: `history_reader=store.read_history`, `"--no-run-row"`, `choices=("csv", "postgres")`, `def upsert_run`, `def build_run_row`, `on conflict (run_id) do update` present; orchestrator test functions 11, store test functions 19; shadow-facing definitions of `historical_archive` AST-identical to 5efe97d.

---
*Phase: 04-supabase-store-writer*
*Completed: 2026-10-21*
