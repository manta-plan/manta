"""The transport between the orchestrator and a block's own container.

`run-block` is what executes inside that container, and `PrefectStepRunner` is
what dispatches at it. Both are exercised without Prefect infrastructure: the
flow through its undecorated function, the runner with `run_deployment` stubbed.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from blocks.core import BlockDims, ConfigSchema, DataRecord, MantaBlock
from blocks.registry import BlockDescription, BlockSpec, register

from manta_runtime import flows
from manta_runtime.flows import BLOCK_DEPLOYMENT, BlockRunFailedError, PrefectStepRunner


class _FakeConfig(ConfigSchema):
    label: str = ""
    source: DataRecord | None = None


@register("runtime_fake")
class _RuntimeFake(MantaBlock[_FakeConfig]):
    """Records what it was given, so the transport can be checked end to end."""

    ENV = "default"
    CONFIG = _FakeConfig
    DIMS = BlockDims()
    INPUTS = frozenset({"source"})

    def run(self, record: DataRecord, output_base: str) -> DataRecord:
        wired = self.config.source.url if self.config.source else "-"
        return DataRecord(url=f"{output_base}|{record.url}|{self.config.label}|{wired}")


def _spec(name: str = "runtime_fake") -> BlockSpec:
    return BlockSpec(BlockDescription(name=name, env="default", module="tests:_RuntimeFake"))


def _completed(result: dict):
    state = SimpleNamespace(
        is_completed=lambda: True, result=lambda: result, type=SimpleNamespace(value="COMPLETED")
    )
    return SimpleNamespace(id="flow-run-id", state=state)


def test_the_block_flow_runs_the_named_block_with_its_config_and_inputs() -> None:
    # When: the flow's own body, as it runs inside the block's container
    result = flows.run_block.fn(
        block="runtime_fake",
        step_name="cluster",
        config={"label": "tidy"},
        record={"url": "s3://bucket/in.nc"},
        inputs={"source": {"url": "s3://bucket/earlier.nc"}},
        output_base="s3://bucket/steps/cluster",
    )

    # Then: the record, the settings and the wired input all arrived, and the
    # result comes back as plain data, ready to cross a process boundary.
    assert result == {
        "url": "s3://bucket/steps/cluster|s3://bucket/in.nc|tidy|s3://bucket/earlier.nc"
    }


def test_the_block_flow_accepts_a_step_with_nothing_wired_into_it() -> None:
    # When
    result = flows.run_block.fn(
        block="runtime_fake",
        step_name="cluster",
        config={},
        record={"url": "in.nc"},
        inputs=None,
        output_base="out/cluster",
    )

    # Then
    assert result == {"url": "out/cluster|in.nc||-"}


def test_a_step_is_dispatched_at_the_block_deployment_fully_spelled_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    dispatch = MagicMock(return_value=_completed({"url": "s3://bucket/steps/cluster.nc"}))
    monkeypatch.setattr(flows, "run_deployment", dispatch)

    # When
    result = PrefectStepRunner().run_block(
        _spec(),
        step_name="cluster",
        config={"label": "tidy"},
        record=DataRecord(url="s3://bucket/in.nc"),
        inputs={"source": DataRecord(url="s3://bucket/earlier.nc")},
        output_base="s3://bucket/steps/cluster",
    )

    # Then: one deployment for every block, with the block named as a parameter,
    # and everything crossing as plain data.
    assert dispatch.call_args.kwargs["name"] == BLOCK_DEPLOYMENT
    assert dispatch.call_args.kwargs["parameters"] == {
        "block": "runtime_fake",
        "step_name": "cluster",
        "config": {"label": "tidy"},
        "record": {"url": "s3://bucket/in.nc"},
        "inputs": {"source": {"url": "s3://bucket/earlier.nc"}},
        "output_base": "s3://bucket/steps/cluster",
    }
    assert result == DataRecord(url="s3://bucket/steps/cluster.nc")


def test_a_step_that_did_not_complete_fails_the_playbook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a step whose flow run ended badly
    crashed = SimpleNamespace(
        id="flow-run-id",
        state=SimpleNamespace(is_completed=lambda: False, type=SimpleNamespace(value="CRASHED")),
    )
    monkeypatch.setattr(flows, "run_deployment", MagicMock(return_value=crashed))

    # When/Then: the error says which step, which block, and where to look
    with pytest.raises(BlockRunFailedError) as exc_info:
        PrefectStepRunner().run_block(
            _spec(),
            step_name="cluster",
            config={},
            record=DataRecord(url="in.nc"),
            inputs={},
            output_base="out/cluster",
        )
    message = str(exc_info.value)
    assert "cluster" in message
    assert "runtime_fake" in message
    assert "CRASHED" in message
    assert "flow-run-id" in message


def test_a_step_with_no_state_at_all_fails_rather_than_returning_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    stateless = SimpleNamespace(id="flow-run-id", state=None)
    monkeypatch.setattr(flows, "run_deployment", MagicMock(return_value=stateless))

    # When/Then
    with pytest.raises(BlockRunFailedError, match="UNKNOWN"):
        PrefectStepRunner().run_block(
            _spec(),
            step_name="cluster",
            config={},
            record=DataRecord(url="in.nc"),
            inputs={},
            output_base="out/cluster",
        )
