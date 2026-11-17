---
phase: 01-pss-e-reference-session-and-network-parity
plan: 05
subsystem: infra
tags: [pandapower, pip, requirements, package-legitimacy, venv, hash-check]
status: complete

requires:
  - phase: 01-pss-e-reference-session-and-network-parity
    provides: this checkout's own Python 3.12 .venv (plan 01-01 Task 1)
provides:
  - requirements-pandapower.txt pinning pandapower 3.5.6 and repeating the numpy, pandas and scipy pins of requirements.txt
  - pandapower 3.5.6 and its declared requirements installed in this checkout's .venv, pip check clean, case39 solves
affects: [01-06, 01-07, 01-08, 01-09]

plan_head_before: 5d5a28272a96ae1f2cf11edd0f85fcd284cbca29
plan_head_after: ea9b1efb6442f8bbcf7627dcddf053174b90c1db
actuals:
  tokens: 1500
  tasks: 2
  commits: 1

tech-stack:
  added: [pandapower 3.5.6, networkx 3.7, pandera 0.36.0, pydantic 2.14.3, pydantic_core 2.50.4, deepdiff 9.1.0, geojson 3.3.0, typeguard 4.6.0, orderly-set 5.5.0, cachebox 5.2.3, colorama 0.4.6, annotated-types 0.8.0, mypy_extensions 1.2.0, typing-inspect 0.9.0, typing-inspection 0.4.5]
  patterns:
    - "A new top-level package enters only after a blocking-human legitimacy checkpoint, and the downloaded wheel's sha256 is compared with the approved hash before pip installs it"
    - "Mac-side solver pins live in requirements-pandapower.txt and repeat the numpy, pandas and scipy pins of requirements.txt; requirements.txt is not edited"

key-files:
  created:
    - requirements-pandapower.txt
  modified: []

key-decisions:
  - "requirements-pandapower.txt pins only pandapower plus the numpy, pandas and scipy trio; pandapower's own declared requirements are left to pip, as the plan specifies"
  - "numba is not installed: pandapower prints a warning that numba is missing and runs slower, which does not affect correctness; installing it would be a second new package needing its own legitimacy checkpoint"

requirements-completed: []

coverage:
  - id: D1
    description: "The owner confirmed the package, version and wheel hash in a blocking checkpoint before anything was installed"
    requirement: "NET-01"
    verification:
      - kind: manual
        ref: "Task 1 checkpoint reply: approved"
        status: pass
    human_judgment: true
  - id: D2
    description: "The downloaded wheel's sha256 equals the approved hash before install; pip check is clean; case39 solves; version equals the pin"
    requirement: "NET-01"
    verification:
      - kind: integration
        ref: ".venv/bin/python -m pip check (No broken requirements found.)"
        status: pass
      - kind: integration
        ref: ".venv/bin/python -c 'import pandapower as pp, pandapower.networks as pn; net = pn.case39(); pp.runpp(net); assert net.converged; print(pp.__version__)' (prints 3.5.6)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The existing PSS/E job's tests still pass after the install and requirements.txt is untouched"
    requirement: "NET-03"
    verification:
      - kind: unit
        ref: "psse_contract_test, psse_api_test, psse_study_test, secret_scan_test (-k 'not real_project_values'): 132 passed, 1 deselected"
        status: pass
    human_judgment: false

duration: 10min
completed: 2026-11-16
---

# Phase 1 Plan 05: Pin and install pandapower Summary

**pandapower 3.5.6 installed into this checkout's own `.venv` behind an owner-approved legitimacy checkpoint, with the wheel's sha256 verified before install, `pip check` clean and a case39 power flow solving.**

## Performance

- **Duration:** about 10 min for Task 2 (Task 1 was the owner checkpoint)
- **Completed:** 2026-11-16
- **Tasks:** 2 (1 checkpoint resolved with no commit, 1 auto with one commit)
- **Files modified:** 1 created

## Accomplishments

- Task 1 gate honoured: nothing was installed until the owner replied.
- `requirements-pandapower.txt` records the pin, the approval and the hash, and repeats numpy, pandas and scipy exactly.
- pandapower and its declared requirements are installed in this checkout's `.venv` only.

## Task 1: Owner approval (checkpoint:human-verify, blocking-human)

Owner's reply, verbatim: "approved"

Meaning: install pandapower 3.5.6, wheel `pandapower-3.5.6-py3-none-any.whl`, sha256 `b6d15d0d506136fd0b8d58a18c2e05ad4947fe1c8d5db2b74c9615cbb473c877`. The orchestrator also re-checked PyPI on 2026-11-16 just before the approval: 3.5.6 is the latest release, the source is github.com/e2nIEE/pandapower, and the wheel sha256 matches that value (uploaded 2026-10-07). No commit; nothing was installed before the reply.

## Task 2: Pin, hash-check, install, pip check, smoke solve

Commit `ea9b1ef` `build(01-05): pin pandapower for the Mac-side network parity`.

**Hash check (before install).** `pip download pandapower==3.5.6 --no-deps --only-binary=:all:` into a new empty scratch folder outside the repository, then `shasum -a 256`:

- downloaded wheel sha256: `b6d15d0d506136fd0b8d58a18c2e05ad4947fe1c8d5db2b74c9615cbb473c877`
- approved sha256: `b6d15d0d506136fd0b8d58a18c2e05ad4947fe1c8d5db2b74c9615cbb473c877`
- result: identical, install proceeded.

**Install** with `.venv/bin/python -m pip install -r requirements-pandapower.txt`, using this worktree's `.venv` only (Python 3.12.13).

**Packages pip added** (from `pip freeze` before and after, 57 lines before): pandapower 3.5.6, networkx 3.7, pandera 0.36.0, pydantic 2.14.3, pydantic_core 2.50.4, deepdiff 9.1.0, geojson 3.3.0, typeguard 4.6.0, orderly-set 5.5.0, cachebox 5.2.3, colorama 0.4.6, annotated-types 0.8.0, mypy_extensions 1.2.0, typing-inspect 0.9.0, typing-inspection 0.4.5.

**Packages pip upgraded:** none. The research expected tqdm to be upgraded; the venv's existing tqdm already satisfied pandapower, so the freeze diff shows additions only. numpy 2.4.3, pandas 2.3.3 and scipy 1.17.1 are unchanged.

**Verification output**

- `pip check`: `No broken requirements found.`
- Smoke solve (`pn.case39()`, `pp.runpp(net)`, `assert net.converged`): printed `3.5.6`, equal to the pin. It also printed pandapower's warning "numba cannot be imported and numba functions are disabled. Probably the execution is slow." (informational, see Decisions).
- Existing job tests (`psse_contract_test.py`, `psse_api_test.py`, `psse_study_test.py`, `secret_scan_test.py`, `-k "not real_project_values"`): `132 passed, 1 deselected in 13.60s`.
- Pin comparison: `diff <(grep -E '^(numpy|pandas|scipy)==' requirements-pandapower.txt | sort) <(grep -E '^(numpy|pandas|scipy)==' requirements.txt | sort)` exit 0.
- `git status --porcelain -- requirements.txt`: empty.
- `.venv/bin/python -I -B backend/private_leak_scan.py --staged`: exit 0.

## Deviations from Plan

None - plan executed exactly as written. One difference from the research's expectation is recorded above (tqdm was not upgraded, because the installed version already satisfied the requirement); this is an outcome, not a change of action.

## Issues Encountered

- A compound shell command (`cd ... && ... ; git ...`) was refused by the worktree guard; the commands were rerun as plain separate calls from the worktree. No effect on the result.
- `pip install -r` fetched the wheel again from PyPI rather than installing the hash-checked local copy. The plan specifies this sequence; the file on PyPI is the one whose hash the owner approved, and a later plan may add `--require-hashes` if stronger pinning is wanted.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or file-access surface was added.

## Next Phase Readiness

Plans 01-06 to 01-09 can import pandapower 3.5.6 from `.venv/bin/python`. numba is absent, so large solves run without its speedup; adding it needs its own legitimacy checkpoint.

## Self-Check: PASSED

- FOUND: requirements-pandapower.txt
- FOUND: commit ea9b1ef
