# Acknowledgements — Use of Generative AI Tools

Per the ECE 464 policy on generative AI use, this document logs how AI tools were used on this Capstone Design project. It is a living document and should be reviewed and updated before any significant commit that includes AI-assisted work — see "Keeping This Updated" below.

## 1. AI Tool(s) Used

- **Claude Code** (Anthropic), running the **Claude Sonnet 5** model — an agentic CLI coding assistant with direct read/write access to this repository.

## 2. How and Why It Was Used

### Session: 2026-08-24 (a), conducted by Aaron Phan — DS documentation + initial file-structure reorg

Claude Code was used to:

1. Review the existing repository (the Data Science pipeline's Python files) and the three existing EE464 course deliverables in `docs/` (`Project Definition.md`, `Prior Art Report.md`, `System Design Report.md`) to build an accurate as-built picture of the Data Science subsystem.
2. Draft internal engineering documentation, explicitly **not** a course deliverable and not submitted to Canvas: `docs/data-science/PRD.md` (requirements), `docs/data-science/ROADMAP.md` (phased implementation plan, dependency graph, blocker analysis), and ten component-level technical specs in `docs/data-science/specs/` (C1–C10).
3. Identify and flag — not silently fix — discrepancies between the System Design Report's claims and the actual repository state (e.g., the SDR states the team selected NOAA + NSRDB for weather ingestion, but all working code uses the Synoptic Data API; the SDR describes a corridor-discretization spatial pipeline and a trained anomaly-detection model as completed risk-reduction work, neither of which exists in code).
4. Identify a pre-existing defect: a self-contradictory assertion in `tests/SafetyMonitor_TestSuite.py` (`test_gate_2_fails_when_link_status_not_ok`), confirmed failing by actually running `pytest` rather than by inspection alone, and documented (not fixed, per team decision) as a known issue in the C7 spec.
5. Reorganize the repository's flat file layout into `src/`, `tests/`, and `data/` directories; update the resulting hardcoded relative-path string literals and documentation cross-references; and verify (via `pytest` and `py_compile`) that behavior was identical before and after the move.

The AI was used to accelerate documentation drafting, cross-reference verification (confirming every file/function/line reference cited in the new docs actually resolves against the source), and mechanical refactoring. It was **not** used to generate the underlying engineering content of the DS subsystem itself — the IEEE 738 thermal model, the safety-gating logic, the ERCOT load-merge logic, and the dimensional-analysis module all predate this AI-assisted session and were authored by the team.

### Session: 2026-08-24 (b), conducted by Aaron Phan — frontend/API scaffolding

Claude Code was used to:

1. Rename `src/` → `backend/` and move `tests/` inside it (`backend/tests/`), so the DS subsystem's code sits as a clearly-named, self-contained peer to two new empty scaffold directories, `frontend/` and `api/`.
2. Create placeholder `README.md` files in `frontend/`, `api/`, and a new `docs/frontend/`, stating planned stack (React / Flask, per the System Design Report's Bill of Materials), current status (not started), and pointing future Software sub-team documentation at the `docs/data-science/` convention (PRD → ROADMAP → component specs) established in the prior session — no frontend/API requirements were invented.
3. Update `pytest.ini`, `README.md`, and all file/path references across `docs/data-science/` to reflect the `backend/` rename, and re-verify the test-suite baseline was unchanged by the move.

No frontend or API code was written this session — this was structural scaffolding only, based on the BOM already present in the team's own System Design Report, not on any AI-generated requirements.

### Session: 2026-08-24 (c), conducted by Aaron Phan — Phase 1 (C1/C2/C3) implementation via subagents

Claude Code was used, at the user's explicit direction to use subagents, to implement the three Phase 1 components identified as the starting point in `docs/data-science/ROADMAP.md`:

1. Dispatched a research subagent (with live web search) to find real, citable static line ratings for 5 major Texas metro areas (Houston, Austin, Dallas, Fort Worth, San Antonio), for use in a new configuration module. The first research pass found no source differentiating a per-city rating and flagged this honestly rather than inventing numbers. Based on that finding, the user was asked how to proceed; a second, more targeted research pass (specifically pointed at ERCOT Regional Planning Group filings, PUCT dockets, and FERC filings) found one genuinely sourced, city-specific value (San Antonio, via an ERCOT Board filing on an existing 345kV circuit). The user was asked again how to treat a partially-useful result found for Dallas/Fort Worth (a real but non-representative "modern rebuild target" spec) and the remaining unsourced cities; the user chose to exclude the non-representative number and accept the sourcing gap for the four other cities as an honestly-labeled uniform baseline rather than pursue further research.
2. Dispatched three sequential implementation subagents (one per component, each briefed with only its own spec file from `docs/data-science/specs/`) to build: `backend/config.py` (C1 — centralizing the previously-duplicated hardcoded values, including the researched static ratings with source citations in-code); wiring of the existing `validate_pipeline_row` function into the pipeline's real output path (C2); and a published output schema doc plus a hand-built sample fixture CSV (C3).
3. Independently re-verified every subagent's self-reported work rather than trusting it as delivered — re-read the actual diffs, re-ran `py_compile`/`pytest`/the standalone `units_def_test.py` script, and constructed independent test cases (not reused from the subagents' own verification) for the C2 validation logic and the C3 fixture's schema round-trip.
4. Updated `docs/data-science/PRD.md`, `ROADMAP.md`, and the three components' own spec files to reflect what was actually implemented — including flagging, not silently omitting, the acceptance criteria that were NOT fully met (e.g., C1's per-city rating *selection* logic isn't wired in yet, only the lookup table exists; C3's fixture is hand-built, not generated by a real pipeline run, since no Synoptic API token was available in this environment to verify against).

All implementation work happened on a new branch, `feature/phase1-foundation`, per the user's explicit choice (rather than directly on `main`, which was this repo's practice in prior sessions).

## 3. Ideas Attributable to AI

- The specific ten-component decomposition (C1–C10) and the four-phase implementation ordering (Foundation → Core Consolidation → Safety & Spatial → Predictive) in `ROADMAP.md` were proposed by Claude Code, based on its analysis of the existing code's actual coupling — specifically, the observation that the DS modules communicate with each other only through CSV files on disk (zero cross-module Python imports) — and adopted by the team after review.
- The five "Blocker Analysis" findings in `ROADMAP.md` (e.g., identifying the DS→dashboard output schema as the primary cross-team wait risk for the Software sub-team; recommending historical weather-data collection start during Phase 2 rather than Phase 4 to avoid a training-data stall) are AI-proposed risk analysis, not independently derived by the team prior to this session.
- The `src/` / `tests/` / `data/` file-structure scheme (session a) and the subsequent `backend/` / `frontend/` / `api/` top-level split (session b) were both proposed by Claude Code as one of several options and selected by the team via direct confirmation.
- The specific implementation of `backend/config.py` (session c) — its exact set of exposed constants, the decision to keep it a plain Python module rather than JSON/YAML, and the choice to include per-value source comments directly in code rather than only in docs — was proposed by Claude Code and executed by a subagent, not specified by the user beyond the general C1 spec.
- The wording, structure, and logging behavior of `backend/dlr_pipeline.py::validate_pipeline_output` (session c) — non-strict validation, a deduped top-N violation summary logged at `WARNING`, zero mutation of pipeline output — was designed by Claude Code within the bounds of C2's spec, not dictated line-by-line by the user.

## 4. Identification and Independent Confirmation of AI-Provided Information

- All file paths, function names, and line-number citations throughout `docs/data-science/` were generated by directly reading the repository's actual files during each session (not recalled or assumed), and were spot-checked against source with `grep`/`sed` before being finalized.
- The claim that `test_gate_2_fails_when_link_status_not_ok` fails was independently confirmed by executing the test suite, not merely asserted — output `1 failed, 17 passed`, reproduced identically across every session in this document, including after every file move and every new component landing in session (c).
- No external citations, IEEE/NERC standard interpretations, or third-party API claims were generated by the AI in sessions (a) or (b). All such references in `docs/data-science/` from those sessions point back to the team's own pre-existing course deliverables, which were outside AI review scope and not altered by it.
- **Session (c) is different and requires closer scrutiny**: it DOES include AI-sourced external claims — the static line rating research (ERCOT Board filings, utility documents) cited in `backend/config.py` and `docs/data-science/specs/C1-configuration.md`. These were retrieved via live web search by a subagent, not recalled from training data, and the subagent was explicitly instructed to flag anything it could not verify rather than present it as confirmed (it did so — e.g., explicitly stating it could not verify FERC Form 715 filing content, and correctly identifying Dallas/Fort Worth's only found number as a non-representative rebuild-target spec rather than presenting it as a like-for-like value). **These citations have NOT yet been independently confirmed by a human team member** — per this document's own policy (§2 of the ECE 464 requirement), the URLs and figures in `backend/config.py`'s comments (particularly the San Antonio 1,761 A / ERCOT Board Item 11.2 citation) should be opened and verified by a team member before being treated as authoritative, especially if used in the research paper deliverable.
- Team members should independently review `docs/data-science/`, `backend/config.py`'s sourcing comments specifically, and all file-structure changes before relying on them for grading submissions or downstream engineering decisions, consistent with standard practice for AI-assisted work product.

## Keeping This Updated

This file should be reviewed and updated to reflect new AI-assisted work **before any significant commit** — i.e., before committing new features, substantial documentation, or non-trivial refactors produced with AI assistance. A commit is "significant" for this purpose if it would need describing in a standup/status update; trivial fixes (typos, formatting) don't require an update here.
