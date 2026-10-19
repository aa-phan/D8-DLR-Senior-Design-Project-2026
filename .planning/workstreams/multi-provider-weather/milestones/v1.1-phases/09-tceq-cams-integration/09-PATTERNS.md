# Phase 9: TCEQ CAMS Integration - Pattern Map

**Mapped:** 2026-09-13
**Files analyzed:** 5
**Analogs found:** 5 / 5

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/tceq_provider.py` (new) | service (provider adapter) | file-I/O (HTML scrape, per-day request loop) | `backend/asos_provider.py` | role-match (also borrow error/malformed-detection shape from `nsrdb_provider.py`) |
| `backend/weather_provider.py::_fetch_station` (modified) | controller/dispatch | request-response | same file, existing `"synoptic"` branch (line 441-452) and `_fetch_grid`'s `"nsrdb"` branch (line 470-482) | exact |
| `backend/config.py::TCEQ_STATIONS` (new dict) | config | CRUD (static lookup) | `backend/config.py::ASOS_STATIONS` (line 252-257) | exact |
| `backend/tests/tceq_provider_test.py` (new) | test | request-response (mocked HTTP) | `backend/tests/asos_provider_test.py` | exact (structure); pull malformed-response test idea from `nsrdb_provider.py`'s error-shape handling |
| `backend/tests/weather_provider_test.py` (modified — add tceq dispatch test) | test | request-response | same file's existing Synoptic dispatch tests | exact |

`backend/units_def.py` and `backend/requirements.txt` (bs4 pin fix) are also touched per RESEARCH.md
(Pitfall 8) but require no new pattern — `"tceq"` is already registered in `KNOWN_PROVIDER_NAMES`,
and the `requirements.txt` edit is a one-line typo fix (`bs4 4.14.3` → `bs4==4.14.3`), not a new file.

## Pattern Assignments

### `backend/tceq_provider.py` (service, file-I/O / HTML scrape)

**Primary analog:** `backend/asos_provider.py` (module shape, unit conversion, range check)
**Secondary analog:** `backend/nsrdb_provider.py` (malformed-response detection, per-period-loop-then-concat shape)

**Module docstring / no-side-effects-on-import contract** (asos_provider.py lines 1-14):
```python
"""
ASOS 1-minute Provider Adapter (C4, Phase 7 / WX-02)
=====================================================
...
Importing this module has no side effects (no file I/O, no network calls,
no environment variable reads), mirroring `weather_provider.py`'s own
no-side-effects-on-import contract. A network call only happens when
`fetch_asos_1min` is actually called.
"""
```
Apply the same contract to `tceq_provider.py`: no network call at import time; `fetch_tceq` is the
only function that calls `requests.get`.

**Imports pattern** (asos_provider.py lines 16-25):
```python
import logging
from io import StringIO

import pandas as pd
import requests

import units_def
from units_def import Q

log = logging.getLogger(__name__)
```
For `tceq_provider.py`, add `from bs4 import BeautifulSoup` per RESEARCH.md's Standard Stack (use
`"html.parser"` backend, no new `lxml` pin). No `StringIO` needed (HTML text is passed directly to
`BeautifulSoup`, not `pd.read_csv`).

**Fixed constants, never built from caller input** (asos_provider.py lines 27-31):
```python
ASOS_BASE: str = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos1min.py"
ASOS_VARS: tuple[str, ...] = ("tmpf", "sknt", "drct")

_RETURN_COLUMNS = ["datetime_utc", "air_temp", "wind_speed", "wind_direction"]
```
For TCEQ: `TCEQ_BASE`, `_RETURN_COLUMNS = ["datetime_utc", "air_temp", "wind_speed",
"wind_direction", "relative_humidity"]`, plus the fixed per-site UTC-offset dict
(`TCEQ_FIXED_UTC_OFFSET_HOURS`, given verbatim in 09-RESEARCH.md Pattern 3) and the exact-match
label map (`TARGET_LABELS`, given verbatim in 09-RESEARCH.md Pattern 2).

**Timestamp coercion helper** (asos_provider.py lines 34-54, `_to_asos_timestamp`):
```python
def _to_asos_timestamp(value: str) -> str:
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"asos_provider: cannot parse timestamp {value!r}: {exc}") from exc

    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")

    return ts.strftime("%Y-%m-%dT%H:%MZ")
```
`nsrdb_provider.py`'s `_to_utc_timestamp` (lines 311-331) is the same coercion returning a
`pd.Timestamp` instead of a formatted string — use that variant for TCEQ since the per-day loop
(D-09) needs `.year`/`.month`/`.day` components, matching `nsrdb_provider._window_bounds` /
`_years_spanned`'s shape (lines 334-392) but looped by **calendar day** instead of calendar year.

**Per-period-loop-then-concat shape** (nsrdb_provider.py `fetch_nsrdb`, lines 395-499, especially
444-487): loop over spanned periods (years there, days here per D-09), issue one request per
period, parse into a `[datetime_utc, <fields>]` frame, `pd.concat` all period frames, filter/sort/
dedupe, then run `_range_check`. This is the direct template for `fetch_tceq`'s per-calendar-day
loop over `daily_summary.pl`.

**Malformed/unreachable-response detection before parse** — new pattern, not present in ASOS/NSRDB
verbatim (ASOS checks a substring in CSV text; NSRDB checks HTTP status + JSON/CSV error body).
09-RESEARCH.md's own Code Examples section gives the exact TCEQ-specific version (already
research-verified against live `cams=999999`):
```python
def _validate_response(html: str, cams_id: str) -> BeautifulSoup:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    site_link = h1.find("a", href=lambda h: h and f"CAMS={cams_id}" in h) if h1 else None
    data_table = soup.find("table", attrs={"border": "1"})
    if site_link is None or data_table is None:
        raise ValueError(
            f"tceq_provider: no site-specific report found for CAMS {cams_id!r} -- "
            "the endpoint returned the generic site-selection form instead of a report "
            "(unreachable, unknown CAMS ID, or the report page's structure changed)."
        )
    return data_table
```
This mirrors ASOS's "status alone is not a trust signal" lesson (asos_provider.py lines 103-106,
"Unknown station provided" substring check) — same *shape* (structural response check, not just
HTTP status), different mechanism (HTML structure vs CSV substring).

**Row/field extraction with placeholder handling** — new pattern (09-RESEARCH.md Code Examples,
Pitfall 2/4/Pattern 2 combined):
```python
TARGET_LABELS = {
    "Wind Speed": "wind_speed",
    "Wind Direction": "wind_direction",
    "Outdoor Temperature": "air_temp",
    "Relative Humidity": "relative_humidity",
}
for row in table.find_all("tr"):
    label_cell = row.find("strong")
    if label_cell is None:
        continue
    label_text = label_cell.get_text(strip=True)
    if label_text not in TARGET_LABELS:      # exact match, never `in` / substring
        continue
    ...
```
and per-cell parsing:
```python
def _extract_row_values(data_table, label: str) -> list[float | None]:
    for row in data_table.find_all("tr"):
        strong = row.find("strong")
        if strong is None or strong.get_text(strip=True) != label:
            continue
        cells = row.find_all("td")
        hourly_cells = cells[1:-2]
        values = []
        for cell in hourly_cells:
            text = cell.get_text(strip=True)
            try:
                values.append(float(text))
            except ValueError:
                values.append(None)   # "FEW" / "NA" placeholder -- not an error
            values.append(None)
        return values
    return []   # row not present at all -- site doesn't monitor this parameter
```
D-04/D-07 semantics: absence of a row entirely (empty list returned) means "site doesn't monitor
this field" → null for RH (D-04), raise for wind_speed/wind_direction/air_temp (D-07).

**Unit conversion — never hand-roll** (asos_provider.py lines 141-146):
```python
df["air_temp"] = tmpf.apply(
    lambda v: Q(v, "degF").to("degC").value if pd.notna(v) else None
)
df["wind_speed"] = sknt.apply(
    lambda v: Q(v, "knots").to("m/s").value if pd.notna(v) else None
)
```
For TCEQ: `Q(v, "mph").to("m/s")` for wind speed, `Q(v, "degF").to("degC")` for air_temp
(both units already registered in `units_def.py` lines 41/46 — no schema change needed).
Wind direction and relative_humidity pass through unconverted (already degrees / percent).

**Fixed (never-DST) UTC offset application** — new pattern, TCEQ-specific (09-RESEARCH.md
Pattern 3): apply `TCEQ_FIXED_UTC_OFFSET_HOURS[cams_id]` as a plain integer-hour offset to each
row's local-standard-time hour to build `datetime_utc` — never `zoneinfo`/`pytz`.

**Range-check backstop** (asos_provider.py lines 165-193, `_range_check`):
```python
def _range_check(frame: pd.DataFrame) -> None:
    for column in ("air_temp", "wind_speed", "wind_direction"):
        if column not in frame.columns:
            continue
        lo, hi = units_def.PIPELINE_SCHEMA[column]["range"]
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        out_of_range = values[(values < lo) | (values > hi)]
        if not out_of_range.empty:
            bad_value = out_of_range.iloc[0]
            raise ValueError(
                f"asos_provider: converted value {bad_value!r} for column "
                f"{column!r} is outside PIPELINE_SCHEMA's range "
                f"[{lo}, {hi}] -- check for a native-unit value that was "
                "never converted."
            )
```
Copy this pattern verbatim into `tceq_provider._range_check`, adding `"relative_humidity"` to the
checked-columns tuple (own-module error-message prefix `"tceq_provider:"`).

**D-06/D-07 raise-on-missing-required-field** — apply after the per-day concat, before return,
modeled on nsrdb_provider.py's empty-result raise (lines 489-495):
```python
if combined.empty:
    raise ValueError(
        f"nsrdb_provider: window [{start_ts}, {end_ts}] selected zero "
        f"rows across {len(years)} year(s) of NSRDB data -- raising "
        "rather than returning an empty frame a caller could mistake "
        "for night-time (07-CONTEXT.md D-05)."
    )
```
For TCEQ: raise if `wind_speed`, `wind_direction`, or `air_temp` is entirely absent (row never
found across any fetched day) — this is the D-07 "missing needed field" condition, distinct from
per-hour null values (which are fine) and distinct from RH absence (which is never a raise reason,
D-04).

---

### `backend/weather_provider.py::_fetch_station` (controller/dispatch, request-response)

**Analog:** same file, existing `"synoptic"` branch (lines 441-452) and `_fetch_grid`'s `"nsrdb"`
branch (lines 470-482).

**Current synoptic branch** (lines 441-452):
```python
def _fetch_station(stids: list[str], start: str, end: str, provider: str) -> pd.DataFrame:
    if provider == "synoptic":
        return _supplement_with_asos(
            attach_provenance(dlr_pipeline.fetch_timeseries(stids, start, end), "synoptic"),
            start,
            end,
        )

    raise ValueError(
        f"Unknown weather provider: {provider!r}. Only 'synoptic' is "
        "currently implemented."
    )
```

**nsrdb grid branch, for the attach_provenance + attach_city + raise-on-unresolved-city shape**
(lines 470-482):
```python
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
```

**New `"tceq"` branch to add** (per RESEARCH.md Open Question 1's recommendation — `stids` is a
list of CAMS IDs, no city-resolution needed inside `_fetch_station` itself, matching the Synoptic
branch's simplicity):
```python
if provider == "tceq":
    frame = tceq_provider.fetch_tceq(stids[0], start, end)
    return attach_provenance(frame, "tceq")

if provider == "synoptic":
    ...  # existing branch unchanged

raise ValueError(
    f"Unknown weather provider: {provider!r}. Only 'synoptic' and 'tceq' "
    "are currently implemented."
)
```
Also add `import tceq_provider` to the imports block (lines 42-48, alongside `asos_provider`,
`nsrdb_provider`, `open_meteo_provider`). `attach_provenance(frame, "tceq")` needs no change —
`"tceq"` is already in `KNOWN_PROVIDER_NAMES` (units_def.py line 331) and `PROVENANCE_FIELD_MAP`
(weather_provider.py lines 58-63) already covers `wind_source`/`temp_source`/`humidity_source`,
which is exactly D-05's null-RH-row mechanism.

---

### `backend/config.py::TCEQ_STATIONS` (config, CRUD/static lookup)

**Analog:** `backend/config.py::ASOS_STATIONS` (lines 252-257):
```python
ASOS_STATIONS: dict[str, str] = {
    "AUSTIN": "AUS",
    "CORPUS_CHRISTI": "CRP",
    "MIDLAND": "MAF",
    "EL_PASO": "ELP",
}
```

**New dict to add** (09-RESEARCH.md Pattern 1, already research-verified CAMS IDs):
```python
TCEQ_STATIONS: dict[str, str] = {
    "AUSTIN": "38",           # Audubon C38 -- true Wind Direction (not resultant-only), no RH
    "CORPUS_CHRISTI": "83",   # Corpus Christi Palm C83 -- WS+WD+Temp+RH all live-confirmed
    "MIDLAND": "1095",        # Midland Avalon Drive C1095 -- true WD (added 2026-05-01), no RH
    "EL_PASO": "41",          # Chamizal C41 -- WS+WD+Temp+RH+solar all live-confirmed, most complete of the four
}
```
Place immediately adjacent to `ASOS_STATIONS` in `config.py`, same dict shape (`dict[str, str]`
keyed by the same four literal `CITY_COORDINATES` keys).

---

### `backend/tests/tceq_provider_test.py` (test, request-response / mocked HTTP)

**Analog:** `backend/tests/asos_provider_test.py` (full file convention, lines 1-60 shown).

**Module docstring + fixture/mock convention** (lines 1-53):
```python
"""
Tests for backend/asos_provider.py (C4, Phase 7 / WX-02).
...
Follows backend/tests/dlr_pipeline_test.py's `_FakeResponse` +
`monkeypatch.setattr(module.requests, "get", ...)` convention (also reused
in weather_provider_test.py) to avoid a live network call. Module-level
plain-assert functions, no test classes -- matches every existing test
file's convention in this project.
"""

import re
import pandas as pd
import pytest
import requests
import units_def
from units_def import Q
import asos_provider

class _FakeResponse:
    def __init__(self, text):
        self._text = text

    def raise_for_status(self):
        pass

    @property
    def text(self):
        return self._text

def _mock_get(monkeypatch, text):
    monkeypatch.setattr(asos_provider.requests, "get", lambda *a, **k: _FakeResponse(text))
```
For `tceq_provider_test.py`: replace CSV fixture strings with small hand-built HTML fixture
strings matching `daily_summary.pl`'s confirmed table shape (one `<table border='1'>`, one `<tr>`
per parameter with a `<strong>` label cell and `<td>` hourly cells) — build one fixture per test
case (happy path with RH, no-RH site, missing-required-field site, malformed/invalid-CAMS-ID
response with no `<table border='1'>` and no matching `<h1><a>`). `_mock_get` should
`monkeypatch.setattr(tceq_provider.requests, "get", ...)`, same convention, but note `_fetch_one_day`
is called once per calendar day (D-09) — the multi-day test should track call count/params via a
list-based fake rather than a single fixed response, to assert one request per calendar day
(mirrors the RESEARCH.md-recommended `test_fetch_tceq_multi_day_window_issues_one_request_per_day`).

**Test-name-to-behavior mapping** — the exact test list to build (from 09-RESEARCH.md Validation
Architecture table): `test_fetch_tceq_parses_into_pipeline_columns`,
`test_fetch_tceq_converts_units`, `test_fetch_tceq_applies_fixed_utc_offset_no_dst`,
`test_fetch_tceq_leaves_rh_null_when_site_has_no_rh_row`,
`test_fetch_tceq_raises_when_required_field_row_absent`,
`test_fetch_tceq_raises_on_malformed_response`, `test_fetch_tceq_treats_few_and_na_as_null`,
`test_fetch_tceq_multi_day_window_issues_one_request_per_day`.

---

### `backend/tests/weather_provider_test.py` (test, request-response — add tceq dispatch test)

**Analog:** existing Synoptic dispatch test in the same file (search for
`test_dispatch_station_list_routes_to_the_station_path` — same file already monkeypatches
`dlr_pipeline`/`asos_provider`/`nsrdb_provider` module functions the same way
`asos_provider_test.py` does). New test: `test_dispatch_tceq_provider_routes_to_new_branch` —
monkeypatch `weather_provider.tceq_provider.fetch_tceq` to return a small fixed frame, call
`fetch_weather(["38"], start, end, provider="tceq")`, assert the returned frame carries
`temp_source`/`wind_source`/`humidity_source` == `"tceq"` where the corresponding data column is
non-null (same assertion shape `attach_provenance`'s existing tests already use for nsrdb/asos).

---

## Shared Patterns

### Unit conversion via `units_def.Q` — never hand-rolled
**Source:** `backend/asos_provider.py` lines 141-146; `backend/units_def.py` lines 41, 46
(`"degF"`, `"mph"` already registered).
**Apply to:** `tceq_provider.py`'s air_temp and wind_speed columns.

### Range-check backstop after unit conversion
**Source:** `backend/asos_provider.py::_range_check` (lines 165-193), `backend/nsrdb_provider.py::_range_check`
(lines 289-308).
**Apply to:** `tceq_provider.py::_range_check`, called once at the end of `fetch_tceq` before
return, covering `air_temp`, `wind_speed`, `wind_direction`, `relative_humidity`.

### Provenance tagging — reused as-is, no modification
**Source:** `backend/weather_provider.py::attach_provenance` / `PROVENANCE_FIELD_MAP` (lines
52-113).
**Apply to:** The new `"tceq"` branch in `_fetch_station` — call `attach_provenance(frame, "tceq")`
exactly once, no field-map change needed. This is D-05's entire mechanism for null-RH provenance.

### Fail-loud on malformed/unreachable/missing-required-field response
**Source:** `backend/asos_provider.py` lines 107-122 (string-check + header-check, both raise
`ValueError`); `backend/nsrdb_provider.py` lines 489-495 (empty-result raise).
**Apply to:** `tceq_provider.py`'s `_validate_response` (per-day malformed check, D-06) and the
post-concat missing-required-field check (D-07). Both raise plain `ValueError` prefixed
`"tceq_provider: ..."`, never a silent fallback or empty-frame return.

### No-network-on-import module contract
**Source:** `backend/asos_provider.py` lines 9-14; `backend/nsrdb_provider.py` lines 8-11.
**Apply to:** `tceq_provider.py` — no `requests.get` call, no env-var read, at import time; only
inside `fetch_tceq`.

## No Analog Found

None — every file in this phase's scope has a strong, directly-reusable analog from Phase 7/8's
provider modules and Phase 6/7's dispatch/config/test conventions.

## Metadata

**Analog search scope:** `backend/` (provider modules, `weather_provider.py`, `config.py`,
`units_def.py`), `backend/tests/`.
**Files scanned:** `backend/asos_provider.py`, `backend/nsrdb_provider.py`,
`backend/weather_provider.py`, `backend/config.py`, `backend/units_def.py`,
`backend/tests/asos_provider_test.py`.
**Pattern extraction date:** 2026-09-13
