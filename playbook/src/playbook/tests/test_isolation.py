# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The two boundaries this package is built around, checked rather than promised.

Both are easy to break by accident with a single convenient import, and neither
breaks anything visible when it happens - which is exactly why they are tested.
"""

import ast
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parent.parent

ORCHESTRATION = {"prefect", "docker", "kubernetes", "celery", "airflow", "manta"}
"""Nothing here may know what runs a block, or that Manta exists at all."""


def source_files() -> list[Path]:
    return sorted(PACKAGE_ROOT.rglob("*.py"))


def imported_roots(path: Path) -> set[str]:
    """The top-level module name of every import in `path`."""
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_there_are_source_files_to_check():
    # A broken path here would make every other test in this module pass vacuously.
    assert len(source_files()) > 5


@pytest.mark.parametrize("path", source_files(), ids=lambda p: p.name)
def test_nothing_imports_an_orchestration_tool(path: Path):
    # Running a block is a plain method call. What schedules that call lives outside
    # this package, behind the StepRunner protocol, and must stay there: it is what
    # lets a modeller test a block without any of Manta's infrastructure.
    assert not (imported_roots(path) & ORCHESTRATION)


@pytest.mark.parametrize(
    "path",
    [p for p in source_files() if "blocks" in p.relative_to(PACKAGE_ROOT).parts],
    ids=lambda p: p.name,
)
def test_the_block_layer_does_not_import_the_playbook_layer(path: Path):
    # A block library depends on `playbook.blocks` alone, so that half can become its
    # own project without anything having to be untangled first.
    imported = {
        node.module
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any(module.startswith("playbook.playbooks") for module in imported)
