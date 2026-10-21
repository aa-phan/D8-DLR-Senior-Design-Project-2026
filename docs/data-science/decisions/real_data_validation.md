# Real-data validation and production go/no-go (2026-10, production-pipeline Phase 3)

**Status:** the measurements are complete and the owner's decision was made and signed on 2026-10-21: NO-GO,
blocking on B1, B2, B4 and B5 (see "Decision"; plan 03-05). Nothing was
changed to produce these numbers: no rating bound, static rating, line bearing, conductor model, fallback
policy, forecast method, quantile, control limit or model file. Findings below are recorded with options for
the owner; none is applied.

**Provisional:** every rating value in this note depends on provisional static ratings, plausibility bounds and
assumed line bearings (OD-5, `.planning/workstreams/production-pipeline/REQUIREMENTS.md`; `config.py` comments;
`line_bearing_check.md`), and on one Drake ACSR conductor model with `max_temp_c` 75 and `elevation_m` 900 for
every city (`config.DEFAULT_CONDUCTOR_CONFIG_KWARGS`; the 75 C limit has no documented source, PROV-01). The
numbers describe what the pipeline did with those assumptions. They are not validated line ratings.

Scope: four cities (AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO), one real backfill, 14 scored days after a 7-day
warm-up. All tables below are copied verbatim from `real_data_validation/tables.md` (the output of one
`report` run); the numbers in the prose come from those tables, from `report_meta.json`, `manifest.json`,
`run_completeness.csv`, `replay_fidelity.json`, `val02_g6_trips.csv`, or are labelled as exact counts read from
the git-ignored trace (`backfill_trace/1`, listed under Backfill record).

## Backfill record

- **Window.** Hourly steps from 2026-09-08T00:00:00Z to 2026-09-28T23:00:00Z, 504 steps per city (2016
  city-steps). Warm-up: the first 168 hours (2026-09-08T00:00Z to 2026-09-14T23:00Z, 168 steps per city; the
  archive started empty). Scored window: 2026-09-15T00:00:00Z to 2026-09-28T23:00:00Z, 14 days, 336 steps per
  city. The window ends before 2026-09-29T00:00Z, the anti-peeking cutoff used for this phase, and after the
  models' 2023-2025 training years.
- **Exact owner command** (`manifest.json`, `command`):

```
cd /Users/aphan/Senior_Design && PYTHONPATH=backend /Users/aphan/Senior_Design/.venv/bin/python -c "from dotenv import load_dotenv; load_dotenv('/Users/aphan/Senior_Design/.env'); import sys, backfill_archive; sys.exit(backfill_archive.main(['--start', '2026-09-08T00:00:00Z', '--end', '2026-09-28T23:00:00Z', '--step-hours', '1', '--forecast-method', 'ml', '--archive-path', 'data/historical/real_data_validation_2026-09-08_2026-09-28.csv', '--log-path', 'data/historical/real_data_validation_2026-09-08_2026-09-28_log.csv', '--trace-path', 'data/historical/real_data_validation_2026-09-08_2026-09-28_trace.jsonl']))"
```

- **Working directory:** `/Users/aphan/Senior_Design` (the main checkout). Forecast method `ml`; providers composed
  (TCEQ, ASOS and Synoptic for air temperature; TCEQ for wind; Open-Meteo for solar).
- **Files** (git-ignored, main checkout, `manifest.json` `files`):

| File | Path | Bytes | sha256 |
| --- | --- | --- | --- |
| archive | `data/historical/real_data_validation_2026-09-08_2026-09-28.csv` | 212702 | `18f999aac44540138cfb2a2d1c7f624688e66d261e391a01b036970b8bfa25cf` |
| trace | `data/historical/real_data_validation_2026-09-08_2026-09-28_trace.jsonl` | 1988914 | `4999c5cf2aa4b58b77f05b1a537c917e4c8a9487cd6a31fe2bf25f17630d781d` |
| log | `data/historical/real_data_validation_2026-09-08_2026-09-28_log.csv` | 114390 | `a9662fb795fc09d33d79490f43c1c8b6889138993be217f35d33835b22716180` |
| console | `data/historical/real_data_validation_2026-09-08_2026-09-28_console.txt` | 984282 | `113d25fc718547e4c85db0feb9fae1722f16787613bd50dfed9c3fa025857cf8` |

- **Archive rows per city:** 504 each (AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO). The archive sha256 was
  recomputed from the file and matched `manifest.json` before any analysis in this plan.
- **Model files** (`manifest.json` `models`, sha256):

| Model file | sha256 |
| --- | --- |
| `forecast_AUSTIN.joblib` | `dd6d540d0ccd8403f6b857001919ffa1505e0dc25a0c4f9e3789a3699804cc7c` |
| `forecast_CORPUS_CHRISTI.joblib` | `d4527fefb591301e54d5cf536bfd86ff44cc70f434e62402a45fd9d8b10e535e` |
| `forecast_MIDLAND.joblib` | `0a62d94ed4402bfa294619969aedd4f4ab51b64c9736f89c4241abe776e81606` |
| `forecast_EL_PASO.joblib` | `3cd066e0c3fd31f5a786323282a75ec9ca806d10b190ac83fb1ff1fa285731c3` |
| `anomaly_AUSTIN.joblib` | `2ecaead8d2be2fb7bcc179bef82958b536f73f34b6959b9b63a22f0faa83f6a4` |
| `anomaly_CORPUS_CHRISTI.joblib` | `9fbc26ab8907a033e013b4e67881b4bc0d399de74f912ba7ee9423fa920c8cc0` |
| `anomaly_MIDLAND.joblib` | `d1b2ac321a79ec77a6d16314c3a2b8cfc6cd370e38a526b4370cc758b03c4f9b` |
| `anomaly_EL_PASO.joblib` | `d4431d56fabd8514df228b585ccc5c156a2c12b7653f57363236c9c79a7aaf37` |

- **Git HEAD** of the run: `175b32bc443b4128195dcac70b3d96a60c653a1a`, `backend/` clean (`backend_dirty` false).
- **Resumed:** no. The console summary reports `steps already archived (skipped): 0`; the run was not interrupted.
- **Smoke run:** a 2-step run before the full run (separate `real_data_validation_smoke*` files, not part of the
  analysis): all four cities archived 2 steps, 0 errors.
- **Completeness** (`run_completeness.csv`, produced by the `completeness` subcommand):

| city | expected_steps | trace_records | archive_rows | log_rows | exhausted | errors | no_trace | missing |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AUSTIN | 504 | 504 | 504 | 504 | 0 | 0 | 0 | 0 |
| CORPUS_CHRISTI | 504 | 504 | 504 | 504 | 0 | 0 | 0 | 0 |
| MIDLAND | 504 | 504 | 504 | 504 | 0 | 0 | 0 | 0 |
| EL_PASO | 504 | 504 | 504 | 504 | 0 | 0 | 0 | 0 |

Console summary of the full run (`..._console.txt`): fallback runs AUSTIN 353, CORPUS_CHRISTI 98, MIDLAND 79,
EL_PASO 3; gates that fired (point-level counts) G4 422 and G6 111; sources for air temperature TCEQ 1512, ASOS
384, Synoptic 120; wind TCEQ 2016; solar Open-Meteo 2016; provider issue: NSRDB returned HTTP 400 for year 2026
three times and was then skipped for the remaining 2013 requests.

**For other phases.**

- Phase 4 (DB-03) loads this archive and must match its sha256 above and the 504-rows-per-city counts.
- Backfill steps are hour-aligned run slots, which map to `valid_time` under OD-7. The trace's `observation_hour`
  is the aligned weather hour, which is OD-7's `observation_time`; the two differ for CORPUS_CHRISTI at every
  step (see Finding 5).
- Phase 5 (OD-10, models committed to git) can check that the committed model files match the model sha256
  values listed above. If the models are refit before Phase 5, these results no longer describe the shipped
  models.

## Method

- **Computed versus reported.** The *computed* rating is the IEEE 738 ampacity of the rated observation with the
  city's conductor and line bearing; it is what the plausibility gate G4 judges. The *reported* rating is what
  the pipeline publishes after G1-G6: the computed rating when every gate passes, otherwise the city's static
  rating (a fallback). Both appear in every table; the analysis recomputes the ampacity from the traced
  observation and compares it with the archive (see self-checks).
- **Twelve outcomes, every step counted once.** `ok`, `G1`, `G2`, `G3`, `G4_low` (computed below the city's
  lower bound), `G4_high` (above the upper bound), `G5`, `G6` (the learned detector gate), `EXHAUSTED`, `ERROR`,
  `NO_TRACE` (archive row without a trace record) and `MISSING` (no record at all). Rate denominators are the
  expected steps of the period, so exhausted, errored, untraced and missing steps stay in every rate.
- **Upward and downward fallback.** A fallback is *upward* when the static rating it publishes is higher than the
  computed rating, *downward* when lower. `overstatement` columns are reported minus computed, in A, over the
  upward steps only.
- **Warm-up versus scored.** The first 168 steps per city are warm-up; the headline numbers cover the 336 scored
  steps per city. Warm-up outcomes are listed for completeness.
- **Forecast-band coverage.** `coverage_nominal` is the share of computed ratings inside the forecast's own 5-95%
  band (nominal target 0.90) over scored steps that reached G6 with a positive-width band and a computed rating,
  whether or not G6 used that forecast (`n_band`). The interval is a seeded day-block bootstrap (whole UTC days,
  2000 resamples, seed 20261019, 95%). `coverage_widened` is inside the detector's widened band (k = 4,
  `config.ANOMALY_CONTROL_LIMIT_K_BY_LOCATION`) on the steps whose forecast G6 used. Every exclusion has its own
  count column.
- **Naive replay.** The `replay` subcommand re-runs the real per-city pipeline offline on exactly the traced
  observations with the naive forecast method. It is a same-observation counterfactual used as a reference, never
  a record of live behaviour; its rows carry the label `naive_replay`. It starts from an empty archive, like the
  original run, so early-step histories are like-for-like. Fidelity check: 2016 steps compared, 0 excluded, 0
  mismatches in G1-G5/EXHAUSTED outcome, computed rating (tolerance 1e-9 A) or G6 reach (`replay_fidelity.json`).
  The naive reference therefore differs from the live run only by forecast method.
- **Self-checks** (`report_meta.json`), all zero: computed-versus-reported mismatches 0, archive-versus-trace
  mismatches 0, archive duplicate-slot mismatches 0, archive rows dropped by validation 0, archive rows outside
  the window 0, trace duplicates 0, trace records out of window 0, replay fidelity mismatches 0. Trace records:
  2016. VAL-01 and the live VAL-02 rows describe the original `ml` run; only the `naive_replay` rows come from the
  replay.
- **Models.** The per-city forecast and anomaly models were trained on 2023-2025 Open-Meteo history
  (`config.FORECAST_ML_TRAINING_YEARS` and `config.ANOMALY_ML_TRAINING_YEARS` are 3; the files in `data/models/`
  are dated 2026-10-13), so the window is out of sample. `docs/data-science/PROJECT-STATUS.md` records the
  per-city forecast models as NOT MET against naive on held-out MAE and the anomaly models as MET.

## VAL-01: ratings against static ratings and bounds

### Rating distribution (scored window, 336 steps per city)

| city | expected_steps | static_a | lower_a | upper_a | reported_n | reported_min | reported_p05 | reported_p25 | reported_p50 | reported_p75 | reported_p95 | reported_max | reported_mean | frac_reported_above_static | frac_reported_equal_static | frac_reported_below_static | computed_n | computed_min | computed_p05 | computed_p25 | computed_p50 | computed_p75 | computed_p95 | computed_max | computed_mean | frac_computed_below_lower | frac_computed_within | frac_computed_above_upper | frac_computed_below_static |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AUSTIN | 336 | 1825.0 | 1150.0 | 2500.0 | 336 | 1150.5 | 1175.7 | 1296.3 | 1825.0 | 1825.0 | 1825.0 | 1825.0 | 1638.5 | 0.0 | 0.6815 | 0.3185 | 336 | 832.3 | 923.4 | 1015.0 | 1105.0 | 1186.5 | 1316.3 | 1569.5 | 1106.9 | 0.6696 | 0.3304 | 0.0 | 1.0 |
| CORPUS_CHRISTI | 336 | 1500.0 | 800.0 | 2200.0 | 336 | 902.7 | 998.9 | 1190.6 | 1406.0 | 1500.0 | 1551.5 | 1665.6 | 1339.7 | 0.1488 | 0.1101 | 0.7411 | 336 | 902.7 | 998.9 | 1177.7 | 1380.4 | 1459.3 | 1559.3 | 1682.5 | 1325.7 | 0.0 | 1.0 | 0.0 | 0.8363 |
| MIDLAND | 336 | 1875.0 | 1250.0 | 2500.0 | 336 | 1257.4 | 1316.6 | 1471.8 | 1603.2 | 1767.6 | 1875.0 | 1875.0 | 1610.9 | 0.0 | 0.2083 | 0.7917 | 336 | 917.0 | 1070.5 | 1314.4 | 1494.4 | 1620.8 | 1757.4 | 1858.0 | 1458.0 | 0.2024 | 0.7976 | 0.0 | 1.0 |
| EL_PASO | 336 | 1320.0 | 640.0 | 2000.0 | 336 | 856.3 | 938.6 | 1034.1 | 1132.7 | 1270.5 | 1603.4 | 1787.7 | 1179.0 | 0.1935 | 0.003 | 0.8036 | 336 | 856.3 | 938.6 | 1034.1 | 1132.7 | 1270.5 | 1616.3 | 1787.7 | 1180.3 | 0.0 | 1.0 | 0.0 | 0.8036 |

Reading, per city:

- **AUSTIN.** Physics gives a median of 1105.0 A (p05 923.4, p95 1316.3) against a 1150 A lower bound and a 1825 A
  static rating: computed is below the lower bound in 66.96% of steps and below the static rating in every step.
  The published median is 1825.0 A, the static rating itself, which is also the published value at 68.15% of
  steps; none is above static. Mean published 1638.5 A against mean computed 1106.9 A, a difference of 531.6 A.
- **CORPUS_CHRISTI.** Computed ratings span 902.7 to 1682.5 A (median 1380.4 A) and sit inside the 800-2200 A
  bounds at every step; they are below the 1500 A static rating in 83.63% of steps. Published values are above
  static in 14.88% of steps (maximum 1665.6 A), equal to static in 11.01% (the 37 G6 fallbacks) and below static
  in 74.11%. Mean published 1339.7 A against mean computed 1325.7 A.
- **MIDLAND.** Median computed 1494.4 A (p05 1070.5), below the 1250 A lower bound in 20.24% of steps; computed
  never reaches the 1875 A static rating (maximum 1858.0 A). The published value equals static at 20.83% of steps
  (68 G4 plus 2 G6 fallbacks) and the lowest published value is 1257.4 A, just above the bound. Mean published
  1610.9 A against mean computed 1458.0 A, 152.9 A more.
- **EL_PASO.** Median computed 1132.7 A (p05 938.6, p95 1616.3), inside the 640-2000 A bounds at every step and
  below the 1320 A static rating in 80.36% of steps. Published values are above static in 19.35% of steps
  (maximum 1787.7 A) and equal to static at one step (0.30%, a G6 fallback). Mean published 1179.0 A against mean
  computed 1180.3 A: for practical purposes the pipeline published what physics computed.

### Outcomes by gate (all twelve outcomes, warm-up and scored)

| city | period | outcome | count | rate |
| --- | --- | --- | --- | --- |
| AUSTIN | warmup | ok | 44 | 0.2619 |
| AUSTIN | warmup | G1 | 0 | 0.0 |
| AUSTIN | warmup | G2 | 0 | 0.0 |
| AUSTIN | warmup | G3 | 0 | 0.0 |
| AUSTIN | warmup | G4_low | 123 | 0.7321 |
| AUSTIN | warmup | G4_high | 0 | 0.0 |
| AUSTIN | warmup | G5 | 0 | 0.0 |
| AUSTIN | warmup | G6 | 1 | 0.006 |
| AUSTIN | warmup | EXHAUSTED | 0 | 0.0 |
| AUSTIN | warmup | ERROR | 0 | 0.0 |
| AUSTIN | warmup | NO_TRACE | 0 | 0.0 |
| AUSTIN | warmup | MISSING | 0 | 0.0 |
| AUSTIN | scored | ok | 107 | 0.3185 |
| AUSTIN | scored | G1 | 0 | 0.0 |
| AUSTIN | scored | G2 | 0 | 0.0 |
| AUSTIN | scored | G3 | 0 | 0.0 |
| AUSTIN | scored | G4_low | 225 | 0.6696 |
| AUSTIN | scored | G4_high | 0 | 0.0 |
| AUSTIN | scored | G5 | 0 | 0.0 |
| AUSTIN | scored | G6 | 4 | 0.0119 |
| AUSTIN | scored | EXHAUSTED | 0 | 0.0 |
| AUSTIN | scored | ERROR | 0 | 0.0 |
| AUSTIN | scored | NO_TRACE | 0 | 0.0 |
| AUSTIN | scored | MISSING | 0 | 0.0 |
| CORPUS_CHRISTI | warmup | ok | 107 | 0.6369 |
| CORPUS_CHRISTI | warmup | G1 | 0 | 0.0 |
| CORPUS_CHRISTI | warmup | G2 | 0 | 0.0 |
| CORPUS_CHRISTI | warmup | G3 | 0 | 0.0 |
| CORPUS_CHRISTI | warmup | G4_low | 0 | 0.0 |
| CORPUS_CHRISTI | warmup | G4_high | 0 | 0.0 |
| CORPUS_CHRISTI | warmup | G5 | 0 | 0.0 |
| CORPUS_CHRISTI | warmup | G6 | 61 | 0.3631 |
| CORPUS_CHRISTI | warmup | EXHAUSTED | 0 | 0.0 |
| CORPUS_CHRISTI | warmup | ERROR | 0 | 0.0 |
| CORPUS_CHRISTI | warmup | NO_TRACE | 0 | 0.0 |
| CORPUS_CHRISTI | warmup | MISSING | 0 | 0.0 |
| CORPUS_CHRISTI | scored | ok | 299 | 0.8899 |
| CORPUS_CHRISTI | scored | G1 | 0 | 0.0 |
| CORPUS_CHRISTI | scored | G2 | 0 | 0.0 |
| CORPUS_CHRISTI | scored | G3 | 0 | 0.0 |
| CORPUS_CHRISTI | scored | G4_low | 0 | 0.0 |
| CORPUS_CHRISTI | scored | G4_high | 0 | 0.0 |
| CORPUS_CHRISTI | scored | G5 | 0 | 0.0 |
| CORPUS_CHRISTI | scored | G6 | 37 | 0.1101 |
| CORPUS_CHRISTI | scored | EXHAUSTED | 0 | 0.0 |
| CORPUS_CHRISTI | scored | ERROR | 0 | 0.0 |
| CORPUS_CHRISTI | scored | NO_TRACE | 0 | 0.0 |
| CORPUS_CHRISTI | scored | MISSING | 0 | 0.0 |
| MIDLAND | warmup | ok | 159 | 0.9464 |
| MIDLAND | warmup | G1 | 0 | 0.0 |
| MIDLAND | warmup | G2 | 0 | 0.0 |
| MIDLAND | warmup | G3 | 0 | 0.0 |
| MIDLAND | warmup | G4_low | 6 | 0.0357 |
| MIDLAND | warmup | G4_high | 0 | 0.0 |
| MIDLAND | warmup | G5 | 0 | 0.0 |
| MIDLAND | warmup | G6 | 3 | 0.0179 |
| MIDLAND | warmup | EXHAUSTED | 0 | 0.0 |
| MIDLAND | warmup | ERROR | 0 | 0.0 |
| MIDLAND | warmup | NO_TRACE | 0 | 0.0 |
| MIDLAND | warmup | MISSING | 0 | 0.0 |
| MIDLAND | scored | ok | 266 | 0.7917 |
| MIDLAND | scored | G1 | 0 | 0.0 |
| MIDLAND | scored | G2 | 0 | 0.0 |
| MIDLAND | scored | G3 | 0 | 0.0 |
| MIDLAND | scored | G4_low | 68 | 0.2024 |
| MIDLAND | scored | G4_high | 0 | 0.0 |
| MIDLAND | scored | G5 | 0 | 0.0 |
| MIDLAND | scored | G6 | 2 | 0.006 |
| MIDLAND | scored | EXHAUSTED | 0 | 0.0 |
| MIDLAND | scored | ERROR | 0 | 0.0 |
| MIDLAND | scored | NO_TRACE | 0 | 0.0 |
| MIDLAND | scored | MISSING | 0 | 0.0 |
| EL_PASO | warmup | ok | 166 | 0.9881 |
| EL_PASO | warmup | G1 | 0 | 0.0 |
| EL_PASO | warmup | G2 | 0 | 0.0 |
| EL_PASO | warmup | G3 | 0 | 0.0 |
| EL_PASO | warmup | G4_low | 0 | 0.0 |
| EL_PASO | warmup | G4_high | 0 | 0.0 |
| EL_PASO | warmup | G5 | 0 | 0.0 |
| EL_PASO | warmup | G6 | 2 | 0.0119 |
| EL_PASO | warmup | EXHAUSTED | 0 | 0.0 |
| EL_PASO | warmup | ERROR | 0 | 0.0 |
| EL_PASO | warmup | NO_TRACE | 0 | 0.0 |
| EL_PASO | warmup | MISSING | 0 | 0.0 |
| EL_PASO | scored | ok | 335 | 0.997 |
| EL_PASO | scored | G1 | 0 | 0.0 |
| EL_PASO | scored | G2 | 0 | 0.0 |
| EL_PASO | scored | G3 | 0 | 0.0 |
| EL_PASO | scored | G4_low | 0 | 0.0 |
| EL_PASO | scored | G4_high | 0 | 0.0 |
| EL_PASO | scored | G5 | 0 | 0.0 |
| EL_PASO | scored | G6 | 1 | 0.003 |
| EL_PASO | scored | EXHAUSTED | 0 | 0.0 |
| EL_PASO | scored | ERROR | 0 | 0.0 |
| EL_PASO | scored | NO_TRACE | 0 | 0.0 |
| EL_PASO | scored | MISSING | 0 | 0.0 |

Reading, per city (G1, G2, G3, G4_high, G5, EXHAUSTED, ERROR, NO_TRACE and MISSING are 0 in every city and both
periods):

- **AUSTIN.** Scored: 107 ok (31.85%), 225 G4_low (66.96%), 4 G6 (1.19%). Warm-up: 44 ok, 123 G4_low (73.21%), 1
  G6. G4 on the low side is the dominant outcome in both periods.
- **CORPUS_CHRISTI.** Scored: 299 ok (88.99%), 37 G6 (11.01%), no G4. Warm-up: 107 ok, 61 G6 (36.31%). All
  fallbacks come from the detector gate.
- **MIDLAND.** Scored: 266 ok (79.17%), 68 G4_low (20.24%), 2 G6 (0.60%). Warm-up: 159 ok, 6 G4_low, 3 G6. The
  low-side G4 rate is concentrated in the scored window.
- **EL_PASO.** Scored: 335 ok (99.70%), 1 G6 (0.30%). Warm-up: 166 ok, 2 G6. Effectively no fallbacks.

### Fallback direction and overstatement

| city | gate | fallback_steps | upward | downward | none | unknown | upward_rate | overstatement_median | overstatement_p95 | overstatement_max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AUSTIN | G4_low | 225 | 225 | 0 | 0 | 0 | 0.6696 | 782.6 | 919.2 | 992.7 |
| AUSTIN | G4_high | 0 | 0 | 0 | 0 | 0 | 0.0 |  |  |  |
| AUSTIN | G6 | 4 | 4 | 0 | 0 | 0 | 0.0119 | 315.0 | 342.2 | 346.7 |
| AUSTIN | all | 229 | 229 | 0 | 0 | 0 | 0.6815 | 780.1 | 919.1 | 992.7 |
| CORPUS_CHRISTI | G4_low | 0 | 0 | 0 | 0 | 0 | 0.0 |  |  |  |
| CORPUS_CHRISTI | G4_high | 0 | 0 | 0 | 0 | 0 | 0.0 |  |  |  |
| CORPUS_CHRISTI | G6 | 37 | 32 | 5 | 0 | 0 | 0.0952 | 113.9 | 379.3 | 410.7 |
| CORPUS_CHRISTI | all | 37 | 32 | 5 | 0 | 0 | 0.0952 | 113.9 | 379.3 | 410.7 |
| MIDLAND | G4_low | 68 | 68 | 0 | 0 | 0 | 0.2024 | 717.2 | 904.4 | 958.0 |
| MIDLAND | G4_high | 0 | 0 | 0 | 0 | 0 | 0.0 |  |  |  |
| MIDLAND | G6 | 2 | 2 | 0 | 0 | 0 | 0.006 | 497.1 | 528.2 | 531.6 |
| MIDLAND | all | 70 | 70 | 0 | 0 | 0 | 0.2083 | 712.3 | 903.6 | 958.0 |
| EL_PASO | G4_low | 0 | 0 | 0 | 0 | 0 | 0.0 |  |  |  |
| EL_PASO | G4_high | 0 | 0 | 0 | 0 | 0 | 0.0 |  |  |  |
| EL_PASO | G6 | 1 | 0 | 1 | 0 | 0 | 0.0 |  |  |  |
| EL_PASO | all | 1 | 0 | 1 | 0 | 0 | 0.0 |  |  |  |

Reading, per city (overstatement is reported minus computed over the upward steps):

- **AUSTIN.** 229 of 336 scored steps (68.15%) published more than computed: 225 from the G4 low bound (median
  +782.6 A, p95 +919.2, maximum +992.7) and 4 from G6 (median +315.0, maximum +346.7). No downward fallback.
- **CORPUS_CHRISTI.** 37 G6 fallbacks: 32 upward (9.52% of scored steps; median +113.9 A, p95 +379.3, maximum
  +410.7) and 5 downward, where the 1500 A static rating is below the computed value.
- **MIDLAND.** 70 fallbacks, all upward (20.83%): 68 from G4 (median +717.2 A, maximum +958.0) and 2 from G6
  (median +497.1, maximum +531.6).
- **EL_PASO.** One fallback, downward: the static 1320 A replaced a computed 1747.0 A (427.0 A lower).

### Outliers (five lowest and five highest computed ratings per city)

| city | rank_kind | rank | run_end_utc | outcome | reported_a | computed_a | obs_temp | obs_wind | obs_wind_raw | obs_wind_direction | obs_solar | temp_source | wind_source | solar_source | observation_hour |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AUSTIN | lowest | 1 | 2026-09-22T13:00:00Z | G4_low | 1825.0 | 832.3 | 26.778 | 0.168 | 0.492 | 188.0 | 23.0 | tceq | tceq | open_meteo | 2026-09-22T13:00:00Z |
| AUSTIN | lowest | 2 | 2026-09-21T00:00:00Z | G4_low | 1825.0 | 853.2 | 32.056 | 0.302 | 0.849 | 194.0 | 115.0 | tceq | tceq | open_meteo | 2026-09-21T00:00:00Z |
| AUSTIN | lowest | 3 | 2026-09-18T09:00:00Z | G4_low | 1825.0 | 853.7 | 24.278 | 0.168 | 0.492 | 159.0 | 0.0 | tceq | tceq | open_meteo | 2026-09-18T09:00:00Z |
| AUSTIN | lowest | 4 | 2026-09-21T19:00:00Z | G4_low | 1825.0 | 865.1 | 34.333 | 0.581 | 1.699 | 154.0 | 768.0 | tceq | tceq | open_meteo | 2026-09-21T19:00:00Z |
| AUSTIN | lowest | 5 | 2026-09-20T00:00:00Z | G4_low | 1825.0 | 865.4 | 31.556 | 0.321 | 0.939 | 167.0 | 124.0 | tceq | tceq | open_meteo | 2026-09-20T00:00:00Z |
| AUSTIN | highest | 1 | 2026-09-21T02:00:00Z | G6 | 1825.0 | 1569.5 | 26.611 | 3.808 | 3.979 | 280.0 | 0.0 | tceq | tceq | open_meteo | 2026-09-21T02:00:00Z |
| AUSTIN | highest | 2 | 2026-09-21T23:00:00Z | G6 | 1825.0 | 1511.6 | 32.5 | 4.369 | 4.426 | 74.0 | 306.0 | tceq | tceq | open_meteo | 2026-09-21T23:00:00Z |
| AUSTIN | highest | 3 | 2026-09-21T03:00:00Z | G6 | 1825.0 | 1508.4 | 25.0 | 3.082 | 3.085 | 261.0 | 0.0 | tceq | tceq | open_meteo | 2026-09-21T03:00:00Z |
| AUSTIN | highest | 4 | 2026-09-20T14:00:00Z | G6 | 1825.0 | 1478.3 | 26.611 | 3.118 | 3.129 | 268.0 | 186.0 | tceq | tceq | open_meteo | 2026-09-20T14:00:00Z |
| AUSTIN | highest | 5 | 2026-09-22T00:00:00Z | ok | 1429.5 | 1429.5 | 30.667 | 3.186 | 3.219 | 75.0 | 120.0 | tceq | tceq | open_meteo | 2026-09-22T00:00:00Z |
| CORPUS_CHRISTI | lowest | 1 | 2026-09-27T08:00:00Z | ok | 902.7 | 902.7 | 27.2 | 0.291 | 0.849 | 192.0 | 0.0 | synoptic | tceq | open_meteo | 2026-09-27T07:00:00Z |
| CORPUS_CHRISTI | lowest | 2 | 2026-09-18T14:00:00Z | ok | 915.3 | 915.3 | 29.444 | 0.367 | 1.073 | 164.0 | 21.0 | asos | tceq | open_meteo | 2026-09-18T13:00:00Z |
| CORPUS_CHRISTI | lowest | 3 | 2026-09-20T12:00:00Z | ok | 927.8 | 927.8 | 23.333 | 0.277 | 0.805 | 153.0 | 0.0 | asos | tceq | open_meteo | 2026-09-20T11:00:00Z |
| CORPUS_CHRISTI | lowest | 4 | 2026-09-16T13:00:00Z | ok | 931.4 | 931.4 | 25.556 | 0.321 | 0.939 | 170.0 | 0.0 | asos | tceq | open_meteo | 2026-09-16T12:00:00Z |
| CORPUS_CHRISTI | lowest | 5 | 2026-09-22T12:00:00Z | ok | 932.2 | 932.2 | 24.444 | 0.303 | 0.805 | 151.0 | 0.0 | asos | tceq | open_meteo | 2026-09-22T11:00:00Z |
| CORPUS_CHRISTI | highest | 1 | 2026-09-18T06:00:00Z | G6 | 1500.0 | 1682.5 | 30.0 | 5.629 | 5.633 | 81.0 | 0.0 | asos | tceq | open_meteo | 2026-09-18T05:00:00Z |
| CORPUS_CHRISTI | highest | 2 | 2026-09-24T19:00:00Z | ok | 1665.6 | 1665.6 | 31.8 | 6.414 | 6.437 | 88.0 | 808.0 | synoptic | tceq | open_meteo | 2026-09-24T18:00:00Z |
| CORPUS_CHRISTI | highest | 3 | 2026-09-18T03:00:00Z | G6 | 1500.0 | 1652.6 | 30.0 | 5.266 | 5.32 | 75.0 | 0.0 | asos | tceq | open_meteo | 2026-09-18T02:00:00Z |
| CORPUS_CHRISTI | highest | 4 | 2026-09-24T20:00:00Z | ok | 1643.0 | 1643.0 | 31.9 | 6.111 | 6.169 | 91.0 | 768.0 | synoptic | tceq | open_meteo | 2026-09-24T19:00:00Z |
| CORPUS_CHRISTI | highest | 5 | 2026-09-24T21:00:00Z | ok | 1634.9 | 1634.9 | 31.7 | 5.978 | 6.035 | 91.0 | 798.0 | synoptic | tceq | open_meteo | 2026-09-24T20:00:00Z |
| MIDLAND | lowest | 1 | 2026-09-20T20:00:00Z | G4_low | 1875.0 | 917.0 | 33.5 | 0.78 | 2.28 | 102.0 | 799.0 | tceq | tceq | open_meteo | 2026-09-20T20:00:00Z |
| MIDLAND | lowest | 2 | 2026-09-20T21:00:00Z | G4_low | 1875.0 | 934.4 | 34.056 | 0.841 | 2.459 | 97.0 | 735.0 | tceq | tceq | open_meteo | 2026-09-20T21:00:00Z |
| MIDLAND | lowest | 3 | 2026-09-27T02:00:00Z | G4_low | 1875.0 | 960.3 | 29.778 | 0.489 | 1.431 | 101.0 | 0.0 | tceq | tceq | open_meteo | 2026-09-27T02:00:00Z |
| MIDLAND | lowest | 4 | 2026-09-27T17:00:00Z | G4_low | 1875.0 | 968.1 | 31.278 | 0.813 | 1.475 | 301.0 | 646.0 | tceq | tceq | open_meteo | 2026-09-27T17:00:00Z |
| MIDLAND | lowest | 5 | 2026-09-27T20:00:00Z | G4_low | 1875.0 | 975.3 | 33.722 | 0.961 | 2.012 | 239.0 | 691.0 | tceq | tceq | open_meteo | 2026-09-27T20:00:00Z |
| MIDLAND | highest | 1 | 2026-09-15T14:00:00Z | ok | 1858.0 | 1858.0 | 26.333 | 7.146 | 7.153 | 175.0 | 115.0 | tceq | tceq | open_meteo | 2026-09-15T14:00:00Z |
| MIDLAND | highest | 2 | 2026-09-15T13:00:00Z | ok | 1835.9 | 1835.9 | 25.444 | 6.559 | 6.571 | 174.0 | 8.0 | tceq | tceq | open_meteo | 2026-09-15T13:00:00Z |
| MIDLAND | highest | 3 | 2026-09-15T15:00:00Z | ok | 1830.5 | 1830.5 | 27.889 | 7.325 | 7.331 | 180.0 | 340.0 | tceq | tceq | open_meteo | 2026-09-15T15:00:00Z |
| MIDLAND | highest | 4 | 2026-09-17T14:00:00Z | ok | 1823.4 | 1823.4 | 25.611 | 6.516 | 7.108 | 154.0 | 134.0 | tceq | tceq | open_meteo | 2026-09-17T14:00:00Z |
| MIDLAND | highest | 5 | 2026-09-17T15:00:00Z | ok | 1816.7 | 1816.7 | 27.0 | 6.905 | 7.242 | 160.0 | 349.0 | tceq | tceq | open_meteo | 2026-09-17T15:00:00Z |
| EL_PASO | lowest | 1 | 2026-09-21T17:00:00Z | ok | 856.3 | 856.3 | 29.722 | 0.398 | 1.162 | 102.0 | 693.0 | tceq | tceq | open_meteo | 2026-09-21T17:00:00Z |
| EL_PASO | lowest | 2 | 2026-09-18T23:00:00Z | ok | 874.4 | 874.4 | 32.556 | 0.443 | 1.296 | 96.0 | 418.0 | tceq | tceq | open_meteo | 2026-09-18T23:00:00Z |
| EL_PASO | lowest | 3 | 2026-09-19T17:00:00Z | ok | 883.3 | 883.3 | 29.0 | 0.427 | 1.073 | 111.0 | 622.0 | tceq | tceq | open_meteo | 2026-09-19T17:00:00Z |
| EL_PASO | lowest | 4 | 2026-09-27T17:00:00Z | ok | 886.8 | 886.8 | 28.833 | 0.443 | 1.296 | 76.0 | 668.0 | tceq | tceq | open_meteo | 2026-09-27T17:00:00Z |
| EL_PASO | lowest | 5 | 2026-09-18T22:00:00Z | ok | 900.5 | 900.5 | 33.111 | 0.657 | 1.922 | 254.0 | 624.0 | tceq | tceq | open_meteo | 2026-09-18T22:00:00Z |
| EL_PASO | highest | 1 | 2026-09-16T08:00:00Z | ok | 1787.7 | 1787.7 | 20.278 | 4.991 | 5.007 | 173.0 | 0.0 | tceq | tceq | open_meteo | 2026-09-16T08:00:00Z |
| EL_PASO | highest | 2 | 2026-09-17T13:00:00Z | ok | 1772.3 | 1772.3 | 21.611 | 5.048 | 5.856 | 28.0 | 0.0 | tceq | tceq | open_meteo | 2026-09-17T13:00:00Z |
| EL_PASO | highest | 3 | 2026-09-18T09:00:00Z | ok | 1761.6 | 1761.6 | 21.778 | 4.962 | 5.409 | 21.0 | 0.0 | tceq | tceq | open_meteo | 2026-09-18T09:00:00Z |
| EL_PASO | highest | 4 | 2026-09-18T11:00:00Z | ok | 1761.4 | 1761.4 | 21.556 | 4.924 | 5.409 | 22.0 | 0.0 | tceq | tceq | open_meteo | 2026-09-18T11:00:00Z |
| EL_PASO | highest | 5 | 2026-09-23T02:00:00Z | ok | 1749.4 | 1749.4 | 19.444 | 4.482 | 5.007 | 24.0 | 0.0 | tceq | tceq | open_meteo | 2026-09-23T02:00:00Z |

Reading, per city (explanations are under Explanations):

- **AUSTIN.** The five lowest are all G4_low fallbacks (832.3 to 865.4 A) published as 1825.0 A; four of the five
  highest are G6 fallbacks, also published as 1825.0 A.
- **CORPUS_CHRISTI.** The five lowest (902.7 to 932.2 A) are accepted as computed; of the five highest, two are G6
  fallbacks published as 1500.0 A, below their computed 1682.5 and 1652.6 A.
- **MIDLAND.** The five lowest (917.0 to 975.3 A) are G4_low fallbacks published as 1875.0 A; the five highest
  (1816.7 to 1858.0 A) are accepted as computed.
- **EL_PASO.** All ten extremes are accepted as computed (lowest 856.3 A, highest 1787.7 A).

### Drivers by group (below lower bound, within, above upper bound)

| city | group | n | temp_median | solar_median | wind_raw_median | wind_proj_median | perp_fraction_median | wind_open_meteo_share | solar_open_meteo_share | lag_over_1h_share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AUSTIN | below_lower | 225 | 26.778 | 0.0 | 1.699 | 0.78 | 0.3559 | 0.0 | 1.0 | 0.0 |
| AUSTIN | within | 111 | 30.889 | 304.0 | 2.414 | 2.034 | 0.9345 | 0.0 | 1.0 | 0.0 |
| AUSTIN | above_upper | 0 |  |  |  |  |  |  |  |  |
| CORPUS_CHRISTI | below_lower | 0 |  |  |  |  |  |  |  |  |
| CORPUS_CHRISTI | within | 336 | 29.444 | 21.0 | 3.398 | 2.678 | 0.8585 | 0.0 | 1.0 | 0.0357 |
| CORPUS_CHRISTI | above_upper | 0 |  |  |  |  |  |  |  |  |
| MIDLAND | below_lower | 68 | 28.111 | 19.0 | 2.727 | 1.17 | 0.342 | 0.0 | 1.0 | 0.0 |
| MIDLAND | within | 268 | 26.667 | 7.0 | 4.605 | 3.85 | 0.8946 | 0.0 | 1.0 | 0.0 |
| MIDLAND | above_upper | 0 |  |  |  |  |  |  |  |  |
| EL_PASO | below_lower | 0 |  |  |  |  |  |  |  |  |
| EL_PASO | within | 336 | 25.028 | 3.5 | 2.012 | 1.083 | 0.5801 | 0.0 | 1.0 | 0.0 |
| EL_PASO | above_upper | 0 |  |  |  |  |  |  |  |  |

Reading, per city:

- **AUSTIN.** Below-bound steps have a much smaller line-perpendicular share of the wind (median perp_fraction
  0.3559 against 0.9345) and lighter projected wind (0.78 against 2.034 m/s) than accepted steps, and lower solar
  (median 0.0 against 304.0 W/m2). Wind and solar come from TCEQ and Open-Meteo respectively in every step.
- **CORPUS_CHRISTI.** All 336 steps are in the within group (median wind projected 2.678 m/s, perp_fraction
  0.8585); 3.57% of steps have an observation lag above one hour.
- **MIDLAND.** The 68 below-bound steps have median projected wind 1.17 m/s (perp_fraction 0.342) against 3.85 m/s
  (0.8946) for accepted steps; temperature is 1.4 C warmer and solar 19.0 against 7.0 W/m2.
- **EL_PASO.** All 336 steps are within bounds (median projected wind 1.083 m/s, perp_fraction 0.5801).

## VAL-02: forecast band and anomaly detector

Rows labelled `ml` are the live system (the forecast method the pipeline used in the real run). Rows labelled
`naive_replay` are the reference: the same observations with the naive forecast, not what the system did.

### Forecast band: coverage, width and error

| city | method | n_warmup | n_scored | n_not_g6 | n_g6_evaluated | n_with_forecast | n_cold_start | n_silent_forecast_failure | n_cleaning_failure_suspect | n_degenerate_band | n_no_computed | n_band | n_withheld_gap | n_used_by_g6 | coverage_nominal | nominal_target | coverage_ci_lo | coverage_ci_hi | coverage_widened | width_mean_a | width_median_a | mae_a | bias_a | n_all_computed | coverage_all_computed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AUSTIN | ml | 168 | 336 | 225 | 111 | 111 | 0 | 0 | 0 | 0 | 0 | 111 | 96 | 15 | 0.8108 | 0.9 | 0.7327 | 0.88 | 1.0 | 257.6 | 262.5 | 104.1 | 87.6 | 336 | 0.4851 |
| AUSTIN | naive_replay | 168 | 336 | 225 | 111 | 111 | 0 | 0 | 0 | 0 | 0 | 111 | 28 | 83 | 0.8649 | 0.9 | 0.7475 | 0.9549 | 1.0 | 225.6 | 228.6 | 62.3 | 0.4 | 336 | 0.503 |
| CORPUS_CHRISTI | ml | 168 | 336 | 0 | 336 | 336 | 0 | 0 | 0 | 0 | 0 | 336 | 103 | 233 | 0.8958 | 0.9 | 0.8452 | 0.9435 | 1.0 | 343.8 | 335.3 | 86.4 | 41.9 | 336 | 0.8958 |
| CORPUS_CHRISTI | naive_replay | 168 | 336 | 0 | 336 | 336 | 0 | 0 | 0 | 0 | 0 | 336 | 20 | 316 | 0.9018 | 0.9 | 0.8661 | 0.9345 | 1.0 | 324.8 | 319.9 | 62.9 | 2.5 | 336 | 0.9018 |
| MIDLAND | ml | 168 | 336 | 68 | 268 | 268 | 0 | 0 | 0 | 0 | 0 | 268 | 99 | 169 | 0.8134 | 0.9 | 0.7719 | 0.8567 | 0.9882 | 268.6 | 261.4 | 94.2 | 49.8 | 336 | 0.6994 |
| MIDLAND | naive_replay | 168 | 336 | 68 | 268 | 268 | 0 | 0 | 0 | 0 | 0 | 268 | 16 | 252 | 0.8097 | 0.9 | 0.7553 | 0.8605 | 1.0 | 273.9 | 263.3 | 80.3 | -0.5 | 336 | 0.6935 |
| EL_PASO | ml | 168 | 336 | 0 | 336 | 336 | 0 | 0 | 0 | 0 | 0 | 336 | 6 | 330 | 0.8839 | 0.9 | 0.8363 | 0.9256 | 1.0 | 444.2 | 454.3 | 126.7 | 77.6 | 336 | 0.8839 |
| EL_PASO | naive_replay | 168 | 336 | 0 | 336 | 336 | 0 | 0 | 0 | 0 | 0 | 336 | 0 | 336 | 0.881 | 0.9 | 0.8274 | 0.9316 | 1.0 | 507.2 | 517.0 | 117.3 | 0.0 | 336 | 0.881 |

Empirical coverage of the ml band against the nominal 90%, with the day-block bootstrap 95% interval and n
(`n_band`, scored steps that reached G6 with a computed rating):

- **AUSTIN:** 0.8108 (interval 0.7327 to 0.8800, n = 111). The interval excludes 0.90. Naive reference 0.8649
  (0.7475 to 0.9549, n = 111).
- **CORPUS_CHRISTI:** 0.8958 (0.8452 to 0.9435, n = 336). The interval contains 0.90. Naive 0.9018 (0.8661 to
  0.9345).
- **MIDLAND:** 0.8134 (0.7719 to 0.8567, n = 268). The interval excludes 0.90. Naive 0.8097 (0.7553 to 0.8605).
- **EL_PASO:** 0.8839 (0.8363 to 0.9256, n = 336). The interval contains 0.90. Naive 0.8810 (0.8274 to 0.9316).

Other columns, ml against naive_replay: mean band width 257.6 / 343.8 / 268.6 / 444.2 A against 225.6 / 324.8 /
273.9 / 507.2 A (AUSTIN / CORPUS_CHRISTI / MIDLAND / EL_PASO); MAE 104.1 / 86.4 / 94.2 / 126.7 A against 62.3 /
62.9 / 80.3 / 117.3 A; bias (computed minus forecast centre) +87.6 / +41.9 / +49.8 / +77.6 A against +0.4 / +2.5 /
-0.5 / 0.0 A. Coverage inside the detector's widened band is 1.0 for ml in three cities and 0.9882 in MIDLAND (the
2 forecast-branch trips). Coverage over every scored step with a computed rating (`coverage_all_computed`, G4
fallbacks included) is 0.4851 for AUSTIN, 0.8958 for CORPUS_CHRISTI, 0.6994 for MIDLAND and 0.8839 for EL_PASO.

Exclusions, ml: cold start 0, silent forecast failure 0, suspected cleaning failure 0, degenerate (zero-width) band
0, no computed rating 0 in every city. Forecasts computed but withheld from G6 across a history gap
(`n_withheld_gap`): AUSTIN 96, CORPUS_CHRISTI 103, MIDLAND 99, EL_PASO 6 (naive reference: 28, 20, 16, 0). There
were no exhausted or errored steps, so these withholdings have another cause, explained in Finding 8. Steps that
never reached G6 (`n_not_g6`): AUSTIN 225 (the G4 fallbacks), MIDLAND 68, CORPUS_CHRISTI 0, EL_PASO 0.

### Coverage by number of backtest residuals

| city | method | period | bucket | n | coverage_nominal | n_zero_width |
| --- | --- | --- | --- | --- | --- | --- |
| AUSTIN | ml | warmup | 0 | 0 |  | 1 |
| AUSTIN | ml | warmup | 1-47 | 28 | 0.6786 | 4 |
| AUSTIN | ml | warmup | 48-167 | 0 |  | 0 |
| AUSTIN | ml | warmup | 168+ | 0 |  | 0 |
| AUSTIN | ml | scored | 0 | 0 |  | 0 |
| AUSTIN | ml | scored | 1-47 | 16 | 0.875 | 0 |
| AUSTIN | ml | scored | 48-167 | 95 | 0.8 | 0 |
| AUSTIN | ml | scored | 168+ | 0 |  | 0 |
| AUSTIN | naive_replay | warmup | 0 | 0 |  | 1 |
| AUSTIN | naive_replay | warmup | 1-47 | 30 | 0.7333 | 2 |
| AUSTIN | naive_replay | warmup | 48-167 | 0 |  | 0 |
| AUSTIN | naive_replay | warmup | 168+ | 0 |  | 0 |
| AUSTIN | naive_replay | scored | 0 | 0 |  | 0 |
| AUSTIN | naive_replay | scored | 1-47 | 15 | 1.0 | 0 |
| AUSTIN | naive_replay | scored | 48-167 | 96 | 0.8438 | 0 |
| AUSTIN | naive_replay | scored | 168+ | 0 |  | 0 |
| CORPUS_CHRISTI | ml | warmup | 0 | 0 |  | 1 |
| CORPUS_CHRISTI | ml | warmup | 1-47 | 70 | 0.8286 | 1 |
| CORPUS_CHRISTI | ml | warmup | 48-167 | 82 | 0.8415 | 0 |
| CORPUS_CHRISTI | ml | warmup | 168+ | 0 |  | 0 |
| CORPUS_CHRISTI | ml | scored | 0 | 0 |  | 0 |
| CORPUS_CHRISTI | ml | scored | 1-47 | 0 |  | 0 |
| CORPUS_CHRISTI | ml | scored | 48-167 | 97 | 0.8454 | 0 |
| CORPUS_CHRISTI | ml | scored | 168+ | 239 | 0.9163 | 0 |
| CORPUS_CHRISTI | naive_replay | warmup | 0 | 0 |  | 1 |
| CORPUS_CHRISTI | naive_replay | warmup | 1-47 | 69 | 0.7971 | 2 |
| CORPUS_CHRISTI | naive_replay | warmup | 48-167 | 82 | 0.7805 | 0 |
| CORPUS_CHRISTI | naive_replay | warmup | 168+ | 0 |  | 0 |
| CORPUS_CHRISTI | naive_replay | scored | 0 | 0 |  | 0 |
| CORPUS_CHRISTI | naive_replay | scored | 1-47 | 0 |  | 0 |
| CORPUS_CHRISTI | naive_replay | scored | 48-167 | 97 | 0.866 | 0 |
| CORPUS_CHRISTI | naive_replay | scored | 168+ | 239 | 0.9163 | 0 |
| MIDLAND | ml | warmup | 0 | 0 |  | 1 |
| MIDLAND | ml | warmup | 1-47 | 37 | 0.8919 | 10 |
| MIDLAND | ml | warmup | 48-167 | 102 | 0.8627 | 0 |
| MIDLAND | ml | warmup | 168+ | 0 |  | 0 |
| MIDLAND | ml | scored | 0 | 0 |  | 0 |
| MIDLAND | ml | scored | 1-47 | 0 |  | 0 |
| MIDLAND | ml | scored | 48-167 | 21 | 0.8095 | 0 |
| MIDLAND | ml | scored | 168+ | 247 | 0.8138 | 0 |
| MIDLAND | naive_replay | warmup | 0 | 0 |  | 1 |
| MIDLAND | naive_replay | warmup | 1-47 | 46 | 0.8043 | 3 |
| MIDLAND | naive_replay | warmup | 48-167 | 100 | 0.88 | 0 |
| MIDLAND | naive_replay | warmup | 168+ | 0 |  | 0 |
| MIDLAND | naive_replay | scored | 0 | 0 |  | 0 |
| MIDLAND | naive_replay | scored | 1-47 | 0 |  | 0 |
| MIDLAND | naive_replay | scored | 48-167 | 22 | 0.7727 | 0 |
| MIDLAND | naive_replay | scored | 168+ | 246 | 0.813 | 0 |
| EL_PASO | ml | warmup | 0 | 0 |  | 1 |
| EL_PASO | ml | warmup | 1-47 | 45 | 0.7556 | 4 |
| EL_PASO | ml | warmup | 48-167 | 106 | 0.9434 | 0 |
| EL_PASO | ml | warmup | 168+ | 0 |  | 0 |
| EL_PASO | ml | scored | 0 | 0 |  | 0 |
| EL_PASO | ml | scored | 1-47 | 0 |  | 0 |
| EL_PASO | ml | scored | 48-167 | 14 | 0.7857 | 0 |
| EL_PASO | ml | scored | 168+ | 322 | 0.8882 | 0 |
| EL_PASO | naive_replay | warmup | 0 | 0 |  | 1 |
| EL_PASO | naive_replay | warmup | 1-47 | 48 | 0.7292 | 1 |
| EL_PASO | naive_replay | warmup | 48-167 | 106 | 0.9528 | 0 |
| EL_PASO | naive_replay | warmup | 168+ | 0 |  | 0 |
| EL_PASO | naive_replay | scored | 0 | 0 |  | 0 |
| EL_PASO | naive_replay | scored | 1-47 | 0 |  | 0 |
| EL_PASO | naive_replay | scored | 48-167 | 14 | 0.7857 | 0 |
| EL_PASO | naive_replay | scored | 168+ | 322 | 0.8851 | 0 |

Reading: bucket 0 is always empty because a forecast with no residuals has a zero-width band
(`n_zero_width`). In the scored window the ml coverage in the 168+ residual bucket is 0.9163 (CORPUS_CHRISTI, n =
239), 0.8138 (MIDLAND, n = 247) and 0.8882 (EL_PASO, n = 322); AUSTIN has no step with 168 or more residuals (95
steps in 48-167 at 0.80, 16 in 1-47 at 0.875). MIDLAND's shortfall persists in its 168+ bucket (0.8138, n = 247), so
it is not a short-history effect. For AUSTIN no step reached that bucket, so the data cannot say, and its history is
sparse (Finding 7). In the warm-up period, steps with few residuals cover less (for example AUSTIN 1-47 residuals:
0.6786, n = 28), as expected for a young band.

### Detector trip rate by voting branch

| city | method | n_g6_evaluated | n_g6_trips | trip_rate | trip_rate_ci_lo | trip_rate_ci_hi | forecast_runs | rolling_runs | model_runs | cold_start_runs | forecast_votes | rolling_votes | model_votes | detector_errors | n_g6_trips_unattributed | model_trip_rate | n_detector_model_missing | anomaly_ml_max_false_positive_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AUSTIN | ml | 111 | 4 | 0.036 | 0.0 | 0.0935 | 15 | 96 | 111 | 0 | 0 | 4 | 0 | 0 | 0 | 0.0 | 0 | 0.05 |
| AUSTIN | naive_replay | 111 | 0 | 0.0 | 0.0 | 0.0 | 83 | 28 | 111 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | 0.05 |
| CORPUS_CHRISTI | ml | 336 | 37 | 0.1101 | 0.0595 | 0.1637 | 233 | 103 | 336 | 0 | 0 | 0 | 37 | 0 | 0 | 0.1101 | 0 | 0.05 |
| CORPUS_CHRISTI | naive_replay | 336 | 37 | 0.1101 | 0.0595 | 0.1637 | 316 | 20 | 336 | 0 | 0 | 0 | 37 | 0 | 0 | 0.1101 | 0 | 0.05 |
| MIDLAND | ml | 268 | 2 | 0.0075 | 0.0 | 0.0229 | 169 | 99 | 268 | 0 | 2 | 0 | 0 | 0 | 0 | 0.0 | 0 | 0.05 |
| MIDLAND | naive_replay | 268 | 0 | 0.0 | 0.0 | 0.0 | 252 | 16 | 268 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | 0.05 |
| EL_PASO | ml | 336 | 1 | 0.003 | 0.0 | 0.0089 | 330 | 6 | 336 | 0 | 0 | 0 | 1 | 0 | 0 | 0.003 | 0 | 0.05 |
| EL_PASO | naive_replay | 336 | 1 | 0.003 | 0.0 | 0.0089 | 336 | 0 | 336 | 0 | 0 | 0 | 1 | 0 | 0 | 0.003 | 0 | 0.05 |

Trip rate = G6 trips / `n_g6_evaluated`, with its bootstrap interval; the last column is the design false-positive
ceiling `config.ANOMALY_ML_MAX_FALSE_POSITIVE_RATE` = 0.05, used when the anomaly models were selected on
historical holdout data (not a promise about live behaviour).

- **AUSTIN (ml):** 4 trips in 111 evaluated steps, 0.0360 (0.0 to 0.0935), all from the rolling-baseline branch.
  Naive reference: 0 trips.
- **CORPUS_CHRISTI (ml):** 37 trips in 336, 0.1101 (0.0595 to 0.1637), all from the learned-model branch
  (`model_votes` 37). The lower end of the interval is above 0.05. The naive reference has the same 37 trips,
  because the model branch does not depend on the forecast.
- **MIDLAND (ml):** 2 trips in 268, 0.0075 (0.0 to 0.0229), both from the forecast branch. Naive reference: 0.
- **EL_PASO (ml):** 1 trip in 336, 0.0030 (0.0 to 0.0089), from the learned-model branch; same in the reference.

Detector errors: 0 in every city. Steps with no anomaly model loaded: 0. Unattributed trips: 0. Forecast branch
runs, rolling-baseline runs and model runs are in the table; the model branch ran at every evaluated step.

### G6 trips

| city | method | trips_listed |
| --- | --- | --- |
| AUSTIN | ml | 4 |
| CORPUS_CHRISTI | ml | 37 |
| CORPUS_CHRISTI | naive_replay | 37 |
| MIDLAND | ml | 2 |
| EL_PASO | ml | 1 |
| EL_PASO | naive_replay | 1 |

The full capped trip lists (at most 50 per city and method, ordered by deviation) are in
`real_data_validation/val02_g6_trips.csv`.

Silent failures: forecasts silently absent despite enough usable history 0, suspected cleaning failures 0,
unloaded anomaly models 0, detector errors 0, in every city. Forecasts withheld from G6 for a gap: see above and
Finding 8.

## Explanations

Every statement below is drawn from the tables above, `val02_g6_trips.csv`, the manifest, or exact counts read from
the trace (marked "trace"). Where the data cannot explain something it says so.

### AUSTIN

- **Computed below the lower bound (225 scored steps, 66.96%).** The five lowest computed ratings (832.3 to 865.4
  A) all occur in near-calm conditions: projected wind 0.168 to 0.581 m/s (measured 0.492 to 1.699 m/s) at air
  temperatures of 24.3 to 34.3 C and solar 0 to 768 W/m2, so neither temperature nor solar separates them. The
  drivers table separates the groups by wind geometry: below-bound steps have a median perp_fraction of 0.3559
  (the measured wind runs about 21 degrees off the line axis) and projected wind 0.78 m/s, against 0.9345 and
  2.034 m/s for accepted steps. Trace: 152 of 336 scored steps have wind within 30 degrees of the assumed 173.15
  degree axis, and the fallbacks occur at every local hour (117 of 225 between 20:00 and 06:59 local, against 11
  of 24 hours), so this is not a night-only effect. The first record of the run shows the pattern: 2026-09-08T00:00Z,
  33.8 C, measured wind 1.34 m/s from 146 degrees, projected 0.61 m/s, solar 191 W/m2, computed 938 A, "G4 FAIL
  (implausible (938 A))", fallback 1825 A. The STATE.md observation of 2026-10-19 (computed 1080 A below the 1150 A
  bound, published 1825 A) is the typical Austin outcome in this window, not an exception.
- **Why the line bearing matters here.** `line_bearing_check.md` found no single dominant axis near Austin (R =
  0.46; dominant axis 30 degrees within 30 km) and kept the carried-over 173.15 as an assumption. Because wind
  geometry is the main separator above, Austin's G4 rate depends on that assumption. The size of that dependence
  was not measured here (nothing was recomputed with another bearing).
- **Computed below the static rating at every step.** The static 1825 A is the owner-supplied 345 kV bundle average
  of 3650 A divided by 2 subconductors, and the 1150-2500 A bounds are the bundle ranges divided by 2
  (`config.py` lines 41-51 and 97-116). The computed rating is one Drake ACSR conductor at 75 C and 900 m
  elevation (`config.py` lines 138-148). The data cannot say which side of that mismatch is wrong; it only shows
  that, under these assumptions, physics is below the static rating at every Austin step.
- **Upward fallbacks (229).** All 225 G4 fallbacks and all 4 G6 fallbacks publish 1825 A, above computed by a median
  of 780.1 A (maximum 992.7 A).
- **G6 trips (4, rolling-baseline branch).** The four highest computed ratings of the window (1478.3 to 1569.5 A,
  strong near-perpendicular wind of 3.1 to 4.4 m/s) deviated from the rolling baseline mean (1223.5 to 1226.7 A) by
  +254.8 to +343.6 A and fell above its upper band edge (1449.6 to 1462.3 A) by 28.7 to 107.5 A
  (`val02_g6_trips.csv`). The baseline is built only from hours the gates accepted (151 usable rows of 504, Finding
  7), so its mean (about 1225 A) sits above the median of all computed hours (1105.0 A). The data are consistent
  with the baseline being a selected sample but do not prove it. Each trip published 1825 A, above computed by 255.5
  to 346.7 A.
- **Forecast.** The ml forecast gated G6 on only 15 of the 111 evaluated steps; at the other 96 the forecast was
  withheld across a gap and the rolling baseline was used (Finding 8).

### CORPUS_CHRISTI

- **No G4 fallbacks, no step outside the 800-2200 A bounds.** The lowest computed ratings (902.7 to 932.2 A) are
  calm, mild, dark or dim hours (projected wind 0.28 to 0.37 m/s, 23 to 29 C, solar 0 to 21 W/m2) and are accepted as
  computed because they are above the 800 A bound.
- **G6 trips (37, all learned-model branch).** The model flagged the reading as outside its learned per-variable
  envelope. Decision scores are negative but mostly small: median -0.0831, minimum -0.5483, and 22 of the 37 are
  above -0.1 (marginal). Trace and `val02_g6_trips.csv`: 29 of the 37 fall between 10:00 and 18:59 local time; 8
  fall on 2026-09-15 alone, in hot, bright, windy conditions (33.3 to 36.7 C, measured wind 4.6 to 5.7 m/s, solar
  415 to 890 W/m2), including the five strongest scores (-0.3857 to -0.5483). Ten of the 14 scored days have at
  least one trip. The warm-up period has 61 trips in 168 steps (36.31%).
- **What the data can and cannot say.** The envelope was learned from 2023-2025 Open-Meteo reanalysis; in this run
  the air temperature came from ASOS (238 scored steps) and Synoptic (98) stations (trace), the wind from TCEQ and
  the solar radiation from Open-Meteo. Either a too-tight envelope or a systematic difference between station and
  reanalysis inputs would produce scores just below zero; nothing in this run separates them, because no
  reanalysis value for the same hours was compared.
- **Direction of the fallback.** G6 publishes the static 1500 A: 32 of the 37 are above the computed value
  (median +113.9 A, maximum +410.7 A) and 5 are below it (computed 1506.9 to 1682.5 A, including the two highest
  computed ratings of the window, 1682.5 A at 2026-09-18T06:00Z and 1652.6 A at 03:00Z, scores -0.0183 and
  -0.0048).
- **Highest accepted values** (1634.9 to 1665.6 A, 2026-09-24 19:00Z to 21:00Z, afternoon local) occur at 6.0 to
  6.4 m/s measured wind and 31.7 to 31.9 C with solar of 768 to 808 W/m2 and Synoptic temperature.
- **Observation lag.** The aligned weather hour is one hour before the run slot at 324 of 336 scored steps, two
  hours at 10 and three hours at 2 (trace); in AUSTIN it equals the run slot at every step. The data do not say
  which provider causes the lag.

### MIDLAND

- **Computed below the lower bound (68 scored steps, 20.24%).** The five lowest computed ratings (917.0 to 975.3 A)
  have projected wind of 0.489 to 0.961 m/s (measured 1.431 to 2.459 m/s). Drivers table: below-bound steps have
  perp_fraction 0.342 and projected wind 1.17 m/s against 0.8946 and 3.85 m/s for accepted steps, the same
  mechanism as AUSTIN. Wind directions at three of the five lowest steps are 97 to 102 degrees, within about 15
  degrees of the assumed 267.54 degree line axis (axis 87.54).
- **Clustering.** Trace: fallbacks per UTC day are 13 on 2026-09-27 and 9 each on 09-23 and 09-28, against 2 to 3
  on 09-24 to 09-26 and none on 09-15, 09-17, 09-18; the low-side fallbacks come in multi-day light-wind regimes.
  The data do not say what weather caused them.
- **Never above static.** Computed ratings reach at most 1858.0 A (7.2 m/s measured wind, near-perpendicular), so no
  step is above the 1875 A static rating. The highest five (1816.7 to 1858.0 A) are accepted as computed.
- **G6 trips (2, forecast branch).** 2026-09-16T05:00Z and 06:00Z: computed 1343.4 and 1412.4 A against a forecast
  centre of 1769.2 A (widened band 1543.1 to 2494.2 A), after accepted ratings rose from 1624.0 A (01:00Z) to
  1753.4 A (04:00Z). Both published 1875 A, above computed by 531.6 and 462.6 A. The forecast centre is identical
  at the two steps, consistent with the 05:00Z fallback row being excluded from the usable history (trace: usable
  rows 188 at both steps); at 07:00Z the forecast is withheld for the gap (trace: `forecast_used_by_g6` false).

### EL_PASO

- **No G4 fallbacks.** The lowest computed ratings (856.3 to 900.5 A) are well above the 640 A bound: light measured
  wind (0.4 to 0.7 m/s projected), 28.8 to 33.1 C and strong sun (solar 418 to 693 W/m2). The highest (1749.4 to
  1787.7 A) occur at cool night hours (19.4 to 21.8 C, no sun) with 4.5 to 5.0 m/s projected wind, well below the
  2000 A upper bound and above the 1320 A static rating (19.35% of steps).
- **Single G6 trip.** 2026-09-23T07:00Z from the learned-model branch at decision score -0.0002 (effectively on
  the boundary), computed 1747.0 A at 17.1 C, 4.43 m/s measured wind, no sun. The fallback published 1320 A, 427.0
  A below computed (a downward fallback).
- **Small warm-up difference.** 2 G6 trips in 168 warm-up steps.

### Categories with no occurrences

Computed above the upper bound (G4_high), G1, G2, G3, G5, exhausted, errored, untraced and missing steps are 0 in
all four cities in both periods. Upward fallbacks occur in AUSTIN, MIDLAND and CORPUS_CHRISTI; EL_PASO has none.

## Findings for the owner

Nothing was changed in this phase. Each finding gives the evidence and options for the owner to choose between.

**1. Upward-fallback exposure (VAL-01).** Evidence: Fallback direction table above; STATE.md "Output Observations"
(lines 107-112). In the scored window the pipeline published a value above the computed rating at 229 of 336 steps
in AUSTIN (68.15%; median +780.1 A, p95 +919.1, maximum +992.7), 70 in MIDLAND (20.83%; median +712.3, maximum
+958.0) and 32 in CORPUS_CHRISTI (9.52%; median +113.9, maximum +410.7); none in EL_PASO. Across the four cities
that is 331 of 1344 scored city-steps (24.63%). The STATE.md observation (AUSTIN 1080 A computed, 1825 A published
on 2026-10-19, MIDLAND exposed too) is a modal outcome in this window, not an exception. `config.py` (lines 97-116)
records that computed ratings were expected to fall below the AUSTIN and MIDLAND lower bounds in "roughly 5-30%"
of hours and that the owner accepted this; the measured low-side G4 share here is 66.96% (AUSTIN) and 20.24%
(MIDLAND), over one late-summer fortnight with wind direction projected.
  - Option A: keep the policy and bounds as they are and document the measured rates, with the fallback flag
    carried to every consumer. Trade-off: consumers will see a published value that is, on a majority of Austin
    hours, far above what the physics model computed.
  - Option B: change the fallback policy so that a fallback never publishes more than the computed rating (or
    publishes the lower bound, or no value). Trade-off: a rating-policy change owned by the bounds and fallback
    owner, which alters what Phase 4 stores and what Phase 6 checks.
  - Option C: first reconcile static ratings, bounds, conductor model and bearings (Finding 9) and re-measure.
    Trade-off: needs Power Systems input and delays the decision.

**2. ml wind feature differs between training and serving (VAL-02).** Evidence: `backend/forecast_training.py`
lines 204-224: `city_training_frame` computes the line-perpendicular wind only to compute `dlr_amps` and keeps the
measured `wind_speed` as the model feature. `backend/city_rating.py` lines 93-110: `_project_wind` replaces the
observation's `wind` with the perpendicular component, so the archived `wind_speed` is the projected value
(documented in `historical_archive`). `backend/ampacity_forecast.py` lines 124-161: at inference
`build_ml_features` reads the archive's `wind_speed` (`config.FORECAST_ML_FEATURE_WEATHER_COLUMNS` includes
`wind_speed`, line 311). So the model is trained on measured speed and served the projected speed, which is
smaller by construction (trace: median perp_fraction over scored steps 0.547 AUSTIN, 0.859 CORPUS_CHRISTI, 0.861
MIDLAND, 0.580 EL_PASO). The ml band shows a positive bias (computed minus forecast centre) of +87.6, +41.9, +49.8
and +77.6 A in the four cities against about 0 for naive. The direction agrees with a wind feature that is too
low, but this run has no ablation, so the cause is not established. The archive has no measured-wind or
wind-direction column (`ARCHIVE_COLUMNS`), so the measured speed cannot be rebuilt from the archive.
  - Option A: leave it and record the offset as a known property of the ml band.
  - Option B: retrain the four forecast models with the projected speed as the feature (and re-run this
    validation). Trade-off: new model hashes, and the earlier ml-modeling evaluation no longer describes them.
  - Option C: keep the models and store the measured wind speed and direction with each row so the feature can be
    served as trained. Trade-off: a schema change that Phase 4 would need to carry.

**3. ml versus naive on coverage, MAE and trip rate (context for OD-3).** Evidence: forecast and detector tables.
Coverage of the 90% band: ml 0.8108 / 0.8958 / 0.8134 / 0.8839 against naive 0.8649 / 0.9018 / 0.8097 / 0.8810
(AUSTIN / CORPUS_CHRISTI / MIDLAND / EL_PASO). MAE: ml 104.1 / 86.4 / 94.2 / 126.7 A against naive 62.3 / 62.9 /
80.3 / 117.3 A, so naive has lower MAE in all four cities. Trip rate: ml 0.036 / 0.1101 / 0.0075 / 0.003 against
naive 0 / 0.1101 / 0 / 0.003. The EWM method was not replayed. OD-3 chose `ml` for the live path; this is context
only. The naive rows are a counterfactual on the same observations and use a different history (their withheld
counts differ), so they are a reference, not a competing live run.
  - Option A: keep `ml` as decided in OD-3 and carry the measured gap as a known limitation.
  - Option B: switch the live method to naive (or run a replay with `ewm`) before Phase 4. Trade-off: a reversal of
    OD-3, with the model-provisioning work in Phases 4-5 no longer needed for the forecast.
  - Option C: keep `ml` but add a bias correction after fixing Finding 2. Trade-off: new modelling work.

**4. Detector trip rate and the branch that drives it (VAL-02).** Evidence: detector table, `val02_g6_trips.csv`.
CORPUS_CHRISTI trips at 11.01% (interval 5.95% to 16.37%, above the 0.05 reference ceiling), every trip from the
learned-model branch, mostly marginal scores, mostly between 10:00 and 18:59 local time and on hot, bright, windy
hours. The other cities are at 3.6% (rolling branch), 0.75% (forecast branch) and 0.30% (model branch), inside the
reference. No detector error and no missing model occurred. The cause (envelope too tight versus station inputs
differing from the training reanalysis) is not separated by this run.
  - Option A: accept the rate and the fallback (static 1500 A, mostly above the computed value).
  - Option B: ask the ml-modeling owners to re-check the CORPUS_CHRISTI anomaly model on station-measured inputs
    for the same hours, then decide on a threshold or refit. Trade-off: a model change outside this workstream.
  - Option C: change the G6 vote rule for the model branch. Trade-off: a safety-policy change.

**5. Input provenance (VAL-01).** Evidence: console summary, drivers table, trace counts. Solar came from Open-Meteo
for all 2016 city-steps (the only reanalysis-derived input); NSRDB returned HTTP 400 for year 2026 (STATE.md
integration item 3). Wind came from TCEQ for all 2016. Air temperature came from TCEQ for AUSTIN, MIDLAND and
EL_PASO at all 504 steps each, and from ASOS (384) and Synoptic (120) for CORPUS_CHRISTI. Observation lag: zero in
AUSTIN; in CORPUS_CHRISTI the aligned weather hour is one hour before the run slot at every step (scored: 324 at 1
h, 10 at 2 h, 2 at 3 h); one step each in MIDLAND and EL_PASO is 1 h. The models were trained on reanalysis for all
three variables, so for temperature and wind the live inputs differ in kind from the training inputs.
  - Option A: accept Open-Meteo solar and record the source per row.
  - Option B: pursue a measured or NSRDB solar source for the current year. Trade-off: provider work and cost.
  - Option C: measure the effect of the solar and temperature source on the rating before deciding. Trade-off:
    more analysis, no change to this run.

**6. History gap between 2026-09-28 and go-live; OD-8 read window (Phase 4 input).** Evidence: manifest window;
`data_cleaning.py` lines 75-92 (`MAX_TRAILING_GAP_SLOTS` = 1, `ML_LOOKBACK_ROWS` = 7). The archive ends at
2026-09-28T23:00Z. OD-8 limits the live read to the last 30 days, so the newest archived row leaves that window on
2026-10-28. Independently, an ml forecast whose lookback spans a gap is computed but withheld from G6 until the
newest 7 usable rows are on consecutive hours, so after a gap G6 runs on the rolling baseline and the learned
model. If the history before go-live is not contiguous, the ml forecast will not gate G6 for roughly the first
hours of live operation.
  - Option A: a top-up backfill from 2026-09-29 to go-live with the same command and trace, then load both. Trade-off:
    provider calls, and the window must first be cleared against the anti-peeking rule that this phase's cutoff
    of 2026-09-29 respected.
  - Option B: load only this archive in Phase 4 and accept a cold start at go-live.
  - Option C: seed the live history with a short backfill immediately before go-live (at least the
    `FORECAST_MIN_HISTORY_ROWS` = 12 usable rows, with the newest 7 on consecutive hours for ml). Trade-off: it must
    be repeated at go-live time and is only as good as the providers' recent data.

**7. Cleaning activity (VAL-01).** Evidence: `report_meta.json` `cleaning` block and the table below (every flag in
`data_cleaning.FLAG_ORDER`).

| city | rows_in | rows_usable | rows_excluded | missing_slots | bad_timestamp | duplicate | fallback | at_or_after_run | same_hour | stuck_air_temp | stuck_wind_speed | stuck_solar_radiation | spike_air_temp | spike_wind_speed | spike_solar_radiation | after_gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AUSTIN | 504 | 151 | 353 | 350 | 0 | 0 | 353 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 56 |
| CORPUS_CHRISTI | 504 | 400 | 104 | 103 | 0 | 0 | 98 | 0 | 0 | 6 | 0 | 0 | 0 | 0 | 0 | 33 |
| MIDLAND | 504 | 425 | 79 | 79 | 0 | 0 | 79 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 25 |
| EL_PASO | 504 | 501 | 3 | 3 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 |

AUSTIN keeps 151 usable rows of 504; all 353 excluded rows carry the `fallback` flag, 350 hourly slots are missing and
56 usable rows follow a gap. CORPUS_CHRISTI keeps 400 (104 excluded: 98 `fallback` and 6 `stuck_air_temp`; 103 missing
slots; 33 rows after a gap). MIDLAND keeps 425 (79 `fallback`; 25 after a gap). EL_PASO keeps 501 (3 `fallback`; 2
after a gap). Every other flag (`bad_timestamp`, `duplicate`, `at_or_after_run`, `same_hour`, `stuck_wind_speed`,
`stuck_solar_radiation`, `spike_air_temp`, `spike_wind_speed`, `spike_solar_radiation`) is 0 in all four cities. At
each run's own `as_of` the excluded rows it could see peaked at 353 / 104 / 79 / 3 and had medians of 184.5 / 85.0 /
14.0 / 2.0 (AUSTIN / CORPUS_CHRISTI / MIDLAND / EL_PASO, `report_meta.json`). The only effect of cleaning in this window
is therefore to remove fallback rows from the history, so the forecast, the rolling baseline and the detector's
history see only hours the gates accepted, plus one stuck-temperature event of 6 rows at CORPUS_CHRISTI. The stuck and
spike thresholds (6 rows; 10 C, 10 m/s, 700 W/m2 per hour) are provisional and unfitted (STATE.md, 02-03); zero spike
flags and zero stuck wind or solar flags show neither that they are too tight nor that they catch anything.
  - Option A: leave the rules and record the measured flag rates.
  - Option B: revisit the thresholds on a longer or different-season window, where spikes and stuck sensors are more
    likely to occur. Trade-off: more data collection.
  - Option C: reconsider excluding fallback rows from the history (Finding 8). Trade-off: a Phase 2 rule change.

**8. Forecasts withheld from G6 for a gap, and suspected cleaning failures (VAL-02).** Evidence: forecast table
(`n_withheld_gap`, `n_cold_start`, `n_silent_forecast_failure`, `n_cleaning_failure_suspect`), detector table
(`forecast_runs`, `rolling_runs`), cleaning table. Cold starts, silent forecast failures and suspected cleaning
failures are 0 in every city. The ml forecast was nevertheless withheld from G6 at 96 of 111 evaluated steps in
AUSTIN, 103 of 336 in CORPUS_CHRISTI, 99 of 268 in MIDLAND and 6 of 336 in EL_PASO (naive reference: 28, 20, 16, 0).
In each city `rolling_runs` equals `n_withheld_gap`, so at those steps G6 judged the rating against the rolling
baseline instead of the forecast. The share of evaluated steps on which the ml forecast gated G6 is 13.5% (15 of 111)
in AUSTIN, 69.3% in CORPUS_CHRISTI, 63.1% in MIDLAND and 98.2% in EL_PASO. There were no exhausted or errored steps,
which is the cause the design anticipated for gaps; the cause here is different. Phase 2 cleaning excludes fallback
rows from the usable history, so every fallback leaves a missing hourly slot (cleaning table: missing slots are
within 3 of the number of excluded rows in every city), and the ml forecast is withheld until its newest 7 usable rows
are consecutive hours again (`data_cleaning.ML_LOOKBACK_ROWS`; naive is withheld only by the one-slot trailing-gap
rule). Fallbacks therefore reduce the forecast branch's availability for the hours that follow. The Phase 2 rule is
provisional until Phase 3 (STATE.md decision for 02-04).
  - Option A: keep the rule; the rolling baseline and the learned model still gate G6 at those steps.
  - Option B: relax it, for example by allowing fallback rows or short gaps in the ml lookback. Trade-off: the ml
    model was trained on a gap-free hourly series, so its features become less like training data.
  - Option C: keep the rule but record `forecast_used_by_g6` per row downstream so the share is visible to consumers.

**9. Static ratings, bounds and the computed rating rest on different assumptions (VAL-01).** Evidence: ratings
table, `config.py` lines 41-51, 97-116, 138-148, 216-221. The static ratings and G4 bounds come from owner-supplied
345 kV bundle ranges divided by an assumed number of subconductors per phase; the computed rating is one Drake ACSR
conductor at 75 C and 900 m elevation for every city, with assumed line bearings. Computed is below the static
rating at every step in AUSTIN and MIDLAND and at 83.63% and 80.36% of steps in CORPUS_CHRISTI and EL_PASO. The data
cannot say which side is wrong; they only show that under the current assumptions the gap is large and systematic in
the two cities whose lower bound is reached.
  - Option A: keep all values labelled provisional (OD-5) and carry this finding into the schema documentation.
  - Option B: ask Power Systems to confirm the basis (per conductor or per bundle), the subconductor counts, the
    maximum conductor temperature (PROV-01), elevation and the line azimuths, then refit and re-run this validation.
    Trade-off: external input and a refit of models and shadow artifacts (see `line_bearing_check.md`).
  - Option C: set the bounds and static ratings to the computed model's own basis. Trade-off: a policy change that
    discards the owner-supplied ranges.

**10. Self-checks, exhaustion and errors.** No finding: all self-checks are 0, 2016 of 2016 steps have a trace record
and an archive row, no step is exhausted or errored, and the offline replay reproduced the original run with 0
mismatches in 2016 comparisons.

## Limits

- **One late-summer window.** 14 scored days (336 steps per city) in September 2026; no winter, storm, extreme heat
  or cold-front period. Rates would differ in other seasons.
- **Reanalysis-derived inputs.** Solar came from Open-Meteo reanalysis at every step because NSRDB has no 2026 data.
  The models were trained on reanalysis for all three variables, while this run used station air temperature and
  wind.
- **No anomaly ground truth.** There are no labelled anomalies, so the detector results are trip rates (how often it
  flags), not accuracy, recall or precision.
- **Hourly autocorrelation.** Consecutive hours are not independent, so a plain binomial interval would be too
  narrow; the intervals use whole-UTC-day blocks, and with only 14 days they are wide and approximate.
- **Warm-up excluded from the headline.** The first 168 steps are shown but not counted in the scored rates; the
  archive started empty.
- **Naive replay is a reference.** It uses the traced observations, not new weather, and starts from an empty archive;
  EWM was not replayed.
- **Modelling assumptions.** Provisional static ratings and bounds (OD-5), assumed line bearings
  (`CITY_LINE_BEARING_DEG`, `line_bearing_check.md`), and one Drake ACSR conductor with `max_temp_c` 75 and
  `elevation_m` 900 for every city (PROV-01) bear directly on the rating level and are not changed or tested here.
- **Explanations are partly hypotheses.** Where the text says the data are consistent with a cause, no experiment
  separated it from the alternatives.

## Go/no-go

This section lays out what the decision rests on. It does not recommend or choose.

### (a) Questions and measured answers

| Question | Measured answer (scored window, 336 steps per city) |
| --- | --- |
| Did every city produce a rating at every step? | Yes. 504 of 504 steps per city have a trace record, an archive row and a log row; 0 exhausted, 0 errored, 0 missing. Of the scored steps, the published rating equals the computed one at 107 / 299 / 266 / 335 steps (AUSTIN / CORPUS_CHRISTI / MIDLAND / EL_PASO), and a fallback value was published at 229 / 37 / 70 / 1. |
| How often, and by how much, did a fallback report more than physics computed? | AUSTIN 229 steps (68.15%), median +780.1 A, maximum +992.7 A; MIDLAND 70 (20.83%), median +712.3 A, maximum +958.0 A; CORPUS_CHRISTI 32 (9.52%), median +113.9 A, maximum +410.7 A; EL_PASO 0. Total 331 of 1344 city-steps (24.63%). |
| Is the ml band calibrated near its nominal 90%? | Coverage 0.8108 (0.7327 to 0.8800), 0.8958 (0.8452 to 0.9435), 0.8134 (0.7719 to 0.8567), 0.8839 (0.8363 to 0.9256) for AUSTIN / CORPUS_CHRISTI / MIDLAND / EL_PASO. The intervals for AUSTIN and MIDLAND exclude 0.90; those for CORPUS_CHRISTI and EL_PASO contain it. Naive reference: 0.8649, 0.9018, 0.8097, 0.8810. |
| How often does the detector trip, and does it ever error? | Trip rate 0.0360 / 0.1101 / 0.0075 / 0.0030; CORPUS_CHRISTI is above the 0.05 reference ceiling (interval 0.0595 to 0.1637) and every one of its trips is from the learned-model branch. Detector errors: 0 in every city. |
| Did the ml forecast or the anomaly model ever fail silently? | No. Silent forecast failures 0, suspected cleaning failures 0, anomaly models not loaded 0, detector errors 0, in every city. Not a failure but a degradation: the ml forecast was withheld from G6 at 96 / 103 / 99 / 6 evaluated steps (Finding 8). |
| How much of the input is reanalysis? | Solar: 100% Open-Meteo (all 2016 city-steps). Wind: 0% (TCEQ stations). Air temperature: 0% (TCEQ, ASOS, Synoptic stations). |

### (b) Candidate blocking fixes, for the owner to confirm, amend or drop

Each is tied to a finding above and is a candidate only. None is applied.

- **B1 (Findings 1, 9).** A decision on the fallback policy and the rating basis: either confirm that a fallback may
  publish more than the computed rating at the measured rates, or change the policy; and confirm or correct the
  static ratings, bounds, conductor model and bearings that drive those rates.
- **B2 (Finding 2).** Align the ml wind feature between training and serving, or confirm the offset is acceptable.
- **B3 (Finding 6).** Provide a contiguous history up to go-live (top-up backfill or equivalent) so the live read
  window (OD-8) and the ml lookback are satisfied.
- **B4 (Finding 4).** Decide whether the CORPUS_CHRISTI detector trip rate (11.01%) is acceptable.
- **B5 (Finding 8).** Decide whether fallbacks may reduce the forecast branch's availability as measured.
- **B6 (Finding 5).** Decide whether Open-Meteo solar (and its labelling) is acceptable for the first live runs.

### (c) The three options and their consequence for Phase 4

- **GO.** Phase 4 starts. The findings above are tracked as known issues with no condition attached. Consequence: the
  database schema and loader are built against the measured behaviour; the rates in this note become the baseline
  that later phases compare with.
- **GO WITH CONDITIONS.** Phase 4 starts, and named conditions from (b) must be met by a stated point, for example
  before Phase 5's live runs. Consequence: Phase 4 proceeds in parallel with the listed fixes; the owner names which
  of B1-B6 are conditions and by when, and a condition that changes a model or a rating policy would require this
  validation to be re-run on the new values.
- **NO-GO.** Phase 4 does not start. The blocking fixes the owner confirms from (b) are the work list. Consequence:
  integration waits for those fixes and a re-validation.

## Decision

**Decision:** NO-GO

**Owner's words:**

> 0305 is no go, blocking on b1, b2, b4, b5. record that decision

**Blocking fixes:**

1. **B1 (Findings 1, 9).** A decision on the fallback policy and the rating basis: either confirm that a fallback may
   publish more than the computed rating at the measured rates, or change the policy; and confirm or correct the
   static ratings, bounds, conductor model and bearings that drive those rates. (Context, not the owner's words: the
   owner confirmed the subconductor counts, 2 / 2 / 2 / 1, are correct, so the open question is the conductor type,
   maximum operating temperature, elevation and azimuth; those questions are with the Power Systems team.)
2. **B2 (Finding 2).** Align the ml wind feature between training and serving, or confirm the offset is acceptable.
3. **B4 (Finding 4).** Decide whether the CORPUS_CHRISTI detector trip rate (11.01%) is acceptable.
4. **B5 (Finding 8).** Decide whether fallbacks may reduce the forecast branch's availability as measured.

Not blocking: B3 (Finding 6) and B6 (Finding 5).

Phase 4 does not start until these are resolved and the validation is repeated.

**Signed by:** Aaron Phan, 2026-10-21

**Recorded by:** the executor, from the owner's reply at plan 03-05's checkpoint.

## Reproduce

The analysis is offline: it reads only the four git-ignored files named above and the models in the main checkout's
`data/models` (the replay needs the anomaly models and, for method `ml`, the forecast model; the naive replay
needs the anomaly models). It makes no network call. Run everything from `/Users/aphan/Senior_Design`.

1. The owner backfill command (as in Backfill record). Check afterwards:
   `shasum -a 256 data/historical/real_data_validation_2026-09-08_2026-09-28.csv` must print
   `18f999aac44540138cfb2a2d1c7f624688e66d261e391a01b036970b8bfa25cf`.
2. The naive replay (new output paths; any existing output is a refusal):

```
cd /Users/aphan/Senior_Design && P=data/historical/real_data_validation_2026-09-08_2026-09-28 && PYTHONPATH=backend .venv/bin/python backend/real_data_validation.py replay --archive $P.csv --trace ${P}_trace.jsonl --start 2026-09-08T00:00:00Z --end 2026-09-28T23:00:00Z --step-hours 1 --method naive --warmup-hours 168 --archive-out ${P}_replay_naive.csv --trace-out ${P}_replay_naive_trace.jsonl --log-out ${P}_replay_naive_log.csv --fidelity-out ${P}_replay_naive_fidelity.json
```

   It prints `replay fidelity: compared=2016, excluded=0, mismatches=0, ...` and exits 0.
3. The report:

```
cd /Users/aphan/Senior_Design && P=data/historical/real_data_validation_2026-09-08_2026-09-28 && OUT=/Users/aphan/Senior_Design/docs/data-science/decisions/real_data_validation && PYTHONPATH=backend .venv/bin/python backend/real_data_validation.py report --archive $P.csv --trace ${P}_trace.jsonl --replay-archive ${P}_replay_naive.csv --replay-trace ${P}_replay_naive_trace.jsonl --start 2026-09-08T00:00:00Z --end 2026-09-28T23:00:00Z --step-hours 1 --warmup-hours 168 --out-dir "$OUT"
```

   It exits 0 and writes the twelve files named in this note. A second run into an empty directory produced
   byte-identical files (`diff -r`, ignoring `manifest.json` and `run_completeness.csv`, which `report` does not
   write).
