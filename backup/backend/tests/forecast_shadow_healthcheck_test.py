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


_CITIES = ("AUSTIN", "CORPUS_CHRISTI", "MIDLAND", "EL_PASO")


def _write_entry(path, logged_at: datetime, fallback_used: bool, city: str | None = None):
    """`city` defaults to the log file's own stem (`{CITY}.jsonl`), as the collector writes it."""
    city = city if city is not None else os.path.splitext(os.path.basename(path))[0]
    with open(path, "a") as fh:
        fh.write(json.dumps({
            "schema_version": 3, "city": city,
            "logged_at": logged_at.isoformat(), "fallback_used": fallback_used,
        }) + "\n")


def _write_all_cities(predictions_dir, logged_at, fallback_used=False):
    for city in _CITIES:
        _write_entry(os.path.join(predictions_dir, f"{city}.jsonl"), logged_at, fallback_used=fallback_used)


def test_check_reports_unhealthy_for_missing_log(predictions_dir):
    assert healthcheck.check(max_age_minutes=1440) == 1


def test_check_reports_healthy_for_recent_entry(predictions_dir):
    now = datetime.now(timezone.utc)
    _write_all_cities(predictions_dir, now)
    assert healthcheck.check(max_age_minutes=1440) == 0


def test_check_reports_unhealthy_for_stale_entry(predictions_dir):
    stale = datetime.now(timezone.utc) - timedelta(days=3)
    _write_all_cities(predictions_dir, stale)
    assert healthcheck.check(max_age_minutes=1440) == 1


def test_check_treats_a_recent_fallback_entry_as_healthy(predictions_dir):
    """An all-fallback run means the collector IS running -- a station
    gap is not a scheduler failure, per this script's own docstring."""
    now = datetime.now(timezone.utc)
    _write_all_cities(predictions_dir, now, fallback_used=True)
    assert healthcheck.check(max_age_minutes=1440) == 0


# ──────────────────────────────────────────────────────────────────────
# Adversarial mutation-testing pass (2026-10-06): closes gaps surfaced by
# manually probing the pre-existing suite.
# ──────────────────────────────────────────────────────────────────────

def test_check_uses_the_most_recently_appended_entry_not_the_first(predictions_dir):
    """
    Survived mutant: `_last_entry` picking the FIRST non-empty line instead
    of the LAST. Every pre-existing test wrote exactly one line per
    corridor file, so "most recent" was never actually distinguished from
    "only" or "first" entry. This test appends a STALE entry first, then a
    FRESH one, and confirms the health check reports healthy based on the
    fresh (later-appended) entry -- a `_last_entry` bug that picked the
    first line would see only the stale entry and wrongly report unhealthy.
    """
    path = os.path.join(predictions_dir, "AUSTIN.jsonl")
    stale = datetime.now(timezone.utc) - timedelta(days=5)
    fresh = datetime.now(timezone.utc)
    _write_entry(path, stale, fallback_used=False)
    _write_entry(path, fresh, fallback_used=False)
    # The other cities still need an entry for `check` to consider them
    # healthy too, so the overall exit code isolates AUSTIN's own behavior.
    for city in _CITIES[1:]:
        _write_entry(os.path.join(predictions_dir, f"{city}.jsonl"), fresh, fallback_used=False)
    assert healthcheck.check(max_age_minutes=1440) == 0


def test_check_reports_unhealthy_when_the_latest_entry_is_stale_even_if_an_earlier_one_was_fresher():
    """
    Companion to the above, same root behavior from the opposite direction:
    if the MOST RECENT entry is stale (even though an earlier one in the
    same file happened to be newer -- an out-of-order append, which should
    not occur in practice but pins the "last line wins" contract precisely
    rather than "whichever line has the latest timestamp wins"), the check
    must report unhealthy based on the last-appended line.
    """
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        healthcheck.PREDICTIONS_DIR = d
        path = os.path.join(d, "AUSTIN.jsonl")
        newer_but_not_last = datetime.now(timezone.utc)
        stale_but_appended_last = datetime.now(timezone.utc) - timedelta(days=5)
        _write_entry(path, newer_but_not_last, fallback_used=False)
        _write_entry(path, stale_but_appended_last, fallback_used=False)
        for city in _CITIES[1:]:
            _write_entry(os.path.join(d, f"{city}.jsonl"), newer_but_not_last, fallback_used=False)
        assert healthcheck.check(max_age_minutes=1440) == 1


def test_check_reports_healthy_at_the_exact_age_boundary(predictions_dir, monkeypatch):
    """
    Boundary: survived mutant `age > max_age` -> `age >= max_age`, which
    would wrongly report unhealthy when age is EXACTLY equal to the
    threshold. The clock inside `check()` is pinned via monkeypatch (not
    raced against real wall-clock time) so `age` is deterministically
    exactly `max_age`, not merely close to it.
    """
    fixed_now = datetime(2026, 10, 6, 12, 0, 0, tzinfo=timezone.utc)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    monkeypatch.setattr(healthcheck, "datetime", _FixedDatetime)
    exactly_at_threshold = fixed_now - timedelta(minutes=1440)
    _write_all_cities(predictions_dir, exactly_at_threshold)
    assert healthcheck.check(max_age_minutes=1440) == 0


# ──────────────────────────────────────────────────────────────────────
# Plan 05-05, Task 1: proves (not merely argues) that `forecast_shadow_
# healthcheck.py` needs ZERO code change against a new-shape (schema_
# version: 2) row -- the six-field top-level mirror 05-01-SUMMARY.md
# approved means `_last_entry`/`check`'s existing `entry.get('logged_at')`/
# `entry.get('fallback_used')` top-level reads see exactly what they saw
# for an old-shape row.
# ──────────────────────────────────────────────────────────────────────

def test_check_reports_the_same_verdict_for_a_new_shape_schema_version_3_row(predictions_dir):
    """
    This file itself (`forecast_shadow_healthcheck.py`) carries zero diff
    from this task -- only this test is new. A new-shape entry's top-level
    mirror fields (`method`, `ampacity_amps`, `fallback_used`,
    `fallback_reason`, `model_version`, `input_provenance`) are an exact
    copy of `candidates["ml_wind_corrected"]`'s own fields, so `check`
    reports the identical healthy verdict and "corrected"/"fallback"
    status string it would report for an equivalent old-shape entry.
    """
    now = datetime.now(timezone.utc)
    new_shape_entry = {
        "schema_version": 3,
        "city": "AUSTIN",
        "decision_time": now.isoformat(), "valid_time": now.isoformat(),
        "logged_at": now.isoformat(),
        "candidates": {
            "ml_wind_corrected": {
                "status": "ok", "ampacity_amps": 700.0, "fallback_used": False,
                "fallback_reason": None, "model_version": "v2",
                "input_provenance": None, "reason": None,
            },
            "ml_cooling_corrected": {"status": "ok", "ampacity_amps": 690.0, "fallback_used": False, "fallback_reason": None, "model_version": "v2", "input_provenance": None, "reason": None},
            "raw_forecast": {"status": "ok", "ampacity_amps": 650.0, "fallback_used": False, "fallback_reason": None, "model_version": None, "input_provenance": None, "reason": None},
            "persistence_24h": {"status": "unavailable", "ampacity_amps": None, "fallback_used": False, "fallback_reason": None, "model_version": None, "input_provenance": None, "reason": "no prior entry within tolerance"},
            "reference_ml_refit_24h": {"status": "unavailable", "ampacity_amps": None, "fallback_used": False, "fallback_reason": None, "model_version": None, "input_provenance": None, "reason": "no persisted artifact"},
        },
        # The six-field legacy mirror, byte-for-byte copied from
        # candidates["ml_wind_corrected"] -- the ONLY fields `_last_entry`/
        # `check` actually read.
        "method": "ml_wind_corrected", "ampacity_amps": 700.0,
        "fallback_used": False, "fallback_reason": None,
        "model_version": "v2", "input_provenance": None,
    }
    with open(os.path.join(predictions_dir, "AUSTIN.jsonl"), "a") as fh:
        fh.write(json.dumps(new_shape_entry) + "\n")
    for city in _CITIES[1:]:
        _write_entry(os.path.join(predictions_dir, f"{city}.jsonl"), now, fallback_used=False)

    assert healthcheck.check(max_age_minutes=1440) == 0


# ──────────────────────────────────────────────────────────────────────
# 2026-10-12: per-city health. Four cities; legacy corridor logs ignored.
# ──────────────────────────────────────────────────────────────────────

def test_check_requires_every_one_of_the_four_cities(predictions_dir, capsys):
    now = datetime.now(timezone.utc)
    for city in _CITIES[:-1]:
        _write_entry(os.path.join(predictions_dir, f"{city}.jsonl"), now, fallback_used=False)
    assert healthcheck.check(max_age_minutes=1440) == 1
    out = capsys.readouterr().out
    assert "[UNHEALTHY] EL_PASO: no log entries at all" in out
    for city in _CITIES[:-1]:
        assert f"[OK] {city}:" in out


def test_check_ignores_legacy_corridor_logs_entirely(predictions_dir, capsys):
    """Fresh per-city logs + stale/garbage legacy corridor logs = healthy; the
    legacy files can neither pass nor fail the check."""
    now = datetime.now(timezone.utc)
    stale = now - timedelta(days=30)
    _write_all_cities(predictions_dir, now)
    for legacy in ("AUSTIN_CORPUS_CHRISTI", "MIDLAND_EL_PASO"):
        with open(os.path.join(predictions_dir, f"{legacy}.jsonl"), "w") as fh:
            fh.write(json.dumps({"corridor": legacy, "logged_at": stale.isoformat(), "fallback_used": False}) + "\n")
            fh.write("{garbage that is not json\n")
    assert healthcheck.check(max_age_minutes=1440) == 0
    assert "CORPUS_CHRISTI.jsonl" not in capsys.readouterr().out


def test_check_does_not_let_legacy_only_logs_stand_in_for_missing_city_logs(predictions_dir):
    now = datetime.now(timezone.utc)
    for legacy in ("AUSTIN_CORPUS_CHRISTI", "MIDLAND_EL_PASO"):
        with open(os.path.join(predictions_dir, f"{legacy}.jsonl"), "w") as fh:
            fh.write(json.dumps({"corridor": legacy, "logged_at": now.isoformat()}) + "\n")
    assert healthcheck.check(max_age_minutes=1440) == 1


def test_check_skips_a_malformed_or_legacy_trailing_line_in_a_city_log(predictions_dir):
    """One bad trailing line must not crash the check or hide the real last entry."""
    now = datetime.now(timezone.utc)
    _write_all_cities(predictions_dir, now)
    with open(os.path.join(predictions_dir, "AUSTIN.jsonl"), "a") as fh:
        fh.write("{truncated\n")
        fh.write(json.dumps({"corridor": "AUSTIN_CORPUS_CHRISTI", "logged_at": "2000-01-01T00:00:00+00:00"}) + "\n")
        fh.write(json.dumps([1, 2]) + "\n")
    assert healthcheck.check(max_age_minutes=1440) == 0
