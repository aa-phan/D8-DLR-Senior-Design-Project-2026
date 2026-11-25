# Findings: dashboard docs against the code

Findings from grounding the dashboard-facing documents against `feature/dashboard` at `1db9b18` (frontend, migrations, backend), 2026-11-25. Each line is a suspicion or a mismatch for the owner to classify; nothing here was fixed. Every finding below was checked by a second reader; findings the second reader rejected are left out, and overstated ones are given in their corrected form.

Line numbers in `docs/frontend/PRD.md` are from `1db9b18`. A later commit on this branch added a two-line banner at the top, so lines 3 and below are now two higher.

Kinds used below:

- **Violation**: the code breaks a normative document (contract, PRD rule, requirement). The document stands; the code is what changes.
- **Drift**: a descriptive statement in a document no longer matches the code or schema. The document is what changes.
- **Decision**: the document and the code disagree on design, not on a fact. The owner picks a side.
- **Defect**: something in the code looks broken; no document is involved.

## 1. Decisions for the owner

| # | Question | Evidence |
|---|---|---|
| D1 | The requirements assume the **browser** fetches the database (OD-2, ch. 7 tests read "the browser's network log", 2-minute and 10-minute polls, age ticking offline). The Django app fetches **server-side** and reloads the whole page every 60 s when a city is selected. Until the owner decides, the affected requirements count as violated, not optional. FRESH-02 and UI-14 need browser-side behavior while the database is unreachable, so a purely server-rendered page cannot meet them. Change the requirements (restate OD-2, DATA-02 to DATA-05, FRESH-02, UI-13 and UI-14 for server rendering) or change the architecture (add a small browser-side layer)? | DASHBOARD-REQUIREMENTS.md:97, :376, :213-214, :358-362, :378-387; `frontend/homepage/supabase_utils.py:13-22`; `frontend/homepage/templates/home.html:5-8` |
| D2 | Framework is settled in code (Django 5.2) but still open in the docs (PRD OD-11, DASHBOARD-REQUIREMENTS Q6). Record Django as the decision? | PRD.md:116; DASHBOARD-REQUIREMENTS.md:454; `frontend/requirements.txt` |
| D3 | With server rendering, the 60 s reload per open tab means database requests grow with viewers. DATA-05 needs a per-deployment rule (server cache or throttle), not a per-browser one. | DASHBOARD-REQUIREMENTS.md:386-387; `frontend/homepage/views.py:16-26` |
| D4 | The env var name: docs say `SUPABASE_PUBLISHABLE_KEY`; the code reads `SUPABASE_KEY` first and falls back. Drop the `SUPABASE_KEY` read so the code matches the documented name? | software-team-handoff.md:11-12; `frontend/frontend/settings.py:19-21` |

## 2. Code violations (dashboard work)

The full per-requirement status is in [`coverage.md`](coverage.md). The violations of the contract and the PRD:

| # | Rule | What the code does | Code |
|---|---|---|---|
| V1 | Key in `apikey` header only, never `Authorization` (rest-api.md:15; handoff:13; DATA-01) | Sends `Authorization: Bearer <key>` as well; headers built at import time, so a missing key sends `Bearer None` | `frontend/homepage/supabase_utils.py:7-11` |
| V2 | Show `rating_basis` wherever a value is shown (rest-api.md:9, :67; handoff:97; LBL-01, DET-05) | Never selects or shows it | `frontend/homepage/views.py:20` |
| V3 | Branch on `is_provisional` (handoff:97; STA-05) | Selects it, never reads it | `frontend/homepage/views.py:20` |
| V4 | A fallback is never hidden (handoff:98; STA-03; PRD SW-NF1) | Never selects `status`, `fallback_gates` or `exhausted`; a non-stale fallback row shows as "using Dynamic Line Ratings" with no reason | `frontend/homepage/views.py:20`, `:66-70` |
| V5 | A stale row is shown as stale (rest-api.md:89, :97) | Shows the static rating under "reverted to Static Line Ratings"; a visible change, but labelled as a fallback, not as late data (partial) | `frontend/homepage/views.py:66-68` |
| V6 | Feed loss is not masked (PRD SW-NF1; UI-14) | A failed request returns None, the same as no row; page says "reverted to Static Line Ratings" with "-" and no static value | `frontend/homepage/views.py:24-25`, `:62-64` |
| V7 | No-data state is neutral (PRD SW-NF1) | With no city selected, the page says "Currently using Dynamic Line Ratings" | `frontend/homepage/views.py:47-48`, `:79` |
| V8 | Show the day-ahead `label` with every day-ahead value; `day_ahead_status` badge (rest-api.md:180; handoff:119-120; DET-04) | `label` selected but not rendered; `band_source` not selected; `day_ahead_status` never read; times shown in UTC, not Central Time (UI-07) | `frontend/homepage/views.py:34`; `frontend/homepage/templates/forecast.html:40`, `:50-54` |
| V9 | Errors are normal states, not crashes (rest-api.md:129-131; PRD SW-NF5) | Forecast page raises TypeError when the fetch fails | `frontend/homepage/views.py:39-40`, `:111` |
| V10 | Dynamic shown beside static (PRD SW-F2) | Shows one number: static only when stale, dynamic otherwise; the row carries both | `frontend/homepage/views.py:66-70` |
| V11 | Plain-language rule: no "dynamic"/"static" wording (DASHBOARD-REQUIREMENTS.md:53-60; STA-01) | Labels read "using Dynamic Line Ratings" / "reverted to Static Line Ratings" | `frontend/homepage/views.py:11-12` |
| V12 | No secrets in the repo (PRD SW-NF6) | Django `SECRET_KEY` committed, with `DEBUG = True` | `frontend/frontend/settings.py:31`, `:34` |
| V13 | The four read examples must show `rating_basis` (rest-api.md:9, :67) | None of the three examples selects it | `docs/integration/examples/curl.sh:39`, `supabase_js.mjs:44`, `read_ratings.py:62-63` |

## 3. Document drift

| # | Document line | Says | Code or schema says | Fix |
|---|---|---|---|---|
| R1 | rest-api.md:16 | Readable objects "and nothing else" (no `latest_grid_study`) | Granted to anon at `supabase/migrations/20261116200000_expose_latest_grid_study.sql:69`; the doc lists it at :29 and :137 already | Add it to the :16 list |
| R2 | rest-api.md:25 | Filters work on every column of `latest_rating` for `city_rating` | `age_minutes`, `is_stale`, `is_provisional` are computed in the view (`20261026195124_expose_latest_rating.sql:80-83`) | "every stored column (the first 31)" |
| R3 | rest-api.md:24, :27, :89; DASHBOARD-REQUIREMENTS.md:76 | "exactly four rows" | `distinct on (city)`: one row per city that has data (`20261026195124_expose_latest_rating.sql:48,84`) | "up to four rows, one per city with data" |
| R4 | rest-api.md:98, :102-104, :110 | AUSTIN falls back while conductor data is pending; Phase 7 "may deploy around 2026-11-01" | The doc itself says the go was signed 2026-11-02; :110 is a past date stated as a plan | State the current AUSTIN status from a source; remove delivery-history wording |
| R5 | rest-api.md:5, :16, :26, :36-38, :69 | "once the owner applies ...", "before the ... migration it was ...", phase names | House rules: no delivery history, no previous behavior | Restate as current fact |
| H1 | software-team-handoff.md:52-59 | "What you can read" omits `latest_grid_study`; :91 says PSS/E results have no agreed interface | View exists and is granted (`20261116200000_expose_latest_grid_study.sql:69`) | Add the view, marked preliminary |
| H2 | software-team-handoff.md:3 | "the Flask layer (`api/`)" | `api/` holds only a README marked "Not started" | Note that the Flask layer is planned with no code |
| H3 | software-team-handoff.md:154 | api/README, frontend/README and the F1 spec read `outputs/` CSV and the fixture | api/README.md:9 and the F1 spec do; frontend/README.md:9 says only "backend's output files" | Name api/README and F1; frontend/README is the looser reference |
| F1 | frontend/README.md:3 | "Not started, structural placeholder" | A Django app with three pages exists | Describe the Django app |
| F2 | frontend/README.md:7 | "Planned stack: React" | Django 5.2 (`frontend/requirements.txt`) | Say Django |
| F3 | frontend/README.md:9 | Reads `api/` or backend output files; lists DLR-vs-static charts, anomaly status, trusted-duration windows | Reads Supabase REST directly (`frontend/homepage/supabase_utils.py:14`); has a rating and age, a history stub, a day-ahead table | State what exists |
| F4 | frontend/README.md | No setup or env section | Needs `requirements.txt`, two env vars, `manage.py runserver` | Add a short run section |
| P1 | docs/frontend/PRD.md:4 | "Nothing described here has been built" | `frontend/` is a Django app; `api/` is still README only | Correct the frontend half |
| P2 | docs/frontend/PRD.md:2, :12, :15-16 | React dashboard and Flask BFF | Django server-rendered, no BFF | Say Django; keep the SW-NF9 Bill of Materials quote at :98 and note the stack differs |
| P3 | docs/frontend/PRD.md:95 | SW-NF6 credential list omits the Supabase key | `frontend/frontend/settings.py:19-21` | Add it, stated as read-only and server-side |
| C1 | COLUMN-GUIDE.md:45 | Checks run in table order, EXHAUSTED last | EXHAUSTED is decided before G1 and the monitor never runs with it (`backend/city_rating.py:395-405`) | Say so |

The PRD supersession banner the second reader asked for is already on this branch (it came in with the workstream commits), so it is not listed.

## 4. Code defects

| # | Defect | Code |
|---|---|---|
| X1 | History page always crashes: `{% url '' %}` has no matching route (NoReverseMatch, confirmed by running it) | `frontend/homepage/templates/history.html:47` |
| X2 | History view fetches a rating and discards it; the page shows only "-" | `frontend/homepage/views.py:91` |
| X3 | `Decimal(None)` raises when a stale row has no static rating, giving a 500 page | `frontend/homepage/views.py:68` |
| X4 | "Rounded to the nearest thousandth" but the code truncates (`ROUND_DOWN`); UI-06 asks for whole amps with a thousands separator | `frontend/homepage/templates/home.html:44`, `history.html:37`; `frontend/homepage/views.py:68`, `:70` |
| X5 | The same age value is labelled "Age of Rating ... minutes" on home and "Trusted Duration ... s" on history; the variable is named `trusted_duration` | `frontend/homepage/views.py:71`; `home.html:48`; `history.html:41` |
| X6 | Debug `print` left in the forecast view | `frontend/homepage/views.py:109` |
| X7 | Unused imports `redirect`, `HttpResponse`, `time` | `frontend/homepage/views.py:1`, `:2`, `:6` |
| X8 | `<script>` and `<link>` sit before `<!DOCTYPE>` and outside `<html>` | `frontend/homepage/templates/home.html:1-10` |
| X9 | `ALLOWED_HOSTS = []` and `db.sqlite3` committed; `requirements.txt` is UTF-16 with CRLF | `frontend/frontend/settings.py:36`; `frontend/db.sqlite3`; `frontend/requirements.txt` |
| X10 | A None `age_minutes` renders as "None minutes" | `frontend/homepage/views.py:71` |
