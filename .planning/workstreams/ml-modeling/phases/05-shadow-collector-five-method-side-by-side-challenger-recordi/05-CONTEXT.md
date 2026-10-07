# Phase 5: Shadow Collector — Five-Method Side-by-Side Challenger Recording - Context

**Gathered:** 2026-10-07 (via chat — the user specified this phase's full scope directly, in the
same decision-record precision as Phase 3/4; captured here verbatim as the phase's locked scope,
not re-derived)
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase **extends** the existing, already-working, already-production-inert shadow collector
(`backend/forecast_shadow_pipeline.py` / `backend/forecast_shadow_collect.py`, built in Phase 4) to
record **five** 24-hour-lead candidates side by side per cycle, instead of the one
(`ml_wind_corrected`) it records today. It does **not**:

- Change which method is wired into production (`dlr_pipeline.py` calls nothing in this module
  today, and that stays true after this phase).
- Pick a new provisional default. `ml_wind_corrected` stays the provisional default (the value any
  caller still reading a single `method`/`model_version` field would see); the other four are
  additive recording only.
- Declare any candidate an overall winner. Phase 3's frozen verdict and Phase 4's audit corrections
  to it stand exactly as written — this phase produces more FRESH-basis observational data for the
  **already-scheduled** 2026-11-24T00:00:00 UTC evaluation, it does not pre-empt that evaluation.
- Touch the Nov 1 model-freeze / Nov 24 evaluation protocol defined in
  `forecast_correction_followup_audit.md`'s "Fresh-basis confirmation protocol" section (v2 +
  corrections) in any way: no retuning, no pooling model versions across runs, no inspecting any
  FRESH row's outcome (predicted-vs-truth comparison) before the fixed instant. This phase is
  firmly inside the explicit carve-out that section already grants: "confirming the shadow
  pipeline's own logs exist... FRESH-basis row counts are accruing... without errors" is a
  mechanical health check, never outcome inspection.
- Change production behavior in any file outside the shadow module and its tests.

It **does**:

- Add four new candidate methods to the collector's per-cycle output:
  `ml_cooling_corrected`, `reference_ml_refit_24h`, `raw_forecast`, and `persistence_24h` —
  alongside the existing `ml_wind_corrected` — so all five of Phase 3/4's real (non-oracle) arms are
  recorded from the same cycle, the same shared inputs, the same decision/valid time pair.
- Reuse Phase 3/4's existing estimator/physics code (`forecast_correction_models.py`,
  `forecast_experiment.py`'s arm implementations, `thermal_model.ieee738_ampacity`) rather than
  reimplementing any candidate's math from scratch in the shadow module.
- Preserve every existing field the collector already logs (per-city predictions, corridor
  minimum, `model_version`, `input_provenance`, the four timestamps, the provider-fallback vs.
  prediction-method-fallback distinction) — for all five candidates, not just the one that exists
  today.
- Document, in the shadow runbook or an equivalent record, when five-method collection starts and
  how its data relates to the existing Nov 1/Nov 24 protocol (i.e., which rows/candidates count
  toward that pre-committed evaluation vs. which are purely exploratory/observational).

</domain>

<decisions>
## Implementation Decisions (user's brief, verbatim scope)

### D-01: Record all five real candidates side by side; keep wind-correction as the provisional default; no winner declared

Extend the working shadow collector to record, every cycle, all five non-oracle 24-hour-lead
candidates from Phase 3/4's comparison:

- `ml_wind_corrected` (today's sole recorded candidate — stays the provisional production
  default)
- `ml_cooling_corrected` (Phase 3's lowest-observed-MAE candidate per the frozen record, per
  Phase 4's corrected, non-"established-winner" language)
- `reference_ml_refit_24h` (the 24-hour refit MLP reference arm)
- `raw_forecast` (the uncorrected forecast run through IEEE 738, no ML correction)
- `persistence_24h` (ampacity 24 hours ago, the baseline every other arm is measured against)

This phase makes no claim about which one is "best" — it is purely a recording-breadth expansion.
`ml_wind_corrected` remains what any legacy single-method reader sees as the default; nothing in
this phase promotes any other candidate to that role.

### D-02: One shared-input fetch per cycle; aligned timing, horizon, endpoints, and availability across all five

Fetch each cycle's forecast and observed-anchor inputs **once**, not once per candidate — every
candidate for a given corridor/cycle must be computed from the exact same forecast row, the exact
same anchor observation, the exact same `initialization_time`/`availability_time`/`decision_time`/
`valid_time` quadruple, and the same 24-hour horizon. No candidate may silently use a different
endpoint-city configuration, a different lead time, or data that became available at a different
point in the cycle than its siblings — if alignment cannot be guaranteed for one candidate (e.g. a
feature genuinely unavailable only to that arm), that candidate is marked unavailable for the cycle
(D-04), never computed from a different input snapshot than the others.

### D-03: `reference_ml_refit_24h` uses the 24-hour refit MLP — never the production 60-minute artifact

The `reference_ml_refit_24h` candidate must use the same from-scratch, 24-hour-horizon refit
artifact/training path Phase 3/4 built for this arm (`forecast_training.build_training_matrix`'s
`horizon_minutes=1440` seam), never `ampacity_forecast.py`'s persisted 60-minute `"ml"` production
model and never that module's process-global per-corridor model cache — the same isolation
Phase 3's own arm 5 required, re-affirmed here for the shadow collector specifically.

### D-04: Validate required features per candidate; unavailable means unavailable, never silent substitution

Before computing any candidate's prediction, validate that candidate's own required feature set is
actually present and usable for this cycle (each candidate has a different input footprint — e.g.
`persistence_24h` needs a decision-time-available ampacity estimate, not forecast data at all;
`ml_cooling_corrected` needs the forecast's full weather set; `raw_forecast` needs no correction
inputs at all beyond the forecast itself). If a candidate's required inputs are unavailable or
invalid for a cycle, record that specific candidate as **unavailable** for that cycle (with a
reason), and let the other candidates in the same cycle compute independently. No candidate is ever
silently substituted for another (e.g. never silently falling back to `raw_forecast` under a
different candidate's label) — a prediction-method fallback must always be visible under its own
name, exactly as the existing `fallback_used`/`fallback_reason` fields already do for
`ml_wind_corrected` today.

### D-05: Persistence uses a decision-time-available estimate, never hindsight-reconstructed

`persistence_24h`'s own ampacity figure (the value from ~24 hours ago) and the contemporaneous
weather/rating it was computed from must be a value that was genuinely available **at this cycle's
decision time** — e.g., read from the shadow collector's own prior logged entry for that corridor
24 hours back, or an equivalent decision-time-available source — never recomputed after the fact
from data (including reanalysis/truth-archive data) that was not actually available at decision
time. If no decision-time-available persistence anchor exists yet for a corridor (e.g., the
collector hasn't been running long enough to have a same-corridor entry from 24 hours prior),
`persistence_24h` is recorded as unavailable for that cycle (D-04) rather than backfilled from
hindsight.

### D-06: Preserve every existing record field, for every candidate, independently

Each cycle's log entry must preserve, per candidate: the per-city predictions and the corridor-
level weakest-link minimum, that candidate's own `model_version` string, that candidate's own
`input_provenance` (including `anchor_provenance.<city>.anchor_source`), and the shared four
timestamps (`initialization_time`/`availability_time`/`decision_time`/`valid_time`). The existing,
never-conflated distinction between **provider fallback** (e.g. TCEQ → Synoptic, which still
yields a genuine prediction) and **prediction-method fallback** (`fallback_used`/`fallback_reason`,
degrading a specific candidate to a different method) must be tracked **per candidate** — one
candidate's method-level fallback must never be reported as, or confused with, another candidate's
successful prediction in the same cycle.

### D-07: Isolate per-candidate failures; keep append-only durable storage

A real code-level failure computing one candidate (as opposed to an input-unavailability case
already covered by D-04) must not prevent the other four candidates from being computed and logged
for that cycle, and must not crash the whole collection run. Record the failing candidate's own
failure distinctly (not silently dropped, not conflated with "unavailable"). Durable storage stays
append-only exactly as today — `>>` onto each corridor's `.jsonl` file on the
`shadow-collection-data` branch, never an overwrite, per the bug already fixed in this project's
history (commit `417dc54`).

### D-08: Document when challenger collection starts and its relationship to the existing evaluation protocol

Add a dated note (in `shadow_collection_runbook.md` or an equivalent record) stating exactly when
five-method recording began, and stating plainly which data this protocol change does and does not
affect: the Nov 1/Nov 24 fresh-basis confirmation protocol in
`forecast_correction_followup_audit.md` already scores `FRESH`-basis rows for the candidates under
its own evaluation harness (`forecast_experiment.py`'s `_fresh_confirmation_report`), which is
**independent of** this shadow collector's own JSONL logs. This phase's four newly-added candidates
are additional **observational** shadow data — useful evidence for whoever eventually plans
production integration — not a substitute for, replacement of, or silent modification to that
already-running, already-dated evaluation protocol.

### D-09: No silent protocol changes — ever

This phase must not, under any framing: change the Nov 1 freeze or Nov 24 evaluation dates; pool
or blend model versions/artifacts across runs (e.g. averaging an old and a retrained model's
outputs under one `model_version` label); retune, retrain, or reconfigure any candidate's model
based on anything observed in this collector's own logs; or inspect any FRESH row's
predicted-vs-truth outcome before 2026-11-24T00:00:00 UTC. Per
`forecast_correction_followup_audit.md`'s own explicit carve-out, confirming the collector's logs
exist, that its timestamps are populated and sane, and that rows are accruing without errors is a
mechanical health check and remains permitted at any time — this phase's own verification work
(D-10) must stay inside that carve-out and never cross into outcome inspection.

### D-10: Verify with targeted tests, one live collection cycle, and a persisted scheduled-run confirmation

Verification for this phase must include: targeted unit/integration tests for the new candidate
computations, the shared-input alignment (D-02), the per-candidate feature validation and
unavailable-marking (D-04), the decision-time-only persistence anchor (D-05), and per-candidate
failure isolation (D-07); one real live collection cycle run end to end (local or via a manual
GitHub Actions dispatch) showing all five candidates recorded with plausible values or honest
unavailable/failure markers; and confirmation that the next **scheduled** (cron-triggered) GitHub
Actions run persists the expanded five-candidate record shape to `shadow-collection-data`, not just
a manually-triggered one.

### D-11: Report operational completeness and blockers only — never accuracy or reliability claims

This phase's own completion report (SUMMARY.md and any user-facing report) must describe what was
built and whether it runs end to end — successful execution and physically plausible ampacity
values across all five candidates. It must **not** claim or imply anything about which candidate is
more accurate, better-calibrated, or more conservative/safe than another — those are exactly the
reserved-outcome questions the Nov 1/Nov 24 protocol exists to answer on its own fixed schedule
(D-09). Production (`dlr_pipeline.py` and every other caller) remains completely unchanged by this
phase, exactly as the existing shadow-prototype inertness guarantee already states.

</decisions>

<execution_notes>
## Notes for the planner/researcher

- **Read the actual shadow module before planning anything.** `backend/forecast_shadow_pipeline.py`
  and `backend/forecast_shadow_collect.py` already implement the single-candidate version of almost
  everything D-01/D-02/D-06/D-07 ask for (timestamps, provenance, provider-vs-method fallback,
  append-only logging). This phase's job is breadth (four more candidates computed from the same
  shared inputs), not a rebuild — identify exactly which function currently hardcodes
  `ml_wind_corrected` and generalize it, rather than writing five parallel pipelines.
- **Reuse, don't reimplement.** `backend/forecast_correction_models.py` (wind/cooling correction),
  `backend/forecast_experiment.py` (the `ALL_ARMS` registry, `raw_forecast`, `persistence_24h`
  construction patterns), and `backend/forecast_training.py` (the `horizon_minutes=1440` refit seam
  for `reference_ml_refit_24h`) already contain working, tested implementations of every candidate
  this phase needs to add. The research pass should map each of the four new candidates to its exact
  existing function/class before the planner writes tasks.
- **`persistence_24h`'s decision-time constraint (D-05) is the trickiest piece.** Phase 3's offline
  harness computed `persistence_24h` from the full truth series (`forecast_experiment.py`), which is
  fine offline but is exactly the hindsight-reconstruction this phase's live collector must NOT do.
  The research pass should figure out concretely what decision-time-available source the live
  collector can read 24h-ago ampacity from (its own prior log entries are the most obvious
  candidate) and what the cold-start behavior is before any history has accrued.
- **Isolate failure per candidate, not per cycle.** The existing single-candidate collector's error
  handling may currently assume one method per corridor per cycle; check whether its structure
  needs restructuring (e.g. a per-candidate try/except inside a per-corridor loop) rather than
  assuming the existing control flow generalizes for free.
- **This phase does not reopen or re-litigate Phase 3/4's verdict.** Any plan task that reads like
  "determine which correction method is best" is out of scope — reject it. The phase succeeds by
  producing more side-by-side recorded data, not by answering the production question.

</execution_notes>

## References

- `backend/forecast_shadow_pipeline.py`, `backend/forecast_shadow_collect.py`,
  `backend/forecast_shadow_healthcheck.py` — the existing single-candidate shadow collector this
  phase extends
- `docs/data-science/decisions/shadow_collection_runbook.md` — the existing one-page operational
  reference; D-08's documentation lands here or in an equivalent record
- `docs/data-science/decisions/forecast_correction_followup_audit.md` — the "Shadow prototype"
  section (built-around-provisional-wind-correction-choice framing) and the "Fresh-basis
  confirmation protocol" section (v2 + corrections: 2026-11-01 freeze, 2026-11-24T00:00:00 UTC
  evaluation instant, anti-peeking discipline, mechanical-health-check carve-out) — D-01, D-08, D-09
  are built directly on this section's exact wording
- `docs/data-science/decisions/forecast_correction_experiment.md` — the frozen Phase 3 verdict and
  all five candidates' original definitions (`ml_wind_corrected`, `ml_cooling_corrected`,
  `reference_ml_refit_24h`, `raw_forecast`, `persistence_24h`)
- `backend/forecast_correction_models.py`, `backend/forecast_experiment.py`,
  `backend/forecast_training.py`, `backend/thermal_model.py`, `backend/config.py` — the existing
  implementations this phase reuses rather than rebuilds
- `.github/workflows/shadow_collect.yml` — the scheduled GitHub Actions workflow D-10's
  scheduled-run confirmation targets
