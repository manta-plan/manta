from unittest.mock import MagicMock

import pytest

from manta.workflows import playbook_flows
from manta.workflows.playbook_flows import BlockRunFailedError, _run_block_in_container


class _FakeContainer:
    def __init__(self, log_chunks: list[bytes], exit_code: int = 0) -> None:
        self._log_chunks = log_chunks
        self._exit_code = exit_code
        self.removed = False

    def logs(self, stream: bool, follow: bool):
        yield from self._log_chunks

    def wait(self) -> dict:
        return {"StatusCode": self._exit_code}

    def remove(self, force: bool = False) -> None:
        self.removed = True


def _fake_docker(monkeypatch, container: _FakeContainer) -> MagicMock:
    client = MagicMock()
    client.images.get.return_value = object()  # the image exists
    client.containers.run.return_value = container
    monkeypatch.setattr(playbook_flows, "_docker_client", lambda: client)
    return client


def _job_env(monkeypatch) -> None:
    monkeypatch.setenv("S3_ACCESS_KEY", "test-key")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")
    monkeypatch.setenv("MANTA_JOB_S3_ENDPOINT", "http://seaweedfs:8333")
    monkeypatch.setenv("MANTA_BLOCKS_IMAGE", "manta-blocks-runner:test")
    monkeypatch.setenv("MANTA_DOCKER_NETWORK", "manta-test-net")


def test_a_block_runs_in_a_container_and_returns_its_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a container that logs solver output and ends with a result line
    _job_env(monkeypatch)
    container = _FakeContainer(
        [
            b"INFO solving 8 snapshots\n",
            b'MANTA_BLOCK_RESULT {"url": "s3://manta/p/runs/1/steps/cluster.nc"}\n',
        ]
    )
    client = _fake_docker(monkeypatch, container)

    # When
    result = _run_block_in_container(
        block_name="cluster_time",
        step_name="cluster",
        config={"n_hours": 3},
        record={"url": "s3://manta/p/runs/1/input/network.nc"},
        inputs={},
        output_base="s3://manta/p/runs/1/steps/cluster",
    )

    # Then the result came back through the container's output...
    assert result == {"url": "s3://manta/p/runs/1/steps/cluster.nc"}

    # ...the container ran the bare blocks entrypoint from the runner image, on
    # the stack's network, with the object-store environment blocks expect...
    run_kwargs = client.containers.run.call_args.kwargs
    run_args = client.containers.run.call_args.args
    assert run_args[0] == "manta-blocks-runner:test"
    assert run_kwargs["command"][:4] == ["python", "-m", "blocks.run_one", "cluster_time"]
    assert run_kwargs["network"] == "manta-test-net"
    assert run_kwargs["environment"] == {
        "AWS_ACCESS_KEY_ID": "test-key",
        "AWS_SECRET_ACCESS_KEY": "test-secret",
        "AWS_ENDPOINT_URL": "http://seaweedfs:8333",
    }
    assert run_kwargs["name"].startswith("manta-block-cluster-")

    # ...and was cleaned up.
    assert container.removed


def test_a_result_line_split_across_log_chunks_is_still_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given docker delivering the result line in two chunks
    _job_env(monkeypatch)
    container = _FakeContainer([b'MANTA_BLOCK_RESULT {"url": ', b'"out/cluster.nc"}\n'])
    _fake_docker(monkeypatch, container)

    # When
    result = _run_block_in_container(
        block_name="cluster_time",
        step_name="cluster",
        config={},
        record={"url": "in.nc"},
        inputs={},
        output_base="out/cluster",
    )

    # Then
    assert result == {"url": "out/cluster.nc"}


def test_a_failing_container_raises_and_is_still_cleaned_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a container that logs a traceback and exits non-zero
    _job_env(monkeypatch)
    container = _FakeContainer([b"Traceback ...\n"], exit_code=1)
    _fake_docker(monkeypatch, container)

    # When/Then
    with pytest.raises(BlockRunFailedError, match=r"'solve'.*exited with code 1"):
        _run_block_in_container(
            block_name="overnight_capacity_expansion",
            step_name="solve",
            config={},
            record={"url": "in.nc"},
            inputs={},
            output_base="out/solve",
        )
    assert container.removed


def test_a_clean_exit_without_a_result_line_is_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a container that exits 0 but never reports where its output went
    _job_env(monkeypatch)
    container = _FakeContainer([b"did some work, told nobody\n"], exit_code=0)
    _fake_docker(monkeypatch, container)

    # When/Then
    with pytest.raises(BlockRunFailedError, match="never reported a"):
        _run_block_in_container(
            block_name="cluster_time",
            step_name="cluster",
            config={},
            record={"url": "in.nc"},
            inputs={},
            output_base="out/cluster",
        )


def test_a_missing_runner_image_fails_before_any_container_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given no locally built blocks runner image
    _job_env(monkeypatch)
    client = MagicMock()
    client.images.get.side_effect = RuntimeError("not found")
    monkeypatch.setattr(playbook_flows, "_docker_client", lambda: client)

    # When/Then
    with pytest.raises(BlockRunFailedError, match="not available locally"):
        _run_block_in_container(
            block_name="cluster_time",
            step_name="cluster",
            config={},
            record={"url": "in.nc"},
            inputs={},
            output_base="out/cluster",
        )
    client.containers.run.assert_not_called()
