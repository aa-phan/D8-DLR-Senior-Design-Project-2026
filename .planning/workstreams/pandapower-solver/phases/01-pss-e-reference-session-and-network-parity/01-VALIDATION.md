---
phase: "01"
slug: "pss-e-reference-session-and-network-parity"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-11-16"
---

# Phase 01 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Seeded from `01-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 |
| **Config file** | `pytest.ini` (`pythonpath = backend`) |
| **Quick run command** | `.venv/bin/python -m pytest -q -p no:cacheprovider -rs backend/tests/private_data_guard_test.py backend/tests/psse_session_test.py backend/tests/psse_session_reference_test.py backend/tests/psse_session_settings_test.py backend/tests/pandapower_raw_test.py backend/tests/pandapower_network_test.py backend/tests/pandapower_parity_test.py backend/tests/pandapower_compare_test.py backend/tests/pandapower_ingest_test.py backend/tests/pandapower_cli_test.py -k "not owner_local"` |
| **Full suite command** | `.venv/bin/python -m pytest -q -p no:cacheprovider` |
| **Estimated runtime** | ~10 seconds (quick); full suite not measured |

CI does not run the full suite, so the owner runs these locally before any push. Tests that need pandapower use `pytest.importorskip("pandapower")`.

---

## Sampling Rate

- **After every task commit:** Run the quick command, limited to the files the task touched
- **After every plan wave:** Quick command in full plus `backend/tests/secret_scan_test.py backend/tests/psse_contract_test.py backend/tests/psse_api_test.py backend/tests/psse_study_test.py` (existing job untouched)
- **Before `/gsd-verify-work`:** Full suite must be green, then the owner-run real-data checkpoint
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

Task IDs are filled in by the planner and checker; the requirement-to-test map below is the contract.

| Requirement | Tasks | Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|-------|----------|-----------|-------------------|-------------|--------|
| PSE-04 | 01-01 T1, T2; 01-09 T2, T3; 01-10 T2; 01-11 T2 | `data/private/` ignored; no tracked path under it; shape scan clean; planted placeholder flagged; staged mode scans the index; scanner never prints the match; fixtures generated into `tmp_path`; CLI outputs only under data/private | unit | `.venv/bin/python -m pytest -q -rs backend/tests/private_data_guard_test.py backend/tests/secret_scan_test.py -k "not owner_local and not real_project_values"` | ❌ W0 (01-01) | ⬜ pending |
| PSE-01 | 01-02 T1, T2; 01-04 T3 | Session end to end against `FakeSessionPsspy`: zip members equal manifest, hashes match, work folder and mapping copy deleted; summary vocabulary-only; call gate + AST import gate; no network; filesystem snapshot; per-section isolation; interrupt and collision edges; thin wrapper | integration | `.venv/bin/python -m pytest -q -rs backend/tests/psse_session_test.py backend/tests/psse_session_settings_test.py` | ❌ W0 (01-02) | ⬜ pending |
| PSE-02 | 01-04 T1, T2; 01-08 T2, T3 | `settings.json` keys read, measured or unavailable with a reason; fingerprints and scaling experiments recorded; three scaling details classified yes/no/inconclusive by the offline analyser with tested thresholds | unit | `.venv/bin/python -m pytest -q -rs backend/tests/psse_session_settings_test.py backend/tests/pandapower_compare_test.py` | ❌ W0 (01-04, 01-08) | ⬜ pending |
| PSE-03 | 01-03 T1, T2 | Reference holds base solve per city plus one record per `select_outages` outage; non-converged and islanded outages recorded; margin limit-point records; city isolation; no .sav left | integration | `.venv/bin/python -m pytest -q -rs backend/tests/psse_session_reference_test.py` | ❌ W0 (01-03) | ⬜ pending |
| NET-01 | 01-06 T1, T2, T3 | Parser/builder fail closed on each refusal case; bus index = PSS/E number (+90000 offset); `from-to-ckt` names; round trip equals case39 to 1e-9 | unit | `.venv/bin/python -m pytest -q -rs backend/tests/pandapower_raw_test.py backend/tests/pandapower_network_test.py` | ❌ W0 (01-06) | ⬜ pending |
| NET-02 | 01-07 T1, T2, T3; 01-09 T1 | Parity zero on clean build; each single mutation yields exactly that category and element; converted copy round trip; D-06 evidence counts | unit | `.venv/bin/python -m pytest -q -rs backend/tests/pandapower_parity_test.py` | ❌ W0 (01-07) | ⬜ pending |
| NET-03 | 01-08 T1, T2, T3; 01-09 T1, T3 | Comparator tolerance edges (0.01 pu, 2%, 2 MVA floor); incomplete never passes; registry exact; net unchanged; injected-snapshot vs algorithm runs localise a wrong scaling flag; synthetic session passes and a deliberate mismatch fails end to end | unit + integration | `.venv/bin/python -m pytest -q -rs backend/tests/pandapower_compare_test.py backend/tests/pandapower_cli_test.py backend/tests/pandapower_ingest_test.py` | ❌ W0 (01-08, 01-09) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `.gitignore` gains `/data/private/` and session artefact patterns; `backend/private_leak_scan.py` + `backend/tests/private_data_guard_test.py` (must land before any exported file arrives)
- [ ] `requirements-pandapower.txt` and `.venv` install with `pip check` (checkpoint: human-verify the pin and wheel hash)
- [ ] `backend/tests/pandapower_fixture.py` (not collected): synthetic RAW + synthetic reference into `tmp_path` from `case39()` with buses offset by 90000
- [ ] `backend/tests/psse_session_fake.py` (not collected): `FakePsspy` subclass; do not edit `psse_fake_psspy.py`
- [ ] Test files above plus an import-and-syntax gate for the laptop session package

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Scripted read-only session on the licensed PSS/E machine returns masked report and zip | PSE-01, PSE-02, PSE-03 | Needs a teammate at a licensed PSS/E install | Teammate runs the session wrapper; owner pastes masked summary; zip moved into `data/private/` |
| Parser on real file, parity zero, NET-03 on real reference, D-06 evidence report | NET-01, NET-02, NET-03 | Real data is private and only exists after the session | Owner runs the pandapower_job CLI; only masked pass/fail output is shared |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
