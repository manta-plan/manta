# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Settings naming part of a record, checked against a stored toy network."""

import pytest

pytest.importorskip("pypsa", reason="reading a record needs datarecord")

from playbook_library.datarecord_helpers import record_contents
from playbook_library.playbooks import library_playbooks
from playbook_library.tests.networks import new_zoned_network
from playbook_library.tests.test_playbooks import as_the_backend_sees_it, with_its_blocks_imported


@pytest.mark.parametrize("as_seen", [as_the_backend_sees_it, with_its_blocks_imported])
@pytest.mark.parametrize(
    ("bus", "problems"),
    [
        ("zone", []),
        (
            "busmap_5",
            [
                ("expansion_overnight", "aggregation", "bus"),
                ("dispatch", "aggregation", "bus"),
            ],
        ),
    ],
)
def test_aggregation_names_are_checked_against_the_record_and_the_time_partition(
    as_seen, bus, problems, store_record
):
    record = record_contents(store_record(new_zoned_network(), "zoned"), [])
    default_config = library_playbooks()["cluster-expand-dispatch"].default_config
    aggregation = {"snapshot": "seg_730", "bus": bus, "entity": "carrier"}
    config = {
        **default_config,
        "expansion_overnight": {"aggregation": aggregation},
        "dispatch": {
            **default_config["dispatch"],
            "aggregation": {**aggregation, "snapshot": None},
        },
    }
    issues = as_seen("cluster-expand-dispatch").find_issues(config, record)
    assert [issue.config_path for issue in issues] == problems
