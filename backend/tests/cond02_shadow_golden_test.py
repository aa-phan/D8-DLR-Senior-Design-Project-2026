"""
COND-02 proof (production-pipeline Phase 7, plan 01): the frozen shadow path is byte-identical to the
untouched tree while production moves to per-city conductor configs.

The committed golden (`fixtures/golden_shadow_baseline_d71c501.json`) was captured by
`golden_shadow_capture.py --capture` from a `git archive d71c501 backend` copy in a child process whose
import path held only that copy. These tests recompute every section on the LIVE tree and require an exact
match: city_point geometry and conductor attributes, the truth / raw_forecast / persistence arms on the
committed dev fixture, the three shadow fits on a time-shifted copy of it, the collector's per-row methods,
the dev-basis nine-test family with per-city metrics, and the sha256 of the 12 frozen artifacts. A source
guard requires the frozen modules to have no diff since the baseline, and a negative control shows the golden
fails when the Drake conductor changes.

Nothing here loads one of the 12 real frozen artifacts (the dev fixture is TEST-split data; scoring the real
artifacts needs the signed v4): fits and the evaluation run use stub models fitted on the fixture, and the
artifacts are only hashed. Offline: `requests.get` raises.

If the shadow path is changed deliberately (it must not be, COND-02), re-capture with
`PYTHONPATH=backend .venv/bin/python backend/tests/golden_shadow_capture.py --capture` only after confirming
the change is intended and signed off.
"""

import hashlib
import json
import os
import subprocess

import pytest
import requests

import config
import golden_shadow_capture as golden

_SIGNATURE_PREFIX = "- Signature:"


def _git(*args):
    return subprocess.run(["git", *args], cwd=golden.REPO_ROOT, check=True, capture_output=True, text=True).stdout


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    attempts = []

    def boom(url, *args, **kwargs):
        attempts.append(url)
        raise AssertionError("requests.get must not be called in this test")

    monkeypatch.setattr(requests, "get", boom)
    yield
    assert attempts == []


@pytest.fixture(scope="module")
def baseline():
    with open(golden.GOLDEN_PATH, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def live():
    """The live-tree payload, computed once, with the real-artifact loaders spied and the network blocked."""
    import joblib

    import forecast_shadow_pipeline

    calls = {"joblib.load": 0, "load_correction_model": 0}
    real_joblib_load = joblib.load
    real_load_model = forecast_shadow_pipeline.load_correction_model

    def spy_joblib_load(*args, **kwargs):
        calls["joblib.load"] += 1
        return real_joblib_load(*args, **kwargs)

    def spy_load_model(*args, **kwargs):
        calls["load_correction_model"] += 1
        return real_load_model(*args, **kwargs)

    def boom(url, *args, **kwargs):
        raise AssertionError("requests.get must not be called while computing the golden payload")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(joblib, "load", spy_joblib_load)
        mp.setattr(forecast_shadow_pipeline, "load_correction_model", spy_load_model)
        mp.setattr(requests, "get", boom)
        payload = golden.compute_payload()
    return {"payload": payload, "calls": calls}


def test_golden_fixture_records_the_untouched_baseline_commit(baseline):
    assert baseline["source_commit"].startswith(golden.BASELINE_COMMIT)
    assert len(baseline["source_commit"]) == 40
    _git("cat-file", "-e", baseline["source_commit"] + "^{commit}")
    assert baseline["fixture_sha256"] == golden.FIXTURE_SHA256
    assert sorted(baseline["payload"]) == sorted(golden.SECTIONS)


def test_versions_match_the_capture(baseline):
    """Fails (never skips): the golden is deterministic only under the captured library versions."""
    current = golden.versions()
    differing = {k: (baseline["versions"].get(k), current[k]) for k in current if baseline["versions"].get(k) != current[k]}
    assert not differing, (
        f"library versions differ from the golden capture {differing} (captured, current). The golden is only "
        "deterministic under the captured versions: confirm the shadow path is unchanged, then re-capture with "
        "golden_shadow_capture.py --capture")


@pytest.mark.parametrize("section", golden.SECTIONS)
def test_shadow_section_is_identical_to_the_baseline(section, baseline, live):
    assert live["payload"][section] == baseline["payload"][section], (
        f"shadow section {section!r} differs from the d71c501 baseline: the frozen path changed (COND-02)")


def test_frozen_artifacts_match_their_manifest():
    seen = 0
    with open(golden.ARTIFACT_MANIFEST, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            want, rel = line.split(None, 1)
            digest = hashlib.sha256()
            with open(os.path.join(golden.REPO_ROOT, rel.strip()), "rb") as art:
                digest.update(art.read())
            assert digest.hexdigest() == want, f"frozen artifact {rel} no longer matches ARTIFACT_HASHES.sha256"
            seen += 1
    assert seen == 12


def test_frozen_sources_are_unchanged_since_baseline():
    changed = _git("diff", "--name-only", golden.BASELINE_COMMIT, "--", *golden.FROZEN_PATHS).split()
    assert changed == [], f"frozen shadow sources differ from {golden.BASELINE_COMMIT}: {changed}"
    untracked = _git("status", "--porcelain", "--untracked-files=all", "--", *golden.FROZEN_PATHS).split("\n")
    assert [u for u in untracked if u.strip()] == [], f"untracked or modified files under the frozen paths: {untracked}"

    for path in golden.V4_PERMITTED_PATHS:
        if not _git("diff", "--name-only", golden.BASELINE_COMMIT, "--", path).strip():
            continue
        signing = os.path.join(golden.REPO_ROOT, golden.V4_SIGNING_COPY)
        assert os.path.isfile(signing), (
            f"{path} differs from {golden.BASELINE_COMMIT} but the signed v4 signing copy does not exist")
        with open(signing, encoding="utf-8") as fh:
            lines = [ln.strip() for ln in fh if ln.strip().startswith(_SIGNATURE_PREFIX)]
        filled = [ln for ln in lines if ln[len(_SIGNATURE_PREFIX):].replace("_", "").strip()]
        assert filled, f"{path} differs from {golden.BASELINE_COMMIT} but the v4 signing copy has no filled signature line"


def test_golden_has_power(baseline, monkeypatch):
    """Negative control: a different Drake conductor must make the geometry and arms sections differ."""
    monkeypatch.setitem(config.DEFAULT_CONDUCTOR_CONFIG_KWARGS, "max_temp_c", 80.0)
    assert golden.compute_section("geometry") != baseline["payload"]["geometry"]
    assert golden.compute_section("arms") != baseline["payload"]["arms"]


def test_no_real_artifact_is_loaded(live):
    assert live["calls"] == {"joblib.load": 0, "load_correction_model": 0}
