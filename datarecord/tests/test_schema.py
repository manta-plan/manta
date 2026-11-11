# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""The typed schema: declarations, derived keys, validation, versioning.

Notes
-----
- [the schema](https://energy-models.github.io/datarecord/design/schema/)
"""

from typing import Any

import duckdb
import narwhals as nw
import pytest
from pydantic import ValidationError

from datarecord.duck import DuckTypes
from datarecord.schema import (
    AttributeSpec,
    Dimension,
    Group,
    PropertySpec,
    Schema,
    Trait,
    flag_type,
)


def _schema(**overrides) -> Schema:
    """A schema shaped like a stochastic multi-period record."""
    kwargs: dict[str, Any] = {
        "dimensions": {
            "entity": Dimension(dtype=nw.String()),
            "bus": Dimension(dtype=nw.String()),
            "period": Dimension(dtype=nw.Int64()),
            "timestep": Dimension(dtype=nw.Datetime(), within={"period"}),
            "scenario": Dimension(dtype=nw.String()),
        },
        "properties": {
            "entity": {
                "entity_type": PropertySpec(dtype=nw.Enum(["Generator", "Link"]))
            }
        },
        "groups": {"connection": Group(over={"entity": "entity", "bus": "bus"})},
        # Declared once, record-wide; a trait narrows one to some types.
        "attributes": {
            "p_nom": AttributeSpec(dtype=nw.Float64(), dims={"entity"}),
            "p_max_pu": AttributeSpec(
                dtype=nw.Float64(), dims={"entity", "scenario", "timestep"}
            ),
            "marginal_cost": AttributeSpec(
                dtype=nw.Float64(), dims={"entity", "scenario"}, breakpoints=True
            ),
            "carrier": AttributeSpec(dtype=nw.String(), dims={"entity"}),
            # A connection attribute says so by naming the group among its
            # dims, rather than by a field of its own.
            "efficiency": AttributeSpec(
                dtype=nw.Float64(), dims={"connection", "scenario", "timestep"}
            ),
        },
        "traits": {
            "dispatchable": Trait(
                attributes={"p_nom", "p_max_pu", "marginal_cost", "carrier"},
                on={"entity_type": frozenset({"Generator"})},
            ),
            "converting": Trait(
                attributes={"efficiency"},
                on={"entity_type": frozenset({"Link"})},
            ),
        },
        "partial": frozenset({"entity", "scenario"}),
    }
    kwargs.update(overrides)
    return Schema(**kwargs)


# -- derived keys (https://energy-models.github.io/datarecord/design/schema/#partial-the-granularity-of-an-override) -----------------------------------------------------


def test_ownership_is_derived_not_declared():
    """`owned_per` is `dims` and `partial` together, never a third declaration."""
    s = _schema()
    # Varies over both time axes, but only `scenario` is partial among them -
    # so a patch to one timestep restates that scenario's whole series.
    # `entity` joins it because a layer patches one component's value.
    assert s.owned_per("p_max_pu") == frozenset({"entity", "scenario"})
    assert s.owned_per("marginal_cost") == frozenset({"entity", "scenario"})
    # A first-stage decision: one value per component, owned once across
    # every axis it does not vary over.
    assert s.owned_per("p_nom") == frozenset({"entity"})
    assert s.owned_per("carrier") == frozenset({"entity"})


def test_partial_dims_is_the_union_over_attributes():
    """The fold's key is one fixed tuple, so an unowned dim is NULL rather than absent."""
    s = _schema()
    assert s.partial_dims == ("entity", "scenario"), "only what `partial` lists"

    wider = _schema(partial=frozenset({"entity", "scenario", "timestep", "connection"}))
    assert wider.partial_dims == ("entity", "timestep", "scenario", "connection"), (
        "a `partial` dim or group joins the key"
    )

    dims = {
        "entity": Dimension(dtype=nw.String()),
        "scenario": Dimension(dtype=nw.String()),
    }
    unlisted = Schema(dimensions=dims, partial=frozenset({"scenario"}))
    assert unlisted.partial_dims == ("scenario",), (
        "no dim is keyed by name: `entity` is owned whole where not partial"
    )


# -- entity types and traits (https://energy-models.github.io/datarecord/design/schema/#traits) ------------------------------------


def test_an_untraited_attribute_is_carried_by_every_type():
    """A trait narrows; declaring `entity` in `dims` is what grants.

    `sign` is bundled by no trait, so every type addressed by `entity` carries
    it - the same thing `dims={"scenario"}` means along the scenario axis.
    Where `p_max_pu`, which `dispatchable` bundles, reaches Generator alone.
    """
    s = _schema(
        attributes={
            **_schema().attributes,
            "sign": AttributeSpec(dtype=nw.Float64(), dims={"entity"}),
        }
    )
    assert "p_max_pu" not in s.attributes_for("entity", entity_type="Link"), (
        "narrowed to Generator"
    )
    assert "sign" in s.attributes_for("entity", entity_type="Link"), (
        "untraited, so carried by all"
    )
    assert "sign" in s.attributes_for("entity", entity_type="Generator")


def test_an_attribute_addressing_no_entity_reaches_no_type():
    """A record-level attribute belongs to the record, however few traits name it.

    Default-open is scoped by addressing rather than by trait membership: with
    no `entity` among its coordinates there is no component for it to reach,
    so `names=None` targets nothing rather than every component in the record.
    """
    s = _schema(
        attributes={
            **_schema().attributes,
            "weighting": AttributeSpec(dtype=nw.Float64(), dims={"timestep"}),
        }
    )
    assert not s.addresses("weighting", "entity")
    assert "weighting" not in s.attributes_for("entity", entity_type="Generator")


def test_a_group_addressed_attribute_reaches_the_types_it_coordinates():
    """`efficiency` is over `connection`, whose coordinates include `entity`."""
    s = _schema()
    assert s.addresses("efficiency", "entity")
    assert "efficiency" in s.attributes_for("entity", entity_type="Link")


def _with_entity_property(name: str, spec: PropertySpec) -> dict:
    """`_schema`'s properties with `name` added to `entity`'s."""
    return {"entity": {**_schema().properties["entity"], name: spec}}


@pytest.mark.parametrize(
    ("build", "match"),
    [
        pytest.param(
            lambda: Schema(
                dimensions={
                    "entity": Dimension(dtype=nw.String()),
                    "bus": Dimension(dtype=nw.String()),
                    "country": Dimension(dtype=nw.String()),
                },
                groups={"bus_country": Group(over=["bus"], into="country")},
                attributes={
                    "p_nom": AttributeSpec(dtype=nw.Float64(), dims={"entity"})
                },
                traits={"t": Trait(attributes={"p_nom"}, on={"country": {"DE"}})},
                partial=frozenset(),
            ),
            "which is no property",
            id="a-dim",
        ),
        pytest.param(
            lambda: _schema(
                properties=_with_entity_property(
                    "kind", PropertySpec(dtype=nw.String())
                ),
                traits={"t": Trait(attributes={"p_nom"}, on={"kind": {"wind"}})},
            ),
            "is no `Enum` property",
            id="a-string-property",
        ),
        pytest.param(
            lambda: _schema(
                properties={
                    **_schema().properties,
                    "period": {"era": PropertySpec(dtype=nw.Enum(["old", "new"]))},
                },
                traits={"t": Trait(attributes={"p_nom"}, on={"era": {"old"}})},
            ),
            "`partial` does not list",
            id="a-property-of-a-non-partial-dim",
        ),
        pytest.param(
            lambda: _schema(
                properties={
                    **_schema().properties,
                    "connection": {"role": PropertySpec(dtype=nw.Enum(["in", "out"]))},
                },
                partial=frozenset({"entity", "scenario", "connection"}),
                traits={"t": Trait(attributes={"p_nom"}, on={"role": {"in"}})},
            ),
            "a group is never categorized",
            id="a-group-property",
        ),
        pytest.param(
            lambda: _schema(
                traits={"t": Trait(attributes={"p_nom"}, on={"entity_type": {"Store"}})}
            ),
            "not categories of 'entity_type'",
            id="an-unknown-category",
        ),
        pytest.param(
            lambda: _two_subjects(
                traits={
                    "both": Trait(
                        attributes={"efficiency"},
                        on={"entity_type": {"Link"}, "bus_type": {"DC"}},
                    )
                }
            ),
            "a trait is `on` one",
            id="two-properties",
        ),
        pytest.param(
            lambda: Schema(
                dimensions={"entity": Dimension(dtype=nw.String())},
                attributes={
                    "committable": AttributeSpec(
                        dtype=nw.Boolean(), dims={"entity"}, default=False
                    ),
                },
                traits={"committable": Trait(switch="committable")},
                partial=frozenset({"entity"}),
            ),
            "`on` no category",
            id="a-switch-with-no-on",
        ),
        pytest.param(
            lambda: _schema(
                traits={
                    "g": Trait(
                        attributes={"entity_type"}, on={"entity_type": {"Generator"}}
                    )
                }
            ),
            "circular",
            id="bundling-its-own-categorizing-property",
        ),
    ],
)
def test_a_trait_is_on_categories_of_one_categorizing_property(build, match):
    """A trait keys on the `Enum` property of a `partial` dim that classifies a label."""
    with pytest.raises(ValidationError, match=match):
        build()


def test_a_trait_switch_is_folded_into_attributes():
    """`switch` need not be named twice in `attributes`."""
    t = Trait(attributes={"start_up_cost"}, switch="committable")
    assert t.attributes == {"start_up_cost", "committable"}


def test_a_trait_switch_narrows_neither_attributes_for_nor_the_switch_itself():
    """`switch` is a validation and query mechanism, not a change to `attributes_for`.

    The schema-level answer stays type-scoped: `committable` the attribute is
    carried by every type `committable` the trait is `on`, whatever any
    component's switch value - and it is not narrowed by its own trait.
    """
    s = _schema(
        attributes={
            **_schema().attributes,
            "start_up_cost": AttributeSpec(dtype=nw.Float64(), dims={"entity"}),
            "committable": AttributeSpec(
                dtype=nw.Boolean(), dims={"entity"}, default=False
            ),
        },
        traits={
            **_schema().traits,
            "committable": Trait(
                attributes={"start_up_cost"},
                on={"entity_type": frozenset({"Generator"})},
                switch="committable",
            ),
        },
    )
    assert "start_up_cost" in s.attributes_for("entity", entity_type="Generator")
    assert "committable" in s.attributes_for("entity", entity_type="Generator")
    assert "start_up_cost" not in s.attributes_for("entity", entity_type="Link")


def test_a_trait_switch_must_be_addressed_by_its_categorized_dim_alone():
    """A switch narrower or wider than `entity` alone has no per-component reading."""
    with pytest.raises(ValidationError, match="addressed by that dim alone"):
        _schema(
            attributes={
                **_schema().attributes,
                "committable": AttributeSpec(
                    dtype=nw.Boolean(), dims={"entity", "scenario"}, default=False
                ),
            },
            traits={
                **_schema().traits,
                "committable": Trait(
                    on={"entity_type": frozenset({"Generator"})},
                    switch="committable",
                ),
            },
        )


def test_a_functional_group_may_not_key_an_attribute_with_what_it_maps_from():
    """`into` says the label follows from the key, so the row is keyed twice."""
    with pytest.raises(ValidationError, match="keys a row twice over"):
        Schema(
            dimensions={
                "bus": Dimension(dtype=nw.String()),
                "country": Dimension(dtype=nw.String()),
            },
            groups={"in_country": Group(over=["bus"], into="country")},
            attributes={
                "x": AttributeSpec(dtype=nw.Float64(), dims={"bus", "country"})
            },
            partial=frozenset(),
        )


def test_the_section_decides_where_a_value_lives():
    """An attribute is long rows whatever its `dims`; a property is a column of its subject's axis.

    Notes
    -----
    - [AttributeSpec](https://energy-models.github.io/datarecord/design/schema/#attributespec)
    """
    s = _schema()
    assert s.long_columns_for("p_nom") == ("entity", "attribute", "breakpoint", "value")
    assert s.column_type("p_nom") is None, "a single-dim attribute is no axis column"
    assert s.column_type("entity_type") == nw.Enum(["Generator", "Link"])
    assert s.subject_of("entity_type") == "entity"
    assert s.subject_of("p_nom") is None, "an attribute has no subject"
    assert s.property_spec("entity_type") == s.properties["entity"]["entity_type"]
    assert s.categorizing("entity") == ("entity_type",)
    assert "entity_type" not in s.long_columns
    assert "entity_type" not in s.broadcast_dims
    assert "entity_type" not in s.partial_dims


def test_a_group_may_have_properties():
    """A column of `groups/<group>.parquet`, typed like a dim's property."""
    s = _schema(
        properties={
            "entity": {
                "entity_type": PropertySpec(dtype=nw.Enum(["Generator", "Link"]))
            },
            "connection": {"role": PropertySpec(dtype=nw.Enum(["in", "out"]))},
        },
        partial=frozenset({"entity", "scenario", "connection"}),
    )
    assert s.subject_of("role") == "connection"
    assert s.column_type("role") == nw.Enum(["in", "out"])
    assert s.properties_for("connection") == {
        "role": s.properties["connection"]["role"]
    }
    assert s.categorizing("connection") == (), (
        "a group is never categorized, even by an `Enum` property of a `partial` group"
    )


def test_properties_are_narrowed_by_the_traits_attributes_are():
    """A trait `on` a category may bundle properties of its dim beside attributes."""
    s = _schema(
        properties={
            "entity": {
                "entity_type": PropertySpec(dtype=nw.Enum(["Generator", "Link"])),
                "sign": PropertySpec(dtype=nw.Float64()),
            }
        },
        traits={
            "generating": Trait(
                attributes={"sign", "p_nom"},
                on={"entity_type": frozenset({"Generator"})},
            )
        },
    )
    assert set(s.properties_for("entity", entity_type="Generator")) == {
        "entity_type",
        "sign",
    }
    assert set(s.properties_for("entity", entity_type="Link")) == {"entity_type"}
    assert "p_nom" not in s.attributes_for("entity", entity_type="Link")
    assert "sign" not in s.attributes_for("entity", entity_type="Generator"), (
        "attributes_for answers attributes only"
    )


def test_an_enum_property_categorizes_only_a_partial_dim():
    """No flag: the dtype and `partial` decide, a `String` property never."""
    s = _schema(
        properties={
            "entity": {
                **_schema().properties["entity"],
                "carrier_kind": PropertySpec(dtype=nw.Enum(["wind", "solar"])),
                "label": PropertySpec(dtype=nw.String()),
            },
            "period": {"era": PropertySpec(dtype=nw.Enum(["old", "new"]))},
        }
    )
    assert s.categorizing("entity") == ("entity_type", "carrier_kind"), (
        "every `Enum` property, in declaration order"
    )
    assert s.categorizing("period") == (), "`period` is not partial"
    assert s.categorizing("scenario") == (), "no properties"


@pytest.mark.parametrize(
    ("build", "match"),
    [
        pytest.param(
            lambda: _schema(
                properties={
                    **_schema().properties,
                    "bus": {"carrier": PropertySpec(dtype=nw.String())},
                }
            ),
            "one name is one spec",
            id="an-attributes-name",
        ),
        pytest.param(
            lambda: _schema(
                properties=_with_entity_property("bus", PropertySpec(dtype=nw.String()))
            ),
            "shares its name with the dim 'bus'",
            id="a-dims-name",
        ),
        pytest.param(
            lambda: _schema(
                properties=_with_entity_property(
                    "connection", PropertySpec(dtype=nw.String())
                )
            ),
            "with the group 'connection'",
            id="a-groups-name",
        ),
        pytest.param(
            lambda: Schema(
                dimensions={"bus": Dimension(dtype=nw.String())},
                groups={"corridor": Group(over={"from": "bus", "to": "bus"})},
                properties={"corridor": {"from": PropertySpec(dtype=nw.String())}},
            ),
            "share their names with its coordinates",
            id="a-group-coordinates-name",
        ),
        pytest.param(
            lambda: _schema(
                properties={"nope": {"kind": PropertySpec(dtype=nw.String())}}
            ),
            "undeclared dims or groups",
            id="on-an-undeclared-dim",
        ),
        pytest.param(
            lambda: _schema(
                properties={
                    **_schema().properties,
                    "bus": {"x": PropertySpec(dtype=nw.Float64())},
                },
                traits={"t": Trait(attributes={"x"}, on={"entity_type": {"Link"}})},
            ),
            "bundles undeclared attributes",
            id="bundled-by-another-subjects-trait",
        ),
    ],
)
def test_a_property_is_one_column_of_a_declared_subject(build, match):
    """A property's column may collide with no other name, and lives on its own subject."""
    with pytest.raises(ValidationError, match=match):
        build()


def test_a_record_may_declare_no_category_at_all():
    """Categories are optional: with none nothing narrows an attribute of a dim.

    A tool needing them requires the property in the schema it builds, which
    is where that requirement belongs.
    """
    s = Schema(
        dimensions={
            "entity": Dimension(dtype=nw.String()),
            "timestep": Dimension(dtype=nw.Datetime()),
        },
        attributes={
            "p_nom": AttributeSpec(dtype=nw.Float64(), dims={"entity"}),
            "weighting": AttributeSpec(dtype=nw.Float64(), dims={"timestep"}),
        },
        partial=frozenset(),
    )
    assert s.categorizing("entity") == (), "no vocabulary declared"
    assert sorted(s.attributes_for("entity")) == ["p_nom"], "nothing narrows"
    assert sorted(s.attributes_for("timestep")) == ["weighting"]
    with pytest.raises(ValueError, match="do not categorize 'entity'"):
        s.attributes_for("entity", entity_type="Generator")


# -- defaults by label -------------------------------------------------------


def test_default_for_reads_a_labels_default_over_the_plain_one():
    s = _schema(
        attributes={
            **_schema().attributes,
            "sign": AttributeSpec(
                dtype=nw.Float64(),
                dims={"entity"},
                default=1.0,
                default_by={"entity_type": {"Link": -1.0}},
            ),
        }
    )
    assert s.default_for("sign", entity_type="Link") == -1.0
    assert s.default_for("sign", entity_type="Generator") == 1.0, (
        "no entry, so the plain default"
    )
    assert s.default_for("sign") == 1.0
    assert s.default_for("entity_type") is None, "a property has one too"
    with pytest.raises(KeyError):
        s.default_for("nope")

    plain = _schema(
        properties={
            "entity": {
                "entity_type": PropertySpec(
                    dtype=nw.Enum(["Generator", "Link"]), default="Generator"
                )
            }
        }
    )
    assert plain.default_for("entity_type") == "Generator", (
        "a categorizing property may have a plain default"
    )


def _with_x(spec: AttributeSpec, base=_schema) -> Schema:
    """`base()` with `spec` declared as attribute `x`."""
    return base(attributes={**base().attributes, "x": spec})


@pytest.mark.parametrize(
    ("build", "match"),
    [
        pytest.param(
            lambda: _with_x(
                AttributeSpec(
                    dtype=nw.Float64(),
                    dims={"entity"},
                    default_by={"kind": {"Link": 1.0}},
                )
            ),
            "which is no property",
            id="no-property",
        ),
        pytest.param(
            lambda: _with_x(
                AttributeSpec(
                    dtype=nw.Float64(),
                    dims={"entity"},
                    default_by={"entity_type": {"Store": 1.0}},
                )
            ),
            "not categories of 'entity_type'",
            id="an-unknown-category",
        ),
        pytest.param(
            lambda: _with_x(
                AttributeSpec(
                    dtype=nw.Float64(),
                    dims={"timestep"},
                    default_by={"entity_type": {"Link": 1.0}},
                )
            ),
            "does not reach its dim 'entity'",
            id="a-dim-out-of-reach",
        ),
        pytest.param(
            lambda: _with_x(
                AttributeSpec(
                    dtype=nw.Float64(),
                    dims={"entity"},
                    default_by={"entity_type": {"Link": 0.5}, "bus_type": {"DC": 0.0}},
                ),
                base=_two_subjects,
            ),
            "does not reach its dim 'bus'",
            id="every-key-reaches-its-dim",
        ),
        pytest.param(
            lambda: _schema(
                properties={
                    "entity": {
                        "entity_type": PropertySpec(
                            dtype=nw.Enum(["Generator", "Link"]),
                            default="Generator",
                            default_by={"entity_type": {"Link": "Generator"}},
                        )
                    }
                }
            ),
            "circular",
            id="a-categorizing-property-by-a-category",
        ),
    ],
)
def test_default_by_is_validated_against_the_categories(build, match):
    with pytest.raises(ValidationError, match=match):
        build()


def _two_subjects(**overrides) -> Schema:
    """`_schema` with `bus` categorized by `bus_type` beside `entity_type`."""
    kwargs: dict[str, Any] = {
        "properties": {
            **_schema().properties,
            "bus": {"bus_type": PropertySpec(dtype=nw.Enum(["AC", "DC"]))},
        },
        "attributes": {
            **_schema().attributes,
            "v_nom": AttributeSpec(dtype=nw.Float64(), dims={"bus"}),
            "frequency": AttributeSpec(dtype=nw.Float64(), dims={"bus"}),
        },
        "traits": {
            **_schema().traits,
            "alternating": Trait(
                attributes={"frequency"}, on={"bus_type": frozenset({"AC"})}
            ),
        },
        "partial": frozenset({"entity", "bus", "scenario"}),
    }
    kwargs.update(overrides)
    return _schema(**kwargs)


def test_a_category_on_bus_works_like_one_on_entity():
    """A trait `on` and a `default_by` keyed by `bus_type` narrow bus attributes alone."""
    s = _two_subjects(
        attributes={
            **_two_subjects().attributes,
            "frequency": AttributeSpec(
                dtype=nw.Float64(),
                dims={"bus"},
                default=0.0,
                default_by={"bus_type": {"AC": 50.0}},
            ),
        }
    )
    assert s.default_for("frequency", bus_type="AC") == 50.0
    assert s.default_for("frequency", bus_type="DC") == 0.0
    assert s.categorizing("bus") == ("bus_type",)
    assert s.categorizing("entity") == ("entity_type",)
    assert sorted(s.attributes_for("bus", bus_type="AC")) == [
        "efficiency",
        "frequency",
        "v_nom",
    ], "`efficiency` reaches buses through `connection`, untraited on `bus_type`"
    assert sorted(s.attributes_for("bus", bus_type="DC")) == ["efficiency", "v_nom"], (
        "AC alone has frequency"
    )
    assert "frequency" not in s.attributes_for("entity", entity_type="Generator"), (
        "a bus attribute reaches no entity"
    )
    assert "p_nom" in s.attributes_for("entity", entity_type="Generator")
    assert s.attributes_for("bus", bus_type="Generator") == {}, "not a bus_type"


def test_categorizing_properties_of_one_dim_combine_as_a_union():
    """Traits on `entity_type` and on `carrier_kind` claiming one attribute give it to both."""
    s = _schema(
        properties={
            "entity": {
                **_schema().properties["entity"],
                "carrier_kind": PropertySpec(dtype=nw.Enum(["wind", "solar"])),
            }
        },
        traits={
            "generating": Trait(
                attributes={"p_max_pu"}, on={"entity_type": frozenset({"Generator"})}
            ),
            "windy": Trait(
                attributes={"p_max_pu"}, on={"carrier_kind": frozenset({"wind"})}
            ),
        },
    )
    assert "p_max_pu" in s.attributes_for("entity", entity_type="Generator")
    assert "p_max_pu" in s.attributes_for(
        "entity", entity_type="Link", carrier_kind="wind"
    ), "a wind link matches the `carrier_kind` trait"
    assert "p_max_pu" not in s.attributes_for(
        "entity", entity_type="Link", carrier_kind="solar"
    ), "neither trait matches a solar link"
    assert "p_max_pu" not in s.attributes_for("entity"), "no category matches no trait"
    assert "p_nom" in s.attributes_for("entity"), "untraited, so carried by every label"


def test_default_by_takes_the_first_key_listing_a_category():
    """Several keys may default one value; declaration order decides between them."""
    loss = AttributeSpec(
        dtype=nw.Float64(),
        dims={"connection"},
        default=1.0,
        default_by={"bus_type": {"DC": 0.0}, "entity_type": {"Link": 0.5}},
    )
    s = _two_subjects(attributes={**_two_subjects().attributes, "loss": loss})
    assert s.default_for("loss", bus_type="DC", entity_type="Link") == 0.0, (
        "`bus_type` is declared first"
    )
    assert s.default_for("loss", bus_type="AC", entity_type="Link") == 0.5, (
        "`bus_type` lists no AC, so `entity_type` decides"
    )
    assert s.default_for("loss", bus_type="AC", entity_type="Generator") == 1.0
    back = Schema.model_validate_json(s.model_dump_json())
    assert list(back.attributes["loss"].default_by) == ["bus_type", "entity_type"], (
        "the order survives `manifest.json`"
    )


# -- nesting (https://energy-models.github.io/datarecord/design/schema/#within-an-axis-inside-an-axis) ----------------------------------------------------------


@pytest.mark.parametrize(
    ("dimensions", "dim", "key"),
    [
        pytest.param(
            _schema().dimensions, "timestep", ("period", "timestep"), id="nested"
        ),
        pytest.param(_schema().dimensions, "period", ("period",), id="a-parent"),
        pytest.param(_schema().dimensions, "scenario", ("scenario",), id="unnested"),
        pytest.param(
            {
                "horizon": Dimension(dtype=nw.Int64()),
                "period": Dimension(dtype=nw.Int64(), within={"horizon"}),
                "timestep": Dimension(dtype=nw.Datetime(), within={"period"}),
            },
            "timestep",
            ("horizon", "period", "timestep"),
            id="transitive",
        ),
        pytest.param(
            {
                "period": Dimension(dtype=nw.Int64()),
                "stage": Dimension(dtype=nw.String()),
                "timestep": Dimension(dtype=nw.Datetime(), within={"period", "stage"}),
            },
            "timestep",
            ("period", "stage", "timestep"),
            id="several-direct-parents",
        ),
    ],
)
def test_axis_key_is_parents_then_dim(dimensions, dim, key):
    """A nested axis's labels identify only within its parents.

    Naming a parent pulls in that parent's own parents, and `within` is a set,
    since two axes may each qualify a label without containing each other.

    Notes
    -----
    - [within](https://energy-models.github.io/datarecord/design/schema/#within-an-axis-inside-an-axis)
    """
    assert Schema(dimensions=dimensions).axis_key(dim) == key


@pytest.mark.parametrize(
    ("build", "match"),
    [
        pytest.param(
            lambda: Schema(
                dimensions={"timestep": Dimension(dtype=nw.Datetime(), within={"nope"})}
            ),
            "undeclared",
            id="nesting-names-an-undeclared-dim",
        ),
        pytest.param(
            lambda: Schema(
                dimensions={
                    "a": Dimension(dtype=nw.Int64(), within={"b"}),
                    "b": Dimension(dtype=nw.Int64(), within={"a"}),
                }
            ),
            "cyclic",
            id="cyclic-nesting",
        ),
        pytest.param(
            lambda: Schema(dimensions={"a": Dimension(dtype=nw.Int64(), within={"a"})}),
            "within` itself",
            id="within-itself",
        ),
        pytest.param(
            lambda: Schema(
                dimensions={"scenario": Dimension(dtype=nw.String())},
                attributes={"p": AttributeSpec(dtype=nw.Float64(), dims={"nope"})},
            ),
            "undeclared",
            id="an-attribute-over-an-undeclared-dim",
        ),
    ],
)
def test_a_dim_reference_must_resolve(build, match):
    """`within` and an attribute's `dims` name declared dims, nesting acyclically."""
    with pytest.raises(ValidationError, match=match):
        build()


# -- defaults through the manifest (https://energy-models.github.io/datarecord/design/schema/#attributespec, https://energy-models.github.io/datarecord/design/schema/#one-schema-per-record) ------------------------------


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), 0.0, None, "AC"])
def test_a_default_survives_the_manifest_round_trip(value):
    """An `inf` default must read back as `inf`, not as "no default".

    JSON has no literal for a non-finite float, and pydantic's own serialiser
    emits `null` for one - which would silently turn an unbounded capacity into
    an absent bound. PyPSA declares `inf` defaults (`p_nom_max`), so this is the
    ordinary case rather than an edge one, and it is only the encoding in
    `AttributeSpec` that keeps it.

    Notes
    -----
    - [AttributeSpec](https://energy-models.github.io/datarecord/design/schema/#attributespec)
    """
    schema = Schema(
        dimensions={"scenario": Dimension(dtype=nw.String())},
        attributes={"p_nom_max": AttributeSpec(dtype=nw.Float64(), default=value)},
    )
    back = Schema.model_validate_json(schema.model_dump_json())
    assert repr(back.attributes["p_nom_max"].default) == repr(value)


# -- versioning (https://energy-models.github.io/datarecord/design/schema/#versioning) -------------------------------------------------------


def _restating(**attributes: AttributeSpec) -> Schema:
    """`_schema` with `attributes` added or replaced, every other one unchanged."""
    return _schema(attributes={**_schema().attributes, **attributes})


@pytest.mark.parametrize(
    "new",
    [
        pytest.param(
            _restating(p_min_pu=AttributeSpec(dtype=nw.Float64(), dims={"scenario"})),
            id="adding-an-attribute",
        ),
        pytest.param(
            _restating(
                marginal_cost=AttributeSpec(
                    dtype=nw.Float64(),
                    dims={"entity", "scenario", "timestep"},
                    breakpoints=True,
                )
            ),
            id="widening-dims",
        ),
        pytest.param(
            _schema(partial=frozenset({"entity", "scenario", "timestep"})),
            id="widening-partial",
        ),
        pytest.param(
            _restating(
                p_nom=AttributeSpec(
                    dtype=nw.Float64(),
                    dims={"entity"},
                    unit="kW",
                    description="Rated power.",
                )
            ),
            id="changing-a-unit",
        ),
    ],
)
def test_a_compatible_change(new):
    """Every row the old schema wrote still decodes under the new one.

    A row setting fewer dims reads an unset dim as NULL, which means all; an
    old row is owned at the coarser granularity; and neither `unit` nor
    `description` decides how a row decodes.

    Notes
    -----
    - [versioning](https://energy-models.github.io/datarecord/design/schema/#versioning)
    """
    assert new.compatible_with(_schema()) == []


_LABELLED = _with_entity_property("label", PropertySpec(dtype=nw.String()))


@pytest.mark.parametrize(
    ("old", "new", "reason"),
    [
        pytest.param(
            _schema(),
            _restating(
                p_max_pu=AttributeSpec(dtype=nw.Float64(), dims={"entity", "scenario"})
            ),
            "no longer varies over ['timestep']",
            id="narrowing-dims",
        ),
        pytest.param(
            _schema(),
            _restating(p_nom=AttributeSpec(dtype=nw.Int64(), dims={"entity"})),
            "Float64 -> Int64",
            id="changing-a-dtype",
        ),
        pytest.param(
            _schema(partial=frozenset({"entity", "scenario", "timestep"})),
            _schema(),
            "no longer `partial`",
            id="removing-from-partial",
        ),
        pytest.param(
            _schema(properties=_LABELLED),
            _schema(
                properties=_LABELLED,
                traits={
                    **_schema().traits,
                    "linking": Trait(
                        attributes={"label"}, on={"entity_type": {"Link"}}
                    ),
                },
            ),
            "category 'Generator' of 'entity_type' on 'entity' no longer carries ['label']",
            id="a-category-losing-a-property",
        ),
        pytest.param(
            _schema(),
            _schema(
                dimensions={
                    **_schema().dimensions,
                    "timestep": Dimension(dtype=nw.Datetime()),
                }
            ),
            "nesting changed",
            id="changing-nesting",
        ),
    ],
)
def test_an_incompatible_change(old, new, reason):
    """A row the old schema wrote has no valid reading under the new one.

    Notes
    -----
    - [versioning](https://energy-models.github.io/datarecord/design/schema/#versioning)
    """
    reasons = new.compatible_with(old)
    assert any(reason in r for r in reasons), reasons


# -- unit and description (https://energy-models.github.io/datarecord/design/schema/#unit-and-description) ---------------------------------------------


def test_unit_and_description_are_declared_on_both():
    """An axis may carry them too, not just an attribute.

    Notes
    -----
    - [unit and description](https://energy-models.github.io/datarecord/design/schema/#unit-and-description)
    """
    s = Schema(
        dimensions={
            "vintage": Dimension(
                dtype=nw.Int64(), unit="year", description="Build year."
            ),
            "scenario": Dimension(dtype=nw.String(), description="One realisation."),
        },
        attributes={
            "p_nom": AttributeSpec(
                dtype=nw.Float64(), unit="MW", description="Nominal power."
            )
        },
    )
    assert s.dimensions["vintage"].unit == "year"
    assert s.attributes["p_nom"].unit == "MW"
    # An axis whose labels are not a quantity declares none.
    assert s.dimensions["scenario"].unit is None
    assert AttributeSpec(dtype=nw.Float64(), unit="").unit == "", (
        '`""` is "genuinely dimensionless", apart from `None`, "undeclared"'
    )


# -- serialisation (https://energy-models.github.io/datarecord/design/schema/#one-schema-per-record) ----------------------------------------------------


def test_round_trips_through_json():
    """`manifest.json` is how a schema is written down, so this must be lossless."""
    s = _schema()
    back = Schema.model_validate_json(s.model_dump_json())
    assert back == s


def test_column_types_cover_structural_dims_and_flags():
    s = _schema()
    assert s.column_type("entity") == nw.String()
    assert s.column_type("timestep") == nw.Datetime()
    # One struct per flag column, a BOOLEAN field per declared dim (https://energy-models.github.io/datarecord/design/read-path/#owner-map), so
    # the map's column set does not widen when a dim is declared.
    for column in ("varies", "broadcast"):
        column_type = s.column_type(column)
        assert column_type == flag_type(s.broadcast_dims)
        assert column_type is not None
        duck_types = DuckTypes(duckdb.connect())
        assert "scenario BOOLEAN" in str(duck_types(column_type))
    assert s.column_type("value") is None
    assert s.value_type("p_nom") == nw.Float64()


def test_attributes_need_at_least_one_dim():
    """Attribute data varying over no axis is a table, not a record.

    Rejected at the schema rather than handled in the fold: the owner map's
    flag columns are structs with a field per dim, and DuckDB has no empty
    struct - so forbidding the case is what keeps a placeholder field out of
    every fold.

    Notes
    -----
    - [dimensions](https://energy-models.github.io/datarecord/design/schema/#dimensions)
    """
    with pytest.raises(ValidationError, match="at least one dim"):
        Schema(attributes={"p_nom": AttributeSpec(dtype=nw.Float64())})


# -- names (https://energy-models.github.io/datarecord/design/schema/#names) -----


def _declaring(position: str, name: str) -> Schema:
    """A minimal schema declaring `name` in one position."""
    dim = Dimension(dtype=nw.String())
    attr = AttributeSpec(dtype=nw.Float64(), dims={"entity"})
    if position == "dim":
        return Schema(dimensions={"entity": dim, name: dim}, partial={name})
    if position == "group":
        return Schema(
            dimensions={"entity": dim, "bus": dim},
            groups={name: Group(over=["entity", "bus"])},
        )
    if position == "coordinate":
        return Schema(
            dimensions={"entity": dim, "bus": dim},
            groups={"connection": Group(over={"entity": "entity", name: "bus"})},
        )
    if position == "attribute":
        return Schema(dimensions={"entity": dim}, attributes={name: attr})
    return Schema(dimensions={"entity": dim}, results={name: attr})


POSITIONS = ["dim", "group", "coordinate", "attribute", "result"]

WRITTEN = {
    "attribute": "a column datarecord writes",
    "breakpoint": "a column datarecord writes",
    "value": "a column datarecord writes",
    "deleted": "a column datarecord writes",
    "breakpoints": "a column datarecord writes",
    "varies": "a column datarecord writes",
    "broadcast": "a column datarecord writes",
    "layer_uuid": "a column datarecord writes",
    "order_key": "a column datarecord writes",
    "Value": "a column datarecord writes",
    "_depth": "starts with `_`",
    "_row": "starts with `_`",
    "_rank": "starts with `_`",
    "_first": "starts with `_`",
    "_broadcast": "starts with `_`",
    "_pos": "starts with `_`",
    'say "hi"': 'contains `"`',
    "a.b": "contains `.`",
}


@pytest.mark.parametrize("position", POSITIONS)
@pytest.mark.parametrize("name", list(WRITTEN))
def test_a_name_that_cannot_be_its_own_column_is_refused(name, position):
    """Every column the format or the fold writes beside a schema's own, `.` and
    `"`, which `duckdb.ColumnExpression` cannot spell, and case folded as DuckDB
    folds it. `deleted` as a dim read every label as a tombstone, and `value`
    gave the long file two columns of one name."""
    with pytest.raises(ValidationError) as refused:
        _declaring(position, name)
    message = str(refused.value)
    assert repr(name) in message, "the error names the offending name"
    assert WRITTEN[name] in message, "the error says why the name is refused"
    assert "Rename" in message, "the error says what to do"


@pytest.mark.parametrize("position", POSITIONS)
def test_names_differing_only_in_case_are_refused(position):
    """DuckDB resolves `Entity` and `entity` to one column, so declaring both
    would have one read the other's values."""
    with pytest.raises(ValidationError) as refused:
        _declaring(position, "Entity")
    message = str(refused.value)
    assert "'Entity'" in message, "the error names the new spelling"
    assert "'entity'" in message, "and the one it clashes with"
    assert "differ only in case" in message, "the error says why"


@pytest.mark.parametrize("position", POSITIONS)
@pytest.mark.parametrize("name", ["Order Size", "select", "Horizon", "1st"])
def test_a_name_duckdb_quotes_is_accepted(name, position):
    """A space, a keyword, mixed case or a leading digit all quote cleanly."""
    _declaring(position, name)
