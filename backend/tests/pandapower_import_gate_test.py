"""
The one-way import boundary (pandapower-solver Phase 2, plan 02-01, D-01, threat T-02-01):
`pandapower_job` may import `psse_job`, never the reverse. `backend/psse_job/` is the standard
library only, Python 3.7 job that runs on the licensed laptop, so it must neither name nor load
the second solver. The solver is reached through study.API_FACTORIES, which the solver package
fills when it is imported.

Three kinds of check, because each catches what the others miss: a text scan (comments and
docstrings included), an AST walk of every import (inside functions and handlers too) and a
fresh `python -I` interpreter that imports study and reports what it registered and loaded.
This file imports no solver package and skips nothing.

Follows backend/tests/psse_contract_test.py's conventions (module-level imports, plain asserts,
no test classes, no network). Failure messages list file names and counts only.
"""

import ast
import glob
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
_PACKAGE_DIR = os.path.join(_BACKEND, "psse_job")

_SOLVER_WORD = "pandapower"
_SOLVER_MODULES = ("pandapower", "pandapower_job")


def _module_paths():
    return sorted(glob.glob(os.path.join(_PACKAGE_DIR, "*.py")))


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _text_problems(source, filename):
    """One problem per line naming the solver in any letter case (code, comment or docstring)."""
    lowered = source.lower()
    count = lowered.count(_SOLVER_WORD)
    return ["%s names the second solver %d time(s)" % (filename, count)] if count else []


def _collect_imports(body, found):
    """(top-level module name, line) for every import under `body`, in functions and handlers too."""
    for node in body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name.split(".")[0], node.lineno))
        elif isinstance(node, ast.ImportFrom):
            found.append(((node.module or "").split(".")[0], node.lineno))
        else:
            for field in ("body", "orelse", "finalbody"):
                inner = getattr(node, field, None)
                if isinstance(inner, list):
                    _collect_imports(inner, found)
            for handler in getattr(node, "handlers", []):
                _collect_imports(handler.body, found)
    return found


def _import_problems(source, filename):
    found = _collect_imports(ast.parse(source, filename).body, [])
    return ["%s:%d imports %s (the boundary is one way)" % (filename, line, name)
            for name, line in found if name in _SOLVER_MODULES]


def test_psse_job_source_never_names_the_other_solver():
    paths = _module_paths()
    assert len(paths) >= 5
    problems = []
    for path in paths:
        problems += _text_problems(_read(path), os.path.basename(path))
    assert problems == []


def test_psse_job_imports_no_solver_package():
    problems = []
    for path in _module_paths():
        problems += _import_problems(_read(path), os.path.basename(path))
    assert problems == []


def test_gates_flag_planted_violations():
    assert len(_text_problems("# PandaPower is faster\nx = 1\n", "planted.py")) == 1
    assert len(_text_problems("'''uses PANDAPOWER_job'''\n", "planted.py")) == 1
    assert _text_problems("import json\n", "planted.py") == []
    for text in (
        "def f():\n    import pandapower_job.api\n",
        "from pandapower import runpp\n",
        "import pandapower as pp\n",
        "try:\n    import pandapower_job\nexcept ImportError:\n    pass\n",
        "try:\n    pass\nexcept ImportError:\n    from pandapower_job import api\n",
    ):
        assert len(_import_problems(text, "planted.py")) == 1, text
    assert _import_problems("import json\n", "planted.py") == []
    assert _import_problems("from psse_job import study\n", "planted.py") == []


def test_importing_study_registers_only_psse():
    code = (
        "import json, sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from psse_job import study\n"
        "loaded = sorted(n for n in sys.modules if n.split('.')[0] in json.loads(sys.argv[2]))\n"
        "print(json.dumps([sorted(study.API_FACTORIES), loaded]))\n"
    )
    done = subprocess.run(
        [sys.executable, "-I", "-c", code, _BACKEND, json.dumps(list(_SOLVER_MODULES))],
        cwd=_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert done.returncode == 0, done.stderr[-500:]
    registered, loaded = json.loads(done.stdout.strip().splitlines()[-1])
    assert registered == ["psse"]
    assert loaded == []
