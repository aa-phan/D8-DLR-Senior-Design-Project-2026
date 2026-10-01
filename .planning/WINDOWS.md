---
schema_version: 1
open_count: 3
waived_count: 0
fixed_count: 0
total_count: 3
last_updated: 2026-10-01T03:46:46.718Z
---

# Broken Windows Ledger

> Cross-phase defect register. With `workflow.windows_enforce` enabled, `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 03 | deviation | backend/tests/corridor_discretization_test.py |  | 23 pre-existing failures reproducible in isolation on the phase's base commit, unrelated to files this plan (03-02) touches (wind_vector.py, thermal_model.py, forecast_training.py); not fixed per scope boundary | open |  | 2026-09-29T18:52:49.533Z |  |
| 2 | 04 | deviation | .planning/workstreams/ml-modeling/phases/04-forecast-correction-experiment-follow-up-audit-data-provenan/04-02-PLAN.md |  | Plan 04-02's own Task 1-3 doc-verify scripts use a self-contradicting section-boundary regex (r'^##+ ' also matches the required r'^###+ ' subsection markers); substantive intent independently confirmed via the corrected r'^## ' boundary, no code change needed. | open |  | 2026-09-30T23:57:26.945Z |  |
| 3 | 04 | deviation | .planning/workstreams/ml-modeling/phases/04-forecast-correction-experiment-follow-up-audit-data-provenan/04-04-PLAN.md |  | Plan 04-04 Task 1's own <verify> literal for overrating_profile hand-computes an incorrect expected result (count==6, runs=={2:1,1:1,3:1}) for its truth/pred fixture; the mathematically correct count is 7 with runs {2:1,4:1,1:1} (verified independently by script and matched exactly by the executor's own pytest test_overrating_profile_matches_hand_computation, part of the passing 74-test suite). Implementation follows the plan's prose <action>/<behavior> spec exactly; only the embedded verify literal is wrong. Same defect class as issue #2 (self-contradicting regex). | open |  | 2026-10-01T03:46:46.718Z |  |

````json
[
  {
    "id": 1,
    "kind": "deviation",
    "phase": "03",
    "file": "backend/tests/corridor_discretization_test.py",
    "line": null,
    "description": "23 pre-existing failures reproducible in isolation on the phase's base commit, unrelated to files this plan (03-02) touches (wind_vector.py, thermal_model.py, forecast_training.py); not fixed per scope boundary",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-29T18:52:49.533Z",
    "resolved_at": null
  },
  {
    "id": 2,
    "kind": "deviation",
    "phase": "04",
    "file": ".planning/workstreams/ml-modeling/phases/04-forecast-correction-experiment-follow-up-audit-data-provenan/04-02-PLAN.md",
    "line": null,
    "description": "Plan 04-02's own Task 1-3 doc-verify scripts use a self-contradicting section-boundary regex (r'^##+ ' also matches the required r'^###+ ' subsection markers); substantive intent independently confirmed via the corrected r'^## ' boundary, no code change needed.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-30T23:57:26.945Z",
    "resolved_at": null
  },
  {
    "id": 3,
    "kind": "deviation",
    "phase": "04",
    "file": ".planning/workstreams/ml-modeling/phases/04-forecast-correction-experiment-follow-up-audit-data-provenan/04-04-PLAN.md",
    "line": null,
    "description": "Plan 04-04 Task 1's own <verify> literal for overrating_profile hand-computes an incorrect expected result (count==6, runs=={2:1,1:1,3:1}) for its truth/pred fixture; the mathematically correct count is 7 with runs {2:1,4:1,1:1} (verified independently by script and matched exactly by the executor's own pytest test_overrating_profile_matches_hand_computation, part of the passing 74-test suite). Implementation follows the plan's prose <action>/<behavior> spec exactly; only the embedded verify literal is wrong. Same defect class as issue #2 (self-contradicting regex).",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-10-01T03:46:46.718Z",
    "resolved_at": null
  }
]
````
