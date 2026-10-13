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


def test_render_markdown_ignores_a_legacy_corridor_log_and_names_it_in_a_footer(tmp_path):
    """Legacy corridor-era logs (rows keyed by `corridor`) are not rendered
    -- no section, no row detail, never mixed into a city's table -- but a
    single footer line names them so their absence is explicit."""
    _write_entry(str(tmp_path / "AUSTIN_CORPUS_CHRISTI.jsonl"), {
        "corridor": "AUSTIN_CORPUS_CHRISTI", "method": "ml_wind_corrected",
        "ampacity_amps": 1004.136, "fallback_used": False, "fallback_reason": None,
        "model_version": "ml_wind_corrected_AUSTIN_CORPUS_CHRISTI@2026-10-07T06:51:38+00:00",
        "decision_time": "2026-10-07T06:52:09+00:00", "valid_time": "2026-10-07T18:00:00+00:00",
    })

    markdown = render_table.render_markdown(str(tmp_path))

    assert "## AUSTIN_CORPUS_CHRISTI" not in markdown
    assert "Legacy corridor-era logs are not rendered" in markdown
    assert "`AUSTIN_CORPUS_CHRISTI.jsonl`" in markdown
    assert "1004.1" not in markdown
    assert "2026-10-07T06:52:09+00:00" not in markdown


def test_render_markdown_legacy_v2_corridor_log_is_ignored_even_with_candidates(tmp_path):
    entry = _new_shape_entry(schema_version=2, corridor="MIDLAND_EL_PASO")
    entry.pop("city")
    _write_entry(str(tmp_path / "MIDLAND_EL_PASO.jsonl"), entry)

    markdown = render_table.render_markdown(str(tmp_path))

    assert "## MIDLAND_EL_PASO" not in markdown
    assert "✓ 650.0" not in markdown
    assert "`MIDLAND_EL_PASO.jsonl`" in markdown


def test_render_markdown_non_v3_rows_in_a_city_file_are_counted_not_rendered(tmp_path):
    """A flat single-method row (the demo's layout: keyed by `city`, no
    schema_version) in a city's own log is summarized by count only."""
    path = str(tmp_path / "AUSTIN.jsonl")
    _write_entry(path, {
        "city": "AUSTIN", "method": "ml_wind_corrected",
        "ampacity_amps": 1004.136, "fallback_used": False, "fallback_reason": None,
        "model_version": None,
        "decision_time": "2026-10-07T06:52:09+00:00", "valid_time": "2026-10-07T18:00:00+00:00",
    })
    _write_entry(path, _new_shape_entry())

    markdown = render_table.render_markdown(str(tmp_path))

    assert "## AUSTIN" in markdown
    assert "1 logged prediction(s)" in markdown
    assert "1 non-`schema_version: 3` row(s)" in markdown
    assert "1004.1" not in markdown


def test_render_markdown_skips_a_malformed_line_instead_of_crashing(tmp_path):
    path = str(tmp_path / "AUSTIN.jsonl")
    _write_entry(path, _new_shape_entry())
    with open(path, "a") as fh:
        fh.write("{not json\n")
    markdown = render_table.render_markdown(str(tmp_path))
    assert "1 logged prediction(s)" in markdown


def test_render_markdown_latest_summary_has_one_row_per_city_and_never_mixes_legacy(tmp_path):
    for city, amps in (("AUSTIN", 111.0), ("CORPUS_CHRISTI", 222.0), ("MIDLAND", 333.0), ("EL_PASO", 444.0)):
        entry = _new_shape_entry(city=city)
        entry["candidates"]["raw_forecast"]["ampacity_amps"] = amps
        _write_entry(str(tmp_path / f"{city}.jsonl"), entry)
    _write_entry(str(tmp_path / "AUSTIN_CORPUS_CHRISTI.jsonl"), {
        "corridor": "AUSTIN_CORPUS_CHRISTI", "method": "raw_forecast", "ampacity_amps": 999.0,
    })

    markdown = render_table.render_markdown(str(tmp_path))

    summary = markdown.split("## Latest cycle per city")[1].split("\n## ")[0]
    rows = [ln for ln in summary.splitlines() if ln.startswith("| ") and "---" not in ln and "City" not in ln]
    assert len(rows) == 4
    for city, amps in (("AUSTIN", 111.0), ("CORPUS_CHRISTI", 222.0), ("MIDLAND", 333.0), ("EL_PASO", 444.0)):
        assert any(ln.startswith(f"| {city} |") and f"✓ {amps:.1f}" in ln for ln in rows)
    assert "999.0" not in markdown
    # One section per city, in file-name order.
    for city in ("AUSTIN", "CORPUS_CHRISTI", "MIDLAND", "EL_PASO"):
        assert f"\n## {city}\n" in markdown


# ──────────────────────────────────────────────────────────────────────
# Plan 05-05, Task 1: both shapes forever (05-01's approved schema_version-3
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
        "schema_version": 3, "city": "AUSTIN",
        "decision_time": "2026-10-07T06:52:09+00:00", "valid_time": "2026-10-07T18:00:00+00:00",
        "logged_at": "2026-10-07T06:52:10+00:00",
        "candidates": candidates,
        "method": "ml_wind_corrected", "ampacity_amps": 650.0, "fallback_used": False,
        "fallback_reason": None, "model_version": "v2", "input_provenance": None,
    }
    entry.update(overrides)
    return entry


def test_render_markdown_non_v3_only_city_file_renders_summary_line_not_a_table(tmp_path):
    """
    2026-10-08 ("remove that"), per city since 2026-10-12: non-v3 rows
    (flat single-method rows keyed by `city`) render a one-line count,
    never a table.
    """
    path = str(tmp_path / "AUSTIN.jsonl")
    _write_entry(path, {
        "city": "AUSTIN", "method": "ml_wind_corrected",
        "ampacity_amps": 1004.136, "fallback_used": False, "fallback_reason": None,
        "model_version": "ml_wind_corrected_AUSTIN@2026-10-07T06:51:38+00:00",
        "decision_time": "2026-10-07T06:52:09+00:00", "valid_time": "2026-10-07T18:00:00+00:00",
    })
    _write_entry(path, {
        "city": "AUSTIN", "method": "raw_forecast", "ampacity_amps": None,
        "fallback_used": True, "fallback_reason": "total failure", "model_version": None,
        "decision_time": "2026-10-07T18:52:09+00:00", "valid_time": "2026-10-08T06:00:00+00:00",
    })

    markdown = render_table.render_markdown(str(tmp_path))

    expected = (
        "## AUSTIN\n"
        "\n"
        "0 logged prediction(s), most recent first.\n"
        "\n"
        "_2 non-`schema_version: 3` row(s) in this city's raw log are not rendered here "
        "-- see `data/shadow/predictions/AUSTIN.jsonl` on this branch._\n"
        "\n"
    )
    assert expected in markdown
    assert "ml_wind_corrected_AUSTIN@2026-10-07T06:51:38" not in markdown
    assert "total failure" not in markdown
    assert "## Latest cycle per city" not in markdown  # no v3 row to summarize


def test_render_markdown_new_shape_entry_renders_all_five_candidates(tmp_path):
    _write_entry(str(tmp_path / "AUSTIN.jsonl"), _new_shape_entry())

    markdown = render_table.render_markdown(str(tmp_path))

    for name in _NEW_SHAPE_CANDIDATE_NAMES:
        assert name in markdown
    assert "schema_version: 3" in markdown


def test_render_markdown_new_shape_unavailable_candidate_shows_its_reason(tmp_path):
    _write_entry(str(tmp_path / "AUSTIN.jsonl"), _new_shape_entry())

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
    _write_entry(str(tmp_path / "AUSTIN.jsonl"), _new_shape_entry())

    markdown = render_table.render_markdown(str(tmp_path))

    assert "### Cycle" not in markdown  # the old per-cycle sub-section header is gone
    # One row: all five candidates' own cells appear on the SAME line as
    # the cycle's decision_time, not on five separate lines below it.
    formatted = render_table._format_timestamp("2026-10-07T06:52:09+00:00")
    row_lines = [
        line for line in markdown.splitlines()
        if line.startswith(f"| {formatted}")
    ]
    assert len(row_lines) == 1, row_lines


def test_render_markdown_new_shape_row_shows_ok_candidates_with_checkmark_ampacity(tmp_path):
    _write_entry(str(tmp_path / "AUSTIN.jsonl"), _new_shape_entry())

    markdown = render_table.render_markdown(str(tmp_path))

    assert "✓ 650.0" in markdown  # ml_wind_corrected
    assert "✓ 640.0" in markdown  # ml_cooling_corrected
    assert "✓ 600.0" in markdown  # raw_forecast


def test_render_markdown_new_shape_row_shows_unavailable_status_not_a_bare_ampacity(tmp_path):
    _write_entry(str(tmp_path / "AUSTIN.jsonl"), _new_shape_entry())

    markdown = render_table.render_markdown(str(tmp_path))

    # persistence_24h and reference_ml_refit_24h are unavailable in the
    # fixture -- their own cell must say so, never a bare "—" that could
    # be mistaken for "no data" vs. "this candidate reported a real gap".
    assert "| unavailable |" in markdown


def test_render_markdown_new_shape_notes_column_names_which_candidate_and_why(tmp_path):
    _write_entry(str(tmp_path / "AUSTIN.jsonl"), _new_shape_entry())

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
    path = str(tmp_path / "AUSTIN.jsonl")
    total = render_table.RENDERED_CYCLE_CAP + 5
    for i in range(total):
        _write_entry(path, _new_shape_entry(
            decision_time=f"2026-10-07T{i:02d}:00:00+00:00", valid_time="x",
        ))

    markdown = render_table.render_markdown(str(tmp_path))

    # The oldest 5 decision_times (00..04) must be omitted from the render.
    for i in range(5):
        formatted = render_table._format_timestamp(f"2026-10-07T{i:02d}:00:00+00:00")
        assert formatted not in markdown
    # The newest RENDERED_CYCLE_CAP must all be present. i=24 would be an
    # invalid hour ("24:00:00") -- _format_timestamp's own fallback path
    # returns such a string unparsed/unchanged, so the raw literal is the
    # correct thing to check for at that one value, same as every other.
    for i in range(5, total):
        formatted = render_table._format_timestamp(f"2026-10-07T{i:02d}:00:00+00:00")
        assert formatted in markdown
    assert "5 older cycle(s) omitted" in markdown
    assert f"{total} logged prediction(s)" in markdown  # the TOTAL count is never understated


def test_render_markdown_new_shape_under_cap_does_not_print_an_omission_note(tmp_path):
    _write_entry(str(tmp_path / "AUSTIN.jsonl"), _new_shape_entry())

    markdown = render_table.render_markdown(str(tmp_path))

    assert "omitted" not in markdown


def test_render_markdown_mixed_old_and_new_shape_lines_both_accounted_for_in_one_document(tmp_path):
    """
    One city file with a non-v3 (flat) line AND a v3 line. Both must be
    accounted for in the same document with no exception -- the flat one
    as a one-line count, the v3 one as its own compact row.
    """
    path = str(tmp_path / "AUSTIN.jsonl")
    _write_entry(path, {
        "city": "AUSTIN", "method": "ml_wind_corrected",
        "ampacity_amps": 700.0, "fallback_used": False, "fallback_reason": None,
        "model_version": "v1", "decision_time": "2026-10-06T06:00:00+00:00",
        "valid_time": "2026-10-06T18:00:00+00:00",
    })
    _write_entry(path, _new_shape_entry())

    markdown = render_table.render_markdown(str(tmp_path))

    assert "1 non-`schema_version: 3` row(s)" in markdown
    assert "| 2026-10-06T06:00:00+00:00 | 2026-10-06T18:00:00+00:00 | ml_wind_corrected |" not in markdown
    for name in _NEW_SHAPE_CANDIDATE_NAMES:
        assert name in markdown
    assert "1 logged prediction(s)" in markdown


# ──────────────────────────────────────────────────────────────────────
# 2026-10-08 ("is the bundled ampacity result being displayed in the
# readme, i don't see it"): the bundle-level companion table.
# ──────────────────────────────────────────────────────────────────────

def _new_shape_entry_with_bundle(**overrides) -> dict:
    """`_new_shape_entry` extended with a real `bundle` dict on each
    candidate -- ml_wind_corrected/ml_cooling_corrected/raw_forecast "ok"
    (bundle = this city's own value times its subconductor count),
    persistence_24h/reference_ml_refit_24h bundle-unavailable."""
    entry = _new_shape_entry(**overrides)
    ok_bundle = {
        "status": "ok", "bundle_ampacity_amps": 1300.0,
        "subconductors_per_phase": 2,
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
    _write_entry(str(tmp_path / "AUSTIN.jsonl"), _new_shape_entry_with_bundle())

    markdown = render_table.render_markdown(str(tmp_path))

    assert "Bundle-level (subconductors-per-phase) ampacity" in markdown
    assert "✓ 1300.0" in markdown
    assert "(AUSTIN)" not in markdown  # no bottleneck-city suffix in a per-city log
    assert "Subconductor-per-phase counts are the Power Systems sub-team's provisional" in markdown


def test_render_markdown_bundle_row_is_separate_from_the_per_conductor_row(tmp_path):
    """The per-conductor row shows ml_wind_corrected's ampacity (650.0) and
    the bundle row for the SAME cycle shows the bundle value (1300.0) --
    two separate tables, never one cell."""
    _write_entry(str(tmp_path / "AUSTIN.jsonl"), _new_shape_entry_with_bundle())

    markdown = render_table.render_markdown(str(tmp_path))

    assert "✓ 650.0" in markdown  # per-conductor ml_wind_corrected cell
    assert "✓ 1300.0" in markdown  # bundle cell, same cycle


def test_render_markdown_bundle_table_notes_column_names_unavailable_candidates(tmp_path):
    _write_entry(str(tmp_path / "AUSTIN.jsonl"), _new_shape_entry_with_bundle())

    markdown = render_table.render_markdown(str(tmp_path))

    assert "persistence_24h: no matched prior entry this cycle" in markdown
    assert "reference_ml_refit_24h: reference_ml_refit_24h produces only a corridor-level prediction" in markdown


def test_render_markdown_omits_bundle_table_when_no_entry_carries_bundle_data(tmp_path):
    """Entries that predate the bundle feature (no 'bundle' key on any
    candidate) must not produce an empty/useless bundle table."""
    _write_entry(str(tmp_path / "AUSTIN.jsonl"), _new_shape_entry())  # no bundle key

    markdown = render_table.render_markdown(str(tmp_path))

    assert "Bundle-level" not in markdown


def test_render_markdown_main_table_never_shows_a_bottleneck_city_suffix(tmp_path):
    """Per-city logs have no bottleneck: even a (corridor-era shaped)
    provenance naming one must not produce a "(CITY)" suffix, and anchor
    provenance renders nowhere in the cell."""
    entry = _new_shape_entry()
    entry["candidates"]["ml_wind_corrected"]["input_provenance"] = {
        "bottleneck_city": "AUSTIN",
        "anchor_provenance": {"anchor_source": "tceq", "anchor_station": "X"},
    }
    _write_entry(str(tmp_path / "AUSTIN.jsonl"), entry)

    markdown = render_table.render_markdown(str(tmp_path))

    assert "✓ 650.0 (" not in markdown
    assert "✓ 650.0" in markdown


def test_render_markdown_main_table_omits_city_suffix_when_no_bottleneck_known(tmp_path):
    """reference_ml_refit_24h (and any candidate with no per-city
    provenance) must render a bare ampacity, never a stray "(None)"."""
    _write_entry(str(tmp_path / "AUSTIN.jsonl"), _new_shape_entry())

    markdown = render_table.render_markdown(str(tmp_path))

    assert "✓ 650.0 (" not in markdown  # ml_wind_corrected's own fixture has no provenance
    assert "(None)" not in markdown


# ──────────────────────────────────────────────────────────────────────
# 2026-10-08 ("UTC is hard to interpret quickly" / "document that
# explanation ... at the top of the readme"): timestamp formatting and
# the methods-taxonomy explanation block.
# ──────────────────────────────────────────────────────────────────────


def test_format_timestamp_shows_utc_and_local_same_calendar_date():
    # 06:52 UTC on Oct 7 2026 (CDT, UTC-5) -> 01:52 local, same date.
    result = render_table._format_timestamp("2026-10-07T06:52:09.123456+00:00")

    assert result == "2026-10-07 06:52 UTC (01:52 CDT)"


def test_format_timestamp_shows_local_date_when_it_differs_from_utc():
    # 02:00 UTC -> 21:00 CDT the PREVIOUS calendar day.
    result = render_table._format_timestamp("2026-10-08T02:00:00+00:00")

    assert result == "2026-10-08 02:00 UTC (2026-10-07 21:00 CDT)"


def test_format_timestamp_drops_seconds_and_microseconds():
    result = render_table._format_timestamp("2026-10-07T06:52:09.992257+00:00")

    assert ":09" not in result
    assert "992257" not in result


def test_format_timestamp_returns_empty_string_for_falsy_input():
    assert render_table._format_timestamp(None) == ""
    assert render_table._format_timestamp("") == ""


def test_format_timestamp_returns_unparseable_input_unchanged():
    assert render_table._format_timestamp("x") == "x"
    assert render_table._format_timestamp("not-a-timestamp") == "not-a-timestamp"


def test_render_markdown_includes_methods_explanation_once_at_the_top_with_no_data(tmp_path):
    markdown = render_table.render_markdown(str(tmp_path))

    assert markdown.count("What the five candidates actually do") == 1
    assert "Open-Meteo's own independent NWP model" in markdown
    assert "no sensor-measured ground truth anywhere" in markdown
    # Appears before the "no predictions logged yet" placeholder -- i.e.
    # unconditionally in the header, never skipped on an empty directory.
    assert markdown.index("What the five candidates actually do") < markdown.index(
        "No predictions logged yet"
    )


def test_render_markdown_includes_methods_explanation_once_with_real_data(tmp_path):
    """Pins that the explanation renders exactly once regardless of how
    many corridors/entries exist -- never once per corridor."""
    _write_entry(str(tmp_path / "AUSTIN.jsonl"), _new_shape_entry())
    _write_entry(str(tmp_path / "MIDLAND.jsonl"), _new_shape_entry(city="MIDLAND"))

    markdown = render_table.render_markdown(str(tmp_path))

    assert markdown.count("What the five candidates actually do") == 1
    assert markdown.index("What the five candidates actually do") < markdown.index("## AUSTIN")


# 2026-10-13 (V5/decision 11B): each row shows the NWP model that produced it.

def test_render_shows_the_nwp_tag_and_treats_a_missing_field_as_ecmwf_ifs(tmp_path):
    path = str(tmp_path / "AUSTIN.jsonl")
    legacy = _new_shape_entry(decision_time="2026-10-12T12:00:00+00:00")
    legacy.pop("forecast_model", None)
    new = _new_shape_entry(decision_time="2026-10-13T12:00:00+00:00", forecast_model="gfs_seamless")
    _write_entry(path, legacy)
    _write_entry(path, new)
    markdown = render_table.render_markdown(str(tmp_path))
    assert "| NWP model |" in markdown
    assert "| ecmwf_ifs |" in markdown
    assert "| gfs_seamless |" in markdown
    assert "must not be pooled" in markdown  # mixed-model caution line
    assert render_table._entry_forecast_model(legacy) == "ecmwf_ifs"


def test_render_single_model_city_has_no_mixed_model_note(tmp_path):
    path = str(tmp_path / "AUSTIN.jsonl")
    _write_entry(path, _new_shape_entry(forecast_model="gfs_seamless"))
    markdown = render_table.render_markdown(str(tmp_path))
    assert "| gfs_seamless |" in markdown
    assert "must not be pooled" not in markdown


def test_render_keeps_the_five_row_cap_with_the_tag_column(tmp_path):
    path = str(tmp_path / "AUSTIN.jsonl")
    for i in range(8):
        _write_entry(path, _new_shape_entry(decision_time=f"2026-10-13T{i:02d}:00:00+00:00", forecast_model="gfs_seamless"))
    markdown = render_table.render_markdown(str(tmp_path))
    assert "most recent 5 of 8 shown" in markdown
