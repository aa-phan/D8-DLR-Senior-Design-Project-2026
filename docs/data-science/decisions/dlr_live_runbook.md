# DLR Live Ratings Runbook

**Status: production path (production-pipeline Phase 5). Operating this workflow writes hourly ratings
for the four cities into Supabase. It never touches Shadow Collection.**

This is the operating reference for `.github/workflows/dlr_live.yml` and the cron-job.org job that
starts it: how it is triggered, what one run does, where the results go, how to pause, change,
drill and check it, and what it costs in GitHub Actions minutes. It is deliberately commands and
settings, not rationale; the rationale is in the Phase 5 plans and `REQUIREMENTS.md`. Nothing here
holds a secret value: tokens and keys live in cron-job.org and in GitHub's Actions secrets, never in
this repository.

Last updated 2026-10-26 (plan 06-07: the permanent freshness alarm, soak monitoring and the
post-2026-10-30 permission re-check, sections 14 to 16). Earlier: 2026-10-26 (plan 05-08: measured
Actions minutes for a full 24 h of hourly live runs and the same day of shadow runs, section 12). Earlier: 2026-10-24 (plan 05-06: owner's Actions quota recorded
in section 12; the repository was made public the same day, so Actions minutes are free going forward).

## 1. Purpose and scope

Every hour the workflow rates the four cities in `config.LOCATIONS` (`AUSTIN`, `CORPUS_CHRISTI`,
`MIDLAND`, `EL_PASO`) and writes the results to Supabase: one row per city in `public.city_rating`
and one row per run in `public.pipeline_run`.

It is a separate workflow from Shadow Collection (`shadow_collect.yml`). It has its own concurrency
group, its own trigger job and its own token. It does not read or write `data/shadow/`, the shadow
modules or the shadow runbook, which stay frozen until the 2026-11-24 confirmation run.

Owner decisions this runbook relies on, by number (`REQUIREMENTS.md`, "Owner decisions"):

| Decision | What it fixes here |
|---|---|
| OD-1 | Hourly cadence |
| OD-2 | Composed weather providers (`SYNOPTIC_TOKEN`, `NREL_API_KEY`, `NREL_API_EMAIL`) |
| OD-3 | ML forecast on the live path; a run without the ML forecast or an anomaly model is red |
| OD-7 | `valid_time` is the hour-truncated UTC slot of the run's window end; a second run in the same hour overwrites that hour's rows |
| OD-9 | A city that fails outright writes no rating row; the failure is recorded in `pipeline_run` only |
| OD-10 | The eight per-city model files are committed to git; there is no model storage elsewhere |

## 2. Trigger (cron-job.org)

The workflow has no GitHub `schedule:` trigger. GitHub's own scheduler started shadow runs 3 to 8
hours late, so the hourly start comes from a cron-job.org job that calls the workflow's `dispatches`
endpoint, the same mechanism Shadow Collection has used since 2026-10-15. Manual runs from the Actions
tab still work because `workflow_dispatch` is the only trigger.

Job settings in cron-job.org:

| Setting | Value |
|---|---|
| URL | `https://api.github.com/repos/aa-phan/D8-DLR-Senior-Design-Project-2026/actions/workflows/dlr_live.yml/dispatches` |
| Method | POST |
| Header `Accept` | `application/vnd.github+json` |
| Header `Authorization` | `Bearer <the fine-grained token, entered in cron-job.org only>` |
| Header `X-GitHub-Api-Version` | `2022-11-28` |
| Body | `{"ref":"main"}` |
| Expected result | HTTP 204 with an empty body (GitHub accepted the dispatch) |
| Schedule | `5 * * * *`, time zone set to UTC |
| Notifications | failure notifications on |

The scheduled body never carries `inputs`. `"inputs":{"fault_city":"MIDLAND"}` is added only for a
drill (section 8).

**Why minute 05.** The shadow job fires at minute 00 of its hours, so the live job never starts in the
same minute as a shadow run. The runner floors its window end to 5 minutes, so a run dispatched at
hh:05 has end hh:05 and slot hh:00. The two workflows use different concurrency groups (`dlr-live`
and `shadow-collection`), so they may overlap in time without blocking each other. Observation, not
a change request: the shadow runbook lists its times as 00/06/12/18 UTC, while `gh run list` shows
its recent runs created at 05, 11, 17 and 23 UTC (minute 00); that does not affect minute 05.

**The token.** A fine-grained personal access token owned by the repository owner:

- Resource owner: the repository owner; "Only select repositories": this repository only.
- Repository permission "Actions": read and write. Nothing else.
- An expiry date, with a calendar reminder set before it. An expired token makes every dispatch fail
  and nothing in the repository reports it (section 11).
- Separate from the shadow job's token, so either can be revoked alone.
- Stored only in cron-job.org. It is never written in this repository, in a workflow, in a `.env`
  or in a message.

**What is recorded here and what is not.** Recorded: the URL, method, headers by name, body, expected
status, schedule and token scope above. Not recorded, by design: the token, its value, its expiry
date and the cron-job.org account details.

## 3. Secrets

Four repository secrets are required, added under Settings, Secrets and variables, Actions. The
runner stops before starting any city if one is unset or empty, and logs the names only.

| Secret | What it is for |
|---|---|
| `SYNOPTIC_TOKEN` | Synoptic station observations (OD-2). The same secret Shadow Collection uses |
| `NREL_API_KEY` | NSRDB solar data (OD-2) |
| `NREL_API_EMAIL` | The email NSRDB requires with the key |
| `SUPABASE_DB_URL` | Phase 4's writer connection: the session pooler URL (port 5432) for the `dlr_writer` role, which has SELECT, INSERT and UPDATE on the two tables and nothing else |

`gh secret list` shows secret names only, never values. To check that all four exist without reading
anything sensitive, run it and look for the four names.

## 4. What one run does

Steps, in order (`.github/workflows/dlr_live.yml`, job `rate`, runner `ubuntu-latest`):

1. Checkout `main`.
2. Python 3.12 with the pip cache (it cuts billed minutes at an hourly cadence).
3. Install `requirements.txt`.
4. Model pre-flight (`backend/dlr_live_check_models.py`, no secrets): fails the run before any city is
   rated if one of the eight model files is missing, differs from its recorded SHA-256 or will not load.
   It also checks the four day-ahead cooling files and the day-ahead band artifact (section 9), as
   warnings only (D-13a): a problem there prints a `::warning::` line, never turns the run red and never
   stops a rating. Only the eight live models can fail the pre-flight.
5. Run `backend/dlr_live_run.py`: one `dlr_orchestrator.py` child process per city, one after another in
   `config.LOCATIONS` order, all sharing one window end. Each child rates its city with the composed
   providers and the ML forecast and writes its own rating row. Each child has a hard budget of
   `CITY_TIMEOUT_S` = 300 s and is killed at that point.
6. After the ratings and the exit code are settled, the day-ahead stage runs (section 17). It
   publishes a separate day-ahead forecast table, never sets or checks a rating and never changes the
   exit code. From Phase 8 on, `finished_at` in the run log means "the ratings finished": the
   day-ahead stage runs after it and records its own outcome in `pipeline_run.day_ahead`.

**Timeout.** `timeout-minutes: 30`. At the cap, 4 cities x 300 s = 1200 s (20 minutes) of children plus
at most 10 minutes for checkout, install, the pre-flight and the run-log writes. That is shorter than
the 60-minute cadence, so a run cut off at its timeout never overlaps the next slot. A healthy run
takes a few minutes.

**Concurrency.** Group `dlr-live`, `cancel-in-progress: false`. At most one run executes and one
waits. A newer waiting run replaces an older waiting one, and GitHub shows the replaced run as
cancelled. A run in flight is never cancelled.

**City outcomes** (the runner's record per city):

| Outcome | Meaning | Rating row |
|---|---|---|
| ok | The child exited 0, left an output file with a summary row for the city, and that row says the rating row was written | written |
| error | The child failed, or produced no usable result | none confirmed (OD-9) |
| timeout | The child outlived 300 s and was killed | none confirmed (OD-9) |
| degraded | An ok child whose ML forecast failed, that ran with no anomaly model, or whose history could not be cleaned | written |

`degraded` is decided by health: `forecast_status` must be `ok` or `cold_start`, an anomaly model
must have loaded and the history must have cleaned (no `cleaning_error`). A missing
`forecast_status` counts as degraded.

"None confirmed" means the runner has no evidence of a written row. A child writes its rating inside the
per-city loop and can still exit non-zero afterwards (a failing report print or `--output` dump, or a hang
at shutdown that hits the time budget), so an `error` or `timeout` city may occasionally have a stored row
that the run log does not know about. The slot is red either way, so no gap is hidden.

**Exit codes of `dlr_live_run.py`:** 0 when every city is ok and healthy; 1 for anything else (a city
errored, timed out or was degraded, or a `pipeline_run` write failed), which turns the Actions run
red; 2 for a usage error such as an unknown `--fault-city`. The other cities always still run.

The step summary of each run lists every city (outcome, rating, fallback, written, forecast status,
anomaly model, fault, redacted error) and a `pipeline_run: N writes, M failed` line.

## 5. Where results go

**`public.city_rating`.** One row per city and slot. `valid_time` is the hour-truncated UTC slot of the
run's window end (OD-7). A second run in the same hour (a manual run, a drill, a re-run) overwrites that
hour's rows for the cities it rates; `first_written_at` never changes. `run_id` is the workflow run id
(`GITHUB_RUN_ID`) and `run_attempt` its attempt number. A failed city writes no rating row (OD-9), so
the previous hour's row stays the latest one for that city.

**`public.pipeline_run`.** One row per run, keyed by `run_id` alone (the attempt is not part of the key).
Only the runner writes it; the children run with `--no-run-row`. It is inserted before the first city
starts, updated after each city and finished at the end:

- `finished_at` null means the run did not finish, for example the job timeout killed it. It is the
  moment the ratings finished; the day-ahead stage (section 17) runs after it.
- `cities_ok`: the cities whose row was written with a healthy ML path, in `config.LOCATIONS` order.
- `cities_failed`: an object per other city with `outcome` (`error`, `timeout` or `degraded`),
  `written`, `exit_code`, `duration_s`, `forecast_status`, `forecast_error`, `detector_model_loaded`,
  `cleaning_error`, the redacted `error` and `fault_injected`. The schema document lists all three
  outcomes; the stored column comment still lists only `error` and `degraded` until an additive
  migration updates it (Phase 6, with IN-11).
- `provider_errors` and `sources`, keyed by city.
- The table is not readable with the public key; read it with the owner's database connection or the
  Supabase SQL editor.

Limitation: a city whose history cleaning failed but whose forecast was fine reads as healthy in this
log, because the orchestrator's summary does not export the cleaning error.

Two read-only example queries:

```sql
-- latest runs
select run_id, run_attempt, window_end, finished_at, cities_ok, cities_failed
from public.pipeline_run
order by window_end desc
limit 24;

-- failed cities in the last 24 hours
select p.window_end, f.key as city, f.value ->> 'outcome' as outcome, f.value ->> 'error' as error
from public.pipeline_run p, jsonb_each(p.cities_failed) as f
where p.window_end > now() - interval '24 hours'
order by p.window_end desc, f.key;
```

## 6. Pause and resume

**Pause.** Disable the cron-job.org job. That stops new runs at the source. A run already in flight
finishes. To also block manual dispatches, open the Actions tab, DLR Live Ratings, the "..." menu, and
choose Disable workflow. If the workflow is disabled while the cron-job.org job is still enabled,
cron-job.org receives errors and may disable its own job after repeated failures; check its state
after resuming.

**Pausing the pipeline also pauses the freshness alarm (section 14).** Switch off the cron-job.org job
named "DLR freshness alarm" at the same time as the dispatch job. A paused pipeline writes no new
ratings, so within 90 minutes every city is stale and the alarm would fail on every check. It would
email once, then keep failing, and cron-job.org disables a job that fails more than 25 times in a row
(about 6.5 hours at 15 minutes); a disabled alarm stays off until someone switches it back on.

**Resume.** Re-enable the cron-job.org dispatch job (and the workflow, if it was disabled). Nothing
needs to be reset: there is no state outside the database. Resuming re-enables both jobs: switch the
freshness alarm back on too, then check that the alarm job is enabled and that its next execution
answers HTTP 200 once the first new hourly rating has landed (an alarm switched on earlier fails until
then). Missed slots are not back-filled. The gap stays in `city_rating` until it is filled by hand with
a local run for that slot (section 8), and the freshness alarm (section 14) will fire while the newest
rating is older than 90 minutes.

## 7. Change cadence

Edit the cron-job.org schedule only; the workflow does not contain a schedule. Cadence is OD-1, and
OD-4's freshness limit is one cadence plus 30 minutes (90 minutes at hourly), so a change revisits OD-1
and OD-4 with the owner, and the minutes table in section 12 is recomputed. A cadence faster than hourly
overwrites the same hour's rows (OD-7), so it adds cost without adding rows.

Returning to GitHub's own scheduler is not recommended (it started shadow runs 3 to 8 hours late). It
would mean adding a `schedule` trigger to `dlr_live.yml`, updating
`backend/tests/dlr_live_workflow_test.py` (which pins the workflow as dispatch-only) and disabling the
cron-job.org job so runs are not doubled.

## 8. Manual runs and drills

**Manual run.** Actions tab, "Run workflow", or

```bash
gh workflow run dlr_live.yml --ref main
```

**Fault drill.** Proves the failure path end to end: one city runs with blank provider credentials, so
it fails, the run turns red, and the other three cities still write.

```bash
gh workflow run dlr_live.yml --ref main -f fault_city=MIDLAND
```

Dispatch a drill at least 15 minutes before the next hh:05, so it finishes before the scheduled run
starts. The drilled city has no rating row for that run (OD-9) and appears in `cities_failed` with
`fault_injected` true. The input is checked against `config.LOCATIONS` and reaches the runner only
through an environment variable, never a shell script.

**Re-run jobs.** "Re-run jobs" in the Actions tab keeps the run id and increments `run_attempt`. The
re-run uses the current time for its window end, so a re-run in a later hour writes the later slot. It
replaces that run's `pipeline_run` row (same `run_id`, new `run_attempt` and `started_at`).

**Local run (owner only).**

```bash
PYTHONPATH=backend .venv/bin/python backend/dlr_live_run.py
```

It loads `.env` and, when `SUPABASE_DB_URL` is set there, writes production rows. `--end
2026-10-24T14:05:00Z` rates a chosen past window end and so writes that slot (how a missed slot is
filled by hand; a future end is refused); `--cities MIDLAND` limits the cities; `--no-run-log` skips the `pipeline_run` row (the
scheduled workflow never passes it) but still writes rating rows.

## 9. Models (OD-10)

The live ML forecast and anomaly models are eight files under `data/models/`
(`forecast_{CITY}.joblib` and `anomaly_{CITY}.joblib` for the four cities), committed to git through a
`.gitignore` carve-out. `data/models/LIVE_ARTIFACT_HASHES.sha256` holds their SHA-256 hashes. Every other
file under `data/models/` stays ignored.

**Promoting a retrained model.** Retrain offline, validate as in Phase 3, then:

```bash
PYTHONPATH=backend .venv/bin/python backend/dlr_live_check_models.py --write-manifest
```

Commit the changed `.joblib` files and the regenerated manifest together, and push with the owner's
approval. A binary committed to git stays in its history. The pre-flight fails the run when the files and
the manifest disagree, so an unpromoted retrain (files changed, manifest not) turns every run red before
any city is rated. Running `backend/dlr_live_check_models.py` with no argument performs the same check
locally.

**The 13 manifest entries.** Since Phase 8 the manifest lists thirteen files, in three groups:

| Group | Entries | Pre-flight tier |
|---|---|---|
| Live models (8) | `forecast_{CITY}.joblib` and `anomaly_{CITY}.joblib` for the four cities | Fatal: a problem fails the run before any city is rated |
| Day-ahead cooling models (4) | The served `ml_cooling_corrected` file of each city: the AUSTIN refit file under `data/models/conductor_refit/` and the three frozen files under `data/shadow/models/` | Warning only |
| Day-ahead band (1) | `data/day_ahead/day_ahead_bands_v1.json`, the launch band artifact | Warning only |

The day-ahead child checks the hash of a cooling file and of the band artifact itself before it loads or
parses them, and publishes nothing for a target whose file does not match (section 17). The warning tier
is the early notice.

**Promoting a later conductor refit (D-13).** If the Power Systems team answers with a different
conductor for a city, the day-ahead forecast follows only through this step, never by itself:

1. Refit that city's cooling model as in Phase 7.
2. Bump `DAY_AHEAD_REFIT_VERSION` in `backend/day_ahead_forecast.py` together with the refit, so the
   served path points at the new refit folder.
3. Regenerate the manifest with `PYTHONPATH=backend .venv/bin/python backend/dlr_live_check_models.py --write-manifest`.
4. Run the day-ahead tests (`backend/tests/day_ahead_forecast_test.py`, `dlr_day_ahead_test.py`,
   `dlr_live_check_models_day_ahead_test.py`).
5. Ask the owner before pushing, as for any model promotion.

After a config or model change the live band starts again from the launch band: a graded pair counts only
when its forecast and the rating it is compared with share the same `config_fingerprint` and the same
cooling model sha256, so the 60-pair count for the live band restarts from zero.

## 10. NSRDB

NSRDB is skipped for windows in the current UTC year: `NSRDB_SKIP_YEARS_BEFORE_CURRENT = 0` in
`backend/observation_composer.py`. NSRDB publishes a year only after it ends, so a current-year window
would always fail; skipping it makes no request, records no error and does not count towards the circuit
breaker, and solar comes from Open-Meteo. Early in a year, if NSRDB has not yet published the previous
year, set the constant to 1 so the previous year is skipped too, and set it back to 0 once it has.

## 11. Failure modes and alerting

| What happens | What you see | Backstop |
|---|---|---|
| A run is red (a city errored, timed out or was degraded, a `pipeline_run` write failed) | The Actions run is red and GitHub's failure notification goes to the account that owns the dispatch token, per its notification settings. The step summary and `cities_failed` name the city | Section 13 counts red runs as visible |
| A dispatch fails, for example an expired token | Nothing starts and nothing in the repository reports it | cron-job.org failure notifications |
| The cron-job.org job is disabled, misconfigured or its token has expired | No run starts and nothing in the repository reports it | cron-job.org failure notifications and the freshness alarm (section 14): a city whose latest `valid_time` is older than 90 minutes |
| Supabase free-tier pause | Every child fails to connect; red runs | Unpause the project in Supabase, then confirm with the next run |
| A model file is missing or altered | The pre-flight fails and the run is red before any city is rated | Section 9 |
| GitHub Actions minutes exhausted | No workflow in the account starts. Not expected while the repository is public (hosted-runner minutes are free); it applies again if the repository is made private | Section 12 |

The runner records a failed city and carries on; no rating row is ever invented for it (OD-9).

## 12. GitHub Actions minutes (SCHED-02)

**Update 2026-10-24: the repository is now public, so the overage projection below no longer applies
going forward.** On 2026-10-24 the owner made the repository public
(https://github.com/aa-phan/D8-DLR-Senior-Design-Project-2026) to remove the Actions-minutes cost.
Actions minutes on GitHub-hosted runners are free for public repositories, so hourly live runs and
Shadow Collection no longer draw on the 2,000 included minutes or incur overage from that point. The
figures and projections in the rest of this section are kept as history: they are what the owner
measured and what the decision to go public was based on. They describe a private repository and do not
describe the account's billing once the change is in effect. Minutes already billed this cycle (about
1,028 overage minutes, $6.17) are not refunded by the change. Re-read the Billing page after the first
full day of live runs to confirm that Actions usage stopped growing; that confirmation is not recorded
yet (on 2026-10-26 `gh` could not read billing without the `user` scope, so the Billing page is still the
owner's check).

**Security posture of a public repository.** The things that matter now:

- `dlr_live.yml` is `workflow_dispatch`-only. Only users with write access to the repository can
  dispatch it, from the Actions tab, the CLI or the cron-job.org token (scoped to Actions read and write
  on this repository only, section 2). It has no `pull_request`, `push` or `schedule` trigger, so a
  pull request or a push from outside cannot start it.
- Repository secrets (`SYNOPTIC_TOKEN`, `NREL_API_KEY`, `NREL_API_EMAIL`, `SUPABASE_DB_URL`) are not
  passed to workflows triggered by pull requests from forks, and this workflow does not run on pull
  requests at all.
- The `rate` job runs only on `main` (`if: github.ref == 'refs/heads/main'`) and in the `production`
  environment (T-04-38), as does `supabase_smoke.yml`. The environment's deployment-branch rule allows
  `main` only, so a branch that edits a workflow cannot reach the writer secret. Set up in GitHub
  (Settings, Environments): environment `production`, deployment branches "Selected branches" with
  `main`, and an environment secret `SUPABASE_DB_URL` holding the same `dlr_writer` URL as the
  repository secret. An environment secret takes precedence over the repository secret of the same
  name. Delete the repository-level `SUPABASE_DB_URL` only after a live run in the environment is green;
  until then it is the fallback.
- Everything committed is now public and stays public in history: the eight per-city model files under
  `data/models/` (section 9), the data, the planning documents and the code. A scan of all 904 commits
  of history for credential patterns (database URLs with passwords, Supabase and JWT keys, GitHub
  tokens, cloud-provider and AI-provider keys, NREL and Synoptic token assignments) and for committed
  `.env` files found nothing before the change. Never commit a secret; rotating it is the only remedy
  once it has been pushed to a public repository.
- Workflow logs of a public repository are public. The runner redacts errors and logs secret names
  only; do not add steps that print environment values.

Hourly runs cost many more minutes than Shadow Collection when the repository is private. Billed
minutes per month (private-repository basis, kept as history):

    runs per day x billed minutes per run x 30

GitHub bills each job rounded up to whole minutes; a run's billed minutes are approximated from
`gh run list` as `ceil((updatedAt - startedAt) / 60 s)`, at least 1, which is what
`backend/dlr_live_window_check.py` prints.

| Workflow | Runs per day | Billed minutes per run | Minutes per month | Basis |
|---|---|---|---|---|
| Shadow Collection | 4 | median 5 (max 6) | about 600 | Measured 2026-10-25 00:00Z to 2026-10-26 00:00Z (plan 05-08): 4 runs (created 05, 11, 17 and 23 UTC), billed 3, 5, 5 and 6 minutes, 19 in the day; median basis 4 x 5 x 30 = 600 (about 570 at the mean of 4.75). Earlier measurement 2026-10-16 to 2026-10-19: median 5 per run, about 600 to 660 |
| DLR Live Ratings | 24 | median 4 (max 8) | about 2,880 | Measured 2026-10-25 00:00Z to 2026-10-26 00:00Z (plan 05-08): 25 runs (24 scheduled plus the 05-07 drill), billed 1 to 8 minutes, 103 in the day (the drill billed 1); median basis 24 x 4 x 30 = 2,880 (about 3,060 at the mean of the 24 scheduled runs, 4.25). Billed minutes are the checker's `ceil((updatedAt - startedAt) / 60 s)` approximation. Slowest runs (8 min) were the 00:05 and 16:05 runs; the first run (05-06) billed 4 |
| Total | 28 | | about 3,500 | Sum of the two rows above (median basis); about 3,600 at the means |

Owner's Billing figures, read from GitHub Settings, Billing and plans (account aa-phan) and recorded
2026-10-24 (plan 05-06):

| Quota figure | Value |
|---|---|
| Billing page read on | 2026-10-24 |
| Plan | Free (inferred from the 2,000 included minutes; the owner did not state the plan name) |
| Actions included minutes | 2,000 per month |
| Usage this cycle (cycle Oct 1 to Oct 31, 2026) | About 3,028 minutes, derived from the dollar figures: the included-minutes line shows about $12.00 off (2,000 minutes at $0.006 per Linux minute) and $6.17 billed beyond it (about 1,028 further minutes at $0.006). So about 2,000 included plus about 1,028 billed overage minutes |
| Cycle reset date | 2026-11-01 ("Monthly quota resets in 8 day(s)" on 2026-10-24) |
| Spending limit or budget | Not stated by the owner. Overage is being billed ($6.17 this cycle), so spending is not capped at $0 |
| Other usage lines | Storage, LFS and Packages included usage all $0. The $11.60 "Free usage" line (100% off) is not Actions-minute overage. Total current account usage shown: $17.78 |

The usage and overage minutes above are derived from the page's dollar figures, not read as a minute
count.

**The included minutes are already used up this cycle.** Every billed minute from now to the reset is
overage at $0.006 per minute.

Projection for the rest of this cycle, using the 05-06 formula "used + days left x (4 shadow + 24 live
runs per day) x 5 billed minutes per run":

    3,028 + 8 days x 28 runs x 5 minutes = 3,028 + 1,120 = about 4,148 minutes

That is above the 2,000 included minutes (about 2,148 over). The 1,120 minutes this plan would add are
all billed: about $6.72 at $0.006 per minute, of which the live runs are 960 minutes (about $5.76) and
the shadow runs 160 minutes (about $0.96, which Shadow Collection would spend anyway).

Projection for a full month, using the measured table above (private-repository basis, kept as history):

| Item | Minutes per 30 days (measured, 2026-10-25 window) |
|---|---|
| Shadow Collection | about 600 |
| DLR Live Ratings | about 2,880 |
| Total | about 3,500 (about 3,600 at the means) |
| Included | 2,000 |
| Overage | about 1,500 to 1,600 |
| Overage cost at $0.006 per minute | about $9 to $10 per month |

**Measured result, 2026-10-26 (plan 05-08): the measured total does not fit the 2,000 included minutes
recorded at 05-06.** On a private-repository basis a full month of hourly live runs plus Shadow
Collection would use about 3,500 minutes, about 1,500 to 1,600 over, roughly $9 to $10 per month at
$0.006 per minute. That is lower than the earlier estimate of 3,500 to 5,000 minutes and $9 to $18, and
it is moot while the repository stays public (hosted-runner minutes are free, 2026-10-24 update above):
the quota is not the binding constraint now. It binds again if the repository is made private. Shadow
Collection alone (about 600 minutes) fits inside the 2,000 included minutes. Dollar figures assume the
Linux rate of $0.006 per minute that the owner's figures imply.

Context only: GitHub's published included minutes for private repositories on personal plans are 2,000
(Free) and 3,000 (Pro) per month.

Hourly exceeds the included minutes of this plan. When the included minutes run out and no spending
allowance is set, GitHub stops all workflows in the account, including Shadow Collection before its
2026-11-24 confirmation run. Here overage is already being billed, so workflows are not stopped today,
but that depends on the owner's budget staying above zero and being large enough for the projection
above. Levers, none chosen here:

1. Allow paid overage up to a set budget (the rate is on the billing page).
2. Lower the billed minutes per run (a shorter install, fewer retries, a smaller timeout).
3. Lower the cadence, which revisits OD-1 and OD-4 (section 7).
4. Change repository visibility. Chosen by the owner on 2026-10-24: the repository is public, which
   makes GitHub-hosted runner minutes free (see the update at the top of this section).

**How to measure.** For the live side, `backend/dlr_live_window_check.py --start <hour> --hours 24`
prints the count, median and maximum billed minutes and the projected 30-day minutes for a window. For
the shadow side, `gh run list --workflow shadow_collect.yml --json databaseId,createdAt,startedAt,updatedAt,event,conclusion`
and count every run: before 2026-10-17 21:00 UTC `schedule` events also ran, so count the actual runs, not
4 a day, when measuring a past month.

## 13. Checking a window

`backend/dlr_live_window_check.py` turns "over 24 hours, every scheduled slot has either a successful run
or a visible failed run, and each successful run wrote one row per city" into one command. It is
read-only and runs from the owner's main checkout, because it needs `gh` authenticated and
`SUPABASE_DB_URL` in `.env`:

```bash
PYTHONPATH=backend .venv/bin/python backend/dlr_live_window_check.py --start 2026-10-25T00:00:00Z --hours 24
```

`--start` is the first slot, an exact UTC hour. `--json PATH` also writes the full result. It prints a
table (slot, verdict, runs, note), the billed-minutes line and the window verdict, and exits 0 when the
window passed, 1 otherwise.

| Verdict | Meaning |
|---|---|
| ok | A run succeeded, its `pipeline_run` row lists all four cities in `cities_ok`, and `city_rating` has four rows at that slot written by the slot's runs |
| incomplete | A successful run exists but one of those conditions fails. Fails the window |
| failed-visible | No successful run, but at least one non-drill run is red (failure, timed_out, cancelled or startup_failure). Passes: the failure is visible. A fault-drill run never counts (see below) |
| missing | No run, or only unfinished or inconclusive runs. Fails the window |

A run belongs to the slot of its `pipeline_run` `window_end` truncated to the hour; a run with no
`pipeline_run` row is placed by its start time and counts only if it is red. Rows from any run of the
slot count, so a later drill or re-run that overwrote some cities' rows in the same hour does not turn an
earlier good run into a failure.

A fault-drill run is excluded from the slot's verdict: it always ends red, so counting it would let a
slot whose scheduled run never happened pass as failed-visible. The check recognises a drill by a
`fault_injected` entry in the run's saved `cities_failed`, which the runner writes after the drilled
city's child ends. A drill that was cancelled or killed before that city finished, or that died before
its first row was written, leaves no such entry and still counts as a red run; the report's note names
a run it excluded ("fault-drill run ... not counted"), so a slot that shows `failed-visible` right after
a drill dispatch should be checked against the drill's run id by hand. Its rating rows (when it got that
far) still count toward the slot, and its minutes are still billed.

## 14. Freshness alarm (permanent)

In plain English: every 15 minutes a cron-job.org job asks the database whether every city's current
rating is at most 90 minutes old. If one is not, the job fails and, after 2 failures in a row, an email
goes to the owner. When the ratings are fresh again a recovery email follows. The alarm is permanent
(D-13): it stays on after the 72 h soak is over and the soak's own log job has been removed.

**What it is.** A cron-job.org job titled "DLR freshness alarm". It is separate from the dispatch job
(section 2) and from the Shadow Collection job; those two are never changed for it. It is not a
database job: the 5-minute log job of section 15 is the soak's record, this alarm is not.

| Setting | Value |
|---|---|
| Title | DLR freshness alarm |
| URL | `<SUPABASE_URL>/rest/v1/rpc/assert_fresh` (typed into cron-job.org only; the default `max_age_minutes` is 90) |
| Method | GET |
| Header `apikey` | `<SUPABASE_PUBLISHABLE_KEY>`: the publishable key only, never the secret key (D-10) |
| Expected result | HTTP 200. HTTP 503 with code `PT503` means a city is missing or stale; 400 means a bad `max_age_minutes` |
| Schedule | every 15 minutes, time zone UTC (`*/15 * * * *`) |
| Timeout | 30 s (cron-job.org's own limit) |
| Notify on failure | after 2 failures (the "failures required before a notification is sent" option) |
| Notify on success after a failure | on (the recovery email) |
| Notify when the job is disabled | on |
| Emails go to | the owner's cron-job.org account only (D-15); there is no team address yet |

The URL and the key are entered in cron-job.org and nowhere else: not in this repository, not in a
`.env`, not in a message (D-10). The key is the one the dashboard and PSS/E teams use, so it can only
read; the secret key is never used here. The same 90 minutes as `latest_rating.is_stale` and the soak
report apply (OD-4): a rating exactly 90 minutes old is fresh, one second more is stale.

**How soon it tells you.** A city-hour that is lost goes stale 90 minutes after its slot starts. The
first failing check follows within 15 minutes and the second 15 minutes after that, so the email arrives
about 105-120 minutes after the missed hour began. One slow hour (a rating that lands 30 or more minutes
late) can trip it for the same reason.

**It stays on after the soak.** At soak end only the 5-minute log job is removed (section 15). Leave
this alarm running. This runbook is where the owner records that it is permanent.

**To pause the alarm.** Open the job in cron-job.org and switch it off. Pause it whenever the pipeline
is paused (section 6): with no new ratings it would fail on every check. To resume, switch it back on and
check that the next execution answers 200.

**When it fires.** Work from the cause towards the data:

1. Read the newest `pipeline_run` rows and the `cities_failed` of each (the query in section 5): which
   city failed, with what `outcome` and redacted error.
2. Look at the Actions history for the live workflow: `gh run list --workflow dlr_live.yml --limit 6`.
   A missing run points at the dispatch job (section 2: expired token, disabled job); a red run points
   at the run's log.
3. Check what consumers see: `PYTHONPATH=backend .venv/bin/python backend/e2e_verify_readonly.py --check-read`
   prints each city's age and `latest_rating.is_stale`.

Then follow the matching row of section 11. Fresh ratings end the alarm on their own: the next check
answers 200 and the recovery email arrives.

**The 25-failure auto-disable.** cron-job.org disables a job that fails more than 25 times in a row,
which at 15 minutes is a continuous outage of about 6.5 hours. The "job disabled" email is on for that
case. To recover: fix the cause (above), then re-enable the job in cron-job.org (a disabled job does not
come back by itself) and check that its next execution answers 200.

## 15. Soak monitoring (Phase 6)

In plain English: for three days a database job writes down every five minutes how old each city's
current rating is. At the end one report lists every time a rating was older than 90 minutes, with a
cause for each, and every deploy that happened in that time. The soak passes when the window is at least
72 h long, the log has no gap longer than 11 minutes and every breach has a cause or an owner annotation.

**Start (owner, after the dry-soak review, D-07).**

1. Enable the Cron integration once: Supabase dashboard, Integrations, Cron.
2. Run `supabase/ops/soak_cron_schedule.sql` in the SQL editor. It creates one job, `dlr-soak-freshness`,
   that calls `ops.log_freshness()` every five minutes (`*/5 * * * *`). Running it again changes nothing.
3. After 15 to 20 minutes run `supabase/ops/soak_probe_smoke.sql`: every row must be `ok` before the
   72 h clock starts.
4. Run `supabase/ops/verify_monitoring.sql`: every row must be `ok` (the public key cannot read the log).

**The dry soak (before the clock, D-07).** It measures how late each hourly rating really lands, from
rows already written, so nobody waits a fresh 12-24 hours:

```bash
PYTHONPATH=backend .venv/bin/python backend/e2e_soak_report.py export --mode dry --since 2026-10-25T00:00:00Z --until <DRY_END_UTC> --out-dir <DRY_DIR>
PYTHONPATH=backend .venv/bin/python backend/e2e_soak_report.py report --mode dry --in-dir <DRY_DIR> --out <DRY_DIR>/dry_report.md --json-out <DRY_DIR>/dry_report.json
```

**The 72 h soak.** `<G>` is the start of the clock (a 5-minute boundary) and `<U>` is at least 72 hours
later. The 72 h window never overlaps the dry-soak window. `export` is read-only and runs from the
owner's main checkout (it needs `SUPABASE_DB_URL` in `.env` and `gh` signed in); `report` is offline and
gives the same bytes for the same files:

```bash
PYTHONPATH=backend .venv/bin/python backend/e2e_soak_report.py export --mode soak --since <G> --until <U> --out-dir <SOAK_DIR>
PYTHONPATH=backend .venv/bin/python backend/e2e_soak_report.py report --mode soak --in-dir <SOAK_DIR> --annotations <SOAK_DIR>/annotations.json --out <SOAK_DIR>/soak_report.md --json-out <SOAK_DIR>/soak_report.json
```

It exits 0 only when the window is at least 72 h (`--min-hours`), probes are present and every breach
and probe gap is explained; 1 otherwise; 2 when a file or `annotations.json` is missing or malformed.
Run it during the soak as often as you like; a run before 72 h have passed fails on length only.

**Reading the report.**

- A write breach is an exact interval in which a city's current rating was older than 90 minutes,
  computed from when each row was first written (a same-hour retry cannot move it). Its id is
  `write:<city>:<start>`. A probe breach (`probe:`) is one the probe log saw that no write interval
  explains; a probe gap (`probe-gap:ALL:`) is a hole in the log longer than 11 minutes, window edges
  included.
- The cause is derived, not guessed: no workflow run for the slot (dispatch missing); a run that
  concluded failure; the city listed as failed in that run's `pipeline_run` row (with its redacted
  error). A row first written more than 30 minutes after its slot is named as a "late run", but that is
  the same condition as the 90-minute limit being passed, so it does not excuse the breach. A breach
  none of the other causes explains, or that only a late run explains, needs an owner annotation.
- Deploys are derived from the data (D-08): any slot where a city's `pipeline_version`,
  `config_fingerprint`, model hashes, `forecast_method` or `config_version` differs from its previous
  row, classified with `git diff --name-only <old> <new>` as model, config, workflow, code or no runtime
  change. If the commit is not in the local clone the report says so: run `git fetch` and report again.
  A deploy within two hours before a breach is shown beside it as context. A deploy never excuses a
  breach, and the soak is not paused or restarted for one.

**annotations.json.** Only the owner writes it; nothing is written on the owner's behalf. Breach ids come
from the report. The text is printed verbatim with its author and date. Events are things the data cannot
show (a cron-job.org edit, an owner pause, an incident):

```json
{
  "breaches": {
    "write:EL_PASO:2026-10-29T06:30:00Z": {
      "explanation": "<what happened, in the owner's words>",
      "by": "<owner name>",
      "date": "2026-10-30"
    }
  },
  "events": [
    {"time": "2026-10-29T10:00:00Z", "what": "<what changed>", "by": "<owner name>"}
  ]
}
```

An annotation whose id matches no breach is listed as a warning and excuses nothing.

**No writes during the write check.** Run `--check-writes` (section 16) with no backfill load and no
past-slot re-run in progress: those are the only legitimate writers of old rows, and a changed row would
look like an accepted write. The hourly run is harmless; it writes only the current slot.

**Teardown at soak end (D-13).** After the soak record has been exported and the owner has signed off,
run `supabase/ops/soak_cron_unschedule.sql` in the SQL editor: it removes the job `dlr-soak-freshness`
and shows `remaining_jobs`, which must be 0. The alarm stays: section 14 is permanent. `ops.freshness_log`
keeps its rows as the frozen soak record; there is no retention job and nothing deletes them.

## 16. Permission re-check after 2026-10-30

In plain English: Supabase changes the default permissions of new tables on 2026-10-30 (existing projects
included). Ours are written out explicitly, so nothing should change, and this re-check proves it. Run
it on or after 2026-10-31. It also closes Phase 4's carried item T-04-22 (the `consumers_cannot_write`
smoke after 10-30). The two values below go in your shell, never in a file:

```bash
export SUPABASE_URL=<SUPABASE_URL> SUPABASE_PUBLISHABLE_KEY=<SUPABASE_PUBLISHABLE_KEY>
PYTHONPATH=backend .venv/bin/python backend/e2e_verify_readonly.py --check-read --check-hidden --check-writes --json-out <RECHECK_FILE>
```

| Check | Command | What it means |
|---|---|---|
| Read | `e2e_verify_readonly.py --check-read` | With only the public key you see exactly one current rating per city, with the documented columns |
| Hidden tables | `e2e_verify_readonly.py --check-hidden` | The private run log and the soak log cannot be read with the public key |
| Writes | `e2e_verify_readonly.py --check-writes` | Trying to add, change or delete data with the public key is refused, and the data afterwards is identical |
| Database permission list | `supabase/ops/verify_exposure.sql` in the SQL editor | The database's own list says the public key can read the ratings table and the view and nothing else |
| Writer smoke | `supabase_smoke.py`, check `consumers_cannot_write` (owner command in its docstring, with `--report <RECHECK_SMOKE_FILE>`) | The public roles hold no write privilege on either table, checked as the CI writer role |

```bash
PYTHONPATH=backend .venv/bin/python -c "from dotenv import load_dotenv; load_dotenv('.env'); import sys, supabase_smoke; sys.exit(supabase_smoke.main(['--report', '<RECHECK_SMOKE_FILE>']))"
```

Compare the result with 06-09's live evidence. Any difference (a check that passed then and fails now, a
new column, a grant that appeared or went away) is a discrepancy to bring to the owner; do not fix it
silently. Run `--check-writes` only when no backfill load or past-slot re-run is in progress (section 15).

## 17. Day-ahead forecast stage (Phase 8)

In plain English: besides rating each line now (and 60 minutes ahead), the hourly job also publishes a
separate, higher-error day-ahead forecast of each city's ampacity in amperes. It never sets or checks a
rating, and it never gates the 60-minute forecast (G6). Every row carries the label
`day-ahead-24h; engineering-selection; not-validated`: it is an engineering-selected forecast that has
not been validated. It is stored in its own table, `public.day_ahead_forecast`, one row per city and
target hour, and it is not readable with the public key until the expose migration (D-17) is applied.

**What "24 h" means.** "24 h" is the weather run's age, not the time between issue and target. Each value
is computed from the Open-Meteo run that started exactly 24 h before the target. A row is issued 0 to
18 h before its target (the run is published about 6 h after it starts, so a target becomes issuable 18 h
ahead). Both times are stored: `forecast_run_init_time` (target minus 24 h) and `issued_at` (the actual
decision time of the run that issued the row).

The correction also needs a recent station reading, the anchor. How far before the target it is differs
by setup, and it is why the launch band is only a starting estimate:

| Setup | Anchor reading is about | Where it is used |
|---|---|---|
| TEST | exactly 24 h before the target | The launch band is built from the TEST split |
| Shadow collection | 12 h before the target | The shadow log the model was selected on |
| Live (this stage) | up to 18 h before the target (less for a catch-up issue) | Every published row |

**When a target is due.** Targets are the 00, 06, 12 and 18 UTC hours. A target is due from the hourly
run at or after target minus 18 h until the target itself. The hourly runs at 06:05, 12:05, 18:05 and 00:05
UTC (12:05 AM, 6:05 AM, 12:05 PM and 6:05 PM Central standard time, the time in force until March; in
daylight time subtract 5 hours from UTC instead of 6) therefore normally issue one new target per city.
The other hourly runs find nothing to do. About three targets per city are issued ahead at any time. The
first run after go-live issues every target then due, up to 3 per city (12 rows in all), each with a
different lead.

**Catch-up (D-04).** The table is the only state. Each run reads which future targets already have a row
and issues the missing due ones, earliest first, so a missed or failed run is repaired by the next hourly
run with no marker file. A row is never rewritten: the first write wins, and a catch-up row simply carries
a later `issued_at`, so a late value is visible.

**Budget.** The stage starts only after the ratings are finished and the exit code is fixed. It runs one
`backend/dlr_day_ahead.py` child per city, in `config.LOCATIONS` order, inside the same 1200 s child
budget the ratings share (4 cities x 300 s). Each child is killed at `DAY_AHEAD_CITY_TIMEOUT_S` = 150 s or
at the budget left, whichever is smaller, and a city is started only when at least
`DAY_AHEAD_MIN_START_S` = 60 s of the shared budget remain; otherwise it is recorded `skipped_budget`
and the next hourly run catches up. A healthy run takes seconds; if the ratings used the whole budget the
stage starts nothing. The workflow file and its `timeout-minutes: 30` are unchanged.

**Outcomes** (one per city, in `pipeline_run.day_ahead`):

| Outcome | Meaning | What to do |
|---|---|---|
| none_due | Every due target already has a row (the usual state for most hours) | Nothing |
| issued | Every missing due target got a row | Nothing |
| partial | Some targets got a row and some did not (for example one weather run was not yet available) | Nothing; the next hour retries the rest. The reasons name each missing target |
| error | The child failed, or refused for a named reason: the band file or a cooling model differs from the manifest, no anchor reading, the database could not be reached | Read the reason. A hash refusal means the files and the manifest disagree (section 9); an unreachable database is the Supabase pause row of section 11 |
| timeout | The child outlived its time and was killed | Rows it wrote before the kill stand; the next hour catches up. Repeated timeouts point at a slow weather provider |
| skipped_budget | Less than 60 s of the shared budget remained when the city was reached | The ratings ran long; the next hourly run catches up |

**Where outcomes are recorded.** In `pipeline_run.day_ahead` (a private jsonb column, written by the stage
as its own `pipeline_run` upsert, so it never touches the rating-stage columns): `started_at`,
`finished_at`, `budget_s` and, per city, the outcome, the `due`, `issued` and `missing` targets, the
redacted `reasons`, `band_sources`, `out_of_bounds`, the cooling model sha256, `exit_code` and `duration_s`.
The step summary of each run shows a separate day-ahead table and its own `pipeline_run day_ahead: N
writes, M failed` line next to the rating table and the `pipeline_run: N writes, M failed` line.

```sql
-- the day-ahead outcome of the latest runs
select run_id, window_end, day_ahead -> 'cities' as cities
from public.pipeline_run
where day_ahead is not null
order by window_end desc
limit 24;
```

**Failure policy (D-15, D-16).** The day-ahead stage never turns a run red: a crash, a hang, a refusal or a
failed write of its own record cannot change the exit code of `dlr_live_run.py`, the rating rows or the
rating run log. If a value cannot be computed there is no value and no row for that target, and the reason is
logged and recorded; no other method is used in its place. A value outside the city's rating bounds is
still published as computed and listed under `out_of_bounds`. No exception text or provider message is
ever placed in the table.

**The band.** Each row carries a 5-95% band in amperes. At launch every band comes from the hashed TEST
artifact (`band_source` test-split, 196 residuals per city and target hour, built from the TEST split, which
is a starting estimate rather than a live calibration). Each band switches on its own to a live band
(`live-rolling`) once 60 graded pairs exist for that city and UTC target hour, using the newest 120 pairs,
and only when the live band brackets the value (its 5% offset below zero and its 95% offset above it);
otherwise it keeps the TEST band. A graded pair is a day-ahead value and the weather-computed rating for the
same city and hour, under the same `config_fingerprint` and the same cooling model sha256 (section 9).

**A later conductor refit (D-13).** The served cooling model follows a new refit only through the promotion
step in section 9: refit the city, bump `DAY_AHEAD_REFIT_VERSION` in `backend/day_ahead_forecast.py`
together with the refit, regenerate the manifest, run the day-ahead tests and ask the owner before pushing.
Until then the stage keeps serving the files the manifest names.

**How to check it.**

- After the first live run following the push, with the time just before the push (an ISO time in UTC),
  from the repository root with `SUPABASE_DB_URL` in the git-ignored `.env`:

  ```bash
  PYTHONPATH=backend .venv/bin/python backend/day_ahead_verify.py --check-store --since <PUSH_TIME_UTC> --json-out <EVIDENCE_FILE>
  ```

  It only reads (one read-only transaction, rolled back), prints one PASS or FAIL line per named check and
  one line per row, and exits 0 only when the first issuing run wrote every due target (up to 3 per city, 12
  in all) with the right label, the TEST band, the manifest hashes, the code's config identity, a bracketing
  band, a lead of at most 18 h and a `pipeline_run.day_ahead` record. Exit 1 means a check failed, 2 a missing
  `SUPABASE_DB_URL` or a bad `--since`. The JSON never holds the connection URL, host or user.
- To run one city locally without the database (a dry run: nothing is stored, the TEST band is used):

  ```bash
  PYTHONPATH=backend .venv/bin/python backend/dlr_day_ahead.py --city AUSTIN --output /tmp/da.json --no-store
  ```

- To run the ratings without the stage (a local run, for example when testing a rating change):
  `PYTHONPATH=backend .venv/bin/python backend/dlr_live_run.py --no-day-ahead`. The scheduled workflow never
  passes it.
- The owner's one-query check of the write side after the migration is applied is
  `supabase/ops/verify_day_ahead_store.sql` in the SQL editor: every `ok` must be true.
