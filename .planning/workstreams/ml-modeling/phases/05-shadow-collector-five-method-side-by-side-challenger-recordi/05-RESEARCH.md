# Phase 5: Shadow Collector — Five-Method Side-by-Side Challenger Recording - Research

**Researched:** 2026-10-07
**Domain:** Extending an existing, inert, experimental shadow pipeline (`backend/forecast_shadow_pipeline.py`
/ `forecast_shadow_collect.py`) to compute and log five candidates per cycle instead of one, reusing
Phase 3/4's existing offline estimator/physics code. No new libraries; the domain is entirely
in-repo code structure and data-flow, verified by direct read this session.
**Confidence:** HIGH for every code-grounded claim below (file:line cited, read directly this
session); the one open empirical question (offline retrain runtime for `reference_ml_refit_24h`)
is flagged LOW/ASSUMED and listed in Open Questions, not treated as settled.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01** — Record all five real candidates side by side every cycle: `ml_wind_corrected` (today's
sole recorded candidate, stays the provisional production default), `ml_cooling_corrected`,
`reference_ml_refit_24h`, `raw_forecast`, `persistence_24h`. No winner declared; purely a
recording-breadth expansion.

**D-02** — One shared-input fetch per cycle: every candidate for a given corridor/cycle computed
from the exact same forecast row, the exact same anchor observation, the exact same
`initialization_time`/`availability_time`/`decision_time`/`valid_time` quadruple, and the same
24-hour horizon. A candidate that cannot share alignment with its siblings is marked unavailable
(D-04), never computed from a different input snapshot.

**D-03** — `reference_ml_refit_24h` must use the 24-hour refit MLP (`forecast_training.
build_training_matrix`'s `horizon_minutes=1440` seam), never `ampacity_forecast.py`'s persisted
60-minute `"ml"` production model and never that module's process-global per-corridor model cache.

**D-04** — Validate required features per candidate before computing; unavailable means unavailable
(with a reason), never silent substitution. A prediction-method fallback must always be visible
under its own name — never silently reported as another candidate's label.

**D-05** — `persistence_24h`'s own ampacity figure must be a value genuinely available at this
cycle's decision time (e.g. the collector's own prior logged entry for that corridor ~24h back),
never recomputed from hindsight/reanalysis data. No decision-time-available anchor yet → record
unavailable (D-04), never backfilled.

**D-06** — Preserve every existing record field, per candidate, independently: per-city predictions
and corridor-level weakest-link minimum, that candidate's own `model_version`, that candidate's own
`input_provenance` (including `anchor_provenance.<city>.anchor_source`), the shared four timestamps.
Provider fallback vs. prediction-method fallback must be tracked per candidate, never conflated
across candidates in the same cycle.

**D-07** — Isolate per-candidate failures (distinct from D-04's input-unavailability case): one
candidate's real code-level failure must not prevent the other four from being computed/logged, and
must not crash the run. Durable storage stays append-only (`>>`, never overwrite — commit `417dc54`).

**D-08** — Document, in the shadow runbook or equivalent, when five-method collection starts and
that it is independent of and does not substitute for the Nov 1/Nov 24 fresh-basis confirmation
protocol (`_fresh_confirmation_report`/FRESH-basis scoring in `forecast_correction_followup_audit.md`).

**D-09** — No silent protocol changes: no changing the Nov 1/Nov 24 dates, no pooling model
versions, no retuning based on this collector's own logs, no inspecting any FRESH row's
predicted-vs-truth outcome before 2026-11-24T00:00:00 UTC. Confirming the collector's logs exist,
timestamps are sane, and rows accrue without errors is an explicitly permitted mechanical health
check at any time.

**D-10** — Verify with targeted unit/integration tests, one real live collection cycle end to end
(local or manual GitHub Actions dispatch), and confirmation that the *next scheduled* (cron-
triggered) GitHub Actions run persists the expanded five-candidate shape — not just a manual run.

**D-11** — Completion report describes operational completeness/blockers and physical plausibility
only — never accuracy, calibration, or reliability claims comparing candidates. Production
(`dlr_pipeline.py`) remains completely unchanged.

### Claude's Discretion

Not explicitly separated in CONTEXT.md as its own section — the Execution Notes direct the
researcher/planner toward specific implementation choices (reuse existing functions, restructure
per-candidate try/except, use the collector's own prior log entries for persistence) but leave the
exact code shape (e.g. whether `ShadowPipeline` is extended to a multi-method object or a new
orchestrator function is added) to the planner.

### Deferred Ideas (OUT OF SCOPE)

- Picking a new provisional production default, or wiring any candidate into `dlr_pipeline.py`.
- Declaring any candidate a winner, or any plan task that reads like "determine which correction
  method is best."
- Touching the Nov 1 freeze / Nov 24 evaluation dates, `_fresh_confirmation_report`, or any FRESH-row
  outcome inspection.
- Changing production behavior in any file outside the shadow module and its tests.
</user_constraints>

<phase_requirements>
## Phase Requirements

No FCST/ANOM requirement ID applies — `REQUIREMENTS.md` shows FCST-01/02 and ANOM-01/02 already
Complete against Phases 1–2; this phase (like Phase 3/4) is scoped entirely by its own CONTEXT.md
decisions D-01 through D-11, carried in each plan's `requirements:` field exactly as Phase 3/4 did.

| ID | Description | Research Support |
|----|-------------|------------------|
| D-01 | Record all five candidates | §1–2 map each candidate to its exact existing function/class |
| D-02 | Shared-input fetch | §3 enumerates every distinct live fetch and which candidates need which subset |
| D-03 | 24h refit MLP, never 60-min production artifact/cache | §2's `reference_ml_refit_24h` row; confirmed via `fit_fitted_arms`'s own docstring and test |
| D-04 | Per-candidate feature validation, unavailable-marking | §3's per-candidate input footprint table |
| D-05 | Persistence decision-time constraint | §4 |
| D-06 | Preserve every field per candidate | §5 |
| D-07 | Per-candidate failure isolation | §1's current control-flow finding + Open Risks |
| D-08 | Runbook documentation of start date / protocol relationship | §7 confirms workflow mechanics the runbook entry must describe |
| D-09 | No silent protocol changes | Verified against `forecast_correction_followup_audit.md`'s carve-out text (quoted in Summary) |
| D-10 | Targeted tests + live cycle + scheduled-run confirmation | §6 (existing coverage), §7 (workflow mechanics) |
| D-11 | Operational-only reporting | No code implication; carried into plan verification language only |
</phase_requirements>

## Summary

The existing shadow collector is a thin, already-correct skeleton for exactly one candidate
(`ml_wind_corrected`, via `CorridorWindCorrectionMethod`), called from `forecast_shadow_demo.run_once`,
which `forecast_shadow_collect.collect_once` loops over corridors to invoke — **one corridor, one
hardcoded method-name string literal, per iteration** `[VERIFIED: backend/forecast_shadow_collect.py:101]`.
There is currently **no per-candidate concept anywhere in the collection loop** — `collect_once`
calls `forecast_shadow_demo.run_once(corridor, "ml_wind_corrected")` once per corridor, and nothing
iterates over a set of methods. Extending this to five candidates per cycle is breadth, not a
rebuild: four of the five candidates' real math already exists as working, tested functions/classes
this phase reuses verbatim — `ml_cooling_corrected` → `CoolingCorrectionShadowMethod` (already
defined in `forecast_shadow_pipeline.py`, just never instantiated by the demo script)
`[VERIFIED: backend/forecast_shadow_pipeline.py:729-745]`; `raw_forecast` → `RawForecastShadowMethod`
(already the fallback target) `[VERIFIED: backend/forecast_shadow_pipeline.py:748-769]`;
`persistence_24h` → no existing live implementation at all (Phase 3/4's `_make_persistence_24h_arm`
reads a hindsight truth column, D-05 forbids that for the live collector) — this is genuinely new
code, reading the collector's own prior JSONL entry; `reference_ml_refit_24h` → an estimator-fitting
recipe exists (`forecast_experiment.fit_fitted_arms`'s `arm5_estimator` via
`forecast_training.build_training_matrix(horizon_minutes=1440)` + `CANDIDATE_ESTIMATORS["MLPRegressor"]`)
but **no persisted artifact for it exists on disk or in git today** — `data/shadow/models/` (the one
directory this project deliberately carved out of `.gitignore` specifically so the GitHub Actions
runner can load trained artifacts with no network access) currently holds only
`ml_wind_corrected_*.joblib` and `ml_cooling_corrected_*.joblib`, no `reference_ml_refit_24h_*.joblib`
`[VERIFIED: git ls-files data/shadow/; .gitignore:16-24]`. This is the phase's one genuine offline
prerequisite: an estimator must be fit (reusing `forecast_training.build_training_matrix` +
`forecast_correction_models`-style persistence, not retraining logic) and committed to
`data/shadow/models/` before the live collector can serve `reference_ml_refit_24h`'s real path; D-04
means it is simply marked unavailable for any cycle where that artifact is missing, which is an
acceptable (if initially-degraded) starting state, not a blocker to shipping the rest.

The collector's shared inputs are exactly two live fetches per corridor per cycle — one forecast row
per endpoint city (`fetch_live_forecast_for_valid_time`, Open-Meteo) and one anchor observation per
endpoint city (`fetch_live_anchor_observation`, TCEQ→Synoptic) — both already looped per-city inside
`CorridorWindCorrectionMethod.predict` `[VERIFIED: backend/forecast_shadow_pipeline.py:678-726]`.
Every candidate except `persistence_24h` needs some subset of these two fetches; `persistence_24h`
needs **neither** — it needs only the collector's own prior JSONL entry for the same corridor, which
is a wholly new read-path this collector does not currently have (today it only ever appends,
never reads back its own log — confirmed by grepping every `open(...)` call in
`forecast_shadow_pipeline.py`, which shows exactly one, opened in `"a"` mode
`[VERIFIED: backend/forecast_shadow_pipeline.py:930]`). The existing `fallback_used`/`fallback_reason`/
`model_version`/`input_provenance`/four-timestamp fields are all currently top-level, single-candidate
fields in one flat JSON object per logged line `[VERIFIED: backend/forecast_shadow_pipeline.py:914-932]`
— this phase's own D-06 requires every one of these per-candidate, which is a genuine restructuring
of the log-entry shape (flat → nested-by-method-name, or five independent per-method log calls per
cycle), not something the current schema already supports. The scheduled GitHub Actions workflow
(`.github/workflows/shadow_collect.yml`) runs `forecast_shadow_collect.py` directly with no
awareness of which methods it invokes internally — D-10's "confirm the next scheduled run persists
the expanded shape" is verifiable purely by waiting for the next 06:00/18:00 UTC cron tick and
inspecting the committed JSONL/README.md on `shadow-collection-data` for five method entries per
corridor per cycle; no workflow-file change is required unless the collector's own timeout/runtime
grows enough to threaten the job's 15-minute `timeout-minutes` budget (worth flagging, not yet
measured).

**Primary recommendation:** Generalize `forecast_shadow_demo.run_once`/`collect_once`'s
single-method call into a per-corridor loop over all five method names, reusing
`CorridorWindCorrectionMethod`, `CoolingCorrectionShadowMethod`, and `RawForecastShadowMethod`
unchanged; add two new classes (`Persistence24hShadowMethod` reading the collector's own prior JSONL
entry, and a `ReferenceRefit24hShadowMethod` wrapping a persisted MLP estimator fit via
`forecast_training.build_training_matrix(horizon_minutes=1440)`); fetch each corridor's two live
inputs exactly once per cycle and pass the same validated frame/timestamps into each of the five
method calls; wrap each candidate's compute+log in its own try/except inside the per-corridor loop
(not a shared one); and restructure `log_prediction`'s JSON shape to nest per-candidate fields under
each method name while still preserving the single flat `ml_wind_corrected` view any legacy reader
depends on.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Five-candidate orchestration (per-cycle loop, per-candidate try/except) | Offline/shadow backend (`backend/forecast_shadow_*.py`, not imported by production) | — | Pure Python orchestration; no browser/API/DB tier involved; never reaches `dlr_pipeline.py` |
| Shared live-input fetch (forecast + anchor observation) | Offline/shadow backend | External provider (Open-Meteo, TCEQ/Synoptic) | Already-wired network calls (`fetch_live_forecast_for_valid_time`, `fetch_live_anchor_observation`); this phase reuses, does not rebuild |
| `ml_wind_corrected`/`ml_cooling_corrected` prediction math | Offline ML (`forecast_correction_models.py`) | Shadow backend (wiring only) | Already-fitted, persisted `.joblib` models; shadow module is a thin caller |
| `reference_ml_refit_24h` prediction math | Offline ML (`forecast_training.py` seam via `forecast_experiment.fit_fitted_arms`) | Shadow backend (persistence + wiring, new) | Needs a fit-once-offline, load-at-runtime artifact exactly like wind/cooling already work; no new training *algorithm*, just a new persisted artifact and a shadow-side loader |
| `persistence_24h`'s decision-time anchor | Offline/shadow backend (reads its own prior JSONL) | Filesystem (`data/shadow/predictions/*.jsonl`, or `shadow-collection-data` branch in CI) | New read-path; genuinely new code, no existing reusable reader |
| Append-only durable logging | Offline/shadow backend + CI workflow commit step | GitHub Actions / `shadow-collection-data` branch | Unchanged mechanism; this phase changes the record *shape*, not the storage discipline |
| Scheduled execution | CI (`.github/workflows/shadow_collect.yml`) | — | No workflow-file change needed unless runtime budget is threatened (Open Risks) |

No capability in this phase touches the browser, frontend server, CDN, or production database tiers
— everything is the existing offline/shadow backend tier, mirroring Phase 3/4's own
"standalone, not imported by the runtime pipeline" convention.

## Standard Stack

No new libraries. This phase extends existing, already-installed-and-verified code
(`scikit-learn`, `pandas`, `numpy` — all already present per Phase 3/4's own verified `.venv`
introspection) with new orchestration and two new method classes. No `pip install` step, no
Package Legitimacy Audit is required.

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| (none new) | — | — | Every dependency this phase needs (`pandas`, `numpy`, `scikit-learn`, `joblib`, `fcntl`, `requests` via `weather_provider`) is already installed and already imported by the modules this phase extends. |

### Package Legitimacy Audit

Not applicable — this phase installs no external packages. Skipped per the protocol's own
"required whenever this phase installs external packages" scope condition.

## Architecture Patterns

### System Architecture Diagram

```
Scheduled trigger (cron 06:00/18:00 UTC, or workflow_dispatch)
         │
         ▼
forecast_shadow_collect.collect_once()
  - acquire flock (data/shadow/.collect.lock)
  - for each corridor in config.CORRIDOR_ENDPOINTS:        ← existing per-corridor loop
      ├─► [NEW] fetch shared inputs ONCE per corridor/cycle (D-02):
      │     - fetch_live_forecast_for_valid_time(city_a), (city_b)   [Open-Meteo]
      │     - fetch_live_anchor_observation(city_a), (city_b)       [TCEQ → Synoptic]
      │     - one ShadowTimestamps quadruple shared by all 5 candidates
      │
      └─► [NEW] for each of the 5 candidate methods:               ← NEW inner loop (D-01)
            ml_wind_corrected      → CorridorWindCorrectionMethod   (existing class, reused)
            ml_cooling_corrected   → CoolingCorrectionShadowMethod  (existing class, reused)
            raw_forecast           → RawForecastShadowMethod        (existing class, reused)
            persistence_24h        → Persistence24hShadowMethod     (NEW: reads own prior JSONL entry)
            reference_ml_refit_24h → ReferenceRefit24hShadowMethod   (NEW: loads persisted MLP artifact)
              │
              ├─ per-candidate try/except (D-07): one candidate's exception
              │    is caught HERE, logged as that candidate's own failure,
              │    never escapes to abort the other 4 candidates
              │
              ├─ per-candidate feature validation (D-04): missing inputs for
              │    THIS candidate → record "unavailable" with a reason,
              │    skip computing, continue to next candidate
              │
              └─► log_prediction(...) appends ONE JSON line per cycle per
                    corridor, nested per-candidate (D-06 restructure),
                    to data/shadow/predictions/<corridor>.jsonl (>>, append-only)
         │
         ▼
GitHub Actions workflow step: clone shadow-collection-data branch, `cat >>` each
corridor's jsonl, render README.md table, commit + push (unchanged mechanism)
```

A reader can trace the primary cycle: trigger → per-corridor loop → shared-input fetch (once) →
five-candidate inner loop (each isolated by its own try/except and feature-validation gate) → one
append-only log write → CI commit. The oracle/`nwp_wind_delta` arms from Phase 3/4's offline harness
never appear here — this phase's five candidates are exactly D-01's named five, not the full
seven-arm registry.

### Recommended Project Structure

```
backend/
├── forecast_shadow_pipeline.py   # ADD: Persistence24hShadowMethod, ReferenceRefit24hShadowMethod
│                                 #   classes; generalize log_prediction's record shape to carry
│                                 #   per-candidate fields (D-06); REUSE existing
│                                 #   CorridorWindCorrectionMethod/CoolingCorrectionShadowMethod/
│                                 #   RawForecastShadowMethod unchanged
├── forecast_shadow_demo.py       # GENERALIZE: run_once's single-method body into a per-corridor,
│                                 #   per-candidate orchestration (or add a new run_once_all_methods
│                                 #   entry point, calling the existing single-method one 5x with
│                                 #   shared fetched inputs threaded through)
├── forecast_shadow_collect.py    # CHANGE: collect_once's hardcoded "ml_wind_corrected" argument →
│                                 #   call the new all-methods entry point instead (1-line call-site
│                                 #   change; existing lock/exit-code/delay logic untouched)
├── forecast_training.py          # UNCHANGED — reused for reference_ml_refit_24h's offline fit
├── forecast_correction_models.py # UNCHANGED — reused for ml_wind_corrected/ml_cooling_corrected
├── tests/
│   ├── forecast_shadow_pipeline_test.py   # EXTEND: new tests for the two new method classes +
│   │                                       #   restructured log_prediction shape
│   └── forecast_shadow_collect_test.py    # EXTEND: assert all 5 methods attempted per corridor,
│                                           #   one candidate's failure doesn't block the other 4
data/shadow/models/
└── reference_ml_refit_24h_<corridor>.joblib   # NEW artifact — must be fit offline once and
                                                 # committed (data/shadow/models/ is NOT gitignored,
                                                 # by deliberate 2026-10-06 carve-out) before the
                                                 # live collector can serve this candidate for real
docs/data-science/decisions/
└── shadow_collection_runbook.md  # ADD: dated note per D-08 (five-method collection start date,
                                   #   relationship to Nov 1/24 protocol)
```

### Pattern 1: Reuse the existing `CorrectionMethod` protocol — don't invent a sixth interface

**What:** `forecast_shadow_pipeline.py` already defines a `CorrectionMethod` Protocol
(`name: str`, `predict(frame, geometry) -> float`) that `CorridorWindCorrectionMethod`,
`CoolingCorrectionShadowMethod`, and `RawForecastShadowMethod` already implement
`[VERIFIED: backend/forecast_shadow_pipeline.py:564-576]`. The two new candidates
(`persistence_24h`, `reference_ml_refit_24h`) should implement this exact same protocol so
`ShadowPipeline.predict`'s existing try/except/fallback/logging machinery works unchanged for all
five — no new orchestration class is needed at the single-prediction level, only at the
per-cycle "loop over five methods" level.
**When to use:** Both new method classes.
**Example:**
```python
# Source: backend/forecast_shadow_pipeline.py:564-576 (CorrectionMethod Protocol), read this session.
class CorrectionMethod(Protocol):
    name: str
    def predict(self, frame: pd.DataFrame, geometry) -> float: ...
```

### Pattern 2: `ShadowPipeline` already isolates ONE method's failure via try/except — reuse it five times, don't share one try/except across candidates

**What:** `ShadowPipeline.predict` already catches any exception from its `primary_method` and
routes to `fallback_method` with a `fallback_reason` — this is D-07's isolation mechanism, but it
currently isolates "the one configured method" from "the hardcoded raw_forecast fallback," not
"candidate N" from "candidates N+1..5." The planner's job is to construct **five separate
`ShadowPipeline` instances per corridor per cycle** (one per candidate, sharing the same fetched
`frame`/`timestamps`), each with its own try/except boundary — not to build one shared try/except
around a loop that could let one candidate's exception abort the others.
**When to use:** The per-cycle orchestration change in `forecast_shadow_demo.py`/
`forecast_shadow_collect.py`.
**Example:**
```python
# Source: backend/forecast_shadow_pipeline.py:860-904 (ShadowPipeline.predict), read this session —
# pattern to replicate per candidate, not share across candidates:
for method_name, primary_method in five_candidates.items():
    try:
        pipeline = ShadowPipeline(corridor, primary_method)
        prediction = pipeline.predict(frame, timestamps)   # already isolates method-internal failure
    except Exception as exc:
        # D-07: a REAL code bug escaping ShadowPipeline.predict itself (not the already-caught
        # inner failure) — record THIS candidate as failed, continue to the next.
        ...
```

### Pattern 3: `data/shadow/.../*.jsonl`'s own prior entries are the D-05 persistence source — no reusable reader exists yet, build on `forecast_shadow_healthcheck._last_entry`'s idiom

**What:** `forecast_shadow_healthcheck.py` already has a `_last_entry(corridor)` helper that reads
`data/shadow/predictions/<corridor>.jsonl` line-by-line and returns the last parsed JSON object
`[VERIFIED: backend/forecast_shadow_healthcheck.py:44-56]` — this is the only existing code in the
repo that reads this collector's own log back. `persistence_24h`'s decision-time anchor needs the
same idiom, but filtered to **the entry whose `valid_time` is ~24h before this cycle's own
`valid_time`** (not simply "the last entry," since the last entry is this cycle's immediately
preceding run, ~12h ago at the twice-daily cadence, not 24h). See §4 for the exact field to key off
and the cold-start shape.
**When to use:** The new `Persistence24hShadowMethod`.
**Example:**
```python
# Source: backend/forecast_shadow_healthcheck.py:44-56, read this session — the only existing
# "read our own JSONL back" idiom in this repo; persistence_24h's reader should follow this same
# shape (open, iterate lines, json.loads), but search for a specific valid_time match rather than
# just taking the last line:
def _last_entry(corridor: str) -> dict | None:
    path = os.path.join(PREDICTIONS_DIR, f"{corridor}.jsonl")
    if not os.path.exists(path):
        return None
    last = None
    with open(path, "r") as fh:
        for line in fh:
            line = line.strip()
            if line:
                last = line
    if last is None:
        return None
    return json.loads(last)
```

### Anti-Patterns to Avoid

- **Computing `persistence_24h` from reanalysis/truth data, mirroring Phase 3/4's offline
  `_make_persistence_24h_arm`:** That arm reads `frame["anchor_dlr_amps"]`, a column built from
  Open-Meteo's **Archive API** (settled reanalysis truth) at the anchor time
  `[VERIFIED: backend/forecast_experiment.py:384-406]`. D-05 explicitly forbids this for the live
  collector — the live anchor must be a value that was genuinely available at THIS cycle's own
  decision time, i.e. this collector's own prior logged prediction, never a reanalysis backfill.
- **Sharing one try/except around the five-candidate loop:** Would violate D-07 — one candidate's
  bug would abort the remaining four for that cycle.
- **Loading `reference_ml_refit_24h` from `ampacity_forecast.py`'s persisted 60-minute `"ml"` model
  or its process-global per-corridor cache:** D-03 explicitly forbids this; `ampacity_forecast.py`
  is never imported by the correct path (`forecast_training.build_training_matrix` +
  `forecast_training.CANDIDATE_ESTIMATORS["MLPRegressor"]`, which `forecast_experiment.
  fit_fitted_arms` already demonstrates never touches `ampacity_forecast._load_corridor_model`
  `[VERIFIED: backend/tests/forecast_experiment_test.py:1437-1457]`).
- **Fetching inputs once per candidate instead of once per corridor/cycle:** Violates D-02 directly
  — would make five separate network round-trips per corridor per cycle instead of one, and risks
  five slightly different `decision_time` values for what should be one shared decision instant.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Wind-correction prediction | A new correction-math implementation | `forecast_correction_models.predict_wind_correction` + `thermal_model.perpendicular_wind`/`ieee738_ampacity`, already wired in `CorridorWindCorrectionMethod` | Already fitted, tested, and persisted; this phase's job is wiring breadth, not new math |
| Cooling-correction prediction | A new convective-term correction | `forecast_correction_models.predict_cooling_correction` + `apply_cooling_correction`, already wired in `CoolingCorrectionShadowMethod` | Same reuse rationale |
| 24-hour MLP refit training | A hand-rolled training loop for `reference_ml_refit_24h` | `forecast_training.build_training_matrix(horizon_minutes=1440)` + `forecast_training.CANDIDATE_ESTIMATORS["MLPRegressor"]` + `forecast_training.fit_corridor_model` | Exactly the recipe `forecast_experiment.fit_fitted_arms` already uses for this arm (D-03's own re-affirmed isolation requirement) — a fresh hand-rolled trainer risks silently diverging from the one this project already validated |
| Weakest-link corridor reduction (any candidate needing a per-city → corridor reduction) | A second elementwise-minimum implementation | `forecast_training.corridor_weakest_link` | The repository's one weakest-link reduction, already reused by `CorridorWindCorrectionMethod` |
| Reading the collector's own prior log entry | A new ad-hoc JSONL scan | Follow `forecast_shadow_healthcheck._last_entry`'s existing idiom, generalized to search for a specific `valid_time` match rather than only the last line | Only one such reader exists in the repo; diverging risks a second, subtly different JSONL-parsing convention |

**Key insight:** Every piece of actual prediction math this phase needs already exists and is
already tested — the only genuinely new code is (a) two new thin `CorrectionMethod` classes
(`persistence_24h`'s own-log reader, `reference_ml_refit_24h`'s artifact loader), (b) the
per-cycle "loop over five, isolate failures, validate features per-candidate" orchestration, and
(c) the restructured per-candidate log-entry shape. There is no risk of reinventing a
correction-math wheel here; the risk is entirely in orchestration and data-shape discipline.

## Common Pitfalls

### Pitfall 1: Assuming the current collector already has a per-candidate concept because `ShadowPipeline` takes a "primary_method" argument

**What goes wrong:** `ShadowPipeline.__init__(corridor, primary_method, fallback_method=None)`
looks like it could already support "one of several methods" — but at the collection-loop level
(`forecast_shadow_collect.collect_once` → `forecast_shadow_demo.run_once`), there is exactly one
hardcoded method-name string literal, `"ml_wind_corrected"`, passed once per corridor per cycle
`[VERIFIED: backend/forecast_shadow_collect.py:101]`. `ShadowPipeline` itself is per-prediction
infrastructure, not a per-cycle multi-candidate orchestrator.
**Why it happens:** The class name and constructor signature read as if multiple methods were
already a first-class concept; only the calling code reveals that today only one method is ever
instantiated per corridor per cycle.
**How to avoid:** Read `forecast_shadow_demo.run_once`'s full body (lines 36-173) and
`forecast_shadow_collect.collect_once`'s loop (lines 86-114) before assuming any existing
multi-method capability — confirmed there is none.
**Warning signs:** A plan task that says "extend `ShadowPipeline` to accept five methods" without
first touching `run_once`/`collect_once`'s call sites will miss where the single-method hardcoding
actually lives.

### Pitfall 2: Treating `reference_ml_refit_24h`'s missing artifact as a blocking gap rather than a D-04 "unavailable" case

**What goes wrong:** It is tempting to treat "no persisted `reference_ml_refit_24h` model exists
yet" as something that must be resolved (a training run, a new offline step) before this phase can
ship at all.
**Why it happens:** The other four candidates' artifacts (or math) already exist and work live
today; this one doesn't, which can read as a blocker.
**How to avoid:** D-04 already specifies the correct behavior for exactly this case — if a
candidate's required inputs/artifacts are unavailable for a cycle, record it as unavailable with a
reason, and let the other four candidates proceed. The planner should include a task to fit and
commit the artifact (reusing `fit_fitted_arms`'s exact recipe) as part of this phase's own scope —
but the collector's code should not special-case "retrain if missing"; it should simply report
`reference_ml_refit_24h` unavailable until that one-time offline fit+commit has happened, exactly
like any other missing-input case.
**Warning signs:** A plan task that tries to make the live collector train a model inline (network
+ `scikit-learn` fit inside a GitHub Actions job meant to run in well under its 15-minute budget)
rather than treating the fit as a separate, one-time offline step whose output gets committed to
`data/shadow/models/` (the directory already deliberately carved out of `.gitignore` for exactly
this purpose).

### Pitfall 3: Assuming `persistence_24h`'s "~24 hours ago" entry is simply "the previous log line"

**What goes wrong:** At the collector's twice-daily cadence (06:00/18:00 UTC), the *immediately
preceding* logged entry for a corridor is ~12 hours old, not ~24. Naively reading
"the last line" (as `forecast_shadow_healthcheck._last_entry` does, correctly, for ITS OWN
different purpose — freshness, not a 24h-offset lookup) would silently give `persistence_24h` a
12-hour-old anchor under a 24-hour label.
**Why it happens:** The only existing "read our own log back" code in the repo
(`_last_entry`) is written for a different purpose (staleness check) where "the last line" is
exactly the right thing to read.
**How to avoid:** `persistence_24h`'s reader must scan entries for the one whose `valid_time` (or
`decision_time`) is closest to `this_cycle_valid_time - 24h`, not simply take the last line. See §4
for the exact field recommendation.
**Warning signs:** A test that only exercises the cadence boundary case (immediately-prior entry)
would not catch this — the planner should include a test with multiple entries at different ages.

## Code Examples

### The current single-candidate call site (what to generalize)

```python
# Source: backend/forecast_shadow_collect.py:93-112, read this session — the ENTIRE per-cycle
# per-corridor loop. This is the one place "ml_wind_corrected" is hardcoded as a literal.
hard_failure = False
for i, corridor in enumerate(config.CORRIDOR_ENDPOINTS):
    if i > 0:
        time.sleep(INTER_CORRIDOR_DELAY_S)
    try:
        forecast_shadow_demo.run_once(corridor, "ml_wind_corrected")
    except Exception:
        hard_failure = True
        print(f"forecast_shadow_collect: hard failure for corridor {corridor!r}:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
return 1 if hard_failure else 0
```

### The existing per-candidate classes to reuse unchanged

```python
# Source: backend/forecast_shadow_pipeline.py:636-769, read this session.
class CorridorWindCorrectionMethod:
    name = "ml_wind_corrected"
    # ... fetches BOTH endpoint cities' live forecast + anchor, corrects each, reduces via
    # forecast_training.corridor_weakest_link -- already corridor-correct, already live-wired.

class CoolingCorrectionShadowMethod:
    name = "ml_cooling_corrected"
    def predict(self, frame, geometry):
        prediction = forecast_correction_models.predict_cooling_correction(self.model, frame)
        ampacity = forecast_correction_models.apply_cooling_correction(frame, prediction.q_conv, geometry)
        return float(np.asarray(ampacity)[0])

class RawForecastShadowMethod:
    name = "raw_forecast"
    def predict(self, frame, geometry):
        perp = thermal_model.perpendicular_wind(
            frame["fcst_wind_speed"].to_numpy(dtype=float),
            frame["fcst_wind_direction"].to_numpy(dtype=float),
            geometry.bearing_deg,
        )
        return float(np.asarray(thermal_model.ieee738_ampacity(
            frame["fcst_air_temp"].to_numpy(dtype=float), perp,
            frame["fcst_solar_radiation"].to_numpy(dtype=float), geometry.conductor,
        ))[0])
```

### The offline recipe `reference_ml_refit_24h` must reuse (D-03)

```python
# Source: backend/forecast_experiment.py:1130-1134 (fit_fitted_arms body), read this session --
# the EXACT, already-working recipe this phase's artifact-fitting step must replicate (then
# persist via joblib into data/shadow/models/, following save_correction_model's own convention):
arm5_frame = _arm5_truth_frame(train_val_frame, city_a, city_b)
X5, y5 = forecast_training.build_training_matrix(arm5_frame, horizon_minutes=1440)
arm5_estimator = forecast_training.fit_corridor_model(
    X5, y5, forecast_training.CANDIDATE_ESTIMATORS["MLPRegressor"]()
)
```

### The only existing "read our own JSONL log back" code (basis for `persistence_24h`)

```python
# Source: backend/forecast_shadow_healthcheck.py:44-56, read this session.
def _last_entry(corridor: str) -> dict | None:
    path = os.path.join(PREDICTIONS_DIR, f"{corridor}.jsonl")
    if not os.path.exists(path):
        return None
    last = None
    with open(path, "r") as fh:
        for line in fh:
            line = line.strip()
            if line:
                last = line
    if last is None:
        return None
    return json.loads(last)
```

## State of the Art

| Old Approach (Phase 4, this module) | New Approach (this phase) | When Changed | Impact |
|--------------------|------------------|--------------|--------|
| One hardcoded method name per corridor per cycle (`"ml_wind_corrected"`) | A loop over five named candidates per corridor per cycle, sharing one fetched input set | This phase, D-01/D-02 | Collection breadth increases 5x; no change to fetch volume (still 2 live calls/corridor/cycle, not 10) |
| Flat, single-candidate JSON log entry (`method`, `fallback_used`, `model_version`, ... all top-level) | Per-candidate nested fields under each method name, D-06 | This phase, D-06 | Existing single-method readers (`forecast_shadow_healthcheck.py`, `forecast_shadow_render_table.py`) must be checked against the new shape — see Open Risks |
| `ShadowPipeline.predict`'s try/except isolates ONE configured method from its OWN fallback | Five independent `ShadowPipeline` (or equivalent) invocations per cycle, each isolated from the other four (D-07) | This phase | Prevents one candidate's bug from blocking the other four — currently impossible to violate accidentally today only because there's nothing to isolate (one candidate total) |

**Deprecated/outdated:** Nothing — every existing class/function this phase touches is reused, not
replaced. `forecast_shadow_demo.run_once`'s single-method signature becomes either a thin wrapper
called 5x internally by a new orchestrator, or is itself generalized; either way its existing
callers (manual `python backend/forecast_shadow_demo.py <corridor> <method>` invocations, and its
own test file) should keep working for backward-compatible manual single-method testing.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `persistence_24h`'s reader should key off `valid_time` (not `decision_time`) when searching prior entries for the ~24h-ago anchor | Pattern 3, Pitfall 3 | If the planner instead keys off `decision_time`, the anchor could drift relative to the forecast's own valid-time alignment at the twice-daily (not exactly-24h) cadence; this is a design recommendation, not verified against any existing code (no prior implementation of this read-path exists to check against) — flagged for a `checkpoint:human-verify` or explicit plan decision |
| A2 | The GitHub Actions job's 15-minute `timeout-minutes` budget has enough headroom for 5x the per-corridor work (still only 2 live fetches/corridor, same as today, plus 5x in-process compute which is cheap for 2 corridors) | Summary, Architecture Patterns | If wrong (e.g. `reference_ml_refit_24h`'s joblib-loaded MLP inference is unexpectedly slow, or a new live fetch is accidentally added per-candidate against D-02), the scheduled job could start timing out — not measured this session since the new code doesn't exist yet to time |
| A3 | No workflow-file (`shadow_collect.yml`) change is needed for D-10's scheduled-run confirmation — the existing `cat >>`/commit step is format-agnostic to the JSON shape inside each `.jsonl` line | §7 | If the restructured per-candidate JSON shape breaks `forecast_shadow_render_table.py`'s existing field reads (`e.get('method')`, `e.get('ampacity_amps')`, etc., which assume the OLD flat shape), the rendered README.md table would silently show wrong/missing values without the workflow itself failing — this is a real, concrete follow-on change this phase must make, not merely assumed safe |
