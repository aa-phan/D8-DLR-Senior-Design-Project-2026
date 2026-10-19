# Data Science Subsystem — Post-v1.1 Development Tracks

> **Update 2026-10-12:** the corridor model was retired — each of the four cities is now an
> independent rating point (`decisions/point_scope.md`). **Track 3 below is retired**, and Track 1
> text that mentions corridors has been updated to per-city terms. Track 3's section is kept as
> history.

Four workstreams (Track 3 since retired; Track 4 added 2026-10-17) for dividing remaining
DS-subsystem work across developers.
Each is scoped to have no file/function overlap with the others at the level of "who owns
the PR," so they can run in parallel. Story-level planning for each track happens separately
(via this project's `.planning/` milestone workflow) once a track is assigned.

This document exists because `PRD.md` §8 ("Future Scope") predates v1.0 and is stale — it
describes C8/C9/C10 as "no corresponding code today," which was true when it was written but
is not true now. This document reflects actual current repo state (2026-09-14) instead.

**For current status** — which of these three tracks are scoped vs. planned vs. shipped, and
what's actually landed since this document was written — see [`PROJECT-STATUS.md`](PROJECT-STATUS.md).

---

## Track 1: Pipeline Integration & Real-Data Verification

**Goal:** Make the DS pipeline actually run end to end against real data, and prove the
result is trustworthy — not just that each piece passes its own tests in isolation.

**Current state:** `dlr_pipeline.py::run_pipeline` — the pipeline's real entry point — never
calls `city_rating.py::rate_city` (formerly `corridor_discretization.py::rate_corridor`), `anomaly_detector.py::AnomalyDetector`, or
`ampacity_forecast.py::forecast_ampacity`. All three are fully implemented and individually
tested, but only ever invoked from their own test suites. They are three disconnected code
paths, not one pipeline. Separately, everything that has been validated so far was validated
either against synthetic fixtures or (for the IEEE 738 thermal model only) a textbook worked
example — nothing has been run against real historical ERCOT transmission data and checked
against published static line ratings, which is the validation bar the System Design Report
itself sets.

**Scope:**
- Wire `run_pipeline` (or a new orchestrating entry point) to call per-city rating
  (`rate_city`) → anomaly check → forecast in sequence, against a real accumulating `historical_archive.py`
  history rather than one-shot test fixtures.
- Finish out the current v1.1 milestone (Synoptic fallback wiring, provider-composition doc
  ratification in `PRD.md`/`data_provider.md`) — this is pipeline-completion work of the same
  kind, not a separate concern.
- Re-run the integrated pipeline against real historical ERCOT data for the four cities
  and sanity-check results against published SLR values, per the System Design Report's stated
  validation plan (§ Full System Integration / weather-corridor validation).

**Not in scope:** building new models (Track 2), the Software sub-team's `api/`/`frontend/` layer.

**Depends on:** nothing new from Track 2 to start; it should hand a clean integration point to
whichever model Track 2 produces. (It previously also benefited from Track 3's real corridor
geometry; that track is retired.)

---

## Track 2: ML Model Development

**Goal:** Build the actual machine-learning models the PRD originally scoped for C9/C10 —
today's code satisfies the naming and the test contracts but is not ML.

**Current state:**
- **Update (2026-10-08):** the state below predates the `ml-modeling` workstream. `ampacity_forecast.py`
  now has three methods (`FORECAST_METHODS = ("naive", "ewm", "ml")`), and C10 is marked Implemented;
  see `specs/C9-ampacity-forecasting.md`, `specs/C10-anomaly-detection.md` and
  `workstreams/ml-modeling/`. The remaining bullets in this section describe the earlier state.
- `ampacity_forecast.py` ("Ampacity Forecasting") originally implemented two methods:
  `"naive"` (last observed value) and `"ewm"` (exponentially-weighted moving average).
- `anomaly_detector.py` ("Learned Anomaly Detection") originally was a rolling `mean ± k·std` threshold
  check plus a forecast-residual check.
- Both are tested exclusively against deterministically-generated synthetic fixtures
  (`_synthetic_history`, seeded). Whether either is well-calibrated against real data is
  unknown — this has never been checked.

**Scope:**
- Design and train an actual forecasting model (regression or neural network, per the PRD's
  own §8 language and the IEEE Trans. Smart Grid prior art already cited in
  `docs/Prior Art Report.md`) to replace/extend the naive/EWM methods behind the same
  `forecast_ampacity` signature.
- Design and train an actual anomaly-detection model on historical per-variable baselines
  (wind, temp, solar, load) to replace/extend the `mean ± k·std` gate, behind the same
  `AnomalyDetector` interface so it drops into the existing `DLRSafetyMonitor` G6 gate
  without changing the fail-safe contract.
- Validate both against real accumulated historical data (depends on volume — see
  `docs/data-science/ROADMAP.md` §5, finding 5, on historical-data lead time), not just
  synthetic fixtures.

**Not in scope:** pipeline wiring/orchestration (Track 1). The
existing `forecast_ampacity`/`AnomalyDetector` signatures and `PIPELINE_SCHEMA` columns are the
interface contract this track must preserve — Track 1's integration work depends on that
contract holding, not on knowing what's inside it.

**Depends on:** real accumulated historical archive volume (Track 1's integration work is what
starts that data actually accruing in production, so this track benefits from Track 1 running
first or in parallel, not necessarily blocking on it for design/prototyping work).

---

## Track 3: Real Transmission-Line Corridor Geometry — RETIRED 2026-10-12

**Retired.** The corridor model this track would have improved no longer exists: each of the four
cities is an independent rating point (`config.LOCATIONS`, `city_point.city_point`,
`city_rating.rate_city`), with no pairing of cities and no spatial discretization. See
`decisions/point_scope.md`. What remains of this track's intent is a single open item — replacing
the assumed per-city line bearings (`config.CITY_LINE_BEARING_DEG`, carried over from the retired
corridor bearings) with real line orientation when known. The text below is the original track
description, kept as history; it describes the corridor-era state (`config.CORRIDOR_ENDPOINTS` is
now `config.LEGACY_CORRIDOR_ENDPOINTS`, used only by the frozen forecast-correction experiment).

**Goal (original):** Replace the two placeholder corridors with real transmission-line geometry.

**State when written:** `backend/config.py::CORRIDOR_ENDPOINTS` defined exactly two corridors —
Austin↔Corpus Christi and Midland↔El Paso — as straight city-centroid-to-city-centroid pairs.
This was always known to be a placeholder: the System Design Report states explicitly that
"during the implementation phase, this will be replaced with actual transmission line geometry
that traces the true conductor path." That replacement did not happen before the corridor model
was retired.

**Scope:**
- Source real substation-to-substation transmission-line route geometry for the corridors this
  project needs to rate (coordinate with the Power Systems (PSS/E) sub-team, who likely already
  have or need the same real line geometry for their own grid simulation work).
- Feed that real geometry into `corridor_discretization.py`'s point-generation logic in place
  of the current synthetic straight-line interpolation between city centroids.
- Decide (with the team) whether corridor coverage should expand beyond the current two pairs
  once real geometry sourcing is in place.

**Not in scope:** pipeline orchestration (Track 1), modeling (Track 2). This track's output is
a data/config change (`CORRIDOR_ENDPOINTS` and whatever geometry representation replaces
straight-line interpolation) — it should not need to touch `ampacity_forecast.py`,
`anomaly_detector.py`, or `dlr_pipeline.py`.

**Depends on:** coordination with the Power Systems sub-team for shared line-geometry data;
otherwise independent.

---

## Track 4: Input Provenance & Power Systems Contract

**Added 2026-10-17**, after Track 3 was retired.

**Goal:** Make every input the rating depends on citable, measure how much the open ones matter,
and turn the DS → PSS/E hand-off from an informal understanding into a confirmed contract.

**Current state:**
- `max_temp_c` is 75 °C in `backend/config.py` and the `ConductorConfig` default, with no
  documented source; project reports state 100 °C. `ieee738_ampacity` uses it as the fixed
  conductor temperature, so it drives every computed rating.
- `STATIC_RATINGS` and `RATING_BOUNDS_BY_LOCATION` come from Power Systems bundle ranges divided
  by a provisional subconductor count; whether those ranges are normal or emergency ratings, and
  at what conductor temperature, is not recorded.
- `config.CITY_LINE_BEARING_DEG` values are placeholders carried over from the retired corridors.
- `decisions/pss_e_handoff.md` is an informal note never confirmed with Power Systems.

**Scope:**
- Audit and record the source and basis of each input above; send Power Systems one consolidated
  data request.
- Measure the sensitivity of computed ampacity to the open inputs, and record before the
  2026-11-01 model freeze whether any model artifact must be refit.
- Apply the values Power Systems confirms to config, `ConductorConfig`, docs, and tests.
- Agree and implement the PSS/E interface contract (format, cadence, fields, granularity, rating
  basis) with a test that checks an emitted file against it.

**Not in scope:** shadow-evaluation scoring and the confirmation protocol (Track 2,
`ml-modeling`); wiring the pipeline into one scheduled run (Track 1); the dashboard and API.

**Depends on:** answers from the Power Systems sub-team. Phase 2 (sensitivity) is designed to
run on candidate values without waiting for them. Live roadmap:
`.planning/workstreams/input-provenance/ROADMAP.md`.

---

## Parallelization Notes

- Tracks 1 and 2 have no file overlap in their early work. Track 4 touches `config.py`,
  `thermal_model.py` defaults and docs, so coordinate with Track 2 on anything that changes a
  value the existing models were trained on. (Track 3 is retired; its former
  overlap with Track 1 on `corridor_discretization.py` no longer applies.)
- All active tracks should treat `PIPELINE_SCHEMA` (`backend/units_def.py`) as the fixed
  contract between them, per the project's existing constraint that no new component may
  create a parallel schema.
