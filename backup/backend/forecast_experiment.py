"""
FROZEN: reproduces the completed corridor-based 2026 experiment (docs/data-science/decisions/point_scope.md). Uses legacy_corridor; do not extend.

Ampacity Forecast Experiment Harness -- Anchored Pair Frame + Arm Scoring
(D-01 legacy 1h arm + D-04 PRIMARY 24h arm, Phase 3 experiment)
==========================================================================
Standalone offline entry point -- NOT imported by the runtime pipeline,
mirroring `forecast_training.py`/`anomaly_training.py`'s own convention.
Imports `ampacity_forecast`, `config`, `legacy_corridor`,
`experiment_splits`, `forecast_training` (for `corridor_weakest_link` only --
Plan 03-04, the repository's ONE weakest-link reduction, never a second
copy), `open_meteo_forecast_provider`, `open_meteo_provider`,
`thermal_model`; nothing imports this module.

CORRIDOR-LEVEL SCORING (Plan 03-04, D-02): `corridor_anchored_pair_frame`
assembles BOTH endpoint cities' `anchored_pair_frame`s, inner-joins them on
`datetime_utc`, and reduces the TRUTH group, the ANCHOR group, and each of
`NON_FITTED_ARMS`' four predictions INDEPENDENTLY through `forecast_
training.corridor_weakest_link` -- per column group AT ITS OWN TIME, since
the bottleneck city at the anchor time twenty-four hours earlier is not
necessarily the bottleneck at the valid time. `main`'s default mode (no
`--city`) scores every corridor this way; `--city` retains Plan 03-03's
single-city tracer path unchanged. The oracle (`ORACLE_ARM_NAME`) is scored
alongside the three genuine candidates but `corridor_experiment_report`
ALWAYS pops it into its own top-level `oracle_diagnostic` key -- structural
isolation, not caller discipline (ROADMAP Success Criterion 2).

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
import scipy.stats

import ampacity_forecast
import config
import legacy_corridor
import experiment_splits
import forecast_correction_models
import forecast_training
import open_meteo_forecast_provider
import open_meteo_provider
import thermal_model

logger = logging.getLogger(__name__)

# Success Criterion 5's no-peeking discipline, mechanically enforced (a
# comment asking a future executor not to peek is not enforcement).
# UNLOCKED by Plan 03-06 Task 1, in the SAME commit that lands the
# Expectation section of docs/data-science/decisions/
# forecast_correction_experiment.md -- git log is the audit trail: this
# commit contains exactly the decision record and this one-line flip, no
# scoring run and no arm implementation, so a reviewer can check from the
# commit graph, not a document's own date field, that the Expectation
# predates every held-out test read.
_TEST_SPLIT_UNLOCKED: bool = True

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


def _require_test_split_unlocked() -> None:
    """
    Plan 03-04's self-describing form of the no-peeking lock (Task 3):
    unconditionally raise if `_TEST_SPLIT_UNLOCKED` is `False`, naming the
    lock constant itself, Success Criterion 5's Expectation-record
    requirement, and Plan 03-06 as the specific commit that flips it. A
    lock whose error message does not say what to do next is a lock a
    future executor deletes instead of satisfying -- this message names
    both the WHY (the Expectation record) and the WHEN (Plan 03-06).

    Distinct from `_guard_test_split_access(split_name)` below, which only
    raises for a specific `"test"` request: this is the unconditional
    "is the lock engaged at all" check, usable without first constructing
    a split name.
    """
    if not _TEST_SPLIT_UNLOCKED:
        raise RuntimeError(
            "forecast_experiment: _TEST_SPLIT_UNLOCKED is False -- the "
            "held-out TEST split stays locked until the Expectation record "
            "(Success Criterion 5's no-peeking discipline) is committed. "
            "Plan 03-06 flips this flag in the SAME commit that lands that "
            "record; until then, no code path may score the test split."
        )


def _guard_test_split_access(split_name: str) -> None:
    """
    Raise if `split_name` names the held-out TEST split while
    `_TEST_SPLIT_UNLOCKED` is `False` -- the mechanical enforcement of
    Success Criterion 5's no-peeking discipline. Delegates the actual
    raise to `_require_test_split_unlocked` so both entry points share one
    message. Plan 03-06 flips the module-level flag in the same commit
    that lands the Expectation record.
    """
    if split_name == "test":
        _require_test_split_unlocked()


def _corridor_for_city(city: str) -> str:
    """
    Reverse-lookup: the one corridor in `config.LEGACY_CORRIDOR_ENDPOINTS` whose
    endpoints include `city`. Task 3 scores at CITY level, but
    `thermal_model.ieee738_ampacity` needs a per-corridor `ConductorConfig`
    and bearing (`legacy_corridor.corridor_geometry`) -- the
    conductor config is per-corridor even though this module scores one
    city at a time (03-01-PLAN.md Task 3 read_first).

    Raises:
        ValueError: naming `city` and the valid cities, if `city` is not
            an endpoint of any corridor.
    """
    for corridor, (city_a, city_b) in config.LEGACY_CORRIDOR_ENDPOINTS.items():
        if city in (city_a, city_b):
            return corridor
    valid = sorted({c for pair in config.LEGACY_CORRIDOR_ENDPOINTS.values() for c in pair})
    raise ValueError(
        f"forecast_experiment: {city!r} is not an endpoint of any corridor "
        f"in config.LEGACY_CORRIDOR_ENDPOINTS; valid cities: {valid}"
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


# ──────────────────────────────────────────────────────────────────────────
# D-02's four non-fitted arms (Plan 03-04): persistence, the NWP-wind-delta
# baseline, the raw forecast, and the oracle diagnostic. Mirrors
# `forecast_training.CANDIDATE_ESTIMATORS`'s convention -- a zero-argument
# ... except here each entry is a ONE-argument factory taking the corridor
# geometry (not zero-argument, since every arm needs a `ConductorConfig`/
# bearing to turn weather into amps via `_city_ampacity`) and returning a
# callable of the scored frame. Nothing is bound to a geometry at import
# time; a caller resolves the geometry for its own corridor/city first
# (`legacy_corridor.corridor_geometry`), then builds each arm's
# callable from it. Order below is significant ONLY for report readability
# (the order candidates print in) -- it has no effect on scoring. The
# oracle's membership in this mapping does NOT make it a candidate: Task 2's
# report assembly is what keeps it out of `report["candidates"]`, by
# reading `NON_FITTED_ARMS` but excluding `ORACLE_ARM_NAME` before scoring
# the candidate set.
# ──────────────────────────────────────────────────────────────────────────

# A rename of this string cannot desynchronize the oracle's isolation logic
# from the arm it isolates -- every place that needs to single out the
# oracle (Task 2's report assembly, every test) refers to this constant,
# never a literal string.
ORACLE_ARM_NAME: str = "oracle_observed_future_wind"


def _make_persistence_24h_arm(geometry):
    """
    Arm 0 (D-02 approach 0, promoted to PRIMARY by D-04): the frame's
    `anchor_dlr_amps` column directly -- the truth ampacity computed at
    `T - lead_hours` from the FULL unfiltered series (`anchored_pair_
    frame`'s anchor group), never re-derived here. This arm is deliberately
    NOT routed through the production forecasting module's naive
    point-forecast/backtest-walk-forward helpers: that code path's naive
    branch returns the immediately preceding ROW, which is one hour at this
    project's hourly cadence, so a twenty-four-hour claim routed through it
    would silently score a one-hour-old baseline under a twenty-four-hour
    label (03-RESEARCH.md Anti-Patterns). RESEARCH.md Pattern 4's
    expectation-setting: at exactly 24 hours, persistence is diurnally
    self-aligned to the SAME approximate solar angle and diurnal wind
    regime as the valid time, making this the day-ago-same-hour baseline
    time-series literature treats as genuinely hard to beat -- not the weak
    baseline a "longer horizon is easier to beat" intuition predicts.
    """

    def arm(frame: pd.DataFrame) -> np.ndarray:
        return frame["anchor_dlr_amps"].to_numpy(dtype=float)

    return arm


def _nwp_wind_delta_raw_wind_speed(frame: pd.DataFrame) -> np.ndarray:
    """
    Arm 1's wind speed BEFORE the physical zero-floor clamp: the observed
    wind at the anchor time plus the forecast's own change between the
    anchor time and the valid time. Factored out of the arm callable so
    `nwp_wind_delta_clamp_count` can recompute the identical unclamped value
    without duplicating the arithmetic.
    """
    return (
        frame["anchor_wind_speed"].to_numpy(dtype=float)
        + (
            frame["fcst_wind_speed"].to_numpy(dtype=float)
            - frame["fcst_anchor_wind_speed"].to_numpy(dtype=float)
        )
    )


def nwp_wind_delta_clamp_count(frame: pd.DataFrame) -> int:
    """
    Count of rows where arm 1's raw (pre-clamp) wind speed was negative and
    was brought to the schema's physical zero lower bound. This clamp is a
    physical bound, not an imputation -- no value is invented, a physically
    impossible one is brought to its bound -- but its hit rate is reported
    on every output surface so the adjustment is visible rather than
    silent (Task 2's `corridor_experiment_report` extension).
    """
    raw = _nwp_wind_delta_raw_wind_speed(frame)
    return int(np.sum(raw < 0.0))


def _make_nwp_wind_delta_arm(geometry):
    """
    Arm 1 (D-02 approach 1): the observed wind at the anchor time, adjusted
    by the forecast's own change over the lead --
    `anchor_wind_speed + (fcst_wind_speed - fcst_anchor_wind_speed)` --
    with every OTHER input (air temperature, solar radiation, wind
    direction) held at its latest-observed anchor value, exactly what D-02
    specifies by "other inputs held at latest-observed". A wind speed
    cannot be negative (the schema's physical lower bound is zero), so the
    result is floored at zero with `np.maximum` rather than dropping the
    row -- a physical bound, not an imputation; see
    `nwp_wind_delta_clamp_count` for the visible hit-rate accounting. When
    the forecast's anchor and valid values coincide
    (`fcst_wind_speed == fcst_anchor_wind_speed`), the wind term reduces to
    `anchor_wind_speed` exactly and every other input is already the anchor
    value, so this arm's prediction equals arm 0's (`persistence_24h`).
    """

    def arm(frame: pd.DataFrame) -> np.ndarray:
        wind_speed = np.maximum(_nwp_wind_delta_raw_wind_speed(frame), 0.0)
        return _city_ampacity(
            frame["anchor_air_temp"], wind_speed, frame["anchor_wind_direction"],
            frame["anchor_solar_radiation"], geometry,
        )

    return arm


def _make_raw_forecast_arm(geometry):
    """
    Arm 2 (D-02 approach 2): `_city_ampacity` applied to the four forecast
    weather columns (`fcst_air_temp`, `fcst_wind_speed`,
    `fcst_wind_direction`, `fcst_solar_radiation`) unchanged -- no
    correction of any kind. Structurally identical to the tracer's arm 2
    from Plan 03-03, now sourced from this registry.
    """

    def arm(frame: pd.DataFrame) -> np.ndarray:
        return _city_ampacity(
            frame["fcst_air_temp"], frame["fcst_wind_speed"], frame["fcst_wind_direction"],
            frame["fcst_solar_radiation"], geometry,
        )

    return arm


def _make_oracle_arm(geometry):
    """
    This is NOT a forecast and can never be a candidate. Arm 6 (D-02
    approach 6, the oracle diagnostic): `_city_ampacity` applied to the
    TRUTH wind speed and direction together with the FORECAST air
    temperature and solar radiation. This is deliberate: substituting truth
    for every variable would make the oracle simply reproduce
    `truth_dlr_amps` and measure nothing; substituting truth for the WIND
    ONLY isolates precisely the headroom a perfect wind correction could
    capture, which is the diagnostic D-02 asks for. It substitutes observed
    future weather that no real forecast could have had, so it bounds the
    maximum benefit any wind correction could ever achieve rather than
    representing an achievable method -- Task 2's report assembly keeps it
    under its own top-level report key, structurally outside
    `report["candidates"]`, so no winner-selection step iterating
    candidates can ever reach it.
    """

    def arm(frame: pd.DataFrame) -> np.ndarray:
        return _city_ampacity(
            frame["fcst_air_temp"], frame["truth_wind_speed"], frame["truth_wind_direction"],
            frame["fcst_solar_radiation"], geometry,
        )

    return arm


# The named arm registry: name -> factory(geometry) -> callable(frame) ->
# np.ndarray. Mirrors `forecast_training.CANDIDATE_ESTIMATORS`'s
# zero-argument-factory convention, generalized to one argument (the
# corridor geometry) since every arm here needs a `ConductorConfig`/bearing
# to turn weather into amps. Order is significant only for report
# readability; the oracle's presence here does NOT make it a candidate --
# see `ORACLE_ARM_NAME`'s docstring and Task 2's report assembly.
NON_FITTED_ARMS: dict = {
    "persistence_24h": _make_persistence_24h_arm,
    "nwp_wind_delta": _make_nwp_wind_delta_arm,
    "raw_forecast": _make_raw_forecast_arm,
    ORACLE_ARM_NAME: _make_oracle_arm,
}


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
    geometry = legacy_corridor.corridor_geometry(_corridor_for_city(city))

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


def _strip_city_suffix(merged: pd.DataFrame, suffix: str) -> pd.DataFrame:
    """
    Recover one endpoint city's own per-row columns from `merged` (the
    result of `frame_a.merge(frame_b, on="datetime_utc", suffixes=("_a",
    "_b"))`) by keeping only the columns ending in `suffix` and stripping
    it, then re-attaching the unsuffixed `datetime_utc` merge key. The
    returned frame has exactly the same column names `anchored_pair_frame`
    produces for a single city, so `NON_FITTED_ARMS`' factories can be
    applied to it unchanged.
    """
    cols = [c for c in merged.columns if c.endswith(suffix)]
    renamed = merged[cols].rename(columns=lambda c: c[: -len(suffix)])
    renamed.insert(0, "datetime_utc", merged["datetime_utc"].to_numpy())
    return renamed


def _bottleneck_counts(bottleneck_index, corridor: str) -> dict:
    """
    Given a `bottleneck_index` array (0 for the corridor's first endpoint
    city, 1 for its second, `forecast_training.corridor_weakest_link`'s own
    convention) and `corridor`, return `{city_name: count}` for both
    endpoints -- the per-corridor bottleneck distribution Task 2's report
    extension carries.
    """
    city_a, city_b = config.LEGACY_CORRIDOR_ENDPOINTS[corridor]
    idx = np.asarray(bottleneck_index)
    return {city_a: int(np.sum(idx == 0)), city_b: int(np.sum(idx == 1))}


def corridor_anchored_pair_frame(corridor: str, start=None, end=None, *, lead_hours: int) -> pd.DataFrame:
    """
    Assemble the corridor-level scoring frame for `corridor` at
    `lead_hours`: each endpoint city's own `anchored_pair_frame` is built
    independently (same window, same lead), inner-joined on `datetime_utc`,
    and reduced through `forecast_training.corridor_weakest_link` -- the
    repository's ONE weakest-link reduction (D-03's extraction), never a
    second elementwise-minimum written here.

    The reduction is applied PER COLUMN GROUP AT ITS OWN TIME, not once
    globally:
      - the TRUTH group (`truth_dlr_amps`, at the valid time T) is reduced
        on the two cities' truth ampacities; the accompanying `truth_*`
        weather columns are the LOSING (bottleneck) city's own values.
      - the ANCHOR group (`anchor_dlr_amps`, at T - lead_hours) is reduced
        independently on the two cities' anchor ampacities -- the
        bottleneck city at the anchor time is NOT necessarily the
        bottleneck at the valid time twenty-four hours later; collapsing
        both to one selection would attribute one city's anchor
        observation to the other city's valid-time rating.
      - each of `NON_FITTED_ARMS`' four predictions is reduced
        INDEPENDENTLY again, computed from each city's own per-row weather
        under the SAME corridor geometry (mirroring `forecast_training.
        corridor_training_frame`'s own per-corridor-geometry,
        per-city-weather convention) -- never derived from the truth or
        anchor group's own winning-city selection, since an arm's own
        bottleneck city need not match either of those.
    On an exact ampacity tie in any group, the bottleneck resolves to the
    first endpoint city (`config.LEGACY_CORRIDOR_ENDPOINTS[corridor][0]`), matching
    `corridor_weakest_link`'s own documented tie-break.

    Returns a DataFrame with `datetime_utc`, `anchor_datetime_utc`,
    `hour_mod_remainder`, `truth_dlr_amps`/`bottleneck_index_truth`/winning
    `truth_*` weather, `anchor_dlr_amps`/`bottleneck_index_anchor`/winning
    `anchor_*` weather, `pred_<arm_name>`/`bottleneck_index_<arm_name>` for
    every `NON_FITTED_ARMS` entry, and `nwp_wind_delta_clamped_a`/`_b`
    (per-row booleans recording whether that ENDPOINT city's own pre-clamp
    wind-delta arm input was negative -- `main`'s corridor path sums these
    into the report's visible clamp-hit count).

    Logs a warning naming the corridor and both row counts if the inner
    join on `datetime_utc` drops rows relative to either city's own
    assembled frame -- never silently.
    """
    city_a, city_b = config.LEGACY_CORRIDOR_ENDPOINTS[corridor]
    frame_a = anchored_pair_frame(city_a, start, end, lead_hours=lead_hours)
    frame_b = anchored_pair_frame(city_b, start, end, lead_hours=lead_hours)

    merged = frame_a.merge(frame_b, on="datetime_utc", how="inner", suffixes=("_a", "_b"))
    if len(merged) < min(len(frame_a), len(frame_b)):
        logger.warning(
            "corridor_anchored_pair_frame: inner join for %s dropped rows -- "
            "%s has %d row(s), %s has %d row(s), joined has %d row(s)",
            corridor, city_a, len(frame_a), city_b, len(frame_b), len(merged),
        )

    geometry = legacy_corridor.corridor_geometry(corridor)

    result = pd.DataFrame({"datetime_utc": merged["datetime_utc"]})
    result["anchor_datetime_utc"] = merged["anchor_datetime_utc_a"]
    result["hour_mod_remainder"] = merged["hour_mod_remainder_a"]

    truth_amps, truth_bottleneck, truth_winning = forecast_training.corridor_weakest_link(
        merged["truth_dlr_amps_a"].to_numpy(dtype=float),
        merged["truth_dlr_amps_b"].to_numpy(dtype=float),
        {c: merged[f"{c}_a"].to_numpy(dtype=float) for c in (
            "truth_air_temp", "truth_wind_speed", "truth_wind_direction", "truth_solar_radiation",
        )},
        {c: merged[f"{c}_b"].to_numpy(dtype=float) for c in (
            "truth_air_temp", "truth_wind_speed", "truth_wind_direction", "truth_solar_radiation",
        )},
    )
    result["truth_dlr_amps"] = truth_amps
    result["bottleneck_index_truth"] = truth_bottleneck
    for name, values in truth_winning.items():
        result[name] = values

    anchor_amps, anchor_bottleneck, anchor_winning = forecast_training.corridor_weakest_link(
        merged["anchor_dlr_amps_a"].to_numpy(dtype=float),
        merged["anchor_dlr_amps_b"].to_numpy(dtype=float),
        {c: merged[f"{c}_a"].to_numpy(dtype=float) for c in (
            "anchor_air_temp", "anchor_wind_speed", "anchor_wind_direction", "anchor_solar_radiation",
        )},
        {c: merged[f"{c}_b"].to_numpy(dtype=float) for c in (
            "anchor_air_temp", "anchor_wind_speed", "anchor_wind_direction", "anchor_solar_radiation",
        )},
    )
    result["anchor_dlr_amps"] = anchor_amps
    result["bottleneck_index_anchor"] = anchor_bottleneck
    for name, values in anchor_winning.items():
        result[name] = values

    sub_a = _strip_city_suffix(merged, "_a")
    sub_b = _strip_city_suffix(merged, "_b")

    # Arm 1's clamp visibility, per endpoint city, BEFORE any corridor
    # reduction -- recorded here since sub_a/sub_b (each city's own
    # unsuffixed columns) only exist inside this function.
    result["nwp_wind_delta_clamped_a"] = _nwp_wind_delta_raw_wind_speed(sub_a) < 0.0
    result["nwp_wind_delta_clamped_b"] = _nwp_wind_delta_raw_wind_speed(sub_b) < 0.0

    for arm_name, factory in NON_FITTED_ARMS.items():
        arm_fn = factory(geometry)
        pred_a = np.asarray(arm_fn(sub_a), dtype=float)
        pred_b = np.asarray(arm_fn(sub_b), dtype=float)
        pred_amps, pred_bottleneck, _ = forecast_training.corridor_weakest_link(
            pred_a, pred_b, {}, {},
        )
        result[f"pred_{arm_name}"] = pred_amps
        result[f"bottleneck_index_{arm_name}"] = pred_bottleneck

    return result


# ──────────────────────────────────────────────────────────────────────────
# Plan 03-06 Task 2: the three FITTED arms (D-02 approaches 3, 4, 5).
#
# Unlike NON_FITTED_ARMS' pure factory(geometry) -> callable(frame) shape,
# a fitted arm's callable needs a MODEL fit on real train-plus-validation
# rows before it can predict anything -- `fit_fitted_arms` is the one
# entry point that fits all three, using the configurations Plan 03-05's
# validation selectors already chose (passed in below as WIND_CONFIGURATION/
# COOLING_CONFIGURATION, never re-selected here: re-selecting after the
# test split is unlocked would itself be a configuration decision made
# with more information available than the no-peeking discipline permits).
# ──────────────────────────────────────────────────────────────────────────

FITTED_ARM_NAMES: tuple[str, ...] = (
    "ml_wind_corrected", "ml_cooling_corrected", "reference_ml_refit_24h",
)

# Plan 03-05's validation-selected configurations (03-05-SUMMARY.md
# "Selection Evidence", measured on representative synthetic data --
# that plan's own harness does not fetch real corridor data). Passed into
# fit_fitted_arms as fixed arguments per this task's own instruction; never
# re-selected against real data here.
WIND_CONFIGURATION: dict = {"estimator": "LinearRegression", "pooling": "pooled"}
COOLING_CONFIGURATION: dict = {"estimator": "GradientBoostingRegressor", "target": "log_ratio"}


def _fitted_arm_not_wired_via_registry(arm_name: str):
    """
    Placeholder factory for `ALL_ARMS`' three fitted-arm entries. A fitted
    arm cannot be scored via `factory(geometry) -> callable(frame)` the way
    `NON_FITTED_ARMS`' entries can, because its callable needs a MODEL fit
    on real train-plus-validation rows first. `ALL_ARMS` still carries all
    seven names -- D-02's seven-approach registry is inspectable by length
    and membership without a live fetch or a fit -- but invoking one of
    these three placeholder factories' returned callable raises, naming
    `fit_fitted_arms` as the correct entry point, rather than silently
    returning a callable that would fail confusingly deep inside scoring.
    """

    def factory(geometry):
        def not_ready(frame):
            raise RuntimeError(
                f"forecast_experiment: {arm_name!r} has no callable via "
                f"ALL_ARMS[{arm_name!r}](geometry) -- fitted arms are only "
                f"scoreable through fit_fitted_arms(train_val_frame, "
                f"geometry, wind_configuration=..., cooling_configuration="
                f"...)'s returned fitted objects, never through this "
                f"placeholder"
            )

        return not_ready

    return factory


# The seven-arm registry D-02 commits this phase to (ROADMAP Success
# Criterion 2). The oracle's presence does NOT make it a candidate --
# `corridor_experiment_report` structurally pops it out of any candidate
# mapping derived from this registry, exactly as it does for NON_FITTED_ARMS.
ALL_ARMS: dict = {
    **NON_FITTED_ARMS,
    **{name: _fitted_arm_not_wired_via_registry(name) for name in FITTED_ARM_NAMES},
}


def _add_correction_columns(frame: pd.DataFrame, geometry) -> pd.DataFrame:
    """
    Add the columns `backend/forecast_correction_models.py` expects that
    the anchored-pair-frame contract does not already provide under the
    same name: `truth_ampacity` (an alias of `truth_dlr_amps` -- Plan
    03-05's own module docstring flagged this exact adapter as Plan
    03-06's job) and the perpendicular-projected wind speed for the
    forecast, anchor, and truth groups (`fcst_perp_wind_ms`/
    `anchor_perp_wind_ms`/`truth_perp_wind_ms`), computed via the SAME
    `thermal_model.perpendicular_wind` seam `_city_ampacity` uses, on the
    corridor's own bearing -- never a second wind-projection
    implementation.
    """
    frame = frame.copy()
    frame["truth_ampacity"] = frame["truth_dlr_amps"]
    for prefix in ("fcst", "anchor", "truth"):
        frame[f"{prefix}_perp_wind_ms"] = thermal_model.perpendicular_wind(
            frame[f"{prefix}_wind_speed"].to_numpy(dtype=float),
            frame[f"{prefix}_wind_direction"].to_numpy(dtype=float),
            geometry.bearing_deg,
        )
    return frame


def _wind_corrected_ampacity(
    model: "forecast_correction_models.WindCorrectionModel", frame: pd.DataFrame, geometry,
) -> np.ndarray:
    """
    Arm 3's live prediction: `forecast_correction_models.
    predict_wind_correction` corrects the forecast's own wind, then the
    corrected wind is projected and run through the SAME `_city_ampacity`
    physics seam every other arm uses. Genuinely re-reads `frame`'s own
    `fcst_*`/`anchor_*` columns on every call (never a cached lookup by
    timestamp) -- the leakage probe's power depends on this arm actually
    recomputing from whatever frame it is given.
    """
    prediction = forecast_correction_models.predict_wind_correction(model, frame)
    perp = thermal_model.perpendicular_wind(
        prediction.speed, prediction.direction, geometry.bearing_deg,
    )
    return np.asarray(
        thermal_model.ieee738_ampacity(
            frame["fcst_air_temp"].to_numpy(dtype=float), perp,
            frame["fcst_solar_radiation"].to_numpy(dtype=float), geometry.conductor,
        ),
        dtype=float,
    )


def _cooling_corrected_ampacity(
    model: "forecast_correction_models.CoolingCorrectionModel", frame: pd.DataFrame, geometry,
) -> np.ndarray:
    """
    Arm 4's live prediction: `forecast_correction_models.
    predict_cooling_correction` corrects the convective term, substituted
    back through `thermal_model.ieee738_ampacity`'s `q_conv_override` seam
    via `apply_cooling_correction` -- never a second heat-balance
    implementation. Requires `frame` to already carry the `fcst_perp_
    wind_ms`/`anchor_perp_wind_ms` columns `_add_correction_columns` adds;
    genuinely re-reads them on every call, for the same leakage-probe-power
    reason `_wind_corrected_ampacity` does.
    """
    prediction = forecast_correction_models.predict_cooling_correction(model, frame)
    return np.asarray(
        forecast_correction_models.apply_cooling_correction(frame, prediction.q_conv, geometry),
        dtype=float,
    )


def _stacked_pair_frame(corridor: str, start=None, end=None, *, lead_hours: int) -> pd.DataFrame:
    """
    Assemble both endpoint cities' `anchored_pair_frame`s and STACK them
    (concatenate, tag `endpoint_city`) rather than corridor-reduce them.
    Arms 3 and 4 fit `pooled` (one model over both cities, with an
    endpoint indicator) or `per_city` (one model per city) -- both need
    each city's own individual weather/wind rows side by side, which the
    corridor-reduced single-row-per-timestamp shape
    `corridor_anchored_pair_frame` returns does not preserve. UNFILTERED
    with respect to lead (every hour, not just the exact-24h-lead subset)
    -- arm 5's own truth-only reduction (`_arm5_truth_frame`) needs a
    genuine hourly cadence for its lag features; callers that need arms 3
    or 4's exact-lead invariant apply `filter_to_exact_lead` themselves.
    """
    city_a, city_b = config.LEGACY_CORRIDOR_ENDPOINTS[corridor]
    frame_a = anchored_pair_frame(city_a, start, end, lead_hours=lead_hours).copy()
    frame_a["endpoint_city"] = city_a
    frame_b = anchored_pair_frame(city_b, start, end, lead_hours=lead_hours).copy()
    frame_b["endpoint_city"] = city_b
    return (
        pd.concat([frame_a, frame_b], ignore_index=True)
        .sort_values("datetime_utc")
        .reset_index(drop=True)
    )


def _arm5_truth_frame(stacked_frame: pd.DataFrame, city_a: str, city_b: str) -> pd.DataFrame:
    """
    Reduce a stacked (endpoint_city-tagged) two-city TRUTH series into one
    corridor-level frame shaped for `forecast_training.
    build_training_matrix`: `datetime_utc`, `dlr_amps`, `air_temp`,
    `wind_speed`, `solar_radiation`. Arm 5 never sees `fcst_*`/`anchor_*`
    at all -- it is refit purely on the corridor's own archived TRUTH
    series, weakest-link-reduced via `forecast_training.
    corridor_weakest_link` (the repository's one reduction), exactly the
    way the production trainer builds its own corridor series.
    """
    a = stacked_frame[stacked_frame["endpoint_city"] == city_a].sort_values("datetime_utc").reset_index(drop=True)
    b = stacked_frame[stacked_frame["endpoint_city"] == city_b].sort_values("datetime_utc").reset_index(drop=True)
    merged = a.merge(b, on="datetime_utc", suffixes=("_a", "_b"))

    truth_columns = ("truth_air_temp", "truth_wind_speed", "truth_solar_radiation")
    dlr_amps, _, winning = forecast_training.corridor_weakest_link(
        merged["truth_dlr_amps_a"].to_numpy(dtype=float),
        merged["truth_dlr_amps_b"].to_numpy(dtype=float),
        {c: merged[f"{c}_a"].to_numpy(dtype=float) for c in truth_columns},
        {c: merged[f"{c}_b"].to_numpy(dtype=float) for c in truth_columns},
    )

    return pd.DataFrame({
        "datetime_utc": merged["datetime_utc"],
        "dlr_amps": dlr_amps,
        "air_temp": winning["truth_air_temp"],
        "wind_speed": winning["truth_wind_speed"],
        "solar_radiation": winning["truth_solar_radiation"],
    }).sort_values("datetime_utc").reset_index(drop=True)


def fit_fitted_arms(
    train_val_frame: pd.DataFrame, geometry, *, wind_configuration: dict, cooling_configuration: dict,
) -> dict:
    """
    Fit arms 3 (`ml_wind_corrected`), 4 (`ml_cooling_corrected`) and 5
    (`reference_ml_refit_24h`) on `train_val_frame` -- a STACKED,
    per-city, UNFILTERED anchored-pair frame (`_stacked_pair_frame`'s
    shape) spanning the train-plus-validation calendar range.

    Arms 3 and 4 fit ONLY on the exact-24h-lead subset
    (`filter_to_exact_lead`) of `train_val_frame` -- fitting on the
    broader 24-29h-lead-smeared rows would blend inconsistent lead
    semantics into the correction, the same risk 03-RESEARCH.md Pitfall 1
    warns against for SCORING.

    Arm 5 never sees `fcst_*`/`anchor_*` at all: its feature and target
    matrices come from `forecast_training.build_training_matrix` at an
    explicit `horizon_minutes=1440`, applied to `train_val_frame`'s own
    weakest-link-reduced TRUTH series (`_arm5_truth_frame`) -- full hourly
    cadence, never the exact-lead-filtered subset, since its lag features
    need genuine hour-to-hour spacing. It is fit with `forecast_training.
    CANDIDATE_ESTIMATORS["MLPRegressor"]` (the SAME estimator family
    `forecasting_model.md` persisted as the production winner) via
    `forecast_training.fit_corridor_model` -- which only calls
    `estimator.fit(...)`, never `persist_corridor_model` and never
    anything in `ampacity_forecast`, so arm 5 can never reach the
    persisted production artifact, the runtime module's per-corridor
    model loader, or its process-global model cache.

    `wind_configuration`/`cooling_configuration` are Plan 03-05's
    validation-selected (estimator, pooling)/(estimator, target) pairs,
    passed in rather than re-selected here (see this module's
    `WIND_CONFIGURATION`/`COOLING_CONFIGURATION`).

    Returns:
        `{"wind_model": WindCorrectionModel, "cooling_model":
        CoolingCorrectionModel, "arm5_estimator": a fitted scikit-learn
        estimator, "wind_configuration": dict, "cooling_configuration":
        dict}`.

    Raises:
        ValueError: naming the found cities, if `train_val_frame` does not
            carry exactly two distinct `endpoint_city` values.
    """
    lead_hours = config.FORECAST_EXPERIMENT_PRIMARY_LEAD_HOURS
    cities = sorted(train_val_frame["endpoint_city"].unique())
    if len(cities) != 2:
        raise ValueError(
            f"fit_fitted_arms: train_val_frame must carry exactly two "
            f"endpoint_city values, found {cities!r}"
        )
    city_a, city_b = cities

    exact_lead = filter_to_exact_lead(train_val_frame, lead_hours=lead_hours)
    exact_lead = _add_correction_columns(exact_lead, geometry)

    wind_model = forecast_correction_models.fit_wind_correction(
        exact_lead,
        forecast_correction_models.WIND_CORRECTION_ESTIMATORS[wind_configuration["estimator"]],
        pooling=wind_configuration["pooling"],
    )
    cooling_model = forecast_correction_models.fit_cooling_correction(
        exact_lead,
        forecast_correction_models.COOLING_CORRECTION_ESTIMATORS[cooling_configuration["estimator"]],
        target=cooling_configuration["target"], conductor=geometry.conductor,
    )

    arm5_frame = _arm5_truth_frame(train_val_frame, city_a, city_b)
    X5, y5 = forecast_training.build_training_matrix(arm5_frame, horizon_minutes=1440)
    arm5_estimator = forecast_training.fit_corridor_model(
        X5, y5, forecast_training.CANDIDATE_ESTIMATORS["MLPRegressor"]()
    )

    return {
        "wind_model": wind_model,
        "cooling_model": cooling_model,
        "arm5_estimator": arm5_estimator,
        "wind_configuration": dict(wind_configuration),
        "cooling_configuration": dict(cooling_configuration),
    }


def leakage_probe(scored_frame: pd.DataFrame, arms: dict) -> dict:
    """
    ROADMAP Success Criterion 3's measurement, not inspection: proves that
    no arm's prediction depends on any value timestamped at or after its
    own valid time. Builds a sabotaged copy of `scored_frame` in which
    every column whose name marks it as a truth value AT THE VALID TIME
    (every column starting with `truth_`) is overwritten with a sentinel
    that is in-range but physically wrong -- a constant well inside the
    schema bounds, chosen so any arm actually reading it would produce a
    visibly different number -- then runs every `arms` callable against
    both the original and the sabotaged frame and compares elementwise.

    `arms` must be a mapping of arm name to a LIVE-RECOMPUTING callable
    (one that genuinely reads `scored_frame`'s own columns on every call,
    like `NON_FITTED_ARMS`' factories or `_wind_corrected_ampacity`/
    `_cooling_corrected_ampacity`) -- a callable that looks up a
    precomputed prediction by timestamp would trivially (and
    meaninglessly) report no change regardless of sabotage.

    This detects a DIRECT read of a truth column at the valid time. It
    does NOT detect a leak through a fitted model that was trained on
    test rows -- that failure mode is covered separately by arm 5's
    from-scratch refit and by `assert_filtered_split_disjoint`.

    Returns:
        `{arm_name: {"changed": bool, "max_abs_change": float}}` -- the
        max absolute change surfaces a PARTIAL dependency as a small
        nonzero value rather than rounding it away into a boolean.
    """
    sentinels = {
        "truth_air_temp": 15.0,
        "truth_wind_speed": 1.0,
        "truth_wind_direction": 200.0,
        "truth_solar_radiation": 50.0,
        "truth_relative_humidity": 40.0,
        "truth_dlr_amps": 1000.0,
        "truth_ampacity": 1000.0,
        "truth_perp_wind_ms": 1.0,
    }
    truth_columns = [c for c in scored_frame.columns if c.startswith("truth_")]

    sabotaged = scored_frame.copy()
    for column in truth_columns:
        sabotaged[column] = sentinels.get(column, 1.0)

    result = {}
    for name, fn in arms.items():
        original_pred = np.asarray(fn(scored_frame), dtype=float)
        sabotaged_pred = np.asarray(fn(sabotaged), dtype=float)
        diff = np.abs(original_pred - sabotaged_pred)
        result[name] = {
            "changed": bool(np.any(diff > 1e-9)),
            "max_abs_change": float(np.max(diff)) if diff.size else 0.0,
        }
    return result


def _corridor_arm_reader(arm_name: str):
    """
    A `score_arms`-compatible callable reading `corridor_anchored_pair_
    frame`'s already-reduced `pred_<arm_name>` column -- corridor-level arm
    predictions are computed ONCE, per-city, inside `corridor_anchored_pair_
    frame` itself (each arm needs each city's OWN weather columns before
    reduction, which a post-hoc frame no longer carries), so the callable
    passed to `score_arms` for the corridor path is a column read, not a
    recomputation through `_city_ampacity`.
    """
    column = f"pred_{arm_name}"

    def reader(frame: pd.DataFrame) -> np.ndarray:
        return frame[column].to_numpy(dtype=float)

    return reader


def assert_identical_index(test_frame: pd.DataFrame, arms: dict) -> dict:
    """
    Called by `score_arms` BEFORE any arm's prediction is actually scored
    (Task 3): the automated enforcement of D-02's single load-bearing claim
    -- "identical held-out chronological test timestamps" -- turned into an
    exception rather than a property that merely happens to hold.

    Asserts `test_frame`'s index is unique and sorted, then computes every
    arm's prediction length up front and raises `ValueError` the moment ANY
    TWO arms disagree, naming BOTH arm names and BOTH their counts --
    stronger than comparing each arm only to `test_frame`'s own length one
    at a time, which can only ever name a single arm. Only after every pair
    agrees does it check the shared length against `test_frame` itself
    (still naming the one arm and both counts if that fails, e.g. every
    arm agrees with each other but not with `test_frame`).

    Returns:
        `{"rows": int, "first_timestamp": str, "last_timestamp": str}` --
        the scored index's own shape and span. Timestamps are included only
        when `test_frame` carries a `datetime_utc` column. Merged into
        `score_arms`'s returned mapping (outside `candidates`) so the
        identical-index claim is INSPECTABLE from the report, not merely
        enforced silently.
    """
    if not test_frame.index.is_unique:
        raise ValueError("assert_identical_index: test_frame index is not unique")
    if not test_frame.index.is_monotonic_increasing:
        raise ValueError("assert_identical_index: test_frame index is not sorted")

    n = len(test_frame)
    lengths = {name: len(np.asarray(fn(test_frame))) for name, fn in arms.items()}

    names = list(lengths)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            arm_a, arm_b = names[i], names[j]
            if lengths[arm_a] != lengths[arm_b]:
                raise ValueError(
                    f"assert_identical_index: arm {arm_a!r} scored "
                    f"{lengths[arm_a]} row(s) while arm {arm_b!r} scored "
                    f"{lengths[arm_b]} row(s) -- every arm in this phase's "
                    f"comparison MUST share one identical row index (D-02's "
                    f"'identical held-out chronological test timestamps')"
                )
    for name, length in lengths.items():
        if length != n:
            raise ValueError(
                f"assert_identical_index: arm {name!r} returned {length} "
                f"prediction(s), expected {n} (test_frame's row count)"
            )

    index_info = {"rows": int(n)}
    if "datetime_utc" in test_frame.columns:
        index_info["first_timestamp"] = str(test_frame["datetime_utc"].min())
        index_info["last_timestamp"] = str(test_frame["datetime_utc"].max())
    return index_info


def paired_bootstrap_margin(errors_arm, errors_baseline) -> dict:
    """
    Plan 03-06 Task 3: a paired bootstrap confidence interval on an arm's
    margin against a baseline (persistence, throughout this phase), over
    the per-row ABSOLUTE-error difference series -- not two independently
    resampled error series. Every arm in this phase's comparison scores on
    one byte-identical held-out row index by construction
    (`assert_identical_index`), so `errors_arm[i]` and `errors_baseline[i]`
    are genuinely the SAME row's two residuals; resampling the paired
    DIFFERENCE preserves that correspondence, while resampling the two
    series independently would discard it and widen every interval for no
    reason.

    `errors_arm`/`errors_baseline` are raw residuals (actual - predicted),
    the SAME shape `score_arms` already computes per arm -- this function
    takes their absolute value itself, so a caller never has to remember
    to.

    The point margin is `mean(|errors_baseline|) - mean(|errors_arm|)`:
    positive means the arm's mean absolute error is LOWER than the
    baseline's (a margin favouring the arm). The confidence interval comes
    from `scipy.stats.bootstrap` on the mean of the per-row difference
    series `|errors_baseline| - |errors_arm|`, using
    `config.FORECAST_EXPERIMENT_BOOTSTRAP_RESAMPLES` resamples at
    `config.FORECAST_EXPERIMENT_BOOTSTRAP_CONFIDENCE` confidence, with a
    FIXED random state (`config.FORECAST_EXPERIMENT_CORRECTION_RANDOM_
    STATE` -- this phase's one existing fixed seed; no second bootstrap-
    specific seed constant exists in `config.py`, and this task's own
    `<read_first>` says read that module, not edit it) so the interval is
    exactly reproducible from the same two residual arrays.

    An interval excluding zero is STATISTICAL significance, not PRACTICAL
    significance: a margin of a few amps on a rating in the hundreds can
    have an interval that excludes zero at this phase's sample size
    without being large enough, on its own, to justify replacing
    persistence in production -- see the decision record's Expectation
    section for the amperes-scale practical-significance threshold this
    distinction exists for.

    A degenerate (zero-variance) difference series -- most notably the
    baseline scored against ITSELF, where every difference is exactly
    zero -- is handled directly rather than handed to `scipy.stats.
    bootstrap`: `scipy`'s default `BCa` method cannot compute an
    acceleration parameter on degenerate data and returns `NaN` bounds
    (confirmed empirically, not assumed), which would make every
    downstream `ci_low <= point <= ci_high` assertion fail on exactly the
    baseline-vs-itself entry every candidate mapping carries.

    Returns:
        `{"point": float, "ci_low": float, "ci_high": float,
        "excludes_zero_favorably": bool}` -- the last key is `True` only
        when `ci_low > 0.0` (the ENTIRE interval favours the arm).

    Raises:
        ValueError: naming both shapes, if `errors_arm` and
            `errors_baseline` are not the same length.
    """
    abs_arm = np.abs(np.asarray(errors_arm, dtype=float))
    abs_baseline = np.abs(np.asarray(errors_baseline, dtype=float))
    if abs_arm.shape != abs_baseline.shape:
        raise ValueError(
            f"paired_bootstrap_margin: errors_arm has shape {abs_arm.shape} "
            f"but errors_baseline has shape {abs_baseline.shape} -- both "
            f"must be scored on the identical row index"
        )

    diff = abs_baseline - abs_arm
    point = float(np.mean(diff)) if diff.size else 0.0

    if diff.size == 0 or np.ptp(diff) == 0.0:
        # Degenerate: every row's difference is identical (typically all
        # zero, the baseline scored against itself). The interval collapses
        # to the point value -- no resampling can produce a different
        # number from constant data, and scipy's BCa method returns NaN
        # here rather than the mathematically correct degenerate answer.
        return {
            "point": point,
            "ci_low": point,
            "ci_high": point,
            "excludes_zero_favorably": bool(point > 0.0),
        }

    result = scipy.stats.bootstrap(
        (diff,), np.mean,
        n_resamples=config.FORECAST_EXPERIMENT_BOOTSTRAP_RESAMPLES,
        confidence_level=config.FORECAST_EXPERIMENT_BOOTSTRAP_CONFIDENCE,
        random_state=config.FORECAST_EXPERIMENT_CORRECTION_RANDOM_STATE,
        method="BCa",
    )
    ci_low = float(result.confidence_interval.low)
    ci_high = float(result.confidence_interval.high)
    return {
        "point": point,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "excludes_zero_favorably": bool(ci_low > 0.0),
    }


def score_arms(test_frame: pd.DataFrame, arms: dict, *, baseline_name: str | None = None) -> dict:
    """
    Score every callable in `arms` (mapping of arm name -> a callable
    taking `test_frame` and returning a prediction array) against
    `test_frame["truth_dlr_amps"]`.

    Calls `assert_identical_index` FIRST, before any arm's prediction is
    scored -- the automated enforcement of the identical-row-index claim
    this phase's whole design rests on, extended (Task 3) to name BOTH
    arms and BOTH counts when any two arms disagree with each other, not
    only when one disagrees with `test_frame`'s own length.

    `baseline_name` (Plan 03-06 Task 3, additive, default `None` -- every
    pre-existing caller's behavior is byte-identical to before this
    parameter existed): when given, every OTHER arm's entry in
    `candidates` gains a `margin_vs_persistence` key
    (`paired_bootstrap_margin`'s return value) computed against
    `baseline_name`'s own residuals on this SAME call's identical index --
    including `baseline_name`'s own entry, scored against itself
    (trivially a zero-width interval at zero), so a caller iterating
    `candidates` never has to special-case the one entry missing the key.

    Returns:
        `{"candidates": {arm_name: {"mae", "rmse", "rows"[, "margin_vs_
        persistence"]}}, "test_index": [the exact index values scored, as
        a list], "rows": int, "first_timestamp": str, "last_timestamp":
        str}` -- `test_index` and the index-shape fields are kept OUTSIDE
        `candidates` so `report["candidates"]` (this function's
        `candidates` value) stays a clean per-arm score mapping, matching
        `forecast_training.corridor_report`'s own `candidates` shape.

    Raises:
        ValueError: naming `baseline_name` and the scored arm names, if
            `baseline_name` is given but is not among `arms`.
    """
    index_info = assert_identical_index(test_frame, arms)

    actual = test_frame["truth_dlr_amps"].to_numpy(dtype=float)
    n = len(test_frame)

    residuals = {}
    candidates = {}
    for name, fn in arms.items():
        pred = np.asarray(fn(test_frame), dtype=float)
        residual = actual - pred
        residuals[name] = residual
        candidates[name] = {
            "mae": float(np.mean(np.abs(residual))),
            "rmse": float(np.sqrt(np.mean(residual ** 2))),
            "rows": int(n),
        }

    if baseline_name is not None:
        if baseline_name not in residuals:
            raise ValueError(
                f"score_arms: baseline_name {baseline_name!r} is not "
                f"among the scored arms {sorted(residuals)}"
            )
        baseline_residual = residuals[baseline_name]
        for name, residual in residuals.items():
            candidates[name]["margin_vs_persistence"] = paired_bootstrap_margin(
                residual, baseline_residual,
            )

    return {
        "candidates": candidates,
        "test_index": list(test_frame.index),
        **index_info,
    }


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


def assert_filtered_split_disjoint(
    train_filtered: pd.DataFrame, val_filtered: pd.DataFrame, test_filtered: pd.DataFrame,
) -> None:
    """
    Raise `ValueError` naming the overlapping timestamps when the FILTERED
    train/val/test frames -- the ones actually scored, AFTER `filter_to_
    exact_lead`, not the frames `experiment_splits.calendar_split` itself
    received -- are not strictly chronologically disjoint: every train
    timestamp strictly before every validation timestamp, and every
    validation timestamp strictly before every test timestamp (Task 3).

    `calendar_split` is already tested on its own unfiltered contract
    (`experiment_splits_test.py`'s own ordering assertions) -- this
    function does not re-derive that; it asserts the SAME property holds
    on the subset this module actually scores, since the six-hourly filter
    is applied per-side, independently, and a mismatched filter or a
    boundary miscalculation could in principle desynchronize the two
    without either side's own internal ordering ever breaking.

    Reading test's own timestamps here (never its `truth_dlr_amps` or any
    other value) is NOT a no-peeking violation -- it is calendar-boundary
    arithmetic identical in kind to what `_default_split_boundaries`
    already computes over the full frame; no target value is read.
    """
    if len(train_filtered) and len(val_filtered):
        train_max = train_filtered["datetime_utc"].max()
        val_min = val_filtered["datetime_utc"].min()
        if not (train_max < val_min):
            raise ValueError(
                f"assert_filtered_split_disjoint: filtered TRAIN max "
                f"timestamp {train_max} is not strictly before filtered "
                f"VAL min timestamp {val_min} -- the filter and/or split "
                f"boundaries have desynchronized on the frame actually "
                f"scored"
            )
    if len(val_filtered) and len(test_filtered):
        val_max = val_filtered["datetime_utc"].max()
        test_min = test_filtered["datetime_utc"].min()
        if not (val_max < test_min):
            raise ValueError(
                f"assert_filtered_split_disjoint: filtered VAL max "
                f"timestamp {val_max} is not strictly before filtered "
                f"TEST min timestamp {test_min} -- the filter and/or split "
                f"boundaries have desynchronized on the frame actually "
                f"scored"
            )


# Plan 03-06 Task 3's plainly-worded null-result verdict value, per D-02's
# explicit commitment: the record states this outcome the same way every
# time, never reframed as a near-miss or a partial win. A shared module
# constant so `corridor_experiment_report` and every caller/test that
# checks for this outcome compare against one string, never a
# re-typed literal that could silently drift.
NO_CANDIDATE_BEAT_PERSISTENCE_VERDICT: str = "no candidate beat persistence"


def _resolve_verdict(candidates: dict, baseline_name: str) -> str:
    """
    Plan 03-06 Task 3's three-valued verdict, resolved from `candidates`'
    (already oracle-popped) `margin_vs_persistence` entries:

    - `NO_CANDIDATE_BEAT_PERSISTENCE_VERDICT` when no candidate other than
      `baseline_name` itself has an interval excluding zero favourably --
      D-02's explicit commitment to reporting this outcome plainly.
    - the single winning arm's bare name when exactly one candidate's
      interval excludes zero favourably.
    - an explicit, self-describing multiple-candidates string, naming
      every beating candidate and its point margin, when more than one
      does -- resolved to the largest point margin, with an exact tie at
      the top recorded in the string rather than silently broken.

    `baseline_name` itself is never a candidate winner (its own margin
    against itself is the degenerate zero-width interval at zero) -- this
    function does not need to special-case it beyond excluding it from
    consideration, since its own entry can never satisfy
    `excludes_zero_favorably`.
    """
    winners = [
        (name, entry["margin_vs_persistence"]["point"])
        for name, entry in candidates.items()
        if name != baseline_name
        and "margin_vs_persistence" in entry
        and entry["margin_vs_persistence"]["excludes_zero_favorably"]
    ]
    if not winners:
        return NO_CANDIDATE_BEAT_PERSISTENCE_VERDICT
    if len(winners) == 1:
        return winners[0][0]

    best_margin = max(margin for _, margin in winners)
    tied_at_top = sorted(name for name, margin in winners if margin == best_margin)
    resolved = tied_at_top[0]
    ranked = ", ".join(
        f"{name} ({margin:.3f})" for name, margin in sorted(winners, key=lambda p: p[1], reverse=True)
    )
    tie_note = (
        f"; tied at the top margin with {tied_at_top[1:]!r}, resolved to "
        f"{resolved!r} by name order" if len(tied_at_top) > 1 else ""
    )
    return (
        f"multiple candidates beat persistence ({ranked}); resolved to "
        f"{resolved!r} by largest point margin ({best_margin:.3f}){tie_note}"
    )


def corridor_experiment_report(
    label, start, end, assembled_frame, filtered_frame, boundaries, scored,
    *, lead_hours: int, split: str = "val", bottleneck_distribution: dict | None = None,
    nwp_wind_delta_clamp_count: int | None = None, id_key: str = "city",
    baseline_name: str | None = None,
) -> dict:
    """
    Assemble the report mapping: `label` under `id_key` (`"city"` for Plan
    03-03's single-city tracer path, `"corridor"` for Plan 03-04's
    corridor-level path -- same function, the key name records which), the
    window start and end, the assembled and scored row counts, the split
    boundaries, the ACTUAL `lead_hours` (never a hardcoded value -- exact by
    construction of `filter_to_exact_lead`, which only ever passes through
    rows whose anchor gap matches this value), the caveat and filter
    remainder that match THIS lead (`_lead_source_config(lead_hours)`,
    never the other lead's), the split side actually scored, the
    per-corridor bottleneck distribution and arm 1's clamp-hit count when
    supplied, and the per-arm scores.

    STRUCTURAL ORACLE ISOLATION (T-03-04-02): if `scored["candidates"]`
    contains `ORACLE_ARM_NAME`, this function ALWAYS pops it out of the
    emitted `candidates` mapping into its own top-level `oracle_diagnostic`
    key (with an attached non-forecast statement) -- regardless of whether
    the caller remembered to exclude it. The isolation is a property of
    THIS FUNCTION, not caller discipline: any later winner-selection step
    iterating `report["candidates"]` structurally cannot reach the oracle
    (ROADMAP Success Criterion 2).

    `baseline_name` (Plan 03-06 Task 3, additive, default `None` -- every
    pre-existing caller's behavior and emitted report shape is byte-
    identical to before this parameter existed): when given, this
    function ALSO attaches a top-level `"verdict"` key
    (`_resolve_verdict`'s return value) resolved from `candidates`'
    `margin_vs_persistence` entries -- `score_arms` must have been called
    with the matching `baseline_name` for those entries to exist.
    """
    lead_cfg = _lead_source_config(lead_hours)
    candidates = dict(scored["candidates"])
    oracle_entry = candidates.pop(ORACLE_ARM_NAME, None)

    report = {
        id_key: label,
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
        "split": split,
        "candidates": candidates,
    }

    if oracle_entry is not None:
        report["oracle_diagnostic"] = {
            "score": oracle_entry,
            "statement": (
                "This substitutes OBSERVED FUTURE wind into the forecast's "
                "thermal inputs -- it is NOT a forecast, no real system "
                "could ever have had this input, and it must never be "
                "compared against persistence or any candidate as though "
                "it were a competing method. It bounds the maximum benefit "
                "any wind correction could ever achieve."
            ),
        }
    if bottleneck_distribution is not None:
        report["bottleneck_distribution"] = bottleneck_distribution
    if nwp_wind_delta_clamp_count is not None:
        report["nwp_wind_delta_clamp_count"] = nwp_wind_delta_clamp_count
    if baseline_name is not None:
        report["verdict"] = _resolve_verdict(candidates, baseline_name)

    return report


def _run_city_tracer(city, start, end, lead_hours, lead_cfg):
    """
    Plan 03-03's single-city tracer path, UNCHANGED: assemble one city's
    anchored pair frame, score `persistence`/`raw_forecast` (never the
    full `NON_FITTED_ARMS` registry -- this path predates it and Plan
    03-03's live gate depends on its exact output shape), and write a
    per-city JSON report. Kept working verbatim so Plan 03-03's own
    live-network gate is never broken by this plan's corridor-level
    addition.
    """
    frame = anchored_pair_frame(city, start, end, lead_hours=lead_hours)
    assert_exact_lead(frame, lead_hours=lead_hours)

    boundaries = _default_split_boundaries(frame)
    train, val, test = experiment_splits.calendar_split(frame, boundaries)

    # Task 3: assert the FILTERED train/val/test frames -- the ones
    # actually scored, after filter_to_exact_lead -- are still strictly
    # chronologically disjoint, not only the unfiltered frames
    # calendar_split itself received. Reads only test's own timestamps,
    # never its truth values -- calendar-boundary arithmetic, not a
    # no-peeking violation.
    train_filtered = filter_to_exact_lead(train, lead_hours=lead_hours)
    val_scored = filter_to_exact_lead(val, lead_hours=lead_hours)
    test_filtered = filter_to_exact_lead(test, lead_hours=lead_hours)
    assert_filtered_split_disjoint(train_filtered, val_scored, test_filtered)

    # Success Criterion 5's no-peeking discipline: this path scores the
    # VALIDATION split only. The guard call below is a no-op for "val" --
    # it documents, in the code path itself, that a future change routing
    # this call through "test" would be mechanically refused while
    # _TEST_SPLIT_UNLOCKED is False.
    _guard_test_split_access("val")
    assert_exact_lead(val_scored, lead_hours=lead_hours)

    geometry = legacy_corridor.corridor_geometry(_corridor_for_city(city))

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


def _fitted_arm_city_frame(stacked_frame: pd.DataFrame, city: str, boundaries, split: str, *, lead_hours: int) -> pd.DataFrame:
    """
    Plan 03-06 Task 3: `city`'s own exact-lead-filtered rows for `split`
    ('val' or 'test'), sliced from `stacked_frame` (this module's
    `_stacked_pair_frame` shape) using the SAME `boundaries` the
    corridor-level split used -- so arms 3/4's per-city scoring frame is
    split on the identical calendar dates the corridor-level candidates
    were reduced from, never a re-derived boundary that could drift from
    it.
    """
    city_frame = (
        stacked_frame[stacked_frame["endpoint_city"] == city]
        .sort_values("datetime_utc").reset_index(drop=True)
    )
    _train, val_side, test_side = experiment_splits.calendar_split(city_frame, boundaries)
    side = {"val": val_side, "test": test_side}[split]
    return filter_to_exact_lead(side, lead_hours=lead_hours)


def _merge_prediction_to_scored_index(scored_frame: pd.DataFrame, datetimes_a, pred_a, datetimes_b, pred_b) -> tuple:
    """
    Plan 03-06 Task 3: align two cities' own per-row predictions
    (`datetimes_a`/`pred_a`, `datetimes_b`/`pred_b`) onto `scored_frame`'s
    own `datetime_utc` index by timestamp, then reduce them through
    `forecast_training.corridor_weakest_link` -- the repository's ONE
    weakest-link reduction, the SAME one `corridor_anchored_pair_frame`
    uses for the four non-fitted arms. Each city's own frame may carry
    timestamps beyond `scored_frame`'s own set (its own `anchored_pair_
    frame` predates the corridor-level inner join); alignment is by
    explicit reindex onto `scored_frame`'s timestamps, never by raw
    positional concatenation, so a length coincidence can never silently
    pair the wrong rows.

    Raises:
        ValueError: naming the missing timestamp count on whichever side
            is short, if either city's own predictions do not cover every
            timestamp `scored_frame` needs.
    """
    target_index = pd.DatetimeIndex(pd.to_datetime(scored_frame["datetime_utc"], utc=True))
    series_a = pd.Series(
        np.asarray(pred_a, dtype=float),
        index=pd.DatetimeIndex(pd.to_datetime(datetimes_a, utc=True)),
    )
    series_b = pd.Series(
        np.asarray(pred_b, dtype=float),
        index=pd.DatetimeIndex(pd.to_datetime(datetimes_b, utc=True)),
    )
    aligned_a = series_a.reindex(target_index)
    aligned_b = series_b.reindex(target_index)
    if aligned_a.isna().any() or aligned_b.isna().any():
        missing_a = target_index[aligned_a.isna()]
        missing_b = target_index[aligned_b.isna()]
        raise ValueError(
            f"_merge_prediction_to_scored_index: {len(missing_a)} "
            f"timestamp(s) missing from city A's prediction "
            f"(e.g. {list(missing_a[:3])}), {len(missing_b)} missing from "
            f"city B's (e.g. {list(missing_b[:3])}) -- the corridor-level "
            f"scored index is not fully covered by both cities' own "
            f"per-city predictions"
        )
    reduced, bottleneck, _ = forecast_training.corridor_weakest_link(
        aligned_a.to_numpy(dtype=float), aligned_b.to_numpy(dtype=float), {}, {},
    )
    return reduced, bottleneck


def _score_fitted_arms_at_corridor_level(
    stacked_full: pd.DataFrame, boundaries, split: str, scored_frame: pd.DataFrame, geometry, fitted: dict,
    *, lead_hours: int,
) -> pd.DataFrame:
    """
    Plan 03-06 Task 3: compute arms 3 (`ml_wind_corrected`), 4
    (`ml_cooling_corrected`) and 5 (`reference_ml_refit_24h`)'s
    corridor-level predictions for `split` ('val' or 'test') and attach
    them to a COPY of `scored_frame` as `pred_<arm_name>` columns, on the
    SAME `datetime_utc` index `scored_frame` already carries -- so
    `_corridor_arm_reader` can read all seven `ALL_ARMS` entries
    uniformly and `score_arms`'s identical-index assertion holds by
    construction, not by coincidence.

    Arms 3/4 are corrected PER CITY (Plan 03-05's correction models are
    fit pooled-with-an-endpoint-indicator or per-city, on each city's own
    weather rows), so each city's own corrected ampacity is computed
    independently via `_wind_corrected_ampacity`/`_cooling_corrected_
    ampacity` and reduced through the SAME `forecast_training.
    corridor_weakest_link` helper `corridor_anchored_pair_frame` uses for
    the four non-fitted arms (`_merge_prediction_to_scored_index`).

    Arm 5 is fit AND scored purely from the corridor's own weakest-link-
    reduced TRUTH series (`_arm5_truth_frame`) -- its prediction is
    already corridor-level by construction, with no further per-city
    reduction needed. Its FEATURES are rebuilt here from `stacked_full`
    (the FULL train+val+test window), not the train-plus-validation frame
    `fitted["arm5_estimator"]` was FIT on -- a fresh feature build is
    needed so lag features exist at `split`'s own anchor times; only the
    fitted ESTIMATOR itself (never re-fit here) came from train+val. This
    is not a leak: every scored row's own features are built from truth
    values strictly BEFORE that row's own valid time (the anchor time is
    `lead_hours` earlier), and the estimator's learned weights never saw a
    train/val-excluded row during fitting.
    """
    city_a, city_b = sorted(stacked_full["endpoint_city"].unique())

    city_a_frame = _add_correction_columns(
        _fitted_arm_city_frame(stacked_full, city_a, boundaries, split, lead_hours=lead_hours), geometry,
    )
    city_b_frame = _add_correction_columns(
        _fitted_arm_city_frame(stacked_full, city_b, boundaries, split, lead_hours=lead_hours), geometry,
    )

    wind_pred_a = _wind_corrected_ampacity(fitted["wind_model"], city_a_frame, geometry)
    wind_pred_b = _wind_corrected_ampacity(fitted["wind_model"], city_b_frame, geometry)
    wind_reduced, wind_bottleneck = _merge_prediction_to_scored_index(
        scored_frame, city_a_frame["datetime_utc"], wind_pred_a, city_b_frame["datetime_utc"], wind_pred_b,
    )

    cooling_pred_a = _cooling_corrected_ampacity(fitted["cooling_model"], city_a_frame, geometry)
    cooling_pred_b = _cooling_corrected_ampacity(fitted["cooling_model"], city_b_frame, geometry)
    cooling_reduced, cooling_bottleneck = _merge_prediction_to_scored_index(
        scored_frame, city_a_frame["datetime_utc"], cooling_pred_a, city_b_frame["datetime_utc"], cooling_pred_b,
    )

    arm5_truth_frame = _arm5_truth_frame(stacked_full, city_a, city_b)
    X5_all, _ = forecast_training.build_training_matrix(arm5_truth_frame, horizon_minutes=1440)
    anchor_index = pd.DatetimeIndex(pd.to_datetime(scored_frame["anchor_datetime_utc"], utc=True))
    X5_scored = X5_all.reindex(anchor_index)
    missing_mask = X5_scored.isna().any(axis=1)
    if missing_mask.any():
        missing = anchor_index[missing_mask]
        raise ValueError(
            f"_score_fitted_arms_at_corridor_level: arm 5's feature table "
            f"is missing {int(missing_mask.sum())} anchor timestamp(s) "
            f"needed by the {split!r} split, e.g. {list(missing[:3])}"
        )
    arm5_pred = np.asarray(
        fitted["arm5_estimator"].predict(X5_scored.to_numpy(dtype=float)), dtype=float,
    )

    augmented = scored_frame.copy()
    augmented["pred_ml_wind_corrected"] = wind_reduced
    augmented["bottleneck_index_ml_wind_corrected"] = wind_bottleneck
    augmented["pred_ml_cooling_corrected"] = cooling_reduced
    augmented["bottleneck_index_ml_cooling_corrected"] = cooling_bottleneck
    augmented["pred_reference_ml_refit_24h"] = arm5_pred
    return augmented


def _run_corridor(corridor, start, end, lead_hours, lead_cfg, split):
    """
    Plan 03-04's corridor-level path (the default, and the phase's PRIMARY
    comparison as of this plan): assemble both endpoint cities, reduce
    through `corridor_anchored_pair_frame`'s per-group weakest-link
    reduction, score ALL FOUR `NON_FITTED_ARMS` entries (including the
    oracle) on the requested split, and write a per-corridor JSON report
    with the oracle structurally isolated by `corridor_experiment_report`.

    Plan 03-06 Task 3: when `split == "test"`, this is the phase's ONE
    irreversible step. Arms 3/4/5 are fit ONCE, on the stacked train+val
    frame only (`fit_fitted_arms`, never on test rows), and their
    corridor-level predictions are attached to the scored frame
    (`_score_fitted_arms_at_corridor_level`) so all SEVEN `ALL_ARMS`
    entries score together. The `split == "val"` path below is UNCHANGED
    from Plan 03-04 -- it is the exact path Plans 03-04/03-05's own
    validation-split reports were produced by (see `docs/data-science/
    decisions/forecast_correction_experiment.md`'s Configuration measured
    section), and this plan does not alter that historical reproduction
    path or its four-non-fitted-arm report shape.
    """
    frame = corridor_anchored_pair_frame(corridor, start, end, lead_hours=lead_hours)
    assert_exact_lead(frame, lead_hours=lead_hours)

    boundaries = _default_split_boundaries(frame)
    train, val, test = experiment_splits.calendar_split(frame, boundaries)

    # Task 3: assert the FILTERED train/val/test frames -- the ones
    # actually scored, after filter_to_exact_lead -- are still strictly
    # chronologically disjoint, not only the unfiltered frames
    # calendar_split itself received. Reads only each split's own
    # timestamps, never truth values -- not a no-peeking violation.
    train_filtered = filter_to_exact_lead(train, lead_hours=lead_hours)
    val_filtered = filter_to_exact_lead(val, lead_hours=lead_hours)
    test_filtered = filter_to_exact_lead(test, lead_hours=lead_hours)
    assert_filtered_split_disjoint(train_filtered, val_filtered, test_filtered)

    # Success Criterion 5's no-peeking discipline, routed through the
    # command line's own --split rather than around it: requesting "test"
    # while the module-level lock is engaged raises here, before any test
    # row is ever scored.
    _guard_test_split_access(split)
    scored_frame = {"val": val_filtered, "test": test_filtered}[split]
    assert_exact_lead(scored_frame, lead_hours=lead_hours)

    geometry = legacy_corridor.corridor_geometry(corridor)

    if split == "test":
        # Plan 03-06 Task 3: the phase's one irreversible step. Fit arms
        # 3/4/5 on the STACKED train+val frame -- never on test rows --
        # then attach their corridor-level predictions to scored_frame so
        # all seven ALL_ARMS entries score on the identical row index.
        stacked_full = _stacked_pair_frame(corridor, start, end, lead_hours=lead_hours)
        stacked_train, stacked_val, _stacked_test = experiment_splits.calendar_split(
            stacked_full, boundaries,
        )
        train_val_stacked = (
            pd.concat([stacked_train, stacked_val], ignore_index=True)
            .sort_values("datetime_utc").reset_index(drop=True)
        )
        fitted = fit_fitted_arms(
            train_val_stacked, geometry,
            wind_configuration=WIND_CONFIGURATION, cooling_configuration=COOLING_CONFIGURATION,
        )
        scored_frame = _score_fitted_arms_at_corridor_level(
            stacked_full, boundaries, split, scored_frame, geometry, fitted, lead_hours=lead_hours,
        )
        arms = {name: _corridor_arm_reader(name) for name in ALL_ARMS}
        baseline_name = "persistence_24h"
    else:
        # UNCHANGED from Plan 03-04 -- see this function's own docstring.
        arms = {name: _corridor_arm_reader(name) for name in NON_FITTED_ARMS}
        baseline_name = None

    scored = score_arms(scored_frame, arms, baseline_name=baseline_name)

    bottleneck_distribution = {
        "truth": _bottleneck_counts(scored_frame["bottleneck_index_truth"], corridor),
        "anchor": _bottleneck_counts(scored_frame["bottleneck_index_anchor"], corridor),
    }
    clamp_count = int(
        (scored_frame["nwp_wind_delta_clamped_a"] | scored_frame["nwp_wind_delta_clamped_b"]).sum()
    )

    report = corridor_experiment_report(
        corridor, start, end, frame, scored_frame, boundaries, scored,
        lead_hours=lead_hours, split=split, bottleneck_distribution=bottleneck_distribution,
        nwp_wind_delta_clamp_count=clamp_count, id_key="corridor", baseline_name=baseline_name,
    )

    os.makedirs(config.FORECAST_EXPERIMENT_CACHE_DIR, exist_ok=True)
    # The test-split report is written under its OWN, split-suffixed
    # filename (never the bare val filename Plan 03-04 established) so a
    # test-set run can never silently overwrite -- or be mistaken for --
    # the validation-split report the Configuration measured section of
    # the decision record cites.
    report_filename = (
        f"experiment_report_{corridor}.json" if split == "val"
        else f"experiment_report_{corridor}_{split}.json"
    )
    report_path = os.path.join(config.FORECAST_EXPERIMENT_CACHE_DIR, report_filename)
    with open(report_path, "w") as fh:
        json.dump(report, fh, indent=2, default=str)

    print(f"\n{corridor}: assembled {len(frame)} rows, scored {len(scored_frame)} {split} rows, "
          f"lead {lead_hours}h, window {start} -> {end}")
    print(f"{'candidate':<24}{'mae':>12}{'rmse':>12}{'rows':>10}")
    for name, s in report["candidates"].items():
        print(f"{name:<24}{s['mae']:>12.3f}{s['rmse']:>12.3f}{s['rows']:>10d}")
    oracle_score = report["oracle_diagnostic"]["score"]
    print("-" * 58)
    print(
        f"{ORACLE_ARM_NAME:<24}{oracle_score['mae']:>12.3f}{oracle_score['rmse']:>12.3f}"
        f"{oracle_score['rows']:>10d}  <- NON-FORECAST DIAGNOSTIC, never a candidate"
    )
    print(f"\n{lead_cfg.caveat}")
    print(f"report written to {report_path}")

    candidate_summary = " ".join(
        f"{name}_mae={s['mae']:.3f}" for name, s in report["candidates"].items()
    )
    print(
        f"\nSUMMARY: {corridor} lead_hours={lead_hours} rows_assembled={len(frame)} "
        f"rows_scored={len(scored_frame)} window={start}->{end} split={split} "
        f"{candidate_summary} oracle_mae={oracle_score['mae']:.3f} caveat_present=True"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Score the D-02 non-fitted arms on an identical "
        "held-out timestamp index. Corridor-level scoring (the default, "
        "and the phase's PRIMARY comparison) reduces both endpoint cities "
        "through the repository's one weakest-link helper and scores all "
        "four NON_FITTED_ARMS entries, with the oracle structurally "
        "isolated from the candidate mapping. --city retains Plan 03-03's "
        "single-city tracer path (persistence/raw_forecast only) "
        "unchanged.",
    )
    parser.add_argument(
        "--city", choices=sorted(config.CITY_COORDINATES), default=None,
        help="Legacy single-city tracer mode (Plan 03-03). When omitted "
        "(the default), this module scores at CORRIDOR level instead.",
    )
    parser.add_argument(
        "--corridor", choices=sorted(config.LEGACY_CORRIDOR_ENDPOINTS), default=None,
        help="Corridor to score in corridor-level mode. Default: every "
        "corridor in config.LEGACY_CORRIDOR_ENDPOINTS. Ignored when --city is given.",
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
    parser.add_argument(
        "--split", choices=["val", "test"], default="val",
        help="Which split to score (corridor-level mode only -- the "
        "--city tracer path always scores 'val'). Routes through the "
        "module's test-split lock: requesting 'test' while "
        "_TEST_SPLIT_UNLOCKED is False raises, naming Plan 03-06 as the "
        "unlock (Success Criterion 5's no-peeking discipline). Default: "
        "val.",
    )
    args = parser.parse_args(argv)

    lead_hours = args.lead_hours
    lead_cfg = _lead_source_config(lead_hours)
    start = args.start if args.start is not None else lead_cfg.default_window_start
    end = _resolve_window_end(args.end if args.end is not None else config.FORECAST_EXPERIMENT_WINDOW_END)

    if args.city is not None:
        _run_city_tracer(args.city, start, end, lead_hours, lead_cfg)
        return

    corridors = [args.corridor] if args.corridor else sorted(config.LEGACY_CORRIDOR_ENDPOINTS)
    for corridor in corridors:
        _run_corridor(corridor, start, end, lead_hours, lead_cfg, args.split)


if __name__ == "__main__":
    main()
