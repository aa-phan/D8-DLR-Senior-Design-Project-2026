"""
The only module of the PSS/E job that names psspy functions (pss-e-integration Phase 2,
plan 02-02; research D-07 and D-10).

`PsseApi` wraps a psspy module object that is passed in. The job never imports psspy: it is
importable only inside PSS/E's own interpreter, and the import gate in
backend/tests/psse_contract_test.py forbids the import statement in this package. Tests pass
backend/tests/psse_fake_psspy.FakePsspy; the Phase 3 launcher passes the real module.

Every function the adapter calls is one row of SURFACE, with the parameter names of the
PSS/E API manual and the evidence for that signature. A call outside the table, or with a
keyword the table does not list, is refused before it reaches psspy. The Phase 3 probe
compares this table with the real psspy on the laptop; branch_chng_3 is the one row whose
signature is an assumption (research A1) and is marked UNVERIFIED.

A load flow counts as converged only when fnsl returned ierr 0 and solved() then returned 0
(classify_solve). The adapter never writes a rating that is not a finite number above 0 and
refuses to save onto the case file it was given. Every psspy failure (a non-zero ierr, an
exception, bulk columns of unequal length) is a PsseCallError naming the function, the ierr
and the manual's meaning; the message never holds an argument or a path.

Standard library only, Python 3.7 syntax (D-05).
"""

import collections
import math
import os


SurfaceRow = collections.namedtuple(
    "SurfaceRow", ["name", "parameters", "returns", "evidence", "confidence"]
)

CONFIDENCE_LEVELS = ("HIGH", "MEDIUM", "LOW", "UNVERIFIED")

# One row per psspy function the adapter calls. Evidence ranks (research, "The real psspy
# surface"): M33 = PSS/E 33.5 API manual text, REF34 = a 34-era PSSPY reference, BLOG24 = a
# 2024 blog quoting the 35-era API, PYPSSE = NREL's open-source PyPSSE, FORUM = psspy.org.
_ABRN_PARAMETERS = ("sid", "owner", "ties", "flag", "entry", "string")
SURFACE = (
    SurfaceRow("psseversion", (), "(name, major, minor, modlvl, date, stat)",
               "M33 12.14; 35 and 36 signature unverified", "MEDIUM"),
    SurfaceRow("getdefaultint", (), "int sentinel",
               "M33 12.7; BLOG24; FORUM question 8382", "HIGH"),
    SurfaceRow("getdefaultreal", (), "float sentinel",
               "M33 12.8; BLOG24; FORUM question 8382", "HIGH"),
    SurfaceRow("getdefaultchar", (), "str sentinel",
               "M33 12.9; BLOG24; FORUM question 8382", "HIGH"),
    SurfaceRow("case", ("sfile",), "ierr",
               "M33 1.50; BLOG24; PYPSSE simulator.py:172", "HIGH"),
    SurfaceRow("save", ("sfile",), "ierr",
               "REF34 p.4; BLOG24 psspy.save('tmp.sav')", "HIGH"),
    SurfaceRow("fnsl", ("options",), "ierr",
               "REF34 p.6 (options list of 8); PYPSSE static.py:25 (no-argument form)", "HIGH"),
    SurfaceRow("solved", (), "solution indicator",
               "M33 7.142; PYPSSE pcm.py:31-33", "HIGH"),
    SurfaceRow("iterat", (), "iteration count",
               "REF34 p.8; M33 7.155", "HIGH"),
    SurfaceRow("sysmsm", (), "system MVA mismatch",
               "REF34 p.8; M33 7.155; FORUM question 6921", "HIGH"),
    SurfaceRow("abrnint", _ABRN_PARAMETERS, "(ierr, [columns])",
               "M33 8.12.2-8.12.5; BLOG24; FORUM abrnint answer", "HIGH"),
    SurfaceRow("abrnreal", _ABRN_PARAMETERS, "(ierr, [columns])",
               "M33 8.12.2-8.12.5; BLOG24", "HIGH"),
    SurfaceRow("abrnchar", _ABRN_PARAMETERS, "(ierr, [columns])",
               "M33 8.12.2-8.12.5; BLOG24", "HIGH"),
    SurfaceRow("abusint", ("sid", "flag", "string"), "(ierr, [columns])",
               "M33 8.3.2; BLOG24", "HIGH"),
    SurfaceRow("abusreal", ("sid", "flag", "string"), "(ierr, [columns])",
               "M33 8.3.3; BLOG24 psspy.abusreal(-1, flag, string)", "HIGH"),
    SurfaceRow("brndat", ("ibus", "jbus", "ickt", "string"), "(ierr, rval)",
               "M33 7.9", "HIGH"),
    SurfaceRow("branch_chng_3",
               ("ibus", "jbus", "ckt", "intgar", "realar", "ratings", "namear"), "ierr",
               "FORUM questions 10264 and 3039; parameter list by analogy with branch_data_3 "
               "(BLOG24, FORUM question 10559); signature assumed (research A1)", "UNVERIFIED"),
    SurfaceRow("bsys",
               ("sid", "usekv", "basekv", "numarea", "areas", "numbus", "buses", "numowner",
                "owners", "numzone", "zones"), "ierr",
               "REF34 p.9; BLOG24", "HIGH"),
    SurfaceRow("scal_2", ("sid", "all", "apiopt", "status", "scalval"), "(ierr, totals, moto)",
               "M33 1.274; FORUM question 6830", "HIGH"),
)
SURFACE_NAMES = frozenset(row.name for row in SURFACE)
SURFACE_BY_NAME = {row.name: row for row in SURFACE}

# solved() codes, verbatim meaning from the manual (M33 7.142). Only 0 is success.
SOLVED_MEANING = {
    0: "met convergence tolerance",
    1: "iteration limit exceeded",
    2: "blown up (non-divergent option disabled)",
    3: "terminated by non-divergent option",
    4: "terminated by console interrupt",
    5: "singular Jacobian matrix or voltage of 0.0 detected",
    6: "inertial power flow dispatch error (INLF)",
    7: "OPF solution met convergence tolerance (NOPF)",
    9: "solution not attempted",
}
FNSL_ERRORS = {
    1: "invalid options",
    2: "generators are converted",
    3: "buses in island without swing bus",
    4: "bus type and series element status inconsistencies",
    5: "prerequisite requirements not met",
}
CASE_ERRORS = {
    1: "case file name is blank",
    2: "error reading the case file",
    3: "error opening the case file",
    4: "prerequisite requirements not met",
}
BRNDAT_ERRORS = {
    1: "bus not found",
    2: "branch not found",
    3: "invalid string",
    4: "invalid with multisection line identifier",
}
BRANCH_CHNG_ERRORS = {
    1: "bus not found",
    3: "branch is a two-winding transformer",
    9: "branch not found",
}

RATE_INDEX = {"RATEA": 0, "RATEB": 1, "RATEC": 2}
THERMAL_BASES = ("current", "mva")

_NOT_LISTED = "error code not listed in the manual excerpt"
_SHAPE = "unexpected return shape"
_UNEQUAL = "columns of unequal length"
_COLUMN_TYPE = "unexpected column type"
_FNSL_OPTION_COUNT = 8


def pct_string(rate_set, basis):
    """The abrnreal percent-of-rating item for `rate_set` on `basis` ("current" or "mva")."""
    if rate_set not in RATE_INDEX:
        raise ValueError("rate_set must be one of %s" % ", ".join(sorted(RATE_INDEX)))
    if basis not in THERMAL_BASES:
        raise ValueError("basis must be one of %s" % ", ".join(THERMAL_BASES))
    letter = rate_set[-1]
    return ("MAXPCTRATE" if basis == "current" else "MXPCTMVARAT") + letter


SolveResult = collections.namedtuple(
    "SolveResult", ["converged", "ierr", "solved_code", "meaning", "iterations", "mismatch_mva"]
)


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def classify_solve(ierr, solved_code, iterations=None, mismatch_mva=None):
    """The convergence rule (STU-01, research D-10): converged only for fnsl ierr 0 and solved() 0.

    Both values must be plain ints. A non-zero fnsl ierr means solved() describes an older
    attempt, so it is never trusted then (research Pitfall 1); only 0 is success among the
    solved() codes (Pitfall 2).
    """
    ierr_ok = _is_int(ierr) and ierr == 0
    code_is_int = _is_int(solved_code)
    converged = ierr_ok and code_is_int and solved_code == 0
    if ierr_ok:
        if code_is_int and solved_code in SOLVED_MEANING:
            meaning = SOLVED_MEANING[solved_code]
        else:
            meaning = "unknown solved code %s" % (solved_code,)
    else:
        text = FNSL_ERRORS.get(ierr, "unknown fnsl error") if _is_int(ierr) else "unknown fnsl error"
        meaning = "fnsl ierr %s: %s; solved() is not trusted after a failed fnsl" % (ierr, text)
    return SolveResult(converged, ierr, solved_code, meaning, iterations, mismatch_mva)


class PsseCallError(RuntimeError):
    """A psspy call failed. The message holds the function, the ierr and the meaning only."""

    def __init__(self, function, ierr, meaning):
        self.function = function
        self.ierr = ierr
        self.meaning = meaning
        RuntimeError.__init__(self, "psspy.%s failed: ierr=%s (%s)" % (function, ierr, meaning))


class CaseProtected(RuntimeError):
    """A save onto the case file that was loaded (Power Systems' file is never overwritten)."""


class BranchRow(collections.namedtuple(
        "BranchRow", ["from_bus", "to_bus", "ckt", "in_service", "is_transformer"])):
    """One branch of the case index; `ckt` is stripped of PSS/E's two-character padding."""

    __slots__ = ()

    @property
    def key(self):
        return "%d-%d-%s" % (self.from_bus, self.to_bus, self.ckt)


class BusRow(collections.namedtuple(
        "BusRow", ["number", "type_code", "base_kv", "pu", "nvlmlo", "nvlmhi", "evlmlo", "evlmhi"])):
    """One bus of the case: type code, base kV, voltage in pu and the case's own limits."""

    __slots__ = ()


class BranchFlow(collections.namedtuple(
        "BranchFlow",
        ["from_bus", "to_bus", "ckt", "in_service", "rate_mva", "pct", "p_mw", "max_mva"])):
    """One line's rating, percent loading, active power and larger-end apparent flow."""

    __slots__ = ()

    @property
    def key(self):
        return "%d-%d-%s" % (self.from_bus, self.to_bus, self.ckt)


def _normalise_path(path):
    if not isinstance(path, str) or not path.strip():
        raise ValueError("path must be a non-empty string")
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


class PsseApi(object):
    """The study's only way to PSS/E: an injected psspy module behind the SURFACE table."""

    def __init__(self, psspy_module, protected_path=None):
        self._psspy = psspy_module
        self._protected = None if protected_path is None else _normalise_path(protected_path)
        self.calls = []
        self.warnings = []
        self._int_sentinel = self._call("getdefaultint")
        self._real_sentinel = self._call("getdefaultreal")
        self._char_sentinel = self._call("getdefaultchar")

    # -- the one gate to psspy ------------------------------------------------------------

    def _call(self, name, *args, **kwargs):
        row = SURFACE_BY_NAME.get(name)
        if row is None:
            raise ValueError("psspy.%s is not in the SURFACE table" % name)
        if len(args) > len(row.parameters):
            raise ValueError("psspy.%s takes at most %d arguments" % (name, len(row.parameters)))
        for keyword in kwargs:
            if keyword not in row.parameters:
                raise ValueError("psspy.%s has no parameter %s in the SURFACE table" % (name, keyword))
            if row.parameters.index(keyword) < len(args):
                raise ValueError("psspy.%s got parameter %s twice" % (name, keyword))
        self.calls.append((name, len(args), tuple(sorted(kwargs))))
        try:
            return getattr(self._psspy, name)(*args, **kwargs)
        except Exception as error:
            raise PsseCallError(name, None, type(error).__name__) from None

    @staticmethod
    def _plain_ierr(name, value):
        if not _is_int(value):
            raise PsseCallError(name, None, _SHAPE)
        return value

    def _bulk(self, name, count, **kwargs):
        """The `count` columns of a bulk read as lists, equal in length; PsseCallError otherwise."""
        result = self._call(name, **kwargs)
        if not isinstance(result, (tuple, list)) or len(result) != 2:
            raise PsseCallError(name, None, _SHAPE)
        ierr = self._plain_ierr(name, result[0])
        if ierr != 0:
            raise PsseCallError(name, ierr, _NOT_LISTED)
        columns = result[1]
        if (not isinstance(columns, (tuple, list)) or len(columns) != count
                or any(not isinstance(column, (tuple, list)) for column in columns)):
            raise PsseCallError(name, None, _SHAPE)
        if len(set(len(column) for column in columns)) > 1:
            raise PsseCallError(name, None, _UNEQUAL)
        return [list(column) for column in columns]

    # -- case ----------------------------------------------------------------------------

    def load_case(self, path):
        """Load the saved case at `path` (a non-zero ierr is a PsseCallError with the manual's text)."""
        ierr = self._plain_ierr("case", self._call("case", path))
        if ierr != 0:
            raise PsseCallError("case", ierr, CASE_ERRORS.get(ierr, "unknown case error"))

    # -- load flow -----------------------------------------------------------------------

    def solve(self, options=None):
        """Run fnsl and classify the result; non-convergence is a result, never an exception.

        Iterations and mismatch are kept only when fnsl itself returned 0, because after a
        failed fnsl they describe an older attempt.
        """
        if options is None:
            ierr = self._call("fnsl")
        else:
            values = list(options)
            if len(values) != _FNSL_OPTION_COUNT or not all(_is_int(value) for value in values):
                raise ValueError("options must be a list of %d integers" % _FNSL_OPTION_COUNT)
            ierr = self._call("fnsl", options=values)
        solved_code = self._call("solved")
        iterations = self._call("iterat")
        mismatch = self._call("sysmsm")
        if _is_int(ierr) and ierr == 0:
            return classify_solve(ierr, solved_code, iterations, mismatch)
        return classify_solve(ierr, solved_code)

    # -- reads ---------------------------------------------------------------------------

    def _branch_read(self, flag):
        selectors = dict(sid=-1, owner=1, ties=1, flag=flag, entry=1)
        ints = self._bulk("abrnint", 3, string=["FROMNUMBER", "TONUMBER", "STATUS"], **selectors)
        chars = self._bulk("abrnchar", 1, string=["ID"], **selectors)
        if len(chars[0]) != len(ints[0]):
            raise PsseCallError("abrnchar", None, _UNEQUAL)
        if not all(_is_int(v) for column in ints for v in column) or not all(
                isinstance(v, str) for v in chars[0]):
            raise PsseCallError("abrnint", None, _COLUMN_TYPE)
        return list(zip(ints[0], ints[1], [text.strip() for text in chars[0]], ints[2]))

    def branch_table(self):
        """(lines, transformers): BranchRow lists sorted by key, any status, ckt stripped."""
        lines = {}
        for from_bus, to_bus, ckt, status in self._branch_read(2):
            row = BranchRow(from_bus, to_bus, ckt, status == 1, False)
            if row.key in lines:
                raise PsseCallError("abrnint", None, "duplicate branch key")
            lines[row.key] = row
        transformers = {}
        for from_bus, to_bus, ckt, status in self._branch_read(4):
            row = BranchRow(from_bus, to_bus, ckt, status == 1, True)
            if row.key not in lines:
                if row.key in transformers:
                    raise PsseCallError("abrnint", None, "duplicate branch key")
                transformers[row.key] = row
        return ([lines[key] for key in sorted(lines)],
                [transformers[key] for key in sorted(transformers)])
