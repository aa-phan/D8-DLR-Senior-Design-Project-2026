# Unknowns

What the grounding of the dashboard docs could not settle, and what was checked before stopping. Each entry is a starting point for the next attempt.

| # | Question | What was checked | How to settle it |
|---|---|---|---|
| U1 | Does supabase-js send an `Authorization` header as well as `apikey`? rest-api.md:15 says it sends `apikey` only. | `docs/integration/examples/supabase_js.mjs:39` only calls `createClient(url, key)`; nothing in the repo shows the headers it sends. | Read the supabase-js source for the pinned version, or capture one request. |
| U2 | Is the 503 body key from `rpc/assert_fresh` `details` (the doc) or `detail` (the SQL)? | The migrations raise with SQL `detail` (`20261026195124_expose_latest_rating.sql:176`, `20261108120100_expose_day_ahead_forecast.sql:209`); PostgREST normally maps it to a JSON `details` key. No live response is in the repo. | One live call to `rpc/assert_fresh` while a city is late. |
| U3 | PostgREST behavior the contract states: 1,000-row cap, 206, PGRST202/205/116, 401/403 42501, `Prefer`/`Range` handling. | Not in the repo; no live call made. | Live calls against the project, read-only. |
| U4 | Is AUSTIN still falling back often, and is its conductor data still pending (rest-api.md:98)? | No runtime evidence in the migrations or code. | Query `city_rating` for AUSTIN's `status` share over the last week. |
| U5 | Were 19 grid-study runs written on 2026-11-11 and 2026-11-12 (DASHBOARD-REQUIREMENTS.md:441)? | Runtime data; not queried. | Count `psse_run` rows by `solver` and date. |
| U6 | Does stored `rating_basis` still contain "provisional" in older rows? | `backend/config.py:439-449` at HEAD does not contain the word; stored rows not queried. | Select distinct `rating_basis` from `city_rating`. |
| U7 | Is the full set of `detector_signal` values the three that COLUMN-GUIDE.md:93 lists? | Only `_check_against_rolling_baseline` confirmed (`backend/anomaly_detector.py:26`, `:240`). | Grep the backend for every value written to `detector_signal`. |
| U8 | Does Appendix E of the System Design Report name React or Flask (frontend/README.md:7, PRD SW-NF9)? | A grep of `docs/System Design Report.md` for React, Flask, Vite and npm matched only "reactive". | Open Appendix E. |
| U9 | Is the live `SUPABASE_KEY` value (if the deployed host sets it) the publishable key and not a stronger one? | `.env` contents are off limits to the grounding; the repo-root `.env` defines only `SUPABASE_PUBLISHABLE_KEY` by name. | The owner checks the deployed host's environment. |
| U10 | Do the chapter references in DASHBOARD-REQUIREMENTS.md:7 match the decisions recorded in the workstream's STATE.md? | STATE.md exists; its decisions list was not compared line by line. | Compare the two. |
| U11 | Rendered layout, contrast and accessibility (UI-01, UI-02, UI-16). | Only a grep of the CSS and templates; nothing rendered or measured. | Run `/gsd-ui-review` once the overview page exists. |
