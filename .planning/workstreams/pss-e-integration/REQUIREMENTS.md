# Requirements: Dynamic Line Rating (DLR) System — PSS/E Integration (v1.6)

**Defined:** 2026-10-26
**Core Value:** Each city's rating reaches PSS/E and PSS/E's results come back to the database,
every hour the host is on, and a rating that can't be trusted never reaches a study as anything
higher than the static rating.

**Scope note:** `PROJECT.md` lists PSS/E integration as out of scope for this project. This
workstream changes that boundary: this project now writes the PSS/E-side (`psspy`) job. Grid
modelling choices stay with Power Systems (their case, their branch mapping). `PROJECT.md` is
updated at milestone completion (a workstream does not edit its shared milestone section).

**Who builds it:** another team member implements and researches this milestone. These
requirements state what must be true, not how; `psspy` API choices are theirs.

**Deadline:** about 2026-11-02.

## v1 Requirements

### Database (via production-pipeline Phase 6)

- [ ] **DBX-01**: A written spec of the four PSS/E result tables (contingency results,
  dispatched capacity, voltage margins, run record), with columns, units, keys, and how each
  row links to its run and to the `city_rating` rows it used, is handed to production-pipeline
  Phase 6 so the tables and a PSS/E write grant ship in Phase 6's migration. No standalone
  migration in this workstream.
- [ ] **DBX-02**: The job reads ratings only through Phase 6's access and writes only to the
  PSS/E result tables; its credential cannot change `city_rating`.

### Inputs

- [ ] **IN-01**: For each city the job uses the newest `city_rating` row. When that row is
  missing, older than 90 minutes, or provisional, the job uses the city's static rating instead
  and records that it did. (Until production-pipeline Phase 7's go lifts the provisional label,
  this means studies run on static ratings.)
- [ ] **IN-02**: The city-to-branch mapping supplied by Power Systems is stored as
  configuration. If any mapped branch is missing from the case, the run is recorded as failed
  and no study results are written.
- [ ] **IN-03**: Ratings are converted to the units PSS/E's branch rating expects with the
  conversion stated and tested (amps to MVA at the branch's voltage).

### Study

- [ ] **STU-01**: A load flow runs on Power Systems' case with the ratings applied. A load flow
  that does not converge is recorded as a failed run, never written as valid results.
- [ ] **STU-02**: N-1 contingency screening runs; for each contingency, thermal overloads and
  voltage violations are recorded with the element, the limit, and the amount by which it was
  exceeded.
- [ ] **STU-03**: A voltage-stability margin is computed for each city.
- [ ] **STU-04**: Dispatched capacity per city is recorded as the lower of the applied DLR
  rating and the voltage-stability limit, in amps and MW, with which of the two set it.

### Write-back

- [ ] **WB-01**: Every run writes one run record: start and end time, case identifier, per-city
  rating used with its source (`city_rating` row or static fallback), outcome (ok, fallback,
  failed), and any error. A run record is written even when the study fails.
- [ ] **WB-02**: A run's results are either all written or the run is marked failed; no partial
  result set is left looking complete.

### Scheduling

- [ ] **SCH-01**: Windows Task Scheduler runs the job hourly on the teammate's licensed laptop,
  with no overlapping runs.
- [ ] **SCH-02**: An hour with no run (laptop off or asleep) is visible as a gap in the run
  records, through a stated query or check.

### Verification

- [ ] **TST-01**: Tests on the Mac against a fake `psspy` cover static fallback, the mapping
  check, a non-converging load flow, and write-back (including a failed run).
- [ ] **TST-02**: One real end-to-end run on the laptop against Power Systems' case writes a
  run record and results that can be read back from the database.
- [ ] **DOC-01**: A setup guide for the laptop (PSS/E and Python versions, credentials, Task
  Scheduler entry) lets someone else install and start the hourly job.

## Future Requirements

- Always-on host so studies run every hour, not only while the laptop is on.
- Dashboard views of PSS/E results (`docs/frontend/specs/F7-psse-integration.md`).

## Out of Scope

| Item | Reason |
|------|--------|
| Dashboard ⇄ PSS/E or dashboard display of results | User excluded it; Software sub-team scope (F7) |
| Standalone migration in this workstream | Tables and grants ship with production-pipeline Phase 6, built in parallel |
| Choosing or building the grid case or branch mapping | Power Systems owns their case and supplies the mapping |
| Always-on hourly guarantee | Only a teammate's laptop is available; gaps are recorded instead |
| Editing `input-provenance` PSSE-01/02 | User chose to leave that workstream untouched; overlap noted here only |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|

**Coverage:**
- v1 requirements: 17 total
- Mapped to phases: 0 (filled by roadmap)

---
*Requirements defined: 2026-10-26*
*Last updated: 2026-10-26 after initial definition*
