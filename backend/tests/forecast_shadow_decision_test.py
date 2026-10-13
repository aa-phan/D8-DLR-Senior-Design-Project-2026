"""
Tests for `backend/forecast_shadow_decision.py`, the owner's ship rule
(quick task 261013-285, Task 2). Each case is a synthetic family report: no
statistics are run here, only the rule.
"""

from __future__ import annotations

import copy

import pytest

import forecast_shadow_decision as dec
import forecast_shadow_eval_core as core

CITIES = ("AUSTIN", "CORPUS_CHRISTI", "MIDLAND", "EL_PASO")
W, C, R = "ml_wind_corrected", "ml_cooling_corrected", "reference_ml_refit_24h"
RAW = "raw_forecast"


def entry(a, b, margin=0.0, *, rejected=False, outcome=None, city_margins=None, n=120, row_source="reconstructed_frames"):
    if outcome is None:
        outcome = ("favors_A" if margin > 0 else "favors_B") if rejected else "inconclusive"
    cm = city_margins if city_margins is not None else {c: margin for c in CITIES}
    with_data = [c for c, v in cm.items() if v is not None]
    return {
        "id": f"{a}__vs__{b}", "a": a, "b": b, "row_source": row_source, "flags": [], "n_paired": n, "n_nominal": n,
        "point_margin": None if outcome == "insufficient_data" and margin is None else margin,
        "per_city_margins": cm, "cities_favoring_a": sum(1 for c in with_data if cm[c] > 0), "cities_with_data": len(with_data),
        "headline": {"outcome": outcome, "holm_rejected": bool(rejected and outcome != "insufficient_data"),
                     "p_holm_adjusted": 0.01 if rejected else 0.5, "p_headline": 0.01},
        "per_city": {},
    }


def family(overrides=None, row_source="reconstructed_frames", n=120):
    overrides = overrides or {}
    comps = [overrides.get((a, b)) or entry(a, b, 0.0, n=n, row_source=row_source) for a, b in core.HEADLINE_FAMILY]
    pairs = [{"a": c["a"], "b": c["b"], "n_paired": c["n_paired"],
              "targets": core.precision_targets(c["n_paired"])} for c in comps]
    return {"row_source": row_source, "family_size": 9, "comparisons": comps,
            "sample_size": {"pairs": pairs, "n_scored": {}, "targets_met": {}}}


def margin_over_wind(alt, over, favoured_cities, **kw):
    """The (wind, alt) entry: margin = MAE_alt - MAE_wind, so alt better by `over` means a NEGATIVE margin."""
    cm = {c: (-over if c in favoured_cities else +over) for c in CITIES}
    pooled = -over if len(favoured_cities) >= 2 else over
    return entry(W, alt, pooled, city_margins=cm, **kw)


def ship(overrides, **kw):
    return dec.apply_ship_rule(family(overrides), **kw)


# --------------------------------------------------------------------------
# Levels and actions
# --------------------------------------------------------------------------

def test_wind_supported_ships_wind():
    out = ship({(W, RAW): entry(W, RAW, 12.0, rejected=True)})
    assert out["levels"][W]["level"] == "supported" and out["levels"][W]["benefit_amps"] == 12.0
    assert out["working_choice"] == W and out["action"]["ship"] == W and out["action"]["level"] == "supported"
    assert "supported" in out["action"]["statement"]


def test_wind_indicated_not_resolved_ships_wind_with_the_level_stated():
    out = ship({(W, RAW): entry(W, RAW, 7.0, rejected=False)})
    assert out["levels"][W]["level"] == "indicated, not resolved"
    assert out["action"]["ship"] == W and "indicated, not resolved" in out["action"]["statement"]


def test_wind_not_shown_falls_back_to_raw():
    out = ship({(W, RAW): entry(W, RAW, 3.0, rejected=True)})                  # significant but below X
    assert out["levels"][W]["level"] == "not shown" and out["action"]["ship"] == RAW
    out = ship({(W, RAW): entry(W, RAW, -4.0)})
    assert out["levels"][W]["level"] == "not shown" and out["action"]["ship"] == RAW


def test_x_boundary_is_inclusive():
    assert ship({(W, RAW): entry(W, RAW, 5.0)})["levels"][W]["level"] == "indicated, not resolved"
    assert ship({(W, RAW): entry(W, RAW, 4.999)})["levels"][W]["level"] == "not shown"
    assert ship({(W, RAW): entry(W, RAW, 5.0, rejected=True)})["levels"][W]["level"] == "supported"
    assert dec.apply_ship_rule(family({(W, RAW): entry(W, RAW, 6.0)}), margin=7.0)["levels"][W]["level"] == "not shown"


def test_all_three_levels_are_reported_for_every_real_candidate():
    out = ship({(W, RAW): entry(W, RAW, 12.0, rejected=True), (C, RAW): entry(C, RAW, 6.0), (R, RAW): entry(R, RAW, -1.0)})
    assert [out["levels"][x]["level"] for x in (W, C, R)] == ["supported", "indicated, not resolved", "not shown"]
    assert set(out["levels"]) == set(core.REAL_CANDIDATES) and dec.EVIDENCE_LEVELS[-1] == "insufficient data"


def test_cooling_consistently_better_with_three_cities_becomes_the_working_choice():
    out = ship({(W, RAW): entry(W, RAW, 12.0, rejected=True), (C, RAW): entry(C, RAW, 20.0, rejected=True),
                (W, C): margin_over_wind(C, 6.0, CITIES[:3])})
    alt = out["alternatives_vs_default"][C]
    assert alt["consistently_better"] and alt["margin_over_default_amps"] == pytest.approx(6.0) and alt["cities_favoring"] == 3
    assert out["working_choice"] == C and out["action"]["ship"] == C and out["action"]["level"] == "supported"


def test_cooling_with_only_two_cities_keeps_wind():
    out = ship({(W, RAW): entry(W, RAW, 12.0, rejected=True), (C, RAW): entry(C, RAW, 20.0, rejected=True),
                (W, C): margin_over_wind(C, 6.0, CITIES[:2])})
    alt = out["alternatives_vs_default"][C]
    assert not alt["consistently_better"] and alt["cities_favoring"] == 2 and "favoured in only 2 of 4" in alt["reason"]
    assert out["working_choice"] == W


def test_cooling_below_x_with_four_of_four_cities_keeps_wind():
    out = ship({(W, RAW): entry(W, RAW, 12.0, rejected=True), (W, C): margin_over_wind(C, 4.0, CITIES)})
    alt = out["alternatives_vs_default"][C]
    assert alt["cities_favoring"] == 4 and not alt["consistently_better"] and "below 5" in alt["reason"]
    assert out["working_choice"] == W


def test_two_qualifying_alternatives_the_larger_pooled_margin_wins():
    out = ship({(W, RAW): entry(W, RAW, 12.0, rejected=True), (C, RAW): entry(C, RAW, 20.0, rejected=True),
                (R, RAW): entry(R, RAW, 25.0, rejected=True),
                (W, C): margin_over_wind(C, 6.0, CITIES), (W, R): margin_over_wind(R, 9.0, CITIES[:3])})
    assert out["alternatives_vs_default"][C]["consistently_better"] and out["alternatives_vs_default"][R]["consistently_better"]
    assert out["working_choice"] == R
    swapped = ship({(W, RAW): entry(W, RAW, 12.0, rejected=True), (C, RAW): entry(C, RAW, 20.0, rejected=True),
                    (R, RAW): entry(R, RAW, 25.0, rejected=True),
                    (W, C): margin_over_wind(C, 10.0, CITIES), (W, R): margin_over_wind(R, 9.0, CITIES)})
    assert swapped["working_choice"] == C


def test_switching_to_an_alternative_that_is_not_shown_against_raw_ships_raw():
    out = ship({(W, RAW): entry(W, RAW, 12.0, rejected=True), (R, RAW): entry(R, RAW, 1.0),
                (W, R): margin_over_wind(R, 6.0, CITIES)})
    assert out["working_choice"] == R and out["levels"][R]["level"] == "not shown"
    assert out["action"]["ship"] == RAW


def test_insufficient_data_keeps_wind_with_the_exact_statement():
    out = ship({(W, RAW): entry(W, RAW, 0.0, outcome="insufficient_data", n=5)})
    assert out["levels"][W]["level"] == "insufficient data"
    assert out["working_choice"] == W and out["action"]["ship"] == W and out["action"]["level"] == "insufficient data"
    assert "no evidence-based selection was possible; the provisional default is retained" in " ".join(out["statements"])
    assert dec.NO_SELECTION_STATEMENT == "no evidence-based selection was possible; the provisional default is retained"


def test_insufficient_data_for_a_switched_working_choice_keeps_wind_as_the_default_action():
    out = ship({(W, RAW): entry(W, RAW, 12.0, rejected=True), (C, RAW): entry(C, RAW, 0.0, outcome="insufficient_data", n=3),
                (W, C): margin_over_wind(C, 6.0, CITIES)})
    assert out["working_choice"] == C and out["levels"][C]["level"] == "insufficient data"
    assert out["action"]["ship"] == W and "provisional default is retained" in out["action"]["statement"]


def test_only_two_cities_with_data_makes_consistency_impossible():
    cm = {CITIES[0]: -6.0, CITIES[1]: -6.0, CITIES[2]: None, CITIES[3]: None}
    out = ship({(W, RAW): entry(W, RAW, 12.0, rejected=True), (W, C): entry(W, C, -6.0, city_margins=cm)})
    alt = out["alternatives_vs_default"][C]
    assert alt["cities_with_data"] == 2 and alt["consistency_possible"] is False and not alt["consistently_better"]
    assert "consistency impossible" in alt["reason"] and out["working_choice"] == W


def test_an_insufficient_wind_vs_alternative_comparison_never_qualifies():
    out = ship({(W, RAW): entry(W, RAW, 12.0, rejected=True),
                (W, C): entry(W, C, -9.0, outcome="insufficient_data", city_margins={c: -9.0 for c in CITIES}, n=4)})
    assert not out["alternatives_vs_default"][C]["consistently_better"] and out["working_choice"] == W


def test_unsigned_adds_the_exploratory_statement_and_signed_does_not():
    base = {(W, RAW): entry(W, RAW, 12.0, rejected=True)}
    unsigned = ship(base)
    signed = ship(base, protocol_status="signed")
    assert unsigned["protocol_status"] == "unsigned" and core.EXPLORATORY_STATEMENT in unsigned["statements"]
    assert core.EXPLORATORY_STATEMENT not in signed["statements"]
    for out in (unsigned, signed):
        assert core.NOT_MEASURED_STATEMENT in out["statements"]
        assert any(s.startswith("Sample size:") for s in out["statements"])


def test_sample_size_sentence_reports_unmet_targets_and_the_range():
    out = ship({}, )
    sentence = next(s for s in out["statements"] if s.startswith("Sample size:"))
    assert "120 to 120" in sentence and "590" in sentence and "1,575" in sentence and "not met" in sentence
    big = dec.apply_ship_rule(family(n=1600))
    assert "590-row target was met for 9 of 9" in next(s for s in big["statements"] if s.startswith("Sample size:"))


def test_mixed_row_sources_raise():
    fam = family({(W, RAW): entry(W, RAW, 12.0, rejected=True, row_source="shadow_logs")})
    with pytest.raises(ValueError, match="never combined"):
        dec.apply_ship_rule(fam)
    fam = family()
    fam["row_source"] = "shadow_logs"
    with pytest.raises(ValueError):
        dec.apply_ship_rule(fam)


def test_labels_follow_the_row_source():
    assert dec.apply_ship_rule(family())["label"] == "headline decision"
    assert dec.apply_ship_rule(family(row_source="shadow_logs", n=50))["label"] == "live-system check"


def test_runtime_modules_do_not_import_the_frozen_audit_or_name_its_gate_machinery():
    import ast
    import os
    import forecast_shadow_confirm as confirm_mod
    import forecast_shadow_score as score_mod
    import forecast_shadow_score_stats as stats_mod
    banned = {"CONFIRMATION_MINIMUM_ROWS", "basis_evaluation_report", "_fresh_confirmation_report", "build_basis_manifest",
              "fresh_basis_attempt", "minimum_fresh_rows"}
    for mod in (dec, core, score_mod, stats_mod, confirm_mod):
        tree = ast.parse(open(mod.__file__, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(a.name != "forecast_experiment_audit" for a in node.names), mod.__name__
            if isinstance(node, ast.ImportFrom):
                assert node.module != "forecast_experiment_audit", mod.__name__
            if isinstance(node, ast.Name):
                assert node.id not in banned, (mod.__name__, node.id)
            if isinstance(node, ast.Attribute):
                assert node.attr not in banned, (mod.__name__, node.attr)
            if isinstance(node, ast.arg):
                assert node.arg not in banned, (mod.__name__, node.arg)
    assert os.path.basename(dec.__file__) == "forecast_shadow_decision.py"


def test_missing_comparison_is_refused():
    fam = family()
    fam["comparisons"] = [c for c in fam["comparisons"] if (c["a"], c["b"]) != (W, RAW)]
    with pytest.raises(ValueError, match="no comparison"):
        dec.apply_ship_rule(fam)


# --------------------------------------------------------------------------
# combined_summary
# --------------------------------------------------------------------------

def report(row_source, n, over=None):
    fam = family(over, row_source=row_source, n=n)
    for c in fam["comparisons"]:
        c["row_source"] = row_source
    return {"row_source": row_source, "family": fam, "sample_size": fam["sample_size"],
            "decision": dec.apply_ship_rule(fam)}


def test_combined_summary_keeps_the_sources_separate_and_never_adds_counts():
    headline = report("reconstructed_frames", 190, {(W, RAW): entry(W, RAW, 12.0, rejected=True, n=190)})
    live = report("shadow_logs", 50, {(W, RAW): entry(W, RAW, 3.0, n=50, row_source="shadow_logs")})
    text = dec.combined_summary(headline, live)
    assert "240" not in text
    assert text.index("Headline decision") < text.index("Live-system check") < text.index("Agreement")
    assert "190 to 190" in text and "50 to 50" in text
    assert "The working choices agree: ml_wind_corrected (headline) and ml_wind_corrected (live-system check)" in text
    assert "ship ml_wind_corrected (supported)" in text and "ship raw_forecast (not shown)" in text
    assert "never changes the headline decision" in text and core.EXPLORATORY_STATEMENT in text
    assert core.NOT_MEASURED_STATEMENT in text


def test_combined_summary_reports_disagreement():
    headline = report("reconstructed_frames", 190, {(W, RAW): entry(W, RAW, 12.0, rejected=True, n=190), (C, RAW): entry(C, RAW, 20.0, rejected=True, n=190),
                                                      (W, C): margin_over_wind(C, 6.0, CITIES, n=190)})
    live = report("shadow_logs", 50)
    text = dec.combined_summary(headline, live)
    assert "The working choices differ: ml_cooling_corrected (headline) and ml_wind_corrected (live-system check)" in text


def test_combined_summary_refuses_swapped_or_duplicated_sources():
    headline = report("reconstructed_frames", 190)
    live = report("shadow_logs", 50)
    with pytest.raises(ValueError):
        dec.combined_summary(live, headline)
    with pytest.raises(ValueError):
        dec.combined_summary(headline, headline)
    with pytest.raises(ValueError):
        dec.combined_summary(live, live)
    broken = copy.deepcopy(live)
    broken["decision"] = None
    with pytest.raises(ValueError):
        dec.combined_summary(headline, broken)
    wrong = copy.deepcopy(live)
    wrong["decision"]["row_source"] = "reconstructed_frames"
    with pytest.raises(ValueError):
        dec.combined_summary(headline, wrong)
