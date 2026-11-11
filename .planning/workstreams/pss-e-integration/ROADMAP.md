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

- [x] **Phase 1: Result-Table Spec and Rating I/O** - Spec to Phase 6; rating selection with static fallback; run record and all-or-nothing write
- [x] **Phase 2: Study on Power Systems' Case** - Branch mapping, unit conversion, load flow, N-1, voltage margin, dispatched capacity, proven on the Mac with a fake `psspy`
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

**Plans**: 8 plans (6 waves, run one plan after another in one working tree: 01, 02 and 03 in wave 1, then 04, then 05 (it needs 04 committed), then 06, then 07, then 08; 01 to 06 are built and tested on the Mac, 07 and 08 are human checklists that need the laptop, then Phase 6, the real case and the mapping)
- [x] 03-01-PLAN.md — Launcher core: configuration file outside the repository, OS-released run lock, database preflight, exit codes, dry-run; the fake `psspy` through `run_once` into local Postgres
- [x] 03-02-PLAN.md — Gap check: one SQL statement for the hours with no complete run, a read-only wrapper, tested against an independent reference
- [x] 03-03-PLAN.md — Credential proof: the writer role and the publishable key checked from the catalog and by refused statements, planted-fault tests, an opt-in rolled-back write proof
- [x] 03-04-PLAN.md — Entry script that alone imports `psspy`, selftest, probe, hold-lock, and the gaps and credcheck commands
- [x] 03-05-PLAN.md — Task Scheduler XML template (no overlap, 45-minute limit, no secrets) with a safe renderer and structure tests
- [x] 03-06-PLAN.md — Setup guide and laptop runbook with drift gates; every runbook command rehearsed on fakes and local Postgres
- [ ] 03-07-PLAN.md — Laptop session A (human): versions, psycopg wheelhouse after a legitimacy check, selftest, probe, dry-run on an example case, three hourly dry-runs
- [ ] 03-08-PLAN.md — Live session (human): credential proof, real-case review, one proof write with read-back behind a decision, the real hourly task behind a second decision, gap check, final guide edit

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Result-Table Spec and Rating I/O | 5/5 | In Progress | - |
| 2. Study on Power Systems' Case | 7/7 | In Progress | - |
| 3. Laptop Run and Handover | 6/8 | In Progress | - |

### Phase 4: Per-city scaling of the 39-bus case

**Goal:** The job runs the same study once per city on its own fresh copy of the same 39-bus network, scaled to that city's load and generation targets, so the four cities never share a solve. The targets live in the private mapping (never in git); the job applies them with its own scaling call and never executes the recorded `.idv` scripts. See `phases/04-per-city-scaling-of-the-39-bus-case/04-CONTEXT.md`.
**Requirements**: SCL-01, SCL-02, SCL-03, SCL-04, SCL-05, SCL-06
**Depends on:** Phase 3
**Plans:** 2/6 plans executed (5 waves, run one after another in one working tree: 01 and 02 in wave 1, then 03, then 04, then 05, then 06; 01 to 05 are built and tested on the Mac, 06 is a human checklist at the laptop)

Plans:
- [x] 04-01-PLAN.md — Mapping schema version 2: per-city scaling block (target load, target generation, basis), refused before any PSS/E call; the same line may serve several cities
- [x] 04-02-PLAN.md — Adapter `scale_case` and `read_totals` (whole-case `scal_2`, layout in one UNVERIFIED table) and the fake's generation and whole-case modes
- [ ] 04-03-PLAN.md — Per-city study: a fresh scaled copy per city, read-back and bounds before the solve, city-prefixed contingency ids, scaling basis and method in details, recomputed counts
- [ ] 04-04-PLAN.md — All-or-nothing city failure: every city attempted, one failed run naming each city, no result rows; shared budget; no figures in any output
- [ ] 04-05-PLAN.md — Probe row `scale_to_target`, the study note's per-city scaling section, runbook steps 4 and 5 and register rows U35 to U38
- [ ] 04-06-PLAN.md — Laptop session (human): read the scaling layout on PSS/E 36.4, decide whether it matches, `scale_to_target` and a timed four-city dry run, record
