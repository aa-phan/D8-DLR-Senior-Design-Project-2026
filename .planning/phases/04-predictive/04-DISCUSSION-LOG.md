# Phase 4: Predictive - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-08
**Phase:** 4-Predictive
**Areas discussed:** Forecast horizon, C9→C10 coupling, Historical archive scope, Tier 1 vs Tier 2 scope for this phase

---

## Forecast horizon

| Question | Options | Selected |
|---|---|---|
| How far ahead should C9's ampacity forecast look? | 1 hour ahead (Recommended) / 6 hours ahead / Multiple horizons (e.g. 1h and 6h) | 1 hour ahead ✓ |
| Forecast ampacity directly, or forecast weather inputs and re-run IEEE 738? | Forecast ampacity directly (Recommended) / Forecast weather, then re-run IEEE 738 | Forecast ampacity directly ✓ |
| How should the confidence/uncertainty band be produced? | Empirical residual quantiles (Recommended) / Normal-distribution band (mean ± k·std) | Empirical residual quantiles ✓ |

**User's choice:** Recommended option selected at every question — 1-hour direct-ampacity forecast with an empirical-residual-quantile confidence band.
**Notes:** None — straightforward acceptance of research's Tier 1 recommendation.

---

## C9→C10 coupling

| Question | Options | Selected |
|---|---|---|
| Should C10 use C9's forecast as primary signal, or run fully independent? | Coupled to C9 forecast, with rolling-baseline fallback (Recommended) / Fully independent rolling-baseline detector | Coupled, with fallback ✓ |
| Where should C10 plug into DLRSafetyMonitor's gate chain? | New gate G6 after G5, constructor-injected (Recommended) / You decide | New gate G6, constructor-injected ✓ |
| What false-positive tolerance should the control limit target? | Conservative — wide band (Recommended) / Tighter band / You decide (config constant) | Conservative — wide band ✓ |

**User's choice:** Recommended option selected at every question.
**Notes:** The conservative-band choice was framed against the codebase's existing fail-safe philosophy (G1–G5 already catch clear-cut cases) — user accepted that framing.

---

## Historical archive scope

| Question | Options | Selected |
|---|---|---|
| Should building the archive job be Wave 0 of Phase 4? | Yes, build it as Wave 0 (Recommended) / It may already exist somewhere — let me check first | Yes, build as Wave 0 ✓ |
| What granularity should the archive target? | Per-corridor (Recommended) / Per-station/point | Per-corridor ✓ |
| What retention/storage policy? | Append-only CSV, unbounded for now (Recommended) / Append-only CSV with a rolling retention window | Unbounded CSV ✓ |

**User's choice:** Recommended option selected at every question — confirms research's Wave 0 recommendation directly rather than pausing to verify elsewhere.
**Notes:** The direct-grep verification from RESEARCH.md (no archive implementation found anywhere in `backend/`) was accepted as sufficient evidence.

---

## Tier 1 vs Tier 2 scope for this phase

| Question | Options | Selected |
|---|---|---|
| Should Tier 2 be attempted this phase, or Tier 1-only? | Tier 1 only this phase (Recommended) / Build Tier 1 + a Tier 2 hook/interface / Attempt Tier 2 now despite low data | Tier 1 only ✓ |
| Should Phase 4 add a requirements.txt? | Yes, add requirements.txt this phase (Recommended) / No, out of scope | Yes ✓ |

**User's choice:** Recommended option selected at every question.
**Notes:** Tier 2 explicitly deferred rather than pre-building an unused interface — user chose the leaner of the two Tier-1-compatible options.

---

## Claude's Discretion

- Exact `config.py` constant names/values for the anomaly control-limit multiplier and forecast horizon
- Exact archive row schema (column names/order) beyond the per-corridor shape already sketched in RESEARCH.md's Pattern 3
- Whether `PIPELINE_SCHEMA_VERSION` starts at 2
- Exact walk-forward backtest window size for the empirical residual quantiles

## Deferred Ideas

- Tier 2 (scikit-learn quantile-loss GBT) forecasting/anomaly detection — until archive volume clears a floor
- Full multi-provider weather composition (`docs/data-science/decisions/data_provider.md`) — carried forward from Phase 3's own deferral, not re-discussed
- Multiple forecast horizons (e.g. both 1h and 6h) — considered, not chosen; single 1-hour horizon is this phase's scope
