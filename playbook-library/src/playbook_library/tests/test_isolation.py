# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""What this library is allowed to depend on.

Modelling code may use whatever it needs to do modelling. What it may not do is learn
how Manta runs it: a block that imports an orchestration tool no longer runs anywhere
but inside Manta, and can no longer be tested without it. The same check lives in the
framework next door, because both packages are written to stand alone.
"""

import ast
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parent.parent

ORCHESTRATION = {"prefect", "docker", "kubernetes", "celery", "airflow", "manta"}


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
    assert len(source_files()) > 5


@pytest.mark.parametrize("path", source_files(), ids=lambda p: p.name)
def test_no_block_imports_an_orchestration_tool(path: Path):
    assert not (imported_roots(path) & ORCHESTRATION)


def test_registering_the_blocks_does_not_import_them():
    # Importing this package must stay free of PyPSA: that is what lets a process
    # which cannot install a solver stack still list these blocks and read their
    # settings out of the catalogue.
    package_init = PACKAGE_ROOT / "__init__.py"
    assert "pypsa" not in imported_roots(package_init)
