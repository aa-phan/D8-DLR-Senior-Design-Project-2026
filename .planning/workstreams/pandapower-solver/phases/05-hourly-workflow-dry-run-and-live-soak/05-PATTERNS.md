# Phase 5: Hourly Workflow, Dry Run and Live Soak - Pattern Map

**Mapped:** 2026-11-25
**Files analyzed:** 14 new (no existing file is modified)
**Analogs found:** 13 / 14 (all analog paths verified git-tracked with `git ls-files`)

File list comes from the Recommended Project Structure in 05-RESEARCH.md. Names are discretion (CONTEXT). Nothing under `data/private/` was opened.

## File Classification

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `.github/workflows/pandapower_hourly.yml` | config (workflow) | event-driven (dispatch) | `.github/workflows/dlr_live.yml` | exact |
| `backend/pandapower_hourly.py` | entry script | request-response | `backend/pandapower_replay.py` | exact |
| `backend/pandapower_job/hourly.py` | runner (service + CLI) | batch / request-response | `backend/pandapower_job/replay_cli.py` | role-match (printer, error handling, CI detection); live call from `psse_job/job.py` |
| soak function (inside `hourly.py`, or `psse_job/gaps.py` neighbour) | utility | transform | `backend/psse_job/gaps.py` `compute_gaps` (lines 226-247) | exact |
| `backend/tests/pandapower_hourly_test.py` | test (pure tier) | request-response | `backend/tests/pandapower_study_job_test.py` (helpers) | role-match |
| `backend/tests/pandapower_hourly_leak_test.py` | test | transform (scan) | `backend/tests/pandapower_replay_output_test.py` | exact |
| `backend/tests/pandapower_hourly_pg_test.py` | test (DB tier) | CRUD | `backend/tests/pandapower_study_job_test.py` | exact |
| `backend/tests/pandapower_soak_test.py` | test | transform | `backend/tests/psse_gaps_solver_test.py` | exact |
| `backend/tests/pandapower_hourly_workflow_test.py` | test (text) | file-I/O | `backend/tests/dlr_live_workflow_test.py` | exact |
| `docs/data-science/decisions/pandapower_hourly_runbook.md` | doc | n/a | `docs/data-science/decisions/dlr_live_runbook.md` | exact |
| `docs/data-science/decisions/pandapower_live_write_decision.md` | doc (decision record) | n/a | `docs/data-science/decisions/pandapower_network_data_decision.md` | exact |
| `.../05-RETENTION-DECISION.md` | doc (decision record) | n/a | `pandapower_network_data_decision.md` | exact |
| `.../05-SOAK-RECORD.md` | doc (counts-only record) | n/a | `.planning/workstreams/pandapower-solver/phases/04-*/04-REPLAY-RECORD.md` (cited by RESEARCH; not re-read here) | role-match |
| `bundle` / `scan-log` subcommands in `hourly.py` (base64 transport) | utility | file-I/O | none exact | no analog |

## Pattern Assignments

### `.github/workflows/pandapower_hourly.yml` (config, event-driven)

**Analog:** `.github/workflows/dlr_live.yml`

**Trigger, permissions, concurrency** (lines 17-30). Drop the `inputs:` block (D-13: no inputs, so a dispatcher cannot flip live mode); change the group:
```yaml
on:
  workflow_dispatch: # cron-job.org (hourly) and manual runs from the Actions tab

permissions:
  contents: read

concurrency:
  group: dlr-live          # use `pandapower-hourly`
  cancel-in-progress: false
```

**Job guard** (lines 37-45):
```yaml
    if: github.ref == 'refs/heads/main'
    environment: production
    runs-on: ubuntu-latest
    timeout-minutes: 30
```

**Setup steps** (lines 47-59). Add `cache-dependency-path: requirements-pandapower.txt` and install `-r requirements-pandapower.txt psycopg==3.3.6 psycopg-binary==3.3.6`:
```yaml
      - name: Checkout code (main)
        uses: actions/checkout@v4
      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install -r requirements.txt
```

**Secrets only through `env:`** (lines 71-78). Never `${{ }}` in `run:`. Use env names from `psse_job/constants.py` (`SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_PSSE_DB_URL`) plus `PANDAPOWER_LIVE: ${{ vars.PANDAPOWER_LIVE }}` and the four `*_B64` secrets:
```yaml
      - name: Run live pipeline
        env:
          SUPABASE_DB_URL: ${{ secrets.SUPABASE_DB_URL }}
        run: PYTHONPATH=backend python backend/dlr_live_run.py
```
Use `python -I -B backend/pandapower_hourly.py run` (the entry script sets sys.path itself). Add a second read-only "Gap and soak check" step and an `if: always()` temp-folder removal step per RESEARCH Pattern 1 skeleton.

---

### `backend/pandapower_hourly.py` (entry script)

**Analog:** `backend/pandapower_replay.py` (whole file, lines 14-24). Copy verbatim, swap the module:
```python
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from pandapower_job import replay_cli  # noqa: E402

if __name__ == "__main__":
    sys.exit(replay_cli.main(sys.argv[1:]))
```
Replace `replay_cli` with `hourly`. Keep the module docstring shape (usage lines, "all logic is in ...", exit codes).

---

### `backend/pandapower_job/hourly.py` (runner, batch)

**Analog:** `backend/pandapower_job/replay_cli.py`

**Imports** (lines 37-47). Same layering: stdlib, then `psse_job`, then `pandapower_job`; `pandapower_job` may import `psse_job` and never the reverse:
```python
import argparse
import re
import sys

from psse_job import constants, study
from pandapower_job import agree, cli, engine, private, recorded, replay
```
For hourly add `job, ratings, run_record, contract, writer, gaps` from `psse_job` (writer imported only in the live path, never in the dry function, per D-10).

**Closed-vocabulary printer** (lines 58-115). Build `HOURLY_LINE_PATTERNS` from the same helpers (`_alt`, `_NUM`, `\Z` anchors), then the `_Printer` class unchanged:
```python
def _alt(words):
    return "(?:%s)" % "|".join(re.escape(word) for word in sorted(set(words), key=len, reverse=True))

class _Printer(object):
    def say(self, text, stream=None):
        if not any(pattern.match(text) for pattern in CLI_LINE_PATTERNS):
            raise ValueError("a printed line is outside the command vocabulary")
        target = self.out if stream is None else stream
        target.write(text + "\n")
```
Stage words: `"runs failed at stage %s: %s" % (_alt(constants.FAILED_STAGES), _NUM)` (line 83). Vocabulary list is in RESEARCH Pattern 4. No pattern may allow a leading `::`; no run id line.

**Top-level error handling** (lines 410-423). Copy exactly; no traceback may escape:
```python
    except KeyboardInterrupt:
        return 130
    except Exception as problem:  # noqa: BLE001 - nothing may escape as a traceback
        word = type(problem).__name__
        _quiet(printer, "error: unexpected (%s)" % (
            word if re.match(r"[A-Z][A-Za-z]{0,39}\Z", word) else "Exception"))
        return EXIT_USAGE
    finally:
        printer.flush()
```
**CI fail-safe detection** (replay_cli lines 27-29 docstring; code at ~345-346): `environ.get("GITHUB_ACTIONS") == "true"`.

**Live call** (from RESEARCH Pattern 6, verified against `psse_job/job.py:77-78`):
```python
outcome = job.run_once(
    lambda: ratings.fetch_latest_rating(env), prepared.study,
    functools.partial(writer.connect, env=env),
    prepared.case_id, prepared.case_sha256, prepared.mapping_sha256,
    clock=None, env=env, solver=engine.SOLVER)   # solver= is mandatory (F-2)
```
**Gate and refusal** (RESEARCH "mode gate"): `live` only if `environ.get("PANDAPOWER_LIVE") == "true"`; `if mode == "live" and engine.is_placeholder(backend)` print `placeholder: refused`, return 2 before any connect.
**Temp folder**: `tempfile.mkdtemp(prefix="pandapower_hourly_", dir=os.environ.get("RUNNER_TEMP") or None)` with `shutil.rmtree` in `finally`.
**Sinks**: no analog in repo; implement per RESEARCH Pattern 4 (dup fds 1/2 to devnull, `logging.disable`, ignore warnings, restore in `finally`).

---

### Soak function (pure, transform)

**Analog:** `backend/psse_job/gaps.py`

**Data source and normalisation** (lines 196-214, 226-247). `fetch_runs(conn)` returns `(slot_time, solver, outcome)`; `fetch_current_slot(conn)` returns aware UTC; use `_utc` and `_solver_label`. The walk shape to mirror:
```python
def compute_gaps(runs, current_slot):
    current = _utc(current_slot)
    result = {}
    for solver, by_slot in _group(runs).items():
        ...
        hour = min(by_slot)
        while hour < current:
            outcomes = by_slot.get(hour)
            if outcomes is None: ...   # no_run
            elif all(outcome == "failed" for outcome in outcomes): ...  # failed_only
            hour += _HOUR
```
Soak counts backward from `current_slot - 1h` instead (RESEARCH "soak count" listing); pass when count >= 24. Per-solver check call: `gaps.run_by_solver(env, since=None, until=None, fail_on_gaps=False, out=None, connect=None, expected=(), failing=None)` (line 292) with `expected=(engine.SOLVER,)`; exits `EXIT_OK=0`, `EXIT_GAPS=5`, `EXIT_CHECK_FAILED=6` (lines 40-42).

---

### `backend/tests/pandapower_soak_test.py` (test, transform)

**Analog:** `backend/tests/psse_gaps_solver_test.py`

**Constants and fake connection** (lines 40-99): `H`, `HOUR`, `PP`, `PSSE`, `_FakeConnection` (asserts `gaps.RUNS_SQL` / `gaps.CURRENT_HOUR_SQL`, records `("set","read_only",True)`), `_check(rows, current=H, **kwargs)`.

**Independent-oracle pattern** (lines 140-201): plain-loop `reference_gaps`, `_random_rows(rng)`, `random.Random(20261118)` loop of 300 seeds, with a non-vacuity assertion (`assert with_gaps > 50`). Write a plain-loop oracle for the trailing count, run 300 seeds, plus the hand cases listed in RESEARCH Pattern 6 (exactly 24, 23 plus gap, failed_only hour inside, PSS/E row not filling a pandapower hour, current-hour-only rows, empty table). Also assert the read-only event sequence (lines 128-134) for the soak step's connection.

---

### `backend/tests/pandapower_hourly_pg_test.py` (test, DB tier CRUD)

**Analog:** `backend/tests/pandapower_study_job_test.py`

**Imports and skip guard** (lines 30-51):
```python
pandapower = pytest.importorskip("pandapower")
_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import pandapower_study_fixture as study_fixture  # noqa: E402
import psse_fakes  # noqa: E402
import psse_local_pg as pg_helper  # noqa: E402
from pandapower_job import engine  # noqa: E402
from psse_job import job, run_record, writer  # noqa: E402
```
**Fixtures** (lines 57-78): module `pg` via `pg_helper.cluster(tmp_path_factory)` + `apply_solver_schema`, `clean_pg` via `pg_helper.reset`, autouse `_private_temp` setting `tempfile.tempdir` to `tmp_path/scratch`. Assert `os.listdir(tempfile.gettempdir()) == []` afterwards (temp-cleanup claim).
**Helpers** (lines 81-110): `_clock`, `_connect(admin_url)` using `pg_helper.role_url(admin_url, "dlr_psse_writer")`, `_counts`, `_run_row` via `pg_helper.admin_rows`; `pg_helper.RESULT_TABLES` for the four-table fingerprint (count plus md5 in fixed order). Include the live positive control (fingerprint changes by exactly one run row set) so "unchanged" can fail. Assert stored row `solver == "pandapower"` and run id starts `pp-`.

---

### `backend/tests/pandapower_hourly_leak_test.py` (test, planted identifiers)

**Analog:** `backend/tests/pandapower_replay_output_test.py`

**Header, skip, imports** (lines 24-37):
```python
pytest.importorskip("pandapower")
import pandapower_replay_fixture as fixture  # noqa: E402
import private_leak_scan  # noqa: E402
_PATTERNS = replay_cli.CLI_LINE_PATTERNS     # use hourly.<PATTERNS>
_TOKEN = private_leak_scan._TOKEN
```
**Reusable helpers** (lines 48-120): `_collect_numbers`, `_set_b`, `_set_a` (`private_leak_scan.derive_needles(os.path.join(repo, "data", "private"))` on a throwaway tree under `tmp_path`), `_write`, `_first`, `_in_vocabulary` (every line matches a pattern), `_tokens_of`, `_scans_clean` (guards against empty needle sets, then `scan_paths([path], needles=..., root=repo)` must equal `[]`). Import or copy them. Add planted fake writer URL / key / base64 needles, capture via `capfd` + `caplog` as well as the printer, the five "teeth" (plant into a copy of clean output, require a hit, rescan clean after), and the no-line-starts-with-`::` assertion. Fixture data: `pandapower_replay_fixture.standin(...)` (line 183). Never write the marker key literal; use `cli.REPORT_MARKER`.

---

### `backend/tests/pandapower_hourly_workflow_test.py` (test, text)

**Analog:** `backend/tests/dlr_live_workflow_test.py` (no PyYAML; regex on text)

**Loader** (lines 18-25): `_REPO = os.path.join(os.path.dirname(__file__), "..", "..")`, open `.github/workflows/<file>` in text mode.
**Dispatch-only, group, permissions** (lines 28-41):
```python
assert re.search(r"^\s*workflow_dispatch:", text, flags=re.M)
for trigger in ("schedule", "push", "pull_request"):
    assert not re.search(rf"^\s*{trigger}\s*:", text, flags=re.M), trigger
assert re.search(r"^\s*group:\s*dlr-live\s*(#.*)?$", text, flags=re.M)   # pandapower-hourly
assert re.search(r"^permissions:\s*\n\s+contents:\s*read\b", text, flags=re.M)
```
**Main-only and environment** (lines 49-52): regex over `^  <jobname>:\s*\n(    .*\n)*?    if: github\.ref == 'refs/heads/main'`.
**Timeout** (lines 58-59): `timeout-minutes` equals 30 and is below 60.
**No `${{` in any `run:` body** (lines 80-91, copy the loop verbatim). Replace the inputs assertion with: no `inputs:` block and no `${{ inputs.` anywhere. Add: `PANDAPOWER_LIVE: ${{ vars.PANDAPOWER_LIVE }}` present, no `secrets.PANDAPOWER_LIVE`, `-I -B` run line, step order install < run < gap < cleanup (lines 101-108 pattern). Do not pin file bytes (CRLF on Windows).

---

### `docs/data-science/decisions/pandapower_hourly_runbook.md` and the cron job section

**Analog:** `docs/data-science/decisions/dlr_live_runbook.md` (cited lines 46-58 cron-job.org settings, 63 minute choice, 76 separate token, 94 session pooler, 207-209 25-failure disable; not re-read this session, planner should open it for exact section layout). Say where each secret lives (repo vs `production` environment); the runbook table is stale on `SUPABASE_DB_URL`.

### Decision records (`pandapower_live_write_decision.md`, `05-RETENTION-DECISION.md`)

**Analog:** `docs/data-science/decisions/pandapower_network_data_decision.md` lines 1-30. Layout to copy:
```markdown
# <title>

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-11-20 (UTC) |
| **Deciders** | <name> |

Scope: <one sentence>

## Decision
## Context
## Consequences
**Positive:** ...
**Negative:** ...
```
Retention document must state the corrected rate (about 5,100 rows a day, D-01) and the owner-named database size trigger. The OPS-03 document carries a dated line naming who decided, after NET-03 and AGR-02 passed.

---

## Shared Patterns

### Closed-vocabulary output (D-05, D-14)
**Source:** `backend/pandapower_job/replay_cli.py` lines 58-115 and 417-421.
**Apply to:** `hourly.py` and every test that captures output (`_in_vocabulary` in the replay output test).

### Fail closed, no traceback
**Source:** `replay_cli.py` lines 410-423 (`except Exception` prints a class name only).
**Apply to:** `hourly.py` `main`.

### Secrets via `env:` only, never inline `${{ }}` in `run:`
**Source:** `.github/workflows/dlr_live.yml` lines 71-78; enforced by `dlr_live_workflow_test.py` lines 80-91.
**Apply to:** the workflow and its text test.

### Solver tag on every write
**Source:** `backend/tests/pandapower_study_job_test.py` header (lines 16-22) and `job.run_once(..., solver=engine.SOLVER)`.
**Apply to:** live path in `hourly.py` and the DB-tier test.

### Throwaway scratch temp folder
**Source:** `pandapower_study_job_test.py` lines 72-78 (`_private_temp` autouse fixture).
**Apply to:** every Phase 5 test that makes a runner temp folder.

### Windows caveat
No file-permission-bit assertions and no byte-hash pins of workflow/SQL files on this checkout (skip when `os.name == "nt"`).

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| stream/logging sinks (fd 1/2 to null, `logging.disable`) in `hourly.py` | utility | I/O redirection | No existing code redirects file descriptors; use RESEARCH Pattern 4 and the planted-error leak test cases |
| base64 secret decode to temp folder and owner `bundle` / `scan-log` commands | utility | file-I/O | Nearest relatives are `private.write_private_bytes` (owner-side writes) and `engine.load_recorded_backend`, but no base64 transport exists; follow RESEARCH Pattern 3 |
| Dry-run path with no connect parameter | service | transform | `launcher._dry_run_mode` (PSS/E, private, not importable); follow RESEARCH Pattern 5 using public `psse_job` functions |

## Metadata

**Analog search scope:** `.github/workflows/`, `backend/pandapower_job/`, `backend/psse_job/gaps.py`, `backend/tests/` (workflow, replay output, study job, gaps solver tests), `docs/data-science/decisions/`.
**Files read:** 9 (plus the two required-reading files). `git ls-files` confirmed the analogs are tracked; the new files are not yet tracked.
**Not read (cited from RESEARCH.md only):** `dlr_live_runbook.md`, `04-REPLAY-RECORD.md`, `psse_job/job.py`, `psse_local_pg.py`.
**Pattern extraction date:** 2026-11-25
