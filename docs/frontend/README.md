<!-- generated-by: gsd-doc-writer -->
# Frontend/API Documentation — Index

**Status:** Requirements, roadmap and component specs are written; **no implementation exists yet.** `frontend/` (React dashboard) and `api/` (Flask backend-for-frontend) each still contain only a placeholder README. Every component below is "Not started".

This directory is the home for the Software sub-team's PRD and technical specs. It follows the convention established in `docs/data-science/`:

- `PRD.md` — requirements: what the subsystem must do, why, who consumes it, non-functional requirements, open decisions.
- `ROADMAP.md` — phased implementation order (least→most complex), a dependency graph, and a blocker/parallelization analysis so work can be split across contributors without idle time.
- `specs/` — one file per component, each covering current implementation (or "not started"), interface/data contract, what it's blocked by, what it blocks, what it's safe to build in parallel with, known issues, and acceptance criteria. See `specs/README.md` for the exact template.

Read in that order: PRD → ROADMAP → specs.

**Scope note (2026-10-12):** the Data Science side now rates four independent city points (`AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND`, `EL_PASO`) and has retired transmission corridors, corridor minima and bottleneck points. These docs describe a per-city dashboard and API. The contract is `docs/data-science/decisions/point_scope.md`; read it before the PRD. Result names and shapes in these docs were read from the migrated backend on 2026-10-12; DS has not formally frozen them, so confirm before building against them. See `PRD.md` §1.1.

## Index

| Document | What it contains |
|---|---|
| [`PRD.md`](PRD.md) | Purpose and scope (including the per-city rating unit), users, functional requirements `SW-F1`–`SW-F12` (each traced to `Project Definition.md` / `System Design Report.md`), non-functional requirements `SW-NF1`–`SW-NF9`, open decisions `OD-1`–`OD-13`, data contract requests to the DS sub-team, observed characteristics of existing DS output, and documentation discrepancies |
| [`ROADMAP.md`](ROADMAP.md) | Four phases, dependency graph, blocker findings, and parallelization summary |
| [`specs/README.md`](specs/README.md) | Component index, spec template, and the blocked-by/blocks consistency table |

### Component specs

| ID | Component | Phase | Effort | Status | Spec |
|---|---|---|---|---|---|
| F1 | Data Access & API Layer | 1 | M | Not started | [`specs/F1-data-access-api.md`](specs/F1-data-access-api.md) |
| F2 | Dashboard Shell & Location Selection | 1 | M | Not started | [`specs/F2-dashboard-shell.md`](specs/F2-dashboard-shell.md) |
| F3 | Line Status & Current Conditions View | 2 | S | Not started | [`specs/F3-line-status.md`](specs/F3-line-status.md) |
| F4 | DLR vs. Static Capacity Chart | 2 | M | Not started | [`specs/F4-dlr-vs-static-chart.md`](specs/F4-dlr-vs-static-chart.md) |
| F5 | Forecast & Trusted-Duration View | 3 | M | Not started (externally blocked) | [`specs/F5-forecast-trusted-duration.md`](specs/F5-forecast-trusted-duration.md) |
| F6 | Anomaly & Fallback Status Indicators | 3 | M | Not started (externally blocked) | [`specs/F6-anomaly-fallback-status.md`](specs/F6-anomaly-fallback-status.md) |
| F7 | PSS/E Output Integration | 4 | L | Not started (contract undefined) | [`specs/F7-psse-integration.md`](specs/F7-psse-integration.md) |
| F8 | Integration, E2E & Usability Validation | 4 | M | Not started | [`specs/F8-integration-validation.md`](specs/F8-integration-validation.md) |

### Other documents in this directory

- [`specs/api-contract.md`](specs/api-contract.md) — a reference describing the per-city data shapes the DS backend produces that an `api/` layer would serve. It is not one of the eight component specs and carries no phase or status.
- [`guides/`](guides/) — developer how-to guides (getting started, architecture, configuration, development, testing) for the Software sub-team. These describe the repo as it is today and are maintained separately from the PRD/ROADMAP/specs above.

## Where to start

1. Resolve the two gating decisions first: confirm what remains of OD-1 (a location is now a city; the station-to-city mapping and any per-station view are still open) and decide the front-end stack (OD-11).
2. Send the data contract requests in `PRD.md` §8 to the Data Science sub-team — F5 and F6 depend on columns the current export does not carry.
3. Start F1 and F2 in parallel against `data/fixtures/sample_pipeline_output.csv` (the only guaranteed dev data; `outputs/` is gitignored).

## Upstream sources

The requirements are grounded in, and should be kept consistent with: `docs/Project Definition.md`, `docs/System Design Report.md`, `docs/data-science/decisions/point_scope.md`, `docs/data-science/specs/C3-export-visualization.md` (plus C7, C9, C10), `docs/data-science/schema/pipeline_output_v1.md`, and `data/fixtures/sample_pipeline_output.csv`. Where these do not decide something, `PRD.md` §7 lists it as an open decision rather than assuming an answer.

See also: `frontend/README.md` and `api/README.md` for the current (empty) code-side status.
