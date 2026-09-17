# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

from collections.abc import Sequence
from typing import Any, Literal, Self

from pydantic import Field, computed_field, model_validator

from blocks.core import ConfigSchema
from blocks.library import linopy_configs

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
    # TODO: dynamically generate this schema from the PyPSA optimize function signature, so that we don't have to maintain it manually.
    snapshots: Sequence | None = None
    """A list of snapshots to optimise, must be a subset of n.snapshots, defaults to n.snapshots"""

    multi_investment_periods: bool = False
    """Whether to optimise as a single investment period or to optimise in multiple investment periods.

    If multiple investment periods requested, the `investment_period` dimension must exist in the model data.
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
    """Whether to assign all dual values or only those that already have a designated place in the network."""

    solver_name: Literal["highs"] = "highs"
    """Name of the solver to use."""

    # log_to_console: bool | None = None, # we do not allow this in blocks

    # compute_infeasibilities: bool = False # we do not allow this in MVP blocks

    include_objective_constant: bool = False
    """Whether to include the objective constant (capital costs of existing infrastructure) as a variable in the objective function.

    Setting to False improves LP numerical conditioning."""

    committable_big_m: float | None = None
    """Big-M value for committable+extendable constraints.

    If None, PyPSA infers a scale from the network (e.g. peak load).
    Otherwise this numeric bound is used when no component-specific limit (p_nom_max) is available.
    """

    meshed_thresholds: Sequence[int] = Field(default_factory=lambda: [30, 100, 400])
    """Thresholds for splitting buses into nodal-balance constraint groups by bus connectivity count."""

    piecewise_options: list[PiecewiseOptions] = Field(default_factory=list)
    """Options to override defaults in piecewise constraint formulation.

    Each operator is interpreted as ``y operator f(x)``.
    """

    @computed_field
    def solver_options(self) -> linopy_configs.HighsOptions:
        """Settings to pass to the solver."""
        return linopy_configs.HighsOptions()


class PyPSAOptimizeRollingHorizonConfig(PyPSAOptimizeSchema):
    # TODO: dynamically generate this schema from the PyPSA optimize.optimize_with_rolling_horizon function signature, so that we don't have to maintain it manually.
    horizon: int = 100
    """Number of snapshots to consider in each iteration."""

    overlap: int = 0
    """Number of snapshots to overlap between two iterations.

    Results of overlapping snapshots will be superseded by those provided by the next iteration(s)."""
