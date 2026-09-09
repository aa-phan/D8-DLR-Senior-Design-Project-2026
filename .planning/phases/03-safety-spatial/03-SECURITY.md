---
phase: "03"
slug: "safety-spatial"
status: verified
threats_open: 0
asvs_level: 1
created: "2026-09-09"
---

# Phase 03 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| weather provider -> pipeline row | Untrusted third-party sensor telemetry (possibly stale, null, or physically impossible) crosses into the rating computation | Synoptic weather observations (temp, wind, solar) |
| computed rating -> reported rating | A number derived from untrusted telemetry becomes an operational statement about how much current a physical conductor can carry | Ampacity value (float, amps) |
| environment (`SYNOPTIC_TOKEN`) -> process | Secret material enters the process | API token — not exercised by `DLRSafetyMonitor`/`corridor_discretization` code paths directly; token stays inside `weather_provider.fetch_weather` / `dlr_pipeline` |
| Synoptic station-discovery query -> candidate pool | Broadened, unrestricted-network station query returns a wider, still-untrusted candidate pool per city | Station id, lat/lon, distance |

---

## Threat Register

| Threat ID | Plan | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|------|----------|-----------|----------|-------------|------------|--------|
| T-03-01 | 03-01 | Tampering (physical-world trust) | `DLRSafetyMonitor.run_check`/`_compute_ampacity` | high | mitigate | Wired to real `thermal_model.ieee738_ampacity`; per-location `RATING_BOUNDS` recalibrated. Verified by `test_compute_ampacity_is_wired_to_thermal_model` + grep gate (0 placeholder-formula occurrences). | closed |
| T-03-03 | 03-01 | Tampering (stale-value trust) | `DLRSafetyMonitor` G1/G2 fallback target | high | mitigate | G1/G2 fall back to `static_rating`, never `last_good_rating`. Verified by `-k fallback` suite. | closed |
| T-03-04 | 03-01 | Tampering (unbounded-swing trust) | `DLRSafetyMonitor` G5 branch | high | mitigate | G5 reports `min(computed, static_rating)` under `status="fallback"` (user-selected option-a, `DELTA_FRACTION=0.15`). Verified by `test_gate_5_fallback_when_delta_exceeds_threshold`. | closed |
| T-03-05 | 03-01 | Denial of Service (self-inflicted latching) | `DLRSafetyMonitor` G5 latching | medium | mitigate | `last_good_rating` updates on a G5 event, so a genuine sustained weather change resolves in one cycle. Verified by `test_gate_5_does_not_latch_after_fallback`. | closed |
| T-03-06 | 03-01 | Information Disclosure | `_fallback` alert strings / `self.logger` | low | accept | No network I/O in this module; alert strings carry only gate id, reason, rounded ampacity. Accepted, no new control needed. | closed |
| T-03-01 (dup id) | 03-02 | Tampering (physical-world trust) | `corridor_discretization.rate_corridor` reduction | high | mitigate | `min()` reduction over all 5 points, bottleneck index asserted in tests; grep gate blocks a second ampacity formula. Verified by `test_rate_corridor_returns_expected_keys_and_min_reduction`. | closed |
| T-03-07 | 03-02 | Tampering (mis-modelled physics) | `corridor_geometry` `line_azimuth` | high | mitigate | Each corridor computes its own bearing via `config.conductor_kwargs_for`; verified bearings differ >45° and neither is the 90.0 default. | closed |
| T-03-08 | 03-02 | Spoofing (wrong sensor speaks for a span) | `station_explorer.nearest_stations` | medium | mitigate | Deterministic distance-then-`stid` tie-break. Verified by `test_nearest_stations_ties_broken_by_stid_ascending`. | closed |
| T-03-02 | 03-02 | Information Disclosure | weather fetch call path | high | mitigate | No new logging added in this plan; token stays inside `weather_provider.fetch_weather`/`dlr_pipeline`. Explicit candidate-probe mitigation deferred to and closed by 03-03 (below). | closed |
| T-03-09 | 03-02 | Denial of Service | per-point fetch fan-out | medium | transfer | Transferred to 03-03 for sequencing/rate-limit handling; this plan issues exactly one fetch per point (the floor of the budget). Resolved by 03-03's T-03-09 (below). | closed |
| T-03-SC | 03-02 | Tampering (supply chain) | pip installs | low | accept | No new external packages; grep gate blocks `geopy`/`pyproj`/`shapely`/`geographiclib`. | closed |
| T-03-02 (dup id) | 03-03 | Information Disclosure | `resolve_point_observation` probe logging | high | mitigate | Probe log lines carry only station id/lat/lon/distance/outcome; grep gate fails the task if `token`/`api_key`/`params` appear in a log/print statement. Verified by `test_probe_trail_has_no_credential_or_request_parameter_material`. | closed |
| T-03-01 (dup id) | 03-03 | Tampering (physical-world trust) | `rate_corridor` exhaustion path | high | mitigate | Exhausted point resolves to corridor static rating and stays in the `min()` reduction — never dropped or interpolated. Verified by `test_exhaust_single_point_falls_back_to_static_others_succeed`. | closed |
| T-03-09 (dup id) | 03-03 | Denial of Service | Synoptic call volume | medium | mitigate | Probe batches paced with `PROBE_BATCH_PAUSE_S`; worst-case ceiling (100 station-level attempts/2-corridor run) pinned by assertion. Verified by `test_worst_case_two_corridor_all_unusable_probe_count_is_100`. | closed |
| T-03-10 | 03-03 | Denial of Service (availability of the safe state) | exhaustion path | medium | accept | A fully-exhausted corridor reports the static rating rather than failing; `exhausted_points` count makes the degradation visible. Accepted as the intended fail-safe cost. | closed |
| T-03-08 (dup id) | 03-03 | Spoofing (wrong sensor speaks for a span) | candidate probe ordering | medium | mitigate | Deterministic distance-then-`stid` ordering, ranked once and sliced into batches. Verified by `test_probe_equidistant_candidates_probed_in_same_order_across_runs`. | closed |
| T-03-11 | 03-03 | Tampering (scope drift into unvetted providers) | provider surface | low | mitigate | Prohibition list forbids TCEQ/NSRDB/ASOS/Open-Meteo composition this phase; broadened Synoptic query is the entire provider scope. No unvetted endpoint introduced. | closed |
| T-03-SC (dup id) | 03-03 | Tampering (supply chain) | pip installs | low | accept | No new external packages; probe uses `math`, `pandas`, existing `requests` path. | closed |

*Status: open · closed · open — below {block_on} threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on (`high`) count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

**Note on duplicate threat IDs:** Threat IDs (e.g. `T-03-01`, `T-03-02`, `T-03-08`, `T-03-09`, `T-03-SC`) are reused across the three plans' independently-authored `<threat_model>` blocks, each referring to a distinct threat scoped to that plan. Disambiguated above by `Plan` column; a future phase should mint globally-unique IDs to avoid this collision.

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-03-01 | T-03-06 (03-01) | `DLRSafetyMonitor` performs no network I/O; alert strings carry no station identifiers, coordinates, credentials, or request parameters. | plan author (03-01-PLAN.md) | 2026-09-03 |
| AR-03-02 | T-03-SC (03-01, 03-02, 03-03) | No new external packages introduced in any of the three plans; `03-RESEARCH.md` Package Legitimacy Audit recorded as not applicable. | plan author | 2026-09-03 |
| AR-03-03 | T-03-10 (03-03) | A fully-exhausted corridor degrades to the static rating rather than becoming unavailable; `exhausted_points` count keeps the degradation visible rather than silent. | plan author (03-03-PLAN.md) | 2026-09-03 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-09-09 | 18 | 18 | 0 | /gsd-secure-phase (orchestrator, State B — built from PLAN.md threat models, short-circuited per ASVS L1 + register_authored_at_plan_time=true) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-09-09
