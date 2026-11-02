<!-- generated-by: gsd-doc-writer -->
# Phase 7 re-validation and new go/no-go (REVAL-01)

**Status:** the measurements and the checklist are complete; the owner signed GO on 2026-11-02 (see "Decision"). The measurements in this note change no rating, model or setting; the label text changes only as the Decision records. Every figure cites a file in [`real_data_validation_p7/`](real_data_validation_p7/) (the offline re-run of 2026-09-08 to 2026-09-28, plan 07-14) or the Phase 3 note [`real_data_validation.md`](real_data_validation.md).

## In plain English

**What this is.** On 2026-10-21 the owner signed a NO-GO on lifting the "provisional" label from the stored ratings, blocking on four findings: B1 (fallback policy and the conductor the model assumes), B2 (the ml forecast was trained on one kind of wind and served another), B4 (the CORPUS_CHRISTI anomaly detector trips on 11% of hours) and B5 (after any fallback, the ml forecast sat out for hours, so the check that catches too-high ratings did not run). Phase 7 worked on all four, re-ran the same September fortnight offline, and this note sets the results against a checklist the owner fixed in advance (D-18). There is no numeric pass bar; the owner reads the evidence and signs GO or NO-GO.

**How each blocker closes.**

- **B1, fallback policy (D-12).** Kept as it was. A low-side fallback to the documented static rating is safe by the owner's standing rule; the only unsafe direction is a published rating above what the conditions support. Static ratings and the plausibility bounds are unchanged.
- **B1, conductor basis (D-13).** AUSTIN is now rated as 795 kcmil Drake at a 100 C maximum operating temperature (it was 75 C), from an Austin Energy teammate's statement; CORPUS_CHRISTI, MIDLAND and EL_PASO still use the model-default Drake at 75 C because Power Systems never sent values for them (`v4_selection/power_systems_gate.md`). A GO is allowed on this basis, and every row keeps saying which conductor basis produced it (`config_version`, `config_fingerprint`). The conductor question stays open for three cities, and for AUSTIN's elevation and line bearing, which are still model defaults.
- **B2, wind mismatch (D-14).** Fixed. All four ml models were retrained on the same line-perpendicular wind they are served (commit `e0a00a9`, new model fingerprints in "Checklist"). The upward bias that ml carried in Phase 3 (+41.9 to +87.6 A) is gone: +0.1 to -21.1 A in the re-run (`real_data_validation_p7/val02_forecast_by_city.csv`).
- **B4, CORPUS_CHRISTI trips (D-16).** Re-measured: 37 trips in 336 hours, 11.01%, exactly the Phase 3 rate and entirely from the learned-model branch (`val02_detector_by_city.csv`). The owner's decision was to accept it as safe, because a trip publishes the static rating, which is the safe fallback. The follow-up refit is logged with a proposed date the owner confirms below.
- **B5, band check after a gap (D-17).** Fixed. When the ml forecast sits out because of a gap, the naive forecast's band now checks the rating instead. The share of G6-evaluated hours in which some forecast band checked the rating is now 0.9875 (AUSTIN), 0.9405 (CORPUS_CHRISTI), 0.9366 (MIDLAND) and 1.0 (EL_PASO) (`val02_g6_band_by_city.csv`). This is the safety item: it is the check that catches a rating above its band.

**AUSTIN band engagement, before and after.** In Phase 3 the ml band checked 15 of 111 G6-evaluated AUSTIN hours (13.5%; `real_data_validation.md`, forecast table, `n_used_by_g6` 15, `n_withheld_gap` 96). In the re-run a band checked 317 of 321 hours (0.9875): the ml band 261, the naive stand-in 56, no band 4. The two populations are not like for like: the AUSTIN conductor change moved the computed rating above AUSTIN's lower plausibility bound, so 321 hours (not 111) reached G6 (15 low-side fallbacks, down from 225; `val01_outcomes_by_city.csv`). Both the B5 fix and the conductor change contribute, and the 100 C figure rests on one statement from an Austin Energy teammate.

**ml against naive (D-15).** With the B2 fix, ml has a lower mean error than naive in all four cities on the September window: 84.6 against 87.6 A (AUSTIN), 61.3 against 62.9 (CORPUS_CHRISTI), 80.2 against 80.3 (MIDLAND), 112.6 against 117.3 (EL_PASO). The gaps are small next to the forecast bands (260 to 470 A wide), and MIDLAND's 0.1 A is a tie. Because ml is not worse anywhere, D-15's trigger (ml worse than naive somewhere) did not fire; the owner still states the choice at the checkpoint. Supporting context, clearly not part of the checklist: an exploratory (not pre-registered) comparison over 2026-01-01 to 2026-09-29 found ml better than naive by +3.9 A pooled in all four cities, but not significantly better on the two-week September replay itself (+1.9 A, p 0.47).

**Replay check.** The re-run reproduces the recorded run with 0 fidelity mismatches in every replay. 333 AUSTIN steps are excluded by construction (the recorded steps used Drake 75 C, the new code recomputes at 100 C, so the two cannot agree); a control replay at the commit before that change matches all 2016 steps with 0 mismatches (`real_data_validation_p7/README.md`).

**The decision asked.** GO or NO-GO on lifting the provisional label for rows written from now on; if GO, whether to also relabel stored live rows from a date the owner names (backfill rows are never relabelled); the D-15 interim G6 method (keep ml or switch to naive); the date of the B4 follow-up; and the label text. Nothing reaches the live system until the push approved in plan 07-18; backfill rows keep their Phase 3 label whatever is chosen.

## Checklist (D-18)

No numeric bars. Each item shows its status, the evidence and the decision it rests on.

| Item | Status | Evidence | Decision it rests on |
|---|---|---|---|
| B1, fallback policy | Closed: policy kept, bounds and static ratings unchanged | Low-side G4 fallbacks 15 of 336 (AUSTIN, 0.0446), 68 (MIDLAND, 0.2024), 0 and 0; no hour above the upper bound in any city (`val01_fallback_direction_by_city.csv`, `val01_ratings_by_city.csv`). Hours where a fallback published more than the computed rating: 117 of 1344 city-steps (8.7%), down from 331 (24.6%) in Phase 3, almost all of the drop being AUSTIN (229 to 15) from the conductor change | D-12: a low-side fallback to the static rating is safe; only above-band ratings are unsafe |
| B1, conductor basis | Closed for the GO with a stated basis; open for CORPUS_CHRISTI, MIDLAND, EL_PASO and AUSTIN's elevation and bearing | AUSTIN Drake 795 ACSR at 100 C (Austin Energy teammate, relayed 2026-10-27; signed v4 O4); the other three cities Drake 75 C, 900 m, carried-over bearings; version `v3-powersystems-2026-11-02` (`v4_selection/power_systems_gate.md`); no Power Systems answer arrived after the gate | D-13: a GO is allowed on the Drake assumption, each row labelled with its conductor basis |
| B2, ml wind feature | Closed | Four models retrained on the projected wind (2023 to 2025 data, config `v3-powersystems-2026-11-02`), commit `e0a00a9`, manifest regenerated, `dlr_live_check_models.py` prints OK for all 8 artifacts, not pushed (`real_data_validation_p7/b2_retrain.md`). ml bias now +0.1 to -21.1 A (`val02_forecast_by_city.csv`) | D-14 |
| B4, CORPUS_CHRISTI detector | Closed by acceptance, with a logged follow-up | Re-measured trip rate 0.1101 (37 of 336, interval 0.0595 to 0.1637), all model-branch votes, identical under the ml and naive replays; AUSTIN 0 of 321, MIDLAND 2 of 268, EL_PASO 1 of 336 (`val02_detector_by_city.csv`). A trip publishes the safe static rating | D-16. Follow-up: refit the CORPUS_CHRISTI anomaly detector on station-measured inputs once Power Systems answers, or by 2026-11-30T00:00:00Z if they never do, then re-check with a replay of the September window. A conductor change alters only the detector's validation arm (the fit of the anomaly model uses weather, not the conductor) and does not by itself force an anomaly refit |
| B5, band check after a gap | Closed | Share of G6-evaluated hours with a band: AUSTIN 0.9875, CORPUS_CHRISTI 0.9405, MIDLAND 0.9366, EL_PASO 1.0. ml band gated 261, 233, 169, 330 hours; naive band gated 56, 83, 82, 6; no band 4, 20, 17, 0 (`val02_g6_band_by_city.csv`). Naive fallback counts equal `n_band_naive`. Fallback rows stay out of history (Phase 2 rule unchanged) | D-17 |
| Re-run complete, fidelity 0 | Met | Window 2026-09-08 to 2026-09-28, 168 warm-up and 336 scored steps per city (`val02_forecast_by_city.csv`). Mismatches 0 in `fidelity_ml_p7.json` (1683 compared, 333 AUSTIN excluded by construction), `fidelity_naive_p7.json` (same), `fidelity_ml_control_p7.json` (control at `2c48f9e`, 2016 compared, 0 excluded) and `replay_fidelity.json` (2016 compared); `real_data_validation_p7/README.md` | D-18 |
| Numeric pass bar | None | D-18 sets none | D-18 |

Model fingerprints (SHA-256, first 12 characters; full values in `real_data_validation_p7/b2_retrain.md`): AUSTIN `dd6d540d0ccd` to `60b7e1349ccf`, CORPUS_CHRISTI `d4527fefb591` to `43d9115f2b96`, MIDLAND `0a62d94ed440` to `875fdbb394ad`, EL_PASO `3cd066e0c3fd` to `3dc69b7e0f95`. The four anomaly model fingerprints are unchanged.

Other measurements, for context (all `real_data_validation_p7/val02_forecast_by_city.csv`): coverage of the 90% band (ml / naive) 0.8692 / 0.8629 (AUSTIN), 0.8839 / 0.9018 (CORPUS_CHRISTI), 0.8022 / 0.8097 (MIDLAND), 0.875 / 0.881 (EL_PASO). MIDLAND's ml band is the weakest, with an interval (0.746 to 0.855) that excludes 0.90. These are accuracy items, not safety items.

## ml versus naive on the September window (D-15)

Source: `real_data_validation_p7/val02_forecast_by_city.csv`, rows `ml_p7` and `naive_p7`, scored period (336 steps per city; the figures use the hours that reached G6 and had a computed rating, `n_band`). Error is mean absolute difference between the computed rating and the forecast centre, in amps; bias is computed minus forecast centre.

| City | ml MAE | naive MAE | ml bias | naive bias | ml band width (mean) | naive band width (mean) | Reading |
|---|---|---|---|---|---|---|---|
| AUSTIN | 84.6 | 87.6 | -21.1 | 0.8 | 315.4 | 326.9 | ml lower by 3.0 A; ml's centre sits about 21 A above the computed rating on average (the naive centre is about on it) |
| CORPUS_CHRISTI | 61.3 | 62.9 | 0.1 | 2.5 | 291.9 | 324.8 | ml lower by 1.6 A; bias gone (was +41.9) |
| MIDLAND | 80.2 | 80.3 | 1.1 | -0.5 | 260.4 | 273.9 | a tie (0.1 A) |
| EL_PASO | 112.6 | 117.3 | -11.5 | 0.0 | 469.1 | 507.2 | ml lower by 4.7 A |

ml is not worse than naive in any city, so D-15's condition for an owner decision is not met on this evidence, but the margin is small and the owner states the choice at the checkpoint. Phase 3 had ml worse in every city (104.1 / 86.4 / 94.2 / 126.7 A against naive 62.3 / 62.9 / 80.3 / 117.3 A; `real_data_validation.md`, Finding 3); the B2 retrain reversed that.

Exploratory supporting context (not pre-registered, not part of the checklist, not FRESH; `docs/data-science/exploratory/2026-11-02_ml_vs_naive/REPORT.md`): over 2026-01-01 to 2026-09-29 (6528 hours per city, reanalysis weather) ml beats naive by +3.9 A pooled (95% interval 3.1 to 4.7), significant in all four cities (Holm 0.0008), concentrated in May to September and absent in January and February. On the two-week September replay it is not significant (+1.9 A pooled, p 0.47), and on recorded station observations the edge was smaller than on reanalysis. Part of AUSTIN's 3.0 A gain here comes from hours where ml was withheld from G6 (post-hoc check in that report); on hours where ml fed G6 AUSTIN's gain is 0.0 A.

## Selection status (SEL-04)

Read 1 of signed protocol v4 ran once, on 2026-11-02T17:51:56Z. Its outcome is no pick: no shadow model replaces ml. The owner accepted that outcome on 2026-11-02 (`rule-outcome-ml`), kept ml retrained on projected wind (B2, models `e0a00a9`) as the interim G6 method, subject to D-15 at this checkpoint, and, as a labelled engineering choice and not a rule pick, selected `ml_cooling_corrected` as a day-ahead (24 h) forecast to be served in a new Phase 8 (`v4_selection/decision_record.md`, plan 07-13). Read 2 is still pending: it runs at or after 2026-11-08T00:00:00Z (plan 07-15), under the same rules, and is reported either way. This note read no outcome of read 2. A picked shadow model is not wired into live ratings in this phase, so nothing about the live G6 method depends on read 2.

## Late Power Systems answers (D-03)

None arrived after the gate. The one answer that exists (AUSTIN, Drake at 100 C) was applied before read 1 was run (`v4_selection/power_systems_gate.md`). Answers for the other three cities, if they come, fall under D-03: the ABLATION check showed the ranking is invariant across the bracketing conductor set (`ranking_invariant` true in `v4_selection/vetoes.json`), so a decision made on read 1 would stand, with cooling and reference refit for serving and no FRESH re-read. They would also bring a config-version bump, a repeat of the B2 retrain under the new values (D-14) and the B4 detector refit (D-16). No handling options are needed now.

## Label lift (REVAL-01)

**What a GO changes.** Every stored row carries a `rating_basis` text and a `config_version`. The consumer view `latest_rating.is_provisional` is true while the word "provisional" (any case) appears in either of them (`supabase/migrations/20261026195124_expose_latest_rating.sql`, `backend/latest_rating_contract.py`). The version `v3-powersystems-2026-11-02` no longer contains the word, but the current `RATING_BASIS` text still does, so the flag stays true until the text changes. A GO therefore changes `config.RATING_BASIS` and the schema doc's "Provisional label (OD-5)" section together (a test pins them to each other), and the new text must not contain the word, even in a phrase such as "no longer provisional", which would still read as provisional. Phase 6's `latest_rating` column comments say the values are provisional "per rating_basis" and can stay.

**Proposed new `RATING_BASIS` text** (the owner may edit it; it keeps the conductor basis on every row, D-13, and does not use the word that drives the flag):

> Per-conductor amperes from the IEEE 738 thermal model at one rating point per city, using the per-city conductor table identified by the row's config_version and config_fingerprint. AUSTIN's conductor type and maximum operating temperature come from an Austin Energy statement; every other conductor value, for every city, is a model default awaiting Power Systems confirmation. Static ratings are owner-supplied 345 kV bundle averages divided by an assumed subconductor count; line bearings are assumed, not measured. Not a verified equipment-limited circuit rating. The Phase 3 findings were re-validated in Phase 7 (REVAL-01) on this conductor basis.

**Options for stored rows (owner chooses).**

1. **Going forward only (recommended by the plan).** Rows written after the promotion push carry the new text; every earlier live row keeps the old text and so keeps reading as provisional. Rationale: rows before promotion were computed with the un-fixed ml model and without B5, so the old label describes them accurately. Backfill rows keep their Phase 3 label.
2. **Also relabel stored live rows from a date the owner names.** An owner-run `UPDATE` in plan 07-18, restricted to `origin = 'live'` rows from that date whose `rating_basis` still holds the old text, run with the writer credential by the owner, never by the executor. Consumers then see one label across the named range, but the date must be late enough that the rows were produced after the B2 and B5 behaviour; an early date relabels rows the fixes did not touch.
3. **NO-GO.** The label stays on every row and the items still blocking are recorded in STATE.md.

Backfill rows are never relabelled under any option. Under options 1 and 2 the schema doc's "Rules for consumers" lines that say every row stays provisional until the go, and the lines that say a row must never be described as having passed a go/no-go (`city_rating_v1.md`, `docs/integration/rest-api.md`), need rewording for rows that carry the new text; the proposed text above is written to avoid that phrase.

**D-15, interim G6 method.** Keep ml (retrained, `e0a00a9`) or switch the live forecast method to naive. Keeping ml changes nothing in code here. Switching sets `dlr_live_run.FORECAST_METHOD` to `"naive"` with its test updated; the retrained models would then not be used by live runs (a naive forecast has no model file, so `forecast_model_sha256` would be empty) and B5 would be moot (naive would be the primary band). Nothing is pushed in this plan either way.

## Not blocking

B3 (history gap between the backfill window and go-live) and B6 (Open-Meteo solar accepted and labelled per row) were recorded as not blocking in the Phase 3 decision and are unchanged here. The G6 method that gated each hour is in the trace and the validation report only (`g6_forecast_method`); a consumer-visible column for it would be an additive migration later. `forecast_used_by_g6` keeps describing the stored forecast: when ml is held back by the lookback rule and a naive band checks G6, it reads false and the trace says which band was used.

## Decision

**Decision: GO.** The owner signed GO on lifting the provisional label, in the mode `go-forward-only`: the new label applies to rows written after the promotion push in plan 07-18. No stored live row is relabelled and no backfill row is ever relabelled. The proposed `RATING_BASIS` text above was accepted without edits.

- **Label mode:** `go-forward-only` (no date named, no stored-row `UPDATE`).
- **D-15, interim G6 method:** `ml` (retrained, `e0a00a9`). No change to `dlr_live_run.FORECAST_METHOD`.
- **B4 follow-up date:** `2026-11-30T00:00:00Z` accepted (refit the CORPUS_CHRISTI anomaly detector on station-measured inputs once Power Systems answers, or by that date if they never do, then re-check with a replay of the September window).
- **Closed blockers:** B1, B2, B4 and B5 are closed as set out in the checklist; B3 and B6 remain not blocking.
- **What changed in code and docs on this GO:** `config.RATING_BASIS` and the schema doc's "Provisional label (OD-5)" section carry the new text together; `RATING_CONFIG_VERSION` is unchanged (`v3-powersystems-2026-11-02`, which does not contain the word), so `latest_rating.is_provisional` is false for a row that carries both. The schema doc's "Rules for consumers" and `docs/integration/rest-api.md` "Provisional values" were reworded so they stay correct for older rows (which still read provisional) and for rows carrying the new label. Nothing is pushed or applied to the live database in plan 07-17.

The owner's reply, recorded verbatim (2026-11-02T20:43Z), second line included:

> go-forward-only, D-15: ml; 2026-11-30 ok; aaphan
> power systems answers were primarily to clear assumptions causing austin to fallback to static over half the time, other results are accepted as stated

**Signed by:** aaphan, 2026-11-02 (UTC)

**Recorded by:** the executor, from the owner's reply at plan 07-17's checkpoint
