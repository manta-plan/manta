# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

import pytest
from prefect.client.orchestration import get_client
from prefect.client.schemas.actions import WorkPoolCreate

from manta_blocks.deployment import DeploymentPlan
from manta_blocks.environments import EnvironmentSpec
from manta_blocks.tests.fakes import FakeOtherEnv, FakePassthrough
from manta_playbooks.deploy import (
    ProcessPixiRenderer,
    deployment_plan,
    docker_job_template,
)
from manta_playbooks.playbook import Playbook


def _plan() -> DeploymentPlan:
    return (
        DeploymentPlan()
        .add("fake_passthrough", "default", ("a",))
        .add_env(EnvironmentSpec(name="default"))
    )


@pytest.fixture
def _default_work_pool():
    # Applying a plan puts deployments onto a work pool; creating the pool itself is
    # deliberately left to an operator, so a test has to stand one up just as a real
    # run would with `pixi run ... prefect work-pool create`.
    with get_client(sync_client=True) as client:
        client.create_work_pool(WorkPoolCreate(name="manta-default", type="process"))


@pytest.mark.slow
@pytest.mark.usefixtures("_default_work_pool")
def test_applying_a_plan_registers_one_deployment_per_block():
    ids = ProcessPixiRenderer().apply(_plan())
    assert len(ids) == 1


def test_work_pool_commands_use_the_manifest_of_a_third_party_environment():
    plan = DeploymentPlan().add_env(
        EnvironmentSpec(name="solver", manifest="ext/pixi.toml")
    )
    commands = ProcessPixiRenderer().work_pool_commands(plan)
    assert any("--manifest-path ext/pixi.toml" in c for c in commands)
    assert any("work-pool create" in c for c in commands)
    assert any("worker start" in c for c in commands)


def test_a_plan_lists_one_deployment_per_block_and_environment():
    pb = Playbook(name="p")
    pb.add("a", FakePassthrough)
    pb.add("b", FakePassthrough)
    pb.add("c", FakeOtherEnv)

    plan = deployment_plan(pb, {"a": {}, "b": {}, "c": {}})

    # `a` and `b` are the same block in the same environment, so they share one.
    assert len(plan.deployments) == 2
    assert {(d.block, d.env) for d in plan.deployments} == {
        ("fake_passthrough", "default"),
        ("fake_other_env", "elsewhere"),
    }
    assert set(plan.environments) == {"default", "elsewhere"}


def test_a_plan_covers_only_the_steps_that_will_run():
    from manta_playbooks.playbook import When

    pb = Playbook(name="p")
    pb.add("a", FakePassthrough)
    pb.add("b", FakeOtherEnv, when=When(config="globals.mode", equals="on"))

    plan = deployment_plan(pb, {"globals": {"mode": "off"}, "a": {}, "b": {}})
    assert {d.block for d in plan.deployments} == {"fake_passthrough"}
    assert set(plan.environments) == {"default"}


def test_a_docker_job_template_runs_jobs_inside_the_named_pixi_environment():
    template = docker_job_template(
        "pypsa",
        image="manta-playbooks-worker",
        env={"MANTA_BLOCK_SOURCES": "manta_batteries"},
        network="manta_default",
        volumes=["manta_prefect-results:/prefect-results"],
    )

    defaults = {
        key: value.get("default")
        for key, value in template["variables"]["properties"].items()
    }
    assert defaults["image"] == "manta-playbooks-worker"
    assert defaults["command"] == "pixi run -e pypsa prefect flow-run execute"
    assert defaults["env"] == {"MANTA_BLOCK_SOURCES": "manta_batteries"}
    assert defaults["networks"] == ["manta_default"]
    assert defaults["volumes"] == ["manta_prefect-results:/prefect-results"]
    # A locally built image must never be pulled, and finished jobs must not
    # pile up as stopped containers.
    assert defaults["image_pull_policy"] == "IfNotPresent"
    assert defaults["auto_remove"] is True


def test_a_docker_job_template_leaves_unset_wiring_to_the_worker_defaults():
    template = docker_job_template("pypsa", image="manta-playbooks-worker")

    properties = template["variables"]["properties"]
    assert (
        "default" not in properties["networks"] or not properties["networks"]["default"]
    )
    assert "default" not in properties["env"] or not properties["env"]["default"]
