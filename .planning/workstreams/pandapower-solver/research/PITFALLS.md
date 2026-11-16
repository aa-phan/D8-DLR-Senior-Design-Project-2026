# Pitfalls Research

**Domain:** Adding a pandapower solver (hourly, GitHub Actions) beside an existing PSS/E per-city 39-bus study, writing to the same append-only Supabase tables, with an agreement check against recorded PSS/E runs
**Milestone:** v1.7 pandapower Solver (subsequent milestone, existing repo)
**Researched:** 2026-11-16
**Confidence:** HIGH on pandapower conversion/solver behaviour and GitHub/Supabase platform rules (verified empirically in a scratch venv, pandapower 3.2.2, and against official docs); MEDIUM on PSS/E-side semantics (read from this repo's own code, not from a PSS/E install); the PSS/E copy of the 39-bus case was NOT inspected (it is private), so every "the PSS/E copy may differ" item is a risk to be confirmed in Phase A, not a finding.

Public-repo note: this file contains no credentials, hosts or live results. Numbers quoted come from the public MATPOWER `case39` as shipped in pandapower, never from the private case, the private mapping or the database.

## How to read the phase labels

No roadmap exists yet. The labels below are suggested; the roadmapper may merge or rename them, but the dependency order matters (see the last section).

| Label | Suggested phase |
|-------|-----------------|
| A | Network parity: build the pandapower net from the PSS/E case data and prove the base case matches |
| B | Study engine: scaling, base flow, N-1 outages, voltage-margin search, dispatched capacity, determinism |
| C | Schema migration and write path (`solver` column, writer, dry-run) |
| D | Hourly workflow: trigger, concurrency, secrets, monitoring, gap check |
| E | Agreement check (replay of recorded PSS/E runs) |
| F | Dashboard view and DEF-01 doc update |
| G | Cross-cutting ops: retention, runbook, leakage guards |

Confidence tags: [HIGH] verified by experiment or official doc, [MEDIUM] read from code or a single source, UNVERIFIED = inference that needs a check.

## Critical Pitfalls

### Pitfall 1: Treating MATPOWER `case39` as "the" 39-bus case (data parity)

**What goes wrong:**
pandapower's built-in `case39` (and `from_mpc` of `case39.m`) is MATPOWER's re-worked copy, not a neutral reference. MATPOWER's own header says it added or changed: line flow limits (from a secondary source), Qmin/Qmax for some generators, Vg for bus 39, Pmin/Pmax values, a bus 39 data set, voltage limits 0.94 to 1.06, and a re-solved power flow. It also notes that taking Vg from bus data "results in two binding Q limits" in the base solution. The PSS/E copy on the laptop (Power Systems' case) can differ in any of: RATEA/B/C (MATPOWER rateA is an addition, and rateC is 2500 on transformers), generator Q limits, Vg and which bus regulates (remote regulation cannot be expressed in MATPOWER), transformer ratio and its base (PSS/E winding ratio vs MATPOWER `ratio`, CW/CZ/CM codes), shunts (fixed and switched), load values and load type (PSS/E loads may carry constant-current and constant-admittance parts), base kV per bus, and system MVA base. Results from the two solvers would then differ because the inputs differ, not because pandapower is wrong, and nobody could tell which.

**Why it happens:**
STATE.md already flags this ("matching the network data is likely the first real work"). The risk is that the plan treats it as a one-line "load case39" task and discovers the gap only when the agreement check fails.

**How to avoid:**
- Make network parity its own gate (Phase A) that must pass before any study logic is written. Export the PSS/E case on the laptop with the existing read-only bulk reads (`bus_table`, `branch_loading`, plus machine, load, shunt and transformer data from a RAW export, which needs no new psspy surface beyond the export), build the pandapower net from that export, not from MATPOWER, and compare table by table (bus base kV, load P/Q, generator P/Q limits/Vg, branch r/x/b, tap, ratings, shunt Q).
- Gate: a solved base case, with the stored PSS/E bus voltages and branch flows from the same export, agrees within the milestone tolerances (0.01 pu, 2%) before moving on. This is a stronger test than the replay in Pitfall 2 because it uses full bus and branch vectors, which the database does not hold.
- If the case data cannot be published (public repo), keep it out of the repo: either a private delta over the public MATPOWER base, or a gzip+base64 secret (see Pitfall 14 for the 48 KB limit). Decide the delivery path in Phase A, not Phase D.
- Hash the network file the way `case_sha256` hashes the PSS/E case, and store that hash on every row, so a changed network is visible in the data.

**Warning signs:**
Base-case voltages differ by more than about 1e-3 pu or any branch flow by more than 1 percent before any outage is applied; Q at a generator in pandapower is at a limit that PSS/E does not show; total losses differ.

**Phase to address:** A (gate), then E (re-verified by replay).
**Confidence:** [HIGH] for the MATPOWER modifications (MATPOWER `case39.m` header, fetched 2026-11-16); UNVERIFIED for what differs in the private PSS/E copy.

---

### Pitfall 2: False agreement (comparing the two solvers on different inputs, or on nothing)

**What goes wrong:**
The agreement check can pass or fail for reasons unrelated to solver quality.
1. **Inputs re-derived instead of replayed.** If the replay recomputes MVA from amps with its own kV, power factor or bundle count, it feeds pandapower a rating PSS/E never saw. Replay must use the stored per-city values (`ratings_used`, and `applied_mva`, `line_voltage_kv`, `subconductors_per_phase` in the dispatched rows), not config constants.
2. **Different study definition.** The study settings (voltage bands, thermal basis, outage scope, hops, transfer step) and the per-city scaling targets live in the private mapping; the run row stores only `mapping_sha256`. The 19 recorded runs span the Phase 4 change to per-city scaling (code comments date it 2026-11-11), so older runs were a different study. Replaying all 19 through one pandapower study will disagree by construction; replaying with a changed mapping will "agree" with a study PSS/E never ran.
3. **Only violations are stored.** A clean contingency has no row, and bus voltages and branch flows are not stored except in violation rows and the per-city minimum voltage. "Same violation set per outage" is therefore set equality over sparse data: an outage pandapower did not solve looks identical to a clean outage unless `non_convergence` rows and `n_contingencies` are compared too. "Voltages within 0.01 pu" can be tested only at the buses that appear in stored rows.
4. **Vacuous agreement.** If most of the 19 runs have empty violation sets, "empty equals empty" passes for any solver. The number of runs with a non-empty set is not known (the database was not queried for this research).
5. **Limit-boundary flips.** An element within solver tolerance of its limit (for example 99.99 vs 100.01 percent) puts it in or out of the set on a rounding difference. Strict set equality will flap.
6. **Rows with no comparable truth.** `failed` runs have no result rows. `fallback` runs used the static rating, which is a valid input but must be replayed as such.

**How to avoid:**
- Filter replay to runs whose `mapping_sha256` and `job_version` identify the study definition being replayed; report skipped runs and why.
- Compare in a fixed order and fail loudly on shape: same `n_contingencies`; same set of `non_convergence` contingencies; same violation keys (contingency, kind, element); then values (0.01 pu, 2 percent).
- Add an epsilon band: an element within the tolerance of its limit in either solver is "marginal", reported but not a set mismatch.
- Require a minimum count of non-empty violation sets and of runs per city in the replay corpus, or add laptop-produced PSS/E reference runs at deliberately stressed ratings (a few extra permanent rows, or better a file kept off the database) so the check has teeth. Make "agreement passed with N non-empty comparisons" the reported result, not a bare pass.
- Do the full-vector check in Phase A (Pitfall 1) so the sparse replay is a second line, not the only one.
- The replay must write nothing to the database (Pitfall 16).

**Warning signs:** a pass on the first try; a pass with zero or one non-empty comparison; disagreement concentrated in the oldest runs; agreement that does not change when the mapping is altered.

**Phase to address:** E (design the check), A and B (inputs it relies on).
**Confidence:** [HIGH] on what is stored (migration DDL, `contract.py`, `contingency.py` read); UNVERIFIED on how many recorded runs have violations.

---

### Pitfall 3: `from_mpc` / `from_ppc` conversion traps

All verified in pandapower 3.2.2 by reading `from_ppc.py` and running the converted public `case39`.

| Trap | What happens | Prevention |
|------|--------------|------------|
| Bus index is 0-based, `name` is empty after `from_mpc` | Bus N becomes index N-1 (case39: index 0..38). The private mapping uses PSS/E bus numbers. An off-by-one silently attaches a city to the wrong bus. | Keep one explicit crosswalk, PSS/E bus number to pandapower index, built from data (not arithmetic), and assert it round-trips. Never index `net.bus` by a PSS/E number. |
| `ratio` equal to 0 or 1 becomes a **line**, anything else a **trafo** | In `case39`, branch 23-36 has ratio 1.0 and becomes a line, while PSS/E treats it as a transformer. The outage candidate set differs (the PSS/E job screens only non-transformer lines and `branch_chng_3` refuses transformers). pandapower logs "11 branches are considered as trafos ... but connect same voltage levels". | Classify branches from the PSS/E export (transformer flag), not from ratio. Build the outage list from the PSS/E classification and map by key. |
| `rateA == 0` becomes `max_i_ka = 99999` (and trafo `sn_mva = 99999`) | An unrated branch becomes unlimited, logged only at debug level. A zero rate in PSS/E would be "no limit" too, but the two solvers must agree on which branches are unlimited. | Fail the build if any monitored branch has rate 0 or 99999; log a table of rated branches in the parity report. |
| `max_i_ka = rateA / baseKV(to bus) / sqrt(3)` | Uses the TO-bus base kV. For a line this equals the from-bus kV. For a transformer the kV differ and `sn_mva` (MVA) is used, not kA. The job's `units.py` uses the from-bus kV. | Assert equal base kV at both ends for every line the job rates. Set mapped-line ratings directly as `max_i_ka = circuit_amps / 1000`. |
| One generator per bus becomes `gen`; the second generator on a bus, and any generator on a PQ bus, become **`sgen`** | A second machine at a PV bus loses voltage control and becomes fixed PQ. Vg is taken from the first generator on the bus. | Check machine counts per bus in the parity report; combine or model explicitly; verify no unexpected `sgen`. |
| The reference-bus generator becomes `ext_grid` (slack), with `max/min_q_mvar` stored but not enforced in `runpp` | Slack P and Q are outputs. Matches PSS/E's swing behaviour, but only if the same bus is the swing. | Confirm the swing bus equals the PSS/E swing bus; assert exactly one slack. |
| Remote voltage regulation, switched shunts, tap-stepping transformers | MATPOWER/`from_ppc` has no representation; pandapower needs explicit controllers. PSS/E `fnsl` options can adjust taps and switched shunts (see Pitfall 6). | Parity report lists every such device in the PSS/E case; either model it or prove it is fixed in the stored solution. |
| `f_hz=50` default in `from_mpc` | Cosmetic for a plain load flow (b to c_nf and back round-trips), but wrong for a 60 Hz system and wrong the moment a frequency-dependent feature is used. | Pass `f_hz=60`. |
| Trafo `tap_pos` = sign(ratio-1), `tap_step_percent` = |ratio-1| x 100 | Fine for a fixed ratio, but a later "change tap" edit will behave unexpectedly. | Treat taps as fixed data; do not edit them in study code. |

**Phase to address:** A. **Confidence:** [HIGH].

---

### Pitfall 4: Ratings units (amps per conductor vs per circuit vs MVA vs kA, and which loading basis)

**What goes wrong:**
- The city rating is amps **per conductor**; the PSS/E path multiplies by `subconductors_per_phase` (2, 2, 2, 1 by city in `constants.py`) to get **per circuit** amps, then `circuit_mva = sqrt(3) x kV x circuit_amps / 1000`, with no power factor. pandapower `max_i_ka` is a per-circuit current in **kA**. Feeding the per-conductor figure halves the rating for a bundled city, and feeding MVA where kA is expected is off by a factor of about 600 at 345 kV. Example with public numbers: 1825 A used as `max_i_ka` of 1.825 gives about 1090 MVA at 345 kV; as a two-conductor circuit it is about 2181 MVA.
- `dispatched_mw` applies a power factor (0.95); `applied_mva` and the rating never do. The migration comments say per-circuit values are not comparable with `city_rating.rating_mw` (per conductor). Reusing `rating_mw` by mistake is a silent 2x/0.95 error.
- **Loading basis.** The PSS/E study uses `thermal_basis = current` (percent of current rating, larger end). pandapower's `loading_percent` is also current-based. On the unmodified public `case39` base solution, current-basis maximum loading was 73.4 percent while an MVA-basis calculation of the same flows gave 76.4 percent: a 3 point difference, larger than the 2 percent agreement tolerance. Choosing the wrong basis consumes the whole tolerance.
- `df` (derating) and `parallel` multiply into pandapower's loading denominator; leave both at 1 or the rating silently changes.
- `loading_percent` of an out-of-service line is 0.0 (not NaN), so a tripped line looks like a healthy, unloaded one if the code reads it.
- Rate sets: PSS/E rate A/B/C vs MATPOWER rateA/B/C. The job writes and checks RATEA only.

**How to avoid:** One conversion module with unit tests copied from `units.py` cases (per-conductor to per-circuit to MVA to kA) run on both solver paths; name variables with their unit and basis (`amps_circuit`, `mva_circuit`, `max_i_ka`); take thermal checks from `loading_percent` with `trafo_loading="current"` and say so in the output (`details`); skip out-of-service elements explicitly.

**Warning signs:** capacities off by 2x, 0.95x, or about 600x; loading differs by about 3 percent at every branch uniformly; a tripped line appearing in results.

**Phase to address:** B (conversion module), E (verify on stored `applied_mva`).
**Confidence:** [HIGH] (experiment on public case39; `units.py`, `migration.sql` comments).

---

### Pitfall 5: Slack, generator dispatch and `scal_2` scaling semantics

**What goes wrong:**
The PSS/E job scales the whole case to a per-city target total load and total generation with `scal_2` (new-total mode, constant P/Q so each load keeps its power factor), on a fresh copy of the case per city, then reads the totals back and requires a match within 1e-3 and a scale factor within 0.05 to 20. `read_totals` reads the case's totals before the solve, so the "generation total" includes the swing machine's **stored** P from the PSS/E case file. In pandapower the slack (`ext_grid`) has no stored P: it is a solution output. Reproducing "scale generation to the target" therefore needs an explicit, written definition (which machines scale, whether the slack's PSS/E-stored P is included as a fixed number, how the post-solve mismatch lands on the slack). Different choices give different slack P and different losses allocation, shifting flows and voltages. Other differences: how `scal_2` treats machines at limits or out of service, whether constant-current/admittance load parts scale, and whether the generation target is hit before or after the solve. Scaling "in place" on one net for four cities, or scaling twice, compounds (PSS/E reloads the saved case for each outage and each transfer step to avoid exactly this).

**How to avoid:**
- Write the scaling definition down from the PSS/E side first (the existing study docs and the SCALE_LAYOUT evidence) and implement it as one function with a read-back check equal to the existing one (totals within 1e-3, factor bounds).
- Deep-copy the network per city and per outage, never mutate the shared net; never chain `init="results"` across cases.
- Test on a case where the answer is known: replay one recorded run per city and compare slack P and losses as well as capacity.
- Confirm on the laptop what scal_2 does to the swing machine and to out-of-range machines (UNVERIFIED here; the manual excerpt available to this research did not state it).

**Warning signs:** slack P or losses differ by more than a percent between solvers at the same targets; different results when the cities are run in a different order.

**Phase to address:** B. **Confidence:** [HIGH] on pandapower side and on the code's `read_totals` behaviour; UNVERIFIED for the swing-machine rule inside `scal_2`.

---

### Pitfall 6: Q limits, solver options and convergence differences

**What goes wrong:**
- `runpp(enforce_q_lims=False)` is the **default**. With it off, a generator can end far outside its Q limits and pandapower still reports success. In an experiment on public `case39` with tightened Q limits, 7 of 9 generators ended outside their limits with the default.
- With `enforce_q_lims=True`, pandapower documents that it runs "a second loadflow" if limits are violated. It is not documented as an iterate-until-consistent loop, so a generator that violates only after the second pass must be re-checked by the caller (`res_gen.q_mvar` against `min_q_mvar`/`max_q_mvar`). It also works only with `algorithm="nr"`. Squeezing the limits harder in the same experiment made the Newton solve fail with the default 10 iterations.
- Even for unmodified `case39`, enforcing limits changes the base solution (max 5e-4 pu in voltage, and the two MATPOWER-noted binding generators move to their limits). PSS/E applies var limits by its own rule, and the PSS/E `fnsl` options array also controls tap stepping, area interchange, switched shunts, flat start and non-divergent solution. Which of these the existing job uses is controlled by the private mapping (`study.solve.options`, null means defaults). A solver that enforces a different subset gives different voltages. The PSS/E defaults were not verifiable from the sources reachable in this research (a forum source says tap stepping defaults to on; UNVERIFIED).
- Convergence: pandapower `max_iteration="auto"` is 10 for Newton-Raphson, `tolerance_mva=1e-8`, `init="auto"` becomes a DC start when `calculate_voltage_angles` is true. PSS/E's own mismatch tolerance and iteration limit differ. Stressed post-outage points can converge in PSS/E and fail in pandapower at 10 iterations (or the reverse), producing false `non_convergence` rows.

**How to avoid:** Decide the Q-limit rule from what the PSS/E study actually does, then set `enforce_q_lims` explicitly and post-verify limits; raise `max_iteration` (30) and keep `tolerance_mva` explicit; record the options used in `details`; test convergence on the stressed outages from the recorded runs; document every `fnsl` option the job uses and reproduce each or list it as a known difference with a measured effect.

**Phase to address:** A (confirm PSS/E settings), B (implement), E (measure).
**Confidence:** [HIGH] for pandapower behaviour (docs and experiment); UNVERIFIED for the PSS/E option defaults.

---

### Pitfall 7: Islanding, NaN results and non-convergence reporting

**What goes wrong:**
pandapower does not always raise on a bad outage. Verified on public `case39`:
- Tripping 2 of the 35 lines islands a bus (4 buses and 1 bus respectively): `runpp` returns, `net.converged` is True, and the islanded buses have NaN voltages.
- Tripping the transformer that connects the slack bus to the network returned `converged` True with 38 of 39 bus voltages NaN.
- Genuine non-convergence **raises** `LoadflowNotConverged`, not a flag.
- PSS/E returns `fnsl` ierr 3 ("buses in island without swing bus") in the islanded case, which the job reports as a `non_convergence` row (and "NaN counts as collapsed" in `contingency._collapsed`).
So the same outage can be a `non_convergence` row in PSS/E and a clean pass in pandapower (NaN compares false against every limit, so no violation is raised). That is a false agreement in the dangerous direction: a worse grid reported as fine.

**How to avoid:** After every solve, check for NaN in monitored bus voltages and branch loadings and map it to the same `non_convergence` row; catch `LoadflowNotConverged` explicitly; also treat collapse (monitored bus below the configured collapse voltage) as the job does; build a test net with a radial bus and a slack-isolating outage, and assert the row; do not rely on `check_connectivity` alone. Reload (deep-copy) the base before each outage, as the PSS/E job does, rather than un-trip and re-solve.

**Warning signs:** an outage with no result row in pandapower but a `non_convergence` row in PSS/E; NaN anywhere in `res_bus`.

**Phase to address:** B (implementation), E (compare `non_convergence` sets).
**Confidence:** [HIGH] (experiment) for pandapower; MEDIUM for PSS/E ierr 3 handling (from `psse_api.py` tables).

---

### Pitfall 8: Voltage-margin (transfer search) differences near the nose

**What goes wrong:**
The PSS/E margin is a plain load-transfer search: raise the sink-bus load at constant P/Q in steps, bisect, with the swing absorbing the increase, stopping on non-convergence, a voltage criterion (0.90 pu post-contingency default), the applied rating, or the base case. Where the bound is the **voltage criterion** the limit is determined by the network and the two solvers should agree. Where the bound is **non-convergence**, the limit depends on each solver's robustness (iteration cap, start point, tolerance) and can differ by a step or more near the nose, which breaks the 2 percent capacity tolerance with no bug. pandapower's default start (DC angles, flat magnitudes) versus PSS/E's start from the saved solved case also differs. The transfer search also needs `distributed_slack` left at False (the swing absorbs) and the same sink buses.

**How to avoid:** Store and compare `bounded_by` (already in the dispatch `details`); compare limits only where both solvers report `voltage_criterion`; treat `non_convergence`-bounded and `dlr_rating`-bounded (a lower bound) results as different classes; use the same step and tolerance from the mapping; warm-start each step from the previous converged step (`init="results"`) only inside the transfer walk, never across outages or cities.

**Phase to address:** B, E. **Confidence:** MEDIUM (code read; pandapower options verified).

---

### Pitfall 9: Non-determinism and dependency drift

**What goes wrong:**
Same inputs gave bitwise-identical voltages on repeated runs on one machine (verified), and `init="results"` after an outage differed from a cold start by only about 7e-11 pu. So the solver itself is deterministic. The risks are around it: an unpinned `pip install pandapower` on every hourly run (pandapower, numpy, scipy, numba and pandas all move; pandapower 3.x already changed APIs versus 2.x), so a behaviour change lands silently mid-series; numba on or off (runners differ from the laptop; pandapower warns when numba is missing and runs "slow"); BLAS threading and solver ordering at the 1e-10 level; set or dict iteration order in outage selection; floating-point bisection landing on different steps; and elements at the limit boundary flipping between hourly runs or between solvers (Pitfall 2).

**How to avoid:** Pin exact versions in a lock file used by the workflow; record `pandapower` version (and numpy/scipy) in the run row (a `solver_version` column in the same migration, rather than reusing `psse_version`); sort outage lists; give the transfer search a fixed step; use hysteresis/epsilon band for limit classification; run the replay with the same pinned versions the hourly job uses; upgrade deliberately with a replay in the same PR.

**Phase to address:** B (determinism), C (version column), D (lock file in workflow), E.
**Confidence:** [HIGH] for same-machine determinism; UNVERIFIED across numpy/scipy versions and platforms.

---

### Pitfall 10: GitHub Actions scheduling (delays, skips, jitter, concurrency, 60-day disable)

**What goes wrong:**
- **This repo has already measured it.** The shadow-collection runbook records that GitHub `schedule:` runs started 3 to 8 hours late, which is why `shadow_collect.yml` and `dlr_live.yml` use `workflow_dispatch` only, fired by an external cron-job.org job. GitHub's docs say scheduled runs "can be delayed during periods of high loads" and queued jobs may be dropped. An hourly requirement cannot be met by `schedule:` alone.
- Repository activity: "In a public repository, scheduled workflows are automatically disabled when no repository activity has occurred in 60 days" (GitHub docs). This repo is public today (`gh repo view` shows public) although the runbook still calls it private. The rule applies to `schedule:`; it matters if a `schedule:` watchdog or backup trigger is added, and external dispatch is, per the wording, not covered (UNVERIFIED for dispatch). Scheduled runs also execute only from the default branch, and dispatch requires the workflow file on the default branch.
- **Dispatch jitter versus the hour-slot rule.** `psse_run.slot_time` must equal the UTC hour floor of `started_at` (a table CHECK). A dispatch fired near an hour boundary can start in the next hour: that hour then has two runs and the previous hour has none, a false gap plus a doubled slot. Observed prior art: the cron-job.org job was found to be set to US Central, not UTC (runbook, observed 2026-10-25), so schedules move by an hour at daylight-saving changes.
- **Concurrency.** With `cancel-in-progress: false` there is still only one pending run: "any existing pending run in the same group is canceled and replaced" (GitHub docs). Two quick dispatches in one hour (for example a manual run plus the cron one) can silently drop one. Different workflows with different groups run in parallel, so the pandapower job and `dlr_live` can overlap. A newer option, `queue: max`, keeps up to 100 pending (not combinable with `cancel-in-progress: true`).
- **Coupling to the city rating.** The job reads the newest `city_rating` row, which is stale after 90 minutes (the `latest_rating` rule). `dlr_live` rows are stamped with the hour slot. If the pandapower job starts at minute :00 together with `dlr_live`, it reads the previous hour's rating; if it starts after about :30 while `dlr_live` is slow or failed, the previous row is more than 90 minutes old and the job silently falls back to the static rating (`fallback_reason = stale`). A low-side fallback is safe (project memory) but would degrade every hourly result unnoticed.
- **Alerting.** A run that never starts produces no failure email; GitHub's workflow-failure email only covers runs that started (the runbook states this about the shadow job).

**How to avoid:**
- Reuse the proven pattern: `workflow_dispatch` only, cron-job.org trigger, `concurrency` group of its own, `timeout-minutes` below the cadence, `if: github.ref == 'refs/heads/main'`, `environment: production`.
- Fire at a minute well inside the hour (for example :15 to :25) so jitter up to about 35 minutes still lands in the intended slot and `dlr_live` has finished; document the minute and keep it in UTC terms.
- Consider `queue: max` or let the job compute its slot from the dispatch time and refuse a second run for a slot that already has an `ok` row for this solver.
- If a `schedule:` backup is added, add a trivial commit or a keep-alive step policy, or do not rely on it.
- Rotate the dispatch token on a calendar (fine-grained tokens expire) and record its expiry in the runbook.

**Warning signs:** two rows in one slot and none in the previous slot; `fallback_reason = stale` appearing every hour; runs missing after a repository quiet period; workflow shown as disabled.

**Phase to address:** D. **Confidence:** [HIGH] (GitHub docs; repo runbook and workflow files).

---

### Pitfall 11: The hourly-gap check cannot see its own missing run, and it ignores the solver

**What goes wrong:**
The existing gap query (`docs/data-science/schema/psse_run_gaps.sql`) lists UTC hours with no `ok`/`fallback` row, with rule 1: several rows in an hour are not a gap. After the migration there are two solvers writing to one table. A PSS/E row in an hour hides a missing pandapower row in that hour, and a clean-looking history could show no gaps while the new solver never ran. The check also runs inside the job (the runbook's own description of the shadow health check: it cannot detect a missing run). The check excludes the current hour and hours before the first run, so it reports gaps after the fact, with up to an hour of delay, and never during an outage of the trigger itself.

**How to avoid:** Add a `solver` filter (or `partition by solver`) to the gap query as part of the migration work, with a test using rows of both solvers in the same hour; run the check from a different trigger than the job (a second cron-job.org call, or the existing Supabase freshness-assertion pattern used for `assert_fresh`) and alarm on "no `ok`/`fallback` row for solver X in the last N minutes", N about 90 to match the staleness rule, instead of per-clock-hour presence; do not let the PSS/E laptop's rows count toward pandapower freshness; define the "full day" acceptance (done criterion) precisely: 24 consecutive slots, each with an `ok` or `fallback` pandapower run, evaluated by the solver-aware query.

**Phase to address:** C (query change with the migration), D (external watchdog).
**Confidence:** [HIGH] (SQL read) for the blind spot; MEDIUM for the watchdog design.

---

### Pitfall 12: Migration on live append-only tables

**What goes wrong:**
- **Default and NOT NULL.** `alter table ... add column solver text not null default 'psse'` is the natural way to tag the existing 19 PSS/E rows without an UPDATE (the writer role has INSERT and SELECT only, and policies exist for INSERT and SELECT only). If the default is later dropped to force explicitness, the unchanged laptop PSS/E writer, which does not know the column, starts failing on every insert. If the default is kept, any writer that forgets `solver` is silently labelled `psse`.
- **The shared writer will do exactly that.** `psse_job.contract.TABLE_COLUMNS` is the explicit column list the writer builds its INSERT from. A pandapower job that reuses `writer.py` and `run_record.py` without adding `solver` inserts rows that get the default `psse`. The dashboard would then show PSS/E-labelled rows produced by pandapower, and the agreement check would compare a solver with itself.
- **Hard-coded run-id pattern.** `psse_run_run_id_ck` requires `^psse-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$`, and `run_id` is the primary key and part of three composite foreign keys. A pandapower run id such as `pp-...` fails the insert. Options: keep the `psse-` prefix (misleading), or replace the constraint with one that allows both prefixes and ties the prefix to the solver.
- **Pinned migration.** The original migration's marked region is pinned by sha256 and tested (`psse_results_migration_test.py`); editing it breaks the test and the "applied exactly this" guarantee. The change must be a new migration file; the schema doc and its tests (`psse_schema_doc_test.py` compares DDL columns and order against the doc) need a v2 doc.
- **Other column semantics.** `psse_version` (PSS/E version string) is the wrong home for a pandapower version; `case_id`, `case_sha256`, `rate_set` have PSS/E meaning; `schema_version` semantics (is this a v2 row schema?). `rate_set` is nullable, `case_id` is required and must not contain a slash.
- **Locks and timing.** `ALTER TABLE` needs a brief exclusive lock; at an hourly insert cadence, run it away from the writers' minute (the PSS/E laptop run time is also unknown). Existing rows are 19, so constraint validation is instant, but the migration must still be idempotent (`add column if not exists`, `drop constraint if exists`) like the existing ones, because `supabase db push --db-url` is run by hand.
- **Irreversibility.** There is no DELETE for the role and no UPDATE, so a wrongly labelled row is permanent unless the owner fixes it by hand as the table owner (possible, but it breaks the "immutable record" promise).

**How to avoid:**
- One new migration that: adds `solver text not null default 'psse'` with a CHECK on the vocabulary (`'psse'`, `'pandapower'`); adds a CHECK tying `solver` to the `run_id` prefix (both directions) so a mislabel fails at insert; relaxes the run-id pattern for the second prefix; adds `solver_version`; adds `solver` to the child tables (or derives it by join, decide once; the view in Phase F needs it cheaply); adds an index suited to "newest per city per solver" (the existing index is on `slot_time` only).
- Keep the default `'psse'` (the laptop job is unchanged by decision) but make the pandapower writer set `solver` explicitly and add a test that fails if `solver` is not in its column list; add the new column to `contract.TABLE_COLUMNS` behind a flag so the PSS/E job's inserts stay byte-identical.
- Rehearse on the project's throwaway-Postgres harness (`psse_local_pg.py`, the pattern used by `psse_schema_pg_test.py`) including an insert as the writer role, an old-style insert without `solver`, a wrong-prefix insert (must fail), and the gap query with two solvers.
- Update `supabase/ops/verify_psse_results.sql` and the pinned-hash tests in the same change; update the PSS/E side doc statement that "anon and authenticated receive nothing".

**Warning signs:** first pandapower row labelled `psse`; insert error on `psse_run_run_id_ck`; PSS/E job tests failing after the migration; schema-doc test failing on column order.

**Phase to address:** C. **Confidence:** [HIGH] (migration, `contract.py`, `run_record.py` read). The PostgreSQL behaviour that adding a column with a constant default is metadata-only is standard for PostgreSQL 11 and later (UNVERIFIED against this project's version; irrelevant at 19 rows).

---

### Pitfall 13: The read-only view, anon-key exposure, RLS and PostgREST

**What goes wrong:**
- **The established pattern does not fit.** The project's existing views (`latest_rating`, `day_ahead_*`) use `security_invoker = true` plus a table grant and an RLS read policy for `anon`. Here the four tables must stay private. A `security_invoker` view over tables the caller cannot read returns a permission error (or zero rows under RLS). A default (definer) view reads with the owner's rights and **bypasses RLS** ("Views bypass RLS by default because they are usually created with the `postgres` user", Supabase docs), which is what makes it work, but it is also what Supabase's security advisor flags (lint 0010, "security definer view"). Either way a column added to the view later is exposed to the public key immediately.
- **Exposure is by explicit grant now.** Supabase's change (new projects from 2026-05-30, all existing projects 2026-10-30) means new tables in `public` are no longer granted to `anon`/`authenticated` automatically; without a grant the role is rejected before RLS. The changelog does not mention views (UNVERIFIED whether views follow the same default). The project's expose migration already sweeps grants and sets default privileges, so the new view needs an explicit `grant select ... to anon[, authenticated]` and nothing else; relying on defaults in either direction is wrong.
- **The exposure verifier will break.** `supabase/ops/verify_exposure.sql` asserts the public roles hold exactly the published objects (its text counts "10 of 10 grants") and has a check that only listed views are `security_invoker`. A new definer view is a deliberate exception that must be added to that script and to `expose_migration_test.py`, otherwise either the check fails or, worse, the exception is waved through.
- **Column leakage.** The tables hold `ratings_used` (JSON, with the link to the city rating and config fingerprint), `case_sha256`, `mapping_sha256`, `case_id`, `error`, and `details` JSON that can contain grid element identifiers. The agreed view lists only dispatched capacity, limiting factor, solver and study time. Select exactly those columns, never `*`.
- **Meaning traps.** `dispatched_mw` and `dispatched_mva` are per **circuit** and not comparable with `city_rating.rating_mw` (per conductor, scaled by power factor); a dashboard comparing them will be off by about 2x/0.95. Say so in column comments, as the existing views do (unit-first comments, one-way column list).
- **"Newest per city" semantics.** Across two solvers, "newest" may be a PSS/E laptop row. Decide: newest per city **per solver**, or filter to `pandapower` (the dashboard source of truth by decision) and show the PSS/E row separately. A `failed` run has no result rows, so the newest result can be hours old; expose an age or study-time column plus a staleness flag like `latest_rating.is_stale` so the dashboard cannot present an old value as current. Ties (two runs in one slot) need a deterministic tiebreak (`slot_time`, then `created_at`).
- **PostgREST schema cache.** A new view is invisible to the REST API until the schema cache reloads; Supabase documents `NOTIFY pgrst, 'reload schema'` (and an event trigger that does it after DDL). A "view not found" right after `db push` is usually this, not a missing grant; a smoke test should call the view with the publishable key only (read-only HTTP GET) after a reload.

**How to avoid:** Decide the access mechanism explicitly in the milestone requirements (options: a definer view with exactly the agreed columns and a documented exception to the invoker rule; column-level SELECT on base tables with an anon read policy and an invoker view; or a read function in a non-exposed schema). Then: explicit grants and revokes in the migration; `comment on view` and per-column comments; extend `verify_exposure.sql` and its test; an anon-key smoke check (this repo has `supabase_smoke.yml` as a pattern) that confirms the view reads and that the four tables still return a permission error; include `NOTIFY pgrst, 'reload schema'` at the end of the migration (harmless if redundant). Update DEF-01 in the dashboard document only after the smoke check passes, not before.

**Warning signs:** `permission denied for table psse_*` from the view; the advisor raising lint 0010; view data visible but base tables also readable with the anon key; REST 404 for the view for several minutes after the push.

**Phase to address:** F (with the grant tests alongside the migration in C if the view ships in the same file).
**Confidence:** [HIGH] on RLS/definer semantics and the 2026-10-30 grant change (Supabase docs and changelog); UNVERIFIED on whether this project and views follow the new default.

---

### Pitfall 14: Secrets in logs, the mapping as a secret, one shared credential

**What goes wrong:**
- **Structured secrets are not reliably redacted.** GitHub's secure-use guidance: "Structured data can cause secret redaction within logs to fail"; create individual secrets per value. The private mapping is a JSON document. Its parts (bus numbers, branch keys such as `12-13-1`) are exactly what the project wants hidden, and they can be printed by an error message, a traceback, a debug dump or a step summary without matching the masked string.
- **Derived values are not masked.** "Registering secrets applies to any sort of transformation/encoding": a decoded mapping, a password parsed out of a connection URL, a URL-encoded or base64 form are all different strings. The repo already knows this (`redaction.py` registers user, project reference and host separately from the URL and strips resolved addresses from libpq text).
- **Size.** Secrets are limited to 48 KB; a gzip+base64 network and mapping can approach it. GitHub's workaround (an encrypted file in the repo plus a passphrase secret) disables redaction of what is printed ("GitHub does not redact secrets that are printed in logs") and puts ciphertext of private data in a public repo history permanently, which is worse than a plain secret for this project.
- **Public logs.** The repository is public, so run logs, step summaries and uploaded artifacts are readable by anyone who can see the repo. Any bus number, branch key, per-line flow or contingency list printed by the job is a disclosure. A rule that "failed runs print the violation table to help debugging" would publish the private mapping piece by piece.
- **One role, two places.** Decision: the CI job writes as the existing `dlr_psse_writer`; the same password then lives on the laptop and in GitHub. That role also holds SELECT on all four tables, so a leaked Actions secret exposes `ratings_used`, hashes and `details`, and allows forged INSERTs labelled `psse`. Rotation must update both places.
- **Fork and trigger safety.** Secrets are not passed to workflows from forks (GitHub docs), but `pull_request_target`/`workflow_run` with untrusted code can expose them; this repo's pattern (dispatch only, main-only guard, `production` environment with a main-only deployment rule) is the right one and must be copied exactly, including `permissions: contents: read`.

**How to avoid:**
- Separate secrets for the DB URL and for each private artifact; load them with environment variables into `$RUNNER_TEMP` files, never echo, never `set -x`, no `env` or `printenv`; run `::add-mask::` for every derived value (decoded mapping lines, password) before use; use the existing `redaction` module for every exception message.
- Make the job's logging policy "counts and codes only": slot time, outcome, counts, durations, city names; no bus numbers or branch keys in stdout, annotations, summaries or artifacts. Put identifiers only in the database tables, which are private. A test that runs the job against the placeholder mapping and fails if any placeholder bus number appears in captured output.
- Avoid the encrypted-file workaround; if size forces it, store the large network as the unmasked-derivative-free delta only.
- Review the first runs' logs by eye after valid and invalid inputs (GitHub's own advice); if a secret appears in a log, delete the run logs and rotate.
- Consider (owner decision, flag only) a separate CI role: `dlr_psse_writer` for the laptop, a new role for CI, so each can be revoked independently; the decision recorded in STATE.md uses the existing role, so a rotation runbook is the minimum.

**Phase to address:** D (workflow and logging), G (rotation runbook).
**Confidence:** [HIGH] (GitHub docs; repo `redaction.py` and workflows read).

---

### Pitfall 15: Leaking the private mapping and case through the public repo

**What goes wrong:**
`.gitignore` blocks `/psse_local/`, `*.sav` and `*.raw`, and only `psse_mapping_example.json` (placeholder buses 9xxxx) is committed. The new solver creates new ways around that: a network exported to JSON (`pandapower.to_json`) or a pickled net dropped in `backend/` or `data/`; test fixtures made "from a real run" so the tests pass; agreement-check reports (CSV, markdown, notebooks) saved into `.planning/` or `docs/` with real element identifiers or per-line values; planning and research documents quoting live numbers; generated graph or index output (the working tree has untracked `graphify-out/` and `.planning/graphs/`, which can embed whatever the tools indexed); workflow artifacts and caches (`actions/cache` keys and content are visible to repo readers); screenshots. Git history is permanent: a committed identifier is public even after deletion.

**How to avoid:**
- Add ignore patterns for every new artefact type up front (exported network JSON/pickle, agreement report outputs, a `psse_local/`-style `pandapower_local/`), and write all private outputs under the already ignored directory.
- Fixtures only from the placeholder mapping and the public MATPOWER case; assert in a test that the committed example mapping still has `"placeholder": true`.
- A local-only pre-commit or pre-push check on the laptop (where the real mapping exists) that scans staged text for the real bus numbers and branch keys; CI cannot do this because the private data is not in CI. UNVERIFIED as a practice, recommended.
- Agreement results are reported as counts, a pass/fail verdict and tolerances, not element-level tables; element-level detail stays in a private file or in the database.
- Do not commit anything under `graphify-out/` or `.planning/graphs/` unless reviewed.

**Phase to address:** G (guards, set up in A before any real data is touched), E (report format).
**Confidence:** [HIGH] for the repo's current ignore rules; guard design MEDIUM.

---

### Pitfall 16: Permanent rows, test pollution and growth

**What goes wrong:**
- Every hourly run adds one `psse_run` row, four dispatch rows, four margin rows and zero to many violation rows, forever (STATE.md: 24 row sets a day). The writer role cannot delete, so every dry run, debugging run, workflow re-run and half-finished rollout that writes to the live database is permanent noise labelled as a real pandapower result. The run id is built to be an idempotency key within one process, but a workflow "re-run" is a new process and a new id; nothing prevents two `ok` runs for one slot.
- Growth: about 8,760 run sets a year. Violation rows per run are capped at 5,000 in code (`MAX_CONTINGENCY_ROWS`), so the worst case is about 120,000 rows a day; the typical count is unknown (violations only are stored). The database size limit of the current Supabase plan was not verified (UNVERIFIED). The existing index on the run table is by `slot_time` only; "newest per city per solver" through a join may need a supporting index once rows reach the hundreds of thousands.
- No retention rule exists (STATE.md concern), and an append-only grant makes a retention job a privileged, owner-only operation.

**How to avoid:**
- A `--dry-run` (the default) that never opens a write connection; tests and the agreement replay use the throwaway Postgres harness and never the live project; production writing only from the guarded workflow on `main`.
- Pre-go-live gate: do not enable the hourly writer until the agreement check (Phase E) passes, because each earlier row is permanent.
- Idempotency: before inserting, check for an existing `ok`/`fallback` row for this solver and slot and skip (the writer role has SELECT); or accept double rows and make the view tolerant. Choose and document.
- Decide retention before go-live: for example keep everything for N months, then an owner-run archive of `psse_contingency_result` older than N days; or aggregate. Record row counts per day in the runbook so growth is visible. At minimum write the decision down; the cost is nil now and large later.

**Phase to address:** C (dry-run, idempotency, indexes), G (retention decision).
**Confidence:** [HIGH] for row/permission facts (migration read); growth rate UNVERIFIED.

## Moderate Pitfalls

### Pitfall 17: Installing and running pandapower in CI

**What goes wrong:** Cold `pip install` of pandapower and its dependencies on every hourly run costs minutes of runner time and is another failure point (index outage, a new release). numba is optional and not installed in a plain venv (pandapower prints a "slow" warning); results are the same but runtime differs from the laptop. Python 3.12 on the runner versus the PSS/E code's Python 3.7 syntax rule: shared modules (`contract.py`, `run_record.py`, `writer.py`) must stay importable by both, and new pandapower code must not leak into the PSS/E package.
**Prevention:** pip cache (as `dlr_live.yml` does), exact pins, a `timeout-minutes` below 60, and keep the pandapower code in its own package that imports only the shared pure modules. Time the job in the dry-run phase; a 39-bus load flow is milliseconds, so a few hundred outage and transfer solves per city should finish in minutes, but this was not measured end to end.
**Phase:** D.

### Pitfall 18: Reusing the PSS/E schema vocabulary for pandapower semantics

**What goes wrong:** `failed_stage` values name PSS/E stages and `error` is a PSS/E redacted message; `rate_set` is `RATEA`; `psse_version` is the PSS/E version; unit CHECKs allow only `MVA` and `pu`. Forcing pandapower into them hides the difference, while a new vocabulary needs a CHECK change on a live table.
**Prevention:** Decide the vocabulary mapping in the migration phase, once; prefer new nullable columns over overloaded meanings.
**Phase:** C.

### Pitfall 19: Time handling

**What goes wrong:** `slot_time` and the run id use UTC; the existing cron-job.org job runs on Central time (observed), the owner reads Central clock times, and the laptop clock can disagree with the database (the gap SQL says so). Runner clocks are NTP-synced, so the risk is in the trigger and in reading reports.
**Prevention:** UTC everywhere in code and reports; state the dispatch minute in UTC; report agreement results with UTC slots.
**Phase:** D, E.

### Pitfall 20: Reading pandapower results by position

**What goes wrong:** `res_line`, `res_trafo` and `res_bus` are indexed by pandapower element index, not by the PSS/E key `from-to-ckt`. Parallel circuits (ckt 1 and 2 between the same buses) and the line/trafo split make a position-based join wrong without any error.
**Prevention:** Build the key map from the export in Phase A and join on it; assert one-to-one.
**Phase:** A, B.

### Pitfall 21: Hourly cost and runner minutes

**What goes wrong:** The runbook assumes a private repo with a monthly minute quota; the repo is public today, where standard runners are free, but that can change if visibility changes (UNVERIFIED current billing). A change to private would add cost for 24 runs a day.
**Prevention:** Record the assumption in the runbook; keep the job short.
**Phase:** D.

## Minor Pitfalls

- **`loading_percent` and `trafo_loading`:** leave `trafo_loading="current"` (default) and record it. Phase B.
- **`voltage_depend_loads=True` default:** harmless when `const_z`/`const_i` are 0, but a PSS/E load with constant-current/admittance parts imported without them is silently constant-power. Check during parity. Phase A.
- **`check_connectivity=True`:** do not turn it off to "fix" NaN; handle NaN instead (Pitfall 7). Phase B.
- **Dashboard doc wording:** DEF-01 must say the view is unblocked and name solver semantics; do not promise PSS/E-grade equivalence until agreement passes. Phase F.
- **Timestamps in the view:** expose the study time (`slot_time`) and the computed time; the dashboard should show age. Phase F.

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Build the net straight from MATPOWER `case39` | Works in an hour | Agreement fails for unexplained reasons; whole milestone stalls | Only for unit tests, never for the study |
| Keep the `psse-` run-id prefix for pandapower rows | No constraint change | Run id lies about the producer; prefix cannot separate solvers | Never; tie prefix and `solver` by CHECK |
| Reuse `psse_version` for the pandapower version | No new column | Mixed semantics forever in an append-only table | Never; add `solver_version` |
| Unpinned `pip install pandapower` in the workflow | Zero maintenance | Silent behaviour change mid-series | Never |
| Print violation tables in logs "for debugging" | Faster debugging | Public disclosure of private identifiers | Never in the production workflow |
| Skip the epsilon band in the agreement check | Simpler code | Flapping pass/fail at limit boundaries | Never |
| Write test runs to the live database | Realistic | Permanent junk rows | Never; use the throwaway Postgres |
| Definer view without an exposure-script exception | Fast | Verifier either fails or stops meaning anything | Never; document the exception |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| pandapower `from_mpc` | Trusting ratio-based line/trafo split, 0-based indexes, rateA=0 as unlimited | Build from the PSS/E export; explicit crosswalk; parity report |
| pandapower `runpp` | Assuming success means valid (NaN buses, default `enforce_q_lims=False`) | Post-solve NaN, limit and convergence checks; explicit options |
| PSS/E recorded rows | Re-deriving inputs | Replay stored ratings, filter by mapping hash and job version |
| Supabase pooler | Using the direct (IPv6) host from a runner | Session pooler URL, as `supabase_smoke.yml` proves; `prepare_threshold=None` as `writer.connect` does |
| Supabase view | Relying on default grants/definer behaviour | Explicit grant, explicit column list, exposure verifier updated |
| `dlr_live` ratings | Starting at the same minute or after :30 | Start at about :15 to :25; check `fallback_reason` distribution |
| GitHub concurrency | Assuming `cancel-in-progress: false` queues everything | Only one pending run is kept; use `queue: max` or idempotent slots |
| cron-job.org | Setting local time, token expiry unnoticed | UTC minute documented, token expiry tracked, external freshness alarm |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Cold dependency install each hour | Job takes minutes before any study | pip cache, pins | Immediately (cost), or on an index outage |
| Deep-copying the net per outage | Slow loops | Acceptable at 39 buses; copy the base once per city and re-copy per outage as the PSS/E job reloads | Not at this size |
| View over unindexed child tables joined to runs | Slow dashboard read | Index (solver, slot_time desc) and city keys | Roughly 10^5 run rows (UNVERIFIED) |
| `contingency_result` volume | Table size and slow scans | Cap kept at 5,000/run, retention decision | Worst case about 120k rows/day |
| Runs overlapping the next slot | Pending run replaced, missing slot | Timeout below cadence (30 min as `dlr_live`), own concurrency group | Any run over 60 min |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Mapping as one JSON secret and printing parts of it | Private grid identifiers in public logs | Counts and codes only in logs; add-mask for derived values; leak test |
| Same writer password in two places, role with SELECT on all four tables | Wider leak surface; forged rows | Rotation runbook; consider a CI-only role (owner decision) |
| Definer view returning more columns than agreed | Public read of private run data | Explicit column list, comments, verifier |
| Dispatch from any branch with secrets | Edited workflow exfiltrates secrets | `github.ref == 'refs/heads/main'` guard and `production` environment rule |
| Encrypted-file workaround for large secrets | Ciphertext in public history, no log redaction | Avoid; shrink the secret |
| Committed network or report with real identifiers | Permanent public disclosure | Ignore patterns, placeholders in fixtures, local scan before push |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Dashboard shows an old dispatched value as current after failed runs | Operators act on stale capacity | Expose study time, age and a stale flag; define freshness |
| Per-circuit MW compared with per-conductor rating MW | Capacity appears 2x/0.95 too high or low | Unit-first column comments; name the basis in the dashboard doc |
| Solver label hidden | Users trust pandapower results as PSS/E-grade | Show `solver` and the agreement status in DEF-01 text |
| Fallback (static rating) rows indistinguishable | A degraded hour looks like a real DLR hour | Expose `limiting_factor` and rating source (agreed columns plus the source if allowed) |

## "Looks Done But Isn't" Checklist

- [ ] **Network parity:** base-case voltages and flows match the PSS/E export before any outage; verify with a table-by-table report, not a spot check.
- [ ] **Agreement check:** passes with N non-empty comparisons per city and compares `non_convergence` sets and `n_contingencies`, not only violations; verify the mapping hash filter and a deliberate-failure test (alter a rating, expect fail).
- [ ] **Islanding/NaN:** a test net proves an islanding outage yields a `non_convergence` row; verify no NaN passes as clean.
- [ ] **Migration:** old-style insert (no `solver`) labels `psse`; pandapower insert labels `pandapower`; wrong prefix fails; gap query with both solvers in one hour reports the pandapower gap; PSS/E job tests still pass.
- [ ] **View:** anon key reads the view and cannot read the four tables; exposure verifier updated; PostgREST reload done; no extra columns.
- [ ] **Workflow:** dispatch only, main guard, `production` environment, own concurrency group, timeout under 60 min, pinned deps; first runs' logs reviewed for identifiers.
- [ ] **Scheduling:** dispatch minute documented in UTC, token expiry recorded, external freshness alarm exists, rating-staleness fallbacks not occurring.
- [ ] **Full-day acceptance:** 24 consecutive slots counted by the solver-aware query, not by eye.
- [ ] **Retention:** a written decision and a row-count log exist.
- [ ] **Leakage:** ignore patterns added, fixtures placeholder-only, no element-level tables in committed reports.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Mislabelled pandapower rows labelled `psse` | MEDIUM | Owner (table owner) corrects by hand in SQL editor; add the CHECK; document the exception |
| Junk or test rows in live tables | MEDIUM | Owner-run delete by `run_id`/slot range, recorded in the runbook; add the dry-run default |
| Secret printed in a log | MEDIUM | Delete the run logs, rotate the DB password in GitHub and on the laptop, review artifacts |
| Mapping committed to the public repo | HIGH | Treat as disclosed; rewrite history is not enough (clones, forks); notify the data owner; rotate scaling targets if feasible |
| Agreement fails after build | HIGH if parity was skipped, LOW if gated | Fall back to the Phase A parity report to localise the data difference |
| Silent dependency upgrade changes results | LOW | Pin, rerun the replay, mark the affected slots by `solver_version` |
| Trigger stopped (token expired, job disabled) | LOW | Re-issue token, re-enable job; the freshness alarm shows the gap; backfill is not possible for past slots (the study is live-time), so record the gap |
| View exposes too much | MEDIUM | Revoke and recreate the view, rotate nothing (publishable key is public); audit what was readable |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1 Network parity | A | Full-vector base-case match within 0.01 pu / 2 percent, table-by-table report |
| 2 False agreement | E (design), A/B (inputs) | Mapping-hash filter, shape checks, non-empty count, deliberate-failure test |
| 3 Conversion traps | A | Crosswalk round-trip, transformer classification from PSS/E, no unexpected `sgen`, no rate 0/99999 on monitored branches |
| 4 Ratings units | B | Unit tests mirroring `units.py`; loading basis recorded |
| 5 Scaling and slack | B | Read-back within 1e-3, per-city copies, laptop confirmation of `scal_2` swing rule |
| 6 Q limits and options | A, B, E | Post-solve Q check; option list reproduced or declared |
| 7 Islanding and NaN | B, E | Test net with islanding outage; NaN-to-`non_convergence` |
| 8 Margin near the nose | B, E | Compare only `voltage_criterion`-bounded limits |
| 9 Determinism and drift | B, C, D | Lock file; version column; replay with pinned versions |
| 10 Scheduling | D | Runs at the intended minute; no doubled slots; pending-run behaviour tested |
| 11 Gap check | C, D | Two-solver gap test; external freshness alarm |
| 12 Migration | C | Throwaway-Postgres rehearsal incl. old and new writers, prefix CHECK |
| 13 View exposure | F (tests in C) | Anon-key smoke test; verifier updated; reload done |
| 14 Secrets and logs | D, G | Leak test on placeholder mapping; log review; rotation runbook |
| 15 Repo leakage | A (ignore rules), G | Ignore patterns, placeholder-only fixtures, local scan |
| 16 Permanent rows | C, G | Dry-run default; retention decision written; row-count log |

## Recommended ordering (derived from the dependencies above)

1. **A (network parity) first.** Everything else is meaningless without it, and it needs the laptop.
2. **B (study engine)** against the parity net; **C (migration and writer)** can run in parallel with A/B on the throwaway Postgres.
3. **E (agreement) before D go-live.** Rows are permanent; enabling the hourly writer before agreement passes creates permanent unvalidated `pandapower` rows.
4. **D (hourly workflow)** in dry-run first, then live for the full-day acceptance.
5. **F (view and DEF-01)** last, once results are validated and the access mechanism is decided.
6. **G** runs alongside, but the ignore rules and logging policy go in at the start of A and D respectively.

Research flags: Phase A (needs the PSS/E export and the laptop; deepest unknowns), Phase E (corpus content unknown), Phase F (access-mechanism decision). Phases B, C and D follow standard patterns already present in this repo.

## Sources

- MATPOWER `case39.m` (header lists modifications; branch/gen tables): https://raw.githubusercontent.com/MATPOWER/matpower/master/data/case39.m (fetched 2026-11-16) [HIGH]
- pandapower 3.2.2: `from_ppc.py`, `from_mpc` and `runpp` docstrings; experiments on public `case39` in a scratch venv (conversion, NaN/islanding, `enforce_q_lims`, determinism, loading basis) [HIGH]
- GitHub Docs, events that trigger workflows (schedule delays, 60-day disable in public repos, default branch, dispatch file location): https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows [HIGH]
- GitHub Docs, concurrency (one pending run, replaced; `queue: max`): https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency [HIGH]
- GitHub Docs, secure use (structured data redaction, derived values, log review, `pull_request_target`): https://docs.github.com/en/actions/reference/security/secure-use [HIGH]
- GitHub Docs, using secrets (48 KB limit and the gpg workaround, no redaction with it, forks): https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions [HIGH]
- Supabase Docs, row level security (views bypass RLS, `security_invoker`): https://supabase.com/docs/guides/database/postgres/row-level-security [HIGH]
- Supabase changelog, new public tables not exposed to the Data API by default (2026-05-30 new projects, 2026-10-30 existing): https://supabase.com/changelog/45329-breaking-change-tables-not-exposed-to-data-and-graphql-api-automatically [HIGH]; views not mentioned there [UNVERIFIED for views]
- Supabase splinter lint 0010 (security definer view): https://supabase.github.io/splinter/0010_security_definer_view [MEDIUM]
- PostgREST schema cache reload and Supabase refresh guide: https://docs.postgrest.org/en/v12/references/schema_cache.html , https://supabase.com/docs/guides/troubleshooting/refresh-postgrest-schema [MEDIUM]
- PSS/E `fnsl` options (partial, forum): https://www.whit.com.au/blog/2012/12/keyword-arguments-for-psse-functions/ , https://psspy.org/psse-help-forum/question/116/how-do-i-call-a-psspy-function-without-listing-every-argument [LOW, partial]
- This repo (read for this research): `supabase/migrations/20261109233541_psse_results.sql`, `backend/psse_job/psse_api.py`, `units.py`, `contract.py`, `run_record.py`, `study.py`, `contingency.py`, `margin.py`, `dispatch.py`, `settings.py`, `constants.py`, `gaps.py`, `redaction.py`, `writer.py`; `docs/data-science/schema/psse_run_gaps.sql`; `.github/workflows/shadow_collect.yml`, `dlr_live.yml`, `supabase_smoke.yml`; `docs/data-science/decisions/shadow_collection_runbook.md` (3 to 8 h schedule lateness, cron-job.org on Central time, "nothing reports a missing run"); `supabase/migrations/20261026195124_expose_latest_rating.sql` and `supabase/ops/verify_exposure.sql` (existing invoker-view pattern and exposure verifier); `.gitignore` (private-file rules); `.planning/workstreams/pandapower-solver/STATE.md` [HIGH for what the files say]

---
*Pitfalls research for: pandapower solver beside a PSS/E study, append-only Supabase tables, hourly GitHub Actions*
*Researched: 2026-11-16*
