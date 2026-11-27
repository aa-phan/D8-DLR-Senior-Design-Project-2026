---
phase: 03-solver-tag-migration-and-per-solver-gaps
verified: 2026-11-23T00:00:00Z
status: passed
score: 4/4 must-haves verified
live_check_recorded: 2026-11-25
covered_files:
  - .planning/workstreams/pandapower-solver/phases/03-solver-tag-migration-and-per-solver-gaps/03-01-PLAN.md
  - .planning/workstreams/pandapower-solver/phases/03-solver-tag-migration-and-per-solver-gaps/03-01-SUMMARY.md
  - .planning/workstreams/pandapower-solver/phases/03-solver-tag-migration-and-per-solver-gaps/03-02-PLAN.md
  - .planning/workstreams/pandapower-solver/phases/03-solver-tag-migration-and-per-solver-gaps/03-02-SUMMARY.md
  - .planning/workstreams/pandapower-solver/phases/03-solver-tag-migration-and-per-solver-gaps/03-03-PLAN.md
  - .planning/workstreams/pandapower-solver/phases/03-solver-tag-migration-and-per-solver-gaps/03-03-SUMMARY.md
  - .planning/workstreams/pandapower-solver/phases/03-solver-tag-migration-and-per-solver-gaps/03-04-PLAN.md
  - .planning/workstreams/pandapower-solver/phases/03-solver-tag-migration-and-per-solver-gaps/03-04-SUMMARY.md
  - .planning/workstreams/pandapower-solver/phases/03-solver-tag-migration-and-per-solver-gaps/03-05-PLAN.md
  - .planning/workstreams/pandapower-solver/phases/03-solver-tag-migration-and-per-solver-gaps/03-05-SUMMARY.md
  - backend/pandapower_job/api.py
  - backend/pandapower_job/engine.py
  - backend/psse_job/contract.py
  - backend/psse_job/gaps.py
  - backend/psse_job/job.py
  - backend/psse_job/run_record.py
  - backend/psse_job/writer.py
  - backend/tests/local_pg.py
  - backend/tests/pandapower_solver_tag_test.py
  - backend/tests/psse_gaps_solver_test.py
  - backend/tests/psse_local_pg.py
  - backend/tests/psse_solver_tag_test.py
  - backend/tests/solver_tag_migration_test.py
  - backend/tests/solver_tag_owner_check_test.py
  - supabase/migrations/20261118200000_psse_run_solver_tag.sql
  - supabase/ops/verify_solver_tag.sql
covered_digest: "v3:sha256:689dee19b2883c9d4713486da4ea6c9e37065cde64a4fc20d2aedac3cabfe798"
behavior_unverified: 0
overrides_applied: 0
human_verification: []
resolved_human_verification:
  - test: "Apply migration 20261118200000_psse_run_solver_tag.sql to the live Supabase project, then run supabase/ops/verify_solver_tag.sql, verify_psse_results.sql and verify_exposure.sql in the SQL editor"
    resolved: 2026-11-25
    result: "Owner (Aaron) applied it with no errors; all three check files all ok, the tag counts and the dashboard confirmed (see Live check, 2026-11-25)."
---

# Phase 3: Solver Tag, Migration and Per-Solver Gaps Verification Report

**Phase Goal:** The four result tables can hold PSS/E and pandapower runs side by side, every run carries the solver that produced it, and the gap check shows which solver missed which hour.
**Verified:** 2026-11-23
**Status:** passed (2026-11-25). Every code-side and throwaway-database truth held on 2026-11-23; the owner's live apply and read-only checks were reported on 2026-11-25 and are recorded in "Live check, 2026-11-25" below.
**Re-verification:** No, initial verification, plus the owner's live result added 2026-11-25.

Limit as of the 2026-11-23 verification: the migration was not yet applied to the live Supabase project, and every database proof in the sections between here and "Live check, 2026-11-25" ran on a throwaway local PostgreSQL 17.12 cluster (Windows). Those sections are left as written; read them with the live section below. The live result is the owner's report, not something this verifier ran.

Private data rule kept: nothing under `data/private/pandapower/` was opened, read, grepped or printed.

## What changed since the plan summaries

Plans 03-01 to 03-05 each recorded their database tier as only SKIPPED (no Postgres on this machine) and left DB-01 to DB-03 Pending. That is why this report exists: PostgreSQL 17.12 is installed now, and I ran the whole tier myself.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC1 / DB-01: one additive migration keeps pre-existing runs valid and tagged `psse` (default), adds `solver_version`, accepts a `pp-` run id only with `solver = 'pandapower'`; a deliberately mismatched insert is refused by the database; the applied v1 migration is not edited | VERIFIED on a throwaway database (live apply pending, see Truth 4) | Migration read in full (`supabase/migrations/20261118200000_psse_run_solver_tag.sql:46-63`): `add column if not exists solver text not null default 'psse'`, `solver_version text`, four named check constraints (`psse_run_solver_ck`, `psse_run_solver_version_ck`, widened `psse_run_run_id_ck`, tie `psse_run_solver_run_id_ck`: `(solver='psse' and left(run_id,5)='psse-') or (solver='pandapower' and left(run_id,3)='pp-')`), each dropped-if-exists then added, no `NOT VALID`, no UPDATE, no grant/revoke on the table. `solver_tag_migration_test.py`: 16 passed on Postgres (9 text, 7 database): existing runs read `psse` and NULL after the migration with no UPDATE, each constraint refuses its case by constraint name, re-applying twice changes nothing, the unchanged 17-column PSS/E insert still writes. The applied files are untouched: `20261109233541_psse_results.sql` and `20261116200000_expose_latest_grid_study.sql` each have exactly one commit in git history (`fbd3e22`, `17bccbd`) and their committed blobs hash to the pinned values (psse_results `08e7e103...`, expose_latest_rating `7e2d5f01...`, expose_day_ahead `253a539e...`). |
| 2 | SC2 / DB-02: the pandapower job writes through the existing all-or-nothing writer as `dlr_psse_writer` and stamps every run with its solver; a pandapower run cannot be stored as `psse`; the unchanged PSS/E job's tests still pass | VERIFIED with limits (see "DB-02 sentence checked against the code" below) | `api.py:472` registers tag `pandapower`, prefix `pp`, on import; `engine._recording_study` stamps `solver` and `solver_version`; `job.run_once(solver=)` builds a `pp-` id (`run_record.new_run_id`), a 19-key record and refuses results whose solver differs (`run_record.py:145`); `writer._check_tag` refuses every mismatch before any statement (`writer.py:122-150`); the database tie is the last layer. `pandapower_solver_tag_test.py` 9 passed on Postgres including `test_db_tagged_rehearsal_through_the_real_writer` (real writer as `dlr_psse_writer`: 1 run, 4 dispatch and 4 margin rows, tagged), `test_db_a_pandapower_run_cannot_be_stored_as_psse` (both INSERTs refused by `psse_run_solver_run_id_ck`, no row left) and `test_db_both_solvers_side_by_side_in_one_hour`. `psse_solver_tag_test.py` 13 passed, `psse_writer_test.py` 13 passed, `psse_schema_pg_test.py` 45 passed. PSS/E launcher still calls `job.run_once` with the default tag (`launcher.py:578`). |
| 3 | SC3 / DB-03: with a PSS/E run in an hour and no pandapower run in that hour, the gap check reports that hour as missing for pandapower; PSS/E offline gaps are listed separately and neither hide nor are hidden by pandapower gaps | VERIFIED with limits (library only; see Limits) | `gaps.compute_gaps` (`gaps.py:226-247`) walks each solver from its own first slot over its own rows. I called it myself on PSS/E at 07, 09, 10, 11 and pandapower at 09, 11 (current hour 12): the report prints a PSS/E section with one gap (08:00 `no_run`) and a separate pandapower section with one gap (10:00 `no_run`), although PSS/E has a run at 10:00. `psse_gaps_solver_test.py` 15 passed on Postgres, including `test_db_run_by_solver_on_the_migrated_schema` (real `RUNS_SQL` and `CURRENT_HOUR_SQL`, exit 5, exactly H-2h missing for the second solver, a write on the session raises `ReadOnlySqlTransaction`), the independent plain-loop oracle comparison over 300 seeded histories and `test_pss_e_offline_is_listed_separately`. `psse_gaps_pg_test.py` (legacy pooled check) 13 passed, unchanged. |
| 4 | SC4: after the owner applies the migration to the live project, a read-only check shows the existing runs tagged `psse` and nothing else changed | VERIFIED 2026-11-25 on the owner's report (see "Live check, 2026-11-25"). Text below is the 2026-11-23 state: | The check exists and runs: `supabase/ops/verify_solver_tag.sql` is one read-only SELECT of seven checks. `solver_tag_owner_check_test.py` 13 passed on Postgres: all seven ok after the chain, and each check is made false once by its own sabotage (`test_db_each_check_can_fail`, 7 cases, each rolled back). Nothing has been run against the live project. This is the open human item in the frontmatter. |

**Score:** 4 of 4 as of 2026-11-25 (3 of 4 on 2026-11-23; the fourth was the owner's live step). 0 present-but-behavior-unverified (every state-transition or constraint truth has a passing database test).

## The test run, as I ran it

Environment as instructed: Git Bash, `PATH` with `C:\Program Files\PostgreSQL\17\bin`, `DLR_TEST_PG_AUTOSTART=1 PSSE_REQUIRE_PG=1 PYTHONDONTWRITEBYTECODE=1`, `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider`, run in the background, not piped to head.

| Run | Files | Result |
|-----|-------|--------|
| Phase 3 set | `solver_tag_migration_test` (16), `psse_solver_tag_test` (13), `pandapower_solver_tag_test` (9), `psse_gaps_solver_test` (15), `psse_gaps_pg_test` (13), `solver_tag_owner_check_test` (13), `psse_writer_test` (13), `psse_schema_pg_test` (45) | **137 passed, 0 failed, 0 skipped** in 328 s. The 137 equals the sum of the per-file collected counts, so nothing was deselected or skipped; `PSSE_REQUIRE_PG=1` would have turned a missing database into errors. |
| Adjacent | `pandapower_study_job_test`, `grid_study_expose_test`, `psse_results_migration_test`, `expose_migration_test`, `day_ahead_expose_test`, `pandapower_import_gate_test` | 106 passed, 4 failed in 233 s. All 4 are the known Windows-only failures, none a phase defect: three CRLF byte-hash tests (`test_psse_migration_is_unchanged_after_apply`, `test_phase6_migrations_are_unchanged_after_apply`, `test_expose_migration_is_unchanged_after_apply`: the working-tree files are CRLF under `autocrlf=true`; `git show HEAD:` of the same files hashes to `08e7e103`, `7e2d5f01`, `253a539e`, the pinned values) and `test_is_provisional_reads_the_real_labels` (no `matplotlib`). `pandapower_cli_test` and `pandapower_ingest_test` were not run. |

The first run's 137 includes the two tests the plan summaries said had never run on a database anywhere: the seven `test_db_*` of the migration file and the whole owner-check database tier.

## Your two uncommitted changes (judged, not accepted)

Both are now in commit `c10f8dc` (made while I was working; I did not create it and did not commit anything).

### 1. Seeding `city_rating` in `test_db_tracer_every_check_is_ok_after_the_chain`: a legitimate fix, not a weakening

I tested it rather than reading it. A throwaway script (scratchpad, not committed) built the same database as the test (every migration, one complete PSS/E run and one complete pandapower run) and ran the three check files before and after the seed:

| State | `verify_solver_tag.sql` | `verify_psse_results.sql` | `verify_exposure.sql` |
|-------|------------------------|--------------------------|----------------------|
| No `city_rating` rows | 7 of 7 ok | 7 of 7 ok | 4 of 36 false |
| One hour-aligned row per city | 7 of 7 ok | 7 of 7 ok | 36 of 36 ok |

The four false checks without the seed are `is_provisional_matches_the_labels` and `is_stale_matches_age_minutes` (`rows checked=0`), `latest_rating_has_the_four_cities` (`cities: none`) and `latest_rating_one_row_per_city` (`rows=0`). All four belong to the older exposure checker and describe the rating table, not the solver tag. They are false on an empty rating table by design; the live project has ratings. So:

- The seed does not touch any of the seven solver-tag checks: they were ok with and without it, and they have their own sabotage proofs.
- Without the seed the test could never have run green on any machine, because the chain test asserts `verify_exposure.sql` is all ok and that file demands rating rows. The same fix is the pattern the exposure suite already uses (`expose_migration_test.py:470, 493`, `rating_row` per city).
- The seed makes the "earlier checks still all ok" assertion stronger, not weaker: four checks that were failing on emptiness now pass on real rows. The slightly different thing it does not prove is that exposure checks stay ok on the live rating data; the owner's live run covers that.

One residual note, not a defect: the assertion that the older checks stay ok now depends on `rating_row` producing a row the older checker likes, which is a fixture assumption shared with `expose_migration_test.py`.

### 2. `backend/tests/local_pg.py` Windows guard and DEVNULL pipes: legitimate, with one small diagnostic cost

It mirrors `psse_local_pg.py`. Evidence it works: the cluster started and 137 plus 110 tests ran on it. On non-Windows the options are the same flags in a different order (`unix_socket_directories=''` now last), so Mac behaviour is unchanged. Cost: `capture_output=True` is gone, so a failed `pg_ctl start` now raises `CalledProcessError` with no stderr in the exception; the server log file still holds the diagnostics. INFO only. I did not run it on macOS.

## DB-02 sentence checked against the constraint and writer path

REQUIREMENTS.md DB-02: "a pandapower run can never be stored as `psse`". There are four layers; I read each:

1. `run_record.new_run_id(started_at, solver)` gives the run its prefix from the registry (`pp` for pandapower).
2. `run_record.build_run_record` raises `ResultsInvalid` when `results.solver != context.solver` (`run_record.py:145`); `job.run_once` catches it inside the validate/build `try` and stores one failed run with no result rows.
3. `writer._check_tag` (`writer.py:122-150`): an untagged record needs a `psse-` id; a tagged record needs a registered non-PSS/E solver whose prefix starts the run id; a tagged `psse` record is refused. It raises a plain `ValueError` before any statement.
4. Database: `psse_run_solver_run_id_ck` refuses a `pp-` id with `solver = 'psse'`, and, because the column default is `psse`, a `pp-` id sent through the old 17-column INSERT gets `psse` and is refused too (both asserted in `test_db_a_pandapower_run_cannot_be_stored_as_psse`, which executes the INSERTs directly as the writer role, bypassing layer 3).

What the sentence does hold: **a run with a `pp-` run id can never be stored as `psse`**, in the database itself, and through `run_once` a pandapower study can never put figures into the PSS/E rows.

What the sentence overstates, if read as a guarantee about where figures came from:

- **A pandapower study started with the default tag is stored as a failed `psse-` run, with no figures.** `test_refused_default_tag_never_stores_results` covers it. It is recorded under PSS/E (as `failed_stage validate_results`), so it would show in the PSS/E section of the gap check as a failed-only hour. No figures leak, but the row is tagged `psse`. This is caused by a runner that forgets `solver=engine.SOLVER`; no runner exists yet (Phase 5 builds it, `engine.py:29` documents the requirement).
- **The database cannot see where figures came from.** A caller that bypasses `run_once` and hands the writer a hand-built record with a `psse-` id and `solver` omitted will be accepted, whatever produced the figures. Layers 2 and 3 only compare tags the caller supplies. This is not a defect in the phase's design (the tie is on identity, not on provenance), but "never" is true of the identity link and of the `run_once` path, not of a hand-built record.

Suggested wording for the requirement text (owner-side, not edited here): "a run with a `pp-` run id can never be stored as `psse`, and a pandapower study given the default tag is refused and stored as a failed run with no results".

"Writes as `dlr_psse_writer`" is proven in a test (`test_db_tagged_rehearsal_through_the_real_writer` connects through `pg_helper.role_url(..., "dlr_psse_writer")`). No pandapower runner or workflow exists yet to do it for real: `run_once` has no pandapower caller outside tests. That is Phase 5.

## DB-03 per-solver gaps, with PSS/E offline gaps separate

- Per solver: `compute_gaps` takes each solver's own first slot and own rows (`gaps.py:226-247`). There is no pooled first slot. A PSS/E row in an hour never fills a pandapower hour, and the reverse.
- Separately listed: `format_solver_report` prints PSS/E first, then each other solver by name. In my scenario above PSS/E's 08:00 gap and pandapower's 10:00 gap appear in their own sections.
- Exit rule: with `fail_on_gaps`, PSS/E gaps are listed but do not fail by default (its machine being offline is the known state); every other present or expected solver fails on a gap in the window, or on being expected with no rows; an empty table fails. This is the plan's recommendation, which the owner may change (`failing=(...)`). It is a design choice, not a defect, but note the consequence: an outage of PSS/E alone never turns the check red by default.
- A pandapower hour before pandapower's own first run is not a gap. That is deliberate (it has no history before then) and means "a missing pandapower hour" is measured from its first recorded slot. A solver expected but with no rows is reported as `no runs recorded` only if named in `expected`.

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `supabase/migrations/20261118200000_psse_run_solver_tag.sql` (140 lines) | columns, four constraints, guarded view | VERIFIED | Read in full. Sorts after `20261116200000`; committed. Not applied live. |
| `supabase/ops/verify_solver_tag.sql` | one read-only SELECT, seven checks, counts only | VERIFIED | Read in full; ran in the test and in my control script, 7 of 7 ok; no run id or version in `detail` (asserted by the test). |
| `backend/psse_job/contract.py`, `run_record.py`, `job.py`, `writer.py` | tag registry, tagged record, tagged insert, refusals | VERIFIED | Read the load-bearing parts; 13 + 13 + 45 tests passed. `psse_job` still names no second solver (`pandapower_import_gate_test` passed in the adjacent run). |
| `backend/psse_job/gaps.py` | `run_by_solver` beside untouched `run` | VERIFIED, library only | `run_by_solver` has no caller outside tests (grep). |
| `backend/pandapower_job/api.py`, `engine.py` | registers and stamps the tag | VERIFIED | `api.py:472`; engine stamps `solver` and `solver_version`. |
| Tests listed in the frontmatter | proofs | VERIFIED | Substantive; all run on Postgres here. |

## Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| `api.py` import | tag registry | `contract.register_solver_tag("pandapower", "pp")` | WIRED; Python vocabulary equals the migration's constraints (parity tests passed) |
| engine results | run record | `results.solver` / `solver_version` into `build_run_record` (19 columns) | WIRED |
| run record | database | `writer._run_insert` chooses `INSERT_RUN_TAGGED_SQL` when the record carries `solver` | WIRED; executed on real Postgres as the writer role |
| `solver` column | gap check | `RUNS_SQL` selects it, `compute_gaps` groups on it | WIRED; real database test passed |
| migration view section | public dashboard view | `r.solver = 'psse'` predicate added to `latest_grid_study` | WIRED; `test_db_a_newer_pandapower_run_never_changes_the_view` passed (anon sees only the older PSS/E run; with only pandapower runs the view is empty) |
| `run_by_solver` | any CLI, workflow or runner | none | NOT WIRED (laptop `gaps` command is still pooled; Phase 5 wires the hourly call) |

## Data-Flow Trace (Level 4)

| Artifact | Data | Source | Real data | Status |
|----------|------|--------|-----------|--------|
| stored `solver`, `solver_version` | engine results | real pandapower four-city study through `run_once` into Postgres | Yes (the rehearsal reads them back from the table) | FLOWING |
| per-solver gap lines | `RUNS_SQL` rows | the `psse_run` table on a migrated database | Yes | FLOWING |

## Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| DB-01 | 03-01, 03-05 | One additive migration: `solver` (default `psse`), `solver_version`, `pp-` tied by a check constraint | MET WITH LIMITS | Truth 1. Proven on a throwaway database only; the live apply and read-only check (Truth 4) are the owner's step. Wider than the requirement text in one respect: the migration also replaces the public view `latest_grid_study` with a `solver = 'psse'` filter (owner decision D-03, 2026-11-18). |
| DB-02 | 03-02, 03-04 | Pandapower writes through the existing writer as `dlr_psse_writer`, tagged; never stored as `psse` | MET WITH LIMITS | Truth 2 and the sentence check above. Proven by tests and a throwaway database; no real pandapower runner exists yet; "never" is about the run-id identity and the `run_once` path. |
| DB-03 | 03-03 | Gap check per solver; PSS/E offline gaps separate | MET WITH LIMITS | Truth 3. Done as `gaps.run_by_solver`; the laptop `gaps` command is still pooled and no workflow calls the new check until Phase 5. |

No orphaned requirements: REQUIREMENTS.md maps exactly DB-01 to DB-03 to Phase 3, and each is claimed by a plan.

## Anti-Patterns Found

None. Debt-marker grep (`TBD|FIXME|XXX|TODO|HACK`) over the migration, the owner-check SQL, the six changed source files and the five test files returned no matches. No stub or placeholder flows to output.

## Findings

| ID | Severity | Finding |
|----|----------|---------|
| F-1 | WARNING (the open gate) | The migration is not applied to the live project, so roadmap success criterion 4 has not happened and nothing here shows the live data. Phase 5's live-write gate needs it. Do the apply, then run all three owner checks; every ok must be true. Recommended: keep DB-01 to DB-03 Pending in REQUIREMENTS.md and Phase 3 unticked in ROADMAP.md until the live check is recorded, or tick them with a "throwaway database only" note. The decision is orchestrator-owned; I changed neither file. |
| F-2 | WARNING (wording) | DB-02's "can never be stored as `psse`" is true of the run-id identity and the `run_once` path, not of a caller that bypasses `run_once`; and a pandapower study with the default tag is stored as a failed `psse-` run with no figures. See the DB-02 section for suggested wording. |
| F-3 | WARNING (reach) | `gaps.run_by_solver` is library-level. The laptop `gaps` command and the legacy pooled `run` are unchanged (assumption A6 of 03-03), so nobody can run the per-solver check from the command line yet; the hourly call belongs to Phase 5 (OPS-05). The pooled check can still hide one solver's gap behind the other's if someone uses it. |
| F-4 | INFO (live behaviour change) | Applying the migration also replaces the public `latest_grid_study` view. Today every run is `psse`, so the predicate keeps the same rows; the contract (20 columns, order, owner rights, grants, comments) is pinned by a test and passed here. Owner-confirmed (D-03), but it touches the dashboard, so check the dashboard once after the live apply. |
| F-5 | INFO (design consequence) | By default a PSS/E-only outage never fails the per-solver check. A custom `failing=(...)` changes it. Phase 5 must pass `expected=(engine.SOLVER,)` as 03-03 says, or an absent pandapower solver is only reported if it has some rows. |
| F-6 | INFO (Windows) | The CRLF byte-hash tests and `test_is_provisional_reads_the_real_labels` fail here and are not phase defects; I confirmed the committed blobs hash to the pinned values and that each applied migration has one commit. `pandapower_cli_test` and `pandapower_ingest_test` were not run. |
| F-7 | INFO (not run) | The tests and SQL ran on PostgreSQL 17.12 on Windows. The live project is Supabase on its own Postgres version; nothing here proves identical behaviour there (the owner's live check does). `pg_ctl` stderr is no longer captured in `local_pg.py` (see change 2). |

No finding is a BLOCKER: no truth failed.

## Limits that stay attached to this verdict

- Throwaway local PostgreSQL 17.12 only. The live Supabase project does not have the migration.
- The proof of "no pandapower run stored as `psse`" is on identity (run id and tag), enforced in the database, and on the `run_once` path; it does not detect a hand-built record.
- No pandapower runner or workflow exists; the "pandapower job writes as `dlr_psse_writer`" proof is a rehearsal with the engine's four-city study in tests.
- Per-solver gaps are a function, not yet a command or a scheduled check.
- Windows byte-hash and missing-package failures are environmental; not reproduced on the Mac.

## Live check, 2026-11-25

Reported by the project owner (Aaron) to the user; counts and pass/fail only, no connection strings. Not run by this verifier.

| Step | Reported result |
|------|-----------------|
| Apply `20261118200000_psse_run_solver_tag.sql` in the Supabase SQL Editor | Applied, no errors |
| `verify_solver_tag.sql` | 7 of 7 ok; 19 runs tagged `psse`, 0 tagged `pandapower` |
| `verify_psse_results.sql` | 7 of 7 ok |
| `verify_exposure.sql` | 36 of 36 ok (first reported as 37, a miscount; see below) |
| `latest_grid_study` after the apply | Unchanged: the same four cities from the 2026-11-12 15:00 UTC run |

Follow-up from the owner, same day, closing the three notes that were open when the phase was closed:

- **Check count: resolved, a miscount.** `verify_exposure.sql` is the same file on `main` and on this branch, and it returned 36 of 36 ok. The earlier "37 of 37" was the owner's miscount. The live result is therefore 36 of 36, matching the repo file and the local run.
- **`solver_version`: resolved.** `select solver, solver_version, count(*) from psse_run group by 1, 2` returned one row: `psse | NULL | 19`. Every existing run reads `psse` with `solver_version` NULL, as expected.
- **Dashboard: checked, with a limit.** The owner ran the dashboard from `main` locally against the live project: the home and forecast pages load for all four cities and show "using Dynamic Line Ratings". Those pages read `latest_rating` and `day_ahead_upcoming`, not `latest_grid_study`, so this shows the dashboard still works after the apply; it does not exercise the replaced view. The view itself was checked separately: its output is unchanged (same four cities, 2026-11-12 15:00 UTC run).

## Human Verification Required (resolved 2026-11-25)

The item below was resolved by the live check above. Kept for the record.

### 1. Apply the migration to the live project and run the three read-only checks

**Test:** Apply `20261118200000_psse_run_solver_tag.sql` with `supabase db push --db-url ...`, then run `verify_solver_tag.sql`, `verify_psse_results.sql` and `verify_exposure.sql` in the SQL editor, and open the dashboard once.
**Expected:** Every `ok` is true in all three files (seven, seven and 36 checks); the existing runs read `solver = psse` and `solver_version` NULL; the dashboard still shows the newest PSS/E result per city.
**Why human:** Only the owner applies it to the live project; this verifier has no access and did not try.

## Gaps Summary

No gaps in code, in the throwaway-database proofs or in the owner's reported live check. The status is passed (2026-11-25); the three requirement sentences still carry the limits above, and the live check's three follow-up notes are all resolved.

---

_Verified: 2026-11-23_
_Verifier: Claude (gsd-verifier)_
