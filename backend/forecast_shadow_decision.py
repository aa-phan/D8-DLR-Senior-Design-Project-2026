"""
The owner's ship rule (amendment decision 8D with X = 5 A, planner defaults
PD-05/PD-10; quick task 261013-285, S4).

`apply_ship_rule` turns ONE family report (one row source) into evidence levels
for each real candidate against `raw_forecast`, the 3-of-4-city consistency
count, the working choice and the default action. The ship decision is read
from the reconstructed-frame report (the headline); the shadow-log report is a
separate live-system check. Combining comparisons across the two row sources is
refused (`apply_ship_rule` raises ValueError when a family report carries more
than one `row_source`, and `combined_summary` computes no number across the
two sources).

Levels, for a real candidate C against raw_forecast (pooled entry (C,
raw_forecast), benefit = its point margin in amps):

* "insufficient data": the pooled outcome is insufficient_data;
* "supported": benefit >= X and Holm rejects in C's favour (PD-05);
* "indicated, not resolved": benefit >= X;
* "not shown": otherwise.

Working choice: start at ml_wind_corrected; an alternative A (cooling or the
reference) is "consistently better" when its pooled point margin over wind is at
least X AND it is favoured in at least 3 cities' point estimates (and at least 3
cities have data, and the wind-vs-A comparison is not insufficient_data). With
several qualifiers the larger pooled margin over wind wins. Action: W "not
shown" -> ship raw_forecast; W "supported" or "indicated, not resolved" -> ship
W, stating the level; W "insufficient data" -> keep ml_wind_corrected as the
provisional default with the statement that no evidence-based selection was
possible. Parameters default to the pre-registered values in
`forecast_shadow_eval_core`; non-default values are recorded and, in a FRESH
run, need the override reason (enforced by `check_guard`).

Every number is reanalysis-derived, never sensor-validated.
"""

from __future__ import annotations

from typing import Optional

import forecast_shadow_eval_core as core

EVIDENCE_LEVELS = ("supported", "indicated, not resolved", "not shown", "insufficient data")
ALTERNATIVES = ("ml_cooling_corrected", "reference_ml_refit_24h")
NO_SELECTION_STATEMENT = "no evidence-based selection was possible; the provisional default is retained"


def _entry(family_report: dict, a: str, b: str) -> dict:
    for c in family_report.get("comparisons", []):
        if c["a"] == a and c["b"] == b:
            return c
    raise ValueError(f"apply_ship_rule: family report has no comparison ({a}, {b})")


def evidence_level(entry: dict, margin: float = core.DECISION_MARGIN_AMPS) -> dict:
    """Level of one correction against raw_forecast from its pooled entry."""
    head = entry["headline"]
    benefit = entry.get("point_margin")
    holm_rejected = bool(head.get("holm_rejected"))
    if head.get("outcome") == "insufficient_data" or benefit is None:
        level = "insufficient data"
    elif benefit >= margin and holm_rejected:
        level = "supported"
    elif benefit >= margin:
        level = "indicated, not resolved"
    else:
        level = "not shown"
    return {"level": level, "benefit_amps": benefit, "holm_rejected": holm_rejected,
            "outcome": head.get("outcome"), "n_paired": entry.get("n_paired"),
            "cities_favoring": entry.get("cities_favoring_a"), "cities_with_data": entry.get("cities_with_data"),
            "p_holm_adjusted": head.get("p_holm_adjusted")}


def _row_sources(family_report: dict) -> set:
    return {c.get("row_source") for c in family_report.get("comparisons", [])}


def _sample_size_sentence(family_report: dict) -> str:
    pairs = (family_report.get("sample_size") or {}).get("pairs") or []
    ns = [p["n_paired"] for p in pairs]
    if not ns:
        return "Sample size: no scored rows."
    tail = sum(1 for p in pairs if p["targets"]["tail_rate_target_met"])
    mdd = sum(1 for p in pairs if p["targets"]["mdd_target_met"])
    unmet = ("both precision targets (about 590 rows for the tail rate, about 1,575 rows for a 5 A minimum detectable "
             "difference) were not met for any headline test" if tail == 0 and mdd == 0 else
             f"the ~590-row target was met for {tail} of {len(pairs)} tests and the ~1,575-row target for {mdd}")
    return (f"Sample size: pooled paired rows per headline test range from {min(ns)} to {max(ns)} (nominal, not "
            f"effective; effective sample sizes are smaller because six-hourly rows and the four cities share weather); "
            f"{unmet}.")


def apply_ship_rule(family_report: dict, *, protocol_status: str = "unsigned",
                    margin: float = core.DECISION_MARGIN_AMPS,
                    min_cities: int = core.CONSISTENCY_MIN_CITIES) -> dict:
    sources = _row_sources(family_report)
    if len(sources) > 1:
        raise ValueError(f"apply_ship_rule: the family report mixes row sources {sorted(map(str, sources))}; "
                         f"comparisons from different row sources are never combined")
    row_source = family_report.get("row_source")
    if sources and row_source is not None and sources != {row_source}:
        raise ValueError(f"apply_ship_rule: comparisons carry row source {sorted(map(str, sources))} but the report is {row_source!r}")

    levels = {c: evidence_level(_entry(family_report, c, core.FALLBACK_CHOICE), margin) for c in core.REAL_CANDIDATES}

    alternatives = {}
    for alt in ALTERNATIVES:
        e = _entry(family_report, core.DEFAULT_CHOICE, alt)
        point = e.get("point_margin")
        over = None if point is None else -float(point)
        per_city = e.get("per_city_margins") or {}
        with_data = [c for c, v in per_city.items() if v is not None]
        favoring = [c for c in with_data if per_city[c] < 0.0]
        possible = len(with_data) >= min_cities
        insufficient = e["headline"].get("outcome") == "insufficient_data"
        qualifies = bool(possible and not insufficient and over is not None and over >= margin and len(favoring) >= min_cities)
        if not possible:
            reason = f"consistency impossible: only {len(with_data)} cities have data (need {min_cities})"
        elif insufficient:
            reason = "insufficient data for the pooled comparison with the default"
        elif over is None or over < margin:
            reason = f"pooled margin over {core.DEFAULT_CHOICE} is below {margin} A"
        elif len(favoring) < min_cities:
            reason = f"favoured in only {len(favoring)} of {len(with_data)} cities (need {min_cities})"
        else:
            reason = "pooled margin and city consistency both met"
        alternatives[alt] = {"margin_over_default_amps": over, "cities_favoring": len(favoring),
                             "cities_with_data": len(with_data), "consistency_possible": possible,
                             "consistently_better": qualifies, "reason": reason,
                             "n_paired": e.get("n_paired")}

    qualifying = [a for a, d in alternatives.items() if d["consistently_better"]]
    working = core.DEFAULT_CHOICE
    reasons = []
    if qualifying:
        working = max(qualifying, key=lambda a: alternatives[a]["margin_over_default_amps"])
        reasons.append(f"{working} is consistently better than {core.DEFAULT_CHOICE} (pooled margin "
                       f"{alternatives[working]['margin_over_default_amps']:.2f} A, favoured in "
                       f"{alternatives[working]['cities_favoring']} of {alternatives[working]['cities_with_data']} cities)"
                       + ("; it has the larger pooled margin among qualifying alternatives" if len(qualifying) > 1 else ""))
    else:
        reasons.append(f"no alternative is consistently better than {core.DEFAULT_CHOICE}; it stays the working choice")

    w_level = levels[working]["level"]
    if w_level == "not shown":
        ship = core.FALLBACK_CHOICE
        statement = (f"{working} is not shown to improve on raw_forecast by at least {margin:g} A; fall back to "
                     f"{core.FALLBACK_CHOICE}.")
    elif w_level in ("supported", "indicated, not resolved"):
        ship = working
        statement = f"Ship {working}: its benefit over raw_forecast is {w_level} (benefit {levels[working]['benefit_amps']:.2f} A)."
    else:
        ship = core.DEFAULT_CHOICE
        statement = f"Insufficient data for {working} against raw_forecast: {NO_SELECTION_STATEMENT}."
    reasons.append(f"working choice {working} has evidence level {w_level!r}")

    statements = [_sample_size_sentence(family_report), statement,
                  "Per-city results are descriptive and uncorrected; the headline is the pooled, city-clustered 9-test "
                  "family with Holm correction at 0.05.", core.NOT_MEASURED_STATEMENT, core.TRUTH_LABEL + "."]
    if protocol_status != "signed":
        statements.append(core.EXPLORATORY_STATEMENT)
    return {
        "row_source": row_source,
        "protocol_status": protocol_status,
        "label": "headline decision" if row_source == core.HEADLINE_ROW_SOURCE else "live-system check",
        "margin_amps": margin, "consistency_min_cities": min_cities,
        "levels": levels, "alternatives_vs_default": alternatives,
        "working_choice": working,
        "action": {"ship": ship, "level": w_level, "statement": statement},
        "reasons": reasons, "statements": statements,
    }


def combined_summary(headline_report: dict, live_report: dict) -> str:
    """
    Side-by-side Markdown. The headline decision comes from the reconstructed
    frames report; the live-system check is the shadow-log report's own
    levels, with an agreement line on the working choices. No number is
    computed across the two row sources.
    """
    if headline_report.get("row_source") != core.HEADLINE_ROW_SOURCE or live_report.get("row_source") != core.LIVE_ROW_SOURCE:
        raise ValueError("combined_summary: expected (reconstructed_frames headline report, shadow_logs live report), got "
                         f"({headline_report.get('row_source')!r}, {live_report.get('row_source')!r}); sources are never swapped or duplicated")
    hd, ld = headline_report.get("decision"), live_report.get("decision")
    if not hd or not ld or hd.get("row_source") != core.HEADLINE_ROW_SOURCE or ld.get("row_source") != core.LIVE_ROW_SOURCE:
        raise ValueError("combined_summary: each report must carry a decision for its own row source")

    def n_range(report):
        ns = [p["n_paired"] for p in (report.get("sample_size", {}).get("pairs") or [])]
        return f"{min(ns)} to {max(ns)}" if ns else "none"

    def block(title, report, dec):
        lines = [f"## {title} (row source: {dec['row_source']})", "",
                 f"Paired rows per headline test: {n_range(report)} (nominal, not effective).", ""]
        for cand, lv in dec["levels"].items():
            b = lv["benefit_amps"]
            lines.append(f"- {cand} vs raw_forecast: {lv['level']} (benefit {'n/a' if b is None else f'{b:.2f}'} A)")
        lines += ["", f"Working choice: {dec['working_choice']}", f"Action: ship {dec['action']['ship']} ({dec['action']['level']})", ""]
        return lines

    agree = hd["working_choice"] == ld["working_choice"]
    lines = ["# Combined summary: two row sources, never pooled", "",
             f"Truth: {core.TRUTH_LABEL}. Protocol status: {hd['protocol_status']}.", ""]
    lines += block("Headline decision", headline_report, hd)
    lines += block("Live-system check", live_report, ld)
    lines += ["## Agreement", "",
              ("The working choices agree: " if agree else "The working choices differ: ")
              + f"{hd['working_choice']} (headline) and {ld['working_choice']} (live-system check). "
              "The live-system check never changes the headline decision.", "",
              core.NOT_MEASURED_STATEMENT]
    if hd["protocol_status"] != "signed" or ld["protocol_status"] != "signed":
        lines += ["", core.EXPLORATORY_STATEMENT]
    return "\n".join(lines) + "\n"
