"""
SCH-02 gap-check proofs on a throwaway local Postgres (pss-e-integration Phase 3, plan 03-02):
`docs/data-science/schema/psse_run_gaps.sql` lists every UTC hour between the first recorded
run and the last closed hour that has no complete result set, and `psse_job.gaps.run` runs that
file as the writer credential on a read-only session and prints it.

Skipped unless `DLR_TEST_PG_AUTOSTART=1` (the fixture runs initdb and pg_ctl under pytest's tmp
dir and stops the cluster afterwards) or `DLR_TEST_DATABASE_URL` names a local throwaway
database (host 127.0.0.1, localhost or ::1; anything else fails the test). With
`PSSE_REQUIRE_PG=1` a missing database, driver or binary fails instead of skipping. They never
touch Supabase.

Honest scope: these tests prove the statement's logic and the wrapper on local Postgres. They do
not prove that the live table shows the real laptop's hours, that the laptop clock agrees with
the database, or daylight-saving effects (the statement works in UTC only); those are the
laptop session's induced-gap step and stay UNVERIFIED until then.

Follows backend/tests/psse_study_job_test.py (module-level imports, plain asserts, no classes).
"""

import datetime
import io
import os
import random
import sys

import pytest

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import psse_local_pg as pg_helper  # noqa: E402
from psse_job import gaps, writer  # noqa: E402

WRITER_ROLE = "dlr_psse_writer"
HOUR = datetime.timedelta(hours=1)
UTC = datetime.timezone.utc


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    """Admin URL of a database that already carries the Phase 4 migrations and the reference DDL."""
    with pg_helper.cluster(tmp_path_factory) as admin_url:
        pg_helper.apply_schema(admin_url)
        yield admin_url


@pytest.fixture
def clean_pg(pg):
    """The same database with the four result tables empty."""
    pg_helper.reset(pg)
    return pg


def _current_slot(admin_url):
    """The database's own current UTC hour, as an aware datetime."""
    rows = pg_helper.admin_rows(
        admin_url, "select (date_trunc('hour', now() at time zone 'UTC') at time zone 'UTC') as slot")
    return rows[0]["slot"].astimezone(UTC)


def _put(admin_conn, slot, outcome, n):
    """Insert one psse_run row started 15 minutes into `slot` (run row only, no result rows)."""
    started = slot + datetime.timedelta(minutes=15)
    run_id = pg_helper.make_run_id(n, started)
    if outcome == "failed":
        row = pg_helper.failed_run_row(run_id, started)
    else:
        row = pg_helper.valid_run_rows(run_id, started, outcome=outcome)["psse_run"][0]
    pg_helper.insert_rows(admin_conn, "psse_run", [row])


def _seed(admin_url, plan):
    """Insert `plan`, a list of (slot, outcome) pairs, as the superuser; run ids are unique."""
    import psycopg

    with psycopg.connect(admin_url, autocommit=True) as conn:
        for n, (slot, outcome) in enumerate(plan):
            _put(conn, slot, outcome, n + 1)


def _writer_url(admin_url):
    return pg_helper.role_url(admin_url, WRITER_ROLE)


def _env(admin_url):
    return {"SUPABASE_PSSE_DB_URL": _writer_url(admin_url)}


def _stable(admin_url, trial):
    """
    Reset the tables, read the current slot, run `trial(slot)` (which must return values, not
    assert) and accept the result only when the database's hour did not roll meanwhile; up to
    three attempts, then fail.
    """
    for _ in range(3):
        pg_helper.reset(admin_url)
        before = _current_slot(admin_url)
        result = trial(before)
        if _current_slot(admin_url) == before:
            return before, result
    pytest.fail("the database's UTC hour rolled during all three attempts")


def _iso(value):
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fetch(admin_url):
    conn = writer.connect(_writer_url(admin_url))
    try:
        return gaps.fetch_gaps(conn)
    finally:
        conn.close()


def test_tracer_gap_check_lists_the_missing_hours(clean_pg):
    def trial(s):
        _seed(clean_pg, [
            (s - 6 * HOUR, "fallback"),
            (s - 5 * HOUR, "fallback"), (s - 5 * HOUR, "ok"),
            (s - 3 * HOUR, "failed"),
            (s - 2 * HOUR, "failed"), (s - 2 * HOUR, "fallback"),
            (s, "fallback"),
        ])
        buffer = io.StringIO()
        code = gaps.run(_env(clean_pg), out=buffer)
        strict = gaps.run(_env(clean_pg), fail_on_gaps=True, out=io.StringIO())
        return code, strict, buffer.getvalue(), _fetch(clean_pg)

    s, (code, strict, text, rows) = _stable(clean_pg, trial)
    assert code == 0
    assert strict == 5

    gap_lines = [line for line in text.splitlines() if "no_run" in line or "failed_only" in line]
    assert [(line.split()[0], line.split()[1]) for line in gap_lines] == [
        (_iso(s - 4 * HOUR), "no_run"),
        (_iso(s - 3 * HOUR), "failed_only"),
        (_iso(s - 1 * HOUR), "no_run"),
    ]
    assert all(line.split()[0].endswith("Z") for line in gap_lines)
    assert "7 runs recorded" in text
    assert _iso(s - 6 * HOUR) in text
    assert _iso(s) in text

    assert [(r.slot_time.astimezone(UTC), r.gap_kind, r.runs, r.failed_runs) for r in rows] == [
        (s - 4 * HOUR, "no_run", 0, 0),
        (s - 3 * HOUR, "failed_only", 1, 1),
        (s - 1 * HOUR, "no_run", 0, 0),
    ]


def reference_gaps(runs, current_slot):
    """
    The independent oracle: `runs` is a list of (slot, outcome); returns the gaps as
    (slot, kind, runs, failed_runs) tuples. Plain loops, no SQL concepts: group the outcomes by
    slot, walk the hours from the first slot up to the hour before `current_slot`, list a slot
    with no outcome at all as no_run and a slot whose outcomes are all failed as failed_only.
    """
    by_slot = {}
    for slot, outcome in runs:
        by_slot.setdefault(slot, []).append(outcome)
    if not by_slot:
        return []
    found = []
    hour = min(by_slot)
    while hour < current_slot:
        outcomes = by_slot.get(hour)
        if outcomes is None:
            found.append((hour, "no_run", 0, 0))
        elif all(outcome == "failed" for outcome in outcomes):
            found.append((hour, "failed_only", len(outcomes), len(outcomes)))
        hour += HOUR
    return found


def _as_tuples(rows):
    return [(r.slot_time.astimezone(UTC), r.gap_kind, r.runs, r.failed_runs) for r in rows]


def _random_history(rng):
    """A history relative to the current hour: a list of (hours back, outcome); 0 is this hour."""
    while True:
        closed = rng.randint(3, 40)
        plan = []
        for back in range(closed, 0, -1):
            if rng.random() < 0.25:
                continue
            for _ in range(rng.randint(1, 3)):
                plan.append((back, rng.choice(("ok", "fallback", "failed"))))
        if rng.random() < 0.4:
            plan.append((0, rng.choice(("ok", "fallback", "failed"))))
        if plan:
            return plan


def test_gap_sql_matches_independent_reference_over_random_histories(clean_pg):
    rng = random.Random(20261103)
    nonempty = 0
    for trial_no in range(30):
        history = _random_history(rng)

        def trial(s, history=history):
            runs = [(s - back * HOUR, outcome) for back, outcome in history]
            _seed(clean_pg, runs)
            return runs, _fetch(clean_pg)

        s, (runs, rows) = _stable(clean_pg, trial)
        expected = reference_gaps(runs, s)
        nonempty += 1 if expected else 0
        assert _as_tuples(rows) == expected, "trial %d: %r" % (trial_no, history)
    # The seed must exercise the gap path, not only gap-free histories.
    assert nonempty >= 20


def test_gap_empty_table(clean_pg):
    def trial(s):
        buffer = io.StringIO()
        code = gaps.run(_env(clean_pg), out=buffer)
        strict = gaps.run(_env(clean_pg), fail_on_gaps=True, out=io.StringIO())
        return _fetch(clean_pg), code, strict, buffer.getvalue()

    _, (rows, code, strict, text) = _stable(clean_pg, trial)
    assert rows == []
    assert "no runs recorded" in text
    assert code == 0
    assert strict == 5


def test_gap_only_current_hour_has_no_gaps(clean_pg):
    def trial(s):
        # A failed row in the current hour: were the hour counted, it would be listed failed_only.
        _seed(clean_pg, [(s, "failed")])
        buffer = io.StringIO()
        strict = gaps.run(_env(clean_pg), fail_on_gaps=True, out=buffer)
        return _fetch(clean_pg), strict, buffer.getvalue()

    _, (rows, strict, text) = _stable(clean_pg, trial)
    assert rows == []
    assert strict == 0
    assert "1 runs recorded" in text
    assert "no gaps" in text


def test_gap_single_closed_slot_complete_and_failed_only(clean_pg):
    def trial_complete(s):
        _seed(clean_pg, [(s - HOUR, "ok")])
        return _fetch(clean_pg)

    _, rows = _stable(clean_pg, trial_complete)
    assert rows == []

    def trial_failed(s):
        _seed(clean_pg, [(s - HOUR, "failed"), (s - HOUR, "failed")])
        return _fetch(clean_pg)

    s, rows = _stable(clean_pg, trial_failed)
    assert _as_tuples(rows) == [(s - HOUR, "failed_only", 2, 2)]


def test_gap_duplicates_and_failed_plus_complete_are_not_gaps(clean_pg):
    def trial(s):
        _seed(clean_pg, [
            (s - 3 * HOUR, "ok"), (s - 3 * HOUR, "fallback"), (s - 3 * HOUR, "ok"),
            (s - 2 * HOUR, "failed"), (s - 2 * HOUR, "fallback"), (s - 2 * HOUR, "failed"),
            (s - 1 * HOUR, "fallback"),
        ])
        return _fetch(clean_pg)

    _, rows = _stable(clean_pg, trial)
    assert rows == []


def test_gap_since_until_filter_and_exit_codes(clean_pg):
    def trial(s):
        _seed(clean_pg, [
            (s - 6 * HOUR, "fallback"), (s - 5 * HOUR, "fallback"),
            (s - 3 * HOUR, "failed"), (s - 2 * HOUR, "fallback"),
        ])
        env = _env(clean_pg)
        window = io.StringIO()
        in_window = gaps.run(env, since=s - 3 * HOUR, until=s - 1 * HOUR, fail_on_gaps=True, out=window)
        none_left = gaps.run(env, since=s - 2 * HOUR, until=s - 1 * HOUR, fail_on_gaps=True, out=io.StringIO())
        unfiltered = gaps.run(env, fail_on_gaps=True, out=io.StringIO())
        tolerant = gaps.run(env, out=io.StringIO())
        return in_window, none_left, unfiltered, tolerant, window.getvalue()

    s, (in_window, none_left, unfiltered, tolerant, text) = _stable(clean_pg, trial)
    gap_lines = [line for line in text.splitlines() if "no_run" in line or "failed_only" in line]
    assert [line.split()[:2] for line in gap_lines] == [[_iso(s - 3 * HOUR), "failed_only"]]
    assert in_window == 5
    assert none_left == 0
    assert unfiltered == 5
    assert tolerant == 0


# --- read-only by construction, the writer role, and no secret or identifier in any output ---

_FORBIDDEN_WORDS = (
    "insert", "update", "delete", "drop", "alter", "create", "truncate", "grant", "revoke", "copy",
    "call", "do",
)


def _statement_text():
    """The SQL file with its `--` comment text removed."""
    with open(gaps.GAP_SQL_PATH, encoding="utf-8") as handle:
        raw = handle.read()
    return "\n".join(line.split("--", 1)[0] for line in raw.splitlines())


def test_gap_safe_sql_is_one_select_statement():
    import re

    with open(gaps.GAP_SQL_PATH, encoding="utf-8") as handle:
        raw = handle.read()
    assert "%" not in raw
    statement = _statement_text().strip()
    assert statement.endswith(";")
    assert statement.count(";") == 1
    assert re.match(r"(?i)(with|select)\b", statement)
    for word in _FORBIDDEN_WORDS:
        assert not re.search(r"(?i)\b" + word + r"\b", statement), word
    # The gap logic lives only in the SQL file: the wrapper holds no gap statement of its own.
    with open(gaps.__file__, encoding="utf-8") as handle:
        source = handle.read()
    assert "generate_series" not in source
    assert gaps.SUMMARY_SQL.lower().startswith("select ")


class _Recorder:
    """A proxy around a real connection that records each statement and the read-only state."""

    def __init__(self, conn):
        self._conn = conn
        self.statements = []

    @property
    def read_only(self):
        return self._conn.read_only

    @read_only.setter
    def read_only(self, value):
        self._conn.read_only = value

    @property
    def autocommit(self):
        return self._conn.autocommit

    @autocommit.setter
    def autocommit(self, value):
        self._conn.autocommit = value

    def execute(self, sql, *args, **kwargs):
        # Ask the server, not the flag: the session the statement runs in must really be read-only.
        in_effect = self._conn.execute("show transaction_read_only").fetchone()[0]
        self.statements.append((str(sql), self._conn.read_only, in_effect))
        return self._conn.execute(sql, *args, **kwargs)

    def close(self):
        self._conn.close()


def test_gap_safe_session_is_read_only(clean_pg):
    import psycopg

    recorders = []

    def connect():
        recorder = _Recorder(writer.connect(_writer_url(clean_pg)))
        recorders.append(recorder)
        return recorder

    s = _current_slot(clean_pg)
    _seed(clean_pg, [(s - 3 * HOUR, "fallback")])
    code = gaps.run(_env(clean_pg), out=io.StringIO(), connect=connect)
    assert code == 0
    statements = recorders[0].statements
    assert len(statements) == 2
    assert all(read_only is True for _, read_only, _ in statements)
    assert all(in_effect == "on" for _, _, in_effect in statements)
    for sql, _, _ in statements:
        # The gap file carries its header comment; the statement itself starts after it.
        code_lines = [line.split("--", 1)[0] for line in sql.splitlines()]
        assert "\n".join(code_lines).lstrip().lower().startswith(("with", "select"))

    # A read-only transaction really prevents a write: the writer role may insert, this may not.
    started = s - 2 * HOUR + datetime.timedelta(minutes=15)
    row = pg_helper.valid_run_rows(pg_helper.make_run_id(90, started), started)["psse_run"][0]
    control = writer.connect(_writer_url(clean_pg))
    try:
        pg_helper.insert_rows(control, "psse_run", [row])
    finally:
        control.close()
    blocked = writer.connect(_writer_url(clean_pg))
    try:
        blocked.autocommit = False
        blocked.read_only = True
        row2 = dict(row, run_id=pg_helper.make_run_id(91, started))
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            pg_helper.insert_rows(blocked, "psse_run", [row2])
    finally:
        blocked.close()
    counts = pg_helper.admin_rows(clean_pg, "select count(*) as n from public.psse_run")
    assert counts[0]["n"] == 2  # the seed row and the control row; the read-only insert left none


def test_gap_safe_same_rows_as_writer_and_superuser(clean_pg):
    import psycopg

    def trial(s):
        _seed(clean_pg, [
            (s - 5 * HOUR, "fallback"), (s - 3 * HOUR, "failed"), (s - 3 * HOUR, "failed"),
            (s - 2 * HOUR, "ok"), (s, "fallback"),
        ])
        as_writer = _fetch(clean_pg)
        with psycopg.connect(clean_pg, autocommit=True) as conn:
            as_superuser = gaps.fetch_gaps(conn)
            super_summary = gaps.fetch_summary(conn)
        writer_conn = writer.connect(_writer_url(clean_pg))
        try:
            writer_summary = gaps.fetch_summary(writer_conn)
        finally:
            writer_conn.close()
        return as_writer, as_superuser, writer_summary, super_summary

    s, (as_writer, as_superuser, writer_summary, super_summary) = _stable(clean_pg, trial)
    assert _as_tuples(as_writer) == _as_tuples(as_superuser)
    assert _as_tuples(as_writer) == [
        (s - 4 * HOUR, "no_run", 0, 0),
        (s - 3 * HOUR, "failed_only", 2, 2),
        (s - 1 * HOUR, "no_run", 0, 0),
    ]
    assert writer_summary == super_summary
    assert writer_summary[0] == 5


def test_gap_safe_connection_failure_names_no_secret():
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    # The port is closed again when the socket is released, so nothing listens on it.
    user = "gap" + "user" + "_zq"
    password = "pw" + "-" + "Zk93Xr"
    url = "postgresql://" + user + ":" + password + "@127.0.0.1:" + str(port) + "/somedb"
    buffer = io.StringIO()
    code = gaps.run({"SUPABASE_PSSE_DB_URL": url}, out=buffer)
    text = buffer.getvalue()
    assert code == 6
    lines = [line for line in text.splitlines() if line.strip()]
    assert len(lines) == 1
    assert lines[0].startswith("gap check could not run")
    assert password not in text
    assert user not in text
    assert "127.0.0.1" not in text
    assert "somedb" not in text
    # A missing URL is a failed check too, and says which setting is missing without a value.
    blank = io.StringIO()
    assert gaps.run({}, out=blank) == 6
    assert blank.getvalue().startswith("gap check could not run")


def test_gap_safe_missing_sql_file(clean_pg, monkeypatch, tmp_path):
    missing = tmp_path / "no_such_folder" / "missing_gap_statement.sql"
    monkeypatch.setattr(gaps, "GAP_SQL_PATH", str(missing))
    buffer = io.StringIO()
    code = gaps.run(_env(clean_pg), out=buffer)
    text = buffer.getvalue()
    assert code == 6
    assert text.startswith("gap check could not run")
    assert "no_such_folder" not in text
    assert "missing_gap_statement" not in text
    assert str(tmp_path) not in text


def test_gap_safe_report_holds_only_times_kinds_and_counts(clean_pg):
    import re

    label = "DISTINCTIVE_CASE_LABEL_7Q"
    iso = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"
    allowed = [
        re.compile(r"^gap check \(UTC\): \d+ runs recorded$"),
        re.compile(r"^first run slot: " + iso + "$"),
        re.compile(r"^latest run slot: " + iso + "$"),
        re.compile(r"^(\d+ gaps|no gaps)$"),
        re.compile(r"^" + iso + r"  (no_run|failed_only)\s+runs=\d+ failed=\d+$"),
    ]

    def trial(s):
        import psycopg

        with psycopg.connect(clean_pg, autocommit=True) as conn:
            for n, (slot, outcome) in enumerate([
                (s - 5 * HOUR, "fallback"), (s - 3 * HOUR, "failed"), (s - 2 * HOUR, "ok"),
            ]):
                started = slot + datetime.timedelta(minutes=15)
                run_id = pg_helper.make_run_id(n + 1, started)
                if outcome == "failed":
                    row = pg_helper.failed_run_row(run_id, started)
                else:
                    row = pg_helper.valid_run_rows(run_id, started, outcome=outcome)["psse_run"][0]
                row["case_id"] = label
                pg_helper.insert_rows(conn, "psse_run", [row])
        buffer = io.StringIO()
        code = gaps.run(_env(clean_pg), out=buffer)
        return code, buffer.getvalue(), pg_helper.admin_rows(clean_pg, "select run_id from public.psse_run")

    _, (code, text, run_ids) = _stable(clean_pg, trial)
    assert code == 0
    assert "failed_only" in text and "no_run" in text
    assert label not in text
    assert len(run_ids) == 3
    for row in run_ids:
        assert row["run_id"] not in text
    assert "psse-" not in text
    assert not re.search(r"[0-9a-f]{32}", text)
    for line in text.splitlines():
        assert any(pattern.match(line) for pattern in allowed), line
