# Requirements: Dynamic Line Rating (DLR) System - Operator Dashboard

**Defined:** 2026-11-11
**Core Value:** A grid operator who does not know the system can tell, in five seconds, which
city lines are rated above or below normal, which are on their normal rating, and which have
late data, and a late or untrusted dynamic rating never looks current.

**Scope note:** This workstream belongs to the Software sub-team. It lays out what the dashboard
must do; it does not implement it and does not plan phases. The Software team plans phases with
GSD (`/gsd-discuss-phase`, then `/gsd-plan-phase`) against these requirements. Data Science owns
the database and its contract and does not build the dashboard.

**Who builds it:** the Software sub-team. Framework, charting library, hosting and phase order are
theirs to choose (open questions Q5 and Q6 in the requirements document).

**Read first:**

- [`docs/DASHBOARD-REQUIREMENTS.md`](docs/DASHBOARD-REQUIREMENTS.md) - the requirements in full,
  with the reasoning, a "Done when" test for each, the design rules, the design tools to use
  (ch. 8) and the open questions (ch. 11). Where this checklist and that document disagree, that
  document wins.
- [`docs/COLUMN-GUIDE.md`](docs/COLUMN-GUIDE.md) - every database column in plain language and
  where the dashboard uses it.
- [`docs/integration/rest-api.md`](../../../docs/integration/rest-api.md) - the database contract.

## v1 Requirements

### Overview page (ch. 5.1)

- [ ] **OVR-01**: Four city cards, side by side, fixed order, no selector and no combined card.
- [ ] **OVR-02**: A summary line counts cities per state and names late and below-normal cities;
  it never combines cities' ratings.
- [ ] **OVR-03**: A card opens its city's detail view by mouse and keyboard.

### City states (ch. 5.2)

- [ ] **STA-01**: Each state is shown in words and an icon, not colour alone.
- [ ] **STA-02**: Data late (no row, or older than 90 minutes) shows the normal rating, never the
  old dynamic value.
- [ ] **STA-03**: Normal rating in use shows the plain reason (rules for several, unknown or
  missing codes) and is not styled as an error.
- [ ] **STA-04**: Below normal (rounded percentage -1% or lower) is visibly distinct from
  Weather-based rating and uses the caution style.
- [ ] **STA-05**: A "Provisional" badge appears when `is_provisional` is true.

### Headline, freshness and label (ch. 5.3 to 5.5)

- [ ] **HEAD-01**: The headline is the whole-percent difference from the normal rating, with amps
  beneath (a named exception to the earlier PRD's SW-NF4, ch. 5.3).
- [ ] **FRESH-01**: "Updated X min ago" and, unless late, "Current until" (90 minutes after the
  rating's hour).
- [ ] **FRESH-02**: Age keeps counting from the last poll without trusting the desktop clock, and
  the state turns to Data late on time, even offline.
- [ ] **LBL-01**: Fixed short estimate label on every card; full `rating_basis` in the detail view.

### Detail view (ch. 5.6)

- [ ] **DET-01**: Weather drivers in °F, mph and W/m², with a fixed one-line explanation each.
- [ ] **DET-02**: Next-hour forecast with its range, or a plain "not available" message.
- [ ] **DET-03**: History chart, 24 hours by default, 7 days on request.
- [ ] **DET-04**: Day-ahead outlook, separate, labelled "Planning estimate, not validated".
- [ ] **DET-05**: "About this rating" shows the full `rating_basis`.
- [ ] **DET-06**: Collapsed "Technical details" with the listed diagnostic fields.

### UI design (ch. 6)

- [ ] **UI-01**: Desk monitor first; fits 1366 by 768 without scrolling; stacks cleanly when narrow.
- [ ] **UI-02**: Card hierarchy: state and headline, then amps, then freshness, then label.
- [ ] **UI-03**: Passes the five-second test with non-technical testers.
- [ ] **UI-04**: Updates in place; no layout shift, reordering or counting animation.
- [ ] **UI-05**: Four status roles (blue for weather-based, grey, amber, red for unreachable only);
  WCAG AA contrast.
- [ ] **UI-06**: Number and unit formatting.
- [ ] **UI-07**: Central Time, labelled CST or CDT; relative ages.
- [ ] **UI-08**: Missing values show a dash, never 0.
- [ ] **UI-09**: History chart rules: normal-rating line, shading, gaps, settings-change markers.
- [ ] **UI-10**: Day-ahead outlook kept separate from the history chart.
- [ ] **UI-11**: Nothing blinks or flashes; respects reduced motion.
- [ ] **UI-12**: No sound, pop-ups or acknowledgement in v1.
- [ ] **UI-13**: Loading state with no numbers.
- [ ] **UI-14**: Database-unreachable banner; cards keep ageing.
- [ ] **UI-15**: A city with no row shows Data late with "No rating received yet".
- [ ] **UI-16**: WCAG 2.1 AA, keyboard use and screen-reader state announcements.

### Data access (ch. 7)

- [ ] **DATA-01**: Publishable key only, in the `apikey` header.
- [ ] **DATA-02**: Overview reads selected `latest_rating` columns every 2 minutes.
- [ ] **DATA-03**: Detail view reads the city's `city_rating` window every 10 minutes and when a
  newer hour arrives.
- [ ] **DATA-04**: Detail view reads `day_ahead_upcoming` and `day_ahead_status`.
- [ ] **DATA-05**: Never faster than 60 seconds; no `rpc/assert_fresh`.
- [ ] **DATA-06**: Never combines cities' rating or capacity values; counting cities per state is
  allowed.
- [ ] **DATA-07**: No rating calculation beyond the named display arithmetic.
- [ ] **DATA-08**: Ignores unknown columns.

## Deferred

- **DEF-01**: Grid-study results (usable share of the rating and its limiting factor) per city.
  Blocked on the Data Science owner opening read access to the PSS/E result tables and on a
  first real PSS/E run (ch. 10).

## Out of Scope

| Feature | Reason |
|---------|--------|
| Controls, acknowledgement, triggering runs | The dashboard is read-only |
| Line sag | Nothing in the system calculates it |
| Megawatts as a headline | `rating_mw` is per wire and would mislead (ch. 5.3) |
| Per-station view | The rating unit is the city |
| Shadow-forecast files, CSV exports | The database is the only source |
| Email, text or sound notifications | Not required for v1 |
