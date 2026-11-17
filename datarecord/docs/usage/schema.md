<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# The schema

One schema per record, written down as `manifest.json` ([design](../design/schema.md)).

```python
import narwhals as nw
from datarecord import Schema, Dimension, AttributeSpec, PropertySpec, Group, Trait

schema = Schema(
    version=1,
    dimensions={
        "entity": Dimension(dtype=nw.String()),
        "bus": Dimension(dtype=nw.String()),
        "scenario": Dimension(dtype=nw.String()),
        "timestep": Dimension(dtype=nw.Datetime()),
    },
    properties={
        "entity": {
            "entity_type": PropertySpec(
                dtype=nw.Enum(["Bus", "Generator", "Link", "StorageUnit"])
            ),
            "carrier": PropertySpec(
                dtype=nw.String(), default="", default_by={"entity_type": {"Bus": "AC"}}
            ),
        },
        "connection": {"role": PropertySpec(dtype=nw.String())},
    },
    groups={"connection": Group(over={"entity": "entity", "bus": "bus"})},
    attributes={
        "p_nom": AttributeSpec(
            dtype=nw.Float64(), dims={"entity"}, default=0.0, unit="MW"
        ),
        "p_max_pu": AttributeSpec(
            dtype=nw.Float64(), dims={"entity", "scenario", "timestep"}, default=1.0
        ),
        "p_min_pu": AttributeSpec(
            dtype=nw.Float64(),
            dims={"entity", "timestep"},
            default=0.0,
            default_by={"entity_type": {"StorageUnit": -1.0}},
        ),
        "efficiency": AttributeSpec(
            dtype=nw.Float64(), dims={"connection", "timestep"}, default=1.0
        ),
    },
    traits={
        "dispatchable": Trait(
            attributes={"p_max_pu", "p_min_pu"},
            on={"entity_type": {"Generator", "StorageUnit"}},
        )
    },
    partial={"entity", "scenario", "connection"},
)
```

- **`Dimension`** declares one axis: its `dtype` (a narwhals dtype, translated to its DuckDB name — a DuckDB type name works too, for a type narwhals does not spell) and `within` for an axis whose labels identify a point only inside another's — multi-period time being the case ([design](../design/schema.md#within-an-axis-inside-an-axis)). `entity` is a dim like any other.
- **`properties`** is metadata: per subject — a dim or a group — the values that identify, classify or describe one of its labels, one value per label and never varying along another axis. Each is a column of the subject's own file, `dims/entity.parquet` or `groups/connection.parquet` ([design](../design/schema.md#properties)).
- **An `Enum` property of a `partial` dim categorizes it**: its values are the dim's categories, which traits and `default_by` key on. `entity_type` above is one; a dim may have several, and no name is special. `Schema.categorizing("entity")` lists them ([design](../design/schema.md#categories-an-enum-property-of-a-partial-dim)).
- **`default_by`** overrides `default` per category, on properties and attributes alike: the first key listing the label's category wins. `Schema.default_for("p_min_pu", entity_type="StorageUnit")` answers `-1.0` ([design](../design/schema.md#default_by-a-default-per-category)).
- **`attributes` is data**, and flat — one name, one spec, record-wide, across every section. **A `Trait` narrows** attributes (and properties) to the labels whose category its `on` names. One no trait claims is carried by every label its `dims` can address, so `p_nom` above reaches every entity while `p_max_pu` reaches only generators and storage units. `Schema.attributes_for("entity", entity_type="Bus")` and `Schema.properties_for(...)` resolve what a category carries ([design](../design/schema.md#traits)).
- **`AttributeSpec.dims`** is the only addressing mechanism, naming dims and groups alike — `efficiency` is a connection attribute because its `dims` name the group, carried as one struct column ([design](../design/schema.md#addressing-dims-x)). It is what makes a scenario-varying `p_nom` a violation rather than data. Every attribute lands in `inputs/`, whatever its `dims`, so widening one is a compatible change that moves no file.
- **`Group`** declares which tuples over several dims exist, mapping coordinate name → dim; a list is sugar where the two coincide. `connection` over `(entity, bus)` is the one every network has. Adding **`into`** declares the group _functional_ into that dim — each `over` tuple carrying exactly one of its labels — which is a constraint checkable on write ([design](../design/schema.md#groups)).
- **`partial`** is the layering granularity — which dims and groups a layer may patch value by value, and the fold key. `entity` in it lets a layer patch one entity, and is required for its categories to key traits and defaults. `scenario` is patchable; `timestep` is not, so a patch to one hour restates that entity's whole series rather than leaving a curve resolved across two layers with a hole in it ([design](../design/schema.md#partial-the-granularity-of-an-override)). A group is the same: with `connection` in it a layer patches one connection's `efficiency`, without it the layer restates every connection's.
- **`unit`** and **`description`** are stored and never interpreted — no conversion, no dimensional analysis. `None` is undeclared, `""` genuinely dimensionless ([design](../design/schema.md#unit-and-description)).

## Compatibility

`schema.compatible_with(other)` answers whether layers written under `other` still read under `self`, returning one reason per incompatibility and an empty list when the change is compatible ([design](../design/schema.md#versioning)).

```python
reasons = new_schema.compatible_with(old_schema)
if reasons:
    raise ValueError("\n".join(reasons))
```
