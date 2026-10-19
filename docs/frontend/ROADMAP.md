<!-- generated-by: gsd-doc-writer -->
# Software Subsystem — Implementation Roadmap

**Status:** Internal engineering reference, companion to `PRD.md` and `specs/`. Defines build order, dependencies, and where parallel work is and isn't safe. Not a course deliverable and not a calendar — no dates. Effort sizes (S/M/L) are relative complexity, not time estimates; the team should size against its own velocity. **All components are Not started.**

**Last reviewed against repo state:** 2026-10-12 (per-city scope change; `docs/data-science/decisions/point_scope.md`)

---

## 1. Why This Ordering

`frontend/` and `api/` are empty placeholders, so the whole subsystem is greenfield. The facts that shape the order come from outside it:

1. **The DS contract is the only fixed input.** The sole committed data is the 10-row fixture `data/fixtures/sample_pipeline_output.csv`; `outputs/` is gitignored, so a fresh clone has nothing else. The v1 schema (`docs/data-science/schema/pipeline_output_v1.md`) covers current weather, `dlr_amps`, headroom and an uplift flag — but **not** forecast, trusted duration, fallback/anomaly status, sag, location, or the static rating (PRD §8, gaps G1–G8). So the views that the v1 export fully supports (current limit, weather, DLR-vs-static chart) can start now; the forecast and anomaly/fallback views are externally blocked on DS.
2. **Two small decisions gate everything.** What a "location" is (PRD OD-1, now narrowed: DS rates four independent city points and corridors are retired) and the front-end stack (OD-11) must be settled before the API's routes and the UI's component choices harden. They are cheap to decide and expensive to reverse. What remains of OD-1 is how a station file maps to a city and whether a per-station view exists.
3. **Least→most dependent.** Foundation (data access, shell) first; then views backed by data that exists; then views waiting on DS; then cross-team integration and the course test plan last, because they need everything else.

Mirroring `docs/data-science/ROADMAP.md`: formalizing the contract the UI reads is the cheapest, highest-leverage first move, because it is what lets several people build panels in parallel without colliding.

## 2. Component Model

| ID | Component | Phase | Effort | Status | WBS |
|---|---|---|---|---|---|
| F1 | Data Access & API Layer | 1 | M | Not started | 4.2.1 |
| F2 | Dashboard Shell & Location Selection | 1 | M | Not started | 4.1.1, 4.1.2 |
| F3 | Line Status & Current Conditions View | 2 | S | Not started | 4.1.3 (current-value part) |
| F4 | DLR vs. Static Capacity Chart | 2 | M | Not started | 4.1.3 |
| F5 | Forecast & Trusted-Duration View | 3 | M | Not started (externally blocked) | 4.1.4 |
| F6 | Anomaly & Fallback Status Indicators | 3 | M | Not started (externally blocked) | 4.1.5 |
| F7 | PSS/E Output Integration | 4 | L | Not started (contract undefined) | 4.2.2 |
| F8 | Integration, E2E & Usability Validation | 4 | M | Not started | 4.2.3, 4.3.4 |

Full detail per component: `specs/F1-data-access-api.md` through `specs/F8-integration-validation.md`. The WBS column maps to Appendix B of `System Design Report.md`; F3 has no dedicated WBS line and is split out because it is the first end-to-end slice (see §4 Phase 2).

## 3. Dependency Graph

```
 DS contract (C2/C3 schema + fixture)  ── exists today
        │
        ├──> F1 Data Access & API ────┬──> F3 Line Status ──────────┐
        │                             ├──> F4 DLR vs Static Chart ──┤
 [OD-1, OD-11 decided]                │                             │
        │                             ├──> F5 Forecast/Trusted ─────┤──> F8 Integration,
        └──> F2 Shell & Location ─────┤        ▲                    │      E2E & Usability
                                      ├──> F6 Anomaly/Fallback ─────┤
                                      │        ▲                    │
                                      └──> F7 PSS/E (soft) ─────────┘
                                               ▲
 DS contract extension (G2–G4, G8) ────────────┘  (F5, F6)
 Power Systems contract (OD-9) ────────────────────  (F7)
```

- **Hard dependencies:** F1 and F2 both must land before any view (F3–F7). F8 needs F1–F6. F7 is a **soft** dependency of F8: only F8's PSS/E leg waits on it.
- **External dependencies (not components in this repo):** F5 and F6 also wait on DS exporting the columns in PRD §8; F7 waits on a Power Systems interface contract.
- **Critical path:** F2 → F4 → F8 for what can be done today; **F5/F6's external DS dependency is the long pole** (it may arrive after everything else).
- **Cross-team unblock path:** the DS contract-extension request (PRD §8) → F5, F6.
- Anything not connected by an arrow is fair game to build concurrently.

## 4. Phases

### Phase 1 — Foundation (F1, F2)

Lowest complexity of cross-cutting work, highest fan-out: every view reads through F1 and sits inside F2's shell. Deliberately a serialization point — land the data layer's shape and the shell's layout before panels are built against them.

- **F1** defines the dashboard's one way of reading DS output: a Flask BFF (`api/`) that reads the fixture (and, when present, pipeline output files), normalizes timestamps and nulls, and exposes it to a thin client in `frontend/`, per city (four points; no corridor aggregate). Fixture-first, so everything downstream can start without a Synoptic token or a pipeline run.
- **F2** is the operator-workflow analysis and wireframes (WBS 4.1.1, 4.1.2), plus the app shell: layout slots for each panel, the preset-location selector, global status banner placement, and the ISO 9241 conventions (typography, color/alert conventions, timezone labelling) every panel reuses. Its design deliverables need no code and can start immediately.

### Phase 2 — Core Views (F3, F4)

Two independent views, **fully parallel**, both supportable by the v1 export alone.

- **F3** is the first vertical slice: select a city → see the current dynamic limit, that city's own static limit, weather. Smallest effort; it proves F1 + F2 end to end early. Sag (SW-F4) is gated on OD-4 and is not required to ship F3.
- **F4** is the DLR-vs-static time series (WBS 4.1.3): the core visual argument of the whole project. Includes how the lower-DLR case is shown (OD-5).

### Phase 3 — Predictive & Safety Views (F5, F6)

Highest external dependency — deliberately after the views that can be completed without DS changes.

- **F5** needs DS forecast columns exported (G3) and a decided definition of "trusted duration" (OD-3).
- **F6** needs DS fallback/anomaly status exported (G2) and OD-6 settled so the UI can state which rating basis is in effect. F6 is the **safety-critical** view (fail-safe is the project's ethical core) and should get the most review.

Both can be started against a **mock** of the extended fixture whose column names DS has agreed to — see Finding 2.

### Phase 4 — Integration & Validation (F7, F8)

- **F7** has no interface to build against (OD-9) and is the largest unknown; it stays a placeholder until Power Systems and DS agree a contract.
- **F8** is the course test plan: weather change → pipeline → dashboard within the refresh window, no unit errors, no undetected anomalies, outputs consistent with the pipeline (`System Design Report.md` §3.3); plus the ISO 9241 usability review. It needs every view to exist.

## 5. Blocker Analysis

The findings below are the actual point of this document — read them before assigning work.

1. **F1 is a serialization chokepoint, so keep it thin.** Every view reads through it. If scope creeps (auth, caching, live polling, PSS/E proxying) every panel idles. Land the minimum — read fixture/outputs, normalize, serve — and let live-feed work (OD-2) arrive as a later, additive change.

2. **The DS contract extension is the largest external-wait risk.** F5 and F6 — the forecast panel and the anomaly/fallback indicators, half of WBS 4.1 and the safety-critical half — need columns the v1 export does not carry (PRD §8, G2–G4). DS is a different sub-team with its own roadmap, and the extension is not in their component list. **Send the contract request (PRD §8) to DS now**, before F5/F6 are scheduled, and agree on a mock fixture extension so UI work isn't waiting. Do not invent column names in production code.

3. **Confirm the unit of selection (OD-1) and decide the stack (OD-11) before F1/F2 harden.** The per-city contract settles the rating unit as a city, so routes should be per city; a route shaped around `stid` is a rewrite if the station-to-city mapping (G1) lands differently. These two decisions take a meeting, not a sprint — hold it first.

4. **Don't let "trusted duration" gate layout.** OD-3 is genuinely unresolved (10–20 s in `Project Definition.md` vs. minutes–hours in DS). F5's layout, the forecast band, and the "valid until" slot can be built; only the labelled value waits. Whoever owns F5 should not sit idle: start the forecast chart.

5. **Sag has no producer.** The mock-up shows it; nothing computes it (OD-4). F3 must not wait on it. Raise it with the team (and Power Systems / DS) as a scope decision: build, source, or drop it from the dashboard.

6. **The UI must not silently "fix" DS output.** The committed outputs contain constant solar values, empty humidity, DLR below static, and headroom of 200%+ (PRD §9). The right response is to display faithfully (SW-NF4, SW-NF5) and report to DS — not to clamp, fill, or recompute in the UI. F1 owns the null/format handling in one place so no panel re-derives it.

7. **Staffing limits the parallelism on paper.** The Linear Responsibility Chart (`System Design Report.md` Appendix C) lists the same single primary owner (Allie) for every Software-sub-team task, 4.1.1 through 4.3.4, with others in support or review roles. The "can run simultaneously" table below describes which work is *independent*, not how many people are assigned; if the team does not add contributors, treat it as an order-of-attack guide. Reassign explicitly if the parallel split in §6 is to be used.

8. **F4 and F5 share a chart.** Both draw time series with a limit line and a band. They are separate WBS items and separate files, but agree a shared chart wrapper (axes, timezone, units, null handling) in F2 so they don't diverge — a contract, not a blocker.

9. **The per-city result has no export yet.** DS rates each city independently (`city_rating.rate_city`) but returns the result as an in-process dict (plus, optionally, one archive row); the four cities' status, alerts and fallback are not in any file feed a BFF can read. This is the same external wait as Finding 2, now stated per city. Do not synthesize a four-city view from the station CSVs, and do not add a corridor-style aggregate (`min` or bottleneck) in the UI.

## 6. Parallelization Summary

Read alongside each component's **Parallel-safe with** field in its spec.

| Can run simultaneously | Why |
|---|---|
| F1, F2 (Phase 1) | Data layer vs. layout/wireframes; only the OD-1 decision in common. F2's wireframes and ISO 9241 analysis need no code. |
| F3, F4 (Phase 2) | Independent panels reading the same F1 view-model; no shared files beyond the shell's layout slots |
| F5, F6 (Phase 3) | Independent panels, each against its own mock fixture extension |
| F3/F4 + DS contract-extension negotiation | The request to DS costs no build time and shortens the Phase 3 wait |
| F7 requirements discussion + anything | Pure coordination with Power Systems; no code |
| F1 + early F2 wireframes + OD-1/OD-11 decision | See Finding 3 |

| Should NOT start until dependency lands | Reason |
|---|---|
| F1 routes before OD-1 (remaining part) | Routes are per city, but the station-to-city mapping (G1) and any per-station view are undecided |
| F3–F7 before F1 + F2 | No data layer or shell to build on; panels would each invent their own parsing and layout |
| F5, F6 production code before DS agrees the columns | Would hard-code guessed field names (PRD §8) |
| F6's "rating basis" wording before OD-6 | The UI must not claim "static rating in effect" when DS's gate fell back to a different basis (G5 reports `min(computed, static)`) |
| F7 before OD-9 | Nothing to integrate against |
| F8 before F1–F6 | Needs every view to exist; its PSS/E leg additionally waits on F7 |

## 7. References

- `PRD.md` — requirements, open decisions, DS contract requests
- `specs/README.md` — component index and spec template
- `docs/System Design Report.md` §3.3 (test plan), Appendix B (WBS 4.0), Appendix C (LRC) — original task breakdown this roadmap supersedes for Software-specific sequencing
- `docs/data-science/decisions/point_scope.md` — per-city scope contract (corridors retired 2026-10-12)
- `docs/data-science/ROADMAP.md` (Finding 2, "C3's output schema is the largest external-wait risk") — the DS-side view of this same dependency
