# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Tests of bus and entity aggregation, by properties a rev already has.

Buses merge by a bus property, and assets by an entity property, at the same buses.
Candidates merge within one cohort, and existing assets by the first and last investment
periods they are active in. A network merged
so is solved, and its results expanded back to every bus and asset of the rev.
"""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, closing, nullcontext

import pytest

pypsa = pytest.importorskip("pypsa", reason="the PyPSA blocks need PyPSA installed")

import numpy as np
import pandas as pd
from datarecord import Revision, Workspace
from pypsa.clustering.spatial import aggregateoneport
from pypsa.geo import haversine_pts

from playbook_library.overnight_capacity_expansion import OvernightCapacityExpansion
from playbook_library.pypsa_configs import Aggregation, PyPSAOptimizeSchema
from playbook_library.pypsa_helpers import (
    fix_capacities,
    optimize_network,
    to_network,
    write_aggregated_results,
)
from playbook_library.pypsa_spatial_aggregation import (
    aggregate_network,
    expand_network,
    spatial_maps,
)
from playbook_library.pypsa_time_aggregation import series_frame, snapshot_frame
from playbook_library.tests.networks import (
    ASSETS,
    BATTERIES,
    GAS,
    HYDRO,
    LOADS,
    SOLAR,
    new_zoned_network,
    set_status,
)
from playbook_library.time_partition import TimePartition

pytestmark = pytest.mark.pypsa

SPATIAL = Aggregation(bus="zone", entity="carrier")
ZONES = Aggregation(bus="zone")
CARRIERS = Aggregation(entity="carrier")
UNTYPED = {"check_names": False, "check_index_type": False, "check_column_type": False}
"""Compare frames by their labels and values, whatever type of index holds the labels."""


@pytest.fixture(scope="module")
def module_store(
    tmp_path_factory, store_network
) -> Iterator[Callable[[pypsa.Network, str], Revision]]:
    """Return a function that stores a network as `name`, in a workspace of this module's own."""
    with closing(Workspace()) as ws:
        yield lambda n, name: store_network(n, ws.store(str(tmp_path_factory.mktemp(name))))


@pytest.fixture
def zoned_record(store_revision) -> Revision:
    return store_revision(new_zoned_network(), "zoned")


@pytest.fixture
def bel_status_record(bel, store_revision) -> Revision:
    """Store BEL with each extendable asset a candidate and each other existing."""
    return store_revision(set_status(to_network(bel)), "bel")


def _run(block_cls, config: dict, rev: Revision) -> Revision:
    return block_cls(block_cls.merge_config(config, {})).run(rev)


@pytest.mark.parametrize("ctype", ["Generator", "Load", "StorageUnit", "Store"])
def test_merging_by_carrier_matches_pypsa_one_port_aggregation(ctype, zoned_record):
    """PyPSA weighs averages by `p_nom`, here in proportion to the largest capacity."""
    n = to_network(zoned_record)
    expected, series = aggregateoneport(n, spatial_maps(n, zoned_record, SPATIAL).buses, ctype)
    merged = aggregate_network(n, zoned_record, SPATIAL)

    static = merged.components[ctype].static
    labels = static["bus"] + " " + static["carrier"]
    defaults = merged.components[ctype].defaults.index
    columns = expected.columns.intersection(defaults)
    actual = static.set_axis(labels).loc[expected.index, columns]
    pd.testing.assert_frame_equal(actual, expected[columns], check_dtype=False, **UNTYPED)
    for attr, frame in series.items():
        dense = merged.get_switchable_as_dense(ctype, attr).set_axis(labels, axis=1)
        pd.testing.assert_frame_equal(dense[frame.columns], frame, **UNTYPED)


def test_merging_buses_leaves_out_the_flows_of_an_earlier_solve(zoned_record):
    solved = _run(OvernightCapacityExpansion, {}, zoned_record)
    merged = aggregate_network(to_network(solved), solved, ZONES)
    assert all(frame.empty for frame in merged.c.lines.dynamic.values())


def test_merged_averages_weigh_by_largest_capacity_not_by_capacity(store_revision):
    """`p_nom` runs against `p_nom_max`, where PyPSA would weigh averages the other way."""
    n = new_zoned_network()
    n.generators.loc[SOLAR, "p_nom"] = [30.0, 10.0]
    rev = store_revision(n, "weighted")
    merged = aggregate_network(to_network(rev), rev, SPATIAL)
    shares = np.r_[0.25, 0.75]

    assert merged.generators.loc["solar_a", "capital_cost"] == pytest.approx(11.5)
    np.testing.assert_allclose(
        merged.generators_t.p_max_pu["solar_a"], n.generators_t.p_max_pu[SOLAR] @ shares
    )


def new_parallel_network() -> pypsa.Network:
    """Add to the zoned network a line parallel to `ab`, a link without a carrier beside
    `dc` and a link with its carrier."""
    n = new_zoned_network()
    n.add("Line", "ab2", bus0="a", bus1="b", s_nom=300.0, x=0.1, r=0.01, carrier="AC")
    n.add("Link", ["dc_bare", "dc2"], bus0="a", bus1="d", carrier=["", "DC"], p_nom=20.0)
    return set_status(n)


def test_merging_by_entity_merges_parallel_lines_and_leaves_bare_links(store_revision):
    """Untyped, `ab` and `ab2` combine their impedances in parallel, and their cost by
    `s_nom`, both scaled from their 100 km to the distance between `a` and `b`."""
    n = new_parallel_network()
    n.lines.loc[["ab", "ab2"], ["length", "capital_cost"]] = [[100.0, 10.0], [100.0, 20.0]]
    rev = store_revision(n, "parallel")
    merged = aggregate_network(to_network(rev), rev, CARRIERS)
    scale = haversine_pts([[0.0, 1.0]], [[1.0, 1.0]])[0] / 100.0
    expected = {"s_nom": 400.0, "x": 0.05 * scale, "r": 0.005 * scale, "capital_cost": 17.5 * scale}

    assert set(merged.links.index) == {"dc", "loop", "dc_bare"}
    assert merged.links.loc["dc", "p_nom"] == 40.0
    assert set(merged.lines.index) == {"ab", "ac", "db", "cd"}
    assert merged.lines.loc["ab", list(expected)].to_dict() == pytest.approx(expected)


@pytest.mark.parametrize("length", [100.0, 0.0])
def test_parallel_lines_between_buses_without_coordinates_keep_their_impedances(
    length, store_revision
):
    n = new_parallel_network()
    n.buses[["x", "y"]] = 0.0
    n.lines.loc[["ab", "ab2"], "length"] = length
    rev = store_revision(n, "uncoordinated")
    merged = aggregate_network(to_network(rev), rev, CARRIERS)
    expected = {"length": length, "x": 0.05, "r": 0.005}

    assert merged.lines.loc["ab", list(expected)].to_dict() == pytest.approx(expected)


LINE_TYPE = "Al/St 240/40 4-bundle 380.0"
"""A standard line type of PyPSA, of 0.03 ohm/km resistance and 0.246 ohm/km reactance."""


def _typed_network(other_type: str = LINE_TYPE) -> pypsa.Network:
    """Build the parallel network with lines of `LINE_TYPE` and text PyPSA does not know.

    Bus `e`, alone in zone east, joins `c` by line `ce`. Line `db`, which merges with `ac`
    by zone, and `ab2`, which merges with `ab` by carrier, are of `other_type`.
    """
    n = new_parallel_network()
    n.add("Bus", "e", x=2, y=0, carrier="AC")
    n.buses.loc["e", "zone"] = "east"
    n.add("Line", "ce", bus0="c", bus1="e", s_nom=100.0, carrier="AC")
    n.lines["type"] = LINE_TYPE
    n.lines.loc[["db", "ab2"], "type"] = other_type
    n.lines["num_parallel"] = 2.0
    n.lines["tags"] = "line " + n.lines.index
    n.lines["underground"] = True
    n.buses["symbol"] = "bus " + n.buses.index
    return set_status(n)


@pytest.fixture(scope="module")
def typed_record(module_store) -> Revision:
    return module_store(_typed_network(), "typed")


@pytest.mark.parametrize(
    ("aggregation", "ctype", "attr", "label", "expected"),
    [
        pytest.param(ZONES, "Bus", "symbol", "a", None, id="merged-bus"),
        pytest.param(ZONES, "Bus", "symbol", "e", "bus e", id="lone-bus"),
        pytest.param(ZONES, "Line", "tags", "ac", None, id="merged-line-by-zone"),
        pytest.param(ZONES, "Line", "tags", "ce", "line ce", id="lone-line-by-zone"),
        pytest.param(CARRIERS, "Line", "tags", "ab", None, id="merged-line-by-carrier"),
        pytest.param(CARRIERS, "Line", "tags", "ac", "line ac", id="lone-line-by-carrier"),
        pytest.param(ZONES, "Line", "underground", "ac", None, id="merged-flag-by-zone"),
        pytest.param(ZONES, "Line", "underground", "ce", True, id="lone-flag-by-zone"),
        pytest.param(CARRIERS, "Line", "underground", "ab", None, id="merged-flag-by-carrier"),
    ],
)
def test_merged_buses_and_lines_leave_text_pypsa_does_not_know_unset(
    aggregation, ctype, attr, label, expected, typed_record
):
    merged = aggregate_network(to_network(typed_record), typed_record, aggregation)
    value = merged.components[ctype].static.loc[label, attr]

    assert value == expected if expected else pd.isna(value)


@pytest.mark.parametrize(
    ("aggregation", "line", "ends"),
    [
        pytest.param(ZONES, "ac", [[0.5, 1.0], [0.5, 0.0]], id="by-zone"),
        pytest.param(CARRIERS, "ab", [[0.0, 1.0], [1.0, 1.0]], id="by-carrier"),
    ],
)
def test_merged_lines_keep_their_type_and_span_their_buses(aggregation, line, ends, typed_record):
    """Merged by zone, `ac` and `db` run between the centres of north and south."""
    merged = aggregate_network(to_network(typed_record), typed_record, aggregation)
    length = haversine_pts([ends[0]], [ends[1]])[0]
    expected = {
        "num_parallel": 4.0,
        "s_nom": 400.0,
        "length": length,
        "r": 0.03 * length / 4,
        "x": 0.246 * length / 4,
    }

    assert merged.lines.loc[line, "type"] == LINE_TYPE
    assert merged.lines.loc[line, list(expected)].to_dict() == pytest.approx(expected)


@pytest.mark.parametrize(
    ("aggregation", "line"),
    [pytest.param(ZONES, "ac", id="by-zone"), pytest.param(CARRIERS, "ab", id="by-carrier")],
)
def test_merging_lines_of_different_types_raises(aggregation, line, store_revision):
    rev = store_revision(_typed_network("Al/St 240/40 2-bundle 220.0"), "mixed_types")
    with pytest.raises(ValueError, match=rf"Lines of different types merge into \['{line}'\]"):
        aggregate_network(to_network(rev), rev, aggregation)


@pytest.mark.parametrize(
    ("aggregation", "members"),
    [
        pytest.param(ZONES, ["ac", "db"], id="by-zone"),
        pytest.param(CARRIERS, ["ab", "ab2"], id="by-carrier"),
    ],
)
@pytest.mark.parametrize(
    ("s_nom_max", "extendable", "expected"),
    [
        pytest.param([150.0, 400.0], [True, True], 500.0, id="largest-extension"),
        pytest.param([150.0, np.inf], [True, True], np.inf, id="no-limit"),
        pytest.param([150.0, np.inf], [True, False], 450.0, id="one-fixed"),
        pytest.param([np.inf, np.inf], [False, False], 400.0, id="all-fixed"),
    ],
)
def test_merged_lines_extend_by_the_largest_extension_of_their_members(
    aggregation, members, s_nom_max, extendable, expected, store_revision
):
    """Merged lines of 100 and 300 MW extend once, as PyPSA-Eur extends merged lines."""
    n = new_parallel_network()
    n.lines.loc[members, "s_nom"] = [100.0, 300.0]
    n.lines.loc[members, "s_nom_max"] = s_nom_max
    n.lines.loc[members, "s_nom_extendable"] = extendable
    rev = store_revision(set_status(n), "extension")
    merged = aggregate_network(to_network(rev), rev, aggregation)

    assert merged.lines.loc[members[0], "s_nom_max"] == expected


@pytest.mark.parametrize(
    ("aggregation", "members"),
    [
        pytest.param(ZONES, ["ac", "db"], id="by-zone"),
        pytest.param(CARRIERS, ["ab", "ab2"], id="by-carrier"),
    ],
)
def test_merging_lines_above_their_s_nom_max_raises(aggregation, members, store_revision):
    n = new_parallel_network()
    limits = [[100.0, 120.0, 150.0], [300.0, 390.0, 400.0]]
    n.lines.loc[members, ["s_nom", "s_nom_min", "s_nom_max"]] = limits
    n.lines.loc[members, "s_nom_extendable"] = True
    rev = store_revision(set_status(n), "above")

    with pytest.raises(ValueError, match=rf"`s_nom_max` into \['{members[0]}'\]"):
        aggregate_network(to_network(rev), rev, aggregation)


def _transformer_record(store_revision, carrier: str, zone: str = "north") -> Revision:
    n = new_zoned_network()
    n.add("Bus", "e", carrier="AC")
    n.buses.loc["e", "zone"] = zone
    n.add("Transformer", "t", bus0="a", bus1="e", s_nom=100.0, x=0.1, carrier=carrier)
    return store_revision(n, "transformer")


def test_merging_by_entity_refuses_transformers_with_a_value(store_revision):
    rev = _transformer_record(store_revision, "AC")
    with pytest.raises(NotImplementedError, match="Entity aggregation of transformers"):
        aggregate_network(to_network(rev), rev, Aggregation(entity="carrier"))


def test_merging_by_entity_keeps_transformers_without_a_value(store_revision):
    rev = _transformer_record(store_revision, "")
    merged = aggregate_network(to_network(rev), rev, Aggregation(entity="carrier"))

    assert list(merged.transformers.index) == ["t"]


@pytest.mark.parametrize(
    ("zone", "outcome"),
    [
        pytest.param("north", nullcontext(), id="within"),
        pytest.param(
            "east",
            pytest.raises(NotImplementedError, match=r"between merged buses: \['t'\]"),
            id="between",
        ),
    ],
)
def test_merging_by_bus_drops_transformers_within_a_merged_bus(
    zone: str, outcome: AbstractContextManager, store_revision
):
    rev = _transformer_record(store_revision, "AC", zone)
    n = to_network(rev)
    with outcome:
        n_c = optimize_network(aggregate_network(n, rev, SPATIAL), PyPSAOptimizeSchema())
        _, result = write_aggregated_results(n_c, n, rev, SPATIAL, False)
        expanded = to_network(result)

        assert n_c.transformers.empty
        assert expanded.transformers.loc["t", "s_nom_opt"] == 100.0
        assert (expanded.transformers_t.p0["t"] == 0).all()
        assert (expanded.transformers_t.p1["t"] == 0).all()


def test_merging_by_bus_needs_every_bus_value(store_revision):
    n = new_zoned_network()
    n.buses.loc["d", "zone"] = None
    rev = store_revision(n, "unzoned")
    with pytest.raises(ValueError, match=r"bus.zone is not set for \['d'\]"):
        aggregate_network(to_network(rev), rev, SPATIAL)


UNTYPED_MEMBERS = {"Generator": ["solar_b"], "Load": ["load_b"], "Store": ["st_c", "st_d"]}
"""The one-ports left without a carrier, beside the link `dc_bare`: every store among them."""

UNTYPED_RESULTS = {"Generator": ["p", "p_nom_opt"], "Load": ["p"], "Store": ["p", "e", "e_nom_opt"]}


@pytest.mark.parametrize("ungrouped", ["keep", "drop"])
def test_one_ports_without_a_value_are_kept_apart_or_dropped(ungrouped, store_revision):
    """Kept, each stays apart at its merged bus. Dropped, each keeps its capacity and carries
    no flow, `load_b` draws no demand and the stores hold no energy. Links without a value
    are always kept."""
    n = new_parallel_network()
    for ctype, members in UNTYPED_MEMBERS.items():
        n.components[ctype].static.loc[members, "carrier"] = ""
    rev = store_revision(n, "untyped")
    n = to_network(rev)
    aggregation = Aggregation(bus="zone", entity="carrier", ungrouped=ungrouped)
    n_c = optimize_network(aggregate_network(n, rev, aggregation), PyPSAOptimizeSchema())
    _, result = write_aggregated_results(n_c, n, rev, aggregation, False)
    expanded = to_network(result)
    kept = ungrouped == "keep"

    assert "dc_bare" in n_c.links.index
    assert n_c.generators.loc["solar_a", "p_nom"] == 10.0
    for ctype, members in UNTYPED_MEMBERS.items():
        solved, unsolved = n_c.components[ctype], n.components[ctype]
        assert solved.static.index.isin(members).any() == kept
        for attr in UNTYPED_RESULTS[ctype]:
            if attr.endswith("_opt"):
                fixed = unsolved.static.loc[members, attr.removesuffix("_opt")]
                expected = solved.static[attr].reindex(members).fillna(fixed)
                actual = expanded.components[ctype].static.loc[members, attr]
            else:
                expected = solved.dynamic[attr].reindex(columns=members, fill_value=0.0)
                actual = expanded.components[ctype].dynamic[attr][members]
            np.testing.assert_allclose(actual, expected)


def test_dropping_one_ports_without_a_value_needs_an_entity_aggregation():
    with pytest.raises(ValueError, match="`ungrouped: drop` needs `entity`"):
        Aggregation(bus="zone", ungrouped="drop")


def test_dropped_one_ports_carry_no_flow_at_any_snapshot_of_a_time_aggregation(store_revision):
    n = new_parallel_network()
    for ctype, members in UNTYPED_MEMBERS.items():
        n.components[ctype].static.loc[members, "carrier"] = ""
    n.stores.loc["st_c", "e_initial"] = 5.0
    rev = _run(TimePartition, {"name": "agg", "n_hours": 3}, store_revision(n, "untyped_time"))
    aggregation = {"snapshot": "agg", "bus": "zone", "entity": "carrier", "ungrouped": "drop"}
    result = _run(OvernightCapacityExpansion, {"aggregation": aggregation}, rev)
    members = [member for names in UNTYPED_MEMBERS.values() for member in names]

    for name in ["p", "e"]:
        frame = series_frame(result.record, name)
        entity = frame["connection"].str.get("entity") if "connection" in frame else frame["entity"]
        dropped = frame[entity.isin(members)]
        assert not dropped.empty
        assert (dropped["value"] == 0).all()


def test_parallel_line_flows_and_capacity_split_by_capacity(store_revision):
    rev = store_revision(new_parallel_network(), "parallel")
    n = to_network(rev)
    aggregation = Aggregation(entity="carrier")
    n_c = optimize_network(aggregate_network(n, rev, aggregation), PyPSAOptimizeSchema())
    _, result = write_aggregated_results(n_c, n, rev, aggregation, False)
    flows = to_network(result).lines_t.p0[["ab", "ab2"]]

    assert n_c.lines_t.p0["ab"].abs().max() > 1
    np.testing.assert_allclose(flows.sum(axis=1), n_c.lines_t.p0["ab"])
    np.testing.assert_allclose(3 * flows["ab"], flows["ab2"])


def _two_bus_periods_network(new_multi_period_network) -> pypsa.Network:
    """Build the network of three investment periods with each cohort also at a second bus."""
    n = new_multi_period_network()
    n.add("Bus", "bus2")
    n.add("Line", "line", bus0="bus", bus1="bus2", x=0.1, s_nom=100.0)
    cohorts = n.generators[["build_year", "lifetime", "capital_cost", "marginal_cost"]]
    columns = {name: values.to_numpy() for name, values in cohorts.items()}
    n.add("Generator", cohorts.index + "-bus2", bus="bus2", p_nom_extendable=True, **columns)
    n.generators["carrier"] = "gas"
    n.generators["asset_status"] = "candidate"
    n.loads["carrier"] = "electricity"
    return n


@pytest.fixture
def two_bus_periods_record(store_revision, new_multi_period_network) -> Revision:
    return store_revision(_two_bus_periods_network(new_multi_period_network), "two_buses")


COHORTS = [2030, 2040, 2050]


@pytest.mark.parametrize(
    ("aggregation", "expected"),
    [
        pytest.param(
            Aggregation(entity="carrier"),
            {f"gen-{y}{s}": (b, y) for y in COHORTS for s, b in [("", "bus"), ("-bus2", "bus2")]},
            id="entities",
        ),
        pytest.param(
            Aggregation(bus="carrier"),
            {f"gen-{y}{s}": ("bus", y) for y in COHORTS for s in ["", "-bus2"]},
            id="buses",
        ),
        pytest.param(
            Aggregation(bus="carrier", entity="carrier"),
            {f"gen-{y}": ("bus", y) for y in COHORTS},
            id="both",
        ),
    ],
)
def test_merging_keeps_cohorts_and_buses_apart(aggregation, expected, two_bus_periods_record):
    n = to_network(two_bus_periods_record)
    merged = aggregate_network(n, two_bus_periods_record, aggregation)

    generators = merged.generators[["bus", "build_year"]]
    assert dict(zip(generators.index, generators.itertuples(index=False), strict=True)) == expected
    assert (merged.generators["lifetime"] == 30).all()


ONWIND = pd.DataFrame(
    {
        "bus": ["bus", "bus", "bus2", "bus", "bus", "bus"],
        "build_year": [2003, 2010, 2010, 2015, 2010, 1990],
        "lifetime": 30.0,
        "resource_class": [0.0, 0.0, 0.0, 0.0, 1.0, 0.0],
        "p_nom": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
        "marginal_cost": [0.0, 0.0, 1.0, 1.0, 1.0, 0.0],
    },
    index=pd.Index(["on_a", "on_b", "on_c", "on_d", "on_e", "on_f"]),
)
"""Existing onwind units: `on_a` and `on_b` are last active in 2030, `on_c` too but at
`bus2`, `on_d` in 2040, `on_e` in 2030 but of another resource class and `on_f` in none.
`on_a` and `on_b` run first."""


def _vintage_network(new_multi_period_network) -> pypsa.Network:
    """Build the network of two buses and three investment periods with `ONWIND`."""
    n = _two_bus_periods_network(new_multi_period_network)
    n.add("Generator", ONWIND.index, carrier="onwind", **ONWIND)
    n.generators.loc[ONWIND.index, "asset_status"] = "existing"
    return n


@pytest.fixture(scope="module")
def vintage_record(module_store, new_multi_period_network) -> Revision:
    return module_store(_vintage_network(new_multi_period_network), "vintage")


@pytest.mark.parametrize(
    ("aggregation", "expected"),
    [
        pytest.param(
            Aggregation(entity="carrier"),
            {
                "on_a": ("bus", 2010, 23.0, 30.0),
                "on_c": ("bus2", 2010, 30.0, 30.0),
                "on_d": ("bus", 2015, 30.0, 40.0),
                "on_e": ("bus", 2010, 30.0, 50.0),
            },
            id="entities",
        ),
        pytest.param(
            Aggregation(bus="carrier", entity="carrier"),
            {
                "on_a": ("bus", 2010, 23.0, 60.0),
                "on_d": ("bus", 2015, 30.0, 40.0),
                "on_e": ("bus", 2010, 30.0, 50.0),
            },
            id="both",
        ),
    ],
)
def test_existing_assets_merge_by_the_last_period_they_are_active_in(
    aggregation, expected, vintage_record
):
    """Merged, `on_a` and `on_b` of 2003 and 2010 are built in 2010 and retire in 2033."""
    merged = aggregate_network(to_network(vintage_record), vintage_record, aggregation)
    onwind = merged.generators[merged.generators["carrier"] == "onwind"]
    columns = ["bus", "build_year", "lifetime", "p_nom"]

    assert dict(zip(onwind.index, onwind[columns].itertuples(index=False), strict=True)) == expected


@pytest.mark.parametrize("builder", ["new_multi_period_network", "new_single_period_network"])
def test_merged_existing_assets_that_never_retire_keep_an_infinite_lifetime(
    builder, store_revision, request
):
    """Merged, `on_a` and `on_b` are built in their later build year, as PyPSA-Eur merges
    existing hydro plants and batteries."""
    n = request.getfixturevalue(builder)()
    n.add(
        "Generator",
        ["on_a", "on_b"],
        bus="bus",
        carrier="onwind",
        p_nom=10.0,
        build_year=[2000, 2010],
        lifetime=np.inf,
        asset_status="existing",
    )
    rev = store_revision(n, "lifetimes")
    merged = aggregate_network(to_network(rev), rev, CARRIERS)

    assert merged.generators.loc["on_a", ["build_year", "lifetime"]].tolist() == [2010, np.inf]
    assert "on_b" not in merged.generators.index


STAGGERED = pd.DataFrame(
    {"build_year": [2025, 2045], "lifetime": [30.0, 10.0], "p_nom": [10.0, 20.0]},
    index=pd.Index(["on_x", "on_y"]),
)
"""Existing onwind units both last active in 2050: `on_x` first in 2030, `on_y` in 2050."""


@pytest.fixture(scope="module")
def staggered_record(module_store, new_multi_period_network) -> Revision:
    n = new_multi_period_network()
    n.add("Generator", STAGGERED.index, bus="bus", carrier="onwind", **STAGGERED)
    n.generators.loc[STAGGERED.index, "asset_status"] = "existing"
    return module_store(n, "staggered")


def test_existing_assets_first_active_in_different_periods_stay_apart(staggered_record):
    merged = aggregate_network(to_network(staggered_record), staggered_record, CARRIERS)

    assert merged.generators.loc[STAGGERED.index, "p_nom"].tolist() == [10.0, 20.0]


def test_merging_keeps_candidates_apart_from_existing_assets_of_their_cohort(store_revision):
    """`gas_c` is a candidate of the cohort of the existing `gas_old`, PyPSA's default one."""
    n = new_zoned_network()
    n.add("Generator", "gas_old", bus="c", carrier="gas", p_nom=50.0)
    n.generators.loc["gas_old", "asset_status"] = "existing"
    rev = store_revision(n, "mixed")
    merged = aggregate_network(to_network(rev), rev, SPATIAL)
    gas = merged.generators[merged.generators["carrier"] == "gas"]

    assert gas[["p_nom_extendable", "p_nom"]].to_dict("index") == {
        "gas_c": {"p_nom_extendable": True, "p_nom": 0.0},
        "gas_old": {"p_nom_extendable": False, "p_nom": 50.0},
    }


def test_merging_by_bus_keeps_line_cohorts_apart(store_revision):
    n = new_zoned_network()
    n.lines.loc["db", "build_year"] = 2025
    rev = store_revision(n, "line_cohorts")
    merged = aggregate_network(to_network(rev), rev, Aggregation(bus="zone"))

    assert merged.lines["build_year"].to_dict() == {"ac": 0, "db": 2025}


@pytest.mark.parametrize(
    ("aggregation", "match"),
    [
        (Aggregation(bus="zone"), "no bus property 'zone'"),
        (Aggregation(entity="zone"), "no entity property 'zone'"),
    ],
)
def test_merging_needs_its_property(aggregation, match, single_period):
    with pytest.raises(ValueError, match=match):
        aggregate_network(to_network(single_period), single_period, aggregation)


def _drop_status(n: pypsa.Network) -> None:
    for c in n.components[ASSETS]:
        c.static.drop(columns="asset_status", inplace=True)


def _unset_status(n: pypsa.Network) -> None:
    n.generators.loc["gas_d", "asset_status"] = np.nan


@pytest.mark.parametrize(
    ("unset", "match"),
    [
        (_drop_status, "entity property 'asset_status', which entity agg"),
        (_unset_status, r"entity.asset_status is not set for \['gas_d'\]"),
    ],
)
def test_merging_by_entity_needs_the_asset_status(unset, match, store_revision):
    n = new_zoned_network()
    unset(n)
    rev = store_revision(n, "statusless")
    with pytest.raises(ValueError, match=match):
        aggregate_network(to_network(rev), rev, Aggregation(entity="carrier"))


HYDRO_ATTRIBUTES = {
    "p_nom_min": [1.0, 2.0],
    "p_nom_max": [20.0, 40.0],
    "p_min_pu": [0.1, 0.3],
    "marginal_cost": [4.0, 8.0],
    "efficiency": [0.4, 0.6],
    "ramp_limit_up": [0.5, 0.8],
    "ramp_limit_down": [0.9, 0.3],
    "ramp_limit_start_up": [0.2, 0.6],
    "ramp_limit_shut_down": [0.1, 0.5],
    "capital_cost": [2.0, 6.0],
    "committable": [False, True],
    "build_year": [2010, 2020],
    "lifetime": [25.0, 40.0],
}
"""Attributes of the existing hydro plants, which merge into `hydro_a`."""

HYDRO_P_MAX_PU = np.array([[0.2, 0.6], [0.4, 0.8], [1.0, 0.0], [0.0, 1.0], [0.5, 0.5], [0.8, 0.4]])
"""Availability of the existing hydro plants at each snapshot."""

BATTERY_ATTRIBUTES = {
    "p_nom_extendable": False,
    "max_hours": [2.0, 6.0],
    "asset_status": "existing",
}
"""Attributes of the batteries, made existing, which merge into `bat_a`."""


@pytest.fixture(scope="module")
def merge_hydro(module_store) -> Callable[[tuple], pypsa.Network]:
    """Return a function that merges the zoned network with hydro plants and existing
    batteries of `p_nom`, once."""
    merged: dict[tuple, pypsa.Network] = {}

    def merge(p_nom: tuple) -> pypsa.Network:
        if p_nom not in merged:
            n = new_zoned_network()
            n.generators.loc[HYDRO, "p_nom"] = p_nom
            for attr, values in HYDRO_ATTRIBUTES.items():
                n.generators.loc[HYDRO, attr] = values
            n.generators_t.p_max_pu[HYDRO] = HYDRO_P_MAX_PU
            n.storage_units.loc[BATTERIES, "p_nom"] = p_nom
            for attr, values in BATTERY_ATTRIBUTES.items():
                n.storage_units.loc[BATTERIES, attr] = values
            rev = module_store(n, "hydro")
            merged[p_nom] = aggregate_network(to_network(rev), rev, SPATIAL)
        return merged[p_nom]

    return merge


@pytest.mark.parametrize(
    ("p_nom", "attr", "expected"),
    [
        pytest.param((10.0, 30.0), "p_nom", 40.0, id="sum-p_nom"),
        pytest.param((10.0, 30.0), "capital_cost", 5.0, id="weighted-capital_cost"),
        pytest.param((0.0, 0.0), "capital_cost", 4.0, id="uniform-capital_cost"),
        pytest.param((10.0, 30.0), "p_nom_min", 3.0, id="sum-p_nom_min"),
        pytest.param((10.0, 30.0), "p_nom_max", 60.0, id="sum-p_nom_max"),
        pytest.param((10.0, 30.0), "p_min_pu", 0.25, id="weighted-p_min_pu"),
        pytest.param((10.0, 30.0), "marginal_cost", 7.0, id="weighted-marginal_cost"),
        pytest.param((10.0, 30.0), "efficiency", 0.55, id="weighted-efficiency"),
        pytest.param((0.0, 0.0), "marginal_cost", 6.0, id="uniform-marginal_cost"),
        pytest.param((0.0, 0.0), "efficiency", 0.5, id="uniform-efficiency"),
        pytest.param((10.0, 30.0), "ramp_limit_up", 0.8, id="max-ramp_limit_up"),
        pytest.param((10.0, 30.0), "ramp_limit_down", 0.9, id="max-ramp_limit_down"),
        pytest.param((10.0, 30.0), "ramp_limit_start_up", 0.4, id="mean-ramp_limit_start_up"),
        pytest.param((10.0, 30.0), "ramp_limit_shut_down", 0.3, id="mean-ramp_limit_shut_down"),
        pytest.param((10.0, 30.0), "committable", True, id="any-committable"),
        pytest.param((10.0, 30.0), "build_year", 2020, id="last-build_year"),
        pytest.param((10.0, 30.0), "lifetime", 15.0, id="first-retirement-lifetime"),
    ],
)
def test_existing_assets_merge_as_pypsa_eur_merges_power_plants(p_nom, attr, expected, merge_hydro):
    merged = merge_hydro(p_nom)

    assert list(merged.generators.index[merged.generators["carrier"] == "hydro"]) == ["hydro_a"]
    assert np.isclose(merged.generators.loc["hydro_a", attr], expected)


@pytest.mark.parametrize(
    ("p_nom", "shares"),
    [
        pytest.param((10.0, 30.0), [0.25, 0.75], id="weighted"),
        pytest.param((0.0, 0.0), [0.5, 0.5], id="uniform"),
    ],
)
def test_existing_assets_merge_series_and_storage_by_capacity(p_nom, shares, merge_hydro):
    merged = merge_hydro(p_nom)

    assert list(merged.storage_units.index) == ["bat_a"]
    assert np.isclose(merged.storage_units.loc["bat_a", "max_hours"], np.r_[2.0, 6.0] @ shares)
    np.testing.assert_allclose(merged.generators_t.p_max_pu["hydro_a"], HYDRO_P_MAX_PU @ shares)


def _active_existing(n: pypsa.Network, ctype: str) -> pd.DataFrame:
    """Return whether each existing asset of `ctype` in `n` is active in each period."""
    c = n.components[ctype]
    periods = n.investment_periods.tolist() or [None]
    active = pd.DataFrame({period: c.get_active_assets(period) for period in periods})
    return active[c.static["asset_status"] == "existing"]


def _existing_capacity(n: pypsa.Network, ctype: str, buses: pd.Series) -> pd.DataFrame:
    """Return the active capacity of the existing assets of `ctype` in `n` in each period,
    by zone and carrier."""
    active = _active_existing(n, ctype)
    static = n.components[ctype].static.loc[active.index]
    nominal = "e_nom" if ctype == "Store" else "p_nom"
    capacity = active.mul(static[nominal], axis=0)
    return capacity.groupby([static["bus"].map(buses), static["carrier"]]).sum()


def _existing_keys(n: pypsa.Network, ctype: str) -> pd.DataFrame:
    """Return the bus, carrier, resource class and first and last active periods of each
    existing asset of `ctype` in `n`."""
    active = _active_existing(n, ctype)
    static = n.components[ctype].static.loc[active.index]
    keys = static[static.columns.intersection(["bus", "carrier", "resource_class"])]
    return keys.assign(first=active.idxmax(axis=1), last=active.iloc[:, ::-1].idxmax(axis=1))


def _existing_network() -> pypsa.Network:
    """Build the zoned network with every asset existing and hydro plants of two cohorts."""
    n = set_status(new_zoned_network(), "existing")
    n.generators.loc[HYDRO, "build_year"] = [2010, 2020]
    return n


@pytest.fixture(scope="module")
def existing_record(module_store) -> Revision:
    return module_store(_existing_network(), "existing")


@pytest.mark.parametrize(
    ("record_name", "aggregation", "ctype"),
    [
        ("existing_record", SPATIAL, "Generator"),
        ("existing_record", SPATIAL, "StorageUnit"),
        ("existing_record", SPATIAL, "Store"),
        ("existing_record", Aggregation(entity="carrier"), "Generator"),
        ("existing_record", Aggregation(entity="carrier"), "StorageUnit"),
        ("existing_record", Aggregation(entity="carrier"), "Store"),
        ("vintage_record", Aggregation(entity="carrier"), "Generator"),
        ("vintage_record", Aggregation(bus="carrier", entity="carrier"), "Generator"),
        ("staggered_record", CARRIERS, "Generator"),
    ],
)
def test_merged_existing_assets_are_one_per_group_with_their_capacity_in_each_period(
    record_name, aggregation, ctype, request
):
    rev = request.getfixturevalue(record_name)
    n = to_network(rev)
    buses = spatial_maps(n, rev, aggregation).buses
    merged = aggregate_network(to_network(rev), rev, aggregation)
    before = _existing_capacity(n, ctype, buses)
    after = _existing_capacity(merged, ctype, merged.buses.index.to_series())

    assert not _existing_keys(merged, ctype).duplicated().any()
    pd.testing.assert_frame_equal(after, before, check_index_type=False)


@pytest.fixture(scope="module")
def solved_vintages(vintage_record) -> tuple[pypsa.Network, pypsa.Network]:
    """Return the vintage network merged by carrier and solved over its periods, and the
    network with its buses and assets expanded."""
    aggregation = Aggregation(entity="carrier")
    n = to_network(vintage_record)
    n_c = aggregate_network(n, vintage_record, aggregation)
    optimize_network(n_c, PyPSAOptimizeSchema(), multi_investment_periods=True)
    return n_c, write_aggregated_results(n_c, n, vintage_record, aggregation, True)[0]


def test_existing_assets_active_in_no_period_are_left_out_and_keep_their_capacity(
    solved_vintages,
):
    n_c, n = solved_vintages

    assert "on_f" not in n_c.generators.index
    assert n.generators.loc["on_f", "p_nom_opt"] == 60.0
    assert (n.generators_t.p["on_f"] == 0).all()


def test_merged_existing_capacity_and_flows_split_by_capacity(solved_vintages):
    n_c, n = solved_vintages
    flows = n.generators_t.p[["on_a", "on_b"]]

    assert n_c.generators_t.p["on_a"].abs().max() > 1
    np.testing.assert_allclose(n.generators.loc[["on_a", "on_b"], "p_nom_opt"], [10.0, 20.0])
    np.testing.assert_allclose(flows.sum(axis=1), n_c.generators_t.p["on_a"])
    np.testing.assert_allclose(2 * flows["on_a"], flows["on_b"])


@pytest.fixture(scope="module")
def solved(module_store) -> tuple[pypsa.Network, pypsa.Network]:
    """Return the zoned network merged by zone and carrier and solved, and its expanded results."""
    rev = module_store(new_zoned_network(), "zoned")
    n = to_network(rev)
    n_c = aggregate_network(n, rev, SPATIAL)
    optimize_network(n_c, PyPSAOptimizeSchema(assign_all_duals=True))
    _, result = write_aggregated_results(n_c, n, rev, SPATIAL, False)
    return n_c, to_network(result)


@pytest.mark.parametrize(
    ("ctype", "attr", "member", "representative", "source"),
    [
        ("Bus", "marginal_price", "b", "a", "marginal_price"),
        ("Bus", "marginal_price", "d", "c", "marginal_price"),
        ("Generator", "mu_upper", "solar_b", "solar_a", "mu_upper"),
        ("Line", "mu_upper", "ac", "ac", "mu_upper"),
        ("Line", "mu_upper", "db", "ac", "mu_lower"),
    ],
)
def test_merged_members_hold_the_duals_of_what_they_merged_into(
    ctype, attr, member, representative, source, solved
):
    """Line `db` runs against the line it merged into, so its upper bound is the lower one."""
    n_c, n = solved
    held = n_c.components[ctype].dynamic[source][representative]
    pd.testing.assert_series_equal(
        n.components[ctype].dynamic[attr][member], held, check_names=False
    )


def test_merged_line_flows_and_capacity_split_by_capacity(solved):
    n_c, n = solved
    flows = n.lines_t.p0
    built = n.lines.s_nom_opt

    assert flows["ac"].abs().max() > 1
    np.testing.assert_allclose(flows["ac"] - flows["db"], n_c.lines_t.p0["ac"])
    np.testing.assert_allclose(3 * flows["ac"], -flows["db"])
    np.testing.assert_allclose(built[["ac", "db"]], n_c.lines.s_nom_opt["ac"] * np.r_[0.25, 0.75])
    assert (built[["ab", "cd"]] == n.lines.s_nom[["ab", "cd"]]).all()


def test_moved_assets_keep_their_results(solved):
    n_c, n = solved
    moved = ["dc", "loop"]

    assert n_c.links.loc["loop", "bus0"] == n_c.links.loc["loop", "bus1"]
    pd.testing.assert_frame_equal(
        n_c.links.loc[moved, ["length", "capital_cost"]],
        n.links.loc[moved, ["length", "capital_cost"]],
        **UNTYPED,
    )
    pd.testing.assert_frame_equal(n.links_t.p0[moved], n_c.links_t.p0[moved], check_names=False)
    assert n.loads_t.p["load_d"].equals(n_c.loads_t.p["load_d"])


@pytest.mark.parametrize(
    ("ctype", "members", "shares"),
    [
        pytest.param("Generator", SOLAR, [0.25, 0.75], id="solar"),
        pytest.param("Generator", GAS, [0.5, 0.5], id="gas-unlimited"),
        pytest.param("Generator", HYDRO, [0.25, 0.75], id="hydro-fixed"),
        pytest.param("StorageUnit", BATTERIES, [0.25, 0.75], id="battery"),
    ],
)
def test_merged_capacity_splits_by_largest_capacity(ctype, members, shares, solved):
    n_c, n = solved
    total = n_c.components[ctype].static.loc[members[0], "p_nom_opt"]

    assert total > 1
    np.testing.assert_allclose(
        n.components[ctype].static.loc[members, "p_nom_opt"], total * np.r_[shares]
    )


@pytest.mark.parametrize(
    ("ctype", "members", "attr"),
    [
        ("Generator", SOLAR, "p"),
        ("Generator", GAS, "p"),
        ("Generator", HYDRO, "p"),
        ("StorageUnit", BATTERIES, "p"),
        ("StorageUnit", BATTERIES, "state_of_charge"),
        ("Load", LOADS, "p"),
    ],
)
def test_merged_flows_keep_the_total_of_what_they_merged_into(ctype, members, attr, solved):
    n_c, n = solved
    merged = n_c.components[ctype].dynamic[attr][members[0]]

    assert merged.abs().max() > 1
    np.testing.assert_allclose(n.components[ctype].dynamic[attr][members].sum(axis=1), merged)


@pytest.mark.parametrize("members", [SOLAR, HYDRO])
def test_merged_generation_stays_within_each_capacity(members, solved):
    _, n = solved
    generation = n.generators_t.p[members]
    p_max_pu = n.get_switchable_as_dense("Generator", "p_max_pu")[members]
    available = p_max_pu * n.generators.p_nom_opt[members]

    assert (generation <= available + 1e-6).all().all()
    assert (generation[available == 0].fillna(0) == 0).all().all()


def test_merged_loads_draw_their_own_demand(solved):
    _, n = solved
    demand = n.get_switchable_as_dense("Load", "p_set")[LOADS]
    pd.testing.assert_frame_equal(n.loads_t.p[LOADS], demand, **UNTYPED)


def test_merged_loads_whose_demand_cancels_draw_their_own_demand(store_revision):
    n = new_zoned_network()
    n.loads.loc["load_b", "p_set"] = -20.0
    rev = store_revision(n, "cancelling")
    n = to_network(rev)
    n_c = optimize_network(aggregate_network(n, rev, SPATIAL), PyPSAOptimizeSchema())
    expanded, _ = write_aggregated_results(n_c, n, rev, SPATIAL, False)
    demand = expanded.get_switchable_as_dense("Load", "p_set")[LOADS]

    pd.testing.assert_frame_equal(expanded.loads_t.p[LOADS], demand, **UNTYPED)


LAND_USE = pd.DataFrame(
    {
        "bus": ["b", "a", "c", "d", ""],
        "carrier_attribute": ["solar", "solar", "gas", "gas", "solar"],
        "constant": [20.0, 40.0, 100.0, 200.0, 1000.0],
    },
    index=pd.Index(
        ["land_use solar b", "land_use solar a", "land_use gas c", "land_use gas d", "solar"]
    ),
)
"""Limits on the extendable capacity of a carrier at a bus, as PyPSA-Eur names its land-use
limits, and one at no bus."""

POTENTIALS = pd.DataFrame(
    {
        "p_nom_max": [10.0, 20.0, 40.0, np.inf, 50.0, 60.0, 70.0],
        "resource_class": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
    },
    index=pd.Index(
        [
            "gen-2030",
            "gen-2030-bus2",
            "gen-2040",
            "gen-2040-bus2",
            "gen-2050",
            "gen-2050-bus2",
            "gen-2050-rc1",
        ]
    ),
)
"""The potentials of the gas candidates at `bus` and `bus2`, one each per period, and at
`bus` of another resource class in 2050."""

PERIOD_LIMITS = pd.DataFrame(
    [
        ("bus", 2030, 10.0),
        ("bus2", 2030, 20.0),
        ("bus", 2040, 40.0),
        ("bus", 2050, 50.0),
        ("bus2", 2050, 60.0),
    ],
    columns=["bus", "investment_period", "constant"],
)
PERIOD_LIMITS.index = (
    "land_use gas " + PERIOD_LIMITS["bus"] + " " + PERIOD_LIMITS["investment_period"].astype(str)
)
"""The land-use limits PyPSA-Eur sets from `POTENTIALS`: the smallest `p_nom_max` of the
candidates at each bus built in each period, and none where that is infinite."""


@pytest.fixture(scope="module")
def land_use_record(module_store, new_multi_period_network) -> Revision:
    """Store the network of two buses and three periods with `POTENTIALS`, `PERIOD_LIMITS`
    and a CO2 limit at no bus."""
    n = _two_bus_periods_network(new_multi_period_network)
    n.add("Generator", "gen-2050-rc1", bus="bus", carrier="gas", build_year=2050, lifetime=30)
    n.generators.loc["gen-2050-rc1", ["p_nom_extendable", "asset_status"]] = [True, "candidate"]
    n.generators[POTENTIALS.columns] = POTENTIALS
    n.add("GlobalConstraint", PERIOD_LIMITS.index, carrier_attribute="gas", **PERIOD_LIMITS)
    n.global_constraints["type"] = "tech_capacity_expansion_limit"
    n.add("GlobalConstraint", "co2", type="primary_energy", constant=1000.0)
    n.global_constraints["sense"] = "<="
    return module_store(n, "land_use")


@pytest.mark.parametrize(
    ("aggregation", "expected"),
    [
        pytest.param(
            Aggregation(bus="carrier", entity="carrier"),
            {"land_use gas bus 2030": 30.0, "land_use gas bus 2050": 70.0},
            id="both",
        ),
        pytest.param(
            Aggregation(entity="carrier"), PERIOD_LIMITS["constant"].to_dict(), id="entities"
        ),
    ],
)
def test_land_use_limits_are_the_smallest_potential_of_the_merged_candidates(
    aggregation, expected, land_use_record
):
    """Merged by bus and carrier, the 2050 candidates of class 0 have 110 and of class 1 70,
    and the 2040 candidate has no limit, so 2040 has none."""
    n_c = aggregate_network(to_network(land_use_record), land_use_record, aggregation)
    limits = n_c.global_constraints

    assert list(limits["constant"].items()) == [*expected.items(), ("co2", 1000.0)]
    assert limits.loc[list(expected), "bus"].tolist() == [name.split()[2] for name in expected]


@pytest.mark.parametrize(
    ("aggregation", "attrs", "expectation"),
    [
        pytest.param(
            Aggregation(entity="carrier"),
            {"constant": 15.0},
            pytest.raises(ValueError, match=r"rule: \['land_use gas bus 2030'\]"),
            id="other-constant",
        ),
        pytest.param(
            Aggregation(entity="carrier"),
            {"bus": "bus2", "investment_period": 2040},
            pytest.raises(ValueError, match=r"rule: \['land_use gas bus 2030'\]"),
            id="no-finite-potential",
        ),
        pytest.param(
            Aggregation(entity="carrier"),
            {"investment_period": np.nan},
            pytest.raises(ValueError, match=r"period: \['land_use gas bus 2030'\]"),
            id="no-period",
        ),
        pytest.param(
            Aggregation(bus="carrier"),
            {"constant": 10.0},
            pytest.raises(NotImplementedError, match=r"generators \['gen-2030', 'gen-2040'"),
            id="candidates-of-one-class-at-a-bus",
        ),
    ],
)
def test_land_use_limits_must_be_stated_by_the_rule_of_pypsa_eur(
    aggregation, attrs, expectation, land_use_record
):
    n = to_network(land_use_record)
    n.global_constraints.loc["land_use gas bus 2030", list(attrs)] = list(attrs.values())

    with expectation:
        aggregate_network(n, land_use_record, aggregation)


def test_land_use_limits_without_extendable_generators_are_dropped(land_use_record):
    n = to_network(land_use_record)
    n.generators["p_nom_extendable"] = False
    n_c = aggregate_network(n, land_use_record, Aggregation(entity="carrier"))
    assert n_c.global_constraints.index.tolist() == ["co2"]


def test_fixed_capacities_leave_no_land_use_limit_to_merge(land_use_record):
    expanded = _run(OvernightCapacityExpansion, {}, land_use_record)
    n = to_network(expanded, select={"period": [2050]})
    fix_capacities(n, expanded, [2050])

    n_c = aggregate_network(n, land_use_record, Aggregation(entity="carrier"))

    assert n_c.global_constraints.index.tolist() == ["co2"]


@pytest.mark.parametrize(
    ("member", "mu"),
    [
        ("land_use gas bus 2030", 3.0),
        ("land_use gas bus2 2030", 3.0),
        ("land_use gas bus 2040", 0.0),
        ("land_use gas bus 2050", 5.0),
        ("land_use gas bus2 2050", 5.0),
        ("co2", 7.0),
    ],
)
def test_land_use_limits_hold_the_dual_of_the_limit_stated_for_their_merged_bus(
    member, mu, land_use_record
):
    """`land_use gas bus 2040` was not stated again, so it holds none."""
    n = to_network(land_use_record)
    aggregation = Aggregation(bus="carrier", entity="carrier")
    n_c = aggregate_network(n, land_use_record, aggregation)
    n_c.global_constraints["mu"] = pd.Series(
        {"land_use gas bus 2030": 3.0, "land_use gas bus 2050": 5.0, "co2": 7.0}
    )

    expanded = expand_network(n_c, n, land_use_record, aggregation)

    assert expanded.global_constraints.loc[member, "mu"] == mu


@pytest.fixture
def spaced_land_use(store_revision) -> pd.Series:
    """Return how zones merge land-use limits per period at buses `BE0 0` and `BE0 1` in
    zone west, after `BE0 0`, and at `BE0 10` alone in zone east, as PyPSA-Eur names them."""
    n = new_zoned_network()
    n.add("Bus", ["BE0 0", "BE0 1", "BE0 10"], carrier="AC")
    n.buses.loc[["BE0 0", "BE0 1", "BE0 10"], "zone"] = ["west", "west", "east"]
    limits = [("BE0 1", 2030), ("BE0 0", 2030), ("BE0 1", 2040), ("BE0 0", 2040), ("BE0 10", 2030)]
    names = [f"land_use solar {bus} {period}" for bus, period in limits]
    buses, periods = zip(*limits, strict=True)
    n.add(
        "GlobalConstraint",
        names,
        type="tech_capacity_expansion_limit",
        bus=list(buses),
        carrier_attribute="solar",
        investment_period=list(periods),
        constant=10.0,
    )
    rev = store_revision(n, "spaced_land_use")
    return spatial_maps(to_network(rev), rev, ZONES).constraints


@pytest.mark.parametrize(
    ("member", "merged"),
    [
        ("land_use solar BE0 1 2030", "land_use solar BE0 0 2030"),
        ("land_use solar BE0 0 2030", "land_use solar BE0 0 2030"),
        ("land_use solar BE0 1 2040", "land_use solar BE0 0 2040"),
        ("land_use solar BE0 0 2040", "land_use solar BE0 0 2040"),
        ("land_use solar BE0 10 2030", "land_use solar BE0 10 2030"),
    ],
)
def test_land_use_limits_merge_per_period_under_their_merged_bus(member, merged, spaced_land_use):
    assert spaced_land_use[member] == merged


@pytest.mark.parametrize(
    ("aggregation", "kind", "bus", "carrier", "expectation"),
    [
        pytest.param(
            ZONES,
            "operational_limit",
            "b",
            "solar",
            pytest.raises(NotImplementedError, match="'operational_limit'"),
            id="unknown-type-at-bus",
        ),
        pytest.param(
            ZONES,
            "primary_energy",
            "c",
            "solar",
            pytest.raises(NotImplementedError, match=r"\['limit'\]"),
            id="names-the-constraint",
        ),
        pytest.param(
            ZONES,
            "tech_capacity_expansion_limit",
            "b",
            "",
            pytest.raises(NotImplementedError, match=r"\['limit'\]"),
            id="limit-of-no-carrier",
        ),
        pytest.param(ZONES, "primary_energy", "", "solar", nullcontext(), id="at-no-bus"),
        pytest.param(CARRIERS, "operational_limit", "b", "solar", nullcontext(), id="by-carrier"),
    ],
)
def test_merging_by_bus_needs_a_rule_for_the_type_of_global_constraints_at_buses(
    aggregation, kind, bus, carrier, expectation, store_revision
):
    n = new_zoned_network()
    n.add("GlobalConstraint", LAND_USE.index, type="tech_capacity_expansion_limit", **LAND_USE)
    n.add("GlobalConstraint", "limit", type=kind, bus=bus, carrier_attribute=carrier)
    rev = store_revision(n, "typed_limits")

    with expectation:
        spatial_maps(to_network(rev), rev, aggregation)


def test_merged_constraints_of_different_periods_keep_names_of_their_own(store_revision):
    n = new_zoned_network()
    n.add(
        "GlobalConstraint",
        ["limit a", "limit b"],
        type="tech_capacity_expansion_limit",
        bus=["a", "b"],
        carrier_attribute="solar",
        investment_period=[2030, 2040],
    )
    rev = store_revision(n, "period_limits")
    maps = spatial_maps(to_network(rev), rev, ZONES)

    assert maps.constraints[["limit a", "limit b"]].tolist() == ["limit a", "limit b"]


def _keys(rev: Revision, name: str) -> set[tuple]:
    """Return the labels of the rows of result `name` in `rev`, without their values."""
    frame = series_frame(rev.record, name)
    if "connection" in frame:
        frame["connection"] = frame["connection"].map(lambda c: tuple(c.values()))
    labels = frame.drop(columns=["value", "attribute", "breakpoint"], errors="ignore")
    return set(labels.itertuples(index=False))


@pytest.mark.parametrize(
    ("record_name", "spatial", "n_hours"),
    [
        pytest.param("zoned_record", {"bus": "zone", "entity": "carrier"}, 3, id="zoned"),
        pytest.param(
            "bel_status_record",
            {"bus": "carrier", "entity": "carrier"},
            72,
            marks=pytest.mark.slow,
            id="pypsa-eur-test-elec-preaggregated-perfect-datarecords",
        ),
    ],
)
def test_solving_by_every_aggregation_writes_results_as_solving_by_time_alone(
    record_name, spatial, n_hours, request
):
    rev = _run(
        TimePartition, {"name": "agg", "n_hours": n_hours}, request.getfixturevalue(record_name)
    )
    by_time = _run(OvernightCapacityExpansion, {"aggregation": {"snapshot": "agg"}}, rev)
    merged = _run(OvernightCapacityExpansion, {"aggregation": {"snapshot": "agg", **spatial}}, rev)

    assert merged.ancestry() == [*rev.ancestry(), merged.id]
    assert len(snapshot_frame(merged.record)) == len(to_network(rev).snapshots)
    for name in ["p", "marginal_price", "p_nom_opt", "s_nom_opt"]:
        assert _keys(merged, name) == _keys(by_time, name)


def _clipped_network() -> pypsa.Network:
    """Give the zoned network a static `p_max_pu` of 0.1 at `hydro_a`, and the solar profile
    of `solar_a` as the inflow of `bat_a` and, negated, as the `p_min_pu` of link `dc`."""
    n = new_zoned_network()
    profile = n.generators_t.p_max_pu["solar_a"]
    n.generators.loc["hydro_a", "p_max_pu"] = 0.1
    n.storage_units_t.inflow["bat_a"] = profile
    n.links_t.p_min_pu["dc"] = -profile
    return n


@pytest.mark.parametrize("bus", [None, "zone"])
@pytest.mark.parametrize(
    ("threshold", "expected"),
    [
        pytest.param(None, [0.0, 0.5, 1.0, 0.5, 0.0, 0.2], id="unset"),
        pytest.param(0.2, [0.0, 0.5, 1.0, 0.5, 0.0, 0.0], id="at-threshold"),
        pytest.param(0.5, [0.0, 0.0, 1.0, 0.0, 0.0, 0.0], id="above-threshold"),
    ],
)
def test_clipping_sets_small_time_varying_limits_to_zero(bus, threshold, expected, store_revision):
    rev = store_revision(_clipped_network(), "clipped")
    n = to_network(rev)
    merged = aggregate_network(n, rev, Aggregation(bus=bus, clip_p_max_pu=threshold))

    np.testing.assert_allclose(merged.generators_t.p_max_pu["solar_a"], expected)
    np.testing.assert_allclose(merged.storage_units_t.inflow["bat_a"], expected)
    np.testing.assert_allclose(merged.links_t.p_min_pu["dc"], np.negative(expected))
    assert merged.generators.loc["hydro_a", "p_max_pu"] == 0.1
    np.testing.assert_allclose(n.generators_t.p_max_pu["solar_a"], [0.0, 0.5, 1.0, 0.5, 0.0, 0.2])


def test_clipping_refuses_a_negative_threshold():
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        Aggregation(clip_p_max_pu=-0.01)
