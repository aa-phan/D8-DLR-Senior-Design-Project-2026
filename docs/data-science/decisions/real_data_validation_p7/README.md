# Phase 3 validation re-run (plan 07-14, REVAL-01 re-run half)

## In plain English

This folder repeats the September 2026 check from Phase 3 (the window 2026-09-08 to 2026-09-28, already recorded by the live system) with everything now in its final form: the retrained ml forecast models (B2, trained on the same projected wind they are served), the naive-band fix for the G6 check (B5), and the final per-city conductor table (AUSTIN at Drake 100 C, `v3-powersystems-2026-11-02`). It is an offline replay of recorded observations: no network call, no FRESH row (the window ends 2026-09-28T23:00:00Z, before 2026-09-30), nothing pushed. The numbers are measurements, not a decision; the go/no-go is 07-17.

## Inputs and the commands that made the files

Input archive `data/historical/real_data_validation_2026-09-08_2026-09-28.csv`, sha256 `18f999aac44540138cfb2a2d1c7f624688e66d261e391a01b036970b8bfa25cf` (checked before and after the run). Run from the repository root with `P=data/historical/real_data_validation_2026-09-08_2026-09-28`:

```
PYTHONPATH=backend .venv/bin/python backend/real_data_validation.py replay --archive $P.csv --trace ${P}_trace.jsonl --start 2026-09-08T00:00:00Z --end 2026-09-28T23:00:00Z --step-hours 1 --method ml --warmup-hours 168 --archive-out ${P}_replay_ml_p7.csv --trace-out ${P}_replay_ml_p7_trace.jsonl --log-out ${P}_replay_ml_p7_log.csv --fidelity-out ${P}_replay_ml_p7_fidelity.json
(the same with --method naive and the _naive_p7 output names)
PYTHONPATH=backend .venv/bin/python backend/real_data_validation.py report --archive ${P}_replay_ml_p7.csv --trace ${P}_replay_ml_p7_trace.jsonl --start 2026-09-08T00:00:00Z --end 2026-09-28T23:00:00Z --step-hours 1 --warmup-hours 168 --method-label ml_p7 --replay-archive ${P}_replay_naive_p7.csv --replay-trace ${P}_replay_naive_p7_trace.jsonl --replay-label naive_p7 --out-dir docs/data-science/decisions/real_data_validation_p7
PYTHONPATH=backend .venv/bin/python backend/real_data_validation.py manifest --archive ${P}_replay_ml_p7.csv --trace ${P}_replay_ml_p7_trace.jsonl --log ${P}_replay_ml_p7_log.csv --start 2026-09-08T00:00:00Z --end 2026-09-28T23:00:00Z --step-hours 1 --warmup-hours 168 --forecast-method ml --out docs/data-science/decisions/real_data_validation_p7/manifest.json -- <the ml replay argv>
```

The report was re-run into a fresh directory and `diff -r` against the committed tables showed no difference (manifest and the fidelity copies excluded). One quirk of `manifest.json`: its `command` field is built by the Phase 3 `owner_command` helper, which wraps the arguments after `--` in the backfill entry point, so the `command` text is not runnable for a replay; `backfill_argv` holds the true argument list and is the record to trust. The manifest's `files` block hashes the replay outputs (archive, trace, log) and its `models` block the model files in force.

## Replay fidelity (D-18)

| Replay | Code and models | compared | excluded | mismatches |
|---|---|---|---|---|
| `fidelity_ml_p7.json` | HEAD, retrained models, B5, v3 config | 1683 | 333 | 0 |
| `fidelity_naive_p7.json` | HEAD, v3 config | 1683 | 333 | 0 |
| `fidelity_ml_control_p7.json` | commit `2c48f9e` (the commit before `a14f088`, which adopted the Power Systems values), previous models, Drake 75 C everywhere | 2016 | 0 | 0 |
| `replay_fidelity.json` (written by `report`: ml replay against naive replay) | HEAD | 2016 | 0 | 0 |

The 333 excluded steps in the two new-configuration replays are all AUSTIN (333 of its 504 steps), and they are the expected, by-construction effect of the conductor change (research Pitfall 14). The original live run rated AUSTIN with Drake at 75 C; `classify_steps` recomputes each step's rating with the production conductor, which is now Drake at 100 C, finds the archived rating contradicting its own recomputation, and classes the original step ERROR, which the fidelity check excludes and counts. The other three cities are not affected (zero excluded). The control replay at the commit before the change reproduces the live archive on all 2016 steps with zero mismatches, which shows the harness itself is intact and the AUSTIN differences come from the configuration alone.

## Headline (the full tables are in `tables.md` and the CSV files)

The comparison below sets this re-run against the Phase 3 tables in `../real_data_validation/`; AUSTIN is not like for like (different conductor, and the Phase 3 AUSTIN ml figures cover only 111 steps because the old ml lookback withheld the forecast most of the time; B5 now falls back to the naive band).

| City | ml MAE (A), Phase 3 | ml MAE (A), re-run | naive MAE (A), Phase 3 | naive MAE (A), re-run | ml bias (A), Phase 3 | ml bias (A), re-run |
|---|---|---|---|---|---|---|
| AUSTIN | 104.1 | 84.6 | 62.3 | 87.6 | 87.6 | -21.1 |
| CORPUS_CHRISTI | 86.4 | 61.3 | 62.9 | 62.9 | 41.9 | 0.1 |
| MIDLAND | 94.2 | 80.2 | 80.3 | 80.3 | 49.8 | 1.1 |
| EL_PASO | 126.7 | 112.6 | 117.3 | 117.3 | 77.6 | -11.5 |

ml now has a lower MAE than naive in every city of this window (the earlier upward bias of ml is gone), by 3.0 A (AUSTIN), 1.6 A (CORPUS_CHRISTI), 0.1 A (MIDLAND) and 4.7 A (EL_PASO). The differences are small next to the 260 to 470 A interval widths; this is context for D-15, not its answer.

Band engagement (B5, `val02_g6_band_by_city.csv`, share of G6-evaluated hours that had a band): AUSTIN 0.9875, CORPUS_CHRISTI 0.9405, MIDLAND 0.9366, EL_PASO 1.0. Of these hours the ml band gated 261, 233, 169 and 330 in the four cities and the naive band 56, 83, 82 and 6.

Detector (B4, D-16, `val02_detector_by_city.csv`): the CORPUS_CHRISTI trip rate is 0.1101 (37 trips of 336, 95 percent interval 0.0595 to 0.1637), the same as Phase 3 and entirely the model branch (37 model votes, no forecast or rolling votes), identical under the ml and naive replays. AUSTIN 0 of 321, MIDLAND 2 of 268 (ml only, forecast votes), EL_PASO 1 of 336.
