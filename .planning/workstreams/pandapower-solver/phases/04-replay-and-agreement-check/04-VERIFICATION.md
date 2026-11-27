---
phase: 04-replay-and-agreement-check
verified: 2026-11-21T23:15:00Z
status: passed
score: 7/7 must-haves verified
covered_files:
  - .planning/workstreams/pandapower-solver/phases/04-replay-and-agreement-check/04-01-PLAN.md
  - .planning/workstreams/pandapower-solver/phases/04-replay-and-agreement-check/04-01-SUMMARY.md
  - .planning/workstreams/pandapower-solver/phases/04-replay-and-agreement-check/04-02-PLAN.md
  - .planning/workstreams/pandapower-solver/phases/04-replay-and-agreement-check/04-02-SUMMARY.md
  - .planning/workstreams/pandapower-solver/phases/04-replay-and-agreement-check/04-03-PLAN.md
  - .planning/workstreams/pandapower-solver/phases/04-replay-and-agreement-check/04-03-SUMMARY.md
  - .planning/workstreams/pandapower-solver/phases/04-replay-and-agreement-check/04-04-PLAN.md
  - .planning/workstreams/pandapower-solver/phases/04-replay-and-agreement-check/04-04-SUMMARY.md
  - backend/pandapower_job/agree.py
  - backend/pandapower_job/recorded.py
  - backend/pandapower_job/replay.py
  - backend/pandapower_job/replay_cli.py
  - backend/pandapower_replay.py
  - backend/tests/pandapower_agree_test.py
  - backend/tests/pandapower_recorded_test.py
  - backend/tests/pandapower_replay_cli_test.py
  - backend/tests/pandapower_replay_fixture.py
  - backend/tests/pandapower_replay_output_test.py
  - backend/tests/pandapower_replay_owner_test.py
  - backend/tests/pandapower_replay_pg_test.py
  - backend/tests/pandapower_replay_readonly_test.py
  - backend/tests/pandapower_replay_study_test.py
  - backend/tests/pandapower_replay_test.py
  - supabase/ops/export_psse_runs_for_replay.sql
covered_digest: "v3:sha256:1b62374edd5d07d651d053a0a7353ee796d9868175f1116baa122c3ef8605217"
behavior_unverified: 0
overrides_applied: 0
---

# Phase 4: Replay and Agreement Check Verification Report

**Phase Goal:** A read-only replay of the recorded PSS/E runs through pandapower shows whether the two solvers agree, in a report that states how much it checked, shows the largest deviation even on a pass, and is proven able to fail.
**Verified:** 2026-11-21
**Status:** passed, with real limits (listed under "Limits that stay attached to this pass"). None of the limits is a gap in the check itself; they are limits on what the one real run proves.
**Re-verification:** No, initial verification.

Private data rule kept: nothing under `data/private/` was opened, read, grepped, scanned or printed. The real run is judged only from the counts-only record `04-REPLAY-RECORD.md` and from the public code.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC1 / AGR-01: each recorded run is replayed through pandapower with that run's stored ratings and the same mapping (matched by recorded hash), and a check shows it writes nothing to the database | VERIFIED | `replay.py:63-114` rebuilds a `ratings.Selection` from the run's own `ratings_used` (never the live view). `replay.py:140-161` `_decide` excludes unless `mapping_sha256` equals the local mapping hash and `case_sha256` equals the session case hash. `replay.py:215-275` `replay_snapshot` runs one study per distinct configuration and compares every member run. Write proofs: see "Read-only proofs" below. Tests pass (30 in `pandapower_replay_readonly_test.py`). |
| 2 | SC2 / AGR-02: a run passes only when the per-outage sets of overloads, voltage violations and non-converged outages are the same and margins and dispatch agree within the tolerances; near-limit elements are borderline, not failures | VERIFIED | `agree.py:255-273` compares violation keys of both sides; `agree.py:199-215` one-sided element within the owner band is borderline, outside it or any one-sided non-convergence is a failure; `agree.py:372-401` margins; `agree.py:404-445` dispatch; `agree.py:584-636` gate. `agree.compare_run` is exercised by 243 passing tests (agree, recorded) including a rule matrix covering every check word (`pandapower_agree_test.py:370-387`). Note the tolerance wording gap in Finding F-2. |
| 3 | SC3 / AGR-03: the report states runs checked, non-empty comparisons, the largest deviation even on a pass (private only), and exclusions with reasons | VERIFIED | Counts: `agree.py:500-514` `Summary` (integers and closed words; building one with anything else raises, `agree.py:485-497`), printed by `replay_cli.py:153-184` (runs in snapshot/replayed/passed/failed, per-reason exclusion counts, configurations, pairs, margin and dispatch comparisons, borderline, non-empty comparisons per kind, not-exercised kinds). Largest deviation: kept in `Detail` even on a pass (`agree.py:560-569, 630-635`) and written to `report.json` only (`replay_cli.py:194-221`, line 209); exclusions with run ids and reasons at `replay_cli.py:212`. `pandapower_replay_cli_test.py:345-364` asserts the report holds the largest deviation and run id and that the terminal holds neither. |
| 4 | SC4: a deliberate-mismatch test makes the replay fail, proving the check can fail | VERIFIED | `pandapower_replay_study_test.py:121-376`: for each tolerance, a perturbation inside passes with a non-zero deviation (utilisation strictly between 0 and 1) and one outside fails. Cases: thermal value 1% pass / 3% fail (121-130); voltage 0.005 pass / 0.02 fail (133-139); dispatch 1% / 3% (146-161); margin 0.9 / 1.1 of its allowance, both search classes (171-197); contingency count (200-205); removed voltage row fails, smallest is borderline (208-224); bogus voltage and thermal rows far-over fail, just-over borderline (236-254); recorded non-convergence on a converged outage fails (257-268); removed island rows fail (271-278); limiting factor flip (281-301); changed stored rating on the real solver fails on dispatch (304-316); altered mapping and different case hash are excluded and never pass (319-336); failed-only, broken-count and empty-comparison snapshots are incomplete, not pass (339-370). Ran: 22 passed in 52 s. Honest scope is in the file header: stand-in from the public 39-bus fixture; it proves failure detection and wiring, not agreement. Most matrix cases feed the stand-in's own stored results through a runner seam (`_gate`, line 74) instead of a fresh solve; the tracer (27-43), the stored-rating case (`real=True`, 311) and the CLI real-replay tests use the real solver. Disclosed in the file, not hidden. |
| 5 | SC5 / AGR-04: detailed output stays on the owner's machine; CI-mode output is counts and pass/fail only, and a test scanning it finds no identifier or study value | VERIFIED | One printer, `replay_cli.py:94-115`, raises on any line outside `CLI_LINE_PATTERNS` (62-91: integers of 1-9 digits and closed words; no figure, id, hash or path pattern). CI mode on for `--ci` or `GITHUB_ACTIONS == "true"` whatever the flag (`replay_cli.py:346`), writes no file or folder (365-371; `pandapower_replay_cli_test.py:390-415`). Leak scan test `pandapower_replay_output_test.py:129-192`: scan A (needles derived from the throwaway private tree) and scan B (the stand-in's run ids, element ids, every number in three text forms, hashes) are clean on the real CI output, and five planted values (branch key, long decimal, run id, mapping hash twice, report marker) each make a scan fire (162-189); the clean output is re-scanned after the plants. A second test (285-312) covers verdict pass/fail/incomplete in ci and local mode, every refusal and usage output. Ran: 2 passed. |
| 6 | Owner decision D-02: margin floor is `max(2%, stored step or tolerance)`; voltage keeps 0.01 pu; flows keep `max(2%, 2 MVA)` imported from `compare.py`, not redefined; the floor printed/recorded in the report header | VERIFIED | `agree.py:355-358` `margin_allowance = max(compare.FLOW_RELATIVE_TOLERANCE * abs(ref), resolution)`; `agree.py:386` resolution is the recorded `step_mw` for a rating-bound margin and the recorded `tolerance_mw` for a voltage-bound one, read from the recorded run so it cannot be widened; `agree.py:337-352` a differing step/tolerance/criterion/sink set is a failure. Voltages use `compare.VOLTAGE_TOLERANCE_PU` (`agree.py:209, 246, 398`), flows use `compare.within_flow`/`flow_allowance` (`agree.py:242-243, 393, 408-410`). `pandapower_agree_test.py:696-712` walks the syntax tree and proves no second tolerance literal exists (planted 0.01/0.02/2.0/1e-12/2 each detected). Header: `agree.tolerance_header()` (`agree.py:532-547`) goes into `report.json` header (`replay_cli.py:203-207`) and states the margin rule in words. Matches 04-CONTEXT.md D-02 exactly. |
| 7 | The real run in `04-REPLAY-RECORD.md` (19 of 19 passed; voltage_low and non_convergence not exercised; one mapping, case and job version) is described truthfully; SUMMARY and REQUIREMENTS wording does not overclaim | VERIFIED (with F-2 wording note) | Record and 04-04-SUMMARY state the limits in plain words (record lines 27-34; SUMMARY lines 40-45): not exercised kinds named, one configuration family over one period, not an hourly cloud run, "no rule was changed to reach this". Internal consistency checks that I can make from counts alone all hold: 19 runs x 4 cities = 76 dispatch rows and 76 dispatch comparisons; 76 margin rows x 5 comparisons = 380 minus 2 per rating-bound (quantised) margin = 362 requires 9 quantised margins, an integer; pairs compared 3895 equals contingency rows 3895 (every recorded row found its partner); non-empty comparison lines in the record match `gate()` (`agree.py:594-600`) and the not-exercised list matches the zero counts. The code path that would print exactly these lines exists (`replay_cli.py:153-184`). I cannot re-run the real replay (private data is out of scope); the pass itself is an owner-run, counts-only record (see Limits). |

**Score:** 7/7 truths verified, 0 present-but-behavior-unverified.

### Read-only proofs (check 1), and would they fail if a write were added

| Layer | Evidence | Would it fire? |
|-------|----------|----------------|
| Static import walk of the five phase modules | `pandapower_replay_readonly_test.py:68-71`: no psycopg, psycopg2, sqlalchemy, socket, http, urllib, requests, and no `psse_job.writer/job/gaps/credcheck/launcher/probe` | Yes: 20 planted import forms (direct, `from`, inside a function, inside an except block, nested class) each flagged (`:74-100`); quiet on the allowed imports (`:103-107`) |
| Fresh interpreter | `:110-129` imports the four modules and the entry script and prints which writer-side modules are in `sys.modules` (must be "none") | Yes for any writer-side import in the transitive chain |
| Runtime: full real-solver replay with blocks | `:158-185`: `socket.connect`, `connect_ex`, `create_connection`, `psycopg.connect` made to raise; `writer.connect/write_run/record_failure` and `job.run_once` replaced by recorders; replay must return `replay: pass` with zero recorder calls | Yes: `:188-199` shows the block and the recorder each raise when called |
| Postgres-tier read-only proof of the export SQL | `pandapower_replay_pg_test.py` (runs the SQL in a read-only session, tables unchanged) | Skips here (no Postgres). Not run by me. See F-4. |

Module docstrings of `replay.py:1-22` and `recorded.py:1-50` match the code: no driver, no network, no writer import; the replay never calls `run_once`, `write_run` or `record_failure` (grep of the four modules found no such call).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/pandapower_job/recorded.py` (680 lines) | strict ingest, snapshot, counts-only profile | VERIFIED | Strict validation with count cross-check (module docstring 14-20); closed refusal reasons (99-103); closed print vocabulary (113-120); wired into `replay.py:28`, `replay_cli.py:47`. |
| `backend/pandapower_job/agree.py` (636 lines) | pure rules and gate | VERIFIED | Imports only collections, math, `compare`, `constants` (asserted by `test_agree_is_pure`); wired from `replay.py`. |
| `backend/pandapower_job/replay.py` (275 lines) | hash-matched replay | VERIFIED | Wired from `replay_cli.py:361`. |
| `backend/pandapower_job/replay_cli.py` (430 lines), `backend/pandapower_replay.py` (24) | owner commands, closed-vocabulary printer, private report, CI mode | VERIFIED | Entry script puts backend on the path under `python -I` and calls `replay_cli.main`; exit-code test and no-argument usage test pass. |
| `supabase/ops/export_psse_runs_for_replay.sql` (98 lines) | one read-only SELECT | VERIFIED | Single statement of CTEs plus SELECT, no write word; selects only pinned columns (46-74), never `error`, `ratings_read_error` or case label. A text test pins it (`pandapower_recorded_test.py`, passed). Real-world evidence it ran: the owner's export ingested with the database-computed counts equal to the parsed rows (record lines 9-12). |
| `backend/tests/pandapower_{agree,recorded,replay,replay_cli,replay_study,replay_readonly,replay_output,replay_owner,replay_pg}_test.py` and `pandapower_replay_fixture.py` | proofs | VERIFIED | All present and substantive. |
| `04-REPLAY-RECORD.md` | counts-only record | VERIFIED | One `Verdict:` line; no id, hash, path or figure beyond counts. |

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| owner export file | snapshot | `replay_cli._run_ingest` -> `recorded.ingest_export` (`replay_cli.py:301`), private path guard first (295-299) | WIRED |
| snapshot | replay | `recorded.load_snapshot` (`replay_cli.py:350`) -> `replay.replay_snapshot` (361) | WIRED |
| recorded rows + results | verdict | `agree.side_from_recorded/side_from_results/compare_run` (`replay.py:255-257`) -> `agree.gate` (`replay.py:274`) | WIRED |
| verdict | printed lines / private report | `render_summary_lines` (`replay_cli.py:372-373`), `report_document` + `private.write_private_json` (366-371) | WIRED |
| tolerances | `compare.py` | imported by name in `agree.py` (tree-walk test) | WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data | Source | Real data | Status |
|----------|------|--------|-----------|--------|
| replayed side | `agree.side_from_results(results)` | `prepared.study(selection, None)` on the real pandapower engine (`replay.py:192-195`) | Yes (real solver in tracer, stored-rating, CLI-real and readonly tests) | FLOWING |
| recorded side | `agree.side_from_recorded(row, item.dispatch, ...)` | validated snapshot rows (`replay.py:256`) | Yes | FLOWING |
| summary counts | `agree.gate` totals | sums of per-run `RunComparison.counts` (`agree.py:618-628`) | Yes | FLOWING |

### Behavioral Spot-Checks (I ran these)

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Agreement rules, gate, ingest and export validation | `pytest backend/tests/pandapower_agree_test.py backend/tests/pandapower_recorded_test.py` | 243 passed, 18.6 s | PASS |
| Read-only proofs (import walk, planted imports, fresh interpreter, blocked-connection real replay) | `pytest backend/tests/pandapower_replay_readonly_test.py` | 30 passed, 19.4 s | PASS |
| CI output leak scan with planted values; every output scanned | `pytest backend/tests/pandapower_replay_output_test.py` | 2 passed, 20.5 s | PASS |
| Deliberate-mismatch matrix on the real solver | `pytest backend/tests/pandapower_replay_study_test.py` | 22 passed, 52.3 s | PASS |
| Owner-local test of the real snapshot | not run (private data, about 11 minutes, record says it passed) | n/a | SKIPPED by instruction |
| `pandapower_replay_cli_test.py`, `pandapower_replay_test.py`, `pandapower_replay_pg_test.py` | not run by me (time; pg skips without Postgres) | n/a | not run |

### Probe Execution

Step 7c: SKIPPED (no probe scripts declared by the phase; no `scripts/*/tests/probe-*.sh` relevant).

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| AGR-01 | 04-01, 04-03, 04-04 | Read-only replay of each recorded run with stored ratings and same mapping by hash, writes nothing | SATISFIED | Truth 1; `replay.py:63-161, 215-275`; readonly proofs; real replay of 19 runs recorded. |
| AGR-02 | 04-02, 04-03 | Pass rule on sets, margins and dispatch within 2%; borderline | SATISFIED, with wording note | Truth 2 and 6. "Within 2%" is implemented as the owner's D-02 rule (floors); see F-2. |
| AGR-03 | 04-02, 04-03, 04-04 | Report states runs, non-empty comparisons, largest deviation even on a pass, exclusions; deliberate mismatch fails | SATISFIED | Truths 3 and 4. |
| AGR-04 | 04-01, 04-03, 04-04 | Detailed output on owner's machine; Actions output counts and pass/fail only | SATISFIED | Truth 5. |

No orphaned requirements: REQUIREMENTS.md maps exactly AGR-01 to AGR-04 to Phase 4, and each is claimed by a plan.

### Anti-Patterns Found

None. Debt-marker grep (`TBD|FIXME|XXX|TODO|HACK`) over the phase's source, SQL and test files returned no matches. No stub, placeholder return or hardcoded-empty value flows to output.

## Findings

| ID | Severity | Finding |
|----|----------|---------|
| F-1 | WARNING (tracker, not code) | `ROADMAP.md` still shows Phase 4 as "3/4 plans executed" and `04-04-PLAN.md` unchecked (`ROADMAP.md:190, 201`) and the phase line `[ ]` (79), while SUMMARY, STATE and REQUIREMENTS record 04-04 and AGR-01 to AGR-04 complete. Update ROADMAP when this verification is accepted; STATE.md and ROADMAP are orchestrator-owned and were not edited here. |
| F-2 | WARNING (wording) | The text of AGR-02 in REQUIREMENTS.md ("margins and dispatched capacity agree within 2%") and the STATE.md decision line ("flows and capacities within 2%") omit the owner-decided floors that actually apply: flows and dispatch `max(2%, 2 MVA)` (`compare.py`), margins `max(2%, stored step or tolerance)` (D-02, `agree.py:355-358`), voltages 0.01 pu. A rating-bound margin can therefore differ by up to one stored step (25 MW in the design) while passing. This is deliberate and owner-approved and the code, tolerance header and 04-CONTEXT all say so; only the requirement/STATE sentences read as a plain 2%. Also, REQUIREMENTS marks AGR-02 "Complete" with no caveat that low-voltage and non-convergence agreement has not been exercised by real data. Phase 5's OPS-03 decision should read the record's limits, not only the tick. No SUMMARY overclaims: 04-03 and 04-04 SUMMARY carry the limits. |
| F-3 | WARNING (evidence limit, accepted) | The real pass (19 of 19) is evidenced only by an owner-run, counts-only record. No test pins the real verdict (by design: `pandapower_replay_owner_test.py` docstring), CI cannot reproduce it, and I could not and did not re-run it (private data forbidden). I checked that the record's counts are mutually consistent and match what the code would print, which is consistent with an honest run but is not independent proof. Reproduction needs the owner's machine. |
| F-4 | INFO | The Postgres-tier tests (`pandapower_replay_pg_test.py`) skip on this machine, so the read-only behaviour of the export SQL in a read-only session is shown here only by its text test (single statement, no write word, pinned columns). In practice the SQL has run for real once: the owner's export passed the strict ingest with the database counts equal to the parsed row counts. Run the pg tier where Postgres exists before relying on it for a wider export. |
| F-5 | INFO | The static import walk covers only the five phase modules' own imports. Transitive modules the replay does import (`psse_job.ratings` imports `http.client` and `urllib`; `engine`, `study`, `run_record` import `subprocess`/`tempfile`) are not walked for network or driver names; the fresh-interpreter check covers writer-side modules only. The runtime test with blocked connections and recorder fakes is the layer that would catch an actual connection or writer call on a replayed path. Residual risk is low (replay calls `ratings.parse_ts` and constructs `RatingChoice`, not the fetch functions), but a network call on a path the stand-in does not exercise would not be caught. |
| F-6 | INFO | Voltage-low agreement is exercised only at unit level (`pandapower_agree_test.py:54, 78, 118, 519`), never by the real solver stand-in or by real data; non-convergence is exercised by the real-solver stand-in (island rows) but not by real data. The record says so. The code path for voltage_low is the same kind-agnostic path as voltage_high (`agree.py:206-209, 246`). |
| F-7 | INFO | Real-data pass has no real-data negative control: the check is shown able to fail only on the public stand-in matrix. This is the stated design; it is a limit of what "19 of 19" shows, not a defect. |

No finding is a BLOCKER.

## Limits that stay attached to this pass

- One mapping, one case hash, one job version, one recorded period: agreement on one configuration family, not across mappings or seasons. (Record lines 32-33; confirmed by the code that matches by hash, `replay.py:140-161`.)
- Thermal overload and high-voltage agreement are exercised by real comparisons (114 and 608 outage-kind counts). Low-voltage and non-convergence agreement is not exercised by real data.
- The tolerances are the owner's: 0.01 pu, `max(2%, 2 MVA)`, margins `max(2%, step or tolerance)`. A pass means agreement inside those, not exact equality.
- The 19 runs are replayed through 18 distinct configurations (one study per configuration, each compared with every member run); run-level row times are not compared.
- Not an hourly cloud run. Phase 5 (workflow, dry run, soak, OPS-03 owner decision) is unbuilt. Phase 5's live-write gate still needs the owner decision recorded.

## Human Verification Required

None required to close this phase. Optional, owner-side: re-run `pandapower_replay.py replay` locally after any change to mapping, case or the rules, and re-run the pg tier where Postgres exists (F-3, F-4).

## Gaps Summary

No gaps. All five roadmap success criteria and the D-02 and real-run-description truths hold against the code and the tests I ran (297 tests across four files, all passed). The status is passed with the limits above; the actionable follow-ups are tracker and wording (F-1, F-2), not code.

---

_Verified: 2026-11-21_
_Verifier: Claude (gsd-verifier)_
