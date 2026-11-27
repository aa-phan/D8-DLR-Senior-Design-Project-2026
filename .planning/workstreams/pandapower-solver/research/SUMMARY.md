# Project Research Summary

**Project:** v1.7 pandapower Solver (workstream pandapower-solver)
**Domain:** a second, open-source power-flow solver (pandapower) running the existing hourly per-city IEEE 39-bus grid study in GitHub Actions, writing to the existing `psse_*` Supabase tables tagged by a `solver` column, with an agreement check against recorded PSS/E runs
**Researched:** 2026-11-16
**Confidence:** MEDIUM overall. HIGH on stack, platform mechanics and reuse of the job code. LOW to MEDIUM on whether pandapower will match the PSS/E copy of the case (never inspected; stored rows are sparse).

## Executive Summary

This is an additive solver, not a rewrite. The study code (`study`, `contingency`, `margin`, `violations`, `dispatch`, `run_record`, `writer`, `ratings`, `mapping`, `settings`) is solver-neutral and touches the solver only through about 14 `PsseApi` methods plus named-tuple value types. Recommended build: a new package `backend/pandapower_job/` with a duck-typed `PandapowerApi`, one additive `api_factory` seam in `study.py`, a default-preserving `solver`/`solver_version` thread through five `psse_job` files, one additive migration, and a dispatch-only workflow poked by cron-job.org. Add exactly one runtime package, `pandapower==3.5.6`, which resolves cleanly against the existing pins (Python 3.12, pandas 2.3.3, numpy 2.4.3, scipy 1.17.1). No numba, no `run_contingency`, no extras. A full per-city study is seconds of solver time (about 11 ms per 39-bus solve).

The real risk is data and definition parity. pandapower has no PSS/E importer, and neither `case39()` nor `from_mpc` reproduces the PSS/E branch classification (35 lines and 11 transformers vs 34 and 12 on the laptop; bus numbers lost). Three pandapower behaviours silently diverge and must be coded around: an islanding outage returns "converged" with NaN voltages (PSS/E gives `fnsl` ierr 3, stored as `non_convergence`); a failed solve leaves stale `res_*` tables; `enforce_q_lims` defaults off while PSS/E's setting is unrecorded (about 5e-4 pu effect in the base case, but about 0.1 pu on minimum voltage and about 12% on a voltage-bound transfer in a stressed scaled case, so a base-case check cannot detect a wrong choice).

**Cross-cutting finding: the stored PSS/E rows hold only violations, per-city margin figures (`min_voltage_pu`, `critical_bus`) and dispatch rows, not full bus-voltage or flow vectors.** The owner's "bus voltages within 0.01 pu, flows within 2%" therefore cannot be proven from the database. Either change the scope to "agreement on stored quantities" (violation set per outage including `non_convergence` and `n_contingencies`, observed values on violation rows, margin and dispatch figures), or add a one-off private PSS/E-side reference export of solved base (ideally per-outage) bus and branch tables. Recommendation: take the export in the same PSS/E-machine session as the network export, use it as the Phase 1 base-case gate, use the stored-row replay as Phase 4, and state in requirements which criterion is claimed.

## Key Findings

### Recommended Stack

- `pandapower==3.5.6` (Python >= 3.10; ceilings `pandas~=2.3`, `numpy<2.5`, so keep pandas 2.3.x and numpy 2.4.x and comment the pins).
- Python 3.12 on `ubuntu-latest`, `actions/setup-python@v5` with `cache: 'pip'`; free hosted minutes on a public repo.
- Hand-written contingency loop over `runpp` (library `run_contingency` returns only aggregates and swallows non-convergence).
- Fixed `runpp` settings: `numba=False`, `algorithm="nr"`, `calculate_voltage_angles=True`, `max_iteration=30`, `distributed_slack=False`, `enforce_q_lims` a measured settings value, `trafo_model="t"` until agreement says otherwise.
- Reuse `psycopg` 3.3.6 and `psse_job/writer.py` as role `dlr_psse_writer`.
- cron-job.org `workflow_dispatch` (GitHub `schedule:` ran 3 to 8 h late in this repo), own concurrency group, timeout below cadence, `production` environment, main-only guard.
- Network: project builder over PSS/E-derived text, PSS/E bus numbers kept as pandapower bus indices, `line.name`/`trafo.name` = `"<from>-<to>-<ckt>"`; `case39()` is only a fixture.
- Separate requirements file with the shared pins test-enforced equal to `requirements.txt`.
- Dashboard view must be security-definer (the `security_invoker` pattern cannot read private tables); the Supabase linter 0010 ERROR is accepted and documented.

### Expected Features

**Must have:** network parity with parity report; `PandapowerApi` plus factory seam; rating write as `max_i_ka = amps_per_circuit/1000`, current-basis loading only (fail loudly on `mva` basis and `voltage.source = case`); per-city scaling with read-back and bounds; strict converged definition (no exception, no NaN, no bus under 0.5 pu); island/NaN handling that reproduces `non_convergence`; fresh deepcopy per outage; N-1 and margin through the existing pure code; Q-limit setting decided from a PSS/E measurement with a calibration flag; replay harness and agreement report; `solver` migration and writer tag; latest-per-city view; hourly job with secrets and a full-day soak; DEF-01 doc update.

**Should have:** one-off full-state reference dump; borderline classification; max-deviation printed even on pass; retention rule for 24 row sets a day.

**Defer (v2+):** transformer/generator/multi-element outages in both solvers; scheduled re-agreement once PSS/E runs resume; PSS/E PV/QV.

**Anti-features:** distributed slack, native pandapower TDPF, OPF/DC flow, fitting reactances to force agreement, a fake `psspy`, committing the network, mapping or live numbers.

### Architecture Approach

`pandapower_job` (3.12) depends one way on `psse_job` (stdlib-only, 3.7 syntax). `PandapowerApi` mirrors the 14 `PsseApi` methods, value types and `PsseCallError`; a parity test pins names and signatures. Additive `psse_job` edits: `api_factory` in `study.py`; `solver`/`solver_version` in `contract`, `constants`, `run_record`, `job`; per-solver gaps in `gaps.py` and `psse_run_gaps.sql`. Additive migration (the applied v1 migration is sha-pinned): `solver` default `'psse'` kept permanently, `solver_version`, run-id pattern `^(psse|pp)-...` with a CHECK tying prefix to solver, `(solver, slot_time desc)` index; child tables inherit via `run_id`.

**Major components:**
1. `PandapowerApi` + `network.py`: master net plus snapshots, deepcopy per outage and step, island/NaN policy, swing-machine saved dispatch as a custom column so generation totals match `scal_2`.
2. `runner.py` / entry script: identifier-free output, reuses `job.EXIT_*`, does not reuse the laptop launcher.
3. `replay.py`: read-only; detail stays local; CI prints counts and PASS/FAIL.
4. Migration plus `latest_grid_study` definer view with a whitelisted narrow column list (no `details`, `run_id`, hashes, `critical_bus`).
5. Hourly, gap-check and optional agreement workflows.

### Critical Pitfalls

1. **Data parity:** MATPOWER `case39` is a modified copy; gate on a parity report and a full-vector base-case match.
2. **False agreement:** replay with stored ratings, filter by `mapping_sha256` and `job_version` (the 19 runs span the 2026-11-11 per-city scaling change), compare `non_convergence` sets and `n_contingencies`, use an epsilon band, report the non-empty comparison count (empty-equals-empty is vacuous), include a deliberate-failure test.
3. **Silent islands and stale results:** any NaN on an in-service bus becomes `non_convergence`; deepcopy before every solve; never read results after a failure.
4. **Rating units and loading basis:** per-conductor vs per-circuit vs MVA vs kA (2x, 0.95x, about 600x errors); an MVA-basis percent differs from `loading_percent` by up to about 3 points on the public case, more than the 2% tolerance. Current basis only.
5. **Permanent rows, migration, leakage:** the writer cannot delete, so no live writes before parity and a first agreement result; solver tag enforced by CHECK; public logs mean counts and codes only; ignore patterns before any real data is touched.

## Where the Four Files Disagree, and the Resolution

| Topic | Positions | Resolution |
|---|---|---|
| Integration shape | STACK offers a pandapower-backed `psspy` shim or an adapter, leaning shim. ARCHITECTURE and FEATURES recommend a duck-typed `PandapowerApi`; ARCHITECTURE rejects the shim (it must reproduce the `scal_2` state machine and sentinels). | **`PandapowerApi` + `api_factory`.** Sameness comes from reusing `study`/`contingency`/`margin` unchanged plus a signature-parity test. Use `psse_fake_psspy.py` only as a `scal_2` layout reference. |
| Network-data route | STACK: RAW export + stdlib fail-closed parser + builder; rejects `psse2mpc`, `pypowsybl`, `matpower-pip`. FEATURES: `case39()` if proven equal, else table export, or RAW to `psse2mpc` to `from_mpc`. PITFALLS: build from a PSS/E export, never MATPOWER. ARCHITECTURE: commit a public sha-pinned JSON, fall back to private. | **One route: RAW-class export from the PSS/E machine, stdlib fail-closed parser, project builder.** Existing bulk reads do not cover machines, loads and shunts. Reject `psse2mpc` and `from_mpc` (lossy; they reclassify the ratio-1.0 branch). `case39()` is a fixture only. Committing the JSON is allowed only if parity proves the data is the public case and the vendor licence permits; otherwise a private secret or local file. Decide at the end of Phase 1. |
| Requirements file | `requirements-solver.txt` (STACK) vs `requirements-pandapower.txt` (ARCHITECTURE). | **`requirements-pandapower.txt`**, matching `pandapower_job`. Separate file; shared pins test-enforced equal. |
| Dispatch minute | STACK :20 or :25; ARCHITECTURE about :20; PITFALLS :15 to :25 after `dlr_live` finishes; existing minutes :00 shadow, :05 live, :15 laptop. | **:20 UTC.** After the :05 live run so `latest_rating` is current, clear of :15, 10 minutes of jitter room. Verify the cron-job.org time zone (an existing entry was once found on US Central). |
| Warm start | FEATURES: `init="results"` on a deepcopy; ARCHITECTURE: never; PITFALLS: only inside the margin walk. | Default start for base, outages and cities; warm start only inside the margin walk and only if replay shows it agrees better. |
| Version tested | STACK verified 3.5.6; FEATURES and PITFALLS experimented on 3.2.2. | Re-verify island/NaN, stale results, `loading_percent` and `enforce_q_lims` on 3.5.6 in Phase 2. |
| Live-write timing | ARCHITECTURE runs the soak parallel to agreement; PITFALLS says rows are permanent. | Dry run first; live writes only after parity passes and a first agreement result exists. |
| Minor | `solver_version`, run-id prefix, child-table `solver`, view name. | Add `solver_version`; prefix `pp-` with a prefix-to-solver CHECK; no `solver` on child tables; view `latest_grid_study` (newest complete run per solver, up to 8 rows; the dashboard filters `solver = 'pandapower'`). |

## Items That Need a Session on a PSS/E Machine

Schedule as one early task; all output private.

1. Network export: the exact 36.4 export call and options, the RAW revision written, full case data (buses, loads, fixed and switched shunts, machines with P/Q limits and V setpoint, all branch rating fields, two-winding transformers with CW/CZ/CM codes).
2. `fnsl()` default solution settings: reactive-limit handling (sets `enforce_q_lims`), tap, area-interchange and switched-shunt adjustment, mismatch tolerance, iteration limit; read machine QGEN against QMAX/QMIN in a solved scaled copy.
3. `scal_2` details: does total generation include the swing machine, are machines clamped at Pmax/Pmin, in-service-only scaling, and does the increment form scale Q with P (decides whether the margin walk adds P only or P and Q).
4. Island outcome: confirm ierr 3 for islanding outages (recorded `non_convergence` rows may already show it).
5. RATEA of unmapped lines; any load with constant-current or constant-admittance parts.
6. Optional but recommended: the full-state reference dump (solved base per city, ideally per outage).

## Implications for Roadmap

Suggested 6 phases:

1. **PSS/E measurement session and network parity.** The private export, fail-closed parser, builder, parity report, full-vector base-case match, recorded settings, decision on fixture vs private network, ignore patterns and placeholder-only fixtures before any real data is touched. **Needs research** (PSS/E machine; transformer conversion; vendor licence).
2. **PandapowerApi and study engine (no database).** `PandapowerApi`, `api_factory`, swing-machine column, island/NaN rule, deepcopy discipline, `runpp` settings, current-basis loading, unit tests mirroring `units.py`, end-to-end `make_study` dry run on the placeholder mapping, 3.5.6 re-verification, measured deepcopy cost. **Standard patterns.**
3. **Schema migration, solver tag, writer path** (parallel with 2). Additive migration, five `psse_job` edits, per-solver gap SQL and `gaps.py`, v1.1 schema doc, the pinned tests rewritten, `psse_local_pg` updated, local-Postgres rehearsal, dry-run default. **Standard patterns.**
4. **Replay harness and agreement check** (the go-live gate). Read-only `replay.py`, stored `ratings_used`, filter by mapping hash and job version, early reconciliation against recorded `line_voltage_kv`, `rate_before_mva` and branch keys, calibration mode, epsilon band, max-deviation report, deliberate-failure test, counts-only CI mode, explicit statement of which criterion is met. **Needs research** (corpus content unknown; tolerance floors and borderline band are decisions).
5. **Hourly workflow: dry run, then live soak.** Dispatch-only, :20 UTC, own concurrency group, main guard, `production` environment, timeout 15 to 20 min, secrets (writer URL, ratings read, private mapping as minified single-line JSON), identifier-free logging with a leak test, gap-check workflow, external freshness alarm, retention decision written, then 24 consecutive slots verified by the solver-aware gap query. **Standard patterns** (copies `dlr_live.yml`).
6. **Dashboard view and DEF-01.** Definer view migration with whitelisted columns and unit-first comments, explicit grants, `verify_exposure.sql` and `expose_migration_test.py` updated, `NOTIFY pgrst, 'reload schema'`, anon-key smoke check, view contract drift test, `rest-api.md` section, DEF-01 edit on the separate software-dashboard branch (needs coordination). **Light research** (PostgREST cache reload, Supabase default grants for views).

Ordering rationale: parity gates everything and depends on the PSS/E machine, so it starts first; 2 and 3 run in parallel; live writes follow agreement because rows are permanent; the view ships last so no unverified figure reaches the dashboard; ignore rules and log policy go in at the start of Phases 1 and 5.

## Confidence Assessment

| Area | Confidence | Notes |
|---|---|---|
| Stack | HIGH | Versions, resolution, `pip check`, timings and source reads done against 3.5.6. pandapower-to-PSS/E closeness is MEDIUM. |
| Features | MEDIUM | pandapower behaviour HIGH (run on 3.2.2); PSS/E defaults UNVERIFIED (`fnsl()` uses unrecorded case settings). |
| Architecture | HIGH / MEDIUM / LOW | HIGH on seam, schema, gaps, Actions layout; MEDIUM on pandapower internals; LOW on numerical agreement. |
| Pitfalls | HIGH / MEDIUM | HIGH on pandapower, GitHub, Supabase; MEDIUM on PSS/E semantics; the private case was never inspected. |

**Overall: MEDIUM.** The build is low risk; whether agreement can be demonstrated depends on measurements not yet taken.

## Gaps to Address

- Criterion (a) stored-quantity agreement vs (b) full-state agreement: decide in requirements; if (b), schedule the reference export in the Phase 1 session.
- All PSS/E-machine items above.
- Whether the PSS/E copy equals MATPOWER data and whether it may be committed (vendor licence unverified); private storage fallback (48 KB secret limit; avoid the encrypted-file-in-repo workaround).
- Replay corpus: how many of the 19 runs have non-empty violation sets and share one study definition; may need stressed reference runs kept off the database.
- `MAXPCTRATEA` vs `loading_percent` equivalence; re-verification of 3.2.2 findings on 3.5.6.
- Open owner decisions: retention for 24 row sets a day; shared writer role vs a separate CI role (rotation runbook minimum); tie-break solver preference in the view; two requirements files vs one; staleness alarm scope.
- Unverified platform details: PostgREST cache reload after the new view; multi-line JSON secret masking (use minified single-line, never print); `workflow_dispatch` exemption from the 60-day disable rule; cron-job.org time zone and token expiry.
- `gaps --solver psse` will list every hour while the laptop job is paused; treat as expected.

## Sources

Primary: repo code, docs and workflows (`backend/psse_job/*`, the v1 migration, `supabase/ops/verify_*.sql`, `dlr_live.yml`, `shadow_collect.yml`, schema docs, pss-e-integration records, pandapower-solver `STATE.md`); PyPI metadata for pandapower 3.5.6; scratch Python 3.12 experiments; pandapower source and docs; MATPOWER `case39.m`; GitHub and Supabase docs. Secondary: PSSPY `fnsl` reference, PowSyBl PSS/E import docs, MATPOWER list post. Tertiary: PSS/E forum threads; no published pandapower-versus-PSS/E comparison exists, so 0.01 pu and 2% are project-chosen thresholds.
