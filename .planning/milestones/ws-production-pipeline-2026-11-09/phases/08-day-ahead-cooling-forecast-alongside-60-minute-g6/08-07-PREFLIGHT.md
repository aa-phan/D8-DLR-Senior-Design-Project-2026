# Plan 08-07 Pre-flight: the day-ahead write side

Written 2026-11-08 by the executor. Nothing in this note or in the rehearsal touched the live Supabase project: no migration applied, no `.env` read, no network call to the project, nothing pushed. It holds no project URL, host, reference or key.

## 1. In plain English: what this step does and what you are deciding

**What gets applied.** One migration file, `20261108120000_day_ahead_forecast_store.sql`. It adds an empty, private table for day-ahead forecasts (`day_ahead_forecast`) and one private field on the run log (`pipeline_run.day_ahead`) where the hourly job will note how each city's day-ahead step went.

**Who can see it.** Nobody outside. The public keys (the ones the dashboard and PSS/E scripts will use) get no access at all to the new table yet. The only thing that can touch it is the hourly job's own database login, and that login is limited to reading and adding rows. It cannot change or delete a row it wrote, so a forecast, once issued, stays as issued.

**Does the live system change.** No. The hourly job does not use the table until the code is pushed in a later step (08-08). The existing rating table, the public `latest_rating` view and its 34-column contract are not touched.

**What I need from you before it is applied (the next step, Task 2).** Two things:

1. Confirm the names and column list in section 3. After the forecast is public, the dashboard team and the PSS/E team will write code against these names. Before it is public, changing one costs a single edit to a file that has not been applied. After it is public, renaming or dropping a column needs a new migration and a coordinated change with both teams. Adding a column at the end later stays cheap.
2. Confirm the rules in section 4. You decided the structure (a new table plus a new view, existing contract untouched) and the label wording. I chose the rest; each choice is written out in plain words so you can disagree with any of them.

You can reply `confirm`, or `revise: <what to change>`. A revise sends the work back to the earlier plans and the go-live waits.

**Not part of this step.** The two public read views (`day_ahead_upcoming`, `day_ahead_status`) are created later, in the separate expose migration (plan 08-09). They do not exist anywhere yet, local or live. Their column lists below come from the contract file, which the later migration must match.

## 2. Local rehearsal result

The migration set on disk and in git, checked before the owner is asked to push anything (the Supabase CLI applies every pending file it finds, so the set matters):

| Order | File | State |
|---|---|---|
| 1 | `20261019000000_create_city_rating.sql` | live (Phase 4) |
| 2 | `20261023000000_city_rating_utc_hour_check_and_run_log_comments.sql` | live (Phase 4) |
| 3 | `20261026195124_expose_latest_rating.sql` | live (Phase 6) |
| 4 | `20261026204258_soak_freshness_log.sql` | live (Phase 6) |
| 5 | `20261108120000_day_ahead_forecast_store.sql` | pending (08-01), the only one to apply |

Exactly five `.sql` files, all tracked in git, the write-side file last, and no expose migration for the day-ahead views anywhere in `supabase/migrations` (tracked or untracked). The first dry run must list exactly file 5. Anything else pending: stop and report.

Full suite on a throwaway local Postgres (`DLR_TEST_PG_AUTOSTART=1`, run from the repository root):

```
DLR_TEST_PG_AUTOSTART=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs
```

Result: **2894 passed, 0 failed, 0 skipped** (4 minutes 10 seconds). No skip reason appeared in the `-rs` list, so the local-Postgres tests all ran. In plain English, that includes: the migration applied to a fresh database, the table refusing every malformed row, the job's login being able to add and read rows but not change or delete them, the public roles being refused, and the new check file `supabase/ops/verify_day_ahead_store.sql` returning ok for all 10 checks.

## 3. The contract as built (the one-way part)

Source of truth: `backend/day_ahead_contract.py`. The migration writes the same columns in SQL and the tests fail if the two ever differ.

### The label and its paragraph (D-11, wording you approved)

The short, stable label every row carries is exactly:

`day-ahead-24h; engineering-selection; not-validated`

The plain-English paragraph for the contract documentation:

> A 24-hour-ahead estimate from ml_cooling_corrected. It has more error than the 60-minute forecast because it looks further ahead. On past data (TEST window, Mar-Sep 2026) its typical error was about 23 A (~1.7% of rating) larger. It is the owner's engineering choice, not picked by the signed selection rule, and it never sets or checks the live rating.

### The table `day_ahead_forecast`: 25 columns, in order

One row per city and target hour (that pair is the key). All currents are amperes per conductor.

1. `city` : which city (AUSTIN, CORPUS_CHRISTI, MIDLAND or EL_PASO).
2. `valid_time` : the target hour the forecast is for (UTC, always 00, 06, 12 or 18).
3. `issued_at` : the actual time the job issued the row; always before `valid_time`. A catch-up issue carries a later time than the first chance, so a late value is visible.
4. `forecast_run_init_time` : when the weather run behind the value started; always exactly 24 hours before `valid_time`.
5. `horizon_minutes` : age of that weather run at the target; always 1440.
6. `forecast_amps` : the day-ahead ampacity forecast.
7. `forecast_ci_lower_amps` : lower edge (5%) of the band around the forecast.
8. `forecast_ci_upper_amps` : upper edge (95%) of the band.
9. `band_source` : where the band came from, `test-split` (the launch band) or `live-rolling` (the forecast's own recent misses).
10. `band_n` : how many past misses sit behind the band.
11. `band_pairs_through` : for a live-rolling band, the target time of the newest past miss used; empty for a test-split band.
12. `band_artifact_sha256` : fingerprint of the launch band file; always recorded because it stays the fallback band.
13. `forecast_method` : always `ml_cooling_corrected`; no substitute method is ever published.
14. `cooling_model_sha256` : fingerprint of the cooling model file the value came from.
15. `cooling_model_source` : `refit` (the city serves its production-conductor refit) or `frozen` (the frozen shadow model).
16. `anchor_observation_time` : time of the station reading (the "now" reading) the correction used.
17. `anchor_source` : which provider supplied that reading (tceq or synoptic).
18. `label` : the label above.
19. `config_version` : the human-readable name of the rating assumption set.
20. `config_fingerprint` : fingerprint of the city's rating assumptions (same identity the rating rows carry).
21. `run_id` : the workflow run that issued the row.
22. `run_attempt` : that run's attempt number.
23. `pipeline_version` : short git commit of the pipeline code.
24. `schema_version` : row layout version; 1.
25. `first_written_at` : when the row was inserted (set by the database, never by the job; never changes).

### The public view `day_ahead_upcoming`: 26 columns (created later, plan 08-09)

The 25 columns above, in the same order, plus one more at the end: `lead_minutes` (minutes from now until the target hour). The view returns every future target that has a value.

### The public view `day_ahead_status`: 7 columns (created later, plan 08-09)

Always four rows, one per city: `city`, `checked_at`, `next_target_time`, `upcoming_count`, `newest_issued_at`, `missing_targets`, `is_late`.

### Added to the private run log

`pipeline_run.day_ahead` (a json field): per-city outcome of the day-ahead step and redacted reasons. Operational, never public.

### Safety rules built into the table itself

The database refuses a row that breaks any of these, so a bug cannot publish a malformed value: the target must be on the 00/06/12/18 UTC grid; the issue time must be before the target; the weather run must start exactly 24 h before the target; `horizon_minutes` must be 1440; the method must be `ml_cooling_corrected`; the forecast must be above zero and finite; the band must contain the forecast; a live-rolling band must name its newest past miss and a test-split band must not; the three fingerprints must be 64-character hex. The 1440 and method rules also mean that a future change (hourly issue at several leads, or a second method) fails loudly instead of silently overwriting a row; that would need a key change and a contract revision.

## 4. Claude's-discretion choices you are confirming

1. **Names.** The table is `day_ahead_forecast`; the public views will be `day_ahead_upcoming` and `day_ahead_status`; the private run-log field is `pipeline_run.day_ahead`; the writer's policy is `dlr_writer_all` (same name as the existing ones, scoped per table).
2. **Insert-only writer.** The job's database login can read and add rows but never change or delete one. If two runs race for the same target, the first one wins and the second does nothing (not an error). A bad value can only be corrected through an owner action with the admin login, never by the job.
3. **Amps only.** There are no megawatt columns. A consumer converts amps to MW the same way it does for `city_rating` (voltage and power factor), and the contract documentation will say how.
4. **Out-of-bounds values are published and logged, not withheld.** If a forecast falls outside the expected range, the row is still stored and the run logs a warning. The reason: the day-ahead value has no safety role (it never gates G6 and never sets the live rating), so hiding a surprising value would only hide information.
5. **The live band takes over per city and per target hour at 60 graded pairs.** Each of the 16 bands (4 cities times 4 target hours) starts on the launch band built from the TEST window. Once 60 forecasts for that city and hour have been graded against what the live rating later turned out to be, the band is rebuilt from the newest 120 such pairs (or all of them if fewer than 120). It switches only when that live band brackets zero (its 5% edge below zero and its 95% edge above it); otherwise it keeps the launch band. Each row records which band it used and how many pairs stood behind it.
6. **"Late" rule.** A city counts as late when a 6-hourly target due within the next 12 hours has no value. It is checked only once the city's first row exists, so the day before the first issue does not read as late.
7. **One child process per city, inside the existing 20-minute budget.** Each city's day-ahead step runs as its own process with a 150-second limit. A city reached with less than 60 seconds of the shared budget left is skipped and recorded as `skipped_budget` rather than started and killed. The shared budget is the existing 20 minutes (4 times the 300-second per-city rating limit), measured from the start of the run, so day-ahead can never delay the rating that gates G6 beyond what is already allowed.
8. **When a target is issued.** A target is issued from 18 hours before it until it starts (the weather provider's publication lag is about 6 hours, so the 24-hour-old run is available from T minus 18 h). A missed target is caught up by later hourly runs while it is still in the future. The first run after go-live therefore writes up to 3 targets per city (12 in all), not 4.
9. **Two times per row, and what "24 h" means.** Each row records `issued_at` and `anchor_observation_time`. "24 h" means the age of the weather run (always exactly 24 h before the target), not the lead from the moment the row was issued; a row is issued 0 to 18 h before its target. The anchor reading is therefore 24 h ahead of its target in the TEST data, about 12 h ahead in the shadow collection, and up to 18 h ahead live. The documentation will say so.
10. **The band artifact is a JSON file** in `data/day_ahead` (`day_ahead_bands_v1.json`, 16 bands). It is checked against a recorded fingerprint before it is read, and every row records that fingerprint.

## 5. What else the migration does, so nothing surprises you

- It is safe to apply twice: the table is created only if absent, the run-log field only if absent, and its policy is replaced rather than duplicated.
- It turns row-level security on for the new table and revokes all access from the two public roles (`anon`, `authenticated`). The expose migration later grants the public read, after the first issued rows have been checked.
- It comments every column with its unit first, so the Supabase table editor shows what each one means.
- It does not touch `city_rating`, `latest_rating`, or the existing exposure.

## 6. The owner's commands for Task 3

Only after you reply `confirm` to Task 2. All from `/Users/aphan/Senior_Design`. `.env` is loaded through python-dotenv because its `KEY = value` spacing cannot be sourced by a shell (Phase 4's recorded procedure). `<admin URL from .env>` stands for the admin session-pooler connection string already held in your git-ignored `.env` under `SUPABASE_ADMIN_DB_URL`; it is never pasted into a file or into chat.

1. Dry run. Expect exactly one pending file, `20261108120000_day_ahead_forecast_store.sql`. Anything else pending: stop and report.

```
.venv/bin/python -c "from dotenv import dotenv_values; import os, subprocess, sys; u=dotenv_values('/Users/aphan/Senior_Design/.env')['SUPABASE_ADMIN_DB_URL']; sys.exit(subprocess.run([os.path.expanduser('~/tools/supabase-cli/node_modules/.bin/supabase'), 'db', 'push', '--db-url', u, '--dry-run']).returncode)"
```

   (`u` is `<admin URL from .env>`; the command reads it itself.)

2. Push: the same command without `'--dry-run'`.

3. In the Supabase SQL editor run `supabase/ops/verify_day_ahead_store.sql`; every row must show ok = true (10 checks). Then run `supabase/ops/verify_exposure.sql`; every row must still show ok = true (nothing new is exposed). Copy both result tables.

4. Optional, recommended: prove the live weather and station chain for one city before the code push. This touches no database:

```
PYTHONPATH=backend .venv/bin/python backend/dlr_day_ahead.py --city AUSTIN --output /tmp/da_check.json --no-store
```

   It needs the provider tokens in your `.env`. Copy its outcome and the computed values.

5. Re-run the dry run from step 1. Expect nothing pending ("Remote database is up to date").

Then reply `applied` with the dry-run output, both SQL result tables, the optional no-store outcome and the second dry-run output; or describe what failed.

## 7. After the apply (executor, for the record)

The executor pins the applied file's sha256 in `backend/tests/day_ahead_migration_test.py` so the file is never edited again; any later fix goes in a new additive migration.
