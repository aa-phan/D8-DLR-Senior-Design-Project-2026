"""
Tests for the day-ahead tier of backend/dlr_live_check_models.py (production-pipeline Phase 8,
DAY-02, DAY-04, D-13, D-13a).

The live pre-flight verifies the eight live models and exits 1 for any problem with them. The
four served cooling files and the band artifact are verified the same way (presence, then sha256,
then a strict load) but a problem with them is only a GitHub `::warning::` line: the exit code
comes from the eight live models alone, so a day-ahead problem can never stop live ratings.

Every behavior test runs offline on stand-in files under `tmp_path`; the day-ahead modules are
monkeypatched to point at them and to record loads instead of unpickling anything. The last group
of tests reads the real committed tree, with no stand-ins and no deserializing.
"""

import hashlib
import os
import subprocess
import sys

import joblib
import pytest

import ampacity_forecast
import anomaly_detector
import config
import day_ahead_band
import day_ahead_forecast
import dlr_live_check_models as preflight

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_KINDS = ("forecast", "anomaly")
_LOADED = "ml_cooling_corrected"
_WARNING_PREFIX = "::warning title=day-ahead artifact::"


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _manifest_lines(paths):
    return [f"{_sha(path)}  {path}" for path in sorted(paths)]


class World:
    """Stand-in live models and day-ahead files, a manifest listing all thirteen, and the load spies."""

    def __init__(self, tmp_path):
        self.tmp_path = tmp_path
        self.live = {}
        self.cooling = {}
        self.band = str(tmp_path / "da" / "bands.json")
        self.loads = []  # cooling loader calls (city, method)
        self.band_loads = []
        self.manifest = str(tmp_path / "LIVE.sha256")

    def write_manifest(self, skip=()):
        paths = [p for p in [*self.live.values(), *self.cooling.values(), self.band] if p not in skip]
        with open(self.manifest, "w") as fh:
            fh.write("\n".join(["# stand-in manifest", *_manifest_lines(paths)]) + "\n")


@pytest.fixture
def world(tmp_path, monkeypatch):
    forecast_dir = tmp_path / "forecast_models"
    anomaly_dir = tmp_path / "anomaly_models"
    da_dir = tmp_path / "da"
    for directory in (forecast_dir, anomaly_dir, da_dir):
        directory.mkdir()
    monkeypatch.setattr(config, "FORECAST_ML_MODEL_DIR", str(forecast_dir))
    monkeypatch.setattr(config, "ANOMALY_ML_MODEL_DIR", str(anomaly_dir))
    monkeypatch.setattr(ampacity_forecast, "_MODEL_CACHE", {})
    monkeypatch.setattr(anomaly_detector, "_MODEL_CACHE", {})

    state = World(tmp_path)
    resolvers = {"forecast": ampacity_forecast._model_path_for, "anomaly": anomaly_detector._model_path_for}
    for kind in _KINDS:
        for city in config.LOCATIONS:
            path = resolvers[kind](city)
            joblib.dump({"city": city, "kind": kind}, path)
            state.live[(kind, city)] = path
    for city in config.LOCATIONS:
        path = str(da_dir / f"cooling_{city}.joblib")
        joblib.dump({"city": city, "kind": "cooling"}, path)
        state.cooling[city] = path
    with open(state.band, "wb") as fh:
        fh.write(b'{"stand_in": "band"}\n')

    monkeypatch.setattr(day_ahead_forecast, "serving_model_path", lambda city: state.cooling[city])
    monkeypatch.setattr(day_ahead_band, "BAND_ARTIFACT_PATH", state.band)

    def make_model_loader():
        def loader(city, method):
            state.loads.append((city, method))
            return object()
        return loader

    def load_verified_band(path=state.band, manifest_path=state.manifest):
        state.band_loads.append((path, manifest_path))
        return {}, "stand-in"

    monkeypatch.setattr(day_ahead_forecast, "make_model_loader", make_model_loader)
    monkeypatch.setattr(day_ahead_band, "load_verified_band", load_verified_band)
    monkeypatch.setattr(preflight, "MANIFEST_PATH", state.manifest)
    state.write_manifest()
    return state


def _run(capsys):
    code = preflight.main([])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _warning_lines(out):
    return [line for line in out.splitlines() if line.startswith("::warning")]


def _live_ok(world_):
    return f"OK: all 8 live model artifacts present and match {world_.manifest}"


def test_all_ok_prints_both_ok_lines(world, capsys):
    code, out, err = _run(capsys)

    assert code == 0
    assert err == ""
    lines = out.splitlines()
    assert lines == [
        _live_ok(world),
        f"OK: all 5 day-ahead artifacts present and match {world.manifest}",
    ]
    # The strict load ran for the four cooling models and the band.
    assert sorted(world.loads) == sorted((city, _LOADED) for city in config.LOCATIONS)
    assert len(world.band_loads) == 1
    assert world.band_loads[0][0] == world.band


@pytest.mark.parametrize("target", ["cooling", "band"])
def test_warn_tamper_never_stops_the_ratings_and_never_loads(world, capsys, target):
    tampered = world.band if target == "band" else world.cooling["MIDLAND"]
    with open(tampered, "ab") as fh:
        fh.write(b"substituted")

    code, out, err = _run(capsys)

    assert code == 0  # D-13a: a day-ahead problem is a warning
    assert err == ""
    assert _live_ok(world) in out.splitlines()
    warnings = _warning_lines(out)
    assert len(warnings) == 1
    assert warnings[0].startswith(_WARNING_PREFIX)
    assert tampered in warnings[0]
    assert "hash mismatch" in warnings[0]
    summary = [line for line in out.splitlines() if line.startswith("WARNING:")]
    assert len(summary) == 1
    assert "1 day-ahead artifact problem(s)" in summary[0]
    assert "live ratings are not affected" in summary[0]
    assert "OK: all 5 day-ahead" not in out
    # Hash before load: nothing day-ahead was deserialized while a hash problem is open.
    assert world.loads == []
    assert world.band_loads == []


def test_warn_missing_entry_exits_zero(world, capsys):
    world.write_manifest(skip={world.cooling["EL_PASO"]})

    code, out, _ = _run(capsys)

    assert code == 0
    warnings = _warning_lines(out)
    assert len(warnings) == 1
    assert world.cooling["EL_PASO"] in warnings[0]
    assert "no entry" in warnings[0]
    assert world.loads == [] and world.band_loads == []


def test_missing_day_ahead_file_exits_zero(world, capsys):
    os.remove(world.cooling["AUSTIN"])

    code, out, _ = _run(capsys)

    assert code == 0
    warnings = _warning_lines(out)
    assert len(warnings) == 1
    assert "missing artifact" in warnings[0] and world.cooling["AUSTIN"] in warnings[0]


def test_live_problem_stays_fatal_with_healthy_day_ahead_files(world, capsys):
    joblib.dump({"substituted": True}, world.live[("anomaly", "EL_PASO")])

    code, out, err = _run(capsys)

    assert code == 1
    assert "ERROR: 1 live model problem(s)" in err
    assert "hash mismatch" in err
    assert "OK: all 8 live model artifacts" not in out
    assert _warning_lines(out) == []
    assert f"OK: all 5 day-ahead artifacts present and match {world.manifest}" in out


def test_warning_text_is_escaped_onto_one_line(world, monkeypatch, capsys):
    monkeypatch.setattr(preflight, "check_day_ahead", lambda *a, **k: ["bad\nline\rwith 100% sure\r\n::stop-commands::x"])

    code, out, _ = _run(capsys)

    assert code == 0
    warnings = _warning_lines(out)
    assert warnings == [_WARNING_PREFIX + "bad%0Aline%0Dwith 100%25 sure%0D%0A::stop-commands::x"]
    # The raw pieces never start a line of their own, so no text of ours can read as a workflow command.
    assert not any(line.startswith("line") or line.startswith("::stop-commands") for line in out.splitlines())


def test_escape_helper_matches_github_rules():
    assert preflight._escape_workflow_data("a%b\rc\nd") == "a%25b%0Dc%0Ad"


def _break_import(monkeypatch, world_):
    monkeypatch.setitem(sys.modules, "day_ahead_forecast", None)


def _break_required(monkeypatch, world_):
    def boom():
        raise RuntimeError("no list")
    monkeypatch.setattr(preflight, "required_day_ahead_artifacts", boom)


def _break_serving_path(monkeypatch, world_):
    def boom(city):
        raise KeyError(city)
    monkeypatch.setattr(day_ahead_forecast, "serving_model_path", boom)


def _break_loader_factory(monkeypatch, world_):
    def boom():
        raise RuntimeError("no loader")
    monkeypatch.setattr(day_ahead_forecast, "make_model_loader", boom)


def _break_band_load(monkeypatch, world_):
    def boom(*args, **kwargs):
        raise ValueError("band refused")
    monkeypatch.setattr(day_ahead_band, "load_verified_band", boom)


def _break_with_exit(monkeypatch, world_):
    def boom(*args, **kwargs):
        sys.exit(3)
    monkeypatch.setattr(preflight, "check_day_ahead", boom)


_CRASHES = [
    # A None entry in sys.modules raises ModuleNotFoundError (an ImportError subclass); the warning names the real type.
    pytest.param(_break_import, "ModuleNotFoundError", id="import"),
    pytest.param(_break_required, "RuntimeError", id="required_list"),
    pytest.param(_break_serving_path, "KeyError", id="serving_path"),
    pytest.param(_break_loader_factory, "RuntimeError", id="loader_factory"),
    pytest.param(_break_band_load, "ValueError", id="band_load"),
    pytest.param(_break_with_exit, "SystemExit", id="sys_exit"),
]


@pytest.mark.parametrize("breaker,type_name", _CRASHES)
def test_tier_crash_cannot_change_the_exit_code(world, monkeypatch, capsys, breaker, type_name):
    breaker(monkeypatch, world)

    code, out, err = _run(capsys)

    assert code == 0
    assert err == ""
    assert _live_ok(world) in out.splitlines()
    warnings = _warning_lines(out)
    assert len(warnings) == 1
    assert warnings[0].startswith(_WARNING_PREFIX)
    assert type_name in warnings[0]
    summary = [line for line in out.splitlines() if line.startswith("WARNING:")]
    assert len(summary) == 1 and "live ratings are not affected" in summary[0]


@pytest.mark.parametrize("breaker,type_name", _CRASHES)
def test_tier_crash_with_a_live_problem_still_exits_one(world, monkeypatch, capsys, breaker, type_name):
    joblib.dump({"substituted": True}, world.live[("forecast", "AUSTIN")])
    breaker(monkeypatch, world)

    code, out, err = _run(capsys)

    assert code == 1
    assert "ERROR: 1 live model problem(s)" in err
    assert "hash mismatch" in err
    assert len(_warning_lines(out)) == 1 and type_name in _warning_lines(out)[0]


def test_keyboard_interrupt_still_stops_the_job(world, monkeypatch):
    def boom(*args, **kwargs):
        raise KeyboardInterrupt
    monkeypatch.setattr(preflight, "check_day_ahead", boom)

    with pytest.raises(KeyboardInterrupt):
        preflight.main([])


def test_a_failing_cooling_load_is_a_warning_per_file(world, monkeypatch, capsys):
    def make_model_loader():
        def loader(city, method):
            raise RuntimeError(f"cannot load {city}")
        return loader
    monkeypatch.setattr(day_ahead_forecast, "make_model_loader", make_model_loader)

    code, out, _ = _run(capsys)

    assert code == 0
    warnings = _warning_lines(out)
    assert len(warnings) == len(config.LOCATIONS)
    assert all("load failed" in line and "RuntimeError" in line for line in warnings)


def test_empty_day_ahead_list_prints_nothing_for_the_tier(world, monkeypatch, capsys):
    monkeypatch.setattr(preflight, "required_day_ahead_artifacts", lambda: [])

    code, out, err = _run(capsys)

    assert code == 0 and err == ""
    assert out.splitlines() == [_live_ok(world)]


def test_required_day_ahead_artifacts_names_four_cooling_files_and_the_band(world):
    artifacts = preflight.required_day_ahead_artifacts()

    assert artifacts == [
        *[("day_ahead_cooling", city, world.cooling[city]) for city in config.LOCATIONS],
        ("day_ahead_band", "", world.band),
    ]
    assert tuple(kind for kind, _, _ in artifacts[:1] + artifacts[-1:]) == preflight.DAY_AHEAD_KINDS


def test_writer_writes_thirteen_sorted_entries_and_refuses_a_missing_day_ahead_file(world, tmp_path, capsys):
    written = tmp_path / "written.sha256"

    assert preflight.write_manifest(str(written)) == []

    lines = [ln for ln in written.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    assert len(lines) == 13
    paths = [ln.split("  ", 1)[1] for ln in lines]
    assert paths == sorted(paths)
    expected = {*world.live.values(), *world.cooling.values(), world.band}
    assert set(paths) == expected
    assert all(ln.split("  ", 1)[0] == _sha(ln.split("  ", 1)[1]) for ln in lines)
    assert preflight.check_day_ahead(str(written), load=False) == []

    os.remove(world.cooling["CORPUS_CHRISTI"])
    refused = tmp_path / "refused.sha256"
    problems = preflight.write_manifest(str(refused))
    assert len(problems) == 1 and world.cooling["CORPUS_CHRISTI"] in problems[0]
    assert not refused.exists()

    # main --write-manifest targets the (monkeypatched) MANIFEST_PATH and refuses the same way
    assert preflight.main(["--write-manifest"]) == 1
    assert world.cooling["CORPUS_CHRISTI"] in capsys.readouterr().err


def test_main_reports_the_written_entry_count(world, tmp_path, monkeypatch, capsys):
    target = tmp_path / "counted.sha256"
    monkeypatch.setattr(preflight, "MANIFEST_PATH", str(target))

    assert preflight.main(["--write-manifest"]) == 0

    assert f"Wrote 13 entries to {target}" in capsys.readouterr().out


@pytest.mark.parametrize("order", ["dlr_live_check_models, forecast_conductor_refit",
                                   "forecast_conductor_refit, dlr_live_check_models"])
def test_import_order_has_no_circular_import(order, tmp_path):
    env = dict(os.environ, PYTHONPATH=os.path.join(REPO, "backend"))
    result = subprocess.run(
        [sys.executable, "-c", f"import {order}"],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr


# --------------------------------------------------------------------------------------------------
# The committed tree (no stand-ins, nothing deserialized). D-13a: a day-ahead mismatch fails here,
# offline, before any push, instead of becoming a warning on the live runner.
# --------------------------------------------------------------------------------------------------

# The last commit that changed the live manifest before Phase 8 plan 05 added the day-ahead entries:
# it holds exactly the eight live-model lines, which must survive unchanged.
PRE_08_05_MANIFEST_COMMIT = "e0a00a9e37f694f03571d1e78a9c99f8ffe6cf6b"
_REFIT_MANIFEST = os.path.join(
    "data", "models", "conductor_refit", day_ahead_forecast.DAY_AHEAD_REFIT_VERSION, "ARTIFACT_HASHES.sha256"
)
_FROZEN_MANIFEST = os.path.join("data", "shadow", "models", "ARTIFACT_HASHES.sha256")


@pytest.fixture
def repo_root(monkeypatch):
    monkeypatch.chdir(REPO)
    return REPO


def test_committed_day_ahead_files_match_the_committed_manifest(repo_root):
    assert preflight.check_day_ahead(preflight.MANIFEST_PATH, load=False) == []
    kinds = [kind for kind, _, _ in preflight.required_day_ahead_artifacts()]
    assert kinds == ["day_ahead_cooling"] * len(config.LOCATIONS) + ["day_ahead_band"]


def test_cooling_hashes_equal_the_refit_and_frozen_manifests(repo_root):
    live = preflight.read_manifest(preflight.MANIFEST_PATH)
    refit = preflight.read_manifest(_REFIT_MANIFEST)
    frozen = preflight.read_manifest(_FROZEN_MANIFEST)
    served = {city: preflight._key(path) for kind, city, path in preflight.required_day_ahead_artifacts()
              if kind == "day_ahead_cooling"}

    assert served["AUSTIN"] == (
        "data/models/conductor_refit/v3-powersystems-2026-11-02/ml_cooling_corrected_AUSTIN.joblib"
    )
    assert live[served["AUSTIN"]] == refit[served["AUSTIN"]]
    for city in ("CORPUS_CHRISTI", "MIDLAND", "EL_PASO"):
        assert served[city] == f"data/shadow/models/ml_cooling_corrected_{city}.joblib"
        assert live[served[city]] == frozen[served[city]]


def test_the_eight_live_entries_are_unchanged(repo_root):
    try:
        shown = subprocess.run(
            ["git", "show", f"{PRE_08_05_MANIFEST_COMMIT}:data/models/LIVE_ARTIFACT_HASHES.sha256"],
            capture_output=True, text=True, check=True, cwd=repo_root,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        pytest.skip(f"git history for {PRE_08_05_MANIFEST_COMMIT} is not available here: {type(exc).__name__}")
    before = {}
    for line in shown.splitlines():
        if line.strip() and not line.startswith("#"):
            digest, path = line.split("  ", 1)
            before[path] = digest
    assert len(before) == 8

    now = preflight.read_manifest(preflight.MANIFEST_PATH)

    assert {path: now.get(path) for path in before} == before
    assert len(now) == 13
    live_paths = {preflight._key(path) for _, _, path in preflight.required_artifacts()}
    assert set(before) == live_paths


def test_band_default_arguments_load_the_committed_band(repo_root):
    artifact, digest = day_ahead_band.load_verified_band()

    assert sum(len(by_hour) for by_hour in artifact["bands"].values()) == 16
    assert digest == preflight.read_manifest(preflight.MANIFEST_PATH)["data/day_ahead/day_ahead_bands_v1.json"]


def test_full_preflight_in_a_fresh_process_prints_both_ok_lines_and_no_warning(repo_root):
    env = dict(os.environ, PYTHONPATH=os.path.join(repo_root, "backend"))
    result = subprocess.run(
        [sys.executable, os.path.join("backend", "dlr_live_check_models.py")],
        cwd=repo_root, env=env, capture_output=True, text=True, timeout=300,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "::warning" not in result.stdout + result.stderr
    assert "OK: all 8 live model artifacts present and match" in result.stdout
    assert "OK: all 5 day-ahead artifacts present and match" in result.stdout
