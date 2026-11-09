---
gsd_state_version: "1.0"
milestone: v1.6
milestone_name: PSS/E Integration
current_phase: 3
current_phase_name: Laptop Run and Handover
status: laptop_steps_2_to_5_passed
stopped_at: 03-07 steps 2 to 5 passed on the laptop (session B, 2026-11-09); step 6 pending; 03-08 waits on the psse_* tables and writer login
last_updated: "2026-11-09T22:00:00.000Z"
last_activity: 2026-11-09
last_activity_desc: Laptop session B - selftest, probe, write check and dry run (live ratings read) all pass on the 39-bus case
state_head: 6b8cc5e88371736055be0a125a4ba86d62f13024
progress:
  total_phases: 3
  completed_phases: 2
  total_plans: 20
  completed_plans: 19
---

# Project State

## Project Reference

See: .planning/PROJECT.md (shared; PSS/E integration moves in scope at milestone completion, see this workstream's REQUIREMENTS.md scope note)

**Core value:** Each city's rating reaches PSS/E and PSS/E's results come back to the database,
every hour the host is on, and a rating that can't be trusted never reaches a study as anything
higher than the static rating.
**Current focus:** Phase 3 — Laptop Run and Handover (plans 07 and 08 need the licensed laptop)

## Current Position

Phase: 3 (Laptop Run and Handover) — EXECUTING
Plan: 03-01 to 03-06 and gap-closure 03-09 done; 03-07 steps 2 to 5 passed on the laptop (step 6, the Task Scheduler dry-run task, pending), then 03-08
Status: Laptop available; 03-08 and a real run wait on the psse_* tables and dlr_psse_writer login (production-pipeline owner) and on Power Systems' real mapping. Phases 1 and 2 verified (human_needed)
Last activity: 2026-11-09 — laptop session B recorded in 03-07-LAPTOP-RECORD.md

Progress: [█████████░] 95%

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

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

- [Milestone]: No standalone migration; the four result tables and the PSS/E write grant ship in production-pipeline Phase 6, and this workstream hands it the spec (DBX-01).
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

### Blockers/Concerns

- The deadline (about 2026-11-02) has passed. Production-pipeline Phases 6, 7 and 8 are complete and archived on main (merged into this branch 2026-11-09), and none of them added the four `psse_*` tables or the `dlr_psse_writer` role (a search of main finds no `psse_run`, `dlr_psse_writer` or related migration). Phase 3's real run and plan 03-08 need that migration, a new follow-on one. The request to the owner is in `docs/data-science/decisions/psse_message_to_aaron.md`; the user will ask in person.
- Power Systems has not yet supplied the real city-to-branch mapping or confirmed the case. The laptop is available and the job has run end to end (dry run) on the public 39-bus case with a throwaway mapping. The real case must be an unconverted saved case and fit within the free edition's 50 buses. The user will raise the mapping in person; the email draft will not be sent.
- The 2026-11-09 dry run read four live `city_rating` rows with outcome `ok`, so ratings are no longer all static or provisional at the read. Production-pipeline Phase 7's go was recorded on main; this has not been re-checked row by row.
- REQUIREMENTS.md said 17 v1 requirements; it defines 16. Corrected to 16 in its Traceability section on 2026-10-26.

## Deferred Items

Items acknowledged and deferred at milestone close, most recent first:

| Category | Item | Status | Deferred At | Milestone |
|----------|------|--------|-------------|-----------|
| *(none)* | | | | |

## Session Continuity

Last session: 2026-11-09
Stopped at: 03-07 steps 2 to 5 passed on the laptop; next is step 6 (Task Scheduler dry-run task), then 03-08 once the psse_* tables and writer login exist
Resume file: None

## Session note 2026-11-08 (end of day)

No laptop access. Done today: STATE refreshed and committed; Python 3.13 to 3.14 row added to the guide's decision table (commit 02e4f0f). Nothing else in this workstream is possible without the laptop.
Tomorrow: (1) send POWER-SYSTEMS-EMAIL-DRAFT.md (case is the IEEE 39-bus New England system, already on the laptop; only a saved .sav on the laptop is needed, plus the city-to-branch mapping and laptop session); (2) raise with production-pipeline owner that Phase 6's 13 plans do not yet include the four psse_* tables and the dlr_psse_writer grant (hand-off: docs/data-science/decisions/psse_results_phase6_handoff.md); (3) get the dlr_psse_writer URL, SUPABASE_URL and publishable key from the DS owner; (4) at the laptop resume 03-07 at step 2 (selftest with and without PSSE_BIN_DIR, U33 and U07).

## Session note 2026-11-09 (laptop session B)

Laptop reached. Done: pushed the three docs commits and merged main into the branch (clean, tests pass); on the laptop selftest (6 PASS), probe (27 PASS) and probe with the write check (29 PASS) pass, and a dry run on the public 39-bus case with a throwaway mapping completes with live ratings (outcome ok, 28 of 28 contingencies). Found: a converted (cnv) case fails the load flow; use an unconverted case (runbook step 3 note). Full record: phases/03-laptop-run-and-handover/03-07-LAPTOP-RECORD.md.
Next: (1) laptop: git pull, then runbook step 6 (Task Scheduler dry-run task); (2) ask the production-pipeline owner for the psse_* migration and the dlr_psse_writer login (message already in the repo, updated 2026-11-09); (3) in person with Power Systems: real mapping and confirm the case is unconverted and within 50 buses; (4) then 03-08 (credential proof, proof write, real task).
