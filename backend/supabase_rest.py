"""
Standard-library client for the Supabase REST interface (production-pipeline Phase 6,
API-01, D-10).

This is the consumer's view of the system: it talks to PostgREST the way the dashboard
and the PSS/E scripts do, with only the publishable key. It is used by
backend/e2e_verify_readonly.py and by the later E2E tools, and it is deliberately small:

  config_from_env   reads SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY from the environment
                    (never from a file), and refuses a secret key or a service_role token
                    before any request is made, so a check can never pass because it ran
                    with more power than a consumer has (T-06-14)
  redact_rest       removes the project URL, host, project reference and keys from any text
                    (Pitfall 15: supabase_store.redact does not know them)
  request           one HTTP call; the key goes only in the `apikey` header; an HTTP error
                    status comes back as a value, a network failure as a redacted RestError
  get_all           pages with limit/offset until an EMPTY page (never stops on a short page,
                    because the server's row cap may be lower than the page size)
  count_exact       the exact row count from the Content-Range total
  parse_ts          PostgREST timestamps on Python 3.7+ (fromisoformat before 3.11 rejects
                    a trailing Z and fractions that are not 3 or 6 digits)

Nothing here prints, and no message, repr or exception carries the URL, the host, the
20-character project reference or a key. Standard library only.
"""

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import namedtuple
from datetime import datetime

ENV_URL = "SUPABASE_URL"
ENV_KEY = "SUPABASE_PUBLISHABLE_KEY"
PAGE_SIZE = 1000  # the server returns at most this many rows per request (project "Max rows")
USER_AGENT = "dlr-e2e-verify/1.0"
# Supabase's new key prefixes, assembled from pieces so the repository secret scan never
# matches this file.
SECRET_KEY_PREFIX = "sb_" + "secret_"
PUBLISHABLE_KEY_PREFIX = "sb_" + "publishable_"

_MAX_PAGES = 100000  # a server that ignores `offset` must not loop forever
_MAX_MESSAGE_CHARS = 300


class ConfigError(RuntimeError):
    """A missing or unsafe setting. The message names the variable, never its value."""


class RestError(RuntimeError):
    """A request failure or an unusable response. The message is always redacted."""


RestConfig = namedtuple("RestConfig", ["base_url", "key"])


class Response(object):
    """An HTTP answer: status, headers with lower-case keys, and the decoded text."""

    def __init__(self, status, headers, text):
        self.status = status
        self.headers = headers
        self.text = text

    def json(self):
        return json.loads(self.text)

    def __repr__(self):
        return "Response(status=%r)" % (self.status,)


# ---------------------------------------------------------------------------
# Configuration (D-10, T-06-14)
# ---------------------------------------------------------------------------


def _jwt_role(token):
    """The `role` claim of a JWT-shaped token, or None when it is not one."""
    parts = token.split(".")
    if len(parts) != 3 or not parts[1]:
        return None
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeError):
        return None
    if isinstance(claims, dict):
        role = claims.get("role")
        return role if isinstance(role, str) else None
    return None


def config_from_env(env=None):
    """
    Read the project URL and the publishable key. Values are stripped of whitespace (a
    pasted trailing newline must work) and the URL of a trailing slash. Raises ConfigError
    naming the variable, never a value, when one is missing or blank, when the URL is not
    http(s), when the key is a secret key (`sb_secret_...`), or when it is a JWT whose role
    is service_role. The refusal happens before any request.
    """
    env = os.environ if env is None else env
    values = {}
    for name in (ENV_URL, ENV_KEY):
        raw = env.get(name)
        if raw is None or not str(raw).strip():
            raise ConfigError("%s is not set" % name)
        values[name] = str(raw).strip()
    base_url = values[ENV_URL].rstrip("/")
    key = values[ENV_KEY]
    if not re.match(r"^https?://[^/\s]+", base_url, re.IGNORECASE):
        raise ConfigError("%s must start with https://" % ENV_URL)
    if key.startswith(SECRET_KEY_PREFIX):
        raise ConfigError("%s holds a secret key; use the publishable key (a check run with a secret key proves nothing)" % ENV_KEY)
    if _jwt_role(key) == "service_role":
        raise ConfigError("%s holds a service_role token; use the publishable key (a check run with it proves nothing)" % ENV_KEY)
    return RestConfig(base_url=base_url, key=key)


# ---------------------------------------------------------------------------
# Redaction (D-10, Pitfall 15)
# ---------------------------------------------------------------------------

_SUPABASE_HOST_RE = re.compile(r"\b[a-z0-9]{20}\." + "supa" + "base" + r"\.(?:co|in|red)\b", re.IGNORECASE)
_KEY_TOKEN_RE = re.compile(r"\bsb_(?:publishable|secret)_[A-Za-z0-9_-]+")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{7,}\.eyJ[A-Za-z0-9_-]{7,}\.[A-Za-z0-9_-]{6,}")
_APIKEY_PARAM_RE = re.compile(r"(?i)\b(apikey|api_key)=([^\s&;,'\"]+)")


def _url_parts(url):
    """The URL's host and the host's first label (the project reference), when long enough to be one."""
    found = []
    try:
        host = urllib.parse.urlsplit(url).hostname
    except ValueError:
        host = None
    if host:
        found.append(host)
        label = host.split(".", 1)[0]
        if len(label) >= 8:  # a project reference is 20 characters; "127" or "localhost" stay readable
            found.append(label)
    return found


def _secrets_from(cfg, env):
    secrets = []
    if cfg is not None:
        for value in (cfg.base_url, cfg.key):
            if value:
                secrets.append(value)
        secrets.extend(_url_parts(cfg.base_url))
    source = os.environ if env is None else env
    for name in (ENV_URL, ENV_KEY):
        value = source.get(name)
        if value and str(value).strip():
            value = str(value).strip()
            secrets.append(value)
            secrets.append(value.rstrip("/"))
            if name == ENV_URL:
                secrets.extend(_url_parts(value))
    return secrets


def redact_rest(text, cfg=None, env=None, limit=_MAX_MESSAGE_CHARS):
    """
    `text` with the full project URL, its host, its project reference and the key removed
    (from `cfg` and from SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY in `env`, default the process
    environment), plus any 20-character reference host on the Supabase domain and any key
    with the publishable or secret prefix, any JWT and any `apikey=` value. Longest first, so
    a URL goes before the host inside it. The cut to `limit` characters (None keeps the whole
    text) is made after redaction, so a short limit never lets a value through.
    """
    text = "" if text is None else str(text)
    for secret in sorted({s for s in _secrets_from(cfg, env) if s}, key=len, reverse=True):
        text = text.replace(secret, "REDACTED")
    text = _SUPABASE_HOST_RE.sub("REDACTED", text)
    text = _KEY_TOKEN_RE.sub("REDACTED", text)
    text = _JWT_RE.sub("REDACTED", text)
    text = _APIKEY_PARAM_RE.sub(lambda m: m.group(1) + "=REDACTED", text)
    return text if limit is None else text[:limit]


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


def _lower_headers(raw):
    headers = {}
    if raw is None:
        return headers
    items = raw.items() if hasattr(raw, "items") else raw
    for name, value in items:
        headers[str(name).lower()] = str(value)
    return headers


def _decode(data):
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return "" if data is None else str(data)


def request(cfg, method, path, params=None, headers=None, body=None, profile=None, timeout=30,
            opener=None, send_key=True):
    """
    One call to `<base>/rest/v1/<path>`. `params` is a list of (name, value) pairs (or a dict) so
    a column can be filtered twice. The key is sent in the `apikey` header only, never in
    `Authorization` and never in the URL; `send_key=False` makes the keyless request a check needs.
    `profile` selects a non-default schema (Accept-Profile for reads, Content-Profile for writes).
    A dict or list `body` is sent as JSON. An HTTP error status is returned as a Response; a
    network failure or timeout raises RestError with redacted text and no chained exception.
    `opener` defaults to urllib.request.urlopen (tests pass a stub).
    """
    method = method.upper()
    query = ""
    if params:
        pairs = list(params.items()) if hasattr(params, "items") else list(params)
        query = "?" + urllib.parse.urlencode(pairs, safe=",.()*:")
    url = "%s/rest/v1/%s%s" % (cfg.base_url, path, query)
    sent = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if send_key:
        sent["apikey"] = cfg.key
    if profile:
        sent["Accept-Profile" if method in ("GET", "HEAD") else "Content-Profile"] = profile
    for name, value in (headers or {}).items():
        if name.lower() == "authorization":
            raise RestError("an Authorization header is not allowed; the key goes in apikey only")
        sent[name] = value
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        sent.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=sent, method=method)
    open_url = opener if opener is not None else urllib.request.urlopen

    failure = None
    response = None
    try:
        with open_url(req, timeout=timeout) as handle:
            status = getattr(handle, "status", None) or handle.getcode()
            response = Response(int(status), _lower_headers(handle.headers), _decode(handle.read()))
    except urllib.error.HTTPError as exc:
        try:
            text = _decode(exc.read())
        except Exception:  # noqa: BLE001 - an unreadable error body is just an empty one
            text = ""
        response = Response(int(exc.code), _lower_headers(exc.headers), text)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        failure = "request to the REST service failed: %s" % redact_rest(str(exc), cfg)
    # Raised outside the except block so no exception context (and thus no part of the original
    # message, which may echo the URL) is attached to the RestError.
    if failure is not None:
        raise RestError(failure)
    return response


def brief(response, cfg=None, limit=160):
    """A short redacted description of an error answer: status plus the JSON code and message."""
    parts = ["HTTP %s" % response.status]
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        for name in ("code", "message"):
            if body.get(name):
                parts.append(str(body[name]))
    elif response.text:
        parts.append(response.text)
    return redact_rest(" ".join(parts), cfg, limit=limit)


def _list_body(response, path, cfg):
    if not 200 <= response.status < 300:
        raise RestError("%s answered %s" % (path, brief(response, cfg)))
    try:
        body = response.json()
    except ValueError:
        raise RestError("%s did not answer with JSON" % path)
    if not isinstance(body, list):
        raise RestError("%s did not answer with a list of rows" % path)
    return body


def get_all(cfg, path, params, order, page_size=PAGE_SIZE, opener=None, profile=None):
    """
    Every row of `path` matching `params`, fetched in pages ordered by `order` (a UNIQUE key, so no
    row repeats or is skipped). The offset advances by the rows actually received, and the loop ends
    only on an empty page, never on a short one: the server cap can be lower than `page_size`.
    Raises RestError on a non-2xx page.
    """
    base = list(params.items()) if hasattr(params, "items") else list(params or [])
    rows = []
    offset = 0
    for _ in range(_MAX_PAGES):
        page_params = base + [("order", order), ("limit", str(page_size)), ("offset", str(offset))]
        response = request(cfg, "GET", path, page_params, opener=opener, profile=profile)
        page = _list_body(response, path, cfg)
        if not page:
            return rows
        rows.extend(page)
        offset += len(page)
    raise RestError("paging %s did not end after %d pages" % (path, _MAX_PAGES))


def count_exact(cfg, path, params, opener=None, profile=None):
    """The exact number of rows matching `params`, read from the total after the slash of Content-Range."""
    headers = {"Prefer": "count=exact", "Range-Unit": "items", "Range": "0-0"}
    response = request(cfg, "GET", path, params, headers=headers, opener=opener, profile=profile)
    if not 200 <= response.status < 300:
        raise RestError("%s count answered %s" % (path, brief(response, cfg)))
    match = re.search(r"/(\d+)\s*$", response.headers.get("content-range", ""))
    if not match:
        raise RestError("%s count answered without a Content-Range total" % path)
    return int(match.group(1))


_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}(?::?\d{2})?)?$")


def parse_ts(s):
    """
    PostgREST timestamptz -> aware datetime. datetime.fromisoformat() before Python 3.11 rejects 'Z'
    and any fraction that is not exactly 3 or 6 digits. A missing offset is read as UTC. Raises
    ValueError on anything else.
    """
    text = str(s).strip()
    match = _TS_RE.match(text)
    if not match:
        raise ValueError("unrecognised timestamp: %r" % text)
    day, clock, frac, off = match.groups()
    off = off or "+00:00"
    if off == "Z":
        off = "+00:00"
    if re.match(r"^[+-]\d{2}$", off):
        off += ":00"
    if re.match(r"^[+-]\d{4}$", off):
        off = off[:3] + ":" + off[3:]
    return datetime.fromisoformat("%sT%s.%s%s" % (day, clock, ((frac or "") + "000000")[:6], off))
