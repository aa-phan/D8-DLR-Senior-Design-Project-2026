# Stack Research: v1.7 pandapower Solver

**Domain:** hourly per-city IEEE 39-bus grid study (load flow, N-1 line outages, voltage-margin transfer search, dispatched capacity) run by pandapower in GitHub Actions, written to the existing `psse_*` Supabase tables tagged by a `solver` column
**Researched:** 2026-11-16
**Overall confidence:** HIGH on versions, dependency fit, pandapower behaviour and GitHub/Supabase mechanics (all checked this session); MEDIUM on how closely pandapower will match the PSS/E copy of the case (only the agreement check can settle that)

Scope note: only what the NEW capability needs. The PSS/E job (`backend/psse_job/`), the writer role, and the existing pins are treated as given.

Confidence tags: HIGH = ran it here or read primary source this session; MEDIUM = official docs or one-source; UNVERIFIED = could not confirm.

## Headline recommendations

1. Add exactly one new runtime package: `pandapower==3.5.6` (released 2026-10-07; pure-Python wheel; Python >= 3.10, so Python 3.12 in CI is fine). Do **not** install any pandapower extra (`[converter]`, `[performance]`, `[all]`).
2. It resolves and runs cleanly against the repo's existing pins (pandas 2.3.3, numpy 2.4.3, scipy 1.17.1, psycopg 3.3.6): `pip install --dry-run` on a fresh Python 3.12 venv, real install, `pip check` clean, `runpp` converged on `case39()` (HIGH).
3. Do **not** add numba. Measured here on the 39-bus case: first solve 1.19 s with numba (JIT) vs 0.01 s without, then 9.8 ms vs 11.4 ms per solve. A fresh hourly process never earns the compile cost back. Pass `numba=False` to `runpp` to silence the import warning (HIGH).
4. Do **not** use `pandapower.contingency.run_contingency`. Write a hand loop. It returns only min/max aggregates across all outages and swallows non-convergence into a log line, so it cannot produce the per-outage violation rows (`contingency_id`, element, limit, observed, `non_convergence`) the `psse_contingency_result` table needs (HIGH, source read).
5. pandapower has **no** PSS/E importer, and neither built-in route (`case39()`, MATPOWER `from_mpc`) reproduces the PSS/E classification of the case. Build the network with `pp.create_*` calls from PSS/E-derived data, keeping PSS/E bus numbers as pandapower bus indices (HIGH, verified; details below).
6. Scheduling stays on the house pattern: dispatch-only workflow poked by cron-job.org, not GitHub `schedule:`. Public repo means hosted-runner minutes are free.
7. Dashboard view must be a **security-definer** view (the repo's existing `security_invoker = true` pattern cannot be reused) because the four tables stay private. Expect a Supabase linter ERROR (0010) that is accepted and documented.

## Recommended Stack

### Core Framework

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| pandapower | 3.5.6 (PyPI 2026-10-07) | AC Newton-Raphson load flow on the 39-bus network; branch loading, bus voltages | The one library the milestone is named for. Pure-Python wheel, BSD licence (METADATA classifier), `runpp` takes ~11 ms on the 39-bus case, so ~6 s for a whole four-city hourly study. Releases come every few weeks (3.5.2 to 3.5.6 between 2026-07-06 and 2026-10-07), so pin exactly. |
| Python | 3.12 (existing) | Runtime in CI | pandapower 3.5.6 needs >= 3.10. The repo, `shadow_collect.yml` and `dlr_live.yml` already use 3.12. The PSS/E 3.7-syntax rule (D-05) does NOT apply to the pandapower runner; it runs on CI's interpreter. |

### Database

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Supabase Postgres (existing) | n/a | Same four `psse_*` tables plus a `solver` column and one read-only view | Decision already made by the owner. |
| psycopg + psycopg-binary (existing pins) | 3.3.6 | Writer connection as `dlr_psse_writer` | Already pinned; reuse `psse_job/writer.py` as is (it is stdlib + psycopg, imports fine on 3.12). |

### Infrastructure

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| GitHub Actions, `ubuntu-latest`, `actions/setup-python@v5` with `cache: 'pip'` | existing house pattern | Hourly run | Same as `dlr_live.yml`. Hosted-runner minutes are free on a public repo (GitHub billing docs, HIGH; repo runbook section 12 records the repo went public 2026-10-24). |
| cron-job.org (existing account) | n/a | Hourly `workflow_dispatch` | GitHub's own `schedule:` trigger ran this repo's shadow job 3 to 8 hours late (comment in `shadow_collect.yml`); GitHub's docs confirm delays at high load, that the top of the hour is the worst time, and that queued jobs can be dropped. Use a minute that no other job uses (existing: 00 shadow, 05 live; laptop task at :15 per the PSS/E research), for example :20 or :25. Choose it so the `latest_rating` view already holds this hour's ratings from the :05 run. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| numpy | 2.4.3 (existing pin) | Arrays under pandapower | **Keep at 2.4.x.** pandapower 3.5.6 requires `numpy<2.5,>=1.26`, and numpy 2.5.5 is now the newest release. An unpinned bump breaks the install. |
| pandas | 2.3.3 (existing pin) | pandapower's table store | **Keep at 2.3.x.** pandapower requires `pandas~=2.3`; pandas 3.1.1 exists and is excluded. |
| scipy | 1.17.1 (existing pin) | Sparse solves | Satisfies `scipy>=1.15`. |
| pandera, pydantic, networkx, deepdiff, geojson, tqdm, colorama, typing_extensions, packaging | transitive (resolved: pandera 0.36.0, networkx 3.7, tqdm 4.70.1, colorama 0.4.6 pinned by pandapower) | pandapower's own dependencies | Not imported by us. They arrive automatically. Total solver-only install is 26 packages (listed in "Installation"). |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| pytest 9.0.3 (existing) | Unit tests of the builder, loop and mapping | A pandapower-free fake is not needed; `case39()` is a free, fast fixture (18 ms first solve). |
| `supabase/ops/verify_*.sql` pattern (existing) | A new `verify_psse_public_view.sql` | The existing `verify_psse_results.sql` asserts anon/authenticated hold nothing on the four tables; keep it passing and add a view check beside it. |

## Compatibility with the repo (verified)

Fresh Python 3.12.13 venv in a scratch directory, `pip install -r requirements.txt pandapower==3.5.6`:

- Resolves with every existing pin unchanged: pandas 2.3.3, numpy 2.4.3, scipy 1.17.1, scikit-learn 1.9.1, gridstatus 0.35.0, psycopg 3.3.6, matplotlib 3.10.8. `pip check`: no broken requirements. (HIGH)
- pandapower 3.5.6 declared requirements: `pandas~=2.3`, `numpy<2.5,>=1.26`, `scipy>=1.15`, `networkx~=3.6`, `packaging~=26.0`, `tqdm~=4.68`, `colorama==0.4.6`, `deepdiff~=9.1`, `geojson~=3.3`, `typing_extensions~=4.16`, `pandera~=0.32`. The repo's current `.venv` has tqdm 4.67.3 and no networkx/pandera/deepdiff, so `pip install pandapower==3.5.6` there will upgrade tqdm and add the rest. (HIGH)
- `import pandapower` takes about 1.8 s wall; negligible against an hourly run.
- Base install excludes numba, lightsim2grid, matpowercaseframes, pypowsybl and plotting. Keep it that way.

### Where to put the pin: a separate requirements file

`requirements.txt` calls itself the single source of truth, but `dlr_live.yml` and `shadow_collect.yml` install all of it. Adding pandapower there adds 15 or so packages (pandera pulls pydantic and typeguard) to the job that holds the ratings-writer secret and to the shadow job. Recommendation: a second file `requirements-solver.txt` for the new workflow only, with a header comment pointing at `requirements.txt` and a test that every shared pin (numpy, scipy, pandas, psycopg, psycopg-binary) is identical in both files, so the two never drift. Developers and the full test suite install both. If the owner prefers one file, adding `pandapower==3.5.6` to `requirements.txt` works (verified) and is the fallback. Either way keep `cache: 'pip'` with `cache-dependency-path` set to the file that the job installs.

## pandapower.networks.case39()

- Exists in 3.5.6 (`pandapower/networks/power_system_test_cases.py`). Its docstring says the data origin is PYPOWER, first published in Bills et al., "On-line stability analysis study", EEI RP90-1, 1970. The MATPOWER `case39.m` header says the same source plus the MATPOWER authors' modifications: generator buses renumbered, Pmin set to 0, Q limits added for buses 31 and 39, bus 39 data from Pai (1989), line limits from PSERC TC Calculator data, voltage limits 0.94 to 1.06, Pmax at bus 34 raised from 308 to 508 (assumed typo), power flow re-solved. (HIGH, both read this session)
- Shape in pandapower: 39 buses (all 345 kV, indexed 0 to 38, `name` 1 to 39), 35 lines, 11 transformers, 9 gens + 1 ext_grid (bus 31, vm 0.982), 21 loads, 60 Hz, 100 MVA base. Line limit `max_i_ka` is derived from the MATPOWER RATE_A (600 MVA at 345 kV gives 1.004 kA). (HIGH, ran it)
- **The built-in case does not match the PSS/E copy's branch classification.** The laptop record describes the PSS/E example as 34 lines and 12 transformers. MATPOWER has 12 branches with a non-zero tap ratio (2-30, 6-31, 10-32, 12-11, 12-13, 19-20, 19-33, 20-34, 22-35, 23-36, 25-37, 29-38). pandapower's converter treats ratio 0 **or 1** as a line, so 23-36 (ratio 1.0) becomes a line: 35 lines, 11 transformers. The N-1 screen outages lines only (`select_outages` skips transformers), so the screened set would differ by one branch. The same happens through `from_mpc` (it logs "11 branches which are considered as trafos - due to ratio unequal 0 or 1"). (HIGH for pandapower and MATPOWER side; the PSS/E side is MEDIUM, taken from the laptop record. Whether the PSS/E example's electrical data equals MATPOWER's is UNVERIFIED.)
- Both routes also lose PSS/E bus numbers (`from_mpc` leaves `name` empty; `case39()` has 1-based names but 0-based indices). The private mapping, contingency ids (`from-to-ckt`) and violations all use PSS/E bus numbers, so a renumbering layer would be a standing source of off-by-one bugs.
- Verdict: use `case39()` as the **bootstrap and test fixture** (public, BSD data, zero secrets, solves in milliseconds). It is not the production network if the agreement check shows a difference; the STATE.md concern ("matching the network data is likely the first real work") is correct.

## Getting PSS/E network data into pandapower

Findings (all HIGH unless noted):

| Route | Status | Verdict |
|-------|--------|---------|
| pandapower built-in PSS/E import | None. `pandapower/converter/` contains cim, jao, matpower, opendss, pandamodels, powerfactory, pypower, pypowsybl, ucte. No `psse`/`raw` anywhere. | Not available. |
| pandapower `from_mpc` / `from_ppc` (MATPOWER, PYPOWER) | Works (`.m` needs `matpowercaseframes` 2.1.1; `.mat` needs scipy). Loses bus numbers; ratio 1.0 branch becomes a line (above). | Only useful if the data were first converted to MATPOWER, which is lossy. Do not use as the production path. |
| MATPOWER `psse2mpc` | MATLAB/Octave code, not Python. Forum reports of encoding and revision-detection failures on v33 files; NESTA authors report converted cases that did not converge. | Reject. |
| `matpower-pip` | Wraps MATPOWER through Octave (oct2py). Heavy native dependency. | Reject for CI. |
| PYPOWER 5.1.21 | Pure Python, but has no PSS/E reader; it is the data origin of `case39`. | Not an importer. |
| PowerModels.jl | Parses PSS/E RAW v33 and can export MATPOWER. Needs Julia. | Offline cross-check only, never CI. |
| `pypowsybl` 1.16.1 + `pandapower.converter.from_pypowsybl` | PowSyBl reads PSS/E RAW **v33 and v35** and RAWX v35 (v36 not listed); drops constant-current/impedance load parts, reactive transformer control, impedance-correction tables. Native GraalVM library, large wheel; it is the pandapower `[converter]` extra. | Dev-machine cross-check only, if at all. Never in CI. |
| `grg-pssedata` 0.1.4 (LANL) | Pure-Python RAW read/write, v33. Last release 2020-12-15. | Candidate for a one-off conversion script; unmaintained and v33-only. Suitability for RAW from PSS/E 36.4 is UNVERIFIED. |
| ANDES 2.0.0 (Python >= 3.11) | Has a PSS/E RAW parser (v32/33 per the AMS docs). A full dynamic-simulation framework. | Too heavy for this need. |
| PSS/E `.sav` | Binary, proprietary, readable only by PSS/E. | Cannot be read outside PSS/E. |

**Recommendation: a project-owned builder, with a PSS/E-derived text file as the data source.**

- Source file: a RAW export of the case from PSS/E on the laptop (plain text), or a compact JSON the same person extracts. The RAW export function name and option layout are UNVERIFIED (forum posts show `rawd_2` with a 7-element options list and at least one "incorrect file type OPTIN" failure; PSS/E 36.4 may default to RAW revision 36). The laptop probe pattern the project already uses (SURFACE table, probe on the laptop) is the way to settle it.
- Parser: stdlib only, around 150 lines, reading just the sections the 39-bus study uses: case header (revision, system base MVA, base frequency), bus, load, fixed shunt, generator, non-transformer branch, two-winding transformer. **Fail closed** on anything else (switched shunts, three-winding transformers, non-default CW/CZ/CM codes, HVDC, multi-section lines): raise, so a case the builder does not understand never produces a "result". RAW revision 33 and later carry 12 rating fields on branches; earlier revisions carry 3.
- Builder: `pp.create_bus(net, vn_kv=..., index=<PSS/E bus number>)`, `create_line_from_parameters` (length 1 km; per-unit R, X, B converted with Zbase = kV squared / MVA, c_nf from B at 60 Hz), `create_transformer_from_parameters`, `create_load`, `create_gen`, `create_ext_grid` for the swing bus. Set `net.line.name` and `net.trafo.name` to `"<from>-<to>-<ckt>"` so branch lookups match `BranchRow.key` and the private mapping verbatim. Keep `max_i_ka = rating_MVA / (sqrt(3) * kV)`, which is also how the job converts amps to MVA (`applied_mva = sqrt(3) * kV * I / 1000`).
- Where the converted data lives (owner decision, flagged for requirements): a PSS/E example case is vendor-supplied, so its licence terms are UNVERIFIED and `*.sav`/`*.raw` are already git-ignored. The converted per-unit tables are small (estimated 15 to 25 KB as compact JSON, UNVERIFIED size), under GitHub's 48 KB secret limit, so they can ride in a secret like the mapping if the owner does not want them in the repo.
- Phase risk: transformer data conversion is the part most likely to need its own research (tap representation, magnetising branch location, phase shift). Scope it to the 39-bus case's actual CW/CZ/CM values and assert them.

## The contingency loop

What `pandapower.contingency` offers in 3.5.6 (source read):

- `run_contingency(net, nminus1_cases, ...)`: loops outages, calls `runpp`, keeps **running min/max** of bus `vm_pu` and element `loading_percent`, a boolean `causes_overloading` per outage and the worst `cause_element`. A failed solve is logged (`logger.error`) and skipped unless `raise_errors=True`; the N-1 results do not say which outage did not converge. Limits come from `max_loading_percent` (or `max_loading_percent_nminus1`), and voltage limits are not evaluated at all.
- `run_contingency_ls2g`: needs lightsim2grid, contiguous bus index from 0, ignores isolated-grid handling differences, flows valid at the from-end only. The pandapower `[performance]` extra pins `lightsim2grid~=0.13.0`; PyPI now has 1.3.1, so compatibility is UNVERIFIED.
- `contingency_parallel`: multiprocessing helper, not needed at 46 branches.

Why the hand loop is required: the schema stores one row per (outage, violated element) with the limit, observed value, exceeded-by and unit, plus a `non_convergence` row per failed outage. That cannot be recovered from min/max aggregates. The cost is small: 46 outages ran in 0.59 s total on the 39-bus case (HIGH, measured), so no speed argument for a library tool either.

Loop design points that follow from the code and from `psse_job/contingency.py`:

- Mirror the PSS/E screen: lines only, one at a time; fresh state before every outage (restore `in_service` in a `finally`, or `copy.deepcopy(net)` per outage; the net is tiny); catch `pandapower.LoadflowNotConverged` and record a `non_convergence` row; continue to the next outage.
- **pandapower silently de-energises islands.** With `check_connectivity=True` (default) an outage that islands buses still returns `converged=True` and gives NaN `vm_pu` on the dead buses. Measured on the public case: tripping the transformer at the swing bus left 38 buses NaN. PSS/E would report an island without a swing bus (`fnsl` ierr 3, which the job records as `non_convergence`). The loop must treat any NaN in `res_bus.vm_pu` as a collapsed case, the same rule `_collapsed` already applies to PSS/E (NaN counts as collapsed). Lines only are outaged, which reduces but does not remove the exposure (two lines were seen leaving 1 to 4 NaN buses).
- Re-use the pure evaluation in `psse_job/violations.py` (`thermal_violations`, `voltage_violations`, `non_convergence_row`): they take `BranchFlow` / `BusRow` named tuples, so a pandapower reader only has to produce those.

## Load-flow settings to fix explicitly

| `runpp` setting | Recommendation | Why |
|-----------------|----------------|-----|
| `numba=False` | always | No benefit per process; silences the warning |
| `algorithm="nr"` | default | Matches PSS/E `fnsl` (full Newton) |
| `calculate_voltage_angles=True` | set | Needed once any transformer carries a phase shift; harmless otherwise |
| `enforce_q_lims` | decide by PSS/E's setting | PSS/E default solution options apply generator var limits unless the case turns them off (UNVERIFIED for 36.4 `fnsl()` with no argument). pandapower defaults to off. On the public case both settings converged to the same minimum voltage. Make it a settings value, compare during the agreement check. |
| `tolerance_mva` | default (1e-8) | Tighter than PSS/E's usual 0.1 MVA; differences land well inside the 0.01 pu / 2% agreement bands |
| `init` | default `"auto"` | Fine for a converging 39-bus case; restart from base state per outage rather than chaining solutions |
| `trafo_model` | leave `"t"` until agreement says otherwise | A transformer-model difference is a known source of small bus-voltage offsets |

Per-city scaling maps to the `scaling` columns on `net.load` and `net.gen` (constant power factor, same as the `scal_2` call). The slack (ext_grid) absorbs mismatch, as the PSS/E swing does.

## Integration with `psse_job` (flag for the architecture decision)

`study.make_study(psspy_module, case_path, mapping)` takes an **injected** psspy-like module, and `psse_api.SURFACE` limits what that module must provide to about 20 functions. Two integration shapes follow:

1. **Shim psspy backed by pandapower.** Implement those ~20 functions (`case`, `fnsl`, `solved`, `abrn*`, `abus*`, `brndat`, `branch_chng_3`, `bsys`, `scal_2`, `save`, ...) over a pandapower net. The whole job (rating selection, scaling, N-1, margin search, dispatch, validation, writer) then runs unchanged, so "same study" holds by construction and the agreement check measures only solver differences. `backend/tests/psse_fake_psspy.py` (543 lines) already emulates this surface, including the `scal_2` layout and `branch_chng_3` sentinels, so it is a template. Cost: the shim must reproduce PSS/E quirks (sentinels, subsystem ids, the totals-read-must-be-closed rule).
2. **A second adapter with the same method surface as `PsseApi`** (`load_case`, `solve`, `branch_table`, `bus_table`, `branch_loading`, `set_rate`, `set_status`, `scale_case`, `read_totals`, `define_subsystem`, `scale_load`, `save_case`) returning the same named tuples. `contingency.py`, `margin.py`, `dispatch.py` use only that surface through `base.api`; `study.py` constructs `PsseApi` itself, so it needs a small seam.

Option 1 gives the strongest equivalence evidence and the least duplicated logic; option 2 is cleaner code. Either way the reusable pieces, which must not be rewritten, are `mapping.parse_mapping`, `settings`, `ratings` (reads the `latest_rating` view), `run_record` validation, `contract`, `writer` and `redaction`. Two schema facts matter for the migration:

- `psse_run.run_id` has a check `^psse-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$`. A pandapower run either keeps that prefix or the new migration alters the check; applied migrations are never edited, so this is an additive `alter table ... drop constraint ... add constraint`.
- The role `dlr_psse_writer` holds INSERT and SELECT only. Adding `solver text not null default 'psse'` to the four tables tags the existing 19 rows and needs no new grant.

## GitHub Actions specifics

| Topic | Finding | Source / confidence |
|-------|---------|---------------------|
| Trigger | `workflow_dispatch` only, called by cron-job.org with a token that has Actions write. Add a second cron-job.org entry; do not add `schedule:`. | House pattern in `dlr_live.yml` and runbook; GitHub docs on delay and dropped runs. HIGH |
| `schedule:` caveats (reasons not to use it) | Minimum 5 min; delays at high load, worst at the top of the hour; queued runs can be dropped; scheduled workflows auto-disable after 60 days without repository activity; run only from the default branch. | GitHub docs. HIGH. This repo measured 3 to 8 h lateness. |
| Secrets needed | `SUPABASE_PSSE_DB_URL` (the `dlr_psse_writer` connection string, session pooler, same env name `constants.ENV_PSSE_DB_URL` the job already reads), the private mapping JSON (new secret, for example `PSSE_MAPPING_JSON`), `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` (the ratings read goes through the `latest_rating` view; the publishable key is designed to be public, but keep the names `constants.ENV_SUPABASE_URL` / `ENV_PUBLISHABLE_KEY`). If the converted network data is kept private, one more secret for it. | `constants.py`; Supabase docs. HIGH |
| Secret size | 48 KB per secret; larger needs gpg-encrypt-and-commit or base64. The per-city mapping is a few KB. | GitHub docs. HIGH |
| Secret scoping | Put them in the existing `production` environment (main-only deployment-branch rule) and keep the `if: github.ref == 'refs/heads/main'` guard exactly as `dlr_live.yml` does. Secrets are not passed to fork PR runs. | `dlr_live.yml`; GitHub docs. HIGH |
| Writing the mapping | Pass the secret through `env:`, then `umask 077` and `printf '%s' "$VAR" > "$RUNNER_TEMP/mapping.json"`; hand the path to the job. Store it as **minified single-line JSON** (GitHub masks per line; the docs do not describe structured-data masking, so do not rely on masking). Never `echo` it. The job already records `mapping_sha256`. | GitHub docs (masking caveat UNVERIFIED for multi-line JSON). MEDIUM |
| Logs are public | The repository is public, so Actions logs are world-readable. Do not print result values, the mapping, bus ids tied to cities or the DB host. Reuse `psse_job/redaction.py`. | HIGH (follows from public repo; this repo's rule against credentials/hosts in public files) |
| Concurrency | `concurrency: group: pandapower-solver, cancel-in-progress: false`, as the other workflows. | House pattern. HIGH |
| Timeout | A healthy run is seconds of solver time plus 1 to 2 min of install and checkout (pip cache on). Use `timeout-minutes: 15`, below the 60-minute cadence so a cut-off never overlaps the next slot. | Measured solver cost, estimate for install. MEDIUM |
| Minutes | Free on public repos for standard hosted runners. If the repo ever goes private: Free plan includes USD 12/month of compute, roughly 2,000 Linux 2-core minutes (the roughly-2,000 figure is GitHub's rate arithmetic, not a stated quota); this job adds about 24 runs a day on top of the live job (24/day) and shadow (4/day), so revisit runbook section 12. | GitHub billing docs. HIGH |
| Dependency cache | `setup-python` with `cache: 'pip'` and `cache-dependency-path: requirements-solver.txt`. | House pattern. HIGH |

## Supabase: a view the dashboard key can read, over private tables

Facts (Supabase docs, HIGH; existing migrations, HIGH):

- The publishable key (`sb_publishable_...`) maps to the `anon` role (to `authenticated` once a user signs in); the secret key maps to `service_role`, which bypasses RLS.
- A Postgres view is by default **security definer** in effect: created and owned by `postgres`, it reads its tables with the owner's rights, so it **bypasses RLS** for every caller. `security_invoker = true` (Postgres 15+) makes it read the tables as the caller instead, so RLS and the caller's table privileges decide.
- This repo's two existing public views (`latest_rating`, `day_ahead_upcoming`/`day_ahead_status`) use `security_invoker = true` and give anon SELECT on the underlying table plus a read policy. **That pattern cannot be reused here**: with the milestone decision ("the four tables stay private"), anon has no privilege and no policy on `psse_*`, so an invoker view would return "permission denied" to the dashboard.

Recommended migration shape (one additive migration, owner pushes it):

1. Add `solver text not null default 'psse'` to the four tables (with a `check (solver in ('psse','pandapower'))`), tagging the 19 existing rows.
2. `create or replace view public.psse_latest_capacity with (security_invoker = false) as select distinct on (city) ... order by city, <newest first>`, with only the columns the decision lists (city, `dispatched_mva`/MW, `limiting_factor`, `solver`, study time) and no `details` jsonb, no `run_id`. Decide in requirements whether "newest per city" means newest across solvers (suggested: slot time first, then prefer `pandapower` as the always-on source on a tie).
3. `revoke all on public.psse_latest_capacity from public, anon, authenticated; grant select on public.psse_latest_capacity to anon, authenticated;` The four tables get no new grant; `supabase/ops/verify_psse_results.sql` must stay green (it checks anon/authenticated hold nothing on them).
4. A comment on the view stating why it is a definer view, and an ops verify query that the view exists, is selectable by anon, and exposes only the whitelisted columns.

Caveat to record rather than fight: Supabase's database linter 0010 `security_definer_view` is level ERROR for any definer view in `public`, because `public` is exposed through the API. The lint's only remedy is `security_invoker`, which does not fit this requirement, and there is no documented suppression. This is the intended exposure: the view's column list is the whole contract. Alternatives that avoid the lint were considered and are weaker: a `SECURITY DEFINER` function behind `/rpc` (trips the separate "anon-executable security definer function" advisories and is no easier to reason about), or a small separate public snapshot table written by the job in the same transaction (a fifth table, more moving parts). Neither is recommended.

PostgREST picks up the new view after the DDL (Supabase reloads the schema cache on DDL events; the earlier `expose_*` migrations relied on this). UNVERIFIED in this session; the verify query hitting the REST endpoint with the publishable key once after the push settles it.

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Load-flow library | pandapower 3.5.6 | PYPOWER 5.1.21, lightsim2grid 1.3.1 | The milestone names pandapower. PYPOWER is the stagnant ancestor with no element model; lightsim2grid is a faster solver binding for training RL agents, a native build the 11 ms solve does not need. |
| Contingency | Hand loop over `runpp` | `pandapower.contingency.run_contingency` / `_ls2g` | Aggregates only; no per-outage rows; non-convergence swallowed (see above). |
| Speed-up | None | numba 0.68.1 | JIT compile 1.2 s per process beats the gain (9.8 vs 11.4 ms per solve). Compatible with numpy 2.4.3 (`numpy<2.6`), but not worth a dependency. |
| Network source | Project builder over PSS/E-derived text | `case39()`; `from_mpc`; pypowsybl; psse2mpc; PowerModels.jl | See the routes table: wrong classification and lost bus numbers, or native/Julia/MATLAB dependencies. |
| Requirements file | `requirements-solver.txt` | Add to `requirements.txt` | Keeps pandapower and its 15 transitive packages out of the jobs that do not need them; the shared pins are test-enforced identical. Fallback if the owner wants one file. |
| Scheduling | cron-job.org dispatch | GitHub `schedule:` | 3 to 8 h late in this repo; may drop runs. |
| Dashboard view | Definer view with an explicit column list | `security_invoker` view; grant on tables | Invoker view needs table access for anon; contradicts "tables stay private". |

## What NOT to Add

- numba, lightsim2grid, matpowercaseframes, pypowsybl, matpower-pip, oct2py, juliacall: none is needed on the hourly path (reasons above).
- pandapower extras (`[all]`, `[converter]`, `[performance]`, `[pandamodels]`): `[converter]` drags in pypowsybl.
- An ORM or a second DB driver: psycopg 3.3.6 and `psse_job/writer.py` already do the all-or-nothing write.
- A new writer role or a new set of tables: decided; reuse `dlr_psse_writer` and the four tables.
- pandas 3.x, numpy 2.5.x bumps: both fall outside pandapower 3.5.6's ranges. Add a comment next to the pins so a routine "upgrade everything" does not break the solver job.
- GitHub `schedule:` trigger.

## Installation

```bash
# requirements-solver.txt  (new file; shared pins must equal requirements.txt)
pandapower==3.5.6
numpy==2.4.3
scipy==1.17.1
pandas==2.3.3
psycopg==3.3.6
psycopg-binary==3.3.6

# In CI and locally
python -m pip install -r requirements-solver.txt
python -m pip check
```

Resolved solver-only install (fresh Python 3.12, dry-run then real install, 26 packages): annotated-types 0.8.0, cachebox 5.2.3, colorama 0.4.6, deepdiff 9.1.0, geojson 3.3.0, mypy_extensions 1.2.0, networkx 3.7, numpy 2.4.3, orderly-set 5.5.0, packaging 26.3, pandapower 3.5.6, pandas 2.3.3, pandera 0.36.0, psycopg 3.3.6, psycopg-binary 3.3.6, pydantic 2.14.3, pydantic_core 2.50.4, python-dateutil 4.0.0, pytz 2026.6, scipy 1.17.1, tqdm 4.70.1, typeguard 4.6.0, typing-inspect 0.9.0, typing-inspection 0.4.5, typing_extensions 4.16.0, tzdata 2026.6. The transitive versions will drift with time; if exact reproducibility of the solver job matters (DS-NF2), freeze this resolved set into the file as a lock section.

## Pitfalls surfaced by stack research (for PITFALLS.md and phase planning)

1. **Network mismatch is the first real work.** pandapower `case39()` has 35 lines and 11 transformers; the PSS/E case has 34 and 12. The outage set and monitored-element set differ unless the builder is fed PSS/E data.
2. **Silent islands.** pandapower returns converged with NaN buses where PSS/E fails. Without an explicit NaN rule the agreement check will disagree on exactly the hardest outages.
3. **Agreement fields vs stored fields.** The agreement criteria (bus voltages within 0.01 pu, flows within 2%) can only be checked where the tables hold values: `psse_contingency_result` stores violations only, and `psse_voltage_margin` keeps `min_voltage_pu` and `critical_bus` per city. A replay that needs full bus-voltage or flow vectors needs them recorded or recomputed from a saved case; scope this in requirements.
4. **Run-id check** (`psse-` prefix) and the pinned sha256 of the applied migration: ship an additive migration, never edit `20261109233541_psse_results.sql`.
5. **Definer view lint ERROR** is expected; document it so a later "fix all advisor errors" pass does not convert the view to invoker and silently break the dashboard.
6. **Public logs.** Hourly runs in a public repo write to public logs; print counts and outcomes only.
7. **Dependency ceilings.** pandas `~=2.3` and numpy `<2.5` are hard ceilings in pandapower 3.5.6; a newer pandapower may move them, so re-resolve on every pandapower bump.
8. **Retention.** 24 permanent row sets per day with INSERT-only role and no retention rule (already in STATE.md); the solver job adds a second writer to the same tables, which doubles growth if both solvers run hourly.

## Unverified items (carry into phase research)

- Exact PSS/E 36.4 call and options to export a RAW file, and which RAW revision it writes. (UNVERIFIED)
- Whether the PSS/E example's electrical data equals MATPOWER `case39`. (UNVERIFIED; the line/transformer counts are consistent with MATPOWER's 12 ratio-bearing branches.)
- PSS/E `fnsl()` default handling of generator var limits, tap adjustment and area interchange on 36.4. (UNVERIFIED)
- `grg-pssedata` behaviour on RAW written by PSS/E 36.4. (UNVERIFIED)
- lightsim2grid 1.3.1 compatibility with pandapower 3.5.6 (not needed). (UNVERIFIED)
- PostgREST schema-cache refresh after the new view. (UNVERIFIED this session)
- Whether GitHub masks a multi-line JSON secret as one value. (UNVERIFIED; use single-line JSON and do not log it.)

## Sources

- PyPI JSON API, checked 2026-11-16: pandapower 3.5.6 (requires_dist, `requires_python >=3.10`, wheel `py3-none-any`, release dates); numba 0.68.1; lightsim2grid 1.3.1; pandas 3.1.1; numpy 2.5.5; scipy 1.18.1; matpowercaseframes 2.1.1; PYPOWER 5.1.21; grg-pssedata 0.1.4; andes 2.0.0; pypowsybl 1.16.1. (HIGH)
- Local experiments in a scratch Python 3.12.13 venv: dependency resolution against `requirements.txt`, `pip check`, `case39()` shape, `runpp` timing with and without numba, 46-outage loop, island behaviour, `from_mpc` classification. (HIGH)
- pandapower 3.5.6 source (installed): `networks/power_system_test_cases.py` (case39 docstring), `contingency/contingency.py`, `converter/` tree, `from_mpc`/`from_ppc` docstrings. (HIGH)
- MATPOWER `data/case39.m` header and branch table: https://raw.githubusercontent.com/MATPOWER/matpower/master/data/case39.m (HIGH)
- PowSyBl PSS/E import: https://powsybl.readthedocs.io/projects/powsybl-core/en/latest/grid_exchange_formats/psse/import.html (MEDIUM)
- GitHub docs: events that trigger workflows (schedule delays, 60-day disable): https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows ; Actions billing: https://docs.github.com/en/billing/concepts/product-billing/github-actions ; secrets: https://docs.github.com/en/actions/how-tos/security-for-github-actions/security-guides/using-secrets-in-github-actions (HIGH)
- Supabase docs: Row Level Security and views: https://supabase.com/docs/guides/database/postgres/row-level-security ; linter 0010: https://supabase.com/docs/guides/database/database-linter?lint=0010_security_definer_view ; API keys: https://supabase.com/docs/guides/api/api-keys (HIGH)
- PSS/E forum threads on RAW conversion and `rawd_2` (LOW, community; used only to flag the export call as UNVERIFIED): psspy.org questions 8493, 8220, 10100, 3777.
- Repo files read: `.planning/PROJECT.md`, pandapower-solver `STATE.md`, `requirements.txt`, `.github/workflows/shadow_collect.yml`, `dlr_live.yml`, `backend/psse_job/` (`psse_api.py`, `contingency.py`, `violations.py`, `study.py`, `constants.py`), `supabase/migrations/20261109233541_psse_results.sql`, `20261026195124_expose_latest_rating.sql`, `docs/data-science/decisions/dlr_live_runbook.md`, pss-e-integration laptop record.
