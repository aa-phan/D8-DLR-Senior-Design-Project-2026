"""
Renders a human-readable Markdown summary table from the shadow
collector's JSONL prediction logs (2026-10-07, "a way to pull the data
into a table that gets updated after the action triggers").

Written to the TOP LEVEL of the `shadow-collection-data` branch as
`README.md` -- GitHub renders a branch's root `README.md` automatically,
so switching to that branch shows this table immediately, without
opening the raw JSONL files. Only ever invoked by
`.github/workflows/shadow_collect.yml`'s own commit step, against that
branch's own clone directory -- never against this repo's `main`
working tree, and never by `dlr_pipeline.py` or any other production
caller (same inertness discipline as the rest of this shadow prototype).

Deterministic given the same input files: this module adds no dynamic
timestamp of its own, so a run that logs nothing new (e.g. an identical
fallback twice in a row) regenerates byte-identical Markdown -- `git
diff --cached --quiet` in the workflow still correctly detects "no
change" and skips the commit, exactly as it already does for the
underlying JSONL files.
"""
from __future__ import annotations

import glob
import json
import os
import sys

# Mirrors `forecast_shadow_pipeline.CANDIDATE_METHOD_NAMES` (05-02's D-01
# order, 05-01-SUMMARY.md's approved schema_version-2 shape) -- duplicated
# here rather than imported, so this pure-function, network-free render
# script stays dependency-light. `forecast_shadow_pipeline.py` pulls in
# pandas/scikit-learn/dotenv for its own live-prediction machinery, none of
# which this renderer needs. If the five-candidate roster ever changes,
# update both tuples together.
CANDIDATE_METHOD_NAMES: tuple[str, ...] = (
    "ml_wind_corrected", "ml_cooling_corrected", "raw_forecast",
    "persistence_24h", "reference_ml_refit_24h",
)

# RENDERED_CYCLE_CAP (2026-10-08, "the new render format is messy, it'll
# add a new table after every run"): the number of most-recent
# schema_version>=2 cycles rendered per corridor. The one-block-per-cycle
# format this replaced grew the README by a full multi-line sub-table on
# every single collection run with no limit, forever. This caps the
# RENDERED view only -- every cycle beyond the cap is still in the raw
# `data/shadow/predictions/<corridor>.jsonl` on `shadow-collection-data`,
# untouched and un-pruned; nothing is deleted, only what this specific
# README shows is bounded. Pre-cutover (flat-shape) rows are never capped
# -- that stream is finite and stopped growing at the cutover, per 05-01's
# approved "no migration" strategy, so there is nothing to bound there.
RENDERED_CYCLE_CAP = 20

# Flagged explicitly (2026-10-07, "verify the static rating is realistic
# first"): the per-city STATIC_RATINGS values are this project's own
# unverified placeholder -- the arithmetic midpoint of a *range* given in
# `Project Definition.md`'s I/O spec table, explicitly labeled by the
# data-science team's own `C1-configuration.md` spec as "derived-from-spec
# rather than independently sourced," and never confirmed by the Power
# Systems sub-team (checked directly: no document in this repo -- System
# Design Report, Prior Art Report, pss_e_handoff.md, C6-grid-load-
# integration.md -- supplies an independently-sourced static rating).
STATIC_RATINGS_CAVEAT = (
    "Static ratings are this project's own unverified placeholder (the midpoint of a *range* "
    "given in `Project Definition.md`'s I/O spec table) -- explicitly flagged by the "
    "data-science team's own `C1-configuration.md` spec as \"derived-from-spec rather than "
    "independently sourced,\" and never confirmed by the Power Systems sub-team. Do not treat a "
    "predicted ampacity below this number as a safety violation without that context."
)

BASIS_CAVEAT = (
    "**Experimental/shadow prototype. Not field-validated operational safety data.** Every "
    "number here is a reanalysis-derived development comparison per this phase's own basis "
    "caveat -- see `docs/data-science/decisions/forecast_correction_followup_audit.md` on "
    "`main` for the full technical record."
)


def _load_entries(path: str) -> list[dict]:
    entries = []
    if not os.path.exists(path):
        return entries
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def _escape_note(text, limit: int = 100) -> str:
    """
    Shared table-cell-escaping discipline (pipe/newline escaping, 100-char
    truncation) -- applied identically to the old shape's `fallback_reason`
    and the new shape's per-candidate `reason`/`fallback_reason` fields, so
    neither a multi-line nor a pipe-containing string can corrupt a Markdown
    table's column structure.
    """
    note = (text or "").replace("|", "\\|").replace("\n", " ")
    if len(note) > limit:
        note = note[:limit] + "…"
    return note


def _render_candidate_cell(c: dict) -> str:
    """
    One cell's worth of one candidate's outcome for the compact one-
    row-per-cycle table: a checkmark-prefixed ampacity when it produced a
    real value, or a short status word when it did not. Never embeds the
    candidate's own `reason`/`fallback_reason` text here -- those are
    long, free-form strings that would blow out a 5-candidate-wide row;
    `_render_new_shape_row` collects them into one trailing Notes column
    instead, per status, not per cell.
    """
    status = c.get("status") or "—"
    ampacity = c.get("ampacity_amps")
    if status == "ok" and isinstance(ampacity, (int, float)):
        return f"✓ {ampacity:.1f}"
    return status  # "unavailable" / "failed" / "—" -- never a bare ampacity without its status


def _render_new_shape_row(e: dict) -> str:
    """
    Renders one schema_version>=2 cycle as ONE table row (2026-10-08, per
    the user's own "compact one-row-per-cycle" direction, replacing the
    original one-sub-section-per-cycle format that grew the README by a
    full multi-line block on every single run forever). One column per
    candidate (`_render_candidate_cell`), plus a trailing Notes column
    that aggregates every non-"ok" candidate's own `reason` (preferred)
    or `fallback_reason`, name-prefixed and semicolon-joined, so a reader
    can still see WHY a candidate was unavailable/failed without the
    per-candidate detail sub-tables the old format used.
    """
    candidates = e.get("candidates") or {}
    cells = [_render_candidate_cell(candidates.get(name) or {}) for name in CANDIDATE_METHOD_NAMES]
    notes_parts = []
    for name in CANDIDATE_METHOD_NAMES:
        c = candidates.get(name) or {}
        if c.get("status") == "ok":
            continue
        reason = c.get("reason") or c.get("fallback_reason")
        if reason:
            notes_parts.append(f"{name}: {reason}")
    notes = _escape_note("; ".join(notes_parts), limit=200)
    return (
        f"| {e.get('decision_time', '')} | {e.get('valid_time', '')} | " +
        " | ".join(cells) +
        f" | {notes} |"
    )


# 2026-10-08 ("is the bundled ampacity result being displayed in the
# readme, i don't see it"): duplicated verbatim from `config.
# BUNDLE_RATING_BASIS` rather than imported, same dependency-light
# discipline `BASIS_CAVEAT`/`STATIC_RATINGS_CAVEAT` above already follow
# (this module stays importable without pandas/scikit-learn/dotenv).
BUNDLE_RATING_BASIS_CAVEAT = (
    "Conductor-based bundle thermal estimate (equal-current-sharing assumption across "
    "subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase "
    "counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed "
    "for any specific line segment."
)


def _render_bundle_cell(c: dict) -> str:
    """
    One candidate's bundle outcome for the bundle table -- a checkmark-
    prefixed `corridor_bundle_ampacity_amps` with its OWN
    `bundle_bottleneck_city` in parentheses (deliberately named
    separately from whatever the per-conductor table's own bottleneck
    was -- the two can differ, per the mixed-count case this feature
    exists to surface), or the bundle's own status word when
    unavailable.
    """
    bundle = c.get("bundle") or {}
    status = bundle.get("status") or "—"
    if status == "ok":
        amps = bundle.get("corridor_bundle_ampacity_amps")
        city = bundle.get("bundle_bottleneck_city") or "?"
        if isinstance(amps, (int, float)):
            return f"✓ {amps:.1f} ({city})"
    return status


def _render_bundle_row(e: dict) -> str:
    """
    One cycle's bundle-level row -- same shape as `_render_new_shape_row`
    (one cell per candidate, a trailing aggregated Notes column for any
    non-"ok" bundle), rendered as its OWN table rather than extra columns
    on the per-conductor table, so the two bottleneck identities (per-
    conductor vs. bundle) and the two rating bases stay visually distinct
    rather than cramped into one already-wide row.
    """
    candidates = e.get("candidates") or {}
    cells = [_render_bundle_cell(candidates.get(name) or {}) for name in CANDIDATE_METHOD_NAMES]
    notes_parts = []
    for name in CANDIDATE_METHOD_NAMES:
        bundle = (candidates.get(name) or {}).get("bundle") or {}
        if bundle.get("status") == "ok":
            continue
        reason = bundle.get("reason")
        if reason:
            notes_parts.append(f"{name}: {reason}")
    notes = _escape_note("; ".join(notes_parts), limit=200)
    return (
        f"| {e.get('decision_time', '')} | {e.get('valid_time', '')} | " +
        " | ".join(cells) +
        f" | {notes} |"
    )


def _render_bundle_table(entries: list[dict]) -> list[str]:
    """
    The bundle-level companion to `_render_new_shape_table` -- same cap
    (`RENDERED_CYCLE_CAP`), same cycles (the caller passes the identical
    `entries` list), rendered as a SEPARATE table immediately below the
    per-conductor one. Returns `[]` when no entry in `entries` carries a
    `bundle` key at all (e.g. every entry predates this feature) -- never
    an empty/useless table.
    """
    if not entries:
        return []
    has_any_bundle = any(
        isinstance((c or {}).get("bundle"), dict)
        for e in entries for c in (e.get("candidates") or {}).values()
    )
    if not has_any_bundle:
        return []

    shown = entries[:RENDERED_CYCLE_CAP]
    header_cells = " | ".join(CANDIDATE_METHOD_NAMES)
    block = [
        f"> {BUNDLE_RATING_BASIS_CAVEAT}",
        "",
        "Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent "
        f"{len(shown)} of {len(entries)} shown:",
        "",
        f"| Decision time (UTC) | Valid time (UTC) | {header_cells} | Notes |",
        "|---|---|" + "---|" * len(CANDIDATE_METHOD_NAMES) + "---|",
    ]
    block.extend(_render_bundle_row(e) for e in shown)
    block.append("")
    return block


def _render_new_shape_table(entries: list[dict]) -> list[str]:
    """
    Renders every schema_version>=2 entry for one corridor as ONE compact
    table, most-recent-first, capped to `RENDERED_CYCLE_CAP` rows. Caller
    passes already-sorted, already-filtered (schema_version>=2) entries
    for a single corridor; this function owns only the cap and the table
    shape, not the sort/filter.
    """
    if not entries:
        return []
    shown = entries[:RENDERED_CYCLE_CAP]
    header_cells = " | ".join(CANDIDATE_METHOD_NAMES)
    block = [
        "All five candidates per cycle (`schema_version: 2`), most recent "
        f"{len(shown)} of {len(entries)} shown:",
        "",
        f"| Decision time (UTC) | Valid time (UTC) | {header_cells} | Notes |",
        "|---|---|" + "---|" * len(CANDIDATE_METHOD_NAMES) + "---|",
    ]
    block.extend(_render_new_shape_row(e) for e in shown)
    if len(entries) > RENDERED_CYCLE_CAP:
        block.append("")
        block.append(
            f"_{len(entries) - RENDERED_CYCLE_CAP} older cycle(s) omitted from this "
            "render -- still present, unpruned, in the raw "
            "`data/shadow/predictions/<corridor>.jsonl` file._"
        )
    block.append("")
    return block


def render_markdown(predictions_dir: str) -> str:
    """
    Pure function: `predictions_dir` (a directory of `<corridor>.jsonl`
    files, the shape `forecast_shadow_pipeline.log_prediction`/
    `log_cycle_predictions` writes) in, a complete Markdown document out.
    One section per corridor, most recent first.

    Each logged line is grouped by its OWN shape (`entry.get(
    "schema_version", 1) >= 2`). schema_version>=2 entries render as ONE
    compact one-row-per-cycle table, capped to the most recent
    `RENDERED_CYCLE_CAP` cycles (2026-10-08 -- the original
    one-sub-section-per-cycle format grew the README by a full block on
    every run forever). 2026-10-08 (second pass, "remove that" -- the
    rendered view no longer shows pre-cutover flat-shape rows as a table
    at all): those rows are summarized in a single one-line count instead
    -- they are NEVER deleted or migrated from the raw JSONL (05-01's own
    approved "no migration" strategy), only no longer rendered as their
    own table underneath the new one.
    """
    lines = [
        "# Shadow Collection — Live Predictions",
        "",
        BASIS_CAVEAT,
        "",
        f"> {STATIC_RATINGS_CAVEAT}",
        "",
        "Regenerated automatically after every `shadow_collect.yml` run — do not hand-edit.",
        "",
    ]
    paths = sorted(glob.glob(os.path.join(predictions_dir, "*.jsonl")))
    if not paths:
        lines.append("_No predictions logged yet._")
        return "\n".join(lines) + "\n"

    for path in paths:
        corridor = os.path.splitext(os.path.basename(path))[0]
        entries = _load_entries(path)
        entries.sort(key=lambda e: e.get("decision_time", ""), reverse=True)
        lines.append(f"## {corridor}")
        lines.append("")
        lines.append(f"{len(entries)} logged prediction(s), most recent first.")
        lines.append("")

        new_entries = [e for e in entries if e.get("schema_version", 1) >= 2]
        old_entries = [e for e in entries if e.get("schema_version", 1) < 2]

        lines.extend(_render_new_shape_table(new_entries))
        lines.extend(_render_bundle_table(new_entries))

        if old_entries:
            # 2026-10-08 ("why does the readme still have the old table
            # underneath the new one -- remove that"): pre-cutover
            # flat-shape rows are no longer rendered as their own table at
            # all. They are NOT deleted or migrated (05-01's own approved
            # strategy) -- still fully present, untouched, in the raw
            # `<corridor>.jsonl` on `shadow-collection-data` -- only the
            # RENDERED view stops showing them, exactly like
            # `RENDERED_CYCLE_CAP`'s own "older cycles omitted" note above.
            lines.append(
                f"_{len(old_entries)} pre-cutover (single-method) entries exist in "
                "this corridor's raw history and are not rendered here -- see "
                f"`data/shadow/predictions/{corridor}.jsonl` on this branch for "
                "the full single-candidate record._"
            )
            lines.append("")
        lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    predictions_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join("data", "shadow", "predictions")
    out_path = sys.argv[2] if len(sys.argv) > 2 else "README.md"
    markdown = render_markdown(predictions_dir)
    with open(out_path, "w") as fh:
        fh.write(markdown)
    print(f"forecast_shadow_render_table: wrote {out_path} ({len(markdown)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
