# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""A PyPSA network as a record whose schema follows OGSchema, and back.

The tests read PyPSA's AC-DC meshed example, typed for OGSchema and stored as the root of a
store. With every capacity extendable its assets are Investments technologies, and with
every capacity fixed they are Operations devices. PyPSA's model-energy example adds storage
and load shedding, and a small network has what the PyPSA-Earth model of Zambia has:
reservoir hydro, a line of a standard type, an exchange with a neighbour, load shedding
at every bus and a global constraint without an OGSchema type. Another has what the
PyPSA-Eur model of Belgium has: investment periods, a cohort of each technology per period,
limits on CO2 and on capacity per period, costs that vary in time, and shapes.
"""

import json
import os
from collections.abc import Collection
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

pypsa = pytest.importorskip("pypsa", reason="the OGSchema tool needs PyPSA installed")

import numpy as np
import pandas as pd
import shapely
from datarecord import WorkingRecord, Workspace
from datarecord.tools.base import UnsupportedRecordError
from playbook.blocks.core import DataRecord

from playbook_library.datarecord_helpers import revision
from playbook_library.ogschema.examples import (
    AC_DC_MESHED_CARRIERS,
    BEL_CARRIERS,
    MODEL_ENERGY_BUSES,
    MODEL_ENERGY_CARRIERS,
    ZMB_CARRIERS,
    ac_dc_meshed,
    model_energy,
)
from playbook_library.ogschema.pypsa import OG_COLUMNS, OGSchema, Technology, classify
from playbook_library.ogschema.validation import violations
from playbook_library.overnight_capacity_expansion import OvernightCapacityExpansion
from playbook_library.pypsa_helpers import to_network
from playbook_library.rolling_horizon_dispatch import RollingHorizonDispatch
from playbook_library.time_partition import TimePartition

pytestmark = pytest.mark.pypsa

TOPOLOGY = {"ACBus", "DCBus", "GeographicInfo", "EmissionsData", "PowerLoad", "CarbonCaps"}
TECHNOLOGIES = {"SupplyTechnology", "NodalACTransportTechnology", "NodalHVDCTransportTechnology"}
DEVICES = {
    "ThermalStandard",
    "RenewableDispatch",
    "Line",
    "TModelHVDCLine",
    "InterconnectingConverter",
    "TwoTerminalGenericHVDCLine",
    "Arc",
}
FINANCIAL_DATA = {
    "capital_recovery_period",
    "technology_base_year",
    "debt_fraction",
    "debt_rate",
    "return_on_equity",
    "tax_rate",
    "discount_rate",
    "inflation_rate",
    "interest_rate",
}
UNFILLED = {
    "SupplyTechnology": 6,
    "NodalACTransportTechnology": 4,
    "NodalHVDCTransportTechnology": 7,
}


def _fixed(n: pypsa.Network) -> pypsa.Network:
    """Fix every capacity of `n`, and lift its CO2 cap far enough for it to stay feasible."""
    for c in n.components:
        extendable = c.static.filter(like="_nom_extendable").columns
        c.static[extendable] = False
    n.global_constraints["constant"] = 1e9
    return n


def _mixed(n: pypsa.Network) -> pypsa.Network:
    """Fix some capacities of `n`, and set values and series that OGSchema has no field for."""
    snapshots = n.snapshots
    fixed = {"Generator": ["Norway Gas", "Frankfurt Wind"], "Line": ["0", "2"]}
    fixed["Link"] = ["Norwich Converter", "Norway Converter"]
    for cls, names in fixed.items():
        c = n.components[cls]
        c.static.loc[names, c.static.filter(like="_nom_extendable").columns] = False
    reversed_ends = n.links.loc["Norway Converter", ["bus1", "bus0"]].to_numpy()
    n.links.loc["Norway Converter", ["bus0", "bus1"]] = reversed_ends
    n.links.loc["Bremen Converter", "efficiency"] = 0.97
    n.links.loc["DC link", ["efficiency", "marginal_cost"]] = [0.95, 0.5]
    n.generators.loc["Norway Gas", ["p_min_pu", "start_up_cost", "lifetime"]] = [0.005, 7.0, 30.0]
    n.generators.loc["Frankfurt Wind", "p_max_pu"] = 0.9
    financed = ["overnight_cost", "discount_rate", "lifetime", "p_nom_max"]
    n.generators.loc["Manchester Gas", financed] = [1e6, 0.07, 25.0, 9e4]
    n.generators["asset_status"] = pd.Series("existing", index=n.generators.index, dtype=object)
    n.lines.loc["0", ["length", "b", "s_max_pu", "v_ang_max"]] = [120.0, 1e-4, 0.7, 30.0]
    n.loads.loc["Norwich", "p_set"] = 3.0
    n.buses.loc["London", "v_mag_pu_set"] = 1.02
    n.snapshot_weightings.loc[snapshots[:3], "objective"] = 2.0
    n.loads_t.q_set = n.loads_t.p_set[["London"]] * 0.1
    n.generators_t.p_min_pu = pd.DataFrame({"Norway Gas": 0.001}, index=snapshots)
    costs = {"Manchester Gas": 4.0 + np.arange(10) / 10, "Frankfurt Wind": 0.2}
    n.generators_t.marginal_cost = pd.DataFrame(costs, index=snapshots)
    n.global_constraints["constant"] = 1e9
    return n


OFFSHORE = {
    "offwind-ac": Technology("RenewableDispatch", prime_mover_type="WS"),
    "offwind-float": Technology("RenewableDispatch", prime_mover_type="WS", group="float"),
}


def _grouped(carriers: dict[str, Technology]) -> pypsa.Network:
    """Return the example with two offshore wind carriers, typed by `carriers`."""
    n = pypsa.examples.ac_dc_meshed()
    n.add("Carrier", ["offwind-ac", "offwind-float"])
    n.generators.loc["Norway Wind", "carrier"] = "offwind-ac"
    n.generators.loc["Frankfurt Wind", "carrier"] = "offwind-float"
    classify(n, AC_DC_MESHED_CARRIERS | carriers)
    return n


def _zambia_like() -> pypsa.Network:
    """Build two buses and a neighbour, with every kind of component the model of Zambia has."""
    n = pypsa.Network()
    hours = pd.DatetimeIndex(pd.date_range("2023-01-01", periods=24, freq="h").to_numpy())
    shape = np.sin(np.arange(24) * np.pi / 24)
    n.set_snapshots(hours)
    n.add("Carrier", ["coal", "hydro"], co2_emissions=[0.83, 0.025])
    n.add("Carrier", ["solar", "ror", "export", "import", "load shedding", "AC"])
    n.add(
        "Bus", ["north", "south", "ZW"], v_nom=330.0, x=[28.0, 28.5, 31.0], y=[-13.0, -16.0, -18.0]
    )
    n.buses["country"] = pd.Series(["ZM", "ZM", "ZW"], n.buses.index, dtype=object)
    n.add("LineType", "bison", f_nom=50.0, r_per_length=0.04, x_per_length=0.34, c_per_length=10.8)
    n.add("Line", "1", bus0="north", bus1="south", type="bison", length=320.0, num_parallel=0.5)
    n.lines.loc["1", ["s_nom", "s_max_pu", "capital_cost"]] = [400.0, 0.7, 8000.0]
    n.add("Link", "tie", bus0="south", bus1="ZW", p_nom=150.0, p_min_pu=-1.0, carrier="AC")
    n.add("Generator", "coal", bus="north", carrier="coal", p_nom=120.0, efficiency=0.36)
    n.generators.loc["coal", ["marginal_cost", "lifetime", "build_year"]] = [72.9, 40.4, 1995]
    n.add("Generator", "coal 2", bus="south", carrier="coal", p_nom=30.0, efficiency=0.36)
    n.generators.loc["coal 2", ["marginal_cost", "build_year"]] = [72.9, 2014]
    solar = pd.DataFrame({"solar": shape}, index=hours)
    n.add("Generator", ["solar"], bus="north", carrier="solar", p_nom=60.0, p_max_pu=solar)
    n.generators.loc["solar", ["lifetime", "build_year"]] = [25.0, 2015]
    more = pd.DataFrame({"more solar": shape}, index=hours)
    n.add("Generator", ["more solar"], bus="north", carrier="solar", p_max_pu=more)
    n.generators.loc["more solar", ["p_nom_extendable", "capital_cost"]] = [True, 4e4]
    river = pd.DataFrame({"river": 0.5 + shape / 4}, index=hours)
    n.add("Generator", ["river"], bus="south", carrier="ror", p_nom=20.0, p_max_pu=river)
    n.generators.loc["river", "efficiency"] = 0.9
    n.add("Generator", "ZW export", bus="ZW", carrier="export", p_nom=14.0)
    shedding = pd.Index(n.buses.index + " load shedding")
    n.add("Generator", shedding, bus=n.buses.index, carrier="load shedding", p_nom=1e9)
    n.generators.loc[shedding, ["sign", "marginal_cost"]] = [1e-3, 100.0]
    demand = pd.DataFrame({"load-north": 150 + 60 * shape, "load-south": 90.0}, index=hours)
    n.add("Load", ["load-north", "load-south"], bus=["north", "south"], p_set=demand)
    n.add("Load", "load-ZW", bus="ZW", carrier="import", p_set=5.0)
    inflow = pd.DataFrame({"dam": 30 + 20 * shape}, index=hours)
    n.add("StorageUnit", ["dam"], bus="south", carrier="hydro", p_nom=100.0, inflow=inflow)
    reservoir = ["max_hours", "efficiency_dispatch", "efficiency_store", "p_min_pu"]
    n.storage_units.loc["dam", reservoir] = [40.3, 0.9, 0.0, 0.0]
    n.storage_units.loc["dam", ["marginal_cost", "cyclic_state_of_charge"]] = [1.05, True]
    n.add("GlobalConstraint", "lv_limit", type="transmission_volume_expansion_limit")
    n.global_constraints.loc["lv_limit", ["carrier_attribute", "sense"]] = ["AC, DC", "<="]
    n.global_constraints.loc["lv_limit", "constant"] = 5e6
    classify(n, ZMB_CARRIERS)
    return n


def _belgium_like() -> pypsa.Network:
    """Build a bus over two investment periods, with every kind of input the Belgian model has."""
    n = pypsa.Network()
    periods = [2030, 2040]
    hours = pd.date_range("2013-01-01", periods=6, freq="h")
    n.set_snapshots(pd.MultiIndex.from_product([periods, hours], names=["period", "timestep"]))
    n.investment_period_weightings = pd.DataFrame(
        {"objective": [9.2, 7.5], "years": 10.0}, index=n.investment_periods
    )
    sun = pd.Series(np.tile([0.0, 0.2, 0.7, 0.9, 0.4, 0.0], 2), n.snapshots)
    later = pd.Series(n.snapshots.get_level_values("period") == 2040, n.snapshots)
    n.add("Carrier", ["AC", "H2", "H2 Electrolysis", "H2 Fuel Cell", "solar", "electricity"])
    n.add("Carrier", "CCGT", co2_emissions=0.198)
    n.add("Bus", "north", v_nom=380.0, x=4.4, y=50.8)
    n.add("Bus", "north H2", carrier="H2", x=4.4, y=50.8)
    n.buses["country"] = pd.Series("BE", n.buses.index, dtype=object)
    n.add(
        "Load",
        ["demand"],
        bus="north",
        carrier="electricity",
        p_set=(80 + 40 * sun).to_frame("demand"),
    )
    n.add("Generator", "north CCGT old", bus="north", carrier="CCGT", p_nom=60.0)
    n.generators.loc["north CCGT old", ["build_year", "lifetime"]] = [2011, 25.0]
    n.generators_t.marginal_cost["north CCGT old"] = 55.0 - 6.0 * later
    n.generators_t.efficiency["north CCGT old"] = 0.58 + 0.01 * later
    for period, cap in zip(periods, [2000.0, 1300.0], strict=True):
        newer = (period - 2030) / 10
        cohort = {"build_year": period, "capital_cost": 9e4 - 1e4 * newer, "lifetime": 25.0}
        n.add("Generator", f"north CCGT-{period}", bus="north", carrier="CCGT", **cohort)
        gas = [0.58 + 0.02 * newer, 55.0 - 5.0 * newer, 200.0 + 100.0 * newer]
        n.generators.loc[f"north CCGT-{period}", ["efficiency", "marginal_cost", "p_nom_max"]] = gas
        solar = sun.where(later | (period == 2030), 1.0).to_frame(f"north solar-{period}")
        n.add("Generator", [f"north solar-{period}"], bus="north", carrier="solar", p_max_pu=solar)
        n.generators.loc[f"north solar-{period}", list(cohort)] = [period, 4e4 - 1e4 * newer, 40.0]
        n.add("Store", f"north H2-{period}", bus="north H2", carrier="H2", **cohort)
        ends = {"bus0": "north", "bus1": "north H2", "efficiency": 0.62 + 0.03 * newer}
        n.add(
            "Link", f"north H2 Electrolysis-{period}", carrier="H2 Electrolysis", **ends, **cohort
        )
        ends = {"bus0": "north H2", "bus1": "north", "efficiency": 0.5}
        n.add("Link", f"north H2 Fuel Cell-{period}", carrier="H2 Fuel Cell", **ends, **cohort)
        limit = {"sense": "<=", "investment_period": period}
        emitted = {"type": "primary_energy", "carrier_attribute": "co2_emissions"}
        n.add("GlobalConstraint", f"CO2Limit-{period}", constant=cap, **emitted, **limit)
        area = {
            "type": "tech_capacity_expansion_limit",
            "carrier_attribute": "solar",
            "bus": "north",
        }
        n.add("GlobalConstraint", f"land_use solar north {period}", constant=60.0, **area, **limit)
    n.generators.loc[n.generators.build_year >= 2030, "p_nom_extendable"] = True
    n.stores["e_nom_extendable"] = True
    n.links["p_nom_extendable"] = True
    n.links.loc[n.links.carrier == "H2 Fuel Cell", "lifetime"] = 10.0
    outlines = shapely.box([4.0, 2.0], [50.0, 51.0], [5.0, 6.0], [51.0, 52.0])
    n.add("Shape", ["Bus north onshore", "country BE onshore"], geometry=outlines)
    n.shapes[["component", "idx", "type"]] = [
        ["Bus", "north", "onshore"],
        ["country", "BE", "onshore"],
    ]
    classify(n, BEL_CARRIERS)
    return n


NETWORKS = {
    "extendable": ac_dc_meshed,
    "fixed": lambda: _fixed(ac_dc_meshed()),
    "mixed": lambda: _mixed(ac_dc_meshed()),
    "grouped": lambda: _grouped(OFFSHORE),
    "model-energy": model_energy,
    "zambia-like": _zambia_like,
    "belgium-like": _belgium_like,
}
SOLVED = {"model-energy": 240}
"""The number of snapshots a network is solved over, if not all, to keep the tests short."""
OPTIONS = {"belgium-like": {"multi_investment_periods": True}}
"""What a network is solved with, beside its snapshots."""


class _Records(dict):
    """The record of each of `NETWORKS`, stored when a test first reads it."""

    def __init__(self, root: Path, store) -> None:
        super().__init__()
        self.root = root
        self.store = store

    def __missing__(self, name: str) -> DataRecord:
        self[name] = self.store(NETWORKS[name](), str(self.root / name))
        return self[name]


@pytest.fixture(scope="module")
def records(tmp_path_factory, store_ogschema_network) -> dict[str, DataRecord]:
    """Return the records of `NETWORKS`, each stored once for the tests that only read it."""
    return _Records(tmp_path_factory.mktemp("ogschema"), store_ogschema_network)


RENAMED = {
    ("*", "carrier"),
    ("GlobalConstraint", "carrier_attribute"),
    ("Carrier", "*"),
    ("*", "order"),
}
"""What differs in every network built from a record: its carriers are named for the types
of its components, and its components are in the order of their types."""


def _inputs(c) -> pd.DataFrame:
    """Return the static inputs of PyPSA components, with the outline of a shape as text."""
    outputs = c.defaults.index[c.defaults.status == "Output"]
    static = c.static.drop(columns=[*outputs, *OG_COLUMNS], errors="ignore")
    if c.name != "Shape":
        return static
    return pd.DataFrame(static).assign(geometry=static.geometry.to_wkb(hex=True))


def _gap(a: np.ndarray, b: np.ndarray) -> dict[str, float]:
    """Return how many values of `a` differ from those of `b`, and by how much at most."""
    numeric = all(kind in "biuf" for kind in (a.dtype.kind, b.dtype.kind))
    if not numeric:
        blank = [np.where(pd.isna(x), "", x.astype(object)) for x in (a, b)]
        return {"cells": int((blank[0] != blank[1]).sum()), "largest": np.nan, "relative": np.nan}
    x, y = a.astype(float), b.astype(float)
    apart = ~((x == y) | (np.isnan(x) & np.isnan(y)))
    if not apart.any():
        return {"cells": 0, "largest": 0.0, "relative": 0.0}
    gap = np.nan_to_num(np.abs(x[apart] - y[apart]), nan=np.inf)
    scale = np.maximum(np.abs(x[apart]), np.abs(y[apart]))
    relative = np.nan_to_num(gap / scale, nan=np.inf)
    return {"cells": int(apart.sum()), "largest": gap.max(), "relative": relative.max()}


def _column(c, static: pd.DataFrame, name: str, like: pd.Series) -> np.ndarray:
    """Return the column `name` of `static`, or what PyPSA holds for components without it."""
    if name in static:
        return static[name].to_numpy()
    if name in c.defaults.index:
        return np.full(len(static), c.defaults.at[name, "default"], c.defaults.at[name, "dtype"])
    return np.full(len(static), np.nan if like.dtype.kind in "iuf" else "", object)


def _dense(c, attr: str, names: pd.Index) -> np.ndarray:
    """Return the series `attr` of the components `names`, static where one has none."""
    series = c.dynamic[attr]
    dense = series.reindex(columns=names)
    static = names.difference(series.columns)
    dense[static] = c.static.loc[static, attr].to_numpy()
    return dense.to_numpy()


def _emitted(n: pypsa.Network, c, names: pd.Index) -> np.ndarray:
    """Return the CO2 that the carrier of each of the components `names` of `c` emits."""
    rates = n.carriers.co2_emissions.reindex(c.static.carrier[names])
    return rates.fillna(0).to_numpy()


def _row(component: str, kind: str, attribute: str, note: str = "", **gap: float) -> dict[str, Any]:
    return {"component": component, "kind": kind, "attribute": attribute, **gap, "note": note}


def _of_the_network(built: pypsa.Network, n: pypsa.Network) -> list[dict[str, Any]]:
    """Return a row per axis, weighting and description of `n`, compared with that of `built`."""
    rows = []
    axes = {"snapshots": (n.snapshots, built.snapshots)}
    axes["investment_periods"] = (n.investment_periods, built.investment_periods)
    for name, (a, b) in axes.items():
        typed = a.dtype == b.dtype and list(a.names) == list(b.names)
        note = "" if typed else "dtype or names"
        rows.append(_row("Network", "index", name, note, cells=int(not a.equals(b))))
    weightings = {"snapshot_weightings": (n.snapshot_weightings, built.snapshot_weightings)}
    weightings["investment_period_weightings"] = (
        n.investment_period_weightings,
        built.investment_period_weightings,
    )
    for name, (a, b) in weightings.items():
        for column in a.columns.union(b.columns):
            gap = _gap(a[column].to_numpy(), b[column].to_numpy())
            rows.append(_row("Network", "static", f"{name}.{column}", **gap))
    described = {"name": (n.name, built.name), "meta": (n.meta, built.meta)}
    described["crs"] = (n.crs, built.crs)
    for name, (a, b) in described.items():
        rows.append(_row("Network", "static", name, cells=int(a != b)))
    return rows


def _of_the_statics(expected, c, common: pd.Index) -> list[dict[str, Any]]:
    """Return a row per static input of the components `common` to `expected` and `c`."""
    rows = []
    a, b = _inputs(expected).loc[common], _inputs(c).loc[common]
    for column in a.columns.union(b.columns):
        like = a[column] if column in a else b[column]
        x, y = _column(expected, a, column, like), _column(c, b, column, like)
        note = ""
        if column not in a or column not in b:
            note = "not in original" if column not in a else "not in built"
        elif x.dtype != y.dtype:
            note = f"dtype {x.dtype} in original, {y.dtype} in built"
        rows.append(_row(c.name, "static", column, note, **_gap(x, y)))
    return rows


def _of_the_series(expected, c, common: pd.Index) -> list[dict[str, Any]]:
    """Return a row per input series of the components `common` to `expected` and `c`."""
    rows = []
    inputs = expected.defaults.index[expected.defaults.status != "Output"]
    for attr in inputs.intersection(list(expected.dynamic)):
        series, restored = expected.dynamic[attr], c.dynamic[attr]
        names = series.columns.union(restored.columns).intersection(common)
        if names.empty:
            continue
        static = {"original": names.difference(series.columns)}
        static["built"] = names.difference(restored.columns)
        lacking = [f"{len(held)} static in {side}" for side, held in static.items() if len(held)]
        gap = _gap(_dense(expected, attr, names), _dense(c, attr, names))
        rows.append(_row(c.name, "series", attr, ", ".join(lacking), **gap))
    return rows


def _comparison(built: pypsa.Network, n: pypsa.Network) -> pd.DataFrame:
    """Return a row per input of `n` and `built`, with how far the one of `built` is from it.

    A row names the class of components, the kind of input and the input. `cells` counts the
    values that differ, `largest` is the largest difference and `relative` the largest as a
    share of the value. `note` says what else differs: a dtype, or a column or a series that
    one network lacks, which is compared with what PyPSA takes in its place. The rows of
    kind `index` have the number of components of each network.
    """
    rows = _of_the_network(built, n)
    for expected in n.components:
        c = built.components[expected.name]
        a, b = expected.static.index, c.static.index
        apart = len(a.symmetric_difference(b))
        rows.append(_row(c.name, "index", "index", cells=apart, original=len(a), built=len(b)))
        reordered = apart == 0 and not a.equals(b)
        rows.append(_row(c.name, "index", "order", cells=int(reordered)))
        common = a.intersection(b)
        rows += _of_the_statics(expected, c, common)
        rows += _of_the_series(expected, c, common)
        if "carrier" in expected.static and "carrier" in c.static:
            gap = _gap(_emitted(n, expected, common), _emitted(built, c, common))
            rows.append(_row(c.name, "static", "co2_emissions of the carrier", **gap))
    return pd.DataFrame(rows).fillna({"cells": 0, "largest": 0.0, "relative": 0.0})


def _unexpected(compared: pd.DataFrame, expected: Collection[tuple[str, str]]) -> pd.DataFrame:
    """Return the rows of `compared` that differ by more than rounding, less those `expected`.

    `expected` pairs a class with an input, either of which may be `*` for any.
    """
    differing = compared[
        (compared.cells > 0) & ~(compared.relative <= 1e-9) | (compared.note != "")
    ]
    pairs = zip(differing.component, differing.attribute, strict=True)
    known = [bool({(c, a), (c, "*"), ("*", a)} & set(expected)) for c, a in pairs]
    return differing[~np.array(known, dtype=bool)]


def _assert_same_inputs(
    built: pypsa.Network, n: pypsa.Network, expected: Collection[tuple[str, str]] = ()
) -> None:
    unexpected = _unexpected(_comparison(built, n), RENAMED | set(expected))
    assert unexpected.empty, unexpected.to_string()


def _resolved(n: pypsa.Network) -> pypsa.Network:
    """Return `n` as a record keeps it: lines by their impedances, lifetimes in whole years."""
    n.calculate_dependent_values()
    n.lines.loc[:, "type"] = ""
    n.generators.loc[:, "lifetime"] = n.generators.lifetime.round()
    return n


def _entities(record: DataRecord) -> pd.DataFrame:
    """Return the properties of each entity of `record`, by entity."""
    return revision(record)[1].record.properties["entity"].df().set_index("entity")


def _values(record: DataRecord, name: str) -> dict[str, float]:
    """Return the values of the attribute `name` of `record` over `entity` alone, by entity."""
    rows = revision(record)[1].record.attributes[name].df()
    return rows.set_index("entity")["value"].to_dict()


def _attribute_rows(record: DataRecord, prefix: str) -> dict[str, int]:
    """Return the number of rows of each attribute of `record` whose name contains `prefix`."""
    rec = revision(record)[1].record
    names = sorted(name for name in rec.flags() if prefix in name)
    return {name: len(rec.attributes[name].fetchall()) for name in names}


@pytest.mark.parametrize("name", list(NETWORKS))
def test_a_network_comes_back_from_its_record_as_it_went_in(name, records):
    network = NETWORKS[name]()

    built = to_network(records[name])

    _assert_same_inputs(_resolved(built), _resolved(network))
    assert built.name == network.name
    assert built.meta == network.meta
    assert built.crs == network.crs
    pd.testing.assert_frame_equal(built.snapshot_weightings, network.snapshot_weightings)


@pytest.mark.parametrize("name", list(NETWORKS))
def test_a_network_built_from_its_record_has_the_same_optimum(name, records):
    network = NETWORKS[name]()
    built = to_network(records[name])

    snapshots = network.snapshots[: SOLVED.get(name)]

    network.optimize(snapshots=snapshots, log_to_console=False, **OPTIONS.get(name, {}))
    built.optimize(snapshots=snapshots, log_to_console=False, **OPTIONS.get(name, {}))

    assert built.objective == pytest.approx(network.objective, rel=1e-6)


SCENARIOS = {
    "equal": {"w2010": 0.5, "w2013": 0.5},
    "unequal": {"w2010": 0.2, "w2013": 0.3, "w2019": 0.5},
}


def _stochastic(weights: dict[str, float]) -> pypsa.Network:
    """Return the Zambia-like network over `weights`, with less sun and inflow in each later one."""
    n = _zambia_like()
    n.set_scenarios(weights)
    for i, scenario in enumerate(weights):
        n.generators_t.p_max_pu.loc[:, (scenario, "solar")] *= 1 - i / 4
        n.storage_units_t.inflow.loc[:, (scenario, "dam")] *= 1 - i / 3
    return n


@pytest.mark.parametrize("weights", SCENARIOS.values(), ids=list(SCENARIOS))
def test_a_network_with_scenarios_comes_back_with_the_same_optimum(
    weights, store_ogschema_network, tmp_path
):
    network = _stochastic(weights)
    built = to_network(store_ogschema_network(network, str(tmp_path)))

    pd.testing.assert_frame_equal(built.scenario_weightings, network.scenario_weightings)
    for scenario in weights:
        _assert_same_inputs(
            _resolved(built.get_scenario(scenario)), _resolved(network.get_scenario(scenario))
        )
    network.optimize(log_to_console=False)
    built.optimize(log_to_console=False)
    assert built.objective == pytest.approx(network.objective, rel=1e-6)


def test_a_series_is_stored_per_scenario_only_where_the_scenarios_differ(
    store_ogschema_network, tmp_path
):
    record = store_ogschema_network(_stochastic(SCENARIOS["unequal"]), str(tmp_path))

    rec = revision(record)[1].record
    keys = "entity, scenario"
    series = ("ts__max_active_power", "ts__inflow")
    held = {row for name in series for row in rec.attributes[name].aggregate(keys, keys).fetchall()}
    weights = rec.attributes["scenario__ext__pypsa__weighting_weight"].df()

    varying = {(e, s) for e, s in held if e in {"solar", "dam reservoir"}}
    assert varying == {(e, s) for e in ("solar", "dam reservoir") for s in SCENARIOS["unequal"]}
    assert {s for e, s in held if e == "more solar"} == {None}
    assert weights.set_index("scenario")["value"].to_dict() == SCENARIOS["unequal"]


def test_a_static_value_that_differs_between_scenarios_is_refused():
    n = _stochastic(SCENARIOS["equal"])
    n.generators.loc[("w2013", "coal"), "marginal_cost"] = 80.0

    with pytest.raises(UnsupportedRecordError, match="Generator coal: marginal_cost"):
        OGSchema.to_datarecord(n, Workspace().con)


@pytest.mark.parametrize(
    ("name", "types", "carriers"),
    [
        (
            "extendable",
            TOPOLOGY | TECHNOLOGIES,
            {"SupplyTechnology - WT", "SupplyTechnology - GT - NATURAL_GAS"},
        ),
        (
            "fixed",
            TOPOLOGY | DEVICES,
            {"RenewableDispatch - WT", "ThermalStandard - GT - NATURAL_GAS"},
        ),
    ],
)
def test_extendable_assets_are_technologies_and_fixed_ones_devices(name, types, carriers, records):
    built = to_network(records[name])

    assert set(revision(records[name])[1].record.schema.meta["types"]) == types
    assert set(built.generators.carrier) == carriers
    assert built.carriers.co2_emissions[built.carriers.index.str.contains("GT")].tolist() == [0.24]


STORED = {"SupplyTechnology": 2, "StorageTechnology": 2}


@pytest.mark.parametrize(
    ("name", "unfilled"),
    [
        ("extendable", UNFILLED),
        ("fixed", {}),
        ("model-energy", STORED),
        ("zambia-like", {"SupplyTechnology": 2}),
    ],
)
def test_a_record_lacks_the_financial_data_that_ogschema_requires_of_a_technology(
    name, unfilled, records
):
    lacking = violations(revision(records[name])[1].record).df()

    counts = lacking.groupby(["component_type", "name"]).size().to_dict()
    expected = {
        (component_type, f"financial_data__{field}"): labels
        for component_type, labels in unfilled.items()
        for field in FINANCIAL_DATA
    }
    assert counts == expected


@pytest.mark.parametrize(
    ("name", "kept"),
    [
        (
            "extendable",
            {
                "ext__pypsa__capital_cost": 17,
                "ext__pypsa__p_max_pu": 4,
                "ext__pypsa__p_min_pu": 4,
                "ext__pypsa__p_nom": 10,
                "ext__pypsa__r": 3,
                "ext__pypsa__s_nom": 7,
            },
        ),
        ("fixed", {"ext__pypsa__capital_cost": 17, "ext__pypsa__p_nom_min": 3}),
    ],
)
def test_values_without_an_ogschema_field_are_kept_as_extensions(name, kept, records):
    buses = revision(records[name])[1].record.properties["bus"].df()

    countries = buses.set_index("bus")["ext__pypsa__country"].to_dict()
    assert _attribute_rows(records[name], "ext__pypsa__") == kept
    assert countries == ac_dc_meshed().buses.country.to_dict()


WEIGHTED = dict.fromkeys(
    [
        f"snapshot__ext__pypsa__weighting_{column}"
        for column in ("generators", "objective", "stores")
    ],
    2920,
)


@pytest.mark.parametrize(
    ("name", "kept", "texts"),
    [
        (
            "model-energy",
            {
                "ext__pypsa__capital_cost": 4,
                "ext__pypsa__charge__capital_cost": 1,
                "ext__pypsa__cyclic_state_of_charge": 1,
                "ext__pypsa__discharge__capital_cost": 1,
                "ext__pypsa__e_cyclic": 1,
                "ext__pypsa__shedding__p_nom": 1,
                **WEIGHTED,
            },
            {
                "ext__pypsa__bus__name": 1,
                "ext__pypsa__charge__name": 1,
                "ext__pypsa__discharge__name": 1,
                "ext__pypsa__shedding__name": 1,
            },
        ),
        (
            "zambia-like",
            {
                "ext__pypsa__capital_cost": 2,
                "ext__pypsa__cyclic_state_of_charge": 1,
                "ext__pypsa__efficiency": 1,
                "ext__pypsa__length": 1,
                "ext__pypsa__num_parallel": 1,
                "ext__pypsa__s_max_pu": 1,
                "ext__pypsa__shedding__p_nom": 3,
                "ext__pypsa__shedding__sign": 3,
            },
            {"ext__pypsa__shedding__name": 3, "ext__pypsa__standard_type": 1},
        ),
    ],
)
def test_parts_and_values_without_an_ogschema_field_are_kept_as_extensions(
    name, kept, texts, records
):
    entities = _entities(records[name])

    assert _attribute_rows(records[name], "ext__pypsa__") == kept
    assert entities.filter(like="ext__").notna().sum().to_dict() == texts


def test_a_store_with_its_bus_and_links_is_one_storage_technology(records):
    record = records["model-energy"]
    hydrogen = _entities(record).loc["hydrogen storage"].dropna()
    turbine = model_energy().links.efficiency["turbine"]

    built = to_network(record)

    assert hydrogen[["component_type", "storage_tech"]].tolist() == ["StorageTechnology", "HGS"]
    assert hydrogen.filter(like="__name").to_dict() == {
        "ext__pypsa__bus__name": "hydrogen",
        "ext__pypsa__charge__name": "electrolysis",
        "ext__pypsa__discharge__name": "turbine",
    }
    assert revision(record)[1].record.dims["bus"].fetchall() == [("electricity",)]
    assert _values(record, "efficiency__out")["hydrogen storage"] == pytest.approx(turbine)
    assert "hydrogen storage" not in _values(record, "duration_limits__max")
    assert built.links[["bus0", "bus1", "carrier"]].to_dict("index") == {
        "electrolysis": {
            "bus0": "electricity",
            "bus1": "hydrogen",
            "carrier": "StorageTechnology - ES - HGS - charge",
        },
        "turbine": {
            "bus0": "hydrogen",
            "bus1": "electricity",
            "carrier": "StorageTechnology - ES - HGS - discharge",
        },
    }
    assert built.buses.carrier["hydrogen"] == built.stores.carrier["hydrogen storage"]


def test_a_discharging_link_is_sized_at_the_grid(store_ogschema_network, tmp_path):
    n = model_energy()
    n.set_snapshots(n.snapshots[:8])
    n.links.loc["turbine", ["p_nom_max", "overnight_cost", "discount_rate"]] = [500.0, 1e6, 0.07]
    efficiency = n.links.efficiency["turbine"]

    record = store_ogschema_network(n, str(tmp_path / "sized"))

    limit = _values(record, "capacity_limits_discharge__max")["hydrogen storage"]
    cost = "capital_costs__discharge_capital_cost__function_data__proportional_term"
    assert limit == pytest.approx(500.0 * efficiency)
    assert _values(record, cost)["hydrogen storage"] == pytest.approx(1e6 / efficiency)
    _assert_same_inputs(to_network(record), n)


def test_a_storage_technology_without_pypsa_names_is_built_with_names_from_its_label(records):
    _, rev = revision(records["model-energy"])
    edits = WorkingRecord(rev.record)
    for part in ("bus", "charge", "discharge"):
        edits.set(f"entity.ext__pypsa__{part}__name", None, entity="hydrogen storage")
    edits.set("entity.ext__pypsa__shedding__name", None, entity="demand")

    built = OGSchema.build(rev.store.commit(edits).record)

    assert built.stores.bus.to_dict() == {"hydrogen storage": "hydrogen storage bus"}
    assert built.links[["bus0", "bus1"]].to_dict("index") == {
        "hydrogen storage charger": {"bus0": "electricity", "bus1": "hydrogen storage bus"},
        "hydrogen storage discharger": {"bus0": "hydrogen storage bus", "bus1": "electricity"},
    }
    assert built.generators.bus["demand shedding"] == "electricity"


@pytest.mark.parametrize(
    ("name", "load", "generator", "value_of_lost_load"),
    [
        ("model-energy", "demand", "load shedding", 2000.0),
        ("zambia-like", "load-ZW", "ZW load shedding", 1e5),
    ],
)
def test_load_shedding_is_the_cost_of_interrupting_the_load_on_its_bus(
    name, load, generator, value_of_lost_load, records
):
    entities = _entities(records[name])
    cost = "operation_cost__variable_operation_cost__value_curve__function_data__proportional_term"

    assert entities.component_type[load] == "InterruptiblePowerLoad"
    assert entities.ext__pypsa__shedding__name[load] == generator
    assert generator not in entities.index
    assert _values(records[name], cost)[load] == pytest.approx(value_of_lost_load)


def test_reservoir_hydro_is_a_turbine_and_the_reservoir_above_it(records):
    record = records["zambia-like"]
    rec = revision(record)[1].record
    entities = _entities(record)

    types = entities.component_type[["dam", "dam reservoir"]].tolist()
    inflow = rec.attributes["ts__inflow"].df()
    assert types == ["HydroTurbine", "HydroReservoir"]
    assert rec.dims["downstream_turbines"].fetchall() == [
        ({"reservoir": "dam reservoir", "turbine": "dam"},)
    ]
    assert _values(record, "storage_level_limits__max") == {"dam reservoir": pytest.approx(4030.0)}
    assert inflow.entity.unique().tolist() == ["dam reservoir"]
    assert len(inflow) == 24


def test_a_line_of_a_standard_type_is_written_with_its_impedances(records):
    record = records["zambia-like"]
    line = _resolved(_zambia_like()).lines.loc["1"]

    built = to_network(record).lines.loc["1"]

    assert _entities(record).ext__pypsa__standard_type["1"] == "bison"
    assert _values(record, "x")["1"] == pytest.approx(0.34 * 320.0 / 0.5)
    assert built[["r", "x", "b", "type"]].to_dict() == pytest.approx(
        line[["r", "x", "b", "type"]].to_dict()
    )


def test_fixed_generators_are_the_existing_devices_of_a_technology(records):
    record = records["zambia-like"]
    rec = revision(record)[1].record
    described = rec.properties["supplemental_attribute"].df().set_index("supplemental_attribute")
    invented = "invented ThermalStandard - ST - COAL"

    devices = described.existing_devices.dropna().to_dict()
    built = described.build_year.dropna().map(json.loads).to_dict()
    retired = described.planned_retirement_year.dropna().map(json.loads).to_dict()
    technologies = _entities(record).loc[[invented, "more solar"]]
    limits = [
        _values(record, f"capacity_limits__{bound}").get(invented) for bound in ("min", "max")
    ]
    attached = {
        tuple(row["entity_supplemental_attribute"].values())
        for row in rec.dims["entity_supplemental_attribute"].df().to_dict("records")
    }
    assert devices == {
        f"{invented} ExistingDevices": "coal|coal 2",
        "more solar ExistingDevices": "solar",
    }
    assert built == {
        f"{invented} RetirementPotential": {"coal": 1995, "coal 2": 2014},
        "more solar RetirementPotential": {"solar": 2015},
    }
    assert retired == {
        f"{invented} RetirementPotential": {"coal": 2035},
        "more solar RetirementPotential": {"solar": 2040},
    }
    assert described.eligible_generators.dropna().tolist() == ["", ""]
    assert technologies.power_systems_type.tolist() == ["ThermalStandard", "RenewableDispatch"]
    assert technologies.fuel.fillna("").tolist() == ["COAL", ""]
    assert limits == [0.0, 0.0]
    assert _values(record, "ext__invented_candidate") == {invented: True}
    assert {
        (invented, f"{invented} RetirementPotential"),
        ("more solar", "more solar ExistingDevices"),
    } <= attached
    assert "ext__pypsa__lifetime" not in rec.flags()
    assert set(to_network(record).generators.index) == set(_zambia_like().generators.index)


def test_the_lifetime_of_a_technology_is_stored_in_whole_years(store_ogschema_network, tmp_path):
    n = ac_dc_meshed()
    n.generators.loc["Manchester Gas", "lifetime"] = 25.4

    record = store_ogschema_network(n, str(tmp_path / "rounded"))

    assert _values(record, "lifetime") == {"Manchester Gas": 25}
    assert to_network(record).generators.lifetime["Manchester Gas"] == 25.0


def test_a_component_without_an_ogschema_type_is_kept_beside_the_record(records):
    record = records["zambia-like"]
    kept = revision(record)[1].record.schema.meta["pypsa"]["components"]

    built = to_network(record).global_constraints

    assert [row["name"] for row in kept["GlobalConstraint"]] == ["lv_limit"]
    assert "lv_limit" not in _entities(record).index
    assert built.loc["lv_limit", ["type", "constant"]].tolist() == [
        "transmission_volume_expansion_limit",
        5e6,
    ]


def _tuples(record: DataRecord, multi: str) -> set[tuple[str, ...]]:
    """Return the tuples of the multi-dim `multi` of `record`."""
    rows = revision(record)[1].record.dims[multi].df()[multi]
    return {tuple(row.values()) for row in rows}


def test_a_snapshot_of_a_network_with_investment_periods_is_a_timestep_in_a_period(records):
    record = records["belgium-like"]
    rec = revision(record)[1].record

    weightings = {
        column: rec.attributes[f"period__ext__pypsa__weighting_{column}"].df()
        for column in ("objective", "years")
    }
    assert rec.schema.over("snapshot") == {"period": "period", "timestep": "timestep"}
    assert rec.dims["period"].fetchall() == [(2030,), (2040,)]
    assert len(rec.dims["timestep"].fetchall()) == 6
    assert len(rec.dims["snapshot"].fetchall()) == 12
    assert weightings["objective"].set_index("period")["value"].to_dict() == {2030: 9.2, 2040: 7.5}
    assert weightings["years"]["value"].tolist() == [10.0, 10.0]
    assert to_network(record).investment_periods.tolist() == [2030, 2040]


def _by_year(record: DataRecord, name: str) -> dict[tuple[str, int], float]:
    """Return the values of the attribute `name` of `record`, by entity and build year."""
    rows = revision(record)[1].record.attributes[name].df()
    return {tuple(row["cohort"].values()): row["value"] for row in rows.to_dict("records")}


def test_the_cohorts_of_a_technology_are_one_entity_with_values_by_build_year(records):
    record = records["belgium-like"]
    entities = _entities(record)
    slope = (
        "operation_costs__variable_operation_cost__value_curve__function_data__proportional_term"
    )

    built = to_network(record).generators

    assert entities.index[entities.component_type.str.endswith("Technology")].tolist() == [
        "north CCGT",
        "north solar",
        "north H2",
    ]
    assert {("north CCGT", 2030), ("north CCGT", 2040)} <= _tuples(record, "cohort")
    assert _by_year(record, "cohort__ext__pypsa__efficiency") == {
        ("north CCGT", 2030): 0.58,
        ("north CCGT", 2040): 0.6,
    }
    assert _by_year(record, "cohort__ext__pypsa__capital_cost")[("north solar", 2040)] == 3e4
    assert _values(record, slope)["north CCGT"] == pytest.approx(3.6 / 0.58)
    assert json.loads(entities.capacity_limits["north CCGT"]) == {
        "2030.0": {"min": 0.0, "max": 200.0},
        "2040.0": {"min": 0.0, "max": 300.0},
    }
    assert "north CCGT" not in _values(record, "capacity_limits__max")
    assert "ext__pypsa__build_year" not in revision(record)[1].record.flags()
    assert built.build_year[["north CCGT-2030", "north CCGT-2040"]].tolist() == [2030, 2040]
    assert built.p_nom_max[["north CCGT-2030", "north CCGT-2040"]].tolist() == [200.0, 300.0]


def test_the_stores_built_in_each_period_are_one_storage_technology(records):
    record = records["belgium-like"]
    hydrogen = _entities(record).loc["north H2"].dropna()

    built = to_network(record)

    assert hydrogen.component_type == "StorageTechnology"
    assert hydrogen.filter(like="__name").to_dict() == {
        "ext__pypsa__bus__name": "north H2",
        "ext__pypsa__charge__name": "north H2 Electrolysis",
        "ext__pypsa__discharge__name": "north H2 Fuel Cell",
    }
    assert {("north H2", 2030), ("north H2", 2040)} <= _tuples(record, "cohort")
    assert _by_year(record, "cohort__ext__pypsa__charge__efficiency") == {
        ("north H2", 2030): 0.62,
        ("north H2", 2040): 0.65,
    }
    assert _values(record, "efficiency__in") == {"north H2": 0.62}
    assert _values(record, "ext__pypsa__discharge__lifetime") == {"north H2": 10}
    assert built.buses.index.tolist() == ["north", "north H2"]
    assert built.stores.bus.to_dict() == dict.fromkeys(
        ["north H2-2030", "north H2-2040"], "north H2"
    )
    assert built.links.efficiency["north H2 Electrolysis-2040"] == 0.65


def test_a_cohort_named_for_no_period_stays_a_technology_of_its_own(
    store_ogschema_network, tmp_path
):
    n = _belgium_like()
    n.generators.rename(index={"north CCGT-2040": "north CCGT late"}, inplace=True)

    record = store_ogschema_network(n, str(tmp_path / "late"))

    assert _values(record, "ext__pypsa__build_year") == {"north CCGT late": 2040}
    assert {year for label, year in _tuples(record, "cohort") if label == "north CCGT"} == {2030}
    _assert_same_inputs(to_network(record), n)


def test_a_technology_of_a_record_not_made_from_pypsa_is_built_in_every_period(tmp_path):
    n = _belgium_like()
    n.generators.rename(index={"north CCGT-2040": "north CCGT late"}, inplace=True)
    ws = Workspace()
    layer = OGSchema.to_datarecord(n, ws.con)
    meta = {key: value for key, value in layer.schema.meta.items() if key != "pypsa"}
    layer.schema = layer.schema.model_copy(update={"meta": meta})

    built = OGSchema.build(ws.store(str(tmp_path / "plain")).commit(layer, parent=None).record)

    late = built.generators.build_year.filter(like="north CCGT late")
    assert late.to_dict() == {"north CCGT late-2030": 2030, "north CCGT late-2040": 2040}
    assert built.generators.build_year.filter(like="north solar").tolist() == [2030, 2040]


def test_a_limit_in_an_investment_period_is_a_requirement_of_that_year(records):
    record = records["belgium-like"]
    limits = ["land_use solar north 2030", "land_use solar north 2040"]
    solar = {(limits[0], "north solar"), (limits[1], "north solar")}

    built = to_network(record).global_constraints.loc[limits]

    assert _entities(record).component_type[limits].tolist() == ["MaximumCapacityRequirements"] * 2
    assert _values(record, "target_year") == {
        "CO2Limit-2030": 2030,
        "CO2Limit-2040": 2040,
        limits[0]: 2030,
        limits[1]: 2040,
    }
    assert _values(record, "max_capacity_mw") == dict.fromkeys(limits, 60.0)
    assert _values(record, "max_mtons") == pytest.approx(
        {"CO2Limit-2030": 2e-4, "CO2Limit-2040": 1.3e-4}
    )
    assert {
        pair for pair in _tuples(record, "requirement_association") if "land" in pair[0]
    } == solar
    assert built.carrier_attribute.tolist() == ["SupplyTechnology - PVe"] * 2
    assert built.bus.tolist() == ["north"] * 2


def test_a_series_is_the_form_of_a_field_that_varies_or_an_extension(records):
    record = records["belgium-like"]
    rec = revision(record)[1].record
    slope = "operation_cost__variable_operation_cost__value_curve__function_data__proportional_term"

    heat_rates = rec.attributes[f"ts__{slope}"].df()
    costs = rec.attributes["ts__ext__pypsa__marginal_cost"].df()
    assert heat_rates.entity.unique().tolist() == ["north CCGT old"]
    assert sorted(heat_rates.value.unique()) == pytest.approx([3.6 / 0.59, 3.6 / 0.58])
    assert _values(record, slope)["north CCGT old"] == 3.6
    assert costs.entity.unique().tolist() == ["north CCGT old"]
    assert sorted(costs.value.unique()) == [49.0, 55.0]
    assert len(costs) == 12


def test_a_shape_is_the_geographic_information_of_what_it_outlines(records):
    record = records["belgium-like"]
    rec = revision(record)[1].record
    described = rec.properties["supplemental_attribute"].df().set_index("supplemental_attribute")
    shapes = described.loc[["Bus north onshore", "country BE onshore"]]

    outlined = json.loads(shapes.geo_json["Bus north onshore"])
    assert shapes.component_type.tolist() == ["GeographicInfo"] * 2
    assert outlined["type"] == "Polygon"
    assert shapes.ext__pypsa__type.tolist() == ["onshore"] * 2
    assert shapes.ext__pypsa__component.fillna("").tolist() == ["", "country"]
    assert shapes.ext__pypsa__idx.fillna("").tolist() == ["", "BE"]
    assert _tuples(record, "bus_supplemental_attribute") == {
        ("north", "north GeographicInfo"),
        ("north", "Bus north onshore"),
    }


def test_a_generator_of_fixed_capacity_is_a_device_of_the_technology_of_its_kind(records):
    rec = revision(records["belgium-like"])[1].record
    described = rec.properties["supplemental_attribute"].df().set_index("supplemental_attribute")

    assert described.existing_devices.dropna().to_dict() == {
        "north CCGT ExistingDevices": "north CCGT old"
    }


def test_a_technology_group_keeps_two_carriers_of_one_prime_mover_apart(records):
    entities = revision(records["grouped"])[1].record.properties["entity"].df()

    groups = entities.set_index("entity")["ext__technology_group"].dropna().to_dict()
    built = to_network(records["grouped"])
    assert groups == {"Frankfurt Wind": "float"}
    assert built.generators.og_technology_group.dropna().to_dict() == groups
    wind = ["Manchester Wind", "Norway Wind", "Frankfurt Wind"]
    assert built.generators.carrier.loc[wind].tolist() == [
        "SupplyTechnology - WT",
        "SupplyTechnology - WS",
        "SupplyTechnology - WS - float",
    ]
    assert (
        "ext__technology_group"
        not in revision(records["extendable"])[1].record.schema.properties["entity"]
    )


def test_overnight_expansion_writes_its_results_over_an_ogschema_record(records, ancestry):
    n = ac_dc_meshed()
    record = records["extendable"]
    block = OvernightCapacityExpansion

    result = block(block.merge_config({}, {})).run(record)

    solved = to_network(result)
    _assert_same_inputs(solved, n)
    n.optimize(log_to_console=False)
    files = revision(result)[1].manifest.files
    assert ancestry(result) == [record.uuid, result.uuid]
    assert files.dims == ()
    assert files.attributes
    assert all("ext__pypsa_result__" in name for name in files.attributes)
    assert solved.objective == pytest.approx(n.objective, rel=1e-6)
    assert solved.generators.p_nom_opt.to_dict() == pytest.approx(
        n.generators.p_nom_opt.to_dict(), rel=1e-4, abs=1e-2
    )
    assert solved.generators_t.p.shape == n.generators_t.p.shape


def test_a_block_writes_the_results_of_the_parts_of_a_component(records, ancestry):
    n = _zambia_like()
    record = records["zambia-like"]
    block = OvernightCapacityExpansion

    result = block(block.merge_config({}, {})).run(record)

    solved = to_network(result)
    n.optimize(log_to_console=False)
    files = revision(result)[1].manifest.files
    shed = solved.generators_t.p.filter(like="load shedding")
    assert ancestry(result) == [record.uuid, result.uuid]
    assert {"ext__pypsa_result__shedding__p", "ext__pypsa_result__state_of_charge"} <= set(
        files.attributes
    )
    assert solved.objective == pytest.approx(n.objective, rel=1e-6)
    assert shed.columns.tolist() == n.generators_t.p.filter(like="load shedding").columns.tolist()


def test_a_dispatch_written_whole_keeps_the_time_aggregations_of_its_record(records):
    partition = TimePartition(TimePartition.merge_config({"name": "agg_3h", "n_hours": 3}, {}))
    dispatch = RollingHorizonDispatch(RollingHorizonDispatch.merge_config({}, {}))

    result = dispatch.run(partition.run(records["fixed"]))

    snapshots = revision(result)[1].record.properties["snapshot"].df()
    assert snapshots["agg_3h"].nunique() == 4
    assert to_network(result).generators_t.p.shape == (10, 6)
    _assert_same_inputs(to_network(result), NETWORKS["fixed"]())


def test_a_value_per_unit_of_the_device_base_is_scaled_by_it(records):
    _, rev = revision(records["fixed"])
    edits = WorkingRecord(rev.record)
    edits.set("entity.power_units", "COMPONENT_BASE", entity="London")
    edits.set("max_active_power", 1.0, entity="London")

    built = OGSchema.build(rev.store.commit(edits).record)

    expected = ac_dc_meshed().loads_t.p_set["London"]
    pd.testing.assert_series_equal(built.loads_t.p_set["London"], expected, rtol=1e-9)


@pytest.mark.parametrize(
    ("name", "value", "entity", "match"),
    [
        ("parameter_units", "COMPONENT_BASE", "0", "impedances per unit.*'0'"),
        (
            "operation_cost__variable_operation_cost__value_curve__function_data__function_type",
            "QUADRATIC",
            "Manchester Gas",
            "function_type other than LINEAR.*Manchester Gas",
        ),
        (
            "operation_cost__variable_operation_cost__variable_cost_type",
            "COST",
            "Norway Gas",
            "no fuel curve.*Norway Gas",
        ),
    ],
)
def test_a_record_the_mapping_cannot_read_is_refused(name, value, entity, match, records):
    _, rev = revision(records["fixed"])
    edits = WorkingRecord(rev.record)
    edits.set(f"entity.{name}", value, entity=entity)

    with pytest.raises(UnsupportedRecordError, match=match):
        OGSchema.build(rev.store.commit(edits).record)


def test_results_alone_are_written_over_a_record():
    with pytest.raises(ValueError, match="needs `base`"):
        OGSchema.to_datarecord(ac_dc_meshed(), Workspace().con, results_only=True)


def _with_storage(n: pypsa.Network) -> None:
    n.add("StorageUnit", "battery", bus="London", p_nom=10.0)


def _with_a_hydrogen_bus(n: pypsa.Network) -> None:
    n.add("Bus", "hydrogen", carrier="H2")


def _with_a_third_port(n: pypsa.Network) -> None:
    n.links["bus2"] = "London"


def _with_a_transformer(n: pypsa.Network) -> None:
    n.add("Transformer", "step", bus0="London", bus1="Norwich", x=0.1, s_nom=10.0)


def _with_one_name_twice(n: pypsa.Network) -> None:
    n.add("Load", "Manchester Gas", bus="Manchester", og_type="PowerLoad")


def _with_two_rates_for_one_type(n: pypsa.Network) -> None:
    n.add("Carrier", "biogas", co2_emissions=0.0)
    n.generators.loc["Norway Gas", "carrier"] = "biogas"


@pytest.mark.parametrize(
    ("change", "match"),
    [
        (_with_storage, "StorageUnit"),
        (_with_a_hydrogen_bus, "Bus.*hydrogen"),
        (_with_a_third_port, "more than two ports"),
        (_with_a_transformer, "Transformer"),
        (_with_one_name_twice, "Manchester Gas"),
        (_with_two_rates_for_one_type, "several CO2 rates"),
    ],
)
def test_a_network_the_mapping_does_not_cover_is_refused(change, match):
    n = ac_dc_meshed()
    change(n)

    with pytest.raises(UnsupportedRecordError, match=match):
        OGSchema.to_datarecord(n, Workspace().con)


def _with_pumping(n: pypsa.Network) -> None:
    n.storage_units.loc["dam", "efficiency_store"] = 0.8


def _with_something_else_on_the_bus_of_a_chain(n: pypsa.Network) -> None:
    n.add("Load", "fuel cells", bus="hydrogen", p_set=1.0, og_type="PowerLoad")


def _with_a_battery_of_fixed_capacity(n: pypsa.Network) -> None:
    n.storage_units.loc["battery storage", "p_nom_extendable"] = False


def _with_a_limit_on_no_asset(n: pypsa.Network) -> None:
    n.global_constraints.loc["land_use solar north 2030", "carrier_attribute"] = "onwind"


def _with_a_limit_on_a_store(n: pypsa.Network) -> None:
    n.global_constraints.loc["land_use solar north 2030", "carrier_attribute"] = "H2"
    n.global_constraints.loc["land_use solar north 2030", "bus"] = "north H2"


def _with_a_shape_that_is_a_point(n: pypsa.Network) -> None:
    n.shapes.loc["Bus north onshore", "geometry"] = shapely.Point(4.4, 50.8)


def _with_a_series_of_one_cohort(n: pypsa.Network) -> None:
    n.generators_t.p_max_pu["north solar-2040"] *= 0.5


def _with_cohorts_that_differ_in_text(n: pypsa.Network) -> None:
    n.generators["phase"] = "planned"
    n.generators.loc["north CCGT-2040", "phase"] = "proposed"


@pytest.mark.parametrize(
    ("new", "change", "match"),
    [
        (_zambia_like, _with_pumping, "StorageUnit.*dam"),
        (model_energy, _with_something_else_on_the_bus_of_a_chain, "bus of a storage chain"),
        (model_energy, _with_a_battery_of_fixed_capacity, "StorageUnit.*battery storage"),
        (_belgium_like, _with_a_limit_on_no_asset, "capacity limit on no extendable asset"),
        (_belgium_like, _with_a_limit_on_a_store, "capacity limit on a store or a part"),
        (_belgium_like, _with_a_shape_that_is_a_point, "a shape that is a point"),
        (_belgium_like, _with_a_series_of_one_cohort, "not that of the cohort built first"),
        (_belgium_like, _with_cohorts_that_differ_in_text, "differ in \\['phase'\\]"),
    ],
)
def test_a_component_the_mapping_does_not_cover_is_refused(new, change, match):
    n = new()
    change(n)

    with pytest.raises(UnsupportedRecordError, match=match):
        OGSchema.to_datarecord(n, Workspace().con)


def _without_the_way_back(n: pypsa.Network) -> None:
    n.remove("Link", "turbine")


def _without_the_load(n: pypsa.Network) -> None:
    n.remove("Load", "demand")


@pytest.mark.parametrize(
    ("change", "match"),
    [
        (_without_the_way_back, "Buses \\['hydrogen'\\].*no storage chain"),
        (_without_the_load, "Load-shedding generators \\['load shedding'\\]"),
    ],
)
def test_classifying_needs_every_part_of_a_component_made_of_several(change, match):
    n = pypsa.examples.model_energy()
    change(n)

    with pytest.raises(ValueError, match=match):
        classify(n, MODEL_ENERGY_CARRIERS, MODEL_ENERGY_BUSES)


def test_classifying_needs_both_links_of_every_store_on_a_bus():
    n = _belgium_like()
    n.remove("Link", "north H2 Fuel Cell-2040")

    with pytest.raises(ValueError, match="Buses \\['north H2'\\].*no storage chain"):
        classify(n, BEL_CARRIERS)


def _sample(name: str) -> pypsa.Network:
    """Build the base network of the sample store `name`, if the stores are on this machine.

    `MANTA_SAMPLE_DATARECORDS` names the folder that has the sample stores.
    """
    samples = os.environ.get("MANTA_SAMPLE_DATARECORDS")
    if samples is None:
        pytest.skip("MANTA_SAMPLE_DATARECORDS names no folder of sample stores")
    store = Path(samples) / name
    base = json.loads((store / "store.json").read_text())["references"]["base"]["revision"]
    return to_network(DataRecord(url=str(store), uuid=UUID(base)))


@pytest.mark.slow
def test_the_model_of_zambia_comes_back_from_an_ogschema_record(store_ogschema_network, tmp_path):
    original = _sample("ZMB")
    classify(original, ZMB_CARRIERS)

    built = to_network(store_ogschema_network(original, str(tmp_path / "ZMB")))

    week = original.snapshots[:168]
    _assert_same_inputs(_resolved(built), _resolved(original))
    original.optimize(snapshots=week, log_to_console=False)
    built.optimize(snapshots=week, log_to_console=False)
    assert built.objective == pytest.approx(original.objective, rel=1e-6)


UNVALUED = {("Bus", "onshore_bus")}
"""The columns of the model of Belgium that hold no value, which a record does not keep."""

STANDARD_LINES = {("Line", "type"), ("Line", "x"), ("Line", "r"), ("Line", "b")}
"""What a line of a standard type comes back with in place of its type: its impedances.

They are those PyPSA computes from the type when it solves, which the network as built
does not hold yet.
"""


@pytest.mark.slow
def test_the_model_of_belgium_comes_back_from_an_ogschema_record(store_ogschema_network, tmp_path):
    """Compare the PyPSA-Eur model of Belgium with what its OGSchema record builds, unsolved."""
    original = _sample("BEL-full-res")
    classify(original, BEL_CARRIERS)

    built = to_network(store_ogschema_network(original, str(tmp_path / "BEL")))

    _assert_same_inputs(built, original, UNVALUED | STANDARD_LINES)
    _assert_same_inputs(_resolved(built), _resolved(original), UNVALUED)


def test_a_network_is_classified_before_it_is_written():
    with pytest.raises(UnsupportedRecordError, match="classify"):
        OGSchema.to_datarecord(pypsa.examples.ac_dc_meshed(), Workspace().con)


@pytest.mark.parametrize(
    ("carriers", "match"),
    [
        ({}, "Generator .*Manchester Wind"),
        ({"gas": AC_DC_MESHED_CARRIERS["gas"]}, "Generator .*Manchester Wind"),
    ],
)
def test_classifying_needs_a_type_for_every_generator_carrier(carriers, match):
    with pytest.raises(ValueError, match=match):
        classify(pypsa.examples.ac_dc_meshed(), carriers)


def test_classifying_needs_a_group_to_tell_two_carriers_of_one_type_apart():
    ungrouped = dict.fromkeys(OFFSHORE, Technology("RenewableDispatch", prime_mover_type="WS"))

    with pytest.raises(ValueError, match=r"\['offwind-ac', 'offwind-float'\].*distinct `group`"):
        _grouped(ungrouped)
