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

**Measured (Plan 04-01 Task 2, `data/experiment/audit_basis_manifest.json`, generated 2026-09-30, run
against the pinned frozen window `[2024-01-20, 2026-09-29]` at the 24-hour primary lead):**

| Corridor | ABLATION train rows | ABLATION val rows | Re-derived `test_start` | Matches pinned `2026-03-17`? | Rows clipped for pin-safety | FRESH rows | FRESH reason (if zero) |
|---|---|---|---|---|---|---|---|
| AUSTIN_CORPUS_CHRISTI | 2360 | 784 | 2026-03-17 | Yes | 2 | 0 | resolved window end 2026-09-29 is not strictly later than `FROZEN_WINDOW_END` 2026-09-29 — nothing to fetch |
| MIDLAND_EL_PASO | 2360 | 784 | 2026-03-17 | Yes | 2 | 0 | resolved window end 2026-09-29 is not strictly later than `FROZEN_WINDOW_END` 2026-09-29 — nothing to fetch |

**Both may-say/may-not-say statements, restated at their measured size, so no later plan may soften
them:**

- **ABLATION, at 784 validation rows per corridor (minus 2 clipped for pin-safety — see the Data
  provenance re-audit finding below — leaving 782 rows actually usable per corridor), may support**
  replication of Phase 3's own candidate ordering, relative-ordering findings between candidates, and
  ablation studies of the harness's own code. **It may NOT support a confirmation claim** — this exact
  calendar range (2024-01-20 through 2026-03-16) was already assembled and read during Phase 3's own
  development and its own validation-split runs (Plans 03-04/03-05), so any later plan's number
  computed on this basis is a replication of already-seen evidence, not new evidence.
- **FRESH, at 0 rows for both corridors, measured — not assumed — at run time via
  `forecast_experiment._resolve_window_end(None)`, may support nothing numeric.** As of this audit's
  run date (2026-09-30), "yesterday UTC" resolves to exactly `2026-09-29`, the frozen window's own
  last day — there is zero calendar time between the frozen window's end and today from which to draw
  a genuinely fresh row. This is the expected honest answer 04-RESEARCH.md's Open Question 2
  anticipated, not a defect: it means Plan 04-03's confirmation-basis claim for this audit's real-data
  track is, at this calendar date, necessarily an ABLATION-basis replication only — no real
  confirmation claim is available today. A future re-run of `build_basis_manifest` on a later calendar
  date would report a nonzero FRESH row count (accruing at four corridor rows per calendar day, since
  the exact-lead filter keeps one row in four).

## Data provenance re-audit (D-01)

### Finding 1 — truth-side provenance

**Verdict: the entire "truth" side of Phase 3's experiment is a physics-model output, not a
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

### Finding 2 — split-boundary reproducibility

**Verdict: the frozen record's stated split boundary is reproducible only because it was pinned;
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

On the real, pinned-window corridor frame (`[2024-01-20, 2026-09-29]`, both corridors), the re-derived
`test_start`'s DATE matches the frozen record's `2026-03-17` exactly. But `_default_split_boundaries`
computes an exact sub-day TIMESTAMP, not a midnight-aligned date, and the two real corridor frames'
re-derived boundary lands a few hours into that day rather than at `2026-03-17T00:00:00Z` — so 2 rows
per corridor (both at `2026-03-17T00:00:00Z` and `T06:00:00Z`) fall on the frozen record's boundary
DATE while still belonging, under the harness's own precise sub-day rule, to Phase 3's real validation
split rather than its test split. `forecast_experiment_audit.py`'s pin is deliberately DATE-granularity
(matching how the frozen record itself states the boundary — "test split starts 2026-03-17", no time
component), which is the more conservative reading of the two, so `build_basis_manifest` clips both
corridors' ABLATION basis to strictly before the pinned constant, discarding those 2 legitimate-but-
boundary-adjacent rows per corridor rather than trusting the sub-day recomputation this module
explicitly does not pin on. This costs nothing scientifically (2 rows out of 784) and keeps the
frozen-window guard's coarser, safer boundary authoritative.

### Finding 3 — null-row drop (04-RESEARCH.md Open Question 1)

**Verdict: the null-row drop is a one-time window-start boundary effect, not a scattered internal
gap, and it does not threaten arm 5's positional lag assumption (closes 04-RESEARCH.md Open
Question 1).** `anchored_pair_frame`'s `dropna()` (`backend/forecast_experiment.py:658`) drops
exactly 24 rows for every one of the four project cities over the pinned frozen window — measured via
`build_basis_manifest`'s `_measure_city_assembly`, cross-checked independently against an hourly-span
expectation computed from calendar arithmetic alone (23,616 expected hourly rows over
`[2024-01-20, 2026-09-29]` inclusive, versus 23,592 actually assembled — a difference of 24, matching
the frozen record's own stated per-city row count of 23,592 exactly). I inspected the cached assembled
frames directly (`data/experiment/anchored_pair_frame_<CITY>_2024-01-20_2026-09-29_lead24_previous_runs.csv`)
to locate the 24 missing hours rather than assuming their position, and found the SAME 24-hour block
for all four cities: `2024-01-20T00:00:00Z` through `2024-01-20T23:00:00Z` — the window's entire FIRST
calendar day, contiguous, with no other gap anywhere else in the 983-day series. This is fully
explained structurally, not mysteriously: `anchored_pair_frame`'s anchor group is the truth series
shifted forward by `lead_hours` (24), so the anchor value for a row at valid time `T` on the window's
first day requires a truth observation from `T - 24h`, i.e. from the day BEFORE the window start —
but `open_meteo_provider.fetch_open_meteo` is only called for `[start, end]` = `[2024-01-20,
2026-09-29]`, never for `2024-01-19`. The anchor columns for the first 24 rows are therefore
necessarily null, and `merged.dropna()` (line 658) removes them. **Judgement: this does NOT threaten
arm 5's positional lag assumption.** The drop is a single contiguous block at the extreme edge of the
window, entirely outside any scored split (the ABLATION train split begins at the window start and
extends for roughly 1,770 days before reaching validation, so the missing first day is deep inside
the earliest training rows, not adjacent to any split boundary that would misalign a lag). From
`2024-01-21T00:00:00Z` onward, the hourly cadence is unbroken for all four cities — confirmed by the
same missing-timestamp scan finding zero additional gaps anywhere in the remaining ~23,592-row series.
Plan 04-02's own lag-offset audit (04-CONTEXT.md D-01's fifth bullet) can therefore treat the interior
hourly cadence as gap-free rather than as an open empirical question.

### Finding 4 — decision-time availability (D-01 bullet 2)

**Verdict: the lead-time calibration gate proves a value-match between two archives, not that
any consumer could have received the forecast over the network at the claimed decision time
(closes D-01 bullet 2).** `forecast_leadtime_calibration.measure_previous_runs_alignment`
(`backend/forecast_leadtime_calibration.py:390`) fetches exactly two products, both read directly
this session, not assumed from either the module's own docstring or `04-RESEARCH.md`'s prior read:
the Previous-Runs archive's `previous_day1` series, via
`open_meteo_forecast_provider.fetch_previous_runs` (`backend/open_meteo_forecast_provider.py:513`,
endpoint `previous-runs-api.open-meteo.com`, `backend/open_meteo_forecast_provider.py:80`), and the
Single-Runs archive's one exact named run, via `open_meteo_forecast_provider.fetch_single_run`
(`backend/open_meteo_forecast_provider.py:374`, endpoint `single-runs-api.open-meteo.com`,
`backend/open_meteo_forecast_provider.py:79`). Both are confirmed, by reading their own request
functions and this module's own docstring (`backend/open_meteo_forecast_provider.py:1-58`), to be
backward-looking archives — neither endpoint is, or could be, a live dissemination feed a real
forecast consumer could have polled at a wall-clock moment. The compared quantity is `wind_speed`
(`backend/forecast_leadtime_calibration.py:412`, matching the legacy gate's own convention),
compared within a 0.1 m/s tolerance to absorb independent-rounding noise between the two endpoints'
own JSON serialization. The gate's success condition
(`assert_exact_offset_lead`, `backend/forecast_leadtime_calibration.py:515`) requires every
offset in the stitched band to show a match rate at or above 90%, and requires the per-row lead
sample to be uniformly exactly the claimed lead with no percentile softening
(`backend/forecast_leadtime_calibration.py:552-615`) — both conditions computed purely from
comparing the two archived series against each other.

**Verdict: the gate supports "this archived value corresponds, by construction, to a run issued
exactly `lead_hours` earlier" — it does not, and structurally cannot, support "this value was
available for consumption at the real clock moment `T - lead_hours`."** No archive-to-archive
comparison can ever evidence real-time dissemination, regardless of how well the two archives agree,
because neither side of the comparison is a record of what was actually served over a network at a
given wall-clock instant — both sides are retrospective reconstructions. This is a structural
argument, not a rhetorical one: `decision_time_availability_finding()`'s
`reachable_fetch_functions` field enumerates the exact two fetch functions reachable from the gate's
measurement path, both flagged as backward-looking archives, so the claim is checkable by re-running
the enumeration rather than by trusting this paragraph.

This is a DIFFERENT limitation from the one the frozen record's Limitations section already
discloses (`docs/data-science/decisions/forecast_correction_experiment.md:392-401`, "the stitching
verification's reach is bounded, and the gap is not directly closed"). That existing disclosure is a
**coverage** limitation: the Single-Runs archive for `gfs_seamless` only reaches back to roughly
mid-2026, so the cross-check can only be *run* over a handful of recent dates, and its applicability
to 2024–2025 rests on the stitching mechanism being general rather than on a direct historical
cross-check. This finding is a **claim-type** limitation: even over the dates the cross-check *does*
reach, the thing it proves is a value-match between two archives, and a deeper archive (more
coverage) would not close this gap, because the gap is in what *kind* of claim two archives can
jointly support, not in how much of the calendar they cover. A reader who conflates the two would
wrongly conclude that resolving the coverage limitation (a deeper Single-Runs archive) would also
resolve this one; it would not.

### Finding 5 — exhaustive time-reference partition (D-01 bullet 3, first half)

**Verdict: every column of both assembled frame shapes is classified into exactly one time
reference, exhaustively and breakably, and no column references an instant strictly between
decision time and valid time (D-01 bullet 3, first half).** `frame_time_reference_groups`
(`backend/forecast_experiment_audit.py`) derives its classification rules directly from
`anchored_pair_frame`'s rename maps (`backend/forecast_experiment.py:611-651`) and
`corridor_anchored_pair_frame`'s own column construction (`backend/forecast_experiment.py:815-866`)
— never from a guess about naming conventions — and classifies by exact `startswith` prefix match,
never substring containment, so an unrecognized column (tested with a deliberately
truth-substring-but-not-truth-prefix column,
`midwindow_truth_wind_speed_t_minus_12h`) lands in `unclassified` rather than being silently
absorbed into a group.

| Label | Clock instant | Per-city frame columns | Corridor frame columns |
|---|---|---|---|
| `observed_at_valid_time` | valid time (T) | `truth_air_temp`, `truth_wind_speed`, `truth_wind_direction`, `truth_solar_radiation`, `truth_relative_humidity`, `truth_dlr_amps` | `truth_dlr_amps`, `truth_air_temp`, `truth_wind_speed`, `truth_wind_direction`, `truth_solar_radiation` |
| `observed_at_decision_time` | decision time (T − lead) | `anchor_air_temp`, `anchor_wind_speed`, `anchor_wind_direction`, `anchor_solar_radiation`, `anchor_relative_humidity`, `anchor_dlr_amps` | `anchor_dlr_amps`, `anchor_air_temp`, `anchor_wind_speed`, `anchor_wind_direction`, `anchor_solar_radiation` |
| `forecast_valid_at_valid_time` | valid time (T) | `fcst_air_temp`, `fcst_wind_speed`, `fcst_wind_direction`, `fcst_solar_radiation`, `fcst_relative_humidity` | *(none — corridor frame carries no `fcst_*` group)* |
| `forecast_valid_at_decision_time` | decision time (T − lead) | `fcst_anchor_air_temp`, `fcst_anchor_wind_speed`, `fcst_anchor_wind_direction`, `fcst_anchor_solar_radiation`, `fcst_anchor_relative_humidity` | *(none — corridor frame carries no `fcst_anchor_*` group)* |
| `corridor_reduced_predictions` | valid time (T) | *(none — per-city frame has no `pred_*` group)* | `pred_<arm_name>` for every `NON_FITTED_ARMS` entry |
| `bottleneck_selection_diagnostics` | none | *(none)* | `bottleneck_index_truth`, `bottleneck_index_anchor`, `bottleneck_index_<arm_name>` |
| `index_and_diagnostic_columns` | mixed (`datetime_utc`→valid time; `anchor_datetime_utc`/`fcst_anchor_datetime_utc`→decision time; `hour_mod_remainder`/`nwp_wind_delta_clamped_a`/`_b`→none) | `datetime_utc`, `anchor_datetime_utc`, `fcst_anchor_datetime_utc`, `hour_mod_remainder` | `datetime_utc`, `anchor_datetime_utc`, `hour_mod_remainder`, `nwp_wind_delta_clamped_a`, `nwp_wind_delta_clamped_b` |

Both frame shapes report `distinct_clock_instants_per_row == 2` (valid time and decision time
only) — verified on a real-shaped per-city frame (26 columns from `anchored_pair_frame`'s
documented schema) and a real-shaped corridor frame (17 columns from
`corridor_anchored_pair_frame`'s documented schema), both with an empty `unclassified` list.
**Conclusion: no column in either schema, today, references an instant strictly between decision
time and valid time — the "feature available only partway through the decision-to-valid window"
leak class D-01 bullet 3 asks about is not expressible in this frame at all.** This makes the
existing leakage probe's blindness to a mid-window leak a property of the schema (there is no
mid-window column for it to fail to catch), not a gap in the probe itself. The corollary, stated
explicitly so a future reader does not over-read this as a permanent guarantee: this argument is
only as durable as the schema — a future column that shifts a value by some offset strictly between
0 and `lead_hours` (rather than by exactly 0 or exactly `lead_hours`, the only two shifts either
assembly function currently performs) would reopen this question, and `frame_time_reference_groups`
would report that column as `unclassified` rather than silently mis-filing it, which is what makes
this assertion re-checkable rather than a one-time snapshot.

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
