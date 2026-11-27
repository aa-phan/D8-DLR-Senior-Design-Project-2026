---
phase: 01-pss-e-reference-session-and-network-parity
plan: 04
subsystem: testing
tags: [pss-e, laptop-session, settings-probe, fnsl-fingerprint, scaling-experiments, powershell-wrapper, session-guide, stdlib, python37]

requires:
  - phase: 01-pss-e-reference-session-and-network-parity
    provides: "plan 01-02: SessionContext, SectionResult, SECTION_FUNCTIONS table, GatedPsspy, WorkFolder members, raw_writer, build_parser, FakeSessionPsspy; plan 01-03: ctx.results['reference'] (margin_increments, sink_buses)"
provides:
  - "backend/psse_session/settings_probe.py: SETTING_KEYS (10), SETTINGS_READS (6), FNSL_VARIANTS (4), run(ctx); settings/settings.json, settings/docs/<function>.txt, settings/fingerprint_<city>_<point>_<variant>.json and .raw"
  - "backend/psse_session/scaling_probe.py: EXPERIMENTS (4), CLAMP_FACTORS, Q_WITH_P_INCREMENT_MW, run(ctx); scaling/experiments.json, scaling/<name>_before.raw, scaling/<name>_after.raw"
  - "docs/data-science/ops/psse_pandapower_session.ps1: the teammate's one command (-Python, -Config, -Mapping, -Check, -Only)"
  - "docs/data-science/decisions/psse_pandapower_session_guide.md: plain-English guide for the teammate and the owner"
  - "backend/tests/psse_session_settings_test.py: 9 tests (PSE-02 on the fake, wrapper static checks, guide placeholder check)"
affects: [01-08, 01-09, 01-10]

plan_head_before: 6c2e4d02d37997fc682c80b8df5eeb64fea3828e
plan_head_after: 0e77395a87ad6d5bce3722757d3b428060bbecc8

actuals:
  tokens: 16600
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Every setting key is read, measured or unavailable, and an unavailable key always carries a reason naming the refused call (function, parameter, ierr or exception class), never an empty field"
    - "Every fingerprint and scaling experiment starts from a fresh load_case; the stressed point prepares its saved base in a temporary folder inside the work folder that is removed in a finally block and never becomes a member"
    - "A list fnsl variant is called positionally first and by keyword only on TypeError; the call form that worked is recorded (the keyword form has never run on the real engine)"
    - "Values read from PSS/E are stored exactly as returned (JSON float repr round-trips bit for bit); no rounding, formatting or unit conversion on the laptop"
    - "The wrapper holds no logic beyond path resolution, one python -I call and removal of a psse_pp_session_ folder that appeared during the run; its safety is proved by static text checks"

key-files:
  created:
    - backend/psse_session/settings_probe.py
    - backend/psse_session/scaling_probe.py
    - backend/tests/psse_session_settings_test.py
    - docs/data-science/ops/psse_pandapower_session.ps1
    - docs/data-science/decisions/psse_pandapower_session_guide.md
  modified: []

key-decisions:
  - "A missing case index makes the settings and scaling sections failed with ('no case index', stage), not skipped as the plan text said: the plan 01-02 entry-script test requires every section to fail on a stub psspy, and 'skipped' is reserved for --only (the same decision plan 01-03 made for the reference section)"
  - "The settings section is failed only when no fingerprint solve produced a member (then var_limits is unavailable with a reason and the detail is 'unavailable'); a refused reader or one refused variant is information, not a failure, so the section stays ok"
  - "The wrapper prints two marker lines (==== copy from the next line ====, ==== copy up to the line above ====) because the Python summary has no ==== lines and the guide tells the teammate what to copy; the plan said the guide would refer to two ==== lines but gave the wrapper no way to print them"
  - "Under fail={'scal_2': 1} swing_in_total is also recorded as failed (it reads the totals through scal_2), with its before snapshot kept; the plan text named only the clamp and q_with_p experiments as failed"
  - "A failed experiment writes no after snapshot (the case state after a refused call is not a measurement)"
  - "Stressed fingerprints run for a city only when ctx.results['reference'][city] holds a non-None last-good increment and sink buses; a base that cannot be prepared gives four failed entries (call_failed names the stage), not silence"

requirements-completed: [PSE-02, PSE-01]

coverage:
  - id: D1
    description: "settings/settings.json holds all ten setting keys, each read, measured or unavailable with a reason; the candidate prmint/prmdat reads are recorded one by one; four cities x four fnsl variants are solved from a fresh load with JSON, RAW and the call form"
    requirement: "PSE-02"
    verification:
      - kind: unit
        ref: "backend/tests/psse_session_settings_test.py#test_tracer_settings_section_reads_and_fingerprints_into_the_zip"
        status: pass
    human_judgment: false
  - id: D2
    description: "Values are stored exactly as returned (0.1+0.2 round-trips; ints stay ints)"
    requirement: "PSE-02"
    verification:
      - kind: unit
        ref: "backend/tests/psse_session_settings_test.py#test_values_are_stored_exactly_as_returned"
        status: pass
    human_judgment: false
  - id: D3
    description: "Stressed fingerprints at the margin last-good point from the saved base; cities without a recorded increment get none; no saved copy is left or zipped"
    requirement: "PSE-02"
    verification:
      - kind: unit
        ref: "backend/tests/psse_session_settings_test.py#test_stressed_fingerprints_at_the_margin_point"
        status: pass
    human_judgment: false
  - id: D4
    description: "A raising reader, a positional-list TypeError (keyword form recorded), an ierr 1 variant and every solve refused are all recorded with their cause"
    requirement: "PSE-02"
    verification:
      - kind: unit
        ref: "backend/tests/psse_session_settings_test.py#test_refused_reads_and_variants_are_recorded"
        status: pass
    human_judgment: false
  - id: D5
    description: "The four scaling experiments run in order from a fresh load with before and after RAW snapshots; refusals and a missing RAW export are recorded; the section never solves and never saves"
    requirement: "PSE-02"
    verification:
      - kind: unit
        ref: "backend/tests/psse_session_settings_test.py#test_tracer_scaling_experiments_in_order_with_snapshots"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_session_settings_test.py#test_scaling_refusals_are_recorded"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_session_settings_test.py#test_scaling_section_never_solves_or_saves"
        status: pass
    human_judgment: false
  - id: D6
    description: "The wrapper is thin and offline (one python -I call, no web or file-writing cmdlet, removal only of a new folder, flags the parser accepts); the guide holds only placeholders and flags the parser accepts"
    requirement: "PSE-01"
    verification:
      - kind: unit
        ref: "backend/tests/psse_session_settings_test.py#test_wrapper_is_thin_and_offline"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_session_settings_test.py#test_guide_uses_placeholders_only"
        status: pass
    human_judgment: false
  - id: D7
    description: "That the real PSS/E 36.4 has prmint/prmdat under these names, that the eight-option fnsl list means what research assumption A6 says, that scaling clamps or ties Q to P as the experiments suppose, that the PowerShell wrapper runs on the laptop, and that the guide is clear to the teammate"
    requirement: "PSE-02"
    verification:
      - kind: manual_procedural
        ref: "the session of plan 01-10 on the PSS/E laptop (the PowerShell wrapper and guide are not run on the Mac)"
        status: unknown
    human_judgment: true
    rationale: "Only a fake psspy exists here and PowerShell is not run in the tests. Reader names, option meanings, the keyword fnsl form, the scaling behaviour, Windows removal of the work folder and the guide's clarity can only be learned on the laptop with the teammate."

duration: "about 7 minutes (2026-11-17T01:07Z to 01:14Z by the shell clock)"
completed: 2026-11-17
status: complete
---

# Phase 1 Plan 04: The settings and scaling sections, the wrapper and the guide Summary

**The session now records PSS/E's load-flow settings by candidate reads and by fingerprint solves (four cities x four fnsl option variants at the base and at each margin last-good point, from fresh loads), runs four scaling experiments with before and after RAW snapshots without ever solving or saving, and ships the teammate a thin PowerShell wrapper plus a plain-English guide.**

## Performance

- **Duration:** about 7 minutes (shell clock 01:07Z to 01:14Z)
- **Completed:** 2026-11-17 (UTC)
- **Tasks:** 3 of 3
- **Files:** 5 created (1043 lines of code and tests, plus the wrapper and guide), none modified

## Accomplishments

- `settings_probe.run(ctx)` plugs into `session.SECTION_FUNCTIONS["settings"]` with no edit to `session.py`. It captures the signature and doc text of `prmint` and `prmdat`, tries the six `SETTINGS_READS` one by one (function, name, ierr or class, value), and writes `settings/settings.json` with all ten `SETTING_KEYS`: `iteration_limit` and `mismatch_tolerance_mva` read from the engine, `var_limits` measured from the fingerprint member list, `tap_adjustment`, `phase_shift_adjustment`, `switched_shunt_adjustment` and `area_interchange` measured from the network section's counts, and `dc_tap_adjustment`, `flat_start`, `non_divergent` unavailable with a stated reason. Counts: read 2, measured 5, unavailable 3, fingerprints 16, fingerprints_ok 16 on the fake.
- Fingerprints: for each city in `CITIES` order and each `FNSL_VARIANTS` entry, a fresh `load_case`, the city's scaling, then one solve (the job's own no-argument `fnsl` for `default`, `gated.fnsl(list)` positionally for the others, keyword form only after a TypeError), the bus table and a RAW snapshot. The fake's call log shows `case, fnsl` pairs for all 16.
- Stressed point: for each city whose reference entry has a last-good increment and sink buses, `study.prepare_city_base` into `tmp_sav_settings/<city>` inside the work folder, four reloads of the saved copy with `define_subsystem` and `scale_load`, then `cleanup_base` and folder removal in `finally`. No `.sav` is left (the work folder is kept in the test on purpose) or zipped.
- `scaling_probe.run(ctx)` runs `swing_in_total`, `clamp_at_limits_x1_5`, `clamp_at_limits_x3` and `q_with_p` in order, each from a fresh `load_case` with a before and an after RAW snapshot and the totals as returned. The fake's call log has exactly one extra `case` load per experiment and no `fnsl` or `save` call.
- `psse_pandapower_session.ps1` (50 lines): resolves the repository (three folders above the script) and the Desktop, records existing `psse_pp_session_*` folders, makes one `& $Python -I -X utf8 -B ...\backend\psse_pandapower_session.py` call with `run` or `check`, removes only directories that are new since the start, and prints `Exit code: N`. No web, no file-writing cmdlet.
- `psse_pandapower_session_guide.md`: plain English; what the session is for, what it does and never does, the placeholders table, owner prerequisites, the teammate's eight steps, what each summary line and exit code (0, 1, 2, 6, 7, 130) means, stop rules, the owner's after-session steps and what is still unverified.

## Task Commits

1. **Task 1: Tracer - settings reads and fingerprint solves into the zip** - `a28c8dd` (feat)
2. **Task 2: Stressed fingerprints and the scaling experiments** - `871b9d2` (feat)
3. **Task 3: The session wrapper and the plain-English session guide** - `0e77395` (docs)

**Plan metadata:** the SUMMARY commit that follows this file (docs).

Tracer feedback gate: after `a28c8dd` the tracer `<verify>` was re-run end to end (2 passed; the acceptance import check printed `ok`; the combined run with `psse_session_test.py` and `psse_session_reference_test.py` 43 passed) before Task 2 expanded.

## Verification Results

- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs backend/tests/psse_session_settings_test.py backend/tests/psse_session_test.py`: `36 passed in 0.87s` (no skips; 9 settings tests including all nine named in the plan, plus the 27 of plan 01-02).
- With the reference tests as well: `50 passed in 1.55s`.
- Task 1 verify: `2 passed`. Task 3 verify, `-k "wrapper or guide"`: `2 passed, 7 deselected`.
- Acceptance import check (10 keys, four variant names in order): prints `ok`. `grep -c "psse_pandapower_session.py" docs/data-science/ops/psse_pandapower_session.ps1`: `1`.
- Frozen-job regression `psse_contract_test.py psse_api_test.py psse_entry_test.py psse_study_test.py private_data_guard_test.py -k "not owner_local"`: `148 passed, 1 deselected in 3.84s`.
- `.venv/bin/python -I -B backend/private_leak_scan.py --staged` before each of the three commits: exit 0. Working-tree scan `backend/private_leak_scan.py`: exit 0 with empty stdout (its one "not scanned" notice goes to stderr).
- Frozen-file gate (the plan's file list, checked with `git diff-tree` on each commit, run as simple separate commands): empty for all three commits. Post-commit deletion check: no deletions. `git rev-list --count 6c2e4d0..HEAD` measured 3 before this SUMMARY commit.
- Four mutations were applied by hand and reverted to prove the tests bite: removing the fresh `load_case` from the fingerprint start fails the tracer test; removing the `cleanup_base` and folder removals fails `test_stressed_fingerprints_at_the_margin_point`; adding an `api.solve(None)` to a clamp experiment fails `test_scaling_section_never_solves_or_saves`; adding `Set-Content` to the wrapper and misspelling a flag in the guide fails both static tests.

## Files Created

- `backend/psse_session/settings_probe.py` - constants, candidate reads, fingerprint solves, stressed point, section
- `backend/psse_session/scaling_probe.py` - constants, the four experiments, section
- `backend/tests/psse_session_settings_test.py` - 9 tests; fake subclasses `PositionalRejectingPsspy` and `OneVariantRefusedPsspy` and the reference stub live there
- `docs/data-science/ops/psse_pandapower_session.ps1` - the wrapper
- `docs/data-science/decisions/psse_pandapower_session_guide.md` - the guide

## Decisions Made

See `key-decisions` in the frontmatter. Interface notes for plans 01-08 and 01-09:

- `settings.json` extra keys beyond the plan: each fingerprint entry also carries `snapshot` (the RAW member or null), `increment_mw` (null at the base point) and `call_failed` (function and class or stage, never a message); a top-level `counts` mirrors the manifest counts.
- A fingerprint's JSON member holds `city`, `point`, `variant`, `options`, `call_form`, `solve`, `buses` (number, type_code, base_kv, pu), `snapshot`, `increment_mw`. `call_form` is `job_default`, `positional` or `keywords`.
- RAW members of this plan are registered by the session's own `raw_writer`, which files every export under the manifest section `network`; plan 01-09's reader should find them by member name, as noted in the 01-03 summary.
- `scaling/experiments.json` also holds a top-level `no_raw_export` flag.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] A missing case index is `failed`, not `skipped`**
- **Found during:** Task 1 (reading the plan 01-02 entry-script test and the 01-03 precedent)
- **Issue:** The plan says `run(ctx)` returns `skipped` ("no case index",) when `ctx.index` is None. `test_entry_script_runs_under_isolated_mode_with_a_stub_psspy` requires every section to be failed with a detail on a stub psspy that has no `case`, and `skipped` is the word `--only` uses.
- **Fix:** both `run` functions return `failed` with `("no case index", ctx.index_stage or "internal")`.
- **Files modified:** `backend/psse_session/settings_probe.py`, `backend/psse_session/scaling_probe.py`
- **Commit:** `a28c8dd`, `871b9d2`

**2. [Rule 2 - Missing critical functionality] The wrapper prints the two copy-marker lines**
- **Found during:** Task 3 (reading `bundle.render_summary` and the guide's paste step)
- **Issue:** The plan's guide tells the teammate to copy everything between two `====` lines, but the Python summary prints none and the plan's wrapper spec had no line printing them. A non-expert would not know where to start or stop copying.
- **Fix:** the wrapper prints `==== copy from the next line ====` before the call and `==== copy up to the line above ====` after `Exit code:`. `test_wrapper_is_thin_and_offline` still pins the flag set and the forbidden cmdlets.
- **Files modified:** `docs/data-science/ops/psse_pandapower_session.ps1`
- **Commit:** `0e77395`

### Interpretation choices (no code conflict, recorded for the verifier)

**3. swing_in_total under a refused scal_2.** The plan says `fail={"scal_2": 1}` makes the clamp and q_with_p experiments failed "while swing_in_total keeps its snapshot". Reading the totals is itself a `scal_2` call, so swing_in_total also fails; it keeps its before snapshot (written first) and the test asserts that.

**4. Section status rule for settings.** The plan does not say when the settings section is failed. Chosen: failed (detail `unavailable`) only when no fingerprint solve produced a member; a refused reader or variant is recorded and the section stays ok, because finding out which forms work is the point of the session.

### Process notes

**5. Test-first.** Tests were written before the code and run red (the module import failed) for Task 1 and Task 2, so the red was an import error rather than a behaviour failure. Task 3's wrapper and guide were written before their tests, as the files had to exist to be checked. The tests' ability to fail was proved afterwards by the four hand-made mutations listed above.

**6. Branch allow-list and ledger.** The `agent-*` branch allow-list was not applied (sequential run on `feature/pandapower-solver` as dispatched); the supplied-root pin, the detached-HEAD check and the protected-branch check were run before the writes and each commit. The plan commit ledger is the scratchpad file `gsd-plan-head-before-01-04` (base `6c2e4d0`). The frozen-file gate was run as simple separate commands because the sandbox refuses compound git forms. One compound Python-heredoc edit and one compound git/for-loop command were refused by the sandbox and redone with the Edit tool and plain commands. STATE.md and ROADMAP.md were left alone as instructed.

**Total deviations:** 1 Rule 1, 1 Rule 2, 2 interpretation choices, 2 process notes. **Impact:** none on the plan's outputs; the interfaces only grew.

## Issues Encountered

None blocking.

## Known Stubs

None.

## Threat Flags

None. No new network endpoint, auth path or schema. The PowerShell wrapper is new code outside Python and is the surface T-01-15 covers (static checks forbid web and file-writing cmdlets and restrict removal to new folders).

## Threat Model Coverage

- T-01-14 (fingerprints and scaling touching PSS/E state): every fingerprint and experiment starts from a fresh `load_case`; the scaling section makes no `save` or `fnsl` call (`test_scaling_section_never_solves_or_saves`); the stressed point's saved copies live in `tmp_sav_settings` inside the work folder, are never members and are removed; the plan 01-02 gate still refuses any save outside the work folder.
- T-01-15 (wrapper): one Python call, no web or file-writing cmdlet, `Remove-Item` only on the new-folder variable; `test_wrapper_is_thin_and_offline`.
- T-01-16 (guide disclosure): placeholders only, no drive-letter or home-folder path; `test_guide_uses_placeholders_only` and the repository leak scan.
- T-01-17 (unreadable settings): every unavailable key has a reason naming the refused call or the missing reader; the tracer test asserts a non-empty reason for each.
- T-01-SC: nothing was installed.

## Open Items For Later Plans

- Everything about real PSS/E (D7 above) is for the session of plan 01-10: whether `prmint`/`prmdat` exist with these names and `ITMXN`/`TOLN` are valid, which fnsl call form works, what the var-limit slot values do, and what the scaling experiments show.
- Plan 01-08's analyser classifies the fingerprints (compare voltages across variants) and the three scaling details offline; plan 01-09's reader should read RAW members by name.
- The guide names plan 01-09's `ingest` and `check` commands exactly as written in the plan; they do not exist yet.
- Nobody has run the PowerShell wrapper; the first run on the laptop is the test of it (`-ExecutionPolicy Bypass -File` form, argument quoting for a path with a space, marker lines).

## Next Phase Readiness

Ready for plan 01-08 (analyser) and plan 01-09 (reader and ingest): the member layout and JSON shapes in this summary are final. The teammate has one command and a guide for plan 01-10.

## Self-Check: PASSED

- FOUND: `backend/psse_session/settings_probe.py`, `backend/psse_session/scaling_probe.py`, `backend/tests/psse_session_settings_test.py`, `docs/data-science/ops/psse_pandapower_session.ps1`, `docs/data-science/decisions/psse_pandapower_session_guide.md`
- FOUND commits: `a28c8dd`, `871b9d2`, `0e77395` (all in `git log` of HEAD)
