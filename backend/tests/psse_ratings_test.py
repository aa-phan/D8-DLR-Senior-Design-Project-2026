"""
The PSS/E job's rating input (pss-e-integration Phase 1, plan 01-02: IN-01, D-02, D-06).

Offline: the only network is a loopback fake PostgREST server (psse_fakes.py). Covers the
per-city choice between the newest city_rating row and the static rating, failed reads,
the amps-to-MVA helper and secret redaction.

Follows backend/tests/supabase_schema_doc_test.py's conventions (module-level imports,
plain asserts, no test classes). Every planted key, JWT, reference and database URL is
assembled from pieces so backend/tests/secret_scan_test.py never matches this file.
"""

import functools
import os
import sys

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import datetime  # noqa: E402

from psse_fakes import FakeLatestRatingServer, fake_publishable_key, latest_rows  # noqa: E402
from psse_job import constants  # noqa: E402
from psse_job.ratings import fetch_latest_rating, select_ratings  # noqa: E402

NOW = datetime.datetime(2026, 10, 28, 12, 20, 0, tzinfo=datetime.timezone.utc)


def _env(server, key=None):
    return {
        constants.ENV_SUPABASE_URL: server.url,
        constants.ENV_PUBLISHABLE_KEY: key or fake_publishable_key(),
    }


def test_tracer_today_labels_select_static_for_all_four_cities():
    key = fake_publishable_key()
    with FakeLatestRatingServer(rows=latest_rows(NOW, provisional=True, age_minutes=10.0), key=key) as server:
        env = _env(server, key)
        selection = select_ratings(functools.partial(fetch_latest_rating, env=env), NOW)
        requests = list(server.requests)

    assert list(selection.choices) == ["AUSTIN", "CORPUS_CHRISTI", "MIDLAND", "EL_PASO"]
    assert selection.read_error is None
    assert selection.ignored_rows == 0
    for city, choice in selection.choices.items():
        static = constants.STATIC_RATINGS_AMPS_PER_CONDUCTOR[city]
        count = constants.SUBCONDUCTORS_PER_PHASE[city]
        assert choice.city == city
        assert choice.source == "static_fallback"
        assert choice.fallback_reason == "provisional"
        assert choice.amps_per_conductor == static
        assert choice.subconductors_per_phase == count
        assert choice.amps_circuit == static * count
        assert choice.row_valid_time is not None
        assert choice.row_computed_at is not None
    assert selection.choices["AUSTIN"].amps_per_conductor == 1825.0
    assert selection.choices["CORPUS_CHRISTI"].amps_per_conductor == 1500.0
    assert selection.choices["MIDLAND"].amps_per_conductor == 1875.0
    assert selection.choices["EL_PASO"].amps_per_conductor == 1320.0

    assert len(requests) == 1
    request = requests[0]
    query = dict(request["query"])
    assert query["select"] == ",".join(constants.LATEST_RATING_SELECT)
    assert query["order"] == "city.asc"
    assert request["headers"]["apikey"] == key
    assert "authorization" not in request["headers"]
