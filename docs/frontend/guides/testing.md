<!-- generated-by: gsd-doc-writer -->
# Testing

This guide is for the Software sub-team. It covers two things:

1. How the existing backend `pytest` suite is configured and run. It is the only automated test suite in the repo today.
2. A recommended contract-testing approach for `api/` and `frontend/` against the `pipeline_output_v1` schema and the checked-in sample fixture.

**Status legend:**

- **Built** means it exists in the repo today.
- **PLANNED** means nothing exists yet. `frontend/` and `api/` are structural placeholders with no code, no `package.json`, and no Flask app (see [architecture.md](architecture.md)).
- **Not yet chosen** means the team has not made the decision. No test tooling for `frontend/` or `api/` has been selected, and this guide does not select it.

## Test framework and setup (backend, built)

The backend suite uses `pytest`, pinned in the root `requirements.txt` as `pytest==9.0.3`. Python 3.12 is the version the repo's `.venv` and the GitHub Actions workflow use.

Setup, from the repo root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

No credentials are needed to run the suite. Tests replace network calls with `monkeypatch` stand-ins, and the backend modules can be imported without `SYNOPTIC_TOKEN` set. See [configuration.md](configuration.md) for when a token is needed outside tests.

### How pytest is configured

All configuration is in the root `pytest.ini`:

```ini
[pytest]
pythonpath = backend
testpaths = backend/tests
python_files = test_*.py *_test.py *_TestSuite.py
```

| Setting | Effect |
|---|---|
| `pythonpath = backend` | Puts `backend/` on `sys.path`, so tests use bare imports such as `import config` and `import dlr_pipeline`. This replaces the `PYTHONPATH=backend` prefix used when running backend scripts by hand. |
| `testpaths = backend/tests` | Running `pytest` with no arguments collects only the backend tests. |
| `python_files` | Test files are named `*_test.py` (the convention), `test_*.py`, or `*_TestSuite.py` (one legacy file: `SafetyMonitor_TestSuite.py`). |

Because `testpaths` is fixed to `backend/tests`, a plain `pytest` run will not pick up tests that you add under `api/` or `frontend/`. Pass the path explicitly or add a separate config for those subsystems.

## Running tests

Run these from the repo root with the virtual environment active.

```bash
# Full backend suite
pytest

# One test file
pytest backend/tests/dlr_pipeline_test.py

# One test by name
pytest backend/tests/dlr_pipeline_test.py -k "city"

# Stop at the first failure, with short tracebacks
pytest -x --tb=short
```

Notes on what to expect:

- The suite is large (923 tests were collected before the per-city migration; the count has changed and was not re-measured). A full run takes more than two minutes on a development laptop, so run a single file while iterating.
- **Current result (2026-10-12):** the full suite reports 947 passed, 0 failed (`.venv/bin/python -m pytest -q` from the repo root). Before the per-city migration it reported 900 passed and 23 failed, all in `backend/tests/corridor_discretization_test.py`, which was deleted with the corridor modules (`docs/data-science/decisions/point_scope.md`).
- There is no watch-mode script. The repo has no `pytest-watch` or similar dependency.
- There is no coverage tool in `requirements.txt` and no coverage configuration. **No coverage threshold is configured.**

## Layout and fixtures

Tests live flat in `backend/tests/`, one file per backend module, named `{module}_test.py` (for example `thermal_model_test.py` tests `backend/thermal_model.py`). There is no `conftest.py`, so fixtures and helpers are defined inside the file that uses them.

### Isolation conventions

Most tests avoid network access, the real filesystem layout, and shared state by using built-in pytest fixtures:

- `monkeypatch.setattr(module, "fetch_timeseries", ...)` replaces a network fetch with a function returning synthetic data. `dlr_pipeline_test.py` builds a synthetic observation frame this way, then runs `run_pipeline` end to end with no Synoptic token.
- `monkeypatch.setattr(config, "SOME_DIR", str(tmp_path))` redirects cache, model, and archive directories into a temporary directory. The corridor-era `corridor_discretization_test.py` had an autouse fixture that pointed the historical archive at `tmp_path` so tests never touched `data/historical/`; per-city rating tests are expected to do the same.
- `monkeypatch.setenv(...)` supplies fake API keys.
- `monkeypatch.chdir(tmp_path)` isolates tests that write to the current directory.

### Named fixtures worth knowing

| Fixture | File | Purpose |
|---|---|---|
| `monitor`, `valid_data` | `SafetyMonitor_TestSuite.py` | A `DLRSafetyMonitor` with a quiet logger and a known-good sensor reading. |
| `synthetic_corridor`, `fake_stations`, `probe_stations` | `corridor_discretization_test.py` (corridor era; the file is slated for removal) | Stand-in station tables and a patched corridor for the retired `rate_corridor`. The per-city equivalents are not documented here yet. |
| `dlr_csv` | `ercot_dlr_merger_test.py` | Writes a small station CSV to `tmp_path` for the merger tests. |
| `default_conductor` | `thermal_model_test.py` | The default `ConductorConfig` built from `config.DEFAULT_CONDUCTOR_CONFIG_KWARGS`. |
| `predictions_dir` | `forecast_shadow_healthcheck_test.py` | A temporary shadow predictions directory. |
| `fitted_ml_model`, `fitted_anomaly_model` | `ampacity_forecast_test.py`, `anomaly_detector_test.py` | Small fitted models so tests do not retrain. |

### Golden files

Two regression files sit in `backend/tests/` next to the tests that read them. They pin numeric output from before a refactor:

- `thermal_model_pre_refactor_golden.npz`
- `forecast_training_pre_horizon_param_golden.npz`

Do not regenerate them without talking to the DS team. A golden mismatch usually means behavior changed, not that the file is stale.

## Writing new backend tests

- Name the file `{module}_test.py` and put it in `backend/tests/`.
- Use plain `assert` statements and `@pytest.fixture` for setup.
- Never make a live network call. Patch the fetch function, as in `dlr_pipeline_test.py`.
- Write generated files under `tmp_path`, not `outputs/` or `data/`.

The `backend/` code is owned by the DS team. If you want a backend-side test added (see the contract tests below), raise it with them or open a PR that follows their layout.

## CI integration

The only workflow is `.github/workflows/shadow_collect.yml` (name: "Shadow Collection"). It runs four times daily on a cron schedule (00:00, 06:00, 12:00 and 18:00 UTC) and on manual dispatch. It installs `requirements.txt`, runs the shadow collector and health check, and commits predictions to the `shadow-collection-data` branch. **It does not run `pytest`.**

There is currently no automated test run on pushes or pull requests. Until one is added, run `pytest` locally before opening a PR that touches `backend/`.

## Frontend and API testing (PLANNED, tooling not yet chosen)

Nothing under `frontend/` or `api/` is testable yet. The following decisions are open and should be made when those layers are scaffolded:

| Area | Decision | Status |
|---|---|---|
| `frontend/` unit and component tests | Test runner and component-testing library | **Not yet chosen** |
| `frontend/` end-to-end tests | Browser automation tool, if any | **Not yet chosen** |
| `api/` tests | Test runner and HTTP test client | **Not yet chosen** (Flask is the planned framework, per `api/README.md`) |
| CI for either layer | Whether to add a workflow that runs tests on PRs | **Not yet chosen** |

The `docs/frontend/ROADMAP.md` phase **F8** covers the course-level test plan (weather change to pipeline to dashboard within the refresh window, no unit errors, outputs consistent with the pipeline). That is an acceptance test, separate from the contract tests below.

Whatever tools are picked, the contract-testing approach below does not depend on them. It is a set of facts to assert and a set of inputs to assert them against.

## Recommended contract-testing approach

The Software team's only fixed input from the DS team is the `pipeline_output_v1` contract. The dashboard and API should be tested against it so that a DS change that breaks the shape fails a test instead of breaking the UI.

### The two sources of truth

| Artifact | Path | What it is |
|---|---|---|
| Schema document | [`docs/data-science/schema/pipeline_output_v1.md`](../../data-science/schema/pipeline_output_v1.md) | The 11 columns, their order, units, and valid ranges for `outputs/station_data/*.csv`. Any add, remove, reorder, or rename is a breaking change that should bump the doc to `pipeline_output_v2.md`. |
| Sample fixture | [`data/fixtures/sample_pipeline_output.csv`](../../../data/fixtures/sample_pipeline_output.csv) | 10 rows for station `AP140` at 5-minute cadence, committed to git so it is available on a fresh clone. All schema-validated columns pass `units_def.validate_pipeline_row` with zero violations. |

`outputs/` is gitignored, so a fresh clone has only the fixture. Do not write tests that depend on files in `outputs/`.

### The fixture is not byte-identical to a real export

The schema document says the fixture "matches this exact schema", and it does for column names, order, and units. But the fixture and a real pipeline export differ in value formatting. A contract test built on the fixture alone will miss these:

| Aspect | Sample fixture | Real export (`dlr_pipeline.export_results`, as seen in `outputs/station_data/`) |
|---|---|---|
| `datetime_utc` text | `2026-07-15T18:00:00Z` | `2025-07-01 00:00:00+00:00` (pandas default) |
| `relative_humidity` | Always populated | Can be blank (empty string in CSV, `NaN` when parsed) |
| Cadence | 5 minutes | Whatever the run requested; the checked-in `AN489` and `AN490` example files are hourly. |
| `dlr_uplift_flag` | `True` or `False` text | Same (`True` or `False`) |
| Numeric precision | Short decimals | Full float precision, for example `4.304557290454432` |

Your parser must accept both timestamp formats and treat an empty `relative_humidity` as missing, not zero. Add a second, small hand-written CSV fixture in the Software team's own test data directory that uses the real-export formatting. Do not edit `data/fixtures/sample_pipeline_output.csv`; DS owns it.

### What to assert

Split the checks into producer-side and consumer-side tests. Keep the column list in one place on each side so a schema change is a one-line edit.

**Producer-side (backend, Python, runs under the existing pytest setup):**

1. The fixture's header equals the `cols` list in `dlr_pipeline.export_results`, in order:
   `stid, datetime_utc, air_temp, wind_speed, wind_direction, wind_perp_ms, solar_radiation, relative_humidity, dlr_amps, dlr_headroom_pct, dlr_uplift_flag`.
2. Every fixture row passes `units_def.validate_pipeline_row(row, strict=False)` with an empty error list.
3. The CSV that `export_results` writes from a synthetic run has the same header as the fixture. `dlr_pipeline_test.py` already shows how to run `run_pipeline` with a patched `fetch_timeseries`.

**Consumer-side (`api/` and `frontend/`, tooling not yet chosen):**

1. The parser reads the fixture and yields 10 rows with 11 fields each.
2. Types after parsing: `stid` is a string; `datetime_utc` is a UTC instant; the numeric columns are numbers; `dlr_uplift_flag` is a boolean (not the string `"False"`, which is truthy in many languages).
3. The parser handles the real-export formatting from the second fixture: space-separated timestamp with `+00:00`, blank `relative_humidity`, long decimals.
4. Derived-field consistency: `dlr_uplift_flag` is true exactly when `dlr_amps` is above the static rating, and `dlr_headroom_pct` equals `(dlr_amps - static_rating) / static_rating * 100`. The fixture implies a static rating of 900 A (its first row: 1180 A gives 31.11% headroom), which is `config.DEFAULT_STATIC_RATING`.
5. Rejection behavior: a file missing a column, or with columns reordered, produces a clear error rather than silently shifted data. Decide whether the API rejects by name or by position; the schema fixes both.
6. Range checks mirror `PIPELINE_SCHEMA` for columns 3 to 9 (for example `dlr_amps` in `[100, 4000]`, `relative_humidity` in `[0, 100]`). Treat out-of-range values as data-quality warnings to surface, matching the backend, which logs violations but never drops rows.

The consumer tests should read the fixture from its checked-in path rather than copying it, so a DS update to the fixture is exercised immediately.

### Test data for contract extensions

The v1 contract does not carry forecast, trusted duration, fallback or anomaly status, sag, a city identifier, or the static rating (see the gaps listed in [architecture.md](architecture.md) and `docs/frontend/ROADMAP.md`). For panels that need those fields, `docs/frontend/ROADMAP.md` recommends an agreed mock extension of the fixture. Keep any such mock clearly labeled as a mock, and do not invent column names in production code until DS confirms them.

### Keeping the contract honest

- When `pipeline_output_v1.md` changes, update the consumer-side column list and fixtures in the same PR.
- A schema bump to `pipeline_output_v2.md` should keep the v1 tests as a regression check until the v1 export is retired.
- The shadow forecast JSONL feed (`data/shadow/predictions/{CITY}.jsonl` on the `shadow-collection-data` branch; `schema_version: 3`, records carry `city`) has no published, final contract and is marked experimental. Do not write contract tests against its v3 field list yet. A tolerance test is reasonable: a reader must accept the legacy corridor files (`AUSTIN_CORPUS_CHRISTI.jsonl`, `MIDLAND_EL_PASO.jsonl`; v1 flat and v2 rows) without error and never mix them into per-city results.

## Related docs

- [architecture.md](architecture.md) for the data flow and the PLANNED `api/` and `frontend/` layers.
- [configuration.md](configuration.md) for environment variables and file locations.
- [`docs/data-science/schema/pipeline_output_v1.md`](../../data-science/schema/pipeline_output_v1.md) for the column contract.
- `docs/frontend/ROADMAP.md` for the F1 to F8 phases, including the F8 test plan.
