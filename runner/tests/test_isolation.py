# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The one boundary this package is built around, checked rather than promised.

Easy to break by accident with a single convenient import, which is exactly why
it is tested rather than only written down.
"""

import ast
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "src"

FORBIDDEN = {"manta", "playbook_library"}
"""`runner` is meant to be published so any block library's own author can reuse
it to run and test their playbooks without Manta. Depending on Manta's own
library — or on Manta itself — would make that a cycle. Prefect and Docker, by
contrast, are exactly what this package exists to wrap, so they are not checked
here (see playbook/tests/test_isolation.py for that boundary, one layer down)."""


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
    assert len(source_files()) > 2


@pytest.mark.parametrize("path", source_files(), ids=lambda p: p.name)
def test_nothing_imports_manta_or_a_block_library(path: Path):
    assert not (imported_roots(path) & FORBIDDEN)
