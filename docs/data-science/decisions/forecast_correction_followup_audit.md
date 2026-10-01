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

**Basis.** Both corridors were re-scored on the real **ABLATION** basis: all seven candidates were
evaluated on the 784 validation rows per corridor (782 after Plan 04-01's 2-row pin-safety clip),
with the three fitted arms (`ml_wind_corrected`, `ml_cooling_corrected`, `reference_ml_refit_24h`)
refit on the ABLATION TRAIN rows (2,360 rows/corridor) alone — not train+val, unlike the frozen
harness's own test-scoring convention. This is the one deliberate difference from Phase 3's setup:
it costs a smaller fit sample in exchange for a genuinely held-out validation score for exactly the
three candidates this audit most needs to re-examine, verified by assertion that the maximum fit
timestamp is strictly earlier than the minimum scored timestamp (a test proves the assertion raises
on a deliberately overlapping pair). An ABLATION-basis number may support replication of the frozen
record's own candidate ordering and relative-ordering findings between candidates; it may not claim
confirmation — this is not a confirmation basis — because this calendar range (2024-01-20 through 2026-03-16) was
already assembled and read during Phase 3's own development and its own validation-split runs
(Plans 03-04/03-05) — a number computed on it is a replication of already-seen evidence, not new
evidence. The **FRESH** branch was not attempted beyond a zero-row check: the resolved fresh window
`[2026-09-30, 2026-09-30]` produced zero rows after the exact-lead filter (both corridors), matching
Plan 04-01's checkpoint-approved finding exactly — no confirmation claim is built on a below-minimum
sample.

### Does the candidate ordering replicate?

**AUSTIN_CORPUS_CHRISTI replicates.** `ml_cooling_corrected` wins (MAE 107.190, RMSE 140.031),
beating persistence by 49.121 A (95% CI [40.746, 57.623], excludes zero) and beating the refit model
by 21.198 A (95% CI [15.966, 26.340], excludes zero) — the same winner the frozen record reports.

**MIDLAND_EL_PASO does NOT replicate — this is the phase's single most important finding.**
`ml_wind_corrected` now leads by MAE (127.129), ahead of `ml_cooling_corrected` (132.239) and
`reference_ml_refit_24h` (135.547). Cooling's margin over the refit model is 3.308 A, 95% CI
[-2.667, 9.055] — **statistically indistinguishable from zero** — where the frozen record reported a
distinguishable edge at this exact pair (132.865 vs. 133.525 MAE; see below). The frozen record's
candidate ordering is **contradicted** at this corridor on this real-data basis: the method that was
reported as the winner no longer carries a distinguishable advantage over the runner-up it was
declared to beat, and a different candidate (`ml_wind_corrected`) now has the lowest point MAE.
Neither ordering is comparable row-for-row to the frozen numbers — a smaller fit sample was used,
scored on a different held-out period — but the direction of this disagreement, not its exact
magnitude, is the finding: a decision this audit exists to check for would have shipped the wrong
answer on evidence this fragile.

### Block-bootstrap intervals with block-length sensitivity

| Margin | Corridor | Block 1 CI | Block 4 CI | Block 8 CI | Block 28 CI | Stable? |
|---|---|---|---|---|---|---|
| cooling vs. persistence | AUSTIN_CORPUS_CHRISTI | [40.774, 57.529] | [39.043, 58.359] | [38.142, 59.302] | [36.076, 62.004] | Yes |
| cooling vs. refit | AUSTIN_CORPUS_CHRISTI | [15.875, 26.339] | [14.623, 26.638] | [14.311, 27.027] | [13.328, 27.504] | Yes |
| cooling vs. persistence | MIDLAND_EL_PASO | [19.918, 37.416] | [19.102, 38.123] | [18.990, 38.637] | [17.870, 39.189] | Yes |
| cooling vs. refit | MIDLAND_EL_PASO | [-2.562, 9.041] | [-3.042, 9.487] | [-2.992, 9.307] | [-3.074, 8.958] | Yes (never excludes zero at any length) |
| **wind vs. refit** | **MIDLAND_EL_PASO** | **[0.254, 16.641] excl=True** | **[-0.127, 17.581] excl=False** | **[-0.190, 17.337] excl=False** | **[-0.675, 18.007] excl=False** | **No — flips at block lengths 4, 8, 28** |

At AUSTIN_CORPUS_CHRISTI, every pairwise margin's favourable-exclusion flag is stable across all
four block lengths (percentile widths run 1.03x–1.57x the i.i.d. percentile width at the same
confidence level, mean 1.30x) — the frozen record's intervals, while narrower than these, do not
change which margins are distinguishable from noise. At MIDLAND_EL_PASO the width ratio is smaller
on average (0.98x–1.31x, mean 1.11x) but one margin **flips**: `ml_wind_corrected` vs.
`reference_ml_refit_24h` excludes zero at block length 1 (CI [0.254, 16.641]) but stops excluding
zero at block lengths 4, 8, and 28 (e.g. block 28: [-0.675, 18.007]). The harness's own accelerated
i.i.d. (BCa) interval for this same margin was already barely excluding zero (CI low = 0.036) before
any autocorrelation structure was accounted for — the block interval shows this apparent "win" is
fragile at the frozen record's own interval method, not only at this audit's stricter one. **This
means the frozen record's intervals are optimistic at Midland**: a margin reported there as
distinguishable would not survive a block-length sweep accounting for serial correlation in the
hourly series, and the corrected language in Plan 04-05 must say so.

### Direct pairwise comparison

| Baseline → Candidate | Corridor | Point margin (A) | 95% CI (percentile) | Excludes zero favorably? |
|---|---|---|---|---|
| persistence → cooling | AUSTIN_CORPUS_CHRISTI | 49.121 | [40.746, 57.623] | Yes |
| raw_forecast → cooling | AUSTIN_CORPUS_CHRISTI | 4.123 | [-1.390, 9.724] | No |
| wind_corrected → cooling | AUSTIN_CORPUS_CHRISTI | 5.365 | [-1.609, 12.465] | No |
| refit → cooling | AUSTIN_CORPUS_CHRISTI | 21.198 | [15.966, 26.340] | Yes |
| persistence → cooling | MIDLAND_EL_PASO | 28.742 | [19.962, 37.640] | Yes |
| raw_forecast → cooling | MIDLAND_EL_PASO | 27.748 | [20.961, 34.655] | Yes |
| wind_corrected → cooling | MIDLAND_EL_PASO | -5.110 | [-11.987, 1.924] | No (wind now ahead) |
| refit → cooling | MIDLAND_EL_PASO | 3.308 | [-2.667, 9.055] | No |

`ml_cooling_corrected` is statistically distinguishable from `persistence_24h` at both corridors —
but beating persistence is a **different comparison axis**: persistence is temporal extrapolation
(the ampacity 24 hours ago), not a physics-informed forecast, and establishes nothing about
superiority over `raw_forecast`, `ml_wind_corrected`, or `reference_ml_refit_24h`. Against those
three real candidates, cooling's margin excludes zero only once (vs. refit at Austin); every other
real-candidate comparison at both corridors is statistically indistinguishable from zero, including
the margin against the current real winner's own closest competitor. `oracle_observed_future_wind`
appears nowhere in this table — it is a labelled diagnostic (MAE 12.873/12.254, an unrealizable
upper bound using observed future wind), never a comparison reference.

### Both error metrics, and the disagreements

| Candidate | MAE (A), AUSTIN_CORPUS_CHRISTI | RMSE (A), AUSTIN_CORPUS_CHRISTI | MAE (A), MIDLAND_EL_PASO | RMSE (A), MIDLAND_EL_PASO |
|---|---|---|---|---|
| persistence_24h | 156.311 | 199.649 | 160.981 | 199.652 |
| raw_forecast | 111.313 | 147.449 | 159.987 | 207.182 |
| ml_wind_corrected | 112.554 | 146.899 | 127.129 | 163.348 |
| **ml_cooling_corrected** | **107.190** | **140.031** | **132.239** | **163.957** |
| reference_ml_refit_24h | 128.388 | 161.521 | 135.547 | 165.596 |

The frozen record's own Midland numbers for the cooling-versus-refit pair were MAE 132.865 vs.
133.525 (a 0.66 A MAE advantage for cooling) against RMSE 170.869 vs. 166.668 (a 4.2 A RMSE
*disadvantage* for cooling) — a MAE/RMSE ordering disagreement the frozen record already carried.
This replication's own measurement reproduces the same qualitative pattern on different rows: MAE
favors cooling by a similarly thin margin (132.239 vs. 135.547, now not even distinguishable from
zero per the pairwise table above) while RMSE still favors refit (163.957 vs. 165.596, though here
the gap narrows to near-parity). A candidate that wins on mean absolute error while losing on
root-mean-square error has a lighter typical error and a heavier tail — and for a rating decision the
tail is the part that matters, because it is the large errors that would have overstated capacity.
If the frozen record's verdict text had led with RMSE instead of MAE at Midland, it would have read
differently: `reference_ml_refit_24h`, not `ml_cooling_corrected`, has the better (lower) RMSE at
this corridor in the frozen numbers (166.668 vs. 170.869), the opposite of what the MAE-led verdict
states.

### Multiple comparisons and the reserved period

Six candidates (persistence, nwp_wind_delta, raw_forecast, ml_wind_corrected, ml_cooling_corrected,
reference_ml_refit_24h) were scored once against one baseline (persistence) at each corridor, and a
winner resolved by largest point margin — a single read used for both discovery (which candidate
looks best) and confirmation (is that candidate actually better), the exact conflation a
no-peeking discipline exists to prevent. No correction for multiple comparisons was applied to
either the frozen record's test-set read or this replication's ABLATION-basis read. This phase
therefore reserves a genuinely fresh chronological period for any future confirmation claim: it
begins the day after `FROZEN_WINDOW_END`, **2026-09-30**, requires a minimum of **56 rows** (**14.0
days** at this lead's four-scored-rows-per-day exact-lead filter) before any statistic may be
computed on it, and is enforced disjoint from Phase 3's train, validation, and test ranges by the
same frozen-window guard (`assert_basis_excludes_frozen_test_rows`) Plan 04-01 built — the FRESH
basis in this plan's own measurement run confirmed zero rows available today, so no revised or
promoted method is settled until a future run reports a nonzero FRESH count there.

### The synthetic configuration selection

Plan 03-05's pooling selection for arm 3 (pooled, `LinearRegression`) and target selection for arm 4
(log-ratio, `GradientBoostingRegressor`) were made on representative **synthetic** data during
development, because that plan's own harness does not fetch real corridor data. This does not
invalidate the real-data test performed here or in Phase 3 — that test ran on real corridor rows,
and the configurations were fixed before either test split was read — but it equally does not
establish that those configurations are optimal for real data, because the selection process itself
never saw a single real corridor row. This plan deliberately reused those same configurations
unchanged rather than re-selecting against real data, so that its numbers remain comparable in kind
to the frozen ones; any future re-tuning of arm 3/4 pooling or target choice should be run against
real development data, not synthetic data, to close this gap.

### D-02 dispositions

| Bullet | Disposition | Where answered |
|---|---|---|
| Block-bootstrap intervals + block-length sensitivity | Confirmed issue at Midland (one margin's exclusion flips at longer block lengths; frozen intervals are optimistic there) | "Block-bootstrap intervals with block-length sensitivity" above |
| Direct pairwise comparison | Confirmed: cooling distinguishable from persistence only; indistinguishable from raw_forecast/wind_corrected at Austin and from refit at Midland | "Direct pairwise comparison" above |
| MAE + RMSE reporting, including the Midland divergence | Confirmed: MAE/RMSE ordering disagreement reproduces at Midland; RMSE favors refit, not cooling | "Both error metrics, and the disagreements" above |
| Multiple-comparisons / fresh-holdout reservation | Confirmed issue (single-read discovery+confirmation conflation); fresh period reserved from 2026-09-30, 56-row/14-day minimum, currently zero rows available | "Multiple comparisons and the reserved period" above |
| Synthetic-data configuration selection | Confirmed limitation, both halves stated; real-data re-tuning recommended for future work | "The synthetic configuration selection" above |

## Conservative-rating analysis (D-03)

**Reanalysis-scope limitation, stated before any number below.** Every overrating rate, pinball
loss, exceedance rate, derating, and retained-capacity figure in this section is measured against
the SAME reanalysis-derived truth series Finding 1 above already names: an IEEE-738 output computed
from ERA5/ERA5-Land reanalysis weather, not a sensor-measured observation. That means every number
in this section is a statement about a candidate's self-consistency with a physics simulation — it
measures whether a candidate's predicted ampacity agrees with what IEEE-738 computes from modelled
weather, never whether a real conductor actually carried the current a candidate predicted. Nothing
below should be read as a margin that guarantees conductor safety, or as evidence of conductor-level
thermal reliability. What WOULD make these numbers safety-relevant is sensor-measured conductor temperature
or line-side current/voltage observations, each carrying their own availability timestamp distinct
from any physics-model truth column — Plan 04-06's minimum data contract (D-05) names exactly that
requirement, so the integration-readiness plan already accounts for closing this gap rather than
treating it as a permanent limitation of the method.

**Basis.** Every number below rests on the real ABLATION basis (Finding 1/`## Audit bases` above):
real corridor rows strictly before `FROZEN_TEST_SPLIT_START` (2026-03-17), carrying the SAME
may-support/may-not-support statement already recorded there — these numbers support relative
comparison between candidates, not a confirmation claim, because this calendar range was already
read during Phase 3's own development. The quantile pipeline further partitions this basis into
three chronologically disjoint sub-periods — fit, calibrate, evaluate — expressed through
`experiment_splits.SplitBoundaries`/`calendar_split` and asserted disjoint from the periods' own
timestamps, never merely from the partition predicate. Both corridors share the identical calendar
boundaries (the ABLATION basis spans the same window for both):

| Period | Rows | Start | End |
|---|---|---|---|
| Fit | 1,883 | 2024-01-22 06:00 UTC | 2025-05-06 18:00 UTC |
| Calibrate | 628 | 2025-05-07 00:00 UTC | 2025-10-10 18:00 UTC |
| Evaluate | 628 | 2025-10-11 00:00 UTC | 2026-03-16 18:00 UTC |

A lower-tail quantile model is fit on the Fit period, its calibration offset is learned on the
Calibrate period, and that offset is checked, unchanged, on the Evaluate period — no row is ever
used both to calibrate and to check calibration, asserted directly from the three periods' own
timestamp sets (`quantile_period_boundaries`'s own disjointness assertion, independent of the
calendar splitter's partition predicate).

### Frequency, magnitude, duration, and regime

The overrating profile — how often each candidate's prediction exceeded the modelled truth
ampacity, by how much, and for how many consecutive scored rows — on the real ABLATION-basis
validation rows (784 rows per corridor), computed from the per-row truth and prediction columns
`overrating_profile` consumes directly (reanalysis-derived, per the limitation above):

| Candidate | Corridor | Rate | Mean exceedance (A) | 95th pct. exceedance (A) | Max exceedance (A) | Longest run (rows) |
|---|---|---|---|---|---|---|
| persistence_24h | AUSTIN_CORPUS_CHRISTI | 0.480 | 160.80 | 411.16 | 702.31 | 9 |
| ml_cooling_corrected | AUSTIN_CORPUS_CHRISTI | 0.620 | 125.38 | 327.29 | 474.06 | 27 |
| ml_wind_corrected | AUSTIN_CORPUS_CHRISTI | 0.425 | 96.15 | 255.17 | 449.91 | 8 |
| reference_ml_refit_24h | AUSTIN_CORPUS_CHRISTI | 0.546 | 142.63 | 338.20 | 465.03 | 10 |
| persistence_24h | MIDLAND_EL_PASO | 0.491 | 161.94 | 418.92 | 585.09 | 10 |
| ml_cooling_corrected | MIDLAND_EL_PASO | 0.686 | 148.27 | 333.42 | 613.35 | 25 |
| ml_wind_corrected | MIDLAND_EL_PASO | 0.557 | 134.02 | 323.26 | 667.91 | 15 |
| reference_ml_refit_24h | MIDLAND_EL_PASO | 0.616 | 146.41 | 322.34 | 488.37 | 24 |

**Cadence caveat, in the words the report itself carries:** every profile above reports
`cadence_hours: 6.0` and a `run_length_caveat` stating that "a run counts CONSECUTIVE SCORED rows
only — a run of k scored rows spans roughly 6*k hours of wall-clock time with unscored gaps inside
it, and this profile says nothing about whether the condition held during those unscored hours."
`ml_cooling_corrected`'s 27-row run at Austin (2025-09-25 06:00 through 2025-10-01 18:00) is a
scored-cadence exceedance bound spanning roughly 162 wall-clock hours with six-hour unscored gaps
inside it — not a measured continuous 162-hour exceedance, because the model was never asked about
the hours in between.

**Regime breakdown.** Perpendicular wind is projected from the valid-time truth wind via
`thermal_model.perpendicular_wind` on the corridor's own bearing, binned with the measured
convection crossover as the lowest interior edge. The crossover (`convection_crossover_wind_speed`,
verified against `thermal_model.convective_heat_loss` on both sides) is **0.1428 m/s at 35.0°C** for
both corridors — the conductor configuration's own natural-versus-forced convection boundary, not a
round number. The regime breakdown below is computed for `ml_cooling_corrected` (the frozen record's
own stated winner and the estimator family this phase's quantile work also reuses), reported once
per corridor rather than per candidate (D-03's own regime-breakdown ask is a single table, not a
per-candidate one). This table, like every table in this section, is read against the reanalysis-
scope limitation above — a 100% rate in a 22-row bin measures self-consistency with a physics
simulation, not a field-observed failure:

| Corridor | Bin (perp. wind, m/s) | Is crossover edge? | Rows | Overrating rate |
|---|---|---|---|---|
| AUSTIN_CORPUS_CHRISTI | [0.000, 0.143) | No (floor) | 22 | 1.000 |
| AUSTIN_CORPUS_CHRISTI | [0.143, 1.411) | **Yes — measured crossover** | 500 | 0.802 |
| AUSTIN_CORPUS_CHRISTI | [1.411, 2.680) | No (presentational span) | 240 | 0.258 |
| AUSTIN_CORPUS_CHRISTI | [2.680, 3.948] | No (presentational span) | 22 | 0.045 |
| MIDLAND_EL_PASO | [0.000, 0.143) | No (floor) | 37 | 1.000 |
| MIDLAND_EL_PASO | [0.143, 1.448) | **Yes — measured crossover** | 593 | 0.789 |
| MIDLAND_EL_PASO | [1.448, 2.753) | No (presentational span) | 143 | 0.210 |
| MIDLAND_EL_PASO | [2.753, 4.058] | No (presentational span) | 11 | **flagged — fewer than 20 rows, no rate reported** |

Every bin's own row count is reported directly in the table above; the per-bin counts sum to each
corridor's own 784 scored rows, asserted (`overrating_by_regime`'s own partition check). Secondary
breakdowns by ambient-temperature quartile (four bins per corridor, each with 194–197 rows) show a
flatter pattern: Austin's overrating rate ranges 0.592–0.650 across temperature quartiles, Midland's
ranges 0.599–0.747 — temperature band does not concentrate overrating nearly as sharply as the
perpendicular-wind regime does.

**Low-wind discussion.** Overrating concentrates sharply in the lowest-wind bin: 100% of rows below
the measured crossover are overrating rows, at both corridors, versus 80.2%/78.9% in the bin
immediately above the crossover and 25.8%/21.0% two bins up. This is the expected physical pattern,
not an artifact: below the crossover the convective term is pinned at its natural-convection floor
and is INSENSITIVE to further wind decreases, so the forecast's own wind-speed error stops mattering
for the convective term specifically — but the corridor's TRUE ampacity at very low wind is itself
at its most conservative (natural convection alone), which is exactly where any candidate's forecast
error, however small in absolute wind-speed terms, is most likely to land on the overrating side of
that already-low ceiling. This is the low-wind SENSITIVITY D-04 asks to be distinguished from
low-wind numerical INSTABILITY — the concentration is the convective term's own physical behavior
near the crossover, not a code defect, and `backend/thermal_model.py` carries zero git diff from
this plan's own measurement of it (`FROZEN_SOURCES_UNTOUCHED_OK`).

### Calibrated lower quantiles

Lower-tail quantile models (`alpha = 0.05` and `alpha = 0.10`) are fit via `sklearn.ensemble.
GradientBoostingRegressor(loss="quantile")` on the Fit period, around each candidate's own point
prediction plus decision-time weather features and an hour-of-day encoding — never a valid-time
truth column, asserted by the fixed, auditable feature-name tuple `fit_lower_quantile_model` builds
from. Pinball loss is scikit-learn's own `mean_pinball_loss`, verified in this phase's own test suite
against its alpha-one-half identity (reported loss at alpha=0.5 equals half the mean absolute error
of the same pair) — never a hand-rolled asymmetric loss. The THREE periods' own disjointness,
asserted from their timestamps, is what licenses treating the calibrate-period offset as genuinely
unseen when it is applied to evaluate: a quantile calibrated and checked on the same rows would be
calibrated by construction, and the assertion is what rules that out here.

| Alpha | Candidate | Corridor | Calibrate exceedance (before → after) | Evaluate exceedance (before → after) | Evaluate pinball (before → after) | Calibration improved on evaluate? |
|---|---|---|---|---|---|---|
| 0.05 | ml_cooling_corrected | AUSTIN_CORPUS_CHRISTI | 0.086 → 0.051 | 0.104 → 0.076 | 17.45 → 15.90 | Yes |
| 0.05 | ml_wind_corrected | MIDLAND_EL_PASO | 0.142 → 0.051 | 0.086 → 0.013 | 13.65 → 13.92 | **No** |
| 0.10 | ml_cooling_corrected | AUSTIN_CORPUS_CHRISTI | 0.178 → 0.100 | 0.161 → 0.137 | 27.87 → 26.49 | Yes |
| 0.10 | reference_ml_refit_24h | MIDLAND_EL_PASO | 0.234 → 0.100 | 0.205 → 0.067 | 26.95 → 25.04 | Yes |

The reanalysis-scope limitation above applies to every pinball-loss and exceedance-rate figure in
this table exactly as it does to the overrating table: these are self-consistency numbers against
a physics simulation, not field-validated coverage guarantees. Every candidate at both corridors
improves under calibration at `alpha = 0.10`, and all but one improve at `alpha = 0.05`. The one
exception is named rather than folded into an aggregate: `ml_wind_corrected` at Midland, alpha 0.05 —
the calibrate-period offset (−84.6 A) actually widens the evaluate-period exceedance rate's distance
from nominal (0.086 → 0.013, moving FURTHER from the 0.05 target than the uncalibrated 0.086 was,
in the opposite direction) even though its OWN evaluate pinball loss barely moves (13.65 → 13.92).
This is a real, reportable result about the stability of the underlying error distribution between
two adjacent chronological periods, not a bug: an error distribution that shifts between Calibrate
and Evaluate is not one a single fixed additive offset can calibrate for every candidate, and a
production consumer relying on this candidate at this alpha would need a rolling recalibration
rather than a one-time fit.

### Retained capacity at matched overrating rates

**This is the headline comparison this section exists to produce.** For each candidate and each
target overrating rate (5% and 10%), the additive derating that achieves that rate on the Calibrate
period is applied UNCHANGED on the Evaluate period, and the table reports what it actually achieves
there — never the target as though it were the result. Persistence and the corridor's own static
rating (the weakest-link minimum of its two endpoint cities' `config.STATIC_RATINGS`, consistent
with the frozen record's own weakest-link limitation — a documented proxy, not an independently
sourced corridor-level rating) appear as reference rows; the calibrated lower quantile at each alpha
appears as an additional row at the matching target rate, so a flat derating and a calibrated
quantile are compared at the same nominal risk level. Every number here, like every number above,
measures self-consistency against the reanalysis-derived truth series, not field-validated safety:

| Row | Corridor | Target rate | Derating fitted on Calibrate (A) | Achieved rate on Evaluate | Retained capacity (A) | Retained capacity (fraction of static) |
|---|---|---|---|---|---|---|
| persistence_24h | AUSTIN_CORPUS_CHRISTI | 0.05 | 246.20 | 0.124 | 984.98 | 0.518 |
| ml_wind_corrected | AUSTIN_CORPUS_CHRISTI | 0.05 | 174.80 | 0.069 | 1026.75 | 0.540 |
| ml_cooling_corrected | AUSTIN_CORPUS_CHRISTI | 0.05 | 214.73 | 0.113 | 1064.68 | 0.560 |
| reference_ml_refit_24h | AUSTIN_CORPUS_CHRISTI | 0.05 | 235.19 | 0.105 | 1020.82 | 0.537 |
| static_rating_reference | AUSTIN_CORPUS_CHRISTI | 0.05 | 1008.83 | 0.024 | 891.17 | 0.469 |
| quantile (alpha 0.05, ml_cooling_corrected) | AUSTIN_CORPUS_CHRISTI | 0.05 | 0.00 | 0.076 | 1013.94 | 0.534 |
| persistence_24h | MIDLAND_EL_PASO | 0.05 | 318.19 | 0.075 | 867.24 | 0.598 |
| ml_wind_corrected | MIDLAND_EL_PASO | 0.05 | 294.48 | 0.043 | 921.53 | 0.636 |
| ml_cooling_corrected | MIDLAND_EL_PASO | 0.05 | 302.44 | 0.062 | 962.50 | 0.664 |
| reference_ml_refit_24h | MIDLAND_EL_PASO | 0.05 | 277.19 | 0.069 | 959.95 | 0.662 |
| static_rating_reference | MIDLAND_EL_PASO | 0.05 | 598.59 | 0.005 | 851.41 | 0.587 |
| quantile (alpha 0.05, ml_cooling_corrected) | MIDLAND_EL_PASO | 0.05 | 0.00 | 0.029 | 929.65 | 0.641 |

At a matched 5% acceptable overrating rate, `ml_cooling_corrected` retains the most usable capacity
of any real candidate at BOTH corridors — 1,064.68 A (56.0% of Austin-Corpus Christi's static
rating) and 962.50 A (66.4% of Midland-El Paso's static rating) — ahead of `ml_wind_corrected`,
`reference_ml_refit_24h`, and persistence at the same matched rate, and well ahead of the static
rating itself (which retains only 46.9%/58.7% of its own nameplate value at a comparably conservative
achieved rate). The calibrated quantile at alpha 0.05 (built from `ml_cooling_corrected`'s own point
prediction) retains a comparable amount — 1,013.94 A at Austin, 929.65 A at Midland — at an achieved
rate reasonably close to the nominal target, offering the SAME order of retained capacity as the flat
derating without needing a second calibration pass against a target rate.

**Every achieved rate differs from its target**, and the gap is itself a finding, not noise: at
Austin, persistence's 5%-target derating actually achieves a 12.4% rate on Evaluate — more than
double the target — while `ml_wind_corrected`'s 5%-target derating achieves 6.9%, much closer. At
Midland, the static rating's 5%-target derating achieves only 0.5% (the static rating is already so
conservative that matching its own natural overrating rate to 5% overshoots in the safe direction).
This miss bounds how tightly any of these methods could actually be operated at a stated risk level
without recalibration: a derating fitted on one chronological period and applied to the next is not
guaranteed to hit its target, and the size of that miss — sometimes more than double the target rate,
sometimes a fifth of it — is a property of how stable each candidate's own error distribution is
across adjacent six-month periods, not a flaw in the matching procedure itself.

### The scope of the reliability claim

Restated once more, in its own subsection, because D-03 asks for this limitation to travel beside
every number rather than sit once at the top: every rate, loss, and retained-capacity figure in this
section is a reanalysis-basis self-consistency measurement. The truth series every number above is
checked against is itself computed from ERA5/ERA5-Land reanalysis weather through the identical
IEEE-738 physics every candidate's own prediction already uses (Finding 1) — agreement between a
candidate and this truth series is agreement between two model outputs, not confirmation against a
field-measured conductor temperature or a line-side current observation. None of the frequency,
magnitude, duration, regime, pinball-loss, exceedance-rate, derating, or retained-capacity numbers
in this section may be read as a margin that guarantees conductor safety, or as proof that a real
conductor's reliability has been shown at the corridor level. Closing that gap requires exactly the sensor-
measured or line-side data Plan 04-06's minimum data contract (D-05) already names as a prerequisite
for any eventual integration decision — this section measures what is measurable today against a
reanalysis-derived truth series, honestly scoped to that basis, and no further.

### D-03 dispositions

| D-03 bullet | Disposition | Where answered |
|---|---|---|
| Overrating frequency, magnitude, and duration by weather regime (including low-wind) | Confirmed: measured per candidate at both corridors; overrating concentrates sharply below the measured convection crossover (100% vs. 80%/79% just above it) | "Frequency, magnitude, duration, and regime" above |
| Lower ampacity quantiles via pinball loss with a chronologically separate calibration period | Confirmed: three asserted-disjoint periods (fit/calibrate/evaluate); calibration improves evaluate-period exceedance for all but one (candidate, alpha) pair, which is named rather than hidden | "Calibrated lower quantiles" above |
| Matched-overrating-rate comparison with retained capacity as the headline metric | Confirmed: `ml_cooling_corrected` retains the most capacity among real candidates at a matched 5% rate at both corridors; achieved rates reported alongside targets, including material misses | "Retained capacity at matched overrating rates" above |
| Reliability claim explicitly scoped to the reanalysis-derived verification data, not conductor-level safety | Confirmed: limitation stated before the section's first number, repeated in its own closing subsection and in every table's surrounding text, with no number described as a guaranteed margin of conductor safety | "The scope of the reliability claim" above, and the opening paragraph |

## Corrected language in the frozen record (D-04)

Every row below maps a D-04 bullet to the frozen record's own wording, this audit's revision, and the
amendment subsection in `docs/data-science/decisions/forecast_correction_experiment.md` where the full
correction lives (quoted original, what is wrong with it, and the revised wording in full):

| D-04 bullet | Frozen record's wording (brief) | Audit's revision (brief) | Amendment subsection |
|---|---|---|---|
| 1 | `ml_cooling_corrected` "wins on the held-out test set at both corridors" | Lowest-observed-24-hour-MAE candidate only; its margin over `reference_ml_refit_24h` is not distinguishable from zero at MIDLAND_EL_PASO (3.308 A, 95% CI [-2.667, 9.055]) | Amendment § 1 |
| 2 | Point margins "clear" the 30A practical-significance threshold at MIDLAND_EL_PASO | Interval lower bounds (22.347 A / 22.343 A) sit well below the threshold; a related margin (wind vs. refit) flips from excluding zero to not excluding zero across block lengths | Amendment § 2 |
| 3 | Oracle's margin framed by "recovered fraction" (26.8% / 21.0%) | The oracle is a diagnostic bound on one unrealizable intervention, not an achievable performance ceiling | Amendment § 3 |
| 4 | Headroom measured against `persistence_24h` | The headroom attributable to correction is the raw_forecast-relative margin (15.053 A / 30.260 A), numerically distinct from the persistence-relative one | Amendment § 4 |
| 5 | Legacy 1-hour arm excluded (reaffirmed, not revised) | Adds: a 24-hour-lead result does not, by itself, establish a replacement for the 60-minute production method | Amendment § 5 |
| 6 | Frozen record never states a position on low-wind sensitivity vs. numerical instability | Measured, not asserted: the response is physics (a floor), not a defect | Amendment § 6 |

**The two structural guarantees this amendment was made under.** The frozen record's `## Expectation`
and `## Measured results` sections remain byte-identical to their committed versions — proven by
extracting both sections from the committed file and the working copy and comparing them byte-for-byte
(`EXPECTATION_AND_MEASURED_BYTE_IDENTICAL_OK`) — and every line of the committed file still appears, in
order, in the amended one, under an append-only discipline that only ever adds lines beside an original
claim rather than replacing it (`FROZEN_RECORD_APPEND_ONLY_OK`, 246 lines added, zero deleted or
reworded). Both gates run as automated verification before the amendment commit, not as a documentation
convention trusted after the fact.

**This phase's own physics measurement (Amendment § 6 in full).** The natural-vs-forced convection
crossover for both corridors' shared conductor configuration, at a representative 35.0°C ambient
temperature, is 0.1428 m/s. Sweeping perpendicular wind across a grid bracketing this crossover, the
ampacity response is measured finite and non-negative everywhere, including at exactly zero wind;
monotone non-decreasing across the whole grid; and continuous across the crossover (a vanishing step on
either side produces a vanishing ampacity gap, not a fixed-size jump). Below the crossover the response
is exactly flat — `convective_heat_loss` returns the natural-convection expression unchanged there, and
that expression does not contain the wind variable at all, so the convective term cannot respond to wind
in that regime by construction. The peak sensitivity to wind is located well above the crossover, not at
zero wind. Independently of this sweep, Phase 3's Success-Criterion-4 convective-seam claim was
re-verified from this phase's own code path against the committed golden fixture
(`backend/tests/thermal_model_pre_refactor_golden.npz`), never by invoking the existing equality test
itself: the live ampacity and the live convective term both match the stored golden arrays by exact
array equality, the override seam reproduces the default path exactly, and a perturbed override changes
the result (proving the equality is not the trivial consequence of an ignored parameter). The sub-floor
routing question D-04 bullet 6 raises was answered by attempting it: a corrected convective term that is
positive but below the natural-convection floor IS permitted to reach the physics through the
`q_conv_override` seam, because `predict_cooling_correction`'s own guard rejects only a non-positive
term (`backend/forecast_correction_models.py:547`) and `ieee738_ampacity`'s override branch bypasses
`convective_heat_loss`'s floor entirely when an override is supplied
(`backend/thermal_model.py:236-239`) — a real, measured finding about the seam's exposure, reported here
for the integration-readiness plan to weigh, not evidence of a defect in the physics itself.

## Corrected verdict

**Recommendation: keep both `ml_cooling_corrected` and `reference_ml_refit_24h` live as integration
candidates, with low-to-moderate confidence, and do not treat either as ready for a production
integration decision on this phase's own evidence.** This is not a hedge against disagreeing with the
frozen record — it is this audit's own considered answer, and it would change under two concrete
conditions: it would strengthen toward preferring `ml_cooling_corrected` if a future FRESH-basis
confirmation run reproduces AUSTIN_CORPUS_CHRISTI's clean replication at MIDLAND_EL_PASO too (i.e., if
cooling's margin over the refit model becomes distinguishable from zero on genuinely new rows, not the
ABLATION basis this phase was limited to); it would weaken toward narrowing to `ml_wind_corrected` or
dropping `ml_cooling_corrected`'s "primary candidate" status if a future FRESH-basis run instead
reproduces MIDLAND_EL_PASO's contradiction. Until one of those two things happens, this record treats
the question as genuinely open at one of the two corridors that matter, not settled.

Grounded in this phase's own measurements, not the frozen record's own framing: the ABLATION-basis
replication (D-02) reproduces the frozen record's candidate ordering cleanly at AUSTIN_CORPUS_CHRISTI
(`ml_cooling_corrected` wins, beating the refit model by 21.198 A, 95% CI [15.966, 26.340], excludes
zero, stable across every block length tried) but does NOT reproduce it at MIDLAND_EL_PASO — a
different candidate, `ml_wind_corrected`, now has the lowest point MAE, and `ml_cooling_corrected`'s
margin over the refit model (3.308 A) is not distinguishable from zero there (95% CI [-2.667, 9.055]).
A related margin at the same corridor (`ml_wind_corrected` vs. `reference_ml_refit_24h`) excludes zero
at the i.i.d.-equivalent block length but stops excluding zero at longer block lengths that account for
temporal dependence in the hourly series — this phase's single most load-bearing finding about how
fragile the frozen record's own confidence intervals are at this corridor. Separately, the conservative-
rating analysis (D-03) found `ml_cooling_corrected` retains the most usable capacity of any real
candidate at a matched 5% overrating rate at BOTH corridors (1,064.68 A / 56.0% of static at
AUSTIN_CORPUS_CHRISTI; 962.50 A / 66.4% of static at MIDLAND_EL_PASO) — a genuinely new axis the frozen
record never measured, and one that argues FOR keeping `ml_cooling_corrected` live even where its
pairwise MAE margin is weak, since a risk-adjusted capacity comparison is answering a different and
arguably more decision-relevant question than a raw MAE margin is. Where this verdict differs from the
frozen record's own: the frozen record states `ml_cooling_corrected` "wins on the held-out test set at
both corridors" without qualification; this audit's own real-data replication shows that claim holds
cleanly at one corridor and does not hold, by the frozen record's own comparison logic (beat the nearest
real competitor distinguishably), at the other — the reason is Plan 04-03's direct pairwise
measurement, a comparison the frozen record itself never computed.

**Completed audit findings, by decision.** Every finding this phase produced, one line each, grouped
by decision, with its disposition:

- **D-01 (Data provenance re-audit):** Phase 3's entire "truth" side is a physics-model reanalysis
  output (ERA5/ERA5-Land via Open-Meteo's Archive API), never a sensor measurement — confirmed,
  previously undisclosed in the frozen record. Disposition: confirmed gap, now disclosed.
- **D-01:** The lead-time calibration gate proves an archive-to-archive value match, not real-time
  dissemination availability at the claimed decision point — a claim-type limitation distinct from the
  frozen record's already-disclosed coverage limitation. Disposition: confirmed, narrower claim type.
- **D-01:** Every column of both assembled frame shapes is exhaustively classified into exactly one time
  reference; no column references an instant strictly between decision time and valid time today.
  Disposition: confirmed non-issue for the schema.
- **D-01:** The leakage probe's frozen-run callable shape (`_corridor_arm_reader`) is powerless by
  construction — the oracle itself is silent under it; a live-recomputing re-run (Mode B) on real
  ABLATION rows demonstrates genuine power and finds no leakage in any of the seven real arms.
  Disposition: confirmed issue with the frozen run's own evidentiary basis, remediated by this phase's
  own re-run.
- **D-01:** Arm 5's training labels postdate their own features by exactly 24.0 hours, measured from
  returned indices; split boundaries share zero timestamps across train/val/test; the six-hourly filter
  does not corrupt arm 5's hourly lag offsets, and the interior cadence is unbroken. Disposition:
  confirmed non-issue, all three measured directly.
- **D-02 (Strengthened comparison):** AUSTIN_CORPUS_CHRISTI's candidate ordering replicates cleanly on
  real ABLATION-basis out-of-sample rows; MIDLAND_EL_PASO's does not — a different candidate leads, and
  the frozen record's winning margin over its nearest competitor is not distinguishable from zero.
  Disposition: confirmed; the phase's single most important finding.
- **D-02:** Block-bootstrap intervals with block-length sensitivity (1/4/8/28) show every
  AUSTIN_CORPUS_CHRISTI margin stable; at MIDLAND_EL_PASO, one margin's favourable exclusion flips at
  longer block lengths, and the frozen harness's own original interval method was already barely
  excluding zero for that margin before any correction. Disposition: confirmed; frozen intervals
  optimistic at Midland.
- **D-02:** Direct pairwise comparisons (never computed in the frozen record) show `ml_cooling_corrected`
  distinguishable from the other real candidates in only one of eight comparisons across both corridors.
  Disposition: confirmed; "wins" overstates the pairwise evidence.
- **D-02:** MAE and RMSE disagree in ranking at MIDLAND_EL_PASO in both the frozen record's own numbers
  and this replication — `reference_ml_refit_24h` has the better RMSE where `ml_cooling_corrected` has
  the (thin, now-replicated-as-fragile) MAE edge. Disposition: confirmed, consistent with the frozen
  record's own numbers.
- **D-02:** A fresh chronological period (starting 2026-09-30, 56-row/14-day minimum) is formally
  reserved for any future confirmation claim; zero rows are available as of this audit's run date.
  Disposition: confirmed limitation, reservation made.
- **D-03 (Conservative-rating analysis):** Overrating frequency, magnitude, and duration measured per
  candidate at both corridors; overrating concentrates sharply below the measured convection crossover
  (100% vs. 80.2%/78.9% just above it) — the low-wind finding D-04 bullet 6 above explains. Disposition:
  confirmed, genuinely new analysis axis.
- **D-03:** Calibrated lower quantiles (alpha 0.05/0.10) fit, calibrated, and checked on three
  chronologically disjoint periods; calibration improves the evaluate-period exceedance rate for all but
  one (candidate, alpha) pair, named rather than hidden. Disposition: confirmed.
- **D-03:** At a matched 5% overrating rate, `ml_cooling_corrected` retains the most usable capacity of
  any real candidate at both corridors, ahead of persistence and the static rating. Disposition:
  confirmed; this phase's headline new metric.
- **D-03:** Every reliability claim in this section is explicitly scoped to self-consistency against a
  reanalysis-derived truth series, never conductor-level field-validated safety. Disposition: confirmed,
  stated before the section's first number and repeated throughout.
- **D-04 (Corrected language):** All six items corrected or confirmed via the append-only, byte-identity-
  gated amendment to the frozen record (table above). Disposition: confirmed, all six closed.
- **D-05 (Integration readiness plan):** Deferred to Plan 04-06 — not produced by this plan. This
  record's own recommendation above (keep both candidates live) is the input Plan 04-06's
  integration-readiness plan should carry forward, not a substitute for it.

**Confidence statement.** Every load-bearing claim in this document rests on exactly one of three named bases
(`## Audit bases` above): **SYNTHETIC** basis supports only that the harness's own code (the block
bootstrap's reduction to i.i.d., the quantile pipeline's disjointness assertions, the leakage probe's
sabotage test) is implemented correctly — it proves nothing about this project's real corridors.
**ABLATION** basis — every number in the D-02 strengthened comparison and the D-03 conservative-rating
analysis, including the replication/contradiction finding above and the matched-rate retained-capacity
table — supports replication of the frozen record's own candidate ordering and relative-ordering
findings between candidates; it does **not** support a confirmation claim, because this exact calendar
range was already assembled and read during Phase 3's own development and validation-split runs.
**FRESH** basis is the only basis on which this audit may make a confirmation claim, and it is measured,
not assumed, at **0 rows for both corridors** as of this audit's run date (2026-09-30) — "yesterday UTC"
resolves to exactly the frozen window's own last day, leaving zero calendar time from which to draw a
genuinely fresh row today. Stated plainly so no later reader upgrades a replication to a confirmation by
omission: **not a confirmation — no claim in this record is a confirmation on a genuinely fresh
chronological period** —
every comparative, calibration, and retained-capacity number above is an ABLATION-basis replication or
ablation-study finding, bounded by the same already-seen calendar range Phase 3's own development used.
An audit that quietly treated an ABLATION-basis replication as a confirmation would have repeated
exactly the error it was convened to find.

## Limitations

What this audit could not establish, and why — each marked **permanent** (a limitation of the data
available that no amount of calendar time alone would remove) or **removable** (by calendar time
accruing a FRESH basis, or by Plan 04-06's minimum data contract):

- **The fresh-basis row count is zero.** As of this audit's run date, the FRESH basis (rows strictly
  after `FROZEN_WINDOW_END`) is measured at 0 rows for both corridors — "yesterday UTC" resolves to the
  frozen window's own last day. No comparative, calibration, or retained-capacity number in this record
  is a confirmation on genuinely fresh data; every one is an ABLATION-basis replication. **Removable**
  by calendar time: the basis accrues 4 corridor rows per calendar day at this lead's exact-lead filter,
  and reaches the reserved 56-row/14-day minimum roughly two weeks after this audit's run date.
- **Every "truth" value this audit's numbers are checked against is itself a physics-model reanalysis
  output (ERA5/ERA5-Land), never a sensor measurement** — carried forward from the D-01 finding this
  audit's own code-level re-read confirmed, previously undisclosed in the frozen record. Agreement
  between a candidate and this truth series is agreement between two model outputs, not field-validated
  accuracy. **Permanent** for this project's current data sources; **removable** only by Plan 04-06's
  minimum data contract, which names sensor-measured conductor temperature or line-side current
  observations as the prerequisite for closing this gap.
- **The ABLATION basis was already seen during Phase 3's own development.** Every number this audit
  computed on it (the replication/contradiction finding, the block-bootstrap sensitivity sweep, the
  overrating and retained-capacity tables) is a relative-ordering or ablation-study finding, not new
  evidence in the sense a genuinely unseen holdout would provide. **Permanent** for this calendar range;
  **removable** going forward only via the reserved FRESH period above.
- **The single pinned weather model, the single conductor configuration, and the two-endpoint
  weakest-link proxy** — all three carried forward unchanged from the frozen record's own Limitations
  section. This audit neither strengthened nor narrowed any of the three: every number in this document,
  like every number in the frozen record, rests on exactly one pinned NWP model (`gfs_seamless`), one
  shared `ConductorConfig` (795 kcmil Drake ACSR) across both corridors, and the weakest-link minimum of
  two endpoint cities as the corridor-level proxy. **Permanent** without a second NWP source, a richer
  corridor-discretization dataset, or a different conductor configuration to test against.
- **The fitted arms this audit scored are not the same fitted objects Phase 3's frozen run scored.**
  `ml_wind_corrected`, `ml_cooling_corrected`, and `reference_ml_refit_24h` were refit on ABLATION TRAIN
  rows alone for this audit's own replication (a genuinely held-out re-run for this phase's purposes),
  never on the frozen harness's own train+val convention. No number in this record is row-for-row
  comparable to a frozen one — only the qualitative ordering and the direction of disagreement are
  comparable. **Permanent**, by design: a row-for-row comparable re-run would require re-scoring the
  frozen test set itself, which `04-CONTEXT.md`'s Phase Boundary forbids outright.
- **The leakage probe's demonstrated power (Mode B) was never actually exercised against the frozen
  run's own callable shape (Mode A).** This audit's own re-run closes the evidentiary gap for the seven
  real arms on real ABLATION rows, but it does not retroactively re-run the probe against the frozen
  test-set run itself — that run is not re-executable without re-scoring the frozen test set, which this
  phase does not do. **Permanent** for the frozen run specifically; **removable** in spirit only by a
  future phase building the probe into the scoring path itself before any future frozen run.
- **This audit's own statistical machinery (block bootstrap, pairwise comparisons, quantile
  calibration) has not itself been re-examined under the SAME multiple-comparisons discipline D-02
  flags for the frozen record.** Six candidates were compared pairwise in this audit's own D-02 work
  without a formal multiple-comparisons correction, mirroring the exact scrutiny this record directs at
  the frozen record's own single-read discovery-and-confirmation conflation. **Permanent** for this
  phase's own ABLATION-basis work; worth a dedicated correction (e.g., Holm-Bonferroni across the
  pairwise table) if a future phase treats any single pairwise margin in this record as decisive on its
  own.
- **The low-wind sensitivity sweep and the sub-floor routing finding (D-04 bullet 6) are measured at one
  representative ambient temperature (35.0°C) and one representative solar irradiance, not across the
  full observed range of either.** The crossover wind speed moves with ambient temperature (it scales
  with `(T_max - T_amb)^1.25`), so the measured 0.1428 m/s crossover is representative, not universal.
  **Removable** by re-running the same sweep across the full observed ambient-temperature range, a
  bounded extension this phase's own code already supports via the `air_temp_c` keyword.

## Integration readiness plan (D-05)

This section is a plan, not an implementation. Nothing in it builds any part of an integration —
no packaging artifact exists, no runtime forecast fetch has been added to a production module, and
no monitoring hook or change to `ampacity_forecast.py` or its method registry has been made.
`04-CONTEXT.md`'s Deferred Ideas name building any of this as explicitly out of this phase's scope.

### Candidates, and why they perform as they do

Both `ml_cooling_corrected` and `reference_ml_refit_24h` remain live integration candidates.
Neither is narrowed away on this phase's evidence — the Corrected verdict above already says so,
and the ablation below explains *why* the refit model performs as well as it does without
resolving which of the two candidates should ultimately be preferred.

The frozen record's own Open Question — why the reference `"ml"` model reversed from a loss at
60 minutes (Phase 1) to a win at 24 hours (Phase 3) — is answered here by a measurement, not a
second deferral. `lag_vs_covariate_ablation` fit three variants of the SAME refit-reference
estimator family on the real ABLATION train rows, differing only in which named feature columns
each received, and scored all three on the real ABLATION validation rows:

| Corridor | Variant | MAE (A) | RMSE (A) | Margin vs. all-features MAE |
|---|---|---|---|---|
| AUSTIN_CORPUS_CHRISTI | all_features | 127.215 | 161.639 | — |
| AUSTIN_CORPUS_CHRISTI | lags_only | 131.983 | 165.013 | all-features wins by 4.768 A, 95% CI [0.727, 8.879] (excludes zero) |
| AUSTIN_CORPUS_CHRISTI | covariates_only | 127.759 | 162.042 | all-features wins by 0.545 A, 95% CI [-0.986, 2.046] (does not exclude zero) |
| MIDLAND_EL_PASO | all_features | 136.558 | 166.750 | — |
| MIDLAND_EL_PASO | lags_only | 131.450 | 162.529 | lags-only wins by 5.108 A, 95% CI [-8.504, -1.732] (excludes zero) |
| MIDLAND_EL_PASO | covariates_only | 137.636 | 168.501 | all-features wins by 1.078 A, 95% CI [-0.070, 2.271] (does not exclude zero) |

The verdict differs by corridor. At AUSTIN_CORPUS_CHRISTI the covariates-only variant approaches
the full model's own skill (a 0.545 A MAE gap, statistically indistinguishable from the
all-features variant) while the lags-only variant does not (a 4.768 A gap that DOES exclude zero)
— the pattern the frozen record's own explanation predicts, and it SUPPORTS the hypothesis that
the non-lag weather covariates carry the skill the lag features lose as they go stale over a
24-hour horizon. At MIDLAND_EL_PASO the opposite pattern holds: the lags-only variant is
measurably closer to (in fact slightly better than) the full model, and the covariates-only
variant is the one that falls away — this DOES NOT SUPPORT the frozen record's proposed
explanation at this corridor. Taken together, the ablation's own finding is itself corridor-
dependent: the refit model's 24-hour skill is not explained by one single mechanism at both
corridors, and a reader should not generalize the Austin pattern to Midland or vice versa.

**The cooling-rediscovery hypothesis.** `cooling_rediscovery_hypothesis` tested the sharper
question D-05 actually asks: is the refit model (or, more precisely, its covariates-only variant)
implicitly rediscovering a cooling-like correction, or doing something else? Residual correlation
is the informative measure here — two models can produce highly correlated PREDICTIONS simply
because both track the same strong diurnal ampacity signal, while correlated RESIDUALS mean the
two models are failing in the SAME places, which is the signature of a shared mechanism rather
than a shared target:

| Corridor | Variant | Prediction correlation (Pearson) | Residual correlation (Pearson) | Residual correlation (Spearman) |
|---|---|---|---|---|
| AUSTIN_CORPUS_CHRISTI | all_features | 0.590 | 0.849 | 0.846 |
| AUSTIN_CORPUS_CHRISTI | lags_only | 0.470 | 0.831 | 0.829 |
| AUSTIN_CORPUS_CHRISTI | covariates_only | 0.583 | 0.846 | 0.844 |
| MIDLAND_EL_PASO | all_features | 0.542 | 0.806 | 0.822 |
| MIDLAND_EL_PASO | lags_only | 0.449 | 0.781 | 0.787 |
| MIDLAND_EL_PASO | covariates_only | 0.531 | 0.803 | 0.821 |

The covariates-only variant's residual correlation against `ml_cooling_corrected`'s own residuals
(0.846 at Austin, 0.803 at Midland) is high, comparable to the full-feature variant's own
correlation, and noticeably higher than the lags-only variant's. A high residual correlation here
is CONSISTENT WITH — but does not PROVE — the covariates-only variant implicitly rediscovering a
cooling-like correction, since two models trained on the same series can share an error structure
for reasons that have nothing to do with the convective term (both are, after all, trying to
predict the same physically-driven ampacity series). What remains unexplained after this ablation:
why the lags-only variant ALSO shows a substantial residual correlation (0.831 / 0.781) against the
cooling correction, nearly as high as the full-feature variant's — a pure rediscovery story would
predict a sharper gap between the lags-only and covariates-only correlations than what was
measured. An explanation that would close this gap: the lag features themselves encode a smoothed
proxy for recent cooling trends (a dlr_amps lag IS partly a function of recent wind and temperature
history), so even the "lags only" variant is not actually blind to cooling-relevant information —
only a feature-level ablation finer than lag-vs-covariate (e.g., decorrelating lagged ampacity from
its own underlying weather drivers) could separate these two explanations further, and that is
itself a "now" item in the split below.

### The minimum data contract

A field-level specification, because a vague instruction to improve the inputs is not a data
contract — a contract is a list of named fields with types, units, cadences and owners, each
traceable to something this audit actually found. Every row below cites the finding that motivates
it and names a real field, never a stand-in to be named later.

| Field | Type | Unit | Cadence | Required/Desirable | Owner | Motivating finding |
|---|---|---|---|---|---|---|
| `forecast_model_id` | string | n/a | per-run, static once pinned | Required | Pipeline/data team | Mirrors `open_meteo_forecast_provider.py`'s own pinning discipline (`FORECAST_MODEL_ID`/`PREVIOUS_RUNS_MODEL_ID`) — an un-pinned model selection silently resolves to a different model domain per endpoint (D-01). |
| `forecast_value` | float | project-native (m/s, degC, W/m^2 per variable) | hourly | Required | Pipeline/data team | Finding 1 / the null-handling discipline: an absent forecast value must never be padded, truncated, or zero-filled — it is a failed fetch, and the contract must carry the value as nullable rather than defaulted. |
| `forecast_lead_hours` | float | hours | per-row | Required | Pipeline/data team | D-01 Finding 4 — lead must be carried explicitly on the record itself, not re-derived after the fact from an init/valid difference that archive-to-archive comparison cannot evidence. |
| `initialization_timestamp` | datetime (UTC, ISO-8601) | n/a | per-run | Required | Pipeline/data team | D-01 Finding 4 — the model-run issuance instant, the first of the three distinct timestamps this contract requires. |
| `availability_timestamp` | datetime (UTC, ISO-8601), recorded at ingestion | n/a | per-run | Required | Ingestion team | D-01 Finding 4 — the audit's central finding: two retrospective archives can prove a value MATCHES a run issued `lead_hours` earlier, but cannot evidence that the value was actually available to a consumer at that wall-clock instant. Nothing except a timestamp recorded live, at ingestion, closes this gap. |
| `valid_timestamp` | datetime (UTC, ISO-8601) | n/a | per-row | Required | Pipeline/data team | D-01 Finding 5 — the exhaustive time-reference partition found exactly two clock instants per row (decision time, valid time) in every column this audit's assembled frames carry; a contract must keep that partition explicit rather than collapsing it. |
| `observed_dlr_amps` | float | amps | hourly or finer | Required | Field/instrumentation team | D-01 Finding 1 — the entire "truth" side of this project's experiments is itself a physics-model reanalysis output, never a sensor measurement; D-03's reanalysis-scope limitation says plainly that no claim in this record establishes conductor-level safety without one. |
| `observed_air_temp` | float | degC | hourly | Required | Field/instrumentation team | Same as `observed_dlr_amps` — a sensor-measured input is needed for an independent ampacity computation, not only a sensor-measured output. |
| `observed_wind_speed` | float | m/s | hourly | Required | Field/instrumentation team | Same. |
| `observed_wind_direction` | float | degrees | hourly | Desirable | Field/instrumentation team | Improves the perpendicular-wind projection D-03's regime analysis already depends on (`thermal_model.perpendicular_wind`). |
| `observation_quality_flag` | categorical (`ok`/`suspect`/`missing`/`out_of_range`) | n/a | per-observation | Required | Field/instrumentation team | D-03's reanalysis-scope limitation, read forward: without a quality flag, a single bad sensor reading could silently become a false field-validated safety claim rather than a flagged, excluded one. |
| `observation_availability_timestamp` | datetime (UTC), recorded at ingestion | n/a | per-observation | Required | Ingestion team | The same decision-time-availability reasoning as `availability_timestamp` above, applied to local observations rather than archived forecasts — a local reading has its own ingestion-time availability question too. |
| `unit_of_record` | string (SI unit code) | n/a | static, per field | Required | Data team | Finding 1's own citation discipline, generalized: this project's existing `units_def.PIPELINE_SCHEMA` convention already names every pipeline field's unit explicitly; a new external field entering the pipeline must do the same rather than relying on an assumed convention. |
| `sensor_location` | lat/lon (float pair) | degrees | static | Required | Field team | Needed to map a sensor reading onto a specific corridor endpoint — without it, an observation cannot be attributed to either city in a two-endpoint corridor. |
| `sensor_height_above_ground` | float | meters | static | Required | Field team | D-03's low-wind finding: overrating concentrates at 100% below the measured convection crossover, and the physics consumes a wind speed AT CONDUCTOR HEIGHT. Wind speed varies with height (the atmospheric boundary layer's own log-wind profile); a sensor reading with no recorded height cannot be corrected to conductor height, and a surface-level reading misapplied as a conductor-height reading would bias the regime the data already shows is most overrating-prone. |
| `sensor_exposure_class` | categorical (`open`/`sheltered`/`obstructed`) | n/a | static | Desirable | Field team | An obstructed site could bias readings specifically in the low-wind regime D-03 already found to be the most overrating-sensitive. |
| `conductor_type_per_span` | string (e.g. ACSR code) | n/a | static, per span | Required | Engineering team | The frozen record's own Limitations section states this project uses a single, shared conductor configuration across both corridors — a per-span field is what would replace that assumption with measured per-span truth. |
| `span_geometry` | structured (endpoint coordinates, length, bearing) | meters / degrees | static, per span | Required | Engineering team | The frozen record's and this audit's shared weakest-link-proxy limitation — the two-endpoint-minimum convention is a documented proxy for a richer, per-span discretization this field would enable. |
| `span_count_per_corridor` | integer | n/a | static | Desirable | Engineering team | Same — replacing the two-endpoint proxy with the actual number of discretizable spans a corridor contains. |

### Timestamps: why three, not one

Collapsing these into one timestamp is the error this contract exists to prevent, so they get
their own subsection rather than living only as three table rows.

- **`initialization_timestamp`** — when the forecast model run was ISSUED. A data engineer can
  implement this directly from the NWP provider's own run-identifier field (mirroring
  `open_meteo_forecast_provider.py`'s own `run=<timestamp>` parameter for the Single-Runs
  endpoint). Closes no audit finding on its own — it is the baseline the other two timestamps are
  measured relative to.
- **`availability_timestamp`** — when the run's OUTPUT became available for a consumer to fetch,
  recorded live at ingestion time, never reconstructed after the fact from two archives' agreement.
  This is the field that closes D-01 Finding 4 — this audit's own finding that two backward-looking
  archives can prove a value corresponds, by construction, to a run issued `lead_hours` earlier, but
  cannot and structurally never could prove that value was actually reachable over a network at that
  wall-clock moment. Without this field recorded at ingestion time, going forward, no future
  experiment can make a decision-time-availability claim any stronger than this audit's own could.
- **`valid_timestamp`** — the time the forecast VALUE is valid for (the moment being predicted). A
  data engineer implements this as the NWP provider's own forecast-hour offset applied to
  `initialization_timestamp`. Closes D-01 Finding 5's exhaustive time-reference partition — every
  column in this project's assembled frames already resolves to exactly one of two clock instants
  (decision time or valid time), and this field is what keeps that partition intact going forward
  rather than letting it collapse back into one ambiguous "timestamp" column.

### Now versus later

Every recommendation this audit produced sits in exactly one of the two tables below.

**Table 1 — the ML track can do this now, with existing data and tools.**

| Recommendation | Owner | Rough size |
|---|---|---|
| Re-tune arm 3/4's pooling and target-parameterization selection against real (not synthetic) development data, closing D-02's synthetic-configuration-selection limitation | ML track | Medium |
| Run the FRESH-basis confirmation once the reserved period accrues its 56-row/14-day minimum (roughly two weeks after this audit's run date) | ML track | Small — one scheduled script run |
| Apply a formal multiple-comparisons correction (e.g. Holm-Bonferroni) across D-02's own uncorrected pairwise table, closing this audit's own D-04 Limitations item about its own statistical machinery | ML track | Small |
| Extend the low-wind sensitivity sweep across the full observed ambient-temperature range, closing a named D-04 Limitations item (the measured 0.1428 m/s crossover is representative at 35.0°C, not universal) | ML track | Small |
| Harden `predict_cooling_correction`'s guard so a positive, below-the-natural-convection-floor corrected term is explicitly rejected rather than permitted through the `q_conv_override` seam — the exposure this audit's own sub-floor-routing attempt found and measured | ML track (owns `forecast_correction_models.py`) | Small |
| Build the leakage probe into the scoring path itself for any future frozen run, so a future audit does not need a retroactive re-run (D-01 Finding 6's remaining gap) | ML track | Medium — a process change for the next experiment, not a fix to this one |

**Table 2 — blocked on the data contract above.**

| Recommendation | Blocked on | Why |
|---|---|---|
| Any claim that a candidate's conservative-rating behavior reflects field-validated conductor safety, not self-consistency with a reanalysis simulation (D-03's reanalysis-scope limitation) | `observed_dlr_amps`, `observed_air_temp`, `observed_wind_speed`, `observation_quality_flag`, `observation_availability_timestamp` | D-03's every overrating, calibration, and retained-capacity number is checked against the same reanalysis-derived truth series Finding 1 names — only a sensor-measured series closes this gap. |
| A genuine decision-time-availability claim for any future forecast-lead calibration, stronger than "two archives agree" | `availability_timestamp` | D-01 Finding 4 is structural: no archive-to-archive comparison can ever evidence real-time availability, regardless of archive depth. |
| Replacing the two-endpoint weakest-link proxy with a richer, per-span corridor discretization | `conductor_type_per_span`, `span_geometry`, `span_count_per_corridor` | The frozen record's own Limitations and this audit's D-03 section both carry the weakest-link proxy forward unchanged — a richer dataset is what would let a future phase measure, not assume, whether the proxy is conservative. |
| Testing model-choice sensitivity against a second, independently-provisioned NWP source | `forecast_model_id` (a second pinned value) plus its own `forecast_value`/timestamps | The frozen record's Limitations section already names the single-pinned-NWP-model scope as a limitation this audit neither strengthened nor narrowed; a second source is what a future comparison would need. |
| Wiring a corrected-model candidate's runtime forecast fetch into a production module | `initialization_timestamp`, `availability_timestamp`, `valid_timestamp`, `forecast_value`, `forecast_lead_hours` | The packaging/fetch outline below can be scoped now, but cannot be implemented without a live forecast source carrying all three timestamps distinctly — exactly the gap D-05 was convened to specify. |
| Correcting any sensor-height-dependent bias in the low-wind regime D-03 already found to be most overrating-sensitive | `sensor_height_above_ground`, `sensor_exposure_class` | Without a recorded sensor height, a surface-level reading cannot be corrected to the conductor-height wind speed the physics consumes. |

### Packaging

A fitted correction model (whichever of the two candidates, or a future successor, is eventually
chosen) would be persisted, versioned, and loaded the SAME way `forecast_training.
persist_corridor_model`/`ampacity_forecast._load_corridor_model` already do for the production "ml"
method today — an atomic `joblib.dump` to a temp file, `os.replace`d onto a per-corridor path, with
a version tag recorded alongside the artifact so a loader can refuse a stale or incompatible file
rather than silently deserializing one. It would sit BEHIND `ampacity_forecast.py`'s existing
`forecast_ampacity(history, horizon_min, method=...)` signature and `ForecastResult` schema — a new
entry in `FORECAST_METHODS` (alongside `"naive"`, `"ewm"`, `"ml"`), never a change to the function's
signature or to `forecast_columns()`'s four-key `PIPELINE_SCHEMA` mapping. This mirrors exactly the
precedent the `"ml"` method itself already set for FCST-01/FCST-02, and preserves the public
interface contract this workstream's own `ROADMAP.md` names as not renegotiable.

### Runtime forecast fetching

The corrected candidate's 24-hour lead would be served by Open-Meteo's Previous-Runs endpoint
(`previous-runs-api.open-meteo.com`), the same primary data source this phase's own ABLATION and
Phase 3's frozen comparison already use — not a new, unvetted source. Cadence would match the
pipeline's own existing measurement cycle (hourly, per `DLRSafetyMonitor.run_check`'s own calling
convention), with the fetched forecast cached per corridor between cycles rather than re-fetched on
every call, since the provider's own archive updates at most once per model run. The request budget
against the provider's documented limits would need to be sized against this project's four-city,
two-corridor footprint before any production cutover — a concrete sizing exercise, not estimated
here, since it depends on the provider's own rate-limit terms at integration time.

### Stale and missing data

At a 24-hour lead, a forecast is stale once its own `initialization_timestamp` is further in the
past than this project's own measured effective lead (`24 + hour % 6` hours, per Phase 3's D-04
finding) would predict for the current valid time — i.e., the fetched run is not the run that
SHOULD cover the current decision. Staleness is detected the same way `open_meteo_forecast_
provider.py`'s own completeness check already works: comparing the fetched run's own carried
timestamp fields against the expected ones, not by trusting the provider's HTTP 200 status alone.
That module's own null-handling discipline — nothing is ever padded, truncated, zero-filled,
forward-filled, or back-filled; an absent value is a failed fetch, never a null column — is the
exact discipline this stale-data check must also apply once it is live in production rather than in
an offline harness: a stale OR missing forecast is the SAME signal, and both route to the identical
fallback below.

### Fallback

The standing commitment is not negotiable here: a failed, stale, or incomplete forecast fetch
degrades to a KNOWN-SAFE path, never to an optimistic guess — this project's own
`REQUIREMENTS.md` "Out of Scope" table names changing this fail-safe contract as explicitly out of
this entire workstream's scope, and D-05's own fifth bullet names the same commitment specifically
for forecast fallback. The concrete existing mechanism this mirrors is `DLRSafetyMonitor`'s own G6
gate: `anomaly_detector.check(...)` is wrapped in `except Exception`, and ANY failure — not only an
anomalous result, but a broken call itself — resolves to `self.static_rating`, the corridor's
nameplate rating, never a computed value that happens to look plausible. A corrected-forecast
integration would route through the identical pattern, as an explicit degradation ladder:

1. **Rung 1 — the corrected forecast.** Requires a fresh, complete, on-time forecast fetch with all
   three timestamp fields present and consistent. Gives the full candidate accuracy this audit
   measured.
2. **Rung 2 — the raw (uncorrected) forecast through IEEE-738.** Requires only that the underlying
   weather forecast itself fetched successfully; gives up the correction's own measured headroom
   (this audit's own ablation and D-02's pairwise work both bound how much that headroom actually
   is) but keeps a physics-informed forecast.
3. **Rung 3 — persistence (the last known-good value, lagged).** Requires nothing beyond the
   pipeline's own existing last-observed-value path; gives up any forecast skill at all beyond
   simple extrapolation.
4. **Rung 4 — the corridor's static rating.** Requires nothing. This is the known-safe floor every
   rung above is permitted to fall back to, and the ONLY rung this fallback may ever resolve to on
   any genuine failure — mirroring G6's own `_fallback(result, "G6", ..., self.static_rating)` call
   exactly.

No rung in this ladder is permitted to substitute an "optimistic" value for a missing one at any
stage — a forecast that cannot be trusted degrades toward the static rating, never toward a
guessed number dressed up as a measurement.

### Shadow evaluation before cutover

The candidate would run alongside the incumbent `"ml"` method for a defined observation window,
computing and logging its own prediction and confidence band on every cycle WITHOUT that prediction
ever reaching `DLRSafetyMonitor.run_check`'s own rating decision — an additive, observation-only
path, the same non-interference discipline `anomaly_detector`'s own G6 injection already
established for C10 ("None = C10 disabled, G1-G5 untouched" per `DLRSafetyMonitor.py`'s own
docstring). What would be logged: the candidate's own point prediction, its confidence band, the
incumbent method's prediction on the same cycle, and whichever of the two this audit's own
conservative-rating or pairwise-margin work would eventually need to re-measure once live data
accrues. What would justify cutover: a FRESH-basis (not ABLATION-basis) measurement reproducing, on
genuinely new rows, the Corrected verdict's own stated bar for confidence — specifically, the same
distinguishable margin and the same matched-overrating-rate retained-capacity advantage this phase
measured on the ABLATION basis, now measured on data neither this phase nor Phase 3 has already
seen.

### Monitoring

Once live, at minimum: the overrating rate this audit's own D-03 analysis introduced, measured
continuously against whatever truth source is available at that point (the reanalysis-derived
series today, a sensor-measured one once the data contract above is satisfied); the pinball
loss/exceedance rate of any deployed lower-ampacity quantile, the same measure D-03's own
calibration work already established; and the shadow-vs-incumbent prediction divergence from the
evaluation above, continued past cutover rather than discarded. A threshold that would raise an
alarm: the live overrating rate exceeding, by a stated margin, the rate this phase measured on the
ABLATION basis for the same candidate — a live rate meaningfully worse than the offline measurement
would mean the offline numbers no longer describe production behavior.

### Rollback

Triggered by: the monitoring threshold above firing, a sustained increase in the fallback rate at
the packaging layer (a proxy for forecast-fetch reliability degrading), or a manual override by
whoever owns production operation. Mechanism: revert `FORECAST_METHODS`'s default back to the
incumbent `"ml"` method for the affected corridor — the SAME kind of single-value configuration
change this project's own method-registry pattern already makes cheap, never a code rollback of the
packaging itself. Time to execute: bounded by how quickly that configuration change propagates to
the running pipeline, which is an operational question for whoever owns deployment at integration
time, not estimated here. State returned to: the incumbent `"ml"` method's own existing behavior,
unchanged by anything this plan proposes — the new method's packaged artifact remains on disk,
available to re-enable once whatever triggered the rollback is resolved.

### The product question, named and left open

This audit cannot determine, and was not convened to determine, whether the product needs
60-minute forecasting, 24-hour forecasting, or both — and the 24-hour result measured throughout
this phase does not settle that question. No integration of the 24-hour-lead candidates (either
`ml_cooling_corrected` or `reference_ml_refit_24h`) is recommended as a blanket replacement for the
production 60-minute `"ml"` method until this question is answered. This is unresolved, and it is
assigned to whoever owns product scope for this project — not to the ML track, and not to this
audit. What an answer would need to consider: how far ahead a DLR-informed operating decision
actually acts on a forecast (a 60-minute lead serves a materially different operational use than a
24-hour lead), and whether the two horizons in fact serve two different decisions entirely (e.g. a
short-horizon dispatch decision versus a day-ahead planning decision) rather than one horizon simply
superseding the other. Until that scoping decision is made, both horizons' own existing production
and experimental paths should be left as they are.

## References

**The record under audit, and its appended amendment.**

- `docs/data-science/decisions/forecast_correction_experiment.md` — the frozen record under audit,
  read-only to this document except for Plan 04-05's permitted append-only `## Follow-up Audit
  Amendment (Phase 4, D-04)` section.
- `.planning/workstreams/ml-modeling/ROADMAP.md`'s `### Phase 3: Ampacity Forecast Correction
  Experiment` entry — the frozen record's own closing ROADMAP disposition, five success criteria
  each marked MET.

**This phase's own locked scope and research.**

- `.planning/workstreams/ml-modeling/phases/04-forecast-correction-experiment-follow-up-audit-data-provenan/04-CONTEXT.md`
  — this phase's locked scope (D-01 through D-05).
- `.planning/workstreams/ml-modeling/phases/04-forecast-correction-experiment-follow-up-audit-data-provenan/04-RESEARCH.md`
  — the persisted-artifact scope gap and fresh-holdout constraint that shape this phase.
- `.planning/workstreams/ml-modeling/phases/04-forecast-correction-experiment-follow-up-audit-data-provenan/04-PATTERNS.md`
  — the reusable patterns (named audit bases, the frozen-window guard, the dispositions-table
  convention) every plan in this phase, including this one, followed.

**All six Phase 4 plan summaries.**

- `.planning/workstreams/ml-modeling/phases/04-forecast-correction-experiment-follow-up-audit-data-provenan/04-01-SUMMARY.md`
  — the audit spine, the three named bases, and the first provenance finding.
- `.planning/workstreams/ml-modeling/phases/04-forecast-correction-experiment-follow-up-audit-data-provenan/04-02-SUMMARY.md`
  — the data-provenance re-audit closing all five D-01 bullets.
- `.planning/workstreams/ml-modeling/phases/04-forecast-correction-experiment-follow-up-audit-data-provenan/04-03-SUMMARY.md`
  — the strengthened block-bootstrap comparison and the Austin-replicates/Midland-contradicted
  finding.
- `.planning/workstreams/ml-modeling/phases/04-forecast-correction-experiment-follow-up-audit-data-provenan/04-04-SUMMARY.md`
  — the conservative-rating analysis, the measured convection crossover, and the matched-
  overrating-rate retained-capacity headline.
- `.planning/workstreams/ml-modeling/phases/04-forecast-correction-experiment-follow-up-audit-data-provenan/04-05-SUMMARY.md`
  — the low-wind-sensitivity-is-physics measurement, the frozen record's six-item amendment, and
  this record's own corrected verdict.
- `.planning/workstreams/ml-modeling/phases/04-forecast-correction-experiment-follow-up-audit-data-provenan/04-06-SUMMARY.md`
  — this plan's own closing summary: the lag-versus-covariate ablation, the integration-readiness
  plan above, and the project's AI-use disclosure.

**The audit module and its tests.**

- `backend/forecast_experiment_audit.py` — every audit routine this phase built, including this
  plan's own `lag_vs_covariate_ablation`/`cooling_rediscovery_hypothesis`.
- `backend/tests/forecast_experiment_audit_test.py` — the full test suite backing every routine
  above, network-free throughout.

**The harness and production modules under audit (read, never modified by this phase).**

- `backend/forecast_experiment.py` — the harness under audit (assembly, filtering, scoring, boundary
  computation).
- `backend/open_meteo_provider.py` — the truth-source provider module (Archive API / ERA5-ERA5-Land
  reanalysis).
- `backend/open_meteo_forecast_provider.py` — the forecast-archive provider module (Previous-Runs,
  Single-Runs, Historical-Forecast endpoints) this plan's runtime-fetch outline builds on.
- `backend/ampacity_forecast.py` — the production forecasting interface
  (`forecast_ampacity`/`ForecastResult`/`forecast_columns`) this plan's packaging outline fits
  behind without changing.
- `backend/DLRSafetyMonitor.py` — the G6 safety gate whose fail-safe resolution this plan's fallback
  ladder mirrors.
- `.planning/workstreams/ml-modeling/REQUIREMENTS.md` — the standing fail-safe commitment this
  plan's fallback section is not permitted to renegotiate.

**Git-ignored evidence, not the artifact of record.** Every JSON report named below is generated,
reproducible, and gitignored — this document, not any report file, is the citable record. Re-running
the function named alongside each path reproduces it from the real repository:

- `data/experiment/audit_basis_manifest.json` — `build_basis_manifest()`, Plan 04-01.
- `data/experiment/leakage_probe_coverage_report_<CORRIDOR>.json` — `leakage_probe_coverage_report(corridor)`, Plan 04-02.
- `data/experiment/audit_ablation_report_<CORRIDOR>.json` — `ablation_basis_report(corridor)`, Plan 04-03.
- `data/experiment/audit_overrating_report_<CORRIDOR>.json` — `overrating_basis_report(corridor)`, Plan 04-04.
- `data/experiment/audit_ablation_features_<CORRIDOR>.json` — `lag_vs_covariate_ablation(corridor)` /
  `cooling_rediscovery_hypothesis(corridor)`, this plan (Plan 04-06) — the per-variant MAE/RMSE/
  margins and the cooling-rediscovery correlations transcribed into this section above.
