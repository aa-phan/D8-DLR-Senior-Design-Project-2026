"""
Tests for `forecast_conductor_refit.py` (SEL-02, plan 07-03 task 1).

Fixture-only and offline. The committed dev fixture (TEST-split dates 2026-03-30 .. 2026-05-31) is shifted back
365 days so it lies before the 2026-03-17 split; a few synthetic rows dated on or after the split prove the
restriction. Frozen artifacts are stubs in a tmp SHADOW_MODEL_DIR with their own tmp manifest; refit roots are tmp
directories. No test reads data/experiment, writes under the real data/shadow/models or loads a real artifact:
an autouse spy records every open(), pandas.read_csv and joblib.dump/load and fails the test if a path under
data/experiment carries the FRESH date 2026-09-30, if a dump lands under the real data/shadow/models, or if a
real frozen artifact is loaded.
"""

from __future__ import annotations

import ast
import builtins
import os

import joblib
import numpy as np
import pandas as pd
import pytest

import city_point
import config
import dlr_live_check_models as live_check
import forecast_conductor_refit as refit
import forecast_correction_models
import forecast_experiment_audit
import forecast_shadow_fit_models as fm
import forecast_shadow_pipeline as shadow

_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "shadow_eval_frozen_dev_frames.csv.gz")
_SPLIT = pd.Timestamp(forecast_experiment_audit.FROZEN_TEST_SPLIT_START, tz="UTC")
_REAL_SHADOW_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "shadow", "models"))
_REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
_DATE_COLUMNS = ("datetime_utc", "anchor_datetime_utc", "fcst_anchor_datetime_utc")
_COOLING = "ml_cooling_corrected"
_REFERENCE = "reference_ml_refit_24h"
_WIND = "ml_wind_corrected"


# --------------------------------------------------------------------------
# Spies: no FRESH cache, no write under the real frozen directory, no real artifact load
# --------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _spies(monkeypatch):
    opened: list[str] = []
    read: list[str] = []
    dumped: list[str] = []
    loaded: list[str] = []

    real_open = builtins.open
    real_read_csv = pd.read_csv
    real_dump = joblib.dump
    real_load = joblib.load

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

    def spy_load(filename, *args, **kwargs):
        loaded.append(filename if isinstance(filename, str) else "<file object>")
        return real_load(filename, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(pd, "read_csv", spy_read_csv)
    monkeypatch.setattr(joblib, "dump", spy_dump)
    monkeypatch.setattr(joblib, "load", spy_load)
    yield {"opened": opened, "read": read, "dumped": dumped, "loaded": loaded}
    monkeypatch.undo()
    for path in opened + read:
        norm = path.replace("\\", "/")
        assert not ("data/experiment" in norm and "2026-09-30" in norm), f"FRESH-dated cache touched: {path}"
    for path in dumped:
        real = os.path.realpath(path)
        assert not (real == _REAL_SHADOW_DIR or real.startswith(_REAL_SHADOW_DIR + os.sep)), (
            f"joblib.dump wrote under the real data/shadow/models: {path}"
        )
    for path in loaded:
        if path != "<file object>":
            real = os.path.realpath(path)
            assert not real.startswith(_REAL_SHADOW_DIR + os.sep), f"a real frozen artifact was loaded: {path}"


# --------------------------------------------------------------------------
# Frames
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def dev_frame() -> pd.DataFrame:
    frame = pd.read_csv(_FIXTURE)
    for col in _DATE_COLUMNS:
        frame[col] = pd.to_datetime(frame[col], utc=True)
    return frame


def _shifted(dev_frame, city="AUSTIN", days=365) -> pd.DataFrame:
    frame = dev_frame[dev_frame["city"] == city].copy()
    for col in _DATE_COLUMNS:
        frame[col] = frame[col] - pd.Timedelta(days=days)
    return frame.reset_index(drop=True)


def _late_rows(frame: pd.DataFrame, n=24) -> pd.DataFrame:
    """Rows dated on or after the split (datetime_utc and anchor), built from real rows."""
    late = frame.iloc[:n].copy()
    late["datetime_utc"] = [_SPLIT + pd.Timedelta(hours=i) for i in range(n)]
    late["anchor_datetime_utc"] = late["datetime_utc"] - pd.Timedelta(hours=24)
    late["fcst_anchor_datetime_utc"] = late["anchor_datetime_utc"]
    return late


def _exact_count(frame: pd.DataFrame, upto=None) -> int:
    ts = pd.to_datetime(frame["datetime_utc"], utc=True)
    keep = ts < _SPLIT
    if upto is not None:
        keep &= ts <= upto
    hours = ts[keep].dt.hour
    return int((hours % config.FORECAST_EXPERIMENT_LEAD_FILTER_MODULUS
                == config.FORECAST_EXPERIMENT_24H_LEAD_FILTER_REMAINDER).sum())


def _drake_point(city="AUSTIN"):
    """The frozen Drake point (not the production point, which differs for AUSTIN since v3)."""
    return city_point.city_point(city)


# --------------------------------------------------------------------------
# fit_for_point: restriction and fit_end
# --------------------------------------------------------------------------

def test_fit_for_point_fits_only_rows_before_the_split(dev_frame, _spies, monkeypatch):
    base = _shifted(dev_frame)
    frame = pd.concat([base, _late_rows(base)], ignore_index=True)
    assert frame["datetime_utc"].max() >= _SPLIT  # the input does straddle the split

    seen = {}
    real_fit = forecast_correction_models.fit_cooling_correction

    def spy_fit(train_frame, factory, **kwargs):
        seen["max_dt"] = pd.to_datetime(train_frame["datetime_utc"], utc=True).max()
        seen["max_anchor"] = pd.to_datetime(train_frame["anchor_datetime_utc"], utc=True).max()
        return real_fit(train_frame, factory, **kwargs)

    monkeypatch.setattr(forecast_correction_models, "fit_cooling_correction", spy_fit)
    out = refit.fit_for_point("AUSTIN", frame, _drake_point(), methods=(_COOLING,))

    assert set(out["models"]) == {_COOLING}
    assert out["n_rows_fit"][_COOLING] == _exact_count(base)
    assert seen["max_dt"] < _SPLIT and seen["max_anchor"] < _SPLIT


def test_fit_for_point_fits_cooling_and_reference_by_default(dev_frame):
    out = refit.fit_for_point("MIDLAND", _shifted(dev_frame, "MIDLAND"), _drake_point("MIDLAND"))
    assert set(out["models"]) == set(refit.REFIT_METHODS)
    assert all(n > 0 for n in out["n_rows_fit"].values())


def test_anchor_reaching_the_split_after_restriction_raises(dev_frame):
    base = _shifted(dev_frame)
    bad = base.iloc[[0]].copy()
    bad["datetime_utc"] = [_SPLIT - pd.Timedelta(hours=12)]       # kept by the restriction
    bad["anchor_datetime_utc"] = [_SPLIT + pd.Timedelta(hours=0)]  # but its anchor reaches the split
    frame = pd.concat([base, bad], ignore_index=True)
    with pytest.raises(AssertionError, match="leak"):
        refit.fit_for_point("AUSTIN", frame, _drake_point(), methods=(_COOLING,))


def test_fit_end_restricts_the_rows_fit(dev_frame):
    frame = _shifted(dev_frame)
    fit_end = pd.Timestamp("2025-04-30T18:00:00Z")
    point = _drake_point()
    full = refit.fit_for_point("AUSTIN", frame, point)
    cut = refit.fit_for_point("AUSTIN", frame, point, fit_end=fit_end)
    assert cut["n_rows_fit"][_COOLING] == _exact_count(frame, upto=fit_end)
    assert cut["n_rows_fit"][_COOLING] < full["n_rows_fit"][_COOLING]
    assert cut["n_rows_fit"][_REFERENCE] < full["n_rows_fit"][_REFERENCE]


def test_prepare_fit_frame_recomputes_truth_under_the_given_point(dev_frame):
    frame = _shifted(dev_frame)
    drake = _drake_point()
    hot = city_point.production_city_point("AUSTIN")
    hot.conductor.T_max = 100.0
    f75, _ = refit.prepare_fit_frame(frame, drake, "AUSTIN")
    f100, exact100 = refit.prepare_fit_frame(frame, hot, "AUSTIN")
    assert (f100["truth_dlr_amps"] > f75["truth_dlr_amps"]).all()
    assert (exact100["city"] == "AUSTIN").all()
    assert {"fcst_perp_wind_ms", "anchor_perp_wind_ms", "truth_perp_wind_ms"} <= set(exact100.columns)


def test_arm5_frame_for_point_matches_the_shadow_frame_at_the_frozen_point(dev_frame):
    frame = _shifted(dev_frame, "EL_PASO")
    mine = refit.arm5_frame_for_point(frame, city_point.city_point("EL_PASO"), prefix="truth_")
    theirs = fm.weather_to_arm5_frame(frame, "EL_PASO", prefix="truth_")
    pd.testing.assert_frame_equal(mine, theirs, check_exact=True)


def test_fit_for_point_rejects_unknown_methods_and_cities(dev_frame):
    frame = _shifted(dev_frame)
    with pytest.raises(ValueError):
        refit.fit_for_point("AUSTIN", frame, _drake_point(), methods=("raw_forecast",))
    with pytest.raises(KeyError):
        refit.fit_for_point("NOWHERE", frame, _drake_point(), methods=(_COOLING,))


# --------------------------------------------------------------------------
# write_refit, manifest, refit_dir
# --------------------------------------------------------------------------

def _stub(tag):
    return {"stub": tag}


def test_write_refit_writes_artifacts_and_a_verifiable_manifest(tmp_path):
    paths = refit.write_refit("AUSTIN", {_COOLING: _stub("c"), _REFERENCE: _stub("r")}, "v-test", root=str(tmp_path))
    directory = tmp_path / "v-test"
    assert sorted(os.listdir(directory)) == sorted(
        [f"{_COOLING}_AUSTIN.joblib", f"{_REFERENCE}_AUSTIN.joblib", refit.MANIFEST_NAME])
    assert paths == {m: str(directory / f"{m}_AUSTIN.joblib") for m in (_COOLING, _REFERENCE)}
    manifest = live_check.read_manifest(str(directory / refit.MANIFEST_NAME))
    assert len(manifest) == 2
    for path in paths.values():
        assert manifest[refit._manifest_key(path)] == live_check.sha256_file(path)
    text = (directory / refit.MANIFEST_NAME).read_text()
    assert text.splitlines()[0].startswith("#") and "v-test" in text.splitlines()[0]
    assert joblib.load(paths[_COOLING]) == {"stub": "c"}


def test_manifest_lists_every_city_written_and_is_sorted(tmp_path):
    refit.write_refit("MIDLAND", {_COOLING: _stub("m")}, "v-test", root=str(tmp_path))
    refit.write_refit("AUSTIN", {_COOLING: _stub("a"), _REFERENCE: _stub("ar")}, "v-test", root=str(tmp_path))
    lines = [ln for ln in (tmp_path / "v-test" / refit.MANIFEST_NAME).read_text().splitlines()
             if ln and not ln.startswith("#")]
    keys = [ln.split("  ", 1)[1] for ln in lines]
    assert len(keys) == 3 and keys == sorted(keys)


def test_write_refit_refuses_wind(tmp_path):
    with pytest.raises(ValueError, match="reused, never refit"):
        refit.write_refit("AUSTIN", {_WIND: _stub("w")}, "v-test", root=str(tmp_path))
    with pytest.raises(ValueError, match="reused, never refit"):
        refit.write_refit("AUSTIN", {_COOLING: _stub("c"), _WIND: _stub("w")}, "v-test", root=str(tmp_path))
    assert os.listdir(tmp_path) == []


def test_write_refit_refuses_an_unknown_method_or_city(tmp_path):
    with pytest.raises(ValueError):
        refit.write_refit("AUSTIN", {"raw_forecast": _stub("x")}, "v-test", root=str(tmp_path))
    with pytest.raises(KeyError):
        refit.write_refit("../../etc", {_COOLING: _stub("x")}, "v-test", root=str(tmp_path))
    assert os.listdir(tmp_path) == []


def test_write_refit_never_overwrites(tmp_path):
    refit.write_refit("AUSTIN", {_COOLING: _stub("first")}, "v-test", root=str(tmp_path))
    before = live_check.sha256_file(str(tmp_path / "v-test" / f"{_COOLING}_AUSTIN.joblib"))
    with pytest.raises(FileExistsError):
        refit.write_refit("AUSTIN", {_COOLING: _stub("second"), _REFERENCE: _stub("new")}, "v-test", root=str(tmp_path))
    after = live_check.sha256_file(str(tmp_path / "v-test" / f"{_COOLING}_AUSTIN.joblib"))
    assert before == after
    # all-or-nothing: the new reference artifact was not written either
    assert not (tmp_path / "v-test" / f"{_REFERENCE}_AUSTIN.joblib").exists()
    assert not [n for n in os.listdir(tmp_path / "v-test") if n.endswith(".tmp")]


@pytest.mark.parametrize("version", ["a/b", "a\\b", "..", ".", "a..b", "../x", "", "/abs", "has space", "v1\n"])
def test_refit_dir_refuses_unsafe_versions(tmp_path, version):
    with pytest.raises(ValueError):
        refit.refit_dir(version, root=str(tmp_path))
    with pytest.raises(ValueError):
        refit.write_refit("AUSTIN", {_COOLING: _stub("c")}, version, root=str(tmp_path))


def test_refit_dir_accepts_the_live_config_version(tmp_path):
    assert refit.refit_dir(config.RATING_CONFIG_VERSION, root=str(tmp_path)) == os.path.join(
        str(tmp_path), config.RATING_CONFIG_VERSION)


def test_refit_dir_refuses_the_frozen_directory(tmp_path, monkeypatch):
    frozen = tmp_path / "shadow_models"
    frozen.mkdir()
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(frozen))
    # the version resolves to the frozen directory itself
    with pytest.raises(ValueError, match="data/shadow/models|frozen|SHADOW_MODEL_DIR"):
        refit.refit_dir("shadow_models", root=str(tmp_path))
    # the root is the frozen directory or inside it
    with pytest.raises(ValueError):
        refit.refit_dir("v1", root=str(frozen))
    with pytest.raises(ValueError):
        refit.refit_dir("v1", root=str(frozen / "sub"))
    with pytest.raises(ValueError):
        refit.write_refit("AUSTIN", {_COOLING: _stub("c")}, "v1", root=str(frozen))
    assert os.listdir(frozen) == []


def test_refit_dir_refuses_a_symlink_into_the_frozen_directory(tmp_path, monkeypatch):
    frozen = tmp_path / "shadow_models"
    frozen.mkdir()
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(frozen))
    link = tmp_path / "innocent"
    os.symlink(frozen, link)
    with pytest.raises(ValueError):
        refit.refit_dir("v1", root=str(link))
    assert os.listdir(frozen) == []


def test_default_root_is_outside_the_frozen_directory():
    resolved = os.path.realpath(refit.refit_dir("v-test"))
    assert not resolved.startswith(_REAL_SHADOW_DIR)
    assert resolved.endswith(os.path.join("data", "models", "conductor_refit", "v-test"))


# --------------------------------------------------------------------------
# verify-before-load
# --------------------------------------------------------------------------

def test_load_refit_model_loads_a_matching_artifact(tmp_path):
    refit.write_refit("AUSTIN", {_COOLING: _stub("c"), _REFERENCE: _stub("r")}, "v-test", root=str(tmp_path))
    assert refit.load_refit_model("AUSTIN", _COOLING, "v-test", root=str(tmp_path)) == {"stub": "c"}
    assert refit.load_refit_model("AUSTIN", _REFERENCE, "v-test", root=str(tmp_path)) == {"stub": "r"}


def test_a_flipped_byte_raises_and_joblib_load_is_not_called(tmp_path, _spies):
    paths = refit.write_refit("AUSTIN", {_COOLING: _stub("c")}, "v-test", root=str(tmp_path))
    path = paths[_COOLING]
    data = bytearray(open(path, "rb").read())
    data[len(data) // 2] ^= 0x01
    with open(path, "wb") as fh:
        fh.write(bytes(data))
    _spies["loaded"].clear()
    with pytest.raises(refit.ArtifactIntegrityError):
        refit.load_refit_model("AUSTIN", _COOLING, "v-test", root=str(tmp_path))
    assert _spies["loaded"] == []


def test_a_missing_manifest_entry_raises(tmp_path, _spies):
    refit.write_refit("AUSTIN", {_COOLING: _stub("c")}, "v-test", root=str(tmp_path))
    manifest = tmp_path / "v-test" / refit.MANIFEST_NAME
    manifest.write_text("# empty on purpose\n")
    _spies["loaded"].clear()
    with pytest.raises(refit.ArtifactIntegrityError, match="no entry"):
        refit.load_refit_model("AUSTIN", _COOLING, "v-test", root=str(tmp_path))
    assert _spies["loaded"] == []


def test_a_missing_manifest_or_file_raises(tmp_path, _spies):
    paths = refit.write_refit("AUSTIN", {_COOLING: _stub("c")}, "v-test", root=str(tmp_path))
    os.remove(tmp_path / "v-test" / refit.MANIFEST_NAME)
    _spies["loaded"].clear()
    with pytest.raises(refit.ArtifactIntegrityError):
        refit.load_refit_model("AUSTIN", _COOLING, "v-test", root=str(tmp_path))
    os.remove(paths[_COOLING])
    with pytest.raises(refit.ArtifactIntegrityError):
        refit.load_refit_model("AUSTIN", _COOLING, "v-test", root=str(tmp_path))
    assert _spies["loaded"] == []


def test_a_malformed_manifest_raises(tmp_path, _spies):
    refit.write_refit("AUSTIN", {_COOLING: _stub("c")}, "v-test", root=str(tmp_path))
    (tmp_path / "v-test" / refit.MANIFEST_NAME).write_text("not a manifest line\n")
    _spies["loaded"].clear()
    with pytest.raises(refit.ArtifactIntegrityError):
        refit.load_refit_model("AUSTIN", _COOLING, "v-test", root=str(tmp_path))
    assert _spies["loaded"] == []


def test_load_refit_model_refuses_wind_and_unknown_cities(tmp_path):
    with pytest.raises(ValueError):
        refit.load_refit_model("AUSTIN", _WIND, "v-test", root=str(tmp_path))
    with pytest.raises(KeyError):
        refit.load_refit_model("NOWHERE", _COOLING, "v-test", root=str(tmp_path))


def test_a_real_fitted_refit_round_trips_and_predicts(dev_frame, tmp_path):
    frame = _shifted(dev_frame)
    out = refit.fit_for_point("AUSTIN", frame, _drake_point())
    refit.write_refit("AUSTIN", out["models"], "v-test", root=str(tmp_path))
    cooling = refit.load_refit_model("AUSTIN", _COOLING, "v-test", root=str(tmp_path))
    assert cooling.n_rows_fit == out["n_rows_fit"][_COOLING]
    reference = refit.load_refit_model("AUSTIN", _REFERENCE, "v-test", root=str(tmp_path))
    assert hasattr(reference, "predict")


# --------------------------------------------------------------------------
# the headline loader
# --------------------------------------------------------------------------

@pytest.fixture
def frozen_dir(tmp_path, monkeypatch):
    """Stub frozen artifacts for AUSTIN and MIDLAND in a tmp SHADOW_MODEL_DIR with their own manifest."""
    directory = tmp_path / "shadow_models"
    directory.mkdir()
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(directory))
    lines = []
    for city in ("AUSTIN", "MIDLAND"):
        for method in (_WIND, _COOLING, _REFERENCE):
            path = shadow._model_path_for(city, method)
            joblib.dump({"frozen": f"{method}_{city}"}, path)
            lines.append(f"{live_check.sha256_file(path)}  {refit._manifest_key(path)}")
    manifest = tmp_path / "frozen_ARTIFACT_HASHES.sha256"
    manifest.write_text("# stub frozen manifest\n" + "\n".join(lines) + "\n")
    return {"dir": directory, "manifest": str(manifest), "lines": lines}


def test_headline_loader_serves_refit_cooling_and_reference_and_frozen_the_rest(tmp_path, frozen_dir):
    root = tmp_path / "refit"
    refit.write_refit("AUSTIN", {_COOLING: _stub("refit_c"), _REFERENCE: _stub("refit_r")}, "v-test", root=str(root))
    loader = refit.make_headline_loader("v-test", {"AUSTIN"}, root=str(root), frozen_manifest=frozen_dir["manifest"])

    assert loader("AUSTIN", _COOLING) == {"stub": "refit_c"}
    assert loader("AUSTIN", _REFERENCE) == {"stub": "refit_r"}
    assert loader("AUSTIN", _WIND) == {"frozen": f"{_WIND}_AUSTIN"}
    assert loader("MIDLAND", _COOLING) == {"frozen": f"{_COOLING}_MIDLAND"}

    served = {(s["city"], s["method"]): s for s in loader.served}
    assert len(loader.served) == 4 and len(served) == 4
    assert served[("AUSTIN", _COOLING)]["source"] == "refit"
    assert served[("AUSTIN", _REFERENCE)]["source"] == "refit"
    assert served[("AUSTIN", _WIND)]["source"] == "frozen"
    assert served[("MIDLAND", _COOLING)]["source"] == "frozen"
    for entry in loader.served:
        assert set(entry) >= {"city", "method", "path", "sha256", "source"}
        assert entry["sha256"] == live_check.sha256_file(entry["path"])
    assert served[("AUSTIN", _COOLING)]["path"].startswith(str(root))
    assert served[("MIDLAND", _COOLING)]["path"].startswith(str(frozen_dir["dir"]))


def test_headline_loader_without_refit_cities_serves_only_frozen(tmp_path, frozen_dir):
    loader = refit.make_headline_loader("v-test", set(), root=str(tmp_path / "none"),
                                        frozen_manifest=frozen_dir["manifest"])
    assert loader("AUSTIN", _COOLING) == {"frozen": f"{_COOLING}_AUSTIN"}
    assert [s["source"] for s in loader.served] == ["frozen"]


def test_headline_loader_serving_the_same_artifact_twice_records_it_once(tmp_path, frozen_dir):
    loader = refit.make_headline_loader("v-test", set(), root=str(tmp_path), frozen_manifest=frozen_dir["manifest"])
    loader("AUSTIN", _WIND)
    loader("AUSTIN", _WIND)
    assert len(loader.served) == 1


def test_headline_loader_checks_the_frozen_hash_before_loading(tmp_path, frozen_dir, _spies):
    loader = refit.make_headline_loader("v-test", set(), root=str(tmp_path), frozen_manifest=frozen_dir["manifest"])
    path = shadow._model_path_for("AUSTIN", _WIND)
    data = bytearray(open(path, "rb").read())
    data[len(data) // 2] ^= 0x01
    with open(path, "wb") as fh:
        fh.write(bytes(data))
    _spies["loaded"].clear()
    with pytest.raises(refit.ArtifactIntegrityError):
        loader("AUSTIN", _WIND)
    assert _spies["loaded"] == []
    assert loader.served == []


def test_headline_loader_frozen_entry_missing_from_the_manifest_raises(tmp_path, frozen_dir, _spies):
    kept = [ln for ln in frozen_dir["lines"] if f"{_WIND}_AUSTIN" not in ln]
    with open(frozen_dir["manifest"], "w") as fh:
        fh.write("\n".join(kept) + "\n")
    loader = refit.make_headline_loader("v-test", set(), root=str(tmp_path), frozen_manifest=frozen_dir["manifest"])
    _spies["loaded"].clear()
    with pytest.raises(refit.ArtifactIntegrityError, match="no entry"):
        loader("AUSTIN", _WIND)
    assert _spies["loaded"] == []


def test_headline_loader_missing_frozen_manifest_raises(tmp_path, frozen_dir):
    loader = refit.make_headline_loader("v-test", set(), root=str(tmp_path),
                                        frozen_manifest=str(tmp_path / "does_not_exist.sha256"))
    with pytest.raises(refit.ArtifactIntegrityError):
        loader("AUSTIN", _WIND)


def test_headline_loader_missing_frozen_file_is_a_file_not_found(tmp_path, frozen_dir):
    os.remove(shadow._model_path_for("MIDLAND", _REFERENCE))
    loader = refit.make_headline_loader("v-test", set(), root=str(tmp_path), frozen_manifest=frozen_dir["manifest"])
    with pytest.raises(FileNotFoundError):
        loader("MIDLAND", _REFERENCE)  # the confirm evaluator reads this as candidate_unavailable


def test_headline_loader_rejects_unknown_cities_and_methods(tmp_path, frozen_dir):
    with pytest.raises(KeyError):
        refit.make_headline_loader("v-test", {"NOWHERE"}, root=str(tmp_path), frozen_manifest=frozen_dir["manifest"])
    loader = refit.make_headline_loader("v-test", set(), root=str(tmp_path), frozen_manifest=frozen_dir["manifest"])
    with pytest.raises(KeyError):
        loader("NOWHERE", _WIND)
    with pytest.raises(ValueError):
        loader("AUSTIN", "raw_forecast")


def test_headline_loader_checks_the_real_frozen_manifest_by_default_without_loading_it():
    loader = refit.make_headline_loader("v-test", set())
    assert os.path.realpath(loader.frozen_manifest) == os.path.join(_REAL_SHADOW_DIR, "ARTIFACT_HASHES.sha256")
    # the real manifest parses and covers the 12 frozen artifacts (no artifact is loaded here)
    entries = live_check.read_manifest(loader.frozen_manifest)
    for city in config.LOCATIONS:
        for method in (_WIND, _COOLING, _REFERENCE):
            assert refit._manifest_key(shadow._model_path_for(city, method)) in entries


# --------------------------------------------------------------------------
# production_differs and the CLI
# --------------------------------------------------------------------------

@pytest.fixture
def drake_parity_table(monkeypatch):
    """Every city at the model-default Drake point (AUSTIN's max_temp_c back at 75 C), patched and never edited in
    config.py: the table as it stood before the v3 Power Systems switch, for tests of the no-differing-city path."""
    table = {c: dict(v) for c, v in config.PRODUCTION_CONDUCTORS.items()}
    table["AUSTIN"]["max_temp_c"] = 75.0
    monkeypatch.setattr(config, "PRODUCTION_CONDUCTORS", table)
    return table


@pytest.mark.parametrize("city", sorted(config.LOCATIONS))
def test_production_differs_is_false_at_drake_parity(city, drake_parity_table):
    assert refit.production_differs(city) is False


@pytest.mark.parametrize("city", sorted(config.LOCATIONS))
def test_production_differs_only_for_austin_in_the_live_table(city):
    assert refit.production_differs(city) is (city == "AUSTIN")


def test_production_differs_sees_a_conductor_or_bearing_change(monkeypatch):
    table = {c: dict(v) for c, v in config.PRODUCTION_CONDUCTORS.items()}
    table["AUSTIN"]["max_temp_c"] = 100.0
    table["MIDLAND"]["line_azimuth"] = 100.0
    monkeypatch.setattr(config, "PRODUCTION_CONDUCTORS", table)
    assert refit.production_differs("AUSTIN") is True
    assert refit.production_differs("MIDLAND") is True
    assert refit.production_differs("EL_PASO") is False
    with pytest.raises(KeyError):
        refit.production_differs("NOWHERE")


def test_cli_refuses_a_parity_city_with_the_d10_message_and_makes_no_file(tmp_path, capsys, drake_parity_table):
    rc = refit.main(["--cities", "AUSTIN", "--root", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 2
    message = captured.err + captured.out
    assert ("production config equals the frozen Drake configuration for AUSTIN; "
            "the frozen artifacts serve as its production models (D-10)") in message
    assert os.listdir(tmp_path) == []


def test_cli_with_the_production_diff_flag_and_no_differing_city_exits_zero(tmp_path, capsys, drake_parity_table):
    rc = refit.main(["--cities-from-production-diff", "--root", str(tmp_path)])
    assert rc == 0
    assert "no city differs from the frozen Drake configuration; nothing to refit (D-10)" in capsys.readouterr().out
    assert os.listdir(tmp_path) == []


def test_cli_requires_a_city_selection():
    with pytest.raises(SystemExit):
        refit.main([])


def _differing_table(monkeypatch, *cities):
    table = {c: dict(v) for c, v in config.PRODUCTION_CONDUCTORS.items()}
    for city in cities:
        table[city]["max_temp_c"] = 90.0
    monkeypatch.setattr(config, "PRODUCTION_CONDUCTORS", table)


def test_cli_refits_a_differing_city_under_its_production_point(tmp_path, dev_frame, monkeypatch, capsys):
    _differing_table(monkeypatch, "AUSTIN")
    monkeypatch.setattr(fm, "load_city_frame", lambda city: _shifted(dev_frame, city))
    root = tmp_path / "refit"
    rc = refit.main(["--cities-from-production-diff", "--config-version", "v-test", "--root", str(root)])
    out = capsys.readouterr().out
    assert rc == 0
    directory = root / "v-test"
    assert sorted(os.listdir(directory)) == sorted(
        [f"{_COOLING}_AUSTIN.joblib", f"{_REFERENCE}_AUSTIN.joblib", refit.MANIFEST_NAME])
    manifest = live_check.read_manifest(str(directory / refit.MANIFEST_NAME))
    for method in refit.REFIT_METHODS:
        path = str(directory / f"{method}_AUSTIN.joblib")
        sha = live_check.sha256_file(path)
        assert manifest[refit._manifest_key(path)] == sha
        assert f"AUSTIN {method} n_rows_fit=" in out and path in out and sha in out
    # the cooling model was fit under the production conductor (90 C), not the frozen Drake 75 C
    cooling = refit.load_refit_model("AUSTIN", _COOLING, "v-test", root=str(root))
    assert cooling.conductor.T_max == 90.0


def test_cli_checks_every_city_before_fitting_any(tmp_path, dev_frame, monkeypatch, capsys):
    _differing_table(monkeypatch, "AUSTIN")
    calls = []
    monkeypatch.setattr(fm, "load_city_frame", lambda city: calls.append(city) or _shifted(dev_frame, city))
    rc = refit.main(["--cities", "AUSTIN", "MIDLAND", "--config-version", "v-test", "--root", str(tmp_path)])
    assert rc == 2
    assert "MIDLAND" in capsys.readouterr().err
    assert calls == [] and os.listdir(tmp_path) == []


def test_cli_does_not_overwrite_an_existing_refit(tmp_path, dev_frame, monkeypatch, capsys):
    _differing_table(monkeypatch, "AUSTIN")
    monkeypatch.setattr(fm, "load_city_frame", lambda city: _shifted(dev_frame, city))
    args = ["--cities", "AUSTIN", "--config-version", "v-test", "--root", str(tmp_path)]
    assert refit.main(args) == 0
    capsys.readouterr()
    path = tmp_path / "v-test" / f"{_COOLING}_AUSTIN.joblib"
    before = live_check.sha256_file(str(path))
    assert refit.main(args) == 2
    assert "refusing to overwrite" in capsys.readouterr().err
    assert live_check.sha256_file(str(path)) == before


def test_cli_refuses_an_unsafe_version_and_the_frozen_directory(tmp_path, monkeypatch, capsys):
    _differing_table(monkeypatch, "AUSTIN")
    assert refit.main(["--cities", "AUSTIN", "--config-version", "../x", "--root", str(tmp_path)]) == 2
    frozen = tmp_path / "shadow_models"
    frozen.mkdir()
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(frozen))
    assert refit.main(["--cities", "AUSTIN", "--config-version", "v1", "--root", str(frozen)]) == 2
    assert os.listdir(frozen) == []


def test_cli_default_version_is_the_rating_config_version(tmp_path, dev_frame, monkeypatch):
    _differing_table(monkeypatch, "AUSTIN")
    monkeypatch.setattr(fm, "load_city_frame", lambda city: _shifted(dev_frame, city))
    assert refit.main(["--cities", "AUSTIN", "--root", str(tmp_path)]) == 0
    assert os.listdir(tmp_path) == [config.RATING_CONFIG_VERSION]


# --------------------------------------------------------------------------
# isolation
# --------------------------------------------------------------------------

def test_the_module_never_calls_the_frozen_save_helper():
    tree = ast.parse(open(refit.__file__, encoding="utf-8").read())
    used = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    used |= {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert "save_correction_model" not in used


def test_a_refit_run_touches_neither_data_experiment_nor_the_frozen_directory(tmp_path, dev_frame, _spies):
    out = refit.fit_for_point("AUSTIN", _shifted(dev_frame), _drake_point())
    refit.write_refit("AUSTIN", out["models"], "v-test", root=str(tmp_path))
    assert all("data/experiment" not in p.replace("\\", "/") for p in _spies["opened"] + _spies["read"])
    assert _spies["dumped"] and all(str(tmp_path) in p for p in _spies["dumped"])
