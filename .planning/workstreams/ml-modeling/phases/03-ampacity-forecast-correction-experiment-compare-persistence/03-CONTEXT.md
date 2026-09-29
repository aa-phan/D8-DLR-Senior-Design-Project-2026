# Phase 3: Ampacity Forecast Correction Experiment - Context

**Gathered:** 2026-09-29 (via extended chat discussion + live codebase/API investigation, not a
formal /gsd-discuss-phase session — captured here so planning doesn't re-derive it)
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase does **not** build a new production forecasting method. It builds a reproducible
**experiment** — new files only, zero behavior change to any existing runtime caller — that
determines, on held-out evidence, whether any of several forecast-plus-physics approaches should
eventually replace `ampacity_forecast.py`'s current `"ml"` method (which Phase 1 found loses to
naive persistence at the 60-minute horizon; see `docs/data-science/decisions/forecasting_model.md`
and backlog Phase 999.1, which this phase supersedes).

Out of scope for this phase: wiring any winning approach into `ampacity_forecast.FORECAST_METHODS`
(that's a separate future phase, contingent on this one's results, and requires its own decision
about runtime forecast-fetch fallback behavior); probabilistic/quantile evaluation; regime-specific
correction models; multi-NWP-source fusion. These are explicitly deferred, not silently dropped —
see Open Questions.

</domain>

<decisions>
## Implementation Decisions

### Forecast data source
- **D-01: Use Open-Meteo's Historical Forecast API (bulk date-range mode) as the forecast archive,
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

### Scope and phasing
- **D-02: Build and run the full seven-approach comparison in this phase; explicitly stop and
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
- **D-03: No existing runtime file changes behavior in this phase.** New code lives in new files
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

### D-04 (SUPERSEDES D-01's 1-hour lead as primary): Pivot to the 24-hour realizable lead via
Open-Meteo's Previous Runs API as the phase's primary comparison; the 1-hour idealized-lead arm
(D-01) is downgraded to a documented, non-primary curiosity.

**What happened.** Plan 03-01 executed D-01 fully: it built the bulk-forecast provider, the
lead-time calibration gate, found and precisely characterized a real deterministic-lead boundary
(sharp cutover, further refined to 2025-10-01 once all four daily six-hourly runs were checked, not
just 00Z), corrected the experiment window accordingly, and then ran the first real scored slice
(persistence vs. raw-forecast-through-IEEE-738 for one city). That run surfaced a second, more
fundamental problem no prior document anticipated: **for the corrected (necessarily recent) window,
Open-Meteo's "forecast" bulk product is empirically bit-identical to the "truth" archive/reanalysis
product** — confirmed independently via raw HTTP requests bypassing all repo code, across three
cities. Arm 2 (raw forecast) consequently scored an exact 0.000 MAE against truth — not because a
1-hour-lead forecast is skillful, but because in this data source, at this lead, for this recent
window, "forecast" and "truth" are the same number. Best-effort root cause: Open-Meteo's Archive API
likely serves provisional/near-real-time analysis data (not final delayed reanalysis) for anything
this recent, so both endpoints draw from the same underlying source — and the lead-alignment rule
that forced the window to be this recent may be structurally incompatible with genuine
forecast/truth independence at a 1-hour lead from this provider.

**Resolution (user decision, 2026-09-29):** rather than keep chasing a window where both constraints
hold simultaneously at 1-hour lead (which may not exist), **promote the 24-hour realizable-lead
arm — previously scoped as a secondary "sensitivity pass" in the old Plan 03-06 — to the phase's
PRIMARY comparison.** Open-Meteo's Previous Runs API (`previous-runs-api.open-meteo.com`) gives an
exact, unambiguous lead by construction (`<var>_previous_dayN` columns, N=1..7 days), is
bulk-batched (no per-run HTTP calls, no calibration gate needed at all — the lead is correct by
API contract, not something to empirically verify), and at 24 hours out, forecast and truth should
genuinely diverge (real NWP skill differs meaningfully from persistence and from the eventual
observation at that horizon) — sidestepping the bit-identity problem entirely rather than fighting
it. Archive coverage for this endpoint begins ~2024-01-15/20 (per 03-RESEARCH.md's own live
verification), giving a much longer, simpler-to-assemble window than the fragile 1-hour dataset.

**What carries over unchanged:** `backend/wind_vector.py`, the `thermal_model.py`
`convective_heat_loss`/`q_conv_override` extraction, and `backend/forecast_training.py`'s
`corridor_weakest_link` extraction (all from Plan 03-02) are lead-time-agnostic and fully reusable.
The provider adapter (`open_meteo_forecast_provider.py`) needs a new `fetch_previous_runs` function
(already sketched in 03-RESEARCH.md's Pattern 4, not yet implemented) rather than a redesign.

**What needs replanning:** the anchored-pair-frame contract, `forecast_experiment.py`'s arm-scoring
machinery, and Plans 03-03 through 03-07 were all designed around the 1-hour idealized lead as
primary. These need re-design around the 24-hour Previous-Runs-API lead as primary instead — a
much simpler data-assembly story (no calibration gate, no lead-alignment sweep, no anchor/filter
distinction since Previous Runs already gives a clean, uniform, exact lead for every row).

**Disposition of the 1-hour arm:** keep it as a documented, explicitly-labeled non-primary
curiosity (the code already exists and is committed, don't delete working tested code) — report its
result in the final decision record with the bit-identity caveat prominently attached, but do not
treat it as a competing candidate against persistence in the phase's primary verdict. — **Not a
requirements change:** still no new FCST/ANOM ID (D-03's original reasoning holds unchanged).

</decisions>

<verified_facts>
## Facts confirmed by direct code/API investigation (do not re-derive)

- `ampacity_forecast._point_forecast(series, method, history=, model=)` exists exactly as needed —
  approach 5's refit-without-touching-the-production-artifact path is real (confirmed by direct
  read of `backend/ampacity_forecast.py`).
- `backend/thermal_model.py::ieee738_ampacity` computes both forced (`Q_cf`, Reynolds-branched at
  `N_Re=1000`) and natural (`Q_cn`) convection, takes `Q_conv = np.maximum(Q_cf, Q_cn)` — both
  regimes already implemented, no artificial wind-speed floor anywhere (the only floor is a
  documented directional one at 20° in `perpendicular_wind`, a physical convention, not an
  anti-instability hack).
- No wind u/v vector decomposition exists anywhere in the codebase (grep-confirmed) — wind is
  always speed+direction, reduced to a scalar perpendicular component before reaching the thermal
  model or the current ML feature set.
- `ConductorConfig` (795 kcmil Drake ACSR) is identical for both corridors except `elevation_m`
  (both currently 900.0 — no per-corridor split implemented) and `line_azimuth` (computed
  dynamically per corridor via `corridor_discretization.initial_bearing_deg`).
- Current training data: 3 years hourly Open-Meteo Archive (reanalysis) per city
  (`config.FORECAST_ML_TRAINING_YEARS = 3`); `wind_direction`/`relative_humidity` are fetched by
  `fetch_city_weather` but dropped from `corridor_training_frame`'s persisted schema (only used
  internally for the perpendicular-wind computation) — Phase 3 will need to retain these.
- No fixed train/val/test split exists anywhere in this repo currently — only walk-forward
  (`backtest_residuals`) and `sklearn.TimeSeriesSplit` (`bakeoff_corridor`, 5 splits). This phase's
  fixed calendar split is genuinely new infrastructure, reusable by future phases.
- Live-confirmed via direct `curl`: `historical-forecast-api.open-meteo.com`'s bulk mode rejects
  `forecast_hours`/`past_hours` when combined with `start_date`/`end_date` ("mutually exclusive").

</verified_facts>

<open_questions>
## Open Questions (explicitly not decided here — resolve during planning/implementation)

- **Lead-time gate contingency.** If the calibration step's measured p05 lead can't support a
  60-minute claim, three options were scoped (not chosen — pick explicitly if it comes up):
  (a) anchor pulls via Single-Runs directly on a stratified subsample (shrinks test set, no
  batching); (b) relabel the horizon to the bulk product's measured native lead, stated plainly in
  every output; (c) filter to rows whose assumed issue time ≤ T (preserves 60-min framing, needs its
  own characterization of what gets filtered). Leaning (b) primary + (c) as a sensitivity check if
  needed, but not locked in — the planner/executor should decide once real numbers are in hand.
- **`ieee738_ampacity` override shape.** Keyword on the existing function
  (`q_conv_override=None`) vs. a separate `ieee738_ampacity_from_terms(...)`. Only visible once
  `convective_heat_loss` is actually extracted and its call sites are visible — not resolvable from
  outside implementation.
- **Approach 4 (ML-corrected cooling) target parameterization.** Predict the level `Q_conv_obs`
  directly, or a scale-free log-ratio `log(Q_conv_obs / Q_conv_fc)`? Decide on the validation set,
  not up front.
- **Approach 3 pooling.** One correction model per corridor pooled over both endpoint cities (with
  an endpoint indicator) vs. two per-city models — decide on the validation set.
- **Whether the bulk product's effective lead time is stable or hour-of-day dependent.** If it
  varies materially, `assumed_issue_time` needs to be an hour-of-day-conditional lookup rather than
  one scalar — the calibration step's own output should reveal this.
- **Total HTTP request volume budget** for the initial data-warming run (2 sources × 4 cities × N
  years, plus calibration samples) — should be estimated and done deliberately once, not repeated
  per test run (results get cached).
- **Requirement ID.** This phase has no new FCST/ANOM requirement — it's a methodology
  investigation of Phase 1's existing "ml" method, not new project scope. Confirm with
  REQUIREMENTS.md conventions whether a new tracking ID is warranted or whether this stays
  untracked-by-requirement-ID (leaning: no new ID needed, since nothing here is a new capability
  commitment until Phase D/production-wiring exists).
- **Detailed file-level design** (function signatures, exact module contents, test list, 5-step
  implementation sequence with per-step gates) was already worked out in detail during the chat
  discussion that produced this context — the planner should treat that design as a strong starting
  point rather than re-deriving it from scratch, but should still verify every code claim against
  the live repo rather than trusting this summary, per this project's own no-peeking/no-assumed-
  facts discipline.

</open_questions>

## References

- `docs/data-science/decisions/forecasting_model.md` — Phase 1's original bake-off result (both ML
  candidates lost to naive persistence at 60 min; this phase's reason for existing).
- `.planning/workstreams/ml-modeling/phases/01-forecasting-model/01-VERIFICATION.md` — Phase 1
  verification record.
- `backend/thermal_model.py`, `backend/ampacity_forecast.py`, `backend/forecast_training.py`,
  `backend/open_meteo_provider.py`, `backend/config.py` — files read/verified during this
  discussion; primary reference material for planning.
