---
phase: 06-exposure-e2e-verification
plan: 01
subsystem: database
tags: [postgres, supabase, postgrest, rls, security-invoker-view, grants, pytest, psycopg]

requires:
  - phase: 04-supabase-store-writer
    provides: "public.city_rating (PK city, valid_time; RLS on; dlr_writer role), public.pipeline_run, OD-7 upsert, DB-06 identity columns"
  - phase: 05-scheduled-live-runs
    provides: "live hourly rows carrying config.RATING_BASIS and config.RATING_CONFIG_VERSION"
provides:
  - "Unapplied migration 20261026195124_expose_latest_rating.sql: security_invoker view public.latest_rating (34 commented columns), newest-row index, assert_fresh RPC, revoke sweep plus SELECT-only grants, read policy city_rating_public_read"
  - "backend/latest_rating_contract.py: STORED/COMPUTED/LATEST_COLUMNS, STALE_AFTER_MINUTES, PROVISIONAL_WORD, is_provisional, age_minutes, is_stale"
  - "supabase/ops/verify_exposure.sql: 17 read-only named checks shared by the local test and the owner's live runs"
  - "backend/tests/local_pg.py: throwaway local Postgres harness with Supabase roles and legacy default grants"
  - "backend/tests/expose_migration_test.py: 21 tests (offline drift guards plus local-Postgres proofs)"
affects: [06-04, 06-05, 06-06, 06-09, 06-10, 06-12, 06-13, 07-per-city-conductors]

# Actuals (#2632): same estimateTokens scale (chars/4 over the realized diff)
actuals:
  tokens: 18000
  tasks: 2
  commits: 2
plan_head_before: 82c033294c18705a566fb0c7d4fdbe7ac56df290
plan_head_after: f82f130583e9e16b360936fa880791f8aa0bcd81

tech-stack:
  added: []
  patterns:
    - "Invoker view over an RLS table, with explicit REVOKE ALL then SELECT-only GRANT (privilege is the lock, RLS the second lock)"
    - "Python contract module twinned to a SQL view, with an offline drift-guard test"
    - "Local throwaway Postgres harness started from Supabase's legacy default grants (worst case)"
    - "Shared read-only verification SELECT (check_name, ok, detail) run by tests and by the owner live"

key-files:
  created:
    - supabase/migrations/20261026195124_expose_latest_rating.sql
    - supabase/ops/verify_exposure.sql
    - backend/latest_rating_contract.py
    - backend/tests/local_pg.py
    - backend/tests/expose_migration_test.py
  modified:
    - backend/tests/supabase_smoke_test.py

key-decisions:
  - "is_provisional is the word rule on rating_basis OR config_version (D-03 as revised 2026-10-25), guarded offline against the real config strings"
  - "age_minutes is ceil(...)::integer and is_stale a direct timestamp comparison, so age_minutes > 90 is exactly is_stale; exactly 90 minutes is fresh"
  - "assert_fresh uses the same strict comparison as the view and runs security invoker with an empty search_path"
  - "Local module seed puts the newest slot at the current UTC hour (not hour minus one) so the default assert_fresh() stays fresh at every minute of the hour"

patterns-established:
  - "Exact-boundary proof: drop the whole-hour CHECK inside a rolled-back transaction so a row can sit exactly now() - 90 minutes"
  - "Negative checks on the shared verifier: a stray grant, readable run log, extra callable function and write policy each turn the matching rows false"

requirements-completed: [API-01]

coverage:
  - id: D1
    description: "latest_rating invoker view with the 34-column contract in order, equal to latest_rating_contract.LATEST_COLUMNS, with the three computed columns last"
    requirement: API-01
    verification:
      - kind: unit
        ref: "backend/tests/expose_migration_test.py#test_view_columns_equal_the_contract"
        status: pass
      - kind: integration
        ref: "backend/tests/expose_migration_test.py#test_tracer_anon_reads_the_newest_row_per_city"
        status: pass
    human_judgment: false
  - id: D2
    description: "Newest row per city wins even when it is a fallback row (D-04)"
    requirement: API-01
    verification:
      - kind: integration
        ref: "backend/tests/expose_migration_test.py#test_newest_row_wins_even_when_it_is_a_fallback"
        status: pass
    human_judgment: false
  - id: D3
    description: "90-minute rule agrees between age_minutes, is_stale and assert_fresh, including the exact boundary"
    requirement: API-01
    verification:
      - kind: integration
        ref: "backend/tests/expose_migration_test.py#test_age_and_stale_agree_with_assert_fresh_at_the_boundary"
        status: pass
      - kind: integration
        ref: "backend/tests/expose_migration_test.py#test_exactly_90_minutes_is_fresh_and_one_microsecond_more_is_stale"
        status: pass
      - kind: unit
        ref: "backend/tests/expose_migration_test.py#test_contract_age_and_stale_rules"
        status: pass
    human_judgment: false
  - id: D4
    description: "is_provisional is true for the real live label, the real backfill label and a word only in config_version; false for a lifted pair; drift guard in the default suite"
    requirement: API-01
    verification:
      - kind: integration
        ref: "backend/tests/expose_migration_test.py#test_is_provisional_reads_the_real_labels"
        status: pass
      - kind: unit
        ref: "backend/tests/expose_migration_test.py#test_live_label_is_provisional_offline"
        status: pass
    human_judgment: false
  - id: D5
    description: "anon and authenticated are refused INSERT, UPDATE, DELETE, TRUNCATE by privilege (42501) and cannot read pipeline_run, starting from every legacy default grant"
    requirement: API-01
    verification:
      - kind: integration
        ref: "backend/tests/expose_migration_test.py#test_writes_are_denied_by_privilege"
        status: pass
    human_judgment: false
  - id: D6
    description: "The view applies the caller's RLS; with the read policy dropped anon sees zero rows"
    requirement: API-01
    verification:
      - kind: integration
        ref: "backend/tests/expose_migration_test.py#test_view_obeys_the_callers_rls"
        status: pass
    human_judgment: false
  - id: D7
    description: "assert_fresh contract (200 JSON, PT503 naming cities, 22023 out of range, invoker, stable, empty search_path, anon-executable, no PUBLIC execute); city list equals config.LOCATIONS"
    requirement: API-01
    verification:
      - kind: integration
        ref: "backend/tests/expose_migration_test.py#test_assert_fresh_contract"
        status: pass
      - kind: unit
        ref: "backend/tests/expose_migration_test.py#test_assert_fresh_city_list_matches_config_locations"
        status: pass
    human_judgment: false
  - id: D8
    description: "Concurrency edge: same-key re-upsert by the Phase 4 writer leaves one row per city; re-applying the migration is idempotent"
    requirement: API-01
    verification:
      - kind: integration
        ref: "backend/tests/expose_migration_test.py#test_same_key_upsert_keeps_one_row_per_city"
        status: pass
      - kind: integration
        ref: "backend/tests/expose_migration_test.py#test_expose_migration_reapplies_cleanly"
        status: pass
    human_judgment: false
  - id: D9
    description: "verify_exposure.sql is one read-only SELECT of 17 checks, all true on the seeded local database, and each check can fail"
    requirement: API-01
    verification:
      - kind: integration
        ref: "backend/tests/expose_migration_test.py#test_verify_exposure_sql_reports_every_check_ok"
        status: pass
      - kind: unit
        ref: "backend/tests/expose_migration_test.py#test_verify_exposure_sql_is_one_read_only_select"
        status: pass
    human_judgment: false
  - id: D10
    description: "The live half of API-01 (migration applied to the Supabase project, REST read with the publishable key) is NOT done here; it is plan 06-09 after Phase 5's 05-08 sign-off"
    requirement: API-01
    verification: []
    human_judgment: true
    rationale: "Per D-06 this plan is offline; applying the migration and reading through the real PostgREST gateway needs the owner and cannot be shown by a local test"

# Metrics
duration: 16min
completed: 2026-10-26
status: complete
---

# Phase 6 Plan 01: Expose latest_rating Summary

**Security-invoker `public.latest_rating` view (34 commented columns), SELECT-only grants with a revoke sweep, read policy, `assert_fresh` RPC and a shared `verify_exposure.sql`, proven read-only for anon on a local Postgres that starts with every legacy default grant; nothing applied to Supabase.**

## Performance

- **Duration:** 16 min
- **Started:** 2026-10-26T19:51:00Z
- **Completed:** 2026-10-26T20:07:00Z
- **Tasks:** 2 (1 tracer, 1 auto/tdd)
- **Files modified:** 6 (5 created, 1 modified)

## Accomplishments

- **Migration** `supabase/migrations/20261026195124_expose_latest_rating.sql` (sorts after `20261023000000_...`; no Phase 4 file touched, the sha256 pin test still passes). It creates the descending index, the view, 35 comments (view plus 34 columns), the revoke sweep and SELECT grants, the default-privilege revokes for role postgres, the read policy and `assert_fresh`, and ends with `notify pgrst, 'reload schema'`.
- **Final 34-column list, in order** (equal to `LATEST_COLUMNS`): city, valid_time, observation_time, rating_amps, rating_mw, static_rating_amps, static_rating_mw, line_voltage_kv, power_factor, status, fallback, fallback_gates, alerts, exhausted, forecast_method, forecast_status, forecast_amps, forecast_ci_lower_amps, forecast_ci_upper_amps, forecast_horizon_min, detector_signal, rating_basis, config_version, origin, run_id, pipeline_version, computed_at (27); config_fingerprint, forecast_model_sha256, anomaly_model_sha256, solar_source (D-01, 4); age_minutes, is_stale, is_provisional (computed, 3).
- **The three computed expressions:**
  - `ceil(extract(epoch from (now() - valid_time)) / 60)::integer as age_minutes`
  - `(valid_time < now() - interval '90 minutes') as is_stale`
  - `(position('provisional' in lower(rating_basis)) > 0 or position('provisional' in lower(config_version)) > 0) as is_provisional`
- **Extra revoke beyond the plan:** none. The privileges section is exactly the plan's: `revoke all` on all tables and all sequences in schema public from anon and authenticated, `grant select on public.city_rating, public.latest_rating`, `alter default privileges for role postgres ... revoke all` on tables and sequences, plus `revoke all on function public.assert_fresh(integer) from public, anon, authenticated` before the EXECUTE grant.
- **Proofs on the local cluster** (what each means for the owner): the public key reads exactly four rows from `latest_rating` and the full history from `city_rating`; it is refused (42501, permission denied) on INSERT, UPDATE, DELETE and TRUNCATE as both anon and authenticated, and on any read of the run log; the view is not a back door (dropping the read policy leaves anon with zero rows); a rating is called old only when more than 90 whole minutes old and the number shown never contradicts the flag, checked at exactly 90 minutes and 90 minutes plus one microsecond; today's real live and backfill labels read provisional while a lifted pair reads final.
- **Mutation spot-check** (migration mutated, tests re-run, file restored byte-identical): dropping `security_invoker` fails 3 tests; `floor` instead of `ceil` fails the boundary test; testing only `rating_basis` fails 2 tests; skipping the table revoke sweep fails the re-apply snapshot and the verifier; `<=` instead of `<` in either the view or `assert_fresh` fails the exact-90-minute test.

## Task Commits

1. **Task 1 (tracer): latest_rating invoker view with the 34-column contract and SELECT-only grants, read by anon on a local Postgres** - `4d8cde6` (feat)
2. **Task 2: assert_fresh, the 90-minute boundary, the real provisional labels, write denial, invoker RLS, idempotency and the shared verification query** - `f82f130` (feat)

**Plan metadata:** committed with this SUMMARY (docs: complete plan).

The tracer gate: `type="tracer"` without `gate="blocking-human"` and with an automated-only `<verify>`, so the tracer verify was re-run end to end (7 passed, nothing skipped) and expansion continued with no checkpoint.

## Files Created/Modified

- `supabase/migrations/20261026195124_expose_latest_rating.sql` - the exposure migration (view, comments, index, grants, policy, assert_fresh)
- `supabase/ops/verify_exposure.sql` - 17-check read-only SELECT (check_name, ok, detail)
- `backend/latest_rating_contract.py` - published column contract and the three rules in Python
- `backend/tests/local_pg.py` - throwaway Postgres harness (cluster, roles with legacy grants, migration apply, row helpers)
- `backend/tests/expose_migration_test.py` - 21 tests
- `backend/tests/supabase_smoke_test.py` - one assertion updated (see Deviations)

## Decisions Made

- Followed D-01..D-05 and the plan's SQL. The `is_provisional` word rule is the revised D-03.
- `assert_fresh` returns `oldest_valid_time` as the minimum over the four latest rows and names `missing=` and `stale=` city lists in the PT503 detail.
- Phase 4's own `revoke all on public.city_rating, public.pipeline_run` already denies table writes; the new sweep matters for the new view and any later object. The write-denial test therefore cannot tell the sweep apart for `city_rating`, and the sweep is pinned by the re-apply snapshot and by `verify_exposure.sql` instead.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Seed slot would make the default `assert_fresh()` test flaky**
- **Found during:** Task 1 design (the plan seeds the newest slot at current UTC hour minus one hour, and Task 2 asserts `assert_fresh()` returns ok)
- **Issue:** that slot is 60-119 minutes old, so after minute 30 of any hour the default 90-minute check would raise PT503 and the test would fail depending on the time of day.
- **Fix:** the module fixture seeds the newest slot at the current UTC hour (0-59 minutes old, always fresh). The D-04 fallback test inserts its newer row at the next hour inside a rolled-back transaction. The two boundary tests that need ages above 60 minutes seed hour minus one and hour minus two inside their own rolled-back transactions and read the age from the view, so the plan's intent is kept.
- **Files modified:** backend/tests/expose_migration_test.py
- **Verification:** all 21 tests pass; boundary tests run for ages 60-179 minutes.
- **Committed in:** 4d8cde6, f82f130

**2. [Rule 1 - Bug] Phase 4 smoke test asserted anon cannot SELECT after all migrations**
- **Found during:** Task 2 (full suite with `DLR_TEST_PG_AUTOSTART=1`)
- **Issue:** `supabase_smoke_test.py::test_smoke_passes_on_a_fresh_migration_and_leaves_no_rows` applies every migration and expected `anon_can_select is False`; the new migration grants anon SELECT by design (OD-6), so the assertion was stale. `consumers_cannot_write` still passes.
- **Fix:** the assertion now expects `True`, with a comment naming Phase 6's expose migration.
- **Files modified:** backend/tests/supabase_smoke_test.py
- **Verification:** full suite with local Postgres: 1815 passed, 0 skipped, 0 failed.
- **Committed in:** f82f130

**3. [Rule 2 - Missing critical] Extra tests beyond the plan's list (21 instead of 18)**
- **Added:** `test_exactly_90_minutes_is_fresh_and_one_microsecond_more_is_stale` (the plan's boundary test cannot hit an exact tie, and mutating `<` to `<=` survived it), `test_view_comment_statements_cover_every_column` (offline comment coverage so the default suite catches a missing comment), and `test_verify_exposure_sql_is_one_read_only_select` (offline guard that the shared file stays one read-only SELECT).
- **Committed in:** f82f130

**4. Attribution line.** The plan asked for `Co-Authored-By: Claude Opus 5.5`; the commits carry the session's attribution lines (`Claude Sonnet 5.5` plus the session link) per the executor instructions.

### TDD note (Task 2)

Tests were written before the SQL. Against Task 1's migration, 6 of the new tests failed (`test_assert_fresh_city_list_matches_config_locations`, `test_verify_exposure_sql_is_one_read_only_select`, `test_assert_fresh_contract`, `test_age_and_stale_agree_with_assert_fresh_at_the_boundary`, `test_expose_migration_reapplies_cleanly`, `test_verify_exposure_sql_reports_every_check_ok`); the other 8 new tests exercise Task 1 behavior (labels, write denial, RLS, upsert, comments) and passed immediately. The Task 2 SQL then turned all green. Two test-side mistakes found at GREEN were fixed in the tests, not the SQL (a `;` inside a string literal confused the statement splitter; `anon=X/postgres` matched a PUBLIC-entry substring).

---

**Total deviations:** 2 auto-fixed bugs (Rule 1), 1 added coverage (Rule 2), 1 attribution wording note.
**Impact on plan:** no scope creep; the migration, column list and expressions are exactly the plan's.

## Discrepancies

- **Plan seeds "current UTC hour minus one hour"; implemented as the current UTC hour** for the shared fixture (reason and mitigation under Deviation 1).
- **Function privileges beyond assert_fresh are not swept.** A future function created in `public` is executable by PUBLIC by Postgres default (a schema-level revoke cannot remove that). `verify_exposure.sql` check `anon_executable_public_functions_are_assert_fresh_only` is the guard; the migration adds no `alter default privileges ... on functions` (not in the plan). Worth a look in 06-09 if the live project already has other public functions.
- **Local PostgREST was not exercised** (not available); HTTP status mapping of PT503 to 503 and 42501 to 401/403 stays as researched and is exercised at the live run.

## Issues Encountered

None blocking. Pre-existing working-tree changes (.DS_Store files, `.planning/config.json`, untracked `.obsidian/`, `graphify-out/`, etc.) were left unstaged. `.planning/workstreams/production-pipeline/STATE.md` already carried an uncommitted change before this plan; the state update below builds on it.

## Known Stubs

None. No placeholder text, empty-value-to-UI paths or unwired data in the files this plan created.

## Threat Flags

None. `assert_fresh` and the grant changes are exactly the surface in the plan's threat model (T-06-01..T-06-05); T-06-06 stays accepted.

## User Setup Required

None - no external service configuration required. The live apply (`supabase db push --db-url ...`), the owner confirmation of the one-way column list (D-01..D-03) and the first `verify_exposure.sql` live run are plan 06-09, after Phase 5's 05-08 sign-off. Nothing was pushed and nothing was applied to Supabase.

## Next Phase Readiness

- Ready for 06-02 onward. `backend/tests/local_pg.py` (`require_local_pg`, `cluster`, `SUPABASE_ROLES_SQL`, `apply_migrations`, `rating_row`, `insert_rows`, `run_select_file`) is ready for 06-05 and 06-09.
- API-01 stays open in REQUIREMENTS.md on purpose: five later plans (06-04, 06-06, 06-09, 06-12, 06-13) also declare it, and its live half is 06-09; `requirements.ready-ids` reported 0 of 1 ready.
- Phase 7 hand-off (REVAL-01): lifting the provisional label must remove the word from BOTH `config.RATING_BASIS` and `config.RATING_CONFIG_VERSION`; the offline test `test_live_label_is_provisional_offline` will fail with a message naming REVAL-01 until the expectation is updated deliberately.

## Self-Check: PASSED

- Files present: migration, `verify_exposure.sql`, `latest_rating_contract.py`, `local_pg.py`, `expose_migration_test.py` (all FOUND).
- Commits `4d8cde6` and `f82f130` are ancestors of HEAD; `git rev-list --count 82c0332..HEAD` measured 2 at SUMMARY time.
- Task acceptance criteria re-run: one expose migration sorting after Phase 4; `security_invoker = true`, `drop policy if exists city_rating_public_read`, `sqlstate 'PT503'`, `security invoker`, `check_name` all present; contract import prints ok; Phase 4 pin test passes (15 passed); `git log --grep='(06-01)' -- supabase/migrations` lists only the expose file; 21 test functions (at least 18); offline subset passes with no failures.
- Verify commands: `DLR_TEST_PG_AUTOSTART=1 ... expose_migration_test.py` 21 passed, none skipped; full suite with local Postgres 1815 passed, and the default full suite 1755 passed, 60 skipped (the skips are the local-Postgres tests without the autostart flag), 0 failed.
- `git status --porcelain -- data/shadow .github/workflows/shadow_collect.yml` prints nothing.

---
*Phase: 06-exposure-e2e-verification*
*Completed: 2026-10-26*
