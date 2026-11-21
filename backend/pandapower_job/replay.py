"""
The replay of the recorded PSS/E runs through pandapower (pandapower-solver Phase 4, plan 04-03:
AGR-01; decisions D-01 and D-04).

What is replayed, and from what. Each recorded run of a snapshot (`pandapower_job.recorded`) is run
again through the unchanged study of `psse_job.study` on the pandapower engine, with that run's own
stored ratings (rebuilt from its `ratings_used`, never from the live ratings view), the recorded
PSE-02 settings and the converted network. The two sides, the recorded rows and the replayed
results, are compared by `pandapower_job.agree`, which also decides the verdict.

What this module reads. The snapshot (already validated, a plain data structure) and the files named
by its caller: the converted network, the mapping, and the recorded settings. It imports no database
driver, no network module and no writer-side module of the PSS/E job, and it never calls
`job.run_once`, `writer.write_run` or `writer.record_failure`; the tests prove it with an import
walk, a fresh interpreter and a full replay with every connection blocked and the writer entry
points replaced by recorders.

What is kept. A failed study is a failed run and never an exclusion; only a run whose recorded
inputs differ from the local ones (mapping hash, case hash) or whose rows or ratings are unusable is
excluded, with a reason from `agree.EXCLUSION_REASONS`. Anything this module keeps about a failed
study is the stage word, never a message (a message can carry a path or a value).
"""

import collections

from psse_job import constants, contract, ratings, run_record
from pandapower_job import agree, engine, recorded

SELECTION_AMPS_RELATIVE_TOLERANCE = 1e-6


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _positive_finite(value):
    return _is_number(value) and value == value and value not in (float("inf"), float("-inf")) \
        and value > 0


def _time(value):
    return None if value is None else ratings.parse_ts(value)


def selection_from_ratings_used(ratings_used):
    """
    The `ratings.Selection` that produced a stored `ratings_used`, or None when an entry is
    unusable. One `ratings.RatingChoice` per city of constants.CITIES from that city's stored
    entry; the core fields source, fallback_reason, rating_amps_per_conductor,
    subconductors_per_phase and rating_amps_circuit are required, the rest default to None (the
    static amps to the constant). Unusable: a missing core field, amps that are not finite and
    positive, a count that is not a positive integer, a source outside constants.SOURCES, or amps
    times count differing from rating_amps_circuit by more than 1e-6 relative.
    """
    if not isinstance(ratings_used, dict):
        return None
    choices = {}
    for city in constants.CITIES:
        item = ratings_used.get(city)
        if not isinstance(item, dict):
            return None
        try:
            source = item["source"]
            reason = item["fallback_reason"]
            amps = item["rating_amps_per_conductor"]
            count = item["subconductors_per_phase"]
            circuit = item["rating_amps_circuit"]
        except KeyError:
            return None
        if source not in constants.SOURCES or not _positive_finite(amps) or not _positive_finite(
                circuit):
            return None
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            return None
        if abs(amps * count - circuit) > SELECTION_AMPS_RELATIVE_TOLERANCE * max(
                abs(amps * count), abs(circuit)):
            return None
        static = item.get("static_rating_amps_per_conductor")
        if static is None:
            static = constants.STATIC_RATINGS_AMPS_PER_CONDUCTOR[city]
        try:
            choices[city] = ratings.RatingChoice(
                city=city, source=source, fallback_reason=reason, amps_per_conductor=float(amps),
                subconductors_per_phase=count, amps_circuit=float(circuit),
                static_amps_per_conductor=static,
                row_valid_time=_time(item.get("city_rating_valid_time")),
                row_computed_at=_time(item.get("city_rating_computed_at")),
                row_run_id=item.get("city_rating_run_id"),
                row_status=item.get("city_rating_status"),
                row_config_fingerprint=item.get("config_fingerprint"),
                age_minutes=item.get("age_minutes"),
                server_is_stale=item.get("server_is_stale"),
                server_is_provisional=item.get("server_is_provisional"))
        except (ValueError, TypeError, OverflowError):
            return None
    return ratings.Selection(choices, None, 0)


RunOutcome = collections.namedtuple("RunOutcome", ["run_id", "status", "reason", "comparison"])
ReplayResult = collections.namedtuple("ReplayResult", ["gate", "outcomes", "configurations"])


def _default_runner(prepared):
    def run(selection):
        return prepared.study(selection, None)
    return run


def replay_snapshot(snapshot, backend, network_path, mapping_path, session_case_sha256,
                    allow_placeholder=False, runner=None):
    """
    Replay every eligible run of `snapshot` and judge it (AGR-01). `runner`, when given, is called
    as runner(selection) and returns `contract.StudyResults`; the default runs the prepared study
    on the real solver. Returns a ReplayResult.
    """
    prepared = engine.prepare_run(backend, network_path, mapping_path, allow_placeholder)
    run = _default_runner(prepared) if runner is None else runner
    compared, exclusions, outcomes = [], [], []
    runs = recorded.by_run(snapshot)
    for item in runs:
        row = item.run
        run_id = row["run_id"]
        if row["outcome"] == "failed":
            exclusions.append((run_id, "failed_run"))
            continue
        if row["mapping_sha256"] != prepared.mapping_sha256:
            exclusions.append((run_id, "mapping_hash_differs"))
            continue
        if row["case_sha256"] != session_case_sha256:
            exclusions.append((run_id, "case_hash_differs"))
            continue
        selection = selection_from_ratings_used(row["ratings_used"])
        results = run(selection)
        run_record.validate_results(results, selection)
        comparison = agree.compare_run(
            agree.side_from_recorded(row, item.dispatch, item.margins, item.contingencies),
            agree.side_from_results(results))
        compared.append((run_id, comparison))
        outcomes.append(RunOutcome(run_id, "passed" if comparison.passed else "failed", None,
                                   comparison))
    gate = agree.gate(compared, exclusions, len(runs), len(compared))
    return ReplayResult(gate, outcomes, len(compared))
