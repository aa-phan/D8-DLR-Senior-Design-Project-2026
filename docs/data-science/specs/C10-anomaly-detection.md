# C10 — Learned Anomaly Detection

**Phase:** 4 (Predictive) · **Effort:** L · **Status:** Implemented. Shipped in **v1.3 Phase 2**
of the independent `ml-modeling` workstream (ANOM-01, ANOM-02). The System Design Report's claim
that a model was "currently being trained and tuned" (§3.2, "Data Integrity") was **inaccurate at
the time it was written** — `PRD.md` §10 Documentation Discrepancies records that discrepancy, and
correcting this section's status now does not erase that earlier claim was wrong when made.

## Responsibility

Replace or augment `DLRSafetyMonitor`'s (C7) deterministic threshold gates with a model trained on historical baselines per variable (wind, temp, solar, load), so anomaly detection can catch patterns that fixed range/delta thresholds miss — while preserving C7's non-negotiable fail-safe-to-static behavior.

## Current Implementation

`backend/anomaly_detector.py::AnomalyDetector.check(raw_data, rating)` dispatches across three
branches, combined via logical OR (D-05/D-06 — a trip on any branch trips the whole check, no
branch can suppress another):

- **`_check_against_forecast`** — the primary signal when a `ForecastResult` (C9) is available:
  widens C9's own confidence band by a per-location control-limit multiplier and flags a rating
  outside it.
- **`_check_against_rolling_baseline`** — the cold-start fallback when no forecast is available
  yet: a rolling mean ± k·standard-deviation band over archived `dlr_amps` history.
- **`_check_against_model`** (v1.3 Phase 2, ANOM-01) — a genuinely trained, per-city
  `scikit-learn` outlier estimator (`OneClassSVM`, the winner of the 2026-10-13 per-city three-candidate bake-off in all four cities: `AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND`, `EL_PASO`) that
  judges the **raw** `wind`/`temp`/`solar` readings in `raw_data` — never the derived `rating`
  the two branches above judge — against a learned per-variable envelope.

`backend/anomaly_training.py` is the offline training/measurement entry point: it assembles a
real Open-Meteo backfill series for one city (no pooling across cities), runs the bake-off,
measures false-positive and recall rates against synthetically injected corruption, and persists
each city's evidence-selected winner to `data/models/anomaly_{city}.joblib` (git-ignored generated
data — a clean checkout has no model until this script is run). `--city <CITY>` selects one city
(default: every city in `config.LOCATIONS`). **The per-city refit ran on 2026-10-13**
(`--validate`, `--bakeoff`, `--characterize-load`): `anomaly_{city}.joblib` was fit locally for all
four cities. The corridor-named artifacts (`anomaly_AUSTIN_CORPUS_CHRISTI.joblib`,
`anomaly_MIDLAND_EL_PASO.joblib`) are legacy and are not loaded. Because `data/models/` is
git-ignored, the per-city models exist only where the script has been run: in a clean checkout the
model branch is absent (`decisions/point_scope.md`). See
`docs/data-science/decisions/anomaly_detection_model.md` for the measured false-positive/recall
evidence — this section does not restate those numbers.

`backend/DLRSafetyMonitor.py`'s G1–G5 deterministic gates and its G6 call site/fail-safe wiring
were **not changed** by this phase.

## Interface & Data Contract

The settled contract, read off `backend/anomaly_detector.py`:

- **Function:** `AnomalyDetector.check(raw_data: dict, rating: float) -> tuple[bool, str]` —
  returns `(is_anomalous, reason)`, unchanged since before this phase.
- **Fail-safe resolution:** `DLRSafetyMonitor` resolves both a detected trip and any exception
  raised anywhere inside `check` (a broken model, a corrupt artifact, a feature-count mismatch)
  through its own existing G6 `except Exception -> _fallback` path, to the city's static
  rating. `AnomalyDetector` never builds `DLRSafetyMonitor`'s own `{status, rating, fallback,
  alerts}` result mapping and never imports `DLRSafetyMonitor` — the coupling runs one direction
  only.
- This is exactly the additive-to-C7's-interface, not-a-replacement shape this section originally
  called for — the original guidance here was right, and it is what was built.

## Blocked by

**C7** — the gating framework this component's learned signal plugs into. Already shipped and
unchanged as this component's dependency; the model judges raw sensor readings directly (D-01),
not the C7-computed rating, so it did not additionally require C7's own correctness to be
re-verified.

The **accumulated historical data** blocker this section originally anticipated (same lead-time
concern as C9's own Finding 5) was resolved the same way C9's was: rather than waiting for the
live `historical_archive.py` archive to accrue — it remains empty today, since Track 1 (Pipeline
Integration) has not executed — this phase assembled its own real (non-synthetic) series
**offline**, directly from Open-Meteo Archive API backfill (plus real ERCOT historical load for
the D-02 training-time characterization). See
`docs/data-science/decisions/anomaly_detection_model.md` for the full data-provenance detail.

## Blocks

Nothing else in this roadmap depends on C10 — it's the last component in the dependency chain.

## Parallel-safe with

**C9** — both Phase 4, distinct models, workable simultaneously by different people once both land.

## Known Issues

Sourced from `docs/data-science/decisions/anomaly_detection_model.md`'s Limitations section:

- **Per-city models are fit, and the record now carries per-city numbers.** The corridor-era model
  was trained on a pooled two-city envelope (both endpoint cities' readings concatenated); the
  point-scope change replaced that with one model per city trained on that city's own rows, refit
  on 2026-10-13. `decisions/anomaly_detection_model.md` has the per-city false-positive/recall
  figures (selected: `OneClassSVM` in all four cities, all four **MET**). The pooled corridor-era
  envelope's numbers (3.77% and 0.53% false-positive rate) are kept there as labeled history and
  do not describe the per-city models. The per-city measurements use a 2,190-row holdout and 44
  injected rows per category, so each category's recall moves in steps of 2.27 percentage points.
- A detector gets its city's model at construction (`AnomalyDetector.for_city(city, ...)`, with the
  city validated against `config.LOCATIONS` before an artifact path is built); `raw_data` itself
  carries no location identifier at the `check()` call site.
- **No time-of-day feature** — `raw_data` carries no timestamp at the `check()` call site, so a
  reading implausible at 2am but normal at 2pm is judged by the same learned envelope either way.
- Per **D-02**, ERCOT historical load is a **training-time-only** signal — a real, executed
  characterization exists (zone-matched correlations; characterized per corridor in the retired
  model, and per city on 2026-10-13, when all four cities succeeded with 8,731 load rows each; the
  per-city zone mapping is `config.ANOMALY_ML_ERCOT_ZONE_SUBSTRINGS_BY_CITY`), but it never reaches
  the live `check()` call, and wiring it in is Track 1's scope, not this component's. The zone group
  is `SOUTH` for `AUSTIN` and `CORPUS_CHRISTI` and `WEST` for `MIDLAND` and `EL_PASO`, so each pair
  shares one load series. `gridstatus` 0.35.0 is installed in `.venv` but is not listed in
  `requirements.txt`, a reproducibility caveat for `--characterize-load`.
- A clean checkout has **no persisted model artifact** until
  `.venv/bin/python3 backend/anomaly_training.py --bakeoff` (or `--city <CITY>`) is run —
  `data/models/` is git-ignored, generated data. Until then, the model branch is simply **absent**
  (one logged warning, `model=None`), and the two heuristic branches (`_check_against_forecast`/
  `_check_against_rolling_baseline`) carry G6 alone, exactly as they did before this phase.

## Acceptance Criteria

Adapted from System Design Report §3.3's stated validation plan, annotated with how each is now
evidenced by `docs/data-science/decisions/anomaly_detection_model.md`:

- Injecting corrupted or out-of-range values into weather/operating data streams (e.g. sudden
  temperature spikes, impossible wind speeds) is correctly identified as anomalous. **Evidenced**
  by the record's two labelled injection categories (`out_of_range`, `in_range_implausible`): on
  real held-out data (2026-10-13 per-city refit) the selected `OneClassSVM` model caught 100.00% of
  `out_of_range` and 100.00% of `in_range_implausible` injected rows in each of `AUSTIN`,
  `CORPUS_CHRISTI`, `MIDLAND` and `EL_PASO` (the rolling baseline caught 27.27% and 0.00%
  respectively in every city); the corridor-era models also reached 100.00% on both. Note the
  record's own caveat — `out_of_range` values are already rejected by C7's G3
  range gate upstream in the live pipeline, so `in_range_implausible` (a value each component
  passes G3 with, but whose joint combination is implausible) is the category that actually
  demonstrates this model's unique multivariate contribution.
- Zero false positives on clean historical data. **Not fully met** by the measurement: the selected model's false-positive rate on real, clean,
  held-out data (2026-10-13 per-city refit) was 1.00% (`AUSTIN`), 0.27% (`CORPUS_CHRISTI`), 0.00%
  (`MIDLAND`) and 0.37% (`EL_PASO`) — nonzero in three of the four cities, though every city is at
  or below the configured ceiling (`config.ANOMALY_ML_MAX_FALSE_POSITIVE_RATE`, 5.00%). (The
  corridor-era figures were 3.77% for `AUSTIN_CORPUS_CHRISTI` and 0.53% for `MIDLAND_EL_PASO`.) The record's Verdict
  states this plainly as the real cost of the added caution the model buys, rather than reporting
  a pass this criterion's literal "zero" wording does not support.
- Automatic fallback to SLR is confirmed upon every detected anomaly — this must go through C7's
  existing fallback path, not a separate one. **Evidenced** by
  `backend/tests/anomaly_detector_test.py::test_model_failure_resolves_to_static_rating` and
  `test_model_exception_propagates_out_of_check`, proving a detector exception propagates
  uncaught to `DLRSafetyMonitor`'s existing G6 `except Exception -> _fallback` handler; also
  confirmed by `git diff --quiet HEAD -- backend/DLRSafetyMonitor.py` reporting zero diff across
  this entire phase.

## Open Questions

- ~~Model type~~ — **answered, on measured evidence.** Per
  `docs/data-science/decisions/anomaly_detection_model.md`, `OneClassSVM` was selected over
  `IsolationForest`/`EllipticEnvelope` for both retired corridor models (corridor-era) via a
  three-candidate, five-contamination-point bake-off, and again in each of the four cities in the
  2026-10-13 per-city refit (`OneClassSVM` for `AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND` and
  `EL_PASO`) — see the record's Measured results for every candidate's numbers, losers included.
  The record also notes that `IsolationForest` matches the winner's 100.00% recall on the
  `in_range_implausible` category, so the per-city choice of `OneClassSVM` rests on pooled recall
  driven by the `out_of_range` category that G3 already covers upstream.
- ~~Does this run instead of C7's deterministic gates, alongside them, or only for anomaly types
  the deterministic gates structurally can't catch?~~ — **answered.** Alongside, additively,
  OR-combined (D-05/D-06) — the model branch can only ever add a trip on top of an existing
  branch's verdict, never suppress one. The "plausible-but-wrong-values-within-range" case this
  question raised is precisely what the `in_range_implausible` injection category was built to
  measure, and it is the category on which the deterministic gates structurally have zero recall.
- Training data provenance — **answered by the synthetic-injection strategy this section itself
  proposed**: no labelled real anomaly exists in any project data source, so false-negative/recall
  rate is measured against deliberately injected synthetic corruption on real historical weather,
  exactly as this criterion anticipated. Still genuinely open: whether real, labelled anomalies
  will ever exist once Track 1's live pipeline archive accrues enough history to observe an actual
  sensor fault, which would let a future validation record measure recall without injection.
