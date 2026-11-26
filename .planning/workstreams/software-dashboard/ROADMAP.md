# Roadmap: Operator Dashboard

## Overview

The dashboard is a Django app (`frontend/`) that renders pages on the server and adds a small
browser script for the parts that must keep working between server responses: each card's age
keeps counting, a card turns to **Data late** at 90 minutes even when the database cannot be
reached, and values refresh in place. Requirements are in [`REQUIREMENTS.md`](REQUIREMENTS.md)
and [`docs/DASHBOARD-REQUIREMENTS.md`](docs/DASHBOARD-REQUIREMENTS.md); the gap between them and
the code at the start of this roadmap is in [`grounding/coverage.md`](grounding/coverage.md).

The work is split across two workstreams that run at the same time:

- **software-dashboard** (this one): the shared foundation, the four-card overview, and the
  final integration and usability review.
- **[dashboard-detail](../dashboard-detail/ROADMAP.md)** (Allie): the per-city detail view
  (DET-01 to DET-06, DATA-03, DATA-04, UI-09, UI-10). It starts once Phase 1 here delivers the
  data layer. DEF-01 (grid-study results) stays deferred and is in neither workstream.

**ISO 9241.** The course documents require the dashboard to follow ISO 9241 (`docs/Project
Definition.md`, UI Specifications; PRD SW-NF3). The requirements document's design rules (ch. 6)
are written in that spirit but do not cite the standard. Phase 1 writes the traceability list that
maps each ISO 9241 principle to the requirements that carry it (PRD SW-F11), and Phase 3 runs the
usability review against it (PRD SW-F12). Both workstreams build against that list.

### Ordering and gates

- **Phase 1 gates both workstreams.** The data layer, the city-state rules and the browser script
  are shared; building two copies would produce two answers to "is this city late?".
- **The fail-safe fixes come first.** At the start of this roadmap a fallback to the normal rating
  is shown as a dynamic rating (STA-03), which breaks the project's rule that a fallback is never
  hidden. Nothing new ships on top of that.
- **File ownership.** Phase 1 owns the shared data layer and the browser script. The overview owns
  its own templates and views. The detail view lives in its own Django app, so the two workstreams
  do not edit the same files.

## Phases

- [ ] **Phase 1: Foundation and fail-safe** - One data layer, the city-state rules, the browser script for live age and Data late, the crashes and contract breaches fixed, and the ISO 9241 traceability list
- [ ] **Phase 2: Overview page** - Four city cards with state, headline percentage, freshness and the estimate label, readable in five seconds
- [ ] **Phase 3: Integration and usability review** - The course test plan run end to end, including the ISO 9241 usability review, with results for the Test and Evaluation Report

## Phase Details

### Phase 1: Foundation and fail-safe

**Goal**: Every page reads the database through one data layer that obeys the contract, decides each city's state by one set of rules, never crashes on a database error, and keeps ages and Data late correct in the browser between server responses.
**Depends on**: Nothing.
**Requirements**: DATA-01, DATA-02, DATA-05, DATA-06, DATA-07, DATA-08, STA-02, STA-03, FRESH-02, UI-04, UI-13, UI-14, UI-15; PRD SW-F11, SW-NF1, SW-NF6
**Success Criteria** (what must be TRUE):
  1. Requests carry the key in the `apikey` header only, read from `SUPABASE_PUBLISHABLE_KEY`; no `Authorization` header is sent, and a missing key stops the app at start-up with a clear message.
  2. One function decides a city's state (Data late, Normal rating in use, Below normal, Weather-based rating) in the order of DASHBOARD-REQUIREMENTS.md ch. 5.2, and fixture tests cover each state, including a fallback row that is not stale.
  3. A database error or an absent city shows an explicit state ("Data unavailable" or "No rating received yet"), never a crash and never a fallback label.
  4. With the network disconnected, a card whose rating passes 90 minutes old turns to Data late within one minute, and a wrong desktop clock does not change any card's state or age.
  5. One shared server cache keeps database requests to at most one per endpoint per 60 seconds, however many tabs are open.
  6. The History and Forecast crashes are fixed, the debug output is gone, and the settings hold no committed secret.
  7. The ISO 9241 traceability list exists and maps each principle the team applies to the requirement IDs that carry it, and the requirements document's ch. 7 states the server-plus-script design (OD-2) in place of browser polling.

**Plans**: TBD

### Phase 2: Overview page

**Goal**: An operator who does not know the system can tell from the overview, in five seconds, which cities are above or below normal, which are on their normal rating, and which have late data.
**Depends on**: Phase 1.
**Requirements**: OVR-01, OVR-02, OVR-03, STA-01, STA-04, STA-05, HEAD-01, FRESH-01, LBL-01, UI-01, UI-02, UI-05, UI-06, UI-07, UI-08, UI-11, UI-12, UI-16
**Success Criteria** (what must be TRUE):
  1. Four cards in the fixed order are visible without scrolling at 1366 by 768, with a summary line that counts states and never combines ratings.
  2. Each card shows its state in words and an icon, the headline as a percentage against normal with amps per wire beneath, "Updated N min ago" and "Current until" in Central Time, and the fixed estimate label.
  3. Each state is identifiable on a greyscale screenshot, and a below-normal rating uses the caution style.
  4. Each card opens its city's detail view by mouse and by keyboard.
  5. The overview passes the ISO 9241 items assigned to it in the Phase 1 traceability list.

**Plans**: TBD

### Phase 3: Integration and usability review

**Goal**: The course test plan for the dashboard is run and recorded: displayed values match their source rows, injected faults produce the documented fail-safe display, and operators interpret ratings and alerts without guidance.
**Depends on**: Phase 2 and the dashboard-detail workstream's last phase.
**Requirements**: UI-03; PRD SW-F12, SW-NF3
**Success Criteria** (what must be TRUE):
  1. A script compares every displayed value with its source row and reports zero mismatches in value, unit label and timezone label.
  2. Injected faults (stale row, fallback, missing status, unreachable database) each produce the documented display.
  3. The five-second test (UI-03) and the ISO 9241 usability review are run with recorded results: task success out of N attempts, the operator response time against a numeric bar the team sets before the test, and each finding filed against a requirement ID.
  4. The dashboard results are ready to replace the placeholders in the Test and Evaluation Report's Software section.

**Plans**: TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation and fail-safe | 0/TBD | Not started | - |
| 2. Overview page | 0/TBD | Not started | - |
| 3. Integration and usability review | 0/TBD | Not started | - |
