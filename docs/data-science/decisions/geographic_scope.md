# Geographic / Corridor Scope Decision Log

**Status:** Open — recommendation drafted below, awaiting team ratification. Answers the geographic/corridor scope conflict flagged in `.planning/PROJECT.md` Key Decisions, `.planning/INGEST-CONFLICTS.md`, and `PRD.md` §10 Documentation Discrepancies (row 5).

**Purpose:** Same working-log format as `data_provider.md` — lay out the evidence for each of the three conflicting location sets found in this repo, then propose one authoritative scope for the team to confirm or override. Unlike `data_provider.md`, this one has a strong enough evidentiary trail to recommend an answer rather than leave it fully open — but the recommendation is a proposal, not a unilateral decision; the team should ratify or override it before it's treated as settled in `PROJECT.md`.

## The Conflict

Three same-precedence-tier documents/artifacts define three different, non-overlapping location scopes for this project:

| Source | Type | Locations | Overlap with Project Definition.md |
|---|---|---|---|
| `docs/Project Definition.md` §"Input/Output Specifications" (lines 79–86) | Course deliverable (graded) | Austin, Corpus Christi, Midland, El Paso — 4 cities, each with a documented input-range and static-rating bound table | — (this is the baseline) |
| `backend/config.py::STATIC_RATINGS` (via `docs/data-science/specs/C1-configuration.md`) | SPEC / working code | Houston, Austin, Dallas, Fort Worth, San Antonio — 5 different cities | Austin only |
| `backend/station_explorer.py::CORRIDORS` (via `docs/data-science/specs/C8-corridor-discretization.md`) | SPEC / working code | Panhandle Export, Permian Basin 345kV, Sweetwater Wind Hub, Big Spring Corridor, West TX to Hill Country — 5 West-Texas transmission corridors (not cities) | none |

A fourth, smaller data point corroborates rather than complicates: `backend/dlr_pipeline.py`'s `__main__` block (line ~439) has a dead-code stub, `STATIC_RATINGS = {"AUSTIN": None, "EL_PASO": None, "MIDLAND": None}` — never read by `run_pipeline` — that is a *subset* of Project Definition.md's four cities (missing only Corpus Christi). This reads as an earlier, abandoned attempt to align the code with the real spec, not a fourth competing scope.

## Evidence Considered

**Project Definition.md is the graded course deliverable**, not an internal working document. Its I/O Specification Table is a structured, fully-populated table (temperature/wind/solar ranges, static-limit bounds, trusted-duration values, all four cities) — this is the kind of table a grader checks the implementation against, and per `PRD.md` §10 it is already explicitly documented, by the team, as the target the code does not currently hit.

**`PRD.md` §10 (Documentation Discrepancies) already adopted the 4-city scope as ground truth**, before this decision doc existed. Its row on this exact conflict states: "No code implements this four-city list, and three different, mutually inconsistent location sets exist instead" — followed by a description of `config.py`'s 5 cities and `station_explorer.py`'s 5 corridors as the *deviations*, not as competing specs of equal standing. `data_provider.md` (this directory) independently reached the same conclusion in its own requirements section, footnoting that the code's "West-Texas-only framing and mismatched city lists...never actually matched this spec."

**`config.py`'s 5-city list is itself internally flagged as incomplete and unwired**: `C1-configuration.md` states plainly that "nothing selects a specific city's `STATIC_RATINGS` entry per pipeline run" — every run currently uses a uniform fallback regardless of location. This is a lookup table awaiting a decision, not a settled scope choice. Its city selection (Houston, Dallas, Fort Worth, San Antonio in place of Corpus Christi, Midland, El Paso) also isn't traceable to any documented requirement — `C1-configuration.md`'s own sourcing notes describe a static-rating *research* pass (finding citable ERCOT/PUCT/FERC values for major metros), not a scope decision.

**`station_explorer.py`'s West-Texas corridors are pre-C8 exploratory tooling, not C8 itself.** `C8-corridor-discretization.md` is explicit: "This is not corridor discretization — there's no notion of a line, a route, or multiple points along one." The five corridor names rank station proximity to a single reference point each; they don't discretize a transmission line into multiple points the way C8's actual acceptance criteria require. There's no documented rationale tying these five specific corridors to the four-city spec, or to any requirement at all — they look like ad hoc West Texas exploration (consistent with `config.py::DEFAULT_CONDUCTOR_CONFIG_KWARGS`'s "West Texas Permian Basin avg elevation" comment, also flagged in `PRD.md` §10 as evidence of an implicit, undocumented West-Texas narrowing).

## Recommendation

**Adopt `Project Definition.md`'s four-city scope — Austin, Corpus Christi, Midland, El Paso — as the authoritative location scope for `C1-configuration.md::STATIC_RATINGS` and any future per-location wiring (the DS-F5 gap).** This is not a new decision so much as ratifying what `PRD.md` §10 and `data_provider.md` have already treated as true — this document exists to make it official rather than an implicit convention repeated across docs without ever being formally settled.

Concretely, this means:

1. **`backend/config.py::STATIC_RATINGS`** should be re-keyed to Austin, Corpus Christi, Midland, El Paso, sourced from `Project Definition.md`'s own static-rating bounds (or better citations if the team wants to re-derive them, the way `C1`'s original 5-city table cited ERCOT/PUCT/FERC filings) — replacing, not supplementing, the current 5-city table. This closes the DS-F5 blocker recorded in `REQUIREMENTS.md`.
2. **`backend/station_explorer.py::CORRIDORS`** should **not** simply be re-pointed at the four cities as-is — a city is a point (for weather/rating lookup), while a corridor for C8's purposes needs two *endpoints* (a transmission line segment) to discretize into multiple points. Mapping the four cities to actual corridor endpoints is a real, still-open design question this document does not resolve (see Open Questions below). The five West-Texas corridors should be treated as legacy exploratory artifacts to retire from the authoritative scope, not repurposed by default.
3. **`backend/dlr_pipeline.py`'s dead `STATIC_RATINGS` stub** should either be deleted (now redundant once `config.py` carries the real four-city table) or, if kept temporarily, extended to add Corpus Christi so it's at least internally consistent while it exists.
4. **`PROJECT.md` Key Decisions** should be updated from "OPEN" to reflect this resolution once the team ratifies it, and `STATE.md`'s Phase 3 blocker note should be cleared.

## Open Questions (explicitly not decided here)

- **City→corridor mapping.** C8 needs transmission-line endpoints, not city points. Which two of the four cities (or which city + which substation) define each corridor C8 will discretize? None of the three source documents answer this — it requires either real ERCOT transmission-line data or a team decision on synthetic endpoints, same gap `C8-corridor-discretization.md`'s own Open Questions section already flags ("Real geometry source...no such data source exists in this repo today").
- **Re-sourcing the four cities' static ratings.** `Project Definition.md`'s table has bound *ranges*, not necessarily citable, single point-value static ratings in the format `config.py::STATIC_RATINGS` currently uses (a single float per city, following `C1`'s existing convention). Whether to use the table's range midpoint/bound, or re-run the citation research `C1` did for the original 5-city table against these four cities instead, is a team call.
- **Disposition of the West-Texas corridor list.** Retiring it from the *authoritative* scope doesn't necessarily mean deleting the code — it may still be useful as a secondary/future corridor set once the four required cities are handled, if the team wants broader coverage later. Not decided here.

## References

- `docs/Project Definition.md` §"Input/Output Specifications" (lines 76–88) — the four-city table
- `docs/data-science/PRD.md` §10 Documentation Discrepancies (row 5) — the team's own prior flagging of this exact conflict
- `docs/data-science/specs/C1-configuration.md` — current 5-city `STATIC_RATINGS`, and confirmation that per-city selection isn't wired
- `docs/data-science/specs/C8-corridor-discretization.md` — confirmation that `station_explorer.py::CORRIDORS` is proximity-ranking, not corridor discretization
- `backend/station_explorer.py`, `backend/config.py`, `backend/dlr_pipeline.py` — the three/four conflicting artifacts themselves
- `.planning/PROJECT.md` Key Decisions, `.planning/INGEST-CONFLICTS.md` — where this conflict was first surfaced during GSD doc ingest
- `.planning/REQUIREMENTS.md` DS-F5 — the requirement blocked on this decision
