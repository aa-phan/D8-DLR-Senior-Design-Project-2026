"""
The session's output bundle (pandapower-solver Phase 1, plan 01-02): one work folder that
collects every output, a manifest with a sha256 per member, one zip written under a `.partial`
name and renamed only after every member hash is re-read from the finished archive, and the
masked summary the teammate pastes back.

The summary is built from fixed line templates filled with integers, versions and words from
SUMMARY_WORDS (plus a class name or a stage name), and `render_summary` raises ValueError on
anything else, so a bus number, a branch key, a path, a user name or a machine name cannot reach
the text by construction. The text then passes `mask_identity` (the environment's identity values
and the output folder) and `redaction.redact` as a backstop.

Honest scope: this module is plain file and text handling and is proven on the Mac with a fake
psspy (backend/tests/psse_session_test.py). That Windows lets the work folder be deleted while
PSS/E still holds its console log open is UNVERIFIED until the session of plan 01-10, which is why
`WorkFolder.remove` is best effort and reports what it could not delete.

Standard library plus psse_job only, Python 3.7 syntax (D-05).
"""

import collections
import hashlib
import json
import os
import re
import zipfile

from psse_job import constants, redaction

BUNDLE_FORMAT = 1
SESSION_PREFIX = "psse_pp_session_"
MANIFEST_NAME = "manifest.json"
# The marker keys of the private JSON files of this phase, assembled from pieces so that no
# tracked source holds them as a literal (the leak guard's shape layer would match the source).
MANIFEST_MARKER = "psse_pp_" + "session_manifest"
MEMBER_MARKER = "psse_pp_" + "session_member"
MEMBER_NAME_RE = re.compile(r"[a-z0-9_]+(?:/[a-z0-9_]+)*\.(?:raw|json|txt)\Z")

_STAMP_RE = re.compile(r"[0-9]{8}T[0-9]{6}Z\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_VERSION_RE = re.compile(r"[0-9]+(?:\.[0-9]+){0,3}\Z")
_CLASS_RE = re.compile(r"[A-Z][A-Za-z]{0,39}\Z")
_SECTION_NAME_RE = re.compile(r"[a-z_]{1,40}\Z")
_CHUNK = 1024 * 1024
_MAX_COUNT = 10 ** 9


class BundleRefused(ValueError):
    """The bundle would be malformed or would overwrite something; the message never holds a path."""


# -- the vocabulary of the printed summary -------------------------------------------------------

SECTION_WORDS = ("network", "reference", "settings", "scaling")
STATUS_WORDS = ("ok", "failed", "skipped")
OUTCOME_WORDS = ("complete", "partial", "failed", "interrupted", "checked")
MODE_WORDS = ("run", "check")
CHECK_WORDS = ("case index", "base solve")
STATE_WORDS = ("deleted", "kept", "not deleted", "written", "not written", "left for the wrapper")
DETAIL_WORDS = (
    "no case index", "count mismatch", "no raw export", "log unreadable", "none selected",
    "not run", "not attempted", "unavailable", "unknown",
)
# Every count name a section returns. The later plans' counts are listed now so they never edit
# this file: reference (plan 01-03), settings and scaling (plan 01-04).
NETWORK_COUNT_NAMES = (
    "buses", "loads", "fixed_shunts", "machines", "lines", "transformers", "three_winding",
    "switched_shunts", "areas", "controlling_transformers",
)
COUNT_NAMES = NETWORK_COUNT_NAMES + (
    "attempts", "revision",
    "cities", "cities_ok", "outages", "converged", "not_converged", "margin_points",
    "extended_reads_unavailable",
    "read", "measured", "unavailable", "fingerprints", "fingerprints_ok",
    "experiments", "experiments_ok",
)


def _unique(items):
    seen = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return tuple(seen)


SUMMARY_WORDS = _unique(
    SECTION_WORDS + STATUS_WORDS + OUTCOME_WORDS + MODE_WORDS + CHECK_WORDS + STATE_WORDS
    + DETAIL_WORDS + tuple(constants.FAILED_STAGES) + COUNT_NAMES)

CLOSING_WITH_ZIP = "send the zip to the owner by the private channel, then delete it from the Desktop."
CLOSING_WITHOUT_ZIP = "no zip was written."


def _alternation(words):
    return "(?:%s)" % "|".join(re.escape(word) for word in sorted(words, key=len, reverse=True))


_WORD = _alternation(SUMMARY_WORDS)
_ITEM = "(?:%s|[A-Z][A-Za-z]{0,39})" % _WORD
_VERSION = "(?:[0-9]+(?:[.][0-9]+){0,3}|unknown)"
_COUNT = "(?:%s (?:-?[0-9]{1,10}|unknown))" % _alternation(COUNT_NAMES)

SUMMARY_LINE_PATTERNS = tuple(re.compile(pattern + r"\Z") for pattern in (
    "session: %s" % _alternation(OUTCOME_WORDS),
    "mode: %s" % _alternation(MODE_WORDS),
    "python: %s" % _VERSION,
    "psse: %s" % _VERSION,
    "section %s: %s" % (_alternation(SECTION_WORDS), _alternation(STATUS_WORDS)),
    "section %s counts: %s(?: %s)*" % (_alternation(SECTION_WORDS), _COUNT, _COUNT),
    "section %s detail: %s(?:; %s)*" % (_alternation(SECTION_WORDS), _ITEM, _ITEM),
    "check %s: %s" % (_alternation(CHECK_WORDS), _alternation(STATUS_WORDS)),
    "check %s detail: %s(?:; %s)*" % (_alternation(CHECK_WORDS), _ITEM, _ITEM),
    "note: %s(?:; %s)*" % (_ITEM, _ITEM),
    "members: [0-9]{1,6}",
    "zip: %s" % _alternation(("written", "not written")),
    "mapping copy: %s" % _alternation(("deleted", "kept", "not deleted")),
    "work folder: %s" % _alternation(("deleted", "left for the wrapper")),
    re.escape(CLOSING_WITH_ZIP),
    re.escape(CLOSING_WITHOUT_ZIP),
))

SummaryReport = collections.namedtuple("SummaryReport", [
    "mode", "outcome", "python_version", "psse_version", "sections", "checks", "notes",
    "members", "zip_state", "mapping_state", "work_state",
])
# sections: ((name, status, detail tuple, counts dict), ...) in SECTIONS order;
# checks: ((name, status, detail tuple), ...); notes: a tuple of summary words.


def class_word(exc):
    """The class name of `exc` when it is a plain capitalised identifier, else "Exception"."""
    name = type(exc).__name__
    return name if _CLASS_RE.match(name) else "Exception"


def _word(value, allowed):
    if value not in allowed:
        raise ValueError("a summary field is outside its vocabulary")
    return value


def _item(value):
    if isinstance(value, str) and (value in SUMMARY_WORDS or _CLASS_RE.match(value)):
        return value
    raise ValueError("a summary detail is neither a summary word nor a class name")


def safe_item(value):
    """`value` when it may appear in a summary detail (a summary word or a class name), else "unknown"."""
    try:
        return _item(value)
    except ValueError:
        return "unknown"


def _detail(items):
    return "; ".join(_item(item) for item in items)


def _version(value):
    return value if isinstance(value, str) and _VERSION_RE.match(value) else "unknown"


def _counts(counts):
    pairs = []
    for name in sorted(counts):
        value = counts[name]
        if name not in COUNT_NAMES:
            raise ValueError("a summary count name is outside its vocabulary")
        if value is None:
            pairs.append("%s unknown" % name)
        elif isinstance(value, int) and not isinstance(value, bool) and abs(value) <= _MAX_COUNT:
            pairs.append("%s %d" % (name, value))
        else:
            raise ValueError("a summary count is not a small integer")
    return " ".join(pairs)


def _int(value):
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 999999:
        raise ValueError("a summary number is out of range")
    return value


def mask_identity(text, environ, extra=()):
    """`text` with the values of USERNAME, COMPUTERNAME, USERDOMAIN, USERPROFILE, HOME and every
    string of `extra` (the output folder) replaced, when at least 3 characters long."""
    values = []
    for name in ("USERNAME", "COMPUTERNAME", "USERDOMAIN", "USERPROFILE", "HOME"):
        value = environ.get(name)
        if isinstance(value, str):
            values.append(value.strip())
    values.extend(item for item in extra if isinstance(item, str))
    for value in sorted(set(item for item in values if len(item) >= 3), key=len, reverse=True):
        text = text.replace(value, "MASKED")
    return text


def render_summary(report, environ=None, extra=()):
    """The printed summary of `report` (a SummaryReport) as ASCII text, one line per fact.

    Raises ValueError for anything outside the fixed vocabulary. The result is masked with
    `mask_identity` and passed through `redaction.redact` as a backstop.
    """
    lines = [
        "session: %s" % _word(report.outcome, OUTCOME_WORDS),
        "mode: %s" % _word(report.mode, MODE_WORDS),
        "python: %s" % _version(report.python_version),
        "psse: %s" % _version(report.psse_version),
    ]
    for name, status, detail, counts in report.sections:
        lines.append("section %s: %s" % (_word(name, SECTION_WORDS), _word(status, STATUS_WORDS)))
        if counts:
            lines.append("section %s counts: %s" % (name, _counts(counts)))
        if detail:
            lines.append("section %s detail: %s" % (name, _detail(detail)))
    for name, status, detail in report.checks:
        lines.append("check %s: %s" % (_word(name, CHECK_WORDS), _word(status, STATUS_WORDS)))
        if detail:
            lines.append("check %s detail: %s" % (name, _detail(detail)))
    if report.notes:
        lines.append("note: %s" % _detail(report.notes))
    zip_state = _word(report.zip_state, ("written", "not written"))
    lines.append("members: %d" % _int(report.members))
    lines.append("zip: %s" % zip_state)
    lines.append("mapping copy: %s" % _word(report.mapping_state, ("deleted", "kept", "not deleted")))
    lines.append("work folder: %s" % _word(report.work_state, ("deleted", "left for the wrapper")))
    lines.append(CLOSING_WITH_ZIP if zip_state == "written" else CLOSING_WITHOUT_ZIP)
    text = "\n".join(lines)
    environ = os.environ if environ is None else environ
    text = mask_identity(text, environ, extra)
    text = redaction.redact(text, redaction.env_secrets(environ), 20000)
    return text.encode("ascii", "replace").decode("ascii")


# -- the work folder -----------------------------------------------------------------------------


def stamp(now):
    """`YYYYMMDDTHHMMSSZ` of the aware or naive-UTC datetime `now`."""
    return now.strftime("%Y%m%dT%H%M%SZ")


def _hash_file(path):
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _check_member_name(name):
    if not isinstance(name, str) or not MEMBER_NAME_RE.match(name):
        raise BundleRefused("a member name is not of the allowed shape")
    if name == MANIFEST_NAME:
        raise BundleRefused("the manifest name is reserved")
    return name


def read_manifest(data):
    """The manifest dict of `data` (bytes or text); BundleRefused for anything not exactly a
    manifest of this bundle format. Fails closed and never echoes the content."""
    try:
        text = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else data
        manifest = json.loads(text)
    except (ValueError, UnicodeDecodeError):
        raise BundleRefused("the manifest is not valid JSON")
    if not isinstance(manifest, dict) or manifest.get(MANIFEST_MARKER) != 1:
        raise BundleRefused("the manifest marker is missing")
    if manifest.get("bundle_format") != BUNDLE_FORMAT:
        raise BundleRefused("the bundle format is not the one this reader knows")
    for key in ("created_utc", "mode", "python_version", "psse_version", "case_sha256",
                "mapping_sha256", "mapping_placeholder", "sections", "members"):
        if key not in manifest:
            raise BundleRefused("the manifest lacks a required key")
    for key in ("case_sha256", "mapping_sha256"):
        value = manifest[key]
        if value is not None and not (isinstance(value, str) and _SHA256_RE.match(value)):
            raise BundleRefused("a manifest hash is malformed")
    members = manifest["members"]
    if not isinstance(members, dict):
        raise BundleRefused("the manifest members are malformed")
    for name, entry in members.items():
        if (not isinstance(name, str) or not MEMBER_NAME_RE.match(name) or name == MANIFEST_NAME
                or not isinstance(entry, dict)
                or not (isinstance(entry.get("sha256"), str) and _SHA256_RE.match(entry["sha256"]))
                or not isinstance(entry.get("bytes"), int) or isinstance(entry.get("bytes"), bool)
                or entry["bytes"] < 0
                or not (isinstance(entry.get("section"), str)
                        and _SECTION_NAME_RE.match(entry["section"]))):
            raise BundleRefused("a manifest member entry is malformed")
    sections = manifest["sections"]
    if not isinstance(sections, list):
        raise BundleRefused("the manifest sections are malformed")
    for section in sections:
        if (not isinstance(section, dict)
                or not (isinstance(section.get("name"), str) and _SECTION_NAME_RE.match(section["name"]))
                or section.get("status") not in STATUS_WORDS
                or not isinstance(section.get("detail"), list)
                or not isinstance(section.get("counts"), dict)
                or not isinstance(section.get("members"), list)):
            raise BundleRefused("a manifest section entry is malformed")
    return manifest


class WorkFolder(object):
    """`<out_dir>/psse_pp_session_<stamp>/`: the one place the session writes, and its zip."""

    def __init__(self, out_dir, stamp_text):
        if not isinstance(stamp_text, str) or not _STAMP_RE.match(stamp_text):
            raise BundleRefused("the session stamp is malformed")
        self.out_dir = os.path.abspath(out_dir)
        self.name = SESSION_PREFIX + stamp_text
        self.path = os.path.join(self.out_dir, self.name)
        self.zip_path = self.path + ".zip"
        self.partial_path = self.zip_path + ".partial"
        for existing in (self.path, self.zip_path, self.partial_path):
            if os.path.lexists(existing):
                raise BundleRefused("a session folder or zip with this name already exists")
        try:
            os.makedirs(self.path)
        except OSError:
            raise BundleRefused("the work folder could not be created")
        self._members = {}

    # -- members -------------------------------------------------------------------------------

    def member_path(self, name):
        """A path inside the folder for PSS/E to write to; creates the parent folders."""
        _check_member_name(name)
        path = os.path.join(self.path, *name.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    def _record(self, name, section):
        if not isinstance(section, str) or not _SECTION_NAME_RE.match(section):
            raise BundleRefused("a member section name is malformed")
        digest, size = _hash_file(os.path.join(self.path, *name.split("/")))
        self._members[name] = {"sha256": digest, "bytes": size, "section": section}

    def add_bytes(self, name, data, section):
        _check_member_name(name)
        if name in self._members:
            raise BundleRefused("a member with this name was already added")
        path = self.member_path(name)
        try:
            with open(path, "xb") as handle:
                handle.write(data)
        except FileExistsError:
            raise BundleRefused("a member file with this name already exists")
        self._record(name, section)

    def add_json(self, name, obj, section):
        """Adds `obj` (a dict) with the member marker key set to 1, dumped with sorted keys."""
        if not isinstance(obj, dict):
            raise BundleRefused("a JSON member must be an object")
        document = dict(obj)
        document[MEMBER_MARKER] = 1
        text = json.dumps(document, sort_keys=True, allow_nan=False, indent=1) + "\n"
        self.add_bytes(name, text.encode("ascii"), section)

    def register(self, name, section):
        """Add the file PSS/E already wrote at `member_path(name)`; a missing file is refused."""
        _check_member_name(name)
        if name in self._members:
            raise BundleRefused("a member with this name was already added")
        path = os.path.join(self.path, *name.split("/"))
        if not os.path.isfile(path):
            raise BundleRefused("a registered member file does not exist")
        self._record(name, section)

    def members(self):
        return sorted(self._members)

    # -- manifest and zip ----------------------------------------------------------------------

    def write_manifest(self, meta, sections):
        """Write manifest.json: `meta` holds created_utc, mode, python_version, psse_version,
        case_sha256, mapping_sha256 and mapping_placeholder; `sections` is a list of dicts with
        name, status, detail, counts (and optionally members)."""
        listed = []
        for section in sections:
            entry = dict(section)
            entry["detail"] = list(entry.get("detail", ()))
            entry["counts"] = dict(entry.get("counts", {}))
            entry.setdefault("members", sorted(
                name for name, item in self._members.items() if item["section"] == entry["name"]))
            listed.append(entry)
        manifest = {
            MANIFEST_MARKER: 1,
            "bundle_format": BUNDLE_FORMAT,
            "sections": listed,
            "members": dict((name, dict(item)) for name, item in self._members.items()),
        }
        for key in ("created_utc", "mode", "python_version", "psse_version", "case_sha256",
                    "mapping_sha256", "mapping_placeholder"):
            manifest[key] = meta[key]
        text = json.dumps(manifest, sort_keys=True, allow_nan=False, indent=1) + "\n"
        data = text.encode("ascii")
        read_manifest(data)
        with open(os.path.join(self.path, MANIFEST_NAME), "wb") as handle:
            handle.write(data)

    def zip_and_verify(self):
        """Write `<folder>.zip.partial`, re-read every member and compare with the manifest, then
        rename it to `<folder>.zip` and return that path. A failure removes the partial file."""
        manifest_path = os.path.join(self.path, MANIFEST_NAME)
        try:
            with open(manifest_path, "rb") as handle:
                manifest_bytes = handle.read()
            manifest = read_manifest(manifest_bytes)
            if os.path.lexists(self.zip_path):
                raise BundleRefused("the zip name is already taken")
            with zipfile.ZipFile(self.partial_path, "w", zipfile.ZIP_DEFLATED) as archive:
                for name in sorted(manifest["members"]):
                    archive.write(os.path.join(self.path, *name.split("/")), name)
                archive.write(manifest_path, MANIFEST_NAME)
            self._verify_archive(self.partial_path, manifest, manifest_bytes)
            os.rename(self.partial_path, self.zip_path)
        except BaseException:
            self._remove_partial()
            raise
        return self.zip_path

    @staticmethod
    def _verify_archive(path, manifest, manifest_bytes):
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            expected = sorted(list(manifest["members"]) + [MANIFEST_NAME])
            if sorted(names) != expected or len(set(names)) != len(names):
                raise BundleRefused("the archive members differ from the manifest")
            if archive.testzip() is not None:
                raise BundleRefused("the archive failed its own integrity check")
            for name, entry in manifest["members"].items():
                data = archive.read(name)
                if (len(data) != entry["bytes"]
                        or hashlib.sha256(data).hexdigest() != entry["sha256"]):
                    raise BundleRefused("an archive member does not match its manifest hash")
            if archive.read(MANIFEST_NAME) != manifest_bytes:
                raise BundleRefused("the archived manifest differs from the written one")

    def _remove_partial(self):
        try:
            if os.path.lexists(self.partial_path):
                os.remove(self.partial_path)
        except OSError:
            pass

    def remove(self):
        """Delete the folder tree and any partial zip, best effort; returns the number of
        entries that could not be deleted (Windows keeps PSS/E's console log open)."""
        failures = 0
        if os.path.lexists(self.partial_path):
            try:
                os.remove(self.partial_path)
            except OSError:
                failures += 1
        for root, dirs, files in os.walk(self.path, topdown=False):
            for name in files:
                try:
                    os.remove(os.path.join(root, name))
                except OSError:
                    failures += 1
            for name in dirs:
                try:
                    os.rmdir(os.path.join(root, name))
                except OSError:
                    failures += 1
        try:
            os.rmdir(self.path)
        except FileNotFoundError:
            pass
        except OSError:
            failures += 1
        return failures
