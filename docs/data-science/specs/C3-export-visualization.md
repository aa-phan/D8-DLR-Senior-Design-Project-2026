# C3 — Export & Visualization

**Phase:** 1 (Foundation) · **Effort:** S · **Status:** Implemented; schema now formally published.

**Responsibility:** Write pipeline results to CSV and produce summary plots, in a format stable enough for other components (C6) and other sub-teams (Software's dashboard) to build against without re-deriving it by reading source.

## Current Implementation

- `backend/dlr_pipeline.py::export_results(df, output_path, file_prefix)` — writes one CSV per station to `outputs/station_data/`, columns: `stid, datetime_utc, air_temp, wind_speed, wind_direction, wind_perp_ms, solar_radiation, relative_humidity, dlr_amps, dlr_headroom_pct, dlr_uplift_flag`.
- `backend/dlr_pipeline.py::plot_dlr_summary(df, city=None, output_dir='.', file_prefix='dlr')` — one 4-panel PNG per station to `outputs/station_plots/`: DLR vs. static time series, wind (total + perpendicular), ambient temp, headroom histogram.
- `backend/ercot_dlr_merger.py::plot_holistic_grid_view(merged_df, stid)` — two-panel PNG (`holistic_view_{stid}.png`): MW capacity vs. ERCOT load, and a derived "stress %" panel.

## Interface & Data Contract

Output CSV columns are exactly the list in `export_results` above, which is a **subset** of `PIPELINE_SCHEMA` (C2) — not every schema column is exported (e.g. `dlr_capacity_mw`/`static_capacity_mw` are computed later, in C6, not here). This is the point where C3's job is to **publish** that subset explicitly as the DS→dashboard contract, rather than leaving it implicit in `export_results`'s `cols` list.

## Blocked by

**C2** — the schema being exported should be validated against `PIPELINE_SCHEMA` before this is considered stable enough to publish externally.

## Blocks

- **C6** — `backend/ercot_dlr_merger.py::process_dlr_to_hourly` reads the CSV C3 produces by column name (`dlr_amps`, `wind_speed`, `air_temp`, `datetime_utc`) with zero validation that those columns exist or hold what's expected.
- **Software sub-team's dashboard (external)** — this is the actual interface between DS and Software. Per `ROADMAP.md` Finding 2, publishing this schema (plus a small sample fixture CSV) as early as possible is the single highest-leverage item in Phase 1 for unblocking a different sub-team.

## Parallel-safe with

C1, C2 (all Phase 1).

## Known Issues

- ~~The exported schema exists only as the `cols` list...~~ **Fixed** — see `docs/data-science/schema/pipeline_output_v1.md`.
- Filenames still encode the date window and station ID (`{prefix}_{stid}.csv`) with no versioning — a schema change (new/renamed column) is still not distinguishable from an old export by filename alone. Not addressed this pass (see Open Questions — versioning strategy is still undecided).
- **Newly found via live verification**: when a requested station returns zero observation rows from the API entirely (as opposed to rows with some NaN columns), it is silently absent from `run_pipeline`'s output — no warning is logged that a specifically-requested station contributed nothing. `profile_missing_data`'s dead-station detection (`missing_pct[col] == 100`) only fires for stations that have rows with 100%-NaN columns; a station with zero rows never enters the groupby at all, so it's invisible to that check too. Confirmed with a real station (`MOFWL`, access-restricted under the current Synoptic token — see C4's Known Issues) run alongside a working station (`KAUS`): output silently contained only `KAUS`, with no log line calling out `MOFWL`'s absence.

## Acceptance Criteria

- ✅ A documented, versioned schema for the exported CSV exists independent of the `export_results` source code, and matches `PIPELINE_SCHEMA` for every overlapping column: `docs/data-science/schema/pipeline_output_v1.md`.
- ✅ A sample fixture CSV with realistic values exists so the Software sub-team can build/test the dashboard without needing to run the full pipeline or hold a Synoptic token: `data/fixtures/sample_pipeline_output.csv` (10 rows, one station, 5-minute cadence, round-trips through `validate_pipeline_row` with zero violations).
- ✅ **Now verified against a real, live pipeline run** (2026-08-25): `run_pipeline(['KAUS'], ...)` against live Synoptic data → `export_results` and `plot_dlr_summary` both completed with zero exceptions on real output (75 rows, one 6-hour window). C2's `validate_pipeline_output` also ran automatically and found 0 violations against live data — the first time C2 has been exercised against anything other than synthetic/hand-built rows. The specific "all-missing-data station" edge case was also tested (a zero-row station run alongside a working one) — export/plot succeeded without error, but see the new Known Issue above: the dead station is silently dropped rather than flagged, which is real behavior worth fixing, not just an untested edge case.

## Open Questions

- Should the export schema be versioned (e.g. a `schema_version` column or filename tag) so downstream consumers can detect breaking changes automatically?
- Should `dlr_capacity_mw`/`static_capacity_mw` (currently only computed in C6) be pulled forward into C3's export, so the dashboard doesn't need to run the ERCOT merge step just to get MW values?
