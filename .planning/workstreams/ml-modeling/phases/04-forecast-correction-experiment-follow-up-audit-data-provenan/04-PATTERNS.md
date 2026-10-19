# Phase 4: Forecast Correction Follow-up Audit - Pattern Map

**Mapped:** 2026-09-30
**Files analyzed:** 6 (this phase is audit/doc-heavy; RESEARCH.md's own "Recommended Project
Structure" already names the concrete new files, reproduced and pattern-mapped below)
**Analogs found:** 6 / 6 (all analogs are Phase 3's own tracked files, per phase-context guidance)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `backend/forecast_experiment_audit.py` (NEW) | utility / analysis module | transform (batch statistical post-processing) | `backend/forecast_experiment.py` | exact (same author convention: standalone, additive, offline harness) |
| `backend/tests/forecast_experiment_audit_test.py` (NEW) | test | transform (synthetic-data unit tests) | `backend/tests/forecast_experiment_test.py` | exact (same mocking/tmp_path/module-level-assert conventions) |
| Any new `SplitBoundaries` usage for fresh-holdout / calibration-vs-evaluation periods | utility (config/boundary) | batch (chronological partition) | `backend/experiment_splits.py` | exact — reuse directly, do not create a new file |
| `docs/data-science/decisions/forecast_correction_followup_audit.md` (NEW, or amendment) | config/doc (ADR-format record) | request-response N/A — static document | `docs/data-science/decisions/forecast_correction_experiment.md` | exact (same 9-section ADR format, same "git log is the audit trail" discipline) |
| Amendment additions to `docs/data-science/decisions/forecast_correction_experiment.md` | config/doc (append-only amendment) | batch (prose correction, D-04) | same file's own existing Limitations/Verdict sections | exact — additive-only edit pattern |
| D-05 integration-readiness plan doc (new planning artifact, location per Claude's discretion — likely alongside the audit doc or as a phase deliverable) | config/doc (planning) | batch | `docs/data-science/decisions/forecast_correction_experiment.md`'s own "Recommendation" / "Next steps"-style sections, or a sibling `.planning/` document | role-match |

No controller/component/service/model/route/hook/provider/store files are in scope for this phase —
it is offline analysis + documentation only (confirmed by RESEARCH.md's "Architectural
Responsibility Map": no browser/frontend/API/DB tier is touched).

## Pattern Assignments

### `backend/forecast_experiment_audit.py` (utility, transform) — NEW

**Analog:** `backend/forecast_experiment.py` (2075 lines, git-tracked: confirmed via `git ls-files`)

**Module docstring / standalone-harness convention** (lines 1-13):
```python
"""
Ampacity Forecast Experiment Harness -- Anchored Pair Frame + Arm Scoring
(D-01 legacy 1h arm + D-04 PRIMARY 24h arm, Phase 3 experiment)
==========================================================================
Standalone offline entry point -- NOT imported by the runtime pipeline,
mirroring `forecast_training.py`/`anomaly_training.py`'s own convention.
Imports `ampacity_forecast`, `config`, `corridor_discretization`,
`experiment_splits`, `forecast_training` (for `corridor_weakest_link` only --
Plan 03-04, the repository's ONE weakest-link reduction, never a second
copy), `open_meteo_forecast_provider`, `open_meteo_provider`,
`thermal_model`; nothing imports this module.
"""
```
New audit module should open the same way: state plainly it is standalone, additive, imports
`forecast_experiment` (for `paired_bootstrap_margin`, `score_arms`, arm callables) rather than
duplicating any scoring logic, and is never imported by the runtime pipeline.

**Additive-function pattern to copy verbatim in spirit** — `paired_bootstrap_margin` (lines
1278-1374, full function read this session) is the direct template for the new
`paired_block_bootstrap_margin`:
- Same docstring shape: state the statistical claim, name the exact config constants it reuses
  (`config.FORECAST_EXPERIMENT_BOOTSTRAP_RESAMPLES`, `config.FORECAST_EXPERIMENT_BOOTSTRAP_
  CONFIDENCE`, `config.FORECAST_EXPERIMENT_CORRECTION_RANDOM_STATE` — reuse the SAME fixed seed
  constant, do not invent a second one, per RESEARCH.md's explicit note that no second
  bootstrap-specific seed exists in `config.py`).
- Same degenerate-input guard: check `np.ptp(diff) == 0.0` before calling into the statistical
  routine and short-circuit to a point-mass interval — the block-bootstrap version needs an
  analogous guard for a constant block-difference series.
- Same return shape: `{"point": float, "ci_low": float, "ci_high": float,
  "excludes_zero_favorably": bool}` — keep this contract identical so callers (any new pairwise
  comparison code) can treat both bootstrap flavors interchangeably.
- Same `ValueError` shape-mismatch guard at the top, naming both shapes in the message (lines
  1337-1342).

**`score_arms`'s `baseline_name` generalization** (lines 1377-1445, full function read this
session) is the direct template for D-02's pairwise (non-persistence-only) comparisons — it
ALREADY generalizes to any arm as baseline (RESEARCH.md's own State-of-the-Art table confirms
"no new scoring machinery needed, just additional calls with `baseline_name="ml_cooling_
corrected"`"). The new audit module should call `forecast_experiment.score_arms(frame, arms,
baseline_name="ml_cooling_corrected")` directly rather than reimplementing per-arm MAE/RMSE
computation — copy the calling convention, not the function body.

**Error handling / invariant-assertion pattern**: `score_arms` calls `assert_identical_index`
FIRST (line 1412) before scoring anything — any new audit function that consumes multiple arms'
predictions on the same frame should assert index identity up front the same way, rather than
letting a silent length mismatch corrupt a downstream numpy operation.

### `backend/tests/forecast_experiment_audit_test.py` (test, transform) — NEW

**Analog:** `backend/tests/forecast_experiment_test.py` (git-tracked, confirmed via `git ls-files`)

**Header/testing-convention pattern** (lines 1-21):
```python
"""
Tests for backend/forecast_experiment.py (D-01 legacy 1h arm + D-04 PRIMARY
24h arm, Phase 3 Plans 03-01/03-03).

Every test is network-free: monkeypatch `open_meteo_provider.
fetch_open_meteo` and either `open_meteo_forecast_provider.fetch_historical_
forecast` (legacy 1h lead) or `open_meteo_forecast_provider.
fetch_previous_runs` (D-04 primary 24h lead) on the module objects
`forecast_experiment` imports, following the convention
`anomaly_training_test.py`/`forecast_training_test.py` use for mocking a
fetch one layer up. Module-level plain-assert functions, no test classes.
Every test also redirects `config.FORECAST_EXPERIMENT_CACHE_DIR` to a
pytest `tmp_path`, so no test reads or writes the real `data/experiment/`
cache.
"""
```
New test file should state the equivalent network-free guarantee: since D-02/D-03's new code
(block-bootstrap, overrating rate, quantile calibration) needs no network I/O at all (pure numpy/
pandas/sklearn transforms on synthetic or in-memory arrays), the docstring should say so plainly
and confirm no fetch monkeypatching is even needed for this file — a stronger, simpler guarantee
than the module it's modeled on.

**Deterministic-synthetic-data helper pattern** (lines 38-49) — `_synthetic_weather_frame` builds
a fully-populated, deterministic hourly frame with `np.random.default_rng(20260929)` (Phase 3's
own fixed seed) for reproducible synthetic tests. The new test file's synthetic-autocorrelated-
series helper (for block-bootstrap block-length-sensitivity tests) should follow the exact same
shape: a small, deterministic, seeded generator function at module scope, not inline per-test
random calls.

**Module-level plain-assert convention, no test classes** — confirmed both in this file's
docstring and structurally; the new audit test file should follow suit: `def test_block_bootstrap_
*():`, `def test_pairwise_margin_*():`, `def test_overrating_rate_*():`, `def test_quantile_
calibration_split_disjoint():` as flat module-level functions per RESEARCH.md's own Test Map.

### Reused directly (no new file needed): `backend/experiment_splits.py`

**Analog / source to import from, not copy:** `backend/experiment_splits.py` (full file, 168+
lines, git-tracked). Any new disjoint calendar period this phase defines (D-02's fresh
chronological holdout, D-03's calibration-vs-evaluation split) should construct a new
`SplitBoundaries` instance and call `calendar_split`, exactly per this module's own docstring
claim to generalize `anomaly_training.chronological_split` to calendar dates:

**Value-object + validation pattern** (lines 46-71, full class read this session):
```python
class SplitBoundaries:
    def __init__(self, val_start, test_start):
        val_start = _to_utc_timestamp(val_start)
        test_start = _to_utc_timestamp(test_start)
        if not val_start < test_start:
            raise ValueError(
                f"SplitBoundaries: val_start ({val_start}) must be "
                f"strictly before test_start ({test_start})"
            )
        self.val_start = val_start
        self.test_start = test_start
```
Do not hand-roll a new date-boundary class — construct `experiment_splits.SplitBoundaries(...)`
directly, per RESEARCH.md's explicit "Don't Hand-Roll" table entry and Pattern 2.

### `docs/data-science/decisions/forecast_correction_followup_audit.md` (doc) — NEW sibling ADR

**Analog:** `docs/data-science/decisions/forecast_correction_experiment.md` (the frozen record
under audit itself — git-tracked)

**Structure to copy:** the existing 9-section ADR format used by that document (and precedented
further by `docs/data-science/decisions/forecasting_model.md`'s header structure). Use section
headers of the same shape (Context/Data provenance/Expectation/Method/Measured results/Limitations/
Verdict/Recommendation/References or equivalent), but populate them with THIS phase's own new
content (D-01 findings, D-02 methodology + fresh-holdout results, D-03 overrating/quantile
findings, D-05 integration plan) — never copy the frozen document's Expectation/Measured-results
prose verbatim, since those sections describe Phase 3's own experiment, not this audit.

**Citation discipline pattern to copy:** every claim in the frozen document traces to a specific
git-log-referenced plan/task (the "git log is the audit trail" discipline RESEARCH.md's Security
Domain section names explicitly) — the new audit document must do the same: every new finding
cites a specific `file:line` (as this PATTERNS.md itself does) or a specific computation/dataset,
never an unsourced assertion.

### Amendment to `docs/data-science/decisions/forecast_correction_experiment.md` (D-04)

**Pattern:** additive-only append, never in-place rewrite of the Expectation/Measured-results
sections (explicitly forbidden by CONTEXT.md's Phase Boundary). Mirror Phase 3's own Plan 03-06
discipline of stating explicitly, in the new prose, that it is an addition/correction layered on
top of frozen content, not a replacement — the same "additive... byte-identical to before this
[change] existed" framing `paired_bootstrap_margin`'s own docstring uses for code, applied here to
prose.

## Shared Patterns

### Additive-only changes to frozen modules (applies to ALL new code in this phase)
**Source:** `backend/forecast_experiment.py:1389-1391` (`score_arms`'s `baseline_name` parameter
docstring: "every pre-existing caller's behavior is byte-identical to before this parameter
existed")
**Apply to:** `forecast_experiment_audit.py` (new functions only, never edit `score_arms`,
`paired_bootstrap_margin`, `corridor_experiment_report`, or any arm factory in
`forecast_experiment.py` itself), and the D-04 doc amendment (append, never rewrite the frozen
Expectation/Measured-results sections).

### Fixed-seed reproducibility
**Source:** `backend/forecast_experiment.py:1303-1307` (`config.FORECAST_EXPERIMENT_CORRECTION_
RANDOM_STATE = 20260929`, reused — not duplicated — across every stochastic routine in the module)
**Apply to:** any new stochastic routine (block-bootstrap resampling, `GradientBoostingRegressor(
loss="quantile", random_state=...)`) — reuse this existing constant from `config.py` rather than
inventing a second seed constant, exactly as `paired_bootstrap_margin` itself does.

### Degenerate-input guards before delegating to a statistical library call
**Source:** `backend/forecast_experiment.py:1347-1358` (`np.ptp(diff) == 0.0` short-circuit before
calling `scipy.stats.bootstrap`, because `BCa` returns `NaN` on constant data)
**Apply to:** `paired_block_bootstrap_margin` and any new quantile-calibration code — check for
degenerate/constant input before delegating to `scipy.stats.bootstrap` or
`sklearn.metrics.mean_pinball_loss` and handle it explicitly rather than passing NaN downstream.

### Chronological-boundary reuse (never hand-roll a splitter)
**Source:** `backend/experiment_splits.py:46-90` (`SplitBoundaries`/`calendar_split`)
**Apply to:** D-02's fresh chronological holdout definition and D-03's calibration-vs-evaluation
disjoint split — both must be expressed as `SplitBoundaries` instances with explicit dates,
verified non-overlapping with Phase 3's frozen `train`/`val`/`test` boundaries.

### Network-free, offline-only test convention
**Source:** `backend/tests/forecast_experiment_test.py:1-16` (monkeypatch fetch functions on
imported module objects; redirect `config.FORECAST_EXPERIMENT_CACHE_DIR` to `tmp_path`)
**Apply to:** `forecast_experiment_audit_test.py` — since D-02/D-03's new statistical code needs no
network I/O at all, this is an even simpler bar to clear than the analog file, but the same
"assert no real cache/network path is touched" discipline should be stated in the new file's
docstring.

## No Analog Found

None — every file this phase creates/modifies has a strong, git-tracked analog in Phase 3's own
artifacts, per the phase-context's explicit steer to favor Phase 3's files.

## Metadata

**Analog search scope:** `backend/*.py`, `backend/tests/*.py`, `docs/data-science/decisions/*.md`
(all Phase 3-authored or Phase-3-adjacent files named explicitly in CONTEXT.md's References section
and RESEARCH.md's Sources section — no broader repo-wide glob search was needed since RESEARCH.md
had already identified and read every relevant file this session).
**Files scanned:** 6 analog files fully or partially read this session (`forecast_experiment.py`
full read of two target functions + module docstring, `experiment_splits.py` first ~90 lines,
`forecast_experiment_test.py` first ~60 lines, `forecast_leadtime_calibration.py` function index,
`forecast_correction_experiment.md` and `forecasting_model.md` referenced from RESEARCH.md's own
prior full reads).
**Tracked-source gate:** all six analog paths confirmed via `git ls-files -- <path>` (non-empty
output for each) — no gitignored mirror paths used.
**Pattern extraction date:** 2026-09-30
