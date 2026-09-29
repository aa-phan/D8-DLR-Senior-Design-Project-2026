# Phase 3: Ampacity Forecast Correction Experiment - Research

**Researched:** 2026-09-28
**Domain:** NWP forecast archives (Open-Meteo), IEEE 738 heat-balance decomposition, scikit-learn
offline experiment harnesses, chronological held-out evaluation
**Confidence:** HIGH for the API layer and the in-repo code layer (both live-probed / directly
read this session); MEDIUM for the operational-latency framing; LOW for nothing load-bearing.

## Summary

The phase as scoped in `03-CONTEXT.md` is buildable, but **three of its load-bearing premises are
wrong or incomplete**, and one of them changes the design materially.

First, the good news: the Open-Meteo **Historical Forecast API's bulk mode, pinned to
`models=ecmwf_ifs`, has a fully deterministic and now-measured lead-time structure.** A live
cross-check this session showed the bulk product's values are **bit-identical** to the Single-Runs
API's values at forecast leads 0-5 h and diverge at lead >= 6 h, across three cities and three
seasons. The bulk product stitches exactly the first six hours of each six-hourly ECMWF IFS run.
That makes `lead_hours = valid_time.hour % 6` an exact, verifiable rule — not a statistical
estimate. The CONTEXT's `forecast_leadtime_calibration.py` therefore becomes a *verification* of a
deterministic mapping on a sample, not a distribution-estimation exercise, and it can and should
still be a hard gate. The measured p05 lead is **0 h**, so `assert_supports_horizon(60min)` fails
as the CONTEXT anticipated — but the resolution is cleaner than any of its three scoped
contingencies: filter to valid times where `hour % 6 == 1`, which yields an *exactly* 1-hour lead,
4 rows/day/city (~1,460/year/city, ~4,380 over the existing 3-year window). This is CONTEXT option
(c), promoted from a probabilistic filter to a deterministic one.

Second, the corrections. (a) `03-CONTEXT.md`'s verified-fact "No fixed train/val/test split exists
anywhere in this repo currently" is **false** — `anomaly_training.chronological_split` (lines
394-438) is a fixed, time-ordered, never-shuffled (fit, holdout) split with its own validation
guards and a `config` fraction. The new `experiment_splits.py` should extend that function's shape
to three ways and to calendar dates, citing it, not be written as greenfield. (b) The Single-Runs
`run=` parameter is **not** free-form ISO-8601: `2026-09-25T00:00:00Z` returns HTTP 400
`Bad Request`; only `YYYY-MM-DDTHH:MM` (no seconds, no `Z`) works. (c) Single-Runs depth is model-
dependent: `ecmwf_ifs025` only reaches ~2026-04-02, while `ecmwf_ifs` (HRES 9 km) reaches
2024-03-14 — the CONTEXT's "~March 2024+ for the best model" is right only for `ecmwf_ifs`.

Third, the thing nobody has said out loud: **no Open-Meteo product can supply an operationally
realizable 60-minute-ahead NWP forecast, and no run cadence finer than 6-hourly exists in the
archive** (HRRR included — Open-Meteo archives only its 00/06/12/18 extended cycles). Global models
carry a 4-6 h dissemination delay after initialization. A "1-hour lead" row taken from the 00Z run
is a *physically unobtainable* forecast: at 01:00 UTC the 00Z run has not been disseminated. The
experiment can still be run and is still worth running — but every output surface must state that
the raw-forecast and ML-corrected arms are scored at an *idealized* lead that a live system could
not have had, exactly as the oracle arm is labeled non-forecast. Otherwise the phase repeats, at
one level up, the honesty failure it was created to avoid.

**Primary recommendation:** Pin `models=ecmwf_ifs` on the Historical Forecast bulk API, fetch the
full 2023-01-01→2025-12-31 window in **one request per city** (verified: 26,304 rows, ~1.07 MB,
zero nulls — an exact 1:1 row match with Phase 1's existing Archive-derived training frame), derive
lead deterministically as `hour % 6`, verify that rule against Single-Runs `models=ecmwf_ifs` on a
stratified sample as the hard gate, score the 60-minute arms only on the `hour % 6 == 1` subset,
and label the realizability caveat everywhere.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01: Use Open-Meteo's Historical Forecast API (bulk date-range mode) as the forecast archive,
gated by an empirical lead-time calibration step — never trust the product's stated lead time.**
Live-confirmed during this discussion: no historical forecast archive with real issue-time/
valid-time separation exists anywhere in this codebase (`v1.0-ROADMAP.md` explicitly flags this
as absent). Open-Meteo's Historical Forecast API (`historical-forecast-api.open-meteo.com`)
archives real stitched-together past model-run output (ECMWF/GFS/ICON), several years deep, free,
already the provider family this project uses — genuinely a forecast product, not reanalysis. But
its bulk mode's `forecast_hours`/`past_hours` params are live-confirmed **mutually exclusive**
with `start_date`/`end_date` — it returns "the first few hours of each successive run stitched
into a continuous series," an approximately-short-lead product with an *unmeasured* effective lead
time, not a user-pinned exact lead. A separate Single-Runs API (`single-runs-api.open-meteo.com`,
`&run=<ISO8601>`) gives exact, unambiguous lead times but only reaches back to ~March 2024 and
requires one call per model run (no batching).
**Resolution:** use the bulk product for the main experiment's data volume, but build a
calibration step (`forecast_leadtime_calibration.py`) that samples the Single-Runs API over the
overlap window and empirically measures the bulk product's actual effective lead-time
distribution before any approach is scored. This is a **hard gate** (`assert_supports_horizon`),
not an assumption: if the measured p05 lead can't support a 60-minute claim, the phase does not
silently proceed — see the contingency in Open Questions. — **Reversibility:** reversible — the
calibration step is disposable tooling; if a better forecast-archive source appears later, only
the fetch layer changes, not the experiment's approach implementations.

- **Rejected alternative — wait and collect forward-only.** Truest to a strict "never substitute"
  reading, but means no real backtest is possible for months. Rejected as impractical for this
  phase's timeline; the calibration-gate approach gets a real, honestly-characterized backtest now.
- **Rejected alternative — Single-Runs-only.** Cleaner (exact lead time, zero ambiguity) but limited
  to ~18 months of history and requires substantially more collection engineering (no batching).
  Deferred to a future phase (see Open Questions) if the bulk product's calibration gate fails.

**D-02: Build and run the full seven-approach comparison in this phase; explicitly stop and
report if nothing beats persistence rather than building probabilistic/regime/fusion layers on
top of a losing result.** The full ask (4+ approaches, oracle diagnostic, probabilistic
evaluation, regime analysis, multi-source fusion, production integration) is too large for one
phase without wasting effort on machinery built atop an unproven base.
**Resolution — this phase covers only:**
0. Persistence (reuse `ampacity_forecast.forecast_ampacity(method="naive")` unchanged)
1. NWP-wind-delta baseline (observed wind + forecast wind delta, other inputs held at
   latest-observed)
2. Raw forecast → IEEE 738 (no correction)
3. ML-corrected wind → IEEE 738 (u/v decomposition; linear regression, then gradient boosting)
4. ML-corrected cooling → heat balance (corrects the convective heat-loss term directly)
5. Reference: current `"ml"` model, **refit on train+val only** (the production artifact was
   trained on years overlapping this experiment's test range and would leak if reused as-is)
6. Oracle diagnostic (observed future wind substituted in; explicitly labeled non-forecast in
   every output surface — never presented as a competing method)

All seven scored on **identical held-out chronological test timestamps** — a fixed calendar
train/val/test split, which is new infrastructure (every existing eval mechanism in this repo,
`backtest_residuals` and `TimeSeriesSplit`, is walk-forward-only, not a true held-out split).
— **Reversibility:** reversible — a follow-up phase can add probabilistic/regime/fusion work or
production wiring without touching this phase's experiment code, only extending it.

**D-03: No existing runtime file changes behavior in this phase.** New code lives in new files
(`backend/open_meteo_forecast_provider.py`, `backend/wind_vector.py`,
`backend/experiment_splits.py`, `backend/forecast_leadtime_calibration.py`,
`backend/forecast_experiment.py`), following the repo's own `forecast_training.py`/
`anomaly_training.py` convention (standalone offline script imports the runtime modules, never
the reverse). Two existing files get **additive, default-preserving** refactors, each gated by an
equality test against pre-refactor output:

- `backend/thermal_model.py`: extract `convective_heat_loss`/`natural_convection` from the
  existing `Q_cf`/`Q_cn`/`max()` block (verified by direct read, ~lines 152-161); add an optional
  `q_conv_override=None` keyword to `ieee738_ampacity` (new param, default `None`, zero existing
  call-site changes — `T_c` is always `conductor.T_max`, a fixed constant, so the extracted
  function only needs `T_amb_c`/`wind_perp_ms` as live inputs).
- `backend/forecast_training.py`: extract the inline weakest-link min()-over-two-cities block
  (~lines 147-189) into a shared `corridor_weakest_link(...)` helper, reused by both the
  production trainer and the new experiment harness.

If the equality gate can't be made to pass for either extraction, fall back to a clearly-commented
duplicate in the new experiment file rather than force it — logged as debt, not silently done.
— **Reversibility:** the `thermal_model.py` change is a one-way door in the loose sense that
reverting it later means re-deriving the extraction; but it's purely additive (no removed
capability) so the practical reversal cost is low. Flagged for a `checkpoint:decision` if
`--no-reversibility-gates` is not set.

### Claude's Discretion

No `## Claude's Discretion` section exists in `03-CONTEXT.md`. The equivalent discretion surface is
its `## Open Questions` block, reproduced here because the planner must resolve each one:

- **Lead-time gate contingency.** If the calibration step's measured p05 lead can't support a
  60-minute claim, three options were scoped (not chosen — pick explicitly if it comes up):
  (a) anchor pulls via Single-Runs directly on a stratified subsample (shrinks test set, no
  batching); (b) relabel the horizon to the bulk product's measured native lead, stated plainly in
  every output; (c) filter to rows whose assumed issue time <= T (preserves 60-min framing, needs
  its own characterization of what gets filtered). Leaning (b) primary + (c) as a sensitivity check
  if needed, but not locked in — the planner/executor should decide once real numbers are in hand.
- **`ieee738_ampacity` override shape.** Keyword on the existing function (`q_conv_override=None`)
  vs. a separate `ieee738_ampacity_from_terms(...)`.
- **Approach 4 (ML-corrected cooling) target parameterization.** Predict the level `Q_conv_obs`
  directly, or a scale-free log-ratio `log(Q_conv_obs / Q_conv_fc)`? Decide on the validation set.
- **Approach 3 pooling.** One correction model per corridor pooled over both endpoint cities (with
  an endpoint indicator) vs. two per-city models — decide on the validation set.
- **Whether the bulk product's effective lead time is stable or hour-of-day dependent.**
- **Total HTTP request volume budget** for the initial data-warming run.
- **Requirement ID.** Leaning: no new ID needed.
- **Detailed file-level design** was worked out during the chat discussion; treat as a strong
  starting point but verify every code claim against the live repo.

**This research answers five of those eight.** See `## Open Questions` at the end for what remains.

### Deferred Ideas (OUT OF SCOPE)

From `03-CONTEXT.md` `<domain>`:

> Out of scope for this phase: wiring any winning approach into
> `ampacity_forecast.FORECAST_METHODS` (that's a separate future phase, contingent on this one's
> results, and requires its own decision about runtime forecast-fetch fallback behavior);
> probabilistic/quantile evaluation; regime-specific correction models; multi-NWP-source fusion.
> These are explicitly deferred, not silently dropped.
</user_constraints>

<phase_requirements>
## Phase Requirements

**No new requirement ID is warranted.** This is confirmed against REQUIREMENTS.md's own conventions,
not assumed:

`REQUIREMENTS.md` is a **capability-commitment** register, not a work register. Every one of its
four IDs is phrased as a shipped capability ("An ML model ... forecasts ampacity ahead of real
time, dropped in behind `ampacity_forecast.py`'s existing `forecast_ampacity` function signature")
[VERIFIED: .planning/workstreams/ml-modeling/REQUIREMENTS.md:20-24]. Its `## Traceability` table has
exactly four rows and its `**Coverage:**` block reads `v1.3 requirements: 4 total / Mapped to
phases: 4 / Unmapped: 0` [VERIFIED: REQUIREMENTS.md:53-64] — a closed set, all four marked
`Complete`.

D-03 locks this phase to **zero behavior change in any existing runtime caller**. A phase that
changes no runtime capability cannot discharge a capability commitment, so adding an ID would
create a fifth row that the phase is structurally unable to satisfy, and would break the
`Unmapped: 0 ✓` invariant on the way in.

| ID | Description | Research Support |
|----|-------------|------------------|
| *(none — see above)* | Methodology investigation of FCST-01's shipped `"ml"` method | The whole of this document |

**Relationship to existing IDs.** This phase investigates the open recommendation left by
**FCST-02**'s validation record, which explicitly declines to resolve it:

> "Whether `"ml"` should be recommended as the production-preferred method at all at the current
> 60-minute horizon, given that the measured evidence in this document does not currently support
> that recommendation — this document intentionally does not resolve that recommendation; it
> records the evidence a future decision would need."
> [VERIFIED: docs/data-science/decisions/forecasting_model.md:207-210]

The planner should add a follow-up line to `forecasting_model.md`'s Open Questions pointing at this
phase's output record, and should **not** edit REQUIREMENTS.md.
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Forecast-archive HTTP fetch + response validation | Provider adapter (`open_meteo_forecast_provider.py`) | — | The repo already owns exactly one tier for "normalize a weather HTTP source into PIPELINE_SCHEMA columns" (`open_meteo_provider`, `asos_provider`, `tceq_provider`, `nsrdb_provider`); a fifth sibling is the established shape |
| Lead-time verification against Single-Runs | Offline experiment script (`forecast_leadtime_calibration.py`) | Provider adapter | The gate is disposable tooling, not runtime; it consumes two providers and asserts a relationship between them |
| Wind u/v decomposition + recomposition | Pure math module (`wind_vector.py`) | — | Stateless, no I/O, no config — same tier as `thermal_model.perpendicular_wind`, which it must agree with |
| Convective heat-loss term extraction | Physics core (`thermal_model.py`) | — | Already owns `Q_cf`/`Q_cn`/`Q_conv`; splitting the term out anywhere else forks the physics, which the module docstring forbids |
| Fixed calendar train/val/test split | Shared experiment infra (`experiment_splits.py`) | — | Generalizes `anomaly_training.chronological_split`; belongs beside neither trainer since both may use it |
| Per-approach fit + score | Offline experiment harness (`forecast_experiment.py`) | scikit-learn | Mirrors `forecast_training.bakeoff_corridor` / `anomaly_training.corridor_report` |
| Weakest-link corridor reduction | Offline trainer (`forecast_training.py`, extracted helper) | — | D-03's second refactor; currently inline in `corridor_training_frame` |
| Runtime forecast serving | **explicitly NOT this phase** (`ampacity_forecast.py` untouched) | — | D-03 |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pandas` | 2.3.3 | Frame assembly, time indexing, joins | Already pinned [VERIFIED: requirements.txt:23] and used by every backend module |
| `numpy` | 2.4.3 | Vectorized physics + error metrics | Already pinned [VERIFIED: requirements.txt:24] |
| `scikit-learn` | 1.9.1 | `LinearRegression`, `HistGradientBoostingRegressor` for the correction models | Already pinned [VERIFIED: requirements.txt:28]; confirmed installed at 1.9.1 via `.venv/bin/python -c "import sklearn"` this session |
| `requests` | 2.32.5 (installed, **undeclared**) | HTTP for both Open-Meteo endpoints | Used by `open_meteo_provider` [VERIFIED: backend/open_meteo_provider.py:37]; see Pitfall 7 |
| `pytest` | 9.0.3 | Test runner | Already pinned [VERIFIED: requirements.txt:26]; `pytest.ini` sets `pythonpath = backend`, `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py` [VERIFIED: pytest.ini:1-5] |

**No new package is required by this phase.** `LinearRegression` and
`HistGradientBoostingRegressor` both ship in the already-pinned scikit-learn.

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `joblib` | (transitive via scikit-learn) | Estimator persistence | Only if the experiment persists correction models; `forecast_training.persist_corridor_model` is the pattern [VERIFIED: backend/forecast_training.py:444-471] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Historical Forecast bulk + `models=ecmwf_ifs` | Single-Runs API for every anchor | Exact lead by construction, no calibration gate needed — but one HTTP request per (run, city), no batching [VERIFIED: live probe, `start_date` rejected], and depth only to 2024-03-14. At 4 runs/day × 4 cities × 2.5 y that is ~14,600 requests vs. 4. Rejected for volume; retained as the gate's sampling source. |
| Historical Forecast bulk + `models=ecmwf_ifs` | Previous Runs API (`previous_dayN`) | Batched *and* exactly lead-pinned — but the finest granularity is `previous_day1` = 24 h [CITED: open-meteo.com/en/docs/previous-runs-api]. Useless for a 60-min horizon; **highly valuable as a lead-time sensitivity ladder** — see Pattern 4. |
| `models=ecmwf_ifs` | unpinned `best_match` | `best_match` resolves to different domains per location and per API (`best_match` on Single-Runs resolved to `dwd_icon` in a live probe), which destroys the deterministic lead rule. Do not use. |
| `models=ecmwf_ifs` | `models=ncep_hrrr_conus` | HRRR is CONUS-native and would be the physically right choice for Texas — but Open-Meteo archives only its 00/06/12/18 cycles on Single-Runs (live-verified: 01/02/05/07/11Z all return "model run is not available"), so it buys no finer lead than IFS while adding null-padded arrays (49/168 non-null). |

**Installation:** none required — the environment already satisfies this phase.

## Package Legitimacy Audit

This phase installs **no external packages**. All four libraries it uses are already pinned in
`requirements.txt` and already installed in `.venv`, and all were audited in prior phases
(`01-RESEARCH.md` "Package Legitimacy Audit" for scikit-learn per requirements.txt:17-22).

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| pandas 2.3.3 | PyPI | >15 yrs | very high | github.com/pandas-dev/pandas | OK | Already pinned, no change |
| numpy 2.4.3 | PyPI | >15 yrs | very high | github.com/numpy/numpy | OK | Already pinned, no change |
| scikit-learn 1.9.1 | PyPI | >15 yrs | very high | github.com/scikit-learn/scikit-learn | OK | Already pinned + prior-phase audited |
| requests 2.32.5 | PyPI | >14 yrs | very high | github.com/psf/requests | OK | **Installed but missing from requirements.txt** — see Pitfall 7 |

**Packages removed due to [SLOP] verdict:** none — no new package proposed.
**Packages flagged as suspicious [SUS]:** none.

*Age/download figures above are [ASSUMED] from general knowledge; they are not load-bearing because
no install decision rests on them. The load-bearing facts — that each package is already pinned and
already present — are [VERIFIED: requirements.txt:23-28] and, for `requests` and `sklearn`, by
direct interpreter import this session.*

## Architecture Patterns

### System Architecture Diagram

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
   │  │ Open-Meteo Historical Fcst   │  │                                    │
   │  │ historical-forecast-api...   │  │                                    │
   │  │ &models=ecmwf_ifs            │  │                                    │
   │  │ &start_date&end_date (bulk)  │  │                                    │
   │  └──────────────┬───────────────┘  │                                    │
   │   (NEW provider)│                  │                                    │
   │                 ▼                  │                                    │
   │      "FORECAST" weather @ T        │                                    │
   │      lead = T.hour % 6  ───────────┼──┐                                 │
   │                 │                  │  │                                 │
   │                 │   ┌──────────────┴──▼─────────────────────────┐       │
   │                 │   │ HARD GATE: forecast_leadtime_calibration  │       │
   │                 │   │  sample Single-Runs (&run=,&models=       │       │
   │                 │   │  ecmwf_ifs) → assert bulk == run@lead     │       │
   │                 │   │  → assert_supports_horizon(60min)         │       │
   │                 │   │  FAIL ⇒ phase stops / horizon relabelled  │       │
   │                 │   └──────────────┬────────────────────────────┘       │
   │                 │                  │ pass                               │
   │                 ▼                  ▼                                    │
   │     ┌───────────────────────────────────────────┐                       │
   │     │ JOIN on datetime_utc, per endpoint city   │◄──────────────────────┘
   │     │ → paired (forecast, truth) frame          │
   │     │ → FILTER to hour % 6 == 1  (exact 1h lead)│
   │     └───────────────────┬───────────────────────┘
   │                         ▼
   │     ┌───────────────────────────────────────────┐
   │     │ experiment_splits.calendar_split()        │
   │     │ train | val | test   (dates, never shuffled)│
   │     └───────────────────┬───────────────────────┘
   │                         │  identical test timestamps for ALL arms
   │        ┌────────────────┼────────────────┬──────────────┬─────────────┐
   │        ▼                ▼                ▼              ▼             ▼
   │  ┌──────────┐   ┌──────────────┐  ┌───────────┐  ┌───────────┐ ┌──────────┐
   │  │0 persist │   │1 wind-delta  │  │2 raw fcst │  │3 ML-wind  │ │4 ML-cool │
   │  │ naive    │   │ obs+Δfcst    │  │ →IEEE738  │  │ u/v corr  │ │ Q_conv   │
   │  └────┬─────┘   └──────┬───────┘  └─────┬─────┘  └─────┬─────┘ └────┬─────┘
   │       │                │                │              │            │
   │       │                │   wind_vector.to_uv/from_uv ──┘            │
   │       │                │                │                           │
   │       │                ▼                ▼                           ▼
   │       │      thermal_model.perpendicular_wind          thermal_model
   │       │                 └──────┬────────┘            .convective_heat_loss
   │       │                        ▼                              │
   │       │        thermal_model.ieee738_ampacity  ◄──── q_conv_override
   │       │                        │
   │       │        forecast_training.corridor_weakest_link (min over 2 cities)
   │       │                        │
   │       ▼                        ▼              ▼              ▼
   │  ┌──────────────────────────────────────────────────────────────────┐
   │  │ 5 reference: "ml" refit on train+val only (NOT the prod artifact) │
   │  │ 6 oracle: observed future wind  [LABELLED NON-FORECAST]           │
   │  └──────────────────────────┬───────────────────────────────────────┘
   │                             ▼
   │              ┌──────────────────────────────────┐
   │              │ score on identical test rows     │
   │              │ MAE / RMSE / rows / lead / caveat│
   │              │ → JSON report + tracked record   │
   │              └──────────────────────────────────┘
   └──────────────────── no arrow returns to ampacity_forecast.py (D-03) ─────┘
```

### Recommended Project Structure

```
backend/
├── open_meteo_forecast_provider.py   # NEW  Historical Forecast + Single Runs adapters
├── wind_vector.py                    # NEW  u/v decomposition, pure math, no I/O
├── experiment_splits.py              # NEW  calendar train/val/test split
├── forecast_leadtime_calibration.py  # NEW  the hard gate; __main__ entry point
├── forecast_experiment.py            # NEW  7-arm harness; __main__ entry point
├── thermal_model.py                  # EDIT additive: convective_heat_loss / natural_convection
│                                     #      + q_conv_override=None
├── forecast_training.py              # EDIT additive: corridor_weakest_link(...) extraction
└── tests/
    ├── open_meteo_forecast_provider_test.py
    ├── wind_vector_test.py
    ├── experiment_splits_test.py
    ├── forecast_leadtime_calibration_test.py
    └── forecast_experiment_test.py
```

Test files use the `*_test.py` suffix (matches `pytest.ini`'s `python_files` and every existing
file in `backend/tests/`) and live in `backend/tests/`, **not** beside the module.

### Pattern 1: Provider adapter — clone `open_meteo_provider`'s structure, change only the base URL

The Historical Forecast API's response envelope is **byte-for-byte the same shape** as the Archive
API's. Live-verified this session:

```
# historical-forecast-api.open-meteo.com/v1/forecast?...&models=ecmwf_ifs
{"latitude":30.269146,"longitude":-97.75338,"generationtime_ms":45.3,"utc_offset_seconds":0,
 "timezone":"GMT","timezone_abbreviation":"GMT","elevation":167.0,
 "hourly_units":{"time":"iso8601","temperature_2m":"°C","wind_speed_10m":"m/s",
                 "wind_direction_10m":"°","shortwave_radiation":"W/m²",
                 "relative_humidity_2m":"%"},
 "hourly":{"time":["2025-07-01T00:00", ...], "temperature_2m":[26.0,...], ...}}
```

Same offset-free ISO time strings, same `hourly_units` echo, same five variable keys. Therefore
`HOURLY_TO_PIPELINE`, `OPEN_METEO_HOURLY_VARS`, `EXPECTED_HOURLY_UNITS`, the `hourly`/`time`/
length/unit checks, and `_range_check` can all be reused **verbatim**
[VERIFIED: backend/open_meteo_provider.py:50-71, 150-202].

The existing mapping and unit table, quoted verbatim so the new module can be checked against it:

```python
# backend/open_meteo_provider.py:50-58
HOURLY_TO_PIPELINE: dict[str, str] = {
    "temperature_2m": "air_temp",
    "wind_speed_10m": "wind_speed",
    "wind_direction_10m": "wind_direction",
    "shortwave_radiation": "solar_radiation",
    "relative_humidity_2m": "relative_humidity",
}

OPEN_METEO_HOURLY_VARS: tuple[str, ...] = tuple(HOURLY_TO_PIPELINE)
```

```python
# backend/open_meteo_provider.py:65-71
EXPECTED_HOURLY_UNITS: dict[str, str] = {
    "temperature_2m": "°C",
    "wind_speed_10m": "m/s",
    "wind_direction_10m": "°",
    "shortwave_radiation": "W/m²",
    "relative_humidity_2m": "%",
}
```

**When to use:** for the bulk fetch. **Do not** import `open_meteo_provider` and monkeypatch its
`OPEN_METEO_ARCHIVE_BASE` — that constant is documented as "a fixed constant -- never built from
caller input" [VERIFIED: backend/open_meteo_provider.py:43]. Either import the three tables by name
from it (dependency new→existing, matching how `forecast_training` imports `ampacity_forecast`
[VERIFIED: backend/forecast_training.py:6-8]) or restate them with a test asserting equality.

**Required deltas from the Archive adapter:**
1. Base URL constant: `OPEN_METEO_HISTORICAL_FORECAST_BASE = "https://historical-forecast-api.open-meteo.com/v1/forecast"`
2. Add `"models": "ecmwf_ifs"` to `params` — non-optional; see Pitfall 2.
3. Add an explicit **null-completeness** check — the Archive path does not need one; this one does.
   See Pitfall 3.

### Pattern 2: Deterministic lead-time derivation, verified rather than estimated

**What:** With `models=ecmwf_ifs` pinned on both endpoints, the bulk product's value at valid time
`T` equals the `run = T.floor('6h')` single-run's value at lead `T.hour % 6`.

**Evidence (live, this session).** Exact-equality counts, single-run value vs. bulk value, by lead
hour, over 8 runs/day:

```
exact-match counts (single-run value == bulk value), by lead hour
Austin        2026-09-20  L0:4/4 L1:4/4 L2:4/4 L3:4/4 L4:4/4 L5:4/4 L6:0/4 L7:0/4 L8:0/4 L9:0/4
El Paso       2026-06-15  L0:4/4 L1:4/4 L2:4/4 L3:4/4 L4:4/4 L5:4/4 L6:0/4 L7:0/4 L8:0/4 L9:0/4
CorpusChristi 2026-01-10  L0:4/4 L1:3/4 L2:4/4 L3:4/4 L4:3/4 L5:3/4 L6:0/4 L7:0/4 L8:0/4 L9:0/4
Austin ifs025 2026-09-20  L0:4/4 L1:1/4 L2:0/4 L3:4/4 L4:0/4 L5:0/4 L6:1/4 L7:0/4 L8:0/4 L9:0/4
```

and the corresponding MAE view for Austin 2026-09-20 (`ecmwf_ifs`, wind_speed_10m, m/s):

```
 lead_h    n   MAE_vs_bulk
      0    4        0.0000
      1    4        0.0000
      2    4        0.0000
      3    4        0.0000
      4    4        0.0000
      5    4        0.0000
      6    4        0.2950
      7    4        0.2625
      8    4        0.5800
```

Three cities, three seasons, unambiguous cut at lead 6. The Corpus Christi 3/4 cells are 2-decimal
rounding at the boundary, not a different lead — MAE there is also ~0. `ecmwf_ifs025` does **not**
show the pattern, which is exactly why the model must be pinned to `ecmwf_ifs`.

**When to use:** always, for this phase. It turns the calibration gate from "estimate a
distribution" into "assert a rule," which is far easier to verify and far harder to get subtly
wrong.

**Gate design implied:**

```python
def measure_lead_alignment(lat, lon, days, model="ecmwf_ifs"):
    """For each sampled day, pull the bulk series and the four 6-hourly
    single runs, and return per-lead exact-match counts. The claim under
    test is: match at leads 0..5, no match at lead >= 6."""

def assert_supports_horizon(alignment, horizon_min=60.0):
    """The bulk product's lead distribution over ALL hours is uniform on
    {0,1,2,3,4,5} -> p05 == 0h, which does NOT support a 60-minute claim.
    This function MUST fail on the unfiltered series. It passes only for the
    hour % 6 == 1 subset, where the lead is exactly 1h for every row."""
```

The gate failing on the unfiltered series is the **correct** outcome, not a defect — do not tune it
until it passes.

### Pattern 3: Wind u/v decomposition, meteorological convention

**What:** Convert (speed, met-direction) to Cartesian components so a regression can correct a
vector rather than a discontinuous 0/360 angle.

**Formula** [CITED: https://confluence.ecmwf.int/pages/viewpage.action?pageId=133262398]:

> u = −|V| sin φ
> v = −|V| cos φ
> |V| = √(u² + v²)
> φ = mod(180 + (180/π)·atan2(u, v), 360)

with φ the **meteorological** direction in radians (the direction the wind comes **FROM**), and u
positive eastward, v positive northward.

**Consistency with this repo.** `thermal_model.perpendicular_wind`'s docstring declares the same
input convention verbatim:

```
wind_dir_deg:    Meteorological wind direction (degrees from North,
                 direction wind is coming FROM)
```
[VERIFIED: backend/thermal_model.py:36-37]

and its body confirms it by flipping to flow direction before projecting:

```python
# backend/thermal_model.py:43-55
ws  = np.asarray(wind_speed_ms, dtype=float)
wd  = np.asarray(wind_dir_deg,  dtype=float)
# Wind flow direction = opposite of met convention
flow_dir = (wd + 180) % 360
# Angle between wind flow and line
delta = np.abs(flow_dir - line_azimuth_deg) % 180
# Convert angles > 90° to acute angle
delta = np.where(delta > 90, 180 - delta, delta)
# Perpendicular component
perp = ws * np.sin(np.radians(delta))
# IEEE 738: below ~20° treat as low-wind / natural convection dominates
perp = np.where(delta < 20, ws * np.sin(np.radians(20)), perp)
return perp
```

So `wind_vector.from_uv(...)` must return a **meteorological** direction, feedable straight into
`perpendicular_wind` with no adjustment. The round-trip test is the contract:
`from_uv(*to_uv(speed, dir)) == (speed, dir)` for all `dir` in `range(0, 360)` and `speed > 0`.

**Example:**

```python
# Source: ECMWF Confluence pageId=133262398 (formulas), convention cross-checked
#         against backend/thermal_model.py:36-37, 43-46 (this repo's own declared input).
import numpy as np

def to_uv(wind_speed_ms, wind_dir_deg):
    """Meteorological (speed, FROM-direction) -> (u eastward, v northward), m/s."""
    ws = np.asarray(wind_speed_ms, dtype=float)
    phi = np.radians(np.asarray(wind_dir_deg, dtype=float))
    return -ws * np.sin(phi), -ws * np.cos(phi)

def from_uv(u, v):
    """(u, v) -> (speed m/s, meteorological FROM-direction deg in [0, 360))."""
    u = np.asarray(u, dtype=float)
    v = np.asarray(v, dtype=float)
    speed = np.hypot(u, v)
    direction = np.mod(180.0 + np.degrees(np.arctan2(u, v)), 360.0)
    return speed, direction
```

**Anti-pattern:** regressing on `wind_direction` in degrees directly. 359° and 1° are 2° apart
physically and 358 apart numerically; a linear model or a tree will both learn nonsense at the
wrap. This is precisely why approach 3 is specified as u/v in the first place.

### Pattern 4: Previous Runs API as a free lead-time sensitivity ladder

**What:** `previous-runs-api.open-meteo.com/v1/forecast` accepts `start_date`/`end_date`
(bulk-batched, live-verified HTTP 200 over multi-day ranges) and serves `<var>_previous_dayN` for
N = 1..7, where N is the number of **24-hour** steps before valid time.

> "Requesting temperature_2m_previous_day1 returns the value predicted 24 hours before valid time;
> _previous_day2 returns 48 hours before, and so on up to day 7."
> [CITED: https://open-meteo.com/en/docs/previous-runs-api]

Live-verified: `previous_day8` returns HTTP 200 with an all-null array (not an error), confirming 7
is the ceiling. Coverage for this project's cities begins between 2024-01-15 (`prev1=0/24`) and
2024-01-20 (`prev1=24/24`), consistent with the docs' "Most models are archived from January 2024."

**When to use:** *not* for the 60-minute arms — 24 h is the finest step. Use it as a cheap,
one-request-per-city **sensitivity arm**: "does the wind-correction model that helps (or doesn't)
at a 1-hour lead still help at 24 h / 48 h?" That question is the single most informative thing the
phase can add for almost zero extra cost, and it directly de-risks the follow-up phase. Recommended
as an **optional final task**, gated behind the seven core arms landing.

### Anti-Patterns to Avoid

- **Calling `_dynamic_viscosity`/`_thermal_conductivity` from the extracted convective function.**
  They are algebraically equal to the inline forms in `ieee738_ampacity` but **not** guaranteed
  bit-equal. See Pitfall 1 — this will break the D-03 equality gate in a way that looks like a
  physics bug.
- **Writing `experiment_splits.py` from scratch.** `anomaly_training.chronological_split` already
  exists and already solved the guard conditions. See Pitfall 5.
- **Using unpinned `best_match`.** Destroys the deterministic lead rule (Pattern 2) and resolves to
  different domains on different endpoints.
- **Presenting the 1-hour-lead arms as operationally achievable.** See Pitfall 6 — this is the
  phase's headline integrity risk.
- **Letting the oracle arm into a "winner" ranking.** D-02 already forbids this; the planner should
  make it a structural property (separate output section, separate key in the JSON), not a caption.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Chronological holdout split | A fresh `iloc[:n]`/`iloc[n:]` splitter | Generalize `anomaly_training.chronological_split` [VERIFIED: backend/anomaly_training.py:394-438] | It already handles sort-by-`datetime_utc`, index reset, empty-side guard, and a minimum-fit-rows floor, with a documented purity guarantee |
| Open-Meteo response validation | New shape/length/unit checks | Reuse `open_meteo_provider`'s block [VERIFIED: backend/open_meteo_provider.py:150-202] | Five distinct failure modes already covered with named-column error messages; the response envelope is identical |
| Weakest-link corridor reduction | A second `np.minimum` + bottleneck-index block | D-03's extracted `corridor_weakest_link(...)` | Two independent copies will drift; the tie-break rule (`amps_a <= amps_b` → city A, matching `rate_corridor`'s `ratings.index(min_rating)`) is non-obvious [VERIFIED: backend/forecast_training.py:175-189] |
| Perpendicular-wind projection | Re-deriving sin(delta) with a 20° floor | `thermal_model.perpendicular_wind` | The 20° directional floor is a deliberate physical convention, easy to omit by accident [VERIFIED: backend/thermal_model.py:53-54] |
| Persistence baseline | A new "last value" function | `ampacity_forecast.forecast_ampacity(method="naive")` — D-02 explicitly says *unchanged* | `forecast_training.baseline_scores` already set the precedent: "the baselines come from the module's own walk-forward function, never a second error computation written here" [VERIFIED: backend/forecast_training.py:318-321] |
| Estimator persistence | `joblib.dump` direct to final path | `forecast_training.persist_corridor_model`'s temp-then-`os.replace` [VERIFIED: backend/forecast_training.py:444-471] | Torn-file guarantee |
| Wind direction → components | Guessing the sign convention | ECMWF's published pair (Pattern 3) | Sign errors here are silent: a 180°-flipped wind still produces plausible-looking ampacity because `perpendicular_wind` folds to an acute angle — the bug survives every smoke test |

**Key insight:** this phase's genuine novelty is only in (a) the forecast provider and (b) the
lead-time gate. Everything downstream of the joined frame is a re-composition of machinery
`forecast_training.py` and `anomaly_training.py` already contain. The plan should read as
"assemble existing parts, add two new ones," and any task that reads otherwise is probably
duplicating something.

## Common Pitfalls

### Pitfall 1: The `thermal_model` extraction is not bit-exact if you reuse the module helpers

**What goes wrong:** the D-03 equality gate fails by ~1 ULP and looks like a physics error.

**Why it happens:** `ieee738_ampacity` does **not** call the module-level `_dynamic_viscosity`
helper — it recomputes it inline with the terms grouped differently. Both blocks, verbatim:

```python
# backend/thermal_model.py:93-101  (module helpers — NOT used by ieee738_ampacity)
def _dynamic_viscosity(T_film_c: float) -> float:
    """Air dynamic viscosity (Pa·s) at film temperature."""
    T_k = T_film_c + 273.15
    return 1.458e-6 * T_k**1.5 / (T_k + 110.4)


def _thermal_conductivity(T_film_c: float) -> float:
    """Air thermal conductivity (W/m·K) at film temperature."""
    return 2.42e-2 + 7.2e-5 * T_film_c
```

```python
# backend/thermal_model.py:128-141  (what ieee738_ampacity actually does)
    T_a  = np.asarray(T_amb_c,     dtype=float)
    Vw   = np.asarray(wind_perp_ms, dtype=float)
    Q_s  = np.asarray(ghi_wm2,     dtype=float)

    T_c  = conductor.T_max
    T_f  = (T_c + T_a) / 2          # film temperature

    # Air properties at film temp (vectorized approximation)
    rho_f = _air_density(conductor.elev)
    mu_f  = 1.458e-6 * (T_f + 273.15)**1.5 / (T_f + 110.4 + 273.15)
    k_f   = 2.42e-2 + 7.2e-5 * T_f

    # Reynolds number
    N_Re = conductor.D * Vw * rho_f / mu_f
```

The denominators differ in association order: `(T_f + 273.15) + 110.4` versus
`(T_f + 110.4) + 273.15`. Floating-point addition is not associative.

**How to avoid:** build the extracted function by **moving lines 128-161 verbatim** into it and
having `ieee738_ampacity` call it. Do not retype, do not "tidy," do not substitute the helpers.

**Warning signs:** an equality test that passes with `np.allclose` but fails with `==` or
`array_equal`. Write the gate with exact equality (`np.array_equal`) so this cannot hide.

### Pitfall 2: `models=` is not optional, and the two endpoints resolve model aliases differently

**What goes wrong:** the deterministic lead rule (Pattern 2) silently stops holding.

**Why it happens:** unpinned, both APIs use `best_match`, which is location-dependent. Live probe:
`models=best_match` on Single-Runs for Austin returned the error
`"The requested model run is not available. Model: dwd_icon, run: ..."` — i.e. `best_match`
resolved to ICON there. Likewise `models=gfs_global` resolved to `ncep_gfs013`. And `ecmwf_ifs025`
— superficially the obvious "ECMWF" choice — showed **no** lead-alignment pattern at all
(`L1:1/4 L2:0/4 L4:0/4 L5:0/4`).

**How to avoid:** hard-code `models="ecmwf_ifs"` as a module constant in the new provider, exactly
as `OPEN_METEO_ARCHIVE_BASE` is hard-coded, with a comment recording the live evidence. Add a test
asserting the request `params` carry it — the existing suite already has the exact idiom
(`test_fetch_open_meteo_requests_metres_per_second_wind` uses a `recorder` dict
[VERIFIED: backend/tests/open_meteo_provider_test.py:126-136]).

### Pitfall 3: Out-of-depth and out-of-horizon requests return HTTP 200 with silent nulls

**What goes wrong:** the fetch "succeeds," the frame has the right number of rows, `_range_check`
passes, and the model trains on nothing.

**Why it happens:** `_range_check` drops nulls before comparing:

```python
# backend/open_meteo_provider.py:220
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
```

That is correct for the Archive API (which errors on absence) but not for these two. Live-measured:

| Request | HTTP | Result |
|---|---|---|
| previous-runs, 2023-01-01, `wind_speed_10m_previous_day1` | 200 | `0/24` non-null |
| previous-runs, 2024-01-15, `wind_speed_10m_previous_day1` | 200 | `0/24` non-null |
| previous-runs, 2024-01-20, `wind_speed_10m_previous_day1` | 200 | `24/24` non-null |
| previous-runs, `wind_speed_10m_previous_day8` (over ceiling) | 200 | `0/24` non-null |
| single-runs, `models=ncep_hrrr_conus`, any valid run | 200 | `49/168` non-null (48 h model, array padded to 168) |
| single-runs, `models=ecmwf_ifs`, `shortwave_radiation` | 200 | `167/168` — **index 0 is null** (flux undefined at the analysis step) |

**How to avoid:** the new provider must add an explicit completeness check *before* `_range_check`,
in the same fail-loud spirit as the existing module's "a missing variable is a failed fetch, never
substituted with a null column" [VERIFIED: backend/open_meteo_provider.py:170-171]:

```python
null_count = sum(1 for x in values if x is None)
if null_count:
    raise ValueError(
        f"open_meteo_forecast_provider: {provider_key!r} has {null_count}/{n} "
        f"null value(s) -- an out-of-archive-depth or out-of-horizon request "
        f"returns HTTP 200 with nulls, not an error. Never forward-filled."
    )
```

with a documented, narrow carve-out for `shortwave_radiation` at single-run index 0 only.

**Warning signs:** a suspiciously round row count, or an ML arm whose MAE is identical to a
constant predictor's.

### Pitfall 4: The Single-Runs `run=` format is stricter than "ISO 8601"

**What goes wrong:** every calibration request 400s, and the error body says only `"Bad Request"` —
no hint about the format.

**Live-measured, all five variants against the same otherwise-valid request:**

```
2026-09-25T00:00         HTTP:200 OK
2026-09-25T00:00Z        HTTP:400 "reason":"Bad Request"
2026-09-25T00:00:00Z     HTTP:400 "reason":"Bad Request"
2026-09-25 00:00         HTTP:400 "reason":"Bad Request"
2026-09-25T06:00         HTTP:200 OK
2026-09-25T03:00         HTTP:400 "reason":"The requested model run is not available. ..."
```

The docs agree: *"Must be provided in ISO 8601 format without seconds, e.g. &run=2024-06-01T00:00"*
[CITED: https://open-meteo.com/en/docs/single-runs-api].

Note the two distinct 400s: a malformed `run` gives `"Bad Request"`; a well-formed but unavailable
`run` names the model and the run. The calibration step must distinguish them — the first is a bug,
the second is an expected archive-boundary condition to be counted and reported.

**How to avoid:** format with `ts.strftime("%Y-%m-%dT%H:%M")`, mirroring
`open_meteo_provider._to_archive_date`'s own `ts.strftime("%Y-%m-%d")`
[VERIFIED: backend/open_meteo_provider.py:95]. Also: `start_date` on Single-Runs is rejected
outright — live: `{"error":true,"reason":"Parameter 'start_date' must not be set"}`.

### Pitfall 5: `03-CONTEXT.md` is wrong that no fixed split exists — build on the one that does

**What goes wrong:** the plan commits to greenfield split infrastructure, re-derives the same guard
conditions, and ends up with two inconsistent splitters in one repo.

**Why it happens:** `03-CONTEXT.md` states, under *Facts confirmed by direct code/API
investigation (do not re-derive)*: "No fixed train/val/test split exists anywhere in this repo
currently — only walk-forward (`backtest_residuals`) and `sklearn.TimeSeriesSplit`." That is
**refuted** by direct read. Verbatim:

```python
# backend/anomaly_training.py:394-421
def chronological_split(
    frame: pd.DataFrame, holdout_fraction: float = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split `frame` (any `datetime_utc`-bearing frame this module produces)
    into a strictly time-ordered (fit, holdout) pair for ROADMAP SC4's
    false-positive/recall measurement: sorts by `datetime_utc`, splits at
    `int(len(frame) * (1 - holdout_fraction))`, and resets both sides'
    indexes. Every fit-slice timestamp is <= the holdout slice's minimum
    timestamp -- the estimator is measured only against rows strictly
    later than anything it was fitted on (T-02-08). Called twice on the
    same frame returns identical slices (pure function of the input).
    ...
    """
    if holdout_fraction is None:
        holdout_fraction = config.ANOMALY_ML_VALIDATION_HOLDOUT_FRACTION

    sorted_frame = frame.sort_values("datetime_utc").reset_index(drop=True)
    split_index = int(len(sorted_frame) * (1 - holdout_fraction))

    fit = sorted_frame.iloc[:split_index].reset_index(drop=True)
    holdout = sorted_frame.iloc[split_index:].reset_index(drop=True)
```

What the CONTEXT got *right* is narrower and still justifies new code: this is **two-way**, not
three-way, and it splits by **row fraction**, not calendar date. D-02 asks for a calendar
train/val/test split.

**How to avoid:** frame `experiment_splits.py` as a generalization. Carry over, explicitly:
the sort-by-`datetime_utc`, the `reset_index(drop=True)` on every side, the purity guarantee, the
empty-side `ValueError` naming all row counts, and the minimum-rows floor
[VERIFIED: backend/anomaly_training.py:417-436]. Add a test that
`calendar_split` and `chronological_split` agree when given equivalent boundaries, so the two
cannot drift.

### Pitfall 6: A 60-minute NWP lead is not operationally realizable, and the phase must say so

**What goes wrong:** the phase produces a defensible-looking result that a reader will reasonably
interpret as "we could deploy this," when no live system could ever have had that forecast.

**Why it happens:** the lead-time arithmetic ignores **dissemination latency**. Global models
(ECMWF IFS, GFS) are typically available 4-6 h after their nominal initialization; regional models
1-3 h; ECMWF AIFS is documented at 5:45 after init
[CITED: https://openmeteo.substack.com/p/single-runs-api, via Open-Meteo's own model-updates page].
So the 00Z run does not exist as a product at 01:00 UTC. A row scored at "lead 1 h" from the 00Z
run is an *idealized* forecast, exactly the way the oracle arm is an idealized observation — less
extreme, but the same category of thing.

Compounding it: **no Open-Meteo product offers a run cadence finer than 6-hourly in the archive.**
Live-verified for `ecmwf_ifs` (00/06/12/18 available; 01/03/09Z "not available") and, more
surprisingly, for `ncep_hrrr_conus` too — HRRR runs hourly in reality, but Open-Meteo archives only
its four extended cycles (01/02/05/07/11Z all returned "model run is not available"). So there is
no product-side fix available within this phase.

**How to avoid:** this does **not** block the phase. It changes the labelling, and it should change
the report's framing from "can we forecast 60 min ahead" to "**given** a perfect-latency NWP at a
1-hour lead, does physics-plus-correction beat persistence?" — which is still the right first
question, because a *negative* answer under idealized latency is decisive (it cannot get better
with real latency). Concretely, the planner should require:
1. A named constant, e.g. `EXPERIMENT_LEAD_REALIZABILITY_CAVEAT`, emitted into the JSON report and
   printed in the `SUMMARY:` line — following the precedent of
   `forecast_training.corridor_report` recording `window_start`/`window_end` "so a shortened run is
   visible in the evidence rather than hidden behind a score"
   [VERIFIED: backend/forecast_training.py:353-355].
2. A dedicated `## Limitations` bullet in the output record, in the same voice as
   `forecasting_model.md`'s existing five limitation bullets.
3. Pattern 4's 24 h / 48 h sensitivity arm as the *realizable-lead* counterpart, if budget allows.

**Warning signs:** any sentence in a draft report of the form "at the 60-minute horizon, method X
achieves..." without an adjacent latency qualifier.

### Pitfall 7: `requests` is used but not declared in `requirements.txt`

**What goes wrong:** a clean checkout `pip install -r requirements.txt` produces an environment
where every provider module fails at import.

**Why it happens:** `requirements.txt` declares exactly six packages — `pandas`, `numpy`, `scipy`,
`pytest`, `beautifulsoup4`, `scikit-learn` [VERIFIED: requirements.txt:23-28] — and none of them
depends on `requests`. Yet `open_meteo_provider` imports it at module level
[VERIFIED: backend/open_meteo_provider.py:37]. It is present in `.venv` at 2.32.5 (confirmed by
direct import this session), so the gap is latent, not currently breaking.

The file's own docstring claims it is "the single source of truth for this repo's runtime
dependencies" and that "Every version below was verified already installed in this project's
`.venv` (via `.venv/bin/python -m pip freeze`)" [VERIFIED: requirements.txt:4-14] — the second
claim is true, the first is not.

**How to avoid:** this is **pre-existing debt, not this phase's scope**, and D-03's no-behavior-
change lock argues against fixing it here. Recommend the planner capture it as a one-line backlog
item rather than a task. Flagging it because the new provider makes the repo *more* dependent on
`requests`, and because a reviewer will reasonably ask.

## Code Examples

### Verified: the exact convective block to extract (`thermal_model.py:152-161`)

```python
# Source: backend/thermal_model.py:152-161, read verbatim this session.
    Q_cf = np.where(
        N_Re < 1000,
        k_f * (1.01 + 1.347 * N_Re**0.52) * (T_c - T_a),
        k_f * 0.754 * N_Re**0.6 * (T_c - T_a)
    )

    # Natural convection (when wind is very low, use max of forced/natural)
    Q_cn = 3.645 * rho_f**0.5 * conductor.D**0.75 * (T_c - T_a)**1.25

    Q_conv = np.maximum(Q_cf, Q_cn)
```

`03-CONTEXT.md`'s "~lines 152-161" is **exactly right**. Two details worth carrying into the plan:
the forced-convection coefficient is `1.347` (not the `1.35` printed in the adjacent comment at
line 148), and `T_c` is fixed at `conductor.T_max` on line 132 (`T_c  = conductor.T_max`), which is
what makes the extracted signature `(T_amb_c, wind_perp_ms, conductor)` sufficient — CONTEXT is
correct on this too.

Downstream, `Q_conv` is consumed at exactly one site:

```python
# backend/thermal_model.py:177-181
    # Solve for I:  I² * R_Tc = Q_conv + Q_rad - Q_solar
    heat_balance = Q_conv + Q_rad - Q_solar
    heat_balance = np.maximum(heat_balance, 0)   # cannot be negative
    I = np.sqrt(heat_balance / R_Tc)
    return I
```

That single consumption point is what makes `q_conv_override=None` a clean one-line insertion.

### Verified: the estimator-dictionary convention a `WIND_CORRECTION_ESTIMATORS` dict must match

Both existing trainers use the identical shape — module-level `dict` keyed by estimator class name,
values are **zero-argument factories** (never shared instances), with an insertion-order-is-tiebreak
comment and a lazy `sklearn` import inside each factory.

```python
# Source: backend/forecast_training.py:43-86, verbatim.
def _make_regression_candidate():
    """Regression arm of D-01's bake-off. Fixed `random_state` so a
    bake-off run is reproducible. Lazy `sklearn` import, matching this
    module's other estimator-touching functions (`fit_corridor_model`) --
    importing `forecast_training` stays free of a hard `sklearn` import."""
    from sklearn.ensemble import HistGradientBoostingRegressor

    return HistGradientBoostingRegressor(random_state=20260924)


def _make_neural_network_candidate():
    ...
    from sklearn.neural_network import MLPRegressor
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return make_pipeline(
        StandardScaler(),
        MLPRegressor(
            hidden_layer_sizes=(32, 16),
            max_iter=2000,
            random_state=20260924,
            early_stopping=False,
        ),
    )


# D-01's evidence-based bake-off: exactly two entries, one per arm of
# "regression or neural network" -- a zero-argument factory per entry (not
# a shared instance), since each `TimeSeriesSplit` fold must fit a FRESH,
# never-before-fit estimator. Order is significant: `select_winner`'s
# deterministic tiebreak falls back to this order as its last resort.
CANDIDATE_ESTIMATORS: dict = {
    "HistGradientBoostingRegressor": _make_regression_candidate,
    "MLPRegressor": _make_neural_network_candidate,
}
```

`anomaly_training.py:866-870` follows the same shape with a `contamination` parameter threaded
through, and its comment explicitly names the precedent: *"mirroring
`forecast_training.CANDIDATE_ESTIMATORS`'s own insertion-order convention"*
[VERIFIED: backend/anomaly_training.py:859-870].

So a new `WIND_CORRECTION_ESTIMATORS` should be:

```python
def _make_linear_correction_candidate():
    """Linear arm of approach 3. Lazy `sklearn` import, matching
    forecast_training._make_regression_candidate's own discipline."""
    from sklearn.linear_model import LinearRegression

    return LinearRegression()


def _make_gradient_boosting_correction_candidate():
    """Gradient-boosting arm of approach 3. Fixed `random_state` reusing
    config.ANOMALY_ML_RANDOM_SEED's value (20260924), this repo's single
    reproducibility seed."""
    from sklearn.ensemble import HistGradientBoostingRegressor

    return HistGradientBoostingRegressor(random_state=20260924)


# Order is significant: last-resort deterministic tiebreak, mirroring
# forecast_training.CANDIDATE_ESTIMATORS and anomaly_training.CANDIDATE_ESTIMATORS.
WIND_CORRECTION_ESTIMATORS: dict = {
    "LinearRegression": _make_linear_correction_candidate,
    "HistGradientBoostingRegressor": _make_gradient_boosting_correction_candidate,
}
```

The seed `20260924` is the repo's single reproducibility constant — it appears as a literal in
both `forecast_training` factories and as `config.ANOMALY_ML_RANDOM_SEED: int = 20260924`, whose
comment reads *"Matches forecast_training.py's fixed-seed reproducibility convention"*
[VERIFIED: backend/config.py:353-354].

### Verified: the network-mocking convention for provider tests

```python
# Source: backend/tests/open_meteo_provider_test.py:59-81, verbatim.
class _FakeResponse:
    def __init__(self, payload=None, json_exc=None):
        self._payload = payload
        self._json_exc = json_exc

    def raise_for_status(self):
        pass

    def json(self):
        if self._json_exc is not None:
            raise self._json_exc
        return self._payload


def _mock_get(monkeypatch, payload=None, json_exc=None, recorder=None):
    def fake_get(url, params=None, timeout=None):
        if recorder is not None:
            recorder["calls"] = recorder.get("calls", 0) + 1
            recorder["params"] = params
            recorder["url"] = url
        return _FakeResponse(payload=payload, json_exc=json_exc)

    monkeypatch.setattr(open_meteo_provider.requests, "get", fake_get)
```

The file's own docstring records this as an inherited convention: *"Follows
backend/tests/asos_provider_test.py's `_FakeResponse` + `monkeypatch.setattr(module.requests,
"get", ...)` convention. Module-level plain-assert functions, no test classes -- matches every
existing test file's convention in this project."*
[VERIFIED: backend/tests/open_meteo_provider_test.py:11-14]

The `recorder` dict is the idiom for asserting on outgoing request params — which is how the new
tests should pin `models=ecmwf_ifs` and the `run=` format.

### Verified: the convention for mocking *training-module* fetches (one layer up)

Training/experiment modules do **not** mock `requests`; they monkeypatch the fetch function on the
module object:

```python
# Source: backend/tests/forecast_training_test.py:146 and
#         backend/tests/anomaly_training_test.py:109, verbatim.
    monkeypatch.setattr(ft, "fetch_city_weather", _fake_fetch)
    monkeypatch.setattr(forecast_training, "fetch_city_weather", _fake_fetch)
```

`forecast_experiment_test.py` and `forecast_leadtime_calibration_test.py` should follow this,
patching the new provider's fetch entry point on the experiment module, while
`open_meteo_forecast_provider_test.py` follows the `_FakeResponse` pattern one layer down. Note
`anomaly_training_test.py` patches `forecast_training.fetch_city_weather` across the module
boundary — the same cross-module patch is available here.

### Live-probe recipe for the calibration gate (reproducible)

```bash
# The two calls the gate compares. Run them and diff the overlapping hours.
curl -s -G "https://historical-forecast-api.open-meteo.com/v1/forecast" \
  --data-urlencode "latitude=30.2711" --data-urlencode "longitude=-97.7437" \
  --data-urlencode "start_date=2026-09-20" --data-urlencode "end_date=2026-09-20" \
  --data-urlencode "hourly=wind_speed_10m" --data-urlencode "wind_speed_unit=ms" \
  --data-urlencode "timezone=UTC" --data-urlencode "models=ecmwf_ifs"

curl -s -G "https://single-runs-api.open-meteo.com/v1/forecast" \
  --data-urlencode "latitude=30.2711" --data-urlencode "longitude=-97.7437" \
  --data-urlencode "hourly=wind_speed_10m" --data-urlencode "wind_speed_unit=ms" \
  --data-urlencode "timezone=UTC" --data-urlencode "run=2026-09-20T00:00" \
  --data-urlencode "models=ecmwf_ifs"
```

## Runtime State Inventory

This phase is an additive-experiment phase, not a rename/refactor/migration. It is included anyway
because D-03 *does* touch two existing runtime files, so "what carries old state" is a live
question.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `data/models/forecast_{corridor}.joblib` and `data/models/training_frame_{corridor}.csv` exist as generated artifacts [VERIFIED: config.py:234, 240]. **These were trained on 2023-01-01→2025-12-31** [VERIFIED: forecasting_model.md:69] — which fully overlaps any test range this phase can construct. | **Code discipline, not data migration.** D-02 already requires approach 5 to refit on train+val only. The plan must add a test asserting the experiment never calls `ampacity_forecast._load_corridor_model`. |
| Live service config | None — no external service holds configuration for this workstream. Verified: the only network dependencies are the unauthenticated Open-Meteo endpoints (`open_meteo_provider` needs "no token and no API key" [VERIFIED: backend/open_meteo_provider.py:19-20]). | None |
| OS-registered state | None — `pytest.ini` and `requirements.txt` are the only build-adjacent registrations, and neither changes. | None |
| Secrets/env vars | None. `open_meteo_provider`'s docstring records that it "needs no token and no API key" and performs no environment variable reads on import [VERIFIED: backend/open_meteo_provider.py:19-22]. Both new endpoints are on the same unauthenticated provider family (live-confirmed: all probes this session succeeded with no credentials). | None |
| Build artifacts | `backend/__pycache__/` and `backend/tests/__pycache__/` exist. No `.egg-info`, no installed package — this repo runs from source via `pythonpath = backend` [VERIFIED: pytest.ini:2]. | None |
| **Module-level caches** | `ampacity_forecast._MODEL_CACHE: dict = {}` is a process-lifetime, never-invalidated per-corridor model cache [VERIFIED: backend/ampacity_forecast.py:247-248, 263-279]. | **Relevant.** If the experiment ever loads a corridor model in-process it poisons the cache for anything later in the same process. Reinforces the "never call `_load_corridor_model`" rule above. |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python venv | everything | ✓ | `.venv/bin/python` present | — |
| `pandas` | frame assembly | ✓ | 2.3.3 (pinned) | — |
| `numpy` | physics/metrics | ✓ | 2.4.3 (pinned) | — |
| `scikit-learn` | correction models | ✓ | 1.9.1 (confirmed by import) | — |
| `requests` | HTTP | ✓ | 2.32.5 (confirmed by import) | — undeclared, see Pitfall 7 |
| `pytest` | tests | ✓ | 9.0.3 (pinned) | — |
| `historical-forecast-api.open-meteo.com` | forecast archive | ✓ | live HTTP 200, `models=ecmwf_ifs`, 2021-01-01→present | Previous Runs API (24 h lead floor) |
| `single-runs-api.open-meteo.com` | calibration gate | ✓ | live HTTP 200, `models=ecmwf_ifs` from 2024-03-14 | **none** — the gate cannot be built without it |
| `previous-runs-api.open-meteo.com` | optional sensitivity arm | ✓ | live HTTP 200, `previous_day1..7` from ~2024-01-20 | drop the optional arm |
| `archive-api.open-meteo.com` | "truth" weather | ✓ | already in production use | — |
| Network egress (unauthenticated HTTPS) | all fetches | ✓ | all probes this session succeeded | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none currently missing.

**Request-volume budget** (answers a CONTEXT open question). Live-measured: a single bulk request
for `2023-01-01 → 2025-12-31` with all five hourly variables returned **HTTP 200, 26,304 rows,
1,066,859 bytes, zero nulls**. So:

| Purpose | Requests | Note |
|---|---|---|
| Forecast archive, 3 y, 5 vars | **4** (1 per city) | one shot, ~1.07 MB each |
| Truth archive, 3 y | 12 (1/city/year) | already the existing `fetch_city_weather` pattern [VERIFIED: backend/forecast_training.py:103-106]; likely already cached in `training_frame_*.csv` |
| Calibration gate | 8 per sampled (city, day) | 4 cycles × 2 days-back. 10 sampled days × 4 cities ≈ **320** |
| Optional sensitivity arm | 4 (1 per city) | `previous_day1..7` in one call |
| **Total** | **≈ 340** | comfortably inside a free tier; warm once, cache to CSV, never re-fetch per test run |

The 26,304-row count is an **exact match** for the assembled row count in Phase 1's existing
training frames [VERIFIED: docs/data-science/decisions/forecasting_model.md:68-72, 96-97], so the
forecast frame will join 1:1 against the truth frame with no reindexing.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest` 9.0.3 [VERIFIED: requirements.txt:26] |
| Config file | `pytest.ini` [VERIFIED: pytest.ini:1-5] — `pythonpath = backend`, `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py` |
| Quick run command | `.venv/bin/python -m pytest backend/tests/<new_file>_test.py -x -q` |
| Full suite command | `.venv/bin/python -m pytest -q` |

Conventions to match: module-level plain-`assert` functions, no test classes, no fixtures beyond
pytest built-ins plus a small number of local `@pytest.fixture` helpers (e.g.
`default_conductor` in `thermal_model_test.py`), `pytest.approx(..., rel=1e-6)` for float
comparison [VERIFIED: backend/tests/thermal_model_test.py:246].

### Phase Requirements → Test Map

No formal REQ-IDs exist (see `<phase_requirements>`), so this maps to D-01/D-02/D-03 obligations.

| Obligation | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| D-03 equality gate (thermal) | `ieee738_ampacity` output is **exactly** unchanged after extraction, over a random input sweep | unit | `pytest backend/tests/thermal_model_test.py -x -q` | ✅ extend existing |
| D-03 equality gate (thermal) | `q_conv_override=None` is a true no-op; a passed override changes the result | unit | same | ❌ Wave 0 |
| D-03 equality gate (trainer) | `corridor_weakest_link` reproduces `corridor_training_frame`'s pre-refactor `dlr_amps` + `bottleneck_index` exactly | unit | `pytest backend/tests/forecast_training_test.py -x -q` | ✅ extend existing |
| D-03 no-behavior-change | Importing every new module performs no network call and no file I/O | unit | `pytest backend/tests/ -k "importable" -q` | ❌ Wave 0 — idiom exists at `thermal_model_test.py:249` |
| D-01 provider | Request carries `models=ecmwf_ifs`, `wind_speed_unit=ms`, `timezone=UTC`; exactly one HTTP call | unit (recorder) | `pytest backend/tests/open_meteo_forecast_provider_test.py -x -q` | ❌ Wave 0 |
| D-01 provider | An all-null / partially-null variable array raises, never forward-fills | unit | same | ❌ Wave 0 |
| D-01 provider | Single-Runs `run=` is formatted `%Y-%m-%dT%H:%M`; a malformed-`run` 400 and an unavailable-`run` 400 are distinguished | unit | same | ❌ Wave 0 |
| D-01 gate | `assert_supports_horizon` **fails** on the unfiltered series and **passes** on `hour % 6 == 1` | unit | `pytest backend/tests/forecast_leadtime_calibration_test.py -x -q` | ❌ Wave 0 |
| D-02 split | Every train timestamp < every val timestamp < every test timestamp; split is pure; empty side raises | unit | `pytest backend/tests/experiment_splits_test.py -x -q` | ❌ Wave 0 |
| D-02 split | `calendar_split` agrees with `anomaly_training.chronological_split` at equivalent boundaries | unit | same | ❌ Wave 0 |
| D-02 fairness | All seven arms are scored on a byte-identical test-timestamp index | unit | `pytest backend/tests/forecast_experiment_test.py -x -q` | ❌ Wave 0 |
| D-02 leakage | The experiment never calls `ampacity_forecast._load_corridor_model`; approach 5 refits from train+val only | unit (monkeypatch to raise) | same | ❌ Wave 0 |
| D-02 oracle | The oracle arm is in a separate report key and is absent from any winner-selection input | unit | same | ❌ Wave 0 |
| Wind vector | `from_uv(*to_uv(s, d)) == (s, d)` for all integer `d` in 0..359, `s > 0`; a due-north wind (`d=0`) gives `u=0, v=-s` | unit | `pytest backend/tests/wind_vector_test.py -x -q` | ❌ Wave 0 |
| Wind vector | `perpendicular_wind(*from_uv(*to_uv(s, d)), az) == perpendicular_wind(s, d, az)` | unit | same | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `.venv/bin/python -m pytest backend/tests/<touched>_test.py -x -q`
- **Per wave merge:** `.venv/bin/python -m pytest -q`
- **Phase gate:** full suite green before `/gsd-verify-work`, **plus** one live-network calibration
  run whose output is transcribed into the tracked record. Every unit test above must pass with
  network fully mocked; the live run is a separate, manually-invoked step (the repo's existing
  precedent — `forecast_training.py --bakeoff` is run by hand, and `forecasting_model.md` is a
  hand-transcribed record of it).

### Wave 0 Gaps

- [ ] `backend/tests/open_meteo_forecast_provider_test.py` — new, clone `open_meteo_provider_test.py`'s `_FakeResponse`/`_mock_get`/`_archive_payload` scaffolding
- [ ] `backend/tests/wind_vector_test.py` — new
- [ ] `backend/tests/experiment_splits_test.py` — new
- [ ] `backend/tests/forecast_leadtime_calibration_test.py` — new
- [ ] `backend/tests/forecast_experiment_test.py` — new
- [ ] Extend `backend/tests/thermal_model_test.py` with the exact-equality extraction gate
- [ ] Extend `backend/tests/forecast_training_test.py` with the `corridor_weakest_link` gate
- [ ] Framework install: **none needed** — pytest 9.0.3 present

## Security Domain

`security_enforcement` is absent from `.planning/config.json` [VERIFIED: .planning/config.json — the
file contains only `{"workflow":{"_auto_chain_active":false}}`], so it is enabled by default.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Both new endpoints are unauthenticated public APIs; no credential is introduced |
| V3 Session Management | no | Offline batch scripts, no session |
| V4 Access Control | **yes (path traversal)** | Any `{corridor}`-templated output path must validate the corridor against `config.CORRIDOR_ENDPOINTS` **before** formatting — the repo's existing control, documented as T-01-03 at `ampacity_forecast._corridor_of` ("this is also the path-traversal guard for `_model_path_for`: the corridor key is validated against a closed set before it is ever formatted into a filename") [VERIFIED: backend/ampacity_forecast.py:213-217] and mirrored at `anomaly_detector._model_path_for` (T-02-02) [VERIFIED: backend/config.py:316-318] |
| V5 Input Validation | **yes** | Every provider response value goes through `units_def.PIPELINE_SCHEMA` range checking. `_range_check` is documented as "the phase's V5 input-validation control" [VERIFIED: backend/open_meteo_provider.py:211-214]. Extend with the null-completeness check (Pitfall 3) |
| V6 Cryptography | no | No cryptography; HTTPS is provided by `requests` defaults |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Caller-supplied URL / SSRF | Tampering | Base URLs are module constants, never built from caller input — the existing rule: "`OPEN_METEO_ARCHIVE_BASE`: a fixed constant -- never built from caller input" [VERIFIED: backend/open_meteo_provider.py:43]. New module must state and follow the same rule. |
| Path traversal via corridor key | Tampering | Closed-set validation before `.format()` (V4 above) |
| Silent unit regression | Tampering / Information Disclosure | `EXPECTED_HOURLY_UNITS` echo check — "the cheapest possible detector for a request parameter that was dropped, renamed, or ignored upstream" [VERIFIED: backend/open_meteo_provider.py:62-64] |
| Silent null substitution producing a falsely confident rating | Tampering | Pitfall 3's completeness gate. This is the project's standing ethical commitment surface: `REQUIREMENTS.md`'s Out-of-Scope table names "any gate resolving to an optimistic guess instead of the static rating" as a **standing ethical commitment** [VERIFIED: REQUIREMENTS.md:46] |
| Unbounded response memory | DoS (self-inflicted) | Live-measured worst case is 1.07 MB for a 3-year 5-variable request; `timeout=60` already the module convention [VERIFIED: backend/open_meteo_provider.py:139] |
| Untrusted deserialization (`joblib.load`) | Tampering | Pre-existing; this phase should **not** load the production artifact at all (see Runtime State Inventory), which sidesteps it |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Reanalysis (ERA5) as a stand-in for "what a forecast would have said" | Dedicated forecast archives with real issue-time/valid-time separation — Open-Meteo's Historical Forecast, Previous Runs, and Single Runs APIs | Previous Runs archive begins ~Jan 2024; Single Runs ~Mar 2024 (ECMWF HRES) / Apr 2026 (most models) [CITED: open-meteo.com docs] | This phase is only possible *because* these exist; Phase 1 predates the team knowing about them |
| Forecast the target series directly (Phase 1's `"ml"`) | Forecast/correct the **physical drivers**, then push through the physics model | Established in the DLR literature | Approaches 2/3/4 are the mainstream framing; Phase 1's direct-target approach is the outlier that lost to persistence |
| Point forecast only | Point forecast + confidence interval derived from measured residuals | — | Already the repo's practice via `backtest_residuals`; noted in DLR-ML prior art, which "introduce[s] confidence intervals for DLR assessments to mitigate risks associated with uncertainties" [CITED: arxiv.org/abs/2405.12319] |
| Scalar wind speed as an ML feature | u/v vector decomposition | Long-standing meteorological practice | Avoids the 0/360 discontinuity; D-02 already specifies it |

**Deprecated/outdated:**
- Treating `forecast_hours`/`past_hours` as usable alongside `start_date`/`end_date` on the
  Historical Forecast API: live-confirmed rejected —
  `{"reason":"Parameter 'forecast_hours' is mutually exclusive with 'start_date' and 'end_date'","error":true}`,
  HTTP 400. CONTEXT is correct on this.
- `models=ecmwf_ifs025` as "the ECMWF option": only reaches ~2026-04-02 on Single Runs and does not
  exhibit the lead-alignment property. Use `ecmwf_ifs` (HRES 9 km).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The lead-alignment rule (`lead = hour % 6` for `models=ecmwf_ifs`) holds over the **full** 2023-2025 window, not just the three sampled days | Pattern 2 | Moderate. Sampling was 3 cities × 3 seasons and was unanimous, but the calibration gate is precisely the mechanism for testing this at scale — that is why it stays a hard gate rather than becoming a hard-coded constant. Expand the gate's sample to ≥30 stratified days. |
| A2 | Open-Meteo will not change the Historical Forecast stitching depth (currently exactly 6 h) during this phase | Pattern 2 | Low near-term, real long-term. Mitigated by the gate running on every warm and recording its measured alignment in the report, not assuming it. |
| A3 | Dissemination latency of 4-6 h for global models applies to ECMWF IFS as delivered via Open-Meteo | Pitfall 6 | Moderate. Sourced from Open-Meteo's own blog/model-updates page via search rather than read off the live table (the table did not render through WebFetch). Direction is not in doubt — latency is certainly > 1 h — but the exact figure is not verified. **Does not change the recommendation**, only the precision of the caveat's wording. Confirm by loading open-meteo.com/en/docs/model-updates in a browser. |
| A4 | Package age/download figures in the legitimacy audit | Package Legitimacy Audit | None — no install decision rests on them; all four are already pinned and installed. |
| A5 | `HistGradientBoostingRegressor` + `LinearRegression` are the right two arms for approach 3 | Code Examples | Low. Follows the repo's own two-arm precedent and D-02's explicit "linear regression, then gradient boosting." |
| A6 | Approach 4's convective-term correction is well-posed at the extracted granularity | Architectural Responsibility Map | Moderate. `Q_conv = max(Q_cf, Q_cn)` is a non-smooth function; a regression on its level may behave badly near the regime boundary. This is exactly the CONTEXT open question about level vs. log-ratio target — decide on the validation set, and log the regime-boundary row fraction. |
| A7 | 4 rows/day (`hour % 6 == 1`) over the 3-year window is enough test data | Summary | Low-moderate. ~4,380 rows/city before the train/val/test split; the test slice at a 20% tail is ~875 rows/city. Comparable to the 21,910 rows Phase 1 scored but an order of magnitude smaller — MAE differences under ~3 A may not be separable. The plan should compute and report a paired bootstrap CI on the MAE difference rather than comparing point estimates. |

## Open Questions

1. **Is the `hour % 6` rule stable across the full window, and is it hour-of-day dependent?**
   - What we know: unanimous across 3 cities × 3 seasons × 8 runs each, with a clean cut at lead 6.
   - What's unclear: behavior at DST boundaries (should be none — everything is UTC), at ECMWF
     model-version upgrades (IFS cycle changes happen ~annually), and in 2023 (before the
     Single-Runs archive exists, so **unverifiable by this method for 2023 data**).
   - Recommendation: run the gate on ≥30 stratified days across the **2024-03-14 → present**
     overlap. For 2023, the rule is extrapolated — state that explicitly in the record, or restrict
     the experiment window to 2024-03-14 onward (costs ~40% of rows, buys full verifiability).
     **This is a real decision the planner must make.**

2. **Does the phase proceed at an unrealizable 1-hour lead, or relabel to a realizable one?**
   - What we know: a 1-hour NWP lead is not operationally obtainable (Pitfall 6); the bulk product
     at `hour % 6 == 1` genuinely *is* a 1-hour-lead forecast in the issue-time sense.
   - What's unclear: whether the team wants the idealized-lead result at all.
   - Recommendation: **proceed at the 1-hour lead with an explicit realizability caveat.** A
     negative result under idealized latency is decisive and cheap; a positive result motivates the
     follow-up phase to study realizable leads. Add Pattern 4's 24 h arm if budget allows. This
     supersedes CONTEXT's (a)/(b)/(c) framing, which assumed the lead was unknown.

3. **`ieee738_ampacity` override shape: keyword vs. separate function.** (CONTEXT open question)
   - What we know: `Q_conv` has exactly one consumption site, `thermal_model.py:178`. A keyword is
     a one-line insertion with zero call-site churn.
   - Recommendation: **`q_conv_override=None` keyword.** Now resolvable — the CONTEXT said it was
     "only visible once `convective_heat_loss` is actually extracted," but the single-consumption-
     site read settles it.

4. **Approach 4 target parameterization (level vs. log-ratio).** (CONTEXT open question)
   - Unchanged: decide on the validation set. Note A6's regime-boundary concern favors the
     log-ratio, which is scale-free and better-behaved across the `max()` kink.

5. **Approach 3 pooling (per-corridor pooled vs. per-city).** (CONTEXT open question)
   - Unchanged: decide on the validation set. Note the two corridors have identical `ConductorConfig`
     except `line_azimuth` [VERIFIED per CONTEXT; `elevation_m` is 900.0 for both via
     `config.DEFAULT_CONDUCTOR_CONFIG_KWARGS` at config.py:99], so pooling across corridors is also
     defensible and would quadruple the training rows — worth adding as a third pooling option.

6. **Should the phase's output record be a new `docs/data-science/decisions/` file?**
   - What we know: `forecasting_model.md` is the established ADR-style shape for exactly this kind
     of measured-evidence record, and it has an Open Questions entry this phase answers.
   - Recommendation: new sibling file (e.g. `forecast_correction_experiment.md`), plus a one-line
     cross-reference added to `forecasting_model.md`'s Open Questions. Do not rewrite
     `forecasting_model.md` — it is marked "Ratified as a record of measured fact."

7. **Project-instruction compliance: `ACKNOWLEDGEMENTS.md`.** The user's standing memory records
   that ECE 464 requires AI-use disclosure and that `ACKNOWLEDGEMENTS.md` must be updated before
   any significant AI-assisted commit. The planner should include that update as an explicit task,
   since this phase will produce a large AI-assisted diff.

## Project Constraints (from CLAUDE.md)

**No `./CLAUDE.md` or `./.claude/CLAUDE.md` exists in this repository**, and `.claude/skills/` and
`.agents/skills/` are both absent (verified by directory listing this session — `.claude/` contains
only `jobs/`, `scheduled_tasks.lock`, `settings.local.json`, `worktrees/`).

The project's actual constraints are encoded in three places the planner must honor as if they were
CLAUDE.md directives:

1. **`requirements.txt` header** — "This file is the single source of truth for this repo's runtime
   dependencies and supersedes the prose `pip install ...` lines in README.md:33 and
   backend/dlr_pipeline.py:8" [VERIFIED: requirements.txt:4-7]. Pin anything new here, nowhere else.
2. **`REQUIREMENTS.md` Out of Scope** — "Changing the fail-safe contract (any gate resolving to an
   optimistic guess instead of the static rating) | Standing ethical commitment
   (`Project Definition.md`) — models must plug into the existing gate framework, not alter its
   fail-safe guarantee" [VERIFIED: REQUIREMENTS.md:46].
3. **`backend/config.py` centralization discipline** — every tunable a module reads lives in
   `config.py` [VERIFIED: backend/config.py:1-19, 184-189]. New constants
   (`FORECAST_EXPERIMENT_*`) go there, following the existing `FORECAST_ML_*` / `ANOMALY_ML_*`
   block structure and its heavy inline-justification comment style.

Plus the user's standing memory directive on `ACKNOWLEDGEMENTS.md` (Open Question 7).

## Sources

### Primary (HIGH confidence)

- Direct `Read` of `backend/thermal_model.py` (all 182 lines), `backend/ampacity_forecast.py` (all
  550 lines), `backend/forecast_training.py` (all 615 lines), `backend/open_meteo_provider.py` (all
  230 lines), `backend/config.py` (all 489 lines), `backend/units_def.py:344-386`,
  `backend/anomaly_training.py:380-449, 815-874`,
  `backend/tests/open_meteo_provider_test.py:1-90`, `requirements.txt`, `pytest.ini`
- Direct `Read` of `REQUIREMENTS.md`, `STATE.md`, `03-CONTEXT.md`,
  `docs/data-science/decisions/forecasting_model.md`
- Live HTTP probes this session against `historical-forecast-api.open-meteo.com`,
  `single-runs-api.open-meteo.com`, `previous-runs-api.open-meteo.com` — ~60 requests covering
  parameter rejection, run-format validation, per-model archive-depth bisection, null behavior, and
  the bulk-vs-single-run lead-alignment measurement. Raw outputs pasted inline above.

### Secondary (MEDIUM confidence)

- https://open-meteo.com/en/docs/previous-runs-api — `previous_dayN` semantics, day-7 ceiling,
  "Most models are archived from January 2024" (cross-confirmed by live bisection to 2024-01-15/20)
- https://open-meteo.com/en/docs/single-runs-api — `run=` format, no `start_date`, archive depth
  "2nd of April 2026 for most models / ECMWF IFS HRES 9 km from March 14, 2024" (cross-confirmed by
  live bisection: `ecmwf_ifs025` boundary in 2026-04-01/15; `ecmwf_ifs` works at 2024-03-20)
- https://open-meteo.com/en/docs/historical-forecast-api — "Each run's first few hours are stitched
  into a continuous hourly timeseries" (cross-confirmed by the lead-alignment measurement, which
  quantifies "a few" as exactly 6)
- https://confluence.ecmwf.int/pages/viewpage.action?pageId=133262398 — u/v formulas

### Tertiary (LOW confidence)

- https://openmeteo.substack.com/p/single-runs-api (via WebSearch) — model dissemination latency
  figures (4-6 h global, 1-3 h regional, AIFS 5:45). **Not** read off the live model-updates table;
  see Assumption A3.
- https://arxiv.org/abs/2405.12319 — "Dynamic Line Rating using Hyper-local Weather Predictions: A
  Machine Learning Approach." Abstract only; confirms the correct-weather-then-DLR framing and
  confidence intervals as established practice, but the abstract names no horizon, baseline, or
  quantitative result. Cited for framing, not for any number.

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — nothing new is installed; every version read from `requirements.txt`
  and confirmed by interpreter import
- API layer: **HIGH** — every claim live-probed this session with raw output pasted; docs
  cross-confirm each live finding
- In-repo code claims: **HIGH** — every cited file read in full this session, with line ranges and
  verbatim quotes; three CONTEXT claims verified exactly, one refuted
- Architecture: **HIGH** — follows two existing, shipped precedents (`forecast_training.py`,
  `anomaly_training.py`) rather than proposing a new shape
- Pitfalls: **HIGH** for 1-5 and 7 (each demonstrated from read code or live probe output);
  **MEDIUM** for 6 (direction certain, exact latency figure from a secondary source)
- Operational-realizability framing: **MEDIUM** — see Assumption A3

**Research date:** 2026-09-28
**Valid until:** 2026-10-28 for the in-repo claims (stable). **2026-10-12** for the Open-Meteo
findings — the Single-Runs archive is a rolling window (its "most models" boundary moved to
2026-04-02, ~6 months back from today), so depth claims decay; the lead-alignment rule should be
re-measured by the gate on every warm rather than trusted from this document.
