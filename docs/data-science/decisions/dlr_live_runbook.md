# DLR Live Ratings Runbook

**Status: production path (production-pipeline Phase 5). Operating this workflow writes hourly ratings
for the four cities into Supabase. It never touches Shadow Collection.**

This is the operating reference for `.github/workflows/dlr_live.yml` and the cron-job.org job that
starts it: how it is triggered, what one run does, where the results go, how to pause, change,
drill and check it, and what it costs in GitHub Actions minutes. It is deliberately commands and
settings, not rationale; the rationale is in the Phase 5 plans and `REQUIREMENTS.md`. Nothing here
holds a secret value: tokens and keys live in cron-job.org and in GitHub's Actions secrets, never in
this repository.

Last updated 2026-10-26 (plan 05-08: measured Actions minutes for a full 24 h of hourly live runs and
the same day of shadow runs, section 12). Earlier: 2026-10-24 (plan 05-06: owner's Actions quota recorded
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
5. Run `backend/dlr_live_run.py`: one `dlr_orchestrator.py` child process per city, one after another in
   `config.LOCATIONS` order, all sharing one window end. Each child rates its city with the composed
   providers and the ML forecast and writes its own rating row. Each child has a hard budget of
   `CITY_TIMEOUT_S` = 300 s and is killed at that point.

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

- `finished_at` null means the run did not finish, for example the job timeout killed it.
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

**Resume.** Re-enable the cron-job.org job (and the workflow, if it was disabled). Nothing needs to be
reset: there is no state outside the database. Missed slots are not back-filled. The gap stays in
`city_rating` until it is filled by hand with a local run for that slot (section 8), and Phase 6's
freshness check will show the gap while it exists.

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
filled by hand); `--cities MIDLAND` limits the cities; `--no-run-log` skips the `pipeline_run` row (the
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
| The cron-job.org job is disabled, misconfigured or its token has expired | No run starts and nothing in the repository reports it | cron-job.org failure notifications and Phase 6's freshness check (a city whose latest `valid_time` is older than 90 minutes) |
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
| failed-visible | No successful run, but at least one run is red (failure, timed_out or cancelled). Passes: the failure is visible |
| missing | No run, or only unfinished or inconclusive runs. Fails the window |

A run belongs to the slot of its `pipeline_run` `window_end` truncated to the hour; a run with no
`pipeline_run` row is placed by its start time and counts only if it is red. Rows from any run of the
slot count, so a later drill or re-run that overwrote some cities' rows in the same hour does not turn an
earlier good run into a failure.
