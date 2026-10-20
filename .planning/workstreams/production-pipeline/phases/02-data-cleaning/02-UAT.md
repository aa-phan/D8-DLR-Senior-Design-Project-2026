---
status: testing
phase: 02-data-cleaning
source: [02-VERIFICATION.md]
started: 2026-10-20T00:00:00Z
updated: 2026-10-20T00:00:00Z
---

## Current Test

number: 1
name: Provisional cleaning thresholds are physically reasonable on real data
expected: |
  During Phase 3 (VAL-01/VAL-02), the per-city flag rates from
  `clean_history(read_history(path, city=c), as_of=None)` (`report["flag_counts"]`)
  over the backfilled window are plausible for each city. Stuck and spike rates are
  believable, calm-night wind runs (El Paso, Midland) are not removed in bulk, and
  run-time jitter does not create spurious trailing gaps. If either happens, adjust
  the thresholds or rules and bump `CLEANING_POLICY_VERSION`.
awaiting: user response

## Tests

### 1. Provisional cleaning thresholds are physically reasonable on real data
expected: Stuck (6 rows) and spike (10 degC, 10 m/s, 700 W/m2 per hour) flag rates per city are plausible on the backfilled archive. Calm wind is not mass-excluded (see review WR-02), and hour-boundary jitter does not create trailing gaps (see review WR-04).
result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
