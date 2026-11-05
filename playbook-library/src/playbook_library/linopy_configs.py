# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

from typing import Literal

from playbook.blocks.core import ConfigSchema


class LinopyModelSchema(ConfigSchema):
    # TODO: dynamically generate this schema from the linopy Model init signature, so
    # that we don't have to maintain it manually.
    solver_dir: str | None = None
    """Path where temporary files like the lp file or solution file should be stored.
    The default None results in taking the default temporary directory."""

    chunk: int | None = None
    """Chunksize used when assigning data, this can speed up large programs while keeping
    memory-usage low."""

    force_dim_names: bool = False
    """Whether assigned variables, constraints and data should always have custom dimension names,
    i.e. not matching dimension names "dim_0", "dim_1" and so on.
    These help to avoid unintended broadcasting over dimension."""

    auto_mask: bool = False
    """Whether to automatically mask variables and constraints where bounds, coefficients, or RHS
    values contain NaN. """

    freeze_constraints: bool = False
    """Whether constraints added to the model should be frozen to the CSR-backed representation by
    default."""

    set_names_in_solver_io: bool = True
    """Whether direct solver exports should include variable and constraint names by default."""


class HighsOptions(ConfigSchema):
    # TODO: dynamically generate this schema from the given Highs version, so that we
    # don't have to maintain it manually.
    solver: Literal["simplex", "ipm", "hipo"] = "hipo"
    parallel: Literal["on", "off"] = "on"
    primal_feasibility_tolerance: float = 1.0e-05
    dual_feasibility_tolerance: float = 1.0e-05
    random_seed: int = 123
    run_crossover: Literal["on", "off"] = "off"
