"""
Repeatable scan of every git-tracked file for credentials (production-pipeline
Phase 4, DB-04, ROADMAP SC4). Runs in the normal suite. Since Phase 6 (D-10; the
repository has been public since 05-06) it also flags the Supabase project
address (project host, pooler user carrying a project reference) and the
publishable key, so none of them can be committed.

Owner-local exact-value check (D-10): the shape patterns above cannot know the real
project, so one more test compares every tracked file with the real values. Before any
push, export the variables in a shell (never from a committed file; this test never reads
.env or loads any dotenv file) and run

    export SUPABASE_URL=... SUPABASE_PUBLISHABLE_KEY=... SUPABASE_DB_URL=...
    /Users/aphan/Senior_Design/.venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/secret_scan_test.py

It reports only relative path and line number, never a value, and is skipped when none of
the three variables is exported (so CI keeps the shape scan only).

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
from urllib.parse import unquote, urlsplit

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_MAX_BYTES = 2 * 1024 * 1024
_SKIP_SUFFIXES = (".joblib", ".npz", ".png", ".jpg", ".pdf", ".xlsx")

_SCHEME = "postgres" + "(?:ql)?://"
_PG_URL = re.compile(_SCHEME + r"([^\s:/@'\"`]+):([^\s@/'\"`]+)@")
_SB_KEY = re.compile("sb_" + "secret_" + r"[A-Za-z0-9_-]{16,}")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{7,}\.eyJ[A-Za-z0-9_-]{7,}\.[A-Za-z0-9_-]{10,}")
# D-10 (Phase 6): the project address and the publishable key never reach the public repository.
# A project reference is 20 lowercase letters or digits (assumption A19 in 06-RESEARCH).
_SB_HOST = re.compile(r"\b[a-z0-9]{20}\." + "supa" + "base" + r"\.(?:co|in|red)\b")
_POOLER_REF = re.compile(r"\b(?:postgres|dlr_writer|authenticator)\.[a-z0-9]{20}\b")
_SB_PUBLISHABLE = re.compile("sb_" + "publishable_" + r"[A-Za-z0-9_-]{16,}")
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
    if _SB_HOST.search(line):
        found.append("supabase_project_host")
    if _POOLER_REF.search(line):
        found.append("pooler_project_reference")
    if _SB_PUBLISHABLE.search(line):
        found.append("supabase_publishable_key")
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


_MIN_EXACT_CHARS = 8


def _exact_values(env) -> list:
    """
    The real project values the owner exported (D-10): the full URL, its host, its project
    reference (the first host label), the publishable key, and the pooler user's reference
    and host from the database URL. Reads only the mapping it is given, never a file.
    Values shorter than 8 characters are dropped so a stray short string cannot match
    everywhere.
    """
    found = []

    url = (env.get("SUPABASE_URL") or "").strip().rstrip("/")
    if url:
        found.append(url)
        try:
            host = urlsplit(url if "//" in url else "//" + url).hostname
        except ValueError:
            host = None
        if host:
            found.append(host)
            found.append(host.split(".", 1)[0])

    key = (env.get("SUPABASE_PUBLISHABLE_KEY") or "").strip()
    if key:
        found.append(key)

    db_url = (env.get("SUPABASE_DB_URL") or "").strip()
    if db_url:
        try:
            parts = urlsplit(db_url)
            user, host = parts.username, parts.hostname
        except ValueError:
            user = host = None
        if user and "." in unquote(user):
            found.append(unquote(user).split(".", 1)[1])
        if host:
            found.append(host)

    unique = []
    for value in found:
        if len(value) >= _MIN_EXACT_CHARS and value not in unique:
            unique.append(value)
    return unique


def _scan_exact(paths, values):
    """(path, line number) for every line holding one of the values; never the value itself."""
    findings = []
    if not values:
        return findings
    for path in paths:
        if not _readable(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as handle:
            for number, line in enumerate(handle, start=1):
                if any(value in line for value in values):
                    findings.append((path, number))
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
    ref = "abcdefghij" + "klmnopqrst"  # a 20-character project reference, built at run time
    domain = ".supa" + "base.co"
    plants = [
        (scheme + user + ":" + secret + host, "pg_url_credential"),
        ("DATABASE_URL=" + scheme + user + ":" + encoded + host, "pg_url_credential"),
        ("key = " + "sb_" + "secret_" + "A1b2C3d4E5f6G7h8I9j0", "supabase_secret_key"),
        ("token: " + "eyJ" + "hbGciOiJIUzI1NiJ9" + "." + "eyJ" + "zdWIiOiIxMjM0NTY3ODkwIn0" + "." + "SflKxwRJSMeKKF2QT4fw",
         "jwt"),
        ("ALTER ROLE dlr_writer WITH " + "PASS" + "WORD '" + secret + "';", "alter_role_literal"),
        ("alter role dlr_writer " + "pass" + "word '" + secret + "';", "alter_role_literal"),
        ("curl https://" + ref + domain + "/rest/v1/latest_rating", "supabase_project_host"),
        ("SUPABASE_" + "URL=https://" + ref + domain, "supabase_project_host"),
        ("user = postgres." + ref, "pooler_project_reference"),
        ("apikey: " + "sb_" + "publishable_" + "A1b2C3d4E5f6G7h8I9j0", "supabase_publishable_key"),
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
        "curl https://<project-ref>" + domain + "/rest/v1/latest_rating",
        "curl https://[ref]" + domain + "/rest/v1/latest_rating",
        "curl ${SUPABASE_" + "URL}/rest/v1/latest_rating",
        "curl https://" + "abcdefghij" + "klmnop" + domain + "/rest/v1/latest_rating",  # 16-character dummy reference
        "user = postgres." + "<project-ref>",
        "user = postgres." + "[ref]",
        "user = postgres." + "...",
        "user = dlr_writer." + "abcdefghij" + "klmnop",  # 16-character dummy reference
        "host = aws-0-us-east-1.pooler" + domain.replace(".co", ".com"),
        "apikey: <publishable-key>",
        "apikey: " + "sb_" + "publishable_" + "xxxx",
        "apikey: ${SUPABASE_PUBLISHABLE_" + "KEY}",
    ]
    planted = tmp_path / "planted.txt"
    planted.write_text("\n".join(text for text, _ in plants) + "\n", encoding="utf-8")
    clean = tmp_path / "clean.txt"
    clean.write_text("\n".join(placeholders) + "\n", encoding="utf-8")

    found = _scan([str(planted), str(clean)])
    assert found == [(str(planted), number, name) for number, (_, name) in enumerate(plants, start=1)]
    # The report holds no matched text.
    assert all(secret not in repr(item) and encoded not in repr(item) for item in found)
    assert all(ref not in repr(item) and "A1b2C3d4E5f6G7h8I9j0" not in repr(item) for item in found)

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


# ---------------------------------------------------------------------------
# Owner-local exact-value scan (D-10)
# ---------------------------------------------------------------------------

_EXACT_VARIABLES = ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_DB_URL")


def test_exact_values_come_from_the_exported_variables_only():
    ref = "mnopqrst" + "uvwxyz0123" + "45"  # synthetic 20-character reference
    env = {
        "SUPABASE_URL": "https://" + ref + ".supa" + "base.co/",
        "SUPABASE_PUBLISHABLE_KEY": "  sb_" + "publishable_" + "A1b2C3d4E5f6G7h8  ",
        "SUPABASE_DB_URL": "postgres" + "ql://dlr_writer." + ref + ":pw@aws-0-eu-west-1.pooler.example.invalid:5432/postgres",
        "UNRELATED": "not-a-supabase-value-at-all",
    }
    values = _exact_values(env)
    assert "https://" + ref + ".supa" + "base.co" in values  # full URL, trailing slash removed
    assert ref + ".supa" + "base.co" in values  # host
    assert ref in values  # project reference (first host label and pooler user suffix)
    assert "sb_" + "publishable_" + "A1b2C3d4E5f6G7h8" in values
    assert "aws-0-eu-west-1.pooler.example.invalid" in values
    assert "not-a-supabase-value-at-all" not in values
    assert len(values) == len(set(values))
    # Nothing exported, or only values shorter than 8 characters: nothing to look for.
    assert _exact_values({}) == []
    assert _exact_values({"SUPABASE_URL": "", "SUPABASE_PUBLISHABLE_KEY": "short", "SUPABASE_DB_URL": "  "}) == []


def test_exact_value_scan_finds_a_planted_reference_without_printing_it(tmp_path):
    ref = "zyxwvuts" + "rqponmlkji" + "98"  # synthetic 20-character reference
    planted = tmp_path / "planted.md"
    planted.write_text("intro\nsee https://" + ref + ".example.invalid/docs\nend\n", encoding="utf-8")
    clean = tmp_path / "clean.md"
    clean.write_text("intro\nsee https://<project-ref>.example.invalid/docs\n", encoding="utf-8")
    binary = tmp_path / "model.joblib"
    binary.write_bytes((ref + "\n").encode())

    found = _scan_exact([str(planted), str(clean), str(binary)], [ref])
    assert found == [(str(planted), 2)]
    assert all(ref not in repr(item) for item in found)
    assert _scan_exact([str(planted)], []) == []


def test_tracked_files_hold_no_real_project_values_from_env():
    values = _exact_values(os.environ)
    if not values:
        pytest.skip("owner-local check: export " + ", ".join(_EXACT_VARIABLES) + " in a shell to run it")
    findings = _scan_exact(_tracked_files(), values)
    shown = [f"{os.path.relpath(path, _REPO_ROOT)}:{number}" for path, number in findings]
    assert findings == [], (
        "a real value from the exported environment (" + ", ".join(_EXACT_VARIABLES)
        + ") appears in tracked files: " + ", ".join(shown)
    )
