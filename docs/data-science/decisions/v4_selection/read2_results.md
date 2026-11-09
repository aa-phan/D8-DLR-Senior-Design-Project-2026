# Read 2 results (signed protocol v4, round `v4-read2`)

Written 2026-11-08 (UTC) by plan 07-16. Every figure below is copied from the two committed read-2 `report.json` files (and their `report.md`), except the read-1 figures in the comparison table, which are copied from `read1_results.md`. Nothing was recomputed, re-run or re-scored. Truth throughout is reanalysis-derived (Open-Meteo Archive through IEEE 738), never sensor-validated.

## In plain English

**What was compared.** The same three shadow methods as read 1 (`ml_wind_corrected`, `ml_cooling_corrected`, `reference_ml_refit_24h`) were each compared with the plain weather forecast (`raw_forecast`), this time on 128 six-hourly slots per city (valid times 2026-09-30 up to, not including, 2026-11-01), in all four cities, 512 paired slots in total. Read 2 ran once per row source at 2026-11-08T01:21:06Z (headline) and 2026-11-08T01:21:22Z (live-system check), with no failed city, no missing slot, no dropped row and no override.

**Read 2 is not independent of read 1.** Read 2 re-grades read 1's rows. Its 128 slots per city include 100 that read 1 already scored (the 2026-09-30 to 2026-10-25 slots), and only the remaining 28 per city (up to 2026-11-01) are new. Agreement between the two reads is therefore expected and is not a second confirmation; read 2 is a longer look at mostly the same period, not an independent test.

**The bar.** To qualify, a method had to beat the plain forecast by at least 2% of the city's average ampacity, pooled across cities: AUSTIN 28.84 A, CORPUS_CHRISTI 27.85 A, MIDLAND 31.12 A, EL_PASO 24.22 A, pooled 28.01 A. It also had to be better in at least 3 of the 4 cities, show real statistical evidence, and not be ruled out by the two older-data checks (ABLATION and TEST).

**What happened.**

| Method | Average improvement over plain forecast (pooled) | Bar | Better in how many cities | Ruled out by ABLATION or TEST | Evidence level |
|---|---|---|---|---|---|
| `ml_cooling_corrected` | 12.12 A | 28.01 A | 3 of 4 | no | not shown (Holm-adjusted p 0.2930) |
| `ml_wind_corrected` | 3.97 A | 28.01 A | 3 of 4 | no | not shown (Holm-adjusted p 0.7643) |
| `reference_ml_refit_24h` | -24.19 A (worse than plain forecast) | 28.01 A | 1 of 4 | no | not shown (Holm-adjusted p 0.7643) |

As in read 1, the two `ml` variants beat the plain forecast in 3 of 4 cities, so the "at least 3 cities" test passes, but their improvement (12.12 A and 3.97 A) is well under half the 28.01 A bar and the statistical evidence is weak, so each is rated "not shown". `reference_ml_refit_24h` was worse than the plain forecast overall and better in only 1 city. Nothing was vetoed.

**The rule's outcome: no pick, and the signed O3 outcome applies.** The report states: "No candidate qualifies under signed protocol v4: no shadow model replaces ml (D-07). Read 2 (v4-read2) also names no winner: there is no day-ahead pick and the interim G6 method keeps running; 2026-11-24 stays retired and any later evaluation needs a new signed protocol (owner item O3)." The reported pick is none. Under owner item O3 (signed 2026-11-02, option A) that means: no day-ahead pick under the rule, the interim G6 method keeps running, 2026-11-24 stays retired, and any later evaluation needs a new signed protocol. No further FRESH read happens without one.

**What "no day-ahead pick" does and does not say.** It means no method won the pre-registered rule. It does not say anything about the owner's separate, labelled engineering selection of `ml_cooling_corrected` for the day-ahead output (recorded in `decision_record.md`, Read 1 section). That selection was never a rule pick. The record said a rule pick at read 2 would supersede it; read 2 did not pick, so the label has not been superseded by the rule, and whether it stands is for the owner to confirm in the decision recorded in `decision_record.md`.

**Read 1 against read 2 (headline, pooled; overlapping, so not two independent results).**

| Figure | Read 1 | Read 2 |
|---|---|---|
| Slots per city / pooled paired | 100 / 400 | 128 / 512 |
| Pooled bar | 27.86 A | 28.01 A |
| `ml_cooling_corrected` benefit over plain forecast | 11.89 A (Holm p 0.3624) | 12.12 A (Holm p 0.2930) |
| `ml_wind_corrected` benefit over plain forecast | 6.35 A (Holm p 0.9569) | 3.97 A (Holm p 0.7643) |
| `reference_ml_refit_24h` benefit over plain forecast | -29.59 A (Holm p 0.9569) | -24.19 A (Holm p 0.7643) |
| Cities favoured (cooling / wind / refit) | 3 / 3 / 1 of 4 | 3 / 3 / 1 of 4 |
| `ml_cooling_corrected` margin over `ml_wind_corrected` | 5.54 A | 8.14 A |
| Outcome | no pick | no pick (O3 applies) |

In both reads `ml_cooling_corrected` is the strongest candidate and stays well under the bar; the two reads tell the same story, which is what overlapping data would give. `ml_cooling_corrected` against `reference_ml_refit_24h` is the one candidate pair that clears Holm in both reads (read 1 adjusted p 0.0042, read 2 adjusted p 0.0028, favouring cooling in all 4 cities), but that pair is not what the rule tests; the rule tests candidates against the plain forecast and the bar.

**How much to trust it.** The sample is still small: 512 paired slots is a nominal count; the effective sample size is much smaller (bootstrap n_eff 218.3 for `ml_wind_corrected` and 152.0 for `ml_cooling_corrected` against the plain forecast), and both precision targets (about 590 rows for the tail rate, about 1,575 rows for a 5 A detectable difference) are not met for any test. The four cities share weather, and the truth is a reanalysis model, not a sensor.

**What happens next.** Nothing is scheduled under the protocol. The owner's decision for this plan is recorded in `decision_record.md`.

## Headline (reconstructed frames)

Source: `data/shadow/evaluation/v4-read2/reconstructed_frames_20261108T012106Z/report.json`. Label: headline decision. Basis FRESH, protocol status signed, rule v4, config `v3-powersystems-2026-11-02`, conductor basis differing city: AUSTIN (Drake ACSR at 100 C; the other three cities on model-default Drake at 75 C).

### Per-city bars (2% of mean truth ampacity over the city's scored rows)

| City | Rows scored (every candidate) | Mean truth (A) | Bar (A) |
|---|---|---|---|
| AUSTIN | 128 | 1441.78 | 28.84 |
| CORPUS_CHRISTI | 128 | 1392.34 | 27.85 |
| MIDLAND | 128 | 1556.07 | 31.12 |
| EL_PASO | 128 | 1211.10 | 24.22 |
| Pooled bar (paired-row weighted) | 512 | | 28.01 |

### Each candidate against `raw_forecast`

| Candidate | Level | Pooled benefit (A) | Pooled bar (A) | Holm-adjusted p | Cities favoured | Consistent (need 3) | Vetoed | Veto source |
|---|---|---|---|---|---|---|---|---|
| `ml_wind_corrected` | not shown | 3.97 | 28.01 | 0.7643 | 3 of 4 | yes | no | ablation+test |
| `ml_cooling_corrected` | not shown | 12.12 | 28.01 | 0.2930 | 3 of 4 | yes | no | ablation+test |
| `reference_ml_refit_24h` | not shown | -24.19 | 28.01 | 0.7643 | 1 of 4 | no | no | ablation+test |

Per-city margin over `raw_forecast` in amps (positive means the candidate has the lower error; descriptive, uncorrected):

| City | `ml_wind_corrected` | `ml_cooling_corrected` | `reference_ml_refit_24h` |
|---|---|---|---|
| AUSTIN | 2.56 | 14.62 | -0.58 |
| CORPUS_CHRISTI | 18.41 | 24.80 | 4.48 |
| MIDLAND | 0.76 | -3.37 | -89.61 |
| EL_PASO | -5.84 | 12.42 | -11.06 |

### Alternatives against the default (`ml_wind_corrected`)

| Alternative | Pooled margin over `ml_wind_corrected` (A) | Pooled bar (A) | Cities favoured | Consistently better |
|---|---|---|---|---|
| `ml_cooling_corrected` | 8.14 | 28.01 | 3 of 4 | False |
| `reference_ml_refit_24h` | -28.16 | 28.01 | 0 of 4 | False |

### Vetoes applied, with source

Both records are consulted ("ablation+test"); no candidate is vetoed (ablation false and test false for all three). Source record: `docs/data-science/decisions/v4_selection/vetoes.json` (unchanged since read 1; sha256 `1d31cf387098b85be46a5cedc83fa8097061ffa5bb9dd612e67e6204e37454dc`, equal to read 1's per the 07-15 preflight).

### Full headline family (9 tests, pooled, city-clustered, Holm at 0.05)

Margin = mean|e_B| minus mean|e_A| in amps, so positive means A has the lower MAE.

| A vs B | n | margin (A) | Cities favouring A | Headline p | Holm-adj. p | Outcome |
|---|---|---|---|---|---|---|
| ml_wind_corrected vs ml_cooling_corrected | 512 | -8.14 | 1 of 4 | 0.2756 | 0.7643 | inconclusive |
| ml_wind_corrected vs reference_ml_refit_24h | 512 | 28.16 | 4 of 4 | 0.0786 | 0.3144 | inconclusive |
| ml_cooling_corrected vs reference_ml_refit_24h | 512 | 36.31 | 4 of 4 | 0.0004 | 0.0028 | favors_A |
| ml_wind_corrected vs raw_forecast | 512 | 3.97 | 3 of 4 | 0.4996 | 0.7643 | inconclusive |
| ml_cooling_corrected vs raw_forecast | 512 | 12.12 | 3 of 4 | 0.0586 | 0.2930 | inconclusive |
| reference_ml_refit_24h vs raw_forecast | 512 | -24.19 | 1 of 4 | 0.2548 | 0.7643 | inconclusive |
| ml_wind_corrected vs persistence_24h | 512 | 54.35 | 4 of 4 | 0.0002 | 0.0018 | favors_A |
| ml_cooling_corrected vs persistence_24h | 512 | 62.50 | 4 of 4 | 0.0002 | 0.0018 | favors_A |
| reference_ml_refit_24h vs persistence_24h | 512 | 26.19 | 4 of 4 | 0.0050 | 0.0300 | favors_A |

`persistence_24h` is a baseline in the family only and cannot be picked. The statistically clear differences over it do not bear on the rule.

### Per-city mean absolute error (A), descriptive

| City | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h |
|---|---|---|---|---|---|
| AUSTIN | 129.81 | 117.76 | 132.38 | 158.91 | 132.95 |
| CORPUS_CHRISTI | 99.92 | 93.54 | 118.34 | 134.62 | 113.86 |
| MIDLAND | 127.21 | 131.34 | 127.97 | 247.65 | 217.57 |
| EL_PASO | 124.20 | 105.93 | 118.36 | 157.37 | 129.42 |

### Sample sizes

Pooled nominal n = 512 (128 per city for every candidate). Effective sample sizes are smaller: bootstrap n_eff 203.6 (wind vs cooling), 57.4 (wind vs reference), 46.7 (cooling vs reference), 218.3 (wind vs raw), 152.0 (cooling vs raw), 51.4 (reference vs raw). Both precision targets (about 590 rows, about 1,575 rows) are "not met" for every test. Calibrated overrating risk and retained capacity were not measured; no 8% ceiling was applied; candidates are ranked on point error only.

## Secondary (frozen Drake artifacts)

AUSTIN's conductor basis differs between the headline (Drake at 100 C) and the frozen artifacts (Drake at 75 C), so the secondary block is computed. Label: "secondary: frozen Drake artifacts, never decides". Source: the `secondary` key of the headline `report.json`. Its own pick is none; its would-be outcome is "no candidate qualifies".

| Candidate | Level | Benefit over `raw_forecast` (A) | Pooled bar (A) | Holm-adjusted p | Cities favoured |
|---|---|---|---|---|---|
| `ml_wind_corrected` | not shown | 3.84 | 26.82 | 0.5089 | 3 of 4 |
| `ml_cooling_corrected` | not shown | 12.06 | 26.82 | 0.2264 | 3 of 4 |
| `reference_ml_refit_24h` | not shown | -27.10 | 26.82 | 0.3798 | 1 of 4 |

Secondary per-city bars: AUSTIN 24.08 A, CORPUS_CHRISTI 27.85 A, MIDLAND 31.12 A, EL_PASO 24.22 A. Alternatives over `ml_wind_corrected`: `ml_cooling_corrected` 8.22 A (bar 26.82 A, 3 of 4 cities, not consistently better); `reference_ml_refit_24h` -30.95 A (0 of 4 cities). The conductor change at AUSTIN does not change the outcome.

## Live-system check (shadow logs, never pooled)

Source: `data/shadow/evaluation/v4-read2/shadow_logs_20261108T012122Z/report.json`. Label: "live-system check, never decides". It is reported on its own and is never pooled with the headline. The live logs are scored as collected (Drake), the veto records are not applied there (`no ABLATION/TEST veto record was applied (development basis)`), and the report marks its thresholds "exploratory: thresholds not pre-registered in a signed protocol".

Reported pick: none (always). Would-be outcome under the v4 rule: "no candidate qualifies."

Per-city bars on the logged rows: AUSTIN 24.33 A, CORPUS_CHRISTI 28.93 A, MIDLAND 32.27 A, EL_PASO 24.44 A.

| Candidate | Level | Benefit over `raw_forecast` (A) | Pooled bar (A) | Holm-adjusted p | Paired n | Cities favoured |
|---|---|---|---|---|---|---|
| `ml_wind_corrected` | not shown | 0.85 | 27.57 | 1.0000 | 280 | 2 of 4 |
| `ml_cooling_corrected` | not shown | -0.01 | 27.55 | 1.0000 | 279 | 2 of 4 |
| `reference_ml_refit_24h` | not shown | -36.72 | 27.56 | 0.2226 | 265 | 0 of 4 |

Alternatives over `ml_wind_corrected` in the live logs: `ml_cooling_corrected` -0.90 A (bar 27.55 A, favoured in 2 of 4 cities); `reference_ml_refit_24h` -39.52 A (bar 27.56 A, favoured in 1 of 4). No test in the live-log family has a Holm-adjusted p below 0.05 except `ml_cooling_corrected` vs `persistence_24h` (Holm-adjusted p 0.0018, 143 pairs), a baseline comparison that does not bear on the rule. Paired n per comparison ranges from 130 to 280. Both precision targets are not met for any test. In this check the two `ml` variants are about level with the plain forecast (0.85 A and -0.01 A), so the live-system check does not support a candidate either; it decides nothing.

## Data gaps

- Headline: no failed city (`failed_cities` is empty), no missing slot, 0 rows dropped for null weather, 0 candidate failures; every candidate scored 128 of 128 expected slots per city. Leakage probe passed for all four cities. Archive-vs-frame truth difference 0.0.
- Live-system check: per city, 72 rows in scope after exclusions (`missing_forecast_model` 5, `at_or_after_cutoff` 31, `duplicate_valid_time` 10 per city); `persistence_24h` is available for only 37 rows per city (candidate_unavailable 35); `reference_ml_refit_24h` is unavailable for 3 to 8 rows per city plus 1 row per city whose own target hour is at or after the cutoff; `ml_wind_corrected` and `ml_cooling_corrected` are unavailable for 1 to 5 rows in AUSTIN, CORPUS_CHRISTI and EL_PASO (5 in AUSTIN, 1 in CORPUS_CHRISTI, 2 in EL_PASO); `ml_cooling_corrected` failed for 1 MIDLAND row; `raw_forecast` is unavailable for 1 EL_PASO row.
- Report header shows `Git SHA f9be67aa1dee290bcb161a4abe0cb2e99286848f (dirty: True)`; the 07-15 summary records that the read-scope clean-tree check printed nothing (the dirty files were unrelated).
- Read 2 is spent. It is not re-run, re-scoped or re-parameterised, and no further FRESH read happens without a new signed protocol.

## Provenance

| Item | Path | sha256 |
|---|---|---|
| Headline report.json | `data/shadow/evaluation/v4-read2/reconstructed_frames_20261108T012106Z/report.json` | `9a22caf85d85a9510baa0db9be23cd8558e8dacb73aadbb97e97e255a083b9cb` |
| Headline report.md | `data/shadow/evaluation/v4-read2/reconstructed_frames_20261108T012106Z/report.md` | `b1f8be350e92dac97328b59c711d8ce8ca973af806b7cc46ebeaf5b8acd1101c` |
| Live-system report.json | `data/shadow/evaluation/v4-read2/shadow_logs_20261108T012122Z/report.json` | `1ad79ee06f9f8fb6a098e526a0695abf774c5ef6c10b47404c34549087efaf94` |
| Live-system report.md | `data/shadow/evaluation/v4-read2/shadow_logs_20261108T012122Z/report.md` | `3f40b84d55b879d0c1cb8d54a801b8a023f5471293f4cafd1448668e344a29a4` |
| vetoes.json | `docs/data-science/decisions/v4_selection/vetoes.json` | `1d31cf387098b85be46a5cedc83fa8097061ffa5bb9dd612e67e6204e37454dc` |

- `rating_config_version`: `v3-powersystems-2026-11-02` (equal to read 1's).
- Scored artifacts: same as read 1 (12 frozen artifacts, with AUSTIN `ml_cooling_corrected` and `reference_ml_refit_24h` from the refit directory); all verified against their manifests (`refit_verified: true`, no problems).
- Evidence round: `v4-read2`; evaluation instant 2026-11-08T00:00:00Z; valid-time cutoff 2026-11-01T00:00:00Z (strict); run at 2026-11-08T01:21:06Z (headline) and 2026-11-08T01:21:22Z (live-system); live logs exported from `origin/shadow-collection-data` at `e7863106bc7f305534031c818092887ddd207eeb`.
- Protocol: `docs/data-science/decisions/confirmation_protocol_v4_early_selection_SIGNING_COPY.md`, signed 2026-11-02 by `aaphan`.
