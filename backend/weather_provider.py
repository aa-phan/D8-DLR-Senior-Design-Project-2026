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
        return dlr_pipeline.fetch_timeseries(stids, start, end)

    raise ValueError(
        f"Unknown weather provider: {provider!r}. Only 'synoptic' is "
        "currently implemented."
    )
