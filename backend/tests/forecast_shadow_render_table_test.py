"""
Tests for `backend/forecast_shadow_render_table.py` -- the Markdown
summary table rendered to the `shadow-collection-data` branch's top-level
README.md. Network-free throughout; this module is never invoked by
production code.
"""
from __future__ import annotations

import json
import os

import forecast_shadow_render_table as render_table


def _write_entry(path: str, entry: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps(entry) + "\n")


def test_render_markdown_with_no_files_reports_nothing_logged_yet(tmp_path):
    markdown = render_table.render_markdown(str(tmp_path))
    assert "No predictions logged yet" in markdown
    # The basis/static-ratings caveats must appear regardless of whether
    # there's any data -- someone opening the branch with zero runs so far
    # should still see the warning, not just an empty page.
    assert "Experimental/shadow prototype" in markdown
    assert "Power Systems sub-team" in markdown


# ──────────────────────────────────────────────────────────────────────
# 2026-10-08 ("why does the readme still have the old table underneath
# the new one -- remove that"): pre-cutover flat-shape entries no longer
# render as their own table (or any per-row content) at all -- only a
# one-line count-and-pointer summary. The detailed-row behaviors these
# tests used to pin (pipe-escaping, null handling, truncation, per-row
# sorting) no longer apply to old-shape data, since no old-shape row
# content is rendered anymore; replaced below with tests pinning the
# summary-line behavior itself.
# ──────────────────────────────────────────────────────────────────────


def test_render_markdown_one_corridor_one_old_shape_entry_shows_count_not_row_detail(tmp_path):
    _write_entry(str(tmp_path / "AUSTIN_CORPUS_CHRISTI.jsonl"), {
        "corridor": "AUSTIN_CORPUS_CHRISTI", "method": "ml_wind_corrected",
        "ampacity_amps": 1004.136, "fallback_used": False, "fallback_reason": None,
        "model_version": "ml_wind_corrected_AUSTIN_CORPUS_CHRISTI@2026-10-07T06:51:38+00:00",
        "decision_time": "2026-10-07T06:52:09+00:00", "valid_time": "2026-10-07T18:00:00+00:00",
    })

    markdown = render_table.render_markdown(str(tmp_path))

    assert "## AUSTIN_CORPUS_CHRISTI" in markdown
    assert "1 logged prediction(s)" in markdown
    assert "1 pre-cutover (single-method) entries" in markdown
    assert "data/shadow/predictions/AUSTIN_CORPUS_CHRISTI.jsonl" in markdown
    # No per-row detail: the specific ampacity value is never rendered.
    assert "1004.1" not in markdown
    assert "2026-10-07T06:52:09+00:00" not in markdown


def test_render_markdown_old_shape_entries_never_render_a_table_at_all(tmp_path):
    """
    Pins the exact bug report ("the old table underneath the new one"):
    even with multiple old-shape entries carrying every field the old
    per-row renderer used to format (pipe characters, null fields, a very
    long fallback_reason), NO pipe-table syntax for them appears anywhere
    in the output -- only the one-line summary.
    """
    path = str(tmp_path / "AUSTIN_CORPUS_CHRISTI.jsonl")
    _write_entry(path, {
        "corridor": "AUSTIN_CORPUS_CHRISTI", "method": "raw_forecast", "ampacity_amps": 500.0,
        "fallback_used": True,
        "fallback_reason": "provider A failed | provider B also failed",
        "decision_time": "2026-10-07T01:00:00+00:00", "valid_time": "x",
    })
    _write_entry(path, {
        "corridor": "AUSTIN_CORPUS_CHRISTI", "method": "raw_forecast", "ampacity_amps": None,
        "fallback_used": True, "model_version": None, "fallback_reason": "x" * 500,
        "decision_time": "2026-10-07T02:00:00+00:00", "valid_time": "x",
    })

    markdown = render_table.render_markdown(str(tmp_path))

    assert "2 pre-cutover (single-method) entries" in markdown
    assert "provider A failed" not in markdown
    assert "x" * 100 not in markdown
    assert "| Method | Fallback?" not in markdown  # the old header row is gone entirely


def test_render_markdown_is_deterministic_for_unchanged_input(tmp_path):
    """
    No dynamic "rendered at" timestamp -- re-rendering the SAME input must
    produce byte-identical output, so the workflow's own `git diff
    --cached --quiet` dedupe (a day with no new predictions produces no
    commit) still works correctly once this file is part of what's
    committed.
    """
    _write_entry(str(tmp_path / "AUSTIN_CORPUS_CHRISTI.jsonl"), {
        "corridor": "AUSTIN_CORPUS_CHRISTI", "method": "ml_wind_corrected", "ampacity_amps": 1.0,
        "fallback_used": False, "decision_time": "x", "valid_time": "x",
    })

    first = render_table.render_markdown(str(tmp_path))
    second = render_table.render_markdown(str(tmp_path))

    assert first == second


def test_main_writes_the_rendered_markdown_to_the_given_output_path(tmp_path, monkeypatch):
    predictions_dir = tmp_path / "predictions"
    _write_entry(str(predictions_dir / "AUSTIN_CORPUS_CHRISTI.jsonl"), {
        "corridor": "AUSTIN_CORPUS_CHRISTI", "method": "ml_wind_corrected", "ampacity_amps": 1.0,
        "fallback_used": False, "decision_time": "x", "valid_time": "x",
    })
    out_path = tmp_path / "README.md"

    monkeypatch.setattr(
        "sys.argv", ["forecast_shadow_render_table.py", str(predictions_dir), str(out_path)]
    )
    assert render_table.main() == 0

    content = out_path.read_text()
    assert "AUSTIN_CORPUS_CHRISTI" in content


# ──────────────────────────────────────────────────────────────────────
# Plan 05-05, Task 1: both shapes forever (05-01's approved schema_version-2
# shape + no-migration-of-historical-rows strategy).
# ──────────────────────────────────────────────────────────────────────

_NEW_SHAPE_CANDIDATE_NAMES = (
    "ml_wind_corrected", "ml_cooling_corrected", "raw_forecast",
    "persistence_24h", "reference_ml_refit_24h",
)


def _new_shape_entry(**overrides) -> dict:
    candidates = {
        "ml_wind_corrected": {
            "status": "ok", "ampacity_amps": 650.0, "fallback_used": False,
            "fallback_reason": None, "model_version": "v2", "input_provenance": None,
            "reason": None,
        },
        "ml_cooling_corrected": {
            "status": "ok", "ampacity_amps": 640.0, "fallback_used": False,
            "fallback_reason": None, "model_version": "v2", "input_provenance": None,
            "reason": None,
        },
        "raw_forecast": {
            "status": "ok", "ampacity_amps": 600.0, "fallback_used": False,
            "fallback_reason": None, "model_version": None, "input_provenance": None,
            "reason": None,
        },
        "persistence_24h": {
            "status": "unavailable", "ampacity_amps": None, "fallback_used": False,
            "fallback_reason": None, "model_version": None, "input_provenance": None,
            "reason": "no prior entry within tolerance of decision_time",
        },
        "reference_ml_refit_24h": {
            "status": "unavailable", "ampacity_amps": None, "fallback_used": False,
            "fallback_reason": None, "model_version": None, "input_provenance": None,
            "reason": "no persisted reference_ml_refit_24h model artifact",
        },
    }
    entry = {
        "schema_version": 2, "corridor": "AUSTIN_CORPUS_CHRISTI",
        "decision_time": "2026-10-07T06:52:09+00:00", "valid_time": "2026-10-07T18:00:00+00:00",
        "logged_at": "2026-10-07T06:52:10+00:00",
        "candidates": candidates,
        "method": "ml_wind_corrected", "ampacity_amps": 650.0, "fallback_used": False,
        "fallback_reason": None, "model_version": "v2", "input_provenance": None,
    }
    entry.update(overrides)
    return entry


def test_render_markdown_old_shape_only_renders_summary_line_not_a_table(tmp_path):
    """
    2026-10-08 ("remove that"): superseded regression pin. The original
    version of this test hand-reconstructed the exact row/table text the
    legacy per-row renderer produced -- that renderer is now removed
    entirely (old-shape rows render a one-line summary, never a table),
    so this test pins the NEW behavior instead.
    """
    path = str(tmp_path / "AUSTIN_CORPUS_CHRISTI.jsonl")
    _write_entry(path, {
        "corridor": "AUSTIN_CORPUS_CHRISTI", "method": "ml_wind_corrected",
        "ampacity_amps": 1004.136, "fallback_used": False, "fallback_reason": None,
        "model_version": "ml_wind_corrected_AUSTIN_CORPUS_CHRISTI@2026-10-07T06:51:38+00:00",
        "decision_time": "2026-10-07T06:52:09+00:00", "valid_time": "2026-10-07T18:00:00+00:00",
    })
    _write_entry(path, {
        "corridor": "AUSTIN_CORPUS_CHRISTI", "method": "raw_forecast", "ampacity_amps": None,
        "fallback_used": True, "fallback_reason": "total failure", "model_version": None,
        "decision_time": "2026-10-07T18:52:09+00:00", "valid_time": "2026-10-08T06:00:00+00:00",
    })

    markdown = render_table.render_markdown(str(tmp_path))

    expected = (
        "## AUSTIN_CORPUS_CHRISTI\n"
        "\n"
        "2 logged prediction(s), most recent first.\n"
        "\n"
        "_2 pre-cutover (single-method) entries exist in this corridor's raw "
        "history and are not rendered here -- see "
        "`data/shadow/predictions/AUSTIN_CORPUS_CHRISTI.jsonl` on this branch "
        "for the full single-candidate record._\n"
        "\n"
    )
    assert expected in markdown
    assert "ml_wind_corrected_AUSTIN_CORPUS_CHRISTI@2026-10-07T06:51:38" not in markdown
    assert "total failure" not in markdown


def test_render_markdown_new_shape_entry_renders_all_five_candidates(tmp_path):
    _write_entry(str(tmp_path / "AUSTIN_CORPUS_CHRISTI.jsonl"), _new_shape_entry())

    markdown = render_table.render_markdown(str(tmp_path))

    for name in _NEW_SHAPE_CANDIDATE_NAMES:
        assert name in markdown
    assert "schema_version: 2" in markdown


def test_render_markdown_new_shape_unavailable_candidate_shows_its_reason(tmp_path):
    _write_entry(str(tmp_path / "AUSTIN_CORPUS_CHRISTI.jsonl"), _new_shape_entry())

    markdown = render_table.render_markdown(str(tmp_path))

    assert "no prior entry within tolerance of decision_time" in markdown
    assert "no persisted reference_ml_refit_24h model artifact" in markdown
    assert "unavailable" in markdown


# ──────────────────────────────────────────────────────────────────────
# 2026-10-08: compact one-row-per-cycle format + RENDERED_CYCLE_CAP
# (replaces the one-sub-section-per-cycle format that grew the README by
# a full multi-line block on every single collection run, forever).
# ──────────────────────────────────────────────────────────────────────


def test_render_markdown_new_shape_renders_one_row_not_a_subsection(tmp_path):
    """
    The compact format must emit exactly one table row per cycle, not the
    old multi-line "### Cycle — ..." sub-section header the prior format
    used -- this is the behavior change this test exists to pin.
    """
    _write_entry(str(tmp_path / "AUSTIN_CORPUS_CHRISTI.jsonl"), _new_shape_entry())

    markdown = render_table.render_markdown(str(tmp_path))

    assert "### Cycle" not in markdown  # the old per-cycle sub-section header is gone
    # One row: all five candidates' own cells appear on the SAME line as
    # the cycle's decision_time, not on five separate lines below it.
    row_lines = [
        line for line in markdown.splitlines()
        if "2026-10-07T06:52:09+00:00" in line and "|" in line
    ]
    assert len(row_lines) == 1, row_lines


def test_render_markdown_new_shape_row_shows_ok_candidates_with_checkmark_ampacity(tmp_path):
    _write_entry(str(tmp_path / "AUSTIN_CORPUS_CHRISTI.jsonl"), _new_shape_entry())

    markdown = render_table.render_markdown(str(tmp_path))

    assert "✓ 650.0" in markdown  # ml_wind_corrected
    assert "✓ 640.0" in markdown  # ml_cooling_corrected
    assert "✓ 600.0" in markdown  # raw_forecast


def test_render_markdown_new_shape_row_shows_unavailable_status_not_a_bare_ampacity(tmp_path):
    _write_entry(str(tmp_path / "AUSTIN_CORPUS_CHRISTI.jsonl"), _new_shape_entry())

    markdown = render_table.render_markdown(str(tmp_path))

    # persistence_24h and reference_ml_refit_24h are unavailable in the
    # fixture -- their own cell must say so, never a bare "—" that could
    # be mistaken for "no data" vs. "this candidate reported a real gap".
    assert "| unavailable |" in markdown


def test_render_markdown_new_shape_notes_column_names_which_candidate_and_why(tmp_path):
    _write_entry(str(tmp_path / "AUSTIN_CORPUS_CHRISTI.jsonl"), _new_shape_entry())

    markdown = render_table.render_markdown(str(tmp_path))

    assert "persistence_24h: no prior entry within tolerance of decision_time" in markdown
    assert "reference_ml_refit_24h: no persisted reference_ml_refit_24h model artifact" in markdown
    # An "ok" candidate must never appear in the Notes aggregate.
    assert "ml_wind_corrected:" not in markdown
    assert "ml_cooling_corrected:" not in markdown
    assert "raw_forecast:" not in markdown


def test_render_markdown_new_shape_caps_rendered_cycles_and_says_so(tmp_path):
    """
    `RENDERED_CYCLE_CAP` + 5 cycles logged -> only the cap's worth render,
    newest first, and the document says how many older ones were omitted
    -- never silently truncated with no indication.
    """
    path = str(tmp_path / "AUSTIN_CORPUS_CHRISTI.jsonl")
    total = render_table.RENDERED_CYCLE_CAP + 5
    for i in range(total):
        _write_entry(path, _new_shape_entry(
            decision_time=f"2026-10-07T{i:02d}:00:00+00:00", valid_time="x",
        ))

    markdown = render_table.render_markdown(str(tmp_path))

    # The oldest 5 decision_times (00..04) must be omitted from the render.
    for i in range(5):
        assert f"2026-10-07T{i:02d}:00:00+00:00" not in markdown
    # The newest RENDERED_CYCLE_CAP must all be present.
    for i in range(5, total):
        assert f"2026-10-07T{i:02d}:00:00+00:00" in markdown
    assert "5 older cycle(s) omitted" in markdown
    assert f"{total} logged prediction(s)" in markdown  # the TOTAL count is never understated


def test_render_markdown_new_shape_under_cap_does_not_print_an_omission_note(tmp_path):
    _write_entry(str(tmp_path / "AUSTIN_CORPUS_CHRISTI.jsonl"), _new_shape_entry())

    markdown = render_table.render_markdown(str(tmp_path))

    assert "omitted" not in markdown


def test_render_markdown_mixed_old_and_new_shape_lines_both_accounted_for_in_one_document(tmp_path):
    """
    The real situation this collector is in from the cutover forward: one
    corridor file with an old-shape line AND a new-shape line. Both must
    render correctly in the same document with no exception -- the old
    one as its one-line summary (2026-10-08: no longer a table), the new
    one as its own compact row.
    """
    path = str(tmp_path / "AUSTIN_CORPUS_CHRISTI.jsonl")
    _write_entry(path, {
        "corridor": "AUSTIN_CORPUS_CHRISTI", "method": "ml_wind_corrected",
        "ampacity_amps": 700.0, "fallback_used": False, "fallback_reason": None,
        "model_version": "v1", "decision_time": "2026-10-06T06:00:00+00:00",
        "valid_time": "2026-10-06T18:00:00+00:00",
    })
    _write_entry(path, _new_shape_entry())

    markdown = render_table.render_markdown(str(tmp_path))

    # Old-shape row accounted for by the one-line summary, never a table.
    assert "1 pre-cutover (single-method) entries" in markdown
    assert "| 2026-10-06T06:00:00+00:00 | 2026-10-06T18:00:00+00:00 | ml_wind_corrected |" not in markdown
    # New-shape block still present with all five candidates.
    for name in _NEW_SHAPE_CANDIDATE_NAMES:
        assert name in markdown
    assert "2 logged prediction(s)" in markdown


# ──────────────────────────────────────────────────────────────────────
# 2026-10-08 ("is the bundled ampacity result being displayed in the
# readme, i don't see it"): the bundle-level companion table.
# ──────────────────────────────────────────────────────────────────────

def _new_shape_entry_with_bundle(**overrides) -> dict:
    """`_new_shape_entry` extended with a real `bundle` dict on each
    candidate -- ml_wind_corrected/ml_cooling_corrected/raw_forecast "ok"
    (a different bottleneck city than the per-conductor one, to prove the
    two identities render independently), persistence_24h/
    reference_ml_refit_24h bundle-unavailable."""
    entry = _new_shape_entry(**overrides)
    ok_bundle = {
        "status": "ok", "endpoint_bundle_ampacity_amps": {"AUSTIN": 1300.0, "CORPUS_CHRISTI": 1250.0},
        "corridor_bundle_ampacity_amps": 1250.0, "bundle_bottleneck_city": "CORPUS_CHRISTI",
        "subconductors_per_phase": {"AUSTIN": 2, "CORPUS_CHRISTI": 2},
        "config_version": "v1-provisional-2026-10-08",
        "rating_basis": "Conductor-based bundle thermal estimate...", "reason": None,
    }
    entry["candidates"]["ml_wind_corrected"]["bundle"] = dict(ok_bundle)
    entry["candidates"]["ml_cooling_corrected"]["bundle"] = dict(ok_bundle)
    entry["candidates"]["raw_forecast"]["bundle"] = dict(ok_bundle)
    entry["candidates"]["persistence_24h"]["bundle"] = {
        "status": "unavailable", "reason": "no matched prior entry this cycle",
        "config_version": "v1-provisional-2026-10-08",
    }
    entry["candidates"]["reference_ml_refit_24h"]["bundle"] = {
        "status": "unavailable",
        "reason": "reference_ml_refit_24h produces only a corridor-level prediction",
        "config_version": "v1-provisional-2026-10-08",
    }
    return entry


def test_render_markdown_shows_bundle_table_when_bundle_data_present(tmp_path):
    _write_entry(str(tmp_path / "AUSTIN_CORPUS_CHRISTI.jsonl"), _new_shape_entry_with_bundle())

    markdown = render_table.render_markdown(str(tmp_path))

    assert "Bundle-level (subconductors-per-phase) ampacity" in markdown
    assert "✓ 1250.0 (CORPUS_CHRISTI)" in markdown  # the bundle bottleneck
    assert "Subconductor-per-phase counts are the Power Systems sub-team's provisional" in markdown


def test_render_markdown_bundle_bottleneck_can_differ_from_per_conductor_row(tmp_path):
    """
    The per-conductor row's own candidate cells show ml_wind_corrected's
    ampacity (650.0, no bottleneck city named at this table's own
    granularity) while the bundle row for the SAME cycle shows
    CORPUS_CHRISTI as the bundle bottleneck -- the two tables' bottleneck
    concepts are visually separate, never conflated into one cell.
    """
    _write_entry(str(tmp_path / "AUSTIN_CORPUS_CHRISTI.jsonl"), _new_shape_entry_with_bundle())

    markdown = render_table.render_markdown(str(tmp_path))

    assert "✓ 650.0" in markdown  # per-conductor ml_wind_corrected cell
    assert "✓ 1250.0 (CORPUS_CHRISTI)" in markdown  # bundle cell, same cycle


def test_render_markdown_bundle_table_notes_column_names_unavailable_candidates(tmp_path):
    _write_entry(str(tmp_path / "AUSTIN_CORPUS_CHRISTI.jsonl"), _new_shape_entry_with_bundle())

    markdown = render_table.render_markdown(str(tmp_path))

    assert "persistence_24h: no matched prior entry this cycle" in markdown
    assert "reference_ml_refit_24h: reference_ml_refit_24h produces only a corridor-level prediction" in markdown


def test_render_markdown_omits_bundle_table_when_no_entry_carries_bundle_data(tmp_path):
    """Entries that predate the bundle feature (no 'bundle' key on any
    candidate) must not produce an empty/useless bundle table."""
    _write_entry(str(tmp_path / "AUSTIN_CORPUS_CHRISTI.jsonl"), _new_shape_entry())  # no bundle key

    markdown = render_table.render_markdown(str(tmp_path))

    assert "Bundle-level" not in markdown
