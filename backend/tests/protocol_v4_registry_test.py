"""
Registry parity for confirmation protocol v4 (07-10, SEL-01, SEL-03, T-07-22).

Every key of the signed registry (`## Registered values (machine-checked)` of the SIGNING COPY the owner signed on
2026-11-02) is pinned here either to a code constant that must equal it (`CODE_MAP`), to a state-aware check for the
rows whose code counterpart is the production conductor table (`STATE_CHECKS`: the owner's AUSTIN switch lands in a
later plan), or to the explicit `DOC_ONLY_KEYS` list of rows with no code counterpart. A key in none of the three
fails `test_every_registry_key_is_mapped`, so a value added to the signed document without a code check cannot slip
in, and a code constant that differs from the signature fails its own parametrized case. The signed copy is never
edited to make a case pass.

This module only reads the Markdown registry and imports constants; it never touches a scorer, a log or any FRESH
data.
"""

from __future__ import annotations

import os

import pandas as pd
import pytest

import config
import forecast_conductor_ablation as ablation
import forecast_conductor_refit as refit
import forecast_experiment_audit as audit
import forecast_shadow_confirm as confirm
import forecast_shadow_decision_v4 as decision
import forecast_shadow_eval_core as core
import forecast_shadow_fit_models as fit_models
import forecast_test_split_score as test_split
import protocol_v4_registry as reg

SIGNED = reg.parse_registry(reg.SIGNING_COPY_PATH)


def _round(name: str) -> core.ProtocolRound:
    return core.PROTOCOL_ROUNDS[name]


def _utc(value: str) -> pd.Timestamp:
    return pd.Timestamp(value, tz="UTC")


def _variants_in_registry() -> list[str]:
    return reg.as_list(SIGNED["ablation.variants"])


def _variant_by_name(name: str) -> dict:
    return next(v for v in ablation.BRACKETING_SET if v["name"] == name)


def _variant_value(name: str) -> dict:
    """A code variant in the shape of its registry row: numbers as floats and `cities` as `all` or a comma list."""
    v = _variant_by_name(name)
    cities = v["cities"] if v["cities"] == "all" else ",".join(v["cities"])
    return {"diameter_m": float(v["diameter_m"]), "resistance_ac": float(v["resistance_ac"]),
            "max_temp_c": float(v["max_temp_c"]), "elevation_m": float(v["elevation_m"]), "cities": cities}


def _parse_fields(value: str) -> dict:
    """`a=1;b=x` to {"a": 1.0, "b": "x"}: numeric fields become floats, the rest stay text."""
    out: dict = {}
    for part in value.split(";"):
        key, _, raw = part.partition("=")
        try:
            out[key] = float(raw)
        except ValueError:
            out[key] = raw
    return out


# --------------------------------------------------------------------------
# Registry key -> the code value that must equal it
# --------------------------------------------------------------------------

CODE_MAP: dict = {
    # shared instants and the three named rounds (forecast_shadow_eval_core)
    "v3_retired_instant": lambda: core.V3_RETIRED_INSTANT,
    "fresh_basis_start": lambda: core.FRESH_BASIS_START,
    "model_freeze": lambda: core.MODEL_FREEZE,
    "late.name": lambda: _round("v4-late-descriptive").name,
    **{f"read{n}.{field}": (lambda n=n, field=field: getattr(_round(f"v4-read{n}"), {
        "name": "name", "instant": "instant", "cutoff": "cutoff", "fetch_start": "fetch_start",
        "fetch_end": "fetch_end", "slots_per_city": "slots_per_city"}[field]))
       for n in (1, 2) for field in ("name", "instant", "cutoff", "fetch_start", "fetch_end", "slots_per_city")},
    # the selection rule (forecast_shadow_decision_v4) and the statistical defaults (eval core)
    "read1.family_alpha": lambda: decision.FAMILY_ALPHA_BY_ROUND["v4-read1"],
    "read2.family_alpha": lambda: decision.FAMILY_ALPHA_BY_ROUND["v4-read2"],
    "rule.relative_margin_fraction": lambda: decision.RELATIVE_MARGIN_FRACTION,
    "rule.bar_scope": lambda: decision.BAR_SCOPE,
    "rule.consistency_min_cities": lambda: decision.CONSISTENCY_MIN_CITIES,
    "rule.tie_order": lambda: list(decision.TIE_ORDER),
    "rule.family_size": lambda: core.FAMILY_SIZE,
    "rule.block_lengths": lambda: list(core.BLOCK_LENGTHS_SLOTS),
    "rule.n_resamples": lambda: core.N_RESAMPLES,
    # ABLATION (forecast_conductor_ablation)
    "ablation.train_end": lambda: ablation.TRAIN_END,
    "ablation.validation_start": lambda: ablation.VALIDATION_START,
    "ablation.validation_end_exclusive": lambda: ablation.VALIDATION_END_EXCLUSIVE,
    "ablation.train_rows_per_city": lambda: ablation.TRAIN_ROWS_PER_CITY,
    "ablation.validation_rows_per_city": lambda: ablation.VALIDATION_ROWS_PER_CITY,
    "ablation.control": lambda: ablation.CONTROL,
    "ablation.variants": lambda: [v["name"] for v in ablation.BRACKETING_SET],
    "ablation.veto_rule": lambda: ablation.VETO_RULE,
    **{f"ablation.variant.{name}": (lambda name=name: _variant_value(name)) for name in _variants_in_registry()},
    # TEST (forecast_test_split_score)
    "test.window_start": lambda: test_split.TEST_WINDOW_START,
    "test.window_end_exclusive": lambda: test_split.TEST_WINDOW_END_EXCLUSIVE,
    "test.slots_per_city": lambda: test_split.TEST_SLOTS_PER_CITY,
    "test.veto_min_cities": lambda: test_split.VETO_MIN_CITIES,
    "test.rescore_gate": lambda: test_split.RESCORE_GATE,
    # refit (forecast_conductor_refit); the fit ends the day before the frozen test split starts
    "refit.methods": lambda: list(refit.REFIT_METHODS),
    "refit.root": lambda: refit.REFIT_ROOT.replace(os.sep, "/"),
    "refit.fit_end_exclusive": lambda: _utc(audit.FROZEN_TEST_SPLIT_START),
}


# --------------------------------------------------------------------------
# Rows whose code counterpart is the production conductor table (the AUSTIN switch of owner item O4)
# --------------------------------------------------------------------------

def _provisional() -> bool:
    """True while the production table is still the v2 provisional Drake table (the O4 switch is not applied yet)."""
    return config.RATING_CONFIG_VERSION.startswith("v2-provisional")


def _differing_cities() -> list[str]:
    return sorted(c for c in config.LOCATIONS if refit.production_differs(c))


def _check_switch_cities(signed: str) -> None:
    cities = reg.as_list(signed)
    assert cities and set(cities) <= set(config.LOCATIONS)
    if _provisional():
        assert _differing_cities() == [], "the provisional table is at parity with the frozen Drake points"
    else:
        assert _differing_cities() == sorted(cities), (
            "after the O4 switch exactly the signed cities differ from the frozen Drake points")


def _check_refit_cities(signed: str) -> None:
    cities = reg.as_list(signed)
    assert sorted(cities) == sorted(reg.as_list(SIGNED["power_systems.switch_cities"])), (
        "the cities that are refit are the cities that switch conductor")
    if not _provisional():
        basis = confirm.conductor_basis(list(config.LOCATIONS))
        assert sorted(basis["differing"]) == sorted(cities)
        assert basis["problems"] == [], f"refit or frozen artifacts are not sound: {basis['problems']}"
        assert {(a["city"], a["method"]) for a in basis["refit_artifacts"]} == {
            (c, m) for c in cities for m in refit.REFIT_METHODS}


def _check_austin_config(signed: str) -> None:
    fields = _parse_fields(signed)
    assert fields["cities"] == "AUSTIN"
    table = config.PRODUCTION_CONDUCTORS["AUSTIN"]
    # the numbers the signature does not change are exactly the table's and the ABLATION Drake-100 bracket's
    drake100 = _variant_value("Drake-100")
    for key in ("diameter_m", "resistance_ac", "max_temp_c", "elevation_m"):
        assert fields[key] == drake100[key], f"{key}: the signed AUSTIN configuration is the ABLATION Drake-100 bracket"
    for key in ("diameter_m", "resistance_ac", "elevation_m", "line_azimuth"):
        assert float(table[key]) == fields[key], f"{key}: the production table row for AUSTIN"
    assert float(config.CITY_LINE_BEARING_DEG["AUSTIN"]) == fields["line_azimuth"]
    assert float(table["max_temp_c"]) == (75.0 if _provisional() else fields["max_temp_c"]), (
        "AUSTIN stays at the provisional 75 C until the O4 switch is applied, then equals the signed 100 C")


STATE_CHECKS: dict = {
    "power_systems.switch_cities": _check_switch_cities,
    "refit.cities": _check_refit_cities,
    "power_systems.austin_config": _check_austin_config,
}

# Rows with no code counterpart: provenance and process statements. Each says why.
DOC_ONLY_KEYS: dict = {
    "protocol_version": "document label",
    "amends": "names the amended document",
    "power_systems_deadline": "a dated owner deadline that has passed; nothing in code reads it",
    "power_systems.partial_answers": "the owner's O4 choice, enforced through the production table (STATE_CHECKS)",
    "read2.runs_only_if": "an operating condition of the human runbook, stated in the decision module's prose",
    "read2.models": "an operating condition of the human runbook (frozen at read 1)",
    "rule.alternative_vs_default_bar": "behavior of the decision rule, tested in forecast_shadow_decision_v4_test",
    "live_check.runs_at_each_read": "an operating condition of the shadow-log scorer's runbook",
}


# --------------------------------------------------------------------------
# Comparison
# --------------------------------------------------------------------------

def assert_equal(key: str, signed: str, code) -> None:
    """The signed text equals the code value: instants as tz-aware UTC timestamps, lists item by item, numbers as
    floats, `a=1;b=x` rows field by field, anything else as exact text."""
    if isinstance(code, pd.Timestamp):
        assert code.tzinfo is not None, f"{key}: the code value must be a tz-aware UTC instant"
        parsed = reg.as_timestamp(signed) if key in reg.TIMESTAMP_KEYS else _utc(signed)
        assert parsed == code, f"{key}: signed {signed!r}, code {code!r}"
    elif isinstance(code, (list, tuple)):
        assert reg.as_list(signed) == [str(item) for item in code], f"{key}: signed {signed!r}, code {list(code)!r}"
    elif isinstance(code, dict):
        assert _parse_fields(signed) == code, f"{key}: signed {signed!r}, code {code!r}"
    elif isinstance(code, bool):
        raise AssertionError(f"{key}: booleans are not registered values")
    elif isinstance(code, (int, float)):
        assert float(signed) == float(code), f"{key}: signed {signed!r}, code {code!r}"
    else:
        assert signed == code, f"{key}: signed {signed!r}, code {code!r}"


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------

def test_the_registry_is_read_from_the_signed_copy_and_the_copy_is_signed():
    assert reg.SIGNING_COPY_PATH.name.endswith("_SIGNING_COPY.md")
    assert reg.is_signed(reg.SIGNING_COPY_PATH), "the signing copy must carry the owner's name, signature and date"
    assert core.v4_signed()
    assert set(reg.REQUIRED_KEYS) <= set(SIGNED)


def test_the_three_groups_are_disjoint():
    groups = [set(CODE_MAP), set(STATE_CHECKS), set(DOC_ONLY_KEYS)]
    assert not (groups[0] & groups[1]) and not (groups[0] & groups[2]) and not (groups[1] & groups[2])


def test_every_registry_key_is_mapped():
    mapped = set(CODE_MAP) | set(STATE_CHECKS) | set(DOC_ONLY_KEYS)
    unmapped = sorted(set(SIGNED) - mapped)
    assert not unmapped, f"registry keys with no code constant, state check or DOC_ONLY entry: {unmapped}"


def test_no_mapping_names_a_key_the_signed_registry_lacks():
    mapped = set(CODE_MAP) | set(STATE_CHECKS) | set(DOC_ONLY_KEYS)
    assert not sorted(mapped - set(SIGNED)), f"stale mapping(s): {sorted(mapped - set(SIGNED))}"


def test_every_doc_only_key_says_why():
    assert all(isinstance(why, str) and why for why in DOC_ONLY_KEYS.values())


@pytest.mark.parametrize("key", sorted(CODE_MAP))
def test_code_constant_equals_the_signed_value(key):
    assert_equal(key, SIGNED[key], CODE_MAP[key]())


@pytest.mark.parametrize("key", sorted(STATE_CHECKS))
def test_production_table_row_matches_the_signed_o4_choice(key):
    STATE_CHECKS[key](SIGNED[key])


def test_the_code_has_no_variant_the_registry_lacks():
    assert [v["name"] for v in ablation.BRACKETING_SET] == _variants_in_registry()


def test_the_o4_choice_and_the_rescore_gate_are_the_signed_words():
    assert SIGNED["power_systems.partial_answers"] == "custom_switch_austin_drake_100c"
    assert SIGNED["power_systems.switch_cities"] == "AUSTIN" and SIGNED["refit.cities"] == "AUSTIN"
    assert SIGNED["test.rescore_gate"] == "before_read1_run"


def test_values_the_code_repeats_agree_with_each_other():
    # the same signed number lives in more than one module; they must not drift apart
    for name in ("v4-read1", "v4-read2"):
        assert core.PROTOCOL_ROUNDS[name].family_alpha == decision.FAMILY_ALPHA_BY_ROUND[name]
    assert decision.FAMILY_ALPHA_BY_ROUND["v4-late-descriptive"] == core.V4_LATE_DESCRIPTIVE.family_alpha
    assert core.PRE_REGISTERED_PARAM_DEFAULTS["relative_margin_fraction"] == decision.RELATIVE_MARGIN_FRACTION \
        == core.RELATIVE_MARGIN_FRACTION == float(SIGNED["rule.relative_margin_fraction"])
    assert core.PRE_REGISTERED_PARAM_DEFAULTS["consistency_min_cities"] == decision.CONSISTENCY_MIN_CITIES \
        == core.CONSISTENCY_MIN_CITIES == int(SIGNED["rule.consistency_min_cities"])
    assert core.PRE_REGISTERED_PARAM_DEFAULTS["block_lengths"] == core.BLOCK_LENGTHS_SLOTS
    assert core.PRE_REGISTERED_PARAM_DEFAULTS["n_resamples"] == core.N_RESAMPLES


def test_the_split_and_the_fit_end_agree_with_the_frozen_split():
    split = _utc(audit.FROZEN_TEST_SPLIT_START)
    assert ablation.VALIDATION_END_EXCLUSIVE == split == reg.as_timestamp(SIGNED["refit.fit_end_exclusive"])
    assert _utc(fit_models.train_val_window_end()) + pd.Timedelta(days=1) == split
    # TEST starts the day after the first post-split day (its anchors sit in the fit window) and ends at FRESH
    assert test_split.TEST_WINDOW_START == split + pd.Timedelta(days=1)
    assert test_split.TEST_WINDOW_END_EXCLUSIVE == core.FRESH_BASIS_START


def test_slot_counts_follow_from_the_registered_windows():
    per_day = reg.SLOTS_PER_DAY
    window = lambda a, b: int((b - a) / pd.Timedelta(hours=core.SLOT_HOURS))
    assert window(test_split.TEST_WINDOW_START, test_split.TEST_WINDOW_END_EXCLUSIVE) == test_split.TEST_SLOTS_PER_CITY
    assert window(core.FRESH_BASIS_START, _round("v4-read1").cutoff) == _round("v4-read1").slots_per_city == 25 * per_day
    assert window(core.FRESH_BASIS_START, _round("v4-read2").cutoff) == _round("v4-read2").slots_per_city == 32 * per_day
    assert window(ablation.VALIDATION_START, ablation.VALIDATION_END_EXCLUSIVE) == ablation.VALIDATION_ROWS_PER_CITY


def test_the_registry_keys_collected_by_the_parametrized_cases_are_counted():
    # recorded in the plan summary: one parametrized case per mapped key (CODE_MAP and STATE_CHECKS)
    assert len(CODE_MAP) + len(STATE_CHECKS) + len(DOC_ONLY_KEYS) == len(SIGNED)


# --------------------------------------------------------------------------
# The state-aware checks tighten themselves once the O4 switch is applied (a later plan edits the table)
# --------------------------------------------------------------------------

@pytest.fixture
def table(monkeypatch):
    rows = {c: dict(v) for c, v in config.PRODUCTION_CONDUCTORS.items()}
    monkeypatch.setattr(config, "PRODUCTION_CONDUCTORS", rows)
    return rows


def test_after_the_switch_the_checks_accept_exactly_the_signed_table(monkeypatch, table):
    monkeypatch.setattr(config, "RATING_CONFIG_VERSION", "v3-powersystems-2026-11-05")
    table["AUSTIN"]["max_temp_c"] = 100.0
    _check_switch_cities(SIGNED["power_systems.switch_cities"])
    _check_austin_config(SIGNED["power_systems.austin_config"])


def test_after_the_switch_a_second_changed_city_or_an_unswitched_austin_fails(monkeypatch, table):
    monkeypatch.setattr(config, "RATING_CONFIG_VERSION", "v3-powersystems-2026-11-05")
    with pytest.raises(AssertionError):                       # version moved on but AUSTIN is still at 75 C
        _check_switch_cities(SIGNED["power_systems.switch_cities"])
    with pytest.raises(AssertionError):
        _check_austin_config(SIGNED["power_systems.austin_config"])
    table["AUSTIN"]["max_temp_c"] = 100.0
    table["MIDLAND"]["max_temp_c"] = 90.0                     # a city the owner did not switch
    with pytest.raises(AssertionError):
        _check_switch_cities(SIGNED["power_systems.switch_cities"])


def test_while_provisional_a_changed_austin_value_is_not_silently_accepted(table):
    table["AUSTIN"]["max_temp_c"] = 100.0                     # still labelled v2-provisional: the label must move too
    with pytest.raises(AssertionError):
        _check_switch_cities(SIGNED["power_systems.switch_cities"])
    with pytest.raises(AssertionError):
        _check_austin_config(SIGNED["power_systems.austin_config"])
