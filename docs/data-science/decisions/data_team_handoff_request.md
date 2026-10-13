# Data-Team Handoff Request — Sensor-Grounded Validation Inputs

**Status: DRAFT, NOT SENT.** Prepared 2026-10-05 for Aaron to review and send at their discretion.
Nothing in this file has been transmitted to anyone.

**Why this matters now:** every number this phase's ML-correction audit has produced validates
self-consistency against reanalysis-derived weather (Open-Meteo's Archive API), never an
independent sensor measurement — see `docs/data-science/decisions/forecast_correction_followup_audit.md`,
Finding 1 (D-01). Development continues against that archive data while this handoff is pending;
this request is what would let a *future* pass check the prototype's predictions against real
sensor readings instead.

**Proposed delivery date: no later than 2026-10-25.** This is one week before the project's Nov 1
model-freeze point (see the "Project pivot" section of the audit record above). If the data arrives
by then, the Nov 1 freeze decision can be informed by a quick look at whether the archive and the
sensor data agree in the ways D-03's reanalysis-only numbers assume; if it arrives later, see the
contingency note at the bottom of this request — the frozen Nov 1 configuration is not reopened to
accommodate late data.

## What's being requested

The smallest useful handoff to unblock an eventual sensor-grounded validation of the four per-city rating
points now in scope (AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO; see `point_scope.md`. This request
was drafted 2026-10-05 against the corridor-era scope of AUSTIN_CORPUS_CHRISTI and MIDLAND_EL_PASO,
retired 2026-10-12):

1. **Cleaned local weather observations** — station-level wind speed/direction, temperature, and
   (if available) solar irradiance at each of the four cities (Austin, Corpus Christi,
   Midland, El Paso), post quality-control.
2. **Timestamps and availability semantics, kept distinct** — the observation's own valid time,
   AND separately the time the cleaned record actually became queryable (its own
   decision-time-availability lag). These must not be conflated into a single timestamp field.
3. **Units, explicit per field, SI throughout** — m/s for wind speed, °C for temperature, W/m² for
   solar irradiance. No field should require the consumer to infer or assume a unit.
4. **Quality flags, per field** — naming the QC method or source used, so a flagged row can be
   excluded by the consumer rather than silently trusted as clean.
5. **Sensor location and height** — exact station coordinates, and anemometer/thermometer height
   above ground. IEEE 738's convective heat-loss term is height- and exposure-sensitive, so this is
   not optional metadata.
6. **Matching archived-forecast fields** — for each observation, the corresponding forecast-archive
   row (initialization time, availability time, decision time, and valid time — see
   `backend/forecast_shadow_pipeline.py`'s `ShadowTimestamps` for the exact four-field shape already
   in use) at the same valid time, so a forecast error can be computed against a real sensor
   reading instead of against reanalysis.

## What this does NOT ask for

- No request for real-time/streaming delivery — a batch historical pull covering whatever window
  the data team already has clean is sufficient to start.
- No request for new sensor installation or new locations — this is scoped to the four city
  points already in scope.

## Contingency if the data arrives late or incompletely

If this handoff is not ready by 2026-10-25 (or arrives only partially), the Nov 1 model freeze
proceeds on development evidence alone, as already planned. Any sensor-grounded validation that
becomes possible afterward is run as a **separately labeled external/sensor validation pass**,
clearly dated and clearly distinguished from this phase's own frozen ABLATION/FRESH-basis results —
it is never used to silently revise or re-run the already-frozen experiment's own numbers. This
mirrors the same append-only, never-overwrite discipline the audit record already uses for every
other correction in this phase.

## References

- `docs/data-science/decisions/forecast_correction_followup_audit.md` — "Data-team handoff —
  smallest useful spec" (the technical content above is drawn directly from that section) and
  Finding 1 (D-01, the reanalysis-provenance finding motivating this request).
- `backend/forecast_shadow_pipeline.py` — the experimental shadow prototype whose four-timestamp
  `ShadowTimestamps` shape this handoff's archived-forecast fields (item 6) should match.
