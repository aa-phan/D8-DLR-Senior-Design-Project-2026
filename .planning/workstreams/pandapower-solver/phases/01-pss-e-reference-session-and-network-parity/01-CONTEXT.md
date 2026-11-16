# Phase 1: PSS/E Reference Session and Network Parity - Context

**Gathered:** 2026-11-16
**Status:** Ready for planning

<domain>
## Phase Boundary

One scripted, read-only session on the licensed PSS/E laptop exports (a) the 39-bus case's network data, (b) PSS/E's load-flow and scaling settings, and (c) PSS/E's full solved answers, all to one private zip. On the owner's machine, project code parses that export, builds a pandapower network from it, proves element-by-element parity with the export, and proves each city's solved base case matches PSS/E within 0.01 pu and 2%. Nothing from the session reaches the public repository. Requirements: PSE-01 to PSE-04, NET-01 to NET-03.

Not in this phase: the `PandapowerApi`/study-engine integration (Phase 2; Phase 1 builds only the minimal scaling plus load flow NET-03 needs, which Phase 2 reuses), any database change, and the outage/margin comparisons as pass/fail gates (Phase 1 exports those answers; Phase 2 consumes them).

</domain>

<decisions>
## Implementation Decisions

### Session logistics
- **D-01:** The session runs on the same PSS/E laptop (PSS/E 36.4 Xplore, Python 3.14) with the same teammate. The repo checkout there is already set up.
- **D-02:** Remote, one script. The teammate runs `git pull` and one command, in the style of `docs/data-science/ops/psse_laptop_status.ps1`: it runs end to end, writes everything to one output folder, and prints a short masked summary (counts, statuses, versions; no bus numbers, values, paths, names or targets) that the teammate pastes back. No database access, no network calls, no writes outside its own output folder, and the case file is never saved (in-memory copies only, as the job already does).
- **D-03:** Output is one zip on the Desktop, sent privately to the owner (UT OneDrive/Box share or direct message, the same channel the mapping used). The owner unzips it into the git-ignored private folder (D-07).
- **D-04:** The private per-city mapping goes back to the laptop by the same private channel. The script deletes its copy at the end and says so in the summary. The teammate also deletes the zip after sending; the summary reminds them.
- **D-05:** The session is single-purpose: no dry run of the existing PSS/E job.

### Where private data lives
- **D-06:** The converted network data stays private on the owner's machine during Phase 1. At the end of Phase 1 the owner decides, with evidence: if the parity report shows the data equals the public IEEE 39-bus case, and its licence permits publication, commit a sha256-pinned copy; otherwise it becomes a GitHub secret for Phase 5 (it must fit the 48 KB limit). — **Reversibility:** one-way — a committed copy is public in git history permanently.
- **D-07:** Private folder: `data/private/pandapower/` inside the repo, git-ignored. The ignore rule and the secret/identifier scan land before any exported file arrives (PSE-04, success criterion 1).
- **D-08:** The PSS/E reference answers stay only on the owner's machine (git-ignored), never in a GitHub secret or CI. The owner keeps a backup wherever the mapping is kept.

### Reference answer scope
- **D-09:** The session exports full solved answers (every bus voltage and angle, every branch flow and loading, generator P/Q) for each city's scaled base case and for every screened outage of each city (about 4 + 130 solves), with each solve's convergence status. Non-converged and islanded outages are recorded as such, not dropped.
- **D-10:** For each city, the session also exports the voltage-margin search's limit point: the transfer PSS/E finds and the bus voltages at that point. This is where the reactive-limit effect shows up.
- **D-11:** NET-03 (this phase's gate) compares the base cases only. The outage and margin answers are exported now for Phase 2 to test against; they are not a Phase 1 pass/fail gate.

### When numbers don't match
- **D-12:** Match the data first. A remaining difference is allowed only if it is written up with its cause (for example, transformer modelling) and shown not to break the tolerance elsewhere. Anything unexplained fails NET-03. Network parameters are never tuned to force a match.
- **D-13:** Flow tolerance: a branch passes if its flow is within 2% or within 2 MVA, whichever is looser. Bus voltage tolerance: 0.01 pu absolute.
- **D-14:** pandapower copies whatever reactive-limit and adjustment settings the session reads from PSS/E (PSE-02). The parity check proves the copy; no physics-based override.

### Claude's Discretion
- The exact export format (RAW-class text vs project-defined JSON tables), file names inside the zip, and the parser's structure, provided the parser fails closed on unknown record types (NET-01).
- Exactly which `psspy` calls read the settings and the scaling details, chosen from the PSS/E 36.4 docs on the laptop and verified in the session.
- The masked summary's exact lines, following the masking rules of the existing laptop scripts.
- Whether the minimal Phase 1 scaling and load-flow code lives in `backend/pandapower_job/` from the start (recommended, so Phase 2 extends it).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope and research
- `.planning/workstreams/pandapower-solver/REQUIREMENTS.md` — PSE-01..04, NET-01..03 wording and thresholds
- `.planning/workstreams/pandapower-solver/ROADMAP.md` §Phase 1 — goal and five success criteria
- `.planning/workstreams/pandapower-solver/STATE.md` — owner decisions for the milestone
- `.planning/workstreams/pandapower-solver/research/SUMMARY.md` — resolved disagreements, PSS/E-machine item list, network-data route
- `.planning/workstreams/pandapower-solver/research/STACK.md` — pandapower 3.5.6 pins, RAW parser recommendation, case39 differences
- `.planning/workstreams/pandapower-solver/research/PITFALLS.md` — conversion traps (ratio-1.0 branch, rateA 0, sgen, 50 Hz, 0-based buses), island/NaN, leakage

### The PSS/E study pandapower must match
- `docs/data-science/decisions/psse_study_definitions.md` — what each study step computes
- `backend/psse_job/psse_api.py` — the only PSS/E call surface (SURFACE table, scaling layout)
- `backend/psse_job/study.py`, `backend/psse_job/contingency.py`, `backend/psse_job/margin.py` — per-city copy, outage screen, margin search
- `backend/psse_job/mapping.py` — mapping schema version 2 (per-city scaling block)
- `backend/psse_job/units.py` — rating unit conversions

### Laptop session conventions
- `docs/data-science/ops/psse_laptop_status.ps1`, `docs/data-science/ops/psse_laptop_cleanup.ps1` — remote-script style and masking rules
- `docs/data-science/decisions/psse_laptop_runbook.md` — laptop facts, "Pasting results safely", stop rules
- `.planning/workstreams/pss-e-integration/phases/03-laptop-run-and-handover/03-07-LAPTOP-RECORD.md` — PSS/E 36.4 environment helper (psse3604), converted-case finding, case facts (34 lines, 12 transformers)

### Leakage guards
- `backend/tests/secret_scan_test.py` — existing secret scan to extend for the private folder

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/psse_run_hourly.py` and `backend/psse_job/launcher.py`: how the laptop loads `psspy` (environment helper module, DLL folders); the session script reuses this loading, not the hourly launcher.
- `backend/psse_job/mapping.py`: the session script reads the same private mapping to build each city's scaled copy.
- `backend/psse_job/study.py` / `contingency.py`: the outage selection the session must reproduce so its outage list equals the job's.
- `backend/tests/psse_fake_psspy.py`: a fake `psspy` to test the session script on the Mac before the session.
- `backend/psse_job/redaction.py`: masking for the pasted summary.

### Established Patterns
- psse_job code is Python 3.7 syntax, stdlib only; the session script runs on the laptop's Python 3.14 but should keep to stdlib.
- Laptop deliverables are scripts in `docs/data-science/ops/` or `backend/`, pushed to a branch the laptop pulls.
- Masked output: counts, statuses and versions only (runbook "Pasting results safely").

### Integration Points
- New package `backend/pandapower_job/` (Python 3.12, `requirements-pandapower.txt`, `pandapower==3.5.6`) for the parser, builder, parity report and base-case comparison.
- `.gitignore` gains `data/private/`; `secret_scan_test.py` gains a guard for it.

</code_context>

<specifics>
## Specific Ideas

- The laptop branch: the teammate pulls a branch carrying only the session script (main or `feature/pandapower-solver`, pushed before the session).
- Book the session early; everything except running it can be built and tested on the Mac with the fake `psspy` and pandapower's `case39()` fixture.

</specifics>

<deferred>
## Deferred Ideas

None raised in discussion.

</deferred>

---

*Phase: 01-pss-e-reference-session-and-network-parity*
*Context gathered: 2026-11-16*
