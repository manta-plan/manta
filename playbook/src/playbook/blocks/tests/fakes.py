# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Stand-in blocks for testing, which need nothing installed.

Each one just adds its name to the record's url, so a finished run reads as a record
of which blocks ran and in what order. None of them writes a file.

They are registered here, once, and shared by the tests for both packages: a block
name can only be claimed once per process, so registering them in two places would
clash.
"""

from uuid import UUID, uuid5

from playbook.blocks.core import BlockDims, ConfigSchema, DataRecord, MantaBlock
from playbook.blocks.registry import BlockSpec, register

RECORD_UUID = UUID(int=0)


def revision_of(record: DataRecord) -> DataRecord:
    return DataRecord(url=record.url, uuid=uuid5(record.uuid, "revision"))


class FakeConfig(ConfigSchema):
    label: str = ""
    source: DataRecord | None = None


class FakeBlock(MantaBlock[FakeConfig]):
    """Adds a label to the record's url, and nothing else."""

    ENV = "default"
    CONFIG = FakeConfig
    DIMS = BlockDims()
    INPUTS = frozenset()

    def run(self, record: DataRecord) -> DataRecord:
        suffix = self.config.label or type(self).__name__
        return DataRecord(url=f"{record.url}+{suffix}", uuid=record.uuid)


@register("fake_passthrough")
class FakePassthrough(FakeBlock):
    """Changes no dimensions, so it can be used as often as a playbook likes."""


@register("fake_adds_clustered")
class FakeAddsClustered(FakeBlock):
    DIMS = BlockDims(adds=frozenset({"clustered"}))


@register("fake_requires_period")
class FakeRequiresPeriod(FakeBlock):
    DIMS = BlockDims(requires=frozenset({"period"}))


@register("fake_removes_period")
class FakeRemovesPeriod(FakeBlock):
    DIMS = BlockDims(
        requires=frozenset({"period"}),
        removes=frozenset({"period"}),
    )


@register("fake_needs_upstream")
class FakeNeedsUpstream(FakeBlock):
    INPUTS = frozenset({"source"})

    def run(self, record: DataRecord) -> DataRecord:
        source_url = self.config.source.url if self.config.source else "none"
        return DataRecord(url=f"{record.url}+needs({source_url})", uuid=record.uuid)


class StrictConfig(ConfigSchema):
    required_field: int


@register("fake_strict_config")
class FakeStrictConfig(FakeBlock):
    CONFIG = StrictConfig

    def run(self, record: DataRecord) -> DataRecord:
        return DataRecord(
            url=f"{record.url}+strict({self.config.required_field})", uuid=record.uuid
        )


class OptionalGroupConfig(ConfigSchema):
    size: int = 1


class NestedSettingsConfig(ConfigSchema):
    group: OptionalGroupConfig | None = None


@register("fake_nested_settings")
class FakeNestedSettings(FakeBlock):
    """Has an optional group of settings, shaped like a real block's solver options."""

    CONFIG = NestedSettingsConfig


@register("fake_writes_output")
class FakeWritesOutput(FakeBlock):
    """Writes its result as a new revision in the input record's store, like a real block."""

    def run(self, record: DataRecord) -> DataRecord:
        return revision_of(record)


@register("fake_other_env")
class FakeOtherEnv(FakeBlock):
    """Claims an environment nothing runs in, for testing hand-off between them."""

    ENV = "elsewhere"


@register("fake_explodes")
class FakeExplodes(FakeBlock):
    """Fails if it is ever run, to prove that something never runs it."""

    def run(self, record: DataRecord) -> DataRecord:
        raise AssertionError("this block should never have been run")


class RecordingRunner:
    """Hands back made-up records, and keeps every call for the test to inspect."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def run_block(
        self,
        block: BlockSpec,
        *,
        step_name: str,
        config: dict,
        record: DataRecord,
        inputs: dict[str, DataRecord],
    ) -> DataRecord:
        self.calls.append(
            {
                "block": block.name,
                "step_name": step_name,
                "config": config,
                "record": record,
                "inputs": inputs,
            }
        )
        return DataRecord(url=f"{record.url}/{step_name}", uuid=record.uuid)
