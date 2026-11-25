# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Stand-in blocks for testing, which need nothing but datarecord installed.

Each one commits an empty revision on top of the one it was given, labelled with its
name, so the lineage of a finished run reads as a record of which blocks ran and in
what order.

They are registered here, once, and shared by the tests for both packages: a block
name can only be claimed once per process, so registering them in two places would
clash.
"""

from contextlib import closing

from datarecord import Revision, Schema, WorkingRecord, Workspace

from playbook.blocks.core import BlockDims, ConfigSchema, MantaBlock, RevisionRef
from playbook.blocks.registry import BlockSpec, register
from playbook.blocks.run import open_revision


class _Empty:
    """A record holding nothing, to root a store on."""

    schema = Schema()

    def axes(self) -> set:
        return set()

    def axis(self, dim: str) -> None:
        return None

    def attributes(self) -> set:
        return set()

    def attribute(self, name: str) -> None:
        return None


def commit_root(store: str) -> RevisionRef:
    """A fresh root revision in `store`, with no steps behind it."""
    with closing(Workspace()) as workspace:
        root = workspace.store(store).commit(_Empty(), parent=None, meta={"label": "root"})
        return RevisionRef.from_revision(root)


def commit_step(base: Revision, label: str) -> Revision:
    """A new, empty revision on top of `base`, labelled as the step that made it."""
    return base.store.commit(WorkingRecord(base.record), meta={"label": label})


def _steps(revision: Revision) -> list[str]:
    return [revision.store.revision(id).meta["label"] for id in revision.ancestry()[1:]]


def steps(ref: RevisionRef) -> list[str]:
    """The labels of the steps that led from the root to `ref`, oldest first."""
    with closing(Workspace()) as workspace:
        return _steps(open_revision(workspace, ref))


class FakeConfig(ConfigSchema):
    label: str = ""


class FakeBlock(MantaBlock[FakeConfig]):
    """Commits a labelled revision on top of its input, and nothing else."""

    ENV = "default"
    CONFIG = FakeConfig
    DIMS = BlockDims()

    def run(self, base: Revision) -> Revision:
        return commit_step(base, self.config.label or type(self).__name__)


@register("fake_passthrough")
class FakePassthrough(FakeBlock):
    """Changes no dimensions, so it can be used as often as a playbook likes."""


@register("fake_adds_clustered")
class FakeAddsClustered(FakeBlock):
    DIMS = BlockDims(adds=frozenset({"clustered"}))


@register("fake_requires_period")
class FakeRequiresInvestmentPeriod(FakeBlock):
    DIMS = BlockDims(requires=frozenset({"period"}))


@register("fake_removes_period")
class FakeRemovesInvestmentPeriod(FakeBlock):
    DIMS = BlockDims(
        requires=frozenset({"period"}),
        removes=frozenset({"period"}),
    )


class StrictConfig(ConfigSchema):
    required_field: int


@register("fake_strict_config")
class FakeStrictConfig(FakeBlock):
    CONFIG = StrictConfig

    def run(self, base: Revision) -> Revision:
        return commit_step(base, f"strict({self.config.required_field})")


class OptionalGroupConfig(ConfigSchema):
    size: int = 1


class NestedSettingsConfig(ConfigSchema):
    group: OptionalGroupConfig | None = None


@register("fake_nested_settings")
class FakeNestedSettings(FakeBlock):
    """Has an optional group of settings, shaped like a real block's solver options."""

    CONFIG = NestedSettingsConfig


@register("fake_other_env")
class FakeOtherEnv(FakeBlock):
    """Claims an environment nothing runs in, for testing hand-off between them."""

    ENV = "elsewhere"


@register("fake_explodes")
class FakeExplodes(FakeBlock):
    """Fails if it is ever run, to prove that something never runs it."""

    def run(self, base: Revision) -> Revision:
        raise AssertionError("this block should never have been run")


class RecordingRunner:
    """Hands back made-up revisions without opening a store, keeping every call."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def run_block(
        self,
        block: BlockSpec,
        *,
        step_path: tuple[str, ...],
        config: dict,
        revision: RevisionRef,
    ) -> RevisionRef:
        self.calls.append(
            {"block": block.name, "step_path": step_path, "config": config, "revision": revision}
        )
        return RevisionRef(store=f"{revision.store}/{step_path[-1]}", id=revision.id)
