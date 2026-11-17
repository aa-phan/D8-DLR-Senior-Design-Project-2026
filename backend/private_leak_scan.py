"""
Leak scanner for the private PSS/E reference-session data (pandapower-solver Phase 1, PSE-04, D-07).

The repository is public and git history is permanent, so the session's export, reference answers,
settings, mapping copies and converted network must never reach a commit. This scanner is the
guard that runs before that can happen. It is standard library only and has three layers:

  path    no file under data/private/ or named with the psse_pp_session prefix is in the working
          tree as a tracked or not-ignored file, and the ignore rule for data/private/ is in place.
          Proves the folder and the session artefacts cannot be added by name.
  shape   no file holds RAW-file structure (section terminator and begin lines, a case header on the
          first non-empty line) or one of the marker keys every private JSON file of this phase
          carries. Proves a copied private file is caught by its shape alone, with no private value
          needed, so this layer runs everywhere including CI.
  needle  no file holds a value derived from the real files under data/private/: mapping
          from-to-ckt keys (both orientations), scaling targets in the forms they would be typed,
          each private file's sha256 and decimals with at least five fractional digits. Proves a
          typed or pasted private value is caught. Skipped, never failed, when data/private/ is
          absent (CI, other machines).

Output is `relative/path:line:layer:pattern`, one per finding, and never the matched text, so a
terminal, a CI log or a test failure cannot leak what was found. Exit status: 0 clean, 1 findings,
2 usage error, unreadable allow-list or not a git checkout. A count of files that could not be
scanned (binary, over 2 MiB) is written to stderr.

Scope. The working-tree mode scans tracked files plus untracked files that are not ignored, because
that is what the next broad `git add` would take; a scan of tracked files alone fires after the
commit, which is too late. Tool output folders (graph builders, note tools) that are untracked and
not ignored are therefore inside the scan. Whether those tools honour .gitignore and skip
data/private/ is unverified (research assumption A13); the working-tree scan is the backstop, not a
proof that they do.

Local pre-commit step. Staged mode scans the content in the git index, not the working tree, so a
file staged and then edited or deleted is still judged on what would be committed. To run it before
every commit, put these two lines in .git/hooks/pre-commit and make the file executable:

    #!/bin/sh
    exec .venv/bin/python backend/private_leak_scan.py --staged

Allow-list. backend/private_leak_allow.json, when present, is a JSON list of objects with the keys
path and sha256. A file is exempt from the shape and needle layers only when both its path and its
sha256 match an entry, so any edit to an allowed file brings it back into the scan. A sha256 listed
there is also not a needle. A missing file allows nothing; a malformed file is exit status 2.

A private JSON file written by this phase carries one of the marker keys listed in SHAPE_PATTERNS.
A tracked source file that writes such a key as a JSON literal would match its own shape; assemble
the key from string pieces there, as this module does for its own patterns.
"""

import argparse
import collections
import hashlib
import json
import os
import re
import subprocess
import sys

Finding = collections.namedtuple("Finding", ["path", "line", "layer", "pattern"])

MAX_BYTES = 2 * 1024 * 1024
NUL_WINDOW = 8192
MIN_NEEDLE_CHARS = 5
SKIP_SUFFIXES = (".joblib", ".npz", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".xlsx",
                 ".zip", ".gz", ".pyc", ".woff", ".woff2")
PRIVATE_DIR = "data/private"
SESSION_PREFIX = "psse_pp_session"

# The shape layer. Every pattern is assembled from pieces so this source never matches itself.
_END_OF = "END" + " OF "
_BEGIN = "BEG" + "IN"
SHAPE_PATTERNS = collections.OrderedDict([
    # A RAW section terminator: a zero, a slash, then the end-of phrase (and no begin phrase after
    # it, which is the raw_begin line below).
    ("raw_terminator", re.compile(
        r"^\s*0\s*/\s*" + _END_OF + r"[A-Z0-9][A-Z0-9 -]* DATA\b(?!.*\b" + _BEGIN + r"\b)")),
    # A line that names the next RAW section.
    ("raw_begin", re.compile(r"\b" + _BEGIN + r" [A-Z0-9][A-Z0-9 -]* DATA\b")),
    # A RAW case header (IC 0 or 1, base MVA, revision 33 to 36); first non-empty line of a file only.
    ("raw_header", re.compile(r"^\s*[01]\s*,\s*[0-9]+(?:\.[0-9]*)?\s*,\s*3[3-6]\s*(?:,|/|$)")),
    # The marker keys every private JSON file of the phase carries.
    ("session_marker", re.compile('"psse_pp_' + 'session_' + '(?:manifest|member)"\\s*:')),
    ("pandapower_marker", re.compile('"pandapower_' + 'job_' + '(?:network|report|registry)"\\s*:')),
])
_LINE_SHAPES = ("raw_terminator", "raw_begin", "session_marker", "pandapower_marker")

_TOKEN = re.compile(r"[A-Za-z0-9._+\-]+")
_COMMA_NUMBER = re.compile(r"[0-9][0-9,]*[0-9](?:\.[0-9]+)?")
_EXPONENT = re.compile(r"^(.*[0-9])[eE][+-]?[0-9]+$")
_DECIMAL = re.compile(r"[0-9]+\.[0-9]+")


class GitError(RuntimeError):
    """git could not be run or reported an error; the message never holds file content."""


class AllowListError(ValueError):
    """The allow-list file exists but is not a list of objects with path and sha256."""


class NeedleSet(set):
    """A set of needle strings that remembers which kind (reported pattern name) each one is."""

    def __init__(self):
        set.__init__(self)
        self.kinds = {}

    def add_needle(self, text, kind):
        if len(text) >= MIN_NEEDLE_CHARS and text not in self:
            self.add(text)
            self.kinds[text] = kind


# ---------------------------------------------------------------------------
# Git and file listing
# ---------------------------------------------------------------------------

def _git(root, *args):
    try:
        done = subprocess.run(["git", *args], cwd=root, capture_output=True)
    except OSError:
        raise GitError("git could not be run")
    if done.returncode != 0:
        raise GitError("git %s failed (exit %d)" % (args[0], done.returncode))
    return done.stdout


def repo_root():
    """The repository folder: two levels above this file, confirmed with git rev-parse."""
    candidate = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        top = _git(candidate, "rev-parse", "--show-toplevel").decode("utf-8", "replace").strip()
    except GitError:
        return candidate
    return top or candidate


def _toplevel(folder):
    """The git toplevel of `folder`, or None when it is not inside a git checkout."""
    try:
        top = _git(folder, "rev-parse", "--show-toplevel").decode("utf-8", "replace").strip()
    except GitError:
        return None
    return top or None


def working_tree_files(root):
    """
    Absolute paths of tracked files plus untracked files that are not ignored: what the next
    broad `git add` would take. Sorted and deduplicated.
    """
    names = set()
    for args in (("ls-files", "-z"), ("ls-files", "--others", "--exclude-standard", "-z")):
        for name in _git(root, *args).split(b"\0"):
            if name:
                names.add(name.decode("utf-8", "replace"))
    return sorted(os.path.join(root, name) for name in names)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def _known_binary(name):
    return name.lower().endswith(SKIP_SUFFIXES)


def _read_text(path):
    """(status, text): status is ok, missing, binary or oversize. Text is decoded latin-1."""
    if not os.path.isfile(path):
        return "missing", ""
    if _known_binary(path):
        return "binary", ""
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return "oversize", ""
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError:
        return "missing", ""
    if b"\x00" in data[:NUL_WINDOW]:
        return "binary", ""
    return "ok", data.decode("latin-1")


# ---------------------------------------------------------------------------
# Needles
# ---------------------------------------------------------------------------

def _branch_key(from_bus, to_bus, ckt):
    try:
        if isinstance(from_bus, bool) or isinstance(to_bus, bool):
            return None
        return "%d-%d-%s" % (int(from_bus), int(to_bus), str(ckt).strip())
    except (TypeError, ValueError):
        return None


def _add_branch_keys(node, needles):
    key = _branch_key(node["from_bus"], node["to_bus"], node["ckt"])
    reverse = _branch_key(node["to_bus"], node["from_bus"], node["ckt"])
    for text in (key, reverse):
        if text:
            needles.add_needle(text, "mapping_key")


def _walk_json(node, needles):
    """Mapping keys from every object that names from_bus, to_bus and ckt, at any depth."""
    if isinstance(node, dict):
        if "from_bus" in node and "to_bus" in node and "ckt" in node:
            _add_branch_keys(node, needles)
        for value in node.values():
            _walk_json(value, needles)
    elif isinstance(node, list):
        for value in node:
            _walk_json(value, needles)


def derive_needles(private_root):
    """
    The needles derived from the files under `private_root`, as a NeedleSet. This task: mapping
    from-to-ckt keys in both orientations. Parsed with json only, never executed. An absent folder
    gives an empty set (the layer is skipped, never failed).
    """
    needles = NeedleSet()
    private_root = os.fspath(private_root)
    if not os.path.isdir(private_root):
        return needles
    for folder, names, files in os.walk(private_root):
        names.sort()
        for name in sorted(files):
            if not name.lower().endswith(".json"):
                continue
            try:
                with open(os.path.join(folder, name), "r", encoding="utf-8-sig") as handle:
                    parsed = json.load(handle)
                _walk_json(parsed, needles)
            except (OSError, ValueError, RecursionError):
                continue
    return needles


def _tokens(line):
    """Whole-token candidates of one line, so a needle is matched by set membership."""
    for match in _TOKEN.finditer(line):
        token = match.group()
        yield token
        trimmed = token.strip("+-._")
        if trimmed and trimmed != token:
            yield trimmed
        exponent = _EXPONENT.match(trimmed)
        if exponent:
            yield exponent.group(1)
        if "-" in trimmed:
            for part in trimmed.split("-"):
                if part:
                    yield part
    if "," in line:
        for match in _COMMA_NUMBER.finditer(line):
            run = match.group()
            if "," in run:
                yield run
                yield run.replace(",", "")


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

def _scan_text(text, needles):
    """(line number, layer, pattern) for shapes and needles in `text`; never the matched text."""
    hits = []
    kinds = getattr(needles, "kinds", None) or {}
    first = True
    for number, raw in enumerate(text.split("\n"), start=1):
        line = raw.rstrip("\r")
        if not line.strip():
            continue
        if first:
            first = False
            if SHAPE_PATTERNS["raw_header"].search(line):
                hits.append((number, "shape", "raw_header"))
        for name in _LINE_SHAPES:
            if SHAPE_PATTERNS[name].search(line):
                hits.append((number, "shape", name))
        if needles:
            seen = set()
            for token in _tokens(line):
                if token in needles:
                    kind = kinds.get(token, "needle")
                    if kind not in seen:
                        seen.add(kind)
                        hits.append((number, "needle", kind))
    return hits


def _path_findings(path, relative):
    """Path-layer findings for a file in the working tree, from its path relative to the root."""
    rel = relative.replace(os.sep, "/")
    if rel.startswith("../") or rel == "..":
        return []
    found = []
    if rel == PRIVATE_DIR or rel.startswith(PRIVATE_DIR + "/"):
        found.append(Finding(path, 0, "path", "private_path_in_tree"))
    if any(part.startswith(SESSION_PREFIX) for part in rel.split("/")):
        found.append(Finding(path, 0, "path", "session_artifact_path"))
    return found


def _scan_paths(paths, needles, root):
    findings = []
    unscanned = 0
    for path in paths:
        relative = os.path.relpath(path, root)
        findings.extend(_path_findings(path, relative))
        status, text = _read_text(path)
        if status in ("binary", "oversize"):
            unscanned += 1
        if status != "ok":
            continue
        for number, layer, pattern in _scan_text(text, needles):
            findings.append(Finding(path, number, layer, pattern))
    findings.sort(key=lambda item: (item.path, item.line, item.layer, item.pattern))
    return findings, unscanned


def scan_paths(paths, needles=None, allow=None, root=None):
    """
    Findings for the given absolute file paths, sorted by path then line. `needles` is a set (a
    NeedleSet from derive_needles reports its kind names); `root` is the repository folder used to
    judge the path layer (default: repo_root()). Never carries the matched text.
    """
    findings, _ = _scan_paths(paths, needles or (), root or repo_root())
    return findings


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def _check_ignore_rule(root):
    """The path-layer finding for a missing ignore rule, or an empty list."""
    done = subprocess.run(["git", "check-ignore", "-q", PRIVATE_DIR + "/pandapower/x.json"],
                          cwd=root, capture_output=True)
    if done.returncode == 0:
        return []
    return [Finding(PRIVATE_DIR, 0, "path", "private_dir_not_ignored")]


def _display(path, root):
    return os.path.relpath(path, root) if os.path.isabs(path) else path


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="private_leak_scan.py",
        description="Scan the working tree for private PSS/E session data. Prints "
                    "path:line:layer:pattern per finding, never the matched text.")
    parser.add_argument("--private-root", default=None,
                        help="folder the needles are derived from (default: <repo>/data/private)")
    try:
        args = parser.parse_args(argv)
    except SystemExit as stop:
        return stop.code if isinstance(stop.code, int) else 2

    root = _toplevel(os.getcwd()) or _toplevel(os.path.dirname(os.path.abspath(__file__)))
    if root is None:
        sys.stderr.write("private_leak_scan: not a git checkout\n")
        return 2
    private_root = args.private_root or os.path.join(root, "data", "private")
    try:
        needles = derive_needles(private_root)
        findings = _check_ignore_rule(root)
        scanned, unscanned = _scan_paths(working_tree_files(root), needles, root)
    except GitError as error:
        sys.stderr.write("private_leak_scan: %s\n" % error)
        return 2
    findings.extend(scanned)
    for item in findings:
        sys.stdout.write("%s:%d:%s:%s\n" % (_display(item.path, root), item.line, item.layer, item.pattern))
    sys.stderr.write("private_leak_scan: %d file(s) not scanned (binary or over 2 MiB)\n" % unscanned)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
