# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""The same playbook as `cluster_expand_dispatch.yaml`, written in Python.

Run it to see what a playbook can tell you before anything is executed:

    pixi run -e full python -m manta_batteries.examples.cluster_expand_dispatch

It checks the playbook, draws it, and works out what would have to be deployed. None
of that runs a block. Applying the deployments does need a Prefect server to talk to
(`prefect server start` in another window); without one, that last step is skipped.
"""

from pathlib import Path

from manta_playbooks.deploy import ProcessPixiRenderer
from manta_playbooks.playbook import Playbook, When
from manta_playbooks.yaml_io import load_config

from manta_batteries.myopic_capacity_expansion import MyopicCapacityExpansion
from manta_batteries.overnight_capacity_expansion import OvernightCapacityExpansion
from manta_batteries.rolling_horizon_dispatch import RollingHorizonDispatch
from manta_batteries.time_cluster import ClusterTime

HERE = Path(__file__).parent


def build_playbook() -> Playbook:
    pb = Playbook(name="cluster-expand-dispatch", initial_dims=frozenset({"snapshot"}))
    pb.add("cluster", ClusterTime)
    overnight = pb.add(
        "expansion_overnight",
        OvernightCapacityExpansion,
        when=When(config="globals.expansion_mode", equals="overnight"),
    )
    pb.add(
        "expansion_myopic",
        MyopicCapacityExpansion,
        when=When(config="globals.expansion_mode", equals="myopic"),
    )
    pb.add(
        "dispatch",
        RollingHorizonDispatch,
        inputs={"capacity_source": overnight.output},
        when=When(config="globals.expansion_mode", equals="overnight"),
    )
    return pb


if __name__ == "__main__":
    playbook = build_playbook()
    config = load_config(HERE / "cluster_expand_dispatch_config.yaml")

    playbook.validate_playbook(config)
    mode = config["globals"]["expansion_mode"]
    print(f"Playbook is valid for expansion_mode={mode!r}\n")

    print(playbook.to_mermaid(config))

    plan = playbook.deployment_plan(config)
    renderer = ProcessPixiRenderer()

    print(f"\n{len(plan.deployments)} deployment(s) needed:")
    for dep in plan.deployments:
        print(f"  {dep.name} (for steps: {[list(p) for p in dep.paths]})")

    print("\nWork pool setup:")
    for command in renderer.work_pool_commands(plan):
        print(f"  {command}")

    try:
        deployment_ids = renderer.apply(plan)
    except Exception as exc:
        # Most likely there is no Prefect server to talk to, or the work pools above
        # do not exist yet. Applying a plan puts deployments onto a pool; it does not
        # create the pool.
        print(f"\nSkipped applying deployments ({exc})")
    else:
        print(f"\nApplied {len(deployment_ids)} deployment(s): {deployment_ids}")
