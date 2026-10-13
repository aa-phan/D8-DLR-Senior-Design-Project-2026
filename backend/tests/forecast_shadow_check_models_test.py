import config
import forecast_shadow_check_models as chk
import forecast_shadow_pipeline as shadow


def test_reports_every_city_method_pair_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(tmp_path))
    assert len(chk.missing_artifacts()) == len(config.LOCATIONS) * 3
    assert chk.main() == 1
    err = capsys.readouterr().err
    for city in config.LOCATIONS:
        assert f"ml_wind_corrected_{city}.joblib" in err


def test_passes_when_all_present_and_flags_a_single_gap(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(tmp_path))
    for city in config.LOCATIONS:
        for m in chk.ARTIFACT_METHOD_NAMES:
            (tmp_path / f"{m}_{city}.joblib").write_bytes(b"x")
    assert chk.main() == 0
    (tmp_path / f"reference_ml_refit_24h_{config.LOCATIONS[0] if not isinstance(config.LOCATIONS, dict) else next(iter(config.LOCATIONS))}.joblib").unlink()
    assert len(chk.missing_artifacts()) == 1


def test_legacy_corridor_files_do_not_satisfy_the_check(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(tmp_path))
    (tmp_path / "ml_wind_corrected_AUSTIN_CORPUS_CHRISTI.joblib").write_bytes(b"x")
    assert len(chk.missing_artifacts()) == len(config.LOCATIONS) * 3
