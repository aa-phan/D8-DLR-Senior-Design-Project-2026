"""
Tests of the safe handling of the incoming session zip and of the private-path guard
(pandapower-solver Phase 1, plan 01-09: PSE-04, research Pitfall 9; threats T-01-31 to T-01-35):
`pandapower_job.ingest` (zip slip, zip bomb, allow-list, hash and mapping checks) and
`pandapower_job.private` (a write can never land outside an ignored `data/private/`).

Every archive is built with `zipfile` in tmp_path and every repository is a throwaway git
repository whose `.gitignore` holds `/data/private/`, passed as `repo_root`; no real data and no
network. Refusal messages are checked to hold the reason word only.
"""

import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import warnings
import zipfile

import pytest

pandapower = pytest.importorskip("pandapower")   # the cli imports it

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
for _folder in (_BACKEND, _HERE):
    if _folder not in sys.path:
        sys.path.insert(0, _folder)

from psse_job import mapping as mapping_module  # noqa: E402
from psse_session import bundle  # noqa: E402
from pandapower_job import cli, ingest, private  # noqa: E402

EXAMPLE_MAPPING = os.path.join(_ROOT, "docs", "data-science", "schema", "psse_mapping_example.json")
STAMP = "20261116T150000Z"
STEM = bundle.SESSION_PREFIX + STAMP
MEMBERS = {
    "network/network.raw": b"first member text\n" * 3,
    "settings/settings.json": b'{"a": 1}\n',
    "reference/austin/base.json": b'{"b": 2}\n',
}
MARKER = "pandapower_job_" + "report"


# -- helpers --------------------------------------------------------------------------------------


def make_repo(path, ignore=True):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(path), "init", "-q"], check=True)
    if ignore:
        (path / ".gitignore").write_text("/data/private/\n", encoding="utf-8")
    return str(path)


def make_manifest(members, **changes):
    manifest = {
        bundle.MANIFEST_MARKER: 1, "bundle_format": 1, "created_utc": "2026-11-16T15:00:00Z",
        "mode": "run", "python_version": "3.12.0", "psse_version": "36.4.0", "case_sha256": None,
        "mapping_sha256": None, "mapping_placeholder": False,
        "sections": [{"name": "network", "status": "ok", "detail": [], "counts": {},
                      "members": sorted(members)}],
        "members": dict((name, {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
                                "section": "network"}) for name, data in members.items())}
    manifest.update(changes)
    return manifest


def manifest_bytes(manifest):
    return (json.dumps(manifest, sort_keys=True) + "\n").encode("ascii")


def write_zip(path, entries, compression=zipfile.ZIP_DEFLATED):
    """A zip of `entries`, a list of (name or ZipInfo, bytes), written as given."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with zipfile.ZipFile(str(path), "w", compression) as archive:
            for name, data in entries:
                archive.writestr(name, data)
    return str(path)


def good_entries(members=None, manifest=None):
    members = dict(MEMBERS if members is None else members)
    manifest = make_manifest(members) if manifest is None else manifest
    return [(name, data) for name, data in sorted(members.items())] + [
        (bundle.MANIFEST_NAME, manifest_bytes(manifest))]


def info(name, attr=0):
    item = zipfile.ZipInfo(name)
    item.compress_type = zipfile.ZIP_DEFLATED
    item.external_attr = attr
    return item


class Case(object):
    def __init__(self, tmp_path):
        self.repo = make_repo(tmp_path / "repo")
        self.sessions = os.path.join(self.repo, "data", "private", "pandapower", "sessions")
        self.incoming = tmp_path / "incoming"
        self.incoming.mkdir()
        self.destination = os.path.join(self.sessions, STEM)

    def zip_path(self, name=STEM + ".zip"):
        return str(self.incoming / name)

    def ingest(self, zip_path):
        return ingest.ingest_zip(zip_path, self.sessions, self.repo)


def _replace(entries, name, data):
    return [(item, data if item == name else content) for item, content in entries]


def _bad_manifest_without_marker(entries):
    manifest = make_manifest(MEMBERS)
    del manifest[bundle.MANIFEST_MARKER]
    return good_entries(manifest=manifest)


def _bad_manifest_format_two(entries):
    return good_entries(manifest=make_manifest(MEMBERS, bundle_format=2))


def _no_manifest(entries):
    return entries[:-1]


def _unlisted(entries):
    return entries + [("extra/unlisted.json", b"{}")]


def _missing(entries):
    return entries[1:]


def _bad_name(name):
    def build(entries):
        return entries + [(name, b"{}")]
    return build


def _duplicate(entries):
    return entries + [(entries[0][0], b"another body")]


def _symlink(entries):
    return entries[:-1] + [(info("network/link.json", attr=(0o120777 << 16)), b"network/network.raw"),
                           entries[-1]]


def _encrypted(entries):
    return entries[:-1] + [("network/secret.json", b"{}"), entries[-1]]


def _mark_encrypted(path, name):
    """Set the encryption flag bit in the central-directory entry of `name` (zipfile resets the
    flag bits when it writes, so the bit has to be forged in the finished file)."""
    with open(path, "rb") as handle:
        data = bytearray(handle.read())
    start = 0
    while True:
        start = data.find(b"PK\x01\x02", start)
        assert start >= 0, "entry not found"
        length = int.from_bytes(data[start + 28:start + 30], "little")
        if bytes(data[start + 46:start + 46 + length]) == name.encode("ascii"):
            data[start + 8] |= 0x1
            break
        start += 4
    with open(path, "wb") as handle:
        handle.write(bytes(data))


def _changed(entries):
    return _replace(entries, "settings/settings.json", b'{"a": 2}\n')


UNSAFE = [
    ("not_a_zip", None, None, None),
    ("bad_zip_name", None, None, "other_name.zip"),
    ("no_manifest", _no_manifest, None, None),
    ("bad_manifest", _bad_manifest_without_marker, None, None),
    ("bad_manifest", _bad_manifest_format_two, None, None),
    ("unlisted_member", _unlisted, None, None),
    ("missing_member", _missing, None, None),
    ("bad_member_name", _bad_name("../escape.json"), None, None),
    ("bad_member_name", _bad_name("/abs.json"), None, None),
    pytest.param("bad_member_name", _bad_name("dir\\x.json"), None, None,
                 marks=pytest.mark.skipif(os.name != "posix",
                                          reason="zipfile turns a backslash into a slash on Windows")),
    ("bad_member_name", _bad_name("Upper.json"), None, None),
    ("duplicate_member", _duplicate, None, None),
    ("symlink_member", _symlink, None, None),
    ("encrypted_member", _encrypted, None, None),
    ("too_many_members", None, ("MAX_MEMBERS", 2), None),
    ("member_too_large", None, ("MAX_MEMBER_BYTES", 10), None),
    ("total_too_large", None, ("MAX_TOTAL_BYTES", 40), None),
    ("ratio_too_high", None, ("MAX_COMPRESSION_RATIO", 1), None),
    ("hash_mismatch", _changed, None, None),
]


def _build(case, reason, builder, zip_name):
    path = case.zip_path(zip_name or STEM + ".zip")
    if reason == "not_a_zip":
        with open(path, "wb") as handle:
            handle.write(b"this is not an archive\n")
        return path
    entries = good_entries()
    if builder is not None:
        entries = builder(entries)
    write_zip(path, entries)
    if reason == "encrypted_member":
        _mark_encrypted(path, "network/secret.json")
    return path


# -- Task 2: unsafe archives ----------------------------------------------------------------------


@pytest.mark.parametrize("reason,builder,cap,zip_name", UNSAFE)
def test_ingest_refuses_each_unsafe_archive(tmp_path, monkeypatch, reason, builder, cap, zip_name):
    case = Case(tmp_path)
    if cap is not None:
        monkeypatch.setattr(ingest, cap[0], cap[1])
    path = _build(case, reason, builder, zip_name)
    with pytest.raises(ingest.IngestRefused) as caught:
        case.ingest(path)
    assert caught.value.reason == reason
    assert str(caught.value) == "ingest refused: %s" % reason
    assert reason in ingest.INGEST_REFUSAL_REASONS
    assert not os.path.exists(case.destination)
    assert not os.path.exists(case.destination + ".partial")
    assert not os.path.exists(os.path.join(case.repo, "escape.json"))


def test_every_refusal_reason_but_the_mapping_one_is_exercised():
    exercised = set((item.values if hasattr(item, "values") else item)[0]
                    for item in UNSAFE) | {"destination_exists"}
    assert exercised == set(ingest.INGEST_REFUSAL_REASONS) - {"mapping_mismatch"}


def test_a_good_archive_is_extracted_and_verified(tmp_path):
    case = Case(tmp_path)
    path = write_zip(case.zip_path(), good_entries())
    result = case.ingest(path)
    assert result.session_dir == os.path.realpath(case.destination)
    assert result.members_verified == len(MEMBERS)
    assert not os.path.exists(case.destination + ".partial")
    for name, data in MEMBERS.items():
        with open(os.path.join(result.session_dir, *name.split("/")), "rb") as handle:
            assert handle.read() == data
    assert ingest.verify_session_dir(result.session_dir)["members"].keys() == MEMBERS.keys()


def test_an_existing_destination_is_refused_and_left_alone(tmp_path):
    case = Case(tmp_path)
    os.makedirs(case.destination)
    keep = os.path.join(case.destination, "keep.txt")
    with open(keep, "w") as handle:
        handle.write("untouched")
    with pytest.raises(ingest.IngestRefused) as caught:
        case.ingest(write_zip(case.zip_path(), good_entries()))
    assert caught.value.reason == "destination_exists"
    assert os.listdir(case.destination) == ["keep.txt"]
    with open(keep) as handle:
        assert handle.read() == "untouched"
    assert not os.path.exists(case.destination + ".partial")


def test_refusals_leave_no_partial_or_destination_folder(tmp_path, monkeypatch):
    case = Case(tmp_path)
    # the first member in name order extracts, the second does not match its hash: the folder the
    # first one went into must be gone
    members = dict(MEMBERS)
    entries = good_entries(members)
    entries = _replace(entries, "settings/settings.json", b'{"a": 3}\n')
    with pytest.raises(ingest.IngestRefused) as caught:
        case.ingest(write_zip(case.zip_path(), entries))
    assert caught.value.reason == "hash_mismatch"
    assert not os.path.exists(case.destination + ".partial")
    assert not os.path.exists(case.destination)
    assert os.listdir(case.sessions) == []

    # an interrupt in the middle of extraction removes the partial folder as well
    real = ingest._extract

    def interrupted(archive, infos, manifest, manifest_bytes_, partial):
        os.makedirs(os.path.join(partial, "network"), exist_ok=True)
        with open(os.path.join(partial, "network", "half.json"), "wb") as handle:
            handle.write(b"{")
        raise KeyboardInterrupt()

    monkeypatch.setattr(ingest, "_extract", interrupted)
    with pytest.raises(KeyboardInterrupt):
        case.ingest(write_zip(case.zip_path(), good_entries()))
    monkeypatch.setattr(ingest, "_extract", real)
    assert os.listdir(case.sessions) == []


def test_a_body_longer_than_its_limit_is_refused_while_reading(tmp_path):
    path = write_zip(tmp_path / "body.zip", [("network/network.raw", b"x" * 100)])
    with zipfile.ZipFile(path) as archive:
        item = archive.infolist()[0]
        with pytest.raises(ingest.IngestRefused) as caught:
            ingest._read_bounded(archive, item, 10)
        assert caught.value.reason == "member_too_large"
        assert ingest._read_bounded(archive, item, 100) == b"x" * 100


def test_zip_slip_writes_nothing_outside_the_session_folder(tmp_path):
    case = Case(tmp_path)
    before = sorted(os.listdir(tmp_path))
    with pytest.raises(ingest.IngestRefused):
        case.ingest(write_zip(case.zip_path(), good_entries() + [("../../escape.json", b"{}")]))
    assert sorted(os.listdir(tmp_path)) == before
    assert not os.path.exists(os.path.join(case.repo, "escape.json"))


def test_verify_session_dir_detects_an_edit(tmp_path):
    case = Case(tmp_path)
    result = case.ingest(write_zip(case.zip_path(), good_entries()))
    directory = result.session_dir
    assert ingest.verify_session_dir(directory)["bundle_format"] == 1

    # folders `check` writes and the owner's registry file are not extra entries
    os.makedirs(os.path.join(directory, "check_20261116T160000Z"))
    with open(os.path.join(directory, "check_20261116T160000Z", "report.json"), "w") as handle:
        handle.write("{}")
    with open(os.path.join(directory, ingest.REGISTRY_FILE_NAME), "w") as handle:
        handle.write("{}")
    assert ingest.verify_session_dir(directory)

    target = os.path.join(directory, "settings", "settings.json")
    with open(target, "rb") as handle:
        original = handle.read()
    with open(target, "wb") as handle:
        handle.write(original.replace(b"1", b"7"))
    with pytest.raises(ingest.IngestRefused) as caught:
        ingest.verify_session_dir(directory)
    assert caught.value.reason == "hash_mismatch"
    with open(target, "wb") as handle:
        handle.write(original)

    stray = os.path.join(directory, "settings", "extra.json")
    with open(stray, "w") as handle:
        handle.write("{}")
    with pytest.raises(ingest.IngestRefused) as caught:
        ingest.verify_session_dir(directory)
    assert caught.value.reason == "unlisted_member"
    os.remove(stray)

    os.remove(target)
    with pytest.raises(ingest.IngestRefused) as caught:
        ingest.verify_session_dir(directory)
    assert caught.value.reason == "missing_member"
    os.symlink(os.path.join(directory, "network", "network.raw"), target)
    with pytest.raises(ingest.IngestRefused) as caught:
        ingest.verify_session_dir(directory)
    assert caught.value.reason == "symlink_member"
    os.remove(target)

    os.remove(os.path.join(directory, "manifest.json"))
    with pytest.raises(ingest.IngestRefused) as caught:
        ingest.verify_session_dir(directory)
    assert caught.value.reason == "no_manifest"


def _mapping_case(tmp_path, changed=False):
    with open(EXAMPLE_MAPPING, "rb") as handle:
        data = handle.read()
    digest = hashlib.sha256(data).hexdigest()
    if changed:
        assert b"2430.5" in data
        data = data.replace(b"2430.5", b"2430.6")
    path = tmp_path / "mapping_copy.json"
    path.write_bytes(data)
    return str(path), digest


def test_mapping_mismatch_is_refused_by_reason_only(tmp_path):
    case = Case(tmp_path)
    manifest_hash = _mapping_case(tmp_path)[1]
    entries = good_entries(manifest=make_manifest(MEMBERS, mapping_sha256=manifest_hash,
                                                  mapping_placeholder=True))
    result = case.ingest(write_zip(case.zip_path(), entries))
    manifest = ingest.verify_session_dir(result.session_dir)

    same, _digest = _mapping_case(tmp_path)
    loaded = ingest.check_mapping(manifest, same, allow_placeholder=True)
    assert loaded.sha256 == manifest["mapping_sha256"]
    # a placeholder mapping is refused unless the caller allows it
    with pytest.raises(mapping_module.MappingError):
        ingest.check_mapping(manifest, same, allow_placeholder=False)

    other, _digest = _mapping_case(tmp_path, changed=True)
    with pytest.raises(ingest.IngestRefused) as caught:
        ingest.check_mapping(manifest, other, allow_placeholder=True)
    assert caught.value.reason == "mapping_mismatch"
    assert str(caught.value) == "ingest refused: mapping_mismatch"

    out, err = io.StringIO(), io.StringIO()
    code = cli.main(["check", "--session", result.session_dir, "--mapping", other,
                     "--allow-placeholder"], out=out, err=err, repo_root=case.repo)
    assert code == 2 and out.getvalue().splitlines() == ["session: verified"]
    assert err.getvalue().splitlines() == ["mapping: refused (mapping_mismatch)"]
    # nothing was written next to the session
    assert [name for name in os.listdir(result.session_dir) if name.startswith("check_")] == []

    # an unreadable mapping is a refusal by reason as well
    code = cli.main(["check", "--session", result.session_dir, "--mapping",
                     str(tmp_path / "absent.json")], out=io.StringIO(), err=err, repo_root=case.repo)
    assert code == 2 and err.getvalue().splitlines()[-1] == "mapping: refused (mapping_invalid)"


# -- Task 2: unsafe output paths ------------------------------------------------------------------


def test_private_guard_refuses_unsafe_paths(tmp_path):
    repo = make_repo(tmp_path / "repo")
    private_dir = os.path.join(repo, "data", "private")
    os.makedirs(private_dir)

    def refused(path, reason, root=repo):
        with pytest.raises(private.PrivatePathRefused) as caught:
            private.require_private(path, root)
        assert caught.value.reason == reason
        assert str(caught.value) == "private path refused: %s" % reason
        assert reason in private.REFUSAL_REASONS

    inside = os.path.join(private_dir, "pandapower", "x.json")
    assert private.require_private(inside, repo) == os.path.realpath(inside)
    assert private.private_root(repo) == os.path.join(os.path.realpath(repo), "data", "private")

    # outside the private folder, in the repository and beside it
    refused(os.path.join(repo, "docs", "x.json"), "outside_private_root")
    refused(str(tmp_path / "elsewhere.json"), "outside_private_root")
    refused(private_dir, "outside_private_root")
    refused(os.path.join(private_dir, "..", "tracked.json"), "outside_private_root")

    # a repository without the ignore rule
    bare = make_repo(tmp_path / "bare", ignore=False)
    os.makedirs(os.path.join(bare, "data", "private"))
    refused(os.path.join(bare, "data", "private", "x.json"), "not_ignored", bare)

    # a folder that is not a git repository
    plain = tmp_path / "plain"
    os.makedirs(plain / "data" / "private")
    refused(str(plain / "data" / "private" / "x.json"), "not_a_git_checkout", str(plain))

    # a link inside data/private that leads out of it
    outside = tmp_path / "outside_dir"
    outside.mkdir()
    os.symlink(str(outside), os.path.join(private_dir, "link"))
    refused(os.path.join(private_dir, "link", "x.json"), "symlink_escape")
    with pytest.raises(private.PrivatePathRefused) as caught:
        private.write_private_bytes(os.path.join(private_dir, "link", "x.json"), b"{}", repo)
    assert caught.value.reason == "symlink_escape"
    assert os.listdir(str(outside)) == []

    # an existing file under exclusive creation
    target = os.path.join(private_dir, "existing.json")
    private.write_private_bytes(target, b"first", repo)
    with pytest.raises(private.PrivatePathRefused) as caught:
        private.write_private_bytes(target, b"second", repo)
    assert caught.value.reason == "exists"
    with open(target, "rb") as handle:
        assert handle.read() == b"first"
    private.write_private_bytes(target, b"third", repo, exclusive=False)
    with open(target, "rb") as handle:
        assert handle.read() == b"third"


def test_private_writers_add_the_marker_and_keep_the_file_private(tmp_path):
    repo = make_repo(tmp_path / "repo")
    path = os.path.join(repo, "data", "private", "pandapower", "doc.json")
    written = private.write_private_json(path, {"b": 1, "a": [0.5]}, MARKER, repo)
    with open(written, "rb") as handle:
        text = handle.read().decode("ascii")
    document = json.loads(text)
    assert document == {"a": [0.5], "b": 1, MARKER: 1}
    assert list(document) == sorted(document)
    if os.name == "posix":  # Windows has no 0o600 file mode
        assert stat.S_IMODE(os.stat(written).st_mode) == 0o600
    with pytest.raises(ValueError):
        private.write_private_json(path + "2", {"x": float("nan")}, MARKER, repo)
    with pytest.raises(ValueError):
        private.write_private_json(path + "3", [1], MARKER, repo)
    made = private.make_private_dir(os.path.join(repo, "data", "private", "folder"), repo)
    assert os.path.isdir(made)
    with pytest.raises(private.PrivatePathRefused) as caught:
        private.make_private_dir(made, repo)
    assert caught.value.reason == "exists"
    with pytest.raises(private.PrivatePathRefused) as caught:
        private.make_private_dir(os.path.join(repo, "tracked_folder"), repo)
    assert caught.value.reason == "outside_private_root"
    assert not os.path.exists(os.path.join(repo, "tracked_folder"))
