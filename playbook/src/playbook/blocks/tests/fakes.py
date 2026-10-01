# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Stand-in blocks for testing, which need nothing installed.

Each one just adds its name to the record's url, so a finished run reads as a record
of which blocks ran and in what order. None of them writes a file, so `output_base`
goes unused - which is allowed: where a block puts its output is the block's call.

They are registered here, once, and shared by the tests for both packages: a block
name can only be claimed once per process, so registering them in two places would
clash.
"""

from playbook.blocks.core import BlockDims, ConfigSchema, DataRecord, MantaBlock
from playbook.blocks.registry import register


class FakeConfig(ConfigSchema):
    label: str = ""
    source: DataRecord | None = None


class FakeBlock(MantaBlock[FakeConfig]):
    """Adds a label to the record's url, and nothing else."""

    ENV = "default"
    CONFIG = FakeConfig
    DIMS = BlockDims()
    INPUTS = frozenset()

    def run(self, record: DataRecord, output_base: str) -> DataRecord:
        suffix = self.config.label or type(self).__name__
        return DataRecord(url=f"{record.url}+{suffix}")


@register("fake_passthrough")
class FakePassthrough(FakeBlock):
    """Changes no dimensions, so it can be used as often as a playbook likes."""


@register("fake_adds_clustered")
class FakeAddsClustered(FakeBlock):
    DIMS = BlockDims(adds=frozenset({"clustered"}))


@register("fake_requires_investment_period")
class FakeRequiresInvestmentPeriod(FakeBlock):
    DIMS = BlockDims(requires=frozenset({"investment_period"}))


@register("fake_removes_investment_period")
class FakeRemovesInvestmentPeriod(FakeBlock):
    DIMS = BlockDims(
        requires=frozenset({"investment_period"}),
        removes=frozenset({"investment_period"}),
    )


@register("fake_needs_upstream")
class FakeNeedsUpstream(FakeBlock):
    INPUTS = frozenset({"source"})

    def run(self, record: DataRecord, output_base: str) -> DataRecord:
        source_url = self.config.source.url if self.config.source else "none"
        return DataRecord(url=f"{record.url}+needs({source_url})")


class StrictConfig(ConfigSchema):
    required_field: int


@register("fake_strict_config")
class FakeStrictConfig(FakeBlock):
    CONFIG = StrictConfig

    def run(self, record: DataRecord, output_base: str) -> DataRecord:
        return DataRecord(url=f"{record.url}+strict({self.config.required_field})")


@register("fake_writes_output")
class FakeWritesOutput(FakeBlock):
    """Points its result at the place it was asked to write, like a real block."""

    def run(self, record: DataRecord, output_base: str) -> DataRecord:
        return DataRecord(url=f"{output_base}.txt")


@register("fake_other_env")
class FakeOtherEnv(FakeBlock):
    """Claims an environment nothing runs in, for testing hand-off between them."""

    ENV = "elsewhere"


@register("fake_explodes")
class FakeExplodes(FakeBlock):
    """Fails if it is ever run, to prove that something never runs it."""

    def run(self, record: DataRecord, output_base: str) -> DataRecord:
        raise AssertionError("this block should never have been run")
