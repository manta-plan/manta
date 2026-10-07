# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

import pypsa
from playbook.blocks.core import BlockDims, ConfigSchema, DataRecord, MantaBlock
from pydantic import model_validator

from playbook_library.pypsa_helpers import to_network, write_network


class ClusterTimeConfig(ConfigSchema):
    segments: int | None = None
    """Group the time series into this many stretches of similar conditions.

    Stretches can be of different lengths, so a few hours of unusual weather are kept
    apart from a long stretch of ordinary weather.
    """

    n_hours: int | None = None
    """Group the time series into even blocks of this many hours."""

    @model_validator(mode="after")
    def exactly_one_way_to_cluster(self):
        if (self.segments is None) == (self.n_hours is None):
            raise ValueError("Exactly one of segments or n_hours must be set")
        return self


class ClusterTime(MantaBlock[ClusterTimeConfig]):
    """Shorten a model's time series, so later blocks have less to solve."""

    ENV = "pypsa"
    CONFIG = ClusterTimeConfig
    DIMS = BlockDims(requires=frozenset({"snapshot"}))

    def cluster(self, n: pypsa.Network) -> pypsa.Network:
        if self.config.segments is not None:
            return n.cluster.temporal.segment(self.config.segments)
        return n.cluster.temporal.resample(f"{self.config.n_hours}h")

    def run(self, record: DataRecord, output_base: str) -> DataRecord:
        n_new = self.cluster(to_network(record))
        return write_network(n_new, output_base)
