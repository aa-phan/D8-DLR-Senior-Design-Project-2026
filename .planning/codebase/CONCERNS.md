# Codebase Concerns

**Analysis Date:** 2026-09-02

## Tech Debt

**DLRSafetyMonitor uses outdated ampacity formula:**
- Issue: `backend/DLRSafetyMonitor.py::_compute_ampacity` (line 62-64) uses a simplified formula `900 + wind*30 - (temp-20)*4 - solar*0.05` that does not match the IEEE 738 standard implementation
- Files: `backend/DLRSafetyMonitor.py` (lines 62-64), `backend/thermal_model.py` (authoritative implementation)
- Impact: Safety monitor's plausibility gate (G4) checks ratings against a different, less-accurate reference than the actual thermal model. This means a reading could pass the safety check but still overstate line capacity. Undermines the fail-safe-by-default ethical commitment.
- Fix approach: Replace `_compute_ampacity()` to call `thermal_model.ieee738_ampacity()` instead of using placeholder formula (C7 Phase 3 work)

**Debug print statements instead of logging:**
- Issue: `backend/dlr_pipeline.py` (lines 141-146) uses print statements for API response debugging instead of logging
- Files: `backend/dlr_pipeline.py` (lines 141-146)
- Impact: Debug output pollutes stdout; not captured by logging framework; hard to control verbosity
- Fix approach: Replace `print()` calls with `log.debug()` calls to use the existing logging infrastructure

**Validation is non-strict with silent failures:**
- Issue: `backend/dlr_pipeline.py::validate_pipeline_output` and `backend/units_def.py::validate_pipeline_row` (strict=False) detect data contract violations but only log warnings — never filter, drop, or reject rows
- Files: `backend/dlr_pipeline.py` (lines 251-291), `backend/units_def.py` (lines 378-426)
- Impact: Bad data can silently flow through pipeline into CSV exports and visualizations. Non-strict mode was intentional per spec (to not block multi-station runs), but exported data may contain values outside valid ranges
- Fix approach: Add a threshold — if violation rate exceeds N%, escalate from warning to error and halt pipeline; below N%, log and continue (gives users control)

**Duplicate range bounds across modules:**
- Issue: `WIND_BOUNDS`, `TEMP_BOUNDS`, `SOLAR_BOUNDS` in `backend/DLRSafetyMonitor.py` (lines 7-9) are a second independent copy of ranges already defined in `backend/units_def.py::PIPELINE_SCHEMA` (lines 324-374)
- Files: `backend/DLRSafetyMonitor.py` (lines 7-9), `backend/units_def.py` (lines 324-374)
- Impact: Two sources of truth for valid data ranges. Changes to one aren't reflected in the other — risk of inconsistent validation. Example: if solar range gets updated in PIPELINE_SCHEMA, safety monitor still uses the old bounds.
- Fix approach: Have `DLRSafetyMonitor` read bounds from `units_def.PIPELINE_SCHEMA` at initialization time, or move bounds to `config.py` as a single source

**Undocumented fallback behavior distinction:**
- Issue: `backend/DLRSafetyMonitor.py::_fallback` (lines 66-70): gates G1/G2 fall back to `last_good_rating` (most recent *dynamic* value), while G3/G4 fall back to `static_rating`. This distinction is not documented anywhere.
- Files: `backend/DLRSafetyMonitor.py` (lines 22-31, fallback calls)
- Impact: Unclear whether different fallback targets for sensor/link loss vs. range/plausibility failures is intentional design or an accident. Code review or refactoring could silently "fix" this difference and break intended behavior.
- Fix approach: Document the design decision in `backend/DLRSafetyMonitor.py` module docstring; confirm it matches the spec intent in `backend/specs/C7-safety-monitor.md`

## Known Bugs

**Test contradiction in SafetyMonitor_TestSuite:**
- Symptoms: Test `test_gate_2_fails_when_link_status_not_ok` (line 57-66) asserts both `result["status"] == "ok"` AND `result["fallback"] is True`, which cannot both be true
- Files: `backend/tests/SafetyMonitor_TestSuite.py` (lines 57-66)
- Trigger: Run `pytest backend/tests/SafetyMonitor_TestSuite.py` — test fails because `DLRSafetyMonitor._fallback()` unconditionally sets `status` to `"fallback"`, never `"ok"`
- Workaround: None — test must be fixed. Needs decision on intended semantics: should `status` field reflect gate-specific outcome (requiring richer result shape) or is this a copy-paste error from a passing test?
- Documented in `backend/specs/C7-safety-monitor.md` as unresolved and explicitly NOT fixed pending semantic decision

**Erroneous π factor (FIXED):**
- Issue: `backend/thermal_model.py` had an extra `* np.pi` factor in forced-convection terms (lines 152-156, now fixed)
- Files: `backend/thermal_model.py` (lines 152-156 — the fix)
- Impact: Was causing ~69% overestimate of line ampacity for reference inputs (computed 1728 A instead of published 1025 A). This violated the project's ethical fail-safe requirement — line was silently overstated as able to carry more current than physically safe.
- Status: FIXED in current code; regression test validates against IEEE Std 738-2023 worked example within 0.95% tolerance (`backend/tests/thermal_model_test.py`)

## Security Considerations

**API token management:**
- Risk: `SYNOPTIC_TOKEN` environment variable used for weather data ingestion; if exposed, attacker could exhaust API quotas or access geolocation data
- Files: `backend/dlr_pipeline.py` (line 59-65, `_token()` function), `.env` (listed in `.gitignore`)
- Current mitigation: Token loaded from environment variable, not hardcoded; `.env` file is gitignored; error raised if token missing
- Recommendations: 
  - Use a secrets manager (e.g., AWS Secrets Manager, HashiCorp Vault) for production deployments
  - Implement token rotation policy
  - Add logging for failed auth attempts without exposing the token
  - Rate-limit retries on auth failure

**ERCOT data handling:**
- Risk: Load data from ERCOT is real operational grid information; could be misused if intercepted
- Files: `backend/ercot_data_retriever.py`, `backend/ercot_dlr_merger.py`
- Current mitigation: Downloaded over HTTPS via gridstatus library; saved locally to CSV
- Recommendations: Document data retention policy; consider encryption at rest if deployment includes sensitive systems

## Performance Bottlenecks

**fetch_timeseries API calls scale linearly with station count:**
- Problem: `backend/dlr_pipeline.py::fetch_timeseries` (lines 107-166) makes a single API request for all stations, but API response parsing iterates row-by-row with no batching
- Files: `backend/dlr_pipeline.py` (lines 107-166)
- Cause: Synoptic API returns all stations in one request; pandas DataFrame construction from row-level loops; no asynchronous I/O
- Improvement path: 
  - Profile API response time vs. DataFrame construction time to identify bottleneck
  - If API: implement request batching/pagination if Synoptic API supports it
  - If DataFrame: pre-allocate arrays and use vectorized construction
  - Consider caching API responses for repeat analyses of same time window

**Missing data profiling on empty station responses:**
- Problem: `backend/dlr_pipeline.py::profile_missing_data` (lines 294-318) prints diagnostic info but doesn't fail fast on completely empty stations
- Files: `backend/dlr_pipeline.py` (lines 294-318)
- Cause: Logs warnings but continues pipeline execution, which then produces empty output CSVs
- Improvement path: Add early-exit logic if all stations are dead (100% missing data across all variables); fail with descriptive error rather than silent empty output

**No caching of weather or ERCOT data:**
- Problem: Every pipeline run re-downloads the same historical data from Synoptic and ERCOT even if the time window hasn't changed
- Files: `backend/dlr_pipeline.py`, `backend/ercot_data_retriever.py`
- Cause: No local cache or memoization; API calls are always fresh
- Improvement path: Implement a cache layer (file-based or in-process) with TTL; invalidate on window/station changes

## Fragile Areas

**Conductor configuration is not location-specific:**
- Files: `backend/config.py` (lines 65-73), `backend/thermal_model.py::ConductorConfig`
- Why fragile: Global `DEFAULT_CONDUCTOR_CONFIG_KWARGS` assumes all lines use 795 kcmil Drake ACSR with 90° azimuth and 300/900 m elevation. Real transmission corridors vary — different conductor types, orientations, elevations. Running pipeline on a different line without updating these constants silently produces wrong results.
- Safe modification: 
  - Add a location/corridor table to `config.py` mapping corridor IDs to conductor properties
  - Pass conductor config per-station through pipeline rather than using global defaults
  - Add validation to reject runs without explicit conductor specification
- Test coverage gaps: No test verifies behavior when conductor properties differ from defaults

**Solar altitude is a run-level constant, not computed per observation:**
- Files: `backend/dlr_pipeline.py` (line 229), `backend/thermal_model.py::ieee738_ampacity` (lines 171-172)
- Why fragile: A full-day analysis (sunrise to sunset) uses a single `solar_alt_deg` value (e.g., 72° for midday). Morning and evening observations with actual lower solar altitude are computed with higher incidence angle than reality — overstating solar gain. 
- Safe modification: 
  - Compute true solar altitude from timestamp + location using astropy or equivalent
  - Pass as a series aligned with each observation, not a scalar
  - Document the accuracy trade-off in function docstring
- Test coverage gaps: No test validates behavior across different times of day

**No per-location static rating lookup in pipeline:**
- Files: `backend/config.py::STATIC_RATINGS` (lines 42-51), `backend/dlr_pipeline.py::run_pipeline` (line 187)
- Why fragile: `run_pipeline` takes a single `static_rating` parameter; doesn't look up per-station values from `STATIC_RATINGS` table. Caller must manually look up the right value and pass it. If they pass the wrong value or forget to pass anything, pipeline silently uses default (900 A).
- Safe modification: 
  - Add an optional `location_id` parameter to `run_pipeline`
  - Have it automatically look up both conductor config and static rating from tables
  - Make the lookup explicit in log output
- Test coverage gaps: No test validates that per-location static ratings are actually used

## Scaling Limits

**Synoptic API free research tier constraints:**
- Current capacity: Unknown exact limits; documented as "research-tier rate limits and station/network restrictions"
- Limit: Unclear when system hits quota, but documented in PRD as a risk for scaling beyond current West Texas pilot
- Scaling path: 
  - Migrate to NOAA + NSRDB (decision pending per PRD §7.1)
  - Or: migrate to paid Synoptic tier with documented SLA
  - Implement fallback provider (weather_provider.py adapter allows this)

**Single-station per-run limitation in pipeline:**
- Current capacity: Can process multiple stations in one run (via `run_pipeline(stids=[...])`) but exports and plots iterate station-by-station
- Limit: For 100+ stations, this becomes I/O bottleneck
- Scaling path: 
  - Batch file I/O (write all stations to one CSV, index by stid)
  - Use Parquet or HDF5 for larger datasets
  - Add optional database output backend

**No time-series chunking for large date windows:**
- Current capacity: Loads entire window into memory as a single DataFrame
- Limit: 6+ months of 5-minute data for multiple stations could exceed available RAM
- Scaling path: Implement streaming/chunked processing over date windows; process month-by-month and aggregate results

## Dependencies at Risk

**gridstatus for ERCOT data retrieval:**
- Risk: Dependency on third-party ERCOT API wrapper; if gridstatus changes or breaks, ERCOT integration fails
- Impact: C6 (grid load integration) and downstream analysis depends on this
- Migration plan: Add an ERCOT API integration test that mocks gridstatus; implement direct ERCOT API calls as fallback if gridstatus becomes unmaintained

**Synoptic Data API availability:**
- Risk: If Synoptic service goes down, pipeline cannot run; research tier may have downtime SLAs
- Impact: All weather ingestion (C4) and downstream thermal model (C5) blocked
- Migration plan: PRD §7.1 identifies NOAA as an alternative; implementing weather_provider.py adapter allows swapping providers without pipeline changes

## Missing Critical Features

**Corridor spatial discretization not started:**
- Problem: System Design Report describes breaking transmission corridors into multiple geographic points and computing minimum ampacity per corridor. No such spatial pipeline exists.
- Blocks: Accurate per-corridor ratings; spatial visualization of bottleneck locations
- Implementation: C8 (Phase 3) — not started; currently only station-level ratings

**ML forecasting not started:**
- Problem: PRD §5 lists DS-F11 "Forecast ampacity ahead of real time (regression/ML)" as required; no forecasting code exists
- Blocks: Predictive control and proactive congestion management
- Implementation: C9 (Phase 4) — not started; C5 thermal model is prerequisite

**Learned anomaly detection not started:**
- Problem: PRD §5 lists DS-F12 "Anomaly detection via trained model"; code only has deterministic threshold gates (C7)
- Blocks: Improved fail-safe logic with lower false-alarm rate; integration with real-time monitoring systems
- Implementation: C10 (Phase 4) — not started; depends on C7 unification and historical data

## Test Coverage Gaps

**No test for per-location conductor configuration:**
- What's not tested: Verifying that different locations use appropriate conductor properties instead of global defaults
- Files: `backend/config.py`, `backend/thermal_model.py`, `backend/dlr_pipeline.py`
- Risk: Code can silently use wrong conductor data; no regression test would catch it
- Priority: Medium — becomes critical once corridor discretization (C8) adds location awareness

**No test for API failure and retry behavior:**
- What's not tested: fetch_timeseries behavior when Synoptic API returns 5xx errors, rate-limit responses, or timeouts
- Files: `backend/dlr_pipeline.py::fetch_timeseries` (lines 136-138)
- Risk: Silent failures with timeout=120s hang; no exponential backoff or circuit breaker
- Priority: High — critical for production deployment; current code will block indefinitely on network issues

**No end-to-end integration test:**
- What's not tested: Full pipeline from weather ingestion through CSV export with real (or mock) API responses
- Files: Entire backend/
- Risk: Regressions in data flow or schema mismatches between components go undetected
- Priority: High — recommended before production deployment

**No test for safety monitor G1/G2 vs G3/G4 fallback distinction:**
- What's not tested: Verifying that sensor/link loss falls back to `last_good_rating` while range violations fall back to `static_rating`
- Files: `backend/tests/SafetyMonitor_TestSuite.py` (test missing)
- Risk: Fallback behavior could be accidentally "fixed" and break intended design
- Priority: Medium — unblocks C7 completion once semantics are confirmed

**No test validating solar altitude impact:**
- What's not tested: Verifying that ampacity changes appropriately across different solar altitudes for same weather conditions
- Files: `backend/tests/thermal_model_test.py`
- Risk: Solar altitude modeling simplification (documented in C5 spec) is not validated; changes could drift further from physics
- Priority: Low — known limitation, but regression test would prevent worse approximations

## Documentation Discrepancies

**Weather provider selection mismatch:**
- Stated in: System Design Report §3.1 ("NOAA + NSRDB selected")
- Actual code: All working ingestion uses Synoptic/WTM; NOAA integration doesn't exist
- Files: `backend/weather_provider.py`, `backend/dlr_pipeline.py`, no NOAA code anywhere
- Impact: Course deliverable claims capability that isn't implemented; decision is genuinely open per PRD §7.1
- Action: Update System Design Report to reflect that provider decision is pending; reference PRD as source of truth

**Target city mismatch:**
- Stated in: Project Definition.md §"Input/Output Specifications" (four cities: Austin, Corpus Christi, Midland, El Paso)
- Actual code: Five different cities in `backend/config.py::STATIC_RATINGS` (San Antonio, Houston, Austin, Dallas, Fort Worth); only Austin overlaps the spec
- Files: `backend/config.py` (lines 42-51), no code implementing Corpus Christi, Midland, or El Paso
- Impact: Three of four target cities have no representation in static ratings table; Corpus Christi (Gulf Coast) completely absent
- Action: Resolve in next project phase — either update spec to match current implementation, or implement missing cities

**Corridor vs. city confusion:**
- Stated in: Project Definition.md targets specific cities
- Actual code: `backend/station_explorer.py` defines five *transmission corridors* (Panhandle Export, Permian Basin 345kV, Sweetwater Wind Hub, Big Spring Corridor, West TX to Hill Country), none of which are cities
- Files: `backend/station_explorer.py`, `backend/config.py`, `backend/dlr_pipeline.py` (line ~439 dead code)
- Impact: Unclear whether system is city-based, corridor-based, or station-based; three inconsistent location taxonomies in code
- Action: Formalize location model in Phase 3; refactor once C8 (corridor discretization) is scoped

**Anomaly detection status overstated:**
- Stated in: System Design Report §3.2 "ML model currently being trained and tuned"
- Actual code: No model, no training script; only deterministic gates in `backend/DLRSafetyMonitor.py`
- Files: No ML code anywhere
- Impact: Deliverable describes capability that doesn't exist; course reviewers may think risk reduction is further along than it is
- Action: Update SDR to note C10 is Phase 4 future work; remove claims about "currently training"

---

*Concerns audit: 2026-09-02*
