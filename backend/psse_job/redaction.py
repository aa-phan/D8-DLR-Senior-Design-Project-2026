"""
Secret hygiene for every error the PSS/E job stores or logs (pss-e-integration Phase 1).

A port, not an import, of backend/supabase_store.py's redact rules: that module imports
pandas at the top and the job must stay standard-library only (D-05). The rules are the
same (postgres URLs, key=value pairs, explicit secrets longest first, cut AFTER
redaction), plus Supabase key tokens, JWT-shaped tokens and parenthesized resolved
addresses. backend/tests/psse_ratings_test.py checks parity on the shared cases.
"""

import re
import os
import urllib.parse

from psse_job import constants

_URL_RE = re.compile(r"postgres(?:ql)?://\S+", re.IGNORECASE)
_KEY_VALUE_RE = re.compile(
    r"(?i)\b(password|token|api_key|apikey|key|secret)=([^\s&;,'\"]+)"
)
# Pattern assembled from pieces so this file never holds a key-shaped literal.
_SB_TOKEN_RE = re.compile("sb_" + "(?:publishable|secret)_" + r"[A-Za-z0-9_-]+")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
# libpq's failure text names the server it tried, with its resolved address in parentheses.
_RESOLVED_ADDRESS_RE = re.compile(
    r"\((?:\d{1,3}\.){3}\d{1,3}\)|\((?:[0-9a-fA-F]{0,4}:){2,}[0-9a-fA-F:.]*\)"
)


def connection_identifiers(url):
    """
    The user, the project reference (the part of a pooler user after the first dot) and the
    host of a connection URL. They name the project, so an error message must not carry
    them. Items shorter than 3 characters are dropped (same rule as supabase_store).
    """
    if not url or not isinstance(url, str):
        return []
    try:
        parts = urllib.parse.urlsplit(url)
        host, user = parts.hostname, parts.username
    except ValueError:
        return []
    found = []
    if user:
        user = urllib.parse.unquote(user)
        found.append(user)
        if "." in user:
            found.append(user.split(".", 1)[1])
    if host:
        found.append(host)
    return [item for item in found if len(item) >= 3]


def _host_of(url):
    try:
        return urllib.parse.urlsplit(url).hostname
    except ValueError:
        return None


def env_secrets(env=None):
    """
    Every secret the job's environment can hold: the Supabase URL and its host, the
    publishable key, and the PSS/E database URL with its password (raw and percent-decoded)
    and connection identifiers. Unset or blank variables are skipped.
    """
    env = os.environ if env is None else env
    found = []

    def value(name):
        raw = env.get(name)
        if raw is None or not str(raw).strip():
            return None
        return str(raw).strip()

    api_url = value(constants.ENV_SUPABASE_URL)
    if api_url:
        found.append(api_url)
        host = _host_of(api_url)
        if host:
            found.append(host)
    key = value(constants.ENV_PUBLISHABLE_KEY)
    if key:
        found.append(key)
    db_url = value(constants.ENV_PSSE_DB_URL)
    if db_url:
        found.append(db_url)
        try:
            password = urllib.parse.urlsplit(db_url).password
        except ValueError:
            password = None
        if password:
            found.extend([password, urllib.parse.unquote(password)])
        found.extend(connection_identifiers(db_url))
    return found


def redact(text, secrets=None, limit=constants.LOG_MAX_CHARS):
    """
    `text` with every secret removed, cut to `limit` characters AFTER redaction (so a
    longer limit never lets a secret through). In order: every non-empty string in
    `secrets` (default: env_secrets()), longest first, becomes REDACTED; postgres(ql)://
    URLs become postgresql://REDACTED; password/token/api_key/apikey/key/secret=value
    becomes name=REDACTED; Supabase key tokens become sb_REDACTED; JWT-shaped tokens become
    JWT_REDACTED; a parenthesized IPv4 or IPv6 address becomes (REDACTED). None gives "".
    """
    text = "" if text is None else str(text)
    if secrets is None:
        secrets = env_secrets()
    for secret in sorted(set(s for s in secrets if s), key=len, reverse=True):
        text = text.replace(secret, "REDACTED")
    text = _URL_RE.sub("postgresql://REDACTED", text)
    text = _KEY_VALUE_RE.sub(lambda m: m.group(1) + "=REDACTED", text)
    text = _SB_TOKEN_RE.sub("sb_REDACTED", text)
    text = _JWT_RE.sub("JWT_REDACTED", text)
    text = _RESOLVED_ADDRESS_RE.sub("(REDACTED)", text)
    return text[:limit]
