---
phase: "04"
slug: "forecast-correction-experiment-follow-up-audit-data-provenan"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: true
wave_0_complete: false
created: "2026-09-30"
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (project-wide) |
| **Config file** | `/Users/aphan/Senior_Design/pytest.ini` |
| **Quick run command** | `.venv/bin/python3 -m pytest -q backend/tests/forecast_experiment_audit_test.py` |
| **Full suite command** | `.venv/bin/python3 -m pytest -q` |
| **Estimated runtime** | ~10–40 s quick (grows with the audit file); ~50 s full suite (measured 49.17 s at planning time) |
| **Python invocation** | `.venv/bin/python3` from the repo root; module imports use `PYTHONPATH=backend` |

**Pre-existing baseline — not a regression this phase introduces.** The full suite measured
**641 passed / 23 failed in 49.17 s** at planning time (2026-09-30). All 23 failures are in
`backend/tests/corridor_discretization_test.py`, predate Phase 3 entirely, and are documented in
`.planning/workstreams/ml-modeling/phases/03-ampacity-forecast-correction-experiment-compare-persistence/deferred-items.md`
and `.planning/WINDOWS.md` (kind: deviation, phase 03). Every plan in this phase states this baseline
in its full-suite `<fails_when>` clause; no pass/fail claim in this phase is meaningful without it.

**Existing files this phase must not regress:** `backend/tests/forecast_experiment_test.py`
(84 passed at planning time) and `backend/tests/thermal_model_test.py` — both belong to modules this
phase audits but never modifies. Plan 04-01 gates the first at ≥ 84; Plan 04-05 runs the second
alongside its own file, because a failure there would mean the physics was modified rather than
measured.

---

## Sampling Rate

- **After every task commit:** `.venv/bin/python3 -m pytest -q backend/tests/forecast_experiment_audit_test.py`
- **After every plan wave:** `.venv/bin/python3 -m pytest -q`, compared against the 23-failure / 641-pass baseline
- **Before `/gsd-verify-work`:** Full suite green modulo the 23-failure baseline, and every named gate token printed
- **Max feedback latency:** 60 seconds

**Additive-gate discipline unique to this phase.** Because this is an audit phase whose central risk
is silently touching frozen evidence, every task also runs a structural gate that is not a test:
`git diff --quiet HEAD -- <frozen production modules>` plus `git diff --quiet HEAD -- <frozen decision
record> <Phase 3 phase directory>`. These are as load-bearing as the unit tests and are listed per
task below.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Decision | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|----------|------------|-----------------|-----------|-------------------|-------------|--------|
| 4-01-01 | 01 | 1 | D-01 | T-04-01-01 / -03 / -04 / -06 | Frozen-test-window rows cannot enter any audit computation; no audit claim ships without a `file:line` citation | unit + structural | `pytest -q backend/tests/forecast_experiment_audit_test.py` · `FROZEN_GUARD_OK` · `BOUNDARY_WINDOW_DEPENDENCE_OK` · `PROVENANCE_FINDING_OK` · `FROZEN_SOURCES_UNTOUCHED_OK` | ❌ W0 | ⬜ pending |
| 4-01-02 | 01 | 1 | D-01, D-02 | T-04-01-02 / -05 / -07 | The harness's split-carrying runner entry points are never invoked; a zero-row basis is reported as zero | unit + integration + structural | `MANIFEST_BUILT_OK` · `MANIFEST_SHAPE_OK` · `AUDIT_BASES_SECTION_OK` · `MANIFEST_IGNORED_AND_SOURCES_UNTOUCHED_OK` · `pytest -q` | ❌ W0 | ⬜ pending |
| 4-01-03 | 01 | 1 | D-02 | T-04-01-05 | A human sees the measured row counts before any claim is written from them | manual (blocking checkpoint) | n/a — `checkpoint:human-verify`, manifest + Audit-bases section reviewed | n/a | ⬜ pending |
| 4-02-01 | 02 | 2 | D-01 | T-04-02-01 / -02 / -07 | The calibration gate's claim type is stated precisely; every frame column has exactly one time reference and an unknown column breaks loudly | unit + structural | `pytest -q …audit_test.py` · `CALIBRATION_CLAIM_FINDING_OK` · `TIME_REFERENCE_PARTITION_OK` · `D01_SECTION_GROWING_OK` · `FROZEN_SOURCES_UNTOUCHED_OK` | ❌ W0 | ⬜ pending |
| 4-02-02 | 02 | 2 | D-01 | T-04-02-03 / -04 / -07 | The leakage probe is re-run on real rows in both callable shapes with a sabotaged arm proving power | unit + integration + structural | `PROBE_RERUN_RAN_OK` · `PROBE_RERUN_SHAPE_OK` · `PROBE_FINDING_PUBLISHED_OK` · `FROZEN_SOURCES_UNTOUCHED_OK` | ❌ W0 | ⬜ pending |
| 4-02-03 | 02 | 2 | D-01 | T-04-02-05 / -06 / -07 | Label timing, split boundaries and lag-offset integrity are measured, not read; every D-01 bullet gets a published disposition | unit + integration + structural | `D01_MEASUREMENTS_OK` · `D01_SECTION_COMPLETE_OK` · `FROZEN_SOURCES_UNTOUCHED_OK` · `pytest -q` | ❌ W0 | ⬜ pending |
| 4-03-01 | 03 | 3 | D-02 | T-04-03-03 / -04 | The block bootstrap reduces to a method-matched i.i.d. percentile interval at block length one and widens only under dependence | unit + structural | `pytest -q …audit_test.py` · `BLOCK_BOOTSTRAP_OK` · `FROZEN_SOURCES_UNTOUCHED_OK` | ❌ W0 | ⬜ pending |
| 4-03-02 | 03 | 3 | D-02 | T-04-03-01 / -02 / -05 / -06 / -07 / -09 | Fit rows strictly predate scored rows; the oracle is never a baseline; persisted residuals match the reported error metrics | unit + integration + structural | `ABLATION_RUN_OK` · `ABLATION_REPORT_SHAPE_OK` · `FRESH_BRANCH_OK` · `FROZEN_SOURCES_UNTOUCHED_OK` · `pytest -q` | ❌ W0 | ⬜ pending |
| 4-03-03 | 03 | 3 | D-02 | T-04-03-06 | A human approves how strongly the replication's evidence may be stated before prose is written | manual (blocking checkpoint) | n/a — `checkpoint:human-verify`, both ablation reports reviewed | n/a | ⬜ pending |
| 4-03-04 | 03 | 3 | D-02 | T-04-03-06 / -07 / -08 | Every published number is traceable to a measured report; no ABLATION number is framed as confirmation | doc-gate + structural | `D02_SECTION_OK` · `D02_NUMBERS_TRANSCRIBED_OK` · `DOC_ONLY_TASK_OK` | n/a | ⬜ pending |
| 4-04-01 | 04 | 4 | D-03, D-04 | T-04-04-05 / -07 / -08 / -09 | The low-wind bin boundary is the conductor's own measured convection crossover, verified on both sides; the physics is untouched | unit + structural | `pytest -q …audit_test.py` · `OVERRATING_PROFILE_OK` · `CONVECTION_CROSSOVER_OK` · `FROZEN_SOURCES_UNTOUCHED_OK` | ❌ W0 | ⬜ pending |
| 4-04-02 | 04 | 4 | D-03 | T-04-04-02 / -03 / -04 / -06 | Calibration and its own check never share rows; a target rate is never published as an achieved rate; pinball loss is the library metric | unit + integration + structural | `OVERRATING_RUN_OK` · `OVERRATING_REPORT_SHAPE_OK` · `PINBALL_SANITY_OK` · `FROZEN_SOURCES_UNTOUCHED_OK` · `pytest -q` | ❌ W0 | ⬜ pending |
| 4-04-03 | 04 | 4 | D-03 | T-04-04-01 | The reanalysis-scope limitation precedes the first number and repeats beside every rate table; no number is called a safety margin | doc-gate + structural | `D03_SECTION_OK` · `D03_NUMBERS_TRANSCRIBED_OK` · `DOC_ONLY_TASK_OK` | n/a | ⬜ pending |
| 4-05-01 | 05 | 5 | D-04 | T-04-05-08 / -09 | Low-wind behaviour is finite, monotone and continuous across the crossover; the seam's bit-identity is reproduced independently and proven non-trivial | unit + structural | `pytest -q …audit_test.py …thermal_model_test.py` · `LOW_WIND_SENSITIVITY_OK` · `SEAM_BIT_IDENTITY_OK` · `PHYSICS_UNTOUCHED_OK` | ❌ W0 | ⬜ pending |
| 4-05-02 | 05 | 5 | D-04 | T-04-05-01 / -02 / -03 / -04 / -05 / -10 | The frozen Expectation and Measured results stay byte-identical; no committed line is deleted or reworded anywhere | doc-gate + structural | `EXPECTATION_AND_MEASURED_BYTE_IDENTICAL_OK` · `FROZEN_RECORD_APPEND_ONLY_OK` · `D04_AMENDMENT_OK` · `NO_CODE_OR_PHASE3_DIFF_OK` | n/a | ⬜ pending |
| 4-05-03 | 05 | 5 | D-04 | T-04-05-06 / -07 / -10 | No established/unique/proven-winner or universal-ceiling language survives; no replication is upgraded to a confirmation | doc-gate + structural | `CORRECTED_VERDICT_OK` · `FROZEN_RECORD_SETTLED_OK` · `DOC_ONLY_TASK_OK` · `pytest -q` | n/a | ⬜ pending |
| 4-06-01 | 06 | 6 | D-05 | T-04-06-01 / -02 / -03 / -05 | Ablation feature subsets are disjoint, complete and dropped rather than zeroed; fit rows strictly predate scored rows | unit + integration + structural | `pytest -q …audit_test.py` · `ABLATION_FEATURES_RUN_OK` · `ABLATION_FEATURES_SHAPE_OK` · `FROZEN_SOURCES_UNTOUCHED_OK` · `pytest -q` | ❌ W0 | ⬜ pending |
| 4-06-02 | 06 | 6 | D-05 | T-04-06-04 / -05 / -06 / -07 / -11 | The data contract names every field; the fallback ladder ends in a known-safe path; the horizon question is left open | doc-gate + structural | `D05_SECTION_OK` · `AUDIT_RECORD_COMPLETE_OK` · `DOC_ONLY_TASK_OK` | n/a | ⬜ pending |
| 4-06-03 | 06 | 6 | D-05 | T-04-06-08 / -09 / -10 | No non-target ROADMAP phase entry is modified; every success criterion gets a disposition; the AI-use disclosure is filed | doc-gate + structural | `ROADMAP_SCOPED_EDIT_OK` · `ACKNOWLEDGEMENTS_OK` · `DOC_ONLY_TASK_OK` · `pytest -q` | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Decision IDs substitute for requirement IDs.** No FCST/ANOM requirement ID applies to this phase —
`REQUIREMENTS.md` shows FCST-01/02 and ANOM-01/02 already Complete against Phases 1 and 2. This is a
methodology/audit investigation, mirroring Phase 3's own no-new-requirement-ID reasoning; `04-CONTEXT.md`'s
five locked decisions (D-01 … D-05) are the scope, exactly as Phase 3's plans used
`requirements: [D-02, D-03, D-04]`.

---

## Wave 0 Requirements

- [ ] `backend/tests/forecast_experiment_audit_test.py` — new file, created by Plan 04-01 Task 1 and
      extended by every subsequent plan. Network-free by construction: every function it exercises is a
      pure transform over in-memory frames, so no fetch monkeypatching is needed, and any test that
      could touch disk redirects `config.FORECAST_EXPERIMENT_CACHE_DIR` to a pytest `tmp_path`.
      Cumulative floors gated per plan: ≥ 10 (04-01 T1), ≥ 14 (04-01 T2), ≥ 20 / 25 / 32 (04-02),
      ≥ 42 / 50 (04-03), ≥ 60 / 70 (04-04), ≥ 78 (04-05), ≥ 86 (04-06).
- [ ] No shared `conftest.py` needed — the analog file (`backend/tests/forecast_experiment_test.py`)
      uses module-level plain-assert functions with no test classes and no shared fixture module, and
      this phase follows the same convention.
- [ ] Framework install: none — `pytest` is already present and `pytest.ini` already exists.
- [ ] Library install: none — `numpy` 2.4.3, `pandas` 2.3.3, `scipy` 1.17.1 and `scikit-learn` 1.9.1
      were all verified present in `.venv` during research, and 04-RESEARCH.md's Package Legitimacy
      Audit is deliberately empty because this phase installs nothing.

**Data prerequisite, not a test-framework gap.** Plan 04-01 Task 2 carries a `<precondition>` on
network reachability to `archive-api.open-meteo.com` and `previous-runs-api.open-meteo.com`, because
`data/experiment/` is git-ignored and does not exist on a fresh clone. Every later plan's real-data
task depends on that cache and carries its own `<precondition>` naming the idempotent rebuild path.
If the network is unreachable at execution time, 04-RESEARCH.md's permitted fallback is a
synthetic-only methodology track — which is a scope reduction on D-02 and D-03 and is therefore a
decision for Plan 04-01's blocking human checkpoint, never an executor's silent substitution.

---

## Manual-Only Verifications

| Behavior | Decision | Why Manual | Test Instructions |
|----------|----------|------------|-------------------|
| How much real data actually exists on each basis, and whether that is acceptable | D-02 | The ABLATION and FRESH row counts determine what the phase may honestly claim. A zero-row FRESH basis is the expected honest answer at this calendar date and is not a failure — but whether to proceed on that footing, defer the confirmation run, or reduce D-02/D-03 to a synthetic-only track is a scope decision. | Plan 04-01 Task 3 checkpoint: open `data/experiment/audit_basis_manifest.json` and the record's `## Audit bases` section; check the four numbers the checkpoint enumerates; approve or name the unacceptable one. |
| How strongly the ABLATION replication's evidence may be stated | D-02 | Whether the replication corroborates, disagrees with, or is inconclusive about the frozen record's candidate ordering is a judgement about evidence strength — the exact judgement this phase exists to get right. It should not be an executor's call. | Plan 04-03 Task 3 checkpoint: open both `data/experiment/audit_ablation_report_<CORRIDOR>.json` files; check the candidate ordering, the block-versus-i.i.d. interval widths, the block-length stability verdict and the fresh-basis branch; approve a framing. |
| Whether the audit's prose findings are genuinely grounded rather than paraphrases of the frozen record | D-01, D-04 | Citation counts and word floors are automatable and are gated; whether a cited claim is the *right* claim is not. | End-of-phase read of `docs/data-science/decisions/forecast_correction_followup_audit.md`: spot-check three `file:line` citations against the named lines, and confirm the corrected verdict names a recommendation you could disagree with. |

Everything else in this phase has automated verification. Notably, the two doc-heavy waves (04-05 and
04-06) are gated by structural document checks rather than left to review: byte-identity extraction of
the frozen record's two protected sections, a whole-file line-subsequence check proving the amendment
is append-only, a per-phase ROADMAP section comparison proving the edit was scoped, and keyword/table
/word-floor checks per required element of each published section.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies — every task carries at least one
      runnable `<automated>` with a `<fails_when>` sibling naming an observable signal; the two
      `checkpoint:human-verify` tasks are the only non-automated blocks and both are listed under
      Manual-Only Verifications above.
- [x] Sampling continuity: no 3 consecutive tasks without automated verify — the longest run of
      non-unit-tested tasks is one (each doc task is bracketed by unit-tested tasks and carries its own
      structural doc gate).
- [x] Wave 0 covers all MISSING references — the single missing test file is created by Plan 04-01
      Task 1, the first task of the first wave, and every later plan's floor is stated cumulatively.
- [x] No watch-mode flags — every command is a one-shot `pytest -q` or a `python3 -c` assertion script.
- [x] Feedback latency < 60s — quick run ~10–40 s, full suite measured 49.17 s.
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** approved 2026-09-30 (planning pass; per-task statuses flip from ⬜ to ✅ during
execution, and `status:` moves from `draft` to `validated` by `/gsd-validate-phase` §6).
