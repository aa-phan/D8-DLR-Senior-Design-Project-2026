<!-- generated-by: gsd-doc-writer -->
# Component Specs — Index

Eight component specs for the Software subsystem (`frontend/` React dashboard + `api/` Flask backend-for-frontend). See `../PRD.md` for requirements/why and `../ROADMAP.md` for phase order/dependencies/why-this-order. This file is just the index and the shared template. (`api-contract.md` in this directory is a data-shape reference for the API layer, not a component spec, and is outside the F1–F8 numbering.) It mirrors `docs/data-science/specs/README.md`.

| ID | Component | Phase | Effort | Status | File |
|---|---|---|---|---|---|
| F1 | Data Access & API Layer | 1 | M | Not started | `F1-data-access-api.md` |
| F2 | Dashboard Shell & Location Selection | 1 | M | Not started | `F2-dashboard-shell.md` |
| F3 | Line Status & Current Conditions View | 2 | S | Not started | `F3-line-status.md` |
| F4 | DLR vs. Static Capacity Chart | 2 | M | Not started | `F4-dlr-vs-static-chart.md` |
| F5 | Forecast & Trusted-Duration View | 3 | M | Not started (externally blocked) | `F5-forecast-trusted-duration.md` |
| F6 | Anomaly & Fallback Status Indicators | 3 | M | Not started (externally blocked) | `F6-anomaly-fallback-status.md` |
| F7 | PSS/E Output Integration | 4 | L | Not started (contract undefined) | `F7-psse-integration.md` |
| F8 | Integration, E2E & Usability Validation | 4 | M | Not started | `F8-integration-validation.md` |

## Spec Template

Every component spec in this directory follows this structure, so they're scannable and diffable against each other:

- **Header** — ID, phase, effort (S/M/L), build status, one-line responsibility
- **Current Implementation** — files/functions/line refs, or "not started"
- **Interface & Data Contract** — inputs/outputs with units
- **Blocked by** — upstream components that must land first, and specifically why
- **Blocks** — what waits on this component landing (the anti-idle-time field — kept as the exact inverse of every other spec's "Blocked by")
- **Parallel-safe with** — components workable simultaneously without file collision
- **Known Issues** — concrete, file/line-referenced problems in the current code, or in the upstream data this component must cope with (while a component is not started, the latter is the relevant kind)
- **Acceptance Criteria** — testable, drawn from `System Design Report.md` §3.3 where applicable
- **Open Questions** — cross-referenced to `../PRD.md` §7 Open Decisions (`OD-n`) where one already exists

## Consistency Check

The dependency graph in `ROADMAP.md` §3 is the authoritative picture. Every "Blocked by" entry in a spec must have a matching "Blocks" entry in the upstream component's spec, and vice versa. If you edit one, edit the other.

Current edges (for quick checking):

| Component | Blocked by (internal) | Blocks |
|---|---|---|
| F1 | — | F3, F4, F5, F6, F7, F8 |
| F2 | — | F3, F4, F5, F6, F7, F8 |
| F3 | F1, F2 | F8 |
| F4 | F1, F2 | F8 |
| F5 | F1, F2 | F8 |
| F6 | F1, F2 | F8 |
| F7 | F1, F2 | F8 (soft, PSS/E leg only) |
| F8 | F1, F2, F3, F4, F5, F6 (hard); F7 (soft) | — |

External blockers (not components in this repo) — F5, F6: DS contract extension (`../PRD.md` §8); F7: Power Systems interface contract (`../PRD.md` OD-9). Both are recorded in the specs' "Blocked by" sections, with no matching "Blocks" entry because they live outside this directory.

## Shared Conventions Across Specs

- Reference `docs/data-science/schema/pipeline_output_v1.md` and `backend/units_def.py::PIPELINE_SCHEMA` for column names, units and ranges. Do not restate or fork them here.
- Fixture-first: every spec's acceptance criteria that can be met against `data/fixtures/sample_pipeline_output.csv` should be.
- Every spec is "Not started"; update this table and the spec header together when status changes.
