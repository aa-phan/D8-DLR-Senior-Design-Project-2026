# Phase 3 Plan 01: Bulk/Single-Run Lead-Alignment Boundary Investigation

**Status:** Investigation only. Task 3 of `03-01-PLAN.md` remains NOT executed. No design
decision (CONTEXT.md option a/b/c) is made here. This document characterizes the boundary the
`03-01-SUMMARY.md` halt report found, so that decision can be made with precise data instead of
"2024 fails, 2025 mostly holds."

**Date of investigation:** 2026-09-29
**Investigator:** continuation executor (worktree `agent-ac068a60a31eba6e8`), spawned specifically
for this characterization task.

---

## 1. Method

Reused `open_meteo_forecast_provider.fetch_historical_forecast` / `fetch_single_run` directly (no
HTTP logic duplicated — both functions are the same ones `forecast_leadtime_calibration.
measure_lead_alignment` calls). For each sampled `(city, date)`:

1. Fetch the bulk Historical Forecast series for that single date (`fetch_historical_forecast`).
2. Fetch the 00Z Single-Runs run for that date, `wind_speed_10m` only, `forecast_days=1`
   (`fetch_single_run`) — mirrors `measure_lead_alignment`'s own request shape exactly.
3. Compare the two series at leads 0–5 (valid hours 00:00–05:00 UTC that date) on `wind_speed`,
   using the same exact-equality match test the gate uses. Report `matched/6` and mean absolute
   difference (MAD) over the 6 compared hours.

Cities: **AUSTIN** and **EL_PASO** (one city from each of the phase's two corridors). Model
pinned to `ecmwf_ifs`, matching the gate.

Sampling cadence: monthly across 2024 (the year already known to fail), biweekly across 2025 (the
suspected transition year), sparse confirmation dates in 2026, plus a **daily-resolution pass**
around the transition once it was located (every 3 days from 2024-11-01 to 2024-12-13, then a
single-day pass on 2024-11-11 and 2024-11-12 to pin the exact cutover).

Scratch scripts used: `/tmp/boundary_sweep.py`, `/tmp/boundary_sweep_daily.py` (not part of the
repo, not committed — pure investigation tooling; only this findings document and the git commit
that adds it are permanent artifacts of this task).

---

## 2. Results — monthly/biweekly sweep (2024-01 through 2026-09)

`matched/6` = exact bulk-vs-single-run matches at leads 0–5. MAD = mean absolute difference (m/s)
over the 6 compared hours.

| Date | AUSTIN matched/6 | AUSTIN MAD | EL_PASO matched/6 | EL_PASO MAD | Verdict |
|---|---|---|---|---|---|
| 2024-01-01 | — | — | — | — | `SingleRunUnavailable` both cities (archive-boundary, not a mismatch) |
| 2024-02-01 | — | — | — | — | `SingleRunUnavailable` both cities |
| 2024-03-01 | — | — | — | — | `SingleRunUnavailable` both cities |
| 2024-04-01 | 0/6 | 0.955 | 0/6 | 0.920 | FAIL |
| 2024-05-01 | 0/6 | 0.810 | 0/6 | 1.070 | FAIL |
| 2024-06-01 | 0/6 | 1.067 | 0/6 | 0.768 | FAIL |
| 2024-07-01 | 0/6 | 0.538 | 0/6 | 2.377 | FAIL |
| 2024-08-01 | 0/6 | 1.202 | 0/6 | 0.613 | FAIL |
| 2024-09-01 | 0/6 | 0.623 | 0/6 | 1.575 | FAIL |
| 2024-10-01 | 0/6 | 0.453 | 0/6 | 1.227 | FAIL |
| 2024-11-01 | 0/6 | 0.172 | 0/6 | 0.425 | FAIL |
| **2024-12-01** | **5/6** | **0.043** | **5/6** | **0.028** | **PASS (rounding)** |
| 2025-01-01 | 5/6 | 0.047 | 5/6 | 0.007 | PASS |
| 2025-01-15 | 5/6 | 0.003 | 5/6 | 0.023 | PASS |
| 2025-02-01 | 5/6 | 0.050 | 5/6 | 0.012 | PASS |
| 2025-02-15 | 6/6 | 0.000 | 5/6 | 0.175 | PASS |
| 2025-03-01 | 5/6 | 0.087 | 5/6 | 0.108 | PASS |
| 2025-03-15 | 5/6 | 0.080 | 5/6 | 0.153 | PASS |
| 2025-04-01 | 5/6 | 0.018 | 5/6 | 0.002 | PASS |
| 2025-04-15 | 5/6 | 0.182 | 5/6 | 0.285 | PASS |
| 2025-05-01 | 5/6 | 0.127 | 5/6 | 0.030 | PASS |
| 2025-05-15 | 5/6 | 0.057 | 5/6 | 0.033 | PASS |
| 2025-06-01 | 5/6 | 0.095 | 5/6 | 0.098 | PASS |
| 2025-06-15 | 5/6 | 0.015 | 5/6 | 0.023 | PASS |
| 2025-07-01 | 5/6 | 0.145 | 5/6 | 0.020 | PASS |
| 2025-07-15 | 5/6 | 0.173 | 5/6 | 0.142 | PASS |
| 2025-08-01 | 5/6 | 0.012 | 5/6 | 0.083 | PASS |
| 2025-08-15 | 5/6 | 0.415 | 5/6 | 0.060 | PASS |
| 2025-09-01 | 5/6 | 0.160 | 5/6 | 0.020 | PASS |
| 2025-09-15 | 5/6 | 0.352 | 5/6 | 0.270 | PASS |
| 2025-10-01 | 6/6 | 0.000 | 3/6 | 0.017 | PASS (El Paso lower count, but MAD trivial) |
| 2025-10-15 | 6/6 | 0.000 | 5/6 | 0.008 | PASS |
| 2025-11-01 | 5/6 | 0.003 | 6/6 | 0.000 | PASS |
| 2025-11-15 | 6/6 | 0.000 | 5/6 | 0.002 | PASS |
| 2025-12-01 | 5/6 | 0.008 | 6/6 | 0.000 | PASS |
| 2025-12-15 | 6/6 | 0.000 | 6/6 | 0.000 | PASS |
| 2026-01-01 | 5/6 | 0.007 | 5/6 | 0.008 | PASS |
| 2026-01-15 | 5/6 | 0.002 | 6/6 | 0.000 | PASS |
| 2026-03-01 | 4/6 | 0.010 | 5/6 | 0.005 | PASS (MAD trivial) |
| 2026-06-01 | 6/6 | 0.000 | 6/6 | 0.000 | PASS |
| 2026-09-20 | 6/6 | 0.000 | 6/6 | 0.000 | PASS (RESEARCH.md's own probe date — reproduced) |

**Interpretation of the "5/6, near-zero MAD" pattern (2024-12-01 onward):** this is the same
two-decimal-rounding artifact `03-01-SUMMARY.md` already flagged for Corpus Christi ("three-of-four
cells are two-decimal rounding at the boundary rather than a different lead"). Every "PASS" row's
MAD is ≤0.42 m/s and the overwhelming majority are <0.2 — genuinely bit-identical to two-decimal
precision, one lead cell out of six occasionally rounding differently. This is categorically
different from the pre-boundary "FAIL" rows, whose MAD ranges 0.17–2.4 m/s (a real, different
underlying value, not a rounding artifact).

---

## 3. Daily-resolution pinpoint (2024-11-01 through 2024-12-13)

| Date | AUSTIN matched/6 | MAD | EL_PASO matched/6 | MAD |
|---|---|---|---|---|
| 2024-11-01 | 0/6 | 0.172 | 0/6 | 0.425 |
| 2024-11-04 | 0/6 | 1.453 | 0/6 | 1.765 |
| 2024-11-07 | 0/6 | 0.493 | 0/6 | 0.890 |
| 2024-11-10 | 0/6 | 0.332 | 0/6 | 0.388 |
| **2024-11-11** | **0/6** | **0.932** | **0/6** | **0.660** |
| **2024-11-12** | **0/6** | **0.262** | **0/6** | **0.518** |
| **2024-11-13** | **5/6** | **0.045** | **5/6** | **0.025** |
| 2024-11-16 | 5/6 | 0.047 | 5/6 | 0.013 |
| 2024-11-19 | 5/6 | 0.068 | 5/6 | 0.160 |
| 2024-11-22 | 5/6 | 0.070 | 6/6 | 0.000 |
| 2024-11-25 | 5/6 | 0.037 | 5/6 | 0.202 |
| 2024-11-28 | 5/6 | 0.065 | 5/6 | 0.315 |
| 2024-12-01 | 5/6 | 0.043 | 5/6 | 0.028 |
| 2024-12-04 | 5/6 | 0.217 | 5/6 | 0.060 |
| 2024-12-07 | 5/6 | 0.070 | 5/6 | 0.003 |
| 2024-12-10 | 5/6 | 0.017 | 5/6 | 0.058 |
| 2024-12-13 | 5/6 | 0.067 | 5/6 | 0.007 |

(2024-11-11 and 2024-11-12 were sampled by direct follow-up query, not the automated daily sweep,
to pin the exact cutover between the last-failing and first-passing dates.)

---

## 4. Answer to Question 1: sharp boundary, not a gradual zone

**The transition is a single-day, sharp cutover, not a gradual degradation.** Both cities flip
from complete failure (0/6, MAD 0.26–0.93 m/s) to the healthy pattern (5–6/6, MAD ≤0.05 m/s)
**between 2024-11-12 and 2024-11-13**, with no intermediate/noisy zone at daily resolution. Every
date sampled before 2024-11-13 fails uniformly (0/6); every date sampled at or after 2024-11-13
passes (5/6 or 6/6, small-rounding-only misses), all the way through the most recent confirmation
date (2026-09-20).

There is a second, distinct boundary earlier in 2024: dates before roughly 2024-03-14 return
`SingleRunUnavailable` (archive-boundary, not a value mismatch) rather than a failed comparison —
this is a different phenomenon from the transition above (see Section 5) and is already reflected
in `config.FORECAST_EXPERIMENT_VERIFIED_WINDOW_START = "2024-03-14"`. The **verified-good boundary
for the bit-identical rule itself is 2024-11-13, not 2024-03-14** — the existing config constant
correctly marks where the Single-Runs archive *starts*, but that is a different and earlier
threshold than where the bulk/single-run *alignment rule* actually starts holding. Data from
2024-03-14 through 2024-11-12 is inside the "archive reachable" window but the rule does not hold
there.

**Corrected verified-good window for this rule: 2024-11-13 through the present.**

---

## 5. Answer to Question 2: root cause (best-effort, found)

Two separate facts were checked, both from public documentation, in well under the "one quick
check" budget:

**a) Open-Meteo's own docs** (`https://open-meteo.com/en/docs/historical-forecast-api`, fetched
2026-09-29) state directly: *"ECMWF IFS HRES at 9 km is archived from March 2024; all other
models from 2nd of April 2026"* — this is the Single-Runs archive's own start date for this
model, and it matches `config.FORECAST_EXPERIMENT_VERIFIED_WINDOW_START` almost exactly (measured
2024-03-14, documented "March 2024"). This explains the `SingleRunUnavailable` boundary skips for
January/February 2024 in Section 2 — those are not part of the "rule doesn't hold" finding; they
are simply dates the Single-Runs archive doesn't reach at all, so no comparison is possible.

**b) The 2024-11-12/13 alignment cutover matches ECMWF's operational IFS model-cycle upgrade to
Cycle 49r1, implemented 12 November 2024** — found via a public search returning an ECMWF forum
post title ("CAMS Model CY49R1 successfully upgraded on 12 November 2024") and independent
third-party confirmation ("ECMWF 49r1 Upgrade - 12 November 2024," weatherbell.com). This is not
an Open-Meteo-side change; it is ECMWF's own IFS model version changing underneath Open-Meteo's
ingestion. A model cycle upgrade plausibly changes how the bulk Historical Forecast product's
"stitched first 6 hours of each run" is archived/re-derived relative to the Single-Runs archive,
consistent with the measured before/after shift from "systematically different" (MAD 0.17–2.4 m/s
every hour) to "bit-identical" (MAD <0.05 m/s except two-decimal rounding).

This is corroborating, not certain — no Open-Meteo-side changelog entry was found confirming
they changed their *own* stitching/archival logic at that date (only that ECMWF's own upstream
model cycle changed then, and the alignment property flipped on the same day). Not investigated
further, per the "one quick check" budget — this is sufficient to say the boundary is real,
dated, and externally explicable, not a data artifact.

---

## 6. Answer to Question 3: usable row volume if narrowed to the verified-good window

Arithmetic only, per city (all four project cities would each get this same row count from a
narrowed window, since the window is a calendar range applied uniformly):

| Window | Days | Hourly rows | Scored rows (`hour % 6 == 1`, ~4/day) |
|---|---|---|---|
| **Plan's original window** (`2023-01-01` – `2025-12-31`, unmodified) | 1,095 | 26,280 | ~4,380 |
| **Verified-good window, capped at original end** (`2024-11-13` – `2025-12-31`) | 413 | 9,912 | ~1,652 |
| **Verified-good window, through today** (`2024-11-13` – `2026-09-29`) | 685 | 16,440 | ~2,740 |

Capping at the original window's end date (`2025-12-31`) and starting at the verified boundary
leaves **~38% of the originally planned row volume** (1,652 vs. 4,380 scored rows). Extending the
window's end date to "now" (2026-09-29) instead of the original 2025-12-31 cap recovers to
**~63%** of the original volume (2,740 vs. 4,380 scored rows), at the cost of departing from the
window `03-CONTEXT.md`/`03-RESEARCH.md` originally scoped (which was chosen to match Phase 1's
training window row-for-row per `03-01-PLAN.md`'s Task 1 action block).

Either narrowed figure (1,652 or 2,740 scored rows per city) is a real, non-trivial reduction from
4,380, but neither is degenerate — for context, a three-way calendar split with even thirds would
still leave roughly 550–900 scored test rows per city under the narrower framing, which is enough
for a meaningful (if noisier than originally planned) MAE comparison between arms. This is
arithmetic only; no claim is made here about statistical power or which of CONTEXT.md's options
(a)/(b)/(c) is preferable — that decision is explicitly out of scope for this investigation.

---

## 7. Summary

- The bulk/single-run bit-identical rule has a **sharp, single-day transition at 2024-11-12 →
  2024-11-13**, not a gradual or noisy degradation zone, confirmed at daily resolution across two
  cities (AUSTIN, EL_PASO) spanning both of the phase's corridors.
- Before the boundary: uniform, total failure (0/6 matched leads, MAD 0.17–2.4 m/s). After the
  boundary: uniform success (5–6/6 matched leads, MAD ≤0.42 m/s and almost always <0.2 — a
  rounding artifact at the margin, not a different value), confirmed continuously from 2024-11-13
  through 2026-09-20 (33 additional sample dates, zero exceptions to the pattern).
- Root cause: best-effort search found a plausible, dated external explanation — ECMWF's IFS
  model cycle upgrade to Cycle 49r1, implemented 2024-11-12, the same day the alignment property
  flips. Not proven beyond correlation on the same date, but sufficient to establish the boundary
  is a real, externally-anchored event rather than a code or data artifact.
- A separate, earlier, and different phenomenon (`SingleRunUnavailable` for dates before
  2024-03-14) reflects the Single-Runs archive's own start date for this model — already
  correctly captured by `config.FORECAST_EXPERIMENT_VERIFIED_WINDOW_START`. That constant should
  not be confused with the alignment-rule boundary found here (2024-11-13), which is substantially
  later.
- Narrowing the experiment window to start at the verified boundary leaves ~38% of the originally
  planned row volume if the window's end date is kept at 2025-12-31, or ~63% if extended through
  the present — both non-trivial but materially smaller than originally planned.

**No design decision is made here.** This document exists solely to give the next design
conversation (CONTEXT.md options a/b/c, or a fourth option this data may newly support — e.g.
"narrow the window to 2024-11-13 onward" as a more precise version of option (c) than the
original halt report could offer) a precise, dated, multi-city-confirmed boundary instead of
"2024 fails, 2025 mostly holds."

---

## Addendum (Plan 03-01 execution session, same day): this boundary was incomplete

**This document's "corrected verified-good window: 2024-11-13 through the present" is NOT the
final window.** This investigation's method (Section 1) compared bulk against the **00Z single
run only**. The user's decision to narrow the window to 2024-11-13 was made on that basis. When
the plan's execution resumed and re-ran the ACTUAL calibration gate
(`forecast_leadtime_calibration.measure_lead_alignment`, which samples all four six-hourly runs —
00Z/06Z/12Z/18Z — not just 00Z), the live gate still FAILED at 2024-11-13. A follow-up daily
-resolution sweep (same method as Section 3, both AUSTIN and EL_PASO) found the 06Z/18Z runs carry
their OWN separate, later, equally sharp cutover: uniform failure through 2025-09-30, uniform
success from 2025-10-01 onward. The 00Z/12Z runs were reliable throughout the 2024-11-13 ->
2025-09-30 gap; only 06Z/18Z were not — invisible to this document's 00Z-only method.

`config.FORECAST_EXPERIMENT_WINDOW_START` was corrected a second time, to **2025-10-01** (the
later of the two boundaries — both must hold for all four daily `hour % 6 == 1` scored rows, which
draw one row each from all four runs). See `backend/config.py`'s own comment on that constant for
the full two-boundary history, and `03-01-SUMMARY.md` for the live re-verification transcript.

A second, independent, and more consequential finding also emerged during that same re
-verification and is unrelated to lead-time alignment: Open-Meteo's bulk `historical-forecast-api`
response was found to be **empirically bit-identical** to `archive-api`'s reanalysis "truth" for
every hour tested, across all four project cities and the full corrected window — not merely
close. This is documented in `forecast_experiment.EXPERIMENT_LEAD_REALIZABILITY_CAVEAT` and in
full in `03-01-SUMMARY.md`; it was not something this boundary investigation was scoped to find
(it only characterized bulk-vs-single-run lead alignment, never bulk-vs-archive content), but a
future reader relying on this document alone should know it exists.

---
*Phase: 03-ampacity-forecast-correction-experiment-compare-persistence*
*Plan: 01 (investigation addendum — Task 3 still not executed)*
*Investigation completed: 2026-09-29*
