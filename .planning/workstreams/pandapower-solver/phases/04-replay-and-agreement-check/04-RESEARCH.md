# Phase 4: Replay and agreement check - Research

**Researched:** 2026-11-20
**Domain:** read-only replay of recorded PSS/E runs through the pandapower engine, a two-solver agreement report, owner-local detail with counts-only CI output
**Confidence:** MEDIUM overall. HIGH on the code seams, tolerances and test design (all read this session). MEDIUM on the recorded corpus: the live database was never queried (no credential was used or printed), so how many of the 19 runs share one mapping hash, one case hash or one rating set is unknown.

<user_constraints>
## User Constraints

No `04-CONTEXT.md` exists for this phase (the phase directory was empty), so there is nothing to copy verbatim. The locked inputs are the workstream decisions and requirements that bind this phase:

### Locked decisions (from STATE.md "Decisions", REQUIREMENTS.md, ROADMAP.md Phase 4)
- Agreement is checked by replaying the recorded PSS/E runs (their stored ratings) through pandapower: same overload and voltage violation set per outage, bus voltages within 0.01 pu, flows and capacities within 2%. (STATE.md line 38)
- The replay matches each run to the mapping by the run's recorded hash, writes nothing to the database, reports near-limit elements as borderline, states runs checked, non-empty comparisons, the largest deviation even on a pass, and the exclusions with reasons. A deliberate mismatch test must make it fail. (AGR-01 to AGR-03)
- Detailed output stays on the owner's machine; CI prints counts and pass or fail only. (AGR-04)
- Out of scope: tuning network parameters to force agreement; committing the network export, reference solution or mapping. (REQUIREMENTS.md "Out of Scope")
- The converted network stays private and lives in the owner's check folder (decision record 2026-11-20). (`docs/data-science/decisions/pandapower_network_data_decision.md`)
- Never print, quote or copy a value from `data/private/`. Do not commit research or code from this step.

### Claude's discretion
Module and file names, the report layout, the exact borderline and resolution rules (these need owner confirmation, see Open Questions), the test layout.

### Deferred (out of scope here)
AGR-05 (re-run whenever new PSS/E runs exist), ENG-07, OPS-06, DB-04, the hourly workflow (Phase 5), the dashboard view (Phase 6).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AGR-01 | Read-only replay of each recorded PSS/E run through pandapower with the run's stored ratings and the same mapping (matched by recorded hash); writes nothing | Sections "Reading the recorded runs", "Proving it writes nothing", Pattern 1 to 3, Pitfalls 1, 2, 3 |
| AGR-02 | Pass when per outage the sets of overloads, voltage violations and non-converged outages are the same and margins and dispatched capacity agree within 2%; near-limit elements are borderline | "What is compared", Pattern 4, Pitfall 4 and 5 |
| AGR-03 | Report states runs and non-empty comparisons checked, the largest deviation even on a pass, exclusions and reasons; a deliberate mismatch test proves it can fail | "Report structure", "The deliberate mismatch test", Validation Architecture |
| AGR-04 | Detail stays on the owner's machine; anything printed in Actions is counts and pass or fail only | "Detail local, CI counts only", Pattern 5 |
</phase_requirements>

## Summary

The replay is a thin harness around code that already exists. The recorded rows hold everything a replay needs except the mapping and the network, which are private files: `psse_run.ratings_used` holds each city's stored rating (amps per conductor, bundle count, source, fallback reason), `mapping_sha256` and `case_sha256` identify the study definition, and three result tables hold what PSS/E recorded. The replay rebuilds a `ratings.Selection` from `ratings_used`, calls `engine.prepare_run(...).study(selection, None)` directly (never `job.run_once`, never the writer), and compares the returned `StudyResults` with the recorded rows using the Phase 1 comparator tolerances. Nothing in the replay path needs a database connection if the owner first exports the recorded rows once into a private snapshot file. That export is the only code that touches the database, and it is read-only.

No read-only database role exists. The only roles the migrations create are `dlr_writer` and `dlr_psse_writer`; the four result tables are private (no privilege for `anon` or `authenticated`) and only `dlr_psse_writer` has a select policy, together with INSERT. So the recommended route is the one `gaps.run` already uses: connect as the writer with a read-only transaction (`autocommit = False`, `read_only = True`), issue only allow-listed SELECT texts through a guard wrapper, and prove it with a recording fake, an import scan, and a Postgres-tier test that a write attempt is refused with SQLSTATE 25006. The owner then needs nothing new except the writer connection string in their own shell. An optional additive migration for a SELECT-only role is the stronger alternative and is listed as an owner decision.

Three findings change how the comparison must be built. (1) The margin search is quantised: a rating-bound margin stops at the first 25 MW step whose flow reaches the rating, so a tiny flow difference moves `margin_mw` by a whole step; a strict 2% test would fail on quantisation, not on disagreement. The comparison needs a per-quantity resolution floor taken from the stored search settings. (2) The stored tables hold only violations, so a one-sided row can only be classed borderline by asking whether its excess over the limit is within the tolerance; and the corpus may exercise little: the 19 runs probably carry few distinct rating sets, and thermal and non-converged outages may have no rows at all. The report must say "not exercised" for such kinds instead of "agree". (3) The run's `case_sha256` is the hash of PSS/E's `.sav` file and can never equal the hash of the pandapower converted network; the comparable value is the `case_sha256` the Phase 1 session recorded in its manifest, which `cli check` copies into `report.json` under `session`.

**Primary recommendation:** Add `pandapower_job/recorded.py` (the only reader: read-only export to a private snapshot, plus snapshot loader), `pandapower_job/replay.py` (pure compute and comparison, no database import) and an entry script `backend/pandapower_replay.py`; replay each distinct (mapping hash, rating set) once on the recorded settings and the converted network; classify results as pass, fail or incomplete with a closed output vocabulary in CI mode; prove failure with a stand-in "recorded" run built from the public 39-bus fixture and a matrix of single mutations.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Read recorded runs | Owner machine, export step (Python, read-only DB session) | Database (RLS, writer role select policy) | One narrow reader keeps the replay path free of any connection code |
| Hold recorded runs between steps | Owner machine, private snapshot file under `data/private/pandapower/` | none | Rows are append-only so a snapshot is exact; also lets the replay run offline and on this Windows machine |
| Rebuild ratings and run the study | `pandapower_job` engine (solver tier) | `psse_job.study` loops (unchanged) | Same code path as the hourly job, so a disagreement is never a harness difference |
| Compare and classify | `pandapower_job/replay.py` (pure) | `pandapower_job/compare.py` tolerance functions | Tolerances live in one place and are imported, never redefined |
| Detailed report | Owner machine, private report folder | none | Names buses, circuits and values |
| CI summary | Closed-vocabulary printer | `GITHUB_ACTIONS` auto switch | Public log must hold counts and a word only |
| Proof of "writes nothing" | Tests (recording fake, import scan, Postgres tier) | Read-only session | Evidence must not depend on trust |

## Standard Stack

No new package. The phase uses what Phases 1 to 3 pinned. [VERIFIED: ran imports with `.venv/Scripts/python.exe` this session]

### Core
| Library | Version | Purpose | Why standard |
|---------|---------|---------|--------------|
| pandapower | 3.5.6 | the solver under the engine | already pinned in `requirements-pandapower.txt` and in use |
| psycopg | 3.3.6 | the export step's read-only session, via `psse_job.writer.connect` only | the job's existing driver; imported only inside `writer.connect` |
| pytest | 9.0.3 | tests | repo standard (`pytest.ini`: `pythonpath = backend`, `*_test.py`) |

### Supporting (in repo, reuse as is)
| Module | Use |
|--------|-----|
| `pandapower_job.engine` | `prepare_run`, `load_recorded_backend`, `is_placeholder` |
| `pandapower_job.compare` | `within_voltage`, `within_flow`, `flow_allowance` and the four tolerance constants |
| `pandapower_job.private` | `make_private_dir`, `write_private_json` (git-ignore guard, owner-only files, exclusive create) |
| `pandapower_job.cli` | the `_Printer` plus `CLI_LINE_PATTERNS` closed-vocabulary pattern, `REPORT_MARKER`, exit codes |
| `psse_job.ratings` | `RatingChoice`, `Selection`, `parse_ts` |
| `psse_job.run_record` | `validate_results` on replayed results; `build_run_record` and `result_rows` to build the stand-in recorded run in tests |
| `psse_job.redaction` | `redact`, `env_secrets` for any failure line |
| `backend/private_leak_scan.py` | `derive_needles`, `scan_paths`, `SHAPE_PATTERNS` for the output scan test |

### Alternatives considered
| Instead of | Could use | Tradeoff |
|------------|-----------|----------|
| Writer role on a read-only session | New SELECT-only role (additive migration, owner applies, new secret) | Database-enforced but one more one-way owner step and credential; Phase 3 D-02 deliberately added none |
| Snapshot file between export and replay | Replay reading the database directly | Direct reading puts connection code in the compute path, makes the "writes nothing" proof harder and breaks offline and Windows use |
| Owner SQL-editor export | Python export | Needs no credential in code, but the editor may truncate about 4000 rows with JSON details; keep as fallback only |

**Installation:** none. **Package Legitimacy Audit:** not applicable, this phase installs no external package; nothing was run through the legitimacy seam.

## Architecture Patterns

### System architecture

```
 owner shell: SUPABASE_PSSE_DB_URL (writer string, never printed)
        |
        v
 [export]  recorded.export()                       data/private/pandapower/sessions/<s>/check_<t>/
   writer.connect -> autocommit False, read_only True      report.json (settings, session{case_sha256,mapping_sha256})
   guard wrapper: allow-listed SELECT texts only           converted_network.json
   4 tables, runs where run_id like 'psse-%'               scaling_details.json
        |                                                  data/private/pandapower/mapping.json
        v                                                         |
 snapshot file (private, marker key, run rows + 3 tables)         |
        |                                                         |
        v                                                         v
 [replay]  replay.py  (imports no psycopg, no writer, no job) <---+
   1 plan: per run, check hashes -> eligible or excluded(reason)
   2 group eligible runs by (mapping hash, rating tuple) -> distinct configurations
   3 per configuration: Selection from ratings_used ->
       engine.prepare_run(recorded backend, converted_network.json, mapping.json).study(selection, None)
       validate_results; StudyFailed counts as a replay failure, not an exclusion
   4 compare each recorded run with its configuration's results (data, sets, values, margins, dispatch)
   5 verdict: pass | fail | incomplete
        |                                   |
        v                                   v
 private report (detail, values)     closed-vocabulary summary on stdout
 (not written in CI mode)            (counts and the verdict word only)
```

### Recommended project structure
```
backend/pandapower_job/recorded.py    # read-only export + guard + snapshot load (only DB-touching module of the phase)
backend/pandapower_job/replay.py      # selection rebuild, plan, replay, comparison, verdict, rendering
backend/pandapower_replay.py          # entry script, same shape as pandapower_net_check.py (export, replay)
backend/tests/pandapower_recorded_test.py        # guard, recording fake, import scan (runs here)
backend/tests/pandapower_replay_test.py          # comparison matrix, borderline, exclusions (pure, runs here)
backend/tests/pandapower_replay_study_test.py    # real solver on the public fixture: self-replay, mismatch matrix (runs here, ~12 s per study)
backend/tests/pandapower_replay_output_test.py   # closed vocabulary, leak scan, CI writes no file (runs here)
backend/tests/pandapower_replay_pg_test.py       # Postgres tier: nothing changes, 25006, SELECT-only role (skips here)
```
A stand-in helper (recorded run built from a fixture study) belongs in `backend/tests/pandapower_study_fixture.py`, which is already the shared helper and is not collected.

### Reading the recorded runs (question 1)

Columns the replay needs, from `backend/psse_job/contract.py`:

- `psse_run` (contract.py:40-45): `run_id, slot_time, started_at, finished_at, outcome, failed_stage, error, ratings_read_error, case_id, case_sha256, mapping_sha256, rate_set, ratings_used, n_contingencies, n_contingencies_with_results, job_version, psse_version`. Read: `run_id, slot_time, outcome, failed_stage, case_sha256, mapping_sha256, rate_set, ratings_used, n_contingencies, n_contingencies_with_results, job_version`. Do not read `error`, `ratings_read_error` or `case_id`.
- `psse_dispatched_capacity` (contract.py:83-90): `run_id, run_outcome, city, rating_source, fallback_reason, city_rating_valid_time, city_rating_computed_at, applied_amps_per_conductor, subconductors_per_phase, applied_amps_circuit, line_voltage_kv, applied_mva, voltage_limit_mva, dispatched_mva, dispatched_amps_circuit, dispatched_amps_per_conductor, power_factor, dispatched_mw, limiting_factor, details`.
- `psse_voltage_margin` (contract.py:92-96): `run_id, run_outcome, city, method, base_transfer_mw, limit_transfer_mw, margin_mw, margin_pct, voltage_limit_mva, critical_bus, min_voltage_pu, details`.
- `psse_contingency_result` (contract.py:98-101): `run_id, run_outcome, contingency_id, violation_kind, element_type, element_id, city, limit_value, observed_value, exceeded_by, unit, details`.
- `ratings_used` keys per city (constants.py:68-74): `"source", "fallback_reason", "rating_amps_per_conductor", "subconductors_per_phase", "rating_amps_circuit", "static_rating_amps_per_conductor", "line_voltage_kv", "rating_mva", "city_rating_valid_time", "city_rating_computed_at", "city_rating_run_id", "city_rating_status", "config_fingerprint", "age_minutes", "server_is_stale", "server_is_provisional"`.
- `details` keys the replay uses: dispatch `details.branches`, `details.rate_before_mva`, `details.voltage_limit_bounded_by` (dispatch.py:90-95); margin `details.bounded_by`, `lower_bound`, `step_mw`, `tolerance_mw`, `sink_buses`, `criterion_pu` (margin.py:278-291). [VERIFIED: files read this session]

Filter. Use `run_id like 'psse-%'`, not `solver = 'psse'`. The solver-tag migration `20261118200000_psse_run_solver_tag.sql` is not applied to the live project (project notes, STATE.md), so a `solver` column may not exist yet; the migration ties the `psse-` prefix to `solver = 'psse'`, so the two filters are equivalent after it and the prefix filter works before and after. Replay only `outcome in ('ok','fallback')`; a `failed` run has no result rows (run_record writes none).

Which credential can read, and does a read-only one exist? [VERIFIED: grep of `supabase/migrations/*.sql` this session]
- `supabase/migrations/20261109233541_psse_results.sql:164`: `revoke all on public.psse_run, public.psse_dispatched_capacity, public.psse_voltage_margin, public.psse_contingency_result from public, anon, authenticated;` so the publishable key (REST) cannot read them.
- `supabase/migrations/20261109233541_psse_results.sql:175`: `grant select, insert on public.psse_run, public.psse_dispatched_capacity, public.psse_voltage_margin, public.psse_contingency_result to dlr_psse_writer;` and the only policies are `dlr_psse_writer_insert` and `dlr_psse_writer_select` (lines 177-195).
- The only roles any migration creates are `dlr_writer` (city_rating, no access to these tables) and `dlr_psse_writer`. **No read-only role exists.** The Supabase owner and `service_role` bypass RLS but are forbidden by this repo's own rules (`ratings.fetch_latest_rating` refuses a secret key or a service_role JWT) and must not be used for a replay.

Recommended route: the writer connection string in the owner's shell as `SUPABASE_PSSE_DB_URL` (constants.py: `ENV_PSSE_DB_URL = "SUPABASE_PSSE_DB_URL"`), opened with `writer.connect(env=env)`, then read-only. This is exactly what `gaps.run` does (gaps.py:152-153: `conn.autocommit = False` then `conn.read_only = True`, with the reason in the comment above it). psycopg documents `read_only` as "The read-only state of the new transactions started on the connection" [CITED: psycopg.org/psycopg3/docs/api/connections.html], which is why autocommit must be left first. What the owner must do if they want a hard guarantee instead: apply one additive migration creating a SELECT-only login role and select policies (open question Q1); this is optional.

### What is compared (question 2)

Tolerances come from `backend/pandapower_job/compare.py:45-48`, quoted verbatim: `VOLTAGE_TOLERANCE_PU = 0.01`, `FLOW_RELATIVE_TOLERANCE = 0.02`, `FLOW_FLOOR_MVA = 2.0`, `COMPARISON_EPSILON = 1e-12`, with `within_voltage`, `flow_allowance` (`max(FLOW_RELATIVE_TOLERANCE * abs(ref_mva), FLOW_FLOOR_MVA)`) and `within_flow` at lines 83-95. The replay imports these functions. It must not define a second tolerance literal for voltages or flows (compare.py's own test walks that file's syntax tree; give `replay.py` the same kind of test for the few constants it does add).

Check order (fail loudly on shape first). Reference side is the recorded PSS/E value, replay side is pandapower.

| # | Check | Rule | Class |
|---|-------|------|-------|
| 1 | Shape | `n_contingencies` equal; `n_contingencies_with_results` equal; one dispatch and one margin row per city on both sides | fail |
| 2 | Data reconciliation per city | `line_voltage_kv`, `applied_amps_per_conductor`, `subconductors_per_phase`, `applied_mva` equal (relative 1e-6); `details.branches` equal as a set; `details.rate_before_mva` equal (relative 1e-6); margin `details.sink_buses` equal as a set; every both-sided violation row's `limit_value` equal (relative 1e-9) | data fail, never borderline |
| 3 | Violation sets per outage | key = `(contingency_id, violation_kind, element_id)`; kinds are `"thermal_overload", "voltage_low", "voltage_high", "non_convergence"` (constants.py:55); an outage is one `contingency_id` | see below |
| 4 | Values on keys present on both sides | voltage rows: `within_voltage` on `observed_value`; thermal rows: `within_flow` on `observed_value`; `city`, `element_type`, `unit` equal | fail |
| 5 | Margin per city | see "Margin resolution" | fail |
| 6 | Dispatch per city | `within_flow` on `dispatched_mva`; `limiting_factor` equal, else borderline when `abs(applied_mva - voltage_limit_mva)` is within `flow_allowance(applied_mva)` on either side | fail or borderline |

Same set. A key present on one side only is not automatically a failure. Its row says the element exceeds its limit by `exceeded_by`; the other solver's value is unknown (violations are the only thing stored) but is on the other side of the limit. Agreement within tolerance is therefore possible exactly when `exceeded_by` is within the allowance: `flow_allowance(limit_value)` for a thermal row, `VOLTAGE_TOLERANCE_PU` for a voltage row. Define **borderline** as that case: reported with count and largest excess, not a failure. A one-sided key whose excess is larger is a **set failure**. A `non_convergence` row present on one side only is always a failure (one solver converged, the other did not); intra-run `details` of such rows are not compared. This rule is permissive by construction (it admits anything the owner's own tolerance admits), which is why the count and largest borderline excess must appear in the report (Q3 asks the owner to confirm the band).

Margin resolution. The search steps by `transfer.step_mw` and bisects to `transfer.tolerance_mw` (margin.py:116-148, quoted behaviour: the walk returns `"dlr_rating"` at the first stepped point whose flow reaches the rating; only after a bad point does it bisect to `tol_mw`). So for a rating-bound margin, `limit_transfer_mw` and `margin_mw` are only defined to one step (25 MW default), while `voltage_limit_mva` and `min_voltage_pu` are read at that quantised point and are lower-bound style numbers (`details.lower_bound` true). Rules:

- Classes of `details.bounded_by`: `{dlr_rating}`, `{voltage_criterion, non_convergence}` (both mean voltage limited), `{base_case}`. Different classes are a failure. Same class with different members is noted, not failed.
- Voltage-limited margin: `margin_mw`, `limit_transfer_mw`, `base_transfer_mw` compared with allowance `max(flow_allowance(ref), tolerance_mw)` (the stored bisection tolerance); `min_voltage_pu` with `within_voltage`; `voltage_limit_mva` with `within_flow`.
- Rating-bound margin: `margin_mw` and `limit_transfer_mw` compared with allowance `max(flow_allowance(ref), step_mw)` using the stored `step_mw`; `min_voltage_pu` and `voltage_limit_mva` are not value-compared (they depend on which step the walk stopped at); the differences are reported as "quantised", and `dispatched_mva` (which equals the applied rating when rating-bound) is the headline.
- `critical_bus` is not a gate; a difference is counted as a note.
- The resolution floor is derived from stored search settings, not tuned, and must be printed in the private report header. It is an owner decision (Q2).

Non-empty comparison. Count, separately: (a) outages whose union of recorded and replayed keys is non-empty, split by kind (thermal, voltage, non_convergence); (b) key pairs value-compared; (c) margin comparisons; (d) dispatch comparisons. A kind with zero non-empty comparisons is reported "not exercised", never "agree". The check can only be a pass if there is at least one replayed run and at least one non-empty set comparison (otherwise `incomplete`), which is the same discipline `compare.py` applies ("Incomplete is not passed").

Largest deviation. Track, per quantity, the largest deviation and its ratio to its own allowance ("utilisation", 1.00 is the edge). The headline is the largest utilisation across everything compared, printed even on a pass in the private report. The deviation of a self-replay is 0 (deterministic: 02-05 proved two runs equal), so the teeth test must perturb the recorded side by a known amount to show a non-zero deviation on a pass.

### Report structure (question 4)

Private detail report (owner machine, `data/private/pandapower/replays/replay_<stamp>/`, created with `private.make_private_dir`, JSON written with `private.write_private_json(path, obj, cli.REPORT_MARKER)`, so a stray copy is caught by the leak scan's shape layer):

1. Header: pandapower version, tolerance constants and resolution rule in force, snapshot export time, replayed settings provenance (`engine.settings_record` without values it need not repeat), verdict word.
2. Counts: runs in snapshot, replayed, excluded (by reason), distinct configurations, outages compared, non-empty set comparisons per kind, key pairs value-compared, margin and dispatch comparisons, borderline count, runs passed and failed.
3. Largest deviation: per quantity (value and utilisation), and the single largest utilisation with its run, city and element.
4. Exclusions: one line per run with a reason from a closed list: `failed_run`, `mapping_hash_missing`, `mapping_hash_differs`, `case_hash_differs`, `ratings_unusable`, `rows_incomplete`.
5. Failures and borderlines with element keys and both values (private).

A replay that raises `StudyFailed` on a run PSS/E completed is a **failure** of that run (stage word only), never an exclusion. Exclusions are only for inputs that prove the comparison would not be like for like.

CI summary (stdout only, closed vocabulary): `replay: pass|fail|incomplete`, `runs in snapshot: N`, `runs replayed: N`, `runs excluded <reason>: N`, `non-empty comparisons <kind>: N`, `borderline: N`, `runs failed: N`. No deviation values, no element, no hash.

### Proving it writes nothing (question 3)

Layered, cheapest first. Each layer has its own test.

1. **No connection code in the compute path.** `replay.py` imports no `psycopg`, no `psse_job.writer`, no `psse_job.job`. An AST scan like `pandapower_import_gate_test.py`'s `_collect_imports` pins that. `recorded.py` imports `psse_job.writer` and uses only `writer.connect`; a text scan asserts `write_run`, `record_failure`, `INSERT_` and the words insert, update, delete, truncate, alter, create, drop, grant never occur in its statements.
2. **Read-only session.** Same sequence as gaps.py:152-153 before any statement. Never call `conn.commit()`; end with `rollback()` then `close()`.
3. **Statement guard.** `recorded.py` wraps the connection in an object whose only method runs a statement if its text is one of a fixed tuple of module constants (exact string match, bound parameters only) and raises `WriteRefused` otherwise. A planted `insert` through the wrapper raises before reaching the driver.
4. **Recording fake test (runs here).** A fake connection records every `execute`, plus the order of `autocommit`/`read_only` assignments and `commit`/`close` calls. Assert: `autocommit` is False and `read_only` True before the first `execute`; every statement is in the allow-list; no `commit`; `close` called on success and on failure.
5. **Postgres tier (skips here, runs on a machine with Postgres).** On a throwaway database seeded through the real writer: fingerprint the four tables (row counts and an md5 of the ordered rows) before and after an export; assert equal. Reuse the proxy pattern of `psse_gaps_pg_test.py` (lines 334-407: records each statement, asks the server `show transaction_read_only`, and shows a read-only insert leaves no row). Add: an insert on the guarded connection is refused with SQLSTATE 25006, which `credcheck.py` documents (its module docstring: PostgreSQL checks a read-only transaction before privileges, giving 25006). With `PSSE_REQUIRE_PG=1` a missing Postgres is a failure, never a skip.
6. **Replay never reaches the database at all.** In the replay test, call `replay.run(snapshot, ...)` with `socket.socket.connect` and `psycopg.connect` monkeypatched to raise; the replay still completes.

Rejected: driving `job.run_once` with a "dry" connection. It exists to write; a bug in the harness would write. The replay calls the study callable directly.

### Detail local, CI counts only (question 5)

- Mode: `GITHUB_ACTIONS == "true"` forces CI mode whatever the flag (fail safe), `--ci` forces it locally. CI mode writes no file (a detailed folder on the runner could be uploaded as an artifact of a public repo) and prints only through the closed-vocabulary printer.
- Closed vocabulary: copy the mechanism of `cli._Printer` (cli.py:117-135): a tuple of compiled regexes, each ending `\Z`, numbers only as `[0-9]{1,9}`, words from fixed sets; `say()` raises `ValueError` for any other line. Free text, exception messages and `str(path)` never reach `say`. Every failure line is a reason word from a fixed set (as `RecordsRefused` reasons are), not an exception string.
- The scan test (reuse `backend/private_leak_scan.py`): (a) every printed line matches the vocabulary; (b) build a synthetic private tree under `tmp_path`, `needles = private_leak_scan.derive_needles(str(private_root))`, write the CI output to a file and run `private_leak_scan.scan_paths([file], needles=needles, root=...)`: no finding; (c) a second needle set built from the test's own recorded and replayed data (every run id, element id, bus number, hash, and every number in `repr`, `%g` and `%.1f` forms, length at least 5, matching whole tokens as the scanner does) must not occur in the output; (d) teeth: append one planted identifier to the output and see both (b) and (c) find it (so the scanner is proven able to fire). `pandapower_cli_test.py:574-590` is the precedent for writing output to a file and scanning it.
- Exit codes follow the existing entry script: 0 pass, 1 fail or incomplete, 2 usage or refusal (cli.py:53-55: `EXIT_OK = 0`, `EXIT_FAILED = 1`, `EXIT_USAGE = 2`); the export step uses 6 for "could not read the database" as `gaps.py` does.

### The deliberate mismatch test (question 4)

Build the "recorded PSS/E run" from the public 39-bus fixture, with no private data, the way Phase 2 tests do:

1. `case = write_converted(tmp)`, `mapping = write_placeholder_mapping(tmp)`, `selection = study_fixture.selection()`, `backend = fixture_backend()`.
2. `results = engine.prepare_run(backend, case, mapping, allow_placeholder=True).study(selection, None)`.
3. Present them as a PSS/E run: `results = results._replace(solver="psse", solver_version=None, psse_version="test")`, a `contract.RunContext(run_id, started_at, case_id, case_sha256, mapping_sha256, job_version)` with the default PSS/E solver, then `record = run_record.build_run_record(context, selection, finished_at, results=results)` and `rows = run_record.result_rows(record, results)`. These are the same shapes the database returns. `mapping_sha256` is `mapping_module.load_mapping(mapping, True).sha256`.
4. Measured this session on that fixture (default settings, `fixture_backend()`): 38 outages, 54 contingency rows, all `voltage_high`, 24 outages with results, all four cities voltage-limited, about 11.7 s per four-city study without numba. [VERIFIED: probe run this session] So the public fixture gives non-empty voltage comparisons but no thermal and no non-converged rows. To exercise those kinds use a stress rating (low amps in the stand-in selection) and `contingency.extra` with `study_fixture.ISLANDING_OUTAGE`, as `pandapower_study_behaviour_test.py` does for the island.

Test matrix (parametrised), each on a deep copy of the recorded rows, replayed with the real solver once per module-scoped study:
- self-replay passes, non-empty comparisons greater than 0, deviation 0;
- recorded `observed_value` changed by +1% (thermal) or +0.005 pu (voltage): still pass, and the largest deviation is now non-zero (teeth on the pass side);
- changed by +3% or +0.02 pu: fail;
- drop one violation row from the recorded set: fail unless its excess is within the band (assert both outcomes with a row far over and a row marginally over);
- add a bogus recorded row for a bus or branch that is not in violation: fail;
- change `n_contingencies`: fail;
- flip a recorded row to `non_convergence`, or remove one (stress variant): fail;
- change `dispatched_mva` by +3%: fail; by +1%: pass;
- move `margin_mw` by more than the resolution: fail; by less: pass;
- change a recorded rating in `ratings_used` (replay then runs a different configuration from the one recorded): fail on dispatch and sets;
- alter the mapping file after hashing the recorded run: the run is excluded `mapping_hash_differs`, replayed count 0, verdict incomplete (a bypassed hash must not pass silently);
- all runs excluded or zero non-empty comparisons: verdict `incomplete`, exit 1.

### Pattern 1: rebuild the selection from the stored ratings

**What:** one `ratings.RatingChoice` per city from `ratings_used`, never from `constants` or the live ratings view. **When:** every replay. **Why:** PITFALLS 2.1 (inputs re-derived instead of replayed).

```python
# Source: backend/psse_job/ratings.py (RatingChoice fields, Selection, parse_ts) read this session
def selection_from_ratings_used(ratings_used):
    choices = {}
    for city in constants.CITIES:
        item = ratings_used[city]                       # exactly constants.RATINGS_USED_KEYS
        amps = item["rating_amps_per_conductor"]
        count = item["subconductors_per_phase"]
        # unusable if not finite and positive, count not a positive int,
        # source not in constants.SOURCES, or amps*count differs from rating_amps_circuit by more than 1e-6
        valid = item["city_rating_valid_time"]
        computed = item["city_rating_computed_at"]
        choices[city] = ratings.RatingChoice(
            city=city, source=item["source"], fallback_reason=item["fallback_reason"],
            amps_per_conductor=float(amps), subconductors_per_phase=count,
            amps_circuit=float(item["rating_amps_circuit"]),
            static_amps_per_conductor=item["static_rating_amps_per_conductor"],
            row_valid_time=None if valid is None else ratings.parse_ts(valid),
            row_computed_at=None if computed is None else ratings.parse_ts(computed),
            row_run_id=item["city_rating_run_id"], row_status=item["city_rating_status"],
            row_config_fingerprint=item["config_fingerprint"], age_minutes=item["age_minutes"],
            server_is_stale=item["server_is_stale"], server_is_provisional=item["server_is_provisional"])
    return ratings.Selection(choices, None, 0)
```
A run whose entry fails these checks is excluded `ratings_unusable`. Afterwards call `run_record.validate_results(results, selection)` on the replayed results; it already checks that the replay applied exactly the selected rating.

### Pattern 2: one replay per distinct configuration

Replayed results depend only on (mapping, ratings, network, settings). Key a cache by `(mapping_sha256, tuple of (amps, count) per city, source and fallback per city)`. With the 19 runs probably sharing one mapping and few rating sets this turns about 4 minutes (19 × about 12 s) into a few studies, and it gives an honest "runs vs distinct configurations" count. [ASSUMED: that the corpus is this uniform; the export counts it]

```python
# Source: backend/pandapower_job/engine.py:143-171 (prepare_run) and :320-334 (load_recorded_backend)
backend = engine.load_recorded_backend(check_dir)           # RecordsRefused fails closed
if engine.is_placeholder(backend):                          # never replay on placeholder settings
    raise Refused("placeholder_settings")
prepared = engine.prepare_run(backend, converted_network_json, mapping_json)
# prepared.mapping_sha256 is the hash of the mapping bytes; compare it with each run's mapping_sha256
results = prepared.study(selection, None)                   # StudyFailed -> run failure (stage word only)
```

### Pattern 3: the read-only session and guard

```python
# Source: modelled on backend/psse_job/gaps.py:132-172 (run) read this session
SELECT_RUNS = "select run_id, slot_time, outcome, ... from public.psse_run where run_id like 'psse-%' order by slot_time, run_id"
ALLOWED = (SELECT_RUNS, SELECT_DISPATCH, SELECT_MARGIN, SELECT_CONTINGENCY)   # module constants

class WriteRefused(RuntimeError): ...

class ReadOnly(object):
    def __init__(self, conn):
        conn.autocommit = False          # before any statement, or read_only would do nothing
        conn.read_only = True
        self._conn = conn
    def select(self, text, params=None):
        if text not in ALLOWED:
            raise WriteRefused("statement not allowed")
        return self._conn.execute(text, params).fetchall()
    def close(self):
        try: self._conn.rollback()
        finally: self._conn.close()
```
Result tables are read with `where run_id = any(%(ids)s)` (a bound parameter, the text is still a constant). After reading, check integrity: each non-failed run has 4 dispatch and 4 margin rows and the distinct `contingency_id` count equals `n_contingencies_with_results`; a truncated read is `rows_incomplete`, not a pass.

### Pattern 4: borderline classification (pure)

```python
# Source: compare.py tolerance functions (lines 83-95) imported, not redefined
def one_sided(row):
    """'borderline' when the row's excess over its limit is within the owner's tolerance, else 'fail'."""
    if row["violation_kind"] == "non_convergence":
        return "fail"
    excess = row["exceeded_by"]
    if row["violation_kind"] == "thermal_overload":
        band = compare.flow_allowance(row["limit_value"])
    else:
        band = compare.VOLTAGE_TOLERANCE_PU
    return "borderline" if excess <= band + compare.COMPARISON_EPSILON else "fail"
```

### Pattern 5: closed-vocabulary CI printer

Copy `cli._Printer` and extend the pattern tuple with the replay lines (verdict words from `("pass", "fail", "incomplete")`, reason words from a constant tuple, counts `[0-9]{1,9}`). A test enumerates every line the CI path can produce for a pass, a fail, an incomplete and a refusal and matches each one against the tuple.

### Anti-patterns to avoid
- Calling `job.run_once`, `writer.write_run` or `writer.record_failure` anywhere in the phase.
- Reading `latest_rating` or any live table other than the four `psse_*` tables during replay (stored ratings only).
- Comparing `case_sha256` of a run with the hash of `converted_network.json`: different file types, never equal.
- A tolerance flag or a widened tolerance to make a run pass (Out of Scope: "Tuning network parameters to force agreement", and D-12).
- Printing `str(exception)` from a data read or a parse: it can carry an identifier; print a reason word.
- Writing the detailed report anywhere but `data/private/` through `private.py`.

## Don't Hand-Roll

| Problem | Don't build | Use instead | Why |
|---------|-------------|-------------|-----|
| Voltage and flow tolerance | new epsilon logic | `compare.within_voltage`, `within_flow`, `flow_allowance` | One place for tolerances; boundary written in decimal needs the epsilon already there |
| Private file placement and permissions | `open(...)` into a folder | `private.make_private_dir`, `write_private_json` | Refuses paths outside `data/private/`, not git-ignored, symlink escape; owner-only; exclusive create |
| Recorded settings | parsing `report.json` yourself | `engine.load_recorded_backend` | Strict JSON, size cap, placeholder refusal, fail closed |
| Running the study | a second solve loop | `engine.prepare_run(...).study` | Same loops as the hourly job; island, stale-result and fresh-copy handling already proven (02-05) |
| Output safety | ad hoc redaction | closed vocabulary printer plus `psse_job.redaction.redact` for connection failures | A whitelist fails closed, a blacklist leaks |
| Leak detection in tests | custom regexes | `private_leak_scan.derive_needles` and `scan_paths` | Already covers hashes, from-to-circuit keys, scaling targets, long decimals |
| Read-only DB session | `set default_transaction_read_only` | `autocommit = False; read_only = True` | Holds behind a transaction pooler; `supabase_store.begin_read_only` documents why |

**Key insight:** the risk is not computing the replay, it is a false pass (vacuous, quantised, one rating set) and a quiet leak. Every rule above is there to make "pass" mean something and to make output safe by construction.

## Common Pitfalls

### Pitfall 1: The case hash cannot match the way the roadmap implies
**What goes wrong:** the replay is asked to match "by its recorded hash" but `psse_run.case_sha256` is `run_record.file_sha256` of the laptop's `.sav` (`study.prepare_run` hashes the file at `case_path`), while the pandapower network is a converted JSON built from a RAW export. They never match.
**How to avoid:** match `mapping_sha256` against the mapping file bytes (`engine.prepare_run(...).mapping_sha256`), and compare each run's `case_sha256` with the `case_sha256` the Phase 1 session recorded in its manifest, which `cli.py` copies into `report.json` under `session` (cli.py:458-461: the meta keys `case_sha256, mapping_sha256, ...`). Equal means the converted network was exported from the same `.sav` the hourly job used. Different means exclusion `case_hash_differs` for those runs. [VERIFIED: cli.py:458-461 read; whether the values are equal is UNKNOWN until the export runs]
**Warning signs:** all runs excluded; `report.json` has no `session` entry (some `check_*` folders have no `report.json`; pass an explicit check folder or default to the newest one that has it).

### Pitfall 2: Vacuous or thin agreement
**What goes wrong:** 19 runs that share one mapping and a few rating sets are a handful of independent comparisons; thermal and non-converged outages may have no rows at all (the 32 session outages all converged per `01-SESSION-RECORD.md`); "empty equals empty" passes for any solver.
**How to avoid:** report distinct configurations, non-empty comparisons per kind, and "not exercised" for empty kinds; verdict `incomplete` with zero non-empty comparisons; state plainly in the report that thermal agreement rests on NET-03's base-case flows and the fixture matrix when no thermal row exists. NET-03 (base case only) is the strong evidence; this replay is the second line.
**Warning signs:** a pass on the first try; `runs replayed` large but `distinct configurations` 1 or 2.

### Pitfall 3: Mapping or study definition changed since the runs
**What goes wrong:** the session used a COPY of the hourly mapping; if the owner or teammate edited targets or settings between the runs and the session, `mapping_sha256` differs and every run is excluded; if the comparison bypasses the hash it "agrees" with a study PSS/E never ran.
**How to avoid:** hash check is an exclusion, not a warning; no override flag. If every run is excluded, the owner's remedies are outside this phase (one explicit-yes PSS/E run under the current mapping, or the session's own per-outage reference, see Open Questions Q7). Do not exclude by `job_version`; the mapping hash covers the study definition. Print the distinct `job_version` count as information.

### Pitfall 4: Margin quantisation read as disagreement
**What goes wrong:** rating-bound margins move by a whole 25 MW step on a negligible flow difference, so a strict 2% on `margin_mw` fails for the wrong reason; `min_voltage_pu` and `voltage_limit_mva` at that point move with it.
**How to avoid:** the resolution rule above. Evidence: margin.py:120-134 steps `increment = steps * step_mw` and returns the first point whose `max_flow_mva` reaches the rating; bisection (line 138) happens only after a bad point. At least one city was rating-bound in the recorded run per project notes (11-11 run). [ASSUMED: from project notes, not re-read from the database]

### Pitfall 5: Element flips at a limit
**What goes wrong:** a bus at 1.0499 versus 1.0501 flips set membership on noise; strict equality flaps. NET-03 measured agreement near 1e-4 pu on bus voltages (01-SESSION-RECORD.md), so true flips are rare but real.
**How to avoid:** borderline rule (Pattern 4); count and largest excess printed. The band equals the owner's tolerance and is wider than the observed accuracy, so the owner may want it tighter (Q3).

### Pitfall 6: Column that may not exist yet
**What goes wrong:** selecting `solver` fails with "column does not exist" on the live project until the owner applies migration 20261118200000.
**How to avoid:** filter by `run_id like 'psse-%'`; never select `solver`; one test with a fake that rejects any statement naming `solver`.

### Pitfall 7: Placeholder or unrecorded settings
**What goes wrong:** replaying on placeholder settings compares against a study PSS/E never ran (Phase 2 decision: Phase 5 refuses a live write on a placeholder).
**How to avoid:** refuse when `engine.is_placeholder(backend)`; the recorded backend loader already rejects any source starting "placeholder" and an undecided `enforce_q_lims` is refused by `preflight` at stage mapping.

### Pitfall 8: Clock and slot matching
**What goes wrong:** attempting to re-fetch ratings or to align slots between solvers.
**How to avoid:** none needed. The replay uses the ratings stored in the run row, so `slot_time`, `started_at`, `age_minutes` and `server_is_stale` are labels only. `slot_time` is the UTC hour floor of `started_at` (DDL check `psse_run_slot_matches_start_ck`), and two runs in one slot are both replayed. Slot alignment of the two solvers is the gap check's job in Phase 5.

### Pitfall 9: Windows and no Postgres
**What goes wrong:** database tests cannot run on this machine; a skip reads as proof.
**How to avoid:** Postgres-tier tests use `psse_local_pg.require_local_pg` and skip here; with `PSSE_REQUIRE_PG=1` they fail; the plan's SUMMARY states plainly they were only skipped and gives the command for a Postgres host. Everything else (guard, fake, compare, fixture study, output scan) runs here. The real replay on private data runs on this machine because the data is here; the live export needs the writer string on whichever machine runs it. Windows quirks already known: file mode 0o600 assertions and CRLF byte-hash migration tests fail here (STATE and project notes), so do not add new mode assertions without a platform guard.

### Pitfall 10: A replay failure mistaken for an exclusion
**What goes wrong:** a run that PSS/E completed but pandapower refuses (`StudyFailed`) is dropped from the denominator and the check passes on the rest.
**How to avoid:** `StudyFailed` and `ResultsInvalid` on replay are failures of every run in that configuration; only input-mismatch reasons exclude.

## Code Examples

### Borderline and value comparison on a key present on both sides
```python
# Source: backend/pandapower_job/compare.py:83-95
def compare_pair(kind, recorded, replayed):
    if kind == "thermal_overload":
        ok = compare.within_flow(recorded["observed_value"], replayed["observed_value"])
        dev = abs(replayed["observed_value"] - recorded["observed_value"])
        allowance = compare.flow_allowance(recorded["observed_value"])
    else:
        ok = compare.within_voltage(recorded["observed_value"], replayed["observed_value"])
        dev = abs(replayed["observed_value"] - recorded["observed_value"])
        allowance = compare.VOLTAGE_TOLERANCE_PU
    return ok, dev, dev / allowance          # utilisation feeds the largest-deviation headline
```

### The guarded-output test shape
```python
# Source: pattern of backend/tests/pandapower_cli_test.py:102 and :574-590
def test_ci_output_is_counts_only(tmp_path):
    lines = replay.render_ci(summary)                       # list of str
    assert all(any(p.match(line) for p in replay.CI_LINE_PATTERNS) for line in lines)
    out = tmp_path / "ci_output.txt"; out.write_text("\n".join(lines))
    assert private_leak_scan.scan_paths([str(out)], needles=needles, root=str(repo)) == []
    assert tokens_of(lines).isdisjoint(identifier_and_value_needles(recorded, replayed))
    out.write_text("\n".join(lines + [planted_identifier]))   # teeth
    assert private_leak_scan.scan_paths([str(out)], needles=needles, root=str(repo)) != []
```

## State of the Art

| Old approach | Current approach | Impact |
|--------------|------------------|--------|
| Research suggested a single `replay.py` reading the database | Separate export and replay, snapshot file between | Compute path has no connection code; works offline on Windows; "writes nothing" is provable by import scan |
| Strict set equality | Borderline band plus counts | No flapping at limits; the band is printed |
| Bare "agreement passed" | Pass with non-empty counts per kind, "not exercised" for empty kinds | Matches PITFALLS 2.4 and the roadmap's honesty requirement |

**Deprecated or not to use:** a replay path through `job.run_once` (ARCHITECTURE sketch said `study.make_study`; calling the study callable directly is simpler and has no writer in reach).

## Assumptions Log

| # | Claim | Section | Risk if wrong |
|---|-------|---------|---------------|
| A1 | The 19 live runs share one mapping hash and few distinct rating sets | Pitfalls 2 and 3, Pattern 2 | If hashes differ, more exclusions and more distinct configurations; if all differ from the local mapping, the replay is `incomplete` and the owner needs another route (Q7) |
| A2 | The session's recorded `case_sha256` equals the runs' `case_sha256` (same `.sav`) | Pitfall 1 | If not, all runs excluded `case_hash_differs` until the owner decides what a different `.sav` means |
| A3 | The recorded rows contain no thermal and no non-converged rows (all 32 session outages converged) | Pitfall 2 | If they do exist, more of the check is exercised; no harm |
| A4 | At least one city was rating-bound in the recorded run (project notes of 2026-11-11) | Pitfall 4 | If none, the quantisation floor never fires; no harm |
| A5 | Pandapower study cost is about 12 s per four-city study on the real network (measured on the fixture) | Pattern 2 | Longer runs; deduplication still applies |
| A6 | The live database has no `solver` column yet (migration not applied per STATE.md and project notes) | Pitfall 6 | Prefix filter works either way |
| A7 | The resolution floor, borderline band and pass thresholds are acceptable to the owner | What is compared, Q2, Q3, Q5 | The gate's meaning changes; these are owner decisions, not facts |

## Open Questions (RESOLVED)

All seven questions are settled by `04-CONTEXT.md` (the owner's decisions D-01 to D-04 of 2026-11-20 and the defaults taken from this research); the plans in this phase implement those answers. The original text of each question is kept below with its resolution first.

1. **Q1: Which database route?** RESOLVED by D-01 (owner-run SQL export in the Supabase SQL editor; no credential shared, no connection made by the replay; a private snapshot under `data/private/` is the only thing the replay reads). The alternatives below (read-only session through the writer credential, SELECT-only role migration) are not built; a direct read-only connection can be added later. Original question: Recommended: writer connection string in the owner's shell, read-only session plus guard (no new credential, precedent `gaps.run`). Alternative: an additive migration for a SELECT-only login role (database-enforced, one more owner-applied one-way step and a secret). Fallback: an owner-run SQL export in the Supabase editor if the owner prefers no string on the machine. The owner chooses; research recommends the first.
2. **Q2: Margin resolution floor.** RESOLVED by D-02 (margins use `max(2%, stored step or tolerance)`; the floor is printed in the report header; voltages keep 0.01 pu and flows keep `max(2%, 2 MVA)` from `compare.py`). Original question: Allow `max(2%, stored step or tolerance)` for margin quantities, printed in the report header? Recommended yes, because the stored value cannot be more precise than the search. If the owner wants strict 2%, expect rating-bound cities to fail on quantisation.
3. **Q3: Borderline band.** RESOLVED by the default in `04-CONTEXT.md` ("Defaults taken from the research"): the band equals the owner's tolerance (0.01 pu, 2%); a one-sided element within it is borderline, outside it a failure, and any one-sided non-convergence row is a failure; the count and largest borderline excess are reported. Original question: The band equals the owner's tolerance (`0.01` pu, `max(2%, 2 MVA)`). Observed base-case accuracy is about 1e-4 pu, so a tighter band (for example a tenth of the tolerance) is defensible. Recommended: start at the tolerance and print the largest borderline excess.
4. **Q4: Largest deviation in CI?** RESOLVED by D-03 (private report only; CI mode prints counts and pass or fail only, no deviation, not even as a ratio). Original question: AGR-03 wants it on a pass, AGR-04 allows counts and a word only in Actions. Recommended: private report only; CI prints no deviation, not even as a ratio.
5. **Q5: What counts as a gate pass?** RESOLVED by D-04 (at least 1 replayed run, at least 1 non-empty set comparison, no failures; kinds with no recorded rows listed "not exercised"; zero runs or zero non-empty comparisons is "incomplete", not a pass). Original question: Proposed: at least one replayed run, at least one non-empty set comparison, no failure; kinds with zero non-empty comparisons listed "not exercised" and the owner records in the Phase 5 gate decision whether that suffices.
6. **Q6: What do the hashes say?** RESOLVED by the default in `04-CONTEXT.md`: the first export prints counts only (runs by outcome, distinct mapping and case hashes, how many match the local mapping and the session's recorded case hash). Original question: First export prints counts only: runs by outcome, distinct mapping hashes, distinct case hashes, how many equal the local mapping and the session's case hash. Needed before the check can be judged.
7. **Q7: If no run matches the current mapping.** RESOLVED by the default in `04-CONTEXT.md`: such runs are reported as excluded with the reason; the ways to get a matching run (one explicit-yes PSS/E run under the current mapping, or the Phase 1 session's per-outage reference files) are outside this phase and are surfaced to the owner. Original question: Options outside this phase: one explicit-yes PSS/E run under the current mapping (a permanent row, per the standing rule), or compare against the Phase 1 session's per-outage reference files in the private session folder (they exist per city; a stronger full-state check than the database replay, noted as AGR-05 or v2 material). Not recommended to widen Phase 4 unless Q6 forces it.

## Environment Availability

| Dependency | Required by | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Project venv Python | all tests | yes | 3.12.10 (`.venv/Scripts/python.exe`) | none needed |
| pandapower | fixture study, replay | yes | 3.5.6 | none |
| pytest | tests | yes | 9.0.3 | none |
| psycopg | export step | yes | 3.3.6 | none |
| PostgreSQL binaries (`psql`, `pg_ctl`, `initdb`) | database-tier tests | no | none | Postgres-tier tests skip here; run on a host with Postgres |
| Docker | alternative harness | no | none | same |
| Private session data (`data/private/pandapower/`) | owner-local real replay | yes (session folders, `mapping.json`, `converted_network.json` in several `check_*` folders; contents not read) | n/a | owner-local tests skip with an owner-local reason when absent |
| Writer connection string | live export | not probed (no credential used) | n/a | owner provides in own shell; or fallback SQL export |
| numba | speed | no | n/a | slower solves (about 12 s per study measured) |

Only a check folder that holds `report.json` can supply recorded settings (some folders do not). **Missing with no fallback:** none for building and testing; the live export and the real replay are owner steps.

## Validation Architecture

`workflow.nyquist_validation` is absent from `.planning/config.json` (only `workflow._auto_chain_active`, `workflow.use_worktrees` and `graphify.enabled` are set), so validation is enabled.

### Test framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config file | `pytest.ini` at the repo root (`pythonpath = backend`, `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py`) |
| Quick run command | `PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider -rs backend/tests/pandapower_recorded_test.py backend/tests/pandapower_replay_test.py backend/tests/pandapower_replay_output_test.py` |
| Full suite command | quick command plus `pandapower_replay_study_test.py pandapower_replay_pg_test.py pandapower_import_gate_test.py pandapower_compare_test.py pandapower_cli_test.py private_data_guard_test.py` |
| Database tier | `DLR_TEST_PG_AUTOSTART=1 PSSE_REQUIRE_PG=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs backend/tests/pandapower_replay_pg_test.py`, must report 0 skipped, on a host with Postgres |

### Phase requirements to test map
| Req | Behavior | Test type | Automated command | File exists |
|-----|----------|-----------|-------------------|-------------|
| AGR-01 | recording fake: read-only set before first statement, only allow-listed SELECTs, no commit | unit | `pytest backend/tests/pandapower_recorded_test.py -k readonly` | Wave 0 |
| AGR-01 | replay module imports no psycopg, writer, job (AST); replay runs with network and `psycopg.connect` patched to raise | unit | `pytest backend/tests/pandapower_recorded_test.py -k imports` | Wave 0 |
| AGR-01 | stored ratings rebuilt exactly; hash match groups runs; hash mismatch excludes with reason | unit | `pytest backend/tests/pandapower_replay_test.py -k plan` | Wave 0 |
| AGR-01 | tables unchanged after export; insert refused with 25006; SELECT-only role works | database | `pytest backend/tests/pandapower_replay_pg_test.py` | Wave 0, skips here |
| AGR-02 | comparison matrix: same, one-sided borderline, one-sided fail, value fail, convergence fail, margin resolution, dispatch | unit | `pytest backend/tests/pandapower_replay_test.py -k compare` | Wave 0 |
| AGR-02 | self-replay of a stand-in recorded run on the public fixture passes with non-empty counts | integration (real solver) | `pytest backend/tests/pandapower_replay_study_test.py -k self` | Wave 0 |
| AGR-03 | report counts, per-kind non-empty counts, "not exercised", largest utilisation on a pass, exclusions with reasons | unit | `pytest backend/tests/pandapower_replay_test.py -k report` | Wave 0 |
| AGR-03 | deliberate mismatch matrix fails; tolerance-edge perturbations pass (teeth both sides); zero replayed or zero non-empty is incomplete | integration | `pytest backend/tests/pandapower_replay_study_test.py -k mismatch` | Wave 0 |
| AGR-04 | every CI line matches the closed vocabulary; no file written in CI mode; `GITHUB_ACTIONS=true` forces CI mode | unit | `pytest backend/tests/pandapower_replay_output_test.py` | Wave 0 |
| AGR-04 | leak scan over CI output finds nothing; planted identifier is found | unit | `pytest backend/tests/pandapower_replay_output_test.py -k leak` | Wave 0 |
| all | owner-local replay of the real snapshot reports counts only (skips without private data; fails with `DLR_PANDAPOWER_REQUIRE_RECORDS=1`) | owner-local | same file, `-k owner_local` | Wave 0 |

### Sampling rate
- Per task commit: the quick run command (pure tier, a few seconds; the real-solver file adds about 12 s per study, use a module-scoped study).
- Per wave merge: the full suite command (pure tier) here, then the database tier on a Postgres host.
- Phase gate: pure tier green here; database tier green with 0 skipped on a Postgres host, or the SUMMARY states plainly it was only skipped and gives the command. Then the owner-local replay on the real snapshot, recorded as a decision for the Phase 5 gate.

### Wave 0 gaps
- [ ] `backend/pandapower_job/recorded.py`, `replay.py`, `backend/pandapower_replay.py`
- [ ] the five test files above and a stand-in helper in `backend/tests/pandapower_study_fixture.py`
- [ ] `pandapower_import_gate_test.py` extended or a sibling test for the replay module's import list
- [ ] a leak-scan teeth fixture (synthetic private tree under `tmp_path`, as `private_data_guard_test.py` builds)
- [ ] no framework install needed

## Security Domain

`security_enforcement` is absent from the config, so it is enabled.

### Applicable ASVS categories
| ASVS category | Applies | Standard control |
|---------------|---------|------------------|
| V2 Authentication | yes (database credential) | connection string only from the environment, never logged; `psse_job.redaction.redact` and `env_secrets` on every failure line |
| V4 Access control | yes | least privilege: read-only session now; optional SELECT-only role (Q1); never `service_role` or a secret key |
| V5 Input validation | yes | strict snapshot parsing (size cap, no NaN or duplicate keys, marker key, as `engine._read_document` does); `ratings_used` validated field by field; hashes matched with `[0-9a-f]{64}` |
| V6 Cryptography | no | hashes are identity checks only, sha256 already in use |
| V7 Logging | yes | closed-vocabulary output; no `str(exception)` of data; counts and a verdict word in CI |
| V8 Data protection | yes | snapshot and report only under git-ignored `data/private/` through `private.py`; marker key for the shape layer; detail never written in CI mode |
| V12 Files | yes | `private.require_private` blocks outside paths and symlink escape; exclusive create |
| V14 Configuration | yes | tolerances in code constants printed in the private report header, not flags |

### Known threat patterns for this stack
| Pattern | STRIDE | Standard mitigation |
|---------|--------|---------------------|
| Replay writes to the live tables | Tampering | no connection in compute path, read-only session, statement allow-list, 25006 proof |
| Credential or connection detail in a log or error | Information disclosure | redaction plus closed vocabulary; connection failure prints one reason word |
| Private identifiers or study values in a public Actions log | Information disclosure | CI mode counts only, no file in CI, leak-scan test with planted teeth |
| SQL injection | Tampering | fixed statement texts, bound parameters only |
| Tampered snapshot or private path trick | Tampering | marker and strict parse; private path guard; hashes compared before use |
| Overly powerful credential | Elevation of privilege | writer role only; SELECT-only role optional; service role refused |
| A false pass used as the go-live gate | Repudiation | pass needs non-empty comparisons, `incomplete` is not a pass, exclusions always listed |

## Sources

### Primary (HIGH, files read this session)
- `.planning/workstreams/pandapower-solver/ROADMAP.md`, `REQUIREMENTS.md`, `STATE.md`, `research/ARCHITECTURE.md` (section 5), `research/PITFALLS.md` (Pitfall 2), `research/FEATURES.md` (comparison rules), `research/SUMMARY.md`
- Phase 1 to 3 summaries, `01-SESSION-RECORD.md` (counts only), `03-CONTEXT.md`, `03-05-SUMMARY.md`, `02-07-SUMMARY.md`
- `backend/pandapower_job/engine.py`, `compare.py`, `api.py`, `private.py`, `cli.py` (vocabulary and exit codes), `convert.py`
- `backend/psse_job/study.py`, `run_record.py`, `ratings.py`, `contract.py`, `constants.py`, `job.py`, `writer.py`, `gaps.py`, `contingency.py`, `violations.py`, `margin.py`, `dispatch.py`
- `supabase/migrations/20261109233541_psse_results.sql`, `20261118200000_psse_run_solver_tag.sql`; `docs/data-science/decisions/psse_study_definitions.md`, `pandapower_network_data_decision.md`; `docs/data-science/schema/psse_run_gaps.sql`
- `backend/private_leak_scan.py`; tests `pandapower_study_fixture.py`, `pandapower_engine_recorded_test.py`, `pandapower_import_gate_test.py`; `psse_local_pg.py`; `psse_gaps_pg_test.py`
- A probe study on the public fixture run this session in the scratchpad (counts reported above); file names under `data/private/pandapower/` listed, no content read

### Secondary (MEDIUM)
- psycopg 3 connection API: read_only definition [CITED: https://www.psycopg.org/psycopg3/docs/api/connections.html]; the page does not state when it applies in autocommit mode, so that behaviour rests on `gaps.py:149-153` and `psse_gaps_pg_test.py`

### Tertiary (LOW)
- Project memory notes of the 11-11 real runs (rating-bound city, run count and hours); not re-verified against the database

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH, no new package, versions imported this session
- Architecture: HIGH for the seams (read), MEDIUM for the borderline and resolution rules (design judgement awaiting owner confirmation)
- Pitfalls: MEDIUM, several depend on the unread live corpus (A1 to A4)

**Research date:** 2026-11-20
**Valid until:** 2026-12-20, or until the owner reads the recorded runs, whichever is first
