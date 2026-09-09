# Data Provider Decision Log

**Status:** Open — vetting in progress. Answers `PRD.md` §7.1 (weather data provider — unresolved).

**Purpose:** One section per candidate data provider, vetted individually against this project's actual requirements before a decision is made. Not a final recommendation document — a working log of what was checked and why each provider was accepted, rejected, or kept as a supplement.

**Requirements each candidate is vetted against** (see conversation history / `PRD.md` §5–7, §10 for full derivation):

1. **Temporal density** — ideally 5-minute cadence to match the current WTM/Synoptic pipeline; hourly is acceptable for historical-training use but not for live operation.
2. **Spatial coverage of the actual four target cities** — Austin, Corpus Christi, Midland, El Paso, per `Project Definition.md`'s I/O Specification Table (the project's real documented scope — see `PRD.md` §10, which flags that the code's West-Texas-only framing and mismatched city lists in `config.py`/`station_explorer.py` never actually matched this spec). A provider does **not** need to cover all four to be viable — a provider covering only one or two regions can still be used **as long as its data can be standardized/scrubbed down to whatever fields and resolution are common across every provider actually selected**, so the combined pipeline stays consistent city-to-city. Note per-provider which of the four cities it actually covers, and at what resolution.
3. **Variable completeness** — air temp, wind speed/direction, solar irradiance (GHI), relative humidity. Solar specifically, since it's a required IEEE 738 input and the current pipeline fakes it with a hardcoded constant for stations that lack it.
4. **Cost / access model** — free or free-for-research strongly preferred; note exact quota/rate-limit if not unlimited.
5. **Historical depth/volume** — relevant for C9 (forecasting) and C10 (anomaly detection) training data, not just live operation.
6. **Integration effort** — auth model, request format, whether it fits behind the existing `backend/weather_provider.py` adapter interface without a redesign.

## Candidates to Vet

- [x] **TCEQ CAMS** (state air-quality network; added after initial research surfaced it as the strongest per-city candidate for real-station wind/temp coverage)
- [x] **NREL NSRDB** (PSM v4 GOES CONUS)
- [x] **Synoptic — Open Access Program** (free, .edu-gated upgrade of the currently-in-use Synoptic/WTM path)
- [x] **Synoptic — current/existing token** (baseline — what the pipeline uses today, for comparison)
- [x] **ASOS 1-minute (Iowa Environmental Mesonet)** (added after research — best temporal density for wind/temp)
- [x] **Open-Meteo (Historical Weather API)**
- [x] **USCRN** (added after research — flagged as a likely-obvious-looking candidate that is actually disqualified)
- [x] **NOAA RTMA / URMA (gridded analysis)**
- [x] **NOAA MADIS**
- [x] **Meteostat**
- [x] **NWS / api.weather.gov**
- [x] **TexMesonet direct (non-Synoptic-API paths, e.g. Custom Downloads)** — folded into the Synoptic entry below (routes through the same API)

## Per-Provider Template

Each vetted candidate gets a section in this shape:

```
### <Provider Name>

**Verdict:** Viable / Not viable / Viable as supplement only — <one line why>

**Cost & access:** 
**Temporal resolution:** 
**Spatial coverage (Austin / Corpus Christi / Midland / El Paso):** 
**Variable completeness (esp. solar):** 
**Historical depth:** 
**Integration effort:** 
**Evidence checked:** <what was actually verified — live API call, docs read, account created, etc. Distinguish "confirmed live" from "per documentation, unverified">

**Decision rationale:**
```

---

## Vetted Providers

**Headline finding, before the per-provider detail:** no single candidate is both observation-grade *and* variable-complete. IEEE 738 needs air temp, wind speed, wind direction, solar irradiance, and RH — and wind is the dominant cooling term in the heat-balance equation, so it's the one the ampacity result is most sensitive to. Every candidate researched splits into one of two camps:

- **Real-station networks** (TCEQ CAMS, Synoptic/WTM, ASOS) — trustworthy, sensor-measured 10m wind, but solar is either absent or present at only a minority of sites.
- **Satellite/reanalysis products** (NSRDB, Open-Meteo, RTMA) — purpose-built, complete solar coverage, but wind is modeled, at non-standard height, or coarse-resolution.

This means the likely outcome of this vetting pass is **per-variable sourcing** (a real-station provider for wind/temp + a satellite provider for solar) rather than one winning provider. See "Recommended Composition" at the end of this section.

---

### TCEQ CAMS (Continuous Ambient Monitoring Stations)

**Verdict:** Viable as the primary **wind/temp/RH** source for all four cities — **not viable as a solar source** except at a minority of sites, confirmed site-by-site.

**Cost & access:** Free, no account or API key. Public CGI/HTML endpoints (`tceq.texas.gov/cgi-bin/compliance/monops/daily_summary.pl?cams=<id>`).

**Temporal resolution:** Internally averaged every 5 minutes per TCEQ's own monitoring description, but the publicly exposed `daily_summary.pl` report is **hourly averages**, not raw 5-minute values — confirmed by directly fetching a live report (see Evidence below). Sub-hourly access, if it exists, would require a different TCEQ interface (TAMISWeb) not yet checked.

**Spatial coverage (Austin / Corpus Christi / Midland / El Paso):** All four have CAMS sites — confirmed live for Austin (11 sites found, region 11) and Corpus Christi (CAMS 4, CAMS 83); confirmed via search only (not yet live-fetched) for Midland/Odessa (region 7) and El Paso (region 6).

**Variable completeness (esp. solar):** Wind speed, wind direction, resultant wind, max gust, std-dev of wind direction, and outdoor temperature are present at every site checked — a strong, consistent set. **Solar radiation is not universal** — it's a per-site instrument, not a network-wide parameter. Confirmed live: **Corpus Christi CAMS 83 (Palm) has no solar radiation field.** Confirmed live: **Austin's Audubon site (CAMS 38) does report "Solar Radiation."** No solar-equipped site has yet been confirmed for Midland or El Paso — this needs to be checked before relying on TCEQ for solar in those two cities.

**Historical depth:** TCEQ states hourly data is available for all sites "after June 1998" — over 25 years, by far the deepest archive of any candidate checked.

**Integration effort:** No REST/JSON API found — access is HTML report scraping (`daily_summary.pl`, `yearly_summary.pl`) or TAMISWeb's report-generation UI, not yet confirmed to have a machine-readable bulk-export path. This is real integration work: a scraper, not an API client. Higher effort than every other candidate in this list except MADIS.

**Evidence checked:** **Confirmed live** — fetched `daily_summary.pl?cams=83` (Corpus Christi Palm) and `monitors.pl?region=11` (Austin) directly; both returned real, current parameter listings, not just documentation claims. Midland/El Paso site-level solar availability is **per documentation only, unverified** — flagged for follow-up before this provider is finalized for those two cities.

**Decision rationale:** Best real-station candidate for the wind term specifically — better spatial density and longer history than Synoptic/WTM, and it's not gated by an account tier the way Synoptic's default token currently is. But solar is a real gap that needs a per-city, per-site check (not yet done for two of the four cities) before treating this as anything more than a wind/temp source, and the lack of a real API means this is the highest integration-effort option that still made the "viable" list.

---

### NREL NSRDB — PSM v4 (GOES CONUS)

**Verdict:** Viable as the primary **solar** source for all four cities — weak, not-recommended-by-NREL-itself for wind.

**Cost & access:** Free. Requires a free NREL developer API key (registration at `developer.nrel.gov` — a user action, no account was created during this research pass).

**Temporal resolution:** Selectable — 5, 15, 30, or 60-minute intervals (confirmed via NREL docs and the `pvlib.iotools.get_psm3` reader's own `interval` parameter, which only accepts {5, 15, 30, 60}).

**Spatial coverage (Austin / Corpus Christi / Midland / El Paso):** All four — it's a 2 km CONUS satellite grid, not discrete stations, so every point in Texas has a value.

**Variable completeness (esp. solar):** 23 variables per request, confirmed via NREL's own API docs: `air_temperature, dew_point, relative_humidity, wind_speed, wind_direction, surface_pressure, ghi, dni, dhi, clearsky_ghi/dni/dhi`, plus cloud/aerosol fields. This is the most complete single-request variable set of any candidate — genuinely purpose-built for solar, and it happens to include everything else IEEE 738 needs too, on paper.

**Historical depth:** 2018–2025 for this specific product (GOES CONUS PSM v4). Older/coarser NSRDB products go back further at lower resolution (30-min, 4 km) if a longer window is needed.

**Integration effort:** Real REST API (`developer.nrel.gov`), and an existing, maintained Python reader (`pvlib.iotools.get_psm3`) already handles auth, request building, and interval selection — this is the easiest integration of any candidate that isn't already wired into the codebase.

**Rate limits (confirmed via docs):** CSV format — 10,000 requests/day, 1 req/sec, 20 concurrent in-flight.

**Evidence checked:** Attribute list, interval options, and rate limits confirmed via NREL's own developer docs (`developer.nrel.gov/docs/solar/nsrdb/...`) and cross-checked against `pvlib`'s documented `get_psm3` signature. **Not confirmed live** — no API key was obtained, so no actual data pull was performed this pass.

**Decision rationale:** Best solar candidate by a wide margin — complete GHI/DNI/DHI, 5-minute option, all four cities, simple auth, existing Python library support. The wind field is the catch: it's derived from **MERRA-2 reanalysis at 2 meters**, and NREL's own documentation states this wind data "should not be used for wind power calculations" — a direct signal it's not trustworthy for a physics calculation as wind-sensitive as IEEE 738 ampacity. Use for solar; do not use for the wind term.

---

### Synoptic — Open Access Program (+ current token, + TexMesonet folded in)

**Verdict:** Viable as an immediate, zero-code-change fix for the *currently broken* real-time path — same coverage/completeness ceiling as what's already in the codebase.

**Cost & access:** Free with a `.edu` email (confirmed eligible: `atp2323@utexas.edu`). Application-gated, not instant — Synoptic reviews and approves, typically annual renewal required.

**Temporal resolution:** 5-minute, matching the existing `dlr_pipeline.py::DLR_VARS` fetch cadence — no pipeline change needed.

**Spatial coverage:** Network-dependent, same WTM/mesonet stations already targeted by `station_explorer.py`. Confirmed **not** to currently cover Corpus Christi, Austin metro, or El Paso with the same density as West Texas — this is the same West-Texas-skewed footprint flagged in `PRD.md` §10, unless a broader Synoptic network (not just WTM) is queried, which hasn't been checked this pass.

**Variable completeness (esp. solar):** Same as today's live-verified finding in `specs/C4-weather-ingestion.md`: solar is commonly missing on airport/METAR-style stations (confirmed for `KAUS`), which is why the pipeline currently substitutes a hardcoded `1000` W/m² constant. Open Access doesn't change per-station instrumentation — it only changes account-tier access.

**Historical depth:** Capped at 1 year of history under the Open Access tier (vs. presumably more on a paid tier — not checked).

**Integration effort:** None — `backend/weather_provider.py`'s existing `fetch_weather(provider="synoptic")` path works unchanged; only the token/account changes.

**TexMesonet direct access:** Investigated as a possible way around Synoptic's account tiering — confirmed via TexMesonet's own FAQ that it **routes through the Synoptic/MesoWest API** for its programmatic access; its non-API path (Custom Downloads) is a size-capped CSV export tool, not suited to bulk/automated pulls. Not a materially different option from Synoptic itself — folded in here rather than given a separate verdict.

**Evidence checked:** Open Access eligibility terms and rate/history caps confirmed via Synoptic's own program page (`synopticdata.com/open-access-program/`) and API limits page. TexMesonet's Synoptic-passthrough confirmed via its own FAQ page. **Not confirmed live** — no application was submitted, since that's a real account action requiring the team's decision, not something to do unilaterally during vetting.

**Decision rationale:** This directly resolves the account-tier failure documented in `specs/C4-weather-ingestion.md` (the default station list returning zero data) at zero engineering cost, using credentials the user already qualifies for. Worth doing regardless of whatever else gets chosen. But it doesn't solve the solar gap or the geographic mismatch with the real four-city spec — it's a fix for the existing West-Texas path, not a broadening of it.

---

### ASOS 1-minute data (Iowa Environmental Mesonet)

**Verdict:** Viable as a **wind/temp supplement** — no solar, so not usable alone.

**Cost & access:** Free, no API key, no registration. Public CGI endpoint (`mesonet.agron.iastate.edu/cgi-bin/request/asos.py` / `.../request/asos/1min.phtml`).

**Temporal resolution:** **1-minute** — the densest of any candidate checked, real-station observations (not modeled).

**Spatial coverage (Austin / Corpus Christi / Midland / El Paso):** All four have a major airport ASOS station — Austin-Bergstrom (KAUS), Corpus Christi Intl (KCRP), Midland Intl (KMAF), El Paso Intl (KELP). Not live-confirmed per-station this pass, but these are all major-hub airports near-certain to be in the ASOS network per IEM's own network coverage description.

**Variable completeness (esp. solar):** **Confirmed live, no solar radiation field** — the 1-minute dataset's variable list is air temp, dew point, wind speed (knots), wind direction, gust, pressure, visibility, precipitation. No radiative measurement at all.

**Historical depth:** Back to 2000 for US ASOS sites, "up until" the present per IEM's own archive description — over 25 years, on par with TCEQ.

**Integration effort:** Simple CGI request/response, no auth. Units need conversion (knots → m/s, °F → °C) to match `PIPELINE_SCHEMA`.

**Evidence checked:** **Confirmed live** — fetched the IEM 1-minute request page directly and confirmed the variable list and no-solar-field finding, not just inferred from a search snippet.

**Decision rationale:** The best wind/temp temporal density of any candidate — genuinely useful for C9/C10 training features where sub-5-minute granularity matters — but purely a supplement, since it has zero solar coverage.

---

### Open-Meteo (Historical Weather / Forecast API)

**Verdict:** Viable as a **secondary solar + wind source** and the easiest bulk-historical backfill option — model output, not raw observations.

**Cost & access:** Free, **no API key**, no registration. ~10,000 requests/day for non-commercial use.

**Temporal resolution:** 15-minute (`minutely_15` parameter) for North America, backed by NOAA's HRRR model.

**Spatial coverage (Austin / Corpus Christi / Midland / El Paso):** All four — global grid, any lat/lon works.

**Variable completeness (esp. solar):** **Confirmed live** — queried Austin's coordinates (30.27, -97.74) directly against the production API and got real, non-null `minutely_15` values for temperature, wind speed, wind direction, shortwave radiation, and relative humidity simultaneously, in one request. This is the only candidate confirmed this pass to return the **full variable set from a single live call**.

**Historical depth:** Archive API covers 1940–present (hourly); the Historical Forecast API (HRRR-based, matching the live-forecast format) covers 2021–present. Far and away the deepest *and* most complete-per-request history of any candidate.

**Integration effort:** Trivial — plain HTTP GET, JSON response, no auth headers required beyond a reasonable User-Agent.

**Evidence checked:** **Confirmed live** via a direct API call this pass (see above) — the strongest evidence tier of any candidate in this document.

**Decision rationale:** Not real sensor data — it's model/reanalysis output, which is a real accuracy caveat worth stating explicitly in the research paper if used, especially since it competes with TCEQ/ASOS's real-station wind. But as a bulk historical-training-data source for C9/C10 (ROADMAP Finding 5's "start accumulating now" problem), this is the strongest option: zero setup, all four cities, all five needed variables, confirmed live, decades of depth.

---

### USCRN (U.S. Climate Reference Network)

**Verdict:** **Not viable** — disqualifying gap found, worth documenting explicitly since it looks viable from a surface read.

**Cost & access:** Free, no key, NOAA public data.

**Temporal resolution:** 5-minute — looks attractive on paper.

**Spatial coverage:** Sparse by design — only 137 stations nationwide (2023 count); Texas coverage not checked in detail since the disqualifier below makes it moot.

**Variable completeness (esp. solar):** Has solar radiation. **Does not measure wind direction at all** — confirmed via NOAA's own USCRN measurements page: "the network only captures wind speed data," no direction. Wind speed itself is measured at **1.5 meters**, not the standard 10m height every other candidate and this project's own `perpendicular_wind()` function assumes.

**Historical depth:** Since 2006.

**Integration effort:** N/A — disqualified on data completeness before integration effort matters.

**Evidence checked:** **Confirmed** via direct fetch of NOAA's own USCRN measurements documentation page — this is a documented network limitation, not an access/tier problem.

**Decision rationale:** Without wind direction, `thermal_model.py::perpendicular_wind()` cannot be computed — a hard blocker, not a degraded-quality tradeoff. And the 1.5m wind height would need a wind-profile extrapolation to 10m even if direction existed, introducing another unvalidated assumption. Documented explicitly because it's the kind of "free, 5-minute, has solar" candidate that looks like an obvious win until the wind-direction gap is checked — worth ruling out on the record so it isn't re-proposed later without this context.

---

### NOAA RTMA / URMA, NOAA MADIS, Meteostat, NWS/api.weather.gov — brief entries

Lower priority; documented briefly since none surfaced a compelling reason to invest further research time this pass.

- **NOAA RTMA/URMA** — Viable as supplement only. Hourly, 2.5 km CONUS grid, all four cities, temp/wind/dewpoint/pressure — but **no solar field**, and access is via AWS S3/GRIB or Google Earth Engine, not a simple REST call. Higher integration cost than Open-Meteo for a strictly worse (no-solar, hourly-only) variable set — dominated by Open-Meteo for this project's purposes.
- **NOAA MADIS** — Not pursued further. Same underlying WTM/mesonet station data Synoptic already resells, but application-gated with an uncertain approval timeline. Only worth revisiting if Synoptic's Open Access application is denied.
- **Meteostat** — Viable as supplement only, low priority. Hourly, 30-day-per-request cap, no solar field confirmed, and station density in West Texas specifically was already flagged (prior research pass) as weak. Dominated by ASOS 1-minute for the same underlying airport stations, at coarser resolution.
- **NWS / api.weather.gov** — Viable as supplement only, low priority. Free, no key, but hourly METAR-based and no solar — same airport-station coverage as ASOS/Meteostat with less temporal density than ASOS's 1-minute data. No reason to prefer this over ASOS 1-minute for the same stations.

---

## Recommended Composition (synthesis, not a final decision)

Based on the vetting above, the strongest path is **per-variable sourcing**, not a single winning provider:

- **Wind (speed + direction) and temperature:** TCEQ CAMS as primary (best spatial density + longest history of any real-station network for these four cities), with ASOS 1-minute as a higher-temporal-density supplement where sub-hourly wind matters (e.g. C9 feature engineering).
- **Solar irradiance:** NSRDB PSM v4 as primary (purpose-built, complete, 5-minute option) — this is also the piece that would make the System Design Report's existing NOAA+NSRDB claim (`PRD.md` §10) actually true, if the team wants to close that discrepancy.
- **Bulk historical backfill for C9/C10 training volume:** Open-Meteo, given it's the only candidate confirmed live to return the complete variable set from a single, zero-auth request — the fastest way to start accumulating the historical corpus ROADMAP Finding 5 flags as currently missing, without waiting on NSRDB API-key provisioning or a TCEQ scraper being built.
- **Immediate fix, independent of the above:** apply for Synoptic Open Access now — it's free, uses credentials already available, and resolves the account-tier failure blocking the pipeline's default config today, regardless of what else is decided.

**A real design consequence this surfaced:** `backend/weather_provider.py::fetch_weather(stids, start, end, provider)` is station-ID-based. NSRDB and Open-Meteo are lat/lon-based. Combining a station-based primary (TCEQ/ASOS) with a grid-based supplement (NSRDB/Open-Meteo) needs either a station→lat/lon mapping layer or a signature change to `fetch_weather` — this should be designed deliberately now rather than discovered mid-way through C8.

**Standardization implication, per the team's own stated approach:** whatever combination is chosen, every provider's output must be scrubbed down to the intersection of fields common across the selected set — `PIPELINE_SCHEMA`'s five weather columns (`air_temp`, `wind_speed`, `wind_direction`, `solar_radiation`, `relative_humidity`) — with the source provider tracked per row (not just per dataset), since accuracy/measurement-height caveats differ by provider (e.g. NSRDB's 2m reanalysis wind vs. TCEQ's real 10m sensor) and that provenance will matter if the research paper needs to explain result quality.

**Explicitly not decided here:** which combination to actually adopt, whether to update `PRD.md` §7.1's status, and any provider integration code. This section is a synthesis of the research for the team to review, not a final call.

## References

- `PRD.md` §7.1 — Open Decisions: Weather data provider
- `ROADMAP.md` Finding 3 — the weather-provider decision must not gate C8
- `specs/C4-weather-ingestion.md` — current implementation and live-verification findings (account-tier failure, missing solar on working stations)
