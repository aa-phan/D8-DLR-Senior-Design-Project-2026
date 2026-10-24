"""
Live model pre-flight (production-pipeline Phase 5, PIPE-02) -- RED-phase stub.

This stub has the planned public names and no behavior, so the tests can import
it and fail on their assertions. The implementation replaces it in the GREEN commit.
"""

from __future__ import annotations

import os

MANIFEST_PATH = os.path.join("data", "models", "LIVE_ARTIFACT_HASHES.sha256")


def required_artifacts() -> list[tuple[str, str, str]]:
    return []


def sha256_file(path: str) -> str:
    return ""


def read_manifest(path: str) -> dict[str, str]:
    return {}


def check(manifest_path: str = MANIFEST_PATH, load: bool = True) -> list[str]:
    return ["not implemented"]


def write_manifest(manifest_path: str = MANIFEST_PATH) -> list[str]:
    return []


def main(argv: list[str] | None = None) -> int:
    return 1
