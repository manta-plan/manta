# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""Overlay semantics over a parent/child pair.

Notes
-----
- [layered resolution](https://energy-models.github.io/datarecord/design/layers/)
- [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
"""

import narwhals as nw
import pandas as pd
import pytest

from datarecord.layered.resolve import (
    Resolver,
    read_schema,
    sources_to_read,
    write_schema,
)
from datarecord.layered.revision import ancestry
from datarecord.layered.sources import ParquetLayer
from datarecord.record import EMPTY
from datarecord.schema import AttributeSpec
from datarecord.tools.pypsa import PyPSA
from tests.fixtures import (
    empty_child,
    empty_root,
    export_network,
    outputs,
    relation,
    schema,
    write_entity_type,
    write_group,
    write_input,
)


def _entities(revision) -> set[str]:
    axis = revision.resolver.axis("entity")
    assert axis is not None, "every revision here has entities"
    return set(axis.df()["entity"])


@pytest.fixture
def parent(store):
    """A materialised root: two generators with a three-snapshot `p_max_pu`.

    `Norway Wind` also carries an `efficiency` on its connection, so a
    group-keyed attribute folds through the base too.
    """
    revision = empty_root(store)
    layer = store.layer_dir(revision.id)
    write_schema(schema(), store)
    names = ["Manchester Wind", "Norway Wind"]
    write_entity_type(layer, "Generator", [{"entity": n} for n in names])
    write_group(
        layer, "connection", [{"connection": {"entity": "Norway Wind", "bus": "NO"}}]
    )
    write_input(
        layer,
        "p_max_pu",
        [
            {"entity": n, "snapshot": f"2030-01-0{d}", "value": 0.1 * d}
            for n in names
            for d in (1, 2, 3)
        ],
    )
    write_input(
        layer, "efficiency", [{"entity": "Norway Wind", "bus": "NO", "value": 0.9}]
    )
    revision.materialise()
    return revision


@pytest.fixture
def network(store, ac_dc):
    revision = export_network(ac_dc, store)
    revision.materialise()
    return revision


def test_child_overwrites_component(store, parent):
    """A child's rows replace all of that component's rows for the attribute.

    Notes
    -----
    - [partial](https://energy-models.github.io/datarecord/design/schema/#partial-the-granularity-of-an-override)
    """
    child = empty_child(parent)
    write_input(
        store.layer_dir(child.id),
        "p_max_pu",
        [{"entity": "Manchester Wind", "value": 0.42}],
    )

    df = relation(child, "p_max_pu").df()
    manchester = df[df["entity"] == "Manchester Wind"]
    # The parent's 3 series rows are gone, replaced by the child's single row.
    assert len(manchester) == 1
    assert manchester["value"].iloc[0] == 0.42
    assert pd.isna(manchester["snapshot"].iloc[0])

    # Siblings on the same layer are untouched.
    assert len(df[df["entity"] == "Norway Wind"]) == 3


def test_child_overwrite_reaches_model(store, network):
    """The overwrite turns a series component into a static one in the model."""
    child = empty_child(network)
    write_input(
        store.layer_dir(child.id),
        "p_max_pu",
        [{"entity": "Manchester Wind", "value": 0.42}],
    )

    n = PyPSA.build(child.record)
    assert n.c["Generator"].static.loc["Manchester Wind", "p_max_pu"] == 0.42
    assert "Manchester Wind" not in n.c["Generator"].dynamic["p_max_pu"].columns
    assert "Norway Wind" in n.c["Generator"].dynamic["p_max_pu"].columns


def test_child_adds_attribute(store, network):
    """A child may write an attribute no ancestor had."""
    child = empty_child(network)
    write_input(
        store.layer_dir(child.id),
        "p_min_pu",
        [{"entity": "Norway Gas", "value": 0.1}],
    )

    n = PyPSA.build(child.record)
    assert n.c["Generator"].static.loc["Norway Gas", "p_min_pu"] == 0.1
    # Untouched generators keep the catalog default.
    assert n.c["Generator"].static.loc["Norway Wind", "p_min_pu"] == 0.0


def test_closed_child_reads_own_resolver(store, network):
    """Reading a closed non-root record uses its own persisted dims/manifest/map.

    Its `ancestry_since_closed` is just itself, so the raw layer (which has
    no `dims/` or `manifest.json` of its own here) cannot be the source.

    Notes
    -----
    - [materialised node caches](https://energy-models.github.io/datarecord/design/layers/#materialised-node-caches)
    """
    child = empty_child(network)
    write_input(
        store.layer_dir(child.id),
        "p_max_pu",
        [{"entity": "Manchester Wind", "value": 0.42}],
    )
    child.materialise()

    reloaded = store.revision(child.id)
    n = PyPSA.build(reloaded.record)
    assert n.c["Generator"].static.loc["Manchester Wind", "p_max_pu"] == 0.42

    df = relation(reloaded, "p_max_pu").df()
    assert df[df["entity"] == "Manchester Wind"]["value"].tolist() == [0.42]


def test_outputs_do_not_overlay(store, parent):
    """Results come from the node's own layer only.

    Notes
    -----
    - [outputs](https://energy-models.github.io/datarecord/design/read-path/#outputs)
    """
    child = empty_child(parent)
    assert outputs(child, "p").df().empty


def test_resolved_reads_same_as_unresolved(store, parent):
    """A materialised node reads identically to the same node folded from its layers.

    The invariant the base/source split protects: a materialised ancestor's
    resolved fold, read as the base, gives every reader the same answer as
    re-folding the whole ancestry from the root. Materialise a grandchild, then
    build one node cache the truncated way (base = the materialised parent) and
    one the long way (every layer as its own `ParquetLayer`, no truncation), and
    assert they agree on the owner map, the entity axis, every attribute
    relation, and the group frames.
    """
    child = empty_child(parent)
    write_input(
        store.layer_dir(child.id),
        "p_max_pu",
        [{"entity": "Manchester Wind", "value": 0.42}],
    )
    child.materialise()

    grandchild = empty_child(child)
    write_input(
        store.layer_dir(grandchild.id),
        "p_max_pu",
        [{"entity": "Manchester Wind", "value": 0.99}],
    )

    # `unresolved` folds the whole ancestry from the root: every layer read from
    # its own directory, no base short-circuit, even though the ancestors are
    # materialised. `_Unmaterialised` forces `materialised()` to `None` so the
    # fold cannot take a base and must re-derive what the base would carry.
    class _Unmaterialised(ParquetLayer):
        def materialised(self, con, schema):  # noqa: ARG002
            return None

    schema = read_schema(store)
    full = ancestry(store, grandchild.id)
    workspace = store.workspace
    truncated = Resolver(
        grandchild.id, sources_to_read(full, store, schema), workspace, schema
    )
    unresolved = Resolver(
        grandchild.id,
        [_Unmaterialised(uid, schema, store) for uid in full],
        workspace,
        schema,
    )

    def ownership(nc):
        return sorted(
            nc.inputs.project("attribute, entity, layer_uuid").fetchall(),
            key=str,
        )

    assert ownership(truncated) == ownership(unresolved), (
        "the owner map folded through the base matches folding from the root"
    )

    t_axis, u_axis = truncated.axis("entity"), unresolved.axis("entity")
    assert t_axis is not None and u_axis is not None
    assert set(t_axis.df()["entity"]) == set(u_axis.df()["entity"]), (
        "the resolved entity axis is the same either way"
    )

    for attr in truncated.attributes():
        a = sorted(truncated.attribute(attr).fetchall(), key=str)
        b = sorted(unresolved.attribute(attr).fetchall(), key=str)
        assert a == b, f"{attr} resolves the same through the base as from the root"

    manchester = truncated.attribute("p_max_pu").df()
    assert manchester[manchester["entity"] == "Manchester Wind"]["value"].tolist() == [
        0.99
    ], "grandchild's value wins over the materialised base"
    assert len(manchester[manchester["entity"] == "Norway Wind"]) == 3, (
        "an untouched sibling keeps the root's series through the ancestry"
    )


def test_a_new_attribute_is_a_schema_amendment(store, network):
    """Adding an attribute amends the record's one schema, not a layer's.

    A schema is not layered data: folding it would let a layer redefine what
    an attribute means, and make the schema unknowable without walking the
    ancestry. So the amendment lands beside the layers, and every layer in the
    tree - including ones already written - is read under it.

    Notes
    -----
    - [one schema per record](https://energy-models.github.io/datarecord/design/schema/#one-schema-per-record)
    """
    amended = read_schema(store)
    # Declared once, record-wide, then narrowed to the type that carries it -
    # the two halves an amendment now has.
    amended.attributes["p_min_pu"] = AttributeSpec(
        dtype=nw.Float64(), dims={"entity", "snapshot"}, default=0.25
    )
    was = amended.traits["Generator"]
    amended.traits["Generator"] = was.model_copy(
        update={"attributes": was.attributes | {"p_min_pu"}}
    )
    write_schema(amended, store)

    # Adding an attribute is compatible, so the layers written before the
    # amendment stay readable (https://energy-models.github.io/datarecord/design/schema/#versioning).
    assert amended.compatible_with(read_schema(store)) == []

    child = empty_child(network)
    write_input(
        store.layer_dir(child.id),
        "p_min_pu",
        [{"entity": "Norway Gas", "value": 0.1}],
    )
    n = PyPSA.build(child.record)
    assert n.c["Generator"].static.loc["Norway Gas", "p_min_pu"] == 0.1
    # And the amendment is visible from the record, not just from the layer
    # that happens to carry a row for it.
    assert "p_min_pu" in child.record.schema.attributes_for(
        "entity", entity_type="Generator"
    )


def test_a_schema_narrowing_is_refused(store, parent):
    """A layer cannot redefine what an attribute means.

    Notes
    -----
    - [one schema per record](https://energy-models.github.io/datarecord/design/schema/#one-schema-per-record)
    - [versioning](https://energy-models.github.io/datarecord/design/schema/#versioning)
    """
    narrowed = read_schema(store)
    narrowed.attributes["p_max_pu"] = AttributeSpec(
        dtype=nw.Float64(), dims=frozenset()
    )

    class _Narrowed:
        """The record's own source, with one attribute's dims taken away."""

        schema = narrowed
        dims = EMPTY
        groups: dict = {}
        attributes = EMPTY
        outputs = EMPTY

        def flags(self):
            return {}

    before = read_schema(store)
    with pytest.raises(ValueError, match="no longer varies over"):
        parent.child(_Narrowed())
    assert read_schema(store) == before, "the manifest is never narrowed"
    assert [r.id for r in store.revisions()] == [parent.id], (
        "the layer was written, but without its revision file nothing reaches it"
    )
