"""
Tests for `forecast_conductor_ablation.py` (SEL-03 ABLATION driver and veto evaluation, plan 07-03 task 2).

Fixture-only and offline. The frame loader is injected with the committed dev fixture (TEST-split dates
2026-03-30 .. 2026-05-31) shifted back 241 days so it straddles TRAIN_END (2026-03-30 maps to 2025-08-01 and the
fixture ends 2025-10-02). A spy records every open(), pandas.read_csv and joblib.dump: no test opens a
data/experiment file carrying the FRESH date 2026-09-30, and no test dumps a model anywhere (the driver fits in
memory only). The veto cases use small synthetic family reports; no statistics run for them.
"""

from __future__ import annotations

import builtins
import json
import os

import joblib
import numpy as np
import pandas as pd
import pytest

import city_point
import config
import forecast_conductor_ablation as abl
import forecast_conductor_refit as refit
import forecast_correction_models
import forecast_experiment
import forecast_shadow_eval_core as core
import forecast_shadow_fit_models as fm
import forecast_shadow_pipeline as shadow

_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "shadow_eval_frozen_dev_frames.csv.gz")
_SHIFT_DAYS = 241  # 2026-03-30 -> 2025-08-01
_DATE_COLUMNS = ("datetime_utc", "anchor_datetime_utc", "fcst_anchor_datetime_utc")
_WIND, _COOLING, _REFERENCE = "ml_wind_corrected", "ml_cooling_corrected", "reference_ml_refit_24h"
_RAW, _PERSIST = "raw_forecast", "persistence_24h"
_CITIES4 = ("AUSTIN", "CORPUS_CHRISTI", "MIDLAND", "EL_PASO")
_BY_NAME = {v["name"]: v for v in abl.BRACKETING_SET}


@pytest.fixture(autouse=True)
def _spies(monkeypatch):
    opened, read, dumped = [], [], []
    real_open, real_read_csv, real_dump = builtins.open, pd.read_csv, joblib.dump

    def spy_open(file, *args, **kwargs):
        if isinstance(file, (str, bytes, os.PathLike)):
            opened.append(os.fsdecode(file))
        return real_open(file, *args, **kwargs)

    def spy_read_csv(path, *args, **kwargs):
        read.append(str(path))
        return real_read_csv(path, *args, **kwargs)

    def spy_dump(value, filename, *args, **kwargs):
        dumped.append(str(filename))
        return real_dump(value, filename, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(pd, "read_csv", spy_read_csv)
    monkeypatch.setattr(joblib, "dump", spy_dump)
    yield {"opened": opened, "read": read, "dumped": dumped}
    monkeypatch.undo()
    for path in opened + read:
        norm = path.replace("\\", "/")
        assert not ("data/experiment" in norm and "2026-09-30" in norm), f"FRESH-dated cache touched: {path}"
    assert dumped == [], f"the ABLATION driver must not write a model anywhere: {dumped}"


@pytest.fixture(scope="module")
def dev_frame() -> pd.DataFrame:
    frame = pd.read_csv(_FIXTURE)
    for col in _DATE_COLUMNS:
        frame[col] = pd.to_datetime(frame[col], utc=True)
    return frame


def _shifted(dev_frame, city) -> pd.DataFrame:
    frame = dev_frame[dev_frame["city"] == city].copy()
    for col in _DATE_COLUMNS:
        frame[col] = frame[col] - pd.Timedelta(days=_SHIFT_DAYS)
    return frame.reset_index(drop=True)


@pytest.fixture
def loader(dev_frame):
    return lambda city: _shifted(dev_frame, city)


@pytest.fixture
def fixture_counts(monkeypatch, dev_frame):
    """The fixture's own train/validation exact-lead counts stand in for 2,360 / 784."""
    frame = _shifted(dev_frame, "AUSTIN")
    point = city_point.production_city_point("AUSTIN")
    _, exact = refit.prepare_fit_frame(frame, point, "AUSTIN")
    train, validation = abl.split(exact, expected_counts=False)
    monkeypatch.setattr(abl, "TRAIN_ROWS_PER_CITY", len(train))
    monkeypatch.setattr(abl, "VALIDATION_ROWS_PER_CITY", len(validation))
    return len(train), len(validation)


# --------------------------------------------------------------------------
# The bracketing set and variant_point
# --------------------------------------------------------------------------

def test_bracketing_set_names_are_in_the_registered_order():
    assert [v["name"] for v in abl.BRACKETING_SET] == [
        "Drake-75", "Drake-100", "Falcon-90", "Suwannee-150", "Suwannee-200", "Drake-75-AUSTIN-163m"]
    assert abl.CONTROL == "Drake-75"
    assert abl.TRAIN_ROWS_PER_CITY == 2360 and abl.VALIDATION_ROWS_PER_CITY == 784
    assert abl.EMISSIVITY == abl.ABSORPTIVITY == 0.8 and abl.RESIST_TEMP_COEF == 0.00404
    assert abl.VETO_RULE == "sign_flip_vs_raw_or_default" and abl.ROW_SOURCE == "reconstructed_frames"


@pytest.mark.parametrize("name, diameter, resistance, max_temp, elevation", [
    ("Drake-75", 0.02814, 0.0726, 75.0, 900.0),
    ("Drake-100", 0.02814, 0.0726, 100.0, 900.0),
    ("Falcon-90", 0.03924, 0.0371, 90.0, 900.0),
    ("Suwannee-150", 0.02819, 0.0597, 150.0, 900.0),
    ("Suwannee-200", 0.02819, 0.0597, 200.0, 900.0),
    ("Drake-75-AUSTIN-163m", 0.02814, 0.0726, 75.0, 163.0),
])
def test_variant_point_returns_the_catalogue_values(name, diameter, resistance, max_temp, elevation):
    point, applies = abl.variant_point("AUSTIN", _BY_NAME[name])
    assert applies is True
    c = point.conductor
    assert (c.D, c.T_max, c.elev) == (diameter, max_temp, elevation)
    assert c.R25 == pytest.approx(resistance / 1000)
    assert c.eps == c.alpha_s == 0.8 and c.alpha_r == 0.00404
    bearing = config.CITY_LINE_BEARING_DEG["AUSTIN"]
    assert point.bearing_deg == bearing and c.line_az == bearing
    assert point.coord == config.CITY_COORDINATES["AUSTIN"]
    assert point.static_rating == config.STATIC_RATINGS["AUSTIN"]
    assert point.rating_bounds == config.RATING_BOUNDS_BY_LOCATION["AUSTIN"]


@pytest.mark.parametrize("city", _CITIES4)
def test_the_control_point_is_the_frozen_drake_point(city):
    point, applies = abl.variant_point(city, _BY_NAME[abl.CONTROL])
    frozen = city_point.city_point(city)
    assert applies and point.bearing_deg == frozen.bearing_deg
    assert vars(point.conductor) == vars(frozen.conductor)


def test_the_austin_elevation_variant_applies_to_austin_only():
    variant = _BY_NAME["Drake-75-AUSTIN-163m"]
    for city in ("CORPUS_CHRISTI", "MIDLAND", "EL_PASO"):
        point, applies = abl.variant_point(city, variant)
        assert applies is False and point is None
    assert abl.variant_point("AUSTIN", variant)[1] is True
    for name in ("Drake-100", "Falcon-90", "Suwannee-150"):
        assert all(abl.variant_point(c, _BY_NAME[name])[1] for c in _CITIES4)


def test_only_the_suwannee_variants_are_flagged_approximate():
    flagged = [v["name"] for v in abl.BRACKETING_SET if v["approximate_resistance"]]
    assert flagged == ["Suwannee-150", "Suwannee-200"]


def test_variant_point_accepts_a_name_and_rejects_unknowns():
    assert abl.variant_point("AUSTIN", "Drake-100")[0].conductor.T_max == 100.0
    with pytest.raises(KeyError):
        abl.variant_point("AUSTIN", "Zebra-1")
    with pytest.raises(KeyError):
        abl.variant_point("NOWHERE", _BY_NAME["Drake-75"])


# --------------------------------------------------------------------------
# split and the boundary edge
# --------------------------------------------------------------------------

def _exact_rows(times, city="AUSTIN"):
    ts = pd.to_datetime(list(times), utc=True)
    return pd.DataFrame({"city": city, "datetime_utc": ts, "anchor_datetime_utc": ts - pd.Timedelta(hours=24)})


def test_split_puts_the_boundary_rows_on_the_right_side():
    exact = _exact_rows([
        "2025-09-01T12:00:00Z", "2025-09-01T18:00:00Z", "2025-09-02T00:00:00Z", "2025-09-02T06:00:00Z",
        "2026-03-16T18:00:00Z",
    ])
    train, validation = abl.split(exact, expected_counts=False)
    assert list(train["datetime_utc"].dt.strftime("%Y-%m-%dT%H:%M")) == ["2025-09-01T12:00", "2025-09-01T18:00"]
    assert list(validation["datetime_utc"].dt.strftime("%Y-%m-%dT%H:%M")) == [
        "2025-09-02T00:00", "2025-09-02T06:00", "2026-03-16T18:00"]


def test_split_leaves_a_row_between_the_windows_in_neither():
    exact = _exact_rows(["2025-09-01T18:00:00Z", "2025-09-01T19:00:00Z", "2025-09-01T23:00:00Z", "2025-09-02T00:00:00Z"])
    train, validation = abl.split(exact, expected_counts=False)
    assert len(train) == 1 and len(validation) == 1


def test_split_refuses_a_row_at_the_test_split():
    exact = _exact_rows(["2025-09-02T00:00:00Z", "2026-03-17T00:00:00Z"])
    with pytest.raises(AssertionError, match="2026-03-17"):
        abl.split(exact, expected_counts=False)
    with pytest.raises(AssertionError):
        abl.split(exact, expected_counts=True)


def _counted(n_train, n_val, city="MIDLAND"):
    train = pd.date_range("2024-01-20T06:00:00Z", periods=n_train, freq="6h")  # ends 2025-09-01T00:00Z at 2359
    val = pd.date_range("2025-09-02T00:00:00Z", periods=n_val, freq="5h")
    return _exact_rows(list(train) + list(val), city)


def test_expected_counts_pass_at_2360_and_784():
    train, validation = abl.split(_counted(2360, 784), expected_counts=True)
    assert (len(train), len(validation)) == (2360, 784)


@pytest.mark.parametrize("n_train, n_val", [(2360, 783), (2360, 785), (2359, 784), (2361, 784)])
def test_expected_counts_name_the_city_and_both_counts_when_either_differs(n_train, n_val):
    with pytest.raises(AssertionError) as info:
        abl.split(_counted(n_train, n_val, "MIDLAND"), expected_counts=True)
    message = str(info.value)
    assert "MIDLAND" in message and str(n_train) in message and str(n_val) in message
    assert "2360" in message and "784" in message


# --------------------------------------------------------------------------
# candidate_errors and run_ablation on the fixture
# --------------------------------------------------------------------------

def _fit_models(frame, point, city="AUSTIN"):
    wind = refit.fit_for_point(city, frame, point, methods=(_WIND,), fit_end=abl.TRAIN_END)["models"]
    rest = refit.fit_for_point(city, frame, point, fit_end=abl.TRAIN_END)["models"]
    return {**wind, **rest}


def test_candidate_errors_match_an_independent_recomputation(dev_frame):
    frame = _shifted(dev_frame, "AUSTIN")
    point, _ = abl.variant_point("AUSTIN", _BY_NAME["Drake-100"])
    full, exact = refit.prepare_fit_frame(frame, point, "AUSTIN")
    train, validation = abl.split(exact, expected_counts=False)
    models = _fit_models(frame, point)
    errors, mean_truth = abl.candidate_errors(validation, full, point, models)

    assert errors.attrs["row_source"] == abl.ROW_SOURCE
    assert list(errors.columns[:-1]) == list(core.CANDIDATES) and errors.columns[-1] == "slot"
    assert len(errors) == len(validation) and errors.index.equals(pd.DatetimeIndex(validation["datetime_utc"]))
    truth = validation["truth_dlr_amps"].to_numpy(dtype=float)
    assert mean_truth == pytest.approx(float(truth.mean()))
    # truth, raw and persistence are recomputed under the variant point
    raw = forecast_experiment._city_ampacity(
        validation["fcst_air_temp"], validation["fcst_wind_speed"], validation["fcst_wind_direction"],
        validation["fcst_solar_radiation"], point)
    persistence = forecast_experiment._city_ampacity(
        validation["anchor_air_temp"], validation["anchor_wind_speed"], validation["anchor_wind_direction"],
        validation["anchor_solar_radiation"], point)
    np.testing.assert_array_equal(errors[_RAW].to_numpy(), raw - truth)
    np.testing.assert_array_equal(errors[_PERSIST].to_numpy(), persistence - truth)
    wind = forecast_experiment._wind_corrected_ampacity(models[_WIND], validation, point)
    cooling = forecast_experiment._cooling_corrected_ampacity(models[_COOLING], validation, point)
    np.testing.assert_array_equal(errors[_WIND].to_numpy(), wind - truth)
    np.testing.assert_array_equal(errors[_COOLING].to_numpy(), cooling - truth)
    # the 100 C truth really differs from the 75 C truth
    control_point, _ = abl.variant_point("AUSTIN", _BY_NAME[abl.CONTROL])
    _, control_exact = refit.prepare_fit_frame(frame, control_point, "AUSTIN")
    _, control_validation = abl.split(control_exact, expected_counts=False)
    assert (truth > control_validation["truth_dlr_amps"].to_numpy(dtype=float)).all()
    # the reference candidate is scored where its feature window is complete
    assert errors[_REFERENCE].notna().sum() > 0
    assert pd.DatetimeIndex(errors["slot"]).equals(errors.index)


def test_run_ablation_returns_variant_reports_metrics_ranks_and_tau(loader, fixture_counts, _spies):
    variants = (_BY_NAME["Drake-75"], _BY_NAME["Drake-100"])
    report = abl.run_ablation(["AUSTIN", "MIDLAND"], frame_loader=loader, variants=variants,
                              params={"n_resamples": 200}, expected_counts=True)
    json.loads(core.dumps(report))  # JSON-ready

    assert report["basis"] == "ABLATION (train <= 2025-09-01T18:00Z, validation 2025-09-02..2026-03-16)"
    assert report["control"] == "Drake-75" and report["cities"] == ["AUSTIN", "MIDLAND"]
    assert set(report["variants"]) == {"Drake-75", "Drake-100"}
    assert report["n_rows"]["AUSTIN"] == {"train": fixture_counts[0], "validation": fixture_counts[1]}
    assert any("Suwannee" in text and "unverified" in text for text in report["caveats"])

    control, hot = report["variants"]["Drake-75"], report["variants"]["Drake-100"]
    assert control["kendall_tau_vs_control"] == 1.0
    assert -1.0 <= hot["kendall_tau_vs_control"] <= 1.0
    for block in (control, hot):
        assert block["family"]["row_source"] == abl.ROW_SOURCE and len(block["family"]["comparisons"]) == 9
        assert sorted(block["rank_order"]) == sorted(core.CANDIDATES)
        for candidate in core.CANDIDATES:
            for city in ("AUSTIN", "MIDLAND"):
                metrics = block["metrics"][candidate][city]
                assert {"n", "bias", "mae", "rmse"} <= set(metrics)
                rel = block["relative_metrics"][candidate][city]
                mean_truth = block["mean_truth_by_city"][city]
                assert rel["mae"] == pytest.approx(metrics["mae"] / mean_truth, rel=1e-12)
                assert rel["rmse"] == pytest.approx(metrics["rmse"] / mean_truth, rel=1e-12)
                assert rel["bias"] == pytest.approx(metrics["bias"] / mean_truth, rel=1e-12)
            assert block["pooled"][candidate]["mae"] is not None
        for candidate in core.REAL_CANDIDATES:
            margin = block["margins_over_raw"][candidate]
            comparison = next(c for c in block["family"]["comparisons"] if (c["a"], c["b"]) == (candidate, _RAW))
            assert margin["amps"] == comparison["point_margin"]
            assert margin["pct"] == pytest.approx(100.0 * comparison["relative_mae_reduction"], rel=1e-9)
    # a hotter conductor raises the truth ampacity (more current is allowed at 100 C)
    assert all(hot["mean_truth_by_city"][c] > control["mean_truth_by_city"][c] for c in ("AUSTIN", "MIDLAND"))
    assert _spies["dumped"] == []


def test_wind_is_fit_once_per_city_and_cooling_reference_fit_on_train_only(loader, fixture_counts, monkeypatch):
    calls = []
    real = refit.fit_for_point

    def spy(city, frame, point, methods=refit.REFIT_METHODS, fit_end=None):
        calls.append((city, tuple(methods), fit_end, point.conductor.T_max))
        return real(city, frame, point, methods=methods, fit_end=fit_end)

    monkeypatch.setattr(refit, "fit_for_point", spy)
    abl.run_ablation(["AUSTIN", "MIDLAND"], frame_loader=loader,
                     variants=(_BY_NAME["Drake-75"], _BY_NAME["Drake-100"], _BY_NAME["Falcon-90"]),
                     params={"n_resamples": 100}, expected_counts=True)
    wind = [c for c in calls if c[1] == (_WIND,)]
    rest = [c for c in calls if c[1] != (_WIND,)]
    assert sorted(c[0] for c in wind) == ["AUSTIN", "MIDLAND"]
    assert len(rest) == 2 * 3
    assert all(c[2] == abl.TRAIN_END for c in calls)
    assert {c[3] for c in rest} == {75.0, 100.0, 90.0}
    assert all(set(c[1]) == set(refit.REFIT_METHODS) for c in rest)


def test_cooling_and_reference_models_never_see_validation_rows(loader, fixture_counts, monkeypatch):
    seen = []
    real = forecast_correction_models.fit_cooling_correction

    def spy(train_frame, factory, **kwargs):
        seen.append(pd.to_datetime(train_frame["datetime_utc"], utc=True).max())
        return real(train_frame, factory, **kwargs)

    monkeypatch.setattr(forecast_correction_models, "fit_cooling_correction", spy)
    abl.run_ablation(["AUSTIN"], frame_loader=loader, variants=(_BY_NAME["Drake-75"], _BY_NAME["Drake-100"]),
                     params={"n_resamples": 100}, expected_counts=True)
    assert seen and all(t <= abl.TRAIN_END for t in seen)


def test_run_ablation_asserts_the_expected_counts_per_city(loader):
    # the fixture does not hold 2,360 / 784 rows, so the default check fires and names the city
    with pytest.raises(AssertionError) as info:
        abl.run_ablation(["AUSTIN"], frame_loader=loader, variants=(_BY_NAME["Drake-75"],),
                         params={"n_resamples": 50}, expected_counts=True)
    assert "AUSTIN" in str(info.value) and "2360" in str(info.value) and "784" in str(info.value)


def test_the_austin_only_variant_is_scored_for_austin_against_a_matched_control(loader, fixture_counts):
    report = abl.run_ablation(
        ["AUSTIN", "MIDLAND"], frame_loader=loader,
        variants=(_BY_NAME["Drake-75"], _BY_NAME["Drake-75-AUSTIN-163m"]),
        params={"n_resamples": 100}, expected_counts=True)
    block = report["variants"]["Drake-75-AUSTIN-163m"]
    assert block["cities"] == ["AUSTIN"]
    assert set(block["family"]["comparisons"][0]["per_city_margins"]) == {"AUSTIN"}
    matched = block["matched_control"]
    assert set(matched["family"]["comparisons"][0]["per_city_margins"]) == {"AUSTIN"}
    assert "matched_control" not in report["variants"]["Drake-75"]
    assert report["variants"]["Drake-75"]["cities"] == ["AUSTIN", "MIDLAND"]


def test_a_variant_that_applies_to_no_requested_city_is_skipped(loader, fixture_counts):
    report = abl.run_ablation(["MIDLAND"], frame_loader=loader,
                              variants=(_BY_NAME["Drake-75"], _BY_NAME["Drake-75-AUSTIN-163m"]),
                              params={"n_resamples": 100}, expected_counts=True)
    assert set(report["variants"]) == {"Drake-75"}
    assert report["skipped_variants"] == {"Drake-75-AUSTIN-163m": "applies to AUSTIN only; no requested city applies"}


def test_run_ablation_requires_the_control_variant(loader):
    with pytest.raises(ValueError, match="Drake-75"):
        abl.run_ablation(["AUSTIN"], frame_loader=loader, variants=(_BY_NAME["Drake-100"],), expected_counts=False)


def test_a_frame_with_test_period_rows_is_refused(dev_frame):
    def leaky(city):
        return dev_frame[dev_frame["city"] == city].reset_index(drop=True)  # unshifted: TEST-split dates

    with pytest.raises(AssertionError, match="leak"):
        abl.run_ablation(["AUSTIN"], frame_loader=leaky, variants=(_BY_NAME["Drake-75"],), expected_counts=False)


def test_the_default_frame_loader_is_the_shadow_cached_frame_loader():
    import inspect
    assert inspect.signature(abl.run_ablation).parameters["frame_loader"].default is fm.load_city_frame


# --------------------------------------------------------------------------
# The veto
# --------------------------------------------------------------------------

def _family(raw, over_wind, city_over_wind):
    """
    A minimal family report. `raw[c]` is the pooled margin of candidate c over raw_forecast (positive: c better);
    `over_wind[c]` and `city_over_wind[c]` (one value per city) are the margin of cooling/reference over
    ml_wind_corrected, positive when the candidate is better (the family stores it as wind-minus-candidate).
    """
    def comparison(a, b, margin, per_city):
        return {"id": f"{a}__vs__{b}", "a": a, "b": b, "point_margin": margin,
                "per_city_margins": dict(zip(_CITIES4, per_city))}

    zero = [0.0] * 4
    return {"row_source": abl.ROW_SOURCE, "comparisons": [
        comparison(_WIND, _COOLING, None if over_wind[_COOLING] is None else -over_wind[_COOLING],
                   [None if v is None else -v for v in city_over_wind[_COOLING]]),
        comparison(_WIND, _REFERENCE, None if over_wind[_REFERENCE] is None else -over_wind[_REFERENCE],
                   [None if v is None else -v for v in city_over_wind[_REFERENCE]]),
        comparison(_COOLING, _REFERENCE, 0.0, zero),
        comparison(_WIND, _RAW, raw[_WIND], zero),
        comparison(_COOLING, _RAW, raw[_COOLING], zero),
        comparison(_REFERENCE, _RAW, raw[_REFERENCE], zero),
        comparison(_WIND, _PERSIST, 1.0, zero),
        comparison(_COOLING, _PERSIST, 1.0, zero),
        comparison(_REFERENCE, _PERSIST, 1.0, zero),
    ]}


def _base(raw_w=30.0, raw_c=25.0, raw_r=10.0, wind_c=-5.0, wind_r=-20.0,
          cities_c=(-5.0, -5.0, -5.0, -5.0), cities_r=(-20.0, -20.0, -20.0, -20.0)):
    return _family({_WIND: raw_w, _COOLING: raw_c, _REFERENCE: raw_r},
                   {_COOLING: wind_c, _REFERENCE: wind_r},
                   {_COOLING: list(cities_c), _REFERENCE: list(cities_r)})


def _report(variants: dict, control=None):
    out = {"control": abl.CONTROL, "variants": {abl.CONTROL: {"family": control or _base(), "kendall_tau_vs_control": 1.0}}}
    for name, spec in variants.items():
        block = {"family": spec["family"], "kendall_tau_vs_control": spec.get("tau", 1.0)}
        if "matched_control" in spec:
            block["matched_control"] = {"family": spec["matched_control"]}
        out["variants"][name] = block
    return out


def test_identical_signs_and_tau_one_give_ranking_invariant():
    result = abl.veto(_report({"Drake-100": {"family": _base(raw_w=31.0)}, "Falcon-90": {"family": _base()}}))
    assert result["rule"] == abl.VETO_RULE and result["ranking_invariant"] is True
    assert set(result["vetoes"]) == set(core.REAL_CANDIDATES)
    assert not any(v["vetoed"] for v in result["vetoes"].values())
    assert all(v["reasons"] == [] for v in result["vetoes"].values())


@pytest.mark.parametrize("candidate, kwargs", [
    (_WIND, {"raw_w": -1.0}), (_COOLING, {"raw_c": -1.0}), (_REFERENCE, {"raw_r": -1.0}),
])
def test_a_raw_margin_sign_flip_vetoes_that_candidate(candidate, kwargs):
    result = abl.veto(_report({"Drake-100": {"family": _base(**kwargs)}}))
    assert result["vetoes"][candidate]["vetoed"] is True
    assert any("raw_forecast" in r and "Drake-100" in r for r in result["vetoes"][candidate]["reasons"])
    others = [c for c in core.REAL_CANDIDATES if c != candidate]
    assert not any(result["vetoes"][c]["vetoed"] for c in others)
    assert result["ranking_invariant"] is False


def test_a_cooling_versus_wind_sign_flip_vetoes_cooling_and_reference_only():
    flipped = abl.veto(_report({"Falcon-90": {"family": _base(wind_c=+3.0)}}))
    assert flipped["vetoes"][_COOLING]["vetoed"] is True
    assert any("ml_wind_corrected" in r for r in flipped["vetoes"][_COOLING]["reasons"])
    assert flipped["vetoes"][_WIND]["vetoed"] is False and flipped["vetoes"][_REFERENCE]["vetoed"] is False
    again = abl.veto(_report({"Falcon-90": {"family": _base(wind_r=+1.0)}}))
    assert again["vetoes"][_REFERENCE]["vetoed"] is True and again["vetoes"][_COOLING]["vetoed"] is False


def test_the_wind_candidate_has_no_wind_clauses():
    # wind's own comparison with itself does not exist; only the raw clause can veto it
    result = abl.veto(_report({"Drake-100": {"family": _base(wind_c=+3.0, wind_r=+3.0,
                                                           cities_c=(5.0,) * 4, cities_r=(5.0,) * 4)}}))
    assert result["vetoes"][_WIND]["vetoed"] is False


def test_crossing_the_three_of_four_line_vetoes_in_both_directions():
    control = _base(cities_c=(2.0, 2.0, 2.0, -2.0))   # favoured over wind in 3 cities
    lost = abl.veto(_report({"Drake-100": {"family": _base(cities_c=(2.0, 2.0, -2.0, -2.0))}}, control=control))
    assert lost["vetoes"][_COOLING]["vetoed"] is True
    assert any("3 cities" in r or "at least 3" in r for r in lost["vetoes"][_COOLING]["reasons"])
    control2 = _base(cities_c=(2.0, 2.0, -2.0, -2.0))  # 2 cities
    gained = abl.veto(_report({"Drake-100": {"family": _base(cities_c=(2.0, 2.0, 2.0, -2.0))}}, control=control2))
    assert gained["vetoes"][_COOLING]["vetoed"] is True
    # moving between 3 and 4 cities stays on the same side of the line: no veto
    stays = abl.veto(_report({"Drake-100": {"family": _base(cities_c=(2.0, 2.0, 2.0, 2.0))}}, control=control))
    assert stays["vetoes"][_COOLING]["vetoed"] is False


def test_a_city_with_a_zero_margin_is_not_favoured():
    control = _base(cities_c=(2.0, 2.0, 2.0, -2.0))
    result = abl.veto(_report({"Drake-100": {"family": _base(cities_c=(2.0, 2.0, 0.0, -2.0))}}, control=control))
    assert result["vetoes"][_COOLING]["vetoed"] is True


def test_a_positive_margin_changing_to_exactly_zero_counts_as_a_sign_flip():
    assert abl.veto(_report({"Drake-100": {"family": _base(raw_c=0.0)}}))["vetoes"][_COOLING]["vetoed"] is True
    zero_control = _base(raw_c=0.0)
    assert abl.veto(_report({"Drake-100": {"family": _base(raw_c=4.0)}}, control=zero_control))[
        "vetoes"][_COOLING]["vetoed"] is True
    assert abl.veto(_report({"Drake-100": {"family": _base(raw_c=-0.0)}}, control=zero_control))[
        "vetoes"][_COOLING]["vetoed"] is False


def test_signs_come_from_unrounded_values():
    control = _base(raw_c=4.0e-9)
    tiny_flip = abl.veto(_report({"Drake-100": {"family": _base(raw_c=-4.0e-9)}}, control=control))
    assert tiny_flip["vetoes"][_COOLING]["vetoed"] is True       # would round to 0.0 and look unchanged
    same_side = abl.veto(_report({"Drake-100": {"family": _base(raw_c=9.0e-16)}}, control=control))
    assert same_side["vetoes"][_COOLING]["vetoed"] is False


def test_a_tau_below_one_with_no_veto_is_not_ranking_invariant():
    result = abl.veto(_report({"Falcon-90": {"family": _base(), "tau": 0.8}}))
    assert not any(v["vetoed"] for v in result["vetoes"].values())
    assert result["ranking_invariant"] is False
    missing = abl.veto(_report({"Falcon-90": {"family": _base(), "tau": None}}))
    assert missing["ranking_invariant"] is False
    nan = abl.veto(_report({"Falcon-90": {"family": _base(), "tau": float("nan")}}))
    assert nan["ranking_invariant"] is False


def test_an_unavailable_margin_vetoes_with_a_reason():
    family = _base()
    family["comparisons"][4]["point_margin"] = None   # cooling vs raw: no data under this variant
    result = abl.veto(_report({"Suwannee-200": {"family": family}}))
    assert result["vetoes"][_COOLING]["vetoed"] is True
    assert any("unavailable" in r and "Suwannee-200" in r for r in result["vetoes"][_COOLING]["reasons"])


def test_a_subset_variant_is_compared_with_its_matched_control():
    # against the full control the variant's raw margin looks flipped; against the matched control it does not
    full_control = _base(raw_c=25.0)
    matched = _base(raw_c=-3.0)
    variant = _base(raw_c=-2.0)
    flagged = abl.veto(_report({"Drake-75-AUSTIN-163m": {"family": variant}}, control=full_control))
    assert flagged["vetoes"][_COOLING]["vetoed"] is True
    cleared = abl.veto(_report({"Drake-75-AUSTIN-163m": {"family": variant, "matched_control": matched}},
                               control=full_control))
    assert cleared["vetoes"][_COOLING]["vetoed"] is False


def test_each_veto_reason_names_the_variant():
    result = abl.veto(_report({"Drake-100": {"family": _base(raw_c=-1.0)},
                               "Suwannee-150": {"family": _base(raw_c=-1.0, wind_c=2.0)}}))
    reasons = " | ".join(result["vetoes"][_COOLING]["reasons"])
    assert "Drake-100" in reasons and "Suwannee-150" in reasons


def test_veto_works_on_a_real_run_report(loader, fixture_counts):
    report = abl.run_ablation(["AUSTIN", "MIDLAND"], frame_loader=loader,
                              variants=(_BY_NAME["Drake-75"], _BY_NAME["Drake-100"]),
                              params={"n_resamples": 100}, expected_counts=True)
    result = abl.veto(report)
    assert set(result["vetoes"]) == set(core.REAL_CANDIDATES)
    assert isinstance(result["ranking_invariant"], bool)
    # the control compared with itself is always invariant
    same = abl.veto({"control": abl.CONTROL, "variants": {abl.CONTROL: report["variants"][abl.CONTROL]}})
    assert same["ranking_invariant"] is True and not any(v["vetoed"] for v in same["vetoes"].values())


# --------------------------------------------------------------------------
# write_report and the CLI
# --------------------------------------------------------------------------

@pytest.fixture
def small_report(loader, fixture_counts):
    return abl.run_ablation(["AUSTIN"], frame_loader=loader,
                            variants=(_BY_NAME["Drake-75"], _BY_NAME["Suwannee-150"]),
                            params={"n_resamples": 100}, expected_counts=True)


def test_write_report_writes_json_and_a_plain_english_markdown(tmp_path, small_report):
    out = tmp_path / "ablation-out"
    abl.write_report(small_report, str(out))
    assert sorted(os.listdir(out)) == ["ablation.json", "ablation.md"]
    data = json.loads((out / "ablation.json").read_text())
    assert data["basis"] == small_report["basis"] and "veto" in data
    assert set(data["veto"]["vetoes"]) == set(core.REAL_CANDIDATES)
    text = (out / "ablation.md").read_text()
    first_section = text.split("\n## ", 2)[1]
    assert first_section.lower().startswith("summary")
    assert "ranking" in first_section.lower() and "veto" in first_section.lower()
    for candidate in core.REAL_CANDIDATES:
        assert candidate in first_section
    assert "Suwannee-150" in text and "unverified" in text


def test_write_report_refuses_an_existing_directory_and_the_frozen_one(tmp_path, small_report, monkeypatch):
    existing = tmp_path / "exists"
    existing.mkdir()
    with pytest.raises(FileExistsError):
        abl.write_report(small_report, str(existing))
    assert os.listdir(existing) == []
    frozen = tmp_path / "shadow_models"
    frozen.mkdir()
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(frozen))
    with pytest.raises(ValueError):
        abl.write_report(small_report, str(frozen / "nested"))
    with pytest.raises(ValueError):
        abl.write_report(small_report, str(frozen))
    assert os.listdir(frozen) == []


def test_main_runs_the_ablation_and_prints_the_veto_summary(tmp_path, dev_frame, fixture_counts, monkeypatch, capsys):
    monkeypatch.setattr(fm, "load_city_frame", lambda city: _shifted(dev_frame, city))
    monkeypatch.setattr(abl, "BRACKETING_SET", (_BY_NAME["Drake-75"], _BY_NAME["Drake-100"]))
    out = tmp_path / "v4-ablation" / "run1"
    rc = abl.main(["--cities", "AUSTIN", "--out-dir", str(out), "--n-resamples", "100"])
    printed = capsys.readouterr().out
    assert rc == 0
    assert str(out) in printed and "veto" in printed.lower()
    assert sorted(os.listdir(out)) == ["ablation.json", "ablation.md"]


def test_main_when_unsigned_exits_2_before_any_work(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(core, "v4_signed", lambda repo_root=None: False)
    monkeypatch.setattr(abl, "run_ablation", lambda *a, **k: pytest.fail("ran while unsigned"))
    out = tmp_path / "v4-ablation" / "run1"
    rc = abl.main(["--cities", "AUSTIN", "--out-dir", str(out)])
    assert rc == 2 and "not signed" in capsys.readouterr().err
    assert not os.path.exists(out)


def test_main_default_out_dir_is_a_timestamped_directory_outside_the_frozen_models():
    import re
    parser_default = abl._default_out_dir()
    assert re.search(r"data[/\\]shadow[/\\]evaluation[/\\]v4-ablation[/\\]\d{8}T\d{6}Z$", parser_default)
    assert "shadow" + os.sep + "models" not in parser_default


# --------------------------------------------------------------------------
# isolation
# --------------------------------------------------------------------------

def test_neither_driver_touches_the_frozen_directory_or_save_helpers():
    import ast
    for module in (abl, refit):
        tree = ast.parse(open(module.__file__, encoding="utf-8").read())
        names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        names |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        assert "save_correction_model" not in names
    tree = ast.parse(open(abl.__file__, encoding="utf-8").read())
    joblib_calls = [n.attr for n in ast.walk(tree)
                    if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "joblib"]
    assert joblib_calls == [], "the ABLATION driver fits in memory only and never dumps or loads a model"
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert "joblib" not in imported
