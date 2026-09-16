# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""The Prefect flow that every block deployment runs.

There is one deployment per block-and-environment pair, and they all run this same
function; each deployment carries its own block name in its parameters. That keeps
per-block visibility in Prefect without needing per-block code here.

Everything passed in has crossed a process boundary, so records arrive as plain
`{"url": ...}` data. A loaded model could never travel this way, which is exactly why
blocks pass pointers to data rather than the data itself.
"""

from prefect import flow

from manta_blocks.core import DataRecord
from manta_blocks.deployment import ENTRYPOINT_FLOW
from manta_blocks.registry import get_block, load_block_sources

# A worker imports this module to run the flow below, so this is the moment the block
# libraries it serves (named in MANTA_BLOCK_SOURCES) have to be imported: their blocks
# must be registered before any of them is looked up by name.
load_block_sources()


# The result is persisted so a caller in another process - the playbook orchestrator
# dispatching a step to this environment's worker - can read it back. Where persisted
# results live is deployment configuration (PREFECT_LOCAL_STORAGE_PATH on a volume
# shared between workers for local dev; object storage once multi-machine).
@flow(name=ENTRYPOINT_FLOW, persist_result=True)
def run_block(
    block: str, config: dict, record: dict, inputs: dict[str, dict] | None = None
) -> dict:
    """Run one block by name and return where its result was written."""
    block_cls = get_block(block)
    wired = {
        name: DataRecord.from_dict(value) for name, value in (inputs or {}).items()
    }
    result = block_cls.as_flow(config, name=block, input_names=wired.keys())(
        DataRecord.from_dict(record), **wired
    )
    return result.to_dict()
