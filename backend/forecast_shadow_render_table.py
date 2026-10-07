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


def _render_legacy_row(e: dict) -> str:
    """
    The EXACT, unchanged single-row rendering for a pre-cutover (no
    `schema_version`, or `schema_version < 2`) flat-shape entry -- byte-
    identical to this function's behavior before the schema_version-2
    branch below existed, per 05-01-SUMMARY.md's "no migration of
    historical rows" approved strategy: old rows render forever, exactly
    as they always have.
    """
    fallback = "Yes" if e.get("fallback_used") else "No"
    note = _escape_note(e.get("fallback_reason"))
    model_version = e.get("model_version") or "—"
    ampacity = e.get("ampacity_amps")
    ampacity_str = f"{ampacity:.1f}" if isinstance(ampacity, (int, float)) else "—"
    return (
        f"| {e.get('decision_time', '')} | {e.get('valid_time', '')} | "
        f"{e.get('method', '')} | {fallback} | {ampacity_str} | "
        f"{model_version} | {note} |"
    )


def _render_new_shape_block(e: dict) -> list[str]:
    """
    Renders one schema_version>=2 cycle's all-five-candidates record as its
    own sub-section with a dedicated per-candidate table -- a reader can
    tell, per cycle, which of the five candidates produced a value and
    which did not, without opening the raw JSONL (this task's own
    behavior spec). `reason` is shown ahead of `fallback_reason` in the
    Notes column since an unavailable/failed candidate's `reason` is the
    more informative field when both could theoretically be present.
    """
    block = [
        f"### Cycle — decision time {e.get('decision_time', '')} (valid time {e.get('valid_time', '')})",
        "",
        "All five candidates recorded this cycle (`schema_version: 2`):",
        "",
        "| Candidate | Status | Ampacity (A) | Fallback? | Model version | Notes |",
        "|---|---|---|---|---|---|",
    ]
    candidates = e.get("candidates") or {}
    for name in CANDIDATE_METHOD_NAMES:
        c = candidates.get(name) or {}
        status = c.get("status") or "—"
        ampacity = c.get("ampacity_amps")
        ampacity_str = f"{ampacity:.1f}" if isinstance(ampacity, (int, float)) else "—"
        fallback = "Yes" if c.get("fallback_used") else "No"
        model_version = c.get("model_version") or "—"
        note = _escape_note(c.get("reason") or c.get("fallback_reason"))
        block.append(
            f"| {name} | {status} | {ampacity_str} | {fallback} | {model_version} | {note} |"
        )
    block.append("")
    return block


def render_markdown(predictions_dir: str) -> str:
    """
    Pure function: `predictions_dir` (a directory of `<corridor>.jsonl`
    files, the shape `forecast_shadow_pipeline.log_prediction`/
    `log_cycle_predictions` writes) in, a complete Markdown document out.
    One section per corridor, most recent first.

    Each logged line is rendered per its OWN shape (`entry.get(
    "schema_version", 1) >= 2`), per 05-01-SUMMARY.md's approved,
    forever-coexisting-shapes strategy: a pre-cutover flat-shape entry
    renders as a single table row, byte-identical to this module's
    original (schema_version-naive) behavior; a schema_version-2 entry
    renders as its own all-five-candidates sub-section. A single corridor
    file mixing both shapes (the real situation from the cutover forward)
    renders both correctly, in the same most-recent-first order, in one
    document -- old rows keep reopening/extending the same legacy table
    whenever consecutive, new-shape rows interrupt it with their own block.
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

        legacy_table_open = False
        for e in entries:
            if e.get("schema_version", 1) >= 2:
                legacy_table_open = False
                lines.extend(_render_new_shape_block(e))
            else:
                if not legacy_table_open:
                    lines.append(
                        "| Decision time (UTC) | Valid time (UTC) | Method | Fallback? | "
                        "Ampacity (A) | Model version | Notes |"
                    )
                    lines.append("|---|---|---|---|---|---|---|")
                    legacy_table_open = True
                lines.append(_render_legacy_row(e))
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
