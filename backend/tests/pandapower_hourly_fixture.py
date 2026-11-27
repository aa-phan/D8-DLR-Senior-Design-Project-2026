"""
Shared helper for the hourly-runner tests (pandapower-solver Phase 5, plan 05-01). Not collected by
pytest (the file name does not match `*_test.py`, and nothing here has a `test_` prefix).

Synthetic data only: every file is generated from the public 39-bus fixture into the test's own
`tmp_path`, and nothing here reads `data/private`. The four secrets of the runner are produced as
the single-line base64 text the workflow would hand over in the environment, so a test exercises
the runner exactly as the workflow does.
"""

import base64
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
for _folder in (_BACKEND, _HERE):
    if _folder not in sys.path:
        sys.path.insert(0, _folder)

import pandapower  # noqa: E402
import pandapower_replay_fixture as replay_fixture  # noqa: E402
import pandapower_study_fixture as study_fixture  # noqa: E402
import psse_fakes  # noqa: E402
from pandapower_job import cli, engine, hourly  # noqa: E402

FIXED_NOW = study_fixture.NOW


def _write_json(path, document):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle)
    return path


def secret_files(tmp_path, island=False):
    """Write the four private inputs into `tmp_path` and return a dict from the secret's word
    (network, mapping, settings, scaling) to its path: the converted fixture network, the
    non-placeholder mapping, the recorded settings document and the scaling document, both with
    the report marker key (built from `cli.REPORT_MARKER`, never a literal)."""
    values = study_fixture.fixture_backend().solve_settings
    details = study_fixture.fixture_backend().scaling_details
    settings_path = os.path.join(str(tmp_path), "settings_document.json")
    scaling_path = os.path.join(str(tmp_path), "scaling_document.json")
    _write_json(settings_path, {
        "settings": {
            "enforce_q_lims": values.enforce_q_lims, "tolerance_mva": values.tolerance_mva,
            "max_iteration": values.max_iteration,
            "collapse_voltage_pu": values.collapse_voltage_pu,
            "sources": dict(values.sources), "deviations": list(values.deviations)},
        cli.REPORT_MARKER: 1})
    _write_json(scaling_path, {
        "swing_in_total": details.swing_in_total, "clamped_at_limits": details.clamped_at_limits,
        "q_scales_with_p": details.q_scales_with_p, cli.REPORT_MARKER: 1})
    return {
        "network": study_fixture.write_converted(tmp_path),
        "mapping": replay_fixture.write_mapping(tmp_path, island=island),
        "settings": settings_path,
        "scaling": scaling_path}


def _single_line_base64(path):
    with open(path, "rb") as handle:
        return base64.b64encode(handle.read()).decode("ascii")


def read_env():
    """The non-secret part of a runner environment: synthetic Supabase read settings and a job
    version."""
    return {
        "SUPABASE_URL": "https://hourly-example-project.supabase.example",
        "SUPABASE_PUBLISHABLE_KEY": psse_fakes.fake_publishable_key(),
        "PSSE_JOB_VERSION": "test-version"}


def hourly_env(tmp_path, live=False, island=False, **extra):
    """The environment of one runner call: each secret of `hourly.SECRET_ENV` as the single-line
    base64 text of its file, synthetic Supabase read settings, a job version and PANDAPOWER_LIVE
    set to `true` only when `live`. `extra` replaces or adds names."""
    files = secret_files(tmp_path, island=island)
    environ = dict((name, _single_line_base64(files[word]))
                   for word, name, _file, _cap in hourly.SECRET_ENV)
    environ.update(read_env())
    if live:
        environ[hourly.LIVE_VARIABLE] = "true"
    environ.update(extra)
    return environ


def fake_fetch_for(now):
    """A ratings read of four current, non-provisional rows (every city gets its city rating)."""
    return psse_fakes.fake_fetch(psse_fakes.latest_rows(now, provisional=False))


def fake_pandapower_study(selection, context):
    """A study that takes no time: valid results of the public synthetic rows, tagged pandapower."""
    results = psse_fakes.fake_results(selection)
    return results._replace(solver=engine.SOLVER, solver_version=pandapower.__version__,
                            psse_version=None)


def fast_prepare(backend, case_path, mapping_path, allow_placeholder=False, clock=None):
    """The real `engine.prepare_run` (real hashes, real mapping load) with its study replaced by
    `fake_pandapower_study`, so a test that is not about the solver takes milliseconds."""
    prepared = engine.prepare_run(backend, case_path, mapping_path, allow_placeholder, clock)
    return prepared._replace(study=fake_pandapower_study)


# -- the owner's private tree (plan 05-05) ----------------------------------------------------------

# Fake values the owner-command and leak tests plant, each assembled from pieces and on the
# reserved `.invalid` top-level domain so none is credential-shaped. The first four sit in the check
# folder's report and scaling files only, where the bundle must leave them; the rest stand for the
# runner's connection settings.
PLANTED = {
    "session_case_sha256": "5a" * 32,
    "session_mapping_sha256": "6b" * 32,
    "net03_text": "net03" + "verdict" + "zq4417",
    "parity_value": 4417.8832911,
    "evidence_text": "evidence" + "zq4417",
    "db_user": "writer" + "usr" + "zq4417",
    "db_password": "pw" + "zq4417" + "@" + "x9",
    "db_host": "db-" + "zq4417" + ".invalid",
    "project_ref": "projref" + "zq4417",
}


def planted_writer_url():
    """A writer URL of the planted user, percent-encoded password and host."""
    from urllib.parse import quote
    return "postgresql://%s:%s@%s:5432/postgres" % (
        PLANTED["db_user"], quote(PLANTED["db_password"], safe=""), PLANTED["db_host"])


def planted_supabase_url():
    return "https://" + PLANTED["project_ref"] + ".supabase.invalid"


def private_tree(repo, study=None, island=False):
    """Write into the throwaway repository `repo` the private files the owner commands read, in the
    shape the real tree has: the non-placeholder mapping at `data/private/pandapower/mapping.json`
    and one check folder `sessions/session_one/check_20261120T000000Z/` holding the converted
    network, `report.json` (the six settings keys, a `session` object with two hashes, `net03` and
    `parity` objects and the marker) and `scaling_details.json` (the three details, an `evidence`
    object and the marker), each planted value from PLANTED. `study` replaces the mapping's study
    section. Returns a `replay_fixture.Layout`."""
    root = os.path.join(str(repo), "data", "private", "pandapower")
    check_dir = os.path.join(root, "sessions", "session_one", "check_20261120T000000Z")
    os.makedirs(check_dir, exist_ok=True)
    if study is None:
        mapping = replay_fixture.write_mapping(root, island=island)
    else:
        mapping = study_fixture.write_placeholder_mapping(root, study=study)
        with open(mapping, "r", encoding="utf-8") as handle:
            document = json.load(handle)
        document["placeholder"] = False
        _write_json(mapping, document)
    network = study_fixture.write_converted(check_dir, name="converted_network.json")
    values = study_fixture.fixture_backend().solve_settings
    details = study_fixture.fixture_backend().scaling_details
    report = _write_json(os.path.join(check_dir, "report.json"), {
        "settings": {
            "enforce_q_lims": values.enforce_q_lims, "tolerance_mva": values.tolerance_mva,
            "max_iteration": values.max_iteration,
            "collapse_voltage_pu": values.collapse_voltage_pu,
            "sources": dict(values.sources), "deviations": list(values.deviations)},
        "session": {"case_sha256": PLANTED["session_case_sha256"],
                    "mapping_sha256": PLANTED["session_mapping_sha256"]},
        "net03": {"verdict": PLANTED["net03_text"]},
        "parity": {"largest_difference": PLANTED["parity_value"]},
        cli.REPORT_MARKER: 1})
    scaling = _write_json(os.path.join(check_dir, "scaling_details.json"), {
        "swing_in_total": details.swing_in_total, "clamped_at_limits": details.clamped_at_limits,
        "q_scales_with_p": details.q_scales_with_p,
        "evidence": {"note": PLANTED["evidence_text"]}, cli.REPORT_MARKER: 1})
    return replay_fixture.Layout(str(repo), mapping, check_dir, network, report, scaling)
