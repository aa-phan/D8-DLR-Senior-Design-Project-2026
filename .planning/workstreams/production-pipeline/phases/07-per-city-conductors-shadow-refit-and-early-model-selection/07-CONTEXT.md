# Phase 7: Per-City Conductors, Shadow Refit and Early Model Selection - Context

**Gathered:** 2026-10-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Production rates each city through its own conductor configuration (COND-01/02), while the shadow collector, the 12 frozen Drake artifacts and the frozen evaluation modules stay byte-identical on Drake. Confirmation protocol v4 (SEL-01) is drafted and signed before any FRESH outcome is read. It retires the 2026-11-24 run and selects which shadow model, if any, replaces `ml` through one early FRESH read on 2026-11-01, plus a pre-registered conditional re-test on 2026-11-08. B1, B2, B4 and B5 are closed, the Phase 3 validation is re-run on the same 2026-09-08..09-28 window, and the owner signs a new go/no-go (REVAL-01).

Wiring a selected shadow model into the live path is out of scope (REQUIREMENTS.md "Out of Scope"; a follow-on phase).

**Timing:** today is 2026-10-25. The FRESH cutoff (2026-10-25T00Z) has already passed, so v4 must be drafted and signed in the next day or two. Nobody may open a FRESH outcome before the instant (anti-peeking, ROADMAP constraints).

</domain>

<decisions>
## Implementation Decisions

### FRESH read: conductor and evidence weight (SEL-01, SEL-03, SEL-04)
- **D-01:** The FRESH headline scores the candidates under the **production per-city conductor configs**: reconstructed frames recompute truth, `raw_forecast` and persistence under that config, and `ml_cooling_corrected` / `reference_ml_refit_24h` use models fit under it. `ml_wind_corrected` is conductor-independent and is reused. The frozen Drake artifacts are scored in the same read as a **labelled secondary**. The live shadow logs (Drake, as collected) remain the live-system check and are never pooled with the headline. Because of D-09, the production config is Drake unless Power Systems answers by the D-11 deadline, so in the default case the headline and the frozen Drake setup coincide.
- **D-02:** **FRESH decides; ABLATION and TEST only veto.** Only the FRESH read can name a winner. The ABLATION conductor-invariance re-score and the per-city TEST-split scoring are pre-registered gates that disqualify a candidate whatever FRESH says. Example vetoes: a candidate whose point order against the default flips under the bracketing conductor set, or one that loses to `raw_forecast` on TEST in at least 3 of 4 cities. The exact veto criteria are drafted in v4 for owner signature.
- **D-03:** **Late Power Systems answers (after the FRESH read):** the decision stands if the ABLATION test showed the ranking is invariant across the bracketing set. Cooling and reference are then refit under the real values for serving, with no FRESH re-read. If ABLATION did not show invariance, the decision is labelled **conductor-conditional**, and v4 pre-registers a descriptive re-score under the confirmed conductor that can flag a problem but cannot overturn the decision. — **Reversibility:** one-way — fixed in signed v4 before outcomes; changing it afterwards would be a post-hoc protocol change.
- **D-04:** **One method for all four cities**, keeping v3 decision 8's structure: "consistent" means the point estimate favours it in at least 3 of 4 cities. No per-city winners.

### v4 dates, threshold and no-winner rule (SEL-01)
- **D-05:** **Dates:** the same 1-week truth-revision margin as v3. `valid_time` cutoff **strictly before 2026-10-25T00:00Z**, instant **2026-11-01T00:00Z**, about 100 headline rows per city (25 days × 4 cycles). The fetch window pinned in the frozen evaluation modules (`backend/forecast_shadow_confirm.py:186-191`, `backend/forecast_shadow_eval_core.py:65-71`) is re-pinned only as v4 explicitly allows. — **Reversibility:** one-way — signed protocol dates.
- **D-06:** **Relative win threshold:** v3's X = 5 A becomes **2% of the city's mean truth ampacity** (MAE reduction), so the bar doesn't move with the conductor. The owner chose 2% because it is roughly what about 100 rows per city can resolve. v3's three evidence levels ("supported" / "indicated, not resolved" / "not shown") and the 9-test city-clustered Holm family (v3 decision 2) carry over unchanged (Claude default; the owner may revisit at signing). — **Reversibility:** one-way — fixed before outcomes.
- **D-07:** **If no candidate qualifies, there is no pick.** v3's fallback rules (keep `ml_wind_corrected` / fall back to `raw_forecast`) are replaced by a pre-registered re-test. No shadow model replaces `ml` at 11-01.
- **D-08:** **Conditional re-test**, pre-registered in v4: instant **2026-11-08T00:00Z**, cutoff **2026-11-01T00:00Z** (same 1-week margin), about 130 rows per city. It grades **all** rows, including the first read's, and uses the same rules. It runs only if the 11-01 read names no winner. This replaces "the single FRESH read" in ROADMAP SC 5 / SEL-04: the planner must update that wording and REQUIREMENTS SEL-04 and record the change in the ml-modeling STATE.md. **Open for the v4 draft:** what happens if the re-test also names no winner. Claude's suggested default for the owner to confirm at signing: no day-ahead pick, and the interim G6 method continues. — **Reversibility:** one-way — pre-registered.

### Provisional conductors (COND-01, COND-02, B1)
- **D-09:** **Every city stays on Drake 795 ACSR at 75 °C, 900 m, current bearings** (`config.DEFAULT_CONDUCTOR_CONFIG_KWARGS`, `CITY_LINE_BEARING_DEG`) until Power Systems answers. The owner explicitly declined the researched AUSTIN alternatives (Drake @100 °C, Suwannee ACSS/TW @200 °C) and the measured-elevation fix (Austin 163 m). The per-city config structure is still built now: per-city type, diameter, AC resistance, MOT, elevation and azimuth, each with a recorded source (for now "current model default, provisional; Power Systems pending"), plus a config-version bump path. Power Systems' values then drop in with no code change. The production-only resolver, the shadow path left on `city_point.city_point` / `config.conductor_kwargs_for`, and the byte-identical golden test are all still built (COND-02).
- **D-10:** Consequence of D-09: SEL-02's refit under the production config is **conditional**. If no Power Systems values arrive by D-11, the production config equals the frozen Drake configuration, so the 12 frozen artifacts serve as the production-conductor models for the headline and no duplicate refit is produced. If values arrive (for any city), cooling and reference are refit for those cities on rows before 2026-03-17 only (asserted), saved as new hashed artifacts, never overwriting the frozen ones. The ABLATION refits under the bracketing set (SEL-03) happen regardless. The planner should reflect this in the SEL-02 / ROADMAP SC 3 wording.
- **D-11:** **Power Systems deadline for the 11-01 test: end of 2026-10-30, recorded as 2026-10-31T00:00Z.** Values received by then are used in the 11-01 headline. Production switches to them via a config-version bump, cooling and reference are refit, and the TEST-split veto is re-scored under them before the instant. Values arriving later fall under D-03 and go into production but not into the 11-01 headline. — **Reversibility:** one-way — written into signed v4.
- **D-12:** **B1 fallback-policy half: keep the current policy** (Finding 1 option A). The owner's standing rule is that a low-side G4 fallback to the documented static rating is safe and only above-band ratings are unsafe (`memory: static-rating-fallback-is-safe`). Static ratings and G4 bounds are unchanged.
- **D-13:** **A GO is allowed while still on the Drake assumption.** The GO lifts the provisional label for the other closed blockers, but each row stays labelled with its conductor basis (already carried by `config_fingerprint` / `config_version` / `rating_basis`, OD-5, DB-06). B1's conductor question stays open until Power Systems answers.

### Interim G6 method, B2/B4/B5, go/no-go (REVAL-01)
- **D-14:** **B2: keep `ml` (OD-3 stands) and retrain the four per-city forecast models with the projected (line-perpendicular) wind speed as the feature** (Finding 2 option B), under the current production config. The new artifacts get new hashes, the live manifest is regenerated (`dlr_live_check_models.py --write-manifest`), and they are committed per OD-10. Ask before pushing anything that changes live CI. If Power Systems' values are adopted, the retrain is redone under them.
- **D-15:** **If the retrained `ml` still has higher error than naive in the September re-run, the owner decides at the go/no-go.** There is no pre-set rule; report the comparison clearly.
- **D-16:** **B4: accept CORPUS_CHRISTI's 11.01% detector trip rate as safe** (a trip falls back to the safe static rating; D-12). Re-measure it in the re-run. Log a follow-up to refit the CORPUS_CHRISTI anomaly detector on station-measured inputs together with the conductor-driven detector retrain when Power Systems' values arrive (or by a fallback date the plan proposes if they never answer), then re-check it with a replay on the September window.
- **D-17:** **B5: when the `ml` forecast is withheld from G6 because of a gap** (`data_cleaning.ML_LOOKBACK_ROWS` = 7 consecutive usable rows not met), **G6 uses the naive band instead**, which needs only 1 recent usable slot (`MAX_TRAILING_GAP_SLOTS` = 1). `ml` stays primary. Fallback rows stay excluded from history (the Phase 2 rule is unchanged). Rationale: this restores the high-side band check, the owner's one unsafe direction, at AUSTIN, where `ml` was withheld 96 of 111 evaluated steps against naive's 28. Which method gated each step should be visible in the trace and report.
- **D-18:** **GO requires a checklist, then the owner's signature:** B1, B2, B4 and B5 each closed with a recorded decision; the re-run complete on 2026-09-08..09-28 with 0 replay-fidelity mismatches; the share of hours in which the band check ran reported per city, AUSTIN in particular. The owner then signs GO or NO-GO on the report. There are no hard numeric bars (no ≤5% trip-rate requirement).

### Claude's Discretion
- Drafting the full v4 text: the exact ABLATION invariance criteria (start from `shadow_early_decision_options.md` §5.4: set Drake-75 control, Drake-100, Falcon-90, Suwannee-150, Suwannee-200, plus a 163 m Austin variant), the exact TEST veto criteria, and the precise "qualifies" definition combining D-04 and D-06. The owner signs it.
- **Partial Power Systems answers by D-11:** default to switching only the cities with a complete answer, leaving the rest on Drake. This is flagged for the owner to confirm in v4.
- The fallback date for the CORPUS_CHRISTI detector refit if Power Systems never answers (D-16).
- Whether the TEST-split scoring needs a development-window provider (`shadow_early_decision_options.md` option (e) notes one exists for tests).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Selection and protocol
- `docs/data-science/decisions/shadow_early_decision_options.md` — candidates, evidence bases, option (b) row and power estimates, §5 conductor analysis, §5.4 ABLATION invariance design, open questions
- `docs/data-science/decisions/confirmation_protocol_v3_per_city.md` — signed v3, which v4 amends (decisions 2, 5, 8, 9; anti-peeking; V1-V6 validity threats; frozen artifact hashes)
- `docs/data-science/decisions/forecast_correction_followup_audit.md` — ABLATION/TEST/FRESH definitions (`:45-49`), ABLATION replication, owner's wind tie-break
- `docs/data-science/decisions/forecast_correction_experiment.md` — candidate definitions, corridor-era results
- `docs/data-science/decisions/shadow_collection_runbook.md` — fit windows, frozen configurations, `assert_no_test_leak`
- `.planning/workstreams/ml-modeling/STATE.md` — must record the v4 amendment (ROADMAP Phase 7 context)

### Validation and blockers
- `docs/data-science/decisions/real_data_validation.md` — B1-B5 findings and options (§"Findings for the owner"), signed NO-GO, reproduce commands for the re-run
- `.planning/workstreams/production-pipeline/phases/03-real-data-validation/03-05-CONDUCTOR-RESEARCH.md` — Austin conductor/MOT/elevation research, Power Systems questions
- `.planning/workstreams/production-pipeline/phases/03-real-data-validation/03-05-conductor_sensitivity.py` — conductor catalogue values used for the bracketing set
- `docs/data-science/decisions/line_bearing_check.md` — bearing assumptions

### Workstream
- `.planning/workstreams/production-pipeline/ROADMAP.md` — Phase 7 goal and success criteria (SC 3 and SC 5 wording to update per D-08, D-10)
- `.planning/workstreams/production-pipeline/REQUIREMENTS.md` — COND-01/02, SEL-01..04, REVAL-01, OD-1..OD-10
- `.planning/workstreams/production-pipeline/STATE.md` — AUSTIN fallback open issue, Phase 4/5 identity and model-manifest decisions
- `docs/data-science/decisions/dlr_live_runbook.md` — live model promotion and manifest procedure

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/config.py:140-161` `DEFAULT_CONDUCTOR_CONFIG_KWARGS` / `conductor_kwargs_for`: the shared Drake config. It must stay unchanged for the shadow path; the production resolver is new.
- `backend/city_point.py:45-69` `city_point()`: the shared resolver used by both production and shadow.
- `backend/rating_identity.py`: per-row `config_fingerprint` recipe. Per 04-11, a live module that reads a new config name at import time must not break the backfill identity re-run.
- `backend/dlr_live_check_models.py` + `data/models/LIVE_ARTIFACT_HASHES.sha256`: hash manifest for promoting the B2 retrain.
- `backend/real_data_validation.py` `replay` / `report`: the REVAL-01 re-run (commands in real_data_validation.md "Reproduce").
- `backend/forecast_shadow_confirm.py` (`--override-reason` at `:784-786`) and `backend/forecast_shadow_eval_core.py`: the FRESH headline scorer, frozen except as v4 allows.

### Established Patterns
- Production callers to repoint to the production resolver: `backend/city_rating.py:377`, `backend/anomaly_training.py:566`, `backend/forecast_training.py:200-226`, `backend/real_data_validation.py`, `backend/dlr_orchestrator.py:95` (static rating only).
- Shadow callers that must keep Drake: `backend/forecast_shadow_pipeline.py` (`:656`, `:1644`, `:1822`), `forecast_shadow_fit_models.py`, `forecast_shadow_fit_reference_refit.py`, `forecast_shadow_confirm.py`, `forecast_shadow_demo.py`, `legacy_corridor.py`.
- `backend/forecast_training.py:204-224` keeps the measured `wind_speed` as the feature; this is the B2 retrain point. Serving reads the projected `wind_speed` (`backend/ampacity_forecast.py:124-161`, `city_rating._project_wind`).
- `backend/data_cleaning.py` `ML_LOOKBACK_ROWS` / `MAX_TRAILING_GAP_SLOTS` and the G6 forecast selection in `city_pipeline`: the D-17 integration point. `ampacity_forecast.FORECAST_METHODS = ("naive", "ewm", "ml")`.

### Integration Points
- Shadow artifacts in `data/shadow/models/` are never written. New refits go to a new, hashed location.
- Never open `data/experiment/anchored_pair_frame_*_2026-09-30_*`. Cached frames `..._2024-01-20_2026-09-29_...` contain TEST rows, so filter in code to before 2026-03-17 and assert it for ABLATION and refits.

</code_context>

<specifics>
## Specific Ideas

- The owner wants decisions explained in plain language before options are offered (`memory: explain-decisions-plainly`). The v4 draft and go/no-go report should open with a plain-English summary.
- The owner treats low-side fallbacks as safe and the high side as the only safety concern. Frame band engagement (D-17) as the safety item, and fallback rates as accuracy/coverage items.

</specifics>

<deferred>
## Deferred Ideas

- Refit the CORPUS_CHRISTI anomaly detector on station-measured inputs, bundled with the conductor-driven detector retrain (D-16 follow-up).
- Real per-city elevations (Austin 163 m etc.) and the researched AUSTIN conductor alternatives: deferred to Power Systems' answer by owner choice (D-09).
- Wiring the selected shadow model into the live path (already out of scope; follow-on phase).

</deferred>

---

*Phase: 07-per-city-conductors-shadow-refit-and-early-model-selection*
*Context gathered: 2026-10-25*
