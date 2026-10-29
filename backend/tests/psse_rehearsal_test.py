"""
TST-02 rehearsal of the laptop runbook (pss-e-integration Phase 3, plan 03-06): every command the
runbook `docs/data-science/decisions/psse_laptop_runbook.md` documents for the launcher or the task
renderer is executed here on the Mac, against the fake psspy, the loopback ratings and PostgREST
stand-ins and a throwaway local Postgres. A documented command that does not parse, or that does not
do what the runbook says it shows, fails this file.

How it works: a command block of the runbook is marked by a comment line `<!-- cmd: NAME -->`
directly above its fence. Each line of such a block is tokenised the way Windows splits a command
line (double quotes group a token), the token that ends with psse_run_hourly.py or
psse_render_task.py is found, the placeholders (`<PYTHON>`, `<REPO>`, `<CONFIG>`, `<SITE>`,
`<WORKDIR>`, `<OUT>`) are replaced with temporary files, and the arguments after the script go to
`launcher.main` (or, for the renderer, to a real `python -I -B` process). A block tagged with a name
outside the known set, other than `manual`, fails, so a typo cannot hide a command from this test.

Skipped unless `DLR_TEST_PG_AUTOSTART=1` (the fixture runs initdb and pg_ctl under pytest's tmp dir
and stops the cluster afterwards) or `DLR_TEST_DATABASE_URL` names a local throwaway database (host
127.0.0.1, localhost or ::1; anything else fails the test); with `PSSE_REQUIRE_PG=1` a missing
database, driver or binary fails instead of skipping. Nothing here touches Supabase: the ratings
server and the REST stand-in listen on loopback only.

Honest scope: this proves that each documented command parses and, against a fake psspy and a local
database, does what the runbook says it shows. It does not prove real PSS/E behaviour, Windows Task
Scheduler, the licence, the laptop's filesystem, the Windows byte lock on that machine or the live
database; every statement about those carries an `[UNVERIFIED until step N]` tag in the documents.

Follows backend/tests/psse_launcher_test.py (module-level imports, plain asserts, no test classes).
"""

import copy
import datetime
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import xml.etree.ElementTree as ET

import pytest

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import psse_fake_launch  # noqa: E402
import psse_fake_psspy as fake_module  # noqa: E402
import psse_fakes  # noqa: E402
import psse_local_pg as pg_helper  # noqa: E402
from psse_credcheck_test import RestStandIn  # noqa: E402
from psse_task_xml_test import _split_arguments as split_windows  # noqa: E402
from psse_job import launcher  # noqa: E402

RUNBOOK = os.path.join(_ROOT, "docs", "data-science", "decisions", "psse_laptop_runbook.md")
EXAMPLE = os.path.join(_ROOT, "docs", "data-science", "schema", "psse_mapping_example.json")
ENTRY_SCRIPT = os.path.join(_BACKEND, "psse_run_hourly.py")
RENDER_SCRIPT = os.path.join(_BACKEND, "psse_render_task.py")
WRITER_ROLE = "dlr_psse_writer"
SUMMARY_LINE = re.compile(r"^run_id=(\S+) outcome=(\S+) status=(\S+) exit=(\d+)$")
FIVE_DIGITS = re.compile(r"(?<![0-9])[0-9]{5}(?![0-9])")
TIMEOUT = 60

# The names of the command blocks (design decision D-02 of the plan). `manual` marks a block the Mac
# cannot run (PowerShell, pip, icacls). Any other name fails the extraction.
LAUNCHER_NAMES = (
    "selftest", "probe", "probe_write_check", "dry_run_smoke", "dry_run_real", "real_run", "gaps",
    "credcheck", "credcheck_write_proof", "hold_lock",
)
RENDER_NAMES = ("render_task", "render_task_dry_run")
COMMAND_NAMES = LAUNCHER_NAMES + RENDER_NAMES
MANUAL = "manual"

# What each name must parse to. A name and its command cannot drift apart (a real run that carries
# --allow-placeholder, a dry-run block without --dry-run) because the launcher's own parser reads it.
SHAPES = {
    "selftest": lambda a: a.mode == "selftest",
    "probe": lambda a: a.mode == "probe" and not a.write_check and not a.show_identifiers,
    "probe_write_check": lambda a: a.mode == "probe" and a.write_check and not a.show_identifiers,
    "dry_run_smoke": lambda a: a.mode == "run" and a.dry_run and a.allow_placeholder,
    "dry_run_real": lambda a: a.mode == "run" and a.dry_run and not a.allow_placeholder,
    "real_run": lambda a: a.mode == "run" and not a.dry_run and not a.allow_placeholder,
    "gaps": lambda a: a.mode == "gaps",
    "credcheck": lambda a: a.mode == "credcheck" and not a.write_proof,
    "credcheck_write_proof": lambda a: a.mode == "credcheck" and a.write_proof,
    "hold_lock": lambda a: a.mode == "hold-lock",
}
RENDER_SHAPES = {
    "render_task": lambda a: not a.dry_run and not a.allow_placeholder,
    "render_task_dry_run": lambda a: a.dry_run and a.allow_placeholder,
}

_CMD_TAG = re.compile(r"^<!-- cmd: ([a-z_]+) -->$", re.M)
_CMD_BLOCK = re.compile(r"^<!-- cmd: ([a-z_]+) -->\n```[a-z]*\n(.*?)\n```$", re.M | re.S)


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


@pytest.fixture(autouse=True)
def _private_temp(tmp_path, monkeypatch):
    """Every temporary directory of a test lives under tmp_path/scratch, so a leak shows."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    return scratch


@pytest.fixture(autouse=True)
def _restore_search_path(monkeypatch):
    """add_search_dirs changes sys.path: every test works on a copy that is put back afterwards."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(launcher, "DLL_DIRECTORY_HANDLES", [])
    monkeypatch.setattr(launcher, "LAST_START_NOTES", [])


# --------------------------------------------------------------------------- the runbook's command blocks


def command_blocks(path):
    """
    [(name, [line, ...])] for every `<!-- cmd: NAME -->` block of the document at `path`, in order.
    A tag that is not directly above a fenced block, or a name outside COMMAND_NAMES and `manual`,
    fails; blank lines inside a block are dropped. Shared with psse_setup_doc_test.py.
    """
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    tags = _CMD_TAG.findall(text)
    blocks = _CMD_BLOCK.findall(text)
    assert len(tags) == len(blocks), "a cmd tag is not directly above a fenced block"
    result = []
    for name, body in blocks:
        assert name in COMMAND_NAMES or name == MANUAL, "unknown command name %r" % name
        result.append((name, [line for line in body.splitlines() if line.strip()]))
    return result


def group_by_name(blocks):
    """{name: [line, ...]} over every block of that name, in document order."""
    groups = {}
    for name, lines in blocks:
        groups.setdefault(name, []).extend(lines)
    return groups


def split_command(line, values, script_suffix):
    """
    (interpreter tokens, script token, argument tokens) of one documented line after the
    placeholders in `values` ({"CONFIG": path, ...}) are replaced. The script token is the one that
    ends with `script_suffix`. The interpreter part must be `<PYTHON> -X utf8`, the form the task
    XML uses.
    """
    text = line
    for key, value in values.items():
        text = text.replace("<%s>" % key, value)
    tokens = split_windows(text)
    matches = [index for index, token in enumerate(tokens) if token.endswith(script_suffix)]
    assert len(matches) == 1, "no single %s token in: %s" % (script_suffix, line)
    index = matches[0]
    assert tokens[1:index] == ["-X", "utf8"], "the interpreter part of %r is not '<PYTHON> -X utf8'" % line
    if "REPO" in values:
        assert os.path.isfile(tokens[index]), "the documented script path does not exist: %s" % line
    return tokens[:index], tokens[index], tokens[index + 1:]


def launcher_arguments(line, values):
    """The argument tokens the launcher would receive from one documented line."""
    return split_command(line, values, "psse_run_hourly.py")[2]


def render_arguments(line, values):
    """The argument tokens the renderer would receive from one documented line."""
    return split_command(line, values, "psse_render_task.py")[2]


# --------------------------------------------------------------------------- helpers


def _case_file(tmp_path):
    """A stand-in for the copy of a PSS/E example case; the fake psspy registers it under this path."""
    folder = tmp_path / "private_case_directory"
    folder.mkdir(exist_ok=True)
    path = str(folder / "EXAMPLE_COPY.sav")
    with open(path, "wb") as handle:
        handle.write(b"MARKER - a copy of an example case")
    return path


def _mapping_without_marker(tmp_path):
    """A temp copy of the placeholder example mapping with the placeholder marker removed."""
    with open(EXAMPLE, encoding="utf-8") as handle:
        data = copy.deepcopy(json.load(handle))
    data["placeholder"] = False
    path = str(tmp_path / "real_mapping.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    return path


def _write_config(tmp_path, name, values):
    """A configuration file with the paths a rehearsal needs; `values` add to or override the defaults."""
    merged = {
        "PSSE_PSSPY_DIR": str(tmp_path / "psspy"),
        "PSSE_JOB_VERSION": "rehearsal",
        "PSSE_LOG_DIR": str(tmp_path / "logs"),
        "PSSE_LOCK_PATH": str(tmp_path / "locks" / "psse_job.lock"),
    }
    merged.update(values)
    path = tmp_path / name
    path.write_text("".join("%s=%s\n" % (key, value) for key, value in merged.items()), encoding="utf-8")
    return str(path)


def _loader(case_path):
    """The loader the entry script's load_psspy stands for: a fresh fake psspy, started like the real one."""
    def load(cfg):
        fake = psse_fake_launch.FakeLaunchPsspy()
        fake.fake_register_case(case_path, fake_module.placeholder_case())
        launcher.start_psspy(
            fake, int(cfg["PSSE_MAX_BUSES"]), os.path.join(cfg["PSSE_LOG_DIR"], "psse_output.log"))
        return fake
    return load


def _call(argv, loader):
    """(exit code, stdout lines, stderr text) of one launcher.main call."""
    out, err = io.StringIO(), io.StringIO()
    code = launcher.main(argv, loader, out=out, err=err)
    return code, out.getvalue().splitlines(), err.getvalue()


def _counts(admin_url):
    """Row counts of the four result tables, in the order of pg_helper.RESULT_TABLES."""
    return [pg_helper.admin_rows(admin_url, "select count(*) as n from public." + table)[0]["n"]
            for table in pg_helper.RESULT_TABLES]


def _report_rows(lines):
    """[(status, check)] of the report rows (lines that start with PASS, FAIL or SKIP)."""
    rows = []
    for line in lines:
        match = re.match(r"^(PASS|FAIL|SKIP)\s+(\S+)\s", line)
        if match:
            rows.append((match.group(1), match.group(2)))
    return rows


def _first_line_of(process, seconds):
    """The first stdout line of `process`, or None when it does not print one within `seconds`."""
    holder = []

    def read():
        holder.append(process.stdout.readline())

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    reader.join(seconds)
    return holder[0].strip() if holder else None


# --------------------------------------------------------------------------- the tracer


def test_tracer_rehearsal_runs_the_runbook_commands_against_fakes_and_local_postgres(clean_pg, tmp_path):
    """Every launcher and renderer command block of the runbook runs once, in an order that makes each result checkable."""
    groups = group_by_name(command_blocks(RUNBOOK))
    for name in COMMAND_NAMES:
        assert groups.get(name), "the runbook has no command block named %s" % name

    case_path = _case_file(tmp_path)
    loader = _loader(case_path)
    key = psse_fakes.fake_publishable_key()
    db_url = pg_helper.role_url(clean_pg, WRITER_ROLE)
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    outputs = []

    def values(config, out_name=None):
        found = {
            "PYTHON": sys.executable, "REPO": _ROOT, "CONFIG": config, "SITE": str(site_dir),
            "WORKDIR": str(work_dir), "OUT": str(tmp_path / (out_name or "unused.xml")),
        }
        return found

    now = datetime.datetime.now(datetime.timezone.utc)
    rows = psse_fakes.latest_rows(now, provisional=True)
    real_mapping = _mapping_without_marker(tmp_path)
    with psse_fakes.FakeLatestRatingServer(rows, key=key) as ratings_server, \
            RestStandIn(rows=psse_fakes.latest_rows(now, provisional=True)) as rest_server:
        base = {"PSSE_CASE_PATH": case_path}
        config_bare = _write_config(tmp_path, "bare.env", base)
        config_smoke = _write_config(tmp_path, "smoke.env", dict(base, PSSE_MAPPING_PATH=EXAMPLE))
        config_real = _write_config(tmp_path, "real.env", dict(
            base, PSSE_MAPPING_PATH=real_mapping, SUPABASE_PSSE_DB_URL=db_url,
            SUPABASE_URL=ratings_server.url, SUPABASE_PUBLISHABLE_KEY=key))
        config_cred = _write_config(tmp_path, "cred.env", dict(
            base, PSSE_MAPPING_PATH=real_mapping, SUPABASE_PSSE_DB_URL=db_url,
            SUPABASE_URL=rest_server.url, SUPABASE_PUBLISHABLE_KEY=key))

        # each name parses to the command it stands for (a real run never carries --allow-placeholder)
        for name in LAUNCHER_NAMES:
            for line in groups[name]:
                parsed = launcher.build_parser().parse_args(launcher_arguments(line, values(config_real)))
                assert SHAPES[name](parsed), "%s does not parse to its own shape: %s" % (name, line)

        # selftest: Python line, started line, four notes, six rows, a count line; exit 0
        for line in groups["selftest"]:
            code, out, err = _call(launcher_arguments(line, values(config_bare)), loader)
            outputs.append("\n".join(out) + err)
            assert code == 0, out
            assert out[0].startswith("Python ") and out[0].endswith("-bit") and out[1] == "PSS/E started"
            rows = _report_rows(out)
            assert [status for status, _ in rows] == ["PASS"] * 6
            assert [check for _, check in rows][0] == "version"
            assert out[-1] == "6 PASS, 0 FAIL, 0 SKIP"

        # probe (with no mapping, and with the mapping of step 7) and its write check: no FAIL, no identifier
        for name, expected_tail in (("probe", ", 0 FAIL, 0 SKIP"), ("probe_write_check", ", 0 FAIL, 0 SKIP")):
            for line in groups[name]:
                for config in (config_bare, config_real):
                    code, out, err = _call(launcher_arguments(line, values(config)), loader)
                    outputs.append("\n".join(out) + err)
                    assert code == 0, (name, out)
                    assert out[-1].endswith(expected_tail), out[-1]
                    assert all(status != "FAIL" for status, _ in _report_rows(out))
                    checks = [check for _, check in _report_rows(out)]
                    for needed in ("branch_table", "bus_table", "column_alignment", "circuit_id_padding",
                                   "option_strings", "load_flow"):
                        assert needed in checks, (name, needed)
                    if name == "probe_write_check":
                        assert "rating_write" in checks and "scale_load" in checks
                        assert "in memory only" in out[0]
                    text = "\n".join(out)
                    assert FIVE_DIGITS.search(text) is None  # the default report holds no bus number
                    assert "EXAMPLE_COPY" not in text and "private_case_directory" not in text

        # dry-run on the throwaway (placeholder) mapping: counts, validation ok, nothing written
        for line in groups["dry_run_smoke"]:
            code, out, err = _call(launcher_arguments(line, values(config_smoke)), loader)
            outputs.append("\n".join(out) + err)
            assert code == 0, (out, err)
            assert out[0] == "dry run: nothing was written to the database"
            assert out[1] == "rows: psse_run=1 psse_dispatched_capacity=4 psse_voltage_margin=4 psse_contingency_result=10"
            assert out[-1] == "validation: ok"
            assert any(line.startswith("study_seconds: ") for line in out)
            assert _counts(clean_pg) == [0, 0, 0, 0]

        # dry-run on a mapping without the placeholder marker (step 7): the same report
        for line in groups["dry_run_real"]:
            code, out, err = _call(launcher_arguments(line, values(config_real)), loader)
            outputs.append("\n".join(out) + err)
            assert code == 0, (out, err)
            assert out[0] == "dry run: nothing was written to the database" and out[-1] == "validation: ok"
            assert _counts(clean_pg) == [0, 0, 0, 0]

        # the real run: one run of 1 + 4 + 4 + 10 rows, every completeness check ok, one summary line
        (real_line,) = groups["real_run"]
        code, out, err = _call(launcher_arguments(real_line, values(config_real)), loader)
        outputs.append("\n".join(out) + err)
        assert code == 0, (out, err)
        assert len(out) == 1
        match = SUMMARY_LINE.match(out[0])
        assert match is not None, out
        run_id, outcome, status, exit_text = match.groups()
        assert (outcome, status, exit_text) == ("fallback", "written", "0")
        assert _counts(clean_pg) == [1, 4, 4, 10]
        checks = pg_helper.admin_rows(clean_pg, pg_helper._read(pg_helper.CHECKS_SQL))
        assert checks and [row for row in checks if not row["ok"]] == []

        # the gap check: exit 0 and a header with the one run recorded
        for line in groups["gaps"]:
            code, out, err = _call(launcher_arguments(line, values(config_real)), loader)
            outputs.append("\n".join(out) + err)
            assert code == 0, (line, out, err)
            assert out[0] == "gap check (UTC): 1 runs recorded", out
            assert "no gaps" in "\n".join(out)

        # the credential proof: every row PASS; the write proof leaves the tables as they were
        for line in groups["credcheck"]:
            code, out, err = _call(launcher_arguments(line, values(config_cred)), loader)
            outputs.append("\n".join(out) + err)
            assert code == 0, out
            assert all(status == "PASS" for status, _ in _report_rows(out))
            assert out[-1] == "16 PASS, 0 FAIL, 0 SKIP"
        for line in groups["credcheck_write_proof"]:
            code, out, err = _call(launcher_arguments(line, values(config_cred)), loader)
            outputs.append("\n".join(out) + err)
            assert code == 0, out
            assert all(status == "PASS" for status, _ in _report_rows(out))
            assert out[-1] == "18 PASS, 0 FAIL, 0 SKIP"
            assert _counts(clean_pg) == [1, 4, 4, 10]  # still only the one real run
        assert len(rest_server.requests) >= 3 * (len(groups["credcheck"]) + len(groups["credcheck_write_proof"]))

        # an overlapping start: a second process holds the run lock, the real run is skipped with exit 4
        for line in groups["hold_lock"]:
            interpreter, script, arguments = split_command(line, values(config_real), "psse_run_hourly.py")
            assert arguments[0] == "hold-lock"
            assert "--seconds" in arguments
            arguments[arguments.index("--seconds") + 1] = "2"  # the documented 60 seconds, shortened
            holder = subprocess.Popen(
                [sys.executable, "-I", "-B", "-X", "utf8", ENTRY_SCRIPT] + arguments,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            try:
                assert _first_line_of(holder, TIMEOUT / 2) == "locked"
                code, out, err = _call(launcher_arguments(real_line, values(config_real)), loader)
                outputs.append("\n".join(out) + err)
                assert code == 4, (out, err)
                assert out == [] and "another instance holds the run lock" in err
                assert _counts(clean_pg) == [1, 4, 4, 10]  # nothing new was written
                assert holder.wait(timeout=TIMEOUT) == 0
            finally:
                if holder.poll() is None:
                    holder.kill()
                    holder.wait(timeout=TIMEOUT)
                holder.stdout.close()
                holder.stderr.close()
        code, out, err = _call(launcher_arguments(real_line, values(config_smoke)), loader)
        assert code == 2  # a configuration without the database keys still stops with a usage exit

    # the renderer: well-formed UTF-8 XML whose Arguments the launcher's own parser accepts
    for name in RENDER_NAMES:
        for number, line in enumerate(groups[name]):
            out_name = "%s_%d.xml" % (name, number)
            interpreter, script, arguments = split_command(
                line, values(config_real, out_name), "psse_render_task.py")
            result = subprocess.run(
                [sys.executable, "-I", "-B", "-X", "utf8", RENDER_SCRIPT] + arguments,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=TIMEOUT)
            assert result.returncode == 0, result.stderr
            assert result.stdout.strip() == "wrote %s" % str(tmp_path / out_name)
            with open(str(tmp_path / out_name), "rb") as handle:
                raw = handle.read()
            assert not raw.startswith(b"\xef\xbb\xbf")
            root = ET.fromstring(raw.decode("utf-8"))
            namespace = "{http://schemas.microsoft.com/windows/2004/02/mit/task}"
            node = root.find(namespace + "Actions/" + namespace + "Exec/" + namespace + "Arguments")
            tokens = split_windows(node.text)
            assert tokens[:2] == ["-X", "utf8"] and tokens[2].endswith("psse_run_hourly.py")
            parsed = launcher.build_parser().parse_args(tokens[3:])
            assert parsed.mode == "run" and parsed.config == config_real
            assert RENDER_SHAPES[name](_render_namespace(arguments)), name

    # nothing printed anywhere holds a secret, a connection string or a temporary path
    text = "\n".join(outputs)
    for secret in (key, db_url, "postgresql://", str(tmp_path), "private_case_directory"):
        assert secret not in text, secret


def _render_namespace(arguments):
    """The renderer's own parse of its documented arguments (parse errors would be SystemExit)."""
    import psse_render_task
    return psse_render_task._parser().parse_args(arguments)


# --------------------------------------------------------------------------- the induced gap

HOUR = datetime.timedelta(hours=1)
UTC = datetime.timezone.utc


def _database_slot(admin_url):
    """The database's own current UTC hour, as an aware datetime."""
    rows = pg_helper.admin_rows(
        admin_url, "select (date_trunc('hour', now() at time zone 'UTC') at time zone 'UTC') as slot")
    return rows[0]["slot"].astimezone(UTC)


def _seed_complete_runs(admin_url, slots):
    """One complete (fallback) run row, started 15 minutes into each slot of `slots`, as the superuser."""
    import psycopg

    with psycopg.connect(admin_url, autocommit=True) as conn:
        for number, slot in enumerate(slots, 1):
            started = slot + datetime.timedelta(minutes=15)
            row = pg_helper.valid_run_rows(
                pg_helper.make_run_id(number, started), started, outcome="fallback")["psse_run"][0]
            pg_helper.insert_rows(conn, "psse_run", [row])


def _iso(moment):
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_rehearsal_gap_check_exit_codes_after_an_induced_missing_hour(clean_pg, tmp_path):
    """
    The documented `gaps` commands through launcher.main on a seeded history. Runs sit in the slots
    s-3h and s-1h, so the hour s-2h is missing: the documented plain command prints a `no_run` line
    for that hour and exits 0, and the documented `--fail-on-gaps` command exits 5. With no missing hour
    the same command exits 0 and prints `no gaps`. A history is accepted only if the database's hour
    did not roll while it was read.
    """
    groups = group_by_name(command_blocks(RUNBOOK))
    plain = [line for line in groups["gaps"] if "--fail-on-gaps" not in line]
    strict = [line for line in groups["gaps"] if "--fail-on-gaps" in line]
    assert plain and strict, "the runbook documents the gap check with and without --fail-on-gaps"
    config = _write_config(tmp_path, "gaps.env", {
        "SUPABASE_PSSE_DB_URL": pg_helper.role_url(clean_pg, WRITER_ROLE)})
    values = {
        "PYTHON": sys.executable, "REPO": _ROOT, "CONFIG": config, "SITE": str(tmp_path / "site"),
        "WORKDIR": str(tmp_path), "OUT": str(tmp_path / "unused.xml"),
    }

    def no_loader(cfg):
        raise AssertionError("the gap check never starts PSS/E")

    def check(slots_of):
        """(slot, results) for one history; retried when the database's hour rolled while reading it."""
        for _ in range(3):
            pg_helper.reset(clean_pg)
            before = _database_slot(clean_pg)
            _seed_complete_runs(clean_pg, slots_of(before))
            results = {}
            for line in plain + strict:
                results[line] = _call(launcher_arguments(line, values), no_loader)
            if _database_slot(clean_pg) == before:
                return before, results
        pytest.fail("the database's UTC hour rolled during all three attempts")

    # one missing hour: s-2h
    slot, results = check(lambda s: [s - 3 * HOUR, s - 1 * HOUR])
    for line in plain:
        code, out, err = results[line]
        assert code == 0 and err == "", (out, err)
        gap_lines = [text for text in out if "no_run" in text]
        assert [text.split()[:2] for text in gap_lines] == [[_iso(slot - 2 * HOUR), "no_run"]]
        assert out[0] == "gap check (UTC): 2 runs recorded" and "1 gaps" in "\n".join(out)
    for line in strict:
        code, out, err = results[line]
        assert code == 5, (out, err)
        assert [text.split()[:2] for text in out if "no_run" in text] == [[_iso(slot - 2 * HOUR), "no_run"]]
    assert _counts(clean_pg)[0] == 2  # the gap check wrote nothing

    # no missing hour: the same documented commands exit 0 and report no gaps
    slot, results = check(lambda s: [s - 3 * HOUR, s - 2 * HOUR, s - 1 * HOUR])
    for line in plain + strict:
        code, out, err = results[line]
        assert code == 0, (out, err)
        assert out[0] == "gap check (UTC): 3 runs recorded" and "no gaps" in "\n".join(out)
        assert not [text for text in out if "no_run" in text]
