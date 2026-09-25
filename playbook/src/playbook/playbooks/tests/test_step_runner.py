# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The seam between a playbook and whatever actually runs its blocks.

An orchestrator plugs in a `StepRunner` and receives one fully spelled-out block
invocation at a time; nothing else about running a playbook changes. These tests
drive the executor with a recording runner, exactly the way Manta's own runner is
driven, so the contract an orchestrator relies on is pinned down here.
"""

from playbook.blocks import BlockSpec, DataRecord
from playbook.blocks.tests.fakes import FakeNeedsUpstream, FakePassthrough
from playbook.playbooks.execution import execute_playbook
from playbook.playbooks.playbook import Playbook


class RecordingRunner:
    """Hands back made-up records, and keeps every call for the test to inspect."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def run_block(
        self,
        block: BlockSpec,
        *,
        step_name: str,
        config: dict,
        record: DataRecord,
        inputs: dict[str, DataRecord],
        output_base: str,
    ) -> DataRecord:
        self.calls.append(
            {
                "block": block.name,
                "step_name": step_name,
                "config": config,
                "record": record,
                "inputs": inputs,
                "output_base": output_base,
            }
        )
        return DataRecord(url=f"{output_base}.out")


def test_every_step_reaches_the_runner_with_everything_spelled_out(initial_record):
    pb = Playbook(name="p")
    cluster = pb.add("cluster", FakePassthrough)
    pb.add("dispatch", FakeNeedsUpstream, inputs={"source": cluster.output})

    runner = RecordingRunner()
    result = execute_playbook(
        pb,
        initial_record,
        {"cluster": {"label": "c"}, "dispatch": {}},
        output_prefix="s3://bucket/run",
        runner=runner,
    )

    first, second = runner.calls
    assert first["block"] == "fake_passthrough"
    assert first["step_name"] == "cluster"
    assert first["config"] == {"label": "c"}
    assert first["record"] is initial_record
    assert first["output_base"] == "s3://bucket/run/cluster"

    # The next step receives the record the runner returned for the previous one,
    # and the wired input points at that same result.
    assert second["record"].url == "s3://bucket/run/cluster.out"
    assert second["inputs"] == {"source": second["record"]}
    assert result.url == "s3://bucket/run/dispatch.out"


def test_nested_steps_write_under_their_nesting_steps_prefix(initial_record):
    inner = Playbook(name="inner")
    inner.add("leaf", FakePassthrough)

    outer = Playbook(name="outer")
    outer.add_playbook("regional", inner)

    runner = RecordingRunner()
    execute_playbook(
        outer,
        initial_record,
        {"regional": {"leaf": {}}},
        output_prefix="out",
        runner=runner,
    )

    assert runner.calls[0]["step_name"] == "leaf"
    assert runner.calls[0]["output_base"] == "out/regional/leaf"


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
        output_prefix="out",
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
        output_prefix="out",
        runner=runner,
    )

    leaf_call = runner.calls[1]
    assert leaf_call["step_name"] == "leaf"
    assert leaf_call["inputs"]["source"].url == "out/upstream.out"
