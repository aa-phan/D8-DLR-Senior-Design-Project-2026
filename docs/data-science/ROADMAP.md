# Data Science Subsystem — Implementation Roadmap

**Status:** Internal engineering reference, companion to `PRD.md` and `specs/`. Defines build order, dependencies, and where parallel work is and isn't safe. Not a course deliverable and not a calendar — no dates. Effort sizes (S/M/L) are relative complexity, not time estimates; the team should size against its own velocity.

**Last reviewed against repo state:** 2026-08-24

---

## 1. Why This Ordering

The repo's five production modules (`backend/station_explorer.py`, `backend/dlr_pipeline.py`, `backend/DLRSafetyMonitor.py`, `backend/units_def.py`, `backend/ercot_data_retriever.py` / `backend/ercot_dlr_merger.py`) have **zero cross-module imports**. They communicate entirely through CSV files on disk, coupled by column name — e.g. `backend/ercot_dlr_merger.py` reads `dlr_amps`, `datetime_utc`, `wind_speed`, `air_temp` directly out of whatever `backend/dlr_pipeline.py` exported. That's already close to the modularity the team wants: different people can own different files without touching each other's code. What's missing is that the file contract is **implicit and unenforced** — nothing stops a column rename from silently breaking a downstream script until someone runs it.

That fact drives the whole roadmap: **formalizing the implicit contract is the cheapest, highest-leverage first move**, because it's the specific thing that lets multiple people build against each other's outputs safely and in parallel. Everything after that is ordered least→most complex, with the two Phase 4 components deliberately last because they're both highest-effort and dependent on everything else.

## 2. Component Model

| ID | Component | Phase | Effort | Status |
|---|---|---|---|---|
| C1 | Configuration & Parameterization | 1 | S | Implemented (`backend/config.py`) |
| C2 | Pipeline Data Contract | 1 | S | Implemented and integrated — `run_pipeline` validates every row against `PIPELINE_SCHEMA` |
| C3 | Export & Visualization | 1 | S | Implemented — schema now documented at `docs/data-science/schema/pipeline_output_v1.md`, with a fixture at `data/fixtures/sample_pipeline_output.csv` |
| C4 | Weather Ingestion | 2 | M | Implemented — provider-agnostic adapter (`backend/weather_provider.py`); still only Synoptic behind it |
| C5 | Thermal Model (IEEE 738) | 2 | M | Implemented as `backend/thermal_model.py`; validated against IEEE 738's own published worked example. A real bug (erroneous π factor, ~69% ampacity overestimate) was found and fixed in the process — see `PRD.md` §9 |
| C6 | Grid Load Integration (ERCOT) | 2 | M | Implemented, with new test coverage for the three previously-unverified acceptance criteria |
| C7 | Safety Monitor & Fallback | 3 | M | Implemented (G1–G6; uses C5 ampacity) |
| C8 | Corridor Spatial Discretization | 3 | L | Implemented (great-circle geometry) |
| C9 | Ampacity Forecasting | 4 | L | Implemented (naive, ewm, ml) |
| C10 | Learned Anomaly Detection | 4 | L | Implemented (G6, optional) |

Full detail per component: `specs/C1-configuration.md` through `specs/C10-anomaly-detection.md`.

## 3. Dependency Graph

```
                    ┌──> C4 Weather ────────┬──> C8 Corridor
                    │         │             │
C1 Configuration ───┼──> C5 Thermal ────────┤
                    │         │             │
                    │         └──> C7 Safety ──> C10 Learned Anomaly
                    │
                    └──> C6 ERCOT  (isolated track — no DS-component dependency beyond C1)

C2 Data Contract ───────> C3 Export ──┬──> C6 ERCOT (reads C3's export schema)
                                      └──> Software sub-team dashboard (external consumer)

C4 + C5 ──> C9 Forecasting
```

- **Critical path:** C1 → C5 → C8 (longest chain of hard dependencies)
- **Cross-team unblock path:** C2 → C3 → Software sub-team's dashboard work
- Every arrow is a **hard** dependency (the downstream component's interface assumes the upstream one exists). Anything not connected by an arrow is fair game to build concurrently.

## 4. Phases

### Phase 1 — Foundation (C1, C2, C3)

Lowest complexity, highest fan-out — nearly everything else either reads config (C1) or produces/consumes the pipeline's CSV schema (C2, C3). This is a deliberate **serialization point**: land it in one focused pass rather than letting people start Phase 2 work against a contract that's still moving underneath them.

- **C1** pulls the hardcoded values scattered across `backend/dlr_pipeline.py`, `backend/DLRSafetyMonitor.py`, and `backend/ercot_dlr_merger.py` (station file, date window, `900.0` A static rating duplicated in two places, conductor defaults) into one place.
- **C2** takes `backend/units_def.py`'s already-built `PIPELINE_SCHEMA` and makes it the single enforced source of truth for column names/units/ranges, rather than a library that exists but is never called.
- **C3** documents and stabilizes the CSV/plot output shape that C2 defines, so downstream consumers (C6, the Software sub-team) can build against a fixed contract.

### Phase 2 — Core Consolidation (C4, C5, C6)

Three genuinely independent tracks — **can run fully in parallel** once Phase 1 lands, by different people, with no file collisions.

- **C4** wraps the existing Synoptic fetch logic behind a provider-agnostic adapter interface, so the still-open weather-provider decision (PRD §7.1) doesn't block anyone downstream.
- **C5** extracts the IEEE 738 math (`ieee738_ampacity`, `perpendicular_wind`, `ConductorConfig`) into an importable module with no `__main__`-block side effects, so C7 and C9 can call it directly instead of reimplementing it.
- **C6** is fully isolated from the other two — ERCOT ingestion and merge logic touch no shared code, only the C2/C3 file contract.

### Phase 3 — Safety & Spatial (C7, C8)

- **C7** becomes small once C5 exists: point `DLRSafetyMonitor._compute_ampacity` at the real thermal model instead of its linear placeholder. Independent of C8.
- **C8** is the largest net-new build in the roadmap — real corridor geometry, per-point ampacity, min-ampacity bottleneck logic. Needs C4 (weather at each point) and C5 (ampacity at each point), not C7.

### Phase 4 — Predictive (C9, C10)

Highest complexity and most dependent on everything before them — deliberately last.

- **C9** needs both weather ingestion (C4) and the thermal model (C5) to generate training features, plus accumulated historical data (see §5 Blocker Analysis).
- **C10** builds on C7's gating framework, replacing/augmenting its deterministic thresholds with a trained model.

## 5. Blocker Analysis

The findings below are the actual point of this document — read them before assigning work.

1. **C1 is a serialization chokepoint, so keep it small.** Nearly every component reads configuration. If C1's scope creeps (e.g. into a full settings-management system), the whole team idles waiting on it. Land the minimum — a single config source for the values currently hardcoded — and move on.

2. **C3's output schema is the largest external-wait risk.** The Software sub-team's dashboard work depends entirely on knowing the DS output column contract, and they are not part of this repo's DS phasing — they're a different sub-team on a different timeline. Publish C3's schema (with a sample fixture CSV) as early in Phase 1 as possible, even before C4/C5/C6 are fully consolidated, so UI work can start against the contract instead of waiting for the full pipeline to be "done."

3. **The weather-provider decision must not gate C8.** It's still genuinely unresolved (PRD §7.1) — Synoptic's free-tier limits are real, NOAA is unvalidated. C4's adapter-interface design exists specifically so C8 can build against the current Synoptic provider (or a mock implementing the same interface) and absorb a provider switch later without re-architecting the corridor pipeline.

4. **Don't let a dev sit idle waiting on C5 to start C7.** C7's actual change (swap the ampacity formula) is small, but it's gated on C5 landing first. Whoever's slated for C7 should pick up C6 or start scaffolding C8 in the meantime rather than waiting.

5. **Historical data for C9/C10 has lead time that Phase ordering alone doesn't solve.** Both Phase 4 components need an accumulated historical weather record to train against. If data collection only starts when Phase 4 begins, Phase 4 stalls immediately on a data-volume problem. Mitigation: as part of C4 (Phase 2), start a background historical pull/archive job so data is accruing well before Phase 4 work begins.

## 6. Parallelization Summary

Read alongside each component's **Parallel-safe with** field in its spec.

| Can run simultaneously | Why |
|---|---|
| C4, C5, C6 (Phase 2) | No shared files, no shared functions — only the C2/C3 contract in common |
| C7, C8 (Phase 3) | Independent dependency chains (C7 ← C5; C8 ← C4+C5), no shared files |
| C1 + early C3 schema drafting | C3's schema doesn't strictly need C1 finished, just needs C2's contract |
| Historical data collection (part of C4) + C6 | Both Phase 2, no interaction |

| Should NOT start until dependency lands | Reason |
|---|---|
| C4, C5, C6 before C1/C2 | Would build against config values and column names likely to change |
| C8 before C4 + C5 | Needs both a weather source and an ampacity function per corridor point |
| C9 before C4 + C5 (+ accumulating history) | Needs features and training data volume |
| C10 before C7 | Builds on the gating framework C7 establishes |

## 7. References

- `PRD.md` — requirements and open decisions this roadmap builds toward
- `specs/README.md` — component index and spec template
- `System Design Report.md` §3.3 (test plan), Appendix B (WBS) — original task breakdown this roadmap supersedes for DS-specific sequencing
