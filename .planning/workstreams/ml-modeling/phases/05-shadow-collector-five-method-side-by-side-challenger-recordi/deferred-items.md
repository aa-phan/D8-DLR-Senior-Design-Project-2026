# Deferred Items — Phase 05

## 23 pre-existing failures in `backend/tests/corridor_discretization_test.py` (out of scope for 05-04)

Found while running the full `backend/tests/` suite as part of 05-04's regression check (full-suite
run: `857 passed, 23 failed`). None of these 23 failures are in files this plan touches
(`backend/forecast_shadow_pipeline.py`, `backend/forecast_shadow_fit_reference_refit.py`,
`backend/forecast_shadow_demo.py`'s one-line call-site fix, or either test file this plan modifies)
-- `corridor_discretization_test.py` imports only `config`, `corridor_discretization`, and
`station_explorer`, none of which this plan edits or depends on transitively through anything this
plan changed. `git log --oneline -3 -- backend/corridor_discretization.py` shows no commit from this
plan touching that module.

Representative failures: `test_rate_corridor_calls_fetcher_once_per_point_even_with_shared_station`,
`test_probe_first_candidate_succeeds_calls_fetcher_once`, `test_bottleneck_cooled_point_at_index_0_is_identified`,
`test_rate_corridor_archives_one_row_per_call` (a `FileNotFoundError` on a tmp path). The failure
shapes (fetch-call counters reading 0, probe trails reading empty lists, a `FileNotFoundError` on a
pytest `tmp_path`) look environmental/pre-existing rather than caused by any change in this plan --
per this plan's own scope boundary ("Only auto-fix issues DIRECTLY caused by the current task's
changes"), these are logged here, not fixed, and not re-run hoping they resolve themselves.

**Status:** Deferred — not fixed by 05-04. Flag for whoever next touches
`backend/corridor_discretization.py` or its test file.
