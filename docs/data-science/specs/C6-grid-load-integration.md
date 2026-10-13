# C6 — Grid Load Integration (ERCOT)

**Phase:** 2 (Core Consolidation) · **Effort:** M · **Status:** Implemented and now covered by real tests for the three previously-unverified acceptance criteria.

**Responsibility:** Pull real ERCOT hourly load data, resample DLR output to hourly worst-case, convert ampacity to MW, and merge the two for the economic/reliability comparison (DLR vs. static capacity vs. actual grid demand). This is the component feeding the research paper deliverable.

## Current Implementation

- `backend/ercot_data_retriever.py::pull_ercot_data(start, end)` — pulls via the `gridstatus` library, sums ERCOT zone columns matching `"WEST"` (case-insensitive) as a West-zone load proxy (falls back to total-ERCOT if no match; the `zone_substrings` parameter defaults to `("WEST",)`, and the per-city selection used for training-time characterization is `config.ANOMALY_ML_ERCOT_ZONE_SUBSTRINGS_BY_CITY` — Austin and Corpus Christi `SOUTH`, Midland and El Paso `WEST`), writes `outputs/ercot_data/ercot_west_load_{start_tag}_{end_tag}.csv`.
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

- ~~`static_capacity_mw` computed from a hardcoded `900.0` A...~~ **Fixed in C1** — now reads `config.DEFAULT_STATIC_RATING`.
- ~~`pull_ercot_data`'s output filename hardcoded...~~ **Fixed** — now `outputs/ercot_data/ercot_west_load_{start}_{end}.csv`, with colons/spaces sanitized out of the date strings. `ercot_dlr_merger.py`'s `__main__` block updated to match.
- The "stress %" metric (`ercot_west_load_mw / dlr_capacity_mw`) treats total ERCOT western-zone load as if it all flows across the single modeled line — explicitly labeled a "simplified metric for visual correlation" in-code. **Still open** — not addressed this pass; fine for illustrative plots, should not be read as an actual utilization number in the research paper without real power-flow allocation (Power Systems sub-team territory, out of DS scope).
- ~~`resample("1H")` deprecated alias...~~ **Fixed** — now `resample("1h")`.
- **Newly found via live verification (2026-08-25)**: `pull_ercot_data` reaches ERCOT successfully (connects, begins downloading the "2026 historical load archive") but fails deterministically with `Error: Bad CRC-32 for file 'Native_Load_2026.xlsx'` → `ValueError: No objects to concatenate`. Reproduced twice, consistently. This is in the `gridstatus` library's own download/decompression of ERCOT's published archive, not this project's code — but it means **C6's live ERCOT path was non-functional on 2026-08-25**, independent of anything in this repo. **Retest 2026-10-13: not reproduced.** `pull_ercot_data("2026-06-01", "2026-06-03", save=False)` and the same call for 2025-06-01..03 both completed (49 rows each, no `Bad CRC-32`) with the installed `gridstatus` 0.35.0, so the 2026 archive file now downloads. The cause (transient ERCOT-side archive issue vs. a fixed upstream file) was not determined; treat the path as working but unmonitored. Worth a follow-up to determine if this is a transient ERCOT-side archive issue, a `gridstatus` version incompatibility, or something fixable on our end (e.g. pinning a different `gridstatus` version, or fetching the current year differently than the historical-archive endpoint this function uses).

## Acceptance Criteria

- ✅ Hourly ampacity reflects the true minimum within each hour. Verified with a synthetic dip test (`backend/tests/ercot_dlr_merger_test.py::test_hourly_resample_uses_min_not_mean`) — confirms `.min()` behavior specifically, not just coincidentally matching mean/first/last.
- ✅ `amps_to_mw` output matches hand-calculated values for known (A, kV, PF) triples. Verified against independently hand-computed expected values (not re-derived from the same formula) for 3 triples plus a simple round-number sanity check.
- ✅ Merge produces no row loss/duplication for overlapping timestamps between DLR and ERCOT data. Verified: `pd.merge(..., how="inner")` confirmed to keep only the overlap with no duplicates, and to correctly drop non-overlapping hours from either source — this is documented, current, intentional behavior (see Open Questions below for whether it should stay that way).

## Open Questions

- Should the retriever's output filename be parameterized by date range, or is a single rolling file intentional?
- Is "stress %" meant to ever become a real per-line congestion metric, or does it stay illustrative-only permanently? Affects whether it belongs in the research paper's quantitative claims.
