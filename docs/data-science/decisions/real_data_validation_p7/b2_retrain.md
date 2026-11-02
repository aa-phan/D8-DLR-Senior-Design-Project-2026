# B2 retrain record: ml forecast models retrained on projected wind (plan 07-14, D-14)

## In plain English

The `ml` forecast model used to be trained on the raw measured wind speed but, when it runs live, it is handed the wind component that blows across the line (the "projected" wind). That mismatch was finding B2. Plan 07-19 fixed the training code so the model now learns from the same projected wind it is later served. This plan ran the retrain: all four cities got a fresh model, trained on 2023 to 2025 weather from Open-Meteo, under the final rating configuration (`v3-powersystems-2026-11-02`, AUSTIN at Drake 100 C, the other three at Drake 75 C). The new models are committed on local `main` with a regenerated hash manifest. They are **not pushed and not live**; promotion is the owner's decision in 07-18.

## Run

| Item | Value |
|---|---|
| Date (UTC) | 2026-11-02 |
| Rating configuration | `RATING_CONFIG_VERSION` = `v3-powersystems-2026-11-02` |
| Command | `PYTHONPATH=backend .venv/bin/python backend/forecast_training.py --bakeoff` |
| Years used | 2023, 2024, 2025 (the last three complete calendar years; 2023-01-01 to 2025-12-31 23:00 UTC, 26304 hourly rows per city). No row on or after 2026-09-30 (FRESH) is used. |
| Log | `data/models/retrain_logs/forecast_bakeoff_b2_2026-11-02.log` (git-ignored) |
| First attempt | `data/models/retrain_logs/forecast_bakeoff_b2_2026-11-02_attempt1_midland_timeout.log`: MIDLAND failed to assemble on an Open-Meteo read timeout; the whole command was re-run so the committed models and the bake-off report come from one clean run |
| Archive of the previous models, frames and report | `data/models/retrain_logs/pre_b2_2026-11-02/` (git-ignored) |
| Commit of the models and manifest | `e0a00a9` (`feat(07-14): retrain ml on projected wind (B2) with a new live manifest`) |
| Status | Not pushed; promotion is the owner's decision (07-18) |

## Bake-off results per city (MAE in amps on the held-out rows; 21910 rows for the two candidates, 26292 for the baselines)

| City | Winner (persisted) | HistGradientBoosting | MLP | naive | ewm |
|---|---|---|---|---|---|
| AUSTIN | MLPRegressor | 79.490 | **78.675** | 81.379 | 108.995 |
| CORPUS_CHRISTI | HistGradientBoostingRegressor | **59.844** | 60.103 | 62.410 | 106.768 |
| MIDLAND | MLPRegressor | 78.477 | **76.763** | 79.365 | 131.448 |
| EL_PASO | MLPRegressor | 77.031 | **76.108** | 78.265 | 100.962 |

RMSE and row counts are in `data/models/bakeoff_report.json` (local, git-ignored) and the log. Every winner has a lower MAE than the naive baseline in this training-time bake-off (note the baselines are scored on more rows than the two candidates, so the comparison is indicative only). It is not the September replay result; that is reported in `tables.md`.

## Wind-feature check (new frame against the archived pre-B2 frame, joined on `datetime_utc`)

| City | Rows old | Rows new | Shared rows | new wind <= old wind + 1e-9 on every row | Rows where wind differs (> 1e-9) | Mean wind old (m/s) | Mean wind new (m/s) |
|---|---|---|---|---|---|---|---|
| AUSTIN | 26304 | 26304 | 26304 | yes | 99.98% | 3.333 | 1.649 |
| CORPUS_CHRISTI | 26304 | 26304 | 26304 | yes | 100.00% | 4.560 | 2.533 |
| MIDLAND | 26304 | 26304 | 26304 | yes | 100.00% | 4.431 | 3.331 |
| EL_PASO | 26304 | 26304 | 26304 | yes | 99.95% | 3.212 | 1.501 |

The projection never exceeds the measured speed, and it differs on nearly every row (the few equal rows are calm hours).

## Model hashes (SHA-256)

| Model | Old (2026-10-24 manifest) | New |
|---|---|---|
| forecast_AUSTIN.joblib | dd6d540d0ccd8403f6b857001919ffa1505e0dc25a0c4f9e3789a3699804cc7c | 60b7e1349ccfcd2e3d6ffafd4ce582dbd3da01baae6848b5c4ebe9be005399e7 |
| forecast_CORPUS_CHRISTI.joblib | d4527fefb591301e54d5cf536bfd86ff44cc70f434e62402a45fd9d8b10e535e | 43d9115f2b96ce6ea2392a959c8f6c2414d5d2c9d32bf22140848cf30cbfb92d |
| forecast_MIDLAND.joblib | 0a62d94ed4402bfa294619969aedd4f4ab51b64c9736f89c4241abe776e81606 | 875fdbb394ad4737802321f9a9798652cce13e56833eb448b7dbd7ff978669c4 |
| forecast_EL_PASO.joblib | 3cd066e0c3fd31f5a786323282a75ec9ca806d10b190ac83fb1ff1fa285731c3 | 3dc69b7e0f95e53f1c9ae539728d82d66f736bccef208db612be8c635b0b583e |

The four anomaly model hashes in `LIVE_ARTIFACT_HASHES.sha256` are byte-identical to the previous manifest (the manifest diff touches only the date comment and the four forecast lines). `PYTHONPATH=backend .venv/bin/python backend/dlr_live_check_models.py` (check mode) prints `OK: all 8 live model artifacts present and match data/models/LIVE_ARTIFACT_HASHES.sha256`.

## Not pushed

These models are committed locally only. Pushing them would change every live forecast and its `forecast_model_sha256`. Promotion is the owner's decision (plan 07-18). A rollback copy of the previous models is in `data/models/retrain_logs/pre_b2_2026-11-02/` and in git history before `e0a00a9`.
