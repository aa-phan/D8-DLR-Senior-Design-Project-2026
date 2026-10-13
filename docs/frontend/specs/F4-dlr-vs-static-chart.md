<!-- generated-by: gsd-doc-writer -->
# F4 — DLR vs. Static Capacity Chart

**Phase:** 2 (Core Views) · **Effort:** M · **Status:** Not started.

**Responsibility:** Visualize dynamic capacity against the static rating over time for the selected city — the project's central visual argument ("visualizing dynamic capacity", `Project Definition.md`; WBS 4.1.3 "Implement real-time data visualization of DLR vs. SLR capacity"; SW-F6). Makes the headroom (or shortfall) between the two ratings readable at a glance, with the driving weather available for context.

## Current Implementation

None. DS already produces static equivalents that show what the chart should convey:

- `outputs/station_plots/{window}_{stid}.png` (DS C3, `plot_dlr_summary`) — panel 1: DLR (IEEE 738) as a line, the static rating as a dashed red line (900 A in committed outputs), shaded uplift headroom between them; panel 2: total and perpendicular wind; panel 3: ambient temperature; panel 4: headroom histogram.
- `outputs/holistic_view_AN489.png` (DS C6) — MW capacity (DLR vs. static) against ERCOT West load, and a derived "stress %".

These are DS research-paper figures, not specifications for the dashboard.

## Interface & Data Contract

Inputs, via F1's time-series view-model (v1 export):

| Series | Source column | Unit |
|---|---|---|
| Dynamic limit | `dlr_amps` | A |
| Static limit | derived from `dlr_amps` and `dlr_headroom_pct`, or exported column (PRD §8, G5) | A |
| Headroom | `dlr_headroom_pct`, `dlr_uplift_flag` | % |
| Context: wind, temperature | `wind_speed`, `wind_perp_ms`, `air_temp` | m/s, degC |
| Time axis | `datetime_utc` | UTC, with timezone label (SW-NF7) |

Behavior rules:

- Both limits are always shown together with units on the axis; headroom is shaded where DLR > static and **visibly distinct** where DLR < static (that case occurs in committed outputs — PRD §9, OD-5).
- Gaps in data (missing slots, null values) render as gaps, never interpolated across silently and never as zero.
- Periods in which DS reports fallback (once exported, G2) are marked on the time axis so a low or flat segment can be read as "fallback" rather than "weather" — coordinated with F6.
- The chart uses F2's shared chart wrapper (also used by F5) so axes, units, timezone, and null handling are consistent.
- The chart plots DS values only; it computes no ratings (SW-NF4). Shape-only operations (downsampling for display, axis scaling) are presentation, not data changes.
- Whether to also show MW capacity versus ERCOT load (DS C6's view) is OD-8, **not a requirement**. If it is added, the "stress %" metric must not be shown as a utilization number (DS C6 Known Issues).

## Blocked by

**F1** (time-series view-model, null/timestamp normalization) and **F2** (shell slot, shared chart wrapper, timezone/unit conventions).

## Blocks

**F8** — the end-to-end test checks chart values against pipeline output.

## Parallel-safe with

**F3**, and (after F1/F2) **F5**, **F6**. F4 and F5 should agree on the shared chart wrapper up front (ROADMAP Finding 8) rather than each building its own.

## Known Issues

Upstream-data concerns (PRD §9):

- **Variable cadence and missing slots** across station files: charts must not assume a fixed 5-minute interval.
- **Static line is 900 A in all committed outputs**, not the per-city static ratings (`backend/config.py::STATIC_RATINGS`); a chart that hardcodes a static value would be wrong in either direction — read it from data. A city's static limit is now its own entry, not the minimum of a corridor pair, so a per-city line will differ from older corridor-era figures (for example Corpus Christi 3000 A rather than 1900 A).
- **Headroom up to 274%** and **DLR below static** both occur; neither matches the "30–50%" in the course documents. The chart's y-axis must accommodate both; do not clip.
- **`solar_radiation` constant at 1000.0** in five of six stations — if solar is plotted for context it may look like a flat line for a reason DS must explain.
- **Existing DS plots show repeated date tick labels** on the x-axis (the same `07/01` appears at two ticks); a dashboard time axis must label unambiguously.
- **MW capacity** exists only after DS's C6 merge, hourly, for one station — not available per location or at the cadence of the main series.

## Acceptance Criteria

- Against the fixture (10 rows, `AP140`), the chart shows 10 points whose y-values equal `dlr_amps` and a static line at the value implied by `dlr_amps` and `dlr_headroom_pct` (900 A); the shaded region matches `dlr_uplift_flag = True` for every row.
- Against a station with DLR below static (e.g. `F2876` output data) the sub-static region is visibly distinct from uplift and still plotted (no clipping at the static line).
- Null values and missing time slots (e.g. the `AN490` gaps) render as gaps, not zeros or straight lines across a gap.
- Axis labels carry units (A, MW if used) and timezone; hover/readout values equal the CSV values to the displayed precision.
- Switching city updates the chart through F1/F2's selected-location state with no stale series remaining from the previous location.
- When data are stale or unavailable (F1 `stale_or_missing`), the chart shows a clear unavailable state rather than the last series as if current.
- Chart plotted values for a pipeline run match the pipeline's CSV for every row (feeds F8's consistency check).

## Open Questions

- OD-5 (headline and styling when DLR < SLR), OD-7 (timezone), OD-8 (MW and ERCOT load).
- Look-back window and default time range, and whether the user can change them — not specified in the sources.
- A city is one point, but the station behind it can change between runs (nearest usable station, with fallback). Is the chart one series per city, or does it mark or split where the source station changes? Station files in the v1 export are keyed by `stid` with no city column (PRD G1), so a per-city series cannot be assembled from them until that mapping exists.
- No chart plots a corridor minimum or bottleneck; the dashboard has no such series.
