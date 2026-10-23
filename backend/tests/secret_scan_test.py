"""
Repeatable scan of every git-tracked file for credentials (production-pipeline
Phase 4, DB-04, ROADMAP SC4). Runs in the normal suite.

The scan reports the path, the line number and the pattern name only, never the
matched text, so a failure message cannot itself leak what it found. A planted
control proves that each pattern fires. The pattern strings and the plants are
assembled from pieces, so this file never matches itself.

Follows backend/tests/city_rating_test.py's conventions (module-level imports,
plain asserts, no test classes, no network).
"""

import os
import re
import subprocess

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_MAX_BYTES = 2 * 1024 * 1024
_SKIP_SUFFIXES = (".joblib", ".npz", ".png", ".jpg", ".pdf", ".xlsx")

_SCHEME = "postgres" + "(?:ql)?://"
_PG_URL = re.compile(_SCHEME + r"([^\s:/@'\"`]+):([^\s@/'\"`]+)@")
_SB_KEY = re.compile("sb_" + "secret_" + r"[A-Za-z0-9_-]{16,}")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{7,}\.eyJ[A-Za-z0-9_-]{7,}\.[A-Za-z0-9_-]{10,}")
_ALTER_ROLE = re.compile(
    r"(?i)\balter\s+role\s+\S+(?:\s+with)?\s+(?:encrypted\s+)?password\s+'([^']*)'"
)

_PLACEHOLDER_WORDS = {"password", "your-password", "yourpassword", "redacted", "pw", "pwd"}


def _is_placeholder(credential: str) -> bool:
    """Angle, square or curly brackets, ${VAR} / $VAR, all asterisks, all x, REDACTED, 'password'."""
    value = credential.strip()
    if not value:
        return True
    if value[0] in "<[{" and value[-1] in ">]}":
        return True
    if re.fullmatch(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?", value):
        return True
    if set(value) == {"*"} or re.fullmatch(r"[xX]+", value):
        return True
    return value.lower() in _PLACEHOLDER_WORDS


def _scan_line(line: str):
    """The pattern names found on one line."""
    found = []
    for match in _PG_URL.finditer(line):
        if not _is_placeholder(match.group(2)):
            found.append("pg_url_credential")
    if _SB_KEY.search(line):
        found.append("supabase_secret_key")
    if _JWT.search(line):
        found.append("jwt")
    for match in _ALTER_ROLE.finditer(line):
        if not _is_placeholder(match.group(1)):
            found.append("alter_role_literal")
    return found


def _readable(path: str) -> bool:
    if path.lower().endswith(_SKIP_SUFFIXES) or not os.path.isfile(path):
        return False
    if os.path.getsize(path) > _MAX_BYTES:
        return False
    with open(path, "rb") as handle:
        return b"\x00" not in handle.read(8192)


def _scan(paths):
    """(path, line number, pattern name) for every credential-shaped line; never the matched text."""
    findings = []
    for path in paths:
        if not _readable(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as handle:
            for number, line in enumerate(handle, start=1):
                for name in _scan_line(line):
                    findings.append((path, number, name))
    return findings


def _tracked_files():
    inside = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=_REPO_ROOT,
                            capture_output=True, text=True)
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        pytest.skip("not a git checkout")
    listed = subprocess.run(["git", "ls-files", "-z"], cwd=_REPO_ROOT, capture_output=True, check=True)
    return [os.path.join(_REPO_ROOT, name.decode("utf-8", "replace"))
            for name in listed.stdout.split(b"\0") if name]


def test_tracked_files_hold_no_credentials():
    findings = _scan(_tracked_files())
    shown = [f"{os.path.relpath(path, _REPO_ROOT)}:{number}:{name}" for path, number, name in findings]
    assert findings == [], "credential-shaped text in tracked files: " + ", ".join(shown)


def test_the_scanner_flags_planted_credentials_and_ignores_placeholders(tmp_path):
    secret = "Zx9" + "Qw7" + "Lk2"
    encoded = "Zx9%40" + "Qw7%2F" + "Lk2"
    user = "dlr_writer." + "abcdefghijklmnop"
    host = "@aws-0-us-east-1.pooler.example.invalid:5432/postgres"
    scheme = "postgres" + "ql://"
    plants = [
        (scheme + user + ":" + secret + host, "pg_url_credential"),
        ("DATABASE_URL=" + scheme + user + ":" + encoded + host, "pg_url_credential"),
        ("key = " + "sb_" + "secret_" + "A1b2C3d4E5f6G7h8I9j0", "supabase_secret_key"),
        ("token: " + "eyJ" + "hbGciOiJIUzI1NiJ9" + "." + "eyJ" + "zdWIiOiIxMjM0NTY3ODkwIn0" + "." + "SflKxwRJSMeKKF2QT4fw",
         "jwt"),
        ("ALTER ROLE dlr_writer WITH " + "PASS" + "WORD '" + secret + "';", "alter_role_literal"),
        ("alter role dlr_writer " + "pass" + "word '" + secret + "';", "alter_role_literal"),
    ]
    placeholders = [
        scheme + user + ":<password>" + host,
        scheme + "postgres.[ref]:[YOUR-" + "PASSWORD]" + host,
        scheme + "u:${SUPABASE_DB_URL}" + host,
        scheme + "u:$DB_" + "PASS" + host,
        scheme + "u:{secret}" + host,
        scheme + "u:*****" + host,
        scheme + "u:xxxx" + host,
        scheme + "u:REDACTED" + host,
        scheme + "u:" + "PASS" + "WORD" + host,
        scheme + "127.0.0.1:5432/db",
        "export SUPABASE_DB_URL=" + scheme + "...",
        "sb_" + "secret_" + "xxxx",
        "ALTER ROLE dlr_writer WITH " + "PASS" + "WORD '<password>';",
        "ALTER ROLE dlr_writer WITH " + "PASS" + "WORD :'writer_" + "pw';",
        "eyJ" + "short" + "." + "eyJ" + "short" + "." + "abc",
    ]
    planted = tmp_path / "planted.txt"
    planted.write_text("\n".join(text for text, _ in plants) + "\n", encoding="utf-8")
    clean = tmp_path / "clean.txt"
    clean.write_text("\n".join(placeholders) + "\n", encoding="utf-8")

    found = _scan([str(planted), str(clean)])
    assert found == [(str(planted), number, name) for number, (_, name) in enumerate(plants, start=1)]
    # The report holds no matched text.
    assert all(secret not in repr(item) and encoded not in repr(item) for item in found)

    # Binary and oversized files are skipped, not scanned.
    binary = tmp_path / "model.joblib"
    binary.write_bytes((plants[0][0] + "\n").encode())
    nul = tmp_path / "nul.bin"
    nul.write_bytes(b"\x00" + (plants[0][0] + "\n").encode())
    assert _scan([str(binary), str(nul)]) == []


def test_env_file_is_ignored_and_untracked():
    ignored = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=_REPO_ROOT)
    if ignored.returncode == 128:
        pytest.skip("not a git checkout")
    assert ignored.returncode == 0, ".env must be git-ignored"
    tracked = subprocess.run(["git", "ls-files", "--", ".env"], cwd=_REPO_ROOT,
                             capture_output=True, text=True, check=True)
    assert tracked.stdout.strip() == ""
