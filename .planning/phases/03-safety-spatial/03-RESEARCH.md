# Phase 3: Safety & Spatial - Research

**Researched:** 2026-09-03
**Domain:** Backend physics/data pipeline unification (safety-gate ↔ thermal model) + geographic corridor discretization, Python/pandas/numpy
**Confidence:** HIGH (code-derived findings) / LOW (external facts pulled via unconfigured WebSearch — see tags below)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-00:** The 4-city scope (Austin, Corpus Christi, Midland, El Paso) is authoritative, per `docs/data-science/decisions/geographic_scope.md` — already implemented in `backend/config.py::STATIC_RATINGS`. Carried forward as locked context, not re-discussed.
- **D-01:** Corridors are defined by pairing the 4 cities into 2 line segments: **Austin↔Corpus Christi** and **Midland↔El Paso**. Reversibility: reversible.
- **D-02:** Corridor endpoint coordinates use **city-center lat/lon** (same precision level as `station_explorer.py`'s existing `CORRIDORS` dict), not a specific substation lookup. Reversibility: reversible.
- **D-03:** Corridor geometry for Phase 3 is **synthetic straight-line (geodesic) interpolation** between the two city endpoints. Real GIS transmission-line geometry is explicitly deferred. Reversibility: reversible.
- **D-04:** Each corridor is discretized into **5 points** (2 endpoints + 3 interior, evenly spaced along the line). Reversibility: reversible — a constant.
- **D-05:** Each of the 5 corridor points gets **its own independent weather fetch** (no nearest-station sharing across points) — **10 weather fetches per run** across the 2 corridors, before the candidate-probe fallback (D-08). Reversibility: reversible.
- **D-06:** Use a **broadened Synoptic query (not restricted to the WTM network)** with a per-location candidate-probe fallback, instead of adopting `data_provider.md`'s full multi-provider composition (TCEQ CAMS + NSRDB + ASOS + Open-Meteo) for Phase 3. Live-verified: current token sees 424 networks nationally; solar-tagged stations within 50km — Austin 628, Corpus Christi 64, Midland 30, El Paso 94; live pull success rate — Austin 75%, Corpus Christi 25%, Midland 25%, El Paso 38%. `data_provider.md`'s full composition is deferred (likely Phase 4). Reversibility: costly but additive.
- **D-07:** `backend/weather_provider.py::fetch_weather`'s station-ID-based signature is **preserved for callers**; a new internal station→lat/lon mapping layer resolves IDs before any future grid-based provider call. Reversibility: reversible.
- **D-08:** Per-location weather lookup probes candidate stations **nearest-5 first**; if all 5 return no usable (non-null) data, expand to the next 5 nearest (10 total) before giving up. Reversibility: reversible.
- **D-09:** If all 10 nearest candidates are exhausted with no usable data for a given location, **fall back to the static rating** for that point — treated the same as any other data-loss gate (DS-NF5), not a special case. Reversibility: reversible.

### Claude's Discretion

- Exact interior-point spacing algorithm for the 5-point geodesic interpolation (equal-distance vs. equal-fraction-of-great-circle) — left to planner/implementer as a standard interpolation choice.
- Whether the station→lat/lon mapping layer (D-07) is a new module, a method on `weather_provider.py`, or folded into `station_explorer.py` — an implementation-location choice.
- Exact fallback-target semantics for G1/G2 vs. G3/G4 in `DLRSafetyMonitor` — investigate against C7 spec's own Open Questions before locking behavior. **Resolved by this research — see "G1/G2 vs. G3/G4 Fallback Semantics" below.**
- Gate-2 test contradiction fix approach — same, resolved below.

### Deferred Ideas (OUT OF SCOPE)

- **Full multi-provider weather composition** (TCEQ CAMS + NSRDB PSM v4 + ASOS 1-minute + Open-Meteo) — deferred pending evidence the broadened-Synoptic fallback-probe approach (D-06) proves insufficient. Natural Phase 4 candidate (overlaps C9/C10 historical-backfill needs).
- **G1/G2 vs. G3/G4 fallback-target semantics** and **gate-2 test contradiction** were listed as deferred-from-discussion in CONTEXT.md, but explicitly assigned to this research pass to resolve — see below. Not out of phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DS-F7 | Detect unreliable/anomalous inputs and fall back to SLR (Static Line Rating) | "C7 Wiring: `_compute_ampacity` → `thermal_model.ieee738_ampacity`" and "G1/G2 vs. G3/G4 Fallback Semantics" sections give exact current signatures, the disconnect, and a resolved fallback-target recommendation |
| DS-F10 | Discretize a transmission corridor into multiple geographic points and take the minimum ampacity as the corridor-level rating | "C8 Corridor Discretization" section gives the interpolation approach, per-corridor `line_azimuth` finding, station-resolution layer design, and the `.min()` reduction pattern to reuse |
| DS-NF5 | Fail-safe by default — every data-loss/implausibility case must resolve toward static rating, never an optimistic guess | "G1/G2 vs. G3/G4 Fallback Semantics" section directly addresses this; "RATING_BOUNDS Must Be Recalibrated" pitfall prevents a silent failure mode that would otherwise make G4 reject valid data for 3 of 4 cities post-wiring |
</phase_requirements>

## Summary

Phase 3 is two small, mechanically well-scoped changes to an already-correct codebase, not a design-from-scratch effort. C7's fix is a ~10-line wiring change: replace `DLRSafetyMonitor._compute_ampacity`'s placeholder linear formula with a call into the already-tested, bug-fixed `thermal_model.ieee738_ampacity`. C8 is new: a corridor discretization module that generates 5 geodesic points per corridor, resolves each to a nearby weather station (reusing `station_explorer.py`'s haversine pattern, generalized from "rank stations near 5 fixed points" to "rank stations near any point"), computes ampacity per point via the same `ieee738_ampacity` call C7 now uses, and reduces to a corridor-level rating via `.min()` — directly analogous to `ercot_dlr_merger.py::process_dlr_to_hourly`'s existing `.min()` resampling ("weakest link" on the time axis; C8 is the same principle on the space axis).

Direct inspection of the code and tests resolved both C7 gray areas the planner needs locked before writing tasks. First, `SafetyMonitor_TestSuite.py::test_gate_2_fails_when_link_status_not_ok` is a plain copy-paste bug, not a hint at a richer status shape — it is the only one of 6 fallback-path tests in the suite that asserts `status == "ok"`; every sibling gate test (G1, G3, G4) correctly asserts `status == "fallback"`, and `_fallback()` unconditionally sets `status = "fallback"` with no code path that could ever produce the asserted combination. Fix: change the one assertion to `"fallback"`. Second, the G1/G2-vs-G3/G4 fallback-target question is resolved by the phase's own ROADMAP Success Criteria, which explicitly lists "missing sensor" and "broken communication link" (G1/G2) alongside range/plausibility failures as cases that must fall back "toward the static rating, never toward an optimistic guess" — this is stronger and more specific than C7's spec-level "possibly intentional" hedge, and the current code's G1/G2→`last_good_rating` behavior does not straightforwardly satisfy it (a stale `last_good_rating` from a strong-wind reading, held through an extended comms outage while real conditions calmed, is exactly the "optimistic guess" DS-NF5 forbids). Recommendation below.

A significant, previously undocumented finding from this research: `DLRSafetyMonitor.RATING_BOUNDS = (400, 1800)` (the G4 plausibility gate) is incompatible with 3 of the 4 newly-adopted city static ratings — Austin (1900 A), Corpus Christi (3000 A), and Midland (1800 A, boundary case) all sit at or above the current upper bound. Once C7 is wired to the real thermal model and used against real per-city data, G4 will reject essentially all plausible Corpus Christi and Austin readings as "implausible," permanently forcing those two cities into fallback. This must be fixed as part of the C7 wiring work, not left as a follow-on — see "Common Pitfalls" below.

**Primary recommendation:** Wire `DLRSafetyMonitor._compute_ampacity` to call `thermal_model.ieee738_ampacity` directly (no new abstraction needed); widen/recalibrate `RATING_BOUNDS` to the documented per-city range before doing so; fix the one gate-2 test assertion; and build C8 as a new `backend/corridor_discretization.py` module that composes existing `station_explorer.py` (generalized station-ranking), `weather_provider.py` (unchanged interface), and `thermal_model.py` (unchanged) rather than introducing any new external dependency.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Ampacity computation (IEEE 738) | Backend / physics core (`thermal_model.py`) | — | Pure function, no I/O; single source of truth C7 and C8 must both call |
| Safety gating & fallback decision | Backend / orchestration (`DLRSafetyMonitor.py`) | Backend / physics core (calls into `thermal_model.py`) | Gating is a policy layer wrapping the physics core, not a competing implementation of it |
| Weather station discovery & ranking | Backend / data access (`station_explorer.py`) | — | Owns the Synoptic metadata query and haversine-based proximity ranking; must generalize from "rank near 5 fixed points" to "rank near any point" for C8 |
| Weather observation fetch | Backend / data access (`weather_provider.py` → `dlr_pipeline.py::fetch_timeseries`) | — | Provider-agnostic adapter boundary; signature unchanged per D-07 |
| Corridor geometry & discretization | Backend / orchestration (new `corridor_discretization.py`) | Backend / data access (calls station/weather layers) | New C8 component; composes existing layers, owns the interpolation + per-point orchestration + min-reduction |
| Per-location static ratings / corridor endpoints | Backend / configuration (`config.py`) | — | C1's config-centralization convention; corridor endpoint coordinates and (new) per-corridor conductor config belong here, not hardcoded in `station_explorer.py` |

## Standard Stack

### Core

No new external packages are required for this phase. All work reuses libraries already present and imported in `backend/`:

| Library | Version (observed) | Purpose | Why Standard |
|---------|---------|---------|--------------|
| numpy | already imported (`thermal_model.py`, `dlr_pipeline.py`) | Vectorized ampacity math, trig for bearing/geodesic interpolation | Already the project's numeric backbone; no reason to add a geo library for a handful of trig formulas |
| pandas | already imported (`station_explorer.py`, `weather_provider.py`) | Station metadata frames, per-point result assembly | Matches existing station/weather DataFrame conventions |
| requests | already imported (`station_explorer.py`, `dlr_pipeline.py`) | Synoptic HTTP calls (unchanged — D-06/D-07 reuse existing fetch paths) | Already the project's HTTP client |

### Supporting

None needed. `math` (stdlib) is sufficient for the geodesic interpolation and bearing calculation described below — this matches `station_explorer.py::haversine_km`'s existing pattern of using only `math`, not a geo library.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled great-circle interpolation (stdlib `math`) | `geopy.distance.geodesic` / `pyproj` | A new dependency for ~15 lines of standard trig that mirrors the codebase's existing `haversine_km` style; not justified at Texas-corridor scale (a few hundred km) where hand-rolled and library results agree to well under 1 km. **Do not add a geo library for this.** |
| Great-circle (spherical) interpolation | Simple linear lat/lon interpolation | Linear interpolation error at these corridor lengths (Austin↔Corpus Christi ≈280 km, Midland↔El Paso ≈390 km) is negligible for weather-station-selection purposes (sub-km class of error), but "geodesic" is explicitly named in D-03 — implement the standard great-circle intermediate-point formula so the term in the locked decision is met literally, not approximated away |

**Installation:** None required — no new packages.

**Version verification:** N/A — no new packages to verify against a registry this phase.

## Package Legitimacy Audit

**Not applicable this phase.** No new external packages are introduced. All functionality (geodesic interpolation, bearing calculation, nearest-station generalization) is implemented with `math`/`numpy`/`pandas`, all already present and imported elsewhere in `backend/`. The Package Legitimacy Gate protocol was not run because there is nothing to check against a registry.

## Architecture Patterns

### System Architecture Diagram

```
                     ┌─────────────────────────────┐
                     │        config.py (C1)        │
                     │ STATIC_RATINGS (4 cities)     │
                     │ CORRIDOR_ENDPOINTS (2 pairs)  │  <- new, per D-01/D-02
                     │ DEFAULT_CONDUCTOR_CONFIG_...  │
                     └───────────────┬───────────────┘
                                     │ read by
        ┌────────────────────────────┼────────────────────────────┐
        │                             │                             │
        ▼                             ▼                             ▼
┌───────────────┐          ┌─────────────────────┐        ┌──────────────────┐
│ DLRSafetyMonitor│         │ corridor_discretization│      │  dlr_pipeline.py │
│   (C7, fixed)   │         │      .py (C8, new)     │      │ (single-station  │
│                 │         │                         │      │  run_pipeline)   │
│ run_check(data) │         │ 1. interpolate 5 pts    │      └──────────────────┘
│  G1 sensor      │         │    per corridor (D-03/  │
│  G2 link        │         │    D-04)                │
│  G3 range       │         │ 2. per point: resolve   │
│  G4 plausible ──┼────┐    │    nearest station(s)   │
│  G5 delta       │    │    │    (station_explorer,   │
└───────┬─────────┘    │    │    generalized;         │
        │              │    │    D-07/D-08 probe)     │
        │              │    │ 3. per point: fetch     │
        │              │    │    weather (weather_    │
        │              │    │    provider.fetch_      │
        │              │    │    weather, unchanged)  │
        │              │    │ 4. per point: compute   │
        │              │    │    ampacity ────────────┼──┐
        │              │    │ 5. reduce: min() across │  │
        │              │    │    5 points (D-04/D-05, │  │
        │              │    │    analogous to C6's    │  │
        │              │    │    hourly .min())       │  │
        │              │    └─────────────────────────┘  │
        │              │                                  │
        └──────────────┴──────────────────┬───────────────┘
                                           ▼
                            ┌───────────────────────────┐
                            │   thermal_model.py (C5)    │
                            │   ieee738_ampacity()       │
                            │   — single source of truth │
                            │   for every ampacity value │
                            │   computed anywhere in the │
                            │   system                    │
                            └───────────────────────────┘
```

A reader can trace both use cases end to end: C7's `run_check` calls straight down into `ieee738_ampacity` for G4's plausibility check (previously a disconnected placeholder); C8's new module fans out to 5 geodesic points per corridor, each independently resolving a station, fetching weather, and calling the same `ieee738_ampacity`, before reducing with `min()`.

### Recommended Project Structure

```
backend/
├── config.py                    # (existing, extend) STATIC_RATINGS, + new CORRIDOR_ENDPOINTS
├── station_explorer.py          # (existing, extend) + generalized nearest-N-stations function
├── weather_provider.py          # (existing, unchanged interface) fetch_weather(stids, start, end)
├── thermal_model.py             # (existing, unchanged) ieee738_ampacity — single source of truth
├── DLRSafetyMonitor.py          # (existing, fix) _compute_ampacity wired to thermal_model
├── corridor_discretization.py   # (NEW, C8) interpolation + per-point orchestration + min-reduction
└── tests/
    ├── SafetyMonitor_TestSuite.py     # (existing, fix gate-2 test + add wiring-equivalence test)
    ├── thermal_model_test.py          # (existing, unchanged)
    └── corridor_discretization_test.py # (NEW, C8 — no existing coverage, see Runtime/Test Gaps)
```

### Pattern 1: C7 Wiring — `_compute_ampacity` → `thermal_model.ieee738_ampacity`

**What:** Replace the placeholder formula with a direct call into the real thermal model, using the interface mapping already documented in C7's own spec (`wind ≈ wind_perp_ms`, `temp ≈ air_temp`, `solar ≈ solar_radiation`).

**Current placeholder** `[VERIFIED: backend/DLRSafetyMonitor.py:62-64]`:
```python
def _compute_ampacity(self, d):
    # Simplified IEEE 738 — replace with your full thermal model
    return 900 + d["wind"] * 30 - (d["temp"] - 20) * 4 - d["solar"] * 0.05
```

**Real model signature it must call** `[VERIFIED: backend/thermal_model.py:104-110]`:
```python
def ieee738_ampacity(
    T_amb_c: Union[float, np.ndarray],
    wind_perp_ms: Union[float, np.ndarray],
    ghi_wm2: Union[float, np.ndarray],
    conductor: ConductorConfig,
    solar_altitude_deg: float = 45.0,
) -> np.ndarray
```

**When to use:** This is the core Phase 3 fix. `DLRSafetyMonitor` needs a `ConductorConfig` instance available at check time — the C7 spec itself flags this as an open question ("Where does the monitor get a `ConductorConfig` for each check cycle — one global default, or per-location?"). Recommendation: pass a `ConductorConfig` (and optionally `solar_altitude_deg`) into `DLRSafetyMonitor.__init__` alongside `static_rating`, following the same per-location instantiation pattern C8 will need anyway (one monitor instance per corridor/city, each constructed with that location's static rating *and* conductor config — see the `line_azimuth` finding below for why a single global conductor config is not safe to reuse across both corridors).

**Example wiring:**
```python
# Source: derived from backend/thermal_model.py:104-110 (VERIFIED signature)
# and backend/DLRSafetyMonitor.py:13-17 (VERIFIED __init__ signature)
import thermal_model

class DLRSafetyMonitor:
    def __init__(self, static_rating: float, conductor: thermal_model.ConductorConfig,
                 solar_altitude_deg: float = 45.0, logger=None):
        self.static_rating = static_rating
        self.conductor = conductor
        self.solar_altitude_deg = solar_altitude_deg
        self.last_good_rating = static_rating
        self.logger = logger or print

    def _compute_ampacity(self, d):
        return float(thermal_model.ieee738_ampacity(
            T_amb_c=d["temp"],
            wind_perp_ms=d["wind"],
            ghi_wm2=d["solar"],
            conductor=self.conductor,
            solar_altitude_deg=self.solar_altitude_deg,
        ))
```

Note `ieee738_ampacity` returns an `np.ndarray` (even for scalar input, via `np.asarray`) `[VERIFIED: backend/thermal_model.py:128-130,181]` — wrap with `float(...)` so `_compute_ampacity`'s scalar-arithmetic callers (`_gate_plausible`, the `abs(rating - self.last_good_rating)` delta check) keep working exactly as today; every existing test's numeric assertions (e.g. `test_run_check_success_returns_ok`) compare against a plain float.

### Pattern 2: Per-Corridor `line_azimuth` — Do Not Reuse a Single Global Default

**What:** `thermal_model.ConductorConfig.line_azimuth` defaults to `90.0` (an east-west line) `[VERIFIED: backend/thermal_model.py:75,84]`, and `config.py::DEFAULT_CONDUCTOR_CONFIG_KWARGS` currently hardcodes `"line_azimuth": 90.0` `[VERIFIED: backend/config.py:66]`. `perpendicular_wind()` uses this value to compute the cooling-relevant wind component `[VERIFIED: backend/thermal_model.py:22-55]` — an azimuth that's wrong for a corridor's real orientation will systematically bias every ampacity value computed for that corridor, in either direction depending on prevailing wind direction that day.

**Why it matters here:** the two D-01 corridors have very different real bearings. Using the standard initial-bearing (forward azimuth) formula against city-center coordinates:

- Austin `[CITED: docs/data-science/decisions/data_provider.md:166 — (30.27, -97.74), confirmed via a live API call in that document]` → Corpus Christi `[ASSUMED: WebSearch/Wikipedia infobox, LOW confidence per this session's `classify-confidence --provider websearch` result — (27.74, -97.40), not independently verified]`: computed bearing ≈ **173°** (a near north-south line).
- Midland `[ASSUMED: same WebSearch/Wikipedia sourcing, LOW confidence — (32.00, -102.10)]` → El Paso `[ASSUMED: same — (31.76, -106.49)]`: computed bearing ≈ **268°** (a near east-west line — coincidentally close to the existing 90°/270° default's implied orientation).

So the existing default (90°, i.e. east-west) happens to be roughly right for Midland↔El Paso, but badly wrong for Austin↔Corpus Christi (≈173°, i.e. north-south) — reusing one global `ConductorConfig` for both corridors would silently mis-model the Austin↔Corpus Christi corridor's wind cooling by close to the maximum possible error for this formula. **Compute `line_azimuth` per corridor from its actual endpoints; do not reuse `DEFAULT_CONDUCTOR_CONFIG_KWARGS`'s `line_azimuth: 90.0` unmodified for both corridors.**

**Example (standard forward-azimuth / initial-bearing formula, matching `haversine_km`'s stdlib-`math`-only style):**
```python
# Source: standard great-circle initial bearing formula (own derivation,
# not tool-verified against a reference implementation — recommend a
# spot-check against a known bearing calculator during implementation)
import math

def initial_bearing_deg(lat1, lon1, lat2, lon2) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlam = math.radians(lon2 - lon1)
    y = math.sin(dlam) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlam)
    theta = math.atan2(y, x)
    return (math.degrees(theta) + 360) % 360
```

**City-center coordinates used above should be re-verified (or sourced from an authoritative dataset such as the US Census Gazetteer) before being hardcoded into `config.py`** — they are tagged `[ASSUMED]`/LOW confidence in this research because they came from an unconfigured `WebSearch` call (`brave_search`/`exa_search`/`firecrawl` are all `false` in this project's init context), not from a tool this session confirmed as authoritative. Austin's coordinate is the one exception — it is `[CITED]` because it was independently confirmed via a live API call already documented in `data_provider.md`.

### Pattern 3: C8 Corridor Discretization — Compose, Don't Reinvent

**What:** 5-point geodesic interpolation between corridor endpoints, per-point station resolution + weather fetch + ampacity, then `min()` reduction — reusing three already-existing patterns rather than building new ones.

**Geodesic interpolation (great-circle intermediate point), satisfying D-03/D-04:**
```python
# Source: standard great-circle intermediate-point formula, own derivation
# (own trig, cross-check against a reference geodesic tool recommended
# before treating output coordinates as final)
import math

def interpolate_great_circle(lat1, lon1, lat2, lon2, fraction: float):
    """fraction=0.0 -> point 1, fraction=1.0 -> point 2."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    lam1, lam2 = math.radians(lon1), math.radians(lon2)
    d = 2 * math.asin(math.sqrt(
        math.sin((phi2 - phi1) / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin((lam2 - lam1) / 2) ** 2
    ))
    if d == 0:
        return (lat1, lon1)
    a = math.sin((1 - fraction) * d) / math.sin(d)
    b = math.sin(fraction * d) / math.sin(d)
    x = a * math.cos(phi1) * math.cos(lam1) + b * math.cos(phi2) * math.cos(lam2)
    y = a * math.cos(phi1) * math.sin(lam1) + b * math.cos(phi2) * math.sin(lam2)
    z = a * math.sin(phi1) + b * math.sin(phi2)
    phi_i = math.atan2(z, math.sqrt(x ** 2 + y ** 2))
    lam_i = math.atan2(y, x)
    return (math.degrees(phi_i), math.degrees(lam_i))

def discretize_corridor(lat1, lon1, lat2, lon2, n_points: int = 5):
    return [interpolate_great_circle(lat1, lon1, lat2, lon2, i / (n_points - 1))
            for i in range(n_points)]
```
This is `d` = the pre-existing `haversine_km` central angle in a different form — consistent with the codebase's existing distance-math style `[VERIFIED: backend/station_explorer.py:17-23]`.

**Generalizing station-proximity ranking** (`station_explorer.py::rank_by_corridor` currently ranks against the 5 fixed legacy `CORRIDORS` points only `[VERIFIED: backend/station_explorer.py:9-15,75-88]`) **to an arbitrary point**, satisfying D-07/D-08:
```python
# Source: generalization of backend/station_explorer.py::rank_by_corridor
# (VERIFIED pattern at station_explorer.py:75-88), parameterized on an
# arbitrary (lat, lon) instead of the fixed CORRIDORS dict
def nearest_stations(stations: pd.DataFrame, lat: float, lon: float, n: int = 5) -> pd.DataFrame:
    stations = stations.copy()
    stations["km_to_point"] = stations.apply(
        lambda r: haversine_km(r["lat"], r["lon"], lat, lon), axis=1)
    return stations.sort_values("km_to_point").head(n)
```
D-08's nearest-5-then-10 probe is then: call `nearest_stations(..., n=5)`, attempt `weather_provider.fetch_weather` for those 5 `stid`s, and if every returned row for every variable is null, call `nearest_stations(..., n=10)` and probe the next 5 (indices 5:10).

**Min-reduction across the 5 points**, analogous to C6's existing pattern `[VERIFIED: backend/ercot_dlr_merger.py:33-40]`:
```python
# Existing pattern (time axis) — backend/ercot_dlr_merger.py:36-40
hourly = df.resample("1h").agg({"dlr_amps": "min", ...})

# C8 analog (space axis) — one row per corridor per timestamp,
# min() across the 5 per-point ampacity values
corridor_rating = min(point_ampacities)   # or per-timestamp: df.groupby("timestamp")["ampacity"].min()
```

### Anti-Patterns to Avoid

- **Reusing one global `ConductorConfig` across both corridors:** see Pattern 2 above — the ≈95° bearing difference between the two corridors makes this a real, silent accuracy bug, not a cosmetic simplification.
- **Building a second ampacity formula for C8** instead of calling `thermal_model.ieee738_ampacity`: would recreate exactly the C7 problem this phase exists to fix, just in a new module.
- **Sharing weather fetches across corridor points to save API calls:** explicitly rejected by D-05 ("no nearest-station sharing across points") — don't optimize this away during implementation.
- **Treating `station_explorer.py`'s legacy `CORRIDORS` dict (5 West-Texas proximity points) as the source of the new 2 corridors:** per `geographic_scope.md`'s own recommendation, these are legacy exploratory artifacts to retire from the authoritative scope, not repurpose. The new 2 corridors (D-01) need a distinct, endpoint-pair-shaped structure (see Don't Hand-Roll below) — reusing the `CORRIDORS` name/shape for a fundamentally different data structure (single point vs. line segment) invites confusion.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| IEEE 738 ampacity math (anywhere in C7 or C8) | A second formula, even a "close enough" one | `thermal_model.ieee738_ampacity` `[VERIFIED: backend/thermal_model.py:104-181]` | This is the entire point of Phase 3 — a second formula is the exact bug being fixed |
| Corridor "weakest link" reduction | A bespoke min-with-metadata aggregator | Plain `min()` / `pandas` `.agg({"col": "min"})`, matching `ercot_dlr_merger.py`'s existing `.min()` resampling `[VERIFIED: backend/ercot_dlr_merger.py:36-40]` | Same principle already proven in this codebase on a different axis; no new abstraction needed |
| Great-circle distance/interpolation | A geo library (`geopy`, `pyproj`) | Stdlib `math`, matching `haversine_km`'s existing style `[VERIFIED: backend/station_explorer.py:17-23]` | Codebase convention is zero geo dependencies; corridor lengths here (≈280-390 km) don't need library-grade geodesy precision |

**Key insight:** every piece of new logic this phase needs (interpolation, bearing, nearest-N ranking, min-reduction) already has a structurally identical pattern living in this codebase (`haversine_km`, `rank_by_corridor`, `process_dlr_to_hourly`'s `.min()`). The work is generalizing/composing these, not inventing new algorithms.

## G1/G2 vs. G3/G4 Fallback Semantics (C7 Open Question — Resolved)

**The question, per C7 spec's Open Questions:** "Confirm G1/G2 vs. G3/G4 fallback-target distinction is intentional." `[CITED: docs/data-science/specs/C7-safety-monitor.md:59]`

**Current code behavior** `[VERIFIED: backend/DLRSafetyMonitor.py:22-31]`:
```python
if not self._gate_sensor(raw_data):
    return self._fallback(result, "G1", "sensor timeout", self.last_good_rating)
if not self._gate_link(raw_data):
    return self._fallback(result, "G2", "link lost", self.last_good_rating)
if not self._gate_range(raw_data):
    return self._fallback(result, "G3", "out-of-range", self.static_rating)
```
G1/G2 → `last_good_rating`; G3/G4 → `static_rating`.

**Resolution:** the phase's own Success Criteria (as provided in this task's phase description, mirroring `ROADMAP.md`'s Phase 3 criteria) state: *"Any missing sensor, broken communication link, out-of-range reading, implausible computed rating, or large rating swing causes the reported rating to fall back toward the static rating, never toward an optimistic guess."* This sentence explicitly names "missing sensor" (G1) and "broken communication link" (G2) in the same "fall back toward the static rating" clause as the range/plausibility gates — it does not carve out an exception for G1/G2. This is a stronger, more specific instruction than C7 spec's own hedged "possibly-intentional" framing, and it resolves the gray area CONTEXT.md left to this research pass.

**Recommendation:** change G1 and G2 to fall back to `self.static_rating`, matching G3/G4, so all four fallback gates share one target — the reading with no dependency on a potentially-stale prior value. Rationale beyond the literal ROADMAP wording: `last_good_rating` is only as trustworthy as the moment it was set, and G1/G2 are precisely the cases where the monitor has lost the ability to tell whether conditions have changed since then (no sensor data, no link). Continuing to report a stale, possibly-optimistic `last_good_rating` through an extended outage is the "optimistic guess" DS-NF5 forbids, whereas `static_rating` carries no time-decay risk. This is a **behavior change** relative to the current code (and 3 currently-passing tests — `test_gate_1_fallback_uses_last_good_rating_after_prior_success`, `test_gate_2_fallback_uses_last_good_rating_after_prior_success`, `test_last_good_rating_not_updated_on_fallback`'s companion `test_gate_2_fallback_uses_last_good_rating_after_prior_success` — assert the *current* last-good-rating behavior `[VERIFIED: backend/tests/SafetyMonitor_TestSuite.py:189-215]` and will need updating to assert `static_rating` instead if this recommendation is adopted).

This is tagged `[ASSUMED]` as a *recommendation*, not a locked fact — it is a defensible reading of the phase's success criteria, but it is a genuine behavior change with test-suite implications, not a pure bug fix. **Flag for a one-line user confirmation before the planner locks it** (see Assumptions Log).

## Gate-2 Test Contradiction (C7 Open Question — Resolved)

**The bug** `[VERIFIED: backend/tests/SafetyMonitor_TestSuite.py:57-66]`:
```python
def test_gate_2_fails_when_link_status_not_ok(monitor, valid_data):
    valid_data["link_status"] = "down"
    result = monitor.run_check(valid_data)
    assert result["status"] == "ok"        # <- contradicts fallback is True
    assert result["fallback"] is True
    assert result["rating"] == monitor.static_rating
    assert "G2 FAIL" in result["alerts"][0]
    assert "link lost" in result["alerts"][0]
```

**Why it's a copy-paste error, not an intentional richer status shape:** every other fallback-path test in the same file asserts `result["status"] == "fallback"` — confirmed directly for G1 `[VERIFIED: backend/tests/SafetyMonitor_TestSuite.py:39]`, G3 `[VERIFIED: backend/tests/SafetyMonitor_TestSuite.py:74]`, and G4 `[VERIFIED: backend/tests/SafetyMonitor_TestSuite.py:108]`. `_fallback()`'s implementation unconditionally sets `result["status"] = "fallback"` with no branch on which gate triggered it `[VERIFIED: backend/DLRSafetyMonitor.py:66-71]`:
```python
def _fallback(self, result, gate, reason, rating):
    msg = f"{gate} FAIL ({reason}) — fallback rating {rating:.0f} A"
    self.logger(msg)
    result.update({"status": "fallback", "rating": rating, "fallback": True,
                    "alerts": [msg]})
    return result
```
There is no code path that could produce `status == "ok"` and `fallback is True` simultaneously — the G2 test is simply the one test in the suite where `"fallback"` was mistyped as `"ok"`, most likely copied from a success-path test template.

**Fix:** change line 62 of `SafetyMonitor_TestSuite.py` from `assert result["status"] == "ok"` to `assert result["status"] == "fallback"`. No production code change needed for this specific bug — `_fallback()`'s behavior is already correct and consistent; only the test assertion is wrong. (The G1/G2 fallback-*target* question above is a separate, larger behavior decision — don't conflate fixing this one-line assertion bug with that recommendation.)

## Common Pitfalls

### Pitfall 1: `RATING_BOUNDS` Is Incompatible With 3 of 4 Cities' Static Ratings

**What goes wrong:** `DLRSafetyMonitor.RATING_BOUNDS = (400, 1800)` `[VERIFIED: backend/DLRSafetyMonitor.py:10]` is the G4 plausibility ceiling. `config.py::STATIC_RATINGS` `[VERIFIED: backend/config.py:41-46]`:
```python
STATIC_RATINGS: dict[str, float] = {
    "AUSTIN": 1900.0,          # midpoint of documented 800-3000 A range
    "CORPUS_CHRISTI": 3000.0,  # midpoint of documented 1000-5000 A range
    "MIDLAND": 1800.0,         # midpoint of documented 600-3000 A range
    "EL_PASO": 1450.0,         # midpoint of documented 600-2300 A range
}
```
Austin's own *static* rating (1900 A) already exceeds G4's upper bound (1800 A). Corpus Christi's (3000 A) is 67% above it. Once C7 is wired to the real `ieee738_ampacity` and evaluated against real per-city data, G4 will reject nearly every plausible Austin and Corpus Christi reading — including readings that legitimately compute *below* the city's own static rating, since the city's documented range floor (Austin 800 A, Corpus Christi 1000 A per the same config.py comments) is itself compatible with G4's band, but the ceiling is not.

**Why it happens:** `RATING_BOUNDS` was calibrated against the placeholder formula's output range (`900 + wind*30 - (temp-20)*4 - solar*0.05`, which for the placeholder's plausible input domain stays roughly in the 400-1800 A band) and was never revisited when the 4-city static ratings were adopted (D-00, a decision made independently of C7's gate bounds).

**How to avoid:** widen or recalibrate `RATING_BOUNDS` before wiring the real model, using the same documented per-city range this project already cites in `config.py`'s comments (Austin 800-3000, Corpus Christi 1000-5000, Midland 600-3000, El Paso 600-2300 — combined span 600-5000 A `[VERIFIED: backend/config.py:42-45]`). Two viable approaches: (a) a single wider global bound spanning all 4 cities' documented ranges (simplest, matches the current single-constant design), or (b) a per-location bound derived from each city's own documented range (more precise, requires `DLRSafetyMonitor` to be constructed per-location anyway per the C7 `ConductorConfig` recommendation above, so the marginal cost is low). This is a **planner decision, not fully resolved here** — flagged in Assumptions Log.

**Warning signs:** after wiring, if G4 fallback rate spikes for Austin/Corpus Christi specifically while Midland/El Paso stay low, this is the cause.

### Pitfall 2: `ieee738_ampacity` Returns an `np.ndarray`, Not a Python Float

**What goes wrong:** `thermal_model.ieee738_ampacity` internally calls `np.asarray(...)` on every input and returns the result of `np.sqrt(...)` `[VERIFIED: backend/thermal_model.py:128-130,180-181]` — even for scalar Python float inputs, the return value is a 0-d or 1-element `np.ndarray`, not a plain `float`. `DLRSafetyMonitor`'s existing gates do scalar comparisons (`self.RATING_BOUNDS[0] <= rating <= self.RATING_BOUNDS[1]`, `abs(rating - self.last_good_rating)`) and its tests assert exact equality against plain floats (e.g. `expected_rating = 900 + 5.0 * 30 - ...`).

**Why it happens:** `thermal_model.py` is designed for C5's original use case — batch/vectorized computation over a whole DataFrame column (`obs["dlr_amps"] = thermal_model.ieee738_ampacity(...)` in `dlr_pipeline.py::run_pipeline` `[VERIFIED: backend/dlr_pipeline.py:224-230]`) — not single-reading calls.

**How to avoid:** wrap the call with `float(...)` in `_compute_ampacity` (shown in Pattern 1 above). Cheap, no risk, and keeps every existing scalar-comparison gate and test assertion working unmodified.

### Pitfall 3: Synoptic API Call Volume Under D-05/D-08 Can Reach 100 Calls/Run

**What goes wrong:** D-05 locks 10 independent weather fetches per run (5 points × 2 corridors, no sharing). D-08's candidate-probe fallback means each of those 10 fetches can itself expand from 5 candidate stations to 10 before giving up. Worst case: 10 points × 10 candidate stations = 100 station-level fetch attempts in a single corridor run. C4's spec already flags "No retry/backoff or rate-limit handling on the Synoptic requests — relevant given the free-tier constraints" as a **still-open** issue `[CITED: docs/data-science/specs/C4-weather-ingestion.md:42]`.

**Why it happens:** D-05/D-08 were locked to prioritize per-point accuracy and fallback robustness over API economy (explicitly noted as the tradeoff in CONTEXT.md's own rationale for D-05).

**How to avoid:** not a blocker for this phase (D-05/D-08 are locked decisions, not to be re-litigated), but the planner should budget a task for basic rate-limit-aware sequencing (e.g., a short delay between candidate-station probe batches) or at minimum surface this volume explicitly so it isn't discovered for the first time against a live rate limit during testing.

**Warning signs:** intermittent `429`/rate-limit HTTP responses during a full 2-corridor test run, especially if Corpus Christi/Midland stations (25% live-pull success rate per D-06's verification) trigger the 10-candidate expansion path repeatedly.

## Runtime State Inventory

Not applicable — this is a code-and-config phase (new module + wiring fix), not a rename/refactor/migration. No stored data, live service config, OS-registered state, or build artifacts reference the strings/values this phase changes.

## Code Examples

See "Architecture Patterns" above for the four load-bearing code examples (C7 wiring, per-corridor bearing, geodesic interpolation, generalized nearest-station ranking) — each is tagged with its verification status inline rather than repeated here.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `DLRSafetyMonitor._compute_ampacity` placeholder linear formula | `thermal_model.ieee738_ampacity` (real, bug-fixed IEEE 738) | This phase | G4 plausibility gate becomes meaningful; C7 and C5 can no longer silently disagree |
| `station_explorer.py::CORRIDORS` — 5 fixed West-Texas proximity points, single reference point each | New `CORRIDOR_ENDPOINTS` (or similar) — 2 city-pair line segments, 5-point discretized | This phase | First real corridor (line, not point) representation in the codebase; legacy `CORRIDORS` retired from authoritative scope per `geographic_scope.md`'s recommendation |
| WTM-network-only Synoptic query (`network_id = 152` hardcoded) `[VERIFIED: backend/station_explorer.py:99]` | Broadened, unrestricted-network Synoptic query (D-06) | This phase | Station candidate pool goes from ~2 (both currently zero-data, per C4's Known Issues) to hundreds per city |

**Deprecated/outdated:**
- `station_explorer.py`'s hardcoded `network_id = 152` `[VERIFIED: backend/station_explorer.py:99]` — superseded by D-06's broadened query (pass `network_id=None` to `get_all_stations`, which already supports this per its existing `Optional[str] = None` signature `[VERIFIED: backend/station_explorer.py:48]`).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | G1/G2 fallback target should change from `last_good_rating` to `static_rating`, matching G3/G4 | "G1/G2 vs. G3/G4 Fallback Semantics" | If the team intended the current distinction to stay (e.g. explicit design rationale not captured in any doc read this session), this recommendation would force an unwanted behavior + test-suite change. Low-cost to confirm with a single question before planning locks it. |
| A2 | Corpus Christi and Midland city-center coordinates ((27.74,-97.40) and (32.00,-102.10) and El Paso (31.76,-106.49)) | "Per-Corridor `line_azimuth`" | Sourced via an unconfigured `WebSearch` call (this project's `brave_search`/`exa_search`/`firecrawl` are all `false`), so tagged LOW confidence by this session's own `classify-confidence` check. Wrong coordinates would shift computed bearings and shift which weather stations are "nearest" to each interior point — re-verify against an authoritative source (e.g. US Census Gazetteer) before hardcoding into `config.py`. |
| A3 | `RATING_BOUNDS` recalibration approach — single wider global band vs. per-city band | "RATING_BOUNDS Must Be Recalibrated" pitfall | Both are defensible; the planner should pick one explicitly rather than leaving G4 uncalibrated post-wiring, since either fixes the immediate incompatibility with `STATIC_RATINGS`. |
| A4 | `ConductorConfig`/`solar_altitude_deg` should be passed into `DLRSafetyMonitor.__init__` (one instance per location/corridor) rather than computed globally | "C7 Wiring" Pattern 1 | If the team prefers a single global monitor instance with per-call location parameters instead, the constructor shape changes; either resolves the underlying gap (C7 spec's own open question on where `ConductorConfig` comes from), but the two are not code-compatible without a rewrite, so the planner should pick one before task-writing. |
| A5 | New `CORRIDOR_ENDPOINTS`-style structure belongs in `config.py` (C1 convention) rather than `station_explorer.py` | "Anti-Patterns to Avoid" | Low risk either way — `station_explorer.py` is also defensible (it currently owns `CORRIDORS`). Recommendation follows the C1 config-centralization pattern already established by the codebase and flagged as an "Established Pattern" in CONTEXT.md. |

## Open Questions

1. **Should `RATING_BOUNDS` be a single global band or per-city?**
   - What we know: the current single global band (400-1800 A) is incompatible with 3 of 4 cities' static ratings.
   - What's unclear: whether the team wants the simplicity of one wider band or the precision of per-city bands, given `DLRSafetyMonitor` will likely already be instantiated per-location for the `ConductorConfig` reason above.
   - Recommendation: default to per-location (marginal cost is low once per-location instantiation exists anyway), but confirm with the user before locking — see A3/A4.

2. **Should the G5 `DELTA_THRESH` (150 A) also scale per-city?**
   - What we know: `DELTA_THRESH` is a flat 150 A alert threshold across all locations; the 4 cities' static ratings span 1450-3000 A, a >2x range.
   - What's unclear: whether a flat absolute threshold or a relative (%-of-rating) threshold better serves DS-NF5's "large rating swing" language.
   - Recommendation: out of this phase's explicit scope (not named in Phase 3's Success Criteria, which mentions the delta check generically) — flag for the planner to decide whether to touch it now (small, same-file change) or defer.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | All backend code | ✓ (observed in this session) | 3.9.6 | — |
| numpy, pandas, requests | thermal_model.py, station_explorer.py, weather_provider.py, dlr_pipeline.py | ✓ (imported successfully throughout existing codebase) | not pinned — no requirements.txt/pyproject.toml found in repo | — |
| `SYNOPTIC_TOKEN` env var | Live weather fetch (C4/C8 runtime, not needed for unit tests) | Not checked this session (no live API call attempted) | — | Tests use fixtures/mocks, not live calls — `thermal_model_test.py` explicitly verifies importability with no token set `[VERIFIED: backend/tests/thermal_model_test.py:249-266]` |
| pytest | Test execution | Configured via repo-root `pytest.ini` `[VERIFIED: /Users/aphan/Documents/Senior_Design/pytest.ini]` (`pythonpath = backend`, `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py`) | not pinned | — |

**Missing dependencies with no fallback:** none identified.

**Missing dependencies with fallback:** `SYNOPTIC_TOKEN` — not required for the unit-test-level work this phase's tests will cover; only needed for live end-to-end corridor runs.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (config: repo-root `pytest.ini` `[VERIFIED]`) |
| Config file | `/Users/aphan/Documents/Senior_Design/pytest.ini` |
| Quick run command | `pytest backend/tests/SafetyMonitor_TestSuite.py -x` |
| Full suite command | `pytest` (uses `pytest.ini`'s `testpaths = backend/tests` automatically) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DS-F7 | `_compute_ampacity` matches `thermal_model.ieee738_ampacity` for identical inputs | unit | `pytest backend/tests/SafetyMonitor_TestSuite.py -k wired -x` (new test to add) | ❌ Wave 0 — add an equivalence test comparing `DLRSafetyMonitor._compute_ampacity(d)` against a direct `thermal_model.ieee738_ampacity(...)` call for the same inputs |
| DS-F7 | Gate-2 test no longer contradicts itself | unit | `pytest backend/tests/SafetyMonitor_TestSuite.py::test_gate_2_fails_when_link_status_not_ok -x` | ✅ exists, currently failing (documented bug — see "Gate-2 Test Contradiction") |
| DS-NF5 | G1-G4 fallback correctly targets the resolved value (static or last-good, per A1's resolution) | unit | `pytest backend/tests/SafetyMonitor_TestSuite.py -k fallback -x` | ✅ exists, will need target-assertion updates if A1's recommendation is adopted |
| DS-F10 | Corridor discretized into 5 points; per-point ampacity computed; corridor rating = min() | unit + integration | `pytest backend/tests/corridor_discretization_test.py -x` (new file) | ❌ Wave 0 — no existing coverage of `station_explorer.py` or any corridor logic (confirmed via repo-wide grep this session) |
| DS-F10 | Artificially "cooled" point correctly identified as the bottleneck (min-reduction correctness) | unit | `pytest backend/tests/corridor_discretization_test.py -k bottleneck -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest backend/tests/SafetyMonitor_TestSuite.py -x` (or the relevant new C8 test file for corridor-touching tasks)
- **Per wave merge:** `pytest` (full suite)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `backend/tests/corridor_discretization_test.py` — new file, no existing coverage of `station_explorer.py`, corridor logic, or any C8 behavior (confirmed via repo-wide `grep -rl "station_explorer\|CORRIDORS\|corridor" backend/tests/` returning zero matches this session)
- [ ] A new equivalence test in `SafetyMonitor_TestSuite.py` asserting `DLRSafetyMonitor`'s computed rating matches a direct `thermal_model.ieee738_ampacity` call for identical inputs — this is literally C7's own stated Acceptance Criterion (`docs/data-science/specs/C7-safety-monitor.md`: "Once wired to C5: for identical weather inputs, `DLRSafetyMonitor`'s computed rating matches `dlr_pipeline`'s `ieee738_ampacity` output exactly") but no such test exists yet
- [ ] If A1 (G1/G2 fallback-target change) is adopted: update `test_gate_1_fallback_uses_last_good_rating_after_prior_success` and `test_gate_2_fallback_uses_last_good_rating_after_prior_success` (`[VERIFIED: backend/tests/SafetyMonitor_TestSuite.py:189-215]`) to assert `static_rating` instead of the previously-good dynamic rating

## Security Domain

`security_enforcement` is absent from `.planning/config.json` (no such file exists in this repo), so treated as enabled per protocol default; this is a backend physics/data pipeline with no user-facing auth surface, so most ASVS categories are not applicable.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | No user-facing auth in this phase's scope |
| V3 Session Management | No | N/A |
| V4 Access Control | No | N/A |
| V5 Input Validation | Yes | Already implemented via `PIPELINE_SCHEMA` (C2) and `DLRSafetyMonitor`'s G1-G3 gates `[VERIFIED: backend/DLRSafetyMonitor.py:7-11]` — this phase extends, not introduces, this control |
| V6 Cryptography | No | No new secrets/crypto surface — `SYNOPTIC_TOKEN` handling is unchanged by this phase (C4's existing `.env`/env-var pattern) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Silent overstatement of line capacity from an unvalidated/stale computed rating | Tampering (of physical-world trust, not classic injection) | This is DS-NF5 itself — the fail-safe gating chain (G1-G5) is the mitigation; this phase's job is making the gated value actually correspond to the real physics |
| API token (`SYNOPTIC_TOKEN`) leakage via logs/error messages during the new candidate-probe fallback logic (D-08) | Information Disclosure | Ensure any new logging added for the candidate-probe expansion (nearest-5 → nearest-10) logs station IDs/lat-lon, never request params containing the token — matches the existing pattern in `station_explorer.py`/`dlr_pipeline.py`, which already keep `token` out of log statements |

## Sources

### Primary (HIGH confidence — direct code/test/spec reads this session)
- `backend/DLRSafetyMonitor.py` (full file read) — current gates, fallback targets, placeholder formula
- `backend/thermal_model.py` (full file read) — `ieee738_ampacity`, `ConductorConfig`, `perpendicular_wind` signatures and implementation
- `backend/station_explorer.py` (full file read) — `CORRIDORS`, `haversine_km`, `rank_by_corridor`, `get_all_stations`
- `backend/weather_provider.py` (full file read) — `fetch_weather` interface
- `backend/config.py` (full file read) — `STATIC_RATINGS`, `DEFAULT_CONDUCTOR_CONFIG_KWARGS`, `DEFAULT_STATION_SOURCE`
- `backend/dlr_pipeline.py` (lines 1-260 read) — `fetch_timeseries`, `run_pipeline`, existing ieee738 call pattern
- `backend/ercot_dlr_merger.py` (full file read) — `.min()` resampling pattern
- `backend/units_def.py` (lines 300-379 read) — `PIPELINE_SCHEMA` ranges, including the `dlr_amps` (100-4000 A) vs. `RATING_BOUNDS` (400-1800 A) discrepancy noted in Pitfall 1
- `backend/tests/SafetyMonitor_TestSuite.py` (full file read) — the gate-2 contradiction, fallback-target assertions
- `backend/tests/thermal_model_test.py` (full file read) — existing C5 validation coverage
- `/Users/aphan/Documents/Senior_Design/pytest.ini` — test framework config
- `.planning/phases/03-safety-spatial/03-CONTEXT.md`, `.planning/REQUIREMENTS.md`, `.planning/STATE.md` — phase scope and locked decisions
- `.planning/codebase/CONCERNS.md` — corroborates the known-issues list independently

### Secondary (MEDIUM confidence)
- `docs/data-science/specs/C7-safety-monitor.md`, `docs/data-science/specs/C8-corridor-discretization.md`, `docs/data-science/specs/C4-weather-ingestion.md`, `docs/data-science/specs/C1-configuration.md` — component specs, cited for their Open Questions and documented known issues
- `docs/data-science/decisions/geographic_scope.md`, `docs/data-science/decisions/data_provider.md` — decision logs; Austin's coordinate `(30.27, -97.74)` cited from `data_provider.md:166`, confirmed there via a live Open-Meteo API call

### Tertiary (LOW confidence — flag for validation)
- Corpus Christi, Midland, El Paso city-center coordinates — sourced via an unconfigured `WebSearch` call (Wikipedia infobox coordinates); this session's `gsd-tools query classify-confidence --provider websearch` call returned `LOW` confidence for this provider given the project has `brave_search`/`exa_search`/`firecrawl` all disabled. Re-verify before hardcoding.
- Bearing/interpolation formula outputs derived from those coordinates (Pattern 2, Pattern 3) — correct formulas, unverified specific numeric outputs; recommend a spot-check during implementation.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies; existing library usage directly observed
- Architecture: HIGH — every recommended pattern is a direct generalization of code read this session
- Pitfalls: HIGH for RATING_BOUNDS/ndarray findings (directly derived from verified code); MEDIUM for the G1/G2 fallback-target recommendation (a defensible reading of stated success criteria, not a locked decision)
- Geographic coordinates (non-Austin): LOW — flag for user/planner verification before locking into config.py

**Research date:** 2026-09-03
**Valid until:** 30 days (stable, code-derived findings; no fast-moving external dependency in this phase's scope)
