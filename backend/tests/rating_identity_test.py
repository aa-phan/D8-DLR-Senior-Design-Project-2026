"""
Offline tests of the rating identity every stored row carries (production-pipeline
Phase 4, DB-06): the per-city configuration fingerprint, the model file hashes and
the guarantee that a conductor, model or forecast-method change alters values
only, never the row's columns.

Follows backend/tests/city_rating_test.py's conventions (module-level imports,
plain asserts, no test classes, no network).
"""

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

import pytest
import requests

import ampacity_forecast
import anomaly_detector
import city_point
import config
import supabase_store
import thermal_model

_BACKEND = os.path.join(os.path.dirname(__file__), "..")
_REPO = os.path.join(_BACKEND, "..")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """
    Replace `requests.get` for every test. The composer and `rate_city` catch
    every provider exception, so raising alone could be swallowed; the teardown
    assert on the recorded attempts cannot be.
    """
    attempts = []

    def boom(url, *args, **kwargs):
        attempts.append(url)
        raise AssertionError("requests.get must not be called in this test")

    monkeypatch.setattr(requests, "get", boom)
    yield
    assert attempts == []


@pytest.fixture(autouse=True)
def _offline_env(tmp_path, monkeypatch):
    # Another test module loads `.env` into the process at import time.
    for name in ("SYNOPTIC_TOKEN", "NREL_API_KEY", "NREL_API_EMAIL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "HISTORICAL_ARCHIVE_PATH", str(tmp_path / "default_archive.csv"))
    # Trained models are git-ignored, so a test must not depend on whether this
    # checkout has them.
    monkeypatch.setattr(anomaly_detector, "_load_city_model_or_none", lambda city: None)


def _fingerprints():
    return {city: supabase_store.rating_config_fingerprint(city) for city in config.LOCATIONS}


def _result(**overrides):
    """A rate_city-shaped result with a `pipeline` key."""
    result = {
        "city": "AUSTIN",
        "point": (30.2711, -97.7437),
        "station_id": "T_AUSTIN",
        "candidates_probed": 1,
        "probe_trail": [{"stid": "T_AUSTIN", "lat": 30.27, "lon": -97.74, "distance_km": 0.5, "outcome": "ok"}],
        "rating": 1825.0,
        "status": "ok",
        "fallback": False,
        "alerts": [],
        "observation": {"sensor_status": "ok", "link_status": "ok", "temp": 25.0, "wind": 6.5,
                        "solar": 500.0, "wind_direction": 263.15, "wind_raw": 6.5},
        "exhausted": False,
        "archived": False,
        "pipeline": {
            "history_rows": 10, "usable_history_rows": 9, "forecast_method": "naive",
            "forecast_used_by_g6": False, "forecast": None, "detector_signal": "cold_start",
            "detector_model": None,
        },
    }
    result.update(overrides)
    return result


_RUN_CTX = {"run_id": "123", "run_attempt": 1, "pipeline_version": "abcdef1"}


def _patch_austin_conductor(monkeypatch, **changes):
    """Rebuild only AUSTIN's ConductorConfig with `changes` applied to its kwargs."""
    real = city_point.city_point

    def patched(city):
        point = real(city)
        if city == "AUSTIN":
            kwargs = config.conductor_kwargs_for(config.CITY_LINE_BEARING_DEG[city])
            kwargs.update(changes)
            point.conductor = thermal_model.ConductorConfig(**kwargs)
        return point

    monkeypatch.setattr(city_point, "city_point", patched)


def test_fingerprint_is_hex_per_city_and_stable_across_processes():
    fingerprints = _fingerprints()
    assert set(fingerprints) == set(config.LOCATIONS)
    assert all(_HEX64.match(value) for value in fingerprints.values())
    assert len(set(fingerprints.values())) == len(config.LOCATIONS)

    code = (
        "import json, config, supabase_store;"
        "print(json.dumps({c: supabase_store.rating_config_fingerprint(c) for c in config.LOCATIONS}))"
    )
    for seed in ("0", "12345"):
        env = dict(os.environ, PYTHONPATH=os.path.abspath(_BACKEND), PYTHONHASHSEED=seed, MPLBACKEND="Agg")
        out = subprocess.run(
            [sys.executable, "-c", code], cwd=os.path.abspath(_REPO), env=env,
            capture_output=True, text=True, timeout=180, check=True,
        )
        assert json.loads(out.stdout.strip().splitlines()[-1]) == fingerprints


_ALL = set(config.LOCATIONS)


def _conductor(name, value):
    return lambda mp: _patch_austin_conductor(mp, **{name: value})


_CASES = [
    ("austin-diameter_m", _conductor("diameter_m", 0.03), {"AUSTIN"}),
    ("austin-resistance_ac", _conductor("resistance_ac", 0.08), {"AUSTIN"}),
    ("austin-resist_temp_coef", _conductor("resist_temp_coef", 0.0041), {"AUSTIN"}),
    ("austin-emissivity", _conductor("emissivity", 0.7), {"AUSTIN"}),
    ("austin-absorptivity", _conductor("absorptivity", 0.7), {"AUSTIN"}),
    ("austin-max_temp_c", _conductor("max_temp_c", 80.0), {"AUSTIN"}),
    ("austin-elevation_m", _conductor("elevation_m", 1000.0), {"AUSTIN"}),
    ("austin-line_azimuth", _conductor("line_azimuth", 100.0), {"AUSTIN"}),
    ("static-el-paso", lambda mp: mp.setitem(config.STATIC_RATINGS, "EL_PASO", 1300.0), {"EL_PASO"}),
    ("bounds-midland",
     lambda mp: mp.setitem(config.RATING_BOUNDS_BY_LOCATION, "MIDLAND", (1200.0, 2500.0)), {"MIDLAND"}),
    ("bearing-corpus-christi",
     lambda mp: mp.setitem(config.CITY_LINE_BEARING_DEG, "CORPUS_CHRISTI", 170.0), {"CORPUS_CHRISTI"}),
    ("subconductors-austin", lambda mp: mp.setitem(config.SUBCONDUCTORS_PER_PHASE, "AUSTIN", 3), {"AUSTIN"}),
    ("g6-limit-midland",
     lambda mp: mp.setitem(config.ANOMALY_CONTROL_LIMIT_K_BY_LOCATION, "MIDLAND", 9.0), {"MIDLAND"}),
    ("line-voltage", lambda mp: mp.setattr(config, "LINE_VOLTAGE_KV", 400.0), _ALL),
    ("power-factor", lambda mp: mp.setattr(config, "POWER_FACTOR", 0.9), _ALL),
    ("default-conductor-max-temp",
     lambda mp: mp.setitem(config.DEFAULT_CONDUCTOR_CONFIG_KWARGS, "max_temp_c", 80.0), _ALL),
    ("forecast-horizon", lambda mp: mp.setattr(config, "FORECAST_HORIZON_MINUTES", 120.0), _ALL),
]


@pytest.mark.parametrize("apply_change, expected", [c[1:] for c in _CASES], ids=[c[0] for c in _CASES])
def test_each_rating_assumption_changes_only_its_citys_fingerprint(monkeypatch, apply_change, expected):
    before = _fingerprints()

    apply_change(monkeypatch)
    after = _fingerprints()
    changed = {city for city in config.LOCATIONS if before[city] != after[city]}
    assert changed == expected
    assert all(_HEX64.match(value) for value in after.values())

    monkeypatch.undo()
    assert _fingerprints() == before


def _config_names_read_by(module):
    """Every `config.<NAME>` (and `from config import NAME`) in one backend module, by AST."""
    path = os.path.join(_BACKEND, f"{module}.py")
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=path)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "config":
            names.add(node.attr)
        elif isinstance(node, ast.ImportFrom) and node.module == "config":
            names.update(alias.name for alias in node.names)
    return names


def test_every_config_name_the_rating_path_reads_is_classified():
    fingerprinted = set(supabase_store.FINGERPRINTED_CONFIG_NAMES)
    unfingerprinted = set(supabase_store.UNFINGERPRINTED_CONFIG_NAMES)
    assert fingerprinted.isdisjoint(unfingerprinted)
    assert all(hasattr(config, name) for name in fingerprinted), "a fingerprinted name is not in config"
    assert all(hasattr(config, name) for name in unfingerprinted), "an unfingerprinted name is not in config"
    assert all(str(reason).strip() for reason in supabase_store.UNFINGERPRINTED_CONFIG_NAMES.values())

    unclassified = []
    for module in supabase_store.RATING_PATH_MODULES:
        for name in sorted(_config_names_read_by(module)):
            if name not in fingerprinted and name not in unfingerprinted:
                unclassified.append(f"config.{name} (read in {module}.py)")
    assert not unclassified, (
        "config names on the rating path that supabase_store neither fingerprints nor excludes with a "
        "reason (add each to FINGERPRINTED_CONFIG_NAMES or UNFINGERPRINTED_CONFIG_NAMES): "
        + "; ".join(unclassified)
    )


def _forecast_pipeline(method, with_forecast=True, detector_model=None):
    return {
        "forecast_method": method,
        "forecast": {"amps": 1700.0} if with_forecast else None,
        "detector_model": detector_model,
    }


def _sha256_cli(path):
    shasum = shutil.which("shasum")
    if shasum is None:
        return None
    out = subprocess.run([shasum, "-a", "256", str(path)], capture_output=True, text=True, check=True)
    return out.stdout.split()[0]


def test_model_hashes_match_the_loaded_files_or_are_null(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "FORECAST_ML_MODEL_DIR", str(tmp_path))
    forecast_file = tmp_path / "forecast_AUSTIN.joblib"
    forecast_file.write_bytes(b"forecast-model-bytes\x00\x01\x02")
    detector_file = tmp_path / "anomaly_AUSTIN.joblib"
    detector_file.write_bytes(b"anomaly-model-bytes")

    expected_forecast = hashlib.sha256(b"forecast-model-bytes\x00\x01\x02").hexdigest()
    expected_anomaly = hashlib.sha256(b"anomaly-model-bytes").hexdigest()
    cli = _sha256_cli(forecast_file)
    if cli is not None:
        assert cli == expected_forecast

    identity = supabase_store.model_identity("AUSTIN", _forecast_pipeline("ml", detector_model=str(detector_file)))
    assert identity == {"forecast_model_sha256": expected_forecast, "anomaly_model_sha256": expected_anomaly}
    cli = _sha256_cli(detector_file)
    if cli is not None:
        assert cli == expected_anomaly

    # "ml" without a forecast never loaded the model; "naive" and "ewm" have no artifact.
    assert supabase_store.model_identity("AUSTIN", _forecast_pipeline("ml", with_forecast=False)) == {
        "forecast_model_sha256": None, "anomaly_model_sha256": None}
    for method in ("naive", "ewm"):
        assert supabase_store.model_identity("AUSTIN", _forecast_pipeline(method)) == {
            "forecast_model_sha256": None, "anomaly_model_sha256": None}

    with pytest.raises(ValueError, match="telepathy"):
        supabase_store.model_identity("AUSTIN", _forecast_pipeline("telepathy"))

    # A used model that is missing must fail the row, never write a NULL.
    with pytest.raises(FileNotFoundError):
        supabase_store.model_identity("EL_PASO", _forecast_pipeline("ml"))


def test_every_forecast_method_is_classified_for_model_identity():
    with_artifact = set(supabase_store.FORECAST_ARTIFACT_PATHS)
    without = set(supabase_store.FORECAST_METHODS_WITHOUT_ARTIFACT)
    assert with_artifact.isdisjoint(without)
    assert with_artifact | without == set(ampacity_forecast.FORECAST_METHODS)
    assert supabase_store.FORECAST_ARTIFACT_PATHS["ml"] is ampacity_forecast._model_path_for


def test_a_conductor_or_model_change_alters_values_not_columns(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "FORECAST_ML_MODEL_DIR", str(tmp_path))
    model_file = tmp_path / "forecast_AUSTIN.joblib"
    model_file.write_bytes(b"model-one")
    result = _result()
    result["pipeline"] = dict(result["pipeline"], forecast_method="ml", forecast={
        "amps": 1700.0, "ci_lower_amps": 1650.0, "ci_upper_amps": 1750.0,
        "n_observations": 40, "horizon_min": 60.0})

    before = supabase_store.build_rating_row(result, "2025-06-01T14:07:00Z", _RUN_CTX)

    _patch_austin_conductor(monkeypatch, diameter_m=0.031)
    model_file.write_bytes(b"model-two")
    after = supabase_store.build_rating_row(result, "2025-06-01T14:07:00Z", _RUN_CTX)

    assert tuple(before) == supabase_store.CITY_RATING_COLUMNS
    assert tuple(after) == supabase_store.CITY_RATING_COLUMNS
    differing = {key for key in before if before[key] != after[key]}
    assert differing == {"config_fingerprint", "forecast_model_sha256"}
    assert before["forecast_model_sha256"] == hashlib.sha256(b"model-one").hexdigest()
    assert after["forecast_model_sha256"] == hashlib.sha256(b"model-two").hexdigest()


def test_store_reexports_the_identity_recipe():
    # The recipe lives in rating_identity (a dependency set the Phase 3 backfill child can
    # load); supabase_store keeps every name as an attribute and is the same object.
    import rating_identity

    for name in (
        "RATING_CONFIG_SNAPSHOT_SCHEMA",
        "RATING_CONFIG_SOURCE_FILES",
        "RATING_PATH_MODULES",
        "FINGERPRINTED_CONFIG_NAMES",
        "UNFINGERPRINTED_CONFIG_NAMES",
        "rating_config_snapshot",
        "rating_config_fingerprint",
    ):
        assert getattr(supabase_store, name) is getattr(rating_identity, name), name
    assert _fingerprints() == {
        city: rating_identity.rating_config_fingerprint(city) for city in config.LOCATIONS
    }
