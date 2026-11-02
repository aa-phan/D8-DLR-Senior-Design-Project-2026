"""
The signed v4 selection rule (confirmation protocol v4, signed 2026-11-02; 07-05).

v4 (see `docs/data-science/decisions/confirmation_protocol_v4_early_selection_SIGNING_COPY.md`) replaces v3
decision 8 for per-city scoring. `forecast_shadow_decision.py` (v3) is untouched. Every constant below equals
a row of the signing copy's machine-checked registry; `forecast_shadow_decision_v4_test.py` asserts that
parity, so the rule cannot drift from what the owner signed. Every number is reanalysis-derived, never
sensor-validated.

The rule, for one round and one family report (one row source):

* Per city c with data, bar_c = RELATIVE_MARGIN_FRACTION x mean truth ampacity T_c (replacing the fixed 5 A).
  The pooled bar of a comparison is the paired-row-weighted mean of the cities' bars, with that
  comparison's own per-city paired-row counts as weights (BAR_SCOPE "pooled_paired_row_weighted").
* A real candidate X's level against raw_forecast: "insufficient data"; "supported" (pooled benefit >= pooled
  bar and the Holm-adjusted p-value <= the round's family alpha, benefit > 0); "indicated, not resolved"
  (benefit >= bar); else "not shown". A pooled benefit exactly equal to the pooled bar meets it.
* X is consistent when it is favoured over raw_forecast in at least CONSISTENCY_MIN_CITIES cities by point
  estimate and at least that many cities hold data (a failed city counts as no data).
* X qualifies when its level is supported or indicated, it is consistent and it is not vetoed by the
  ABLATION or TEST re-scores (D-02: those bases only veto, never pick).
* Winner: ml_wind_corrected if it qualifies, unless a qualifying alternative is consistently better than it
  (pooled margin over wind >= that comparison's pooled bar, and favoured over wind in >= 3 cities); the larger
  margin wins. If wind does not qualify, the qualifying alternative with the larger pooled benefit over
  raw_forecast wins. Exact ties follow TIE_ORDER. If nothing qualifies there is NO PICK and no shadow model
  replaces ml (D-07); the v3 fallbacks no longer exist.

All arithmetic is unrounded float64; rounding happens only in rendered text (two decimals).
"""

from __future__ import annotations

from typing import Optional

import forecast_shadow_eval_core as core

# --- Registered values (parity with the signing copy's registry is asserted in the tests) ---------------
RELATIVE_MARGIN_FRACTION = 0.02
BAR_SCOPE = "pooled_paired_row_weighted"
CONSISTENCY_MIN_CITIES = 3
FAMILY_ALPHA_BY_ROUND = {"v4-read1": 0.05, "v4-read2": 0.05, "v4-late-descriptive": 0.05}
READ2_REQUIRES_SUPPORTED = False  # owner item O2 signed as option A: same rules at both reads
TIE_ORDER = ("ml_wind_corrected", "ml_cooling_corrected", "reference_ml_refit_24h")

EVIDENCE_LEVELS = ("supported", "indicated, not resolved", "not shown", "insufficient data")
LABELS = {
    "headline": "headline decision",
    "secondary": "secondary: frozen Drake artifacts, never decides",
    "live": "live-system check, never decides",
    "descriptive": "descriptive re-score (D-03), cannot overturn",
}
NO_PICK_STATEMENT = "No candidate qualifies under signed protocol v4: no shadow model replaces ml (D-07)."
READ2_SCHEDULED_STATEMENT = (
    "Read 1 names no winner, so the pre-registered re-test v4-read2 runs at or after 2026-11-08T00:00:00Z "
    "under the same rules."
)
READ2_NO_WINNER_STATEMENT = (
    "Read 2 (v4-read2) also names no winner: there is no day-ahead pick and the interim G6 method keeps running; "
    "2026-11-24 stays retired and any later evaluation needs a new signed protocol (owner item O3)."
)

_SCOPES = ("pooled_paired_row_weighted", "per_city")


# --- Private helpers (copied from the v3 module's shape; never imported from it) ----------------------------

def _entry(family_report: dict, a: str, b: str) -> dict:
    for c in family_report.get("comparisons", []):
        if c["a"] == a and c["b"] == b:
            return c
    raise ValueError(f"apply_ship_rule_v4: family report has no comparison ({a}, {b})")


def _row_sources(family_report: dict) -> set:
    return {c.get("row_source") for c in family_report.get("comparisons", [])}


def _plural(n: int, noun: str = "city", plural: str = "cities") -> str:
    return f"{n} {noun if n == 1 else plural}"


# --- Bars ----------------------------------------------------------------------------------------------

def city_bars(truth_stats: dict, fraction: float = RELATIVE_MARGIN_FRACTION) -> dict:
    """{city: fraction x mean truth ampacity}, or None for a city with no truth rows. Unrounded."""
    bars: dict = {}
    for city, stats in truth_stats.items():
        mean = (stats or {}).get("mean_truth_amps")
        rows = (stats or {}).get("n_truth_rows")
        bars[city] = None if mean is None or not rows else fraction * float(mean)
    return bars


def pooled_bar(entry: dict, bars: dict) -> Optional[float]:
    """Paired-row-weighted mean of the cities' bars, weights = this entry's per-city n_paired.

    Cities with no paired rows or no bar are left out; None when none remain.
    """
    total = 0.0
    weight = 0
    for city, info in (entry.get("per_city") or {}).items():
        n = (info or {}).get("n_paired") or 0
        bar = bars.get(city)
        if n > 0 and bar is not None:
            total += n * bar
            weight += n
    return None if weight == 0 else total / weight


# --- Evidence levels and consistency ------------------------------------------------------------------

def evidence_level_v4(entry: dict, bar: Optional[float], alpha: float) -> dict:
    """Level of one comparison from its pooled entry, against the pooled bar and the round's family alpha."""
    head = entry.get("headline") or {}
    benefit = entry.get("point_margin")
    p_adj = head.get("p_holm_adjusted")
    if head.get("outcome") == "insufficient_data" or benefit is None or bar is None:
        level = "insufficient data"
    elif benefit >= bar and benefit > 0.0 and p_adj is not None and p_adj <= alpha:
        level = "supported"
    elif benefit >= bar:
        level = "indicated, not resolved"
    else:
        level = "not shown"
    return {"level": level, "benefit_amps": benefit, "bar_amps": bar,
            "holm_rejected": bool(head.get("holm_rejected")), "p_holm_adjusted": p_adj,
            "outcome": head.get("outcome"), "n_paired": entry.get("n_paired")}


def consistency(entry: dict, bars: dict, min_cities: int = CONSISTENCY_MIN_CITIES, *, scope: str = BAR_SCOPE) -> dict:
    """How many cities favour the first model of the pair.

    Under the pooled scope a city favours it when its per-city margin is positive; under the per-city scope
    the margin must reach that city's own bar. A city counts as holding data when its margin is not None.
    """
    if scope not in _SCOPES:
        raise ValueError(f"consistency: unknown bar scope {scope!r} (expected one of {_SCOPES})")
    per_city = entry.get("per_city_margins") or {}
    with_data = [c for c, v in per_city.items() if v is not None]
    if scope == "per_city":
        favoring = [c for c in with_data if bars.get(c) is not None and per_city[c] >= bars[c]]
    else:
        favoring = [c for c in with_data if per_city[c] > 0.0]
    possible = len(with_data) >= min_cities
    consistent = possible and len(favoring) >= min_cities
    if not possible:
        reason = f"consistency impossible: only {_plural(len(with_data))} have data (need {min_cities})"
    elif consistent:
        reason = f"favoured in {len(favoring)} of {len(with_data)} cities (need {min_cities})"
    else:
        reason = f"favoured in only {len(favoring)} of {len(with_data)} cities (need {min_cities})"
    return {"cities_with_data": len(with_data), "cities_favoring": len(favoring),
            "possible": possible, "consistent": consistent, "reason": reason}


# --- Vetoes, pick or no pick ----------------------------------------------------------------------------

ALTERNATIVES = tuple(c for c in TIE_ORDER if c != core.DEFAULT_CHOICE)
_NO_VETO_RECORD_STATEMENT = "no ABLATION/TEST veto record was applied (development basis)"


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


def _veto_record(vetoes: Optional[dict], candidate: str) -> dict:
    """One candidate's veto state. A candidate missing from a supplied record is not vetoed (source says so)."""
    if vetoes is None:
        return {"ablation": False, "test": False, "vetoed": False, "source": "no veto record applied (development basis)"}
    found = {}
    for basis in ("ablation", "test"):
        rec = (vetoes.get(basis) or {}).get(candidate)
        if rec is not None:
            found[basis] = bool(rec.get("vetoed"))
    return {"ablation": found.get("ablation", False), "test": found.get("test", False),
            "vetoed": any(found.values()),
            "source": "+".join(found) if found else "no veto entry for this candidate"}


def _best(candidates: list, key) -> Optional[str]:
    """The candidate with the largest key; an exact tie goes to the earlier name in TIE_ORDER."""
    best = None
    for c in TIE_ORDER:
        if c in candidates and (best is None or key(c) > key(best)):
            best = c
    return best


def apply_ship_rule_v4(family_report: dict, *, truth_stats: dict, round_name: str, label: str = "headline",
                       vetoes: Optional[dict] = None, require_vetoes: bool = True, protocol_status: str = "unsigned",
                       fraction: Optional[float] = None, min_cities: Optional[int] = None,
                       alpha: Optional[float] = None) -> dict:
    """Apply the signed v4 rule to ONE family report (one row source) for one round.

    `truth_stats` is {city: {"mean_truth_amps", "n_truth_rows"}} for the round's scored rows. `vetoes` is
    {"ablation": {candidate: {"vetoed": bool}}, "test": {...}}. Only label "headline" can report a pick; the
    other labels compute everything and carry the would-be result in `rule_outcome`.
    """
    if label not in LABELS:
        raise ValueError(f"apply_ship_rule_v4: unknown label {label!r} (expected one of {sorted(LABELS)})")
    if round_name not in FAMILY_ALPHA_BY_ROUND:
        raise ValueError(f"apply_ship_rule_v4: unknown round {round_name!r} (registered: {sorted(FAMILY_ALPHA_BY_ROUND)})")
    if label == "headline" and require_vetoes and vetoes is None:
        raise ValueError("apply_ship_rule_v4: a v4 headline decision needs the ABLATION and TEST veto record (SEL-03)")
    fraction = RELATIVE_MARGIN_FRACTION if fraction is None else fraction
    min_cities = CONSISTENCY_MIN_CITIES if min_cities is None else min_cities
    alpha = FAMILY_ALPHA_BY_ROUND[round_name] if alpha is None else alpha

    sources = _row_sources(family_report)
    if len(sources) > 1:
        raise ValueError(f"apply_ship_rule_v4: the family report mixes row sources {sorted(map(str, sources))}; "
                         f"comparisons from different row sources are never combined")
    row_source = family_report.get("row_source")
    if sources and row_source is not None and sources != {row_source}:
        raise ValueError(f"apply_ship_rule_v4: comparisons carry row source {sorted(map(str, sources))} but the report "
                         f"is {row_source!r}")
    if row_source is None and len(sources) == 1:
        row_source = next(iter(sources))
    if label == "headline" and row_source != core.HEADLINE_ROW_SOURCE:
        raise ValueError(f"apply_ship_rule_v4: a headline decision is read from {core.HEADLINE_ROW_SOURCE!r}, not "
                         f"{row_source!r}; the live-system check never decides")

    bars = city_bars(truth_stats, fraction)
    read2_needs_supported = READ2_REQUIRES_SUPPORTED and round_name == "v4-read2"
    pooled_by: dict = {}
    levels: dict = {}
    cons: dict = {}
    vetoed: dict = {}
    qualifies: dict = {}
    reasons: list = []

    for cand in core.REAL_CANDIDATES:
        e = _entry(family_report, cand, core.FALLBACK_CHOICE)
        pb = pooled_bar(e, bars)
        pooled_by[f"{cand}__vs__{core.FALLBACK_CHOICE}"] = pb
        levels[cand] = evidence_level_v4(e, pb, alpha)
        cons[cand] = consistency(e, bars, min_cities, scope=BAR_SCOPE)
        vetoed[cand] = _veto_record(vetoes, cand)
        lv = levels[cand]["level"]
        level_ok = lv == "supported" if read2_needs_supported else lv in ("supported", "indicated, not resolved")
        qualifies[cand] = bool(level_ok and cons[cand]["consistent"] and not vetoed[cand]["vetoed"])
        notes = [f"level {lv!r}"]
        if read2_needs_supported and lv == "indicated, not resolved":
            notes.append("round v4-read2 needs 'supported' (registry)")
        notes.append(cons[cand]["reason"])
        if vetoed[cand]["vetoed"]:
            by = [b.upper() for b in ("ablation", "test") if vetoed[cand][b]]
            notes.append(f"vetoed by the {' and '.join(by)} re-score (D-02), so it never qualifies")
        reasons.append(f"{cand} {'qualifies' if qualifies[cand] else 'does not qualify'}: " + "; ".join(notes))

    most_cities = max((c["cities_with_data"] for c in cons.values()), default=0)
    if most_cities < min_cities:
        reasons.append(f"only {_plural(most_cities)} hold data (need {min_cities}): no candidate can be consistent, "
                       f"so there is no pick")

    alternatives: dict = {}
    for alt in ALTERNATIVES:
        e = _entry(family_report, core.DEFAULT_CHOICE, alt)
        point = e.get("point_margin")
        margin = None if point is None else -float(point)
        pb = pooled_bar(e, bars)
        pooled_by[f"{core.DEFAULT_CHOICE}__vs__{alt}"] = pb
        # The pair is (wind, alt): a negative per-city margin favours the alternative, so negate to reuse consistency().
        flipped = {"per_city_margins": {c: None if v is None else -v for c, v in (e.get("per_city_margins") or {}).items()}}
        c_alt = consistency(flipped, bars, min_cities, scope=BAR_SCOPE)
        insufficient = (e.get("headline") or {}).get("outcome") == "insufficient_data"
        better = bool(c_alt["possible"] and not insufficient and margin is not None and pb is not None
                      and margin >= pb and c_alt["consistent"])
        if not c_alt["possible"]:
            why = c_alt["reason"]
        elif insufficient or margin is None or pb is None:
            why = "insufficient data for the pooled comparison with the default"
        elif margin < pb:
            why = f"pooled margin over {core.DEFAULT_CHOICE} ({margin:.2f} A) is below the pooled bar ({pb:.2f} A)"
        elif not c_alt["consistent"]:
            why = c_alt["reason"]
        else:
            why = "pooled margin and city consistency both met"
        alternatives[alt] = {"margin_over_default_amps": margin, "bar_amps": pb,
                             "cities_favoring": c_alt["cities_favoring"], "cities_with_data": c_alt["cities_with_data"],
                             "consistency_possible": c_alt["possible"], "consistently_better": better,
                             "reason": why, "n_paired": e.get("n_paired")}

    qualifying = [c for c in TIE_ORDER if qualifies.get(c)]
    pick: Optional[str]
    if qualifies[core.DEFAULT_CHOICE]:
        displacers = [a for a in ALTERNATIVES if qualifies[a] and alternatives[a]["consistently_better"]]
        pick = _best(displacers, lambda a: alternatives[a]["margin_over_default_amps"]) if displacers else core.DEFAULT_CHOICE
        if displacers:
            reasons.append(f"{pick} qualifies and is consistently better than {core.DEFAULT_CHOICE} (pooled margin "
                           f"{alternatives[pick]['margin_over_default_amps']:.2f} A against a pooled bar of "
                           f"{alternatives[pick]['bar_amps']:.2f} A, favoured in {alternatives[pick]['cities_favoring']} of "
                           f"{alternatives[pick]['cities_with_data']} cities)"
                           + ("; it has the larger pooled margin among qualifying alternatives" if len(displacers) > 1 else ""))
        else:
            reasons.append(f"{core.DEFAULT_CHOICE} qualifies and no qualifying alternative is consistently better")
    else:
        alts = [a for a in ALTERNATIVES if qualifies[a]]
        pick = _best(alts, lambda a: levels[a]["benefit_amps"])
        if pick is not None:
            reasons.append(f"{core.DEFAULT_CHOICE} does not qualify; {pick} qualifies with the larger pooled benefit over "
                           f"{core.FALLBACK_CHOICE} ({levels[pick]['benefit_amps']:.2f} A)" if len(alts) > 1 else
                           f"{core.DEFAULT_CHOICE} does not qualify; {pick} is the only qualifying alternative")
    if pick is None:
        reasons.append("no candidate qualifies")

    if label == "headline":
        if pick is None:
            decision_text = [NO_PICK_STATEMENT]
            if round_name == "v4-read1":
                decision_text.append(READ2_SCHEDULED_STATEMENT)
            elif round_name == "v4-read2":
                decision_text.append(READ2_NO_WINNER_STATEMENT)
        else:
            lv = levels[pick]
            decision_text = [f"Pick {pick}: it qualifies under signed protocol v4 (level {lv['level']}, benefit "
                             f"{lv['benefit_amps']:.2f} A against a pooled bar of {lv['bar_amps']:.2f} A)."]
    else:
        would = pick if pick is not None else "no candidate qualifies"
        decision_text = [f"This is the {LABELS[label]}: its pick is always None. Under the v4 rule its would-be outcome "
                         f"is {would}."]

    statements = [_sample_size_sentence(family_report), *decision_text]
    if vetoes is None:
        statements.append(_NO_VETO_RECORD_STATEMENT)
    statements += [f"Per-city results are descriptive and uncorrected; the headline is the pooled, city-clustered 9-test "
                   f"family with Holm correction at {alpha:g}.", core.NOT_MEASURED_STATEMENT, core.TRUTH_LABEL + "."]
    if protocol_status != "signed" or vetoes is None:
        statements.append(core.EXPLORATORY_STATEMENT)

    return {
        "rule": "v4", "row_source": row_source, "round": round_name, "label": LABELS[label],
        "protocol_status": protocol_status, "fraction": fraction, "consistency_min_cities": min_cities,
        "family_alpha": alpha, "bar_scope": BAR_SCOPE,
        "bars": {"per_city": bars, "pooled_by_comparison": pooled_by},
        "levels": levels, "consistency": cons, "vetoes": vetoed, "qualifying": qualifying,
        "alternatives_vs_default": alternatives,
        "rule_outcome": pick, "pick": pick if label == "headline" else None,
        "statement": " ".join(decision_text), "reasons": reasons, "statements": statements,
    }


# --- Side-by-side summary ---------------------------------------------------------------------------------

def _amps(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def combined_summary_v4(headline_report: dict, live_report: dict, secondary_report: Optional[dict] = None) -> str:
    """
    Side-by-side Markdown: the headline decision (reconstructed frames), the live-system check (shadow logs) and,
    when given, the labelled secondary result. Each block reads its own decision; no number is computed across
    row sources. Swapped, duplicated or mislabelled reports are refused.
    """
    swapped = ("combined_summary_v4: expected (reconstructed_frames headline report, shadow_logs live report"
               "[, reconstructed_frames secondary report]), got ({!r}, {!r}{}); sources are never swapped or duplicated")
    sec_src = None if secondary_report is None else secondary_report.get("row_source")
    if (headline_report.get("row_source") != core.HEADLINE_ROW_SOURCE or live_report.get("row_source") != core.LIVE_ROW_SOURCE
            or (secondary_report is not None and (sec_src != core.HEADLINE_ROW_SOURCE or secondary_report is headline_report))):
        raise ValueError(swapped.format(headline_report.get("row_source"), live_report.get("row_source"),
                                        "" if secondary_report is None else f", {sec_src!r}"))
    blocks = [("Headline decision", headline_report, core.HEADLINE_ROW_SOURCE, "headline"),
              ("Live-system check", live_report, core.LIVE_ROW_SOURCE, "live")]
    if secondary_report is not None:
        blocks.append(("Secondary result (frozen Drake artifacts)", secondary_report, core.HEADLINE_ROW_SOURCE, "secondary"))
    for title, report, source, label in blocks:
        d = report.get("decision")
        if not d or d.get("row_source") != source:
            raise ValueError(f"combined_summary_v4: the {title.lower()} report must carry a decision for its own row source")
        if d.get("rule") != "v4" or d.get("label") != LABELS[label]:
            raise ValueError(f"combined_summary_v4: the {title.lower()} decision must carry the label {LABELS[label]!r}, "
                             f"got {d.get('label')!r}")

    def n_range(report):
        ns = [p["n_paired"] for p in (report.get("sample_size", {}).get("pairs") or [])]
        return f"{min(ns)} to {max(ns)}" if ns else "none"

    def block(title, report, label):
        d = report["decision"]
        lines = [f"## {title} (row source: {d['row_source']})", "",
                 f"Round {d['round']}. Paired rows per headline test: {n_range(report)} (nominal, not effective).", "",
                 f"Bars ({d['fraction'] * 100:g}% of mean truth) per city: "
                 + ", ".join(f"{c} {_amps(b)} A" for c, b in d["bars"]["per_city"].items()) + ".", ""]
        for cand, lv in d["levels"].items():
            v = d["vetoes"][cand]
            tag = ("; vetoed by " + "+".join(b for b in ("ablation", "test") if v[b])) if v["vetoed"] else ""
            lines.append(f"- {cand} vs raw_forecast: {lv['level']} (benefit {_amps(lv['benefit_amps'])} A, pooled bar "
                         f"{_amps(lv['bar_amps'])} A; favoured in {d['consistency'][cand]['cities_favoring']} of "
                         f"{d['consistency'][cand]['cities_with_data']} cities{tag})")
        lines.append("")
        if label == "headline":
            if d["pick"] is None:
                lines.append(f"No pick. {NO_PICK_STATEMENT}")
                for s in (READ2_SCHEDULED_STATEMENT, READ2_NO_WINNER_STATEMENT):
                    if s in d["statements"]:
                        lines.append(s)
            else:
                lines.append(f"Pick: {d['pick']}")
        else:
            lines.append(f"Reported pick: None ({LABELS[label]}). Would-be outcome under the v4 rule: "
                         f"{d['rule_outcome'] or 'no candidate qualifies'}.")
        lines.append("")
        return lines

    hd, ld = headline_report["decision"], live_report["decision"]
    agree = hd["rule_outcome"] == ld["rule_outcome"]
    lines = ["# Combined summary: row sources never pooled", "",
             f"Truth: {core.TRUTH_LABEL}. Protocol status: {hd['protocol_status']}. Rule: v4.", ""]
    for title, report, _source, label in blocks:
        lines += block(title, report, label)
    lines += ["## Agreement", "",
              ("The outcomes agree: " if agree else "The outcomes differ: ")
              + f"{hd['rule_outcome'] or 'no candidate qualifies'} (headline) and {ld['rule_outcome'] or 'no candidate qualifies'} "
              "(live-system check). The live-system check never changes the headline decision.", "",
              core.NOT_MEASURED_STATEMENT]
    if any(r["decision"]["protocol_status"] != "signed" for _t, r, _s, _l in blocks):
        lines += ["", core.EXPLORATORY_STATEMENT]
    return "\n".join(lines) + "\n"
