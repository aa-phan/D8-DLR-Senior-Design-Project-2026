# C8 — Corridor Spatial Discretization

**Phase:** 3 (Safety & Spatial) · **Effort:** L · **Status:** Not started. The System Design Report describes this as completed risk-reduction work (§3.2, "Weather Data and Transmission Corridor Mapping") — that claim is inaccurate; see `PRD.md` §9 Documentation Discrepancies.

**Responsibility:** Represent a transmission corridor as multiple geographic points along its real (or, initially, synthetic) route between substation endpoints, compute ampacity independently at each point, and report the corridor-level rating as the **minimum** across all points — the true thermal bottleneck, since a line is only as strong as its weakest span.

## Current Implementation

None. The closest existing artifact is `src/station_explorer.py::CORRIDORS` — five hardcoded `(lat, lon)` tuples (Panhandle Export, Permian Basin 345kV, Sweetwater Wind Hub, Big Spring Corridor, West TX to Hill Country) used only to **rank nearby stations by proximity to a single reference point per corridor**. This is not corridor discretization — there's no notion of a line, a route, or multiple points along one.

## Interface & Data Contract

Not yet designed. Should minimally need:

- A corridor definition: substation endpoints (lat/lon) at minimum; the System Design Report's stated future step is real transmission-line geometry (e.g. GIS shapefiles) rather than a straight line between endpoints — the SDR explicitly calls the current five-point setup a "development and validation environment" using "synthetically connected substation coordinates," which matches: no such synthetic-line generator exists in code either, so this component starts from zero on both the synthetic and real geometry paths.
- A discretization step: N points along the corridor (interpolated or from real geometry).
- Per-point weather (via C4) and per-point ampacity (via C5).
- A reduction step: corridor-level rating = `min()` across points, analogous to C6's existing hourly `.min()` resampling pattern (`src/ercot_dlr_merger.py::process_dlr_to_hourly`) — same "weakest link" principle, different axis (space vs. time).

## Blocked by

**C4** (weather ingestion, called once per corridor point) and **C5** (ampacity computation, called once per corridor point). Explicitly **not** blocked by C7 — independent tracks per `ROADMAP.md` §4 Phase 3.

Also implicitly depends on the weather-provider decision remaining unresolved being a non-issue — see `PRD.md` §7.1 and C4's adapter-interface mitigation. C8 should build against C4's interface, not directly against Synoptic, so it's insulated from that decision.

## Blocks

Nothing else in this roadmap directly depends on C8, though it's the component the System Design Report currently (inaccurately) claims already exists, so landing it is what would make that section of the SDR true.

## Parallel-safe with

**C7** — no shared files, independent dependency chains.

## Known Issues

Not applicable — no implementation exists yet to have issues.

## Acceptance Criteria

Adapted from System Design Report §3.3's stated (but not yet actually implemented) validation plan:

- Running the full spatial pipeline on a synthetic corridor confirms weather data is correctly fetched and assigned to each corridor point, and fed into the IEEE 738 calculator (C5) at each point.
- Minimum-ampacity logic is verified by artificially "cooling" one corridor segment (e.g. injecting a lower wind value at one point) and confirming the system correctly identifies it as the bottleneck.
- Once real transmission-line geometry is available (out of scope for the initial build): rerun against actual ERCOT transmission data and confirm results are reasonable and consistent with published SLR values for those lines.

## Open Questions

- Real geometry source — the System Design Report mentions GIS shapefiles as the eventual replacement for synthetic substation-to-substation lines; no such data source exists in this repo today. Where does it come from?
- How many points per corridor is enough to catch a real bottleneck without excessive API calls against a rate-limited weather provider (see C4's known issues on Synoptic's free-tier limits)?
- Does C8 call C4/C5 per-point synchronously, or does it need a batched/parallel fetch pattern given N points × however many corridors?
