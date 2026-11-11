# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

from collections.abc import Sequence
from typing import Any, Literal, Self

from playbook.blocks.core import ConfigSchema
from pydantic import Field, computed_field, model_validator

from playbook_library import linopy_configs

try:
    # `pypsa.optimize.piecewise` only exists on an as-yet-unreleased pypsa feature
    # branch; fall back to `Any` until it lands in a released version.
    from pypsa.optimize.piecewise import PiecewiseOptions
except ImportError:
    PiecewiseOptions = Any


class _PyPSAOptimizeTransmissionLossesSchema(ConfigSchema):
    # TODO: separate into different pydantic models per mode, which we can switch between
    mode: Literal["secant", "tangent"] = "secant"
    """Linear approximation method."""

    atol: float = 1.0
    """Absolute tolerance in `secant` mode."""

    rtol: float = 0.1
    """Relative tolerance in `secant` mode."""

    max_segments: int = 20
    """Maximum number of segments in `secant` mode."""

    segments: int | None = None
    """Exact number of segments in `tangent` mode"""

    @model_validator(mode="after")
    def tangent_mode_must_have_segments(self: Self) -> Self:
        if self.mode == "tangent" and self.segments is None:
            raise ValueError("Must define number of segments in `tangent` mode.")
        return self


class PyPSAOptimizeSchema(ConfigSchema):
    # TODO: dynamically generate this schema from the PyPSA optimize function
    # signature, so that we don't have to maintain it manually.
    snapshots: Sequence | None = None
    """A list of snapshots to optimise, must be a subset of n.snapshots, defaults to n.snapshots"""

    multi_investment_periods: bool = False
    """Whether to optimise as a single investment period or to optimise in multiple investment
    periods.

    If multiple investment periods requested, the `period` dimension must exist in the
    model data.
    """

    transmission_losses: _PyPSAOptimizeTransmissionLossesSchema | None = None
    """Include piecewise linear approximation of transmission losses for passive branches

    See `https://go.pypsa.org/transmission-losses` for details.
    """

    linearized_unit_commitment: bool = False
    """Whether to optimise using the linearised unit commitment formulation or not."""

    model_kwargs: linopy_configs.LinopyModelSchema = Field(
        default_factory=linopy_configs.LinopyModelSchema
    )
    """Keyword arguments passed to the `linopy` `Model` instantiation."""

    # extra_functionality: Callable | None = None # we do not allow this in blocks

    assign_all_duals: bool = False
    """Whether to assign all dual values or only those that already have a designated place in the
    network."""

    solver_name: Literal["highs"] = "highs"
    """Name of the solver to use."""

    # log_to_console: bool | None = None, # we do not allow this in blocks

    # compute_infeasibilities: bool = False # we do not allow this in MVP blocks

    include_objective_constant: bool = True
    """Whether to include the objective constant (capital costs of existing infrastructure) as a
    variable in the objective function.

    Setting to False improves LP numerical conditioning, but the objective then leaves out the
    capital costs of what already exists."""

    committable_big_m: float | None = None
    """Big-M value for committable+extendable constraints.

    If None, PyPSA infers a scale from the network (e.g. peak load).
    Otherwise this numeric bound is used when no component-specific limit (p_nom_max) is available.
    """

    meshed_thresholds: Sequence[int] = Field(default_factory=lambda: [30, 100, 400])
    """Thresholds for splitting buses into nodal-balance constraint groups by bus connectivity
    count."""

    piecewise_options: list[PiecewiseOptions] = Field(default_factory=list)
    """Options to override defaults in piecewise constraint formulation.

    Each operator is interpreted as ``y operator f(x)``.
    """

    @computed_field
    def solver_options(self) -> linopy_configs.HighsOptions:
        """Settings to pass to the solver."""
        return linopy_configs.HighsOptions()


class PyPSAOptimizeRollingHorizonConfig(PyPSAOptimizeSchema):
    # TODO: dynamically generate this schema from the PyPSA
    # optimize.optimize_with_rolling_horizon function signature, so that we don't have
    # to maintain it manually.
    horizon: int = 100
    """Number of snapshots to consider in each iteration."""

    overlap: int = 0
    """Number of snapshots to overlap between two iterations.

    Results of overlapping snapshots will be superseded by those provided by the next
    iteration(s)."""

    @model_validator(mode="after")
    def overlap_must_be_shorter_than_horizon(self: Self) -> Self:
        if self.overlap >= self.horizon:
            raise ValueError("`overlap` must be smaller than `horizon`.")
        return self


class Aggregation(ConfigSchema):
    snapshot: str | None = Field(None, json_schema_extra={"x-uses-property": "snapshot"})
    """The time aggregation to solve by: the `name` given to an earlier `time_partition` block.

    A time aggregation groups the snapshots into clusters, and the block solves one
    snapshot per cluster. The results cover every snapshot, spread over the cluster each
    falls in. A model without that time aggregation is refused. None solves every snapshot.
    A time aggregation cannot be combined with `optimize_config.snapshots`.
    """

    bus: str | None = Field(None, json_schema_extra={"x-uses-property": "bus"})
    """The bus property to merge buses by, such as `country`.

    Buses with the same value merge into the first of them. Lines between the same merged
    buses merge, span the distance between those buses and take the impedances of their
    type. Land-use limits at buses that merge add up. The results of each bus are those of
    the bus it merged into. None keeps every bus.
    """

    entity: str | None = Field(None, json_schema_extra={"x-uses-property": "entity"})
    """The entity property to merge assets by, such as `carrier`.

    Assets merge where they share this value, their component and every bus they connect
    to. Candidates, by the entity property `asset_status`, merge only with the same build
    year and lifetime. Other assets merge across build years with those active in the same
    investment periods, as PyPSA-Eur merges power plants, and retire with the first of
    them. An asset without a value is kept apart or left out, as
    `ungrouped` says. Capacities and dispatch are split back over the assets by their
    largest possible capacity if extendable candidates, or their capacity if not, or
    equally where one of them has no limit. None keeps every asset.
    """

    ungrouped: Literal["keep", "drop"] = "keep"
    """What to do with a generator, load, storage unit or store without a value of the
    `entity` property.

    `keep` solves it apart from the others, at its merged bus. `drop` leaves it out of the
    solve, and it keeps its capacity and carries no flow, so a dropped load takes its
    demand out of the solve. Links and lines without a value are always kept. `drop`
    needs `entity` to be set.
    """

    clip_p_max_pu: float | None = Field(None, ge=0.0)
    """The threshold at or below which time-varying availabilities are set to 0, after
    every other aggregation, as PyPSA-Eur's `solving.options.clip_p_max_pu` sets them.

    It applies to the `p_max_pu` and `p_min_pu` series of generators and links, and the
    `inflow` series of storage units, by their absolute value. Static values are left as
    they are. It applies with or without any other aggregation. Results split back over
    the assets are judged against their unclipped values, so a dispatch may fall below
    an unclipped `p_min_pu` by up to the threshold. PyPSA-Eur sets 0.01. None
    leaves every value as it is.
    """

    @model_validator(mode="after")
    def drop_needs_entity(self: Self) -> Self:
        if self.ungrouped == "drop" and self.entity is None:
            raise ValueError("`ungrouped: drop` needs `entity` to be set.")
        return self


class PyPSAOptimizeBlockConfig(ConfigSchema):
    optimize_config: PyPSAOptimizeSchema = Field(default_factory=PyPSAOptimizeSchema)
    aggregation: Aggregation = Field(default_factory=Aggregation)
    """What to merge before solving: snapshots, buses or assets, each by a property of the
    model.

    Buses merge first, then assets, then snapshots. The results cover the model at full
    resolution.
    """

    @model_validator(mode="after")
    def snapshots_are_not_chosen_with_a_time_aggregation(self: Self) -> Self:
        if self.aggregation.snapshot is not None and self.optimize_config.snapshots is not None:
            raise ValueError(
                "`optimize_config.snapshots` cannot be set together with `aggregation.snapshot`."
            )
        return self


class LoadSheddingConfig(ConfigSchema):
    marginal_cost: float = 100.0
    """The cost of shedding one unit of load, in the unit `sign` sets."""

    p_nom: float = 1e9
    """The most load each bus can shed, in the unit `sign` sets."""

    sign: float = 1e-3
    """The scale of shed load against the model's power unit.

    With power in MW, 1e-3 counts shed load in kW.
    """
