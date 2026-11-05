# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Fixtures shared by the tests that run real blocks.

Each test gets one datarecord workspace, closed when it ends, and every revision it
reads or writes is opened on it.
"""

import json
import shutil
from collections.abc import Callable, Iterator
from contextlib import closing
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlencode
from urllib.request import urlopen, urlretrieve
from uuid import UUID

import pytest

if TYPE_CHECKING:
    import pypsa
    from datarecord import Revision, Workspace

PUBLIC_OBJECTS = "https://storage.googleapis.com/storage/v1/b/manta-public-test-data/o"


@pytest.fixture
def workspace() -> Iterator["Workspace"]:
    from datarecord import Workspace

    with closing(Workspace()) as ws:
        yield ws


@pytest.fixture
def store_revision(tmp_path: Path, workspace: "Workspace") -> Callable[..., "Revision"]:
    """Write a network as the root revision of a new store, named `name`, under tmp_path."""
    from playbook_library.pypsa_helpers import store_network

    def write(n, name: str) -> "Revision":
        return store_network(n, workspace.store(str(tmp_path / name)))

    return write


@pytest.fixture
def single_period(store_revision) -> "Revision":
    """Store a network of one bus, one extendable generator and a day of demand."""
    from playbook_library.examples import build_example_network

    return store_revision(build_example_network(), "base")


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
        return n

    return build


@pytest.fixture
def multi_period_network(new_multi_period_network) -> "pypsa.Network":
    """Build the network of three investment periods that `new_multi_period_network` builds."""
    return new_multi_period_network()


@pytest.fixture
def multi_period(store_revision, multi_period_network) -> "Revision":
    return store_revision(multi_period_network, "periods")


@pytest.fixture(scope="session")
def public_store(tmp_path_factory) -> Callable[[str], Path]:
    """Return a function that downloads a store of the public test data, once a session.

    The function takes the store's folder name in the bucket, and returns its local path.
    """
    stores: dict[str, Path] = {}

    def download(name: str) -> Path:
        if name in stores:
            return stores[name]
        store_dir = tmp_path_factory.mktemp(name)
        prefix = f"{name}/"
        with urlopen(f"{PUBLIC_OBJECTS}?{urlencode({'prefix': prefix})}") as response:
            listing = json.load(response)
        for item in listing["items"]:
            target = store_dir / item["name"].removeprefix(prefix)
            target.parent.mkdir(parents=True, exist_ok=True)
            urlretrieve(item["mediaLink"], target)
        stores[name] = store_dir
        return store_dir

    return download


@pytest.fixture
def public_revision(
    tmp_path: Path, public_store, workspace: "Workspace"
) -> Callable[[str], "Revision"]:
    """Return a function that copies a store of the public test data under `tmp_path`.

    The function takes the store's folder name, and opens its `inputs` revision.
    """

    def copy(name: str) -> "Revision":
        store_dir = tmp_path / name
        shutil.copytree(public_store(name), store_dir)
        revisions = json.loads((store_dir / "revisions.json").read_text())
        return workspace.store(str(store_dir)).revision(UUID(revisions["inputs"]))

    return copy


@pytest.fixture
def bel(public_revision) -> "Revision":
    """Copy BEL as PyPSA-Eur segments it, with 730 segments in each of three investment periods."""
    return public_revision("BEL-pre-aggregated")


@pytest.fixture
def bel_hourly(public_revision) -> "Revision":
    """Copy BEL at hourly resolution, over three investment periods."""
    return public_revision("BEL-pre-aggregated-hourly")
