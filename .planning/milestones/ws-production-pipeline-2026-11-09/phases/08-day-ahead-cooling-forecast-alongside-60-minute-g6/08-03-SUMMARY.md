---
phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6
plan: 03
subsystem: database
tags: [postgres, day-ahead, empirical-quantile-band, live-rolling-band, anti-peeking, sha256, pytest]

requires:
  - phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6
    provides: 08-01 band_for TEST branch behind its final signature, the hashed band artifact, day_ahead_contract (LIVE_BAND_MIN_PAIRS, LIVE_BAND_WINDOW), public.day_ahead_forecast
  - phase: 04-supabase-store-and-writer
    provides: public.city_rating and the dlr_writer role, local_pg harness
provides:
  - day_ahead_band.live_pairs (one bound-parameter join of day_ahead_forecast to city_rating with the D-08 filters)
  - band_for live-rolling branch, per city x UTC target hour, behind the unchanged signature
  - strict parse_band_artifact (schema, method, quantiles, every city and target hour, integer n > 0, finite ordered offsets)
  - anti-peek test over every backend/*day_ahead*.py module
affects: [08-04, 08-05, 08-06, 08-07, 08-10, 08-12]

actuals:
  tokens: 7500
  tasks: 2
  commits: 2
plan_head_before: dce2e70d3028171adafa0766eafd3976674e69d2
plan_head_after: 8a59547d311385ee85770bdc210456302babba57

tech-stack:
  added: []
  patterns:
    - "Per-band switch: each city x UTC hour band moves from the hashed TEST offsets to the newest 120 live residuals independently, and keeps TEST unless the live 5% offset is below 0 and the 95% offset above 0"
    - "Graded pairs computed on the fly from two tables with one bound-parameter SELECT; nothing new is stored"
    - "Anti-peek guard as a test that globs the day-ahead modules at run time, reading source text and import AST"

key-files:
  created:
    - backend/tests/day_ahead_band_test.py
  modified:
    - backend/day_ahead_band.py

key-decisions:
  - "Live offsets are np.quantile of residual = rating_amps - forecast_amps at config.FORECAST_BACKTEST_QUANTILES, the same sign and method as the TEST artifact"
  - "A live set that does not bracket zero keeps the TEST band and logs the offsets and the pair count at INFO (the straddle rule), rather than clamping a live band to the point"
  - "BandChoice.artifact_sha256 always carries the TEST artifact hash, including on live-rolling rows, because the TEST artifact stays the fallback (D-05)"
  - "parse_band_artifact also pins method == ml_cooling_corrected; the plan listed the other checks but a wrong method would silently relabel another method's residuals"

patterns-established:
  - "Each live-pair filter is proven by a test that fails when only that WHERE condition is removed (mutation-checked by hand)"

requirements-completed: [DAY-03]

coverage:
  - id: D1
    description: "Hashed TEST artifact is rebuilt byte for byte from the tracked TEST rows; 16 bands, n = 196 each, lower < 0 < upper; every offset equals np.quantile of truth minus ml_cooling_corrected; rows_sha256 equals the rows file hash"
    requirement: "DAY-03"
    verification:
      - kind: unit
        ref: "backend/tests/day_ahead_band_test.py -k artifact"
        status: pass
      - kind: other
        ref: "PYTHONPATH=backend .venv/bin/python backend/day_ahead_band.py --check"
        status: pass
    human_judgment: false
  - id: D2
    description: "Strict artifact parser and TEST-window guard: wrong schema, method or quantiles, a missing city or hour key, a non-finite or unordered offset, a non-positive, fractional or boolean n are each rejected with a message naming the field; the builder refuses a row before 2026-03-18, at or after 2026-09-30, or with a missing value; window bounds equal forecast_test_split_score's"
    requirement: "DAY-03"
    verification:
      - kind: unit
        ref: "backend/tests/day_ahead_band_test.py -k 'parser or window'"
        status: pass
    human_judgment: false
  - id: D3
    description: "Anti-peeking: no backend/*day_ahead*.py module names the shadow prediction logs, the shadow-log reader, the anchored pair frame or a cut-off-dated cache, and none imports the shadow confirm, eval-core or score modules; no skill statistic is computed"
    requirement: "DAY-03"
    verification:
      - kind: unit
        ref: "backend/tests/day_ahead_band_test.py -k anti_peek"
        status: pass
    human_judgment: false
  - id: D4
    description: "Live rolling band per city x UTC hour: 59 pairs keep TEST, 60 switch with band_n 60 and pairs_through equal to the newest valid_time, only the newest 120 of 150 are used, offsets equal np.quantile of the residuals, one band's pairs never switch another hour or city"
    requirement: "DAY-03"
    verification:
      - kind: integration
        ref: "backend/tests/day_ahead_band_test.py -k 'live or per_band'"
        status: pass
    human_judgment: false
  - id: D5
    description: "D-08 filters, straddle rule, residual sign and the no-database path: fallback status, fallback flag, exhausted, backfill origin, a different config fingerprint on either row, a different cooling model hash, and a target at or after decision time are each not counted; a live set not bracketing zero keeps TEST and logs why; a forecast always 50 A low gives offsets centred near +50; conn None returns the TEST band"
    requirement: "DAY-03"
    verification:
      - kind: integration
        ref: "backend/tests/day_ahead_band_test.py -k 'filters or straddle or sign or conn_none'"
        status: pass
    human_judgment: false

duration: 9min
completed: 2026-11-08
status: complete
---

# Phase 8 Plan 03: Day-Ahead Uncertainty Band Summary

**Each of the 16 day-ahead bands (city x UTC target hour) now starts on the hashed TEST-split offsets and moves on its own to the empirical 5-95% residual quantiles of its newest 120 graded live pairs once 60 exist, with a strict artifact parser, a TEST-window guard and an anti-peeking test over every day-ahead module.**

The band artifact bytes did not change. Its sha256 is still `19b9c522bea11862c6edb97085d5f121d3c389e2420500a5e50b4ec004a747ec`, which is the value 08-05 pins in the live manifest. `git diff --quiet -- data/day_ahead/day_ahead_bands_v1.json` exits 0 and `day_ahead_band.py --check` is green.

## Performance

- **Duration:** about 9 min (09:47Z to 09:55Z)
- **Tasks:** 2
- **Files modified:** 2 (1 created, 1 edited)

## Accomplishments

- `live_pairs` is one statement with bound parameters: `day_ahead_forecast` joined to `city_rating` on (city, valid_time), restricted to weather-computed ratings (status ok, fallback false, exhausted false, origin live), the caller's config fingerprint on both rows, the caller's cooling model hash on the forecast, and a target before the decision time. Residual is `rating_amps - forecast_amps`.
- `band_for` keeps its 08-01 signature, so no caller changes. With a connection it fetches up to 120 pairs per band; at 60 or more it computes `np.quantile` offsets at `config.FORECAST_BACKTEST_QUANTILES` and uses them only when the 5% offset is below 0 and the 95% offset above 0. A live choice records `source=live-rolling`, `n` and `pairs_through` (the newest pair's valid_time). Otherwise the TEST band stays, and the straddle case logs why.
- `parse_band_artifact` rejects a wrong schema, method or quantiles, a missing city or hour key, a non-finite or unordered offset, and a non-positive, fractional or boolean `n`, each naming the field.
- Anti-peek test globs `backend/*day_ahead*.py` at run time (so 08-04's child is covered when it lands) and fails on any mention of the shadow prediction logs, the shadow-log reader, the anchored pair frame or a cut-off-dated cache, and on any import of the shadow confirm, eval-core or score modules.
- Mutation check by hand: removing each of the eight WHERE conditions from the pair query, one at a time, makes at least one `filters` test fail, so every filter is pinned.
- Full suite with local Postgres: 2788 passed.

## Task Commits

1. **Task 1: strict artifact parsing, reproducibility, TEST-window guard and anti-peeking guard** - `9c620cf` (test)
2. **Task 2: live rolling band per city x target hour** - `8a59547` (feat)

**Plan metadata:** recorded in the docs commit that follows this summary.

## TDD Notes

Both tasks carry `tdd="true"` but the plan is `type: execute` and `workflow.tdd_mode` is not enabled, so the gate is advisory and the plan prescribes one commit per task.

- **Task 1 RED:** the new tests were run first. 12 of 29 failed on the planned assertion (`Failed: DID NOT RAISE BandArtifactError` for the missing city, missing hour key, NaN and infinite offset, unordered offsets, non-positive n, wrong quantiles and wrong method cases). The artifact, window, clamp and anti-peek tests passed at once because 08-01 already built the reproducible artifact, the window guard and the clamp, and no module names the forbidden text; these tests pin existing behaviour rather than add any. GREEN: the strict parser made all 29 pass.
- **Task 2 RED:** 9 failed on the planned behaviour (no switch at 60 pairs, wrong source and size, and `AttributeError: module 'day_ahead_band' has no attribute 'live_pairs'`). The parametrized `filters` cases passed in RED because with no live branch nothing is ever counted; they only became meaningful at GREEN, which is why the control case (`59 good + 1 good = 60 switches`) and the by-hand removal of each WHERE condition were added. GREEN: 51 of 51 pass.

## Files Created/Modified

- `backend/day_ahead_band.py` - strict `parse_band_artifact` and `_check_band`; `live_pairs`, `_live_offsets`, the live-rolling branch of `band_for`; module docstring updated
- `backend/tests/day_ahead_band_test.py` - 51 tests: artifact, window, parser, clamp, anti_peek, live, per_band, filters, straddle, sign, conn_none, on a throwaway local Postgres as role `dlr_writer`

## Decisions Made

- Live offsets use the same residual sign and the same quantiles as the TEST artifact, so a band is `point + offset` in both branches.
- A live set that does not bracket zero keeps the TEST band; it is not clamped to a zero-width band.
- The recorded `artifact_sha256` is always the TEST artifact's, because that artifact stays the fallback.
- `method` is validated in the parser in addition to the plan's list, so a wrong-method artifact cannot be relabelled.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Parser also pins `method`**
- **Found during:** Task 1
- **Issue:** The plan's strictness list did not include `method`, but `build_band_artifact` writes it and the day-ahead value is only ever `ml_cooling_corrected`. An artifact of another method's residuals would otherwise parse and band the wrong forecast.
- **Fix:** `parse_band_artifact` requires `method == contract.FORECAST_METHOD`, with a test.
- **Files modified:** backend/day_ahead_band.py, backend/tests/day_ahead_band_test.py
- **Verification:** `-k parser` passes; `--check` still green, artifact bytes unchanged
- **Committed in:** 9c620cf

**Total deviations:** 1 auto-fixed (missing validation). **Impact:** none on the artifact or any caller; the committed artifact already has the right method.

## Issues Encountered

- Running `pytest backend` (a directory argument) instead of the repo-root default errors in collection because `backend/smoke_test.py` exits without `SYNOPTIC_TOKEN`. The suite is run from the repository root with the `pytest.ini` `testpaths`, as 08-01 did.

## Known Stubs

None.

## Threat Flags

None. The new surface is the one SQL statement and the live branch, both in the plan's threat model (T-08-08, T-08-09, T-08-39): the statement uses bound parameters and fixed identifiers, every D-08 filter has a test, and the anti-peek test covers all day-ahead modules.

## User Setup Required

None. Nothing here touched the live Supabase project, the live job, or any remote. No package was installed.

## Next Phase Readiness

- Ready for 08-04 (child calls `band_for` through the unchanged signature, passing its writer connection, config fingerprint, cooling model hash and decision time).
- 08-05 pins the band artifact hash `19b9c522bea11862c6edb97085d5f121d3c389e2420500a5e50b4ec004a747ec` (unchanged by this plan) in `data/models/LIVE_ARTIFACT_HASHES.sha256`.
- The writer role needs `select` on `public.city_rating` and `public.day_ahead_forecast`; it holds both today.

## Self-Check: PASSED

- Files present: `backend/day_ahead_band.py`, `backend/tests/day_ahead_band_test.py`.
- Commits `9c620cf` and `8a59547` are ancestors of HEAD; `git rev-list --count dce2e70..HEAD` was 2 before this summary.
- Verify commands: `-k "artifact or window or parser or clamp or anti_peek"` 29 passed; full `day_ahead_band_test.py` with local Postgres 51 passed, no skips; `--check` exits 0; `grep -c "join public.city_rating" backend/day_ahead_band.py` prints 1; artifact diff is empty; full suite 2788 passed.

---
*Phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6*
*Completed: 2026-11-08*
