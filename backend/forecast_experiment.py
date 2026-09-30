"""
Ampacity Forecast Experiment Harness -- Anchored Pair Frame + Arm Scoring
(D-01 legacy 1h arm + D-04 PRIMARY 24h arm, Phase 3 experiment)
==========================================================================
Standalone offline entry point -- NOT imported by the runtime pipeline,
mirroring `forecast_training.py`/`anomaly_training.py`'s own convention.
Imports `ampacity_forecast`, `config`, `corridor_discretization`,
`experiment_splits`, `open_meteo_forecast_provider`, `open_meteo_provider`,
`thermal_model`; nothing imports this module.

THE ANCHORED-PAIR-FRAME CONTRACT (this plan's central invariant, inherited
by every later plan in this phase, now GENERALIZED by a `lead_hours`
parameter -- Plan 03-03, D-04's replan). One row per scored valid time `T`
where `T.hour % config.FORECAST_EXPERIMENT_LEAD_FILTER_MODULUS == r`,
carrying three time-distinct column groups, ALL assembled from the FULL
unfiltered hourly truth series BEFORE the `hour % modulus == r` filter is
applied:

    Group      Time              Source
    ---------  ----------------  ---------------------------------------------
    anchor_*   T - lead_hours    Archive API truth (the last observation a
                                 forecaster would actually have had)
    truth_*    T                 Archive API truth (what actually happened)
    fcst_*     T (issued at      Historical Forecast API (lead_hours=1,
               T - lead_hours)   models=ecmwf_ifs) or Previous Runs API
                                 (lead_hours=24, models=gfs_seamless)
    fcst_anchor_*  T - lead_hours  The FORECAST series' own value at the
                                 anchor time (Plan 03-04's wind-delta arm
                                 needs the forecast's change between anchor
                                 and valid time)

`r` is the remainder `lead_hours` claims on the six-hourly modulus:
`config.FORECAST_EXPERIMENT_LEAD_FILTER_REMAINDER` (= 1) for the LEGACY
1-hour arm, `config.FORECAST_EXPERIMENT_24H_LEAD_FILTER_REMAINDER` (= 0)
for D-04's PRIMARY 24-hour arm. The `hour % modulus == r` filter selects
WHICH ROWS ARE SCORED. It is NEVER the source of a lagged value. This is
the single most important invariant in the phase, LEAD-INDEPENDENT: filtered
rows are six hours apart at EITHER lead, so a persistence baseline computed
from them would be a six-hour-stale predictor at the 1-hour lead and a
THIRTY-hour-stale one at the 24-hour lead -- every forecast arm would beat
it and the phase would publish a falsely positive result. `anchored_pair_
frame` builds the anchor group by shifting the FULL, unfiltered hourly
truth series forward by exactly `lead_hours` -- never from the filtered
subset -- and `assert_exact_lead` is the automated gate that catches a
violation of this invariant before any scoring pass runs.

D-04's `previous_day1` effective lead is `24 + (T.hour % 6)` hours -- exactly
24.0h ONLY when `T.hour % 6 == 0` (03-RESEARCH.md Pattern 2,
`forecast_leadtime_calibration.assert_exact_offset_lead`'s live-verified
measurement). The remainder-0 filter is what makes the 24.0-hour claim
TRUE for the scored rows; it is not automatic just because Open-Meteo's
docs (or D-04's own original `03-CONTEXT.md` text) describe the endpoint as
an exact-by-construction 24-hour lead.

Two caveat constants, one per lead, NEVER interchanged:
`EXPERIMENT_LEAD_REALIZABILITY_CAVEAT` (03-RESEARCH.md Pitfall 6, legacy
1-hour arm) and `PRIMARY_24H_LEAD_CAVEAT` (D-04, primary 24-hour arm). Each
is emitted on every output surface -- the JSON report and the printed
`SUMMARY:` line -- attached to its own lead's arms only, so a reader can
never see a score without seeing the qualifier that matches its own lead.

LEAD-TO-SOURCE MAPPING: `_lead_source_config(lead_hours)` is the single
module-level table mapping a `lead_hours` value to its
(fetch function, filter remainder, default window start, caveat) --
implemented as a lookup, not an inline branch, so the four lead-coupled
facts can never be set inconsistently with each other, and adding a future
lead is a table entry, not a cross-module search-and-replace.

Window note (Plan 03-01, corrected twice; Plan 03-03 added the 24h-primary
window -- see `config.py`'s `FORECAST_EXPERIMENT_WINDOW_START`/
`FORECAST_EXPERIMENT_PREVIOUS_RUNS_WINDOW_START` for the full history): the
bulk/single-run bit-identical lead rule the legacy arm depends on does not
hold before `config.FORECAST_EXPERIMENT_WINDOW_START`; the 24-hour offset
rule is only exact from `config.FORECAST_EXPERIMENT_PREVIOUS_RUNS_WINDOW_
START` onward. This module does not itself re-verify either rule --
`forecast_leadtime_calibration.py` is the gate for both -- but each lead
defaults to its OWN corrected window so a caller who doesn't override
`--start`/`--end` cannot accidentally score outside the window the rule has
actually been verified on.

TEST-SPLIT LOCK (Success Criterion 5's no-peeking discipline): a
module-level `_TEST_SPLIT_UNLOCKED` flag defaults to `False`.
`_guard_test_split_access` raises if any code path attempts to score the
held-out TEST split while it is locked. Plan 03-06 flips the flag in the
same commit that lands the Expectation record -- this plan's own `main`
never requests the test split, scoring the VALIDATION split only.
"""

import argparse
import dataclasses
import json
import logging
import os

import numpy as np
import pandas as pd

import ampacity_forecast
import config
import corridor_discretization
import experiment_splits
import open_meteo_forecast_provider
import open_meteo_provider
import thermal_model

logger = logging.getLogger(__name__)

# Success Criterion 5's no-peeking discipline, mechanically enforced (a
# comment asking a future executor not to peek is not enforcement). Plan
# 03-06 flips this in the SAME commit that lands the Expectation record --
# this module's own `main` never requests the test split while this plan
# is executing.
_TEST_SPLIT_UNLOCKED: bool = False

# 03-RESEARCH.md Pitfall 6: global NWP models are typically available
# several hours after their nominal initialization, and no Open-Meteo
# product offers a run cadence finer than six-hourly in the archive -- so
# no live system could ever have disseminated a forecast at a genuine
# one-hour lead. This constant is emitted on every output surface (the
# JSON report and the printed SUMMARY: line) so a reader can never see a
# score without seeing this qualifier alongside it. A NEGATIVE result
# under this idealized latency is still decisive: it cannot improve with
# real (worse) latency. The question this experiment answers is "given a
# perfect-latency NWP at a one-hour lead, does physics-plus-correction
# beat persistence" -- not "can we forecast sixty minutes ahead."
EXPERIMENT_LEAD_REALIZABILITY_CAVEAT: str = (
    "IDEALIZED LATENCY: the one-hour-lead arms in this report assume the "
    "forecast was available at exactly T-1h. Real NWP dissemination "
    "latency for global models is several hours, and no Open-Meteo "
    "product offers a run cadence finer than six-hourly in the archive -- "
    "no live system could have had this forecast at this lead. This "
    "report answers 'given a perfect-latency NWP at a one-hour lead, does "
    "physics-plus-correction beat persistence', not 'can we forecast "
    "sixty minutes ahead'. "
    "SECOND, STRONGER CAVEAT (live-discovered, Plan 03-01, 2026-09-29): "
    "at this lead, Open-Meteo's bulk historical-forecast-api response is "
    "empirically BIT-IDENTICAL to archive-api's reanalysis 'truth' for "
    "every hour tested, across all four project cities and the full "
    "corrected window -- not merely close. A raw_forecast MAE near zero "
    "in this report therefore does not demonstrate that a 1-hour-lead "
    "NWP forecast is an accurate PREDICTOR of the future; it demonstrates "
    "that, in this data source, the 'forecast' at this lead already IS "
    "the eventual observation, so this arm is not yet exercising genuine "
    "forecast skill. See 03-01-SUMMARY.md for the full evidence and its "
    "implications for later plans in this phase."
)

# D-04's PRIMARY 24-hour-lead caveat -- a SEPARATE constant from
# EXPERIMENT_LEAD_REALIZABILITY_CAVEAT above, never interchanged with it.
# Every 24-hour score on every output surface (the JSON report and the
# printed SUMMARY: line) carries THIS caveat, never the legacy one, and
# vice versa -- T-03-03-05 (a 24-hour score published without its lead
# qualifier is a Repudiation threat this module closes by construction).
PRIMARY_24H_LEAD_CAVEAT: str = (
    "PRIMARY 24-HOUR LEAD (D-04): this lead is exactly 24.0 hours ONLY "
    "because the scored rows are filtered to the six-hourly cycle hours "
    "(hour % 6 == 0) -- verified against the Single-Runs product "
    "(forecast_leadtime_calibration.assert_exact_offset_lead), NOT taken "
    "from Open-Meteo's or D-04's own 'exact by construction, no "
    "calibration gate needed' framing, which is contradicted by direct "
    "measurement for the other 5 of every 6 hours (25-29h lead). "
    "A 24-hour persistence baseline is DIURNALLY SELF-ALIGNED and is "
    "therefore a genuinely STRONG day-ago-same-hour baseline, not the weak "
    "one a 'longer horizon is easier to beat' intuition would suggest "
    "(03-RESEARCH.md Pattern 4) -- do not expect the correction arms to "
    "beat it as easily as that intuition implies. This is the phase's "
    "PRIMARY comparison (D-04); the 1-hour arm is a labelled non-primary "
    "curiosity whose raw-forecast score is an artifact of a bit-identical "
    "data source, never a competing candidate against this arm's result."
)


@dataclasses.dataclass(frozen=True)
class _LeadSourceConfig:
    """
    The four lead-coupled facts for one `lead_hours` value, bundled so they
    can never be set inconsistently with each other (this module's
    docstring, "LEAD-TO-SOURCE MAPPING").
    """

    fetch_fn_name: str  # attribute name on open_meteo_forecast_provider, looked up at call time so monkeypatch (tests) is honored
    filter_remainder: int
    default_window_start: str
    caveat: str
    source_name: str  # for the cache filename and the report/arm naming


def _lead_source_config(lead_hours: int) -> _LeadSourceConfig:
    """
    The single module-level table mapping `lead_hours` to its
    (fetch function, filter remainder, default window start, caveat)
    record. A lookup, not an inline branch -- adding a future lead is a
    table entry, and the four lead-coupled facts can never be set
    inconsistently with each other.

    Raises:
        ValueError: naming `lead_hours` and the supported values, for any
            lead this table does not know about.
    """
    if lead_hours == 1:
        return _LeadSourceConfig(
            fetch_fn_name="fetch_historical_forecast",
            filter_remainder=config.FORECAST_EXPERIMENT_LEAD_FILTER_REMAINDER,
            default_window_start=config.FORECAST_EXPERIMENT_WINDOW_START,
            caveat=EXPERIMENT_LEAD_REALIZABILITY_CAVEAT,
            source_name="historical_forecast",
        )
    if lead_hours == config.FORECAST_EXPERIMENT_PRIMARY_LEAD_HOURS:
        return _LeadSourceConfig(
            fetch_fn_name="fetch_previous_runs",
            filter_remainder=config.FORECAST_EXPERIMENT_24H_LEAD_FILTER_REMAINDER,
            default_window_start=config.FORECAST_EXPERIMENT_PREVIOUS_RUNS_WINDOW_START,
            caveat=PRIMARY_24H_LEAD_CAVEAT,
            source_name="previous_runs",
        )
    raise ValueError(
        f"forecast_experiment: no lead-source mapping for lead_hours={lead_hours!r} "
        f"-- supported: 1 (legacy 1h arm), "
        f"{config.FORECAST_EXPERIMENT_PRIMARY_LEAD_HOURS} (D-04 primary arm)"
    )


def _guard_test_split_access(split_name: str) -> None:
    """
    Raise if `split_name` names the held-out TEST split while
    `_TEST_SPLIT_UNLOCKED` is `False` -- the mechanical enforcement of
    Success Criterion 5's no-peeking discipline. Plan 03-06 flips the
    module-level flag in the same commit that lands the Expectation record.
    """
    if split_name == "test" and not _TEST_SPLIT_UNLOCKED:
        raise RuntimeError(
            "forecast_experiment: refusing to score the held-out TEST "
            "split -- _TEST_SPLIT_UNLOCKED is False. Plan 03-06 unlocks "
            "this in the same commit that lands the Expectation record "
            "(Success Criterion 5's no-peeking discipline)."
        )


def _corridor_for_city(city: str) -> str:
    """
    Reverse-lookup: the one corridor in `config.CORRIDOR_ENDPOINTS` whose
    endpoints include `city`. Task 3 scores at CITY level, but
    `thermal_model.ieee738_ampacity` needs a per-corridor `ConductorConfig`
    and bearing (`corridor_discretization.corridor_geometry`) -- the
    conductor config is per-corridor even though this module scores one
    city at a time (03-01-PLAN.md Task 3 read_first).

    Raises:
        ValueError: naming `city` and the valid cities, if `city` is not
            an endpoint of any corridor.
    """
    for corridor, (city_a, city_b) in config.CORRIDOR_ENDPOINTS.items():
        if city in (city_a, city_b):
            return corridor
    valid = sorted({c for pair in config.CORRIDOR_ENDPOINTS.values() for c in pair})
    raise ValueError(
        f"forecast_experiment: {city!r} is not an endpoint of any corridor "
        f"in config.CORRIDOR_ENDPOINTS; valid cities: {valid}"
    )


def _resolve_window_end(end) -> str:
    """
    Resolve `config.FORECAST_EXPERIMENT_WINDOW_END`'s `None` sentinel (or
    any `None` passed by a caller) to "yesterday" (UTC) -- the archive
    needs the day to be fully past, mirroring `forecast_leadtime_
    calibration.py`'s own `_stratified_sample_days` end-of-range
    convention. A non-`None` value passes through unchanged.
    """
    if end is not None:
        return end
    yesterday = pd.Timestamp.now(tz="UTC").normalize() - pd.Timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d")


def _cache_path_for(city: str, start: str, end: str, *, lead_hours: int) -> str:
    """
    Include the lead hours AND the forecast source name in the cache
    filename -- not cosmetic. The prior (city, window)-only key would
    silently serve a warmed 1-hour-lead frame to a 24-hour caller, and
    every downstream arm would score a one-hour lead while the report
    claimed twenty-four (T-03-03-06). The source name is included too, so a
    future third lead sharing a lead-hours VALUE with an existing one (not
    currently possible, but not structurally prevented) can never collide.
    """
    source_name = _lead_source_config(lead_hours).source_name
    return os.path.join(
        config.FORECAST_EXPERIMENT_CACHE_DIR,
        f"anchored_pair_frame_{city}_{start}_{end}_lead{lead_hours}_{source_name}.csv",
    )


def _city_ampacity(air_temp, wind_speed, wind_direction, solar_radiation, geometry) -> np.ndarray:
    """
    The ONE place this module turns weather into amps:
    `thermal_model.perpendicular_wind` onto the corridor bearing, then
    `thermal_model.ieee738_ampacity` with the corridor's `ConductorConfig`.
    Every arm goes through this function so no arm can accidentally use
    different physics from another.
    """
    perp = thermal_model.perpendicular_wind(
        np.asarray(wind_speed, dtype=float),
        np.asarray(wind_direction, dtype=float),
        geometry.bearing_deg,
    )
    return np.asarray(
        thermal_model.ieee738_ampacity(
            np.asarray(air_temp, dtype=float), perp,
            np.asarray(solar_radiation, dtype=float), geometry.conductor,
        ),
        dtype=float,
    )


def anchored_pair_frame(city: str, start=None, end=None, *, lead_hours: int) -> pd.DataFrame:
    """
    Assemble the anchored pair frame for `city` over `[start, end]` at
    `lead_hours` -- see this module's docstring for the full contract.
    `lead_hours` is a REQUIRED keyword-only parameter (Plan 03-03's
    checkpoint decision): no caller can omit it, so no caller can silently
    score a 1-hour-lead frame while believing it is a 24-hour one -- the
    exact failure mode ("a lead-time boundary characterized from one of
    four model runs", "a raw-forecast arm scoring a perfect zero because
    forecast and truth were the same numbers") that has already derailed
    this phase twice this session.

    Truth comes directly from `open_meteo_provider.fetch_open_meteo` over
    the exact `[start, end]` window (rather than `forecast_training.
    fetch_city_weather`'s own per-complete-calendar-year chunking), so the
    window bounds passed in are exactly the window bounds fetched --
    `fetch_city_weather` would silently round to complete calendar years,
    which would misrepresent the window in the emitted report (03-RESEARCH.md
    Pitfall 6's "a shortened run is visible in the evidence" principle,
    applied to the window bounds themselves). The forecast series comes
    from `_lead_source_config(lead_hours)`'s fetch function -- the legacy
    Historical-Forecast adapter for `lead_hours=1`, the Previous-Runs
    adapter for `lead_hours=config.FORECAST_EXPERIMENT_PRIMARY_LEAD_HOURS`.

    `truth_dlr_amps` and `anchor_dlr_amps` (from the SAME per-row ampacity
    computed `lead_hours` earlier, via the SAME `_city_ampacity` every arm
    uses) are computed over the FULL unfiltered hourly series before the
    `hour % modulus == r` filter is applied -- the filter is applied later,
    by `filter_to_exact_lead`, and is never consulted here. The SAME
    discipline builds `fcst_anchor_*`: the forecast series' own values at
    `T - lead_hours`, from the FULL unfiltered forecast series -- Plan
    03-04's wind-delta arm needs the forecast's own change between the
    anchor time and the valid time, and deriving it there from a re-shift
    of an already-filtered frame would reintroduce exactly the staleness
    this contract exists to prevent.

    Caches the assembled frame to CSV under
    `config.FORECAST_EXPERIMENT_CACHE_DIR`, keyed by city, window, lead
    hours AND forecast source (`_cache_path_for`), and reads the cache when
    present, so a test run never re-issues an HTTP request.

    Returns:
        A DataFrame with `datetime_utc` (valid time T), `anchor_datetime_utc`
        (T - lead_hours), `anchor_*`/`truth_*`/`fcst_*`/`fcst_anchor_*`
        weather + ampacity columns, and `hour_mod_remainder`
        (`T.hour % config.FORECAST_EXPERIMENT_LEAD_FILTER_MODULUS`, a
        diagnostic column -- `filter_to_exact_lead` recomputes this from
        `datetime_utc` directly rather than trusting a stored column).
    """
    lead_cfg = _lead_source_config(lead_hours)
    lead_td = pd.Timedelta(hours=lead_hours)

    start = start if start is not None else lead_cfg.default_window_start
    end = _resolve_window_end(end if end is not None else config.FORECAST_EXPERIMENT_WINDOW_END)

    os.makedirs(config.FORECAST_EXPERIMENT_CACHE_DIR, exist_ok=True)
    cache_path = _cache_path_for(city, start, end, lead_hours=lead_hours)
    if os.path.exists(cache_path):
        cached = pd.read_csv(cache_path)
        cached["datetime_utc"] = pd.to_datetime(cached["datetime_utc"], utc=True)
        cached["anchor_datetime_utc"] = pd.to_datetime(cached["anchor_datetime_utc"], utc=True)
        return cached

    lat, lon = config.CITY_COORDINATES[city]
    geometry = corridor_discretization.corridor_geometry(_corridor_for_city(city))

    truth = open_meteo_provider.fetch_open_meteo(lat, lon, start, end)
    truth = truth.sort_values("datetime_utc").reset_index(drop=True)
    truth["dlr_amps"] = _city_ampacity(
        truth["air_temp"], truth["wind_speed"], truth["wind_direction"],
        truth["solar_radiation"], geometry,
    )

    # Looked up via getattr at call time (not bound at import), so a test's
    # monkeypatch on open_meteo_forecast_provider.<fetch_fn_name> is honored.
    fetch_fn = getattr(open_meteo_forecast_provider, lead_cfg.fetch_fn_name)
    fcst = fetch_fn(lat, lon, start, end)
    fcst = fcst.sort_values("datetime_utc").reset_index(drop=True)

    # Anchor group: the FULL, unfiltered truth series shifted forward by
    # exactly lead_hours, so each row at valid time T carries the
    # observation a forecaster would have had at T - lead_hours. Built
    # from the unfiltered series -- never from a subset -- per this
    # module's central invariant.
    anchor = truth.rename(columns={
        "datetime_utc": "anchor_datetime_utc",
        "air_temp": "anchor_air_temp",
        "wind_speed": "anchor_wind_speed",
        "wind_direction": "anchor_wind_direction",
        "solar_radiation": "anchor_solar_radiation",
        "relative_humidity": "anchor_relative_humidity",
        "dlr_amps": "anchor_dlr_amps",
    })
    anchor["datetime_utc"] = anchor["anchor_datetime_utc"] + lead_td

    # fcst_anchor group: the SAME shift-by-lead_hours discipline, applied to
    # the FULL unfiltered FORECAST series instead of truth -- the
    # forecast's own value at the anchor time, for Plan 03-04's wind-delta
    # arm to consume without re-deriving this shift itself.
    fcst_anchor = fcst.rename(columns={
        "datetime_utc": "fcst_anchor_datetime_utc",
        "air_temp": "fcst_anchor_air_temp",
        "wind_speed": "fcst_anchor_wind_speed",
        "wind_direction": "fcst_anchor_wind_direction",
        "solar_radiation": "fcst_anchor_solar_radiation",
        "relative_humidity": "fcst_anchor_relative_humidity",
    })
    fcst_anchor["datetime_utc"] = fcst_anchor["fcst_anchor_datetime_utc"] + lead_td

    truth_renamed = truth.rename(columns={
        "air_temp": "truth_air_temp",
        "wind_speed": "truth_wind_speed",
        "wind_direction": "truth_wind_direction",
        "solar_radiation": "truth_solar_radiation",
        "relative_humidity": "truth_relative_humidity",
        "dlr_amps": "truth_dlr_amps",
    })

    fcst_renamed = fcst.rename(columns={
        "air_temp": "fcst_air_temp",
        "wind_speed": "fcst_wind_speed",
        "wind_direction": "fcst_wind_direction",
        "solar_radiation": "fcst_solar_radiation",
        "relative_humidity": "fcst_relative_humidity",
    })

    merged = truth_renamed.merge(fcst_renamed, on="datetime_utc", how="inner")
    merged = merged.merge(anchor, on="datetime_utc", how="inner")
    merged = merged.merge(fcst_anchor, on="datetime_utc", how="inner")

    before = len(merged)
    merged = merged.dropna().reset_index(drop=True)
    dropped = before - len(merged)
    if dropped:
        logger.warning(
            "anchored_pair_frame: dropped %d row(s) with a null in any "
            "group for %s [%s, %s] at lead_hours=%d -- never imputed",
            dropped, city, start, end, lead_hours,
        )

    merged["hour_mod_remainder"] = (
        merged["datetime_utc"].dt.hour % config.FORECAST_EXPERIMENT_LEAD_FILTER_MODULUS
    )
    merged = merged.sort_values("datetime_utc").reset_index(drop=True)

    merged.to_csv(cache_path, index=False)
    return merged


def assert_exact_lead(frame: pd.DataFrame, *, lead_hours: int) -> None:
    """
    Raise `ValueError` naming the first offending timestamp, the observed
    gap, and the CLAIMED lead when any row's `datetime_utc` (truth time T)
    minus `anchor_datetime_utc` is not exactly `lead_hours`. `lead_hours` is
    a REQUIRED keyword-only parameter (Plan 03-03's checkpoint decision) --
    naming the claimed lead in the error message means a caller who passes
    the wrong `lead_hours` gets a message that names BOTH numbers, making
    the mismatch diagnosable from the exception alone. Called before every
    scoring pass -- the automated enforcement of this module's central
    invariant.
    """
    lead_td = pd.Timedelta(hours=lead_hours)
    gaps = frame["datetime_utc"] - frame["anchor_datetime_utc"]
    bad = gaps != lead_td
    if bad.any():
        first_idx = bad.idxmax()
        raise ValueError(
            f"forecast_experiment: row at {frame.loc[first_idx, 'datetime_utc']} "
            f"has an anchor gap of {gaps.loc[first_idx]}, not the claimed "
            f"{lead_td} ({lead_hours}h) lead -- the persistence baseline "
            f"would be stale for this row"
        )


def filter_to_exact_lead(frame: pd.DataFrame, *, lead_hours: int) -> pd.DataFrame:
    """
    Return the subset of `frame` where `datetime_utc.hour % modulus`
    equals the remainder `_lead_source_config(lead_hours)` claims --
    `config.FORECAST_EXPERIMENT_LEAD_FILTER_REMAINDER` (1) for the legacy
    1-hour arm, `config.FORECAST_EXPERIMENT_24H_LEAD_FILTER_REMAINDER` (0)
    for D-04's primary 24-hour arm. `lead_hours` is a REQUIRED keyword-only
    parameter for the same reason `anchored_pair_frame`/`assert_exact_lead`
    require it: a defaulted value would let a caller silently filter a
    24-hour frame to the legacy remainder (or vice versa), scoring rows
    that look plausible but carry the wrong lead.

    Recomputes the remainder directly from `datetime_utc` rather than
    trusting `frame`'s stored `hour_mod_remainder` diagnostic column, so
    this function's correctness never depends on that column having been
    computed consistently upstream.

    This SELECTS WHICH ROWS ARE SCORED. It is never applied before the
    anchor group is built -- `anchored_pair_frame` always builds the
    anchor group from the full unfiltered series first.
    """
    remainder = _lead_source_config(lead_hours).filter_remainder
    modulus = config.FORECAST_EXPERIMENT_LEAD_FILTER_MODULUS
    selected = frame["datetime_utc"].dt.hour % modulus == remainder
    return frame[selected].reset_index(drop=True)


def score_arms(test_frame: pd.DataFrame, arms: dict) -> dict:
    """
    Score every callable in `arms` (mapping of arm name -> a callable
    taking `test_frame` and returning a prediction array) against
    `test_frame["truth_dlr_amps"]`.

    Asserts up front that `test_frame`'s index is unique and sorted (the
    identical-test-timestamp-index requirement this phase's whole design
    rests on), and that every arm returns an array of the same length as
    `test_frame`.

    Returns:
        `{"candidates": {arm_name: {"mae", "rmse", "rows"}}, "test_index":
        [the exact index values scored, as a list]}` -- `test_index` is
        kept OUTSIDE `candidates` so `report["candidates"]` (this
        function's `candidates` value) stays a clean per-arm score
        mapping, matching `forecast_training.corridor_report`'s own
        `candidates` shape.
    """
    if not test_frame.index.is_unique:
        raise ValueError("score_arms: test_frame index is not unique")
    if not test_frame.index.is_monotonic_increasing:
        raise ValueError("score_arms: test_frame index is not sorted")

    actual = test_frame["truth_dlr_amps"].to_numpy(dtype=float)
    n = len(test_frame)

    candidates = {}
    for name, fn in arms.items():
        pred = np.asarray(fn(test_frame), dtype=float)
        if len(pred) != n:
            raise ValueError(
                f"score_arms: arm {name!r} returned {len(pred)} "
                f"prediction(s), expected {n} (test_frame's row count)"
            )
        residual = actual - pred
        candidates[name] = {
            "mae": float(np.mean(np.abs(residual))),
            "rmse": float(np.sqrt(np.mean(residual ** 2))),
            "rows": int(n),
        }

    return {"candidates": candidates, "test_index": list(test_frame.index)}


def _default_split_boundaries(frame: pd.DataFrame, val_fraction=0.2, test_fraction=0.2):
    """
    Compute calendar `SplitBoundaries` for `frame` that place the last
    `test_fraction` of its CALENDAR SPAN (not row count) in test and the
    `val_fraction` before that in val -- since `frame`'s rows are
    approximately evenly spaced in time, this closely approximates a
    row-count-proportional split without hand-rolling an `.iloc` slice
    (RESEARCH.md "Don't Hand-Roll").
    """
    min_dt = frame["datetime_utc"].min()
    max_dt = frame["datetime_utc"].max()
    span = max_dt - min_dt
    val_start = min_dt + span * (1.0 - val_fraction - test_fraction)
    test_start = min_dt + span * (1.0 - test_fraction)
    return experiment_splits.SplitBoundaries(val_start, test_start)


def corridor_experiment_report(city, start, end, assembled_frame, filtered_frame,
                                boundaries, scored, *, lead_hours: int) -> dict:
    """
    Assemble the report mapping: the city, the window start and end, the
    assembled and scored row counts, the split boundaries, the ACTUAL
    `lead_hours` (never a hardcoded 1.0 -- exact by construction of
    `filter_to_exact_lead`, which only ever passes through rows whose
    anchor gap matches this value), the caveat and filter remainder that
    match THIS lead (`_lead_source_config(lead_hours)`, never the other
    lead's), and the per-arm scores (`scored["candidates"]`, unpacked so
    this key matches `forecast_training.corridor_report`'s own
    `candidates` shape).
    """
    lead_cfg = _lead_source_config(lead_hours)
    return {
        "city": city,
        "window_start": str(start),
        "window_end": str(end),
        "rows_assembled": int(len(assembled_frame)),
        "rows_scored": int(len(filtered_frame)),
        "split_boundaries": {
            "val_start": str(boundaries.val_start),
            "test_start": str(boundaries.test_start),
        },
        "measured_lead_hours": float(lead_hours),
        "filter_remainder": lead_cfg.filter_remainder,
        "caveat": lead_cfg.caveat,
        "candidates": scored["candidates"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Assemble the anchored pair frame for one city at "
        "--lead-hours and score persistence against raw-forecast-through-"
        "IEEE-738 on an identical held-out VALIDATION-split-timestamp "
        "index (never the test split -- Success Criterion 5's no-peeking "
        "discipline).",
    )
    parser.add_argument(
        "--city", choices=sorted(config.CITY_COORDINATES), required=True,
        help="City to score.",
    )
    parser.add_argument(
        "--start", default=None,
        help="Window start (default: the --lead-hours-appropriate default "
        "window start -- config.FORECAST_EXPERIMENT_PREVIOUS_RUNS_WINDOW_"
        "START for the 24h primary lead, config.FORECAST_EXPERIMENT_"
        "WINDOW_START for the legacy 1h lead).",
    )
    parser.add_argument(
        "--end", default=None,
        help="Window end (default: config.FORECAST_EXPERIMENT_WINDOW_END, "
        "resolved to yesterday UTC when unset).",
    )
    parser.add_argument(
        "--lead-hours", type=int, default=config.FORECAST_EXPERIMENT_PRIMARY_LEAD_HOURS,
        help="Which lead to score: 1 (legacy non-primary curiosity) or "
        f"{config.FORECAST_EXPERIMENT_PRIMARY_LEAD_HOURS} (D-04 primary, "
        "the default).",
    )
    args = parser.parse_args(argv)

    city = args.city
    lead_hours = args.lead_hours
    lead_cfg = _lead_source_config(lead_hours)
    start = args.start if args.start is not None else lead_cfg.default_window_start
    end = _resolve_window_end(args.end if args.end is not None else config.FORECAST_EXPERIMENT_WINDOW_END)

    frame = anchored_pair_frame(city, start, end, lead_hours=lead_hours)
    assert_exact_lead(frame, lead_hours=lead_hours)

    boundaries = _default_split_boundaries(frame)
    train, val, test = experiment_splits.calendar_split(frame, boundaries)

    filtered = filter_to_exact_lead(frame, lead_hours=lead_hours)

    # Success Criterion 5's no-peeking discipline: this plan's own main()
    # scores the VALIDATION split only. The guard call below is a no-op
    # for "val" -- it documents, in the code path itself, that a future
    # change routing this call through "test" would be mechanically
    # refused while _TEST_SPLIT_UNLOCKED is False.
    _guard_test_split_access("val")
    val_scored = filter_to_exact_lead(val, lead_hours=lead_hours)
    assert_exact_lead(val_scored, lead_hours=lead_hours)

    geometry = corridor_discretization.corridor_geometry(_corridor_for_city(city))

    # The 24-hour persistence arm's prediction is the anchor group's
    # ampacity DIRECTLY -- built by anchored_pair_frame as a shift of the
    # FULL unfiltered truth series by exactly lead_hours, never via
    # ampacity_forecast's one-row-lag production helpers (03-RESEARCH.md
    # Anti-Patterns; this module's own docstring). The arm name is
    # lead-qualified for lead_hours != 1 so a report can never present a
    # 24-hour persistence score under the legacy arm's bare "persistence"
    # name.
    persistence_arm_name = "persistence" if lead_hours == 1 else f"persistence_{lead_hours}h"
    arms = {
        persistence_arm_name: lambda f: f["anchor_dlr_amps"].to_numpy(dtype=float),
        "raw_forecast": lambda f: _city_ampacity(
            f["fcst_air_temp"], f["fcst_wind_speed"], f["fcst_wind_direction"],
            f["fcst_solar_radiation"], geometry,
        ),
    }
    scored = score_arms(val_scored, arms)

    report = corridor_experiment_report(
        city, start, end, frame, val_scored, boundaries, scored, lead_hours=lead_hours,
    )

    os.makedirs(config.FORECAST_EXPERIMENT_CACHE_DIR, exist_ok=True)
    report_path = os.path.join(
        config.FORECAST_EXPERIMENT_CACHE_DIR, f"experiment_report_{city}_lead{lead_hours}.json",
    )
    with open(report_path, "w") as fh:
        json.dump(report, fh, indent=2, default=str)

    print(f"\n{city}: assembled {len(frame)} rows, scored {len(val_scored)} val rows, "
          f"lead {lead_hours}h, window {start} -> {end}")
    print(f"{'candidate':<20}{'mae':>12}{'rmse':>12}{'rows':>10}")
    for name, s in report["candidates"].items():
        print(f"{name:<20}{s['mae']:>12.3f}{s['rmse']:>12.3f}{s['rows']:>10d}")
    print(f"\n{lead_cfg.caveat}")
    print(f"report written to {report_path}")

    candidate_summary = " ".join(
        f"{name}_mae={s['mae']:.3f}" for name, s in report["candidates"].items()
    )
    print(
        f"\nSUMMARY: {city} lead_hours={lead_hours} rows_assembled={len(frame)} "
        f"rows_scored={len(val_scored)} window={start}->{end} split=val "
        f"{candidate_summary} caveat_present=True"
    )


if __name__ == "__main__":
    main()
