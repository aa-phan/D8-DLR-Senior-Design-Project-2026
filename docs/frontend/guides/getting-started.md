<!-- generated-by: gsd-doc-writer -->
# Getting Started

This guide is for the Software sub-team (`frontend/` and `api/`) picking up the repo for the first time. It gets you from a fresh clone to a working Python environment and real pipeline-shaped data on disk. For where the data goes next, see [architecture.md](architecture.md). For tokens and file locations in depth, see [configuration.md](configuration.md).

`frontend/` (React) and `api/` (Flask) are structural placeholders today. They contain only a `README.md` each, with no `package.json` and no Flask app. Everything you can run today is the Python backend in `backend/`.

## Prerequisites

| Requirement | Version | Why |
|-------------|---------|-----|
| Python | 3.12 recommended | The project's `.venv` and the GitHub Actions workflow (`.github/workflows/shadow_collect.yml`) both use 3.12. No minimum is declared in the repo. |
| git | any recent version | To clone the repo. |
| Synoptic API token | optional | Only needed to run the station pipeline against live data. |
| NREL/NLR API key and email | optional | Only needed for NSRDB solar data. |

You do not need any token to start building. The checked-in fixture (see [Start without a token](#start-without-a-token-use-the-sample-fixture)) has the same columns the pipeline exports.

## Installation

1. Clone the repo and enter it:

   ```bash
   git clone https://github.com/aa-phan/D8-DLR-Senior-Design-Project-2026.git
   cd D8-DLR-Senior-Design-Project-2026
   ```

2. Create and activate a virtual environment (`.venv` is git-ignored):

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install the pinned dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

`requirements.txt` is the source of truth for dependencies (pandas, numpy, scipy, pytest, beautifulsoup4, scikit-learn, python-dotenv, requests, matplotlib). The older `pip install requests pandas numpy scipy matplotlib rich` line (still in the `backend/dlr_pipeline.py` docstring) is superseded by `requirements.txt`.

Run every backend command from the repo root. Paths such as `data/` and `outputs/` are relative to the working directory.

## Start without a token: use the sample fixture

`data/fixtures/sample_pipeline_output.csv` is checked in. It holds one station (`AP140`) and 10 rows at 5-minute cadence, in the exact column order the pipeline exports:

`stid, datetime_utc, air_temp, wind_speed, wind_direction, wind_perp_ms, solar_radiation, relative_humidity, dlr_amps, dlr_headroom_pct, dlr_uplift_flag`

Load it with pandas to confirm your environment works:

```bash
python -c "
import pandas as pd
df = pd.read_csv('data/fixtures/sample_pipeline_output.csv', parse_dates=['datetime_utc'])
print(df.shape)
print(df[['datetime_utc', 'dlr_amps', 'dlr_headroom_pct']].head(3))
"
```

Expected output:

```
(10, 11)
               datetime_utc  dlr_amps  dlr_headroom_pct
0 2026-07-15 18:00:00+00:00    1180.0         31.111111
1 2026-07-15 18:05:00+00:00    1210.0         34.444444
2 2026-07-15 18:10:00+00:00    1245.0         38.333333
```

Things to know when building against it:

- `datetime_utc` is a UTC ISO-8601 string (for example `2026-07-15T18:00:00Z`). Convert to local time in the UI layer.
- Column meanings, units, and valid ranges are in [`docs/data-science/schema/pipeline_output_v1.md`](../../data-science/schema/pipeline_output_v1.md). Treat that file as the contract. A column change bumps it to `pipeline_output_v2.md`.
- `dlr_headroom_pct` and `dlr_uplift_flag` depend on the static rating the pipeline was run with, which comes from `backend/config.py`.
- When you later swap in real files, they will have the same columns.

## Run the pipeline (needs a Synoptic token)

The station pipeline fetches 5-minute West Texas Mesonet observations from the Synoptic API, so it needs a token.

1. Get a free research token at https://synopticdata.com/ and export it. A `.env` file is not read by this script; the variable must be in your shell:

   ```bash
   export SYNOPTIC_TOKEN=your_token_here
   ```

2. Run the pipeline from the repo root:

   ```bash
   python backend/dlr_pipeline.py
   ```

`dlr_pipeline.py` takes no command-line arguments. Its `__main__` block at the bottom of the file reads the station list from `data/wtm_stations_austin.csv` (`config.DEFAULT_STATION_SOURCE`), uses the window `config.DEFAULT_START` to `config.DEFAULT_END` (`2025-07-01T00:00:00Z` to `2025-07-04T23:55:00Z`), and rates the stations as city `AUSTIN`. To change any of those, edit `backend/config.py` or the bottom of `backend/dlr_pipeline.py`.

If the token is missing, the fetch raises an error ("Set SYNOPTIC_TOKEN env var"). If the fetch returns no rows, the script exports nothing. See [configuration.md](configuration.md) for the known caveat about the Austin station list returning zero rows under the project's token.

NSRDB solar data additionally needs `NREL_API_KEY` and `NREL_API_EMAIL`. You do not need them for the command above. See [configuration.md](configuration.md).

## Where outputs land

| Path | Contents |
|------|----------|
| `outputs/station_data/<start>_<end>_<STID>.csv` | One CSV per station, same columns as the fixture. For the default window the prefix is `2025-07-01_2025-07-04`. |
| `outputs/station_plots/<start>_<end>_<STID>.png` | One 4-panel summary plot per station: DLR vs static, wind, temperature, headroom histogram. |

`outputs/` is git-ignored, so a fresh clone has none of these files until you run the pipeline. Two other generated locations exist, `data/historical/ampacity_history.csv` and `data/shadow/predictions/*.jsonl`. They are also git-ignored and are described in [configuration.md](configuration.md) and [architecture.md](architecture.md).

## Run the tests

`pytest.ini` sets `pythonpath = backend` and `testpaths = backend/tests`, so from the repo root:

```bash
python -m pytest -q
```

The suite takes a couple of minutes. Counts previously recorded here (900 passed, 23 failed, all failures in `backend/tests/corridor_discretization_test.py`) predate the move to per-city scope: that test file and the corridor modules it covered are slated for removal (`docs/data-science/decisions/point_scope.md`), and the counts have not been re-measured. While the backend migration is in progress, failures in or around corridor, shadow or training tests may be expected. Check with the Data Science sub-team before treating a failure as something you broke. <!-- VERIFY: current pytest pass/fail counts after the per-city migration -->

## Common setup issues

- **`ModuleNotFoundError` for pandas, requests, or similar.** The virtual environment is not active or the install step was skipped. Re-run `source .venv/bin/activate` and `python -m pip install -r requirements.txt`.
- **Paths not found (`data/...` or `outputs/...`).** You ran from a subdirectory. Run from the repo root.
- **"Set SYNOPTIC_TOKEN env var" error.** The token is not in your shell environment. `dlr_pipeline.py` does not load `.env`; use `export SYNOPTIC_TOKEN=...` in the same terminal session.
- **Pipeline runs but writes nothing.** The Synoptic fetch returned zero rows, for example because the stations in the default list return no data under the token. Use the sample fixture in the meantime.
- **`import config` fails in your own script.** The backend modules expect `backend/` on the Python path. Run with `PYTHONPATH=backend`, as `pytest.ini` and the workflow do.

## Next steps

- [architecture.md](architecture.md): how data flows from `backend/` to flat files, and where `api/` and `frontend/` will attach.
- [configuration.md](configuration.md): environment variables, `backend/config.py`, and the full list of data and output locations.
- `docs/frontend/README.md`: the PRD, roadmap, and specs convention for the Software sub-team.
- `frontend/README.md` and `api/README.md`: code-side status of each subsystem.
