# Phase 1: PSS/E Reference Session and Network Parity - Research

**Researched:** 2026-11-16
**Domain:** one scripted read-only PSS/E 36.4 export session (licensed Windows laptop, Python 3.14) plus a private-data pipeline on the owner's Mac (Python 3.12): fail-closed RAW parser, pandapower 3.5.6 network builder, parity report, base-case match against PSS/E, and a leak guard that must exist before any exported file arrives.
**Confidence:** MEDIUM. HIGH on the repo seams, pandapower behaviour and the conversion maths (all run in this session). LOW to MEDIUM on every PSS/E-side call that the laptop has not yet shown (RAW export call and revision, setting readers, scaling behaviour), which is why the design below makes the session partial-success tolerant and measures behaviour instead of trusting documentation.

This file is tracked in a public repository. It contains placeholder bus numbers (the `9xxxx` convention) and public-case facts only. No real identifier, value, mapping target or laptop path is recorded here.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Session logistics**
- **D-01:** The session runs on the same PSS/E laptop (PSS/E 36.4 Xplore, Python 3.14) with the same teammate. The repo checkout there is already set up.
- **D-02:** Remote, one script. The teammate runs `git pull` and one command, in the style of `docs/data-science/ops/psse_laptop_status.ps1`: it runs end to end, writes everything to one output folder, and prints a short masked summary (counts, statuses, versions; no bus numbers, values, paths, names or targets) that the teammate pastes back. No database access, no network calls, no writes outside its own output folder, and the case file is never saved (in-memory copies only, as the job already does).
- **D-03:** Output is one zip on the Desktop, sent privately to the owner (UT OneDrive/Box share or direct message, the same channel the mapping used). The owner unzips it into the git-ignored private folder (D-07).
- **D-04:** The private per-city mapping goes back to the laptop by the same private channel. The script deletes its copy at the end and says so in the summary. The teammate also deletes the zip after sending; the summary reminds them.
- **D-05:** The session is single-purpose: no dry run of the existing PSS/E job.

**Where private data lives**
- **D-06:** The converted network data stays private on the owner's machine during Phase 1. At the end of Phase 1 the owner decides, with evidence: if the parity report shows the data equals the public IEEE 39-bus case, and its licence permits publication, commit a sha256-pinned copy; otherwise it becomes a GitHub secret for Phase 5 (it must fit the 48 KB limit). — **Reversibility:** one-way — a committed copy is public in git history permanently.
- **D-07:** Private folder: `data/private/pandapower/` inside the repo, git-ignored. The ignore rule and the secret/identifier scan land before any exported file arrives (PSE-04, success criterion 1).
- **D-08:** The PSS/E reference answers stay only on the owner's machine (git-ignored), never in a GitHub secret or CI. The owner keeps a backup wherever the mapping is kept.

**Reference answer scope**
- **D-09:** The session exports full solved answers (every bus voltage and angle, every branch flow and loading, generator P/Q) for each city's scaled base case and for every screened outage of each city (about 4 + 130 solves), with each solve's convergence status. Non-converged and islanded outages are recorded as such, not dropped.
- **D-10:** For each city, the session also exports the voltage-margin search's limit point: the transfer PSS/E finds and the bus voltages at that point. This is where the reactive-limit effect shows up.
- **D-11:** NET-03 (this phase's gate) compares the base cases only. The outage and margin answers are exported now for Phase 2 to test against; they are not a Phase 1 pass/fail gate.

**When numbers don't match**
- **D-12:** Match the data first. A remaining difference is allowed only if it is written up with its cause (for example, transformer modelling) and shown not to break the tolerance elsewhere. Anything unexplained fails NET-03. Network parameters are never tuned to force a match.
- **D-13:** Flow tolerance: a branch passes if its flow is within 2% or within 2 MVA, whichever is looser. Bus voltage tolerance: 0.01 pu absolute.
- **D-14:** pandapower copies whatever reactive-limit and adjustment settings the session reads from PSS/E (PSE-02). The parity check proves the copy; no physics-based override.

### Claude's Discretion
- The exact export format (RAW-class text vs project-defined JSON tables), file names inside the zip, and the parser's structure, provided the parser fails closed on unknown record types (NET-01).
- Exactly which `psspy` calls read the settings and the scaling details, chosen from the PSS/E 36.4 docs on the laptop and verified in the session.
- The masked summary's exact lines, following the masking rules of the existing laptop scripts.
- Whether the minimal Phase 1 scaling and load-flow code lives in `backend/pandapower_job/` from the start (recommended, so Phase 2 extends it).

### Deferred Ideas (OUT OF SCOPE)
None raised in discussion.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PSE-01 | A teammate can run one scripted, read-only session on a licensed PSS/E machine that exports the 39-bus case's network data (buses, loads, shunts, machines with limits and setpoints, every branch and two-winding transformer with its ratings) to a private text file, and returns a masked report of what was exported. | Session design (Pattern 1): RAW export of the loaded case as the network source, section-isolated so one unverified call cannot lose the rest; masked summary built from integers and enums only; reuse of `psse_job` loader, config reader, `PsseApi` and `redaction`. |
| PSE-02 | The same session records PSS/E's load-flow solution settings that affect agreement (reactive-limit handling, tap and switched-shunt adjustment, mismatch tolerance, iteration limit) and the three scaling details. | Pattern 2: settings read by candidate `prmdat`/`prmint` names plus behavioural fingerprints (solve with explicit option lists, machine Q against limits); the three scaling details measured from in-memory RAW snapshots before and after scaling experiments, analysed offline. Settings-to-pandapower table. |
| PSE-03 | The same session exports a private reference solution: every bus voltage and every branch flow for the base case of each city's scaled copy, and for each screened outage. | Pattern 3: the session replays the job's own functions (`index_case`, `prepare_city_base`, `contingency.select_outages`, `margin.city_margin`) so the reference copy and outage list are the job's; verified end to end against the repo's fake psspy this session. |
| PSE-04 | Nothing from the session is committed; the ignore rules and a secret/identifier scan are in place before any exported file reaches the owner's machine. | Pattern 4: `.gitignore` rule (currently absent, verified), three-layer guard (path, shape, owner-local exact needles) scanning tracked plus untracked-not-ignored files, fixtures generated at test time so no export-shaped file is ever tracked. |
| NET-01 | The job builds a pandapower network from the PSS/E export, keeping PSS/E bus numbers as bus indices and `from-to-circuit` names for branches, and refuses any record type it does not understand. | Pattern 5: stdlib RAW v33 tokenizer and section state machine (fail closed), builder with formulas verified against `case39()` to 1e-15 and against an independent Ybus solve for 16.5/345 and 138/345 kV transformers. |
| NET-02 | A parity report compares the built network with the PSS/E export element by element (counts, line vs transformer classification, ratings, limits, setpoints) and lists every difference; it must show none. | Pattern 6: independent inverse read-back from the pandapower tables, per-category diff, mutation tests for each category; informational comparison against `case39()` for the D-06 evidence. |
| NET-03 | The base-case load flow of each city's scaled copy matches the PSS/E reference solution: every bus voltage within 0.01 pu and every branch flow within 2% (with an absolute floor). | Pattern 7: minimal scaling plus `runpp` in `backend/pandapower_job/`, settings copied per D-14, comparison with the D-13 rule, explained-difference registry per D-12, pre-solve injection comparison to separate scaling error from network error. |
</phase_requirements>

## Summary

The phase is mostly ordinary Python work that can be finished and tested on the Mac with placeholder data, and one external event (the session) whose success depends on PSS/E calls that nobody has run on the laptop yet. The research therefore concentrates on two things: making the session survive its own unverified calls, and making everything downstream of the session iterable on the owner's machine without going back to the laptop.

Recommended shape, all of it consistent with the locked decisions. (1) Guards first: add `/data/private/` to `.gitignore` (today `git check-ignore -v data/private/pandapower/x.json` returns rc=1, i.e. not ignored) and a three-layer leak guard, before anything else is built. (2) The session exports the network as a **RAW text file written by PSS/E itself** and takes every other state snapshot (pre-solve scaled injections, solved states, scaling experiments) as further in-memory RAW snapshots. That removes the dependence on a dozen unverified bulk-reader item names, because a RAW file carries bus voltage and angle, load P/Q, machine P/Q and limits, branch data and transformer data in one standard text (that a RAW written from the solved in-memory case holds the solved values is Assumption A3). Solved branch flows come from the already laptop-proven `branch_loading` read (P, MAXMVA, percent of RATEA). The RAW export call itself is the single critical unknown, so the script tries a short candidate list and records each ierr; the parser lives on the Mac and is iterated against the real private file there. (3) The session reuses the job's own functions so the reference copy and outage list are the job's by construction; this call sequence was run against the repo's fake psspy in this session and works. (4) The Mac side is a new `backend/pandapower_job/` package: fail-closed RAW v33 parser, builder, parity report, minimal scaling and `runpp`, comparator. The builder formulas reproduce pandapower's own `case39()` to 1e-15 and match an independent Ybus solve for transformers between different base kV.

The main risk that survives all of this is parity that proves only transcription. The parity report is written by the same hand as the builder, so it can pass while both misread a PSS/E convention. NET-03 against PSS/E's own numbers is the independent check, which is why the session also exports pre-solve injections: a mismatch can then be attributed to the network, the scaling rule or the solver instead of being one opaque difference.

**Primary recommendation:** Build the guards first, then in parallel (a) the laptop session script with section isolation and RAW snapshots, tested against a fake-psspy subclass, and (b) the Mac-side parser, builder, parity and comparison on synthetic fixtures generated at test time; request RAW revision 33 from PSS/E because its record layout is the best documented; and treat the first real file as an explicit local iteration task, not a surprise.

## Project Constraints (from CLAUDE.md)

No project `./CLAUDE.md` or `./.claude/CLAUDE.md` exists, and `.claude/` holds no skills (`ls .claude` shows `jobs`, `scheduled_tasks.lock`, `settings.local.json`, `worktrees`) [VERIFIED: command run this session]. The directives that apply come from the user's global instructions and auto-memory:

- Never shell-source `.env` (shell errors echoed database passwords); if environment values are ever needed, load through python-dotenv. Nothing in this phase needs `.env`; the session has no database access (D-02).
- Plain-English setup before any option question put to the owner; no unexplained jargon (relevant to the D-06 owner decision write-up and to any checkpoint text).
- A low-side static-rating fallback is safe; only above-band ratings are a safety issue. Relevant to the reference ratings: the session applies static ratings (see Pitfall 6).
- User clock times are Central, 12-hour, often without am/pm: convert explicitly to UTC when scheduling the session or reading timestamps.
- Global: `/graphify` skill exists; the graph at `.planning/graphs/graph.json` is 839 commits stale (built 2026-10-07) and was not used for this research.
- Git: branch is `feature/pandapower-solver`; do not create or switch branches. `.planning/` is tracked (620 files), so every planning document is public.

## Architectural Responsibility Map

This is not a web application; the tiers are the machines and artifacts that own each capability.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Reading the case, scaling, solving, tripping branches, writing RAW | Licensed laptop (PSS/E 36.4, Python 3.14, `psspy`) | — | Only place `psspy` and the licence exist; stdlib only, Python 3.7-compatible syntax like `psse_job` |
| Masking the summary, zip and manifest | Laptop session script | Laptop PowerShell wrapper (thin) | Logic stays in Python so it is testable on the Mac; there is no `pwsh` on the Mac to test a `.ps1` |
| Private transfer and storage | Owner's machine, `data/private/pandapower/` | Owner's backup location (D-08) | Never git, never CI, never a secret for reference answers |
| Leak guard | Repo: `.gitignore`, a stdlib scanner, a pytest test | Local pre-commit step | Git history is permanent; the check must run before a commit, not after a push |
| RAW parsing (fail closed) | `backend/pandapower_job/` (Python 3.12) | — | Parser runs where the private file is; iterated locally against the real export |
| Network build, parity, scaling, solve, comparison | `backend/pandapower_job/` | `psse_job` pure modules reused (`mapping`, `settings`, `units`) | Phase 2 extends the same package; one-way dependency on `psse_job` |
| Decision evidence for D-06 | Parity report section (export vs `case39()`) | Owner | Evidence only; the commit-or-secret choice is the owner's |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandapower | 3.5.6 (PyPI, released 2026-10-07) | Network model and AC Newton-Raphson load flow on the Mac | The milestone's named solver; installed and run in a scratch Python 3.12.13 venv this session with numpy 2.4.3, pandas 2.3.3, scipy 1.17.1; `pip check` reported "No broken requirements found." [VERIFIED: pip run this session] |
| Python stdlib (`json`, `hashlib`, `zipfile`, `re`, `argparse`) | 3.12 (Mac), 3.14 (laptop) | RAW tokenizer, manifest hashes, zip, CLI | No third-party RAW reader is suitable (see Alternatives); stdlib keeps the laptop side dependency-free |
| `psse_job` (in repo) | current | Laptop side: `launcher.read_config`, `launcher.add_search_dirs`, `launcher.start_psspy`, `psse_run_hourly.load_psspy`, `PsseApi`, `study.*`, `contingency.select_outages`, `margin.city_margin`, `redaction.redact`; Mac side: `mapping.parse_mapping`, `settings`, `units` | Reuse makes the reference the job's own study and the mapping parse identical |
| pytest | 9.0.3 (installed in `.venv`) | Tests | `pytest.ini`: `pythonpath = backend`, `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py` [VERIFIED: pytest.ini] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `backend/tests/psse_fake_psspy.py` `FakePsspy` | in repo | Fake for session tests | Subclass in a new test helper to add the extra calls the session uses; do not edit the fake (a drift test ties it to `SURFACE` exactly) |
| `backend/tests/secret_scan_test.py` helpers (`_scan`, `_readable`, `_tracked_files`, `_scan_exact`) | in repo | Pattern for the leak guard | Import or copy the approach; its "never print the matched text" rule applies |
| `pandapower.networks.case39()` | 3.5.6 | Test fixture source and the D-06 comparison target | Public MATPOWER-derived data; fixture only, never the production network |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| RAW text from PSS/E as network source | Project JSON built from many `psspy` bulk readers | Item names for machines, loads, transformers are unverified on 36.4, and a wrong name needs the laptop again; RAW is one call and can be re-parsed locally. Keep a few proven bulk reads only as an independent cross-check |
| Stdlib RAW tokenizer | `grg-pssedata` 0.1.4, `pypowsybl`, `psse2mpc`, pandapower `from_mpc` | Unmaintained and v33-only, native GraalVM, MATLAB, or lossy (reclassifies the ratio-1.0 branch, loses bus numbers); none gives fail-closed control. Research SUMMARY already rejected them |
| Request RAW revision 33 | Whatever revision `rawd_2` writes by default (possibly 36) | v33 has a published field table (PowerModels `pti.jl`); v35 and v36 add records not tabulated in any source reached here. Support the revision actually produced, one field table per revision |
| One RAW per snapshot | Bulk machine/load readers (`amachreal`, `aloadreal`) | Fewer unverified names with RAW; cost is a few extra files of about 14 KB each |

**Installation:**
```bash
# requirements-pandapower.txt  (new file at the repo root, per CONTEXT)
pandapower==3.5.6
numpy==2.4.3
pandas==2.3.3
scipy==1.17.1
# keep numpy <2.5 and pandas ~=2.3: pandapower 3.5.6 declares pandas~=2.3, numpy<2.5,>=1.26 [CITED: research/STACK.md]
.venv/bin/python -m pip install -r requirements-pandapower.txt
.venv/bin/python -m pip check
```
The repo `.venv` is Python 3.12.13 with numpy 2.4.3, pandas 2.3.3, scipy 1.17.1 and tqdm 4.67.3, and has no pandapower; installing upgrades tqdm and adds networkx, pandera, pydantic, deepdiff, geojson and others [VERIFIED: `.venv/bin/python -m pip list` and import attempt this session].

**Version verification:** `pandapower 3.5.6`, wheel `pandapower-3.5.6-py3-none-any.whl` uploaded 2026-10-07T11:00:03, sha256 `b6d15d0d506136fd0b8d58a18c2e05ad4947fe1c8d5db2b74c9615cbb473c877`; requires Python `>=3.10` [VERIFIED: PyPI JSON API this session].

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| pandapower | PyPI | since 2017-01-12, 62 releases | about 162,000 per week (pypistats `last_week`) | github.com/e2nIEE/pandapower, 1,330 stars, last push 2026-11-16, not archived | SUS (seam reason: `unknown-downloads` only) | Owner named it in the milestone; independent evidence above supports it. Per protocol the planner adds one `checkpoint:human-verify` to confirm the pin and wheel hash before the first install |
| networkx, pandera, deepdiff, geojson, typeguard, orderly-set, cachebox, pydantic, colorama, tqdm, packaging | PyPI | transitive via pandapower 3.5.6 | not available from the seam | various | SUS on all of them | Seam artefact: it returned `unknown-downloads` even for `packaging`, `tqdm` and `networkx`, so its downloads signal was unavailable this session. `too-new` on pandera, pydantic and cachebox is only their latest release date. Arrive as pandapower's declared requirements; review the resolved list at the same checkpoint |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** pandapower and its transitive set (all `unknown-downloads`; see above). One checkpoint covers the single new top-level package.

*The `postinstall` check does not apply: pandapower is a pure-Python wheel with no install script.*

## Architecture Patterns

### System Architecture Diagram

```
 OWNER MACHINE (Mac, Python 3.12)                       LICENSED LAPTOP (Windows, Python 3.14, PSS/E 36.4)
 ---------------------------------                       ------------------------------------------------
 [0] GUARD FIRST (blocks everything)
     .gitignore /data/private/
     leak scan: path | shape | exact needles
                |
                | pass on clean tree; flags planted id
                v
 [1] build + test on SYNTHETIC data  <----- generated at test time from case39(), buses offset +90000
     parser / builder / parity / scale+solve / compare
                |                                          teammate: git pull ; one command
                |                                                    |
                |                                          [S1] load psspy via psse_run_hourly.load_psspy(cfg)
                |                                          [S2] case as loaded -> RAW export (candidate calls) ----+
                |                                          [S3] settings: prmdat/prmint candidates + fingerprints  |
                |                                          [S4] scaling experiments (in memory) -> RAW snapshots   |
                |                                          [S5] per city (job's own functions):                    |
                |                                                reload -> scale -> RAW pre-solve snapshot         |
                |                                                prepare_city_base (rate static, solve, save temp) |
                |                                                RAW solved snapshot + bus/flow reads              |
                |                                                each outage from select_outages: reload saved     |
                |                                                  base, trip, solve, read V + flows, or record     |
                |                                                  non-converged / islanded                        |
                |                                                margin: city_margin -> limit point -> re-solve,   |
                |                                                  dump V (last good and first bad)                |
                |                                          [S6] manifest (sha256, case_sha256, mapping_sha256)     |
                |                                          [S7] zip on Desktop; delete work folder + mapping copy; |
                |                                               print MASKED summary  <----------------------------+
                |                                                    |
                |<====== private channel (zip) ======================+   summary pasted back (counts, statuses only)
                v
 [2] safe unzip -> data/private/pandapower/<session>/ ; verify manifest hashes ; mapping_sha256 must match
 [3] RAW parser (fail closed; iterate locally on the real file)
 [4] builder -> pandapower net (bus index = PSS/E number, name = "from-to-ckt")
 [5] parity report: export vs net (counts, classification, ratings, limits, setpoints)  -> must show zero
        + informational: export vs case39()  -> D-06 evidence
 [6] settings (D-14) + three scaling details -> scale each city -> runpp -> compare with reference (NET-03)
        voltage 0.01 pu ; flow max(2%, 2 MVA) ; explained-differences registry (D-12)
 [7] verdict + D-06 evidence report (owner decision, one-way)
```

### Recommended Project Structure

```
backend/
├── psse_session/                # LAPTOP side. stdlib only, Python 3.7-compatible syntax, imports psse_job
│   ├── session.py               # sections S1-S7, section isolation, --only, --check
│   ├── surface.py               # SESSION_SURFACE: one table of the extra psspy calls with evidence and confidence
│   ├── summary.py               # masked summary: integers and enums only
│   └── bundle.py                # manifest, sha256, zip
├── psse_pandapower_session.py   # tiny entry script (like psse_run_hourly.py); the only importer of psspy
├── pandapower_job/              # MAC side. Python 3.12, pandapower, imports psse_job one way
│   ├── raw.py                   # tokenizer + section state machine, fail closed, per-revision field tables
│   ├── network.py               # builder
│   ├── parity.py                # NET-02 report
│   ├── scaling.py               # minimal scale_case (Phase 2 reuses)
│   ├── solve.py                 # runpp with settings copied from settings.json
│   ├── compare.py               # NET-03 comparator, tolerance rule, explained-differences registry
│   ├── private.py               # path guard: outputs only under data/private/, must be git-ignored
│   └── ingest.py                # safe unzip, manifest verification
├── private_leak_scan.py         # stdlib scanner used by the test and by a local pre-commit step
└── tests/
    ├── private_data_guard_test.py
    ├── psse_session_test.py     # uses a FakePsspy subclass defined in a helper (not collected)
    ├── pandapower_raw_test.py, pandapower_network_test.py, pandapower_parity_test.py,
    └── pandapower_compare_test.py
docs/data-science/ops/psse_pandapower_session.ps1   # thin wrapper: resolve paths, call Python, mask, print
requirements-pandapower.txt
data/private/pandapower/         # git-ignored; created by the owner
```
Names are recommendations (Claude's discretion). Keeping the laptop package separate from `pandapower_job` matters: the laptop must never import pandapower, and the existing `psse_contract_test.py` gate only globs `backend/psse_job/*.py`, so a new laptop package needs its own copy of that import-and-syntax gate.

### Pattern 1: A session built from isolated sections

**What:** Each of S2 to S5 runs inside its own try/except that records `ok`, a short status and the ierr or exception class, never the text. A failure in one section does not stop the others. The manifest lists every section's status. The command accepts `--only <section>` so a failed section can be rerun alone, and `--check` (load PSS/E, read the case, validate the mapping, solve one city, export nothing).
**When to use:** Always. D-05 and D-02 make the session expensive to repeat, and Pattern 2 to 3 contain several calls the laptop has never run.
**Why not simply trust the manual:** The existing `SURFACE` table shows how often a documented call is wrong on the real engine: `scal_2` needed an undocumented close step found only on the laptop [VERIFIED: backend/psse_job/psse_api.py:104-109 comment, read this session].
**Reuse:** `psse_run_hourly.load_psspy(cfg)` after `launcher.add_search_dirs(cfg)`; `launcher.read_config(path)` with no mode (it then requires no secret keys); never import `psycopg` or open a socket.
**Output rules:** the work folder and the zip are the only things written; point PSS/E's own console output file into the work folder (`launcher.start_psspy(psspy, max_buses, log_path)` takes the path); delete the work folder after the zip is verified; delete the mapping copy and say so.

### Pattern 2: Settings and the three scaling details by measurement

**What:** Do not rely on one documented getter.

| Quantity | Primary evidence | Secondary evidence |
|----------|------------------|--------------------|
| Reactive-limit handling | Behavioural fingerprint: solve the scaled copy with `fnsl()` (what the job does), then with explicit 8-element option lists that apply var limits immediately and that ignore them (positional list; forum form `psspy.fnsl([1,0,0,1,1,0,99,0])`), and compare bus voltages; read each machine's Q against its Q limits in the RAW after the default solve | Candidate `psspy.prmint('PFCODE')` and `psspy.prmdat(<name>)` reads |
| Tap, switched-shunt, area-interchange adjustment | Counts from the RAW: transformers with `COD1` not 0, switched shunts, area records. If all are zero the setting cannot affect the solution | `fnsl` option fingerprint |
| Mismatch tolerance, iteration limit | RAW system-wide data record if the revision has one (revision 35 and later, ASSUMED), else candidate `prmdat`/`prmint` names tried one by one | The solve's `iterat()` and `sysmsm()` (already in `PsseApi.solve`) |
| Swing machine in the generation total | Compare `read_totals().gen_mw` with the sum of machine P in the RAW taken just before, with and without machines at swing-type buses | Machine P ratios before and after scaling |
| Machines clamped at limits | Scale to a target chosen so at least one machine would pass its P maximum; compare P after with Pmax in the RAW snapshot | `scal_2` ierr |
| Increment form scales Q with P | Sink-bus load P and Q in RAW snapshots before and after `define_subsystem` plus `scale_load`; compare the Q ratio with the P ratio | — |

The scaling experiments only call `PsseApi` methods that already exist (`read_totals`, `scale_case`, `define_subsystem`, `scale_load`, `load_case`) plus RAW exports, then reload the case from disk. The analysis is done offline on the Mac from the RAW deltas, so the laptop script records only what it did. The masked summary may state each detail as `yes`, `no` or `inconclusive` (behaviour, not a value).

Settings-to-pandapower mapping (D-14, copy what was read):

| PSS/E setting | pandapower treatment |
|---------------|----------------------|
| Var limits applied | `enforce_q_lims` True or False, copied |
| Mismatch tolerance (MVA) | `tolerance_mva` |
| Iteration limit | `max_iteration` |
| Tap adjustment, switched-shunt adjustment, area interchange | No pandapower equivalent used; the builder fails closed if the export contains a controlling transformer (`COD1` not 0), a switched shunt or more than one area with interchange control |
| Flat start, non-divergent solution | Recorded; not copied |

pandapower's `enforce_q_lims=True` for `gen` elements loops until no new violations (`while True` in `_run_ac_pf_with_qlims_enforced`), converts violators to PQ at the limit, never converts back, and excludes the reference machines (`setdiff1d(..., ref_gens)`), so the `ext_grid` Q is never limited [VERIFIED: pandapower 3.5.6 `pf/run_newton_raphson_pf.py:180-250`, read this session]. Whether PSS/E also never switches back is not known; the stressed margin limit point (D-10) is where a difference would show.

### Pattern 3: The reference is the job's own study

**What:** The session calls the job's public functions instead of re-implementing them. Run this session against the repo's `FakePsspy` with the placeholder mapping, this sequence works and reproduces the job's own outage list and margin details:
- `selection = ratings.select_ratings(lambda: [], now)` gives the static rating for all four cities (reason `missing`); the session has no database, so static is the only possible rating (D-02).
- `index = study.index_case(psspy, case_path, mapping)`, then per city `base = study.prepare_city_base(index, mapping, selection, city, budget, temp_dir)`.
- Outages: `contingency.select_outages(base)` (sorted, in the case's orientation). For each: `api.load_case(base.saved_path)`, `api.set_status(outage, False)`, `api.solve(settings.solve_options)`, then `bus_table()` and `branch_loading(settings.rate_sets[0], settings.thermal_basis)` if converged; otherwise record `ierr`, `solved_code`, `meaning` as non-converged.
- Margin: `margin.city_margin(base, city)`; `row["details"]` carries `increment_mw` (last good point), `first_bad_mw`, `sink_buses`, `bounded_by`. To get the limit-point voltages, reload the saved base, `define_subsystem(margin.SINK_SID, sink_buses)`, `scale_load(SINK_SID, increment_mw)`, solve, read buses; repeat once at `first_bad_mw` when it is not None.
- Pre-solve snapshot: a separate load, `study.scale_city_case(api, city, scaling)`, RAW export, before the `prepare_city_base` pass (which does its own load, scale, rate, solve).

`prepare_city_base` saves the solved copy to a private temporary folder and the job removes it (`study._remove_dir`); "in-memory only" in D-02 means the case file is never saved over, as the job already does. The session should clean that folder the same way.

### Pattern 4: Guards before data

Three layers; the first two run in CI, the third only where private data exists.
1. **Path layer.** `git check-ignore -q data/private/pandapower/x.json` must succeed (same shape as the existing `test_env_file_is_ignored_and_untracked`); no tracked path starts with `data/private/`; also ignore `psse_pp_session*` (zip and folder) and keep `*.raw` and `*.sav`.
2. **Shape layer.** No tracked or untracked-not-ignored file contains RAW structure (a line matching `^\s*0\s*/\s*END OF [A-Z0-9 -]+ DATA`, or `BEGIN [A-Z0-9 -]+ DATA`, or a case header of the form `^\s*\d+\s*,\s*[\d.]+\s*,\s*3[3-6]\s*,`) or the session manifest marker (a distinctive key such as `"psse_pp_session_manifest"`). Because fixtures are generated at test time, this layer has no exceptions.
3. **Exact-needle layer (owner-local, skipped if the folder is absent).** Derive needles from the private files: every `from-to-ckt` key and sink-bus tuple of the mapping, the scaling targets formatted the ways they would be typed, each file's sha256 (a pin committed under D-06 is then allow-listed explicitly), and every decimal literal with five or more fractional digits found in the export and reference. Tokenise each scanned line with a regex and test set membership (linear time). Report path and line number only, never the text.

Scan the **working tree** (`git ls-files` plus `git ls-files --others --exclude-standard`), because that is what the next `git add` would take; a scan of tracked files alone fires after the commit, which is too late for a public repository. Add a documented local pre-commit step that runs the same scanner on staged content. The success-criterion test plants a placeholder identifier in a temporary file (using values that are not the committed `9xxxx` example, so the planted value is not allow-listed) and asserts the scanner flags it and that the clean tree passes.

Related leak vectors to close in the same task: `graphify-out/`, `.planning/graphs/` and `.obsidian/` are untracked now; confirm the graph builder and Obsidian do not index `data/private/` (ASSUMED that they honour `.gitignore`; add an explicit ignore for each tool if not). Pytest assertion messages print values, so tests that run on private data must raise counts-only messages.

### Pattern 5: A fail-closed RAW parser

**What:** Tokenise by commas outside single quotes, stop a record at an unquoted `/`, skip header comment lines, and walk the section list in the file order. Accept only a declared revision with a field table; for each section require the record length to fall within `(required, max)` because PSS/E may truncate trailing default fields, and apply the documented defaults to the missing tail. Raise on: unknown revision; a section marker not in the table; a non-empty section the builder does not support; too few or too many fields; a three-winding transformer record (`K` not 0); duplicate bus numbers or duplicate `from-to-ckt` keys; any value the builder cannot represent (list below).

The v33 section order is: case identification, bus, load, fixed shunt, generator, branch, transformer, area interchange, two-terminal DC, voltage source converter, impedance correction, multi-terminal DC, multi-section line, zone, inter-area transfer, owner, FACTS control device, switched shunt, GNE device, induction machine; a first field of `0` ends a section and `Q` ends the file; a two-winding transformer is four records [CITED: lanl-ansi/PowerModels.jl `src/io/pti.jl`, fetched this session]. v33 field lists are in that source; they are the starting table for the parser (bus 13, load 14, fixed shunt 5, generator 28, branch 24, transformer records 21, 3, 17 and 2 fields).

Builder fail-closed list for the 39-bus study: load with non-zero `IP`, `IQ`, `YP` or `YQ`; branch with non-zero `GI`, `BI`, `GJ` or `BJ`; generator with `IREG` not 0 and not its own bus; more than one machine at the swing bus; a type-2 bus with no in-service machine; transformer with `CW`, `CZ` or `CM` not 1, non-zero `MAG1` or `MAG2`, `COD1` not 0, `ANG1` not 0, or `WINDV2` not 1.0; any non-empty switched-shunt, DC, FACTS, GNE, induction-machine, multi-section or impedance-correction section. Each of these is a one-line relaxation once the real file shows it is needed, with an NET-03 check as the safety net. PowSyBl's import documents the same kinds of loss for constant-current and constant-admittance load parts, impedance correction tables and reactive transformer control [CITED: powsybl.readthedocs.io PSS/E import page].

### Pattern 6: A parity report that is not circular

Compare the built network with the parsed export through an **inverse read-back** written independently of the builder: from `net.line` convert ohms back to per-unit on the system base and compare with `R`, `X`, `B`; from `net.trafo` recover ratio, `R`, `X`; compare `max_i_ka` with the rating; compare bus voltage limits, machine setpoints and limits, load P and Q, shunts, in-service flags, element counts, line-versus-transformer classification and name sets. Report each difference as category, element key and size; a CI or summary mode prints category counts only. Add mutation tests: change one reactance, one rating, one setpoint, drop one line, reclassify one branch, and assert exactly that category reports exactly that element.

State plainly in the report header what it proves: transcription fidelity. It cannot detect a shared misunderstanding of a PSS/E convention; NET-03 does.

Informational section for D-06: compare the built data with `pandapower.networks.case39()` element by element, by bus number first. Expect the known classification difference (35 lines and 11 transformers in pandapower against 34 and 12 on the laptop [CITED: research/STACK.md, 03-07 laptop record]) and report how many elements differ beyond 1e-6 relative. This is evidence only; it neither gates nor decides the licence question.

### Pattern 7: Minimal scaling and solve, shaped for Phase 2

`backend/pandapower_job/scaling.py` and `solve.py` hold only what NET-03 needs; Phase 2 renames them into the engine.
- Scale loads by one factor on P and Q (constant power factor, as `scal_2` is believed to do; the Q-with-P measurement checks the increment form).
- Scale generation by one factor on machine P, with the swing machine's stored P included in or excluded from the total according to the measured detail, and clamping to `[min_p_mw, max_p_mw]` only if measured.
- Provide a second entry that **injects PSS/E's own post-scaling machine P and load P and Q** taken from the pre-solve RAW snapshot. Run NET-03 both ways. If the injected-snapshot run passes and the algorithm run fails, the scaling rule is wrong, not the network; if both fail, the network or solver settings are wrong.
- Settings come from `settings.json` and are stored with the result.
- Comparison rule (D-13): voltage passes if `abs(got - ref) <= 0.01`; a flow passes if `abs(got - ref) <= max(0.02 * abs(ref), 2.0)` MVA. Compare, per branch, the signed from-end P, the from-end Q if available, and the larger-end apparent flow (`MAXMVA`, the quantity the job uses). Angles, total losses and per-machine Q are reported as diagnostics, not gates.
- Explained differences (D-12): a private registry file lists element, quantity, cause text and measured size; an out-of-tolerance value not in the registry is a failure; a registry entry never widens the tolerance for any other element. The comparator receives the net read-only and a test asserts the net's tables are unchanged by the comparison (no tuning).

### Anti-Patterns to Avoid

- **Building from `case39()` or `from_mpc` for production:** wrong branch classification, bus numbers lost; fixture only.
- **Indexing `net.bus` by position or by `PSS/E number - 1`:** use `index=<PSS/E number>`; test with the `+90000` offset so index never equals position.
- **Reading `res_line` by position:** join on the `from-to-ckt` name; assert the name set is unique (pandapower accepts duplicate line names silently, verified; it raises on a duplicate bus index).
- **Writing any output outside `data/private/`:** `to_json`, pickles and report files go through `private.py`, which resolves the path and checks `git check-ignore`.
- **A pandapower-backed fake `psspy`:** rejected in the requirements; the session tests only need call shapes and canned values.
- **Calling `PsseApi.solve(options=[...])` for the fingerprint solves:** the keyword form `options=` has never run on the real engine (the job always calls `fnsl()`); use the positional list the forum shows, or try both and record which worked.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Newton-Raphson load flow | Own solver | `pandapower.runpp` | Verified to reproduce the reference to 1e-15 on the same data |
| Mapping parse and hash | New JSON schema reader | `psse_job.mapping.parse_mapping` / `load_mapping` | Same duplicate-key, range and hash rules; `Scaling` namedtuple already there |
| Outage list, per-city scaling, ratings, margin | Re-implemented loops | `contingency.select_outages`, `study.scale_city_case`, `study.apply_ratings`, `margin.city_margin` | The reference must be the job's own copy and list |
| Masked output | Free-form prints | Integers and enums formatted with `%d`/`%s`; `redaction.redact` as a backstop | A summary assembled only from counts cannot carry an identifier; the existing probe report is built this way |
| Hashes and zip | Custom checksums or archive code | `hashlib.sha256`, `zipfile` | Standard; also gives safe path handling on extract |
| Secret and identifier scanning | New scanner from nothing | The `secret_scan_test.py` helpers and its report-path-only rule | Same conventions, same never-print-the-match guarantee |
| Unit conversion for ratings | New formulas | `psse_job.units` (`circuit_mva`, `mva_to_circuit_amps`) | Phase 2 needs them identical |
| Tolerance logic | Per-test inline arithmetic | One `compare.within()` | D-13 stated once |

**Key insight:** The only conversion code that is genuinely new is the RAW tokenizer and the per-unit-to-pandapower builder, and both are small (the whole round trip prototype was about 130 lines). Everything that could silently drift between the PSS/E study and the pandapower study should be imported, not copied.

## Runtime State Inventory

Not a rename or migration phase. Section omitted.

## Common Pitfalls

### Pitfall 1: The session is expensive to repeat and half of it is untested on the laptop
**What goes wrong:** One wrong item name or call signature aborts the script and the teammate must run again.
**Why it happens:** Nothing beyond `case`, `fnsl`, the `abrn*`/`abus*` bulk reads, `brndat`, `branch_chng_3`, `bsys`, `scal_2`, `save`, `solved`, `iterat`, `sysmsm` and `psseversion` has run on 36.4 (the probe passed 27 rows on an unconverted case) [VERIFIED: 03-07 laptop record, "Step 3 ... 27 PASS 0 FAIL 0 SKIP"].
**How to avoid:** Pattern 1 section isolation, `--only`, `--check`, an AST-enforced allow-list so the script can only call functions it declares in `SESSION_SURFACE`, and a fake-psspy test in which each unverified call is made to fail in turn and the remaining sections still produce files.
**Warning signs:** A summary line reading `failed` for a section; a manifest with fewer files than sections.

### Pitfall 2: The RAW export call, revision and options are unverified
**What goes wrong:** The call returns an error ("incorrect file type OPTIN" appears in a forum report), writes an empty file, or writes a revision the parser does not know.
**Why it happens:** Only forum evidence exists: `psspy.rawd_2(0,1,[1,1,1,0,0,0,0], 0, 'raw_file_out.raw')` in one answer and `psspy.rawd_2(0,1, out= 0,ofile=oname )` in a question that failed; a reply reports that the "output bus names" option misbehaves in revisions 35 and 36; `writerawversion` and `readrawversion` exist (the latter used as `psspy.readrawversion(1,r"""36""",...)`) [CITED: psspy.org questions 3777 and 10100 and a search summary of questions 12001 and 10593; LOW, community, argument meanings not documented].
**How to avoid:** Try, in order, a `writerawversion` form requesting revision 33, then `rawd_2` with the forum option list and with no name option, and record each ierr and the resulting header revision and byte count; keep every file that was produced. Do not request bus names. Verify `inspect.signature` of each candidate first (the existing probe shows `inspect.signature` works on the real module). Capture the candidates' `__doc__` text into the private zip so the next iteration is informed (ASSUMED that the real functions carry docstrings).
**Warning signs:** `raw_export: failed` in the summary; a zero-byte file.

### Pitfall 3: RAW records are not fixed width and the layout varies by revision
**What goes wrong:** A strict field count rejects a legitimate file, or the builder indexes past a truncated record.
**Why it happens:** PSS/E fills omitted trailing fields with defaults; revision 34 and later add fields and sections (v33 load has 14 fields, later revisions more).
**How to avoid:** Per-revision `(required, max)` ranges, defaults applied before the builder sees a record, and fail closed on more than `max`. The prototype showed a strict equality check rejecting my own synthetic file (18 fields written, 24 required) before the range rule was added.
**Warning signs:** `IndexError` from builder code instead of a clear refusal.

### Pitfall 4: Transformer conventions
**What goes wrong:** Impedance or tap placed on the wrong side shifts voltages by a few thousandths of a pu, enough to blame the solver.
**Why it happens:** PSS/E puts the configured ratio on winding 1 with the series impedance on the winding 2 side; PowSyBl documents the same arrangement ("fixing an ideal end-2 ratio and moving the configured ratio to end 1") [CITED: powsybl.readthedocs.io PSS/E import]. MATPOWER uses the same convention (tap on the from side, series Z on the to side).
**How to avoid:** Use `hv_bus = I`, `lv_bus = J` regardless of kV, `vn_hv_kv = WINDV1 * kV_I`, `vn_lv_kv = kV_J`, `sn_mva` equal to the system base so `vk_percent = 100*|Z|` and `vkr_percent = 100*R`, no magnetizing branch, and fail closed on `WINDV2` not 1.0. Verified this session: reproduces `case39()` to 1.3e-15 pu, and matches an independent MATPOWER-convention Ybus solve to 2.7e-11 pu for taps of 1.00, 1.05, 1.04 and 0.97 with 345/345, 16.5/345 and 138/345 kV. That equivalence is with MATPOWER's convention; that PSS/E's is identical is `[ASSUMED]` until NET-03 passes.
**Warning signs:** Differences concentrated at transformer terminals.

### Pitfall 5: Parity passes while the network is wrong
**What goes wrong:** Parity proves the builder read the file consistently, not that the file was understood.
**How to avoid:** Pattern 6 and Pattern 7: independent read-back, pre-solve injection comparison, and treat NET-03 against PSS/E's numbers as the real test. The session's reference must come from the same moment as the RAW (same loaded case) so the two cannot disagree for unrelated reasons.

### Pitfall 6: Loading percentages depend on the rating applied
**What goes wrong:** Reference `MAXPCTRATEA` for the mapped circuits reflects whatever rating was written, so a reference taken with live ratings cannot be reproduced.
**How to avoid:** The session applies the static fallback rating through `study.apply_ratings` (the only option without a database), and also exports the raw branch ratings from the RAW. Loading is a diagnostic in Phase 1; the gate is voltage and flow. A low-side static fallback is safe (project memory), so there is no safety issue in using it.

### Pitfall 7: Outage references must start from the saved solved base
**What goes wrong:** Solving an outage from the original case instead of the saved solved copy changes the start point and, near a limit, the solution.
**How to avoid:** Reproduce the job: reload `base.saved_path` before every outage (never un-trip), as `contingency.screen` does [VERIFIED: backend/psse_job/contingency.py:88-94]. Record islanded outages (`fnsl` ierr 3, "buses in island without swing bus" per `FNSL_ERRORS`) as non-converged; pandapower returns "converged" with NaN voltages for the same outage, so Phase 2 must map NaN to non-converged [CITED: research/PITFALLS.md Pitfall 7, STACK.md]; Phase 1 only has to keep the PSS/E side honest.

### Pitfall 8: The private files leak through side channels
**What goes wrong:** Real identifiers reach git history through generated artefacts rather than through the files themselves.
**Why it happens:** `.planning/` is tracked; `graphify-out/`, `.planning/graphs/` and `.obsidian/` are untracked and could be added by a broad `git add`; pytest and pandapower print element indices; `net.to_json` and pickles are one line of code.
**How to avoid:** Pattern 4, the `private.py` path guard, counts-only messages in any test that touches private data, and a rule that the summary pasted back contains counts, statuses and versions only (D-02).

### Pitfall 9: Safe handling of the incoming zip
**What goes wrong:** A tampered or oversized archive writes outside the private folder or fills the disk.
**How to avoid:** Extract member by member with a resolved-path check, a member allow-list from the manifest, a total-size cap, and sha256 verification against the manifest before any parser runs; refuse any file the manifest does not list. Check that the manifest's `mapping_sha256` equals the sha256 of the mapping used for NET-03 and that `case_sha256` is recorded; otherwise the comparison may use the wrong scaling targets without any error.

## Code Examples

All three snippets were run in a scratch Python 3.12.13 venv with pandapower 3.5.6 this session unless marked as a skeleton.

### Builder: PSS/E per-unit data to a pandapower network (verified against `case39()`)
```python
# Source: prototype run this session; reproduces pandapower.networks.case39() to 1.3e-15 pu.
import math
import pandapower as pp

def build(buses, lines, trafos, loads, gens, ext, sb, f_hz):
    net = pp.create_empty_network(sn_mva=sb, f_hz=f_hz)
    for n, kv in sorted(buses.items()):
        pp.create_bus(net, vn_kv=kv, index=n, name=str(n))          # PSS/E number is the index
    for ln in lines:                                                 # R, X, B in pu on the system base
        kv = buses[ln["i"]]; z = kv * kv / sb
        pp.create_line_from_parameters(
            net, ln["i"], ln["j"], length_km=1.0,
            r_ohm_per_km=ln["R"] * z, x_ohm_per_km=ln["X"] * z,
            c_nf_per_km=ln["B"] / (z * 2 * math.pi * f_hz) * 1e9,
            max_i_ka=ln["rate"] / (math.sqrt(3) * kv),               # rate in MVA, RATEA
            name="%d-%d-%s" % (ln["i"], ln["j"], ln["ckt"]))
    for tr in trafos:                                                # CW=CZ=CM=1, WINDV2=1.0, no magnetizing
        pp.create_transformer_from_parameters(
            net, hv_bus=tr["i"], lv_bus=tr["j"], sn_mva=sb,
            vn_hv_kv=tr["windv1"] * buses[tr["i"]], vn_lv_kv=buses[tr["j"]],
            vk_percent=100 * math.hypot(tr["R"], tr["X"]), vkr_percent=100 * tr["R"],
            pfe_kw=0.0, i0_percent=0.0, shift_degree=0.0,
            name="%d-%d-%s" % (tr["i"], tr["j"], tr["ckt"]))
    for bus, p, q in loads:
        pp.create_load(net, bus, p_mw=p, q_mvar=q)
    for bus, p, vm, qmax, qmin in gens:                              # the swing machine becomes the ext_grid
        pp.create_gen(net, bus, p_mw=p, vm_pu=vm, max_q_mvar=qmax, min_q_mvar=qmin)
    pp.create_ext_grid(net, ext[0], vm_pu=ext[1], va_degree=ext[2])
    return net
```
Fixed shunt rule, verified: PSS/E `BL` positive is capacitive, so `pp.create_shunt(net, bus, q_mvar=-BL, p_mw=GL, vn_kv=kv)`; a +100 Mvar capacitor raised a test bus from 0.90015 to 0.99105 pu and `res_shunt.q_mvar` came out negative (injecting).

### RAW tokenizer and section walk, failing closed (verified on a synthetic v33 file made from `case39()` with buses offset by 90000)
```python
# Source: prototype run this session. Synthetic file refused for revision 34, a three-winding record and a
# non-empty switched-shunt section; accepted when well formed; max |dV| vs case39() = 1.6e-15.
def split_record(line):
    toks, cur, quoted = [], [], False
    for ch in line:
        if ch == "'":
            quoted = not quoted; cur.append(ch); continue
        if ch == "/" and not quoted: break                 # trailing comment
        if ch == "," and not quoted:
            toks.append("".join(cur).strip()); cur = []; continue
        cur.append(ch)
    toks.append("".join(cur).strip())
    return [t[1:-1].strip() if len(t) >= 2 and t[0] == t[-1] == "'" else t for t in toks]

# per section: loop until split_record(line)[0] == "0"; transformer = 4 lines, refuse K != 0;
# file ends at "Q"; (required, max) field counts per section, e.g. BUS (11, 13), BRANCH (6, 24).
```
Size check, measured on the synthetic equivalent: RAW text 13,757 bytes, compact JSON of the parsed records 15,053 bytes (1,993 gzipped), so a converted copy fits the 48 KB secret limit of D-06 with room to spare [VERIFIED: run this session; real file size unknown].

### Session call sequence on the job's own functions (verified against `FakePsspy`)
```python
# Source: run this session against backend/tests/psse_fake_psspy.py with the placeholder mapping.
selection = ratings.select_ratings(lambda: [], now)                 # static ratings, reason "missing"
index = study.index_case(psspy, case_path, mapping)
for city in constants.CITIES:
    base = study.prepare_city_base(index, mapping, selection, city, budget, temp_dir)
    outages = contingency.select_outages(base)                       # the job's own list
    for outage in outages:
        base.api.load_case(base.saved_path)
        base.api.set_status(outage, False)
        result = base.api.solve(mapping.settings.solve_options)
        # converged -> base.api.bus_table(), base.api.branch_loading(rate_set, basis); else record ierr/meaning
    m = margin.city_margin(base, city)   # m.row["details"]["increment_mw"], ["first_bad_mw"], ["sink_buses"]
# Output of the run: 10 outages per placeholder city, all converged; margin bounded_by voltage_criterion
# (three cities) and dlr_rating (one); distinct psspy calls used were all in SURFACE.
```
Skeleton (not run): per-city RAW snapshot before the `prepare_city_base` pass is `api.load_case(...)`, `study.scale_city_case(api, city, scaling)`, then the RAW export call chosen in Pitfall 2.

### Comparator (D-13)
```python
def within_voltage(ref_pu, got_pu):  return abs(got_pu - ref_pu) <= 0.01
def within_flow(ref_mva, got_mva):   return abs(got_mva - ref_mva) <= max(0.02 * abs(ref_mva), 2.0)
```

### Repo values these examples depend on (read this session)
| Value | Quote | Source |
|-------|-------|--------|
| Whole-case scaling call layout | `SCALE_LAYOUT = ScaleLayout(sid=0, all_flag=1, apiopt_scale=0, apiopt_totals=1, apiopt_close=2, status=(None, 1, 0, 1, 0), scalval_load=0, scalval_gen=1, scalval_slots=7, totals_load=1, totals_gen=2,` | backend/psse_job/psse_api.py:110-114 |
| fnsl option count and call form | `_FNSL_OPTION_COUNT = 8`; `ierr = self._call("fnsl", options=values)` | backend/psse_job/psse_api.py:173 and 345 |
| Sink subsystem id | `SINK_SID = 9` | backend/psse_job/margin.py:38 |
| Cities | `CITIES = ("AUSTIN", "CORPUS_CHRISTI", "MIDLAND", "EL_PASO")` | backend/psse_job/constants.py:13 |
| Scale guards | `SCALE_TOLERANCE = 1e-3`; `SCALE_FACTOR_BOUNDS = (0.05, 20.0)` | backend/psse_job/study.py:73 and 76 |
| Mapping schema | `SCHEMA_VERSION = 2`; `MAX_MAPPING_BYTES = 65536` | backend/psse_job/mapping.py:34-35 |
| Study defaults used | `solve_options=None`, `max_mismatch_mva=1.0`, `collapse_voltage_pu=0.5`, `rate_sets=("RATEA",)`, `thermal_basis="current"` | backend/psse_job/settings.py:84-118 |
| Existing ignore rules | `/psse_local/`, `*.sav`, `*.raw` | .gitignore (last lines) |
| Test configuration | `pythonpath = backend`, `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py` | pytest.ini |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `pandapower.pypower.runpf` as an independent solver | Removed from 3.5.6 (`ModuleNotFoundError`); write a short Ybus check in test code | pandapower 3.x | An independent check of the transformer maths needs its own few lines of numpy/scipy |
| `case39()` as "the" 39-bus case | MATPOWER-modified copy, 35 lines and 11 transformers | — | Fixture and D-06 comparison only |
| `fnsl` with keyword `optionsN` (1-based) per a 2012 blog | A positional 8-list in a forum answer; the project's `options=` keyword is unproven | unknown for 36.4 | Use positional for fingerprints; leave `fnsl()` for the study |
| RAW revisions 32/33 only in open-source tools | PSS/E 35 added RAWX (JSON); PowSyBl reads RAW 33 and 35 and RAWX 35 | PSS/E 35 | If 36.4 offers RAWX it would be easier to parse; not relied on here |

**Deprecated/outdated:** `scal_2` is marked obsolete in the PSS/E 36.4 documentation (implemented by `scal_4`) but works and is what the job uses [CITED: docs/data-science/decisions/psse_laptop_runbook.md step 4 text and psse_study_definitions.md assumption A19].

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | PSS/E 36.4 can write a revision 33 RAW through `writerawversion` or `rawd_2`; the forum argument lists are right | Pitfall 2, Pattern 1 | Parser must handle revision 36 (new field tables); session may need a second run |
| A2 | The v33 record layout in PowerModels `pti.jl` matches what PSS/E writes, and trailing defaults may be omitted | Pattern 5 | Parser refusals on the first real file; local iteration needed |
| A3 | A RAW written from the in-memory case carries the latest solved bus VM and VA and machine PG and QG | Summary, Pattern 2 | Solved snapshots lose Q and angles; fall back to bulk readers for them |
| A4 | PSS/E's two-winding convention (ratio at winding 1, impedance on winding 2 side) equals MATPOWER's for CW=CZ=CM=1 | Pitfall 4 | Small voltage offsets at transformers; settled by NET-03 and recorded as an explained difference if real |
| A5 | `psspy.prmdat` and `psspy.prmint` exist on 36.4 and accept solution-parameter names; no getter is documented for tap, shunt or area program settings | Pattern 2 | Settings fall back to fingerprints only |
| A6 | The meanings of the eight `fnsl` options (tap, area interchange, phase shift, DC tap, switched shunt, flat start, var limits, non-divergent) as given in forum answers | Pattern 2 | Fingerprint solves test the wrong switch |
| A7 | `fnsl()` with no argument uses the program settings stored with the case (project assumption A4) | Pattern 2 | The default solve may not match any explicit option list |
| A8 | Behavioural fingerprints (voltages with and without var limits; machine Q against limits) separate on-versus-off in the stressed margin point if not in the base | Pattern 2 | Settings inconclusive; D-14 needs a human decision |
| A9 | `scal_2` scaling details (swing in total, clamping, Q with P) are measurable from RAW deltas | Pattern 2 | PSE-02 incomplete; Phase 2 scaling rule unfixed |
| A10 | The free Xplore edition allows RAW export through the API | Pitfall 2 | Export impossible on that machine; would need the full edition |
| A11 | The 39-bus case has none of: switched shunts, controlling transformers, line shunts, magnetizing branches, remote regulation, `WINDV2` other than 1 | Pattern 5 fail-closed list | Builder refuses the real file; relaxations are small but must be re-verified |
| A12 | The PSS/E-bundled 39-bus example's licence terms are unknown; publication is not assumed | D-06 | Owner decision stands on unknown licence |
| A13 | `graphify` and Obsidian honour `.gitignore` and will not index `data/private/` | Pattern 4 | Private values could appear in untracked tool output that is later committed |
| A14 | The swing machine's Q limits are not enforced by PSS/E at a swing bus, matching pandapower's `ext_grid` | Pattern 2 | Differences at the swing bus under stress |
| A15 | PSS/E function objects carry docstrings worth capturing | Pitfall 2 | Capture is empty; harmless |
| A16 | `pwsh` is not needed: the wrapper holds no logic beyond path resolution and masking | Structure | An untested `.ps1` fails on the laptop; keep it to a few lines |

## Open Questions

1. **Which RAW call and revision work on 36.4?**
   - What we know: forum calls exist; v33 is the best documented layout; PowSyBl handles v33 and v35.
   - What's unclear: the real signature, option meanings and default revision.
   - Recommendation: candidates in order, all results recorded; plan an explicit "ingest and iterate the parser on the first real file" task so this is not a surprise.
2. **Does the real 39-bus case trip any fail-closed rule?** (Assumption A11.) Recommendation: the masked summary reports counts of switched shunts, controlling transformers, areas and three-winding transformers so the owner knows before the file arrives.
3. **Who prepares the mapping copy on the Mac for NET-03, and from where?** The owner holds it; place it under `data/private/pandapower/` and compare its sha256 with the manifest's `mapping_sha256`. The session must record that hash from the same bytes it parsed (`mapping.load_mapping` already returns `sha256`).
4. **Is a `--check` preflight acceptable under D-05 ("single-purpose")?** It is not a dry run of the existing job; it runs the new script's own load and one solve and exports nothing. Recommendation: include it; the owner confirms.
5. **Does the owner want the explained-differences registry committed?** Recommendation: keep it private (it names elements); only counts appear in committed notes.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 (repo `.venv`) | Mac side | yes | 3.12.13 | — |
| pandapower 3.5.6 in `.venv` | NET-01 to NET-03 | no (not installed in `.venv`) | scratch venv has 3.5.6 | `pip install -r requirements-pandapower.txt` then `pip check` |
| pytest | all tests | yes | 9.0.3 | — |
| git | guard, branch | yes | 2.39.5 | — |
| `git check-ignore` behaviour for `data/private/` | PSE-04 | rule absent | `git check-ignore -v data/private/pandapower/x.json` exit status 1 | add `/data/private/` first |
| PowerShell (`pwsh`) on the Mac | testing the `.ps1` wrapper | no | — | keep logic in Python; review the `.ps1` by eye; test its masking regexes through a Python twin |
| Licensed PSS/E laptop and teammate | PSE-01 to PSE-03 | not accessible from here | PSS/E 36.4 Xplore, Python 3.14.0 (per 03-07 record) | none; this is the one external dependency |
| Network, database | — | not used by the session (D-02) | — | — |

**Missing dependencies with no fallback:** the laptop session itself (a person and a licence).
**Missing dependencies with fallback:** pandapower in `.venv` (install); `pwsh` (Python twin of the masking).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 (3,773 tests currently collected) |
| Config file | `pytest.ini` (`pythonpath = backend`) |
| Quick run command | `.venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/private_data_guard_test.py backend/tests/psse_session_test.py backend/tests/pandapower_raw_test.py backend/tests/pandapower_network_test.py backend/tests/pandapower_parity_test.py backend/tests/pandapower_compare_test.py` |
| Full suite command | `.venv/bin/python -m pytest -q -p no:cacheprovider` (runtime not measured; the relevant existing subset of 276 tests ran in 8.7 s and passed, 1 skipped) |

CI does not run the full suite (workflows run named test files), so these tests are run locally by the owner before any push. Tests that need pandapower use `pytest.importorskip("pandapower")` so a bare environment still collects; the Wave 0 install makes them run.

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PSE-04 | `data/private/` is ignored; no tracked path under it; shape scan clean on the tree; planted placeholder identifier flagged; clean tree passes; scanner never prints the match | unit | `pytest -q backend/tests/private_data_guard_test.py` | Wave 0 |
| PSE-04 | Fixtures are generated into `tmp_path`; no tracked file has RAW structure or the manifest marker | unit | same file | Wave 0 |
| PSE-01 | Session runs end to end against a `FakePsspy` subclass: zip members equal the manifest, hashes match, work folder and mapping copy deleted | integration | `pytest -q backend/tests/psse_session_test.py` | Wave 0 |
| PSE-01 | Summary contains only whitelisted line shapes and none of the planted `9xxxx` bus numbers, targets or paths | unit | same file | Wave 0 |
| PSE-01 | Read-only: only `SESSION_SURFACE` calls, never `save` onto the case path; AST gate: stdlib plus `psse_job` only, `psspy` imported only in the entry script, no `socket`, `urllib`, `psycopg` | unit | same file | Wave 0 |
| PSE-01 | Each unverified call forced to fail in turn: other sections still write files and the manifest records the failure | unit | same file | Wave 0 |
| PSE-02 | `settings.json` has each required key or an explicit unavailable marker with a reason; the three scaling details are `yes`, `no` or `inconclusive`; the offline analyser classifies synthetic RAW deltas correctly for swing included or excluded, clamped or not, Q scaled or not | unit | `pytest -q backend/tests/psse_session_test.py backend/tests/pandapower_compare_test.py` | Wave 0 |
| PSE-03 | Reference holds the base solve per city plus one record per outage equal to `select_outages`; a forced non-converged and an islanded outage are recorded, not dropped; margin limit-point records exist | integration | `pytest -q backend/tests/psse_session_test.py` | Wave 0 |
| NET-01 | Parser refuses: unknown revision, unknown section, non-empty unsupported section, too few or too many fields, three-winding record, duplicate bus, duplicate branch key; builder refuses each item of the fail-closed list | unit | `pytest -q backend/tests/pandapower_raw_test.py backend/tests/pandapower_network_test.py` | Wave 0 |
| NET-01 | Bus index equals the PSS/E number with the `+90000` offset (never equal to position); line and trafo names are `from-to-ckt`; round trip equals `case39()` to 1e-9 | unit | `pytest -q backend/tests/pandapower_network_test.py` | Wave 0 |
| NET-02 | Parity report shows zero differences on a clean build; mutation of one reactance, rating, setpoint, a dropped line and a reclassified branch each yields exactly that category and element | unit | `pytest -q backend/tests/pandapower_parity_test.py` | Wave 0 |
| NET-03 | Comparator passes the self-consistent synthetic reference; a voltage 0.011 pu off fails; a flow 2.5 percent and 3 MVA off fails; a 1.5 MVA error on a 0.5 MVA flow passes under the 2 MVA floor and 2.5 MVA fails; unexplained difference fails; the net's tables are unchanged by the comparison | unit | `pytest -q backend/tests/pandapower_compare_test.py` | Wave 0 |
| NET-03 | Injected-snapshot run and algorithm run both exist and a deliberately wrong scaling flag fails only the second | unit | same file | Wave 0 |
| Real data | Session on the licensed laptop; parser on the real file; parity zero; NET-03 on the real reference; D-06 evidence report | manual (owner-run checkpoint, masked pass or fail output) | `.venv/bin/python -m pandapower_job.<cli> ...` run by the owner | n/a, needs the session |

Why the synthetic reference is acceptable: a reference generated by pandapower from the same synthetic case is circular and proves plumbing, tolerance logic and failure detection only; the deliberate-mismatch tests are what show the comparator can fail. Physics is only validated by the real session.

### Sampling Rate
- **Per task commit:** the quick command above, limited to the files the task touched.
- **Per wave merge:** the quick command in full plus `backend/tests/secret_scan_test.py backend/tests/psse_contract_test.py backend/tests/psse_api_test.py backend/tests/psse_study_test.py` to prove the existing job is untouched.
- **Phase gate:** full suite green, then the owner-run real-data checkpoint, before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `.gitignore` gains `/data/private/` and the session artefact patterns; `backend/tests/private_data_guard_test.py` and `backend/private_leak_scan.py` (success criterion 1; must land before any file arrives)
- [ ] `requirements-pandapower.txt` and a `.venv` install with `pip check`
- [ ] `backend/tests/pandapower_fixture.py` (not collected): generates the synthetic RAW text and the synthetic reference into `tmp_path` from `case39()` with buses offset by 90000
- [ ] `backend/tests/psse_session_fake.py` (not collected): `FakePsspy` subclass adding the extra calls and a RAW writer; do not edit `psse_fake_psspy.py`
- [ ] Test files named above and an import-and-syntax gate for `backend/psse_session/`
- [ ] A checkpoint task for the pandapower pin (legitimacy seam returned SUS)

## Security Domain

`security_enforcement` is not set to false in `.planning/config.json` (the file holds only `workflow` and `graphify` keys), so this section applies.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No login in scope; the session has no database or network access |
| V3 Session Management | no | — |
| V4 Access Control | yes (files) | Private folder git-ignored; outputs only through `private.py`; owner-only backup |
| V5 Input Validation | yes | The zip, manifest and RAW file come from another machine: fail-closed parser, member allow-list, size caps, resolved-path check on extract, hash verification before parse |
| V6 Cryptography | yes | `hashlib.sha256` only; no custom hashing |
| V7 Error Handling and Logging | yes | Masked summary built from integers and enums; `redaction.redact` backstop; counts-only assertion messages on private-data tests |
| V8 Data Protection | yes | Reference answers never in a secret or CI (D-08); delete mapping copy and zip after use (D-04) |
| V12 Files and Resources | yes | Zip handling as above; refuse writes outside the output folder |
| V14 Configuration | yes | No secrets read or printed; the config reader returns text values and the session never prints them |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Private identifier or value committed to the public repository | Information disclosure | Three-layer guard on the working tree, local pre-commit step, ignore rules before data arrives |
| Identifier in the pasted summary or a test failure message | Information disclosure | Summary from integers and enums only; test that planted identifiers never appear; counts-only messages |
| Leak through generated artefacts (graph output, notes, `to_json`, pickles) | Information disclosure | Path guard in `private.py`; ignore patterns; explicit tool ignores (A13) |
| Zip slip or zip bomb from the incoming archive | Tampering, denial of service | Member allow-list from the manifest, resolved-path check, total-size cap |
| Comparison against the wrong mapping or case | Tampering | `mapping_sha256` and `case_sha256` in the manifest checked before NET-03 |
| Session writing or calling out where it should not | Elevation of privilege | AST gate (no socket, urllib, psycopg), allow-list of psspy calls, never `save` onto the case path (`CaseProtected`) |
| Silent acceptance of an unknown record | Tampering | Fail-closed parser; mutation tests for every refusal |

## Sources

### Primary (HIGH confidence)
- Repo files read this session: `backend/psse_job/psse_api.py`, `study.py`, `contingency.py`, `margin.py`, `mapping.py`, `settings.py`, `units.py`, `redaction.py`, `constants.py`, `launcher.py`, `ratings.py`, `probe.py`; `backend/psse_run_hourly.py`; `backend/tests/psse_fake_psspy.py`, `secret_scan_test.py`, `psse_contract_test.py`; `docs/data-science/decisions/psse_study_definitions.md`, `psse_laptop_runbook.md`; `docs/data-science/ops/psse_laptop_status.ps1`, `psse_laptop_cleanup.ps1`; `.planning/workstreams/pss-e-integration/phases/03-laptop-run-and-handover/03-07-LAPTOP-RECORD.md`; `.gitignore`; `pytest.ini`; `requirements.txt`; this workstream's `REQUIREMENTS.md`, `STATE.md`, `ROADMAP.md`, `research/SUMMARY.md`, `STACK.md`, `PITFALLS.md`
- Scratch experiments this session (Python 3.12.13, pandapower 3.5.6, numpy 2.4.3, pandas 2.3.3, scipy 1.17.1): builder round trip against `case39()`, synthetic RAW v33 writer, fail-closed parser, shunt sign, duplicate handling, transformer mapping against an independent Ybus solve, session call sequence against `FakePsspy`
- pandapower 3.5.6 installed source: `run.py` (runpp signature and `enforce_q_lims` text), `pf/run_newton_raphson_pf.py` (Q-limit loop), creator signatures via `inspect`
- PyPI JSON API and pypistats for pandapower; `gh api repos/e2nIEE/pandapower`

### Secondary (MEDIUM confidence)
- lanl-ansi PowerModels.jl `src/io/pti.jl` (v33 field tables, section order, terminators): https://raw.githubusercontent.com/lanl-ansi/PowerModels.jl/master/src/io/pti.jl
- PowSyBl PSS/E import documentation (transformer convention, unsupported items, RAW 33 and 35, RAWX 35): https://powsybl.readthedocs.io/projects/powsybl-core/en/latest/grid_exchange_formats/psse/import.html

### Tertiary (LOW confidence, community or search summaries)
- psspy.org forum: RAW export examples and errors (https://psspy.org/psse-help-forum/question/3777/unable-to-write-out-using-either-rawd_2-or-writerawversion/ , https://psspy.org/psse-help-forum/question/10100/save-raw-and-dyr-file/); reader functions `prmint('PFCODE')` and `prmdat('ACCN')` (https://psspy.org/psse-help-forum/question/11652/get-solution-parameters-and-solution-algorithm/); a `fnsl` positional option list and revision 35 and 36 bus-name problem seen only in web search summaries
- whit.com.au blog on keyword arguments (https://www.whit.com.au/blog/2012/12/keyword-arguments-for-psse-functions/): `options1` tap adjustment (0, 1, 2; default 1) and `options5` switched shunt flag, keywords start at 1

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH. Versions, installability and `pip check` all run this session; one new top-level package.
- Architecture: MEDIUM. The Mac side is proven on synthetic data; the laptop side reuses proven job functions but adds unverified calls, mitigated by isolation and measurement.
- Pitfalls: MEDIUM. Repo and pandapower pitfalls verified; PSS/E export, settings and scaling behaviour are LOW until the session runs.

**Research date:** 2026-11-16
**Valid until:** 2026-12-16 (30 days); re-check the pandapower pin and the PyPI wheel hash at plan time because pandapower releases every few weeks.
