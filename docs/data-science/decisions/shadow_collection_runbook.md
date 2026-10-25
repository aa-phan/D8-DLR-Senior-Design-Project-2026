# Shadow Collection Runbook

**Status: experimental/shadow path. Never invoked by production (`dlr_pipeline.py` or any other
caller). Operating this collector changes nothing about any operational rating decision.**

This is the one-page operational reference for running `backend/forecast_shadow_collect.py`
continuously. The full technical trace (input contract, failure-attribution design, live-run
evidence) lives in `forecast_correction_followup_audit.md`'s "Shadow prototype" section — this
runbook is deliberately just the commands and host requirements, not the rationale.

> **Per-city collection (2026-10-12).** The project no longer rates corridors: each of the four
> cities — `AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND`, `EL_PASO` — is an independent rating point
> (contract: `point_scope.md`). The collector loops `config.LOCATIONS` (four cities, not two
> corridors) and writes one log per city. Everything below describes that per-city operation;
> sections or sentences marked **corridor-era** are dated history kept for the record.
> Verified against the code (2026-10-12): `forecast_shadow_collect.py`, `forecast_shadow_pipeline.py`,
> `forecast_shadow_demo.py`, `forecast_shadow_healthcheck.py` and `forecast_shadow_render_table.py`
> all iterate `config.LOCATIONS` / key on `city`; none reference `config.CORRIDOR_ENDPOINTS`.

## What changed from the corridor-era collector

| | Corridor-era (retired 2026-10-12) | Per-city (current contract) |
|---|---|---|
| Units collected | 2 corridors: `AUSTIN_CORPUS_CHRISTI`, `MIDLAND_EL_PASO` | 4 cities: `AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND`, `EL_PASO` (`config.LOCATIONS`) |
| Log files | `data/shadow/predictions/AUSTIN_CORPUS_CHRISTI.jsonl`, `MIDLAND_EL_PASO.jsonl` | `data/shadow/predictions/{CITY}.jsonl`, one per city |
| Record key | `corridor` | `city` |
| `schema_version` | 1 (flat rows) and 2 (nested `candidates`) | **3** |
| Target of each candidate | Corridor ampacity: `min()` over two endpoint cities | That city's own ampacity; no reduction across cities |
| Model artifacts | `data/shadow/models/{method}_{CORRIDOR}.joblib` | `data/shadow/models/{method}_{CITY}.joblib` |
| Anchor-wind lookups | Both endpoint cities per corridor entry | The one city's own station observation (`fetch_live_anchor_observation(city, ...)`; TCEQ, then Synoptic) |

**Legacy corridor logs are untouched.** The existing `AUSTIN_CORPUS_CHRISTI.jsonl` and
`MIDLAND_EL_PASO.jsonl` (local, and on the `shadow-collection-data` branch) are left exactly as
they are: append-only history in the corridor-era schema (v1 flat rows and v2). The collector no
longer writes to them. Any reader that scans `data/shadow/predictions/*.jsonl` must tolerate
these legacy files and must **not** mix legacy corridor rows into per-city evaluation (key on
`schema_version: 3` / the `city` field, never on file glob alone). Per-city logs start empty.

## Per-city models and unavailable ML candidates

Model artifacts are per city and are fitted on that one city's own rows (`pooling="per_city"` for
the wind and cooling correction models; the `"ml"`, anomaly and `reference_ml_refit_24h` targets
are that city's own ampacity, not a minimum). Existing corridor-named artifacts under
`data/shadow/models/` (for example `ml_wind_corrected_AUSTIN_CORPUS_CHRISTI.joblib`) are legacy
and are **not loaded**.

**Per-city refit was run 2026-10-12** (offline, from the cached experiment frames; see "Refit
procedure" below): all twelve artifacts (3 methods x 4 cities) exist under `data/shadow/models/` and
are git-tracked so the runner receives them via `actions/checkout`. A city/method pair whose artifact
is absent still reports `status="unavailable"` with a named reason (the existing `FileNotFoundError`
path) while `raw_forecast` records normally and `persistence_24h` records once that city has a prior
v3 entry for the matching hour (a cold start is `unavailable` with a "cold start" reason, not a fault).
The workflow's pre-flight step (`backend/forecast_shadow_check_models.py`) fails the run up front if
any of the twelve files is missing from the checkout.

The reason string is the `FileNotFoundError` text from `forecast_shadow_pipeline.load_correction_model`:
``load_correction_model: no persisted '<method>' model for city '<CITY>' at
'data/shadow/models/<method>_<CITY>.joblib'. Fit one with ...``. The three ML candidates degrade to
`status="unavailable"` (never to `raw_forecast`, and never `failed`) and carry no value for that cycle;
`raw_forecast` is a separate candidate and is unaffected. A legacy corridor-named artifact in that
directory is never loaded.

### Refit procedure

```bash
PYTHONPATH=backend .venv/bin/python backend/forecast_shadow_fit_models.py            # all of config.LOCATIONS
PYTHONPATH=backend .venv/bin/python backend/forecast_shadow_fit_models.py --city AUSTIN
```

Writes `data/shadow/models/{ml_wind_corrected,ml_cooling_corrected,reference_ml_refit_24h}_{CITY}.joblib`
via `forecast_shadow_pipeline.save_correction_model` and prints each path and `n_rows_fit`. Then
`git add data/shadow/models/*.joblib` and commit to main (the runner only sees what main contains).

**Data needed (no network).** The cached anchored pair frames
`data/experiment/anchored_pair_frame_{CITY}_2024-01-20_2026-09-29_lead24_previous_runs.csv`
(git-ignored; `data/experiment/` is local only). If a file is missing the script refuses with a
`FileNotFoundError` naming it (it never lets `anchored_pair_frame` fall through to the network).
Rebuild it deliberately, with network access, via
`forecast_experiment.anchored_pair_frame(city, "2024-01-20", "2026-09-29", lead_hours=24)`, then refit.

**Recipe.** Same as the frozen experiment's `fit_fitted_arms`, per city: only rows strictly before
`FROZEN_TEST_SPLIT_START` (2026-03-17) are used (asserted in code); arms 3/4 fit on the exact-24h-lead
subset with `city_point.city_point(city)` geometry (wind: LinearRegression, `pooling="per_city"`;
cooling: GradientBoostingRegressor, `log_ratio`); arm 5 fits `MLPRegressor` on that city's OWN
ampacity truth series at `horizon_minutes=1440`. `forecast_shadow_fit_reference_refit.py` still
exists as the network (Archive API) variant for `reference_ml_refit_24h` alone and shares the same
arm-5 fit.

### Fit-window decision: train + validation (2026-10-12)

**Decision.** The per-city `ml_wind_corrected` and `ml_cooling_corrected` artifacts are fit on the
**train and validation splits together** (every cached row strictly before the frozen test split,
`FROZEN_TEST_SPLIT_START` = 2026-03-17). The team accepted this on 2026-10-12 on the condition that it
be recorded here as a choice made possible by model selection having already finished.

**What the original artifacts did.** The corridor-era wind and cooling artifacts were fit on the
experiment's **train split only**: exact-24h-lead rows up to `2025-09-01T18:00:00Z`, 2,360 rows per
city (`n_rows_fit` 4,720 across each pooled pair; counts in `forecast_correction_followup_audit.md`,
split boundary audit). The validation split (`2025-09-02T00:00:00Z` up to the day before the test
split; 786 exact-lead rows per city in that audit) was held out of those fits. The old
`reference_ml_refit_24h` artifact, by contrast, was already fit on train + validation
(`_train_val_window_end()` = the day before the test split). The original setup therefore gave the
reference candidate more data than the two correction candidates.

**Why using validation data for the final fit is legitimate here.**

1. *What validation was for.* The validation split was used to **select** the model configuration
   (Plan 03-05's validation-selected pairs, now frozen as `forecast_experiment.WIND_CONFIGURATION`
   — LinearRegression — and `COOLING_CONFIGURATION` — GradientBoostingRegressor with the `log_ratio`
   target; the MLP family for the reference arm comes from `forecasting_model.md`'s separate
   bake-off). Selection is finished: this change does not re-select anything, and the per-city
   artifacts use those frozen configurations unchanged.
2. *Refit after selection.* Once the configuration is chosen, refitting the chosen configuration on
   train + validation is standard practice, because validation is no longer needed to compare
   candidates, and it adds 784 further exact-lead rows per city (3,144 vs 2,360, about 33% more).
3. *The test split is untouched.* No row at or after 2026-03-17 is read by the fit, and
   `forecast_shadow_fit_models.assert_no_test_leak` enforces this (it checks both `datetime_utc` and
   the anchor timestamps). The live shadow data collected from 2026-10-12 onward did not exist when
   the models were fit, so the shadow evaluation remains genuinely out of sample.
4. *Comparability.* All three ML candidates now see the same calendar span of data, removing the
   original asymmetry in which only the reference candidate had seen the validation period.

**What this does and does not allow you to claim.**

* The frozen experiment's validation and test-split results describe the **train-only** fits. They
  must **not** be quoted as the performance of these per-city artifacts.
* The new artifacts must **not** be scored on the validation period (it is in-sample for them), and
  nothing in this repository scores them on the test split. Their only honest out-of-sample evidence
  is the live shadow collection.
* The selection of the configurations itself used the validation split, so any optimism in that
  selection is unchanged by this refit; this change adds data to the fit, it does not remove or
  repair that bias.
* The wind model is now fit per city (`pooling="per_city"`) instead of pooled over a corridor's two
  cities with an endpoint indicator, and all three targets are the city's own quantities. Those are
  separate changes from the fit window (see `point_scope.md`).
* The sanity comparison against the legacy corridor models below used rows from the frozen test
  period. It shows only that the new artifacts behave sensibly, not that they are more accurate.

**Reproducing the original train-only recipe.** Not implemented as a flag. It would require cutting
the exact-lead frame at `2025-09-01T18:00:00Z` (the end of the train split) instead of
`FROZEN_TEST_SPLIT_START` in `forecast_shadow_fit_models.py` for the wind and cooling arms, then
re-running the refit.

**Fit results (2026-10-12).** `n_rows_fit` per artifact:

| City | `ml_wind_corrected` | `ml_cooling_corrected` | `reference_ml_refit_24h` |
|---|---|---|---|
| AUSTIN | 3144 | 3144 | 18834 |
| CORPUS_CHRISTI | 3144 | 3144 | 18834 |
| MIDLAND | 3144 | 3144 | 18834 |
| EL_PASO | 3144 | 3144 | 18834 |

Sanity check (not ground truth): each artifact loads through `load_correction_model`, and a one-row
prediction on the last cached row of each city is finite and within `RATING_BOUNDS_BY_LOCATION[city]`.
Over the 24 last cached rows, per-city vs the legacy corridor models differ by roughly 16-140 A mean
absolute (largest: MIDLAND/EL_PASO reference and cooling models), as expected from the changed
targets and per-city fits. These last rows are in the frozen test period (post-fit); no
outcome-vs-truth scoring is implied.

## Five-method collection (D-08)

**Five-method collection began 2026-10-07 (corridor-era, retired 2026-10-12 as a per-corridor
log; the five-method shape carries over per city).** From this date forward, every cycle's log
entry records all five real (non-oracle) 24-hour-lead candidates side by side, not just one:
`ml_wind_corrected` (unchanged provisional default — the six-field top-level mirror any legacy
single-method reader, e.g. `forecast_shadow_healthcheck.py`, still sees unmodified),
`ml_cooling_corrected`, `raw_forecast`, `persistence_24h`, and `reference_ml_refit_24h`. Each
candidate carries its own `status`/`ampacity_amps`/`fallback_used`/`fallback_reason`/
`model_version`/`input_provenance`/`reason`, nested under a `candidates` object
(`forecast_shadow_pipeline.log_cycle_predictions`). Corridor-era `schema_version: 2` records
carried this shape keyed by `corridor`; `schema_version: 3` carries it keyed by `city`.
Rows already committed to `shadow-collection-data` before 2026-10-07 keep their old flat,
single-candidate shape forever — no migration, no backfill, no rewrite of historical rows
(05-01-SUMMARY.md's approved historical-data strategy). Both `forecast_shadow_render_table.py`
(the README table generator) and `forecast_shadow_healthcheck.py` are required to read every
shape (v1, v2, v3) correctly, per line, forever. Verified: `forecast_shadow_render_table.py` renders only `schema_version >= 3` rows keyed by the file's own city (legacy corridor logs are named in a footer line, not rendered, never mixed in), and `forecast_shadow_healthcheck.py` reads only the last parseable `city`-keyed row of each `{CITY}.jsonl`.

**This is additional observational data. It is independent of, and is not a substitute for, the
Nov 1/Nov 24 fresh-basis confirmation protocol in `forecast_correction_followup_audit.md`.** That
protocol's own `_fresh_confirmation_report` harness scores FRESH-basis rows under its own
pre-committed, fixed schedule (2026-11-01 freeze, 2026-11-24T00:00:00 UTC evaluation instant) and
is untouched by this phase — no code, date, or harness there was changed to produce the five-method
expansion above. Per that document's own explicit carve-out (quoted verbatim so both documents
agree on exactly what counts as a permitted mechanical check): *"confirming the shadow pipeline's
own logs exist, that its four timestamps (initialization/availability/decision/valid) are
populated and sane, that FRESH-basis row counts are accruing, and that
`data/shadow/predictions/*.jsonl` is being written to without errors"* is permitted at any time and
is **not** outcome inspection. This runbook note, and every check this phase ran to confirm the
collector works, stayed entirely inside that boundary — no FRESH-basis row's predicted-vs-truth
outcome was inspected, or will be, before 2026-11-24T00:00:00 UTC.

*(Per-city scoring is governed by `confirmation_protocol_v3_per_city.md`, signed 2026-10-13.)* **Evidence base and the 2026-11-24 date.** The fixed 2026-11-24 evaluation date was set against
corridor-level collection. Per-city logs start empty, so whether that date moves (and whether
corridor-era FRESH-basis rows count toward any per-city evaluation) is an open team decision
recorded in `point_scope.md` — this runbook does not decide it.

### Confirming the next SCHEDULED run (D-10) — corridor-era, retired 2026-10-12

**What was confirmed on 2026-10-07 (manual dispatch, corridor-era):** a real `gh workflow run
"Shadow Collection"` dispatch ran the full pipeline end to end on the actual `ubuntu-latest` CI
runner, completed successfully in ~1m2s (well under the 15-minute `timeout-minutes` budget then in force), and
committed a new `schema_version: 2` entry for both corridors to `shadow-collection-data`, each
carrying all five candidate names under `candidates`. That run was two corridors; a per-city run
makes four city cycles with the inter-city delay (see Exact commands); that wall time has not been
measured. Each city does roughly half the fetching one corridor did, plus 3 x 15s = 45s of
deliberate pauses, so the nominal run should be a few minutes. The workflow's `timeout-minutes`
was raised from 15 to 30 (2026-10-12) to cover the degraded case, where each city's forecast,
anchor, truth-proxy and solar fetches can each hit their own 60s timeout.

**What that did NOT prove, and remains an outstanding, dated follow-up:** a manual
`workflow_dispatch` run is not the same trigger as the cron `schedule` trigger (`0 6,18 * * *`
UTC) — D-10 explicitly requires confirming the *next scheduled* run, not just a manually-triggered
one. The next cron boundary after that phase's own work was **2026-10-08T06:00:00 UTC**. After that
boundary had actually passed, the confirmation was to be made with:

```bash
git fetch origin shadow-collection-data
git log -1 --format=%cI origin/shadow-collection-data
gh run list --repo <owner>/<repo> --workflow="Shadow Collection" --limit 5 --json event,status,conclusion,createdAt
```
Look for an entry with `"event": "schedule"` and `createdAt` at or after the boundary,
`"conclusion": "success"`, and confirm the newest commit on `shadow-collection-data` postdates it
with a new entry. For per-city operation the same check applies and the new entries should be
`schema_version: 3` rows in `data/shadow/predictions/{CITY}.jsonl` for all four cities. **Do not
treat the manual-dispatch confirmation as satisfying the scheduled-run check.** Whether the 2026-10-08 scheduled-run confirmation was ever recorded is not established by anything in this repo; this page does not claim it.

## Verified input contract (summary)

| Variable | Source | Fallback |
|---|---|---|
| Forecast wind, temperature, solar (valid-time) | Open-Meteo forecast API (`fetch_live_forecast_for_valid_time`) | None — single provider; a null/missing row raises and the prediction falls back to `raw_forecast` |
| Observed anchor wind (now, per city) | TCEQ CAMS (primary) | Synoptic station (automatic, on an unusable TCEQ row) |

Two distinct, never-conflated failure types in every log entry:
- **Provider fallback** (TCEQ → Synoptic succeeded) — visible in `input_provenance.anchor_provenance.anchor_source` (on the anchored candidates, `ml_wind_corrected` and `ml_cooling_corrected`, in that city's own log). The prediction is still a genuine `ml_wind_corrected` result; `fallback_used` stays `false`.
- **Prediction-method fallback** (no provider anywhere supplied a usable value) — `fallback_used: true`, `fallback_reason` names exactly which provider(s) failed and how, `method` reads `raw_forecast`.

Every log entry additionally preserves the issued ampacity, `model_version`, full `input_provenance`, and all four timestamps (`initialization_time`/`availability_time`/`decision_time`/`valid_time`) — enough to reproduce, after the fact, exactly what was actually available at the moment each prediction was made.

**Since 2026-10-07, `ml_cooling_corrected`, `raw_forecast`, `persistence_24h`, and
`reference_ml_refit_24h` also accrue in the same per-city `.jsonl` files, each with its own
input footprint** (e.g. `persistence_24h` reads only this collector's own prior logged entry for
that city, never a forecast/anchor fetch; `reference_ml_refit_24h` loads a persisted, offline-fit
MLP artifact under `data/shadow/models/` — per city, and `unavailable` until that city is refit).
This runbook stays a one-page command reference — see the
`05-02-SUMMARY.md` through `05-05-SUMMARY.md` phase records under
`.planning/workstreams/ml-modeling/phases/05-shadow-collector-five-method-side-by-side-challenger-recordi/`
for each candidate's full input trace rather than duplicating it here (those records are
corridor-era).

## One-hour forecast offset, fixed (2026-10-13)

Before 2026-10-13 the live forecast fetch asked for `forecast_days=1` (hours `init .. init+23`) but the valid
hour is `init + 24 h`, and the lookup `frame.index.asof(valid_ts)` silently returned `init + 23 h`. Every
forecast-based candidate therefore predicted the weather for the hour before the hour it was logged under.
The request now covers 2 days and the lookup is strict (`fetch_live_forecast_for_valid_time` raises
`StaleOrMissingDataError` if the exact valid hour is absent, so the candidates report `unavailable` with a
named reason instead of using a neighbouring hour). Rows logged before the fix have no `forecast_model`
field and carry the offset, so they must not be scored or pooled with later rows (see V6 in
`confirmation_protocol_v3_per_city.md`).

## Cadence and underlying weather model (2026-10-13)

Two protocol-affecting collector changes, decided by the project owner on 2026-10-13 (decisions 6B and 11B in
`confirmation_protocol_v3_per_city.md`, which is still DRAFT) and made before the 2026-11-01 model freeze.

**1. Cadence: 4 decision cycles/day.** Cron was `0 0,6,12,18 * * *` (was `0 6,18 * * *`); since 2026-10-15 the same 00/06/12/18 UTC times are fired by cron-job.org, not GitHub (see "External trigger (2026-10-15)" below). The NWP runs on a
6-hourly UTC grid and one decision cycle yields exactly one valid time (the next grid hour 11 to 17 h ahead).
GitHub starts scheduled runs 3 to 8 h late, so expect about 2 to 4 distinct valid times per day, not a guaranteed
4; a delayed run can land on the same valid time as the next (duplicates, decision 10). The 30-minute job timeout
still fits: 4 cities x `CITY_TIMEOUT_S` (360 s) + 3 x `INTER_CITY_DELAY_S` (15 s) = 1485 s, about 25 minutes.
`forecast_shadow_healthcheck.py` needs no change: it checks that each city's latest entry is younger than
`--max-age-minutes` (default 1440), which does not depend on cadence.

**2. Underlying weather model: `gfs_seamless`.** (The external numerical weather prediction model the shadow candidates start from, not the Phase 1 "ml" ampacity forecaster.) The live forecast now comes from `config.SHADOW_LIVE_FORECAST_MODEL`
(`"gfs_seamless"`, the model the corrections were trained on), passed to `fetch_single_run(model=...)`. Before
2026-10-13 it was `ecmwf_ifs` (the provider default, `open_meteo_forecast_provider.FORECAST_MODEL_ID`, which is
frozen-experiment territory and was not changed). Each new v3 row carries a top-level `"forecast_model"` string
(additive; `schema_version` stays 3).

**Identifying pre-switch rows.** A row with no `forecast_model` field is an `ecmwf_ifs`-era row
(`config.SHADOW_LEGACY_FORECAST_MODEL`). Every reader treats a missing field that way, per line. Rows from the two
models are different series and **must not be pooled in scoring**. The README table shows an "NWP model" column and
a warning line when a city's log mixes models.

**Persistence.** `persistence_24h` only reuses a prior entry whose model equals the current cycle's, so the first
cycles after the switch report it as unavailable (cold start) until a `gfs_seamless` entry falls within the
tolerance of the decision time.

### REVERT (if GitHub Actions minute limits are hit)
- Back to 2 cycles/day: change the cron-job.org schedule to 06:00 and 18:00 UTC (before 2026-10-15 this was the cron line in `.github/workflows/shadow_collect.yml`, `0 6,18 * * *`).
- Back to the legacy model: set `SHADOW_LIVE_FORECAST_MODEL = "ecmwf_ifs"` in `backend/config.py`. New rows are then
  tagged `ecmwf_ifs` again and must not be pooled with `gfs_seamless` rows.
- The two are independent. Logged rows are never rewritten.

**Actions minutes caveat.** 4/day is about 140 runs to the cutoff at roughly 3 to 5 min each (about 700 min), double
the 2/day figure. The repository is private and the plan's monthly Linux-minute quota is **unverified**.

## External trigger (2026-10-15)

The workflow's GitHub `schedule:` trigger was removed on 2026-10-15. Scheduled runs started 3 to 8 h late,
which left the 24 h persistence anchor unavailable. The four daily runs (00, 06, 12 and 18 UTC) are now started by
a cron-job.org job that POSTs to the workflow's `dispatches` endpoint
(`.../actions/workflows/shadow_collect.yml/dispatches`). `workflow_dispatch` is the only trigger in
`shadow_collect.yml`, so manual runs from the Actions tab still work.

- **Recorded here:** the trigger mechanism and times above, and that the owner confirmed the cron-job.org job is
  configured. Its credentials (a GitHub token allowed to dispatch workflows) live in cron-job.org and are not in
  this repo.
- **Not measured:** how late runs start under the external trigger. Check `gh run list` before relying on
  timing, and note that rows from before 2026-10-15 were produced by GitHub-scheduled runs.
- **Observed (2026-10-25):** the runs actually start at 05, 11, 17 and 23 UTC (minute 00), every day from
  2026-10-21 to 2026-10-24. That is 00/06/12/18 in US Central Daylight Time, so the cron-job.org job is set
  to Central, not UTC. When daylight saving ends on 2026-11-01 the runs move to 06, 12, 18 and 00 UTC.
  Neither schedule affects the data: each run derives its decision time from the actual UTC run time and
  takes the next 6-hourly grid hour 11 to 17 h ahead (see "Cadence and underlying weather model"), so both
  give the same four valid times per day (18, 00, 06 and 12 UTC). The only effect is about 1 h less forecast
  lead time after 2026-11-01 and one 7 h gap that day. The owner left the job on Central (2026-10-25).
- **Failure mode:** if the cron-job.org job is disabled, misconfigured or its token expires, no runs start and
  nothing in the repo reports it. `forecast_shadow_healthcheck.py` only runs inside a collection run, so it
  cannot detect a missing run.
- **To return to GitHub's scheduler:** re-add `schedule: [{cron: '0 0,6,12,18 * * *'}]` to the workflow's `on:`
  block, and disable the cron-job.org job so runs are not doubled.

## Host: GitHub Actions (chosen 2026-10-06)

No persistent machine is designated or required. The collector runs on GitHub's own scheduled
runners via `.github/workflows/shadow_collect.yml` — free, no provisioning, no uptime/sleep
concerns, and its cadence is 4 cycles/day (00, 06, 12 and 18 UTC, raised from 2/day on 2026-10-13; see "Cadence and underlying weather model (2026-10-13)" below). Since 2026-10-15 the runs are started by an external cron-job.org job, not by GitHub's scheduler (see "External trigger (2026-10-15)" below).

**One-time setup (do this once, before the first scheduled run):**
1. In the GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**,
   name it exactly `SYNOPTIC_TOKEN`, paste the token value there. GitHub encrypts it; it is never
   visible in logs, never committed, and Claude has never seen or will see its value.
2. Push `.github/workflows/shadow_collect.yml` to `main` (or merge the PR that adds it). That's the
   only manual step — the schedule activates automatically once the file is on the repo's default
   branch.
3. Optionally trigger one manual run immediately via the **Actions** tab → "Shadow Collection" →
   **Run workflow**, to confirm it works before waiting for the next 06:00/18:00 UTC boundary.

**Where results land:** a dedicated `shadow-collection-data` branch (created automatically by the
workflow on its first run) — never `main`. This keeps ~100 automated commits over the collection
window off the branch anyone actually reviews. The workflow appends (never overwrites) each
`data/shadow/predictions/*.jsonl` the run produced onto the same-named file on the data branch,
re-renders the branch's root `README.md` table, and commits only if something changed (a no-op
run produces no commit via `git diff --cached --quiet`). Because the collector no longer writes
the two corridor files, the data branch's `AUSTIN_CORPUS_CHRISTI.jsonl` and
`MIDLAND_EL_PASO.jsonl` simply stop growing, and four new `{CITY}.jsonl` files appear on the
first per-city run.

**Stop:** disable the cron-job.org job (or delete or disable the workflow file on `main`, or disable it
from the Actions tab's "..." menu on the workflow page) — no server to touch, no crontab to edit.
**Restart:** re-enable the cron-job.org job (and the workflow if it was disabled); it resumes on the next
boundary. State is entirely
in the `shadow-collection-data` branch's append-only logs, nothing to reset.

**To retrieve the collected data later** (e.g. for the Nov 24 evaluation):
```bash
git fetch origin shadow-collection-data
git show shadow-collection-data:data/shadow/predictions/AUSTIN.jsonl
git show shadow-collection-data:data/shadow/predictions/CORPUS_CHRISTI.jsonl
git show shadow-collection-data:data/shadow/predictions/MIDLAND.jsonl
git show shadow-collection-data:data/shadow/predictions/EL_PASO.jsonl
```
The corridor-era history is still retrievable the same way
(`.../AUSTIN_CORPUS_CHRISTI.jsonl`, `.../MIDLAND_EL_PASO.jsonl`) but is a different schema and
must be analyzed separately, never merged with the per-city files.

## Credential setup for local/manual runs (never exposes the secret)

Not needed for the GitHub Actions path above (the secret lives in GitHub, not on your machine).
For running the collector by hand or via the fallback cron option below, either works — a real
shell export always takes precedence if both are present:
```bash
export SYNOPTIC_TOKEN=<token>          # matches this repo's existing convention
```
or a `.env` file in the repo root containing `SYNOPTIC_TOKEN=<token>` (loaded automatically via
`python-dotenv`, wired in `forecast_shadow_pipeline.py` only — never printed, logged, or committed
by any tooling in this repo).

## Exact commands (local testing, or manual runs on any machine)

**One-shot run (all four cities, in `config.LOCATIONS` order):**
```bash
cd <repo_root> && PYTHONPATH=backend .venv/bin/python3.12 backend/forecast_shadow_collect.py
```
Exit 0 = all four cities attempted (success, `unavailable` candidates, or honest fallback — each is a healthy exit). Exit 1 = a genuine code-level bug in one city. Exit 2 = a concurrent run was already in progress (lock held) — this invocation skipped, not an error.

**Process model: one child process per city (2026-10-13).** `collect_once` does not run the cities
inside its own Python process. For each city in `config.LOCATIONS`, in order, it spawns a fresh
interpreter, `python backend/forecast_shadow_collect.py --city <CITY>`, waits for it, then pauses
`INTER_CITY_DELAY_S` before the next one. The parent holds the lock, streams the children's output
into the job log and aggregates exit codes: a child that exits non-zero counts as a hard failure
(exit 1 overall); a child still running after `CITY_TIMEOUT_S` (360 s) is killed, reported on stderr
and does **not** fail the run, so the other cities' logs are still committed (four cities at the
cap plus pauses is about 24.75 minutes, inside the workflow's 30-minute timeout; a test pins this).
`--city` can be run by hand to collect a single city, but it takes **no lock** — do not run it while
the scheduled collector may be active.

*Why.* On GitHub-hosted runners the second and later `single-runs-api.open-meteo.com` requests in
one Python process timed out position-dependently (first city ok, later cities `unavailable`),
even though `fetch_single_run` already sends `Connection: close`. In the corridor-era logs the
second corridor's `raw_forecast` was `unavailable` in 9 consecutive scheduled runs from
2026-10-08 12:40 UTC to 2026-10-12, and in the first four-city run (2026-10-13 02:36 UTC) the first two
cities succeeded while Midland and El Paso timed out. The same request from a fresh process had
succeeded every time, so each city now gets a fresh process, interpreter and TLS session. This is a
mitigation matched to that evidence, not a confirmed root cause; the first scheduled runs after it
should be checked for `unavailable` forecasts by position. Other Open-Meteo calls (historical-forecast
solar proxy, archive, previous-runs) do not send `Connection: close`; the per-city process
boundary covers them too.

**Outcome of the per-city processes, and the retry that actually fixed it (2026-10-13).** The first
run with a process per city (run 38337657403's successor, 02:49 UTC) still timed out for the 3rd and 4th
city, so process state was ruled out as the cause: the identical single-runs request answered in
about 0.6 s from a developer machine for all four cities. What worked is the retry now in
`forecast_shadow_pipeline.fetch_live_forecast_for_valid_time` (`_FORECAST_FETCH_ATTEMPTS = 3`,
`_FORECAST_FETCH_TIMEOUT_S = 30`, `_FORECAST_FETCH_RETRY_DELAY_S = 20`, transport errors only; each
attempt's duration is logged at INFO). In three consecutive workflow runs after it
(38339746263, 38340170149, 38340580821) all four cities returned `ok` for `ml_wind_corrected`,
`ml_cooling_corrected` and `raw_forecast`. In two of those runs Midland's first attempt stalled for
the full 30 s read timeout and its second attempt succeeded in 0.6 s, so the stall is a transient
that a fresh attempt clears immediately; it was not seen on the other cities in those runs. The cause
of the stall on Open-Meteo's side (or the runner's IP) is **not established**; this is a mitigation
matched to the evidence. If a city's forecast candidates show `unavailable` after all three attempts,
look for `single-run fetch attempt` lines in that run's log to see each attempt's duration.

The collector keeps a fixed pause between consecutive cities' live-provider requests (never before
the first) — currently 15 seconds, so four cities add about 45 seconds of delay per run. The pause
exists because back-to-back requests to the same providers were observed to make the second
request fail regardless of which location it was. The constant is `INTER_CITY_DELAY_S = 15.0` in `forecast_shadow_collect.py` (renamed from `INTER_CORRIDOR_DELAY_S`; value unchanged).

**Health check (is the collector still running?):**
```bash
PYTHONPATH=backend .venv/bin/python3.12 backend/forecast_shadow_healthcheck.py
```
Exit 0 = every city has a log entry within the last 24h (override with `--max-age-minutes`). An all-fallback or all-`unavailable` recent run is still reported healthy — this only answers "is the scheduler firing," never "is every input source available right now." Legacy corridor logs are ignored: the check loops `config.LOCATIONS` only, so `AUSTIN_CORPUS_CHRISTI.jsonl` and `MIDLAND_EL_PASO.jsonl` can neither pass nor fail it.

## Fallback option: self-hosted cron (only if GitHub Actions ever becomes unviable)

Not the current plan — documented so this isn't lost if GitHub Actions' free minutes, reliability,
or some future constraint ever forces a move to an actual persistent host.

Cadence: **00:00, 06:00, 12:00 and 18:00 UTC daily** — same schedule as the workflow since 2026-10-13 (the previous 2/day line was `0 6,18 * * *`).

```cron
0 0,6,12,18 * * * cd <repo_root> && PYTHONPATH=backend <repo_root>/.venv/bin/python3.12 backend/forecast_shadow_collect.py >> data/shadow/collect.cron.log 2>&1
```

Install: `crontab -e`, paste the line above with `<repo_root>` replaced by the real absolute path on that host, save. This path also needs `SYNOPTIC_TOKEN` set per the credential setup above, and logs land locally in `data/shadow/predictions/` rather than the `shadow-collection-data` branch.

**Stop:** `crontab -e`, delete the line. **Restart:** re-add it; resumes on the next boundary.

## Durable storage

- **GitHub Actions path (current):** `shadow-collection-data` branch, `data/shadow/predictions/{CITY}.jsonl` (four files) — append-only, one JSON object per line, committed by the workflow after each run. Legacy `AUSTIN_CORPUS_CHRISTI.jsonl` and `MIDLAND_EL_PASO.jsonl` remain on the branch, frozen.
- **Local/fallback-cron path:** same file layout, but on disk at `data/shadow/predictions/`, git-ignored (same convention as every other generated report in this phase).

Nothing in this collector ever deletes or rewrites a prior entry, on either path, including the legacy corridor files.

## Monitoring, without inspecting any reserved outcome

The health check (above) plus `data/shadow/predictions/{CITY}.jsonl`'s own fields are sufficient to monitor: input freshness (`decision_time` vs. `logged_at`), missingness (a city with no recent entry), provider usage (`anchor_provenance.anchor_source`), per-candidate availability (`candidates.*.status`, so a city still awaiting its refit shows `unavailable` rather than looking broken), and prediction-method fallback rate (`fallback_used`) — all without ever comparing a prediction to a ground-truth outcome, reserved or otherwise.

## Evaluation day (2026-11-24): per-city confirmation run

Two one-shot tools, run in this order: the reconstructed-frame port (`forecast_shadow_confirm.py`, the HEADLINE for "which candidate to ship") and then the shadow-log scorer (`forecast_shadow_score.py`, the live-system check). The two row sources are reported separately and never pooled. Definitions, validity flags and planner defaults are in `confirmation_protocol_v3_per_city.md` and the module docstrings; nothing here changes them.

**Preconditions.**
- Pass `--protocol-status signed` only if the amendment is signed; otherwise leave the default `unsigned` (every report is then labelled exploratory). The tools never decide this.
- Do not run before 2026-11-24T00:00:00Z. Before that both tools refuse a FRESH-dated run (exit 2) before any network call or file read. Do not use `--override-reason` to get around it: it is for rehearsals and an owner-approved rerun, and it is printed in `report.json` and the `report.md` header.
- Leave every default alone (dates, `--block-lengths`, `--n-resamples`, ...); a non-default value in a FRESH run is refused without `--override-reason`.

**Any time before the instant** (permitted mechanical checks: no truth, no outcome):

    PYTHONPATH=backend .venv/bin/python backend/forecast_shadow_confirm.py --dry-run --out dry_run.json
    PYTHONPATH=backend .venv/bin/python backend/forecast_shadow_score.py --count-only --predictions-dir <exported logs> --out counts.json

Dry run first, on the day too: it makes no network call and creates no evidence directory, and prints whether the guard would refuse now, the 8 planned requests, the 12 artifact hashes and the freeze check (artifact commits dated 2026-11-01 or later are flagged).

**On the day, in order** (once each, at or after the instant):

    PYTHONPATH=backend .venv/bin/python backend/forecast_shadow_confirm.py --protocol-status <signed|unsigned>
    # export the logs as in the docstring of forecast_shadow_score.py (git show origin/shadow-collection-data:... per city), then:
    PYTHONPATH=backend .venv/bin/python backend/forecast_shadow_score.py --predictions-dir <exported logs> --source-commit $(git rev-parse origin/shadow-collection-data) --protocol-status <signed|unsigned>

**One-shot marker.** Each run writes `data/shadow/evaluation/{row_source}_{UTC time}/`. Its first file, `run_started.json` (guard record and config), is written after the guard passes and before any request. A second FRESH run of the same row source is refused (exit 2) if any `run_started.json` with basis FRESH and that row source exists, even if that run crashed and wrote no report. Never re-run, retry or extend a run after seeing its output; a rerun needs an owner-approved `--override-reason`.

**What each report states** (`report.json` and `report.md`; every number is reanalysis-derived, never sensor-validated): n, effective sample size and the ~590 / ~1,575 precision targets (unmet is expected) first; per-city bias, MAE, RMSE and median absolute error; the 9-test pooled city-clustered Holm family; per-city comparisons (descriptive, uncorrected); minimum detectable differences; the evidence level against `raw_forecast` at 5 A and the default action (labelled "headline decision" for the port, "live-system check" for the scorer); the exploratory label when unsigned; and that calibrated overrating risk and retained capacity were not measured and no 8% ceiling was applied.

**Refusal or a failed city.**
- Exit 2 (`refused: ...`): nothing was fetched and no directory was created. Fix the cause named in the message (clock, log directory, argument); do not override.
- A failed city (previous-runs or archive HTTP error, structural check) is named in the report with its error and is not retried; the other cities are scored. Report it as failed.
- Port exit 1 (leakage probe failed) writes no `report.json`. Do not re-run to get one; archive the evidence directory and tell the owner.

**Archive and cite.** Both evidence directories (`report.json`, `report.md`, `run_started.json`, `http/` bodies and meta, and `frames/` for the port) are not git-ignored: `git add data/shadow/evaluation` and commit them. In the write-up cite both directory names and the output of

    PYTHONPATH=backend .venv/bin/python -c "import json,sys; import forecast_shadow_decision as d; print(d.combined_summary(json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))))" <port report.json> <scorer report.json>

The headline decision comes from the port's report; the live-system check never changes it, and no count is ever added across the two sources.

## Artifact hash manifest (recorded 2026-10-13)

`data/shadow/models/ARTIFACT_HASHES.sha256` holds the sha256 of the 12 per-city shadow artifacts
(`ml_wind_corrected`, `ml_cooling_corrected`, `reference_ml_refit_24h` x AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO).
Check it from the repo root with `shasum -a 256 -c data/shadow/models/ARTIFACT_HASHES.sha256` (all 12 must print OK).
Nothing is refit after the 2026-11-01 freeze based on FRESH data; any artifact change after that date must be
reported as a protocol deviation and the manifest not silently regenerated. The legacy corridor-named artifacts are
not in the manifest.

## gfs_seamless single-run publication lag (measured 2026-10-14)

`data/publication_lag_check/` (script `poll_lag.py`, workflow `.github/workflows/publication_lag_check.yml`,
manual dispatch, weather fetches only). Polling Austin every 5 minutes from init:

| Run (init UTC) | Last "unavailable" | First complete response | Lag |
|---|---|---|---|
| 2026-10-13 18Z | not observed (already served at the first poll) | 4.67 h old | at most 4.67 h |
| 2026-10-14 00Z (GitHub runner) | 3.148 h | 3.232 h | between 3.15 and 3.23 h (about 3.2 h) |

The earlier bracket (1.1 h to 7.05 h) is replaced by about 3.2 h for the 00Z run; further runs (06Z, 12Z) are added below
when measured. The collector requests runs that are 7 to 13 h old, so the margin over the measured lag is at least
3.8 h, and the 6 h default (`_DEFAULT_PUBLICATION_LAG_HOURS`) is conservative. No collector change is proposed.
One city (Austin) and a small number of runs; a single run's lag can vary.
