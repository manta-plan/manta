"""Manta's execution runtime: the Prefect side of running blocks and playbooks.

This is the one place in the system that knows playbooks are run by Prefect.
`manta-blocks` stays orchestration-agnostic, and the Manta backend only starts and
watches runs through the Prefect API by deployment name.
"""

from manta_runtime.flows import (
    BLOCK_DEPLOYMENT,
    PLAYBOOK_DEPLOYMENT,
    PrefectStepRunner,
    run_block,
    run_playbook,
)

__all__ = [
    "BLOCK_DEPLOYMENT",
    "PLAYBOOK_DEPLOYMENT",
    "PrefectStepRunner",
    "run_block",
    "run_playbook",
]
