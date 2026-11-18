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
with each run" means this record in every dispatch row (free JSON, no schema change; Phase 3 owns
the schema, and a run-level column would be its migration). The pandapower version is a solver
version, not a PSS/E version, so the study's `psse_version` is None for a pandapower run (RESEARCH
Pitfall 9).

Placeholders (D-06). Until PSE-02 is recorded the settings are the named PLACEHOLDER_* constants.
They are used only when a caller passes them in: the adapter solves with the settings of the
backend it was given and never imports this module. `is_placeholder` tells a placeholder backend
from a recorded one (Phase 5 refuses a live write on a placeholder). Recorded PSE-02 values drop in
through `backend_from_records` or `load_recorded_backend`, which fail closed.

Every refusal text is a reason only: no path, bus number or value.
"""

import copy

from psse_job import mapping as mapping_module, run_record, study
from pandapower_job import api, scaling, solve   # importing api registers the "pandapower" factory

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


def is_placeholder(backend):
    """True when any solve-setting source starts with "placeholder", or the scaling details'
    evidence is a dict whose "placeholder" key is True."""
    sources = backend.solve_settings.sources
    if any(str(value).startswith("placeholder") for value in sources.values()):
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


def _recording_study(inner, run_backend):
    """The study of a run: `inner`'s results with the settings record added to every dispatch
    row's details and psse_version None (a StudyFailed passes through unchanged)."""
    def recorded(selection, context):
        results = inner(selection, context)
        record = settings_record(run_backend, results.psse_version)
        dispatch = []
        for row in results.dispatch:
            row = dict(row)
            row["details"] = dict(row.get("details") or {}, solve_settings=copy.deepcopy(record))
            dispatch.append(row)
        return results._replace(dispatch=dispatch, psse_version=None)
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
    # Plan 02-04 Task 2: the preflight (settings pandapower cannot reproduce) is called here.
    run_backend = api.PandapowerBackend(
        backend.solve_settings._replace(collapse_voltage_pu=loaded.settings.collapse_voltage_pu),
        backend.scaling_details)
    inner = study.make_study(run_backend, case_path, loaded, clock, solver=api.SOLVER_NAME)
    return study.PreparedRun(_recording_study(inner, run_backend), case_id, case_sha256,
                             loaded.sha256, None)
