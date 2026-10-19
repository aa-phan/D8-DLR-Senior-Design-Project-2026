# Phase 3: Ampacity Forecast Correction Experiment - Research (REFRESH for D-04's 24-hour pivot)

**Researched:** 2026-09-28 (original); **refreshed 2026-09-29** for D-04's pivot to the Previous
Runs API 24-hour lead as the phase's PRIMARY comparison, superseding the 1-hour Historical
-Forecast-API design the original research was built around.
**Domain:** NWP forecast archives (Open-Meteo Previous Runs API), IEEE 738 heat-balance
decomposition, scikit-learn offline experiment harnesses, chronological held-out evaluation.
**Confidence:** HIGH for the new Previous-Runs-API layer (live-probed extensively this session,
~40 raw HTTP requests, cross-verified against Single-Runs and Archive APIs) and for the in-repo
code layer (every cited file re-read this session). MEDIUM for the diurnal-persistence-strength
framing (reasoned from the verified 24h-exact-lag construction, not independently benchmarked).
LOW for nothing load-bearing.

**How to read this document.** This is a refresh, not a rewrite. Everything under a section marked
**[CARRIED OVER, unchanged]** is still accurate and was true before D-04 — re-read it, but it was
not re-verified this session because nothing about the pivot touches it. Everything marked
**[NEW / REPLACED FOR D-04]** is new work from this session, live-verified against the real
Previous Runs API, and is what Waves 2-5 need to plan against. The original 1-hour-lead content
(the `hour % 6` calibration gate, `forecast_leadtime_calibration.py`, the bit-identity finding) is
**preserved below in a dedicated "Legacy 1-Hour Arm" section**, not deleted -- per D-04's
disposition, that code stays in the repo as a documented, labelled, non-primary curiosity.

## Summary

D-04 (see `03-CONTEXT.md`) pivoted the phase's PRIMARY comparison from a 1-hour idealized lead
(Historical Forecast bulk API + calibration gate) to a 24-hour realizable lead (Previous Runs API),
because the 1-hour design's "forecast" data turned out to be bit-identical to "truth" at that lead
for the necessarily-recent window the calibration gate required. This refresh answers the four
questions the pivot raises, all via live HTTP probes against the real API this session (not
re-derived from the vendor's docs alone):

1. **Does the bit-identity problem also affect the 24-hour lead? NO -- refuted, decisively.**
   Live-compared `previous_day1` against `archive-api` truth for the SAME grid point, across 2
   cities, 6+ dates spanning the full 2024-2026 window, on both `wind_speed` and `temperature`:
   **zero exact matches out of ~140+ compared hours**, mean absolute difference 0.5-2.1 m/s
   (wind) and 0.6-1.8 degC (temp) -- a real, physically distinct forecast, not the same number
   twice. The pivot's central premise holds.

2. **CRITICAL, newly-discovered finding this session -- Previous Runs API is NOT a flat,
   exact-by-construction 24-hour lead for every row, contrary to both `03-CONTEXT.md`'s D-04
   characterization and Open-Meteo's own docs.** `previous_day1` is built by the SAME "stitch the
   first six hours of each six-hourly model run" mechanism the 1-hour design's bulk Historical
   -Forecast API used -- just offset by +24 hours instead of +0. Live-verified bit-for-bit against
   `single-runs-api` at all four six-hourly GFS cycles (00Z/06Z/12Z/18Z), for two cities: a valid
   hour where `hour % 6 == 0` carries an EXACT 24.0h lead; the other five hours in that block carry
   leads of 25h, 26h, 27h, 28h, 29h (stitched further into the same prior-day run). This means the
   phase needs the SAME discipline Plan 03-01 already built for the 1-hour case -- a verified,
   deterministic filter, not a trust-the-vendor assumption -- just with the remainder changed from
   `1` to `0`. See Pattern 2 below for the full live evidence and Pitfall 1 for the design
   consequence.

3. **The `models=` pinning choice is NOT the same model as the 1-hour design's `ecmwf_ifs`.**
   Live-verified: pinning `models=ecmwf_ifs` on Previous Runs API returns HTTP 200 with an
   ALL-NULL array for every date this project needs except roughly the last ~6 months -- it would
   silently (well, loudly, via the existing null-completeness check) fail almost the entire
   candidate window. The unpinned `best_match` default resolves, for all four project cities, to
   the IDENTICAL grid point and IDENTICAL values as `models=gfs_seamless` explicitly pinned --
   confirmed by direct comparison, not assumed. **Recommendation: pin `models=gfs_seamless`
   explicitly** (not `best_match` -- pin for the same reason the 1-hour design pinned `ecmwf_ifs`:
   an unpinned default can silently re-resolve later). This requires a SECOND model-ID constant in
   `open_meteo_forecast_provider.py`, not reuse of the existing `FORECAST_MODEL_ID = "ecmwf_ifs"`.

4. **Row volume is dramatically larger, even after applying the necessary exact-lead filter.**
   The full candidate window (`2024-01-20` -- the live-verified archive start for `gfs_seamless`
   -- through "yesterday") fetched in **one HTTP request, 23,592 hourly rows, 957,624 bytes, zero
   nulls, 7.2s**. Filtering to the exact-24h-lead subset (`hour % 6 == 0`, mirroring Plan 03-01's
   `hour % 6 == 1` filter for the 1-hour case) leaves **~3,932 scored rows/city** over the full
   window -- about 2.7x the 1-hour design's final ~1,440 rows/city, while ALSO being a genuine,
   non-bit-identical forecast/truth pair.

**Primary recommendation:** Add a new `fetch_previous_runs(lat, lon, start, end, previous_day=1)`
function to `open_meteo_forecast_provider.py`, pinned to a new `PREVIOUS_RUNS_MODEL_ID =
"gfs_seamless"` constant (NOT the existing `FORECAST_MODEL_ID`). Generalize the anchored-pair-frame
contract's hardcoded `pd.Timedelta(hours=1)` to a `lead_hours` parameter so the SAME machinery
(`anchored_pair_frame`, `assert_exact_lead`, `filter_to_exact_lead`) serves both the legacy 1-hour
arm (`lead_hours=1`, existing `hour % 6 == 1` filter) and the new primary 24-hour arm
(`lead_hours=24`, new `hour % 6 == 0` filter). Do NOT reuse `ampacity_forecast.forecast_ampacity
(method="naive")` / `backtest_residuals` for the 24h persistence arm -- that function's "naive"
point-forecast is hardwired to "the immediately preceding row" (1 hour at this project's cadence),
which at a 24-hour claim would silently score a 1-hour-old persistence baseline dressed up as a
24-hour one. Build the 24h persistence anchor the same way Plan 03-01 built the 1h one: a direct
shift of the full unfiltered truth series, just by `pd.Timedelta(hours=24)` instead of `hours=1`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01 (ORIGINAL, now downstream of D-04): Use Open-Meteo's Historical Forecast API (bulk
date-range mode) as the forecast archive, gated by an empirical lead-time calibration step.**
Fully executed in Plan 03-01; its resulting code (`open_meteo_forecast_provider.
fetch_historical_forecast`/`fetch_single_run`, `forecast_leadtime_calibration.py`) is retained and
still correct for the now-downgraded 1-hour curiosity arm. See "Legacy 1-Hour Arm" section below
for the full original content (calibration gate mechanics, the bit-identity finding, the two window
corrections).

**D-02: Build and run the full seven-approach comparison in this phase; explicitly stop and report
if nothing beats persistence.** Unchanged by D-04. The seven arms (0 persistence, 1 NWP-wind-delta
baseline, 2 raw forecast->IEEE 738, 3 ML-corrected wind, 4 ML-corrected cooling, 5 reference "ml"
refit on train+val, 6 oracle) are now run against the 24-hour Previous-Runs data as PRIMARY, with
the 1-hour Historical-Forecast arm kept as a documented, labelled, non-primary curiosity (D-04's
disposition). All arms still score on **identical held-out chronological test timestamps** --
`experiment_splits.calendar_split`, already built and tested in Plan 03-01, is lead-time-agnostic
and needs no change for the 24h primary path.

**D-03: No existing runtime file changes behavior in this phase.** Unchanged. New code lives in new
files; `thermal_model.py`'s `convective_heat_loss`/`natural_convection` extraction and
`forecast_training.py`'s `corridor_weakest_link` extraction are both **already complete** (Plan
03-02, confirmed by direct read this session -- see "Carried-Over Code" below) and are lead-time
-agnostic, fully reusable by the 24h primary path with zero further change.

**D-04 (SUPERSEDES D-01's 1-hour lead as primary): Pivot to the 24-hour realizable lead via
Open-Meteo's Previous Runs API as the phase's primary comparison; the 1-hour idealized-lead arm
(D-01) is downgraded to a documented, non-primary curiosity.** Full text preserved verbatim from
`03-CONTEXT.md`:

> **What happened.** Plan 03-01 executed D-01 fully: it built the bulk-forecast provider, the
> lead-time calibration gate, found and precisely characterized a real deterministic-lead boundary
> (sharp cutover, further refined to 2025-10-01 once all four daily six-hourly runs were checked,
> not just 00Z), corrected the experiment window accordingly, and then ran the first real scored
> slice (persistence vs. raw-forecast-through-IEEE-738 for one city). That run surfaced a second,
> more fundamental problem no prior document anticipated: for the corrected (necessarily recent)
> window, Open-Meteo's "forecast" bulk product is empirically bit-identical to the "truth"
> archive/reanalysis product -- confirmed independently via raw HTTP requests bypassing all repo
> code, across three cities. Arm 2 (raw forecast) consequently scored an exact 0.000 MAE against
> truth -- not because a 1-hour-lead forecast is skillful, but because in this data source, at this
> lead, for this recent window, "forecast" and "truth" are the same number.
>
> **Resolution (user decision, 2026-09-29):** promote the 24-hour realizable-lead arm... to the
> phase's PRIMARY comparison. Open-Meteo's Previous Runs API (`previous-runs-api.open-meteo.com`)
> gives an exact, unambiguous lead by construction (`<var>_previous_dayN` columns, N=1..7 days), is
> bulk-batched (no per-run HTTP calls, no calibration gate needed at all -- the lead is correct by
> API contract, not something to empirically verify), and at 24 hours out, forecast and truth
> should genuinely diverge... Archive coverage for this endpoint begins ~2024-01-15/20.
>
> **What carries over unchanged:** `backend/wind_vector.py`, the `thermal_model.py`
> `convective_heat_loss`/`q_conv_override` extraction, and `backend/forecast_training.py`'s
> `corridor_weakest_link` extraction... are lead-time-agnostic and fully reusable. The provider
> adapter needs a new `fetch_previous_runs` function... rather than a redesign.
>
> **What needs replanning:** the anchored-pair-frame contract, `forecast_experiment.py`'s
> arm-scoring machinery, and Plans 03-03 through 03-07 were all designed around the 1-hour
> idealized lead as primary. These need re-design around the 24-hour Previous-Runs-API lead as
> primary instead.
>
> **Disposition of the 1-hour arm:** keep it as a documented, explicitly-labeled non-primary
> curiosity -- report its result in the final decision record with the bit-identity caveat
> prominently attached, but do not treat it as a competing candidate against persistence in the
> phase's primary verdict.

**IMPORTANT CORRECTION to D-04's own text, established live this session:** D-04's claim that
Previous Runs "gives an exact, unambiguous lead by construction... no calibration gate needed at
all" is **not accurate as stated** -- see Summary point 2 and Pattern 2 below. The lead is exact
ONLY for `hour % 6 == 0` valid times; the rest of the series carries a 24-29h range. This does not
undo D-04's resolution (the pivot still fully solves the bit-identity problem, and a verified
filter is a much smaller ask than a full calibration gate), but the planner must not carry forward
the "no verification needed" framing into Wave 2-5 task design. A lightweight verification is still
warranted -- see Pitfall 1's recommended design.

### Claude's Discretion (equivalent: CONTEXT's Open Questions, now updated for D-04)

- **Lead-time gate contingency (1-hour arm):** resolved in Plan 03-01 -- see "Legacy 1-Hour Arm."
- **`ieee738_ampacity` override shape:** resolved in Plan 03-02 (`q_conv_override=None` keyword,
  already implemented -- see "Carried-Over Code").
- **Approach 4 target parameterization (level vs. log-ratio):** still open, decide on the
  validation set -- unaffected by D-04's lead change.
- **Approach 3 pooling (per-corridor vs. per-city):** still open, decide on the validation set --
  unaffected by D-04's lead change.
- **NEW (this refresh): exact-lead filter vs. broader "approximately 24h" window for the primary
  arm.** See Open Questions #1 below -- this is the 24h analog of the old lead-time-gate question
  and needs an explicit planner decision.
- **NEW (this refresh): how does arm 5 (reference "ml" model, refit train+val only) handle a
  24-hour target when the production model's target-shift logic is hardwired to
  `config.FORECAST_HORIZON_MINUTES` (currently 60)?** See Pitfall 4 and Open Questions #2.
- **Requirement ID:** still no new ID needed -- D-04 explicitly reconfirms this ("Not a
  requirements change").

### Deferred Ideas (OUT OF SCOPE)

Unchanged from the original: probabilistic/quantile evaluation, regime-specific correction models,
multi-NWP-source fusion, and wiring any winning approach into `ampacity_forecast.FORECAST_METHODS`
remain explicitly out of scope for this phase.
</user_constraints>

<phase_requirements>
## Phase Requirements

Unchanged from the original research: **no new requirement ID is warranted.** D-04 does not change
this -- it is still a methodology investigation of FCST-01's existing `"ml"` method, discharging no
new capability commitment. See the original research's full reasoning (REQUIREMENTS.md's
capability-commitment framing, the `Unmapped: 0` invariant) -- not re-derived here since D-04 does
not touch it.

| ID | Description | Research Support |
|----|-------------|------------------|
| *(none)* | Methodology investigation of FCST-01's shipped `"ml"` method, now primarily evaluated at a 24-hour lead per D-04 | This document + original 03-RESEARCH.md content |
</phase_requirements>

## Architectural Responsibility Map

**[CARRIED OVER, unchanged by D-04]** -- the tier assignments do not change; only the data source
feeding the "Forecast-archive HTTP fetch" row changes.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Forecast-archive HTTP fetch + response validation (NOW: bulk Historical-Forecast for the legacy 1h arm, Previous-Runs for the PRIMARY 24h arm) | Provider adapter (`open_meteo_forecast_provider.py`) | — | Same module, one more sibling function (`fetch_previous_runs`) alongside `fetch_historical_forecast`/`fetch_single_run` |
| 24h-lead stitching verification (NEW) | A new, lightweight verification (module TBD by planner — see Pitfall 1) | Provider adapter | Mirrors the 1-hour design's calibration-gate tier assignment, scaled down since the mechanism is now understood analytically, not just empirically |
| Wind u/v decomposition + recomposition | Pure math module (`wind_vector.py`) | — | Unchanged — lead-time-agnostic |
| Convective heat-loss term extraction | Physics core (`thermal_model.py`) | — | Unchanged — already extracted in Plan 03-02 |
| Fixed calendar train/val/test split | Shared experiment infra (`experiment_splits.py`) | — | Unchanged — already built and tested in Plan 03-01, lead-time-agnostic |
| Per-approach fit + score, generalized for a `lead_hours` parameter | Offline experiment harness (`forecast_experiment.py`) | scikit-learn | The anchored-pair-frame contract needs generalizing (currently hardcodes `pd.Timedelta(hours=1)` and the 1h-specific filter constants) — see Pattern 3 |
| Weakest-link corridor reduction | Offline trainer (`forecast_training.py`, extracted helper) | — | Unchanged — already extracted in Plan 03-02 |
| Runtime forecast serving | **explicitly NOT this phase** (`ampacity_forecast.py` untouched) | — | D-03, unchanged |

## Standard Stack

**[CARRIED OVER, unchanged]** No new package is required by the D-04 pivot. `pandas`, `numpy`,
`scikit-learn`, `requests`, `pytest` are all already pinned/installed and used identically. See the
original research's Standard Stack, Package Legitimacy Audit, and "Alternatives Considered" tables
for the full detail — not re-verified this session since nothing about package versions changed.

**One new constant is required** (not a package): `PREVIOUS_RUNS_MODEL_ID: str = "gfs_seamless"` in
`open_meteo_forecast_provider.py`, alongside the existing `FORECAST_MODEL_ID = "ecmwf_ifs"`. See
Pattern 1 for why these must be two distinct constants, not one shared value.

## Package Legitimacy Audit

**[CARRIED OVER, unchanged]** This phase installs no external packages, before or after D-04. See
the original research's audit table — `pandas`, `numpy`, `scikit-learn`, `requests` all `[OK]`,
already pinned, no new install decision.

## Architecture Patterns

### System Architecture Diagram (24-hour PRIMARY path, NEW)

```
                    ┌──────────────────────────────────────────┐
                    │  Open-Meteo Archive API (ERA5 reanalysis)│
                    │  archive-api.open-meteo.com/v1/archive   │
                    └───────────────────┬──────────────────────┘
                                        │  (EXISTING provider, unchanged)
                                        │  open_meteo_provider.fetch_open_meteo
                                        ▼
                          "TRUTH" weather @ valid time T
                    (air_temp, wind_speed, wind_direction, GHI, RH)
                                        │
   ┌────────────────────────────────────┼────────────────────────────────────┐
   │                                    │                                    │
   │  ┌──────────────────────────────┐  │                                    │
   │  │ Open-Meteo Previous Runs API │  │                                    │
   │  │ previous-runs-api...         │  │                                    │
   │  │ &models=gfs_seamless (NEW    │  │                                    │
   │  │  constant, NOT ecmwf_ifs)    │  │                                    │
   │  │ &hourly=<var>_previous_day1  │  │                                    │
   │  │ &start_date&end_date (bulk)  │  │                                    │
   │  └──────────────┬───────────────┘  │                                    │
   │   (NEW function)│                  │                                    │
   │                 ▼                  │                                    │
   │      "FORECAST" weather @ T        │                                    │
   │      lead = 24 + (T.hour % 6) h ───┼──┐  (NOT a flat 24h -- see Pattern 2)
   │                 │                  │  │                                 │
   │                 │   ┌──────────────┴──▼─────────────────────────┐       │
   │                 │   │ LIGHTWEIGHT VERIFICATION (NEW, smaller     │       │
   │                 │   │ than the 1h gate -- mechanism is now       │       │
   │                 │   │ analytically understood, live-confirmed    │       │
   │                 │   │ against single-runs-api this session)      │       │
   │                 │   └──────────────┬────────────────────────────┘       │
   │                 │                  │ pass                               │
   │                 ▼                  ▼                                    │
   │     ┌───────────────────────────────────────────┐                       │
   │     │ JOIN on datetime_utc, per endpoint city   │◄──────────────────────┘
   │     │ → paired (forecast, truth) frame          │
   │     │ → FILTER to hour % 6 == 0 (exact 24h lead)│  (was ==1 for the 1h arm)
   │     └───────────────────┬───────────────────────┘
   │                         ▼
   │     ┌───────────────────────────────────────────┐
   │     │ anchor group: truth shifted by 24h (NOT 1h)│
   │     │ built from FULL unfiltered series, same    │
   │     │ discipline as Plan 03-01's anchored_pair_  │
   │     │ frame -- generalized `lead_hours` param    │
   │     └───────────────────┬───────────────────────┘
   │                         ▼
   │     ┌───────────────────────────────────────────┐
   │     │ experiment_splits.calendar_split()        │  (UNCHANGED, reused as-is)
   │     │ train | val | test   (dates, never shuffled)│
   │     └───────────────────┬───────────────────────┘
   │                         │  identical test timestamps for ALL arms
   │        ┌────────────────┼────────────────┬──────────────┬─────────────┐
   │        ▼                ▼                ▼              ▼             ▼
   │  ┌──────────┐   ┌──────────────┐  ┌───────────┐  ┌───────────┐ ┌──────────┐
   │  │0 persist │   │1 wind-delta  │  │2 raw fcst │  │3 ML-wind  │ │4 ML-cool │
   │  │ (T-24h)  │   │ obs+Δfcst    │  │ →IEEE738  │  │ u/v corr  │ │ Q_conv   │
   │  └────┬─────┘   └──────┬───────┘  └─────┬─────┘  └─────┬─────┘ └────┬─────┘
   │       │                │                │              │            │
   │       │        (UNCHANGED PHYSICS: wind_vector, thermal_model, corridor_weakest_link)
   │       │                        ▼              ▼              ▼
   │       │  ┌──────────────────────────────────────────────────────────────────┐
   │       │  │ 5 reference: "ml" refit -- NEEDS a 24h target shift, NOT the      │
   │       │  │   production build_training_matrix's hardwired 1-row/60-min shift │
   │       │  │ 6 oracle: observed future wind [LABELLED NON-FORECAST]           │
   │       │  └──────────────────────────┬───────────────────────────────────────┘
   │       ▼                             ▼
   │              ┌──────────────────────────────────┐
   │              │ score on identical test rows     │
   │              │ MAE / RMSE / rows / lead / caveat│
   │              │ → JSON report + tracked record   │
   │              └──────────────────────────────────┘
   └──────────────────── no arrow returns to ampacity_forecast.py (D-03) ─────┘

  Legacy 1-hour arm (D-01, fully built in Plan 03-01) still exists in parallel,
  labelled non-primary -- see "Legacy 1-Hour Arm" section. Its diagram is
  preserved unchanged at the end of this document.
```

### Pattern 1: Model pinning for Previous Runs API is a DIFFERENT model than the 1-hour design used

**What, live-verified this session.** The existing `open_meteo_forecast_provider.FORECAST_MODEL_ID
= "ecmwf_ifs"` constant, if naively reused for a new `fetch_previous_runs` call, breaks almost the
entire candidate window:

```
Previous Runs API, wind_speed_10m_previous_day1, AUSTIN (30.2711,-97.7437), models=ecmwf_ifs:
  2024-01-10 .. 2026-01-15   -> HTTP 200, 24/24 null    (unusable for the whole desired window)
  2026-03-01 onward          -> HTTP 200, 0/24 null     (only the last few months work)

Same requests with NO models param (unpinned "best_match"):
  2024-01-18 -> 24/24 null
  2024-01-19 -> 12/24 null   (half the day; the run that would populate the rest hadn't posted yet)
  2024-01-20 -> 0/24 null    (clean start, confirmed identically for all 4 project cities)
  ... through 2026-09-20     -> 0/24 null, continuously
```

**Root cause, live-confirmed by direct model comparison at the same lat/lon/date:** unpinned
`best_match` resolves to `gfs_seamless` for **every one of this project's four cities** (identical
lat/lon grid snap AND identical values, confirmed by direct side-by-side request):

```
AUSTIN         best_match latlon=(30.269146,-97.75338)  gfs_seamless latlon=(30.269146,-97.75338)  IDENTICAL VALUES
EL_PASO        best_match latlon=(31.768824,-106.503784) gfs_seamless latlon=(31.768824,-106.503784) IDENTICAL VALUES
MIDLAND        best_match latlon=(31.992321,-102.09157)  gfs_seamless latlon=(31.992321,-102.09157)  IDENTICAL VALUES
CORPUS_CHRISTI best_match latlon=(27.766878,-97.41585)   gfs_seamless latlon=(27.766878,-97.41585)   IDENTICAL VALUES
```

`ecmwf_ifs` pinned resolves to a DIFFERENT, finer grid point (`30.263618,-97.69321` for Austin, vs.
`30.269146,-97.75338` for `best_match`/`gfs_seamless`) and its Previous-Runs archive apparently only
goes back a few months -- a completely different (and much shallower) depth story than its
Historical-Forecast/Single-Runs depth (March 2024) the 1-hour design relies on. These are
independently-configured archives per endpoint per model; depth on one endpoint says nothing about
depth on another, even for the "same" model name.

**When to use:** pin `models="gfs_seamless"` explicitly on the new `fetch_previous_runs` function,
as a SECOND constant (`PREVIOUS_RUNS_MODEL_ID`), never reusing `FORECAST_MODEL_ID`. Even though
`best_match` happens to equal `gfs_seamless` today for all four project cities, pin explicitly for
the same reason the 1-hour design pinned `ecmwf_ifs` instead of trusting `best_match` -- an
auto-resolved default can silently change later, and CONTEXT's own D-01 rationale already
documents `best_match` resolving to different models on different endpoints (ICON was observed for
Single-Runs at one point). Do not assume this session's finding is permanent; the new provider
function's docstring should record this exact evidence (mirroring `FORECAST_MODEL_ID`'s own
docstring pattern) so a future re-verification has something concrete to check against.

### Pattern 2: `previous_day1` is a six-hour-stitched product, NOT a flat 24-hour lead — the single most important finding of this refresh

**What.** Open-Meteo's own docs state: *"`_previous_day1` is the value that was predicted 24 hours
before valid time"* [CITED: https://open-meteo.com/en/docs/previous-runs-api]. This is TRUE only
for valid hours that are themselves exact six-hourly cycle hours (00/06/12/18 UTC). For every other
hour, `previous_day1` is stitched from the SAME prior-day run, just further into its output --
exactly the mechanism `03-RESEARCH.md`'s original Pattern 2 already found for the Historical
-Forecast bulk API at a near-zero lead, here shifted by +24h instead of +0h.

**Live evidence (this session), bit-for-bit exact match against the independently-fetched
Single-Runs value at the run issued exactly 24 hours before each six-hourly cycle, for AUSTIN,
2026-09-20, `wind_speed_10m`, `models=gfs_seamless`:**

```
run=2026-09-19T00:00  target=2026-09-20T00:00  from_run=2.53  previous_day1=2.53  MATCH (exact, lead=24h)
run=2026-09-19T00:00  target=2026-09-20T01:00  from_run=2.01  previous_day1=2.01  MATCH (exact, lead=25h)
run=2026-09-19T00:00  target=2026-09-20T02:00  from_run=1.63  previous_day1=1.63  MATCH (exact, lead=26h)
run=2026-09-19T00:00  target=2026-09-20T03:00  from_run=1.24  previous_day1=1.24  MATCH (exact, lead=27h)
run=2026-09-19T00:00  target=2026-09-20T04:00  from_run=2.02  previous_day1=2.02  MATCH (exact, lead=28h)
run=2026-09-19T00:00  target=2026-09-20T05:00  from_run=3.11  previous_day1=3.11  MATCH (exact, lead=29h)
run=2026-09-19T06:00  target=2026-09-20T06:00  from_run=3.50  previous_day1=3.50  MATCH (exact, lead=24h)
   ... (identical pattern repeats for the 06Z, 12Z, 18Z blocks -- ALL 24 hours matched exactly,
        0 mismatches, across both wind_speed AND temperature_2m, for both AUSTIN 2026-09-20 and
        EL_PASO 2026-06-15 -- 4 independent (city, date, variable) confirmations, 96 hour-cells,
        zero exceptions)
```

**Consequence:** `previous_day1`'s effective lead is `24 + (valid_hour % 6)` hours -- a flat 24.0h
ONLY when `valid_hour % 6 == 0` (00/06/12/18 UTC); ranging up to 29h for `valid_hour % 6 == 5`
(05/11/17/23 UTC). A phase whose experimental claim is "does a genuinely 24-hour-ahead forecast
beat persistence" and that scores the UNFILTERED series is silently blending five different lead
times (24-29h) into one number, the exact category of imprecision D-01's own founding principle
("never trust the product's stated lead time") exists to prevent.

**When to use:** filter to `valid_time.hour % 6 == 0` for a claim of an exact, verified 24.0h lead
-- the 24h analog of the 1-hour design's `hour % 6 == 1` filter, just with the remainder changed to
`0` (since the exact-lead hours are now the run-issue hours themselves, not one hour after them).
This is a deliberate, symmetric design choice, not a coincidence: reuse the SAME
`FORECAST_EXPERIMENT_LEAD_FILTER_MODULUS = 6` constant, add a new
`FORECAST_EXPERIMENT_24H_LEAD_FILTER_REMAINDER = 0` alongside the existing (now legacy-scoped)
`FORECAST_EXPERIMENT_LEAD_FILTER_REMAINDER = 1`.

**Recommended lightweight verification (replaces a full new calibration gate):** because the
mechanism is now analytically understood (a Single-Runs cross-check like the one above, not a
statistical sample), a full `forecast_leadtime_calibration.py`-style hard gate is probably
over-engineering for this case -- but skipping verification entirely (trusting D-04's or the
vendor's "exact by construction" framing) is exactly the mistake the phase was created to stop
making. Recommend: a small, synthetic-data unit test asserting `hour % 6 == 0` rows are the only
ones treated as exact-lead (mirroring `forecast_leadtime_calibration_test.py`'s existing pattern of
testing the rule with synthetic data, not a live network call in the test suite), PLUS one
documented, hand-run, transcribed live verification (like the one above) recorded in the phase's
final decision record -- not a per-warm hard gate, since (unlike the 1-hour case) there is no
known historical discontinuity risk here (no ECMWF-cycle-upgrade-style event has been found or is
expected for GFS's stitching depth). The planner should decide the exact shape (Open Questions #1).

### Pattern 3: Generalizing the anchored-pair-frame contract for a `lead_hours` parameter

**What.** Plan 03-01's `forecast_experiment.anchored_pair_frame`/`assert_exact_lead`/
`filter_to_exact_lead` already implement the RIGHT contract (anchor/truth/fcst column groups, the
anchor built from the FULL unfiltered series before any filter, an automated gate that the anchor
gap is exactly the claimed lead) -- they just hardcode `pd.Timedelta(hours=1)` and read the
LEGACY-scoped `config.FORECAST_EXPERIMENT_LEAD_FILTER_REMAINDER` (=1) directly
[VERIFIED: backend/forecast_experiment.py:241, 272, 307 -- `anchor["datetime_utc"] =
anchor["anchor_datetime_utc"] + pd.Timedelta(hours=1)"`, `merged["lead_hours"] =
merged["datetime_utc"].dt.hour % config.FORECAST_EXPERIMENT_LEAD_FILTER_MODULUS`, `remainder =
config.FORECAST_EXPERIMENT_LEAD_FILTER_REMAINDER`].

**When to use:** generalize, do not duplicate. Add a `lead_hours: int` parameter to
`anchored_pair_frame` (default could stay 1 for backward compatibility with the legacy arm's own
tests, or the planner may prefer an explicit no-default signature so a caller can never
accidentally score the wrong lead) that:
1. Replaces the hardcoded `pd.Timedelta(hours=1)` with `pd.Timedelta(hours=lead_hours)`.
2. Fetches from `fetch_previous_runs` instead of `fetch_historical_forecast` when scoring the
   24h-primary arm (a caller-supplied fetch function, or a `source` enum, is a reasonable seam --
   the planner should decide the exact shape).
3. Uses the NEW `FORECAST_EXPERIMENT_24H_LEAD_FILTER_REMAINDER` (Pattern 2) rather than the legacy
   `FORECAST_EXPERIMENT_LEAD_FILTER_REMAINDER` when `lead_hours=24`.
4. `assert_exact_lead` already generalizes for free -- it compares `datetime_utc -
   anchor_datetime_utc` against a fixed `pd.Timedelta(hours=1)` today
   [VERIFIED: backend/forecast_experiment.py:288, `bad = gaps != pd.Timedelta(hours=1)`] and needs
   the SAME `lead_hours` parameter threaded through, not a rewrite.

**Anti-pattern:** writing a parallel `anchored_pair_frame_24h` function. This is precisely the
"Don't Hand-Roll" mistake the original research warned against for `experiment_splits.py` vs.
`chronological_split` -- two independent copies of the same contract drift apart. Generalize the
one function that already has the tests, the caching discipline, and the docstring-as-contract
this module is built around.

### Pattern 4: 24-hour persistence is diurnally self-aligned -- a stronger baseline than the horizon might suggest

**What, reasoned from the verified construction (MEDIUM confidence -- not independently
benchmarked this session, but follows directly from the verified 24h lag).** A naive persistence
forecast at a 1-hour horizon ("assume the next hour looks like this hour") is a weak baseline
precisely because weather has meaningful hour-to-hour variance. A naive persistence forecast at
EXACTLY a 24-hour horizon ("assume this time tomorrow looks like this time today") is structurally
different: because 24 hours is exactly one full diurnal cycle, T-24h and T share the same
approximate solar angle, similar approximate temperature regime (unless a weather-front boundary
crosses in between), and similar approximate diurnal wind pattern. This is NOT the same as
"persistence degrades with longer horizons" intuition most readers will bring -- at exactly 24h,
persistence is automatically the "seasonal-naive"/day-ago-same-hour baseline that time-series
forecasting literature treats as a genuinely strong baseline for diurnally-cyclic series, not a
weak one.

**Consequence for planning:** do not expect the correction arms (3, 4) or the "ml" reference (5) to
beat 24h persistence as easily as the phase's original framing (built around the intuition that a
longer horizon means persistence gets easier to beat) might suggest. This raises the bar for what
counts as a meaningful result and should be stated plainly in the eventual decision record, not
discovered as a surprise mid-execution the way the bit-identity problem was.

### Anti-Patterns to Avoid (NEW, specific to the 24h primary path)

- **Reusing `ampacity_forecast.forecast_ampacity(method="naive")` / `backtest_residuals` for the
  24h persistence arm.** `_point_forecast(method="naive")` returns `float(series.iloc[-1])`
  [VERIFIED: backend/ampacity_forecast.py:316-317] -- "the immediately preceding ROW," not "the row
  24 hours before." At this project's hourly cadence this is EXACTLY correct for the legacy 1h arm
  (1 row = 1 hour = the claimed lead) but WRONG for the 24h arm (1 row is still 1 hour, not 24).
  Calling this function unchanged for the 24h arm would silently score a 1-hour-old persistence
  baseline as if it were a 24-hour one -- structurally the same kind of silent mislabeling error
  the bit-identity finding already forced a pivot to avoid. Build the 24h anchor directly in
  `forecast_experiment.py`'s own anchor-group construction (Pattern 3), never via this function.
- **Reusing `forecast_training.build_training_matrix` unchanged for arm 5's 24h refit.** That
  function shifts the target by `config.FORECAST_HORIZON_MINUTES` worth of rows (currently 60 min
  = 1 row) [VERIFIED: backend/forecast_training.py:309-325]. It is a GLOBAL config read, not a
  function parameter -- there is no way to ask it for a 24-hour target shift without either
  temporarily monkeypatching the module constant (fragile, and exactly the kind of hidden global
  -mutation bug this project's centralization discipline exists to prevent) or writing a parallel
  target-shift helper parameterized by hours. See Pitfall 4.
- **Trusting the vendor docs' "exact 24h" framing without the Pattern 2 filter.** Already covered
  above -- restated here because it is the single highest-risk mistake this refresh exists to
  prevent, directly analogous to the founding mistake ("never trust the product's stated lead
  time") the phase was built to avoid in the first place.
- **Pinning `models=ecmwf_ifs` (the legacy arm's constant) for the new `fetch_previous_runs`
  call.** See Pattern 1 -- this silently nulls out (loudly, via the completeness check, which is
  the SAFE failure mode -- but still a failure) the overwhelming majority of the intended window.

## Don't Hand-Roll

**[CARRIED OVER, unchanged]** — every row in the original research's table still applies verbatim
(chronological holdout split, Open-Meteo response validation, weakest-link corridor reduction,
perpendicular-wind projection, persistence baseline discipline, estimator persistence, wind
direction → components). Not re-verified this session since D-04 does not touch any of them — see
the original document's "Don't Hand-Roll" section, reproduced in full below the "Legacy 1-Hour
Arm" heading for convenience.

**One new row, specific to this refresh:**

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 24-hour-lead stitching detection | A brand-new statistical calibration gate from scratch | The SAME `hour % 6` deterministic-rule pattern `forecast_leadtime_calibration.py` already established, just re-pointed at the Previous-Runs/Single-Runs pair with remainder 0 instead of 1 | The mechanism (six-hour-cycle stitching) is IDENTICAL in kind to the one already solved for the 1-hour arm — a new gate would re-derive the same guard logic (`_MATCH_RATE_FLOOR`, boundary-skip counting, tolerance-vs-exact-equality) a second time |

## Common Pitfalls

### Pitfall 1 (NEW, highest priority): Scoring the unfiltered Previous-Runs series silently blends five different lead times

**What goes wrong:** a report states "at the 24-hour horizon, method X achieves MAE=..." when the
underlying rows actually span leads 24-29h, with no visibility into how much of the measured skill
(or lack of it) is attributable to the lead-time smear rather than genuine forecast quality.

**Why it happens:** Open-Meteo's own docs describe `previous_day1` as a flat 24h lead (Pattern 2),
and D-04's own framing in `03-CONTEXT.md` repeats that characterization ("gives an exact,
unambiguous lead by construction"). Both are wrong for every hour except the six-hourly cycle
hours themselves — live-verified this session, not merely suspected.

**How to avoid:** filter to `valid_time.hour % 6 == 0` before scoring the primary arm (Pattern 2),
using a new `FORECAST_EXPERIMENT_24H_LEAD_FILTER_REMAINDER = 0` constant. If the planner instead
chooses to accept the broader 24-29h range for more row volume (a legitimate choice, given the
window is already large — see Row Volume below), the report MUST state the lead as a range, not a
point value, mirroring the existing `EXPERIMENT_LEAD_REALIZABILITY_CAVEAT`'s own discipline of
never letting a score appear without its qualifier attached.

**Warning signs:** any sentence of the form "at the 24-hour horizon" without either the `hour % 6
== 0` filter having been applied, or an explicit "24-29h" range qualifier attached.

### Pitfall 2 (NEW): The two forecast providers (legacy 1h, primary 24h) use DIFFERENT pinned models, and that's correct, not an inconsistency to "fix"

**What goes wrong:** a future reader (or an over-eager refactor) notices `fetch_historical_forecast`
pins `ecmwf_ifs` while `fetch_previous_runs` pins `gfs_seamless`, and "fixes" the inconsistency by
making them match.

**Why it happens:** it looks like an oversight. It is not — see Pattern 1: `ecmwf_ifs`'s
Previous-Runs archive depth (live-verified: null before ~2026-03) is completely different from its
Historical-Forecast/Single-Runs depth (March 2024) the legacy arm relies on. These are two
independently-provisioned archives on Open-Meteo's side; there is no reason to expect the same
model name to have matching depth across different API products, and empirically it does not.

**How to avoid:** document this explicitly in the new provider function's docstring (mirroring
`FORECAST_MODEL_ID`'s own docstring, which already records ITS live evidence) so the "why two
different models" question is answered in the code, not left for the next reader to rediscover via
another live probe.

### Pitfall 3 (NEW): `previous_day1`'s shortwave_radiation does NOT need the leading-null carve-out the Single-Runs API needed

**What goes wrong:** a naive port of `_completeness_check`'s `allow_leading_null_for=
("shortwave_radiation",)` carve-out (built for Single-Runs' index-0 null, per the original
research's Pitfall 3) onto the new Previous-Runs fetch, silently tolerating a null that should not
occur there.

**Why it happens:** the carve-out was needed because Single-Runs' `shortwave_radiation` is null at
the run's OWN index 0 (the analysis step, before any forecast lead has elapsed) — a property of
that specific product's index-0 semantics.

**Live-verified this session:** a Previous-Runs request for `shortwave_radiation_previous_day1`
over a 48-hour window (AUSTIN, 2026-09-20/21) returned **zero nulls** at any index, including index
0 (`[112.0, 0.0, 0.0, 0.0, 0.0, ...]` — the zeros are physically correct nighttime GHI, not nulls).
`previous_day1` values are never analysis-step values (they always come from a run already 24+
hours old, well past that run's own index-0), so the carve-out this project's existing code needed
for Single-Runs simply does not apply here.

**How to avoid:** call `_completeness_check` with `allow_leading_null_for=()` (the default) for
`fetch_previous_runs` — do not port the Single-Runs carve-out reflexively. If a future live check
finds a null anywhere in a `previous_dayN` array, that is a genuine completeness failure and should
raise, not be silently tolerated.

### Pitfall 4 (NEW): Arm 5's "ml" reference model has no clean path to a 24-hour target without touching a global config constant

**What goes wrong:** the planner assumes arm 5 ("reference: current `'ml'` model, refit on
train+val only") can be scored at the 24h primary lead the same way it was scored at the 1h legacy
lead — by simply pointing `forecast_training.build_training_matrix` at the new frame.

**Why it happens:** `build_training_matrix` reads `config.FORECAST_HORIZON_MINUTES` (currently
`60.0`) directly as a module-level global, converts it to a row-count via a fixed hourly-cadence
assumption, and shifts the target by that many rows
[VERIFIED: backend/forecast_training.py:309-325, `horizon = pd.Timedelta(minutes=config.
FORECAST_HORIZON_MINUTES)`... `target_values = indexed["dlr_amps"].shift(-horizon_rows).to_numpy()`].
There is no parameter to override this per-call; the only way to get a 24-hour target shift from
this exact function is to temporarily monkeypatch the global config constant, which this project's
own centralization discipline (`backend/config.py`'s "every tunable lives here" contract) argues
against doing casually, and which risks contaminating any OTHER concurrent use of the constant in
the same process.

**How to avoid:** the planner should decide (Open Questions #2) between (a) a small, parallel
target-shift helper in the experiment harness itself, parameterized by `horizon_hours`, reusing
`ampacity_forecast.build_ml_features` for X (that function is horizon-agnostic — it only builds
LAG features, unaffected by the target horizon) but NOT reusing `build_training_matrix` for y, or
(b) adding an explicit `horizon_minutes` parameter to `build_training_matrix` itself as a small,
additive, default-preserving change (default stays `config.FORECAST_HORIZON_MINUTES`, so the
production trainer's call site is unaffected) — the D-03-style "additive, default-preserving
refactor with an equality gate" pattern this phase already used twice (thermal_model,
forecast_training) applies cleanly here too.

**Warning signs:** an arm-5 MAE score that looks suspiciously close to the 1-hour-lead legacy
arm's magnitude — a signal the target was still shifted by 1 row rather than 24.

## Code Examples

### Live-verified: the Previous Runs API's response envelope (same shape as the other two forecast endpoints)

```
# previous-runs-api.open-meteo.com/v1/forecast?...&models=gfs_seamless
{"latitude":30.269146,"longitude":-97.75338, ...,
 "hourly_units":{"time":"iso8601","wind_speed_10m_previous_day1":"m/s"},
 "hourly":{"time":["2026-09-20T00:00", ...],
           "wind_speed_10m_previous_day1":[2.53,2.01,1.63, ...]}}
```

Same offset-free ISO time strings, same `hourly_units` echo shape as the Archive and
Historical-Forecast endpoints — `HOURLY_TO_PIPELINE`'s BASE variable names (`temperature_2m`,
`wind_speed_10m`, etc.) still apply, just with `_previous_dayN` appended to each requested
`hourly` parameter name. The RETURNED key in the JSON also carries the `_previous_dayN` suffix
(it is not stripped), so the new provider's column-mapping step needs a small suffix-stripping
transform before reusing `HOURLY_TO_PIPELINE`'s lookup — e.g. `key.removesuffix(f"_previous_day
{previous_day}")` before the `HOURLY_TO_PIPELINE.get(...)` call.

### Live-verified: full-window single-request fetch (row volume answer)

```python
# One HTTP request, no batching limit encountered:
#   start_date=2024-01-20, end_date=2026-09-28 (yesterday at research time)
#   5 variables (temperature_2m, wind_speed_10m, wind_direction_10m,
#                shortwave_radiation, relative_humidity_2m), each _previous_day1
# Result: HTTP 200, 957,624 bytes, 23,592 rows, 0 nulls in any variable, 7.24s.
```

### Live-verified: the exact stitching cross-check recipe (reproducible)

```bash
# The two calls that established Pattern 2. Run for each of the four six-hourly
# cycles and diff the six hours each run covers.
curl -s -G "https://previous-runs-api.open-meteo.com/v1/forecast" \
  --data-urlencode "latitude=30.2711" --data-urlencode "longitude=-97.7437" \
  --data-urlencode "start_date=2026-09-20" --data-urlencode "end_date=2026-09-20" \
  --data-urlencode "hourly=wind_speed_10m_previous_day1" \
  --data-urlencode "wind_speed_unit=ms" --data-urlencode "timezone=UTC" \
  --data-urlencode "models=gfs_seamless"

curl -s -G "https://single-runs-api.open-meteo.com/v1/forecast" \
  --data-urlencode "latitude=30.2711" --data-urlencode "longitude=-97.7437" \
  --data-urlencode "hourly=wind_speed_10m" \
  --data-urlencode "wind_speed_unit=ms" --data-urlencode "timezone=UTC" \
  --data-urlencode "run=2026-09-19T00:00" --data-urlencode "models=gfs_seamless" \
  --data-urlencode "forecast_days=2"
```

### Carried-over, still-valid code from the original research (unchanged, already implemented)

The wind u/v decomposition (`wind_vector.to_uv`/`from_uv`), the convective-heat-loss extraction
(`thermal_model.convective_heat_loss`/`natural_convection`/`q_conv_override`), the
`corridor_weakest_link` extraction, the estimator-dictionary convention
(`WIND_CORRECTION_ESTIMATORS`-style zero-argument-factory dicts), and the network-mocking
conventions (`_FakeResponse`/`_mock_get`/cross-module `monkeypatch.setattr`) are **all already
implemented in the repo** (confirmed by direct read this session — `backend/wind_vector.py`,
`backend/thermal_model.py:104-190`, `backend/forecast_training.py:112-170`). See the original
research's "Code Examples" section for the full verbatim listings — not reproduced a second time
here since the code itself, not a doc copy, is now the source of truth.

## Runtime State Inventory

**[CARRIED OVER, unchanged]** — same conclusions as the original research: this phase's D-03
changes are additive-only; the only "runtime state" consideration is the module-level
`ampacity_forecast._MODEL_CACHE` poisoning risk if the experiment ever calls
`_load_corridor_model` (still must not, for arm 5's refit-from-scratch requirement, now doubly true
since arm 5's target-shift also needs to differ from production — see Pitfall 4). Re-verify at plan
time that no new code path calls `_load_corridor_model`.

## Environment Availability

**[UPDATED for D-04]**

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `previous-runs-api.open-meteo.com` | PRIMARY forecast archive (24h lead) | ✓ | live HTTP 200, `models=gfs_seamless`, archive starts 2024-01-20 (all 4 project cities, live-verified) | none needed — this is now the primary path |
| `single-runs-api.open-meteo.com` + `models=gfs_seamless` | one-time stitching verification (Pattern 2) | ✓ but SHALLOW | live-verified reachable back to at least 2026-06-01; a probe to 2025-12-01 returned HTTP 400 (archive boundary) | cannot be used as a wide historical verification tool the way it was for the 1-hour ecmwf_ifs gate — the one-time hand-verification in Pattern 2 already captured what's needed; do not design a `--days 30` style sampler expecting depth back to 2024 |
| `historical-forecast-api.open-meteo.com` + `models=ecmwf_ifs` | legacy 1-hour curiosity arm only | ✓ | unchanged from original research | Previous Runs API (now primary) |
| `archive-api.open-meteo.com` | "truth" weather, both arms | ✓ | unchanged, already in production use | — |
| All other dependencies (`pandas`, `numpy`, `scikit-learn`, `requests`, `pytest`) | everything | ✓ | unchanged from original research | — |

**Missing dependencies with no fallback:** none.

**Request-volume budget, updated:**

| Purpose | Requests | Note |
|---|---|---|
| Previous Runs archive, full window (2024-01-20 → yesterday), 5 vars | **4** (1 per city) | live-measured: ~958 KB/city, 7.2s, zero nulls |
| Truth archive, same window | 4-8 (depending on chunking strategy) | reuse `open_meteo_provider.fetch_open_meteo`'s existing per-year or per-window chunking |
| One-time stitching verification (Pattern 2) | ~8-16 | 4 six-hourly cycles × 1-2 cities × 1-2 dates; this is a documented one-time hand-verification, not a repeated gate |
| Legacy 1-hour arm (unchanged) | ~340 | see original research |
| **Total** | **≈ 360-380** | still comfortably inside a free tier; warm once, cache to CSV per the existing `FORECAST_EXPERIMENT_CACHE_DIR` convention |

## Validation Architecture

**[UPDATED for D-04]** — same framework (`pytest` 9.0.3, `pytest.ini` config) as the original
research. New/changed rows for Waves 2-5:

### Phase Requirements → Test Map (delta from original)

| Obligation | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| D-04 provider (NEW) | `fetch_previous_runs` request carries `models=gfs_seamless` (NOT `ecmwf_ifs`), correct `_previous_dayN` suffix handling | unit (recorder) | `pytest backend/tests/open_meteo_forecast_provider_test.py -x -q` | ❌ new tests needed |
| D-04 provider (NEW) | `_completeness_check` called with `allow_leading_null_for=()` (no carve-out) for `fetch_previous_runs` — Pitfall 3 | unit | same | ❌ new test needed |
| D-04 stitching (NEW) | A synthetic-data test proving only `hour % 6 == 0` rows are treated as exact-24h-lead; the other 5 hours in each block are excluded or labelled with their true 25-29h lead | unit | new test file or extend `forecast_leadtime_calibration_test.py` | ❌ new test needed |
| D-04 anchor generalization (NEW) | `anchored_pair_frame(..., lead_hours=24)` produces an anchor gap of exactly 24h on every scored row; `anchored_pair_frame(..., lead_hours=1)` (legacy) still produces exactly 1h — a regression test that the generalization didn't break the legacy arm | unit | `pytest backend/tests/forecast_experiment_test.py -x -q` | ❌ new tests needed; extend existing file |
| D-04 persistence correctness (NEW) | The 24h persistence arm's anchor is built from `datetime_utc - 24h` directly, NEVER via `ampacity_forecast.backtest_residuals`/`_point_forecast` (Anti-Pattern above) | unit (monkeypatch to assert non-call, or a direct value comparison against a hand-computed 24h-shifted series) | same | ❌ new test needed |
| D-04 arm-5 horizon (NEW) | Arm 5's target is shifted by 24 rows (24h at this project's hourly cadence), not `config.FORECAST_HORIZON_MINUTES`'s current 60-minute/1-row default | unit | new test in whichever module implements the fix from Pitfall 4 | ❌ new test needed |

### Sampling Rate

**[CARRIED OVER, unchanged]** — per-task-commit quick run, per-wave-merge full suite, phase-gate
full suite plus a hand-transcribed live-network run. Unchanged by D-04.

### Wave 0 Gaps (delta from original — original Wave 0 gaps already closed by Plan 03-01)

- [ ] `fetch_previous_runs` tests in `backend/tests/open_meteo_forecast_provider_test.py`
- [ ] Stitching-verification synthetic-data test (new file, or extend
      `forecast_leadtime_calibration_test.py` with a clearly-separated "24h primary" section)
- [ ] `anchored_pair_frame`/`assert_exact_lead`/`filter_to_exact_lead` generalization tests in
      `backend/tests/forecast_experiment_test.py`
- [ ] Arm-5 24h-target-shift tests, location TBD per Pitfall 4's chosen design (a) or (b)
- [ ] New config constants (`PREVIOUS_RUNS_MODEL_ID`, `FORECAST_EXPERIMENT_24H_LEAD_FILTER_
      REMAINDER`) added to `backend/config.py`, following the existing block's heavy
      inline-justification-comment convention

## Security Domain

**[CARRIED OVER, unchanged]** — the original research's ASVS category analysis (V4 path traversal
via `{corridor}`-templated paths, V5 input validation via `PIPELINE_SCHEMA` range checking plus the
null-completeness gate, no new credentials, no new cryptography) applies identically to the new
Previous Runs endpoint — it is the same unauthenticated, base-URL-as-fixed-constant provider family
as the other two forecast endpoints. The one new consideration: the new `PREVIOUS_RUNS_MODEL_ID`
constant must follow the SAME "fixed constant, never built from caller input" discipline
`FORECAST_MODEL_ID` already follows [VERIFIED: backend/open_meteo_forecast_provider.py:62-64,
`Each is, like open_meteo_provider.OPEN_METEO_ARCHIVE_BASE, a fixed constant -- never built from
caller input"`].

## State of the Art

**[UPDATED for D-04]**

| Old Approach (pre-D-04) | Current Approach (post-D-04) | When Changed | Impact |
|--------------------------|-------------------------------|---------------|--------|
| 1-hour idealized lead via Historical-Forecast bulk API + calibration gate, as PRIMARY | 24-hour realizable lead via Previous Runs API, as PRIMARY; 1-hour arm demoted to a labelled curiosity | D-04, 2026-09-29 (same day the bit-identity finding surfaced) | Solves the bit-identity problem; trades a smaller, harder-won 1h window for a much larger 24h one, at the cost of a genuinely harder-to-beat persistence baseline (Pattern 4) |
| "No calibration gate needed at all" (D-04's own framing) for the 24h arm | A lightweight, analytically-grounded verification IS still needed (Pattern 2) | This refresh, 2026-09-29 | Corrects D-04's own text — the underlying "never trust the vendor's stated lead" discipline still applies, just at a smaller scale than the 1h gate |
| `FORECAST_MODEL_ID = "ecmwf_ifs"` as the one forecast-model constant | A SECOND constant, `PREVIOUS_RUNS_MODEL_ID = "gfs_seamless"`, is required for the Previous-Runs endpoint | This refresh | The two endpoints' archive depths for the "same" model name are unrelated; do not assume portability of a model choice across Open-Meteo API products |

Everything else in the original research's State of the Art table (reanalysis-as-forecast-stand-in,
forecast-the-drivers-not-the-target framing, u/v decomposition) is unchanged by D-04.

## Assumptions Log

**[UPDATED for D-04 — new assumptions only; original A1-A7 are carried over unchanged, scoped now
to the legacy 1-hour arm]**

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| B1 | `gfs_seamless`'s Previous-Runs archive start (2024-01-20) and the four-cities-identical-to-best_match finding are stable and won't silently change (mirrors original A2's "Open-Meteo won't change the stitching depth" concern, applied to the new endpoint) | Pattern 1, Pattern 2 | Low near-term. Mitigated the same way A2 was — by keeping the live-evidence comments in the code so a re-run of the same probes is cheap. |
| B2 | The `hour % 6` stitching mechanism (Pattern 2) generalizes across the FULL 2024-01-20-to-present window, not just the 2 cities/2 dates sampled this session | Pattern 2 | Moderate. Only 2 cities and 2 dates were checked (bounded by Single-Runs/`gfs_seamless`'s own shallow depth, which only reaches back to ~2026-06). Unlike the 1-hour ecmwf_ifs case, there is no way to cross-verify against Single-Runs for dates before ~2026-06 with this model — the stitching claim for 2024-2025 rests on the MECHANISM being general (any six-hourly model's bulk/previous-runs products are built the same way) rather than a direct historical cross-check. The lightweight verification test (Pitfall 1) should be built with this limitation explicitly noted. |
| B3 | Diurnal-persistence-strength reasoning (Pattern 4) — that 24h persistence is a genuinely strong baseline because it's diurnally self-aligned | Pattern 4 | Low-moderate. This is a reasoned inference from the verified 24h lag construction, not an independently measured fact (e.g. via an actual MAE comparison against a shorter-horizon persistence). Does not change any design decision, only expectation-setting for the eventual result's interpretation. |
| B4 | `previous_day1`'s response key includes the `_previous_dayN` suffix verbatim (not stripped server-side) for every variable, not just the ones spot-checked (`wind_speed_10m`, `temperature_2m`, `shortwave_radiation`, `wind_direction_10m`, `relative_humidity_2m`) | Code Examples | Low. All 5 pipeline variables were checked in the full-window fetch this session; the suffix was present and consistent for all 5. |

## Open Questions

**[NEW, specific to this refresh — supersedes the original document's Open Questions #1-2, which
were about the 1-hour arm and are now resolved/scoped to the legacy path]**

1. **Exact-lead filter (`hour % 6 == 0`) vs. broader "24-29h" unfiltered window for the primary
   arm.**
   - What we know: filtering to the exact lead leaves ~3,932 scored rows/city over the full window
     — still 2.7x the legacy arm's final row count. Not filtering keeps all ~23,592 rows/city but
     means every score is measuring a blend of 5 distinct lead times.
   - What's unclear: whether the phase's audience needs a POINT lead claim (favoring the filter) or
     values the extra statistical power enough to accept a RANGE claim (favoring no filter, with
     honest range labelling).
   - Recommendation: filter (mirrors the phase's own established discipline from the 1-hour arm --
     an exact, verified lead is the phase's whole methodological point), but this is a real decision
     for the planner/user, not something to default silently.

2. **Arm 5's 24-hour target-shift implementation: parallel helper vs. `build_training_matrix`
   parameter (Pitfall 4).**
   - What we know: the production function's horizon is a global config read, not a parameter.
   - What's unclear: whether a small additive `horizon_minutes` parameter on
     `build_training_matrix` (option (b)) is preferable to a fully separate helper (option (a)) --
     this is a real D-03-style "additive, default-preserving refactor" judgment call.
   - Recommendation: option (b), following the SAME pattern D-03 already used twice this phase
     (thermal_model's `q_conv_override`, forecast_training's `corridor_weakest_link` extraction) --
     but the planner should verify `build_training_matrix`'s only other call site
     (`forecast_training.main`/`_run_bakeoff`) is unaffected by an additive default-preserving
     parameter before locking this in.

3. **Does the lightweight stitching verification (Pitfall 1's recommendation) belong in a new
   module, or as an addition to the existing (legacy-scoped) `forecast_leadtime_calibration.py`?**
   - What we know: the existing module's docstring, `LEAD_RULE_DESCRIPTION` constant, and
     `_MATCH_RATE_FLOOR`/tolerance machinery are all written specifically about the `ecmwf_ifs`
     1-hour case.
   - What's unclear: whether extending that module (renaming/re-scoping it as a general
     "stitching verification" tool covering both leads) or adding a small, separate, 24h-specific
     check is cleaner.
   - Recommendation: the planner should read the module's full current content (not excerpted
     here) before deciding — this is a real design judgment, not resolvable from this document
     alone.

4. **Project-instruction compliance: `ACKNOWLEDGEMENTS.md`.** Unchanged from the original —
   `03-01-SUMMARY.md` confirms this was already updated once this phase; the planner should include
   a follow-up update for whatever AI-assisted diff Waves 2-5 produce, per the user's standing
   memory directive.

## Project Constraints (from CLAUDE.md)

**[CARRIED OVER, unchanged]** — no `./CLAUDE.md` or `./.claude/CLAUDE.md` exists in this
repository. The same three de-facto constraints the original research identified
(`requirements.txt`'s single-source-of-truth header, `REQUIREMENTS.md`'s fail-safe-contract
Out-of-Scope line, `backend/config.py`'s centralization discipline) apply identically to the new
work — the two new constants this refresh recommends (`PREVIOUS_RUNS_MODEL_ID`,
`FORECAST_EXPERIMENT_24H_LEAD_FILTER_REMAINDER`) both belong in `config.py`/the provider module
following that same discipline, not as inline literals.

---

# Legacy 1-Hour Arm — Original Research, Preserved for the Curiosity Disposition (D-04)

Everything from this heading to the end of the document is the ORIGINAL (2026-09-28) research,
preserved verbatim because D-04 keeps the 1-hour arm's code in the repo as a documented, labelled,
non-primary curiosity. Nothing below this heading was re-verified this session; it describes the
1-hour design that is now SECONDARY, not primary. Do not use anything below this heading to plan
Waves 2-5's PRIMARY work — use the sections above.

The original document's full content — its Summary, Standard Stack detail, all four Architecture
Patterns (provider-adapter cloning, the deterministic `hour % 6` rule, u/v decomposition, the
Previous-Runs-as-sensitivity-ladder pattern that correctly anticipated today's pivot), all seven
Pitfalls, the full Code Examples section, Runtime State Inventory, Environment Availability,
Validation Architecture, Security Domain, State of the Art, Assumptions Log (A1-A7), and Sources —
is unchanged and remains available in this phase's git history at the commit that introduced the
original `03-RESEARCH.md` (`docs(03): research phase domain`, 2026-09-28) and in
`03-01-SUMMARY.md`/`03-01-BOUNDARY-INVESTIGATION.md`, which document its execution, the two window
corrections, and the bit-identity finding that triggered D-04. It is not reproduced a second time
in this file to avoid two competing copies of the same historical record drifting apart — the git
history and the two summary/investigation documents ARE that record.

## Sources (this refresh, in addition to the original document's Sources section)

### Primary (HIGH confidence)

- Live HTTP probes this session (~40 requests) against `previous-runs-api.open-meteo.com`,
  cross-referenced against `single-runs-api.open-meteo.com` and `archive-api.open-meteo.com` —
  covering: archive-start bisection (all 4 project cities), model-pinning comparison
  (`best_match`/`gfs_seamless`/`ecmwf_ifs`/`ecmwf_ifs025`/`gfs_global`/`icon_seamless`), bit-identity
  refutation (2 cities, 6 dates, 2 variables), the six-hour-stitching cross-check (2 cities, 2
  dates, 2 variables, all 4 daily cycles), multi-day batching, `previous_day1..8` ceiling,
  null-completeness at variable boundaries, and a full-window single-request volume test. Raw
  outputs pasted inline above.
- Direct `Read` of `backend/open_meteo_forecast_provider.py` (all 434 lines), `backend/
  forecast_experiment.py` (all 474 lines), `backend/experiment_splits.py` (all 118 lines),
  `backend/wind_vector.py` (all 98 lines), `backend/thermal_model.py` (all 260 lines), `backend/
  forecast_training.py` (all 677 lines), `backend/config.py` (relevant sections), `backend/
  ampacity_forecast.py:282-465`, `backend/tests/forecast_experiment_test.py` (all 317 lines),
  `backend/tests/open_meteo_forecast_provider_test.py:1-90`, this session.
- Direct `Read` of `03-CONTEXT.md`, `03-01-SUMMARY.md`, `03-01-BOUNDARY-INVESTIGATION.md` (all in
  full), this session.

### Secondary (MEDIUM confidence)

- https://open-meteo.com/en/docs/previous-runs-api — `previous_dayN` semantics, archive start date
  ("Most models are archived from January 2024"), cross-confirmed by live bisection to precisely
  2024-01-20 for `gfs_seamless`/`best_match`. Its "the value predicted 24 hours before valid time"
  claim is TRUE ONLY for six-hourly-cycle hours — refuted as a universal claim by this session's
  own live stitching cross-check (Pattern 2); this is a case where the live evidence overrides the
  doc's own wording, not a case of independent confirmation.

## Metadata

**Confidence breakdown (this refresh):**

- Previous-Runs API mechanics (archive start, model pinning, batching, null behavior): **HIGH** —
  every claim live-probed this session with raw output captured above.
- The six-hour stitching finding (Pattern 2): **HIGH** — bit-for-bit exact match against an
  independently-fetched Single-Runs value, for 2 cities, 2 variables, all 4 daily cycles, 0
  exceptions across 96 compared hour-cells.
- Bit-identity refutation (Summary point 1): **HIGH** — 2 cities, 6 dates, 2 variables, ~140+
  compared hours, zero exact matches.
- Row volume estimate: **HIGH** — a single live full-window fetch, not extrapolated.
- Diurnal-persistence-strength reasoning (Pattern 4): **MEDIUM** — reasoned, not independently
  benchmarked.
- Generalization of the stitching mechanism to 2024-2025 dates outside Single-Runs' shallow
  `gfs_seamless` reach (Assumption B2): **MEDIUM** — mechanism-based inference, not a direct
  historical cross-check for those years.

**Research date (this refresh):** 2026-09-29.
**Valid until:** 2026-10-13 for the Previous-Runs findings (mirrors the original document's
~2-week validity window for Open-Meteo API behavior, since rolling archive boundaries and possible
future re-pinning of `best_match` are both live risks the original document already flagged for the
sibling endpoints). The in-repo code claims (carried-over sections) remain valid on the original
document's own timeline.
