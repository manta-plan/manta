# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""Working out what a playbook needs deployed, and creating it.

A plan says what is needed - which blocks, in which environments - without saying how
to provide it. A renderer then creates it. Today one renderer exists, running each
environment as a local pixi environment; a renderer for containers or a cluster would
read the same plan.

Deployments are pushed straight to the Prefect API rather than written to a file,
since a playbook edited in a browser has nowhere to keep one.

An installation that runs many playbooks does not deploy them one at a time: it
provisions every block in a catalogue once (`provision_catalogue`), after which any
playbook made of catalogued blocks can run with no deploy step of its own.
"""

from typing import TYPE_CHECKING, Protocol

from manta_blocks import Catalogue, DeploymentPlan, EnvironmentSpec, deployment_slug
from manta_blocks.entrypoint import run_block
from manta_playbooks.playbook import BlockStep, Playbook, child_config

if TYPE_CHECKING:
    from collections.abc import Callable


def deployment_plan(playbook: Playbook, config: dict) -> DeploymentPlan:
    """What has to be deployed before `playbook` can run with `config`.

    Steps that need the same block in the same environment share one deployment, and
    nested playbooks are folded in under the step that nests them.
    """
    plan = DeploymentPlan()
    for step in playbook.active(config).steps:
        if isinstance(step, BlockStep):
            plan = plan.add(step.block.name, step.block.env, (step.name,))
            plan = plan.add_env(step.block.environment(), source=step.name)
        else:
            inner = deployment_plan(step.playbook, child_config(config, step.name))
            plan = plan.merge(inner, prefix=step.name)
    return plan


class Renderer(Protocol):
    """Creates whatever a deployment plan says is needed.

    This is the seam for other kinds of target. A renderer for containers or for a
    cluster would take the same plan and create pods or services instead of local
    processes.
    """

    def apply(self, plan: DeploymentPlan) -> list[str]:
        """Create or update everything in `plan`, returning what was created."""
        ...

    def work_pool_commands(self, plan: DeploymentPlan) -> list[str]:
        """Anything an operator still has to run by hand for `plan` to work."""
        ...


class ProcessPixiRenderer:
    """Runs each environment as a local pixi environment.

    Every environment gets its own Prefect work pool, and each block is deployed onto
    the pool for the environment it needs. A worker started inside that pixi
    environment then picks the work up, which is what puts each block in the right
    place without anything having to activate an environment itself.
    """

    def apply(self, plan: DeploymentPlan) -> list[str]:
        """Create or update a deployment per block, returning their ids.

        Work pools are not created here; see `work_pool_commands`.
        """
        ids = []
        for dep in plan.deployments:
            deployment = run_block.to_deployment(
                name=dep.name,
                parameters={"block": dep.block},
                work_pool_name=plan.environments[dep.env].resolved_work_pool(),
            )
            ids.append(str(deployment.apply()))
        return ids

    def work_pool_commands(self, plan: DeploymentPlan) -> list[str]:
        """The commands that create the work pools and workers this plan needs.

        These are printed rather than run: starting long-lived workers is an
        operator's decision, not something applying a plan should do behind their back.
        """
        commands = []
        for env_name, spec in sorted(plan.environments.items()):
            commands.extend(_pool_commands(env_name, spec))
        return commands


def _pool_commands(env_name: str, spec: EnvironmentSpec) -> list[str]:
    manifest = f"--manifest-path {spec.manifest} " if spec.manifest else ""
    pool = spec.resolved_work_pool()
    return [
        f"pixi run {manifest}-e {env_name} "
        f"prefect work-pool create --type process {pool}",
        f"pixi run {manifest}-e {env_name} prefect worker start --pool {pool}",
    ]


def ensure_process_pool(name: str) -> None:
    """Create the process work pool `name`, or leave it be if it already exists."""
    from prefect.client.orchestration import get_client
    from prefect.client.schemas.actions import WorkPoolCreate
    from prefect.exceptions import ObjectAlreadyExists

    with get_client(sync_client=True) as client:
        try:
            client.create_work_pool(WorkPoolCreate(name=name, type="process"))
        except ObjectAlreadyExists:
            pass


def docker_job_template(
    env_name: str,
    image: str,
    env: dict[str, str] | None = None,
    network: str | None = None,
    volumes: "list[str] | None" = None,
) -> dict:
    """A docker work pool's job template: each job is a container running `image`.

    The container's command activates the pixi environment `env_name` before handing
    over to Prefect, which is what keeps "which environment does this pool run" a
    property of the pool rather than of any code. `env`, `network`, and `volumes`
    become defaults for every job the pool runs; a deployment can still override any
    of them through its own job variables.

    Needs `prefect-docker` installed (`manta-blocks[docker]`).
    """
    from prefect_docker.worker import DockerWorker

    template = DockerWorker.get_default_base_job_template()
    defaults = {
        "image": image,
        "command": f"pixi run -e {env_name} prefect flow-run execute",
        # An image that only exists locally (built by compose, never pushed) must
        # not be pulled: for a `latest` tag the worker would otherwise try the
        # registry first and fail.
        "image_pull_policy": "IfNotPresent",
        # Job containers are throwaway by design; their logs live in Prefect.
        "auto_remove": True,
    }
    if env:
        defaults["env"] = env
    if network:
        defaults["networks"] = [network]
    if volumes:
        defaults["volumes"] = volumes

    variables = template["variables"]["properties"]
    for key, value in defaults.items():
        variables[key]["default"] = value
    return template


def ensure_docker_pool(name: str, base_job_template: dict) -> None:
    """Create the docker work pool `name`, or bring it up to date.

    Unlike `ensure_process_pool`, an existing pool is updated rather than left
    alone: the template carries the image and wiring, and re-provisioning is how
    changes to those roll out. A pool of another type under this name is recreated,
    since Prefect cannot change a pool's type in place - anything deployed onto it
    goes with it, which is fine for the one caller (`provision_catalogue`) because
    it re-registers every deployment right after.
    """
    from prefect.client.orchestration import get_client
    from prefect.client.schemas.actions import WorkPoolCreate, WorkPoolUpdate
    from prefect.exceptions import ObjectAlreadyExists

    create = WorkPoolCreate(
        name=name, type="docker", base_job_template=base_job_template
    )
    with get_client(sync_client=True) as client:
        try:
            client.create_work_pool(create)
        except ObjectAlreadyExists:
            if client.read_work_pool(name).type == "docker":
                client.update_work_pool(
                    work_pool_name=name,
                    work_pool=WorkPoolUpdate(base_job_template=base_job_template),
                )
            else:
                client.delete_work_pool(name)
                client.create_work_pool(create)


def provision_catalogue(
    catalogue: Catalogue,
    orchestrator_env: str,
    create_pools: bool = True,
    pool_factory: "Callable[[str, str], None] | None" = None,
) -> list[str]:
    """Make everything in `catalogue` runnable, and return the deployment ids.

    Every block gets a deployment on its environment's work pool, and the playbook
    orchestrator gets one on `orchestrator_env`'s pool. With that in place, any
    playbook made of catalogued blocks can be started with nothing but a
    `run_deployment` call - which is exactly what the Manta backend does.

    Unlike `ProcessPixiRenderer`, this also creates the work pools: it is meant for a
    setup step of a managed installation (Manta's docker compose, later Kubernetes),
    where there is no operator watching for printed commands. Workers are still
    started by the installation itself, one per environment.

    `pool_factory` decides what kind of pool each environment gets, called as
    `pool_factory(pool_name, env_name)`. The default creates process pools (a worker
    per environment runs jobs as subprocesses); pass one built on
    `ensure_docker_pool` + `docker_job_template` to run every job in its own docker
    container instead - which is what Manta's dev stack does.

    Deployments are registered with module entrypoints rather than file paths, so a
    worker finds the flow by importing it from its own installed packages - the
    provisioning process and the workers need no shared filesystem layout.
    """
    from prefect.types.entrypoint import EntrypointType

    from manta_playbooks.execution import run_playbook

    factory = pool_factory or (lambda pool, _env: ensure_process_pool(pool))
    pools = {
        spec.resolved_work_pool(): spec.name for spec in catalogue.environments.values()
    }
    pools[f"manta-{orchestrator_env}"] = orchestrator_env
    if create_pools:
        for pool, env_name in sorted(pools.items()):
            factory(pool, env_name)

    ids = []
    for name, description in sorted(catalogue.blocks.items()):
        spec = catalogue.environments.get(
            description.env, EnvironmentSpec(name=description.env)
        )
        deployment = run_block.to_deployment(
            name=deployment_slug(name, description.env),
            parameters={"block": name},
            work_pool_name=spec.resolved_work_pool(),
            entrypoint_type=EntrypointType.MODULE_PATH,
        )
        ids.append(str(deployment.apply()))

    orchestrator = run_playbook.to_deployment(
        name=orchestrator_env,
        work_pool_name=f"manta-{orchestrator_env}",
        entrypoint_type=EntrypointType.MODULE_PATH,
    )
    ids.append(str(orchestrator.apply()))
    return ids
