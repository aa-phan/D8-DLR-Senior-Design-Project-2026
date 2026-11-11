# Phase 4: Per-city scaling of the 39-bus case - Research

**Researched:** 2026-11-09
**Domain:** PSS/E (`psspy`) whole-case scaling, per-city case copies inside the existing `backend/psse_job` study, run-record and failure semantics
**Confidence:** MEDIUM overall. HIGH on where the code changes and what pins it (read this session). LOW on the exact `psspy` scale-to-target argument layout: only community forum posts were reachable, the vendor manual was not, so that one item is gated behind a short laptop check.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **One network, one case copy per city.** The IEEE 39-bus system stands in for each city. The job takes a fresh copy of the base case for each city, scales it to that city's targets, then runs the existing study on it. The four cities are four independent load flows; no city's scaling touches another's solve. (The user's concern was cross-talk if the cities were areas of one case; this design avoids that by construction.)
- **Scaling targets are data in the mapping.** Per city: a target net load (MW), a target generation (MW), and the load reactive target (Mvar) that the recorded scale step also carries. The job applies them through its own scaling call. It does not run the `.idv` files: they are GUI-recorded scripts, and executing script files named in a config is a risk the job has so far avoided.
- **What the recorded scale step does** (read from PSS/E's own dialog for one city's script): it sets the case's net load to the first number and its generation to the second, and the last number is the load Mvar. The base case's own totals are read from PSS/E's totals report on the laptop and are not recorded here.
- **Basis of the targets: average load** for the three cities that have files. Record the basis (average or peak) next to every city's targets in the mapping.
- **El Paso has no scaling file yet.** Proposal: scale it on its average load from the EIA-861 sales table (2025, utility 5701, retail MWh divided by 8,760 h; 2024 gives the same to within 0.1%), generation set from the same load-to-generation ratio the other cities use. Fallback if the user prefers: its peak, labelled as a placeholder. To be confirmed by the user and Power Systems.
- **The same lines can map in every city's copy** (to be confirmed with Power Systems); only the scaling differs.
- **The case must be unconverted** (a converted dynamics case fails the load flow with `fnsl ierr 2`). The free Xplore edition allows at most 50 buses.

### Claude's Discretion
None stated in CONTEXT.md. The four "Open questions for planning" are the research targets; they are answered below, with a recommendation each.

### Deferred Ideas (OUT OF SCOPE)
Real Power Systems mapping and case review (Phase 3, step 7); the real proof write (Phase 3, step 9); changing the task XML encoding.
</user_constraints>

<phase_requirements>
## Phase Requirements

REQUIREMENTS.md has no entries for this phase (ROADMAP: "Requirements: TBD"). These are proposed; the planner adds them to REQUIREMENTS.md and the Traceability table.

| ID | Acceptance statement (one line) | Research Support |
|----|----------------------------------|------------------|
| SCL-01 | Mapping `schema_version` 2 carries, for every city, a scaling block (target net load MW, target generation MW, target load Mvar, basis label `average` or `peak`); a missing, non-finite, non-positive (load, generation) or unknown-basis value fails the run at stage `mapping` before any case write, and the same branch may be listed under more than one city. | "Mapping schema v2"; pitfalls 4 and 5 |
| SCL-02 | For each city the job loads the base case file afresh, scales the whole case to that city's targets with its own `psspy` call (never executing a `.idv` or any script named in configuration), reads the totals back and fails that city when they miss the targets by more than a stated tolerance. | "The scaling call"; Pattern 1 |
| SCL-03 | Each city's rating write, base solve, N-1 screen, margin search and dispatch row run on that city's own scaled copy; the other cities' scaling, ratings and outages are absent from that solve. | Pattern 2; Validation rows 3 and 4 |
| SCL-04 | One city's failure (scaling, load flow, margin, dispatch) does not stop the other cities from being attempted; the run is recorded `failed` with one error text that names every city's outcome and no result rows are written (WB-02 unchanged). | "Failure behaviour today and what changes" |
| SCL-05 | Per-city contingency rows stay unique and attributable with no change to the live tables (the contingency id carries the city), `n_contingencies` counts every city's screen, each dispatch and margin row's `details` records the scaling basis and method, and no real city figure is written to the repository, a log line, an error text or the database. | "Result tables and run record"; Security Domain |
| SCL-06 | The scale call is proven on the real PSS/E 36.4 laptop: a probe write-check row passes (layout accepted, totals read back at the targets, reload restores the totals) and a dry run on the 39-bus case with placeholder targets completes for four cities. | Validation Architecture, laptop-only list |
</phase_requirements>

## Summary

Today the study is one case for all four cities. `make_study` builds one `BaseCase` (all four cities' ratings written into one in-memory case, one load flow, one saved base, one N-1 screen over the union of the four neighbourhoods, one margin search per city on that same saved base). Phase 4 turns that into a loop of four independent studies on four fresh loads of the same case file, each scaled to its own targets first. The pieces that already exist and are reused unchanged: the unconverted-case rule, `check_mapping` (run once, on the unscaled case, before any write), `apply_ratings` (restricted to the one city), `solve_base`, `contingency.screen`, `margin.city_margin`, `dispatch.build_dispatch_row`, `job.run_once`, the writer and the DDL. `scal_2` is already in `psse_api.SURFACE` and its increment form is proven on the real laptop, so the scaling is an extension of a proven path, not a new function name, unless the laptop shows the recorded `BAT_SCAL_4` has a different layout that matters.

The decisive findings: (1) **No schema migration is needed.** Everything per-city fits existing columns: dispatch and margin rows are already keyed `(run_id, city)`; the contingency primary key has no city, so the city goes into the `contingency_id` text (a prefix) which keeps keys unique and the owner's live completeness checks green; the scaling record goes into the free-form `details` jsonb of the dispatch and margin rows; `mapping_sha256` already covers the targets. The DDL region is sha256-pinned and applied live, so touching it is out of this repo's control. (2) **The failure stage vocabulary is DDL-checked and has no "scaling" stage.** A scaling failure must be raised as an existing stage (`apply_ratings` for the scale call and its read-back, `load_flow` for a scaled base that does not converge, `mapping` for bad targets). (3) **"One city failing must not hide the other three" can be met without a migration only as diagnostics, not as partial results.** WB-02, the DDL (`outcome` is only `ok`, `fallback` or `failed`; result rows cannot point at a failed run) and the owner's live checks (`non_failed_runs_have_four_dispatch_rows`) all require four rows for any non-failed run. So the recommended behaviour is: attempt all four cities, then fail the run once with an error text that names each city's outcome. Writing the three good cities' rows (a "partial" run) needs the data owner's additive migration and a change to WB-02; it is listed as a user decision, not planned. (4) **The exact scale-to-target call layout is not confirmable from public sources** and must be read off the laptop (the `psspy` docstring or a GUI re-record with placeholder numbers) before the adapter method is finalised.

**Primary recommendation:** Add `PsseApi.scale_case(...)` (reusing the `scal_2` SURFACE row, whole case, `all=1`, "new total" mode, `_f` for untouched slots) plus a totals read-back; run `make_study` as a per-city loop (fresh `case()` load, scale, that city's ratings, solve, private temp save, screen, margin, dispatch) that collects failures and raises one combined `StudyFailed`; carry the city in `contingency_id` and the scaling basis in `details`; bump the mapping to `schema_version` 2 with a required per-city `scaling` block; gate finalising the call layout behind one laptop task.

## Architectural Responsibility Map

The "tiers" here are the places this job runs, not web tiers.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Per-city scaling targets (data) | Private mapping file on the laptop (`PSSE_MAPPING_PATH`) | none | Real city figures never enter git; the file is parsed with `json` only, never executed |
| Parse and validate the targets | `psse_job/mapping.py` (job process) | none | Existing validator; fails at stage `mapping` before any case write |
| Whole-case scale call and totals read-back | `psse_job/psse_api.py` (the only module naming `psspy` functions) | PSS/E engine (`psspy`) | One gate to `psspy` with a SURFACE row; the engine does the arithmetic |
| Fresh copy per city | `psse_job/study.py` (reload the case file with `case()`) | PSS/E engine holds the in-memory case | A reload is the only "copy" PSS/E offers in-process; the case file is never saved over |
| Per-city load flow, N-1, margin | PSS/E engine, driven by `study.py`, `contingency.py`, `margin.py` | none | Unchanged algorithms on a different case per city |
| Combine four cities into one result or one failure | `psse_job/study.py` (aggregation) then `job.run_once` | none | `run_once` stays one study call and one write |
| Result storage | Supabase `psse_*` tables via `writer.py` (unchanged) | none | Live DDL; no change in this phase |
| Real-engine proof of the call layout | Teammate's licensed laptop | none | PSS/E and its licence exist only there |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python standard library only | job code uses Python 3.7 syntax (D-05); laptop runs 3.14.0 | Everything in `backend/psse_job/` | `[VERIFIED: backend/psse_job/study.py:18]` module docstring "Standard library and psse_job only, Python 3.7 syntax (D-05)." |
| `psspy` (PSS/E 36.4, free Xplore edition) | 36.4 | The engine; reached only through `psse_api.PsseApi` | `[VERIFIED: 03-07-LAPTOP-RECORD.md]` "PSS/E \| 36.4, free Xplore edition; the banner reads "50 BUS POWER SYSTEM SIMULATOR"" |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest (repo `.venv`) | as installed in `.venv` | Tests against the fake psspy | `[VERIFIED: ran this session]` `.venv/Scripts/python.exe -m pytest` on seven psse test files: "255 passed, 24 skipped in 25.83s" |
| `backend/tests/psse_fake_psspy.py` (`FakePsspy`) | in repo | Fake `psspy` implementing exactly `SURFACE` | Every behaviour test for this phase; must be extended (see Validation Architecture) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| One `scal_2` call in "new total" mode | A new `scal_4` SURFACE row (the recorded `BAT_SCAL_4` suggests PSS/E 36 has one) | Only if the laptop shows `scal_2` cannot express the recorded step (for example the load Mvar target). `scal_4` is unconfirmed in any public source I could reach. Adds an UNVERIFIED row and a probe signature check. |
| `scal_2` target mode | Compute increments from base totals, then use the laptop-proven increment form twice | Needs the base totals from a bulk read whose call names are also unconfirmed; generation increments are not the proven form either. No saving. |
| Per-city copy by reload (`case()`) | Subsystem or area scaling inside one case | Rejected by the user's locked decision (cross-talk by construction). |
| All-or-nothing failure with a combined message | Partial run (rows for the good cities) | Needs a data-owner migration and an amendment of WB-02; see Open Question 1. |

**Installation:** none. No external package is added by this phase.

**Version verification:** not applicable (no new package). The `psspy` version is the laptop's 36.4 per the record above.

## Package Legitimacy Audit

No external packages are installed or added by this phase. Packages removed due to SLOP verdict: none. Packages flagged SUS: none. The planner needs no `checkpoint:human-verify` install gate.

## Architecture Patterns

### System Architecture Diagram

```
 hourly task / dry run
        |
        v
 launcher._run_mode / _dry_run_mode --> study.prepare_run(psspy, case_path, mapping_path)
        |                                   |
        |                       mapping.load_mapping  (schema v2: per-city branches + scaling)
        |                                   | bad file -> failing_study("mapping")
        v                                   v
 job.run_once --select_ratings--> study(selection, context)          [make_study]
                                      |
        (1) PsseApi(psspy, protected_path=case_path); load case ONCE for the index
            branch_table / bus_table / check_mapping(all four cities)   --problems--> StudyFailed("mapping")  (IN-02, no write yet)
                                      |
        (2) for city in AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO:        (each city independent)
            +--------------------------------------------------------------------------+
            | api.load_case(case_path)            fresh copy of the unconverted base    |
            | api.scale_case(targets[city])       whole case, then totals read-back     |
            |      scal_2 error / read-back miss  --> city failure, stage apply_ratings |
            | apply_ratings(only this city)       write MVA, read back (existing)       |
            | solve_base                          not converged --> stage load_flow     |
            | save <tempdir>/<city>.sav           private; never the case file          |
            | contingency.screen(city base, id prefix "<CITY>:")                        |
            | margin.city_margin(city base, city)                                       |
            | dispatch.build_dispatch_row(...)    details += scaling record             |
            +--------------------------------------------------------------------------+
            except StudyFailed: remember (city, stage, message); continue with next city
                                      |
        (3) any city failed? --yes--> ONE StudyFailed(first failed stage, combined message naming all four)
                             --no---> StudyResults(4 dispatch, 4 margin, all contingency rows, n_contingencies = sum)
                                      |
                                      v
        job.run_once: validate_results -> build_run_record -> writer.write_run (one transaction)
                      or failure -> record_failure (psse_run alone, outcome failed, no result rows)
```

### Recommended Project Structure
```
backend/psse_job/
├── mapping.py       # SCHEMA_VERSION 2, Scaling namedtuple, CityMapping.scaling, per-city duplicate rule
├── psse_api.py      # scale_case(...) and read_totals(...) beside scale_load; SURFACE row scal_2 reused
├── study.py         # per-city loop in make_study; prepare_city_base (or prepare_base(city=...)); aggregation
├── contingency.py   # screen(base, id_prefix="") : prefixed contingency_id, raw key still used for skip_key
├── dispatch.py      # dispatch_details(..., scaling=None) adds the scaling record
├── margin.py        # margin details gets the same scaling record (optional)
└── probe.py         # new write-check row scale_to_target (placeholder-safe: scales from the case's own totals)
backend/tests/
├── psse_fake_psspy.py          # extend: generators in FakeCase, scal_2 target and init modes, totals
├── psse_scaling_test.py        # NEW: api layout, mapping block, per-city loop, failure aggregation
└── data/psse_call_surface.json # regenerate deliberately (PSSE_UPDATE_CALL_SURFACE=1)
docs/data-science/schema/psse_mapping_example.json   # v2 with placeholder scaling blocks
docs/data-science/decisions/psse_study_definitions.md # new section; psse_study_doc_test REQUIRED_HEADINGS follows
```

### Pattern 1: The scaling call (whole case, new-total mode)

**What:** One `scal_2` call on the whole case that sets total load to the first target and total generation to the second, then a totals read-back before the solve.

**Evidence and confidence (be explicit):**
- Proven on the laptop, this repo: the increment form for a subsystem. `[VERIFIED: backend/psse_job/psse_api.py:488-490]`
  ```
  "scal_2", sid=sid, all=0, apiopt=0, status=[self._int_sentinel, 3, 0, 1, 0],
  scalval=[increment, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
  ```
  and `[VERIFIED: 03-07-LAPTOP-RECORD.md]` "U11 the combined `scal_2` form (`scale_load` PASS with the write check)". What this proves: the call is accepted, `result[0]` is the plain int `ierr`, status index 1 equal to 3 is an increment, and `scalval[0]` is the load MW. It does not prove generation, new-total mode or the Mvar slot.
- Community only (LOW): the same function in new-total mode, from a psspy.org answer on a PSS/E sample case whose total load went from 3200 to 3400 MW: `psspy.scal_2(0,1,2,[_i,1,0,1,0],[ 3400.0, 3258.7,0.0,-600.0, 950.0,-.0, 1950.0])` with `all=1` and status index 1 equal to 1, next to the increment answer `psspy.scal_2(0,1,2,[_i,3,0,1,0],[ 100.0,0.0,0.0,0.0,0.0,0.0,0.0])`. `[CITED: psspy.org/psse-help-forum/question/1720 - community forum, not the manual; confidence LOW]`. Reading: status index 1 is the mode (1 new total, 2 percent, 3 increment: also stated in `[CITED: psspy.org/psse-help-forum/question/2551 - community forum, LOW]`), `scalval[0]` the load MW, `scalval[1]` plausibly the generation MW (3258.7 looks like that case's generation total), and `_f` placeholders leave a quantity unchanged `[CITED: psspy.org/psse-help-forum/question/6830 - community forum, LOW]`.
- The Mvar slot: forum text says that with status index 3 equal to 1 ("constant P/Q") the seventh scale value has no effect (`[CITED: psspy.org search results, community, LOW]`). If true, the recorded step's last number (load Mvar) is ignored under constant P/Q and Q simply follows P at the base ratio. Whether the recorded step used constant P/Q is unknown. See Open Question 2.
- `scal_4`: the recorded step is `BAT_SCAL_4`. I found no public documentation or example of a `psspy.scal_4` function (several searches returned only `scal`, `scal_2`, `scal2`). Whether it exists in 36.4 and what its layout is `[ASSUMED]`.
- Totals layout (for the read-back): two forum answers agree on zero-based `totals[1]` = total load MW and `totals[2]` = total generation MW from an `apiopt=1` initialise call (`[CITED: psspy.org/psse-help-forum/question/4673 - community forum, LOW]`); the Mvar index is not stated.

**Recommended adapter shape (a sketch; layout values are the LOW-confidence ones above and are finalised only after laptop task L1):**
```python
# psse_job/psse_api.py, beside scale_load. Placeholder numbers only.
def scale_case(self, load_mw, gen_mw, load_mvar=None):
    """Set the whole case's total load and total generation (scal_2, all buses, new-total mode)."""
    for name, value in (("load_mw", load_mw), ("gen_mw", gen_mw)):
        if not _is_number(value) or not math.isfinite(value) or not value > 0:
            raise ValueError("%s must be a finite number above 0" % name)
    f = self._real_sentinel                       # "no input": leaves a quantity unchanged
    result = self._call(
        "scal_2", sid=0, all=1, apiopt=0, status=[self._int_sentinel, 1, 0, 1, 0],
        scalval=[float(load_mw), float(gen_mw), f, f, f, f, f])   # layout: UNVERIFIED until L1
    if not isinstance(result, (tuple, list)) or not result:
        raise PsseCallError("scal_2", None, _SHAPE)
    ierr = self._plain_ierr("scal_2", result[0])
    if ierr != 0:
        raise PsseCallError("scal_2", ierr, _NOT_LISTED)
```
`sid` is ignored by PSS/E when `all=1` (manual semantics assumed `[ASSUMED]`); the adapter's `_subsystem_id` check is not needed for it. A read-back method (`read_totals`, an `apiopt=1` call with the same arrays and zeros) returns `(load_mw, gen_mw)` for the guard below. Whether the totals come back before or after the change in each mode is part of L1.

**Run-time guard (recommended, `[ASSUMED]` tolerance):** immediately after the scale call and before the solve, read the totals and require each within a relative 1e-3 of its target, else `StudyFailed("apply_ratings", ...)` for that city. Before the solve, because the solve moves the swing machine and the voltage-dependent load components, so post-solve totals legitimately differ. The message must name no figure (Security Domain). Add a sanity bound on the implied scale factor (for example outside 0.05 to 20 times the case's own totals) to catch a kW-for-MW typo; the bounds are an `[ASSUMED]` default.

### Pattern 2: Per-city loop with collected failures

**What:** `make_study` stops being "prepare one base, then screen and margin all cities" and becomes "index and check once, then for each city: fresh load, scale, rate, solve, save, screen, margin, dispatch".

**Where it slots into the current flow** (all line numbers read this session):
- `study.make_study.study` (`study.py:357-384`) today: `prepare_base` once (`:359`), `contingency.screen(base)` once (`:361`), `[margin.city_margin(base, city) for city in constants.CITIES]` (`:362`), dispatch loop (`:363-374`), `cleanup_base(base)` in `finally` (`:382-383`).
- `study.prepare_base` (`study.py:262-309`) today, in order: build `PsseApi` with `protected_path=case_path` and `load_case` (`:269-271`), `branch_table`/`bus_table` (`:272-273`), `check_mapping` for all four cities (`:277`, fails as `mapping`), `study_area` (`:281`), `apply_ratings` for all four cities (`:282`), `solve_base` (`:283`), post-solve reads and the collapse guard (`:285-293`), `mkdtemp` and `api.save_case` to `base.sav` (`:294-305`).
- New order inside the per-city step: `load_case` (fresh) then `scale_case` then read-back then rate (that city only) then solve then reads and collapse guard then save to a per-city file then screen, margin, dispatch. The scale call is a case write, so it must come after `check_mapping`: the existing test `test_check_missing_branch_fails_before_any_write` asserts `_writes(fake) == []` for a mapping failure (`psse_study_test.py:154-160`, where `_writes` counts `branch_chng_3`, `fnsl`, `save`, `bsys`, `scal_2`).
- `run_once`, the launcher run mode and the dry run (`launcher._dry_run_mode`) do not change shape: one `study(selection, context)` call returns one `StudyResults` or raises one `StudyFailed`.

**Reuse with the least churn:** every helper that loops `constants.CITIES` (`apply_ratings`, `study_area`) needs to accept a one-city view: pass `{city: resolved[city]}` and `sinks={city: ...}`; `study_area` already tolerates missing cities (`resolved.get(city, ())`). `violations.city_maps(base.cities)` then maps mapped branches and their end buses to the case's own city only. Keep `prepare_base`'s current signature working (it is called by `psse_contingency_test.py` and `psse_margin_test.py`, 2 uses each, and ten times in `psse_study_test.py`) by adding a keyword (`city=None`) or by adding `prepare_city_base` that shares the helpers; the production path passes the city. Retire the four-cities-in-one-case mode only in a final cleanup plan, together with the tests that pin it.

**Adapter reuse:** one `PsseApi` for the whole study is fine (a new one per study is what `test_full_study_new_adapter_per_run` pins: two study calls make two adapters, `psse_study_test.py:635-650`). A reload with `case()` is the fresh copy; `margin.evaluate` and `contingency.screen` already rely on a reload resetting in-memory edits (the probe's `rating_write` row proves a rating change is undone by reloading, `[VERIFIED: probe.py:254-256]`). That reload also undoes a `scal_2` change is the same assumption, `[ASSUMED]` MEDIUM, and the L1 check proves it (totals after reload equal totals before scaling).

**Temp files:** one private directory per run (as today, `tempfile.mkdtemp(prefix="psse_job_")`), one `<city>.sav` per city, removed in `finally` on every path (the tests assert `os.listdir(tempfile.gettempdir()) == []` after success and after failure).

**Budget:** keep the single run-wide `Budget` (default 1500 s, `settings.max_runtime_seconds`) shared by all four cities. When it is exhausted the remaining cities should be reported as "not attempted: run-time budget" rather than four identical budget errors.

### Pattern 3: Aggregated failure, still all-or-nothing

Collect `(city, stage, message)` per failed city (cities that never ran are listed too), then raise one `StudyFailed`. Stage: the stage of the first failed city in `constants.CITIES` order. Message: a header ("2 of 4 cities failed") then one clause per city in order, each clause cut to a fixed share of the 1000-character `error` limit (`constants.ERROR_MAX_CHARS`, redacted and cut after redaction by `run_record._error_text`), and every city named, including the ones that succeeded ("MIDLAND: ok"). `job.run_once` already turns any `StudyFailed` into one failed `psse_run` row (`job.py:101-105`, `:122-124`) and `ratings_used` is still written for all four cities (`run_record._ratings_used` with `results=None`).

### Anti-Patterns to Avoid
- **Executing the recorded `.idv` or any script named in configuration.** Locked out by CONTEXT. The job parses numbers from JSON only.
- **Scaling inside one shared case** (area or subsystem scaling). Rejected by the user; also reintroduces cross-talk.
- **Solving between the scale call and the rating write** to "check" the scaling: one solve per city, after both writes.
- **Reading back totals after the solve** and comparing them to the targets: the swing machine and voltage-dependent load change at the solve, so the comparison would fail on a correct scaling.
- **Adding a `scaling` failure stage.** `failed_stage` is a DDL CHECK list; a new value is rejected by the live table.
- **Putting target numbers into error texts, log lines, dry-run output, `details` or comments.** They are real city figures.
- **Relaxing `validate_results` to accept three cities' rows.** That is the partial-run decision, not a refactor.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Scaling arithmetic (per-bus factors, P/Q ratio, machine limits) | A Python loop over loads and machines with `load_chng`/`machine_chng` | PSS/E's own scaling activity through `scal_2` | Constant-P/Q handling, in-service filters and machine limits are the engine's; custom code adds uncalled-for unverified calls |
| Copying the case | `shutil.copy` of the case file, or `save` of a scaled case over it | Reload with `psspy.case(case_path)`; temp saves only under the private temp directory | `PsseApi.save_case` already refuses the protected case path; `CaseProtected` exists for that |
| Numeric and range validation of the mapping | New ad-hoc checks in the study | The existing `mapping.py` problem-list pattern (`check` helpers, `MappingError` with every problem at once) and `settings._real` style | One reporting path; tests already iterate it |
| Redaction of error and log text | A new scrubber | `run_record._error_text`, `redaction.redact`, `launcher._scrub_paths` (already applied to the dry-run failure line) | Existing, tested; the only new rule is "no figures in messages" |
| Run record, atomic write, idempotency | A per-city run or per-city record | `job.run_once`, `writer.write_run` | One study call, one record; unchanged |
| A new place to store per-city scaling | A new table or column | `details` jsonb on dispatch and margin rows; `mapping_sha256` | The live DDL is pinned and applied by the owner |

**Key insight:** the phase is plumbing around an engine call that already exists and a loop that already exists in pieces. Most risk is in what the tests and the live schema pin, not in new algorithms.

## Mapping schema v2 (answers question 2, the mapping part)

Current state `[VERIFIED: backend/psse_job/mapping.py:23, :39-41]`: `SCHEMA_VERSION = 1`, `_TOP_KEYS = ("schema_version", "placeholder", "note", "cities", "study")`, `_CITY_KEYS = ("branches", "sink_buses", "transfer_max_mw")`, `CityMapping = collections.namedtuple("CityMapping", ["city", "branches", "sink_buses", "transfer_max_mw"])`. An unknown city key is a problem (`"%s.%s: unknown key"`), and a branch listed under two cities is refused: `if normal in seen:` ... `"%s.branches[%d]: branch %s is already listed under %s"` (`mapping.py:126-133`), with `seen` shared across cities (`parse_mapping`, `seen = {}` before the city loop).

Recommended v2:
- `SCHEMA_VERSION = 2`; accept only 2. A version 1 file is refused with a message that says per-city scaling is required (no real mapping exists yet, so there is nothing to migrate in git).
- New required city key `scaling`, an object with exactly: `load_mw` (finite, above 0), `gen_mw` (finite, above 0), `load_mvar` (finite, any sign, capped at a sanity bound), `basis` (`"average"` or `"peak"`), and optional `provisional` (true or false, default false, for the El Paso placeholder case; recorded in `details`, never a refusal). Unknown keys are problems. Names are the planner's to adjust; the contents are fixed by CONTEXT (net load MW, generation MW, load Mvar, basis).
- `CityMapping` gains a `scaling` field (a new `Scaling` namedtuple). `_replace(...)` call sites in tests keep working; the only positional construction is `mapping.py:175`.
- Duplicate rule: keep "listed twice within one city" (and the reversed-orientation duplicate), drop "already listed under another city". Reason: each city is solved on its own copy, so the same line in two cities cannot collide. This is Power Systems' to confirm (CONTEXT); until then it is a recommendation.
- The scaling block is part of the file's bytes, so `mapping_sha256` changes with any target. That is the audit trail (see next section).
- Placeholder example `docs/data-science/schema/psse_mapping_example.json` becomes v2 with four clearly fake blocks, `placeholder: true`, same fake 9xxxx buses. Numbers must be placeholders chosen against the fake network (its four sink loads total 4 x 620 MW), not any real figure.

## Result tables and run record (answers question 4)

No migration is needed. Evidence (all read this session):

| Need | Where it fits today | Quote or source |
|------|---------------------|-----------------|
| Which city a dispatch or margin row belongs to | Already a key column | DDL: `constraint psse_dispatched_capacity_pk primary key (run_id, city)` and `constraint psse_voltage_margin_pk primary key (run_id, city)` |
| Which city's copy a contingency row came from | The contingency primary key has no city: `constraint psse_contingency_result_pk primary key (run_id, contingency_id, violation_kind, element_id)`. Identical lines in four copies would collide on this key and `validate_results` also refuses a repeated `(contingency_id, violation_kind, element_id)` (`run_record.py`, "contingency row %d repeats the key %r"). So put the city in the `contingency_id` text (1 to 200 characters): `AUSTIN:90001-90002-1`. For `non_convergence`, `element_id` must equal `contingency_id` (DDL `kind_shape_rule_ck`), so both carry the prefix; for thermal and voltage rows `element_id` stays the raw branch or bus id. | `psse_results_v1.sql` |
| The count identity | `n_contingencies_with_results` is the number of distinct `contingency_id`; the live check `non_failed_runs_contingency_count_matches` compares it with the distinct ids in the rows. With prefixed ids both sides count per-city contingencies separately; `n_contingencies` becomes the sum over the four screens. | `psse_results_v1_checks.sql:13-15`; `run_record.build_run_record` |
| The `city` column of a contingency row | Today "the city whose mapped branch this is; NULL for other elements" (`violations.city_maps`). In a per-city copy it can stay as is (the case's own city for its mapped branch). | DDL column comment |
| Scaling record per city | `details` jsonb of the dispatch row (`dispatch.dispatch_details`) and of the margin row: add `scaling` with the basis, a `method` label and `provisional`. The DDL only requires `jsonb_typeof(details) = 'object'`. | DDL `psse_dispatched_capacity_details_ck`; `psse_voltage_margin_details_ck` |
| Audit of the targets | `mapping_sha256` is the sha256 of the exact bytes parsed, "the one recorded mapping_sha256 then covers every number that shaped a result" | `[VERIFIED: backend/psse_job/settings.py:7-9]` |
| Base case identity | One `case_id` and `case_sha256` for the run (all four copies are the same file) | `run_record.build_run_record` |

What the data owner would have to do only if the project later wants a queryable column (for example `case_city` or `scaling_basis`, or `city` inside the contingency key): an additive migration, because the reference DDL region is sha256-pinned in `psse_schema_doc_test.py` and applied live as `supabase/migrations/20261109233541_psse_results.sql` (STATE.md, quick task 261109-o6v). That is outside this repository's control; plan nothing on it. Do not edit `psse_results_v1.sql`.

Do not store the target figures themselves in `details` by default: they are real city load numbers and the dashboard may one day read these tables. The basis label, method and provisional flag are enough with the mapping hash. Whether realised totals may be stored is Open Question 3.

The `ratings_used` per-city key list is pinned by three tests (`psse_ratings_test.py:299`, `psse_schema_doc_test.py:222`, `psse_run_record_test.py:199`) against `constants.RATINGS_USED_KEYS`; do not add a key there when `details` serves.

## Failure behaviour today and what changes (answers question 3)

Today (read in `study.py`, `job.py`, `run_record.py`):

| Where a city's problem arises | What happens now |
|-------------------------------|------------------|
| A mapped branch missing, a transformer, out of service, mixed kV, bad sink bus | `check_mapping` returns every problem for every city; `prepare_base` raises one `StudyFailed("mapping", "; ".join(problems))` before any write |
| A rating write that does not read back, city k | `apply_ratings` raises at the first failing city; later cities are never touched |
| The base load flow does not converge | One load flow covers all four cities, so one `StudyFailed("load_flow", ...)` fails everything; no city is distinguishable |
| An outage that does not converge | Data: one `non_convergence` row; the screen continues (unchanged by this phase) |
| A margin search fails, city k | `[margin.city_margin(base, city) for city in constants.CITIES]` raises at the first failing city; the cities after it are never evaluated and the earlier results are discarded with the exception |
| A dispatch row refuses | `StudyFailed("dispatch", "<CITY>: ...")` at the first refusing city |
| Any of the above | `run_once` records one `failed` `psse_run` row (stage, error of at most 1000 characters), no result rows, exit 1 |

So today a failing city hides the cities after it, and with a shared load flow nothing says which city's data caused a base non-convergence.

What changes: with a case per city, a failure is attributable. The loop continues after a city fails, remembers each outcome, and the combined `StudyFailed` (Pattern 3) names all four. Stages used (existing vocabulary only; verbatim list `[VERIFIED: backend/psse_job/constants.py:50-53]`: `"load_case", "mapping", "apply_ratings", "load_flow", "contingency", "voltage_margin", "dispatch", "validate_results", "write", "internal"`, identical to the DDL `psse_run_failed_stage_ck` list):

| Failure | Stage |
|---------|-------|
| Bad or missing scaling block, unknown basis | `mapping` |
| `scal_2` returns a non-zero `ierr`, raises, or the totals read-back misses the targets, or the scale-factor sanity bound trips | `apply_ratings` (message starts "scaling:") |
| Scaled base case does not converge, mismatch too large, collapsed solution | `load_flow` |
| Screen cap, budget, call failure | `contingency` (unchanged) |
| Margin search | `voltage_margin` (unchanged) |

The "partial run" alternative (write the converged cities' rows) is not plannable without the owner: `outcome` is only `ok`, `fallback`, `failed` (DDL `psse_run_outcome_ck`), a result row's `run_outcome` must be `ok` or `fallback` through a composite foreign key, `validate_results` and the live check `non_failed_runs_have_four_dispatch_rows` demand four rows, and a half-complete run labelled `ok` would also count as a complete hour for the gap query (`gaps.py`, "hour that has no complete result set"). The repo already records this stance: `psse_study_definitions.md` says "There is no "not computed" value for a city's margin or dispatch. One city's failed margin therefore fails the whole run. An additive Phase 6 migration could relax this if the project wants it." Open Question 1.

## Common Pitfalls

### Pitfall 1: The call layout is right in the fake and wrong in PSS/E
**What goes wrong:** the fake accepts exactly what the adapter sends, so a wrong slot (generation in the wrong place, Mvar slot ignored, `_f` not honoured) passes every Mac test and scales the wrong quantity on the laptop.
**Why it happens:** the fake is built from the same SURFACE table; `[VERIFIED: backend/tests/psse_fake_psspy.py:1-14]` says it "proves nothing about what real PSS/E accepts". Its current `scal_2` only checks `if len(status) != 5 or status[1] != 3 or status[3] != 1 or len(scalval) != 7:` (line 447).
**How to avoid:** laptop task L1 before finalising the adapter; the read-back guard turns a silent mis-scale into a failed city with a clear message.
**Warning signs:** the probe row `scale_to_target` fails, or a dry run reports `scaling:` failures at `apply_ratings`.

### Pitfall 2: Shared contingency keys across the four copies
**What goes wrong:** the same 28 outages run in four copies produce identical `(contingency_id, violation_kind, element_id)` keys; `validate_results` fails the whole run at `validate_results` ("repeats the key"), or the insert violates `psse_contingency_result_pk`.
**How to avoid:** prefix the contingency id with the city; in `contingency.screen` keep the raw key for `skip_key` (`contingency.py:96` passes `skip_key=contingency_id` today, and `contingency_id = outage.key` at `:80`), because the outaged line is skipped by its raw key. Add an `id_prefix=""` argument so existing tests that expect raw ids stay valid.

### Pitfall 3: The stage vocabulary has no room for "scaling"
**What goes wrong:** raising `StudyFailed("scaling", ...)` becomes stage `internal` with the text "stage 'scaling': ..." (`run_record.failure_from_exception`), hiding the cause in the stage column. Writing the value directly would be rejected by the live CHECK.
**How to avoid:** use the stage table above.

### Pitfall 4: Old mapping files stop working
**What goes wrong:** the throwaway version-1 mapping on the laptop (outside the repo) is refused after the schema bump, so the Task Scheduler dry-run task from runbook step 6 fails each hour with `mapping` failures, and any runbook command that names the mapping fails.
**How to avoid:** the plan that bumps the version also updates the runbook and the laptop setup text, and gives the user a v2 throwaway mapping recipe with placeholder targets for the public case; call it out in the hand-over. Targets for the throwaway mapping must suit the public case's own totals (the base totals recorded in CONTEXT), not the fake network's.

### Pitfall 5: Counts in many tests change
**What goes wrong:** per-city copies change `n_contingencies` and the row counts the tests hard-code (16 outages, 10 violation rows, 7 with results). With `contingency.hops` 2 on the placeholder network, a city's neighbourhood reaches the other cities' tie lines through the swing bus, so each city screens more lines than the combined count today; the total is the sum over four cities.
**How to avoid:** recompute the expected numbers from the fake after the change (do not scale them by hand), and update them in one plan (list in Validation Architecture).

### Pitfall 6: Messages leak real figures
**What goes wrong:** a read-back error like "load 1234.5, wanted 1250.0" lands in `psse_run.error`, the rotating log and the dry-run output that operators paste.
**How to avoid:** messages say "differs from the target by more than the tolerance" and name the quantity, never a number from the mapping or the case. A test greps the failure text for the placeholder target values.

### Pitfall 7: Generation scaling limits and the swing machine (unverified)
**What goes wrong:** a target generation above total Pmax, or a large downward scaling, may be clipped by PSS/E or leave machines outside limits; a large load-to-generation mismatch is absorbed by the swing machine at the solve and can fail to converge.
**How to avoid:** the read-back guard catches clipping before the solve; the `load_flow` stage records non-convergence per city; L1 includes one clipped-target probe if the engine allows. `[ASSUMED]` that the scaling activity honours machine limits; unconfirmed.

### Pitfall 8: Mvar target silently ignored
**What goes wrong:** if the recorded step used constant P/Q, the engine ignores the Mvar slot and the cities all run at the base power factor, while the mapping appears to carry a Mvar target.
**How to avoid:** L1 reads the real layout; the read-back checks load Mvar too if the totals expose it. Open Question 2.

### Pitfall 9: Doc and doc-test drift
`psse_study_doc_test.py` pins required headings and the failure-stage table, and the mapping example link; `psse_schema_doc_test.py` pins the DDL hash and the `ratings_used` key list. A new "Per-city scaling" section in `psse_study_definitions.md` requires adding its heading to `REQUIRED_HEADINGS`; the doc must not contain a number of five or six digits outside the allow-list (`ALLOWED_FIVE_OR_SIX_DIGITS`), so write no real total there.

## Code Examples

All numbers are placeholders. Sources: in-repo sketches built from the verified quotes above.

### Mapping v2, one city (placeholder only)
```json
{
  "schema_version": 2,
  "placeholder": true,
  "cities": {
    "AUSTIN": {
      "branches": [{"from_bus": 90001, "to_bus": 90002, "ckt": "1"}],
      "sink_buses": [90002],
      "scaling": {"load_mw": 1000.0, "gen_mw": 1020.0, "load_mvar": 300.0, "basis": "average"}
    }
  }
}
```
(the real file has all four cities; the same `branches` entry may appear under more than one city)

### Contingency id prefix (keeps keys unique across copies)
```python
# psse_job/contingency.py, inside screen(base, id_prefix="")
contingency_id = id_prefix + outage.key          # e.g. "AUSTIN:90001-90002-1"
...
rows.extend(violations.thermal_violations(
    flows, monitored_keys, settings, contingency_id, city_of_branch,
    base_flows_by_key, skip_key=outage.key))      # skip by the RAW key, not the prefixed id
```

### Aggregated failure (stage and text)
```python
# psse_job/study.py, after the four city attempts
if failures:                                       # list of (city, stage, message), CITIES order
    clauses = []
    for city in constants.CITIES:
        found = [f for f in failures if f[0] == city]
        clauses.append("%s: %s" % (city, ("failed at %s: %s" % (found[0][1], found[0][2][:160]))
                                   if found else "ok"))
    raise StudyFailed(failures[0][1], "%d of 4 cities failed; %s" % (len(failures), "; ".join(clauses)))
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| One 39-bus case holding all four cities, one solve | One fresh copy of the same case per city, scaled to that city | This phase (decided 2026-11-09) | Four independent load flows; per-city attribution of failures |
| Unscaled network standing in for every city | Per-city load and generation targets from Power Systems' scaling files, applied by the job | This phase | Cities differ in loading; mapping gains a scaling block |
| PSS/E GUI-recorded `.idv` scripts apply the scaling by hand | The job applies the numbers itself through `psspy` | This phase | No script execution from configuration |

**Deprecated/outdated:** the assumption in `psse_study_definitions.md` (A13) that `scal_2` "leaves generation unchanged" is about the increment form on a subsystem; the new-total whole-case form changes generation by design and must be documented separately.

## Runtime State (what the schema bump touches)

This is not a rename phase, so the full inventory is omitted. The state that outlives the code change:

| Category | Items | Action |
|----------|-------|--------|
| Stored data | Existing `psse_run` rows from 2026-11 (none written to live tables: the proof write was deferred, so zero real rows) | None |
| Live service config | The laptop's throwaway v1 mapping and the dry-run Task Scheduler task (step 6 of the runbook) | Update the mapping to v2 with placeholder targets; verify the next hourly dry run |
| OS-registered state | The scheduled task command line names the config, not the mapping | None |
| Secrets and env vars | None added | None |
| Build artifacts | None | None |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `scal_2`, `all=1`, `apiopt=0`, `status=[_i, 1, 0, 1, 0]`, `scalval=[load_mw, gen_mw, _f, _f, _f, _f, _f]` sets total load and total generation to the given values (status index 1 equal to 1 is "new total") | Pattern 1 | Wrong quantity scaled; caught by the read-back guard and L1, not by the fake |
| A2 | The seventh `scalval` slot is load Mvar and is ignored under constant P/Q (`status[3]` equal to 1) | Pattern 1, Pitfall 8 | Mvar targets silently not honoured |
| A3 | `psspy.scal_4` exists in 36.4 and its layout is not needed because `scal_2` suffices | Alternatives | If the Mvar or generation option exists only in `scal_4`, a new SURFACE row and probe check are needed |
| A4 | `totals[1]` is total load MW and `totals[2]` total generation MW in the `scal_2` totals array | Pattern 1 | Read-back compares the wrong quantity; L1 settles it |
| A5 | `psspy.case()` fully undoes a `scal_2` change (the fresh copy) | Pattern 2 | Cities leak into each other; L1 settles it |
| A6 | The scaling activity honours machine limits and the swing machine absorbs the mismatch at the solve | Pitfall 7 | Clipped or unconverged scaled cases; guard and `load_flow` stage record it |
| A7 | Read-back tolerance relative 1e-3 and scale-factor sanity bound 0.05 to 20 | Pattern 1 | Too tight or too loose; configuration, adjust after L1 |
| A8 | The same lines may map under every city (Power Systems still to confirm) | Mapping v2 | If not, keep the cross-city duplicate refusal (a one-line difference) |
| A9 | A city prefix in `contingency_id` is acceptable to later consumers (no dashboard consumer of this table exists in the repo today; F7 is unbuilt) | Result tables | Later rework if a consumer wants a city column; needs the owner's migration |
| A10 | `sid` is ignored by PSS/E when `all=1` | Pattern 1 | The whole-case call fails with an `ierr`; L1 settles it |
| A11 | Basis vocabulary `average` or `peak` plus an optional `provisional` flag is enough for El Paso's placeholder case | Mapping v2 | Rename only |

## Open Questions

1. **Partial results when one city fails?**
   - What we know: the live schema, WB-02 and the owner's checks require all four rows for any non-failed run; the cheap, no-migration behaviour is "attempt all four, fail once, name every city".
   - What is unclear: whether the user wants the three good cities' rows stored anyway.
   - Recommendation: plan the no-migration behaviour (SCL-04). If the user wants partial runs, it is a separate request to the data owner for an additive migration (a per-city status and a new outcome or flag) and an amendment of WB-02, out of this repo's control.

2. **Must the load Mvar target be honoured, or is the base power factor acceptable?**
   - What we know: CONTEXT says the recorded step carries a Mvar number; community posts say it is ignored under constant P/Q.
   - What is unclear: what the recorded step's mode was.
   - Recommendation: honour it if the engine allows (explicit Q), verified by read-back; decide after L1 shows the layout. Ask Power Systems which they intend.

3. **May realised totals or targets be stored in the private tables' `details`?**
   - Recommendation: no, store basis, method, provisional only; the mapping hash is the audit trail.

4. **El Paso basis** (average from EIA-861 or peak labelled provisional): data only; the mapping carries whichever is chosen with its basis label. Confirmation is the user's and Power Systems'.

5. **Is the combined `StudyFailed` stage choice (first failed city's stage) acceptable?** Alternative: a fixed "worst stage" ranking. Recommendation: first failed city, because the text names all.

### Laptop tasks the planner must schedule (the only things the fake cannot prove)
- **L1 (blocking-human, before the adapter method is finalised):** on the laptop, in the PSS/E-started interpreter, print the `psspy.scal_2` and (if present) `psspy.scal_4` signature and documentation text (`inspect.signature`, `.__doc__`; whether the bindings carry the manual text is `[ASSUMED]`), and/or re-record the scaling dialog in the GUI as Python on the public 39-bus case with obviously fake numbers (for example 1111, 2222, 3333) so each argument position is visible. Paste only the call line (public case, placeholder numbers). Never open or paste a recorded city `.idv`.
- **L2:** new probe write-check row `scale_to_target`: read the case's own totals, scale to a fraction of them, read totals back, reload, confirm totals restored. Prints PASS or FAIL only.
- **L3:** a dry run with a v2 throwaway mapping on the 39-bus case: four cities complete; record the study seconds (CONTEXT: about 1 second for one scaled-free pass today; now four passes).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python and `.venv` with pytest | All Mac-side tests | yes | Python 3.12.7 in `.venv`; 255 passed, 24 skipped on seven psse files this session | none needed |
| Local Postgres (`initdb`, `pg_ctl`) | `psse_study_job_test.py`, `psse_rehearsal_test.py`, `psse_schema_pg_test.py` (the 24 skips) | no (not on PATH on this machine) | none | Keep non-database proofs of row shape: `run_record.validate_results`, `result_rows`, and `psse_job_test.py` fakes; run the PG-backed tests where Postgres exists (`DLR_TEST_PG_AUTOSTART=1`) |
| PSS/E and its licence | Real proof of the call layout, run time | no (teammate's laptop only; `C:\Program Files\PTI` absent here) | 36.4 on the laptop | none for L1 to L3; plan them as blocking-human |
| Supabase and the writer login | The real proof write | out of scope (Phase 3 step 9 deferred) | live tables exist | none needed in this phase |

**Missing dependencies with no fallback:** PSS/E (L1 to L3 only). **With fallback:** local Postgres.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest in the repo `.venv` (config: `pytest.ini`, `pythonpath = backend`) |
| Config file | `pytest.ini` |
| Quick run command | `.venv/Scripts/python.exe -m pytest backend/tests/psse_mapping_test.py backend/tests/psse_api_test.py backend/tests/psse_scaling_test.py -q` |
| Full suite command | `.venv/Scripts/python.exe -m pytest backend/tests/psse_study_test.py backend/tests/psse_mapping_test.py backend/tests/psse_api_test.py backend/tests/psse_contingency_test.py backend/tests/psse_margin_test.py backend/tests/psse_study_job_test.py backend/tests/psse_launcher_test.py backend/tests/psse_study_doc_test.py backend/tests/psse_schema_doc_test.py backend/tests/psse_probe_test.py backend/tests/psse_laptop_modes_test.py -q` (baseline on seven of these: 255 passed, 24 skipped, about 26 s) |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCL-01 | v2 parses; missing, zero, negative, NaN, unknown basis, unknown key each rejected with every problem named; same branch under two cities accepted, twice in one city refused; v1 refused; hash covers the block | unit | `pytest backend/tests/psse_mapping_test.py -x` | exists; edit (see pinned list) |
| SCL-01 | A bad scaling block fails the run at stage `mapping` and the fake saw no write call | study | `pytest backend/tests/psse_scaling_test.py -k mapping` | Wave 0 |
| SCL-02 | `scale_case` sends the expected arrays (placeholder numbers), takes `result[0]` as `ierr`, rejects bad numbers before any call, maps a non-zero `ierr` to `PsseCallError` | unit (fake) | `pytest backend/tests/psse_api_test.py -k scale_case` | exists; add |
| SCL-02 | Read-back miss and scale-factor bound each fail that city at `apply_ratings` with a message containing no placeholder figure | study (fake whose scal ignores the target) | `pytest backend/tests/psse_scaling_test.py -k readback` | Wave 0 |
| SCL-03 | Four independent solves: a recording solver sees four different totals, each with only its own city's rating written, and the case file is loaded four times and never saved over | study (fake, recording solver) | `pytest backend/tests/psse_scaling_test.py -k independent` | Wave 0 |
| SCL-03 | Call order per city: `case`, `scal_2`, (read-back), `branch_chng_3`, `fnsl`, `save`; calls stay inside SURFACE; golden call surface regenerated deliberately | study | `pytest backend/tests/psse_study_test.py -k "surface or never_saves"` | exists; edit; golden JSON regenerate |
| SCL-04 | City 2 fails (non-convergence, scale `ierr`, margin) yet cities 1, 3, 4 are attempted (fake call log); one `StudyFailed`, first failed stage, text names all four, at most the error limit after redaction; temp directory empty | study | `pytest backend/tests/psse_scaling_test.py -k failure` | Wave 0 |
| SCL-04 | Budget exhausted mid-run: remaining cities reported as not attempted | study (injected clock) | `pytest backend/tests/psse_scaling_test.py -k budget` | Wave 0 |
| SCL-04 | Through `job.run_once` with an in-memory connection: failed record, no result rows, exit 1 | job | `pytest backend/tests/psse_scaling_test.py -k run_once` (PG variant in `psse_study_job_test.py` where Postgres exists) | Wave 0 |
| SCL-05 | Two cities with the same mapped line produce unique contingency keys; `validate_results` passes; `n_contingencies` is the sum; distinct-id count equals `n_contingencies_with_results`; `details` carries the scaling basis and method and is JSON-safe | study | `pytest backend/tests/psse_scaling_test.py -k rows` | Wave 0 |
| SCL-05 | No placeholder target value appears in any row, error text, log record or dry-run output | study + launcher | `pytest backend/tests/psse_scaling_test.py -k no_figures` and `psse_launcher_test.py` | Wave 0 |
| SCL-06 | Probe row `scale_to_target` exists, runs only under the write check, restores the case; offline it runs on the fake | probe | `pytest backend/tests/psse_probe_test.py` | exists; edit |
| SCL-06 | Real engine accepts the layout, totals read back at the targets, reload restores them; four-city dry run on the 39-bus case | laptop only | runbook: probe with write check, then dry run | manual, blocking-human (L1 to L3) |

### Sampling Rate
- **Per task commit:** the quick run command plus the touched module's test file.
- **Per wave merge:** the full suite command above.
- **Phase gate:** full suite green on this machine, the PG-backed files green wherever Postgres exists, and L1 to L3 recorded in a laptop record before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `backend/tests/psse_fake_psspy.py`: give `FakeCase` generators (a `gens` map and a total), extend `scal_2` to accept new-total mode (`status[1] == 1`, `_f` slots untouched) and `apiopt=1` totals reads, keep the existing increment form valid; record nothing new in `SURFACE` unless L1 forces a `scal_4` row. Add a recording-solver helper that captures the case's totals and the rated lines at every `fnsl`.
- [ ] `backend/tests/psse_scaling_test.py`: new file for the SCL rows above.
- [ ] A fake variant whose scaling is silently ignored (read-back miss) and one whose `scal_2` returns an error, following `psse_margin_test.py`'s pattern (a subclass overriding `scal_2`, line 336-338).
- [ ] Regenerate `backend/tests/data/psse_call_surface.json` with `PSSE_UPDATE_CALL_SURFACE=1` and review the diff (first-seen order of `scal_2` moves earlier).
- [ ] No framework install needed.

### Existing tests that pin the current shape (edit deliberately)
| File | Pin | Change |
|------|-----|--------|
| `psse_mapping_test.py` | line 44 `loaded.schema_version == 1`; `_BAD_INPUT` rows 164-167 (`schema_version` 2, text, bool); lines 250 and 593 use 2 as the bad value; lines 318-336 expect "already listed" for the other-city cases; unknown-key tests for city keys | version 2 becomes valid and 1 the refused value; cross-city duplicates now accepted, same-city kept; add scaling-block rows |
| `psse_study_test.py` | `list(base.cities) == list(constants.CITIES)` (tracer), `len(results.contingencies) == 10`, `n_contingencies == 16`, exactly one fresh `case()` load per study (`_fresh_case_calls`, line 616 and 626), `test_call_surface_matches_golden`, the dispatch-failure message `"AUSTIN: inconsistent search"` (line 711), margin failure stage in the temp-dir test (line 664) | recompute counts from the fake; four fresh loads; regenerate golden; messages follow the aggregated text |
| `psse_study_job_test.py` (Postgres) | `n_contingencies == 16`, `n_contingencies_with_results == 7` (lines 163-164), 0 at 429-430, the `_assert_failed` stage and fragment tests | recompute; fragments become city clauses |
| `psse_launcher_test.py` | `n_contingencies == 16` (247), `screened=16 with_results=7` (795) | recompute |
| `psse_rehearsal_test.py` | `psse_contingency_result=10` (360) | recompute |
| `psse_api_test.py` | the SURFACE name list (line 494) and the `scale_load` test (300-335) | add `scale_case` tests; the list changes only if a row is added |
| `psse_probe_test.py`, `psse_laptop_modes_test.py` | probe row counts and call lists in write-check mode (probe test lines 268-273; modes test line 403) | one more row, one more call set |
| `psse_study_doc_test.py` | `REQUIRED_HEADINGS`, the stage table, the example link | new section heading; table unchanged (no new stage) |
| `psse_schema_doc_test.py`, `psse_results_migration_test.py` | DDL region hash and the applied migration | must NOT change: this phase edits neither |

## Security Domain

`security_enforcement` is not set in `.planning/config.json` (absent means enabled).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (no new credential; the existing writer role and ratings key are untouched) | existing |
| V3 Session Management | no | n/a |
| V4 Access Control | no (no new grant; `dlr_psse_writer` keeps INSERT and SELECT on the four tables) | existing DDL |
| V5 Input Validation | yes | the existing `mapping.py` problem-list validation: finite numbers, ranges, closed vocabularies, unknown keys refused, 65536-byte cap, JSON only (never executed) |
| V6 Cryptography | no (the mapping hash is sha256 of the bytes, already computed) | existing |
| V7 Error Handling and Logging | yes | `run_record._error_text` (redacted, 1000 characters), `launcher._scrub_paths`; new rule: no mapping or case figure in any message |
| V8 Data Protection | yes | real city figures only in the private mapping on the laptop; placeholders in repo, tests, docs and examples; no figure in `details` by default |
| V14 Configuration | yes | the job never executes a script or `.idv` named in configuration; the scale call is a `psspy` call with numbers parsed from JSON |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| A config-named script executed by the job (the `.idv` files) | Elevation of privilege, Tampering | Not supported by design: only numbers are read; a test asserts no `psspy` execution or file-run function is in `SURFACE` |
| Real load figures in git, logs, error text or dry-run output | Information disclosure | Placeholder-only tests and examples; messages carry no figures; a test greps outputs for the placeholder values; repository is public |
| A mapping edited between runs without notice | Tampering | `mapping_sha256` of the exact bytes is stored on every run row |
| A typo in units (kW for MW) driving an absurd scaled case | Denial of service, Tampering | Scale-factor sanity bound and read-back guard; per-city failure rather than a wrong stored result; run-time `Budget` |
| Oversized or hostile mapping JSON | Denial of service | Existing size cap and duplicate-key, NaN and unknown-key refusals |
| A case file overwritten by a scaled save | Tampering | `PsseApi.save_case` raises `CaseProtected` for the loaded path; saves only under the private temp directory |

## Sources

### Primary (HIGH confidence)
- Repository files read this session: `backend/psse_job/{study,mapping,psse_api,job,contract,constants,run_record,contingency,margin,violations,dispatch,settings,launcher,writer}.py`, `backend/tests/psse_fake_psspy.py`, `backend/tests/psse_study_test.py` (lines 1-160, 575-811), selected lines of the other psse tests, `docs/data-science/schema/psse_results_v1.sql`, `psse_results_v1.md`, `psse_results_v1_checks.sql`, `psse_mapping_example.json`, `docs/data-science/decisions/psse_study_definitions.md`, `03-07-LAPTOP-RECORD.md`, `04-CONTEXT.md`, `REQUIREMENTS.md`, `STATE.md`, `ROADMAP.md`.
- Test run on this machine: 255 passed, 24 skipped in 25.83 s (seven psse test files).

### Secondary (MEDIUM confidence)
- `03-07-LAPTOP-RECORD.md` (laptop facts proven on the real PSS/E 36.4: combined `scal_2` form, `branch_chng_3`, `fnsl`, bulk reads).

### Tertiary (LOW confidence, community forum, confidence tier from the research seam is LOW for web search and fetch)
- psspy.org Q1720 (new-total `scal_2` example on a sample case): https://psspy.org/psse-help-forum/question/1720/how-to-use-python-to-scale-the-system-load-in-psse/
- psspy.org Q4673 (totals array layout): https://psspy.org/psse-help-forum/question/4673/how-do-i-get-the-total-generation-mw-in-an-area-using-python-in-psse/
- psspy.org Q2551 (status index 1 modes 1, 2, 3): https://psspy.org/psse-help-forum/question/2551/is-it-possible-to-change-generator-and-load-values-in-dynamic-simulation/
- psspy.org Q6830 (`_f` placeholders keep other quantities unchanged): https://psspy.org/psse-help-forum/question/6830/allocating-only-mw-loads-using-psspyscal_2/
- Not found: any public documentation of `psspy.scal_4`; the vendor API manual for `scal_2` or `scal_4` was not reachable.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH, nothing new is added.
- Architecture (where the change goes, what pins it): HIGH, read from the code and run against the tests.
- Scaling call layout: LOW, community sources only; the design confines the uncertainty to one adapter method, one probe row and one laptop task (L1).
- Schema fit (no migration): HIGH, read from the DDL and the owner's checks.
- Pitfalls: MEDIUM to HIGH; items 7 and 8 depend on engine behaviour.

**Research date:** 2026-11-09
**Valid until:** 2026-12-09, or until L1 reports the real layout, whichever is first.
