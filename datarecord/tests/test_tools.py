# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""The tool layer: verify a record, build a model, read results back.

Notes
-----
- [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
"""

import shutil
from pathlib import Path
from types import SimpleNamespace

import narwhals as nw
import numpy as np
import pandas as pd
import pytest

from datarecord import Workspace
from datarecord.layered.resolve import read_schema, write_schema
from datarecord.tools.base import Requirements, Schema, UnsupportedRecordError
from datarecord.tools.pypsa import (
    ENTITY_TYPE,
    PyPSA,
    _colliding_names,
    _registry_schema,
    _scenario_weights,
)
from tests.fixtures import (
    empty_child,
    export_network,
    outputs,
    relation,
    schema,
    unpacked,
    write_entity_type,
    write_input,
)
from tests.test_roundtrip import assert_networks_equal


@pytest.fixture(scope="module")
def single_revision(tmp_path_factory, ac_dc):
    """`ac_dc` exported once for the module, for tests that only read it."""
    workspace = Workspace()
    yield export_network(ac_dc, workspace.store(str(tmp_path_factory.mktemp("ac_dc"))))
    workspace.close()


@pytest.fixture(scope="module")
def solved(single_revision):
    """The network `single_revision` builds, optimised once for the module."""
    n = PyPSA.build(single_revision.record)
    n.optimize(solver_name="highs")
    return n


@pytest.fixture
def exported(single_revision, workspace, tmp_path):
    """A copy of `single_revision`'s store, for a test to rewrite its files or schema."""
    uri = str(tmp_path / "ac_dc")
    shutil.copytree(single_revision.store.uri, uri)
    (revision,) = workspace.store(uri).revisions()
    return revision


def _flat(frame) -> pd.DataFrame:
    """A connection attribute's rows with the `connection` struct spread to `entity` and `bus`."""
    connection = nw.col("connection").struct
    return (
        nw.from_native(frame)
        .with_columns(entity=connection.field("entity"), bus=connection.field("bus"))
        .lazy()
        .collect(backend="pandas")
        .to_native()
    )


def test_requirements_falsy_when_empty():
    """`bool(Requirements())` distinguishes "nothing missing" from "nothing checked"."""
    assert not Requirements()
    assert Requirements(dims=frozenset({"snapshot"}))
    assert "dims ['snapshot']" in Requirements(dims=frozenset({"snapshot"})).describe()
    assert Requirements().describe() == "nothing"


def test_the_record_layer_imports_no_tool():
    """`datarecord` is framework-free: reading a record never imports PyPSA.

    The call runs from the tool inward (`PyPSA.build(revision.record)`), so there is no
    registry and no name dispatch to drag a framework in.

    Notes
    -----
    - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
    """
    import subprocess
    import sys

    # A fresh interpreter, so an already-imported PyPSA from another test
    # cannot mask a real import edge.
    code = (
        "import sys; import datarecord; import datarecord.tools; "
        "assert 'pypsa' not in sys.modules, sorted(sys.modules)"
    )
    assert subprocess.run([sys.executable, "-c", code], check=False).returncode == 0


def test_verify_accepts_a_complete_record(single_revision):
    """A record written by `export_to_parquet` supplies everything PyPSA needs."""
    assert not PyPSA.verify(single_revision.record)


def test_requires_reports_the_records_own_types(single_revision):
    """`requires` is record-dependent: PyPSA's axes plus this record's types."""
    req = PyPSA.requires(single_revision.record)
    assert {"snapshot", "period", "scenario"} <= req.dims
    assert "Generator" in req.categories
    # Required attributes come from PyPSA's registry, not a list we maintain.
    assert ("Generator", "bus") in req.attributes
    assert ("Line", "x") in req.attributes
    # `name` is the member identity, never an attribute row.
    assert not [a for a in req.attributes if a[1] == "entity"]


def test_verify_reports_a_missing_dim(exported):
    """A schema that declares no `scenario` dim cannot build a network.

    Notes
    -----
    - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
    """
    revision = exported
    _with_schema(revision, dims={"snapshot": nw.Datetime()}, partial=set())

    missing = PyPSA.verify(revision.record)
    assert missing
    assert missing.dims == {"period", "scenario"}
    # A build refuses rather than failing deep inside PyPSA.
    with pytest.raises(UnsupportedRecordError, match="scenario"):
        PyPSA.build(revision.record)


def test_verify_reports_a_type_the_tool_does_not_know(exported):
    """A type outside PyPSA's registry is reported by `verify`, not raised in the fold.

    The type must be one the *schema* declares - the entity-type axis is an
    `Enum` and that vocabulary is upheld everywhere, so a record cannot hold a
    type its own schema excludes. What it can hold is a type this tool has no
    registry entry for, which reads back fine and is this tool's business rather
    than the record layer's. `Requirements.categories` is what carries it.

    Notes
    -----
    - [entity types](https://energy-models.github.io/datarecord/design/schema/#entity_type-the-axis-of-kinds)
    - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
    """
    revision, store = exported, exported.store
    # Declared alongside PyPSA's own types, since the `Enum` pins the
    # vocabulary.
    declared = read_schema(store)
    assert declared.categorizing("entity") == (ENTITY_TYPE,)
    prop = declared.properties["entity"][ENTITY_TYPE]
    assert isinstance(prop.dtype, nw.Enum), "PyPSA declares its types as an enum"
    write_schema(
        declared.model_copy(
            update={
                "properties": {
                    **declared.properties,
                    "entity": {
                        **declared.properties["entity"],
                        ENTITY_TYPE: prop.model_copy(
                            update={
                                "dtype": nw.Enum([*prop.dtype.categories, "Widget"])
                            }
                        ),
                    },
                }
            }
        ),
        revision.store,
    )
    write_entity_type(store.layer_dir(revision.id), "Widget", [{"entity": "w1"}])

    missing = PyPSA.verify(revision.record)
    assert missing.categories == {"Widget"}
    # The types PyPSA does know are not reported.
    assert "Generator" not in missing.categories
    with pytest.raises(UnsupportedRecordError, match="Widget"):
        PyPSA.build(revision.record)


_DIMS = {
    "snapshot": nw.Datetime(),
    "period": nw.Int64(),
    "scenario": nw.String(),
}


def _with_schema(revision, **kwargs) -> None:
    """Redeclare the record's schema, keeping the attributes it already declares.

    Written directly rather than through `write_record`, which would reject an
    incompatible redeclaration - here the point is to hand the tool a
    schema it must report on rather than one the writer accepted.

    Notes
    -----
    - [versioning](https://energy-models.github.io/datarecord/design/schema/#versioning)
    """
    was = read_schema(revision.store)
    now = schema(**kwargs)
    # Keep the old attributes, but drop any dim a redeclaration removed from
    # their address - an attribute over a dim the schema no longer declares is
    # rejected at construction, and the point here is the redeclared dims, not a
    # stale attribute reference to a gone one.
    addressable = set(now.dimensions) | set(was.groups)
    attributes = {
        name: pruned
        for name, spec in was.attributes.items()
        if (pruned := spec.model_copy(update={"dims": spec.dims & addressable})).dims
    }
    traits = {
        ctype: trait.model_copy(
            update={"attributes": trait.attributes & attributes.keys()}
        )
        for ctype, trait in was.traits.items()
    }
    now = now.model_copy(
        update={
            "attributes": attributes,
            "groups": was.groups,
            "properties": was.properties,
            "traits": traits,
            "meta": was.meta,
        }
    )
    write_schema(now, revision.store)


def test_verify_reports_a_snapshot_key(exported):
    """`snapshot` as a key is reported, not crashed on.

    A limit of this tool's *representation*, not of the layer format: PyPSA's
    static/series split needs a component's whole series for an attribute to
    come from one layer, so a stored `snapshot = NULL` broadcast row and a
    descendant's per-snapshot row would coexist with no single container to
    put the result in. The record layer therefore permits the
    declaration - every file does carry the column - and the tool catches it.

    Notes
    -----
    - [partial](https://energy-models.github.io/datarecord/design/schema/#partial-the-granularity-of-an-override)
    """
    revision = exported
    _with_schema(revision, partial={"scenario", "snapshot"})

    missing = PyPSA.verify(revision.record)
    assert ("input_key", "snapshot") in missing.unsupported_keys
    assert "snapshot" in missing.describe()
    with pytest.raises(UnsupportedRecordError, match="snapshot"):
        PyPSA.build(revision.record)


def test_verify_reports_a_missing_required_attribute(exported, ac_dc):
    """A component type with no `bus` anywhere - no connection row supplies it.

    A port's bus is the `connection` tuple itself, declared as no attribute, so
    no default can stand in for it.
    """
    revision, store = exported, exported.store
    # A Generator member with no connection row supplying its bus
    # (https://energy-models.github.io/datarecord/design/record/#connections).
    write_entity_type(store.layer_dir(revision.id), "Generator", [{"entity": "g1"}])
    # One file across every type, so the Generators' rows are dropped from it
    # rather than a per-type file being unlinked.
    path = Path(store.layer_dir(revision.id), "groups", "connection.parquet")
    rows = pd.read_parquet(path)
    generators = set(ac_dc.c["Generator"].static.index) | {"g1"}
    entities = rows["connection"].map(lambda c: c["entity"])
    rows[~entities.isin(generators)].to_parquet(path, index=False)

    write_entity_type(store.layer_dir(revision.id), "Line", [{"entity": "l1"}])

    missing = PyPSA.verify(revision.record)
    assert ("Generator", "bus") in missing.attributes
    assert ("Line", "x") not in missing.attributes, (
        "PyPSA declares the required `x` with a default, resolvable with no row"
    )


def test_verify_reports_a_piecewise_linear_attribute(exported):
    """A curve is stored correctly; it is the PyPSA translation that cannot express it.

    Notes
    -----
    - [wide and long rows](https://energy-models.github.io/datarecord/design/record/#wide-and-long-rows)
    """
    revision, store = exported, exported.store
    write_input(
        store.layer_dir(revision.id),
        "marginal_cost",
        [{"entity": "Manchester Wind", "value": 20.0}],
    )
    assert not PyPSA.verify(revision.record).unsupported_values, (
        "the same attribute without breakpoints is not reported"
    )

    revision = empty_child(revision)
    write_input(
        store.layer_dir(revision.id),
        "marginal_cost",
        [
            {
                "entity": "Manchester Wind",
                "breakpoint": x,
                "value": v,
            }
            for x, v in ((0.0, 20.0), (50.0, 35.0))
        ],
    )

    missing = PyPSA.verify(revision.record)
    assert ("Generator", "marginal_cost") in missing.unsupported_values
    assert "piecewise-linear" in missing.describe()
    with pytest.raises(UnsupportedRecordError):
        PyPSA.build(revision.record)


def test_to_datarecord_rejects_a_cross_type_name_collision(workspace):
    """PyPSA scopes names per type; a record scopes them across every type.

    Reported rather than repaired: renaming to `Generator:north` would hand back
    a network whose components PyPSA can no longer find by their own names, so
    the mismatch is the caller's to reconcile.

    Notes
    -----
    - [entity is unique across types](https://energy-models.github.io/datarecord/design/format/#entity-is-unique-across-types)
    - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
    """
    import pypsa

    n = pypsa.Network()
    n.add("Bus", "north")
    n.add("Generator", "north", bus="north")

    with pytest.raises(UnsupportedRecordError, match="more than one category"):
        PyPSA.to_datarecord(n, workspace.con)


def test_to_datarecord_rejects_a_custom_column_declared_with_another_shape(workspace):
    """A carrier's own `efficiency` has nowhere to go: the name is a per-port attribute."""
    import pypsa

    n = pypsa.Network()
    n.add("Carrier", "AC")
    n.c.Carrier.static["efficiency"] = 0.9

    with pytest.raises(UnsupportedRecordError, match="another shape") as raised:
        PyPSA.to_datarecord(n, workspace.con)
    assert raised.value.missing.columns == {("Carrier", "efficiency")}


def test_a_custom_column_round_trips_on_its_own_type(store):
    """A column PyPSA's registry lacks is an entity column carried by its type alone."""
    import pypsa

    n = pypsa.Network()
    n.set_snapshots(pd.date_range("2030-01-01", periods=2, freq="h"))
    n.add("Bus", "north")
    n.add("Generator", "gen", bus="north")
    n.c.Bus.static["country"] = "DE"

    built = PyPSA.build(export_network(n, store).record)
    assert built.c.Bus.static.loc["north", "country"] == "DE"
    assert "country" not in built.c.Generator.static, "a Generator does not carry it"


def test_to_datarecord_accepts_distinct_names(workspace):
    """The negative half: the same network with distinct names is buildable."""
    import pypsa

    n = pypsa.Network()
    n.add("Bus", "north")
    n.add("Generator", "north gen", bus="north")

    assert not _colliding_names(n)
    assert PyPSA.to_datarecord(n, workspace.con) is not None


def test_sub_networks_are_suffixed_off_the_lines(store, ac_dc):
    """PyPSA numbers SubNetworks `0`, `1`, ... as it numbers Lines.

    The record keys them `0 SubNetwork`, ..., the `sub_network` results
    pointing at them likewise, and `build` takes the suffix off again.
    """
    n = ac_dc.copy()
    n.determine_network_topology()
    assert set(n.c["SubNetwork"].static.index) & set(n.c["Line"].static.index)

    record = export_network(n, store).record
    entities = record.properties["entity"]
    sub_networks = entities.filter(nw.col("entity_type") == "SubNetwork")
    names = sub_networks.collect().to_pandas()["entity"]
    assert sorted(names) == [f"{i} SubNetwork" for i in range(4)]
    results = PyPSA.results(n, store.workspace.con)
    pointed = set(results["sub_network"].collect().to_pandas()["value"])
    assert pointed <= set(names), "a `sub_network` value names a SubNetwork entity"

    built = PyPSA.build(record)
    assert sorted(built.c["SubNetwork"].static.index) == ["0", "1", "2", "3"]


def test_a_stochastic_network_is_not_a_false_collision():
    """A `(scenario, name)` index is one name per component, not one per scenario.

    Comparing the index tuples would report every scenario's copy as a distinct
    name while missing a real cross-type clash.
    """
    import pypsa

    n = pypsa.Network()
    n.set_scenarios(["a", "b"])
    n.add("Bus", "north")
    n.add("Generator", "north gen", bus="north")

    assert not _colliding_names(n)


def test_pypsa_schema_is_the_identity(single_revision):
    """PyPSA defines the record vocabulary today, so nothing is renamed.

    The seam still routes every attribute, so an entry added later takes
    effect with no change to `build`.

    Notes
    -----
    - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
    """
    assert PyPSA.schema.attrs == {}
    assert PyPSA.schema.sources("Generator", "p_max_pu") == ("p_max_pu",)
    identity = PyPSA.schema.resolve(single_revision.record, "Generator", "p_max_pu")
    assert identity.fetchall() == relation(single_revision, "p_max_pu").fetchall()


def test_schema_renames_and_computes():
    """A rename maps one source; a computed attribute maps several (`Attr.compute`)."""
    from datarecord.tools.base import Attr

    schema = Schema(
        {
            "Generator": (
                Attr(name="p_max_pu", source=("availability",)),
                Attr(
                    name="marginal_cost",
                    source=("fuel_cost", "efficiency"),
                    compute=lambda fuel, eff: fuel,
                ),
            )
        }
    )
    assert schema.sources("Generator", "p_max_pu") == ("availability",)
    assert schema.sources("Generator", "marginal_cost") == ("fuel_cost", "efficiency")
    # Anything unmapped, and any other type, stays the identity.
    assert schema.sources("Generator", "p_nom") == ("p_nom",)
    assert schema.sources("Link", "p_max_pu") == ("p_max_pu",)
    # A multi-source rename with no way to combine them is a declaration bug.
    with pytest.raises(ValueError, match="exactly one"):
        Attr(name="x", source=("a", "b"))


def test_results_extracts_long_form_outputs(single_revision, solved):
    """A solved network's results come back keyed by attribute, long-form.

    Notes
    -----
    - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
    """
    n = solved

    results = PyPSA.results(n, single_revision.record.con)
    assert "p" in results
    assert "p_nom_opt" in results

    # Narwhals frames, so the seam names no one dataframe library, and lazy so a
    # tool may fetch on demand (https://energy-models.github.io/datarecord/design/tools/).
    assert isinstance(results["p"], nw.LazyFrame)
    p = results["p"].collect()
    # The long schema's columns (https://energy-models.github.io/datarecord/design/record/), so the write path can persist it as-is -
    # and no `entity_type`, an attribute row being keyed by `name` (https://energy-models.github.io/datarecord/design/format/#entity-is-unique-across-types).
    assert {"connection", "snapshot", "scenario", "period", "value"} <= set(p.columns)
    assert "entity_type" not in p.columns
    assert set(p["attribute"].to_list()) == {"p"}
    # Series output: one row per (name, snapshot), for the Generator rows -
    # selected by name, since the frame no longer carries the type.
    gens = set(n.c["Generator"].static.index)
    gen = _flat(p).query("entity in @gens")
    assert len(gen) == len(n.snapshots) * len(gens)

    # A static output has no snapshot, and only the components whose value
    # differs from the default appear (some generators solve to p_nom_opt=0).
    nom = results["p_nom_opt"].collect()
    nom = nom.filter(nw.col("entity").is_in(list(gens)))
    assert nom["snapshot"].is_null().all()
    nonzero = n.c["Generator"].static["p_nom_opt"] != 0.0
    assert set(nom["entity"].to_list()) == set(n.c["Generator"].static.index[nonzero])


def test_results_skips_outputs_still_at_their_default(single_revision):
    """An unsolved network yields no `p`/`p_nom_opt` rows (the outputs default rule).

    Notes
    -----
    - [outputs](https://energy-models.github.io/datarecord/design/read-path/#outputs)
    """
    n = PyPSA.build(single_revision.record)
    results = PyPSA.results(n, single_revision.record.con)
    assert "p" not in results
    assert "p_nom_opt" not in results


def test_results_set_on_the_working_record_they_were_planned_on(
    single_revision, solved
):
    """Every result lands as an output on `w.con`, as the documented loop sets it.

    Notes
    -----
    - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
    - [outputs](https://energy-models.github.io/datarecord/design/read-path/#outputs)
    """
    from datarecord.mutable import WorkingRecord

    n = solved

    w = WorkingRecord(single_revision.record)
    results = PyPSA.results(n, w.con)
    undeclared = set(results) - set(w.schema.results)
    assert not undeclared, f"results the schema does not declare: {sorted(undeclared)}"
    for attr, frame in results.items():
        w.set(attr, frame, kind="outputs")

    assert not {"p0", "p1"} & set(results), "port flows land in `p`, not per port"
    p = _flat(w.outputs["p"])
    gens = list(n.c["Generator"].static.index)
    assert p["entity"].isin(gens).sum() == len(n.snapshots) * len(gens)
    assert p["bus"].notna().all(), "a staged `p` keeps the bus of its connection"


def test_a_solved_p_is_one_row_per_connection(single_revision, solved):
    """`p` holds a row per `(entity, bus)` per snapshot, each port's own sign.

    Notes
    -----
    - [results on connections](https://energy-models.github.io/datarecord/design/tools/#results-on-connections)
    """
    n = solved

    p = _flat(PyPSA.results(n, single_revision.record.con)["p"])
    connections = unpacked(single_revision.record.groups["connection"])
    per_connection = p.groupby(["entity", "bus"]).size()
    assert set(per_connection.index) == set(
        zip(connections["entity"], connections["bus"])
    ), "every connection carries `p`, and nothing else does"
    assert (per_connection == len(n.snapshots)).all(), "one row per snapshot"

    lines = n.c["Line"]
    line = lines.static.index[0]
    for port in ("0", "1"):
        bus = lines.static.at[line, f"bus{port}"]
        rows = p[(p["entity"] == line) & (p["bus"] == bus)].set_index("snapshot")
        expected = lines.dynamic[f"p{port}"][line]
        assert np.allclose(rows["value"].reindex(expected.index), expected), (
            f"`p{port}` lands on the line's bus{port} connection"
        )


def test_bus_power_is_not_a_result(single_revision, solved):
    """`Bus.p`/`q` sum the connections at a bus, so neither is written.

    Notes
    -----
    - [results on connections](https://energy-models.github.io/datarecord/design/tools/#results-on-connections)
    """
    n = solved

    p = _flat(PyPSA.results(n, single_revision.record.con)["p"])
    buses = list(n.c["Bus"].static.index)
    assert not p["entity"].isin(buses).any()
    assert not n.c["Bus"].dynamic["p"].empty, "PyPSA did compute a `Bus.p`"


def test_link_internal_power_is_p_internal(single_revision, solved):
    """`Link.p` is power at no bus: an entity-level `p_internal`, no `bus`.

    Notes
    -----
    - [results on connections](https://energy-models.github.io/datarecord/design/tools/#results-on-connections)
    """
    n = solved

    results = PyPSA.results(n, single_revision.record.con)
    internal = results["p_internal"].collect()
    links = list(n.c["Link"].static.index)
    assert "bus" not in internal.columns
    assert set(internal["entity"].to_list()) == set(links)
    assert len(internal) == len(n.snapshots) * len(links)
    assert "p_internal" in _registry_schema().results


def _three_port_link():
    import pypsa

    n = pypsa.Network()
    n.set_snapshots(pd.date_range("2020-01-01", periods=2, freq="h"))
    for bus in ("a", "b", "c"):
        n.add("Bus", bus)
    n.add("Link", "split", bus0="a", bus1="b", bus2="c")
    return n


def test_a_third_port_result_lands_on_its_connection(workspace):
    """`p2` is `p` on the bus2 connection, declared though the bare registry has no `p2`.

    Notes
    -----
    - [outputs](https://energy-models.github.io/datarecord/design/read-path/#outputs)
    - [results on connections](https://energy-models.github.io/datarecord/design/tools/#results-on-connections)
    """
    n = _three_port_link()
    n.c["Link"].dynamic["p2"] = pd.DataFrame({"split": [1.0, 2.0]}, index=n.snapshots)

    results = PyPSA.results(n, workspace.con)
    assert "p2" not in results
    assert "p" in _registry_schema().results, "the bare registry declares `p`"
    p = _flat(results["p"])
    assert p["bus"].to_list() == ["c", "c"], "a third port's flow is on bus2"
    assert p["value"].to_list() == [1.0, 2.0]
    inputs = PyPSA.to_datarecord(n, workspace.con).attributes
    assert "p" not in inputs, "p2 must not land in inputs"


def test_a_three_port_record_writes_p_on_each_connection(store):
    """Writing a three-port network puts every port's flow on its connection.

    Notes
    -----
    - [results on connections](https://energy-models.github.io/datarecord/design/tools/#results-on-connections)
    """
    n = _three_port_link()
    flows = {"p0": [3.0, 4.0], "p1": [-1.0, -2.0], "p2": [-1.5, -1.5]}
    for attr, values in flows.items():
        n.c["Link"].dynamic[attr] = pd.DataFrame({"split": values}, index=n.snapshots)

    revision = export_network(n, store)

    p = _flat(outputs(revision, "p")).sort_values(["bus", "snapshot"])
    assert p.groupby("bus")["value"].apply(list).to_dict() == {
        "a": flows["p0"],
        "b": flows["p1"],
        "c": flows["p2"],
    }


def test_a_stochastic_third_port_efficiency_survives_a_round_trip(store):
    """Per-scenario port values are placed by connection like any other.

    Notes
    -----
    - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
    """
    n = _three_port_link()
    n.set_scenarios({"low": 0.5, "high": 0.5})
    n.c["Link"].static["efficiency"] = 0.5
    n.c["Link"].static.loc[("low", "split"), "efficiency2"] = 0.2
    n.c["Link"].static.loc[("high", "split"), "efficiency2"] = 0.4

    built = PyPSA.build(export_network(n, store).record)

    static = built.c["Link"].static
    assert static[["efficiency", "efficiency2"]].to_dict("index") == {
        ("low", "split"): {"efficiency": 0.5, "efficiency2": 0.2},
        ("high", "split"): {"efficiency": 0.5, "efficiency2": 0.4},
    }, "each scenario's port values land in their own columns"


def _three_port_process():
    import pypsa

    n = pypsa.Network()
    n.set_snapshots(pd.date_range("2020-01-01", periods=2, freq="h"))
    for bus in ("a", "b", "c"):
        n.add("Bus", bus)
    n.add("Process", "dri", bus0="a", bus1="b", bus2="c")
    return n


def test_process_rate_is_one_attribute_on_its_connections(workspace):
    """`rate0`, `rate1`, `rate2` are one `rate`, a row per connection with its bus.

    Notes
    -----
    - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
    """
    n = _three_port_process()
    n.c["Process"].static.loc["dri", ["rate0", "rate1", "rate2"]] = [-2.0, 1.5, 0.3]

    inputs = PyPSA.to_datarecord(n, workspace.con).attributes
    assert not {"rate0", "rate1", "rate2"} & set(inputs), "no positional names"
    rate = _flat(inputs["rate"])
    assert rate.set_index("bus")["value"].to_dict() == {"a": -2.0, "b": 1.5, "c": 0.3}
    spec = _registry_schema().attributes["rate"]
    assert "connection" in spec.dims
    assert spec.default is None, "rate0 and rate1 default differently"


@pytest.mark.parametrize(
    ("network", "ctype", "name", "columns", "values"),
    [
        (
            _three_port_link,
            "Link",
            "split",
            ["efficiency", "efficiency2"],
            [0.5, 0.3],
        ),
        (
            _three_port_process,
            "Process",
            "dri",
            ["rate0", "rate1", "rate2"],
            [-2.0, 1.5, 0.3],
        ),
    ],
    ids=["link-efficiency", "process-rate"],
)
def test_per_port_values_survive_a_round_trip(
    store, network, ctype, name, columns, values
):
    """Each port's value comes back from its connection, not as PyPSA's default.

    Notes
    -----
    - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
    """
    n = network()
    n.c[ctype].static.loc[name, columns] = values

    built = PyPSA.build(export_network(n, store).record)

    assert built.c[ctype].static.loc[name, columns].tolist() == values, (
        "each port's value lands in its own column"
    )
    assert_networks_equal(built, n)


@pytest.mark.parametrize(
    ("network", "ctype", "name", "static", "series"),
    [
        (
            _three_port_link,
            "Link",
            "split",
            ("efficiency", 0.5),
            ("efficiency2", [0.2, 0.4]),
        ),
        (_three_port_process, "Process", "dri", ("rate0", -2.0), ("rate1", [0.8, 1.2])),
    ],
    ids=["link-efficiency", "process-rate"],
)
def test_a_time_varying_port_survives_a_round_trip(
    store, network, ctype, name, static, series
):
    """A series on one port is that port's series, beside another port's static value.

    Notes
    -----
    - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
    """
    (static_attr, static_value), (series_attr, values) = static, series
    n = network()
    n.c[ctype].static.loc[name, static_attr] = static_value
    n.c[ctype].dynamic[series_attr] = pd.DataFrame(
        {name: values}, index=n.snapshots
    ).rename_axis(columns="name")

    built = PyPSA.build(export_network(n, store).record)

    assert built.c[ctype].dynamic[static_attr].empty, "the static port stays static"
    assert built.c[ctype].static.at[name, static_attr] == static_value
    assert built.c[ctype].dynamic[series_attr][name].to_list() == values
    assert_networks_equal(built, n)


def test_per_type_defaults_round_trip_with_nothing_written(store):
    """A Load and a StorageUnit added without `sign` or `p_min_pu` build with their own defaults.

    A default PyPSA differs per type is declared through `default_by`.

    Notes
    -----
    - [AttributeSpec](https://energy-models.github.io/datarecord/design/schema/#attributespec)
    """
    import pypsa

    from datarecord.mutable import WorkingRecord

    sign = _registry_schema().property_spec("sign")
    assert sign is not None
    assert sign.default_by["entity_type"]["Load"] == -1.0, (
        "PyPSA declares a load's sign through `default_by`"
    )

    n = pypsa.Network()
    n.set_snapshots(pd.date_range("2030-01-01", periods=2, freq="h"))
    n.add("Bus", "b")
    root = export_network(n, store)

    staged = WorkingRecord(root.record)
    staged.add("entity", ["l1"], entity_type="Load")
    staged.add("entity", ["su1"], entity_type="StorageUnit")
    staged.add_group(
        "connection",
        pd.DataFrame(
            [
                {"connection": {"entity": e, "bus": "b"}, "role": "attached"}
                for e in ("l1", "su1")
            ]
        ),
    )
    child = root.child(staged.edits)

    inputs = Path(store.layer_dir(child.id)) / "inputs"
    written = {p.stem for p in inputs.glob("*.parquet")} if inputs.exists() else set()
    assert not {"sign", "p_min_pu"} & written, "a default is never stored"

    built = PyPSA.build(child.record)
    assert built.c["Load"].static.at["l1", "sign"] == -1, "a Load's own sign"
    assert built.c["StorageUnit"].static.at["su1", "sign"] == 1
    assert built.c["StorageUnit"].static.at["su1", "p_min_pu"] == -1, (
        "a StorageUnit's own p_min_pu"
    )


def test_delays_are_rows_keyed_by_their_connections(workspace, store):
    """A Process's `delay0`/`delay1` and a Link's `delay`/`delay2` are one `delay` per bus.

    A Link leaves `delay` unsuffixed at bus1, so no suffix marks it per-port.
    Never varying, it is still an attribute: long rows keyed by the connection,
    where `role` is the connection's one property.

    Notes
    -----
    - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
    """
    n = _three_port_process()
    n.c["Process"].static.loc["dri", ["delay0", "delay1"]] = [1, 2]
    n.c["Process"].static.loc["dri", "cyclic_delay1"] = True
    n.add("Link", "split", bus0="a", bus1="b", bus2="c", delay=3, delay2=4)

    record = PyPSA.to_datarecord(n, workspace.con)
    members = set(record.dims["entity"].collect_schema())
    assert not {"delay", "delay0", "delay2", "cyclic_delay1"} & members, (
        "no positional names on the members"
    )
    assert set(record.groups["connection"].collect_schema()) == {
        "connection",
        "role",
        "deleted",
    }, "a connection row carries its key, its property and its tombstone"
    rows = unpacked(record.attributes["delay"])
    delay = rows.set_index(["entity", "bus"])["value"].dropna().to_dict()
    assert delay == {
        ("dri", "a"): 1,
        ("dri", "b"): 2,
        ("dri", "c"): 0,
        ("split", "b"): 3,
        ("split", "c"): 4,
    }, "bus0 of a Link has no delay"
    assert _registry_schema().attributes["cyclic_delay"].dims == {"connection"}

    built = PyPSA.build(export_network(n, store).record)
    assert built.c["Link"].static.loc["split", ["delay", "delay2"]].tolist() == [3, 4]
    assert built.c["Process"].static.loc["dri", "cyclic_delay1"]
    assert_networks_equal(built, n)


def test_a_nan_in_a_series_survives_the_melt(workspace):
    """`UNPIVOT` drops nulls unless told otherwise; a NaN cell is still a row."""
    import numpy as np

    n = _three_port_link()
    n.c["Link"].dynamic["p_max_pu"] = pd.DataFrame(
        {"split": [1.0, np.nan]}, index=n.snapshots
    )

    rows = PyPSA.to_datarecord(n, workspace.con).attributes["p_max_pu"].collect()
    split = rows.filter(nw.col("entity") == "split")
    assert len(split) == 2, "one row per snapshot, NaN included"


def test_a_name_is_never_an_identifier_in_the_melt_or_pivot(store):
    """Each name is stored and comes back as its own series.

    `wind "north"` would end a quoted identifier, `snapshot` is the pivot's
    group-by column, and `Gen` and `gen` one case-insensitive identifier.

    Notes
    -----
    - [wide and long rows](https://energy-models.github.io/datarecord/design/record/#wide-and-long-rows)
    """
    import pypsa

    names = ['wind "north"', "snapshot", "Gen", "gen"]
    n = pypsa.Network()
    n.set_snapshots(pd.date_range("2030-01-01", periods=2, freq="h"))
    n.add("Bus", "north")
    n.add("Generator", names, bus="north")
    series = pd.DataFrame(
        {name: [0.1 * i, 0.1 * i + 0.05] for i, name in enumerate(names, 1)},
        index=n.snapshots,
    )
    n.c["Generator"].dynamic["p_max_pu"] = series

    revision = store.root(PyPSA.to_datarecord(n, store.workspace.con))
    rows = revision.record.attributes["p_max_pu"].collect()
    assert sorted(rows.select("entity", "value").rows()) == sorted(
        (name, value) for name in names for value in series[name]
    ), "the melt stores each name's own series"
    built = PyPSA.build(revision.record).c["Generator"].dynamic["p_max_pu"]
    pd.testing.assert_frame_equal(
        built[names],
        series,
        check_names=False,
        check_freq=False,
        check_column_type=False,
    )


def test_a_second_tool_needs_no_record_change():
    """A tool is a plain object taking a record; adding one changes nothing here.

    No registration and no name dispatch: conformance to `Tool` is structural,
    so a second framework's module defines its own singleton and callers import
    it.

    Notes
    -----
    - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
    """
    from datarecord.tools.base import Tool

    class FakeTool:
        name = "fake"
        schema = Schema()

        def requires(self, record):
            return Requirements(dims=frozenset({"snapshot"}))

        def verify(self, record):
            return Requirements(categories=frozenset({"Nope"}))

        def build(self, record):
            return "fake-model"

        def results(self, model, con):
            return {("Thing", "x"): model}

        def to_datarecord(self, model, con):
            return f"layer-of-{model}"

    assert isinstance(FakeTool(), Tool), "conformance to `Tool` is structural"


def test_schema_dims_stay_generic(exported):
    """`Coords` carries a dim PyPSA knows nothing about; axis names live in the tool.

    Declared but not `partial`, so the record's files need no column for it.
    Keying it would be a different matter, reported by the tool against the
    real record - see `test_verify_reports_a_snapshot_key`.
    """
    revision = exported
    _with_schema(revision, dims={**_DIMS, "vintage": nw.String()})
    dims = revision.resolver.dims
    assert "vintage" in dims.schema.dims
    # No axis rows anywhere, so the dim is absent from the mapping rather than
    # present-and-empty (https://energy-models.github.io/datarecord/design/record/#frames).
    assert "vintage" not in dims.axes
    # PyPSA's own required dims are still satisfied, and the extra dim is
    # simply not something the tool looks at.
    assert not PyPSA.verify(revision.record)
    assert "vintage" in dims.schema.long_columns


def test_a_null_scenario_weight_reaches_every_scenario_its_own_row_does_not():
    rows = pd.DataFrame({"scenario": [None, "high"], "value": [0.25, 0.5]})
    record = SimpleNamespace(
        attributes={"scenario_weight": nw.from_native(rows).lazy()}
    )
    shape = SimpleNamespace(
        scenarios=pd.DataFrame({"scenario": ["low", "mid", "high"]})
    )
    weights = _scenario_weights(record, shape)  # type: ignore[arg-type]
    assert weights.to_dict() == {"low": 0.25, "mid": 0.25, "high": 0.5}, (
        "a NULL-scenario row broadcasts; a scenario's own row wins"
    )
