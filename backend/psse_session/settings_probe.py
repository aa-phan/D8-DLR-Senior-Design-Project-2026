"""
The settings section of the laptop session (pandapower-solver Phase 1, plan 01-04: PSE-02).

Why settings are measured: pandapower has to copy whatever PSS/E does (D-14), and nothing in hand
documents PSS/E 36.4's getters for the load-flow settings that move the answer (research Pattern 2).
So the session does two things and leaves the judging to the Mac (plan 01-08):

1. It records every candidate reader call one by one (`SETTINGS_READS`: the function, the parameter
   name, the ierr or the exception class and the value exactly as returned). The names `ITMXN`
   and `TOLN` come from psspy.org question 11652 and PSS/E's solution-parameter naming; all of the
   reader names are ASSUMED for 36.4 (research A5, confidence LOW). A refused or missing reader
   leaves its setting unavailable with a reason that names the call, never an empty field.
2. It measures behaviour. For each city's scaled copy, and at the voltage-margin last-good point
   when plan 01-03 recorded one, it solves once per entry of `FNSL_VARIANTS` from a fresh load and
   stores the solve status, the bus voltages and a RAW snapshot of the solved case. The option
   meaning of the eight-integer `fnsl` list (tap adjustment, area interchange, phase-shift
   adjustment, DC tap adjustment, switched-shunt adjustment, flat start, var limits, non-divergent
   solution, in that order) is ASSUMED (research A6, LOW), which is exactly why the variants differ
   only in the var-limit slot: whether voltages differ between them shows how PSS/E treats
   generator reactive limits. The keyword form `fnsl(options=[...])` has never run on the real
   engine, so a list variant is called positionally first and by keyword only if that raises
   TypeError; the form that worked is recorded as `call_form`.

Settings counted from the network section (tap, phase shift, switched shunt and area interchange)
come from `ctx.results["network"]["counts"]`: when the case has no controlling transformers, no
switched shunts and at most one area the setting cannot matter, and that is recorded as the value.

Members: `settings/settings.json` (`settings` keyed by `SETTING_KEYS`, each with `status`
(read, measured or unavailable), `value`, `source`, `reason`, `members`; `reads`; `fingerprints`;
`counts`), `settings/docs/<function>.txt` (signature and doc text of each reader),
`settings/fingerprint_<city>_<point>_<variant>.json` (solve and buses) and `.raw`.

PSS/E settings are never changed: every fingerprint starts from a fresh in-memory load, passes its
options explicitly to one solve and saves nothing. The stressed point makes its temporary saved
copies inside the work folder and removes them. Values read from PSS/E are stored exactly as
returned (the JSON float repr round-trips bit for bit); classification and tolerances are the
offline analyser's.

Honest scope: proven only against the fake psspy. Reader names, option meanings and the keyword
`fnsl` form are UNVERIFIED on PSS/E 36.4 until the session of plan 01-10.

Standard library plus psse_job only, Python 3.7 syntax (D-05).
"""

import math
import os

from psse_job import constants, margin, psse_api, study
from psse_session import bundle, session

SECTION = "settings"
SETTING_KEYS = (
    "var_limits", "tap_adjustment", "switched_shunt_adjustment", "area_interchange",
    "phase_shift_adjustment", "dc_tap_adjustment", "mismatch_tolerance_mva", "iteration_limit",
    "flat_start", "non_divergent",
)
# (function, parameter name, the setting it answers or None). All [ASSUMED] for 36.4, LOW.
SETTINGS_READS = (
    ("prmint", "ITMXN", "iteration_limit"),
    ("prmdat", "TOLN", "mismatch_tolerance_mva"),
    ("prmint", "PFCODE", None),
    ("prmint", "ITMX", None),
    ("prmdat", "TOLER", None),
    ("prmdat", "ACCN", None),
)
# (variant, option list or None). None is the job's own no-argument fnsl. The list order is
# tap, area interchange, phase shift, DC tap, switched shunt, flat start, var limits, non-divergent
# (assumption A6); the variants differ in the var-limit slot.
FNSL_VARIANTS = (
    ("default", None),
    ("forum", [1, 0, 0, 1, 1, 0, 99, 0]),
    ("var_limits_immediate", [1, 0, 0, 1, 1, 0, 0, 0]),
    ("var_limits_ignore", [1, 0, 0, 1, 1, 0, -1, 0]),
)
POINT_BASE = "base"
POINT_MARGIN = "margin_last_good"
PRESENT_REASON = "present: the Mac builder refuses it"
JOB_DEFAULT_FORM = "job_default"


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _num(value):
    """`value` as a float, or None for anything that is not a finite number (JSON has no NaN)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _int_or_none(value):
    return value if _is_int(value) else None


def _failure_text(error):
    """The function and class (or the stage) of a failed call, never its message."""
    if isinstance(error, study.StudyFailed):
        return "StudyFailed %s" % bundle.safe_item(error.stage)
    function = getattr(error, "function", None)
    name = bundle.class_word(error)
    return "%s %s" % (function, name) if isinstance(function, str) else name


def _solve_dict(result):
    return {
        "converged": bool(result.converged),
        "ierr": _int_or_none(result.ierr),
        "solved_code": _int_or_none(result.solved_code),
        "meaning": result.meaning if isinstance(result.meaning, str) else None,
        "iterations": _int_or_none(result.iterations),
        "mismatch_mva": _num(result.mismatch_mva),
    }


def _bus_rows(buses):
    rows = []
    for number in sorted(buses):
        row = buses[number]
        rows.append({"number": row.number, "type_code": row.type_code,
                     "base_kv": _num(row.base_kv), "pu": _num(row.pu)})
    return rows


def _snapshot(ctx, member):
    """`member` when PSS/E wrote it as RAW text, else None (the JSON member is written anyway)."""
    if ctx.raw_writer is None:
        return None
    try:
        record = ctx.raw_writer(member)
    except Exception:  # noqa: BLE001 - a missing snapshot is recorded as null, never fatal
        return None
    return member if isinstance(record, dict) and record.get("status") == "ok" else None


# -- the candidate reads -------------------------------------------------------------------------


def _read_one(ctx, function, name):
    """One candidate read; the record holds the ierr or the class and the value as returned."""
    record = {"function": function, "name": name, "ierr": None, "error_class": None, "value": None}
    try:
        result = getattr(ctx.gated, function)(name)
    except Exception as exc:  # noqa: BLE001 - recorded as the class only, never the text
        record["error_class"] = bundle.class_word(exc)
        return record
    if not isinstance(result, (tuple, list)) or len(result) != 2 or not _is_int(result[0]):
        record["error_class"] = "UnexpectedReturn"
        return record
    record["ierr"] = result[0]
    if result[0] != 0:
        return record
    value = result[1]
    if _is_int(value) or isinstance(value, str) or (isinstance(value, float) and math.isfinite(value)):
        record["value"] = value
    else:
        record["error_class"] = "UnexpectedValue"
    return record


def _refusal_text(record):
    what = record["error_class"] if record["error_class"] else "ierr %s" % record["ierr"]
    return "%s %s: %s" % (record["function"], record["name"], what)


def _setting(status, value, source, reason, members=()):
    return {"status": status, "value": value, "source": source, "reason": reason,
            "members": list(members)}


def _read_setting(reads, key):
    candidates = [record for record in reads
                  if any(row[0] == record["function"] and row[1] == record["name"] and row[2] == key
                         for row in SETTINGS_READS)]
    for record in candidates:
        if record["error_class"] is None and record["ierr"] == 0:
            return _setting("read", record["value"], "%s %s" % (record["function"], record["name"]),
                            None)
    reasons = [_refusal_text(record) for record in candidates]
    return _setting("unavailable", None, None,
                    "; ".join(reasons) if reasons else "no reader is listed for this setting")


def _count_setting(counts, count_name, limit, text):
    """A setting that cannot matter when the case has at most `limit` of what it adjusts."""
    count = (counts or {}).get(count_name)
    if not _is_int(count):
        return _setting("unavailable", None, "raw_counts", "count unknown")
    if count <= limit:
        return _setting("measured", text, "raw_counts", None)
    return _setting("measured", None, "raw_counts", PRESENT_REASON)


def _var_limits_setting(fingerprints):
    members = sorted(item["member"] for item in fingerprints if item["member"])
    if not members:
        return _setting("unavailable", None, "fingerprint", "no fingerprint solve completed")
    return _setting("measured", None, "fingerprint", None, members)


def _settings_document(counts, reads, fingerprints):
    settings = {}
    for key in ("iteration_limit", "mismatch_tolerance_mva"):
        settings[key] = _read_setting(reads, key)
    settings["var_limits"] = _var_limits_setting(fingerprints)
    settings["tap_adjustment"] = _count_setting(
        counts, "controlling_transformers", 0, "no controlling transformers")
    settings["phase_shift_adjustment"] = _count_setting(
        counts, "controlling_transformers", 0, "no controlling transformers")
    settings["switched_shunt_adjustment"] = _count_setting(
        counts, "switched_shunts", 0, "no switched shunts")
    settings["area_interchange"] = _count_setting(counts, "areas", 1, "one area")
    settings["dc_tap_adjustment"] = _setting(
        "unavailable", None, None, "decided on the Mac from the RAW: the builder refuses DC data")
    settings["flat_start"] = _setting(
        "unavailable", None, None, "no reader on this engine; recorded for Phase 2")
    settings["non_divergent"] = _setting(
        "unavailable", None, None, "no reader on this engine; recorded for Phase 2")
    return settings


# -- the fingerprint solves ----------------------------------------------------------------------


def _solve_variant(ctx, api, options):
    """(call form, SolveResult or None, failure text or None) of one solve of the loaded case."""
    if options is None:
        try:
            return JOB_DEFAULT_FORM, api.solve(None), None
        except (psse_api.PsseCallError, ValueError) as error:
            return JOB_DEFAULT_FORM, None, _failure_text(error)
    form = "positional"
    gated = ctx.gated
    try:
        try:
            ierr = gated.fnsl(list(options))
        except TypeError:
            form = "keywords"
            ierr = gated.fnsl(options=list(options))
        solved_code = gated.solved()
        iterations = gated.iterat()
        mismatch = gated.sysmsm()
    except Exception as exc:  # noqa: BLE001 - recorded as the class only, never the text
        return form, None, bundle.class_word(exc)
    if _is_int(ierr) and ierr == 0:
        return form, psse_api.classify_solve(ierr, solved_code, iterations, mismatch), None
    return form, psse_api.classify_solve(ierr, solved_code), None


def _one_fingerprint(ctx, city, point, variant, options, start, increment=None):
    """One fingerprint: `start(api)` puts a freshly loaded case in the point's state, then one solve."""
    entry = {"city": city, "point": point, "variant": variant,
             "options": None if options is None else list(options), "call_form": None,
             "solve": None, "member": None, "snapshot": None, "increment_mw": increment,
             "call_failed": None}
    stem = "settings/fingerprint_%s_%s_%s" % (city.lower(), point, variant)
    api = ctx.index.api
    try:
        start(api)
        form, result, failed = _solve_variant(ctx, api, options)
        entry["call_form"] = form
        entry["call_failed"] = failed
        if result is not None:
            entry["solve"] = _solve_dict(result)
        if result is None or not result.converged:
            return entry
        buses = _bus_rows(api.bus_table())
        snapshot = _snapshot(ctx, stem + ".raw")
        ctx.work.add_json(stem + ".json", {
            "city": city, "point": point, "variant": variant, "options": entry["options"],
            "call_form": form, "solve": entry["solve"], "buses": buses, "snapshot": snapshot,
            "increment_mw": increment}, SECTION)
        entry["member"] = stem + ".json"
        entry["snapshot"] = snapshot
    except (psse_api.PsseCallError, ValueError, study.StudyFailed) as error:
        entry["call_failed"] = _failure_text(error)
    except Exception as exc:  # noqa: BLE001 - recorded as the class only, never the text
        entry["call_failed"] = bundle.class_word(exc)
    return entry


def _base_fingerprints(ctx):
    entries = []
    for city in constants.CITIES:
        scaling = ctx.mapping.cities[city].scaling

        def start(api, city=city, scaling=scaling):
            api.load_case(ctx.case_path)
            study.scale_city_case(api, city, scaling)

        for variant, options in FNSL_VARIANTS:
            entries.append(_one_fingerprint(ctx, city, POINT_BASE, variant, options, start))
    return entries


def _remove_folder(path):
    """Delete the tree at `path`, best effort."""
    for root, dirs, files in os.walk(path, topdown=False):
        for name in files:
            try:
                os.remove(os.path.join(root, name))
            except OSError:
                pass
        for name in dirs:
            try:
                os.rmdir(os.path.join(root, name))
            except OSError:
                pass
    try:
        os.rmdir(path)
    except OSError:
        pass


def _stressed_inputs(ctx, city):
    """(increment_mw, sink buses) of `city` at the margin last-good point, or None when plan 01-03's
    reference section recorded none (the city failed, was bounded without a margin, or never ran)."""
    entry = (ctx.results.get("reference") or {}).get(city)
    if not isinstance(entry, dict):
        return None
    increments = entry.get("margin_increments")
    sink_buses = entry.get("sink_buses")
    if not increments or _num(increments[0]) is None or not sink_buses:
        return None
    return _num(increments[0]), list(sink_buses)


def _stressed_fingerprints(ctx):
    """Four fingerprints per city that has a recorded last-good transfer: the solved base is
    prepared and saved in a temporary folder inside the work folder (never a member, always
    removed), reloaded for each variant, the sink subsystem is defined and the increment added."""
    entries = []
    root = os.path.join(ctx.work.path, "tmp_sav_settings")
    try:
        for city in constants.CITIES:
            inputs = _stressed_inputs(ctx, city)
            if inputs is None:
                continue
            increment, sink_buses = inputs
            folder = os.path.join(root, city.lower())
            base = None
            failure = None
            try:
                os.makedirs(folder, exist_ok=True)
                base = study.prepare_city_base(
                    ctx.index, ctx.mapping, ctx.selection, city, ctx.budget, folder)
            except (psse_api.PsseCallError, ValueError, study.StudyFailed) as error:
                failure = _failure_text(error)
            except Exception as exc:  # noqa: BLE001 - recorded as the class only, never the text
                failure = bundle.class_word(exc)
            try:
                for variant, options in FNSL_VARIANTS:
                    if base is None:
                        entries.append({
                            "city": city, "point": POINT_MARGIN, "variant": variant,
                            "options": None if options is None else list(options),
                            "call_form": None, "solve": None, "member": None, "snapshot": None,
                            "increment_mw": increment, "call_failed": failure})
                        continue

                    def start(api, base=base, sink_buses=sink_buses, increment=increment):
                        api.load_case(base.saved_path)
                        api.define_subsystem(margin.SINK_SID, sink_buses)
                        if increment > 0:
                            api.scale_load(margin.SINK_SID, increment)

                    entries.append(_one_fingerprint(
                        ctx, city, POINT_MARGIN, variant, options, start, increment))
            finally:
                if base is not None:
                    study.cleanup_base(base)
                _remove_folder(folder)
    finally:
        _remove_folder(root)
    return entries


# -- the section ---------------------------------------------------------------------------------


def _capture_docs(ctx):
    for name in ("prmint", "prmdat"):
        text = "signature: %s\n\n%s\n" % (ctx.gated.signature_text(name), ctx.gated.doc_text(name))
        ctx.work.add_bytes("settings/docs/%s.txt" % name, text.encode("utf-8", "replace"), SECTION)


def run(ctx):
    """The settings section; see the module docstring. Returns a session.SectionResult."""
    _capture_docs(ctx)
    if ctx.index is None:
        # failed, not skipped: "skipped" means "--only did not ask for it" (as in the network section)
        ctx.results[SECTION] = {"settings": {}}
        return session.SectionResult("failed", ("no case index", ctx.index_stage or "internal"), {})
    reads = [_read_one(ctx, function, name) for function, name, _key in SETTINGS_READS]
    fingerprints = _base_fingerprints(ctx) + _stressed_fingerprints(ctx)
    network = ctx.results.get("network") or {}
    settings = _settings_document(network.get("counts"), reads, fingerprints)
    tally = dict((status, sum(1 for item in settings.values() if item["status"] == status))
                 for status in ("read", "measured", "unavailable"))
    tally["fingerprints"] = len(fingerprints)
    tally["fingerprints_ok"] = sum(1 for item in fingerprints if item["member"])
    ctx.work.add_json("settings/settings.json", {
        "settings": settings, "reads": reads, "fingerprints": fingerprints, "counts": tally},
        SECTION)
    ctx.results[SECTION] = {"settings": dict((key, item["status"]) for key, item in settings.items())}
    if tally["fingerprints_ok"] == 0:
        return session.SectionResult("failed", ("unavailable",), tally)
    return session.SectionResult("ok", (), tally)
