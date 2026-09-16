# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

import pytest

from manta_blocks.deployment import DeploymentPlan, deployment_path, deployment_slug
from manta_blocks.environments import EnvironmentConflictError, EnvironmentSpec


def test_add_creates_one_deployment_per_block_env_pair():
    plan = DeploymentPlan().add("cluster_time", "pypsa", ("cluster",))
    assert len(plan.deployments) == 1
    assert plan.deployments[0].name == "cluster_time-pypsa"
    assert plan.deployments[0].paths == (("cluster",),)


def test_add_dedups_same_block_env_across_steps():
    plan = DeploymentPlan()
    plan = plan.add("cluster_time", "pypsa", ("a",))
    plan = plan.add("cluster_time", "pypsa", ("b",))
    assert len(plan.deployments) == 1
    assert set(plan.deployments[0].paths) == {("a",), ("b",)}


def test_deployment_names_are_the_same_everywhere():
    assert deployment_slug("cluster_time", "pypsa") == "cluster_time-pypsa"
    assert deployment_path("cluster_time", "pypsa") == "run_block/cluster_time-pypsa"
    plan = DeploymentPlan().add("cluster_time", "pypsa", ("cluster",))
    assert plan.deployments[0].name == deployment_slug("cluster_time", "pypsa")


def test_add_env_records_an_environment():
    plan = DeploymentPlan().add_env(EnvironmentSpec(name="pypsa"))
    assert plan.environments["pypsa"] == EnvironmentSpec(name="pypsa")


def test_add_env_accepts_the_same_environment_twice():
    spec = EnvironmentSpec(name="pypsa", manifest="a.toml")
    plan = DeploymentPlan().add_env(spec).add_env(spec)
    assert plan.environments["pypsa"].manifest == "a.toml"


def test_add_env_rejects_two_descriptions_of_one_environment():
    plan = DeploymentPlan().add_env(EnvironmentSpec(name="solver", manifest="a.toml"))
    with pytest.raises(EnvironmentConflictError):
        plan.add_env(EnvironmentSpec(name="solver", manifest="b.toml"))


def test_merge_reroots_child_paths_under_prefix():
    child = DeploymentPlan().add("cluster_time", "pypsa", ("cluster",))
    parent = DeploymentPlan().merge(child, prefix="regional")
    assert parent.deployments[0].paths == (("regional", "cluster"),)


def test_merge_dedups_against_parent_deployment():
    parent = DeploymentPlan().add("cluster_time", "pypsa", ("expand",))
    child = DeploymentPlan().add("cluster_time", "pypsa", ("cluster",))
    merged = parent.merge(child, prefix="regional")
    assert len(merged.deployments) == 1
    assert set(merged.deployments[0].paths) == {("expand",), ("regional", "cluster")}


def test_merge_carries_environments_forward():
    child = DeploymentPlan().add_env(EnvironmentSpec(name="pypsa"))
    parent = DeploymentPlan().merge(child, prefix="regional")
    assert "pypsa" in parent.environments


def test_merge_rejects_conflicting_environments_and_says_where():
    parent = DeploymentPlan().add_env(EnvironmentSpec(name="solver", manifest="a.toml"))
    child = DeploymentPlan().add_env(EnvironmentSpec(name="solver", manifest="b.toml"))
    with pytest.raises(EnvironmentConflictError, match="regional"):
        parent.merge(child, prefix="regional")
