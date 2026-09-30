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

### Finding 6 — leakage-probe coverage, re-run on real data in both callable shapes (D-01 bullet 3, second half)

**Verdict: the frozen test-set scoring path never actually ran the leakage probe against a callable
shape the probe could fail on — Mode A (the shape the frozen numbers were produced through) reports
every arm unchanged, including the oracle, and that silence is not evidence of an absence of
leakage; Mode B (live-recomputing callables on real rows) demonstrates the probe has genuine power,
and this task's own re-run is the remediation.**

`leakage_probe`'s own docstring caveat (`backend/forecast_experiment.py:1157-1162`, read directly
this session) states plainly that `arms` must be a mapping of LIVE-RECOMPUTING callables, and that "a
callable that looks up a precomputed prediction by timestamp would trivially (and meaninglessly)
report no change regardless of sabotage." The frozen test-set scoring path
(`_run_corridor`, `backend/forecast_experiment.py:1881-1980`) never invokes `leakage_probe` at all —
confirmed by reading the function in full, not assumed — and builds every one of its seven `ALL_ARMS`
callables as `_corridor_arm_reader(name)` (`backend/forecast_experiment.py:1202-1217`), a column
reader over `pred_<arm_name>`, the exact shape the probe's own docstring warns is meaningless to
sabotage-test.

**Two-mode outcome, re-run on real ABLATION-basis rows for both corridors (784 validation rows per
corridor, matching `data/experiment/audit_basis_manifest.json`'s measured ABLATION basis exactly —
no new window invented):**

| Mode | Callable shape | Oracle | Sabotaged arm | Every genuine candidate |
|---|---|---|---|---|
| A | `_corridor_arm_reader` — reads the already-computed `pred_<arm>` column (the shape `_run_corridor` actually built) | **unchanged** (`changed=False`, `max_abs_change=0`) | *(not applicable — Mode A has no sabotaged arm; it re-runs the harness's OWN seven-arm registry as-is)* | unchanged |
| B | Live-recomputing callables (`NON_FITTED_ARMS` factories, `_wind_corrected_ampacity`, `_cooling_corrected_ampacity`, a live arm-5 callable reindexing a feature table onto each frame's own `anchor_datetime_utc`), plus one arm reading `truth_wind_speed` directly | **changed** (`changed=True`) | **changed** (`changed=True`) | unchanged |

Mode A reports **zero** arms changed — the oracle included — for both corridors
(`data/experiment/leakage_probe_coverage_report_AUSTIN_CORPUS_CHRISTI.json`,
`..._MIDLAND_EL_PASO.json`, both git-ignored evidence). This is the measurement, not a null result to
explain away: the oracle (`_make_oracle_arm`, `backend/forecast_experiment.py:485-509`) is the one
arm in the entire registry DESIGNED to consume truth wind at the valid time, specifically so a
leakage probe has something guaranteed to move when sabotage is real. Its silence under Mode A proves
the callable shape itself — not any property of the seven real arms — is what produced the "no
change" result. `_corridor_arm_reader`'s reader function (`backend/forecast_experiment.py:1214-1215`)
returns `frame[f"pred_{arm_name}"]` directly; that column was computed and attached to the frame
*before* `leakage_probe` ever sabotages `frame`'s `truth_*` columns, so no amount of sabotage can
reach it. A probe run in this shape certifies nothing, favorably or unfavorably, about whether the
underlying arms read truth at the valid time.

Mode B, run per endpoint city (AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO — all four cities, both
corridors) on the SAME real ABLATION-basis rows with arms 3/4/5 fit on the ABLATION train rows only
(`WIND_CONFIGURATION`/`COOLING_CONFIGURATION`, never re-selected), demonstrates the probe DOES have
power on real, non-synthetic data: the oracle changed, the deliberately sabotaged arm
(`sabotaged_reads_truth_wind_directly`, reading `truth_wind_speed` unmodified) changed, and every one
of the six genuine candidates (`persistence_24h`, `nwp_wind_delta`, `raw_forecast`,
`ml_wind_corrected`, `ml_cooling_corrected`, `reference_ml_refit_24h`) did not — for both corridors,
with zero exceptions. This is the same qualitative result
`forecast_experiment_test.py::test_leakage_probe_passes_on_real_arms_flags_oracle_and_flags_a_sabotaged_arm`
already established on synthetic data; this task's contribution is running the identical shape on
real ABLATION rows, closing the "only demonstrated on synthetic data" gap.

**What the frozen record's Limitations section does and does not currently disclose.** The record's
existing leakage-probe limitation (`docs/data-science/decisions/forecast_correction_experiment.md`,
"The leakage probe's coverage is partial by design") states that the probe "does not, and was never
designed to, detect a leak through a model that was trained on rows inside the test window" — a
DIFFERENT failure mode (a model **trained on test rows**), covered instead by arm 5's from-scratch
refit and `assert_filtered_split_disjoint`. That disclosure is accurate and this finding does not
contradict it. But the frozen record's Verdict section implicitly credits the leakage probe with
certifying Success Criterion 3 ("no arm depends on truth at or after the valid time") for the actual
scored run — and the mode the probe was DEMONSTRATED to have power in (Mode B, live-recomputing
callables, `forecast_experiment_test.py`'s own power test) is not the mode the frozen numbers were
produced through (Mode A, `_corridor_arm_reader`). The frozen record does not currently distinguish
these two callable shapes anywhere, and a reader who assumes "the probe has demonstrated power,
therefore the scored run is leak-free" has conflated a claim about the probe's general capability
with a claim about the specific run that produced the numbers in this record's Verdict.

**Remediation performed by this task.** `leakage_probe_coverage_report(corridor)` re-runs the probe on
real ABLATION-basis rows in both callable shapes for both corridors, writes a git-ignored two-mode
report, and every frame either mode uses passes `assert_basis_excludes_frozen_test_rows` under
`basis="ABLATION"` before the probe runs on it (`frozen_window_guard_passed: true` for both modes, in
both reports) — no frozen test-window row entered this re-run. This does not change what the frozen
record's Success Criterion 3 disposition says about the SEVEN REAL ARMS (Mode B's real-data re-run
found no evidence any of them leaks); it changes what evidence the record can cite for that
disposition — the record's Verdict should cite Mode B's real-data re-run (this task) rather than
implying Mode A's own silent pass certified it.

### Finding 7 — arm 5's feature-to-label offset is measured, not assumed, and equals the claimed 24 hours exactly (D-01 bullet 4, label timing)

**Verdict: the training labels used to fit arm 5 are measured — from the returned training-matrix
indices themselves, not from the `horizon_minutes` parameter under audit — to postdate their own
features by exactly one value, 24.0 hours, and the ABLATION train rows those labels are drawn from
are strictly chronologically before every scored validation row.**

`forecast_training.build_training_matrix` (`backend/forecast_training.py:288-353`) returns `X` indexed
by each feature row's own timestamp and `y` indexed by `X`'s original index plus the resolved horizon
(`backend/forecast_training.py:311-313,347`, read directly this session). `arm5_label_timing_finding`
builds arm 5's real corridor truth frame on the ABLATION train+val stacked frame exactly the way the
harness does (`_arm5_truth_frame`), calls `build_training_matrix` at `horizon_minutes=1440` (the
experiment's actual horizon), and computes `y.index - X.index` from the two returned indices directly.
For both corridors, this set has exactly one distinct value: 24.0 hours. A single distinct value equal
to the primary lead is the pass condition; more than one would mean arm 5 was fit against a mixture of
horizons.

Reported alongside, with citations, so the record cannot be misread as claiming the experiment used
the production default: the production default horizon is `config.FORECAST_HORIZON_MINUTES = 60.0`
minutes (`backend/config.py:193`), and the horizon this experiment actually passes is
`config.FORECAST_EXPERIMENT_PRIMARY_LEAD_HOURS * 60 = 1440` minutes (`backend/config.py:412`) — two
distinct values, both stated plainly.

D-01's actual question is not "is the shift 24 hours" but "were the training labels available before
the decisions they are compared against." Answered explicitly for the ABLATION basis, both halves
measured, neither assumed: the ABLATION train side's filtered maximum timestamp
(`2025-09-01 18:00:00+00:00` for both corridors) is strictly before the ABLATION validation side's
filtered minimum timestamp (`2025-09-02 00:00:00+00:00`) — `experiment_splits.calendar_split`'s own
partition predicate (`backend/experiment_splits.py:100-102`) guarantees this by construction, and
`train_labels_precede_scored_validation: true` is measured directly from the real filtered frames, not
inferred from the predicate alone. And every scored validation row's own features are drawn from an
anchor time exactly `lead_hours` (24) before its own valid time — `anchored_pair_frame`'s anchor-group
construction (`backend/forecast_experiment.py:606-620`) guarantees this for every row in the frame, not
only the ones this finding happened to sample.

### Finding 8 — the split boundaries are measured disjoint by set intersection and exact-instant placement, not inferred from the predicates (D-01 bullet 4, boundaries)

**Verdict: on the real re-derived boundaries, the filtered train/val/test sides share zero timestamps,
and the harness's own post-filter disjointness assertion passes — measured directly, not assumed from
`calendar_split`'s own partition logic.**

`split_boundary_audit(corridor)` partitions the real ABLATION+held-out corridor frame on the re-derived
boundaries (`forecast_experiment._default_split_boundaries`), filters each side to the exact lead, and
computes the pairwise set intersection of the three FILTERED sides' own timestamps directly — never
inferred from the calendar predicates that produced them. For both corridors: `shared_timestamp_count:
0`; filtered row counts `train=2360, val=786, test=786`; filtered minimum/maximum timestamps for each
side are internally consistent with strict chronological ordering (train's own maximum
`2025-09-01T18:00:00Z` precedes val's own minimum `2025-09-02T00:00:00Z`, which precedes test's own
minimum `2026-03-17T12:00:00Z`). The harness's own existing per-side disjointness assertion
(`forecast_experiment.assert_filtered_split_disjoint`, `backend/forecast_experiment.py:1465-1512`) is
invoked directly, never re-derived, and `split_boundary_audit` additionally raises on its own
independent overlap computation rather than trusting that one check alone — a synthetic test
(`backend/tests/forecast_experiment_audit_test.py::test_split_boundary_audit_raises_on_overlapping_sides`)
proves it actually raises when handed a deliberately corrupted, overlapping split, rather than merely
passing on data that happens not to overlap.

Neither real corridor's assembled data happens to carry a row at the exact fractional-second boundary
instant `_default_split_boundaries` computes (`boundary_row_side` reports `None` for both
`val_start`/`test_start` on both corridors) — the boundary is a computed fraction of the frame's own
calendar span, not aligned to an hourly row. The boundary CONVENTION itself (at-or-after goes right,
strictly-before goes left) is proven as a tested fact rather than a reading of the partition predicates
by a dedicated synthetic test
(`test_split_boundary_audit_boundary_predicate_is_a_tested_fact`) constructing a frame with a row
placed exactly at each boundary instant and asserting `val_start` lands in `val` and `test_start` lands
in `test`.

### Finding 9 — the six-hourly filter's non-interference with arm 5's hourly lag offsets is demonstrated by showing what the other ordering would do, and the interior cadence is measured unbroken (D-01 bullet 5)

**Verdict: filtering to the six-hourly exact-lead subset BEFORE computing arm 5's lag features would
change every lag value — proving the harness's actual ordering (lag features computed on the full
hourly series, the six-hourly subset selected only afterward, via reindex) is load-bearing, not
incidental — and the real ABLATION truth series feeding those lag features carries an unbroken hourly
cadence throughout, with zero gaps.**

**Part one — ordering, demonstrated by disagreement, not asserted from a reading.**
`arm5_lag_offset_finding` builds arm 5's feature table twice from the real ABLATION train+val truth
series: once the way the harness does (`build_training_matrix` on the full, unfiltered hourly series,
matching `_score_fitted_arms_at_corridor_level`'s own construction,
`backend/forecast_experiment.py:1856-1859`), and once from an input already reduced to the six-hourly
exact-lead rows via `forecast_experiment.filter_to_exact_lead` *before* `build_training_matrix` is
called. `ampacity_forecast.build_ml_features`'s lag columns are a positional `.shift(h)`
(`backend/ampacity_forecast.py:145`, read directly this session) — correct only when consecutive rows
are genuinely one hour apart. Filtering to six-hourly cadence first means `.shift(1)` becomes "6 real
hours back," not 1. For both corridors, the two feature tables disagree on every one of the 3,116
timestamps they share (`filter_first_agrees_with_harness_order: false`) — the disagreement is the
demonstration that the harness's own "full series first, select rows after" ordering is the reason the
offsets are intact, a materially stronger finding than observing that the code happens to be
sequenced that way.

**Part two — cadence, measured with a detector proven to detect.** The real ABLATION truth series
feeding arm 5's feature table shows exactly ONE distinct consecutive-timestamp spacing for both
corridors: `1:00:00`, occurring across all 18,872 measured intervals — `positional_shift_safe: true`.
Cross-referencing Plan 04-01's own measured null-drop finding (a single contiguous 24-hour block at
the window's extreme start edge, deep inside the training rows and far from any split boundary, not a
scattered interior gap): this measurement confirms directly, on the ABLATION train+val range this
finding actually scores, that the interior cadence is unbroken — the positional lag shift is safe over
the range arm 5 is fit and scored on. The gap detector itself is proven to detect, not merely proven to
pass: a dedicated synthetic test
(`test_arm5_lag_offset_finding_gap_detector_detects_a_deliberately_removed_hour`) deliberately removes
one interior hour from a synthetic truth series and confirms `positional_shift_safe` flips to `false`
with more than one distinct spacing reported.

### Closing dispositions — every D-01 bullet, one row, no bullet omitted

| D-01 bullet | Disposition | Evidence type | Citation |
|---|---|---|---|
| Bullet 1 — truth source is an archive, not a live feed | Confirmed non-issue (already covered by Plan 04-01, Finding 1) | Code read | `backend/open_meteo_provider.py:1-32`; Finding 1 above |
| Bullet 2 — decision-time availability vs. archive value-matching | Limitation to record (confirmed issue — narrower claim type than the frozen record implies) | Code read | `backend/forecast_leadtime_calibration.py:390,515`; Finding 4 above |
| Bullet 3 — every feature checked against decision time (schema partition + leakage probe coverage) | Confirmed non-issue for the schema partition (no mid-window column exists); confirmed issue for the leakage probe's callable shape (Mode A demonstrated powerless) | Both | `frame_time_reference_groups`, `leakage_probe_coverage_report`; Findings 5–6 above |
| Bullet 4 — preprocessing, shifted targets, and split boundaries | Confirmed non-issue (label timing measured exactly at the claimed lead; split boundaries measured disjoint with zero shared timestamps) | Measurement | `arm5_label_timing_finding`, `split_boundary_audit`; Findings 7–8 above |
| Bullet 5 — six-hourly filter's effect on arm 5's hourly lag offsets | Confirmed non-issue (the harness's own filter-after-lag ordering is demonstrated load-bearing; the interior cadence is measured unbroken) | Measurement | `arm5_lag_offset_finding`; Finding 9 above |

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
