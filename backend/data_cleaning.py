"""
Data Cleaning (production-pipeline Phase 2, CLEAN-01..04)
=========================================================
Cross-row checks on one city's archive history. They run in
`city_pipeline.run_city_pipeline` between `historical_archive.read_history`
and `ampacity_forecast.forecast_ampacity` / `AnomalyDetector.for_city`, so
the forecast band and the detector baseline that gate the rating learn only
from rows that passed.

The module is storage-agnostic: it takes any `ARCHIVE_COLUMNS`-shaped
DataFrame (the CSV via `read_history` today, a Postgres read in Phase 4) and
imports no storage module.

Invariants (CLEAN-04): `clean_history` never changes a cell, never adds or
drops a row in `frame`, and never writes anything. It only appends the marker
columns (`MARKER_COLUMNS`) and selects the usable rows. The archive keeps
rows exactly as written; cleaning is a read-time selection.

Per-row unit and range checks stay with `units_def.validate_pipeline_row`
(`read_history` drops those rows before this module sees them). The written
policy is `docs/data-science/decisions/data_cleaning.md`.
"""

import logging

import pandas as pd

import config

log = logging.getLogger(__name__)

# Bump whenever a rule or threshold changes, so a validation result can name
# the policy behind its flags.
CLEANING_POLICY_VERSION: int = 2

# Thresholds below are PROVISIONAL: they are written down with their reasoning
# and are not fitted to data. Phase 3 measures their per-city flag rates on real
# archives before anyone relies on them. Changing any constant bumps
# CLEANING_POLICY_VERSION.

# Fields the stuck-sensor rule checks.
STUCK_FIELDS: tuple[str, ...] = ("air_temp", "wind_speed", "solar_radiation")

# Consecutive usable rows with one identical value that mark a stuck sensor.
# A run counts rows on consecutive hourly slots: a missing hour (no row at all)
# ends it, a row excluded by an earlier rule does not. Hourly temperature at whole-degree resolution can repeat for a few hours
# overnight; six identical hourly readings of one field is beyond that, and it
# equals the ML forecast's six-row lookback (config.FORECAST_ML_ROLLING_WINDOW_HOURS).
STUCK_MIN_RUN_ROWS: int = 6

# Values that may repeat without meaning a stuck sensor. Solar radiation is
# exactly 0.0 every night. Archived wind_speed is the line-perpendicular
# component and station calm reports are exactly 0.0, so calm nights repeat it.
STUCK_EXEMPT_VALUES: dict[str, tuple[float, ...]] = {
    "solar_radiation": (0.0,),
    "wind_speed": (0.0,),
}

# Fields the spike rule checks.
SPIKE_FIELDS: tuple[str, ...] = STUCK_FIELDS

# Largest believable one-hour excursion per field, in the units of
# units_def.PIPELINE_SCHEMA (degC, m/s, W/m2). A front is a step that stays;
# a spike is a value that jumps away from both neighbors by more than this and
# returns. Archived wind_speed is the line-perpendicular component
# (city_rating._project_wind), so wind-direction swings move it. Clouds swing
# hourly solar widely, so only a larger excursion counts.
SPIKE_MAX_STEP: dict[str, float] = {
    "air_temp": 10.0,
    "wind_speed": 10.0,
    "solar_radiation": 700.0,
}

# Largest number of missing hourly slots between the newest usable row and the
# run's own slot for which a forecast may still gate G6. The forecast band is
# calibrated one step (60 min) ahead of its newest row; one skipped cycle is
# tolerated, and a larger trailing gap means the band describes an older hour
# than the one being rated. Provisional until Phase 3.
MAX_TRAILING_GAP_SLOTS: int = 1

# Newest usable rows that must sit on consecutive hourly slots before an `ml`
# forecast may gate G6. `ampacity_forecast.build_ml_features` lags by row
# position (`.shift(h)`), so the newest row's features are the trained hourly
# features only when this many rows are consecutive hours: the model was
# trained on a gap-free hourly series. Derived from the feature definition
# (config is read only).
ML_LOOKBACK_ROWS: int = (
    max(max(config.FORECAST_ML_LAG_HOURS), config.FORECAST_ML_ROLLING_WINDOW_HOURS) + 1
)

# The order rules run in, and the order flags are joined in `clean_flags`.
# `after_gap` marks a row without excluding it.
FLAG_ORDER: tuple[str, ...] = (
    "bad_timestamp",
    "duplicate",
    "fallback",
    "at_or_after_run",
    "same_hour",
    "stuck_air_temp",
    "stuck_wind_speed",
    "stuck_solar_radiation",
    "spike_air_temp",
    "spike_wind_speed",
    "spike_solar_radiation",
    "after_gap",
)

# Flags that take a row out of `usable`: every flag except `after_gap`.
EXCLUDING_FLAGS: frozenset[str] = frozenset(FLAG_ORDER) - {"after_gap"}

# Columns appended to the cleaned frame, never persisted.
MARKER_COLUMNS: tuple[str, ...] = ("clean_flags", "clean_excluded", "gap_slots")

_AS_OF_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


# A time of day followed by an explicit UTC offset ("...T10:00:00Z", "...+06:00").
_EXPLICIT_OFFSET = r"\d{2}:\d{2}(?::\d{2}(?:[.,]\d+)?)?\s*(?:[Zz]|[+-]\d{2}(?::?\d{2})?)\s*$"


def _parse_utc(values) -> pd.Series:
    """
    Parse timestamps as UTC instants; anything unparseable becomes NaT.

    `format="ISO8601"` matters: without it pandas 2.3 infers one format from
    the first value and rejects other spellings of the same instant (a naive
    "...T10:00:00" after a "...T10:00:00Z"). Naive values read as UTC.

    Values with an explicit offset and values without one are parsed in
    separate batches: pandas 2.3 applies the offset of an earlier value to a
    later naive or date-only one in a single mixed call, which would misplace
    that row in the time sort and miss a duplicate instant. The write-side twin
    is `historical_archive._parse_utc`.
    """
    series = values if isinstance(values, pd.Series) else pd.Series(list(values), dtype=object)
    index = series.index
    series = series.reset_index(drop=True)
    explicit = series.astype(str).str.contains(_EXPLICIT_OFFSET, regex=True)
    parsed = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns, UTC]")
    for mask in (explicit, ~explicit):
        if mask.any():
            parsed.loc[mask] = pd.to_datetime(
                series[mask], utc=True, errors="coerce", format="ISO8601"
            )
    parsed.index = index
    return parsed


class CleanedHistory:
    """
    Result of `clean_history`.

    `frame`   -- every input row, stable-sorted by parsed time (unparseable
                 last), with the marker columns appended.
    `usable`  -- the rows of `frame` with `clean_excluded` false, index reset.
    `report`  -- dict: policy_version, rows_in, rows_usable, rows_excluded,
                 flag_counts (every name in FLAG_ORDER), as_of, missing_slots,
                 trailing_gap_slots, contiguous_tail_rows.
    """

    def __init__(self, frame: pd.DataFrame, usable: pd.DataFrame, report: dict):
        self.frame = frame
        self.usable = usable
        self.report = report

    def __repr__(self) -> str:
        return (
            f"CleanedHistory(rows_in={self.report['rows_in']}, "
            f"rows_usable={self.report['rows_usable']})"
        )


def _hours_since_epoch(instants: pd.Series) -> pd.Series:
    """Whole hours between the Unix epoch and each (hour-floored, UTC) instant."""
    return (instants - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(hours=1)


def _stuck_mask(
    values: pd.Series, hours: pd.Series, live: pd.Series, min_run: int, exempt
) -> pd.Series:
    """
    Rows in a run of at least `min_run` consecutive identical values, judged
    over the rows `live` leaves usable. A run continues across hours held only
    by excluded rows and ends at an hour with no row at all, so readings days
    apart never form one run. NaN never equals itself, so it never forms a
    run; `exempt` values never do.
    """
    out = pd.Series(False, index=values.index, dtype=bool)
    seq = values[live]
    if seq.empty:
        return out
    # Rank of each live row's hour among every hour that holds any row: two
    # live rows are on consecutive held hours when their ranks and their
    # hours step by the same amount.
    held = pd.Series(sorted(hours.dropna().unique()))
    rank = pd.Series(held.index, index=held.to_numpy())
    h = hours[live]
    r = h.map(rank)
    contiguous = (h - h.shift()) == (r - r.shift())
    run_id = ((seq != seq.shift()) | ~contiguous).cumsum()
    long_run = run_id.map(run_id.value_counts()) >= min_run
    flagged = long_run & seq.notna() & ~seq.isin(list(exempt))
    out[flagged.index[flagged.to_numpy()]] = True
    return out


def _spike_mask(values: pd.Series, hours: pd.Series, live: pd.Series, max_step: float) -> pd.Series:
    """
    Live rows whose neighbors sit on the adjacent hourly slots and whose value
    differs from both by more than `max_step` in the same direction. Every row
    is judged against the same set, so an oscillating sensor flags every
    interior row. NaN comparisons are false, so NaN never flags.
    """
    out = pd.Series(False, index=values.index, dtype=bool)
    v = values[live]
    h = hours[live]
    if len(v) < 3:
        return out
    adjacent = ((h - h.shift(1)) == 1) & ((h.shift(-1) - h) == 1)
    d_prev = v - v.shift(1)
    d_next = v - v.shift(-1)
    flagged = adjacent & (d_prev.abs() > max_step) & (d_next.abs() > max_step) & (d_prev * d_next > 0)
    out[flagged.index[flagged.to_numpy()]] = True
    return out


def clean_history(
    history: pd.DataFrame, as_of=None, stuck_min_run_rows=None, spike_max_step=None
) -> CleanedHistory:
    """
    Flag and select the usable rows of one city's archive history.

    A row's hourly slot is its parsed UTC time floored to the hour, the same
    rule as OD-7's `valid_time` (the run end truncated to the hour). Gaps are
    counted in slots, not elapsed time: hourly runs must end inside their own
    hour (the live schedule dispatches at hh:05), and a run that slips past
    the next hour boundary reads as a missing slot. Rules run
    in `FLAG_ORDER` order (a row can carry several flags, joined with "|" in
    that order in `clean_flags`). Row-local rules see every row; cross-row
    rules see only the rows earlier rules left usable:
      bad_timestamp   -- `datetime_utc` is missing or unparseable.
      duplicate       -- a computed (non-fallback) row, and another computed
                         row at the same UTC instant came first in input
                         order; the first computed row written owns the
                         instant, even after a fallback row (matching
                         `historical_archive.append_observation`).
      fallback        -- `fallback` is true, as a bool or text equal to "true"
                         in any case (no other spelling). Fallback
                         cycles archive the static rating as dlr_amps; learning
                         from them makes the naive forecast equal the static
                         rating and latches G6.
      at_or_after_run -- with `as_of` given, the row's slot is at or after
                         `as_of`'s slot. The history a run learns from ends
                         before the slot it rates, so a rerun or an
                         out-of-order backfill sees what the first in-order
                         run saw (no look-ahead).
      same_hour       -- among usable rows in one slot, all but the one with
                         the latest timestamp (the fresher reading).
      stuck_<field>   -- the row is in a run of `stuck_min_run_rows`
                         consecutive usable rows with the identical value in
                         air_temp, wind_speed or solar_radiation (a run
                         continues across hours held by excluded rows and
                         ends at an hour with no row; NaN never forms a run;
                         values in STUCK_EXEMPT_VALUES, solar 0.0 at night
                         and calm wind 0.0, are exempt).
      spike_<field>   -- the row's previous and next usable rows sit on the
                         adjacent hourly slots and its value differs from both
                         by more than `spike_max_step[field]` in the same
                         direction (a one-hour excursion that returns). Steps,
                         ramps, rows next to a gap and the first and last
                         usable rows are never spikes.
      after_gap       -- the row follows a missing slot. Marks the row, does
                         not exclude it.
    Every flag but `after_gap` excludes the row from `usable`; `frame` keeps
    every row. The three stuck rules all judge the rows left usable by
    `same_hour`; the three spike rules all judge the rows left usable by the
    stuck rules.

    `stuck_min_run_rows` and `spike_max_step` override `STUCK_MIN_RUN_ROWS`
    and `SPIKE_MAX_STEP` (None uses the module constant). An overriding
    `spike_max_step` dict replaces the table: a field it omits is not
    spike-checked, and a key outside `SPIKE_FIELDS` is ignored. A field whose
    column is absent from the frame is skipped by both rules.

    Missing hourly slots are marked, never filled: no row is invented and no
    value is imputed. `gap_slots` is, per usable row, the number of hourly
    slots missing since the previous usable row (0 for the first; 0 on
    excluded rows). An excluded row leaves its hour missing.

    `as_of` is the end of the run window: None, or anything
    `pd.to_datetime(..., utc=True, format="ISO8601")` parses. It is reported as
    the canonical `%Y-%m-%dT%H:%M:%SZ` string. The report also carries
    `missing_slots` (sum of `gap_slots`), `trailing_gap_slots` (hourly slots
    between the newest usable row and `as_of`'s slot; None without `as_of` or
    without usable rows) and `contiguous_tail_rows` (the newest usable rows on
    consecutive slots; 0 when none).

    The input frame is never modified. Raises `ValueError` when the frame
    holds more than one non-null city (cross-row rules are per city; loop over
    cities) or when `as_of` does not parse.
    """
    if "city" in history.columns:
        cities = sorted(str(c) for c in history["city"].dropna().unique())
        if len(cities) > 1:
            raise ValueError(
                f"clean_history works on one city at a time, got cities {cities}"
            )

    as_of_text = None
    as_of_slot = None
    if as_of is not None:
        try:
            as_of_ts = pd.to_datetime(as_of, utc=True, format="ISO8601")
        except Exception as exc:
            raise ValueError(f"as_of {as_of!r} does not parse as a timestamp ({exc})") from exc
        if pd.isna(as_of_ts):
            raise ValueError(f"as_of {as_of!r} does not parse as a timestamp")
        as_of_text = as_of_ts.strftime(_AS_OF_FORMAT)
        as_of_slot = as_of_ts.floor("h")

    frame = history.copy().reset_index(drop=True)
    if "datetime_utc" in frame.columns:
        parsed = _parse_utc(frame["datetime_utc"])
    else:
        parsed = pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")

    # Stable sort so rows for one instant keep input order; NaT last. The
    # parsed series stays a local variable, never a column.
    order = parsed.sort_values(kind="mergesort", na_position="last").index
    frame = frame.loc[order].reset_index(drop=True)
    parsed = parsed.loc[order].reset_index(drop=True)
    slots = parsed.dt.floor("h")
    no_rows = pd.Series(False, index=frame.index, dtype=bool)

    masks = {}

    # Row-local rules: every row.
    masks["bad_timestamp"] = parsed.isna()
    masks["fallback"] = (
        frame["fallback"].astype(str).str.lower() == "true"
        if "fallback" in frame.columns
        else no_rows.copy()
    )
    # Judged over computed rows only, so a computed row written after a
    # fallback row at the same instant owns it (matching append_observation).
    computed = parsed.notna() & ~masks["fallback"]
    masks["duplicate"] = (
        parsed[computed].duplicated(keep="first").reindex(frame.index, fill_value=False).astype(bool)
    )
    masks["at_or_after_run"] = (
        parsed.notna() & (slots >= as_of_slot) if as_of_slot is not None else no_rows.copy()
    )
    excluded = (
        masks["bad_timestamp"] | masks["duplicate"] | masks["fallback"] | masks["at_or_after_run"]
    )

    # Cross-row rules: only rows the earlier rules left usable.
    live = ~excluded
    same_hour = (
        slots[live].duplicated(keep="last").reindex(frame.index, fill_value=False).astype(bool)
    )
    masks["same_hour"] = same_hour
    excluded = excluded | same_hour

    min_run = STUCK_MIN_RUN_ROWS if stuck_min_run_rows is None else int(stuck_min_run_rows)
    steps = SPIKE_MAX_STEP if spike_max_step is None else spike_max_step
    slot_hours = _hours_since_epoch(slots)

    def numeric(field):
        return pd.to_numeric(frame[field], errors="coerce") if field in frame.columns else None

    live = ~excluded
    for field in STUCK_FIELDS:
        values = numeric(field)
        masks[f"stuck_{field}"] = (
            no_rows.copy() if values is None
            else _stuck_mask(values, slot_hours, live, min_run, STUCK_EXEMPT_VALUES.get(field, ()))
        )
    for field in STUCK_FIELDS:
        excluded = excluded | masks[f"stuck_{field}"]

    live = ~excluded
    for field in SPIKE_FIELDS:
        values = numeric(field)
        masks[f"spike_{field}"] = (
            no_rows.copy() if values is None or field not in steps
            else _spike_mask(values, slot_hours, live, float(steps[field]))
        )
    for field in SPIKE_FIELDS:
        excluded = excluded | masks[f"spike_{field}"]

    # Gaps: hours missing between consecutive usable rows. Excluded rows carry 0.
    gap_slots = pd.Series(0, index=frame.index, dtype="int64")
    usable_pos = frame.index[~excluded]
    if len(usable_pos):
        usable_hours = _hours_since_epoch(slots[usable_pos])
        gap_slots[usable_pos] = (usable_hours.diff().fillna(1).astype("int64") - 1).clip(lower=0)
    masks["after_gap"] = gap_slots > 0

    # One string per row: the names of its true masks, in FLAG_ORDER order.
    hits = zip(*[masks[name].tolist() for name in FLAG_ORDER])
    flags = pd.Series(
        ["|".join(name for name, hit in zip(FLAG_ORDER, row) if hit) for row in hits],
        index=frame.index, dtype=object,
    )

    frame["clean_flags"] = flags
    frame["clean_excluded"] = excluded.astype(bool)
    frame["gap_slots"] = gap_slots

    usable = frame[~frame["clean_excluded"]].reset_index(drop=True)

    trailing_gap_slots = None
    contiguous_tail_rows = 0
    if len(usable_pos):
        if as_of_slot is not None:
            newest_hour = int(_hours_since_epoch(slots[usable_pos]).iloc[-1])
            as_of_hour = int(_hours_since_epoch(pd.Series([as_of_slot])).iloc[0])
            trailing_gap_slots = as_of_hour - newest_hour - 1
        gaps = usable["gap_slots"].tolist()
        broken_at = [i for i, g in enumerate(gaps) if g > 0]
        contiguous_tail_rows = len(gaps) - (broken_at[-1] if broken_at else 0)

    report = {
        "policy_version": CLEANING_POLICY_VERSION,
        "rows_in": int(len(history)),
        "rows_usable": int(len(usable)),
        "rows_excluded": int(len(frame) - len(usable)),
        "flag_counts": {name: int(masks[name].sum()) for name in FLAG_ORDER},
        "as_of": as_of_text,
        "missing_slots": int(gap_slots.sum()),
        "trailing_gap_slots": trailing_gap_slots,
        "contiguous_tail_rows": int(contiguous_tail_rows),
    }
    return CleanedHistory(frame=frame, usable=usable, report=report)


def forecast_gap_reason(report: dict, forecast_method: str):
    """
    Why a forecast built from this cleaned history must not gate G6, or None.

    This is not a cleaning rule and excludes no row: it tells the caller
    whether a forecast built from the history `report` describes (the report of
    `clean_history`) may be used by G6. A reason is returned when:
      - the newest usable row is more than `MAX_TRAILING_GAP_SLOTS` hourly
        slots before the run (`trailing_gap_slots`), or
      - `forecast_method` is "ml" and fewer than `ML_LOOKBACK_ROWS` of the
        newest usable rows sit on consecutive hours (`contiguous_tail_rows`).
    With no usable rows there is nothing to judge and the result is None.
    """
    if not report.get("rows_usable"):
        return None
    trailing = report.get("trailing_gap_slots")
    if trailing is not None and trailing > MAX_TRAILING_GAP_SLOTS:
        return (
            f"{trailing} missing hourly slot(s) between the newest usable row and the run "
            f"(limit {MAX_TRAILING_GAP_SLOTS})"
        )
    if forecast_method == "ml":
        tail = report.get("contiguous_tail_rows", 0)
        if tail < ML_LOOKBACK_ROWS:
            return (
                f"ml forecast needs {ML_LOOKBACK_ROWS} newest usable rows on consecutive hours, "
                f"found {tail}"
            )
    return None
