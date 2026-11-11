"""
Tests for Phase 4's per-city scaling of the study (pss-e-integration Phase 4, plan 04-03: SCL-02
to SCL-05) at the study level against the fake psspy: every city is studied on its own freshly
loaded copy of the case, scaled to that city's targets with the job's own whole-case scal_2 call
before its rating is written and its load flow solved.

Follows backend/tests/psse_study_test.py's conventions (module-level imports, plain asserts, no
test classes, no network). Honest scope: the fake proves call order, isolation between copies and
failure handling, not how real PSS/E reads the scaling arguments or whether reloading undoes a
scaling; plan 04-06 checks that on the laptop.

Only synthetic targets appear here (plan 04-01's table, the same ones as the committed example
mapping); no real city figure belongs in a public repository.
"""

import datetime
import os
import sys
import tempfile

import pytest

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import psse_fake_psspy as fake_module  # noqa: E402
import psse_fakes  # noqa: E402
from psse_job import (  # noqa: E402
    constants, mapping, ratings, run_record, study,
)

EXAMPLE = os.path.join(_ROOT, "docs", "data-science", "schema", "psse_mapping_example.json")
NOW = datetime.datetime(2026, 10, 28, 12, 20, 0, tzinfo=datetime.timezone.utc)

# city -> (load_mw, gen_mw), basis "average": plan 04-01's synthetic table.
TARGETS = {
    "AUSTIN": (2430.5, 2467.25),
    "CORPUS_CHRISTI": (2455.75, 2492.5),
    "MIDLAND": (2504.25, 2541.75),
    "EL_PASO": (2529.5, 2566.25),
}
MAPPED_LINE = {
    "AUSTIN": (90001, 90002, "1"),
    "CORPUS_CHRISTI": (90011, 90012, "1"),
    "MIDLAND": (90021, 90022, "1"),
    "EL_PASO": (90031, 90032, "1"),
}


@pytest.fixture(autouse=True)
def _private_temp(tmp_path, monkeypatch):
    """Every temporary directory of a test lives under tmp_path/scratch, so a leak shows."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    return scratch


def _registered(tmp_path, case=None, solver=None, fake=None):
    """(fake, case path): the case registered under a path whose file holds a marker."""
    fake = fake_module.FakePsspy(solver=solver) if fake is None else fake
    path = str(tmp_path / "PLACEHOLDER_CASE.sav")
    with open(path, "wb") as handle:
        handle.write(b"MARKER - Power Systems' case")
    fake.fake_register_case(path, fake_module.placeholder_case() if case is None else case)
    return fake, path


def _mapping(cities=None, **changes):
    """The example mapping (placeholder allowed); `cities` maps a city to CityMapping field
    replacements and `changes` replace study settings."""
    loaded = mapping.load_mapping(EXAMPLE, allow_placeholder=True)
    table = dict(loaded.cities)
    for city, fields in (cities or {}).items():
        table[city] = table[city]._replace(**fields)
    return loaded._replace(cities=table, settings=loaded.settings._replace(**changes))


def _selection(provisional=True):
    rows = psse_fakes.latest_rows(NOW, provisional=provisional)
    return ratings.select_ratings(psse_fakes.fake_fetch(rows), NOW)


def _same_file(left, right):
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))


def _case_loads(fake, path):
    """The recorded case() calls that load Power Systems' case file itself."""
    return [call for call in fake.fake_calls if call[0] == "case" and _same_file(call[1][0], path)]


def _city_blocks(fake, path):
    """The recorded calls after the indexing load, one list per city: each starts at a load of
    Power Systems' case file and runs to the next one (or the end)."""
    positions = [position for position, call in enumerate(fake.fake_calls)
                 if call[0] == "case" and _same_file(call[1][0], path)]
    ends = positions[1:] + [len(fake.fake_calls)]
    return [fake.fake_calls[start:end] for start, end in list(zip(positions, ends))[1:]]


def _expected_outage_counts(path, mapping_=None):
    """city -> how many in-service branch outages that city's own study area selects, worked
    out from the index and the study area alone (no screen is run)."""
    mapping_ = _mapping() if mapping_ is None else mapping_
    reference = fake_module.FakePsspy()
    reference.fake_register_case(path, fake_module.placeholder_case())
    index = study.index_case(reference, path, mapping_)
    in_service = set(row.key for row in index.lines if row.in_service)
    assert not mapping_.settings.contingency_extra
    counts = {}
    for city in constants.CITIES:
        area = study.study_area(
            index.lines, index.buses, {city: index.resolved[city]}, mapping_.settings,
            {city: mapping_.cities[city].sink_buses})
        counts[city] = len(area.branch_keys & in_service)
    return counts


def test_tracer_four_cities_each_on_its_own_scaled_copy(tmp_path):
    fake, path = _registered(tmp_path)
    sha_before = run_record.file_sha256(path)
    selection = _selection()
    prepared = study.prepare_run(fake, path, EXAMPLE, allow_placeholder=True)
    results = prepared.study(selection, None)

    run_record.validate_results(results, selection)
    assert [row["city"] for row in results.dispatch] == list(constants.CITIES)
    assert [row["city"] for row in results.margins] == list(constants.CITIES)
    prefixes = tuple(city + ":" for city in constants.CITIES)
    assert results.contingencies
    assert all(row["contingency_id"].startswith(prefixes) for row in results.contingencies)
    assert os.listdir(tempfile.gettempdir()) == []

    reference = fake_module.FakePsspy()
    reference.fake_register_case(path, fake_module.placeholder_case())
    index = study.index_case(reference, path, _mapping())
    case_keys = set(row.key for row in index.lines)
    for row in results.contingencies:
        city, _, key = row["contingency_id"].partition(":")
        assert city in constants.CITIES
        assert key in case_keys
    counts = _expected_outage_counts(path)
    assert results.n_contingencies == sum(counts.values())

    # four fresh loads after the one indexing load, each city's block in the planned order
    assert len(_case_loads(fake, path)) == 5
    blocks = _city_blocks(fake, path)
    assert len(blocks) == len(constants.CITIES)
    for city, block in zip(constants.CITIES, blocks):
        assert block[0][0] == "case" and _same_file(block[0][1][0], path)
        upto_save = []
        for call in block:
            upto_save.append(call)
            if call[0] == "save":
                break
        assert upto_save[-1][0] == "save"
        writes = [call for call in upto_save if call[0] in ("scal_2", "branch_chng_3", "fnsl", "save")]
        names = [call[0] for call in writes]
        assert names[:3] == ["scal_2", "scal_2", "scal_2"], city
        assert names[-2:] == ["fnsl", "save"], city
        middle = names[3:-2]
        assert middle and set(middle) == {"branch_chng_3"}, city
        assert [call[2]["apiopt"] for call in writes[:3]] == [1, 0, 1], city
        assert all(call[2]["all"] == 1 for call in writes[:3]), city
        scale = writes[1][2]
        assert scale["scalval"][:2] == list(TARGETS[city]), city
        line = MAPPED_LINE[city]
        for call in writes[3:-2]:
            assert (call[2]["ibus"], call[2]["jbus"], call[2]["ckt"]) == line, city
        saved = writes[-1][1][0]
        assert os.path.basename(saved) == city + ".sav"
    directories = set(os.path.dirname(os.path.abspath(saved)) for saved in fake.fake_saved_paths
                      if os.path.basename(saved) in [city + ".sav" for city in constants.CITIES])
    assert len(directories) == 1
    assert not any(os.path.exists(saved) for saved in fake.fake_saved_paths)
    assert run_record.file_sha256(path) == sha_before

    expected = {"basis": "average", "method": study.SCALING_METHOD}
    for row in results.dispatch + results.margins:
        assert row["details"]["scaling"] == expected
