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

log = logging.getLogger(__name__)

# Bump whenever a rule or threshold changes, so a validation result can name
# the policy behind its flags.
CLEANING_POLICY_VERSION: int = 1

# The order rules run in, and the order flags are joined in `clean_flags`.
FLAG_ORDER: tuple[str, ...] = ("bad_timestamp", "duplicate", "fallback")

# Flags that take a row out of `usable`.
EXCLUDING_FLAGS: frozenset[str] = frozenset({"bad_timestamp", "duplicate", "fallback"})

# Columns appended to the cleaned frame, never persisted.
MARKER_COLUMNS: tuple[str, ...] = ("clean_flags", "clean_excluded")

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
                 flag_counts (every name in FLAG_ORDER), as_of.
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


def clean_history(history: pd.DataFrame, as_of=None) -> CleanedHistory:
    """
    Flag and select the usable rows of one city's archive history.

    Rules, run in `FLAG_ORDER` order (a row can carry several flags, joined
    with "|" in that order in `clean_flags`):
      bad_timestamp -- `datetime_utc` is missing or unparseable.
      duplicate     -- another row at the same UTC instant came first in
                       input order; the first row written owns the instant
                       (matching `historical_archive.append_observation`).
      fallback      -- `fallback` is true, as a bool or any-case text. Fallback
                       cycles archive the static rating as dlr_amps; learning
                       from them makes the naive forecast equal the static
                       rating and latches G6.
    All three exclude the row from `usable`; `frame` keeps every row.

    `as_of` is the end of the run window: None, or anything
    `pd.to_datetime(..., utc=True, format="ISO8601")` parses. No rule uses it
    yet; it is reported as the canonical `%Y-%m-%dT%H:%M:%SZ` string.

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
    if as_of is not None:
        try:
            as_of_ts = pd.to_datetime(as_of, utc=True, format="ISO8601")
        except Exception as exc:
            raise ValueError(f"as_of {as_of!r} does not parse as a timestamp ({exc})") from exc
        if pd.isna(as_of_ts):
            raise ValueError(f"as_of {as_of!r} does not parse as a timestamp")
        as_of_text = as_of_ts.strftime(_AS_OF_FORMAT)

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

    masks = {
        "bad_timestamp": parsed.isna(),
        "duplicate": parsed.notna() & parsed.duplicated(keep="first"),
        "fallback": (
            frame["fallback"].astype(str).str.lower() == "true"
            if "fallback" in frame.columns
            else pd.Series(False, index=frame.index)
        ),
    }

    # One string per row: the names of its true masks, in FLAG_ORDER order.
    hits = zip(*[masks[name].tolist() for name in FLAG_ORDER])
    flags = pd.Series(
        ["|".join(name for name, hit in zip(FLAG_ORDER, row) if hit) for row in hits],
        index=frame.index, dtype=object,
    )
    excluded = pd.Series(False, index=frame.index, dtype=bool)
    for name in FLAG_ORDER:
        if name in EXCLUDING_FLAGS:
            excluded = excluded | masks[name]

    frame["clean_flags"] = flags
    frame["clean_excluded"] = excluded.astype(bool)

    usable = frame[~frame["clean_excluded"]].reset_index(drop=True)

    report = {
        "policy_version": CLEANING_POLICY_VERSION,
        "rows_in": int(len(history)),
        "rows_usable": int(len(usable)),
        "rows_excluded": int(len(frame) - len(usable)),
        "flag_counts": {name: int(masks[name].sum()) for name in FLAG_ORDER},
        "as_of": as_of_text,
    }
    return CleanedHistory(frame=frame, usable=usable, report=report)
