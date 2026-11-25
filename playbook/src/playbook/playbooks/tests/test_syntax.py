# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from playbook.playbooks.syntax import BlockStepDoc, PlaybookDoc, PlaybookStepDoc
from playbook.playbooks.tests.specs import SPEC_PLAYBOOKS, spec_doc, spec_raw


def one_step(step: dict) -> dict:
    return {"name": "x", "steps": [step]}


def one_input(spec: dict) -> dict:
    return {"name": "x", "inputs": {"value": spec}, "steps": [{"id": "a", "block": "b"}]}


@pytest.mark.parametrize("name", SPEC_PLAYBOOKS)
def test_a_spec_playbook_survives_being_written_out_and_read_back(name):
    doc = spec_doc(name)
    written = doc.model_dump(mode="json", by_alias=True, exclude_unset=True)
    assert PlaybookDoc.model_validate(written) == doc


def test_a_written_out_step_keeps_the_if_and_with_keys():
    written = spec_doc("capacity_expansion").model_dump(by_alias=True, exclude_unset=True)
    assert written["steps"][0]["if"] == "${{ inputs.snapshot != null }}"
    assert written["steps"][0]["with"]["method"] == "resample"


def test_each_kind_of_step_is_told_apart():
    plan, partition, _ = spec_doc("expand_and_dispatch").steps
    assert isinstance(plan, PlaybookStepDoc)
    assert (plan.playbook, plan.inputs) == ("capacity_expansion", "inherit")
    assert isinstance(partition, BlockStepDoc)


@pytest.mark.parametrize(
    "doc",
    [
        pytest.param({"name": "x", "steps": []}, id="no-steps"),
        pytest.param({"name": "x", "steps": [{"id": "a", "block": "b"}], "extra": 1}, id="extra"),
        pytest.param(one_step({"id": "a"}), id="step-runs-nothing"),
        pytest.param(one_step({"id": "a", "block": "b", "playbook": "c"}), id="block-and-playbook"),
        pytest.param(one_step({"id": "a", "block": "b", "inputs": "inherit"}), id="block-inherit"),
        pytest.param(one_step({"id": "a", "block": "b", "when": {}}), id="unknown-step-key"),
        pytest.param(one_step({"id": "a-b", "block": "b"}), id="bad-id"),
        pytest.param(one_step({"name": "a", "block": "b"}), id="name-not-id"),
        pytest.param(one_step({"id": "a", "block": "b", "if": "inputs.x"}), id="if-not-expr"),
        pytest.param(
            one_step({"id": "a", "block": "b", "with": {"x": "at ${{ inputs.x }}"}}),
            id="with-partial-expr",
        ),
        pytest.param(
            one_step({"id": "a", "block": "b", "with": {"x": ["${{ matrix.x }}"]}}),
            id="with-unknown-root",
        ),
        pytest.param(
            one_step({"id": "a", "block": "b", "with": "${{ inputs.x }}"}), id="block-with-expr"
        ),
        pytest.param(
            one_step({"id": "a", "block": "b", "if": "${{ steps.c.record.x }}"}), id="if-steps"
        ),
        pytest.param(
            one_step({"id": "a", "block": "b", "with": {"x": ["${{ steps.c.record }}"]}}),
            id="with-steps",
        ),
        pytest.param(
            one_step({"id": "a", "playbook": "c", "with": "${{ steps.c.record }}"}),
            id="playbook-with-steps",
        ),
        pytest.param(one_input({"type": "text"}), id="unknown-input-type"),
        pytest.param(one_input({"default": 1}), id="input-without-type"),
        pytest.param(one_input({"type": "string", "default": 1}), id="string-default-number"),
        pytest.param(one_input({"type": "number", "default": "3"}), id="number-default-string"),
        pytest.param(one_input({"type": "number", "default": True}), id="number-default-bool"),
        pytest.param(one_input({"type": "boolean", "default": "yes"}), id="boolean-default-string"),
        pytest.param(one_input({"type": "choice", "options": ["a", True]}), id="choice-bool"),
        pytest.param(
            one_input({"type": "choice", "options": ["a"], "default": "b"}),
            id="choice-default-not-an-option",
        ),
        pytest.param(one_input({"type": "choice", "options": []}), id="choice-no-options"),
        pytest.param(
            one_input({"type": "string", "required": True, "default": "a"}),
            id="required-with-default",
        ),
        pytest.param(one_input({"type": "string", "required": "yes"}), id="required-not-bool"),
        pytest.param(
            {
                "name": "x",
                "inputs": {"a-b": {"type": "string"}},
                "steps": [{"id": "a", "block": "b"}],
            },
            id="bad-input-name",
        ),
    ],
)
def test_a_malformed_document_is_refused(doc):
    with pytest.raises(ValidationError):
        PlaybookDoc.model_validate(doc)


@pytest.mark.parametrize(
    ("spec", "field", "value"),
    [
        ({"type": "number", "default": 3}, "default", 3),
        ({"type": "choice", "options": [1, 2.5, "a"], "default": 1}, "options", [1, 2.5, "a"]),
    ],
)
def test_an_input_keeps_its_values_as_written(spec, field, value):
    written = PlaybookDoc.model_validate(one_input(spec)).model_dump(mode="json")
    assert written["inputs"]["value"][field] == value


@pytest.mark.parametrize("name", SPEC_PLAYBOOKS)
def test_a_spec_playbook_fits_the_document_schema(name):
    Draft202012Validator(PlaybookDoc.model_json_schema()).validate(spec_raw(name))
