<!-- generated-by: gsd-doc-writer -->
# F3 — Line Status & Current Conditions View

**Phase:** 2 (Core Views) · **Effort:** S · **Status:** Not started.

**Responsibility:** For the selected city (one independent rating point), show the headline numbers an operator reads first: the current dynamic thermal limit (A) next to the static limit, the headroom, and the weather conditions producing it — and, if a source for it is ever defined, current sag. Implements SW-F2, SW-F3, and (conditionally) SW-F4 from the mock-up in `Project Definition.md` UI Specifications. This is the first vertical slice and the earliest end-to-end proof of F1 + F2.

## Current Implementation

None. For reference, DS already produces an equivalent static view as PNGs: `outputs/station_plots/*.png` (4-panel: DLR vs. static, total and perpendicular wind, ambient temperature, headroom histogram). These are file outputs of DS's `plot_dlr_summary` (C3), not UI code.

## Interface & Data Contract

Inputs, all via F1's view-model, from the v1 export columns (`docs/data-science/schema/pipeline_output_v1.md`):

| Display | Source column | Unit |
|---|---|---|
| Current dynamic limit | `dlr_amps` (latest row) | A |
| Static limit | the selected city's own static rating: derived from `dlr_amps` and `dlr_headroom_pct`, or a DS-exported column once requested (PRD §8, G5) | A |
| Headroom vs. static | `dlr_headroom_pct`, `dlr_uplift_flag` | % |
| Ambient temperature | `air_temp` | degC |
| Wind speed (total / perpendicular) | `wind_speed`, `wind_perp_ms` (direction: `wind_direction`) | m/s, deg |
| Solar irradiance | `solar_radiation` | W/m² |
| Relative humidity (optional) | `relative_humidity` | % |
| Data age | newest `datetime_utc` vs. now | — |
| Sag | **no source** | (unit undefined) |

Behavior rules:

- The headline is for the one selected city. There is no corridor minimum and no bottleneck city; a city is never rolled up with another.
- The headline number is whatever F1 reports as the **limit in effect** (dynamic, or static fallback, or stale), labelled with its basis. F3 does not decide fallback and does not recompute the rating (SW-NF4, SW-NF1).
- When `dlr_uplift_flag` is `False` (DLR below static), the headline shows the lower DLR and says it is below the static limit — never hides it. What the "operating limit" is in this case is OD-5.
- Missing optional values (`relative_humidity`, `solar_radiation`) render as "unavailable", not 0.
- The Input/Output table in `Project Definition.md` gives the intended value ranges per city (e.g. Austin ambient −5.5 to 41.7 degC, wind 0.2–8.0 m/s, solar 0–563 W/m²); these are descriptions of expected inputs, not display clamps.

## Blocked by

**F1** (view-model and limit-basis) and **F2** (shell, selector, shared status conventions). The sag element is additionally blocked by **OD-4** and is not required for F3 to ship.

## Blocks

**F8** — the end-to-end test needs this view to show the pipeline's current rating.

## Parallel-safe with

**F4**, **F5**, **F6** (all after F1 and F2) — separate panels. F3 and **F6** share a status convention defined in F2, so no file collision; they read the same F1 `limit basis` field.

## Known Issues

Upstream-data concerns the view must tolerate (PRD §9):

- **Sag has no producer.** Nothing in `backend/` computes sag and the WBS (Appendix B 4.1.x) lists no sag task, yet the mock-up shows it (OD-4).
- **The static rating is not exported**, only headroom against it. In committed outputs and the fixture it equals 900 A (`DEFAULT_STATIC_RATING`), not the per-city values in `backend/config.py::STATIC_RATINGS`. Under the per-city model a city uses its own entry (Austin 1825 A, Corpus Christi 1500 A, Midland 1875 A, El Paso 1320 A), no longer the minimum of a corridor pair; these are per-conductor values derived from unverified bundle averages and should be labelled as such.
- **`solar_radiation` is a constant 1000.0** in five of six committed station files; showing it as a measured value could mislead. Whether it is a fill value is a question for DS.
- **Headroom of 200%+** and **DLR below static** both occur in committed outputs; neither fits the "30–50%" framing in the course documents. Display faithfully and report to DS.
- **Fallback rating basis** (OD-6) means "static rating in effect" shouldn't be asserted blindly: G5 reports `min(computed, static_rating)`, and DS must export which basis applied.

## Acceptance Criteria

- Selecting the fixture's location shows the latest row's values exactly (the `18:45:00Z` row): `dlr_amps = 1220` A, `dlr_headroom_pct ≈ 35.6`, `air_temp = 34.4` degC, `wind_speed = 8.7` m/s, `wind_perp_ms = 7.2` m/s, `solar_radiation = 790` W/m², each with its unit.
- Every number is shown with the unit string from `PIPELINE_SCHEMA`; no UI-side rating math (SW-NF4).
- A row with `dlr_uplift_flag = False` shows the lower-than-static state unambiguously (test with a synthetic row or `F2876` data).
- A null `relative_humidity` renders "unavailable", not zero.
- When F1 reports `stale_or_missing`, the headline reads as static-rating-in-effect/data-unavailable and shows the data age; the stale dynamic value is not shown as current (SW-NF1).
- Times shown carry a timezone label (SW-NF7).
- Sag is either shown from a defined source with a unit, or visibly absent by an explicit team decision — not a fake placeholder number (OD-4).

## Open Questions

- OD-4 (sag), OD-5 (headline when DLR < SLR), OD-6 (basis wording), OD-7 (timezone).
- The city's observation comes from its nearest usable station, which can differ between runs (the DS probe/fallback lookup). Should the view name the station in use? `rate_city` returns it as `station_id` (`None` when every candidate failed or for grid providers), but that dict is not exported to a file or endpoint yet.
- Does the dashboard show a single latest snapshot, or a snapshot that follows a time scrubber over F4's chart? Not specified in the sources.
