---
phase: 01-pss-e-reference-session-and-network-parity
verified: 2026-11-20T12:00:00Z
status: passed
score: 5/5 must-haves verified
covered_files:
  - .gitignore
  - backend/pandapower_job/cli.py
  - backend/pandapower_job/compare.py
  - backend/pandapower_job/convert.py
  - backend/pandapower_job/ingest.py
  - backend/pandapower_job/network.py
  - backend/pandapower_job/parity.py
  - backend/pandapower_job/raw.py
  - backend/pandapower_job/scaling.py
  - backend/pandapower_job/solve.py
  - backend/private_leak_allow.json
  - backend/private_leak_scan.py
  - backend/psse_pandapower_session.py
covered_digest: "v3:sha256:7e602cb9a4daeb354e42bcf23937084496f4e8d0a9a0f44fdbe420b55878cdca"
behavior_unverified: 0
overrides_applied: 0
---

# Phase 1: PSS/E Reference Session and Network Parity Verification Report

**Phase Goal:** A teammate-run, read-only session on the licensed machine produces the private network data, the load-flow settings and a reference solution, and a pandapower network built from that data matches the reference, with nothing from the session in the public repository.
**Verified:** 2026-11-20
**Status:** passed
**Re-verification:** No, initial verification

Private files under `data/private/` were not printed, quoted or copied. This report holds counts, verdicts and file names of public code only.

## Goal Achievement

### Observable Truths (ROADMAP success criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Ignore rules and the secret/identifier scan are in place before any exported file reaches the owner's machine; the scan passes on the clean tree and flags a planted placeholder identifier | VERIFIED | `.gitignore` line 69 ignores `/data/private/` and line 70 `psse_pp_session*` (also `*.raw`); `git check-ignore` confirms a raw file and a zip under `data/private/` are ignored. `backend/private_leak_scan.py` (554 lines, three layers: path, shape, private needles; working tree and `--staged`) was first committed 2026-11-16 18:08 (3c8066b), three days before the first real session (2026-11-19/20). `private_data_guard_test.py` includes `test_tracer_ignore_rule_clean_tree_and_planted_identifier`, passes. I ran the scanner: working tree exit 0, `--staged` exit 0. |
| 2 | A teammate-run, read-only session returns a masked report listing the network data, load-flow settings, three scaling details, and a reference solution for each city's base case and each screened outage; nothing committed | VERIFIED | `01-SESSION-RECORD.md`: outcome `complete`, exit 0, every section ok, 135 members verified against the manifest by ingest. Counts: buses 39, lines 34, transformers 12, loads 19, machines 10, switched shunts 2; 4 cities all ok, 32 outages (all converged), 8 margin points; settings: 10 read/measured/unavailable classified, 0 deviations; scaling 4 experiments ok. Private session folders exist locally under `data/private/pandapower/sessions/` (reference per city, settings, network, scaling). Session script `backend/psse_pandapower_session.py` is a thin entry over the call-gated session package; `psse_session_*` tests (52) pass. `git ls-files data/private` is empty; no `.raw`, `.sav`, zip, `psse_pp_session*`, `converted_network`, `network_39bus` or `mapping.json` path appears anywhere in `git log --all`. |
| 3 | The builder produces a pandapower network keeping PSS/E bus numbers as indices and `from-to-circuit` names, and stops with a clear failure on any record type it does not understand | VERIFIED | `raw.py` raises `RawRefused` with one reason from a closed list (`unknown_section`, `unsupported_section`, `three_winding`, `field_count`, `bad_value`, `trailing_data`, ...); `network.py` raises `BuildRefused` for features it cannot reproduce exactly (switched-shunt control modes, remote regulation, non-local tap control, no swing bus, ...). `pandapower_raw_test.py`, `pandapower_network_test.py`, `pandapower_shunt_control_test.py` pass. Real export builds (re-run, below). |
| 4 | The parity report compares the built network with the export element by element, lists every difference, and shows none | VERIFIED | Independent re-run of `backend/pandapower_net_check.py check` on the approved session (newest, 135 members): `session: verified`, `mapping: verified`, `network: built`, `parity: pass`; 11 categories each with 0 differing (compared counts 5, 56, 278, 116, 152, 34, 117, 22, 40, 38, 4). Matches the session record exactly. Converted copy 25,191 bytes (3,231 gzip), fits the secret limit. |
| 5 | Base-case load flow of each city's scaled copy matches the PSS/E reference: every bus voltage within 0.01 pu, every branch flow within 2% with an absolute floor | VERIFIED | Same independent re-run: `net03: pass (4 of 4 cities)`; AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO each: algorithm run pass and injected-snapshot run pass, buses compared 39 failed 0, flows compared 138 failed 0. `compare.py` constants: `VOLTAGE_TOLERANCE_PU = 0.01`, `FLOW_RELATIVE_TOLERANCE = 0.02`, `FLOW_FLOOR_MVA = 2.0`; a test walks the file's syntax tree to prove tolerances are written only there; no explained-differences registry was used (`registry: none`). Check exit code 0. |

**Score:** 5/5 truths verified (0 present, behavior-unverified).

Behavior-dependent invariant (switched-shunt step control and the orientation join): not accepted on presence. Synthetic tests in `pandapower_shunt_control_test.py` and `pandapower_compare_test.py` pass, and the real-data comparison was reproduced in this verification.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/private_leak_scan.py`, `.gitignore`, `backend/private_leak_allow.json` | Leak guard | VERIFIED | Present, substantive, run clean. Allow-list has 22 entries, each only `path` and `sha256` (no private value); all are public false positives (planning docs, tests, public weather CSVs, IEEE-39 test tables). |
| `backend/psse_pandapower_session.py`, `docs/data-science/ops/psse_pandapower_session.ps1`, `docs/data-science/decisions/psse_pandapower_session_guide.md` | Laptop session entry, wrapper, guide | VERIFIED | Tracked; used for the real run. |
| `backend/pandapower_job/{raw,network,parity,compare,solve,scaling,convert,ingest,cli}.py`, `backend/pandapower_net_check.py` | Parser, builder, parity, solve, compare, ingest/check | VERIFIED | All substantive (5,260 lines total) and wired through `cli.main`; exercised end to end on the real session. |
| `requirements-pandapower.txt` | pinned install | VERIFIED | Tracked. |
| `docs/data-science/decisions/pandapower_network_data_decision.md` | D-06 decision, keep private | VERIFIED | Present; counts-only evidence; no network file, pin or per-network allow-list entry committed. |

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| session zip | ingest | manifest hash verification, 135 members | WIRED (re-run `session: verified`) |
| ingest/check | parser, builder | `cli.check` | WIRED |
| builder | parity | element-by-element 11 categories | WIRED |
| builder + scaling + solve | compare | per-city algorithm and injected runs | WIRED |
| leak scan | git index and working tree | `--staged`, default | WIRED |

### Data-Flow Trace (Level 4)

Comparison inputs are the real PSS/E export and PSS/E's own solved answers (not literals); the check re-derived parity and NET-03 from them in this verification. FLOWING.

### Behavioral Spot-Checks and Tests

| Check | Command | Result | Status |
|-------|---------|--------|--------|
| Phase 1 tests | `.venv/Scripts/python.exe -m pytest backend/tests/pandapower_*_test.py backend/tests/private_data_guard_test.py` | 299 passed, 8 skipped, 0 failed | PASS |
| Session script tests | `psse_session_test.py`, `psse_session_reference_test.py`, `psse_session_settings_test.py` | 52 passed | PASS |
| Leak scan, tree | `private_leak_scan.py` | exit 0 | PASS |
| Leak scan, staged | `private_leak_scan.py --staged` | exit 0 | PASS |
| Real-data check | `pandapower_net_check.py check --session <approved> --mapping <private>` | `check: pass`, exit 0 | PASS |

The 8 skips are the recorded-run engine tests (no check folder configured, Phase 2 scope), one POSIX-only ingest case, and the database tier (no Postgres here, Phase 3 scope). None belongs to a Phase 1 requirement.

### Probe Execution

No `probe-*.sh` is declared by this phase. SKIPPED.

### Requirements Coverage

| Requirement | Verdict | Evidence |
|-------------|---------|----------|
| PSE-01 session exports network data, returns masked report | VERIFIED | Session record network section counts; manifest-verified zip of 135 members; masked summary matched by ingest; session code read-only by design and by tests. |
| PSE-02 solution settings and the three scaling details | VERIFIED | 10 settings classified (read 2, measured 5, unavailable 3), 0 deviations, `enforce_q_lims` on; scaling: swing absorbs yes, clamped no, Q scales with P yes. Reproduced by the check run. |
| PSE-03 reference solution per city base case and per screened outage | VERIFIED | 4 cities ok, 32 screened outages converged, 8 margin points recorded in the verified zip; base-case reference consumed by NET-03. Outage references are captured and ingested; their consumption belongs to Phase 4 (AGR). |
| PSE-04 nothing committed; ignore rules and scan in place first | VERIFIED | No private path in `git ls-files` or `git log --all`; scanner and ignore rule predate the session; scan clean on tree and index; D-06 recorded as keep-private with nothing published. |
| NET-01 build with PSS/E bus numbers and `from-to-circuit` names; fail closed | VERIFIED | Closed refusal reasons in `raw.py` and `network.py`, covered by tests; real export builds; names category 278 compared, 0 differing. |
| NET-02 parity report, none differing | VERIFIED | 0 differences in 11 categories, reproduced. |
| NET-03 base case matches within 0.01 pu and 2% | VERIFIED | 4 of 4 cities pass both runs, 39 buses and 138 flows compared per city, 0 failed, reproduced. No tolerance, parameter or registry entry was loosened. |

No orphaned requirements: REQUIREMENTS.md maps exactly PSE-01 to PSE-04 and NET-01 to NET-03 to this phase.

### Anti-Patterns Found

None blocking. No unreferenced `TBD`, `FIXME` or `XXX` was a gate issue in the covered code.

### Advisory (not blocking, no effect on status)

1. Bookkeeping is stale: ROADMAP.md still shows Phase 1 unticked and "9/11 plans executed", and REQUIREMENTS.md still shows PSE-01..04 and NET-01..03 unticked (and the traceability table likewise). The orchestrator should update these after this verdict.
2. RESOLVED. `01-11-SUMMARY.md` previously said `backend/private_leak_allow.json` "was not created". It now says plan 01-11 added no new entry; the file already holds 22 entries from plan 01-10 (path and hash only, all public false positives). Re-verified after the edit: no backend or `.gitignore` change since 233de88, Phase 1 tests 299 passed 8 skipped, check on the approved session `check: pass`.
3. Open operational items outside the codebase, recorded in 01-10: the teammate must delete the three session zips, the mapping copy and empty the Recycle Bin on the laptop; the owner must remove mapping copies from Downloads and chat. These cannot be checked from the repository.
4. The owner's approval of parity and NET-03 (2026-11-20) is a recorded human decision; this verification does not depend on it because the results were re-derived here.
5. The network is a PSS/E Xplore (50-bus limit) 39-bus case; the converted network is private by decision (D-06), so the hourly workflow depends on a GitHub secret created from it (Phase 5).
6. Windows-only test failures and Postgres-dependent tiers were not treated as regressions, per instructions; none occurred in the Phase 1 test selection.

### Gaps Summary

No gaps. All five roadmap success criteria and all seven requirements hold in the codebase, and the real-data parity and NET-03 verdicts were reproduced independently.

---

_Verified: 2026-11-20_
_Verifier: Claude (gsd-verifier)_

**Final status: passed**
