---
phase: 02-anomaly-detection-model
reviewed: 2026-09-26T23:35:28Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - backend/anomaly_detector.py
  - backend/anomaly_training.py
  - backend/config.py
  - backend/ercot_data_retriever.py
  - backend/tests/anomaly_detector_test.py
  - backend/tests/anomaly_training_test.py
  - backend/tests/ercot_data_retriever_test.py
  - docs/data-science/decisions/anomaly_detection_model.md
  - docs/data-science/specs/C10-anomaly-detection.md
findings:
  critical: 1
  warning: 5
  info: 4
  total: 10
status: issues_found
---

# Phase 02-anomaly-detection-model: Code Review Report

**Reviewed:** 2026-09-26T23:35:28Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

This phase adds a third, additive, OR-combined anomaly-detection branch (`_check_against_model`)
to `AnomalyDetector.check`, an offline trainer/bake-off/measurement module
(`anomaly_training.py`), a D-02 ERCOT load characterization, and a validation record. The core
safety invariants the phase's own plans emphasize most (no exception handler in
`anomaly_detector.py`, the model can only add a trip and never suppress one, a missing/non-finite
raw field raises rather than substituting, `DLRSafetyMonitor.py` untouched) are genuinely upheld
by the code as written and are exercised by real, non-trivial tests — this is solid work on the
axis the plans were most worried about.

The problems found here are concentrated in the *offline* trainer/measurement machinery and one
pre-existing helper it now newly and repeatedly exercises: a report-writing bug that silently
discards previously-recorded validation evidence for corridors not included in a given
`--bakeoff`/`--validate` invocation (directly contradicting the phase's own stated T-02-09
mitigation), a latent test-coverage gap in `chronological_split`'s disjointness guarantee for the
real two-city pooled data shape, a confirmed date-boundary bug in `ercot_data_retriever.py`'s
window mask (visible in the phase's own generated evidence), a duplicated RNG seed that makes the
two injection categories sample identical rows, and a couple of smaller robustness/quality gaps.
None of these touch the live `check()` safety path, and none contradict the fail-safe contract —
they are training-time/evidentiary defects, which is why none is flagged as jeopardizing runtime
safety directly, but the report-overwrite bug specifically undermines the honesty/completeness
guarantee this phase's own threat register (T-02-09) claims to provide.

## Critical Issues

### CR-01: `--bakeoff`/`--validate` silently discard previously-recorded evidence for corridors not included in the current run

**File:** `backend/anomaly_training.py:591,649-651` (`_run_validate`) and `backend/anomaly_training.py:878,947-953` (`_run_bakeoff`)

**Issue:** Both `_run_validate` and `_run_bakeoff` build their report as a **fresh, empty dict**
(`reports = {}`) scoped only to the corridors passed to that invocation, then unconditionally
`json.dump` it over `config.ANOMALY_ML_VALIDATION_REPORT_NAME` — they never read the existing file
first and merge into it. `main()`'s `--corridor` flag lets a caller select a single corridor
(`corridors = [args.corridor] if args.corridor else sorted(config.CORRIDOR_ENDPOINTS)`), so:

```
.venv/bin/python3 backend/anomaly_training.py --bakeoff --years 1                       # writes both corridors
.venv/bin/python3 backend/anomaly_training.py --bakeoff --years 1 --corridor MIDLAND_EL_PASO   # OVERWRITES the file with ONLY MIDLAND_EL_PASO's entry
```

The second command permanently deletes `AUSTIN_CORPUS_CHRISTI`'s entire measurement history
(every candidate x contamination measurement, the selected winner, the ceiling-met flag) from
`anomaly_validation_report.json` — with no warning, no error, and no diff visible to the operator
beyond the file silently shrinking. This directly contradicts the phase's own T-02-09 threat
register entry, which states as the *mitigation* for exactly this risk: "Every attempted
(candidate, contamination) pair's numbers are written to the report, including the losers',
alongside the assembled row count and the window span, so **a shortened run or a dropped arm is
visible in the evidence rather than hidden behind a single score**." A single-corridor rerun does
not make itself visible in the evidence — it erases the other corridor's evidence outright. The
persisted `.joblib` model artifacts themselves are unaffected (this is report-data loss, not
live-model loss), but `docs/data-science/decisions/anomaly_detection_model.md` is a direct
transcription of this JSON file, so a well-intentioned single-corridor re-run (e.g., to refresh one
corridor's model after a data update) done between validation-record updates would silently corrupt
the source-of-truth evidence the tracked record depends on.

**Fix:** Load the existing report (if present) before building `reports`, and merge only the
selected corridors' new entries into it, e.g.:

```python
report_path = os.path.join(config.ANOMALY_ML_MODEL_DIR, config.ANOMALY_ML_VALIDATION_REPORT_NAME)
reports = {}
if os.path.exists(report_path):
    with open(report_path) as fh:
        reports = json.load(fh)
# ... populate reports[corridor] = ... only for the corridors actually processed this run ...
with open(report_path, "w") as fh:
    json.dump(reports, fh, indent=2)
```

## Warnings

### WR-01: `chronological_split`'s disjoint-timestamp guarantee is untested (and can be violated) for the real pooled two-city data shape

**File:** `backend/anomaly_training.py:249-293`; test gap in `backend/tests/anomaly_training_test.py:219-232`

**Issue:** `chronological_split` sorts only by `datetime_utc` (`sorted_frame = frame.sort_values("datetime_utc")...`) and splits at a raw row-index boundary. The real production frame from
`corridor_observation_frame` has (usually) **two rows per timestamp** — one per endpoint city —
sorted by `["datetime_utc", "city"]`. If the split index happens to fall between two rows sharing
the exact same `datetime_utc` (which occurs whenever the total pooled+surviving row count has the
"wrong" parity relative to the holdout fraction — e.g. after asymmetric per-city row drops from the
G3/null filter), one city's reading for that hour lands in `fit` and the other city's reading for
the *same hour* lands in `holdout`. The docstring and T-02-08 both claim the holdout is "strictly
later than anything the estimator was fitted on," and the acceptance test
`test_chronological_split_returns_nonoverlapping_time_ordered_slices` asserts
`set(fit["datetime_utc"]).isdisjoint(set(holdout["datetime_utc"]))` — but that test only exercises
`_synthetic_observation_frame`, which has one distinct timestamp per row by construction, so it can
never trigger or catch this straddle. Whenever it does occur, the false-positive measurement is
scored on a row that is essentially simultaneous with (and highly correlated to) a row the
estimator trained on, mildly understating the true false-positive rate for the affected corridor —
the exact overstatement-of-generalization risk T-02-08 exists to prevent.

**Fix:** Sort and split on a duplicate-timestamp-aware boundary, e.g. compute the split index from
distinct `datetime_utc` values and assign every row sharing a boundary timestamp to the same side,
or add `"city"` as a stable secondary sort key and adjust the split index to the nearest timestamp
boundary rather than a raw row count. Add a test using a frame with two rows per timestamp (mirroring the real pooled shape) to actually exercise the disjointness guarantee.

### WR-02: `ercot_data_retriever.pull_ercot_data`'s window mask silently drops ~23 hours from the end of every requested window — confirmed by this phase's own generated evidence

**File:** `backend/ercot_data_retriever.py:85`

**Issue:** `mask = (df[time_col] >= f"{start}T00:00:00Z") & (df[time_col] <= f"{end}T00:00:00Z")`.
When `end` is a plain date string (as it always is from `characterize_load`, e.g.
`"2025-12-31"`), the upper bound is `"2025-12-31T00:00:00Z"` — midnight **at the start** of the
final day — so every hourly reading from `01:00` through `23:00` on the final day is excluded. This
line predates this phase (it is unchanged from the pre-phase implementation per `git diff
6f07f8d cb8fc75`), but this phase's new `characterize_load` caller now exercises it on every
`--characterize-load` run with a full-year window, and the resulting evidence directly confirms the
bug: `docs/data-science/decisions/anomaly_detection_model.md`'s Load characterization table reports
a retrieved window of `2025-01-01T06:00:00+00:00 → 2025-12-31T00:00:00+00:00` with only 8,731 of a
possible ~8,760 hourly rows — the 6-hour gap at the start is the expected UTC/Central-time offset
for a calendar-year boundary, but the window ending at `Dec 31T00:00:00` instead of
`Dec 31T23:00:00` (or later) is this mask silently truncating the entire final day. Because
`characterize_load` correctly reports whatever frame *actually came back* (T-02-12's own
requirement), this bug does not misrepresent the evidence, but it does mean "one complete calendar
year" is not actually what gets characterized, and the report gives no indication that the shortfall is caused by an off-by-one boundary rather than a data-availability gap.

**Fix:** Use a half-open interval on the end boundary, e.g. `df[time_col] < (pd.Timestamp(end) + pd.Timedelta(days=1)).tz_localize("UTC")`, or `<= f"{end}T23:59:59Z"`, so the full final calendar day is retained.

### WR-03: Both injection categories in `validate_candidate` sample the identical set of holdout rows due to a duplicated RNG seed

**File:** `backend/anomaly_training.py:531-538`

**Issue:**

```python
seed_rng = np.random.default_rng(config.ANOMALY_ML_RANDOM_SEED)
injected_out, mask_out = inject_anomalies(holdout_frame, "out_of_range", rng=seed_rng)
seed_rng_2 = np.random.default_rng(config.ANOMALY_ML_RANDOM_SEED)
injected_implausible, mask_implausible = inject_anomalies(
    holdout_frame, "in_range_implausible", rng=seed_rng_2, fit_frame=fit_frame,
)
```

Both `seed_rng` and `seed_rng_2` are freshly constructed with the **exact same** seed constant, and
`inject_anomalies`'s very first RNG operation for both categories is
`rng.choice(len(frame), size=n_inject, replace=False)` against the same `len(holdout_frame)` and the
same default rate — so the two calls select the **identical set of row positions** every time. The
`_2` suffix on the second generator's variable name suggests independent sampling was intended.
Because `recall_pooled`/`baseline_recall_pooled` concatenate both categories' flags, the "pooled"
recall figure is effectively measured over one set of holdout rows corrupted two different ways
rather than two independently-sampled subsets of the holdout, understating how broadly the recall
measurement actually samples the holdout set — a methodological weakening of exactly the evidence
this phase's validation record cites as ANOM-02's discharge.

**Fix:** Seed the second generator differently, e.g. `np.random.default_rng(config.ANOMALY_ML_RANDOM_SEED + 1)`, or derive both from a single `np.random.default_rng(config.ANOMALY_ML_RANDOM_SEED).spawn(2)` so the two categories are independently (but still reproducibly) sampled.

### WR-04: `_check_against_model`'s missing/non-finite guard produces an uninformative, contract-violating error on a non-numeric raw value

**File:** `backend/anomaly_detector.py:426-434`

**Issue:** The guard is:

```python
missing = [
    key for key in config.ANOMALY_ML_RAW_DATA_KEYS
    if raw_data.get(key) is None or not math.isfinite(float(raw_data.get(key)))
]
```

If `raw_data[key]` is present but not numeric-castable (e.g. a string like `"bad"`, or a list), `float(raw_data.get(key))` raises **inside the list comprehension itself**, before the intended
`ValueError` (which names the offending field list) is ever constructed. The caller still sees a
`ValueError` (satisfying "propagates uncaught" for the fail-safe boundary), but it is Python's
generic `could not convert string to float: 'bad'` message rather than the documented
`_check_against_model: raw_data is missing or has a non-finite value for required field(s) [...]`
contract this method's own docstring promises ("raises `ValueError` naming that list and this
method"). No test in `anomaly_detector_test.py` covers a non-numeric (as opposed to absent/`None`/`nan`) malformed value, so this gap is untested as well as unhandled.

**Fix:** Wrap the per-key coercion so a non-numeric value is treated the same as a missing one, e.g.:

```python
def _is_bad(key):
    value = raw_data.get(key)
    if value is None:
        return True
    try:
        return not math.isfinite(float(value))
    except (TypeError, ValueError):
        return True

missing = [key for key in config.ANOMALY_ML_RAW_DATA_KEYS if _is_bad(key)]
```

### WR-05: `_MODEL_CACHE` is never invalidated after `persist_corridor_model` writes a new artifact

**File:** `backend/anomaly_detector.py:81,97-112`; `backend/anomaly_training.py:210-241` (`persist_corridor_model`)

**Issue:** `_load_corridor_model` caches the deserialized estimator in the module-level
`_MODEL_CACHE` dict keyed by corridor and never evicts an entry. `persist_corridor_model` (in the
separate `anomaly_training.py` module) writes a new `.joblib` file but has no way to — and makes no
attempt to — invalidate a stale cache entry for that corridor. Within a single long-running Python
process that both loads (via `AnomalyDetector.for_corridor`) and later retrains/persists a model for
the same corridor, `for_corridor` would continue to serve the old cached estimator until process
restart. This is implicitly acknowledged by the plan's own bake-off verification script, which has
to manually call `ad._MODEL_CACHE.clear()` before asserting freshness — i.e., the codebase already
knows this staleness exists and works around it in tests/verify scripts rather than in the loader
itself. In the intended deployment shape (training and serving are separate process invocations)
this is not exercised, but it is a real footgun for any future use of `anomaly_training` functions
from within a long-lived server process (e.g. an admin "retrain now" endpoint).

**Fix:** Have `persist_corridor_model` (or a small wrapper) evict `anomaly_detector._MODEL_CACHE.pop(corridor, None)` after a successful write, or expose a public `anomaly_detector.invalidate_model_cache(corridor)` helper for callers that train and serve in the same process.

## Info

### IN-01: `select_winner` applies an undocumented secondary tie-break (contamination value) not stated in the plan's selection rule

**File:** `backend/anomaly_training.py:829,852`

Both the "eligible" branch's further-tie path and the "no eligible pair" fallback sort by
`(m["order"], m["contamination"])`, but the plan's stated rule only specifies a tie-break by
`recall_pooled` → `false_positive_rate` → `CANDIDATE_ESTIMATORS` insertion order. Since `order` is
identical for two grid points of the *same* candidate, the extra `contamination` sort key silently
picks the lowest contamination among same-candidate ties — harmless and deterministic, but
undocumented behavior beyond what the plan's `<objective>` states verbatim.

### IN-02: CLI flags `--characterize-load`, `--bakeoff`, `--validate` are not mutually exclusive and silently prioritize one over the others

**File:** `backend/anomaly_training.py:1170-1184`

If a caller passes more than one of `--characterize-load`/`--bakeoff`/`--validate` in one
invocation, `main()` checks them in a fixed `if`/`elif`-like sequence and silently runs only the
first one that matches, ignoring the rest with no warning. Using `argparse`'s
`add_mutually_exclusive_group(required=False)` (with a clear error on conflicting flags) would
surface an operator's likely mistake instead of quietly discarding part of their intent.

### IN-03: Generated JSON reports can serialize a non-standard `NaN` token if a correlation or rate is undefined

**File:** `backend/anomaly_training.py` (`characterize_load`'s `correlations` dict; `_run_validate`/`_run_bakeoff`/`_run_characterize_load`'s `json.dump` calls)

`pandas.Series.corr()` returns `NaN` for a zero-variance column (e.g. an unusually short or
degenerate join), and Python's `json.dump` serializes `float('nan')` as the literal `NaN` token by
default (`allow_nan=True`), which is not valid per strict JSON (RFC 8259) and would break a
downstream consumer using a strict JSON parser (e.g. `JSON.parse` in JavaScript). No current
consumer of these reports is known to require strict JSON, so this is a latent robustness gap
rather than an active break, but worth guarding (e.g. serialize as `null` explicitly) given these files are meant to be machine-readable evidence for future tooling.

### IN-04: `characterize_load` groups a CSV-round-tripped `datetime_utc` column while it is still a string, then converts afterward

**File:** `backend/anomaly_training.py:1042-1052`

`obs_frame = pd.read_csv(obs_path)` does not parse `datetime_utc` as a datetime, so
`obs_frame.groupby("datetime_utc", ...)` groups on the raw string representation written by the
earlier `frame.to_csv(...)` call, and only the *already-collapsed* result is converted via
`pd.to_datetime(..., utc=True)` afterward. This works today because the string formatting is
consistent between the two endpoint cities' rows (same source, same code path), but it is fragile:
any future change to how `datetime_utc` is serialized (e.g. a differing timezone suffix or
precision between rows) would silently under-collapse the grouping rather than raising. Parsing the
datetime column immediately after reading the CSV (`pd.read_csv(obs_path, parse_dates=["datetime_utc"])`) would remove this dependency on string-formatting consistency.

---

_Reviewed: 2026-09-26T23:35:28Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
