# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Fixtures for the playbook tests: playbooks built from documents, and a runner that records."""

from collections.abc import Callable

import pytest

from playbook.blocks import BlockDescription, BlockDims, Catalogue
from playbook.blocks.tests.fakes import RecordingRunner
from playbook.playbooks.playbook import Playbook
from playbook.playbooks.syntax import PlaybookDoc
from playbook.playbooks.tests.specs import SPEC_LOADER
from playbook.playbooks.yaml_io import load_playbook, playbook_from_doc

BuildPlaybook = Callable[..., Playbook]


@pytest.fixture
def recording_runner() -> RecordingRunner:
    return RecordingRunner()


@pytest.fixture
def build_playbook() -> BuildPlaybook:
    """Build a playbook from a document written as a dict. A nested playbook is found by name."""

    def build(doc: dict, catalogue: Catalogue | None = None) -> Playbook:
        return playbook_from_doc(PlaybookDoc.model_validate(doc), SPEC_LOADER, catalogue)

    return build


def _settings(properties: dict, required: tuple[str, ...] = ()) -> dict:
    schema = {"type": "object", "properties": properties, "additionalProperties": False}
    return {**schema, "required": list(required)} if required else schema


def _described(name: str, schema: dict) -> BlockDescription:
    return BlockDescription.model_validate(
        {
            "name": name,
            "env": "spec",
            "module": f"spec_blocks:{name}",
            "dims": BlockDims(requires=frozenset({"snapshot"})),
            "config_schema": schema,
        }
    )


@pytest.fixture(scope="session")
def spec_catalogue() -> Catalogue:
    """Describe the blocks that the fixture playbooks name, as a catalogue does. None exists."""
    text = {"type": "string"}
    nullable = {"type": ["string", "null"]}
    aggregation = _settings(dict.fromkeys(("snapshot", "bus"), nullable))
    partitioning = _settings(
        {"method": text, "resolution": text, "property": text}, ("method", "resolution", "property")
    )
    expansion = _settings(
        {
            "method": {"enum": ["overnight", "myopic", "perfect"]},
            "aggregation": aggregation,
            "solver": text,
        }
    )
    blocks = [
        _described("timeseries_partitioning", partitioning),
        _described("capacity_expansion", expansion),
        _described("dispatch_optimisation", _settings({"aggregation": aggregation})),
    ]
    return Catalogue(blocks={block.name: block for block in blocks})


@pytest.fixture
def capacity_expansion(spec_catalogue: Catalogue) -> Playbook:
    return load_playbook("capacity_expansion", SPEC_LOADER, spec_catalogue)


@pytest.fixture
def expand_and_dispatch(spec_catalogue: Catalogue) -> Playbook:
    return load_playbook("expand_and_dispatch", SPEC_LOADER, spec_catalogue)
