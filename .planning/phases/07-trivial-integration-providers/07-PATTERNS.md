# Phase 7: Trivial-Integration Providers - Pattern Map

**Mapped:** 2026-09-11
**Files analyzed:** 6 (2 modified, 1 config extension, 2 new modules, 3 new/extended test files)
**Analogs found:** 6 / 6

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/asos_provider.py` (new) | service (provider adapter) | request-response (HTTP fetch + normalize) | `backend/dlr_pipeline.py::fetch_timeseries` | exact (same role: HTTP-fetch-and-normalize-to-DataFrame for a weather provider) |
| `backend/open_meteo_provider.py` (new) | service (provider adapter) | request-response (HTTP fetch + normalize) | `backend/dlr_pipeline.py::fetch_timeseries` | exact |
| `backend/weather_provider.py` (modified: `_fetch_station`, `_fetch_grid`) | service (dispatch/adapter) | request-response, event-driven composition | itself — extend existing `_fetch_station`/`_fetch_grid`/`merge_observations` | exact (same file, established D-01..D-05 precedent) |
| `backend/config.py` (modified: add `ASOS_STATIONS`) | config | static lookup | `backend/config.py::CITY_COORDINATES` | exact (same dict shape, same city-keyed convention) |
| `backend/units_def.py` | config/schema (no code change expected) | n/a | itself — `KNOWN_PROVIDER_NAMES` already contains `"asos"`/`"open_meteo"` | exact — no change needed, verify only |
| `backend/tests/asos_provider_test.py` (new) | test | request-response (mocked HTTP) | `backend/tests/dlr_pipeline_test.py` | exact (same mocking pattern: monkeypatch `requests.get` with a `_FakeResponse`) |
| `backend/tests/open_meteo_provider_test.py` (new) | test | request-response (mocked HTTP) | `backend/tests/dlr_pipeline_test.py` | exact |
| `backend/tests/weather_provider_test.py` (extended) | test | request-response / event-driven (merge) | itself — extend existing conventions (`_synthetic_frame`, `_station_frame`/`_grid_frame`, `_FakeResponse`) | exact |

## Pattern Assignments

### `backend/asos_provider.py` (new service module)

**Analog:** `backend/dlr_pipeline.py` (`fetch_timeseries`, lines 108-177) — this is the project's one existing "HTTP GET a weather provider, parse into a DataFrame shaped for the pipeline" function. Also draw the unit-conversion call from `backend/units_def.py::Q`.

**Imports pattern** (`backend/dlr_pipeline.py` lines 16-31):
```python
import os
import math
import json
import logging
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import Optional

from units_def import validate_pipeline_row
import thermal_model
import config
```
For `asos_provider.py`, the equivalent minimal set is:
```python
import logging
import requests
import pandas as pd

from units_def import Q

log = logging.getLogger(__name__)
```

**HTTP fetch + parse core pattern** (`backend/dlr_pipeline.py` lines 124-140, adapted per RESEARCH.md's live-confirmed ASOS shape):
```python
params = {
    "token":    _token(),
    "stid":     ",".join(stids),
    "vars":     ",".join(DLR_VARS),
    ...
}
r = requests.get(f"{SYNOPTIC_BASE}/stations/timeseries", params=params, timeout=120)
r.raise_for_status()
data = r.json()
```
ASOS has no token; use the CSV-parsing + malformed-body-check shape from RESEARCH.md's live-confirmed `fetch_asos_1min` (Code Examples section) as the concrete implementation to copy, including the `"Unknown station provided"` string check (Pitfall 1) and the well-formed-empty-vs-malformed distinction (Pitfall 2, Open Question 1 — treat empty as non-fatal per RESEARCH.md's recommendation, reserve raising for HTTP errors / the "Unknown station" string).

**Unit conversion pattern** (`backend/units_def.py` lines 82-92, 220-233 — `Q._to_base`/`CONVERSIONS`):
```python
from units_def import Q
air_temp = Q(tmpf_value, "degF").to("degC").value
wind_speed = Q(sknt_value, "knots").to("m/s").value
```
Do not hand-roll `(f-32)*5/9` or `*0.514444` — `units_def.Q` already owns both factors (`CONVERSIONS["knots"] = 0.514444` at line 92; `_to_base`'s `degF` branch at lines 224-225).

**Error handling pattern** (`backend/dlr_pipeline.py` line 139, `r.raise_for_status()`, combined with the explicit malformed-body check pattern from `weather_provider.py`'s own `ValueError` style, e.g. lines 337-340):
```python
r = requests.get(ASOS_BASE, params=params, timeout=120)
r.raise_for_status()
if "Unknown station provided" in r.text:
    raise ValueError(f"ASOS: unknown station {station!r} -- check the 3-letter FAA code")
```

**Station-ID lookup pattern** — copy `config.py::CITY_COORDINATES`'s dict shape (lines 146-151) for the new `config.ASOS_STATIONS` dict, keyed identically:
```python
ASOS_STATIONS: dict[str, str] = {
    "AUSTIN": "AUS",
    "CORPUS_CHRISTI": "CRP",
    "MIDLAND": "MAF",
    "EL_PASO": "ELP",
}
```
(3-letter FAA codes per RESEARCH.md Pitfall 1 — NOT the 4-letter ICAO codes used elsewhere in the docs.)

---

### `backend/open_meteo_provider.py` (new service module)

**Analog:** Same as ASOS — `backend/dlr_pipeline.py::fetch_timeseries` for the fetch-and-normalize shape; RESEARCH.md's live-confirmed `fetch_open_meteo` (Code Examples section) is the concrete function to copy verbatim (endpoint, params including `wind_speed_unit=ms` per Pitfall 4, and `pd.to_datetime(..., utc=True)` per Pitfall 3).

**Core pattern** (JSON parse into PIPELINE_SCHEMA-named columns):
```python
r = requests.get(OPEN_METEO_ARCHIVE_BASE, params=params, timeout=60)
r.raise_for_status()
data = r.json()
hourly = data.get("hourly")
if not hourly or not hourly.get("time"):
    raise ValueError("Open-Meteo: malformed or empty response (D-05: fail loud)")
df = pd.DataFrame({
    "datetime_utc": pd.to_datetime(hourly["time"], utc=True),
    "air_temp": hourly["temperature_2m"],
    "wind_speed": hourly["wind_speed_10m"],
    "wind_direction": hourly["wind_direction_10m"],
    "solar_radiation": hourly["shortwave_radiation"],
    "relative_humidity": hourly["relative_humidity_2m"],
})
```
Unlike ASOS, D-05 applies unconditionally here (no "well-formed empty is OK" carve-out — Open-Meteo is a standalone backfill source per D-04, not a supplement, so an empty/malformed response is always a hard failure).

---

### `backend/weather_provider.py` (modify `_fetch_station`, `_fetch_grid`)

**Analog:** the file's own existing `_fetch_station`/`_fetch_grid`/`merge_observations`/`attach_provenance`/`attach_city` — this phase extends established patterns in the same file rather than importing a new style.

**`_fetch_station` extension pattern** (RESEARCH.md's "Wiring the ASOS supplement into `_fetch_station`" Code Example, built directly from the current lines 333-340):
```python
def _fetch_station(stids: list[str], start: str, end: str, provider: str) -> pd.DataFrame:
    if provider == "synoptic":
        synoptic = attach_provenance(dlr_pipeline.fetch_timeseries(stids, start, end), "synoptic")
        synoptic = attach_city(synoptic)

        asos_frames = []
        for city in synoptic["city"].dropna().unique():
            station_code = config.ASOS_STATIONS[city]
            asos_raw = asos_provider.fetch_asos_1min(station_code, start, end)
            if asos_raw.empty:
                continue  # Pitfall 2: real outage, not a failure
            lat, lon = config.CITY_COORDINATES[city]
            asos_tagged = attach_city(attach_provenance(asos_raw, "asos"), lat=lat, lon=lon)
            asos_frames.append(asos_tagged)

        if not asos_frames:
            return synoptic
        asos_combined = pd.concat(asos_frames)
        return merge_observations(synoptic, asos_combined)

    raise ValueError(
        f"Unknown weather provider: {provider!r}. Only 'synoptic' is "
        "currently implemented."
    )
```

**`_fetch_grid` implementation pattern** — replace the current unconditional raise (lines 343-348) with a `provider == "open_meteo"` branch mirroring `_fetch_station`'s `if provider == "synoptic": ... raise` structure:
```python
def _fetch_grid(lat: float, lon: float, start: str, end: str, provider: str) -> pd.DataFrame:
    if provider == "open_meteo":
        frame = open_meteo_provider.fetch_open_meteo(lat, lon, start, end)
        frame = attach_provenance(frame, "open_meteo")
        frame = attach_city(frame, lat=lat, lon=lon)
        return frame

    raise ValueError(
        f"Unknown weather provider: {provider!r}. Only 'open_meteo' is "
        "currently implemented on the grid path."
    )
```
Both branches reuse `attach_provenance`/`attach_city`/`merge_observations` unmodified per RESEARCH.md Pattern 1 and Don't Hand-Roll — do not write a new merge function for ASOS.

**Imports to add** at the top of `weather_provider.py` (alongside existing `import dlr_pipeline` at line 31):
```python
import asos_provider
import open_meteo_provider
```

---

### `backend/config.py` (add `ASOS_STATIONS`)

**Analog:** `backend/config.py::CITY_COORDINATES` (lines 146-151) — same dict shape, same city-keys, same section-comment-block convention used throughout this file (see the `STATIC_RATINGS`/`RATING_BOUNDS_BY_LOCATION` sections' explanatory-comment style at lines 21-46, 53-68).

**Pattern to copy:**
```python
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
```

---

### `backend/tests/asos_provider_test.py` (new) and `backend/tests/open_meteo_provider_test.py` (new)

**Analog:** `backend/tests/dlr_pipeline_test.py` (`_FakeResponse` + `monkeypatch.setattr(dlr_pipeline.requests, "get", ...)` pattern, seen reused verbatim inside `backend/tests/weather_provider_test.py` lines 251-291).

**Test structure to copy** (from `weather_provider_test.py` lines 251-291, which itself follows `dlr_pipeline_test.py`'s convention):
```python
class _FakeResponse:
    def __init__(self, payload_or_text):
        self._payload_or_text = payload_or_text

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload_or_text

    @property
    def text(self):
        return self._payload_or_text


def test_fetch_asos_1min_parses_csv_into_expected_columns(monkeypatch):
    csv_text = (
        "station,station_name,lat,lon,valid(UTC),tmpf,sknt,drct\n"
        "AUS,Austin Bergstrom Intl,30.1830,-97.6799,2024-07-01 00:00,95,7,142\n"
    )
    monkeypatch.setattr(
        asos_provider.requests, "get", lambda *a, **k: _FakeResponse(csv_text)
    )
    frame = asos_provider.fetch_asos_1min("AUS", "2024-07-01T00:00Z", "2024-07-01T00:05Z")
    assert "air_temp" in frame.columns
    assert "wind_speed" in frame.columns


def test_fetch_asos_1min_raises_on_unknown_station(monkeypatch):
    monkeypatch.setattr(
        asos_provider.requests, "get",
        lambda *a, **k: _FakeResponse("ERROR: Unknown station provided: KAUS"),
    )
    with pytest.raises(ValueError):
        asos_provider.fetch_asos_1min("KAUS", "2024-07-01T00:00Z", "2024-07-01T00:05Z")
```
Module-level plain-`assert` functions, no test classes — matches every existing test file's convention (`weather_provider_test.py` docstring lines 1-13 explicitly documents this as the established convention to follow).

**No-network-on-import test** — copy `weather_provider_test.py::test_module_import_has_no_side_effects` (lines 111-121) verbatim for both new provider modules, since `weather_provider.py`'s own docstring (lines 20-23) establishes "importing this module has no side effects" as a project-wide invariant for provider adapters.

---

### `backend/tests/weather_provider_test.py` (extend)

**Analog:** itself — extend using the file's own established helpers (`_synthetic_frame` lines 26-34, `_station_frame`/`_grid_frame` lines 298-333, `_mock_grid_provider`/`_end_to_end_merged_frame` lines 463-511) rather than inventing new fixtures.

**Pattern for ASOS-supplement dispatch test** (mirrors `test_dispatch_station_list_routes_to_the_station_path`, lines 132-145, plus the merge-provenance assertions from `test_merge_provenance_names_the_actual_supplier_per_field`, lines 358-372):
```python
def test_station_fetch_is_transparently_supplemented_by_asos(monkeypatch):
    synoptic_frame = _synthetic_frame(
        air_temp=[25.0], wind_speed=[5.0], wind_direction=[180.0], lat=[30.2711], lon=[-97.7437],
    )
    monkeypatch.setattr(dlr_pipeline, "fetch_timeseries", lambda *a, **k: synoptic_frame)
    asos_frame = pd.DataFrame({
        "datetime_utc": pd.to_datetime(["2025-07-01T00:01:00Z"]),
        "air_temp": [25.2], "wind_speed": [5.1], "wind_direction": [181.0],
    })
    monkeypatch.setattr(asos_provider, "fetch_asos_1min", lambda *a, **k: asos_frame)

    result = weather_provider.fetch_weather(["KAUS"], _START, _END)

    assert len(result) == 2  # union-of-timestamps, D-01
    assert (result["wind_source"] == "asos").sum() == 1
```

**Pattern for Open-Meteo grid dispatch test** (mirrors `test_dispatch_latlon_tuple_routes_to_the_grid_path`, lines 148-161, but asserting success instead of raise):
```python
def test_grid_fetch_dispatches_to_open_meteo(monkeypatch):
    fake_frame = pd.DataFrame({
        "datetime_utc": pd.to_datetime(["2025-07-01T00:00:00Z"]),
        "air_temp": [29.9], "wind_speed": [3.4], "wind_direction": [160.0],
        "solar_radiation": [291.0], "relative_humidity": [63.0],
    })
    monkeypatch.setattr(open_meteo_provider, "fetch_open_meteo", lambda *a, **k: fake_frame)

    result = weather_provider.fetch_weather((30.2711, -97.7437), _START, _END, provider="open_meteo")

    assert (result["solar_source"] == "open_meteo").all()
```

## Shared Patterns

### HTTP fetch-and-normalize (both new providers)
**Source:** `backend/dlr_pipeline.py::fetch_timeseries` (lines 108-177)
**Apply to:** `backend/asos_provider.py`, `backend/open_meteo_provider.py`
```python
r = requests.get(BASE_URL, params=params, timeout=<seconds>)
r.raise_for_status()
# parse into a pd.DataFrame with datetime_utc + PIPELINE_SCHEMA-named columns
```

### Provenance tagging
**Source:** `backend/weather_provider.py::attach_provenance` (lines 49-96), `PROVENANCE_FIELD_MAP` (lines 41-46)
**Apply to:** both new providers' output, wired inside `_fetch_station`/`_fetch_grid`
```python
frame = attach_provenance(frame, "asos")   # or "open_meteo"
```
Already validates against `units_def.KNOWN_PROVIDER_NAMES`, which already contains both names — no schema change needed.

### City attribution
**Source:** `backend/weather_provider.py::attach_city` (lines 139-192)
**Apply to:** both new providers, using the two-keyword form since the target city is always already known (RESEARCH.md Pattern 2)
```python
lat, lon = config.CITY_COORDINATES[city]
frame = attach_city(frame, lat=lat, lon=lon)
```

### Union-of-timestamps merge (ASOS only)
**Source:** `backend/weather_provider.py::merge_observations` (lines 229-284) — reused unmodified per RESEARCH.md Pattern 1, empirically verified to already satisfy D-01/D-02
```python
merge_observations(synoptic_frame, asos_combined_frame)
```
Do not write a new merge function for this case.

### Fail-loud on malformed/erroring responses (D-05)
**Source:** `backend/weather_provider.py`'s existing `ValueError` style (e.g. lines 337-340, 344-348, 208-224)
**Apply to:** both new providers' HTTP-error and malformed-body paths
```python
raise ValueError(f"<Provider>: <specific reason> -- <what caller should check>")
```
Exception: a well-formed, zero-row ASOS response for a real outage window is non-fatal (return empty, don't raise) — Open-Meteo has no such carve-out (D-04: standalone source, always fail loud on empty/malformed).

## No Analog Found

None — every file in this phase has a strong, exact-role analog already in the codebase (Phase 6 built these seams specifically to make Phase 7 "cheap," per RESEARCH.md's Key Insight).

## Metadata

**Analog search scope:** `backend/` (source modules), `backend/tests/` (test conventions)
**Files scanned:** `backend/weather_provider.py`, `backend/units_def.py`, `backend/dlr_pipeline.py`, `backend/config.py`, `backend/tests/weather_provider_test.py`, `backend/tests/dlr_pipeline_test.py` (all read in full this session; all confirmed git-tracked via `git ls-files`)
**Pattern extraction date:** 2026-09-11
