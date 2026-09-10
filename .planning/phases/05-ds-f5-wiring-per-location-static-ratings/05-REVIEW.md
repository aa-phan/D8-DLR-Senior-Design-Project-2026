---
phase: 05-ds-f5-wiring-per-location-static-ratings
reviewed: 2026-09-10T05:01:45Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - backend/dlr_pipeline.py
  - backend/ercot_dlr_merger.py
  - backend/tests/dlr_pipeline_test.py
  - backend/tests/ercot_dlr_merger_test.py
  - README.md
findings:
  critical: 1
  warning: 1
  info: 3
  total: 5
status: fixed
---

# Phase 05: Code Review Report

**Reviewed:** 2026-09-10T05:01:45Z
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Reviewed the DS-F5 wiring changes that replaced the `static_rating` parameter with a
`city: str = None` parameter on `run_pipeline`, `plot_dlr_summary`, and
`process_dlr_to_hourly`, resolving the rating via
`config.STATIC_RATINGS.get(city, config.DEFAULT_STATIC_RATING)`. Verified the full
suite (`.venv/bin/python -m pytest -q`) reports 155 passed, 0 failed, matching the
SUMMARY's claim. The signature changes, the `.get()`-with-default (never
bracket-indexed) resolution, the module-top `import config` fix in
`dlr_pipeline.py`, the append-only diff to `ercot_dlr_merger_test.py`, and the
README table update all check out as described.

The one significant defect found is a downstream consequence of the wiring change
that the phase's test suite does not cover: `ercot_dlr_merger.py`'s
`plot_holistic_grid_view` — a function this phase did not touch, but whose input
(`process_dlr_to_hourly`'s output) this phase changed — still hardcodes a
"900 A / ~510 MW" label on its static-limit reference line. Since the file's own
`__main__` block now calls `process_dlr_to_hourly(DLR_FILE, city="AUSTIN")`, the
actual `static_capacity_mw` value plotted is ~1078.6 MW (Austin's 1900 A rating),
so every plot this entry point generates now carries a legend that mislabels the
line it draws. This is exactly the kind of per-location drift DS-F5 exists to
close, just one function further downstream than the plan's stated scope.

## Critical Issues

### CR-01: Stale hardcoded static-limit label no longer matches the per-city rating it plots — FIXED (commit `ff7d077`)

**File:** `backend/ercot_dlr_merger.py:100`
**Issue:** `plot_holistic_grid_view` draws its static-limit reference line at the
real, per-city-resolved value (`merged_df["static_capacity_mw"].iloc[0]`, correct),
but labels it with a hardcoded literal string:

```python
ax1.axhline(merged_df["static_capacity_mw"].iloc[0], color="red", ls="--", lw=2,
            label="Static Limit (900 A / ~510 MW)")
```

Before this phase, `process_dlr_to_hourly` always produced 900 A / ~510 MW, so the
label was accurate by construction. This phase's own `__main__` block (line 145)
now calls `process_dlr_to_hourly(DLR_FILE, city="AUSTIN")`, which resolves Austin's
1900 A rating (~1078.6 MW) instead. The line is now drawn at ~1078.6 MW but its
legend still reads "900 A / ~510 MW" — a false, hardcoded caption on a plot whose
entire purpose is to communicate a transmission line's safety rating. Nothing in
this phase's test coverage catches it because `plot_holistic_grid_view` has no
tests and is only exercised via this file's own `__main__` block (guarded by an
`os.path.exists(DLR_FILE)` check, so it silently never runs in this environment
either — see the plan's own `<human-check>`, whose input CSV was confirmed absent).
**Fix:** Build the label from the same resolved value the axhline uses, so it can
never drift again — mirroring the pattern `plot_dlr_summary` already uses correctly
(`f"Static Rating ({static_rating:.0f} A)"`):
```python
ax1.axhline(
    merged_df["static_capacity_mw"].iloc[0], color="red", ls="--", lw=2,
    label=f"Static Limit (~{merged_df['static_capacity_mw'].iloc[0]:.0f} MW)",
)
```

## Warnings

### WR-01: `city: str = None` is not `Optional[str] = None` on all three resolvers

**File:** `backend/dlr_pipeline.py:188`, `backend/dlr_pipeline.py:332`, `backend/ercot_dlr_merger.py:25`
**Issue:** All three new/changed signatures annotate `city` as `str` but default it
to `None`:
```python
def run_pipeline(..., city: str = None, ...): ...
def plot_dlr_summary(df, city: str = None, ...): ...
def process_dlr_to_hourly(dlr_csv_path: str, city: str = None) -> pd.DataFrame: ...
```
This is a real type mismatch (`None` is not a `str`), not just a style nit —
`dlr_pipeline.py` already imports `typing.Optional` and uses it correctly elsewhere
(`get_wtm_stations(bbox: Optional[tuple] = None)`), so this phase introduces an
inconsistent, incorrect annotation right next to a correct example of the same
pattern in the same file. Any type checker (mypy, pyright) run over this codebase
would flag all three.
**Fix:**
```python
def run_pipeline(..., city: Optional[str] = None, ...): ...
def plot_dlr_summary(df, city: Optional[str] = None, ...): ...
def process_dlr_to_hourly(dlr_csv_path: str, city: Optional[str] = None) -> pd.DataFrame: ...
```
(`ercot_dlr_merger.py` will need `from typing import Optional` added — it currently
has no `typing` import.)

## Info

### IN-01: Rating-resolution one-liner duplicated three times across two files

**File:** `backend/dlr_pipeline.py:237`, `backend/dlr_pipeline.py:349`, `backend/ercot_dlr_merger.py:58`
**Issue:** `config.STATIC_RATINGS.get(city, config.DEFAULT_STATIC_RATING)` is
copy-pasted verbatim in three call sites across two modules (by explicit plan
design, to keep the two files from diverging in how they resolve a rating — see
05-01-PLAN.md's Task 2 `<read_first>`). That intent is honored today, but nothing
enforces it going forward: a future edit to add case-insensitivity, logging, or an
alternate fallback strategy to one call site has no structural pressure to also
land in the other two.
**Fix:** Consider a small `config.resolve_static_rating(city) -> float` helper
(or similar) as the single place this expression lives, called from all three
sites. Not required now — the current tests (`test_every_configured_city_resolves_its_own_rating`,
etc.) would still catch a future divergence — but it removes the "keep three
copies in sync by discipline alone" burden.

### IN-02: City lookup is case-sensitive with no documented caveat

**File:** `backend/dlr_pipeline.py:188-201`, `backend/dlr_pipeline.py:332-345`, `backend/ercot_dlr_merger.py:25-34`
**Issue:** `config.STATIC_RATINGS` keys are uppercase-only (`"AUSTIN"`,
`"CORPUS_CHRISTI"`, `"MIDLAND"`, `"EL_PASO"`). A caller passing `city="Austin"` or
`city="austin"` silently falls back to `config.DEFAULT_STATIC_RATING` — indistinguishable,
by design (D-02), from a genuinely unknown city or a typo. This is consistent with
the phase's stated silent-fallback design and is fail-safe in direction (understates
rather than overstates capacity), so it is not a defect, but none of the three
docstrings mention that the match is case-sensitive, and no test exercises a
differently-cased valid city name to demonstrate the fallback (all tests use exact
`"AUSTIN"` or a clearly-invalid `"NOT_A_CITY"`).
**Fix:** Add one sentence to each of the three docstrings noting that `city` must
match a `config.STATIC_RATINGS` key exactly (case-sensitive), or add a
`test_lowercase_city_falls_back_silently`-style test if case-insensitivity is
ever expected to be supported.

### IN-03: Pre-existing unused import surfaced during review

**File:** `backend/dlr_pipeline.py:27`
**Issue:** `from typing import Union` — `Union` is not referenced anywhere in the
file. This predates this phase (not part of the diff) but was encountered while
reviewing the full file content.
**Fix:** Remove the unused import, or fold it into the existing `from typing import Optional` line above it (`from typing import Optional, Union` if `Union` will be needed shortly, otherwise drop it).

---

_Reviewed: 2026-09-10T05:01:45Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
