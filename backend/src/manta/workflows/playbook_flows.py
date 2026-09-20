"""The Prefect flow that runs playbooks, and the containers it drives blocks in.

This module is the whole execution runtime: `run-playbook` (served as a
deployment by a subprocess of the app, see main.py and the __main__ block below)
walks a playbook document with manta-blocks' engine, and every block step becomes
one Prefect task run that spawns one container from the blocks runner image.

The containers are deliberately dumb: the image holds only manta-blocks and the
blocks' own dependencies — no Prefect, no Manta — and each one runs the
orchestration-agnostic `python -m blocks.run_one` entrypoint. Everything Prefect-
or Docker-shaped stays on this side of the boundary, so the block image is
exactly what an outside block author tests against.

Tracking: one flow run per playbook run (named `run-<run uuid>` by the backend),
one task run per executed step (named `<step>[<block>]`), queryable by the flow
run's id — see RunService.get_run_steps.
"""

import contextlib
import json
import logging
from uuid import uuid4

from blocks import DataRecord
from blocks.library import library_catalogue
from blocks.run_one import parse_result_line
from playbooks import execute_playbook, parse_doc, playbook_from_doc
from prefect import flow, task

from manta.config.blocks_runtime_config import blocks_image, docker_network, job_environment

logger = logging.getLogger(__name__)

PLAYBOOK_FLOW_NAME = "run-playbook"
PLAYBOOK_DEPLOYMENT = f"{PLAYBOOK_FLOW_NAME}/{PLAYBOOK_FLOW_NAME}"
"""Created by this flow's serve() below; RunService dispatches runs at it by name."""


class BlockRunFailedError(Exception):
    """Raised when a block's container did not produce a result."""


def _docker_client():
    # Imported lazily so importing this module (e.g. for PLAYBOOK_DEPLOYMENT) never
    # requires a reachable Docker daemon.
    import docker

    return docker.from_env()


def _step_logger() -> logging.Logger:
    """The task run's logger inside Prefect (so step logs land with the step in the
    API/UI), this module's logger anywhere else (unit tests call the plain
    function without a run context)."""
    try:
        from prefect import get_run_logger

        return get_run_logger()
    except Exception:
        return logger


def _run_block_in_container(
    block_name: str,
    step_name: str,
    config: dict,
    record: dict,
    inputs: dict[str, dict],
    output_base: str,
) -> dict:
    """Run one block in its own container and return the record it produced.

    The container's stdout/stderr is relayed line by line into this task's log, so
    a block's solver output lands in Prefect next to the step it belongs to. The
    result comes back as the entrypoint's final RESULT_MARKER line — parsed here,
    in the same process that orchestrates the playbook, so there is no result
    side-channel to keep consistent.
    """
    client = _docker_client()
    image = blocks_image()
    try:
        client.images.get(image)
    except Exception as exc:
        raise BlockRunFailedError(
            f"blocks runner image {image!r} is not available locally; build it with "
            "the compose stack (see docker/README.md)"
        ) from exc

    command = [
        "python",
        "-m",
        "blocks.run_one",
        block_name,
        "--record",
        json.dumps(record),
        "--output-base",
        output_base,
        "--config",
        json.dumps(config),
        "--inputs",
        json.dumps(inputs),
    ]
    container = client.containers.run(
        image,
        command=command,
        environment=job_environment(),
        network=docker_network(),
        name=f"manta-block-{step_name}-{uuid4().hex[:8]}",
        detach=True,
    )

    step_logger = _step_logger()
    try:
        result: DataRecord | None = None
        for line in _log_lines(container):
            step_logger.info("[%s] %s", step_name, line)
            parsed = parse_result_line(line)
            if parsed is not None:
                result = parsed
        exit_code = container.wait().get("StatusCode", -1)
    finally:
        # Cleanup only; the run's outcome is decided by exit code and result line.
        with contextlib.suppress(Exception):
            container.remove(force=True)

    if exit_code != 0:
        raise BlockRunFailedError(
            f"step {step_name!r} ({block_name}) exited with code {exit_code}; "
            "its log is in this task's output above"
        )
    if result is None:
        raise BlockRunFailedError(
            f"step {step_name!r} ({block_name}) exited cleanly but never reported a result record"
        )
    return result.to_dict()


def _log_lines(container):
    """The container's output, line by line, as it is produced."""
    buffer = b""
    for chunk in container.logs(stream=True, follow=True):
        buffer += chunk
        while b"\n" in buffer:
            line, _, buffer = buffer.partition(b"\n")
            yield line.decode(errors="replace").rstrip("\r")
    if buffer:
        yield buffer.decode(errors="replace")


@task(task_run_name="{step_name}[{block_name}]")
def run_block(
    block_name: str,
    step_name: str,
    config: dict,
    record: dict,
    inputs: dict[str, dict],
    output_base: str,
) -> dict:
    """One playbook step: one task run, one container."""
    return _run_block_in_container(block_name, step_name, config, record, inputs, output_base)


class DockerStepRunner:
    """manta-blocks' StepRunner seam, implemented as one container per step.

    The engine hands over one fully spelled-out block invocation at a time; each
    becomes a `run_block` task run inside the current playbook flow run. Moving
    execution to k8s later means swapping the container call in
    `_run_block_in_container` for a Job — nothing above this class changes.
    """

    def run_block(
        self,
        block,
        *,
        step_name: str,
        config: dict,
        record: DataRecord,
        inputs: dict[str, DataRecord],
        output_base: str,
    ) -> DataRecord:
        result = run_block(
            block_name=block.name,
            step_name=step_name,
            config=config,
            record=record.to_dict(),
            inputs={name: value.to_dict() for name, value in inputs.items()},
            output_base=output_base,
        )
        return DataRecord.from_dict(result)


@flow(name=PLAYBOOK_FLOW_NAME)
def run_playbook(playbook: dict, config: dict, record: dict, output_prefix: str) -> dict:
    """Run a whole playbook, given its document rather than the playbook itself.

    This is what the backend dispatches when a user presses Run. Blocks are
    resolved from the committed catalogue — this process never imports them (they
    need PyPSA, which only exists inside the runner image) — and the document is
    validated again here before any container is started.
    """
    built = playbook_from_doc(parse_doc(playbook), catalogue=library_catalogue())
    result = execute_playbook(
        built,
        DataRecord.from_dict(record),
        config,
        output_prefix=output_prefix,
        runner=DockerStepRunner(),
    )
    return result.to_dict()


if __name__ == "__main__":
    # Served like the pi-digit-stats flow: a subprocess of the app (see main.py)
    # that registers the deployment and executes its runs. TODO(post-MVP): run this
    # as its own long-lived service so in-flight playbook runs survive app restarts.
    run_playbook.serve(name=PLAYBOOK_FLOW_NAME)
