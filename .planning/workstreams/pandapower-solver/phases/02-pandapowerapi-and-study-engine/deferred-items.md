# Phase 2 deferred items

Out-of-scope discoveries logged during execution. Not fixed by the plan that found them.

## 02-03 (2026-11-18)

- `backend/tests/pandapower_cli_test.py::test_private_outputs_are_ignored_and_flagged_by_the_leak_guard`
  fails on this Windows checkout at `assert stat.S_IMODE(os.stat(path).st_mode) == 0o600` (reads 0o666).
  Windows does not honour POSIX file modes, so a `chmod 0o600` in the Phase 1 check CLI cannot show
  in `os.stat`. Plan 01-09's code and test; unrelated to plan 02-03 (the test touches the check CLI,
  not the adapter, scaling or the study). The other 30 tests of `pandapower_compare_test.py` and
  `pandapower_cli_test.py` pass. A fix would skip the mode assertion on `os.name == "nt"`; to be
  decided by whoever owns Phase 1's test.
