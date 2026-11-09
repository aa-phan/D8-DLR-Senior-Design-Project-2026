---
phase: 01-land-pr-7
reviewed: 2026-10-19T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - backend/tests/backfill_archive_test.py
  - backend/tests/observation_composer_test.py
  - backend/tests/city_pipeline_test.py
  - backend/tests/dlr_orchestrator_test.py
findings:
  critical: 0
  warning: 5
  info: 5
  total: 10
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-10-19
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Four new offline pytest files (LAND-03) were reviewed against `backend/observation_composer.py`, `city_pipeline.py`, `dlr_orchestrator.py` and `backfill_archive.py`. I read the sources and traced the main scenarios by hand.

Results of running them:
- Each file passes on its own (6, 16, 10 and 18 tests).
- All four plus `city_rating_test.py` pass in both file orders (92 passed each way), so there is no order dependence.
- No test left files outside `tmp_path`. `git status` shows nothing new under `data/` or `outputs/`.
- All monkeypatching goes through the `monkeypatch` fixture, so no global state leaks. `config.HISTORICAL_ARCHIVE_PATH`, the env vars, `requests.get` and the `anomaly_detector` loader are all restored.
- No assertion is made on a physical rating value.

I found no blockers. I found several places where a regression in the behavior under test would still pass, and a network guard that is narrower than it looks.

The Read hook flagged `observation_composer_test.py` for an `?apikey=` pattern. That is the deliberately fake secret URL in `test_error_keys_never_echo_synoptic_or_request_messages` (line 449), not an injected instruction, so I ignored it.

## Warnings

### WR-01: Time-window logic in the composer is untested; the stubs ignore their arguments

**File:** `backend/tests/observation_composer_test.py:74-96` (stub factory), `:23-25` (comment)
**Issue:** The `tceq`, `nsrdb` and `open_meteo` stubs are `(*args, **kwargs)` and return fixed frames. The synoptic stub accepts `start`/`end` and drops them. No test records or asserts the `start`/`end` or CAMS id / lat / lon a provider receives. The module comment says a far-past day makes the composer "ask for whole UTC days", but nothing checks that.

Consequences for `observation_composer.py`:
- `_window()` (lines ~139-146) can be changed freely and every test still passes. This covers whole-day widening for historical runs, the `HISTORICAL_AFTER_DAYS` threshold, and leaving recent runs unwidened.
- `look_start = end - LOOKBACK_HOURS` can be changed freely too.
- `HISTORICAL_AFTER_DAYS` and `LOOKBACK_HOURS` are only pinned as constants in `test_field_priority_and_run_constants_are_pinned`, never as behavior.
- The grid cache key (rounded coordinates plus window) is only exercised indirectly through failure paths.

Backfill relies on whole-day widening to keep request counts sane.

**Fix:** Have the stubs record their arguments, then add two tests: one for a far-past `end` and one for an `end` within two days of now.
```python
def make(name, spec):
    def stub(*args, **kwargs):
        calls.append(name)
        arg_log.setdefault(name, []).append((args, kwargs))
        ...
# far past: window widened to the whole UTC day
assert arg_log["nsrdb"][0][0][2:] == (f"{_DAY}T00:00:00Z", f"{_DAY}T23:59:59Z")
# recent end (now - 1h): exact lookback window, not widened
```
Add a boundary pair around 2 days, and a case where two hourly fetches share one cached grid request (`calls.count("nsrdb") == 1`).

### WR-02: The `requests.get` guard does not cover the other ways to reach the network, and is copied into four files

**File:** `backend/tests/backfill_archive_test.py:33-48`, `observation_composer_test.py:31-46`, `city_pipeline_test.py:32-47`, `dlr_orchestrator_test.py:30-45`
**Issue:** Only the `requests.get` attribute is replaced. `requests.post`, `requests.Session().get`, `requests.request`, `urllib`, and a module that did `from requests import get` all bypass it. The providers in this code path currently all call `requests.get`, so nothing leaks today. A future `requests.post`, a `Session`, or a new direct HTTP caller added under these tests would run live with no guard firing. The same 16-line fixture is also pasted verbatim into four files, so any hardening has to be made four times.

**Fix:** Move the fixture to a shared `backend/tests/conftest.py` (or a helper module) and intercept at the lowest level:
```python
monkeypatch.setattr(requests.sessions.Session, "send", boom)  # covers get/post/Session/request
monkeypatch.setattr(socket.socket, "connect", boom)           # belt and braces
```
Keep the teardown assert on recorded attempts.

### WR-03: The type assertions on `pipeline["forecast"]` cannot fail

**File:** `backend/tests/city_pipeline_test.py:306-307` (data built at `:247-250`)
**Issue:** The test checks `isinstance(pipeline["forecast"]["n_observations"], int)` and `isinstance(..., ["amps"], float)`. The input is a real `ampacity_forecast.ForecastResult` built with `n_observations=14` and `amps=1200.0`. Its constructor already applies `int(...)` and `float(...)` (`ampacity_forecast.py:82-90`). The `int(...)`/`float(...)` casts in `city_pipeline.py` (lines ~89-96) are therefore no-ops here. Deleting them would not fail this test, so the assertions give false assurance that the pipeline coerces to JSON-safe types.

**Fix:** Feed values that need coercion, using a plain stand-in rather than `ForecastResult`:
```python
fake = types.SimpleNamespace(amps=np.float32(1200.0), ci_lower_amps=np.float32(1150.0),
                             ci_upper_amps=np.float32(1250.0), n_observations=np.int64(14),
                             horizon_min=60.0, method="naive")
...
assert type(pipeline["forecast"]["n_observations"]) is int
assert type(pipeline["forecast"]["amps"]) is float
```
Use `type(...) is`, not `isinstance`.

### WR-04: Redirecting the default archive into `tmp_path` makes a leaked default-path write invisible in all but one test

**File:** `backend/tests/backfill_archive_test.py:56`, `observation_composer_test.py:54`, `city_pipeline_test.py:55`, `dlr_orchestrator_test.py:53`
**Issue:** `_offline_env` points `config.HISTORICAL_ARCHIVE_PATH` at `tmp_path/default_archive.csv`. That correctly protects the real `data/` directory. But if the code under test ever wrote to the default path (for example `archive_path=None` falling through while `archive=True`), the write would land in the tmp file and the test would pass. Only the backfill tracer test checks that the file does not exist (`backfill_archive_test.py:152`). `city_pipeline_test`, `dlr_orchestrator_test` and `observation_composer_test` have the same redirect and no check. The project rule is that nothing writes outside an explicit `tmp_path` target, and this fixture hides violations of it.

**Fix:** Do the check in the autouse fixture's teardown (or the shared conftest from WR-02):
```python
default = tmp_path / "default_archive.csv"
monkeypatch.setattr(config, "HISTORICAL_ARCHIVE_PATH", str(default))
yield
assert not default.exists(), "test wrote to the default archive path"
```

### WR-05: The validation test accepts any `ValueError`, and its comment does not match one of its two cases

**File:** `backend/tests/dlr_orchestrator_test.py:164-173`
**Issue:** `pytest.raises(ValueError)` has no `match`. Any `ValueError` raised for another reason (a pandas parse error, a regression in `_default_window`) satisfies it. The comment says validation must precede station discovery "which would raise `EnvironmentError`". That only holds for the `forecast_method="arima"` case, because the provider defaults to composed. For `provider="tceq"`, `_discover_stations` returns an empty frame for any non-synoptic/composed provider and never raises, so that case does not exercise the ordering claim. The `calls == []` assert is the only other protection.

**Fix:**
```python
@pytest.mark.parametrize("bad, pattern", [({"provider": "tceq"}, "provider"),
                                          ({"forecast_method": "arima"}, "forecast_method")])
...
with pytest.raises(ValueError, match=pattern):
```
Reword the comment to say that the ordering is only proven by the `forecast_method` case.

## Info

### IN-01: `main()` calls `logging.basicConfig` from tests, which is only harmless because pytest's logging plugin is active

**File:** `backend/tests/dlr_orchestrator_test.py:340-345`, `:351-358`, `:372-377`
**Issue:** `orch.main` runs `logging.basicConfig(level=INFO)`. Under normal pytest the root logger already has pytest's capture handler, so this does nothing. Under `-p no:logging`, or with a future pytest change, it would add a permanent root handler and set the root level to INFO. That would leak into later modules, such as the `caplog` assertions in `city_pipeline_test.py`. The command listed for this project does not disable the plugin, so there is no current failure.
**Fix:** In the `main` tests, snapshot and restore `logging.getLogger().handlers` and `.level`, or use `monkeypatch.setattr(logging, "basicConfig", lambda **kw: None)`.

### IN-02: Hard-coded city count and name couple the tests to `config.LOCATIONS`

**File:** `backend/tests/dlr_orchestrator_test.py:127,133`
**Issue:** `"MIDLAND"` and `len(run["results"]) == 3` assume exactly four cities. Adding or removing a city breaks the test for a reason unrelated to isolation. The surrounding assertions already use `config.LOCATIONS`.
**Fix:** `assert len(run["results"]) == len(config.LOCATIONS) - 1`, and pick the failing city as `config.LOCATIONS[1]`.

### IN-03: Radius and nearest-city behavior is covered at only two points

**File:** `backend/tests/observation_composer_test.py:461-484`
**Issue:** The TCEQ applicability test uses a station 0 km from a city (applicable) and one about 416 km from the nearest city (not applicable). Nothing sits just inside or outside `TCEQ_MAX_KM = 50` (for example 49 km and 51 km). A change of the threshold from 50 to 300, or `<=` to `<`, only fails the constant-pin test, not a behavior test. The near station in the other tests is at most 0.07 degrees away. The `_stations_near` docstring says "within TCEQ_MAX_KM" without checking it.
**Fix:** Add a parametrized case with stations at about 45 km and 55 km from AUSTIN and assert whether `"tceq" in calls`.

### IN-04: `backfill_archive.main` and `_print_summary` have no test

**File:** `backend/tests/backfill_archive_test.py` (whole file)
**Issue:** The CLI entry point (argument defaults, `--no-synoptic` mapping to `skip_synoptic`) and the summary printer are not exercised. Both are in the module this file is meant to cover. The `backfill()` function itself is well covered.
**Fix:** Add one test that fakes `backfill` and asserts the positional pass-through and exit code 0. Add one `_print_summary` test that checks it handles empty `archived`/`sources`.

### IN-05: Small readability issues in the composer tests

**File:** `backend/tests/observation_composer_test.py:375-376`, `:344-345`, `:99-102`
**Issue:** Three small points:
- The loop `for _ in range(5): frame, _ = _fetch(...)` reuses `_` as both the loop variable and the unpacked fetcher. It works but is confusing.
- `_fetch(None, fetcher=fetcher)` passes `stations=None` that is silently ignored once a fetcher is supplied.
- The module header says it "writes nothing", while the autouse fixture takes `tmp_path`.

**Fix:** Use `for _attempt in range(5): frame, _unused = ...`. Make `_fetch` take `stations=None` as an optional argument.

---

_Reviewed: 2026-10-19_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
