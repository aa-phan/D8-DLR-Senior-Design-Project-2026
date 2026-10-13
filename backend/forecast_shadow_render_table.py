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
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Mirrors `forecast_shadow_pipeline.CANDIDATE_METHOD_NAMES` (05-02's D-01
# order, 05-01-SUMMARY.md's approved nested-candidates shape, keyed by city
# since `schema_version: 3`) -- duplicated
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
# schema_version>=3 cycles rendered per city. The one-block-per-cycle
# format this replaced grew the README by a full multi-line sub-table on
# every single collection run with no limit, forever. This caps the
# RENDERED view only -- every cycle beyond the cap is still in the raw
# `data/shadow/predictions/<CITY>.jsonl` on `shadow-collection-data`,
# untouched and un-pruned; nothing is deleted, only what this specific
# README shows is bounded.
# 2026-10-12: cap lowered from 20 to 5 -- the README shows only the 5 most recent
# cycles per city; the raw per-city JSONL on the data branch keeps everything.
RENDERED_CYCLE_CAP = 5

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

# 2026-10-08: added at the user's own request, to answer a question a
# first-time reader of this table would otherwise have to go dig through
# chat history or the full decision record to answer -- what each of the
# five candidates is actually doing, and the one thing they genuinely
# share (all five answer the SAME question, for the SAME future target
# time) versus what actually differs between them (who does the
# forward-in-time extrapolation, and on what variable). Written as a
# Markdown block (not a single-line string) since it has its own internal
# structure; inserted once per render, right after the two existing
# caveats above, never per-city or per-cycle.
METHODS_EXPLANATION = """\
**What the five candidates actually do.** All five answer the exact same question -- what will \
this city's ampacity be at the SAME future target time -- but differ in who does the \
forward-in-time extrapolation, and on what:

- **External-forecast-plus-local-physics** (`ml_wind_corrected`, `ml_cooling_corrected`, \
`raw_forecast`): the extrapolation of future WEATHER is done entirely by Open-Meteo's own \
independent NWP model. This project only transforms that already-future weather through IEEE \
738 thermal physics (`raw_forecast`), or through that same physics plus a learned correction \
layer trained to reduce IEEE 738's own known bias (`ml_wind_corrected`/`ml_cooling_corrected`). \
This project does none of the weather extrapolation itself.
- **Self-contained statistical extrapolation** (`reference_ml_refit_24h`): no external forecast \
consulted at all. A model learns directly in ampacity-space, from this city's own recent \
lagged ampacity history plus the MOST RECENTLY OBSERVED (not forecast) weather, to extrapolate \
the next value. This project does 100% of the forward-looking work itself, with no outside NWP \
input.
- **No extrapolation at all** (`persistence_24h`): makes no new claim about how conditions \
evolve. It reuses -- unmodified -- this SAME collector's own `raw_forecast` prediction from ~24 \
hours ago for the matching target hour, betting only that today looks like yesterday at this \
same hour. What it reuses is itself a past FORECAST, never a sensor-measured observation -- this \
project has no sensor-measured ground truth anywhere in this pipeline.

See `docs/data-science/decisions/forecast_correction_followup_audit.md` on `main` for the full \
technical record this summary is drawn from.\
"""


# 2026-10-08 ("UTC is hard to interpret quickly"): every city this
# collector covers (Austin, Corpus Christi, Midland, El Paso) is in
# `America/Chicago` (ERCOT's own home time zone), so that -- not an
# arbitrary third zone -- is the one local time shown alongside UTC.
# `zoneinfo` is a Python 3.9+ stdlib module; no new dependency.
_LOCAL_TZ = ZoneInfo("America/Chicago")


def _format_timestamp(value) -> str:
    """
    Renders one ISO-8601 timestamp (as logged -- always UTC) as
    `YYYY-MM-DD HH:MM UTC (HH:MM CDT/CST)`, seconds/microseconds dropped
    (this table is for a human scanning cycles at a glance, never for
    reproducing the exact logged instant -- the raw JSONL still has full
    microsecond precision for that). The local date is appended too, but
    ONLY when it actually differs from the UTC date (the common case --
    most of the day -- would otherwise show a redundant date twice).
    Returns the original string unchanged (never raises) if it cannot be
    parsed as a timestamp -- the synthetic "x" placeholders this module's
    own tests use, for instance, must still render as themselves.
    """
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    utc_dt = dt.astimezone(timezone.utc)
    local_dt = dt.astimezone(_LOCAL_TZ)
    utc_str = utc_dt.strftime("%Y-%m-%d %H:%M UTC")
    if local_dt.date() == utc_dt.date():
        local_str = local_dt.strftime("%H:%M %Z")
    else:
        local_str = local_dt.strftime("%Y-%m-%d %H:%M %Z")
    return f"{utc_str} ({local_str})"


def _load_entries(path: str) -> list[dict]:
    entries = []
    if not os.path.exists(path):
        return entries
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue  # a malformed line is skipped, never raised on
            if isinstance(entry, dict):
                entries.append(entry)
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
    row-per-cycle table: a checkmark-prefixed ampacity (this city's own
    single-conductor value -- there is no bottleneck city in a per-city
    log). Never embeds the
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
    Renders one schema_version>=3 cycle as ONE table row (2026-10-08, per
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
        f"| {_format_timestamp(e.get('decision_time'))} | {_format_timestamp(e.get('valid_time'))} | " +
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
    prefixed `bundle_ampacity_amps` (this city's single-conductor value
    times its own subconductors-per-phase count), or the bundle's own
    status word when unavailable.
    """
    bundle = c.get("bundle") or {}
    status = bundle.get("status") or "—"
    if status == "ok":
        amps = bundle.get("bundle_ampacity_amps")
        if isinstance(amps, (int, float)):
            return f"✓ {amps:.1f}"
    return status


def _render_bundle_row(e: dict) -> str:
    """
    One cycle's bundle-level row -- same shape as `_render_new_shape_row`
    (one cell per candidate, a trailing aggregated Notes column for any
    non-"ok" bundle), rendered as its OWN table rather than extra columns
    on the per-conductor table, so the two rating bases stay visually
    distinct rather than cramped into one already-wide row.
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
        f"| {_format_timestamp(e.get('decision_time'))} | {_format_timestamp(e.get('valid_time'))} | " +
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
        f"| Decision time | Valid time | {header_cells} | Notes |",
        "|---|---|" + "---|" * len(CANDIDATE_METHOD_NAMES) + "---|",
    ]
    block.extend(_render_bundle_row(e) for e in shown)
    block.append("")
    return block


def _render_new_shape_table(entries: list[dict]) -> list[str]:
    """
    Renders every schema_version>=3 entry for one city as ONE compact
    table, most-recent-first, capped to `RENDERED_CYCLE_CAP` rows. Caller
    passes already-sorted, already-filtered (schema_version>=3) entries
    for a single city; this function owns only the cap and the table
    shape, not the sort/filter.
    """
    if not entries:
        return []
    shown = entries[:RENDERED_CYCLE_CAP]
    header_cells = " | ".join(CANDIDATE_METHOD_NAMES)
    block = [
        "All five candidates per cycle (`schema_version: 3`), most recent "
        f"{len(shown)} of {len(entries)} shown:",
        "",
        f"| Decision time | Valid time | {header_cells} | Notes |",
        "|---|---|" + "---|" * len(CANDIDATE_METHOD_NAMES) + "---|",
    ]
    block.extend(_render_new_shape_row(e) for e in shown)
    if len(entries) > RENDERED_CYCLE_CAP:
        block.append("")
        block.append(
            f"_{len(entries) - RENDERED_CYCLE_CAP} older cycle(s) omitted from this "
            "render -- still present, unpruned, in the raw "
            "`data/shadow/predictions/<CITY>.jsonl` file._"
        )
    block.append("")
    return block


def _is_legacy_corridor_log(entries: list[dict]) -> bool:
    """
    True for a corridor-era log (v1 flat or v2 rows keyed by `corridor`):
    it has at least one `corridor`-keyed row and no `city`-keyed row.
    """
    has_corridor = any(isinstance(e, dict) and "corridor" in e for e in entries)
    has_city = any(isinstance(e, dict) and "city" in e for e in entries)
    return has_corridor and not has_city


def _is_current_entry(entry, city: str) -> bool:
    version = entry.get("schema_version", 1) if isinstance(entry, dict) else None
    return (
        isinstance(version, int) and not isinstance(version, bool)
        and version >= 3 and entry.get("city") == city
    )


def _render_latest_summary(latest: list[tuple[str, dict]]) -> list[str]:
    """One row per city: its most recent v3 cycle (`latest` is `[(city, entry)]`)."""
    header_cells = " | ".join(CANDIDATE_METHOD_NAMES)
    block = [
        "## Latest cycle per city",
        "",
        f"| City | Decision time | Valid time | {header_cells} | Notes |",
        "|---|---|---|" + "---|" * len(CANDIDATE_METHOD_NAMES) + "---|",
    ]
    for city, entry in latest:
        block.append(f"| {city} " + _render_new_shape_row(entry))
    block.append("")
    return block


def render_markdown(predictions_dir: str) -> str:
    """
    Pure function: `predictions_dir` (a directory of `<CITY>.jsonl` files,
    the shape `forecast_shadow_pipeline.log_cycle_predictions` writes) in,
    a complete Markdown document out: a one-row-per-city "latest cycle"
    summary, then one section per city (most recent cycle first, capped to
    `RENDERED_CYCLE_CAP`).

    Only `schema_version>=3` entries keyed by the file's own city are
    rendered. Legacy corridor-era logs (`AUSTIN_CORPUS_CHRISTI.jsonl`,
    `MIDLAND_EL_PASO.jsonl`: rows keyed by `corridor`) are IGNORED -- not
    rendered, never mixed into any city's table -- and named in one
    footer line so their absence is explicit. They are never deleted or
    migrated (05-01's approved "no migration" strategy); the raw files stay
    on `shadow-collection-data`. Non-v3 rows inside a city's own file
    (e.g. flat single-method demo rows) are counted in one line, not shown.
    """
    lines = [
        "# Shadow Collection — Live Predictions",
        "",
        BASIS_CAVEAT,
        "",
        f"> {STATIC_RATINGS_CAVEAT}",
        "",
        METHODS_EXPLANATION,
        "",
        "Regenerated automatically after every `shadow_collect.yml` run — do not hand-edit.",
        "",
    ]
    paths = sorted(glob.glob(os.path.join(predictions_dir, "*.jsonl")))

    city_sections: list[tuple[str, list[dict], int]] = []
    legacy_logs: list[str] = []
    for path in paths:
        name = os.path.splitext(os.path.basename(path))[0]
        entries = _load_entries(path)
        if _is_legacy_corridor_log(entries):
            legacy_logs.append(os.path.basename(path))
            continue
        current = [e for e in entries if _is_current_entry(e, name)]
        current.sort(key=lambda e: e.get("decision_time", ""), reverse=True)
        city_sections.append((name, current, len(entries) - len(current)))

    if not city_sections:
        lines.append("_No predictions logged yet._")
        lines.append("")
    else:
        latest = [(city, current[0]) for city, current, _ in city_sections if current]
        if latest:
            lines.extend(_render_latest_summary(latest))

        for city, current, other_count in city_sections:
            lines.append(f"## {city}")
            lines.append("")
            lines.append(f"{len(current)} logged prediction(s), most recent first.")
            lines.append("")
            lines.extend(_render_new_shape_table(current))
            lines.extend(_render_bundle_table(current))
            if other_count:
                lines.append(
                    f"_{other_count} non-`schema_version: 3` row(s) in this city's raw log are "
                    f"not rendered here -- see `data/shadow/predictions/{city}.jsonl` on this "
                    "branch._"
                )
                lines.append("")
            lines.append("")

    if legacy_logs:
        lines.append(
            "_Legacy corridor-era logs are not rendered (different schema, never mixed with the "
            f"per-city tables): {', '.join(f'`{n}`' for n in legacy_logs)}._"
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
