# Plan 06-09 Pre-flight: the live exposure

Written 2026-10-26 by the executor. Nothing in this note or in the rehearsal touched the live Supabase project: no migration applied, no `.env` read, no network call to the project, nothing pushed. It holds no project URL, host, reference or key.

## 1. Gate status (D-06)

`05-08-SUMMARY.md` exists and records the owner's sign-off of the Phase 5 window: **approve-push** (24 of 24 hourly slots ok, 96 rows, main pushed fast-forward, first scheduled run on the pushed workflow green in environment production). The live steps are therefore allowed to proceed, after the owner confirms the column list below (Task 2).

## 2. Pending migrations (exactly two, sorting after every Phase 4 file)

`git ls-files supabase/migrations` lists four tracked files. The first two are Phase 4's and are already live. The last two are the pending set, expose before soak log:

| Order | File | State |
|---|---|---|
| 1 | `20261019000000_create_city_rating.sql` | live (Phase 4) |
| 2 | `20261023000000_city_rating_utc_hour_check_and_run_log_comments.sql` | live (Phase 4) |
| 3 | `20261026195124_expose_latest_rating.sql` | pending (06-01) |
| 4 | `20261026204258_soak_freshness_log.sql` | pending (06-05) |

The owner's first dry run must list exactly files 3 and 4. Anything else pending: stop and report.

## 3. Local rehearsal result

Run on a throwaway local Postgres (every migration applied to a fresh cluster whose roles start with Supabase's legacy default grants, the worst case), plus the offline suites:

```
DLR_TEST_PG_AUTOSTART=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs \
  backend/tests/expose_migration_test.py backend/tests/soak_log_migration_test.py \
  backend/tests/e2e_readonly_test.py backend/tests/rest_api_doc_test.py \
  backend/tests/secret_scan_test.py
```

Result: **117 passed, 1 skipped, 0 failed.** The one skip is the owner-local exact-value secret scan (it needs the real URL and keys exported in a shell, which the executor must not have). What the suites cover, in plain English:

- `expose_migration_test.py` (21 tests): the public key reads exactly four rows from `latest_rating`; it is refused on every write and on the run log; the 90-minute rule agrees everywhere; `supabase/ops/verify_exposure.sql` returns ok = true for all 17 checks and each check can fail.
- `soak_log_migration_test.py` (24 cases): the soak log is invisible to the public key; `supabase/ops/verify_monitoring.sql` returns ok = true for all 7 checks; re-applying changes nothing.
- `e2e_readonly_test.py` (57 cases): the live-check script's read, hidden-table and write checks behave correctly against an in-process fake of the REST gateway, and never print a URL or key.
- `rest_api_doc_test.py`: the written API documentation matches the contract.
- `secret_scan_test.py`: no tracked file holds a project URL, host reference or key.

## 4. The published contract: 34 columns, in order

This is the list the React dashboard and the PSS/E scripts will build on. Source of truth: `backend/latest_rating_contract.py` (`LATEST_COLUMNS`), mirrored in the view and documented in `docs/integration/rest-api.md`.

Read straight from `city_rating` (31):

1. `city`
2. `valid_time`
3. `observation_time`
4. `rating_amps`
5. `rating_mw`
6. `static_rating_amps`
7. `static_rating_mw`
8. `line_voltage_kv`
9. `power_factor`
10. `status`
11. `fallback`
12. `fallback_gates`
13. `alerts`
14. `exhausted`
15. `forecast_method`
16. `forecast_status`
17. `forecast_amps`
18. `forecast_ci_lower_amps`
19. `forecast_ci_upper_amps`
20. `forecast_horizon_min`
21. `detector_signal`
22. `rating_basis`
23. `config_version`
24. `origin`
25. `run_id`
26. `pipeline_version`
27. `computed_at`
28. `config_fingerprint`
29. `forecast_model_sha256`
30. `anomaly_model_sha256`
31. `solar_source`

Computed when the request is made (3):

32. `age_minutes`
33. `is_stale`
34. `is_provisional`

Columns 1 to 27 are the originally planned set; 28 to 31 are the identity and source columns added by D-01 (they let a consumer see that a conductor or model changed between two rows).

### The three computed columns, in plain English

| Column | SQL as built | Plain English (decision) |
|---|---|---|
| `age_minutes` | `ceil(extract(epoch from (now() - valid_time)) / 60)::integer` | How many minutes old the rating is, rounded up: a started minute counts as a minute (D-02). A rating 90 minutes and 1 second old reads 91. |
| `is_stale` | `(valid_time < now() - interval '90 minutes')` | True only when the rating is more than 90 full minutes old. Exactly 90 minutes is still fresh (D-02, OD-4). It is a direct time comparison, so it can never disagree with `age_minutes > 90`. |
| `is_provisional` | `(position('provisional' in lower(rating_basis)) > 0 or position('provisional' in lower(config_version)) > 0)` | True while the word "provisional" (any capitalisation) appears in either label (D-03, revised 2026-10-25). It is true for every live and backfill row today, and it stays true until Phase 7's re-validation go removes the word from both labels. |

### Claude's-discretion choices you are confirming

- Rounding of `age_minutes`: round up (ceil), chosen so the number never contradicts the stale flag.
- Append order: the three computed columns come last, after the 31 stored ones.
- The word rule: either label counts, not just `rating_basis`, because live rows do not begin with the prefix a prefix test would look for.
- A fallback row (static rating published) still counts as the city's current row (D-04); the view never skips back to an older computed row.

### One-way note

Column names are the dashboard's and PSS/E's contract. Appending a column later is cheap. Renaming or dropping one needs a coordinated change with both consuming teams and a new view migration. That is why you confirm the list before it goes live.

## 5. What else the expose migration does (so nothing surprises you)

- Creates the `latest_rating` view (it runs with the caller's own rights) and the `assert_fresh` check that the permanent alarm calls.
- Removes every write right from the public roles on all current public tables, and keeps read-only access on exactly two objects: `city_rating` and `latest_rating`. `pipeline_run` stays hidden.
- Adds a read policy on `city_rating` (the second lock behind the privilege lock).
- The soak migration adds a private `ops` schema with `freshness_log` and `ops.log_freshness()`, reachable by neither public role. It schedules nothing; scheduling is plan 06-10.
- Carried note from 06-01: a future function created in `public` is executable by everyone by Postgres default. `verify_exposure.sql` has a check for that. If the live project already has other public functions, that check will show them.

## 6. The owner's commands for Task 3

All from `/Users/aphan/Senior_Design`. `.env` is loaded through python-dotenv because its `KEY = value` spacing cannot be sourced by a shell (Phase 4's recorded procedure). `<admin>` stands for the admin session-pooler connection string already held in your git-ignored `.env` under `SUPABASE_ADMIN_DB_URL`; it is never pasted into a file or into chat.

0. Before anything: make sure no backfill load (`backend/supabase_load_backfill.py`) and no manual re-run of a past slot is running. Either would change rows the write check snapshots and make it fail falsely.

1. Dry run (expect exactly the two Phase 6 files pending; add `'--dry-run'` after `u`):

```
.venv/bin/python -c "from dotenv import dotenv_values; import os, subprocess, sys; u=dotenv_values('/Users/aphan/Senior_Design/.env')['SUPABASE_ADMIN_DB_URL']; sys.exit(subprocess.run([os.path.expanduser('~/tools/supabase-cli/node_modules/.bin/supabase'), 'db', 'push', '--db-url', u, '--dry-run']).returncode)"
```

2. Push (the same command without `'--dry-run'`).

3. In the Supabase SQL editor run `supabase/ops/verify_exposure.sql`, then `supabase/ops/verify_monitoring.sql`. Every row must show ok = true. Copy both result tables.

4. In a shell at the main checkout, export `SUPABASE_URL` (project URL) and `SUPABASE_PUBLISHABLE_KEY` (the publishable key, never the secret key; the script refuses a secret key). Optionally:

```
.venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/secret_scan_test.py
```

   With the values exported, the exact-value scan then checks they appear in no tracked file.

5. Live checks:

```
.venv/bin/python backend/e2e_verify_readonly.py --check-read --check-hidden --check-writes --json-out .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-09-live-checks.json
```

   Expect exit 0, four city lines and PASS on every check. If a read returns 401, confirm the Data API is enabled and `public` is an exposed schema (Dashboard, Project Settings, Data API), then re-run.

6. Re-run the dry run from step 1. Expect nothing pending ("Remote database is up to date").

Then reply "applied" with both SQL result tables, the script's exit code and its PASS/FAIL lines, and the second dry-run output.

## 7. Timeline reminder (D-09)

The 72-hour soak clock should start by 2026-10-27T00:00Z so it ends before 2026-10-30. The soak starts only after this push and plan 06-10's scheduling step, so a "revise" answer to Task 2 delays it.
