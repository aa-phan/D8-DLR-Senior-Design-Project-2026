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


def render_markdown(predictions_dir: str) -> str:
    """
    Pure function: `predictions_dir` (a directory of `<corridor>.jsonl`
    files, the shape `forecast_shadow_pipeline.log_prediction` writes) in,
    a complete Markdown document out. One section per corridor, one row
    per logged prediction, most recent first.
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
        lines.append(
            "| Decision time (UTC) | Valid time (UTC) | Method | Fallback? | "
            "Ampacity (A) | Model version | Notes |"
        )
        lines.append("|---|---|---|---|---|---|---|")
        for e in entries:
            fallback = "Yes" if e.get("fallback_used") else "No"
            note = (e.get("fallback_reason") or "").replace("|", "\\|").replace("\n", " ")
            if len(note) > 100:
                note = note[:100] + "…"
            model_version = e.get("model_version") or "—"
            ampacity = e.get("ampacity_amps")
            ampacity_str = f"{ampacity:.1f}" if isinstance(ampacity, (int, float)) else "—"
            lines.append(
                f"| {e.get('decision_time', '')} | {e.get('valid_time', '')} | "
                f"{e.get('method', '')} | {fallback} | {ampacity_str} | "
                f"{model_version} | {note} |"
            )
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
