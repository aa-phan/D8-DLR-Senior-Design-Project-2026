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

import pandas as pd

import config
import experiment_splits
import forecast_experiment

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
