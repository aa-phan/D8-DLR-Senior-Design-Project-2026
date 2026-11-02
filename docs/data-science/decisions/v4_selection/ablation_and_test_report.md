# ABLATION and TEST results against the signed v4 criteria (SEL-03)

Run 2026-11-02 (UTC), plan 07-11 Task 1, under the signed protocol `confirmation_protocol_v4_early_selection_SIGNING_COPY.md` (signed 2026-11-02 by `aaphan`).

## In plain English

Two older-data checks were run before the one-shot read, and neither one removes any of the three candidate methods. The first check (ABLATION) asks whether a method's standing changes when the assumed power line changes; I refit the cooling and reference methods under six different conductors on the early rows (before 2026-03-17) and scored them on the validation rows, and in every case the order of the five methods stayed the same as under the Drake 75 degrees C control, so no method is ruled out and the ranking is invariant to the conductor. The second check (TEST) scored the 12 frozen models on 2026-03-18 up to 2026-09-29, rows they never saw, and a method is ruled out only if it has a higher average error than the plain forecast in at least 3 of the 4 cities: `ml_wind_corrected` and `ml_cooling_corrected` beat the plain forecast in all 4 cities, and `reference_ml_refit_24h` beat it in 3 and lost in 1 (MIDLAND), so it stays in. Being "not ruled out" is a weak statement: on the ABLATION validation rows `reference_ml_refit_24h` is on average about 15 A worse than the plain forecast under every conductor, which is a steady result rather than a conductor-sensitive one, so the signed ABLATION rule does not catch it, and the FRESH read is where it will be judged. The AUSTIN-only variant with Austin's measured 163 m elevation also left every order unchanged. Neither check can name a winner or confirm a method (D-02); both were run on data the methods were chosen or already scored on, and the TEST window was already read once in the corridor-era work. No row on or after 2026-09-30 was opened, computed or read.

## Evidence and how it was produced

| Item | Value |
|---|---|
| Signing check | `forecast_shadow_eval_core.v4_signed()` was `True` |
| Cached frames | the four `anchored_pair_frame_{CITY}_2024-01-20_2026-09-29_lead24_previous_runs.csv` files; sha256 checked against the values in `forecast_shadow_eval_validation_test.py` (all four matched) before the runs |
| FRESH-dated cache files | not opened (both CLIs refuse those paths; the TEST provider also asserts no row on or after 2026-09-30T00:00Z) |
| ABLATION command | `PYTHONPATH=backend .venv/bin/python backend/forecast_conductor_ablation.py --out-dir data/shadow/evaluation/v4-ablation/20261102T085103Z` (n_resamples at the pre-registered 10000) |
| ABLATION row counts | train 2360 and validation 784 for every city (asserted by the CLI; none relaxed) |
| TEST command | `PYTHONPATH=backend .venv/bin/python backend/forecast_test_split_score.py --conductor-basis frozen-drake` |
| TEST window | 2026-03-18T00:00:00Z to before 2026-09-30T00:00:00Z, 784 slots per city (asserted) |
| ABLATION report | `data/shadow/evaluation/v4-ablation/20261102T085103Z/ablation.json`, sha256 `60963aa83030a9e7a11c99db61589ad3426edcfc931e847f48a76c3a3f0e745d` |
| TEST report | `data/shadow/evaluation/v4-test/report_20261102T085108Z/test_split.json`, sha256 `b003a2c0431956f397c302d20d58aac0941973bf745703e0d3ad27b85431c045` |
| Frozen artifacts | `shasum -a 256 -c data/shadow/models/ARTIFACT_HASHES.sha256` reports OK for all 12; nothing under `data/shadow/models` was written |

The directory stamp `20261102T085103Z` is the time the ABLATION report was written (UTC). Truth is reanalysis-derived (Open-Meteo Archive through IEEE 738), never sensor-validated.

## ABLATION (conductor invariance, veto only)

Signed veto (clauses a to c): a candidate is vetoed if under any variant (a) the sign of its pooled margin over `raw_forecast` differs from the control's, (b) (cooling and reference only) the sign of its pooled margin over `ml_wind_corrected` differs, or (c) whether it is favoured over `ml_wind_corrected` in at least 3 cities differs. "Ranking invariant" means no veto and Kendall tau 1.0 for every variant.

Order of the five methods, best first, is identical to the control for five of the six variants (tau 1.0 for all six, including the control against itself):
`ml_cooling_corrected > ml_wind_corrected > raw_forecast > reference_ml_refit_24h > persistence_24h`. The AUSTIN-only variant has its own order, `ml_cooling_corrected > raw_forecast > ml_wind_corrected > reference_ml_refit_24h > persistence_24h`, which is also the order of the control restricted to AUSTIN (the matched control), so tau is 1.0 against that comparison.

Pooled margins over `raw_forecast` in amps (positive means the candidate has the lower error). Sign changes against the control are counted in the last column; there were none.

| Variant | Cities | ml_wind_corrected | ml_cooling_corrected | reference_ml_refit_24h | Sign changes vs control (clauses a, b, c) |
|---|---|---|---|---|---|
| Drake-75 (control) | 4 | +17.14 | +23.58 | -15.18 | not applicable |
| Drake-100 | 4 | +20.14 | +26.85 | -16.17 | none |
| Falcon-90 | 4 | +29.24 | +39.62 | -23.86 | none |
| Suwannee-150 | 4 | +26.62 | +34.17 | -20.00 | none |
| Suwannee-200 | 4 | +29.43 | +37.40 | -21.90 | none |
| Drake-75-AUSTIN-163m (AUSTIN only; matched control in brackets) | 1 | -3.23 (-2.79) | +20.30 (+20.49) | -4.04 (-4.43) | none |

Pooled margins over `ml_wind_corrected` (cooling and reference) and the number of cities favoured over wind, which clause (c) compares with the control (it flips only if the count crosses 3 of 4):

| Variant | ml_cooling_corrected over wind (A, cities favoured) | reference_ml_refit_24h over wind (A, cities favoured) |
|---|---|---|
| Drake-75 (control) | +6.43, 2 of 4 | -32.33, 0 of 4 |
| Drake-100 | +6.71, 2 of 4 | -36.31, 1 of 4 |
| Falcon-90 | +10.39, 2 of 4 | -53.10, 1 of 4 |
| Suwannee-150 | +7.55, 2 of 4 | -46.61, 1 of 4 |
| Suwannee-200 | +7.97, 2 of 4 | -51.34, 1 of 4 |
| Drake-75-AUSTIN-163m (matched control in brackets) | +23.53, 1 of 1 (+23.28, 1 of 1) | -0.80, 0 of 1 (-1.63, 0 of 1) |

Reading of the table: the sizes of the margins move with the conductor (a hotter limit raises every ampacity and so every error in amps), but no sign and no 3-of-4 status flips. `ml_wind_corrected` is slightly worse than the plain forecast for AUSTIN alone under both the control and the 163 m variant, which is the same finding the corridor-era work recorded at Austin; it is the same sign in both, so it is not a conductor effect and does not veto.

Suwannee caveat (signed in the options record): the Suwannee-150 and Suwannee-200 rows use the catalogue ACSS/TW resistance (0.0597 ohm/km at 25 C) in the repo's linear resistance model, whose accuracy at 150 to 200 C is unverified. Those two rows are bracketing values, not claims about any real line.

**ABLATION outcome:** no candidate is vetoed. `ranking_invariant = true`.

## TEST (frozen artifacts, out of sample, veto only)

Signed veto: a candidate is vetoed if its per-city MAE is strictly higher than `raw_forecast`'s, on complete-case pairs, in at least 3 of the cities with data (a tie is not a loss). Basis: the 12 frozen artifacts under the frozen Drake point for every city (`conductor_basis` `frozen-drake`). 784 slots per city.

Mean absolute error in amps:

| Candidate | AUSTIN | CORPUS_CHRISTI | MIDLAND | EL_PASO | Cities worse than raw |
|---|---|---|---|---|---|
| raw_forecast (baseline) | 114.46 | 110.76 | 129.09 | 168.63 | not applicable |
| ml_wind_corrected | 109.24 | 88.06 | 122.96 | 130.84 | 0 |
| ml_cooling_corrected | 91.29 | 85.78 | 119.92 | 126.33 | 0 |
| reference_ml_refit_24h | 101.73 | 101.34 | 178.20 | 141.42 | 1 (MIDLAND) |

**TEST outcome:** no candidate is vetoed. The cities losing to `raw_forecast` are none for `ml_wind_corrected`, none for `ml_cooling_corrected`, and MIDLAND alone for `reference_ml_refit_24h` (one city is below the 3-city line).

## What this means for D-03 and for the read

- `ranking_invariant = true`. Under the signed late-answer rule (D-03), values that arrive after the read leave the decision standing: cooling and reference are then refit under the real values for serving, with no FRESH re-read. This record does not make that rule apply to AUSTIN, whose switch to Drake at 100 degrees C is decided at the Power Systems gate (07-11 Task 2) and, if applied, lands before read 1.
- Because the ABLATION rule is a veto on conductor sensitivity only, it passes a candidate that is consistently poor. `reference_ml_refit_24h` is worse than the plain forecast on the ABLATION validation rows under every conductor, and loses to it at MIDLAND on TEST. Neither the ABLATION nor the TEST rule removes it; the Selection rule on the FRESH rows decides whether it can qualify.
- The two analyses give the read an empty veto list. The read still needs a FRESH result that clears the 2 percent bar in the pooled comparison and is favoured in at least 3 of 4 cities.

## Neither analysis can pick a winner (D-02)

ABLATION rows are the rows the configurations were selected on, so its selection optimism is unchanged. The TEST window was already read once in the corridor-era result, so it is partly already seen. Both can only disqualify a candidate. Neither names a winner or confirms a method, and no figure in this report is a FRESH outcome.

## Limits and notes

- The validation-split mean truth ampacities under Drake-75 in `ablation.json` (AUSTIN 1254.4 A, CORPUS_CHRISTI 1360.6 A, MIDLAND 1538.0 A, EL_PASO 1199.1 A) are the validation-rows means. They differ from the worked example in the signing copy (1257.8, 1375.8, 1525.4, 1236.8 A); no veto depends on them.
- Both reports are committed as evidence, and `vetoes.json` records their sha256 values; `forecast_shadow_confirm.load_vetoes` accepts it.
- If the owner applies Power Systems values at the 07-11 gate, TEST is re-scored under the production conductors before read 1 is run (registry `test.rescore_gate = before_read1_run`), and `vetoes.json`'s test section is updated; the frozen-drake TEST report stays as a referenced record.
