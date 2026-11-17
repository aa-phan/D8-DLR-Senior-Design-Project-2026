"""
The scaling section of the laptop session (pandapower-solver Phase 1, plan 01-04: PSE-02).

The job scales a city's copy of the case by whole-case totals (`scale_case`) and the voltage-margin
search adds load at the sink buses (`scale_load`). pandapower has to reproduce what PSS/E does in
both, and three details of PSS/E's scaling are not documented well enough to copy blind (research
Pattern 2, second table; assumption A9, ASSUMED and LOW). Each experiment below measures one of
them and leaves the judging to the Mac (plan 01-08), which reads the totals and the RAW snapshots:

- `swing_in_total`: is the swing machine's generation part of the generation total that
  `read_totals` returns? The totals are read from a fresh load and the RAW snapshots before and
  after are kept (the second is the first again if reading changed nothing).
- `clamp_at_limits_x1_5` and `clamp_at_limits_x3`: when load and generation are both multiplied by
  the factor, does PSS/E stop each machine at its limit, so that the generation total read back
  falls short of the target? The totals before, the targets and the totals after are recorded and
  the RAW snapshots show which machines hit a limit.
- `q_with_p`: in the increment form (`scale_load`, the form the margin search uses) does reactive
  load move with active load? The first city's sink buses get `Q_WITH_P_INCREMENT_MW` and the RAW
  snapshots before and after show what happened to P and Q at those buses.

The experiments go through the job's own `PsseApi` methods and so bypass the job's ratio guards on
purpose (`study.scale_city_case` would refuse a clamp-sized target), but every factor stays inside
`study.SCALE_FACTOR_BOUNDS`. Each experiment starts from a fresh `load_case` of the configured
case. Nothing is solved and nothing is saved here, so no setting or case file can change (T-01-14).

Members: `scaling/experiments.json` (a list of `name`, `status`, `detail`, `totals_before`,
`totals_after`, `targets`, `sink_buses`, `increment_mw`, `before`, `after`; the last two name the
RAW members or are null) and `scaling/<name>_before.raw`, `scaling/<name>_after.raw`. Totals are
stored exactly as returned.

Honest scope: proven only against the fake psspy. Every statement about what PSS/E does is
UNVERIFIED until the session of plan 01-10.

Standard library plus psse_job only, Python 3.7 syntax (D-05).
"""

from psse_job import constants, margin, psse_api
from psse_session import bundle, session

SECTION = "scaling"
EXPERIMENTS = ("swing_in_total", "clamp_at_limits_x1_5", "clamp_at_limits_x3", "q_with_p")
CLAMP_FACTORS = {"clamp_at_limits_x1_5": 1.5, "clamp_at_limits_x3": 3.0}
Q_WITH_P_INCREMENT_MW = 10.0
NO_RAW_EXPORT = "no raw export"


def _totals(totals):
    """CaseTotals as a dict, exactly as returned."""
    return {"load_mw": totals.load_mw, "gen_mw": totals.gen_mw}


def _snapshot(ctx, member):
    """`member` when PSS/E wrote it as RAW text, else None (the experiment is recorded anyway)."""
    if ctx.raw_writer is None:
        return None
    try:
        record = ctx.raw_writer(member)
    except Exception:  # noqa: BLE001 - a missing snapshot is recorded as null, never fatal
        return None
    return member if isinstance(record, dict) and record.get("status") == "ok" else None


def _operate(ctx, api, name, record):
    """The one operation of experiment `name` on the freshly loaded case."""
    if name == "swing_in_total":
        record["totals_before"] = _totals(api.read_totals())
    elif name in CLAMP_FACTORS:
        factor = CLAMP_FACTORS[name]
        own = api.read_totals()
        record["totals_before"] = _totals(own)
        record["targets"] = {"load_mw": own.load_mw * factor, "gen_mw": own.gen_mw * factor}
        api.scale_case(own.load_mw * factor, own.gen_mw * factor)
        record["totals_after"] = _totals(api.read_totals())
    else:
        city = constants.CITIES[0]
        sink_buses = list(ctx.mapping.cities[city].sink_buses)
        record["sink_buses"] = sink_buses
        record["increment_mw"] = Q_WITH_P_INCREMENT_MW
        api.define_subsystem(margin.SINK_SID, sink_buses)
        api.scale_load(margin.SINK_SID, Q_WITH_P_INCREMENT_MW)


def _experiment(ctx, name):
    record = {"name": name, "status": "ok", "detail": [], "totals_before": None,
              "totals_after": None, "targets": None, "sink_buses": None, "increment_mw": None,
              "before": None, "after": None}
    api = ctx.index.api
    try:
        api.load_case(ctx.case_path)
        record["before"] = _snapshot(ctx, "scaling/%s_before.raw" % name)
        _operate(ctx, api, name, record)
        record["after"] = _snapshot(ctx, "scaling/%s_after.raw" % name)
    except (psse_api.PsseCallError, ValueError) as error:
        record["status"] = "failed"
        record["detail"] = [bundle.class_word(error)]
    except Exception as exc:  # noqa: BLE001 - recorded as the class only, never the text
        record["status"] = "failed"
        record["detail"] = [bundle.class_word(exc)]
    return record


def run(ctx):
    """The scaling section; see the module docstring. Returns a session.SectionResult."""
    if ctx.index is None:
        # failed, not skipped: "skipped" means "--only did not ask for it" (as in the network section)
        ctx.results[SECTION] = {}
        return session.SectionResult("failed", ("no case index", ctx.index_stage or "internal"), {})
    records = [_experiment(ctx, name) for name in EXPERIMENTS]
    ctx.work.add_json(
        "scaling/experiments.json", {"experiments": records, "no_raw_export": ctx.raw_writer is None},
        SECTION)
    ctx.results[SECTION] = dict((record["name"], record["status"]) for record in records)
    detail = []
    for record in records:
        for word in record["detail"]:
            if word not in detail:
                detail.append(word)
    if ctx.raw_writer is None:
        detail.append(NO_RAW_EXPORT)
    ok = sum(1 for record in records if record["status"] == "ok")
    counts = {"experiments": len(records), "experiments_ok": ok}
    status = "ok" if ok == len(records) and ctx.raw_writer is not None else "failed"
    return session.SectionResult(status, tuple(detail), counts)
