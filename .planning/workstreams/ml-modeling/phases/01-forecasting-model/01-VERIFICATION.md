---
phase: 01-forecasting-model
verified: 2026-09-24T00:00:00Z
status: passed
score: 4/4 ROADMAP success criteria verified; 0/2 corridors met the model's own stated accuracy bar (see Findings -- an honest negative result, not an engineering gap)
behavior_unverified: 0
overrides_applied: 0
---

# Phase 1: Forecasting Model Verification Report

**Phase Goal:** `ampacity_forecast.forecast_ampacity` can produce an ampacity forecast from an
actual trained model — not just the last observed value or an exponentially-weighted average —
and that model's accuracy is proven against real historical data rather than assumed.
**Verified:** 2026-09-24
**Status:** PASSED_WITH_FINDINGS
**Re-verification:** No — initial verification

## Verdict

**PASSED_WITH_FINDINGS.**

Every ROADMAP.md Phase 1 success criterion (SC1-SC4) and both requirements (FCST-01, FCST-02) are
demonstrably met by real, independently-reproduced evidence: the interface contract is unbroken,
a genuine fitted `scikit-learn` model produces the `"ml"` point forecast, that model is trained
and backtested against real (non-synthetic) historical data through the existing walk-forward
machinery, and a written, honest validation record exists. The full test suite is green (409
passed, independently re-run, not taken from SUMMARY.md). The stale C9 spec language is corrected.

The finding that keeps this from a clean PASSED: **the fitted model (`MLPRegressor`, chosen per
D-01's bake-off) does not beat the naive last-value baseline's held-out MAE on either corridor.**
This is not a process or engineering failure — the bake-off machinery, leakage guards, and
documentation are all working exactly as designed, and the validation record states this
plainly rather than spinning it. It is a substantive, negative, project-level result that Aaron
should see and decide how to act on (see Findings and Recommendation below). None of ROADMAP's
SC1-SC4 wording requires the model to beat naive/EWM to be "met" — SC4 only requires the
comparison be made and the outcome stated — so this finding does not itself fail any roadmap
criterion; it is a fact about the world the roadmap correctly anticipated might go either way.

## Success Criteria Checked

| # | ROADMAP Success Criterion | Status | Evidence |
|---|---|---|---|
| SC1 | `FORECAST_METHODS` includes a new ML-backed method alongside `"naive"`/`"ewm"`; `forecast_ampacity(history, horizon_min, method=<new>)` returns a `ForecastResult` populating the same four `PIPELINE_SCHEMA` columns — no signature/schema break. | ✓ VERIFIED | Independently imported the module fresh (`PYTHONPATH=backend python3 -c "import ampacity_forecast as af"`): `af.FORECAST_METHODS == ('naive', 'ewm', 'ml')`. `inspect.signature(af.forecast_ampacity)` → `(history: pandas.core.frame.DataFrame, horizon_min=None, method='naive', quantiles=None, min_rows=None)` — identical to the locked pre-Phase-1 signature (no new parameter). `forecast_columns()` remains the sole path to the four `PIPELINE_SCHEMA` keys for all three methods (read in full; unchanged since Phase 4). |
| SC2 | The new method's point forecast is produced by an actual fitted regression/NN model object, not a last-value read or EWM smoothing. | ✓ VERIFIED | `_point_forecast`'s `method == "ml"` branch (`backend/ampacity_forecast.py:319-339`) calls `model.predict(row_as_2d)[0]` on a loaded, previously-fitted `joblib`-persisted estimator (`_load_corridor_model`) — never a `.iloc[-1]` or `.ewm(...)` call. `forecast_training.py::fit_corridor_model` calls `estimator.fit(...)` offline, never inside the runtime module (`ampacity_forecast.py` imports no `sklearn` at module scope — `joblib` is lazy-imported only inside `_load_corridor_model`, confirmed by reading the import block). |
| SC3 | The model is trained/evaluated against real historical data (Open-Meteo backfill → `thermal_model.ieee738_ampacity` → real `dlr_amps`), using the existing `backtest_residuals` walk-forward machinery, not a parallel band implementation. | ✓ VERIFIED | `forecast_training.corridor_training_frame` calls `open_meteo_provider.fetch_open_meteo` (real Archive API), `thermal_model.perpendicular_wind` + `ieee738_ampacity` for both corridor endpoint cities, and the weakest-link `min()` reduction — read in full, no synthetic/fixture data path. `ampacity_forecast.py::backtest_residuals`'s `method == "ml"` branch loads the fitted model ONCE and reuses the same expanding-window walk-forward loop naive/ewm already use (`backend/ampacity_forecast.py:356-413`) — one function, one band implementation, confirmed by reading the code (no second backtest function exists in either file). |
| SC4 | A written validation record documents the new method's measured out-of-sample accuracy vs. naive/ewm on the same data, and states whether the model met expectations (FCST-02). | ✓ VERIFIED | `docs/data-science/decisions/forecasting_model.md` (232 lines) read in full: states the expectation ("chosen ML candidate's held-out MAE must be lower than BOTH naive's and ewm's") *before* presenting results, gives per-corridor four-candidate MAE/RMSE/row-count tables transcribed from `data/models/bakeoff_report.json`, and an explicit **NOT MET** verdict for both `AUSTIN_CORPUS_CHRISTI` and `MIDLAND_EL_PASO`, with the shortfall arithmetic shown (e.g. 77.70 > 67.17). Limitations and Open Questions sections are present and substantive, not boilerplate. |

**Requirements:** FCST-01 (SATISFIED — SC1-SC3 above) and FCST-02 (SATISFIED — SC4 above; the
validation record exists, compares against real data, and states an explicit met/not-met
verdict, which is exactly what FCST-02's text requires — it does not require a positive result).

## Evidence

**1. Full test suite, independently re-run from a clean shell (not taken from SUMMARY.md):**

```
.venv/bin/python3 -m pytest -q
409 passed, 5 warnings in 23.15s
```

No failures, no skips. Warnings are an expected `MLPRegressor` `ConvergenceWarning` (max_iter
reached during a bake-off test's fit) and a pre-existing, unrelated pytest collection warning on
`units_def_test.py::TestResult` — neither is new to this phase and neither indicates a defect.

**2. Independent module-level interface check:**

```
PYTHONPATH=backend .venv/bin/python3 -c "
import ampacity_forecast as af, inspect
print(af.FORECAST_METHODS)
print(inspect.signature(af.forecast_ampacity))
"
('naive', 'ewm', 'ml')
(history: pandas.core.frame.DataFrame, horizon_min=None, method='naive', quantiles=None, min_rows=None)
```

Confirms SC1's interface-preservation claim directly, not via SUMMARY.md assertion.

**3. Validation record read in full** (`docs/data-science/decisions/forecasting_model.md`):
states the expectation before the verdict, reports both ML candidates' numbers regardless of
which lost (transparency per D-01), and gives the honest NOT MET verdict for both corridors:

| Corridor | naive MAE | ewm MAE | HistGradientBoosting MAE | MLPRegressor MAE (persisted) | Verdict |
|---|---|---|---|---|---|
| AUSTIN_CORPUS_CHRISTI | **67.17** | 88.32 | 79.09 | 77.70 | NOT MET |
| MIDLAND_EL_PASO | **79.76** | 99.65 | 90.13 | 89.59 | NOT MET |

The document explicitly separates two distinct, correctly-answered questions: (a) which ML
candidate is better (`MLPRegressor`, evidence-based, a real answer to D-01) vs. (b) does the ML
method as a whole beat naive/ewm (no, on either corridor, at the current 60-minute horizon). It
does not reframe (a)'s win as evidence for (b) — this is the "don't spin the record" check the
task asked for, and it passes: no softening language, no burying the verdict, bolded "NOT MET"
stated twice with the supporting arithmetic shown inline.

**4. Stale spec language check:**

```
grep -n "no model code\|None\. No model" docs/data-science/specs/C9-ampacity-forecasting.md
(no output)
```

`docs/data-science/specs/C9-ampacity-forecasting.md` no longer contains the stale "None. No
model code... exists" language (confirmed absent by grep, not by reading the SUMMARY's claim).
The spec's Current Implementation, Interface & Data Contract, Blocked by, Known Issues,
Acceptance Criteria, and Open Questions sections were read in full and accurately describe the
three shipped methods, correctly cite the validation record's naive-wins finding, and do not
overstate `"ml"`'s status.

**5. Anti-pattern scan:** No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER`/"not yet
implemented" markers found in `backend/ampacity_forecast.py`, `backend/forecast_training.py`, or
`backend/config.py`.

**6. Model-artifact provenance:** `data/models/` is git-ignored (confirmed in `.gitignore`) and
does not exist in this checkout — expected and documented behavior (`forecast_ampacity(...,
method="ml")` raises `FileNotFoundError` naming the training command rather than silently
degrading, per the module's own docstring and `_load_corridor_model`). The 01-02 and 01-03 plans
were executed in different sessions/worktrees and each independently re-ran the real Open-Meteo
bake-off; their reported MAE/RMSE figures match to the last reported decimal across both runs —
strong evidence the reported numbers come from a real, reproducible pipeline rather than a
fabricated or copy-pasted result.

**7. Test coverage of the shipped code:** `backend/tests/ampacity_forecast_test.py` (521 lines,
22 test functions) and `backend/tests/forecast_training_test.py` (361 lines, 10 test functions)
— both substantive, not stub test files; they include named tests for no-future-leakage, ML
sensitivity to weather-feature edits, per-corridor cache isolation, and the four-candidate
bake-off report shape (per the C9 spec's own Acceptance Criteria section).

## Findings

**1. (Process/engineering — met.)** The bake-off machinery, leakage guards, per-corridor model
isolation, and the interface-preservation contract all work correctly and are covered by a
substantive, green test suite. Nothing here is a stub, placeholder, or partially-wired artifact.

**2. (Substantive, project-level — open finding for Aaron.)** At the currently configured
60-minute horizon, with the currently configured lag/rolling-window feature set, the fitted
`"ml"` method does not outperform the simple `"naive"` last-value baseline on held-out MAE, on
either corridor, on a real 3-year Open-Meteo-derived series. The validation record attributes
this to naive's own documented strength on short-horizon, slowly-varying physical series (ampacity
does not change fast hour-to-hour), not to a defect in the training/evaluation pipeline — no
leakage signature is present (a leaking model would show anomalously *good*, not worse,
performance). ROADMAP.md's SC1-SC4 wording does not presuppose the model would win; SC4 only
requires the comparison be made and the result stated, which it is. There is therefore no roadmap
criterion to mark as failed over this — but it is a legitimate, important result for a capstone
project to surface honestly rather than have verification paper over: **the C9 "ML forecasting"
deliverable, as currently scoped (60-min horizon, this feature set, this 3-year backfill), is not
currently a production improvement over the Tier-1 statistical methods it was meant to
replace/extend.** The validation record's own Open Questions section already identifies the next
investigative steps (longer horizon, richer features, deeper architecture, tuned backfill depth)
without resolving whether "ml" should be recommended as production-preferred — that
recommendation is correctly left open, not made by this phase.

**3. (Minor, non-blocking.)** The 01-03-SUMMARY.md's own coverage block flags that its
`<human-check>` (judging whether the Verdict section reads as honest rather than
outcome-arranged) was self-assessed by the executing agent with no human in the loop, and
recommends human confirmation before being treated as final. This verification independently
re-read the full validation record and agrees with that self-assessment (see Evidence #3) — the
verdict is not spun — but per the SUMMARY's own request, a human read of that document is still
worth doing rather than relying solely on two AI passes (the original executor's and this
verifier's).

## Recommendation

**Proceed.** Phase 1's engineering and documentation goals are fully met; do not block on the
model's underperformance, since ROADMAP.md never made beating naive/ewm a precondition for
"met." Recommended follow-ups, none blocking:

1. **Aaron should read `docs/data-science/decisions/forecasting_model.md`'s Verdict and Open
   Questions sections directly** — this is the single most decision-relevant artifact from this
   phase, and its central finding (naive beats the trained model at this horizon) is easy to miss
   if only the SUMMARY.md bullet points ("Phase 1 complete, 3/3 plans executed") are skimmed.
2. Decide whether to invest further (longer horizon / richer features / different lag structure)
   before recommending `"ml"` as production-preferred, or to ship `"naive"`/`"ewm"` as the
   production forecast methods for now and revisit `"ml"` once Track 1's live archive accrues
   real per-point (rather than two-endpoint-proxy) bottleneck history. Both are legitimate paths;
   this verification does not recommend one over the other — that is a project-scope decision,
   not a code-verification finding.
3. Mark ROADMAP.md Phase 1 and Progress table complete (orchestrator's task, not this agent's —
   left unmodified here as instructed).

---

_Verified: 2026-09-24_
_Verifier: Claude (gsd-verifier)_
