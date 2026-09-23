# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The transport between the orchestrator and a block's own container.

`run-block` is what executes inside that container, and `PrefectStepRunner` is
what dispatches at it. Both are exercised without Prefect infrastructure: the
flow through its undecorated function, the runner with `run_deployment` stubbed.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from playbook.blocks import Catalogue, DataRecord
from playbook.blocks.core import BlockDims, ConfigSchema, MantaBlock
from playbook.blocks.registry import BlockDescription, BlockSpec, register
from playbook.playbooks.yaml_io import PlaybookDoc, StepDoc

from runner import flows
from runner.config import UnknownEnvironmentError
from runner.flows import (
    BLOCK_DEPLOYMENT,
    BlockRunFailedError,
    PrefectStepRunner,
    catalogue_parameter,
    parse_catalogue_parameter,
    run_playbook,
)


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


def _spec(name: str = "runtime_fake", env: str = "default") -> BlockSpec:
    return BlockSpec(BlockDescription(name=name, env=env, module="tests:_RuntimeFake"))


@pytest.fixture(autouse=True)
def _env_images(monkeypatch: pytest.MonkeyPatch) -> None:
    """One image per block environment, as an installation configures them."""
    monkeypatch.setenv(
        "MANTA_ENV_IMAGES",
        "default=block-prefect-runtime:default,pypsa=block-prefect-runtime:pypsa",
    )


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


def test_the_block_flow_imports_the_job_containers_block_library_before_looking_anything_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A freshly started job container has imported nothing yet: MANTA_BLOCK_SOURCES
    # names the library, but only importing it registers the block being asked for.
    # Skipping this call is exactly the bug that left every run failing with
    # BlockNotRegisteredError once the block library became a separate package.
    load_sources = MagicMock()
    monkeypatch.setattr(flows, "load_block_sources", load_sources)

    flows.run_block.fn(
        block="runtime_fake",
        step_name="cluster",
        config={},
        record={"url": "in.nc"},
        inputs=None,
        output_base="out/cluster",
    )

    load_sources.assert_called_once_with()


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
    assert dispatch.call_args.kwargs["job_variables"] == {"image": "block-prefect-runtime:default"}
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


def test_a_step_runs_in_its_own_environments_image(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given two steps whose blocks declare different environments
    dispatch = MagicMock(return_value=_completed({"url": "out.nc"}))
    monkeypatch.setattr(flows, "run_deployment", dispatch)
    runner = PrefectStepRunner()

    # When each is dispatched
    for env in ("default", "pypsa"):
        runner.run_block(
            _spec(env=env),
            step_name="step",
            config={},
            record=DataRecord(url="in.nc"),
            inputs={},
            output_base="out/step",
        )

    # Then each went to the image its own environment names — which is what lets
    # two frameworks that cannot share a virtualenv appear in one playbook.
    assert [call.kwargs["job_variables"]["image"] for call in dispatch.call_args_list] == [
        "block-prefect-runtime:default",
        "block-prefect-runtime:pypsa",
    ]


def test_a_step_needing_an_unconfigured_environment_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a block declaring an environment this installation has no image for
    monkeypatch.setattr(flows, "run_deployment", MagicMock())

    # When/Then: it fails naming the environment and what to set, rather than
    # silently running the block in some other environment's image.
    with pytest.raises(UnknownEnvironmentError) as exc_info:
        PrefectStepRunner().run_block(
            _spec(env="julia"),
            step_name="step",
            config={},
            record=DataRecord(url="in.nc"),
            inputs={},
            output_base="out/step",
        )
    assert "julia" in str(exc_info.value)
    assert "MANTA_ENV_IMAGES" in str(exc_info.value)


# --- The catalogue crossing Prefect as a JSON string ---


def test_the_catalogue_parameter_round_trips():
    catalogue = Catalogue(
        blocks={
            "runtime_fake": BlockDescription(
                name="runtime_fake", env="default", module="tests.fakes:RuntimeFake"
            )
        }
    )

    encoded = catalogue_parameter(catalogue)

    # It must be a plain string: Prefect resolves any "$ref" inside a dict
    # parameter as its own block-document reference, and a catalogue of JSON
    # schemas is full of them.
    assert isinstance(encoded, str)
    assert parse_catalogue_parameter(encoded) == catalogue


# --- run-playbook: the orchestrator never imports a block library itself ---


def test_the_playbook_flow_resolves_every_block_purely_from_the_catalogue_parameter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a playbook naming a block that nothing in this process has registered
    # at all — the real situation for an orchestrator container, which never
    # installs a block library and knows blocks only through the catalogue it was
    # handed. Dispatch is stubbed so the block "runs" without a docker work pool.
    dispatch = MagicMock(return_value=_completed({"url": "out/cluster|root|tidy|-"}))
    monkeypatch.setattr(flows, "run_deployment", dispatch)

    catalogue = Catalogue(
        blocks={
            "catalogue_only_fake": BlockDescription(
                name="catalogue_only_fake", env="default", module="nowhere:NeverImported"
            )
        }
    )
    doc = PlaybookDoc(
        name="single-step", steps=[StepDoc(name="cluster", block="catalogue_only_fake")]
    )

    # When
    result = run_playbook.fn(
        playbook=doc.model_dump(mode="json"),
        config={"cluster": {"label": "tidy"}},
        record={"url": "root"},
        output_prefix="out",
        catalogue=catalogue_parameter(catalogue),
    )

    # Then: the block ran through the docker-pool transport, not in this process.
    assert result == {"url": "out/cluster|root|tidy|-"}
    assert dispatch.call_args.kwargs["parameters"]["block"] == "catalogue_only_fake"
