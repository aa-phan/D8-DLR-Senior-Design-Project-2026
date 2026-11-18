"""
Study-level behaviour tests of the pandapower adapter (pandapower-solver Phase 2, plan 02-05:
ENG-03, ENG-04).

Plan 02-02 proved the adapter's rules for the adapter alone. These tests prove them through the
study's own loops, with the `psse_job` code unchanged: an outage that islands part of the grid
becomes one non_convergence row through `contingency.screen`, the order of the outages and a prior
failure change no other row, no reading follows a failed solve, and every city, outage and margin
step solves a freshly loaded copy.

Every input is a synthetic RAW file generated at test time from pandapower's own 39-bus case with
the bus numbers offset by 90000 (`pandapower_study_fixture`), written into tmp_path only. The ratings
come from `psse_fakes` rows, so no live data is read. The solver is the real pandapower.
"""

import json
import tempfile

import pandas
import pytest

pandapower = pytest.importorskip("pandapower")

import pandapower_study_fixture as study_fixture  # noqa: E402
from psse_job import constants, contingency, mapping as mapping_module, psse_api, study  # noqa: E402
from pandapower_job import api as pandapower_api, network, raw  # noqa: E402

ISLAND = study_fixture.ISLANDING_OUTAGE


@pytest.fixture(autouse=True)
def _private_temp(tmp_path, monkeypatch):
    """Every temporary directory of a test lives under tmp_path/scratch, so a leak shows."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    return scratch


def _extra(ref):
    return {"from_bus": ref.from_bus, "to_bus": ref.to_bus, "ckt": ref.ckt}


def _island_mapping(tmp_path):
    """The placeholder mapping with the islanding outage as `contingency.extra`, loaded."""
    path = study_fixture.write_placeholder_mapping(
        tmp_path, study={"contingency": {"extra": [_extra(ISLAND)]}})
    return mapping_module.load_mapping(path, allow_placeholder=True)


def _row_key(row):
    """A stable sort key for a result row (JSON text with sorted keys)."""
    return json.dumps(row, sort_keys=True, default=str)


def test_tracer_island_is_one_non_convergence_row(tmp_path):
    case_path = study_fixture.write_case(tmp_path)
    loaded = _island_mapping(tmp_path)
    base = study.prepare_base(study_fixture.fixture_backend(), case_path, loaded,
                              study_fixture.selection(), solver="pandapower")
    try:
        screened = contingency.screen(base, id_prefix="ALL:")
    finally:
        study.cleanup_base(base)

    assert ISLAND in screened.outages
    assert screened.n_contingencies == len(screened.outages)
    island_rows = [row for row in screened.rows if row["contingency_id"] == "ALL:" + ISLAND.key]
    assert len(island_rows) == 1
    row = island_rows[0]
    assert row["violation_kind"] == "non_convergence"
    details = row["details"]
    assert details["ierr"] == 3
    assert details["solved"] is None
    assert details["collapsed"] is False
    assert details["meaning"].startswith("fnsl ierr 3: buses in island without swing bus")
    # The screen did not stop at the island: another outage was screened (it has rows, or it
    # converged clean and has none), so more than one outage was selected and every one counted.
    assert len(screened.outages) > 1
    other_outages = [outage for outage in screened.outages if outage != ISLAND]
    assert other_outages

    # pandapower itself calls the very same solve converged: the row comes from the adapter's
    # explicit rule, not from pandapower's flag.
    api = pandapower_api.PandapowerApi(study_fixture.fixture_backend(), protected_path=case_path)
    api.load_case(case_path)
    assert api.solve().converged
    snapshot = str(tmp_path / "scratch" / "tracer.snapshot")
    api.save_case(snapshot)
    api.load_case(snapshot)
    api.set_status(ISLAND, False)
    result = api.solve()
    assert not result.converged
    assert result.ierr == 3
    assert api._net.converged is True


# -- a recording adapter ---------------------------------------------------------------------------


class _RecordingApi(pandapower_api.PandapowerApi):
    """The adapter, logging every public call as (name, first argument, extra) before it returns the
    parent's result. `extra` is `converged` for a solve and `in_service` for set_status. The net
    each solve ran on is kept (`solved_nets`) so identity, not an id that could be reused, is compared.
    """

    def __init__(self, backend, protected_path=None):
        super().__init__(backend, protected_path)
        self.log = []
        self.solved_nets = []

    def _record(self, name, first=None, extra=None):
        self.log.append((name, first, extra))

    def load_case(self, path):
        self._record("load_case", path)
        return super().load_case(path)

    def save_case(self, path):
        self._record("save_case", path)
        return super().save_case(path)

    def branch_table(self):
        self._record("branch_table")
        return super().branch_table()

    def read_rate(self, ref, rate_set):
        self._record("read_rate", ref)
        return super().read_rate(ref, rate_set)

    def set_rate(self, ref, rate_set, mva):
        self._record("set_rate", ref)
        return super().set_rate(ref, rate_set, mva)

    def set_status(self, ref, in_service):
        self._record("set_status", ref, in_service)
        return super().set_status(ref, in_service)

    def solve(self, options=None):
        net = self._net
        result = super().solve(options)
        self.log.append(("solve", options, result.converged))
        self.solved_nets.append(net)
        return result

    def bus_table(self):
        self._record("bus_table")
        return super().bus_table()

    def branch_loading(self, rate_set, basis):
        self._record("branch_loading", rate_set)
        return super().branch_loading(rate_set, basis)

    def read_totals(self):
        self._record("read_totals")
        return super().read_totals()

    def scale_case(self, load_mw, gen_mw):
        self._record("scale_case", load_mw)
        return super().scale_case(load_mw, gen_mw)

    def define_subsystem(self, sid, buses):
        self._record("define_subsystem", sid)
        return super().define_subsystem(sid, buses)

    def scale_load(self, sid, increment_mw):
        self._record("scale_load", sid)
        return super().scale_load(sid, increment_mw)

    def version(self):
        self._record("version")
        return super().version()


def test_recording_api_wraps_every_public_method():
    parent = pandapower_api.PandapowerApi
    public = set(name for name in dir(parent)
                 if not name.startswith("_") and callable(getattr(parent, name)))
    assert len(public) == 14
    assert public <= set(vars(_RecordingApi))


@pytest.fixture(scope="module")
def recorded_study(tmp_path_factory):
    """One full four-city study (about 36 s) on the fixture through the recording adapter."""
    root = tmp_path_factory.mktemp("behaviour_run")
    case_path = study_fixture.write_case(root)
    loaded = _island_mapping(root)
    selection = study_fixture.selection()
    scratch = root / "scratch"
    scratch.mkdir()
    instances = []

    def factory(backend, path):
        instance = _RecordingApi(backend, protected_path=path)
        instances.append(instance)
        return instance

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("tempfile.tempdir", str(scratch))
        patch.setitem(study.API_FACTORIES, pandapower_api.SOLVER_NAME, factory)
        results = study.make_study(study_fixture.fixture_backend(), case_path, loaded,
                                   solver=pandapower_api.SOLVER_NAME)(selection, None)
    assert len(instances) == 1
    return {"api": instances[0], "results": results, "case_path": case_path,
            "loaded": loaded, "selection": selection}


# -- order and a failed outage change no other answer (ENG-04, D-05) --------------------------------


def test_order_does_not_change_the_screen(tmp_path, monkeypatch):
    case_path = study_fixture.write_case(tmp_path)
    loaded = _island_mapping(tmp_path)
    base = study.prepare_base(study_fixture.fixture_backend(), case_path, loaded,
                              study_fixture.selection(), solver="pandapower")
    try:
        forward = contingency.screen(base)
        original = contingency.select_outages
        monkeypatch.setattr(contingency, "select_outages",
                            lambda chosen: list(reversed(original(chosen))))
        reverse = contingency.screen(base)
    finally:
        study.cleanup_base(base)

    assert [outage.key for outage in reverse.outages] == \
        list(reversed([outage.key for outage in forward.outages]))
    assert ISLAND in forward.outages
    assert forward.rows
    assert sorted(map(_row_key, forward.rows)) == sorted(map(_row_key, reverse.rows))
    assert forward.n_contingencies == reverse.n_contingencies


def test_a_failed_outage_does_not_change_the_others(tmp_path):
    case_path = study_fixture.write_case(tmp_path)
    plain = mapping_module.load_mapping(study_fixture.write_placeholder_mapping(tmp_path),
                                        allow_placeholder=True)
    with_island = _island_mapping(tmp_path)
    selection = study_fixture.selection()
    base_without = study.prepare_base(study_fixture.fixture_backend(), case_path, plain,
                                      selection, solver="pandapower")
    try:
        without = contingency.screen(base_without)
    finally:
        study.cleanup_base(base_without)
    base_with = study.prepare_base(study_fixture.fixture_backend(), case_path, with_island,
                                   selection, solver="pandapower")
    try:
        added = contingency.screen(base_with)
    finally:
        study.cleanup_base(base_with)

    assert ISLAND not in without.outages
    assert ISLAND in added.outages
    assert added.n_contingencies == without.n_contingencies + 1
    assert without.rows
    assert [row for row in added.rows if row["contingency_id"] == ISLAND.key]
    others = [row for row in added.rows if row["contingency_id"] != ISLAND.key]
    assert sorted(map(_row_key, others)) == sorted(map(_row_key, without.rows))


# -- the call sequence of a full four-city study (ENG-04, D-05, D-09) -------------------------------


def test_recorded_calls_never_read_after_a_failed_solve(recorded_study):
    failed = False
    failed_solves = 0
    reads = 0
    for name, _first, extra in recorded_study["api"].log:
        if name == "load_case":
            failed = False
        elif name == "solve":
            failed = not extra
            failed_solves += failed
        elif name in ("bus_table", "branch_loading"):
            reads += 1
            assert not failed, "%s followed a non-converged solve" % name
    assert failed_solves >= 1
    assert reads > failed_solves


def test_every_solve_runs_on_a_freshly_loaded_copy(recorded_study):
    api = recorded_study["api"]
    loaded_since_solve = False
    solves = 0
    for name, _first, _extra in api.log:
        if name == "load_case":
            loaded_since_solve = True
        elif name == "solve":
            assert loaded_since_solve, "a solve did not follow a fresh load_case"
            loaded_since_solve = False
            solves += 1
    assert solves == len(api.solved_nets) > 8
    # No two solves ran on the same network object, and none ran on the master itself.
    assert len(set(id(net) for net in api.solved_nets)) == len(api.solved_nets)
    masters = list(api._masters.values())
    assert masters
    assert not any(net is master for net in api.solved_nets for master in masters)


def test_each_city_loads_the_case_afresh(recorded_study):
    api = recorded_study["api"]
    case_path = recorded_study["case_path"]
    loads = [first for name, first, _extra in api.log if name == "load_case"]
    assert loads.count(case_path) == 1 + len(constants.CITIES)
    # Every other load is the saved solved copy of a city, never another file.
    assert all(path == case_path or path.endswith(".sav") for path in loads)
    outcomes = []
    pending = False
    for name, first, extra in api.log:
        if name == "set_status" and first == ISLAND and extra is False:
            pending = True
        elif name == "solve" and pending:
            outcomes.append(extra)
            pending = False
        elif name == "load_case":
            pending = False
    assert outcomes
    assert not any(outcomes)
    assert len(outcomes) == len(constants.CITIES)


def test_master_unchanged_after_a_full_study(recorded_study):
    api = recorded_study["api"]
    case_path = recorded_study["case_path"]
    key = psse_api._normalise_path(case_path)
    assert list(api._masters) == [key]
    with open(case_path, "rb") as handle:
        fresh = network.build_network(raw.parse_raw(handle.read()))
    master = api._masters[key]
    for table in ("bus", "line", "trafo", "load", "gen", "ext_grid", "shunt"):
        assert isinstance(getattr(master, table), pandas.DataFrame)
        assert getattr(master, table).equals(getattr(fresh, table)), table


def test_two_runs_give_equal_results(recorded_study):
    assert study.API_FACTORIES[pandapower_api.SOLVER_NAME] is pandapower_api.factory
    second = study.make_study(study_fixture.fixture_backend(), recorded_study["case_path"],
                              recorded_study["loaded"], solver=pandapower_api.SOLVER_NAME)(
        recorded_study["selection"], None)
    first = recorded_study["results"]
    assert second == first
    assert first.contingencies
