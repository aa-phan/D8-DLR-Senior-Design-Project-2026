# Data Science Subsystem — Project Status

A living front door for anyone who wants to know "what's shipped, what's in flight, and where do
I go to find out more" without digging through the GSD planning scaffolding in `.planning/`.

This page is written and updated by hand at milestone boundaries — it does not auto-sync with
`.planning/`. For the current, tool-maintained source of truth, follow the links in each section.

---

## Shipped so far

### v1.0 MVP — shipped 2026-09-10

The full pipeline exists end to end: weather ingestion → IEEE 738 thermal modeling →
per-location static-rating comparison → fail-safe safety monitoring (gates G1–G5) → corridor
spatial discretization (as shipped: two corridors, five points each, worst-point rating;
**retired 2026-10-12** and replaced by one independent rating point per city, see
"Point-scope change" below) → ampacity forecasting (naive/EWM, walk-forward backtested) →
learned anomaly detection (gate G6). See
[`v1.0-summary.md`](milestones/v1.0-summary.md) for the full accomplishment list.

### v1.1 Multi-Provider Weather — shipped 2026-09-15

Weather ingestion is now a ratified, five-provider composition behind one adapter
(`backend/weather_provider.py::fetch_weather`):

| Variable family | Provider | Path |
|---|---|---|
| Wind speed/direction, temperature, RH | TCEQ CAMS (primary) + ASOS 1-minute (supplement) | Station |
| Solar irradiance (GHI) | NREL NSRDB PSM v4 (primary) | Grid |
| Full set, historical bulk backfill | Open-Meteo Archive API | Grid, standalone |
| Any of the above, on primary failure | Synoptic (automatic fallback only — never an additional source) | Both |

Every row carries per-field provenance (`wind_source`, `temp_source`, `humidity_source`,
`solar_source`). `PRD.md` §7.1 and `data_provider.md` now record this composition as the team's
ratified decision — see [`v1.1-summary.md`](milestones/v1.1-summary.md) for the full
accomplishment list, or [`decisions/data_provider.md`](decisions/data_provider.md) for the
ratified decision record itself.

### Point-scope change — 2026-10-12

The corridor model is retired. Each of the four project cities (`AUSTIN`, `CORPUS_CHRISTI`,
`MIDLAND`, `EL_PASO`) is now one independent rating point: `config.LOCATIONS` replaces
`config.CORRIDOR_ENDPOINTS`, `city_point.city_point` and `city_rating.rate_city` replace
`corridor_discretization.corridor_geometry` and `rate_corridor`, and nothing reduces across
cities. Models, logs and record fields formerly keyed by corridor are keyed by city. The contract
is [`decisions/point_scope.md`](decisions/point_scope.md); the component is
[`specs/C8-city-point-rating.md`](specs/C8-city-point-rating.md).

**Done since (2026-10-13):**

- **Per-city retrain.** The "ml" forecaster and the anomaly model were retrained for each city
  (local, git-ignored `data/models/`). Forecast winners: HistGradientBoosting (Austin, El Paso)
  and MLP (Corpus Christi, Midland), all four NOT MET against naive. Anomaly: OneClassSVM, MET in
  all four. The 12 shadow correction artifacts (`ml_wind_corrected`, `ml_cooling_corrected`,
  `reference_ml_refit_24h` x 4 cities) are fit and committed in `data/shadow/models/`.
- **Collector changes.** 4 cycles a day (was 2), one child process per city, a retry on the
  forecast fetch, underlying weather model `gfs_seamless` (`config.SHADOW_LIVE_FORECAST_MODEL`),
  and a `forecast_model` field on every v3 row. A fix removed a one-hour forecast offset. Rows
  logged without `forecast_model` are pre-fix (offset, `ecmwf_ifs` forecast) and must never be
  scored or pooled. Revert steps are in `.github/workflows/shadow_collect.yml`.
- **Scorer built.** Per-city evaluation modules (`forecast_shadow_eval_core.py`,
  `forecast_shadow_score*.py`, `forecast_shadow_decision.py`, `forecast_shadow_confirm.py`) are
  merged with tests. Nothing is published automatically and no real FRESH data has been scored.
- **Protocol amendment drafted.**
  [`decisions/confirmation_protocol_v3_per_city.md`](decisions/confirmation_protocol_v3_per_city.md)
  records the owner selections; **the signature block is still blank.** It must be signed before
  the 2026-11-24 run.

**Still open:**

- **Protocol signature** (owner), then the model-artifact hash manifest by the 2026-11-01 freeze.
- **Legacy corridor-named artifacts and logs are retained, not loaded** - the corridor-named
  model files and the shadow logs `AUSTIN_CORPUS_CHRISTI.jsonl` / `MIDLAND_EL_PASO.jsonl` stay on
  disk as the corridor-era record. Per-city shadow logs started empty on 2026-10-12.
- **Shadow-evidence window.** Per-city evidence only exists from 2026-10-12 (gfs_seamless rows
  from 2026-10-13); the evaluation instant remains 2026-11-24 under the draft protocol.
- **Line bearing is an assumption** - carried over from the retired corridor bearings, to be
  replaced with real line orientation when known.

---

## What's in flight now

No milestone is currently active — v1.2/v1.3/v1.4 are **fully scoped (requirements + roadmap
written) but not yet planned or executed.** These three tracks were split out in
[`DEVELOPMENT-TRACKS.md`](DEVELOPMENT-TRACKS.md) so they can be picked up independently, one per
GSD workstream:

| Track | Milestone | Workstream | Status | Goal |
|---|---|---|---|---|
| 1 — Pipeline Integration & Real-Data Verification | v1.2 | `pipeline-integration` | Scoped (4 phases), not started | Wire `run_pipeline` to actually call per-city rating (`city_rating.rate_city`) → anomaly detection → forecasting as one connected sequence, then validate against real historical ERCOT data |
| 2 — ML Model Development | v1.3 | `ml-modeling` | Scoped (2 phases), not started | Replace the naive/EWM forecaster and the mean±k·std anomaly gate with real trained models, behind the same interfaces |
| 3 — Real Transmission-Line Corridor Geometry | v1.4 | `corridor-geometry` | **Retired 2026-10-12** — corridors no longer exist (`decisions/point_scope.md`) | Was: replace the two placeholder straight-line corridors with real substation-to-substation route geometry. No longer applicable; the only remaining geometry-like item is a real per-city line orientation (see Known open items) |

Each workstream's live roadmap and requirements are the actual source of truth — this table is a
summary, not a substitute. The links below are one click through a redirect page into the real
file GSD maintains under `.planning/`:

- Track 1: [`ROADMAP.md`](workstreams/pipeline-integration/ROADMAP.md) · [`REQUIREMENTS.md`](workstreams/pipeline-integration/REQUIREMENTS.md)
- Track 2: [`ROADMAP.md`](workstreams/ml-modeling/ROADMAP.md) · [`REQUIREMENTS.md`](workstreams/ml-modeling/REQUIREMENTS.md)
- Track 3 (retired): [`ROADMAP.md`](workstreams/corridor-geometry/ROADMAP.md) · [`REQUIREMENTS.md`](workstreams/corridor-geometry/REQUIREMENTS.md) — kept as history only

---

## Known open items

- **TCEQ solar coverage gap** — TCEQ CAMS solar-radiation sensors are confirmed only at the
  Austin and Corpus Christi sites; TCEQ is wired for wind/temperature/RH only in v1.1. Tracked as
  v2 requirement **WX-09** if TCEQ solar is ever pursued for Midland/El Paso.
- **No production caller for forecasting/anomaly-detection** — `ampacity_forecast.forecast_ampacity`
  and `anomaly_detector.AnomalyDetector` are implemented and tested but never invoked from
  `dlr_pipeline.py::run_pipeline` today; they're three disconnected code paths. This is exactly
  what Track 1 (v1.2) closes.
- **DS → PSS/E interface contract undefined** — the handoff to the Power Systems sub-team is
  understood informally (a predicted ampacity, evaluated by them against grid conditions for
  feasibility) but no file format, cadence, or exact field set has ever been agreed. See
  [`decisions/pss_e_handoff.md`](decisions/pss_e_handoff.md) for the full note — deliberately
  deferred until an actual cross-team conversation happens.
- **ERCOT live-pull bug (carried, unrelated to weather work)** — `ercot_data_retriever.py::pull_ercot_data`'s
  live path fails with a deterministic `Bad CRC-32` error inside the third-party `gridstatus`
  library, blocking live ERCOT pulls until upstream fixes it.
- **Line orientation per city is an assumption** — `config.CITY_LINE_BEARING_DEG` carries over the
  retired corridor bearings (Austin and Corpus Christi 173.15°, Midland and El Paso 267.54°) so
  perpendicular-wind behavior is unchanged. It is not a measurement; replace it when each city's
  real line orientation is known. The former
  "corridor geometry is a placeholder" item no longer applies — corridors were retired.

---

## Where the live data lives

This page is a summary. For anything that changes as work progresses, follow the tool-maintained
source instead of trusting a stale copy here:

| What | Where |
|---|---|
| Current project state, requirements, key decisions | [`.planning/PROJECT.md`](../../.planning/PROJECT.md) |
| Shipped-milestone accomplishment log | [`.planning/MILESTONES.md`](../../.planning/MILESTONES.md) |
| Cross-milestone lessons learned | [`.planning/RETROSPECTIVE.md`](../../.planning/RETROSPECTIVE.md) |
| Track 1 roadmap/requirements/state | `.planning/workstreams/pipeline-integration/` |
| Track 2 roadmap/requirements/state | `.planning/workstreams/ml-modeling/` |
| Track 3 roadmap/requirements/state (retired) | `.planning/workstreams/corridor-geometry/` |
| Shipped v1.1 archive (phases, roadmap, requirements) | `.planning/workstreams/multi-provider-weather/milestones/v1.1-*` |
| Shipped v1.0 archive (phases, roadmap, requirements) | `.planning/milestones/v1.0-*` |

*Last updated: 2026-10-12, after the corridor model was retired in favor of per-city rating points (previously: 2026-09-23, after v1.1 shipped and v1.2/v1.3/v1.4 were scoped).*
