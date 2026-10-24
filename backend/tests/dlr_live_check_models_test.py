"""
Tests for backend/dlr_live_check_models.py -- the live model pre-flight
(production-pipeline Phase 5, PIPE-02, OD-3, OD-10).

Every test runs offline against joblib-dumped stand-ins under `tmp_path`: the
two model directories in `config` are redirected there, both loader caches are
reset, and the manifest is a temporary file. No scikit-learn model is needed,
because the pre-flight only hashes files and calls the production loaders.
Stand-in files and manifests are written with `joblib`, `hashlib` and plain file
writes, never with the module under test, so `check` is exercised independently
of `write_manifest`. Follows backend/tests/dlr_live_run_test.py's conventions
(no conftest.py, plain asserts, no test classes).
"""

import hashlib
import os

import joblib
import pytest

import ampacity_forecast
import anomaly_detector
import config
import dlr_live_check_models as preflight

_KINDS = ("forecast", "anomaly")


def _resolver(kind):
    return ampacity_forecast._model_path_for if kind == "forecast" else anomaly_detector._model_path_for


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _artifact_paths():
    return {(kind, city): _resolver(kind)(city) for kind in _KINDS for city in config.LOCATIONS}


def _write_manifest(path, paths=None, comments=()):
    """A manifest in sha256sum format, hashed straight from the files on disk."""
    chosen = sorted((paths or _artifact_paths()).values())
    lines = list(comments) + [f"{_sha(p)}  {p}" for p in chosen]
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    return str(path)


@pytest.fixture
def models(tmp_path, monkeypatch):
    """Eight stand-in artifacts under tmp_path, resolved through the production path functions."""
    forecast_dir = tmp_path / "forecast_models"
    anomaly_dir = tmp_path / "anomaly_models"
    forecast_dir.mkdir()
    anomaly_dir.mkdir()
    monkeypatch.setattr(config, "FORECAST_ML_MODEL_DIR", str(forecast_dir))
    monkeypatch.setattr(config, "ANOMALY_ML_MODEL_DIR", str(anomaly_dir))
    monkeypatch.setattr(ampacity_forecast, "_MODEL_CACHE", {})
    monkeypatch.setattr(anomaly_detector, "_MODEL_CACHE", {})
    for (kind, city), path in _artifact_paths().items():
        joblib.dump({"city": city, "kind": kind}, path)
    return _artifact_paths()


@pytest.fixture
def load_spy(monkeypatch):
    """Record every call to the two production loaders, without loading anything."""
    calls = []
    monkeypatch.setattr(ampacity_forecast, "_load_model", lambda city: calls.append(("forecast", city)))
    monkeypatch.setattr(anomaly_detector, "_load_city_model", lambda city: calls.append(("anomaly", city)))
    return calls


def test_all_present_and_matching_passes(models, tmp_path, monkeypatch, capsys):
    manifest = _write_manifest(tmp_path / "LIVE.sha256", comments=["# promoted 2026-10-24", ""])
    expected = {(kind, city, models[(kind, city)]) for kind in _KINDS for city in config.LOCATIONS}
    assert len(expected) == 8
    assert set(preflight.required_artifacts()) == expected

    assert preflight.check(manifest) == []
    # The strict loaders really ran on every artifact (the caches hold all eight).
    assert sorted(ampacity_forecast._MODEL_CACHE) == sorted(config.LOCATIONS)
    assert sorted(anomaly_detector._MODEL_CACHE) == sorted(config.LOCATIONS)

    monkeypatch.setattr(preflight, "MANIFEST_PATH", manifest)
    assert preflight.main([]) == 0
    out = capsys.readouterr()
    assert out.out.strip() == f"OK: all 8 live model artifacts present and match {manifest}"
    assert out.err == ""


def test_missing_artifact_fails_and_names_the_path(models, tmp_path, monkeypatch, load_spy, capsys):
    manifest = _write_manifest(tmp_path / "LIVE.sha256")
    gone = models[("forecast", "MIDLAND")]
    os.remove(gone)

    problems = preflight.check(manifest)

    assert len(problems) == 1
    assert gone in problems[0]
    assert "missing" in problems[0]
    assert load_spy == []  # nothing is loaded while a problem is open

    monkeypatch.setattr(preflight, "MANIFEST_PATH", manifest)
    assert preflight.main([]) == 1
    captured = capsys.readouterr()
    assert gone in captured.err
    assert "OK" not in captured.out


def test_tampered_artifact_fails_before_any_load(models, tmp_path, monkeypatch, load_spy, capsys):
    manifest = _write_manifest(tmp_path / "LIVE.sha256")
    tampered = models[("anomaly", "EL_PASO")]
    joblib.dump({"city": "EL_PASO", "kind": "anomaly", "substituted": True}, tampered)

    problems = preflight.check(manifest)

    assert len(problems) == 1
    assert "hash mismatch" in problems[0]
    assert tampered in problems[0]
    # Seven artifacts are intact, but none of them was deserialized either.
    assert load_spy == []

    monkeypatch.setattr(preflight, "MANIFEST_PATH", manifest)
    assert preflight.main([]) == 1
    assert "hash mismatch" in capsys.readouterr().err
    assert load_spy == []


def test_missing_or_incomplete_manifest_fails(models, tmp_path, monkeypatch, load_spy, capsys):
    absent = str(tmp_path / "absent.sha256")
    problems = preflight.check(absent)
    assert problems and any(absent in p for p in problems)

    empty = tmp_path / "empty.sha256"
    empty.write_text("")
    problems = preflight.check(str(empty))
    assert problems and any(str(empty) in p for p in problems)

    comments_only = tmp_path / "comments.sha256"
    comments_only.write_text("# nothing listed\n\n")
    problems = preflight.check(str(comments_only))
    assert problems and any(str(comments_only) in p for p in problems)

    # One path left out of an otherwise complete manifest.
    omitted = models[("forecast", "AUSTIN")]
    partial_paths = {key: path for key, path in models.items() if path != omitted}
    partial = _write_manifest(tmp_path / "partial.sha256", partial_paths)
    problems = preflight.check(partial)
    assert len(problems) == 1
    assert partial in problems[0]
    assert omitted in problems[0]

    # A line that is not "<64 hex>  <path>" is reported, not skipped.
    garbled = tmp_path / "garbled.sha256"
    garbled.write_text("this is not a hash line\n")
    problems = preflight.check(str(garbled))
    assert problems and any(str(garbled) in p for p in problems)

    assert load_spy == []

    monkeypatch.setattr(preflight, "MANIFEST_PATH", absent)
    assert preflight.main([]) == 1
    assert absent in capsys.readouterr().err


def test_unloadable_artifact_fails_after_hashes_match(models, tmp_path):
    broken = models[("anomaly", "AUSTIN")]
    with open(broken, "wb") as fh:
        fh.write(b"this is not a joblib payload")
    manifest = _write_manifest(tmp_path / "LIVE.sha256")  # hashes the broken bytes, so they match

    problems = preflight.check(manifest)

    assert len(problems) == 1
    assert problems[0].startswith("load failed: AUSTIN anomaly: ")
    # With load disabled the same tree passes: the failure came from the loader, not the hashes.
    assert preflight.check(manifest, load=False) == []


def test_write_manifest_round_trip_and_refuses_missing_files(models, tmp_path, monkeypatch, load_spy, capsys):
    manifest = tmp_path / "written.sha256"

    assert preflight.write_manifest(str(manifest)) == []

    lines = [ln for ln in manifest.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    assert len(lines) == 8
    parsed = [ln.split("  ", 1) for ln in lines]
    assert all(len(digest) == 64 and set(digest) <= set("0123456789abcdef") for digest, _ in parsed)
    assert [path for _, path in parsed] == sorted(models.values())
    assert {path: digest for digest, path in parsed} == {path: _sha(path) for path in models.values()}
    assert load_spy == []  # writing the manifest never deserializes anything

    assert preflight.check(str(manifest), load=False) == []

    # With one artifact gone the writer refuses and leaves no manifest behind.
    gone = models[("forecast", "EL_PASO")]
    os.remove(gone)
    refused = tmp_path / "refused.sha256"
    problems = preflight.write_manifest(str(refused))
    assert len(problems) == 1
    assert gone in problems[0]
    assert not refused.exists()

    monkeypatch.setattr(preflight, "MANIFEST_PATH", str(refused))
    assert preflight.main(["--write-manifest"]) == 1
    assert gone in capsys.readouterr().err
    assert not refused.exists()
