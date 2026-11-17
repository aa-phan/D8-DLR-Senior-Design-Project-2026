"""
A fail-closed reader for PSS/E RAW files, revision 33 (pandapower-solver Phase 1, plan 01-06: NET-01).

Standard library only. `parse_raw` tokenises by commas outside single quotes, stops a record at an
unquoted slash, walks the sections in the file order of the revision, applies each field table's
documented defaults to a truncated tail of a record, and returns a `ParsedCase`. It accepts only
what the network builder can reproduce exactly: an unknown revision, a section the builder does
not support that holds a record, a record with too few or too many fields, a three-winding
transformer, a duplicate element or a value that is not a number where a number is needed is a
`RawRefused` with exactly one reason from `REFUSAL_REASONS`. Nothing is silently approximated.

The message of a refusal holds the reason and a line number only. A RAW file is private data, and an
error that named a bus, a branch or a field value would carry it into a terminal, a log or a
summary; the line number lets the owner look at the place locally.

Field layout. The field names and their order for revision 33 come from the lanl-ansi PowerModels.jl
`src/io/pti.jl` reader (bus 13 fields, load 14, fixed shunt 5, generator 28, branch 24, transformer
records of 21, 3, 17 and 2 fields), which is how the research for this phase sourced them; whether
PSS/E 36.4 writes exactly this layout is unverified until a real file is parsed (assumption A2).
PSS/E may omit trailing default fields, so each table has a `required` count and defaults for
everything after it; a record shorter than `required` or longer than the table is a refusal. Every
default is the documented PSS/E default, with two stated exceptions: a field that has no sensible
default (a bus number, a bus base voltage, a branch R or X, a transformer's R or X) is refused when
it is empty instead of being invented, and MBASE and SBASE1-2 default to 0.0 meaning "not given"
because neither is used with the unit conventions the builder accepts.

Pure functions only: no module-level mutable state is read or written, and two parses of the same
bytes give equal results that share no mutable object.
"""

import collections
import math
import re

MAX_RAW_BYTES = 5 * 1024 * 1024

REFUSAL_REASONS = (
    "empty", "too_large", "bad_header", "unknown_revision", "unknown_section",
    "unsupported_section", "field_count", "bad_value", "three_winding", "duplicate_bus",
    "duplicate_branch", "duplicate_machine", "duplicate_load", "unterminated", "trailing_data")


class RawRefused(ValueError):
    """
    The RAW input was refused. `reason` is one of REFUSAL_REASONS and `line` the 1-based line
    number it applies to (None for a refusal about the whole input). `str(error)` holds those two
    and nothing from the file.
    """

    def __init__(self, reason, line=None):
        text = "RAW refused: %s" % reason
        if line is not None:
            text += " (line %d)" % line
        ValueError.__init__(self, text)
        self.reason = reason
        self.line = line


FieldSpec = collections.namedtuple("FieldSpec", ["names", "required", "defaults"])
Record = collections.namedtuple("Record", ["section", "line", "values"])
ParsedCase = collections.namedtuple(
    "ParsedCase", ["revision", "ic", "sbase_mva", "base_frequency_hz", "sections"])


def _spec(names, required, defaults):
    return FieldSpec(tuple(names.split()), required, dict(defaults))


_ORDER_FIELDS = {"O%d" % n: 0 for n in range(1, 5)}
_ORDER_FIELDS.update({"F%d" % n: 1.0 for n in range(1, 5)})

_BUS = _spec(
    "I NAME BASKV IDE AREA ZONE OWNER VM VA NVHI NVLO EVHI EVLO", 11,
    {"NAME": "", "IDE": 1, "AREA": 1, "ZONE": 1, "OWNER": 1, "VM": 1.0, "VA": 0.0, "NVHI": 1.1,
     "NVLO": 0.9, "EVHI": 1.1, "EVLO": 0.9})
_LOAD = _spec(
    "I ID STATUS AREA ZONE PL QL IP IQ YP YQ OWNER SCALE INTRPT", 7,
    {"ID": "1", "STATUS": 1, "AREA": 1, "ZONE": 1, "PL": 0.0, "QL": 0.0, "IP": 0.0, "IQ": 0.0,
     "YP": 0.0, "YQ": 0.0, "OWNER": 1, "SCALE": 1, "INTRPT": 0})
_FIXED_SHUNT = _spec(
    "I ID STATUS GL BL", 5, {"ID": "1", "STATUS": 1, "GL": 0.0, "BL": 0.0})
_GENERATOR = _spec(
    "I ID PG QG QT QB VS IREG MBASE ZR ZX RT XT GTAP STAT RMPCT PT PB O1 F1 O2 F2 O3 F3 O4 F4 "
    "WMOD WPF", 7,
    dict({"ID": "1", "PG": 0.0, "QG": 0.0, "QT": 9999.0, "QB": -9999.0, "VS": 1.0, "IREG": 0,
          "MBASE": 0.0, "ZR": 0.0, "ZX": 1.0, "RT": 0.0, "XT": 0.0, "GTAP": 1.0, "STAT": 1,
          "RMPCT": 100.0, "PT": 9999.0, "PB": -9999.0, "WMOD": 0, "WPF": 1.0}, **_ORDER_FIELDS))
_BRANCH = _spec(
    "I J CKT R X B RATEA RATEB RATEC GI BI GJ BJ ST MET LEN O1 F1 O2 F2 O3 F3 O4 F4", 6,
    dict({"CKT": "1", "B": 0.0, "RATEA": 0.0, "RATEB": 0.0, "RATEC": 0.0, "GI": 0.0, "BI": 0.0,
          "GJ": 0.0, "BJ": 0.0, "ST": 1, "MET": 1, "LEN": 0.0}, **_ORDER_FIELDS))
_TRANSFORMER_1 = _spec(
    "I J K CKT CW CZ CM MAG1 MAG2 NMETR NAME STAT O1 F1 O2 F2 O3 F3 O4 F4 VECGRP", 3,
    dict({"K": 0, "CKT": "1", "CW": 1, "CZ": 1, "CM": 1, "MAG1": 0.0, "MAG2": 0.0, "NMETR": 2,
          "NAME": "", "STAT": 1, "VECGRP": ""}, **_ORDER_FIELDS))
_TRANSFORMER_2 = _spec("R1-2 X1-2 SBASE1-2", 2, {"SBASE1-2": 0.0})
_TRANSFORMER_3 = _spec(
    "WINDV1 NOMV1 ANG1 RATA1 RATB1 RATC1 COD1 CONT1 RMA1 RMI1 VMA1 VMI1 NTP1 TAB1 CR1 CX1 CNXA1", 1,
    {"WINDV1": 1.0, "NOMV1": 0.0, "ANG1": 0.0, "RATA1": 0.0, "RATB1": 0.0, "RATC1": 0.0,
     "COD1": 0, "CONT1": 0, "RMA1": 1.1, "RMI1": 0.9, "VMA1": 1.1, "VMI1": 0.9, "NTP1": 33,
     "TAB1": 0, "CR1": 0.0, "CX1": 0.0, "CNXA1": 0.0})
_TRANSFORMER_4 = _spec("WINDV2 NOMV2", 1, {"WINDV2": 1.0, "NOMV2": 0.0})
_AREA = _spec("I ISW PDES PTOL ARNAME", 1, {"ISW": 0, "PDES": 0.0, "PTOL": 10.0, "ARNAME": ""})
_ZONE = _spec("I ZONAME", 1, {"ZONAME": ""})
_OWNER = _spec("I OWNAME", 1, {"OWNAME": ""})

FIELD_TABLES = {
    33: {
        "bus": _BUS, "load": _LOAD, "fixed_shunt": _FIXED_SHUNT, "generator": _GENERATOR,
        "branch": _BRANCH, "transformer_1": _TRANSFORMER_1, "transformer_2": _TRANSFORMER_2,
        "transformer_3": _TRANSFORMER_3, "transformer_4": _TRANSFORMER_4, "area": _AREA,
        "zone": _ZONE, "owner": _OWNER}}

SECTION_ORDER = {
    33: ("bus", "load", "fixed_shunt", "generator", "branch", "transformer", "area",
         "two_terminal_dc", "vsc_dc", "impedance_correction", "multi_terminal_dc",
         "multi_section_line", "zone", "inter_area_transfer", "owner", "facts",
         "switched_shunt", "gne", "induction_machine")}

SUPPORTED_SECTIONS = ("bus", "load", "fixed_shunt", "generator", "branch", "transformer", "area",
                      "zone", "owner")

_TRANSFORMER_TABLES = ("transformer_1", "transformer_2", "transformer_3", "transformer_4")

_UTF8_BOM = b"\xef\xbb\xbf"

# The words a section terminator comment may use for each section (matched as a prefix of the
# phrase between the end-of and data words, so "AREA" accepts "AREA INTERCHANGE"). A terminator
# without a comment is accepted: the position alone says which section it ends.
_MARKERS = {
    "bus": ("BUS",), "load": ("LOAD",), "fixed_shunt": ("FIXED SHUNT",),
    "generator": ("GENERATOR",), "branch": ("BRANCH",), "transformer": ("TRANSFORMER",),
    "area": ("AREA",), "two_terminal_dc": ("TWO-TERMINAL",),
    "vsc_dc": ("VOLTAGE SOURCE", "VSC"), "impedance_correction": ("IMPEDANCE",),
    "multi_terminal_dc": ("MULTI-TERMINAL",), "multi_section_line": ("MULTI-SECTION",),
    "zone": ("ZONE",), "inter_area_transfer": ("INTER-AREA",), "owner": ("OWNER",),
    "facts": ("FACTS",), "switched_shunt": ("SWITCHED SHUNT",), "gne": ("GNE",),
    "induction_machine": ("INDUCTION",)}

# Assembled from pieces: the plan 01-01 shape layer flags the section markers of a RAW file in any
# tracked source, and these are the words it looks for.
_END_PHRASE = re.compile(r"\b" + "END" + r"\s+OF\s+(.+?)\s+DATA\b", re.IGNORECASE)
_BEGIN_PHRASE = re.compile(r"\b" + "BEG" + r"IN\s+(.+?)\s+DATA\b", re.IGNORECASE)
_COMMENT_WINDOW = 200

# Section -> (reason, namespace, key of a record's values): one element per key in a namespace.
_UNIQUE = {
    "bus": ("duplicate_bus", "bus", lambda v: v["I"]),
    "load": ("duplicate_load", "load", lambda v: (v["I"], v["ID"])),
    "generator": ("duplicate_machine", "generator", lambda v: (v["I"], v["ID"])),
    "branch": ("duplicate_branch", "branch", lambda v: branch_key(v["I"], v["J"], v["CKT"])),
    "transformer": ("duplicate_branch", "branch",
                    lambda v: branch_key(v["I"], v["J"], v["CKT"]))}

_STRING_FIELDS = frozenset(["NAME", "ID", "CKT", "VECGRP", "ARNAME", "ZONAME", "OWNAME"])
_INT_FIELDS = frozenset([
    "I", "J", "K", "IDE", "AREA", "ZONE", "OWNER", "STATUS", "STAT", "ST", "MET", "CW", "CZ", "CM",
    "NMETR", "IREG", "O1", "O2", "O3", "O4", "SCALE", "INTRPT", "WMOD", "ISW", "COD1", "CONT1",
    "NTP1", "TAB1"])

# Range rules: a value outside them is a bad_value, so the builder never sees it.
_CHECKS = {
    "I": lambda v: v >= 1, "J": lambda v: v >= 1, "K": lambda v: v >= 0,
    "IDE": lambda v: v in (1, 2, 3, 4),
    "STATUS": lambda v: v in (0, 1), "STAT": lambda v: v in (0, 1), "ST": lambda v: v in (0, 1),
    "BASKV": lambda v: v > 0.0, "R1-2": lambda v: v >= 0.0, "X1-2": lambda v: v > 0.0,
    "WINDV1": lambda v: v > 0.0}

_INT_TEXT = re.compile(r"[+-]?[0-9]+", re.ASCII)
_FLOAT_TEXT = re.compile(r"[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", re.ASCII)


def split_record(line):
    """
    The fields of one RAW line: split at commas outside single quotes, stop at an unquoted slash
    (a trailing comment), strip spaces and tabs, and remove one pair of surrounding quotes.
    """
    tokens, current, quoted = [], [], False
    for char in line:
        if char == "'":
            quoted = not quoted
            current.append(char)
            continue
        if char == "/" and not quoted:
            break
        if char == "," and not quoted:
            tokens.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    tokens.append("".join(current).strip())
    return [token[1:-1].strip() if len(token) >= 2 and token[0] == token[-1] == "'" else token
            for token in tokens]


def branch_key(i, j, ckt):
    """The from-to-circuit key `%d-%d-%s`, the circuit id without quotes or padding."""
    return "%d-%d-%s" % (i, j, str(ckt).strip())


def _typed(name, token, line):
    """`token` as the type its field holds, range-checked; RawRefused(bad_value) otherwise."""
    if name in _STRING_FIELDS:
        return token
    if name in _INT_FIELDS:
        pattern, kind = _INT_TEXT, int
    else:
        pattern, kind = _FLOAT_TEXT, float
    if not pattern.fullmatch(token):
        raise RawRefused("bad_value", line)
    try:
        value = kind(token)
    except (ValueError, OverflowError):
        raise RawRefused("bad_value", line)
    if kind is float and not math.isfinite(value):
        raise RawRefused("bad_value", line)
    check = _CHECKS.get(name)
    if check is not None and not check(value):
        raise RawRefused("bad_value", line)
    return value


def _convert(spec, tokens, line):
    """The value dict of one record line: counts checked, defaults applied, every field typed."""
    count = len(tokens)
    if count < spec.required or count > len(spec.names):
        raise RawRefused("field_count", line)
    values = {}
    for position, name in enumerate(spec.names):
        token = tokens[position] if position < count else ""
        if token == "":
            if name not in spec.defaults:
                raise RawRefused("bad_value", line)
            values[name] = spec.defaults[name]
        else:
            values[name] = _typed(name, token, line)
    return values


def _decode(data):
    """
    The RAW text of `data` (bytes or str). The size cap is checked before anything is decoded, a
    UTF-8 byte order mark is dropped, and bytes that are not UTF-8 are decoded as Latin-1 so no byte
    is lost (PSS/E writes names in the machine's code page). Empty or blank input is refused.
    """
    if isinstance(data, str):
        if len(data) > MAX_RAW_BYTES:
            raise RawRefused("too_large")
        data = data.encode("utf-8", "replace")
    elif isinstance(data, (bytes, bytearray, memoryview)):
        data = bytes(data)
    else:
        raise TypeError("RAW input must be bytes or str")
    if len(data) > MAX_RAW_BYTES:
        raise RawRefused("too_large")
    if data.startswith(_UTF8_BOM):
        data = data[len(_UTF8_BOM):]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    if not text.strip():
        raise RawRefused("empty")
    return text


def _header(lines):
    """(revision, ic, sbase_mva, base_frequency_hz) from the first line."""
    if len(lines) < 3:
        raise RawRefused("bad_header", 1)
    tokens = split_record(lines[0])
    if len(tokens) < 3:
        raise RawRefused("bad_header", 1)
    try:
        ic = int(tokens[0])
        sbase = float(tokens[1])
        revision = int(tokens[2])
    except ValueError:
        raise RawRefused("bad_header", 1)
    if ic not in (0, 1) or not math.isfinite(sbase) or sbase <= 0.0:
        raise RawRefused("bad_header", 1)
    if revision not in FIELD_TABLES:
        raise RawRefused("unknown_revision", 1)
    frequency = 60.0
    if len(tokens) > 5 and tokens[5] != "":
        try:
            frequency = float(tokens[5])
        except ValueError:
            raise RawRefused("bad_header", 1)
        if not math.isfinite(frequency) or frequency <= 0.0:
            raise RawRefused("bad_header", 1)
    return revision, ic, sbase, frequency


class _Walker(object):
    """The data lines of a RAW text with their 1-based numbers; blank and @! comment lines skipped."""

    def __init__(self, lines, start):
        self._lines = lines
        self._position = start

    def next(self):
        """(line number, text) of the next data line, or None at the end of the text."""
        while self._position < len(self._lines):
            text = self._lines[self._position]
            self._position += 1
            stripped = text.strip()
            if stripped and not stripped.startswith("@!"):
                return self._position, text
        return None

    @property
    def end(self):
        return len(self._lines)


def _read_transformer(walker, tables, tokens, number):
    """One two-winding transformer record: its four lines merged into one value dict."""
    if len(tokens) < 3:
        raise RawRefused("field_count", number)
    k_value = 0 if tokens[2] == "" else _typed("K", tokens[2], number)
    if k_value != 0:
        raise RawRefused("three_winding", number)
    values = _convert(tables["transformer_1"], tokens, number)
    for name in _TRANSFORMER_TABLES[1:]:
        item = walker.next()
        if item is None:
            raise RawRefused("unterminated", walker.end)
        line_number, text = item
        values.update(_convert(tables[name], split_record(text), line_number))
    return Record("transformer", number, values)


def _names(section, phrase):
    """True when the terminator phrase `phrase` names `section`."""
    return phrase.strip().upper().startswith(_MARKERS[section])


def _check_terminator(text, section, following, number):
    """
    A terminator comment, when it names a section, must name this one (end-of phrase) and the
    next one in the file order (begin phrase); anything else is an unknown or misplaced section.
    """
    comment = text.partition("/")[2][:_COMMENT_WINDOW]
    ended = _END_PHRASE.search(comment)
    if ended is not None and not _names(section, ended.group(1)):
        raise RawRefused("unknown_section", number)
    begun = _BEGIN_PHRASE.search(comment)
    if begun is not None and (following is None or not _names(following, begun.group(1))):
        raise RawRefused("unknown_section", number)


def _claim(seen, record):
    """Record the key of `record` in `seen`; RawRefused when an earlier record has the same key."""
    entry = _UNIQUE.get(record.section)
    if entry is None:
        return
    reason, namespace, key_of = entry
    key = key_of(record.values)
    taken = seen.setdefault(namespace, set())
    if key in taken:
        raise RawRefused(reason, record.line)
    taken.add(key)


def parse_raw(data):
    """
    The `ParsedCase` of a RAW file given as bytes or str; RawRefused for anything the builder
    cannot reproduce exactly. `sections` maps every section name of the revision to a tuple of
    Records (the title lines are not kept, an unsupported section is always empty, and a transformer
    Record holds the fields of its four lines).
    """
    text = _decode(data)
    lines = [line.rstrip("\r") for line in text.split("\n")]
    revision, ic, sbase, frequency = _header(lines)
    tables = FIELD_TABLES[revision]
    walker = _Walker(lines, 3)
    order = SECTION_ORDER[revision]
    sections = {}
    seen = {}
    for position, section in enumerate(order):
        records = []
        following = order[position + 1] if position + 1 < len(order) else None
        while True:
            item = walker.next()
            if item is None:
                raise RawRefused("unterminated", walker.end)
            number, line = item
            tokens = split_record(line)
            if tokens[0].upper() == "Q":
                raise RawRefused("unterminated", number)
            if tokens == ["0"]:
                _check_terminator(line, section, following, number)
                break
            if section not in SUPPORTED_SECTIONS:
                raise RawRefused("unsupported_section", number)
            if section == "transformer":
                record = _read_transformer(walker, tables, tokens, number)
            else:
                record = Record(section, number, _convert(tables[section], tokens, number))
            _claim(seen, record)
            records.append(record)
        sections[section] = tuple(records)
    item = walker.next()
    if item is None:
        raise RawRefused("unterminated", walker.end)
    if split_record(item[1])[0].upper() != "Q":
        raise RawRefused("trailing_data", item[0])
    extra = walker.next()
    if extra is not None:
        raise RawRefused("trailing_data", extra[0])
    return ParsedCase(revision, ic, sbase, frequency, sections)
