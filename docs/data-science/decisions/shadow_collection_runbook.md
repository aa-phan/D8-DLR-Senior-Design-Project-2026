# Shadow Collection Runbook

**Status: experimental/shadow path. Never invoked by production (`dlr_pipeline.py` or any other
caller). Operating this collector changes nothing about any operational rating decision.**

This is the one-page operational reference for running `backend/forecast_shadow_collect.py`
continuously. The full technical trace (input contract, failure-attribution design, live-run
evidence) lives in `forecast_correction_followup_audit.md`'s "Shadow prototype" section — this
runbook is deliberately just the commands and host requirements, not the rationale.

## Verified input contract (summary)

| Variable | Source | Fallback |
|---|---|---|
| Forecast wind, temperature, solar (valid-time) | Open-Meteo forecast API (`fetch_live_forecast_for_valid_time`) | None — single provider; a null/missing row raises and the prediction falls back to `raw_forecast` |
| Observed anchor wind (now, per endpoint city) | TCEQ CAMS (primary) | Synoptic station (automatic, on an unusable TCEQ row) |

Two distinct, never-conflated failure types in every log entry:
- **Provider fallback** (TCEQ → Synoptic succeeded) — visible in `input_provenance.anchor_provenance.<city>.anchor_source`. The prediction is still a genuine `ml_wind_corrected` result; `fallback_used` stays `false`.
- **Prediction-method fallback** (no provider anywhere supplied a usable value) — `fallback_used: true`, `fallback_reason` names exactly which provider(s) failed and how, `method` reads `raw_forecast`.

Every log entry additionally preserves the issued ampacity, `model_version`, full `input_provenance`, and all four timestamps (`initialization_time`/`availability_time`/`decision_time`/`valid_time`) — enough to reproduce, after the fact, exactly what was actually available at the moment each prediction was made.

## Host requirements

- Any host (Linux or macOS) with network access to Open-Meteo, TCEQ (`daily_summary.pl`, unauthenticated), and Synoptic.
- Python 3.12, this repo's `.venv` per `requirements.txt` (includes `python-dotenv` as of 2026-10-06).
- A `SYNOPTIC_TOKEN` credential (see below). No TCEQ credential needed.
- Persistent uptime for the life of the collection window (through **2026-11-24**, the fixed evaluation date) — a machine that regularly sleeps or reboots unpredictably will produce collection gaps. Gaps are handled gracefully (logged, not fatal) but a host that's reliably on is still what makes the data useful.

## Credential setup (never exposes the secret)

Either works — a real shell export always takes precedence if both are present:
```bash
export SYNOPTIC_TOKEN=<token>          # matches this repo's existing convention
```
or a `.env` file in the repo root containing `SYNOPTIC_TOKEN=<token>` (loaded automatically via `python-dotenv`, wired in `forecast_shadow_pipeline.py` only — never printed, logged, or committed by any tooling in this repo).

## Exact commands

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

## Scheduler (cron, chosen for Linux/macOS portability)

Cadence: **06:00 and 18:00 UTC daily** (00:00/12:00 CDT currently) — roughly matches the anchor station's own refresh cadence without over-polling.

```cron
0 6,18 * * * cd <repo_root> && PYTHONPATH=backend <repo_root>/.venv/bin/python3.12 backend/forecast_shadow_collect.py >> data/shadow/collect.cron.log 2>&1
```

Install: `crontab -e`, paste the line above with `<repo_root>` replaced by the real absolute path on that host, save.

**Stop:** `crontab -e`, delete the line (or `crontab -r` to remove the whole crontab — only do this if nothing else is scheduled on that host).
**Restart:** re-add the same line; collection resumes on the next 06:00/18:00 UTC boundary. No state needs to be reset — the collector is stateless between runs except for the append-only logs.

## Durable storage

`data/shadow/predictions/<corridor>.jsonl` — append-only, one JSON object per line, git-ignored (same convention as every other generated report in this phase). Nothing in this collector ever deletes or rewrites a prior entry.

## Monitoring, without inspecting any reserved outcome

The health check (above) plus `data/shadow/predictions/*.jsonl`'s own fields are sufficient to monitor: input freshness (`decision_time` vs. `logged_at`), missingness (a corridor with no recent entry), provider usage (`anchor_provenance.*.anchor_source`), and prediction-method fallback rate (`fallback_used`) — all without ever comparing a prediction to a ground-truth outcome, reserved or otherwise.
