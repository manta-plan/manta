# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Fixtures shared by the tests that run real blocks."""

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from playbook.blocks.core import DataRecord

from playbook_library.examples import inputs_record
from playbook_library.public_data import download_public_store

if TYPE_CHECKING:
    import pypsa


@pytest.fixture(scope="session")
def store_network() -> Callable[["pypsa.Network", str], DataRecord]:
    """Return a function that stores a network as the root revision of a new store at a URL."""
    from datarecord import Workspace
    from datarecord.tools.pypsa import PyPSA

    def store(n: "pypsa.Network", url: str) -> DataRecord:
        ws = Workspace()
        rev = ws.store(url).commit(PyPSA.to_datarecord(n, ws.con), parent=None)
        return DataRecord(url=url, uuid=rev.id)

    return store


@pytest.fixture
def store_record(tmp_path: Path, store_network) -> Callable[["pypsa.Network", str], DataRecord]:
    """Write a network as the root revision of a new store, named `name`, under tmp_path."""

    def write(n: "pypsa.Network", name: str) -> DataRecord:
        return store_network(n, str(tmp_path / name))

    return write


@pytest.fixture
def ancestry() -> Callable[[DataRecord], list[UUID]]:
    """The revision ids from a record's store root down to the record, root first."""
    from playbook_library.datarecord_helpers import revision

    def lineage(record: DataRecord) -> list[UUID]:
        return revision(record)[1].ancestry()

    return lineage


@pytest.fixture(scope="session")
def new_single_period_network() -> Callable[[], "pypsa.Network"]:
    """Return a builder of a network of one bus, one extendable generator and a day of demand."""
    import pandas as pd
    import pypsa

    def build() -> pypsa.Network:
        n = pypsa.Network()
        n.set_snapshots(pd.date_range("2030-01-01", periods=24, freq="h"))
        n.add("Bus", "bus")
        n.add(
            "Generator",
            "gen",
            bus="bus",
            p_nom_extendable=True,
            capital_cost=100.0,
            marginal_cost=10.0,
        )
        n.add("Load", "load", bus="bus", p_set=50.0)
        n.generators["asset_status"] = "candidate"
        return n

    return build


@pytest.fixture
def single_period_record(store_record, new_single_period_network) -> DataRecord:
    """Store the network that `new_single_period_network` builds."""
    return store_record(new_single_period_network(), "base")


@pytest.fixture(scope="session")
def new_multi_period_network() -> Callable[[], "pypsa.Network"]:
    """Return a builder of a network of three investment periods, for any fixture scope."""
    import pandas as pd
    import pypsa

    def build() -> pypsa.Network:
        """Build a cheap generator, dearer ones later, and demand doubling in the last period."""
        n = pypsa.Network()
        periods = [2030, 2040, 2050]
        snapshots = pd.MultiIndex.from_product(
            [periods, pd.date_range("2030-01-01", periods=4, freq="h")],
            names=["period", "timestep"],
        )
        n.set_snapshots(snapshots)
        n.investment_periods = periods
        n.add("Bus", "bus")
        for period in periods:
            n.add(
                "Generator",
                f"gen-{period}",
                bus="bus",
                p_nom_extendable=True,
                build_year=period,
                lifetime=30,
                capital_cost=1.0 if period == 2030 else 100.0,
                marginal_cost=10.0,
            )
        n.add("Load", "load", bus="bus", p_set=pd.Series([50.0] * 8 + [100.0] * 4, index=snapshots))
        n.generators["asset_status"] = "candidate"
        return n

    return build


@pytest.fixture
def multi_period_network(new_multi_period_network) -> "pypsa.Network":
    """Build the network of three investment periods that `new_multi_period_network` builds."""
    return new_multi_period_network()


@pytest.fixture
def multi_period_record(store_record, multi_period_network) -> DataRecord:
    return store_record(multi_period_network, "periods")


@pytest.fixture(scope="session")
def public_store(tmp_path_factory) -> Callable[[str], Path]:
    """Return a function that downloads a store of the public test data, once a session.

    The function takes the store's folder name in the bucket, and returns its local path.
    """
    stores: dict[str, Path] = {}

    def download(name: str) -> Path:
        if name in stores:
            return stores[name]
        stores[name] = download_public_store(name, tmp_path_factory.mktemp(name))
        return stores[name]

    return download


@pytest.fixture
def public_record(tmp_path: Path, public_store) -> Callable[[str], DataRecord]:
    """Return a function that copies a store of the public test data under `tmp_path`.

    The function takes the store's folder name, and points a record at its `inputs`
    revision.
    """

    def copy(name: str) -> DataRecord:
        store_dir = tmp_path / name
        shutil.copytree(public_store(name), store_dir)
        return inputs_record(store_dir)

    return copy


@pytest.fixture
def bel_record(public_record) -> DataRecord:
    """Copy BEL as PyPSA-Eur segments it, with 730 segments in each of three investment periods."""
    return public_record("BEL-pre-aggregated")


@pytest.fixture
def bel_hourly_record(public_record) -> DataRecord:
    """Copy BEL at hourly resolution, over three investment periods."""
    return public_record("BEL-pre-aggregated-hourly")
