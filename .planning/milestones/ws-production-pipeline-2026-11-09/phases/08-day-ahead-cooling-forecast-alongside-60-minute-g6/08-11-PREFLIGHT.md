# Plan 08-11 Pre-flight: expose the day-ahead feed and publish its contract

Written 2026-11-08 (8:45 PM US Central; 2026-11-09 02:45 UTC) by the executor. Nothing in this note or in the rehearsal applied a migration, read `.env`, contacted the live Supabase project, pushed, or installed anything. The only network call was `git fetch origin` (read-only). It holds no project URL, host, reference or key.

## 1. In plain English: what you are deciding

**What the step does.** Today the day-ahead forecast is written into a private table by the hourly job and nobody outside can read it. This step does three things, in this order:

1. You apply one migration file. After it, anyone holding the public (publishable) key can read the upcoming day-ahead values and a four-row status table, and the full history in the table. They can never change or delete anything.
2. The existing freshness alarm (the 15-minute check on cron-job.org that emails you) also starts watching the day-ahead feed. Same URL, same key, no new alarm job.
3. After the live checks and the live example runs pass, you push `main`. That publishes the consumer documents and the three updated example scripts for the Software team and the PSS/E team.

**What you are deciding (Task 2).** Whether to expose and publish now (`expose-and-publish`) or hold (`hold`). On hold, the feed keeps running privately, nothing public changes, and the alarm keeps ignoring the feed.

**Why this is a one-way door.** After this, the column names are something the dashboard team and the PSS/E team write code against. Renaming or dropping a column later needs a new migration, a revised contract and a coordinated change with both teams. Adding a column at the end stays cheap. You already confirmed this exact column set in 08-07 (reply `confirm`).

**What I (the executor) will not do.** Apply the migration, read your `.env`, call the live project, install anything, or push. You do all of that; I record the results afterwards.

## 2. Local rehearsal result

All of this ran on this machine only, at commit `cd68184` (HEAD of local `main`).

| Check | Result |
|---|---|
| Full suite on a throwaway local Postgres (`DLR_TEST_PG_AUTOSTART=1`, repository root, `-rs`) | **2999 passed, 0 failed, 0 skipped** (8 min 19 s). No skip reason appeared, so every local-Postgres test ran. That includes the expose migration applied to a fresh database, the two views and the extended alarm function, and the public roles being refused every write. |
| Migration files on disk | Exactly six `.sql` files, in order, expose file last (list below). |
| Migration files in git | The same six, all tracked (`git ls-files` equals the disk list). |
| `git diff 14eb365 -- backend/day_ahead_contract.py` | Empty (0 lines). No commit after `14eb365` touches the file, and it has no uncommitted change. |
| `git fetch origin` | Ran (read-only). `origin/main` is `1088392`. Local `main` is 22 commits ahead; none behind. |
| `git diff --name-only origin/main..HEAD -- .github/workflows` | Prints nothing: no workflow file changes in the push. |
| `~/dlr-js-check` (read-only look) | Exists. `package.json` pins `@supabase/supabase-js` at exactly `2.117.3`, and the installed package under `node_modules` reports version `2.117.3`. `supabase_js.mjs` there is the older Phase 6 copy; you replace it in Task 3 step 5(d). Nothing installed. |

Migration order (the Supabase CLI applies every pending file it finds, so the set matters):

| Order | File | State |
|---|---|---|
| 1 | `20261019000000_create_city_rating.sql` | live (Phase 4) |
| 2 | `20261023000000_city_rating_utc_hour_check_and_run_log_comments.sql` | live (Phase 4) |
| 3 | `20261026195124_expose_latest_rating.sql` | live (Phase 6) |
| 4 | `20261026204258_soak_freshness_log.sql` | live (Phase 6) |
| 5 | `20261108120000_day_ahead_forecast_store.sql` | live (08-07) |
| 6 | `20261108120100_expose_day_ahead_forecast.sql` | **pending, the only one to apply** |

**The contract is the one you confirmed.** Decision commit: `14eb365` (the commit holding `backend/day_ahead_contract.py` when you replied `confirm` in 08-07). The file is byte-identical to that commit, so you are not asked to re-confirm the columns.

**The order rule (D-17) holds.** 08-08 recorded the first issuing run (12 rows, every one of its 10 checks PASS, evidence in `08-08-first-slot.json`) before this migration is applied.

## 3. Exactly what becomes public

Read-only for `anon` (the public key) and `authenticated`. Nothing else is granted; every write stays refused by privilege.

**The table `public.day_ahead_forecast`** (25 columns, full history, past targets stay readable): `city`, `valid_time`, `issued_at`, `forecast_run_init_time`, `horizon_minutes`, `forecast_amps`, `forecast_ci_lower_amps`, `forecast_ci_upper_amps`, `band_source`, `band_n`, `band_pairs_through`, `band_artifact_sha256`, `forecast_method`, `cooling_model_sha256`, `cooling_model_source`, `anchor_observation_time`, `anchor_source`, `label`, `config_version`, `config_fingerprint`, `run_id`, `run_attempt`, `pipeline_version`, `schema_version`, `first_written_at`. A read policy named `day_ahead_forecast_public_read` is added.

**The view `public.day_ahead_upcoming`** (26 columns): the same 25 columns in the same order, for targets still in the future only, ordered by city then target time, plus one more at the end: `lead_minutes` (whole minutes from the moment of the request to the target, rounded up, at least 1).

**The view `public.day_ahead_status`** (7 columns, always exactly four rows, one per city): `city`, `checked_at`, `next_target_time`, `upcoming_count`, `newest_issued_at`, `missing_targets`, `is_late`. A city is late when a target due within the next 12 hours has no value and the table holds at least one row.

Every value carries the label `day-ahead-24h; engineering-selection; not-validated`, meaning: a higher-error, owner-selected forecast that has not been validated, and it never sets or checks the live rating.

**What stays private.** `pipeline_run` (the run log) stays hidden. `city_rating`, `latest_rating` and its 34 columns are not touched.

## 4. The alarm change

The alarm is the 15-minute check on cron-job.org that calls `rpc/assert_fresh` (runbook section 14). The URL and key are unchanged. The function keeps its signature and its 90-minute rating rule, and gains one clause:

- Before: it fails (HTTP 503) when a city has no rating or only an old one.
- After: it also fails (HTTP 503, detail `day_ahead_late=CITY@<UTC target>,...`) when a city has a day-ahead target due within the next 12 hours with no value. The success body gains `day_ahead_armed: true`.
- It is armed because the table already holds values (the first slot was verified in 08-08). A table that had never been written could not raise it.

**What this means for you.** A stalled day-ahead feed now sends the failure email after two failed checks. To avoid starting red, apply when the latest hourly run's step summary shows every city as `issued` or `none_due` in the day-ahead table. If a city shows another outcome, wait for the next run (they start about 5 minutes past each hour) and look again. Task 3's precondition is exactly this fact; I cannot check it from here without contacting live services.

## 5. What the final push publishes

The push is a fast-forward of 22 local commits. Only after the SQL checks, the REST check and the four live example runs pass. The files (outside `.planning/`) that go out:

- Consumer documents: `docs/integration/rest-api.md`, `docs/data-science/schema/day_ahead_forecast_v1.md`, `docs/data-science/decisions/pss_e_handoff.md`, `docs/integration/software-team-handoff.md`, `docs/frontend/specs/api-contract.md`.
- The three extended examples: `docs/integration/examples/curl.sh`, `read_ratings.py`, `supabase_js.mjs` (they now also read the day-ahead values).
- The migration file `supabase/migrations/20261108120100_expose_day_ahead_forecast.sql` and the generalised check `supabase/ops/verify_exposure.sql`.
- The runbook `docs/data-science/decisions/dlr_live_runbook.md`, the REST check `backend/day_ahead_verify.py`, and their tests.
- The planning records under `.planning/` for plans 08-08 to 08-12.

No workflow file changes, so the push cannot change what the hourly job does. Pushing the migration file applies nothing (no workflow applies migrations).

**Do not push before the checks pass.** The consumer documents describe views that do not exist live until step 2 of your commands below succeeds.

## 6. The owner's commands for Task 3

Only after you reply `expose-and-publish` to Task 2, and only after the precondition in section 4 holds. All from `/Users/aphan/Senior_Design`. `<admin URL from .env>` stands for the admin session-pooler connection string in your git-ignored `.env` under `SUPABASE_ADMIN_DB_URL`; it is never pasted into a file or into chat. `<project URL>` and `<publishable key>` stand for the Supabase project URL and the publishable key (never the secret key), exported in your shell only.

1. Dry run. Expect exactly one pending file, `20261108120100_expose_day_ahead_forecast.sql`. Anything else pending: stop and report.

```
.venv/bin/python -c "from dotenv import dotenv_values; import os, subprocess, sys; u=dotenv_values('/Users/aphan/Senior_Design/.env')['SUPABASE_ADMIN_DB_URL']; sys.exit(subprocess.run([os.path.expanduser('~/tools/supabase-cli/node_modules/.bin/supabase'), 'db', 'push', '--db-url', u, '--dry-run']).returncode)"
```

2. Push (apply): the same command without `'--dry-run'`.

3. In the Supabase SQL editor run `supabase/ops/verify_exposure.sql` (29 rows) and `supabase/ops/verify_monitoring.sql`. Every row must show ok = true. Copy both tables.

4. In your shell:

```
export SUPABASE_URL=<project URL>
export SUPABASE_PUBLISHABLE_KEY=<publishable key>
PYTHONPATH=backend .venv/bin/python backend/day_ahead_verify.py --check-rest --json-out .planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-11-live-checks.json
```

   Expect exit 0 and PASS on every check. If a read returns 404, wait a minute (the schema cache reloads) and run it again.

5. The three example scripts, same shell, from the repository root, each as written. Reply with the exit code and the first lines of each part, never the URL or key.
   - (a) `bash docs/integration/examples/curl.sh` : exit 0; four cities, a "total rows" line, the pages, then the two day-ahead sections (upcoming rows with the label, four status rows).
   - (b) `/usr/bin/python3 -I docs/integration/examples/read_ratings.py` : exit 0; four city lines, the history line, the day-ahead label line, at least one target line and four status lines.
   - (c) `.venv/bin/python -I docs/integration/examples/read_ratings.py --city AUSTIN` : exit 0, the same parts.
   - (d) Copy `docs/integration/examples/supabase_js.mjs` into `~/dlr-js-check` (outside the repository), then in that folder run `node supabase_js.mjs` : exit 0; the rating table, the history count, the day-ahead table with the label and the four-row status table. `~/dlr-js-check` already holds the supabase-js 2.117.3 install approved in 06-11 (confirmed above); nothing is installed in this step.

6. Re-run the dry run from step 1. Expect "Remote database is up to date."

7. Only if steps 3, 4 and 5 all passed: `git push origin main` (fast-forward). If a check or an example failed, do not push; reply with the failing lines.

Then reply `exposed and published` with the dry-run output, both SQL result tables, the REST check's PASS/FAIL lines, each example run's exit code and first lines per part, the second dry-run output and the push output; or describe what failed.

**If something goes wrong after step 2.** The views and grants are additive. A bad alarm clause would show as `assert_fresh` returning 503 with `day_ahead_late=...`; do not edit the applied migration, report it and a new additive migration fixes it. Nothing in this step changes the ratings or the hourly job.

## 7. Threats covered

- T-08-34 (exposing before the first slot is verified, or after a changed contract): 08-08 evidence all ok; contract diff against `14eb365` empty; the dry run must list exactly the expose file.
- T-08-36 (alarm starting red): apply only when the latest run shows every city issued or none_due.
- T-08-37 (URL or key in git): commands use stand-ins; the verifier redacts; the secret scan runs before the evidence commit.
- T-08-38 (applied migration edited later): a sha256 pin is added after the apply.
- T-08-45 (publishing examples that fail live): the push waits for exit 0 on all four example runs.
- T-08-SC (installs): none; the JS example reuses the existing 2.117.3 install.
