---
gsd_state_version: "1.0"
milestone: v1.6
milestone_name: PSS/E Integration
current_phase: 3
current_phase_name: Laptop Run and Handover
status: executing
stopped_at: Phase 4 complete, ready to execute Phase 3
last_updated: "2026-11-11T07:16:26.024Z"
last_activity: 2026-11-11
last_activity_desc: Phase 4 complete, transitioned to Phase 3
state_head: 074a766680cd9a2283df84339162bae4c0d329f3
progress:
  total_phases: 4
  completed_phases: 2
  total_plans: 27
  completed_plans: 25
---

# Project State

## Project Reference

See: .planning/PROJECT.md (shared; PSS/E integration moves in scope at milestone completion, see this workstream's REQUIREMENTS.md scope note)

**Core value:** Each city's rating reaches PSS/E and PSS/E's results come back to the database,
every hour the host is on, and a rating that can't be trusted never reaches a study as anything
higher than the static rating.
**Current focus:** Phase 04 — Per-city scaling of the 39-bus case

## Current Position

Phase: 3 — Laptop Run and Handover
Plan: 8
Status: Ready to execute
Last activity: 2026-11-11 — Phase 4 complete, transitioned to Phase 3

Progress: [█████████░] 95%

## Performance Metrics

**Velocity:**
- Total plans completed: 6
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 4 | 6 | - | - |

*Updated after each plan completion*
**Per-Plan Metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 1 P01 | 22 min | 2 tasks | 4 files |
| Phase 1 P02 | 9min | 3 tasks | 8 files |
| Phase 1 P03 | 8min | 3 tasks | 3 files |
| Phase 1 P04 | 11min | 3 tasks | 6 files |
| Phase 1 P05 | 13min | 2 tasks | 2 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Milestone]: ~~No standalone migration~~ Superseded 2026-11-09: the four result tables and the `dlr_psse_writer` role shipped as the separate owner migration `20261109233541_psse_results.sql` (quick 261109-o6v), applied live (DBX-01, DBX-02).
- [Milestone]: Dashboard is out of scope; Power Systems owns the case and the branch mapping; `psspy` API choices belong to the implementer.
- [Milestone]: Static rating is the fallback when a `city_rating` row is missing, older than 90 minutes or provisional (IN-01).
- [Phase 1]: 01-01: result-table DDL stays reference-only; dlr_psse_writer holds INSERT and SELECT on the four psse_* tables, applied MVA enforced as sqrt(3) x kV x circuit amps / 1000 (no power factor) — D-01, D-03, D-06; proven on local Postgres 18.6 with Supabase legacy default grants
- [Phase 1]: 01-01: static-fallback dispatch rows carry NULL city_rating link times (link rule); stale/provisional row link lives only in psse_run.ratings_used — psse_dispatched_capacity_link_rule_ck ties both link columns to rating_source = city_rating
- [Phase 1]: [Phase 1 P02]: psse_job keeps its own copies of config constants (no import of backend/config.py), pinned by psse_contract_test; rating_amps per conductor converted to MVA with no power factor (D-05, D-06)
- [Phase 1]: [Phase 1 P02]: a failed latest_rating read is all-static with reason read_failed and a redacted read_error, never an exception (D-02); stale and provisional static choices keep the row link in memory, but the writer must insert NULL link times unless source is city_rating
- [Phase 1]: 01-03: spec and hand-off note pin the DDL marked region by an LF-normalised sha256 recomputed by psse_schema_doc_test.py; spec states service_role and the database owner sit outside the only-dlr_psse_writer access claim — Phase 6 copies the region verbatim, and core.autocrlf makes Windows checkouts CRLF; service_role bypasses RLS
- [Phase 1]: 01-04: write_run is one transaction (run row first, then results) as the INSERT-only dlr_psse_writer; any failure rolls back then records failed_stage write in a new transaction (WriteFailed), RecordFailed only when that also fails; validate_results enforces the selected rating, the link rule and the DDL identities before any write — WB-01/WB-02, D-03, D-04; an unrecorded run must never look successful; a retry with the same run_id returns already_recorded and never overwrites
- [Phase 1]: [Phase 1 P05]: 01-05: run_once connects only after the study and writes once at the end (D-04); exit 0 ok or fallback written, 1 failed run recorded, 3 nothing recorded (an unrecorded run is outcome failed, stage write); a failed ratings read stays a fallback run (D-02); failure text is redacted against the passed-in env as well as os.environ

### Pending Todos

None yet.

### Roadmap Evolution

- Phase 4 added: Per-city scaling of the 39-bus case (2026-11-09)

### Blockers/Concerns

- The deadline (about 2026-11-02) has passed. Production-pipeline Phases 6, 7 and 8 are complete and archived on main (merged into this branch 2026-11-09), and none of them added the four `psse_*` tables or the `dlr_psse_writer` role. Resolved 2026-11-09: the owner added them as a standalone migration (quick task 261109-o6v, `supabase/migrations/20261109233541_psse_results.sql`, applied live, `verify_psse_results.sql` 7 checks ok, the writer login connects and is refused on `city_rating`). What is still needed: the writer's connection string (`SUPABASE_PSSE_DB_URL`) delivered to the laptop directly, never through git or chat.
- Power Systems has not yet supplied the real city-to-branch mapping or confirmed the case. The laptop is available and the job has run end to end (dry run) on the public 39-bus case with a throwaway mapping. The real case must be an unconverted saved case and fit within the free edition's 50 buses. The user will raise the mapping in person; the email draft will not be sent.
- The 2026-11-09 dry run read four live `city_rating` rows with outcome `ok`, so ratings are no longer all static or provisional at the read. Production-pipeline Phase 7's go was recorded on main; this has not been re-checked row by row.
- REQUIREMENTS.md said 17 v1 requirements; it defines 16. Corrected to 16 in its Traceability section on 2026-10-26.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 261109-o6v | Add PSS/E results migration and dlr_psse_writer role | 2026-11-09 | edbb2fd | [261109-o6v-add-pss-e-results-migration-and-dlr-psse](./quick/261109-o6v-add-pss-e-results-migration-and-dlr-psse/) |

## Deferred Items

Items acknowledged and deferred at milestone close, most recent first:

| Category | Item | Status | Deferred At | Milestone |
|----------|------|--------|-------------|-----------|
| *(none)* | | | | |

## Session Continuity

Last session: 2026-11-09
Stopped at: Phase 4 complete, ready to execute Phase 3
Resume file: None

## Session note 2026-11-08 (end of day)

No laptop access. Done today: STATE refreshed and committed; Python 3.13 to 3.14 row added to the guide's decision table (commit 02e4f0f). Nothing else in this workstream is possible without the laptop.
Tomorrow: (1) send POWER-SYSTEMS-EMAIL-DRAFT.md (case is the IEEE 39-bus New England system, already on the laptop; only a saved .sav on the laptop is needed, plus the city-to-branch mapping and laptop session); (2) raise with production-pipeline owner that Phase 6's 13 plans do not yet include the four psse_* tables and the dlr_psse_writer grant (hand-off: docs/data-science/decisions/psse_results_phase6_handoff.md); (3) get the dlr_psse_writer URL, SUPABASE_URL and publishable key from the DS owner; (4) at the laptop resume 03-07 at step 2 (selftest with and without PSSE_BIN_DIR, U33 and U07).

## Session note 2026-11-09 (laptop session B)

Laptop reached. Done: pushed the three docs commits and merged main into the branch (clean, tests pass); on the laptop selftest (6 PASS), probe (27 PASS) and probe with the write check (29 PASS) pass, and a dry run on the public 39-bus case with a throwaway mapping completes with live ratings (outcome ok, 28 of 28 contingencies). Found: a converted (cnv) case fails the load flow; use an unconverted case (runbook step 3 note). Full record: phases/03-laptop-run-and-handover/03-07-LAPTOP-RECORD.md.
Next: (1) laptop: git pull, then runbook step 6 (Task Scheduler dry-run task); (2) ask the production-pipeline owner for the psse_* migration and the dlr_psse_writer login (message already in the repo, updated 2026-11-09); (3) in person with Power Systems: real mapping and confirm the case is unconverted and within 50 buses; (4) then 03-08 (credential proof, proof write, real task).

## Update 2026-11-09 (evening)

The owner applied the psse_results migration and created `dlr_psse_writer` (quick task 261109-o6v, merged into this branch). The writer string is held by the owner in an owner-only file and must be sent to the laptop's user directly. Next on the laptop: step 6 checks (6:15 and 7:15 runs, overlap test, remove the task), then runbook steps 8 and 9 (credential proof, proof write and read-back) with `PSSE_SITE_DIR` and `SUPABASE_PSSE_DB_URL` added to the config.

Evening update: runbook step 8 passed on the laptop (`credcheck` 16 PASS, with `--write-proof` 18 PASS, rolled back). The user decided to defer the real proof write (step 9, decision 1 of 03-08) until Power Systems' real mapping and case exist; no rows were written to the live psse_* tables. Remaining: finish step 6 (overlap test, remove the task), then step 7 (real case and mapping) and steps 9 and 10.

## Session note 2026-11-09 (end of day)

Done today: step 6 complete on the laptop (three hourly dry-run starts at :15:15 each with result 0 and no missed run, overlap test result 4, task removed); step 8 credential proof passed (16 PASS, write proof 18 PASS); Phase 4 (per-city scaling) added, researched, context decisions locked (all-or-nothing on a city failure, no separate Mvar target, realised totals not stored, El Paso on average load), requirements SCL-01 to SCL-06 added, validation file created, pattern map requested.
Open for tomorrow: (1) re-check the laptop clock alignment (the Windows Time service was not running, so `w32tm /query /status` failed; the web-header comparison has not been read); (2) resume `/gsd-plan-phase 4 --ws pss-e-integration` at the planner step, then the plan checker; (3) close plan 03-07 in the laptop record once the clock item is done; (4) in person with Power Systems: real mapping, unconverted case within 50 buses, same lines for every city copy.
