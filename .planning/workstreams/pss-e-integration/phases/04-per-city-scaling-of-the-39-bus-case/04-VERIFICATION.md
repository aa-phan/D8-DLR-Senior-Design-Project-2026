---
phase: 04-per-city-scaling-of-the-39-bus-case
verified: 2026-11-11T23:00:00Z
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
  - "backend/tests/psse_phase4_validation_test.py"
  - "backend/tests/psse_probe_test.py"
  - "backend/tests/psse_scaling_test.py"
  - "docs/data-science/decisions/psse_laptop_runbook.md"
  - "docs/data-science/decisions/psse_laptop_setup.md"
  - "docs/data-science/decisions/psse_study_definitions.md"
  - "docs/data-science/schema/psse_mapping_example.json"
covered_digest: "v3:sha256:f5b0deceb555905143a48dfa8c56dd6ddd636468d261e40e57b5e894d3271873"
behavior_unverified: 0
overrides_applied: 1
overrides:
  - must_have: "No such figure (base case totals) appears in git history"
    reason: "The totals of PSS/E's public 39-bus example case remain in pushed commits 6e59341 and 1f60eb5. The user decided to accept the exposure and not rewrite history; no city target or El Paso figure was ever committed (per the record). The history still contains the totals. The rule going forward is no city figure and no case total in the tree."
    accepted_by: "the user, as recorded in 04-CONTEXT.md under 'Decisions made after execution (2026-11-11, the user)'"
    accepted_at: "2026-11-11"
re_verification:
  previous_status: passed
  previous_score: 7/7
  gaps_closed:
    - "Residual stale wording from the third pass: the psse_study_definitions.md line saying the layout stays UNVERIFIED until the laptop, the line calling the combined scal_2 form UNVERIFIED in the SURFACE table, the psse_api.py 'second such item' phrasing"
    - "04-VALIDATION.md was an unfilled template; it is now filled (validated, nyquist_compliant true, SCL-06 manual-only) with two new tests"
  gaps_remaining: []
  regressions: []
---

# Phase 4: Per-city scaling of the 39-bus case - Verification Report (final pass)

**Phase Goal:** The job runs the same study once per city on its own fresh copy of the same 39-bus network, scaled to that city's load and generation targets, so the four cities never share a solve. The targets live in the private mapping (never in git); the job applies them with its own scaling call and never executes the recorded `.idv` scripts.
**Verified:** 2026-11-11
**Status:** passed (one accepted deviation, stated first below)
**Re-verification:** Yes, fourth pass

## Read this first: git history still contains the totals

**The pushed history of `feature/pss-e-integration` still contains the base case totals of PSS/E's public 39-bus example case.** They are in `04-CONTEXT.md` at 6e59341 and 1f60eb5 and in `04-RESEARCH.md` at 1f60eb5. History was **not rewritten and is not clean**. The user chose to accept that; this report records the exposure as accepted, not removed. A later commit cannot take figures out of earlier ones.

So "never in git" is true of the current tree and the working tree, and false of the repository's history, by the user's recorded choice.

The decision is written in `04-CONTEXT.md` (lines 37 to 38, section "Decisions made after execution (2026-11-11, the user)") and is mirrored as accepted risk AR-1 in `04-SECURITY.md`. Limit I cannot remove: I did not see the conversation, so the attribution to the user rests on the document's own heading and the requester's statement. If the user did not make that decision, truth 6b reverts to UNCERTAIN and the status to `human_needed`. Also, the claim "no city target or El Paso figure was ever committed" is supported by scans of the base-case totals and of the El Paso method, not by a scan of every historical blob for every possible target value (the targets are unknown to this verifier).

## "Never in git": current tree and working tree, searched this pass

Method (patterns in words only; no figure is written in this report): I extracted the three base-case totals programmatically from the pushed historical blob, so no figure was typed or printed, and built these forms for each: plain digits, with a comma thousands separator, with a space, with a dot separator, and rounded "thousand", "k", "GW" and "GVA" phrasings. I also searched for the spelled-out "thousand" phrasing next to a megawatt or megavar unit. I scanned every file in the working tree except `.git`, `.venv` and `node_modules`: 1161 files, including ignored and untracked ones, across backend, docs, supabase, all of `.planning`, data and the rest. `git status` was clean at the start.

Results (hit counts):
- Base-case total patterns: 6 hits, 0 in backend, 0 in docs, 0 in supabase, 5 in one unrelated `.planning` file of another workstream, 1 in a weather-station CSV. I checked each by masked context: the five are a commit-hash prefix, the one is four digits inside a longer decimal. None is a case total.
- Spelled-out "thousand" plus unit phrasing: 2 hits, both inside the previous copy of this verification file, which this report replaces (0 remain after the overwrite).
- City figures and El Paso: I do not know the real targets, so I checked for what would carry them. Files naming the scaling keys are code, tests, docs and planning text; the only data file is `psse_mapping_example.json`, which has `"placeholder": true`, fake five-digit buses starting with 9 and a note saying the targets are synthetic. There is no mapping file anywhere else in the tree (tracked or ignored). El Paso lines with long numbers are per-conductor amp ratings, dates and a Mountain-time note; the El Paso scaling proposal states the method only, with the sales table's year, a utility identifier and hours-per-year, no load figure.
- Info only: `04-CONTEXT.md` keeps a "power factor about 0.90" ratio. It is a ratio, not a total, and not what the rule forbids.

Limit: a search by pattern proves absence of the known case totals; for city targets it proves absence of a private mapping file and of any scaling-key assignment outside the synthetic example, not absence of every number a human might call a target.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | One fresh copy of the case per city, each city solved on its own (SCL-02, SCL-03) | VERIFIED | `study.prepare_city_base` (study.py:435-446) calls `api.load_case(index.case_path)` per city, then `scale_city_case`, the city's own rating, the solve. `psse_scaling_test.py` independence and tracer tests pass. |
| 2 | Targets live in the mapping (schema v2: `load_mw`, `gen_mw`, `basis`) and are refused before any PSS/E call when missing or invalid (SCL-01) | VERIFIED | `mapping.py` (`Scaling`, closed key set at :55, positive-finite check at :143-155); `psse_mapping_test.py` passes; committed example is v2 and placeholder. |
| 3 | The job applies targets with its own scaling call and never runs a recorded `.idv` or any script (SCL-02, CD-2) | VERIFIED | `psse_api.scale_case` is one `scal_2` call through the surface table. Searching `backend/psse_job` for `idv`, `runrspnsfile`, `runiplanfile`, `runpy`, `os.system`, `exec(`, `eval(` and `subprocess` finds only the `git rev-parse` call in `run_record.py` and the study.py docstring saying the job never runs an `.idv`. `test_surface_cannot_run_a_script` passes. |
| 4 | A failing city: all four attempted, one failed run naming every city, no result rows (SCL-04) | VERIFIED | `combined_failure` and the collecting loop in study.py; scaling failure and budget tests pass; the new database-free `test_one_refused_city_writes_no_result_row_for_any_city` passes and asserts no result insert and one run insert with every city named. Postgres-backed study job tests were run by the orchestrator, not by me. |
| 5 | Result rows unique and attributable per city, no schema change; no city figure in the database, a log line, error text or dry-run output (SCL-05) | VERIFIED | `scaling_record` returns basis and method only; contingency ids carry the city prefix; figure-free tests pass, including the new `test_converged_run_logs_and_stores_no_scaling_figure`, which asserts rows were written (not vacuous), then asserts no synthetic target text in captured logs or stored parameters. |
| 6a | No city target, El Paso figure or case total in the current git tree | VERIFIED | Search above; `secret_scan_test.py` passes. |
| 6b | No such figure in git history | PASSED (override) | Not true: the totals are in 6e59341 and 1f60eb5 (pushed). Accepted, not rewritten, by the user's recorded decision of 2026-11-11 (`04-CONTEXT.md`, AR-1 in `04-SECURITY.md`). |
| 7 | Probe row, scaling layout and a four-city dry run proven on the laptop's 39-bus case (SCL-06) | VERIFIED (laptop record only; not re-runnable here) | `04-06-LAPTOP-RECORD.md`: positions match the installed help; first probe had one failure (ierr 5, open totals read); fix at 5a30c63; second probe 0 FAIL exit 0 with `scale_to_target` PASS; four-city dry run exit 0, 4 dispatch rows, 4 margin rows, `validation: ok`, 2.0 s, nothing written. The record holds no path, host, case name, bus number or figure. |

**Score:** 7/7 truths verified, one by a recorded user override (6b). `behavior_unverified: 0`.

### Commit 5a30c63 (the APIOPT 2 close fix)

`git merge-base --is-ancestor 5a30c63 HEAD` succeeds. `psse_api.read_totals` (psse_api.py:553-) issues the read, returns or raises on a failed read without a close, calls `_close_totals_read` (psse_api.py:537) right after a successful read and before any shape check, and `SCALE_LAYOUT.apiopt_close = 2` (line 111). The close uses all-sentinel arguments so nothing is scaled, and a failed close raises a figure-free `_CLOSE_FAILED`. Five named tests exist and pass: `test_read_totals_closes_every_read_so_reads_can_follow_each_other`, `test_fake_scal_2_models_the_open_read_state`, `test_read_totals_close_failure_raises_without_figures`, `test_failed_read_issues_no_close`, `test_surface_cannot_run_a_script`; `psse_scaling_test.py` pins the per-city call order including the close. The "18 tests fail with the close removed" count is the executor's claim; I did not run that mutation.

### Wording check (the five requested items)

1. **`psse_api.py` docstrings:** the module docstring (lines 14-16), `read_totals` and `scale_case` say the layout was shown working on the laptop on 2026-11-11. The old "second such item" phrasing is gone (search finds nothing). Reads honestly.
2. **`psse_study_definitions.md`:** the per-city section now says the layout "was UNVERIFIED until the laptop showed it working on 2026-11-11", and the "what the fake does not prove" list now says the combined `scal_2` form is HIGH in `SURFACE` and only `branch_chng_3` is UNVERIFIED, matching `psse_api.py`. Both third-pass contradictions are fixed.
3. **Runbook step 4:** the U35/U36 tags remain (the doc tests require every register row to be cited) but each sits in a past-tense sentence ("was `[UNVERIFIED until step 4]` ... was seen working on 2026-11-11"); register rows U35, U36, U38 say "Seen on PSS/E 36.4 on 2026-11-11"; U37 keeps its tag as documented, not measured. Reads honestly.
4. **`04-VALIDATION.md`:** filled, `status: validated`, `nyquist_compliant: true`, SCL-01 to SCL-05 mapped to named tests that exist and pass, SCL-06 manual-only with the laptop record as evidence. The two new tests exist (checked above).
5. **`04-SECURITY.md`:** 25 threats, 25 closed, `threats_open: 0`, AR-1 is the history exposure. It states it is an automated audit, not a human review, and lists what it could not see. Consistent with this report. Its own observation that earlier reports used leading digits of the totals is why this report describes patterns in words only.

### Residual contradictions with the laptop record (WARNING, none changes a truth)

These predate Phase 4's own work (Phase 3 wording) and were not in the three stale items, but they still disagree with the laptop records:
1. `psse_laptop_runbook.md:6` says "nothing in it has been run on the laptop" and `psse_laptop_setup.md:6` says "nobody has followed this guide on the laptop yet". The Phase 3 and Phase 4 laptop records show steps run on the laptop (3 and 4 in two sessions, 5, and one live write on 2026-11-11).
2. U11 (the combined `scal_2` form) is recorded as cleared in `03-07-LAPTOP-RECORD.md` ("`scale_load` PASS"), and the Phase 4 record also shows `scale_load` passing, but runbook line 176 and `psse_laptop_setup.md:162` still tag it `[UNVERIFIED until step 4]` in the present tense and its register row (runbook line 412) carries no "seen" note. Likewise `psse_laptop_setup.md:162` still says "that the layout works is `[UNVERIFIED until step 4]` (U35)" in the present tense, while the runbook register says U35 was seen. The guide was not touched by commit 30c1ef6.
3. `psse_laptop_setup.md` line 6 and 162 are what a reader of the guide sees first, so a reader could conclude the scaling layout is still unproven. The register, the runbook step 4 text, the code and the records say otherwise.

### Records agree with each other (checked)

- Plans and summaries: for each of the six plans, `requirements-completed` in the SUMMARY equals `requirements` in the PLAN (SCL-01; SCL-02; SCL-02, 03, 05; SCL-04, 05; SCL-06, 02, 04, 05; SCL-06). REQUIREMENTS.md lists SCL-01 to SCL-06 checked and Complete, mapped to Phase 4, no orphan IDs.
- `04-06-LAPTOP-RECORD.md`, `04-06-SUMMARY.md`, runbook register and `04-VALIDATION.md` agree on the first probe (one failure, ierr 5), the fix at 5a30c63, the second probe (0 FAIL), the dry run (exit 0, four dispatch rows) and on U37 being documented not measured.
- The later live write is recorded only in the Phase 3 record (`03-07-LAPTOP-RECORD.md`, step 9): one permanent run read back with 1 run row, 4 dispatch rows, 4 margin rows and 205 contingency rows, 32 screened with 32 having results, using a private placeholder-free version 2 mapping kept outside the repository. The Phase 4 record is silent about it and still says the real case and real targets are unproven by Phase 4 itself, which is accurate. I did not look for the private mapping. The Phase 3 record shows no figure.
- Note on one open item: the Phase 4 dry run had 28 of 32 screened outages with results; the later live write had 32 of 32 with a different mapping. That makes "expected for placeholder lines" plausible but it is not established; the item stays open.

### Honestly open items (not verified; none reported as verified)

- U37 (power factor kept): documented (STATUS 4 = 1 is a constant P/Q ratio), not measured.
- The meaning of ierr 5: inferred from three experiments and one probe pass; the manual lists no such code.
- The real case and real targets: unproven by Phase 4 itself (the dry run used the public example case with placeholder fractions of its own totals; the Phase 3 live write used real targets on the same public example case).
- CD-6 (the same lines in every city's copy): the code allows it; Power Systems has not confirmed.
- El Paso's basis (average load from EIA-861): awaits Power Systems.
- `scal_2` is obsolete in 36.4 (implemented by `scal_4`); availability going forward is unproven.
- The case copy's size and date were not checked after the probe (the probe never saves by design; its reload check passed), so plan 04-06's truth 3 is only partly evidenced.
- The "18 tests fail with the close removed" count and the other executors' mutation counts: not independently re-run.
- 4 of 32 screened outages gave no result rows in the Phase 4 dry run: not investigated.
- The git history exposure of the public example case's totals: accepted by the user, still present, not removed.
- The security audit is automated; no human security review. The Postgres-backed tests behind SCL-04 and SCL-05 were run by the orchestrator, not by me.

### Required Artifacts

| Artifact | Status | Details |
|----------|--------|---------|
| `backend/psse_job/mapping.py` (v2, `Scaling`) | VERIFIED | exists, substantive, read by `study.py` |
| `backend/psse_job/psse_api.py` (`SCALE_LAYOUT`, `read_totals`, `scale_case`, close) | VERIFIED | wired from `study.scale_city_case` and `probe.scale_to_target` |
| `backend/psse_job/study.py` (per-city flow, `combined_failure`, `scaling_record`) | VERIFIED | wired from `prepare_run` and the launcher |
| `backend/psse_job/contingency.py`, `probe.py` | VERIFIED | city id prefix; `scale_to_target` row |
| `backend/tests/psse_phase4_validation_test.py` | VERIFIED | two tests, both pass, neither vacuous |
| `docs/data-science/schema/psse_mapping_example.json` | VERIFIED | v2, placeholder, synthetic |
| runbook, study note | VERIFIED | pinned by doc tests (pass); step 4 and register honest |
| `psse_laptop_setup.md` | WARNING | status banner and one step still say unproven (see residual list) |
| `04-06-LAPTOP-RECORD.md`, `04-VALIDATION.md`, `04-SECURITY.md` | VERIFIED | consistent, figure-free |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| PSS/E non-Postgres set (api, probe, study, scaling, mapping, contingency, margin, study doc, contract, phase 4 validation) | `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider` on those ten files | 341 passed | PASS |
| Launcher, setup doc, secret scan, rehearsal, laptop modes | same, five files | 54 passed, 18 skipped (Postgres-backed or owner-local) | PASS |
| Run record, schema doc | same, two files | 69 passed | PASS |
| APIOPT 2 close tests | five named tests, selected by `-k` | 5 passed | PASS |
| Postgres-backed sets | not re-run, per instruction | orchestrator reports green except the known owner-local secret-scan skip | NOT RE-RUN |
| `psse_results_migration_test.py` | known failure: `core.autocrlf` rewrites a migration to CRLF on this Windows machine; the committed blob hashes correctly; predates this phase | not counted | NOT COUNTED |

### Probe Execution

SKIPPED: the probes need real `psspy` on the licensed laptop. The laptop record is the evidence (truth 7); the fake-psspy probe tests ran inside the suites above.

### Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| SCL-01 | SATISFIED | mapping v2 block, refusal before any psspy call, parametrized refusal tests |
| SCL-02 | SATISFIED | `scale_case`, `read_totals` with close, fresh load per city, read-back before solve, no script path |
| SCL-03 | SATISFIED | independence tests in `psse_scaling_test.py` |
| SCL-04 | SATISFIED | all four attempted, one failed run, no rows (database-free test by me; Postgres tests per orchestrator) |
| SCL-05 | SATISFIED | rows, logs, output and current tree; history exposure accepted by the user, not removed |
| SCL-06 | SATISFIED on the laptop record's evidence | `scale_to_target` PASS, four-city dry run exit 0; U37 not measured |

### Anti-Patterns Found

No `TBD`, `FIXME` or `XXX` markers in the phase's source files. Residual wording items above are WARNING. `deferred-items.md` logs one pre-existing low-severity item (an oversized integer in the mapping parser raising `OverflowError`), not a phase truth.

### Human Verification Required

None open. The history-exposure item is resolved by the recorded user decision, with the attribution caveat stated above.

### Gaps Summary

No gap blocks the phase goal. The engineering goal is met and tested; the current tree and working tree are clean of the case totals and hold no city or El Paso figure; history is not clean and the user accepted that. Remaining items are the stale present-tense banner and tag in the laptop setup guide (WARNING) and the honestly open list.

---

_Verified: 2026-11-11_
_Verifier: Claude (gsd-verifier)_
