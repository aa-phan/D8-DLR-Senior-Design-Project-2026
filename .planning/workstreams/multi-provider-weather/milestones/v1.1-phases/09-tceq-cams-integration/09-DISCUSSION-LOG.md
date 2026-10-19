# Phase 9: TCEQ CAMS Integration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-13
**Phase:** 9-tceq-cams-integration
**Areas discussed:** CAMS site selection, RH availability handling, Failure/fallback scope, "Current" vs range semantics

---

## CAMS site selection

| Option | Description | Selected |
|--------|-------------|----------|
| Research picks best site | Live-fetch each city's region listing, confirm the most-complete-data site, hard-code that CAMS ID per city | ✓ |
| Prefer solar-capable sites when tied | Same, but tie-break toward solar-reporting sites for future-proofing | |
| You decide per-site during planning | Defer entirely to planner/researcher | |

**User's choice:** Research picks best site.

| Option | Description | Selected |
|--------|-------------|----------|
| Completeness only | Pick strictly on wind/temp/RH completeness | ✓ |
| Completeness + closest to corridor endpoint | Also weigh proximity to CITY_COORDINATES/CORRIDOR_ENDPOINTS | |

**User's choice:** Completeness only.

| Option | Description | Selected |
|--------|-------------|----------|
| Pick the most-complete site anyway | Use best available site; missing fields go null per-row | ✓ |
| Flag as a blocker requiring a checkpoint | Treat like the missing NREL key — explicit precondition | |

**User's choice:** Pick the most-complete site anyway.
**Notes:** Matches Corpus Christi CAMS 83's precedent and the NSRDB/Open-Meteo null-if-absent handling.

---

## RH availability handling

| Option | Description | Selected |
|--------|-------------|----------|
| Null when absent | Leave relative_humidity null when the site's report has no RH field | ✓ |
| Require RH in site selection | Fold RH availability into site-completeness criteria | |

**User's choice:** Null when absent.

| Option | Description | Selected |
|--------|-------------|----------|
| Left null/unset | Provenance only set where the field itself has a value | ✓ |
| Explicitly marked "tceq_unavailable" | New sentinel provenance value | |

**User's choice:** Left null/unset.
**Notes:** Matches existing `attach_provenance` behavior used for NSRDB's null wind/temp/humidity rows.

---

## Failure/fallback scope

| Option | Description | Selected |
|--------|-------------|----------|
| Raise only, no fallback here | fetch_weather raises on bad reports; Synoptic fallback stays entirely out of scope (Phase 10) | ✓ |
| Raise, but structure the exception for Phase 10 to catch | Same behavior plus a purpose-built exception type | |

**User's choice:** Raise only, no fallback here.

| Option | Description | Selected |
|--------|-------------|----------|
| Raise only for wind/temp missing | RH's absence is expected and handled separately (null) | ✓ |
| Raise for any missing field, RH included | Treat RH the same as wind/temp | |

**User's choice:** Raise only for wind/temp missing.
**Notes:** Explicitly locks fallback-to-Synoptic wiring out of this phase's scope (WX-06/Phase 10).

---

## "Current" vs range semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Match existing (start, end) signature | TCEQ uses the same fetch_weather signature as Synoptic/ASOS; no separate single-reading path | ✓ |
| Add a dedicated latest-reading fetch | Separate get_current_conditions-style function | |

**User's choice:** Match existing (start, end) signature.

| Option | Description | Selected |
|--------|-------------|----------|
| Fetch one report per day, concatenate | Loop over each calendar day in range, concatenate hourly rows | ✓ |
| Support single-day ranges only for now | Raise for anything wider than one day | |

**User's choice:** Fetch one report per day, concatenate.

---

## Claude's Discretion

- Exact HTML parsing approach for `daily_summary.pl` (table structure, field matching) — confirm live during research.
- Exact module name/location for the new provider (`backend/tceq_provider.py`, following established naming).
- Unit conversions needed for TCEQ's reported units — confirm live.
- Whether Midland/El Paso CAMS regions (suspected region 7 / region 6) need further discovery — confirm live.
- Whether TAMISWeb is worth investigating if `daily_summary.pl` proves insufficient — default to `daily_summary.pl` unless research finds a blocking reason not to.

## Deferred Ideas

- Fallback/primary-selection logic (Synoptic fallback) — explicitly WX-06/Phase 10 scope, locked out of this phase (D-06).
- TAMISWeb as an alternate TCEQ interface — not a planned deliverable, only a discretionary fallback if `daily_summary.pl` proves insufficient.
- Live per-site solar-availability confirmation for Midland/El Paso (WX-09) — out of scope for REQUIREMENTS.md and not part of this phase's field scope.
