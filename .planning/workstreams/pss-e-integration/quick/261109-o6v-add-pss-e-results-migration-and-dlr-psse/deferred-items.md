# Deferred items (quick 261109-o6v)

Out of scope: not caused by this task's changes, so not fixed here.

- `backend/tests/forecast_shadow_demo_test.py::test_run_once_all_methods_ok_with_per_city_artifacts_and_a_complete_truth_proxy_window`
  fails in the full suite at about 23:48 to 23:50 UTC on 2026-11-09 (it fails again when run alone).
  `reference_ml_refit_24h` comes back `unavailable` with the reason "no usable Open-Meteo
  historical-forecast solar row within 0 days 00:35:00". The test builds its truth-proxy window
  from the wall clock, so it looks time-of-day dependent (run just before midnight UTC). The test
  file and the code it covers are untouched by this task. Re-run it at another hour to confirm.
