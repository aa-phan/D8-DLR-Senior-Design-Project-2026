<!-- generated-by: gsd-doc-writer -->
# F2 — Dashboard Shell & Location Selection

**Phase:** 1 (Foundation) · **Effort:** M · **Status:** Not started.

**Responsibility:** Define how operators will use the dashboard and build the frame every view sits in — operator-workflow and display requirements per ISO 9241 (WBS 4.1.1), layout and alert wireframes (WBS 4.1.2), the preset-location selector (SW-F1), and the cross-cutting presentation rules (units, timezone, status banner slot, shared chart wrapper, empty/error states) that keep panels consistent (SW-NF2, SW-NF3, SW-NF7).

## Current Implementation

None. `frontend/README.md` states the planned stack is React (`System Design Report.md` Appendix E) and that nothing is scaffolded. The only existing design artifact is the mock-up referenced as Figure 2 in `Project Definition.md` (UI Specifications): a location selection, a new dynamic thermal limit with its trusted duration, the current sag, and current weather condition. The mock-up image is embedded in that document and is not extracted into the repo.

## Interface & Data Contract

Not yet designed. It should minimally provide:

- **Design deliverables (no code):** an operator-workflow description (who the operator is, what decisions they make from the dashboard, what an alert must let them do within a time-sensitive situation), a wireframe set (default view, a fallback-active view, a data-unavailable view), and a display-requirements list traceable to ISO 9241's "clarity, consistency, and readability" (`Project Definition.md` Appendix A, item 11).
- **Location selector:** a control populated from F1's location list, restricted to preset entries (no free-text), with a visible selected state and a sensible empty state if the list fails to load. What a "location" is depends on OD-1; the four cities in the I/O table (Austin, Corpus Christi, Midland, El Paso) are the only locations the source documents name.
- **Layout slots** for F3 (status), F4 (chart), F5 (forecast), F6 (status banner and alerts), F7 (PSS/E), so panels are built independently without editing each other's files.
- **Shared presentation rules every panel reuses:** unit labels from `PIPELINE_SCHEMA` (SW-NF2); timezone label and default (OD-7, SW-NF7); a shared time-series chart wrapper (axes, units, null-gap handling, limit line, optional band) that F4 and F5 both use (ROADMAP Finding 8); null/"unavailable" rendering that is visibly different from zero; and the alert/status color-and-text conventions F6 and F3 share.
- **Stack decision record** (OD-11): language, build tool, charting library, data-fetching approach, test frameworks. A short decision note is the deliverable; the choice itself is the team's.

## Blocked by

None internal. Wants **OD-1** (so the selector knows what it selects) and **OD-11** (so scaffolding isn't redone). The wireframe and ISO 9241 analysis work needs neither and can start immediately.

## Blocks

- **F3, F4, F5, F6, F7** — each panel is mounted in the shell and uses its shared presentation rules.
- **F8** — usability review is performed on the shell + panels.

## Parallel-safe with

**F1** — layout and wireframes vs. data layer; the only shared concern is OD-1.

## Known Issues

Concerns inherited from the source documents rather than from existing code:

- **Standards scope is ambiguous.** `Project Definition.md` says the UI should align with ISO 9241 plus IEEE 2030.2, IEEE 1815 and IEEE C37.118; `System Design Report.md` Appendix A lists ISO 9241, 1815 and C37.118 but not 2030.2 (PRD OD-10). No source document says what "aligning" means for a dashboard fed from files.
- **"Real-time" is stated but the feed is batch** (PRD OD-2). The shell's design must say what "current" means: the age of the latest row, visibly.
- **The mock-up includes sag**, which has no data producer (OD-4); the layout should not reserve the dashboard's primary real estate for a value that may be dropped.
- **Only one WBS owner** is named for 4.1.1/4.1.2 (LRC, Appendix C); the review step (SW-F12) is assigned to the whole team as Review.

## Acceptance Criteria

- A written operator-workflow and display-requirements document exists, traceable to ISO 9241 and to `Project Definition.md` UI Specifications, and reviewed by the team (WBS 4.1.1).
- Wireframes exist for at least: default state, fallback-active state, data-unavailable/stale state (WBS 4.1.2).
- The shell renders with the fixture-backed location list (via F1) and selecting a location updates a single shared "selected location" that panels read; selection is restricted to preset entries.
- Every unit label shown by the shell and shared components is taken from `PIPELINE_SCHEMA`'s unit strings; every shown time carries a timezone label.
- The shared chart wrapper renders a null gap as a gap, not zero (verified with the fixture and a synthetic null).
- Alert/status conventions are documented once (what a fallback, a warning, and a stale-data state look like) and are what F3 and F6 both import.
- The stack decision note (OD-11) is written down.

## Open Questions

- OD-1, OD-7, OD-10, OD-11 (see PRD §7).
- Does the dashboard need to be responsive/mobile, or desktop control-room only? Not stated anywhere in the sources.
- Accessibility targets beyond ISO 9241 (e.g. WCAG)? Not stated.
