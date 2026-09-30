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
