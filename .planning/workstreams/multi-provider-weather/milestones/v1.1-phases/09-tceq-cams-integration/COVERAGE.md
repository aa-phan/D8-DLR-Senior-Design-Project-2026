# Phase 9: TCEQ CAMS — External Source Capability Coverage

**Authored:** 2026-09-13 (planning)
**Source:** `tceq.texas.gov/cgi-bin/compliance/monops/daily_summary.pl`, live-enumerated in `09-RESEARCH.md`

**Detector note:** the deterministic `api-coverage.cjs` probe returned `{"detected":false}` against the
ROADMAP Phase 9 section — it keys on `api`/`sdk`/`endpoint`-class nouns, and this phase's own text says
TCEQ has *no* REST API. The matrix is authored anyway under the contribution's stated default (*full
coverage by default — opt out, never opt in*), because a scraped HTML report has a real capability
surface and a silent omission here is exactly what the default exists to prevent.

## Capability Matrix

| # | Capability | Disposition | Reason (required on OPT-OUT) |
|---|------------|-------------|------------------------------|
| 1 | Current-day report (`cams=<id>`, no date params) | **INTEGRATE** | ROADMAP SC1's "current readings"; served by D-08 as a narrow/recent window, not a separate code path. |
| 2 | Historical/date-selected report (`select_date=user&user_month&user_day&user_year`) | **INTEGRATE** | D-09 requires it — a multi-day `(start, end)` is one request per calendar day. `select_date=user` is mandatory even for a single day (Pitfall 1). |
| 3 | `time_format=24hr` header layout (`0000`..`2300`) | **INTEGRATE** | Avoids the `Morning`/`Afternoon` split-header and AM/PM `Mid`/`Noon` ambiguity (Pitfall 5). |
| 4 | Wind Speed (EPA 61101, mph) | **INTEGRATE** | WX-01 required field; D-07 raise-on-absent. |
| 5 | Wind Direction (EPA 61102, deg compass) | **INTEGRATE** | WX-01 required field; D-07 raise-on-absent. Exact-label match only — #8/#9 collide on substring. |
| 6 | Outdoor Temperature (EPA 62101, degF) | **INTEGRATE** | WX-01 required field; D-07 raise-on-absent. |
| 7 | Relative Humidity (EPA 62201, %) | **INTEGRATE** | WX-01 field; present at CAMS 83/41, absent at 38/1095 → null per D-04, never a raise (D-07). |
| 8 | Resultant Wind Speed (61103) / Resultant Wind Direction (61104) | OPT-OUT | A vector-averaged derivative of #4/#5 over the hour. `thermal_model.perpendicular_wind()` consumes a scalar speed and a compass bearing; ingesting both the scalar and the resultant form would put two different definitions of the same `PIPELINE_SCHEMA` column in play with no column to distinguish them. Not in WX-01's field set. |
| 9 | Maximum Wind Gust (61105) | OPT-OUT | Not a `PIPELINE_SCHEMA` column and not in WX-01's field set. A gust is the correct input for a *mechanical* loading study, not for IEEE 738 convective cooling, which uses the sustained average. Adding it would require a schema change (WX-07's additive-only rule), which is Phase 6 scope already closed. |
| 10 | Std. Dev. Wind Direction (61106) | OPT-OUT | A turbulence/stability metric with no consumer anywhere in C5/C7/C8. Also the one parameter whose label provably differs between `monitors.pl` and `daily_summary.pl` (Pitfall 7) — no reason to take on that fragility for an unused field. |
| 11 | Solar Radiation (present at CAMS 38, 83, 41) | OPT-OUT | Explicitly out of this phase's field scope — NSRDB is the ratified primary solar source (WX-03, shipped Phase 8), and TCEQ solar is tracked as v2 requirement **WX-09**, not v1.1. Taking it here would silently contest a decision another phase already made. |
| 12 | Multiple CAMS sites in one request | OPT-OUT | `daily_summary.pl` reports one site per request, and the returned frame carries no station discriminator column — concatenating two sites' rows would let `merge_observations`' `(city, datetime_utc)` key stitch a single row from two stations. Plan 09-02 makes a multi-ID `stids` request **raise** rather than silently using only the first. Reversible: a later phase may add a `stid`/`city` column and loop. |
| 13 | Air-quality parameters (ozone, PM2.5, NOx, …) | OPT-OUT | Not weather. Nothing in the DLR pipeline consumes them; outside WX-01 and outside the milestone. |
| 14 | `monitors.pl?region=<n>` region/site listing | OPT-OUT (as a *runtime* call) | Consumed once, during research, to choose the four CAMS IDs (D-01/D-02). Hard-coded into `config.TCEQ_STATIONS` per D-01's explicit "decide once, hard-code after" instruction — a runtime lookup would scrape a second HTML page on every request for no benefit. |
| 15 | TAMISWeb (alternate TCEQ interface) | OPT-OUT | `daily_summary.pl` proved sufficient for all four cities (09-RESEARCH.md CAMS Site Selection), which is the only condition CONTEXT.md's discretion item set for investigating it. |
| 16 | POST form submission (`method='post'`) | OPT-OUT | GET with the same parameter names was directly confirmed working on every fetch this research session; POST was never exercised (09-RESEARCH.md A2). Using the unproven verb would trade a verified path for an unverified one. |

**Integrated:** 7 of 16. **Opted out:** 9, each with a reason above.
