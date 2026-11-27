"""
Shared helper for the pandapower study-engine tests (pandapower-solver Phase 2, plan 02-02).
Not collected by pytest (the file name does not match `*_test.py`, and nothing here has a `test_`
prefix, so a test module that imports a name would not collect it).

Everything is generated from `pandapower_fixture.case39_records(OFFSET)` into a test's tmp_path
only, never into the repository (D-08): the public repository must never hold RAW structure, so
this file holds no section text; the RAW bytes come from `pandapower_fixture.raw_text`.

The 39-bus case carries machine active-power limits that the scaling of the engine would hit; the
fixture raises every machine limit to `RAISED_PT_MW` so a study on it is not clamped (RESEARCH
Pitfall 5).
"""

import datetime
import json
import os

import pandapower_fixture
import psse_fakes
from psse_job import constants, ratings, settings
from pandapower_job import api, convert, raw, scaling, solve

OFFSET = pandapower_fixture.OFFSET
RAISED_PT_MW = 5000.0
NOW = datetime.datetime(2026, 10, 28, 12, 20, tzinfo=datetime.timezone.utc)

# city -> (from_bus, to_bus, ckt, sink_bus) on the fixture. Every sink carries load (buses 2 and 6
# of the 39-bus case carry none), so the margin's own loaded-sink check holds.
PLACEHOLDER_LINES = {
    "AUSTIN": (OFFSET + 2, OFFSET + 3, "1", OFFSET + 3),
    "CORPUS_CHRISTI": (OFFSET + 3, OFFSET + 4, "1", OFFSET + 4),
    "MIDLAND": (OFFSET + 6, OFFSET + 7, "1", OFFSET + 7),
    "EL_PASO": (OFFSET + 7, OFFSET + 8, "1", OFFSET + 8),
}
# Each city's target is this share of the fixture's own load and generation total, in
# constants.CITIES order, so the four targets differ and none is a Power Systems figure.
TARGET_FACTORS = dict(zip(constants.CITIES, (0.90, 0.92, 0.94, 0.96)))

# This outage isolates four buses of the fixture: pandapower then reports converged and leaves
# their voltages NaN, which the adapter must turn into a non-converged result with ierr 3.
ISLANDING_OUTAGE = settings.BranchRef(OFFSET + 16, OFFSET + 19, "1")


def fixture_records(raise_pt=True):
    """The 39-bus records at OFFSET, every machine's PT raised to RAISED_PT_MW when asked."""
    records = pandapower_fixture.case39_records(OFFSET)
    if raise_pt:
        for machine in records["generator"]:
            machine["PT"] = RAISED_PT_MW
    return records


def write_case(tmp_path, name="CASE39_FIXTURE.raw", raise_pt=True):
    """Write the fixture as a RAW file into `tmp_path` and return its path as a string."""
    path = os.path.join(str(tmp_path), name)
    pandapower_fixture.write_raw(path, fixture_records(raise_pt))
    return path


def write_converted(tmp_path, name="CASE39_FIXTURE.json", raise_pt=True):
    """Write the fixture as the project's converted network document into `tmp_path`.

    The bytes come from `convert.case_to_json` of the parsed fixture RAW text; this file never
    holds the document's marker key as a literal.
    """
    case = raw.parse_raw(pandapower_fixture.raw_text(fixture_records(raise_pt)).encode("utf-8"))
    path = os.path.join(str(tmp_path), name)
    with open(path, "wb") as handle:
        handle.write(convert.case_to_json(case))
    return path


def fixture_backend(enforce_q_lims=False, tolerance_mva=1e-8, max_iteration=30,
                    collapse_voltage_pu=0.5, details=("yes", "no", "yes")):
    """A PandapowerBackend with test settings (every source says so) and the given scaling details."""
    sources = {name: "test fixture" for name in
               ("enforce_q_lims", "tolerance_mva", "max_iteration", "collapse_voltage_pu")}
    return api.PandapowerBackend(
        solve.SolveSettings(enforce_q_lims, tolerance_mva, max_iteration, collapse_voltage_pu,
                            sources, ()),
        scaling.ScalingDetails(details[0], details[1], details[2], {"fixture": True}))


# -- the placeholder mapping and its targets -------------------------------------------------------


def fixture_totals(records):
    """(load_mw, gen_mw) of the records: P of every load with STATUS 1, PG of every machine
    with STAT 1 (the swing machine's PG included, as `scaling.case_totals` does with its detail)."""
    load = sum(rec["PL"] for rec in records["load"] if rec["STATUS"] == 1)
    gen = sum(rec["PG"] for rec in records["generator"] if rec["STAT"] == 1)
    return load, gen


def placeholder_targets(records):
    """city -> (load_mw, gen_mw): TARGET_FACTORS times the records' own totals, to 2 decimals."""
    load, gen = fixture_totals(records)
    return {city: (round(load * factor, 2), round(gen * factor, 2))
            for city, factor in TARGET_FACTORS.items()}


def write_placeholder_mapping(tmp_path, study=None, name="mapping.json", raise_pt=True):
    """Write the placeholder mapping (the example's schema) into `tmp_path`; return its path.

    The four cities sit on PLACEHOLDER_LINES of the public 39-bus fixture with the targets of
    `placeholder_targets`. It is written at run time and never committed (D-08).
    """
    targets = placeholder_targets(fixture_records(raise_pt))
    cities = {}
    for city in constants.CITIES:
        from_bus, to_bus, ckt, sink = PLACEHOLDER_LINES[city]
        load_mw, gen_mw = targets[city]
        cities[city] = {
            "branches": [{"from_bus": from_bus, "to_bus": to_bus, "ckt": ckt}],
            "sink_buses": [sink],
            "scaling": {"load_mw": load_mw, "gen_mw": gen_mw, "basis": "average"}}
    document = {
        "schema_version": 2,
        "placeholder": True,
        "note": "PLACEHOLDER - a synthetic test mapping on the public 39-bus fixture, not Power "
                "Systems data.",
        "cities": cities,
        "study": {} if study is None else study}
    path = os.path.join(str(tmp_path), name)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2)
    return path


def synthetic_target_texts(records):
    """Every target of `placeholder_targets` in repr, %g and %.1f form, sorted, so a leak of a
    figure into an error or a log shows."""
    texts = set()
    for load_mw, gen_mw in placeholder_targets(records).values():
        for value in (load_mw, gen_mw):
            texts.update((repr(value), "%g" % value, "%.1f" % value))
    return sorted(texts)


def selection(now=NOW):
    """The ratings selection of the PSS/E study tests: one provisional latest row per city."""
    rows = psse_fakes.latest_rows(now, provisional=True)
    return ratings.select_ratings(psse_fakes.fake_fetch(rows), now)
