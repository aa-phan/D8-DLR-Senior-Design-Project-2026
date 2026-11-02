<!-- generated-by: gsd-doc-writer -->
# Confirmation Protocol v4 — Early Selection Amendment (SIGNING COPY)

> **Signed 2026-11-02 by the project owner (`aaphan`, the name exactly as typed). This is the signed record of v4. The reviewed draft is [`confirmation_protocol_v4_early_selection.md`](confirmation_protocol_v4_early_selection.md); this copy repeats its full text with the owner's selections filled in below. The owner signed with one change to owner item O4 (AUSTIN switches to Drake ACSR at 100 degrees C); every other item is at the drafter's recommendation (option A). Every protocol time below is in UTC with a trailing Z.**

## In plain English

This document replaces the single 2026-11-24 evaluation with one read of the rows already collected, scored at 2026-11-01T00:00:00Z, and it only counts once you sign it; until then signed v3 (one read at 2026-11-24T00:00:00Z) still governs. The read scores rows from 2026-09-30 up to, but not including, 2026-10-25, which is about 100 six-hourly rows per city, and the week between the last scored hour and the read lets the weather record settle. A shadow model has to beat the plain forecast by at least 2% of the city's average ampacity (about 25 to 31 A at the Drake settings, with AUSTIN scored under Drake at 100 degrees C as your answer to item O4 directs), a bar that scales with the conductor and so does not move if Power Systems changes it, replacing the old fixed 5 A. Only the new rows can pick a winner, while two checks on older data, a conductor-sensitivity re-score and a held-out test-window re-score, can only rule a candidate out. One method is chosen for all four cities, and it has to help in at least 3 of the 4. If nothing clears the bar there is no pick and no shadow model replaces `ml`, and one pre-registered re-test on 2026-11-08T00:00:00Z re-grades all rows under the same rules, after which, if it also finds no winner, there is no day-ahead pick and the interim method keeps running. "No pick" is a realistic result, because a 2% bar is large next to the gaps seen in earlier development data. Nothing in this protocol changes the live ratings, and wiring a picked model into the live system is a later phase. By signing you also give written permission to score the frozen models on the held-out March-to-September window and you accept the eleven numbered owner items below, each with my recommendation and what happens if you do nothing. Several registered dates were already past when this was drafted (see "Status and supersession"); I have not moved them, and signing as drafted keeps them.

## Status and supersession

**Status:** DRAFT, written 2026-11-02 (UTC; the evening of 2026-11-01 in Central time). Not in force until signed. Until the sign-off block is completed, the protocol in force is signed v3, `confirmation_protocol_v3_per_city.md`, whose single FRESH read is at 2026-11-24T00:00:00Z. **Signed 2026-11-02 by `aaphan` (see the signing copy), so v4 is in force from that date and v3's 2026-11-24 read is retired.**

**Amends (if signed):** `confirmation_protocol_v3_per_city.md`, for per-city scoring of the four rating points only: decision 5 (dates) and decision 8 (threshold and fallback actions) are replaced; the rest carries over (see "What v4 changes and what it keeps"). It does **not** edit or replace the corridor-era record (v1, v2, the 2026-10-06 correction and every corridor-era table), which stays exactly as written.

**Related records:** `shadow_early_decision_options.md` (candidates, evidence bases, conductor analysis), `confirmation_protocol_v3_per_city.md`, `forecast_correction_followup_audit.md` (ABLATION, TEST and FRESH definitions), `austin_conductor_mot.md` (Austin Energy input of 2026-10-27), `shadow_collection_runbook.md`.

**Timing at drafting (these are facts for the owner, not decisions).** This draft was written at 2026-11-02T05:02Z. At that moment:

| Registered date | Value | State at drafting |
|---|---|---|
| `power_systems_deadline` | 2026-10-31T00:00:00Z | passed |
| `model_freeze` | 2026-11-01T00:00:00Z | passed |
| `read1.cutoff` | 2026-10-25T00:00:00Z | passed (it is the "valid_time strictly before" bound, so it only fixes which rows count) |
| `read1.instant` | 2026-11-01T00:00:00Z | passed; read 1 may run as soon as this document is signed |
| `read2.cutoff` | 2026-11-01T00:00:00Z | passed |
| `read2.instant` | 2026-11-08T00:00:00Z | still ahead |
| `v3_retired_instant` | 2026-11-24T00:00:00Z | still ahead (retired by this document) |

The dates are written as decided on 2026-10-25; the drafter has not shifted any of them. What keeps the read honest is not the calendar but the order: this document must be signed before any predicted-versus-truth figure for a valid_time on or after 2026-09-30 is computed or read. The owner states in the sign-off acknowledgement that none was read.

## Anti-peeking statement for this draft

While drafting this amendment, no predicted-versus-truth outcome was computed, read or printed for any row whose `valid_time` is on or after 2026-09-30, and no scorer was run. Only counts, timestamps and status fields were read. Every accuracy-related figure in this document comes from non-FRESH evidence already on record: the ABLATION mean truth ampacities (rows before 2026-03-17) and the published corridor-era development results.

## What v4 changes and what it keeps

**Keeps unchanged (carried over from signed v3):** decision 1 (point-error ranking, no ceiling), decision 2 (the pooled, city-clustered headline family of 9 tests with Holm), decision 3 (v2 governs: score what exists), decision 4 (corridor-era rows are not counted), decision 6 (collector cadence), decision 7 (archive reanalysis is the truth source), decision 9 (reconstructed frames are the headline, shadow logs are the live-system check, never pooled), decision 10 (first-logged row per `(city, valid_time)`, complete-case pairing), decision 11 (`gfs_seamless`), validity threats V1 to V6, and the 12 frozen artifact hashes in `data/shadow/models/ARTIFACT_HASHES.sha256`.

**Replaced:** decision 5 (dates) by "Read 1" and "Read 2 (conditional re-test)"; decision 8 (the 5 A threshold, the fallback to `ml_wind_corrected` or `raw_forecast`) by "Selection rule". Decision 8's sub-item 8c (`reference_ml_refit_24h` is scored at its own target hour, decision time + 24 h, with the logged-`valid_time` score reported alongside, flagged) carries over.

**Added:** the evidence bases and what each may support, the conductor handling, the ABLATION and TEST vetoes, the conditional second read, and the list of frozen evaluation modules v4 permits to change.

## Retirement of the 2026-11-24 run

The 2026-11-24 evaluation is retired. Its instant 2026-11-24T00:00:00Z, its valid-time cutoff 2026-11-17T00:00:00Z and its fetch window 2026-09-28..2026-11-16 are no longer used, and no outcome under those dates will be computed. The evaluation code will refuse a FRESH run at the retired instant. The corridor-era record is untouched.

## Read 1

| Item | Value |
|---|---|
| Round name | `v4-read1` |
| Evaluation instant | 2026-11-01T00:00:00Z |
| Rows scored | `valid_time` strictly before 2026-10-25T00:00:00Z, and `valid_time` on or after 2026-09-30T00:00:00Z |
| Reconstruction fetch window | 2026-09-28 to 2026-10-24 |
| Slots per city | 100 (25 days x 4 six-hourly slots) |
| Family alpha | 0.05 |
| Evidence subroot | `data/shadow/evaluation/v4-read1` |

It is a one-shot read: it is not repeated, re-scoped or re-parameterised if the result is unfavourable, and a second run into the same evidence subroot is refused. **Truth availability:** the reanalysis archive runs about 5 days behind (Open-Meteo documents ERA5 as "daily with 5 days delay"), and the last scored hour, 2026-10-24T18:00:00Z, sits about 7.25 days before the instant. **A fetch failure is recorded per city and never retried.** A city with no usable frame reports "insufficient data" and is not imputed.

## Read 2 (conditional re-test)

| Item | Value |
|---|---|
| Round name | `v4-read2` |
| Runs only if | read 1 names no winner |
| Evaluation instant | 2026-11-08T00:00:00Z |
| Rows scored | `valid_time` strictly before 2026-11-01T00:00:00Z, and `valid_time` on or after 2026-09-30T00:00:00Z |
| Reconstruction fetch window | 2026-09-28 to 2026-10-31 |
| Slots per city | 128 (32 days x 4 six-hourly slots) |
| Family alpha | 0.05 |
| Models | the configurations and artifacts frozen at 2026-11-01T00:00:00Z, the same ones read 1 scored |
| Evidence subroot | `data/shadow/evaluation/v4-read2` |

Read 2 grades **all** rows, including read 1's 100 rows per city, under the same rules as read 1. **Read 2 is not independent of read 1:** 100 of its 128 rows per city were already seen in read 1, and a second look at overlapping data is a second chance to clear a point-estimate bar. That is why this document says so plainly and why owner item O2 asks how read 2's evidence labels are to be read. If read 1 names a winner, read 2 does not run.

## Evidence bases

The three bases are those of `forecast_correction_followup_audit.md`.

| Basis | Rows | What it may support in v4 | What it may not support |
|---|---|---|---|
| FRESH | `valid_time` on or after 2026-09-30T00:00:00Z, within the round's window | **Decides.** Only a FRESH read can name a winner. | Nothing beyond the round's own window |
| ABLATION | rows strictly before 2026-03-17 (train to 2025-09-01T18:00:00Z, validation 2025-09-02T00:00:00Z to 2026-03-16) | **Only vetoes.** A conductor-invariance re-score: does a candidate's standing change when the conductor changes? | A confirmation claim, or a pick. The configurations were selected on this data, so its selection optimism is unchanged |
| TEST | 2026-03-18T00:00:00Z <= `valid_time` < 2026-09-30T00:00:00Z, the frozen artifacts scored out of sample | **Only vetoes.** | A confirmation claim, or a pick. The corridor-era result on this window was already read once, so it is partly "already seen" |

**Signing this document is the owner's written decision that scoring the 12 frozen artifacts on the TEST split is permitted.** That departs from v3's "unscored by design" for those artifacts (the Phase 4 principle called re-scoring the test set a second selection-on-test-set decision). Owner item O7 puts that choice to the owner explicitly. Nothing in ABLATION or TEST can name a winner; they can only disqualify one.

## Conductor in the headline

- **Headline conductor (D-01).** The FRESH headline scores the candidates under the production per-city conductor configuration: truth, `raw_forecast` and persistence are recomputed under it, and `ml_cooling_corrected` and `reference_ml_refit_24h` use models fit under it. `ml_wind_corrected` is conductor-independent and is reused.
- **Default is Drake (D-09, D-11).** Every city stays on 795 kcmil Drake ACSR at 75 degrees C, 900 m and its current bearing unless Power Systems answered by 2026-10-31T00:00:00Z. In the default case the headline and the frozen Drake setup coincide, and the 12 frozen artifacts are the production-conductor models. **As signed, AUSTIN is the one exception (owner item O4):** AUSTIN's production conductor is 795 kcmil Drake ACSR with a maximum operating temperature of 100 degrees C, with its elevation (900 m) and azimuth left at the current model defaults; CORPUS_CHRISTI, MIDLAND and EL_PASO stay on the model-default Drake 75 degrees C configuration.
- **Status of that deadline at drafting.** The deadline has passed. This draft records no complete Power Systems answer for any city. One partial input exists: an Austin Energy teammate confirmed on 2026-10-27 that Austin's 345 kV lines are 795 Drake ACSR with a 100 degrees C maximum design temperature (`docs/data-science/decisions/austin_conductor_mot.md`). That note says the value lands in the production table in Phase 7 and that no value had been changed. This draft did not treat it as adopted; owner item O4 asked whether it counts. **Resolved at signing (2026-11-02):** the owner ruled that it counts for AUSTIN, as an answer to O4 that stands in for the complete-answer definition below (source: Austin Energy teammate, relayed by the owner 2026-10-27, corroborated by Austin Energy's 2005 ERCOT ROS/SPWG statement; see `austin_conductor_mot.md`). D-09's values are unchanged for the other three cities.
- **Consequences for AUSTIN (O4, accepted by the owner at signing).** (1) AUSTIN's FRESH headline is scored under Drake at 100 degrees C: truth, `raw_forecast` and persistence are recomputed under it. (2) `ml_cooling_corrected` and `reference_ml_refit_24h` are refit for AUSTIN under that configuration on rows before 2026-03-17 only (asserted), and the reference rows are rebuilt the same way. (3) The TEST veto is re-scored under the production conductors before read 1 is run (see "TEST design and veto criterion"). (4) The 12 frozen Drake artifacts are still scored as the labelled secondary. (5) No registered date moves: the read-1 instant, cutoff, fetch window and slot counts are as registered. The configuration change itself lands later, in the plan that applies the Power Systems answers; this protocol does not edit `backend/config.py`.
- **Refit only for cities whose values arrive (D-10).** For a city whose values were adopted, cooling and reference are refit on rows before 2026-03-17 only (asserted), saved as new hashed artifacts under `data/models/conductor_refit/<config_version>/` with a sha256 manifest that is checked before any file is loaded, and never overwrite the frozen artifacts. Wind is never refit.
- **A complete Power Systems answer for one city** is: the conductor type with catalogue diameter and resistance, the maximum operating temperature, the elevation and the azimuth. A city with anything less stays on Drake, except where owner item O4 says otherwise (as signed: AUSTIN only).
- **Frozen Drake artifacts as a labelled secondary.** The 12 frozen Drake artifacts are scored in the same read as a labelled secondary result.
- **Live shadow logs** (Drake, as collected) are the live-system check and are never pooled with the headline.
- **Late answers (D-03).** Values that arrive after the read fall under D-03: if the ABLATION re-score showed the ranking invariant, the decision stands and cooling and reference are refit under the real values for serving with no FRESH re-read. If it did not, the decision is labelled **conductor-conditional**, and a pre-registered descriptive re-score under the confirmed conductor (named round `v4-late-descriptive`) may flag a problem but cannot overturn the decision.

## Selection rule

This replaces v3 decision 8. It is stated for one round; read 2 applies it again with its own rows.

**Definitions.**

1. For each city c with data, T_c is the mean `truth_amps` over that city's scored rows in the round, and bar_c = 0.02 x T_c.
2. For a comparison of a real candidate X against a baseline B, the per-city benefit is MAE of B minus MAE of X on the paired complete-case rows (positive means X is better). The **pooled benefit** is the paired-row-weighted mean of the per-city benefits. The **pooled bar** is the paired-row-weighted mean of the cities' bars, with the same weights.
3. A candidate's **level against `raw_forecast`** is "insufficient data" (the pooled comparison cannot be computed), "supported" (pooled benefit >= pooled bar and the Holm-adjusted p-value <= the round's family alpha, in the candidate's favour), "indicated, not resolved" (pooled benefit >= pooled bar but not supported), else "not shown". The family is v3's 9 tests, city-clustered, Holm, unchanged.
4. A candidate is **consistent** if it is favoured over `raw_forecast` by point estimate (positive per-city benefit) in at least 3 cities and at least 3 cities have data.
5. A candidate **qualifies** if its level is "supported" or "indicated, not resolved", it is consistent, and it is not vetoed (see the ABLATION and TEST sections).

**Winner.**

- `ml_wind_corrected` wins if it qualifies, unless an alternative (`ml_cooling_corrected` or `reference_ml_refit_24h`) qualifies and is consistently better than it: its pooled margin over `ml_wind_corrected` is at least the pooled bar for that comparison and it is favoured over `ml_wind_corrected` in at least 3 cities. Between two such alternatives, the larger pooled margin wins.
- If `ml_wind_corrected` does not qualify, the qualifying alternative with the larger pooled benefit over `raw_forecast` wins.
- Exact ties are broken in the order `ml_wind_corrected`, `ml_cooling_corrected`, `reference_ml_refit_24h`.
- If nothing qualifies there is **no pick**, and no shadow model replaces `ml` (D-07). The v3 fallbacks ("keep `ml_wind_corrected`", "fall back to `raw_forecast`") no longer apply.
- `persistence_24h` is a baseline in the Holm family only. It cannot be picked.

**Worked example, from non-FRESH evidence only.** The ABLATION mean truth ampacities under Drake are 1257.8 A (AUSTIN), 1375.8 A (CORPUS_CHRISTI), 1525.4 A (MIDLAND) and 1236.8 A (EL_PASO). The bars are therefore 25.2, 27.5, 30.5 and 24.7 A. With equal paired rows in every city the pooled bar is (25.156 + 27.516 + 30.508 + 24.736) / 4 = 26.98 A. A candidate whose MAE is 20 A better than `raw_forecast` pooled is "not shown" even if the p-value is small. One that is 30 A better pooled, favoured in 3 of 4 cities and not vetoed, is at least "indicated, not resolved" and qualifies.

**Why "no pick" is likely (Pitfall 11).** The earlier corridor-era development gaps against `raw_forecast` were about 26 A for wind at Midland and 4.4 A for cooling at Austin, and wind was slightly worse than raw at Austin. Corridor `min()` values do not transfer exactly to per-city values, but the largest known gap is about the size of the bar and most are far below it, so "no candidate qualifies" is a realistic outcome. This is stated now so that it is not read as a failure later.

## ABLATION design and veto criteria

This section is the drafter's proposal for the owner to approve (O5, O6).

- **Splits.** Rows strictly before 2026-03-17 only (asserted). Train to 2025-09-01T18:00:00Z (2360 exact-lead rows per city); validation 2025-09-02T00:00:00Z to before 2026-03-17T00:00:00Z (784 rows per city).
- **Variants.** Six conductor variants: Drake-75 (the control), Drake-100, Falcon-90, Suwannee-150, Suwannee-200, and Drake-75-AUSTIN-163m (the control geometry with Austin's measured elevation of 163 m, applying to AUSTIN only). Emissivity and absorptivity 0.8, `resist_temp_coef` 0.00404, and bearings are held fixed so only the conductor moves. The catalogue values are in the registry. The Suwannee rows use a resistance at 25 degrees C in the repo's linear model, which is unverified at 150 to 200 degrees C (flagged in the options record).
- **Fits.** Wind is fit once on train (it does not depend on the conductor). Cooling and reference are fit on train under each variant, in memory, and never written under `data/shadow/models`. The 12 frozen artifacts are not touched.
- **Scored on validation:** MAE, RMSE and bias; the same divided by mean truth; the rank order and Kendall tau against the control; the 9-test family at block lengths 1, 4, 8 and 28; margins over `raw_forecast` in A and in percent.
- **Veto.** A candidate is vetoed if, under any variant, (a) the sign of its pooled margin over `raw_forecast` differs from the control's, or (b) (cooling and reference only) the sign of its pooled margin over `ml_wind_corrected` differs from the control's, or (c) whether it is favoured over `ml_wind_corrected` in at least 3 cities differs from the control.
- **"Ranking invariant"** (used by the late-answer rule) means: no candidate is vetoed and Kendall tau is 1.0 for every variant.

## TEST design and veto criterion

- **Window.** 2026-03-18T00:00:00Z <= `valid_time` < 2026-09-30T00:00:00Z, 784 slots per city. The first TEST day (2026-03-17) is excluded because its anchors fall inside the fit window.
- **Data.** The cached `_2024-01-20_2026-09-29_` frames only. The FRESH-dated cache files are never opened. Archive weather comes from the frame's own truth columns. The frozen artifacts are scored out of sample.
- **Veto.** A candidate is vetoed if its per-city MAE is strictly higher than `raw_forecast`'s, on complete-case pairs, in at least 3 of the cities with data.
- **Under adopted Power Systems values.** If Power Systems values are adopted, TEST is re-scored under the production conductors before read 1 is run (as signed: AUSTIN at Drake 100 degrees C with its refit cooling and reference models; the other three cities unchanged). The earlier wording "before the instant" is replaced by "before read 1 is run" because the read-1 instant, 2026-11-01T00:00:00Z, had already passed when this was signed; no registered date moves.

## Permitted changes to frozen evaluation code

v4 permits exactly these changes, and no others, to modules otherwise frozen:

- `backend/forecast_shadow_eval_core.py`: named rounds `v4-read1`, `v4-read2` and `v4-late-descriptive`; the defaults move to `v4-read1`; a refusal at the retired instant; a refusal of FRESH runs while this document is unsigned; a relative-margin parameter; the protocol text.
- `backend/forecast_shadow_confirm.py`: `--round`, `--vetoes`, a production-conductor geometry seam whose default path is unchanged, the frozen-Drake secondary block, scored-artifact hashes, and the v4 rule.
- `backend/forecast_shadow_score.py`: `--round`, and the v4 rule as a live-system label.
- Their tests.
- **New modules added:** `forecast_shadow_decision_v4.py`, `forecast_conductor_refit.py`, `forecast_conductor_ablation.py` and `forecast_test_split_score.py`.

The v3 decision module, the collector, the fit modules, `shadow_collect.yml` and `data/shadow/models` stay byte-identical (the COND-02 golden checks this).

## Live-system check

The shadow-log scorer runs at each read with the same round, reports separately from the headline, is labelled by the v4 rule, and never decides.

## Owner items

Eleven items need the owner. "Drafter's recommendation" is a suggestion, never a decision. Each item shows the options, my recommendation and what happens if you do nothing.

### O1. What "qualifies" means: pooled bar or per-city bars

**Question.** Is the 2% bar applied to the pooled comparison, or to each city separately?

**Options.**
- A. Pooled, paired-row-weighted bar (as in "Selection rule"). The level comes from the pooled benefit against the pooled bar; consistency counts cities favoured by point estimate.
- B. Per-city bars. A city counts toward the 3-of-4 only if its own benefit is at least its own bar, and the level still uses the pooled comparison against the pooled bar.

**Drafter's recommendation.** A. It is one number to read, it matches v3's pooled headline, and B makes a pick much less likely.

**If the owner does nothing.** A.

### O2. How read 2's evidence is labelled

**Question.** Read 2 grades overlapping rows a second time, so a second chance to pass exists. Do its labels change?

**Options.**
- A. Same rules as read 1, with the overlap disclosed in the report (registry family alpha 0.05 at both reads).
- B. Read 2 needs the level "supported" (not just "indicated, not resolved") to name a winner.
- C. The family alpha is 0.025 at each read, splitting the 0.05 budget across the two looks.

**Drafter's recommendation.** A, as decided in D-08. B or C is safer against a lucky second pass, at the price of a likelier second "no pick".

**If the owner does nothing.** A. If C is chosen, `read1.family_alpha` and `read2.family_alpha` both become 0.025 in the registry.

### O3. If read 2 also names no winner

**Question.** What happens after two reads with no winner?

**Options.**
- A. No day-ahead pick; the interim G6 method continues; 2026-11-24 stays retired; any later evaluation needs a new signed protocol.
- B. Keep `ml_wind_corrected` as the working engineering default, labelled "not supported by the evidence".
- C. Pre-register a third read now at a later date.

**Drafter's recommendation.** A. It says plainly that the evidence did not support a pick, and it does not add a third look.

**If the owner does nothing.** A.

### O4. Partial Power Systems answers

**Question.** If Power Systems answered for some cities but not all, which cities switch conductor? Which cities count as having answered by 2026-10-31T00:00:00Z is the owner's statement at signing.

**Austin Energy input (2026-10-27).** An Austin Energy teammate confirmed Drake ACSR with a 100 degrees C maximum design temperature for Austin's 345 kV lines (`austin_conductor_mot.md`). That gives Austin's conductor type and maximum operating temperature but not a utility-confirmed azimuth or elevation, so under the definition in "Conductor in the headline" it is a partial answer unless you say otherwise. If you count it as complete, AUSTIN's headline would be under Drake at 100 degrees C, cooling and reference would need an AUSTIN refit, and the TEST veto would need re-scoring "before the instant", which has already passed. This draft does not change D-09's values.

**Options.**
- A. Switch only the cities with a complete answer; the rest stay on Drake.
- B. Switch no city unless all four answered.
- C. Switch any city that answered anything.

**Drafter's recommendation.** A.

**If the owner does nothing.** A, and, as no complete answer is recorded, every city stays on Drake.

**Owner's selection (signed 2026-11-02): custom, not A, B or C.** Verbatim reply: `sign-with-changes: 04=switch austin based on given answers;aaphan`. Recorded as: **Switch AUSTIN using the owner-supplied answer: 795 Drake ACSR with a maximum operating temperature of 100 degrees C** (source: Austin Energy teammate, relayed by the owner 2026-10-27, corroborated by Austin Energy's 2005 ERCOT ROS/SPWG statement; see `docs/data-science/decisions/austin_conductor_mot.md` and `.planning/workstreams/production-pipeline/phases/03-real-data-validation/03-05-CONDUCTOR-RESEARCH.md`). AUSTIN's elevation and azimuth stay at the current model defaults (900 m and 173.15 degrees; they are not part of the answer). CORPUS_CHRISTI, MIDLAND and EL_PASO stay on the model-default Drake 75 degrees C configuration. This supersedes the drafter's A for this item and the "If the owner does nothing" line above.

**Necessary consequence (explained to the owner, who accepted it).** AUSTIN's FRESH headline is scored under Drake at 100 degrees C; its cooling and reference models are refit under that configuration on rows before 2026-03-17 only; and the TEST veto is re-scored under the production conductors **before read 1 is run** (the draft's "before the instant" wording is replaced by "before read 1 is run" for this purpose, because the read-1 instant has already passed). No registered date moves. The registry rows `power_systems.partial_answers`, `power_systems.switch_cities`, `power_systems.austin_config`, `refit.cities` and `test.rescore_gate` encode this choice.

### O5. Azimuth or emissivity variants in ABLATION

**Question.** The ABLATION set varies the conductor but holds azimuth and emissivity fixed. Should it also vary them?

**Austin Energy input.** The 2026-10-27 teammate input is already covered by the Drake-100 variant. The 2005 Austin Energy filing used emissivity and absorptivity 0.5, but on 2026-10-27 the owner left emissivity and absorptivity at 0.8.

**Options.**
- A. Not added (the six variants as drafted).
- B. Add azimuth variants (values to be given by the owner).
- C. Add an emissivity and absorptivity 0.5 variant.

**Drafter's recommendation.** A. Each added variant is another chance to veto every candidate. The compute cost is negligible (about 3.5 s per city fit), so the cost is the larger veto surface.

**If the owner does nothing.** A.

### O6. ABLATION veto criteria

**Question.** Are the three ABLATION veto clauses (a) to (c) acceptable as drafted?

**Options.**
- A. As drafted: a sign flip against `raw_forecast`, a sign flip against `ml_wind_corrected` (cooling and reference), or a change in the 3-of-4 favoured-over-wind status.
- B. Only the sign flip against `raw_forecast` vetoes; the other clauses are reported, not vetoing.
- C. ABLATION is reported but never vetoes.

**Drafter's recommendation.** A.

**If the owner does nothing.** A.

### O7. TEST veto criterion, and permission to score TEST

**Question.** Is scoring the 12 frozen artifacts on the TEST split permitted, and is the TEST veto as drafted?

**Options.**
- A. TEST scoring is permitted and the veto is as drafted (strictly higher MAE than `raw_forecast` in at least 3 of the cities with data).
- B. TEST scoring is permitted but descriptive only; it does not veto.
- C. TEST scoring is not permitted; there is no TEST veto.

**Drafter's recommendation.** A. It gives one more out-of-sample check on the frozen artifacts before any pick, and the corridor-era result is already known, so the cost is that the test window is partly seen.

**If the owner does nothing.** If the document is signed with this item blank, A applies as written. If it is not signed, TEST scoring is not permitted and does not run.

### O8. Production rows for FRESH-window dates

**Question.** Production backfill and live ratings are published for dates in the FRESH window. Are they shadow outcomes?

**Options.**
- A. They are not shadow outcomes, provided nothing joins them to shadow predictions.
- B. They count as a risk, so production ratings for FRESH-window dates are withheld until the last read is done.
- C. A, plus a written rule banning any join and a check that none exists.

**Drafter's recommendation.** A. No recorded ruling exists today, so a ruling is needed either way. C is a stricter version at low cost.

**If the owner does nothing.** No ruling is on record; production rows are published without cover and the question stays open.

### O9. Read 2 models and configurations

**Question.** If Power Systems answers between read 1 and read 2, does read 2 use the new values?

**Options.**
- A. No. Read 2 scores the configurations and models frozen at 2026-11-01T00:00:00Z, the same ones read 1 scored.
- B. Yes, a config refresh is allowed between the reads, and read 2 is labelled as not comparable to read 1.

**Drafter's recommendation.** A. It keeps read 2 a re-test of the same thing rather than a new experiment.

**If the owner does nothing.** A.

### O10. The relative bar for alternative versus wind

**Question.** Does the 2% relative bar also decide whether an alternative displaces `ml_wind_corrected`?

**Options.**
- A. Yes, the pooled margin over wind must be at least the pooled bar.
- B. No, the alternative-versus-wind comparison keeps v3's absolute 5 A.
- C. Yes, and the alternative must also reach "supported".

**Drafter's recommendation.** A. One bar for every comparison, and it moves with the conductor.

**If the owner does nothing.** A.

### O11. When the live-system check runs

**Question.** When does the shadow-log scorer run?

**Options.**
- A. At each read, with the same round.
- B. Only at the final read.
- C. Not at all.

**Drafter's recommendation.** A. It is cheap and labelled, and it never decides.

**If the owner does nothing.** A.

## Registered values (machine-checked)

`backend/tests/protocol_v4_registry.py` parses this table and `backend/tests/protocol_v4_doc_test.py` checks it. Every instant is UTC with a trailing Z.

| Key | Value |
|---|---|
| `protocol_version` | `v4` |
| `amends` | `confirmation_protocol_v3_per_city.md` |
| `v3_retired_instant` | `2026-11-24T00:00:00Z` |
| `fresh_basis_start` | `2026-09-30T00:00:00Z` |
| `model_freeze` | `2026-11-01T00:00:00Z` |
| `power_systems_deadline` | `2026-10-31T00:00:00Z` |
| `read1.name` | `v4-read1` |
| `read1.instant` | `2026-11-01T00:00:00Z` |
| `read1.cutoff` | `2026-10-25T00:00:00Z` |
| `read1.fetch_start` | `2026-09-28` |
| `read1.fetch_end` | `2026-10-24` |
| `read1.slots_per_city` | `100` |
| `read1.family_alpha` | `0.05` |
| `read2.name` | `v4-read2` |
| `read2.instant` | `2026-11-08T00:00:00Z` |
| `read2.cutoff` | `2026-11-01T00:00:00Z` |
| `read2.fetch_start` | `2026-09-28` |
| `read2.fetch_end` | `2026-10-31` |
| `read2.slots_per_city` | `128` |
| `read2.family_alpha` | `0.05` |
| `read2.runs_only_if` | `read1_no_pick` |
| `read2.models` | `frozen_at_read1` |
| `late.name` | `v4-late-descriptive` |
| `rule.relative_margin_fraction` | `0.02` |
| `rule.bar_scope` | `pooled_paired_row_weighted` |
| `rule.consistency_min_cities` | `3` |
| `rule.family_size` | `9` |
| `rule.block_lengths` | `1,4,8,28` |
| `rule.n_resamples` | `10000` |
| `rule.tie_order` | `ml_wind_corrected,ml_cooling_corrected,reference_ml_refit_24h` |
| `rule.alternative_vs_default_bar` | `relative` |
| `ablation.train_end` | `2025-09-01T18:00:00Z` |
| `ablation.validation_start` | `2025-09-02T00:00:00Z` |
| `ablation.validation_end_exclusive` | `2026-03-17T00:00:00Z` |
| `ablation.train_rows_per_city` | `2360` |
| `ablation.validation_rows_per_city` | `784` |
| `ablation.control` | `Drake-75` |
| `ablation.variants` | `Drake-75,Drake-100,Falcon-90,Suwannee-150,Suwannee-200,Drake-75-AUSTIN-163m` |
| `ablation.variant.Drake-75` | `diameter_m=0.02814;resistance_ac=0.0726;max_temp_c=75;elevation_m=900;cities=all` |
| `ablation.variant.Drake-100` | `diameter_m=0.02814;resistance_ac=0.0726;max_temp_c=100;elevation_m=900;cities=all` |
| `ablation.variant.Falcon-90` | `diameter_m=0.03924;resistance_ac=0.0371;max_temp_c=90;elevation_m=900;cities=all` |
| `ablation.variant.Suwannee-150` | `diameter_m=0.02819;resistance_ac=0.0597;max_temp_c=150;elevation_m=900;cities=all` |
| `ablation.variant.Suwannee-200` | `diameter_m=0.02819;resistance_ac=0.0597;max_temp_c=200;elevation_m=900;cities=all` |
| `ablation.variant.Drake-75-AUSTIN-163m` | `diameter_m=0.02814;resistance_ac=0.0726;max_temp_c=75;elevation_m=163;cities=AUSTIN` |
| `ablation.veto_rule` | `sign_flip_vs_raw_or_default` |
| `test.window_start` | `2026-03-18T00:00:00Z` |
| `test.window_end_exclusive` | `2026-09-30T00:00:00Z` |
| `test.slots_per_city` | `784` |
| `test.veto_min_cities` | `3` |
| `test.rescore_gate` | `before_read1_run` |
| `refit.methods` | `ml_cooling_corrected,reference_ml_refit_24h` |
| `refit.root` | `data/models/conductor_refit` |
| `refit.fit_end_exclusive` | `2026-03-17T00:00:00Z` |
| `refit.cities` | `AUSTIN` |
| `power_systems.partial_answers` | `custom_switch_austin_drake_100c` |
| `power_systems.switch_cities` | `AUSTIN` |
| `power_systems.austin_config` | `diameter_m=0.02814;resistance_ac=0.0726;max_temp_c=100;elevation_m=900;line_azimuth=173.15;cities=AUSTIN` |
| `live_check.runs_at_each_read` | `yes` |

## Sign-off

Nothing in this draft is in force until the owner completes this block. The owner may accept the recommendation, choose another option, or leave an item blank (in which case the "if the owner does nothing" consequence applies).

| No. | Item | Option chosen |
|---|---|---|
| O1 | What "qualifies" means: pooled bar or per-city bars | A: pooled, paired-row-weighted bar (selected 2026-11-02) |
| O2 | How read 2's evidence is labelled | A: same rules as read 1, overlap disclosed; family alpha 0.05 at both reads (selected 2026-11-02) |
| O3 | If read 2 also names no winner | A: no day-ahead pick; interim G6 method continues; 2026-11-24 stays retired; any later evaluation needs a new signed protocol (selected 2026-11-02) |
| O4 | Partial Power Systems answers | Custom (owner-supplied): switch AUSTIN to 795 Drake ACSR at a maximum operating temperature of 100 degrees C (elevation and azimuth stay at model defaults); CORPUS_CHRISTI, MIDLAND and EL_PASO stay on model-default Drake 75 degrees C. Consequence accepted: AUSTIN headline scored under Drake 100 degrees C, AUSTIN cooling and reference refit under it, TEST veto re-scored under the production conductors before read 1 is run; no registered date moves (selected 2026-11-02) |
| O5 | Azimuth or emissivity variants in ABLATION | A: not added (selected 2026-11-02) |
| O6 | ABLATION veto criteria | A: as drafted (selected 2026-11-02) |
| O7 | TEST veto criterion, and permission to score TEST | A: TEST scoring permitted, veto as drafted (selected 2026-11-02) |
| O8 | Production rows for FRESH-window dates | A: not shadow outcomes, provided nothing joins them to shadow predictions (selected 2026-11-02) |
| O9 | Read 2 models and configurations | A: read 2 scores the configurations and models frozen at 2026-11-01T00:00:00Z (selected 2026-11-02) |
| O10 | The relative bar for alternative versus wind | A: yes, the relative bar decides alternative versus wind (selected 2026-11-02) |
| O11 | When the live-system check runs | A: at each read, with the same round (selected 2026-11-02) |

I have read this amendment. I acknowledge that validity threats V1 to V6 and the fit-window deviation recorded in v3 carry over unchanged. I approve the choices recorded above as confirmation protocol v4, effective from the date below, and I give written permission to score the 12 frozen per-city artifacts on the TEST split (O7). I acknowledge that several registered dates, including the Power Systems deadline, the model freeze and the read-1 instant, were already past when this was drafted, and that I have chosen to keep them as registered. I confirm that I have not read any FRESH-basis outcome, meaning any predicted-versus-truth figure for a `valid_time` on or after 2026-09-30, before signing.

- Project owner (name): aaphan
- Signature: aaphan
- Date (UTC): 2026-11-02

**Recorded with the signature (2026-11-02):** the owner's verbatim reply was `sign-with-changes: 04=switch austin based on given answers;aaphan`. "04" is owner item O4, set to the custom choice above. Every other owner item (O1 to O3 and O5 to O11) is the drafter's recommendation (option A) and was not changed. The registry in this copy equals the draft's registry (`backend/tests/protocol_v4_doc_test.py` checks it). The date is the UTC date of the reply. The executor recorded the reply and signed nothing.

## What happens by default if unsigned

1. Nothing in this draft is in force. Signed v3 governs.
2. The 2026-11-01 read cannot happen: the evaluation code refuses a FRESH run while this document is unsigned.
3. The 2026-11-24 v3 run stays the only FRESH read, with v3's 5 A threshold and its fallbacks.
4. The selection code that changes frozen evaluation modules waits for the signature, and SEL-01 to SEL-04 cannot be met in this phase.
5. TEST scoring of the frozen artifacts is not permitted.

## Change log

| Date (UTC) | Change |
|---|---|
| 2026-11-02 (signed) | Owner signed as `aaphan` (signing copy), sign-with-changes: O4 set to a custom choice (switch AUSTIN to Drake ACSR at 100 degrees C; elevation and azimuth at model defaults; other cities unchanged); O1 to O3 and O5 to O11 at the drafter's recommendation (A). Edited: this file's banner, the "In plain English" bar sentence, "Status and supersession" status line, "Conductor in the headline" (default bullet, deadline-status bullet, new AUSTIN-consequences bullet, complete-answer bullet), "TEST design and veto criterion" ("before the instant" replaced by "before read 1 is run"), the O4 block (owner's selection and consequence) and the registry (`power_systems.partial_answers` changed from `complete_cities_only` to `custom_switch_austin_drake_100c`; rows added: `power_systems.switch_cities`, `power_systems.austin_config`, `refit.cities`, `test.rescore_gate`). No registered date moved. |
| 2026-11-02 | Draft created for owner review (2026-11-01 evening Central). If signed, amends v3 decisions 5 and 8 for per-city scoring and retires the 2026-11-24 run. Records, but does not move, registered dates that were already past at drafting. No existing protocol document was edited. |
