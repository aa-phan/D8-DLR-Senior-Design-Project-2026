---
phase: 04-supabase-store-writer
plan: 01
subsystem: database
tags: [postgres, supabase, psycopg, migration, row-level-security, upsert, config-fingerprint]

requires:
  - phase: 02-data-cleaning
    provides: data_cleaning.clean_history, applied to the frame the history read returns
  - phase: 03-real-data-validation
    provides: the rating assumption set (config at 175b32b) whose label RATING_CONFIG_VERSION carries; NO-GO does not block this phase (owner re-sequencing 2026-10-21)
provides:
  - supabase/migrations/20261019000000_create_city_rating.sql (public.city_rating 49 columns, public.pipeline_run 12 columns, role dlr_writer, RLS, grants, comments; idempotent)
  - backend/supabase_store.py (connect, redact, slot_of, run_context, rating_config_snapshot, rating_config_fingerprint, file_sha256, model_identity, build_rating_row, upsert_rating, read_history, SupabaseStore, StoreError)
  - config.RATING_BASIS, config.RATING_CONFIG_VERSION, config.DB_HISTORY_WINDOW_DAYS
  - psycopg==3.3.6 and psycopg-binary==3.3.6 pins
  - backend/tests/supabase_live_test.py throwaway-Postgres fixture and 7 live tests
affects: [04-02 pipeline seam, 04-03 backfill loader and smoke test, 04-04 consumer doc, 04-05 owner migration push, 05 scheduled runner, 06 read view, 07 per-city conductors]

actuals:
  tokens: 30000
  tasks: 3
  commits: 2
plan_head_before: f9b1879618d93242aec85e554c12ffd6a6fcf922
plan_head_after: 06318238e8e77b045d589d0a534dc3b51eba0a51

tech-stack:
  added: [psycopg 3.3.6, psycopg-binary 3.3.6]
  patterns:
    - "INSERT ... ON CONFLICT (city, valid_time) DO UPDATE with first_written_at in neither the column list nor the SET list (OD-7)"
    - "automatic per-city sha256 config fingerprint next to the human label (DB-06)"
    - "psycopg imported only inside connect(); every exception message redacted and raised outside the except block so no context is chained"
    - "env-gated live tests on a private throwaway cluster started under pytest's tmp dir"

key-files:
  created:
    - supabase/migrations/20261019000000_create_city_rating.sql
    - backend/supabase_store.py
    - backend/tests/supabase_live_test.py
    - backend/tests/supabase_migration_test.py
    - backend/tests/supabase_store_test.py
    - backend/tests/rating_identity_test.py
  modified:
    - requirements.txt
    - backend/config.py

key-decisions:
  - "valid_time is the UTC hour of the run window end (hour-truncated, CHECK-enforced); the composer's aligned weather hour is observation_time (OD-7)"
  - "RATING_CONFIG_VERSION is v1-provisional-2026-10-13: config.py, city_point.py and thermal_model.py are byte-identical to Phase 3's run commit 175b32b"
  - "connect() pins the session time zone to UTC so the hour CHECK cannot be tripped by a session default"
  - "dlr_writer is policy-based (no BYPASSRLS), created without a credential; anon and authenticated get no privilege until Phase 6"
  - "The fingerprint is the authoritative identity; RATING_CONFIG_VERSION is its human-readable label"

patterns-established:
  - "Migration naming: supabase/migrations/<UTC yyyymmddHHMMSS>_<name>.sql, one column per line, lower-case SQL, parsed by tests"
  - "Client factory: supabase_store.connect() (psycopg 3, %(name)s paramstyle, reads SUPABASE_DB_URL, autocommit, statement_timeout 30s, timezone UTC)"
  - "run_id / run_attempt / pipeline_version come from run_context(): GITHUB_RUN_ID / GITHUB_RUN_ATTEMPT / GITHUB_SHA[:7], else local-<UTC stamp>-<8 hex> / 1 / git rev-parse --short HEAD"
  - "A config constant the rating path reads must be classified in FINGERPRINTED_CONFIG_NAMES or UNFINGERPRINTED_CONFIG_NAMES; the AST guard test names any that is not"

requirements-completed: [DB-01, DB-02, DB-04, DB-06]

coverage:
  - id: D1
    description: "Versioned migration creates public.city_rating (49 columns, PK on (city, valid_time)) and public.pipeline_run (12 columns), applies twice cleanly on an empty Postgres"
    requirement: DB-01
    verification:
      - kind: unit
        ref: "backend/tests/supabase_migration_test.py#test_city_rating_has_every_db01_column_with_its_type"
        status: pass
      - kind: integration
        ref: "backend/tests/supabase_live_test.py#test_tracer_one_city_hour_round_trips_through_postgres"
        status: pass
    human_judgment: false
  - id: D2
    description: "Idempotent upsert on (city, valid_time): a same-hour retry overwrites in place, first_written_at unchanged; offset spellings are one key, neighbours are separate"
    requirement: DB-02
    verification:
      - kind: integration
        ref: "backend/tests/supabase_live_test.py#test_offset_spellings_are_one_key_and_neighbors_are_separate"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_migration_test.py#test_upsert_columns_match_the_migration_and_keep_first_written_at"
        status: pass
    human_judgment: false
  - id: D3
    description: "History read returns the CSV archive's frame for the 30-day window strictly before the run slot, excluding exhausted rows, and feeds Phase 2's cleaner"
    requirement: DB-02
    verification:
      - kind: unit
        ref: "backend/tests/supabase_store_test.py#test_history_frame_matches_the_csv_reader_for_the_same_rows"
        status: pass
      - kind: integration
        ref: "backend/tests/supabase_live_test.py#test_tracer_one_city_hour_round_trips_through_postgres"
        status: pass
    human_judgment: false
  - id: D4
    description: "DB-01 boundary, adjacency, empty, encoding, ordering and precision edges (CHECKs, MW golden, hour floor, exhausted nulls, UTF-8)"
    requirement: DB-01
    verification:
      - kind: integration
        ref: "backend/tests/supabase_live_test.py#test_checks_reject_bad_rows"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_store_test.py#test_build_rating_row_uses_python_types_and_the_mw_golden"
        status: pass
    human_judgment: false
  - id: D5
    description: "Least-privilege writer: dlr_writer has only SELECT/INSERT/UPDATE, no credential in any file, RLS on, anon/authenticated nothing; a missing policy hides rows silently"
    requirement: DB-04
    verification:
      - kind: unit
        ref: "backend/tests/supabase_migration_test.py#test_writer_role_is_least_privilege_and_has_no_credential"
        status: pass
      - kind: integration
        ref: "backend/tests/supabase_live_test.py#test_consumer_roles_have_no_privileges"
        status: pass
    human_judgment: false
  - id: D6
    description: "A failed connection and any logged text carry no part of the password; a blank SUPABASE_DB_URL raises StoreError naming the variable"
    requirement: DB-04
    verification:
      - kind: unit
        ref: "backend/tests/supabase_store_test.py#test_connection_failure_does_not_leak_the_password"
        status: pass
    human_judgment: false
  - id: D7
    description: "Every row names what produced it: per-city config fingerprint (sensitive to every conductor parameter, stable across processes) and the sha256 of the model files the run loaded; a change alters values, never columns"
    requirement: DB-06
    verification:
      - kind: unit
        ref: "backend/tests/rating_identity_test.py#test_each_rating_assumption_changes_only_its_citys_fingerprint"
        status: pass
      - kind: unit
        ref: "backend/tests/rating_identity_test.py#test_every_config_name_the_rating_path_reads_is_classified"
        status: pass
      - kind: unit
        ref: "backend/tests/rating_identity_test.py#test_a_conductor_or_model_change_alters_values_not_columns"
        status: pass
    human_judgment: false
  - id: D8
    description: "psycopg / psycopg-binary 3.3.6 legitimacy confirmed before install"
    verification: []
    human_judgment: true
    rationale: "Package legitimacy is a human decision (Task 1, gate blocking-human); the owner replied approved and the orchestrator checked PyPI metadata and wheels"

duration: ~55min
completed: 2026-10-21
status: complete
---

# Phase 4 Plan 01: Postgres store tracer and schema contract Summary

**Idempotent per-city hourly rating store: a committed Supabase migration, a psycopg 3 writer with `ON CONFLICT (city, valid_time) DO UPDATE`, a history read in the CSV archive's frame shape, and a per-city config fingerprint plus model-file hashes on every row, proven on a throwaway local Postgres**

## Performance

- **Duration:** about 55 min (estimate; the start time was not captured on this continuation)
- **Started:** 2026-10-21 (continuation after the Task 1 approval)
- **Completed:** 2026-10-21T22:55Z
- **Tasks:** 3 (Task 1 approved with no commit, Tasks 2 and 3 committed)
- **Files modified:** 8 (6 created, 2 modified)

## Task 1 approval (package legitimacy gate)

Task 1 (`checkpoint:human-verify`, `gate="blocking-human"`) was resolved by the user with **"approved"** for `psycopg==3.3.6` and `psycopg-binary==3.3.6`. The orchestrator verified the preconditions before resuming (Phase 3 decision line present, reading NO-GO; roadmap sentence "The VAL-03 NO-GO does not block this phase" present; `backend/data_cleaning.py` tracked) and the PyPI metadata (both packages 3.3.6 uploaded 2026-09-18, psycopg.org and github.com/psycopg/psycopg links, cp312 macOS arm64 and manylinux x86_64 binary wheels). Nothing changed, so there is no commit. After install, `pip check` reported no broken requirements, and a `pip download` for the runner platform (manylinux x86_64, cp312) fetched `psycopg_binary-3.3.6-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl` and `psycopg-3.3.6-py3-none-any.whl`.

## Accomplishments

- Tracer proven end to end: a real `run_city_pipeline` result for AUSTIN is written by `SupabaseStore.write_rating` into `public.city_rating` of a throwaway Postgres 16 on which the migration was applied twice; the next hour's `read_history` returns an `ARCHIVE_COLUMNS` frame holding it and `clean_history` keeps it usable.
- OD-7 conflict rule: a same-hour retry (14:12Z after 14:07Z) leaves one row with the retry's values, `first_written_at` unchanged, `computed_at` not earlier.
- Schema contract pinned: 11 offline migration tests, 34 live tests (CHECK boundaries, key adjacency, privileges, RLS) and the writer's offline row-shaping, SQL and secret-hygiene tests.
- DB-06 identity: per-city fingerprint that changes with any conductor parameter or other rating assumption and is identical across processes with different `PYTHONHASHSEED`; AST drift guard; model hashes taken from the files the run loaded.

## Task Commits

1. **Task 1: Package legitimacy gate** - no commit (approved by user, nothing changed)
2. **Task 2: Tracer - migration, writer and history read for one city-hour** - `a036c0d` (feat)
3. **Task 3: Schema contract, row identity, writer row shaping, privileges and secret hygiene** - `0631823` (test)

**Plan metadata:** the `docs(04-01)` commit that adds this SUMMARY and the STATE/ROADMAP/REQUIREMENTS updates.

## Files Created/Modified

- `supabase/migrations/20261019000000_create_city_rating.sql` - DB-01 schema, `dlr_writer` role, RLS, grants, comments; idempotent
- `backend/supabase_store.py` - the store (718 lines)
- `backend/config.py` - additive section "Rating store labels and history window": `RATING_BASIS`, `RATING_CONFIG_VERSION`, `DB_HISTORY_WINDOW_DAYS`
- `requirements.txt` - the two psycopg pins with a comment block
- `backend/tests/supabase_live_test.py` - throwaway-Postgres fixture, tracer, 6 contract tests
- `backend/tests/supabase_migration_test.py`, `supabase_store_test.py`, `rating_identity_test.py` - offline contract tests (11 + 16 + 6 functions)

## Decisions Made

- **Migration naming and client factory:** `supabase/migrations/<UTC yyyymmddHHMMSS>_<name>.sql`; `supabase_store.connect()` uses psycopg 3, `%(name)s` placeholders, reads `SUPABASE_DB_URL`, autocommit, `statement_timeout = '30s'`, `timezone = 'UTC'`, `prepare_threshold=None`.
- **Tables and `valid_time`:** `public.city_rating` keyed `(city, valid_time)`; `valid_time` is the hour-truncated UTC run slot of the window end (OD-7). `public.pipeline_run` is the 12-column run log Phase 5 fills.
- **run identity:** `run_context()` reads `GITHUB_RUN_ID`, `GITHUB_RUN_ATTEMPT`, `GITHUB_SHA[:7]`, falling back to `local-<UTC stamp>-<8 hex>`, 1 and `git rev-parse --short HEAD` (else `unknown`).
- **DB-06 recipe:** `RATING_CONFIG_SNAPSHOT_SCHEMA = 1`; the fingerprint is the sha256 of `json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False)`; the snapshot holds every attribute of `vars(city_point.city_point(city).conductor)`, the point (coordinate, bearing, static rating, bounds) and each fingerprinted config constant reduced to the city's entry.
  - `RATING_CONFIG_SOURCE_FILES = ("backend/config.py", "backend/city_point.py", "backend/thermal_model.py")`
  - `FORECAST_ARTIFACT_PATHS = {"ml": ampacity_forecast._model_path_for}`, `FORECAST_METHODS_WITHOUT_ARTIFACT = ("naive", "ewm")`
  - `RATING_PATH_MODULES = (city_point, thermal_model, city_rating, DLRSafetyMonitor, ampacity_forecast, anomaly_detector, data_cleaning, city_pipeline, ercot_dlr_merger, wind_vector)`
  - `FINGERPRINTED_CONFIG_NAMES` (19): STATIC_RATINGS, RATING_BOUNDS_BY_LOCATION, CITY_LINE_BEARING_DEG, CITY_COORDINATES, SUBCONDUCTORS_PER_PHASE, DEFAULT_CONDUCTOR_CONFIG_KWARGS, LINE_VOLTAGE_KV, POWER_FACTOR, ANOMALY_CONTROL_LIMIT_K_BY_LOCATION, DEFAULT_ANOMALY_CONTROL_LIMIT_K, ANOMALY_ML_FEATURE_COLUMNS, ANOMALY_ML_RAW_DATA_KEYS, FORECAST_HORIZON_MINUTES, FORECAST_MIN_HISTORY_ROWS, FORECAST_BACKTEST_QUANTILES, FORECAST_EWM_HALFLIFE_MIN, FORECAST_ML_FEATURE_WEATHER_COLUMNS, FORECAST_ML_LAG_HOURS, FORECAST_ML_ROLLING_WINDOW_HOURS
  - `UNFINGERPRINTED_CONFIG_NAMES` (9, each with a reason): LOCATIONS, conductor_kwargs_for, DEFAULT_RATING_BOUNDS, DELTA_FRACTION, DEFAULT_STATIC_RATING, FORECAST_ML_MODEL_DIR, FORECAST_ML_MODEL_FILENAME_TEMPLATE, ANOMALY_ML_MODEL_DIR, ANOMALY_ML_MODEL_FILENAME_TEMPLATE
  - The AST guard reported no unclassified name. `SUBCONDUCTORS_PER_PHASE` is fingerprinted as the plan specifies although no rating-path module reads it today (it is read by the shadow bundle only).
- **RATING_CONFIG_VERSION chosen:** `v1-provisional-2026-10-13`. The pre-edit check `git diff --quiet 175b32b -- backend/config.py backend/city_point.py backend/thermal_model.py` exited 0, so Phase 7 had not changed those files.
- **Fingerprints at commit time** (config at `0631823`):
  - AUSTIN `a47b92e4a1f405fd2f8bd752539c371c0d7a1f3cc8cbed2cfd3c4843bb5b9c26`
  - CORPUS_CHRISTI `33de6fc4270e45df4248eeec936f0f0f5509ee86759f31cad167c8455f975267`
  - MIDLAND `deaf07335fabf7456607b004f0222c26d1eb6d5d9a561a3c12fde95f70091c7e`
  - EL_PASO `9a064f9cc0b96e5f6cfb1d98ffbe8567a0fcad4fd3b5cfc8918b6700e9750d02`
- **Note for Phase 7:** changing a conductor parameter needs only a config edit and a `RATING_CONFIG_VERSION` bump (the fingerprints change on their own). A new config constant on the rating path must be classified in `supabase_store`'s two lists; `rating_identity_test.py::test_every_config_name_the_rating_path_reads_is_classified` names it if it is not.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical] Pin the session time zone to UTC in `connect()`**
- **Found during:** Task 2 (tracer run)
- **Issue:** The `valid_time = date_trunc('hour', valid_time)` CHECK truncates in the session time zone, and the first tracer run returned `09:00-05:00` for a 14:00Z slot because the session inherited the local zone. In a zone with a half-hour offset a UTC-hour-aligned slot would fail the CHECK.
- **Fix:** `connect()` runs `set timezone = 'UTC'` after `set statement_timeout`; the tracer compares instants in UTC.
- **Files modified:** `backend/supabase_store.py`, `backend/tests/supabase_live_test.py`
- **Verification:** tracer and all live tests pass
- **Committed in:** `a036c0d`

**2. [Rule 1 - Test precision] CSV parity compared to 1e-12 relative, not bit for bit**
- **Found during:** Task 3
- **Issue:** pandas' default CSV float parser differs from the exact value by one ulp (`1431.0964428223047` vs `...044`), so the forecast bands from the CSV frame and the DB frame differed in the last bit although the inputs are the same rows.
- **Fix:** the comparison uses `pytest.approx(rel=1e-12)` with a comment; the frame comparison, `n_observations` and the cleaning report stay exact.
- **Files modified:** `backend/tests/supabase_store_test.py`
- **Committed in:** `0631823`

---

**Total deviations:** 2 auto-fixed (1 missing critical, 1 test precision). No defect in `supabase_store.py` was exposed by Task 3's tests, so no store fix was made there. **Impact on plan:** none beyond the two items above.

## Discrepancies

- The Task 2 acceptance criterion `git diff --quiet 72832ee -- backend/forecast_experiment.py backend/forecast_experiment_audit.py backend/legacy_corridor.py .github/workflows/shadow_collect.yml` exits 1 because `.github/workflows/shadow_collect.yml` was changed after 72832ee by commit `762a0cd` (the shadow persistence fix), outside this plan. Measured against HEAD before this plan's commits the same paths are unchanged, and this plan touches none of them (DB-02 prohibition holds).
- The plan asks for a `Co-Authored-By: Claude Opus 5.5` trailer; the commits carry `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`, the attribution the harness specifies for this session.
- The plan's interfaces block listed `city_rating` among modules reading `config.ANOMALY_ML_FEATURE_COLUMNS`, `CITY_COORDINATES` and `LOCATIONS`; the AST finds none (those are docstring mentions). Nothing changes: the lists are a superset of what the AST reports.

## TDD Gate Compliance

The plan is `type: execute`; Task 3 carries `tdd="true"` with a single `test(04-01)` commit, as the plan specifies. The tests were written against the implementation the Task 2 tracer had already built, so they passed on first run and there is no separate failing-test (RED) commit or `feat` GREEN commit for Task 3. As substitute evidence the tests are not vacuous, five mutants of `supabase_store.py` were applied and each was killed by at least one test, then reverted: `<=` for `<` in the slot filter (2 failures), dropping `not exhausted` (1), disabling per-city reduction in `_per_city` (5), letting `city` be the only key column in the SET list (1), and a code change inside `connect()` (4 errors).

## Issues Encountered

- `psycopg` aliases `str` as an unknown-typed parameter, so `%(probe_trail)s::jsonb` and empty `text[]` lists worked without wrappers; no issue, noted because the research flagged type adaptation as a pitfall.
- The Homebrew PostgreSQL service the owner runs (`/opt/homebrew/var/postgresql@16`) was left untouched; the tests start and stop only their own cluster on a free loopback port, and the pytest data directories were removed.

## User Setup Required

None - no external service configuration required. The owner's steps on the real Supabase project (apply the migration, set the `dlr_writer` credential, add `SUPABASE_DB_URL`) are plans 04-05 and 04-06. Note for then: `requirements.txt` is installed by `.github/workflows/shadow_collect.yml` and `publication_lag_check.yml`, so once main is pushed their runs install the two new packages.

## Known Stubs

None.

## Threat Flags

None - the surface added (database connection, writer role, row-level security) is the one in the plan's threat model (T-04-01 to T-04-06, T-04-26, T-04-SC).

## Next Phase Readiness

- Ready for 04-02: `SupabaseStore.read_history` and `write_rating(result, end, provenance)` have the names and shapes the pipeline seam needs; `build_rating_row` already reads `pipeline.get("forecast_status")` (None until 04-02 adds it); `pipeline_run` exists but has no writer yet.
- 04-03 can compute Phase 3's fingerprints with the same `rating_config_snapshot` recipe and reuse the `_pg_admin_url` fixture by copying it.
- Nothing is applied to the real Supabase project; that stays the owner's step in 04-05.

## Self-Check: PASSED

- FOUND: supabase/migrations/20261019000000_create_city_rating.sql, backend/supabase_store.py, backend/tests/supabase_live_test.py, backend/tests/supabase_migration_test.py, backend/tests/supabase_store_test.py, backend/tests/rating_identity_test.py
- FOUND commits: a036c0d, 0631823 (both ancestors of HEAD)
- Verification: offline files 53 passed; live file `DLR_TEST_PG_AUTOSTART=1` 34 passed; full suite 1454 passed, 34 skipped (the live file without the gate), 0 failed; no path under data/ or outputs/ changed during the run.

---
*Phase: 04-supabase-store-writer*
*Completed: 2026-10-21*
