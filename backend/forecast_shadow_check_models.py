"""
Pre-flight for the scheduled shadow collector: fail fast, with a clear
message, if any persisted ML artifact `data/shadow/models/{method}_{CITY}.joblib`
is missing for the three artifact-backed candidates x `config.LOCATIONS`.

The runner gets models only through `actions/checkout` of main (that
directory is deliberately git-tracked) and cannot retrain, so a missing file
would otherwise silently turn a candidate `unavailable` for every run. Method
names and the filename rule come from `forecast_shadow_pipeline` (never
re-typed here). Exit 0 = all present; exit 1 = list of missing paths.
"""

from __future__ import annotations

import sys

import config
import forecast_shadow_pipeline as shadow

ARTIFACT_METHOD_NAMES: tuple[str, ...] = (
    shadow.WindCorrectionShadowMethod.name,
    shadow.CoolingCorrectionShadowMethod.name,
    shadow.ReferenceRefit24hShadowMethod.name,
)


def missing_artifacts() -> list[str]:
    import os

    return [
        shadow._model_path_for(city, method)
        for city in config.LOCATIONS
        for method in ARTIFACT_METHOD_NAMES
        if not os.path.exists(shadow._model_path_for(city, method))
    ]


def main() -> int:
    missing = missing_artifacts()
    if missing:
        print(f"ERROR: {len(missing)} shadow model artifact(s) missing (refit offline with "
              f"backend/forecast_shadow_fit_models.py and commit them to main):", file=sys.stderr)
        for path in missing:
            print(f"  - {path}", file=sys.stderr)
        return 1
    print(f"OK: all {len(config.LOCATIONS) * len(ARTIFACT_METHOD_NAMES)} shadow model artifacts present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
