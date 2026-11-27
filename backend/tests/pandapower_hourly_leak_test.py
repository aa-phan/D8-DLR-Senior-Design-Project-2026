"""
What the hourly runner and the owner commands may print, rehearsed with planted identifiers
(pandapower-solver Phase 5, plan 05-05, task 3: OPS-02; decisions D-05 and D-14; the pattern of
`pandapower_replay_output_test.py` of Phase 4).

Every output the runner (`run`) and the owner commands (`soak`, `bundle`, `scan-log`) can produce,
on every path, must be lines of the closed vocabulary (`hourly.HOURLY_LINE_PATTERNS`), none starting
with two colons, with nothing on standard error and nothing logged. This file checks it, and shows
that the checks can fire. Two needle sets are scanned against each output:

  scan A   `private_leak_scan.derive_needles` of the throwaway repository's `data/private` folder:
           the mapping's branch keys, the scaling targets, the sha256 of every private file (the
           bundle files included) and the long decimals, run on a tree shaped like the owner's.
  scan B   a needle set built from this test's own data: every planted secret piece (the writer
           URL's user, password, host and project reference, their percent-decoded and token
           forms), each base64 secret and its tokens of 20 or more characters, the case and mapping
           hashes, every run id the recording study saw, every mapping branch key in both
           orientations, every number of the mapping and of the results in `repr`, `%g` and `%.1f`
           forms of five or more characters, and the planted noise tokens.

Each case runs through `hourly.main` with the real output sink, under `capfd` (the file
descriptors) and `caplog` (every log record at DEBUG), in its own scratch temporary folder, on an
environment whose four secrets are the base64 files `bundle` wrote from the throwaway private tree
and whose Supabase values are planted fakes.

Every private-looking file is synthetic and lives in a throwaway git repository under `tmp_path`;
nothing here reads the real `data/private/`. Honest scope: this proves that the output cannot carry
what these scans know to look for, and that the scans are able to find it (the five teeth of the
last test); it does not prove that no other secret exists. GitHub's own masking of secret values is
an extra layer, not the control (D-05).
"""

import os
import sys
import tempfile

import pytest

pandapower = pytest.importorskip("pandapower")

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
for _folder in (_BACKEND, _HERE):
    if _folder not in sys.path:
        sys.path.insert(0, _folder)

import base64  # noqa: E402
import collections  # noqa: E402
import datetime  # noqa: E402
import hashlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import math  # noqa: E402
import urllib.parse  # noqa: E402
import warnings  # noqa: E402

import pandapower_hourly_fixture as fixture  # noqa: E402
import pandapower_replay_fixture as replay_fixture  # noqa: E402
import pandapower_study_fixture as study_fixture  # noqa: E402
import private_leak_scan  # noqa: E402
import psse_fakes  # noqa: E402
from pandapower_job import engine, hourly  # noqa: E402
from psse_job import gaps  # noqa: E402

_PATTERNS = hourly.HOURLY_LINE_PATTERNS
_TOKEN = private_leak_scan._TOKEN
_BRANCH = study_fixture.ISLANDING_OUTAGE
_BRANCH_KEY = "%d-%d-%s" % (_BRANCH.from_bus, _BRANCH.to_bus, _BRANCH.ckt)
NOISE = "NOISE-" + _BRANCH_KEY
LATER = fixture.FIXED_NOW + datetime.timedelta(hours=1)


@pytest.fixture(autouse=True)
def _private_temp(tmp_path, monkeypatch):
    """Every temporary directory of a test lives under tmp_path/scratch, so a leak shows."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    return scratch


World = collections.namedtuple("World", ["repo", "layout", "secrets"])


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    """A throwaway repository with its private tree and one bundle folder; `secrets` is the
    environment name -> single-line base64 text of the four files `bundle` wrote."""
    repo = replay_fixture.make_repo(tmp_path_factory.mktemp("leak_world") / "repo")
    layout = fixture.private_tree(repo)
    buffer = io.StringIO()
    code = hourly.main(["bundle"], out=buffer, environ={}, repo_root=repo,
                       clock=lambda: fixture.FIXED_NOW, sink=False)
    assert code == 0
    root = os.path.join(repo, "data", "private", "pandapower", hourly.BUNDLE_DIR)
    folder = os.path.join(root, sorted(os.listdir(root))[0])
    secrets = {}
    for _word, name, _file, _cap in hourly.SECRET_ENV:
        with open(os.path.join(folder, name + ".txt"), "r", encoding="ascii") as handle:
            secrets[name] = handle.read()
    return World(repo, layout, secrets)


# -- environments and stand-ins --------------------------------------------------------------------


def _env(world, live=False, **extra):
    environ = dict(world.secrets)
    environ.update(fixture.read_env())
    environ["SUPABASE_URL"] = fixture.planted_supabase_url()
    environ["SUPABASE_PSSE_DB_URL"] = fixture.planted_writer_url()
    if live:
        environ[hourly.LIVE_VARIABLE] = "true"
    environ.update(extra)
    return environ


def _b64(data):
    return base64.b64encode(data).decode("ascii")


def _duplicate_mapping(tmp_path):
    """(base64 text, document) of the mapping that lists one outage twice (a refusal whose error
    text names the branch)."""
    entry = {"from_bus": _BRANCH.from_bus, "to_bus": _BRANCH.to_bus, "ckt": _BRANCH.ckt}
    path = study_fixture.write_placeholder_mapping(
        tmp_path, study={"contingency": {"extra": [entry, dict(entry)]}}, name="duplicate.json")
    with open(path, "r", encoding="utf-8") as handle:
        document = json.load(handle)
    document["placeholder"] = False
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle)
    with open(path, "rb") as handle:
        return _b64(handle.read()), document


def _placeholder_settings(world):
    document = json.loads(base64.b64decode(world.secrets["PANDAPOWER_SETTINGS_B64"]).decode("ascii"))
    document["settings"]["sources"]["enforce_q_lims"] = "placeholder: not decided"
    return _b64(json.dumps(document).encode("ascii"))


class Seen(object):
    """What the recording study saw: every run id, every set of results and every hash."""

    def __init__(self):
        self.run_ids = []
        self.results = []
        self.hashes = set()


def _recording(prepare, seen):
    def wrapped(backend, case_path, mapping_path, allow_placeholder=False, clock=None):
        prepared = prepare(backend, case_path, mapping_path, allow_placeholder, clock)
        seen.hashes.update(text for text in (prepared.case_sha256, prepared.mapping_sha256) if text)
        inner = prepared.study

        def study(selection, context):
            seen.run_ids.append(context.run_id)
            results = inner(selection, context)
            seen.results.append(results)
            return results

        return prepared._replace(study=study)

    return wrapped


def _noisy(prepare):
    """A prepared run whose study writes planted values on every route a library could use."""
    def wrapped(backend, case_path, mapping_path, allow_placeholder=False, clock=None):
        prepared = prepare(backend, case_path, mapping_path, allow_placeholder, clock)
        inner = prepared.study

        def study(selection, context):
            for text in (NOISE, fixture.PLANTED["db_password"], fixture.PLANTED["db_host"],
                         _BRANCH_KEY, fixture.planted_writer_url()):
                print(text)
                print(text, file=sys.stderr)
                os.write(1, (text + "\n").encode("ascii"))
                os.write(2, (text + "\n").encode("ascii"))
                warnings.warn(text)
                logging.getLogger("pandapower").error(text)
                logging.getLogger("psse_job.job").warning(text)
            return inner(selection, context)

        return prepared._replace(study=study)

    return wrapped


def _planted_failure(*args, **kwargs):
    raise RuntimeError("connection failed for %s password %s host %s" % (
        fixture.planted_writer_url(), fixture.PLANTED["db_password"], fixture.PLANTED["db_host"]))


def _raising_prepare(backend, case_path, mapping_path, allow_placeholder=False, clock=None):
    raise RuntimeError("planted text with a branch key " + _BRANCH_KEY)


# -- the checks ------------------------------------------------------------------------------------


def _write(path, text):
    os.makedirs(os.path.dirname(os.fspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return str(path)


def _check_lines(where, text):
    """Every line is of the vocabulary and none starts with two colons; the text is not empty."""
    assert text.strip() != "", "%s: nothing was printed" % where
    for position, line in enumerate(text.splitlines(), start=1):
        assert any(pattern.match(line) for pattern in _PATTERNS), (
            "%s: line %d is outside the command vocabulary" % (where, position))
        assert not line.startswith("::"), "%s: line %d starts with two colons" % (where, position)


def _tokens_of(text):
    return set(_TOKEN.findall(text))


def _collect_numbers(node, found):
    """Every number anywhere in `node` (dicts, lists, tuples, namedtuples) in three text forms."""
    if node is None or isinstance(node, (bool, str, bytes)):
        return
    if isinstance(node, (int, float)):
        if isinstance(node, float) and not math.isfinite(node):
            return
        found.update((repr(node), "%g" % node, "%.1f" % node))
    elif isinstance(node, dict):
        for value in node.values():
            _collect_numbers(value, found)
    elif hasattr(node, "_asdict"):
        _collect_numbers(node._asdict(), found)
    elif isinstance(node, (list, tuple)):
        for value in node:
            _collect_numbers(value, found)


def _add_branch_keys(node, found):
    if isinstance(node, dict):
        if "from_bus" in node and "to_bus" in node and "ckt" in node:
            found.add("%d-%d-%s" % (node["from_bus"], node["to_bus"], node["ckt"]))
            found.add("%d-%d-%s" % (node["to_bus"], node["from_bus"], node["ckt"]))
        for value in node.values():
            _add_branch_keys(value, found)
    elif isinstance(node, list):
        for value in node:
            _add_branch_keys(value, found)


def _with_tokens(text, found):
    found.add(text)
    found.update(_TOKEN.findall(text))


def _set_a(repo):
    return private_leak_scan.derive_needles(os.path.join(repo, "data", "private"))


def _set_b(world, seens, documents):
    """Needle set B (see the module header)."""
    found = set()
    for text in (fixture.PLANTED["db_user"], fixture.PLANTED["db_password"],
                 fixture.PLANTED["db_host"], fixture.PLANTED["project_ref"], NOISE, _BRANCH_KEY,
                 urllib.parse.quote(fixture.PLANTED["db_password"], safe=""),
                 urllib.parse.unquote(urllib.parse.quote(fixture.PLANTED["db_password"], safe="")),
                 fixture.planted_writer_url(), fixture.planted_supabase_url(),
                 psse_fakes.fake_publishable_key()):
        _with_tokens(text, found)
    for text in list(world.secrets.values()) + [item for item in documents if isinstance(item, str)]:
        found.add(text)
        found.update(token for token in _TOKEN.findall(text) if len(token) >= 20)
    for path in (world.layout.network, world.layout.mapping):
        with open(path, "rb") as handle:
            found.add(hashlib.sha256(handle.read()).hexdigest())
    numbers = set()
    mapping_documents = [item for item in documents if not isinstance(item, str)]
    with open(world.layout.mapping, "r", encoding="utf-8") as handle:
        mapping_documents.append(json.load(handle))
    for document in mapping_documents:
        _add_branch_keys(document, found)
        _collect_numbers(document, numbers)
    for seen in seens:
        found.update(seen.hashes)
        for run_id in seen.run_ids:
            _with_tokens(run_id, found)
            found.update(part for part in run_id.split("-") if part)
        for results in seen.results:
            _collect_numbers(results, numbers)
    found.update(numbers)
    return set(text for text in found if isinstance(text, str) and len(text) >= 5)


def _scans_clean(path, repo, needles_a, needles_b, where):
    assert len(needles_a) > 0 and len(needles_b) > 0, "%s: an empty needle set proves nothing" % where
    found_a = private_leak_scan.scan_paths([path], needles=needles_a, root=repo)
    assert found_a == [], "%s: scan A reports %d findings" % (where, len(found_a))
    found_b = private_leak_scan.scan_paths([path], needles=needles_b, root=repo)
    assert found_b == [], "%s: scan B reports %d findings" % (where, len(found_b))
    with open(path, "r", encoding="utf-8") as handle:
        shared = _tokens_of(handle.read()) & needles_b
    assert not shared, "%s: %d printed tokens are known values" % (where, len(shared))


def _first(needles, kind):
    chosen = sorted(text for text, name in needles.kinds.items() if name == kind)
    assert chosen, "precondition not reached: no needle of kind %s in scan set A" % kind
    return chosen[0]


class _Cases(object):
    """Runs cases one by one: each in its own scratch temporary folder, under capfd and caplog,
    through the real sink, keeping what each printed in a file outside the private tree."""

    def __init__(self, tmp_path, monkeypatch, capfd, caplog, repo):
        self.tmp_path, self.monkeypatch, self.capfd, self.caplog = tmp_path, monkeypatch, capfd, caplog
        self.repo = repo
        self.outputs = []
        caplog.set_level(logging.DEBUG)

    def run(self, name, argv, environ, code, expected, repo=None, **seams):
        number = len(self.outputs)
        scratch = self.tmp_path / ("case_scratch_%02d" % number)
        scratch.mkdir()
        self.monkeypatch.setattr(tempfile, "tempdir", str(scratch))
        self.capfd.readouterr()
        self.caplog.clear()
        options = dict(fetch=fixture.fake_fetch_for(fixture.FIXED_NOW), clock=lambda: fixture.FIXED_NOW)
        options.update(seams)
        got = hourly.main(list(argv), out=None, environ=environ,
                          repo_root=repo or self.repo, sink=True, **options)
        captured = self.capfd.readouterr()
        assert captured.err == "", "%s: something reached standard error" % name
        assert [record.getMessage() for record in self.caplog.records] == [], (
            "%s: something was logged" % name)
        assert os.listdir(str(scratch)) == [], "%s: the temporary folder is not empty" % name
        assert got == code, "%s: exit code %d" % (name, got)
        _check_lines(name, captured.out)
        lines = captured.out.splitlines()
        for line in expected:
            assert line in lines, "%s: an expected line is missing" % name
        path = _write(self.tmp_path / "outputs" / ("case_%02d.txt" % number), captured.out)
        self.outputs.append((name, path))
        return lines

    def assert_all_clean(self, world, seens, documents):
        needles_a, needles_b = _set_a(world.repo), _set_b(world, seens, documents)
        for name, path in self.outputs:
            _scans_clean(path, world.repo, needles_a, needles_b, name)


# -- every path of the runner ----------------------------------------------------------------------

DRY_OK = ["mode: dry", "inputs: ok", "study: ok", "dry run: nothing was written to the database"]


def test_tracer_every_run_path_output_is_vocabulary_and_scans_clean(
        tmp_path, monkeypatch, capfd, caplog, world):
    cases = _Cases(tmp_path, monkeypatch, capfd, caplog, world.repo)
    seen_real, seen_fast = Seen(), Seen()
    fast = _recording(fixture.fast_prepare, seen_fast)
    duplicate_text, duplicate_document = _duplicate_mapping(tmp_path)
    duplicate = {"PANDAPOWER_MAPPING_B64": duplicate_text}

    cases.run("dry success on the real engine", ["run"], _env(world), 0, DRY_OK,
              prepare=_recording(engine.prepare_run, seen_real))
    cases.run("dry with a noisy study", ["run"], _env(world), 0, DRY_OK,
              prepare=_noisy(fast))
    cases.run("dry success under GitHub Actions", ["run"], _env(world, GITHUB_ACTIONS="true"), 0,
              DRY_OK, prepare=fast)
    cases.run("dry, duplicated outage", ["run"], _env(world, **duplicate), 1,
              ["mode: dry", "inputs: ok", "study: failed at stage mapping"],
              prepare=_recording(engine.prepare_run, seen_fast))
    cases.run("live, duplicated outage, connect fails", ["run"], _env(world, live=True, **duplicate),
              3, ["mode: live", "run status: not_recorded"],
              prepare=_recording(engine.prepare_run, seen_fast), connect=_planted_failure)
    cases.run("live, fast study, connect fails", ["run"], _env(world, live=True), 3,
              ["mode: live", "run status: not_recorded"], prepare=fast, connect=_planted_failure)
    cases.run("live placeholder", ["run"], _env(world, live=True), 2,
              ["mode: live", "inputs: ok", "placeholder: refused"],
              prepare=fast, backend_loader=lambda folder: engine.PLACEHOLDER_BACKEND)
    missing = _env(world)
    del missing["PANDAPOWER_NETWORK_B64"]
    cases.run("missing secret", ["run"], missing, 2, ["inputs: refused (missing_secret)"],
              prepare=fast)
    cases.run("bad base64", ["run"], _env(world, PANDAPOWER_NETWORK_B64="!!!!"), 2,
              ["inputs: refused (bad_base64)"], prepare=fast)
    cases.run("oversized secret", ["run"], _env(
        world, PANDAPOWER_SETTINGS_B64=_b64(b"a" * (engine.MAX_RECORD_BYTES + 1))), 2,
        ["inputs: refused (too_large)"], prepare=fast)
    cases.run("records refused", ["run"], _env(world, PANDAPOWER_SETTINGS_B64=_placeholder_settings(world)),
              2, ["records: refused (placeholder_source)"], prepare=fast)
    cases.run("exception in prepare", ["run"], _env(world), 2, ["error: unexpected (RuntimeError)"],
              prepare=_raising_prepare)
    cases.run("usage", ["bogus"], _env(world), 2, [hourly.USAGE_LINE])

    assert seen_real.run_ids and seen_real.results, "precondition not reached: the real study ran"
    assert len(cases.outputs) == 13
    cases.assert_all_clean(world, [seen_real, seen_fast], [duplicate_document, duplicate_text])


# -- soak and the owner commands -------------------------------------------------------------------


class _Result(object):
    def __init__(self, rows=None, one=None):
        self._rows = rows
        self._one = one

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._one


class _FakeConnection(object):
    """A connection that answers the two statements of the per-solver gap check and refuses any
    other (the shape of the soak tests' fake)."""

    def __init__(self, rows, current_slot):
        object.__setattr__(self, "_rows", rows)
        object.__setattr__(self, "_current", current_slot)

    def __setattr__(self, name, value):
        pass

    def execute(self, sql, params=None):
        if sql == gaps.RUNS_SQL:
            return _Result(rows=list(self._rows))
        if sql == gaps.CURRENT_HOUR_SQL:
            return _Result(one=(self._current,))
        raise AssertionError("unexpected statement")

    def close(self):
        pass


def _soak_connector():
    hour = datetime.timedelta(hours=1)
    current = datetime.datetime(2026, 11, 24, 12, 0, 0, tzinfo=datetime.timezone.utc)
    rows = [(current - k * hour, "pandapower", "ok") for k in range(1, 25) if k != 7]
    rows += [(current - 3 * hour, "psse", "ok"), (current - 9 * hour, "psse", "ok")]
    return lambda: _FakeConnection(rows, current)


def test_soak_and_owner_command_output_scans_clean(tmp_path, monkeypatch, capfd, caplog, world):
    cases = _Cases(tmp_path, monkeypatch, capfd, caplog, world.repo)
    environ = _env(world)

    lines = cases.run("soak with gaps", ["soak"], environ, 0, [], connect=_soak_connector())
    assert any(line.startswith("gap check: solver pandapower") for line in lines)
    cases.run("soak, connect fails", ["soak"], environ, 6, ["gap check: could not run"],
              connect=_planted_failure)
    cases.run("bundle written", ["bundle"], {}, 0, ["bundle: verified", "bundle: written"],
              clock=lambda: LATER)
    cases.run("bundle exists", ["bundle"], {}, 2, ["bundle: refused (exists)"], clock=lambda: LATER)
    cases.run("bundle in CI", ["bundle"], {"GITHUB_ACTIONS": "true"}, 2, ["bundle: refused (in_ci)"])
    bare = replay_fixture.make_repo(tmp_path / "bare")
    cases.run("bundle without records", ["bundle"], {}, 2, ["bundle: refused (records_missing)"],
              repo=bare)

    log = _write(tmp_path / "downloads" / "run.log", "\n".join(
        ["2026-11-26T10:20:04.1234567Z mode: dry", "2026-11-26T10:20:41.1234567Z study: ok"]) + "\n")
    cases.run("scan-log clean", ["scan-log", "--log", log], {}, 0, ["scan-log: lines=2 findings=0"])
    dirty = _write(tmp_path / "downloads" / "dirty.log",
                   "note %s\nnothing here\n" % _first(_set_a(world.repo), "mapping_key"))
    lines = cases.run("scan-log with findings", ["scan-log", "--log", dirty], {}, 1,
                      ["scan-log: lines=2 findings=1"])
    assert lines[1].startswith("scan-log: finding line=1 kind=")
    cases.run("scan-log refused", ["scan-log", "--log", str(tmp_path / "downloads" / "absent.log")],
              {}, 2, ["scan-log: refused (log_missing)"])

    assert len(cases.outputs) == 9
    cases.assert_all_clean(world, [], [])


# -- teeth -----------------------------------------------------------------------------------------


def test_scan_teeth_fire_on_planted_values(tmp_path, world):
    seen = Seen()
    buffer = io.StringIO()
    code = hourly.main(["run"], out=buffer, environ=_env(world),
                       prepare=_recording(fixture.fast_prepare, seen),
                       fetch=fixture.fake_fetch_for(fixture.FIXED_NOW),
                       clock=lambda: fixture.FIXED_NOW, sink=False)
    assert code == 0
    text = buffer.getvalue()
    _check_lines("teeth baseline", text)
    assert seen.run_ids, "precondition not reached: the recording study saw a run id"

    printed = _write(tmp_path / "outputs" / "clean.txt", text)
    needles_a, needles_b = _set_a(world.repo), _set_b(world, [seen], [])
    _scans_clean(printed, world.repo, needles_a, needles_b, "clean output")

    # Each planted value is appended to a copy of the clean output, and the scan or the token check
    # that should catch it must report a hit. The clean output is never touched.
    def planted(name, value):
        copy = text + "note %s\n" % value
        return _write(tmp_path / "planted" / (name + ".txt"), copy), copy

    password = fixture.PLANTED["db_password"]
    path, copy = planted("password", password)
    assert private_leak_scan.scan_paths([path], needles=needles_b, root=world.repo) != [], (
        "tooth 1 (writer password) did not fire in the scan")
    assert _tokens_of(copy) & needles_b, "tooth 1 (writer password) did not fire in the token check"

    branch_key = _first(needles_a, "mapping_key")
    path, _copy = planted("branch_key", branch_key)
    hits = private_leak_scan.scan_paths([path], needles=needles_a, root=world.repo)
    assert [item.pattern for item in hits] == ["mapping_key"], "tooth 2 (branch key) did not fire"

    target = _first(needles_a, "scaling_target")
    path, _copy = planted("target", target)
    hits = private_leak_scan.scan_paths([path], needles=needles_a, root=world.repo)
    assert any(item.pattern == "scaling_target" for item in hits), (
        "tooth 3 (scaling target) did not fire")

    value = world.secrets["PANDAPOWER_SETTINGS_B64"]
    fragment = [token for token in _TOKEN.findall(value) if len(token) >= 20][0]
    path, copy = planted("fragment", fragment)
    assert private_leak_scan.scan_paths([path], needles=needles_b, root=world.repo) != [], (
        "tooth 4 (base64 fragment) did not fire in the scan")
    assert fragment in _tokens_of(copy) & needles_b, (
        "tooth 4 (base64 fragment) did not fire in the token check")

    run_id = seen.run_ids[0]
    path, copy = planted("run_id", run_id)
    assert private_leak_scan.scan_paths([path], needles=needles_b, root=world.repo) != [], (
        "tooth 5 (run id) did not fire in the scan")
    assert run_id in _tokens_of(copy) & needles_b, "tooth 5 (run id) did not fire in the token check"

    # The vocabulary check can fail too: a workflow command and a bus key are both caught.
    for bad in ("::error::x", "branch " + _BRANCH_KEY):
        with pytest.raises(AssertionError):
            _check_lines("planted line", text + bad + "\n")

    # Without a plant the same scans stay clean: the teeth are not an artefact of the scan settings.
    _scans_clean(printed, world.repo, needles_a, needles_b, "clean output after the teeth")
