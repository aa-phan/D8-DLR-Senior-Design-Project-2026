---
workstream: dashboard-detail
created: 2026-11-25
---

# Project State

## Project Reference

Builds the per-city detail view of the operator dashboard, alongside the `software-dashboard`
workstream. Requirements: [`REQUIREMENTS.md`](REQUIREMENTS.md); roadmap: [`ROADMAP.md`](ROADMAP.md).
Owner: Allie (Software sub-team).

## Current Position

**Status:** Not started
**Current Phase:** 1 of 2 (Detail view and current conditions)
**Waiting on:** software-dashboard Phase 1 (shared data layer, city-state rules, browser script, ISO 9241 traceability list)
**Last Activity:** 2026-11-25
**Last Activity Description:** Workstream created with its roadmap and requirement list

## Decisions

- 2026-11-25: Django, server-rendered, with a small browser script for live age and Data late; shared with software-dashboard (owner).
- 2026-11-25: The detail view is its own Django app inside `frontend/`; it reuses the shared data layer and does not edit it directly (owner).

## Progress

**Phases Complete:** 0 of 2
**Current Plan:** N/A

## Session Continuity

**Stopped At:** Roadmap written
**Resume File:** None

To start: once software-dashboard Phase 1 is complete, run `/gsd-discuss-phase 1 --ws dashboard-detail`.
Before then, the design work (layout of the detail page, chart sketches) can begin from
DASHBOARD-REQUIREMENTS.md ch. 5.6 and ch. 6.
