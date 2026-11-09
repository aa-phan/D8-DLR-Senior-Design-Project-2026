---
status: complete
phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6
source: [08-01-SUMMARY.md, 08-02-SUMMARY.md, 08-03-SUMMARY.md, 08-04-SUMMARY.md, 08-05-SUMMARY.md, 08-06-SUMMARY.md, 08-07-SUMMARY.md, 08-08-SUMMARY.md, 08-09-SUMMARY.md, 08-10-SUMMARY.md, 08-11-SUMMARY.md, 08-12-SUMMARY.md]
started: 2026-11-09T07:56:28Z
updated: 2026-11-09T09:33:49.688Z
---

## Current Test

[testing complete]

## Tests

### 1. Live day-ahead forecast reads through the public API
expected: Run `! .venv/bin/python -c "import os,dotenv; dotenv.load_dotenv('.env'); os.execvp('bash',['bash','docs/integration/examples/curl.sh'])"`, which loads your .env quietly (nothing from it is printed). It exits 0 and prints the current rating for 4 cities, one city's history, up to 12 upcoming day-ahead rows (at most 3 per city, all in the future), the label "day-ahead-24h; engineering-selection; not-validated", and 4 status rows with none late.
result: pass

### 2. Live consumer check passes, and anonymous writes are refused
expected: Run `! PYTHONPATH=backend .venv/bin/python -c "import os,dotenv,sys; dotenv.load_dotenv('.env'); os.execv(sys.executable,[sys.executable,'backend/day_ahead_verify.py','--check-rest'])"`. It exits 0 and prints "DAY-AHEAD REST OK" with 8 PASS lines: upcoming rows in the future and ordered, 26 columns, four cities none late, the table readable, assert_fresh ok and armed, and an anonymous insert, a write to the view, and a read of pipeline_run all refused.
result: pass

### 3. Live ratings are unaffected by the day-ahead stage
expected: Run `! gh run list --workflow dlr_live.yml --limit 10`. The hourly DLR Live Ratings runs stay green (success) since the day-ahead stage went live on 2026-11-09 at 00:43 UTC, and latest_rating still shows a fresh rating for all 4 cities. The 60-minute G6 ml rating is unchanged; day-ahead values never replace or gate it.
result: pass

### 4. Runbook section 17 reads clearly to the owner
expected: docs/data-science/decisions/dlr_live_runbook.md section 17 (Day-ahead forecast stage) explains in plain English what each outcome means, what to do when the feed is late, and that verify_day_ahead_store.sql is run once before the exposure and verify_exposure.sql after it.
result: pass

### 5. Consumer docs read clearly to a dashboard developer and a PSS/E engineer
expected: The day-ahead sections of docs/integration/software-team-handoff.md, docs/integration/rest-api.md and docs/data-science/decisions/pss_e_handoff.md say clearly: the value is a labelled, higher-error, not-validated forecast; it appears about 18 h before the target, at most 3 targets per city; a further-out target is not yet due, not late; and a 503 with empty missing= and stale= means the ratings are fine but a day-ahead forecast is late.
result: pass

### 6. TEST-band fallback on a live-band query error is the behaviour you want
expected: Review fix WR-01: if the live-band database query fails, band_for keeps the TEST band (source test-split) and logs only the error type, so a forecast is still issued. You agree that this is the right behaviour rather than issuing nothing for that target.
result: pass

### 7. 08-01 D1: Tracer: one AUSTIN target computed from stubbed weather with the hash-verified refit mo...
expected: Tracer: one AUSTIN target computed from stubbed weather with the hash-verified refit model under the production point, banded from the hashed TEST artifact, inserted as dlr_writer on a throwaway Postgres; second insert changes nothing; anon is denied
result: pass
source: automated
coverage_id: D1

### 8. 08-01 D2: Write-side migration: 25 columns in contract order, named CHECKs (grid, run init, horiz...
expected: Write-side migration: 25 columns in contract order, named CHECKs (grid, run init, horizon, method, band, hex hashes, label), RLS, anon and authenticated revoked, writer select and insert only, re-apply safe
result: pass
source: automated
coverage_id: D2

### 9. 08-01 D3: Hashed TEST band artifact: 16 bands (4 cities x 00/06/12/18 UTC, n = 196, empirical 5-9...
expected: Hashed TEST band artifact: 16 bands (4 cities x 00/06/12/18 UTC, n = 196, empirical 5-95% offsets of truth minus ml_cooling_corrected), deterministic bytes, verified against the manifest before parsing
result: pass
source: automated
coverage_id: D3

### 10. 08-01 D4: Due and catch-up rule: grid targets strictly after now and within 24 h minus the public...
expected: Due and catch-up rule: grid targets strictly after now and within 24 h minus the publication lag (3 per hour of the day), missing targets read from the table, a missed target stays due until its own hour
result: pass
source: automated
coverage_id: D4

### 11. 08-01 D5: Shadow parity: CORPUS_CHRISTI, MIDLAND and EL_PASO equal run_once_all_methods exactly; ...
expected: Shadow parity: CORPUS_CHRISTI, MIDLAND and EL_PASO equal run_once_all_methods exactly; AUSTIN equals the same chain with the refit model and production point and differs from the Drake value; frozen paths untouched
result: pass
source: automated
coverage_id: D5

### 12. 08-01 D6: No substitute method: every failure (forecast, anchor, hash refusal, non-finite or non-...
expected: No substitute method: every failure (forecast, anchor, hash refusal, non-finite or non-positive value) is a named DayAheadNotIssued reason with no connection string, and only CoolingCorrectionShadowMethod.predict is ever called
result: pass
source: automated
coverage_id: D6

### 13. 08-02 D1: REQUIREMENTS.md and ROADMAP.md define DAY-01..DAY-09, trace them to Phase 8 as Pending,...
expected: REQUIREMENTS.md and ROADMAP.md define DAY-01..DAY-09, trace them to Phase 8 as Pending, and give Phase 8 five success criteria
result: pass
source: automated
coverage_id: D1

### 14. 08-02 D2: upsert_run accepts day_ahead as a single-column jsonb upsert or alongside a full row; b...
expected: upsert_run accepts day_ahead as a single-column jsonb upsert or alongside a full row; build_run_row never emits it; the 12 pinned columns and jsonb subset are unchanged
result: pass
source: automated
coverage_id: D2

### 15. 08-02 D3: Isolation: crashing, hanging or silent day-ahead children leave exit_code, the city rec...
expected: Isolation: crashing, hanging or silent day-ahead children leave exit_code, the city records and run_log identical to a run without the stage; a failing rating child still gives exit 1
result: pass
source: automated
coverage_id: D3

### 16. 08-02 D4: Order: no day-ahead child starts before the last rating child finished and the exit cod...
expected: Order: no day-ahead child starts before the last rating child finished and the exit code was logged; one child per city in config.LOCATIONS order, cwd REPO_ROOT, unmodified environment (the fault drill blanks only the rating child)
result: pass
source: automated
coverage_id: D4

### 17. 08-02 D5: Shared budget: a city reached with under 60 s left is skipped_budget with no child; a s...
expected: Shared budget: a city reached with under 60 s left is skipped_budget with no child; a started child is killed at min(150 s, remaining); the budget is shared across cities
result: pass
source: automated
coverage_id: D5

### 18. 08-02 D6: Own run-log write: one {run_id, day_ahead} row after the stage counted in day_ahead_run...
expected: Own run-log write: one {run_id, day_ahead} row after the stage counted in day_ahead_run_log, never in run_log; a failing write is counted apart, logged redacted, and leaves exit_code and run_log alone; record_run=False sends nothing
result: pass
source: automated
coverage_id: D6

### 19. 08-02 D7: Redaction and output guards: every stored or printed reason is redacted and cut; the st...
expected: Redaction and output guards: every stored or printed reason is redacted and cut; the step summary gains a separate day-ahead table and keeps the pipeline_run line; ten render_guard cases (five malformed shapes x exit 0 and 1) leave main()'s return equal to the rating exit code and both outputs written
result: pass
source: automated
coverage_id: D7

### 20. 08-03 D1: Hashed TEST artifact is rebuilt byte for byte from the tracked TEST rows; 16 bands, n =...
expected: Hashed TEST artifact is rebuilt byte for byte from the tracked TEST rows; 16 bands, n = 196 each, lower < 0 < upper; every offset equals np.quantile of truth minus ml_cooling_corrected; rows_sha256 equals the rows file hash
result: pass
source: automated
coverage_id: D1

### 21. 08-03 D2: Strict artifact parser and TEST-window guard: wrong schema, method or quantiles, a miss...
expected: Strict artifact parser and TEST-window guard: wrong schema, method or quantiles, a missing city or hour key, a non-finite or unordered offset, a non-positive, fractional or boolean n are each rejected with a message naming the field; the builder refuses a row before 2026-03-18, at or after 2026-09-30, or with a missing value; window bounds equal forecast_test_split_score's
result: pass
source: automated
coverage_id: D2

### 22. 08-03 D3: Anti-peeking: no backend/*day_ahead*.py module names the shadow prediction logs, the sh...
expected: Anti-peeking: no backend/*day_ahead*.py module names the shadow prediction logs, the shadow-log reader, the anchored pair frame or a cut-off-dated cache, and none imports the shadow confirm, eval-core or score modules; no skill statistic is computed
result: pass
source: automated
coverage_id: D3

### 23. 08-03 D4: Live rolling band per city x UTC hour: 59 pairs keep TEST, 60 switch with band_n 60 and...
expected: Live rolling band per city x UTC hour: 59 pairs keep TEST, 60 switch with band_n 60 and pairs_through equal to the newest valid_time, only the newest 120 of 150 are used, offsets equal np.quantile of the residuals, one band's pairs never switch another hour or city
result: pass
source: automated
coverage_id: D4

### 24. 08-03 D5: D-08 filters, straddle rule, residual sign and the no-database path: fallback status, f...
expected: D-08 filters, straddle rule, residual sign and the no-database path: fallback status, fallback flag, exhausted, backfill origin, a different config fingerprint on either row, a different cooling model hash, and a target at or after decision time are each not counted; a live set not bracketing zero keeps TEST and logs why; a forecast always 50 A low gives offsets centred near +50; conn None returns the TEST band
result: pass
source: automated
coverage_id: D5

### 25. 08-04 D1: Catch-up from the table (D-04): only due-minus-existing targets are fetched and inserte...
expected: Catch-up from the table (D-04): only due-minus-existing targets are fetched and inserted, earliest first, each with issued_at equal to the run's decision time; a second run is none_due with no fetch and no model load and leaves the first row unchanged
result: pass
source: automated
coverage_id: D1

### 26. 08-04 D2: Contract with the runner (D-02, D-15): the argv from dlr_live_run.day_ahead_child_argv ...
expected: Contract with the runner (D-02, D-15): the argv from dlr_live_run.day_ahead_child_argv is accepted, the output has exactly the runner's 11 keys, exit 0 whatever the outcome, classify_day_ahead returns issued; a bad city or missing argument is a usage error (2); an unwritable output is exit 1
result: pass
source: automated
coverage_id: D2

### 27. 08-04 D3: No substitute (D-16, D-13a): a missing anchor, a band artifact that does not match the ...
expected: No substitute (D-16, D-13a): a missing anchor, a band artifact that does not match the manifest (before any model loads), a manifest with no entry, a cooling model hash refusal, an unreachable database and one unavailable weather run each publish nothing for the affected targets with a named reason and use no other method
result: pass
source: automated
coverage_id: D3

### 28. 08-04 D4: Redaction (OD-6, T-08-11): a database URL, its password and host, and a provider token ...
expected: Redaction (OD-6, T-08-11): a database URL, its password and host, and a provider token planted in a provider message never appear in the output file, the log or the table; unexpected errors are named by type and redacted; no table column can hold free text
result: pass
source: automated
coverage_id: D4

### 29. 08-04 D5: --no-store never calls supabase_store.connect, uses the TEST band, inserts nothing and ...
expected: --no-store never calls supabase_store.connect, uses the TEST band, inserts nothing and marks dry_run; an out-of-bounds value is still inserted and listed
result: pass
source: automated
coverage_id: D5

### 30. 08-04 D6: Write-side privileges and constraints on local Postgres (D-09, T-08-10, T-08-13): dlr_w...
expected: Write-side privileges and constraints on local Postgres (D-09, T-08-10, T-08-13): dlr_writer inserts and selects, a repeated key keeps the first write, update/delete/truncate fail with 42501; anon and authenticated cannot read (42501); eight bad rows each fail with 23514 on the named constraint; pipeline_run accepts a {run_id, day_ahead} upsert; every migration applies twice
result: pass
source: automated
coverage_id: D6

### 31. 08-04 D7: Text contract of the migration: exactly the 25 contract columns in order, the named CHE...
expected: Text contract of the migration: exactly the 25 contract columns in order, the named CHECKs, RLS, revoke from anon and authenticated, exactly two grants, drop-before-create policy, no update/delete/truncate/password/URL, unit-first comment on every column and pipeline_run.day_ahead, sorts after the soak migration, adds every optional run-log column the writer names
result: pass
source: automated
coverage_id: D7

### 32. 08-04 D8: Owner's store check: verify_day_ahead_store.sql is one read-only SELECT of the 10 pinne...
expected: Owner's store check: verify_day_ahead_store.sql is one read-only SELECT of the 10 pinned checks, all ok on the write-side state; thirteen wrong states (public select grant, column grant, writer update/delete/truncate grant, missing insert, RLS off, empty comment, extra column, dropped key, dropped or retyped run-log column, dropped table) each turn exactly the matching checks false; Phase 6 verify_exposure.sql stays all ok
result: pass
source: automated
coverage_id: D8

### 33. 08-05 D1: A day-ahead problem (tampered, missing or unlisted file, failing load, crash anywhere i...
expected: A day-ahead problem (tampered, missing or unlisted file, failing load, crash anywhere in the tier including sys.exit) is only a ::warning:: line and the pre-flight exits 0; live-model problems still exit 1
result: pass
source: automated
coverage_id: D1

### 34. 08-05 D2: Hash before load: nothing day-ahead is unpickled while a day-ahead hash problem is open...
expected: Hash before load: nothing day-ahead is unpickled while a day-ahead hash problem is open; warning text is escaped onto one line
result: pass
source: automated
coverage_id: D2

### 35. 08-05 D3: One manifest names all 13 artifacts; the four cooling hashes equal the refit and frozen...
expected: One manifest names all 13 artifacts; the four cooling hashes equal the refit and frozen manifests; the eight live entries are unchanged; the committed tree matches offline and the real pre-flight prints both OK lines in a fresh process
result: pass
source: automated
coverage_id: D3

### 36. 08-05 D4: No circular import in either order with forecast_conductor_refit; Phase 5 check-model t...
expected: No circular import in either order with forecast_conductor_refit; Phase 5 check-model tests keep every assertion
result: pass
source: automated
coverage_id: D4

### 37. 08-06 D1: The first-slot check passes on a correct first run (12 rows, all ten checks ok, exit 0)...
expected: The first-slot check passes on a correct first run (12 rows, all ten checks ok, exit 0) and each failure (missing due target, wrong label, wrong weather run age, live-rolling at launch, band hash not in the manifest, cooling hash different, config fingerprint or version not the code's, lead over 18 h, no pipeline_run record, issued list differing from the rows, a city with no row) flips exactly its own check with exit 1; no row since T0 fails first_run_found and every other check
result: pass
source: automated
coverage_id: D1

### 38. 08-06 D2: Read-only and redaction: the session is BEGIN READ ONLY and rolled back, a write inside...
expected: Read-only and redaction: the session is BEGIN READ ONLY and rolled back, a write inside the script's connection raises, the table counts are unchanged; a connection failure carrying the URL, password, host and project reference prints and stores none of them; SUPABASE_DB_URL unset is exit 2 naming only the variable
result: pass
source: automated
coverage_id: D2

### 39. 08-06 D3: The runbook documents the day-ahead stage (due times, catch-up, shared budget, outcomes...
expected: The runbook documents the day-ahead stage (due times, catch-up, shared budget, outcomes, where they are recorded, never changes the exit code), the warning-tier pre-flight, the 13 manifest entries and the D-13 promotion step, and states that '24 h' is the weather run's age with the TEST, shadow and live anchor leads; pinned strings are kept and one new test ties section 17 to the code
result: pass
source: automated
coverage_id: D3

### 40. 08-09 D1: day_ahead_upcoming returns only future targets, ordered by city then valid_time, with e...
expected: day_ahead_upcoming returns only future targets, ordered by city then valid_time, with exactly the 26 contract columns and lead_minutes equal to the ceiling of minutes to the target; past values stay readable in the table
result: pass
source: automated
coverage_id: D1

### 41. 08-09 D2: day_ahead_status always returns four rows with the 7 contract columns; missing_targets ...
expected: day_ahead_status always returns four rows with the 7 contract columns; missing_targets lists exactly the unfilled 00/06/12/18 UTC targets within 12 h; is_late is armed by the first row
result: pass
source: automated
coverage_id: D2

### 42. 08-09 D3: anon and authenticated hold SELECT only on the three day-ahead objects; every write is ...
expected: anon and authenticated hold SELECT only on the three day-ahead objects; every write is refused; one read policy and no write policy; every view column commented
result: pass
source: automated
coverage_id: D3

### 43. 08-09 D4: assert_fresh keeps one signature, its 90-minute rule, 22023 and PT503, and raises PT503...
expected: assert_fresh keeps one signature, its 90-minute rule, 22023 and PT503, and raises PT503 with day_ahead_late= when an armed city is late; 200 body gains day_ahead_armed
result: pass
source: automated
coverage_id: D4

### 44. 08-09 D5: verify_exposure.sql covers the five published objects with 29 checks, all ok on local P...
expected: verify_exposure.sql covers the five published objects with 29 checks, all ok on local Postgres after all six migrations, and each new check turns false under its sabotage
result: pass
source: automated
coverage_id: D5

### 45. 08-10 D1: The day-ahead consumer contract (rest-api.md, the new schema doc, the PSS/E note) carri...
expected: The day-ahead consumer contract (rest-api.md, the new schema doc, the PSS/E note) carries the D-11 label and the owner paragraph verbatim, cites the +23 A / ~1.7% figures as exploratory, says '24 h' is the age of the weather run and a value is issued 0 to 18 hours before its target, and states the band, issue and late rules
result: pass
source: automated
coverage_id: D1

### 46. 08-10 D2: The two new REST column tables equal UPCOMING_COLUMNS and STATUS_COLUMNS and the schema...
expected: The two new REST column tables equal UPCOMING_COLUMNS and STATUS_COLUMNS and the schema doc's table equals TABLE_COLUMNS, column for column, with a type, a unit and a meaning on every row
result: pass
source: automated
coverage_id: D2

### 47. 08-10 D3: day_ahead_verify.py --check-rest passes against healthy post-expose answers (eight chec...
expected: day_ahead_verify.py --check-rest passes against healthy post-expose answers (eight checks, exit 0) and each failure (a past or unordered upcoming row, a missing, extra or reordered column, three cities, a late city, an empty table, assert_fresh 503, day_ahead_armed false or missing, an accepted or RLS-only or bare-401 insert, an accepted or bare-403 view write, a readable run log) flips exactly its own check with exit 1
result: pass
source: automated
coverage_id: D3

### 48. 08-10 D4: The check never prints or stores the URL, host, project reference or key (an error body...
expected: The check never prints or stores the URL, host, project reference or key (an error body and a connection failure that echo them, and a hostile served value), refuses a secret key and a missing variable with exit 2 before any request, sends the key in apikey only, and writes only the two year-2000 probes; an accepted insert prints the sentinel recovery SQL
result: pass
source: automated
coverage_id: D4

### 49. 08-10 D5: Runbook section 14 states the day-ahead alarm clause, section 16 describes the post-exp...
expected: Runbook section 14 states the day-ahead alarm clause, section 16 describes the post-expose public surface (five objects, 29 rows, the --check-rest command, the 08-11 comparison) with exactly five table rows, and section 3 states dlr_writer's four grants as the migrations define them
result: pass
source: automated
coverage_id: D5

### 50. 08-12 D1: read_ratings.py prints the upcoming day-ahead targets (12 lines, three per city in conf...
expected: read_ratings.py prints the upcoming day-ahead targets (12 lines, three per city in config order, UTC Z, amps, band, lead, source) and four status lines after Parts 1 and 2, on /usr/bin/python3 (3.9) and the repository interpreter, with empty stderr, no file written and Parts 1 and 2 unchanged
result: pass
source: automated
coverage_id: D1

### 51. 08-12 D2: Empty upcoming prints a notice and exits 0; a late city prints a LATE line and exits 0;...
expected: Empty upcoming prints a notice and exits 0; a late city prints a LATE line and exits 0; a three-row status exits 1 naming the city; a 404 on day_ahead_upcoming exits 1 after Parts 1 and 2 with neither key nor URL printed
result: pass
source: automated
coverage_id: D2

### 52. 08-12 D3: curl.sh and supabase_js.mjs read the two views read-only with the same select lists as ...
expected: curl.sh and supabase_js.mjs read the two views read-only with the same select lists as the Python example (all subsets of the contract columns); curl exits non-zero on a 404; the supabase-js file passes node --check, sets exitCode on a short status and never installs a package; the read-only, one-header and no-project-value tests pass on the extended files
result: pass
source: automated
coverage_id: D3

### 53. 08-12 D4: The four consumer docs carry the day-ahead handoff text (Software section with a column...
expected: The four consumer docs carry the day-ahead handoff text (Software section with a column-checked dashboard table, easy mistakes, key, readable and 503 rows; three api-contract rows; PSS/E next-day guidance with the UTC to CST and CDT table; the Examples sentence) and hold no secret, project host or URL
result: pass
source: automated
coverage_id: D4

## Summary

total: 53
passed: 53
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none yet]
