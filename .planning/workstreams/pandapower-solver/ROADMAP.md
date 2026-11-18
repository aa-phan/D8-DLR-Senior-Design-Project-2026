# Roadmap: Dynamic Line Rating (DLR) System

## Milestones

- 🚧 **v1.7 pandapower Solver** - Phases 1-6 (in progress)

## Overview

The hourly per-city grid study (load flow, N-1 screen, voltage-stability margin, dispatched
capacity) currently runs only on a teammate's licensed PSS/E laptop, and that job is paused until
an always-on licensed host exists. This milestone adds a second, open-source solver, pandapower,
that runs the same study in GitHub Actions every hour and writes into the same four `psse_*`
result tables, tagged by a new `solver` column. PSS/E stays the industry reference and its job
does not change. The dashboard then reads one narrow view of the newest result per city.

The study code (`study`, `contingency`, `margin`, `violations`, `dispatch`, the run record and the
writer) is solver-neutral, so the build is additive: a new `PandapowerApi` behind one factory
argument, one additive migration, one hourly workflow, one read-only view. The real risk is not
the code. It is whether the pandapower network is identical to the PSS/E copy of the 39-bus case
and whether the two solvers then agree. The roadmap is ordered so that question is answered first
and so that no permanent result row is written, and no figure is exposed to the dashboard, before
it is answered.

Six phases. Phase 1 starts with a session that needs a person at a licensed PSS/E machine. Phases
2 and 3 are independent of each other and can run in parallel. Phase 4 is the agreement check and
is the go-live gate. Phase 5 runs the hourly workflow as a dry run, then live for 24 hours.
Phase 6 is last so that no unverified figure reaches the dashboard.

**External dependencies:**
- **A licensed PSS/E machine and a teammate to run one scripted session on it** (Phase 1,
  PSE-01 to PSE-03). Everything else in Phase 1 (session scripts, ignore rules and scan, parser,
  builder, parity and comparison code on placeholder data) can be built and tested before the
  session happens. The session is the only step in the milestone that needs that machine.
- **Power Systems' private per-city mapping** (Phases 4 and 5): already exists as a private file
  for the PSS/E job; this milestone also stores it as a GitHub secret.
- **The owner applies the migration and the view to the live project** (Phases 3 and 6), as in
  earlier workstreams. The workstream writes and proves the SQL on a throwaway local database
  and checks the live result read-only.
- **The software-dashboard workstream** (Phase 6, VIEW-03): the DEF-01 edit lands in that
  workstream's requirements document and needs coordination on its branch.

### Ordering and gates

- **Parity gates everything.** The PSS/E reference session and network parity come first
  because every later phase depends on the network being the same data as the PSS/E copy
  (MATPOWER's published 39-bus case is a modified copy and is a test fixture only).
- **Two different agreement claims, stated separately.** NET-03 (Phase 1) claims full-state
  agreement on the base case of each city: every bus voltage and every branch flow against a
  private PSS/E reference solution. AGR-02 (Phase 4) claims agreement on the quantities PSS/E
  runs actually stored: violation sets per outage including non-converged outages, margins and
  dispatched capacity. The database holds no full voltage or flow vectors, so the owner's
  voltage and flow tolerances can only be proven by NET-03.
- **Live-write gate.** Rows are permanent (the writer cannot delete). The first live write in
  Phase 5 requires NET-03 passed (Phase 1), AGR-02 passed (Phase 4), the migration applied
  (Phase 3) and the written retention decision (OPS-04).
- **One interaction to plan for.** NET-03 needs the city scaling and a load flow run with the
  PSE-02 settings, before the engine exists. Phase 1 builds a minimal scaling and solve step
  for that comparison. Phase 2 then makes the same logic the engine's `scale_case` and stored
  solve settings (ENG-05), rather than writing it twice.
- **Merge and split decisions.** PSE and NET stay in one phase because the session's output is
  the only input to the parity report and the base-case match, so they share one gate. The
  schema work (DB) stays its own phase, parallel to the engine, because it touches a different
  artifact (SQL and the stdlib `psse_job` package, not the Python 3.12 engine) and would
  otherwise serialize two independent tracks. Dry run and 24-hour soak stay in one phase
  because they are one workflow; the soak is the live-write switch plus a day of observation,
  and the gate above is the boundary between the two stages.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: PSS/E Reference Session and Network Parity** - Private export, settings and reference solution from the licensed machine; a pandapower network proven identical to the PSS/E copy, with nothing committed
- [ ] **Phase 2: PandapowerApi and Study Engine** - The unchanged study code runs a full four-city study on pandapower through one factory argument, with no live data
- [ ] **Phase 3: Solver Tag, Migration and Per-Solver Gaps** - One additive migration and a tagged writer path so both solvers' runs live side by side and gaps are reported per solver
- [ ] **Phase 4: Replay and Agreement Check** - A read-only replay of recorded PSS/E runs through pandapower, with an honest report that can fail; the go-live gate
- [ ] **Phase 5: Hourly Workflow, Dry Run and Live Soak** - The hourly GitHub Actions job runs as a dry run, then writes live for 24 consecutive hours
- [ ] **Phase 6: Dashboard Read Access and DEF-01** - One read-only view of the newest result per city and solver, and the dashboard requirements updated to say the blockers are cleared

## Phase Details

### Phase 1: PSS/E Reference Session and Network Parity

**Goal**: A teammate-run, read-only session on the licensed machine produces the private network data, the load-flow settings and a reference solution, and a pandapower network built from that data matches the reference, with nothing from the session in the public repository.
**Depends on**: Nothing (first phase). PSE-01 to PSE-03 need a person at a licensed PSS/E machine; the session scripts, ignore rules and scan, parser, builder and comparison code can be built and tested on placeholder data before the session.
**Requirements**: PSE-01, PSE-02, PSE-03, PSE-04, NET-01, NET-02, NET-03
**Success Criteria** (what must be TRUE):
  1. Before any exported file reaches the owner's machine, the ignore rules and the secret and identifier scan are in place, and the scan passes on the clean tree and flags a planted placeholder identifier.
  2. A teammate runs one scripted, read-only session on the licensed machine and returns a masked report listing what was exported: the network data (buses, loads, shunts, machines with limits and setpoints, every branch and two-winding transformer with its ratings), the load-flow solution settings and the three scaling details, and a reference solution for the base case of each city's scaled copy and for each screened outage. No exported file is committed.
  3. The builder produces a pandapower network from the export keeping PSS/E bus numbers as bus indices and `from-to-circuit` names for branches, and stops with a clear failure on any record type it does not understand.
  4. The parity report compares the built network with the export element by element (counts, line versus transformer classification, ratings, limits, setpoints), lists every difference, and shows none.
  5. The base-case load flow of each city's scaled copy matches the PSS/E reference: every bus voltage within 0.01 pu and every branch flow within 2% (with an absolute floor for lightly loaded branches).

**Plans**: 9/11 plans executed

Plans:
**Wave 1**
- [x] 01-01-PLAN.md — Leak guard first: ignore rules and a three-layer scanner (path, shape, private needles), working tree and staged (wave 1)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 01-02-PLAN.md — Laptop session spine: call gate, RAW export, verified zip, masked summary, entry script (wave 2)
- [x] 01-05-PLAN.md — pandapower pin behind a blocking legitimacy checkpoint, hash-checked install (wave 2)

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 01-03-PLAN.md — Session reference answers: base, every screened outage and margin point per city (wave 3)
- [x] 01-04-PLAN.md — Session settings and scaling experiments, the PowerShell wrapper and the plain-English guide (wave 3)
- [x] 01-06-PLAN.md — Fail-closed RAW parser and pandapower builder, proven against case39 (wave 3)

**Wave 4** *(blocked on Wave 3 completion)*
- [x] 01-07-PLAN.md — Parity report (NET-02), converted network copy and D-06 evidence (wave 4)
- [x] 01-08-PLAN.md — Minimal scaling, copied solve settings, D-13 comparator and scaling-detail analyser (wave 4)

**Wave 5** *(blocked on Wave 4 completion)*
- [x] 01-09-PLAN.md — Owner commands ingest and check, safe unzip, private-only outputs, laptop-to-Mac seam (wave 5)

**Wave 6** *(blocked on Wave 5 completion)*
- [ ] 01-10-PLAN.md — The PSS/E session with the teammate, then parity and NET-03 on the real data (wave 6, checkpoints)

**Wave 7** *(blocked on Wave 6 completion)*
- [ ] 01-11-PLAN.md — The owner's D-06 decision on the converted network, recorded and carried out (wave 7, checkpoint)

### Phase 2: PandapowerApi and Study Engine

**Goal**: The existing study code (`study`, `contingency`, `margin`, `violations`, `dispatch`) runs a full four-city study on pandapower, chosen through one factory argument, with the island, stale-result and rating-basis traps handled and no access to live data.
**Depends on**: Phase 1 (the network builder and the recorded solve settings). Work can start once the builder runs on the placeholder case; the final solve settings (ENG-05) are filled in when PSE-02 is recorded. Runs in parallel with Phase 3.
**Requirements**: ENG-01, ENG-02, ENG-03, ENG-04, ENG-05, ENG-06
**Success Criteria** (what must be TRUE):
  1. A test fails if any `PandapowerApi` method name or signature differs from `PsseApi`, and `study.py` chooses the solver through one new factory argument while the existing PSS/E tests pass unchanged.
  2. A city's rating is applied as a current limit per circuit and line loading is read on the current basis; a mapping that asks for a basis pandapower cannot reproduce is refused with a clear failure.
  3. A solve counts as converged only if it raises no error, leaves no in-service bus without a voltage and leaves no bus below the collapse limit; an outage that islands part of the grid appears as a `non_convergence` row, as PSS/E records it.
  4. Each city, each outage and each margin step solves a fresh copy of its base network: a test shows that running outages in a different order, or after a failed solve, gives identical results, and that no result is read after a failed solve.
  5. The solve settings (reactive limits, iteration limit, tolerance) come from the values recorded in PSE-02 and are stored with each run, and a full four-city study runs end to end on a throwaway local database with the placeholder mapping and no access to live data.

**Plans**: 3/7 plans executed

Plans:
**Wave 1**
- [x] 02-01-PLAN.md — Solver factory argument in study.py through a registry, PSS/E tests unchanged (wave 1)
- [x] 02-02-PLAN.md — PandapowerApi core: case load, fresh copies, reads, writes, solve outcome mapping (wave 1)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 02-03-PLAN.md — Scaling methods, registration, 14-method signature pin against PsseApi (wave 2)

**Wave 3** *(blocked on Wave 2 completion)*
- [ ] 02-04-PLAN.md — Engine entry point: preflight refusals, placeholder settings, four-city study in memory (wave 3)
- [ ] 02-05-PLAN.md — Study-level proof of island, order and stale-result behaviour on the real solver (wave 3)

**Wave 4** *(blocked on Wave 3 completion)*
- [ ] 02-06-PLAN.md — Database tier: four-city study through job.run_once into a throwaway Postgres (wave 4)
- [ ] 02-07-PLAN.md — Close ENG-05 with the recorded PSE-02 values; needs the laptop session (wave 4, checkpoint)

### Phase 3: Solver Tag, Migration and Per-Solver Gaps

**Goal**: The four result tables can hold PSS/E and pandapower runs side by side, every run carries the solver that produced it, and the gap check shows which solver missed which hour.
**Depends on**: Nothing in this milestone for the migration and the `psse_job` changes (runs in parallel with Phase 2); only the closing tagged-write rehearsal with the pandapower engine needs Phase 2.
**Requirements**: DB-01, DB-02, DB-03
**Success Criteria** (what must be TRUE):
  1. One additive migration on a throwaway local database keeps pre-existing runs valid and tagged `psse` (the column defaults to `psse`), adds the solver version, and accepts a `pp-` run id only with `solver = 'pandapower'`; a deliberately mismatched insert is refused by the database, and the applied v1 migration is not edited.
  2. The pandapower job writes through the existing all-or-nothing writer as `dlr_psse_writer` and stamps every run with its solver; a test shows a pandapower run cannot be stored as `psse`, and the unchanged PSS/E job's existing tests still pass.
  3. With a PSS/E run in an hour and no pandapower run in that hour, the gap check reports that hour as missing for pandapower; PSS/E gaps while its machine is offline are listed separately and do not hide, or get hidden by, pandapower gaps.
  4. After the owner applies the migration to the live project, a read-only check shows the existing runs tagged `psse` and nothing else changed.

**Plans**: TBD

### Phase 4: Replay and Agreement Check

**Goal**: A read-only replay of the recorded PSS/E runs through pandapower shows whether the two solvers agree, in a report that states how much it checked, shows the largest deviation even on a pass, and is proven able to fail.
**Depends on**: Phase 2 (the engine, on the Phase 1 network). Does not need Phase 3. This phase is the go-live gate for Phase 5.
**Requirements**: AGR-01, AGR-02, AGR-03, AGR-04
**Success Criteria** (what must be TRUE):
  1. The replay runs each recorded PSS/E run through pandapower using that run's stored ratings and the same mapping (matched by its recorded hash), and a check shows it writes nothing to the database.
  2. A replayed run passes only when its set of overloads, voltage violations and non-converged outages is the same per outage and its margins and dispatched capacity agree within 2%; near-limit elements are reported as borderline, not as failures.
  3. The agreement report states how many runs and how many non-empty comparisons it checked, the largest deviation even on a pass, and which runs were excluded and why.
  4. A deliberate mismatch test makes the replay fail, proving the check can fail.
  5. Detailed output stays on the owner's machine; the output printed in CI mode contains counts and pass or fail only, and a test scanning it finds no identifier or study value.

**Plans**: TBD

### Phase 5: Hourly Workflow, Dry Run and Live Soak

**Goal**: The pandapower job runs every hour in GitHub Actions with no laptop involved, first as a dry run that writes nothing, then, once the gate has passed, writing live results for 24 consecutive hours without anything private reaching the public log.
**Depends on**: Phase 2 (engine), Phase 3 (migration and tagged writer), Phase 4 (agreement). The first live write also requires NET-03 (Phase 1) and AGR-02 (Phase 4) to have passed.
**Requirements**: OPS-01, OPS-02, OPS-03, OPS-04, OPS-05
**Success Criteria** (what must be TRUE):
  1. The workflow, poked by the existing cron-job.org pattern, runs once an hour at :20 UTC on the main branch only, with its own concurrency group and a timeout under one hour; a run dispatched from another branch does not execute the job.
  2. The writer connection, the ratings read settings and the private mapping come from GitHub secrets, the mapping is written only to the runner's temporary folder, and a leak check over a captured public log finds no secret, bus number or study value.
  3. The workflow first runs as a dry run that writes nothing (the four result tables are unchanged afterward), and live writing is switched on only after NET-03 and AGR-02 have passed, as a recorded owner decision.
  4. A written retention decision for the permanent result rows (about 24 row sets a day) exists before the first live write.
  5. The per-solver gap check shows a pandapower result for 24 consecutive hourly slots.

**Plans**: TBD

### Phase 6: Dashboard Read Access and DEF-01

**Goal**: The dashboard's key can read the newest complete result for each city and solver through one read-only view and nothing else, and the dashboard requirements say the blockers are cleared.
**Depends on**: Phase 3 (the solver column) and Phase 5 (verified, live results). Last on purpose: until agreement and the soak pass, no unverified figure should be readable by the dashboard.
**Requirements**: VIEW-01, VIEW-02, VIEW-03
**Success Criteria** (what must be TRUE):
  1. Using the dashboard's key, the view returns for each city and each solver the newest complete result: dispatched capacity, its limiting factor (rating or voltage), the solver, the study time, its age and a stale flag.
  2. A result older than the staleness threshold shows the stale flag, and a fresh result does not.
  3. The view exposes no run ids, hashes, bus numbers or detail fields: a test compares its column list to a whitelist.
  4. With the same key, reading any of the four result tables is refused, and the exposure checks (`verify_exposure.sql` and its test) are updated and pass.
  5. The DEF-01 section of the software-dashboard workstream's requirements says the blockers are cleared and names the view and its columns.

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6. Phases 2 and 3 are independent and may run in parallel once Phase 1's builder works on the placeholder case; Phase 4 needs Phase 2; Phase 5 needs Phases 3 and 4 plus the NET-03 and AGR-02 passes; Phase 6 needs Phases 3 and 5.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. PSS/E Reference Session and Network Parity | 9/11 | In Progress | - |
| 2. PandapowerApi and Study Engine | 3/7 | In Progress | - |
| 3. Solver Tag, Migration and Per-Solver Gaps | 0/TBD | Not started | - |
| 4. Replay and Agreement Check | 0/TBD | Not started | - |
| 5. Hourly Workflow, Dry Run and Live Soak | 0/TBD | Not started | - |
| 6. Dashboard Read Access and DEF-01 | 0/TBD | Not started | - |
