---
phase: 04-per-city-scaling-of-the-39-bus-case
verified: 2026-11-11T20:00:00Z
status: passed
score: 7/7 must-haves verified
covered_files:
  - ".planning/workstreams/pss-e-integration/phases/04-per-city-scaling-of-the-39-bus-case/04-01-PLAN.md"
  - ".planning/workstreams/pss-e-integration/phases/04-per-city-scaling-of-the-39-bus-case/04-01-SUMMARY.md"
  - ".planning/workstreams/pss-e-integration/phases/04-per-city-scaling-of-the-39-bus-case/04-02-PLAN.md"
  - ".planning/workstreams/pss-e-integration/phases/04-per-city-scaling-of-the-39-bus-case/04-02-SUMMARY.md"
  - ".planning/workstreams/pss-e-integration/phases/04-per-city-scaling-of-the-39-bus-case/04-03-PLAN.md"
  - ".planning/workstreams/pss-e-integration/phases/04-per-city-scaling-of-the-39-bus-case/04-03-SUMMARY.md"
  - ".planning/workstreams/pss-e-integration/phases/04-per-city-scaling-of-the-39-bus-case/04-04-PLAN.md"
  - ".planning/workstreams/pss-e-integration/phases/04-per-city-scaling-of-the-39-bus-case/04-04-SUMMARY.md"
  - ".planning/workstreams/pss-e-integration/phases/04-per-city-scaling-of-the-39-bus-case/04-05-PLAN.md"
  - ".planning/workstreams/pss-e-integration/phases/04-per-city-scaling-of-the-39-bus-case/04-05-SUMMARY.md"
  - ".planning/workstreams/pss-e-integration/phases/04-per-city-scaling-of-the-39-bus-case/04-06-PLAN.md"
  - ".planning/workstreams/pss-e-integration/phases/04-per-city-scaling-of-the-39-bus-case/04-06-SUMMARY.md"
  - "backend/psse_job/contingency.py"
  - "backend/psse_job/mapping.py"
  - "backend/psse_job/probe.py"
  - "backend/psse_job/psse_api.py"
  - "backend/psse_job/study.py"
  - "backend/tests/psse_api_test.py"
  - "backend/tests/psse_fake_psspy.py"
  - "backend/tests/psse_mapping_test.py"
  - "backend/tests/psse_probe_test.py"
  - "backend/tests/psse_scaling_test.py"
  - "docs/data-science/decisions/psse_laptop_runbook.md"
  - "docs/data-science/decisions/psse_study_definitions.md"
  - "docs/data-science/schema/psse_mapping_example.json"
covered_digest: "v3:sha256:e39915e0237b1f13bf92a1345038c57ff42733c07c21a48e8735b7a44d13c2f8"
behavior_unverified: 0
overrides_applied: 1
overrides:
  - must_have: "No such figure (base case totals) appears in git history"
    reason: "The totals of PSS/E's public 39-bus example case remain in pushed commits 6e59341 and 1f60eb5. The user decided to accept the exposure and not rewrite history; no city target or El Paso figure was ever committed (per the record). The history still contains the totals. The rule going forward is no city figure and no case total in the tree."
    accepted_by: "the user, as recorded in 04-CONTEXT.md under 'Decisions made after execution (2026-11-11, the user)'"
    accepted_at: "2026-11-11"
re_verification:
  previous_status: human_needed
  previous_score: 6/7
  gaps_closed:
    - "History exposure of the base case totals: decision recorded (accepted, not rewritten) in 04-CONTEXT.md, commit a77d5bd"
    - "Stale 'UNVERIFIED until the laptop' wording in psse_api.py docstrings, runbook step 4 and one line of psse_study_definitions.md; 'same day' date comment; 04-06-SUMMARY allow-placeholder line"
  gaps_remaining: []
  regressions: []
---

# Phase 4: Per-city scaling of the 39-bus case - Verification Report (third pass)

**Phase Goal:** The job runs the same study once per city on its own fresh copy of the same 39-bus network, scaled to that city's load and generation targets, so the four cities never share a solve. The targets live in the private mapping (never in git); the job applies them with its own scaling call and never executes the recorded `.idv` scripts.
**Verified:** 2026-11-11
**Status:** passed (with one accepted deviation, stated plainly below)
**Re-verification:** Yes, third pass

## Read this first: git history still contains the totals

**The pushed history of `feature/pss-e-integration` still contains the base case totals of PSS/E's public 39-bus example case.** They are in `04-CONTEXT.md` at 6e59341 and 1f60eb5 and in `04-RESEARCH.md` at 1f60eb5. Both commits were pushed on 2026-11-09, they are on `origin/feature/pss-e-integration`, and `main` does not contain them (`git merge-base --is-ancestor 6e59341 main` fails). 128cf3d and a77d5bd are also on origin, so the removal from the tree is pushed too, but a later commit cannot take figures out of earlier ones. History was **not rewritten and is not clean**. The user chose to accept that. This report records the exposure as accepted, not as removed.

The "never in git" half of the goal is therefore true of the current tree and the working tree, and false of the repository's history, by the user's recorded choice.

## The recorded decision (checked in the file, not taken from the request)

`04-CONTEXT.md:35-37`, section "Decisions made after execution (2026-11-11, the user)": "The history exposure is accepted, not rewritten." It names commits 6e59341 and 1f60eb5, says the totals were removed from the tree in 128cf3d, gives the reason (a public example case, not Power Systems' data; no city target or El Paso figure ever committed), and states the rule: "no city figure and no case total in the tree from now on." It was added in a77d5bd (`git show a77d5bd --stat` lists `04-CONTEXT.md`, +5 lines).

Judgment: this is an explicit, written, dated decision that answers the exact question the second pass raised (rewrite or accept and record). That resolves the human item, and I treat truth 6b as PASSED (override). One limit I cannot remove: I did not see the conversation. The decision's attribution to the user rests on the document's own heading and on the requester's statement; the commit was authored under the user's git identity but its content was written by Claude. If the user did not in fact make this decision, truth 6b reverts to UNCERTAIN and the status to `human_needed`. Also note the record's own claim "no city target or El Paso figure was ever committed" is supported by the second pass's scans (case totals and the El Paso method, pickaxe on `utility 5701`), not by a scan of every historical blob for every possible target value.

## "Never in git": current tree, searched again this pass

**Current tree (HEAD a77d5bd plus the working tree): CLEAN of case totals and city figures.**
- Searched backend, docs, supabase, `.planning` (all workstreams and milestones); there is no `scripts` directory. Patterns covered the three totals in plain, comma, space and decimal forms (5.8x to 5.9x thousand MW, 2.7x thousand Mvar, 5.9x thousand MW, with a margin), `thousand MW` and `thousand Mvar`, run with PCRE look-arounds over the whole tree, then narrowed to the PSS/E code, tests, docs, schema, supabase and the workstream. Repository-wide hits were weather CSVs, shadow-model numbers, soak data and commit hashes. Inside the PSS/E paths every hit was a line-number range or a commit hash (`:277`, `:590`, `5928`, and similar). None is a case total.
- The only `thousand MW`/`thousand Mvar` strings left are inside the prior copy of this verification file, which this report replaces.
- The phase's own blobs at 128cf3d and a77d5bd hold no totals (`04-CONTEXT.md` 0 matching lines; `04-RESEARCH.md` one match, a `study.py:277` line reference).
- City figures: no city load or generation target and no El Paso number appears. The El Paso proposal states the method only. The scaling numbers in tracked files are the synthetic ones in `psse_mapping_example.json` (`"placeholder": true`, fake 9xxxx buses; they are round numbers chosen against the fake network, not any city's figures, though they sit in a plausible range, which is why the file's own note says so), `04-RESEARCH.md` fixtures, plan text and tests. Phase 1 and 2 notes hold per-circuit rating MVAs and placeholder transfer numbers, which are not scaling targets.
- Info only: `04-CONTEXT.md` says each city keeps the base case's load power factor "(about 0.90)". That is a ratio, not a total, and is not what the rule forbids; noted so the user can decide whether it should be dropped too.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | One fresh copy of the case per city, each city solved on its own (SCL-02, SCL-03) | VERIFIED | `study.prepare_city_base` (study.py:435-446) calls `api.load_case(index.case_path)` per city, then `scale_city_case`, ratings, base solve. `psse_scaling_test.py` tracer and independence tests pass in my run. |
| 2 | Targets live in the mapping (schema v2: `load_mw`, `gen_mw`, `basis`), refused before any PSS/E call when missing or invalid (SCL-01) | VERIFIED | `psse_mapping_test.py` passes in the 329-test set; the committed example is v2 and `placeholder: true`. |
| 3 | Job applies targets with its own scaling call; never runs a recorded `.idv` or any script (SCL-02, CD-2) | VERIFIED | A search of `backend/psse_job` for `idv`, `runrspnsfile`, `runiplanfile`, `runpy`, `os.system`, `exec(`, `subprocess` finds only `git rev-parse` in `run_record.py` and the study.py docstring saying the job never runs an `.idv`; launcher.py and taskxml.py have none. `test_surface_cannot_run_a_script` passes. |
| 4 | A failing city: all four attempted, one failed run naming every city, no result rows (SCL-04) | VERIFIED | `combined_failure` (study.py:517) and the collecting loop (:602); scaling failure and budget tests pass. The Postgres-backed study job tests were run by the orchestrator, not by me. |
| 5 | Result rows unique and attributable per city, no schema change; no city figure in the database, a log line, error text or dry-run output (SCL-05) | VERIFIED | `scaling_record` returns only basis and method; contingency ids carry the city prefix; scaling and launcher figure-free tests pass (131 passed, 14 owner-local or Postgres skips across contract, secret scan, setup doc, launcher, schema doc, run record, task XML). |
| 6a | No city target, El Paso figure or case total in the current git tree | VERIFIED | Search above; `secret_scan_test.py` passes. |
| 6b | No such figure in git history | PASSED (override) | Not true: the totals are in 6e59341 and 1f60eb5 (pushed). Accepted, not rewritten, by the user's recorded decision of 2026-11-11 in `04-CONTEXT.md`. Override: accepted by the user, 2026-11-11. |
| 7 | Probe row, scaling layout and a four-city dry run proven on the laptop's 39-bus case (SCL-06) | VERIFIED (laptop record only; not re-runnable here) | `04-06-LAPTOP-RECORD.md`: positions match the installed help; first probe 30 PASS 1 FAIL (ierr 5); fix at 5a30c63; second probe 0 FAIL exit 0 with `scale_to_target` PASS; four-city dry run exit 0, `psse_dispatched_capacity=4`, `validation: ok`, `study_seconds: 2.0`, nothing written. The record holds no path, host, case name, bus number or figure. |

**Score:** 7/7 truths verified, one of them by a recorded user override (6b). `behavior_unverified: 0`.

### Commit 5a30c63 (the APIOPT 2 close fix)

`git merge-base --is-ancestor 5a30c63 HEAD` succeeds (ANCESTOR_OK). `read_totals` returns on a failed read without a close, calls `_close_totals_read` (an `scal_2` call with `apiopt_close = 2`, figure-free `_CLOSE_FAILED` on failure) before any shape check, then parses. Tests: `psse_api_test.py -k "close or open_read or scale_layout or cannot_run"` gives 6 passed; `test_read_totals_closes_every_read_so_reads_can_follow_each_other`, `test_fake_scal_2_models_the_open_read_state`, `test_read_totals_close_failure_raises_without_figures` and `test_failed_read_issues_no_close` exist; `psse_scaling_test.py:174` pins the per-city call order `[1, 2, 0, 1, 2]`. The "18 tests fail with the close removed" figure (record and 04-06-SUMMARY) is the executor's claim; I did not run that mutation.

### Changes in a77d5bd, checked in the files

- `psse_api.py`: the module docstring, the `read_totals` docstring and the `scale_case` docstring now say the layout was shown working on the laptop on 2026-11-11 (confirmed in `git show a77d5bd`); the comment above `SCALE_LAYOUT` now says "The laptop probe of 2026-11-11". `SCALE_LAYOUT.confidence` is `"HIGH"`.
- `psse_study_definitions.md` line 234 now says the layout was shown working; runbook step 4 now describes U35 as `[UNVERIFIED until step 4]` that "was ... seen working on 2026-11-11".
- `04-06-SUMMARY.md`: the allow-placeholder line now says commit 128cf3d added a prose instruction to step 4's "Needs" paragraph; the next-steps bullet says Done.
- The runbook tag question: does it read honestly? Yes in substance. The tag stays because every register row must be cited by a doc test, the sentence beside it now says seen working on 2026-11-11, the U35 register row (runbook line 436) and the record say the same, and U37 keeps its tag because it really is unmeasured. Nothing overclaims. It is awkward in two places that still use the present tense: runbook line 176 says the call scales the whole case "is `[UNVERIFIED until step 4]` (U35)" and U36 likewise, then ends "Seen on 2026-11-11 ... `scale_to_target` was PASS".

### Residual wording (WARNING, none changes a truth)

1. `psse_study_definitions.md:151` still says the layout "stays UNVERIFIED until the laptop shows it working", then two sentences later says `scale_to_target` passed there. a77d5bd fixed line 234 but not this line.
2. `psse_study_definitions.md:234` still says "the combined `scal_2` form" is UNVERIFIED in the `SURFACE` table, but the `scal_2` row of `SURFACE` (psse_api.py:83) is `HIGH`; only `branch_chng_3` is `UNVERIFIED`. Possibly meant as the sink-load form (U11), but the sentence as written disagrees with the table.
3. `psse_api.py:14-16` calls the whole-case `scal_2` "the second such item" (an assumption/unverified one) and in the same sentence says it was shown working. Reads a little oddly.
4. `04-VALIDATION.md` is an unfilled template (`status: draft`, `nyquist_compliant: false`, placeholder rows like `REQ-{XX}`). Not part of any truth, but it is an untidy planning artifact.

### Honestly open items (not verified; none reported as verified)

- U37 (power factor kept): documented (STATUS 4 = 1 is a constant P/Q ratio), not measured.
- The meaning of ierr 5: inferred from three experiments; the manual lists no such code.
- The real case and real targets: unproven. 2.0 s was the 39-bus example with placeholder fractions of its own totals.
- CD-6 (the same lines in every city's copy): the code allows it; Power Systems has not confirmed.
- El Paso's basis (average from EIA-861): awaits Power Systems.
- `scal_2` is obsolete in 36.4 (implemented by `scal_4`); availability going forward is unproven.
- 4 of 32 screened outages gave no result rows in the dry run (`with_results=28`): not investigated.
- The case copy's bytes, size and date were not checked after the probe (the probe never saves by design; its reload check passed), so plan 04-06's truth 3 is only partly evidenced.
- The "18 tests fail with the close removed" mutation count: executor's claim, not re-run.
- The git history exposure itself (see the top): accepted by the user, still present.

### Required Artifacts

| Artifact | Status | Details |
|----------|--------|---------|
| `backend/psse_job/mapping.py` (v2, `Scaling`) | VERIFIED | exists, substantive, read by `study.py` |
| `backend/psse_job/psse_api.py` (`SCALE_LAYOUT`, `read_totals`, `scale_case`, close) | VERIFIED | wired from `study.scale_city_case` and `probe.scale_to_target` |
| `backend/psse_job/study.py` (per-city flow, `combined_failure`, `scaling_record`) | VERIFIED | wired from `prepare_run` and the launcher |
| `backend/psse_job/contingency.py`, `probe.py` | VERIFIED | city id prefix; `scale_to_target` row |
| `docs/data-science/schema/psse_mapping_example.json` | VERIFIED | v2, placeholder, synthetic |
| runbook and study note | VERIFIED with residual wording | pinned by doc tests (pass) |
| `04-06-LAPTOP-RECORD.md` | VERIFIED | no path, host, case name or figure |

### Plans, summaries, record

Six PLAN and six SUMMARY files plus the laptop record. Each SUMMARY's `requirements-completed` equals its PLAN's `requirements` (04-01 SCL-01; 04-02 SCL-02; 04-03 SCL-02, 03, 05; 04-04 SCL-04, 05; 04-05 SCL-06, 02, 04, 05; 04-06 SCL-06). REQUIREMENTS.md lists SCL-01 to SCL-06 as checked and Complete, mapped to Phase 4, no orphan IDs. The record, 04-06-SUMMARY and the runbook register agree (30 PASS 1 FAIL, ierr 5, fix at 5a30c63, U35/U36/U38 seen, U37 documented only). The 04-06-SUMMARY inconsistency from the second pass is gone.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Non-Postgres PSS/E set (api, probe, study, scaling, mapping, contingency, margin, study doc) | `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider` on those eight files | 329 passed | PASS |
| Contract, secret scan, setup doc, launcher, schema doc, run record, task XML | same, seven files | 131 passed, 14 skipped | PASS |
| APIOPT 2 close and surface tests | `psse_api_test.py -k "close or open_read or scale_layout or cannot_run"` | 6 passed | PASS |
| Postgres-backed sets | not re-run; orchestrator reports 319 passed, 1 owner-local skip after a77d5bd's content, and earlier the full sets green | taken from the orchestrator | NOT RE-RUN |
| `psse_results_migration_test.py` | known failure: `core.autocrlf` rewrites a migration to CRLF on this Windows machine; the committed blob hashes correctly; predates this phase | not counted | NOT COUNTED |

### Probe Execution

SKIPPED: the probes need real `psspy` on the licensed laptop. The laptop record is the evidence (truth 7); the fake-psspy probe tests ran inside the suites above.

### Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| SCL-01 | SATISFIED | mapping v2 block, refusal before any psspy call, tests |
| SCL-02 | SATISFIED | `scale_case` and `read_totals` with close, fresh load per city, read-back before solve, no script path |
| SCL-03 | SATISFIED | independence tests |
| SCL-04 | SATISFIED | all four attempted, one failed run, no rows (Postgres tests per orchestrator) |
| SCL-05 | SATISFIED | database, logs, output and current tree; history exposure accepted by the user, not removed |
| SCL-06 | SATISFIED on the laptop record's evidence | `scale_to_target` PASS, four-city dry run exit 0; U37 not measured |

### Anti-Patterns Found

No `TBD`, `FIXME` or `XXX` markers in `psse_api.py`, `study.py`, `mapping.py`, `probe.py` or `contingency.py`. Residual wording items above are WARNING. `deferred-items.md` logs one pre-existing low-severity item, not a phase truth.

### Human Verification Required

None open. The one item from the second pass (history exposure) is resolved by the recorded user decision, with the caveat on attribution stated above.

### Gaps Summary

No gap blocks the phase goal. The engineering goal is met and tested; the tree is clean of case totals and city figures; history is not clean and that is accepted by the user's recorded decision. The residual items are wording and the honestly open list.

---

_Verified: 2026-11-11_
_Verifier: Claude (gsd-verifier)_
