"""
Offline proofs of the run record, the study-result validation, the row building and the DDL
column contract of the PSS/E job (pss-e-integration Phase 1, WB-01, WB-02, D-02, D-04).

`psse_job.run_record` turns a run's context, rating selection and study outcome into exactly
one psse_run row; `validate_results` refuses a malformed study result before any write;
`psse_job.contract` holds the column tuples every INSERT is built from, and
`test_contract_columns_match_reference_ddl` fails when they drift from
docs/data-science/schema/psse_results_v1.sql. No database, no network. Every planted secret is
assembled from pieces so backend/tests/secret_scan_test.py never matches this file.

Follows backend/tests/psse_ratings_test.py (module-level imports, plain asserts, no test
classes).
"""

import ast
import copy
import datetime
import hashlib
import json
import math
import os
import re

import pytest

import psse_fakes
from psse_job import constants, contract, ratings, run_record

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 10, 28, 14, 7, 30, tzinfo=UTC)
FINISHED = NOW + datetime.timedelta(seconds=90)

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_DDL_PATH = os.path.join(_REPO_ROOT, "docs", "data-science", "schema", "psse_results_v1.sql")
_PSSE_JOB_DIR = os.path.join(_REPO_ROOT, "backend", "psse_job")


# --------------------------------------------------------------------------- helpers

def _context(started=NOW, run_id="psse-20261028T140730Z-0000000a"):
    return contract.RunContext(
        run_id=run_id, started_at=started, case_id="summer_peak_case",
        case_sha256="ab" * 32, mapping_sha256="cd" * 32, job_version="abc1234",
    )


def _selection(provisional=True, age_minutes=10.0, cities=None, now=NOW):
    rows = psse_fakes.latest_rows(now, provisional=provisional, age_minutes=age_minutes, cities=cities)
    return ratings.select_ratings(psse_fakes.fake_fetch(rows), now)


def _ok_selection():
    return _selection(provisional=False)


def _read_failed_selection():
    def boom():
        raise ratings.ReadFailed("latest_rating read failed: HTTP 500")
    return ratings.select_ratings(boom, NOW)


def _record(selection=None, results=None, failure=None, started=NOW, finished=FINISHED):
    selection = _ok_selection() if selection is None else selection
    if failure is None and results is None:
        results = psse_fakes.fake_results(selection)
    return run_record.build_run_record(
        _context(started=started), selection, finished, results=results, failure=failure
    )


def _planted_url_and_pair():
    secret = "hunter2" + "hunter2"
    url = "postgresql" + "://" + "someone" + ":" + secret + "@" + "db.example.invalid" + ":5432/postgres"
    return secret, url, "pass" + "word=" + secret


# --------------------------------------------------------------------------- record

def test_record_every_field_for_ok_fallback_failed():
    """The record has the 17 psse_run client columns, in DDL order, for ok, fallback and failed runs."""
    columns = list(contract.PSSE_RUN_COLUMNS)
    assert len(columns) == 17

    ok = _record(_ok_selection())
    assert list(ok) == columns
    assert ok["outcome"] == "ok" and ok["failed_stage"] is None and ok["error"] is None
    assert ok["ratings_read_error"] is None
    assert ok["run_id"] == "psse-20261028T140730Z-0000000a"
    assert ok["slot_time"] == datetime.datetime(2026, 10, 28, 14, 0, tzinfo=UTC)
    assert ok["started_at"] == NOW and ok["finished_at"] == FINISHED
    assert ok["case_id"] == "summer_peak_case"
    assert ok["case_sha256"] == "ab" * 32 and ok["mapping_sha256"] == "cd" * 32
    assert ok["rate_set"] == "RATEA" and ok["psse_version"] == "35.6.0"
    assert ok["n_contingencies"] == 3 and ok["n_contingencies_with_results"] == 2
    assert ok["job_version"] == "abc1234"
    assert all(ok["ratings_used"][city]["source"] == "city_rating" for city in constants.CITIES)

    fallback = _record(_selection())
    assert list(fallback) == columns
    assert fallback["outcome"] == "fallback" and fallback["error"] is None
    assert fallback["ratings_used"]["AUSTIN"]["fallback_reason"] == "provisional"

    read_failed = _record(_read_failed_selection())
    assert list(read_failed) == columns
    assert read_failed["outcome"] == "fallback"
    assert read_failed["ratings_read_error"] == "latest_rating read failed: HTTP 500"
    assert read_failed["ratings_used"]["EL_PASO"]["fallback_reason"] == "read_failed"

    failed = _record(_selection(), failure=contract.Failure("load_flow", "load flow did not converge"))
    assert list(failed) == columns
    assert failed["outcome"] == "failed"
    assert failed["failed_stage"] == "load_flow" and failed["error"] == "load flow did not converge"
    assert failed["rate_set"] is None and failed["psse_version"] is None
    assert failed["n_contingencies"] is None and failed["n_contingencies_with_results"] is None
    assert sorted(failed["ratings_used"]) == sorted(constants.CITIES)
    assert failed["ratings_used"]["AUSTIN"]["line_voltage_kv"] is None


def test_record_outcome_rule():
    """ok only when all four cities used city_rating; one static city, or a failed read, is fallback."""
    assert _record(_ok_selection())["outcome"] == "ok"
    three = _selection(provisional=False, cities=["AUSTIN", "CORPUS_CHRISTI", "MIDLAND"])
    assert three.choices["EL_PASO"].source == constants.SOURCE_STATIC
    assert _record(three)["outcome"] == "fallback"
    assert _record(_selection(provisional=False, age_minutes=200.0))["outcome"] == "fallback"
    read_failed = _record(_read_failed_selection())
    assert read_failed["outcome"] == "fallback"  # D-02: never failed
    assert run_record.outcome_for(_ok_selection(), True) == "failed"
    assert run_record.outcome_for(_ok_selection(), False) == "ok"


def test_record_slot_time_is_the_utc_hour_floor():
    """slot_time is the UTC hour floor of started_at, also for an aware time at +05:30."""
    def slot(started):
        return _record(started=started, finished=started + datetime.timedelta(seconds=1))["slot_time"]

    hour14 = datetime.datetime(2026, 10, 28, 14, 0, 0, tzinfo=UTC)
    hour15 = datetime.datetime(2026, 10, 28, 15, 0, 0, tzinfo=UTC)
    assert slot(datetime.datetime(2026, 10, 28, 14, 0, 0, tzinfo=UTC)) == hour14
    assert slot(datetime.datetime(2026, 10, 28, 14, 59, 59, 999999, tzinfo=UTC)) == hour14
    assert slot(datetime.datetime(2026, 10, 28, 15, 0, 0, tzinfo=UTC)) == hour15
    plus_530 = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    assert slot(datetime.datetime(2026, 10, 28, 19, 45, 0, tzinfo=plus_530)) == hour14  # 14:15Z
    assert run_record.slot_of(datetime.datetime(2026, 10, 28, 19, 45, tzinfo=plus_530)).tzinfo is not None
    with pytest.raises(ValueError):
        run_record.slot_of(datetime.datetime(2026, 10, 28, 14, 30))


def test_record_finished_equal_to_started_is_accepted():
    """A run that finishes the instant it started is recorded; an earlier finish or a naive time is not."""
    record = _record(finished=NOW)
    assert record["finished_at"] == record["started_at"]
    with pytest.raises(ValueError):
        _record(finished=NOW - datetime.timedelta(microseconds=1))
    with pytest.raises(ValueError):
        _record(finished=datetime.datetime(2026, 10, 28, 14, 9))
    with pytest.raises(ValueError):
        _record(started=datetime.datetime(2026, 10, 28, 14, 7), finished=FINISHED)
    with pytest.raises(ValueError):
        run_record.build_run_record(_context(), _ok_selection(), FINISHED)  # no results and no failure


def test_record_empty_error_message_gets_a_label():
    """A failure with an empty exception message still stores a non-empty error naming class and stage."""
    failure = run_record.failure_from_exception("load_flow", RuntimeError())
    assert failure.stage == "load_flow"
    assert failure.message == "RuntimeError during load_flow"
    assert run_record.failure_from_exception("load_flow", RuntimeError("boom")).message == "RuntimeError: boom"
    record = _record(_selection(), failure=failure)
    assert record["error"] == "RuntimeError during load_flow"
    assert _record(_selection(), failure=contract.Failure("dispatch", ""))["error"] == "dispatch failed"
    assert run_record.as_failed(_record(), "write", "")["error"] == "write failed"
    empty_study = run_record.failure_from_exception("load_flow", contract.StudyFailed("mapping", ""))
    assert empty_study == contract.Failure("mapping", "StudyFailed during mapping")


def test_record_unknown_stage_maps_to_internal():
    """A stage outside the DDL's list is recorded as 'internal' with the given stage in the message."""
    plain = run_record.failure_from_exception("not_a_stage", ValueError("bad"))
    assert plain == contract.Failure("internal", "ValueError: bad")
    study = run_record.failure_from_exception("load_case", contract.StudyFailed("bogus", "went wrong"))
    assert study.stage == "internal"
    assert study.message.startswith("stage 'bogus': ") and "went wrong" in study.message
    own = run_record.failure_from_exception("load_case", contract.StudyFailed("mapping", "no branch"))
    assert own == contract.Failure("mapping", "no branch")
    record = _record(_selection(), failure=contract.Failure("bogus", "x"))
    assert record["failed_stage"] == "internal" and record["error"].startswith("stage 'bogus'")
    assert run_record.as_failed(_record(), "bogus", "x")["failed_stage"] == "internal"
    assert record["failed_stage"] in constants.FAILED_STAGES


def test_record_ratings_used_four_keys_in_order_and_deterministic():
    """ratings_used holds the four cities in CITIES order, keys in RATINGS_USED_KEYS order, as stable JSON."""
    first = _record(_selection())
    second = _record(_selection())
    assert list(first["ratings_used"]) == list(constants.CITIES)
    for city in constants.CITIES:
        assert list(first["ratings_used"][city]) == list(constants.RATINGS_USED_KEYS)
    assert json.dumps(first["ratings_used"], allow_nan=False) == json.dumps(second["ratings_used"], allow_nan=False)
    read_failed = _record(_read_failed_selection())
    assert list(read_failed["ratings_used"]) == list(constants.CITIES)
    json.dumps(read_failed["ratings_used"], allow_nan=False)


def test_record_merges_study_kv_and_mva_into_ratings_used():
    """Each city's line_voltage_kv and rating_mva come from that city's dispatch row."""
    selection = _selection()
    results = psse_fakes.fake_results(selection, line_voltage_kv=230.0)
    record = _record(selection, results=results)
    by_city = dict((row["city"], row) for row in results.dispatch)
    for city in constants.CITIES:
        entry = record["ratings_used"][city]
        assert entry["line_voltage_kv"] == 230.0
        assert entry["rating_mva"] == by_city[city]["applied_mva"]
        assert entry["rating_amps_per_conductor"] == by_city[city]["applied_amps_per_conductor"]
    assert _record(selection, failure=contract.Failure("load_flow", "x"))["ratings_used"]["AUSTIN"]["rating_mva"] is None


def test_redact_record_error_and_cut_after_redaction():
    """A 5000-character failure with a planted URL and password pair is redacted, then cut to 1000."""
    secret, url, pair = _planted_url_and_pair()
    message = "start " + url + " " + pair + " " + ("x" * 5000)
    record = _record(_selection(), failure=contract.Failure("load_flow", message))
    assert secret not in record["error"] and "db.example.invalid" not in record["error"]
    assert 0 < len(record["error"]) <= constants.ERROR_MAX_CHARS
    from_exception = run_record.failure_from_exception("load_flow", RuntimeError(message))
    assert secret not in from_exception.message and len(from_exception.message) <= constants.ERROR_MAX_CHARS
    failed = run_record.as_failed(_record(), "write", message)
    assert secret not in failed["error"] and len(failed["error"]) <= constants.ERROR_MAX_CHARS


def test_redact_ratings_read_error_is_capped():
    """ratings_read_error is redacted and cut to 1000 characters; None when the read worked."""
    secret, url, pair = _planted_url_and_pair()
    selection = _read_failed_selection()._replace(read_error="read failed " + url + " " + pair + (" y" * 3000))
    record = _record(selection)
    assert secret not in record["ratings_read_error"]
    assert 0 < len(record["ratings_read_error"]) <= constants.ERROR_MAX_CHARS
    assert _record(_ok_selection())["ratings_read_error"] is None


# --------------------------------------------------------------------------- labels

def test_new_run_id_matches_the_ddl_pattern():
    """run_id is psse-<UTC stamp>-<8 hex>, new on every call."""
    pattern = re.compile(r"^psse-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")
    first = run_record.new_run_id(NOW)
    assert pattern.match(first) and first.startswith("psse-20261028T140730Z-")
    assert first != run_record.new_run_id(NOW)
    plus_530 = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    assert run_record.new_run_id(NOW.astimezone(plus_530)).startswith("psse-20261028T140730Z-")
    with pytest.raises(ValueError):
        run_record.new_run_id(datetime.datetime(2026, 10, 28, 14, 7, 30))


def test_case_label_is_never_a_path():
    """case_id is the file name part only, at most 200 characters, never empty."""
    assert run_record.case_label("C:\\cases\\summer\\peak.sav") == "peak.sav"
    assert run_record.case_label("/data/cases/peak.sav") == "peak.sav"
    assert run_record.case_label("  peak.sav  ") == "peak.sav"
    assert run_record.case_label("a" * 500) == "a" * 200
    for empty in (None, "", "   ", "/", "C:\\cases\\"):
        assert run_record.case_label(empty) == "unknown"
    assert "/" not in run_record.case_label("x/y\\z") and "\\" not in run_record.case_label("x/y\\z")


def test_file_sha256(tmp_path):
    """The lowercase hex sha256 of the bytes, across chunks; None for a missing file."""
    path = tmp_path / "case.sav"
    data = bytes(bytearray(range(256))) * (3 * 4096 + 7)  # over one 1 MiB chunk
    path.write_bytes(data)
    assert run_record.file_sha256(str(path)) == hashlib.sha256(data).hexdigest()
    assert re.match(r"^[0-9a-f]{64}$", run_record.file_sha256(str(path)))
    assert run_record.file_sha256(str(tmp_path / "missing.sav")) is None


def test_job_version_env_then_git_then_unknown(monkeypatch):
    """PSSE_JOB_VERSION wins (stripped, cut to 40); else the git short hash; else 'unknown', never an error."""
    assert run_record.job_version({"PSSE_JOB_VERSION": "  v1.2.3  "}) == "v1.2.3"
    assert run_record.job_version({"PSSE_JOB_VERSION": "z" * 90}) == "z" * 40

    calls = []

    def fake_run(*args, **kwargs):
        calls.append(args[0])
        raise OSError("no git here")

    monkeypatch.setattr(run_record.subprocess, "run", fake_run)
    assert run_record.job_version({}) == "unknown"
    assert run_record.job_version({"PSSE_JOB_VERSION": "   "}) == "unknown"
    assert calls and calls[0][:2] == ["git", "rev-parse"]

    class Done(object):
        stdout = "abc1234\n"

    monkeypatch.setattr(run_record.subprocess, "run", lambda *a, **k: Done())
    assert run_record.job_version({}) == "abc1234"


# --------------------------------------------------------------------------- validate_results

def _scale_dispatch_row(results, factor):
    row = results.dispatch[0]
    for key, value in list(row.items()):
        if isinstance(value, float):
            row[key] = value * factor
    return results


def _set(path, value):
    """A mutator: results.<list>[index][key] = value."""
    name, index, key = path

    def mutate(results):
        getattr(results, name)[index][key] = value
        return results
    return mutate


def _delete(path):
    name, index, key = path

    def mutate(results):
        del getattr(results, name)[index][key]
        return results
    return mutate


def _too_many_rows(results):
    template = results.contingencies[0]
    rows = []
    for index in range(run_record.MAX_CONTINGENCY_ROWS + 1):
        row = dict(template)
        row["contingency_id"] = "c%d" % index
        rows.append(row)
    return results._replace(contingencies=rows, n_contingencies=len(rows))


def _duplicate_key(results):
    results.contingencies.append(dict(results.contingencies[0]))
    return results


_NAN = float("nan")
_INF = float("inf")

_REJECTIONS = [
    ("not a StudyResults", False, lambda r: r._asdict(), "not a StudyResults"),
    ("dispatch city missing", False, lambda r: r._replace(dispatch=r.dispatch[:3]), "no row for EL_PASO"),
    ("dispatch unknown city", False, _set(("dispatch", 0, "city"), "DALLAS"), "unknown city"),
    ("dispatch duplicate city", False, lambda r: r._replace(dispatch=r.dispatch + [dict(r.dispatch[0])]), "more than one row"),
    ("static city reported as city_rating", False, _set(("dispatch", 0, "rating_source"), "city_rating"), "rating_source"),
    ("fallback reason differs", False, _set(("dispatch", 0, "fallback_reason"), "stale"), "fallback_reason"),
    ("dispatch row scaled by 0.95", False, lambda r: _scale_dispatch_row(r, 0.95), "applied_amps_per_conductor"),
    ("subconductors differ", False, _set(("dispatch", 0, "subconductors_per_phase"), 3), "subconductors_per_phase"),
    ("applied_amps_circuit identity", False, _set(("dispatch", 1, "applied_amps_circuit"), 1234.0), "applied_amps_circuit"),
    ("applied_mva identity", False, lambda r: _scale_applied_mva(r), "sqrt(3) x kV"),
    ("power_factor above 1", False, lambda r: _set_power_factor(r, 1.5), "power_factor must be in"),
    ("dispatched_mva identity", False, lambda r: _scale_key(r, "dispatched_mva", 0.9), "dispatched_mva"),
    ("limiting_factor wrong", False, _set(("dispatch", 2, "limiting_factor"), "voltage_stability"), "limiting_factor"),
    ("double is NaN", False, _set(("dispatch", 0, "voltage_limit_mva"), _NAN), "voltage_limit_mva"),
    ("double is infinite", False, _set(("dispatch", 1, "dispatched_mw"), _INF), "dispatched_mw"),
    ("double missing", False, _delete(("dispatch", 3, "power_factor")), "power_factor"),
    ("double is text", False, _set(("dispatch", 0, "line_voltage_kv"), "345"), "line_voltage_kv"),
    ("static city carries a link", False, _set(("dispatch", 0, "city_rating_valid_time"), NOW), "link"),
    ("city_rating link differs", True, _set(("dispatch", 0, "city_rating_valid_time"), NOW), "link"),
    ("margin city missing", False, lambda r: r._replace(margins=r.margins[:2]), "no row for"),
    ("margin voltage limit differs", False, lambda r: _scale_margin_limit(r), "voltage_limit_mva"),
    ("margin_mw missing", False, _delete(("margins", 0, "margin_mw")), "margin_mw"),
    ("contingency_id missing", False, _delete(("contingencies", 0, "contingency_id")), "contingency_id"),
    ("violation_kind outside vocabulary", False, _set(("contingencies", 0, "violation_kind"), "overheat"), "violation_kind"),
    ("element_type outside vocabulary", False, _set(("contingencies", 0, "element_type"), "line"), "element_type"),
    ("unit outside vocabulary", False, _set(("contingencies", 0, "unit"), "kA"), "unit"),
    ("contingency key repeated", False, _duplicate_key, "repeats the key"),
    ("too many contingency rows", False, _too_many_rows, "exceed the limit"),
    ("n_contingencies not an int", False, lambda r: r._replace(n_contingencies="3"), "n_contingencies"),
    ("n_contingencies negative", False, lambda r: r._replace(n_contingencies=-1), "n_contingencies"),
    ("n_contingencies smaller than distinct ids", False, lambda r: r._replace(n_contingencies=1), "smaller"),
]


def _scale_applied_mva(results):
    """Break only the applied_mva identity: everything derived from it moves with it."""
    row = results.dispatch[0]
    for key in ("applied_mva", "dispatched_mva", "dispatched_amps_circuit",
                "dispatched_amps_per_conductor", "dispatched_mw"):
        row[key] *= 1.01
    return results


def _set_power_factor(results, value):
    row = results.dispatch[0]
    row["power_factor"] = value
    row["dispatched_mw"] = row["dispatched_mva"] * value
    return results


def _scale_key(results, key, factor):
    results.dispatch[0][key] *= factor
    return results


def _scale_margin_limit(results):
    results.margins[0]["voltage_limit_mva"] *= 1.5
    return results


@pytest.mark.parametrize(
    "fresh, mutate, fragment",
    [pytest.param(fresh, mutate, fragment, id=name) for name, fresh, mutate, fragment in _REJECTIONS],
)
def test_validate_results_rejects(fresh, mutate, fragment):
    """Each malformed study result is refused with a message naming the problem, before any write."""
    assert len(_REJECTIONS) >= 14
    selection = _ok_selection() if fresh else _selection()
    good = psse_fakes.fake_results(selection)
    run_record.validate_results(copy.deepcopy(good), selection)  # the unmodified result is fine
    bad = mutate(copy.deepcopy(good))
    with pytest.raises(contract.ResultsInvalid) as caught:
        run_record.validate_results(bad, selection)
    assert fragment in str(caught.value)


def test_validate_results_accepts_zero_violations():
    """A clean study (no contingency row) is valid, for ok and fallback selections alike."""
    for selection in (_selection(), _ok_selection(), _read_failed_selection()):
        results = psse_fakes.fake_results(selection, violations=0, n_contingencies=3)
        assert results.contingencies == []
        assert run_record.validate_results(results, selection) is None
        record = _record(selection, results=results)
        assert record["n_contingencies"] == 3 and record["n_contingencies_with_results"] == 0
    one = psse_fakes.fake_results(_selection(), violations=1, n_contingencies=1)
    assert run_record.validate_results(one, _selection()) is None


# --------------------------------------------------------------------------- result rows

def test_result_rows_columns_and_values():
    """Each table's rows have exactly its column tuple; run_outcome follows the record; strays raise."""
    selection = _selection()
    results = psse_fakes.fake_results(selection)
    record = _record(selection, results=results)
    rows = run_record.result_rows(record, results)
    assert sorted(rows) == sorted(contract.RESULT_TABLES)
    assert [len(rows[table]) for table in contract.RESULT_TABLES] == [4, 4, 2]
    for table in contract.RESULT_TABLES:
        for row in rows[table]:
            assert list(row) == list(contract.TABLE_COLUMNS[table])
            assert row["run_id"] == record["run_id"] and row["run_outcome"] == record["outcome"]

    stray = copy.deepcopy(results)
    stray.dispatch[0]["power_factr"] = 0.95
    with pytest.raises(ValueError) as caught:
        run_record.result_rows(record, stray)
    assert "power_factr" in str(caught.value)
    for key in ("run_id", "run_outcome"):
        spoofed = copy.deepcopy(results)
        spoofed.margins[0][key] = "x"
        with pytest.raises(ValueError):
            run_record.result_rows(record, spoofed)

    sparse = copy.deepcopy(results)
    del sparse.margins[0]["details"]
    sparse.margins[1]["margin_pct"] = _NAN
    sparse.margins[2]["min_voltage_pu"] = _INF
    sparse_rows = run_record.result_rows(record, sparse)[contract.MARGIN_TABLE]
    assert sparse_rows[0]["details"] is None
    assert sparse_rows[1]["margin_pct"] is None and sparse_rows[2]["min_voltage_pu"] is None
    assert run_record.finite(1) == 1.0 and run_record.finite(None) is None
    assert run_record.finite("x") is None and run_record.finite(math.inf) is None


# --------------------------------------------------------------------------- the DDL contract

_SQL_TYPES = r"(text\[\]|double precision|timestamptz|integer|boolean|jsonb|text)"
_COLUMN_LINE = re.compile(r"^\s+([a-z_0-9]+)\s+" + _SQL_TYPES + r"(?=[\s,]|$)")


def _ddl_column_names(table):
    """Column names of one create-table block of the reference DDL, in order (one column per line)."""
    with open(_DDL_PATH, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("create table if not exists %s (" % table))
    names = []
    for line in lines[start + 1:]:
        if line.startswith(");"):
            break
        match = _COLUMN_LINE.match(line)
        if match:
            names.append(match.group(1))
    return names


def test_contract_columns_match_reference_ddl():
    """Each table's column tuple plus schema_version and created_at equals the DDL's columns, in order."""
    assert sorted(contract.TABLE_COLUMNS) == sorted([
        contract.PSSE_RUN_TABLE, contract.DISPATCH_TABLE, contract.MARGIN_TABLE, contract.CONTINGENCY_TABLE,
    ])
    for table, columns in contract.TABLE_COLUMNS.items():
        ddl = _ddl_column_names(table)
        assert len(ddl) >= 12, "%s: the DDL parser found only %d columns" % (table, len(ddl))
        assert list(columns) + list(contract.DB_DEFAULT_COLUMNS) == ddl, table
        assert contract.insert_sql(table).count("%(") == len(columns)
    assert list(contract.DB_DEFAULT_COLUMNS) == ["schema_version", "created_at"]
    assert contract.RESULT_TABLES == (contract.DISPATCH_TABLE, contract.MARGIN_TABLE, contract.CONTINGENCY_TABLE)
    jsonb = [name for name in contract.JSONB_COLUMNS]
    for table, columns in contract.TABLE_COLUMNS.items():
        sql = contract.insert_sql(table)
        for column in columns:
            assert ("%%(%s)s::jsonb" % column in sql) == (column in jsonb)
    with pytest.raises(ValueError):
        contract.insert_sql("public.pg_authid")


def _word(text, word):
    return re.search(r"\b%s\b" % word, text, re.IGNORECASE) is not None


def test_contract_sql_never_updates_or_deletes():
    """The only SQL the job holds is INSERT; no string in contract.py or writer.py starts with update or delete."""
    assert contract.INSERT_RUN_SQL.endswith("on conflict (run_id) do nothing returning run_id")
    statements = [contract.INSERT_RUN_SQL] + list(contract.INSERT_RESULT_SQL.values())
    assert len(contract.INSERT_RESULT_SQL) == 3
    for sql in statements:
        assert sql.startswith("insert into public.psse_")
        assert not _word(sql, "update") and not _word(sql, "delete")
    for name in ("contract.py", "writer.py"):
        with open(os.path.join(_PSSE_JOB_DIR, name), encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)):
                body = getattr(node, "body", [])
                if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
                    docstrings.add(id(body[0].value))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
                assert not re.match(r"\s*(update|delete)\b", node.value, re.IGNORECASE), (name, node.value)
