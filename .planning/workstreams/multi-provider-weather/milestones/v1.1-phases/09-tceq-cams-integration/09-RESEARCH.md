# Phase 9: TCEQ CAMS Integration - Research

**Researched:** 2026-09-13
**Domain:** HTML report scraping (no REST/JSON API) — TCEQ CAMS air-quality monitoring network, wind/temp/RH extraction for a physics pipeline
**Confidence:** HIGH (site selection, report structure, units, and timezone handling are all live-fetch-confirmed this session; a few integration-shape questions remain open for the planner)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** For each of the four cities, the specific CAMS site ID is chosen during research by
  live-fetching that city's region listing (`monitors.pl?region=<n>`) and confirming which
  candidate site has the most complete wind/temp/RH data, then hard-coding that CAMS ID — the
  same evidence-based approach `data_provider.md` already used to confirm Corpus Christi CAMS 83.
  Applies to Austin (11 candidate sites in region 11) and the as-yet-unconfirmed Midland/El Paso
  sites alike. — **Reversibility:** reversible — a hard-coded site ID is a config-level change if
  a better site is found later.
- **D-02:** Site-selection criteria weigh wind/temp/RH completeness **only** — not proximity to
  the corridor endpoint, solar availability, or any other secondary factor. Matches how Corpus
  Christi CAMS 83 was already chosen.
- **D-03:** If no candidate site in a city has fully complete wind/temp/RH data, pick the
  most-complete site anyway; missing individual fields go null per-row rather than blocking the
  city's integration or requiring a checkpoint. Consistent with D-06 (null-when-absent) and the
  NSRDB/Open-Meteo null-if-absent precedent (Phase 7/8).
- **D-04:** TCEQ's confirmed field set (per `data_provider.md`) is wind speed/direction/temp — RH
  is not confirmed present at every site. When the chosen site's report has no RH field,
  `relative_humidity` is left **null** on TCEQ-sourced rows, not backfilled, dropped, or used to
  disqualify a site — same precedent as NSRDB's solar-only population (Phase 8 D-02) and
  Open-Meteo's null-if-absent handling (Phase 7 D-02).
- **D-05:** When RH is null for a TCEQ row, the `humidity_source` provenance column is left
  null/unset for that row — provenance is only set where the mapped field itself has a value,
  matching the existing `attach_provenance` behavior already used for NSRDB's null
  wind/temp/humidity rows. No new sentinel provenance value is introduced.
- **D-06:** On an unreachable, malformed, or missing-required-field CAMS report,
  `fetch_weather(..., provider="tceq")` **raises** — it does not fall back to Synoptic or any
  other provider. Fallback-to-Synoptic wiring is explicitly WX-06/Phase 10 scope and stays out of
  this phase entirely; this phase only needs to fail loud, matching the fail-loud precedent
  already established for ASOS/Open-Meteo (Phase 7 D-05) and NSRDB (Phase 8). —
  **Reversibility:** reversible — Phase 10 wraps this call in fallback logic later without needing
  to change this phase's raise behavior.
- **D-07:** "Missing a needed field" that triggers a raise means **wind speed, wind direction, or
  temperature** are absent from the site's report — these are the fields confirmed present at
  every TCEQ site checked in `data_provider.md`, so their absence signals a broken or
  unexpectedly-shaped report. RH's absence is expected (per D-04) and is never itself a reason to
  raise.
- **D-08:** TCEQ implements the same station-based `fetch_weather(stids, start, end,
  provider="tceq")` signature as Synoptic/ASOS — "current" readings (ROADMAP Success Criterion 1)
  just means a caller passes a narrow/recent window; there is no separate single-reading code
  path. Keeps the adapter interface uniform across all station providers.
- **D-09:** Because `daily_summary.pl` reports one calendar day per request, a multi-day `(start,
  end)` range is served by fetching one report per calendar day in the range and concatenating the
  resulting hourly rows — not restricted to same-day requests only.

### Claude's Discretion

- Exact HTML parsing approach for `daily_summary.pl` (table structure, field-name matching,
  handling of the report's specific column layout) — confirm exact structure live during research,
  per the same "confirm live, don't just trust docs" approach `data_provider.md` used for Corpus
  Christi/Austin. **Resolved this session** — see "Report Structure" below.
- Exact module name/location for the new provider (`backend/tceq_provider.py`, following the
  `asos_provider.py`/`open_meteo_provider.py`/`nsrdb_provider.py` naming convention already
  established). **Resolved this session** — `backend/tceq_provider.py`.
- Unit conversions needed for TCEQ's reported units (confirm exact units live — e.g. wind speed
  may be mph, needing mph→m/s like ASOS's knots→m/s). **Resolved this session** — see "Units"
  below.
- Whether Midland/El Paso's CAMS site regions need additional discovery beyond the region numbers
  already suspected (region 7 for Midland/Odessa, region 6 for El Paso) — confirm live.
  **Resolved this session** — both region numbers confirmed correct.
- Whether TAMISWeb (an alternate TCEQ interface, not yet checked per `data_provider.md`) is worth
  investigating if `daily_summary.pl` proves insufficient for any of the four cities — default to
  `daily_summary.pl` unless research finds a blocking reason not to. **Not needed** —
  `daily_summary.pl` is sufficient for all four cities (see CAMS Site Selection below); TAMISWeb
  was not investigated.

### Deferred Ideas (OUT OF SCOPE)

- **Fallback/primary-selection logic** (if TCEQ fails, fall back to Synoptic) was raised and
  explicitly locked out of this phase's scope (D-06) — it is WX-06 / Phase 10's job.
- **TAMISWeb** as an alternate TCEQ data interface was noted in `data_provider.md` as unchecked;
  left as Claude's Discretion to investigate only if `daily_summary.pl` proves insufficient — not
  a planned deliverable of this phase.
- **Live per-site solar-availability confirmation for Midland/El Paso** (WX-09, out of scope per
  REQUIREMENTS.md) — not raised again here; solar is not part of this phase's field scope
  (wind/temp/RH only).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| WX-01 | Given a target city, the system fetches wind speed, wind direction, temperature, and relative humidity from TCEQ CAMS as the primary real-station source, for all four cities. | "CAMS Site Selection" table below gives a live-verified CAMS ID per city with its actual current parameter availability; "Report Structure" and "Units" sections give the exact scrape/parse/convert recipe; "Common Pitfalls" documents the GET-parameter, timezone, and malformed-response traps that would otherwise silently corrupt or misdate the data. |
</phase_requirements>

## Summary

TCEQ CAMS is confirmed, this session, to be viable as the primary wind/temp source for all four
cities, with usable Relative Humidity at two of the four (Corpus Christi, El Paso). Every finding
below was obtained by fetching the live production endpoints with `curl` and reading the raw HTML
response — not by trusting `monitors.pl`'s "Active" labels alone, and not by trusting an
AI-summarized fetch (an initial `WebFetch` pass on Austin's region page hallucinated two sites as
"Active" that raw `curl` shows are actually deactivated — see Pitfall 6). The `daily_summary.pl`
endpoint is a plain, unauthenticated HTML report: no REST/JSON API exists, confirming
`data_provider.md`'s original assessment. The report is well-structured (one `<table border='1'>`
row per monitored parameter, one column per hour) and is straightforward to parse with
BeautifulSoup (`bs4`, already in `requirements.txt` and already installed in `.venv`, though never
yet imported by any provider module in this codebase). Three of the four candidate `.venv` findings
override or add material detail to `data_provider.md`'s prior page: 1) the CGI script silently
ignores date query parameters unless `select_date=user` is also present, always defaulting to
"today" instead — this is a severe, non-obvious trap that would silently mis-date every historical
request if not caught; 2) TCEQ reports in **fixed Local Standard Time** (never DST-adjusted) — CST
(UTC-6) for the three Central-zone cities and MST (UTC-7) for El Paso — which is a second,
independent silent-corruption trap if a naive zoneinfo/pytz conversion is used instead of a fixed
offset; 3) Corpus Christi CAMS 83, already locked in `data_provider.md`, actually has a live,
populated Relative Humidity field, better than that document's original (RH-agnostic) assessment
implied.

**Primary recommendation:** Build `backend/tceq_provider.py` (mirroring
`nsrdb_provider.py`/`asos_provider.py`'s no-network-on-import, one-`fetch_*`-function shape) using
`requests.get` with `select_date=user&time_format=24hr` plus a per-city hard-coded CAMS ID from a
new `config.TCEQ_STATIONS` dict, parsed with BeautifulSoup, with the four CAMS IDs below.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Per-city CAMS site selection (D-01) | Config / Database tier (`backend/config.py`) | — | A fixed, hard-coded lookup — identical shape to `config.ASOS_STATIONS` — not something resolved at request time. |
| HTML report fetch + parse (`daily_summary.pl`) | API/Backend tier (`backend/tceq_provider.py`, new module) | — | Same tier as `asos_provider.py`/`nsrdb_provider.py` — a provider adapter with no UI surface. |
| Unit conversion (mph→m/s, degF→degC) | API/Backend tier (`units_def.Q`) | — | Reuses the existing dimensional-analysis module; never hand-rolled (matches every other Phase 7/8 provider). |
| Local-standard-time → UTC conversion | API/Backend tier (`backend/tceq_provider.py`) | — | A fixed per-site UTC offset applied inside the new provider module — not delegated to a general timezone library, since TCEQ's "never-DST" behavior is site-specific domain knowledge, not a generic timezone fact (see Pitfall 2). |
| Provider dispatch (`provider="tceq"`) | API/Backend tier (`backend/weather_provider.py::_fetch_station`) | — | Existing integration point per `09-CONTEXT.md` canonical refs; a new `elif` branch alongside `"synoptic"`. |
| Provenance tagging | API/Backend tier (`weather_provider.attach_provenance`) | — | Fully reusable as-is (already registered `"tceq"` in `KNOWN_PROVIDER_NAMES`). |
| Range validation | API/Backend tier (`units_def.validate_pipeline_row` / a local `_range_check`, matching ASOS/NSRDB) | — | Same pattern as every other provider module — an in-module backstop, not delegated to the caller. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `requests` | 2.x (already a transitive dependency via `asos_provider.py`/`nsrdb_provider.py`, no new pin needed) | HTTP GET against `daily_summary.pl` | Already the project's sole HTTP client; every other Phase 7/8 provider uses it identically. |
| `beautifulsoup4` (`bs4`) | 4.14.3 `[VERIFIED: /Users/aphan/Documents/Senior_Design/.venv/bin/python3 -c "import bs4; print(bs4.__version__)"` → `4.14.3`, run this session] | Parse the nested `<table>` HTML of `daily_summary.pl` into rows/cells | Already declared in `requirements.txt` (`bs4 4.14.3` — note: **missing `==`**, see Pitfall 8) and already installed in `.venv`, but this is the **first** provider module to actually import it — every prior provider (ASOS, NSRDB, Open-Meteo) parses CSV/JSON, not HTML. `pd.read_html` was considered and rejected — see "Don't Hand-Roll" below. |
| `pandas` | 2.3.3 `[VERIFIED: .venv, same as above]` | Assemble the per-day parsed rows into a `PIPELINE_SCHEMA`-shaped frame, concatenate per-day frames (D-09) | Already the project's dataframe library throughout. |
| `units_def.Q` | in-repo, `backend/units_def.py` | mph→m/s and degF→degC conversion | Already registers both `"mph"` and `"degF"` (`UNIT_DIMENSIONS`/`CONVERSIONS`, lines 46 and 41 respectively `[VERIFIED: backend/units_def.py:46]` `"mph":  "velocity",` and `[VERIFIED: backend/units_def.py:41]` `"degF": "temperature",`) — no schema change needed, unlike ASOS which needed only knots (already present) and degF (already present). |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `lxml` | 5.4.0 `[VERIFIED: .venv, same check as above]` | Optional faster HTML parser backend for `BeautifulSoup(html, "lxml")` | Already installed in `.venv` (a `bs4` transitive dependency) but **not declared** in `requirements.txt` — either declare it explicitly (`BeautifulSoup(html, "lxml")`) or use the stdlib `"html.parser"` backend (`BeautifulSoup(html, "html.parser")`, zero new dependency, slightly slower, proven adequate for pages this size). Recommend `"html.parser"` unless a planner wants to also add `lxml==5.4.0` to `requirements.txt` for the speed win — the report pages are ~40-70KB, parse time is a non-issue either way. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `bs4` | `pandas.read_html(html)` | Rejected — `read_html` returns the *whole* table (26 columns: label, 24 hourly values, repeated label, POC) as a wide `DataFrame` with duplicate/ambiguous column names (multiple "Parameter Measured" headers) and coerces the `"FEW"`/`"NA"` placeholder cells inconsistently across pandas versions; it also can't distinguish `Wind Direction` from `Resultant Wind Direction` reliably without post-hoc string matching identical to what `bs4` gives directly, so it buys nothing over `bs4` and adds fragility. |
| `bs4` | Regex against raw HTML (matching ASOS/NSRDB's string-based approach) | Rejected — ASOS/NSRDB's string matching works because their responses are single-line CSV; `daily_summary.pl`'s response is a deeply nested HTML table with inline `<font>`/`<a>` wrapper tags around every data cell (bold/italic for min, underline for max, `<a>` for "FEW"/"NA" placeholders) — a regex would need to reimplement half of an HTML parser to strip these reliably. `bs4.get_text(strip=True)` handles this in one call per cell. |

**Installation:**
```bash
# No new pins required — bs4 and pandas/requests are already in requirements.txt / .venv.
# Optional, if the planner wants the faster parser backend:
pip install lxml==5.4.0   # and add lxml==5.4.0 to requirements.txt
```

**Version verification:** `bs4`, `lxml`, `pandas`, `requests` were all verified installed in the
project's actual `.venv` this session (`/Users/aphan/Documents/Senior_Design/.venv/bin/python3`,
not system Python — system Python lacks `lxml`). No `pip index versions` registry check was run
since none of these are *new* pins to add; `bs4`/`pandas` are already declared in
`requirements.txt`.

## Package Legitimacy Audit

No **new** package installation is required by this phase — `bs4`, `pandas`, and `requests` are
already declared in `requirements.txt` and already installed in `.venv`. The audit below was still
run per protocol, since this is the first phase to actually `import bs4` in provider code.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `bs4` | PyPI | latest release 2024-01-17 (project itself is 15+ years old — Beautiful Soup 4 predates this registry lookup's metadata) | unknown (registry lookup returned `null`) | none returned by lookup | `[SUS]` (`reasons: unknown-downloads, no-repository`) | **Already an approved, already-installed dependency** (`requirements.txt`) — not a new install this phase. Flagged per protocol anyway: planner should add a `checkpoint:human-verify` before the first `import bs4` line lands in `tceq_provider.py`, even though it is not a new pin, since the automated legitimacy signal genuinely came back incomplete. |
| `lxml` | PyPI | latest release 2026-09-02 (`reasons: too-new` — this is a *release* recency flag on an old, extremely well-known project, not a new-package flag) | unknown (registry lookup returned `null`) | `github.com/lxml/lxml` (returned) | `[SUS]` (`reasons: too-new, unknown-downloads`) | **Not required** — recommend the stdlib `"html.parser"` backend instead (see Supporting table) to avoid adding a new pin entirely. If a future plan does add `lxml==5.4.0` to `requirements.txt`, gate that specific pin behind a `checkpoint:human-verify`. |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** `bs4` (already installed, no new install action — flag only the first-use `import`), `lxml` (not recommended for this phase; skip it and the flag becomes moot).

## Architecture Patterns

### System Architecture Diagram

```
caller (dlr_pipeline / corridor logic)
        |
        v
weather_provider.fetch_weather(stids=[cams_id], start, end, provider="tceq")
        |
        v
weather_provider._fetch_station(stids, start, end, "tceq")   <-- NEW elif branch
        |
        v
tceq_provider.fetch_tceq(cams_id, start, end)                <-- NEW module
        |
        |  D-09: one calendar day per report -- loop [start..end] by local calendar date
        v
   for each calendar day:
        |
        v
   requests.get(daily_summary.pl, params={cams, select_date="user",
                user_month, user_day, user_year, time_format="24hr"})
        |
        v
   [malformed/unreachable? -- check for <h1><a ...CAMS=<id>> AND <table border='1'>]
        |  yes: raise ValueError (D-06/D-07)     no: continue
        v
   BeautifulSoup(html).find(table, border='1')
        |
        v
   for each <tr>: match <strong> text exactly against
   {"Wind Speed", "Wind Direction", "Outdoor Temperature", "Relative Humidity"}
        |
        v
   per matched row: extract 24 hourly <td> text values,
   "FEW"/"NA" -> null, numeric string -> float
        |
        v
   apply per-site fixed UTC offset (CST=-6 or MST=-7, never DST) to each hour column
   -> datetime_utc
        |
        v
   units_def.Q(value, "mph").to("m/s")   /   units_def.Q(value, "degF").to("degC")
        |
        v
   concat all calendar-day frames -> _range_check (mirrors asos_provider._range_check)
        |
        v
   [missing wind_speed, wind_direction, OR air_temp entirely? -> raise, per D-07]
        |
        v
   return DataFrame(columns=[datetime_utc, air_temp, wind_speed, wind_direction,
                              relative_humidity])
        |
        v
weather_provider.attach_provenance(frame, "tceq")   <-- reused as-is (D-05's mechanism)
        |
        v
returned to caller, PIPELINE_SCHEMA-conformant
```

### Recommended Project Structure

```
backend/
├── tceq_provider.py         # NEW -- this phase. fetch_tceq(cams_id, start, end) -> DataFrame
├── weather_provider.py      # MODIFIED -- new "tceq" branch in _fetch_station
├── config.py                # MODIFIED -- new TCEQ_STATIONS dict (per-city CAMS ID)
├── units_def.py             # UNCHANGED -- "tceq" already in KNOWN_PROVIDER_NAMES, mph/degF
│                             #   already registered units
└── tests/
    └── tceq_provider_test.py  # NEW -- mirrors asos_provider_test.py's _FakeResponse pattern
```

### Pattern 1: Config-driven per-city site ID (matches `config.ASOS_STATIONS`)

**What:** A flat `dict[str, str]` in `config.py` mapping each of the four `CITY_COORDINATES` keys
to its hard-coded CAMS ID, decided by this research (D-01).
**When to use:** Any time the adapter needs to resolve "which CAMS site serves this city" — never
computed dynamically, never looked up via `monitors.pl` at request time (that lookup already
happened, in this research pass).
**Example:**
```python
# backend/config.py -- new dict, same shape/placement as ASOS_STATIONS (line 252-257)
# CAMS site IDs, live-confirmed this session (09-RESEARCH.md "CAMS Site Selection") --
# selected for wind speed + wind direction + temperature completeness (D-01/D-02), NOT
# proximity or solar. Values are strings to match daily_summary.pl's `cams=<id>` query param.
TCEQ_STATIONS: dict[str, str] = {
    "AUSTIN": "38",           # Audubon C38 -- true Wind Direction (not resultant-only), no RH
    "CORPUS_CHRISTI": "83",   # Corpus Christi Palm C83 -- WS+WD+Temp+RH all live-confirmed
    "MIDLAND": "1095",        # Midland Avalon Drive C1095 -- true WD (added 2026-05-01), no RH
    "EL_PASO": "41",          # Chamizal C41 -- WS+WD+Temp+RH+solar all live-confirmed, most complete of the four
}
```

### Pattern 2: HTML table row extraction by exact label match, not substring

**What:** Row identification inside the `<table border='1'>` must match the `<strong>` text
*exactly* (`"Wind Direction"` == `"Wind Direction"`), never with `in`/substring matching.
**When to use:** Always, when scanning `daily_summary.pl`'s rows.
**Why:** `"Resultant Wind Direction"` and `"Std. Dev. Wind Direction"` both contain the substring
`"Wind Direction"` — a substring match would silently grab the wrong row (a systematic,
hard-to-detect data-quality bug, not a crash).
**Example:**
```python
# Source: live HTML fetched this session, tceq.texas.gov/cgi-bin/compliance/monops/daily_summary.pl?cams=83
# Row label cell: <a ...><strong>Wind Direction</strong></a>
# Row label cell (different row): <a ...><strong>Resultant Wind Direction</strong></a>
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

### Pattern 3: Fixed (never-DST) per-site UTC offset

**What:** A per-city constant UTC offset, not a `zoneinfo`/`pytz` timezone-aware conversion.
**When to use:** Converting every extracted hourly value's local-standard-time hour to
`datetime_utc`.
**Why:** TCEQ's own report text states data is presented in **Local Standard Time year-round**,
which is fixed CST (UTC-6) for three of the four cities and fixed MST (UTC-7) for El Paso, even
during months when the true local clock time is CDT/MDT (UTC-5/UTC-6). A `zoneinfo("America/
Chicago")`-based conversion would apply DST and introduce a systematic 1-hour error for
roughly 8 months of the year (see Pitfall 2).
**Example:**
```python
# Source: live HTML fetched this session, same daily_summary.pl responses --
# verbatim quoted text: "We also present our data in Local Standard Time for each measuring
# site... During Daylight Savings, this introduces another apparent one-hour time lag in the
# data."  Confirmed per-site literal labels: cams=83 (Corpus Christi) -> "All times shown are
# in CST"; cams=38 (Austin) -> "All times shown are in CST"; cams=1095 (Midland) -> "All times
# shown are in CST"; cams=41 (El Paso) -> "All times shown are in MST".
TCEQ_FIXED_UTC_OFFSET_HOURS: dict[str, int] = {
    "38": -6,    # Austin -- CST, never DST-adjusted
    "83": -6,    # Corpus Christi -- CST, never DST-adjusted
    "1095": -6,  # Midland -- CST, never DST-adjusted
    "41": -7,    # El Paso -- MST, never DST-adjusted
}
```

### Anti-Patterns to Avoid

- **Using `zoneinfo("America/Chicago")` / `pytz.timezone("America/Chicago")` to convert TCEQ's
  reported hour to UTC:** produces a correct offset only in winter; silently wrong by exactly one
  hour for roughly 8 months of the year (mid-March to early November), since TCEQ never advances
  for Daylight Saving. Use the fixed offset in Pattern 3 instead.
- **Requesting `daily_summary.pl` with only `cams`, `user_month`, `user_day`, `user_year` in the
  query string (no `select_date=user`):** the CGI script silently returns **today's** report
  regardless of the date parameters — no error, no different response shape, HTTP 200 either way.
  See Pitfall 1.
- **Treating a non-2xx HTTP status as the malformed/unreachable signal:** every response this
  session, including a nonexistent CAMS ID (`cams=999999`), returned HTTP 200. The signal is
  absence of the site-specific `<h1>` (see Pattern in Common Pitfalls / Pitfall 3), matching the
  same "status alone is not a trust signal" lesson `asos_provider.py` already encodes for its own
  endpoint (line 103-106 of that file).
- **Substring-matching row labels** (see Pattern 2) — silently grabs `"Resultant Wind Direction"`
  or `"Std. Dev. Wind Direction"` data under the `"wind_direction"` key.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| mph→m/s, degF→degC conversion | A local conversion constant/formula in `tceq_provider.py` | `units_def.Q(value, "mph").to("m/s")` / `units_def.Q(value, "degF").to("degC")` | Both units are already registered (`units_def.py:46`, `:41`) — a hand-rolled conversion is exactly the kind of "units regression" `units_def._range_check`-style gates exist to catch, and every other Phase 7/8 provider already delegates to `Q`. |
| HTML table parsing | Regex against the raw HTML, or manual string splitting on `<td>` | `BeautifulSoup` (`bs4`, already installed) | See "Alternatives Considered" — the inline `<font>`/`<a>` wrapper markup around every cell (bold/italic/underline styling, "FEW"/"NA" placeholder links) makes a hand-rolled string parser fragile in ways `bs4.get_text(strip=True)` avoids in one call. |
| Site-completeness discovery | A live `monitors.pl` lookup performed at request/runtime | The hard-coded `config.TCEQ_STATIONS` dict (Pattern 1) | D-01/D-02 explicitly call for a one-time, research-phase decision, hard-coded afterward — exactly like `config.ASOS_STATIONS`. A runtime lookup would also require scraping a *second* HTML page on every request for no benefit. |
| Provenance tracking | A TCEQ-specific provenance column or sentinel value | `weather_provider.attach_provenance(frame, "tceq")` (existing, unmodified) | Already handles "set provenance only where the mapped column is present and non-null" — exactly D-05's required mechanism for TCEQ's null-RH rows at Austin/Midland. |

**Key insight:** Every non-scraping piece of this phase (units, provenance, range validation
shape, dispatch shape) is already solved by Phase 6-8's existing machinery. The *only* genuinely
new work is the HTML scrape itself — which is exactly why `data_provider.md`'s original assessment
called TCEQ "the highest-integration-effort provider in the milestone."

## Common Pitfalls

### Pitfall 1: `daily_summary.pl` silently ignores date parameters without `select_date=user`

**What goes wrong:** A GET request with `cams=<id>&user_month=<m>&user_day=<d>&user_year=<y>` (no
`select_date` param) returns HTTP 200 with a well-formed report — but for **today's** date, not
the requested one. There is no error, no warning, and no different response shape to detect this
by inspection alone.
**Why it happens:** The site's HTML form (`<form name='sel_daily' method='post' ...>`) includes a
`<input type='hidden' name='select_date' value='user' />` field that is only present when the form
is actually submitted with a custom date selected. A bare GET to the same URL with only the date
sub-fields populated omits this hidden field, and the CGI script defaults to `select_date='today'`
behavior.
**How to avoid:** Always include `select_date=user` explicitly in the request parameters, alongside
`user_month` (0-indexed: January=0), `user_day`, `user_year`. Live-confirmed working request:
`daily_summary.pl?cams=83&select_date=user&user_month=6&user_day=1&user_year=2026&time_format=24hr`
→ correctly returned "Wednesday, July 1, 2026" `[VERIFIED: tceq.texas.gov daily_summary.pl, fetched this session]`.
**Warning signs:** If a historical-range fetch (D-09's per-day loop) ever returns 24 identical
rows across every requested day, this is almost certainly the cause — the loop silently fetched
"today" N times instead of N distinct days.

### Pitfall 2: Reports use fixed Local Standard Time, never Daylight Saving

**What goes wrong:** Converting TCEQ's reported hour to UTC using a DST-aware timezone library
(`zoneinfo`, `pytz`) with `America/Chicago`/`America/Denver` produces a value that is off by
exactly one hour for roughly 8 months of the year.
**Why it happens:** TCEQ's own report page states, verbatim
`[VERIFIED: tceq.texas.gov/cgi-bin/compliance/monops/daily_summary.pl, fetched this session]`:
*"We also present our data in Local Standard Time for each measuring site. For most of Texas this
is [CST]. During Daylight Savings, this introduces another apparent one-hour time lag in the
data."* The per-site literal confirms this in practice: `cams=83`/`cams=38`/`cams=1095` (Austin,
Corpus Christi, Midland — all nominally Central time) each render `"All times shown are in CST"`
even on a September request (during Central Daylight Time in the real world); `cams=41` (El Paso,
nominally Mountain time) renders `"All times shown are in MST"` on the same September date.
**How to avoid:** Apply a fixed integer UTC offset per site (Pattern 3 above: -6 for the three
CST-labeled sites, -7 for El Paso's MST-labeled site) — never a timezone-aware library call.
**Warning signs:** A TCEQ-sourced row whose hour, once "converted," lines up suspiciously close
(within an hour) to a Synoptic/ASOS row for the same real event but is offset by exactly ±1 hour
during summer months.

### Pitfall 3: A non-existent or unreachable CAMS ID returns HTTP 200 with a different page shape, not an error status

**What goes wrong:** Checking `response.raise_for_status()` or `response.status_code` alone will
never catch an invalid CAMS ID — the endpoint always answers 200.
**Why it happens:** Confirmed this session with `cams=999999&select_date=user&user_month=8&
user_day=1&user_year=2026` `[VERIFIED: tceq.texas.gov, fetched this session]`: HTTP status was
`200`; the page rendered the generic site-**selection** form instead of a site-specific report —
its `<h1>` reads `<h1>Data by Site by Date (all parameters)</h1>` (no site name, no `<a
href=...&CAMS=999999>` link), and it contains **zero** `<table>` elements at all, vs. a valid
site's response which has exactly 4 (`border='0'` ×3, `border='1'` ×1 for the data table).
**How to avoid:** After fetching, check for BOTH: (a) an `<h1>` containing an `<a>` tag whose
`href` contains `CAMS=<requested id>`, AND (b) presence of a `<table border='1'>` element. Absence
of either → raise, matching D-06/D-07's fail-loud requirement (mirrors `asos_provider.py`'s
"Unknown station provided" string-check pattern, lines 107-112, for the equivalent TCEQ failure
mode).
**Warning signs:** A parsed frame with zero rows extracted, or a KeyError/AttributeError from
`table.find_all("tr")` on a `None` table — both indicate the fetch silently returned the
generic-form page instead of a report.

### Pitfall 4: "FEW" and "NA" placeholder cells are not numeric strings and must not raise on `float()`

**What goes wrong:** A cell that has not yet accumulated 45 minutes of 5-minute readings within
the hour renders `"FEW"`; an hour whose average has "not been calculated yet" (a not-yet-elapsed
hour on the *current* day's report) renders `"NA"`. Both are wrapped in `<a>`/`<font
color='gray'>` tags but their `get_text(strip=True)` value is the literal string `"FEW"` or
`"NA"`, not a number.
**Why it happens:** Confirmed live this session
`[VERIFIED: tceq.texas.gov/cgi-bin/compliance/monops/daily_summary.pl?cams=83, fetched this session]`
— the tooltip text for `"FEW"` reads *"Not enough five-minute measurements available to create an
hourly average. There must be 45 minutes of data available each hour in order for a valid hourly
average to be created."*; for `"NA"`: *"This hourly average has not been calculated yet."* Both
are real, well-formed, non-error states — not malformed-response signals.
**How to avoid:** Attempt `float(cell_text)` per hourly cell; on `ValueError`, set that hour's
value to `None`/`NaN` rather than raising or skipping the whole row. Do **not** treat a `"FEW"`/
`"NA"` cell as a reason to raise D-06/D-07's "missing needed field" condition — that condition is
about the **row being entirely absent** from the table (the site doesn't monitor that parameter at
all), not an individual hour's placeholder within a present row.
**Warning signs:** A `ValueError: could not convert string to float: 'FEW'` crash during parsing —
this means the placeholder-detection step was skipped, not that the response is malformed.

### Pitfall 5: Requesting today's (partial) report returns fewer than 24 hourly columns

**What goes wrong:** A request for the current calendar day returns only the hours elapsed so far
that day (e.g., 22 columns as of ~9-10pm local time when this session fetched it), not a full 24.
A parser hard-coded to expect exactly 24 `<td>` data cells per row will misalign or crash on a
same-day request.
**Why it happens:** Confirmed live: fetching `cams=83` for "today" (no explicit date params, which
per Pitfall 1 always returns today regardless) rendered a `Morning`/`Afternoon`-split header
totaling 22 hourly columns (`Mid` through `9:00 PM`), while the same site's report for a genuine
past date (`select_date=user&...&time_format=24hr`, July 1 2026) rendered all 24 columns
(`0000`-`2300`) fully populated with numeric values, no `"FEW"`/`"NA"` gaps.
**How to avoid:** Do not assume a fixed column count; extract exactly as many `<td>` values as are
present per row, zipped against the corresponding hour labels found in the header row (which will
also be fewer for the current day). Recommend always requesting `time_format=24hr` (see below) to
get the simpler `0000`-`2300` label format and avoid the `Morning`/`Afternoon` split-header layout
entirely for full-day requests.
**Warning signs:** An `IndexError`/misaligned-hour bug that only manifests when the requested
window includes "today" but not on purely historical windows.

### Pitfall 6: An AI-summarized fetch of a TCEQ page can hallucinate site status

**What goes wrong:** An initial `WebFetch` pass over `monitors.pl?region=11` (Austin) reported
"Camp Mabry KATT C5001/C5002" and "Burnet County Airport KBMQ C5009" as **Active** sites. A
follow-up raw `curl` fetch of the exact same URL shows both are explicitly labeled
`Deactivated: Jul 20, 2020` and `Deactivated: Feb 2, 2022` respectively
`[VERIFIED: tceq.texas.gov/cgi-bin/compliance/monops/monitors.pl?region=11, fetched this session]`.
**Why it happens:** `WebFetch` runs the page through a summarization model before returning
results; that model appears to have dropped or misread the "Deactivated" annotation for at least
two of ~17 sites on a long page.
**How to avoid:** For any claim that gates a load-bearing decision (site selection, in this
phase's case), fetch the raw HTML directly (`curl`) and grep/parse it, rather than trusting an
AI-summarized tool's prose output. This research's CAMS Site Selection table below was built
entirely from raw `curl` output, not the initial `WebFetch` pass.
**Warning signs:** Any "Active"/"Deactivated" claim about a specific CAMS site sourced only from an
AI-summarized fetch, without a raw-HTML cross-check.

### Pitfall 7: A site's row label in `daily_summary.pl` can differ from its label in `monitors.pl`

**What goes wrong:** `monitors.pl`'s parameter list uses the long name "Standard Deviation of
Horizontal Wind Direction"; the same parameter's row in `daily_summary.pl`'s data table is labeled
"Std. Dev. Wind Direction" — a different string.
**Why it happens:** The two CGI scripts render independently and were not confirmed to share a
label-string source. This specific parameter isn't needed by this phase (only Wind Speed, Wind
Direction, Outdoor Temperature, Relative Humidity are targeted, per D-07), but the mismatch shows
`monitors.pl`'s labels cannot be assumed identical to `daily_summary.pl`'s labels for parameters
this phase *does* care about.
**How to avoid:** The four target row labels (`"Wind Speed"`, `"Wind Direction"`, `"Outdoor
Temperature"`, `"Relative Humidity"`) were confirmed identical between the two pages for every CAMS
ID checked this session — no divergence observed for these four specifically. Still, treat
`monitors.pl` as a *discovery* tool (which parameters exist, used for D-01 site selection) and
`daily_summary.pl`'s own rendered `<strong>` text as the sole source of truth for the actual
row-matching logic in `tceq_provider.py` — never hard-code a label string without confirming it
appears verbatim in a `daily_summary.pl` response.
**Warning signs:** N/A for this phase's four target fields (already confirmed matching) — relevant
only if a future phase adds a fifth TCEQ field.

### Pitfall 8: `requirements.txt`'s `bs4` line is missing `==`

**What goes wrong:** The line `bs4 4.14.3` in `requirements.txt` (no `==` between name and
version) is not valid pip-requirements syntax for pinning — `pip install -r requirements.txt`
would either error or (depending on pip version) silently ignore the version constraint and
install whatever the latest `bs4` release is.
**Why it happens:** Likely a typo from whenever this line was added (predates this phase — `bs4`
was already declared before this research pass, per the file's own D-11 provenance comment, though
never previously imported by any provider module).
**How to avoid:** This phase's plan should fix the line to `bs4==4.14.3` while adding the new
`tceq_provider.py` import, both because it's now load-bearing for a shipped module and because
`config.py`'s DS-NF2 "reproducibility" rationale for this file explicitly calls out pinned,
verified versions as the whole point of the file.
**Warning signs:** A `pip freeze` after a fresh `pip install -r requirements.txt` showing a `bs4`
version other than `4.14.3`.

## Code Examples

### Fetching one calendar day's report for a given CAMS site

```python
# Source: live-confirmed request shape, tceq.texas.gov/cgi-bin/compliance/monops/daily_summary.pl,
# fetched this session (see Pitfall 1 for why select_date=user and time_format=24hr both matter).
import requests

TCEQ_BASE = "https://www.tceq.texas.gov/cgi-bin/compliance/monops/daily_summary.pl"

def _fetch_one_day(cams_id: str, year: int, month: int, day: int) -> str:
    params = {
        "cams": cams_id,
        "select_date": "user",       # REQUIRED -- omitting this silently returns "today" (Pitfall 1)
        "user_month": month - 1,     # 0-indexed: January=0 (confirmed via the <select> options)
        "user_day": day,
        "user_year": year,
        "time_format": "24hr",       # avoids AM/PM "Mid"/"Noon" ambiguity and the Morning/Afternoon split header
    }
    r = requests.get(TCEQ_BASE, params=params, timeout=60)
    r.raise_for_status()             # a real network/HTTP failure -- distinct from a malformed *body* (Pitfall 3)
    return r.text
```

### Detecting a malformed or unreachable report (Pitfall 3)

```python
# Source: live-confirmed response shapes for cams=83 (valid) vs cams=999999 (invalid), this session.
from bs4 import BeautifulSoup

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

### Extracting one target field's 24 hourly values with placeholder handling (Pitfall 4)

```python
# Source: live-confirmed row/cell structure, this session.
def _extract_row_values(data_table, label: str) -> list[float | None]:
    for row in data_table.find_all("tr"):
        strong = row.find("strong")
        if strong is None or strong.get_text(strip=True) != label:   # EXACT match -- see Pattern 2
            continue
        cells = row.find_all("td")
        # cells[0] is the row label repeated as a <td>; the trailing 2 cells are the
        # repeated "Parameter Measured" label and the POC value -- only the middle
        # slice is real hourly data (count varies for a same-day partial report, Pitfall 5).
        hourly_cells = cells[1:-2]
        values = []
        for cell in hourly_cells:
            text = cell.get_text(strip=True)
            try:
                values.append(float(text))
            except ValueError:
                values.append(None)   # "FEW" / "NA" placeholder -- not an error (Pitfall 4)
        return values
    return []   # row not present at all -- this site doesn't monitor this parameter (D-04 territory for RH)
```

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 (`requirements.txt`) |
| Config file | `pytest.ini` (repo root) — `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py` |
| Quick run command | `pytest backend/tests/tceq_provider_test.py -x` |
| Full suite command | `pytest` (repo root, runs all of `backend/tests/`) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WX-01 | Happy path: parses a mocked `daily_summary.pl` HTML response into `PIPELINE_SCHEMA`-named columns with correct units | unit | `pytest backend/tests/tceq_provider_test.py::test_fetch_tceq_parses_into_pipeline_columns -x` | ❌ Wave 0 |
| WX-01 | Unit conversion: mph→m/s and degF→degC match `units_def.Q` exactly | unit | `pytest backend/tests/tceq_provider_test.py::test_fetch_tceq_converts_units -x` | ❌ Wave 0 |
| WX-01 | Fixed-offset UTC conversion: an El Paso (MST) row and an Austin (CST) row convert with their respective fixed offsets, unaffected by the fetch's calendar month | unit | `pytest backend/tests/tceq_provider_test.py::test_fetch_tceq_applies_fixed_utc_offset_no_dst -x` | ❌ Wave 0 |
| WX-01 | RH absent at a site → `relative_humidity` null, `humidity_source` null (D-04/D-05) | unit | `pytest backend/tests/tceq_provider_test.py::test_fetch_tceq_leaves_rh_null_when_site_has_no_rh_row -x` | ❌ Wave 0 |
| WX-01 | Missing wind_speed/wind_direction/air_temp row → raises (D-06/D-07) | unit | `pytest backend/tests/tceq_provider_test.py::test_fetch_tceq_raises_when_required_field_row_absent -x` | ❌ Wave 0 |
| WX-01 | Invalid/unreachable CAMS ID (generic form page, no data table) → raises (Pitfall 3) | unit | `pytest backend/tests/tceq_provider_test.py::test_fetch_tceq_raises_on_malformed_response -x` | ❌ Wave 0 |
| WX-01 | `"FEW"`/`"NA"` placeholder cells → null, not a parse crash (Pitfall 4) | unit | `pytest backend/tests/tceq_provider_test.py::test_fetch_tceq_treats_few_and_na_as_null -x` | ❌ Wave 0 |
| WX-01 | Multi-day window → one request per calendar day, concatenated (D-09) | unit | `pytest backend/tests/tceq_provider_test.py::test_fetch_tceq_multi_day_window_issues_one_request_per_day -x` | ❌ Wave 0 |
| WX-01 | Dispatch: `weather_provider.fetch_weather(stids, start, end, provider="tceq")` reaches the new branch and returns a provenance-tagged frame | unit | `pytest backend/tests/weather_provider_test.py::test_dispatch_tceq_provider_routes_to_new_branch -x` | ❌ Wave 0 |
| WX-01 | Live smoke check: one real `daily_summary.pl` fetch for each of the 4 chosen CAMS IDs, confirming the report structure hasn't drifted since this research pass | manual-only (network-dependent, not run in CI) | manual `curl` against each of `cams=38/83/1095/41` | ❌ Wave 0, deliberately manual |

### Sampling Rate

- **Per task commit:** `pytest backend/tests/tceq_provider_test.py -x`
- **Per wave merge:** `pytest` (full suite)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `backend/tests/tceq_provider_test.py` — new file, all of the above unit tests; follow
  `backend/tests/asos_provider_test.py`'s `_FakeResponse` + `monkeypatch.setattr(module.requests,
  "get", ...)` convention (confirmed live this session as the existing project-wide test pattern
  for every provider module, including `weather_provider_test.py`'s own dispatch tests).
- [ ] `backend/tests/weather_provider_test.py` — extend with a `provider="tceq"` dispatch test,
  mirroring the existing `test_dispatch_station_list_routes_to_the_station_path` pattern.
- [ ] No new framework install needed — pytest 9.0.3 is already installed and configured.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | TCEQ's endpoint is public, unauthenticated — no credential to protect (unlike NSRDB's `NREL_API_KEY`). |
| V3 Session Management | No | Stateless GET requests, no session. |
| V4 Access Control | No | No access-control boundary inside this module. |
| V5 Input Validation | Yes | `_range_check` (mirrors `asos_provider._range_check`/`nsrdb_provider._range_check`) validates every converted value against `units_def.PIPELINE_SCHEMA`'s declared `(lo, hi)` range before returning — this is the module's actual injection-adjacent control, since a units regression (e.g. an unconverted mph value flowing through as if it were already m/s) is the realistic "bad input" this module can produce. |
| V6 Cryptography | No | No credential, no encrypted payload — plain HTTP GET to a public TCEQ endpoint (the endpoint itself is served over HTTPS, `https://www.tceq.texas.gov/...`, confirmed this session). |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Silent unit-regression (mph value flowing through unconverted, still numerically "in range" for the wrong unit) | Tampering (of downstream physics results, not an external attacker) | `_range_check` against `units_def.PIPELINE_SCHEMA`'s declared ranges, exactly as ASOS/NSRDB already do — a raw mph wind-speed value up to ~30 could pass an m/s range check `(0, 50)` undetected numerically, but a realistic TCEQ mph reading (5-15 typical, up to ~30-40 in a strong gust) converted to m/s (÷2.237) stays comfortably inside range either way, so this specific column pair is not self-defending — code review / the unit test in Validation Architecture is the actual catch, not the range check alone. |
| HTML injection via a crafted CAMS site name (if ever rendered to a user-facing surface) | Tampering / Spoofing | Not applicable this phase — TCEQ site names are never rendered to any UI; this is a backend-only, internal pipeline module. Flagged only because `bs4`-parsed text is being introduced to the codebase for the first time — future phases that *do* surface a TCEQ site name to a UI should HTML-escape it, since it originates from an external, TCEQ-controlled string. |
| Silent mis-dating from Pitfall 1 (date params ignored without `select_date=user`) | Tampering (of the pipeline's own historical record, not an external attacker) | Explicit `select_date=user` inclusion (Code Examples above) plus the multi-day test (`test_fetch_tceq_multi_day_window_issues_one_request_per_day`) asserting distinct dates across the loop. |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The exact `<td>` slice boundaries (`cells[1:-2]` for hourly data, dropping the trailing repeated-label and POC cells) hold for every one of the four chosen CAMS sites, not just CAMS 83 (the only one whose raw table HTML was fully diffed line-by-line this session). CAMS 38/1095/41 were confirmed to contain the same `<strong>` row labels and same `0000`-`2300` header shape when `time_format=24hr` was used, but their exact `<td>` counts per row were not individually re-verified cell-by-cell the way CAMS 83's was. | Code Examples / Report Structure | Low — the header-row cell count and the data-row cell count are structurally coupled in every site's response (same template), and the planner's Wave 0 tests should assert this per real fetched fixture per site regardless. |
| A2 | `daily_summary.pl` accepts a POST with the same parameter names as the confirmed-working GET request, since the underlying HTML form itself uses `method='post'`. This phase's recommendation is to use GET (which was directly confirmed working), not POST — POST was never tried. | Code Examples | None if GET continues working (it did, every time, this session) — flagged only in case a future rate-limit or proxy behaves differently for GET vs POST; not expected to matter. |
| A3 | The four sites' fixed UTC offsets (CST=-6 for Austin/Corpus Christi/Midland, MST=-7 for El Paso) will remain fixed indefinitely. TCEQ's own explanatory text supports this as a standing policy ("we present data in Local Standard Time"), not a one-off artifact of the September fetch date. | Common Pitfalls / Pattern 3 | Low — this is TCEQ's stated, general policy text, not an inference from a single date's label; still worth a periodic live spot-check if this module is revisited far in the future. |

**If this table is empty:** N/A — see entries above; all are low-risk given the live confirmation
already performed.

## Open Questions (RESOLVED)

*Both questions below were settled during planning; each carries its `RESOLVED:` marker naming the
plan and task where the decision became executable content.*

1. **How should the `_fetch_station(stids, start, end, "tceq")` branch resolve `stids` into a
   `city`/`lat`/`lon` for downstream merge compatibility (if any future caller needs it)?**
   - What we know: D-08 requires the same `fetch_weather(stids, start, end, provider="tceq")`
     signature Synoptic uses; the simplest, most literal reading is that `stids` for TCEQ is a list
     of CAMS IDs (e.g. `["38"]` for an Austin request), directly forwarded to `tceq_provider`, with
     no city-resolution logic inside `_fetch_station` itself — this mirrors the Synoptic branch's
     own simplicity (`dlr_pipeline.fetch_timeseries(stids, start, end)`, one line, no lat/lon
     handling).
   - What's unclear: Whether this phase's returned frame needs a `city` or `lat`/`lon` column at
     all. ROADMAP's 4 success criteria for this phase (fetch, convert+validate, provenance, fail
     loud) do not require one — `merge_observations`/Phase 10's fallback wiring is the phase most
     likely to actually need it.
   - Recommendation: Keep `tceq_provider.fetch_tceq(cams_id, start, end)` returning exactly
     `[datetime_utc, air_temp, wind_speed, wind_direction, relative_humidity]` (no `city`/`lat`/
     `lon`), matching `asos_provider.fetch_asos_1min`'s return shape exactly. If Phase 10's merge
     needs city resolution later, the caller already knows which city it requested (it chose the
     CAMS ID from `config.TCEQ_STATIONS[city]`) and can attach `city` itself with
     `weather_provider.attach_city` the same way `_fetch_grid`'s `open_meteo`/`nsrdb` branches
     already do via their own `lat`/`lon` arguments — no new machinery needed in this phase.
   - **RESOLVED:** Adopted as recommended — no city resolution happens inside `_fetch_station`, and
     no `city`/`lat`/`lon` column is added in this phase. Settled as executable content in **Plan
     09-01 Task 3** (the tracer), which fixes `tceq_provider._RETURN_COLUMNS` to exactly
     `[datetime_utc, air_temp, wind_speed, wind_direction, relative_humidity]` — the same return
     shape as `asos_provider.fetch_asos_1min` — and whose `_fetch_station` `tceq` branch forwards
     the caller's CAMS ID straight through to `fetch_tceq` with no lookup. Plan 09-02 Task 2 then
     parameterises every test over all four `config.TCEQ_STATIONS` values against that same fixed
     column list, so the shape is pinned by test rather than by convention. Attaching `city` stays
     the caller's job via the existing `weather_provider.attach_city`; Phase 10's merge wiring can
     do it without a change here.

2. **Should a request whose window spans a genuinely large multi-day range (e.g. a full historical
   backfill) be rate-limited/throttled against `daily_summary.pl`?**
   - What we know: No documented rate limit was found for this endpoint (unlike NSRDB's documented
     1,000 req/hour); TCEQ CAMS is a free, public, unauthenticated CGI endpoint.
   - What's unclear: Whether TCEQ's server has an undocumented request-rate defense (e.g. returning
     a CAPTCHA, a 429, or silently throttling) for a rapid per-day loop over a long historical
     range.
   - Recommendation: This phase's scope (WX-01, "current" readings per D-08) does not require a
     long historical backfill — Open-Meteo already owns that job (WX-04). No retry/backoff logic
     is recommended for this phase; if a future phase does need TCEQ historical backfill at scale,
     it should re-verify rate-limit behavior with a real multi-week request first.
   - **RESOLVED:** Adopted as recommended, plus one addition. No retry, backoff or throttle logic
     ships in this phase. Instead the question is closed structurally by a hard cap: **Plan 09-02
     Task 1** defines `tceq_provider.TCEQ_MAX_DAYS_PER_FETCH = 31` and raises *before any request is
     issued* when a requested window spans more days than that, with the raise message pointing bulk
     historical callers at Open-Meteo (WX-04), which already owns that job. So the undocumented
     rate-limit behaviour is never exercised rather than being guessed at — the long multi-week loop
     that would provoke it cannot be built from this entry point. Recorded as threat **T-09-11**
     (Denial of Service, `daily_summary.pl`, disposition `mitigate`) in Plan 09-02's threat model,
     and verified by the `window decomposition OK` assertion in that task's `<verify>`. Re-verifying
     real rate-limit behaviour remains a prerequisite for any future phase that wants to lift the cap.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `bs4` (Beautiful Soup 4) | HTML table parsing | ✓ | 4.14.3 `[VERIFIED: .venv, this session]` | — |
| `lxml` | Optional faster `bs4` parser backend | ✓ (but not declared in `requirements.txt`) | 5.4.0 `[VERIFIED: .venv, this session]` | Use stdlib `"html.parser"` backend instead — zero new dependency, adequate for this page size. |
| `requests` | HTTP GET to `daily_summary.pl` | ✓ | already a transitive project dependency | — |
| Network access to `www.tceq.texas.gov` | Every live fetch this phase performs | ✓ (confirmed live this session — all 8+ fetches succeeded) | — | None — this is the primary data source; no fallback exists inside this phase's scope (D-06 raises rather than falling back). |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** `lxml` (declared-but-optional; use `"html.parser"`).

## CAMS Site Selection (D-01 Live Research Findings)

All rows below were confirmed this session via raw `curl` against
`tceq.texas.gov/cgi-bin/compliance/monops/monitors.pl?region=<n>` (site discovery) and
`.../daily_summary.pl?cams=<id>` (report-structure + live-value confirmation for the chosen site).
An initial `WebFetch` pass was also run but is **not** cited as evidence below after it was caught
hallucinating two Austin sites' active/deactivated status (Pitfall 6) — every claim below is
`[VERIFIED: raw curl, tceq.texas.gov, this session]`.

| City | Chosen CAMS ID | Site Name | Wind Speed | Wind Direction (true, not resultant-only) | Outdoor Temp | Relative Humidity | Notes |
|------|----------------|-----------|:----------:|:----------:|:----:|:--:|-------|
| Austin | **38** | Audubon | Active | Active (since 2022-04-07) | Active | Not monitored | Matches `data_provider.md`'s prior reference site; also has Solar Radiation (not a selection factor, bonus). Two other Austin sites (C3, C1068) also have true WD but no RH either — C38 chosen for continuity with the already-published `data_provider.md` reference. |
| Corpus Christi | **83** | Corpus Christi Palm | Active | Active | Active | **Active, live-populated** (89.5-94.9% observed 2026-09-13) | Already locked per `data_provider.md`/D-01. RH is actually present and populated — better than `data_provider.md`'s original (RH-agnostic) characterization of this site. |
| Midland | **1095** | Midland Avalon Drive | Active | Active (since 2026-05-01) | Active | Not monitored | Best of 7 region-7 (Odessa-Midland) candidates checked live — the only currently-active site with a true (non-resultant) Wind Direction parameter, and the only one literally named "Midland." |
| El Paso | **41** | Chamizal | Active | Active (since 2023-02-16) | Active | **Active** (since 1997) | Most complete of all four cities — WS+WD+Temp+RH+Solar Radiation all currently active. Region confirmed as region 6. |

**Region numbers confirmed:** Austin = region 11, Midland/Odessa = region 7, El Paso = region 6 —
all three matched the numbers `09-CONTEXT.md` already suspected; Corpus Christi's region was not
re-derived (its CAMS ID was already locked by `data_provider.md`).

**Report structure (confirmed identical across all 4 chosen sites' `daily_summary.pl` responses):**
- One `<table border='1'>` per report; one `<tr>` per monitored parameter.
- Each row's label cell: `<a href='daily_info.pl?parameter:<EPA code>' ...><strong><label
  text></strong></a>` — EPA parameter codes confirmed: Wind Speed=61101, Wind Direction=61102,
  Resultant Wind Speed=61103, Resultant Wind Direction=61104, Maximum Wind Gust=61105, Std. Dev.
  Wind Direction=61106, Outdoor Temperature=62101, Relative Humidity=62201.
- **Units, confirmed via each parameter's own tooltip text:** Wind Speed / Resultant Wind Speed /
  Maximum Wind Gust → **miles per hour**; Wind Direction / Resultant Wind Direction → **degrees
  compass**; Outdoor Temperature → **degrees Fahrenheit**; Relative Humidity → **percent**.
- With `time_format=24hr`: header row is `0000`, `0100`, ..., `2300` (24 columns, hour-beginning
  convention — the "0000" column is the average for [00:00, 01:00) local standard time, confirmed
  via the page's own explanatory text: *"values shown for the noon hour are based on measurements
  taken from noon to 1:00 p.m."*).
- A row not present in the table at all = that site does not monitor that parameter (this is how
  Austin/Midland's missing Relative Humidity row should be detected — absence of a `<strong>Relative
  Humidity</strong>` row anywhere in the table, not a present-but-null row).
- Non-numeric cell text values observed: `"FEW"` (insufficient 5-minute samples that hour) and
  `"NA"` (average not yet calculated — only ever seen on the current, still-in-progress day).

## Sources

### Primary (HIGH confidence — raw `curl` fetch of the live, authoritative TCEQ endpoint this session)

- `https://www.tceq.texas.gov/cgi-bin/compliance/monops/daily_summary.pl?cams=83` — full report
  HTML, confirmed report table structure, EPA parameter codes, units, RH presence, "FEW"/"NA"
  placeholder behavior, "Local Standard Time"/CST explanatory text.
- `https://www.tceq.texas.gov/cgi-bin/compliance/monops/daily_summary.pl?cams=38` — Austin
  Audubon, confirmed row labels (no RH row), "CST" label.
- `https://www.tceq.texas.gov/cgi-bin/compliance/monops/daily_summary.pl?cams=1095` — Midland
  Avalon Drive, confirmed row labels (no RH row), "CST" label.
- `https://www.tceq.texas.gov/cgi-bin/compliance/monops/daily_summary.pl?cams=41` — El Paso
  Chamizal, confirmed RH row present, "MST" label (Mountain time, not Central).
- `https://www.tceq.texas.gov/cgi-bin/compliance/monops/daily_summary.pl?cams=83&select_date=user&user_month=6&user_day=1&user_year=2026&time_format=24hr` —
  confirmed the `select_date=user` requirement (Pitfall 1), confirmed full 24-hour column layout
  for a genuine past date, confirmed `time_format=24hr`'s simpler header format.
- `https://www.tceq.texas.gov/cgi-bin/compliance/monops/daily_summary.pl?cams=999999&select_date=user&...` —
  confirmed the malformed/invalid-CAMS-ID response shape (HTTP 200, no site `<h1>`, zero
  `<table>` elements) — Pitfall 3.
- `https://www.tceq.texas.gov/cgi-bin/compliance/monops/monitors.pl?region=11` (Austin),
  `?region=7` (Midland/Odessa), `?region=6` (El Paso) — raw HTML, per-site parameter active/
  deactivated status used for CAMS Site Selection.
- `/Users/aphan/Documents/Senior_Design/backend/units_def.py:46` (`"mph": "velocity"`),
  `:41` (`"degF": "temperature"`), `:329-335` (`KNOWN_PROVIDER_NAMES` — `"tceq"` already present),
  `:347-451` (`PIPELINE_SCHEMA` ranges) — read directly this session.
- `/Users/aphan/Documents/Senior_Design/backend/weather_provider.py`,
  `/Users/aphan/Documents/Senior_Design/backend/asos_provider.py`,
  `/Users/aphan/Documents/Senior_Design/backend/nsrdb_provider.py`,
  `/Users/aphan/Documents/Senior_Design/backend/config.py` — read directly this session for
  existing integration/pattern conventions.
- `.venv/bin/python3 -c "import bs4; print(bs4.__version__)"` → `4.14.3`;
  `.venv/bin/python3 -c "import lxml; print(lxml.__version__)"` → `5.4.0` — run this session.

### Secondary (MEDIUM confidence)

- `/Users/aphan/Documents/Senior_Design/docs/data-science/decisions/data_provider.md` §"TCEQ CAMS"
  — prior research pass's original TCEQ assessment; several specific claims (Corpus Christi RH
  absence, Austin site-11-count) were superseded or refined by this session's live re-check, noted
  inline above.
- `/Users/aphan/Documents/Senior_Design/requirements.txt` — existing dependency declarations
  (`bs4`, `pandas`), read directly.

### Tertiary (LOW confidence — superseded, not relied upon for any claim above)

- Initial `WebFetch` summarization pass over `monitors.pl?region=11`/`region=7`/`region=6` —
  caught hallucinating two Austin sites' deactivation status (Pitfall 6); used only to orient the
  raw-`curl` follow-up, not cited as evidence for any table/claim in this document.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — `bs4`/`lxml`/`pandas`/`requests` versions confirmed directly in the
  project's own `.venv`, not from a registry guess.
- CAMS site selection / report structure / units / timezone: HIGH — every claim is a live `curl`
  fetch against the production endpoint this session, cross-checked against an AI-summarized pass
  that was caught being wrong on two sites (giving concrete grounds for the HIGH tier rather than
  just "it looked plausible").
- Architecture (dispatch integration shape): MEDIUM — the recommended `_fetch_station` branch shape
  follows the existing Synoptic/ASOS/NSRDB pattern closely, but the exact `stids`→CAMS-ID handoff
  (Open Question 1) is a genuine design choice left for the planner, not fully pinned by this
  research.
- Pitfalls: HIGH — all 8 are either live-reproduced this session (1, 3, 4, 5, 6) or directly quoted
  from TCEQ's own page text (2) or the project's own `requirements.txt` (8), none are inferred.

**Research date:** 2026-09-13
**Valid until:** 2026-10-13 (30 days — TCEQ's report page is a stable government CGI script that
has not materially changed in years per its own legacy markup, but the specific per-site
active/deactivated parameter status (CAMS Site Selection table) is the kind of fact that can drift
as TCEQ activates/retires instruments; re-verify the four chosen CAMS IDs' parameter lists live if
this research is consumed more than a month after the date above).
