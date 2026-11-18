"""
The entry point of a pandapower run (pandapower-solver Phase 2, plan 02-04: ENG-02, ENG-05, ENG-06).

`prepare_run(backend, case_path, mapping_path, ...)` is the pandapower twin of
`psse_job.study.prepare_run`: it loads the mapping once, runs the unchanged study through
`study.make_study(..., solver="pandapower")` and returns a `study.PreparedRun`. The Phase 5
workflow calls it. Importing this module imports `pandapower_job.api`, which registers the adapter
factory under "pandapower".

Stage `mapping` refusals (ENG-02, D-07). A mapping that asks for something pandapower cannot
reproduce, or a backend whose reactive-limit setting is undecided, fails the run at stage `mapping`
with a one-line reason before any case is loaded and before any adapter is built (see `preflight`).
Assumptions awaiting the owner (reversible, confirmed at plan 02-07's checkpoint):

- Q1: a backend whose `enforce_q_lims` is None (PSE-02's reactive-limit classification was
  inconclusive) is refused. The engine never picks a value (D-14: copy what PSS/E reports).
- Q4: `voltage.source "case"` is refused, because the network builder does not carry PSS/E's
  emergency voltage limits; extending the builder would change Phase 1 code.
- A3: the real private mapping uses the defaults (`thermal.basis "current"`, `voltage.source
  "config"`, `solve.options null`). If it does not, the preflight refuses it on first use, loudly.

Settings provenance (ENG-05, Q6). Every dispatch row's `details` carries a `solve_settings` record
(see `settings_record`): the solver, its version, whether the values are placeholders, the solve
settings, where each came from, the deviations from D-14 and the three scaling details. Q6: "stored
with each run" means this record in every dispatch row (free JSON). Since Phase 3 the run row also
carries it: the `solver` and `solver_version` columns (solver-tag migration) hold the solver and its
version. The pandapower version is a solver version, not a PSS/E version, so the study's
`psse_version` is None for a pandapower run (RESEARCH Pitfall 9) and `solver_version` is the bare
version string the adapter reports. The runner must call `job.run_once(..., solver=engine.SOLVER)`:
the run loop refuses results whose solver differs from the run's tag, so a run started with the
default (PSS/E) tag fails at stage validate_results and is never stored as PSS/E results.

Placeholders (D-06). Until PSE-02 is recorded the settings are the named PLACEHOLDER_* constants.
They are used only when a caller passes them in: the adapter solves with the settings of the
backend it was given and never imports this module. `is_placeholder` tells a placeholder backend
from a recorded one (Phase 5 refuses a live write on a placeholder). Recorded PSE-02 values drop in
through `backend_from_records` or `load_recorded_backend`, which fail closed.

Every refusal text is a reason only: no path, bus number or value.
"""

import copy
import json
import math
import os

from psse_job import mapping as mapping_module, run_record, study
from pandapower_job import api, cli, scaling, solve   # importing api registers the "pandapower" factory

SOLVER = api.SOLVER_NAME

PLACEHOLDER_NOTE = "placeholder: PSE-02 not recorded"
PLACEHOLDER_SOLVE = solve.SolveSettings(
    enforce_q_lims=False, tolerance_mva=1e-8, max_iteration=30, collapse_voltage_pu=0.5,
    sources={"enforce_q_lims": PLACEHOLDER_NOTE, "tolerance_mva": PLACEHOLDER_NOTE,
             "max_iteration": PLACEHOLDER_NOTE},
    deviations=("placeholder: not copied from PSS/E",))
PLACEHOLDER_DETAILS = scaling.ScalingDetails("yes", "no", "yes", {"placeholder": True})
PLACEHOLDER_BACKEND = api.PandapowerBackend(PLACEHOLDER_SOLVE, PLACEHOLDER_DETAILS)

SETTINGS_RECORD_KEYS = (
    "solver", "solver_version", "placeholder", "enforce_q_lims", "tolerance_mva", "max_iteration",
    "collapse_voltage_pu", "sources", "deviations", "scaling_details")


def _says_placeholder(text):
    return str(text).strip().lower().startswith("placeholder")


def is_placeholder(backend):
    """True when any solve-setting source starts with "placeholder", or the scaling details'
    evidence is a dict whose "placeholder" key is True."""
    sources = backend.solve_settings.sources
    if any(_says_placeholder(value) for value in sources.values()):
        return True
    evidence = backend.scaling_details.evidence
    return isinstance(evidence, dict) and evidence.get("placeholder") is True


def settings_record(backend, solver_version):
    """The `solve_settings` record stored in every dispatch row's details: exactly
    SETTINGS_RECORD_KEYS, JSON-safe (the scaling details are the three values, no evidence)."""
    values = backend.solve_settings
    details = backend.scaling_details
    record = {
        "solver": SOLVER,
        "solver_version": solver_version,
        "placeholder": is_placeholder(backend),
        "enforce_q_lims": values.enforce_q_lims,
        "tolerance_mva": values.tolerance_mva,
        "max_iteration": values.max_iteration,
        "collapse_voltage_pu": values.collapse_voltage_pu,
        "sources": dict(values.sources),
        "deviations": list(values.deviations),
        "scaling_details": {
            "swing_in_total": details.swing_in_total,
            "clamped_at_limits": details.clamped_at_limits,
            "q_scales_with_p": details.q_scales_with_p},
    }
    return study.json_safe(record)


def preflight(mapping_settings, backend):
    """The first reason this run cannot be done on pandapower, or None (ENG-02, D-07).

    Refused, in this order: a thermal basis other than current (pandapower has no MVA rating
    basis in the study's units); PSS/E fnsl solve options; voltage limits taken from the case
    (the builder does not carry PSS/E's emergency limits, assumption Q4); and a backend whose
    reactive-limit setting is undecided (assumption Q1, D-14). The adapter's own refusals (MVA
    basis in branch_loading, options in solve) stay as defence in depth. Reasons only: no value,
    path or bus number.
    """
    if mapping_settings.thermal_basis != "current":
        return "thermal basis %s cannot be reproduced by pandapower; use current" % (
            mapping_settings.thermal_basis)
    if mapping_settings.solve_options is not None:
        return "solve.options are PSS/E fnsl options and are not supported; use null"
    if mapping_settings.voltage_source != "config":
        return ("voltage.source %s is not supported (emergency limits are not carried); "
                "use config" % mapping_settings.voltage_source)
    if backend.solve_settings.enforce_q_lims is None:
        return "the reactive-limit setting is undecided; PSE-02 must decide it (D-14)"
    return None


def _recording_study(inner, run_backend):
    """The study of a run: `inner`'s results with the settings record added to every dispatch
    row's details, psse_version None, and this engine's tag stamped on them (solver SOLVER and
    solver_version the adapter's version; a StudyFailed passes through unchanged)."""
    def recorded(selection, context):
        results = inner(selection, context)
        record = settings_record(run_backend, results.psse_version)
        dispatch = []
        for row in results.dispatch:
            row = dict(row)
            row["details"] = dict(row.get("details") or {}, solve_settings=copy.deepcopy(record))
            dispatch.append(row)
        return results._replace(dispatch=dispatch, psse_version=None, solver=SOLVER,
                                solver_version=results.psse_version)
    return recorded


def prepare_run(backend, case_path, mapping_path, allow_placeholder=False, clock=None):
    """Everything a pandapower run passes to job.run_once, as a study.PreparedRun.

    `backend` is an api.PandapowerBackend (anything else is a TypeError, a programming error that
    is never stored as a run). The mapping is parsed once. A mapping that cannot be loaded gives a
    study that fails at stage mapping with mapping_sha256 None; one that loads keeps its hash even
    when it is refused afterwards.
    """
    if not isinstance(backend, api.PandapowerBackend):
        raise TypeError("backend must be a PandapowerBackend")
    case_id = run_record.case_label(case_path)
    case_sha256 = run_record.file_sha256(case_path)
    try:
        loaded = mapping_module.load_mapping(mapping_path, allow_placeholder)
    except mapping_module.MappingError as error:
        text = str(error)
        return study.PreparedRun(
            study.failing_study("mapping", "mapping file not usable: %s" % text),
            case_id, case_sha256, None, text)
    reason = preflight(loaded.settings, backend)
    if reason is not None:
        return study.PreparedRun(study.failing_study("mapping", "pandapower: " + reason),
                                 case_id, case_sha256, loaded.sha256, None)
    run_backend = api.PandapowerBackend(
        backend.solve_settings._replace(collapse_voltage_pu=loaded.settings.collapse_voltage_pu),
        backend.scaling_details)
    inner = study.make_study(run_backend, case_path, loaded, clock, solver=api.SOLVER_NAME)
    return study.PreparedRun(_recording_study(inner, run_backend), case_id, case_sha256,
                             loaded.sha256, None)


# -- recorded PSE-02 settings (ENG-05, D-06, Phase 1 D-14) -----------------------------------------

RECORD_REFUSAL_REASONS = (
    "not_a_dict", "settings_refused", "missing_field", "unknown_field", "bad_value",
    "placeholder_source", "bad_detail", "unreadable", "too_large", "not_json", "bad_marker")
MAX_RECORD_BYTES = 1048576

# The six keys of cli._settings_record, and the scaling document's keys (Phase 1's check output).
_SETTINGS_FIELDS = ("enforce_q_lims", "tolerance_mva", "max_iteration", "collapse_voltage_pu",
                    "sources", "deviations")
_DETAIL_FIELDS = ("swing_in_total", "clamped_at_limits", "q_scales_with_p")
_SCALING_OPTIONAL = ("evidence", "snapshots_wanted", "snapshots_read", cli.REPORT_MARKER)
# solve.settings_from_session stores pandapower's own default under this source when PSS/E's
# value could not be read, and the count may then be the word "auto".
_DEFAULT_SOURCE = "pandapower default"


class RecordsRefused(ValueError):
    """Recorded settings were refused. `reason` is one of RECORD_REFUSAL_REASONS; the message holds
    nothing else (no path, no value)."""

    def __init__(self, reason):
        self.reason = reason
        ValueError.__init__(self, "recorded settings refused: %s" % reason)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _check_settings_keys(record):
    if "refused" in record:
        raise RecordsRefused("settings_refused")
    keys = set(record)
    if not set(_SETTINGS_FIELDS) <= keys:
        raise RecordsRefused("missing_field")
    if keys != set(_SETTINGS_FIELDS):
        raise RecordsRefused("unknown_field")


def _checked_sources(sources):
    if not isinstance(sources, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in sources.items()):
        raise RecordsRefused("bad_value")
    if any(_says_placeholder(value) for value in sources.values()):
        raise RecordsRefused("placeholder_source")
    return dict(sources)


def _checked_iterations(value, sources):
    if isinstance(value, str):
        if value == "auto" and sources.get("max_iteration") == _DEFAULT_SOURCE:
            return value
        raise RecordsRefused("bad_value")
    if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
        return value
    raise RecordsRefused("bad_value")


def _solve_from_record(record):
    _check_settings_keys(record)
    enforce = record["enforce_q_lims"]
    if enforce is not None and not isinstance(enforce, bool):
        raise RecordsRefused("bad_value")
    tolerance = record["tolerance_mva"]
    if not _is_number(tolerance) or tolerance <= 0:
        raise RecordsRefused("bad_value")
    collapse = record["collapse_voltage_pu"]
    if not _is_number(collapse) or not 0 < collapse < 1:
        raise RecordsRefused("bad_value")
    sources = _checked_sources(record["sources"])
    iterations = _checked_iterations(record["max_iteration"], sources)
    deviations = record["deviations"]
    if not isinstance(deviations, list) or not all(isinstance(item, str) for item in deviations):
        raise RecordsRefused("bad_value")
    return solve.SolveSettings(enforce, float(tolerance), iterations, float(collapse), sources,
                               tuple(deviations))


def _details_from_record(record):
    keys = set(record)
    if not set(_DETAIL_FIELDS) <= keys:
        raise RecordsRefused("missing_field")
    if not keys <= set(_DETAIL_FIELDS) | set(_SCALING_OPTIONAL):
        raise RecordsRefused("unknown_field")
    for name in _DETAIL_FIELDS:
        value = record[name]
        if not isinstance(value, str) or value not in scaling.DETAIL_VALUES:
            raise RecordsRefused("bad_detail")
    evidence = record.get("evidence")
    evidence = copy.deepcopy(evidence) if isinstance(evidence, dict) else {}
    if evidence.get("placeholder") is True:
        raise RecordsRefused("placeholder_source")
    return scaling.ScalingDetails(record["swing_in_total"], record["clamped_at_limits"],
                                  record["q_scales_with_p"], evidence)


def backend_from_records(settings_record, scaling_record):
    """An api.PandapowerBackend from the Phase 1 check output (the `settings` value of report.json
    and the scaling_details.json document), or RecordsRefused (fail closed).

    The settings record must hold exactly the six keys of the check command's record;
    `enforce_q_lims` None is kept (the preflight refuses it at run time). A source that says
    "placeholder" is refused, so a placeholder can never pass as a recorded value.
    """
    if not isinstance(settings_record, dict) or not isinstance(scaling_record, dict):
        raise RecordsRefused("not_a_dict")
    values = _solve_from_record(settings_record)
    details = _details_from_record(scaling_record)
    return api.PandapowerBackend(values, details)


def _strict_pairs(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError("duplicate key")
        seen[key] = value
    return seen


def _refuse_constant(name):
    raise ValueError("non-finite number")


def _read_document(path):
    try:
        with open(path, "rb") as handle:
            data = handle.read(MAX_RECORD_BYTES + 1)
    except (OSError, TypeError, ValueError):
        raise RecordsRefused("unreadable") from None
    if len(data) > MAX_RECORD_BYTES:
        raise RecordsRefused("too_large")
    try:
        document = json.loads(data.decode("utf-8"), parse_constant=_refuse_constant,
                              object_pairs_hook=_strict_pairs)
    except (ValueError, RecursionError):
        raise RecordsRefused("not_json") from None
    if not isinstance(document, dict):
        raise RecordsRefused("not_a_dict")
    marker = document.get(cli.REPORT_MARKER)
    if not isinstance(marker, int) or isinstance(marker, bool) or marker != 1:
        raise RecordsRefused("bad_marker")
    return document


def load_recorded_backend(check_dir):
    """The backend recorded by one check run: read `report.json` (key `settings`) and
    `scaling_details.json` from `check_dir`, each written by the check command with the
    cli.REPORT_MARKER key, and validate them through backend_from_records. Strict JSON only (no
    NaN, infinity or duplicate key), at most MAX_RECORD_BYTES a file; no message holds a path."""
    try:
        report_path = os.path.join(str(check_dir), "report.json")
        scaling_path = os.path.join(str(check_dir), "scaling_details.json")
    except (TypeError, ValueError):
        raise RecordsRefused("unreadable") from None
    report = _read_document(report_path)
    scaling_document = _read_document(scaling_path)
    if "settings" not in report:
        raise RecordsRefused("missing_field")
    return backend_from_records(report["settings"], scaling_document)
