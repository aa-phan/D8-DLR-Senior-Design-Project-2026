# Milestones

## v1.0 MVP (Shipped: 2026-09-10)

**Phases completed:** 3 phases, 7 plans, 19 tasks

**Key accomplishments:**

- DLRSafetyMonitor wired to the real IEEE 738 thermal model, made per-location constructible, and all five fail-safe gates (G1-G5) now resolve toward the static rating instead of a stale or optimistic guess.
- Two D-01 corridors (Austin<->Corpus Christi, Midland<->El Paso) discretized into 5 geodesic points each, per-point weather resolved through generalized station-proximity ranking, gated through the real IEEE 738 model via DLRSafetyMonitor, and reduced to a corridor-level rating via min() with the bottleneck point identified.
- Corridor weather lookup now probes a broadened, unrestricted-network station pool nearest-5-then-10 with deterministic, credential-free logging, and any point that exhausts every candidate resolves to the corridor's static rating instead of raising -- closing the last data-loss gap in the corridor path and proving the C8 bottleneck test the spec itself asks for.
- One anomalous reading now travels archive -> naive forecast -> per-location anomaly detector -> a new additive G6 gate -> the static rating, through the same `_fallback` helper Phase 3 shipped — with the whole path fail-safe under a raising detector, an unwritable disk, or a poisoned row.
- Replaced the tracer's in-sample residual band with a true out-of-sample expanding-window walk-forward backtest, added an EWM forecast method behind the same signature, and published forecast output through `PIPELINE_SCHEMA` v2's five additive optional columns.
- `process_dlr_to_hourly`, `run_pipeline`, and `plot_dlr_summary` now resolve `config.STATIC_RATINGS.get(city, config.DEFAULT_STATIC_RATING)` instead of unconditionally reading the 900 A default — closing the last open v1.0 milestone requirement (DS-F5).

---
