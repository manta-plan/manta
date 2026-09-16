# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""What needs deploying so a playbook can run.

A playbook's steps are turned into a list of `(block, environment)` pairs. Steps that
need the same pair share one deployment, so a block used five times is deployed once.

This is a description, not a set of instructions: it says what is needed, and a
renderer decides how to create it.
"""

from pydantic import BaseModel, ConfigDict, Field

from manta_blocks.environments import EnvironmentConflictError, EnvironmentSpec

ENTRYPOINT_FLOW = "run_block"
"""The Prefect flow every block deployment runs."""


def deployment_slug(block: str, env: str) -> str:
    """The deployment name for one block-and-environment pair."""
    return f"{block}-{env}"


def deployment_path(block: str, env: str) -> str:
    """The full name Prefect needs to find a block's deployment and run it."""
    return f"{ENTRYPOINT_FLOW}/{deployment_slug(block, env)}"


class Deployment(BaseModel):
    """One block-and-environment pair, plus every step that needs it."""

    model_config = ConfigDict(frozen=True)

    block: str
    env: str
    paths: tuple[tuple[str, ...], ...] = Field(default_factory=tuple)
    """Each step that needs this deployment, named from the outermost playbook inwards."""

    @property
    def name(self) -> str:
        return deployment_slug(self.block, self.env)

    def with_path(self, path: tuple[str, ...]) -> "Deployment":
        if path in self.paths:
            return self
        return self.model_copy(update={"paths": (*self.paths, path)})


class DeploymentPlan(BaseModel):
    """Everything a playbook needs deployed, including its nested playbooks."""

    model_config = ConfigDict(frozen=True)

    deployments: tuple[Deployment, ...] = Field(default_factory=tuple)
    environments: dict[str, EnvironmentSpec] = Field(default_factory=dict)

    def add(self, block: str, env: str, path: tuple[str, ...]) -> "DeploymentPlan":
        """Return a copy with one more step's requirement folded in."""
        for i, dep in enumerate(self.deployments):
            if dep.block == block and dep.env == env:
                deployments = list(self.deployments)
                deployments[i] = dep.with_path(path)
                return self.model_copy(update={"deployments": tuple(deployments)})
        new_dep = Deployment(block=block, env=env, paths=(path,))
        return self.model_copy(update={"deployments": (*self.deployments, new_dep)})

    def add_env(self, spec: EnvironmentSpec, source: str = "") -> "DeploymentPlan":
        """Return a copy that also knows about `spec`.

        Two blocks are free to share an environment name, but only if they describe it
        the same way; disagreeing about where an environment lives is an error rather
        than a silent win for whichever block was looked at last. `source` names the
        step being folded in, to make such a clash easier to place.
        """
        existing = self.environments.get(spec.name)
        if existing is not None and existing != spec:
            where = f" (under step {source!r})" if source else ""
            raise EnvironmentConflictError(
                f"Environment {spec.name!r} is described as {existing!r} in one part "
                f"of the playbook and {spec!r} in another{where}"
            )
        if existing is not None:
            return self
        return self.model_copy(
            update={"environments": {**self.environments, spec.name: spec}}
        )

    def merge(self, child: "DeploymentPlan", prefix: str) -> "DeploymentPlan":
        """Fold a nested playbook's plan into this one.

        The child's step names are re-rooted under `prefix`, the name of the step that
        nests it, so every path still reads from the outermost playbook inwards.
        """
        plan = self
        for dep in child.deployments:
            for path in dep.paths:
                plan = plan.add(dep.block, dep.env, (prefix, *path))
        for spec in child.environments.values():
            plan = plan.add_env(spec, source=prefix)
        return plan
