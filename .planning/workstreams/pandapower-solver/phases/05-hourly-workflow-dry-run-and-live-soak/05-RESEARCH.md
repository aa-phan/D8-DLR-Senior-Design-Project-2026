# Phase 5: Hourly Workflow, Dry Run and Live Soak - Research

**Researched:** 2026-11-25
**Domain:** GitHub Actions hourly job (dispatch by cron-job.org) running the pandapower study through the existing `psse_job` run loop and writer; dry-run/live gate; public-log leak control; 24-slot soak check.
**Confidence:** HIGH for what the existing code does and what must be wired (all read this session); MEDIUM for GitHub and Supabase platform behaviour (official docs, not exercised from this repo yet); several owner-side facts are `[ASSUMED]` and listed in the Assumptions Log.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

Gathered 2026-11-25. The user did not have a view on the four open choices and asked for recommendations; each recommendation below was approved as written ("go with those"). The owner can change any of them.

#### Retention (OPS-04)
- **D-01:** Keep every result row; no pruning in this phase. The hourly job adds about 24 run row sets a day (one run row plus its dispatch and margin rows), a few hundred rows a day, small for the Supabase project. The writer role `dlr_psse_writer` has no DELETE, so pruning would need the owner's admin login anyway. The written decision (a short document in the phase directory, before the first live write) states this and names a review trigger: revisit if the result tables pass 100,000 rows or the project nears its size limit. — **Reversibility:** easy — a later decision can add pruning or archiving; keeping rows loses nothing.

#### Dry run to live switch (OPS-03)
- **D-02:** The workflow runs as a dry run (no writes) unless a GitHub repository variable, working name `PANDAPOWER_LIVE`, is set to `true`. The owner (Aaron owns the repo secrets and variables, the user believes) sets it only after NET-03 and AGR-02 have passed; a dated line in the repo records who decided and when (the recorded owner decision in roadmap success criterion 3). Default when the variable is absent or anything but `true` is dry run.
- **D-03:** Independently of the variable, the job refuses a live write when `engine.is_placeholder(backend)` is true, so a mistaken flip cannot store figures from the placeholder mapping. A dry run records that it wrote nothing; a test asserts the four result tables are unchanged after one. — **Reversibility:** easy — the variable can be turned off at any time; rows written while live stay (see D-01).

#### The 24 hour soak (OPS-05)
- **D-04:** Pass means 24 consecutive hourly slots, each with a pandapower result, as shown by the per-solver gap check. Any missed hour restarts the clock. The workflow calls `gaps.run_by_solver(...)` with `expected=(engine.SOLVER,)` so an absent pandapower solver is reported, and passes `solver=engine.SOLVER` to `job.run_once` (a run started with the default tag is stored as a failed `psse` run with no figures; see `03-VERIFICATION.md` F-2, F-5). The strict rule matches the roadmap's word "consecutive" and is the simplest to state in the report.

#### Public log leak guard (OPS-02)
- **D-05:** Two layers. The job prints only counts and statuses, never a secret, bus number or study value (GitHub's own secret masking is an extra layer, not the plan). A test runs the job with planted fake identifiers and scans the captured log for them, the same pattern as the Phase 4 replay leak test (`04-04`). The private mapping is written only to the runner's temporary folder.

#### Workflow shape (fixed by the roadmap and the existing pattern; not re-discussed)
- **D-06:** Follow `.github/workflows/dlr_live.yml`: `workflow_dispatch` poked by cron-job.org (no GitHub scheduler), at :20 UTC, `production` environment, main-only `if`, its own concurrency group, timeout under 30 minutes (the roadmap says under one hour; the existing workflow uses 30). The private network comes from a GitHub secret (earlier decision D-06 of the pandapower workstream: 25,191 bytes against the 48 KB limit). The writer connection and ratings read settings are GitHub secrets.

### Claude's Discretion

Workflow file name, the exact variable and group names, log wording (counts only), test layout, and how the retention document is titled, as long as the decisions above hold.

### Deferred Ideas (OUT OF SCOPE)

- OPS-06, an external freshness alarm if pandapower results stop arriving (v2).
- Pruning or archiving old result rows (revisit under D-01's trigger).
- Per-solver dashboard view: Phase 6.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| OPS-01 | Hourly workflow at :20 UTC, cron-job.org trigger, main only, own concurrency group, timeout under one hour | Section "Workflow shape" and Pattern 1 (copy of `dlr_live.yml`); cron-job.org settings from the dlr_live runbook; merge-to-main prerequisite (Pitfall 1); workflow text test pattern |
| OPS-02 | Writer connection, ratings read settings and private mapping from secrets; mapping only in the runner temp folder; never print a secret, bus number or study value | Secret inventory (five private inputs, not three), base64 transport, temp materialisation (Pattern 3), output discipline (Pattern 4), planted-identifier test (Pattern 7), real-log scan (Pattern 8) |
| OPS-03 | Dry run first; live only after NET-03 and AGR-02 pass | `PANDAPOWER_LIVE` gate (Pattern 2), dry-run path that has no connect parameter (Pattern 5), placeholder refusal, tables-unchanged DB test, recorded owner decision document |
| OPS-04 | Written retention decision before live writes | Row-volume finding (Pitfall 4: about 5,000 rows a day, not a few hundred), decision document content, review trigger arithmetic |
| OPS-05 | 24 consecutive hourly slots with a pandapower result, shown by the per-solver gap check | `gaps.run_by_solver` wiring with `expected=`, trailing-slot soak function (Pattern 6), why the pass shows on the 25th run, owner's closing record |
</phase_requirements>

## Summary

Almost everything the hourly job needs already exists and only has to be wired: `engine.prepare_run` builds the study, `job.run_once(..., solver=engine.SOLVER)` runs, validates and writes it through the all-or-nothing writer as `dlr_psse_writer`, and `gaps.run_by_solver(..., expected=(engine.SOLVER,))` is the per-solver check. What does not exist is (a) any runner or workflow, (b) a dry-run path for the pandapower engine (the only dry run in the repo is `launcher._dry_run_mode`, which is bound to PSS/E), (c) a way for the private recorded solver settings to reach the runner, (d) any output control, and (e) a "24 consecutive slots" function. The phase is mostly a small runner module, a workflow file copied from `dlr_live.yml`, three kinds of tests (text test of the workflow, planted-identifier leak test, database tier for dry-run-unchanged), two decision documents, and a sequence of owner-only checkpoints.

Six findings change the plan and are not in CONTEXT.md. **(1)** `origin/main` (as last fetched) has `psse_job` and `dlr_live.yml` but none of `pandapower_job`, the solver-tag migration file, `requirements-pandapower.txt` or `gaps.run_by_solver`; the branch is 132 commits ahead. A `workflow_dispatch` workflow only receives events when its file is on the default branch, and the job is main-only, so nothing can run, not even a dry run, until the branch is merged. **(2)** The engine needs the recorded PSE-02 settings (`engine.load_recorded_backend` reads two marker-keyed files from a check folder). The check folder's `report.json` also holds NET-03 verdicts and parity detail, which D-08 of Phase 1 forbids in CI, so a trimmed third private input is needed (D-06 names only network, mapping, writer and ratings settings). **(3)** `job.run_once` logs the stored error text with `log.warning`; with no logging configured Python prints it to stderr, and a mapping validation message can carry a `from-to-ckt` bus key. The runner must sink logging and the raw streams and print only through a closed vocabulary. **(4)** D-01's premise "a few hundred rows a day" is true for run, dispatch and margin rows only; contingency violation rows dominate (about 205 per run in the 19 recorded runs), so the realistic volume is about 5,000 rows a day and the 100,000-row review trigger is reached in about 20 days of live running. **(5)** The per-solver gap check starts at the solver's first slot and never walks the current hour, so a "24 consecutive slots" pass needs a small trailing-count function and first shows on the run 24 hours after the first live run. **(6)** The repo's real settings: `gh` shows no pandapower secrets and no `PANDAPOWER_LIVE` variable yet, the `production` environment exists with a main-only branch policy and holds `SUPABASE_DB_URL`, and the current user has push but not admin rights, so every secret, variable and cron-job.org step is an owner checkpoint.

**Primary recommendation:** Add one runner module `backend/pandapower_job/hourly.py` (entry script `backend/pandapower_hourly.py`, same shape as `backend/pandapower_replay.py`) with a closed output vocabulary and a dry path that has no database connect parameter; add `.github/workflows/pandapower_hourly.yml` as a copy of `dlr_live.yml` with the live switch read only from `vars.PANDAPOWER_LIVE`; carry the four private files as base64 secrets in the `production` environment; prove OPS-02/03/05 with a text test, a planted-identifier test and a Postgres-tier test; and treat merge-to-main, secrets, cron job, dry-run observation, the live flip and the soak as ordered owner checkpoints.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Hourly trigger (:20 UTC) | cron-job.org (external scheduler) | GitHub `workflow_dispatch` API | GitHub's own scheduler ran hours late (documented in `dlr_live.yml` header); the existing pattern uses an external poke |
| Study compute (network build, 4 cities, N-1, margin, dispatch) | GitHub-hosted runner (Python 3.12) | none | Runs the engine unchanged; about 12 to 36 s on the fixture (02-04, 02-05 summaries) |
| Dry-run vs live decision | GitHub repo variable (`vars`) read into one env var | Python runner (second, independent refusal on placeholder) | `secrets` cannot be used in a job `if`; the variable is the owner's switch, the placeholder refusal is a code-level backstop (D-02, D-03) |
| Private inputs at rest | GitHub secrets (environment `production`) | owner's machine under `data/private/` (git-ignored) | Network, mapping, recorded settings, writer URL and ratings key must never be in the public repo |
| Private inputs at run time | Runner temp folder, removed in `finally` and by an `if: always()` step | none | OPS-02: written only to the runner's temporary folder |
| Result storage | Supabase Postgres, four `psse_*` tables via `dlr_psse_writer` | none | Existing writer; INSERT and SELECT only, no DELETE |
| Public-log control | Python runner (closed vocabulary, stream sinks) | GitHub secret masking (extra layer only) | D-05: masking is explicitly not the plan |
| Gap and soak check | Python runner, read-only connection | owner's closing record | `gaps.run_by_solver` plus a new trailing-count function |
| Go-live and retention decisions | Owner (Aaron) and the user, recorded in repo documents | none | Roadmap success criteria 3 and 4 are recorded human decisions |

## Standard Stack

### Core

No new package is introduced by this phase. Everything below is already pinned and owner-approved in the repository.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.12 on `ubuntu-latest` via `actions/setup-python@v5` | Runner interpreter | Same as `dlr_live.yml`; the pandapower pins were installed and tested on 3.12.10 (02-RESEARCH) |
| pandapower | 3.5.6 | The solver | Pinned and approved at plan 01-05 |
| numpy / pandas / scipy | 2.4.3 / 2.3.3 / 1.17.1 | pandapower's numeric stack | Repeat `requirements.txt` exactly |
| psycopg + psycopg-binary | 3.3.6 + 3.3.6 | Writer connection (imported lazily in `writer.connect`) | Already in `requirements.txt`; the pandapower file does not list them, so the workflow installs them with the same pins |
| pytest | 9.0.3 | Tests only (not installed on the runner) | `requirements.txt` |
| `actions/checkout@v4`, `actions/setup-python@v5` | as in `dlr_live.yml` | Workflow steps | Copy the proven pattern |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| stdlib `base64`, `binascii`, `tempfile`, `shutil`, `json`, `os`, `contextlib` | - | Decode secrets, temp folder, sinks | Runner; no new dependency |
| `psse_job.redaction` (`redact`, `env_secrets`) | in repo | Redact secrets in any text that must be shown | Already applied inside `run_once` and `gaps` |
| `private_leak_scan` (`derive_needles`, `scan_paths`) | in repo | Needles and scan for the leak tests and the real-log scan | Tests and the owner's log check |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Four base64 secrets in env `production` | One combined JSON secret | A combined JSON is structured data; GitHub says structured values can defeat redaction. Four single-line base64 values are exact-match maskable. Combined size would also be about 33 KB for the network alone |
| gzip + base64 | plain base64 | Plain base64 of the 25,191-byte network is 33,588 characters (under 49,152). gzip + base64 is about 4,308 characters. Plain is simpler; gzip leaves room if the mapping grows. Planner's choice; both fit |
| New dry-run function in `psse_job/job.py` | New code in `pandapower_job/hourly.py` | `psse_job` is the laptop job and the roadmap says only default-preserving additions; `pandapower_job` may import `psse_job`, never the reverse (`pandapower_import_gate_test.py`). Keep the dry path on the pandapower side |
| `job.run_once` with a fake `connect` for the dry run | A dry path with no connect at all | A fake connection would still run `writer.write_run` and report `written`, which misstates a dry run; a path with no connect parameter makes "never writes" a structural fact |

**Installation (runner):**
```bash
python -m pip install --upgrade pip
python -m pip install -r requirements-pandapower.txt psycopg==3.3.6 psycopg-binary==3.3.6
```
`[VERIFIED: requirements-pandapower.txt:21-24 "pandapower==3.5.6 / numpy==2.4.3 / pandas==2.3.3 / scipy==1.17.1"; requirements.txt:38-39 "psycopg==3.3.6 / psycopg-binary==3.3.6"]`

**Version verification:** pins are read from the two requirements files this session. They were not re-queried against the PyPI registry for newer releases because the phase installs exactly the pins. pandapower's other declared requirements (networkx, pandera, pydantic, deepdiff, geojson, typeguard, orderly-set, cachebox, colorama, packaging, tqdm) are **not pinned** `[VERIFIED: requirements-pandapower.txt:17-20]`, so each hourly run resolves them fresh (Pitfall 9).

## Package Legitimacy Audit

No new package is installed. The three packages the runner installs are existing, pinned, owner-approved dependencies. The legitimacy seam was run anyway and its verdicts are reported as returned.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| pandapower | PyPI | latest release 2026-10-07 (pin 3.5.6) | unknown to the seam | github.com/e2nIEE/pandapower | SUS (`unknown-downloads`) | Already approved by the owner at plan 01-05 on 2026-11-16 (`requirements-pandapower.txt:8-14`); no new install, no new checkpoint needed |
| psycopg | PyPI | latest release 2026-11-12 (pin 3.3.6) | unknown to the seam | psycopg.org | SUS (`too-new`, `unknown-downloads`) | Already approved at production-pipeline plan 04-01 (`requirements.txt:35-37`); pin unchanged |
| psycopg-binary | PyPI | latest release 2026-11-12 (pin 3.3.6) | unknown to the seam | psycopg.org | SUS (`too-new`, `unknown-downloads`) | Same as psycopg |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** pandapower, psycopg, psycopg-binary, all by the seam's rules, not by anything about the pinned versions. `unknown-downloads` is because PyPI exposes no download count to the seam, and `too-new` describes the newest release, not the 3.3.6 pin. These are already installed in the repo's `.venv` (`pip list` shows pandapower 3.5.6, psycopg 3.3.6, psycopg-binary 3.3.6) and in use by merged code. The planner does not need a new `checkpoint:human-verify` for them; it must not add any other package.
`[VERIFIED: gsd-tools package-legitimacy check, run this session]`

## Architecture Patterns

### System Architecture Diagram

```
 cron-job.org  (20 * * * * UTC, POST .../actions/workflows/<file>/dispatches, body {"ref":"main"})
      |
      v
 GitHub: workflow_dispatch  --(file must be on main)-->  job `if: github.ref == 'refs/heads/main'`
      |                                                  environment: production (main-only branch policy)
      |                                                  concurrency group (own), timeout-minutes 30
      v
 checkout -> setup-python 3.12 (+pip cache) -> pip install pins
      |
      v
 step "Run study"  env: 4 base64 secrets + 3 Supabase values + PANDAPOWER_LIVE (from vars)
      |
      |  runner (python -I -B backend/pandapower_hourly.py run)
      |    1. sink stdout/stderr fds + logging + warnings; keep one private printer channel
      |    2. mode = live only if env PANDAPOWER_LIVE == "true"   (absent/other => dry)
      |    3. decode secrets -> temp folder (0700): network.json, mapping.json,
      |       report/scaling docs -> engine.load_recorded_backend -> backend
      |    4. live and engine.is_placeholder(backend)?  --yes--> refuse, exit 2, no connect
      |    5. engine.prepare_run(backend, network.json, mapping.json, allow_placeholder=False)
      |    6a. DRY:  ratings read (REST, read-only) -> study -> validate_results -> build rows
      |             -> print counts + "nothing was written"        [no connect exists in this path]
      |    6b. LIVE: job.run_once(fetch, study, connect, ..., solver=engine.SOLVER)
      |             -> writer.write_run as dlr_psse_writer (one transaction) -> print status words
      |    7. finally: rmtree temp folder; unsink; exit code (0 / 1 / 3 / 2)
      v
 step "Gap and soak check" (read-only connection)
      |    gaps.run_by_solver(env, expected=(engine.SOLVER,), out=captured)  -> filtered lines
      |    soak count of trailing complete hours with a non-failed pandapower run
      v
 step "Remove private files" (if: always())  -> public log = closed-vocabulary lines only

 Owner side (never in CI):  data/private/pandapower/sessions/.../check_*/  -- `bundle` command -->
      4 base64 files (git-ignored) -> `gh secret set --env production` (Aaron, admin) ; counts-only output
 After first dry runs:  gh run view <id> --log -> scan with private_leak_scan needles from data/private
```

### Recommended Project Structure
```
.github/workflows/
└── pandapower_hourly.yml            # copy of dlr_live.yml shape; name is discretion
backend/
├── pandapower_hourly.py             # entry, same 15 lines as pandapower_replay.py
└── pandapower_job/
    └── hourly.py                    # runner: run / soak / bundle subcommands, closed printer, sinks
backend/tests/
├── pandapower_hourly_test.py            # pure tier: gate, placeholder refusal, temp cleanup, vocabulary
├── pandapower_hourly_leak_test.py       # planted identifiers, scans, teeth (copy of 04-04 pattern)
├── pandapower_hourly_pg_test.py         # DB tier: dry run leaves four tables unchanged; live writes one set
├── pandapower_soak_test.py              # trailing-slot function against an independent oracle
└── pandapower_hourly_workflow_test.py   # text test of the workflow (regex; no PyYAML)
docs/data-science/decisions/
├── pandapower_hourly_runbook.md         # secrets list, cron job, switch, pause, soak steps
└── pandapower_live_write_decision.md    # OPS-03 recorded owner decision (dated)
.planning/workstreams/pandapower-solver/phases/05-hourly-workflow-dry-run-and-live-soak/
├── 05-RETENTION-DECISION.md             # OPS-04, before the first live write
└── 05-SOAK-RECORD.md                    # counts-only OPS-05 record
```
Names are discretion (CONTEXT). The decision-record layout (table with Status, Date, Deciders; Decision; Context; Consequences) follows `docs/data-science/decisions/pandapower_network_data_decision.md`.

### Suggested plan decomposition (for the planner, not binding)
1. **Runner core** (`hourly.py`): gate, secret materialisation, printer and sinks, dry path, placeholder refusal; pure-tier tests including the DB-tier dry-run-unchanged test.
2. **Live path, gap and soak, leak test**: `run_once(..., solver=engine.SOLVER)`, `run_by_solver(..., expected=(engine.SOLVER,))`, the trailing-slot function with an oracle, the planted-identifier test over every path.
3. **Workflow, runbook, owner `bundle` command, workflow text test.**
4. **Retention decision document** (independent, can go first).
5. **Owner checkpoints**, in order: merge to main; create secrets in `production`; add cron job; observe dry runs; real-log scan; record OPS-03 decision; flip `PANDAPOWER_LIVE`; soak; record.

### Pattern 1: Workflow shape (copy of `dlr_live.yml`)
**What:** Dispatch-only, read-only token, own concurrency group, main-only job in the `production` environment, 30-minute timeout, secrets only through `env:`, no workflow inputs.
**Verified values copied from `dlr_live.yml`:** `group: dlr-live` with `cancel-in-progress: false` (lines 28-30), `if: github.ref == 'refs/heads/main'`, `environment: production`, `runs-on: ubuntu-latest` (lines 37-39), `timeout-minutes: 30` (line 45), `actions/checkout@v4`, `actions/setup-python@v5` with `python-version: '3.12'` and `cache: 'pip'` (lines 47-54), `permissions:` `contents: read` (lines 25-26). `[VERIFIED: .github/workflows/dlr_live.yml:25-54]`
**Differences for this phase:** no `inputs:` at all (the fault-city input of `dlr_live.yml` is the only input there; a dispatcher must not be able to flip live mode, so the variable is the only switch); install `requirements-pandapower.txt` plus the two psycopg pins; `cache-dependency-path: requirements-pandapower.txt` (the action's default searches `requirements.txt`, so without it the cache key would hash the wrong file `[CITED: github.com/actions/setup-python README]`); run through the entry script with `python -I -B`.
**Skeleton (design, names are discretion):**
```yaml
name: pandapower hourly

on:
  workflow_dispatch: {}            # cron-job.org (20 * * * * UTC) and manual runs; no inputs

permissions:
  contents: read

concurrency:
  group: pandapower-hourly         # own group; not dlr-live, not shadow-collection
  cancel-in-progress: false

jobs:
  study:
    if: github.ref == 'refs/heads/main'
    environment: production
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false     # optional hardening: nothing here pushes
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'
          cache-dependency-path: requirements-pandapower.txt
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install -r requirements-pandapower.txt psycopg==3.3.6 psycopg-binary==3.3.6
      - name: Run study
        env:
          PANDAPOWER_LIVE: ${{ vars.PANDAPOWER_LIVE }}
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_PUBLISHABLE_KEY: ${{ secrets.SUPABASE_PUBLISHABLE_KEY }}
          SUPABASE_PSSE_DB_URL: ${{ vars.PANDAPOWER_LIVE == 'true' && secrets.SUPABASE_PSSE_DB_URL || '' }}
          PANDAPOWER_NETWORK_B64: ${{ secrets.PANDAPOWER_NETWORK_B64 }}
          PANDAPOWER_MAPPING_B64: ${{ secrets.PANDAPOWER_MAPPING_B64 }}
          PANDAPOWER_SETTINGS_B64: ${{ secrets.PANDAPOWER_SETTINGS_B64 }}
        run: python -I -B backend/pandapower_hourly.py run
      - name: Gap and soak check
        env:
          SUPABASE_PSSE_DB_URL: ${{ secrets.SUPABASE_PSSE_DB_URL }}   # read-only session only
        run: python -I -B backend/pandapower_hourly.py soak
      - name: Remove private files
        if: always()
        run: rm -rf "$RUNNER_TEMP"/pandapower_hourly_*
```
Facts behind the skeleton: `vars` is available in `env` and in a job `if`; an undefined variable is an empty string; `secrets` is **not** available in job or step `if` `[CITED: docs.github.com/en/actions/reference/workflows-and-actions/contexts]`. The `a && b || ''` form hands the writer URL to the study step only when the variable is exactly `true`; this is optional defence in depth (Open Question 4).
**Dispatch only works from the default branch:** "This trigger only receives events when the workflow file is on the default branch." `[CITED: docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax]`

### Pattern 2: The `PANDAPOWER_LIVE` gate
**What:** The workflow copies `vars.PANDAPOWER_LIVE` into one environment variable; the runner treats the run as live only for the exact text `true` (case-sensitive), everything else, including empty, `True`, `1`, `yes`, is dry. D-02 says "anything but `true`".
**Safe default:** an absent variable evaluates to an empty string `[CITED: contexts docs]`, so a fresh repository, a deleted variable or a typo all give a dry run. `gh variable list` returned no variables on 2026-11-25, so the first merged run will be dry. `[VERIFIED: gh variable list and gh variable list --env production, both empty, this session]`
**Printed:** one word, `mode: dry` or `mode: live`, so the log and the recorded owner decision can be matched.
**Where the variable lives:** the repository (D-02). Do not also define it at the environment level; `vars` merges repository, organisation and environment levels and the docs read this session do not state a precedence between them, so one level avoids the question `[CITED: contexts docs]`.

### Pattern 3: Materialise private inputs, then remove them
**What the engine needs (read this session):**
- the network file, loaded by suffix: `_build_master` treats a path ending `.json` as the converted network (`convert.case_from_json`), anything else as RAW `[VERIFIED: api.py:107-118]`;
- the mapping file path for `engine.prepare_run(backend, case_path, mapping_path, allow_placeholder=False, clock=None)` `[VERIFIED: engine.py:143]`;
- a `PandapowerBackend` from `engine.load_recorded_backend(check_dir)`, which reads `report.json` (key `settings`) and `scaling_details.json` from a folder, each carrying the `cli.REPORT_MARKER` key set to 1, strict JSON, at most `MAX_RECORD_BYTES = 1048576` `[VERIFIED: engine.py:179, 299-334]`.

**The gap in CONTEXT:** the third item is not a network, mapping, writer or ratings secret, and the owner's `report.json` is the Phase 1 check report, which also holds `net03` verdicts, `parity` differences and `d06_evidence` `[VERIFIED: cli.py:506-516, 527, 544]`. D-08 of Phase 1 says the PSS/E reference answers never go to a secret or CI. So the runner needs a **trimmed settings bundle**: only the six settings keys, optionally the `session` hashes, and the scaling document with its three detail keys. `_check_settings_keys` demands exactly the six keys `enforce_q_lims, tolerance_mva, max_iteration, collapse_voltage_pu, sources, deviations` `[VERIFIED: engine.py:182-183, 204-211]`; `_details_from_record` accepts the three detail keys plus optional `evidence, snapshots_wanted, snapshots_read` and the marker `[VERIFIED: engine.py:184-185, 253-268]`. The recorded values are non-placeholder and `enforce_q_lims` is decided (02-07 summary).
**Recommended mechanism:** an owner command `bundle` (in the same runner module, prints counts only) that reads the newest check folder, writes the four files under `data/private/pandapower/` through `private.write_private_bytes`, base64-encodes each to a single-line file, and prints byte counts and a fits-the-limit word. The owner runs `gh secret set NAME --env production < file`. The runner decodes strictly (`base64.b64decode(..., validate=True)`), size-checks (each decoded file at most `convert.MAX_CONVERTED_BYTES` for the network, `engine.MAX_RECORD_BYTES` for the rest), writes into `tempfile.mkdtemp(prefix=..., dir=os.environ.get("RUNNER_TEMP") or None)` (mode 0700), names the files `network.json`, `mapping.json`, `report.json`, `scaling_details.json`, and removes the folder in `finally`. `case_id` stored for each run is the file's base name (`run_record.case_label`), so a neutral name like `network.json` is stored, not a path.
**Size:** `SECRET_LIMIT_BYTES = 49152` `[VERIFIED: convert.py:34]`; the network is 25,191 bytes `[VERIFIED: pandapower_network_data_decision.md:23]`, so plain base64 is 33,588 characters (4 x ceil(25191/3), computed). GitHub: "Secrets are limited to 48 KB in size." `[CITED: docs.github.com/en/actions/reference/security/secrets]`
**Why base64 and one value per secret:** "To help ensure that GitHub redacts your secrets in logs correctly, avoid using structured data as the values of secrets." `[CITED: same page]` and "Because there are multiple ways a secret value can be transformed, this redaction is not guaranteed." `[CITED: docs.github.com/en/actions/concepts/security/secrets]`. A single-line base64 string is an exact-match value. The runner never prints the decoded content.
**Where the secrets live:** the `production` environment already exists with a main-only deployment policy and no required reviewers, and holds the environment secret `SUPABASE_DB_URL` (`gh api .../environments/production` and `gh secret list --env production`, names only, this session). Put the new secrets there too: a branch that edits the workflow cannot read them even if the `if` guard were bypassed. Do **not** add required reviewers: an approval wait would stall every hourly run `[CITED: docs.github.com/en/actions/concepts/security/secrets "A workflow job cannot access environment secrets until approval is granted by required approvers."]`.
**Env names for the Supabase values:** the existing code reads exactly these: `ENV_SUPABASE_URL = "SUPABASE_URL"`, `ENV_PUBLISHABLE_KEY = "SUPABASE_PUBLISHABLE_KEY"`, `ENV_PSSE_DB_URL = "SUPABASE_PSSE_DB_URL"` `[VERIFIED: backend/psse_job/constants.py:76-78]`. Using the same names means `writer.connect(env=...)`, `ratings.fetch_latest_rating(env)`, `redaction.env_secrets` and `run_once`'s own redaction work with no change. The writer secret is the `dlr_psse_writer` URL, not the `SUPABASE_DB_URL` of the `dlr_writer` role.
**Connection type:** Supabase says "Direct connections are on IPv6, or on IPv4 if the project has the IPv4 add-on" and "The shared pooler is IPv4-only on every plan, in both session and transaction mode"; session mode is for IPv4-only networks, and pooler users are `[ROLE].[PROJECT-REF]` `[CITED: supabase.com/docs/guides/database/connecting-to-postgres]`. GitHub-hosted runners being IPv4-only is `[ASSUMED]` (A3). The URL stored as the secret should be the session-pooler URL (port 5432), as `dlr_live_runbook.md` already requires for `SUPABASE_DB_URL` (line 94). `writer.connect` already handles a transaction-pooler URL (`prepare_threshold=None`) `[VERIFIED: writer.py:81-82]`.

### Pattern 4: Output discipline (what reaches the public log)
**Three leak routes found, each verified:**
1. **`job.run_once` logs the stored error text.** `log.warning("psse job error for run %s: %s", run_id, error[:constants.LOG_MAX_CHARS])` `[VERIFIED: backend/psse_job/job.py:72-74]`. I ran `logging.getLogger('psse_job.job').warning(...)` in a fresh interpreter with no logging set up and the text appeared on stderr, so in Actions it would be in the public log. The error text of a mapping refusal is `"mapping file not usable: %s" % text` `[VERIFIED: engine.py:158-161]`, and a mapping validation problem can name a branch: `"%s: branch %s is listed twice" % (where, branch.key)` with `key` formatted `"%d-%d-%s"` `[VERIFIED: settings.py:50, 274]`; I ran `parse_settings` on a duplicate extra outage and got `study.contingency.extra[1]: branch 9102-9101-1 is listed twice`. `redact` only removes secrets, not bus keys.
2. **Library output and tracebacks.** pandapower installs no handler (`logging.getLogger('pandapower').handlers` is `[]` after `import pandapower_job.engine`), so its WARNING and above messages fall to Python's last-resort stderr handler; `warnings` and an uncaught exception traceback (whose exception message may hold a bus number) also go to stderr.
3. **Workflow commands.** A line that starts with `::` on stdout is interpreted by the runner (`::error::`, `::warning::` create annotations in the run, `::add-mask::` masks, `::debug::` prints) `[CITED: docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands]`.

**Mitigation (the plan's layer one, D-05):**
- At start the runner saves the real stdout descriptor for its own printer, then points file descriptors 1 and 2 and `sys.stdout`/`sys.stderr` at the null device, sets `logging.disable(logging.CRITICAL)` (or removes handlers and sets `propagate = False` on `psse_job` and `pandapower`), and ignores `warnings`. Restore in `finally`.
- Every line goes through one printer that accepts only lines matching a closed list of patterns, as `replay_cli._Printer.say` does `[VERIFIED: replay_cli.py:62-115]`; a line outside the list is a programming error that prints the generic `error: unexpected (ClassName)` line (a class name only, matching `[A-Z][A-Za-z]{0,39}`) `[VERIFIED: replay_cli.py:417-421]`. No line may begin with `::`.
- Vocabulary (proposed): `mode: dry`, `mode: live`, `inputs: ok` or `inputs: refused (<reason word>)`, `placeholder: refused`, `study: ok` or `study: failed at stage <word>`, `outcome: ok|fallback|failed`, `ratings: city_rating=N static=N`, `rows: run=1 dispatch=N margin=N contingency=N`, `dry run: nothing was written to the database`, `run status: written|already_recorded|failure_recorded|not_recorded`, soak and gap lines (below), `exit: N`. Stage words come from `FAILED_STAGES = ("load_case", "mapping", "apply_ratings", "load_flow", "contingency", "voltage_margin", "dispatch", "validate_results", "write", "internal",)` `[VERIFIED: constants.py:50-53]`. Do not print `run_id`: the PSS/E launcher prints it locally (`launcher.py:581`), the Phase 4 vocabulary excludes it, and it is the key to the stored rows.
- `ratings: city_rating=N static=N` and row counts are counts; the PSS/E dry run already prints the same kind of line `[VERIFIED: launcher.py:632-645]`.
- Layer two is GitHub's masking of the secret values; it is an extra layer only.

### Pattern 5: The dry path
**What exists:** `launcher._dry_run_mode` does it for PSS/E but is private, loads a PSS/E module, and prints `psse_version` `[VERIFIED: launcher.py:602-647]`. `job.run_once` always reaches `connect()` after the study `[VERIFIED: job.py:131-143]`. No pandapower dry run exists.
**What to add (in `pandapower_job/hourly.py`):** the same sequence as `_dry_run_mode`, using public `psse_job` functions: take `started_at` from a clock; `contract.RunContext(run_record.new_run_id(started_at, engine.SOLVER), started_at, case_id, case_sha256, mapping_sha256, run_record.job_version(env), engine.SOLVER)`; `selection = ratings.select_ratings(fetch, started_at)`; `results = prepared.study(selection, context)`; `run_record.validate_results(results, selection)`; `record = run_record.build_run_record(context, selection, finished_at, results=results)`; `rows = run_record.result_rows(record, results)`; print counts. A study failure prints the stage word. **The function takes no `connect` argument and never imports `writer`.**
**Proof "the four tables are unchanged" (D-03):** (a) structural: a test replaces `writer.connect` and `psycopg.connect` with functions that fail the test if called, and runs the dry path with a writer URL present in the environment; (b) database tier: seed the Phase 3 schema with rows of both solvers, take a per-table fingerprint (count plus an md5 over the rows in a fixed order, via `admin_rows`), run the dry path, assert equality; (c) a positive control in the same test file: the live path with the same inputs changes the fingerprint by exactly one run row set, so "unchanged" is shown able to fail. Fixtures to reuse: `pg_helper.cluster`, `apply_solver_schema`, `reset`, `admin_rows`, `valid_run_rows`, `insert_rows`, `RESULT_TABLES` `[VERIFIED: backend/tests/psse_local_pg.py:59, 140, 229, 241, 249, 257, 296]`; the `_connect`, `_counts`, `_run_row`, `_table_rows`, `_checks` helpers of `pandapower_study_job_test.py`.
**Placeholder refusal (D-03):** `engine.is_placeholder(backend)` is true when any solve-setting source starts with `placeholder` or the scaling evidence is a dict with `placeholder` True `[VERIFIED: engine.py:70-77]`. `load_recorded_backend` already refuses placeholder sources (`placeholder_source`, `engine.py:218-219, 265-266`), so a recorded backend cannot be a placeholder; the runner's check is the independent second guard. Order: decide mode, build backend, `if live and engine.is_placeholder(backend)` refuse with exit 2 **before** any connect and before the study. Test with `engine.PLACEHOLDER_BACKEND` injected through a seam (`backend_loader` argument) and `PANDAPOWER_LIVE=true`; assert nothing was connected and nothing written. A dry run with a placeholder backend is allowed only in tests (the runner itself calls `prepare_run(..., allow_placeholder=False)`).

### Pattern 6: Live call, per-solver gap check and the 24-slot soak
**Live call (F-2 of `03-VERIFICATION.md`):**
```python
# Source: backend/psse_job/job.py:77-78 (signature), engine.py:50, api.py:459
# def run_once(fetch, study, connect, case_id, case_sha256=None, mapping_sha256=None,
#              clock=None, env=None, solver=contract.SOLVER_PSSE):
outcome = job.run_once(
    lambda: ratings.fetch_latest_rating(env),
    prepared.study,
    functools.partial(writer.connect, env=env),
    prepared.case_id, prepared.case_sha256, prepared.mapping_sha256,
    clock=None, env=env, solver=engine.SOLVER)      # engine.SOLVER == "pandapower"
# outcome.exit_code: EXIT_OK = 0, EXIT_FAILED_RECORDED = 1, EXIT_NOT_RECORDED = 3  (job.py:33-35)
```
Forgetting `solver=engine.SOLVER` stores a failed `psse-` run with no figures (stage `validate_results`) `[VERIFIED: 03-VERIFICATION.md:183 F-2; engine.py:29-31]`. A test must assert the stored row says `solver = pandapower` and the run id starts `pp-`.
**Per-solver check:** `def run_by_solver(env, since=None, until=None, fail_on_gaps=False, out=None, connect=None, expected=(), failing=None):` `[VERIFIED: gaps.py:292]`; exit codes `EXIT_OK = 0`, `EXIT_GAPS = 5`, `EXIT_CHECK_FAILED = 6` `[VERIFIED: gaps.py:40-42]`. Call with `expected=(engine.SOLVER,)` and `out=` a `StringIO` so the runner can filter the text (F-5: without `expected`, an absent pandapower solver is only reported if it has rows). With `failing=None` PSS/E gaps are listed but never fail; every other present or expected solver fails on a gap or on no rows `[VERIFIED: gaps.py:292-301, 320-330]`.
**Properties of the existing check that shape the soak:**
- `compute_gaps` walks each solver from **its own first slot** to the hour before `current_slot` and "the current hour and later rows are never walked" `[VERIFIED: gaps.py:226-247]`; `failed_only` hours count as gaps.
- The slot of a run is the UTC hour floor of its start (`slot_of`: `replace(minute=0, second=0, microsecond=0)`) `[VERIFIED: run_record.py:66-69]`.
- With the default arguments the check reports gaps back to the first pandapower slot, forever. A run that fails on `fail_on_gaps=True` would stay red after any single missed hour until it ages out of a `since` window; so the hourly step should **report** and not fail on old gaps (Open Question 3).
**Soak function (new, pure):** from the same `(slot_time, solver, outcome)` tuples that `gaps.fetch_runs` returns and the database's `current_slot`, count the trailing run of completed hours (the hour before `current_slot`, then each earlier hour) in which the solver has at least one row whose outcome is not `failed`; stop at the first hour without one. Pass when the count is at least 24. "Any missed hour restarts the clock" then needs no stored state. Test it as Phase 3 tested `compute_gaps`: seeded random histories against an independent plain-loop oracle (`psse_gaps_solver_test.py` does 300 seeds `[VERIFIED: 03-VERIFICATION.md:67]`), plus hand cases: exactly 24, 23 plus a gap, a `failed_only` hour inside, a PSS/E row filling a pandapower hour, rows in the current hour only, an empty table.
**Timing consequence:** because the current hour is never walked, the 24th slot is first counted by the run in the following hour. If the first live run is at 10:20 UTC, slots 10:00 to 09:00 next day are complete at the 10:20 run of the next day, the 25th run. The roadmap criterion ("24 consecutive hourly slots") is therefore shown 24 hours after the first live run, which is the earliest the existing gap semantics can show it.
**Fallback runs:** `outcome_for` gives `fallback` when any city used the static rating `[VERIFIED: run_record.py:90-97]`. A fallback run has figures and counts as a result in the gap check, so a day of fallback runs (ratings stale) would pass the soak. Print the number of fallback slots inside the 24 so the owner sees it (Open Question 7).

### Pattern 7: The planted-identifier leak test (copy of Phase 4 `04-04`)
**What 04-04 did:** every printed line must match the command's vocabulary; two needle sets (A from `private_leak_scan.derive_needles` over a throwaway `data/private`, B built from the test's own run ids, contingency ids, every number of the mapping and results, and the two hashes) are scanned against the captured output; five "teeth" plant a value into a copy of the clean output and require the scan to fire; the clean output is rescanned after the teeth `[VERIFIED: backend/tests/pandapower_replay_output_test.py:1-192]`. Reuse its helpers (`_set_a`, `_set_b`, `_scans_clean`, `_tokens_of`, `_write`) by import or copy.
**For Phase 5 add:**
- Planted **fake secrets** in the environment: a fake writer URL with distinctive user, password, host and project reference; a fake Supabase URL and key; the base64 blobs themselves. Needles: each of those strings, their percent-decoded forms, and the base64 text.
- Capture **all three channels**: the runner's printer output, the process's real file descriptors (`capfd`), and every logging record at DEBUG (`caplog`), then scan the concatenation.
- Cases (each with its own scratch folder): dry success; live success against local Postgres; live success with a fake connection; study failure; mapping refusal whose planted duplicate-outage message holds a bus key (the real finding above); connection failure whose text carries the planted password and host; placeholder refusal; bad base64; oversized secret; `GITHUB_ACTIONS=true` environment; the soak and gap lines.
- Assert no output line starts with `::`, every line matches the vocabulary, and the scratch temp folder is empty afterwards (the existing autouse `_private_temp` fixture sets `tempfile.tempdir` to a scratch folder and tests assert `os.listdir(tempfile.gettempdir()) == []` `[VERIFIED: pandapower_study_job_test.py:72-78, 203]`).
- Teeth: plant the fake password, a mapping branch key, a target figure and a base64 fragment into copies of the clean output and require a hit each. Honest scope as in 04-04: this proves the output cannot carry what the scans know to look for; it does not prove no other secret exists.
- The marker key is never written as a literal in a tracked file; build it from `cli.REPORT_MARKER` (the shape layer of the scanner flags a literal) `[VERIFIED: private_leak_scan.py:49-51]`.

### Pattern 8: The real captured-log check (roadmap criterion 2)
After the first dry runs on Actions, the owner downloads one run's log (`gh run view <id> --log`; the repo is public, so this is public content), stores it outside the working tree or under the ignored `data/private/`, and scans it with `private_leak_scan.derive_needles(<repo>/data/private)` and `scan_paths([log], needles=..., root=...)`, which print `path:line:layer:pattern` and never the text `[VERIFIED: private_leak_scan.py:331, 478-486]`. The command-line scan only walks the working tree, so use a short owner command (an option of the runner, `scan-log --log PATH`, counts only) or an inline call. This is the "real" version of what the unit test rehearses, and it is the evidence for criterion 2.

### Anti-Patterns to Avoid
- **Putting the live switch in a workflow input or in a job `if` on a secret.** `secrets` is not available in `if`; an input lets any dispatcher flip live mode. Use only the repository variable.
- **Inline `${{ ... }}` inside `run:`.** The existing workflow test forbids it (`assert "${{" not in "\n".join(body)`), and GitHub advises env variables over command-line secrets `[VERIFIED: dlr_live_workflow_test.py:79-91]` `[CITED: docs.github.com using-secrets "Avoid passing secrets between processes from the command line"]`.
- **Using `set -x`, `env`, `printenv`, `cat` of any decoded file, or `echo` of a secret in any step.**
- **A shared `report.json` from the check folder as a secret.** It carries NET-03 and parity detail (D-08).
- **Checking decoded files into the workspace** (`$GITHUB_WORKSPACE`): use the runner temp folder only.
- **Hand-rolling the dry run through `run_once` with a fake connection** (reports `written`).
- **Pruning anything:** the writer has no DELETE and D-01 forbids it this phase.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Secret redaction of connection text | A new redactor | `psse_job.redaction.redact`, `env_secrets` | Already handles URLs, passwords (raw and decoded), host, project reference, key tokens, resolved addresses |
| Writing result rows | A new insert path | `psse_job.job.run_once` and `writer.write_run` | All-or-nothing transaction, tag checks, failed-run record, no UPDATE or DELETE |
| Gap detection | A second gap query | `gaps.run_by_solver` and `gaps.fetch_runs`/`fetch_current_slot` | One statement is the gap logic; read-only session proven in tests |
| Recorded-settings parsing | New JSON readers | `engine.load_recorded_backend`, `backend_from_records` | Strict JSON, size cap, placeholder refusal, fail closed |
| Network and mapping parsing | New readers | `convert.case_from_json` via the adapter, `mapping.load_mapping` | Fail-closed, hash recorded |
| Leak scanning in tests | A new scanner | `private_leak_scan.derive_needles` and `scan_paths`, and the 04-04 helpers | Already proven to fire |
| Output allow-list | An ad hoc filter | The `_Printer` pattern of `replay_cli` | A line outside the vocabulary stops the command |
| YAML checks | PyYAML | Regex text tests as in `dlr_live_workflow_test.py` | PyYAML is not installed and "must not be added" per that test's header |
| Dispatch scheduling | A GitHub `schedule:` trigger | cron-job.org | GitHub's scheduler started runs hours late (`dlr_live.yml` header) |

**Key insight:** every security-relevant behaviour in this phase already exists as a proven function. The new code is glue plus a closed output channel; the risk is in what the glue lets through (logging, tracebacks, error text), not in the study itself.

## Common Pitfalls

### Pitfall 1: Nothing can run until the branch is merged to main
**What goes wrong:** the workflow is authored on `feature/pandapower-solver`, but `workflow_dispatch` only receives events when its file is on the default branch, the job is main-only, and `origin/main` (last fetched) lacks the code.
**Why:** `git rev-list --count origin/main..origin/feature/pandapower-solver` returned 132 and the reverse 1; `git ls-tree origin/main backend/` shows `psse_job`, `dlr_live_run.py`, `psse_run_hourly.py` but no `pandapower_job`; `supabase/migrations` on main ends at `20261116200000` (the solver-tag migration `20261118200000` is applied live but its file is not on main); `requirements-pandapower.txt` is not in main's root listing. The remote-tracking refs may be stale; fetch before relying on this.
**How to avoid:** make "merge to main" an explicit owner/user checkpoint before OPS-01 evidence; the workflow is safe to merge because it is dry by default and inert without a cron job. Local verification before the merge is text tests, runner tests and the DB tier only.
**Warning signs:** dispatch returns 404; the Actions tab does not list the workflow.

### Pitfall 2: Creating the cron-job.org job before the workflow exists on main
**What goes wrong:** every dispatch fails; cron-job.org "disables a job that fails more than 25 times in a row (about 6.5 hours at 15 minutes)" `[CITED: docs/data-science/decisions/dlr_live_runbook.md:207-209]`; at hourly cadence that is about a day.
**How to avoid:** create the job only after the merge and one manual dispatch from the Actions tab succeeded. Also note a skipped job (`if` false on a branch dispatch) still returns HTTP 204 to the poker; only main dispatches run.

### Pitfall 3: The recorded settings have no route to the runner
**What goes wrong:** the runner fails closed (`records: refused`) on the first dry run, or someone ships the whole check `report.json`. **How to avoid:** the trimmed settings bundle and the owner `bundle` command (Pattern 3), with a test that the bundle contains none of the report's other keys. **Warning signs:** `inputs: refused (missing_field)` or `(unknown_field)`.

### Pitfall 4: D-01's row-volume premise is off by a factor of about 20
**What goes wrong:** the retention document states "a few hundred rows a day" and a 100,000-row trigger. The real counts: 19 recorded runs hold 76 dispatch rows, 76 margin rows and **3,895 contingency rows**, about 205 per run `[VERIFIED: 04-REPLAY-RECORD.md:11 "rows: dispatch 76, margins 76, contingencies 3895" and :10 "runs: 19"]`. A run is 1 + 4 + 4 + about 205 rows, so 24 runs a day is about 5,100 rows a day, and the 100,000-row trigger is reached in about 20 days. The per-run cap is `MAX_CONTINGENCY_ROWS = 5000` `[VERIFIED: run_record.py:29]`, so the worst case is about 120,000 rows a day. Only violations are written, so volume follows how stressed the grid is `[VERIFIED: docs/data-science/schema/psse_results_v1.md:136 "Only violations are written"]`.
**How to avoid:** D-01 stays locked (keep every row, no pruning) but the written decision should state the true rate and set the trigger knowingly (the owner may keep 100,000 and expect to review in about three weeks, or raise it). The project's size limit is unknown to this research (A5). Do not describe this as an error in the decision; it is a premise to correct in the document.

### Pitfall 5: `run_once` and library logging reach the public log
See Pattern 4. **Warning signs:** any line in the dry run's captured stderr; `psse job error for run` text; tracebacks. **How to avoid:** sinks plus printer, and a test that raises inside the study and inside `connect`.

### Pitfall 6: The gap check makes the job red forever after one missed hour
`compute_gaps` starts at the first pandapower slot. With `fail_on_gaps=True` and no `since`, one missed hour keeps every later run red. **How to avoid:** report-only in the hourly step plus the soak function; a final owner check with `since=<first live slot>`. The workflow still turns red on a failed or unrecorded study (exit 1 or 3), as `dlr_live.yml` does, and GitHub's failure email is the alert.

### Pitfall 7: The first soak slot is wrong if the variable flips mid-run
The variable is read at run start. A flip during an in-flight dry run does not change that run. Record the first live run by its slot, not by the flip time. Manual re-runs from the Actions tab use the variable's current value and add an extra permanent row set in the same slot (the check tolerates two runs in one slot); avoid manual dispatches during the soak.

### Pitfall 8: The ratings are not fresh at :20
`STALE_AFTER_MINUTES = 90` `[VERIFIED: constants.py:38]`; the rating job fires at minute 05 `[VERIFIED: dlr_live_runbook.md:57 "5 * * * *", :63 "Why minute 05"]`, so at :20 the newest rating is normally minutes old. A late or failed rating run makes cities fall back to static (outcome `fallback`). That is allowed, recorded, and counted as a result by the gap check; Pattern 6 prints the fallback count.

### Pitfall 9: Unpinned transitive dependencies change between hourly runs
pandapower's own requirements are not pinned (above). A new networkx or pandera release changes an hourly run without a code change. **How to avoid (optional, discretion):** commit a constraints file generated by `pip freeze` from the owner's verified venv and install with `-c`; pass the cache key through `cache-dependency-path`. The stored `solver_version` records only pandapower's version. No new package is needed.

### Pitfall 10: Linux versus the owner's machine
AGR-02 passed on the owner's machine (19 of 19, `04-REPLAY-RECORD.md`), not on `ubuntu-latest`. The agreement tolerances absorb floating-point noise, and a rating-bound margin may differ by one stored step, but a borderline element could flip. `[ASSUMED]` (A2). **How to avoid:** the dry-run observation period is also the first Linux run; compare its counts (rows, contingency count) with the owner's local four-city dry result and record that in the OPS-03 decision.

### Pitfall 11: Windows differences when running the tests locally
Three CRLF byte-hash tests and `test_is_provisional_reads_the_real_labels` (no `matplotlib`) fail on this Windows checkout `[VERIFIED: 03-VERIFICATION.md:79]`; a Phase 1 CLI test that asserts mode `0o600` fails on Windows (`02-03` decision line in `STATE.md`). Do not assert file permission bits in new tests on Windows (skip when `os.name == "nt"`), and do not pin workflow or SQL file bytes (`autocrlf` is `true` here). Text tests that open the workflow in text mode and use `\s*$` patterns are safe (the existing workflow test passes here).

### Pitfall 12: A fetched documentation page carried instructions
While researching, the Supabase connection page contained an embedded request for the reader to file feedback with a vendor. It was ignored; it is untrusted tool output, not a project instruction. Noted so nobody treats it as part of the docs.

## Code Examples

Verified patterns from this repository.

### Verified in-repo values used by the examples
```text
# backend/psse_job/constants.py:76-78
ENV_SUPABASE_URL = "SUPABASE_URL"
ENV_PUBLISHABLE_KEY = "SUPABASE_PUBLISHABLE_KEY"
ENV_PSSE_DB_URL = "SUPABASE_PSSE_DB_URL"
# backend/psse_job/job.py:33-35
EXIT_OK = 0
EXIT_FAILED_RECORDED = 1
EXIT_NOT_RECORDED = 3
# backend/psse_job/gaps.py:40-42
EXIT_OK = 0
EXIT_GAPS = 5
EXIT_CHECK_FAILED = 6
# backend/pandapower_job/api.py:459 and engine.py:50
SOLVER_NAME = "pandapower"
SOLVER = api.SOLVER_NAME
# backend/pandapower_job/engine.py:143
def prepare_run(backend, case_path, mapping_path, allow_placeholder=False, clock=None):
# backend/pandapower_job/engine.py:320
def load_recorded_backend(check_dir):
# backend/pandapower_job/convert.py:34
SECRET_LIMIT_BYTES = 49152
# backend/psse_job/run_record.py:29
MAX_CONTINGENCY_ROWS = 5000
# backend/psse_job/gaps.py:292
def run_by_solver(env, since=None, until=None, fail_on_gaps=False, out=None, connect=None, expected=(), failing=None):
# backend/pandapower_replay_cli.py:345-346 (CI detection to copy)
ci = bool(args.ci) or environ.get("GITHUB_ACTIONS") == "true"
```

### The mode gate and the placeholder refusal
```python
# Design (names are discretion); semantics from D-02 and D-03.
def decide_mode(environ):
    return "live" if environ.get("PANDAPOWER_LIVE") == "true" else "dry"

mode = decide_mode(environ)
backend = load_backend(temp_dir)                       # engine.load_recorded_backend(temp_dir)
if mode == "live" and engine.is_placeholder(backend):  # engine.py:70
    say("placeholder: refused")
    return 2                                           # before any connect, before the study
```

### The soak count (pure)
```python
# Over (slot_time, solver, outcome) tuples as gaps.fetch_runs returns them (gaps.py:196-199).
def trailing_slots(runs, current_slot, solver="pandapower"):
    have = set()
    for slot, name, outcome in runs:
        if name == solver and outcome != "failed":
            have.add(slot.replace(minute=0, second=0, microsecond=0))
    count, hour = 0, current_slot - datetime.timedelta(hours=1)
    while hour in have:
        count += 1
        hour -= datetime.timedelta(hours=1)
    return count            # pass when count >= 24 (D-04)
```
Normalise `slot` to aware UTC first, as `gaps._utc` does `[VERIFIED: gaps.py:84-87]`.

### Temp folder and cleanup
```python
folder = tempfile.mkdtemp(prefix="pandapower_hourly_", dir=os.environ.get("RUNNER_TEMP") or None)
try:
    ...                      # write network.json, mapping.json, report.json, scaling_details.json
finally:
    shutil.rmtree(folder, ignore_errors=True)
```

### cron-job.org job (owner; same as `dlr_live`, different file name and minute)
`[VERIFIED: dlr_live_runbook.md:46-58]`: URL `https://api.github.com/repos/aa-phan/D8-DLR-Senior-Design-Project-2026/actions/workflows/<workflow file>/dispatches`, method POST, header `Accept: application/vnd.github+json`, header `Authorization: Bearer <fine-grained token, entered in cron-job.org only>`, header `X-GitHub-Api-Version: 2022-11-28`, body `{"ref":"main"}`, expected HTTP 204, schedule `20 * * * *` in UTC (this phase), failure notifications on. A new fine-grained token (Actions read and write, this repository only, with an expiry reminder) separate from the other jobs' tokens, as the runbook requires (line 76).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| GitHub `schedule:` cron | External poke through `workflow_dispatch` | 2026-10-15 for shadow collection | Start times are reliable; manual runs still possible |
| Laptop-only grid study (PSS/E) | pandapower in Actions, same tables, `solver` column | milestone v1.7 | Always-on; PSS/E stays the reference and is paused (`pss-e-integration/STATE.md:8`) |
| Pooled gap check | Per-solver check | Phase 3 | An hour of one solver cannot hide another's gap |

**Deprecated/outdated:** the `dlr_live_runbook.md` section 3 table lists `SUPABASE_DB_URL` as a repository secret, but it is an environment secret in `production` today (`gh secret list --env production`); repository secrets are `NREL_API_EMAIL`, `NREL_API_KEY`, `SYNOPTIC_TOKEN`. Minor documentation drift; the new runbook should say where each secret lives.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Aaron (the repo owner account `aa-phan`) holds admin rights and will create the secrets, variable, cron job and token. The current account has `push` but not `admin` `[VERIFIED: gh api repos/...: permissions admin false, push true]`, so it cannot | Pattern 3, Summary | The owner checkpoints block; the user must route them to whoever has admin |
| A2 | pandapower on `ubuntu-latest` agrees with the owner's machine within the AGR-02 tolerances (same pinned numpy, scipy, pandapower) | Pitfall 10 | A borderline element flips on Linux; the first dry runs would show a different row count |
| A3 | GitHub-hosted runners are IPv4-only, so the writer URL must be the session pooler (port 5432); and `dlr_psse_writer` can connect through the pooler as `dlr_psse_writer.<project-ref>` | Pattern 3 | The first live connect fails; the dry-run read-only gap step is the proof, so run it before going live |
| A4 | A runner's file descriptors 1 and 2 can be redirected to the null device inside Python without breaking the runner's own log capture of the step | Pattern 4 | The step shows no output at all (safe) or the printer cannot write; the leak test covers the printer path |
| A5 | The Supabase project's size limit is large compared with about 5,000 rows a day; the plan tier and limit are not recorded in the repo | Pitfall 4 | The retention review trigger arrives sooner than the document expects |
| A6 | Base64 values of about 4 KB to 34 KB are accepted by `gh secret set` and exact-match redacted by Actions | Pattern 3 | A secret must be split or gzipped; the 48 KB limit itself is documented |
| A7 | `actions/setup-python` `cache-dependency-path` accepts a single non-default file such as `requirements-pandapower.txt` | Pattern 1 | The cache key or the step fails; fall back to no cache (a minute or two longer) |
| A8 | Setting `persist-credentials: false` on checkout is harmless here (nothing pushes) | Pattern 1 | None beyond a failed checkout step on a typo; optional |
| A9 | The `DLR-PSSE-Hourly` laptop task is no longer running; the repo records the plan to stop it and the live data is consistent with it, but no record says it shows Disabled | Open Question 9 | An enabled task writes `psse` rows at :15; harmless to the per-solver check but would confuse a reader |

## Open Questions (RESOLVED)

All nine were settled on 2026-11-25: questions 1 to 8 by the user approving the recommendations (recorded as D-01 correction and D-07 to D-14 in `05-CONTEXT.md`); question 9 is deferred to an owner check that is non-blocking.

1. **How do the recorded PSE-02 settings reach the runner?**
   - What we know: the engine needs them; the check `report.json` cannot ship (D-08); CONTEXT lists no secret for them.
   - What's unclear: whether the owner wants them as a secret (recommended for consistency) or committed (their values are solver settings from licensed software, and the marker key makes the leak guard flag the files).
   - Recommendation: a trimmed base64 secret built by an owner `bundle` command; owner confirms.
   - **RESOLVED (2026-11-25):** CONTEXT D-08.
2. **Retention numbers (OPS-04).** Premise corrected in Pitfall 4. Recommendation: write the true daily row estimate (about 5,100) and either keep 100,000 as the review trigger (about 20 days) or choose a higher one; keep D-01 (no pruning) as decided.
   - **RESOLVED (2026-11-25):** CONTEXT D-01 (corrected rate of about 5,100 rows a day, no pruning, size-based review trigger instead of 100,000 rows).
3. **Should the hourly gap step fail the run?** Recommendation: no, except when the check cannot run (exit 6); report the soak count each hour and let the owner's closing check use `since=<first live slot>` with `fail_on_gaps=True`.
   - **RESOLVED (2026-11-25):** CONTEXT D-09.
4. **Should a dry run hold the writer credential?** Recommendation: the study step gets it only when live; a separate read-only gap step always gets it, which also proves the credential and the live migration from the runner before the flip. The cost is the credential being present in a step on every run; the step opens a read-only transaction and has no write path.
   - **RESOLVED (2026-11-25):** CONTEXT D-10.
5. **Who merges to main and when?** The workflow is inert without a cron job and dry by default, so merging early is safe; the merge also carries the whole pandapower branch (132 commits as last fetched). The user decides how (a pull request, `gsd-ship`).
   - **RESOLVED (2026-11-25):** CONTEXT D-07: the user will not merge; Aaron pulls into `main` when everything is finished, and the owner steps are checkpoints.
6. **How many dry-run hours before the flip?** Not fixed by CONTEXT. Recommendation: at least three consecutive green hourly dry runs, one real-log scan, and the Linux count comparison (Pitfall 10) before the owner records the OPS-03 decision.
   - **RESOLVED (2026-11-25):** CONTEXT D-11.
7. **Do fallback runs count toward the 24-slot soak?** The gap check counts them (a fallback run has figures). Recommendation: yes, but print the fallback count in the soak line and mention it in the soak record.
   - **RESOLVED (2026-11-25):** CONTEXT D-12.
8. **Repository variable versus environment variable for `PANDAPOWER_LIVE`.** D-02 says repository. Keep one level only.
   - **RESOLVED (2026-11-25):** CONTEXT D-13 (repository variable only).
9. **State of `DLR-PSSE-Hourly`.** The repo records: task registered at :15:15, a one-time `DLR-PSSE-Stop` set to disable it at 2026-11-12 10:00 local, and the job "paused until an always-on licensed host" `[CITED: pss-e-integration/HANDOFF.md:11, 24; pss-e-integration/STATE.md:8]`. The live data show the newest PSS/E slot is 2026-11-12 15:00 UTC `[CITED: 03-VERIFICATION.md:210]`, consistent with the stop. No repo record confirms it reads Disabled. The owner can run `docs/data-science/ops/psse_laptop_status.ps1` (read-only) or `Get-ScheduledTask -TaskName "DLR-PSSE-Hourly"`. **Conflict check:** the PSS/E task runs at :15:15 and takes seconds to a minute or two (a real run wrote in 0.44 s, a four-city dry run took 2.0 s `[CITED: memory notes of the PSS/E workstream]`), and the pandapower job starts at :20 and uses its own concurrency group; they never share a process. Both land in the same hour slot but with different solver tags, and the per-solver check walks each solver on its own, so a PSS/E run cannot fill a pandapower hour. By default PSS/E gaps never fail the check. So :20 UTC does not conflict, whether or not the laptop task is still enabled.
   - **RESOLVED (2026-11-25):** DEFERRED, non-blocking: no conflict either way, so the state is only confirmed by the owner at plan 05-07 Task 2 step 10 (`Get-ScheduledTask -TaskName "DLR-PSSE-Hourly"` or `psse_laptop_status.ps1`).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 (`.venv`) | tests, runner | yes | 3.12.10 | none needed |
| pandapower, psycopg, pytest in `.venv` | tests | yes | 3.5.6, 3.3.6, 9.0.3 | none needed |
| PostgreSQL 17 binaries | DB-tier tests | yes (`C:\Program Files\PostgreSQL\17\bin`) | 17.12 | tier skips without `PSSE_REQUIRE_PG=1` |
| `gh` CLI | owner steps, log download | yes, logged in as `tejaswini013` | 2.102.0 | GitHub web UI |
| git | `job_version` (short commit) | yes | 2.56.0 | `PSSE_JOB_VERSION` env value |
| Node | gsd tooling only | yes | v24.20.0 | n/a |
| GitHub repo admin rights | create secrets, variable | **no** for the current account (`push` only) | - | the repo owner account |
| Secrets `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_PSSE_DB_URL` and the three `PANDAPOWER_*` base64 secrets | workflow | **no** (none exist; only `NREL_*`, `SYNOPTIC_TOKEN` repo secrets and `SUPABASE_DB_URL` in `production`) | - | owner creates them |
| Variable `PANDAPOWER_LIVE` | go-live | not defined (correct for dry run) | - | absence is the dry-run default |
| `production` environment | secrets and branch policy | yes, branch policy `main` only, no required reviewers | - | none |
| cron-job.org account and a new token | the :20 poke | not checked (external; owner's) | - | manual dispatch from the Actions tab for a first test |

**Missing dependencies with no fallback:** repo-admin actions (secrets, variable, cron job, token) must be done by the owner account; the plan needs checkpoints for them.
**Missing dependencies with fallback:** none that block code work.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 `[VERIFIED: requirements.txt:26]` |
| Config file | `pytest.ini`: `pythonpath = backend`, `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py` `[VERIFIED: pytest.ini]` |
| Quick run command | `PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider backend/tests/pandapower_hourly_workflow_test.py backend/tests/pandapower_soak_test.py backend/tests/pandapower_hourly_test.py` |
| Full suite command | the quick set plus `pandapower_hourly_leak_test.py`, then the DB tier below, then the regression set below |
| DB-tier command (Git Bash) | `PATH="/c/Program Files/PostgreSQL/17/bin:$PATH" DLR_TEST_PG_AUTOSTART=1 PSSE_REQUIRE_PG=1 PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider backend/tests/pandapower_hourly_pg_test.py` (the env pattern of `03-VERIFICATION.md:74`) |

Measured this session on Windows: `dlr_live_workflow_test.py`, `psse_gaps_solver_test.py` and `pandapower_import_gate_test.py` together: 23 passed, 1 skipped in about 1 s (the skip is the database test without autostart); `pandapower_replay_output_test.py` plus `pandapower_replay_cli_test.py`: 140 passed in 98 s (the leak-test pattern costs about 12 s of setup and 10 to 14 s per test). The four-city study is about 12 to 36 s on the fixture.

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| OPS-01 | Dispatch-only, no schedule/push/pull_request, no inputs, own group `cancel-in-progress: false`, main-only `if`, `environment: production`, timeout under 60 (30), `contents: read`, python 3.12, installs the pandapower file, entry script | text (regex) | `pytest backend/tests/pandapower_hourly_workflow_test.py -x` | no, Wave 0 (model on `dlr_live_workflow_test.py`) |
| OPS-01 | A branch dispatch does not execute the job | text (the `if` guard) plus owner check on Actions (dispatch from a branch shows the job skipped) | same file; owner step | no, Wave 0 |
| OPS-02 | Every secret mapped through `env:` only; no `${{` inside any `run:`; `vars.PANDAPOWER_LIVE` only in `env`; no `secrets.` in an `if` | text | same file | no, Wave 0 |
| OPS-02 | Private files only in the temp folder and removed on success, failure and exception | unit (scratch `tempfile.tempdir`, empty after) | `pytest backend/tests/pandapower_hourly_test.py -k temp` | no, Wave 0 |
| OPS-02 | No planted secret, bus key, target, or base64 fragment in printer output, fds or logging records, in every path; scan teeth fire | leak test (04-04 pattern) | `pytest backend/tests/pandapower_hourly_leak_test.py` | no, Wave 0 |
| OPS-02 | Real Actions log scanned with real needles | owner check | `scan-log` option or inline `private_leak_scan` call | no, owner step |
| OPS-03 | Absent, empty, `True`, `1`, `false` all give dry; only `true` gives live | unit | `pytest backend/tests/pandapower_hourly_test.py -k mode` | no, Wave 0 |
| OPS-03 | Live plus `engine.is_placeholder` refuses before any connect or study | unit | `-k placeholder` | no, Wave 0 |
| OPS-03 | Dry run leaves the four tables unchanged (fingerprint), no connect called; positive control: live changes them by one set | database tier | DB-tier command | no, Wave 0 |
| OPS-03 | Recorded owner decision with date, evidence of NET-03 and AGR-02, and variable state | document check (grep for the dated line) plus owner step | manual | no, owner step |
| OPS-03 | A live run is stored `solver = pandapower`, run id `pp-`, `solver_version` = pandapower version | database tier | DB-tier command | no, Wave 0 |
| OPS-04 | Retention document exists in the phase directory, states daily rows, no-pruning decision, review trigger, before the first live write | document check | `ls` plus grep in a verification step | no, Wave 0 |
| OPS-05 | Soak function matches an independent oracle on 300 seeded histories; hand cases (24, 23 plus a gap, failed-only inside, PSS/E row not filling, current hour, empty) | unit | `pytest backend/tests/pandapower_soak_test.py` | no, Wave 0 |
| OPS-05 | `run_by_solver` is called with `expected=(engine.SOLVER,)` and its output reaches the log only as vocabulary lines | unit with `connect=` seam | `pytest backend/tests/pandapower_hourly_test.py -k gap` | no, Wave 0 |
| OPS-05 | 24 consecutive slots on the live project | owner check, counts-only record `05-SOAK-RECORD.md` | owner step | no, owner step |

### Regression set (must stay green)
`dlr_live_workflow_test.py`, `psse_gaps_solver_test.py`, `pandapower_import_gate_test.py` (psse_job must not name or import the second solver, so no change inside `backend/psse_job/` that names pandapower), `pandapower_replay_output_test.py`, `pandapower_study_job_test.py`, `pandapower_solver_tag_test.py`, `psse_writer_test.py`.

### Known Windows-only failures (not phase defects)
Three CRLF byte-hash tests (`test_psse_migration_is_unchanged_after_apply`, `test_phase6_migrations_are_unchanged_after_apply`, `test_expose_migration_is_unchanged_after_apply`), `test_is_provisional_reads_the_real_labels` (no `matplotlib`) `[VERIFIED: 03-VERIFICATION.md:79]`, and a Phase 1 CLI test on the `0o600` mode (`STATE.md` 02-03 decision). PostgreSQL tests need the PATH entry above. Do not assert file mode bits; do not pin file bytes.

### Sampling Rate
- **Per task commit:** the quick set above (seconds).
- **Per wave merge:** quick set plus leak test plus DB tier plus the regression set (a few minutes; the DB tier of Phase 3 took 328 s for 137 tests).
- **Phase gate:** everything green, then the owner sequence (merge, secrets, cron, dry runs, real-log scan, decision, flip, soak) before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `backend/tests/pandapower_hourly_workflow_test.py` covers OPS-01 and OPS-02 workflow text.
- [ ] `backend/tests/pandapower_hourly_test.py` covers gate, placeholder refusal, temp cleanup, vocabulary.
- [ ] `backend/tests/pandapower_hourly_leak_test.py` covers OPS-02 planted identifiers.
- [ ] `backend/tests/pandapower_hourly_pg_test.py` covers OPS-03 tables unchanged and the live tag.
- [ ] `backend/tests/pandapower_soak_test.py` covers OPS-05 function.
- [ ] A fixture helper that turns the public fixture (`pandapower_study_fixture.write_converted`, a non-placeholder copy of `write_placeholder_mapping`, and settings documents like those `pandapower_replay_fixture.private_layout` writes) into the base64 environment the runner reads. The placeholder mapping has `placeholder` true, which `prepare_run(..., allow_placeholder=False)` refuses, so the helper rewrites that field in a temp copy.
- Framework install: none (pytest already in `.venv`).

## Security Domain

`security_enforcement` is not set in `.planning/config.json` (absent means enabled), so this section is included.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (service credentials) | `dlr_psse_writer` password only in an environment secret; separate fine-grained dispatch token held only in cron-job.org with an expiry |
| V3 Session Management | no | stateless job |
| V4 Access Control | yes | main-only job `if`; `production` environment with main-only branch policy; `permissions: contents: read`; no workflow inputs; writer role INSERT and SELECT only |
| V5 Input Validation | yes | strict base64 (`validate=True`), size caps, `load_recorded_backend` strict JSON and marker, `convert.case_from_json` and `load_mapping` fail closed; mode compared to the exact text `true` |
| V6 Cryptography | no hand-rolled crypto | base64 is transport encoding, not encryption (GitHub's own note); secrets protected by GitHub |
| V7 Error Handling and Logging | yes (the central risk) | closed output vocabulary, stream and logging sinks, generic error line with a class name only, no `::` lines |
| V8 Data Protection | yes | private data only in secrets and the runner temp folder, removed in `finally` and by an `if: always()` step; nothing written to the workspace |
| V14 Configuration | yes | variable-gated live mode with dry default; pinned dependencies; no `set -x`; secrets only via `env:` |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Secret or bus key printed to the public log (error text, traceback, library warning) | Information disclosure | Printer allow-list, fd and logging sinks, planted-identifier test, real-log scan (Patterns 4, 7, 8) |
| A branch edits the workflow to print secrets | Elevation of privilege | Job `if` main-only plus `production` environment main-only branch policy (verified live), secrets stored as environment secrets |
| Dispatcher flips live mode through an input | Tampering | No inputs; only the repository variable decides |
| Mistaken flip stores placeholder-derived figures | Tampering | `engine.is_placeholder` refusal before any connect (D-03); `load_recorded_backend` refuses placeholder sources |
| Wrong solver tag stores PSS/E-tagged failed rows | Tampering | `solver=engine.SOLVER` asserted by a database test |
| Writer credential exposed in a dry run | Information disclosure | Pass the writer URL to the study step only when live; separate read-only step (Open Question 4) |
| Workflow-command injection through printed data (`::add-mask::`, `::error::`) | Tampering | No printed line may start with `::`; the printer only emits fixed words and counts |
| Over-scoped dispatch token | Elevation of privilege | Fine-grained token, this repository, Actions read and write only, separate from other jobs, expiry reminder |
| Credentials left on disk | Information disclosure | `mkdtemp` mode 0700, `finally` cleanup, always-run removal step; ephemeral hosted runner |
| Third-party action tampering | Tampering | Same two first-party actions as `dlr_live.yml`; optionally pin by commit |
| Secret redaction fails on structured data | Information disclosure | One single-line base64 value per secret; never print decoded content |
| Debug logging reveals values (`ACTIONS_STEP_DEBUG`) | Information disclosure | Keep that secret unset; the closed vocabulary does not print values to begin with |

## Sources

### Primary (HIGH confidence, read this session)
- `.github/workflows/dlr_live.yml`, `backend/tests/dlr_live_workflow_test.py`, `docs/data-science/decisions/dlr_live_runbook.md` (trigger, token, minute 05, cron failure behaviour)
- `backend/psse_job/job.py`, `gaps.py`, `writer.py`, `redaction.py`, `constants.py`, `run_record.py`, `settings.py`, `ratings.py`, `launcher.py`; `backend/pandapower_job/engine.py`, `api.py`, `replay_cli.py`, `private.py`, `cli.py`, `convert.py`; `backend/private_leak_scan.py`
- `backend/tests/pandapower_replay_output_test.py`, `pandapower_study_job_test.py`, `pandapower_import_gate_test.py`, `pandapower_study_fixture.py`, `psse_local_pg.py`, `psse_gaps_solver_test.py` (structure)
- Phase artifacts: `03-VERIFICATION.md`, `04-04-SUMMARY.md`, `04-REPLAY-RECORD.md`, `04-VERIFICATION.md`, `01-11-SUMMARY.md`, `02-07-SUMMARY.md`, `pandapower_network_data_decision.md`, `pss-e-integration/HANDOFF.md`, `pss-e-integration/STATE.md`
- Commands run: `gh secret list`, `gh secret list --env production`, `gh variable list`, `gh api .../environments`, `.../deployment-branch-policies`, `.../repos/...` permissions (names and metadata only, no values); `git rev-list` and `git ls-tree` against the last-fetched `origin/main`; `gsd-tools package-legitimacy check`; pytest runs listed under Validation Architecture; two short Python probes (settings message text; last-resort logging)

### Secondary (MEDIUM confidence, official docs fetched)
- docs.github.com: contexts (`vars`, undefined variable empty string, `secrets` not in `if`), workflow syntax (concurrency pending behaviour, `workflow_dispatch` only on the default branch), secrets reference ("Secrets are limited to 48 KB", avoid structured data, 100 repository and 100 environment secrets), secrets concepts (redaction not guaranteed; environment approvals), workflow commands (`::add-mask::`, `::debug::`, `::error::`, `::stop-commands::`)
- supabase.com/docs/guides/database/connecting-to-postgres (IPv6 direct connections, IPv4-only shared pooler, session mode, `[ROLE].[PROJECT-REF]`)
- github.com/actions/setup-python README (`cache-dependency-path`)

### Tertiary (LOW confidence)
- Web search summary on GitHub's advice to create individual secrets and encode structured data (secondary hosts); used only to support the base64 recommendation, which the primary pages above already back.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH, no new packages; pins read from the files.
- Architecture: HIGH for the wiring (all functions read); MEDIUM for runner-side stream redirection (A4, covered by tests).
- Pitfalls: HIGH for the five verified findings (merge prerequisite, settings route, logging leak, row volume, soak semantics); MEDIUM for Linux agreement and pooler reachability (A2, A3).

**Research date:** 2026-11-25
**Valid until:** 30 days for the code facts (they change only when this workstream changes them); 7 days for the `origin/main` comparison, which depends on the last fetch and on other teams' merges.
