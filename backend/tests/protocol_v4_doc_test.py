"""
Structure, registry and signature checks for confirmation protocol v4 (07-02, SEL-01).

These tests read only the Markdown draft; they never touch a scorer, a log or any FRESH data.
"""

from __future__ import annotations

import re

import pandas as pd
import pytest

import protocol_v4_registry as reg

REQUIRED_SECTIONS = (
    "In plain English",
    "Status and supersession",
    "Anti-peeking statement for this draft",
    "What v4 changes and what it keeps",
    "Retirement of the 2026-11-24 run",
    "Read 1",
    "Read 2 (conditional re-test)",
    "Evidence bases",
    "Conductor in the headline",
    "Selection rule",
    "ABLATION design and veto criteria",
    "TEST design and veto criterion",
    "Permitted changes to frozen evaluation code",
    "Live-system check",
    "Owner items",
    "Registered values (machine-checked)",
    "Sign-off",
    "What happens by default if unsigned",
    "Change log",
)
OWNER_ITEM_COUNT = 11
OWNER_BLOCK_LABELS = ("Options", "Drafter's recommendation", "If the owner does nothing")


@pytest.fixture(scope="module")
def text() -> str:
    return reg.DRAFT_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def registry() -> dict[str, str]:
    return reg.parse_registry(reg.DRAFT_PATH)


def _h2_headings(text: str) -> list[str]:
    return [line[3:].strip() for line in text.splitlines() if line.startswith("## ")]


def _section(text: str, heading: str) -> str:
    """Body of the `## heading` section, up to the next `## ` heading."""
    lines = text.splitlines()
    start = lines.index(f"## {heading}") + 1
    body: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        body.append(line)
    return "\n".join(body)


def _whole_days(start: pd.Timestamp, end: pd.Timestamp) -> int:
    return (end - start).days


# ---------------------------------------------------------------- structure


def test_first_h2_heading_is_plain_english(text):
    assert _h2_headings(text)[0] == "In plain English"


def test_every_required_section_is_present_and_in_order(text):
    headings = _h2_headings(text)
    for name in REQUIRED_SECTIONS:
        assert name in headings, f"missing section: {name}"
    positions = [headings.index(name) for name in REQUIRED_SECTIONS]
    assert positions == sorted(positions), "sections are out of order"


def test_plain_english_section_is_six_to_ten_sentences(text):
    body = " ".join(_section(text, "In plain English").split())
    sentences = re.split(r'(?<=[.!?])\s+(?=["A-Z`])', body)
    assert 6 <= len(sentences) <= 10, f"{len(sentences)} sentences"


def test_draft_says_it_is_not_in_force_and_v3_governs(text):
    status = _section(text, "Status and supersession")
    assert "not in force until signed" in status.lower()
    assert "confirmation_protocol_v3_per_city.md" in status
    assert "2026-11-24T00:00:00Z" in status


def test_draft_points_at_v3_and_names_the_amended_decisions(text):
    assert re.search(r"confirmation_protocol_v3_per_city\.md", text)
    changes = _section(text, "What v4 changes and what it keeps")
    assert "decision 5" in changes and "decision 8" in changes


def test_anti_peeking_statement_names_the_fresh_start(text):
    statement = _section(text, "Anti-peeking statement for this draft")
    assert "2026-09-30" in statement
    assert "no predicted-versus-truth outcome" in statement.lower()


def test_retirement_section_names_the_retired_dates(text):
    retirement = _section(text, "Retirement of the 2026-11-24 run")
    for needle in ("2026-11-24T00:00:00Z", "2026-11-17T00:00:00Z", "2026-09-28..2026-11-16"):
        assert needle in retirement
    assert "no outcome under those dates will be computed" in retirement


def test_read2_says_plainly_it_is_not_independent(text):
    read2 = _section(text, "Read 2 (conditional re-test)")
    assert "not independent" in read2


def test_selection_rule_carries_the_worked_example(text):
    rule = _section(text, "Selection rule")
    for needle in ("1257.8", "1375.8", "1525.4", "1236.8", "26.98", "no pick"):
        assert needle in rule


def test_each_owner_item_has_options_recommendation_and_default(text):
    owner = _section(text, "Owner items")
    blocks = re.split(r"(?m)^### ", owner)[1:]
    assert len(blocks) == OWNER_ITEM_COUNT
    for index, block in enumerate(blocks, start=1):
        assert block.startswith(f"O{index}."), f"owner item {index} is out of order"
        for label in OWNER_BLOCK_LABELS:
            assert label in block, f"O{index} lacks {label!r}"


def test_o4_mentions_the_austin_energy_input(text):
    owner = _section(text, "Owner items")
    o4 = re.split(r"(?m)^### ", owner)[4]
    assert "Austin Energy" in o4 and "100 degrees C" in o4


def test_sign_off_table_lists_every_owner_item(text):
    sign_off = _section(text, "Sign-off")
    for index in range(1, OWNER_ITEM_COUNT + 1):
        assert re.search(rf"(?m)^\| O{index} \|", sign_off), f"O{index} missing from the sign-off table"


def test_draft_signature_block_is_left_blank(text):
    # The signing copy is the signed record; the draft's own block stays as drafted (v3 convention).
    assert reg.signature(reg.DRAFT_PATH) == {"name": None, "signature": None, "date": None}
    assert not reg.is_signed(reg.DRAFT_PATH)


# ---------------------------------------------------------------- registry


def test_registry_has_every_required_key(registry):
    missing = [key for key in reg.REQUIRED_KEYS if key not in registry]
    assert not missing, f"missing registry keys: {missing}"


def test_registry_has_one_row_per_ablation_variant(registry):
    variants = reg.as_list(registry["ablation.variants"])
    assert len(variants) == 6
    assert registry["ablation.control"] in variants
    for name in variants:
        row = registry[f"ablation.variant.{name}"]
        fields = dict(part.split("=", 1) for part in row.split(";"))
        assert set(fields) == {"diameter_m", "resistance_ac", "max_temp_c", "elevation_m", "cities"}
        for numeric in ("diameter_m", "resistance_ac", "max_temp_c", "elevation_m"):
            assert float(fields[numeric]) > 0
        assert fields["cities"] == "all" or fields["cities"] == "AUSTIN"
    extra = {key for key in registry if key.startswith("ablation.variant.")} - {
        f"ablation.variant.{name}" for name in variants
    }
    assert not extra, f"variant rows not listed in ablation.variants: {extra}"


def test_every_instant_is_utc_with_a_trailing_z(registry):
    for key in reg.TIMESTAMP_KEYS:
        value = registry[key]
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value), f"{key}={value!r}"
        assert reg.as_timestamp(value).tzinfo is not None


def test_as_timestamp_refuses_a_missing_z():
    with pytest.raises(ValueError):
        reg.as_timestamp("2026-11-01T00:00:00")
    with pytest.raises(ValueError):
        reg.as_timestamp("2026-11-01T00:00:00+00:00")


def test_fetch_windows_are_calendar_dates(registry):
    for key in reg.DATE_KEYS:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", registry[key]), f"{key}={registry[key]!r}"
    assert registry["read1.fetch_end"] < registry["read2.fetch_end"]
    assert registry["read1.fetch_start"] == registry["read2.fetch_start"]


def test_slot_arithmetic_matches_four_slots_per_whole_day(registry):
    fresh_start = reg.as_timestamp(registry["fresh_basis_start"])
    for read in ("read1", "read2"):
        cutoff = reg.as_timestamp(registry[f"{read}.cutoff"])
        assert int(registry[f"{read}.slots_per_city"]) == reg.SLOTS_PER_DAY * _whole_days(fresh_start, cutoff)
    assert int(registry["read1.slots_per_city"]) == 100
    assert int(registry["read2.slots_per_city"]) == 128
    test_days = _whole_days(
        reg.as_timestamp(registry["test.window_start"]),
        reg.as_timestamp(registry["test.window_end_exclusive"]),
    )
    assert int(registry["test.slots_per_city"]) == reg.SLOTS_PER_DAY * test_days == 784
    validation_days = _whole_days(
        reg.as_timestamp(registry["ablation.validation_start"]),
        reg.as_timestamp(registry["ablation.validation_end_exclusive"]),
    )
    assert int(registry["ablation.validation_rows_per_city"]) == reg.SLOTS_PER_DAY * validation_days == 784


def test_date_ordering(registry):
    for read in ("read1", "read2"):
        assert reg.as_timestamp(registry[f"{read}.cutoff"]) < reg.as_timestamp(registry[f"{read}.instant"])
    assert reg.as_timestamp(registry["power_systems_deadline"]) < reg.as_timestamp(registry["read1.instant"])
    assert registry["read2.cutoff"] == registry["read1.instant"]
    assert registry["model_freeze"] == registry["read1.instant"]
    assert reg.as_timestamp(registry["read1.instant"]) < reg.as_timestamp(registry["read2.instant"])
    assert reg.as_timestamp(registry["read2.instant"]) < reg.as_timestamp(registry["v3_retired_instant"])
    assert reg.as_timestamp(registry["fresh_basis_start"]) == reg.as_timestamp(registry["test.window_end_exclusive"])
    assert reg.as_timestamp(registry["ablation.validation_end_exclusive"]) == reg.as_timestamp(
        registry["refit.fit_end_exclusive"]
    )


def test_registered_rule_values(registry):
    assert registry["protocol_version"] == "v4"
    assert registry["amends"] == "confirmation_protocol_v3_per_city.md"
    assert float(registry["rule.relative_margin_fraction"]) == pytest.approx(0.02)
    assert int(registry["rule.family_size"]) == 9
    assert int(registry["rule.consistency_min_cities"]) == 3
    assert reg.as_list(registry["rule.block_lengths"]) == ["1", "4", "8", "28"]
    assert reg.as_list(registry["rule.tie_order"]) == [
        "ml_wind_corrected",
        "ml_cooling_corrected",
        "reference_ml_refit_24h",
    ]
    assert registry["read2.runs_only_if"] == "read1_no_pick"


def test_registry_encodes_the_owner_o4_choice(registry):
    # Signed O4 (custom): AUSTIN only switches, to Drake ACSR at 100 C; elevation and azimuth stay at
    # the model defaults. The rows must agree with each other and with the Drake-100 ablation variant.
    assert registry["power_systems.partial_answers"] == "custom_switch_austin_drake_100c"
    assert reg.as_list(registry["power_systems.switch_cities"]) == ["AUSTIN"]
    assert reg.as_list(registry["refit.cities"]) == ["AUSTIN"]
    assert registry["test.rescore_gate"] == "before_read1_run"
    austin = dict(part.split("=", 1) for part in registry["power_systems.austin_config"].split(";"))
    assert set(austin) == {"diameter_m", "resistance_ac", "max_temp_c", "elevation_m", "line_azimuth", "cities"}
    assert austin["cities"] == "AUSTIN"
    assert float(austin["max_temp_c"]) == 100.0
    drake_100 = dict(part.split("=", 1) for part in registry["ablation.variant.Drake-100"].split(";"))
    for field in ("diameter_m", "resistance_ac", "max_temp_c", "elevation_m"):
        assert float(austin[field]) == float(drake_100[field]), field


def test_registry_rejects_a_duplicate_key(tmp_path):
    doc = tmp_path / "dup.md"
    doc.write_text(
        f"{reg.REGISTRY_HEADING}\n\n| Key | Value |\n|---|---|\n| `a` | `1` |\n| `a` | `2` |\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate"):
        reg.parse_registry(doc)


def test_signature_parser_reads_filled_and_blank_blocks(tmp_path):
    blank = tmp_path / "blank.md"
    blank.write_text(
        "- Project owner (name): ______\n- Signature: ______\n- Date (UTC): ______\n", encoding="utf-8"
    )
    assert reg.signature(blank) == {"name": None, "signature": None, "date": None}
    assert not reg.is_signed(blank)
    filled = tmp_path / "filled.md"
    filled.write_text(
        "- Project owner (name): Ada Lovelace\n- Signature: Ada Lovelace\n- Date (UTC): 2026-11-02\n",
        encoding="utf-8",
    )
    assert reg.signature(filled)["name"] == "Ada Lovelace"
    assert reg.signature(filled)["date"] == "2026-11-02"
    assert reg.is_signed(filled)
    assert not reg.is_signed(tmp_path / "missing.md")


# ---------------------------------------------------------------- signing copy


@pytest.fixture(scope="module")
def signing_text() -> str:
    return reg.SIGNING_COPY_PATH.read_text(encoding="utf-8")


def _sign_off_rows(signing_text: str) -> dict[int, str]:
    rows: dict[int, str] = {}
    for line in _section(signing_text, "Sign-off").splitlines():
        match = re.match(r"^\| O(\d+) \| (?:[^|]+) \| (.*) \|$", line)
        if match:
            rows[int(match.group(1))] = match.group(2).strip()
    return rows


def test_signing_copy_exists_and_is_signed():
    assert reg.SIGNING_COPY_PATH.exists()
    assert reg.is_signed(reg.SIGNING_COPY_PATH)
    parsed = reg.signature(reg.SIGNING_COPY_PATH)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", parsed["date"]), parsed
    assert parsed["name"] == parsed["signature"]


def test_signing_copy_registry_equals_the_drafts(registry):
    assert reg.parse_registry(reg.SIGNING_COPY_PATH) == registry


def test_signing_copy_banner_says_signed_and_names_the_signer(signing_text):
    parsed = reg.signature(reg.SIGNING_COPY_PATH)
    banner = signing_text.split("## In plain English")[0]
    assert f"Signed {parsed['date']} by the project owner (`{parsed['name']}`" in banner
    assert "SIGNING COPY" in banner


def test_every_signing_copy_sign_off_row_has_a_chosen_option(signing_text):
    rows = _sign_off_rows(signing_text)
    assert sorted(rows) == list(range(1, OWNER_ITEM_COUNT + 1))
    date = reg.signature(reg.SIGNING_COPY_PATH)["date"]
    for number, chosen in rows.items():
        assert chosen, f"O{number} has no option chosen"
        assert f"(selected {date})" in chosen, f"O{number} lacks its selection date"


def test_signing_copy_o4_row_records_the_custom_austin_choice(signing_text):
    o4 = _sign_off_rows(signing_text)[4]
    assert "AUSTIN" in o4 and "100 degrees C" in o4 and "Drake" in o4
    assert "before read 1 is run" in o4
    assert not o4.startswith(("A:", "B:", "C:")), "O4 is the owner's custom choice, not A, B or C"


def test_signing_copy_text_matches_the_draft_apart_from_the_signing_edits(text, signing_text):
    # Same body from "In plain English" through the Sign-off table: the signing copy is the final draft text.
    def body(doc: str) -> str:
        start = doc.index("## In plain English")
        end = doc.index("## Sign-off")
        return doc[start:end]

    assert body(text) == body(signing_text)


def test_draft_points_at_the_signing_copy_and_says_signed(text):
    banner = text.split("## In plain English")[0]
    assert "confirmation_protocol_v4_early_selection_SIGNING_COPY.md" in banner
    parsed = reg.signature(reg.SIGNING_COPY_PATH)
    assert f"Signed {parsed['date']} by the project owner (`{parsed['name']}`" in banner
    assert f"| {parsed['date']} (signed) |" in _section(text, "Change log")


def test_o4_block_records_the_owner_selection_and_the_read1_wording(text):
    o4 = re.split(r"(?m)^### ", _section(text, "Owner items"))[4]
    assert "Owner's selection" in o4
    assert "04=switch austin based on given answers" in o4
    assert "before read 1 is run" in o4
    assert "900 m and 173.15 degrees" in o4
    assert "CORPUS_CHRISTI, MIDLAND and EL_PASO stay on the model-default Drake 75 degrees C" in o4


def test_test_section_says_before_read_1_is_run(text):
    section = _section(text, "TEST design and veto criterion")
    assert "before read 1 is run" in section
    assert "re-scored under them before the instant" not in section
