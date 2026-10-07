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
    path = os.path.join(predictions_dir, "AUSTIN_CORPUS_CHRISTI.jsonl")
    stale = datetime.now(timezone.utc) - timedelta(days=5)
    fresh = datetime.now(timezone.utc)
    _write_entry(path, stale, fallback_used=False)
    _write_entry(path, fresh, fallback_used=False)
    # MIDLAND_EL_PASO still needs an entry for `check` to consider it
    # healthy too, so the overall exit code isolates AUSTIN_CORPUS_CHRISTI's
    # own behavior.
    _write_entry(os.path.join(predictions_dir, "MIDLAND_EL_PASO.jsonl"), fresh, fallback_used=False)
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
        path = os.path.join(d, "AUSTIN_CORPUS_CHRISTI.jsonl")
        newer_but_not_last = datetime.now(timezone.utc)
        stale_but_appended_last = datetime.now(timezone.utc) - timedelta(days=5)
        _write_entry(path, newer_but_not_last, fallback_used=False)
        _write_entry(path, stale_but_appended_last, fallback_used=False)
        _write_entry(os.path.join(d, "MIDLAND_EL_PASO.jsonl"), newer_but_not_last, fallback_used=False)
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
    for corridor in ("AUSTIN_CORPUS_CHRISTI", "MIDLAND_EL_PASO"):
        _write_entry(os.path.join(predictions_dir, f"{corridor}.jsonl"), exactly_at_threshold, fallback_used=False)
    assert healthcheck.check(max_age_minutes=1440) == 0
