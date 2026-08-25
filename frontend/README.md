# Frontend — DLR UI Dashboard

**Status:** Not started. This is a structural placeholder, not a scaffolded app.

**Owner:** Software sub-team.

**Planned stack:** React, per the Bill of Materials in `docs/System Design Report.md` Appendix E.

**Purpose:** The real-time UI dashboard described in `docs/Project Definition.md` and `docs/System Design Report.md` — monitors live line conditions, visualizes dynamic vs. static capacity, and surfaces forecasted ratings, anomaly/fallback status, and trusted-duration windows to grid operators. Consumes data from `api/` (or directly from `backend/`'s output files, until `api/` exists).

**Before writing code here:** see `docs/frontend/README.md` for the documentation convention to follow (mirrors `docs/data-science/`'s PRD → ROADMAP → component specs structure) so this subsystem gets the same phased, dependency-aware treatment the DS subsystem already has.
