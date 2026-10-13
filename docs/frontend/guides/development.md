<!-- generated-by: gsd-doc-writer -->
# Development

This guide is for the Software sub-team building the React dashboard (`frontend/`) and the Flask API (`api/`). It covers repo conventions, the commit and branch style visible in git history, how to write a component spec, and how to build against the Data Science (DS) output contract.

**Status legend used throughout:**

- **Built** means the file, tool, or workflow exists in the repo today.
- **PLANNED** means it is intended but nothing exists yet. Do not assume it works.

Today `frontend/` and `api/` each contain a single `README.md`. There is no `package.json`, no `requirements.txt` for Flask, no app code, no lint or formatter config, and no CI for either subsystem. Everything in the "Tooling" section marked PLANNED is a decision the team still has to make. See [architecture.md](architecture.md) for how the backend produces data and [configuration.md](configuration.md) for tokens and file locations.

## Local setup

All commands run from the repo root.

1. Clone the repo and check out `main`.
2. Create and activate a Python virtual environment. `.venv` is git-ignored.

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install the pinned Python dependencies. CI uses Python 3.12 (`.github/workflows/shadow_collect.yml`).

   ```bash
   python -m pip install -r requirements.txt
   ```

4. Confirm the test suite collects. `pytest.ini` sets `pythonpath = backend` and `testpaths = backend/tests`.

   ```bash
   pytest --co -q
   ```

You do not need a Synoptic token or an NREL key to start frontend or API work. The checked-in fixture `data/fixtures/sample_pipeline_output.csv` is enough. Credentials are needed only to regenerate real pipeline output; see [configuration.md](configuration.md).

`requirements.txt` covers the Python backend only. When you scaffold `api/`, decide whether Flask goes into that shared file or into a separate `api/` requirements file. This is not decided. When you scaffold `frontend/`, the package manager and build tool (for example Vite, Create React App, Next.js) are also not decided. The only stack commitment in the repo is "React" and "Flask" in `docs/System Design Report.md` Appendix E.

## Repository conventions

| Path | Convention |
|---|---|
| `backend/` | Flat Python modules that import each other by bare name (`import config`), run with `PYTHONPATH=backend`. Owned by the DS sub-team. Treat as read-only from the Software side unless you coordinate a change. |
| `backend/tests/` | pytest suite. Files match `*_test.py`, `test_*.py`, or `*_TestSuite.py` (per `pytest.ini`). |
| `frontend/`, `api/` | Owned by the Software sub-team. Each has a placeholder `README.md` stating status, owner, and planned stack. Update that README when you scaffold real code. |
| `data/` | Checked-in reference inputs and fixtures. Generated subfolders are git-ignored; see [configuration.md](configuration.md). |
| `outputs/` | Generated pipeline output. Git-ignored as a whole, so it is absent from a fresh clone. |
| `docs/data-science/` | DS requirements, roadmap, specs, schema, and decision records. The model for your docs. |
| `docs/frontend/` | Your docs: `README.md` (convention), `PRD.md`, `ROADMAP.md`, `specs/` (F1–F8 component specs and `api-contract.md`), `guides/` (these how-to guides). |

Other conventions worth following:

- **Never commit secrets.** `.env` is git-ignored. Tokens go in your shell or `.env`, never in source.
- **Do not hand-edit generated files.** The `README.md` on the `shadow-collection-data` branch is regenerated on every collection run and any edit is overwritten.
- **Docs use plain Markdown** with no site generator (no Docusaurus, VitePress, or MkDocs config is present), and no frontmatter.
- **Refer to modules by path and function** (for example `backend/dlr_pipeline.py::export_results`), as the DS docs do, so claims can be checked against code.

## Commit style

The git history (about 470 commits on `main`) follows Conventional Commits: `type(scope): subject`, lowercase, no trailing period, with an optional body that explains the why.

Types seen in the log: `feat`, `fix`, `docs`, `test`, `chore`, `revert`, and `merge`. Recent examples:

```text
fix(shadow): retry the solar-proxy fetch on timeout
docs(shadow): add five-method explanation to README; standardize UTC/local timestamp display
feat(shadow): bundle-level ampacity (subconductors-per-phase) + remove duplicate README table
```

Existing scopes name either a backend area (`shadow`) or a numbered work item (`05-05`, `04-correction`). There are no `frontend` or `api` scopes yet. Using `frontend` and `api` as scopes for your commits fits the pattern, but this is a suggestion rather than an established convention.

Practices visible in commit bodies that are worth copying:

- Explain what was wrong or missing and why the change is the fix, not just what changed.
- State how you verified it (for example "137/137 passing", or "rendered real live data through the actual entry point").
- Say what you deliberately did not touch.

Not all history is clean. A few early commits on side branches have non-conventional subjects (`Original Updates to Main`, `Update corridor_pipeline.py`); do not treat those as the style.

## Branching

**No convention is documented.** There is no `CONTRIBUTING.md`, PR template, or branch-naming rule in the repo. What the history shows:

- `main` is the default branch and carries essentially all work, including the shadow collector's code. The scheduled workflow checks out `main`.
- `origin` also holds `data-science`, `embedded-systems`, and `power-systems`, each sitting at a single "first commit". These look like per-sub-team branches, but no workflow uses them.
- `feature/phase1-foundation` and `feature/phase2-core-consolidation` are earlier feature branches by topic.
- `shadow-collection-data` is a machine-written data branch. Never commit to it by hand.
- One pull request is visible in history (`Merge pull request #4 from aa-phan/track-1-updates-v2`, merged into `test`).

There is no software-side branch yet. Agree on a convention with the team and write it down here. A reasonable starting proposal, clearly not yet adopted, is short-lived topic branches such as `frontend/<topic>` and `api/<topic>` that merge into `main`.

<!-- VERIFY: branch protection, required reviewers, and merge method on the GitHub remote are not visible from the repository contents -->

## Tooling

| Concern | Status |
|---|---|
| Python tests (`pytest`) | Built. Run from the repo root with `pytest`. About 920 tests are collected. |
| Python lint/format | None configured (no ruff, flake8, black, or `.editorconfig`). |
| CI | Built for one purpose only: `.github/workflows/shadow_collect.yml` ("Shadow Collection"), a scheduled data collector. There is no workflow that runs tests, lint, or builds on push or pull request. |
| `frontend/` build, lint, format, unit tests | PLANNED. Nothing exists. Choose and record them in the frontend PRD or a spec. |
| `api/` framework layout, lint, tests | PLANNED. Nothing exists. Flask is the only decision. |
| Pre-commit hooks | None. |
| Container or deploy config | None. Hosting is undecided. |

Do not copy commands from other projects into your docs. When you add a script, document the command you actually ran.

Running the backend tests before and after touching anything in `backend/`:

```bash
pytest                                  # whole suite
pytest backend/tests/units_def_test.py  # one file
```

## Working against the DS output contract

The contract between DS and the dashboard is the exported station CSV. Treat it as the interface and build to it, not to the Python internals.

| Artifact | Location |
|---|---|
| Schema document (v1) | `docs/data-science/schema/pipeline_output_v1.md` |
| Sample fixture | `data/fixtures/sample_pipeline_output.csv` |
| Producing code | `backend/dlr_pipeline.py::export_results` |
| Component spec | `docs/data-science/specs/C3-export-visualization.md` |
| Row validator | `backend/units_def.py::validate_pipeline_row` |

### The v1 shape

Eleven columns, in this order: `stid, datetime_utc, air_temp, wind_speed, wind_direction, wind_perp_ms, solar_radiation, relative_humidity, dlr_amps, dlr_headroom_pct, dlr_uplift_flag`. Units and valid ranges are in the schema document; do not restate them in frontend code or docs, link to the schema.

Rules of the contract, taken from `pipeline_output_v1.md`:

- Any add, remove, reorder, or rename of a column is a breaking change and bumps the document to `pipeline_output_v2.md`. Watch for that file appearing.
- Read columns by name, not by position.
- `datetime_utc` is an ISO-8601 UTC string (for example `2026-07-15T18:00:00Z`) at 5-minute cadence. Convert to local time in the UI.
- `dlr_headroom_pct` and `dlr_uplift_flag` are derived from whichever static rating the run used. The fixture was produced against the 900 A default (`config.DEFAULT_STATIC_RATING`), so its headroom values will not match a run that used a per-city rating from `config.STATIC_RATINGS` (each city uses its own entry, not a corridor minimum). Show the static rating you are comparing against alongside any headroom figure.
- `dlr_uplift_flag` is a boolean serialized in CSV as `True` or `False`. Parse it explicitly rather than treating the string as truthy.
- The static ratings are placeholders (midpoints of ranges in `docs/Project Definition.md`), not confirmed line ratings. Label them that way in the UI.
- Not in the v1 file: MW values (added by `backend/ercot_dlr_merger.py`), forecasts, per-city rating status, alerts, a `city` column, and any trusted-duration value. See "Gaps" in [architecture.md](architecture.md) before designing a panel that needs them.

### Develop against the fixture first

1. Load `data/fixtures/sample_pipeline_output.csv` (10 rows, station `AP140`, 5-minute cadence) as your mock data source.
2. Write your parsing and component code against the column names above.
3. Optionally check any hand-made or generated sample against the validator. The fixture passes with zero violations:

   ```bash
   python -c "
   import sys; sys.path.insert(0, 'backend')
   import pandas as pd, units_def
   df = pd.read_csv('data/fixtures/sample_pipeline_output.csv')
   bad = [units_def.validate_pipeline_row(r.to_dict(), strict=False) for _, r in df.iterrows()]
   print(sum(len(v) for v in bad), 'violations')
   "
   ```

4. Once you hold a Synoptic token and have run `python backend/dlr_pipeline.py` (see the root `README.md`), swap the fixture for real `outputs/station_data/*.csv` files. Real files are named `<start>_<end>_<STID>.csv`. Because of a known issue, a station that returns zero rows is silently absent from the output; do not assume every requested station has a file.
5. If you need data the contract lacks, ask DS to extend it. Do not parse the plots or reach into backend internals. Raise it as an open question in the relevant spec. Contract changes should land in the DS schema doc first.

### The other feeds

Two other data sources exist but have weaker contracts. Confirm their shape with DS before depending on them.

- `data/historical/ampacity_history.csv` (git-ignored, written when a per-city rating is archived) has a locked column list in `historical_archive.ARCHIVE_COLUMNS` and a `schema_version` column. The corridor-era columns are not yet redefined for per-city rows (open).
- The shadow forecast JSONL on the `shadow-collection-data` branch is experimental. Files are now one per city (`{CITY}.jsonl`, `schema_version: 3`, records carry `city`); the corridor-named files are legacy and hold the older flat shape and `schema_version: 2`. Any parser must tolerate all three and must not mix legacy corridor rows into per-city views. Details are in [architecture.md](architecture.md).
- The dashboard works per city: four independent rating points, no corridor minimum and no bottleneck. See `docs/data-science/decisions/point_scope.md`.

## Adding a component spec

Specs are how the DS team made work splittable without idle time, and `docs/frontend/README.md` asks you to mirror that. The DS index and template are in `docs/data-science/specs/README.md`. The DS specs `C2-data-contract.md` and `C3-export-visualization.md` are good examples of the level of detail expected.

The planned structure for `docs/frontend/`, per its `README.md`:

- `PRD.md` for requirements.
- `ROADMAP.md` for phased order and the dependency graph.
- `specs/` with one file per component (F1–F8, plus `api-contract.md`).

`docs/frontend/README.md` says not to invent requirements ahead of time. Write the PRD first, then the roadmap, then the specs it implies. The DS PRD's section outline (purpose and scope, users and consumers, functional and non-functional requirements, open decisions) is a good model. Starting points for what the dashboard should do are `docs/Project Definition.md` and WBS 4.1 and 4.2 in `docs/System Design Report.md`.

### Steps

1. **Pick a component and an ID.** DS uses `C1` to `C10`, so avoid reusing those. A prefix per subsystem is a sensible suggestion (for example one for frontend components and one for API components) but is not yet decided; record the choice in the specs index.
2. **Create `docs/frontend/specs/README.md` if it does not exist.** Copy the DS index structure: a table of ID, component, phase, effort, status, and file, plus the shared template. The DS table columns are `ID | Component | Phase | Effort | Status | File`.
3. **Create the spec file** named `<ID>-<kebab-case-name>.md`, matching the DS naming (`C3-export-visualization.md`).
4. **Fill in every section of the template** in this order. Use "not started" where nothing exists rather than deleting a section:

   ```markdown
   # <ID> — <Component name>

   **Phase:** <n> · **Effort:** <S|M|L> · **Status:** <Not started | Partial | Implemented>.

   **Responsibility:** <one sentence>

   ## Current Implementation
   Files/functions, or "not started".

   ## Interface & Data Contract
   Inputs and outputs with units. Reference the DS schema; do not restate it.

   ## Blocked by
   Upstream components that must land first, and why.

   ## Blocks
   What waits on this component. Must be the exact inverse of other specs' "Blocked by".

   ## Parallel-safe with
   Components that can be worked on at the same time without file collisions.

   ## Known Issues
   Concrete, file-referenced problems.

   ## Acceptance Criteria
   Testable statements.

   ## Open Questions
   ```

5. **Keep the dependency graph consistent.** Every "Blocked by" entry needs a matching "Blocks" entry in the upstream spec, and vice versa. When `ROADMAP.md` exists, its dependency graph is the authoritative picture; update it in the same change.
6. **Declare the DS dependency explicitly.** A component that reads the station CSV is "Blocked by" the DS contract (C3 on the DS side), and its "Interface & Data Contract" section should link to `pipeline_output_v1.md`. If it needs a column or file DS does not yet produce, say so under "Open Questions" so DS can plan for it.
7. **Write acceptance criteria that can be checked.** For example, "renders the 10-row fixture without errors" is checkable, while "looks good" is not. Where the System Design Report states a requirement (WBS 4.1.3 DLR vs. SLR visualization, 4.1.4 forecast panel, 4.1.5 anomaly and fallback indicators, 4.2.1 connecting DS outputs to the feed), reference its number.
8. **Add the row to the specs index** and commit with a `docs` type, for example `docs(frontend): add spec for the DLR vs. SLR chart`.

## Submitting changes

No pull request template or review process is documented. Until the team writes one down, a sensible baseline based on how the history reads:

- Keep each commit to one logical change with a conventional message.
- Run `pytest` if you touched anything under `backend/` or `data/`.
- If your change affects what DS must produce, update the relevant spec or open question in the same commit as the code.
- Do not modify `backend/` or `docs/data-science/` for software-side concerns without telling the DS sub-team.

## Related docs

- [architecture.md](architecture.md) for data flow, key abstractions, and gaps.
- [configuration.md](configuration.md) for environment variables, `backend/config.py`, and file locations.
- `docs/frontend/README.md` for the documentation convention.
- `docs/data-science/specs/README.md` for the spec template.
- `docs/data-science/ROADMAP.md` for the DS phase order and the cross-team unblock path.
