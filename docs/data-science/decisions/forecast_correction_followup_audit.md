# Forecast Correction Follow-up Audit — Data Provenance, Comparison Strength, and Integration Readiness

**Status:** DRAFT / IN PROGRESS. This document is a follow-up, adversarial, independent audit of
`docs/data-science/decisions/forecast_correction_experiment.md` (the "frozen record"), Phase 3's
already-completed and already-verified decision record. The frozen record is **read-only** to this
audit except for the specific appended corrections Decision D-04 explicitly permits (Plan 04-05) —
this document never rewrites its Expectation or Measured-results sections.

This audit **never re-reads Phase 3's held-out test rows**. That is enforced mechanically, not by
convention: every frame this audit's computations touch is passed through
`forecast_experiment_audit.assert_basis_excludes_frozen_test_rows`, which raises `ValueError` on any
row whose timestamp falls on the frozen-test-window side of the pinned boundary
(`backend/forecast_experiment_audit.py`, `FROZEN_TEST_SPLIT_START` / `FROZEN_WINDOW_END`). Three
named audit bases — `SYNTHETIC`, `ABLATION`, `FRESH` — are enumerated in `AUDIT_BASES` and every
number this document states names which basis it rests on and what that basis may and may not claim
(see `## Audit bases` below).

Plan: `04-01`. Phase: `04-forecast-correction-experiment-follow-up-audit-data-provenan`.

## What was audited

This audit examines three artifacts together, never in isolation: the frozen decision record
(`docs/data-science/decisions/forecast_correction_experiment.md`), the offline experiment harness it
was produced by (`backend/forecast_experiment.py` and its dependencies —
`backend/open_meteo_provider.py`, `backend/open_meteo_forecast_provider.py`,
`backend/forecast_leadtime_calibration.py`, `backend/forecast_correction_models.py`,
`backend/forecast_training.py`, `backend/thermal_model.py`, `backend/experiment_splits.py`), and five
locked audit decisions captured in `04-CONTEXT.md` (D-01 through D-05). The phase boundary, stated in
`04-CONTEXT.md`'s Domain section and restated here for a reader of this document alone: this audit
independently re-verifies data provenance and leakage claims against the actual code rather than the
frozen record's own self-description; strengthens the statistical comparison beyond "beats
persistence"; adds a genuinely new conservative-rating/overrating analysis axis Phase 3 did not
attempt; corrects any overstated language in the frozen record; and produces a scoped
integration-readiness plan. It does not re-run or re-score Phase 3's held-out test set, replace the
production forecasting model, or touch any Phase 3 planning artifact beyond the permitted D-04
appendix.

## Audit bases

Every empirical claim in this document rests on exactly one of three named bases, defined in
`backend/forecast_experiment_audit.py`'s `AUDIT_BASES` mapping:

| Basis | What it is | May support | May NOT support |
|---|---|---|---|
| `SYNTHETIC` | Generated in-process, no real corridor/city marker permitted | Proof that a computation (a statistic, a guard, a filter) is implemented correctly | Any claim about this project's real corridors |
| `ABLATION` | Real rows strictly before `FROZEN_TEST_SPLIT_START` (2026-03-17) | Replication of Phase 3's own candidate ordering; relative-ordering and ablation findings | A confirmation claim — that calendar range was already read during Phase 3's own development |
| `FRESH` | Real rows strictly after `FROZEN_WINDOW_END` (2026-09-29) | The only basis on which this audit may make a confirmation claim | Nothing is excluded by construction, but a FRESH basis may legitimately be zero rows, and a zero-row basis supports no numeric claim at all |

**Placeholder — filled by Plan 04-02.** The measured row counts per corridor and basis (real
`ABLATION` train/validation row counts, the real `FRESH` row count and its resolved window, the
re-derived split-boundary match, and the null-drop measurement) are written to
`data/experiment/audit_basis_manifest.json` by Plan 04-01 Task 2 and will be transcribed into this
table's replacement in that same task's commit.

## Data provenance re-audit (D-01)

**Finding 1 — the entire "truth" side of Phase 3's experiment is a physics-model output, not a
sensor measurement, and the frozen record never states this.** `open_meteo_provider.py`'s module
docstring (`backend/open_meteo_provider.py:1-32`, read directly this session) states plainly that
this provider fetches from Open-Meteo's Archive API, chosen specifically because it "reaches back to
1940 (ERA5/ERA5-Land reanalysis)" — a data-assimilation reanalysis product, not a network of physical
sensors reporting live observations. `forecast_experiment.py`'s `anchored_pair_frame` (line 593)
calls `open_meteo_provider.fetch_open_meteo` to obtain this "truth" weather series, and immediately
(`backend/forecast_experiment.py:595-598`) converts it to `truth_dlr_amps` via `_city_ampacity`
(`backend/forecast_experiment.py:337-356`) — the same function, calling the same
`thermal_model.perpendicular_wind` and `thermal_model.ieee738_ampacity` physics, that every forecast
arm's own prediction is computed through (`_make_persistence_24h_arm` and its siblings, same file).
In other words: the "truth" ampacity this entire experiment scores every candidate against is itself
the output of running IEEE-738 physics over reanalysis-modelled weather — the identical physics
family the candidates use, with a different (also modelled, not observed) weather input. There is no
point anywhere in `forecast_experiment.py`'s pipeline where a physically-measured, sensor-reported
ampacity or a field-validated thermal measurement enters the comparison.

I confirmed independently — not by trusting the frozen record's self-description or 04-RESEARCH.md's
prior read — that the frozen record itself never discloses this. A direct `grep -n -i
"sensor\|observational\|field-validated\|field validated"` against
`docs/data-science/decisions/forecast_correction_experiment.md` returns zero matches anywhere in the
file, including its `## Data provenance` section (`forecast_correction_experiment.md:67-100`) and its
`## Limitations` section (`forecast_correction_experiment.md:382-438`) — the two sections a reader
would expect this caveat to live in. `## Data provenance` states the truth source is "Open-Meteo's
Archive API..., the same reanalysis source every other component of this project's weather ingestion
already uses" (`forecast_correction_experiment.md:78-79`) but never draws the connection that this
means the *truth itself* is unvalidated against any physical measurement. `## Limitations`'s seven
bullets cover the exact-lead filter's row cost, the stitching-calibration gate's bounded historical
reach, the strength of the 24-hour persistence baseline, the oracle's diagnostic-not-ceiling status,
the two-corridor/one-conductor/one-NWP-model scope, the leakage probe's partial coverage, and the
single-scoring-pass discipline — none of the seven states that the truth side itself is a model
output with no independent sensor validation. This is a real, confirmed gap, not a nitpick: every
ampere in the frozen record's Verdict section is an agreement between two model outputs, and a reader
unaware of this fact would read the reported margins as field-validated accuracy rather than
self-consistency between two physics simulations run on two different weather inputs.

**Finding 2 — the frozen record's stated split boundary is reproducible only because it was pinned;
recomputing it today would silently move it.** The frozen record states its held-out test split
begins `2026-03-17` (`forecast_correction_experiment.md:205`, `:231`). `forecast_experiment.py`'s own
boundary rule, `_default_split_boundaries` (`backend/forecast_experiment.py:1448-1462`), computes
`val_start`/`test_start` as fractions of the assembled frame's own calendar span — `min_dt` to
`max_dt` — where `max_dt` is a function of the window end, which itself defaults to "yesterday UTC"
(`_resolve_window_end`, `backend/forecast_experiment.py:306-318`, per 04-RESEARCH.md). Re-running this
same boundary rule on any date after Phase 3's original run therefore produces a *different*
`test_start` than the frozen record's `2026-03-17`, because the frame's `max_dt` has moved forward
with calendar time while `val_fraction`/`test_fraction` stayed fixed. I demonstrated this directly on
synthetic data (`backend/tests/forecast_experiment_audit_test.py::test_rederive_frozen_split_boundaries_is_window_end_dependent`,
verified via `BOUNDARY_WINDOW_DEPENDENCE_OK`): two synthetic frames identical except for their window
end produce measurably different re-derived `test_start` values, later for the frame with the later
end. This is why `forecast_experiment_audit.py` pins `FROZEN_TEST_SPLIT_START`/`FROZEN_WINDOW_END` as
explicit constants rather than recomputing them from a freshly assembled frame — recomputing would
silently drift the audit's frozen-window guard off the exact boundary Phase 3's test-set run actually
scored. Plan 04-01 Task 2 independently re-derives the boundary on the real, pinned-window frame and
records whether it matches `2026-03-17` in `data/experiment/audit_basis_manifest.json`.

## Strengthened comparison (D-02)

Placeholder — filled by Plan 04-03 (block-bootstrap confidence intervals with block-length
sensitivity, direct pairwise comparisons, MAE+RMSE reporting, the multiple-comparisons/fresh-holdout
reservation).

## Conservative-rating analysis (D-03)

Placeholder — filled by Plan 04-04 (overrating frequency/magnitude/duration by weather regime,
calibrated lower ampacity quantiles, matched-overrating-rate retained-capacity comparison).

## Corrected language in the frozen record (D-04)

Placeholder — filled by Plan 04-05 (the lowest-observed-MAE language correction, the 30A/CI-lower-
bound honesty correction, the oracle-as-diagnostic reframing, the raw_forecast-relative headroom
correction, the 1-hour-arm exclusion reaffirmation, and the low-wind-sensitivity-vs-numerical-
instability distinction).

## Corrected verdict

Placeholder — filled by Plan 04-05 (the audit's own concise corrected verdict on whether
`ml_cooling_corrected` or `reference_ml_refit_24h` warrants production integration, with confidence
and caveats).

## Limitations

Placeholder — filled by Plan 04-05, alongside the corrected verdict.

## Integration readiness plan (D-05)

Placeholder — filled by Plan 04-06 (the minimum data contract, the now-vs-later split of
recommendations, the packaging/fetch/fallback/shadow-eval/monitoring/rollback outline, and the
explicitly-left-open 60-minute-vs-24-hour-vs-both product question).

## References

- `docs/data-science/decisions/forecast_correction_experiment.md` — the frozen record under audit.
- `.planning/workstreams/ml-modeling/phases/04-forecast-correction-experiment-follow-up-audit-data-provenan/04-CONTEXT.md` — this phase's locked scope (D-01 through D-05).
- `.planning/workstreams/ml-modeling/phases/04-forecast-correction-experiment-follow-up-audit-data-provenan/04-RESEARCH.md` — the persisted-artifact scope gap and fresh-holdout constraint that shape this phase.
- `backend/forecast_experiment.py` — the harness under audit (assembly, filtering, scoring, boundary computation).
- `backend/open_meteo_provider.py` — the truth-source provider module (Archive API / ERA5-ERA5-Land reanalysis).
- `.planning/workstreams/ml-modeling/phases/04-forecast-correction-experiment-follow-up-audit-data-provenan/04-01-PLAN.md` — this plan.
