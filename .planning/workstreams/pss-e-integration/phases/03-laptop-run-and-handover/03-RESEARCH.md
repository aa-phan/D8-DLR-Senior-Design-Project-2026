# Phase 3: Laptop Run and Handover - Research

**Researched:** 2026-10-28
**Domain:** Windows launcher for a PSS/E (`psspy`) study job: interpreter and driver choice, Task Scheduler hourly run, run-record gap check, scoped-credential proof, laptop runbook and setup guide
**Confidence:** HIGH on repo contracts (every contract value below was read this session); MEDIUM on Task Scheduler and psycopg facts (Microsoft docs, psycopg docs and PyPI metadata read this session); LOW on everything specific to PSS/E install layout, Python version per PSS/E release, licensing and example cases (community forum posts and vendor blogs only; Siemens documentation is behind a login and PSS/E is not installed here, so nothing PSS/E-side could be run)

<user_constraints>
## User Constraints (from the spawn prompt; no CONTEXT.md exists for this phase)

### Locked Decisions
- The study code (`backend/psse_job/`, 521 tests) is built and tested against a fake `psspy` only. The real run needs PSS/E on a teammate's licensed Windows laptop. The teammate says their Python "should be compatible" (UNVERIFIED: PSS/E version and Python must be asked).
- The user is NOT an administrator on this Windows machine and the laptop's rights are unknown. The repo is public. The real case, the city-to-branch mapping, credentials and connection strings never go in git. The job's credential is the scoped `dlr_psse_writer` role only. No migrations are written by this workstream.
- The real case is probably the IEEE 39-bus New England test system (not confirmed; the Prior Art Report says the model is "based on the New England network"). The team meets first. The real case, the mapping and production-pipeline Phase 6 (four result tables, `dlr_psse_writer`, ratings read access) may not exist for some time.
- Phase requirement IDs this phase must address: DBX-02, TST-02, SCH-01, SCH-02, DOC-01.
- Success criteria (ROADMAP): (1) one real end-to-end run on the laptop writes a run record and results readable from the database; (2) the job's credential reads ratings and writes the result tables, and an attempt to change `city_rating` with it is rejected; (3) Task Scheduler runs the job hourly with no overlap, and an hour with no run shows as a gap through a stated query or check; (4) a setup guide lets someone else install the job and start hourly runs.
- Git rules (hard): stay on `feature/pss-e-integration`; no branch/switch/push/fetch/merge/rebase/reset/stash; only `git add <named file>` and one commit.

### Claude's Discretion
Launcher shape, lock mechanism, credential storage, task definition format, gap query shape, proof design, plan/wave structure.

### Deferred Ideas (OUT OF SCOPE)
Always-on host, dashboard views of PSS/E results (F7), a standalone migration, choosing the grid case or mapping, PSS/E ACCC and PV/QV engines (REQUIREMENTS.md "Future Requirements" and "Out of Scope").
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DBX-02 | Job reads ratings only through Phase 6's access and writes only to the PSS/E result tables; its credential cannot change `city_rating` | Finding F1: there are TWO credentials (REST publishable key reads; `dlr_psse_writer` writes). "Credential proof" section: safe catalog + `where false` + rolled-back-insert design, Mac version on local Postgres, live version after Phase 6 |
| TST-02 | One real end-to-end run on the laptop against the real case writes a run record and results readable from the database | "Runbook" (probe, dry-run smoke on a PSS/E example case, real case, read-back); dry-run mode avoids permanent smoke rows (F4) |
| SCH-01 | Task Scheduler runs the job hourly, no overlapping runs | "Task Scheduler" settings, XML template, `msvcrt` job lock, exit codes |
| SCH-02 | An hour with no run is visible as a gap through a stated query or check | "Gap check" (SQL on `psse_run.slot_time` plus a small Python check and a differential test) |
| DOC-01 | Setup guide for the laptop lets someone else install and start the hourly job | "Setup guide contents" and the ask-the-teammate list |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

No `CLAUDE.md` exists in the repo [VERIFIED: `ls CLAUDE.md` returned "No such file or directory" this session]. House rules come from Phases 1 and 2: `backend/psse_job/*.py` is standard library only, Python 3.7 syntax, and may import `psycopg` only inside a function; the import gate `backend/tests/psse_contract_test.py` globs `psse_job/*.py` and keeps an allow-list (extending it is a deliberate, commented one-line edit, as 02-03 and 02-07 did). Auto-memory: never create/switch/delete branches or change remote state unasked.

## Summary

The job logic is finished; Phase 3 is a launcher, a lock, a gap check, a credential proof, a scheduler definition and two documents, plus a short list of human steps on the laptop. Most of it can be written and tested now with the fake `psspy` and local Postgres. What cannot: anything that touches real `psspy`, the laptop's rights, the real case, or Phase 6's live database.

Five findings change what the planner should assume:

1. **DBX-02 has two credentials, not one.** The writer role holds INSERT and SELECT on the four result tables and nothing on `city_rating`, `pipeline_run` or `latest_rating`; ratings are read over REST with the publishable key. So "the credential reads ratings" is true of the REST key, "writes the result tables" of the role, and "changing `city_rating` is rejected" must be shown for both. The Mac-side half of the role proof already exists (`psse_schema_pg_test.py:177-194`).
2. **The Python and driver match is a table, not a choice.** `psycopg` 3.3.x needs Python 3.10+, so a 3.9 interpreter (PSS/E 35.x per forum reports) takes `psycopg[binary]==3.2.13`, and a 3.7 interpreter takes `==3.1.20`. Both have 64-bit Windows wheels; no 32-bit wheel exists for any of them, which rules out PSS/E 34.x (reported 32-bit).
3. **Only a fresh process per run is safe.** `psspy` holds process-global state (A12 in the Phase 2 note) and a forum thread reports that ending a thread does not release the PSS/E license; one launcher process per run, with an OS-released file lock, is both the scheduler contract and the license contract.
4. **A smoke run must not write to the live tables.** `psse_run` is append-only and the writer has no DELETE, so a smoke row is permanent. Add a `--dry-run` that runs the real study and `validate_results` but never connects, and keep the one real write for the real case.
5. **Task Scheduler defaults are wrong for a laptop.** `DisallowStartIfOnBatteries` and `StopIfGoingOnBatteries` default to true, `StartWhenAvailable` and `WakeToRun` to false (Microsoft schema). The template below sets them deliberately, uses `InteractiveToken` (no password, no administrator, no batch-logon right), `IgnoreNew` and a 45-minute limit.

**Primary recommendation:** Build, now and on the Mac, a psspy-free `launcher.py` (config file, lock, exit codes, dry-run, preflight) with a thin `backend/psse_run_hourly.py` entry that owns the `psspy` import, a `gaps.py` plus SQL file, a `credcheck.py`, a Task Scheduler XML template and the setup guide and runbook; then close the laptop and real-case items as a short human checklist in the order: ask versions, probe, dry-run on `savnw.sav`, hourly dry-runs, then (after Phase 6 and the real case) credential proof and the real write.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Start PSS/E, import `psspy`, silence output, one process per run | Entry script (`backend/psse_run_hourly.py`, outside the gated package) | Launcher module (receives a loader callable) | `psse_job` may not import `psspy` (gate `_NEVER_IMPORTED`); only the entry script touches it |
| Study, ratings choice, record, atomic write | `psse_job` (Phases 1-2, done) | PSS/E engine | Unchanged; launcher calls `study.prepare_run` then `job.run_once` |
| No-overlap guarantee | OS file lock in `psse_job/lock.py` | Task Scheduler `IgnoreNew` | Scheduler policy is the first line; the lock covers manual runs and scheduler faults |
| Hourly trigger, time limit, battery and wake policy | Windows Task Scheduler (XML in repo) | Launcher exit codes | Scheduler owns timing; the job owns correctness |
| Credential storage | ACL-protected file outside the repo | Process environment (override) | Read by the launcher into a dict passed as `env=`; never in task arguments |
| Gap detection | Database (SQL on `psse_run.slot_time`) | Python wrapper `psse_job/gaps.py` | One SQL statement is the single source of truth; Python only runs and formats it |
| Credential proof | Database privilege catalog + rolled-back statements | REST (PostgREST) status codes | Privileges live in Postgres; the ratings leg lives in PostgREST |
| Case and mapping custody | Laptop filesystem outside the repo (`psse_local/` is git-ignored) | Setup guide | Public repo: grid identifiers never committed |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python interpreter that matches the installed `psspy` folder | 3.7 / 3.9 / 3.11 depending on PSS/E (see matrix) | Runs launcher and `psse_job` | `psspy` is a compiled module per Python minor; a mismatch gives "Bad magic number" or "DLL load failed" [CITED: psspy.org forum, question 8235 comment and search summary on 'Bad magic number'] |
| `psycopg[binary]` | per matrix: 3.1.20 / 3.2.13 / 3.3.6 | Writer connection (already used by `writer.py`) | Already the repo driver; `writer.py` uses only API common to 3.1-3.3 (Phase 1 verification note); 3.0 lacks `prepare_threshold` ("new in Psycopg 3.1") [CITED: psycopg.org/psycopg3/docs/api/connections.html] |
| Python stdlib (`msvcrt`, `fcntl`, `argparse`, `logging`, `socket`, `json`, `os`) | n/a | Launcher, lock, config file, preflight | Same constraint as Phases 1-2 (no site packages on PSS/E's interpreter) |
| Windows Task Scheduler (XML import) | built in | Hourly trigger | Required by SCH-01; no install |
| `icacls` | built in | Restrict the credential file to the user | No administrator needed for the user's own files [ASSUMED] |
| pytest | 9.0.3 (repo pin) | Tests | Existing framework [VERIFIED: Phase 2 verification note] |

### psycopg matrix (read from PyPI JSON this session)
| Interpreter | Pin | `requires_python` | 64-bit Windows wheel | Extra dependencies for an offline wheelhouse |
|-------------|-----|-------------------|----------------------|----------------------------------------------|
| 3.7 | `psycopg[binary]==3.1.20` | `>=3.7` | `cp37-cp37m-win_amd64` | `typing-extensions>=4.1`, `backports.zoneinfo>=0.2.0` (python < 3.9; has `cp37` win wheel), `tzdata` |
| 3.8 | `==3.2.13` (or 3.1.20) | `>=3.8` | `cp38-cp38-win_amd64` | `typing-extensions>=4.6`, `backports.zoneinfo`, `tzdata` |
| 3.9 | `==3.2.13` | `>=3.8` | `cp39-cp39-win_amd64` | `typing-extensions>=4.6`, `tzdata` |
| 3.10 to 3.12 | `==3.3.6` (repo pin) | `>=3.10` | `cp310`, `cp311`, `cp312` `win_amd64` | `typing-extensions>=4.6` (python < 3.13), `tzdata` |
| 32-bit Python (PSS/E 34.x) | none | n/a | no `win32` wheel exists for any of these | would need pure-Python psycopg plus a 32-bit `libpq.dll`: do not support |

[VERIFIED: `https://pypi.org/pypi/psycopg/<v>/json` and `.../psycopg-binary/<v>/json`, fetched and parsed this session; `psycopg-binary` 3.2.13 lists `cp38`-`cp314` `win_amd64` wheels, 3.1.20 lists `cp37`-`cp312`, 3.3.6 lists `cp310`-`cp315`; no `win32` file in any.] psycopg docs: "Drop support for Python 3.8 (ticket #976) and 3.9 (ticket #1056)." in 3.3.0; latest patch lines 3.1.20, 3.2.13, 3.3.6 [CITED: psycopg.org/psycopg3/docs/news.html]. Not run: `writer.py` on 3.1.x or 3.2.x, and nothing runs on a 3.7 interpreter yet [ASSUMED].

**Installation without administrator rights (copy to the setup guide):**
```bash
# On any machine with internet; wheels are tagged for the TARGET interpreter, not this one
python -m pip download "psycopg[binary]==3.2.13" -d wheelhouse --only-binary=:all: --platform win_amd64 --python-version 3.9 --implementation cp
# On the laptop: into a folder the user owns, never Program Files
python -m pip install --no-index --find-links wheelhouse --target "%LOCALAPPDATA%\dlr-psse\site" "psycopg[binary]==3.2.13"
```
The launcher inserts `%LOCALAPPDATA%\dlr-psse\site` into `sys.path` itself. A wheel is a zip file, so if the interpreter has no pip the wheels can be extracted into that folder [ASSUMED: standard wheel format].

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| ACL-protected credential file | Windows Credential Manager (needs `keyring` or `ctypes`) | Extra third-party package per Python minor; an S4U task "has no access to ... encrypted files" so a vault read can fail [CITED: Microsoft LogonType doc]. Not recommended |
| User-level environment variable (`setx`) | the file | Visible to every process of the user and stored plaintext in `HKCU\Environment`; Task Scheduler picking up a `setx` change without a new logon is UNVERIFIED. Keep only as an override |
| `msvcrt.locking` job lock | `O_EXCL` lock file with PID check | `os.kill(pid, 0)` is not a safe liveness probe on Windows [ASSUMED]; `msvcrt` locks are released by the OS when the process dies |
| Task Scheduler repetition | `while True: sleep(3600)` Python service | Dies with the session, no limit, no overlap control; do not build |

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| psycopg | PyPI | years (3.3.6 uploaded 2026-09-18) | not returned by seam | psycopg.org | seam `SUS` (only reason: `unknown-downloads`) | Approved: named on the official install page and already pinned and owner-confirmed in `requirements.txt` (plan 04-01, 2026-10-21) |
| psycopg-binary | PyPI | years | not returned by seam | psycopg.org | seam `SUS` (`unknown-downloads`) | Approved: documented extra of psycopg; must equal psycopg's version |
| typing-extensions | PyPI | years | not returned by seam | none listed | seam `SUS` (`unknown-downloads`, `no-repository`) | Approved: declared dependency of psycopg [VERIFIED: PyPI `requires_dist`]; planner adds `checkpoint:human-verify` before installing the wheelhouse on the laptop |
| tzdata | PyPI | years | not returned by seam | github.com/python/tzdata | seam `SUS` (`too-new`: published today, `unknown-downloads`) | Same; pin the version in the wheelhouse and record hashes |
| backports.zoneinfo | PyPI | 2020 | not returned by seam | github.com/pganssle/zoneinfo | seam `SUS` (`unknown-downloads`) | Only for Python < 3.9; same checkpoint |

`gsd-tools query package-legitimacy check --ecosystem pypi psycopg psycopg-binary typing-extensions tzdata backports.zoneinfo` ran this session; every verdict is `SUS` and every reason is "no download statistics for PyPI" (plus `too-new` for tzdata), none is `SLOP`. **Packages removed due to SLOP verdict:** none. **Packages flagged SUS:** all five (statistics gap, not a content finding); the planner inserts one `checkpoint:human-verify` before the laptop wheelhouse install, which also records the wheel sha256 values from PyPI.

## Architecture Patterns

### System Architecture Diagram
```
Task Scheduler (hourly :15, interactive user, IgnoreNew, 45 min limit)
        |  python.exe -X utf8 backend/psse_run_hourly.py --config <outside repo>
        v
 entry script (only place that imports psspy)
   sys.path += PSSPY dir ; import psspy ; psspy.psseinit(N) ; silence output to local log
        |                                   (failure -> PsseUnavailable)
        v
 launcher.main(psspy_loader, argv)
   1 read config file (+ env override) ........ missing/invalid -> exit 2, nothing recorded
   2 RunLock(lock file) ........................ held -> exit 4 (skipped, nothing recorded)
   3 preflight: TCP connect to DB host:port .... unreachable -> exit 3 early (saves a licence checkout) [recommended]
   4 loader() -> psspy ; PsseUnavailable -> failing_study("load_case", ...)
   5 study.prepare_run(psspy, case, mapping)    -> PreparedRun(study, case_id, case_sha256, mapping_sha256, mapping_error)
   6 --dry-run ? select_ratings + study + validate_results, print counts, exit 0/1, NO database
   7 job.run_once(fetch=REST read, study, connect=writer.connect, case_id, hashes, env=cfg.env)
        |                                   returns RunOutcome(..., exit_code in {0,1,3})
        v
 process exit code -> Task Scheduler "Last Run Result"; lock released by the OS

 Supabase: REST latest_rating (publishable key)  |  Postgres session pooler as dlr_psse_writer (INSERT+SELECT on 4 tables)
 Gap check: SELECT on psse_run.slot_time (same role) or owner SQL editor
```

### Recommended Project Structure
```
backend/psse_run_hourly.py           # entry: psspy import + launcher.main (outside the gated package)
backend/psse_job/launcher.py         # config, preflight, flow, exit codes, dry-run (no psspy import)
backend/psse_job/lock.py             # RunLock (msvcrt / fcntl, imported lazily)
backend/psse_job/gaps.py             # runs psse_run_gaps.sql, formats, optional exit code
backend/psse_job/credcheck.py        # DBX-02 proof (role leg and REST leg), safe by construction
docs/data-science/schema/psse_run_gaps.sql        # SCH-02 statement (next to psse_results_v1_checks.sql)
docs/data-science/ops/psse_hourly_task.xml        # Task Scheduler template, placeholders only
docs/data-science/decisions/psse_laptop_setup.md  # DOC-01
docs/data-science/decisions/psse_laptop_runbook.md# TST-02 steps and what each should show
backend/tests/psse_launcher_test.py, psse_lock_test.py, psse_gaps_pg_test.py, psse_credcheck_test.py, psse_task_xml_test.py
```
Locations are recommendations; the planner may move them. The laptop installs the whole public repo (clone or ZIP), so docs paths resolve at run time.

### Pattern 1: psspy-free launcher with an injected loader
**What:** `launcher.main(argv, psspy_loader, env=None)` does everything except the import. The entry script supplies the loader. Tests pass `FakePsspy`.
**Why:** same seam as Phase 2 (psse_api receives the module). Keeps the import gate untouched.
**Exit codes:** keep the job's three and add two launcher-only codes.

| Code | Meaning | Recorded in DB? |
|------|---------|-----------------|
| 0 | ok or fallback run written, or already recorded (`EXIT_OK`) | yes |
| 1 | study failed, failed record exists (`EXIT_FAILED_RECORDED`); dry-run: validation failed | yes (dry-run: no) |
| 2 | launcher usage or config error, no run attempted | no |
| 3 | no record could be written (`EXIT_NOT_RECORDED`): the SCH-02 gap | no |
| 4 | another instance holds the lock, skipped | no |

[VERIFIED: backend/psse_job/job.py:33-35] `EXIT_OK = 0`, `EXIT_FAILED_RECORDED = 1`, `EXIT_NOT_RECORDED = 3`. [VERIFIED: study.py:387] `def prepare_run(psspy_module, case_path, mapping_path, allow_placeholder=False, clock=None):`; [VERIFIED: study.py:314-316] `PreparedRun` fields `"study", "case_id", "case_sha256", "mapping_sha256", "mapping_error"`. [VERIFIED: job.py:77-78] `def run_once(fetch, study, connect, case_id, case_sha256=None, mapping_sha256=None,\n             clock=None, env=None):`. Do not enable `RestartOnFailure`: a retry after exit 1 or 3 only duplicates a slot. Add a `--selftest` flag (import `psspy`, `psseinit`, print `psseversion`, exit 0 or 2) so the runbook's step 2 and the guide's troubleshooting have one command that isolates interpreter, path and licence problems from study problems.

If `psspy` cannot start (licence, DLL, path) the launcher still records a failed run: `study.failing_study("load_case", "PSS/E could not be started: ...")` with `case_label(case_path)` and `file_sha256` computed by the launcher (`prepare_run` itself hashes and builds a `PreparedRun`, so build the same tuple by hand). This makes licence trouble visible in the table, not only in the local log, whenever the database is reachable.

### Pattern 2: config as a dict, never `os.environ`
**What:** the launcher reads `KEY=VALUE` lines from a file outside the repo (default `%LOCALAPPDATA%\dlr-psse\job.env`), overlays real environment variables, and passes the resulting dict as `env=` to `ratings.fetch_latest_rating`, `writer.connect` and `job.run_once`.
**Why:** `redaction.env_secrets(env)` and `job.run_once(..., env=...)` already take an explicit dict, so the redactor sees exactly the secrets in use. Keys: `SUPABASE_PSSE_DB_URL`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` (names fixed in `constants.py:76-78`), plus `PSSE_CASE_PATH`, `PSSE_MAPPING_PATH` (names planned in `psse_study_definitions.md:176`; no code reads them yet), and new launcher keys `PSSE_PSSPY_DIR`, `PSSE_BIN_DIR`, `PSSE_MAX_BUSES`, `PSSE_LOG_DIR`, `PSSE_SITE_DIR`, `PSSE_ALLOW_PLACEHOLDER`.
[VERIFIED: constants.py:76-78] `ENV_SUPABASE_URL = "SUPABASE_URL"`, `ENV_PUBLISHABLE_KEY = "SUPABASE_PUBLISHABLE_KEY"`, `ENV_PSSE_DB_URL = "SUPABASE_PSSE_DB_URL"`.
**File protection:** `icacls "%LOCALAPPDATA%\dlr-psse\job.env" /inheritance:r /grant:r "%USERNAME%:(R,W)"` (user only). State plainly in the guide that this is protection from other local accounts, not from the user or an administrator, and that BitLocker status is unknown.

### Pattern 3: dry-run is a first-class mode
`--dry-run` runs `select_ratings` (a missing `SUPABASE_URL` simply gives `read_failed` static ratings, so no credential is needed), the real study, and `run_record.validate_results(results, selection)`, prints counts and the validation verdict, and never calls `connect`. It exercises everything the real run does except the write, on the real `psspy`. `--allow-placeholder` (or `PSSE_ALLOW_PLACEHOLDER=1`) feeds `prepare_run(..., allow_placeholder=True)`; [VERIFIED: mapping.py:255-258] the refusal text is "mapping file is marked placeholder; refusing it for a study (allow_placeholder is for tests and a plumbing smoke run only)", so a smoke mapping marked `"placeholder": true` can never be mistaken for a real one, and a real run (no flag) refuses it with a recorded `mapping` failure.

### Pattern 4: job lock with an OS-released file lock
```python
# psse_job/lock.py  (Python 3.7 syntax; msvcrt/fcntl imported lazily; needs the allow-list edit)
class RunLock(object):
    def __init__(self, path):
        self.path, self._fh, self.acquired = path, None, False
    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._fh = open(self.path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)   # one attempt, OSError if held
            else:
                import fcntl
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.acquired = True
        except (OSError, IOError):
            self._fh.close(); self._fh = None
        return self
    def __exit__(self, *exc):
        if self._fh is not None:
            self._fh.close()      # closing the handle releases the lock; the OS also does so on death
```
[CITED: docs.python.org/3.9/library/msvcrt.html] `LK_NBLCK`: "Locks the specified bytes. If the bytes cannot be locked, OSError is raised"; the locked region "extends from the current file position for nbytes bytes" (so `seek(0)` first); `LK_LOCK` retries ten times at one second, which is why `LK_NBLCK` is used. Hold the lock from before `prepare_run` until after `run_once` returns. A second instance exits 4 immediately and writes nothing: it never started a study, so there is no run to record. Test on the Mac with `fcntl`; the Windows branch is exercised on the laptop (unit-test it with a fake `msvcrt` module object).

### Pattern 5: psspy bootstrap in the entry script
```python
# backend/psse_run_hourly.py (outside psse_job, so the gate does not apply; keep it small)
def load_psspy(cfg):
    sys.path.insert(0, cfg["PSSE_PSSPY_DIR"])            # e.g. ...\PSSE35\35.x\PSSPY39 (ask the teammate)
    if hasattr(os, "add_dll_directory") and cfg.get("PSSE_BIN_DIR"):
        os.add_dll_directory(cfg["PSSE_BIN_DIR"])        # Python 3.8+: PATH is no longer searched for DLLs [ASSUMED]
    import psspy                                          # PsseUnavailable on ImportError
    psspy.psseinit(int(cfg.get("PSSE_MAX_BUSES", "20000")))
    for name in ("report_output", "progress_output", "alert_output", "prompt_output"):
        getattr(psspy, name)(2, cfg["psse_log_file"], [0, 0])   # to a local file, not the console [ASSUMED forms]
    return psspy
```
Evidence: an accepted forum answer for PSS/E 35.3.3 on Python 3.9 uses `sys.path.append(...\PSSE35\35.3\PSSPY39)`, `import psspy`, `psspy.psseinit()` and reports "PSS(R)E Version 35" printed; the single-installation shortcut is `import psse35` then `import psspy` [CITED: psspy.org question 9121; community forum, MEDIUM]. A Siemens 2021 user-group handout (via search summary) shows `import psse35; psse35.set_minor(2); import psspy; psspy.psseinit()` [CITED: search result, LOW]. `psseinit(buses)` takes the maximum number of buses and memory grows with it [CITED: whit.com.au/blog/2012/01/how-max-buses-setting-affects-your-code, search summary, LOW]. Output calls: `progress_output(6,'',[])` silences and `progress_output(1,'',[])` restores [CITED: psspy.org forum answers, LOW]; the `[0, 0]` option list and the file form `progress_output(2, path, [0, 0])` come from a vendor blog [CITED: keentelengineering.com, LOW]. "ImportError: DLL load failed while importing psscommon" is a reported failure on 35.x [CITED: psspy.org question 8235 comment, 2023]. All four output functions are unexercised by any repo test: add them to the fake `psspy` and guard with `getattr` so a missing one is logged, not fatal. These names are outside `psse_api.SURFACE`; list them in a separate `LAUNCH_SURFACE` tuple that `run_probe`'s signature check can also cover.

### Pattern 6: Task Scheduler definition as a committed XML template
The template carries `@@PLACEHOLDER@@` values for paths and no secret, and is filled by the person installing it. See Code Examples. Import with typed commands (not a `.ps1`), so PowerShell execution policy never applies: execution policy governs scripts, and typed cmdlets are not scripts [ASSUMED].

### Anti-Patterns to Avoid
- **Connection string in the task's Arguments, XML or `setx`:** arguments are visible in Task Scheduler and process listings. Config file only.
- **`RestartOnFailure`, `Parallel`, `Queue`, `StopExisting`:** any of these breaks "no overlapping runs" or duplicates a slot.
- **Smoke write to the live tables:** permanent (append-only, no DELETE for the writer). Dry-run first.
- **Running as SYSTEM or "whether logged on or not":** needs administrator or the batch-logon right, and changes the user profile and licence context PSS/E sees.
- **A long-lived process or a loop around `psspy`:** one study per process (A12).
- **Importing `psspy` or `msvcrt` in `psse_job/*.py` without the gate edit:** the contract test fails.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Hourly scheduling, overlap policy, kill-on-overrun | Python sleep loop, PID files | Task Scheduler `IgnoreNew` + `ExecutionTimeLimit` | Documented OS behaviour; no custom process to keep alive or supervise |
| Mutual exclusion | PID file with liveness guess | `msvcrt.locking(LK_NBLCK)` | OS releases it on process death |
| Missing-hour detection | Python loop over timestamps | SQL `generate_series` left-joined to `psse_run.slot_time` | One auditable statement; owner can run it in the SQL editor |
| Safe privilege proof | Mutating `city_rating` and reverting | `has_table_privilege`, `where false` statements, `force_rollback` | Nothing can survive |
| Secret redaction | New regexes | `psse_job.redaction.redact` and `env_secrets(env)` | Already ports the repo's rules and covers pooler user, project ref and host |
| Wheel resolution on the laptop | Hand-copying files | `pip download --platform ... --python-version ...` + `--no-index --find-links --target` | Resolves `typing-extensions` and `tzdata` |
| Connection-string parsing | Splitting on `@` | `urllib.parse` (already in `writer.py`) | Percent-encoded passwords |

**Key insight:** every hard part of this phase already has an owner: the job owns correctness, Postgres owns privileges and the slot arithmetic, Windows owns timing. The launcher should be glue that cannot add a failure mode the owners do not already report.

## Common Pitfalls

### Pitfall 1: licence or GUI dialog hangs the run
**What goes wrong:** `psspy.psseinit()` runs in the user's session; a licence prompt or "demo" banner waits for a click nobody sees.
**Why:** `InteractiveToken` tasks run in the interactive session, and a forum reply says that when the licence or dongle is unavailable PSS/E falls back to a demo version [CITED: psspy.org search summary, LOW]; licence type for this laptop is unknown (a campus floating licence would need VPN [CITED: Clemson example, LOW]).
**Avoid:** 45-minute `ExecutionTimeLimit` with `AllowHardTerminate`; log the PSS/E banner to the local file; setup guide asks for the licence type; the probe's `version` row shows the edition string.
**Warning signs:** "Last Run Result" 0x41306 (task terminated, [ASSUMED] code) and no run record for the hour.

### Pitfall 2: the licence is not released between runs
**What goes wrong:** a forum thread reports "closing the thread does not close the license" [CITED: psspy.org question 507, 2012, LOW]. Only process exit is safe, and a hard kill at the time limit may leave the seat checked out until the licence server times out [ASSUMED].
**Avoid:** one process per run (the design); keep the study inside its own budget (`max_runtime_seconds=1500.0`, [VERIFIED: settings.py:117]) so the hard kill is the exception.

### Pitfall 3: non-administrator restrictions
**What goes wrong:** PSS/E's Python layer, in v32/33-era forum reports, needed write access to `HKLM\SOFTWARE\PTI\License` (spelled "Licence" in one post) on import [CITED: psspy.org questions 347 and 726 summaries, LOW]; whether 35.x still does is unknown. Registering a task as another user, or "whether logged on or not", needs the batch-logon right that standard users lack by default [CITED: Microsoft TechNet 'Task Security Context' via search summary, MEDIUM]; schtasks docs say "Only Administrators can schedule tasks, regardless of the value of /ru" in the SYSTEM-account section [CITED: learn.microsoft.com schtasks-create], which does not settle the standard-user-for-self case.
**Avoid:** `InteractiveToken`, `RunLevel LeastPrivilege`, task for the same user; a human checkpoint "register the task" with the fallback "ask the teammate to register it from their own session".

### Pitfall 4: the laptop is asleep
**What goes wrong:** no run, a gap. `WakeToRun` is unreliable on Modern Standby laptops (Windows 11 default hardware), especially on battery or signed out [CITED: Microsoft Q&A 'Regarding waking up from sleep on a Modern Standby PC' and HP community, search summaries, MEDIUM]. Hibernate and lid-close behave the same.
**Avoid:** set `WakeToRun true` anyway, check `powercfg /a` and "Allow wake timers" in the setup guide, and state the product position: only while the laptop is on (REQUIREMENTS "Always-on hourly guarantee" is out of scope). The gap check makes it visible.

### Pitfall 5: catch-up runs and duplicate slots
**What goes wrong:** `StartWhenAvailable true` starts a missed run at wake, in the wake hour's slot, and the next scheduled run follows in the same slot; the earlier hour is still a gap because `slot_time` comes from the actual start. Two rows per slot are legal (append-only), but they burn licence time.
**Avoid:** recommended `StartWhenAvailable false` (a missed hour stays a visible gap, no burst after wake). Setting it true is acceptable; say so in the guide.

### Pitfall 6: `slot_time` is UTC and the laptop clock decides it
`slot_time` is "the hour floor of `started_at` in UTC" [VERIFIED: psse_results_v1.sql:43] `slot_time timestamptz not null constraint psse_run_slot_time_hour_ck check ((slot_time at time zone 'UTC') = date_trunc('hour', slot_time at time zone 'UTC'))`, and `started_at` is the laptop clock (job.py: `clock` default is `datetime.now(datetime.timezone.utc)`). A clock more than a few minutes off moves a run into the wrong slot and creates a false gap plus a double slot. Sync check in the guide: `w32tm /query /status`. Diagnostic that needs no new column: `created_at` is database time, `finished_at` is laptop time, so `created_at - finished_at` approximates skew plus write latency; list runs where it exceeds 5 minutes in the gap tool output. Daylight saving moves local time by an hour; the XML uses a fixed wall-clock minute and the check works only in UTC, so a spring-forward or fall-back hour may show one gap or one doubled slot [ASSUMED].

### Pitfall 7: timing against the 90-minute rule
The spec note: a job started after about HH:30 with the current slot's row not yet written finds the previous row older than 90 minutes and goes all-static with reason `stale` [VERIFIED: psse_results_v1.md:175]. Start at HH:15: even if the current hour's row is late, the previous hour's row is 75 minutes old, still fresh. A study of up to 25 minutes still ends before HH:45. Late starts (after wake) after HH:30 are visible as `stale` in `ratings_used`. Until Phase 7 every row is provisional, so all runs are static anyway.

### Pitfall 8: Windows console encoding and quoting
The default text encoding on Windows is not UTF-8: parsing the PyPI JSON in this session with `open()` and no encoding raised `UnicodeDecodeError: 'charmap' codec can't decode byte 0x81` [VERIFIED: observed this session]. Use `python -X utf8` in the task, open every file with `encoding="utf-8"`, and `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`. In the task XML put each path with spaces in double quotes inside `<Arguments>`; `C:\Program Files\...` is the usual trap. Do not rely on `%VAR%` expansion inside `<Command>`; the installer substitutes literal paths [ASSUMED].

### Pitfall 9: XML import encoding
A task XML saved as UTF-8 but declared UTF-16 (or the reverse) is rejected as malformed [ASSUMED, common failure]. Commit UTF-8 with a UTF-8 declaration and import it as a string (`Register-ScheduledTask -Xml (Get-Content -Raw -Encoding UTF8 ...)`), which avoids file-encoding detection.

### Pitfall 10: console window and `pythonw`
`python.exe` may flash a console each hour in the user's session. `pythonw.exe` has `sys.stdout` of `None`, which breaks `print` and possibly `psspy` banners [ASSUMED]. Default to `python.exe`, log to file, and test `pythonw` only if the flash is a problem.

### Pitfall 11: antivirus or application control
A freshly unzipped script, a `.pyd` in a `--target` folder, or a task action pointing at a new path can be blocked or quarantined [ASSUMED]. Setup guide lists the symptom ("task runs, exits at once, nothing in the log") and the fix path: ask the owner of the machine to allow the folder. The probe and `--selftest` should be the first things run by hand.

### Pitfall 12: network paths
IPv6-only direct connection: Supabase direct connections are IPv6 unless the add-on is bought; the shared session pooler is IPv4 on all plans [CITED: supabase.com/docs/guides/database/connecting-to-postgres]. The handoff note already says to use the session pooler. A campus or hotel network may block ports 5432 and 6543 [ASSUMED]: the preflight is one `socket.create_connection((host, port), timeout=5)`.

### Pitfall 13: the REST leg of the credential proof must not be able to change data
A `PATCH` proof against `city_rating` must match zero rows (`?city=eq.__no_such_city__`) so that, if the key were wrongly allowed to write, no real row changes. PostgREST maps error 42501 to 401 when unauthenticated and 403 when authenticated [CITED: docs.postgrest.org/en/stable/references/errors.html]; expect 401 or 403 and treat any 2xx as a FAIL.

## Code Examples

### Task Scheduler template (`docs/data-science/ops/psse_hourly_task.xml`)
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>DLR PSS/E hourly study job. No secrets in this file.</Description>
  </RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <StartBoundary>2026-11-01T00:15:00</StartBoundary>
      <Enabled>true</Enabled>
      <Repetition><Interval>PT1H</Interval></Repetition>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>false</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <WakeToRun>true</WakeToRun>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT45M</ExecutionTimeLimit>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>@@PYTHON_EXE@@</Command>
      <Arguments>-X utf8 "@@ENTRY_SCRIPT@@" --config "@@CONFIG_FILE@@"</Arguments>
      <WorkingDirectory>@@WORK_DIR@@</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
```
Settings basis [CITED: learn.microsoft.com settingsType complex type, read this session]: `MultipleInstancesPolicy` "default="IgnoreNew""; `DisallowStartIfOnBatteries` and `StopIfGoingOnBatteries` default `true`; `StartWhenAvailable` default `false` ("start the task at any time after its scheduled time has passed"); `WakeToRun` default `false`; `ExecutionTimeLimit` is a duration, "A value of PT0S will enable the task to run indefinitely" (the schtasks documentation's verbose example shows the usual default as "Stop Task If Runs X Hours and X Mins: 72:0"). `MultipleInstancesPolicy` values [CITED: learn.microsoft.com]: "Parallel", "Queue", "IgnoreNew: Default. Does not start a new instance if an existing instance of the task is running.", "StopExisting". `InteractiveToken`: "User must already be logged on. The task will be run only in an existing interactive session." `S4U`: "no password is stored by the system and there is no access to the network or encrypted files." A `Repetition` with an `Interval` and no `Duration` repeating indefinitely is [ASSUMED]; "If you specify a repetition duration for a task, you must also specify the repetition interval" is the documented rule, so verify the registered task with `Get-ScheduledTaskInfo` (NextRunTime must be the next :15) and `schtasks /query /tn DLR-PSSE-Hourly /xml`. `PT45M` is the budget `1500 s` (25 min) plus load, solve overrun (one `fnsl` cannot be interrupted, [VERIFIED: psse_study_definitions.md:178]) and write, and is below the hour.

Register (typed commands, no `.ps1`; run as the same user who will own the task):
```powershell
$xml = (Get-Content -Raw -Encoding UTF8 "$env:LOCALAPPDATA\dlr-psse\psse_hourly_task.filled.xml")
Register-ScheduledTask -TaskName "DLR-PSSE-Hourly" -Xml $xml
Get-ScheduledTaskInfo -TaskName "DLR-PSSE-Hourly"        # LastTaskResult, NextRunTime
Start-ScheduledTask   -TaskName "DLR-PSSE-Hourly"        # test run now
Unregister-ScheduledTask -TaskName "DLR-PSSE-Hourly" -Confirm:$false   # uninstall
```
Fallback if the module is unavailable: `schtasks /create /tn DLR-PSSE-Hourly /xml "<filled file>" /f` ("/xml: Creates a task specified in the XML file", [CITED: schtasks-create]); `schtasks /create /sc hourly /st 00:15` cannot set `MultipleInstancesPolicy`, battery or wake flags, so it is not used.

### Gap statement (`docs/data-science/schema/psse_run_gaps.sql`) - UNTESTED, must be run on local Postgres in the plan
```sql
-- One row per hour (UTC slot) between the first run and the last CLOSED hour that has no complete result set.
-- gap_kind: no_run      = no psse_run row at all (laptop off or asleep, database unreachable, process killed)
--           failed_only = rows exist but every one is failed (the job ran, the study did not complete)
with bounds as (
    select min(slot_time) as first_slot,
           (date_trunc('hour', now() at time zone 'UTC') at time zone 'UTC') - interval '1 hour' as last_closed_slot
    from public.psse_run
),
expected as (
    select g.slot_time
    from bounds b, generate_series(b.first_slot, b.last_closed_slot, interval '1 hour') as g(slot_time)
),
seen as (
    select slot_time, count(*) as runs,
           count(*) filter (where outcome in ('ok', 'fallback')) as complete_runs,
           count(*) filter (where outcome = 'failed') as failed_runs
    from public.psse_run group by slot_time
)
select e.slot_time,
       case when s.slot_time is null then 'no_run' else 'failed_only' end as gap_kind,
       coalesce(s.runs, 0) as runs, coalesce(s.failed_runs, 0) as failed_runs
from expected e left join seen s on s.slot_time = e.slot_time
where s.slot_time is null or s.complete_runs = 0
order by e.slot_time;
```
It fits the existing spec without a DDL change: `slot_time` is `timestamptz not null`, UTC hour-floored by a CHECK, and indexed [VERIFIED: psse_results_v1.sql:70] `create index if not exists psse_run_slot_time_idx on public.psse_run (slot_time desc);`; the writer holds `select` through [VERIFIED: psse_results_v1.sql:181,185-186] `grant select, insert on public.psse_run, ... to dlr_psse_writer;` and `create policy dlr_psse_writer_select on public.psse_run for select to dlr_psse_writer using (true);`, so the same credential can run it. Rules: (a) duplicate rows in a slot are NOT gaps, and the newest-per-slot rule is for reading results (spec "Reading rules": newest `psse_run` for that `slot_time` with outcome in `ok`, `fallback`, ordered by `started_at desc, run_id desc`), not for gap detection; (b) a failed run is a record, so its hour is not `no_run`, but with no complete run it is listed as `failed_only` so "no results this hour" is never hidden (SCH-02 itself asks only for `no_run`); (c) the current hour is excluded because its run may still be pending; (d) hours before the first run are not gaps; (e) an empty table gives zero rows, so the Python wrapper reports "no runs recorded" separately. `gaps.py` runs this file, accepts `--since/--until` (filtering in Python, so there is no second query to drift), prints UTC times, and with `--fail-on-gaps` returns exit 5. Differential test: a pure-Python reference over random slot sets must equal the SQL result on local Postgres.

### Credential proof, role leg (safe by construction)
```python
# credcheck.py (sketch). Nothing here survives: catalog reads, where-false statements, one rolled-back transaction.
checks = [
  ("writer_insert_select_on_results", "select bool_and(has_table_privilege(current_user, 'public.'||t, 'INSERT') "
        "and has_table_privilege(current_user, 'public.'||t, 'SELECT')) from unnest(%s::text[]) t"),
  ("writer_no_update_delete_truncate", "select not bool_or(has_table_privilege(current_user,'public.'||t,p)) "
        "from unnest(%s::text[]) t, unnest(array['UPDATE','DELETE','TRUNCATE']) p"),
  ("writer_nothing_on_ratings", "select not bool_or(has_table_privilege(current_user,'public.'||t,p)) "
        "from unnest(array['city_rating','pipeline_run','latest_rating']) t, unnest(array['SELECT','INSERT','UPDATE','DELETE']) p"),
  ("role_not_privileged", "select not (rolsuper or rolcreaterole or rolcreatedb or rolbypassrls) from pg_roles where rolname = current_user"),
]
# Active attempt, expects SQLSTATE 42501 (insufficient_privilege); 'where false' changes no row even if it were allowed
for stmt in ("update public.city_rating set rating_amps = rating_amps where false",
             "delete from public.city_rating where false"):
    with conn.transaction(force_rollback=True):   # rolled back whatever happens
        try: conn.execute(stmt); verdict = "FAIL: statement was allowed"
        except psycopg.errors.InsufficientPrivilege: verdict = "PASS"
# Write proof: build a synthetic complete run, insert run row + 4 + 4 dispatch/margin rows inside
# conn.transaction(force_rollback=True), count them inside the block, let it roll back.
```
`conn.transaction(savepoint_name=None, force_rollback=False)`: "Roll back the transaction at the end of the block even if there were no error" [CITED: psycopg.org/psycopg3/docs/api/connections.html]. That a `where false` UPDATE raises 42501 for a role without the privilege (privileges are checked at executor start, not per row) is [ASSUMED]; the Mac test proves it against Postgres 18.6. The existing test already proves the role leg on the Mac: [VERIFIED: psse_schema_pg_test.py:186-194] it runs `"select * from public.city_rating"`, `"select * from public.pipeline_run"`, `"select * from public.latest_rating"`, `"insert into public.city_rating (city) values ('AUSTIN')"` and `"update public.city_rating set rating_amps = 1"` as the writer and expects `InsufficientPrivilege` for each. The new work is the same proof as a shipped function that runs against the live credential.

REST leg: `fetch_latest_rating(env)` returns four city rows (reads ratings, exactly the job's code path) and a `PATCH {SUPABASE_URL}/rest/v1/city_rating?city=eq.__no_such_city__` with `{"rating_amps": 1}` and the publishable key must answer 401 or 403.

### Hourly job flow in the launcher (skeleton)
```python
def main(argv, psspy_loader, env=None):
    args, cfg = parse(argv, env)                       # exit 2 on any problem; never echo secrets
    with RunLock(cfg.lock_path) as lock:
        if not lock.acquired: return 4
        preflight(cfg)                                 # socket.create_connection; failure -> log, return 3
        try:
            psspy = psspy_loader(cfg)
            prepared = study.prepare_run(psspy, cfg.case_path, cfg.mapping_path, cfg.allow_placeholder)
            study_fn, case_id, h1, h2 = prepared.study, prepared.case_id, prepared.case_sha256, prepared.mapping_sha256
        except PsseUnavailable as exc:
            study_fn = study.failing_study("load_case", "PSS/E could not be started: %s" % exc)
            case_id, h1, h2 = run_record.case_label(cfg.case_path), run_record.file_sha256(cfg.case_path), None
        if args.dry_run: return dry_run(study_fn, cfg)
        out = job.run_once(lambda: ratings.fetch_latest_rating(cfg.env), study_fn,
                           lambda: writer.connect(env=cfg.env), case_id, h1, h2, env=cfg.env)
        return out.exit_code
```

## Runbook (TST-02): what each step should show

| # | Step (laptop, by a human) | Needs | Should show |
|---|---------------------------|-------|-------------|
| 0 | Fill the ask-the-teammate list (Open Questions) | teammate | PSS/E version and edition, Python path and bitness, licence type |
| 1 | Install repo (clone or ZIP), wheelhouse into `--target`, write `job.env` (ACL) | Python matches `PSSPY3x` | `python -c "import psycopg; print(psycopg.__version__)"` prints the pinned version |
| 2 | `--selftest`: import `psspy`, `psseinit`, print `psseversion` | licence | version printed, no dialog; else the exact failure class for the guide |
| 3 | Probe read-only on a COPY of `savnw.sav` (`probe.run_probe(psspy, case, None, False)`, `show_identifiers=False`) | EXAMPLE folder case | every `signature:` row PASS or SKIP; `branch_table`, `bus_table`, `column_alignment`, `circuit_id_padding`, `option_strings`, `load_flow` PASS. A FAIL on `signature:branch_chng_3` or `scal_2` is the expected-risk row (UNVERIFIED in `SURFACE`): fix `SURFACE` and `psse_api.py` against the real signature before going on |
| 4 | Probe with `write_check=True` on the copy | step 3 green | `rating_write` PASS (RATEA moved one MVA, read back, restored by reload); `scale_load` PASS |
| 5 | Throwaway mapping in `psse_local/` (marked `"placeholder": true`, four lines with equal-kV ends, picked from the probe's branch table), `--dry-run --allow-placeholder` | step 4 | study completes, row counts, `validate_results` OK, wall-clock time under 1500 s |
| 6 | Register the task with `--dry-run`; let three hours pass; `Get-ScheduledTaskInfo` | SCH-01 | three starts at :15, `LastTaskResult` 0, no overlap, local log lines. Start one run by hand mid-run: exit 4 |
| 7 | Real case: probe with the mapping (no `write_check`), then `--dry-run` with the real mapping | case + mapping | `mapping` row "0 problems" with the real kV per city; Power Systems engineer reviews numbers; hand-check one branch's written rating and one `MAXPCTRATEA` value against the formula in `psse_study_definitions.md` |
| 8 | Phase 6 live: credential proof (role leg, REST leg) | Phase 6 applied, owner sets role password | every row PASS |
| 9 | One real write run, then read back | step 8 | exit 0; `psse_results_v1_checks.sql` all `ok`; newest result set per the reading rules (below) |
| 10 | Switch the task to the real run, leave it on; next day run the gap check | all | `no_run` rows only for hours the laptop was off, each explained (or one induced gap: disable the task for two hours) |

Read-back (reading rules from the spec, one statement, no write):
```sql
select distinct on (slot_time) slot_time, run_id, outcome, started_at, finished_at, n_contingencies, n_contingencies_with_results
from public.psse_run where outcome in ('ok','fallback')
order by slot_time desc, started_at desc, run_id desc limit 3;
-- then, for the newest run_id: select city, applied_mva, voltage_limit_mva, dispatched_mva, limiting_factor from public.psse_dispatched_capacity where run_id = :id;
```
`distinct on (slot_time)` after `order by slot_time desc, started_at desc, run_id desc` keeps the newest per slot [ASSUMED: SQL semantics, test it].

**Open questions in `psse_study_definitions.md`:** do not block the run on them. Run with the documented defaults, put each answer into the private mapping's `study` section (which changes `mapping_sha256`, so every result records which settings produced it), and keep the result labelled "not a full N-1 study" until Power Systems agrees the scope. Map: Q1 mapping and Q4 sink buses to step 7; Q2 rate set, Q3 static overwrite, Q5 base-case violations, Q8 limits to the engineer review after step 7; Q6 licensed modules to step 0; Q7 case size and run time to step 5 and step 7 timings. Answer 3 matters operationally: the first scheduled real run overwrites the case's own ratings on the mapped lines in memory only (the case file is never saved), so no customer file changes.

## Smoke case choices (PSS/E example cases)

- **`savnw.sav`** is the sample case in the installation's `EXAMPLE` folder, with `savnw.dyr` for dynamics; the PSS/E 34 path is quoted as `C:\Program Files (x86)\PTI\PSSE34\EXAMPLE` [CITED: psspy.org forum answers 5569 and others, MEDIUM]. For 35.x look for `EXAMPLE` beside `PSSPY39` under the install (layout `C:\Program Files\PTI\PSSE35\35.3\...` appears in a forum answer) [ASSUMED]. A bus count of 23 and the existence of in-service same-kV lines are [ASSUMED]; the probe's `branch_table` and `bus_table` rows give the real numbers. No source confirms an IEEE 14, 30 or 39 case in `EXAMPLE`; a forum reply names "sample.sav" with 2 VSC lines.
- **IEEE 39-bus** is not shipped with PSS/E per any source found. Public copies exist (Texas A&M repository page "New England IEEE 39-bus system", described as synthetic data, free for commercial or non-commercial use, with a form and a citation request [CITED: electricgrids.engr.tamu.edu]; UIUC ICSEG "IEEE 39-Bus System" page, 10 generators, 46 lines [CITED: search summary]; MATPOWER `case39`). Whether a PSS/E `.raw` is offered and its version are UNVERIFIED. A `.raw` is read once in PSS/E and saved as `.sav` outside the job (GUI is enough); a forum answer says raw files of older versions open in newer PSS/E [CITED: psspy.org question 4364, LOW]. The 39-bus system is a 345 kV network [ASSUMED], which matches the job's 345 kV worked table.
- **Free or university edition:** the System Design Report budgets PSS/E at "$0 (free-access tier)" [VERIFIED: docs/System Design Report.md, `| PSS/E Software | Power systems simulation tool | $0 (free-access tier) |`]. A forum user reports a 50-bus limit for the PSS/E 33 free version [CITED: psspy.org search summary, LOW]; if the teammate's edition is limited, `savnw.sav` and the 39-bus case probably fit but a large real case may not. Ask.
- A smoke run on any of these is a `--dry-run` with a throwaway mapping marked `placeholder`, kept in `psse_local/` (git-ignored with `*.sav`, `*.raw`; [VERIFIED: .gitignore lines `/psse_local/`, `*.sav`, `*.raw`]). It proves the real `psspy` path (signatures, bulk reads, rating write, `scal_2`, `fnsl`, N-1 loop, the `validate_results` shape) and the run time on a small case; it does not prove the real case's numbers.

## Setup guide contents (DOC-01)

1. Purpose, scope, what the job writes where, and the "only while the laptop is on" position.
2. Prerequisites with how to read each: PSS/E version and edition (`psseversion`), licence type, Python path and bitness (`python -c "import sys,struct;print(sys.version,struct.calcsize('P')*8)"`), the `PSSPY3x` folder, admin status, Windows version, `powercfg /a`, `w32tm /query /status`, outbound access to the pooler (`Test-NetConnection <host> -Port 5432`).
3. Interpreter and psycopg decision table (the matrix above); wheelhouse commands.
4. Install: repo copy location, `psse_local/` for case and mapping, `job.env` keys and ACL, nothing secret in the repo.
5. First checks in order: selftest, probe, dry-run (the runbook).
6. Task Scheduler: fill the XML, register, test run, what the settings mean, how to change the minute or disable.
7. Reading results and the gap check (both statements, how to run each, the `gap_kind` meaning, the timing and clock notes).
8. Exit codes table and "where to look" (Task Scheduler `LastTaskResult`, local log folder, the run record's `failed_stage` and `error`).
9. Troubleshooting table: licence dialog or demo banner; "Bad magic number" (interpreter mismatch); "DLL load failed" (`os.add_dll_directory`, bitness); task runs and exits at once (antivirus, quoting, UTF-16 XML); exit 3 (network or credential); exit 4 (previous run still going); exit 2 (config); repeated `stale` fallback (start after HH:30); gap after sleep.
10. Credential hygiene: what the job never logs (connection string, password, pooler user and project ref, host, publishable key, JWT-shaped tokens, resolved IP in parentheses: all handled by `redaction.redact`), never paste a failing log with `show_identifiers=True` into the repo, rotate by asking the owner to reset the role password.
11. Uninstall: `Unregister-ScheduledTask`, delete `%LOCALAPPDATA%\dlr-psse`, remove the repo copy, ask the owner to reset the role password.
12. Hand-over record: PSS/E and Python versions found, psycopg pin used, dates of the runbook steps, with no identifiers.

## Buildable-now vs blocked split

| Deliverable | Req | Buildable now (Mac, fake `psspy`, local Postgres) | Needs the laptop | Needs real case or Phase 6 |
|-------------|-----|---------------------------------------------------|------------------|----------------------------|
| `launcher.py`, exit codes, config file, dry-run, preflight, `RunLock` | SCH-01, TST-02 | Yes, with `FakePsspy` and `run_once` into local Postgres | `msvcrt` branch and `psspy` loader run for real | no |
| Entry script `psse_run_hourly.py` (psspy bootstrap) | TST-02 | Skeleton and a loader test with a stub module | Real import, `psseinit`, output silencing | no |
| Gap SQL + `gaps.py` + differential test | SCH-02 | Yes (local Postgres, DDL applied) | no | Live read after Phase 6 (the same SQL) |
| `credcheck.py` role and REST legs | DBX-02 | Yes (local Postgres roles, loopback REST fake) | no | Live run needs Phase 6 migration applied, owner-set role password, live REST key |
| Task XML template + render and structure test | SCH-01 | Yes (parse, assert `IgnoreNew`, limit < 60 min, no secret-looking text, placeholders only) | Registration and observed hourly starts | no (a `--dry-run` task proves scheduling before Phase 6) |
| Setup guide, runbook | DOC-01, TST-02 | Yes, drafted; doc-drift test ties settings and exit codes to code | Verified by someone following it | Final numbers after steps 7-10 |
| Real `psspy` probe and dry-run | TST-02 | no | Yes | Real case for step 7 |
| One real end-to-end write | TST-02 | no | Yes | Phase 6 live, real case and mapping |
| Credential live proof | DBX-02 | no | Run on the laptop (or by the owner) | Phase 6 live |

**Recommended plan structure:** Wave 1 (parallel, no overlap in files): `03-01` launcher + lock + entry + exit codes + dry-run; `03-02` gap check; `03-03` credential check. Wave 2 (parallel): `03-04` task XML + test; `03-05` setup guide + runbook + doc-drift test. Wave 3, human checkpoints only (each is a short checklist with the exact command and the expected output, using `checkpoint:human-action` or `checkpoint:human-verify`): `03-06` laptop session A: ask-the-teammate list, install, selftest, probe, dry-run on `savnw.sav`, three hourly dry-runs (closes SCH-01); `03-07` after Phase 6 and the real case: probe, dry-run, credential proof (closes DBX-02), the one real write and read-back (closes TST-02), enable the real task, next-day gap check (closes SCH-02 live), final guide edit (closes DOC-01). Keep REQUIREMENTS statuses `Pending` until the matching human step passes. Add the allow-list lines (`msvcrt`, `fcntl`, `argparse`) in plan 03-01 with comments in the house style. The phase can show "5 of 7 plans complete, 2 waiting on inputs" and then the remainder is a checklist.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| PSS/E 33: Python 2.7, 32-bit | PSS/E 35: 64-bit, Python 3.x, `import psse35` helper | 34.7 added full 3.7 support; 35.0 "standardized on using Python 3.7 by default" (release notes copy); 35.3+ reported to ship a 3.9 interpreter | Pick the psycopg pin by the actual interpreter; never assume |
| psycopg 3.0/3.1 | 3.3.x requires 3.10+ | 3.3.0 dropped 3.8 and 3.9 | 3.9 interpreters stay on 3.2.13 |
| Siemens 35.x current | 35.6.4 is end of life; 36.x current; 36.1 reported to bundle Python 3.11 | Siemens deck to WECC, January 2026 [CITED: wecc.org PSSE Update January 2026, via search summary]; forum "Python 3.11 comes with PSSE" [CITED: psspy.org question 11182] | The laptop may be on 35.x or 36.x; ask |

**Deprecated/outdated:** `setx` for secrets (readable by the user's processes), `schtasks /sc hourly` for this job (cannot set battery, wake, overlap or time limit), PSS/E 34.x for this job (32-bit, no psycopg wheel).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | PSS/E 35.3+ ships a Python 3.9 interpreter and `PSSPY39`; 34.x is 32-bit; 36.1 bundles Python 3.11 (single forum answers) | Stack, State of the Art | Wrong psycopg pin or an unsupported laptop; mitigated by the ask-first list and the selftest |
| A2 | `psseinit(N)` takes the maximum bus count; 20000 is a safe default | Pattern 5 | Memory or a too-small case limit; `PSSE_MAX_BUSES` is configurable |
| A3 | `report_output`, `progress_output`, `alert_output`, `prompt_output` accept `(2, file, [0, 0])` | Pattern 5 | Banner on the console or a hang; guarded with `getattr`, selftest shows it |
| A4 | `os.add_dll_directory(PSSBIN)` cures "DLL load failed" on Python 3.8+ | Pattern 5, Pitfalls | Import still fails; selftest isolates it |
| A5 | `savnw.sav` has 23 buses and usable same-kV lines; EXAMPLE folder path under 35.x | Smoke case | Probe shows the truth; pick another case |
| A6 | IEEE 39-bus is 345 kV; a PSS/E `.raw` is obtainable | Smoke case | Smoke on `savnw.sav` only |
| A7 | A `Repetition` with `Interval` and no `Duration` repeats indefinitely | XML | Task stops after a day; verify `NextRunTime` |
| A8 | A standard user can register an interactive-only task for themselves | Pitfall 3 | Teammate registers it; documented fallback |
| A9 | `WakeToRun` is unreliable on Modern Standby | Pitfall 4 | Gaps overnight are expected anyway |
| A10 | Licence type is local or dongle and works without VPN | Pitfall 1 | Runs fail off-campus; ask |
| A11 | PSS/E 35.x does not need `HKLM\SOFTWARE\PTI\License` write on import | Pitfall 3 | Import fails for a non-administrator; teammate's own session may differ |
| A12 | `psse_job` runs on Python 3.7/3.8/3.9 with psycopg 3.1.20/3.2.13 | Stack | Code never ran there; the selftest and the fake-study run on the laptop are the proof |
| A13 | A `where false` UPDATE or DELETE as an unprivileged role raises 42501 | Credential proof | Replace with the plain statement from the existing test inside `force_rollback` |
| A14 | A publishable key reaches PostgREST as `anon`, so a refused write is 401 | Pitfall 13 | 403 also accepted; any 2xx fails |
| A15 | The gap SQL is correct as written | Code Examples | Untested; the differential test is the gate |
| A16 | `distinct on` read-back statement returns the newest per slot | Runbook | Untested; test locally |
| A17 | A hard kill at the time limit may leave the licence seat held until the server times out | Pitfall 2 | Longer outage after a hang; only matters for network licences |
| A18 | DST changes cause at most one doubled or missed slot | Pitfall 6 | Cosmetic gap rows around the changeover |

## Open Questions

1. **Which PSS/E version, edition, licence type and Python does the laptop have?**
   - Known: teammate says "should be compatible"; 35.x reportedly 3.9, 36.x reportedly 3.11.
   - Unclear: everything on the laptop, including whether Task Scheduler registration works for them without administrator rights and whether wake works.
   - Recommendation: the ask-the-teammate list in the setup guide is plan 03-06's first step; nothing else depends on the answer except the psycopg pin and the XML Python path.
2. **Is the real case the IEEE 39-bus system, and does it come with a mapping?**
   - Known: only the Prior Art Report wording. Unclear: when the team meets and what arrives.
   - Recommendation: do not wait; smoke on `savnw.sav` in dry-run; treat the real case as Wave 3 item `03-07`.
3. **Does Phase 6 take the migration, and when?**
   - Known: [VERIFIED: `ls supabase`] only `supabase/migrations/` with the two Phase 4 migrations exists and there is no `supabase/ops`; the hand-off note asks Phase 6 for the DDL, the role and a `verify_psse_results.sql`.
   - Recommendation: everything DB-side is proven on local Postgres now; the live legs are one short checklist.
4. **Should a smoke run ever write to the live tables?** Rows are permanent. Recommendation: no; if the owner wants a live DB proof before the real case, accept one row set with a clear `case_id` label and let the owner delete it as the database owner.
5. **Is a PSS/E licence available to a non-interactive or signed-out session?** Recommendation: assume not; `InteractiveToken` only.
6. **Does the pooler accept the custom role?** The username form for a custom role through the shared pooler is `[ROLE].[PROJECT-REF]` [CITED: supabase.com/docs/guides/database/connecting-to-postgres]; whether the role needs a Supabase-side setting beyond the migration is UNVERIFIED until Phase 6 applies.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PSS/E | real run, probe, selftest | no (this machine) | unknown (laptop) | none; all PSS/E-side steps are human checklist items |
| Python on this machine | tests | yes | 3.12.7 system, `.venv` Python 3.12 with pytest 9.0.3 and psycopg 3.3.6 | none needed |
| Local Postgres (portable) | Mac-side DB proofs | present per Phase 2 verification (13 passed with `PSSE_REQUIRE_PG=1 DLR_TEST_PG_AUTOSTART=1`); not located or re-run this session | 18.6 | tests skip without `PSSE_REQUIRE_PG=1` |
| `schtasks` | registration docs | yes (`C:\Windows\System32\schtasks.exe`) | n/a | not used by the research; no task was registered |
| Supabase live database, Phase 6 migration | live proofs, real run | no (migrations folder holds Phase 4 only) | n/a | local Postgres for Mac proofs |
| Laptop rights, wake support, licence type | SCH-01, TST-02 | unknown | n/a | fallback paths named in Pitfalls 3 and 4 |

**Missing with no fallback:** PSS/E and the laptop (blocks only Wave 3). **Missing with fallback:** Phase 6 (local Postgres proves the DB legs; live legs wait).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 (`pytest.ini`: `pythonpath = backend`, `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py`) |
| Config file | `pytest.ini` |
| Quick run command | `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider backend/tests/psse_launcher_test.py backend/tests/psse_lock_test.py backend/tests/psse_task_xml_test.py backend/tests/psse_contract_test.py` |
| Full suite command | `PSSE_REQUIRE_PG=1 DLR_TEST_PG_AUTOSTART=1 .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider backend/tests/psse_*_test.py backend/tests/secret_scan_test.py` (Postgres on PATH, as in the Phase 2 verification) |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCH-01 | Second instance exits 4 and writes nothing; exit codes 0/1/2/3/4; lock released on exit | unit | `pytest backend/tests/psse_lock_test.py backend/tests/psse_launcher_test.py -x` | Wave 0 |
| SCH-01 | Task XML: `IgnoreNew`, `ExecutionTimeLimit` under 60 minutes, battery flags false, `InteractiveToken`, `Repetition` `PT1H`, placeholders only, no secret-looking text | unit | `pytest backend/tests/psse_task_xml_test.py -x` | Wave 0 |
| SCH-02 | Gap SQL equals a pure-Python reference over random slot sets, `no_run` and `failed_only`, duplicates not gaps, empty table, current hour excluded | integration (local PG) | `pytest backend/tests/psse_gaps_pg_test.py -x` | Wave 0 |
| DBX-02 | Role leg: every check PASS as `dlr_psse_writer`, FAIL as a superuser; no row survives; REST leg 401/403 PASS, 2xx FAIL (loopback fake) | integration (local PG) | `pytest backend/tests/psse_credcheck_test.py -x` | Wave 0 |
| TST-02 (Mac part) | Launcher + `FakePsspy` + `run_once` into local PG: ok, fallback, failed (`PsseUnavailable`), dry-run writes nothing | integration | `pytest backend/tests/psse_launcher_test.py -x` | Wave 0 |
| DOC-01 | Guide exit-code table, XML settings, psycopg matrix and env key names equal the code | unit | `pytest backend/tests/psse_setup_doc_test.py -x` | Wave 0 |
| TST-02, SCH-01 (live), DBX-02 (live) | Real run, hourly observation, live proof | manual-only | the runbook steps 2-10 | n/a (laptop and Phase 6) |

### Sampling Rate
- **Per task commit:** the quick run command (under about 30 seconds, no Postgres).
- **Per wave merge:** the full suite command.
- **Phase gate:** full suite green (521 existing plus new) before `/gsd-verify-work`; human items listed as `human_needed`, as in Phases 1 and 2.

### Wave 0 Gaps
- [ ] `backend/tests/psse_launcher_test.py`, `psse_lock_test.py`, `psse_gaps_pg_test.py`, `psse_credcheck_test.py`, `psse_task_xml_test.py`, `psse_setup_doc_test.py`
- [ ] Allow-list edit in `backend/tests/psse_contract_test.py` (`msvcrt`, `fcntl`, `argparse`) with comments
- [ ] Fake `psspy`: the four output-control functions, `psseinit`
- [ ] Framework install: none (pytest and psycopg present)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Scoped role `dlr_psse_writer` and publishable key only; the launcher refuses a secret key or `service_role` JWT (already in `fetch_latest_rating`) |
| V3 Session Management | no | No sessions |
| V4 Access Control | yes | Role privileges proven by `credcheck`; no consumer role on result tables |
| V5 Input Validation | yes | Config file parsed strictly (known keys, size cap, `json`-style no code execution); mapping already validated by `mapping.py` |
| V6 Cryptography | yes | TLS via libpq: `sslmode=require` at minimum, `verify-full` with the Supabase root certificate when practical; no hand-rolled crypto |
| V7 Error Handling and Logging | yes | `redaction.redact` on every logged and stored message; local log files carry no connection string |
| V14 Configuration | yes | Credential file outside the repo, user-only ACL; task XML and arguments carry no secret |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Connection string in task arguments, XML, logs or process list | Information disclosure | Config file with ACL; redaction; arguments carry only a path |
| Plaintext `sslmode=prefer` fallback | Tampering, Disclosure | `sslmode=require` (Supabase: most drivers default to `prefer`, which "falls back to sending your data in plaintext if the encrypted attempt fails") [CITED: supabase.com docs]; `require` does not verify the server |
| Over-privileged key on the laptop | Elevation of privilege | `service_role` and secret keys stay off the laptop; `credcheck` proves scope |
| Case or mapping committed to the public repo | Information disclosure | `/psse_local/`, `*.sav`, `*.raw` ignored; the existing secret-scan test; probe output hides identifiers by default |
| Planted script or module in a user-writable working directory | Tampering | `WorkingDirectory` is a folder only the user can write; not Downloads |
| Wheel from a mirror altered | Tampering | Pin versions; record wheel sha256 from PyPI JSON in the guide |
| Smoke data poisoning the live tables | Tampering | Dry-run default for smoke; append-only table has no delete for the writer |

## Sources

### Primary (HIGH confidence)
- Repo files read this session: `backend/psse_job/job.py`, `study.py`, `probe.py`, `writer.py`, `contract.py`, `redaction.py`, `constants.py`, `settings.py`, `ratings.py`, `mapping.py`, `run_record.py`, `backend/tests/psse_contract_test.py`, `psse_schema_pg_test.py`, `psse_local_pg.py`, `docs/data-science/schema/psse_results_v1.md`, `.sql`, `_checks.sql`, `psse_mapping_example.json`, `docs/data-science/decisions/psse_study_definitions.md`, `psse_results_phase6_handoff.md`, Phase 1 and 2 `VERIFICATION.md`, ROADMAP.md, REQUIREMENTS.md, `.gitignore`.
- PyPI JSON for `psycopg` and `psycopg-binary` 3.1.20, 3.2.13, 3.3.6 and `backports.zoneinfo` (fetched and parsed this session).

### Secondary (MEDIUM confidence)
- Microsoft Learn: settingsType complex type, MultipleInstancesPolicy, ExecutionTimeLimit, Repetition, LogonType, `schtasks create`, `Register-ScheduledTask` (all read this session).
- psycopg docs: install page, news page, connections API (`transaction(force_rollback=...)`, `prepare_threshold` "new in Psycopg 3.1").
- Supabase docs: connecting to Postgres (pooler ports, IPv4/IPv6, custom-role username form, `sslmode`), SSL enforcement; PostgREST error-code mapping (42501 to 401/403).
- Python docs: `msvcrt.locking` (3.9).

### Tertiary (LOW confidence, community or vendor, marked for validation)
- psspy.org forum answers: question 9121 (import pattern on 35.3.3/Python 3.9), 8235 (DLL load failed, 64-bit), 11182 (36.1 Python 3.11), 507 (licence not released by thread end), 347 and 726 (registry write access, v32/33), 4364 (raw version conversion), 5569 (EXAMPLE folder, `savnw`). Several fetched pages returned 403 and were read through search summaries.
- keentelengineering.com guides (version table, output functions), whit.com.au blog (`psseinit` buses), Siemens/WECC decks (release lifecycle, via search summary; PDF text not extractable here), Texas A&M and UIUC pages for the 39-bus case, Microsoft Q&A and HP community threads on wake from Modern Standby, TechNet 'Task Security Context' summary.

## Metadata

**Confidence breakdown:**
- Standard stack and psycopg matrix: HIGH for the PyPI-verified rows, LOW for which Python PSS/E bundles.
- Architecture (launcher, lock, gap, proof): HIGH on fit with the built contracts, MEDIUM on Windows behaviour (nothing was run on Windows Task Scheduler or with `msvcrt` here).
- Pitfalls: MEDIUM (Task Scheduler, Microsoft docs) to LOW (PSS/E licence, registry, example cases).

**Research date:** 2026-10-28
**Valid until:** 2026-11-04 for the PSS/E-side items (the laptop answers will replace them); 30 days for Task Scheduler, psycopg and Supabase facts
