"""
Parser for confirmation protocol v4's machine-checked registry and signature block (07-02).

Not a test module: the file name does not match the collected patterns in pytest.ini
(`test_*.py`, `*_test.py`, `*_TestSuite.py`). `protocol_v4_doc_test.py` imports it, and later
Phase 7 plans import it to compare code constants against the signed registry.

The registry is a two-column Markdown table under the heading `## Registered values
(machine-checked)`; every data row is `| `key` | `value` |`. Nothing here reads outcomes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DECISIONS_DIR = REPO_ROOT / "docs" / "data-science" / "decisions"
DRAFT_PATH = DECISIONS_DIR / "confirmation_protocol_v4_early_selection.md"
SIGNING_COPY_PATH = DECISIONS_DIR / "confirmation_protocol_v4_early_selection_SIGNING_COPY.md"

REGISTRY_HEADING = "## Registered values (machine-checked)"

# Instants, written YYYY-MM-DDTHH:MM:SSZ.
TIMESTAMP_KEYS = (
    "v3_retired_instant",
    "fresh_basis_start",
    "model_freeze",
    "power_systems_deadline",
    "read1.instant",
    "read1.cutoff",
    "read2.instant",
    "read2.cutoff",
    "ablation.train_end",
    "ablation.validation_start",
    "ablation.validation_end_exclusive",
    "test.window_start",
    "test.window_end_exclusive",
    "refit.fit_end_exclusive",
)

# Calendar dates, written YYYY-MM-DD (reconstruction fetch windows).
DATE_KEYS = (
    "read1.fetch_start",
    "read1.fetch_end",
    "read2.fetch_start",
    "read2.fetch_end",
)

REQUIRED_KEYS = (
    "protocol_version",
    "amends",
    "v3_retired_instant",
    "fresh_basis_start",
    "model_freeze",
    "power_systems_deadline",
    "read1.name",
    "read1.instant",
    "read1.cutoff",
    "read1.fetch_start",
    "read1.fetch_end",
    "read1.slots_per_city",
    "read1.family_alpha",
    "read2.name",
    "read2.instant",
    "read2.cutoff",
    "read2.fetch_start",
    "read2.fetch_end",
    "read2.slots_per_city",
    "read2.family_alpha",
    "read2.runs_only_if",
    "read2.models",
    "late.name",
    "rule.relative_margin_fraction",
    "rule.bar_scope",
    "rule.consistency_min_cities",
    "rule.family_size",
    "rule.block_lengths",
    "rule.n_resamples",
    "rule.tie_order",
    "rule.alternative_vs_default_bar",
    "ablation.train_end",
    "ablation.validation_start",
    "ablation.validation_end_exclusive",
    "ablation.train_rows_per_city",
    "ablation.validation_rows_per_city",
    "ablation.control",
    "ablation.variants",
    "ablation.veto_rule",
    "test.window_start",
    "test.window_end_exclusive",
    "test.slots_per_city",
    "test.veto_min_cities",
    "refit.methods",
    "refit.root",
    "refit.fit_end_exclusive",
    "power_systems.partial_answers",
    "live_check.runs_at_each_read",
)

SLOTS_PER_DAY = 4  # six-hourly valid times, hour % 6 == 0

_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_ROW_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*`([^`]*)`\s*\|\s*$")
_NAME_LINE = "- Project owner (name):"
_SIGNATURE_LINE = "- Signature:"
_DATE_LINE = "- Date (UTC):"


def parse_registry(path: Path | str = DRAFT_PATH) -> dict[str, str]:
    """Return {key: value} for every registry row in `path`.

    Raises ValueError when the registry heading is missing or a key appears twice.
    """
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == REGISTRY_HEADING:
            start = index + 1
            break
    if start is None:
        raise ValueError(f"{path}: heading {REGISTRY_HEADING!r} not found")
    registry: dict[str, str] = {}
    for line in lines[start:]:
        if line.startswith("## "):
            break
        match = _ROW_RE.match(line.strip())
        if match is None:
            continue
        key, value = match.group(1), match.group(2)
        if key in registry:
            raise ValueError(f"{path}: duplicate registry key {key!r}")
        registry[key] = value
    return registry


def as_timestamp(value: str) -> pd.Timestamp:
    """Parse a registered instant; the trailing Z (UTC) is required."""
    if not _TIMESTAMP_RE.match(value):
        raise ValueError(f"not a UTC instant of the form YYYY-MM-DDTHH:MM:SSZ: {value!r}")
    return pd.Timestamp(value)


def as_list(value: str) -> list[str]:
    """Split a comma-separated registered value."""
    return [item.strip() for item in value.split(",") if item.strip()]


def _clean(text: str) -> str | None:
    """Strip decoration; None when nothing but underscores and spaces is left."""
    cleaned = text.strip().strip("_").strip()
    return cleaned or None


def signature(path: Path | str = SIGNING_COPY_PATH) -> dict[str, str | None]:
    """Read the owner name, signature and date (UTC) from the sign-off block.

    Each value is None when its line holds only underscores (the blank block of the draft).
    The first occurrence of each line is used.
    """
    found: dict[str, str | None] = {"name": None, "signature": None, "date": None}
    seen: set[str] = set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        for prefix, field in (
            (_NAME_LINE, "name"),
            (_SIGNATURE_LINE, "signature"),
            (_DATE_LINE, "date"),
        ):
            if stripped.startswith(prefix) and field not in seen:
                seen.add(field)
                found[field] = _clean(stripped[len(prefix):])
    return found


def is_signed(path: Path | str = SIGNING_COPY_PATH) -> bool:
    """True when `path` exists and its name, signature and date lines are all filled."""
    path = Path(path)
    if not path.exists():
        return False
    parsed = signature(path)
    return all(parsed[field] is not None for field in ("name", "signature", "date"))
