# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

import pytest

from playbook.playbooks.playbook import Playbook, PlaybookStep
from playbook.playbooks.schema import SCHEMA_PATH, schema_text
from playbook.playbooks.syntax import PlaybookDoc
from playbook.playbooks.tests.specs import FIXTURES, SPEC_LOADER, SPEC_PLAYBOOKS, spec_doc
from playbook.playbooks.yaml_io import (
    PlaybookLoadError,
    load_playbook,
    parse_doc,
    playbook_from_doc,
    playbook_to_doc,
)


def test_reading_a_playbook_gets_its_inputs_and_steps(capacity_expansion):
    assert capacity_expansion.name == "capacity_expansion"
    assert list(capacity_expansion.inputs) == [
        "snapshot",
        "bus",
        "resolution",
        "expansion_method",
        "solver",
    ]
    partition, expand = capacity_expansion.steps
    assert (partition.id, partition.block.name) == ("partition", "timeseries_partitioning")
    assert partition.if_ == "${{ inputs.snapshot != null }}"
    assert partition.with_["method"] == "resample"
    assert (expand.id, expand.block.name) == ("expand", "capacity_expansion")


def test_reading_a_playbook_fetches_the_playbooks_it_nests(expand_and_dispatch):
    plan = expand_and_dispatch.steps[0]
    assert isinstance(plan, PlaybookStep)
    assert (plan.playbook.name, plan.inherit) == ("capacity_expansion", True)


def test_from_yaml_reads_a_file(spec_catalogue):
    pb = Playbook.from_yaml(FIXTURES / "capacity_expansion.yaml", spec_catalogue)
    assert pb == load_playbook("capacity_expansion", SPEC_LOADER, spec_catalogue)


def test_a_block_known_nowhere_is_reported_as_a_load_error(build_playbook):
    with pytest.raises(PlaybookLoadError, match="step 'a'.*not_a_real_block"):
        build_playbook({"name": "x", "steps": [{"id": "a", "block": "not_a_real_block"}]})


def test_a_malformed_document_is_reported_as_a_load_error():
    with pytest.raises(PlaybookLoadError, match="invalid playbook bad.yaml"):
        parse_doc({"name": "x", "steps": [{"name": "a", "block": "b"}]}, source="bad.yaml")


@pytest.mark.parametrize("name", SPEC_PLAYBOOKS)
def test_a_playbook_survives_a_round_trip_through_its_document(name, spec_catalogue):
    original = load_playbook(name, SPEC_LOADER, spec_catalogue)
    written = playbook_to_doc(original).model_dump(mode="json", by_alias=True, exclude_unset=True)
    assert (
        playbook_from_doc(PlaybookDoc.model_validate(written), catalogue=spec_catalogue) == original
    )


def test_a_nested_playbook_is_written_out_in_place(expand_and_dispatch):
    written = expand_and_dispatch.to_doc().model_dump(by_alias=True, exclude_unset=True)
    plan = written["steps"][0]
    assert plan["inputs"] == "inherit"
    assert plan["playbook"] == spec_doc("capacity_expansion").model_dump(
        by_alias=True, exclude_unset=True
    )


def test_a_step_is_written_without_the_keys_it_leaves_unset(capacity_expansion):
    written = capacity_expansion.to_doc().model_dump(by_alias=True, exclude_unset=True)
    assert written["steps"][1] == {
        "id": "expand",
        "block": "capacity_expansion",
        "with": {
            "method": "${{ inputs.expansion_method }}",
            "aggregation": {"snapshot": "${{ inputs.snapshot }}", "bus": "${{ inputs.bus }}"},
            "solver": "${{ inputs.solver }}",
        },
    }


def test_committed_schema_matches_playbook_doc():
    assert SCHEMA_PATH.read_text() == schema_text()
