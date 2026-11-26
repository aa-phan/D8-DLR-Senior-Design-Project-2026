# Roadmap: City Detail View

## Overview

The per-city detail view of the operator dashboard, built by Allie alongside the
[software-dashboard](../software-dashboard/ROADMAP.md) workstream. Requirements come from
[`../software-dashboard/docs/DASHBOARD-REQUIREMENTS.md`](../software-dashboard/docs/DASHBOARD-REQUIREMENTS.md)
ch. 5.6 and ch. 7; that document wins where this roadmap and it disagree. The plain-language
meaning of every column is in
[`../software-dashboard/docs/COLUMN-GUIDE.md`](../software-dashboard/docs/COLUMN-GUIDE.md).

**Starts after** software-dashboard Phase 1, which delivers the shared data layer, the city-state
rules, the browser script for live age and Data late, and the ISO 9241 traceability list. Build
on those; do not write a second copy of any of them.

**Where the code goes.** The detail view is its own Django app in `frontend/` (for example
`frontend/citydetail/`), with its own views, templates and URL include. The shared data layer and
the browser script belong to software-dashboard; changes to them go through that workstream so the
two never edit the same file.

**ISO 9241.** Each phase passes the ISO 9241 items the traceability list assigns to the detail
view. The usability review itself runs in software-dashboard Phase 3 and covers both workstreams.

## Phases

- [ ] **Phase 1: Detail view and current conditions** - The city's state, the weather behind its rating, the next-hour forecast, "About this rating" and Technical details
- [ ] **Phase 2: History and day-ahead outlook** - The 24-hour and 7-day rating chart and the day-ahead outlook with its labels and delay notice

## Phase Details

### Phase 1: Detail view and current conditions

**Goal**: From a city card, the operator opens a page that explains why the rating is what it is, what the next hour looks like, and where the number comes from.
**Depends on**: software-dashboard Phase 1.
**Requirements**: DET-01, DET-02, DET-05, DET-06, DATA-03
**Success Criteria** (what must be TRUE):
  1. The page opens with the same state, headline and freshness as the city's card, using the shared state rules.
  2. The three weather drivers show in °F, mph and W/m² with their fixed explanations; empty readings show "No weather reading" and no zeros.
  3. The next-hour forecast text follows `forecast_status` (ok, cold_start, failed or empty), and no number appears for cold_start or failed.
  4. "About this rating" equals the newest row's `rating_basis` character for character, and Technical details is collapsed on first open and lists all 22 fields.
  5. The page reads the city's `city_rating` rows through the shared data layer and refreshes every 10 minutes and when the overview sees a newer hour.

**Plans**: TBD

### Phase 2: History and day-ahead outlook

**Goal**: The operator can see how the city's rating moved over the last day or week, and what the planning estimate for tomorrow is, without mistaking either for the current rating.
**Depends on**: Phase 1.
**Requirements**: DET-03, DET-04, DATA-04, UI-09, UI-10
**Success Criteria** (what must be TRUE):
  1. The history chart's points equal the `city_rating` rows for the city and the chosen window (24 hours or 7 days), following the chart rules of UI-09.
  2. The day-ahead outlook lists every upcoming row for the city with its band, the percentage against the normal rating, the time in Central Time, and the label "Planning estimate, not validated. Does not affect the current rating."
  3. "Outlook delayed" appears when `day_ahead_status.is_late` is true.
  4. History and the day-ahead outlook are visually separate, so neither is read as the other.
  5. The existing `/history/` and `/forecast/` pages are replaced by the detail view or redirect to it.

**Plans**: TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Detail view and current conditions | 0/TBD | Not started | - |
| 2. History and day-ahead outlook | 0/TBD | Not started | - |
