# Pipeline Output Schema — v1

**Schema version:** v1
**Date:** 2026-08-24
**Scope:** This document describes the CURRENT exported CSV shape produced by
`backend/dlr_pipeline.py::export_results`, i.e. the files written to
`outputs/station_data/*.csv` (one file per station, named
`{file_prefix}_{stid}.csv`).

This is **not** the full pipeline schema. It is a subset of
`backend/units_def.py::PIPELINE_SCHEMA` (C2's canonical column/unit/range
definitions). In particular, `dlr_capacity_mw`, `static_capacity_mw`, and
`ercot_west_load_mw` are part of `PIPELINE_SCHEMA` but are **not** present in
this export — those columns are added later, downstream, by
`backend/ercot_dlr_merger.py` (a separate component, C6), which reads this
CSV and joins in MW/ERCOT-load values.

Column order below matches the exact order of the `cols` list in
`export_results` as of this writing. Any change to that list (add, remove,
reorder, rename) is a breaking change to this contract and should bump this
document to `pipeline_output_v2.md`.

## Columns

| # | Column | Unit | Description | Schema-validated? |
|---|--------|------|-------------|--------------------|
| 1 | `stid` | — (string identifier) | Weather station ID the observation was recorded at (e.g. `AP140`). | No — not in `PIPELINE_SCHEMA`; it's a station identifier, not a measured physical quantity. |
| 2 | `datetime_utc` | — (ISO-8601 UTC timestamp string) | Timestamp of the observation, UTC. Pipeline cadence is 5-minute intervals. | No — not in `PIPELINE_SCHEMA`; it's a timestamp identifier, not a measured physical quantity. |
| 3 | `air_temp` | degC | Ambient air temperature at the station. | Yes — `PIPELINE_SCHEMA["air_temp"]`, range `[-20.0, 60.0]`, required. |
| 4 | `wind_speed` | m/s | Total (scalar) wind speed at the station. | Yes — `PIPELINE_SCHEMA["wind_speed"]`, range `[0.0, 50.0]`, required. |
| 5 | `wind_direction` | deg | Wind direction, compass degrees (0–360, meteorological convention). | Yes — `PIPELINE_SCHEMA["wind_direction"]`, range `[0.0, 360.0]`, required. |
| 6 | `wind_perp_ms` | m/s | Component of wind speed perpendicular to the conductor's azimuth — the component that matters for IEEE 738 convective cooling. | Yes — `PIPELINE_SCHEMA["wind_perp_ms"]`, range `[0.0, 50.0]`, optional. |
| 7 | `solar_radiation` | W/m² | Incident solar radiation at the station, used for the IEEE 738 solar heat gain term. | Yes — `PIPELINE_SCHEMA["solar_radiation"]`, range `[0.0, 1400.0]`, optional. |
| 8 | `relative_humidity` | % | Relative humidity at the station. Not a direct input to the IEEE 738 rating calculation; carried through for context/QA. | Yes — `PIPELINE_SCHEMA["relative_humidity"]`, range `[0.0, 100.0]`, optional. |
| 9 | `dlr_amps` | A | Dynamic line rating (ampacity) computed via IEEE 738 from the weather inputs above and the configured conductor. | Yes — `PIPELINE_SCHEMA["dlr_amps"]`, range `[100.0, 4000.0]`, optional. |
| 10 | `dlr_headroom_pct` | % | Percent headroom of `dlr_amps` over the conventional static rating: `(dlr_amps - static_rating) / static_rating * 100`. Computed in `run_pipeline`'s "Step 5" using `static_rating` (default `900.0` A, see `backend/config.py::DEFAULT_STATIC_RATING`). | No — not in `PIPELINE_SCHEMA`. It's a derived/relative quantity dependent on the chosen static rating, not an absolute physical measurement with a fixed valid range. |
| 11 | `dlr_uplift_flag` | — (boolean) | `True` when `dlr_amps > static_rating`, i.e. dynamic rating exceeds the conventional static rating at that timestamp. | No — not in `PIPELINE_SCHEMA`; boolean derived flag, not a schema-validated physical quantity. |

## Notes

- Columns 3–9 are validated by `backend/units_def.py::validate_pipeline_row`
  (called in non-strict batch mode over the whole DataFrame by
  `backend/dlr_pipeline.py::validate_pipeline_output`, invoked automatically
  at the end of `run_pipeline`). `stid` and `datetime_utc` are identifiers and
  are intentionally excluded from `PIPELINE_SCHEMA` — there's no numeric unit
  or range to check them against.
- `dlr_headroom_pct` and `dlr_uplift_flag` are derived, not measured, and
  depend on whichever `static_rating` was passed into `run_pipeline` (default
  900.0 A). They're excluded from `PIPELINE_SCHEMA` for that reason: a fixed
  valid range wouldn't be meaningful across different static-rating configs.
- A sample fixture matching this exact schema (one station, 10 rows at
  5-minute cadence, all schema-validated columns passing
  `validate_pipeline_row` with zero violations) is checked in at
  `data/fixtures/sample_pipeline_output.csv`.
- See `docs/data-science/specs/C3-export-visualization.md` for the component
  spec this schema fulfills the acceptance criteria of.
