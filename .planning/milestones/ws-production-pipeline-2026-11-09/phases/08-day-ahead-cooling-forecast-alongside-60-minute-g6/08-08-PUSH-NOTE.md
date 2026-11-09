# Plan 08-08 Push note: the day-ahead stage goes to live CI

Written 2026-11-08 by the executor. Nothing in this note or in the rehearsal pushed anything, read `.env` or contacted the live Supabase project. The only network call was `git fetch origin` (read-only). It holds no project URL, host, reference or key.

## 1. In plain English: what you are deciding

**What the push does.** After this push, the hourly job still rates the four cities exactly as it does today. Once it has finished rating, it also computes a day-ahead forecast of each city's ampacity (in amperes) and stores it privately, one row per city and target hour. If anything about the forecast goes wrong (a missing weather run, a corrupted forecast file, a database hiccup), the ratings, the 60-minute forecast and the job's green or red result do not change. A forecast that cannot be computed simply has no row, and the reason is recorded in the run log.

**Who can see the forecasts.** Nobody outside. The table was created private in step 08-07 and stays private until a later, separate step (the expose migration, 08-09). The push is safe in this order because the table already exists.

**What I need from you.** A reply of `approve-push` or `hold`. Standing rule: I ask before pushing anything that changes live CI. I do not push; you do.

**If you hold.** Nothing changes in live CI. The go-live and the expose step wait.

## 2. What goes live

- The runner (`backend/dlr_live_run.py`) gains a day-ahead stage that starts only after the ratings are finished and the exit code is fixed. It runs one small program per city (`backend/dlr_day_ahead.py`), in the usual city order, inside the same time budget the ratings share.
- The pre-flight check (`backend/dlr_live_check_models.py`) gains a warning-only tier: if a day-ahead file is missing or does not match the manifest, it warns; it never fails the run.
- The live manifest (`data/models/LIVE_ARTIFACT_HASHES.sha256`) grows from 8 to 13 entries. The five new ones are the day-ahead band file and the four cooling models the day-ahead stage serves (one refit model for AUSTIN, three shadow models for CORPUS_CHRISTI, EL_PASO and MIDLAND). The eight existing entries (the four forecast and four anomaly models) are unchanged.
- The band file `data/day_ahead/day_ahead_bands_v1.json` is added. It gives each forecast a 5 to 95 percent range, built from the TEST split, as a starting estimate.
- The run log can now record a private `day_ahead` note per run (the column already exists live from 08-07); the older rating-stage writes do not send it.
- A separate day-ahead table appears in each run's GitHub step summary, with its own "pipeline_run day_ahead: N writes, M failed" line.
- The read-only first-slot checker (`backend/day_ahead_verify.py`), the runbook section 17 and the new tests ride along. They run nowhere in CI.
- Also in the range, not part of this stage: protocol v4 read-2 evidence (documents and 34 evaluation files under `data/shadow/evaluation/v4-read2`) and a signed-protocol gate on the offline ablation command. Neither runs in the hourly job.

## 3. What does not change

- The ratings: `city_rating` and `latest_rating`, and the four city rows of each run.
- The 60-minute (G6) machine-learning forecast.
- The job's exit code: it is fixed before the day-ahead stage starts, so the stage cannot change it.
- Both workflow files. `git diff --name-only origin/main..main -- .github/workflows` prints nothing (checked). `.github/workflows/dlr_live.yml` and `.github/workflows/shadow_collect.yml` are untouched, and so are the other two workflow files.
- The database. The one migration in the range (`20261108120000_day_ahead_forecast_store.sql`) was already applied live in 08-07; pushing the file applies nothing, because no workflow applies migrations.
- One small side change worth knowing: `backend/supabase_smoke.py` (run by the smoke-test workflow) now limits one policy lookup to the two tables it meant to check. It is the same answer, asked more precisely.

## 4. What was rehearsed, and at which commit

Rehearsal commit (the last code change; nothing but this note is added after it): `38f438fc488b0759fdb9b7c4d399c63bef85f0b9` (`38f438f`, "docs(08-07): update state and roadmap").

The commit you will push is the commit that holds this note, one docs-only commit on top of `38f438f`. A file cannot contain its own commit's SHA, so that SHA is given to you in the hand-off message and is what `git rev-parse HEAD` prints before you push. It differs from `38f438f` by this one file only; confirm with:

```bash
git diff --name-only 38f438f HEAD
```

Expected output: exactly one line, the path of this note. If it prints anything else, do not push.

Results at `38f438f` (the note commit changes no code or test, and the cheap checks were repeated at the note commit; see section 8):

| Check | Result |
|---|---|
| Full suite, `DLR_TEST_PG_AUTOSTART=1 pytest -q -p no:cacheprovider -rs` | 2895 passed, 0 failed, 0 skipped, exit 0, 252 s |
| Golden tests (`-k golden`) | 16 passed |
| D-03 parity tests (`day_ahead_forecast_test.py -k parity`) | 4 passed, 42 deselected |
| Secret scan (`secret_scan_test.py`) | 5 passed, 1 skipped (the owner-local check that needs your keys exported in a shell) |
| `git fetch origin` | ran (read-only); `origin/main` is `b6e910f` |
| `git merge-base --is-ancestor origin/main main` | exit 0: fast-forward, nothing to merge |
| `git diff --name-only origin/main..main -- .github/workflows` | prints nothing |

## 5. The commit range

`origin/main..main` is 55 commits at `38f438f` (56 with this note), from `b6e910f` (2026-11-03) to the pushed commit. None is a merge. In groups (28 + 11 + 16 = 55):

- Phase 8 plans 08-01 to 08-07, the part that goes live (28 commits, counting their summary and state commits): 08-01 compute and tracer (`14eb365`, `39d874b`), 08-02 stage and run-log column (`06164ee`, `405eda1`), 08-03 band (`9c620cf`, `8a59547`), 08-04 per-city child and write-side migration (`0f7c0fc`, `847044f`, `3013e23`), 08-05 manifest and pre-flight tier (`87b30cd`, `bb82450`), 08-06 first-slot checker and runbook (`42a12c7`, `c15b78e`), 08-07 migration pin (`ca352ed`, `b8db2cb`), plus their summary and state commits.
- Phase 8 planning documents (11 commits): context, research, validation, the 12 plans and their fixes.
- Phase 7 closeout (16 commits): v4 selection read-2, review, security and verification documents, the signed-protocol gate (`3aa7bf4`, `b15d389`).

Diffstat: 105 files, 36,459 insertions, 82 deletions. By area: 27 files under `backend` and `supabase` and the runbook (6,362 insertions, 39 deletions, the code that goes live plus its tests), 38 planning documents, 34 shadow evaluation data files (additions only), 4 decision documents, 2 data files (the band file added, the manifest edited).

## 6. When the first values appear

The hourly job is started by cron-job.org at minute 05 of every hour (UTC). The first run that starts after your push runs the new code. It issues every day-ahead target that is due at that moment, up to 3 per city and 12 in all (targets are the 00, 06, 12 and 18 UTC hours; one becomes due 18 hours before it).

Central time is UTC minus 6 hours now (standard time since 2026-11-01). Examples of the first run after a push:

| You push at (UTC) | You push at (US Central) | First run with day-ahead values (UTC) | First run (US Central) |
|---|---|---|---|
| 23:40 on Nov 8 | 5:40 PM on Nov 8 | 00:05 on Nov 9 | 6:05 PM on Nov 8 |
| 00:20 on Nov 9 | 6:20 PM on Nov 8 | 01:05 on Nov 9 | 7:05 PM on Nov 8 |
| 14:30 on Nov 9 | 8:30 AM on Nov 9 | 15:05 on Nov 9 | 9:05 AM on Nov 9 |

A push in the minutes just before hh:05 can miss that run by seconds; a run already started when you push keeps the old code. Give GitHub a minute or two after the run starts to finish, then check the Actions page before running the check below. Write down your push time in UTC (for example `date -u` right after the push).

## 7. Rollback

If the day-ahead stage misbehaves, the ratings are not affected, so there is no emergency. To stop it:

1. `git revert --no-edit 405eda1` (the commit that adds the stage to the runner; it is the only commit in the range that touches `backend/dlr_live_run.py`, so the revert does not collide with later edits). The per-city program, the band file and the checker stay in the repository, unused.
2. Run the suite, then ask for approval and push after it. A revert is a normal fast-forward commit.
3. The write-side table can stay. It is private, empty or holding a few rows, and nothing reads it.

Rows already written are never rewritten or deleted by the code (the hourly job's login can only add rows). Nothing is exposed, so nothing needs hiding.

## 8. Your commands for Task 3 (after you approve)

These use stand-ins only; you fill in the times.

1. From the main checkout, confirm the commit and push:

   ```bash
   cd /Users/aphan/Senior_Design
   git status --short | head      # your usual untracked files are fine; nothing under backend, data or supabase should be modified
   git rev-parse HEAD             # must equal the SHA in the hand-off message
   git diff --name-only 38f438f HEAD
   git push origin main           # a fast-forward; if refused, stop and report
   date -u                        # write down the push time in UTC
   ```

2. Wait for the next run (minute 05 UTC) to finish. In GitHub Actions confirm the run is green and that its step summary shows the usual four-city rating table plus the new day-ahead table. Copy the day-ahead table and the run id.
3. Run the read-only first-slot check (needs `SUPABASE_DB_URL` in your git-ignored `.env`; it reads inside one read-only transaction and rolls back):

   ```bash
   PYTHONPATH=backend .venv/bin/python backend/day_ahead_verify.py --check-store --since <PUSH_TIME_UTC, e.g. 2026-11-09T14:30:00Z> --json-out .planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-08-first-slot.json
   ```

   Expect exit 0 and PASS on every check. Exit 1 means a check failed; exit 2 means a missing `SUPABASE_DB_URL` or a bad `--since`.
4. Reply `pushed and verified` with the push time (UTC), the run id, the day-ahead table and the script's PASS or FAIL lines. If a check fails, do not continue to the expose step; reply with the failing lines. Nothing is exposed in that case and a gap-closure plan follows.

## 9. Repeat checks at the note commit

After this note is committed, the executor repeats at the note commit: the parity tests, the golden tests, the secret scan (this note is under the scanned tree), `git merge-base --is-ancestor origin/main main`, the workflow-diff check, and `git diff --name-only 38f438f HEAD` (exactly this file). The result is in the hand-off message. The full 2895-test suite is not repeated, because the only difference from the rehearsed commit is this document.
