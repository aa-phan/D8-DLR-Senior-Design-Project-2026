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

import os

import pandapower_fixture
from psse_job import settings
from pandapower_job import api, scaling, solve

OFFSET = pandapower_fixture.OFFSET
RAISED_PT_MW = 5000.0

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


def fixture_backend(enforce_q_lims=False, tolerance_mva=1e-8, max_iteration=30,
                    collapse_voltage_pu=0.5, details=("yes", "no", "yes")):
    """A PandapowerBackend with test settings (every source says so) and the given scaling details."""
    sources = {name: "test fixture" for name in
               ("enforce_q_lims", "tolerance_mva", "max_iteration", "collapse_voltage_pu")}
    return api.PandapowerBackend(
        solve.SolveSettings(enforce_q_lims, tolerance_mva, max_iteration, collapse_voltage_pu,
                            sources, ()),
        scaling.ScalingDetails(details[0], details[1], details[2], {"fixture": True}))
