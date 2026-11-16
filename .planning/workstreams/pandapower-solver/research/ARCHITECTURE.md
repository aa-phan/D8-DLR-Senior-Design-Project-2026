# Architecture Research: v1.7 pandapower Solver

**Domain:** a second, open-source power-flow solver (pandapower) running hourly in GitHub Actions beside an existing licensed-PSS/E hourly job, writing to the same Supabase tables, with a read-only dashboard view and an agreement (replay) check.
**Researched:** 2026-11-16
**Confidence:** HIGH on the integration seam, the schema, the gap check and the Actions layout (all read from the code); MEDIUM on pandapower behaviour (docs read, nothing run: pandapower is not installed in this repo's venv yet); LOW on the numerical agreement itself (that is the milestone's real risk, see "Open questions").

Scope: research only. No code was changed, no database was queried. Nothing below holds a credential, host or numeric result.

## Verdict in one paragraph

Yes: the study code runs unchanged on pandapower if a `PandapowerApi` implements the same 14 public methods as `PsseApi` and raises the same `psse_api.PsseCallError` / returns the same value types. `study.py`, `contingency.py`, `margin.py`, `violations.py`, `dispatch.py`, `run_record.validate_results` and `job.run_once` only ever touch `api.<method>` plus those exception and value types (verified by grep, table below). The only hard-coded PSS/E construction is one line, `psse_api.PsseApi(psspy_module, protected_path=case_path)` in `study._open_case`, so one additive `api_factory` parameter is the whole seam. New pandapower code lives in a new package `backend/pandapower_job/` (Python 3.12, free to import pandas, numpy, pandapower) that imports `psse_job`'s pure modules; `psse_job` never imports it. The "solver" tag needs small additive, default-preserving edits in five `psse_job` files (columns tuple, run id, run context, run_once, study factory) plus one additive migration; the child tables inherit the solver through `run_id` and need nothing.

## Standard Architecture

### System Overview

```
 cron-job.org (hourly, HH:20)                    owner's licensed laptop (paused)
        |  workflow_dispatch                              |  Task Scheduler (unchanged)
        v                                                 v
+---------------------------------------------+  +----------------------------------+
| GitHub Actions: pandapower_hourly.yml       |  | psse_run_hourly.py (3.7 syntax)  |
|  runner py3.12, environment: production     |  |  launcher -> study(PsseApi)      |
|  pandapower_run_hourly.py                   |  +----------------+-----------------+
|   pandapower_job.runner                     |                   |
|    reads ratings (psse_job.ratings, REST)   |                   |
|    study = psse_job.study.make_study(       |                   |
|        api_factory=PandapowerApi)           |                   |
|    job.run_once(solver="pandapower")        |                   |
+--------------------+------------------------+                   |
                     | one transaction, role dlr_psse_writer      |
                     v                                            v
+----------------------------------------------------------------------------------+
| Supabase Postgres (private tables)                                               |
|  psse_run (+ solver, solver_version)  <-FK(run_id, outcome)-  psse_dispatched_capacity
|                                        <-FK-  psse_voltage_margin                 |
|                                        <-FK-  psse_contingency_result             |
|  view latest_grid_study (new, definer-style, narrow columns) -> anon/authenticated|
+--------------------+-----------------------------+---------------------------------+
                     | SELECT (read only)          | SELECT via dashboard key
                     v                             v
   pandapower_job.replay (local CLI)        Software team's dashboard (DEF-01)
   reads recorded PSS/E runs, re-solves
   in memory with pandapower, prints a
   comparison; writes nothing
```

### Component Responsibilities

| Component | New / Modified | Responsibility | Talks to |
|-----------|----------------|----------------|----------|
| `backend/pandapower_job/api.py` `PandapowerApi` | NEW | Same public methods as `psse_api.PsseApi`, backed by a `pandapowerNet` | `study.py` (via factory), `psse_api` value types and exceptions |
| `backend/pandapower_job/network.py` | NEW | Load the committed network JSON, verify its sha256, build the PSS/E-id to pandapower-index translation, refuse `parallel != 1` | `PandapowerApi` |
| `backend/pandapower_job/runner.py` + `backend/pandapower_run_hourly.py` | NEW | Entry: build config from env, `prepare_run`, call `job.run_once`, print one identifier-free line, map exit codes | `psse_job.job`, `psse_job.study`, `psse_job.writer`, `psse_job.ratings` |
| `backend/pandapower_job/replay.py` | NEW | Read-only agreement harness (section 5) | `psse_job.study`, `psse_job.mapping`, `psse_job.ratings`, `psse_job.writer.connect` (read-only session) |
| `backend/psse_job/study.py` | MODIFIED (additive) | `api_factory` parameter on `_open_case`, `index_case`, `make_study`, `prepare_run` | callers |
| `backend/psse_job/contract.py` | MODIFIED | `PSSE_RUN_COLUMNS` gains `solver`, `solver_version`; `RunContext` gains two defaulted fields | `run_record`, `writer` |
| `backend/psse_job/run_record.py` | MODIFIED | `new_run_id(started_at, solver="psse")`, `build_run_record` fills the two columns | `job` |
| `backend/psse_job/job.py` | MODIFIED | `run_once(..., solver="psse", solver_version=None)` | `launcher`, `runner` |
| `backend/psse_job/constants.py` | MODIFIED | `SOLVERS`, run-id prefix per solver | all |
| `backend/psse_job/gaps.py`, `docs/data-science/schema/psse_run_gaps.sql` | MODIFIED | Per-solver gaps (section 3) | `launcher gaps` mode, `pandapower_job` CLI |
| `backend/psse_job/psse_api.py`, `contingency.py`, `margin.py`, `violations.py`, `dispatch.py`, `units.py`, `ratings.py`, `mapping.py`, `settings.py`, `writer.py`, `redaction.py` | UNCHANGED | Reused as they are | |
| `supabase/migrations/<ts>_psse_solver_column.sql` | NEW | `solver`, `solver_version`, constraints, index | applied by the owner |
| `supabase/migrations/<ts>_expose_latest_grid_study.sql` | NEW | The dashboard view and its grants | applied by the owner, after the soak |
| `.github/workflows/pandapower_hourly.yml` (+ gap-check and agreement workflows) | NEW | Actions layout (section 6) | |

## Recommended Project Structure

```
backend/
  psse_job/                      # UNCHANGED location, 3.7 syntax, stdlib only (D-05)
  pandapower_job/                # NEW, Python >= 3.10 (CI: 3.12)
    __init__.py
    api.py                       # PandapowerApi (+ PP_SURFACE evidence table)
    network.py                   # load/verify/translate the network
    runner.py                    # env -> config, prepare_run, run_once, exit codes
    replay.py                    # agreement harness
    data/
      ieee39_pandapower.json     # public case (IEEE 39 is public); sha256 pinned in a test
  pandapower_run_hourly.py       # tiny entry, like psse_run_hourly.py
  tests/
    pandapower_api_test.py       # parity + tiny-net behaviour tests (real pandapower, no fake)
    pandapower_study_test.py     # make_study end to end on a tiny net
    pandapower_runner_test.py    # exit codes, no identifiers in output
    pandapower_replay_test.py    # synthetic "recorded" rows on local Postgres
    pandapower_import_gate_test.py
requirements-pandapower.txt      # separate from requirements.txt
supabase/migrations/             # two new additive files
docs/data-science/schema/psse_results_v1_1_solver.md (+ .sql)   # additive spec, v1 files stay frozen
```

### Structure Rationale

- **A separate package, not a subfolder or edit of `psse_job`:** `psse_job` must keep parsing on PSS/E's interpreter and the gate test (`backend/tests/psse_contract_test.py`: `test_imports_stay_inside_the_laptop_boundary`, `test_importing_psse_job_loads_no_heavy_module`) forbids pandas, numpy, config and anything outside a stdlib allow-list. pandapower 3.5.6 needs Python >= 3.10, pandas ~=2.3, numpy < 2.5, scipy >= 1.15 (PyPI metadata). The repo's pins (pandas 2.3.3, numpy 2.4.3, scipy 1.17.1) and its CI Python (3.12, `dlr_live.yml`) satisfy all of those, so no environment fight, but pandapower is installed only where it is needed.
- **Dependency direction is one-way:** `pandapower_job -> psse_job`. 3.7-syntax code runs fine on 3.12 (the existing suite already runs it there). The existing allow-list gate flags any `psse_job -> pandapower_job` import automatically; add a mirror gate test asserting `psse_job` never mentions `pandapower`.
- **The name `pandapower_job`, never `pandapower`:** a local package named `pandapower` would shadow the library.
- **`requirements-pandapower.txt` instead of editing `requirements.txt`:** `dlr_live.yml` installs `requirements.txt` every hour; pandapower pulls pandera, networkx, deepdiff, geojson, tqdm, colorama, packaging and would slow and widen that unrelated workflow. Pin the same pandas, numpy, scipy, psycopg versions as `requirements.txt` and add a test that the shared pins are equal.

## 1. Can the pandapower adapter implement the PsseApi interface?

### What the study actually depends on (grep of `api.` in the study modules)

| Caller (file:function) | Methods used |
|---|---|
| `study.py:_open_case` / `index_case` | `PsseApi(...)` constructor (the one hard-coded PSS/E line, 326), `version`, `load_case`, `branch_table`, `bus_table` |
| `study.py:apply_ratings` | `read_rate`, `set_rate` |
| `study.py:solve_base`, `_read_solved_base` | `solve`, `bus_table`, `branch_loading` |
| `study.py:_save_solved` | `save_case` |
| `study.py:prepare_city_base`, `scale_city_case` | `load_case`, `read_totals`, `scale_case` |
| `contingency.py:screen` | `load_case`, `set_status`, `solve`, `bus_table`, `branch_loading` |
| `margin.py:city_margin` | `load_case`, `define_subsystem`, `scale_load`, `solve`, `bus_table`, `branch_loading` |
| all of the above | catch `psse_api.PsseCallError` and `ValueError`; use `BranchRow`, `BusRow`, `BranchFlow`, `SolveResult`, `CaseTotals` |
| `violations.py`, `dispatch.py` | consume those value types only (no `api.` call) |

So the interface is exactly the 14 public methods of `PsseApi` plus its value types. `probe.py` uses the same set (PSS/E-only, unaffected).

### Two ways to do it, and the recommendation

| Option | How | Verdict |
|---|---|---|
| A. Emulate `psspy` over pandapower and keep `PsseApi` | Re-implement the 19 SURFACE functions (bulk-column returns, sentinels, ierr codes, the `scal_2` open-totals-read rule) on a pandapower net; `PsseApi` wraps it | REJECT. Zero edits to `study.py`, but it reproduces psspy's quirks (`scal_2` apiopt 1/2 state machine, sentinels, column alignment) for no benefit, and the `solver` column needs contract edits anyway |
| B. Duck-typed `PandapowerApi` with the same public methods | Same names, signatures, return types, exceptions as `PsseApi`; `study.py` gains `api_factory` | RECOMMEND. The 14 methods are already the clean interface; the SURFACE table is PSS/E-specific plumbing |

Required edit in `study.py` (3.7 syntax, additive):

```python
# study.py
def _default_api_factory(backend, case_path):
    return psse_api.PsseApi(backend, protected_path=case_path)

def _open_case(backend, case_path, api_factory=None):
    api = (api_factory or _default_api_factory)(backend, case_path)
    ...
# index_case(backend, case_path, mapping, api_factory=None)
# make_study(backend, case_path, mapping, clock=None, api_factory=None)
# prepare_run(backend, case_path, mapping_path, allow_placeholder=False, clock=None, api_factory=None)
```

Pin the parity with a test (the pattern `psse_api_test.test_scale_layout_matches_the_fake` already uses): the public method names and `inspect.signature` parameter names of `PandapowerApi` must equal those of `PsseApi`.

### SURFACE row to pandapower mapping (every row, plus the `scal_2` forms)

State held by `PandapowerApi`: `_master` (the pristine net, loaded once, never mutated), `_net` (working net), `_snapshots` (path label to net), `_subsystems` (sid to bus indices), `_translation` (PSS/E bus number and (from,to,ckt) to pandapower indices). The "temp file" paths `study.py` passes are only labels: nothing is written to disk.

| # | psspy function (SURFACE) | `PsseApi` method | pandapower implementation |
|---|---|---|---|
| 1 | `psseversion` | `version()` | `"pandapower " + pandapower.__version__`; goes to the new `solver_version` column, `psse_version` stays NULL |
| 2-4 | `getdefaultint/real/char` | constructor sentinels | Not needed (no "no input" markers: pandapower writes values by attribute). Keep `calls`/`warnings` lists for tests |
| 5 | `case` | `load_case(path)` | path == the case path: `self._net = copy.deepcopy(self._master)`; path in `_snapshots`: deep copy of that snapshot; anything else: `PsseCallError("case", 3, ...)`. This is the "fresh scaled copy per city" and "reload saved base before every outage" |
| 6 | `save` | `save_case(path)` | Refuse the protected path (`CaseProtected`, same rule); else `_snapshots[label] = copy.deepcopy(self._net)` |
| 7-10 | `fnsl`, `solved`, `iterat`, `sysmsm` | `solve(options)` | `pandapower.runpp(net, **RUNPP_KWARGS)`; `LoadflowNotConverged` becomes `classify_solve(0, 1, ...)` (not converged, "iteration limit exceeded"); success `classify_solve(0, 0, iterations, mismatch)`. Iterations from `net._ppc["iterations"]` (private, guard it; `None` is accepted); mismatch `None` (`solve_base` skips the check on `None`). `options` (the 8-int PSS/E list) is ignored, so `settings.solve_options` must stay `None` |
| 7 (island) | `fnsl` ierr 3 | `solve` | pandapower silently isolates unsupplied buses (NaN results, `check_connectivity` default). Mirror PSS/E: if any in-service bus has a NaN voltage after the solve, return `classify_solve(3, None)` so the outage becomes a `non_convergence` row. Without this, `contingency._collapsed` still catches NaN, but the recorded reason would differ |
| 11,12 | `abrnint`, `abrnchar` | `branch_table()` and the key part of `branch_loading()` | Lines from `net.line`, transformers from `net.trafo`; `BranchRow(from_bus, to_bus, ckt, in_service, is_transformer)` with PSS/E bus numbers and ckt via the translation (pandapower has no circuit id). Refuse `parallel != 1` at load (one pandapower row per PSS/E circuit) |
| 13 | `abrnreal` | `branch_loading(rate_set, basis)` | `rate_mva = sqrt(3) * vn_kv * max_i_ka * df`; `pct` for basis "current" = `res_line.loading_percent` (documented as `max(i_from, i_to) / (max_i_ka * df * parallel) * 100`), for basis "mva" computed from `p/q` at the larger end over `rate_mva`; `p_mw = p_from_mw`; `max_mva` = larger-end `hypot(p, q)`. Out-of-service line gives 0.0 not NaN. `rate_set` is validated (RATEA/B/C) and otherwise ignored: pandapower has one limit |
| 14,15 | `abusint`, `abusreal` | `bus_table()` | `BusRow` from `net.bus` + `net.res_bus`; `type_code`: 4 out of service/NaN, 3 ext_grid bus, 2 in-service gen bus, else 1 (only `<4` versus `>=4` matters downstream); `pu` = `vm_pu` (1.0 before any solve); NVLMLO/HI from optional `min_vm_pu`/`max_vm_pu`, else 0.0, which makes `violations._limits_and_source` fall back to the configured pair; EVLMLO/HI have no equivalent (0.0) |
| 16 | `brndat` | `read_rate(ref, rate_set)` | `sqrt(3) * vn_kv * max_i_ka * df` (MVA, per circuit) |
| 17 | `branch_chng_3` | `set_rate`, `set_status` | `net.line.at[idx, "max_i_ka"] = mva / (sqrt(3) * vn_kv)` for any listed rate set (all three alias one field; the read-back loop in `apply_ratings` still passes); `net.line.at[idx, "in_service"] = bool`. A transformer ref raises `PsseCallError("branch_chng_3", 3, "branch is a two-winding transformer")`, as PSS/E does |
| 18 | `bsys` | `define_subsystem(sid, buses)` | Store the pandapower bus indices under `sid`; unknown bus gives `PsseCallError("bsys", 1, ...)` |
| 19a | `scal_2` increment form | `scale_load(sid, increment_mw)` | Multiply `p_mw` and `q_mvar` of the in-service loads on the subsystem's buses by `(P + inc) / P` (constant power factor). A subsystem with no load is a no-op, so the existing `_check_loads_mapped_branches` guard ("flow did not rise") fires exactly as it does on PSS/E. The ext_grid absorbs it (distributed slack off), as the swing bus does |
| 19b | `scal_2` totals read (apiopt 1, then the apiopt 2 close) | `read_totals()` | `CaseTotals(sum of in-service load p_mw, generation total)`. No close step exists. Generation total = in-service `gen` + `sgen` plus the swing machine's saved dispatch (see "Swing machine" below) |
| 19c | `scal_2` new-total form | `scale_case(load_mw, gen_mw)` | Factor `load_mw / load_total` on every in-service load's `p_mw` and `q_mvar`; factor `gen_mw / gen_total` on every in-service generator's `p_mw`. `study.scale_city_case` then reads the totals back and enforces its 1e-3 tolerance unchanged |

Methods with no pandapower counterpart are not needed: `PsseApi._bulk`, `_call`, `_plain_ierr`, the SURFACE table itself, `SCALE_LAYOUT`.

### Copy semantics: deep copy, never mutate-and-restore

- `load_case` always yields a fresh `copy.deepcopy` of either the pristine master or a saved snapshot. This is the same discipline `contingency.screen` documents ("an outage is never un-tripped and re-solved, so a blown-up solution cannot contaminate the next outage"): flipping `in_service` back is not equivalent, because a failed `runpp` leaves partial `res_*` tables and `_ppc` state on the object.
- Cost is the only argument for the alternative. A 39-bus net is small; the screen is capped (`contingency.max`, default 200 outages per city) and the margin search is bounded by `extra_steps`, so the worst case is some thousands of deep copies against a 1500 s default budget (`settings.max_runtime_seconds`). Measure it in phase 1 (UNVERIFIED); if it matters, snapshot only the mutable columns (`line.in_service`, `line.max_i_ka`, `load.p_mw/q_mvar`, `gen.p_mw`) instead of the whole net.
- Do not use `init="results"` warm starts: they reintroduce the contamination the deep copy avoids. Use the default start.

### Swing machine (a data-fidelity wrinkle that affects `scale_case`)

PSS/E's `scal_2` scales every in-service machine including the swing machine, whose saved P is part of the case's generation total. In pandapower the `ext_grid` has no P input (its output is a result). To reproduce the same generation scale factor the translated network must carry the swing machine's saved dispatch as a custom column (for example `net.ext_grid["p_saved_mw"]`), counted in `read_totals()` and scaled but never fed to the solver. Without it `gen_total` differs and the per-city generation scaling factor differs from PSS/E's, which changes every flow downstream. HIGH confidence that this is needed; the exact column is a phase 1 decision.

### Adapter parity knobs (decide once, in code, recorded by git commit)

`RUNPP_KWARGS` lives in `api.py`, not in the mapping file: `settings.parse_settings` rejects unknown keys, and a schema change to the private mapping buys nothing. The knobs that decide agreement with PSS/E: `enforce_q_lims` (PSS/E enforces var limits by default through the case's solution settings; pandapower defaults to off), `voltage_depend_loads` (pandapower defaults on, PSS/E studies run constant-power), `trafo_model`, `calculate_voltage_angles`, `tolerance_mva`, `max_iteration`. These are the first suspects when agreement fails (feed PITFALLS).

## 2. Where the new code lives (Python 3.7 constraint)

- New package `backend/pandapower_job/` (see structure). Modern syntax allowed (the existing gate that rejects generics and new stdlib applies to `psse_job` only).
- The edits that DO touch `psse_job` must keep 3.7 syntax and stay stdlib-only, because `test_*new_feature*` and the import-gate tests police them and the laptop copy must still parse. They are all additive with defaults that preserve PSS/E behaviour:

| File:function | Edit |
|---|---|
| `contract.py:PSSE_RUN_COLUMNS`, `RunContext` | append `solver`, `solver_version` (`RunContext` fields get defaults `"psse"`, `None`; `namedtuple(..., defaults=)` is 3.7-safe, so `launcher._dry_run_mode`'s positional construction still works) |
| `constants.py` | `SOLVERS = ("psse", "pandapower")`, `RUN_ID_PREFIX = {"psse": "psse", "pandapower": "pp"}` |
| `run_record.py:new_run_id`, `build_run_record` | prefix by solver; two more `values` entries (so failed rows carry the solver too) |
| `job.py:run_once` | `solver="psse", solver_version=None` keywords, passed to `new_run_id` and `RunContext` |
| `study.py` | `api_factory` (section 1) |
| `gaps.py`, `psse_run_gaps.sql` | solver column and filter (section 3) |

- Alternative considered and rejected: fork `run_record`, `writer` and `job` into `pandapower_job`. It duplicates `validate_results` (the DDL-identity checks that make a pandapower row safe to write) and the all-or-nothing writer, and the two copies would drift.
- What does not move: the PSS/E laptop entry (`backend/psse_run_hourly.py`, `launcher.py`) keeps working with defaults; `launcher.py` needs only the `gaps --solver` option.
- The pandapower entry does NOT reuse `launcher.main`: its `CONFIG_KEYS` require `PSSE_PSSPY_DIR` for `run`, its D-01 forbids reading the environment (the correct rule on a laptop, wrong on Actions), and the lock, preflight and PSS/E start-up are meaningless on a runner. `pandapower_job.runner` composes the same pure pieces instead: `ratings.fetch_latest_rating(env)`, `study.prepare_run(..., api_factory=PandapowerApi)`, `job.run_once(..., solver="pandapower", solver_version=...)`, `writer.connect(env=...)`. `fetch_latest_rating` and `writer.connect` already take an `env` mapping, so no change is needed.

## 3. Schema change

### Migration (additive; never edit `20261109233541_psse_results.sql`, it is applied and sha-pinned)

```sql
-- sketch only
alter table public.psse_run
  add column if not exists solver text not null default 'psse'
      constraint psse_run_solver_ck check (solver in ('psse', 'pandapower')),
  add column if not exists solver_version text
      constraint psse_run_solver_version_ck check (length(solver_version) between 1 and 100);

alter table public.psse_run
  drop constraint psse_run_run_id_ck,
  add constraint psse_run_run_id_ck
      check (run_id ~ '^(psse|pp)-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$'),
  add constraint psse_run_solver_run_id_ck
      check ((solver = 'psse') = (left(run_id, 5) = 'psse-'));

create index if not exists psse_run_solver_slot_time_idx on public.psse_run (solver, slot_time desc);
comment on column ... ;   -- unit-first comments, like every existing column
```

Decisions and why:

- **Existing rows are tagged by the default.** `add column ... not null default 'psse'` is a metadata-only change for a constant default in current Postgres, so all existing rows read `psse` with no rewrite and no separate UPDATE (the writer role has none anyway). **Keep the default permanently**: the PSS/E job must stay usable unchanged; a laptop copy that does not know the column still inserts and gets `psse`.
- **The default is also the danger, so tie it to the run id.** A pandapower insert that forgot `solver` would be tagged `psse` and masquerade as the industry reference. `psse_run_solver_run_id_ck` makes that insert fail loudly because the run id carries the solver (`pp-` prefix). That is why the run id pattern is widened instead of reusing `psse-` for both.
- **`run_id` pattern:** `pp-<UTC yyyymmddThhmmssZ>-<8 hex>`. Dropping and re-adding `psse_run_run_id_ck` revalidates the existing rows (all `psse-`); table is tiny.
- **`solver_version`:** records `pandapower 3.5.6` so a replay or an agreement regression is reproducible; `psse_version` stays NULL for pandapower rows (no CHECK on it today, and its comment says NULL when not reached, so the v1.1 doc must say "also NULL for pandapower"). Not strictly required by the milestone; recommended, cheap. `case_id` (a label of the network file) and `case_sha256` (sha256 of the committed network JSON) already fit the pandapower case; `mapping_sha256` is unchanged; `rate_set` for pandapower should be the label `max_i_ka`.
- **`failed_stage` vocabulary, `outcome` vocabulary, `ratings_used` shape:** no change. Every stage name exists for pandapower (`load_case` covers a network that fails to load).
- **Child tables do not need `solver`.** Each carries `(run_id, run_outcome)` as a composite FK to `psse_run (run_id, outcome)` and `run_id` is globally unique (timestamp + 8 hex, now prefixed per solver), so the solver is one join away. Denormalising it into three tables would add three columns, three constraints and a second place for the tag to disagree. The completeness checks in `psse_results_v1_checks.sql` are keyed by `run_id` and stay valid unchanged; optionally add one check `solver_matches_run_id_prefix` (belt and braces over the CHECK).
- **Unique slot keys: do not add one.** There is none today (the table is append-only and two runs in one slot are both kept; the reading rule picks the newest). PSS/E and pandapower rows in one hour do not collide at the database: the primary key is `run_id`. A unique `(solver, slot_time)` would be wrong: a duplicate dispatch from cron-job.org or a manual re-run is legitimate, and a violated unique on `write_run` would be reported as a failed run with stage `write`, hiding a good one. Keep `on conflict (run_id) do nothing` as the only idempotency rule and add only the non-unique `(solver, slot_time desc)` index, which serves both the gap check and the view.
- **Privileges:** table-level `INSERT, SELECT` already granted to `dlr_psse_writer` covers new columns; policies are per table and unaffected; `verify_psse_results.sql` needs no change (it counts privileges per relation, and the new view must NOT be granted to the writer so its "holds nothing on other relations" check keeps passing).
- **Docs and tests (what else breaks):**
  - `docs/data-science/schema/psse_results_v1.sql` marked region and `psse_results_v1.md` column tables are pinned by `psse_schema_doc_test.py` (`_ddl_columns` equals the doc rows, region sha256, required headings list). Do not edit them to add columns. Add `psse_results_v1_1_solver.md` (+ an additive `.sql` reference of the two changes) as the authority for the new columns, and add one-line cross-references under the existing "Reading rules" and "Versioning" sections (the heading list and the `started_at desc, run_id desc` needle must survive).
  - `psse_run_record_test.test_contract_columns_match_reference_ddl` asserts `PSSE_RUN_COLUMNS + DB_DEFAULT_COLUMNS == v1 DDL columns`; it needs to expect v1 columns plus the two additive ones (added columns land after `created_at` in the table; the INSERT names columns, so order in the tuple is free, but the test must say what it expects).
  - `psse_results_migration_test.test_text_there_is_one_psse_migration_named_by_utc_timestamp_and_it_sorts_last` asserts the psse migration is the last file in `supabase/migrations`; two new migrations break it by design, so it must be rewritten to "the v1 migration is unchanged and pinned; later psse_* migrations are additive".
  - `psse_local_pg.apply_schema` applies the Phase 4 migrations and the reference DDL only; it must also apply the new solver migration or every writer and study-job test fails against a database without the column.
  - The new migration gets a text test (header is comments, no credential) and a local-Postgres test (default tags old rows, `pp-` run with solver `psse` is rejected, writer can insert both, anon and authenticated still hold nothing).

### Gap check and reading rules, per solver

Today `psse_run_gaps.sql` computes `min(slot_time)` and groups `seen` by `slot_time` only. Once pandapower writes every hour, PSS/E hours would look complete (a pandapower row fills the slot) and the first-slot bound would be wrong. Change it so every step is per solver:

```sql
-- sketch
with bounds as (
    select solver, min(slot_time) as first_slot,
           (date_trunc('hour', now() at time zone 'UTC') at time zone 'UTC') - interval '1 hour' as last_closed_slot
    from public.psse_run group by solver
),
expected as (select b.solver, g.slot_time
             from bounds b, generate_series(b.first_slot, b.last_closed_slot, interval '1 hour') as g(slot_time)),
seen as (select solver, slot_time, count(*) as runs,
                count(*) filter (where outcome in ('ok','fallback')) as complete_runs,
                count(*) filter (where outcome = 'failed') as failed_runs
         from public.psse_run group by solver, slot_time)
select e.solver, e.slot_time, case when s.slot_time is null then 'no_run' else 'failed_only' end as gap_kind,
       coalesce(s.runs, 0) as runs, coalesce(s.failed_runs, 0) as failed_runs
from expected e left join seen s on s.solver = e.solver and s.slot_time = e.slot_time
where s.slot_time is null or s.complete_runs = 0
order by e.solver, e.slot_time;
```

- The five rules of the file hold per solver (several rows in one hour are not a gap; a failed-only hour is listed; the current hour is excluded; hours before a solver's first run are not gaps; a solver with no rows gives no rows).
- Keep "the SQL file is the only gap logic": the statement returns all solvers (a leading `solver` column, which stays runnable as is in the Supabase SQL editor); `gaps.py` filters by solver in Python exactly as it already filters by `since`/`until`. Changes: `GapRow` gains `solver`, `run()` gains `solver=None`, `SUMMARY_SQL` becomes per solver, and the launcher `gaps` mode and the new CLI take `--solver`. `psse_gaps_pg_test.py` needs per-solver cases (a pandapower row must not fill a PSS/E hour).
- Operational consequence: the PSS/E job is paused, so `gaps --solver psse` will list every hour since its last run until a host runs it. Make `--solver` required in the pandapower CLI and treat PSS/E gaps as expected while paused.
- Reading rule (`psse_results_v1.md`, "Reading rules"): the result set of an hour is the newest `psse_run` for that `slot_time` **and solver** with outcome `ok` or `fallback`, ordered by `started_at desc, run_id desc`; never combine values across solvers any more than across cities. Both solvers can legitimately hold a set for the same hour.

## 4. The dashboard view

Decision already taken (STATE.md): four tables stay private; one read-only view readable with the dashboard's key.

**Name:** `public.latest_grid_study` (solver-neutral; a `psse_` prefix would mislead because it also carries pandapower rows).

**Semantics:** newest complete run per solver, then that run's four city rows. Picking the run first (`distinct on (solver)` over `psse_run` where outcome in (`ok`,`fallback`), `order by solver, slot_time desc, started_at desc, run_id desc`) guarantees one coherent run per solver and keeps the reading rule; picking newest per `(solver, city)` could mix runs. Result: up to eight rows (4 cities x 2 solvers). While PSS/E is paused its four rows exist but are stale; the dashboard selects `solver = 'pandapower'` for the live figure and may show PSS/E as the reference.

**Columns (one-way list: names are never renamed or dropped, only appended; Python twin `backend/latest_grid_study_contract.py` plus a drift test, the pattern of `latest_rating_contract.py` and `day_ahead_contract.py`):**

| Column | Source | Why |
|---|---|---|
| `solver` | `psse_run.solver` | required by the decision |
| `city` | `psse_dispatched_capacity.city` | one row per city per solver |
| `slot_time` | `psse_run.slot_time` | the study hour |
| `finished_at` | `psse_run.finished_at` | study time to the second |
| `run_outcome` | dispatch `run_outcome` | `ok` or `fallback` |
| `rating_source`, `fallback_reason` | dispatch | the dashboard can say "static rating used" (today every row is static, reason provisional) |
| `applied_amps_per_conductor`, `dispatched_amps_per_conductor` | dispatch | comparable with `latest_rating.rating_amps` (per conductor) |
| `applied_mva`, `voltage_limit_mva`, `dispatched_mva` | dispatch | the capacity and what bounds it, per circuit |
| `usable_fraction` | `dispatched_mva / applied_mva` | the "grid can use N% of this rating" of DEF-01 |
| `limiting_factor` | dispatch | `dlr_rating` or `voltage_stability` |
| `age_minutes`, `is_stale` | computed from `slot_time`, same 90-minute rule as `latest_rating` | an explicit "No grid study available / old" state |

**Not exposed on purpose:** `details` (branch keys, sink buses), `critical_bus`, anything from `psse_voltage_margin` or `psse_contingency_result`, `run_id`, case and mapping hashes, `error`. These are the grid identifiers the tables are private for (the reason D-03 gives).

**Security model (differs from the two existing views):** `latest_rating` and the day-ahead views use `security_invoker = true`, so row-level security on the base table decides. That cannot work here: `anon` and `authenticated` hold nothing on the psse tables, so an invoker view returns nothing or errors. The view must run with its owner's rights (`security_invoker = false`, stated explicitly in the DDL) and the narrow column list IS the access control. Consequences to plan for:

1. Grant only on the view: `revoke all on public.latest_grid_study from public, anon, authenticated; grant select on public.latest_grid_study to anon, authenticated;`. Do not grant `dlr_psse_writer` anything on it.
2. `supabase/ops/verify_exposure.sql` and `backend/tests/expose_migration_test.py` pin exactly five published objects and "10 of 10 grants". Both change: add the view to `published`, expect 12 of 12, and add checks that the view exists with the exact column list and unit-first comments, that it is deliberately not `security_invoker` (the inverse of `latest_rating_is_security_invoker`), that `anon` still has no privilege on any `psse_*` table, and that the view exposes no identifier column.
3. Supabase's database advisor flags definer-style views ("security definer view"); record it as an accepted finding with this reasoning rather than "fixing" it into an empty view.
4. Apply the view migration last, after the soak and the agreement check, as the day-ahead exposure was (applied only after the first live run was verified): no unverified figure reaches the dashboard.
5. Consumer docs: add a section to `docs/integration/rest-api.md` (the pattern `day_ahead_consumer_docs_test.py` pins). DEF-01's own text lives in `DASHBOARD-REQUIREMENTS.md` chapter 10 on the software-dashboard workstream, which is a separate worktree/branch (not in this checkout's `.planning/workstreams`); the "DEF-01 is unblocked" edit is a change on that branch and needs coordination, not a file in this branch.
6. Optional, later: a staleness alarm for the pandapower feed (extend `assert_fresh` or add a sibling function). A GitHub dispatch that never fires writes no row at all (a failed run is only recorded if the job started), so `is_stale` and the gap check are the only signals.

## 5. Replay and agreement harness

`pandapower_job/replay.py`, run locally by the owner (`python backend/pandapower_run_hourly.py replay ...`); not a workflow that publishes detail.

### Flow

```
psse_run (solver='psse', outcome in ok/fallback)       <- read-only session
   |  ratings_used (jsonb), mapping_sha256, case_sha256, n_contingencies*, started_at
   +--> rebuild Selection: one ratings.RatingChoice per city from ratings_used
   |       (source, fallback_reason, rating_amps_per_conductor, subconductors, row links parsed with ratings.parse_ts)
   +--> load the private mapping file; require sha256 == psse_run.mapping_sha256, else flag "mapping changed" and skip
   +--> data reconciliation (before any solve): see below
   +--> study.make_study(backend, case_path, mapping, api_factory=PandapowerApi)(selection, context)  -> StudyResults in memory
   +--> run_record.validate_results(results, selection)   (same identity checks as a real write)
   +--> compare with the recorded rows (join on run_id): dispatched_capacity, voltage_margin, contingency_result
   +--> report; no insert, no update, no file written with values
```

- Read-only enforced the way `gaps.run` does it: `writer.connect(env=...)` returns an autocommit connection, so set `conn.autocommit = False; conn.read_only = True` before the first statement, and add a test that the module issues no `insert`/`update`/`delete` and never imports `writer.write_run`. The role `dlr_psse_writer` already holds SELECT on all four tables, so no new credential is needed.
- Same code path as the hourly job (`make_study`, same mapping, same `settings`), so a disagreement is a solver or data difference, never a harness difference. Contingency ids are `<CITY>:<from>-<to>-<ckt>` for both solvers, which is what makes the comparison a key-for-key join.

### What PSS/E recorded, and therefore what can be compared

| Milestone criterion | Checkable from the recorded rows? |
|---|---|
| Same overload and voltage-violation set per outage | YES: set equality of `(contingency_id, violation_kind, element_id)` per run, plus `n_contingencies` and `n_contingencies_with_results` |
| Flows and capacities within 2 percent | YES for the recorded values: `observed_value` and `limit_value` of thermal rows, margin `base_transfer_mw`, `limit_transfer_mw`, `margin_mw`, `voltage_limit_mva`, `dispatched_mva`, `limiting_factor`, and `details.bounded_by` |
| Bus voltages within 0.01 pu | ONLY for the voltages that were recorded: `observed_value` of `voltage_low`/`voltage_high` rows and margin `min_voltage_pu` and `critical_bus`. The tables do NOT store the solved base bus table or branch flows, so "every bus within 0.01 pu" cannot be checked from them |

That last gap is the main design finding: replaying stored runs proves agreement on what the result tables captured. A whole-network voltage comparison needs one extra PSS/E-side artifact (a one-off export of the solved base bus and branch tables per city from a licensed machine, or a public IEEE 39-bus reference solution). Decide that at requirements time; it changes whether "the agreement check passes" means "on recorded outputs" or "on the full state".

### Free early reconciliation (do this first, it needs no solve)

The recorded rows already contain network facts: dispatch `line_voltage_kv` per city, `details.branches` (the mapped circuit keys), `details.rate_before_mva` (the case's own ratings before the DLR rating replaced them), and the margin `details.sink_buses`. Comparing them with the pandapower network (kV per mapped line, circuit keys resolvable, original `sqrt(3) * kV * max_i_ka`) tells whether the network data matches the PSS/E copy before any load-flow disagreement is debugged. This answers the STATE.md concern ("pandapower's built-in 39-bus case comes from MATPOWER; the PSS/E copy may differ") cheaply.

### Output and where it may run

- Report = per run, per city: pass/fail per criterion, counts of compared elements, worst relative and absolute differences. Exit code: 0 all agree, 1 disagreement, 6 could not run (match the launcher's code vocabulary).
- Public repository: GitHub Actions logs and artifacts of a public repo are readable by anyone. The detailed report names bus numbers, branch keys and values, so it must stay on the owner's machine. If a workflow runs the harness at all, it prints counts and PASS/FAIL only (the `psse_job` launcher's own "counts only" rule).
- Tolerances live in one dict in `replay.py` (2 percent relative, 0.01 pu absolute) and are printed in the report header; a tolerance change is a code change, not a flag.

## 6. GitHub Actions layout

Follow `dlr_live.yml`, which is the repo's tested precedent:

```yaml
name: pandapower hourly study
on:
  workflow_dispatch:            # cron-job.org, about HH:20; NO schedule trigger (it started runs hours late)
    inputs:
      dry_run: { description: "Study and validation only, no write", required: false, default: "" }
permissions: { contents: read }
concurrency: { group: pandapower-hourly, cancel-in-progress: false }
jobs:
  study:
    if: github.ref == 'refs/heads/main'      # only main sees the secrets
    environment: production
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12', cache: 'pip', cache-dependency-path: requirements-pandapower.txt }
      - run: python -m pip install -r requirements-pandapower.txt
      - name: Pre-flight (no secrets)
        run: PYTHONPATH=backend python backend/pandapower_run_hourly.py selftest
      - name: Materialise the private mapping
        env: { MAPPING_B64: "${{ secrets.PSSE_MAPPING_B64 }}" }
        run: umask 077; printf '%s' "$MAPPING_B64" | base64 -d > "$RUNNER_TEMP/mapping.json"
      - name: Run the study
        env:
          SUPABASE_PSSE_DB_URL: ${{ secrets.SUPABASE_PSSE_DB_URL }}
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_PUBLISHABLE_KEY: ${{ secrets.SUPABASE_PUBLISHABLE_KEY }}
          PANDAPOWER_MAPPING_PATH: ${{ runner.temp }}/mapping.json
          DRY_RUN: ${{ inputs.dry_run }}
        run: PYTHONPATH=backend python backend/pandapower_run_hourly.py run
      - if: always()
        run: rm -f "$RUNNER_TEMP/mapping.json"
```

Design points:

- **One hourly job, three small steps** (pre-flight without secrets, materialise the mapping, run). The pre-flight (`selftest`) imports pandapower, loads the committed network, checks its pinned sha256 and solves the base once; it fails fast and is given no secrets (the same reason `dlr_live.yml` has its model pre-flight).
- **Trigger and timing:** cron-job.org `workflow_dispatch`, aimed about HH:20. `dlr_live` writes the hour's `city_rating` row a few minutes after the hour, and `psse_results_v1.md` documents that a job started after about HH:30 without the current row finds a 90-minute-old one and goes all-static (`stale`). HH:20 leaves room for runner start-up and keeps `started_at` inside its slot hour.
- **Budget stack:** study budget (`study.max_runtime_seconds`, in the private mapping, set well under 20 minutes) < workflow `timeout-minutes` (20) < the 60-minute cadence, so a cut-off run never overlaps the next slot. The Actions `concurrency` group replaces the laptop's file lock (`lock.py`); no lock code runs on the runner.
- **Secrets (environment `production`, main-only):** `SUPABASE_PSSE_DB_URL` (the session-pooler URL of `dlr_psse_writer`: Actions runners are IPv4 and the direct host is not, and `launcher._db_url_problem` already requires a TLS sslmode for a non-local host), `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` (`ratings.fetch_latest_rating` refuses a secret or service-role key), and the mapping. Mapping as a secret: GitHub limits a secret to 48 KB; the code's own cap is 64 KB (`mapping.MAX_MAPPING_BYTES`); the real file is small, but store it base64 so multi-line JSON is masked as one token and no line is printed separately. Never `cat` it, never `set -x`.
- **Public-log hygiene (important):** `job._log_run` logs `error[:300]` at WARNING, and study failures name outages and buses ("outage 12-13-1: ..."). On the laptop that goes to a local file; on Actions it would reach a public console. `runner.py` must attach no handler to the `psse_job` loggers (or a filter that drops WARNING and above) and print only one identifier-free line (`run_id`, outcome, status, failed stage, exit code). The detail stays in `psse_run.error`, which is private. pandapower's own logger is silenced the same way.
- **Exit codes** reuse `job.EXIT_*`: 0 ok or fallback written or already recorded; 1 failed run recorded; 3 not recorded. A non-zero exit turns the workflow red and GitHub's failure email is the alert, as in `dlr_live.yml`.
- **Dependencies:** `requirements-pandapower.txt` pins `pandapower==3.5.6` (PyPI, released 2026-10-07, requires Python >= 3.10) with the same pandas, numpy, scipy and `psycopg[binary]` pins as `requirements.txt`. Skip numba and lightsim2grid: on a 39-bus net JIT start-up costs more than it saves, and lightsim2grid is only used when its conditions hold anyway.
- **Second workflow `pandapower_gap_check.yml`** (`workflow_dispatch`, same environment): `gaps --solver pandapower --since <start> --fail-on-gaps`. Its output is slot times, kinds and counts only (already identifier-free). This is the "results land every hour for a full day" gate.
- **Agreement:** local CLI first. An optional manual workflow may print PASS/FAIL and counts only.
- **Network data:** the IEEE 39-bus case is public (the existing job already runs on "the public 39-bus case"), so commit `backend/pandapower_job/data/ieee39_pandapower.json` and pin its sha256 in a test; the private part is the mapping (city branches, sink buses, per-city scaling targets), which stays a secret. If reconciliation shows the PSS/E copy cannot be matched with public data, the network becomes private too and needs gzip + base64 (a pandapower JSON of this size may exceed the 48 KB secret limit uncompressed).

## Data Flow

### Hourly run

```
cron-job.org -> workflow_dispatch -> runner
   ratings.fetch_latest_rating (REST, publishable key)  -> select_ratings -> Selection (static unless fresh and not provisional)
   study.make_study(api_factory=PandapowerApi):
      index_case: load master net, translate ids, check_mapping            (stage mapping / load_case on failure)
      per city (fresh deepcopy of master): scale_city_case -> apply_ratings -> solve_base -> save snapshot
         contingency.screen (deepcopy snapshot per outage) -> rows
         margin.city_margin (deepcopy snapshot per transfer step) -> margin row
         dispatch.build_dispatch_row -> dispatch row
      any city failed -> one combined_failure (no partial set)
   run_record.validate_results -> build_run_record(solver='pandapower') -> result_rows
   writer.write_run: ONE transaction (run row first, then dispatch, margin, contingency); on failure rollback + failed record (stage write)
   no record possible (database unreachable) -> exit 3 -> a gap the gap check shows
```

### Key data flows

1. **Rating to result:** `latest_rating` (REST) -> `ratings_used` (jsonb in `psse_run`) -> applied as `max_i_ka` on the mapped lines -> dispatch row; the same `ratings_used` is what the replay rebuilds a `Selection` from.
2. **Solver tag:** set once at run start (`RunContext.solver`), present on every row including failed ones, encoded in the run id prefix, enforced by the CHECK, read by the gap SQL, the view and the replay.
3. **Dashboard:** `psse_run` + `psse_dispatched_capacity` -> `latest_grid_study` (owner-rights view) -> REST with the dashboard's key.

## Architectural Patterns

### Pattern 1: Injected factory at the one construction point
**What:** `api_factory(backend, case_path)` defaulting to `PsseApi`. **When:** a collaborator is constructed in exactly one place and everything downstream is duck-typed. **Trade-offs:** one small additive edit to a frozen-ish module and no fork; the cost is that "same interface" is enforced by a parity test, not a type system (3.7 has no `Protocol`).

### Pattern 2: Master plus snapshots with deep copies
**What:** one immutable master, a saved base per city, a fresh deep copy per outage and per transfer step. **When:** a failed solve can leave the object in an unknown state. **Trade-offs:** costs a copy per solve; buys the contamination guarantee the PSS/E study already documents.

### Pattern 3: Solver as data, not as a code path
**What:** `solver` flows as a value through `RunContext` to rows, ids, views and gap queries. **When:** two engines produce rows with one shape. **Trade-offs:** every reader must filter by it (the gap SQL, the reading rule and the view are the three places that matter).

## Anti-Patterns

### Anti-Pattern 1: Letting the `solver` default stand in for tagging
**What people do:** rely on `default 'psse'` and forget to set the column in the new job. **Why it's wrong:** pandapower rows would be indistinguishable from the reference and the agreement check would compare a solver with itself. **Do this instead:** the run-id-prefix CHECK, plus a runner test that the record's `solver` is `pandapower`.

### Anti-Pattern 2: Editing the applied migration, the pinned v1 DDL region or the v1 doc tables
**What people do:** add `solver` to `20261109233541_psse_results.sql` or to `psse_results_v1.sql`. **Why it's wrong:** the file is applied live and sha-pinned, the region is pinned in the hand-off note, the doc tables are checked against the DDL. **Do this instead:** additive migration plus a v1.1 doc.

### Anti-Pattern 3: A security-invoker view over private tables
**What people do:** copy `latest_rating`'s pattern. **Why it's wrong:** the public roles have no access to the base tables, so it returns nothing. **Do this instead:** an owner-rights view with a deliberately narrow column list and its own exposure checks.

### Anti-Pattern 4: Reusing the laptop launcher on the runner
**What people do:** call `launcher.main` with a fake loader. **Why it's wrong:** it requires PSS/E config keys, bans environment settings, takes a file lock and logs error text (bus numbers) at WARNING. **Do this instead:** a small runner over the pure `psse_job` pieces with identifier-free output.

### Anti-Pattern 5: Putting detailed agreement output in an Actions log
**What people do:** print the comparison in CI. **Why it's wrong:** the repo is public. **Do this instead:** local run for detail, counts only in CI.

## Scaling Considerations

| Concern | Now (4 cities, 39 buses) | If the network or cadence grows |
|---------|--------------------------|----------------------------------|
| Solve count per run | thousands of small solves, deep-copy dominated; fits the budget (measure) | snapshot only mutable columns; `contingency.scope`/`hops` bound the screen |
| Row growth | one `psse_run` + 8 fixed + violation rows per run, 24 runs a day, never deleted | no retention rule exists and the writer has no DELETE: retention needs the owner's role (for example a scheduled job) and is a later decision (STATE.md blocker) |
| Actions minutes | one short job an hour, pip cache | keep pandapower out of `requirements.txt` so `dlr_live` is unaffected |

## Integration Points

### External services

| Service | Integration | Notes |
|---------|-------------|-------|
| Supabase Postgres | `writer.connect` session-pooler URL as `dlr_psse_writer` | runners are IPv4; TLS mode required for a non-local host; insert and select only |
| Supabase REST | `ratings.fetch_latest_rating`, publishable key | static fallback on any doubt, run still recorded |
| cron-job.org | `workflow_dispatch` | no GitHub `schedule` trigger (late runs) |
| pandapower 3.5.6 | `runpp`, `net.line`, `net.res_*`, `copy.deepcopy` | `LoadflowNotConverged` import path and `net._ppc["iterations"]` to confirm against the pinned version (MEDIUM) |

### Internal boundaries (file:function)

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `study.py:_open_case` -> `PandapowerApi` | injected `api_factory` | the only construction point |
| `PandapowerApi` -> `psse_api` | imports `PsseCallError`, `CaseProtected`, `BranchRow`, `BusRow`, `BranchFlow`, `SolveResult`, `CaseTotals`, `classify_solve` | `psse_api` itself is not modified |
| `job.py:run_once` -> `run_record.py:new_run_id/build_run_record` -> `writer.py:write_run` | `solver`, `solver_version` through `RunContext` and `PSSE_RUN_COLUMNS` | the INSERT SQL is generated from the tuple, so no SQL edit |
| `gaps.py:fetch_gaps` <- `psse_run_gaps.sql` | statement returns a leading `solver` column; Python filters | one place for gap logic |
| `latest_grid_study` -> dashboard | REST with the dashboard key | one-way column contract |
| `replay.py` -> database | read-only session as the writer role | no write path |

## Suggested Build Order (with dependencies)

```
A. Adapter + network  ----+
                          +--> C. Runner + Actions + soak ---+--> E. Dashboard view + docs
B. Schema + solver tag ---+                                   |
                          +--> D. Replay + agreement ---------+
```

1. **A. Network reconciliation and `PandapowerApi` (no database).** Convert and pin the 39-bus network with the PSS/E bus numbers and circuit ids; add the swing-machine column; implement `PandapowerApi`, the `api_factory` edit and the parity test; run `make_study` end to end against the committed placeholder mapping example (`docs/data-science/schema/psse_mapping_example.json`) in a dry run, so `validate_results` accepts the output. Prerequisite for everything; highest risk (data fidelity, parity knobs, island policy, deep-copy cost). Free early reconciliation against the recorded `line_voltage_kv`, `rate_before_mva`, `branches` belongs here.
2. **B. Schema and solver tag.** Migration, constraints, index, the five `psse_job` edits, gap SQL and `gaps.py`, v1.1 doc, test updates (the five listed in section 3), local-Postgres tests. Independent of A except that `run_once(solver=...)` is exercised with A's study. Must be applied to the live project by the owner before any pandapower write. Safe for the laptop job because the default tags its rows `psse` and it is paused.
3. **C. Runner, Actions workflow, secrets, soak.** Needs A and B. Dry-run dispatch first (study and validation, no write), then live; hourly for a full day; gap check `--solver pandapower`. Add the secrets (writer URL, ratings read, mapping) in the `production` environment.
4. **D. Replay and agreement.** Needs A (study) and B (solver column to select `psse` rows); can be built against local Postgres with synthetic recorded rows in parallel with C, then run on the real recorded rows. Iterating the network data and parity knobs until agreement is this phase's loop.
5. **E. Dashboard view and docs.** Needs B; ship after C's soak and D's pass so only verified figures are exposed. Migration, `verify_exposure.sql`/test updates, `latest_grid_study_contract.py`, `rest-api.md` section, and the DEF-01 "unblocked" edit on the software-dashboard branch.

**Done criterion mapping:** C's full-day gap-free soak plus D's pass is the milestone's "done".

## Open Questions and Gaps

1. **Whole-network comparison data:** the recorded rows cannot prove "all bus voltages within 0.01 pu" (section 5). Needs a decision and possibly a one-off PSS/E-side export. Highest-impact requirements question.
2. **Does the PSS/E 39-bus copy equal pandapower's `case39` (MATPOWER lineage)?** Line versus transformer classification, circuit ids, line ratings (the PSS/E side records `rate_before_mva`; pandapower's `case39` page does not state `max_i_ka`), generator Q limits, loads. The adapter's `branch_table` split depends on it; `check_mapping` rejects a mapped transformer.
3. **Loading-percent definition:** PSS/E `MAXPCTRATE` (current basis) versus pandapower `loading_percent` (larger-end current over `max_i_ka * df * parallel`). Likely consistent at nominal voltage, but a few percent of difference would eat the 2 percent tolerance. Verify on the first solved case.
4. **Swing machine saved dispatch** (section 1): the column and the source of its value.
5. **Island policy** (mirror PSS/E's ierr 3 as `non_convergence`): confirm against PSS/E-recorded `non_convergence` rows.
6. **`solver_version` column:** recommended, not required by the milestone; confirm with the owner.
7. **Deep-copy cost and `runpp` time per solve:** unmeasured; pandapower is not installed in the repo venv yet.
8. **Retention** of 24 run sets a day (STATE.md blocker): no rule and no delete privilege.
9. **Pause semantics for PSS/E gaps** and whether the staleness alarm should cover the pandapower feed.

## Sources

- Repository (read in full unless noted): `backend/psse_job/psse_api.py`, `study.py`, `job.py`, `run_record.py`, `contract.py`, `constants.py`, `writer.py`, `contingency.py`, `margin.py`, `violations.py`, `dispatch.py`, `mapping.py`, `settings.py`, `ratings.py`, `gaps.py`, `launcher.py`; `backend/psse_run_hourly.py`; `supabase/migrations/20261109233541_psse_results.sql`, `20261026195124_expose_latest_rating.sql`, `20261108120100_expose_day_ahead_forecast.sql`; `supabase/ops/verify_psse_results.sql`, `verify_exposure.sql` (header and checks); `docs/data-science/schema/psse_results_v1.md`, `psse_results_v1_checks.sql`, `psse_run_gaps.sql`; `.github/workflows/dlr_live.yml`; tests `psse_contract_test.py`, `psse_results_migration_test.py`, `psse_schema_doc_test.py`, `psse_run_record_test.py`, `psse_local_pg.py`, `psse_fake_psspy.py` (confidence HIGH).
- `.planning/workstreams/pandapower-solver/STATE.md`; `.planning/workstreams/pss-e-integration/HANDOFF.md` and `STATE.md` (public 39-bus case, writer password rotated, job paused); `DASHBOARD-REQUIREMENTS.md` ch. 10 (DEF-01) on the software-dashboard worktree (HIGH).
- [pandapower on PyPI (version 3.5.6, requires Python >= 3.10, dependency pins)](https://pypi.org/pypi/pandapower/json) (HIGH).
- [pandapower power flow options (algorithms, init, enforce_q_lims, numba, lightsim2grid conditions)](https://pandapower.readthedocs.io/en/latest/powerflow/ac.html) (HIGH).
- [pandapower line element (max_i_ka, df, parallel, res_line columns, loading_percent formula)](https://pandapower.readthedocs.io/en/latest/elements/line.html) (HIGH).
- [pandapower test cases (case39 data origin PYPOWER, transformers between same-voltage nodes)](https://pandapower.readthedocs.io/en/latest/networks/power_system_test_cases.html) (HIGH for what it states; it gives no `max_i_ka` values).
- [pandapower diagnostic tutorial (`LoadflowNotConverged` on non-convergence)](https://nbviewer.org/github/e2nIEE/pandapower/blob/develop/tutorials/diagnostic.ipynb) and [changelog (out-of-service results are NaN)](https://pandapower.readthedocs.io/en/latest/about/changelog.html) (MEDIUM; exception import path not confirmed).

---
*Architecture research for: v1.7 pandapower Solver (additive solver beside PSS/E)*
*Researched: 2026-11-16*
