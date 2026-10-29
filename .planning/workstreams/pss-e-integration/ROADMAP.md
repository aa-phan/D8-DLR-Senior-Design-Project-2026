# Roadmap: Dynamic Line Rating (DLR) System

## Milestones

- 🚧 **v1.6 PSS/E Integration** - Phases 1-3 (in progress)

## Overview

An hourly job on a teammate's licensed laptop reads each city's latest `city_rating` row, applies
it (static rating when the row is stale, provisional or missing) to Power Systems' branches in
Power Systems' saved case, runs load flow, N-1 and a voltage-stability margin through `psspy`, and
writes the results and a run record back to the database. Another team member builds it; the
`psspy` API choices are theirs. The dashboard is out of scope. Target date: about 2026-11-02.

Three phases, each ending at a different outside gate: the first hands a spec to production-pipeline
Phase 6, the second needs Power Systems' branch mapping (a placeholder is enough to build against),
the third needs Phase 6 live, Power Systems' case file and the laptop.

**External dependencies:**
- **production-pipeline Phase 6** (running in parallel): ratings read access, the four PSS/E result
  tables and the PSS/E write grant, all in its migration. This workstream hands it the spec (DBX-01)
  and writes no migration of its own. Phase 6's live steps are the owner's to apply.
- **Power Systems**: the saved case file, the city-to-branch mapping, and access to the laptop with
  PSS/E.
- **production-pipeline Phase 7**: every `city_rating` row stays provisional until its go, so until
  then studies run on static ratings (IN-01).

## Phases

- [ ] **Phase 1: Result-Table Spec and Rating I/O** - Spec to Phase 6; rating selection with static fallback; run record and all-or-nothing write
- [ ] **Phase 2: Study on Power Systems' Case** - Branch mapping, unit conversion, load flow, N-1, voltage margin, dispatched capacity, proven on the Mac with a fake `psspy`
- [ ] **Phase 3: Laptop Run and Handover** - Real run on the laptop, scoped credential, hourly schedule with visible gaps, setup guide

## Phase Details

### Phase 1: Result-Table Spec and Rating I/O

**Goal**: Phase 6 has what it needs to build the PSS/E result tables and write grant, and the job can choose each city's rating and record every run.
**Depends on**: Nothing (first phase). Time-critical: Phase 6 is building its migration now, so the spec goes first.
**Requirements**: DBX-01, IN-01, WB-01, WB-02
**Success Criteria** (what must be TRUE):
  1. A written spec of the four result tables (contingency results, dispatched capacity, voltage margins, run record) gives columns, units, keys, and how each row links to its run and to the `city_rating` rows used, and production-pipeline Phase 6's plans take the tables and the PSS/E write grant from it.
  2. For each city the job uses the newest `city_rating` row, and uses the city's static rating, recorded as such, when that row is missing, older than 90 minutes or provisional (today every row is provisional, so all four cities show static).
  3. Every run writes one run record (start and end time, case identifier, per-city rating used and its source, outcome ok, fallback or failed, any error), including a run whose study fails.
  4. A run that fails partway leaves no result set that looks complete: results are all written, or the run is marked failed.

**Plans**: 5/5 plans executed
- [x] 01-01-PLAN.md — Reference DDL (four tables, `dlr_psse_writer` role, grants, RLS) proven on a local Postgres
- [x] 01-02-PLAN.md — Rating selection with static fallback, units, constants copy and drift test
- [x] 01-03-PLAN.md — Spec `psse_results_v1.md`, Phase 6 hand-off note, doc/DDL drift test
- [x] 01-04-PLAN.md — Run record and atomic writer (one transaction, failed record on rollback)
- [x] 01-05-PLAN.md — `run_once`: read ratings, study, validate, single write at the end

### Phase 2: Study on Power Systems' Case

**Goal**: Given the ratings, the job applies them to the mapped branches and produces load-flow, N-1, voltage-margin and dispatched-capacity results, proven on the Mac with a fake `psspy`.
**Depends on**: Phase 1. Power Systems' city-to-branch mapping (a placeholder is enough until it arrives).
**Requirements**: IN-02, IN-03, STU-01, STU-02, STU-03, STU-04, TST-01
**Success Criteria** (what must be TRUE):
  1. The city-to-branch mapping is configuration, and a mapped branch missing from the case makes the run fail, recorded, with no study results written.
  2. Ratings reach PSS/E in the units its branch rating expects (conversion stated and tested, amps to MVA at the branch's voltage), and a load flow that does not converge is recorded as a failed run, never written as valid results.
  3. A converged run records, for each contingency, thermal overloads and voltage violations with the element, the limit and the amount exceeded; a voltage-stability margin per city; and per-city dispatched capacity (the lower of the applied DLR rating and the voltage-stability limit, in amps and MW, saying which one set it).
  4. The Mac test suite against a fake `psspy` passes, covering static fallback, the mapping check, a non-converging load flow, and write-back including a failed run.

**Plans**: 7/7 plans executed (5 waves: 01 and 02 parallel, then 03, then 04 and 05 parallel, then 06, then 07)
- [x] 02-01-PLAN.md — Mapping file and study settings: validated JSON configuration, placeholder example with fake 9xxxx buses, real files git-ignored
- [x] 02-02-PLAN.md — `psspy` adapter with the SURFACE table, the convergence rule and the case-file guard; fake `psspy` and placeholder case
- [x] 02-03-PLAN.md — Study base: mapping check before any write, ratings in MVA at the case's kV with read-back, base load flow, private temp copy
- [x] 02-04-PLAN.md — N-1 branch-outage screen: thermal and voltage violations with element, limit and amount exceeded
- [x] 02-05-PLAN.md — Voltage-stability margin per city and dispatched capacity (lower of DLR rating and voltage limit, amps and MW)
- [x] 02-06-PLAN.md — Whole study through `run_once` into local Postgres with the fake `psspy`: complete runs and recorded failed runs
- [x] 02-07-PLAN.md — Laptop probe for Phase 3, study-definitions note, questions for the user and Power Systems

### Phase 3: Laptop Run and Handover

**Goal**: The hourly job runs on the licensed laptop against Power Systems' real case, results can be read back from the database, and someone else can install it.
**Depends on**: Phase 2. production-pipeline Phase 6 live (read access, result tables and PSS/E write grant applied). Power Systems' case file, mapping and laptop access.
**Requirements**: DBX-02, TST-02, SCH-01, SCH-02, DOC-01
**Success Criteria** (what must be TRUE):
  1. One real end-to-end run on the laptop against Power Systems' case writes a run record and results that can be read back from the database.
  2. The job's credential reads ratings and writes the PSS/E result tables, and an attempt to change `city_rating` with it is rejected.
  3. Windows Task Scheduler runs the job hourly with no overlapping runs, and an hour with no run (laptop off or asleep) shows as a gap in the run records through a stated query or check.
  4. A setup guide for the laptop (PSS/E and Python versions, credentials, Task Scheduler entry) lets someone else install the job and start the hourly runs.

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Result-Table Spec and Rating I/O | 5/5 | In Progress | - |
| 2. Study on Power Systems' Case | 7/7 | In Progress | - |
| 3. Laptop Run and Handover | 0/TBD | Not started | - |
