"""
The parity report between a built pandapower network and the parsed PSS/E export
(pandapower-solver Phase 1, plan 01-07: NET-02).

`parity_report(case, net)` reads the pandapower tables back into the export's own units and
compares them with the parsed records element by element, in the eleven categories of
`PARITY_CATEGORIES`. Every difference is returned as data (category, element key, quantity, expected
from the export, got from the network); `ParityReport.render_counts()` is the only text form meant
for a public summary and holds category counts and pass or fail, never an element key or a value.

What it proves, and what it does not (`PARITY_SCOPE_NOTE`). This report proves transcription
fidelity only. It is not circular in the narrow sense: the read-back below is written separately
from the builder and imports nothing from `network.py`, so a slip in one place (a wrong factor, a
swapped field, a dropped element, a mis-classified branch) shows as a difference. But the author of
both reads the same conventions, so a shared misunderstanding of a PSS/E convention (research
Pattern 6, Pitfall 5; assumptions A2 and A4) passes both. NET-03, the base-case load flow against
PSS/E's own numbers, is the independent check.

Read-back (each formula is the inverse of what a pandapower element means physically, not a copy of
the builder's code):

- line: R, X in ohms per km times length, divided by parallel circuits, over the from bus's base
  impedance `kV**2 / system MVA`; B from nF per km times length and parallel circuits, at the net's
  own frequency and that base impedance; rating from `max_i_ka` times the derating factor and
  parallel circuits, times root three and the from bus's kV.
- transformer: vk and vkr percent on the transformer's own MVA, moved to the system base, give
  Z and R, and X is what is left of Z squared after R squared; the ratio is the rated voltage over
  the bus voltage on each side, with any tap step applied on the tapped side; parallel units divide
  the impedance.
- shunt: BL is minus the reactive power times the step, brought from the shunt's rated kV to its
  bus's kV (it scales with voltage squared).
- load and machine values are read straight; the swing machine is the ext_grid row.

Transformer ratings (RATA1) are not carried into the network by the builder, so no transformer
rating is compared; the rating category covers lines only.

Pure and read-only: no table of the net is assigned to or changed, no module-level state is kept,
and two calls on the same inputs give equal reports.
"""

import collections
import math

from pandapower_job import raw

PARITY_CATEGORIES = (
    "counts", "classification", "names", "in_service", "impedance", "rating", "voltage_limits",
    "setpoints", "machine_limits", "loads", "shunts")

PARITY_RELATIVE_TOLERANCE = 1e-9
PARITY_ABSOLUTE_FLOOR = 1e-12
D06_RELATIVE_THRESHOLD = 1e-6

PARITY_SCOPE_NOTE = (
    "Parity proves transcription fidelity only (the network reads back to the export); it cannot "
    "show that a PSS/E convention was understood, and NET-03 against PSS/E's own numbers is the "
    "independent check.")

OUT_OF_SERVICE_IDE = 4
SWING_IDE = 3

# Export limit name to the pandapower column it reads back from: a gen row holds its limits in the
# standard columns; the swing machine's ext_grid row carries them in the psse_ columns.
_GEN_LIMITS = (("QT", "max_q_mvar"), ("QB", "min_q_mvar"), ("PT", "max_p_mw"), ("PB", "min_p_mw"))
_EXT_LIMITS = (("QT", "psse_qt_mvar"), ("QB", "psse_qb_mvar"), ("PT", "psse_pt_mw"),
               ("PB", "psse_pb_mw"))

Difference = collections.namedtuple(
    "Difference", ["category", "element", "quantity", "expected", "got"])

_REPORT_FIELDS = ["differences", "compared", "elements"]


class ParityReport(collections.namedtuple("ParityReport", _REPORT_FIELDS)):
    """
    `differences`: sorted tuple of Difference. `compared`: category to the number of comparisons
    made. `elements`: category to the number of elements it applies to on either side. Equal inputs
    give equal reports (a namedtuple compares by value).
    """

    __slots__ = ()

    @property
    def passed(self):
        """
        True only when there is no difference, at least one comparison was made, and every
        category with elements on either side made at least one comparison: a category that could
        not be compared is never reported as a pass.
        """
        if self.differences:
            return False
        if sum(self.compared.values()) < 1:
            return False
        return all(self.compared.get(category, 0) >= 1 for category in PARITY_CATEGORIES
                   if self.elements.get(category, 0) > 0)

    def category_counts(self):
        """Category to (comparisons made, differences found), in PARITY_CATEGORIES order."""
        found = collections.Counter(item.category for item in self.differences)
        return collections.OrderedDict(
            (category, (self.compared.get(category, 0), found.get(category, 0)))
            for category in PARITY_CATEGORIES)

    def render_counts(self):
        """Scope note, one count line per category and the verdict; no key and no value."""
        lines = [PARITY_SCOPE_NOTE]
        uncompared = []
        for category, (made, differing) in self.category_counts().items():
            lines.append("%s: %d compared, %d differing" % (category, made, differing))
            if self.elements.get(category, 0) > 0 and made < 1:
                uncompared.append(category)
        if self.passed:
            lines.append("parity: pass")
        else:
            lines.append("parity: fail (%d difference(s), %d category(ies) not compared)"
                         % (len(self.differences), len(uncompared)))
        return "\n".join(lines)


# -- comparison ---------------------------------------------------------------------------------


def _number(value):
    """`value` as a float, or None when it is missing or not a number."""
    if value is None or isinstance(value, str):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _differs(expected, got, relative=None):
    """
    True when `got` is not `expected`. Numbers differ when `abs(got - expected)` exceeds the larger
    of the relative tolerance (`relative`, default PARITY_RELATIVE_TOLERANCE) times `abs(expected)`
    and the absolute floor (so a difference exactly at the tolerance passes); a missing,
    non-numeric or non-finite value always differs, and text is compared exactly. The module
    constants are read at call time.
    """
    if expected is None or got is None:
        return expected is not got
    if isinstance(expected, str) or isinstance(got, str):
        return expected != got
    want, have = _number(expected), _number(got)
    if want is None or have is None or not math.isfinite(want) or not math.isfinite(have):
        return True
    if relative is None:
        relative = PARITY_RELATIVE_TOLERANCE
    return not abs(have - want) <= max(relative * abs(want), PARITY_ABSOLUTE_FLOOR)


class _Recorder(object):
    """Collects comparisons and differences; the only mutable object of a report run."""

    def __init__(self):
        self.differences = []
        self.compared = collections.OrderedDict((name, 0) for name in PARITY_CATEGORIES)
        self.elements = collections.OrderedDict((name, 0) for name in PARITY_CATEGORIES)

    def apply_to(self, categories, count=1):
        for name in categories:
            self.elements[name] += count

    def check(self, category, element, quantity, expected, got):
        self.compared[category] += 1
        if _differs(expected, got):
            self.differences.append(Difference(category, element, quantity, expected, got))

    def finish(self):
        order = {name: position for position, name in enumerate(PARITY_CATEGORIES)}
        ordered = sorted(
            self.differences,
            key=lambda d: (order[d.category], str(d.element), d.quantity, repr(d.expected),
                           repr(d.got)))
        return ParityReport(tuple(ordered), dict(self.compared), dict(self.elements))


def _rows(table):
    """[(index, row dict)] of a pandapower table, without touching it."""
    return list(zip(table.index, table.to_dict("records")))


def _flag(row):
    value = row.get("in_service")
    return None if value is None else int(bool(value))


def _scaled(row, column):
    """`row[column]` times the element's `scaling` factor (1 when the table has none)."""
    base = _number(row.get(column))
    factor = _number(row.get("scaling", 1.0))
    if base is None or factor is None:
        return None
    return base * factor


def _check_presence(rec, family_keys_expected, family_keys_got):
    """
    The `names` comparisons of one family: every key of either side is one comparison and a key on
    one side only is a difference. Returns (sorted keys on both sides, sorted union of keys).
    """
    union = sorted(set(family_keys_expected) | set(family_keys_got))
    matched = []
    for key in union:
        in_export, in_net = key in family_keys_expected, key in family_keys_got
        rec.compared["names"] += 1
        if in_export and in_net:
            matched.append(key)
        elif in_export:
            rec.differences.append(Difference("names", key, "missing", "present", "absent"))
        else:
            rec.differences.append(Difference("names", key, "extra", "absent", "present"))
    return matched, union


# -- the report ---------------------------------------------------------------------------------


def _buses(case, net, rec, bus_kv):
    exported = {rec_.values["I"]: rec_.values for rec_ in case.sections["bus"]}
    built = {int(index): row for index, row in _rows(net.bus)}
    rec.check("counts", "buses", "count", len(case.sections["bus"]), len(net.bus))
    matched, union = _check_presence(rec, {str(n) for n in exported}, {str(n) for n in built})
    rec.apply_to(("names", "in_service", "voltage_limits"), len(union))
    for text in matched:
        number = int(text)
        values, row = exported[number], built[number]
        rec.check("names", text, "name", str(number), str(row.get("name")))
        rec.check("voltage_limits", text, "BASKV", values["BASKV"], _number(row.get("vn_kv")))
        rec.check("voltage_limits", text, "NVHI", values["NVHI"], _number(row.get("max_vm_pu")))
        rec.check("voltage_limits", text, "NVLO", values["NVLO"], _number(row.get("min_vm_pu")))
        rec.check("in_service", text, "IDE", int(values["IDE"] != OUT_OF_SERVICE_IDE),
                  _flag(row))
    return exported


def _branches(case, net, rec, bus_kv):
    sbase = case.sbase_mva
    exported = {}
    for kind, section in (("line", "branch"), ("transformer", "transformer")):
        for item in case.sections[section]:
            exported[raw.branch_key(item.values["I"], item.values["J"], item.values["CKT"])] = (
                kind, item.values)
    built = {}
    for kind, table in (("line", net.line), ("transformer", net.trafo)):
        for _, row in _rows(table):
            built.setdefault(str(row.get("name")), []).append((kind, row))
    rec.check("counts", "branches",
              "count", len(case.sections["branch"]) + len(case.sections["transformer"]),
              len(net.line) + len(net.trafo))
    matched, union = _check_presence(rec, set(exported), set(built))
    rec.apply_to(("names", "classification", "in_service", "impedance"), len(union))
    rec.apply_to(("rating",), sum(
        1 for key in union
        if (key in exported and exported[key][0] == "line")
        or any(kind == "line" for kind, _ in built.get(key, ()))))
    for key in matched:
        kind, values = exported[key]
        if len(built[key]) > 1:
            rec.check("names", key, "duplicate", 1, len(built[key]))
            continue
        got_kind, row = built[key][0]
        rec.check("classification", key, "kind", kind, got_kind)
        if got_kind != kind:
            continue
        if kind == "line":
            _line(rec, key, values, row, sbase, net.f_hz, bus_kv)
        else:
            _transformer(rec, key, values, row, sbase, bus_kv)


def _read_line(row, sbase, frequency, bus_kv):
    """R, X, B (per unit on the system base) and RATEA (MVA) of a pandapower line row."""
    got = {"R": None, "X": None, "B": None, "RATEA": None}
    from_bus = row.get("from_bus")
    kv = bus_kv.get(None if from_bus is None else int(from_bus))
    length, parallel = _number(row.get("length_km")), _number(row.get("parallel", 1.0))
    if kv is None or length is None or parallel is None or parallel <= 0.0 or kv <= 0.0:
        return got
    base_z = kv * kv / sbase
    for name, column in (("R", "r_ohm_per_km"), ("X", "x_ohm_per_km")):
        ohm = _number(row.get(column))
        if ohm is not None:
            got[name] = ohm * length / parallel / base_z
    farad = _number(row.get("c_nf_per_km"))
    if farad is not None and frequency is not None:
        got["B"] = farad * 1e-9 * 2.0 * math.pi * frequency * length * parallel * base_z
    amps, derate = _number(row.get("max_i_ka")), _number(row.get("df", 1.0))
    if amps is not None and derate is not None:
        got["RATEA"] = amps * derate * parallel * math.sqrt(3.0) * kv
    return got


def _line(rec, key, values, row, sbase, frequency, bus_kv):
    rec.check("names", key, "from_bus", values["I"], _number(row.get("from_bus")))
    rec.check("names", key, "to_bus", values["J"], _number(row.get("to_bus")))
    got = _read_line(row, sbase, frequency, bus_kv)
    for name in ("R", "X", "B"):
        rec.check("impedance", key, name, values[name], got[name])
    rec.check("rating", key, "RATEA", values["RATEA"], got["RATEA"])
    rec.check("in_service", key, "ST", int(values["ST"] == 1), _flag(row))


def _tap_factor(row, side):
    """The voltage factor of the tap step on `side` ("hv" or "lv"); 1 when the tap is not set."""
    if str(row.get("tap_side")).lower() != side:
        return 1.0
    position, neutral = _number(row.get("tap_pos")), _number(row.get("tap_neutral"))
    step = _number(row.get("tap_step_percent"))
    if None in (position, neutral, step) or not all(
            math.isfinite(item) for item in (position, neutral, step)):
        return 1.0
    return 1.0 + (position - neutral) * step / 100.0


def _read_transformer(row, sbase, bus_kv):
    """R1-2, X1-2 (per unit on the system base), the winding-1 ratio and ANG1 of a trafo row."""
    got = {"R1-2": None, "X1-2": None, "WINDV1": None, "ANG1": _number(row.get("shift_degree"))}
    hv, lv = row.get("hv_bus"), row.get("lv_bus")
    kv_hv = bus_kv.get(None if hv is None else int(hv))
    kv_lv = bus_kv.get(None if lv is None else int(lv))
    sn, parallel = _number(row.get("sn_mva")), _number(row.get("parallel", 1.0))
    vk, vkr = _number(row.get("vk_percent")), _number(row.get("vkr_percent"))
    if None not in (sn, parallel, vk, vkr) and sn > 0.0 and parallel > 0.0:
        scale = sbase / sn / parallel
        r = vkr / 100.0 * scale
        z = vk / 100.0 * scale
        got["R1-2"] = r
        got["X1-2"] = math.sqrt(max((z - r) * (z + r), 0.0))
    rated_hv, rated_lv = _number(row.get("vn_hv_kv")), _number(row.get("vn_lv_kv"))
    if None not in (rated_hv, rated_lv, kv_hv, kv_lv) and kv_hv > 0.0 and kv_lv > 0.0:
        low = rated_lv * _tap_factor(row, "lv") / kv_lv
        if low > 0.0:
            got["WINDV1"] = (rated_hv * _tap_factor(row, "hv") / kv_hv) / low
    return got


def _transformer(rec, key, values, row, sbase, bus_kv):
    rec.check("names", key, "from_bus", values["I"], _number(row.get("hv_bus")))
    rec.check("names", key, "to_bus", values["J"], _number(row.get("lv_bus")))
    got = _read_transformer(row, sbase, bus_kv)
    rec.check("impedance", key, "R1-2", values["R1-2"], got["R1-2"])
    rec.check("impedance", key, "X1-2", values["X1-2"], got["X1-2"])
    rec.check("impedance", key, "WINDV1", values["WINDV1"] / values["WINDV2"], got["WINDV1"])
    rec.check("impedance", key, "ANG1", values["ANG1"], got["ANG1"])
    rec.check("in_service", key, "STAT", int(values["STAT"] == 1), _flag(row))


def _loads(case, net, rec, bus_kv):
    exported = {"%d-%s" % (item.values["I"], item.values["ID"]): item.values
                for item in case.sections["load"]}
    built = {}
    for _, row in _rows(net.load):
        built.setdefault(str(row.get("name")), []).append(row)
    rec.check("counts", "loads", "count", len(case.sections["load"]), len(net.load))
    matched, union = _check_presence(rec, set(exported), set(built))
    rec.apply_to(("names", "in_service", "loads"), len(union))
    for key in matched:
        if len(built[key]) > 1:
            rec.check("names", key, "duplicate", 1, len(built[key]))
            continue
        values, row = exported[key], built[key][0]
        rec.check("names", key, "bus", values["I"], _number(row.get("bus")))
        rec.check("loads", key, "PL", values["PL"], _scaled(row, "p_mw"))
        rec.check("loads", key, "QL", values["QL"], _scaled(row, "q_mvar"))
        rec.check("in_service", key, "STATUS", int(values["STATUS"] == 1), _flag(row))


def _shunts(case, net, rec, bus_kv):
    exported = {"%d-%s" % (item.values["I"], item.values["ID"]): item.values
                for item in case.sections["fixed_shunt"]}
    # A switched shunt is built as a shunt at its initial setting (assumption A-shunt in
    # network.py), named bus-sw: the export side is GL 0 and BL = BINIT, so its quantities are
    # compared like a fixed shunt's.
    for item in case.sections["switched_shunt"]:
        exported["%d-sw" % item.values["I"]] = {
            "I": item.values["I"], "GL": 0.0, "BL": item.values["BINIT"],
            "STATUS": item.values["STAT"]}
    built = {}
    for _, row in _rows(net.shunt):
        built.setdefault(str(row.get("name")), []).append(row)
    rec.check("counts", "shunts", "count", len(exported), len(net.shunt))
    matched, union = _check_presence(rec, set(exported), set(built))
    rec.apply_to(("names", "in_service", "shunts"), len(union))
    for key in matched:
        if len(built[key]) > 1:
            rec.check("names", key, "duplicate", 1, len(built[key]))
            continue
        values, row = exported[key], built[key][0]
        bus = row.get("bus")
        rec.check("names", key, "bus", values["I"], _number(bus))
        kv = bus_kv.get(None if bus is None else int(bus))
        rated, step = _number(row.get("vn_kv")), _number(row.get("step", 1.0))
        factor = None
        if None not in (kv, rated, step) and kv > 0.0:
            factor = step * (rated / kv) ** 2
        p, q = _number(row.get("p_mw")), _number(row.get("q_mvar"))
        rec.check("shunts", key, "GL", values["GL"], None if None in (p, factor) else p * factor)
        rec.check("shunts", key, "BL", values["BL"], None if None in (q, factor) else -q * factor)
        rec.check("in_service", key, "STATUS", int(values["STATUS"] == 1), _flag(row))


def _machines(case, net, rec, exported_buses):
    exported, kinds = {}, {}
    for item in case.sections["generator"]:
        key = "%d-%s" % (item.values["I"], item.values["ID"])
        exported[key] = item.values
        bus = exported_buses.get(item.values["I"])
        swing = bus is not None and bus["IDE"] == SWING_IDE and item.values["STAT"] == 1
        kinds[key] = "ext_grid" if swing else "gen"
    built = {}
    for kind, table in (("gen", net.gen), ("ext_grid", net.ext_grid)):
        for _, row in _rows(table):
            built.setdefault(str(row.get("name")), []).append((kind, row))
    rec.check("counts", "machines", "count", len(case.sections["generator"]),
              len(net.gen) + len(net.ext_grid))
    matched, union = _check_presence(rec, set(exported), set(built))
    rec.apply_to(("names", "classification", "in_service", "setpoints", "machine_limits"),
                 len(union))
    for key in matched:
        if len(built[key]) > 1:
            rec.check("names", key, "duplicate", 1, len(built[key]))
            continue
        values = exported[key]
        got_kind, row = built[key][0]
        rec.check("classification", key, "kind", kinds[key], got_kind)
        if got_kind != kinds[key]:
            continue
        rec.check("names", key, "bus", values["I"], _number(row.get("bus")))
        rec.check("in_service", key, "STAT", int(values["STAT"] == 1), _flag(row))
        rec.check("setpoints", key, "VS", values["VS"], _number(row.get("vm_pu")))
        if got_kind == "gen":
            rec.check("setpoints", key, "PG", values["PG"], _scaled(row, "p_mw"))
            limits = _GEN_LIMITS
        else:
            bus = exported_buses.get(values["I"])
            rec.check("setpoints", key, "VA", None if bus is None else bus["VA"],
                      _number(row.get("va_degree")))
            rec.check("setpoints", key, "PG", values["PG"], _number(row.get("psse_pg_mw")))
            rec.check("setpoints", key, "QG", values["QG"], _number(row.get("psse_qg_mvar")))
            limits = _EXT_LIMITS
        for name, column in limits:
            rec.check("machine_limits", key, name, values[name], _number(row.get(column)))


def parity_report(case, net):
    """
    The `ParityReport` of a built network against the parsed export (see the module docstring).
    Reads `net` and `case` only.
    """
    rec = _Recorder()
    bus_kv = {}
    for index, row in _rows(net.bus):
        number = _number(row.get("vn_kv"))
        if number is not None and math.isfinite(number):
            bus_kv[int(index)] = number
    rec.elements["counts"] = 5
    exported_buses = _buses(case, net, rec, bus_kv)
    _branches(case, net, rec, bus_kv)
    _loads(case, net, rec, bus_kv)
    _machines(case, net, rec, exported_buses)
    _shunts(case, net, rec, bus_kv)
    rec.check("impedance", "system", "SBASE", case.sbase_mva, _number(net.sn_mva))
    rec.check("impedance", "system", "BASFRQ", case.base_frequency_hz, _number(net.f_hz))
    return rec.finish()


# -- evidence for decision D-06 -------------------------------------------------------------------

EVIDENCE_CATEGORIES = (
    "impedance", "rating", "voltage_limits", "setpoints", "machine_limits", "loads", "shunts")

_EVIDENCE_FIELDS = ["element_counts", "classification_differences", "unmatched_buses",
                    "differing_beyond", "threshold"]


class EvidenceReport(collections.namedtuple("EvidenceReport", _EVIDENCE_FIELDS)):
    """
    Counts only. `element_counts` maps "export", "reference" and "matched" to per-family counts;
    `classification_differences` and `unmatched_buses` are numbers; `differing_beyond` maps each of
    EVIDENCE_CATEGORIES to the number of matched elements differing beyond `threshold` relative.
    """

    __slots__ = ()

    def render_counts(self):
        """Text with counts only, headed by the statement that it decides nothing."""
        lines = ["Evidence for the owner's decision on the network copy (D-06); it decides "
                 "nothing and gates nothing."]
        counts = self.element_counts
        for family in ("buses", "lines", "transformers", "loads", "machines", "shunts"):
            text = "%s: %d in the export, %d in the public case" % (
                family, counts["export"][family], counts["reference"][family])
            if family in counts["matched"]:
                text += ", %d matched" % counts["matched"][family]
            lines.append(text)
        lines.append("branches matched by bus pair: %d" % counts["matched"]["branches"])
        lines.append("unmatched buses: %d" % self.unmatched_buses)
        lines.append("classification differences: %d" % self.classification_differences)
        for category in EVIDENCE_CATEGORIES:
            lines.append("elements differing beyond %g relative, %s: %d" % (
                self.threshold, category, self.differing_beyond[category]))
        return "\n".join(lines)


def _matpower_numbers(net):
    """Reference bus index to its MATPOWER number (the bus name when numeric, else index + 1)."""
    numbers = {}
    for index, row in _rows(net.bus):
        name = str(row.get("name")).strip()
        numbers[int(index)] = int(name) if name.isdigit() else int(index) + 1
    return numbers


def _beyond(pairs, threshold):
    """True when any (expected, got) pair of `pairs` differs by more than `threshold` relative."""
    return any(_differs(expected, got, threshold) for expected, got in pairs)


def _grouped(items, key):
    grouped = {}
    for item in items:
        grouped.setdefault(key(item), []).append(item)
    return grouped


def _evidence_branches(case, net, number_of, bus_kv, beyond, threshold):
    """(matched branch count, classification differences); fills the impedance and rating counts."""
    exported = {}
    for kind, section in (("line", "branch"), ("transformer", "transformer")):
        for item in case.sections[section]:
            pair = frozenset((item.values["I"], item.values["J"]))
            exported.setdefault(pair, []).append((str(item.values["CKT"]), kind, item.values))
    reference = {}
    for kind, table, ends in (("line", net.line, ("from_bus", "to_bus")),
                              ("transformer", net.trafo, ("hv_bus", "lv_bus"))):
        for _, row in _rows(table):
            pair = frozenset(number_of.get(int(row[end])) for end in ends)
            reference.setdefault(pair, []).append((kind, row))
    classification = matched = 0
    for pair, items in exported.items():
        items.sort(key=lambda entry: (entry[0], entry[1]))
        for (_, kind, values), (got_kind, row) in zip(items, reference.get(pair, ())):
            matched += 1
            if kind != got_kind:
                classification += 1
            elif kind == "line":
                got = _read_line(row, case.sbase_mva, net.f_hz, bus_kv)
                if _beyond([(values[name], got[name]) for name in ("R", "X", "B")], threshold):
                    beyond["impedance"] += 1
                if _beyond([(values["RATEA"], got["RATEA"])], threshold):
                    beyond["rating"] += 1
            else:
                got = _read_transformer(row, case.sbase_mva, bus_kv)
                if _beyond([(values["R1-2"], got["R1-2"]), (values["X1-2"], got["X1-2"]),
                            (values["WINDV1"] / values["WINDV2"], got["WINDV1"]),
                            (values["ANG1"], got["ANG1"])], threshold):
                    beyond["impedance"] += 1
    return matched, classification


def case39_evidence(case, reference_net=None):
    """
    Counts-only evidence on how the parsed export differs from pandapower's public 39-bus case
    (`reference_net`, default `pandapower.networks.case39()`), for the owner's D-06 decision. It
    neither gates nor decides anything and never raises on a difference.

    Buses are matched by number (the public case's MATPOWER number); branches by their unordered
    bus pair and position within that pair (circuit order against table order, lines first);
    loads, machines and shunts by bus and position within the bus (export order by id, public case
    by table order). Matched elements are read back to the export's units with the same formulas
    as `parity_report` and counted once per category when any of their quantities differs by more
    than `D06_RELATIVE_THRESHOLD`. `unmatched_buses` is the number of export buses the public case
    lacks (public-case buses the export lacks are `reference buses - (export buses - unmatched)`).
    Elements with no counterpart appear in `element_counts` only. A branch pair whose kinds differ
    counts under `classification_differences` and is not compared further.
    """
    if reference_net is None:
        import pandapower.networks as networks   # evidence only: never used to build a network
        reference_net = networks.case39()
    net = reference_net
    threshold = D06_RELATIVE_THRESHOLD
    number_of = _matpower_numbers(net)
    bus_kv = {int(index): _number(row.get("vn_kv")) for index, row in _rows(net.bus)}
    reference_buses = {number_of[int(index)]: row for index, row in _rows(net.bus)}
    exported_buses = {item.values["I"]: item.values for item in case.sections["bus"]}
    beyond = {name: 0 for name in EVIDENCE_CATEGORIES}

    shared = sorted(set(exported_buses) & set(reference_buses))
    unmatched = len(set(exported_buses) - set(reference_buses))
    for number in shared:
        values, row = exported_buses[number], reference_buses[number]
        if _beyond([(values["BASKV"], _number(row.get("vn_kv"))),
                    (values["NVHI"], _number(row.get("max_vm_pu"))),
                    (values["NVLO"], _number(row.get("min_vm_pu")))], threshold):
            beyond["voltage_limits"] += 1
    matched_branches, classification = _evidence_branches(
        case, net, number_of, bus_kv, beyond, threshold)

    matched = {"buses": len(shared), "branches": matched_branches, "loads": 0, "machines": 0,
               "shunts": 0}
    def export_groups(section):
        """The export's records of `section` by bus, each bus's records ordered by id."""
        ordered = sorted(case.sections[section], key=lambda r: str(r.values["ID"]))
        return _grouped(ordered, lambda r: r.values["I"])

    def net_groups(entries, row_of):
        """Reference entries by MATPOWER bus number, in table order."""
        return _grouped(entries, lambda entry: number_of.get(int(row_of(entry)["bus"])))

    reference_loads = net_groups([row for _, row in _rows(net.load)], lambda row: row)
    for number, items in export_groups("load").items():
        for item, row in zip(items, reference_loads.get(number, ())):
            matched["loads"] += 1
            if _beyond([(item.values["PL"], _scaled(row, "p_mw")),
                        (item.values["QL"], _scaled(row, "q_mvar"))], threshold):
                beyond["loads"] += 1

    reference_shunts = net_groups([row for _, row in _rows(net.shunt)], lambda row: row)
    for number, items in export_groups("fixed_shunt").items():
        for item, row in zip(items, reference_shunts.get(number, ())):
            matched["shunts"] += 1
            rated, step = _number(row.get("vn_kv")), _number(row.get("step", 1.0))
            kv = bus_kv.get(int(row["bus"]))
            p, q = _number(row.get("p_mw")), _number(row.get("q_mvar"))
            factor = None
            if None not in (rated, step, kv) and kv > 0.0:
                factor = step * (rated / kv) ** 2
            if _beyond([(item.values["GL"], None if None in (p, factor) else p * factor),
                        (item.values["BL"], None if None in (q, factor) else -q * factor)],
                       threshold):
                beyond["shunts"] += 1

    reference_machines = net_groups(
        [(kind, row) for kind, table in (("gen", net.gen), ("ext_grid", net.ext_grid))
         for _, row in _rows(table)], lambda entry: entry[1])
    for number, items in export_groups("generator").items():
        for item, (kind, row) in zip(items, reference_machines.get(number, ())):
            matched["machines"] += 1
            values = item.values
            setpoints = [(values["VS"], _number(row.get("vm_pu")))]
            if kind == "gen":
                setpoints.append((values["PG"], _scaled(row, "p_mw")))
            if _beyond(setpoints, threshold):
                beyond["setpoints"] += 1
            if _beyond([(values[name], _number(row.get(column))) for name, column in _GEN_LIMITS],
                       threshold):
                beyond["machine_limits"] += 1

    counts = {
        "export": {
            "buses": len(case.sections["bus"]), "lines": len(case.sections["branch"]),
            "transformers": len(case.sections["transformer"]),
            "loads": len(case.sections["load"]), "machines": len(case.sections["generator"]),
            "shunts": len(case.sections["fixed_shunt"])},
        "reference": {
            "buses": len(net.bus), "lines": len(net.line), "transformers": len(net.trafo),
            "loads": len(net.load), "machines": len(net.gen) + len(net.ext_grid),
            "shunts": len(net.shunt)},
        "matched": matched}
    return EvidenceReport(counts, classification, unmatched, beyond, threshold)
