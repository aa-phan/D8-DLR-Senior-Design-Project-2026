# Phase 8: NSRDB Solar Integration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-12
**Phase:** 8-nsrdb-solar-integration
**Areas discussed:** NREL API key availability, Non-solar field handling, Fetch library, Temporal interval

---

## NREL API key availability

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, registered and I have it | Can export NSRDB_TOKEN the same way SYNOPTIC_TOKEN works; plan AND execute now | |
| Not yet — still pending | Plan now so it's ready; execution of live-fetch tasks waits for the key | ✓ |

**User's choice:** Not yet — still pending.
**Notes:** Recorded as D-01. Planning proceeds; live-network verification tasks in the executed plan will need an explicit precondition/checkpoint rather than assuming the key exists.

---

## Non-solar fields

| Option | Description | Selected |
|--------|-------------|----------|
| Solar only (recommended) | Populate only solar_radiation; wind/temp/humidity stay null on NSRDB rows | ✓ |
| Populate everything NSRDB returns | Fill all matching PIPELINE_SCHEMA columns, same shape as Open-Meteo | |

**User's choice:** Solar only (recommended).
**Notes:** Recorded as D-02. Matches `data_provider.md`'s explicit "do not use NSRDB wind for wind power calculations" verdict — prevents downstream consumers from accidentally trusting NSRDB's 2m MERRA-2 reanalysis wind.

---

## Fetch library

| Option | Description | Selected |
|--------|-------------|----------|
| Raw requests (recommended) | Matches the ASOS/Open-Meteo pattern from Phase 7, no new dependency | ✓ |
| pvlib.iotools.get_psm3 | Library-provided reader; adds pvlib as a new dependency | |

**User's choice:** Raw requests (recommended).
**Notes:** Recorded as D-03. Keeps all three Phase 7/8 provider modules consistent with each other.

---

## Interval

| Option | Description | Selected |
|--------|-------------|----------|
| 60-minute (recommended) | Matches Open-Meteo's hourly cadence and TCEQ's typical reporting | ✓ |
| 5-minute | Finest resolution, matching ASOS's density philosophy (Phase 7 D-01) | |

**User's choice:** 60-minute (recommended).
**Notes:** Recorded as D-04. GHI doesn't vary enough minute-to-minute at ampacity timescales to justify the extra rows for this phase's scope.

---

## Claude's Discretion

- Exact NSRDB request parameter names/values (attributes list, `interval=60`, `utc=true`, date formatting) — confirm exact API contract during research.
- API-key-absent error shape — default to the existing `dlr_pipeline._token()` / `SYNOPTIC_TOKEN` precedent unless research finds a reason not to.
- Historical-depth out-of-range handling (NSRDB PSM v4 GOES CONUS covers 2018-2025 only) — follow the Phase 7 D-05 fail-loud precedent.
- New module name/location — `backend/nsrdb_provider.py`, following the established naming convention.

## Deferred Ideas

- Fallback/primary-selection logic (NSRDB fails → fall back to Synoptic) is explicitly WX-06 / Phase 10 scope, not this phase.
- Live execution of the NSRDB fetch tasks is blocked on NREL API key registration completing.
