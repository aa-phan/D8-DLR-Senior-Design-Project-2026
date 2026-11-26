"""
OPS-01, OPS-02, OPS-03 rehearsal of the hourly workflow (pandapower-solver Phase 5, plan 05-06;
decisions D-07, D-10, D-14): runs exactly what `.github/workflows/pandapower_hourly.yml` runs,
`python -I -B backend/pandapower_hourly.py run` and `... soak`, through the entry script in a fresh
interpreter, so the output sink is exercised on real descriptors outside pytest's capture.

The four secrets come from the files the owner's `bundle` command wrote (in-process, on a synthetic
private tree in a throwaway repository), the ratings come from a loopback stand-in of the Supabase
REST view, `GITHUB_ACTIONS` is `true` and `RUNNER_TEMP` is an empty scratch folder, as on a runner.
The soak test is database tier: it needs a throwaway Postgres (`DLR_TEST_PG_AUTOSTART=1` or a local
`DLR_TEST_DATABASE_URL`) and is skipped without one, or fails under `PSSE_REQUIRE_PG=1`.

Honest scope: GitHub's runner itself, its secret store and its log are not rehearsed here (plan 05-07
does that); nothing here reads this checkout's `data/private`; no test asserts a file mode or pins
file bytes (Windows).
"""

import datetime
import hashlib
import os
import subprocess
import sys

import pytest

pandapower = pytest.importorskip("pandapower")

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
_REPO = os.path.abspath(os.path.join(_BACKEND, ".."))
for _folder in (_BACKEND, _HERE):
    if _folder not in sys.path:
        sys.path.insert(0, _folder)

import pandapower_hourly_fixture as fixture  # noqa: E402
import pandapower_replay_fixture as replay_fixture  # noqa: E402
import private_leak_scan  # noqa: E402
import psse_fakes  # noqa: E402
from pandapower_job import hourly  # noqa: E402
from psse_job import constants  # noqa: E402

ENTRY_SCRIPT = os.path.join("backend", "pandapower_hourly.py")
PREFIXES = ("SUPABASE_", "PANDAPOWER_", "GITHUB_")
RATING_PATH = "/rest/v1/latest_rating"
TIMEOUT_S = 600


def _bundle_env(repo):
    """Run the owner's `bundle` in-process on the throwaway repository `repo` and return
    `(values, folder)`: the four secret values read from the files it wrote, by secret name, and the
    folder of those files."""
    result = hourly.bundle(repo_root=repo)
    values = {}
    for _word, name, _file, _cap in hourly.SECRET_ENV:
        with open(os.path.join(result.folder, name + ".txt"), "r", encoding="ascii") as handle:
            values[name] = handle.read()
    return values, result.folder


def _child_env(**values):
    """The parent environment minus every SUPABASE_*, PANDAPOWER_* and GITHUB_* name, plus `values`."""
    environ = dict((name, text) for name, text in os.environ.items()
                   if not name.startswith(PREFIXES))
    environ.update(values)
    return environ


def _run_child(command, environ):
    """The workflow's command line in a fresh interpreter, from the repository root."""
    return subprocess.run(
        [sys.executable, "-I", "-B", ENTRY_SCRIPT] + list(command), env=environ, cwd=_REPO,
        capture_output=True, text=True, timeout=TIMEOUT_S, stdin=subprocess.DEVNULL)


def _vocabulary_ok(lines):
    return all(any(pattern.match(line) for pattern in hourly.HOURLY_LINE_PATTERNS) for line in lines)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    """One throwaway repository with a synthetic private tree and the bundle written from it."""
    base = tmp_path_factory.mktemp("rehearsal")
    repo = replay_fixture.make_repo(base / "repo")
    layout = fixture.private_tree(repo)
    values, folder = _bundle_env(repo)
    return {"repo": repo, "layout": layout, "values": values, "folder": folder, "base": base}


def _runner_env(world, server, scratch, **extra):
    """The environment of the workflow's study step: the four bundled secrets, the two read
    settings pointing at the loopback server, a job version, GITHUB_ACTIONS and RUNNER_TEMP."""
    environ = _child_env(
        SUPABASE_URL=server.url, SUPABASE_PUBLISHABLE_KEY=server.key, PSSE_JOB_VERSION="rehearsal",
        GITHUB_ACTIONS="true", RUNNER_TEMP=str(scratch), **world["values"])
    environ.update(extra)
    return environ


def _scan_sets(world):
    """(derived needles of the throwaway private tree, the long tokens of the four values and the
    hashes of the two source files)."""
    derived = private_leak_scan.derive_needles(os.path.join(world["repo"], "data", "private"))
    found = set()
    for text in world["values"].values():
        found.add(text)
        found.update(token for token in private_leak_scan._TOKEN.findall(text) if len(token) >= 20)
    for path in (world["layout"].network, world["layout"].mapping):
        with open(path, "rb") as handle:
            found.add(hashlib.sha256(handle.read()).hexdigest())
    return derived, set(text for text in found if len(text) >= 5)


def _fresh_server():
    rows = psse_fakes.latest_rows(datetime.datetime.now(datetime.timezone.utc), provisional=False)
    return psse_fakes.FakeLatestRatingServer(rows=rows, key=psse_fakes.fake_publishable_key())


# -- the tracer ------------------------------------------------------------------------------------


def test_tracer_entry_script_dry_run_in_a_fresh_interpreter(world, tmp_path):
    """The exact command of the workflow, on secrets written by `bundle`, reads the ratings from the
    loopback view and completes a dry run: exit 0, vocabulary lines only on stdout, nothing on
    stderr, an empty RUNNER_TEMP afterwards, one request to the ratings view carrying the key, and
    no private value or bundled secret in what it printed."""
    scratch = tmp_path / "runner_temp"
    scratch.mkdir()
    with _fresh_server() as server:
        environ = _runner_env(world, server, scratch)
        # whatever the parent holds, the child has no live variable and no writer value
        assert hourly.LIVE_VARIABLE not in environ
        assert constants.ENV_PSSE_DB_URL not in environ
        completed = _run_child(["run"], environ)
        requests = list(server.requests)

    lines = completed.stdout.splitlines()
    assert completed.returncode == hourly.EXIT_OK, completed.stdout
    assert completed.stderr == ""
    assert lines and _vocabulary_ok(lines), lines
    assert lines[0] == "mode: dry"
    assert "inputs: ok" in lines
    assert "ratings: city_rating=4 static=0" in lines
    assert "study: ok" in lines
    assert lines[-1] == "dry run: nothing was written to the database"
    assert not any(line.startswith("::") for line in lines)
    assert os.listdir(str(scratch)) == []

    assert len(requests) == 1
    assert requests[0]["path"] == RATING_PATH
    assert requests[0]["headers"].get("apikey") == psse_fakes.fake_publishable_key()

    printed = tmp_path / "stdout.txt"
    printed.write_text(completed.stdout, encoding="utf-8")
    derived, fragments = _scan_sets(world)
    assert len(derived) > 0 and len(fragments) > 0, "an empty needle set proves nothing"
    assert private_leak_scan.scan_paths([str(printed)], needles=derived, root=world["repo"]) == []
    assert private_leak_scan.scan_paths([str(printed)], needles=fragments, root=world["repo"]) == []
    # the scan is able to fire: a bundled value planted in a copy of the output is found
    planted = tmp_path / "planted.txt"
    planted.write_text(completed.stdout + sorted(fragments, key=len)[-1] + "\n", encoding="utf-8")
    assert private_leak_scan.scan_paths([str(planted)], needles=fragments, root=world["repo"]) != []


def test_wrong_case_variable_stays_dry(world, tmp_path):
    """`True` is not `true`: GitHub's case-insensitive comparison would hand the writer URL to the
    step, but the runner is live only for the exact lowercase text, so it prints `mode: dry` and
    writes nothing (the known, harmless quirk the runbook names)."""
    scratch = tmp_path / "runner_temp"
    scratch.mkdir()
    with _fresh_server() as server:
        environ = _runner_env(world, server, scratch)
        environ[hourly.LIVE_VARIABLE] = "True"
        completed = _run_child(["run"], environ)
    lines = completed.stdout.splitlines()
    assert completed.returncode == hourly.EXIT_OK, completed.stdout
    assert completed.stderr == ""
    assert lines[0] == "mode: dry"
    assert "mode: live" not in lines
    assert lines[-1] == "dry run: nothing was written to the database"
    assert os.listdir(str(scratch)) == []


# -- the soak command against a throwaway Postgres (database tier) ----------------------------------


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    """Admin URL of a database with the Phase 4 migrations, the reference DDL and the solver-tag
    migration (skips or fails per `psse_local_pg.require_local_pg`)."""
    import psse_local_pg as pg_helper

    with pg_helper.cluster(tmp_path_factory) as admin_url:
        pg_helper.apply_solver_schema(admin_url)
        yield admin_url


def _database_hour(admin_url):
    import psse_local_pg as pg_helper

    value = pg_helper.admin_rows(
        admin_url,
        "select (date_trunc('hour', now() at time zone 'UTC') at time zone 'UTC') as h")[0]["h"]
    return value.astimezone(datetime.timezone.utc)


def _seed_pandapower_runs(admin_url, hour, count):
    """One fallback pandapower run in each of the `count` hours before `hour`."""
    import psse_local_pg as pg_helper
    import psycopg

    with psycopg.connect(admin_url) as conn:
        for back in range(1, count + 1):
            started = hour - datetime.timedelta(hours=back) + datetime.timedelta(minutes=5)
            run_id = pg_helper.make_run_id(back, started, prefix="pp")
            rows = pg_helper.valid_run_rows(run_id, started, outcome="fallback")
            rows["psse_run"][0].update(solver="pandapower", solver_version=pandapower.__version__,
                                       psse_version=None)
            for table in pg_helper.RESULT_TABLES:
                pg_helper.insert_rows(conn, table, rows[table])


def test_entry_script_soak_against_a_throwaway_postgres(pg, tmp_path):
    """The workflow's second command, as the writer role, prints counts only: three pandapower
    runs in the three hours before the database's current hour are three consecutive slots of 24,
    no gap, `soak: not yet`; exit 0, nothing on stderr."""
    import psse_local_pg as pg_helper

    writer_url = pg_helper.role_url(pg, "dlr_psse_writer")
    expected = ["gap check: solver pandapower runs=3 gaps=0",
                "soak: consecutive_slots=3 of 24 fallback_slots=3", "soak: not yet"]
    completed = None
    for _attempt in range(2):
        pg_helper.reset(pg)
        hour = _database_hour(pg)
        _seed_pandapower_runs(pg, hour, 3)
        scratch = tmp_path / ("runner_temp_%d" % _attempt)
        scratch.mkdir()
        environ = _child_env(GITHUB_ACTIONS="true", RUNNER_TEMP=str(scratch),
                             **{constants.ENV_PSSE_DB_URL: writer_url})
        completed = _run_child(["soak"], environ)
        if _database_hour(pg) == hour:
            break
    else:
        raise AssertionError("the database's hour changed twice in a row")

    lines = completed.stdout.splitlines()
    assert completed.returncode == hourly.EXIT_OK, completed.stdout
    assert completed.stderr == ""
    assert _vocabulary_ok(lines)
    assert lines == expected
    assert os.listdir(str(scratch)) == []
