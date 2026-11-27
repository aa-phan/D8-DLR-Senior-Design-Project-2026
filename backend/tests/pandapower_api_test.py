"""
Tests for the pandapower adapter (pandapower-solver Phase 2, plan 02-02: ENG-02 to ENG-04).

Every input is a synthetic RAW file generated at test time from pandapower's own 39-bus case with
the bus numbers offset by 90000 (`pandapower_study_fixture`), written into tmp_path only. The
adapter runs on the real solver. Failure messages are counts only.
"""

import math
import re

import pytest

pandapower = pytest.importorskip("pandapower")

import pandapower_study_fixture as study_fixture  # noqa: E402
from psse_job import psse_api, settings, units  # noqa: E402
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


# -- refusals ---------------------------------------------------------------------------------

_BUS_NUMBER = re.compile(r"\b9[0-9]{4}\b")
_MISSING = settings.BranchRef(1, 2, "1")


def _transformer(api):
    _, transformers = api.branch_table()
    return transformers[0]


def test_refuse_mva_basis_and_unknown_names(case_path):
    api = _api(case_path)
    assert api.solve().converged is True
    with pytest.raises(ValueError) as caught:
        api.branch_loading("RATEA", "mva")
    assert "current" in str(caught.value)
    with pytest.raises(ValueError):
        api.branch_loading("RATEZ", "current")
    with pytest.raises(ValueError):
        api.branch_loading("RATEA", "volts")


def test_refuse_transformer_writes_and_reads(case_path):
    api = _api(case_path)
    ref = _transformer(api)
    for call, args in ((api.set_rate, (ref, "RATEA", 100.0)), (api.set_status, (ref, False))):
        with pytest.raises(psse_api.PsseCallError) as caught:
            call(*args)
        assert caught.value.ierr == 3
        assert caught.value.meaning == "branch is a two-winding transformer"
    with pytest.raises(psse_api.PsseCallError) as caught:
        api.read_rate(ref, "RATEA")
    assert caught.value.ierr == 2
    assert caught.value.meaning == "branch not found"
    assert api._state == "fresh"


def test_refuse_unknown_branch(case_path):
    api = _api(case_path)
    for call, args in ((api.set_rate, (_MISSING, "RATEA", 100.0)),
                       (api.set_status, (_MISSING, False))):
        with pytest.raises(psse_api.PsseCallError) as caught:
            call(*args)
        assert caught.value.ierr == 9
        assert caught.value.meaning == "branch not found"
    with pytest.raises(psse_api.PsseCallError) as caught:
        api.read_rate(_MISSING, "RATEA")
    assert caught.value.ierr == 2


def test_refuse_bad_rating_values(case_path):
    api = _api(case_path)
    ref = _outage(api)
    for bad in (0, -1, float("inf"), float("nan")):
        with pytest.raises(ValueError) as caught:
            api.set_rate(ref, "RATEA", bad)
        assert str(caught.value) == "mva must be finite and greater than 0"
    for bad in (True, "1", None):
        with pytest.raises(ValueError) as caught:
            api.set_rate(ref, "RATEA", bad)
        assert str(caught.value) == "mva must be a number"
    with pytest.raises(ValueError) as caught:
        api.set_rate(ref, "RATEA", 10 ** 400)
    assert str(caught.value) == "mva is out of range"
    with pytest.raises(ValueError) as caught:
        api.set_rate(object(), "RATEZ", 1.0)
    assert str(caught.value) == "rate_set must be one of RATEA, RATEB, RATEC"
    with pytest.raises(ValueError) as caught:
        api.set_status(ref, 1)
    assert str(caught.value) == "in_service must be True or False"
    assert api._state == "fresh"


def test_refuse_solve_options_and_bad_backend(case_path):
    api = _api(case_path)
    with pytest.raises(ValueError):
        api.solve([0] * 8)
    with pytest.raises(ValueError):
        PandapowerApi(object())
    assert api._state == "fresh"


def test_rating_is_a_current_limit_per_circuit(case_path):
    api = _api(case_path)
    lines, _ = api.branch_table()
    net = api._net
    for row in lines:
        index = api._line_index(net, row.from_bus, row.to_bus, row.ckt)
        kv = float(net.bus.at[net.line.at[index, "from_bus"], "vn_kv"])
        for rate_set in ("RATEA", "RATEB", "RATEC"):
            mva = units.circuit_mva(1825.0, 2, kv)
            api.set_rate(row, rate_set, mva)
            assert _relative(float(net.line.at[index, "max_i_ka"]) * 1000.0,
                             units.circuit_amps(1825.0, 2)) < 1e-9
            for read_set in ("RATEA", "RATEB", "RATEC"):
                assert _relative(api.read_rate(row, read_set), mva) < 1e-9


def test_line_derating_and_parallel_are_pinned(case_path):
    api = _api(case_path)
    assert (api._net.line["df"] == 1).all()
    assert (api._net.line["parallel"] == 1).all()
    index = api._net.line.index[0]
    api._net.line.at[index, "df"] = 0.5
    assert api.solve().converged is True
    with pytest.raises(psse_api.PsseCallError):
        api.branch_loading("RATEA", "current")
    api.load_case(case_path)
    api._net.line.at[index, "parallel"] = 2
    assert api.solve().converged is True
    with pytest.raises(psse_api.PsseCallError):
        api.branch_loading("RATEA", "current")


def test_messages_are_figure_free(case_path, tmp_path):
    api = _api(case_path)
    ref = _outage(api)
    transformer = _transformer(api)
    keys = [row.key for row in api.branch_table()[0]]
    texts = []

    def collect(call, *args, kind=Exception):
        with pytest.raises(kind) as caught:
            call(*args)
        texts.append(str(caught.value))
        return caught.value

    collect(api.branch_loading, "RATEA", "current")
    collect(api.set_rate, transformer, "RATEA", 100.0)
    collect(api.set_status, transformer, False)
    collect(api.read_rate, transformer, "RATEA")
    collect(api.set_rate, _MISSING, "RATEA", 100.0)
    collect(api.read_rate, _MISSING, "RATEA")
    for bad in (0, float("nan"), True, 10 ** 400):
        collect(api.set_rate, ref, "RATEA", bad)
    collect(api.set_rate, ref, "RATEZ", 1.0)
    collect(api.set_status, ref, "no")
    collect(api.solve, [0] * 8)
    collect(PandapowerApi, object())
    collect(api.load_case, str(tmp_path / "no_such_case.raw"))
    collect(api.save_case, case_path, kind=psse_api.CaseProtected)
    api.set_status(ref, False)
    collect(api.bus_table)
    api.load_case(case_path)
    api._net.line.at[api._net.line.index[0], "df"] = 0.5
    api.solve()
    error = collect(api.branch_loading, "RATEA", "current")
    assert str(error).startswith("pandapower.")
    api.load_case(case_path)
    api.solve()
    collect(api.branch_loading, "RATEA", "mva")
    assert len(texts) >= 18
    for text in texts:
        assert _BUS_NUMBER.search(text) is None
        assert not any(key in text for key in keys)
        assert str(tmp_path) not in text and case_path not in text


def _fresh_rows(api):
    return {number: row._replace(pu=None) for number, row in api.bus_table().items()}


def test_converted_json_equals_raw(case_path, tmp_path):
    converted = study_fixture.write_converted(tmp_path)
    from_raw = PandapowerApi(study_fixture.fixture_backend(), protected_path=case_path)
    from_json = PandapowerApi(study_fixture.fixture_backend(), protected_path=converted)
    from_raw.load_case(case_path)
    from_json.load_case(converted)
    assert from_raw.branch_table() == from_json.branch_table()
    assert _fresh_rows(from_raw) == _fresh_rows(from_json)
    first, second = from_raw.solve(), from_json.solve()
    assert first.converged is True and second.converged is True
    assert from_raw.branch_loading("RATEA", "current") == from_json.branch_loading("RATEA", "current")
    assert from_raw.bus_table() == from_json.bus_table()


def test_version_is_pandapower(case_path):
    assert _api(case_path).version() == pandapower.__version__
