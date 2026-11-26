# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Fetching the playbooks a playbook refers to.

A reference need not be a file: the loader is the seam a block library or a database
replaces, so the in-memory loader has to work exactly as the file one does.
"""

import pytest

from playbook.playbooks.syntax import PlaybookDoc
from playbook.playbooks.tests.specs import InMemoryPlaybookLoader
from playbook.playbooks.yaml_io import PlaybookLoadError, load_playbook, playbook_from_doc

LEAF = "name: child\nsteps:\n  - id: inner\n    block: fake_passthrough\n"


def nesting(name: str, *locators: str) -> PlaybookDoc:
    steps = [{"id": f"step{index}", "playbook": locator} for index, locator in enumerate(locators)]
    return PlaybookDoc.model_validate({"name": name, "steps": steps})


def nesting_yaml(*locators: str) -> str:
    steps = "".join(
        f"  - id: step{index}\n    playbook: {locator}\n" for index, locator in enumerate(locators)
    )
    return f"name: outer\nsteps:\n{steps}"


def test_a_nested_playbook_can_come_from_somewhere_other_than_a_file():
    child = PlaybookDoc.model_validate(
        {"name": "child", "steps": [{"id": "inner", "block": "fake_passthrough"}]}
    )
    loader = InMemoryPlaybookLoader({"memory://child": child})

    pb = playbook_from_doc(nesting("outer", "memory://child"), loader=loader)

    assert pb.steps[0].playbook.steps[0].block.name == "fake_passthrough"
    assert pb.find_issues({}) == []


def test_a_missing_nested_playbook_is_reported_clearly():
    with pytest.raises(PlaybookLoadError, match="memory://gone"):
        playbook_from_doc(nesting("outer", "memory://gone"), loader=InMemoryPlaybookLoader({}))


def test_a_playbook_that_refers_back_to_itself_is_reported_not_followed():
    loader = InMemoryPlaybookLoader(
        {"memory://a": nesting("a", "memory://b"), "memory://b": nesting("b", "memory://a")}
    )
    with pytest.raises(PlaybookLoadError, match="circular"):
        load_playbook("memory://a", loader=loader)


def test_two_files_that_refer_to_each_other_are_reported_not_followed(tmp_path):
    (tmp_path / "a.yaml").write_text(nesting_yaml("b.yaml"))
    (tmp_path / "b.yaml").write_text(nesting_yaml("a.yaml"))

    with pytest.raises(PlaybookLoadError, match="circular"):
        load_playbook(tmp_path / "a.yaml")


def test_a_file_reference_is_resolved_next_to_the_playbook_that_made_it(tmp_path):
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "child.yaml").write_text(LEAF)
    (tmp_path / "outer.yaml").write_text(nesting_yaml("nested/child.yaml"))

    assert load_playbook(tmp_path / "outer.yaml").steps[0].playbook.name == "child"


@pytest.mark.parametrize(
    ("files", "start"),
    [
        pytest.param(
            {"playbooks/outer.yaml": nesting_yaml("../secret.yaml")},
            "playbooks/outer.yaml",
            id="one-step-out",
        ),
        pytest.param(
            {
                "playbooks/outer.yaml": nesting_yaml("nested/inner.yaml"),
                "playbooks/nested/inner.yaml": nesting_yaml("../../secret.yaml"),
            },
            "playbooks/outer.yaml",
            id="one-directory-at-a-time",
        ),
    ],
)
def test_a_reference_cannot_reach_outside_the_first_playbooks_directory(tmp_path, files, start):
    (tmp_path / "secret.yaml").write_text(LEAF)
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)

    with pytest.raises(PlaybookLoadError, match="points outside"):
        load_playbook(tmp_path / start)


def test_the_same_playbook_used_twice_is_not_mistaken_for_a_loop(tmp_path):
    (tmp_path / "child.yaml").write_text(LEAF)
    (tmp_path / "outer.yaml").write_text(nesting_yaml("child.yaml", "child.yaml"))

    pb = load_playbook(tmp_path / "outer.yaml")
    assert [step.id for step in pb.steps] == ["step0", "step1"]
