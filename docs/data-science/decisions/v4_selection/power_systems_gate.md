# Power Systems gate: outcome (D-11, plan 07-11 Task 2 and 3)

## In plain English

Power Systems never sent a full set of values for any city, but the owner decided at signing (owner item O4 of the signed v4 protocol) that the one answer we do have, from an Austin Energy teammate, counts for AUSTIN. So AUSTIN now rates its line as 795 kcmil Drake ACSR that may run up to 100 degrees C (it was 75 degrees C), and nothing else about AUSTIN changed. CORPUS_CHRISTI, MIDLAND and EL_PASO have no answer and stay on the model-default Drake at 75 degrees C. Because AUSTIN's conductor changed, its two conductor-sensitive models (`ml_cooling_corrected` and `reference_ml_refit_24h`) were refit under the new setting on rows before 2026-03-17, and the held-out TEST check was re-scored under the production conductors. The re-score vetoed no candidate, the same outcome as before the switch. None of this picks a winner; it only fixes the conductor basis that read 1 will be scored under.

## Decision record

| Item | Value |
|---|---|
| Owner's reply | `apply-answers`, confirming the proposed payload shown to the owner |
| Time of the reply (UTC) | about 2026-11-02T17:32Z |
| Deadline named in the plan | 2026-10-31T00:00:00Z (Power Systems answers by this instant would count for read 1) |
| Gate option taken | apply-answers, AUSTIN only (signed v4 O4: `power_systems.partial_answers = custom_switch_austin_drake_100c`) |
| Plan precondition superseded | Task 3 said the clock must be before 2026-11-01T00:00:00Z, otherwise follow D-03. The read-1 instant has already passed (the signing copy says so), and signed v4 O4 replaces "before the instant" with "before read 1 is run" (`test.rescore_gate = before_read1_run`). This work was done before read 1 was run; read 1 has not been run. |
| New `RATING_CONFIG_VERSION` | `v3-powersystems-2026-11-02` (was `v2-provisional-2026-11-02`) |

## Values adopted (AUSTIN)

| Field | Value | Changed? | Source |
|---|---|---|---|
| conductor_type | 795 kcmil ACSR Drake | label only (was "795 kcmil ACSR Drake (model default)") | Austin Energy teammate, relayed by owner 2026-10-27; Austin Energy 2005 ERCOT ROS/SPWG statement; signed v4 O4 (2026-11-02) |
| diameter_m | 0.02814 | no (catalogue) | Drake 795 ACSR catalogue value, type confirmed by the same source |
| resistance_ac | 0.0726 ohm/km at 25 C | no (catalogue) | Drake 795 ACSR catalogue value, type confirmed by the same source |
| max_temp_c | 100.0 | yes (was 75.0) | Austin Energy teammate, relayed by owner 2026-10-27; Austin Energy 2005 ERCOT ROS/SPWG statement; signed v4 O4 (2026-11-02) |
| elevation_m | 900.0 | no (model default, not part of the answer) | provisional, Power Systems pending |
| line_azimuth | 173.15 | no (model default, not part of the answer) | carried-over corridor bearing, provisional |
| resist_temp_coef, emissivity, absorptivity | 0.00404, 0.8, 0.8 | no | provisional defaults |

CORPUS_CHRISTI, MIDLAND, EL_PASO: no answer, unchanged (795 kcmil Drake ACSR, 75 C, 900 m, carried-over bearings). The 2026-10-31T00:00:00Z deadline passed with no complete answer for any city; AUSTIN's switch rests on the owner's signed ruling, not on a complete answer.

## What was done

1. `backend/config.py`: AUSTIN `max_temp_c` 100.0 and `conductor_type` as above, per-value sources recorded, version bumped. `backend/tests/production_conductor_test.py`: `test_provisional_parity` replaced by `test_documented_divergence` (exactly AUSTIN differs, only in maximum operating temperature). `docs/data-science/schema/city_rating_v1.md` label sentence and conductor-basis paragraph updated. Commit a14f088.
2. Refit (`forecast_conductor_refit.py --cities-from-production-diff`): AUSTIN only, `ml_cooling_corrected` (3144 rows) and `reference_ml_refit_24h` (18834 rows), rows before 2026-03-17, into `data/models/conductor_refit/v3-powersystems-2026-11-02/`. Commit a933959.
3. TEST re-score (`forecast_test_split_score.py --conductor-basis production`), run directory `data/shadow/evaluation/v4-test/report_20261102T173449Z`. `vetoes.json` test section updated and accepted by `forecast_shadow_confirm.load_vetoes`; the frozen-drake TEST report is kept as `test.frozen_drake_record`.

## Artifact hashes (SHA-256)

| Artifact | SHA-256 |
|---|---|
| `ml_cooling_corrected_AUSTIN.joblib` (refit) | 31fe8d9b0fec7b89b9deae0e294cabcb4c1d90fa6d43cf10390cda453ff20973 |
| `reference_ml_refit_24h_AUSTIN.joblib` (refit) | f5dc0ebb68b073573d94d6ea1b653fb9636738da575d9077a822427f13f0dc43 |

`shasum -a 256 -c data/models/conductor_refit/v3-powersystems-2026-11-02/ARTIFACT_HASHES.sha256` reports OK for both lines, and `shasum -a 256 -c data/shadow/models/ARTIFACT_HASHES.sha256` still reports OK for every frozen artifact (`data/shadow/models` untouched).

## TEST re-score under the production conductors

Window 2026-03-18T00:00:00Z up to 2026-09-30T00:00:00Z, 784 slots per city. Veto rule unchanged (strictly higher MAE than `raw_forecast` in at least 3 cities).

| Candidate | Vetoed | Cities losing to `raw_forecast` |
|---|---|---|
| ml_wind_corrected | no | none |
| ml_cooling_corrected | no | none |
| reference_ml_refit_24h | no | MIDLAND (1 city, below the 3-city bar) |

Same veto outcome as the frozen-drake TEST run. AUSTIN under production (MAE in amps, candidate vs `raw_forecast`): `ml_wind_corrected` 126.10 vs 133.33, `ml_cooling_corrected` 106.48 vs 133.33, `reference_ml_refit_24h` 122.64 vs 133.33. Under frozen Drake the AUSTIN figures were 109.24, 91.29 and 101.73 against 114.46; the absolute errors rise because the truth and the plain forecast are recomputed at 100 C, which is a different (higher) ampacity scale, not because the models got worse relative to the plain forecast. The other three cities are unchanged. `forecast_shadow_confirm.py --dry-run --round v4-read1` lists AUSTIN as the one differing city, with both refit artifacts verified and no problems.

## Notes for later plans

- Read 1 is scored under this configuration (AUSTIN at 100 C; the other three on Drake 75 C). The 12 frozen Drake artifacts remain the labelled secondary.
- B1's conductor half is partly resolved (AUSTIN only); CORPUS_CHRISTI, MIDLAND and EL_PASO stay open (D-13).
- The B2 retrain in 07-14 runs under this configuration, `v3-powersystems-2026-11-02` (D-14).
- A value that arrives later for another city follows the signed late-answer rule (D-03), not a re-run of read 1.
