# Requirements: City Detail View

The requirement text, reasoning and "Done when" tests live in
[`../software-dashboard/docs/DASHBOARD-REQUIREMENTS.md`](../software-dashboard/docs/DASHBOARD-REQUIREMENTS.md).
This list only says which of them this workstream owns; the checklist of record is
[`../software-dashboard/REQUIREMENTS.md`](../software-dashboard/REQUIREMENTS.md).

| ID | Requirement (short) | Phase |
|---|---|---|
| DET-01 | Why the rating is what it is: three weather drivers with fixed explanations | 1 |
| DET-02 | Next-hour forecast text by `forecast_status` | 1 |
| DET-05 | About this rating: the full `rating_basis` | 1 |
| DET-06 | Technical details, collapsed, 22 fields | 1 |
| DATA-03 | Read the city's `city_rating` window; refresh every 10 minutes and on a newer hour | 1 |
| DET-03 | History chart, 24 hours with a 7-day switch | 2 |
| DET-04 | Day-ahead outlook with band, label and "Outlook delayed" | 2 |
| DATA-04 | Read `day_ahead_upcoming` and `day_ahead_status` on open and every 10 minutes | 2 |
| UI-09 | Chart rules | 2 |
| UI-10 | History and outlook kept visually separate | 2 |

Rules every phase follows, owned elsewhere: the city-state rules and the browser script from
software-dashboard Phase 1; the plain-language rule (DASHBOARD-REQUIREMENTS.md ch. 2.3); units and
times (UI-06, UI-07); DATA-06 and DATA-07; and the ISO 9241 traceability list.
