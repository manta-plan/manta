# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Settings that name part of a record: checked against one, and offered from one."""

import json

import pytest
from pydantic import ValidationError

from playbook.blocks import RecordContents, record_schema
from playbook.blocks.record_refs import RECORD_MARKER, created_properties, referenced_dims
from playbook.blocks.tests.fakes import CreatesBusPropertyConfig, ReadsRecordConfig

RECORD = RecordContents(
    coordinates={"carrier": frozenset({"H2", "AC"})},
    properties={"bus": frozenset({"zone", "country"})},
)


@pytest.mark.parametrize(
    ("values", "valid"),
    [
        ({"by": "zone"}, True),
        ({"carriers": ["H2", "AC"]}, True),
        ({"by": "carrier"}, False),
        ({"carriers": ["H2", "gas"]}, False),
    ],
)
def test_a_setting_naming_part_of_the_record_is_checked_against_it(values, valid):
    if valid:
        ReadsRecordConfig.model_validate(values, context={"record": RECORD})
    else:
        with pytest.raises(ValidationError, match="choose from"):
            ReadsRecordConfig.model_validate(values, context={"record": RECORD})


def test_without_a_record_any_name_is_accepted():
    ReadsRecordConfig.model_validate({"by": "anything", "carriers": ["anything"]})


@pytest.mark.parametrize(
    ("field", "where", "options"),
    [("by", ("anyOf", 0), ["country", "zone"]), ("carriers", ("items",), ["AC", "H2"])],
)
def test_the_record_schema_offers_the_record_values_as_a_plain_enum(field, where, options):
    node = record_schema(ReadsRecordConfig.model_json_schema(), RECORD)["properties"][field]
    for key in where:
        node = node[key]
    assert node == {"type": "string", "enum": options}


@pytest.mark.parametrize("config", [ReadsRecordConfig, CreatesBusPropertyConfig])
def test_the_record_schema_leaves_no_marker_for_a_form_to_interpret(config):
    assert RECORD_MARKER in json.dumps(config.model_json_schema())
    assert RECORD_MARKER not in json.dumps(record_schema(config.model_json_schema(), RECORD))


def test_a_created_property_is_read_from_the_settings():
    schema = CreatesBusPropertyConfig.model_json_schema()
    assert list(created_properties(schema, {"name": "region"})) == [("bus", "region")]


@pytest.mark.parametrize(("kind", "dims"), [("coordinate", {"carrier"}), ("property", {"bus"})])
def test_the_dims_a_schema_refers_to_are_found_by_kind(kind, dims):
    assert referenced_dims(ReadsRecordConfig.model_json_schema(), kind) == dims
