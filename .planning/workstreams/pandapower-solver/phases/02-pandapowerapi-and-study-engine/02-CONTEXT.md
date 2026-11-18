# Phase 2: PandapowerApi and Study Engine - Context

**Gathered:** 2026-11-18
**Status:** Ready for planning

<domain>
## Phase Boundary

A `PandapowerApi` that offers the same methods the study code uses from `PsseApi`, chosen through one new factory argument in `study.py`, so `study`, `contingency`, `margin`, `violations` and `dispatch` run unchanged. A full four-city study runs end to end on a throwaway local database with the placeholder mapping and no live data. Requirements ENG-01 to ENG-06. Runs in parallel with Phase 3.

</domain>

<decisions>
## Implementation Decisions

Gathered with the owner's "use your defaults" instruction (2026-11-18): the owner reviewed a plain-language summary of four open choices and asked Claude to apply its recommendations. The owner can change any of them before or during planning.

### Where the code lives
- **D-01:** `PandapowerApi` goes in `backend/pandapower_job/` (Phase 1 already put the builder, scaling and solve code there), not in the stdlib-only `backend/psse_job/`. `psse_job` must not import pandapower. — **Reversibility:** costly — moving it later touches every import of the module.
- **D-02:** `study.py` selects the solver through one new factory argument, a plain string (`"psse"` default, `"pandapower"`). The default keeps every existing PSS/E test passing unchanged.
- **D-03:** A test pins every `PandapowerApi` public method name and signature to `PsseApi` (success criterion 1).

### Islands and non-convergence
- **D-04:** Copy PSS/E's behaviour. An outage that islands any in-service bus from the main grid is recorded as a `non_convergence` row, whatever pandapower itself returns. Detection is explicit: any in-service bus with no voltage, or below `settings.collapse_voltage_pu`, makes the solve not converged. pandapower's automatic dropping of isolated buses is not relied on.
- **D-05:** No result is ever read after a failed solve (ENG-04).

### Settings before PSE-02
- **D-06:** Until the laptop session records the real values, the solve settings (reactive limits, iteration limit, tolerance) are explicit placeholders, clearly named and stored with each run as placeholder values. Plans must not hard-wire them. ENG-05 is finished once PSE-02 is recorded. Consistent with Phase 1 D-14: copy whatever PSS/E reports, no physics-based override.

### Rating basis and testing
- **D-07:** A rating is applied as a current limit per circuit and loading is read on the current basis. A mapping that asks for any other basis is refused with a clear failure (ENG-02).
- **D-08:** Test against the public IEEE 39-bus case (pandapower's built-in `case39`) as a fixture only, plus a contract test against `PsseApi`. No private data in the repository.
- **D-09:** Each city, each outage and each margin step solves a fresh copy of its base network. A test shows that outage order, or running after a failed solve, does not change the results.

### Claude's Discretion
Internal structure of `PandapowerApi`, helper names, and test layout, as long as the decisions above hold.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Workstream
- `.planning/workstreams/pandapower-solver/ROADMAP.md` — Phase 2 goal and success criteria
- `.planning/workstreams/pandapower-solver/REQUIREMENTS.md` — ENG-01 to ENG-06
- `.planning/workstreams/pandapower-solver/phases/01-pss-e-reference-session-and-network-parity/01-CONTEXT.md` — Phase 1 decisions (D-13 tolerances, D-14 copied settings)
- `.planning/workstreams/pandapower-solver/research/` — ARCHITECTURE.md, PITFALLS.md, STACK.md, FEATURES.md, SUMMARY.md

### Existing code to mirror
- `backend/psse_job/psse_api.py` — `PsseApi`, the interface to match
- `backend/psse_job/study.py`, `contingency.py`, `margin.py`, `violations.py`, `dispatch.py` — solver-neutral study code that must run unchanged
- `backend/pandapower_job/` — Phase 1 builder, scaling and solve code to extend

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/pandapower_job/network.py`, `scaling.py`, `solve.py`: network builder, minimal city scaling and copied solve settings from Phase 1; ENG-05 and `scale_case` extend these rather than rewrite them.
- `backend/psse_job/settings.py`: holds `collapse_voltage_pu`, used in `contingency._collapsed`.

### Established Patterns
- `PsseApi` wraps `psspy` calls and raises on error codes; the study code treats NaN or low voltage as collapsed.

### Integration Points
- `study.py` (`_open_case`, `prepare_base`, `scale_city_case`) is where the factory argument connects.

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 2-PandapowerApi and Study Engine*
*Context gathered: 2026-11-18*
