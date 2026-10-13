<!-- generated-by: gsd-doc-writer -->
# Confirmation Protocol v3 — Per-City Amendment (DRAFT)

> **DRAFT — not in force until the project owner signs the block at the end. The owner's selections for all eleven decisions were recorded in review on 2026-10-13 (see "Owner selections" below); nothing here has been decided by the drafter.**
>
> This document was written to be reviewed and signed by the project owner. Every statement of the
> form "recommended" is the drafter's suggestion, not a decision. Where this draft restates a decision
> the owner or team has already made, it says so and cites where that decision is recorded. Until the
> sign-off block at the end is completed, the confirmation protocol in force is still v2 in
> `forecast_correction_followup_audit.md`, and the open items below have the "if the owner does nothing"
> consequence stated for each.

**Status:** Draft, written 2026-10-13. Amends the confirmation protocol for per-city scoring only.
**Supersedes (if signed):** v2, "Versioned, deadline-based confirmation protocol", but only for
per-city scoring of the four rating points. **Does not edit or replace** the frozen corridor-era record
(v1, v2, the 2026-10-06 correction, and every corridor-era table), which stays exactly as written.

**Related records:** `point_scope.md` (corridors retired 2026-10-12), `shadow_collection_runbook.md`
(collection, fit-window decision), `forecast_correction_followup_audit.md` (v1, project pivot, v2),
`forecasting_model.md` (the separate per-city C9 forecasting models).

**Anti-peeking statement for this draft.** While drafting this amendment, no predicted-versus-truth
outcome was computed, read or printed for any row whose `valid_time` is after 2026-09-29, and no scoring
was run. Only row counts, timestamps and `status` fields of the shadow logs were read (permitted by v2's
mechanical-health-check carve-out). All figures about expected accuracy below come from the
already-published development evidence in the audit record, not from shadow outcomes.

## Owner selections recorded in review (2026-10-13)

The project owner reviewed the eleven decisions and selected the options below. They are recorded here as
the owner's choices, **pending the owner's signature** at the end of this document; the per-decision
sections further down still show the full options, the drafter's recommendation and the "if the owner does
nothing" consequence, and are unchanged. Where a selection differs from the drafter's recommendation it is
marked.

| No. | Decision | Owner's selection | Same as recommendation? |
|---|---|---|---|
| 1 | Ranking and the 8% ceiling | **Option C: point-error ranking, no ceiling.** Rank on MAE/RMSE/bias with effect sizes and intervals; the 8% ceiling and retained capacity are not applied; the write-up states calibrated risk was not measured. The per-city port of the frozen harness covers point metrics only | Differs (the draft recommended A; see note 1) |
| 2 | Multiple-comparison family | **Option E with Holm: a pooled, city-clustered headline family of 9 tests** (3 candidate-vs-candidate, 3 correction-vs-`raw_forecast`, 3 candidate-vs-`persistence_24h`), Bonferroni bound 0.05/9; per-city results uncorrected and descriptive | Yes |
| 3 | 590-row gate | **Option A: v2 governs, score what exists.** No row gate; n, effective sample size and the unmet precision targets printed at the top of the result; the port passes `minimum_fresh_rows` explicitly | Yes |
| 4 | Corridor-era rows | **Option A: not counted, never merged.** Per-city scoring keys on `schema_version: 3` and `city` | Yes |
| 5 | Dates | **Option A: keep 2026-11-01, 2026-11-17 and 2026-11-24T00:00Z** | Yes |
| 6 | Collector cadence | **Option B: 4 cycles/day, one valid time per cycle, cron `0 0,6,12,18 * * *`.** If GitHub Actions limits are hit, revert to 2/day (a documented one-line change) | Yes |
| 7 | Truth source | **Option A: archive reanalysis only**, no secondary station check; every figure labelled reanalysis-derived, never sensor-validated | Yes |
| 8 | Ship rule | **Option D with X = 5 A:** three evidence levels ("supported", "indicated, not resolved", "not shown"); one method for all cities, "consistent" meaning the point estimate favours it in at least 3 of 4 cities; keep `ml_wind_corrected` unless an alternative is consistently better, fall back to `raw_forecast` if a correction is "not shown". **8c: `reference_ml_refit_24h`'s own target hour (decision time + 24 h) is its headline**, with the logged-`valid_time` score reported alongside, flagged | Yes |
| 9 | Scoring basis | **Option C, with the headline reversed from the draft's recommendation: both row sources, reported separately and never pooled; the reconstructed frames are the headline for choosing which candidate to ship; the shadow logs are the live-system check.** The question the 2026-11-24 evaluation answers is "which candidate to ship" | Differs (see note 2) |
| 10 | Duplicates and pairing | **Option A with (i):** first-logged row per `(city, valid_time)`; a pair is scored only where both candidates are `ok`; excluded duplicates counted and listed | Yes |
| 11 | Live weather model | **Option B: switch the live collector to `gfs_seamless`**, record `forecast_model` on every row, score only rows produced after the switch. Implemented together with decision 6 | Yes |

**Note 1 (decision 1).** With no ceiling and no calibrated metrics, the ranking among eligible candidates
rests on point error and the practical-benefit rule of decision 8. This is stated, not hidden: the result
will say that nothing about the calibrated overrating risk of any candidate was measured. The v1
requirement that a candidate pass an 8% achieved-overrating ceiling is therefore not applied in this
amendment; that is a weaker standard than v1 and the write-up must say so.

**Note 2 (decision 9) and what follows from it.** Making the reconstructed frames the headline means the
confirmation read needs a **per-city port of the frozen FRESH harness for point metrics** (the frozen harness
is corridor-only and has the 590-row gate). It must be built and verified on synthetic or already-inspected
development data only, never on FRESH outcomes, before 2026-11-17. It scores the same candidate definitions
the development record used (fit on the stated window, GFS Previous-Runs forecasts, archive-derived
anchors), so it is not affected by threats V1 or V5; the shadow logs, which are, serve as the live check.
The reconstructed frames also supply roughly 192 rows per city by the cutoff against about 69 to 126 from
the logs, which improves the resolving power of the headline. The scorer plan
(`.planning/workstreams/ml-modeling/quick/261013-285-plan-the-per-city-shadow-log-scorer/`) was written for the shadow logs only and
must be extended with this port before it is executed.

**Acknowledgements the owner makes by signing:** the fit-window deviation (recorded decision above), and
validity threats V1 to V6.

## Contents

1. [Why an amendment is needed](#why-an-amendment-is-needed)
2. [What v2 said, and what changes per city](#what-v2-said-and-what-changes-per-city)
3. [What does not change](#what-does-not-change)
4. [Recorded decision: fit window and the model freeze](#recorded-decision-fit-window-and-the-model-freeze)
5. [Evidence base: what the data looks like today](#evidence-base-what-the-data-looks-like-today)
6. [Known validity threats to scoring the live logs](#known-validity-threats-to-scoring-the-live-logs)
7. [Open owner decisions](#open-owner-decisions)
8. [Metrics the shadow-log scorer reports, and cannot report](#metrics-the-shadow-log-scorer-reports-and-cannot-report)
9. [Sign-off](#sign-off)
10. [What happens by default if unsigned by 2026-11-01](#what-happens-by-default-if-unsigned-by-2026-11-01)
11. [Change log](#change-log)

## Why an amendment is needed

v1 and v2 were written for two corridors (`AUSTIN_CORPUS_CHRISTI`, `MIDLAND_EL_PASO`), each scored as
the `min()` of two endpoint cities. On 2026-10-12 the project retired corridors (`point_scope.md`):
each of `AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND`, `EL_PASO` is now one independent rating point, the shadow
collector writes one log per city (`data/shadow/predictions/{CITY}.jsonl`, `schema_version: 3`), and the
shadow candidates were refit per city. `point_scope.md` and the runbook both leave open whether the
2026-11-24 date moves and whether corridor-era rows count; this amendment collects those and the other
protocol questions the change raises, so they are decided before any outcome is seen.

The frozen harness is **not** per-city. `backend/forecast_experiment_audit.py`
(`basis_evaluation_report`, `_fresh_confirmation_report`) is keyed on
`config.LEGACY_CORRIDOR_ENDPOINTS`, scores two-city corridors, and rejects any other key with a
`ValueError`. `point_scope.md` lists it as "Frozen, not migrated". It also reads its FRESH rows from the
experiment's reconstructed anchored frames (`forecast_experiment.corridor_anchored_pair_frame` over the
manifest's FRESH window), not from the shadow `.jsonl` logs <!-- VERIFY: drafter's reading of `_fresh_confirmation_report`; confirm with the code owner -->. Per-city scoring of the shadow logs therefore needs a new scorer
(specified in [the metrics section](#metrics-the-shadow-log-scorer-reports-and-cannot-report)); no such
scorer existed in `backend/` when this draft was written <!-- VERIFY: no per-city shadow-log scorer found in backend/ on 2026-10-13 -->.

## What v2 said, and what changes per city

### What v2 said (summary, with sources)

All of this is in `forecast_correction_followup_audit.md`, section "Versioned, deadline-based
confirmation protocol (v2 ...)", including its 2026-10-05 wording correction and its 2026-10-06
correction.

- Fixed model-freeze date 2026-11-01 and a single final-evaluation instant 2026-11-24T00:00:00 UTC.
- Valid-time scope: originally every FRESH row with `valid_time` strictly before the evaluation instant.
  The 2026-10-06 correction replaced the one-day truth-availability margin (an internal code convention,
  not verified provider behaviour) with a conservative cutoff: **`valid_time` strictly before
  2026-11-17T00:00:00 UTC**, because reanalysis values returned for very recent dates may later be revised.
- Missing-data policy: score what is available at the evaluation instant; exclude rows whose truth is
  not resolvable, state the exclusions plainly, never retry, never backfill, never impute.
- "Inconclusive" and "no candidate meets the requirement" are valid, reportable outcomes. Results are
  reported with block-bootstrap intervals either way.
- Anti-peeking: no inspection of any outcome-based figure (accuracy, achieved overrating rate, retained
  capacity, anything comparing a FRESH prediction to its truth) before 2026-11-24T00:00:00 UTC; no
  retuning of method, preprocessing or calibration between 2026-11-01 and 2026-11-24 based on FRESH data.
- Mechanical-health-check carve-out: confirming logs exist, the four timestamps
  (initialization/availability/decision/valid) are populated and sane, row counts are accruing, and
  `data/shadow/predictions/*.jsonl` is written without errors is permitted at any time.
- Reproducibility requirement for the evaluation run: persist the raw verification-data API
  response(s) for the rows scored, and an explicit retrieval timestamp, alongside the existing report.
- Sample-size figures (about 590 rows for tail-rate precision, about 1,575 for a 5 A margin) are reported
  alongside the result, not substituted for it.
- From v1 (kept in force by v2 where v2 is silent): three real candidates (`ml_wind_corrected`,
  `ml_cooling_corrected`, `reference_ml_refit_24h`) scored against `raw_forecast` and `persistence_24h`
  baselines; pairwise comparisons between every candidate pair; Bonferroni correction (3 pairs x 2
  corridors = 6 tests, alpha = 0.05/6, about 0.0083); an 8% achieved-overrating ceiling at the nominal 5%
  calibration target, explicitly "this pass's own proposed number, not a settled one" and never to be
  chosen after seeing FRESH outcomes; retained capacity as the primary ranking among eligible candidates.
- Stated retain/switch defaults for the 2026-11-01 freeze: retain `ml_wind_corrected` if the
  alternatives show no consistent practical benefit across both corridors; retain `raw_forecast` instead
  if any correction's benefit over the uncorrected forecast is negligible.

### What changes for per-city points

| Item | v1/v2 (corridors) | v3 (this amendment, if signed) |
|---|---|---|
| Scored unit | 2 corridors; each corridor's ampacity is the `min()` of two endpoint cities | 4 cities (`AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND`, `EL_PASO`); each city's own ampacity; nothing reduces across cities |
| Truth series | Corridor ampacity from reanalysis weather at both endpoints, then `min()` | Each city's own ampacity from reanalysis weather at that city's coordinates and static rating (`config.STATIC_RATINGS[city]`, `config.CITY_COORDINATES[city]`) <!-- VERIFY: confirm the scorer will use the same IEEE 738 settings as the shadow candidates --> |
| Logs scored | Corridor logs (v1 flat rows, v2 nested `candidates`) | Per-city logs, `schema_version: 3` only (decision 4) |
| Candidate artifacts | Corridor-pooled wind/cooling/reference models | 12 per-city artifacts: 3 methods x 4 cities under `data/shadow/models/{method}_{CITY}.joblib` |
| Wind model pooling | Pooled across a corridor's two cities with an endpoint indicator | `pooling="per_city"` |
| Pairwise tests | 3 pairs x 2 corridors = 6; alpha about 0.0083 | Open: 12, 24, 40 or a pooled set (decision 2) |
| Partial-day rule | A corridor-day with fewer than the expected 4 rows is "partial" | Applies per city; the scored unit is a `(city, valid_time)` pair (decisions 6 and 10) |
| Retain/switch rule "across both corridors" | Two corridors | "Across cities" needs a numeric meaning (decision 8) |
| Row source | Reconstructed FRESH frames in the frozen harness | Open: shadow logs, reconstructed frames, or both (decision 9) |
| Minimum rows | 590 enforced in code (`CONFIRMATION_MINIMUM_ROWS`) | Open: which governs (decision 3) |

### Scope

This amendment covers the five shadow candidates recorded in the per-city logs: `ml_wind_corrected`,
`ml_cooling_corrected`, `reference_ml_refit_24h`, `raw_forecast`, `persistence_24h`. It does **not**
cover the per-city C9 forecasting models (`forecast_{city}.joblib`) or the C10 anomaly models. For
context only, `forecasting_model.md` records that on the 2026-10-13 per-city refit the naive baseline had
lower held-out MAE than the persisted ML model in all four cities; that is a different task and object, and no
inference about the shadow candidates is drawn from it here.

## What does not change

If signed, every item below remains exactly as in v2. This draft does not propose to alter any of them.

- **Evaluation instant:** 2026-11-24T00:00:00 UTC (subject only to decision 5, which the owner may leave alone).
- **Conservative valid-time cutoff:** only rows with `valid_time` strictly before 2026-11-17T00:00:00 UTC
  are in scope (the 2026-10-06 correction).
- **One-shot evaluation:** the evaluation runs once, at the fixed instant. It is not repeated,
  re-scoped, re-parameterised or extended if the first read is unfavourable, and no row is retried or
  backfilled after the fact.
- **Anti-peeking:** no outcome-based figure for any FRESH row before the evaluation instant. No
  retuning, refitting, preprocessing or calibration change on the basis of FRESH data after the freeze.
- **Mechanical-health-check carve-out:** unchanged, wording as in v2. Confirming that per-city logs exist,
  timestamps are sane, row counts accrue and files are written without errors is permitted at any time.
- **"Inconclusive" is a valid outcome**, as is "no candidate meets the requirement". Neither is a reason
  to extend the window.
- **Reproducibility requirement:** whoever runs the evaluation must persist the raw verification-data
  API response(s) for the rows scored and the retrieval timestamp (distinct from `valid_time`), alongside
  the report, before the run is treated as archived. For per-city scoring this applies to each of the
  four cities' truth retrievals.
- **Missing-truth exclusion policy:** a row whose truth value is not resolvable at the evaluation instant
  is excluded from the reported sample size, the exclusion is stated plainly, and it is never retried or
  imputed.
- **Full uncertainty reporting:** results carry block-bootstrap intervals regardless of what they show.
- **The corridor-era record:** left untouched. The two legacy logs (`AUSTIN_CORPUS_CHRISTI.jsonl`,
  `MIDLAND_EL_PASO.jsonl`) are not rewritten, and no per-city number is merged with a corridor number.
- **Labelling:** every number carries the label "reanalysis-derived, never sensor-validated" (decision 7
  concerns whether a secondary check is added, not whether the label stays).

## Recorded decision: fit window and the model freeze

This section **records a decision already made and accepted** (2026-10-12, in
`shadow_collection_runbook.md`, "Fit-window decision: train + validation (2026-10-12)"). It is not an
open item and the owner is not being asked to re-decide it; signing this document makes it part of the
protocol record.

**The deviation.** v1 said the wind, cooling and reference-MLP models are fit on "ABLATION-TRAIN rows
alone (through 2025-09-01T18:36)", and v2 inherited that wording. The per-city shadow candidates
`ml_wind_corrected` and `ml_cooling_corrected` are instead fit on the **train and validation splits
together**: every cached exact-lead row strictly before the frozen test split (`FROZEN_TEST_SPLIT_START`,
2026-03-17). `reference_ml_refit_24h` was already fit on train + validation. All three now see the same
calendar span.

**Justification, as recorded in the runbook.**

1. Validation was used to *select* the configurations (`WIND_CONFIGURATION` = LinearRegression;
   `COOLING_CONFIGURATION` = GradientBoostingRegressor with the `log_ratio` target). Selection is finished.
   The refit changes nothing about which configuration is used.
2. Refitting a chosen configuration on train + validation is standard practice once selection is done;
   it adds 784 exact-lead rows per city (3,144 vs 2,360, about 33% more).
3. Nothing at or after 2026-03-17 is read by the fit (`forecast_shadow_fit_models.assert_no_test_leak`),
   and shadow data collected from 2026-10-12 onward did not exist when the models were fit, so shadow
   scoring is genuinely out of sample.
4. It removes the earlier asymmetry in which only the reference candidate had seen the validation period.

**The frozen harness is unaffected.** `_fresh_confirmation_report` refits on train-only itself
(`forecast_experiment.fit_fitted_arms(stacked_train, ...)`), so its own fitted objects keep the v1/v2
"ABLATION-TRAIN alone" definition. The objects affected by the deviation are the shadow candidates.

**What the deviation does and does not allow** (restated from the runbook):

- The frozen experiment's validation and test-split numbers describe train-only fits and must not be
  quoted as the performance of the per-city shadow artifacts.
- The artifacts must not be scored on the validation period (in-sample for them). Their only honest
  out-of-sample evidence is the live shadow collection.
- The selection of the configurations used the validation split, so any optimism in that selection is
  unchanged; the refit adds data, it does not repair that bias.

**The freeze, restated for per-city scoring.** The model-freeze date remains **2026-11-01** (unless the
owner changes it under decision 5). If signed, the **12 per-city shadow artifacts**
(`ml_wind_corrected`, `ml_cooling_corrected`, `reference_ml_refit_24h`, each for four cities, under
`data/shadow/models/`) are the frozen objects for shadow scoring once frozen: no refit, retune or
preprocessing change after 2026-11-01 on the basis of FRESH data. `raw_forecast` and `persistence_24h`
have no fitted artifact. The artifacts were committed in `6831322` on 2026-10-12 at 21:35 CDT (2026-10-13T02:35Z), one minute before the first per-city log row. A refit between now and 2026-11-01
is permitted by this document only if it uses no FRESH outcome; if it happens, the rows produced by the
earlier artifact must be identified and must not be pooled with rows from the new one (a recorded
artifact identity, such as a file hash noted at freeze, would make this checkable) <!-- VERIFY: the `model_version` field in the logs looks like a run-time stamp (e.g. `ml_wind_corrected_AUSTIN@2026-10-13T02:36:17...`), not an artifact-file identity; confirm before relying on it -->.

## Evidence base: what the data looks like today

### Row counts

Counted from `origin/shadow-collection-data` after `git fetch` at **2026-10-13T06:37Z**; the newest
commit on that branch is `753557f` (2026-10-13T03:15:13Z). Only line counts, timestamps and
`status` fields were read.

| Log | Rows | Distinct `valid_time` | First logged | Notes |
|---|---|---|---|---|
| `AUSTIN.jsonl` (v3) | 5 | 1 (2026-10-13T18:00Z) | 2026-10-13T02:36Z | all 5 rows are manual dispatches (workflow runs created 02:36, 02:49, 03:01, 03:07, 03:12 UTC), all targeting the same valid time |
| `CORPUS_CHRISTI.jsonl` (v3) | 5 | 1 | 2026-10-13T02:38Z | same |
| `MIDLAND.jsonl` (v3) | 5 | 1 | 2026-10-13T02:39Z | the first 2 rows have `unavailable` forecast candidates (the since-fixed stall); 3 of 5 have `ml_wind_corrected`, `ml_cooling_corrected`, `raw_forecast` all `ok` |
| `EL_PASO.jsonl` (v3) | 5 | 1 | 2026-10-13T02:40Z | same pattern as Midland |
| `AUSTIN_CORPUS_CHRISTI.jsonl` (legacy) | 21 (17 v2, 4 v1) | 14 | 2026-10-07T06:52Z | corridor-era, closed to new rows |
| `MIDLAND_EL_PASO.jsonl` (legacy) | 21 | not separately counted | | corridor-era, closed to new rows |

Observations that matter for the decisions below:

- **Today's usable per-city sample is 1 distinct valid time per city.** The 5 rows per city are the
  repeated manual dispatches of 2026-10-13 and share one `valid_time`; they are not 5 independent
  observations (decision 10).
- `persistence_24h` is `unavailable` in all 20 per-city rows (reason: no prior entry for the matching hour,
  a cold start). It becomes available only once a city has a v3 entry about 24 h earlier at the matching
  hour.
- Per-city logs began at 2026-10-13T02:36Z, although the per-city collector code went live 2026-10-12.
- The 5-row-per-city figure is a snapshot taken before that day's scheduled runs landed; it will be
  larger by the time this is read <!-- VERIFY: re-count at review time -->.

### Accrual rate and the honest expected sample

The collector chooses each cycle's `valid_time` as the first point on the 6-hourly UTC grid that is more
than 11 hours after "now" (`forecast_shadow_demo._resolve_next_valid_time`), so decision-to-valid gaps
are about 11 to 17 hours; the legacy log shows gaps from 11.1 to 16.7 h. One scheduled cycle yields one
valid time per city.

Scheduled runs (cron `0 6,18 * * *`) have in practice landed late and irregularly. From the Actions run
list (`gh run list`, read 2026-10-13): scheduled runs were created at 2026-10-08 22:45Z, 10-09 12:26Z,
10-09 22:08Z, 10-10 11:45Z, 10-10 21:01Z, 10-11 11:57Z, 10-11 21:22Z, 10-12 14:11Z and 10-13 00:02Z, all
successful, i.e. about 2 per day but offset 4 to 8 hours from the nominal 06:00 and 18:00 UTC. As a
consequence the valid hours actually scored have been concentrated on two of the four grid hours (legacy log:
valid hour 12Z in 8 rows, 00Z in 7, 18Z in 5, 06Z in 1). Which two hours depends on GitHub's scheduling
delay, which the project does not control.

Expected per-city sample by the cutoff (`valid_time` strictly before 2026-11-17T00:00Z):

| Scenario | Valid times per city | Basis |
|---|---|---|
| 2 cycles/day, every cycle lands, one per valid time | at most about **69** | valid times from 2026-10-13T18:00Z to 2026-11-16T18:00Z, 34 days x 2 + 1 <!-- VERIFY: arithmetic by the drafter; an upper bound --> |
| 2 cycles/day with skipped cycles, `unavailable` candidates, cold-start persistence | roughly 55 to 69 per city; fewer for `persistence_24h` and for any pair whose two candidates are not both available | drafter's estimate, not measured <!-- VERIFY --> |
| 4 cycles/day from about 2026-10-16 (decision 6) | at most about 130 | 6 at 2/day, then 4/day to 2026-11-16T18:00Z <!-- VERIFY: arithmetic by the drafter; an upper bound --> |
| Reconstructed FRESH frames of the frozen harness (decision 9) | about 192 per city | 4 exact-lead rows/day from 2026-09-30 through 2026-11-16 (48 days); consistent with the 16 rows per corridor recorded on 2026-10-05 <!-- VERIFY: not computed from the frozen harness; drafter's arithmetic --> |

So the earlier "roughly 70 by the cutoff" estimate checks out as an upper bound for the shadow logs. All of
these are far below the 590-row figure in the frozen harness (decision 3).

### What that sample can and cannot resolve (rough estimate, with assumptions)

The audit's paired block-bootstrap interval for wind-minus-cooling MAE had a half-width of about 7.1 A at
Austin and 7.0 A at Midland on 781 scored rows per corridor (block length 1; "Basis-selection gate" subsection of
`forecast_correction_followup_audit.md`). Scaling by the usual 1/sqrt(n):

| Rows per city | Half-width of a paired MAE-difference interval (rough) | With dependence inflation x1.3 | With Bonferroni over 12 tests (z 2.87 vs 1.96, x1.46) and x1.3 |
|---|---|---|---|
| 781 (audit) | about 7 A | n/a | n/a |
| about 69 | about **24 A** | about 31 A | about 45 A |
| about 130 | about 17 A | about 22 A | about 33 A |

Assumptions and weaknesses, none of which this draft can remove:

1. The 7.1 A was measured on corridor-level `min()` ampacity under train-only fits, for the difference
   between two similar candidates (wind vs cooling). Per-city, the refit artifacts and different candidate
   pairs (for example a correction against `raw_forecast`) may have different variance.
2. Scaling by 1/sqrt(n) assumes the same per-row variance. A 69-row bootstrap interval is itself unstable.
3. The audit's own block-length sensitivity found interval-width inflation of 1.03x to 1.57x (Austin) and
   0.98x to 1.31x (Midland) from temporal dependence; x1.3 is the conservative end used in v1. Rows 6 or
   12 hours apart within a day are strongly dependent, so doubling the cadence adds less than double the
   information.
4. Cities share weather. The effective sample of a pooled comparison across four cities is smaller than 4
   x 69 (the scorer reports an effective sample size; Austin and Corpus Christi are the closest pair).
5. The 12-test Bonferroni column treats the family as per-city pairwise (decision 2, option A); other families scale differently.
6. All of this is a rough planning estimate, not a power calculation.

Which development-era gaps are therefore resolvable? Using the published corridor-level development figures
(ABLATION basis, train-only fits, so only reference points for per-city):

| Gap (development evidence) | Size | Resolvable at about 69 rows per city? |
|---|---|---|
| Wind vs cooling | about 5.5 to 5.7 A | **No.** Far inside the interval at any family size considered |
| `ml_cooling_corrected` vs `raw_forecast`, Austin corridor | about 4.4 A (111.44 to 107.04) | **No** |
| `ml_wind_corrected` vs `raw_forecast`, Midland corridor | about 26 A (152.57 to 126.52) | **Borderline.** About the size of the uncorrected interval half-width; not resolvable under a corrected family or with dependence inflation |
| `persistence_24h` vs `raw_forecast`, Austin corridor | about 45 A (156.34 vs 111.44) | **Probably**, if the per-city gap resembles the corridor gap |
| `persistence_24h` vs `raw_forecast`, Midland corridor | about 8.5 A | **No** |
| `reference_ml_refit_24h` vs `raw_forecast` | about 17 A worse (Austin), about 17 A better (Midland) | **No** |

Expect "inconclusive" for most candidate-versus-candidate questions at this sample size, which v2 already
lists as a valid outcome. The audit's own figure for reliably resolving a 5 A margin was about 1,575
rows (about 394 days at 4 rows/day), roughly 2.7 times the 590-row tail-rate figure; neither is reachable
by 2026-11-17 on any scenario above.

## Known validity threats to scoring the live logs

These are properties of how the live collector produces its predictions, found by reading the code
(counts, timestamps and `status` fields only; no outcome was read). They are **limitations of what the
shadow-log scores mean**, not decisions: they do not change the dates or the candidates, but any score
reported on 2026-11-24 must be read with them, and the scorer is specified to flag them in its output. Each
is stated with the code it comes from so it can be checked.

### V1. The live anchor is not the anchor the correction models were trained with

`ml_wind_corrected` and `ml_cooling_corrected` correct a forecast using an "anchor" observation (the most
recent real observation a forecaster would have had).

| | Training (offline, `forecast_experiment.anchored_pair_frame`) | Live (`forecast_shadow_pipeline.fetch_live_anchor_observation`) |
|---|---|---|
| Anchor source | Open-Meteo **archive reanalysis** value | A **station** observation (TCEQ, falling back to Synoptic) |
| Anchor-to-valid-time gap | Exactly **24 h** (`anchor_datetime_utc` = valid time minus `lead_hours`) | The latest observation at or before decision time, looking back at most 6 h (`_ANCHOR_LOOKBACK_HOURS_DEFAULT = 6.0`); decision-to-valid is 11 to 17 h, so the gap is **about 11 to 23 h** |
| Forecast-run age at the anchor | Run initialized 24 h before valid time | Same run rule (valid time minus 24 h), which is already 7 to 13 h old at decision time |

The collector's own docstring already calls the statistical equivalence of the two anchors "open and
explicitly not answered". **Consequence:** the correction candidates are scored while being fed inputs that
differ in source and lead from the inputs they were fit and validated on. A good or bad shadow score
therefore cannot be attributed to the correction *method* alone, and the development-era MAE figures do not
transfer to it. The direction of the effect is unknown. The shadow scores measure "the live system as
operated", which is a legitimate quantity, but it is not the development configuration.
`reference_ml_refit_24h` has the same kind of mismatch (V2): its live inputs come from a station-based
truth proxy rather than the archive series it was fit on.

**What the scorer can do about it (descriptive only, fixed in advance):** each v3 row already logs
`anchor_source`, `anchor_station` and `anchor_observation_time`, so the scorer reports the realized anchor
age and source per row and the distribution of both, and gives each correction candidate's error split by
anchor source (an exploratory breakdown, not a hypothesis test). It does not adjust or reweight scores.

### V2. `reference_ml_refit_24h` is scored against a different hour than it predicts

The live method is computed from the row at decision time (`ReferenceRefit24hShadowMethod.compute(city,
decision_time)`) with the model's 24-hour horizon, so it forecasts roughly **decision time + 24 h**. The
cycle logs it under the cycle's `valid_time`, which is decision time + 11 to 17 h. Its target is therefore
about **7 to 13 h later** than the hour it is scored against. Scoring it at the logged `valid_time` compares
it with the wrong hour and penalises it unfairly in any comparison with the other candidates.
**What the scorer does:** flags every comparison involving this candidate, and reports a separate check at
the candidate's own target hour (truth fetched for decision time + 24 h) so both readings are available,
labelled as such. Which reading is the headline is for the owner (see the metrics section).

### V3. `persistence_24h` is not the 24-hour persistence of the development record

As logged, `Persistence24hShadowMethod` reuses the **previous cycle's `raw_forecast`** for the entry whose
`valid_time` is closest to this cycle's decision time. At the cadence in use that entry's valid time is about
11 to 17 h before the valid time being scored, not 24 h, and it is a forecast, not an observation. It is a
different baseline from the `persistence_24h` of the audit (ABLATION basis, truth shifted by 24 h), so the
development-era figures for persistence (for example MAE 156 A at Austin) are not comparable to its live
score. It is also `unavailable` until a city has a prior entry at the matching hour (cold start), so
comparisons against it have fewer rows than the others.

### V4. Reanalysis truth, and cities that share weather (restated)

Truth is Open-Meteo archive reanalysis (decision 7): reanalysis-derived, never sensor-validated, and the
correction models were trained against the same archive. The four cities share regional weather, so a
pooled comparison has far less than four times the information of one city (the scorer reports an effective
sample size). Neither point is new; both are listed here so every limitation sits in one place.

### V5. The live forecasts come from a different weather model than the one the corrections were trained on

The development evidence and the fitted corrections used Open-Meteo's **Previous Runs API pinned to
`gfs_seamless`** (`open_meteo_forecast_provider.PREVIOUS_RUNS_MODEL_ID`; `forecast_correction_experiment.md`:
"a distinct model pin from the legacy arm's `ecmwf_ifs`, since `ecmwf_ifs`'s Previous-Runs archive is
null", and "nothing in this record generalizes to a different model"). The live collector calls
`fetch_single_run(...)` with no `model` argument (`fetch_live_forecast_for_valid_time`), which falls back to
`open_meteo_forecast_provider.FORECAST_MODEL_ID = "ecmwf_ifs"`. So the live `raw_forecast` is an ECMWF IFS
forecast, and `ml_wind_corrected` / `ml_cooling_corrected` apply corrections learned from **GFS** forecast
errors to **ECMWF** forecasts. Nothing in `shadow_collection_runbook.md` or the audit record reconciles the
two <!-- VERIFY: searched the runbook, the audit record and the experiment record on 2026-10-13 for any note that the live model differs; none found -->. The log rows do not record which NWP
model produced them, so the scorer cannot tell from the rows alone.

**Consequence:** the correction candidates are scored out of the distribution they were fit on, in a way
that could help or hurt them, and the development-era margins (including "wind and cooling beat raw") do not
transfer. The candidates' relative standing on live data would then say less about the correction methods
than about the model mismatch. This is more serious than V1 because it affects the raw forecast itself, not
only the anchor. Both models answer a live single-run request today (mechanical check, 2026-10-13), so
aligning the live model with the training model is technically possible; see decision 11.

### V6. Rows logged before 2026-10-13 predict the weather one hour before the hour they are scored against (fixed)

Found 2026-10-13 by a read-only check while reviewing the collector change. Each cycle's forecast run is
initialized exactly 24 h before the valid time, so the valid hour is `init + 24 h`. The collector requested
`forecast_days=1`, whose response covers only `init .. init + 23 h`, and looked the row up with
`frame.index.asof(valid_ts)`, which quietly returned the nearest earlier hour, `init + 23 h`, whenever the
exact hour was absent. Every forecast-based candidate (`raw_forecast`, `ml_wind_corrected`,
`ml_cooling_corrected`, and `persistence_24h`, which copies a prior `raw_forecast`) therefore predicted the
weather one hour earlier than the hour truth is fetched for. `reference_ml_refit_24h` is not affected by this
particular offset (it has its own target-hour issue, V2). Mechanical check, no outcomes: with
`forecast_days=1` the valid hour is not in the frame; with `forecast_days=2` it is.

**Fix (2026-10-13, shipped together with decisions 6B and 11B):** the request now asks for 2 forecast days
and the lookup is strict: the row for exactly the valid hour, or the cycle reports the candidate as
unavailable with a named reason. Tests cover the request size, that the row used is the exact valid hour,
and that a missing exact hour raises.

**Consequence for scoring:** every row logged before the fix lacks the `forecast_model` field (the same
change added it), so **a row without `forecast_model` is both an `ecmwf_ifs` row and a one-hour-offset
row and must not be scored or pooled with later rows.** That includes every per-city row logged on
2026-10-13 before the fix and all corridor-era rows. It also removes the one-hour offset from the
interpretation of earlier development-era figures only in the sense that those were computed offline on
aligned hours (`anchored_pair_frame` indexes by exact valid time); they were never affected.

### What to do with these

Nothing here asks the owner for a number except V5, which is a decision (decision 11); V6 was a bug and is already fixed. The owner is asked to **acknowledge** V1 to V6 in the sign-off
block, to decide V5 under decision 11, and to say under decision 8 which reading of `reference_ml_refit_24h` (V2) is headline. If the owner
considers V1 serious enough to change what is measured (for example to replace the live anchor with an
archive-derived one for scoring, or to refit with a station-based anchor), that is a protocol change that
would have to be decided before the 2026-11-01 freeze, and is outside this draft.

## Open owner decisions

Eleven items need the owner. Each is listed in the index table, then described in full. "Recommended" is the
drafter's suggestion, never a decision. Items 1, 2, 3, 6, 8 and 11 must be fixed **before** the 2026-11-01
freeze or before any outcome is seen; none of them may be chosen after seeing FRESH outcomes.

### Index

| No. | Decision | Drafter's RECOMMENDATION (not a decision) | If the owner does nothing |
|---|---|---|---|
| 1 | The 8% overrating ceiling | Keep 8%, approve it now, apply only to a ported FRESH harness; do not apply to shadow logs | No ceiling is in force; the shadow scoring is run without a gate and says so; 8% stays an unapproved proposal |
| 2 | Size of the multiple-comparison family | Option E+D: pooled, city-clustered headline family of 9 tests (3 candidate-vs-candidate, 3 vs `raw_forecast`, 3 vs `persistence_24h`), Holm (Bonferroni bound 0.05/9); per-city intervals descriptive | Ambiguous: v1's 0.05/6 was written for two corridors; the scorer author must guess a family |
| 3 | 590-row code gate vs "score what exists" | v2 governs: score what exists, report n and the unmet precision target | v2 text says score what exists, but the frozen harness would raise below 590; nothing per-city would be scored by it |
| 4 | Corridor-era rows in per-city evaluation | Do not count them | Not counted (point scope forbids mixing), but stated in no signed document |
| 5 | Whether 2026-11-24 and 2026-11-01 move | Keep both | Both dates stay |
| 6 | Collector cadence (2/day vs 4/day) | Decide by 2026-10-16; if raised, use cron `0 0,6,12,18 * * *` and one valid time per cycle | Cadence stays 2/day; about 69 rows per city at most |
| 7 | Truth source, and a secondary station check | Keep the archive as primary; report a station check only where it can be made without new inference; label everything reanalysis-derived | Archive primary; no secondary check; caveats stated |
| 8 | Headline comparison and the numeric "negligible" threshold | Per-city MAE reduction vs `raw_forecast` of at least 5 A, with a three-level evidence label; pre-state the action for each level | The v2 retain-wind and retain-raw defaults stay but have no numbers, so they cannot be applied mechanically |
| 9 | Which rows are the scoring basis | Shadow logs are the headline; reconstructed frames are a separately reported secondary analysis | Defaults to whatever the scorer is built on; ambiguous |
| 10 | One row per `(city, valid_time)`, and complete-case pairing | First-logged row per `(city, valid_time)`; pairs scored only where both candidates are `ok` | The scorer author chooses; duplicates may be double counted |
| 11 | Which NWP model the live collector uses (V5) | Switch live to `gfs_seamless` before the freeze, bundled with decision 6, record the model in each row, and score only rows produced after the switch | Live stays on `ecmwf_ifs`; scores are read with the V5 caveat and say less about the correction methods |

### Decision 1. The 8% overrating ceiling

- **Question.** Is 8% (achieved overrating rate at the nominal 5% calibration target) the eligibility ceiling, some other number, or
  no ceiling for per-city scoring?
- **Why it matters.** In v1 a candidate is eligible only if its achieved overrating rate at the nominal 5%
  target does not exceed 8%; among eligible candidates retained capacity (mean derated ampacity) is the
  primary ranking. v1 says plainly that 8% was the drafting pass's own proposed number, never approved by the owner, and
  that it must never be chosen after seeing FRESH outcomes. Choosing it now is the only legitimate time.
- **A hard limit on what can be applied.** The shadow logs hold **point predictions only** (`ampacity_amps`
  per candidate, plus a provisional bundle scaling). The calibrated 5%-target overrating rate and retained
  capacity come from the quantile-calibration pipeline and **cannot be computed from the shadow logs**; they
  could be produced only by a FRESH harness ported to per-city (the existing one is corridor-only and frozen).
  No such per-city port exists today. Building one means working without reading FRESH outcomes (synthetic
  fixtures only), as v2 required of the corridor version.
- **Options.**
  - A. Approve 8% now; apply it only to a ported per-city FRESH harness, if one is built and verified before 2026-11-24.
  - B. Approve a different number now (for example 6% or 10%) on the same terms.
  - C. Drop the ceiling for per-city scoring: rank on point-error metrics and the descriptive over-prediction
    figures, and state that calibrated risk was not measured.
  - D. Define a ceiling on a quantity the shadow logs *can* give (for example on the descriptive
    over-prediction rate). Caution: an unbiased point forecast over-predicts roughly half the time (the
    audit's ceiling-clip table, ABLATION basis, shows roughly 42% to 53% for point-model predictions), so 8% on that quantity would exclude every
    candidate; any such ceiling would need a different number and a new justification.
- **Drafter's RECOMMENDATION (not a decision).** Option A: approve a number now and say explicitly that it is
  applied only if the ported harness exists; otherwise the write-up says calibrated risk was not
  measured.
- **If the owner does nothing.** No ceiling is in force at the evaluation. The shadow scorer cannot compute
  it anyway, so the write-up states that eligibility against the 8% proposal was not assessed. The 8%
  remains an unapproved proposal in the record.

### Decision 2. Size of the multiple-comparison family for four cities

- **Question.** Which tests form the family that gets a multiplicity correction, and which correction?
- **Why it matters.** v1's family was 3 candidate pairs x 2 corridors = 6 tests, Bonferroni alpha =
  0.05/6 = 0.0083. With four cities the same rule gives a different alpha, and the retain-raw rule in
  decision 8 needs candidate-vs-`raw_forecast` comparisons that v1's family did not include. A stricter alpha
  widens intervals (z grows from 1.96 to 2.87 at 12 tests), and with about 69 rows per city the
  decision is largely "inconclusive" or not, depending on this choice.
- **Arithmetic (3 real candidates; two-sided Bonferroni; z from the normal distribution).**

| Option | Family | Tests | Bonferroni alpha | z (two-sided) |
|---|---|---|---|---|
| A. v1-literal, per city | 3 candidate-vs-candidate pairs x 4 cities | 12 | 0.05/12 = 0.0042 | 2.87 |
| B. A plus each correction vs `raw_forecast` | (3 + 3) per city x 4 cities | 24 | 0.05/24 = 0.0021 | 3.08 |
| B2. B plus each candidate vs `persistence_24h` (v1 scored candidates against both baselines) | (3 + 3 + 3) per city x 4 cities | 36 | 0.05/36 = 0.0014 | 3.20 |
| C. All five methods, all pairs (includes raw-vs-persistence) | 10 per city x 4 cities | 40 | 0.05/40 = 0.00125 | 3.23 |
| D. Holm step-down over option A, B, B2 or C's family | same tests | 12, 24, 36 or 40 | smallest p vs 0.05/k, next vs 0.05/(k-1), and so on | first step as in the option's own row |
| E. One pooled, city-clustered comparison per pair (headline), per-city results descriptive | 3 pairs; or 6 with correction-vs-raw; or 9 with persistence | 3, 6 or 9 | 0.05/3 = 0.0167; 0.05/6 = 0.0083; 0.05/9 = 0.0056 | 2.39; 2.64; 2.77 |
| Reference: v1 | 3 pairs x 2 corridors | 6 | 0.0083 | 2.64 |

  **Why persistence belongs in the family.** v1 scored the real candidates "against `raw_forecast` and
  `persistence_24h` baselines". The earlier draft of this table left persistence comparisons out. Note two
  cautions about them: the logged `persistence_24h` is not the development record's persistence (V3), and it
  has fewer rows than the other candidates because of the cold start, so its comparisons will often be
  "insufficient data".

  Holm controls the same family-wise error as Bonferroni, is never less powerful, and does not require
  independence. Pooling (E) spends the multiplicity budget on four times fewer tests but answers a
  different question ("on average across the four cities") and needs city-clustered resampling
  because the cities share weather.
- **Options.** A, B, C, D, E as above; or a hierarchical rule (test the pooled comparison first; look at
  cities only if it passes).
- **Drafter's RECOMMENDATION (not a decision).** E with Holm as the correction: a pre-stated headline family
  of 9 tests (3 candidate-vs-candidate, 3 correction-vs-`raw_forecast`, 3 candidate-vs-`persistence_24h`),
  pooled across cities with city-clustered resampling, Bonferroni bound alpha = 0.05/9 (about 0.0056); per-city
  results reported with uncorrected intervals, labelled descriptive. Reason: about 69 rows per city cannot
  support a 12-, 24- or 36-test corrected family, so most per-city results would be "inconclusive" by
  construction. If the owner prefers a smaller family, dropping the persistence comparisons (6 tests,
  0.05/6 as in v1) is the alternative, but that would leave v1's "scored against both baselines" unmet.
- **If the owner does nothing.** The signed protocol does not define the family. The scorer author must pick
  one, which would be a decision made without the owner and before outcomes, but unreviewed.

### Decision 3. The 590-row code gate vs v2's "score what exists"

- **Question.** Which governs: `CONFIRMATION_MINIMUM_ROWS = 590` in the frozen harness, or v2's rule to score what
  is available at the evaluation instant?
- **Why it matters.** The code gate raises `ValueError` and refuses to score any corridor with fewer than 590
  FRESH rows (`_fresh_confirmation_report`, `minimum_fresh_rows=None` defaults to 590), even with
  `confirm_fresh_run=True`. v2 explicitly replaced the sample-size-gated waiting condition with a fixed calendar
  date and says the sample-size figures describe desired precision, not a prerequisite. The code was never
  changed to match. The harness does take a `minimum_fresh_rows` argument, so a caller can lower it without
  editing the frozen file.
- **The honest sample.** About 69 valid times per city for the shadow logs; about 192 per city for the
  reconstructed frames (table above). Neither reaches 590 by 2026-11-17. If the 590 gate governed, no per-city
  confirmation could be run on 2026-11-24, from either source.
- **Options.**
  - A. v2 governs. The per-city scorer has no row gate; it reports n and states that the tail-rate
    precision target (about 590 rows) and the 5 A minimum-detectable-difference target (about 1,575 rows)
    were not met. A ported harness passes `minimum_fresh_rows` explicitly.
  - B. 590 governs. Per-city evaluation on 2026-11-24 is not run (or is declared exploratory only).
  - C. A middle gate (for example a minimum of 30 valid times per city for any *reported* comparison, fewer is
    "not assessed"). The drafter has no evidence for any particular minimum, so any such number would be the owner's judgment <!-- VERIFY -->.
- **Drafter's RECOMMENDATION (not a decision).** Option A, as v2 already says, with the n, the effective
  sample size and the unmet targets printed at the top of the result.
- **If the owner does nothing.** v2's text stands (score what exists), but the only code that implements the
  confirmation read would refuse. The conflict is left for whoever runs the evaluation to resolve on the
  day, which is exactly what this protocol is meant to prevent.

### Decision 4. Do corridor-era shadow rows count toward any per-city evaluation?

- **Question.** The legacy logs hold 21 rows each (17 v2, 4 v1; 14 distinct valid times for
  `AUSTIN_CORPUS_CHRISTI`), collected from 2026-10-07. Do they add to any per-city sample?
- **Why it matters.** Those rows are corridor-level minima over two cities. They are not per-city
  predictions, and `point_scope.md` and the runbook say legacy rows must never be mixed into per-city evaluation.
  Counting them would raise the apparent n by a handful of rows while mixing targets.
- **Options.** A. No. B. Yes, as a separately labelled secondary analysis of corridor performance only. C. Yes, merged
  (contradicts `point_scope.md`; listed for completeness).
- **Drafter's RECOMMENDATION (not a decision).** A. The corridor logs stay closed and are never merged. A
  separate corridor-level descriptive note, if wanted, is optional and must not be pooled.
- **If the owner does nothing.** Legacy rows are excluded in practice (the per-city scorer keys on
  `schema_version: 3` and `city`), but that exclusion would not be in any signed document.

### Decision 5. Do 2026-11-24 and 2026-11-01 move?

- **Question.** The 2026-11-24 date was set against corridor-level collection; per-city collection started
  2026-10-13 (code live 2026-10-12). Do the evaluation instant (2026-11-24T00:00:00Z), the cutoff
  (2026-11-17T00:00:00Z) or the freeze (2026-11-01) move?
- **Why it matters.** Moving the instant later buys rows at the price of the early-December ship target;
  moving it earlier loses rows. Per-city collection began about six days after the corridor-era collection
  (2026-10-07), so relative to an uninterrupted series the cost is roughly six days of accrual (about 12
  rows per city at 2/day), not a restart over many weeks. The corridor-era rows cannot make that up
  (decision 4). <!-- VERIFY: drafter's arithmetic -->
- **Options.** A. Keep both dates. B. Move the instant later (and the cutoff with it, one week earlier than the
  instant) at the cost of the ship date. C. Keep the dates and pre-declare (before 2026-11-24 outcomes) a
  clearly separate, later descriptive follow-up that is not a second confirmation read. D. Move the freeze earlier
  (the artifacts have not changed since 2026-10-12, so an earlier freeze has no modelling cost; it does not add rows).
- **Drafter's RECOMMENDATION (not a decision).** A, optionally with C. v2's reasoning (ship date, a week
  of margin for truth revision) still applies unchanged.
- **If the owner does nothing.** Both dates stay.

### Decision 6. Collector cadence: 2 cycles/day vs 4/day

This changes what is measured, so it must be fixed **before the freeze**, and it is presented as options only.

- **Question.** Raise decision cycles from 2/day (cron `0 6,18 * * *`) to 4/day (`0 0,6,12,18 * * *`) to
  increase rows?
- **Effects of 4/day.**
  - *Rows.* Up to about 130 valid times per city by the cutoff if started about 2026-10-16, against about 69. Rows 6 h apart within a day
    are strongly dependent, so the information gain is less than double (see the interval table).
  - *Valid-hour coverage.* The grid has four valid hours (00, 06, 12, 18 UTC). At 2/day only two are
    scored, and which two is set by GitHub's scheduling delay (observed: mostly 00Z and 12Z). 4/day would cover all four, which is the span the models were fit on (six-hourly exact-lead).
  - *Actions minutes.* Recent runs took about 3 to 5 minutes each (scheduled 194 to 267 s; manual per-city
    183 to 297 s). 2/day is about 70 runs (roughly 350 min) to the cutoff; 4/day about 140 runs (roughly 700 min).
    The repository is private, so minutes count against the plan's quota <!-- VERIFY: plan and monthly Linux-minute quota; billed minutes round up per job -->.
  - *Per-IP stall risk.* Open-Meteo single-runs requests from the runner stalled transiently in the first
    four-city runs; a retry cleared it, and the cause is "not established" per the runbook. Doubling the request
    volume doubles exposure. Open-Meteo's own rate limits were not checked here <!-- VERIFY -->.
  - *Availability lag.* The model-run publication lag (default 6 h) is not changed by cadence; the
    grid rule keeps decision-to-valid at about 11 to 17 hours at either cadence. GitHub cron delays of 4 to 8 hours have not
    broken that rule so far, but at 4/day a delayed run can land on the same valid time as the next, making
    duplicates more likely (decision 10).
  - *Protocol effect.* It changes the sampled valid hours and the sample size of the one-shot evaluation, so it cannot be adopted after the freeze without
    changing the thing being measured.
- **Constraint on any option that scores more than one valid time per cycle.** The shadow models were fit
  on the exact-24h-lead subset. In the logs, `horizon_minutes = 1440` is the **age of the model run at valid time**
  (initialization = valid time minus 24 h), while the actual decision-to-valid gap is 11 to 17 h. Extra valid times per cycle could be scored
  only if each still uses a model run initialized exactly 24 h before its valid time, and
  that run was already available at decision time; otherwise the candidates are scored outside the lead they
  were fit on. Related, already-documented open question: the live anchor is a station observation taken "now",
  whereas the training anchor is archive-derived at valid time minus 24 h; the collector's own docstring
  says their statistical equivalence is "open and explicitly not answered" (`fetch_live_anchor_observation`).
  Neither option below resolves that.
- **Options.** A. Stay at 2/day. B. 4/day, one valid time per cycle (the current rule), cron `0 0,6,12,18 * * *`. C. Keep
  2/day cycles but score several exact-lead valid times per cycle (needs new collector logic and a review of
  anchor-age semantics; not recommended before the freeze).
- **Drafter's RECOMMENDATION (not a decision).** If the owner wants more rows, B, adopted by about 2026-10-16
  so the change is in place for most of the window. Otherwise A. C is not recommended on this timeline.
- **If the owner does nothing.** Option A. Cadence stays 2/day.

### Decision 7. Truth source, and a secondary station-based check

- **Question.** Open-Meteo's archive reanalysis is the primary truth source (**already decided by the owner**). Is a secondary station-based check
  (TCEQ or Synoptic) also reported where available?
- **Why it matters.** The archive is "reanalysis-derived, never sensor-validated" (the audit's own label for
  every number in the project). There is also a circularity risk: the correction models were trained against the
  same archive, so agreement with it is not independent evidence about the physical line. v2 flagged that archive
  values for very recent dates may later be revised, which is why the cutoff is one week before the instant; the
  re-fetch-and-diff check that v2 said could supersede that figure has not been shown to have been run in this
  repository <!-- VERIFY: whether the revision check was ever run -->.
- **What a secondary check would need.** Station values at each city's own location for every IEEE 738 input
  (wind, temperature and irradiance). TCEQ and Synoptic already supply the live anchor wind. That they cover the full input set at all four city points with usable
  history through 2026-11-17 is not established here <!-- VERIFY: station coverage per city -->, and a station reading is a point measurement,
  not the same quantity as a reanalysis grid cell.
- **Options.** A. Archive only, caveats stated. B. Archive primary; where a station reading exists for the same
  valid hour, report the station-based error alongside, never merged, never used to select. C. Station-based as
  co-primary (not recommended: coverage unknown).
- **Drafter's RECOMMENDATION (not a decision).** B, and only if it can be implemented without new inference
  choices that would be made after outcomes are visible. Whatever is chosen, the reproducibility requirement
  (raw responses and retrieval timestamp) applies to each source.
- **If the owner does nothing.** Archive only, with the caveat sentence stated in the write-up.

### Decision 8. Headline comparison and the numeric meaning of "negligible"

- **Question.** What is the headline comparison per city, and what numbers decide v2's retain/switch rules?
- **Why it matters.** v2's defaults are qualitative: retain `ml_wind_corrected` unless an alternative shows a
  "consistent practical benefit across both corridors"; retain `raw_forecast` if "any correction's benefit over
  the uncorrected forecast turns out to be negligible". With four cities they need restating per city and need a
  threshold. This must be fixed before any outcome, because any threshold chosen after seeing results can be
  tuned to the result. Note also that "any correction" is a harsh rule: one weak candidate in one city would trigger
  the raw default for everything it applies to; the owner should say whether "any" is per city or across cities.
- **Reference points from development evidence (corridor-level, train-only).** Wind's MAE benefit over raw
  was about 17% (26 A) at Midland; cooling's was about 4% (4.4 A) at Austin. Those are the examples v2 itself cites
  as "clearly non-negligible" and "present but thinner".
- **Options for a numeric threshold.**
  - A. An absolute reduction of per-city MAE versus `raw_forecast` of at least X A (the audit used 5 A as its
    assumed "minimum decision-relevant" margin).
  - B. A relative reduction of at least Y% of `raw_forecast` MAE (for example 5%).
  - C. A resolvability requirement: the paired interval must exclude zero (see decision 2 and the interval table:
    at about 69 rows this is only likely for gaps above roughly 25 A).
  - D. Three levels pre-stated: "supported" (point benefit at least X and interval excludes 0), "indicated, not
    resolved" (point benefit at least X, interval includes 0), "not shown" (point benefit below X), with an
    action named for each level before outcomes.
- **Options for the per-city rule.** (i) One method chosen per city, so cities may differ (consistent with
  independent points). (ii) One method for all cities, chosen on the pooled comparison and the number of cities
  that agree (simpler to integrate, matches v2's "across both corridors").
- **Drafter's RECOMMENDATION (not a decision).** Option D with X = 5 A (the audit's own assumed margin; Y not used), and per-city
  rule (ii) with "consistent" meaning the point estimate favours the candidate in at least 3 of the 4 cities.
  For the default action: "supported" or "indicated" in the wind case keeps `ml_wind_corrected` as the working choice, "not shown" for any
  correction against `raw_forecast` keeps `raw_forecast`, as in v2. State plainly that at about 69 rows per
  city most results will be "indicated, not resolved" and that this is reported as such. <!-- VERIFY: X = 5 A and the 3-of-4 rule are the drafter's suggestions, not derived from evidence -->
- **Sub-question 8c (from validity threat V2): which reading of `reference_ml_refit_24h` is the headline?**
  Scored at the logged `valid_time` (decision time + 11 to 17 h) it is compared with an hour it does not
  predict; scored at its own target hour (decision time + 24 h) it is compared with the hour it does predict.
  Options: (i) own target hour is the headline and the logged-`valid_time` score is reported alongside;
  (ii) logged `valid_time` is the headline (a like-for-like hour with the other candidates, at the price of an
  unfair comparison for this candidate); (iii) report both with no headline. Recommendation (not a decision):
  (i). If the owner does nothing, the scorer reports both, flags every comparison involving this candidate,
  and no pre-stated headline exists, which is the situation this decision exists to avoid.
- **If the owner does nothing.** The v2 defaults stay but cannot be applied mechanically, because "negligible"
  and "consistent" have no numbers; whoever writes up the result would supply them after seeing it, which is what
  this decision exists to prevent.

### Decision 9. Which rows are the scoring basis

- **Question.** The shadow logs (live predictions with real decision times) and the frozen harness's reconstructed FRESH frames (previous-runs
  archive data, 4 exact-lead rows/day) are two different row sources. Which one counts?
- **Why it matters.** v1/v2 talk about "FRESH-basis rows"; the harness builds them from the archive
  reconstruction, while the runbook treats the shadow logs as additional observational data independent of the
  harness. The shadow logs are the only record of what was truly available at each decision time; the reconstruction is
  retroactive. They differ in size (about 69 vs about 192 per city) and in what can be computed (the logs
  cannot give calibrated overrating or retained capacity; a ported harness can).
- **Options.** A. Shadow logs only. B. Reconstructed frames only (needs the ported harness). C. Both,
  reported separately, never pooled, with the shadow logs the headline.
- **Drafter's RECOMMENDATION (not a decision).** C, with shadow logs as the headline for the point-error metrics and the
  reconstructed frames, if the port is built in time, as the source of calibrated-risk figures
  (decision 1). <!-- VERIFY: drafter's reading of `_fresh_confirmation_report` as using reconstructed frames -->
- **If the owner does nothing.** The basis is whatever the scorer is built on.

### Decision 10. Duplicates, unavailable candidates and pairing

- **Question.** How are rows handled when a `(city, valid_time)` appears more than once, and when a candidate
  is not `ok`?
- **Why it matters.** The 5 rows per city today are one valid time observed five times. Counting them
  separately would inflate n and treat the same weather as five independent observations. Manual dispatches,
  GitHub retries and a 4/day cadence all create more such rows. Some per-city candidates were `unavailable` on early
  rows (Midland and El Paso `raw_forecast`, `ml_wind_corrected`, `ml_cooling_corrected`); `persistence_24h`
  is unavailable on a cold start.
- **Options.** A. Keep the first-logged row per `(city, valid_time)`. B. Keep the last-logged row. C. Average
  duplicates (not recommended; the rows are not independent draws). For pairing: (i) complete case (a pair is scored only
  where both candidates are `ok`; each candidate's availability rate reported); (ii) each candidate scored on its own
  `ok` rows (unpaired differences, comparing different weather).
- **Drafter's RECOMMENDATION (not a decision).** A with (i). First-logged is a rule that can be
  fixed now and cannot depend on any outcome, whereas choosing between duplicates by looking at results would
  not be; excluded duplicates are counted and listed in the exclusion table (same
  spirit as v2's missing-data policy: never silently dropped, never imputed).
- **If the owner does nothing.** The scorer author chooses; duplicates may be double counted.

### Decision 11. Which weather model does the live collector use? (validity threat V5)

- **Question.** The corrections and all development numbers are for `gfs_seamless` forecasts; the live
  collector fetches `ecmwf_ifs`. Should the scored live forecasts use the training model?
- **Why it matters.** See V5. Left as is, a live score is partly a statement about a model mismatch. It must
  be fixed before the freeze, because it changes what is measured, and any rows produced under the other
  model cannot be pooled with the new ones.
- **Evidence.** Both models return a 24-row single-run forecast for a recent run (mechanical check,
  2026-10-13). Not checked: GFS single-run publication lag and run availability relative to the collector's
  `_resolve_publication_lag_hours` default <!-- VERIFY: whether the 6 h default lag and the 6-hourly valid-time grid are right for gfs_seamless single runs -->, and whether the corrections behave sensibly on live GFS input
  (that is an outcome question and must not be looked at before 2026-11-24).
- **Options.**
  - A. Keep `ecmwf_ifs`. Cheapest, no change. State V5 in every result; interpret scores as "GFS-trained
    corrections applied to ECMWF forecasts".
  - B. Switch the live collector to `gfs_seamless` (pass `model=` in `fetch_live_forecast_for_valid_time`),
    add a `forecast_model` field to each v3 row (backward compatible), and score only rows produced after the
    switch. Costs the rows already collected under `ecmwf_ifs` (a few days at 2/day) and is a
    protocol-affecting collector change, so it belongs with decision 6.
  - C. Log both models in parallel each cycle and score each separately. Most informative, doubles the
    forecast requests (and the exposure to the Open-Meteo stall) and complicates the family of tests.
  - D. Refit the corrections on ECMWF IFS errors. Not available: the experiment record says the
    `ecmwf_ifs` Previous-Runs archive is null, so the same method cannot be repeated for it.
- **Drafter's RECOMMENDATION (not a decision).** B, made by the same date as decision 6 (about 2026-10-16),
  so most of the window is clean. If the owner decides to stay on `ecmwf_ifs` (A), say so explicitly in the
  signed document.
- **If the owner does nothing.** A, with V5 stated in the write-up.

## Metrics the shadow-log scorer reports, and cannot report

This section specifies what the per-city shadow-log scorer is intended to report. No implementation existed in
`backend/` when this was drafted <!-- VERIFY: scorer not yet implemented on 2026-10-13 -->, and nothing here has been run. The scored
quantity is each candidate's per-conductor `ampacity_amps` in a city's v3 log; the provisional `bundle`
field (ampacity scaled by an assumed sub-conductor count, labelled "NOT a verified equipment-limited circuit rating") is not scored.
<!-- VERIFY: owner to confirm that bundle ampacity is out of scope -->

**Reported, per city and per candidate:**

- n scored, and n excluded with the reason for each exclusion (truth not resolvable at the evaluation instant;
  `valid_time` at or after the 2026-11-17 cutoff; duplicate `(city, valid_time)`; candidate not `ok`, with its
  logged reason; prediction-method fallback, `fallback_used: true`, shown separately from provider fallback).
- Bias (mean signed error, prediction minus truth), MAE, RMSE, median absolute error.
- A **descriptive** over-prediction rate (share of rows where the prediction exceeds truth) and overshoot
  (the size of positive errors, for example mean and a high percentile). These are descriptive properties of a point forecast. They are **not**
  the calibrated 5%-target overrating rate and are not compared with the 8% figure.
- Paired block-bootstrap effect sizes with intervals for each pre-stated pair (the machinery and block-length
  sensitivity of v1/v2), with the multiplicity treatment fixed under decision 2.
- The minimum detectable difference at the achieved n (the same scaling as the table above), so a null result is read correctly.
- A **pooled, city-clustered** comparison across the four cities, and the **effective sample size** (rows corrected for temporal
  and cross-city dependence), for the pooled and per-city results.
- The label "reanalysis-derived, never sensor-validated" on every figure, plus the retrieval timestamp and a pointer to the persisted raw responses.
- **Validity-threat flags** (V1 to V3, and V5 once the rows carry a `forecast_model` field): the realized anchor source and age per row, each correction candidate's error split by anchor source (exploratory), a flag on every comparison that involves `reference_ml_refit_24h` or `persistence_24h`, and for `reference_ml_refit_24h` a second check at its own target hour (decision time + 24 h).

**Cannot be reported from the shadow logs:**

- The **calibrated overrating rate** at the nominal 5% target (needs the quantile-calibration pipeline).
- **Retained capacity** at a matched overrating rate (the same dependency).
- Anything about performance on the validation period or the test split for the per-city artifacts (in-sample or unscored by design; see the fit-window section).

Both could come only from a per-city port of the frozen FRESH harness, if one is built and verified on
synthetic fixtures before 2026-11-24 (decisions 1 and 9).

## Sign-off

Nothing in this draft is in force until the owner completes this block. The owner may accept the
recommendation, choose another option, or defer an item (in which case the "if nothing" consequence applies).

| No. | Decision | Option chosen (letter or text) | Initials / date |
|---|---|---|---|
| 1 | 8% overrating ceiling | C: point-error ranking, no ceiling (selected 2026-10-13) | |
| 2 | Multiple-comparison family | E + Holm, pooled family of 9 (selected 2026-10-13) | |
| 3 | 590-row gate vs "score what exists" | A: v2 governs (selected 2026-10-13) | |
| 4 | Corridor-era rows | A: not counted (selected 2026-10-13) | |
| 5 | 2026-11-24 and 2026-11-01 dates | A: keep all dates (selected 2026-10-13) | |
| 6 | Collector cadence | B: 4/day (selected 2026-10-13) | |
| 7 | Truth source and secondary check | A: archive only (selected 2026-10-13) | |
| 8 | Headline comparison and "negligible" threshold | D, X = 5 A, 3-of-4 cities; 8c own target hour (selected 2026-10-13) | |
| 9 | Scoring basis | C, reconstructed frames headline, logs as live check (selected 2026-10-13) | |
| 10 | Duplicates and pairing | A with (i) (selected 2026-10-13) | |
| 11 | Live weather model (V5) | B: gfs_seamless (selected 2026-10-13) | |

I have read this amendment, I acknowledge the known validity threats V1 to V6 (live-versus-training anchor, the `reference_ml_refit_24h` target hour, the logged `persistence_24h` definition, reanalysis truth, the live-versus-training weather model, the pre-fix one-hour forecast offset), I acknowledge that the fit-window deviation in "Recorded decision: fit window and the
model freeze" was made and accepted on 2026-10-12 as described, and I approve the choices recorded above as the per-city
confirmation protocol (v3), effective from the date below. These choices were made without reading any FRESH-basis outcome.

- Project owner (name): ______________________________
- Signature: ______________________________
- Date (UTC): ______________________________

## What happens by default if unsigned by 2026-11-01

The consequences below follow mechanically from the existing documents and code; they are not new decisions.

1. **Nothing in this draft is in force.** The protocol of record remains v2, which is corridor-based. The corridor-era
   record is untouched.
2. **The freeze still happens.** The 12 per-city artifacts committed on 2026-10-12 are what the collector uses on 2026-11-01. The
   fit-window decision stands because it was accepted and recorded in the runbook on 2026-10-12.
3. **Collection continues** at the cadence in the workflow file (2/day) and per-city logs keep accruing. Nobody should read outcomes before 2026-11-24.
4. **Per-decision defaults** are the "if the owner does nothing" entries above, in short: no ceiling applied; no
   family-wise correction defined; 590-row code gate in conflict with v2; corridor rows not counted; both dates unchanged; cadence 2/day;
   archive truth with no secondary check; v2's qualitative defaults without numeric thresholds; basis and duplicate handling left to the scorer author; live model stays `ecmwf_ifs` with V5 stated.
5. **The drafter's recommendation for the unsigned case (itself the owner's to accept).** Treat any per-city result on 2026-11-24
   as exploratory and descriptive: report the metrics above with intervals and the sample size, make no pass/fail
   selection claim, and state that the thresholds were not pre-registered. This protects the one-shot discipline;
   the alternative, letting the person running the evaluation fill in the missing numbers after seeing results, does not.
6. **Earliest sensible deadline.** Items 1, 2, 3, 6, 8 and 11 should be signed before 2026-11-01. Item 6 (cadence) loses
   value every day it is delayed, because each day at 2/day forgoes about 2 rows per city if 4/day is wanted.

## Change log

| Date | Change |
|---|---|
| 2026-10-13 (V6) | Added V6: rows logged before 2026-10-13 predicted the weather one hour before the scored hour (`forecast_days=1` plus a nearest-earlier-hour lookup); fixed with `forecast_days=2` and a strict lookup; rows without a `forecast_model` field are excluded from scoring. |
| 2026-10-13 (owner selections) | Recorded the project owner's selections for all eleven decisions in "Owner selections" and the sign-off table (decisions 1 and 9 differ from the drafter's recommendations, with notes); signature still pending; noted that decision 9 implies a per-city point-metric port of the frozen harness and that the scorer plan must be extended to include it. |
| 2026-10-13 (review pass, 2) | Added V5 (live `ecmwf_ifs` versus training `gfs_seamless`) and decision 11, and extended the sign-off. |
| 2026-10-13 (review pass) | Added persistence comparisons to decision 2's family (new option B2; recommendation changed from 6 to 9 tests); added the standalone "Known validity threats" section (V1 anchor mismatch, V2 `reference_ml_refit_24h` target hour, V3 logged `persistence_24h` definition, V4 reanalysis/shared weather) with sign-off acknowledgement and scorer flags. |
| 2026-10-13 | Draft created for owner review. If signed, supersedes v2 only for per-city scoring of the four rating points; leaves the frozen corridor-era record (v1, v2, the 2026-10-06 correction and all corridor tables in `forecast_correction_followup_audit.md`) and the legacy corridor logs untouched. Records the already-accepted fit-window decision (train + validation) from the shadow collection runbook. No existing document was edited. |

**Suggested follow-up (the owner's call, not done here):** once signed, add a one-line pointer from
`forecast_correction_followup_audit.md` (at the v2 section) to this document, and one from
`shadow_collection_runbook.md`'s "Evidence base and the 2026-11-24 date" paragraph.
