"""The seams of the runtime, checked without a Prefect server.

What is pinned down here: how a step becomes a `run-block` dispatch, how the result
comes back across the container boundary, and how a failed block surfaces. The real
end-to-end path (API request to finished containers) lives in the backend's
integration suite.
"""

import json
from types import SimpleNamespace

import pytest
from blocks import DataRecord, describe_block
from blocks.tests.fakes import FakePassthrough

from manta_runtime import flows
from manta_runtime.flows import BLOCK_DEPLOYMENT, PrefectStepRunner, result_record_url


def _completed_state():
    return SimpleNamespace(
        is_completed=lambda: True, type=SimpleNamespace(value="COMPLETED")
    )


def _failed_state():
    return SimpleNamespace(
        is_completed=lambda: False, type=SimpleNamespace(value="FAILED")
    )


def test_the_result_record_lives_next_to_the_output_it_describes():
    assert (
        result_record_url("s3://manta/p/runs/1/cluster")
        == "s3://manta/p/runs/1/cluster.record.json"
    )


def test_a_step_is_dispatched_with_everything_spelled_out(monkeypatch):
    captured = {}

    def fake_run_deployment(name, parameters):
        captured.update(name=name, parameters=parameters)
        return SimpleNamespace(id="fr-1", state=_completed_state())

    monkeypatch.setattr(flows, "run_deployment", fake_run_deployment)
    monkeypatch.setattr(
        flows, "get_text", lambda url: json.dumps({"url": "s3://b/run/cluster.nc"})
    )

    result = PrefectStepRunner().run_block(
        describe_block(FakePassthrough),
        step_name="cluster",
        config={"label": "c"},
        record=DataRecord(url="s3://b/run/input.nc"),
        inputs={"source": DataRecord(url="s3://b/other.nc")},
        output_base="s3://b/run/cluster",
    )

    assert captured["name"] == BLOCK_DEPLOYMENT
    # Records cross as plain data, since the far side is a separate container.
    assert captured["parameters"] == {
        "block": "fake_passthrough",
        "step_name": "cluster",
        "config": {"label": "c"},
        "record": {"url": "s3://b/run/input.nc"},
        "inputs": {"source": {"url": "s3://b/other.nc"}},
        "output_base": "s3://b/run/cluster",
    }
    assert result.url == "s3://b/run/cluster.nc"


def test_the_result_comes_back_through_the_record_beside_the_output(monkeypatch):
    read_urls = []

    monkeypatch.setattr(
        flows,
        "run_deployment",
        lambda name, parameters: SimpleNamespace(id="fr-1", state=_completed_state()),
    )

    def fake_get_text(url):
        read_urls.append(url)
        return json.dumps({"url": "s3://b/run/expand.nc"})

    monkeypatch.setattr(flows, "get_text", fake_get_text)

    PrefectStepRunner().run_block(
        describe_block(FakePassthrough),
        step_name="expand",
        config={},
        record=DataRecord(url="s3://b/run/input.nc"),
        inputs={},
        output_base="s3://b/run/expand",
    )

    assert read_urls == ["s3://b/run/expand.record.json"]


def test_a_failed_block_run_names_the_step_and_the_flow_run(monkeypatch):
    monkeypatch.setattr(
        flows,
        "run_deployment",
        lambda name, parameters: SimpleNamespace(id="fr-broken", state=_failed_state()),
    )

    with pytest.raises(flows.BlockRunFailedError, match=r"'solve'.*FAILED.*fr-broken"):
        PrefectStepRunner().run_block(
            describe_block(FakePassthrough),
            step_name="solve",
            config={},
            record=DataRecord(url="in"),
            inputs={},
            output_base="out/solve",
        )
