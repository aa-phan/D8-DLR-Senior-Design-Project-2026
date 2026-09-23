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
spatial discretization (two corridors, five points each, worst-point rating) → ampacity
forecasting (naive/EWM, walk-forward backtested) → learned anomaly detection (gate G6). See
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

---

## What's in flight now

No milestone is currently active — v1.2/v1.3/v1.4 are **fully scoped (requirements + roadmap
written) but not yet planned or executed.** These three tracks were split out in
[`DEVELOPMENT-TRACKS.md`](DEVELOPMENT-TRACKS.md) so they can be picked up independently, one per
GSD workstream:

| Track | Milestone | Workstream | Status | Goal |
|---|---|---|---|---|
| 1 — Pipeline Integration & Real-Data Verification | v1.2 | `pipeline-integration` | Scoped (4 phases), not started | Wire `run_pipeline` to actually call corridor discretization → anomaly detection → forecasting as one connected sequence, then validate against real historical ERCOT data |
| 2 — ML Model Development | v1.3 | `ml-modeling` | Scoped (2 phases), not started | Replace the naive/EWM forecaster and the mean±k·std anomaly gate with real trained models, behind the same interfaces |
| 3 — Real Transmission-Line Corridor Geometry | v1.4 | `corridor-geometry` | Scoped (2 phases); Phase 2 blocked on the Power Systems sub-team | Replace the two placeholder straight-line corridors with real substation-to-substation route geometry |

Each workstream's live roadmap and requirements are the actual source of truth — this table is a
summary, not a substitute:

- Track 1: [`../../.planning/workstreams/pipeline-integration/ROADMAP.md`](../../.planning/workstreams/pipeline-integration/ROADMAP.md) · [`REQUIREMENTS.md`](../../.planning/workstreams/pipeline-integration/REQUIREMENTS.md)
- Track 2: [`../../.planning/workstreams/ml-modeling/ROADMAP.md`](../../.planning/workstreams/ml-modeling/ROADMAP.md) · [`REQUIREMENTS.md`](../../.planning/workstreams/ml-modeling/REQUIREMENTS.md)
- Track 3: [`../../.planning/workstreams/corridor-geometry/ROADMAP.md`](../../.planning/workstreams/corridor-geometry/ROADMAP.md) · [`REQUIREMENTS.md`](../../.planning/workstreams/corridor-geometry/REQUIREMENTS.md)

---

## Known open items

- **TCEQ solar coverage gap** — TCEQ CAMS solar-radiation sensors are confirmed only at the
  Austin and Corpus Christi sites; TCEQ is wired for wind/temperature/RH only in v1.1. Tracked as
  v2 requirement **WX-09** if TCEQ solar is ever pursued for Midland/El Paso.
- **No production caller for forecasting/anomaly-detection** — `ampacity_forecast.forecast_ampacity`
  and `anomaly_detector.AnomalyDetector` are implemented and tested but never invoked from
  `dlr_pipeline.py::run_pipeline` today; they're three disconnected code paths. This is exactly
  what Track 1 (v1.2) closes.
- **ERCOT live-pull bug (carried, unrelated to weather work)** — `ercot_data_retriever.py::pull_ercot_data`'s
  live path fails with a deterministic `Bad CRC-32` error inside the third-party `gridstatus`
  library, blocking live ERCOT pulls until upstream fixes it.
- **Corridor geometry is still a placeholder** — the two corridors (Austin↔Corpus Christi,
  Midland↔El Paso) are straight city-centroid-to-city-centroid lines, not real transmission-line
  routes. Track 3 (v1.4) Phase 1 is scoped to request real geometry from the Power Systems
  sub-team; Phase 2 (actually wiring it in) is blocked until that data arrives.

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
| Track 3 roadmap/requirements/state | `.planning/workstreams/corridor-geometry/` |
| Shipped v1.1 archive (phases, roadmap, requirements) | `.planning/workstreams/multi-provider-weather/milestones/v1.1-*` |
| Shipped v1.0 archive (phases, roadmap, requirements) | `.planning/milestones/v1.0-*` |

*Last updated: 2026-09-23, after v1.1 shipped and v1.2/v1.3/v1.4 were scoped.*
