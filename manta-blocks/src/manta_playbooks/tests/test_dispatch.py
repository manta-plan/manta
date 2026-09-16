# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""Whether a step runs here or is handed to another environment.

Only the decision is checked. A real hand-off needs a running Prefect server and a
worker in the other environment, which is a manual check rather than a unit test.
"""

from manta_blocks import DataRecord
from manta_blocks.tests.fakes import FakePassthrough
from manta_playbooks import execution
from manta_playbooks.playbook import Playbook


def test_a_step_runs_here_by_default(initial_record, monkeypatch):
    def _fail_if_called(*args, **kwargs):
        raise AssertionError("nothing should have been handed off")

    monkeypatch.setattr(execution, "dispatch_block", _fail_if_called)

    pb = Playbook(name="p")
    pb.add("a", FakePassthrough)
    assert pb.run(initial_record, {"a": {"label": "a"}}).url == "root+a"


def test_a_step_is_handed_off_when_it_needs_another_environment(
    initial_record, monkeypatch
):
    captured = {}

    def _fake_dispatch_block(block, env, config, record, inputs):
        captured.update(block=block, env=env, config=config)
        return DataRecord(url=f"{record.url}+dispatched({block})")

    monkeypatch.setattr(execution, "dispatch_block", _fake_dispatch_block)
    monkeypatch.setattr(execution, "current_env", lambda: "some-other-env")

    pb = Playbook(name="p")
    pb.add("a", FakePassthrough)
    result = pb.run(initial_record, {"a": {"label": "a"}}, dispatch=True)

    assert captured["block"] == "fake_passthrough"
    assert captured["env"] == "default"
    assert result.url == "root+dispatched(fake_passthrough)"


def test_a_step_runs_here_when_it_is_already_the_right_environment(
    initial_record, monkeypatch
):
    def _fail_if_called(*args, **kwargs):
        raise AssertionError("nothing should have been handed off")

    monkeypatch.setattr(execution, "dispatch_block", _fail_if_called)
    monkeypatch.setattr(execution, "current_env", lambda: "default")

    pb = Playbook(name="p")
    pb.add("a", FakePassthrough)
    assert pb.run(initial_record, {"a": {"label": "a"}}, dispatch=True).url == "root+a"


def test_a_handed_off_step_is_addressed_by_its_deployment_name(monkeypatch):
    captured = {}

    def _fake_run_deployment(name, parameters):
        captured.update(name=name, parameters=parameters)

        class _Run:
            class state:
                @staticmethod
                def result():
                    return {"url": "elsewhere"}

        return _Run()

    monkeypatch.setattr(execution, "run_deployment", _fake_run_deployment)

    result = execution.dispatch_block(
        "fake_passthrough",
        "elsewhere",
        {"label": "x"},
        DataRecord(url="root"),
        {"source": DataRecord(url="other")},
    )

    assert captured["name"] == "run_block/fake_passthrough-elsewhere"
    # Records cross as plain data, since the far side is a separate process.
    assert captured["parameters"]["record"] == {"url": "root"}
    assert captured["parameters"]["inputs"] == {"source": {"url": "other"}}
    assert result.url == "elsewhere"
