"""
Tests for the pandapower adapter (pandapower-solver Phase 2, plan 02-02: ENG-02 to ENG-04).

Every input is a synthetic RAW file generated at test time from pandapower's own 39-bus case with
the bus numbers offset by 90000 (`pandapower_study_fixture`), written into tmp_path only. The
adapter runs on the real solver. Failure messages are counts only.
"""

import math

import pytest

pandapower = pytest.importorskip("pandapower")

import pandapower_study_fixture as study_fixture  # noqa: E402
from psse_job import psse_api  # noqa: E402
from pandapower_job import network, raw  # noqa: E402
from pandapower_job.api import PandapowerApi  # noqa: E402


def _relative(first, second):
    return abs(first - second) / max(abs(first), abs(second), 1e-300)


def _records_rate(records, ref):
    for rec in records["branch"]:
        if (rec["I"], rec["J"], rec["CKT"]) == (ref.from_bus, ref.to_bus, ref.ckt):
            return rec["RATEA"]
    raise AssertionError("branch not in the fixture records")


def test_tracer_case_file_to_current_basis_loading(tmp_path):
    path = study_fixture.write_case(tmp_path)
    api = PandapowerApi(study_fixture.fixture_backend(), protected_path=path)
    api.load_case(path)

    lines, _ = api.branch_table()
    ref = lines[0]
    records = study_fixture.fixture_records()
    assert _relative(api.read_rate(ref, "RATEA"), _records_rate(records, ref)) < 1e-9

    api.set_rate(ref, "RATEA", 1000.0)
    assert _relative(api.read_rate(ref, "RATEA"), 1000.0) < 1e-9

    result = api.solve()
    assert result.converged is True
    assert result.ierr == 0
    assert result.solved_code == 0

    rows = api.branch_loading("RATEA", "current")
    assert [row.key for row in rows] == sorted(row.key for row in rows)
    assert len(rows) == len(lines)
    row = [item for item in rows if item.key == ref.key][0]
    assert _relative(row.rate_mva, 1000.0) < 1e-9
    net = api._net
    index = api._line_index(net, ref.from_bus, ref.to_bus, ref.ckt)
    result_row = net.res_line.loc[index]
    expected = (max(result_row.i_from_ka, result_row.i_to_ka) / net.line.at[index, "max_i_ka"]
                * 100.0)
    assert _relative(row.pct, expected) < 1e-12
    for item in rows:
        if item.in_service:
            assert math.isfinite(item.pct)


# -- shared state -----------------------------------------------------------------------------

_APIS = {}
ISLAND = study_fixture.ISLANDING_OUTAGE


@pytest.fixture(scope="module")
def case_path(tmp_path_factory):
    return study_fixture.write_case(tmp_path_factory.mktemp("pp_api"))


def _api(path, **backend):
    """One adapter per backend setting for the module (the master is built once; every test
    starts from load_case, which hands out a fresh copy)."""
    key = (path, tuple(sorted(backend.items())))
    if key not in _APIS:
        _APIS[key] = PandapowerApi(study_fixture.fixture_backend(**backend), protected_path=path)
    api = _APIS[key]
    api.load_case(path)
    return api


def _outage(api):
    """A line that is not the islanding outage."""
    lines, _ = api.branch_table()
    return [row for row in lines if row.key != ISLAND.key][0]


def _refused(call, *args):
    with pytest.raises(psse_api.PsseCallError) as caught:
        call(*args)
    assert "no valid solution" in str(caught.value)
    return caught.value


# -- state machine ----------------------------------------------------------------------------


def test_state_fresh_reads(case_path):
    api = _api(case_path)
    table = api.bus_table()
    assert len(table) == len(api._net.bus)
    assert all(math.isnan(row.pu) for row in table.values())
    error = _refused(api.branch_loading, "RATEA", "current")
    assert isinstance(error, psse_api.PsseCallError)


def test_state_solved_reads(case_path):
    api = _api(case_path)
    assert api.solve().converged is True
    table = api.bus_table()
    for number, row in table.items():
        if api._net.bus.at[number, "in_service"]:
            assert row.pu == float(api._net.res_bus.at[number, "vm_pu"])
    assert len(api.branch_loading("RATEA", "current")) == len(api._net.line)


def test_state_stale_after_status_or_rating_change(case_path):
    api = _api(case_path)
    ref = _outage(api)
    assert api.solve().converged is True
    api.set_status(ref, False)
    _refused(api.bus_table)
    _refused(api.branch_loading, "RATEA", "current")
    api.load_case(case_path)
    assert api.solve().converged is True
    api.set_rate(ref, "RATEA", 500.0)
    _refused(api.bus_table)
    _refused(api.branch_loading, "RATEA", "current")


def test_state_failed_after_non_converged_solve(case_path):
    api = _api(case_path, max_iteration=1)
    assert api.solve().converged is False
    _refused(api.bus_table)
    _refused(api.branch_loading, "RATEA", "current")


def test_snapshot_save_and_reload(case_path, tmp_path):
    api = _api(case_path)
    ref = _outage(api)
    assert api.solve().converged is True
    snap = str(tmp_path / "snapshot.sav")
    api.save_case(snap)
    assert not (tmp_path / "snapshot.sav").exists()
    assert api._state == "solved"
    api.set_status(ref, False)
    api.load_case(snap)
    assert api._state == "solved"
    row = [item for item in api.branch_loading("RATEA", "current") if item.key == ref.key][0]
    assert row.in_service is True
    api.set_status(ref, False)
    with pytest.raises(psse_api.CaseProtected):
        api.save_case(case_path)
    assert api._net is not None


def test_snapshot_from_failed_state_reloads_fresh(case_path, tmp_path):
    api = _api(case_path, max_iteration=1)
    assert api.solve().converged is False
    snap = str(tmp_path / "failed.sav")
    api.save_case(snap)
    api.load_case(case_path)
    api.load_case(snap)
    assert api._state == "fresh"
    assert all(math.isnan(row.pu) for row in api.bus_table().values())


def test_unknown_path_is_error_opening(case_path, tmp_path):
    api = _api(case_path)
    with pytest.raises(psse_api.PsseCallError) as caught:
        api.load_case(str(tmp_path / "no_such_case.raw"))
    assert caught.value.ierr == 3


# -- outcome mapping ---------------------------------------------------------------------------


def test_island_is_not_converged_while_pandapower_says_converged(case_path, tmp_path):
    api = _api(case_path)
    snap = str(tmp_path / "island.sav")
    api.save_case(snap)
    api.load_case(snap)
    api.set_status(ISLAND, False)
    result = api.solve()
    assert api._net.converged is True
    assert result.converged is False
    assert result.ierr == 3
    assert result.meaning.startswith("fnsl ierr 3: buses in island without swing bus")
    assert api._last_reason == "nan_voltage"


def test_nonconv_iteration_limit(case_path):
    api = _api(case_path, max_iteration=1)
    result = api.solve()
    assert result.converged is False
    assert result.meaning == "iteration limit exceeded"


def test_collapse_voltage(case_path):
    api = _api(case_path, collapse_voltage_pu=1.2)
    result = api.solve()
    assert result.converged is False
    assert result.meaning == "blown up (non-divergent option disabled)"


def test_tripped_line_reads_out_of_service(case_path):
    api = _api(case_path)
    ref = _outage(api)
    api.set_status(ref, False)
    assert api.solve().converged is True
    rows = {row.key: row for row in api.branch_loading("RATEA", "current")}
    assert rows[ref.key].in_service is False
    assert all(row.in_service for key, row in rows.items() if key != ref.key)


def _run(api, snap, outages):
    """{outage key: (converged, ierr, flows, buses)}; reads only after a converged solve."""
    found = {}
    for ref in outages:
        api.load_case(snap)
        api.set_status(ref, False)
        result = api.solve()
        if result.converged:
            found[ref.key] = (True, result.ierr, api.branch_loading("RATEA", "current"),
                              api.bus_table())
        else:
            found[ref.key] = (False, result.ierr, None, None)
    return found


def test_order_and_a_failed_solve_do_not_change_results(case_path, tmp_path):
    api = _api(case_path)
    snap = str(tmp_path / "order.sav")
    api.save_case(snap)
    lines, _ = api.branch_table()
    outages = [row for row in lines if row.key != ISLAND.key][:5] + [ISLAND]
    forward = _run(api, snap, outages)
    reverse = _run(api, snap, list(reversed(outages)))
    island_first = _run(api, snap, [ISLAND] + outages[:-1])
    assert forward[ISLAND.key][0] is False
    assert any(item[0] for item in forward.values())
    assert forward == reverse
    assert forward == island_first


def test_master_unchanged_after_mutations(case_path):
    api = _api(case_path)
    ref = _outage(api)
    api.set_status(ref, False)
    api.set_rate(ref, "RATEA", 250.0)
    api.solve()
    api.load_case(case_path)
    api.set_status(ISLAND, False)
    api.solve()
    master = api._masters[psse_api._normalise_path(case_path)]
    with open(case_path, "rb") as handle:
        built = network.build_network(raw.parse_raw(handle.read()))
    for table in ("bus", "line", "trafo", "load", "gen", "ext_grid"):
        assert getattr(master, table).equals(getattr(built, table))


def test_bus_type_codes_and_limits(case_path):
    api = _api(case_path)
    net = api._net
    swing = set(int(bus) for bus in net.ext_grid.bus)
    gens = set(int(bus) for bus in net.gen.bus)
    dead = [number for number in net.bus.index if number not in swing | gens][0]
    api._net.bus.at[dead, "in_service"] = False
    table = api.bus_table()
    for number, row in table.items():
        expected = 4 if number == dead else (3 if number in swing else (2 if number in gens else 1))
        assert row.type_code == expected
        assert row.base_kv == float(net.bus.at[number, "vn_kv"])
        assert row.nvlmlo == float(net.bus.at[number, "min_vm_pu"])
        assert row.nvlmhi == float(net.bus.at[number, "max_vm_pu"])
        assert row.evlmlo == 0.0 and row.evlmhi == 0.0
        assert type(row.number) is int and type(row.type_code) is int
        assert type(row.base_kv) is float and type(row.pu) is float
