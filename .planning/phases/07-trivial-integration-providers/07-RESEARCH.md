# Phase 7: Trivial-Integration Providers - Research

**Researched:** 2026-09-11
**Domain:** Weather-data HTTP adapters (Iowa Environmental Mesonet ASOS 1-minute CGI; Open-Meteo REST/JSON), wired behind Phase 6's `weather_provider.py` adapter
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** ASOS's finer-grained timestamps are added as **new rows** (union of timestamps with the existing Synoptic series), not merely used to improve values at Synoptic's existing timestamps. This is what actually delivers "higher-temporal-density" — the stated reason ASOS was chosen over alternatives in `data_provider.md`. — **Reversibility:** costly — once C9 feature-engineering code is written against a denser union-of-timestamps series, collapsing back to same-timestamp-only merging would change the shape (row count) of every derived dataset built on it.
- **D-02:** At an ASOS-only timestamp (a minute where Synoptic has no sample), fields ASOS doesn't measure (`solar_radiation`, `relative_humidity`) are left **null**, not backfilled or dropped. This is consistent with how `PIPELINE_SCHEMA` already treats absent per-field data (`required: False` columns, Phase 6 precedent) — C9 feature code decides how to handle sparsity per-feature, not this adapter.
- **D-03:** ASOS supplementation is **automatic and transparent** inside every existing `fetch_weather(..., provider="synoptic")` station-based call — C5/C7/C8 do not need to know ASOS is involved, matching Phase 6's established philosophy that provider composition is an adapter-internal concern. — **Reversibility:** costly — every existing station-based call site starts making an additional network request; reversing this to opt-in later means auditing whether any caller came to implicitly depend on ASOS's presence in the merged result.
- **D-04:** Open-Meteo is wired as Phase 6's `_fetch_grid`'s first real `provider="open_meteo"` implementation, reachable via `fetch_weather(location=(lat, lon), provider="open_meteo")` — reusing the existing dispatch rather than adding a new standalone function. It remains reachable only via the grid path; C5/C7/C8's station-based calls never trigger it (that path continues to raise for any provider other than the ones actually implemented there).
- **D-05:** If ASOS's or Open-Meteo's network call fails or returns malformed/unparseable data, `fetch_weather` **raises** rather than degrading silently to a partial result — consistent with the project's established "never silently overstate" provenance philosophy (Phase 6 D-04, `data_provider.md`). A caller relying on the ASOS supplement or an Open-Meteo backfill should know immediately that it didn't arrive, rather than unknowingly getting Synoptic-only data.

### Claude's Discretion

- Exact ASOS station-ID mapping per city (Austin-Bergstrom/KAUS, Corpus Christi Intl/KCRP, Midland Intl/KMAF, El Paso Intl/KELP — all already named in `data_provider.md`, no research needed) and where that mapping lives (e.g. alongside `config.CITY_COORDINATES` vs. a new lookup table). **Correction found during this research (see Pitfall 1): the actual IEM ASOS-network station identifiers are the 3-letter codes `AUS`/`CRP`/`MAF`/`ELP`, NOT the 4-letter ICAO codes `KAUS`/`KCRP`/`KMAF`/`KELP` used elsewhere in the project's docs. Live-confirmed this session.**
- Exact unit-conversion helper structure for ASOS (knots→m/s, °F→°C) — whether inline or a shared conversion utility. **Resolved by this research: `units_def.Q` already implements both conversions exactly — reuse it, do not hand-roll (see Don't Hand-Roll).**
- Whether Open-Meteo's `provider="open_meteo"` dispatch requests a specific historical API variant (Archive API vs. Historical Forecast API) — both are documented as viable in `data_provider.md`; pick based on what best matches the phase's date-range needs during research/planning. **Resolved by this research: use the Archive API (see Standard Stack) — recommendation, confirm at planning checkpoint.**
- Internal module/function layout for the ASOS fetch + merge-into-union-of-timestamps logic. **Resolved by this research: `weather_provider.merge_observations` already implements D-01/D-02 correctly, empirically verified this session — no new merge function needed (see Architecture Patterns, Pattern 1).**

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within Phase 7's scope. NSRDB solar integration (Phase 8) and fallback-provider semantics (WX-06, later) were not raised.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| WX-02 | Given a target city, the system can additionally fetch higher-temporal-density wind/temp observations from ASOS 1-minute data as a supplement to the primary wind/temp source (currently Synoptic). | ASOS CGI endpoint, parameters, and response format live-confirmed (Standard Stack, Code Examples); union-of-timestamps merge empirically verified reusing `merge_observations` unmodified (Architecture Patterns Pattern 1); unit conversion via `units_def.Q` (Don't Hand-Roll). |
| WX-04 | Given a target city and a historical date range, the system fetches the full weather variable set (temp, wind speed/direction, solar, RH) from Open-Meteo in a single request, for use as C9/C10 training data. | Open-Meteo Archive API endpoint, parameters, and response shape live-confirmed against Austin's coordinates (Standard Stack, Code Examples); variable-to-`PIPELINE_SCHEMA` column mapping table (Architecture Patterns); unit-parameter trick eliminates manual wind conversion. |
</phase_requirements>

## Summary

Both providers are genuinely no-auth and were live-confirmed this session (not just cited from `data_provider.md`): ASOS 1-minute returned real Austin/Corpus Christi/Midland/El Paso data from a plain unauthenticated `GET`, and Open-Meteo's Archive API returned a full temp/wind/solar/RH payload for Austin's exact `config.CITY_COORDINATES` point in one request, no API key on either. This satisfies Success Criterion #4 directly.

The most consequential finding is that **`weather_provider.merge_observations` — Phase 6's existing `combine_first`-based function — already implements D-01's union-of-timestamps requirement and D-02's null-for-unmeasured-fields requirement exactly as specified, with zero modification**, contrary to the `07-CONTEXT.md` canonical-refs' speculation that it "may need its own function alongside these." This was proven empirically in this session with a synthetic 5-minute-Synoptic + 1-minute-ASOS dataset (see Architecture Patterns, Pattern 1): the merged output had the correct union row count, Synoptic's values won at overlapping timestamps, ASOS's values populated ASOS-only timestamps, and `relative_humidity`/`solar_radiation` (fields ASOS doesn't supply) stayed null exactly at ASOS-only rows. This significantly de-risks the phase and removes an implementation task the plan would otherwise have budgeted for.

A second consequential finding: the IEM ASOS network's actual station identifiers for these four airports are the 3-letter FAA codes (`AUS`, `CRP`, `MAF`, `ELP`), not the 4-letter ICAO codes (`KAUS`, `KCRP`, `KMAF`, `KELP`) used throughout `data_provider.md` and `07-CONTEXT.md`. A request with the 4-letter code fails outright (`"Unknown station provided: KAUS"`, live-confirmed). This must be corrected in the planner's station-ID mapping table or the phase will fail at first live execution.

Third: `units_def.KNOWN_PROVIDER_NAMES` already contains `"asos"` and `"open_meteo"` — `07-CONTEXT.md`'s uncertainty about whether these need adding is resolved; **no schema change is needed**, `attach_provenance("asos"/"open_meteo")` will work today.

**Primary recommendation:** Wire ASOS into `_fetch_station`'s `provider="synoptic"` branch (fetch ASOS via the CGI endpoint using the corrected 3-letter station codes, convert units via `units_def.Q`, tag provenance, then call the existing `merge_observations(synoptic_frame, asos_frame)` unmodified); wire Open-Meteo into `_fetch_grid`'s `provider="open_meteo"` branch calling the Archive API (`archive-api.open-meteo.com/v1/archive`) with `wind_speed_unit=ms` so no wind conversion is needed at all.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| ASOS 1-minute HTTP fetch + unit conversion | Backend / data-ingestion adapter (`weather_provider.py` + a new helper module) | — | Pure server-side HTTP client logic; no browser, no persistence layer involved |
| Union-of-timestamps merge (ASOS into Synoptic) | Backend / data-ingestion adapter | — | In-process pandas operation inside the same adapter module — `merge_observations` already lives there |
| Open-Meteo HTTP fetch + schema mapping | Backend / data-ingestion adapter (`_fetch_grid`) | — | Same tier as the station path; both are C4 adapter responsibilities |
| Provenance tagging | Backend / data-ingestion adapter | — | `attach_provenance` already lives in this tier and is directly reusable |
| Station-ID / coordinate lookup tables | Backend / configuration (`config.py`) | — | Matches existing `CITY_COORDINATES`/`STATIC_RATINGS` convention — static, city-keyed data belongs in C1 |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `requests` | 2.32.5 [VERIFIED: installed in project `.venv`, confirmed via `python3 -c "import requests; print(requests.__version__)"` this session] | HTTP GET to both provider endpoints | Already the project's sole HTTP client (`dlr_pipeline.py::fetch_timeseries` uses it identically) — no new dependency |
| `pandas` | 2.3.3 [VERIFIED: installed in project `.venv`, confirmed this session] | DataFrame construction, `combine_first`-based merge, datetime parsing | Already the project's dataframe layer throughout `weather_provider.py`/`dlr_pipeline.py` |

No new third-party packages are required for this phase — both providers are reachable with a plain `requests.get()` and JSON/CSV parsing already available in the stack.

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `units_def.Q` (in-repo) | n/a (project module) | Unit conversion: knots→m/s, °F→°C | For every ASOS value before it enters `PIPELINE_SCHEMA` columns — see Don't Hand-Roll |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Open-Meteo Archive API (`archive-api.open-meteo.com/v1/archive`) | Open-Meteo Historical Forecast API (`historical-forecast-api.open-meteo.com/v1/forecast`) | Historical Forecast only goes back to ~2021-2022 and is HRRR-model output (matches Open-Meteo's *live* forecast exactly, useful for bias-correction/consistency work); Archive API goes back to 1940 (ERA5/ERA5-Land reanalysis, 10km resolution) — far deeper history for C9/C10's "start accumulating training volume now" need (ROADMAP Finding 5). **Recommendation: Archive API**, since WX-04's stated purpose is historical backfill depth, not live-forecast consistency. Flag as a checkpoint for user confirmation since it's explicitly a discretion item. |
| Manual `(f - 32) * 5/9` / `knots * 0.514444` conversion | `units_def.Q("...").to("...")` | None — `units_def.Q` already has both factors registered (`CONVERSIONS["knots"] = 0.514444`, `_to_base()` handles `degF` via formula) [VERIFIED: backend/units_def.py:92, 224-225] — hand-rolling would duplicate an existing, tested utility |

**Installation:** None — no new packages.

## Package Legitimacy Audit

**Not applicable.** This phase introduces no new third-party package dependencies. Both providers are reached via `requests` (already installed, `2.32.5`) and parsed with `pandas`/stdlib `csv`/`json` (already installed). No `npm install`/`pip install` step is needed, so the Package Legitimacy Gate is skipped per its own trigger condition ("Every phase that installs external packages").

## Architecture Patterns

### System Architecture Diagram

```
                         fetch_weather(location, start, end, provider)
                                        │
                         _validate_location_shape(location)
                                        │
                  ┌─────────────────────┴─────────────────────┐
                  │ shape == "station"                shape == "grid"
                  ▼                                            ▼
            _fetch_station(stids, ..., provider)      _fetch_grid(lat, lon, ..., provider)
                  │                                            │
       provider == "synoptic" (only branch today)     provider == "open_meteo" (Phase 7, new)
                  │                                            │
     ┌────────────┴─────────────┐                    GET archive-api.open-meteo.com/v1/archive
     ▼                          ▼                     (lat, lon, start_date, end_date,
dlr_pipeline.fetch_timeseries   NEW: fetch_asos_1min    hourly=temp/wind/solar/RH vars,
(Synoptic CGI, existing)        (IEM CGI, Phase 7)       wind_speed_unit=ms)
     │                          │                                │
attach_provenance("synoptic")  convert units via              parse JSON → DataFrame
attach_city(from lat/lon)      units_def.Q, then               (columns already match
     │                          attach_provenance("asos")        PIPELINE_SCHEMA names
     │                          attach_city(known city)           after rename)
     │                          │                                │
     └──────────┬───────────────┘                       attach_provenance("open_meteo")
                 ▼                                       attach_city(lat, lon)
    merge_observations(synoptic_frame, asos_frame)                │
    (existing combine_first union-of-index merge —                ▼
     reused unmodified — produces union-of-timestamps       returned directly
     rows per D-01/D-02, station values win at overlaps)   (no merge — D-04: grid
                 │                                          path stands alone)
                 ▼
      returned to caller (C5/C7/C8) —
      transparent per D-03, they see one
      merged frame regardless of ASOS's
      involvement
```

### Recommended Project Structure

```
backend/
├── weather_provider.py     # _fetch_station gains the ASOS branch; _fetch_grid gains the open_meteo branch
├── asos_provider.py         # NEW (suggested): fetch_asos_1min(city, start, end) -> DataFrame in PIPELINE_SCHEMA shape
├── open_meteo_provider.py   # NEW (suggested): fetch_open_meteo(lat, lon, start, end) -> DataFrame in PIPELINE_SCHEMA shape
├── config.py                 # gains ASOS_STATIONS: dict[str, str] keyed identically to CITY_COORDINATES
└── units_def.py               # unchanged — Q, KNOWN_PROVIDER_NAMES, PIPELINE_SCHEMA already support both providers
```

Splitting each provider's HTTP-fetch-and-normalize logic into its own module (rather than inlining inside `weather_provider.py`) mirrors the existing separation between `weather_provider.py` (adapter/dispatch) and `dlr_pipeline.py` (Synoptic-specific fetch), which the module docstring explicitly says is a deliberate isolation boundary ("If/when the provider decision lands on something else ... that change should be containable entirely within this file"). This is Claude's Discretion per `07-CONTEXT.md`; the exact module layout is not locked.

### Pattern 1: Reuse `merge_observations` unmodified for the ASOS union-of-timestamps merge

**What:** Contrary to `07-CONTEXT.md`'s canonical-refs speculation that ASOS's union-of-timestamps merge "is a different shape and may need its own function," `merge_observations(station_frame, grid_frame)`'s existing `combine_first`-on-`(city, datetime_utc)` MultiIndex implementation already produces exactly D-01/D-02's semantics when the ASOS frame is passed as the second (`grid_frame`) positional argument — despite ASOS not being a lat/lon "grid" source. The mechanism only cares that both frames are indexed on `(city, datetime_utc)`; it doesn't care what generated that index.

**When to use:** Any time a denser second time series needs to be unioned into a sparser primary series without touching the primary's existing values, where fields the second source doesn't supply should stay null on its new rows.

**Verified this session** — empirical test, not just theoretical: a 5-minute synthetic Synoptic frame (`air_temp`/`wind_speed`/`wind_direction`/`relative_humidity`, 3 rows) was merged with a 1-minute synthetic ASOS frame (`air_temp`/`wind_speed`/`wind_direction` only — no humidity/solar columns, 5 rows, deliberately wrong sentinel values `99.0`/`999.0` at the two timestamps that overlap Synoptic's) via the unmodified `weather_provider.merge_observations()`:

```python
# Verified this session — ran with the project's actual weather_provider.py
# via /Users/aphan/Documents/Senior_Design/.venv/bin/python3
merged = wp.merge_observations(synoptic, asos)

# Result (7 rows = union of {00,05,10} ∪ {00,01,02,03,04} = 7 distinct timestamps):
#                                  air_temp  temp_source  wind_source  humidity_source
# AUSTIN 2025-07-01 00:00:00+00:00     25.0    synoptic     synoptic     synoptic   <- overlap: Synoptic's real value wins over ASOS's 99.0 sentinel
#        2025-07-01 00:01:00+00:00     25.2    asos         asos         NaN        <- ASOS-only row: humidity stays null (ASOS doesn't measure it)
#        2025-07-01 00:02:00+00:00     25.3    asos         asos         NaN
#        2025-07-01 00:03:00+00:00     25.4    asos         asos         NaN
#        2025-07-01 00:04:00+00:00     99.0    asos         asos         NaN        <- ASOS-only row, genuinely ASOS's only value here
#        2025-07-01 00:05:00+00:00     25.5    synoptic     synoptic     synoptic   <- overlap: Synoptic wins again
#        2025-07-01 00:10:00+00:00     26.0    synoptic     synoptic     synoptic
```

This proves: (1) union row count, exactly D-01; (2) Synoptic's value and provenance win at every overlapping timestamp — nothing in D-01/D-03 is violated by ASOS "touching" existing rows; (3) `humidity_source`/`solar_source` are null exactly at ASOS-only rows — exactly D-02; (4) no post-merge provenance-rewriting was needed — `attach_provenance`'s per-side tagging survived the merge intact, matching the existing invariant `merge_observations`'s own docstring describes.

**Practical wiring note:** call `merge_observations(synoptic_frame, asos_frame)` positionally with Synoptic first (matches the function's existing "station frame combined from the left" contract) — the parameter names (`station_frame`/`grid_frame`) are a naming mismatch for the ASOS case, not a functional one; do not rename the shared function or add a parallel one for this phase.

### Pattern 2: City-direct `attach_city` for both new providers (skip lat/lon resolution)

**What:** `attach_city(frame, lat=lat, lon=lon)` — the two-keyword form — sets every row's `city` column from a single caller-supplied coordinate pair, no per-row resolution [VERIFIED: backend/weather_provider.py:139-192, confirmed by reading `attach_city`'s branch handling `lat is not None and lon is not None`].

**When to use:** Both ASOS and Open-Meteo fetches are always issued *for* a specific target city (the caller already knows which city they asked for — it's the input to the ASOS station-ID lookup or the Open-Meteo lat/lon query). Use `attach_city(asos_frame, lat=city_lat, lon=city_lon)` / `attach_city(open_meteo_frame, lat=lat, lon=lon)` with the city's own `config.CITY_COORDINATES` value directly, rather than resolving from whatever lat/lon the provider's response happens to include (ASOS's `gis=true` param returns the *airport's* lat/lon, e.g. `30.1830,-97.6799` for AUS — live-confirmed this session — which is close to but not identical to `config.CITY_COORDINATES["AUSTIN"]`'s `30.2711,-97.7437`; resolving through `resolve_station_city` would likely still land on AUSTIN given the other three cities are all >100km away, but using the known target city directly is simpler and removes a resolution step that could theoretically misfire near a corridor midpoint).

**Example:**
```python
# Source: backend/weather_provider.py:139-192 (attach_city), read this session
city = "AUSTIN"  # already known -- e.g. the caller's requested station's resolved city
lat, lon = config.CITY_COORDINATES[city]
asos_frame = weather_provider.attach_city(asos_frame, lat=lat, lon=lon)
```

### Anti-Patterns to Avoid

- **Re-deriving relative_humidity from ASOS's `tmpf`/`dwpf` (temp/dewpoint):** technically computable via a psychrometric formula, but D-02 explicitly says fields ASOS doesn't measure stay null — deriving RH would be silently overstating a measurement ASOS never took, violating the project's "never silently overstate" ethic. Leave `relative_humidity` null on ASOS-only rows exactly as `merge_observations` already does automatically.
- **Passing the 4-letter ICAO codes (`KAUS` etc.) to the ASOS CGI endpoint:** confirmed to fail outright this session (`"Unknown station provided: KAUS"`). Use the 3-letter codes (`AUS`/`CRP`/`MAF`/`ELP`).
- **Hand-rolling `(f-32)*5/9` / `*0.514444` conversions inline:** `units_def.Q` already has both; duplicating them creates a second source of truth for the exact same constants the project's `units_def.py::CONVERSIONS` dict maintains.
- **Requesting Open-Meteo's default `wind_speed_unit` (`kmh`):** would require an extra conversion step for no reason — pass `wind_speed_unit=ms` and get `PIPELINE_SCHEMA`-ready values directly (live-confirmed this session: requesting `wind_speed_unit=ms` returns `"wind_speed_10m":"m/s"` in the response's `hourly_units` object).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| knots → m/s, °F → °C conversion | Inline arithmetic in the ASOS fetch function | `units_def.Q(value, "knots").to("m/s")` / `units_def.Q(value, "degF").to("degC")` | Already implemented, already tested (`backend/tests/units_def_test.py`), already the project's single source of truth for unit factors — a duplicate inline formula could silently drift (e.g. a typo'd `0.51444` vs `0.514444`) |
| Union-of-timestamps merge with per-field provenance preservation | A new `merge_observations_union` function | `weather_provider.merge_observations(synoptic_frame, asos_frame)` unmodified | Empirically verified this session to already implement D-01/D-02 exactly — see Pattern 1 |
| City resolution for the new providers' output rows | A new city-lookup helper | `weather_provider.attach_city(frame, lat=lat, lon=lon)` | Already implemented for exactly this "caller already knows the city" case |
| Provenance tagging | Custom "which provider filled this" logic | `weather_provider.attach_provenance(frame, "asos"/"open_meteo")` | Already implemented, already validates against `KNOWN_PROVIDER_NAMES` (which already contains both names) |

**Key insight:** Phase 6 was explicitly built to make Phase 7 "cheap" (per the phase description itself). This research confirms that intent was realized in practice, not just in design: every cross-cutting concern (provenance, city resolution, merge semantics) Phase 7 needs already exists and needs zero modification — the only genuinely new code is the two providers' own HTTP-fetch-and-normalize functions.

## Common Pitfalls

### Pitfall 1: ASOS station IDs are 3-letter FAA codes, not 4-letter ICAO codes
**What goes wrong:** Requesting `station=KAUS` (the code used throughout `data_provider.md` and `07-CONTEXT.md`) returns `"Unknown station provided: KAUS"` with no data — a silent-looking failure if not checked for explicitly, though the response body does contain the word "Unknown" so a string-content check (not just HTTP status) is needed to catch it, since the endpoint returns HTTP 200 with this error text rather than a 4xx status.
**Why it happens:** The IEM ASOS network catalogs Austin-Bergstrom, Corpus Christi Intl, Midland Intl, and El Paso Intl under their 3-letter FAA identifiers (`AUS`, `CRP`, `MAF`, `ELP`), not the 4-letter ICAO identifiers (`KAUS`, `KCRP`, `KMAF`, `KELP`) that Synoptic and most other US aviation-weather sources use.
**How to avoid:** Use `AUS`/`CRP`/`MAF`/`ELP` in the `station` parameter. Live-confirmed this session via `https://mesonet.agron.iastate.edu/geojson/network/TX_ASOS.geojson` and direct CGI requests returning real data for all four.
**Warning signs:** An HTTP 200 response whose body is just the CSV header row with zero data rows and/or the literal string "Unknown station provided" — `fetch_weather`'s fail-loud policy (D-05) means this condition must be checked explicitly (an empty-but-200 response will not raise on `raise_for_status()` alone) and turned into a raised exception.

### Pitfall 2: ASOS 1-minute data has real, expected outage gaps
**What goes wrong:** A request for `ELP` over `2023-07-01T00:00Z`–`2023-07-01T00:15Z` returned a header-only response (zero rows) this session, while adjacent dates (`2024-01-15`, `2025-01-15`) returned full data. This is a real sensor-network gap, not a station-ID or endpoint problem (the same station returns data for other windows).
**Why it happens:** 1-minute ASOS sensors have real hardware/maintenance outages; unlike a 5-minute or hourly network with more redundancy, individual-minute gaps are unremarkable.
**How to avoid:** Do not treat a zero-row ASOS response as a hard failure per D-05's fail-loud policy if Synoptic (the primary) still returned data for that window — the phase's own success criteria describe ASOS as a *supplement*, so a request-window with genuinely no ASOS data available should degrade to "no ASOS rows added" rather than raising, whereas a malformed/unparseable response (Pitfall 1's shape, or an HTTP error) should raise per D-05. This distinction (empty due to real absence vs. malformed/erroring) needs to be made explicit in the plan's task breakdown — recommend flagging as a planning checkpoint since D-05's wording ("fails or returns malformed/unparseable data") doesn't explicitly disambiguate "zero rows, well-formed" from "malformed."
**Warning signs:** Tests or manual runs against fixed historical dates producing inconsistent row counts across otherwise-identical requests for different stations/windows.

### Pitfall 3: Open-Meteo's `timezone=UTC` response omits the "Z"/offset suffix
**What goes wrong:** A response requested with `timezone=UTC` echoes back `"timezone":"GMT"` and returns timestamps like `"2025-07-01T00:00"` — no trailing `Z` or `+00:00` — live-confirmed this session. Parsing these with a bare `pd.to_datetime(...)` (no `utc=True`) produces tz-naive timestamps that will silently fail to align against the tz-aware `datetime_utc` index the rest of the pipeline uses (Synoptic's `fetch_timeseries` produces tz-aware UTC timestamps via `pd.to_datetime(..., utc=True)`).
**Why it happens:** Open-Meteo's ISO8601 timeformat mode doesn't append an explicit UTC marker even when the requested timezone is UTC/GMT.
**How to avoid:** Always parse Open-Meteo's `hourly.time` array with `pd.to_datetime(times, utc=True)` explicitly, and always pass `timezone=UTC` in the request so the values are known to be UTC even though the string doesn't say so.
**Warning signs:** A merge or comparison against Synoptic-derived tz-aware timestamps raising `TypeError: Cannot compare tz-naive and tz-aware` or silently producing an all-NaT/no-match result.

### Pitfall 4: Requesting Open-Meteo's default units produces values needing conversion for wind, but not temperature
**What goes wrong:** Assuming *all* variables need conversion (since the phase description mentions "units converted... knots→m/s, °F→°C" for ASOS) and building a conversion step for Open-Meteo too, when in fact Open-Meteo already returns `temperature_2m` in °C by default and can be asked for `wind_speed_10m` in m/s directly via `wind_speed_unit=ms`.
**Why it happens:** The phase's stated unit-conversion need is specific to ASOS's response format (imperial-only, °F/knots, no unit-selection parameter); Open-Meteo's API supports unit selection at request time.
**How to avoid:** Pass `wind_speed_unit=ms` explicitly in every Open-Meteo request (don't rely on the default, which is `kmh`); leave `temperature_unit` unset (default is already `celsius`).
**Warning signs:** A `PIPELINE_SCHEMA` range-validation failure on `wind_speed` (expected 0-50 m/s) if km/h values were accidentally left unconverted and validated as if they were already m/s.

## Code Examples

### ASOS 1-minute request (live-confirmed shape this session)

```python
# Source: live GET request run this session against
# https://mesonet.agron.iastate.edu/cgi-bin/request/asos1min.py
# Confirmed endpoint, params, and response header/row shape for all four
# target airports (AUS, CRP, MAF, ELP) -- see Pitfall 1 for the station-ID correction.
import requests
import pandas as pd
from units_def import Q

ASOS_BASE = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos1min.py"

def _iso_to_asos_ts(iso: str) -> str:
    # ASOS's sts/ets format observed live: "2025-07-01T00:00Z" (no seconds)
    return iso[:16] + "Z" if not iso.endswith("Z") else iso

def fetch_asos_1min(station: str, start: str, end: str) -> pd.DataFrame:
    params = {
        "station": station,          # 3-letter code, e.g. "AUS" -- NOT "KAUS"
        "vars": ["tmpf", "sknt", "drct"],
        "sts": _iso_to_asos_ts(start),
        "ets": _iso_to_asos_ts(end),
        "sample": "1min",
        "tz": "UTC",
        "what": "download",
    }
    r = requests.get(ASOS_BASE, params=params, timeout=120)
    r.raise_for_status()
    text = r.text
    if "Unknown station provided" in text:
        raise ValueError(f"ASOS: unknown station {station!r} -- check the 3-letter FAA code")

    from io import StringIO
    df = pd.read_csv(StringIO(text))
    if df.empty:
        return df  # Pitfall 2: a well-formed empty response is a real outage, not an error

    df["datetime_utc"] = pd.to_datetime(df["valid(UTC)"], utc=True)
    df["air_temp"] = df["tmpf"].apply(lambda f: Q(f, "degF").to("degC").value)
    df["wind_speed"] = df["sknt"].apply(lambda k: Q(k, "knots").to("m/s").value)
    df["wind_direction"] = df["drct"]
    return df[["datetime_utc", "air_temp", "wind_speed", "wind_direction"]]
```

**Live-confirmed example response (station=AUS, 2024-07-01T00:00Z-00:05Z, `gis=true`):**
```csv
station,station_name,lat,lon,valid(UTC),tmpf,sknt,drct
AUS,Austin Bergstrom Intl,30.1830,-97.6799,2024-07-01 00:00,95,7,142
AUS,Austin Bergstrom Intl,30.1830,-97.6799,2024-07-01 00:01,95,8,142
```

### Open-Meteo Archive API request (live-confirmed shape this session)

```python
# Source: live GET request run this session against
# https://archive-api.open-meteo.com/v1/archive
# using config.CITY_COORDINATES["AUSTIN"] = (30.2711, -97.7437) verbatim
import requests
import pandas as pd

OPEN_METEO_ARCHIVE_BASE = "https://archive-api.open-meteo.com/v1/archive"

def fetch_open_meteo(lat: float, lon: float, start_date: str, end_date: str) -> pd.DataFrame:
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,   # "YYYY-MM-DD"
        "end_date": end_date,
        "hourly": "temperature_2m,wind_speed_10m,wind_direction_10m,shortwave_radiation,relative_humidity_2m",
        "wind_speed_unit": "ms",     # Pitfall 4: avoids a km/h -> m/s conversion step
        "timezone": "UTC",           # Pitfall 3: still parse with utc=True regardless
    }
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
    return df
```

**Live-confirmed example response (lat=30.2711, lon=-97.7437, 2025-07-01, `wind_speed_unit=ms`):**
```json
{"latitude":30.263618,"longitude":-97.69321,"hourly_units":{"time":"iso8601","temperature_2m":"°C","wind_speed_10m":"m/s","wind_direction_10m":"°","shortwave_radiation":"W/m²","relative_humidity_2m":"%"},"hourly":{"time":["2025-07-01T00:00","2025-07-01T01:00", ...],"temperature_2m":[29.9,25.8, ...],"wind_speed_10m":[3.40,4.10, ...],"wind_direction_10m":[160,204, ...],"shortwave_radiation":[291.0,109.0, ...],"relative_humidity_2m":[63,81, ...]}}
```
Note the returned `latitude`/`longitude` (30.263618, -97.69321) is Open-Meteo's snapped grid-cell center, not the exact requested point — expected behavior for a gridded model source, not a bug.

### Wiring the ASOS supplement into `_fetch_station` (recommended shape)

```python
# Extends backend/weather_provider.py::_fetch_station
def _fetch_station(stids: list[str], start: str, end: str, provider: str) -> pd.DataFrame:
    if provider == "synoptic":
        synoptic = attach_provenance(dlr_pipeline.fetch_timeseries(stids, start, end), "synoptic")
        synoptic = attach_city(synoptic)  # resolves city from the frame's own lat/lon columns

        asos_frames = []
        for city in synoptic["city"].dropna().unique():
            station_code = config.ASOS_STATIONS[city]  # e.g. {"AUSTIN": "AUS", ...}
            asos_raw = asos_provider.fetch_asos_1min(station_code, start, end)
            if asos_raw.empty:
                continue  # Pitfall 2: real outage, not a failure
            lat, lon = config.CITY_COORDINATES[city]
            asos_tagged = attach_city(attach_provenance(asos_raw, "asos"), lat=lat, lon=lon)
            asos_frames.append(asos_tagged)

        if not asos_frames:
            return synoptic
        asos_combined = pd.concat(asos_frames)
        return merge_observations(synoptic, asos_combined)  # Pattern 1: reused unmodified

    raise ValueError(
        f"Unknown weather provider: {provider!r}. Only 'synoptic' is "
        "currently implemented."
    )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `_fetch_grid` unconditionally raises ("first one lands in Phase 7") | `_fetch_grid` dispatches to Open-Meteo for `provider="open_meteo"` | This phase | Unblocks the grid path entirely — first real implementation |
| Station path is Synoptic-only | Station path transparently supplements Synoptic with ASOS 1-minute | This phase | Higher temporal density available to C9/C10 without any caller change |

**Deprecated/outdated:** None — this is additive, no prior approach is being replaced.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Open-Meteo Archive API (not Historical Forecast API) is the better fit for WX-04's historical-backfill purpose | Standard Stack, Alternatives Considered | Low — both are live, no-auth, and return the same variable set; switching later is a one-line base-URL/param change, not a redesign |
| A2 | A well-formed, zero-row ASOS response for a given window should NOT trigger D-05's "raise on failure" (only a malformed/erroring response should) | Common Pitfalls, Pitfall 2 | Medium — if the planner instead makes every empty ASOS response raise, `fetch_weather` for the station path would become flaky for any window with a real ASOS sensor gap even when Synoptic (primary) succeeded; recommend confirming this interpretation of D-05 at a plan checkpoint |
| A3 | Resolving ASOS station codes and Open-Meteo lat/lon from `config.CITY_COORDINATES`/a new `config.ASOS_STATIONS` dict (rather than deriving from the caller's raw station-ID list) correctly identifies "the target city" for every real call shape this phase needs to support | Architecture Patterns, Code Examples | Low — matches the existing `resolve_station_city`/`attach_city` precedent from Phase 6; would only misfire if a single `fetch_weather` call mixed station IDs from more than one of the four cities, which no current caller does |

## Open Questions

1. **Does D-05's "raises rather than degrading silently" cover a well-formed-but-empty ASOS response, or only a malformed/erroring one?**
   - What we know: ASOS 1-minute data has real, expected outage windows (Pitfall 2, live-confirmed for `ELP` on one specific date). Synoptic can succeed while ASOS returns nothing for the same window.
   - What's unclear: Whether "no ASOS data available for this specific window" should be treated as an acceptable partial result (return Synoptic-only) or as a failure requiring `fetch_weather` to raise, per D-05's literal wording.
   - Recommendation: Treat a well-formed empty ASOS response as non-fatal (don't raise, don't add rows) and reserve raising for HTTP errors and the "Unknown station provided"/malformed-body case (Pitfall 1) — flag this interpretation for explicit user confirmation at the plan's first checkpoint, since D-05 is a locked decision and this is a boundary case it doesn't explicitly resolve.

2. **Does Phase 7's ASOS wiring need to anticipate Phase 9's TCEQ-as-primary change?**
   - What we know: D-03 locks ASOS supplementation to `fetch_weather(..., provider="synoptic")` specifically. `WX-02`'s own requirement text says "as a supplement to TCEQ" (TCEQ is Phase 9's not-yet-built primary).
   - What's unclear: Whether Phase 7 should structure the ASOS-supplement call so it's trivially reattachable to a future `provider="tceq"` branch, or whether that's explicitly Phase 9's problem to solve when TCEQ lands.
   - Recommendation: Scope Phase 7 to `provider="synoptic"` only, per this phase's locked D-03 wording. Note for Phase 9's own research/planning that ASOS's supplement logic will need to be either duplicated or refactored into a shared helper at that point.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Network access to `mesonet.agron.iastate.edu` | ASOS 1-minute fetch (WX-02) | ✓ [VERIFIED: live GET succeeded this session] | n/a | — |
| Network access to `archive-api.open-meteo.com` | Open-Meteo historical fetch (WX-04) | ✓ [VERIFIED: live GET succeeded this session] | n/a | — |
| `requests` (Python package) | Both fetches | ✓ [VERIFIED: `.venv` this session] | 2.32.5 | — |
| `pandas` (Python package) | DataFrame construction/merge | ✓ [VERIFIED: `.venv` this session] | 2.3.3 | — |
| ASOS/Open-Meteo API keys or secrets | Neither — both are no-auth | N/A (none required) [VERIFIED: both live requests succeeded with zero auth headers/params this session] | — | — |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest [VERIFIED: `/Users/aphan/Documents/Senior_Design/pytest.ini`, read this session] |
| Config file | `/Users/aphan/Documents/Senior_Design/pytest.ini` (`pythonpath = backend`, `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py`) |
| Quick run command | `pytest backend/tests/weather_provider_test.py -x` |
| Full suite command | `pytest` (run from repo root; picks up `testpaths` from `pytest.ini`) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WX-02 | ASOS-supplemented station fetch produces union-of-timestamps rows, correct unit conversion, correct provenance | unit | `pytest backend/tests/weather_provider_test.py -k asos -x` | ❌ Wave 0 (new tests needed; existing file has none for ASOS yet) |
| WX-02 | ASOS response for an unknown/mistyped station raises | unit | `pytest backend/tests/asos_provider_test.py -x` | ❌ Wave 0 (new test file) |
| WX-04 | Open-Meteo grid fetch returns all 5 `PIPELINE_SCHEMA` weather columns from one request, correctly mapped and unit-converted | unit | `pytest backend/tests/open_meteo_provider_test.py -x` | ❌ Wave 0 (new test file) |
| WX-04 | Open-Meteo path reachable only via `provider="open_meteo"` on the grid shape; station path unaffected | unit | `pytest backend/tests/weather_provider_test.py -k open_meteo -x` | ❌ Wave 0 (new tests needed) |
| WX-02, WX-04 | Both providers' rows carry correct provenance | unit | `pytest backend/tests/weather_provider_test.py -k provenance -x` | ✅ existing provenance tests already establish the pattern (`test_merge_provenance_names_the_actual_supplier_per_field` etc.) — extend, don't replace |

Existing test conventions to follow (confirmed by reading `backend/tests/weather_provider_test.py` and `backend/tests/dlr_pipeline_test.py` this session): module-level plain-`assert` functions (no test classes), `monkeypatch.setattr(module, "requests", ...)` or a `_FakeResponse` class exposing `.raise_for_status()`/`.json()` to avoid live network calls in the test suite, synthetic-frame builder helper functions per test module.

### Sampling Rate
- **Per task commit:** `pytest backend/tests/weather_provider_test.py -x`
- **Per wave merge:** `pytest`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/asos_provider_test.py` — covers WX-02 (new file, mocked `requests.get`)
- [ ] `backend/tests/open_meteo_provider_test.py` — covers WX-04 (new file, mocked `requests.get`)
- [ ] Extend `backend/tests/weather_provider_test.py` with ASOS-supplement and `provider="open_meteo"` dispatch tests
- [ ] No framework install needed — pytest already configured project-wide

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | No | Neither provider uses auth — nothing to secure |
| V3 Session Management | No | Stateless HTTP GETs, no sessions |
| V4 Access Control | No | No access-control surface introduced |
| V5 Input Validation | Yes | Validate provider responses before use: `raise_for_status()`, explicit empty/malformed-body checks (Pitfall 1), and `units_def.validate_pipeline_row` range/unit checks on the resulting rows before they enter the pipeline |
| V6 Cryptography | No | No secrets, no crypto — reinforces Success Criterion #4 (no new `.env` entries) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed/unexpected provider response silently accepted as valid data | Tampering / Information Disclosure (data-integrity variant) | `raise_for_status()` + explicit body-shape checks (Pitfall 1) + `validate_pipeline_row` range checks before the row enters `PIPELINE_SCHEMA` — matches D-05's fail-loud requirement |
| SSRF via user-controlled URL | Spoofing / Elevation of Privilege | Not applicable — both endpoints are fixed constants (`ASOS_BASE`, `OPEN_METEO_ARCHIVE_BASE`), never built from caller input beyond query-parameter values (station code, lat/lon, dates), none of which are attacker-controlled in this project's current call sites |

## Sources

### Primary (HIGH confidence)
- Live `GET` requests run this session against `mesonet.agron.iastate.edu/cgi-bin/request/asos1min.py` (stations `AUS`, `CRP`, `MAF`, `ELP`) — endpoint, parameters, response CSV shape, station-ID correction, and outage-gap behavior all confirmed directly.
- Live `GET` request run this session against `mesonet.agron.iastate.edu/geojson/network/TX_ASOS.geojson` — confirmed the 3-letter station identifiers for all four target airports.
- Live `GET` request run this session against `archive-api.open-meteo.com/v1/archive` (lat/lon = `config.CITY_COORDINATES["AUSTIN"]`) — endpoint, parameters, response JSON shape, unit-parameter behavior all confirmed directly.
- `backend/weather_provider.py` — read in full this session (`_fetch_station`, `_fetch_grid`, `merge_observations`, `_prepare_merge_side`, `attach_provenance`, `attach_city`, `resolve_station_city`, `PROVENANCE_FIELD_MAP`, `MERGE_KEY`).
- `backend/units_def.py` — read in full this session (`PIPELINE_SCHEMA`, `KNOWN_PROVIDER_NAMES`, `Q` class, `CONVERSIONS`).
- `backend/config.py` — read in full this session (`CITY_COORDINATES`).
- `backend/dlr_pipeline.py::fetch_timeseries` — read this session (existing Synoptic fetch pattern, `requests` usage convention).
- `backend/tests/weather_provider_test.py`, `backend/tests/dlr_pipeline_test.py`, `pytest.ini` — read this session (test conventions, framework config).
- Empirical `merge_observations` test run this session (`.venv/bin/python3`, synthetic Synoptic+ASOS frames) — proves Pattern 1's central claim.

### Secondary (MEDIUM confidence)
- `docs/data-science/decisions/data_provider.md` §"ASOS 1-minute data" (lines 134-155) and §"Open-Meteo" (lines 156-176) — read this session; both sections state their own findings were "confirmed live" in a prior research pass, though the specific station-ID discrepancy (Pitfall 1) was not caught in that pass.
- Open-Meteo official docs (`open-meteo.com/en/docs/historical-weather-api`, `open-meteo.com/en/docs/historical-forecast-api`) — fetched this session, cross-checked against and consistent with the live API response.
- IEM CGI help page (`mesonet.agron.iastate.edu/cgi-bin/request/asos1min.py?help=`) — fetched this session for parameter names; variable-code list was incomplete in the fetched excerpt and was cross-checked via GitHub source (`akrherz/iem`) and live requests instead.

### Tertiary (LOW confidence)
- None — every load-bearing claim in this document was either read directly from project source, confirmed via a live API call this session, or cited from the providers' own official documentation.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — both endpoints live-confirmed this session with real data for the exact four target cities/coordinates
- Architecture: HIGH — `merge_observations` reuse claim is empirically proven, not inferred
- Pitfalls: HIGH — all four pitfalls were discovered via direct live testing this session, not training-data speculation

**Research date:** 2026-09-11
**Valid until:** 30 days (stable, no-auth public APIs; re-verify station-ID/endpoint stability if not planned within that window)
