---
schema_version: 1
open_count: 1
waived_count: 0
fixed_count: 0
total_count: 1
last_updated: 2026-09-29T18:52:49.533Z
---

# Broken Windows Ledger

> Cross-phase defect register. With `workflow.windows_enforce` enabled, `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 03 | deviation | backend/tests/corridor_discretization_test.py |  | 23 pre-existing failures reproducible in isolation on the phase's base commit, unrelated to files this plan (03-02) touches (wind_vector.py, thermal_model.py, forecast_training.py); not fixed per scope boundary | open |  | 2026-09-29T18:52:49.533Z |  |

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
  }
]
````
