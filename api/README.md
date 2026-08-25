# API — Backend-for-Frontend Layer

**Status:** Not started. This is a structural placeholder, not a scaffolded service.

**Owner:** Software sub-team.

**Planned stack:** Flask, per the Bill of Materials in `docs/System Design Report.md` Appendix E.

**Purpose:** Serves `frontend/`'s dashboard from `backend/`'s DS pipeline output (currently flat files under `outputs/` — see `docs/data-science/specs/C3-export-visualization.md` for the export schema this layer would read from). Not yet decided: whether this is a thin file-serving layer, a live-polling service, or something that also proxies PSS/E outputs from the Power Systems sub-team.

**Before writing code here:** see `docs/frontend/README.md` for the documentation convention to follow (mirrors `docs/data-science/`'s PRD → ROADMAP → component specs structure).
