# Phase 1: PSS/E Reference Session and Network Parity - Pattern Map

**Mapped:** 2026-11-16
**Files analyzed:** 27 new/modified
**Analogs found:** 21 exact or role-match / 27 (6 listed under No Analog Found)

All analog paths below were checked as git-tracked (`git ls-files`). No real identifiers appear here; bus numbers use the `9xxxx` placeholder convention (the repo fake uses 90000-series placeholders).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `.gitignore` (modify: add `/data/private/`, `psse_pp_session*`) | config | n/a | `.gitignore` tail (`/psse_local/`, `*.sav`, `*.raw`) | exact |
| `backend/private_leak_scan.py` | utility | batch (file scan) | `backend/tests/secret_scan_test.py` helpers `_scan`, `_readable`, `_scan_exact`, `_tracked_files` | role-match |
| `backend/tests/private_data_guard_test.py` | test | batch | `backend/tests/secret_scan_test.py` (planted-control tests, `test_env_file_is_ignored_and_untracked`) | exact |
| `backend/tests/secret_scan_test.py` (modify: guard for private folder) | test | batch | itself | exact |
| `backend/psse_pandapower_session.py` (entry script, only `psspy` importer) | entry/config | request-response | `backend/psse_run_hourly.py` | exact |
| `backend/psse_session/session.py` | service | batch / file-I/O | `backend/psse_job/study.py` + `contingency.screen` (sequence to replay) | role-match |
| `backend/psse_session/surface.py` (SESSION_SURFACE table) | config | n/a | `backend/psse_job/psse_api.py` SURFACE table | role-match |
| `backend/psse_session/summary.py` (masked summary) | utility | transform | `backend/psse_job/redaction.py` + `probe.py` report | role-match |
| `backend/psse_session/bundle.py` (manifest, sha256, zip) | utility | file-I/O | none close; `mapping.load_mapping` returns `sha256` | partial |
| `docs/data-science/ops/psse_pandapower_session.ps1` | script | request-response | `docs/data-science/ops/psse_laptop_status.ps1` | exact |
| `backend/tests/psse_session_test.py` | test | integration | `backend/tests/psse_contract_test.py` (AST gates) + `psse_entry_test.py` | role-match |
| `backend/tests/psse_session_fake.py` (FakePsspy subclass, not collected) | test helper | n/a | `backend/tests/psse_fake_psspy.py` | exact |
| `backend/pandapower_job/raw.py` | parser | transform | none (research prototype only) | no analog |
| `backend/pandapower_job/network.py` | service | transform | none (research prototype builder) | no analog |
| `backend/pandapower_job/parity.py` | service | transform | none | no analog |
| `backend/pandapower_job/scaling.py` | service | transform | `backend/psse_job/study.py` `scale_city_case` (lines 395-426) | role-match |
| `backend/pandapower_job/solve.py` | service | request-response | `backend/psse_job/study.py` `solve_base` (line 266) | role-match |
| `backend/pandapower_job/compare.py` | utility | transform | `backend/psse_job/violations.py` thresholds | partial |
| `backend/pandapower_job/private.py` (path guard) | utility | file-I/O | `secret_scan_test.test_env_file_is_ignored_and_untracked` (`git check-ignore`) | partial |
| `backend/pandapower_job/ingest.py` (safe unzip) | utility | file-I/O | none | no analog |
| `backend/pandapower_job/__init__.py` | config | n/a | `backend/psse_job/__init__.py` | exact |
| `backend/tests/pandapower_fixture.py` (not collected) | test helper | transform | `backend/tests/psse_fake_psspy.py` `placeholder_case` | role-match |
| `backend/tests/pandapower_{raw,network,parity,compare}_test.py` | test | unit | `backend/tests/psse_contract_test.py` / `secret_scan_test.py` style | role-match |
| `requirements-pandapower.txt` | config | n/a | `requirements.txt` (root) | exact |

## Pattern Assignments

### `.gitignore` (config)

**Analog:** `.gitignore` last lines (tracked). Existing block style: a comment explaining why, then rules.
```
# Power Systems' case and city-to-branch mapping carry grid element identifiers and never
# enter this public repository (pss-e-integration Phase 2). Keep the real files in
# psse_local/; *.sav and *.raw are PSS/E saved-case and raw-case extensions (no tracked
# file uses them). Only docs/data-science/schema/psse_mapping_example.json is committed.
/psse_local/
*.sav
*.raw
```
Add `/data/private/`, `psse_pp_session*` with the same comment-first style. `*.raw` already exists. This must land before any export arrives (PSE-04).

---

### `backend/tests/private_data_guard_test.py` and `backend/private_leak_scan.py` (test + utility, batch)

**Analog:** `backend/tests/secret_scan_test.py`

**Conventions** (lines 19-26, 28-37): never print matched text; patterns assembled from pieces so the file never matches itself; plain asserts, no classes, module-level imports.
```python
import os, re, subprocess
import pytest
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_MAX_BYTES = 2 * 1024 * 1024
_SKIP_SUFFIXES = (".joblib", ".npz", ".png", ".jpg", ".pdf", ".xlsx")
```

**Readable + scan helpers** (lines 91-110) and **exact-needle scan** (lines 160-172): report `(path, line number, name)` only.
```python
def _readable(path):
    if path.lower().endswith(_SKIP_SUFFIXES) or not os.path.isfile(path): return False
    if os.path.getsize(path) > _MAX_BYTES: return False
    with open(path, "rb") as handle:
        return b"\x00" not in handle.read(8192)

def _scan_exact(paths, values):
    """(path, line number) for every line holding one of the values; never the value itself."""
```
Note the exact scan uses `any(value in line ...)`; the research asks for tokenise-and-set-membership (linear time) for the private-needle layer, so do not copy that loop verbatim.

**Tracked-files listing** (lines 175-182): copy, but add `git ls-files --others --exclude-standard` so the scan covers the working tree (Pattern 4), not only tracked files.
```python
listed = subprocess.run(["git", "ls-files", "-z"], cwd=_REPO_ROOT, capture_output=True, check=True)
return [os.path.join(_REPO_ROOT, name.decode("utf-8", "replace")) for name in listed.stdout.split(b"\0") if name]
```

**Ignore test** (lines 260-267): copy for `data/private/pandapower/x.json`.
```python
ignored = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=_REPO_ROOT)
if ignored.returncode == 128:
    pytest.skip("not a git checkout")
assert ignored.returncode == 0, ".env must be git-ignored"
tracked = subprocess.run(["git", "ls-files", "--", ".env"], cwd=_REPO_ROOT, capture_output=True, text=True, check=True)
assert tracked.stdout.strip() == ""
```

**Planted-control pattern** (lines 191-257, 298-310): plant in `tmp_path`, assert `found == [(str(planted), n, name)...]` and `ref not in repr(item)`; plant values must not equal the committed `9xxxx` examples. **Owner-local skip** (lines 313-321): `pytest.skip(...)` when the private folder is absent.

---

### `backend/psse_pandapower_session.py` (entry script, request-response)

**Analog:** `backend/psse_run_hourly.py` (the only importer of `psspy`; keep it small).

**Path bootstrap + imports** (lines 27-36):
```python
import importlib, os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)   # Under `python -I` the script's folder is not on the path
from psse_job import launcher  # noqa: E402
```
**Loader**: reuse `psse_run_hourly.load_psspy(cfg)` (lines 41-73; env helper imported by config name only, `import psspy` only inside the function, `launcher.start_psspy(psspy, max_buses, log_path)`), after `launcher.add_search_dirs(cfg)`; `launcher.read_config(path)` with no mode. Error handling: raise `launcher.PsseUnavailable` naming only the exception class (lines 60-70).
**Streams** (lines 76-91): copy `_prepare_streams()` UTF-8 reconfigure. **Main** (94-100): `sys.exit(main())`. Comment-block "Honest scope" style (lines 19-24) for unverified calls.

---

### `backend/psse_session/session.py` (service, batch/file-I/O)

**Analogs:** `backend/psse_job/study.py` (per-city copy), `backend/psse_job/contingency.py` (outage loop), `backend/psse_job/margin.py` (`city_margin`).

**Outage replay** (contingency.py 88-111): reload saved base before every outage, never un-trip:
```python
for outage in outages:
    try:
        api.load_case(base.saved_path)
        api.set_status(outage, False)
        result = api.solve(settings.solve_options)
        if not result.converged:
            rows.append(violations.non_convergence_row(contingency_id, result))
        else:
            buses = api.bus_table()
            flows = api.branch_loading(rate_set, settings.thermal_basis)
    except (psse_api.PsseCallError, ValueError) as error:
        raise _call_failure(outage, error)
```
For the session, record non-converged/islanded rows (ierr, solved code, meaning) instead of raising; wrap each section S2-S5 in its own try/except recording status and class name only (Pattern 1).

**Outage selection** (contingency.py 38-64): call `contingency.select_outages(base)` directly; do not re-implement.
**City base** (study.py 383-392, 435-459): `index = study.index_case(psspy, case_path, mapping)`, then `study.prepare_city_base(index, mapping, selection, city, budget, temp_dir)`; pre-solve snapshot via `api.load_case(...)` then `study.scale_city_case(api, city, scaling)` (lines 395-426) before `prepare_city_base`. Clean the temp folder with the job's own approach (`study._remove_dir`, line 288 / `cleanup_base`, line 301).
**Python rule:** 3.7 syntax, stdlib only, `psse_job` imports only; never `psycopg`, `socket`, `urllib`; never `save` onto the case path.

---

### `backend/psse_session/surface.py` (config table)

**Analog:** `backend/psse_job/psse_api.py` SURFACE table (comment at lines ~104-109 shows the style of recording evidence per call, e.g. `scal_2` close step). Read that table's entry shape before writing `SESSION_SURFACE` (one row per extra psspy call: name, evidence, confidence). The fake's drift test ties `SURFACE` exactly to `FakePsspy`, so the new table must live in a separate module and the new fake must be a subclass.

---

### `backend/psse_session/summary.py` (utility, transform)

**Analog:** `backend/psse_job/redaction.py` (lines 11-27 regex set, `_URL_RE`, `_KEY_VALUE_RE`, `_SB_TOKEN_RE`, `_JWT_RE`) as a backstop; summary itself is built from `%d`/`%s` integers and enums only. Test with planted `9xxxx` numbers, targets and paths asserting none appear.

---

### `docs/data-science/ops/psse_pandapower_session.ps1` (script)

**Analog:** `docs/data-science/ops/psse_laptop_status.ps1`

**Header comment** (lines 1-8): how to run, what it never opens, what it writes, masking promise.
**Desktop output** (line 18): `$Out = Join-Path ([Environment]::GetFolderPath('Desktop')) 'psse_status.txt'`
**Masking block** (lines 77-84) to reuse:
```powershell
$report = $report -replace 'postgres(ql)?://\S+', '[url masked]'
$report = $report -replace '(sb_publishable_|sb_secret_|eyJ)[A-Za-z0-9_.\-]+', '[key masked]'
$report = $report -replace '(?i)password=\S+', 'password=[masked]'
foreach ($id in @($env:USERNAME, $env:COMPUTERNAME, $env:USERDOMAIN)) {
    if ($id) { $report = $report -replace [regex]::Escape($id), '[masked]' }
}
```
Closing line (87): `"Done. Send this file back: $Out"`. Unlike the analog, drop the `Invoke-WebRequest` clock check (D-02: no network). Keep the wrapper to path resolution, one Python call, masking, print (A16); there is no `pwsh` on the Mac, so test masking through a Python twin.

---

### `backend/tests/psse_session_test.py` and `backend/tests/psse_session_fake.py`

**Analog (fake):** `backend/tests/psse_fake_psspy.py`. `FakePsspy` mirrors `SURFACE` exactly, methods wrapped by `_recorded` (line 165) so `inspect.signature` is the manual's names, helper attributes start `fake_`, constructor `FakePsspy(solver=None)` (line 181), `placeholder_case()` (line 147) with `PLACEHOLDER_CITY_BUSES` in the 90000 series (lines 38-43). Subclass it in `psse_session_fake.py` to add `prmdat`, `prmint`, RAW writer calls; do not edit the original. Not collected (name does not match `*_test.py`).

**Analog (AST gates):** `backend/tests/psse_contract_test.py`:
```python
def _module_paths():
    return sorted(glob.glob(os.path.join(_PACKAGE_DIR, "*.py")))   # line 63-64: glob backend/psse_job/*.py
ast.parse(_read(path), _rel(path), feature_version=(3, 7))          # line 196
```
Also its `test_import_gate_flags_planted_violations` (line 257) and `test_syntax_gates_flag_planted_violations` (216): gates are written over `(source, filename)` so a planted violation proves each fires. Copy as a second gate whose `_PACKAGE_DIR` is `backend/psse_session/` (the existing gate only globs `psse_job`). `backend/tests/psse_entry_test.py` is the analog for "psspy imported only in the entry script".

---

### `backend/pandapower_job/scaling.py` and `solve.py`

**Analog:** `backend/psse_job/study.py` `scale_city_case` (395-426): the guards to port to pandapower (ratio bounds `SCALE_FACTOR_BOUNDS = (0.05, 20.0)`, `SCALE_TOLERANCE = 1e-3` read-back, error text with no figures):
```python
low, high = SCALE_FACTOR_BOUNDS
if not low <= target / own <= high:
    raise refuse("the %s target is outside %g to %g times the case's own total" % (quantity, low, high))
if not abs(read - target) <= SCALE_TOLERANCE * target:
    raise refuse("the %s total read back differs from the target by more than %g percent" % (...))
```
Reuse `psse_job.mapping.parse_mapping`/`load_mapping` (Scaling namedtuple, sha256), `psse_job.settings`, `psse_job.units` by import (one-way dependency); do not copy. `pandapower_job` is Python 3.12 so ordinary modern syntax is fine, but it must never be imported by the laptop package.

---

### `backend/pandapower_job/private.py` (utility, file-I/O)

**Analog (partial):** `git check-ignore` call in `secret_scan_test.py` lines 260-267 (return code 128 = not a checkout, 0 = ignored). Resolve output path, require it under `data/private/`, require `git check-ignore -q` rc 0, else refuse.

---

### `backend/pandapower_job/__init__.py` and `requirements-pandapower.txt`

Analogs: `backend/psse_job/__init__.py` (package marker) and root `requirements.txt` (pin style). Pins per RESEARCH: `pandapower==3.5.6`, `numpy==2.4.3`, `pandas==2.3.3`, `scipy==1.17.1`.

---

### `backend/tests/pandapower_*_test.py` and `pandapower_fixture.py`

Style: plain asserts, module-level imports, no classes (`secret_scan_test.py` header). Use `pytest.importorskip("pandapower")`. `pytest.ini`: `pythonpath = backend`, `python_files = test_*.py *_test.py *_TestSuite.py`. Fixture generated into `tmp_path` from `pandapower.networks.case39()` with buses offset by 90000 (never committed, so the shape scan has no exceptions). Failure messages must be counts-only.

## Shared Patterns

### Never print matched or private text
**Source:** `backend/tests/secret_scan_test.py` lines 19-22, 187-188, 249-250
**Apply to:** leak scanner, session summary, every test touching private data
```python
shown = [f"{os.path.relpath(path, _REPO_ROOT)}:{number}:{name}" for path, number, name in findings]
assert findings == [], "credential-shaped text in tracked files: " + ", ".join(shown)
```

### Fail closed with named-class-only errors
**Source:** `backend/psse_run_hourly.py` lines 58-70
**Apply to:** session loader, section isolation, RAW parser refusals
```python
except (Exception, SystemExit) as exc:
    raise launcher.PsseUnavailable("... could not be imported (%s)" % type(exc).__name__)
```

### Reuse the job's own functions rather than reimplement
**Source:** `backend/psse_job/study.py` (`index_case`, `prepare_city_base`, `scale_city_case`), `contingency.select_outages`, `margin.city_margin`, `mapping.load_mapping`
**Apply to:** session script and any Mac-side scaling code

### Python 3.7 syntax, stdlib only on the laptop side
**Source:** `backend/tests/psse_contract_test.py` lines 191-196 (`feature_version=(3, 7)`)
**Apply to:** everything under `backend/psse_session/` and the entry script

### Read-only: no save onto the case path
**Source:** `backend/psse_job/study.py` `_save_solved` (line 337) saves only to the private temp copy `<temp_dir>/<CITY>.sav`
**Apply to:** session (copy to temp folder only, delete after)

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `backend/pandapower_job/raw.py` | parser | transform | No RAW/text-format parser exists; use RESEARCH Pattern 5 tokenizer prototype and PowerModels v33 field tables |
| `backend/pandapower_job/network.py` | service | transform | No pandapower code in repo yet; use RESEARCH "Builder" example (verified vs `case39()`) |
| `backend/pandapower_job/parity.py` | service | transform | New; RESEARCH Pattern 6 (inverse read-back, mutation tests) |
| `backend/pandapower_job/ingest.py` | utility | file-I/O | No zip handling in repo; RESEARCH Pitfall 9 (member allow-list, resolved-path check, size cap, sha256) |
| `backend/psse_session/bundle.py` | utility | file-I/O | No manifest/zip code; use `hashlib`, `zipfile`; take `sha256` from `mapping.load_mapping` |
| `backend/pandapower_job/compare.py` | utility | transform | Only the D-13 rule exists (RESEARCH "Comparator"); `violations.py` thresholds are a loose partial |

## Metadata

**Analog search scope:** `backend/psse_job/`, `backend/tests/`, `backend/psse_run_hourly.py`, `docs/data-science/ops/`, `.gitignore`, `pytest.ini`
**Files scanned:** about 30 (tracked-source check run for all cited paths)
**Pattern extraction date:** 2026-11-16
