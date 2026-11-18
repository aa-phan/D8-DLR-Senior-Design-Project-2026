# Requirements: v1.7 pandapower Solver

**Defined:** 2026-11-16
**Core Value:** The dashboard always has fresh hourly power-flow results for each city's rating, without depending on a licensed PSS/E machine.
**Research:** `research/SUMMARY.md` (this workstream).

## v1 Requirements

### PSS/E reference session (PSE)

- [ ] **PSE-01**: A teammate can run one scripted, read-only session on a licensed PSS/E machine that exports the 39-bus case's network data (buses, loads, shunts, machines with limits and setpoints, every branch and two-winding transformer with its ratings) to a private text file, and returns a masked report of what was exported.
- [ ] **PSE-02**: The same session records PSS/E's load-flow solution settings that affect agreement (reactive-limit handling, tap and switched-shunt adjustment, mismatch tolerance, iteration limit) and the three scaling details (whether total generation includes the swing machine, whether machines are clamped at their limits, whether the increment form scales Q with P).
- [ ] **PSE-03**: The same session exports a private reference solution: every bus voltage and every branch flow for the base case of each city's scaled copy, and for each screened outage.
- [ ] **PSE-04**: Nothing from the session (network data, reference solution, mapping targets, bus numbers) is committed to the public repository; the ignore rules and a secret/identifier scan are in place before any exported file reaches the owner's machine.

### Network parity (NET)

- [ ] **NET-01**: The job builds a pandapower network from the PSS/E export, keeping PSS/E bus numbers as bus indices and `from-to-circuit` names for branches, so the private mapping and contingency ids work unchanged; it refuses (fails closed) any record type it does not understand.
- [ ] **NET-02**: A parity report compares the built network with the PSS/E export element by element (counts, line vs transformer classification, ratings, limits, setpoints) and lists every difference; it must show none before study code relies on the network.
- [ ] **NET-03**: The base-case load flow of each city's scaled copy matches the PSS/E reference solution: every bus voltage within 0.01 pu and every branch flow within 2% (with an absolute floor for lightly loaded branches).

### Study engine (ENG)

- [x] **ENG-01**: A `PandapowerApi` provides the same methods the study code uses from `PsseApi`, chosen through one new factory argument in `study.py`, so `study`, `contingency`, `margin`, `violations` and `dispatch` run unchanged; a test pins the method names and signatures to `PsseApi`.
- [x] **ENG-02**: A city's rating is applied as a current limit per circuit and line loading is read on the current basis, matching the PSS/E study's default; a mapping that asks for a basis pandapower cannot reproduce is refused.
- [ ] **ENG-03**: A load flow counts as converged only if it raises no error, leaves no in-service bus without a voltage, and leaves no bus below the collapse limit; an outage that islands part of the grid becomes a `non_convergence` row, as in PSS/E.
- [ ] **ENG-04**: Each city, each outage and each margin step solves a fresh copy of its base network; no result is ever read after a failed solve.
- [ ] **ENG-05**: The pandapower solve settings (reactive limits, iteration limit, tolerance) are set from the values recorded in PSE-02 and stored with each run.
- [ ] **ENG-06**: A full four-city study runs end to end on a throwaway local database with the placeholder mapping, with no access to live data.

### Results storage (DB)

- [ ] **DB-01**: One additive migration adds a `solver` column (`psse` or `pandapower`, default `psse` so the existing 19 runs and the unchanged PSS/E job stay valid) and a `solver_version` column to `psse_run`, and allows a `pp-` run-id prefix tied to `solver = 'pandapower'` by a check constraint.
- [ ] **DB-02**: The pandapower job writes through the existing all-or-nothing writer as `dlr_psse_writer`, tagging every run with its solver; a pandapower run can never be stored as `psse`.
- [ ] **DB-03**: The gap check reports missing hours per solver, so a PSS/E run in an hour cannot hide a missing pandapower hour, and PSS/E gaps while its machine is offline are listed separately.

### Agreement (AGR)

- [ ] **AGR-01**: A read-only replay runs each recorded PSS/E run through pandapower using that run's stored ratings and the same mapping (matched by its recorded hash), and writes nothing to the database.
- [ ] **AGR-02**: The replay passes when, for each replayed run, the set of overloads, voltage violations and non-converged outages per outage is the same, and margins and dispatched capacity agree within 2%; near-limit elements are reported as borderline rather than failing.
- [ ] **AGR-03**: The agreement report states how many runs and how many non-empty comparisons it checked, the largest deviation even on a pass, and which runs were excluded and why; a deliberate mismatch test proves it can fail.
- [ ] **AGR-04**: Detailed agreement output stays on the owner's machine; anything printed in GitHub Actions is counts and pass/fail only.

### Hourly operation (OPS)

- [ ] **OPS-01**: A GitHub Actions workflow runs the pandapower job once an hour at :20 UTC, triggered by the existing cron-job.org pattern, main branch only, with its own concurrency group and a timeout under one hour.
- [ ] **OPS-02**: The workflow reads the writer connection, the ratings read settings and the private mapping from GitHub secrets, writes the mapping only to the runner's temporary folder, and never prints a secret, a bus number or a study value to the public log.
- [ ] **OPS-03**: The workflow first runs as a dry run (no writes), and writes to the live tables only after NET-03 and AGR-02 pass.
- [ ] **OPS-04**: A written retention decision for the permanent result rows (about 24 row sets a day) exists before live writes begin.
- [ ] **OPS-05**: Results land in Supabase for 24 consecutive hourly slots, shown by the per-solver gap check.

### Dashboard access (VIEW)

- [ ] **VIEW-01**: A read-only view returns, per city and per solver, the newest complete result: dispatched capacity, its limiting factor (rating or voltage), the solver, the study time, its age and a stale flag; it exposes no run ids, hashes, bus numbers or detail fields.
- [ ] **VIEW-02**: The dashboard's key can read that view and nothing else of the four result tables, which stay private; the exposure checks (`verify_exposure.sql` and its test) are updated to match.
- [ ] **VIEW-03**: The dashboard requirements' DEF-01 section (software-dashboard workstream) is updated to say the blockers are cleared, naming the view and its columns.

## v2 Requirements

- **AGR-05**: Re-run the agreement check whenever new PSS/E runs exist.
- **ENG-07**: Transformer, generator and multi-element outages, in both solvers.
- **OPS-06**: An external freshness alarm if pandapower results stop arriving.
- **DB-04**: A separate CI-only writer role, if the shared role becomes a problem.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Building the dashboard | The Software team owns it; this milestone only provides the data |
| Replacing or changing the PSS/E job's behaviour | PSS/E stays the industry reference; only default-preserving additions |
| Distributed slack, OPF, DC flow, pandapower's line-temperature model | Not what the PSS/E study does; would break agreement |
| Tuning network parameters to force agreement | Hides real differences; agreement must come from identical data |
| A pandapower-backed fake `psspy` | Rejected in research; a parallel `PandapowerApi` is simpler and safer |
| Committing the network export, reference solution or mapping | Public repository; the vendor case's licence is unverified |
| Using pandapower's built-in `case39()` for production | It differs from the PSS/E copy (branch classification, bus numbering); it is a test fixture only |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PSE-01 | Phase 1 | Pending |
| PSE-02 | Phase 1 | Pending |
| PSE-03 | Phase 1 | Pending |
| PSE-04 | Phase 1 | Pending |
| NET-01 | Phase 1 | Pending |
| NET-02 | Phase 1 | Pending |
| NET-03 | Phase 1 | Pending |
| ENG-01 | Phase 2 | Complete |
| ENG-02 | Phase 2 | Complete |
| ENG-03 | Phase 2 | Pending |
| ENG-04 | Phase 2 | Pending |
| ENG-05 | Phase 2 | Pending |
| ENG-06 | Phase 2 | Pending |
| DB-01 | Phase 3 | Pending |
| DB-02 | Phase 3 | Pending |
| DB-03 | Phase 3 | Pending |
| AGR-01 | Phase 4 | Pending |
| AGR-02 | Phase 4 | Pending |
| AGR-03 | Phase 4 | Pending |
| AGR-04 | Phase 4 | Pending |
| OPS-01 | Phase 5 | Pending |
| OPS-02 | Phase 5 | Pending |
| OPS-03 | Phase 5 | Pending |
| OPS-04 | Phase 5 | Pending |
| OPS-05 | Phase 5 | Pending |
| VIEW-01 | Phase 6 | Pending |
| VIEW-02 | Phase 6 | Pending |
| VIEW-03 | Phase 6 | Pending |

**Coverage:**
- v1 requirements: 28 total
- Mapped to phases: 28 (Phase 1: 7, Phase 2: 6, Phase 3: 3, Phase 4: 4, Phase 5: 5, Phase 6: 3)
- Unmapped: 0

---
*Requirements defined: 2026-11-16*
*Last updated: 2026-11-16 after roadmap creation (traceability filled)*
