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
