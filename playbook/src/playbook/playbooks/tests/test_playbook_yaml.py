# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

from pathlib import Path

import pytest

from playbook.blocks.tests.fakes import FakePassthrough
from playbook.playbooks.playbook import Playbook
from playbook.playbooks.yaml_io import (
    PlaybookDoc,
    PlaybookLoadError,
    load_config,
    load_playbook,
    playbook_from_doc,
    playbook_to_doc,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_reading_a_playbook_gets_its_structure_and_wiring():
    pb = load_playbook(FIXTURES / "fake_playbook.yaml")

    assert pb.name == "fake-playbook"
    assert pb.initial_dims == frozenset({"investment_period"})
    assert [step.name for step in pb.steps] == ["cluster", "expand", "dispatch"]

    cluster, expand, dispatch = pb.steps
    assert cluster.block.name == "fake_adds_clustered"
    assert expand.block.name == "fake_passthrough"
    assert dispatch.block.name == "fake_needs_upstream"

    assert dispatch.when is not None
    assert dispatch.when.config == "globals.mode"
    assert dispatch.when.equals == "full"

    assert dispatch.inputs["source"].step == "expand"
    assert dispatch.inputs["source"].output == "output"


def test_the_settings_alongside_a_playbook_are_read_as_a_mapping_per_step():
    config = load_config(FIXTURES / "fake_config.yaml")
    assert config["globals"] == {"mode": "full"}
    assert config["cluster"] == {"label": "clustering"}


def test_from_yaml_matches_load_playbook():
    assert Playbook.from_yaml(FIXTURES / "fake_playbook.yaml").name == "fake-playbook"


def test_unknown_block_error_lists_available_blocks(tmp_path):
    yaml_path = tmp_path / "bad.yaml"
    yaml_path.write_text("name: bad\nsteps:\n  - name: a\n    block: not_a_real_block\n")
    with pytest.raises(PlaybookLoadError, match="not_a_real_block"):
        load_playbook(yaml_path)


def test_invalid_reference_syntax_is_rejected(tmp_path):
    yaml_path = tmp_path / "bad_ref.yaml"
    yaml_path.write_text(
        "name: bad-ref\n"
        "steps:\n"
        "  - name: a\n"
        "    block: fake_passthrough\n"
        "  - name: b\n"
        "    block: fake_needs_upstream\n"
        "    inputs:\n"
        "      source: not-a-valid-ref\n"
    )
    with pytest.raises(PlaybookLoadError, match="not-a-valid-ref"):
        load_playbook(yaml_path)


def test_malformed_top_level_document_is_rejected(tmp_path):
    yaml_path = tmp_path / "malformed.yaml"
    yaml_path.write_text("steps: not-a-list\n")  # no name, and steps is not a list
    with pytest.raises(PlaybookLoadError):
        load_playbook(yaml_path)


def test_a_step_must_be_either_a_block_or_a_playbook(tmp_path):
    yaml_path = tmp_path / "both.yaml"
    yaml_path.write_text(
        "name: both\nsteps:\n  - name: a\n    block: fake_passthrough\n    playbook: other.yaml\n"
    )
    with pytest.raises(PlaybookLoadError, match="Exactly one"):
        load_playbook(yaml_path)


def test_load_config_returns_empty_dict_for_empty_file(tmp_path):
    yaml_path = tmp_path / "empty.yaml"
    yaml_path.write_text("")
    assert load_config(yaml_path) == {}


def test_load_config_rejects_non_mapping_top_level(tmp_path):
    yaml_path = tmp_path / "list.yaml"
    yaml_path.write_text("- 1\n- 2\n")
    with pytest.raises(PlaybookLoadError):
        load_config(yaml_path)


# --- The document is also the form a playbook travels in ---


def test_a_playbook_survives_a_round_trip_through_its_document():
    original = load_playbook(FIXTURES / "fake_playbook.yaml")
    rebuilt = playbook_from_doc(playbook_to_doc(original))

    assert rebuilt.name == original.name
    assert rebuilt.initial_dims == original.initial_dims
    assert [s.name for s in rebuilt.steps] == [s.name for s in original.steps]
    assert [s.block.name for s in rebuilt.steps] == [s.block.name for s in original.steps]
    assert rebuilt.steps[2].inputs == original.steps[2].inputs
    assert rebuilt.steps[2].when == original.steps[2].when


def test_a_document_round_trips_as_json():
    original = load_playbook(FIXTURES / "fake_playbook.yaml")
    as_json = playbook_to_doc(original).model_dump(mode="json")
    rebuilt = playbook_from_doc(PlaybookDoc.model_validate(as_json))
    assert [s.name for s in rebuilt.steps] == [s.name for s in original.steps]


def test_a_reference_is_written_back_the_way_it_was_read():
    doc = playbook_to_doc(load_playbook(FIXTURES / "fake_playbook.yaml"))
    dispatch = next(step for step in doc.steps if step.name == "dispatch")
    assert dispatch.inputs["source"] == "${steps.expand.output}"


def test_a_nested_playbook_can_be_written_out_in_place():
    # This is what a browser sends: there is no file to point at.
    doc = PlaybookDoc.model_validate(
        {
            "name": "outer",
            "steps": [
                {
                    "name": "regional",
                    "playbook": {
                        "name": "inner",
                        "steps": [{"name": "leaf", "block": "fake_passthrough"}],
                    },
                }
            ],
        }
    )
    pb = playbook_from_doc(doc)
    assert pb.steps[0].playbook.name == "inner"
    assert pb.steps[0].playbook.steps[0].block.name == "fake_passthrough"


def test_a_nested_playbook_round_trips_in_place():
    outer = Playbook(name="outer")
    inner = Playbook(name="inner")
    inner.add("leaf", FakePassthrough)
    outer.add_playbook("regional", inner)

    rebuilt = playbook_from_doc(playbook_to_doc(outer))
    assert rebuilt.steps[0].playbook.steps[0].block.name == "fake_passthrough"


def test_an_editor_can_be_told_what_a_valid_document_looks_like():
    schema = PlaybookDoc.model_json_schema()
    # A playbook can contain a playbook, so the schema refers to itself by name
    # rather than being written out inline.
    playbook_schema = schema["$defs"]["PlaybookDoc"]
    assert set(playbook_schema["properties"]) == {"name", "initial_data", "steps"}
    assert set(schema["$defs"]["StepDoc"]["properties"]) == {
        "name",
        "block",
        "playbook",
        "when",
        "inputs",
    }
