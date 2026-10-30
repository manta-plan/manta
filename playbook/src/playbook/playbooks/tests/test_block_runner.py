# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The seam between a playbook and whatever actually runs its blocks.

An orchestrator plugs in a `BlockRunner` and receives one fully spelled-out block
invocation at a time; nothing else about running a playbook changes. These tests
drive the executor with a recording runner, exactly the way Manta's own runner is
driven, so the contract an orchestrator relies on is pinned down here.
"""

from playbook.blocks.tests.fakes import (
    FakeNeedsUpstream,
    FakePassthrough,
    RecordingRunner,
)
from playbook.playbooks.execution import execute_playbook
from playbook.playbooks.playbook import Playbook


def test_every_step_reaches_the_runner_with_everything_spelled_out(initial_record):
    pb = Playbook(name="p")
    cluster = pb.add("cluster", FakePassthrough)
    pb.add("dispatch", FakeNeedsUpstream, inputs={"source": cluster.output})

    runner = RecordingRunner()
    result = execute_playbook(
        pb,
        initial_record,
        {"cluster": {"label": "c"}, "dispatch": {}},
        runner=runner,
    )

    first, second = runner.calls
    assert first["block"] == "fake_passthrough"
    assert first["step_name"] == "cluster"
    assert first["config"] == {"label": "c"}
    assert first["record"] is initial_record

    # The next step receives the record the runner returned for the previous one,
    # and the wired input points at that same result.
    assert second["record"].url == "root/cluster"
    assert second["inputs"] == {"source": second["record"]}
    assert result.url == "root/cluster/dispatch"


def test_a_nested_playbooks_inner_config_reaches_its_steps(initial_record):
    inner = Playbook(name="inner")
    inner.add("leaf", FakePassthrough)

    outer = Playbook(name="outer")
    outer.add_playbook("regional", inner)

    runner = RecordingRunner()
    execute_playbook(
        outer,
        initial_record,
        {"regional": {"leaf": {"label": "deep"}}},
        runner=runner,
    )

    assert runner.calls[0]["config"] == {"label": "deep"}


def test_an_input_wired_into_a_nested_playbook_reaches_the_inner_step(initial_record):
    inner = Playbook(name="inner")
    inner.add("leaf", FakeNeedsUpstream)

    outer = Playbook(name="outer")
    upstream = outer.add("upstream", FakePassthrough)
    outer.add_playbook("regional", inner, inputs={"leaf.source": upstream.output})

    runner = RecordingRunner()
    execute_playbook(
        outer,
        initial_record,
        {"upstream": {}, "regional": {"leaf": {}}},
        runner=runner,
    )

    assert runner.calls[1]["inputs"]["source"].url == "root/upstream"
