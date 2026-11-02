# Read 1 results (signed protocol v4, round `v4-read1`)

Written 2026-11-02 (UTC) by plan 07-13. Every figure below is copied from the two committed `report.json` files (and their `report.md`); nothing was recomputed, re-run or re-scored. Truth throughout is reanalysis-derived (Open-Meteo Archive through IEEE 738), never sensor-validated.

## In plain English

**What was compared.** Three shadow methods (`ml_wind_corrected`, `ml_cooling_corrected`, `reference_ml_refit_24h`) were each compared with the plain weather forecast (`raw_forecast`) on 100 six-hourly slots per city (valid times 2026-09-30 up to, not including, 2026-10-25), in all four cities, 400 paired slots in total. Read 1 ran once, at 2026-11-02T17:51:56Z, with no failed city, no missing slot and no override.

**The bar.** To qualify, a method had to beat the plain forecast by at least 2% of the city's average ampacity, pooled across cities: AUSTIN 28.48 A, CORPUS_CHRISTI 27.40 A, MIDLAND 30.87 A, EL_PASO 24.69 A, pooled 27.86 A. It also had to be better in at least 3 of the 4 cities, show real statistical evidence, and not be ruled out by the two older-data checks (ABLATION and TEST).

**What happened.**

| Method | Average improvement over plain forecast (pooled) | Bar | Better in how many cities | Ruled out by ABLATION or TEST | Evidence level |
|---|---|---|---|---|---|
| `ml_cooling_corrected` | 11.89 A | 27.86 A | 3 of 4 | no | not shown (Holm-adjusted p 0.3624) |
| `ml_wind_corrected` | 6.35 A | 27.86 A | 3 of 4 | no | not shown (Holm-adjusted p 0.9569) |
| `reference_ml_refit_24h` | -29.59 A (worse than plain forecast) | 27.86 A | 1 of 4 | no | not shown (Holm-adjusted p 0.9569) |

The two `ml` variants beat the plain forecast in 3 of 4 cities, so the "at least 3 cities" test passes, but their improvement (11.89 A and 6.35 A) is well under half the 27.86 A bar and the statistical evidence is weak, so each is rated "not shown". `reference_ml_refit_24h` was worse than the plain forecast overall and better in only 1 city. Nothing was vetoed.

**The rule's outcome: no pick.** The report states: "No candidate qualifies under signed protocol v4: no shadow model replaces ml (D-07). Read 1 names no winner, so the pre-registered re-test v4-read2 runs at or after 2026-11-08T00:00:00Z under the same rules." The protocol itself said "no pick" was a realistic result because a 2% bar is large next to the gaps seen earlier.

**What this does and does not say.** Read 1 compares shadow methods against the plain forecast. It does not compare the live `ml` forecast against a naive method; that is the D-15 comparison, read from the September re-run (plan 07-17). A picked shadow model would not have been wired into the live ratings in this phase either; that is a later phase.

**How much to trust it.** The sample is small: 400 paired slots is a nominal count, the effective sample size is much smaller (bootstrap n_eff 133.2 for `ml_wind_corrected` and 118.4 for `ml_cooling_corrected` against the plain forecast), and both precision targets (about 590 rows for the tail rate, about 1,575 rows for a 5 A detectable difference) are not met for any test. The four cities share weather, and the truth is a reanalysis model, not a sensor.

**What happens next.** The pre-registered read 2 runs at or after 2026-11-08T00:00:00Z under the same rules. It scores 128 slots per city (valid times 2026-09-30 up to, not including, 2026-11-01), so 100 of its 128 slots per city were already seen in read 1. Under owner item O3 (signed 2026-11-02, option A), if read 2 also names no winner there is no day-ahead pick and the interim G6 method keeps running. The owner's decision for this plan is recorded in `decision_record.md`.

## Headline (reconstructed frames)

Source: `data/shadow/evaluation/v4-read1/reconstructed_frames_20261102T175156Z/report.json`. Label: headline decision. Basis FRESH, protocol status signed, rule v4, config `v3-powersystems-2026-11-02`, conductor basis differing city: AUSTIN (Drake ACSR at 100 C; the other three cities on model-default Drake at 75 C).

### Per-city bars (2% of mean truth ampacity over the city's scored rows)

| City | Rows scored (every candidate) | Mean truth (A) | Bar (A) |
|---|---|---|---|
| AUSTIN | 100 | 1423.87 | 28.48 |
| CORPUS_CHRISTI | 100 | 1369.78 | 27.40 |
| MIDLAND | 100 | 1543.27 | 30.87 |
| EL_PASO | 100 | 1234.37 | 24.69 |
| Pooled bar (paired-row weighted) | 400 | | 27.86 |

### Each candidate against `raw_forecast`

| Candidate | Level | Pooled benefit (A) | Pooled bar (A) | Holm-adjusted p | Cities favoured | Consistent (need 3) | Vetoed | Veto source |
|---|---|---|---|---|---|---|---|---|
| `ml_wind_corrected` | not shown | 6.35 | 27.86 | 0.9569 | 3 of 4 | yes | no | ablation+test |
| `ml_cooling_corrected` | not shown | 11.89 | 27.86 | 0.3624 | 3 of 4 | yes | no | ablation+test |
| `reference_ml_refit_24h` | not shown | -29.59 | 27.86 | 0.9569 | 1 of 4 | no | no | ablation+test |

Per-city margin over `raw_forecast` in amps (positive means the candidate has the lower error; descriptive, uncorrected):

| City | `ml_wind_corrected` | `ml_cooling_corrected` | `reference_ml_refit_24h` |
|---|---|---|---|
| AUSTIN | 11.97 | 14.58 | -0.49 |
| CORPUS_CHRISTI | 22.39 | 25.22 | 12.16 |
| MIDLAND | 1.35 | -6.20 | -114.09 |
| EL_PASO | -10.31 | 13.96 | -15.95 |

### Alternatives against the default (`ml_wind_corrected`)

| Alternative | Pooled margin over `ml_wind_corrected` (A) | Pooled bar (A) | Cities favoured | Consistently better |
|---|---|---|---|---|
| `ml_cooling_corrected` | 5.54 | 27.86 | 3 of 4 | False |
| `reference_ml_refit_24h` | -35.95 | 27.86 | 0 of 4 | False |

### Vetoes applied, with source

Both records are consulted ("ablation+test"); no candidate is vetoed (ablation false and test false for all three). Source record: `docs/data-science/decisions/v4_selection/vetoes.json` (sha256 `1d31cf387098b85be46a5cedc83fa8097061ffa5bb9dd612e67e6204e37454dc`, created 2026-11-02T08:52:14Z, TEST re-scored under the production conductors 2026-11-02T17:35:17Z).

- ABLATION: `data/shadow/evaluation/v4-ablation/20261102T085103Z/ablation.json`, sha256 `60963aa83030a9e7a11c99db61589ad3426edcfc931e847f48a76c3a3f0e745d`; ranking invariant; no variant vetoes any candidate.
- TEST (production conductor basis, the one that applies to the read): `data/shadow/evaluation/v4-test/report_20261102T173449Z/test_split.json`, sha256 `43fa316f4c0f1ad6c1e0b29a9531c81686a10b66639b7dbce11a68518e76db3f`; veto rule: MAE strictly higher than `raw_forecast` in at least 3 cities; `reference_ml_refit_24h` loses to the plain forecast in MIDLAND only (1 city), not vetoed.

### Full headline family (9 tests, pooled, city-clustered, Holm at 0.05)

Margin = mean|e_B| minus mean|e_A| in amps, so positive means A has the lower MAE.

| A vs B | n | margin (A) | Cities favouring A | Headline p | Holm-adj. p | Outcome |
|---|---|---|---|---|---|---|
| ml_wind_corrected vs ml_cooling_corrected | 400 | -5.54 | 1 of 4 | 0.4990 | 0.9569 | inconclusive |
| ml_wind_corrected vs reference_ml_refit_24h | 400 | 35.95 | 4 of 4 | 0.0500 | 0.2500 | inconclusive |
| ml_cooling_corrected vs reference_ml_refit_24h | 400 | 41.48 | 4 of 4 | 0.0006 | 0.0042 | favors_A |
| ml_wind_corrected vs raw_forecast | 400 | 6.35 | 3 of 4 | 0.3922 | 0.9569 | inconclusive |
| ml_cooling_corrected vs raw_forecast | 400 | 11.89 | 3 of 4 | 0.0906 | 0.3624 | inconclusive |
| reference_ml_refit_24h vs raw_forecast | 400 | -29.59 | 1 of 4 | 0.3190 | 0.9569 | inconclusive |
| ml_wind_corrected vs persistence_24h | 400 | 58.23 | 4 of 4 | 0.0002 | 0.0018 | favors_A |
| ml_cooling_corrected vs persistence_24h | 400 | 63.77 | 4 of 4 | 0.0002 | 0.0018 | favors_A |
| reference_ml_refit_24h vs persistence_24h | 400 | 22.28 | 4 of 4 | 0.0062 | 0.0372 | favors_A |

`persistence_24h` is a baseline in the family only and cannot be picked. Several of these statistically clear differences (for example the two `ml` variants over `persistence_24h`) do not bear on the rule, which tests candidates against `raw_forecast` and against the bar.

### Per-city mean absolute error (A), descriptive

| City | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h |
|---|---|---|---|---|---|
| AUSTIN | 113.17 | 110.56 | 125.14 | 143.23 | 125.63 |
| CORPUS_CHRISTI | 92.63 | 89.81 | 115.03 | 120.85 | 102.87 |
| MIDLAND | 118.79 | 126.33 | 120.13 | 270.02 | 234.22 |
| EL_PASO | 121.77 | 97.51 | 111.47 | 145.18 | 127.42 |

### Sample sizes

Pooled nominal n = 400 (100 per city for every candidate). Effective sample sizes are smaller: bootstrap n_eff 126.4 (wind vs cooling), 35.4 (wind vs reference), 29.5 (cooling vs reference), 133.2 (wind vs raw), 118.4 (cooling vs raw), 32.7 (reference vs raw). Both precision targets (about 590 rows, about 1,575 rows) are "not met" for every test. Calibrated overrating risk and retained capacity were not measured; no 8% ceiling was applied; candidates are ranked on point error only.

## Secondary (frozen Drake artifacts)

AUSTIN's conductor basis differs between the headline (Drake at 100 C) and the frozen artifacts (Drake at 75 C), so the secondary block is computed (it is not equal to the headline). Label: "secondary: frozen Drake artifacts, never decides". Source: the `secondary` key of the headline `report.json`. Its own pick is none; its would-be outcome is "no candidate qualifies".

| Candidate | Level | Benefit over `raw_forecast` (A) | Pooled bar (A) | Holm-adjusted p | Cities favoured |
|---|---|---|---|---|---|
| `ml_wind_corrected` | not shown | 5.99 | 26.67 | 0.8135 | 3 of 4 |
| `ml_cooling_corrected` | not shown | 12.13 | 26.67 | 0.3240 | 3 of 4 |
| `reference_ml_refit_24h` | not shown | -33.04 | 26.67 | 0.5741 | 1 of 4 |

Secondary per-city bars: AUSTIN 23.72 A, CORPUS_CHRISTI 27.40 A, MIDLAND 30.87 A, EL_PASO 24.69 A. Alternatives over `ml_wind_corrected`: `ml_cooling_corrected` 6.15 A (bar 26.67 A, 3 of 4 cities, not consistently better); `reference_ml_refit_24h` -39.03 A (0 of 4 cities). The conductor change at AUSTIN does not change the outcome.

## Live-system check (shadow logs, never pooled)

Source: `data/shadow/evaluation/v4-read1/shadow_logs_20261102T175210Z/report.json`. Label: "live-system check, never decides". It is reported on its own and is never pooled with the headline. The live logs are scored as collected (Drake), the veto records are not applied there (`no ABLATION/TEST veto record was applied (development basis)`), and the report marks its thresholds "exploratory: thresholds not pre-registered in a signed protocol".

Reported pick: none (always). Would-be outcome under the v4 rule: "no candidate qualifies."

Per-city bars on the logged rows: AUSTIN 23.68 A, CORPUS_CHRISTI 28.60 A, MIDLAND 32.42 A, EL_PASO 25.66 A.

| Candidate | Level | Benefit over `raw_forecast` (A) | Pooled bar (A) | Holm-adjusted p | Paired n | Cities favoured |
|---|---|---|---|---|---|---|
| `ml_wind_corrected` | not shown | 10.65 | 27.64 | 1.0000 | 172 | 3 of 4 |
| `ml_cooling_corrected` | not shown | 4.33 | 27.61 | 1.0000 | 171 | 3 of 4 |
| `reference_ml_refit_24h` | not shown | -44.87 | 27.63 | 0.3430 | 165 | 1 of 4 |

Alternatives over `ml_wind_corrected` in the live logs: `ml_cooling_corrected` -6.45 A (bar 27.61 A, favoured in 1 of 4 cities); `reference_ml_refit_24h` -59.16 A (bar 27.63 A, favoured in 0 of 4). Within the live-log family, `ml_wind_corrected` vs `reference_ml_refit_24h` is the one test with Holm-adjusted p 0.0270 (favors `ml_wind_corrected`, margin 59.16 A, 165 pairs). Paired n per comparison ranges from 30 to 172 (35 for the `persistence_24h` pairs). Both precision targets are not met for any test. The check agrees in direction with the headline and does not decide anything.

## Data gaps

- Headline: no failed city (`failed_cities` is empty), no missing slot, 0 rows dropped for null weather, 0 candidate failures; every candidate scored 100 of 100 expected slots per city. Leakage probe passed for all four cities. Archive-vs-frame truth difference 0.0.
- Live-system check: per city, 44 rows in scope after exclusions (`missing_forecast_model` 5, `at_or_after_cutoff` 37, `duplicate_valid_time` 10 per city); `persistence_24h` is available for only 9 rows per city (candidate_unavailable 35); `reference_ml_refit_24h` is unavailable for 1 to 4 rows per city; `ml_wind_corrected` and `ml_cooling_corrected` are unavailable for 1 to 2 rows in AUSTIN, CORPUS_CHRISTI and EL_PASO, and `ml_cooling_corrected` failed for 1 MIDLAND row; `raw_forecast` is unavailable for 1 EL_PASO row.
- Report header shows `Git SHA e092d129978e0744e7565fdbb258a4b1f7ce8eef (dirty: True)`; the plan 07-12 summary records that the dirty files were unrelated (`.DS_Store`, `.obsidian`, `graphify-out`, `.planning/*`, docs Test and Evaluation Report files) and the read-scope clean-tree check printed nothing.
- Read 1 is spent. It is not re-run, re-scoped or re-parameterised.

## Provenance

| Item | Path | sha256 |
|---|---|---|
| Headline report.json | `data/shadow/evaluation/v4-read1/reconstructed_frames_20261102T175156Z/report.json` | `710e7f7946aa7bcbcf941ca43453ae64ff257ffdfc22d4e2c5394cc2cc4132e6` |
| Headline report.md | `data/shadow/evaluation/v4-read1/reconstructed_frames_20261102T175156Z/report.md` | `795f5b76fef0371524365f7d2c394b9041cf41b68bc4faae928b64d498c379c2` |
| Live-system report.json | `data/shadow/evaluation/v4-read1/shadow_logs_20261102T175210Z/report.json` | `8a8f1f0e94fb345e55c197c18bfa612af77ee30c401c4a782742c202b45922b2` |
| Live-system report.md | `data/shadow/evaluation/v4-read1/shadow_logs_20261102T175210Z/report.md` | `4edc89f9a8c0d4b096f547e951ae638733e69abfa2763bd3089738a6190c71ca` |
| vetoes.json | `docs/data-science/decisions/v4_selection/vetoes.json` | `1d31cf387098b85be46a5cedc83fa8097061ffa5bb9dd612e67e6204e37454dc` |
| Frozen artifact manifest | `data/shadow/models/ARTIFACT_HASHES.sha256` | `159f6af01a037042339c7dce36ffaf4910dc19e9eb27a73bc082bf2603ec8ecd` |
| AUSTIN refit manifest | `data/models/conductor_refit/v3-powersystems-2026-11-02/ARTIFACT_HASHES.sha256` | `e88f880cd51f6e25dd5aaa1cdf87ace6485b07f1051c0c4d31377205c53fbe12` |

- `rating_config_version`: `v3-powersystems-2026-11-02`.
- `scored_artifacts` (headline): the 12 frozen artifacts for CORPUS_CHRISTI, MIDLAND, EL_PASO (all three methods each) and AUSTIN `ml_wind_corrected` (frozen, sha256 `b19039c2d3e8bf7688c92d9946eb64fc118994f587ee42fb619349862b21f9a0`); AUSTIN `ml_cooling_corrected` (refit, `data/models/conductor_refit/v3-powersystems-2026-11-02/ml_cooling_corrected_AUSTIN.joblib`, sha256 `31fe8d9b0fec7b89b9deae0e294cabcb4c1d90fa6d43cf10390cda453ff20973`) and AUSTIN `reference_ml_refit_24h` (refit, same directory, sha256 `f5dc0ebb68b073573d94d6ea1b653fb9636738da575d9077a822427f13f0dc43`). All verified against their manifests (`refit_verified: true`, no problems).
- Evidence round: `v4-read1`; evaluation instant 2026-11-01T00:00:00Z; valid-time cutoff 2026-10-25T00:00:00Z (strict); run at 2026-11-02T17:51:56Z (headline) and 2026-11-02T17:52:10Z (live-system); live logs exported from `origin/shadow-collection-data` at `ec4279c04324c0935e77eccf4b3338f754c852da`.
- Protocol: `docs/data-science/decisions/confirmation_protocol_v4_early_selection_SIGNING_COPY.md`, signed 2026-11-02 by `aaphan`.
