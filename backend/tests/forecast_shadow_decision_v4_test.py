"""
Tests for `backend/forecast_shadow_decision_v4.py`, the signed v4 selection rule (07-05).

Every case is a synthetic family report: no statistics are run here, only the rule. The worked-example
mean truths are the non-FRESH ABLATION figures printed in the signing copy; no predicted-versus-truth
figure for a valid_time on or after 2026-09-30 is read or computed.
"""

from __future__ import annotations

import math

import pytest

import forecast_shadow_decision_v4 as dec
import forecast_shadow_eval_core as core
import protocol_v4_registry as reg

CITIES = ("AUSTIN", "CORPUS_CHRISTI", "MIDLAND", "EL_PASO")
W, C, R = "ml_wind_corrected", "ml_cooling_corrected", "reference_ml_refit_24h"
RAW = "raw_forecast"
MEANS = {"AUSTIN": 1257.8, "CORPUS_CHRISTI": 1375.8, "MIDLAND": 1525.4, "EL_PASO": 1236.8}
TRUTH = {c: {"mean_truth_amps": m, "n_truth_rows": 100} for c, m in MEANS.items()}
EXPECTED_BARS = {"AUSTIN": 25.156, "CORPUS_CHRISTI": 27.516, "MIDLAND": 30.508, "EL_PASO": 24.736}
POOLED_EQUAL = 26.979


def entry(a, b, margin=0.0, *, p=0.5, outcome=None, city_margins=None, rows=None, row_source="reconstructed_frames"):
    """One comparison. `rows` maps city -> n_paired (default 100 where the city has data)."""
    cm = city_margins if city_margins is not None else {c: margin for c in CITIES}
    rows = rows or {}
    per_city = {c: {"n_paired": (rows.get(c, 100) if v is not None else 0)} for c, v in cm.items()}
    n = sum(v["n_paired"] for v in per_city.values())
    with_data = [c for c, v in cm.items() if v is not None]
    if outcome is None:
        outcome = "inconclusive"
    return {
        "id": f"{a}__vs__{b}", "a": a, "b": b, "row_source": row_source, "flags": [], "n_paired": n, "n_nominal": n,
        "point_margin": margin, "per_city_margins": cm,
        "cities_favoring_a": sum(1 for c in with_data if cm[c] > 0), "cities_with_data": len(with_data),
        "headline": {"outcome": outcome, "holm_rejected": p <= 0.05 and outcome != "insufficient_data",
                     "p_holm_adjusted": p, "p_headline": p},
        "per_city": per_city,
    }


# --------------------------------------------------------------------------
# Bars
# --------------------------------------------------------------------------

def test_city_bars_are_two_percent_of_mean_truth():
    bars = dec.city_bars(TRUTH)
    assert {c: round(v, 3) for c, v in bars.items()} == EXPECTED_BARS


def test_city_bars_are_unrounded_float64():
    bars = dec.city_bars({"AUSTIN": {"mean_truth_amps": 1257.837, "n_truth_rows": 100}})
    assert bars["AUSTIN"] == dec.RELATIVE_MARGIN_FRACTION * 1257.837
    assert bars["AUSTIN"] != round(bars["AUSTIN"], 3)


def test_city_bar_is_none_for_a_city_without_truth_rows():
    stats = dict(TRUTH, MIDLAND={"mean_truth_amps": None, "n_truth_rows": 0})
    assert dec.city_bars(stats)["MIDLAND"] is None
    stats = dict(TRUTH, MIDLAND={"mean_truth_amps": 1525.4, "n_truth_rows": 0})
    assert dec.city_bars(stats)["MIDLAND"] is None


def test_city_bars_fraction_parameter():
    assert dec.city_bars(TRUTH, fraction=0.05)["EL_PASO"] == pytest.approx(0.05 * 1236.8)


def test_equal_rows_pooled_bar_matches_the_signing_copy_worked_example():
    pooled = dec.pooled_bar(entry(W, RAW, 30.0), dec.city_bars(TRUTH))
    assert round(pooled, 3) == POOLED_EQUAL


def test_pooled_bar_is_weighted_by_paired_rows():
    bars = dec.city_bars(TRUTH)
    rows = {"AUSTIN": 300, "CORPUS_CHRISTI": 100, "MIDLAND": 50, "EL_PASO": 50}
    pooled = dec.pooled_bar(entry(W, RAW, 30.0, rows=rows), bars)
    expected = sum(rows[c] * bars[c] for c in CITIES) / sum(rows.values())
    assert pooled == pytest.approx(expected, abs=1e-12)
    assert pooled != pytest.approx(POOLED_EQUAL, abs=0.1)


def test_pooled_bar_skips_cities_without_data_or_without_a_bar():
    bars = dec.city_bars(dict(TRUTH, MIDLAND={"mean_truth_amps": None, "n_truth_rows": 0}))
    cm = {"AUSTIN": 30.0, "CORPUS_CHRISTI": 30.0, "MIDLAND": 30.0, "EL_PASO": None}
    pooled = dec.pooled_bar(entry(W, RAW, 30.0, city_margins=cm), bars)
    assert pooled == pytest.approx((bars["AUSTIN"] + bars["CORPUS_CHRISTI"]) / 2, abs=1e-12)


def test_pooled_bar_is_none_when_no_city_has_both_rows_and_a_bar():
    cm = {c: None for c in CITIES}
    assert dec.pooled_bar(entry(W, RAW, 30.0, city_margins=cm), dec.city_bars(TRUTH)) is None
    assert dec.pooled_bar(entry(W, RAW, 30.0), {c: None for c in CITIES}) is None


# --------------------------------------------------------------------------
# Evidence levels
# --------------------------------------------------------------------------

BAR = 26.979


def level(margin, *, p=0.5, outcome=None, bar=BAR, alpha=0.05):
    return dec.evidence_level_v4(entry(W, RAW, margin, p=p, outcome=outcome), bar, alpha)


def test_benefit_exactly_equal_to_the_bar_meets_it():
    out = level(BAR)
    assert out["level"] == "indicated, not resolved"
    assert out["benefit_amps"] == BAR and out["bar_amps"] == BAR


def test_benefit_one_ulp_below_the_bar_is_not_shown():
    assert level(math.nextafter(BAR, 0.0))["level"] == "not shown"


def test_benefit_equal_to_the_unrounded_pooled_bar_meets_it():
    pooled = dec.pooled_bar(entry(W, RAW, 0.0), dec.city_bars(TRUTH))
    assert dec.evidence_level_v4(entry(W, RAW, pooled), pooled, 0.05)["level"] == "indicated, not resolved"
    assert dec.evidence_level_v4(entry(W, RAW, pooled - 1e-12), pooled, 0.05)["level"] == "not shown"


def test_holm_adjusted_p_within_alpha_makes_it_supported():
    assert level(BAR + 5.0, p=0.05)["level"] == "supported"
    assert level(BAR + 5.0, p=0.01)["level"] == "supported"


def test_holm_adjusted_p_above_alpha_stays_indicated():
    assert level(BAR + 5.0, p=0.0501)["level"] == "indicated, not resolved"
    assert dec.evidence_level_v4(entry(W, RAW, BAR + 5.0, p=0.04), BAR, 0.025)["level"] == "indicated, not resolved"


def test_below_the_bar_is_not_shown_even_with_a_tiny_p_value():
    assert level(20.0, p=0.0001)["level"] == "not shown"


def test_negative_benefit_is_not_shown():
    assert level(-4.0, p=0.0001)["level"] == "not shown"


def test_insufficient_data_outcome_or_missing_inputs():
    assert level(40.0, outcome="insufficient_data")["level"] == "insufficient data"
    assert level(None)["level"] == "insufficient data"
    assert level(40.0, bar=None)["level"] == "insufficient data"


def test_level_record_carries_its_evidence():
    out = level(BAR + 1.0, p=0.01, outcome="favors_A")
    assert out["holm_rejected"] is True and out["p_holm_adjusted"] == 0.01
    assert out["outcome"] == "favors_A" and out["n_paired"] == 400
    assert dec.EVIDENCE_LEVELS == ("supported", "indicated, not resolved", "not shown", "insufficient data")


# --------------------------------------------------------------------------
# Consistency
# --------------------------------------------------------------------------

def cm_of(*values):
    return dict(zip(CITIES, values))


def test_three_of_four_cities_favouring_is_consistent():
    out = dec.consistency(entry(W, RAW, 30.0, city_margins=cm_of(30.0, 30.0, 30.0, -5.0)), dec.city_bars(TRUTH), 3)
    assert out["cities_with_data"] == 4 and out["cities_favoring"] == 3
    assert out["possible"] is True and out["consistent"] is True


def test_two_of_four_cities_favouring_is_not_consistent():
    out = dec.consistency(entry(W, RAW, 30.0, city_margins=cm_of(30.0, 30.0, -1.0, -5.0)), dec.city_bars(TRUTH), 3)
    assert out["cities_favoring"] == 2 and out["consistent"] is False
    assert out["possible"] is True and "2 of 4" in out["reason"]


def test_a_zero_margin_city_does_not_favour_the_candidate():
    out = dec.consistency(entry(W, RAW, 30.0, city_margins=cm_of(30.0, 30.0, 0.0, 0.0)), dec.city_bars(TRUTH), 3)
    assert out["cities_favoring"] == 2 and out["consistent"] is False


def test_three_cities_with_data_all_favouring_is_consistent():
    out = dec.consistency(entry(W, RAW, 30.0, city_margins=cm_of(30.0, 30.0, 30.0, None)), dec.city_bars(TRUTH), 3)
    assert out["cities_with_data"] == 3 and out["possible"] is True and out["consistent"] is True


def test_two_cities_with_data_cannot_be_consistent_and_the_reason_names_the_count():
    out = dec.consistency(entry(W, RAW, 30.0, city_margins=cm_of(30.0, 30.0, None, None)), dec.city_bars(TRUTH), 3)
    assert out["cities_with_data"] == 2 and out["cities_favoring"] == 2
    assert out["possible"] is False and out["consistent"] is False
    assert "2 cities" in out["reason"]


def test_per_city_scope_needs_each_city_to_reach_its_own_bar():
    bars = dec.city_bars(TRUTH)
    cm = cm_of(bars["AUSTIN"], bars["CORPUS_CHRISTI"], bars["MIDLAND"] - 0.001, 40.0)
    out = dec.consistency(entry(W, RAW, 30.0, city_margins=cm), bars, 3, scope="per_city")
    assert out["cities_favoring"] == 3 and out["consistent"] is True
    cm = cm_of(bars["AUSTIN"], bars["CORPUS_CHRISTI"] - 0.001, bars["MIDLAND"] - 0.001, 40.0)
    out = dec.consistency(entry(W, RAW, 30.0, city_margins=cm), bars, 3, scope="per_city")
    assert out["cities_favoring"] == 2 and out["consistent"] is False


# --------------------------------------------------------------------------
# Constants pinned to the signed registry (T-07-11)
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def registry():
    assert reg.is_signed(reg.SIGNING_COPY_PATH), "the signing copy must be signed before v4 code is checked against it"
    return reg.parse_registry(reg.SIGNING_COPY_PATH)


def test_constants_match_the_signed_registry(registry):
    assert dec.RELATIVE_MARGIN_FRACTION == float(registry["rule.relative_margin_fraction"])
    assert dec.BAR_SCOPE == registry["rule.bar_scope"]
    assert dec.CONSISTENCY_MIN_CITIES == int(registry["rule.consistency_min_cities"])
    assert dec.TIE_ORDER == tuple(reg.as_list(registry["rule.tie_order"]))
    assert dec.FAMILY_ALPHA_BY_ROUND == {
        registry["read1.name"]: float(registry["read1.family_alpha"]),
        registry["read2.name"]: float(registry["read2.family_alpha"]),
        registry["late.name"]: float(registry["read1.family_alpha"]),
    }
    assert registry["rule.alternative_vs_default_bar"] == "relative"


def test_read2_requires_supported_follows_the_signed_o2_choice(registry):
    # O2 was signed as option A (same rules at both reads, alpha 0.05): "supported" is not required.
    assert dec.READ2_REQUIRES_SUPPORTED is False
    assert registry["read1.family_alpha"] == registry["read2.family_alpha"] == "0.05"


def test_tie_order_names_exactly_the_real_candidates():
    assert set(dec.TIE_ORDER) == set(core.REAL_CANDIDATES) and dec.TIE_ORDER[0] == core.DEFAULT_CHOICE


# ==========================================================================
# Task 2: vetoes, pick or no pick, labels, side-by-side summary
# ==========================================================================

NOVETO = {"ablation": {}, "test": {}}
LIVE = "shadow_logs"


def family(overrides=None, row_source="reconstructed_frames"):
    overrides = overrides or {}
    comps = [overrides.get((a, b)) or entry(a, b, 0.0, row_source=row_source) for a, b in core.HEADLINE_FAMILY]
    pairs = [{"a": c["a"], "b": c["b"], "n_paired": c["n_paired"], "targets": core.precision_targets(c["n_paired"])}
             for c in comps]
    return {"row_source": row_source, "family_size": 9, "comparisons": comps,
            "sample_size": {"pairs": pairs, "n_scored": {}, "targets_met": {}}}


def good(cand, benefit=40.0, *, p=0.01, city_margins=None, row_source="reconstructed_frames"):
    """(cand, raw_forecast) entry that favours `cand` by `benefit` A."""
    return {(cand, RAW): entry(cand, RAW, benefit, p=p, outcome="favors_A", city_margins=city_margins,
                               row_source=row_source)}


def over(alt, amount, favoured=CITIES, *, row_source="reconstructed_frames"):
    """(wind, alt) entry: alt beats wind by `amount` A in the `favoured` cities (negative margin = alt better)."""
    cm = {c: (-amount if c in favoured else +amount) for c in CITIES}
    return {(W, alt): entry(W, alt, -amount, city_margins=cm, row_source=row_source)}


def fam(*parts, **kw):
    merged = {}
    for part in parts:
        merged.update(part)
    return family(merged, **kw)


def run(family_report, **kw):
    kw.setdefault("truth_stats", TRUTH)
    kw.setdefault("round_name", "v4-read1")
    kw.setdefault("vetoes", NOVETO)
    kw.setdefault("protocol_status", "signed")
    return dec.apply_ship_rule_v4(family_report, **kw)


def veto(ablation=(), test=()):
    return {"ablation": {c: {"vetoed": True} for c in ablation}, "test": {c: {"vetoed": True} for c in test}}


def text(out):
    return " ".join(out["statements"] + out["reasons"])


# --- the pick ---------------------------------------------------------------

def test_wind_alone_qualifying_is_picked():
    out = run(fam(good(W)))
    assert out["pick"] == W and out["rule_outcome"] == W and out["qualifying"] == [W]
    assert out["rule"] == "v4" and out["round"] == "v4-read1" and out["label"] == dec.LABELS["headline"]
    assert any(W in s for s in out["statements"])


def test_pooled_bar_by_comparison_and_levels_are_reported():
    out = run(fam(good(W)))
    pooled = out["bars"]["pooled_by_comparison"][f"{W}__vs__{RAW}"]
    assert round(pooled, 3) == POOLED_EQUAL
    assert {c: round(v, 3) for c, v in out["bars"]["per_city"].items()} == EXPECTED_BARS
    assert out["levels"][W]["level"] == "supported" and out["levels"][C]["level"] == "not shown"
    assert out["consistency"][W]["consistent"] is True and out["fraction"] == dec.RELATIVE_MARGIN_FRACTION


def test_benefit_exactly_at_the_pooled_bar_qualifies_but_one_ulp_below_does_not():
    pooled = dec.pooled_bar(entry(W, RAW, 0.0), dec.city_bars(TRUTH))
    out = run(fam(good(W, pooled, p=0.5)))
    assert out["levels"][W]["level"] == "indicated, not resolved" and out["pick"] == W
    out = run(fam(good(W, math.nextafter(pooled, 0.0), p=0.5)))
    assert out["levels"][W]["level"] == "not shown" and out["pick"] is None


def test_wind_below_the_bar_is_not_shown_and_nothing_qualifies():
    out = run(fam(good(W, 20.0, p=0.0001)))
    assert out["pick"] is None and out["qualifying"] == []


def test_a_level_without_three_favouring_cities_does_not_qualify():
    cm = {"AUSTIN": 90.0, "CORPUS_CHRISTI": 90.0, "MIDLAND": -5.0, "EL_PASO": -5.0}
    out = run(fam(good(W, 40.0, city_margins=cm)))
    assert out["levels"][W]["level"] == "supported" and out["consistency"][W]["consistent"] is False
    assert out["pick"] is None


def test_wind_wins_unless_an_alternative_is_consistently_better_by_the_bar():
    # cooling qualifies, but only 10 A better than wind (bar about 27 A): wind stays
    out = run(fam(good(W), good(C, 45.0), over(C, 10.0)))
    assert out["qualifying"] == [W, C] and out["pick"] == W
    assert out["alternatives_vs_default"][C]["consistently_better"] is False


def test_alternative_better_by_the_bar_but_favoured_in_only_two_cities_does_not_displace_wind():
    out = run(fam(good(W), good(C, 70.0), over(C, 30.0, favoured=CITIES[:2])))
    assert out["alternatives_vs_default"][C]["consistently_better"] is False and out["pick"] == W


def test_alternative_consistently_better_than_wind_is_picked():
    out = run(fam(good(W), good(C, 70.0), over(C, 30.0, favoured=CITIES[:3])))
    alt = out["alternatives_vs_default"][C]
    assert alt["consistently_better"] is True and alt["margin_over_default_amps"] == pytest.approx(30.0)
    assert out["pick"] == C and out["rule_outcome"] == C


def test_alternative_margin_exactly_at_its_pooled_bar_displaces_wind():
    bar = dec.pooled_bar(entry(W, C, 0.0), dec.city_bars(TRUTH))
    assert run(fam(good(W), good(C, 70.0), over(C, bar)))["pick"] == C
    assert run(fam(good(W), good(C, 70.0), over(C, math.nextafter(bar, 0.0))))["pick"] == W


def test_the_larger_margin_over_wind_wins_between_two_alternatives():
    out = run(fam(good(W), good(C, 70.0), good(R, 70.0), over(C, 28.0), over(R, 35.0)))
    assert out["pick"] == R and "larger pooled margin" in text(out)
    out = run(fam(good(W), good(C, 70.0), good(R, 70.0), over(C, 40.0), over(R, 35.0)))
    assert out["pick"] == C


def test_an_exact_tie_between_alternatives_follows_the_fixed_order_not_dict_order():
    parts = [good(W), good(C, 70.0), good(R, 70.0), over(C, 35.0), over(R, 35.0)]
    forward = fam(*parts)
    reverse = fam(*parts)
    reverse["comparisons"] = list(reversed(reverse["comparisons"]))
    assert run(forward)["pick"] == C and run(reverse)["pick"] == C
    # and with the veto record keyed in the opposite order
    assert run(forward, vetoes={"test": {R: {"vetoed": False}, C: {"vetoed": False}}, "ablation": {}})["pick"] == C


def test_when_wind_does_not_qualify_the_qualifying_reference_is_picked():
    out = run(fam(good(W, 5.0), good(R, 40.0)))
    assert out["pick"] == R and out["qualifying"] == [R]


def test_when_wind_does_not_qualify_the_larger_benefit_over_raw_wins():
    out = run(fam(good(W, 5.0), good(C, 40.0), good(R, 55.0)))
    assert out["pick"] == R
    out = run(fam(good(W, 5.0), good(C, 60.0), good(R, 55.0)))
    assert out["pick"] == C


def test_when_wind_does_not_qualify_an_exact_benefit_tie_follows_the_fixed_order():
    assert run(fam(good(W, 5.0), good(C, 40.0), good(R, 40.0)))["pick"] == C


def test_wind_displaced_only_by_alternatives_that_themselves_qualify():
    # reference is 40 A better than wind but is not shown against raw: it must not be picked
    out = run(fam(good(W), good(R, 10.0), over(R, 40.0)))
    assert out["pick"] == W and out["levels"][R]["level"] == "not shown"


def test_persistence_is_never_picked():
    out = run(fam(good(W)))
    assert out["pick"] in dec.TIE_ORDER


# --- vetoes -----------------------------------------------------------------

def test_an_ablation_vetoed_candidate_never_qualifies_whatever_its_result():
    out = run(fam(good(W, 90.0)), vetoes=veto(ablation=[W]))
    assert out["pick"] is None and out["qualifying"] == []
    assert out["vetoes"][W]["vetoed"] is True and out["vetoes"][W]["ablation"] is True
    assert "veto" in text(out).lower() and "ablation" in text(out).lower()


def test_a_test_vetoed_candidate_never_qualifies():
    out = run(fam(good(W, 90.0)), vetoes=veto(test=[W]))
    assert out["pick"] is None and out["vetoes"][W]["test"] is True and out["vetoes"][W]["ablation"] is False


def test_best_candidate_vetoed_by_ablation_is_never_picked_and_wind_stays():
    out = run(fam(good(W), good(C, 90.0), over(C, 60.0)), vetoes=veto(ablation=[C]))
    assert out["pick"] == W and C not in out["qualifying"]
    assert out["vetoes"][C]["vetoed"] is True and "veto" in text(out).lower()


def test_vetoed_wind_hands_the_pick_to_a_qualifying_alternative():
    out = run(fam(good(W, 90.0), good(R, 40.0)), vetoes=veto(test=[W]))
    assert out["pick"] == R


def test_a_missing_candidate_in_the_veto_record_means_not_vetoed_and_records_the_source():
    out = run(fam(good(W)), vetoes={"ablation": {C: {"vetoed": False}}, "test": {}})
    assert out["vetoes"][W]["vetoed"] is False and out["vetoes"][W]["source"] == "no veto entry for this candidate"
    assert out["vetoes"][C]["vetoed"] is False and out["vetoes"][C]["source"] == "ablation"


def test_headline_needs_the_veto_record_when_required():
    with pytest.raises(ValueError, match="SEL-03"):
        dec.apply_ship_rule_v4(fam(good(W)), truth_stats=TRUTH, round_name="v4-read1", vetoes=None)
    with pytest.raises(ValueError, match="SEL-03"):
        dec.apply_ship_rule_v4(fam(good(W)), truth_stats=TRUTH, round_name="v4-read1", vetoes=None, require_vetoes=True)


def test_development_basis_decides_as_if_nothing_were_vetoed_with_an_exploratory_statement():
    out = dec.apply_ship_rule_v4(fam(good(W)), truth_stats=TRUTH, round_name="v4-read1", vetoes=None,
                                 require_vetoes=False, protocol_status="signed")
    assert out["pick"] == W
    assert "no ABLATION/TEST veto record was applied (development basis)" in out["statements"]
    assert core.EXPLORATORY_STATEMENT in out["statements"]
    assert all(v["vetoed"] is False for v in out["vetoes"].values())


# --- no pick and the round statements ---------------------------------------

def test_no_pick_statement_and_the_read2_schedule_for_read1():
    out = run(fam(good(W, 20.0)))
    assert out["pick"] is None and dec.NO_PICK_STATEMENT in out["statements"]
    assert dec.READ2_SCHEDULED_STATEMENT in out["statements"]
    assert "v4-read2" in dec.READ2_SCHEDULED_STATEMENT and "2026-11-08T00:00:00Z" in dec.READ2_SCHEDULED_STATEMENT
    assert "no shadow model replaces ml" in dec.NO_PICK_STATEMENT


def test_read2_with_no_winner_states_the_signed_o3_outcome():
    out = run(fam(good(W, 20.0)), round_name="v4-read2")
    assert out["pick"] is None and dec.NO_PICK_STATEMENT in out["statements"]
    assert dec.READ2_NO_WINNER_STATEMENT in out["statements"]
    assert dec.READ2_SCHEDULED_STATEMENT not in out["statements"]
    assert "G6" in dec.READ2_NO_WINNER_STATEMENT and "new signed protocol" in dec.READ2_NO_WINNER_STATEMENT


def test_late_descriptive_round_adds_no_read2_sentence():
    out = run(fam(good(W, 20.0)), round_name="v4-late-descriptive")
    assert dec.READ2_SCHEDULED_STATEMENT not in out["statements"] and dec.READ2_NO_WINNER_STATEMENT not in out["statements"]


def test_fewer_than_three_cities_with_data_gives_no_pick_and_names_the_count():
    cm = {"AUSTIN": 90.0, "CORPUS_CHRISTI": 90.0, "MIDLAND": None, "EL_PASO": None}
    out = run(fam(good(W, 90.0, city_margins=cm), good(C, 90.0, city_margins=cm), good(R, 90.0, city_margins=cm)))
    assert out["pick"] is None and out["qualifying"] == []
    assert "2 cities" in text(out)


def test_a_failed_city_counts_as_no_data_so_three_remaining_cities_can_still_decide():
    cm = {"AUSTIN": 90.0, "CORPUS_CHRISTI": 90.0, "MIDLAND": 90.0, "EL_PASO": None}
    assert run(fam(good(W, 90.0, city_margins=cm)))["pick"] == W


def test_all_comparisons_insufficient_gives_no_pick():
    cm = {c: None for c in CITIES}
    ins = {(x, RAW): entry(x, RAW, None, outcome="insufficient_data", city_margins=cm) for x in core.REAL_CANDIDATES}
    out = run(family(ins))
    assert out["pick"] is None and out["levels"][W]["level"] == "insufficient data"
    assert "0 cities" in text(out)


# --- labels, refusals, parameters ------------------------------------------

@pytest.mark.parametrize("label", ["secondary", "live", "descriptive"])
def test_non_headline_labels_compute_levels_but_never_pick(label):
    out = run(fam(good(W)), label=label, vetoes=None)
    assert out["pick"] is None and out["rule_outcome"] == W
    assert out["label"] == dec.LABELS[label] and out["levels"][W]["level"] == "supported"
    assert any("never decides" in s or "cannot overturn" in s for s in out["statements"])


def test_non_headline_label_with_no_qualifier_reports_would_be_none():
    out = run(fam(good(W, 20.0)), label="secondary", vetoes=None)
    assert out["pick"] is None and out["rule_outcome"] is None
    assert dec.READ2_SCHEDULED_STATEMENT not in out["statements"]


def test_mixed_row_sources_are_refused():
    bad = fam(good(W), good(C, row_source=LIVE))
    with pytest.raises(ValueError, match="row sources"):
        run(bad)


def test_report_row_source_must_match_its_comparisons():
    with pytest.raises(ValueError, match="row source"):
        run(dict(fam(good(W)), row_source=LIVE))


def test_a_headline_decision_is_refused_for_the_shadow_log_row_source():
    live = fam(good(W, row_source=LIVE), row_source=LIVE)
    with pytest.raises(ValueError, match="never decides"):
        run(live)
    assert run(live, label="live", vetoes=None)["pick"] is None


def test_unknown_round_or_label_is_refused():
    with pytest.raises(ValueError, match="round"):
        run(fam(good(W)), round_name="v4-read9")
    with pytest.raises(ValueError, match="label"):
        run(fam(good(W)), label="headliner")


def test_a_missing_comparison_is_refused():
    f = fam(good(W))
    f["comparisons"] = [c for c in f["comparisons"] if (c["a"], c["b"]) != (R, RAW)]
    with pytest.raises(ValueError, match="no comparison"):
        run(f)


def test_min_cities_and_alpha_overrides_are_honoured_and_recorded():
    f = fam(good(W, p=0.04))
    assert run(f)["levels"][W]["level"] == "supported"
    assert run(f, alpha=0.025)["levels"][W]["level"] == "indicated, not resolved"
    out = run(f, min_cities=4)
    assert out["pick"] == W and out["consistency"][W]["consistent"] is True
    cm = {"AUSTIN": 40.0, "CORPUS_CHRISTI": 40.0, "MIDLAND": 40.0, "EL_PASO": -1.0}
    assert run(fam(good(W, 40.0, city_margins=cm)), min_cities=4)["pick"] is None


def test_fraction_override_changes_the_bars_and_is_recorded():
    out = run(fam(good(W, 40.0)), fraction=0.04)
    assert out["fraction"] == 0.04 and out["pick"] is None  # 40 A < 4% bar of about 54 A


def test_read2_requires_supported_when_the_registry_says_so(monkeypatch):
    f = fam(good(W, 40.0, p=0.5))
    assert run(f, round_name="v4-read2")["pick"] == W
    monkeypatch.setattr(dec, "READ2_REQUIRES_SUPPORTED", True)
    assert run(f, round_name="v4-read2")["pick"] is None
    assert run(f, round_name="v4-read1")["pick"] == W
    assert run(fam(good(W, 40.0, p=0.01)), round_name="v4-read2")["pick"] == W


def test_statements_carry_the_standing_caveats():
    unsigned = run(fam(good(W)), protocol_status="unsigned")
    signed = run(fam(good(W)))
    for out in (signed, unsigned):
        assert out["statements"][0].startswith("Sample size:")
        assert core.NOT_MEASURED_STATEMENT in out["statements"] and core.TRUTH_LABEL + "." in out["statements"]
    assert core.EXPLORATORY_STATEMENT in unsigned["statements"] and core.EXPLORATORY_STATEMENT not in signed["statements"]


# --- the side-by-side summary ----------------------------------------------

def report(out, row_source):
    return {"row_source": row_source, "decision": out, "sample_size": {"pairs": [{"n_paired": 400}]}}


def three_reports():
    head = report(run(fam(good(W))), "reconstructed_frames")
    live = report(run(fam(good(R, row_source=LIVE), row_source=LIVE), label="live", vetoes=None), LIVE)
    sec = report(run(fam(good(C)), label="secondary", vetoes=None), "reconstructed_frames")
    return head, live, sec


def test_combined_summary_v4_renders_headline_live_and_secondary_blocks():
    head, live, sec = three_reports()
    md = dec.combined_summary_v4(head, live, sec)
    for needle in ("Headline decision", "Live-system check", "Secondary", "AUSTIN 25.16 A", "EL_PASO 24.74 A", W,
                   "never changes the headline", core.NOT_MEASURED_STATEMENT):
        assert needle in md
    assert "Pick: ml_wind_corrected" in md


def test_combined_summary_v4_without_a_secondary_block():
    head, live, _ = three_reports()
    md = dec.combined_summary_v4(head, live)
    assert "Headline decision" in md and "Secondary" not in md


def test_combined_summary_v4_states_no_pick():
    head = report(run(fam(good(W, 20.0))), "reconstructed_frames")
    _, live, _ = three_reports()
    assert "No pick" in dec.combined_summary_v4(head, live)


def test_combined_summary_v4_refuses_swapped_or_duplicated_sources():
    head, live, sec = three_reports()
    with pytest.raises(ValueError, match="never swapped or duplicated"):
        dec.combined_summary_v4(live, head)
    with pytest.raises(ValueError, match="never swapped or duplicated"):
        dec.combined_summary_v4(head, head)
    with pytest.raises(ValueError, match="never swapped or duplicated"):
        dec.combined_summary_v4(head, live, live)
    with pytest.raises(ValueError, match="never swapped or duplicated"):
        dec.combined_summary_v4(head, live, head)


def test_combined_summary_v4_requires_a_decision_with_the_right_label():
    head, live, sec = three_reports()
    with pytest.raises(ValueError, match="decision"):
        dec.combined_summary_v4({"row_source": "reconstructed_frames"}, live)
    with pytest.raises(ValueError, match="label"):
        dec.combined_summary_v4(head, dict(live, decision=run(fam(good(R, row_source=LIVE), row_source=LIVE),
                                                              label="descriptive", vetoes=None)))
    with pytest.raises(ValueError, match="label"):
        dec.combined_summary_v4(head, live, dict(sec, decision=head["decision"]))
