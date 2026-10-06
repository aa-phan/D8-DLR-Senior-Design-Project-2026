from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

import forecast_shadow_healthcheck as healthcheck


@pytest.fixture
def predictions_dir(tmp_path, monkeypatch):
    d = tmp_path / "predictions"
    d.mkdir()
    monkeypatch.setattr(healthcheck, "PREDICTIONS_DIR", str(d))
    return d


def _write_entry(path, logged_at: datetime, fallback_used: bool):
    with open(path, "a") as fh:
        fh.write(json.dumps({"logged_at": logged_at.isoformat(), "fallback_used": fallback_used}) + "\n")


def test_check_reports_unhealthy_for_missing_log(predictions_dir):
    assert healthcheck.check(max_age_minutes=1440) == 1


def test_check_reports_healthy_for_recent_entry(predictions_dir):
    now = datetime.now(timezone.utc)
    for corridor in ("AUSTIN_CORPUS_CHRISTI", "MIDLAND_EL_PASO"):
        _write_entry(os.path.join(predictions_dir, f"{corridor}.jsonl"), now, fallback_used=False)
    assert healthcheck.check(max_age_minutes=1440) == 0


def test_check_reports_unhealthy_for_stale_entry(predictions_dir):
    stale = datetime.now(timezone.utc) - timedelta(days=3)
    for corridor in ("AUSTIN_CORPUS_CHRISTI", "MIDLAND_EL_PASO"):
        _write_entry(os.path.join(predictions_dir, f"{corridor}.jsonl"), stale, fallback_used=False)
    assert healthcheck.check(max_age_minutes=1440) == 1


def test_check_treats_a_recent_fallback_entry_as_healthy(predictions_dir):
    """An all-fallback run means the collector IS running -- a station
    gap is not a scheduler failure, per this script's own docstring."""
    now = datetime.now(timezone.utc)
    for corridor in ("AUSTIN_CORPUS_CHRISTI", "MIDLAND_EL_PASO"):
        _write_entry(os.path.join(predictions_dir, f"{corridor}.jsonl"), now, fallback_used=True)
    assert healthcheck.check(max_age_minutes=1440) == 0
