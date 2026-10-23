# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""The scenario axis and per-scenario overlay.

Notes
-----
- [partial](https://energy-models.github.io/datarecord/design/schema/#partial-the-granularity-of-an-override)
- [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
"""

from pathlib import Path

import pandas as pd
import pytest

from datarecord import Workspace
from datarecord.tools.pypsa import PyPSA
from tests.fixtures import (
    empty_child,
    example,
    export_network,
    relation,
    rename_components,
    write_input,
    write_scenarios,
)
from tests.test_roundtrip import assert_networks_equal


@pytest.fixture(scope="session")
def stochastic():
    """PyPSA's `stochastic_network`, with its generators renamed off their carriers.

    The example names each `Generator` after its `Carrier`, which collides in a
    record. The generators move rather than the carriers, since the
    `carrier` attribute *values* reference the carrier names.

    Notes
    -----
    - [entity is unique across types](https://energy-models.github.io/datarecord/design/format/#entity-is-unique-across-types)
    """
    import pypsa

    n = example(pypsa.examples.stochastic_network)
    rename_components(n, "Generator", " Gen")
    return n


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    """One store for the module: every test branches its own child off `parent`."""
    workspace = Workspace()
    yield workspace.store(str(tmp_path_factory.mktemp("stochastic")))
    workspace.close()


@pytest.fixture(scope="module")
def parent(store, stochastic):
    revision = export_network(stochastic, store)
    revision.materialise()
    return revision


def test_scenario_roundtrip(store, parent, stochastic):
    """A stochastic record round-trips through our reader."""
    n = PyPSA.build(parent.record)
    assert list(n.scenarios) == list(stochastic.scenarios)
    assert_networks_equal(n, stochastic)


def test_map_is_scenario_expanded(store, parent, stochastic):
    """A NULL-scenario row becomes one map entry per scenario.

    Notes
    -----
    - [partial](https://energy-models.github.io/datarecord/design/schema/#partial-the-granularity-of-an-override)
    """
    schema = parent.resolver.schema
    df = parent.resolver.inputs.df()
    by_scenario = df[
        [
            "scenario" in schema.coordinates_of(str(a))
            for a in df["attribute"].astype(str)
        ]
    ]
    assert not by_scenario.empty, "some attribute is addressed by scenario"
    assert set(by_scenario["scenario"]) == set(stochastic.scenarios)

    solar = df[
        (df["entity"] == "solar Gen") & (df["attribute"].astype(str) == "p_max_pu")
    ]
    assert set(solar["scenario"]) == set(stochastic.scenarios)


def test_partial_scenario_override(store, parent, stochastic):
    """A child may replace one scenario and leave the others to the parent."""
    scenario = stochastic.scenarios[0]
    child = empty_child(parent)
    write_input(
        store.layer_dir(child.id),
        "p_max_pu",
        [
            {
                "entity": "solar Gen",
                "scenario": scenario,
                "value": 0.77,
            }
        ],
    )

    df = child.resolver.inputs.df()
    solar = df[
        (df["entity"] == "solar Gen") & (df["attribute"].astype(str) == "p_max_pu")
    ]
    owners = dict(zip(solar["scenario"], solar["layer_uuid"], strict=True))
    assert owners[scenario] == child.id
    for other in stochastic.scenarios[1:]:
        assert owners[other] == parent.id

    # The resolved relation carries the child's value for that scenario only.
    rel = relation(child, "p_max_pu").df()
    solar_rows = rel[rel["entity"] == "solar Gen"]
    overridden = solar_rows[solar_rows["scenario"] == scenario]
    assert set(overridden["value"]) == {0.77}
    assert set(solar_rows[solar_rows["scenario"] != scenario]["value"]) != {0.77}


def test_child_adds_new_scenario(store, parent, stochastic):
    """A child may add a scenario the root never declared.

    Notes
    -----
    - [layered resolution](https://energy-models.github.io/datarecord/design/layers/)
    - [materialised node caches](https://energy-models.github.io/datarecord/design/layers/#materialised-node-caches)
    """
    child = empty_child(parent)
    write_scenarios(
        store.layer_dir(child.id),
        [{"scenario": s} for s in ("high", "low", "med", "extra")],
    )
    write_input(
        store.layer_dir(child.id),
        "scenario_weight",
        [
            {"scenario": s, "value": w}
            for s, w in (("high", 0.27), ("low", 0.36), ("med", 0.27), ("extra", 0.1))
        ],
    )
    write_input(
        store.layer_dir(child.id),
        "p_max_pu",
        [
            {
                "entity": "solar Gen",
                "scenario": "extra",
                "value": 0.33,
            }
        ],
    )

    n = PyPSA.build(child.record)
    assert set(n.scenarios) == set(stochastic.scenarios) | {"extra"}

    rel = relation(child, "p_max_pu").df()
    extra_solar = rel[(rel["entity"] == "solar Gen") & (rel["scenario"] == "extra")]
    assert set(extra_solar["value"]) == {0.33}


def test_scenario_order_survives_a_chain_of_closed_layers(store, parent, stochastic):
    """Axis row order stays root-first, then each layer's own append order.

    `fold_axis` tags each layer's row order (`_row`) before the cross-layer
    `UNION ALL` in `union_all_by_name`, not after: a bare `row_number()` on
    the unioned relation would have no defined order to draw from and could
    silently permute which scenario counts as "first introduced". A single
    child is too small a union to expose this: chain several closed layers,
    each adding one new scenario, to stress the fold across many arms.

    Notes
    -----
    - [materialised node caches](https://energy-models.github.io/datarecord/design/layers/#materialised-node-caches)
    - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
    """
    rec = parent
    added = []
    for i in range(5):
        rec = empty_child(rec)
        name = f"extra{i}"
        write_scenarios(store.layer_dir(rec.id), [{"scenario": name}])
        rec.materialise()
        added.append(name)

    scenarios = rec.resolver.dims.axes["scenario"].df()["scenario"].tolist()
    assert scenarios == list(stochastic.scenarios) + added


def test_resolved_dims_are_node_scoped(store, parent, stochastic):
    """Closing writes the resolved scenario axis to the node cache, not the layer.

    Notes
    -----
    - [materialised node caches](https://energy-models.github.io/datarecord/design/layers/#materialised-node-caches)
    """
    middle = empty_child(parent)
    middle.materialise()

    resolved = Path(store.resolved_dir(middle.id), "dims", "scenario.parquet")
    assert resolved.exists()
    assert set(pd.read_parquet(resolved)["scenario"]) == set(stochastic.scenarios)

    # `middle` wrote nothing itself, so its layer directory has no dims at
    # all - the resolved axis must not have been written there.
    assert not Path(store.layer_dir(middle.id), "dims", "scenario.parquet").exists()


def test_scenario_axis_survives_closed_grandchild(store, parent, stochastic):
    """The scenario axis still comes from the root when a closed node sits in between.

    `middle` is closed but writes nothing scenario-related, so its persisted
    map carries no fresh expansion; the live fold at `grandchild` must expand
    this NULL-scenario row itself, which requires the axis from the true
    root, not just from the nearest closed ancestor.
    """
    middle = empty_child(parent)
    middle.materialise()
    grandchild = empty_child(middle)
    write_input(
        store.layer_dir(grandchild.id),
        "p_max_pu",
        [{"entity": "solar Gen", "value": 0.88}],
    )

    df = grandchild.resolver.inputs.df()
    solar = df[
        (df["entity"] == "solar Gen") & (df["attribute"].astype(str) == "p_max_pu")
    ]
    assert set(solar["scenario"]) == set(stochastic.scenarios)
    assert set(solar["layer_uuid"]) == {grandchild.id}, (
        "the NULL-scenario row replaces the component in every scenario"
    )

    rel = relation(grandchild, "p_max_pu").df()
    assert set(rel[rel["entity"] == "solar Gen"]["value"]) == {0.88}
