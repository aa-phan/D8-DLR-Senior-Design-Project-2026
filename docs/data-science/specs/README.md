# Component Specs — Index

Ten component specs for the Data Science subsystem. See `../PRD.md` for requirements/why and `../ROADMAP.md` for phase order/dependencies/why-this-order. This file is just the index and the shared template.

| ID | Component | Phase | Effort | Status | File |
|---|---|---|---|---|---|
| C1 | Configuration & Parameterization | 1 | S | Not started | `C1-configuration.md` |
| C2 | Pipeline Data Contract | 1 | S | Partial | `C2-data-contract.md` |
| C3 | Export & Visualization | 1 | S | Implemented, schema informal | `C3-export-visualization.md` |
| C4 | Weather Ingestion | 2 | M | Implemented (Synoptic), provider-locked | `C4-weather-ingestion.md` |
| C5 | Thermal Model (IEEE 738) | 2 | M | Implemented, not importable | `C5-thermal-model.md` |
| C6 | Grid Load Integration (ERCOT) | 2 | M | Implemented | `C6-grid-load-integration.md` |
| C7 | Safety Monitor & Fallback | 3 | M | Partial | `C7-safety-monitor.md` |
| C8 | Corridor Spatial Discretization | 3 | L | Not started | `C8-corridor-discretization.md` |
| C9 | Ampacity Forecasting | 4 | L | Not started | `C9-ampacity-forecasting.md` |
| C10 | Learned Anomaly Detection | 4 | L | Not started | `C10-anomaly-detection.md` |

## Spec Template

Every component spec in this directory follows this structure, so they're scannable and diffable against each other:

- **Header** — ID, phase, effort (S/M/L), build status, one-line responsibility
- **Current Implementation** — files/functions/line refs, or "not started"
- **Interface & Data Contract** — inputs/outputs with units
- **Blocked by** — upstream components that must land first, and specifically why
- **Blocks** — what waits on this component landing (the anti-idle-time field — kept as the exact inverse of every other spec's "Blocked by")
- **Parallel-safe with** — components workable simultaneously without file collision
- **Known Issues** — concrete, file/line-referenced problems in the current code
- **Acceptance Criteria** — testable, drawn from System Design Report §3.3 where applicable
- **Open Questions**

## Consistency Check

The dependency graph in `ROADMAP.md` §3 is the authoritative picture. Every "Blocked by" entry in a spec must have a matching "Blocks" entry in the upstream component's spec, and vice versa. If you edit one, edit the other.
