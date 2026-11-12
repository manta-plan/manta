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
    """Snapshots to solve, a subset of the model's snapshots. None solves all of them."""

    multi_investment_periods: bool = False
    """Solve all investment periods together. Needs a model with a `period` dimension."""

    transmission_losses: _PyPSAOptimizeTransmissionLossesSchema | None = None
    """Approximate transmission losses on passive branches (go.pypsa.org/transmission-losses)."""

    linearized_unit_commitment: bool = False
    """Use the linearised unit commitment formulation."""

    model_kwargs: linopy_configs.LinopyModelSchema = Field(
        default_factory=linopy_configs.LinopyModelSchema
    )
    """Keyword arguments passed to the `linopy` `Model` instantiation."""

    # extra_functionality: Callable | None = None # we do not allow this in blocks

    assign_all_duals: bool = False
    """Keep every dual value, not only those the network has a place for."""

    solver_name: Literal["highs"] = "highs"
    """Name of the solver to use."""

    # log_to_console: bool | None = None, # we do not allow this in blocks

    # compute_infeasibilities: bool = False # we do not allow this in MVP blocks

    include_objective_constant: bool = True
    """Include the capital cost of existing assets in the objective."""

    committable_big_m: float | None = None
    """Big-M for committable, extendable assets without `p_nom_max`. None lets PyPSA infer it."""

    meshed_thresholds: Sequence[int] = Field(default_factory=lambda: [30, 100, 400])
    """Bus connectivity thresholds that group the nodal balance constraints."""

    piecewise_options: list[PiecewiseOptions] = Field(default_factory=list)
    """Overrides for piecewise constraints, each read as `y operator f(x)`."""

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
    """Snapshots shared by two windows. The later window's results replace the earlier ones."""

    @model_validator(mode="after")
    def overlap_must_be_shorter_than_horizon(self: Self) -> Self:
        if self.overlap >= self.horizon:
            raise ValueError("`overlap` must be smaller than `horizon`.")
        return self


class Aggregation(ConfigSchema):
    snapshot: str | None = Field(None, json_schema_extra={"x-uses-property": "snapshot"})
    """Time aggregation to solve by: the `name` of an earlier `time_partition` step."""

    bus: str | None = Field(None, json_schema_extra={"x-uses-property": "bus"})
    """Bus property to merge buses by, such as `country`."""

    entity: str | None = Field(None, json_schema_extra={"x-uses-property": "entity"})
    """Entity property to merge assets by, such as `carrier`."""

    ungrouped: Literal["keep", "drop"] = "keep"
    """What to do with an asset that has no `entity` value: solve it alone, or leave it out."""

    clip_p_max_pu: float | None = Field(None, ge=0.0)
    """Set availability values at or below this threshold to 0, as PyPSA-Eur does."""

    @model_validator(mode="after")
    def drop_needs_entity(self: Self) -> Self:
        if self.ungrouped == "drop" and self.entity is None:
            raise ValueError("`ungrouped: drop` needs `entity` to be set.")
        return self


class PyPSAOptimizeBlockConfig(ConfigSchema):
    optimize_config: PyPSAOptimizeSchema = Field(default_factory=PyPSAOptimizeSchema)
    aggregation: Aggregation = Field(default_factory=Aggregation)
    """Merge buses, assets and snapshots before solving. Results cover the full model."""

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
    """Scale of shed load against the model's power unit; 1e-3 turns MW into kW."""
