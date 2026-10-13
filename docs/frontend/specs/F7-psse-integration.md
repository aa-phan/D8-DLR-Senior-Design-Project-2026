<!-- generated-by: gsd-doc-writer -->
# F7 — PSS/E Output Integration

**Phase:** 4 (Integration & Validation) · **Effort:** L (largest unknown — no interface exists) · **Status:** Not started — blocked on an undefined cross-team contract.

**Responsibility:** Display PSS/E simulation outputs on the dashboard (WBS 4.2.2 "Connect PSS/E simulation outputs to dashboard"; SW-F10) so the operator can see grid-feasibility context for the dynamic rating — for example N-1 contingency results, or the minimum-dispatch outcome (`System Design Report.md` §3.2: "dispatched capacity ... the minimum of the DLR thermal limit and the voltage stability limit"). The source documents name the task but not its content.

## Current Implementation

None, and no interface description exists anywhere in the repo for PSS/E → dashboard. The nearest artifact is DS's informal note on the opposite direction, `docs/data-science/decisions/pss_e_handoff.md` (DS → PSS/E: a predicted ampacity, with its confidence band, evaluated by Power Systems against grid conditions). That note records that the file format, cadence, fields and granularity are all "still undefined" and explicitly "not yet confirmed with the Power Systems sub-team".

## Interface & Data Contract

Not designed, and should not be guessed. A contract must minimally state, in agreement with the Power Systems sub-team:

- **Which PSS/E outputs reach the dashboard** — candidates the source documents mention: N-1 contingency thermal/voltage violations (`System Design Report.md` §3.2, §3.3 Power Systems Subsystem), the minimum dispatch rule's result (DLR thermal vs. voltage-stability limit), PV-curve / voltage-stability margin outcomes, reactive-power exhaustion results. None is stated as a dashboard requirement.
- **Format and transport** — file drop, shared directory, PSS/E Python API (`System Design Report.md` §3.1 chose PSS/E for its Python API), or something else.
- **Granularity and cadence** — per line, city, or bus; per run, hourly, or on demand; and how it lines up with F1's location model (OD-1).
- **Units** — all values must come with explicit units per SW-NF2; the dashboard cannot assume DS's `PIPELINE_SCHEMA` covers PSS/E quantities.
- **Ownership of the safety logic** — PSS/E feasibility judgment belongs to Power Systems (per the DS handoff note); the dashboard displays it, like all else, without recomputing (SW-NF4).

If the team decides the dashboard has no PSS/E view, this component is closed as "out of scope" and `System Design Report.md` WBS 4.2.2 is updated; recording that is a valid outcome.

## Blocked by

**F1** and **F2** (internal). **External:** a Power Systems ⇄ DS ⇄ Software interface contract (OD-9) — nothing to build before it exists.

## Blocks

**F8**, softly — only F8's PSS/E leg ("triggers appropriate contingency checks, and displays the updated rating", `System Design Report.md` §3.3 Full System Integration) waits on this. F8's other legs do not.

## Parallel-safe with

**F3**, **F4**, **F5**, **F6** — no shared files. The requirements conversation with Power Systems costs no build time and can run in parallel with everything.

## Known Issues

- **No contract exists** for any PSS/E-related handoff, in either direction (`pss_e_handoff.md`).
- **WBS/LRC assigns 4.2.2** with Power Systems members in support (Appendix C) but names no deliverable format.
- **Unclear whether PSS/E consumes DS output at runtime or in batch** — which determines whether there is a live feed to display at all.
- **Possible mismatch with the dashboard's location model:** PSS/E outputs are per network element, while F1's location is a city (a single rating point per city; station-level views still open, OD-1). There is no corridor to map PSS/E results onto.

## Acceptance Criteria

Deferred until the contract exists. Provisional, to be replaced:

- A written interface contract, agreed by Power Systems, DS and Software, exists in `docs/` (format, fields with units, cadence, granularity), with a sample fixture so F7 can be built without PSS/E running.
- The dashboard shows the agreed PSS/E fields for the selected location alongside the DLR values, each with units and a timestamp, and shows an explicit "PSS/E results not available" state when absent (never blank-as-normal).
- Displayed PSS/E values equal the source file values (no recomputation).
- Alternatively: a recorded team decision that the dashboard has no PSS/E view, and WBS 4.2.2 is amended.

## Open Questions

- OD-9 (the whole contract).
- Does the Power Systems sub-team need the dashboard at all for the course deliverable, or is PSS/E purely a research-paper input?
- Who from Power Systems is the contact for this? (LRC lists Ben H., Ben M. as support on 4.2.2.)
