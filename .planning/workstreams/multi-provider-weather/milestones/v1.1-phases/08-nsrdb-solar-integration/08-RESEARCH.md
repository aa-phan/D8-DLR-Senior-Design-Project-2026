# Phase 8: NSRDB Solar Integration - Research

**Researched:** 2026-09-12
**Domain:** NREL/NLR NSRDB PSM v4 (GOES CONUS) solar-irradiance REST API, wired as a new grid-path provider behind Phase 6/7's `weather_provider.py` adapter
**Confidence:** HIGH (API contract) / MEDIUM (year-out-of-range exact error text, GHI response units) — see Metadata

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** The NREL developer API key (`developer.nrel.gov`) is **not yet registered** as of
  this discussion. This phase is planned now so it's ready, but the live-fetch execution tasks
  cannot run to completion until the key is issued. The plan must surface this explicitly as a
  documented checkpoint/precondition rather than assuming the key exists at execution time. —
  **Reversibility:** reversible — no code depends on the key existing at plan time; it only
  blocks running the live-network tasks.
- **D-02:** NSRDB's PSM v4 response includes 23 variables, including `wind_speed`,
  `wind_direction`, `air_temperature`, and `relative_humidity` alongside solar
  (`ghi`/`dni`/`dhi`). NREL's own documentation states the wind field ("2m MERRA-2 reanalysis")
  "should not be used for wind power calculations" — `data_provider.md`'s vetting already flagged
  this as untrustworthy for IEEE 738. The adapter populates **only `solar_radiation`** from the
  NSRDB response; `wind_speed`, `wind_direction`, `air_temp`, and `relative_humidity` stay null
  on NSRDB-sourced rows even though the raw response contains values for them, so nothing
  downstream (thermal model, anomaly detector, fail-safe gates) can accidentally consume the
  untrustworthy reanalysis wind data. — **Reversibility:** costly — once downstream code is
  written assuming NSRDB rows never carry wind/temp/humidity, later deciding to surface those
  fields means auditing every consumer for accidental reliance on the null.
- **D-03:** Fetch NSRDB data via **raw HTTP requests** (`requests`, matching the exact pattern
  already used for ASOS and Open-Meteo in Phase 7 — see `backend/asos_provider.py` and
  `backend/open_meteo_provider.py`), not `pvlib.iotools.get_psm3`. This keeps the provider
  modules consistent with each other and avoids adding `pvlib` as a new project dependency for
  what NREL's own REST API + CSV response already makes straightforward without it.
- **D-04:** Request NSRDB data at **60-minute intervals** (of the {5, 15, 30, 60} options NSRDB
  supports), matching Open-Meteo's hourly cadence from Phase 7 and TCEQ's typical reporting
  interval. GHI does not vary enough minute-to-minute at ampacity-relevant timescales to justify
  the row-count cost of finer resolution for this phase's scope.
- **D-05:** NSRDB is wired as a new `provider="nsrdb"` branch inside `_fetch_grid`, parallel to
  the existing `provider="open_meteo"` branch from Phase 7 — same dispatch function, same
  `attach_provenance`/`attach_city` post-processing, same lat/lon-based signature. It is reachable
  only via the grid path; station-based calls (`_fetch_station`) never trigger it.

### Claude's Discretion

- Exact NSRDB request parameter names/values (`attributes` list limited to `ghi` plus whatever
  minimum set the API requires, `interval=60`, `utc=true`, date formatting) — confirm exact API
  contract during research, since no live pull has been confirmed yet per `data_provider.md`.
  **Resolved by this research (see Architecture Patterns, Code Examples): `attributes=ghi` alone
  is a legal request with no forced companion fields — live-verified.**
- Whether the API-key-absent case is a `ValueError` at call time (matching the existing
  `dlr_pipeline._token()` / `SYNOPTIC_TOKEN` precedent: "set env var or raise, naming the
  variable") or something else — default to that exact precedent unless research finds a reason
  not to. **Correction found during this research (see Pitfall 1): `dlr_pipeline._token()`
  actually raises `EnvironmentError` (an alias of `OSError` in Python 3), not `ValueError`. The
  precedent to replicate is the message-naming-the-variable *pattern*, not the exception type
  literally called "ValueError" as CONTEXT.md's phrasing assumed.**
- Historical-depth handling: NSRDB PSM v4 GOES CONUS only covers 2018–2025 — if a request falls
  outside that window, follow the fail-loud precedent (D-05 from Phase 7 CONTEXT.md): raise
  rather than silently returning nothing or a different product's data. **Partially resolved
  (see Pitfall 3 / Open Questions): the endpoint does reject an out-of-range year with HTTP 400,
  but the exact error text could not be isolated live without a real API key — DEMO_KEY's
  mandatory email-validation error always appears first in the `errors` array.**
- Exact module name/location for the new provider (`backend/nsrdb_provider.py`, following the
  `asos_provider.py`/`open_meteo_provider.py` naming convention already established).

### Deferred Ideas (OUT OF SCOPE)

- **Fallback/primary-selection logic** (if NSRDB fails, fall back to Synoptic or another provider)
  was raised implicitly by the ROADMAP checkpoint note but is explicitly WX-06 / Phase 10 scope —
  not this phase.
- **Live execution of the NSRDB fetch tasks** is blocked on the NREL API key registration
  completing (D-01). Planning proceeds now; running the plan's live-network verification tasks
  should wait for the key, or be executed with an explicit human checkpoint confirming the key is
  available.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| WX-03 | Given a target city and time window, the system fetches solar irradiance (GHI) from NREL NSRDB (PSM v4) as the primary solar source, using a registered NREL developer API key stored the same way `SYNOPTIC_TOKEN` is (`.env`/environment only, never committed). | Full API contract (endpoint, params, error shapes) live-verified against the real host in this session (Standard Stack, Code Examples); env-var-or-raise pattern corrected against the actual `dlr_pipeline._token()` source (Pitfall 1); `PIPELINE_SCHEMA`/`KNOWN_PROVIDER_NAMES` confirmed to need no changes (Architectural note below); multi-year request chunking requirement discovered and documented (Pitfall 2 — the single most consequential finding of this research). |
</phase_requirements>

## Summary

This phase's API contract was **live-verified against the real production host in this session**,
not just cited from documentation — a materially stronger evidence tier than `data_provider.md`'s
original vetting pass, which explicitly noted "no API key was obtained, so no actual data pull was
performed." Three findings from that live verification change what the planner needs to account
for.

**First, and most important for scope framing:** NREL's developer portal has been institutionally
renamed. `developer.nrel.gov` **no longer resolves via DNS** (confirmed via `curl`/`WebFetch`
failures this session); the live, working host is **`developer.nlr.gov`**, branded "National
Laboratory of the Rockies" (NLR) — confirmed by fetching `developer.nlr.gov/docs/rate-limits/`
directly, whose page footer reads "National Laboratory of the Rockies... operated under Contract
No. DE-AC36-08GO28308" (the same DOE contract number historically associated with NREL). The
migration is incomplete on NREL's side: a live "no api_key" error response still points users to
`https://developer.nrel.gov/signup/` — a dead link. `.planning/`, `data_provider.md`, and
`REQUIREMENTS.md`'s WX-03 wording all say "NREL" / "developer.nrel.gov"; this is now a stale
reference to a renamed host, not a wrong host. **This does not block the phase** (the API works
identically at the new host) but the planner should point the provider module's docstring/base-URL
comment at `developer.nlr.gov` and flag the naming discrepancy for the team, since "NREL API key"
language will persist in requirements/env-var-naming even though the literal current org name has
changed. See Assumptions Log A1 and Open Questions.

**Second, the most consequential functional finding:** the NSRDB CSV download endpoint is
**year-scoped, not date-range-scoped**. Its `names` parameter takes exactly one calendar year and
the CSV-direct-download mode is documented as "restricted to use with only a single POINT, for a
single YEAR at a time" (NREL/NLR docs, cross-confirmed against `pvlib`'s `get_nsrdb_psm4_conus`
source, which takes a single `year` argument and returns that year's full dataset with no separate
start/end parameters at all). Unlike `asos_provider.fetch_asos_1min` and
`open_meteo_provider.fetch_open_meteo`, which pass `start`/`end` straight through to their
respective APIs, `nsrdb_provider.py`'s `fetch_nsrdb(lat, lon, start, end)` must (1) compute the set
of calendar years spanned by `[start, end]` in UTC, (2) issue one HTTP request per year, (3)
concatenate, and (4) filter down to the actual requested window. A request spanning a year
boundary (e.g. `2023-12-20` to `2024-01-10`) requires two API calls, not one. This has no analogue
in the Phase 7 providers and must be budgeted as its own implementation task.

**Third:** the response's `wkt` point parameter takes **longitude first, then latitude**
(`POINT(lon lat)`) — confirmed directly from `pvlib`'s request-building code
(`'wkt': 'POINT(%s %s)' % (longitude, latitude)`). `config.CITY_COORDINATES` stores `(lat, lon)`
tuples and `_fetch_grid(lat, lon, ...)`'s own signature takes `lat` first — the new provider
function must explicitly swap the order when building the WKT string, or every city's solar data
will silently resolve to the wrong point (Pitfall 4).

A live, unauthenticated probe against the real endpoint (using the public `DEMO_KEY`) confirmed
the exact valid `attributes` list, the exact `interval` validation error text, and that
`attributes=ghi` alone is legal with **no forced companion fields** — directly resolving
CONTEXT.md's "Claude's Discretion" question about minimum required attributes. `DEMO_KEY` could
not be used to obtain a real CSV body or to isolate the out-of-range-year error message
specifically (its email-validation gate always fires first), so those two items remain open until
a real key is issued — see Open Questions.

**Primary recommendation:** Build `backend/nsrdb_provider.py` mirroring
`open_meteo_provider.py`'s shape exactly (module constant base URL, `fetch_nsrdb(lat, lon, start,
end)` returning a `PIPELINE_SCHEMA`-shaped frame, fail-loud `_range_check`), but add a
year-chunking loop absent from every existing provider, an `NREL_API_KEY`-or-raise helper mirroring
`dlr_pipeline._token()`'s actual `EnvironmentError` pattern, and a dual-shape error handler (JSON
`{"status":..., "errors":[...]}") vs. raw-CSV `"Error Code,Error Message"` body) matching
`pvlib`'s own `get_nsrdb_psm4_conus` error-handling code exactly.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| NSRDB HTTP fetch (per-year requests) + year-window reassembly | Backend / data-ingestion adapter (new `nsrdb_provider.py`) | — | Pure server-side HTTP client logic, same tier as `asos_provider.py`/`open_meteo_provider.py` |
| API-key lookup / env-var-or-raise | Backend / data-ingestion adapter (`nsrdb_provider.py`, mirroring `dlr_pipeline._token()`) | — | Credential handling is adapter-internal, never exposed to callers, matching `SYNOPTIC_TOKEN` precedent |
| `provider="nsrdb"` dispatch branch | Backend / data-ingestion adapter (`weather_provider.py::_fetch_grid`) | — | Same tier and same function Open-Meteo's branch already lives in (D-05) |
| Provenance tagging (`solar_source="nsrdb"`) | Backend / data-ingestion adapter | — | `attach_provenance` already lives in this tier and is directly reusable, no change needed |
| PIPELINE_SCHEMA / provider-name registry | Backend / configuration (`units_def.py`) | — | Already contains `"nsrdb"` (Phase 6) — no schema change required this phase |
| API key storage | Environment / `.env` (not committed) | — | Matches `SYNOPTIC_TOKEN` precedent exactly (WX-03 requirement) |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `requests` | 2.32.5 [VERIFIED: installed in project environment, confirmed via `python3 -c "import requests; print(requests.__version__)"` this session] | HTTP GET to the NSRDB CSV endpoint | Already the project's sole HTTP client (`asos_provider.py`, `open_meteo_provider.py`, `dlr_pipeline.py` all use it identically) — no new dependency (D-03) |
| `pandas` | 2.3.3 [VERIFIED: installed in project environment, confirmed this session] | CSV parsing (`pd.read_csv` after skipping NSRDB's metadata header rows), datetime construction, concatenation across year-chunks | Already the project's dataframe layer throughout `weather_provider.py`/the other providers |

No new third-party packages are required for this phase — D-03 explicitly rejects `pvlib` in favor
of the same raw-`requests` pattern already used for ASOS and Open-Meteo.

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `units_def.PIPELINE_SCHEMA` (in-repo) | n/a (project module) | Range validation for `solar_radiation` (0.0–1400.0 W/m²) | Same `_range_check` pattern as `asos_provider.py`/`open_meteo_provider.py` — see Don't Hand-Roll |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Raw `requests` (chosen, D-03) | `pvlib.iotools.get_nsrdb_psm4_conus` | `pvlib` already implements exactly this endpoint correctly (verified this session — see Code Examples) and would remove the year-chunking/error-handling code this phase must otherwise hand-write. D-03 explicitly rejects it to avoid a new dependency and keep provider modules stylistically uniform; if the year-chunking implementation proves error-prone in execution, revisiting this tradeoff is cheap since `pvlib`'s request/response shape is now fully documented below. |

**Installation:** No new packages to install — `requests`/`pandas` are already project dependencies.

## Package Legitimacy Audit

No new external packages are introduced by this phase (D-03 rejects the one candidate library,
`pvlib`, in favor of the raw-`requests` pattern already vetted and installed for Phase 7). This
section is not applicable.

**Packages removed due to [SLOP] verdict:** none — no new packages proposed.
**Packages flagged as suspicious [SUS]:** none.

## Architecture Patterns

### System Architecture Diagram

```
caller (C5/C7/C8)
      │
      │ fetch_weather(location=(lat, lon), start, end, provider="nsrdb")
      ▼
weather_provider.fetch_weather()
      │  _validate_location_shape() → "grid"
      ▼
weather_provider._fetch_grid(lat, lon, start, end, provider="nsrdb")
      │
      │  NEW BRANCH (parallel to existing provider=="open_meteo" branch)
      ▼
nsrdb_provider.fetch_nsrdb(lat, lon, start, end)
      │
      ├─► NREL_API_KEY env lookup ──► raise EnvironmentError if unset
      │
      ├─► split [start, end] into per-calendar-year (UTC) sub-windows
      │
      │   for each year Y in the span:
      │        GET https://developer.nlr.gov/api/nsrdb/v2/solar/
      │            nsrdb-GOES-conus-v4-0-0-download.csv
      │            ?api_key=...&email=...&names=Y&interval=60&utc=true
      │            &wkt=POINT(lon lat)&attributes=ghi
      │        │
      │        ├─► non-2xx ──► try response.json()['errors']
      │        │               except JSONDecodeError ──► response.content.decode()
      │        │               ──► raise requests.HTTPError / ValueError naming it
      │        │
      │        └─► 2xx ──► skip 2 metadata header lines, pd.read_csv() from line 3
      │                    ──► per-year DataFrame (Year, Month, Day, Hour, Minute, GHI)
      │
      ├─► pd.concat() all year-chunks
      ├─► build datetime_utc from (Year, Month, Day, Hour, Minute), filter to [start, end]
      ├─► rename GHI → solar_radiation; wind_speed/wind_direction/air_temp/
      │   relative_humidity NEVER populated (D-02 — never requested via `attributes`)
      ├─► _range_check() against PIPELINE_SCHEMA["solar_radiation"]["range"]
      ▼
      returns PIPELINE_SCHEMA-shaped frame
      │
      ▼
weather_provider._fetch_grid: attach_provenance(frame, "nsrdb") → attach_city(frame, lat=, lon=)
      │
      ▼
caller receives one row per (city, datetime_utc) with solar_source="nsrdb"
```

### Recommended Project Structure

```
backend/
├── nsrdb_provider.py          # NEW — this phase. Mirrors open_meteo_provider.py's shape.
├── weather_provider.py        # MODIFIED — new provider=="nsrdb" branch in _fetch_grid (~line 449-467)
├── config.py                  # UNCHANGED — CITY_COORDINATES already usable as-is
├── units_def.py               # UNCHANGED — "nsrdb" already in KNOWN_PROVIDER_NAMES (line 333)
└── tests/
    └── nsrdb_provider_test.py # NEW — follows open_meteo_provider_test.py's _FakeResponse convention
```

### Pattern 1: Year-chunked fetch-and-reassemble (the phase's core new logic)

**What:** Because the NSRDB CSV endpoint is year-scoped (`names=<year>`, one point, one year per
request — live-confirmed and cross-checked against `pvlib`), a `[start, end]` window that crosses
a calendar-year boundary needs multiple sequential requests, concatenated, then filtered to the
actual requested range. Neither `asos_provider.py` nor `open_meteo_provider.py` has this shape —
both pass `start`/`end` straight through to an API that accepts an arbitrary range in one call.

**When to use:** Every `nsrdb_provider.fetch_nsrdb(lat, lon, start, end)` call. Even a
single-day-in-one-year window still issues exactly one request (the common case); the loop only
grows for multi-year spans.

**Example (adapted from `pvlib`'s live-verified request shape, not copied verbatim since D-03
uses raw `requests` rather than `pvlib`):**
```python
# Source: pvlib.iotools.psm4.get_nsrdb_psm4_conus (github.com/pvlib/pvlib-python,
# pvlib/iotools/psm4.py, fetched and read this session) — request-parameter shape and
# error-handling logic adapted for this project's raw-requests convention (D-03).

NSRDB_BASE = "https://developer.nlr.gov/api/nsrdb/v2/solar/nsrdb-GOES-conus-v4-0-0-download.csv"

def _years_spanned(start_ts, end_ts) -> list[int]:
    return list(range(start_ts.year, end_ts.year + 1))

def fetch_nsrdb(lat: float, lon: float, start: str, end: str) -> pd.DataFrame:
    start_ts = pd.Timestamp(start, tz="UTC") if pd.Timestamp(start).tzinfo is None else pd.Timestamp(start).tz_convert("UTC")
    end_ts = pd.Timestamp(end, tz="UTC") if pd.Timestamp(end).tzinfo is None else pd.Timestamp(end).tz_convert("UTC")

    frames = []
    for year in _years_spanned(start_ts, end_ts):
        params = {
            "api_key": _nrel_api_key(),
            "email": _nrel_contact_email(),
            "names": year,
            "interval": 60,               # D-04
            "utc": "true",
            "wkt": f"POINT({lon:.4f} {lat:.4f})",   # lon FIRST -- pvlib-confirmed order
            "attributes": "ghi",          # D-02 -- solar only, no forced companions (live-verified)
        }
        r = requests.get(NSRDB_BASE, params=params, timeout=60)
        if not r.ok:
            try:
                errors = r.json()["errors"]
            except ValueError:            # json.JSONDecodeError subclasses ValueError
                errors = r.content.decode("utf-8")
            raise ValueError(f"nsrdb_provider: request for year {year} failed: {errors!r}")
        frames.append(_parse_psm4_csv(r.text))

    combined = pd.concat(frames, ignore_index=True)
    windowed = combined[(combined["datetime_utc"] >= start_ts) & (combined["datetime_utc"] <= end_ts)]
    _range_check(windowed)
    return windowed
```

### Pattern 2: 3-line metadata header CSV parsing

**What:** The NSRDB CSV body is NOT a simple `pd.read_csv()` target — it carries two metadata
header lines (field names, then values — Source, Location ID, Latitude, Longitude, GHI Units,
etc.) before the real column-name row, confirmed directly from `pvlib`'s `read_nsrdb_psm4` source
(`pvlib/iotools/psm4.py`, lines ~1035-1056, fetched and read this session).

**When to use:** Every successful (2xx) NSRDB response.

**Example:**
```python
# Source: pvlib.iotools.psm4.read_nsrdb_psm4 (github.com/pvlib/pvlib-python,
# pvlib/iotools/psm4.py), adapted for this project's plain-DataFrame convention (no
# metadata dict returned -- this project's other providers don't return one either).
def _parse_psm4_csv(text: str) -> pd.DataFrame:
    lines = text.splitlines()
    # lines[0] = metadata field names, lines[1] = metadata values, lines[2] = column header
    frame = pd.read_csv(StringIO(text), skiprows=2)
    frame["datetime_utc"] = pd.to_datetime(
        frame[["Year", "Month", "Day", "Hour", "Minute"]], utc=True
    )
    frame["solar_radiation"] = pd.to_numeric(frame["GHI"], errors="coerce")
    return frame[["datetime_utc", "solar_radiation"]]
```

### Anti-Patterns to Avoid

- **Passing `(lat, lon)` order into the WKT string:** `config.CITY_COORDINATES` and
  `_fetch_grid`'s own signature both use `(lat, lon)` order; NSRDB's `wkt` parameter requires
  `POINT(lon lat)` — reversed. Getting this backwards silently resolves every city to the wrong
  grid cell rather than raising (WKT syntax stays valid either way) — see Pitfall 4.
- **Treating the CSV endpoint like Open-Meteo's date-range API:** passing `start`/`end` as request
  parameters directly (there is no such parameter — only `names=<year>`) will either be ignored by
  the API or the code will silently only ever fetch one year's data regardless of the caller's
  actual window. See Pattern 1.
- **Assuming every error response is JSON:** a missing/invalid `api_key` returns a **plain
  CSV-formatted** error body (`"Error Code,Error Message"` header row, live-confirmed), not the
  `{"status":400,"errors":[...]}` JSON shape returned for parameter-validation failures under an
  accepted key. Code that does `r.json()` unconditionally will raise a confusing
  `JSONDecodeError` instead of surfacing the real NREL/NLR error text. Mirror `pvlib`'s
  try/except pattern (Code Examples).
- **Requesting the full 23-variable `attributes` set "to be safe":** D-02 requires solar-only.
  Requesting `wind_speed`/`air_temperature`/etc. and then discarding them in code is both wasted
  bandwidth and a foot-gun — a future edit could accidentally start mapping one of those columns
  into `PIPELINE_SCHEMA`, reintroducing the untrustworthy-wind-data risk D-02 exists to prevent.
  Request only `attributes=ghi` (live-verified as sufficient — no forced companions).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Range validation for `solar_radiation` | A new bespoke bounds-check function | `units_def.PIPELINE_SCHEMA["solar_radiation"]["range"]` + the same `_range_check` pattern already in `asos_provider.py`/`open_meteo_provider.py` | Single source of truth for the valid range (0.0–1400.0 W/m² [VERIFIED: `backend/units_def.py:368-372`, quoted: `"solar_radiation": {\n        "unit":      "W/m²",\n        "range":     (0.0, 1400.0),\n        "required":  False,\n    },`]) — a second, independently-written bounds check risks drifting out of sync |
| Provider-name registration for provenance | A new `KNOWN_PROVIDER_NAMES` entry or a separate NSRDB-specific provenance mechanism | `units_def.KNOWN_PROVIDER_NAMES` — `"nsrdb"` is already present [VERIFIED: `backend/units_def.py:329-335`, quoted: `KNOWN_PROVIDER_NAMES: frozenset[str] = frozenset({\n    "synoptic",\n    "tceq",\n    "asos",\n    "nsrdb",\n    "open_meteo",\n})`] | No schema change needed; `attach_provenance(frame, "nsrdb")` will work today without modification |
| Grid-point → city attribution | A new nearest-city lookup for NSRDB rows | `weather_provider.attach_city(frame, lat=lat, lon=lon)` — the exact call Open-Meteo's branch already makes at `weather_provider.py:453` | Same tier, same function, already handles the "coordinate doesn't resolve to a known city" raise case Open-Meteo's branch relies on (`weather_provider.py:455-460`) |
| API-key-missing detection | A bespoke `if not key: ...` inline in the new provider module | Mirror `dlr_pipeline._token()`'s exact structure (a private helper function that reads the env var, raises with a message naming the variable, and returns the value) — see Pitfall 1 for the exact exception type to use | Keeps every credential-lookup helper in the codebase structurally identical, so a future reader recognizes the pattern instantly regardless of which provider module they're in |

**Key insight:** every piece of "don't hand-roll" infrastructure this phase needs (schema range,
provider registry, city resolution, provenance tagging) was already built in Phase 6 and proven
working in Phase 7 — this phase's only genuinely new code is the NSRDB-specific HTTP request
shape, the year-chunking loop, and the CSV metadata-header skip.

## Common Pitfalls

### Pitfall 1: `dlr_pipeline._token()` raises `EnvironmentError`, not `ValueError`

**What goes wrong:** CONTEXT.md's "Claude's Discretion" section frames the key-absent decision as
"whether... a `ValueError` at call time... matching the existing `dlr_pipeline._token()`... or
something else." The actual code does not raise `ValueError`.

**Why it happens:** `dlr_pipeline._token()` is:
```python
# Source: backend/dlr_pipeline.py:59-66 [VERIFIED: read this session]
def _token() -> str:
    tok = os.getenv("SYNOPTIC_TOKEN", "")
    if not tok:
        raise EnvironmentError(
            "Set SYNOPTIC_TOKEN env var. "
            "Free research tokens: https://synopticdata.com/"
        )
    return tok
```
`EnvironmentError` is a built-in alias for `OSError` in Python 3 (has been since Python 3.3) — it
is not `ValueError`, and it is not related to `units_def.UnitError` or the `ValueError`s that
`asos_provider.py`/`open_meteo_provider.py` raise for malformed *response* data.

**How to avoid:** The new NREL-key-lookup helper in `nsrdb_provider.py` should raise
`EnvironmentError` (matching the literal precedent), with a message naming the env var (e.g.
`NREL_API_KEY`) — not `ValueError`. If the planner prefers `ValueError` for consistency with the
*response-validation* errors this phase's provider will also raise (matching
`asos_provider.py`/`open_meteo_provider.py`'s convention for malformed API responses), that is a
legitimate deliberate deviation from `_token()` — but it should be a documented, deliberate choice
at plan time, not an unexamined inheritance of a mischaracterized precedent.

**Warning signs:** A test asserting `pytest.raises(ValueError)` around the missing-key case that
was written to "match `_token()`" without checking `_token()`'s actual source.

### Pitfall 2: NSRDB's CSV endpoint is year-scoped, not date-range-scoped

**What goes wrong:** A `nsrdb_provider.fetch_nsrdb(lat, lon, start, end)` implementation that
naively passes `start_date`/`end_date`-style parameters (copying Open-Meteo's shape) will either
be silently ignored by the API or the code will only ever request one year regardless of the
caller's actual window, silently truncating any multi-year backfill or any window that crosses a
year boundary.

**Why it happens:** The only date-scoping parameter NSRDB's PSM v4 GOES CONUS download API
accepts is `names` (a single year, e.g. `2023`) — confirmed via NREL/NLR's own documentation
("Users can download a single CSV file... The CSV direct download feature is restricted to use
with only a single POINT, for a single YEAR at a time") and cross-checked directly against
`pvlib.iotools.psm4.get_nsrdb_psm4_conus`'s function signature, which takes a single `year`
parameter and has no `start`/`end` parameters at all.

**How to avoid:** Compute the set of calendar years (UTC) spanned by `[start, end]`, issue one
request per year, concatenate, then filter the combined frame down to the actual `[start, end]`
window before returning (Pattern 1).

**Warning signs:** A test with a window entirely inside a single year passes, but a window
spanning e.g. `2023-12-28` to `2024-01-03` silently returns only one year's data or an empty/wrong
result.

### Pitfall 3: Out-of-range-year error text is not fully confirmed live

**What goes wrong:** Planning or implementation that hardcodes an assumed exact NREL/NLR error
message string for an out-of-range year (e.g. matching on `"year not found"` or similar) may not
match the real response.

**Why it happens:** Live probes this session against `names=1990` and `names=2030` both returned
`HTTP 400` with `{"status": 400, "errors": [..., "Invalid value(s)"]}` — confirming the endpoint
*does* reject out-of-range years with a structured 400, not a silent wrong-product fallback. But
the public `DEMO_KEY` used for this probe **always** also returns `"The required 'email' parameter
must be a valid email address"` in the same `errors` array regardless of how the email parameter
was formatted (tested with a syntactically valid Gmail-style address, a garbage string, and no
email at all — same error every time), which appears to be a DEMO_KEY-specific restriction
(`pvlib`'s own docstring warns "The 'DEMO_KEY' `api_key` is severely rate limited and may result
in rejected requests"). This means the *exact* message when only the year is wrong (as opposed to
DEMO_KEY's blanket rejection) could not be isolated this session.

**How to avoid:** Match on the presence of a non-2xx status code and the generic `errors` array
shape, not on a specific substring — the code should raise on *any* structured error response
NSRDB returns, not pattern-match one specific wording. Re-confirm the precise text once a real
API key is issued (D-01's blocking checkpoint) and adjust the error message check if a more
specific test assertion is desired.

**Warning signs:** A test that only exercises `names=2030` under a fake/mocked "success" response
rather than asserting on the generic error-detection code path.

### Pitfall 4: WKT point order is longitude-first, opposite of `config.CITY_COORDINATES`

**What goes wrong:** `config.CITY_COORDINATES` stores `(lat, lon)` tuples (e.g. `"AUSTIN":
(30.2711, -97.7437)` [VERIFIED: `backend/config.py:147`]) and `_fetch_grid(lat, lon, start, end,
provider)`'s own parameter order is `lat` first [VERIFIED: `backend/weather_provider.py:449`,
quoted: `def _fetch_grid(lat: float, lon: float, start: str, end: str, provider: str) ->
pd.DataFrame:`]. NSRDB's `wkt` parameter is `POINT(longitude latitude)` — reversed.

**Why it happens:** Confirmed directly from `pvlib`'s request-building code: `longitude = ('%9.4f'
% longitude).strip(); latitude = ('%8.4f' % latitude).strip(); params = {..., 'wkt': 'POINT(%s %s)'
% (longitude, latitude), ...}` (`pvlib/iotools/psm4.py`, fetched and read this session). If the
new provider function builds the WKT string as `f"POINT({lat} {lon})"` instead of `f"POINT({lon}
{lat})"`, the request is syntactically valid WKT (so it does not raise) but resolves to a
different, wrong point on the map — for Austin (30.2711, -97.7437), a naive `lat`-first WKT string
would silently request data near roughly (−97.74°N, 30.27°E), an ocean point off the coast of
India, rather than central Texas.

**How to avoid:** Always build `wkt` as `f"POINT({lon:.4f} {lat:.4f})"` inside `nsrdb_provider.py`,
never `f"POINT({lat} {lon})"`. A unit test asserting the exact `wkt` string sent for a known city
(e.g. Austin) — following `open_meteo_provider_test.py`'s `recorder["params"]` pattern — is the
cheapest way to catch a regression here, since the failure mode is silent (wrong-but-valid data),
not a raised error.

**Warning signs:** NSRDB solar values that look plausible in isolation but don't correlate at all
with Open-Meteo's `shortwave_radiation` for the same city/window (a cross-provider sanity check
worth including in the phase's verification tasks).

## Code Examples

Verified patterns from official/primary sources fetched and read this session:

### NSRDB GOES CONUS PSM v4 request (adapted for raw `requests`, D-03)

```python
# Source: pvlib.iotools.psm4.get_nsrdb_psm4_conus request-parameter dict
# (github.com/pvlib/pvlib-python, pvlib/iotools/psm4.py, lines ~452-490, fetched and
# read this session), field names cross-confirmed via a live probe against
# developer.nlr.gov this session.
params = {
    "api_key": api_key,
    "email": contact_email,          # REQUIRED -- live-confirmed; omitting or
                                      # malformed values causes a 400
    "names": year,                   # single calendar year, e.g. 2023
    "attributes": "ghi",             # D-02 -- solar only; live-confirmed as
                                      # sufficient alone, no forced companions
    "interval": 60,                  # D-04; live-confirmed valid set is {5,15,30,60}
    "utc": "true",
    "wkt": f"POINT({lon:.4f} {lat:.4f})",   # lon FIRST
    # full_name / affiliation / reason / mailing_list: confirmed optional
    # (live probe omitting all four produced no additional validation error)
}
NSRDB_BASE = "https://developer.nlr.gov/api/nsrdb/v2/solar/nsrdb-GOES-conus-v4-0-0-download.csv"
r = requests.get(NSRDB_BASE, params=params, timeout=60)
```

### Live-verified error responses (this session, against the real host, `DEMO_KEY`)

```text
# Missing api_key entirely -- HTTP 403, CSV-shaped body (NOT JSON):
Error Code,Error Message
"API_KEY_MISSING","No api_key was supplied. Get one at https://developer.nrel.gov/signup/"

# Bad `interval` value (45, not in {5,15,30,60}) -- HTTP 400, JSON body:
{"inputs":{...},"metadata":{"version":"2.0.0"},"status":400,
 "errors":["The required 'email' parameter must be a valid email address",
           "The optional 'interval' parameter must be an integer in the set [5,15,30,60]"]}

# Unknown `attributes` value -- HTTP 400, JSON body (this is the live-confirmed,
# authoritative list of every valid attribute name):
{"...","errors":["The required 'email' parameter must be a valid email address",
 "The optional 'attributes' parameter must contain a list of comma separated attributes. \
Values may include air_temperature, alpha, aod, asymmetry, clearsky_dhi, clearsky_dni, \
clearsky_ghi, cloud_fill_flag, cloud_type, dew_point, dhi, dni, fill_flag, ghi, ozone, \
relative_humidity, solar_zenith_angle, ssa, surface_albedo, surface_pressure, \
total_precipitable_water, wind_direction, wind_speed"]}
```

### Error-handling dispatch (mirrors `pvlib`'s own approach exactly)

```python
# Source: pvlib.iotools.psm4.get_nsrdb_psm4_conus, lines ~482-490 (fetched and read
# this session), adapted to raise ValueError instead of requests.HTTPError to match
# this project's asos_provider.py/open_meteo_provider.py convention.
response = requests.get(NSRDB_BASE, params=params, timeout=60)
if not response.ok:
    try:
        errors = response.json()["errors"]
    except ValueError:  # json.JSONDecodeError is a ValueError subclass
        errors = response.content.decode("utf-8")
    raise ValueError(f"nsrdb_provider: request failed for year {year}: {errors!r}")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `developer.nrel.gov` (NREL Developer Network) | `developer.nlr.gov` (National Laboratory of the Rockies Developer Network) | Confirmed live this session (2026-09-12); exact rename date not published in the fetched pages | `developer.nrel.gov` returns `Could not resolve host` — any plan or documentation still referencing that hostname as a literal request target will fail at execution time. The API's request/response contract is otherwise unchanged. |
| `pvlib.iotools.psm3` (PSM v3 reader, `get_psm3`) | `pvlib.iotools.psm4` (PSM v4 reader, `get_nsrdb_psm4_conus` and siblings) | Confirmed this session: `psm3.py` no longer exists in `pvlib-python`'s `main` branch iotools directory; only `psm4.py` is present | Not directly load-bearing for this phase (D-03 doesn't use `pvlib`), but confirms `data_provider.md`'s reference to `pvlib.iotools.get_psm3` as the "existing, maintained Python reader" is itself now stale — the maintained reader for this exact product is `get_nsrdb_psm4_conus`. |

**Deprecated/outdated:**
- `developer.nrel.gov` as a literal hostname: dead (DNS failure, confirmed this session). Use
  `developer.nlr.gov`.
- `pvlib.iotools.get_psm3`: superseded by `pvlib.iotools.get_nsrdb_psm4_conus` (not used by this
  phase per D-03, but relevant if the project ever revisits the pvlib-vs-raw-requests tradeoff).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Environment variable for the key should be named `NREL_API_KEY` (matching WX-03's literal wording "registered NREL developer API key" and the `.env`/`SYNOPTIC_TOKEN` precedent), despite the live host and org branding now reading "NLR." | Standard Stack / Code Examples | Low — this is a naming choice with no functional consequence; if the team prefers `NLR_API_KEY` for accuracy, it's a one-name rename in a single new module, no other code references it. |
| A2 | GHI values in the NSRDB CSV response are in W/m² (matching `PIPELINE_SCHEMA["solar_radiation"]["unit"]`) with no unit-conversion step needed. | Architecture Patterns Pattern 2, Code Examples | Medium — could not obtain a real successful CSV body this session (DEMO_KEY blocked by its own email-validation gate before reaching a real data response) to directly read the echoed "GHI Units" metadata field. If GHI is actually reported in a different unit, `_range_check` would likely catch a gross mismatch (e.g. kW/m² would produce near-zero values, failing "in range" only by coincidence) but a subtler unit issue could pass undetected. **Recommend the first live-key execution task explicitly assert on the response's "GHI Units" metadata line before trusting downstream values.** |
| A3 | The exact HTTP 400 error text for an out-of-range `names` (year) value, in isolation from DEMO_KEY's blanket email-validation error, matches the generic `{"status":400,"errors":[...]}` shape observed for other validation failures (interval, attributes). | Pitfall 3 | Low — even if the exact text differs, the generic non-2xx-status + JSON-`errors`-array detection pattern (recommended in Code Examples) does not depend on matching a specific substring, so the fail-loud behavior itself is not at risk; only a test asserting a specific message text would need adjustment once a real key is available. |
| A4 | `full_name`, `affiliation`, `reason`, and `mailing_list` are safe to omit entirely from the request (confirmed only that omitting them produces no *additional* validation error under DEMO_KEY — not confirmed that a real API key's request succeeds end-to-end without them). | Code Examples | Low — worst case, add these back in with placeholder/project values; `pvlib`'s own code always sends them, so including them (e.g. `full_name="DLR System"`, `affiliation="ECE 464"`) is a safe, low-cost hedge if the planner prefers not to rely on this being unconfirmed with a real key. |

## Open Questions

1. **Exact GHI response units and the out-of-range-year error text**
   - What we know: The request/response contract's shape (params, error-body shapes, valid
     `attributes`/`interval` values) is live-verified. `_range_check` will catch a grossly wrong
     unit or a request that returns nothing at all.
   - What's unclear: Whether GHI is reported in exactly W/m² with no scaling, and the precise
     wording of the out-of-range-year 400 error in isolation from DEMO_KEY's email-gate error.
   - Recommendation: Both are only fully resolvable once a real `NREL_API_KEY` is issued (D-01's
     blocking checkpoint). Budget one execution task, gated behind that checkpoint, that makes one
     real call for a known city/year, asserts the "GHI Units" metadata line, and separately makes
     one real call for an out-of-range year to capture and hardcode the exact error text if the
     team wants a more specific test assertion than the generic shape check.

2. **Contact `email` value for the required parameter**
   - What we know: NSRDB's API requires a syntactically valid `email` parameter on every request
     (live-confirmed) — this has no analogue in any existing provider module (ASOS and Open-Meteo
     need no credential at all; Synoptic needs only a token, no email).
   - What's unclear: Whose email address the project should use, and whether it should live in
     `.env` alongside `NREL_API_KEY` (e.g. `NREL_API_EMAIL`) or be a hardcoded project-contact
     constant in `nsrdb_provider.py` (it's not a secret, unlike the API key).
   - Recommendation: Treat it like a second required credential-adjacent value — read from a new
     `.env` entry (e.g. `NREL_API_EMAIL`) with the same env-var-or-raise pattern as the API key,
     rather than hardcoding a specific person's address into source control. This is a discretion
     item the planner should resolve explicitly, since D-01/D-05's existing decisions don't cover
     it.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `requests` | HTTP client for NSRDB fetch | ✓ | 2.32.5 | — |
| `pandas` | CSV parsing, frame construction | ✓ | 2.3.3 | — |
| `NREL_API_KEY` (registered NLR/NREL developer key) | Every live NSRDB request | ✗ [per D-01 — "not yet registered" as of context-gathering] | — | None — this is a hard execution blocker per D-01. Planning can proceed (this document); live-fetch execution tasks must be gated behind a `checkpoint:human-verify` confirming the key exists before running. |
| `developer.nlr.gov` (network reachability) | Every live NSRDB request | ✓ [confirmed reachable this session via direct HTTP probes] | — | — |
| `developer.nrel.gov` (legacy hostname) | N/A — do not use | ✗ [DNS resolution fails, confirmed this session] | — | Use `developer.nlr.gov` instead (State of the Art) |

**Missing dependencies with no fallback:**
- `NREL_API_KEY` — this phase's live-execution tasks cannot run to completion until the key is
  issued (D-01). This is a planning-time-known, already-documented blocker, not a new finding.

**Missing dependencies with fallback:**
- None beyond the API key itself.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest` [VERIFIED: `backend/tests/*_test.py` — existing convention, e.g. `open_meteo_provider_test.py` imports `pytest` directly] |
| Config file | none found — tests run via bare `pytest` invocation, matching Phase 7's established pattern |
| Quick run command | `pytest backend/tests/nsrdb_provider_test.py -x` |
| Full suite command | `pytest backend/tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WX-03 | Fetches GHI for all four cities via `nsrdb_provider.fetch_nsrdb` given lat/lon | unit (mocked HTTP) | `pytest backend/tests/nsrdb_provider_test.py::test_fetch_nsrdb_returns_solar_radiation_for_a_known_city -x` | ❌ Wave 0 |
| WX-03 | API key absent raises a clear error naming the env var | unit | `pytest backend/tests/nsrdb_provider_test.py::test_fetch_nsrdb_raises_when_api_key_is_unset -x` | ❌ Wave 0 |
| WX-03 | Failed/malformed NSRDB response raises rather than fabricating data | unit (mocked HTTP, both JSON and CSV error-body shapes) | `pytest backend/tests/nsrdb_provider_test.py::test_fetch_nsrdb_raises_on_json_error_body -x` and `::test_fetch_nsrdb_raises_on_csv_error_body -x` | ❌ Wave 0 |
| WX-03 | NSRDB-sourced rows tagged `solar_source="nsrdb"` and pass `PIPELINE_SCHEMA` range validation | unit + integration (`weather_provider._fetch_grid` dispatch) | `pytest backend/tests/weather_provider_test.py::test_dispatch_grid_nsrdb_provider_attaches_provenance -x` | ❌ Wave 0 (new test, mirroring existing `test_dispatch_latlon_tuple_routes_to_the_grid_path`) |
| WX-03 | A window spanning a calendar-year boundary issues one request per year and reassembles correctly | unit (mocked HTTP, request-count assertion — mirrors `open_meteo_provider_test.py::test_fetch_open_meteo_issues_exactly_one_request`'s recorder pattern) | `pytest backend/tests/nsrdb_provider_test.py::test_fetch_nsrdb_issues_one_request_per_calendar_year -x` | ❌ Wave 0 |
| WX-03 | `wkt` point is built longitude-first | unit (mocked HTTP, params-recorder assertion) | `pytest backend/tests/nsrdb_provider_test.py::test_fetch_nsrdb_wkt_is_longitude_first -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest backend/tests/nsrdb_provider_test.py -x`
- **Per wave merge:** `pytest backend/tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`. Any live-network verification task
  (an actual NSRDB pull) is separately gated behind the D-01 API-key checkpoint and is not part of
  the automated suite.

### Wave 0 Gaps

- [ ] `backend/tests/nsrdb_provider_test.py` — new file, covers WX-03's unit-level behaviors above
- [ ] A `weather_provider_test.py` addition for the new `provider="nsrdb"` grid-dispatch branch,
      mirroring the existing Open-Meteo dispatch/provenance tests
- [ ] Framework install: none — `pytest` is already present and used project-wide

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | API key read only from environment (`os.getenv`), never hardcoded or logged — matches `SYNOPTIC_TOKEN`/`dlr_pipeline._token()` precedent exactly |
| V3 Session Management | no | Stateless per-request API key on a server-to-server call; no session concept applies |
| V4 Access Control | no | No user-facing access-control surface introduced by this phase |
| V5 Input Validation | yes | `_range_check` against `PIPELINE_SCHEMA["solar_radiation"]["range"]`, mirroring `asos_provider.py`/`open_meteo_provider.py`'s existing pattern — catches a units regression or a malformed response before it reaches downstream physics code |
| V6 Cryptography | no | No cryptographic operations in this phase; TLS is handled by `requests`/the OS trust store, never hand-rolled |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| API key committed to version control | Information Disclosure | `.env` is (per existing project convention — `SYNOPTIC_TOKEN` already lives there) not committed; `NREL_API_KEY` follows the identical pattern. The executor should verify `.env` is `.gitignore`d before this phase's first commit. |
| API key leaked via error message or log line | Information Disclosure | The env-var-or-raise helper should name the *variable*, never echo the token's *value*, in its error message — matching `dlr_pipeline._token()`'s existing message text exactly (`"Set SYNOPTIC_TOKEN env var..."`, not `f"got {tok!r}"`) |
| Untrusted/malformed API response silently accepted as valid data | Tampering (of the data pipeline's trust in an external source) | `_range_check` + fail-loud on any non-2xx or malformed body — this phase's success criterion 4 is explicitly this control |
| SSRF via unvalidated `wkt`/coordinate input | Tampering | Not a real risk here — `lat`/`lon` come from `config.CITY_COORDINATES`, a fixed in-repo constant, never from unvalidated external/user input, for all four cities this phase serves |

## Sources

### Primary (HIGH confidence)

- `pvlib-python` source, `pvlib/iotools/psm4.py` (github.com/pvlib/pvlib-python, `main` branch,
  fetched and read directly this session via `curl`) — request-parameter dict, base URL, error
  handling, and CSV-parsing (3-line-header) logic for `get_nsrdb_psm4_conus`/`read_nsrdb_psm4`.
- Live HTTP probes against `https://developer.nlr.gov/api/nsrdb/v2/solar/nsrdb-GOES-conus-v4-0-0-download.csv`
  this session (via `curl`, using the public `DEMO_KEY`) — confirmed: the endpoint exists and is
  reachable; `developer.nrel.gov` does not resolve; the exact valid `attributes` list; the exact
  `interval` validation error text; the JSON vs. CSV dual error-body shape; rate-limit response
  headers (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `Retry-After`).
- `https://developer.nlr.gov/docs/rate-limits/` (fetched and read directly this session) — standard
  key rate limit (1,000 requests/hour, rolling window), `DEMO_KEY` limits (30/hour, 50/day per IP),
  429 status code on exceedance, and the "National Laboratory of the Rockies" institutional
  rebrand.
- `backend/dlr_pipeline.py`, `backend/asos_provider.py`, `backend/open_meteo_provider.py`,
  `backend/weather_provider.py`, `backend/units_def.py`, `backend/config.py`,
  `backend/tests/open_meteo_provider_test.py`, `backend/tests/asos_provider_test.py`,
  `backend/tests/weather_provider_test.py` (all read directly this session) — existing project
  patterns this phase must replicate.

### Secondary (MEDIUM confidence)

- WebSearch results synthesizing `developer.nrel.gov/docs/solar/nsrdb/nsrdb-GOES-conus-v4-0-0-download/`
  content (the page itself could not be reached directly — `WebFetch`/`curl` both failed to
  resolve `developer.nrel.gov`) — corroborated against and superseded by the primary
  `pvlib` source and live `developer.nlr.gov` probes above wherever they overlap.
- `docs/data-science/decisions/data_provider.md` §"NREL NSRDB — PSM v4 (GOES CONUS)" (lines
  86-107) and §"Recommended Composition" (lines 211-224) — prior vetting pass, explicitly
  "not confirmed live" per its own text; this research supersedes its rate-limit figures
  (10,000/day + 1/sec + 20-concurrent) with the live-verified 1,000/hour standard-key limit.

### Tertiary (LOW confidence)

- WebSearch-only claim that "2025 NSRDB satellite dataset for the Western Hemisphere is now
  available" — not independently verified against a primary NREL/NLR announcements page this
  session; treat 2025 data availability as unconfirmed until checked at execution time.

## Metadata

**Confidence breakdown:**
- Standard stack (no new deps, D-03 confirmed sufficient): HIGH — no new packages, both `requests`
  and `pandas` already installed and version-confirmed.
- API request contract (endpoint, params, valid values, error shapes): HIGH — live-verified
  against the real production host this session, cross-checked against actively-maintained
  `pvlib` source code.
- Year-out-of-range exact error text, GHI response units: MEDIUM — mechanism confirmed (400 status,
  structured error), but exact isolated text/unit label not obtainable without a real API key
  (blocked by D-01).
- Pitfalls (env-var exception type, WKT coordinate order, year-chunking requirement): HIGH — each
  independently confirmed by reading the actual source file/response this session, not inferred.

**Research date:** 2026-09-12
**Valid until:** 30 days for the code-pattern/schema findings (stable, in-repo); 7 days for the
live API-contract findings given the confirmed in-flight NREL→NLR migration — re-verify the
`developer.nlr.gov` host and rate-limit figures if execution is delayed past that window, since a
mid-migration API is more likely than usual to shift again.
