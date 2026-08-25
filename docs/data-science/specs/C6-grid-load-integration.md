# C6 — Grid Load Integration (ERCOT)

**Phase:** 2 (Core Consolidation) · **Effort:** M · **Status:** Implemented.

**Responsibility:** Pull real ERCOT hourly load data, resample DLR output to hourly worst-case, convert ampacity to MW, and merge the two for the economic/reliability comparison (DLR vs. static capacity vs. actual grid demand). This is the component feeding the research paper deliverable.

## Current Implementation

- `backend/ercot_data_retriever.py::pull_ercot_data(start, end)` — pulls via the `gridstatus` library, sums ERCOT zone columns matching `"WEST"` (case-insensitive) as a western-corridor load proxy (falls back to total-ERCOT if no match), writes `outputs/ercot_data/ercot_west_load_july2025.csv`.
- `backend/ercot_dlr_merger.py::amps_to_mw(amps, voltage_kv, pf) -> float` — `P = sqrt(3) * V * I * pf / 1000`. Module defaults: `LINE_VOLTAGE_KV = 345.0`, `POWER_FACTOR = 0.95`.
- `backend/ercot_dlr_merger.py::process_dlr_to_hourly(dlr_csv_path) -> pd.DataFrame` — resamples 5-minute DLR data to 1-hour bins, `.min()` for `dlr_amps` (worst-case-within-hour: "if wind dies for 15 minutes, the hourly rating must reflect the weakest link"), `.mean()` for wind/temp context. Converts to `dlr_capacity_mw` and `static_capacity_mw`.
- `backend/ercot_dlr_merger.py::load_ercot_west_data(start, end, csv_path) -> pd.DataFrame` — loads and time-filters the retriever's output.
- `backend/ercot_dlr_merger.py::plot_holistic_grid_view(merged_df, stid)` — two-panel plot: MW capacity (DLR vs. static) vs. ERCOT load, plus a derived "stress %" (load / capacity) for both.

## Interface & Data Contract

Reads C3's exported CSV by column name (`dlr_amps`, `wind_speed`, `air_temp`, `datetime_utc`) — this is the file-based coupling described in `ROADMAP.md` §1. Outputs `merged_ercot_dlr_{stid}.csv` with columns matching the MW subset of `PIPELINE_SCHEMA`: `dlr_capacity_mw`, `static_capacity_mw`, `ercot_west_load_mw`, plus `datetime_utc`.

## Blocked by

**C1** (static rating, date window), **C3** (reads C3's export schema by column name with no validation today — should validate once C2/C3 are stable).

## Blocks

Nothing downstream in this roadmap depends on C6 — it's a terminal component feeding the research paper output, not other DS components. (The research paper itself is a consumer, but it's outside this roadmap's component graph.)

## Parallel-safe with

C4, C5 (all Phase 2) — fully isolated, no shared files or functions with either.

## Known Issues

- `static_capacity_mw` is computed from a hardcoded `900.0` A (`backend/ercot_dlr_merger.py:42`) — this is the **second** of the two independent `900.0` literals flagged in C1; must be unified there, not fixed locally here.
- `pull_ercot_data`'s output filename (`ercot_west_load_july2025.csv`) is hardcoded regardless of the `start`/`end` arguments passed in — running it for a different date range silently overwrites the July 2025 file with mismatched content.
- The "stress %" metric (`ercot_west_load_mw / dlr_capacity_mw`) treats total ERCOT western-zone load as if it all flows across the single modeled line — explicitly labeled a "simplified metric for visual correlation" in-code. Fine for illustrative plots; should not be read as an actual utilization number in the research paper without real power-flow allocation (that's Power Systems sub-team territory, out of DS scope).
- `resample("1H")` uses the deprecated pandas alias `"1H"` rather than `"1h"` — works today but will warn/break on a future pandas major version.

## Acceptance Criteria

- Hourly ampacity reflects the true minimum within each hour — verified by construction (`.resample().min()`), but worth a test with a synthetic dip to confirm the worst-case value survives resampling.
- `amps_to_mw` output matches hand-calculated values for known (A, kV, PF) triples.
- Merge produces no row loss/duplication for overlapping timestamps between DLR and ERCOT data (`pd.merge(..., how="inner")` — confirm this is the intended join type, not `"left"`, since an inner join silently drops any hour missing from either source).

## Open Questions

- Should the retriever's output filename be parameterized by date range, or is a single rolling file intentional?
- Is "stress %" meant to ever become a real per-line congestion metric, or does it stay illustrative-only permanently? Affects whether it belongs in the research paper's quantitative claims.
