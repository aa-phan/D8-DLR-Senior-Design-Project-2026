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

This module deliberately does NOT implement a second (e.g. NOAA) provider.
Doing so would be resolving the open provider question, which is explicitly
out of scope for this component per the spec's own Open Questions section.

Importing this module has no side effects (no file I/O, no network calls) —
it is safe to import without a `SYNOPTIC_TOKEN` env var set. A token is only
required when `fetch_weather(..., provider="synoptic")` is actually called,
via `dlr_pipeline.fetch_timeseries`'s own token lookup.
"""

import math

import pandas as pd

import config
import dlr_pipeline
import station_explorer
import units_def

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


def _fetch_station(stids: list[str], start: str, end: str, provider: str) -> pd.DataFrame:
    if provider == "synoptic":
        return attach_provenance(dlr_pipeline.fetch_timeseries(stids, start, end), "synoptic")

    raise ValueError(
        f"Unknown weather provider: {provider!r}. Only 'synoptic' is "
        "currently implemented."
    )


def _fetch_grid(lat: float, lon: float, start: str, end: str, provider: str) -> pd.DataFrame:
    raise ValueError(
        "No grid weather provider is registered yet -- the first one "
        "(NSRDB or Open-Meteo) lands in Phase 7. A (lat, lon) grid request "
        "cannot be served by any provider today."
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
        provider: Which weather provider to use. Only "synoptic" is
            currently implemented on the station path; any other value
            raises ValueError.

    Returns:
        A DataFrame matching the weather-observation subset of
        `PIPELINE_SCHEMA` (C2): air_temp, wind_speed, wind_direction,
        solar_radiation, relative_humidity, indexed by
        (stid, datetime_utc).

    Raises:
        ValueError: If `location` is neither a valid station-ID list nor a
            valid (lat, lon) tuple, or if `provider` is not a supported
            provider name.
    """
    shape = _validate_location_shape(location)

    if shape == "station":
        return _fetch_station(location, start, end, provider)

    lat, lon = location
    return _fetch_grid(lat, lon, start, end, provider)
