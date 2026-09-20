# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""The playbooks that ship with the library, found and read without PyPSA.

Anything driving Manta - the backend, a UI - lists playbooks from here, in an
environment that cannot import the blocks they name. So these tests only read
documents; actually resolving the blocks is covered by the pypsa-marked tests.
"""

from playbooks.library import library_playbooks


def test_the_library_ships_the_cluster_expand_dispatch_playbook():
    playbooks = library_playbooks()
    assert "cluster-expand-dispatch" in playbooks

    doc = playbooks["cluster-expand-dispatch"].doc
    assert [step.name for step in doc.steps] == [
        "cluster",
        "expansion_overnight",
        "expansion_myopic",
        "dispatch",
    ]


def test_a_library_playbook_comes_with_sensible_default_settings():
    entry = library_playbooks()["cluster-expand-dispatch"]
    assert entry.default_config["globals"]["expansion_mode"] == "overnight"
    # Every step has somewhere for its settings, so a user starts from a complete
    # document rather than a blank page.
    assert {step.name for step in entry.doc.steps} <= set(entry.default_config)
