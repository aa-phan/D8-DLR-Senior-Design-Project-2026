---
phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
plan: 14
subsystem: forecast-models, real-data-validation
tags: [forecast_training, bakeoff, projected-wind, live-manifest, replay-fidelity, REVAL-01]
status: complete

requires:
  - phase: 07 (plan 07-19)
    provides: B2 code fix, ml trains on the projected wind it is served
  - phase: 07 (plan 07-08)
    provides: B5 naive band for G6 and the band-engagement table
  - phase: 07 (plan 07-11)
    provides: final production configuration v3-powersystems-2026-11-02 (AUSTIN Drake 100 C)
provides:
  - four retrained per-city ml forecast models plus a regenerated LIVE_ARTIFACT_HASHES.sha256 (committed on local main, not pushed)
  - REVAL-01 re-run of the Phase 3 validation on 2026-09-08..2026-09-28 (ml and naive replays, 0 fidelity mismatches) with tables, manifest and B2 record
affects: [07-17 go/no-go, 07-18 promotion]

plan_head_before: 27d72693fad81d12beaa7fbcb394844d45360249
plan_head_after: 03253d1062a6706d486ec6144807c389fbd10ef2
commits: 3
actuals:
  tokens: 21000
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns: [control replay in a temporary git worktree at the commit before a configuration change]

key-files:
  created:
    - docs/data-science/decisions/real_data_validation_p7/ (b2_retrain.md, README.md, tables.md, manifest.json, report_meta.json, replay_fidelity.json, fidelity_ml_p7.json, fidelity_naive_p7.json, fidelity_ml_control_p7.json, val01_*.csv, val02_*.csv)
  modified:
    - data/models/forecast_AUSTIN.joblib
    - data/models/forecast_CORPUS_CHRISTI.joblib
    - data/models/forecast_MIDLAND.joblib
    - data/models/forecast_EL_PASO.joblib
    - data/models/LIVE_ARTIFACT_HASHES.sha256

key-decisions:
  - "Re-ran the whole bakeoff after an Open-Meteo read timeout on MIDLAND instead of patching MIDLAND alone, so the models, frames and bakeoff_report.json come from one clean run"

requirements-completed: [REVAL-01]
---

# Phase 7 Plan 14: B2 retrain and Phase 3 validation re-run Summary

The four ml forecast models are retrained on projected wind under the final configuration and committed locally with a new manifest, and the September validation is re-run offline with zero replay-fidelity mismatches.

## In plain English

The ml forecast model was being trained on one kind of wind and used on another. Plan 07-19 fixed the code; this plan did the retrain for all four cities (2023 to 2025 Open-Meteo weather, final conductor settings), recorded the old and new model fingerprints, and committed the new models together with their fingerprint list. Nothing was pushed, so the live system still runs the old models until the owner decides in 07-18. Then it replayed the recorded September window offline with the new models (and again with the simple "naive" forecast) to refresh the Phase 3 tables. Both replays reproduce the recorded run with no mismatches. No row from the FRESH period (2026-09-30 onward) was read.

## Tasks

| Task | Name | Commit | Files |
|---|---|---|---|
| 1 | Retrain the four ml models on projected wind, regenerate the manifest (B2) | `e0a00a9` (models + manifest), `dae287a` (b2_retrain.md) | four forecast joblibs, LIVE_ARTIFACT_HASHES.sha256, real_data_validation_p7/b2_retrain.md |
| 2 | Re-run the Phase 3 validation offline and commit the tables | `03253d1` | real_data_validation_p7/ (tables, manifest, fidelity files, README) |

## What was found

- **Retrain.** Winners: AUSTIN MLP (MAE 78.7), CORPUS_CHRISTI HistGradientBoosting (59.8), MIDLAND MLP (76.8), EL_PASO MLP (76.1); each below the naive baseline's MAE. Per frame, new wind_speed is at most the archived pre-B2 value on every one of the 26304 rows in every city and differs on 99.95 to 100 percent of rows. The four anomaly model hashes in the manifest are byte-identical to before. `dlr_live_check_models.py` prints `OK: all 8 live model artifacts present and match`.
- **Re-run, fidelity.** ml replay and naive replay: mismatches=0 (compared 1683, excluded 333). Control replay at `2c48f9e` (commit before the Power Systems adoption): mismatches=0, compared 2016, excluded 0. The 333 excluded steps are all AUSTIN and are the by-construction effect of its conductor change (research Pitfall 14): the archived rating (Drake 75 C) contradicts the recomputation at the new production conductor (Drake 100 C), so those original steps are classed ERROR and excluded. This is documented in the README.
- **Re-run, results.** ml MAE now beats naive in all four cities of this window (AUSTIN 84.6 vs 87.6, CORPUS_CHRISTI 61.3 vs 62.9, MIDLAND 80.2 vs 80.3, EL_PASO 112.6 vs 117.3 A), and the Phase 3 upward bias of ml is gone (bias 0.1 to -21.1 A, was 41.9 to 87.6). Differences are small against the interval widths (260 to 470 A); that is for D-15 at 07-17, not decided here. B5 band share per city: AUSTIN 0.9875, CORPUS_CHRISTI 0.9405, MIDLAND 0.9366, EL_PASO 1.0. B4 detector: CORPUS_CHRISTI trip rate is unchanged at 0.1101 (37 of 336, all the model branch, identical under ml and naive); the other cities are 0 of 321 (AUSTIN), 2 of 268 (MIDLAND, ml only), 1 of 336 (EL_PASO).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Open-Meteo read timeout on MIDLAND during the first bakeoff run**
- **Found during:** Task 1
- **Issue:** `forecast_training.py --bakeoff` printed `MIDLAND: FAILED to assemble training frame` (read timeout, 60 s) and wrote a bakeoff_report.json without MIDLAND. No source fault; a transient network failure.
- **Fix:** Re-ran the whole `--bakeoff` command so the three already-written models, the frames and the report come from one run. The first log is kept as `data/models/retrain_logs/forecast_bakeoff_b2_2026-11-02_attempt1_midland_timeout.log`. Because the first run overwrote the live forecast files for three cities before the second overwrote them again, the pre-B2 archive (made before the first run) is the rollback source, not the working tree. Results of the first run for the three cities were identical (same MAEs) to the second.
- **Files modified:** none beyond the plan's list
- **Commit:** `e0a00a9`

**2. [Documentation] manifest.json `command` field is not runnable for a replay**
- **Issue:** `build_manifest` builds `command` with the Phase 3 backfill wrapper around whatever argv follows `--`. For a replay that text is misleading. I did not edit the generated manifest and did not change the harness (the plan forbids touching it on mismatch and asks for the generated file).
- **Handling:** README.md in the same folder records the true commands and says `backfill_argv` is the trustworthy field.
- **Commit:** `03253d1`

**3. [Additions] README.md and fidelity_ml_control_p7.json added to real_data_validation_p7/**
- The plan asks for the control replay result and the per-city by-construction note to be reported; they are stored as README.md and `fidelity_ml_control_p7.json`, extra to the required files.

**Total deviations:** 1 Rule 3 transient fix, 2 documentation additions. No impact on plan outcomes.

## Safety checks

- Window: replay 2026-09-08T00:00:00Z..2026-09-28T23:00:00Z (before FRESH_BASIS_START 2026-09-30); training years 2023-2025 (complete past years). Input archive sha256 `18f999aa...a25cf` verified. `forecast_shadow_confirm.py` and `forecast_shadow_score.py` were not run. `git diff --stat 27d7269..HEAD -- data/shadow data/models/conductor_refit` is empty.
- Not pushed: `origin/main` is `e970549...`, and `git branch -r --contains e0a00a9` prints nothing. No Supabase writes, no deploys.
- The temporary control worktree (`/tmp/wt_07_14_control`) was removed; the git-ignored replay outputs (`*_p7*` under data/historical, retrain_logs, `pre_b2_2026-11-02/`) stay local.
- STATE.md, ROADMAP.md and REQUIREMENTS.md were not touched (the orchestrator owns them).
- Full suite once before this SUMMARY: 2570 passed, 82 skipped.

## Known Stubs

None.

## Threat Flags

None. The plan's two mitigations hold: models and manifest are one commit and check mode passes (T-07-29); no FRESH row is read (T-07-30).

## Next

07-17 (go/no-go) can read `real_data_validation_p7/` for the D-15 ml-versus-naive comparison, the B4 trip table and the B5 band share. 07-18 owns promotion of the retrained models; rollback artifacts are in `data/models/retrain_logs/pre_b2_2026-11-02/` and git history before `e0a00a9`.

## Self-Check: PASSED

Verified: the four forecast joblibs, LIVE_ARTIFACT_HASHES.sha256, b2_retrain.md, README.md, tables.md, manifest.json, val02_g6_band_by_city.csv, fidelity_ml_p7.json and fidelity_naive_p7.json exist; commits `e0a00a9`, `dae287a` and `03253d1` are ancestors of HEAD; `dlr_live_check_models.py` prints OK.
