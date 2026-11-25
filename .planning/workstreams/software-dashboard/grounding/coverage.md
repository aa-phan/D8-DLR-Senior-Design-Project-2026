# Coverage ledger: dashboard docs grounding

What was grounded, against what, and how far it got. Findings are in [`findings.md`](findings.md); open questions in [`unknowns.md`](unknowns.md).

**Code at:** `feature/dashboard` `1db9b18` (frontend, migrations and backend unchanged since). **Date:** 2026-11-25.

## Surfaces

| Surface | Count | Command |
|---|---|---|
| Documents in scope | 7 | `wc -l`: software-team-handoff.md 162, rest-api.md 281, PRD.md 177, frontend/README.md 11, DASHBOARD-REQUIREMENTS.md 484, COLUMN-GUIDE.md 222, REQUIREMENTS.md |
| Frontend routes | 3 | `frontend/frontend/urls.py`: `""`, `history/`, `forecast/` |
| Env vars the frontend reads | 3 names | `grep getenv frontend/frontend/settings.py`: `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_PUBLISHABLE_KEY` |
| Database objects the docs name | 5 views | `grep -liE "view ... <name>" supabase/migrations/*.sql`; all 5 defined |
| Database objects the frontend reads | 2 of 5 | `grep` of `frontend/homepage/views.py`: `latest_rating`, `day_ahead_upcoming` |
| Migrations | 8 | `ls supabase/migrations \| wc -l` |
| `api/` | README only | `ls api` |
| Requirement IDs | 43 in DASHBOARD-REQUIREMENTS.md, 43 in REQUIREMENTS.md, same set | `grep -oE '(OVR\|STA\|HEAD\|FRESH\|LBL\|DET\|UI\|DATA\|DEF)-[0-9]+' \| sort -u` and `diff` |

## Per-document status

Each document was grounded by one agent and its findings checked by a second agent that had not seen the first one's reasoning. Status is "reviewed" when the second reader finished.

| Document | Kind | Claims checked | Status | Result |
|---|---|---|---|---|
| docs/integration/software-team-handoff.md | Descriptive, quoting the contract | 46 | Reviewed | 10 confirmed, 7 overstated (corrected or dropped in findings) |
| frontend/README.md | Descriptive | in the 46 above | Reviewed | Stale throughout: describes an unstarted React app |
| docs/integration/rest-api.md | Normative contract | about 70 | Reviewed | 3 drift, 2 contract-wording issues, 1 claim wrong ("exactly four rows"); 6 code and example violations |
| docs/frontend/PRD.md | Normative, partly superseded | 42 | Reviewed | Partly superseded (banner now present); SW-* rules stand; 8 violations by the code |
| DASHBOARD-REQUIREMENTS.md, COLUMN-GUIDE.md, REQUIREMENTS.md | Normative | 46 schema and constant claims, 43 requirement IDs | Reviewed | Schema, counts, gate codes and worked examples hold; 2 minor drift items; 1 architecture decision |

## Requirement status in the Django app

43 requirements: **6 met, 8 partial, 9 violated, 19 missing, 1 deferred.** Three of the "met" (UI-11, UI-12, DATA-07) hold only because nothing that could break them is built yet. The violated rows marked D1 depend on the architecture decision in the findings.

| ID | Status | Evidence | Note |
|---|---|---|---|
| OVR-01 | Missing | `views.py:44-72`, `home.html:21-38` | One city at a time through a selector; no four cards |
| OVR-02 | Missing | `views.py` | No summary line |
| OVR-03 | Missing | `home.html` | No cards to open |
| STA-01 | Violated | `views.py:11-12` | Text only, no icon, uses the forbidden words "dynamic" and "static" |
| STA-02 | Partial | `views.py:66-68` | Stale row shows the static amps; no "Last updated"; missing row shows "-" |
| STA-03 | Violated | `views.py:20`, `:66-70` | `status`, `fallback_gates`, `exhausted` never read; a fallback row shows as dynamic with no reason |
| STA-04 | Missing | `views.py:70` | No comparison with normal |
| STA-05 | Missing | `views.py:20` | `is_provisional` fetched, never shown |
| HEAD-01 | Missing | `views.py:68-70` | No percentage, no "per wire" |
| FRESH-01 | Partial | `views.py:71`, `home.html:48` | Age shown as "N minutes"; no "Current until"; `valid_time` not selected |
| FRESH-02 | Violated (D1) | `home.html:5-8` | No client-side age; offline reload shows a browser error page |
| LBL-01 | Missing | `views.py:20` | No estimate label; `rating_basis` not read |
| DET-01 | Missing | `views.py:20` | No weather |
| DET-02 | Missing | `views.py:20` | No next-hour forecast |
| DET-03 | Missing | `views.py:74-93`, `history.html:47` | History page has no data, no chart, and crashes |
| DET-04 | Partial | `views.py:28-41`, `forecast.html:40` | Day-ahead table exists; no label, no "Outlook delayed", UTC times, limit 4 |
| DET-05 | Missing | `views.py:20` | `rating_basis` not read |
| DET-06 | Missing | none | No Technical details section |
| UI-01 | Missing | `style.css` | No card layout |
| UI-02 | Missing | `home.html` | No hierarchy |
| UI-03 | Missing | none | Five-second test not run; needs the overview |
| UI-04 | Violated | `home.html:5-8` | Full page reload every 60 s when a city is selected |
| UI-05 | Missing | `style.css` | No status roles |
| UI-06 | Violated | `views.py:68`, `:70` | Three decimals, truncated; spec asks for whole amps with a separator |
| UI-07 | Violated | `forecast.html:40`, `home.html:48` | UTC, not Central Time; age not in "12 min ago" form |
| UI-08 | Partial | `views.py:50-51` | Defaults to "-", not 0; shows "- A"; no "No data" hover |
| UI-09 | Missing | none | No chart |
| UI-10 | Met | `forecast.html` | Day-ahead on its own page |
| UI-11 | Met (nothing built) | grep: no animation | Reduce-motion not handled |
| UI-12 | Met (nothing built) | grep: no audio or dialogs | |
| UI-13 | Violated (D1) | none | No loading state under server rendering |
| UI-14 | Violated (D1) | `views.py:24-25`, `:62-64` | Database failure shown as a fallback; no banner, no last values |
| UI-15 | Partial | `views.py:62-64` | City with no row shows "-", not "No rating received yet" |
| UI-16 | Missing | grep: no `aria-`, `role=` | Only one `<label>` |
| DATA-01 | Violated | `supabase_utils.py:10` | Sends `Authorization: Bearer` |
| DATA-02 | Partial (D1) | `views.py:16-22` | 6 of the 10 columns, per page load, not a 2-minute poll |
| DATA-03 | Missing | none | `city_rating` never read |
| DATA-04 | Partial (D1) | `views.py:28-41` | `day_ahead_upcoming` read; `day_ahead_status` never read; no 10-minute refresh |
| DATA-05 | Partial (D1) | `home.html:8` | No `assert_fresh` call; 60 s reload per viewer, no shared throttle |
| DATA-06 | Met | `views.py` | One city at a time, no cross-city arithmetic |
| DATA-07 | Met (nothing built) | `views.py:66-70` | Only formatting |
| DATA-08 | Met | `views.py:20`, `:34` | Explicit selects; extra columns ignored |
| DEF-01 | Deferred | none | `latest_grid_study` unused; deferred by design |

## Not covered

- The live database, the running app's rendered layout and contrast, and the frontend tests: see [`unknowns.md`](unknowns.md).
- No document was edited. The PRD supersession banner on this branch came from the workstream's own commits, not from this grounding.
