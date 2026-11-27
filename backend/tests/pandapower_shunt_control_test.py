"""
Tests for the switched-shunt stepping loop of `solve.run_load_flow` (pandapower-solver Phase 1,
plan 01-10: the A-shunt control the first real session called for).

Inputs are synthetic: pandapower's 39-bus case with the bus numbers offset by 90000, plus one
switched shunt whose band is placed relative to voltages measured in the test itself, so no value
comes from a private file. The tests prove the loop's rules (up below the band, down above it,
never past an end, a locked or out-of-service shunt stays put, a loop that cannot settle is not a
pass). That the rule matches PSS/E is proved only by NET-03 against PSS/E's own answers.

Failure messages are counts only.
"""

import copy

import pytest

pandapower = pytest.importorskip("pandapower")

import pandapower_fixture as fixture  # noqa: E402
from pandapower_job import network, raw, solve  # noqa: E402

OFFSET = fixture.OFFSET
SETTINGS = solve.SolveSettings(False, 1e-8, 30, 0.5, {}, ())
LEVELS = [0.0, 50.0, 100.0, 150.0]


def _bus():
    return fixture.case39_records(OFFSET)["load"][0]["I"]


def _net(binit, low=0.95, high=1.05, **changes):
    records = fixture.case39_records(OFFSET)
    shunt = dict({"I": _bus(), "MODSW": 1, "ADJM": 0, "STAT": 1, "VSWHI": high, "VSWLO": low,
                  "SWREM": 0, "RMPCT": 100.0, "RMIDNT": "", "BINIT": binit, "N1": 3, "B1": 50.0},
                 **changes)
    for number in range(1, 9):
        shunt.setdefault("N%d" % number, 0)
        shunt.setdefault("B%d" % number, 0.0)
    records["switched_shunt"] = [shunt]
    return network.build_network(raw.parse_raw(fixture.raw_text(records).encode("utf-8")))


def _voltage_at(level):
    """The bus voltage with the shunt held at `level` Mvar (no control)."""
    net = _net(level, MODSW=0)
    assert solve.run_load_flow(net, SETTINGS, False).converged
    return float(net.res_bus.at[_bus(), "vm_pu"])


def _level_now(net):
    return -float(net.shunt.at[0, "q_mvar"])


def test_a_voltage_below_the_band_steps_the_shunt_up_until_it_is_inside():
    below = _voltage_at(0.0)
    middle = (_voltage_at(50.0) + _voltage_at(100.0)) / 2.0
    net = _net(0.0, low=middle, high=2.0)
    assert float(net.shunt.at[0, "q_mvar"]) == 0.0
    outcome = solve.run_load_flow(net, SETTINGS, False)
    assert outcome.converged
    level = _level_now(net)
    assert level == 100.0, "it must stop at the first level whose voltage reaches the band"
    assert below < middle <= float(net.res_bus.at[_bus(), "vm_pu"])
    assert _voltage_at(50.0) < middle, "the level below it is still under the band"


def test_a_voltage_above_the_band_steps_the_shunt_down_until_it_is_inside():
    middle = (_voltage_at(50.0) + _voltage_at(100.0)) / 2.0
    net = _net(150.0, low=0.0, high=middle)
    outcome = solve.run_load_flow(net, SETTINGS, False)
    assert outcome.converged
    assert _level_now(net) == 50.0
    assert float(net.res_bus.at[_bus(), "vm_pu"]) <= middle
    assert _voltage_at(100.0) > middle, "the level above it is still over the band"


def test_the_shunt_never_steps_past_its_first_or_last_level():
    top = _net(0.0, low=5.0, high=9.0)            # no level reaches this band: stops at the top
    assert solve.run_load_flow(top, SETTINGS, False).converged
    assert _level_now(top) == LEVELS[-1]
    bottom = _net(150.0, low=0.0, high=0.1)       # every level is above this band: stops at zero
    assert solve.run_load_flow(bottom, SETTINGS, False).converged
    assert _level_now(bottom) == 0.0


def test_a_voltage_inside_the_band_changes_nothing():
    net = _net(100.0, low=0.5, high=2.0)
    assert solve.run_load_flow(net, SETTINGS, False).converged
    assert _level_now(net) == 100.0


def test_a_locked_or_out_of_service_shunt_stays_where_it_starts():
    for change in ({"MODSW": 0}, {"STAT": 0}):
        net = _net(0.0, low=5.0, high=9.0, **change)
        assert solve.run_load_flow(net, SETTINGS, False).converged
        assert _level_now(net) == 0.0


def test_a_band_too_narrow_for_the_step_does_not_settle_and_is_not_a_pass():
    # one value between the voltages at two neighbouring levels: below it the shunt steps up and
    # above it down, for ever
    narrow = (_voltage_at(0.0) + _voltage_at(50.0)) / 2.0
    net = _net(0.0, low=narrow, high=narrow)
    outcome = solve.run_load_flow(net, SETTINGS, False)
    assert outcome.converged is False and outcome.reason == "shunt_control_not_settled"


def test_a_net_without_a_controlled_shunt_solves_exactly_as_before():
    records = fixture.case39_records(OFFSET)
    plain = network.build_network(raw.parse_raw(fixture.raw_text(records).encode("utf-8")))
    copied = copy.deepcopy(plain)
    assert solve.run_load_flow(plain, SETTINGS, False).converged
    pandapower.runpp(copied, algorithm="nr", calculate_voltage_angles=True, enforce_q_lims=False,
                     tolerance_mva=1e-8, max_iteration=30)
    assert plain.res_bus.vm_pu.equals(copied.res_bus.vm_pu)
