# Phase 4: Per-city scaling of the 39-bus case - Pattern Map

**Mapped:** 2026-11-09
**Files analyzed:** 14 (7 modified source, 1 new test, 3 modified fakes/tests/golden, 3 docs)
**Analogs found:** 14 / 14 (all analogs are git-tracked; checked with `git ls-files`)

All numbers below are obvious placeholders. No real city figure, case, mapping or credential appears here.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|-------------------|------|-----------|----------------|-------|
| `backend/psse_job/mapping.py` (modify: v2, `Scaling`, per-city duplicate rule) | config/validator | transform | itself, `transfer_max_mw` block (lines 156-167) | exact |
| `backend/psse_job/psse_api.py` (add `scale_case`, `read_totals`) | service/adapter | request-response | `PsseApi.scale_load` (lines 479-495) | exact |
| `backend/psse_job/study.py` (per-city loop, `prepare_base(city=...)`, aggregated failure) | service | batch (4 independent runs) | `prepare_base` (262-309) and `make_study` (350-384) | exact |
| `backend/psse_job/contingency.py` (`screen(base, id_prefix="")`) | service | batch | `screen` (67-111) | exact |
| `backend/psse_job/dispatch.py` (`dispatch_details(..., scaling=None)`) | utility | transform | `dispatch_details` (85-95) | exact |
| `backend/psse_job/margin.py` (details gets scaling record, optional) | service | transform | `dispatch_details` plus margin row builder | role-match |
| `backend/psse_job/probe.py` (new row `scale_to_target`) | utility/probe | request-response | `_Probe.rating_write` (240-259), `scale_load` (261-280) | exact |
| `backend/tests/psse_fake_psspy.py` (generators, `scal_2` new-total and totals modes) | test fake | request-response | `FakePsspy.scal_2` (441-459) | exact |
| `backend/tests/psse_scaling_test.py` (NEW) | test | request-response | `psse_study_test.py` helpers (1-160, 575-650) and `psse_margin_test.py` `_ScaleFails` (335-339) | role-match |
| `backend/tests/psse_mapping_test.py` (edit pins) | test | transform | `_BAD_INPUT` table (155-195) | exact |
| `backend/tests/psse_study_test.py` / `psse_api_test.py` / `psse_probe_test.py` / `psse_laptop_modes_test.py` / `psse_launcher_test.py` / `psse_study_job_test.py` / `psse_rehearsal_test.py` (edit counts) | test | request-response | themselves | exact |
| `backend/tests/data/psse_call_surface.json` (regenerate) | test fixture | n/a | itself via `PSSE_UPDATE_CALL_SURFACE=1` | exact |
| `docs/data-science/schema/psse_mapping_example.json` (v2) | config example | n/a | itself (v1) | exact |
| `docs/data-science/decisions/psse_study_definitions.md` (+ `psse_study_doc_test.py` `REQUIRED_HEADINGS`) | doc | n/a | existing sections in same file | exact |

Must NOT be edited: `docs/data-science/schema/psse_results_v1.sql`, `psse_schema_doc_test.py`, `psse_results_migration_test.py`, `constants.RATINGS_USED_KEYS`, the failure-stage list (`constants.py:50-53`).

## Pattern Assignments

### `backend/psse_job/psse_api.py`: `scale_case`, `read_totals` (adapter, request-response)

**Analog:** `PsseApi.scale_load`, lines 479-495 (same file, beside it). Copy the validate-then-`_call`-then-shape-check-then-`_plain_ierr` skeleton.

```python
def scale_load(self, sid, increment_mw):
    self._subsystem_id(sid)
    try:
        increment = float(increment_mw) if _is_number(increment_mw) else float("nan")
    except OverflowError:
        increment = float("nan")
    if not math.isfinite(increment):
        raise ValueError("increment_mw must be a finite number")
    result = self._call(
        "scal_2", sid=sid, all=0, apiopt=0, status=[self._int_sentinel, 3, 0, 1, 0],
        scalval=[increment, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    if not isinstance(result, (tuple, list)) or not result:
        raise PsseCallError("scal_2", None, _SHAPE)
    ierr = self._plain_ierr("scal_2", result[0])
    if ierr != 0:
        raise PsseCallError("scal_2", ierr, _NOT_LISTED)
```

New method: same shape, `all=1`, `status[1]=1` (new total), `scalval=[load_mw, gen_mw, f, f, f, f, f]` with `f = self._real_sentinel`. Validation: finite, above 0, reject bool via `_is_number`. Layout is UNVERIFIED until laptop task L1; keep the layout in this one method. `sid` check (`_subsystem_id`) is not needed with `all=1` (A10). `read_totals` is an `apiopt=1` call returning `(load_mw, gen_mw)`; indexes `totals[1]`, `totals[2]` are community-sourced (A4). The `scal_2` SURFACE row is reused; add a row only if L1 shows `scal_4` is needed (then regenerate the golden and edit the SURFACE name list in `psse_api_test.py` line 494).

Messages must name no target figures (Pitfall 6). `save_case` already refuses the protected path (lines 497-503); scaled saves go only to the private temp dir.

---

### `backend/psse_job/mapping.py`: v2 with `scaling` block (validator, transform)

**Analog:** same file. Constants and tuples to extend (lines 23, 32-41):

```python
SCHEMA_VERSION = 1
CityMapping = collections.namedtuple(
    "CityMapping", ["city", "branches", "sink_buses", "transfer_max_mw"])
_CITY_KEYS = ("branches", "sink_buses", "transfer_max_mw")
```

Add `Scaling = collections.namedtuple("Scaling", [...])`, a `scaling` field on `CityMapping` (the only positional construction is line 175: `return CityMapping(city, tuple(branches), sink_buses, transfer_max_mw)`), and `"scaling"` in `_CITY_KEYS`. Tests use `_replace(...)`, which keeps working.

**Numeric-field validation to copy** (lines 156-167):

```python
if "transfer_max_mw" in raw:
    value = raw["transfer_max_mw"]
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value <= 0):
        problems.append("%s.transfer_max_mw: must be a finite number greater than 0" % where)
    else:
        transfer_max_mw = float(value)
```

**Unknown-key and missing-key pattern** (lines 82-91, `_parse_branch`): sorted unknown keys reported as `"%s.%s: unknown key"` using `_short(key)[1:-1]`; `"%s.%s: missing"` for each absent required key; collect all problems, return None if any.

**Duplicate rule to relax** (lines 126-133): drop the cross-city `if normal in seen:` refusal but keep duplicate refusal within one city (and reversed orientation). Make `seen` per city (reset inside `_parse_city`) rather than shared from `parse_mapping`. `MappingError` with every problem at once, capped by `MAX_PROBLEMS` (line 28), is unchanged. Version check: accept only 2; a v1 file message says per-city scaling is required.

`mapping_sha256` is of the exact bytes (computed at line 191) and already covers the targets. No code change there.

---

### `backend/psse_job/study.py`: per-city loop (service, batch)

**Analog:** `prepare_base` (262-309) for the per-city step and `make_study.study` (357-384) for the loop. Reorder inside the city step: fresh `load_case`, `scale_case`, read-back, rate that city only, `solve_base`, reads and collapse guard, save to `<temp>/<city>.sav`, then screen, margin, dispatch. `check_mapping` still runs once, before any write.

**Index-and-check pattern to keep once** (lines 268-282):

```python
try:
    api = psse_api.PsseApi(psspy_module, protected_path=case_path)
    psse_version = api.version()
    api.load_case(case_path)
    lines, transformers = api.branch_table()
    buses = api.bus_table()
except (psse_api.PsseCallError, ValueError) as error:
    raise StudyFailed("load_case", "case %s could not be loaded: %s" % (
        label, getattr(error, "meaning", error)))
resolved, problems = check_mapping(mapping, lines, transformers, buses)
if problems:
    raise StudyFailed("mapping", "; ".join(problems))
sinks = dict((city, mapping.cities[city].sink_buses) for city in constants.CITIES)
area = study_area(lines, buses, resolved, settings, sinks)
cities = apply_ratings(api, resolved, mapping, selection)
result = solve_base(api, settings)
```

One-city view for the helpers: `apply_ratings` loops `constants.CITIES` (lines 186-188: `choice = selection.choices[city]`, `branches = resolved[city]`), so it needs to accept a city subset (add `cities=` argument defaulting to all; `study_area` already tolerates missing cities via `resolved.get(city, ())`).

**Collapse guard and private temp save to copy per city** (lines 285-305): `mkdtemp(prefix=_TEMP_PREFIX)` once per run, `os.path.join(temp_dir, "<city>.sav")`, `_remove_dir` on `BaseException`. Cleanup in `finally` (`cleanup_base`, lines 257-259; lines 382-383).

**Failure collection** (new, adapt the research sketch; stage vocabulary is closed, `constants.py:50-53`): catch `StudyFailed` per city, remember `(city, stage, message)`, continue; after the loop raise one `StudyFailed(first_failed_stage, "N of 4 cities failed; AUSTIN: ok; ...")`. Scale-call errors and read-back misses use stage `apply_ratings` with message prefix "scaling:"; a scaled base that does not converge is `load_flow` (existing `solve_base`, lines 222-238, already prefixes ierr 2 hint); bad targets are `mapping`. Never name a stage "scaling" (becomes `internal`, and the DB CHECK rejects it). Dispatch refusal pattern to keep (lines 373-374): `raise StudyFailed("dispatch", "%s: %s" % (city, error))`.

Budget: one `Budget(clock, mapping.settings.max_runtime_seconds)` shared across cities (line 358); remaining cities after exhaustion reported as "not attempted: run-time budget".

Keep `prepare_base` callable with its current signature (used by `psse_contingency_test.py`, `psse_margin_test.py`, ten times in `psse_study_test.py`): add keyword `city=None` or add `prepare_city_base` sharing helpers. `StudyResults` assembly (lines 375-381) stays, with `n_contingencies` summed over the four screens and each row through `_with_safe_details`.

---

### `backend/psse_job/contingency.py`: `screen(base, id_prefix="")` (service, batch)

**Analog:** `screen`, lines 67-111. Change two lines only; the outaged line is still skipped by its raw key:

```python
contingency_id = outage.key                       # line 80  -> id_prefix + outage.key
...
rows.append(violations.non_convergence_row(contingency_id, result))          # line 86
rows.extend(violations.thermal_violations(
    flows, monitored_keys, settings, contingency_id, city_of_branch,
    base_flows_by_key, skip_key=contingency_id))                             # line 94-96 -> skip_key=outage.key
```

Also `_call_failure(outage, error)` (line 63-64) uses `outage.key` and stays raw. Default `id_prefix=""` keeps existing tests valid. `non_convergence` rows need `element_id == contingency_id` (DDL shape rule), so both carry the prefix through `violations.non_convergence_row`; thermal and voltage rows keep raw element ids. Prefix form: `"AUSTIN:90001-90002-1"` (1 to 200 characters).

---

### `backend/psse_job/dispatch.py` (and `margin.py`): scaling record in `details` (utility, transform)

**Analog:** `dispatch_details`, lines 85-95:

```python
def dispatch_details(city_base, rate_sets, bounded_by):
    return {
        "branches": [branch.ref.key for branch in city_base.branches],
        "rate_sets": list(rate_sets),
        "rate_before_mva": [run_record.finite(value) for value in city_base.rate_before_mva],
        "voltage_limit_bounded_by": bounded_by,
    }
```

Add `scaling=None` and, when given, `"scaling": {"basis": ..., "method": ..., "provisional": ...}`. Store no target or realised totals (user decision). The call site is `study.py:367-372`. `json_safe` (`study.py:326-341`) is applied afterwards by `_with_safe_details`. Do not add keys to `ratings_used` (pinned by three tests).

---

### `backend/psse_job/probe.py`: row `scale_to_target` (probe, request-response)

**Analog:** `_Probe.rating_write` (lines 240-259) for write, read back, reload, confirm restored; `scale_load` (261-280) for the `try/finally: self.api.load_case(self.case_path)` guard. Registration lines 302-304:

```python
if write_check:
    probe.run("rating_write", probe.rating_write)
    probe.run("scale_load", probe.scale_load)
```

New method: read totals, scale to a fraction of the case's own totals (placeholder-safe, no mapping numbers), read totals back, reload in `finally`, compare restored totals with the originals using `_RATING_TOLERANCE`-style relative tolerance; return `PASS`/`FAIL`/`SKIP` with a detail string that prints no figure. Add `probe.run("scale_to_target", probe.scale_to_target)` under `write_check` and update the module docstring list (line 17).

---

### `backend/tests/psse_fake_psspy.py`: generators and `scal_2` modes (test fake)

**Analog:** `FakePsspy.scal_2`, lines 441-459. The current guard rejects anything but the increment form:

```python
@_recorded
def scal_2(self, sid, all, apiopt, status, scalval):
    if sid not in self.fake_subsystems or self.fake_state is None:
        return (1, [], [])
    if all != 0 or apiopt != 0:
        return (2, [], [])
    if len(status) != 5 or status[1] != 3 or status[3] != 1 or len(scalval) != 7:
        return (4, [], [])
```

Extend: branch for `all == 1` with `status[1] == 1` (set load and generation totals; `_f` slots untouched) and `apiopt == 1` (return totals), keep the increment path as is. `FakeCase.__init__` (line 66-70: `buses`, `branches`, `loads`, `drop_per_mva`) gains a generator map and totals. Error codes follow the existing numeric returns (1, 2, 4, 6). Add a recording-solver helper capturing totals and rated lines at each `fnsl`; `fake_module.radial_solver(case)` (used in `psse_margin_test.py:329`) is the solver pattern.

---

### `backend/tests/psse_scaling_test.py` (NEW test, request-response)

**Analogs:** header and helpers from `psse_study_test.py`; fake-subclass failure from `psse_margin_test.py:335-339`.

**Imports and helpers** (`psse_study_test.py` lines 13-58): `sys.path` bootstrap, `import psse_fake_psspy as fake_module`, `import psse_fakes`, `from psse_job import (...)`, `EXAMPLE` path, `_registered(tmp_path, case=None, solver=None, fake=None)` registering the case under a marker file, `_mapping(cities=None, **changes)` using `mapping.load_mapping(EXAMPLE, allow_placeholder=True)` and `_replace`, `_selection()` from `ratings.select_ratings(psse_fakes.fake_fetch(rows), NOW)`.

**Private temp dir fixture** (lines 104-110): autouse `_private_temp` monkeypatching `tempfile.tempdir` so a leak shows; assert `os.listdir(tempfile.gettempdir()) == []` after success and failure.

**Fake variant for failures** (`psse_margin_test.py` 335-339):

```python
class _ScaleFails(fake_module.FakePsspy):
    def scal_2(self, sid, all, apiopt, status, scalval):
        return (6, [], [])
```
Add a second subclass whose `scal_2` silently ignores the target (read-back miss).

**Assertion patterns to reuse:** `_writes(fake)` (lines 66-69, counts `branch_chng_3`, `fnsl`, `save`, `bsys`, `scal_2`) asserted `== []` for a mapping failure (line 160); `_fresh_case_calls(fake, path)` (577-581) now expects four loads per study; `test_full_study_calls_stay_inside_surface` (600-608) and `test_full_study_never_saves_or_changes_the_case` (611-631) with the file sha256 unchanged; `pytest.raises(contract.StudyFailed)` then `caught.value.stage` (lines 134-137). Test names follow the research keys `-k mapping|readback|independent|failure|budget|run_once|rows|no_figures`. For `no_figures`, grep failure text and rows for the placeholder target values.

---

### `backend/tests/psse_mapping_test.py` (edit pins)

**Analog:** the `_BAD_INPUT` table (lines 155-195) of `(name, bytes, expected_fragment)` rows built with `_edit(...)`, `_set([...], value)` and `_drop([...])`. Flip `schema_two` (line 165) so 2 is valid and 1 the refused value; add rows for missing, zero, negative, NaN, bool, text and unknown-basis scaling values and an unknown scaling key, following `("city_unknown_key", _edit(_set(["colour"], "red")), "cities.AUSTIN.colour: unknown key")`. Update line 44 (`schema_version == 1`), the byte-replace at line 159 (`b'"schema_version": 1'`), lines 250 and 593, and lines 318-336 (cross-city "already listed" now accepted; same-city kept).

---

### `docs/data-science/schema/psse_mapping_example.json` and `psse_study_definitions.md`

Analog is the v1 example itself (shape shown in research "Mapping v2, one city"): `schema_version: 2`, `placeholder: true`, a `scaling` object per city with obviously fake numbers, same fake 9xxxx buses. The doc gains a "Per-city scaling" section; add its heading to `REQUIRED_HEADINGS` in `psse_study_doc_test.py`; write no five or six digit number outside `ALLOWED_FIVE_OR_SIX_DIGITS`. Update the A13 text that says `scal_2` leaves generation unchanged (it is true only for the increment form).

---

## Shared Patterns

### Stage vocabulary and failure shape
**Source:** `backend/psse_job/contract.py:110` (`StudyFailed(stage, message)`), `constants.py:50-53` (closed list: `load_case, mapping, apply_ratings, load_flow, contingency, voltage_margin, dispatch, validate_results, write, internal`, same as the DDL CHECK).
**Apply to:** every new failure in `study.py`, `psse_api.py` callers. `job.run_once` turns any `StudyFailed` into one failed `psse_run` row; error text redacted and cut at 1000 characters by `run_record._error_text`.

### Adapter error mapping
**Source:** `psse_api.py:488-495`; callers in `study.py` catch `(psse_api.PsseCallError, ValueError)` and re-raise `StudyFailed(stage, "...%s" % error)` (e.g. `study.py:226-227`, `274-276`, `287-288`).
**Apply to:** the new scale, read-totals and per-city load steps.

### No figures in messages
**Source:** new rule (Pitfall 6). Say "differs from the target by more than the tolerance"; name the quantity, never a mapping or case number.
**Apply to:** `scale_case` errors, read-back guard, aggregated failure text, probe detail strings, dry-run output.

### Problem-list validation
**Source:** `mapping.py` (`problems` list, `settings.check_bus`, `MappingError`).
**Apply to:** the `scaling` block parser and its tests.

### Private temp files, never the case file
**Source:** `study.py:294-305`, `_remove_dir` (244-254), `PsseApi.save_case` (`CaseProtected`).
**Apply to:** per-city `<city>.sav`; cleanup in `finally` on every path.

### Tracked golden call surface
**Source:** `backend/tests/data/psse_call_surface.json`; regenerate deliberately with `PSSE_UPDATE_CALL_SURFACE=1`, review the diff (first-seen order of `scal_2` moves earlier).

## No Analog Found

| File/Item | Role | Data Flow | Reason |
|-----------|------|-----------|--------|
| Aggregated all-or-nothing failure text (naming each city) | service | batch | No loop in the repo collects per-item failures; today the first failing city raises immediately (`study.py:362`, `373-374`). Use the research sketch (Pattern 3). |
| Whole-case scale-to-target `scal_2` layout | adapter | request-response | Only the increment form is proven (`psse_api.py:488-490`); new-total layout is community-sourced, gated on laptop task L1. |

## Laptop-only checks (the fake cannot prove these)
- L1 (blocking-human): print the `scal_2` (and `scal_4` if present) signature and docstring on PSS/E 36.4, or re-record the scale dialog on the public 39-bus case with fake numbers; paste only the call line. Never open or paste a recorded city `.idv`.
- L2: probe row `scale_to_target` with the write check (PASS or FAIL only).
- L3: four-city dry run with a v2 throwaway mapping (placeholder targets suited to the public case's own totals), with timing.

## Existing counts that move (recompute from the fake, do not hand-scale)
`n_contingencies == 16`, `len(results.contingencies) == 10`, `n_contingencies_with_results == 7`, `psse_contingency_result=10` in `psse_study_test.py`, `psse_study_job_test.py` (163-164, 429-430), `psse_launcher_test.py` (247, 795), `psse_rehearsal_test.py` (360); one fresh `case()` load per study becomes four (`psse_study_test.py:616, 626`); `"AUSTIN: inconsistent search"` message (line 711) follows the aggregated text; probe and laptop-mode row and call counts gain one row.

## Metadata

**Analog search scope:** `backend/psse_job/`, `backend/tests/psse_*`, `docs/data-science/` (via the research file lists, read this session)
**Files read:** study.py (225-394), psse_api.py (455-514), mapping.py (15-194), contingency.py (60-122), dispatch.py (80-96), probe.py (236-311), psse_fake_psspy.py (430-460), psse_margin_test.py (325-349), psse_study_test.py (1-165, 575-655), psse_mapping_test.py (155-195)
**Pattern extraction date:** 2026-11-09
