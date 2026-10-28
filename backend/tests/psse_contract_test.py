"""
The PSS/E job stays runnable on the licensed laptop (pss-e-integration Phase 1, plan 01-02, D-05, D-06).

`backend/psse_job/` keeps its own copy of the few config constants it needs, because
backend/config.py annotates module-level dicts with `dict[str, float]` (breaks Python 3.7/3.8)
and uses `str | None` (needs 3.10). These tests pin the copies to config (this file runs on
the repository's newer Python), prove every psse_job module parses as Python 3.7 syntax and
imports nothing outside the standard library, and keep the per-conductor MW column name out
of job code. They glob `backend/psse_job/*.py` at run time, so modules added by later plans
are covered automatically.

Follows backend/tests/supabase_schema_doc_test.py's conventions (module-level imports, plain
asserts, no test classes, no network).
"""

import ast
import glob
import importlib
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import config  # noqa: E402
from psse_job import constants  # noqa: E402

_PACKAGE_DIR = os.path.join(_BACKEND, "psse_job")

# tempfile: pss-e-integration plan 02-03; study.py saves the solved base case to a private per-run temporary directory and never over Power Systems' case file
# inspect: pss-e-integration plan 02-07; probe.py compares the real psspy's signatures with psse_api.SURFACE on the laptop
_STDLIB_ALLOWED = frozenset([
    "__future__", "base64", "binascii", "collections", "contextlib", "datetime", "functools",
    "hashlib", "http", "inspect", "json", "logging", "math", "numbers", "os", "re", "socket", "subprocess",
    "sys", "tempfile", "time", "typing", "urllib", "uuid",
])
_NEVER_IMPORTED = frozenset(["config", "supabase_store", "pandas", "numpy", "requests", "psspy"])
_HEAVY_MODULES = ("pandas", "numpy", "config", "supabase_store", "requests", "psycopg")
_GENERIC_NAMES = frozenset(["list", "dict", "tuple", "set", "frozenset", "type"])
_NEW_METHODS = frozenset(["removeprefix", "removesuffix", "fromisoformat"])
_NEW_MODULES = frozenset(["zoneinfo", "graphlib", "tomllib"])

# Copied from the Phase 6 latest_rating contract (production-pipeline 06-01-PLAN.md, planned).
PHASE6_PLANNED_LATEST_COLUMNS = (
    "city", "valid_time", "observation_time", "rating_amps", "rating_mw", "static_rating_amps",
    "static_rating_mw", "line_voltage_kv", "power_factor", "status", "fallback", "fallback_gates",
    "alerts", "exhausted", "forecast_method", "forecast_status", "forecast_amps",
    "forecast_ci_lower_amps", "forecast_ci_upper_amps", "forecast_horizon_min", "detector_signal",
    "rating_basis", "config_version", "origin", "run_id", "pipeline_version", "computed_at",
    "config_fingerprint", "forecast_model_sha256", "anomaly_model_sha256", "solar_source",
    "age_minutes", "is_stale", "is_provisional",
)


def _module_paths():
    return sorted(glob.glob(os.path.join(_PACKAGE_DIR, "*.py")))


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _rel(path):
    return os.path.relpath(path, _ROOT).replace(os.sep, "/")


# ──────────────────────────────────────────────────────────────────────────────
# Gates, written over (source, filename) so a planted violation proves each one fires
# ──────────────────────────────────────────────────────────────────────────────

def _generic_annotation_problems(source, filename):
    tree = ast.parse(source, filename)
    annotations = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            arguments = node.args
            every = list(getattr(arguments, "posonlyargs", [])) + list(arguments.args) + list(arguments.kwonlyargs)
            every += [a for a in (arguments.vararg, arguments.kwarg) if a is not None]
            annotations += [a.annotation for a in every if a.annotation is not None]
            if node.returns is not None:
                annotations.append(node.returns)
        elif isinstance(node, ast.AnnAssign):
            annotations.append(node.annotation)
    problems = []
    for annotation in annotations:
        for node in ast.walk(annotation):
            if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                    and node.value.id in _GENERIC_NAMES):
                problems.append("%s:%d builtin-generic annotation %s[...]" % (filename, node.lineno, node.value.id))
            elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
                problems.append("%s:%d X | Y annotation" % (filename, node.lineno))
    return problems


def _new_feature_problems(source, filename):
    tree = ast.parse(source, filename)
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if node.attr in _NEW_METHODS:
                problems.append("%s:%d .%s needs a newer Python" % (filename, node.lineno, node.attr))
            if node.attr == "cache" and isinstance(node.value, ast.Name) and node.value.id == "functools":
                problems.append("%s:%d functools.cache needs Python 3.9" % (filename, node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in _NEW_MODULES:
                    problems.append("%s:%d import %s needs a newer Python" % (filename, node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and (node.module or "").split(".")[0] in _NEW_MODULES:
                problems.append("%s:%d import from %s needs a newer Python" % (filename, node.lineno, node.module))
            if node.module == "functools" and any(alias.name == "cache" for alias in node.names):
                problems.append("%s:%d functools.cache needs Python 3.9" % (filename, node.lineno))
        elif isinstance(node, ast.Call):
            target = node.func
            name = target.id if isinstance(target, ast.Name) else getattr(target, "attr", None)
            if name == "dataclass" and any(k.arg in ("slots", "kw_only") for k in node.keywords):
                problems.append("%s:%d dataclass slots/kw_only needs Python 3.10" % (filename, node.lineno))
        elif isinstance(node, ast.NamedExpr):
            problems.append("%s:%d assignment expression needs Python 3.8" % (filename, node.lineno))
    return problems


def _collect_imports(body, in_function, found):
    """(top-level module name, relative?, in_function, line) for every import under `body`."""
    for node in body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name.split(".")[0], False, in_function, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            found.append(((node.module or "").split(".")[0], node.level > 0, in_function, node.lineno))
        else:
            nested_function = in_function or isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            for field in ("body", "orelse", "finalbody"):
                inner = getattr(node, field, None)
                if isinstance(inner, list):
                    _collect_imports(inner, nested_function, found)
            for handler in getattr(node, "handlers", []):
                _collect_imports(handler.body, nested_function, found)
    return found


def _import_problems(source, filename):
    found = _collect_imports(ast.parse(source, filename).body, False, [])
    problems = []
    for name, relative, in_function, line in found:
        if relative or name == "psse_job":
            continue
        if name in _NEVER_IMPORTED:
            problems.append("%s:%d imports %s (never allowed in psse_job)" % (filename, line, name))
        elif name == "psycopg":
            if not in_function:
                problems.append("%s:%d imports psycopg at module level (lazy import only)" % (filename, line))
        elif name not in _STDLIB_ALLOWED:
            problems.append("%s:%d imports %s, outside the laptop allow-list" % (filename, line, name))
    return problems


def _mw_name_problems(source, filename):
    problems = []
    for node in ast.walk(ast.parse(source, filename)):
        if isinstance(node, ast.Constant) and node.value in ("rating_mw", "static_rating_mw"):
            problems.append("%s:%d names the per-conductor MW column" % (filename, node.lineno))
    return problems


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_constants_match_config():
    assert constants.STATIC_RATINGS_AMPS_PER_CONDUCTOR == config.STATIC_RATINGS, (
        "re-copy backend/config.py STATIC_RATINGS into psse_job/constants.py")
    assert constants.SUBCONDUCTORS_PER_PHASE == config.SUBCONDUCTORS_PER_PHASE, (
        "re-copy backend/config.py SUBCONDUCTORS_PER_PHASE into psse_job/constants.py")
    assert constants.LINE_VOLTAGE_KV_DEFAULT == config.LINE_VOLTAGE_KV, (
        "re-copy backend/config.py LINE_VOLTAGE_KV into psse_job/constants.py")
    assert constants.CITIES == tuple(config.LOCATIONS), (
        "re-copy backend/config.py LOCATIONS (order included) into psse_job/constants.py")
    assert constants.STALE_AFTER_MINUTES == 90


def test_syntax_parses_as_python37():
    paths = _module_paths()
    assert len(paths) >= 5, "expected at least 5 psse_job modules, found %d" % len(paths)
    for path in paths:
        try:
            ast.parse(_read(path), _rel(path), feature_version=(3, 7))
        except SyntaxError as exc:
            raise AssertionError(
                "%s does not parse as Python 3.7 syntax (PSS/E's interpreter may be 3.7): %s" % (_rel(path), exc))


def test_syntax_no_runtime_generic_annotations():
    problems = []
    for path in _module_paths():
        problems += _generic_annotation_problems(_read(path), _rel(path))
    assert problems == []


def test_syntax_no_39_only_calls_or_modules():
    problems = []
    for path in _module_paths():
        problems += _new_feature_problems(_read(path), _rel(path))
    assert problems == []


def test_syntax_gates_flag_planted_violations():
    annotated = "def f(x: list[int], y: 'a' = None) -> dict[str, int]:\n    z: tuple[int, ...] = ()\n    return z\n"
    assert len(_generic_annotation_problems(annotated, "planted.py")) == 3
    assert len(_generic_annotation_problems("def f(x: int | None):\n    pass\n", "planted.py")) == 1
    assert _generic_annotation_problems("import typing\ndef f(x: typing.List[int]):\n    pass\n", "planted.py") == []

    planted = (
        "import functools, zoneinfo\n"
        "from graphlib import TopologicalSorter\n"
        "from functools import cache\n"
        "import dataclasses\n"
        "@dataclasses.dataclass(slots=True)\n"
        "class A:\n    pass\n"
        "name.removeprefix('x'); name.removesuffix('y')\n"
        "import datetime\n"
        "datetime.datetime.fromisoformat('2026-01-01')\n"
        "@functools.cache\n"
        "def g():\n    return (n := 1)\n"
    )
    kinds = " ".join(_new_feature_problems(planted, "planted.py"))
    for needle in ("removeprefix", "removesuffix", "fromisoformat", "zoneinfo", "graphlib",
                   "functools.cache", "slots/kw_only", "assignment expression"):
        assert needle in kinds, needle
    assert _new_feature_problems("import json\njson.loads('1')\n", "planted.py") == []

    walrus = "def g():\n    return (n := 1)\n"
    try:
        ast.parse(walrus, "planted.py", feature_version=(3, 7))
    except SyntaxError:
        pass
    else:
        raise AssertionError("the 3.7 parse gate no longer rejects an assignment expression")


def test_imports_stay_inside_the_laptop_boundary():
    problems = []
    for path in _module_paths():
        problems += _import_problems(_read(path), _rel(path))
    assert problems == []


def test_import_gate_flags_planted_violations():
    for text, expected in (
        ("import pandas\n", "pandas"),
        ("import numpy as np\n", "numpy"),
        ("from config import STATIC_RATINGS\n", "config"),
        ("import supabase_store\n", "supabase_store"),
        ("import requests\n", "requests"),
        ("def f():\n    import psspy\n", "psspy"),
        ("import psycopg\n", "psycopg"),
        ("import sqlite3\n", "sqlite3"),
        ("try:\n    import pandas\nexcept ImportError:\n    pass\n", "pandas"),
        ("if True:\n    import requests\n", "requests"),
    ):
        problems = _import_problems(text, "planted.py")
        assert len(problems) == 1 and expected in problems[0], (text, problems)
    allowed = (
        "from __future__ import annotations\nimport json, os\nfrom psse_job import constants\n"
        "from . import units\nfrom psse_job.ratings import choose\nimport urllib.request\n"
        "def write():\n    import psycopg\n    return psycopg\n"
    )
    assert _import_problems(allowed, "planted.py") == []


def test_importing_psse_job_loads_no_heavy_module():
    names = ["psse_job"] + ["psse_job." + os.path.splitext(os.path.basename(p))[0]
                            for p in _module_paths() if os.path.basename(p) != "__init__.py"]
    code = (
        "import importlib, json, sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "for name in json.loads(sys.argv[2]):\n"
        "    importlib.import_module(name)\n"
        "print(json.dumps(sorted(n for n in json.loads(sys.argv[3]) if n in sys.modules)))\n"
    )
    done = subprocess.run(
        [sys.executable, "-I", "-c", code, _BACKEND, json.dumps(names), json.dumps(list(_HEAVY_MODULES))],
        cwd=_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert done.returncode == 0, done.stderr[-500:]
    assert json.loads(done.stdout.strip().splitlines()[-1]) == []
    assert len(names) >= 5


def test_no_bare_mw_column_name_in_job_code():
    problems = []
    for path in _module_paths():
        problems += _mw_name_problems(_read(path), _rel(path))
    assert problems == []
    # The gate sees an exact string constant, not a comment or a longer docstring.
    assert len(_mw_name_problems("x = 'rating_mw'\n", "planted.py")) == 1
    assert len(_mw_name_problems("x = 'static_rating_mw'\n", "planted.py")) == 1
    assert _mw_name_problems("# rating_mw\ndef f():\n    '''reads rating_mw never'''\n", "planted.py") == []


def test_latest_rating_select_is_inside_phase6_contract():
    contract_path = os.path.join(_BACKEND, "latest_rating_contract.py")
    if os.path.exists(contract_path):
        published = tuple(importlib.import_module("latest_rating_contract").LATEST_COLUMNS)
    else:
        published = PHASE6_PLANNED_LATEST_COLUMNS
        assert len(published) == 34
    missing = [name for name in constants.LATEST_RATING_SELECT if name not in published]
    assert missing == [], "selected columns Phase 6 does not publish: %s" % missing
    assert len(set(constants.LATEST_RATING_SELECT)) == len(constants.LATEST_RATING_SELECT)
