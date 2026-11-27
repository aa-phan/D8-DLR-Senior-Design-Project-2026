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
import os

from psse_job import constants, contract, ratings, run_record
from pandapower_job import agree, engine, recorded

SELECTION_AMPS_RELATIVE_TOLERANCE = 1e-6

REFUSAL_REASONS = (
    "snapshot_missing", "records_missing", "mapping_missing", "network_missing",
    "mapping_unusable", "placeholder_settings",
)


class ReplayRefused(ValueError):
    """The replay cannot start. `reason` is one of REFUSAL_REASONS; the message holds the reason
    only (no path, no value). There is no override: a refusal is never a replay on invented
    values."""

    def __init__(self, reason):
        if reason not in REFUSAL_REASONS:
            raise ValueError("not a refusal reason")
        self.reason = reason
        ValueError.__init__(self, "replay refused: %s" % reason)


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
Plan = collections.namedtuple("Plan", ["groups", "exclusions"])

_HEX_DIGITS = frozenset("0123456789abcdef")


def configuration_key(mapping_sha256, selection):
    """What the replayed results depend on, besides the network and the settings the whole
    replay shares: the mapping and, per city, the source, fallback reason, amps and count."""
    return (mapping_sha256, tuple(
        (city, selection.choices[city].source, selection.choices[city].fallback_reason,
         selection.choices[city].amps_per_conductor,
         selection.choices[city].subconductors_per_phase)
        for city in constants.CITIES))


def _is_hash(value):
    return isinstance(value, str) and len(value) == 64 and set(value) <= _HEX_DIGITS


def _decide(item, local_mapping_sha256, session_case_sha256):
    """(reason, selection): the first exclusion reason of a run, in the order of
    agree.EXCLUSION_REASONS, or None with the selection to replay."""
    row = item.run
    if row.get("outcome") == "failed":
        return "failed_run", None
    run_mapping = row.get("mapping_sha256")
    if not _is_hash(run_mapping):
        return "mapping_hash_missing", None
    if run_mapping != local_mapping_sha256:
        return "mapping_hash_differs", None
    run_case = row.get("case_sha256")
    if not _is_hash(run_case) or not _is_hash(session_case_sha256):
        return "case_hash_missing", None
    if run_case != session_case_sha256:
        return "case_hash_differs", None
    selection = selection_from_ratings_used(row.get("ratings_used"))
    if selection is None:
        return "ratings_unusable", None
    if not recorded.complete(item):
        return "rows_incomplete", None
    return None, selection


def plan(runs, local_mapping_sha256, session_case_sha256):
    """
    The plan stage, pure. `runs` is a list of recorded.RecordedRun in slot order. Returns
    Plan(groups, exclusions): the eligible runs grouped by configuration_key (an ordered mapping
    from key to a list of (RecordedRun, Selection)) and the excluded runs as (run_id, reason)
    pairs. The reason is the first that applies, in the order of agree.EXCLUSION_REASONS: a failed
    run; no or a different mapping hash; no (or no session) or a different case hash; unusable
    ratings; rows that are not a full result set. An excluded run is never replayed.
    """
    groups = collections.OrderedDict()
    exclusions = []
    for item in runs:
        reason, selection = _decide(item, local_mapping_sha256, session_case_sha256)
        if reason is not None:
            exclusions.append((item.run["run_id"], reason))
            continue
        key = configuration_key(local_mapping_sha256, selection)
        groups.setdefault(key, []).append((item, selection))
    return Plan(groups, exclusions)


def _is_file(path):
    try:
        return os.path.isfile(path)
    except (TypeError, ValueError):
        return False


def _default_runner(prepared):
    def run(selection):
        return prepared.study(selection, None)
    return run


def _stage_word(stage):
    return stage if stage in constants.FAILED_STAGES else "internal"


def _replay_group(run, selection):
    """(replayed Side, None) for one configuration, or (None, stage word). Only StudyFailed and
    ResultsInvalid are failures of the run; any other exception propagates. No message is kept."""
    try:
        results = run(selection)
        run_record.validate_results(results, selection)
    except contract.StudyFailed as problem:
        return None, _stage_word(problem.stage)
    except contract.ResultsInvalid:
        return None, "validate_results"
    return agree.side_from_results(results), None


def replay_snapshot(snapshot, backend, network_path, mapping_path, session_case_sha256,
                    allow_placeholder=False, runner=None):
    """
    Replay every eligible run of `snapshot` and judge it (AGR-01, AGR-02, D-04). The mapping is
    prepared once; a run is replayed only when its recorded mapping hash equals that of the local
    mapping and its case hash equals `session_case_sha256`; the others are excluded under a
    closed reason and listed. Each distinct configuration is replayed once, with the ratings
    stored in its first run, and every run of the configuration is compared with those results.

    `runner`, when given, is called as runner(selection) and returns `contract.StudyResults`
    (a test seam); the default runs the prepared study on the real solver. A runner that raises
    StudyFailed, or results that fail run_record.validate_results, make every run of that
    configuration a failed run, never an exclusion. `allow_placeholder` only lets the mapping
    loader read a file whose own flag says placeholder (the test fixtures write it false); the
    owner's command never sets it, and placeholder settings are always refused.

    Raises ReplayRefused for placeholder settings, a missing network or mapping file, or a mapping
    that does not load. Returns a ReplayResult(gate, outcomes, configurations).
    """
    if engine.is_placeholder(backend):
        raise ReplayRefused("placeholder_settings")
    if not _is_file(network_path):
        raise ReplayRefused("network_missing")
    if not _is_file(mapping_path):
        raise ReplayRefused("mapping_missing")
    prepared = engine.prepare_run(backend, network_path, mapping_path, allow_placeholder)
    if prepared.mapping_sha256 is None:
        raise ReplayRefused("mapping_unusable")
    run = _default_runner(prepared) if runner is None else runner

    runs = recorded.by_run(snapshot)
    planned = plan(runs, prepared.mapping_sha256, session_case_sha256)
    comparisons = {}
    for members in planned.groups.values():
        replayed, stage = _replay_group(run, members[0][1])
        for item, _ in members:
            row = item.run
            if stage is not None:
                comparisons[row["run_id"]] = agree.replay_failed(stage)
                continue
            comparisons[row["run_id"]] = agree.compare_run(
                agree.side_from_recorded(row, item.dispatch, item.margins, item.contingencies),
                replayed)
    reasons = dict(planned.exclusions)
    outcomes, compared = [], []
    for item in runs:
        run_id = item.run["run_id"]
        if run_id in reasons:
            outcomes.append(RunOutcome(run_id, "excluded", reasons[run_id], None))
            continue
        comparison = comparisons[run_id]
        compared.append((run_id, comparison))
        failure = None
        if not comparison.passed:
            failure = next((found.detail for found in comparison.findings
                            if found.check == "replay_failed"), None)
        outcomes.append(RunOutcome(
            run_id, "passed" if comparison.passed else "failed", failure, comparison))
    configurations = len(planned.groups)
    gate = agree.gate(compared, planned.exclusions, len(snapshot.runs), configurations)
    return ReplayResult(gate, outcomes, configurations)
