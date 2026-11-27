# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Toy networks that more than one test module stores and solves."""

import numpy as np
import pandas as pd
import pypsa

from playbook_library.pypsa_spatial_aggregation import ENTITY_COMPONENTS

SOLAR = ["solar_a", "solar_b"]
GAS = ["gas_c", "gas_d"]
HYDRO = ["hydro_a", "hydro_b"]
BATTERIES = ["bat_a", "bat_b"]
LOADS = ["load_a", "load_b"]
ASSETS = [*ENTITY_COMPONENTS, "Line"]


def set_status(n: pypsa.Network, status: str | None = None) -> pypsa.Network:
    """Mark each asset of `n` as `status`, or a candidate if extendable and existing if not."""
    for c in n.components[ASSETS]:
        extendable = c.static.filter(like="nom_extendable").any(axis=1)
        c.static["asset_status"] = status or np.where(extendable, "candidate", "existing")
    return n


def new_zoned_network() -> pypsa.Network:
    """Build buses `a` and `b` in zone north, `c` and `d` in zone south, with assets to merge.

    Line `db` runs south to north, against `ac`. Link `loop` stays within the north.
    Extendable assets are candidates, and the others exist.
    """
    n = pypsa.Network()
    n.set_snapshots(pd.date_range("2030-01-01", periods=6, freq="h"))
    n.add("Carrier", ["AC", "solar", "hydro", "gas", "battery", "DC", "electricity"])
    n.add("Bus", ["a", "b", "c", "d"], x=[0, 1, 0, 1], y=[1, 1, 0, 0], carrier="AC")
    n.buses["zone"] = ["north", "north", "south", "south"]
    n.add(
        "Line",
        ["ab", "ac", "db", "cd"],
        bus0=["a", "a", "d", "c"],
        bus1=["b", "c", "b", "d"],
        s_nom=[100.0, 100.0, 300.0, 100.0],
        x=0.1,
        r=0.01,
        carrier="AC",
    )
    profiles = pd.DataFrame(
        {"solar_a": [0, 0.5, 1, 0.5, 0, 0.2], "solar_b": [0, 0.2, 0.8, 1, 0.4, 0]}, n.snapshots
    )
    n.add(
        "Generator",
        SOLAR,
        bus=["a", "b"],
        carrier="solar",
        p_nom=[10.0, 30.0],
        p_nom_max=[100.0, 300.0],
        p_nom_extendable=True,
        capital_cost=[10.0, 12.0],
        p_max_pu=profiles,
    )
    n.add(
        "Generator",
        GAS,
        bus=["c", "d"],
        carrier="gas",
        p_nom_extendable=True,
        capital_cost=0.1,
        marginal_cost=[10.0, 12.0],
    )
    n.add(
        "Generator", HYDRO, bus=["a", "b"], carrier="hydro", p_nom=[10.0, 30.0], marginal_cost=5.0
    )
    n.add(
        "Load", [*LOADS, "load_d"], bus=["a", "b", "d"], carrier="electricity", p_set=[20, 40, 60]
    )
    n.add(
        "StorageUnit",
        BATTERIES,
        bus=["a", "b"],
        carrier="battery",
        p_nom=[5.0, 15.0],
        p_nom_max=[50.0, 150.0],
        p_nom_extendable=True,
        capital_cost=10.0,
        max_hours=2,
        cyclic_state_of_charge=True,
    )
    n.add("Store", ["st_c", "st_d"], bus=["c", "d"], carrier="battery", e_nom_extendable=True)
    n.add(
        "Link",
        ["dc", "loop"],
        bus0="a",
        bus1=["d", "b"],
        carrier="DC",
        p_nom=20.0,
        length=[300.0, 50.0],
        capital_cost=[30.0, 5.0],
    )
    return set_status(n)
