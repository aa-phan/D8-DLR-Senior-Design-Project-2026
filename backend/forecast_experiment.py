"""
Ampacity Forecast Experiment Harness -- Anchored Pair Frame + Arm Scoring
(D-01/D-02, Phase 3 experiment, first tracer slice)
==========================================================================
Standalone offline entry point -- NOT imported by the runtime pipeline,
mirroring `forecast_training.py`/`anomaly_training.py`'s own convention.
Imports `ampacity_forecast`, `config`, `corridor_discretization`,
`experiment_splits`, `open_meteo_forecast_provider`, `open_meteo_provider`,
`thermal_model`; nothing imports this module.

THE ANCHORED-PAIR-FRAME CONTRACT (this plan's central invariant, inherited
by every later plan in this phase). One row per scored valid time `T`
where `T.hour % config.FORECAST_EXPERIMENT_LEAD_FILTER_MODULUS ==
config.FORECAST_EXPERIMENT_LEAD_FILTER_REMAINDER`, carrying three
time-distinct column groups, ALL assembled from the FULL unfiltered hourly
truth series BEFORE the `hour % 6 == 1` filter is applied:

    Group      Time         Source
    ---------  -----------  ---------------------------------------------
    anchor_*   T - 1 h      Archive API truth (the last observation a
                            forecaster would actually have had)
    truth_*    T            Archive API truth (what actually happened)
    fcst_*     T (issued    Historical Forecast API, models=ecmwf_ifs
               at T - 1 h)

The `hour % 6 == 1` filter selects WHICH ROWS ARE SCORED. It is NEVER the
source of a lagged value. This is the single most important invariant in
the phase: filtered rows are six hours apart, so a persistence baseline
computed from them would be a six-hour-stale predictor presented as a
one-hour one -- every forecast arm would beat it and the phase would
publish a falsely positive result. `anchored_pair_frame` builds the
anchor group by shifting the FULL, unfiltered hourly truth series forward
by exactly one hour -- never from the filtered subset -- and
`assert_exact_lead` is the automated gate that catches a violation of
this invariant before any scoring pass runs.

`EXPERIMENT_LEAD_REALIZABILITY_CAVEAT` (03-RESEARCH.md Pitfall 6): the
one-hour-lead arms this module scores are scored at an IDEALIZED
dissemination latency no live system could have had. It is emitted on
every output surface -- the JSON report and the printed `SUMMARY:` line --
so a reader can never see a score without seeing that qualifier.

Window note (Plan 03-01, corrected twice -- see `config.py`'s
`FORECAST_EXPERIMENT_WINDOW_START` for the full history): the bulk/single
-run bit-identical lead rule this phase depends on does not hold before
`config.FORECAST_EXPERIMENT_WINDOW_START`. This module does not itself
re-verify that rule -- `forecast_leadtime_calibration.py` is the gate for
that -- but it defaults to the same corrected window so a caller who
doesn't override `--start`/`--end` cannot accidentally score outside the
window the rule has actually been verified on.
"""

import argparse
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


def _cache_path_for(city: str, start: str, end: str) -> str:
    return os.path.join(
        config.FORECAST_EXPERIMENT_CACHE_DIR,
        f"anchored_pair_frame_{city}_{start}_{end}.csv",
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


def anchored_pair_frame(city: str, start=None, end=None) -> pd.DataFrame:
    """
    Assemble the anchored pair frame for `city` over `[start, end]` -- see
    this module's docstring for the full contract.

    Truth comes directly from `open_meteo_provider.fetch_open_meteo` over
    the exact `[start, end]` window (rather than `forecast_training.
    fetch_city_weather`'s own per-complete-calendar-year chunking), so the
    window bounds passed in are exactly the window bounds fetched --
    `fetch_city_weather` would silently round to complete calendar years,
    which would misrepresent the window in the emitted report (03-RESEARCH.md
    Pitfall 6's "a shortened run is visible in the evidence" principle,
    applied to the window bounds themselves).

    Both `truth_dlr_amps` (from truth weather) and `anchor_dlr_amps` (from
    the SAME per-row ampacity computed one hour earlier, via the SAME
    `_city_ampacity` every arm uses) are computed over the FULL unfiltered
    hourly series before the `hour % 6 == 1` filter is applied -- the
    filter is applied later, by `filter_to_exact_lead`, and is never
    consulted here.

    Caches the assembled frame to CSV under
    `config.FORECAST_EXPERIMENT_CACHE_DIR`, keyed by city and window, and
    reads the cache when present, so a test run never re-issues an HTTP
    request.

    Returns:
        A DataFrame with `datetime_utc` (valid time T), `anchor_datetime_utc`
        (T - 1h), `anchor_*`/`truth_*`/`fcst_*` weather + ampacity columns,
        and `lead_hours` (`T.hour % config.FORECAST_EXPERIMENT_LEAD_FILTER_
        MODULUS`).
    """
    start = start if start is not None else config.FORECAST_EXPERIMENT_WINDOW_START
    end = _resolve_window_end(end if end is not None else config.FORECAST_EXPERIMENT_WINDOW_END)

    os.makedirs(config.FORECAST_EXPERIMENT_CACHE_DIR, exist_ok=True)
    cache_path = _cache_path_for(city, start, end)
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

    fcst = open_meteo_forecast_provider.fetch_historical_forecast(lat, lon, start, end)
    fcst = fcst.sort_values("datetime_utc").reset_index(drop=True)

    # Anchor group: the FULL, unfiltered truth series shifted forward by
    # exactly one hour, so each row at valid time T carries the
    # observation the forecaster would have had at T - 1h. Built from the
    # unfiltered series -- never from a subset -- per this module's
    # central invariant.
    anchor = truth.rename(columns={
        "datetime_utc": "anchor_datetime_utc",
        "air_temp": "anchor_air_temp",
        "wind_speed": "anchor_wind_speed",
        "wind_direction": "anchor_wind_direction",
        "solar_radiation": "anchor_solar_radiation",
        "relative_humidity": "anchor_relative_humidity",
        "dlr_amps": "anchor_dlr_amps",
    })
    anchor["datetime_utc"] = anchor["anchor_datetime_utc"] + pd.Timedelta(hours=1)

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

    before = len(merged)
    merged = merged.dropna().reset_index(drop=True)
    dropped = before - len(merged)
    if dropped:
        logger.warning(
            "anchored_pair_frame: dropped %d row(s) with a null in any "
            "group for %s [%s, %s] -- never imputed", dropped, city, start, end,
        )

    merged["lead_hours"] = merged["datetime_utc"].dt.hour % config.FORECAST_EXPERIMENT_LEAD_FILTER_MODULUS
    merged = merged.sort_values("datetime_utc").reset_index(drop=True)

    merged.to_csv(cache_path, index=False)
    return merged


def assert_exact_lead(frame: pd.DataFrame) -> None:
    """
    Raise `ValueError` naming the first offending timestamp and the
    observed gap when any row's `datetime_utc` (truth time T) minus
    `anchor_datetime_utc` is not exactly one hour. Called before every
    scoring pass -- the automated enforcement of this module's central
    invariant.
    """
    gaps = frame["datetime_utc"] - frame["anchor_datetime_utc"]
    bad = gaps != pd.Timedelta(hours=1)
    if bad.any():
        first_idx = bad.idxmax()
        raise ValueError(
            f"forecast_experiment: row at {frame.loc[first_idx, 'datetime_utc']} "
            f"has an anchor gap of {gaps.loc[first_idx]}, not exactly one "
            f"hour -- the persistence baseline would be stale for this row"
        )


def filter_to_exact_lead(frame: pd.DataFrame) -> pd.DataFrame:
    """
    Return the subset of `frame` where `lead_hours` equals
    `config.FORECAST_EXPERIMENT_LEAD_FILTER_REMAINDER`.

    This SELECTS WHICH ROWS ARE SCORED. It is never applied before the
    anchor group is built -- `anchored_pair_frame` always builds the
    anchor group from the full unfiltered series first.
    """
    remainder = config.FORECAST_EXPERIMENT_LEAD_FILTER_REMAINDER
    return frame[frame["lead_hours"] == remainder].reset_index(drop=True)


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
                                boundaries, scored) -> dict:
    """
    Assemble the report mapping: the city, the window start and end, the
    assembled and scored row counts, the split boundaries, the measured
    lead (exactly 1h on the filtered subset, by construction of
    `filter_to_exact_lead`), the realizability caveat constant, and the
    per-arm scores (`scored["candidates"]`, unpacked so this key matches
    `forecast_training.corridor_report`'s own `candidates` shape).
    """
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
        "measured_lead_hours": 1.0,
        "caveat": EXPERIMENT_LEAD_REALIZABILITY_CAVEAT,
        "candidates": scored["candidates"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Assemble the anchored pair frame for one city and "
        "score persistence (arm 0) against raw-forecast-through-IEEE-738 "
        "(arm 2) on an identical held-out test-timestamp index.",
    )
    parser.add_argument(
        "--city", choices=sorted(config.CITY_COORDINATES), required=True,
        help="City to score.",
    )
    parser.add_argument(
        "--start", default=None,
        help="Window start (default: config.FORECAST_EXPERIMENT_WINDOW_START).",
    )
    parser.add_argument(
        "--end", default=None,
        help="Window end (default: config.FORECAST_EXPERIMENT_WINDOW_END, "
        "resolved to yesterday UTC when unset).",
    )
    args = parser.parse_args(argv)

    city = args.city
    start = args.start if args.start is not None else config.FORECAST_EXPERIMENT_WINDOW_START
    end = _resolve_window_end(args.end if args.end is not None else config.FORECAST_EXPERIMENT_WINDOW_END)

    frame = anchored_pair_frame(city, start, end)
    assert_exact_lead(frame)

    boundaries = _default_split_boundaries(frame)
    train, val, test = experiment_splits.calendar_split(frame, boundaries)

    filtered = filter_to_exact_lead(frame)
    test_scored = filter_to_exact_lead(test)
    assert_exact_lead(test_scored)

    geometry = corridor_discretization.corridor_geometry(_corridor_for_city(city))

    arms = {
        "persistence": lambda f: f["anchor_dlr_amps"].to_numpy(dtype=float),
        "raw_forecast": lambda f: _city_ampacity(
            f["fcst_air_temp"], f["fcst_wind_speed"], f["fcst_wind_direction"],
            f["fcst_solar_radiation"], geometry,
        ),
    }
    scored = score_arms(test_scored, arms)

    report = corridor_experiment_report(city, start, end, frame, filtered, boundaries, scored)

    os.makedirs(config.FORECAST_EXPERIMENT_CACHE_DIR, exist_ok=True)
    report_path = os.path.join(
        config.FORECAST_EXPERIMENT_CACHE_DIR, f"experiment_report_{city}.json",
    )
    with open(report_path, "w") as fh:
        json.dump(report, fh, indent=2, default=str)

    print(f"\n{city}: assembled {len(frame)} rows, scored {len(test_scored)} test rows, "
          f"window {start} -> {end}")
    print(f"{'candidate':<16}{'mae':>12}{'rmse':>12}{'rows':>10}")
    for name, s in report["candidates"].items():
        print(f"{name:<16}{s['mae']:>12.3f}{s['rmse']:>12.3f}{s['rows']:>10d}")
    print(f"\n{EXPERIMENT_LEAD_REALIZABILITY_CAVEAT}")
    print(f"report written to {report_path}")

    candidate_summary = " ".join(
        f"{name}_mae={s['mae']:.3f}" for name, s in report["candidates"].items()
    )
    print(
        f"\nSUMMARY: {city} rows_assembled={len(frame)} "
        f"rows_scored={len(test_scored)} window={start}->{end} "
        f"{candidate_summary} caveat_present=True"
    )


if __name__ == "__main__":
    main()
