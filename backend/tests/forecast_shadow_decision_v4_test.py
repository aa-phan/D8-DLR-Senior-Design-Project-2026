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
    bars = dec.city_bars(TRUTH)
    assert bars["AUSTIN"] == dec.RELATIVE_MARGIN_FRACTION * 1257.8
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
