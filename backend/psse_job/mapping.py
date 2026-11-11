"""
The city-to-branch mapping that Power Systems supplies, stored as configuration
(pss-e-integration Phase 2, plan 02-01: IN-02, D-08).

One JSON file: a required `cities` section (their branch choices) and an optional `study`
section (job parameters with stated defaults, psse_job.settings). `load_mapping` returns the
parsed Mapping and the sha256 of exactly the bytes it parsed, so the recorded hash and the
content cannot differ. The real file stays on the laptop outside the repository, because bus
numbers and circuit ids are grid identifiers and the repository is public (OD-6, D-03); only
the marked placeholder example is committed. The file is parsed with json only, never
executed.

Schema version 2 (Phase 4, plan 04-01, SCL-01) adds a required `scaling` block to every city:
the target net load in MW (`load_mw`), the target generation in MW (`gen_mw`) and a `basis`
label (`average` or `peak`). The block holds two numbers and one label and nothing else: a key
that names a file or a script is an unknown key like any other, and there is no reactive
target because each city keeps the base case's load power factor. The parser checks shape and
range only; the real targets live in the private file on the laptop, never in the repository.

The same line may be listed under more than one city, because each city is solved on its own
copy of the case (CD-6, Power Systems to confirm); a line listed twice within one city, in
either orientation, is still refused.

Standard library only, Python 3.7 syntax (D-05).
"""

import collections
import hashlib
import json
import math

from psse_job import constants, run_record, settings

SCHEMA_VERSION = 2
MAX_MAPPING_BYTES = 65536
MAX_BRANCHES_PER_CITY = 20
MAX_SINK_BUSES = 20
NOTE_MAX_CHARS = 200
MAX_PROBLEMS = 20
SCALING_BASES = ("average", "peak")

BranchRef = settings.BranchRef

Scaling = collections.namedtuple("Scaling", ["load_mw", "gen_mw", "basis"])
CityMapping = collections.namedtuple(
    "CityMapping", ["city", "branches", "sink_buses", "transfer_max_mw", "scaling"]
)
Mapping = collections.namedtuple(
    "Mapping", ["schema_version", "placeholder", "note", "cities", "settings", "sha256"]
)

_TOP_KEYS = ("schema_version", "placeholder", "note", "cities", "study")
_CITY_KEYS = ("branches", "sink_buses", "transfer_max_mw", "scaling")
_BRANCH_KEYS = ("from_bus", "to_bus", "ckt")
_SCALING_KEYS = ("load_mw", "gen_mw", "basis")


class MappingError(ValueError):
    """The mapping file is unusable; `.problems` lists every problem found."""

    def __init__(self, problems):
        self.problems = list(problems)
        ValueError.__init__(self, "; ".join(self.problems))


def _short(key):
    """A key cut to 40 characters for a message (a mapping key is untrusted text)."""
    text = str(key)
    return repr(text if len(text) <= 40 else text[:40] + "...")


def _refuse_constant(name):
    raise ValueError("%s is not allowed in a mapping file" % name)


def _parse_json(text):
    """The parsed object; ValueError (with the problem text) for bad JSON, a duplicate key, NaN."""
    duplicates = []

    def pairs_hook(pairs):
        seen = {}
        for key, value in pairs:
            if key in seen:
                duplicates.append(key)
            seen[key] = value
        return seen

    parsed = json.loads(text, object_pairs_hook=pairs_hook, parse_constant=_refuse_constant)
    return parsed, duplicates


def _parse_branch(raw, where, problems):
    if not isinstance(raw, dict):
        problems.append("%s: must be an object" % where)
        return None
    for key in sorted(raw):
        if key not in _BRANCH_KEYS:
            problems.append("%s.%s: unknown key" % (where, _short(key)[1:-1]))
    missing = False
    for key in _BRANCH_KEYS:
        if key not in raw:
            problems.append("%s.%s: missing" % (where, key))
            missing = True
    if missing:
        return None
    count = len(problems)
    from_bus = settings.check_bus(raw["from_bus"], where + ".from_bus", problems)
    to_bus = settings.check_bus(raw["to_bus"], where + ".to_bus", problems)
    ckt = settings.check_ckt(raw["ckt"], where + ".ckt", problems)
    if from_bus is not None and to_bus is not None and from_bus == to_bus:
        problems.append("%s: from_bus and to_bus must differ" % where)
    if len(problems) > count:
        return None
    return BranchRef(from_bus, to_bus, ckt)


def _positive_finite(value):
    """True for a real number (not a bool) that is finite and above 0; never raises."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value) and value > 0
    except OverflowError:
        return False


def _parse_scaling(raw, where, problems):
    """
    The Scaling parsed from a city's `scaling` object, or None with every problem appended.
    A message names the field, never the submitted value (a target is not for logs).
    """
    if not isinstance(raw, dict):
        problems.append("%s: must be an object" % where)
        return None
    count = len(problems)
    for key in sorted(raw):
        if key not in _SCALING_KEYS:
            problems.append("%s.%s: unknown key" % (where, _short(key)[1:-1]))
    for key in _SCALING_KEYS:
        if key not in raw:
            problems.append("%s.%s: missing" % (where, key))
    targets = {}
    for key in ("load_mw", "gen_mw"):
        if key not in raw:
            continue
        if _positive_finite(raw[key]):
            targets[key] = float(raw[key])
        else:
            problems.append("%s.%s: must be a finite number greater than 0" % (where, key))
    basis = raw.get("basis")
    if "basis" in raw and (not isinstance(basis, str) or basis not in SCALING_BASES):
        problems.append("%s.basis: must be one of %s" % (where, ", ".join(SCALING_BASES)))
    if len(problems) > count:
        return None
    return Scaling(targets["load_mw"], targets["gen_mw"], basis)


def _parse_city(city, raw, problems):
    where = "cities.%s" % city
    if not isinstance(raw, dict):
        problems.append("%s: must be an object" % where)
        return None
    # The same line may be listed under several cities, because each city is solved on its own
    # copy of the case (CD-6); only a repeat within this one city is refused.
    seen = {}
    for key in sorted(raw):
        if key not in _CITY_KEYS:
            problems.append("%s.%s: unknown key" % (where, _short(key)[1:-1]))
    branches = []
    raw_branches = raw.get("branches")
    if "branches" not in raw:
        problems.append("%s.branches: missing" % where)
    elif not isinstance(raw_branches, list) or not (
        1 <= len(raw_branches) <= MAX_BRANCHES_PER_CITY
    ):
        problems.append(
            "%s.branches: must be a list of 1 to %d branches" % (where, MAX_BRANCHES_PER_CITY)
        )
    else:
        for index, item in enumerate(raw_branches):
            branch = _parse_branch(item, "%s.branches[%d]" % (where, index), problems)
            if branch is None:
                continue
            normal = branch.normalised()
            if normal in seen:
                problems.append(
                    "%s.branches[%d]: branch %s is listed twice in this city"
                    % (where, index, branch.key)
                )
                continue
            seen[normal] = index
            branches.append(branch)

    sink_buses = None
    if "sink_buses" in raw:
        raw_sinks = raw["sink_buses"]
        if not isinstance(raw_sinks, list) or not (1 <= len(raw_sinks) <= MAX_SINK_BUSES):
            problems.append(
                "%s.sink_buses: must be a list of 1 to %d bus numbers" % (where, MAX_SINK_BUSES)
            )
        else:
            sinks = []
            for index, item in enumerate(raw_sinks):
                bus = settings.check_bus(item, "%s.sink_buses[%d]" % (where, index), problems)
                if bus is None:
                    continue
                if bus in sinks:
                    problems.append("%s.sink_buses[%d]: bus %d is listed twice" % (where, index, bus))
                    continue
                sinks.append(bus)
            if len(sinks) == len(raw_sinks):
                sink_buses = tuple(sinks)

    transfer_max_mw = None
    if "transfer_max_mw" in raw:
        value = raw["transfer_max_mw"]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            problems.append("%s.transfer_max_mw: must be a finite number greater than 0" % where)
        else:
            transfer_max_mw = float(value)

    scaling = None
    if "scaling" not in raw:
        problems.append("%s.scaling: missing" % where)
    else:
        scaling = _parse_scaling(raw["scaling"], "%s.scaling" % where, problems)

    if scaling is None:
        return None
    if not branches or len(branches) != len(raw_branches or []):
        return None
    if sink_buses is None and "sink_buses" not in raw:
        sink_buses = (branches[0].to_bus,)
    if sink_buses is None:
        return None
    return CityMapping(city, tuple(branches), sink_buses, transfer_max_mw, scaling)


def _fail(problems):
    raise MappingError(problems[:MAX_PROBLEMS])


def parse_mapping(data, allow_placeholder=False):
    """
    The Mapping parsed from the bytes `data`, carrying the sha256 of exactly those bytes.
    MappingError (naming every problem at once) for an invalid file, and for a placeholder
    file unless `allow_placeholder` is True.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise MappingError(["mapping data must be bytes"])
    data = bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise MappingError(["mapping file is not UTF-8 text"])
    try:
        parsed, duplicates = _parse_json(text)
    except ValueError as error:
        raise MappingError(["mapping file is not valid JSON (%s)" % error])
    if not isinstance(parsed, dict):
        raise MappingError(["mapping file must hold a JSON object"])

    problems = ["duplicate key %s in the mapping file" % _short(key) for key in duplicates]
    for key in sorted(parsed):
        if key not in _TOP_KEYS:
            problems.append("%s: unknown key" % _short(key))

    version = parsed.get("schema_version")
    if "schema_version" not in parsed:
        problems.append("schema_version: missing")
    elif isinstance(version, bool) or version != SCHEMA_VERSION or not isinstance(version, int):
        problems.append(
            "schema_version: must be the integer %d (version 2 adds the per-city scaling block)"
            % SCHEMA_VERSION
        )

    placeholder = parsed.get("placeholder", False)
    if not isinstance(placeholder, bool):
        problems.append("placeholder: must be true or false")
        placeholder = False

    note = parsed.get("note")
    if "note" in parsed and (not isinstance(note, str) or len(note) > NOTE_MAX_CHARS):
        problems.append("note: must be text of at most %d characters" % NOTE_MAX_CHARS)
        note = None

    cities = {}
    raw_cities = parsed.get("cities")
    if "cities" not in parsed:
        problems.append("cities: missing")
    elif not isinstance(raw_cities, dict):
        problems.append("cities: must be an object")
    else:
        for city in constants.CITIES:
            if city not in raw_cities:
                problems.append("cities.%s: missing" % city)
        for city in sorted(raw_cities):
            if city not in constants.CITIES:
                problems.append(
                    "cities.%s: unknown city (expected %s)"
                    % (_short(city)[1:-1], ", ".join(constants.CITIES))
                )
        for city in constants.CITIES:
            if city in raw_cities:
                parsed_city = _parse_city(city, raw_cities[city], problems)
                if parsed_city is not None:
                    cities[city] = parsed_city

    study = settings.DEFAULT_SETTINGS
    try:
        study = settings.parse_settings(parsed.get("study"))
    except settings.SettingsError as error:
        problems.extend("study: %s" % problem for problem in error.problems)

    if problems:
        _fail(problems)
    if placeholder and not allow_placeholder:
        raise MappingError([
            "mapping file is marked placeholder; refusing it for a study "
            "(allow_placeholder is for tests and a plumbing smoke run only)"
        ])
    ordered = collections.OrderedDict((city, cities[city]) for city in constants.CITIES)
    return Mapping(version, placeholder, note, dict(ordered), study, digest)


def load_mapping(path, allow_placeholder=False):
    """
    Read and parse the mapping file at `path` (binary, at most MAX_MAPPING_BYTES): the Mapping
    with the sha256 of the bytes parsed. MappingError for an unreadable, oversized or invalid
    file; messages name the file's base name only, never its directory.
    """
    label = run_record.case_label(path)
    try:
        with open(path, "rb") as handle:
            data = handle.read(MAX_MAPPING_BYTES + 1)
    except OSError as error:
        raise MappingError(["mapping file %s could not be read (%s)" % (label, type(error).__name__)])
    if len(data) > MAX_MAPPING_BYTES:
        raise MappingError(["mapping file %s is larger than %d bytes" % (label, MAX_MAPPING_BYTES)])
    return parse_mapping(data, allow_placeholder=allow_placeholder)
