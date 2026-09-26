"""
Configuration & Parameterization (C1)
==================================================
This module is C1 per `docs/data-science/specs/C1-configuration.md`.

It centralizes values that were previously hardcoded and duplicated
independently across modules — most notably the "two independent 900.0 A
literals" known issue described in the C1 spec: one in
`backend/dlr_pipeline.py`'s `__main__` block (`static_rating=900.0`) and a
second, wholly independent one in `backend/ercot_dlr_merger.py` (used to
compute `static_capacity_mw`). Because those two literals could be edited
independently, they could silently drift out of agreement with no test or
check to catch it. This module gives every component a single source to
read from instead.

Importing this module has no side effects (no file I/O, no network calls,
no pipeline execution) — it is safe to import without triggering any of
`backend/dlr_pipeline.py`'s `__main__` behavior.
"""

# ──────────────────────────────────────────────────────────────────────────────
# Per-location static line ratings (Amps)
# ──────────────────────────────────────────────────────────────────────────────
# Re-keyed to the four cities in `docs/Project Definition.md`'s I/O
# Specification Table (Austin, Corpus Christi, Midland, El Paso) — the
# project's actual documented/graded scope. This replaces an earlier 5-city
# table (Houston, Austin, Dallas, Fort Worth, San Antonio) that predated this
# decision and only overlapped the real spec on Austin — see
# `docs/data-science/decisions/geographic_scope.md` for the full evidence
# trail and rationale.
#
# Each value is the MIDPOINT of Project Definition.md's documented
# "Worst Case Static Limit (I) [A]" range for that city (lines 79-86 of that
# file) — an honest, clearly-labeled derivation from the team's own graded
# deliverable, NOT an independently sourced single-point citation the way
# e.g. a prior SAN_ANTONIO entry (ERCOT Board Item 11.2) was. If the team
# wants a more precise per-city value later, re-running the kind of
# ERCOT/PUCT/FERC citation research the original 5-city table used — but
# targeted at these four cities — is the natural next step (see
# `geographic_scope.md` Open Questions).
STATIC_RATINGS: dict[str, float] = {
    "AUSTIN": 1900.0,          # midpoint of documented 800-3000 A range
    "CORPUS_CHRISTI": 3000.0,  # midpoint of documented 1000-5000 A range
    "MIDLAND": 1800.0,         # midpoint of documented 600-3000 A range
    "EL_PASO": 1450.0,         # midpoint of documented 600-2300 A range
}

# Fallback static rating (Amps) for any location not present in
# STATIC_RATINGS. Preserves current behavior for stations outside the four
# cities above.
DEFAULT_STATIC_RATING: float = 900.0

# ──────────────────────────────────────────────────────────────────────────────
# Per-location G4 plausibility bounds (Amps)
# ──────────────────────────────────────────────────────────────────────────────
# Each city's documented "Worst Case Static Limit (I) [A]" range from
# `docs/Project Definition.md` (the same source STATIC_RATINGS' midpoints are
# derived from). Per-location, not one widened global band (PD-A3,
# `.planning/phases/03-safety-spatial/03-01-PLAN.md`): a single band spanning
# all four cities (600, 5000) would pass a 4450 A reading for EL_PASO, whose
# own static rating is 1450 A and documented range only extends to 2300 A —
# a 67x-headroom overstatement, exactly the failure DS-NF5 exists to prevent.
RATING_BOUNDS_BY_LOCATION: dict[str, tuple[float, float]] = {
    "AUSTIN": (800.0, 3000.0),
    "CORPUS_CHRISTI": (1000.0, 5000.0),
    "MIDLAND": (600.0, 3000.0),
    "EL_PASO": (600.0, 2300.0),
}

# Fallback plausibility bounds (Amps) for a monitor constructed without a
# location. Matches the pre-existing class-level default so callers that
# don't pass rating_bounds keep their current behavior.
DEFAULT_RATING_BOUNDS: tuple[float, float] = (400.0, 1800.0)

# ──────────────────────────────────────────────────────────────────────────────
# G5 large-swing threshold
# ──────────────────────────────────────────────────────────────────────────────
# Expressed as a fraction of the location's static rating (not a flat Amp
# value) so it scales across the four D-00 cities, whose static ratings span
# 1450-3000 A. At a 1000 A static rating (the existing test fixture's value)
# 0.15 * 1000 = 150.0 A, reproducing the previous flat DELTA_THRESH constant
# exactly. Decided at the 03-01-PLAN.md Task 2 checkpoint (option-a).
DELTA_FRACTION: float = 0.15

# ──────────────────────────────────────────────────────────────────────────────
# Conductor properties
# ──────────────────────────────────────────────────────────────────────────────
# Exact kwargs previously hardcoded in `backend/dlr_pipeline.py`'s __main__
# block for constructing a ConductorConfig. Kept as a plain dict (rather than
# changing ConductorConfig itself) so callers can do:
#     ConductorConfig(**DEFAULT_CONDUCTOR_CONFIG_KWARGS)
DEFAULT_CONDUCTOR_CONFIG_KWARGS: dict = {
    "diameter_m": 0.02814,      # 795 kcmil Drake ACSR
    "resistance_ac": 0.0726,    # Ω/km at 25°C
    "emissivity": 0.8,
    "absorptivity": 0.8,
    "max_temp_c": 75.0,
    "line_azimuth": 90.0,       # set to actual line bearing
    "elevation_m": 900.0,       # West Texas Permian Basin avg elevation
}


def conductor_kwargs_for(line_azimuth: float) -> dict:
    """
    `DEFAULT_CONDUCTOR_CONFIG_KWARGS` with `line_azimuth` overridden to a
    specific corridor's computed bearing. The module-level default of 90.0
    stays as the documented default for callers with no corridor (e.g. this
    module's own DEFAULT_CONDUCTOR_CONFIG_KWARGS, still valid standalone).
    Consumed by Plan 03-02's per-corridor construction, one call per corridor.
    """
    kwargs = dict(DEFAULT_CONDUCTOR_CONFIG_KWARGS)
    kwargs["line_azimuth"] = line_azimuth
    return kwargs

# ──────────────────────────────────────────────────────────────────────────────
# Corridor geographic model (C8, Plan 03-02)
# ──────────────────────────────────────────────────────────────────────────────
# City-center lat/lon for the four D-00 cities, keyed identically to
# STATIC_RATINGS so this dict — together with STATIC_RATINGS and
# RATING_BOUNDS_BY_LOCATION — forms one consistent geographic model (ROADMAP
# Success Criterion 4). 03-RESEARCH.md's Assumptions Log (A2) flagged
# Corpus Christi/Midland/El Paso as LOW-confidence WebSearch values (Austin
# was already CITED via a live API call, see data_provider.md:166). Per
# 03-02-PLAN.md Task 1, all four were re-verified this session (2026-09-03)
# against two live, independently-queried authoritative sources:
#   1. US Census Bureau 2023 Gazetteer Files (Places, Texas) -- the plan's
#      recommended source -- retrieved from
#      https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_gaz_place_48.txt
#      (INTPTLAT/INTPTLONG columns, "<City> city" rows). This matched
#      closely for AUSTIN (30.2986,-97.7541) and MIDLAND (32.0246,
#      -102.1135), confirming methodology, but diverged materially for
#      CORPUS_CHRISTI (27.7543,-97.1734, ~22km east of downtown) and
#      EL_PASO (31.8478,-106.4311, ~10km north of downtown) -- both cities
#      have large, irregularly-shaped incorporated limits (Corpus Christi's
#      city limits include ~329 sq mi of bay/gulf water vs only 162 sq mi
#      of land; El Paso's stretch north into the Franklin Mountains), which
#      skews the Gazetteer's polygon-internal-point algorithm away from the
#      conventional "city center" this project's other 3 corridors imply.
#   2. OpenStreetMap Nominatim administrative-boundary centroid (live query,
#      https://nominatim.openstreetmap.org/search, 2026-09-03), used as the
#      final value below because it agrees with the Census Gazetteer for
#      AUSTIN/MIDLAND (cross-validating both sources) while giving the
#      conventional downtown-centered point for CORPUS_CHRISTI/EL_PASO that
#      D-02's "city-center lat/lon" intent calls for.
# No UNVERIFIED values remain; all four are independently source-cited above.
CITY_COORDINATES: dict[str, tuple[float, float]] = {
    "AUSTIN": (30.2711, -97.7437),          # OSM Nominatim admin centroid, cross-checked vs Census Gazetteer (30.2986,-97.7541)
    "CORPUS_CHRISTI": (27.7635, -97.4033),  # OSM Nominatim admin centroid; Census Gazetteer internal point (27.7543,-97.1734) rejected as bay-skewed
    "MIDLAND": (31.9974, -102.0779),        # OSM Nominatim admin centroid, cross-checked vs Census Gazetteer (32.0246,-102.1135)
    "EL_PASO": (31.7601, -106.4870),        # OSM Nominatim admin centroid; Census Gazetteer internal point (31.8478,-106.4311) rejected as mountain-skewed
}

# The two D-01 corridors: south-central (Austin<->Corpus Christi) and West
# Texas (Midland<->El Paso), chosen over a full 6-pair mesh or a single
# 4-city chain. Values are city *keys* into CITY_COORDINATES/STATIC_RATINGS/
# RATING_BOUNDS_BY_LOCATION, not raw coordinates, so a corridor cannot drift
# out of agreement with those tables. This dict — not the legacy
# station_explorer.CORRIDORS five-point proximity list — is the authoritative
# corridor model per docs/data-science/decisions/geographic_scope.md.
CORRIDOR_ENDPOINTS: dict[str, tuple[str, str]] = {
    "AUSTIN_CORPUS_CHRISTI": ("AUSTIN", "CORPUS_CHRISTI"),
    "MIDLAND_EL_PASO": ("MIDLAND", "EL_PASO"),
}

# ──────────────────────────────────────────────────────────────────────────────
# Analysis window & station source
# ──────────────────────────────────────────────────────────────────────────────
# Today's hardcoded __main__ values from backend/dlr_pipeline.py, moved here
# unchanged.
DEFAULT_STATION_SOURCE: str = "data/wtm_stations_austin.csv"
DEFAULT_START: str = "2025-07-01T00:00:00Z"
DEFAULT_END: str = "2025-07-04T23:55:00Z"

# ──────────────────────────────────────────────────────────────────────────────
# Line electrical parameters
# ──────────────────────────────────────────────────────────────────────────────
# Previously module-level constants at the top of backend/ercot_dlr_merger.py
# (lines 10-11), moved here since centralizing exactly this kind of value is
# C1's job.
LINE_VOLTAGE_KV: float = 345.0  # ERCOT West Texas standard backbone
POWER_FACTOR: float = 0.95      # Standard conservative assumption for grid power

# ──────────────────────────────────────────────────────────────────────────────
# Predictive layer (C9 ampacity forecasting, C10 learned anomaly detection)
# ──────────────────────────────────────────────────────────────────────────────
# Phase 4. Every tunable the forecast/anomaly modules read lives here so
# C1's centralization discipline (this file's own module docstring) extends
# into the two new learned layers, not just the physics/config layer.

# D-01: forecast horizon, 1 hour ahead — matches the pipeline's existing
# hourly analysis cadence and keeps the walk-forward backtest tractable
# against a near-zero starting historical archive.
FORECAST_HORIZON_MINUTES: float = 60.0

# The cold-start floor below which no forecast is emitted at all. Below
# this many archived rows, a fitted band would be confidently wrong rather
# than honestly absent (RESEARCH.md Pitfall 1 — near-zero starting data
# volume). Also doubles as the planner's discretionary backtest window
# floor: 04-RESEARCH.md's Open Questions left the exact window size
# unspecified pending real archive volume.
FORECAST_MIN_HISTORY_ROWS: int = 12

# D-03: empirical residual quantiles for the confidence band — deliberately
# not a mean-plus-k-sigma normal-distribution band, since the residual
# distribution of a naive/EWM forecast on physical ampacity data has no
# guarantee of normality this early.
FORECAST_BACKTEST_QUANTILES: tuple[float, float] = (0.05, 0.95)

# Half-life (minutes) for Plan 04-02's EWM smoothing method. Centralized
# here now, even though Task 2's tracer only implements the "naive"
# method, so config.py is edited once this phase rather than again when
# 04-02 lands.
FORECAST_EWM_HALFLIFE_MIN: float = 180.0

# D-09: append-only CSV, unbounded retention this phase. Path is relative
# to the process working directory, matching DEFAULT_STATION_SOURCE's own
# convention above.
HISTORICAL_ARCHIVE_PATH: str = "data/historical/ampacity_history.csv"

# ──────────────────────────────────────────────────────────────────────────────
# ML forecasting layer (v1.3 Phase 1, "ml" method / FCST-01)
# ──────────────────────────────────────────────────────────────────────────────
# Tunables for the new fitted-model Tier-2 method, mirroring this file's own
# centralization discipline for the predictive layer above.

# Directory for persisted per-corridor model artifacts and the assembled
# training frame that produced them, mirroring DEFAULT_STATION_SOURCE's
# relative-to-cwd convention. Git-ignored (/data/models/), generated data.
FORECAST_ML_MODEL_DIR: str = "data/models"

# {corridor} is formatted in by `ampacity_forecast._model_path_for` after
# `_corridor_of` has already validated it against `CORRIDOR_ENDPOINTS` --
# never a caller-supplied path (T-01-03).
FORECAST_ML_MODEL_FILENAME_TEMPLATE: str = "forecast_{corridor}.joblib"

# The exact real frame that trained a corridor's model, written by
# `forecast_training.main` so the training run can be replayed through
# `forecast_ampacity` (e.g. for the Task 1 E2E verify and the FCST-02
# validation record).
FORECAST_ML_TRAINING_FRAME_TEMPLATE: str = "training_frame_{corridor}.csv"

# D-04's multivariate weather inputs, spelled with the PIPELINE_SCHEMA
# column names already used throughout this file/module.
FORECAST_ML_FEATURE_WEATHER_COLUMNS: tuple[str, ...] = (
    "air_temp", "wind_speed", "solar_radiation",
)

# Lagged dlr_amps offsets (hours) `ampacity_forecast.build_ml_features`
# builds. Deepest lag is 6, so the existing FORECAST_MIN_HISTORY_ROWS (12)
# still suffices for the "ml" method -- a future deepening of this tuple is
# a deliberate change to both constants together, not just this one.
FORECAST_ML_LAG_HOURS: tuple[int, ...] = (1, 2, 3, 6)

# Rolling-mean window (hours) over dlr_amps, shifted by 1 row so the
# current row's own value is excluded (see build_ml_features).
FORECAST_ML_ROLLING_WINDOW_HOURS: int = 6

# Open-Meteo backfill depth per city, in complete calendar years, for
# `forecast_training.fetch_city_weather` (RESEARCH.md Assumption A3's
# 2-5 year band, fixed at 3 for this phase).
FORECAST_ML_TRAINING_YEARS: int = 3

# D-01's evidence-based bake-off (v1.3 Phase 1 Plan 01-02): expanding-window
# fold count for the offline candidate comparison (`forecast_training.
# bakeoff_corridor`). A small fold count rather than per-row retraining --
# refitting a real scikit-learn estimator at every row of a multi-year
# hourly series is the documented cost trap RESEARCH.md Pitfall 1 warns
# about, while a handful of TimeSeriesSplit folds still preserves the same
# "train strictly precedes test" guarantee the walk-forward band relies on.
FORECAST_ML_BAKEOFF_SPLITS: int = 5

# Filename for the bake-off's machine-readable per-corridor comparison
# report, written under FORECAST_ML_MODEL_DIR (git-ignored, generated
# evidence). Plan 01-03 transcribes its numbers into the tracked validation
# record (D-06) -- this JSON file itself is not the artifact of record.
FORECAST_ML_BAKEOFF_REPORT_NAME: str = "bakeoff_report.json"

# D-06: the anomaly control limit is a per-location dict, not one global
# scalar — a single global band is the exact shape of the historical
# RATING_BOUNDS bug documented in
# .planning/phases/03-safety-spatial/03-PATTERNS.md (a band that passed
# for 3 of 4 STATIC_RATINGS). The multiplier is deliberately wide (favors
# fewer false trips over higher sensitivity): per D-06, a learned signal
# that trips too eagerly erodes trust faster than one that occasionally
# misses a subtle anomaly, since G1-G5's deterministic gates already catch
# the clear-cut failure modes. All four values start equal at 4.0 and are
# expected to diverge as each corridor accumulates its own history — it is
# the per-location structure, not these initial numbers, that D-06
# requires.
ANOMALY_CONTROL_LIMIT_K_BY_LOCATION: dict[str, float] = {
    "AUSTIN": 4.0,
    "CORPUS_CHRISTI": 4.0,
    "MIDLAND": 4.0,
    "EL_PASO": 4.0,
}

# Fallback control-limit multiplier for a detector built without a
# location, mirroring how DEFAULT_RATING_BOUNDS backs
# RATING_BOUNDS_BY_LOCATION above.
DEFAULT_ANOMALY_CONTROL_LIMIT_K: float = 4.0

# ──────────────────────────────────────────────────────────────────────────────
# ML anomaly-detection layer (v1.3 Phase 2, additive model branch / ANOM-01)
# ──────────────────────────────────────────────────────────────────────────────
# Tunables for the new fitted-outlier-estimator third branch in
# anomaly_detector.py, mirroring this file's FORECAST_ML_* block structure
# and centralization discipline directly above.

# Directory for persisted per-corridor anomaly model artifacts and the
# observation frame that produced them. Currently resolves to the same
# git-ignored directory as FORECAST_ML_MODEL_DIR, but kept as its own
# constant so the forecasting and anomaly-detection subsystems stay
# independently configurable if their storage needs ever diverge.
ANOMALY_ML_MODEL_DIR: str = "data/models"

# {corridor} is formatted in by `anomaly_detector._model_path_for` only
# after the corridor key has been checked against `CORRIDOR_ENDPOINTS` --
# never a caller-supplied path (T-02-02).
ANOMALY_ML_MODEL_FILENAME_TEMPLATE: str = "anomaly_{corridor}.joblib"

# The exact real pooled observation frame that fitted a corridor's model,
# written by `anomaly_training.main` so a training run can be replayed.
ANOMALY_ML_OBSERVATION_FRAME_TEMPLATE: str = "anomaly_observations_{corridor}.csv"

# D-01's raw per-variable inputs, spelled with the PIPELINE_SCHEMA/
# Open-Meteo column names -- the training-time column names the estimator
# is fitted on, in fit order.
ANOMALY_ML_FEATURE_COLUMNS: tuple[str, ...] = (
    "air_temp", "wind_speed", "solar_radiation",
)

# The `raw_data` key at the same tuple position as the training column
# above it -- the positional correspondence between this tuple and
# ANOMALY_ML_FEATURE_COLUMNS is the entire mapping from a live reading to
# a feature vector (a test asserts their lengths match). No time-of-day
# and no load feature appears in either tuple: `raw_data` carries neither
# a timestamp nor a load value at the `check()` call site, and adding
# either is Track 1's scope, not this phase's (D-01, D-02).
ANOMALY_ML_RAW_DATA_KEYS: tuple[str, ...] = ("temp", "wind", "solar")

# Open-Meteo backfill depth per endpoint city, in complete calendar years,
# matching FORECAST_ML_TRAINING_YEARS.
ANOMALY_ML_TRAINING_YEARS: int = 3

# D-03/D-04: an untuned starting value -- Plan 02-02 replaces this with a
# value selected from measured false-positive evidence against real clean
# historical data (see docs/data-science/decisions/ once that record
# exists). Passed explicitly to IsolationForest rather than left at the
# estimator's own automatic offset heuristic, so this tracer path has one
# explicit, inspectable number rather than a hidden default.
ANOMALY_ML_CONTAMINATION: float = 0.01

# Matches forecast_training.py's fixed-seed reproducibility convention.
ANOMALY_ML_RANDOM_SEED: int = 20260924

# ──────────────────────────────────────────────────────────────────────────────
# ASOS 1-minute network station IDs (Phase 7, C4)
# ──────────────────────────────────────────────────────────────────────────────
# IEM ASOS network 3-letter FAA identifiers -- NOT the 4-letter ICAO codes
# used elsewhere in this project's docs (data_provider.md, 07-CONTEXT.md).
# Live-confirmed via https://mesonet.agron.iastate.edu/geojson/network/TX_ASOS.geojson
# and direct CGI requests this session (07-RESEARCH.md Pitfall 1) -- a 4-letter
# code fails with "Unknown station provided".
ASOS_STATIONS: dict[str, str] = {
    "AUSTIN": "AUS",
    "CORPUS_CHRISTI": "CRP",
    "MIDLAND": "MAF",
    "EL_PASO": "ELP",
}

# ──────────────────────────────────────────────────────────────────────────────
# TCEQ CAMS site IDs (Phase 9, C4 / WX-01)
# ──────────────────────────────────────────────────────────────────────────────
# Selected on wind/temp/RH completeness alone (D-01/D-02) -- NOT proximity to a
# corridor endpoint and NOT solar availability. Each site was confirmed by a
# raw fetch of monitors.pl?region=<n> and daily_summary.pl?cams=<id> during
# Phase 9 research (09-RESEARCH.md "CAMS Site Selection"). Values are strings
# to match daily_summary.pl's `cams=<id>` query parameter, mirroring
# ASOS_STATIONS' own dict[str, str] shape.
TCEQ_STATIONS: dict[str, str] = {
    "AUSTIN": "38",           # Audubon C38 -- WS+WD(true)+Temp confirmed; NO Relative Humidity row
    "CORPUS_CHRISTI": "83",   # Corpus Christi Palm C83 -- WS+WD+Temp+RH all live-confirmed
    "MIDLAND": "1095",        # Midland Avalon Drive C1095 -- WS+WD(true)+Temp confirmed; NO Relative Humidity row
    "EL_PASO": "41",          # Chamizal C41 -- WS+WD+Temp+RH all live-confirmed
}

# ──────────────────────────────────────────────────────────────────────────────
# Synoptic fallback station IDs (Phase 10, C4 / WX-06)
# ──────────────────────────────────────────────────────────────────────────────
# These are 4-letter ICAO identifiers -- deliberately NOT the 3-letter FAA
# codes ASOS_STATIONS uses for the IEM network. Only KAUS has been confirmed
# to return observation rows under this project's Synoptic token (per
# `docs/data-science/specs/C4-weather-ingestion.md`'s live-verification
# note); the other three are unconfirmed until Plan 10-03's live check. This
# table is the fallback target only -- it does not change
# DEFAULT_STATION_SOURCE or any primary path.
SYNOPTIC_FALLBACK_STATIONS: dict[str, str] = {
    "AUSTIN": "KAUS",
    "CORPUS_CHRISTI": "KCRP",
    "MIDLAND": "KMAF",
    "EL_PASO": "KELP",
}
