# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The transport between the orchestrator and a block's own container.

`run-block` is what executes inside that container, and `PrefectBlockRunner` is
what dispatches at it. Both are exercised without Prefect infrastructure: the
flow through its undecorated function, the runner with `run_deployment` stubbed.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from datarecord import Revision
from playbook.blocks import Catalogue, RevisionRef
from playbook.blocks.core import BlockDims, ConfigSchema, MantaBlock
from playbook.blocks.registry import BlockDescription, BlockSpec, register
from playbook.blocks.tests.fakes import commit_root, commit_step, steps
from playbook.playbooks.yaml_io import PlaybookDoc, StepDoc

from runner import flows
from runner.config import UnknownEnvironmentError
from runner.flows import (
    BLOCK_DEPLOYMENT,
    BlockRunFailedError,
    BlockTimedOutError,
    PrefectBlockRunner,
    catalogue_parameter,
    parse_catalogue_parameter,
    run_playbook,
)

STORE = "s3://bucket/store"
REVISION_ID = "00000000-0000-0000-0000-000000000000"
EARLIER_ID = "00000000-0000-0000-0000-000000000001"
OUTPUT_ID = "00000000-0000-0000-0000-000000000002"


class _FakeConfig(ConfigSchema):
    label: str = ""
    source: RevisionRef | None = None


@register("runtime_fake")
class _RuntimeFake(MantaBlock[_FakeConfig]):
    """Records what it was given, so the transport can be checked end to end."""

    ENV = "default"
    CONFIG = _FakeConfig
    DIMS = BlockDims()
    INPUTS = frozenset({"source"})

    def run(self, base: Revision) -> Revision:
        wired = str(self.config.source.id) if self.config.source else "-"
        return commit_step(base, f"{self.config.label}|{wired}")


def _spec(name: str = "runtime_fake", env: str = "default") -> BlockSpec:
    return BlockSpec(BlockDescription(name=name, env=env, module="tests:_RuntimeFake"))


@pytest.fixture(autouse=True)
def _env_images(monkeypatch: pytest.MonkeyPatch) -> None:
    """One image per block environment, as an installation configures them."""
    monkeypatch.setenv(
        "MANTA_ENV_IMAGES",
        "default=block-prefect-runtime:default,pypsa=block-prefect-runtime:pypsa",
    )


@pytest.fixture
def root(tmp_path: Path) -> dict:
    """The revision a block flow runs on, as it arrives across a process boundary."""
    return commit_root(str(tmp_path / "store")).to_dict()


@pytest.fixture(autouse=True)
def published(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """The Prefect artifact API, which `run-block` publishes its output revision to."""
    create = MagicMock()
    monkeypatch.setattr(flows, "create_table_artifact", create)
    return create


_PUBLISHED_OUTPUTS: dict = {}
"""The output revision each completed fake step published, by its flow run id."""

_POLLS: dict = {}
"""What a fake step's flow run looks like each time it is asked for, in order, by its
flow run id. An exception stands for the wait being cut short at that point."""

_STATE_CHANGES: list = []
"""Each state the runner asked Prefect to move a flow run to, with the flow run's id."""


class _FakePrefectClient:
    """Serves the flow runs and output artifacts of the steps the tests made up."""

    def __enter__(self):
        return self

    def __exit__(self, *exc_info) -> None:
        return None

    def read_flow_run(self, flow_run_id):
        polled = _POLLS[flow_run_id].pop(0)
        if isinstance(polled, BaseException):
            raise polled
        return polled

    def set_flow_run_state(self, flow_run_id, state) -> None:
        _STATE_CHANGES.append((flow_run_id, state))

    def read_artifacts(self, artifact_filter):
        assert artifact_filter.key.any_ == [flows.OUTPUT_ARTIFACT_KEY]
        [flow_run_id] = artifact_filter.flow_run_id.any_
        output = _PUBLISHED_OUTPUTS.get(flow_run_id)
        return [] if output is None else [SimpleNamespace(data=json.dumps([output]))]


@pytest.fixture(autouse=True)
def _prefect_client(monkeypatch: pytest.MonkeyPatch) -> None:
    _PUBLISHED_OUTPUTS.clear()
    _POLLS.clear()
    _STATE_CHANGES.clear()
    monkeypatch.setattr(flows, "get_client", lambda sync_client: _FakePrefectClient())
    # A step that is not final yet is asked for again without the real pause.
    monkeypatch.setattr(flows, "BLOCK_POLL_SECONDS", 0)


def _flow_run(state_type: str, name: str | None = None, flow_run_id=None):
    """A step's flow run in the given Prefect state, as far as the runner looks at it."""
    state = SimpleNamespace(
        type=SimpleNamespace(value=state_type),
        name=name or state_type.title(),
        is_final=lambda: state_type in {"COMPLETED", "FAILED", "CRASHED", "CANCELLED"},
        is_completed=lambda: state_type == "COMPLETED",
    )
    return SimpleNamespace(id=flow_run_id or uuid4(), state=state)


def _completed(output: dict | None):
    """A step's flow run that completed, having published `output` (None: nothing)."""
    flow_run = _flow_run("COMPLETED")
    if output is not None:
        _PUBLISHED_OUTPUTS[flow_run.id] = output
    return flow_run


@pytest.mark.parametrize(
    ("config", "inputs", "label"),
    [
        ({"label": "tidy"}, {"source": {"store": STORE, "id": EARLIER_ID}}, f"tidy|{EARLIER_ID}"),
        ({}, None, "|-"),
    ],
    ids=["wired", "nothing-wired"],
)
def test_the_block_flow_runs_the_named_block_with_its_config_and_inputs(
    root: dict, config: dict, inputs: dict | None, label: str
) -> None:
    # When: the flow's own body, as it runs inside the block's container
    result = flows.run_block.fn(
        block="runtime_fake",
        step_name="cluster",
        config=config,
        revision=root,
        inputs=inputs,
    )

    # Then: the revision, the settings and the wired input all arrived, and the
    # result comes back as plain data, a new revision in the input's own store.
    output = RevisionRef.from_dict(result)
    assert output.store == root["store"]
    assert steps(output) == [label]


def test_the_block_flow_publishes_its_output_revision_as_an_artifact(
    published: MagicMock, root: dict
) -> None:
    # When
    result = flows.run_block.fn(
        block="runtime_fake",
        step_name="cluster",
        config={},
        revision=root,
        inputs=None,
    )

    # Then
    published.assert_called_once_with(table=[result], key=flows.OUTPUT_ARTIFACT_KEY)


def test_the_block_flow_imports_the_job_containers_block_library_before_looking_anything_up(
    monkeypatch: pytest.MonkeyPatch, root: dict
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
        revision=root,
        inputs=None,
    )

    load_sources.assert_called_once_with()


def test_a_step_is_dispatched_at_the_block_deployment_fully_spelled_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    dispatch = MagicMock(return_value=_completed({"store": STORE, "id": OUTPUT_ID}))
    monkeypatch.setattr(flows, "run_deployment", dispatch)

    # When
    result = PrefectBlockRunner().run_block(
        _spec(),
        step_name="cluster",
        config={"label": "tidy"},
        revision=RevisionRef(store=STORE, id=REVISION_ID),
        inputs={"source": RevisionRef(store=STORE, id=EARLIER_ID)},
    )

    # Then: one deployment for every block, with the block named as a parameter,
    # and everything crossing as plain data.
    assert dispatch.call_args.kwargs["name"] == BLOCK_DEPLOYMENT
    assert dispatch.call_args.kwargs["job_variables"] == {"image": "block-prefect-runtime:default"}
    assert dispatch.call_args.kwargs["parameters"] == {
        "block": "runtime_fake",
        "step_name": "cluster",
        "config": {"label": "tidy"},
        "revision": {"store": STORE, "id": REVISION_ID},
        "inputs": {"source": {"store": STORE, "id": EARLIER_ID}},
    }
    assert result == RevisionRef(store=STORE, id=OUTPUT_ID)


def test_a_step_that_did_not_complete_fails_the_playbook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a step whose flow run ended badly
    crashed = _flow_run("CRASHED", flow_run_id="flow-run-id")
    monkeypatch.setattr(flows, "run_deployment", MagicMock(return_value=crashed))

    # When/Then: the error says which step, which block, and where to look
    with pytest.raises(BlockRunFailedError) as exc_info:
        PrefectBlockRunner().run_block(
            _spec(),
            step_name="cluster",
            config={},
            revision=RevisionRef(store=STORE, id=REVISION_ID),
            inputs={},
        )
    message = str(exc_info.value)
    assert "cluster" in message
    assert "runtime_fake" in message
    assert "CRASHED" in message
    assert "flow-run-id" in message


def test_a_step_is_dispatched_without_waiting_and_then_waited_for(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a step that is queued when dispatched, and takes two more looks to finish
    scheduled = _flow_run("SCHEDULED")
    finished = _flow_run("COMPLETED", flow_run_id=scheduled.id)
    _PUBLISHED_OUTPUTS[scheduled.id] = {"store": STORE, "id": OUTPUT_ID}
    _POLLS[scheduled.id] = [_flow_run("RUNNING", flow_run_id=scheduled.id), finished]
    dispatch = MagicMock(return_value=scheduled)
    monkeypatch.setattr(flows, "run_deployment", dispatch)

    # When
    result = PrefectBlockRunner().run_block(
        _spec(),
        step_name="cluster",
        config={},
        revision=RevisionRef(store=STORE, id=REVISION_ID),
        inputs={},
    )

    # Then: the dispatch only created the flow run, so the waiting is the runner's
    # own, and nothing was cancelled on the way.
    assert dispatch.call_args.kwargs["timeout"] == 0
    assert result == RevisionRef(store=STORE, id=OUTPUT_ID)
    assert _POLLS[scheduled.id] == []
    assert _STATE_CHANGES == []


def test_a_step_that_timed_out_fails_the_playbook_as_a_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a step whose flow run Prefect ended for exceeding its timeout
    timed_out = _flow_run("FAILED", name=flows.TIMED_OUT_STATE_NAME, flow_run_id="flow-run-id")
    monkeypatch.setattr(flows, "run_deployment", MagicMock(return_value=timed_out))

    # When/Then: a TimeoutError, which is what makes Prefect end the playbook run as
    # timed out too, and still the failure of a step that callers already expect
    with pytest.raises(BlockTimedOutError) as exc_info:
        PrefectBlockRunner().run_block(
            _spec(),
            step_name="cluster",
            config={},
            revision=RevisionRef(store=STORE, id=REVISION_ID),
            inputs={},
        )
    assert isinstance(exc_info.value, TimeoutError)
    assert isinstance(exc_info.value, BlockRunFailedError)
    message = str(exc_info.value)
    assert "cluster" in message
    assert "runtime_fake" in message
    assert "block timeout" in message
    assert "flow-run-id" in message


class _PlaybookRunEnding(BaseException):
    """Stands for what Prefect raises inside a flow whose own timeout has passed."""


def test_a_step_still_running_when_the_playbook_run_ends_is_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a running step, and a playbook run whose timeout passes while it waits
    running = _flow_run("RUNNING")
    _POLLS[running.id] = [_PlaybookRunEnding()]
    monkeypatch.setattr(flows, "run_deployment", MagicMock(return_value=running))

    # When/Then: the playbook run ends for its own reason...
    with pytest.raises(_PlaybookRunEnding):
        PrefectBlockRunner().run_block(
            _spec(),
            step_name="cluster",
            config={},
            revision=RevisionRef(store=STORE, id=REVISION_ID),
            inputs={},
        )

    # ...and the step is not left running with nothing waiting for it.
    [(flow_run_id, state)] = _STATE_CHANGES
    assert flow_run_id == running.id
    assert state.is_cancelling()


def test_a_step_that_cannot_be_cancelled_does_not_hide_why_the_playbook_run_ended(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a running step, a playbook run that ends, and a Prefect API that is gone
    running = _flow_run("RUNNING")
    _POLLS[running.id] = [_PlaybookRunEnding()]
    monkeypatch.setattr(flows, "run_deployment", MagicMock(return_value=running))
    monkeypatch.setattr(
        _FakePrefectClient,
        "set_flow_run_state",
        MagicMock(side_effect=RuntimeError("Prefect is unreachable")),
    )

    # When/Then
    with pytest.raises(_PlaybookRunEnding):
        PrefectBlockRunner().run_block(
            _spec(),
            step_name="cluster",
            config={},
            revision=RevisionRef(store=STORE, id=REVISION_ID),
            inputs={},
        )


def test_each_flow_takes_its_timeout_from_the_environment_it_is_imported_in() -> None:
    # Given: Prefect reads a flow's timeout off the flow where it executes, so it
    # is whatever the environment said when that process imported the flows.
    env = {
        **os.environ,
        "MANTA_BLOCK_TIMEOUT_SECONDS": "7",
        "MANTA_PLAYBOOK_TIMEOUT_SECONDS": "11",
    }
    script = (
        "from runner import flows; "
        "print(flows.run_block.timeout_seconds, flows.run_playbook.timeout_seconds)"
    )

    # When
    printed = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script], env=env, capture_output=True, text=True, check=True
    ).stdout

    # Then
    assert [float(value) for value in printed.split()] == [7.0, 11.0]


def test_a_step_that_completed_without_publishing_its_output_fails_the_playbook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.setattr(flows, "run_deployment", MagicMock(return_value=_completed(None)))

    # When/Then
    with pytest.raises(BlockRunFailedError, match="without publishing its output revision"):
        PrefectBlockRunner().run_block(
            _spec(),
            step_name="cluster",
            config={},
            revision=RevisionRef(store=STORE, id=REVISION_ID),
            inputs={},
        )


def test_a_step_with_no_state_at_all_fails_rather_than_returning_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    stateless = SimpleNamespace(id="flow-run-id", state=None)
    monkeypatch.setattr(flows, "run_deployment", MagicMock(return_value=stateless))

    # When/Then
    with pytest.raises(BlockRunFailedError, match="UNKNOWN"):
        PrefectBlockRunner().run_block(
            _spec(),
            step_name="cluster",
            config={},
            revision=RevisionRef(store=STORE, id=REVISION_ID),
            inputs={},
        )


def test_a_step_runs_in_its_own_environments_image(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given two steps whose blocks declare different environments
    dispatch = MagicMock(return_value=_completed({"store": STORE, "id": OUTPUT_ID}))
    monkeypatch.setattr(flows, "run_deployment", dispatch)
    runner = PrefectBlockRunner()

    # When each is dispatched
    for env in ("default", "pypsa"):
        runner.run_block(
            _spec(env=env),
            step_name="step",
            config={},
            revision=RevisionRef(store=STORE, id=REVISION_ID),
            inputs={},
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
        PrefectBlockRunner().run_block(
            _spec(env="julia"),
            step_name="step",
            config={},
            revision=RevisionRef(store=STORE, id=REVISION_ID),
            inputs={},
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
    dispatch = MagicMock(return_value=_completed({"store": STORE, "id": OUTPUT_ID}))
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
        revision={"store": STORE, "id": REVISION_ID},
        catalogue=catalogue_parameter(catalogue),
    )

    # Then: the block ran through the docker-pool transport, not in this process.
    assert result == {"store": STORE, "id": OUTPUT_ID}
    assert dispatch.call_args.kwargs["parameters"]["block"] == "catalogue_only_fake"
