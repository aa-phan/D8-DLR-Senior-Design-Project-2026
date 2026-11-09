# Phase 7: Per-City Conductors, Shadow Refit and Early Model Selection - Pattern Map

**Mapped:** 2026-10-25
**Files analyzed:** 21 (10 new, 11 modified)
**Analogs found:** 19 / 21 (all analog paths verified git-tracked via `git ls-files`; all under `backend/`)

All line numbers are at HEAD (`4966948`, code unchanged since `d71c501`).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `backend/config.py` (+`PRODUCTION_CONDUCTORS`, `PRODUCTION_CONDUCTOR_SOURCES`, `production_conductor_kwargs_for`) | config | transform | `config.py:140-161` (`DEFAULT_CONDUCTOR_CONFIG_KWARGS`, `conductor_kwargs_for`) + `config.py:566-571` (`ANOMALY_CONTROL_LIMIT_K_BY_LOCATION`) | exact |
| `backend/city_point.py` (+`production_city_point`) | service/resolver | request-response | `city_point.py:45-69` `city_point()` | exact |
| `backend/rating_identity.py` (snapshot uses resolver via getattr) | utility | transform | itself, `rating_identity.py:116-136` | exact |
| `backend/city_rating.py`, `anomaly_training.py`, `forecast_training.py`, `real_data_validation.py` (repoint resolver) | service | batch | existing `city_point.city_point` call sites (`forecast_training.py:~200`) | exact |
| `backend/forecast_training.py` `city_training_frame` (B2 one-line change) | service | batch | itself, `forecast_training.py:~200-226` | exact |
| `backend/city_pipeline.py` (B5 naive-band fallback, `g6_forecast_method`) | service | request-response | itself, `city_pipeline.py:120-160` | exact |
| `backend/forecast_shadow_eval_core.py` (round registry) + `forecast_shadow_confirm.py` (`--round`) | config/guard | request-response | `eval_core.py:65-73`, `check_guard` `:397-424` | exact (v4-authorised edit only, after signing) |
| `backend/forecast_shadow_decision_v4.py` (NEW) | utility | transform | `backend/forecast_shadow_decision.py` | exact |
| `backend/forecast_conductor_refit.py` (NEW) | service | batch/file-I/O | `backend/forecast_shadow_fit_models.py` | role+flow match |
| `backend/forecast_conductor_ablation.py` (NEW) | service | batch | `forecast_shadow_fit_models.py` (`load_city_frame`, `restrict_to_train_val`) | role-match |
| `backend/forecast_test_split_score.py` (NEW) | service | batch | `forecast_shadow_confirm.py` (`run_confirmation` with injected provider/loader) | role-match |
| `backend/tests/production_conductor_test.py` (NEW) | test | unit | `backend/tests/rating_identity_test.py` | role-match |
| `backend/tests/cond02_shadow_golden_test.py` + `fixtures/golden_shadow_baseline_d71c501.json` (NEW) | test | golden | `backend/tests/forecast_training_test.py:94-135` (npz golden) | exact pattern |
| `backend/tests/forecast_shadow_decision_v4_test.py` (NEW) | test | unit | `backend/tests/forecast_shadow_decision_test.py` | exact |
| `backend/tests/forecast_conductor_refit_test.py`, `..._ablation_test.py`, `forecast_test_split_score_test.py` (NEW) | test | unit | `forecast_shadow_eval_validation_test.py` (dev-fixture provider) | role-match |
| `backend/tests/rating_identity_test.py`, `city_rating_test.py` (modify fixtures) | test | unit | themselves | exact |
| `data/models/conductor_refit/<ver>/` + manifest | artifact | file-I/O | `data/models/LIVE_ARTIFACT_HASHES.sha256` via `dlr_live_check_models.py` | exact |
| `docs/data-science/decisions/confirmation_protocol_v4_*.md` (NEW) | doc | n/a | `docs/data-science/decisions/confirmation_protocol_v3_per_city.md` | exact |
| `docs/data-science/schema/city_rating_v1.md` | doc | n/a | itself (test-coupled to `RATING_BASIS`) | exact |
| ROADMAP SC3/SC5, REQUIREMENTS SEL-04, ml-modeling STATE.md | doc | n/a | n/a | no analog (text edits) |

## Pattern Assignments

### `backend/config.py` per-city conductor table (config, transform)

**Analog:** `config.py:140-161` and `:566-571`.

Start values (D-09) are the Drake dict plus `CITY_LINE_BEARING_DEG` (`config.py:216-221`). Do NOT edit `DEFAULT_CONDUCTOR_CONFIG_KWARGS` or `conductor_kwargs_for`.

```python
DEFAULT_CONDUCTOR_CONFIG_KWARGS: dict = {
    "diameter_m": 0.02814, "resistance_ac": 0.0726, "emissivity": 0.8, "absorptivity": 0.8,
    "max_temp_c": 75.0, "line_azimuth": 90.0, "elevation_m": 900.0,
}
def conductor_kwargs_for(line_azimuth: float) -> dict:
    kwargs = dict(DEFAULT_CONDUCTOR_CONFIG_KWARGS)
    kwargs["line_azimuth"] = line_azimuth
    return kwargs
```
Strict per-city dict convention ("Every key in LOCATIONS must appear here -- a test asserts it"):
```python
ANOMALY_CONTROL_LIMIT_K_BY_LOCATION: dict[str, float] = {
    "AUSTIN": 4.0, "CORPUS_CHRISTI": 4.0, "MIDLAND": 4.0, "EL_PASO": 4.0,
}
```
Add `PRODUCTION_CONDUCTORS` (per city incl. `conductor_type`), a parallel `PRODUCTION_CONDUCTOR_SOURCES` (non-empty string per value: "current model default, provisional; Power Systems pending"), and `production_conductor_kwargs_for(city)` (KeyError naming valid cities; drops `conductor_type`; numeric range checks). Bump `RATING_CONFIG_VERSION` in the same change.

---

### `backend/city_point.py` `production_city_point` (resolver, request-response)

**Analog:** `city_point.py:45-69`. Keep `city_point()` byte-unchanged; the resolver lives in this module (no new module, Phase 3 identity child constraint).

```python
def city_point(city: str) -> CityPoint:
    if city not in config.LOCATIONS:
        raise KeyError(f"Unknown city {city!r}. Valid cities: {sorted(config.LOCATIONS)}")
    bearing_deg = config.CITY_LINE_BEARING_DEG[city]
    conductor = thermal_model.ConductorConfig(**config.conductor_kwargs_for(bearing_deg))
    return CityPoint(name=city, coord=config.CITY_COORDINATES[city], bearing_deg=bearing_deg,
        conductor=conductor, static_rating=config.STATIC_RATINGS[city],
        rating_bounds=config.RATING_BOUNDS_BY_LOCATION[city])
```
New function: same shape, but `kwargs = config.production_conductor_kwargs_for(city)`, `bearing_deg=kwargs["line_azimuth"]`.

---

### `backend/rating_identity.py` (utility, transform)

**Analog:** itself, `rating_identity.py:116-136`. Only change `point = city_point.city_point(city)` to a defensive resolve; do not add imports (test pins imports to `{"json","hashlib","config","city_point"}` at `supabase_load_backfill_test.py:617-628`).

```python
resolve = getattr(city_point, "production_city_point", city_point.city_point)
point = resolve(city)
...
"config": {name: _per_city(getattr(config, name, None), city) for name in FINGERPRINTED_CONFIG_NAMES},
```
Classify new names in `FINGERPRINTED_CONFIG_NAMES` (`PRODUCTION_CONDUCTORS`) or `UNFINGERPRINTED_CONFIG_NAMES` with a reason (`PRODUCTION_CONDUCTOR_SOURCES`, `production_conductor_kwargs_for`), or the AST guard test fails.

---

### Production caller repoints (service, batch)

**Analog:** current call sites. Repoint `city_point.city_point` to `city_point.production_city_point` in `city_rating.py:~377`, `anomaly_training.py:~566`, `forecast_training.py:~200`, `real_data_validation.py:310,373,490`. Leave `dlr_orchestrator.py:95`, shadow modules and `legacy_corridor.py` on `city_point.city_point`.

### B2: `forecast_training.city_training_frame` (service, batch)

**Analog:** `forecast_training.py:204-226`. `perp` is already computed; change only the stored feature.
```python
perp = thermal_model.perpendicular_wind(weather["wind_speed"].to_numpy(dtype=float),
    weather["wind_direction"].to_numpy(dtype=float), point.bearing_deg)
...
"wind_speed": weather["wind_speed"].to_numpy(dtype=float),   # -> np.asarray(perp, dtype=float)
```
Do not touch `build_training_matrix` or `build_ml_features` (shadow reference candidate uses them). Archive `data/models/forecast_*.joblib` before retrain; promote via `dlr_live_check_models.py --write-manifest`.

### B5: `backend/city_pipeline.py` (service, request-response)

**Analog:** `city_pipeline.py:120-160` (existing gap guard).
```python
gap_reason = None
if forecast is not None and cleaned is not None:
    gap_reason = data_cleaning.forecast_gap_reason(cleaned.report, forecast_method)
if forecast_degenerate:
    forecast_for_detector = None
elif gap_reason:
    log.info("%s: forecast not used for G6 this run -- %s", city, gap_reason)
    forecast_for_detector = None
else:
    forecast_for_detector = forecast
```
Extend the `elif gap_reason` branch: if the reason is the ml lookback one (not the trailing-gap one), compute `ampacity_forecast.forecast_ampacity(history, method="naive")`, apply the same degenerate-band guard, and pass that to `AnomalyDetector.for_city`. Add `"g6_forecast_method": "ml"|"naive"|None` into `result["pipeline"]` next to `forecast_used_by_g6` (line ~157). Do not reuse `forecast_method`/`forecast_used_by_g6` (they map to DB columns). Also carry key through `backfill_archive._trace_records` and `real_data_validation._PASS_THROUGH_NAMES` (~line 275).

### `forecast_shadow_decision_v4.py` (utility, transform)

**Analog:** `forecast_shadow_decision.py` (leave the v3 module intact). Copy `_entry`, `evidence_level`, `_row_sources`, and the mixed-row-source refusal from `apply_ship_rule`:
```python
levels = {c: evidence_level(_entry(family_report, c, core.FALLBACK_CHOICE), margin) for c in core.REAL_CANDIDATES}
...
qualifies = bool(possible and not insufficient and over is not None and over >= margin and len(favoring) >= min_cities)
```
Changes for v4: margin becomes per-city `0.02 * mean_truth_amps` (add `mean_truth_amps` to the report; pre-register pooled vs per-city formula), 3-of-4 by point estimate (D-04), no-pick when none qualifies instead of falling back to raw/wind (D-07), re-test rule (D-08). Keep the three evidence levels and 9-test Holm family.

### `forecast_conductor_refit.py` (service, batch/file-I/O)

**Analog:** `forecast_shadow_fit_models.py:85-135, 152-200`. Reuse imports as-is:
```python
import city_point, config, forecast_correction_models, forecast_experiment,
       forecast_experiment_audit, forecast_shadow_pipeline, forecast_training, thermal_model
```
Copy `assert_no_test_leak` / `restrict_to_train_val` calls (reuse, do not re-implement), and the `weather_to_arm5_frame` shape (`:91-110`) but take a `point` argument instead of `city_point.city_point(city)`:
```python
perp = thermal_model.perpendicular_wind(wind, truth[f"{prefix}wind_direction"].to_numpy(dtype=float), point.bearing_deg)
dlr_amps = np.asarray(thermal_model.ieee738_ampacity(air, perp, solar, point.conductor), dtype=float)
```
Reference model: `forecast_training.build_training_matrix(frame, horizon_minutes=1440)` + `fit_model(X, y, CANDIDATE_ESTIMATORS["MLPRegressor"]())`. Output to `data/models/conductor_refit/<config_version>/` with a sha256sum-format manifest; never `forecast_shadow_pipeline.save_correction_model` (targets `data/shadow/models`). Verify hash before `joblib.load`.

### Manifest handling (file-I/O)

**Analog:** `dlr_live_check_models.py` (`sha256_file` :76, `read_manifest` :84, `check` :106, `write_manifest` :162). Manifest line format: `f"{sha256_file(path)}  {_key(path)}"`. Reuse these helpers; same sha256sum format.

### `forecast_shadow_eval_core.py` round registry (config/guard)

**Analog:** `forecast_shadow_eval_core.py:65-73` and `check_guard` `:397-424`; add a frozen `ProtocolRound` dataclass (see RESEARCH.md "Round registry" code). Preserve `if now_ts < instant and override is None` and `if prior and override is None`. Merge only after v4 is signed.

### `forecast_test_split_score.py` / `forecast_conductor_ablation.py` (service, batch)

**Analog:** `forecast_shadow_confirm.run_confirmation(frame_provider=, model_loader=, window=)` with an injected provider. Use `forecast_shadow_pipeline.load_correction_model` as explicit `model_loader`. Cached frames: `data/experiment/anchored_pair_frame_{CITY}_2024-01-20_2026-09-29_lead24_previous_runs.csv` (git-ignored; never open the `_2026-09-30_` files). TEST starts at 2026-03-18T00Z. ABLATION fits on train only (up to 2025-09-01T18Z) and asserts 784 validation rows per city. Stats: `forecast_shadow_score_stats.build_family_report`, `per_city_comparison`.

---

### Tests

**`production_conductor_test.py`** — analog `rating_identity_test.py:97-145`. Existing pattern patches the Drake resolver:
```python
def _patch_austin_conductor(monkeypatch, **changes):
    real = city_point.city_point
    def patched(city):
        point = real(city)
        if city == "AUSTIN":
            kwargs = config.conductor_kwargs_for(config.CITY_LINE_BEARING_DEG[city]); kwargs.update(changes)
            point.conductor = thermal_model.ConductorConfig(**kwargs)
        return point
    monkeypatch.setattr(city_point, "city_point", patched)
```
Update to patch `production_city_point` (and `config.PRODUCTION_CONDUCTORS`); extend `_CASES` (`:138`). Add completeness test (every `config.LOCATIONS` city has table + non-empty sources), `test_provisional_parity`, `test_caller_split` (AST).

**`city_rating_test.py:37-46` `synthetic_city`** must add:
`monkeypatch.setitem(config.PRODUCTION_CONDUCTORS, _TEST_CITY, {...})` and a sources entry.

**`cond02_shadow_golden_test.py`** — analog `forecast_training_test.py:94-135` (exact `np.array_equal` against a capture from unmodified source):
```python
g = np.load(path, allow_pickle=True)
assert np.array_equal(X.to_numpy(dtype=float), g["X_values"]), "...not bit-identical to the pre-edit golden capture"
```
Plan: capture JSON at `d71c501` as the FIRST commit, fixture `backend/tests/fixtures/shadow_eval_frozen_dev_frames.csv.gz` (sha256 `a397c82d...6250`), plus `shasum -c data/shadow/models/ARTIFACT_HASHES.sha256` and a `git diff --name-only` guard on frozen files.

**`forecast_shadow_decision_v4_test.py`** — analog `forecast_shadow_decision_test.py:1-40`: synthetic family-report builders `entry(a, b, margin, ...)` and `family(overrides)` using `core.HEADLINE_FAMILY`; no statistics run.

## Shared Patterns

### Shadow isolation (COND-02)
**Apply to:** every new/modified module. Shadow modules (`forecast_shadow_pipeline.py`, `forecast_shadow_fit_models.py`, `forecast_shadow_fit_reference_refit.py`, `forecast_shadow_confirm.py`, `forecast_shadow_demo.py`, `legacy_corridor.py`) keep `city_point.city_point`. New modules wrap frozen helpers rather than adding parameters to them.

### Test-leak guard
**Source:** `forecast_shadow_fit_models.py:122-130`
```python
split = pd.Timestamp(forecast_experiment_audit.FROZEN_TEST_SPLIT_START, tz="UTC")
for col in ("datetime_utc", "anchor_datetime_utc"):
    if col in frame.columns and len(frame):
        latest = pd.to_datetime(frame[col], utc=True).max()
        assert latest < split, ...
```
**Apply to:** refit, ABLATION drivers.

### Anti-peeking
Use round registry, never `--override-reason` (override disables both pre-instant and one-shot refusals). No FRESH scoring before the instant; `--dry-run` only.

### Strict closed-set lookup
**Source:** `city_point.py:60-63` KeyError naming sorted valid cities. **Apply to:** `production_conductor_kwargs_for`, `production_city_point`.

### Artifact integrity
Verify sha256 against manifest before `joblib.load`. **Source:** `dlr_live_check_models.check` (`:106-160`).

## No Analog Found

| File | Role | Reason |
|---|---|---|
| v4 text content (ABLATION invariance, TEST veto, "qualifies") | doc | Owner-signed; v3 doc is structural analog only |
| ROADMAP / REQUIREMENTS / ml-modeling STATE wording edits | doc | Prose edits (D-08, D-10) |
| Label-lift mechanism on stored rows (Open Question 2) | data change | No prior precedent; owner-run UPDATE |

## Metadata

**Analog search scope:** `backend/` (modules and tests), `config.py`, `data/models`
**Files read:** city_point.py, config.py (excerpts), forecast_shadow_decision.py, forecast_shadow_fit_models.py, rating_identity.py, forecast_training.py, city_pipeline.py, dlr_live_check_models.py, test files (excerpts)
**Pattern extraction date:** 2026-10-25
**Note:** Only `shadow_eval_frozen_dev_frames.csv.gz` exists in `backend/tests/fixtures` as tracked; the golden JSON fixture is genuinely new.
