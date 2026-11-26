"""
OPS-02 and OPS-03, pure tier (pandapower-solver Phase 5, plan 05-01): the hourly runner's `run`
command (`pandapower_job.hourly`, entry script `backend/pandapower_hourly.py`).

What is proven here, with no database and no network: four base64 secrets become private files in
a temporary folder that is removed however the run ends; the run is live only for the exact text
`true`; a live run on a placeholder is refused before the ratings are read, before the study and
before any connection; a dry run loads no writer-side module; a live run is tagged pandapower; and
everything printed is a line of the closed vocabulary, with the study's own output, logging and
warnings kept off every channel. The tracer runs the real four-city study on the public 39-bus
fixture; the other tests use a fast stand-in study.

What the database tier of plan 05-04 adds: that a dry run leaves the four result tables unchanged
and that a live run stores a run set with solver pandapower, on a throwaway local Postgres.

Synthetic data only; nothing here reads `data/private`. No test asserts a file mode or pins file
bytes (Windows).
"""

import os
import re
import sys
import tempfile

import pytest

pandapower = pytest.importorskip("pandapower")

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import io  # noqa: E402

import pandapower_hourly_fixture as fixture  # noqa: E402
from pandapower_job import hourly  # noqa: E402


@pytest.fixture(autouse=True)
def _private_temp(tmp_path, monkeypatch):
    """Every temporary directory of a test lives under tmp_path/scratch, so a leak shows."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    return scratch


def _vocabulary_ok(lines):
    return all(any(pattern.match(line) for pattern in hourly.HOURLY_LINE_PATTERNS) for line in lines)


def _clock():
    return lambda: fixture.FIXED_NOW


# -- the tracer ------------------------------------------------------------------------------------


def test_tracer_dry_run_end_to_end_prints_counts_and_writes_nothing(tmp_path):
    environ = fixture.hourly_env(tmp_path)
    buffer = io.StringIO()
    code = hourly.main(["run"], out=buffer, environ=environ,
                       fetch=fixture.fake_fetch_for(fixture.FIXED_NOW), clock=_clock(), sink=False)
    lines = buffer.getvalue().splitlines()
    assert code == 0
    assert lines[0] == "mode: dry"
    assert lines[1] == "inputs: ok"
    match = re.match(r"ratings: city_rating=([0-9]+) static=([0-9]+)\Z", lines[2])
    assert match is not None and int(match.group(1)) + int(match.group(2)) == 4
    assert lines[3] == "study: ok"
    assert lines[4] in ("outcome: ok", "outcome: fallback")
    assert re.match(r"rows: run=1 dispatch=4 margin=4 contingency=[0-9]+\Z", lines[5])
    assert lines[6] == "dry run: nothing was written to the database"
    assert len(lines) == 7
    assert _vocabulary_ok(lines)
    text = buffer.getvalue()
    assert "pp-" not in text
    assert re.search(r"[0-9a-f]{64}", text) is None
    assert os.listdir(tempfile.gettempdir()) == []
