"""
Weather Ingestion — Provider-Agnostic Adapter (C4)
==================================================
This module is C4 per `docs/data-science/specs/C4-weather-ingestion.md`.

It exists to make the still-open weather-provider decision (see
`docs/data-science/PRD.md` §7.1 — Synoptic vs. NOAA vs. some other source)
inconsequential to every downstream caller (C5, C7, C8, ...). Today, the
only implementation behind `fetch_weather` is Synoptic, delegated straight
through to `backend/dlr_pipeline.py::fetch_timeseries`. If/when the provider
decision lands on something else (or a second provider needs to be
supported), that change should be containable entirely within this file —
callers keep calling `fetch_weather(location, start, end)` and shouldn't
need to change at all.

Phase 7 wires the first two real providers into this file: the station path
(`_fetch_station`, `provider="synoptic"`) is now transparently supplemented
with ASOS 1-minute wind/temp rows (`_supplement_with_asos`, WX-02, D-01..
D-03) whenever the Synoptic frame resolves a coordinate to one of
`config.ASOS_STATIONS`' four cities. The grid path (`_fetch_grid`,
`provider="open_meteo"`) now has its first real implementation: a
standalone historical-backfill source (WX-04, D-04) returning the full
temp/wind/solar/RH variable set for C9/C10 training data, no merge
performed.

Phase 8 adds a second grid-path provider: `provider="nsrdb"` delegates to
`nsrdb_provider.fetch_nsrdb` for solar-only GHI (WX-03, D-02), tagged
`solar_source="nsrdb"` and merged into a station row exactly like
`open_meteo`'s solar column would be.

Phase 9 adds a second station-path provider: `provider="tceq"` delegates to
`tceq_provider.fetch_tceq` for one CAMS site's wind/temp/RH (WX-01), tagged
`"tceq"` via the same `attach_provenance` mechanism the Synoptic branch
uses. Unlike the Synoptic branch, no ASOS supplement is applied here --
`_supplement_with_asos` is Synoptic-specific and mixing it into the TCEQ
branch is not in WX-01's scope.

Importing this module has no side effects (no file I/O, no network calls) —
it is safe to import without a `SYNOPTIC_TOKEN` env var set. A token is only
required when `fetch_weather(..., provider="synoptic")` is actually called,
via `dlr_pipeline.fetch_timeseries`'s own token lookup.
"""

import logging
import math

import pandas as pd

import asos_provider
import config
import dlr_pipeline
import nsrdb_provider
import open_meteo_provider
import station_explorer
import tceq_provider
import units_def

log = logging.getLogger(__name__)

# PROVENANCE_FIELD_MAP: which underlying data column(s) each per-field
# provenance column (units_def.PIPELINE_SCHEMA v3) is derived from. A
# provenance column is set to the supplying provider's name only where at
# least one of its mapped source columns is present in the frame AND
# non-null for that row -- never inferred, never carried across rows, and
# never defaulted when the source is unknown (D-03/D-04, T-06-01).
PROVENANCE_FIELD_MAP: dict[str, tuple[str, ...]] = {
    "wind_source": ("wind_speed", "wind_direction"),
    "temp_source": ("air_temp",),
    "humidity_source": ("relative_humidity",),
    "solar_source": ("solar_radiation",),
}


def attach_provenance(
    frame: pd.DataFrame,
    provider: str,
    *,
    field_map: dict[str, tuple[str, ...]] = PROVENANCE_FIELD_MAP,
) -> pd.DataFrame:
    """
    Return a copy of `frame` with per-field provenance columns
    (units_def.PIPELINE_SCHEMA v3) attached, recording `provider` as the
    source of each field family it actually supplied.

    Args:
        frame: A weather-observation DataFrame (may be None or empty).
        provider: The provider name to record. Must be a member of
            `units_def.KNOWN_PROVIDER_NAMES`.
        field_map: Maps each provenance column name to the tuple of
            underlying data columns whose presence it tracks.

    Returns:
        A new DataFrame (the caller's `frame` is left unchanged). Each
        provenance column is set to `provider` on rows where at least one
        of its mapped source columns is present in the frame AND non-null
        for that row, and to `None` everywhere else. `frame` is returned
        unchanged (not copied) when it is `None` or empty.

    Raises:
        ValueError: If `provider` is not in `units_def.KNOWN_PROVIDER_NAMES`.
    """
    if provider not in units_def.KNOWN_PROVIDER_NAMES:
        raise ValueError(
            f"Unknown weather provider: {provider!r}. Must be one of "
            f"{sorted(units_def.KNOWN_PROVIDER_NAMES)}."
        )

    if frame is None or frame.empty:
        return frame

    frame = frame.copy()
    for provenance_col, source_cols in field_map.items():
        present_source_cols = [c for c in source_cols if c in frame.columns]
        if not present_source_cols:
            frame[provenance_col] = None
            continue
        has_value = frame[present_source_cols].notna().any(axis=1)
        frame[provenance_col] = pd.Series(
            [provider if v else None for v in has_value], index=frame.index
        )
    return frame


def resolve_station_city(lat, lon) -> str | None:
    """
    Resolve a station's coordinates to the nearest of the four
    `config.CITY_COORDINATES` cities, returning a literal dict key -- never
    a reformatted, title-cased, or default city label.

    Args:
        lat, lon: The station's coordinates. Any type is accepted; only
            finite, non-bool int/float values resolve to a city.

    Returns:
        The nearest city's exact `config.CITY_COORDINATES` key, or `None`
        if `lat`/`lon` is absent, null, non-numeric, or non-finite. Never
        falls back to a default or nearest-guess-regardless-of-validity
        city -- an unresolved coordinate must not be silently attributed to
        the wrong corridor's static rating.
    """
    for v in (lat, lon):
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return None
        if not math.isfinite(float(v)):
            return None

    return min(
        config.CITY_COORDINATES,
        key=lambda city: station_explorer.haversine_km(
            lat, lon, *config.CITY_COORDINATES[city]
        ),
    )


# MERGE_KEY: the literal (city, datetime_utc) pair merge_observations() keys
# on (D-05). City was chosen over station ID or raw coordinates because
# every request in this codebase already resolves to one of the four
# config.CITY_COORDINATES entries -- keying on city keeps the merge
# insensitive to which specific station or grid cell actually supplied a
# given reading.
MERGE_KEY: tuple[str, str] = ("city", "datetime_utc")


def attach_city(
    frame: pd.DataFrame,
    *,
    lat: float = None,
    lon: float = None,
) -> pd.DataFrame:
    """
    Return a copy of `frame` with a `city` column attached via
    `resolve_station_city` -- never a default, inferred, or reformatted
    city label.

    Args:
        frame: A weather-observation DataFrame (may be None or empty).
        lat, lon: When both are supplied (the grid-request case, where the
            coordinates came from the caller rather than from the data),
            every row's `city` is set from this single coordinate pair.
            When neither is supplied, `city` is derived per row from the
            frame's own `lat`/`lon` columns.

    Returns:
        A new DataFrame (the caller's `frame` is left unchanged) carrying a
        `city` column whose every non-null value is a literal
        `config.CITY_COORDINATES` key. `frame` is returned unchanged (not
        copied) when it is `None` or empty.

    Raises:
        ValueError: If `frame` is non-empty, `lat`/`lon` were not supplied,
            and `frame` has no `lat` column -- a caller asking for city
            attribution on a frame with nothing to attribute from is a bug,
            not a null case.
    """
    if frame is None or frame.empty:
        return frame

    frame = frame.copy()

    if lat is not None and lon is not None:
        frame["city"] = resolve_station_city(lat, lon)
        return frame

    if "lat" not in frame.columns:
        raise ValueError(
            "attach_city: frame has no 'lat' column and no lat/lon keyword "
            "arguments were supplied -- nothing to resolve a city from."
        )

    lon_values = (
        frame["lon"] if "lon" in frame.columns else pd.Series([None] * len(frame), index=frame.index)
    )
    frame["city"] = [
        resolve_station_city(row_lat, row_lon)
        for row_lat, row_lon in zip(frame["lat"], lon_values)
    ]
    return frame


def _prepare_merge_side(frame: pd.DataFrame, side_name: str) -> pd.DataFrame:
    """
    Normalize one side of a merge_observations() call: verify both MERGE_KEY
    members are present (as a column or an index level), verify no row has
    an unresolvable (null) city, then index the frame on MERGE_KEY.

    Raises:
        ValueError: If a MERGE_KEY member is missing from `frame`'s columns
            and index levels, or if any row's `city` is null.
    """
    names_present = set(frame.columns) | {n for n in frame.index.names if n is not None}
    missing = [k for k in MERGE_KEY if k not in names_present]
    if missing:
        raise ValueError(
            f"merge_observations: {side_name} frame is missing required key "
            f"column(s) {missing} -- both {MERGE_KEY} must be present as a "
            "column or an index level."
        )

    if any(name is not None for name in frame.index.names):
        frame = frame.reset_index()

    null_city_count = int(frame["city"].isna().sum())
    if null_city_count:
        raise ValueError(
            f"merge_observations: {null_city_count} row(s) in the "
            f"{side_name} frame have an unresolvable (null) city and cannot "
            "be merged -- resolving or dropping them is the caller's "
            "responsibility, not a default this function may apply."
        )

    return frame.set_index(list(MERGE_KEY)).sort_index()


def merge_observations(station_frame: pd.DataFrame, grid_frame: pd.DataFrame) -> pd.DataFrame:
    """
    Combine a station-sourced frame and a grid-sourced frame into one row
    per (city, datetime_utc) key (D-05), with each field's value and
    provenance drawn from whichever side actually supplied it.

    `combine_first` is the primitive used rather than an outer `merge` plus
    per-column `fillna`: it fills nulls column-by-column from the other
    frame and unions both indexes, which is exactly D-05's semantics, and
    the calling frame's non-null value winning is exactly
    `data_provider.md`'s composition -- station-based wind/temp primary,
    grid-based solar filling what stations lack. The station frame is
    combined from the left for that reason.

    The honesty of the merged provenance rests entirely on an invariant
    `attach_provenance` already establishes: a provenance cell is non-null
    exactly when its mapped data cell is non-null. Because `combine_first`
    fills each column independently, that pairing is preserved automatically
    -- no post-merge provenance rewriting, defaulting, or backfill step is
    performed here, since doing so would re-introduce exactly the
    false-provenance risk the column-wise fill avoids.

    Args:
        station_frame: A station-sourced weather frame (may be None or
            empty), already carrying a `city` column (e.g. via
            `attach_city`).
        grid_frame: A grid-sourced weather frame (may be None or empty),
            already carrying a `city` column.

    Returns:
        A DataFrame indexed by (city, datetime_utc), sorted ascending, with
        every field's value and per-field provenance column drawn from
        whichever side actually supplied it. Returns the other side
        (re-indexed and sorted) when exactly one side is None/empty, and an
        empty DataFrame when both are.

    Raises:
        ValueError: If a non-empty side is missing a MERGE_KEY column/index
            level, or if any row's `city` is null -- merging an unresolvable
            row would otherwise group it under a shared null key with every
            other unresolvable row from both providers, fabricating a
            single row stitched together from unrelated stations.
    """
    station_empty = station_frame is None or station_frame.empty
    grid_empty = grid_frame is None or grid_frame.empty

    if station_empty and grid_empty:
        return pd.DataFrame()
    if station_empty:
        return _prepare_merge_side(grid_frame, "grid")
    if grid_empty:
        return _prepare_merge_side(station_frame, "station")

    station_indexed = _prepare_merge_side(station_frame, "station")
    grid_indexed = _prepare_merge_side(grid_frame, "grid")
    return station_indexed.combine_first(grid_indexed).sort_index()


def _validate_location_shape(location) -> str:
    """
    Classify `location` as the literal string "station" or "grid", or raise
    `ValueError` naming the received shape.

    Returns "grid" only when `location` is a `tuple` of exactly length 2
    whose members are both `isinstance(v, (int, float))` and not `bool`.
    Returns "station" only when `location` is a non-empty `list` whose
    members are all `str`. Every other shape -- including a `list` of two
    numbers, which must not be silently read as coordinates -- raises.
    """
    if isinstance(location, tuple):
        if (
            len(location) == 2
            and all(
                isinstance(v, (int, float)) and not isinstance(v, bool)
                for v in location
            )
        ):
            return "grid"
        length = len(location)
        raise ValueError(
            f"Ambiguous location shape: tuple of length {length} "
            f"({type(location).__name__}). A grid request must be a "
            "2-element tuple of (lat, lon) numbers."
        )

    if isinstance(location, list):
        if location and all(isinstance(v, str) for v in location):
            return "station"
        length = len(location)
        raise ValueError(
            f"Ambiguous location shape: list of length {length} "
            f"({type(location).__name__}). A station request must be a "
            "non-empty list of station-id strings."
        )

    length = len(location) if hasattr(location, "__len__") else None
    raise ValueError(
        f"Ambiguous location shape: {type(location).__name__}"
        + (f" of length {length}" if length is not None else "")
        + ". Expected a list of station-id strings or a 2-element "
        "(lat, lon) tuple of numbers."
    )


def _supplement_with_asos(synoptic_frame: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """
    Transparently supplement a Synoptic station frame with ASOS 1-minute
    wind/temp rows (D-01, D-02, D-03) -- union-of-timestamps rows added at
    ASOS's finer temporal resolution, Synoptic winning at any shared
    timestamp, unmeasured ASOS fields (`relative_humidity`,
    `solar_radiation`) left null rather than backfilled or derived.

    The Synoptic frame is returned unchanged (never re-keyed, never
    reordered, never stripped of a row) and the reason is logged at INFO,
    for each of these skip conditions -- so a future reader can tell "ASOS
    was never asked" apart from "ASOS had nothing" apart from "ASOS broke":
      - `synoptic_frame` is `None` or empty.
      - `synoptic_frame` has no `lat` column (no coordinates to resolve a
        city from, and therefore no station to ask).
      - Any row's resolved `city` is null (merging an unresolvable row
        would raise inside `merge_observations` by design -- letting that
        raise would destroy the primary result over a supplement).
      - `synoptic_frame` has duplicate `(city, datetime_utc)` keys (e.g.
        two stations in the same city reporting at the same timestamp) --
        merging on a duplicated key would let `combine_first` produce a
        row stitched together from two different stations' readings.
      - No ASOS frame survived the per-city fetch loop (every city was
        either not a key of `config.ASOS_STATIONS`, or returned a
        well-formed empty response for a real sensor-outage window).

    Args:
        synoptic_frame: The Synoptic-sourced, already-`attach_provenance`d
            station frame (may be None or empty).
        start, end: The date window, passed through unchanged to
            `asos_provider.fetch_asos_1min`.

    Returns:
        `synoptic_frame` unchanged for any of the skip conditions above.
        Otherwise, `merge_observations(city_attached_synoptic, asos_frames)`
        -- re-keyed to (city, datetime_utc) with `stid` demoted to a
        nullable column, per D-01's union-of-timestamps requirement.
    """
    if synoptic_frame is None or synoptic_frame.empty:
        return synoptic_frame

    if "lat" not in synoptic_frame.columns:
        log.info("ASOS supplement skipped: synoptic frame has no 'lat' column")
        return synoptic_frame

    city_attached = attach_city(synoptic_frame)

    null_city_count = int(city_attached["city"].isna().sum())
    if null_city_count:
        log.info(
            "ASOS supplement skipped: %d row(s) have an unresolvable city",
            null_city_count,
        )
        return synoptic_frame

    plain = (
        city_attached.reset_index()
        if any(name is not None for name in city_attached.index.names)
        else city_attached
    )
    if plain[["city", "datetime_utc"]].duplicated().any():
        log.info(
            "ASOS supplement skipped: synoptic frame has duplicate "
            "(city, datetime_utc) keys"
        )
        return synoptic_frame

    asos_frames = []
    for city in city_attached["city"].dropna().unique():
        if city not in config.ASOS_STATIONS:
            continue
        station_code = config.ASOS_STATIONS[city]
        asos_raw = asos_provider.fetch_asos_1min(station_code, start, end)
        if asos_raw is None or asos_raw.empty:
            log.info(
                "ASOS supplement: no rows returned for city=%s station=%s "
                "window=%s..%s (real outage or no data)",
                city, station_code, start, end,
            )
            continue
        lat, lon = config.CITY_COORDINATES[city]
        asos_tagged = attach_city(attach_provenance(asos_raw, "asos"), lat=lat, lon=lon)
        asos_frames.append(asos_tagged)

    if not asos_frames:
        return synoptic_frame

    asos_combined = pd.concat(asos_frames, ignore_index=True)
    return merge_observations(city_attached, asos_combined)


def _fetch_station(stids: list[str], start: str, end: str, provider: str) -> pd.DataFrame:
    if provider == "tceq":
        # daily_summary.pl serves exactly one site per request and the
        # frame tceq_provider.fetch_tceq returns carries no station
        # discriminator column -- concatenating two sites' rows would let
        # merge_observations' (city, datetime_utc) key stitch one row
        # together from two different stations' readings. Raising here
        # (rather than taking stids[0], as 09-RESEARCH.md Open Question 1
        # originally recommended) keeps this project's standing commitment
        # that an unreliable/ambiguous input must never pass quietly: a
        # caller passing multiple CAMS IDs gets a clear error naming every
        # ID it supplied, not a silently-incomplete result for only the
        # first one.
        if len(stids) != 1:
            raise ValueError(
                f"weather_provider: provider='tceq' requires exactly one "
                f"CAMS ID per call, got {stids!r} -- daily_summary.pl "
                "serves one site per request and the returned frame "
                "carries no station discriminator column, so rows from "
                "two sites would be indistinguishable once merged on "
                "(city, datetime_utc). Call fetch_weather once per CAMS "
                "ID instead."
            )
        return attach_provenance(tceq_provider.fetch_tceq(stids[0], start, end), "tceq")

    if provider == "synoptic":
        return _supplement_with_asos(
            attach_provenance(dlr_pipeline.fetch_timeseries(stids, start, end), "synoptic"),
            start,
            end,
        )

    raise ValueError(
        f"Unknown weather provider: {provider!r}. Only 'synoptic' and "
        "'tceq' are currently implemented."
    )


def _fetch_grid(lat: float, lon: float, start: str, end: str, provider: str) -> pd.DataFrame:
    if provider == "open_meteo":
        frame = open_meteo_provider.fetch_open_meteo(lat, lon, start, end)
        frame = attach_provenance(frame, "open_meteo")
        frame = attach_city(frame, lat=lat, lon=lon)

        if not frame.empty and frame["city"].isna().any():
            raise ValueError(
                f"_fetch_grid: coordinates ({lat!r}, {lon!r}) did not "
                "resolve to a known city -- an open_meteo row that can "
                "never be merged or rated must not be emitted."
            )

        return frame

    if provider == "nsrdb":
        frame = nsrdb_provider.fetch_nsrdb(lat, lon, start, end)
        frame = attach_provenance(frame, "nsrdb")
        frame = attach_city(frame, lat=lat, lon=lon)

        if not frame.empty and frame["city"].isna().any():
            raise ValueError(
                f"_fetch_grid: coordinates ({lat!r}, {lon!r}) did not "
                "resolve to a known city -- an nsrdb row that can never be "
                "merged or rated must not be emitted."
            )

        return frame

    raise ValueError(
        f"Unknown grid weather provider: {provider!r}. Only 'open_meteo' "
        "and 'nsrdb' are currently implemented on the grid path."
    )


def fetch_weather(
    location: list[str] | tuple[float, float],
    start: str,
    end: str,
    provider: str = "synoptic",
) -> pd.DataFrame:
    """
    Fetch weather observations for the given location and date window,
    behind a provider-agnostic interface.

    Args:
        location: A list of station IDs to select the station-based path,
            or a `(lat, lon)` tuple of two numbers to select the
            grid-based path. Any other shape raises ValueError.
        start: Start of the date window (ISO 8601 string).
        end: End of the date window (ISO 8601 string).
        provider: Which weather provider to use. "synoptic" and "tceq" are
            the two providers implemented on the station path (list of
            station IDs); "open_meteo" and "nsrdb" are the two providers
            implemented on the grid path ((lat, lon) tuple) -- any other
            value raises ValueError for the path it was given on.

    Returns:
        A DataFrame matching the weather-observation subset of
        `PIPELINE_SCHEMA` (C2): air_temp, wind_speed, wind_direction,
        solar_radiation, relative_humidity. On the station path
        (`provider="synoptic"`), indexed by (stid, datetime_utc) UNLESS the
        ASOS 1-minute supplement (WX-02) actually supplied rows for the
        resolved city, in which case the frame is re-keyed to
        (city, datetime_utc) with `stid` demoted to a nullable column (null
        on ASOS-only rows, since attributing an ASOS row to a Synoptic
        station ID would fabricate provenance) -- byte-identical to the
        pre-Phase-7 shape whenever the supplement is skipped or ASOS
        returns nothing for the window.

    Raises:
        ValueError: If `location` is neither a valid station-ID list nor a
            valid (lat, lon) tuple; if `provider` is not a supported
            provider name; or, for `provider="tceq"` specifically, if
            `location` carries more than one CAMS ID (`daily_summary.pl`
            serves one site per request and the returned frame carries no
            station discriminator column).
    """
    shape = _validate_location_shape(location)

    if shape == "station":
        return _fetch_station(location, start, end, provider)

    lat, lon = location
    return _fetch_grid(lat, lon, start, end, provider)
