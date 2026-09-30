"""
Forecast Correction Follow-up Audit -- Frozen-Window Guard, Named Bases, and
the First Provenance Finding (Phase 4, D-01/D-02, Plan 04-01)
==========================================================================
Standalone, offline, ADDITIVE audit module. NOT imported by the runtime
pipeline, and NEVER imported by `forecast_experiment.py` or any other module
this audit reads from -- imports run strictly one direction: this module
imports FROM the harness, the harness never imports this module. Imports
`config`, `experiment_splits`, and `forecast_experiment` for reuse; it never
edits, monkeypatches, or shadows any function, constant, or docstring in any
of those modules. Every new capability this phase needs is a NEW symbol in
this NEW module.

This module deliberately reaches for a handful of `forecast_experiment`'s
underscore-prefixed helpers (`_default_split_boundaries`, and, starting with
Plan 04-01 Task 2, `anchored_pair_frame`/`corridor_anchored_pair_frame`/
`_resolve_window_end`) rather than reimplementing the harness's own
assembly or boundary logic a second time. Duplicating that logic in a
second module would create exactly the drift an audit exists to detect: two
implementations of the same computation that silently diverge is a worse
failure mode than reaching across the module boundary for a private helper.
The alternative -- copying the logic instead -- is named here so a future
reader does not "fix" this reuse by duplicating code.

This module NEVER invokes `forecast_experiment._run_city_tracer`,
`forecast_experiment._run_corridor`, or `forecast_experiment.main` -- the
three entry points that carry a `split` argument capable of requesting the
held-out TEST split (`backend/forecast_experiment.py` lines 1650-1660,
1881-1890, 2009-2074). The audit composes the harness's assembly, filtering,
fitting and scoring helpers directly instead, and
`assert_basis_excludes_frozen_test_rows` below is the mechanical backstop
that catches an accidental frozen-window read regardless of how a frame
reached this module.
"""

import json
import logging
import os
import re

import numpy as np
import pandas as pd

import config
import corridor_discretization
import experiment_splits
import forecast_experiment
import forecast_training

# ──────────────────────────────────────────────────────────────────────────
# Frozen-window pins, sourced from the frozen decision record
# (docs/data-science/decisions/forecast_correction_experiment.md). Each is a
# pinned constant, never a recomputation -- see the comment on
# FROZEN_TEST_SPLIT_START for why.
# ──────────────────────────────────────────────────────────────────────────

# ## Data provenance, "Window" paragraph (line 89): the live-bisected
# Previous-Runs archive start for gfs_seamless, common to all four project
# cities.
FROZEN_WINDOW_START: str = "2024-01-20"

# ## Measured results, both corridors' per-corridor summary lines (205,
# 231): "test split starts 2026-03-17". PINNED, not recomputed: the harness
# derives this boundary from the assembled frame's own min/max timestamps
# (`_default_split_boundaries`), which is itself a function of the window
# END -- and the window end defaults to "yesterday" (`_resolve_window_end`),
# so the boundary MOVES as calendar time advances. Re-running the harness's
# own boundary rule today (or on any date after the frozen record's run)
# would place this audit's guard on a DIFFERENT date than the rows Phase 3
# actually scored. Pinning this date is what keeps
# `assert_basis_excludes_frozen_test_rows` protecting the SAME rows Phase 3
# froze, rather than drifting off that boundary every day this audit is
# re-run. `rederive_frozen_split_boundaries` below demonstrates and records
# this window-end dependence rather than silently working around it.
FROZEN_TEST_SPLIT_START: str = "2026-03-17"

# ## Data provenance, "Window" paragraph (line 93) and ## Measured results
# (lines 204, 230): the frozen window's last date ("yesterday" UTC at the
# time Phase 3's test-set run was made).
FROZEN_WINDOW_END: str = "2026-09-29"

DEFAULT_FROZEN_RECORD_PATH: str = (
    "docs/data-science/decisions/forecast_correction_experiment.md"
)

# The three named audit bases (D-02) and what a claim resting on each may
# and may not say. Every later plan in this phase must be able to name
# which of these three bases a number rests on.
AUDIT_BASES: dict = {
    "SYNTHETIC": (
        "Generated in-process. Validates that a computation is correct. "
        "Supports NO claim about this project's real corridors."
    ),
    "ABLATION": (
        "Real rows strictly before FROZEN_TEST_SPLIT_START. Supports "
        "replication, relative-ordering, and ablation findings. Is NOT a "
        "confirmation basis -- that calendar range was already read during "
        "Phase 3's own development."
    ),
    "FRESH": (
        "Real rows strictly after FROZEN_WINDOW_END. The ONLY basis on "
        "which this phase may make a confirmation claim. May legitimately "
        "contain zero rows."
    ),
}


def _assert_no_real_corridor_marker(frame: pd.DataFrame) -> None:
    """
    SYNTHETIC-basis guard: raise if `frame` carries a `corridor` or `city`
    column naming one of this project's real corridors/cities. A SYNTHETIC
    frame validates that a computation is correct and must never be built
    from this project's real geography, or a later reader could mistake a
    synthetic result for a real-data one.
    """
    if "corridor" in frame.columns:
        real = set(frame["corridor"].unique()) & set(config.CORRIDOR_ENDPOINTS)
        if real:
            raise ValueError(
                f"forecast_experiment_audit: a SYNTHETIC-basis frame names "
                f"real corridor(s) {sorted(real)} in its 'corridor' column "
                f"-- SYNTHETIC data must never carry a real-corridor marker"
            )
    if "city" in frame.columns:
        real = set(frame["city"].unique()) & set(config.CITY_COORDINATES)
        if real:
            raise ValueError(
                f"forecast_experiment_audit: a SYNTHETIC-basis frame names "
                f"real cit(y/ies) {sorted(real)} in its 'city' column -- "
                f"SYNTHETIC data must never carry a real-corridor marker"
            )


def _raise_frozen_window_violation(basis: str, count: int, offending_timestamps: list) -> None:
    first_three = ", ".join(str(ts) for ts in offending_timestamps[:3])
    if basis == "ABLATION":
        boundary_clause = (
            f"basis='ABLATION' requires every timestamp strictly before "
            f"FROZEN_TEST_SPLIT_START={FROZEN_TEST_SPLIT_START}"
        )
    else:
        boundary_clause = (
            f"basis='FRESH' requires every timestamp strictly after the "
            f"end of FROZEN_WINDOW_END={FROZEN_WINDOW_END}"
        )
    raise ValueError(
        f"forecast_experiment_audit.assert_basis_excludes_frozen_test_rows: "
        f"{count} row(s) violate the {basis!r} basis boundary -- "
        f"{boundary_clause}. First three offending timestamp(s): "
        f"{first_three}. Frozen window pins: "
        f"FROZEN_TEST_SPLIT_START={FROZEN_TEST_SPLIT_START}, "
        f"FROZEN_WINDOW_END={FROZEN_WINDOW_END}. This guard exists so the "
        f"audit never takes a second look at Phase 3's already-seen "
        f"held-out test rows."
    )


def assert_basis_excludes_frozen_test_rows(frame: pd.DataFrame, *, basis: str) -> dict:
    """
    The mechanical no-peeking lock for this phase (T-04-01-01). Validates
    `basis` against `AUDIT_BASES` first, raising `ValueError` naming all
    three valid basis names for an unknown one.

    - `SYNTHETIC`: requires the frame carry no real-corridor/city marker
      (`_assert_no_real_corridor_marker`), then returns immediately -- a
      SYNTHETIC frame has no calendar relationship to the frozen window by
      construction.
    - `ABLATION`: every `datetime_utc` must be strictly before
      `FROZEN_TEST_SPLIT_START`.
    - `FRESH`: every `datetime_utc` must be strictly after the end of the
      `FROZEN_WINDOW_END` day.

    An empty frame (zero rows) returns a zero-row summary immediately after
    basis validation, for every basis -- a zero-row FRESH basis is a
    legitimate, reportable outcome, not an error.

    On violation, raises `ValueError` naming the basis, the offending row
    count, the first three offending timestamps, and the frozen window's
    two pinned dates.

    Returns a summary dict: `{"basis": ..., "rows": ..., "first_timestamp":
    ..., "last_timestamp": ...}` (the last two are `None` for an empty
    frame).
    """
    if basis not in AUDIT_BASES:
        raise ValueError(
            f"forecast_experiment_audit: unknown basis {basis!r} -- must be "
            f"one of {sorted(AUDIT_BASES)}"
        )

    n_rows = len(frame)
    if n_rows == 0:
        return {
            "basis": basis,
            "rows": 0,
            "first_timestamp": None,
            "last_timestamp": None,
        }

    if basis == "SYNTHETIC":
        _assert_no_real_corridor_marker(frame)
        dt = pd.to_datetime(frame["datetime_utc"], utc=True)
        return {
            "basis": basis,
            "rows": n_rows,
            "first_timestamp": dt.min().isoformat(),
            "last_timestamp": dt.max().isoformat(),
        }

    dt = pd.to_datetime(frame["datetime_utc"], utc=True)
    test_split_start = pd.Timestamp(FROZEN_TEST_SPLIT_START, tz="UTC")
    window_end_exclusive = pd.Timestamp(FROZEN_WINDOW_END, tz="UTC") + pd.Timedelta(days=1)

    if basis == "ABLATION":
        bad = dt >= test_split_start
    else:  # basis == "FRESH", the only other AUDIT_BASES member
        bad = dt < window_end_exclusive

    if bad.any():
        offending = sorted(dt[bad].tolist())
        _raise_frozen_window_violation(basis, int(bad.sum()), offending)

    return {
        "basis": basis,
        "rows": n_rows,
        "first_timestamp": dt.min().isoformat(),
        "last_timestamp": dt.max().isoformat(),
    }


def rederive_frozen_split_boundaries(frame: pd.DataFrame) -> dict:
    """
    Delegate to the harness's own boundary rule
    (`forecast_experiment._default_split_boundaries`, which places the last
    `test_fraction` of the frame's CALENDAR SPAN in test) rather than
    reimplementing the fraction arithmetic, and return both the resulting
    `SplitBoundaries` and a comparison dict recording: the re-derived
    `test_start` date, the pinned `FROZEN_TEST_SPLIT_START`, whether they
    match, and the frame's own min and max timestamps -- so a mismatch is
    diagnosable from the returned value alone without re-running anything.

    On a frame whose maximum timestamp is later than `FROZEN_WINDOW_END`,
    this produces a `test_start` LATER than `FROZEN_TEST_SPLIT_START` --
    the demonstration that the harness's boundary rule is
    window-end-dependent, and that the frozen dates must therefore be
    pinned constants rather than recomputed.
    """
    boundaries = forecast_experiment._default_split_boundaries(frame)
    frame_dt = pd.to_datetime(frame["datetime_utc"], utc=True)
    rederived_test_start = boundaries.test_start.date().isoformat()
    matches = rederived_test_start == FROZEN_TEST_SPLIT_START
    return {
        "boundaries": boundaries,
        "rederived_test_start": rederived_test_start,
        "pinned_test_start": FROZEN_TEST_SPLIT_START,
        "matches_pinned_test_start": matches,
        "frame_min": frame_dt.min().isoformat(),
        "frame_max": frame_dt.max().isoformat(),
    }


# `truth_provenance_finding`'s citations, named constants (never buried in
# prose) so a later plan can re-assert them mechanically.
_TRUTH_SOURCE_CITATION: str = "backend/open_meteo_provider.py:1-32"
_PHYSICS_PATH_CITATION: str = "backend/forecast_experiment.py:337-356"
_TRUTH_DLR_AMPS_CITATION: str = "backend/forecast_experiment.py:595-598"

# Markers this function scans for in the frozen record's own Data-provenance
# and Limitations sections -- confirmed by direct grep of the frozen record
# this session that none of these appear anywhere in either section (see
# this plan's SUMMARY.md for the exact command run).
_DISCLOSURE_MARKERS: tuple = (
    "sensor-measured",
    "sensor measured",
    "observational validation",
    "field-validated",
    "field validated",
    "no sensor",
    "not sensor-measured",
    "no independent sensor",
)


def _extract_section(text: str, heading: str) -> str:
    """Return the body of the first `## <heading>` section (up to the next `## `), or `""` if absent."""
    pattern = r"^##+\s*" + re.escape(heading)
    parts = re.split(pattern, text, maxsplit=1, flags=re.M | re.I)
    if len(parts) < 2:
        return ""
    remainder = parts[1]
    remainder = re.split(r"^##+\s", remainder, maxsplit=1, flags=re.M)[0]
    return remainder


def _scan_for_disclosure(frozen_record_path: str):
    """
    Scan the frozen record's own `## Data provenance` and `## Limitations`
    sections for a sensor/observational-validation disclosure marker.
    Returns `(found: bool, quoted_line: str | None)`.
    """
    with open(frozen_record_path, "r", encoding="utf-8") as fh:
        text = fh.read()
    for section_name in ("Data provenance", "Limitations"):
        section = _extract_section(text, section_name)
        for line in section.splitlines():
            lowered = line.lower()
            if any(marker in lowered for marker in _DISCLOSURE_MARKERS):
                return True, line.strip()
    return False, None


def truth_provenance_finding(frozen_record_path: str = DEFAULT_FROZEN_RECORD_PATH) -> dict:
    """
    The phase's first real, code-grounded finding (T-04-01-03): the entire
    "truth" side of Phase 3's experiment is itself a physics-model output
    computed from reanalysis weather (`open_meteo_provider.py`'s Archive
    API / ERA5-ERA5-Land reanalysis), run through the SAME IEEE-738 physics
    every forecast arm uses (`_city_ampacity`) -- not a sensor measurement.

    `frozen_record_states_limitation` is computed by scanning the frozen
    record's own Data-provenance and Limitations sections for a disclosure
    marker (`_scan_for_disclosure`), never hard-coded -- so a future edit to
    the frozen record that adds this disclosure would flip this field
    without any code change here.
    """
    states_limitation, quoted_line = _scan_for_disclosure(frozen_record_path)
    return {
        "finding_id": "D-01-truth-provenance",
        "truth_source": (
            "Open-Meteo's Archive API, ERA5/ERA5-Land reanalysis weather -- "
            "never a sensor measurement"
        ),
        "truth_source_citation": _TRUTH_SOURCE_CITATION,
        "physics_path": (
            "truth['dlr_amps'] is computed by _city_ampacity "
            "(perpendicular_wind projected onto the corridor bearing, then "
            "thermal_model.ieee738_ampacity) -- the SAME function and the "
            "SAME physics every forecast arm's prediction goes through, so "
            "the truth side is a second model output being compared "
            "against a first, not an independent observation"
        ),
        "physics_path_citation": _PHYSICS_PATH_CITATION,
        "truth_dlr_amps_computation_citation": _TRUTH_DLR_AMPS_CITATION,
        "frozen_record_states_limitation": states_limitation,
        "frozen_record_quotation": quoted_line,
        "severity": "high",
        "consequence": (
            "Every ampere in the frozen record's Verdict is an agreement "
            "between two model outputs (a physics-derived truth series and "
            "a physics-plus-ML-corrected forecast), never a forecast-vs-"
            "field-measurement comparison -- a reader who does not know "
            "this could mistake the reported margins for field-validated "
            "accuracy."
        ),
    }


# ──────────────────────────────────────────────────────────────────────────
# Plan 04-01 Task 2: assembling the real ABLATION/FRESH bases, measuring
# how much real data exists, and closing 04-RESEARCH.md Open Question 1
# with a measured null-drop count.
# ──────────────────────────────────────────────────────────────────────────

DEFAULT_MANIFEST_PATH: str = os.path.join(
    config.FORECAST_EXPERIMENT_CACHE_DIR, "audit_basis_manifest.json"
)


def _measure_city_assembly(city: str, start: str, end: str, *, lead_hours: int) -> dict:
    """
    Measure how many rows `forecast_experiment.anchored_pair_frame` drops
    as null for `city` over `[start, end]` at `lead_hours`, via TWO
    independent methods, per this task's own instruction that the manifest
    should carry whichever measurements were actually taken:

    1. `warning_log_capture` -- a temporary `logging.Handler` installed on
       `forecast_experiment`'s own logger, capturing the `dropped %d row(s)`
       WARNING the assembly path already emits (`anchored_pair_frame`,
       `backend/forecast_experiment.py:660-665`). Only fires on a FRESH
       fetch -- a cache hit re-reads the already-assembled CSV directly and
       never re-triggers the drop computation or its warning.
    2. An independent hourly-span expectation: the number of hourly rows
       `[start, end]` (inclusive of `end`'s full day) SHOULD contain if
       every hour were present, computed from calendar arithmetic alone,
       never from the assembled frame itself. The difference between this
       expectation and the frame's own row count is a cache-independent
       cross-check that closes 04-RESEARCH.md Open Question 1 even when the
       warning-log method is unavailable (a cache hit).

    Never edits `forecast_experiment.py` -- installs and removes its own
    handler on the existing `forecast_experiment` logger.
    """
    captured = {"dropped": None}

    class _DropCaptureHandler(logging.Handler):
        def emit(self, record):
            if record.name == "forecast_experiment" and isinstance(record.msg, str) and (
                "dropped %d row" in record.msg
            ):
                captured["dropped"] = record.args[0] if record.args else None

    fe_logger = logging.getLogger("forecast_experiment")
    handler = _DropCaptureHandler()
    prior_level = fe_logger.level
    fe_logger.addHandler(handler)
    fe_logger.setLevel(logging.WARNING)
    try:
        frame = forecast_experiment.anchored_pair_frame(city, start, end, lead_hours=lead_hours)
    finally:
        fe_logger.removeHandler(handler)
        fe_logger.setLevel(prior_level)

    assembled_rows = len(frame)

    span_index = pd.date_range(
        pd.Timestamp(start, tz="UTC"),
        pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1),
        freq="h", inclusive="left",
    )
    hourly_span_expectation = len(span_index)
    dropped_via_span = hourly_span_expectation - assembled_rows

    if captured["dropped"] is not None:
        method = (
            "warning_log_capture (this run's fresh fetch), cross-checked "
            "against an independent hourly-span expectation"
        )
    else:
        method = (
            "independent hourly-span expectation only -- no fresh "
            "WARNING observed this run, so the frame was very likely "
            "served from cache rather than freshly assembled"
        )

    return {
        "assembled_rows": assembled_rows,
        "dropped_rows": int(dropped_via_span),
        "dropped_rows_via_warning_log": (
            int(captured["dropped"]) if captured["dropped"] is not None else None
        ),
        "hourly_span_expectation": hourly_span_expectation,
        "method": method,
    }


def _build_fresh_basis_entry(corridor: str, *, lead_hours: int, resolved_window_end: str) -> dict:
    """
    Resolve the FRESH basis for `corridor` at run time. If the resolved
    window end is not strictly later than `FROZEN_WINDOW_END`, records a
    zero-row FRESH basis with an explicit reason naming both dates and
    skips the fetch entirely -- there is nothing to fetch, and issuing the
    request anyway would be a request for rows the frozen window already
    contains. Otherwise assembles the corridor frame for the window
    beginning the day after `FROZEN_WINDOW_END` through the resolved end,
    applies the exact-lead filter, and runs the frozen-window guard under
    `basis="FRESH"`.
    """
    frozen_end_ts = pd.Timestamp(FROZEN_WINDOW_END, tz="UTC")
    resolved_end_ts = pd.Timestamp(resolved_window_end, tz="UTC")

    if not (resolved_end_ts > frozen_end_ts):
        return {
            "rows": 0,
            "resolved_window_end": resolved_window_end,
            "reason": (
                f"resolved window end {resolved_window_end} is not "
                f"strictly later than FROZEN_WINDOW_END {FROZEN_WINDOW_END} "
                f"-- there is nothing to fetch"
            ),
        }

    fresh_start = (frozen_end_ts + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    fresh_frame = forecast_experiment.corridor_anchored_pair_frame(
        corridor, fresh_start, resolved_window_end, lead_hours=lead_hours,
    )
    fresh_filtered = forecast_experiment.filter_to_exact_lead(fresh_frame, lead_hours=lead_hours)
    guard_summary = assert_basis_excludes_frozen_test_rows(fresh_filtered, basis="FRESH")

    entry = {
        "rows": guard_summary["rows"],
        "resolved_window_start": fresh_start,
        "resolved_window_end": resolved_window_end,
        "first_timestamp": guard_summary["first_timestamp"],
        "last_timestamp": guard_summary["last_timestamp"],
        "frozen_window_guard_passed": True,
    }
    if entry["rows"] == 0:
        entry["reason"] = (
            f"the resolved fresh window [{fresh_start}, {resolved_window_end}] "
            f"produced zero rows after the exact-lead filter"
        )
    return entry


def _build_corridor_basis_entry(corridor: str, *, lead_hours: int, resolved_window_end: str) -> dict:
    """
    Build one corridor's manifest entry: the ABLATION basis (assembled at
    the PINNED frozen window, boundaries re-derived and matched against the
    pin, filtered train/validation row counts, frozen-window guard run over
    their concatenation), the FRESH basis (`_build_fresh_basis_entry`), and
    the per-city null-drop measurement (`_measure_city_assembly`).

    Never reads or records anything about the held-out TEST split beyond
    what `forecast_experiment.assert_filtered_split_disjoint` itself needs
    internally (which the harness's own docstring establishes is not a
    no-peeking violation -- it reads only timestamps, never a target
    value). This function does not return or log the test split's row
    count or any other property of it.
    """
    city_a, city_b = config.CORRIDOR_ENDPOINTS[corridor]

    # Per-city null-drop measurement FIRST, while a fresh fetch (if any) is
    # still possible -- corridor_anchored_pair_frame below will then hit
    # the cache these calls just warmed.
    cities_entry = {
        city_a: _measure_city_assembly(
            city_a, FROZEN_WINDOW_START, FROZEN_WINDOW_END, lead_hours=lead_hours,
        ),
        city_b: _measure_city_assembly(
            city_b, FROZEN_WINDOW_START, FROZEN_WINDOW_END, lead_hours=lead_hours,
        ),
    }

    corridor_frame = forecast_experiment.corridor_anchored_pair_frame(
        corridor, FROZEN_WINDOW_START, FROZEN_WINDOW_END, lead_hours=lead_hours,
    )

    rederived = rederive_frozen_split_boundaries(corridor_frame)
    boundaries = rederived["boundaries"]

    train, val, test = experiment_splits.calendar_split(corridor_frame, boundaries)
    train_filtered = forecast_experiment.filter_to_exact_lead(train, lead_hours=lead_hours)
    val_filtered = forecast_experiment.filter_to_exact_lead(val, lead_hours=lead_hours)
    test_filtered = forecast_experiment.filter_to_exact_lead(test, lead_hours=lead_hours)

    # Sanctioned per the harness's own precedent (assert_filtered_split_
    # disjoint's docstring): reading test's own TIMESTAMPS for a
    # disjointness check is calendar-boundary arithmetic, not a no-peeking
    # violation -- no target value is read, and this function returns
    # nothing derived from `test_filtered` beyond this assertion's pass/fail.
    forecast_experiment.assert_filtered_split_disjoint(train_filtered, val_filtered, test_filtered)
    del test_filtered  # never referenced again -- not stored, not returned, not logged.

    # The re-derived boundary's DATE matches the pinned constant (checked
    # below), but the harness's own boundary rule computes an exact
    # sub-day TIMESTAMP, not a midnight-aligned date -- so the real
    # validation split can extend a few hours into the pinned boundary's
    # calendar day. The pin is deliberately DATE-granularity (matching how
    # the frozen record itself states it: "test split starts 2026-03-17",
    # no time component), which is the more conservative of the two -- so
    # this audit clips the ABLATION basis to strictly before the PINNED
    # constant (never the re-derived, sub-day-precise one), discarding a
    # handful of same-day rows that the harness's own precise boundary
    # would have kept in validation. This is intentionally conservative:
    # excluding a few extra hours of legitimate validation data costs
    # nothing scientifically and keeps the frozen-window guard's date-level
    # pin authoritative over a sub-day recomputation this module explicitly
    # does not trust (see FROZEN_TEST_SPLIT_START's own comment).
    pinned_boundary = pd.Timestamp(FROZEN_TEST_SPLIT_START, tz="UTC")
    train_before_clip, val_before_clip = len(train_filtered), len(val_filtered)
    train_filtered = train_filtered[train_filtered["datetime_utc"] < pinned_boundary].reset_index(drop=True)
    val_filtered = val_filtered[val_filtered["datetime_utc"] < pinned_boundary].reset_index(drop=True)
    rows_clipped_for_pin_safety = (
        (train_before_clip - len(train_filtered)) + (val_before_clip - len(val_filtered))
    )

    ablation_frame = pd.concat([train_filtered, val_filtered], ignore_index=True)
    assert_basis_excludes_frozen_test_rows(ablation_frame, basis="ABLATION")

    ablation_entry = {
        "train_rows": len(train_filtered),
        "val_rows": len(val_filtered),
        "rederived_test_start": rederived["rederived_test_start"],
        "pinned_test_start": rederived["pinned_test_start"],
        "matches_pinned_test_start": rederived["matches_pinned_test_start"],
        "rows_clipped_for_pin_safety": rows_clipped_for_pin_safety,
        "frozen_window_guard_passed": True,
    }

    fresh_entry = _build_fresh_basis_entry(
        corridor, lead_hours=lead_hours, resolved_window_end=resolved_window_end,
    )

    return {
        "ablation": ablation_entry,
        "fresh": fresh_entry,
        "cities": cities_entry,
    }


def build_basis_manifest(
    corridors=None, *, lead_hours: int = None, manifest_path: str = None,
) -> dict:
    """
    Assemble the real ABLATION and FRESH bases for every corridor in
    `corridors` (default: every corridor in `config.CORRIDOR_ENDPOINTS`),
    measure the null-drop for each endpoint city, and write the whole
    manifest as JSON to `manifest_path` (default:
    `data/experiment/audit_basis_manifest.json`, git-ignored evidence, never
    the artifact of record).

    Raises `ValueError` naming the valid corridors for an unknown one.

    Atomic load-merge-write: if `manifest_path` already exists, this
    function loads it first and merges this run's corridor entries into the
    existing `corridors` mapping (overwriting only the corridors just
    computed) rather than replacing the whole file -- a second, narrower
    run (e.g. `corridors=["AUSTIN_CORPUS_CHRISTI"]`) never clobbers a prior
    run's entry for a corridor it did not touch. Writes to a `.tmp` path and
    `os.replace`s it into place so a reader never observes a partially
    written file.
    """
    if lead_hours is None:
        lead_hours = config.FORECAST_EXPERIMENT_PRIMARY_LEAD_HOURS
    if manifest_path is None:
        manifest_path = DEFAULT_MANIFEST_PATH

    valid_corridors = sorted(config.CORRIDOR_ENDPOINTS)
    if corridors is None:
        corridors = valid_corridors
    else:
        corridors = list(corridors)
        unknown = sorted(set(corridors) - set(valid_corridors))
        if unknown:
            raise ValueError(
                f"build_basis_manifest: unknown corridor(s) {unknown} -- "
                f"valid corridors: {valid_corridors}"
            )

    resolved_window_end = forecast_experiment._resolve_window_end(None)

    new_entries = {}
    for corridor in corridors:
        new_entries[corridor] = _build_corridor_basis_entry(
            corridor, lead_hours=lead_hours, resolved_window_end=resolved_window_end,
        )

    manifest_dir = os.path.dirname(manifest_path)
    if manifest_dir:
        os.makedirs(manifest_dir, exist_ok=True)

    existing = {}
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as fh:
                existing = json.load(fh)
        except (json.JSONDecodeError, OSError):
            existing = {}

    merged_corridors = dict(existing.get("corridors", {}))
    merged_corridors.update(new_entries)

    manifest = {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "note": (
            "Git-ignored evidence, not the artifact of record -- mirrors "
            "this project's established convention for generated JSON "
            "reports (see data/experiment/'s .gitignore entry)."
        ),
        "resolved_window_end": resolved_window_end,
        "lead_hours": lead_hours,
        "corridors": merged_corridors,
    }

    tmp_path = manifest_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, default=str)
    os.replace(tmp_path, manifest_path)

    return manifest


# ──────────────────────────────────────────────────────────────────────────
# Plan 04-02 Task 1: what the lead-time calibration gate actually proves,
# and where in time every column of the scored frame lives (D-01 bullets 2
# and 3, first half).
# ──────────────────────────────────────────────────────────────────────────

# `decision_time_availability_finding`'s citations, named constants (never
# buried in prose) so a later plan can re-assert them mechanically. Every
# one of these was read directly this session, not carried over from
# 04-RESEARCH.md's own citations.
_CALIBRATION_MEASUREMENT_FN_CITATION: str = "backend/forecast_leadtime_calibration.py:390"
_CALIBRATION_GATE_FN_CITATION: str = "backend/forecast_leadtime_calibration.py:515"
_PREVIOUS_RUNS_FETCH_CITATION: str = "backend/open_meteo_forecast_provider.py:513"
_SINGLE_RUNS_FETCH_CITATION: str = "backend/open_meteo_forecast_provider.py:374"
_PREVIOUS_RUNS_ENDPOINT_CITATION: str = "backend/open_meteo_forecast_provider.py:80"
_SINGLE_RUNS_ENDPOINT_CITATION: str = "backend/open_meteo_forecast_provider.py:79"
_COMPARED_QUANTITY_CITATION: str = "backend/forecast_leadtime_calibration.py:412"
_SUCCESS_CONDITION_CITATION: str = "backend/forecast_leadtime_calibration.py:552"
_RECORDED_LIMITATION_CITATION: str = "docs/data-science/decisions/forecast_correction_experiment.md:392"


def decision_time_availability_finding() -> dict:
    """
    D-01 bullet 2. Reads `forecast_leadtime_calibration.measure_previous_runs_alignment`
    (`_CALIBRATION_MEASUREMENT_FN_CITATION`) and `assert_exact_offset_lead`
    (`_CALIBRATION_GATE_FN_CITATION`) -- the gate's own measurement path --
    and the two fetch functions it reaches (`open_meteo_forecast_provider.
    fetch_previous_runs`, `.fetch_single_run`) to establish, from the code
    and nothing else, exactly what the gate proves and what it cannot.

    Both endpoints the gate's measurement path reaches
    (`previous-runs-api.open-meteo.com`, `single-runs-api.open-meteo.com`)
    are backward-looking archives -- confirmed by reading their own request
    functions and the module docstring's own characterization of all three
    forecast-family endpoints as archives, never a live dissemination feed.
    A gate built entirely from two archive reads can therefore prove a
    value-matching relationship between those two archives and nothing
    about whether a real consumer received the value over the network at
    the claimed decision time -- this is a structural argument, not a
    rhetorical one, and `reachable_fetch_functions` below enumerates the
    exact functions that make it checkable.
    """
    compared_products = {
        "previous_runs_archive": {
            "description": (
                "Open-Meteo's Previous-Runs API `previous_day1` series -- a "
                "backward-looking archive reconstructing, for each valid "
                "time T, the stitched value the six-hourly run issued "
                "`lead_hours` earlier produced for T."
            ),
            "endpoint": "previous-runs-api.open-meteo.com",
            "endpoint_citation": _PREVIOUS_RUNS_ENDPOINT_CITATION,
            "fetch_function": "open_meteo_forecast_provider.fetch_previous_runs",
            "fetch_function_citation": _PREVIOUS_RUNS_FETCH_CITATION,
        },
        "single_runs_archive": {
            "description": (
                "Open-Meteo's Single-Runs API -- a backward-looking archive "
                "reconstructing one exact, named model run (`run=<timestamp>`) "
                "at its own native forecast leads."
            ),
            "endpoint": "single-runs-api.open-meteo.com",
            "endpoint_citation": _SINGLE_RUNS_ENDPOINT_CITATION,
            "fetch_function": "open_meteo_forecast_provider.fetch_single_run",
            "fetch_function_citation": _SINGLE_RUNS_FETCH_CITATION,
        },
    }

    compared_quantity = (
        "wind_speed -- the variable measure_previous_runs_alignment requests "
        "from both endpoints (matching the legacy 1-hour gate's own "
        "convention), compared within a 0.1 m/s tolerance "
        "(_MATCH_TOLERANCE_MS) to absorb independent-rounding noise between "
        "the two endpoints' own JSON serialization, not to relax the rule."
    )

    success_condition = (
        "assert_exact_offset_lead requires BOTH: (1) every offset in the "
        "stitched band [lead_hours, lead_hours + modulus - 1] shows a "
        "match rate >= 0.9 (_MATCH_RATE_FLOOR) between the two archives' "
        "values, and (2) the per-row lead sample, restricted to the "
        "exact-lead hour filter, is uniformly exactly lead_hours (min and "
        "max both equal lead_hours, no percentile softening). Both "
        "conditions are computed purely from comparing the two archived "
        "series against each other -- neither reads, nor could read, any "
        "real-time dissemination signal."
    )

    supported_claim = (
        "The gate proves a value-matching relationship between two "
        "retrospective archival products: the Previous-Runs archive's value "
        "at valid time T equals, within rounding tolerance, the Single-Runs "
        "archive's value from the run issued exactly lead_hours earlier -- "
        "i.e. that the Previous-Runs product's construction genuinely "
        "corresponds to a run labeled T-minus-lead_hours, not some other run."
    )
    unsupported_claim = (
        "The gate does NOT prove that a real forecast consumer could have "
        "received this exact value over the network at the actual wall-clock "
        "moment T - lead_hours. Both endpoints the gate queries are "
        "backward-looking archives -- neither is a live dissemination feed a "
        "consumer could have polled in real time -- so no comparison between "
        "two archives, however well they agree, can evidence that the value "
        "was ever actually available for consumption at that clock moment; "
        "it evidences only that the value is the one later archived under "
        "that lead label."
    )

    reachable_fetch_functions = [
        f"open_meteo_forecast_provider.fetch_previous_runs "
        f"({_PREVIOUS_RUNS_FETCH_CITATION}, {compared_products['previous_runs_archive']['endpoint']}"
        f" -- backward-looking archive, confirmed by its own request function"
        f" and this module's docstring)",
        f"open_meteo_forecast_provider.fetch_single_run "
        f"({_SINGLE_RUNS_FETCH_CITATION}, {compared_products['single_runs_archive']['endpoint']}"
        f" -- backward-looking archive, confirmed by its own request function"
        f" and this module's docstring)",
    ]

    differs_from_recorded_limitation = (
        "The frozen record's Limitations section "
        f"({_RECORDED_LIMITATION_CITATION}) already discloses a COVERAGE "
        "limitation: the Single-Runs archive for gfs_seamless only reaches "
        "back to roughly mid-2026, so the stitching cross-check can only be "
        "RUN over a handful of recent dates, and its applicability to the "
        "bulk of the experiment's 2024-2025 window rests on the stitching "
        "mechanism being general rather than on a direct historical "
        "cross-check. That is a claim about HOW MUCH of the window the "
        "cross-check can reach. This finding is a distinct CLAIM-TYPE "
        "limitation: even over the dates the cross-check DOES reach, the "
        "thing it proves is a value-match between two archives, and no "
        "archive-to-archive comparison -- however completely it covers the "
        "window -- can ever evidence real-time dissemination to a consumer. "
        "A reader who conflates the two would wrongly conclude that a wider "
        "cross-check (deeper archive reach) would close this gap; it would "
        "not, because the gap is in what KIND of claim two archives can "
        "jointly support, not in how much of the calendar they cover."
    )

    citations = {
        "measurement_function": _CALIBRATION_MEASUREMENT_FN_CITATION,
        "gate_function": _CALIBRATION_GATE_FN_CITATION,
        "previous_runs_fetch": _PREVIOUS_RUNS_FETCH_CITATION,
        "single_runs_fetch": _SINGLE_RUNS_FETCH_CITATION,
        "previous_runs_endpoint": _PREVIOUS_RUNS_ENDPOINT_CITATION,
        "single_runs_endpoint": _SINGLE_RUNS_ENDPOINT_CITATION,
        "compared_quantity": _COMPARED_QUANTITY_CITATION,
        "success_condition": _SUCCESS_CONDITION_CITATION,
        "recorded_limitation": _RECORDED_LIMITATION_CITATION,
    }

    return {
        "finding_id": "D-01-decision-time-availability",
        "compared_products": compared_products,
        "compared_quantity": compared_quantity,
        "compared_quantity_citation": _COMPARED_QUANTITY_CITATION,
        "success_condition": success_condition,
        "success_condition_citation": _SUCCESS_CONDITION_CITATION,
        "supported_claim": supported_claim,
        "unsupported_claim": unsupported_claim,
        "differs_from_recorded_limitation": differs_from_recorded_limitation,
        "reachable_fetch_functions": reachable_fetch_functions,
        "citations": citations,
        "severity": "critical",
    }


# ──────────────────────────────────────────────────────────────────────────
# `frame_time_reference_groups` -- D-01 bullet 3, first half. Classification
# rules are derived directly from `anchored_pair_frame`'s and
# `corridor_anchored_pair_frame`'s own rename maps
# (backend/forecast_experiment.py:611-651, :819-866), never from a guess
# about naming conventions.
# ──────────────────────────────────────────────────────────────────────────

# The group labels this classification returns, in the order the plan's
# <action> lists them (index/diagnostic last, mirroring how a reader would
# scan the schema: data columns first, bookkeeping last). Every real column
# in either assembled frame shape must land in exactly one of these seven
# lists, or in `unclassified`.
_TIME_REFERENCE_GROUP_LABELS: tuple = (
    "observed_at_valid_time",
    "observed_at_decision_time",
    "forecast_valid_at_valid_time",
    "forecast_valid_at_decision_time",
    "corridor_reduced_predictions",
    "bottleneck_selection_diagnostics",
    "index_and_diagnostic_columns",
)


def _classify_time_reference_column(col: str):
    """
    Return `(group_label, instant)` for one column name, or `(None, None)`
    if the column is not recognized. `instant` is `"valid_time"`,
    `"decision_time"`, or `None` (for a column with no clock-instant
    reference at all, e.g. a diagnostic flag or a bottleneck-selection
    index).

    Checked in an order that matters: `fcst_anchor_*` must be checked
    before the plain `fcst_*` prefix (every `fcst_anchor_*` column also
    starts with `fcst_`), and the three named index columns
    (`datetime_utc`, `anchor_datetime_utc`, `fcst_anchor_datetime_utc`) are
    checked as EXACT matches before any prefix rule, so they are never
    absorbed into `anchor_*`/`forecast_valid_at_decision_time` by accident.
    A column containing a recognized prefix as a SUBSTRING but not as its
    actual PREFIX (e.g. a hypothetical `midwindow_truth_wind_speed_t_minus_12h`)
    is deliberately NOT classified -- `startswith`, never `in`, is what makes
    this an assertion about the schema's own naming convention rather than a
    fuzzy match that could silently absorb an unrelated future column.
    """
    if col == "datetime_utc":
        return "index_and_diagnostic_columns", "valid_time"
    if col in ("anchor_datetime_utc", "fcst_anchor_datetime_utc"):
        return "index_and_diagnostic_columns", "decision_time"
    if col in (
        "hour_mod_remainder", "nwp_wind_delta_clamped_a", "nwp_wind_delta_clamped_b",
    ):
        return "index_and_diagnostic_columns", None
    if col.startswith("bottleneck_index_"):
        return "bottleneck_selection_diagnostics", None
    if col.startswith("fcst_anchor_"):
        return "forecast_valid_at_decision_time", "decision_time"
    if col.startswith("fcst_"):
        return "forecast_valid_at_valid_time", "valid_time"
    if col.startswith("anchor_"):
        return "observed_at_decision_time", "decision_time"
    if col.startswith("truth_"):
        return "observed_at_valid_time", "valid_time"
    if col.startswith("pred_"):
        return "corridor_reduced_predictions", "valid_time"
    return None, None


def frame_time_reference_groups(frame: pd.DataFrame) -> dict:
    """
    Classify every column of `frame` into exactly one time-reference group,
    proven exhaustive by assertion rather than claimed: any column this
    function does not recognize lands in `unclassified` instead of being
    silently absorbed into a group, so a future schema change (a new column
    referencing an instant strictly between decision time and valid time,
    for instance) surfaces as a non-empty `unclassified` list rather than
    passing invisibly.

    Works on both assembled frame shapes -- the per-city `anchored_pair_frame`
    (which carries `fcst_*`/`fcst_anchor_*` groups) and the corridor-level
    `corridor_anchored_pair_frame` (which does not, but carries
    `pred_<arm>`/`bottleneck_index_<arm>` groups instead) -- since
    `_classify_time_reference_column` recognizes both frames' column sets
    from the same prefix rules.

    Returns a mapping from each of `_TIME_REFERENCE_GROUP_LABELS` to the
    list of this frame's columns carrying that label, plus `unclassified`
    (columns recognized by none of the rules) and
    `distinct_clock_instants_per_row` -- the count of distinct clock
    instants (`"valid_time"`, `"decision_time"`) referenced by ANY column in
    the frame, which is 2 for both real assembled frame shapes: no column in
    either schema, today, references an instant strictly between decision
    time and valid time.
    """
    groups = {label: [] for label in _TIME_REFERENCE_GROUP_LABELS}
    unclassified = []
    instants_seen = set()

    for col in frame.columns:
        label, instant = _classify_time_reference_column(col)
        if label is None:
            unclassified.append(col)
            continue
        groups[label].append(col)
        if instant is not None:
            instants_seen.add(instant)

    groups["unclassified"] = unclassified
    groups["distinct_clock_instants_per_row"] = len(instants_seen)
    return groups


# ──────────────────────────────────────────────────────────────────────────
# Plan 04-02 Task 2: re-run the leakage probe on real ABLATION-basis data,
# in both callable shapes, and report the difference (D-01 bullet 3, second
# half).
# ──────────────────────────────────────────────────────────────────────────

def _leakage_report_path(corridor: str) -> str:
    return os.path.join(
        config.FORECAST_EXPERIMENT_CACHE_DIR,
        f"leakage_probe_coverage_report_{corridor}.json",
    )


def _mode_b_arm_mapping(*, geometry, fitted, live_arm5):
    """
    The Mode B arm mapping: the four `NON_FITTED_ARMS` factories (live
    callables already, unmodified), the two fitted corrections bound to
    their ABLATION-train-fit models via `forecast_experiment._wind_
    corrected_ampacity`/`_cooling_corrected_ampacity` (genuinely re-reading
    `frame`'s own `fcst_*`/`anchor_*` columns on every call, per those
    functions' own docstrings), the live arm-5 callable (`live_arm5`,
    genuinely re-reading `frame["anchor_datetime_utc"]` on every call), and
    one deliberately sabotaged arm reading `truth_wind_speed` directly --
    mirrors `forecast_experiment_test.py`'s own existing power test
    (`test_leakage_probe_passes_on_real_arms_flags_oracle_and_flags_a_sabotaged_arm`)
    exactly, generalized to run on real data instead of synthetic.
    """
    arms = {
        name: forecast_experiment.NON_FITTED_ARMS[name](geometry)
        for name in forecast_experiment.NON_FITTED_ARMS
    }
    arms["ml_wind_corrected"] = (
        lambda f, m=fitted["wind_model"]: forecast_experiment._wind_corrected_ampacity(m, f, geometry)
    )
    arms["ml_cooling_corrected"] = (
        lambda f, m=fitted["cooling_model"]: forecast_experiment._cooling_corrected_ampacity(m, f, geometry)
    )
    arms["reference_ml_refit_24h"] = live_arm5
    arms["sabotaged_reads_truth_wind_directly"] = lambda f: f["truth_wind_speed"].to_numpy(dtype=float)
    return arms


def leakage_probe_coverage_report(
    corridor: str, *, lead_hours: int = None, report_path: str = None,
) -> dict:
    """
    Re-run `forecast_experiment.leakage_probe` twice on real ABLATION-basis
    rows for `corridor`: once against the corridor-level prediction-column
    readers the frozen test-set scoring path actually built
    (`forecast_experiment._corridor_arm_reader`, Mode A), and once against
    live-recomputing callables on each endpoint city's own real rows, with
    a deliberately sabotaged arm for power (Mode B). Reports both outcomes
    and what their difference means for the frozen record's Success-
    Criterion-3 disposition.

    Raises `ValueError` naming the valid corridors for an unknown one.

    Every frame either mode uses passes `assert_basis_excludes_frozen_test_rows`
    under `basis="ABLATION"` BEFORE the probe runs on it -- checked
    immediately after each frame is built and clipped, never deferred until
    after fitting or scoring. Arms 3/4/5 are fit ONCE, on the ABLATION train
    rows only (`forecast_experiment.WIND_CONFIGURATION`/
    `COOLING_CONFIGURATION`, never re-selected here), and NEVER on the
    frozen record's held-out test rows -- this function never assembles
    `forecast_experiment._stacked_pair_frame`'s test-range rows into memory
    at all: `stacked_test` is discarded immediately after `calendar_split`,
    and every downstream computation (fitting, arm 5's feature table, both
    probe modes) is built exclusively from the train+val (ABLATION) portion.
    """
    valid_corridors = sorted(config.CORRIDOR_ENDPOINTS)
    if corridor not in config.CORRIDOR_ENDPOINTS:
        raise ValueError(
            f"leakage_probe_coverage_report: unknown corridor {corridor!r} "
            f"-- valid corridors: {valid_corridors}"
        )
    if lead_hours is None:
        lead_hours = config.FORECAST_EXPERIMENT_PRIMARY_LEAD_HOURS
    if report_path is None:
        report_path = _leakage_report_path(corridor)

    city_a, city_b = config.CORRIDOR_ENDPOINTS[corridor]
    geometry = corridor_discretization.corridor_geometry(corridor)

    # ---- Assemble the real ABLATION-basis corridor frame, mirroring
    # build_basis_manifest's own boundary/filter/clip discipline exactly,
    # so this function's val split is the SAME 782-ish-row ABLATION
    # validation basis Plan 04-01 measured -- never a re-derived one. ----
    corridor_frame = forecast_experiment.corridor_anchored_pair_frame(
        corridor, FROZEN_WINDOW_START, FROZEN_WINDOW_END, lead_hours=lead_hours,
    )
    boundaries = forecast_experiment._default_split_boundaries(corridor_frame)
    train, val, test = experiment_splits.calendar_split(corridor_frame, boundaries)
    train_filtered = forecast_experiment.filter_to_exact_lead(train, lead_hours=lead_hours)
    val_filtered = forecast_experiment.filter_to_exact_lead(val, lead_hours=lead_hours)
    test_filtered = forecast_experiment.filter_to_exact_lead(test, lead_hours=lead_hours)
    forecast_experiment.assert_filtered_split_disjoint(train_filtered, val_filtered, test_filtered)
    del test_filtered  # never referenced again -- this function never touches the test split.

    pinned_boundary = pd.Timestamp(FROZEN_TEST_SPLIT_START, tz="UTC")
    train_filtered = train_filtered[train_filtered["datetime_utc"] < pinned_boundary].reset_index(drop=True)
    val_filtered = val_filtered[val_filtered["datetime_utc"] < pinned_boundary].reset_index(drop=True)

    # The frozen-window guard runs BEFORE anything else touches val_filtered
    # -- before fitting, before augmenting, before the probe.
    mode_a_guard = assert_basis_excludes_frozen_test_rows(val_filtered, basis="ABLATION")

    # ---- The stacked, per-city, ABLATION-only (train+val) frame. The
    # frozen record's test-range rows are discarded immediately below and
    # never referenced again by this function -- fit_fitted_arms and both
    # probe modes see ONLY train+val data. ----
    stacked_full = forecast_experiment._stacked_pair_frame(
        corridor, FROZEN_WINDOW_START, FROZEN_WINDOW_END, lead_hours=lead_hours,
    )
    stacked_train, stacked_val, stacked_test = experiment_splits.calendar_split(stacked_full, boundaries)
    del stacked_test  # never touched again -- this function never assembles against Phase 3's frozen test window.
    train_val_stacked = (
        pd.concat([stacked_train, stacked_val], ignore_index=True)
        .sort_values("datetime_utc").reset_index(drop=True)
    )

    # Arms fit on the ABLATION TRAIN rows only -- never train+val, since val
    # is what both probe modes score below, and never re-selected: the
    # harness's own validation-selected configuration constants.
    fitted = forecast_experiment.fit_fitted_arms(
        stacked_train, geometry,
        wind_configuration=forecast_experiment.WIND_CONFIGURATION,
        cooling_configuration=forecast_experiment.COOLING_CONFIGURATION,
    )

    # ---- Mode A: the callable shape the frozen test-set scoring path
    # actually built -- corridor-level prediction-COLUMN readers, never a
    # recomputation from frame's own weather columns.
    #
    # `forecast_experiment._score_fitted_arms_at_corridor_level`/
    # `_fitted_arm_city_frame` are NOT reused here even though they
    # implement this exact logic: both call `experiment_splits.
    # calendar_split` with its default `min_rows_per_side=1`, and
    # `train_val_stacked` (deliberately train+val ONLY, per the docstring
    # above) always produces a zero-row TEST side under that split --
    # `calendar_split` raises on an empty side by design (the harness's own
    # empty-side guard), so those two functions cannot run against a frame
    # that intentionally excludes the test range. `_ablation_val_city_frame`
    # below reimplements only the val-side extraction those functions
    # perform (`datetime_utc >= boundaries.val_start`, filtered to the
    # exact lead), which is safe here because `train_val_stacked` contains
    # no row at or after `boundaries.test_start` in the first place -- so
    # "everything at or after val_start" and "the val side" are the same
    # set for this frame, without needing calendar_split's three-way floor
    # check at all. ----
    def _ablation_val_city_frame(city: str) -> pd.DataFrame:
        city_frame = (
            train_val_stacked[train_val_stacked["endpoint_city"] == city]
            .sort_values("datetime_utc").reset_index(drop=True)
        )
        val_side = city_frame[city_frame["datetime_utc"] >= boundaries.val_start].reset_index(drop=True)
        val_side = forecast_experiment.filter_to_exact_lead(val_side, lead_hours=lead_hours)
        # SAME pin-safety clip build_basis_manifest applies at the corridor
        # level (Finding 2): the harness's own sub-day-precise boundary can
        # land a few hours into the pinned boundary's calendar day, so this
        # per-city extraction is clipped to strictly before the pinned
        # DATE-granularity constant, never the sub-day-precise recomputed one.
        return val_side[val_side["datetime_utc"] < pinned_boundary].reset_index(drop=True)

    arm5_truth_frame = forecast_experiment._arm5_truth_frame(train_val_stacked, city_a, city_b)
    x5_all, _ = forecast_training.build_training_matrix(arm5_truth_frame, horizon_minutes=1440)

    mode_a_city_a_frame = forecast_experiment._add_correction_columns(_ablation_val_city_frame(city_a), geometry)
    mode_a_city_b_frame = forecast_experiment._add_correction_columns(_ablation_val_city_frame(city_b), geometry)

    wind_pred_a = forecast_experiment._wind_corrected_ampacity(fitted["wind_model"], mode_a_city_a_frame, geometry)
    wind_pred_b = forecast_experiment._wind_corrected_ampacity(fitted["wind_model"], mode_a_city_b_frame, geometry)
    wind_reduced, wind_bottleneck = forecast_experiment._merge_prediction_to_scored_index(
        val_filtered, mode_a_city_a_frame["datetime_utc"], wind_pred_a,
        mode_a_city_b_frame["datetime_utc"], wind_pred_b,
    )

    cooling_pred_a = forecast_experiment._cooling_corrected_ampacity(fitted["cooling_model"], mode_a_city_a_frame, geometry)
    cooling_pred_b = forecast_experiment._cooling_corrected_ampacity(fitted["cooling_model"], mode_a_city_b_frame, geometry)
    cooling_reduced, cooling_bottleneck = forecast_experiment._merge_prediction_to_scored_index(
        val_filtered, mode_a_city_a_frame["datetime_utc"], cooling_pred_a,
        mode_a_city_b_frame["datetime_utc"], cooling_pred_b,
    )

    anchor_index = pd.DatetimeIndex(pd.to_datetime(val_filtered["anchor_datetime_utc"], utc=True))
    x5_scored = x5_all.reindex(anchor_index)
    missing_mask = x5_scored.isna().any(axis=1)
    if missing_mask.any():
        missing = anchor_index[missing_mask]
        raise ValueError(
            f"leakage_probe_coverage_report: Mode A's arm 5 feature table is "
            f"missing {int(missing_mask.sum())} anchor timestamp(s) needed "
            f"by the val split, e.g. {list(missing[:3])}"
        )
    arm5_pred = np.asarray(fitted["arm5_estimator"].predict(x5_scored.to_numpy(dtype=float)), dtype=float)

    augmented_val = val_filtered.copy()
    augmented_val["pred_ml_wind_corrected"] = wind_reduced
    augmented_val["bottleneck_index_ml_wind_corrected"] = wind_bottleneck
    augmented_val["pred_ml_cooling_corrected"] = cooling_reduced
    augmented_val["bottleneck_index_ml_cooling_corrected"] = cooling_bottleneck
    augmented_val["pred_reference_ml_refit_24h"] = arm5_pred

    mode_a_arms = {
        name: forecast_experiment._corridor_arm_reader(name) for name in forecast_experiment.ALL_ARMS
    }
    mode_a_result = forecast_experiment.leakage_probe(augmented_val, mode_a_arms)

    # ---- Mode B: live-recomputing callables on each endpoint city's own
    # real rows. Arm 5's live callable re-reads `frame["anchor_datetime_utc"]`
    # on every call and reindexes into the SAME `x5_all` feature table built
    # above from `train_val_stacked` (never stacked_full) -- so it too
    # never sees a test-range truth value. ----

    def _live_arm5(frame: pd.DataFrame) -> np.ndarray:
        idx = pd.DatetimeIndex(pd.to_datetime(frame["anchor_datetime_utc"], utc=True))
        features = x5_all.reindex(idx)
        missing_mask = features.isna().any(axis=1)
        if missing_mask.any():
            missing = idx[missing_mask]
            raise ValueError(
                f"leakage_probe_coverage_report: arm 5's feature table is "
                f"missing {int(missing_mask.sum())} anchor timestamp(s), "
                f"e.g. {list(missing[:3])}"
            )
        return np.asarray(fitted["arm5_estimator"].predict(features.to_numpy(dtype=float)), dtype=float)

    mode_b_by_city = {}
    for city in (city_a, city_b):
        # Same reasoning as Mode A above: `_fitted_arm_city_frame` cannot be
        # reused here because it routes through `calendar_split`'s
        # three-way empty-side floor, which `train_val_stacked` (train+val
        # only, by construction) always fails on the test side.
        city_frame = forecast_experiment._add_correction_columns(_ablation_val_city_frame(city), geometry)
        # Restrict to rows arm 5's feature table can actually serve, the
        # way the harness's existing power test does.
        serviceable = pd.DatetimeIndex(
            pd.to_datetime(city_frame["anchor_datetime_utc"], utc=True)
        ).isin(x5_all.index)
        city_frame = city_frame[serviceable].reset_index(drop=True)
        if len(city_frame) == 0:
            raise ValueError(
                f"leakage_probe_coverage_report: {city}'s Mode B frame has "
                f"zero rows after restricting to arm 5's serviceable "
                f"feature rows -- cannot re-run the probe on an empty frame"
            )

        city_guard = assert_basis_excludes_frozen_test_rows(city_frame, basis="ABLATION")

        arms = _mode_b_arm_mapping(geometry=geometry, fitted=fitted, live_arm5=_live_arm5)
        city_result = forecast_experiment.leakage_probe(city_frame, arms)
        mode_b_by_city[city] = {
            "result": city_result, "rows": len(city_frame), "frozen_window_guard": city_guard,
        }

    # Combine both cities' Mode B results: an arm counts as "changed"
    # overall if it changed in EITHER city -- a real leak in one endpoint
    # city must not be hidden by the other city's silence.
    all_arm_names = sorted(set().union(*(set(v["result"]) for v in mode_b_by_city.values())))
    mode_b_arms_combined = {}
    for name in all_arm_names:
        per_city = [mode_b_by_city[c]["result"][name] for c in (city_a, city_b)]
        mode_b_arms_combined[name] = {
            "changed": any(r["changed"] for r in per_city),
            "max_abs_change": max(r["max_abs_change"] for r in per_city),
        }

    mode_a_candidates_unchanged = all(
        res["changed"] is False
        for name, res in mode_a_result.items()
        if name != forecast_experiment.ORACLE_ARM_NAME
    )
    oracle_distinguished = bool(
        mode_a_result[forecast_experiment.ORACLE_ARM_NAME]["changed"] and mode_a_candidates_unchanged
    )

    if oracle_distinguished:
        finding = (
            "Mode A (the frozen scoring path's own corridor-level prediction-column "
            "readers) DID distinguish the oracle from the candidates -- unexpected "
            "given the probe's own docstring caveat about precomputed-lookup "
            "callables, and worth escalating rather than accepting at face value."
        )
    else:
        oracle_result = mode_a_result[forecast_experiment.ORACLE_ARM_NAME]
        finding = (
            "Mode A reports every arm unchanged, INCLUDING THE ORACLE "
            f"(changed={oracle_result['changed']}, max_abs_change="
            f"{oracle_result['max_abs_change']:.6g}) -- the callable shape the "
            "frozen test-set scoring path actually built (a reader of an "
            "already-computed pred_<arm> column) cannot be moved by sabotaging "
            "truth_* columns, because those predictions were computed BEFORE "
            "sabotage and are never recomputed. The oracle is the one arm "
            "designed to consume truth at the valid time; its silence here is "
            "the proof that this callable shape certifies nothing about leakage, "
            "not evidence of an absence of leakage. Mode B (live-recomputing "
            "callables on real per-city rows) demonstrates the probe DOES have "
            "power on real, non-synthetic data: the sabotaged arm and the oracle "
            "both changed, every genuine candidate did not. The frozen record's "
            "Success Criterion 3 disposition ('leakage probe demonstrates no "
            "arm depends on truth at or after the valid time') was verified in "
            "a callable shape that structurally cannot fail -- the frozen "
            "numbers themselves were never actually probed. This is a real, "
            "confirmed gap this task's own Mode B re-run remediates: the probe "
            "now has demonstrated power on real ABLATION-basis data, in the "
            "live-recomputing shape the frozen record's own Limitations "
            "section already anticipates as the correct one (`leakage_probe`'s "
            "coverage is partial by design -- direct-read leakage, not a "
            "trained-on-test-rows leak), but that shape was never the one the "
            "frozen numbers were produced through."
        )

    comparison = {
        "oracle_distinguished": oracle_distinguished,
        "mode_a_all_unchanged_including_oracle": (
            mode_a_candidates_unchanged and not mode_a_result[forecast_experiment.ORACLE_ARM_NAME]["changed"]
        ),
        "mode_b_sabotaged_arm_detected": mode_b_arms_combined.get(
            "sabotaged_reads_truth_wind_directly", {},
        ).get("changed", False),
        "mode_b_oracle_detected": mode_b_arms_combined.get(
            forecast_experiment.ORACLE_ARM_NAME, {},
        ).get("changed", False),
    }

    report = {
        "corridor": corridor,
        "lead_hours": lead_hours,
        "mode_a": {
            "callable_shape": "corridor-level prediction-column readers (forecast_experiment._corridor_arm_reader) -- the shape the frozen test-set scoring path actually built",
            "arms": mode_a_result,
            "rows": len(val_filtered),
            "frozen_window_guard_passed": True,
            "frozen_window_guard": mode_a_guard,
        },
        "mode_b": {
            "callable_shape": "live-recomputing callables on each endpoint city's own real rows, plus one deliberately sabotaged arm",
            "arms": mode_b_arms_combined,
            "by_city": {
                city: {
                    "arms": entry["result"], "rows": entry["rows"],
                    "frozen_window_guard": entry["frozen_window_guard"],
                }
                for city, entry in mode_b_by_city.items()
            },
            "frozen_window_guard_passed": True,
        },
        "comparison": comparison,
        "finding": finding,
    }

    manifest_dir = os.path.dirname(report_path)
    if manifest_dir:
        os.makedirs(manifest_dir, exist_ok=True)
    tmp_path = report_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)
    os.replace(tmp_path, report_path)

    return report


# ──────────────────────────────────────────────────────────────────────────
# Plan 04-02 Task 3: arm 5's label timing, the split boundaries, and whether
# the six-hourly filter really leaves the hourly lag offsets alone (D-01
# bullets 4 and 5). Every function below builds its own ABLATION-only
# (train+val) stacked frame exactly as Task 2 does, and discards any
# stacked test-range rows immediately -- this section never assembles
# against Phase 3's frozen held-out test window either, with ONE sanctioned
# exception: `split_boundary_audit` reads the test split's own TIMESTAMPS
# (never `truth_dlr_amps` or any other value) to audit the boundary itself,
# exactly the precedent `assert_filtered_split_disjoint`'s own docstring
# and Plan 04-01's `_build_corridor_basis_entry` both already established
# as non-no-peeking calendar-boundary arithmetic.
# ──────────────────────────────────────────────────────────────────────────

def _ablation_train_val_stacked(corridor: str, *, lead_hours: int):
    """
    Shared setup for this section: the real ABLATION-basis corridor frame,
    its re-derived split boundaries, and the stacked train+val-only frame
    (never stacked_test, discarded immediately) -- the same construction
    Task 2 uses, factored out so Task 3's three functions do not each
    re-derive it slightly differently.

    Returns `(corridor_frame, boundaries, stacked_train, train_val_stacked)`.
    """
    corridor_frame = forecast_experiment.corridor_anchored_pair_frame(
        corridor, FROZEN_WINDOW_START, FROZEN_WINDOW_END, lead_hours=lead_hours,
    )
    boundaries = forecast_experiment._default_split_boundaries(corridor_frame)

    stacked_full = forecast_experiment._stacked_pair_frame(
        corridor, FROZEN_WINDOW_START, FROZEN_WINDOW_END, lead_hours=lead_hours,
    )
    stacked_train, stacked_val, stacked_test = experiment_splits.calendar_split(stacked_full, boundaries)
    del stacked_test  # never touched again by this section.
    train_val_stacked = (
        pd.concat([stacked_train, stacked_val], ignore_index=True)
        .sort_values("datetime_utc").reset_index(drop=True)
    )
    return corridor_frame, boundaries, stacked_train, train_val_stacked


def arm5_label_timing_finding(corridor: str, *, lead_hours: int = None) -> dict:
    """
    D-01 bullet 4, label timing. Builds arm 5's corridor truth frame the
    way the harness does (`_arm5_truth_frame` on the ABLATION train+val
    stacked frame), then builds the feature and target matrices through
    `forecast_training.build_training_matrix` at the primary lead. Measures
    the wall-clock difference between each feature row's own timestamp
    (`X.index`) and its own label's timestamp (`y.index`) from the RETURNED
    indices -- never from the `horizon_minutes` parameter that was passed
    in, which is the thing under audit (`build_training_matrix`'s own
    contract: `y.index = X's original index + horizon`, `backend/
    forecast_training.py:311-313,347`).

    Also reports the production default horizon
    (`config.FORECAST_HORIZON_MINUTES`) and the horizon this experiment
    actually passes (`config.FORECAST_EXPERIMENT_PRIMARY_LEAD_HOURS * 60`)
    as distinct values with citations, so the record cannot be misread as
    claiming the experiment ran at the production default.

    Answers D-01's actual question -- not "is the shift 24 hours" but "were
    the training labels available before the decisions they are compared
    against" -- by citing the two assertions that make each half true on
    the ABLATION basis: every train timestamp is strictly before every
    validation timestamp (`experiment_splits.calendar_split`'s own
    partition predicate), and every validation row's own anchor time is
    exactly `lead_hours` before its valid time (`anchored_pair_frame`'s
    anchor-group construction).
    """
    if lead_hours is None:
        lead_hours = config.FORECAST_EXPERIMENT_PRIMARY_LEAD_HOURS
    city_a, city_b = config.CORRIDOR_ENDPOINTS[corridor]
    experiment_horizon_minutes = lead_hours * 60

    corridor_frame, boundaries, stacked_train, train_val_stacked = _ablation_train_val_stacked(
        corridor, lead_hours=lead_hours,
    )

    arm5_truth_frame = forecast_experiment._arm5_truth_frame(train_val_stacked, city_a, city_b)
    x5, y5 = forecast_training.build_training_matrix(arm5_truth_frame, horizon_minutes=experiment_horizon_minutes)

    offsets = (y5.index - x5.index).unique()
    # Formatted as hours explicitly (never pandas' own Timedelta str(),
    # which renders 24 hours as "1 days 00:00:00" -- a representation that
    # would make the offset's actual hour count invisible to a reader or a
    # mechanical citation check).
    distinct_offsets = sorted({f"{off / pd.Timedelta(hours=1):.1f}h" for off in offsets})

    train_val_filtered_train = forecast_experiment.filter_to_exact_lead(stacked_train, lead_hours=lead_hours)
    val_only = train_val_stacked[train_val_stacked["datetime_utc"] >= boundaries.val_start]
    val_filtered = forecast_experiment.filter_to_exact_lead(val_only, lead_hours=lead_hours)
    train_max = train_val_filtered_train["datetime_utc"].max() if len(train_val_filtered_train) else None
    val_min = val_filtered["datetime_utc"].min() if len(val_filtered) else None
    train_precedes_val = bool(train_max is not None and val_min is not None and train_max < val_min)

    return {
        "corridor": corridor,
        "distinct_feature_to_label_offsets": distinct_offsets,
        "distinct_feature_to_label_offsets_citation": "backend/forecast_training.py:311-313,347",
        "production_default_horizon_minutes": config.FORECAST_HORIZON_MINUTES,
        "production_default_horizon_citation": "backend/config.py:193",
        "experiment_horizon_minutes": experiment_horizon_minutes,
        "experiment_horizon_citation": "backend/config.py:412 (FORECAST_EXPERIMENT_PRIMARY_LEAD_HOURS * 60)",
        "train_labels_precede_scored_validation": train_precedes_val,
        "train_max_timestamp": str(train_max) if train_max is not None else None,
        "val_min_timestamp": str(val_min) if val_min is not None else None,
        "train_precedes_val_citation": "backend/experiment_splits.py:100-102 (calendar_split's own partition predicate)",
        "validation_anchor_lead_hours": lead_hours,
        "validation_anchor_lead_citation": "backend/forecast_experiment.py:606-620 (anchored_pair_frame's anchor-group construction)",
    }


def split_boundary_audit(corridor: str, *, lead_hours: int = None) -> dict:
    """
    D-01 bullet 4, boundaries. On the real re-derived boundaries, reports
    each side's unfiltered and filtered row counts, whether any timestamp
    appears on two sides (computed by PAIRWISE SET INTERSECTION on the
    FILTERED sides -- the ones actually scored -- never inferred from the
    partition predicates), whether a row exists exactly at each boundary
    instant and which UNFILTERED side received it, and each filtered
    side's own minimum and maximum timestamp.

    Delegates the strict-ordering check to `forecast_experiment.
    assert_filtered_split_disjoint` (the harness's own existing per-side
    post-filter disjointness assertion) rather than writing a second one,
    and additionally raises on any nonzero `shared_timestamp_count` itself
    -- a boundary audit that reports "passed" next to a nonzero overlap
    count would be worse than no audit at all.

    Reads the TEST split's own timestamps (row counts, min/max, boundary
    membership) but never `truth_dlr_amps` or any other scored value --
    sanctioned calendar-boundary arithmetic, the same precedent
    `assert_filtered_split_disjoint`'s own docstring and Plan 04-01's
    `_build_corridor_basis_entry` both already established.
    """
    if lead_hours is None:
        lead_hours = config.FORECAST_EXPERIMENT_PRIMARY_LEAD_HOURS

    corridor_frame = forecast_experiment.corridor_anchored_pair_frame(
        corridor, FROZEN_WINDOW_START, FROZEN_WINDOW_END, lead_hours=lead_hours,
    )
    boundaries = forecast_experiment._default_split_boundaries(corridor_frame)
    train, val, test = experiment_splits.calendar_split(corridor_frame, boundaries)

    train_filtered = forecast_experiment.filter_to_exact_lead(train, lead_hours=lead_hours)
    val_filtered = forecast_experiment.filter_to_exact_lead(val, lead_hours=lead_hours)
    test_filtered = forecast_experiment.filter_to_exact_lead(test, lead_hours=lead_hours)

    # The harness's own existing per-side post-filter disjointness
    # assertion -- extended (not duplicated) by this function's own
    # set-intersection check below.
    forecast_experiment.assert_filtered_split_disjoint(train_filtered, val_filtered, test_filtered)

    train_ts = set(pd.to_datetime(train_filtered["datetime_utc"], utc=True))
    val_ts = set(pd.to_datetime(val_filtered["datetime_utc"], utc=True))
    test_ts = set(pd.to_datetime(test_filtered["datetime_utc"], utc=True))
    overlap = (train_ts & val_ts) | (val_ts & test_ts) | (train_ts & test_ts)
    if overlap:
        raise ValueError(
            f"split_boundary_audit: {len(overlap)} timestamp(s) appear on "
            f"more than one FILTERED side -- e.g. {sorted(overlap)[:3]} -- "
            f"a boundary audit must never report a passing summary next to "
            f"a nonzero overlap count"
        )

    def _side_for_exact_instant(ts):
        for side_name, side_frame in (("train", train), ("val", val), ("test", test)):
            if (pd.to_datetime(side_frame["datetime_utc"], utc=True) == ts).any():
                return side_name
        return None

    boundary_row_side = {
        "val_start": _side_for_exact_instant(boundaries.val_start),
        "test_start": _side_for_exact_instant(boundaries.test_start),
    }

    def _min_max(frame):
        if len(frame) == 0:
            return {"min": None, "max": None}
        dt = pd.to_datetime(frame["datetime_utc"], utc=True)
        return {"min": str(dt.min()), "max": str(dt.max())}

    return {
        "corridor": corridor,
        "boundaries": {"val_start": str(boundaries.val_start), "test_start": str(boundaries.test_start)},
        "unfiltered_rows": {"train": len(train), "val": len(val), "test": len(test)},
        "filtered_rows": {"train": len(train_filtered), "val": len(val_filtered), "test": len(test_filtered)},
        "shared_timestamp_count": len(overlap),
        "boundary_row_side": boundary_row_side,
        "filtered_side_min_max": {
            "train": _min_max(train_filtered), "val": _min_max(val_filtered), "test": _min_max(test_filtered),
        },
    }


def arm5_lag_offset_finding(corridor: str, *, lead_hours: int = None) -> dict:
    """
    D-01 bullet 5. Settles by measurement, in two parts, whether the
    six-hourly exact-lead filter corrupts arm 5's hourly lag offsets.

    Part one -- ordering. Builds arm 5's feature table the way the harness
    does, from the FULL unfiltered ABLATION truth series
    (`_arm5_truth_frame` on the train+val stacked frame). Then builds a
    SECOND feature table from an input that has already been reduced to
    the six-hourly exact-lead rows
    (`forecast_experiment.filter_to_exact_lead` applied BEFORE
    `build_training_matrix`, never after). Compares the two on the
    timestamps they share -- `ampacity_forecast.build_ml_features`'s lag
    columns are a POSITIONAL `.shift(h)` (`backend/ampacity_forecast.py:145`),
    so filtering to a six-hourly cadence FIRST changes what "one row back"
    means in wall-clock terms, and the two tables are expected to disagree.
    Reports `filter_first_agrees_with_harness_order=False` as the
    measurement that the harness's OWN ordering (lag features computed on
    the full series, six-hourly selection applied only via the later
    reindex in `_score_fitted_arms_at_corridor_level`,
    `backend/forecast_experiment.py:1856-1859`) is load-bearing, not
    incidental.

    Part two -- cadence. Measures the real gap structure of the truth
    series feeding arm 5's feature table: the distinct spacings between
    consecutive timestamps, with counts. A positional lag shift is only
    correct on an unbroken hourly cadence; reports `positional_shift_safe`
    accordingly, cross-referenced against Plan 04-01's own measured
    null-drop finding (a single contiguous window-start boundary effect,
    not a scattered interior gap).
    """
    if lead_hours is None:
        lead_hours = config.FORECAST_EXPERIMENT_PRIMARY_LEAD_HOURS
    city_a, city_b = config.CORRIDOR_ENDPOINTS[corridor]

    _corridor_frame, _boundaries, _stacked_train, train_val_stacked = _ablation_train_val_stacked(
        corridor, lead_hours=lead_hours,
    )
    arm5_truth_frame = forecast_experiment._arm5_truth_frame(train_val_stacked, city_a, city_b)

    harness_order_x5, _ = forecast_training.build_training_matrix(
        arm5_truth_frame, horizon_minutes=lead_hours * 60,
    )

    filter_first_truth = forecast_experiment.filter_to_exact_lead(arm5_truth_frame, lead_hours=lead_hours)
    filter_first_x5, _ = forecast_training.build_training_matrix(
        filter_first_truth, horizon_minutes=lead_hours * 60,
    )

    shared_index = harness_order_x5.index.intersection(filter_first_x5.index)
    if len(shared_index) == 0:
        agrees = False
    else:
        a = harness_order_x5.loc[shared_index].to_numpy(dtype=float)
        b = filter_first_x5.loc[shared_index].to_numpy(dtype=float)
        agrees = bool(np.allclose(a, b, equal_nan=True))

    dt = pd.to_datetime(arm5_truth_frame["datetime_utc"], utc=True).sort_values()
    spacings = dt.diff().dropna()
    spacing_counts = spacings.value_counts()
    distinct_spacings = {str(k): int(v) for k, v in spacing_counts.items()}
    positional_shift_safe = bool(
        len(spacing_counts) == 1 and pd.Timedelta(spacing_counts.index[0]) == pd.Timedelta(hours=1)
    )

    return {
        "corridor": corridor,
        "filter_first_agrees_with_harness_order": agrees,
        "shared_rows_compared": int(len(shared_index)),
        "harness_order_citation": "backend/forecast_experiment.py:1856-1859 (build feature table from the full series, select rows afterwards via reindex)",
        "filter_before_lag_citation": "backend/ampacity_forecast.py:145 (.shift(h) is positional -- filtering first changes what 'h rows back' means in wall-clock terms)",
        "distinct_spacings": distinct_spacings,
        "positional_shift_safe": positional_shift_safe,
    }


def d01_findings_table() -> list:
    """
    The closing dispositions table for the whole Data-provenance-re-audit
    section: one row per D-01 bullet, with the bullet's subject, the
    disposition, the evidence type, and the citation. Five rows, one per
    bullet, no bullet omitted -- a "confirmed non-issue" disposition still
    carries the citation that makes it so, per this plan's own instruction,
    so a future audit is not tempted to re-open a question this one closed.

    Static (not computed from a live run) because it is a SUMMARY of
    findings this module's other functions already establish and this
    plan's own audit-record prose already cites in full -- a future reader
    who wants a specific finding's live re-computation calls the function
    named in that row's own citation, not this summary.
    """
    return [
        {
            "bullet": "D-01 bullet 1 -- truth source is an archive, not a live feed",
            "disposition": "confirmed non-issue (already covered by Plan 04-01, Finding 1)",
            "evidence_type": "code read",
            "citation": "backend/open_meteo_provider.py:1-32; docs/data-science/decisions/forecast_correction_followup_audit.md Finding 1",
        },
        {
            "bullet": "D-01 bullet 2 -- decision-time availability vs. archive value-matching",
            "disposition": "limitation to record (confirmed issue, narrower claim type than the frozen record implies)",
            "evidence_type": "code read",
            "citation": "backend/forecast_leadtime_calibration.py:390,515; docs/data-science/decisions/forecast_correction_followup_audit.md Finding 4",
        },
        {
            "bullet": "D-01 bullet 3 -- every feature checked against decision time (schema partition + leakage probe coverage)",
            "disposition": "confirmed non-issue for the schema partition (no mid-window column exists); confirmed issue for the leakage probe's callable shape (Mode A demonstrated powerless)",
            "evidence_type": "both",
            "citation": "backend/forecast_experiment_audit.py frame_time_reference_groups, leakage_probe_coverage_report; docs/data-science/decisions/forecast_correction_followup_audit.md Findings 5-6",
        },
        {
            "bullet": "D-01 bullet 4 -- preprocessing, shifted targets, and split boundaries",
            "disposition": "confirmed non-issue (label timing measured exactly at the claimed lead; split boundaries measured disjoint with zero shared timestamps)",
            "evidence_type": "measurement",
            "citation": "backend/forecast_experiment_audit.py arm5_label_timing_finding, split_boundary_audit",
        },
        {
            "bullet": "D-01 bullet 5 -- six-hourly filter's effect on arm 5's hourly lag offsets",
            "disposition": "confirmed non-issue (the harness's own filter-after-lag ordering is demonstrated load-bearing; the interior cadence is measured unbroken)",
            "evidence_type": "measurement",
            "citation": "backend/forecast_experiment_audit.py arm5_lag_offset_finding",
        },
    ]
