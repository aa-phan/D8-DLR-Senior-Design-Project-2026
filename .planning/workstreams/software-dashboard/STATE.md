---
gsd_state_version: 1.0
milestone: null
milestone_name: Operator Dashboard
status: planning
last_updated: "2026-11-25T00:00:00.000Z"
last_activity: 2026-11-25
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md and this workstream's
.planning/workstreams/software-dashboard/REQUIREMENTS.md (defined 2026-11-11)

**Core value:** A grid operator who does not know the system can tell, in five seconds, which
city lines are rated above or below normal, which are on their normal rating, and which have late
data, and a late or untrusted dynamic rating never looks current.
**Current focus:** Requirements written; phases not planned. Owner: Software sub-team.

## Current Position

Phase: 1 of 3 (Foundation and fail-safe), not started
Plan: none
Status: Roadmap written 2026-11-25; next is /gsd-discuss-phase 1 --ws software-dashboard
Last activity: 2026-11-11 - workstream created by the Data Science owner with requirements, a
plain-language column guide and design guidance; no implementation.

Progress: [░░░░░░░░░░] 0%

## Accumulated Context

### Decisions

- 2026-11-11: Card headline is the percentage against the normal rating, with amps beneath; MW
  only in Technical details (Data Science owner).
- 2026-11-11: Grid-study (PSS/E) results are a deferred requirement, DEF-01 (Data Science owner).
- 2026-11-16: DEF-01 unblocked. The Data Science owner exposed the view `latest_grid_study` to the dashboard's key (the result tables stay private) and 19 real PSS/E runs exist. Still deferred from the first release; values are preliminary.
- 2026-11-11: Primary screen is a desk monitor; phone layout not required (Data Science owner).
- 2026-11-25: Framework is Django (server-rendered), as built in `frontend/`; settles Q6 framework
  and PRD OD-11 (owner).
- 2026-11-25: Data access is hybrid: Django renders on the server, and a small browser script keeps
  each card's age counting, turns it to Data late at 90 minutes when the database is unreachable,
  and refreshes values in place. Replaces OD-2's browser polling; ch. 7 to be restated in Phase 1
  (owner; grounding/findings.md D1).
- 2026-11-25: Work split in two workstreams: this one (foundation, overview, integration and
  usability review) and `dashboard-detail` (Allie: the per-city detail view). The detail view is
  its own Django app; the shared data layer and browser script stay here (owner).
- 2026-11-25: ISO 9241 is made explicit: Phase 1 writes a traceability list from the standard's
  principles to requirement IDs (PRD SW-F11); Phase 3 runs the usability review (PRD SW-F12).

### Blockers/Concerns

- Open questions Q1 to Q9 in docs/DASHBOARD-REQUIREMENTS.md ch. 11; Q1 (short estimate label)
  and Q9 (store the percentage as a column) need the Data Science owner before the card design
  is final.
