# C3 — Export & Visualization

**Phase:** 1 (Foundation) · **Effort:** S · **Status:** Implemented; schema is real but informal (defined by code, not published).

**Responsibility:** Write pipeline results to CSV and produce summary plots, in a format stable enough for other components (C6) and other sub-teams (Software's dashboard) to build against without re-deriving it by reading source.

## Current Implementation

- `src/dlr_pipeline.py::export_results(df, output_path, file_prefix)` — writes one CSV per station to `outputs/station_data/`, columns: `stid, datetime_utc, air_temp, wind_speed, wind_direction, wind_perp_ms, solar_radiation, relative_humidity, dlr_amps, dlr_headroom_pct, dlr_uplift_flag`.
- `src/dlr_pipeline.py::plot_dlr_summary(df, static_rating, output_dir, file_prefix)` — one 4-panel PNG per station to `outputs/station_plots/`: DLR vs. static time series, wind (total + perpendicular), ambient temp, headroom histogram.
- `src/ercot_dlr_merger.py::plot_holistic_grid_view(merged_df, stid)` — two-panel PNG (`holistic_view_{stid}.png`): MW capacity vs. ERCOT load, and a derived "stress %" panel.

## Interface & Data Contract

Output CSV columns are exactly the list in `export_results` above, which is a **subset** of `PIPELINE_SCHEMA` (C2) — not every schema column is exported (e.g. `dlr_capacity_mw`/`static_capacity_mw` are computed later, in C6, not here). This is the point where C3's job is to **publish** that subset explicitly as the DS→dashboard contract, rather than leaving it implicit in `export_results`'s `cols` list.

## Blocked by

**C2** — the schema being exported should be validated against `PIPELINE_SCHEMA` before this is considered stable enough to publish externally.

## Blocks

- **C6** — `src/ercot_dlr_merger.py::process_dlr_to_hourly` reads the CSV C3 produces by column name (`dlr_amps`, `wind_speed`, `air_temp`, `datetime_utc`) with zero validation that those columns exist or hold what's expected.
- **Software sub-team's dashboard (external)** — this is the actual interface between DS and Software. Per `ROADMAP.md` Finding 2, publishing this schema (plus a small sample fixture CSV) as early as possible is the single highest-leverage item in Phase 1 for unblocking a different sub-team.

## Parallel-safe with

C1, C2 (all Phase 1).

## Known Issues

- The exported schema exists only as the `cols` list inside `export_results` — there's no standalone document or fixture a dashboard developer could read without opening `src/dlr_pipeline.py`.
- Filenames encode the date window and station ID (`{prefix}_{stid}.csv`) with no versioning — a schema change (new/renamed column) is not distinguishable from an old export by filename alone.

## Acceptance Criteria

- A documented, versioned schema for the exported CSV exists independent of the `export_results` source code (e.g. a schema doc or fixture file), and matches `PIPELINE_SCHEMA` for every overlapping column.
- A sample fixture CSV with realistic values exists so the Software sub-team can build/test the dashboard without needing to run the full pipeline or hold a Synoptic token.
- Given a full `run_pipeline` output DataFrame, `export_results` and `plot_dlr_summary` run without error on all target stations, including edge cases (a station with all-missing data, per `profile_missing_data`'s dead-sensor detection in `src/dlr_pipeline.py`).

## Open Questions

- Should the export schema be versioned (e.g. a `schema_version` column or filename tag) so downstream consumers can detect breaking changes automatically?
- Should `dlr_capacity_mw`/`static_capacity_mw` (currently only computed in C6) be pulled forward into C3's export, so the dashboard doesn't need to run the ERCOT merge step just to get MW values?
