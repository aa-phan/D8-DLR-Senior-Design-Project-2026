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


def test_render_markdown_one_corridor_one_entry(tmp_path):
    _write_entry(str(tmp_path / "AUSTIN_CORPUS_CHRISTI.jsonl"), {
        "corridor": "AUSTIN_CORPUS_CHRISTI", "method": "ml_wind_corrected",
        "ampacity_amps": 1004.136, "fallback_used": False, "fallback_reason": None,
        "model_version": "ml_wind_corrected_AUSTIN_CORPUS_CHRISTI@2026-10-07T06:51:38+00:00",
        "decision_time": "2026-10-07T06:52:09+00:00", "valid_time": "2026-10-07T18:00:00+00:00",
    })

    markdown = render_table.render_markdown(str(tmp_path))

    assert "## AUSTIN_CORPUS_CHRISTI" in markdown
    assert "1 logged prediction(s)" in markdown
    assert "1004.1" in markdown
    assert "ml_wind_corrected" in markdown
    assert "| 2026-10-07T06:52:09+00:00 | 2026-10-07T18:00:00+00:00 |" in markdown


def test_render_markdown_sorts_most_recent_first(tmp_path):
    path = str(tmp_path / "MIDLAND_EL_PASO.jsonl")
    _write_entry(path, {
        "corridor": "MIDLAND_EL_PASO", "method": "ml_wind_corrected", "ampacity_amps": 100.0,
        "fallback_used": False, "decision_time": "2026-10-07T01:00:00+00:00", "valid_time": "x",
    })
    _write_entry(path, {
        "corridor": "MIDLAND_EL_PASO", "method": "ml_wind_corrected", "ampacity_amps": 200.0,
        "fallback_used": False, "decision_time": "2026-10-07T03:00:00+00:00", "valid_time": "x",
    })
    _write_entry(path, {
        "corridor": "MIDLAND_EL_PASO", "method": "ml_wind_corrected", "ampacity_amps": 150.0,
        "fallback_used": False, "decision_time": "2026-10-07T02:00:00+00:00", "valid_time": "x",
    })

    markdown = render_table.render_markdown(str(tmp_path))

    idx_200 = markdown.index("200.0")
    idx_150 = markdown.index("150.0")
    idx_100 = markdown.index("100.0")
    assert idx_200 < idx_150 < idx_100  # newest (03:00) first, oldest (01:00) last


def test_render_markdown_escapes_pipe_characters_in_fallback_reason(tmp_path):
    _write_entry(str(tmp_path / "AUSTIN_CORPUS_CHRISTI.jsonl"), {
        "corridor": "AUSTIN_CORPUS_CHRISTI", "method": "raw_forecast", "ampacity_amps": 500.0,
        "fallback_used": True,
        "fallback_reason": "provider A failed | provider B also failed",
        "decision_time": "x", "valid_time": "x",
    })

    markdown = render_table.render_markdown(str(tmp_path))

    # An unescaped "|" inside a table cell would corrupt the Markdown
    # table structure (it would be parsed as a new column boundary).
    assert "provider A failed \\| provider B also failed" in markdown


def test_render_markdown_handles_null_model_version_and_ampacity(tmp_path):
    _write_entry(str(tmp_path / "AUSTIN_CORPUS_CHRISTI.jsonl"), {
        "corridor": "AUSTIN_CORPUS_CHRISTI", "method": "raw_forecast", "ampacity_amps": None,
        "fallback_used": True, "model_version": None,
        "fallback_reason": "total failure", "decision_time": "x", "valid_time": "x",
    })

    markdown = render_table.render_markdown(str(tmp_path))

    assert "| — |" in markdown  # the em-dash placeholder, not "None" or a crash


def test_render_markdown_truncates_a_very_long_fallback_reason(tmp_path):
    long_reason = "x" * 500
    _write_entry(str(tmp_path / "AUSTIN_CORPUS_CHRISTI.jsonl"), {
        "corridor": "AUSTIN_CORPUS_CHRISTI", "method": "raw_forecast", "ampacity_amps": 1.0,
        "fallback_used": True, "fallback_reason": long_reason,
        "decision_time": "x", "valid_time": "x",
    })

    markdown = render_table.render_markdown(str(tmp_path))

    assert long_reason not in markdown  # the full 500-char string must not appear verbatim
    assert "x" * 100 in markdown  # but a truncated prefix should


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
