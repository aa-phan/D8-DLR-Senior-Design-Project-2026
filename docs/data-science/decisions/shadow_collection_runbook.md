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

**Evidence base and the 2026-11-24 date.** The fixed 2026-11-24 evaluation date was set against
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

## Host: GitHub Actions (chosen 2026-10-06)

No persistent machine is designated or required. The collector runs on GitHub's own scheduled
runners via `.github/workflows/shadow_collect.yml` — free, no provisioning, no uptime/sleep
concerns, and it matches the existing twice-daily cadence exactly (`cron: '0 6,18 * * *'`).

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

**Stop:** delete or disable the workflow file on `main` (or disable it from the Actions tab's "..."
menu on the workflow page) — no server to touch, no crontab to edit.
**Restart:** re-enable the workflow; it resumes on the next scheduled boundary. State is entirely
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

Cadence: **06:00 and 18:00 UTC daily** (00:00/12:00 CDT currently) — same schedule as the workflow.

```cron
0 6,18 * * * cd <repo_root> && PYTHONPATH=backend <repo_root>/.venv/bin/python3.12 backend/forecast_shadow_collect.py >> data/shadow/collect.cron.log 2>&1
```

Install: `crontab -e`, paste the line above with `<repo_root>` replaced by the real absolute path on that host, save. This path also needs `SYNOPTIC_TOKEN` set per the credential setup above, and logs land locally in `data/shadow/predictions/` rather than the `shadow-collection-data` branch.

**Stop:** `crontab -e`, delete the line. **Restart:** re-add it; resumes on the next boundary.

## Durable storage

- **GitHub Actions path (current):** `shadow-collection-data` branch, `data/shadow/predictions/{CITY}.jsonl` (four files) — append-only, one JSON object per line, committed by the workflow after each run. Legacy `AUSTIN_CORPUS_CHRISTI.jsonl` and `MIDLAND_EL_PASO.jsonl` remain on the branch, frozen.
- **Local/fallback-cron path:** same file layout, but on disk at `data/shadow/predictions/`, git-ignored (same convention as every other generated report in this phase).

Nothing in this collector ever deletes or rewrites a prior entry, on either path, including the legacy corridor files.

## Monitoring, without inspecting any reserved outcome

The health check (above) plus `data/shadow/predictions/{CITY}.jsonl`'s own fields are sufficient to monitor: input freshness (`decision_time` vs. `logged_at`), missingness (a city with no recent entry), provider usage (`anchor_provenance.anchor_source`), per-candidate availability (`candidates.*.status`, so a city still awaiting its refit shows `unavailable` rather than looking broken), and prediction-method fallback rate (`fallback_used`) — all without ever comparing a prediction to a ground-truth outcome, reserved or otherwise.
