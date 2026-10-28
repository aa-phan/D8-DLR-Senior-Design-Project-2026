"""
The study parameters of the PSS/E job (pss-e-integration Phase 2, plan 02-01; research D-09,
D-11, D-12, D-13).

Every default below is a stated assumption (research A8, A9 and A11) that Power Systems may
replace through the `study` section of the mapping file; nothing here settles an open
question for them. The parameters ride in the mapping file on purpose: the one recorded
mapping_sha256 then covers every number that shaped a result.

`BranchRef` lives here because both the mapping's cities section and `study.contingency.extra`
use it; psse_job.mapping imports this module, never the other way round.

Standard library only, Python 3.7 syntax (D-05).
"""

import collections
import math
import re

# Rating sets of a PSS/E branch; the DLR value is written to every listed set and the first
# listed set is the limit of every thermal check (research D-09).
RATE_SETS = ("RATEA", "RATEB", "RATEC")
# Thermal check basis: percent of the rating by current (an ampacity, so heating follows
# current) or by MVA (research D-11).
THERMAL_BASES = ("current", "mva")
# Where the voltage bands come from: this configuration, or the per-bus limits of the case.
VOLTAGE_SOURCES = ("config", "case")
# N-1 outage set: branches near the mapped branches, or every non-transformer branch.
CONTINGENCY_SCOPES = ("neighbourhood", "all")

_CKT_PATTERN = re.compile(r"[!-~]{1,2}")


class SettingsError(ValueError):
    """The study section is invalid; `.problems` lists every problem found."""

    def __init__(self, problems):
        self.problems = list(problems)
        ValueError.__init__(self, "; ".join(self.problems))


class BranchRef(collections.namedtuple("BranchRef", ["from_bus", "to_bus", "ckt"])):
    """A branch as PSS/E names it: from bus, to bus, circuit identifier."""

    __slots__ = ()

    @property
    def key(self):
        """'from-to-ckt', the contingency and element id of the branch."""
        return "%d-%d-%s" % (self.from_bus, self.to_bus, self.ckt)

    def normalised(self):
        """(smaller bus, larger bus, ckt): the same branch whichever way it is listed."""
        return (min(self.from_bus, self.to_bus), max(self.from_bus, self.to_bus), self.ckt)


Settings = collections.namedtuple("Settings", [
    "rate_sets",
    "thermal_basis",
    "thermal_limit_pct",
    "voltage_source",
    "base_low_pu",
    "base_high_pu",
    "contingency_low_pu",
    "contingency_high_pu",
    "min_monitor_kv",
    "contingency_scope",
    "contingency_hops",
    "contingency_max",
    "contingency_extra",
    "transfer_step_mw",
    "transfer_max_mw",
    "transfer_extra_steps",
    "transfer_tolerance_mw",
    "transfer_min_rise_fraction",
    "solve_options",
    "max_mismatch_mva",
    "collapse_voltage_pu",
    "max_runtime_seconds",
])

# Each default is an assumption Power Systems may replace (research A8, A9, A11).
DEFAULT_SETTINGS = Settings(
    # RATEA is DLR's analogue (an ambient-adjusted continuous ampacity); A8.
    rate_sets=("RATEA",),
    # Current basis at 100 percent of the rating; A8.
    thermal_basis="current",
    thermal_limit_pct=100.0,
    # ERCOT-style bands for buses above 100 kV: 0.95 to 1.05 pu before any outage and
    # 0.90 to 1.05 pu after one; A9.
    voltage_source="config",
    base_low_pu=0.95,
    base_high_pu=1.05,
    contingency_low_pu=0.90,
    contingency_high_pu=1.05,
    min_monitor_kv=100.0,
    # Outages: branches within 2 hops of a mapped branch, at most 200; A9.
    contingency_scope="neighbourhood",
    contingency_hops=2,
    contingency_max=200,
    contingency_extra=(),
    # Margin search: 25 MW steps to a 1000 MW starting cap, then at most 80 further steps
    # while no bound has been found, so a search ended by the cap alone never reports an
    # understated voltage limit; 1 MW tolerance; A11.
    transfer_step_mw=25.0,
    transfer_max_mw=1000.0,
    transfer_extra_steps=80,
    transfer_tolerance_mw=1.0,
    transfer_min_rise_fraction=0.01,
    # Program settings of the case unless a list of 8 integers is given.
    solve_options=None,
    max_mismatch_mva=1.0,
    collapse_voltage_pu=0.5,
    # The job runs hourly; A11.
    max_runtime_seconds=1500.0,
)


def check_bus(value, where, problems):
    """`value` when it is an int (not a bool) from 1 to 999999, else a problem and None."""
    if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 999999:
        return value
    problems.append("%s: bus number must be an integer from 1 to 999999" % where)
    return None


def check_ckt(value, where, problems):
    """
    The stripped circuit id when `value` is a str of one or two printable ASCII characters
    (no space) that does not start with '&' (a multisection line identifier, which PSS/E's
    branch calls reject); otherwise a problem and None.
    """
    if isinstance(value, str):
        text = value.strip()
        if _CKT_PATTERN.fullmatch(text) and not text.startswith("&"):
            return text
    problems.append(
        "%s: circuit id must be 1 or 2 printable characters and not a multisection '&' id" % where
    )
    return None


def rate_set_label(settings):
    """The rate sets joined with '+', for psse_run.rate_set."""
    return "+".join(settings.rate_sets)


def parse_settings(obj):
    """
    The Settings for the `study` section `obj`: DEFAULT_SETTINGS for None or an empty object,
    SettingsError for anything that is not an object.
    """
    if obj is None:
        return DEFAULT_SETTINGS
    if not isinstance(obj, dict):
        raise SettingsError(["study: must be an object"])
    if not obj:
        return DEFAULT_SETTINGS
    raise SettingsError(["study: overrides are not supported yet"])
