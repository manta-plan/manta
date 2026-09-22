# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Fetching the playbooks a playbook refers to.

A reference need not be a file: the loader is the seam a system keeping playbooks in
a database would replace, so the in-memory loader below has to work exactly as the
file one does.
"""

import pytest

import playbook.blocks.tests.fakes  # noqa: F401 - registers the blocks the documents below name
from playbook.playbooks.yaml_io import (
    LoadedPlaybook,
    PlaybookDoc,
    PlaybookLoadError,
    load_playbook,
    playbook_from_doc,
)


class InMemoryPlaybookLoader:
    """A loader backed by a dict, touching no files at all."""

    def __init__(self, docs: dict[str, PlaybookDoc]) -> None:
        self._docs = docs

    def load(self, locator: str) -> LoadedPlaybook:
        if locator not in self._docs:
            raise PlaybookLoadError(f"no playbook stored under {locator!r}")
        return LoadedPlaybook(key=locator, doc=self._docs[locator], loader=self)


def test_a_nested_playbook_can_come_from_somewhere_other_than_a_file():
    child = PlaybookDoc.model_validate(
        {"name": "child", "steps": [{"name": "inner", "block": "fake_passthrough"}]}
    )
    outer = PlaybookDoc.model_validate(
        {"name": "outer", "steps": [{"name": "regional", "playbook": "memory://child"}]}
    )

    pb = playbook_from_doc(outer, loader=InMemoryPlaybookLoader({"memory://child": child}))

    assert len(pb.steps) == 1
    assert pb.steps[0].playbook.name == "child"
    assert pb.steps[0].playbook.steps[0].block.name == "fake_passthrough"


def test_a_missing_nested_playbook_is_reported_clearly():
    outer = PlaybookDoc.model_validate(
        {"name": "outer", "steps": [{"name": "regional", "playbook": "memory://gone"}]}
    )
    with pytest.raises(PlaybookLoadError, match="memory://gone"):
        playbook_from_doc(outer, loader=InMemoryPlaybookLoader({}))


def test_a_playbook_that_refers_back_to_itself_is_reported_not_followed():
    # Two documents that include each other. Following the references would go on
    # until the process ran out of stack, so the loop is spotted first.
    a = PlaybookDoc.model_validate(
        {"name": "a", "steps": [{"name": "to_b", "playbook": "memory://b"}]}
    )
    b = PlaybookDoc.model_validate(
        {"name": "b", "steps": [{"name": "to_a", "playbook": "memory://a"}]}
    )
    loader = InMemoryPlaybookLoader({"memory://a": a, "memory://b": b})

    with pytest.raises(PlaybookLoadError, match="circular"):
        playbook_from_doc(a, loader=loader, _chain=("memory://a",))


def test_two_files_that_refer_to_each_other_are_reported_not_followed(tmp_path):
    (tmp_path / "a.yaml").write_text("name: a\nsteps:\n  - name: to_b\n    playbook: b.yaml\n")
    (tmp_path / "b.yaml").write_text("name: b\nsteps:\n  - name: to_a\n    playbook: a.yaml\n")

    with pytest.raises(PlaybookLoadError, match="circular"):
        load_playbook(tmp_path / "a.yaml")


def test_a_file_reference_is_resolved_next_to_the_playbook_that_made_it(tmp_path):
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "child.yaml").write_text(
        "name: child\nsteps:\n  - name: inner\n    block: fake_passthrough\n"
    )
    (tmp_path / "outer.yaml").write_text(
        "name: outer\nsteps:\n  - name: regional\n    playbook: nested/child.yaml\n"
    )

    pb = load_playbook(tmp_path / "outer.yaml")
    assert pb.steps[0].playbook.name == "child"


def test_the_same_playbook_used_twice_is_not_mistaken_for_a_loop(tmp_path):
    (tmp_path / "child.yaml").write_text(
        "name: child\nsteps:\n  - name: inner\n    block: fake_passthrough\n"
    )
    (tmp_path / "outer.yaml").write_text(
        "name: outer\n"
        "steps:\n"
        "  - name: first\n"
        "    playbook: child.yaml\n"
        "  - name: second\n"
        "    playbook: child.yaml\n"
    )

    pb = load_playbook(tmp_path / "outer.yaml")
    assert [step.name for step in pb.steps] == ["first", "second"]
