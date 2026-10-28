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

# Each default is an assumption Power Systems may replace: A8 (voltage bands), A9 (rate set)
# and A11 (the numeric tuning values) of the research Assumptions Log.
DEFAULT_SETTINGS = Settings(
    # RATEA is DLR's analogue (an ambient-adjusted continuous ampacity); A9.
    rate_sets=("RATEA",),
    # Current basis (an ampacity, so heating follows current) at 100 percent; A11.
    thermal_basis="current",
    thermal_limit_pct=100.0,
    # ERCOT-style bands for buses above 100 kV: 0.95 to 1.05 pu before any outage and
    # 0.90 to 1.05 pu after one; A8.
    voltage_source="config",
    base_low_pu=0.95,
    base_high_pu=1.05,
    contingency_low_pu=0.90,
    contingency_high_pu=1.05,
    min_monitor_kv=100.0,
    # Outages: branches within 2 hops of a mapped branch, at most 200; A11.
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
    # Program settings of the case unless a list of 8 integers is given; a base case left
    # with more than 1 MVA of mismatch fails and a bus below 0.5 pu counts as collapsed; A11.
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


_TOP_KEYS = (
    "rate_sets", "thermal", "voltage", "contingency", "transfer", "solve", "max_runtime_seconds",
)
_SECTION_KEYS = {
    "thermal": ("basis", "limit_pct"),
    "voltage": (
        "source", "base_low_pu", "base_high_pu", "contingency_low_pu", "contingency_high_pu",
        "min_monitor_kv",
    ),
    "contingency": ("scope", "hops", "max", "extra"),
    "transfer": ("step_mw", "max_mw", "extra_steps", "tolerance_mw", "min_rise_fraction"),
    "solve": ("options", "max_mismatch_mva", "collapse_voltage_pu"),
}
_BRANCH_KEYS = ("from_bus", "to_bus", "ckt")
MAX_EXTRA_OUTAGES = 50
SOLVE_OPTION_COUNT = 8


def _name(key):
    """A key cut to 40 characters for a message (a study key is untrusted text)."""
    text = str(key)
    return text if len(text) <= 40 else text[:40] + "..."


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _real(value, path, problems, low=None, high=None, low_open=True, high_open=False):
    """
    A float for a finite non-bool number inside the range, else a problem and None. By default
    the range is (low, high]; `low_open` and `high_open` choose open or closed ends and a
    missing end is unbounded.
    """
    ok = _is_number(value)
    if ok and low is not None and (value <= low if low_open else value < low):
        ok = False
    if ok and high is not None and (value >= high if high_open else value > high):
        ok = False
    if ok:
        return float(value)
    parts = []
    if low is not None:
        parts.append("greater than %s" % low if low_open else "at least %s" % low)
    if high is not None:
        parts.append("below %s" % high if high_open else "at most %s" % high)
    problems.append("%s: must be a finite number %s" % (path, " and ".join(parts)))
    return None


def _whole(value, path, problems, low, high):
    """An int (not a bool, not a float) from `low` to `high`, else a problem and None."""
    if isinstance(value, int) and not isinstance(value, bool) and low <= value <= high:
        return value
    problems.append("%s: must be an integer from %d to %d" % (path, low, high))
    return None


def _choice(value, choices, path, problems):
    if isinstance(value, str) and value in choices:
        return value
    problems.append("%s: must be one of %s" % (path, ", ".join(choices)))
    return None


def _section(obj, name, problems):
    """The dict of study section `name` (empty when absent); unknown keys are problems."""
    raw = obj.get(name, {})
    if not isinstance(raw, dict):
        problems.append("study.%s: must be an object" % name)
        return {}
    for key in sorted(raw, key=str):
        if key not in _SECTION_KEYS[name]:
            problems.append("study.%s.%s: unknown key" % (name, _name(key)))
    return raw


def _rate_sets(raw, problems):
    path = "study.rate_sets"
    if not isinstance(raw, list) or not raw:
        problems.append("%s: must be a non-empty list of %s" % (path, ", ".join(RATE_SETS)))
        return None
    names = []
    for index, item in enumerate(raw):
        if not isinstance(item, str) or item not in RATE_SETS:
            problems.append("%s[%d]: must be one of %s" % (path, index, ", ".join(RATE_SETS)))
        elif item in names:
            problems.append("%s[%d]: %s is listed twice" % (path, index, item))
        else:
            names.append(item)
    return tuple(names) if len(names) == len(raw) else None


def _extra_outages(raw, problems):
    path = "study.contingency.extra"
    if not isinstance(raw, list) or len(raw) > MAX_EXTRA_OUTAGES:
        problems.append("%s: must be a list of at most %d branches" % (path, MAX_EXTRA_OUTAGES))
        return None
    outages = []
    seen = set()
    for index, item in enumerate(raw):
        where = "%s[%d]" % (path, index)
        if not isinstance(item, dict):
            problems.append("%s: must be an object" % where)
            continue
        count = len(problems)
        for key in sorted(item, key=str):
            if key not in _BRANCH_KEYS:
                problems.append("%s.%s: unknown key" % (where, _name(key)))
        for key in _BRANCH_KEYS:
            if key not in item:
                problems.append("%s.%s: missing" % (where, key))
        if len(problems) > count:
            continue
        from_bus = check_bus(item["from_bus"], where + ".from_bus", problems)
        to_bus = check_bus(item["to_bus"], where + ".to_bus", problems)
        ckt = check_ckt(item["ckt"], where + ".ckt", problems)
        if from_bus is None or to_bus is None or ckt is None:
            continue
        if from_bus == to_bus:
            problems.append("%s: from_bus and to_bus must differ" % where)
            continue
        branch = BranchRef(from_bus, to_bus, ckt)
        if branch.normalised() in seen:
            problems.append("%s: branch %s is listed twice" % (where, branch.key))
            continue
        seen.add(branch.normalised())
        outages.append(branch)
    return tuple(outages) if len(outages) == len(raw) else None


def _solve_options(raw, problems):
    if raw is None:
        return None
    if (
        isinstance(raw, list)
        and len(raw) == SOLVE_OPTION_COUNT
        and all(isinstance(item, int) and not isinstance(item, bool) for item in raw)
    ):
        return tuple(raw)
    problems.append(
        "study.solve.options: must be null or a list of exactly %d integers" % SOLVE_OPTION_COUNT
    )
    return None


def parse_settings(obj):
    """
    The Settings for the `study` section `obj`: DEFAULT_SETTINGS for None or an empty object;
    a key that is not given keeps its default. SettingsError, naming every problem with its
    dotted path, for anything that is not an object, an unknown key at any level, and any
    value outside its range (ranges: research D-09, D-11, D-12 and D-13).
    """
    if obj is None:
        return DEFAULT_SETTINGS
    if not isinstance(obj, dict):
        raise SettingsError(["study: must be an object"])
    if not obj:
        return DEFAULT_SETTINGS

    problems = []
    for key in sorted(obj, key=str):
        if key not in _TOP_KEYS:
            problems.append("study.%s: unknown key" % _name(key))
    defaults = DEFAULT_SETTINGS
    values = {}

    if "rate_sets" in obj:
        values["rate_sets"] = _rate_sets(obj["rate_sets"], problems)

    thermal = _section(obj, "thermal", problems)
    if "basis" in thermal:
        values["thermal_basis"] = _choice(
            thermal["basis"], THERMAL_BASES, "study.thermal.basis", problems
        )
    if "limit_pct" in thermal:
        values["thermal_limit_pct"] = _real(
            thermal["limit_pct"], "study.thermal.limit_pct", problems, low=0, high=200
        )

    voltage = _section(obj, "voltage", problems)
    if "source" in voltage:
        values["voltage_source"] = _choice(
            voltage["source"], VOLTAGE_SOURCES, "study.voltage.source", problems
        )
    for key in ("base_low_pu", "base_high_pu", "contingency_low_pu", "contingency_high_pu"):
        if key in voltage:
            values[key] = _real(
                voltage[key], "study.voltage.%s" % key, problems,
                low=0.5, high=1.5, high_open=True,
            )
    if "min_monitor_kv" in voltage:
        values["min_monitor_kv"] = _real(
            voltage["min_monitor_kv"], "study.voltage.min_monitor_kv", problems,
            low=0, low_open=False,
        )

    contingency = _section(obj, "contingency", problems)
    if "scope" in contingency:
        values["contingency_scope"] = _choice(
            contingency["scope"], CONTINGENCY_SCOPES, "study.contingency.scope", problems
        )
    if "hops" in contingency:
        values["contingency_hops"] = _whole(
            contingency["hops"], "study.contingency.hops", problems, 0, 5
        )
    if "max" in contingency:
        values["contingency_max"] = _whole(
            contingency["max"], "study.contingency.max", problems, 1, 1000
        )
    if "extra" in contingency:
        values["contingency_extra"] = _extra_outages(contingency["extra"], problems)

    transfer = _section(obj, "transfer", problems)
    if "step_mw" in transfer:
        values["transfer_step_mw"] = _real(
            transfer["step_mw"], "study.transfer.step_mw", problems, low=0, high=1000
        )
    step = values["transfer_step_mw"] if "transfer_step_mw" in values else defaults.transfer_step_mw
    if "max_mw" in transfer:
        if step is None:
            # The step is invalid and already reported; only the type can still be judged.
            values["transfer_max_mw"] = None
            if not _is_number(transfer["max_mw"]):
                problems.append("study.transfer.max_mw: must be a finite number")
        else:
            values["transfer_max_mw"] = _real(
                transfer["max_mw"], "study.transfer.max_mw", problems,
                low=step, low_open=False, high=10000,
            )
    if "extra_steps" in transfer:
        values["transfer_extra_steps"] = _whole(
            transfer["extra_steps"], "study.transfer.extra_steps", problems, 0, 1000
        )
    if "tolerance_mw" in transfer:
        if step is None:
            values["transfer_tolerance_mw"] = None
            if not _is_number(transfer["tolerance_mw"]):
                problems.append("study.transfer.tolerance_mw: must be a finite number")
        else:
            values["transfer_tolerance_mw"] = _real(
                transfer["tolerance_mw"], "study.transfer.tolerance_mw", problems,
                low=0, high=step, high_open=True,
            )
    elif step is not None and not defaults.transfer_tolerance_mw < step:
        problems.append(
            "study.transfer.tolerance_mw: the default %s is not below study.transfer.step_mw; "
            "set both" % defaults.transfer_tolerance_mw
        )
    if "min_rise_fraction" in transfer:
        values["transfer_min_rise_fraction"] = _real(
            transfer["min_rise_fraction"], "study.transfer.min_rise_fraction", problems,
            low=0, low_open=False, high=1, high_open=True,
        )

    solve = _section(obj, "solve", problems)
    if "options" in solve:
        values["solve_options"] = _solve_options(solve["options"], problems)
    if "max_mismatch_mva" in solve:
        values["max_mismatch_mva"] = _real(
            solve["max_mismatch_mva"], "study.solve.max_mismatch_mva", problems, low=0, high=100
        )
    if "collapse_voltage_pu" in solve:
        values["collapse_voltage_pu"] = _real(
            solve["collapse_voltage_pu"], "study.solve.collapse_voltage_pu", problems,
            low=0, high=1, high_open=True,
        )
    if "max_runtime_seconds" in obj:
        values["max_runtime_seconds"] = _real(
            obj["max_runtime_seconds"], "study.max_runtime_seconds", problems, low=0, high=3600
        )

    def effective(field):
        return values[field] if field in values else getattr(defaults, field)

    # Cross-field rules, judged on the effective values and only when both are valid.
    low, high = effective("base_low_pu"), effective("base_high_pu")
    if low is not None and high is not None and not low < high:
        problems.append("study.voltage.base_low_pu: must be below base_high_pu")
    low, high = effective("contingency_low_pu"), effective("contingency_high_pu")
    if low is not None and high is not None and not low < high:
        problems.append("study.voltage.contingency_low_pu: must be below contingency_high_pu")
    collapse, criterion = effective("collapse_voltage_pu"), effective("contingency_low_pu")
    if collapse is not None and criterion is not None and not collapse < criterion:
        problems.append(
            "study.solve.collapse_voltage_pu: must be below voltage.contingency_low_pu "
            "(otherwise the collapse guard would hide the voltage criterion)"
        )

    if problems:
        raise SettingsError(problems)
    merged = dict((field, getattr(defaults, field)) for field in Settings._fields)
    merged.update(values)
    return Settings(**merged)
