# Shadow Collection Runbook

**Status: experimental/shadow path. Never invoked by production (`dlr_pipeline.py` or any other
caller). Operating this collector changes nothing about any operational rating decision.**

This is the one-page operational reference for running `backend/forecast_shadow_collect.py`
continuously. The full technical trace (input contract, failure-attribution design, live-run
evidence) lives in `forecast_correction_followup_audit.md`'s "Shadow prototype" section — this
runbook is deliberately just the commands and host requirements, not the rationale.

## Five-method collection (D-08)

**Five-method collection began 2026-10-07.** From this date forward, every cycle's log entry
records all five real (non-oracle) 24-hour-lead candidates side by side, not just one:
`ml_wind_corrected` (unchanged provisional default — the six-field top-level mirror any legacy
single-method reader, e.g. `forecast_shadow_healthcheck.py`, still sees unmodified),
`ml_cooling_corrected`, `raw_forecast`, `persistence_24h`, and `reference_ml_refit_24h`. Each
candidate carries its own `status`/`ampacity_amps`/`fallback_used`/`fallback_reason`/
`model_version`/`input_provenance`/`reason`, nested under a `candidates` object in a
`schema_version: 2` record (`forecast_shadow_pipeline.log_cycle_predictions`). Rows already
committed to `shadow-collection-data` before this date keep their old flat, single-candidate
shape forever — no migration, no backfill, no rewrite of historical rows (05-01-SUMMARY.md's
approved historical-data strategy). Both `forecast_shadow_render_table.py` (the README table
generator) and `forecast_shadow_healthcheck.py` read either shape correctly, per line, forever.

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

## Verified input contract (summary)

| Variable | Source | Fallback |
|---|---|---|
| Forecast wind, temperature, solar (valid-time) | Open-Meteo forecast API (`fetch_live_forecast_for_valid_time`) | None — single provider; a null/missing row raises and the prediction falls back to `raw_forecast` |
| Observed anchor wind (now, per endpoint city) | TCEQ CAMS (primary) | Synoptic station (automatic, on an unusable TCEQ row) |

Two distinct, never-conflated failure types in every log entry:
- **Provider fallback** (TCEQ → Synoptic succeeded) — visible in `input_provenance.anchor_provenance.<city>.anchor_source`. The prediction is still a genuine `ml_wind_corrected` result; `fallback_used` stays `false`.
- **Prediction-method fallback** (no provider anywhere supplied a usable value) — `fallback_used: true`, `fallback_reason` names exactly which provider(s) failed and how, `method` reads `raw_forecast`.

Every log entry additionally preserves the issued ampacity, `model_version`, full `input_provenance`, and all four timestamps (`initialization_time`/`availability_time`/`decision_time`/`valid_time`) — enough to reproduce, after the fact, exactly what was actually available at the moment each prediction was made.

**Since 2026-10-07, `ml_cooling_corrected`, `raw_forecast`, `persistence_24h`, and
`reference_ml_refit_24h` also accrue in the same per-corridor `.jsonl` files, each with its own
input footprint** (e.g. `persistence_24h` reads only this collector's own prior logged entry,
never a forecast/anchor fetch; `reference_ml_refit_24h` loads a persisted, offline-fit MLP
artifact under `data/shadow/models/`). This runbook stays a one-page command reference — see the
`05-02-SUMMARY.md` through `05-05-SUMMARY.md` phase records under
`.planning/workstreams/ml-modeling/phases/05-shadow-collector-five-method-side-by-side-challenger-recordi/`
for each candidate's full input trace rather than duplicating it here.

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
window off the branch anyone actually reviews. Each run commits only if the logs changed since the
last run; a day where every corridor hit the exact same fallback twice produces no-op commits
naturally (identical JSON lines dedupe via `git diff --cached --quiet`).

**Stop:** delete or disable the workflow file on `main` (or disable it from the Actions tab's "..."
menu on the workflow page) — no server to touch, no crontab to edit.
**Restart:** re-enable the workflow; it resumes on the next scheduled boundary. State is entirely
in the `shadow-collection-data` branch's append-only logs, nothing to reset.

**To retrieve the collected data later** (e.g. for the Nov 24 evaluation):
```bash
git fetch origin shadow-collection-data
git show shadow-collection-data:data/shadow/predictions/AUSTIN_CORPUS_CHRISTI.jsonl
```

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

**One-shot run (both corridors):**
```bash
cd <repo_root> && PYTHONPATH=backend .venv/bin/python3.12 backend/forecast_shadow_collect.py
```
Exit 0 = both corridors attempted (success or honest fallback, either is a healthy exit). Exit 1 = a genuine code-level bug in one corridor. Exit 2 = a concurrent run was already in progress (lock held) — this invocation skipped, not an error.

**Health check (is the collector still running?):**
```bash
PYTHONPATH=backend .venv/bin/python3.12 backend/forecast_shadow_healthcheck.py
```
Exit 0 = every corridor has a log entry within the last 24h (override with `--max-age-minutes`). An all-fallback recent run is still reported healthy — this only answers "is the scheduler firing," never "is every input source available right now."

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

- **GitHub Actions path (current):** `shadow-collection-data` branch, `data/shadow/predictions/<corridor>.jsonl` — append-only, one JSON object per line, committed by the workflow after each run.
- **Local/fallback-cron path:** same file layout, but on disk at `data/shadow/predictions/`, git-ignored (same convention as every other generated report in this phase).

Nothing in this collector ever deletes or rewrites a prior entry, on either path.

## Monitoring, without inspecting any reserved outcome

The health check (above) plus `data/shadow/predictions/*.jsonl`'s own fields are sufficient to monitor: input freshness (`decision_time` vs. `logged_at`), missingness (a corridor with no recent entry), provider usage (`anchor_provenance.*.anchor_source`), and prediction-method fallback rate (`fallback_used`) — all without ever comparing a prediction to a ground-truth outcome, reserved or otherwise.
