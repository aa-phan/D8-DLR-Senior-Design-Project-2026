# Feature Research

**Domain:** pandapower re-implementation of an existing PSS/E per-city grid study (scaled load flow, N-1 line-outage screen, load-transfer voltage margin, dispatched capacity), with solver-to-solver agreement checking
**Researched:** 2026-11-16
**Confidence:** MEDIUM overall. HIGH for every pandapower behaviour (run locally against pandapower 3.2.2 and read from its docs and source). MEDIUM or UNVERIFIED for PSS/E's default behaviour, because the PSS/E manuals are not publicly fetchable and the job calls `fnsl()` with no argument, which means "use the case's own settings". Those settings have never been recorded in this repo.

Confidence tags used below: HIGH = ran it or read official docs/source; MEDIUM = forum or secondary source, or inferred from the existing job code; UNVERIFIED = needs the laptop or Power Systems. The `research-plan` / `classify-confidence` seam was not used (WebSearch/WebFetch and local experiments only), so the tags are my own judgement against that scale.

## Bottom line for the roadmap

1. **The agreement check is only as good as the data parity and one PSS/E setting.** In pandapower's public `case39` (MATPOWER data), switching `enforce_q_lims` on or off moves base-case bus voltages by only about 5e-4 pu and flows by under 0.1 MW, so the 0.01 pu / 2% base-case test cannot tell the two apart. On a heavier scaled copy of the same network, or in the margin walk, the choice moves minimum voltage by about 0.1 pu and the voltage-criterion transfer by about 100 MW (roughly 12%). The setting PSS/E actually used on the laptop must be measured, not assumed (see "PSS/E behaviours that must be matched").
2. **The stored PSS/E rows cannot support "all bus voltages within 0.01 pu, all flows within 2%".** The four result tables hold only violations, per-city margin figures and the dispatch row. Per-outage bus voltages and non-violating flows were never stored. The replay can compare the violation sets, the observed values on violation rows, and the margin and dispatch figures. A full-state comparison needs a one-off reference dump from the laptop (private).
3. **Two pandapower behaviours silently diverge from the PSS/E study and must be coded around:** an outage that islands generation returns "converged" with NaN voltages (PSS/E `fnsl` returns error 3, which the job records as a `non_convergence` row), and after a `LoadflowNotConverged` the `res_*` tables still hold the previous run's values.
4. **Reuse is large.** `violations.py`, `dispatch.py`, `margin.find_transfer_limit`, `ratings.py`, `run_record.py`, `writer.py`, `settings.py` and `mapping.py` are solver-neutral. The solver-specific surface is the `PsseApi` method set (about 15 methods). A `PandapowerApi` exposing the same methods lets `contingency.py` and `margin.py` run unchanged; `study.py` needs a small injection point because `_open_case` constructs `PsseApi` directly.

## How each study step maps to pandapower

Reference code: `backend/psse_job/study.py`, `contingency.py`, `margin.py`, `violations.py`, `dispatch.py`, `psse_api.py`; semantics in `docs/data-science/decisions/psse_study_definitions.md`.

| Study step | PSS/E semantics (existing job) | pandapower mapping | Agreement risk |
|---|---|---|---|
| 0. Network | The case file (`.sav`, private, from Power Systems) | `pandapower.networks.case39()` carries MATPOWER/PYPOWER data (35 lines, 11 transformers, 9 gens, 1 ext_grid; all buses 345 kV; HIGH, ran it). pandapower 3.2.2 has **no PSS/E importer** (converter packages: cim, jao, matpower, pandamodels, powerfactory, pypower, ucte; HIGH, listed the install). Routes: use `case39()` if a parity table shows it equals the laptop case; otherwise export the laptop case's bus/branch/machine/load/shunt tables once and build the net with a small builder, or go RAW to MATPOWER (`psse2mpc`) to `from_mpc` (a forum thread reports a UTF-8 failure on that route; MEDIUM). | HIGH. STATE.md already flags it. Everything downstream is meaningless if impedances, taps, shunts, machine limits or ratings differ. |
| 1. Rating write | `circuit MVA = sqrt(3) x kV x A_per_conductor x n / 1000` to RATEA of each mapped line, read-back checked | `line.max_i_ka = amps_per_circuit / 1000` (exactly the inverse of the job's conversion at the line's base kV), `df=1`, `parallel=1` (parallel circuits are separate rows, as in PSS/E). pandapower has no MVA rating on lines. Unmapped lines keep `max_i_ka` from the case (case39: `max_i_ka = rateA / (sqrt(3) x 345)`, 600 MVA gives 1.004 kA; HIGH, checked). `rate_before_mva` = old `max_i_ka x sqrt(3) x kV`. | LOW if unmapped-line ratings are taken from the laptop case's RATEA; MEDIUM if left at MATPOWER `rateA`. |
| 2. Per-city whole-case scaling | `scal_2` new-total mode: total load and total generation set to city targets, load P/Q kept in proportion; read-back within 0.1%; bounds 0.05 to 20x | Load: `net.load["scaling"] = target_load / sum(p_mw)` (scales P and Q together, so power factor is kept, matching CD-9). Gen: `net.gen["scaling"]` on PV machines. `ext_grid` has no P setpoint, so the swing machine's pre-solve P must come from the PSS/E case (or a base solve) if the generation total is to include it. Totals read-back is a sum over in-service elements times `scaling`. | **HIGH, UNVERIFIED:** (a) whether PSS/E `scal_2` includes the swing machine in "total generation", (b) whether it clamps machines at Pmax/Pmin, (c) whether it scales in-service machines only. Each changes the PV-machine dispatch that the solve then sees. One laptop read of machine PGEN before and after `scale_to_target` (print factors only) settles it. |
| 3. Base AC load flow | `fnsl()` (full Newton-Raphson, case settings), converged only when `ierr==0` and `solved()==0`; mismatch at most 1 MVA; any bus below 0.5 pu is a collapse | `pp.runpp(net, algorithm="nr", enforce_q_lims=<measured>, init="results" after a first solve or "dc", max_iteration=30, tolerance_mva=1e-8, calculate_voltage_angles=True, check_connectivity=True, distributed_slack=False, voltage_depend_loads=True)`. Defaults confirmed from the 3.2.2 signature (HIGH): `algorithm="nr"`, `init="auto"` (dc when angles on), `max_iteration="auto"` (10 for nr), `tolerance_mva=1e-8`, `enforce_q_lims=False`, `trafo_model="t"`. Converged = no `LoadflowNotConverged` and no NaN on in-service buses and no bus below `collapse_voltage_pu`. | See next section. |
| 4. N-1 line outage | Reload saved base, `set_status(line, False)`, `fnsl`, read buses and loadings, evaluate; non-convergence or monitored bus under 0.5 pu gives one `non_convergence` row | Per outage: `copy.deepcopy(solved_base_net)` (about 4 ms on case39), `net.line.at[i, "in_service"] = False`, `runpp(..., init="results")`. A fresh copy per outage mirrors "reload the saved base" and avoids stale state. 175 case39 outage solves took 2.85 s total (16 ms each, numba absent; HIGH, measured). Thermal: `res_line.loading_percent` (see "Ratings" below). Voltage: `res_bus.vm_pu` against the configured pair. | **Islands (HIGH, measured):** removing 2 of case39's 35 lines leaves generation buses without a path to the swing bus. `runpp` returns normally with NaN `vm_pu` on those buses (4 buses for one line, 1 for the other). PSS/E `fnsl` returns ierr 3 "buses in island without swing bus" (PSSPY reference; MEDIUM), which `study`/`contingency` store as `non_convergence`. The adapter must turn "any in-service bus has NaN voltage" into a non-converged result. |
| 5. Voltage-stability margin | Sink-bus load raised by d MW (`scal_2` increment, constant P/Q), swing absorbs, step 25 MW, bisect to 1 MW; good = converged, no collapse, min monitored V at least 0.9 pu; transfer = sum of abs from-end P on mapped branches | `f = 1 + d / P_sink` on `net.load.loc[load.bus.isin(sinks), "scaling"]`; swing absorbs because `distributed_slack=False`. `p_mapped = sum(abs(res_line.p_from_mw))` keeping PSS/E from/to orientation (from-end and to-end P differ by losses). `max_flow = max(hypot(p_from,q_from), hypot(p_to,q_to))` per mapped line (the job's `MAXMVA`). `find_transfer_limit` is pure Python and reusable as is. About 100 evaluations per city at 20 ms is 2 s. | **UNVERIFIED:** whether PSS/E's increment form scales Q along with P. The job doc says "constant P and Q" only. If PSS/E adds P only, pandapower must add P only (add a load or edit `p_mw` instead of `scaling`). One laptop read of a sink load's Q before and after settles it. |
| 6. Dispatched capacity | `min(applied_mva, voltage_limit_mva)`, tie goes to rating, `dispatched_mw = mva x 0.95` | Unchanged: `dispatch.build_dispatch_row` is pure. | LOW. When the margin is rating-bound (`bounded_by == dlr_rating`) the dispatched figure equals the applied rating and does not depend on solver precision. Only voltage-bound capacities are sensitive. |
| 7. Result rows and write | Four `psse_*` tables via `run_record` and `writer`, one transaction | Same row builders; add the `solver` tag. The `psse_version` column has to carry something for pandapower (for example the pandapower version string), and `job_version` should say which solver. | LOW. |

### Ratings: pandapower `max_i_ka` versus PSS/E RATE in MVA

- pandapower defines `loading_percent = i_ka / (max_i_ka x df x parallel) x 100`, `i_ka = max(i_from, i_to)` (pandapower line docs; HIGH).
- I checked on case39 that this equals `100 x max(|S_end| / V_end_pu) / (sqrt(3) x Vn x max_i_ka)` to 3e-14 percent, i.e. a **current-basis** percent. It differs from an MVA-basis percent (`max(|S|)/rating`) by up to 3.8 percentage points in the case39 base case (HIGH, ran it).
- The job's default `thermal.basis = "current"` reads PSS/E `MAXPCTRATEA`. If PSS/E's current-based percent is `|S|/V_pu` over the MVA rating at the larger end (my reading of the option name; MEDIUM, not read from the manual), pandapower's `loading_percent` is the same quantity with no conversion. The `mva` basis has no native pandapower field and would have to be computed from `res_line.p/q`. Recommendation: support `current` only for the pandapower solver.
- Feed `violations.thermal_violations` with `BranchFlow(rate_mva = max_i_ka x sqrt(3) x kV, pct = loading_percent, p_mw = p_from_mw, max_mva = ...)` so `observed = rate x pct / 100` is computed identically in both solvers.

## PSS/E behaviours that must be matched

| Behaviour | PSS/E side | pandapower side | Action | Confidence |
|---|---|---|---|---|
| Reactive limits on generators | `fnsl` OPTIONS(7): 0 apply immediately, n apply at iteration n, -1 ignore (PSSPY reference PDF; MEDIUM). With no argument the case's own setting applies, and that setting has never been recorded. The documented example `fnsl([1,0,0,0,2,0,0,0])` uses 0 (immediately). | `enforce_q_lims=False` is the pandapower default. When True, pandapower follows the MATPOWER method: any generator over a limit becomes PQ at the limit, it is never switched back to PV, swing generators are excluded, and a second load flow is run (source read, `run_newton_raphson_pf.py`; HIGH). Case39 base: the generator at MATPOWER bus 37 (Qmin 0) reads -1.37 Mvar without limits (HIGH, same figure as the MATPOWER list-post header note). | Measure on the laptop: read machine QGEN against QMAX/QMIN in a solved scaled copy, and the solve settings of the case. Then set `enforce_q_lims` to match. Also run the replay with both settings and report which one agrees. | Effect HIGH (measured). PSS/E default UNVERIFIED. |
| Size of the effect | n/a | Case39 base: dV up to 5.3e-4 pu, dP up to 0.08 MW. Whole case x1.3 load and generation: min V 0.961 (off) versus 0.864 (on), 8 of 9 generators at Qmax. Margin walk at one heavy load bus: 0.9 pu reached near +855 MW (off) versus +750 MW (on); non-convergence at +1375 versus +1025 MW. Without limits, x1.5 scaling converges; with limits it does not. | The base-case comparison alone will not detect a wrong setting. The replay must include scaled-city and margin figures. | HIGH (ran it, public case39) |
| Swing bus | One swing per island, holds V and angle, absorbs the mismatch; swing Q limits probably not applied (UNVERIFIED) | `ext_grid` holds V and angle, absorbs mismatch, has no Q limits; `distributed_slack=False` default | Keep one `ext_grid` at the PSS/E swing bus with the case's V setpoint. Do not enable distributed slack. | MEDIUM |
| Islands without a swing bus | `fnsl` ierr 3, not solved (PSSPY reference table; MEDIUM) | `check_connectivity=True` (default) sets unsupplied buses out of service, results NaN, run "succeeds" (docs, HIGH; measured) | Detect NaN on in-service buses after every solve and return `converged=False` with a meaning like "island without swing bus". Confirm on the laptop that PSS/E gives ierr 3 for the islanding outages (the 19 recorded runs may already show it as `non_convergence` rows). | HIGH (pandapower), MEDIUM (PSS/E) |
| Flat start | OPTIONS(6) 0 by default: start from the case's stored voltages | `init="results"` after a solved run starts from stored voltages; base solution identical for `flat`, `dc` and `results` (max dV 7e-11 pu, HIGH). `init="auto"` means dc here. | Use `init="results"` on a deepcopy of the solved base for outages and margin points. Near the nose the start can pick a different solution, so keep the warm start identical in the replay. | HIGH |
| Convergence tolerance and iteration limit | Default mismatch tolerance TOLN 0.1 MW/Mvar (a forum list of restored defaults; MEDIUM); job also demands mismatch at most 1 MVA; iteration limit unknown here | `tolerance_mva=1e-8`, `max_iteration` auto = 10 for nr | Keep the tight tolerance. Raise `max_iteration` to 30 so a slow-but-fine solve is not scored as non-convergent. A 0.1 MVA tolerance moved case39 voltages by only 8e-6 pu (HIGH), so tolerance is not an agreement risk. | HIGH |
| Non-divergent option and blow-up | OPTIONS(8) 0 by default; "blown up" is `solved()` 2 | None. pandapower raises `LoadflowNotConverged` (`pandapower.auxiliary`), or logs `dgstrf info 1` and fails on a singular Jacobian; no reference bus raises `UserWarning` (HIGH, observed) | Catch broadly (`LoadflowNotConverged`, `UserWarning` from the no-reference case, `numpy.linalg.LinAlgError`, `ValueError`). Never read `res_*` after a failure: the table keeps the previous run's numbers (observed `res_bus` not empty, `net.converged` False). Use a fresh deepcopy per solve. | HIGH |
| Voltage collapse guard | Any in-service bus under `collapse_voltage_pu` (0.5) is a collapse | NR can converge to a very low voltage (case39 walk: min V 0.697 still "ok" one step before failing; HIGH) | Keep the 0.5 pu guard and the NaN guard in the adapter. | HIGH |
| Tap, phase-shift, area-interchange, switched-shunt adjustment | OPTIONS(1) to (5), default taken from the case settings | Off unless controllers are added | Check the laptop case's solution settings once. If any is on and the case has controlling devices, pandapower needs matching controllers or the agreement will fail in stressed states. Case39 transformers are fixed-ratio. | UNVERIFIED |
| Load model | PSS/E loads can carry constant-current and constant-admittance parts | pandapower `voltage_depend_loads=True`, but const-Z/I percentages default to 0 (case39 has none) | Parity table should list load ZIP parts on the laptop case. | UNVERIFIED |
| Transformer model | Pi equivalent with magnetising branch | `trafo_model="t"` default; `"pi"` is what `from_ppc` uses to validate against PYPOWER | On case39 `t` and `pi` give identical results (max difference 0, lossless 345/345 transformers, HIGH). Set `"pi"` if the laptop case has magnetising data. | HIGH (case39) |
| Angle reference | Swing angle from the case | `ext_grid.va_degree` (0 in case39) | Compare magnitudes for the pass test; report angles relative to swing as information only. | HIGH |

## How solver-to-solver cross-validation is usually done

- **Data first, results second.** pandapower's own conversion check (`validate_from_ppc`) compares bus Vm/Va, branch P/Q and generator P/Q between the source solver and pandapower after conversion, with default maximum differences of 1e-6 (pu for voltage, 1e-5 degrees, 1e-6 MW/Mvar) (source read in 3.2.2; HIGH). Those numbers apply to identical data solved to tight tolerance and are a data-parity tripwire, not a statement about two independent products.
- pandapower's historic validation against DIgSILENT PowerFactory and PSS Sincal listed voltage magnitude 1e-6 pu, angle 0.01 degrees, current 1e-6 kA, power 0.005 kW, loading 0.001% (v1.4.3 docs; MEDIUM because old). The same docs say pandapower is not validated against PSS/E.
- **No published pandapower-versus-PSS/E power-flow comparison was found** (web search, several phrasings). An independent ZHAW comparison of pandapower, PyPSA and OpenDSS reports an average error under 2% against PowerFactory, but I only saw it secondhand through a vendor blog (LOW). So 0.01 pu and 2% in this milestone are project-chosen, not an industry standard.
- Expected numerical noise on identical data is far below those tolerances (about 1e-5 pu for a 0.1 MVA PSS/E tolerance, measured as 8e-6). A failure at 0.01 pu or 2% therefore means a data or behaviour mismatch (Q limits, islands, ratings, scaling), not rounding. That makes the milestone thresholds usable as a mismatch detector, provided the replay exercises stressed states.
- **Practical comparison rules** (opinionated):
  - Compare sets by identity (contingency id, element, kind), then values on the intersection.
  - Relative tolerances need an absolute floor, for example `abs(a-b) <= max(0.02 x abs(ref), floor)` with a floor of about 1 MVA for flows and 0.0005 pu for voltages, otherwise near-zero flows fail on noise. The floor values are a decision to take, not a finding.
  - Elements within a small band of a limit can flip sides on 1e-4 pu of noise. Classify those as "borderline" (listed, not failed) instead of failing the set equality, and state the band.
  - Always print the maximum observed deviation per quantity, even on pass, so the margin to the threshold is visible.

## Feature Landscape

### Table Stakes (the milestone fails without these)

| Feature | Why expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Network parity with the laptop case, with a parity report | Agreement is meaningless on different data. STATE.md names it the first real work. | HIGH | Compare element counts, per-branch R/X/B, tap and shift, shunts, machine P, V setpoint, Qmin/Qmax, load P/Q and RATEA, plus the solved base voltages. Needs a one-off laptop export (private; the repo is public, so the export and any pandapower JSON built from it stay out of git, `psse_local/`-style). Public `case39()` is acceptable only if the report says it matches. |
| `PandapowerApi` (or equivalent) presenting the study's data shapes | Lets the existing outage selection, violation rows, margin search, dispatch and guards run unchanged, so semantics cannot drift. | MEDIUM | Methods needed: load/snapshot/restore, `solve` returning `SolveResult`, `set_status`, `bus_table` (`BusRow`), `branch_table`, `branch_loading` (`BranchFlow`), `read_rate`/`set_rate`, `define_subsystem`/`scale_load`, `read_totals`/`scale_case`. `study._open_case` hard-codes `PsseApi(psspy_module, ...)`, so a factory argument is a small change to `study.py`. Shared modules keep Python 3.7 syntax (D-05) even though the Actions runner can use a newer interpreter. |
| Rating write as `max_i_ka` | Same ratings (`ratings_used`) must reach the same lines | LOW | `amps_circuit / 1000`; read back; reject non-finite or non-positive, as the job does. |
| Per-city whole-case scaling with read-back and bounds guards | Four cities, four different results | MEDIUM | `load.scaling` and `gen.scaling`; keep the 0.05 to 20x bounds and 0.1% read-back. Depends on the three UNVERIFIED `scal_2` details above. |
| Base load flow with the PSS/E-matched settings and a strict converged definition | STU-01 parity | MEDIUM | `runpp` options table above. Converged means no exception, no NaN on in-service buses, no collapse. |
| Island and NaN handling that reproduces `non_convergence` | Violation set per outage must match | LOW | A few lines after each solve; verified need on public case39. |
| N-1 screen on a fresh copy per outage | Same outage set, same rows | MEDIUM | `contingency.screen` reused if the adapter provides the API; 16 ms per solve, so budget is not a concern. |
| Margin search through the same pure `find_transfer_limit` | Same stopping rule, same `bounded_by`, same lower-bound semantics | MEDIUM | Needs the Q-scaling answer. Keep the flat-transfer guard (a sink with no load is a no-op in pandapower too). |
| Q-limit setting decided from evidence | Largest single lever on voltage-limited capacity | LOW to build, MEDIUM to decide | Laptop read of machine Q versus limits, then pick; log the chosen setting in the run `details`. |
| Replay harness over the recorded PSS/E runs | The stated acceptance test | MEDIUM | Reads run rows, `ratings_used`, mapping and scaling targets (private), re-runs pandapower, compares what was stored. Only successful runs have result rows. Check each run's `case_sha256` and `mapping_sha256`: runs made before Phase 4 used one unscaled case for all four cities, not four scaled copies, so they need the matching study variant or must be excluded and listed. |
| Agreement report with maximum deviations and pass/fail per criterion | The "done" condition | MEDIUM | Criteria as in STATE.md: same violation set per outage, bus voltages within 0.01 pu, flows and capacities within 2%, but only for the quantities that were stored (see Bottom line 2). |
| `solver` column and the same four tables | Dashboard reads one history | LOW to MEDIUM | One migration; primary keys currently `(run_id, ...)` so no key change is forced. Existing 19 rows tagged `psse`. Reuse `writer.py` with the tag. |
| Hourly GitHub Actions run with the private mapping and network as secrets, slot-time semantics and a time budget | "Results land every hour for a full day" | MEDIUM | `slot_time` must equal the UTC hour floor of `started_at` (DDL check), so a delayed cron run still lands in its own hour. Actions cron can start late and can skip; the existing gap queries already assume that. The run-time budget stays (about 1,200 solves is around 20 s; a hang is the only risk). |
| Read-only latest-result-per-city view | Dashboard unblock (DEF-01) | LOW | Newest result per city: dispatched capacity, limiting factor, solver, study time. Policy on which solver wins when both exist is a decision to take (newest regardless, or prefer one). |

### Differentiators (valuable, not required for "done")

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| One-off full-state reference dump from the laptop (all bus V, all branch flows per city base and per outage) | Lets the replay test the literal "all bus voltages within 0.01 pu, all flows within 2%" claim instead of only the stored subset | MEDIUM | Private artifact. A probe-style script reusing `PsseApi.bus_table` and `branch_loading` already exists in `psse_api.py`. |
| Calibration mode: replay under `enforce_q_lims` on and off and report which agrees | Turns the main unknown into a measurement | LOW | Same harness, one flag. |
| Near-limit "borderline" classification in the agreement report | Avoids false failures from 1e-4 pu noise at a threshold | LOW | See comparison rules. |
| Retention rule for 24 rows a day | STATE.md concern: permanent growth | LOW to MEDIUM | Decision for the owner; not required for done. |
| Agreement run on a schedule (daily recheck against any new PSS/E run) | Catches drift when a PSS/E run is added | MEDIUM | Only useful once PSS/E runs resume. |
| Per-outage solve statistics (iterations, time) in `details` | Shows pandapower health on the dashboard side | LOW | Optional. |

### Anti-Features (do not build)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Distributed slack | "More realistic" | PSS/E's `fnsl` puts the mismatch on the swing bus; distributed slack would move flows by design and break agreement | Keep `distributed_slack=False`. |
| pandapower's native `tdpf` or `consider_line_temperature` | It is a DLR project | That is a different rating method; it would conflate the solver comparison with the rating model. The job takes the rating as an input. | Apply the rating through `max_i_ka` only. |
| `mva` thermal basis and `voltage.source = case` for pandapower | Parity with every PSS/E setting | No native pandapower field for either (one `min/max_vm_pu` pair, no MVA-percent) | Support `current` and `config` only and fail loudly on the others. |
| A fake `psspy` module backed by pandapower | Would reuse `PsseApi` untouched | Needs to imitate `scal_2` status arrays, `abrnreal` option strings and other quirks; brittle | A `PandapowerApi` with the study-level method names. |
| Optimal power flow, DC load flow or other algorithms | pandapower offers them | The study is an AC load flow screen | `algorithm="nr"` only. |
| Transformer, generator or double-line outages, whole-system screens | "Full N-1" | PSS/E study does not do them; adding them breaks set equality and the "do not call this full N-1" note | Keep the same outage set; any extension is a later milestone for both solvers. |
| Pandapower-specific tuning that makes numbers match by fitting (for example scaling reactances) | Quick agreement | Hides a data or behaviour mismatch | Fix data parity and settings; never fit. |
| Committing the exported laptop network, mapping, targets or any live-database numbers | Convenience for reviewers | Repo is public; mapping and case carry grid identifiers; STATE.md and the study doc already forbid it | Secrets and local-only files; committed examples use invented values (9xxxx buses). |

## Feature Dependencies

```
Network parity report
    └──requires──> laptop export of case tables (private)
    └──enables──> every other feature below

PandapowerApi
    └──requires──> Network parity (net exists)
    └──requires──> study.py factory seam
        └──enables──> reused contingency.screen / margin.city_margin / violations / dispatch

Q-limit setting decision
    └──requires──> laptop read of machine Q vs limits, solve settings
    └──feeds──> base solve, N-1, margin, scaling convergence

Per-city scaling ──requires──> laptop read of scal_2 effects (swing in total? clamp? Q in increment form?)
Margin search ──requires──> scal_2 increment Q behaviour
Replay harness ──requires──> PandapowerApi + scaling + margin + stored run rows + private mapping
Agreement report ──requires──> Replay harness
"Done" ──requires──> Agreement report AND a full day of hourly rows

solver column migration ──requires──> nothing in the solver; must precede the hourly writes
Dashboard view ──requires──> solver column; ──enhances──> dashboard (out of scope to build)
Full-state reference dump ──enhances──> Agreement report
Distributed slack ──conflicts──> agreement with PSS/E
```

### Dependency Notes

- **Everything solver-side requires network parity:** a parity failure invalidates replay results, so it comes first.
- **The agreement harness cannot be written before the settings are known:** its value is detecting a wrong setting, so the laptop measurements (Q limits, `scal_2` effects, island behaviour, case solve settings) must be scheduled as a short laptop task early, not discovered at the end.
- **The migration precedes hourly writes** because the writer must tag rows from the first run.
- **Hourly scheduling can be built in parallel** with the replay work, but "done" needs both.

### Dependencies on existing code

| Existing module | Reuse | Change needed |
|---|---|---|
| `violations.py` | As is, fed `BusRow`/`BranchFlow` values | None |
| `dispatch.py`, `units.py` | As is | None |
| `margin.py` | `find_transfer_limit` as is; `city_margin` if the API matches | None if the adapter has `define_subsystem`/`scale_load`; otherwise a thin wrapper |
| `contingency.py` | As is through the API | None; relies on `load_case(saved_path)`, so the adapter maps paths to in-memory snapshots, or add `snapshot`/`restore` methods |
| `study.py` | Orchestration, scaling guards, combined failure | Factory argument in `_open_case`; `check_mapping` and `study_area` are pure and reused |
| `psse_api.py` | Namedtuples (`BusRow`, `BranchFlow`, `BranchRow`, `SolveResult`, `CaseTotals`) | Import from here or move to a neutral module; do not import `psspy` |
| `ratings.py`, `mapping.py`, `settings.py`, `run_record.py`, `writer.py`, `job.py` | As is | `solver` tag, version strings, new settings (for example `enforce_q_lims`, `max_iteration`) with defaults and the closed key set |
| DDL (`psse_results_v1.sql`) | n/a | One migration adding `solver` and the view |
| `docs/.../psse_study_definitions.md` | Source of semantics | A companion note for the pandapower definitions and differences |

## MVP Definition

### Launch With (v1.7)

- [ ] Laptop measurement task: solve settings and Q-limit behaviour, `scal_2` details (swing in total, clamp, Q in increment), island outcome, RATEA of unmapped lines, one-off network export (private)
- [ ] Network parity report and the pandapower net build
- [ ] `PandapowerApi` plus the `study.py` factory seam
- [ ] Study run on pandapower (scaling, base, N-1 with island handling, margin, dispatch) with the chosen Q-limit setting
- [ ] Replay harness and agreement report (stored quantities), including the calibration flag
- [ ] Migration for `solver`, writer tagging, latest-per-city view
- [ ] Hourly Actions job, secrets, and a full-day soak
- [ ] DEF-01 doc update

### Add After Validation (v1.x)

- [ ] Full-state reference dump and full-state replay, if the stored-quantity replay leaves doubt
- [ ] Retention rule for the hourly rows
- [ ] Borderline classification refinements once real disagreements are seen

### Future Consideration (v2+)

- [ ] Transformer, generator and multi-element outages in both solvers
- [ ] PSS/E PV/QV modules, if licensed and wanted

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Laptop measurement task | HIGH | LOW | P1 |
| Network parity report and build | HIGH | HIGH | P1 |
| `PandapowerApi` and factory seam | HIGH | MEDIUM | P1 |
| Scaling, base solve, island handling | HIGH | MEDIUM | P1 |
| N-1 and margin on pandapower | HIGH | MEDIUM | P1 |
| Replay harness and agreement report | HIGH | MEDIUM | P1 |
| `solver` migration, writer tag, view | HIGH | LOW | P1 |
| Hourly Actions job and soak | HIGH | MEDIUM | P1 |
| Calibration flag (Q limits on/off) | HIGH | LOW | P1 |
| Borderline classification | MEDIUM | LOW | P2 |
| Full-state reference dump | MEDIUM | MEDIUM | P2 |
| Retention rule | MEDIUM | LOW | P2 |
| Scheduled re-agreement | LOW | MEDIUM | P3 |

## Comparable Tools

| Capability | MATPOWER / pandapower converters | PSS/E (this job) | Our approach |
|---|---|---|---|
| Case import | pandapower: `from_ppc`/`from_mpc`, no RAW reader; MATPOWER has a RAW converter | `.sav` via `psspy.case` | Parity-checked net built from a laptop export, or `case39()` if proven equal |
| Q limits | MATPOWER `pf.enforce_q_lims` default 0; pandapower default False; PV to PQ, no switch back | Per case settings, OPTIONS(7) | Measure, then set; test both |
| Conversion check | `validate_from_ppc`, 1e-6 | not applicable | Data-parity tripwire at 1e-4 pu, pass criteria at 0.01 pu and 2% |
| Contingencies | pandapower has `in_service` toggling only, no screening module used here | Loop of `fnsl` (the job does not use ACCC) | Same loop, fresh copy per outage |

## Sources

- Local repository (HIGH): `backend/psse_job/{study,contingency,margin,violations,dispatch,psse_api}.py`; `docs/data-science/decisions/psse_study_definitions.md`; `docs/data-science/schema/psse_results_v1.sql`; `.planning/workstreams/pandapower-solver/STATE.md`.
- Local experiments, pandapower 3.2.2 on Python 3.9 in a scratch virtual environment, public `case39()` only, no live database (HIGH): loading definition, island NaN behaviour, Q-limit effect, scaling and margin walks, timing, stale results after failure, `t` versus `pi`.
- pandapower power-flow options (HIGH): https://pandapower.readthedocs.io/en/latest/powerflow/ac.html
- pandapower line model and result formulas (HIGH): https://pandapower.readthedocs.io/en/latest/elements/line.html
- pandapower source in the 3.2.2 wheel: `pf/run_newton_raphson_pf.py` (Q-limit loop), `powerflow.py` (`LoadflowNotConverged`), `converter/pypower/from_ppc.py` (`validate_from_ppc` default 1e-6), `networks/power_system_test_cases.py` (`case39`), converter package list (HIGH).
- pandapower historic validation tolerances, PowerFactory and PSS Sincal only (MEDIUM, old): https://pandapower.readthedocs.io/en/v1.4.3/about/tests.html
- PSSPY reference listing `fnsl`/`fdns` OPTIONS(1..8), error codes 0 to 5 and the case/save calls (MEDIUM, third-party PDF): https://www.3phaseee.com/static/docs/psspy.pdf
- MATPOWER list post on the IEEE 39-bus case: swing bus has no Q limits, Qmin violation at one generator bus (-1.37 versus 0), swing Pmax exceeded (677.87 versus 646); matches the pandapower base case exactly (MEDIUM): https://www.mail-archive.com/matpower-l@cornell.edu/msg05679.html
- PSS/E forum, unanswered RAW-to-pandapower question and the MATPOWER `psse2mpc` workaround (LOW): https://psspy.org/psse-help-forum/question/8493/convert-psse-raw-file-into-pandapower/
- PSS/E forum list of restored default solution parameters, TOLN 0.1 (LOW to MEDIUM): https://psspy.org/psse-help-forum/answers/1551/revisions/
- ZHAW comparison of pandapower, PyPSA and OpenDSS against PowerFactory, secondhand (LOW): https://website-7rv.pages.dev/open-source-power-flow-tools-benchmarked-against-powerfactory
- Not found: a Siemens manual for `fnsl()` default solution settings, `scal_2` swing and clamp behaviour, or any published pandapower-versus-PSS/E power-flow comparison. These are the UNVERIFIED items above.

---
*Feature research for: pandapower solver mirroring the PSS/E per-city grid study*
*Researched: 2026-11-16*
