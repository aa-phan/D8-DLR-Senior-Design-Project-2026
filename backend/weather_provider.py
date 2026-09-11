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
callers keep calling `fetch_weather(stids, start, end)` and shouldn't need
to change at all.

This module deliberately does NOT implement a second (e.g. NOAA) provider.
Doing so would be resolving the open provider question, which is explicitly
out of scope for this component per the spec's own Open Questions section.

Importing this module has no side effects (no file I/O, no network calls) —
it is safe to import without a `SYNOPTIC_TOKEN` env var set. A token is only
required when `fetch_weather(..., provider="synoptic")` is actually called,
via `dlr_pipeline.fetch_timeseries`'s own token lookup.
"""

import pandas as pd

import dlr_pipeline
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


def fetch_weather(
    stids: list[str],
    start: str,
    end: str,
    provider: str = "synoptic",
) -> pd.DataFrame:
    """
    Fetch weather observations for the given stations and date window,
    behind a provider-agnostic interface.

    Args:
        stids: Station IDs to fetch observations for.
        start: Start of the date window (ISO 8601 string).
        end: End of the date window (ISO 8601 string).
        provider: Which weather provider to use. Only "synoptic" is
            currently implemented; any other value raises ValueError.

    Returns:
        A DataFrame matching the weather-observation subset of
        `PIPELINE_SCHEMA` (C2): air_temp, wind_speed, wind_direction,
        solar_radiation, relative_humidity, indexed by
        (stid, datetime_utc).

    Raises:
        ValueError: If `provider` is not a supported provider name.
    """
    if provider == "synoptic":
        return attach_provenance(dlr_pipeline.fetch_timeseries(stids, start, end), "synoptic")

    raise ValueError(
        f"Unknown weather provider: {provider!r}. Only 'synoptic' is "
        "currently implemented."
    )
