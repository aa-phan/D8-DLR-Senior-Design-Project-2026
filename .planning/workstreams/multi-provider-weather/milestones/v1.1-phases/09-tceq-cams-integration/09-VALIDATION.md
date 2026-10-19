---
phase: "09"
slug: "tceq-cams-integration"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-09-13"
---

# Phase 09 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pytest.ini` at repo root (`pythonpath = backend`, `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py`) |
| **Quick run command** | `.venv/bin/python -m pytest backend/tests/tceq_provider_test.py -q` |
| **Full suite command** | `.venv/bin/python -m pytest -q` |
| **Estimated runtime** | ~5 seconds full suite (measured: 296 passed in 4.96s, pre-phase baseline); ~1-2 seconds for the phase-scoped quick command |

**Pre-phase baseline:** 296 passing tests. Several plan-level `<fails_when>` clauses assert against
this number directly — a full-suite passed count at or below 296 after the tracer lands means the new
test file was never collected.

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/python -m pytest backend/tests/tceq_provider_test.py -q`
- **After every plan wave:** Run `.venv/bin/python -m pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

Every one of the three plans additionally closes its own final task with a full-suite
`.venv/bin/python -m pytest -q`, so no wave can end on an unverified regression surface.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 1 | WX-01 | T-09-SC | `bs4`'s `[SUS]` legitimacy verdict (`unknown-downloads`, `no-repository`) is cleared by a human at pypi.org *before* the pin is written or the first `import bs4` lands; not auto-approvable | manual — `checkpoint:human-verify` (`gate="blocking-human"`) | none — human judgement gate, see Manual-Only Verifications | n/a | ⬜ pending |
| 09-01-02 | 01 | 1 | WX-01 | T-09-SC | Only the human-approved distribution is pinned in `requirements.txt`; `lxml` declined outright so its own `[SUS]` flag never goes live. `TCEQ_STATIONS` is a hard-coded four-entry table keyed 1:1 to `CITY_COORDINATES` | unit + inline assertion | `.venv/bin/python -m pytest -q` · `.venv/bin/python -c "... assert config.TCEQ_STATIONS == {...}; assert set(config.TCEQ_STATIONS) == set(config.CITY_COORDINATES) ..."` (prints `tceq station table OK`) | ✅ existing (`pytest.ini`, `backend/config.py`) | ⬜ pending |
| 09-01-03 | 01 | 1 | WX-01 | T-09-01 … T-09-09 | `select_date="user"` is a literal in the params dict (else the CGI answers today's report at HTTP 200 for any date); fixed-integer UTC offsets, never a tz-database lookup; `_validate_response` requires both the site-specific `<h1>` link and a `<table border='1'>`; exact `==` label match against `TARGET_LABELS`; conversions delegate to `units_def.Q` with a `PIPELINE_SCHEMA` range backstop; header-driven cell slice rejects short rows | unit — TDD tracer (RED first) | `.venv/bin/python -m pytest backend/tests/tceq_provider_test.py -q` (≥8 passed) · `... weather_provider_test.py -q -k tceq` (≥4 passed) · `... -k "dispatch or merge or asos or nsrdb or open_meteo"` (Phase 6/7/8 regression guard) · request-contract assertion (prints `tceq request contract OK`) · `.venv/bin/python -m pytest -q` (must exceed 296) | ❌ created by this task — `backend/tests/tceq_provider_test.py` is written RED inside the tracer, not in Wave 0 | ⬜ pending |
| 09-02-01 | 02 | 2 | WX-01 | T-09-10, T-09-11 | Each day in a multi-day window sends its own *distinct* date triple (a loop that recomputes the start date every iteration returns N identical, well-formed, in-range days — the most plausible silent corruption in this phase); `TCEQ_MAX_DAYS_PER_FETCH = 31` raises before any request is issued | unit (TDD) | `.venv/bin/python -m pytest backend/tests/tceq_provider_test.py -q` · window-decomposition assertion (prints `window decomposition OK`) · `.venv/bin/python -m pytest -q` | ✅ (09-01-03) | ⬜ pending |
| 09-02-02 | 02 | 2 | WX-01 | T-09-12, T-09-16 | `_validate_response` tightened to require the *requested* CAMS ID in the `<h1>` link, so one city's readings cannot be attributed to another with every downstream range check still passing; `humidity_source` stays null on the RH-less sites through `attach_provenance`'s existing invariant | unit (TDD) | `.venv/bin/python -m pytest backend/tests/tceq_provider_test.py -q` · `... weather_provider_test.py -q -k tceq` · four-city offset-coverage assertion incl. the MST/CST one-hour split (prints `four-city offset coverage OK`) · `.venv/bin/python -m pytest -q` | ✅ (09-01-03) | ⬜ pending |
| 09-02-03 | 02 | 2 | WX-01 | T-09-13, T-09-14, T-09-15 | Absent *required* row raises while absent `Relative Humidity` nulls — pinned against each other in one parameterised group so the branches cannot be collapsed; multi-ID `stids` raises naming every supplied ID rather than silently returning one city; placeholder cells (`FEW`/`NA`) null a value while preserving row count so no later hour shifts | unit (TDD) | `.venv/bin/python -m pytest backend/tests/tceq_provider_test.py -q` · `... weather_provider_test.py -q` (full file — dispatch regression guard for the new `stids` guard) · `.venv/bin/python -m pytest -q` | ✅ (09-01-03) | ⬜ pending |
| 09-03-01 | 03 | 3 | WX-01 | T-09-17, T-09-18, T-09-20, T-09-21 | Source gate asserts `backend/tceq_provider.py` reads no env var and holds no token/key/secret literal, keeping the credential-free path a verified fact rather than an assumption; Phase 10 docs (`PRD.md`, `data_provider.md`) provably untouched; the gate itself is proven load-bearing against a deliberately broken scratch copy before being accepted green | unit + source/diff gates | `.venv/bin/python -m pytest backend/tests/weather_provider_test.py -q -k "tceq"` · `git diff --name-only -- docs/data-science/PRD.md docs/data-science/decisions/data_provider.md` (any output = fail) · `grep -c 'tceq_provider\|TCEQ_STATIONS' docs/data-science/specs/C4-weather-ingestion.md` (0 = fail) · `.venv/bin/python -m pytest -q` | ✅ existing (`backend/tests/weather_provider_test.py`) | ⬜ pending |
| 09-03-02 | 03 | 3 | WX-01 | T-09-19 | A real per-site pull re-confirms parameter availability and the CST/CST/CST/MST labels against the production endpoint — TCEQ activating or retiring an instrument changes which site is correct, and no mocked test can see it | manual — `checkpoint:human-verify` (`gate="blocking-human"`) | none by design — every automated test in this phase mocks `requests.get`; see Manual-Only Verifications | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Sampling continuity:** the two manual checkpoints (09-01-01, 09-03-02) are non-adjacent and each is
followed or preceded by an automated task, so no three consecutive tasks run without automated verify.

---

## Wave 0 Requirements

**Existing infrastructure covers all phase requirements.** No Wave 0 task is needed:

- pytest is already configured project-wide via `pytest.ini` at the repo root — no framework install.
- `backend/tests/weather_provider_test.py` already exists and is extended in place.
- `backend/tests/tceq_provider_test.py` is new, but it is authored **inside** Plan 09-01 Task 3, which
  is `type="tracer" tdd="true"` — the test file is the RED step of that task, not a prerequisite of it.
  No `<automated>` block in any of the three plans carries a `MISSING —` marker.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `bs4` is the real Beautiful Soup project (or is a dummy alias for `beautifulsoup4`), not a typosquat, before it is pinned | WX-01 (T-09-SC) | Package legitimacy is a human judgement call by policy — legitimacy checkpoints are never auto-approvable, and `bs4` carries a `[SUS]` verdict with a null download count and no source repository, so no automated signal can clear it | Plan 09-01 Task 1 `<how-to-verify>`: inspect pypi.org/project/bs4 and pypi.org/project/beautifulsoup4, confirm 4.14.3 is listed, decide which distribution name the pin should use, confirm `.venv/bin/python -c "import bs4; print(bs4.__version__)"` prints `4.14.3`. Resume signal names the distribution Task 2 must write. |
| A real TCEQ pull succeeds for all four CAMS sites with plausible converted values and unchanged CST/MST labels | WX-01 (T-09-19), ROADMAP Success Criterion 1 | Every automated test in this phase mocks `requests.get` by design, so nothing in Phase 9 ever contacts TCEQ. Research assumptions A1 (per-row cell layout holds for CAMS 38/1095/41, not only the cell-by-cell-diffed CAMS 83) and A3 (the four fixed UTC offsets) can only be closed against the live endpoint, and the site-selection table carries a 30-day validity window for the same reason | Plan 09-03 Task 2 `<how-to-verify>`: run the four-site `fetch_tceq` loop against yesterday's date and confirm per site that `air_temp` reads as °C (not a 60-100 °F number), `wind_speed` as m/s (not mph), `wind_direction` is 0-360, and RH is present at 83/41 and null at 38/1095; open the four `daily_summary.pl` pages and confirm 38/83/1095 say CST and 41 says MST; confirm the four row labels appear verbatim; confirm an invalid CAMS ID still raises `ValueError`. Record the four per-site lines and four timezone labels in the SUMMARY as evidence. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies — 21 `<automated>` commands across 6 automated tasks, each paired 1:1 with a `<fails_when>` clause (21/21); the 2 remaining tasks are blocking-human checkpoints documented above
- [x] Sampling continuity: no 3 consecutive tasks without automated verify — the 2 checkpoints are non-adjacent
- [x] Wave 0 covers all MISSING references — none exist; no plan emits a `MISSING —` marker, and the one new test file is authored as the RED step of the TDD tracer it belongs to
- [x] No watch-mode flags — every command is a single-shot `pytest -q`, `python -c`, `git diff` or `grep`
- [x] Feedback latency < 10s — full suite measured at 4.96s (296 tests); phase-scoped quick command is faster still
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-09-13
