# Doc Ingest Synthesis Summary

Mode: merge (no pre-existing `.planning/PROJECT.md`, `REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md`, or phase `CONTEXT.md` files were found — nothing to merge against, so this run behaves like a fresh synthesis).

## Doc Counts by Type

| Type | Count | Sources |
|---|---|---|
| ADR | 0 | — |
| SPEC | 12 | C1–C10 component specs, `schema/pipeline_output_v1.md`, `Project Definition.md` |
| PRD | 1 | `docs/data-science/PRD.md` |
| DOC | 7 | `ROADMAP.md`, `specs/README.md`, `frontend/README.md`, `citations.md`, `decisions/data_provider.md`, `System Design Report.md`, `Prior Art Report.md` |
| **Total** | **20** | |

## Decisions

0 ADR-classified documents; 0 locked decisions. See `decisions.md` — intentionally near-empty, not an extraction error. The closest artifact (`docs/data-science/decisions/data_provider.md`) is a still-open research log, classified DOC, filed in `context.md` instead.

## Requirements

17 requirements extracted from the single PRD (`docs/data-science/PRD.md`): 12 functional (DS-F1–DS-F12, see `requirements.md`) + 5 non-functional (fail-safe default, unit correctness, reproducibility, no secrets committed, modularity). No competing-variant PRDs exist — nothing to reconcile in this pass.

## Constraints

13 constraint entries from 12 SPEC documents (`Project Definition.md` split into two entries — I/O spec table and UI/operating-environment/performance specs — since both are substantial and distinct constraint categories). Breakdown by type: schema (5), api-contract (4), protocol (3), nfr (1). See `constraints.md`.

## Context

7 topics, one per DOC-classified source. See `context.md`. Notable open item carried through as context (not a conflict): the weather-data-provider choice itself (PRD §7.1) is genuinely and consistently documented as unresolved across `PRD.md` and `decisions/data_provider.md` — no contradiction, just an open decision awaiting a team call.

## Conflicts

**0 blockers, 1 competing-variant warning, 5 auto-resolved (info).** Full detail: `../INGEST-CONFLICTS.md`.

- **Warning**: three same-precedence-tier SPEC documents (`Project Definition.md`, `C1-configuration.md`, `C8-corridor-discretization.md` via `station_explorer.py`) define three mutually inconsistent location/corridor scopes (four Texas cities vs. five different Texas cities vs. five West-Texas corridors). Needs explicit user resolution before routing into `ROADMAP.md` — this synthesizer cannot auto-pick between same-tier SPECs.
- **Auto-resolved (5)**: all five are the same pattern — a DOC-tier document (`System Design Report.md` and/or `Prior Art Report.md`) claims a capability is already selected/implemented/in-training, while a higher-precedence SPEC or the PRD states the actual repo state is otherwise (still-open decision, not-started component, or out-of-scope work). SPEC/PRD won per default precedence in every case; synthesized intel reflects the SPEC/PRD state, not the DOC claim.

## Pointers

- Decisions: `decisions.md`
- Requirements: `requirements.md`
- Constraints: `constraints.md`
- Context: `context.md`
- Conflict report: `../INGEST-CONFLICTS.md`

This file is the single entry point for `gsd-roadmapper`.
