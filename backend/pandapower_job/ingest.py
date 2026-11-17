"""
Safe handling of the incoming session zip (pandapower-solver Phase 1, plan 01-09: PSE-04).

The zip comes from another machine over a private channel and may be damaged or tampered with
(research Pitfall 9). `ingest_zip` extracts it into `<sessions>/<session name>/` only when every
check passes, and checks everything about the archive's directory before it writes one byte:

- the file is a zip and is named like a session zip (`SESSION_NAME_RE`);
- the entry count, each declared size, the declared total and the compression ratio are under the
  caps (`MAX_MEMBERS` and the others); the same sizes are checked again while reading, so a
  header that lies about its size cannot pass;
- every entry name is a plain bundle member name (`bundle.MEMBER_NAME_RE`: lower-case letters,
  digits and underscores, folders by "/", no "..", no leading "/", no backslash, no capitals), no
  name appears twice, no entry is a symbolic link or encrypted;
- the manifest is present and valid (`bundle.read_manifest`), and the entries are exactly the
  manifest's list plus the manifest (nothing unlisted, nothing missing);
- while extracting, every member's size and sha256 equal the manifest's.

The extraction goes into `<destination>.partial` and is renamed into place only after every member
has been verified; any refusal removes the partial folder and writes nothing else. A destination
that already exists is never touched. Refusal messages hold a reason word (one of
`INGEST_REFUSAL_REASONS`) and nothing from the archive.

`verify_session_dir` re-runs the manifest and hash checks on an extracted folder (the `check`
command does this before it trusts a byte), and `check_mapping` refuses a mapping file whose
sha256 differs from the one the session recorded (T-01-33: a comparison against the wrong mapping).
"""

import hashlib
import json
import os
import re
import shutil
import stat
import zipfile
import zlib

from psse_job import mapping as mapping_module
from psse_session import bundle
from pandapower_job import private

MAX_MEMBERS = 4000
MAX_MEMBER_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
MAX_MANIFEST_BYTES = 1024 * 1024

SESSION_NAME_RE = re.compile(re.escape(bundle.SESSION_PREFIX) + r"[0-9]{8}T[0-9]{6}Z\Z")

INGEST_REFUSAL_REASONS = (
    "not_a_zip", "bad_zip_name", "no_manifest", "bad_manifest", "unlisted_member",
    "missing_member", "bad_member_name", "duplicate_member", "symlink_member",
    "encrypted_member", "too_many_members", "member_too_large", "total_too_large",
    "ratio_too_high", "hash_mismatch", "destination_exists", "mapping_mismatch")

# Entries `verify_session_dir` accepts in a session folder besides the manifest's members: the
# folders `check` writes and the owner's explained-differences registry.
_CHECK_DIR_RE = re.compile(r"check_[0-9]{8}T[0-9]{6}Z\Z")
REGISTRY_FILE_NAME = "explained_differences.json"

_CHUNK = 1024 * 1024
_SYMLINK_MODE = 0o120000
_ENCRYPTED_FLAG = 0x1


class IngestRefused(ValueError):
    """The archive or session folder is not acceptable. `reason` is one of INGEST_REFUSAL_REASONS."""

    def __init__(self, reason):
        self.reason = reason
        ValueError.__init__(self, "ingest refused: %s" % reason)


class IngestResult(object):
    """`session_dir` (the extracted folder), `manifest` (its dict) and `members_verified`."""

    def __init__(self, session_dir, manifest, members_verified):
        self.session_dir = session_dir
        self.manifest = manifest
        self.members_verified = members_verified


def _is_symlink(info):
    return stat.S_IFMT((info.external_attr >> 16) & 0xFFFF) == _SYMLINK_MODE


def _check_entries(infos):
    """The checks that need only the zip's directory; raises IngestRefused."""
    if len(infos) > MAX_MEMBERS:
        raise IngestRefused("too_many_members")
    seen = set()
    total = 0
    for info in infos:
        name = info.filename
        if not isinstance(name, str) or not bundle.MEMBER_NAME_RE.match(name):
            raise IngestRefused("bad_member_name")
        if name in seen:
            raise IngestRefused("duplicate_member")
        seen.add(name)
        if _is_symlink(info):
            raise IngestRefused("symlink_member")
        if info.flag_bits & _ENCRYPTED_FLAG:
            raise IngestRefused("encrypted_member")
        cap = MAX_MANIFEST_BYTES if name == bundle.MANIFEST_NAME else MAX_MEMBER_BYTES
        if info.file_size > cap:
            raise IngestRefused("member_too_large")
        if info.file_size > 0 and info.file_size > MAX_COMPRESSION_RATIO * max(info.compress_size, 1):
            raise IngestRefused("ratio_too_high")
        total += info.file_size
        if total > MAX_TOTAL_BYTES:
            raise IngestRefused("total_too_large")
    return seen


def _read_bounded(archive, info, limit):
    """The bytes of an entry, reading at most `limit` + 1; a longer body is a lying header."""
    with archive.open(info) as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise IngestRefused("member_too_large")
    return data


def _read_manifest_entry(archive, infos):
    by_name = dict((info.filename, info) for info in infos)
    if bundle.MANIFEST_NAME not in by_name:
        raise IngestRefused("no_manifest")
    data = _read_bounded(archive, by_name[bundle.MANIFEST_NAME], MAX_MANIFEST_BYTES)
    try:
        return bundle.read_manifest(data), data
    except bundle.BundleRefused:
        raise IngestRefused("bad_manifest")


def _check_listing(names, manifest):
    listed = set(manifest["members"]) | {bundle.MANIFEST_NAME}
    if names - listed:
        raise IngestRefused("unlisted_member")
    if listed - names:
        raise IngestRefused("missing_member")


def _extract(archive, infos, manifest, manifest_bytes, partial):
    """Extract every entry into `partial` and verify each against the manifest. Returns the number
    of listed members verified."""
    total = 0
    verified = 0
    by_name = dict((info.filename, info) for info in infos)
    base = os.path.realpath(partial)
    for name in sorted(by_name):
        info = by_name[name]
        target = os.path.join(partial, *name.split("/"))
        if not os.path.realpath(target).startswith(base + os.sep):
            raise IngestRefused("bad_member_name")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if name == bundle.MANIFEST_NAME:
            data = manifest_bytes
        else:
            limit = min(MAX_MEMBER_BYTES, manifest["members"][name]["bytes"])
            data = _read_bounded(archive, info, limit)
            total += len(data)
            if total > MAX_TOTAL_BYTES:
                raise IngestRefused("total_too_large")
            entry = manifest["members"][name]
            if (len(data) != entry["bytes"]
                    or hashlib.sha256(data).hexdigest() != entry["sha256"]):
                raise IngestRefused("hash_mismatch")
            verified += 1
        with open(target, "xb") as handle:
            handle.write(data)
    return verified


def ingest_zip(zip_path, sessions_dir=None, repo_root=None):
    """
    Extract the session zip `zip_path` into `<sessions_dir>/<zip name without .zip>/` (default
    `<repo>/data/private/pandapower/sessions`) and return an IngestResult. Raises IngestRefused
    (see the module docstring) or private.PrivatePathRefused when the destination is not a private
    ignored place. A refusal leaves no partial folder and never touches an existing destination.
    """
    base_name = os.path.basename(str(zip_path))
    stem = base_name[:-4] if base_name.endswith(".zip") else None
    if stem is None or not SESSION_NAME_RE.match(stem):
        raise IngestRefused("bad_zip_name")
    if sessions_dir is None:
        sessions_dir = os.path.join(private.private_root(repo_root), "pandapower", "sessions")
    destination = os.path.join(str(sessions_dir), stem)
    partial = destination + ".partial"
    private.require_private(destination, repo_root)
    private.require_private(partial, repo_root)
    try:
        archive = zipfile.ZipFile(str(zip_path))
    except (zipfile.BadZipFile, OSError, ValueError, NotImplementedError):
        raise IngestRefused("not_a_zip")
    with archive:
        try:
            infos = archive.infolist()
            names = _check_entries(infos)
            manifest, manifest_bytes = _read_manifest_entry(archive, infos)
            _check_listing(names, manifest)
        except (zipfile.BadZipFile, NotImplementedError, RuntimeError, EOFError, zlib.error):
            raise IngestRefused("not_a_zip")
        if os.path.lexists(destination) or os.path.lexists(partial):
            raise IngestRefused("destination_exists")
        private.make_private_dir(partial, repo_root)
        try:
            verified = _extract(archive, infos, manifest, manifest_bytes, partial)
            os.rename(partial, destination)
        except (zipfile.BadZipFile, NotImplementedError, RuntimeError, EOFError, zlib.error):
            shutil.rmtree(partial, ignore_errors=True)
            raise IngestRefused("not_a_zip")
        except BaseException:
            shutil.rmtree(partial, ignore_errors=True)
            raise
    return IngestResult(destination, manifest, verified)


# -- an extracted session folder -----------------------------------------------------------------


def _read_file(path, limit):
    try:
        with open(path, "rb") as handle:
            data = handle.read(limit + 1)
    except OSError:
        return None
    return None if len(data) > limit else data


def _extra_entries(session_dir, listed):
    """True when the folder holds a file or folder the manifest does not list (other than the
    folders `check` writes and the registry file)."""
    for current, dirs, files in os.walk(session_dir, followlinks=False):
        relative_dir = os.path.relpath(current, session_dir)
        top = None if relative_dir == "." else relative_dir.split(os.sep)[0]
        if top is not None and _CHECK_DIR_RE.match(top):
            dirs[:] = []
            continue
        if top is None:
            dirs[:] = [name for name in dirs if not _CHECK_DIR_RE.match(name)]
        for name in files:
            relative = name if top is None else "/".join(relative_dir.split(os.sep) + [name])
            if relative in listed or (top is None and name == REGISTRY_FILE_NAME):
                continue
            return True
        for name in dirs:
            if os.path.islink(os.path.join(current, name)):
                return True
    return False


def verify_session_dir(session_dir):
    """
    The manifest dict of an extracted session folder, after re-checking that every member the
    manifest lists exists as a plain file of the listed size and sha256 and that nothing else is in
    the folder. IngestRefused reasons: no_manifest, bad_manifest, missing_member, symlink_member,
    hash_mismatch, unlisted_member.
    """
    session_dir = str(session_dir)
    manifest_path = os.path.join(session_dir, bundle.MANIFEST_NAME)
    if not os.path.isfile(manifest_path) or os.path.islink(manifest_path):
        raise IngestRefused("no_manifest")
    data = _read_file(manifest_path, MAX_MANIFEST_BYTES)
    if data is None:
        raise IngestRefused("bad_manifest")
    try:
        manifest = bundle.read_manifest(data)
    except bundle.BundleRefused:
        raise IngestRefused("bad_manifest")
    for name, entry in manifest["members"].items():
        path = os.path.join(session_dir, *name.split("/"))
        if os.path.islink(path):
            raise IngestRefused("symlink_member")
        if not os.path.isfile(path):
            raise IngestRefused("missing_member")
        content = _read_file(path, MAX_MEMBER_BYTES)
        if (content is None or len(content) != entry["bytes"]
                or hashlib.sha256(content).hexdigest() != entry["sha256"]):
            raise IngestRefused("hash_mismatch")
    if _extra_entries(session_dir, set(manifest["members"]) | {bundle.MANIFEST_NAME}):
        raise IngestRefused("unlisted_member")
    return manifest


def check_mapping(manifest, mapping_path, allow_placeholder=False):
    """
    The `psse_job.mapping.Mapping` of the file `mapping_path`, after checking that the sha256 of
    its bytes equals the manifest's `mapping_sha256` (IngestRefused "mapping_mismatch" otherwise,
    before the file is parsed). A file that cannot be read, is too large or is not a valid mapping
    (or is a placeholder without `allow_placeholder`) raises `mapping.MappingError`.
    """
    data = _read_file(str(mapping_path), mapping_module.MAX_MAPPING_BYTES)
    if data is None:
        raise mapping_module.MappingError(["mapping file could not be read"])
    if hashlib.sha256(data).hexdigest() != manifest.get("mapping_sha256"):
        raise IngestRefused("mapping_mismatch")
    return mapping_module.parse_mapping(data, allow_placeholder=allow_placeholder)
