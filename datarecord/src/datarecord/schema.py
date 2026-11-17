# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""The schema: what a record's data is, and how a patch to it behaves.

One schema per record, and `manifest.json` is how it is written down - the two
words name the same thing, the file and the object.

Framework-independent. Dims, properties and attributes are names a schema
declares, because those vocabularies belong to a modelling framework and this
package knows none: a label no tool recognises reads back fine and is reported
by the tool that cannot build it, not rejected here.

Notes
-----
- [the schema](https://energy-models.github.io/datarecord/design/schema/)
- [one schema per record](https://energy-models.github.io/datarecord/design/schema/#one-schema-per-record)
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from graphlib import CycleError, TopologicalSorter
from typing import Any

import narwhals as nw
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

# Narwhals dtypes `manifest.json` encodes by bare class name, covering what a
# dim or attribute actually declares. `Enum` and `Datetime` carry parameters
# and are handled separately in `_dump_dtype`/`_parse_dtype` - extend here as
# a new bare dtype shows up rather than widening the parametrized branches.
_BARE_DTYPES: dict[str, type[nw.dtypes.DType]] = {
    "String": nw.String,
    "Float64": nw.Float64,
    "Int64": nw.Int64,
    "Boolean": nw.Boolean,
    "Date": nw.Date,
}


def _dump_dtype(dtype: nw.dtypes.DType) -> Any:
    """Encode a narwhals dtype for `manifest.json`.

    A bare class name for what `_BARE_DTYPES` covers; a one-key dict of class
    name to constructor args for `Enum`/`Datetime`, the parametrized dtypes a
    schema actually declares.
    """
    if isinstance(dtype, nw.Enum):
        return {"Enum": list(dtype.categories)}
    if isinstance(dtype, nw.Datetime):
        return {"Datetime": dtype.time_unit}
    base = dtype.base_type()
    if base.__name__ in _BARE_DTYPES:
        return base.__name__
    msg = f"no manifest.json encoding for narwhals dtype {base.__name__}"
    raise ValueError(msg)


def _parse_dtype(value: Any) -> nw.dtypes.DType:
    """The `dtype=` field_validator shared by `Dimension` and `AttributeSpec`.

    An instance (`nw.String()`) passes through; anything else is what
    `_dump_dtype` wrote to `manifest.json`, decoded back to an instance -
    `dtype=` takes an instance only, not a bare class.
    """
    if isinstance(value, nw.dtypes.DType):
        return value
    if isinstance(value, str):
        if value not in _BARE_DTYPES:
            msg = f"unknown narwhals dtype {value!r} in manifest.json"
            raise ValueError(msg)
        return _BARE_DTYPES[value]()
    if isinstance(value, dict) and len(value) == 1:
        ((name, arg),) = value.items()
        if name == "Enum":
            return nw.Enum(arg)
        if name == "Datetime":
            return nw.Datetime(arg)
    msg = f"unrecognised dtype encoding in manifest.json: {value!r}"
    raise ValueError(msg)


# Columns the format fixes, whatever the schema declares (https://energy-models.github.io/datarecord/design/format/#the-long-schema). Not the
# dims or properties: each is declared and typed from that declaration, which is
# what lets an `Enum` there pin its vocabulary. These are the ones no schema
# names - `breakpoint` is NULL for an ordinary scalar, so one column set serves
# every row.
STRUCTURAL_TYPES = {
    "attribute": nw.String(),
    "breakpoint": nw.Float64(),
    "deleted": nw.Boolean(),
    "breakpoints": nw.Boolean(),
}


# Every long row's trailing columns, whatever coordinates precede them: the
# attribute named, the abscissa of a piecewise-linear value, and the value
# (https://energy-models.github.io/datarecord/design/format/#the-long-schema).
LONG_TAIL = ("attribute", "breakpoint", "value")


# The owner map's flag columns: two structs with a field per declared dim, so
# the map's column set does not depend on the schema and adding a dim stays the
# compatible change versioning calls it. `breakpoints` is outside both, being no dim
# (https://energy-models.github.io/datarecord/design/read-path/#owner-map, https://energy-models.github.io/datarecord/design/record/#flags).
FLAG_COLUMNS = ("varies", "broadcast", "breakpoints")


LAYER_COLUMN = "layer_uuid"
"""The owner map's column naming the layer each row's value is read from.

Notes
-----
- [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
"""


DERIVED = ("order_key",)
"""Columns a resolved frame carries that no layer file may.

The fold's answer *about* a frame rather than data in it, so writing one would
both put a column in a file the format does not define and read as stored order
where the fold always re-derives it from file order.

Notes
-----
- [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
"""


RESERVED = frozenset(
    {*STRUCTURAL_TYPES, *LONG_TAIL, *FLAG_COLUMNS, LAYER_COLUMN, *DERIVED}
)
"""Columns datarecord writes beside a schema's own, which no declaration may take.

Compared ignoring case, as DuckDB resolves a column name. The fold's scratch
columns are not listed: every one starts with `_`, which `Schema` refuses as a
declared name's first character instead.

Notes
-----
- [names](https://energy-models.github.io/datarecord/design/schema/#names)
"""


def _misnamed(name: str) -> str | None:
    """Why `name` cannot be a declared dim, group, coordinate or attribute, if so.

    `duckdb.ColumnExpression` is how every declared name becomes a column
    reference, and it reads `a.b` as column `b` of table `a` and cannot spell a
    `"` at all; those two are what make a name unquotable, rather than a space
    or a keyword, which it quotes.
    """
    if '"' in name:
        return 'contains `"`, which no DuckDB column reference can spell'
    if "." in name:
        return "contains `.`, which DuckDB reads as a table qualifier"
    if name.startswith("_"):
        return "starts with `_`, kept for the columns a fold adds and drops"
    if name.lower() in RESERVED:
        return f"is `{name.lower()}`, a column datarecord writes into every record"
    return None


def flag_type(dims: tuple[str, ...]) -> nw.dtypes.DType:
    """One flag struct's type: a BOOLEAN field per declared dim.

    `dims` is never empty: a schema declaring no dims describes no dimensioned
    data, which `Schema` rejects - so the struct always has a field and
    needs no placeholder for DuckDB's want of an empty one.

    Notes
    -----
    - [dimensions](https://energy-models.github.io/datarecord/design/schema/#dimensions)
    - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
    """
    return nw.Struct({d: nw.Boolean() for d in dims})


class Dimension(BaseModel):
    """One axis attribute data may vary over: its shape, not its data.

    Not which dims an *attribute* varies over (`AttributeSpec.dims`), nor the
    patch granularity (`Schema.partial`), nor order - an axis is ordered by its
    file's row order, undeclared.

    Attributes
    ----------
    dtype
        The axis labels' type, as a narwhals dtype instance (`nw.String()`,
        `nw.Datetime()`, ...) - translated to its DuckDB name only where a
        column of it is built.
    within
        Dims this one's labels identify a point only *within*; transitive.
    unit
        What this axis's *labels* measure, if anything - `None` is undeclared,
        `""` genuinely dimensionless.
    description
        What the axis is, in prose. Never interpreted.

    Notes
    -----
    - [axis order](https://energy-models.github.io/datarecord/design/record/#axis-order)
    - [dimensions](https://energy-models.github.io/datarecord/design/schema/#dimensions)
    - [within](https://energy-models.github.io/datarecord/design/schema/#within-an-axis-inside-an-axis)
    - [unit and description](https://energy-models.github.io/datarecord/design/schema/#unit-and-description)
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    dtype: nw.dtypes.DType
    within: frozenset[str] = frozenset()
    unit: str | None = None
    description: str | None = None

    @field_validator("dtype", mode="before")
    @classmethod
    def _parse_dtype(cls, value: Any) -> Any:
        return _parse_dtype(value)

    @field_serializer("dtype")
    def _dump_dtype(self, value: nw.dtypes.DType) -> Any:
        return _dump_dtype(value)


class _ValueSpec(BaseModel):
    """What `AttributeSpec` and `PropertySpec` share: a typed value and its defaults.

    The `default`/`default_by` encoding lives here once, so a property and an
    attribute round-trip `manifest.json` identically.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    dtype: nw.dtypes.DType
    default: Any | None = None
    default_by: dict[str, dict[str, Any]] = Field(default_factory=dict)
    unit: str | None = None
    description: str | None = None

    @field_validator("dtype", mode="before")
    @classmethod
    def _parse_dtype(cls, value: Any) -> Any:
        return _parse_dtype(value)

    @field_serializer("dtype")
    def _dump_dtype(self, value: nw.dtypes.DType) -> Any:
        return _dump_dtype(value)

    @field_serializer("default")
    def _serialise_default(self, value: Any) -> Any:
        return _encode_default(value)

    @field_validator("default", mode="before")
    @classmethod
    def _parse_default(cls, value: Any) -> Any:
        return _decode_default(value)

    @field_serializer("default_by")
    def _serialise_default_by(
        self, value: dict[str, dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        return {
            key: {label: _encode_default(v) for label, v in by.items()}
            for key, by in value.items()
        }

    @field_validator("default_by", mode="before")
    @classmethod
    def _parse_default_by(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        return {
            key: {label: _decode_default(v) for label, v in by.items()}
            if isinstance(by, dict)
            else by
            for key, by in value.items()
        }


def _encode_default(value: Any) -> Any:
    """Encode a non-finite default as a string; JSON has no literal for one.

    `inf` is an ordinary default for an unbounded capacity, and JSON's
    `Infinity` is not valid JSON - a plain dump reads back as `None`,
    turning "unbounded" into "no default". `_decode_default` reverses this.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return f"__{value}__"
    return value


def _decode_default(value: Any) -> Any:
    """Decode what `_encode_default` encoded."""
    if isinstance(value, str) and value.startswith("__") and value.endswith("__"):
        try:
            return float(value[2:-2])
        except ValueError:
            return value
    return value


class AttributeSpec(_ValueSpec):
    """What shape one attribute's data may take.

    Attributes
    ----------
    dtype
        The value column's type, as a narwhals dtype instance (`nw.String()`,
        `nw.Datetime()`, ...) - translated to its DuckDB name only where a
        column of it is built.
    dims
        Dims and groups this attribute may vary over; a subset of those
        declared. Whatever they are, its values are long rows of
        `inputs/<attr>.parquet`.
    default
        The value a coordinate no row covers takes.
    default_by
        A categorizing property -> category -> the default for labels of that
        category, overriding `default`; the first key, in declaration order,
        listing a label's category wins. Each key must categorize a dim the
        attribute reaches. Read through `Schema.default_for`; never applied by
        the record layer.
    breakpoints
        Whether it may carry a piecewise-linear curve.
    unit
        What the values measure - `"MW"`, `"EUR/MWh"`. Stored and never
        interpreted; `None` is undeclared, `""` genuinely dimensionless.
    description
        What the attribute is, in prose. Never interpreted.

    Notes
    -----
    - [wide and long rows](https://energy-models.github.io/datarecord/design/record/#wide-and-long-rows)
    - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
    - [the broadcast rule](https://energy-models.github.io/datarecord/design/record/#the-broadcast-rule)
    - [where a value lives](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
    - [AttributeSpec](https://energy-models.github.io/datarecord/design/schema/#attributespec)
    - [unit and description](https://energy-models.github.io/datarecord/design/schema/#unit-and-description)
    """

    dims: frozenset[str] = frozenset()
    breakpoints: bool = False


class PropertySpec(_ValueSpec):
    """One value per label of a dim, or per tuple of a group, describing it.

    A property is keyed by its subject (`Schema.properties`) and stored as a
    column of `dims/{dim}.parquet`, or of `groups/{group}.parquet` for a group.
    An `Enum` property of a dim in `partial` categorizes it
    (`Schema.categorizing`); a group's never does.

    Attributes
    ----------
    dtype
        The column's type, as a narwhals dtype instance.
    default
        The value a label no row sets takes.
    default_by
        A categorizing property of a dim the subject reaches -> category -> the
        default for labels of that category, overriding `default`. Refused on a
        categorizing property itself. Read through `Schema.default_for`.
    unit
        What the values measure; `None` is undeclared.
    description
        What the property is, in prose. Never interpreted.

    Notes
    -----
    - [the schema](https://energy-models.github.io/datarecord/design/schema/)
    - [where a value lives](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
    """


class Group(BaseModel):
    """Which tuples over several dims exist: a sparse subset of a dim product.

    Not a dim. A dim declares an axis of labels and NULL in its column means
    "every value of it"; a group declares *which combinations are there*, which
    no axis can say because the product is sparse - an entity attaches to two
    buses out of a thousand.

    An attribute names the group in its `dims` and its rows carry the group as
    one struct column of the group's name, a field per key coordinate
    (`Schema.group_type`). Coordinates rather than dims because two of them may
    draw on the same axis: a corridor between two entities is `(from, to)`,
    which a set of dims could not spell.

    Attributes
    ----------
    over
        Coordinate name -> the dim it draws its labels from. A list is sugar for
        the dict with identical keys and values; the dict form is what lets two
        coordinates draw on one dim, as `corridor`'s `{from: bus, to: bus}` does.
    into
        The dim each tuple of `over` carries exactly one label of, or `None` for
        a bare tuple set. Must name a declared dim.
    description
        What the group is, in prose. Never interpreted.

    Notes
    -----
    - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
    """

    over: dict[str, str]
    into: str | None = None
    description: str | None = None

    @field_validator("over", mode="before")
    @classmethod
    def _parse_over(cls, value: Any) -> Any:
        """Expand the list form to the dict it is sugar for."""
        if isinstance(value, (list, tuple)):
            return {c: c for c in value}
        return value

    @property
    def key(self) -> tuple[str, ...]:
        """The coordinates a row is unique over: `over`'s, in declaration order.

        `into` is none of them: it follows from the key.

        Notes
        -----
        - [into](https://energy-models.github.io/datarecord/design/schema/#into-a-group-that-classifies)
        """
        return tuple(self.over)


class Trait(BaseModel):
    """A named bundle of attributes, and which categories and labels carry it.

    The narrowing direction: an attribute the schema declares is carried by
    every label, and a trait is how that is cut down to the labels of some
    categories, and further to some of those labels. A trait bundling
    `p_max_pu` `on={"entity_type": {"Generator"}}` says those attributes reach
    generators and no other entity - unless another trait claiming them
    matches it too.

    Attributes
    ----------
    attributes
        The attributes this trait bundles, and properties of the dim its `on`
        key categorizes. Each must be declared. Includes `switch` once parsed,
        whatever the author wrote.
    on
        Mapping one categorizing property (`Schema.categorizing`) -> the
        categories of it this trait applies to. At most one key. Empty means
        this narrowing does not apply, reaching every label.
    switch
        The attribute deciding, per label of the dim the `on` key
        categorizes, whether this trait applies - addressed by that dim
        exactly, so it needs an `on` key. `None` means this narrowing does not
        apply, reaching every label.
    description
        What the trait is, in prose. Never interpreted.

    Notes
    -----
    - [traits](https://energy-models.github.io/datarecord/design/schema/#traits)
    - [switch](https://energy-models.github.io/datarecord/design/schema/#switch-a-trait-an-entity-opts-into)
    """

    attributes: frozenset[str] = frozenset()
    on: dict[str, frozenset[str]] = Field(default_factory=dict)
    switch: str | None = None
    description: str | None = None

    @model_validator(mode="after")
    def _fold_switch_into_attributes(self) -> Trait:
        """Add `switch` to `attributes`, so a caller need not name it twice."""
        if self.switch is not None and self.switch not in self.attributes:
            self.attributes = self.attributes | {self.switch}
        return self


class Schema(BaseModel):
    """One record's schema.

    Attributes
    ----------
    version
        Bumped by any change to the declarations. A reader meeting a
        version it was not written for should refuse rather than guess.
    dimensions
        Every declared axis, keyed by dim name.
    attributes
        Attribute -> spec, flat and record-wide. One attribute is one spec and
        one `inputs/<attr>.parquet`, so a dtype cannot differ per type.
    properties
        Subject dim or group -> property name -> spec: the columns of
        `dims/{dim}.parquet` or `groups/{group}.parquet` that describe its
        labels. A dim's `Enum` properties categorize it where it is in
        `partial`.
    groups
        Group name -> which tuples over several dims exist.
    traits
        Trait -> the attributes it bundles and the categories carrying them.
        A vocabulary a consumer dispatches on, declared rather than derived,
        and the only thing that narrows an attribute to some labels.
    partial
        Which dims a layer may patch value by value. `None` for a record
        with no layers, since nothing overrides anything. A dim outside it is
        one a layer owns entirely once it touches it.
    meta
        A framework's own top-level data - network attributes, CRS, free-form
        metadata. Stored and never interpreted, since none of it describes the
        dimensioned data.

    Notes
    -----
    - [the schema](https://energy-models.github.io/datarecord/design/schema/)
    - [partial](https://energy-models.github.io/datarecord/design/schema/#partial-the-granularity-of-an-override)
    - [versioning](https://energy-models.github.io/datarecord/design/schema/#versioning)
    """

    version: int = 1
    dimensions: dict[str, Dimension] = Field(default_factory=dict)
    attributes: dict[str, AttributeSpec] = Field(default_factory=dict)
    results: dict[str, AttributeSpec] = Field(default_factory=dict)
    """What a solve computes, keyed like `attributes` and shaped the same.

    Separate because the two are governed differently, not because they are
    stored differently: a result is written to `outputs/<attr>.parquet` rather
    than `inputs/`, never overlays a parent's, and may name an entity the
    record does not declare. Keeping it out of `attributes` is what stops it
    reaching `attributes_for`, and so `add`'s wide-frame split and the input
    validation, neither of which a result should meet.
    """

    properties: dict[str, dict[str, PropertySpec]] = Field(default_factory=dict)
    groups: dict[str, Group] = Field(default_factory=dict)
    traits: dict[str, Trait] = Field(default_factory=dict)
    partial: frozenset[str] | None = None
    meta: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate(self) -> Schema:
        """Check the rules the format itself fixes.

        Notes
        -----
        - [dimensions](https://energy-models.github.io/datarecord/design/schema/#dimensions)
        - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
        - [traits](https://energy-models.github.io/datarecord/design/schema/#traits)
        - [within](https://energy-models.github.io/datarecord/design/schema/#within-an-axis-inside-an-axis)
        - [names](https://energy-models.github.io/datarecord/design/schema/#names)
        """
        self._check_names()
        declared = set(self.dimensions)

        # Attributes but no axes is a table, not a record (https://energy-models.github.io/datarecord/design/schema/#dimensions). Rejected here
        # so the owner map never needs a struct with no fields, which DuckDB has
        # no type for. A wholly empty `Schema()` stays legal: "no manifest yet".
        if (self.attributes or self.results) and not declared:
            msg = (
                "a schema declaring attributes must declare at least one dim; "
                "attribute data varying over no axis is not a record (https://energy-models.github.io/datarecord/design/schema/#dimensions)"
            )
            raise ValueError(msg)

        for dim, spec in self.dimensions.items():
            unknown = sorted(spec.within - declared)
            if unknown:
                msg = f"dim {dim!r} is `within` undeclared dims {unknown}"
                raise ValueError(msg)
            if dim in spec.within:
                msg = f"dim {dim!r} is `within` itself"
                raise ValueError(msg)
        # `TopologicalSorter` only needs preparing to reject a cycle, and
        # `CycleError.args[1]` is the offending path - so the acyclicity `within`
        # requires is stdlib rather than a graph walk kept here.
        try:
            TopologicalSorter(
                {d: s.within for d, s in self.dimensions.items()}
            ).prepare()
        except CycleError as e:
            msg = f"`within` is cyclic: {' -> '.join(e.args[1])}"
            raise ValueError(msg) from e

        for group, group_spec in self.groups.items():
            unknown = sorted(set(group_spec.over.values()) - declared)
            if unknown:
                msg = f"group {group!r} is over undeclared dims {unknown}"
                raise ValueError(msg)
            if group in declared:
                renamed = "_".join((*group_spec.over, group))
                msg = (
                    f"group {group!r} shares its name with the dim {group!r}; a "
                    f"group is carried as a column named for it, so the two would "
                    f"be one column. Rename the group, e.g. {renamed!r} into "
                    f"{group!r} (https://energy-models.github.io/datarecord/design/schema/#addressing-dims-x)"
                )
                raise ValueError(msg)
            if group_spec.into is not None and group_spec.into not in declared:
                msg = (
                    f"group {group!r} is `into` undeclared dim "
                    f"{group_spec.into!r}; `into` names the axis whose labels "
                    f"the group's tuples carry (https://energy-models.github.io/datarecord/design/schema/#into-a-group-that-classifies)"
                )
                raise ValueError(msg)
            if group_spec.into is not None and group_spec.into in group_spec.over:
                msg = (
                    f"group {group!r} is `into` {group_spec.into!r}, which is "
                    f"also one of its `over` coordinates; a group cannot map a "
                    f"coordinate to itself"
                )
                raise ValueError(msg)

        self._check_properties()

        addressable = declared | set(self.groups)
        for attr, attr_spec in (*self.attributes.items(), *self.results.items()):
            unknown = sorted(attr_spec.dims - addressable)
            if unknown:
                msg = (
                    f"attribute {attr!r} is addressed by undeclared "
                    f"dims or groups {unknown}"
                )
                raise ValueError(msg)
            for group, group_spec in self.groups.items():
                if group in self.groups_of(attr):
                    twice = sorted(set(group_spec.key) & attr_spec.dims)
                    if twice:
                        msg = (
                            f"attribute {attr!r} is addressed by the group "
                            f"{group!r} and by {twice}, which the group's "
                            f"column already carries; naming both keys a row "
                            f"twice over (https://energy-models.github.io/datarecord/design/schema/#groups)"
                        )
                        raise ValueError(msg)
                if group_spec.into is None or group_spec.into not in attr_spec.dims:
                    continue
                both = sorted(set(group_spec.over) & attr_spec.dims)
                if both:
                    msg = (
                        f"attribute {attr!r} is addressed by "
                        f"{group_spec.into!r} and {both}, which the group "
                        f"{group!r} maps it from; `into` says the first follows "
                        f"from the second, so naming both keys a row twice over"
                    )
                    raise ValueError(msg)

        for trait, trait_spec in self.traits.items():
            self._check_trait(trait, trait_spec)

        if self.partial is not None:
            unknown = sorted(self.partial - declared - set(self.groups))
            if unknown:
                msg = f"`partial` names undeclared dims or groups {unknown}"
                raise ValueError(msg)
        return self

    def _categorized_by(self, name: str, what: str) -> str:
        """The dim `name` categorizes, for a trait's `on` or a `default_by` key `what` names."""
        subject = self.subject_of(name)
        if subject is None:
            reason = "is no property"
        elif subject in self.groups:
            reason = (
                f"is a property of the group {subject!r}; a group is never categorized"
            )
        elif not isinstance(self.properties[subject][name].dtype, nw.Enum):
            reason = "is no `Enum` property"
        elif subject not in (self.partial or set()):
            reason = f"is a property of {subject!r}, which `partial` does not list"
        else:
            return subject
        msg = f"{what} is keyed by {name!r}, which {reason}"
        raise ValueError(msg)

    def _check_trait(self, trait: str, spec: Trait) -> None:
        """Refuse a trait `on` anything but one categorizing property, bundling one, or switched off its dim.

        Only a categorizing property may scope a trait: any other would make
        which attributes a label carries depend on data no schema pins, where
        every caller of `attributes_for` answers from the schema alone. One key
        at most, since the trait then narrows over exactly one dim, the one its
        switch must be addressed by, and the one whose properties it may
        bundle beside attributes.
        """
        if len(spec.on) > 1:
            msg = (
                f"trait {trait!r} is `on` {sorted(spec.on)}; a trait is `on` one "
                f"categorizing property, narrowing over that property's dim "
                f"alone - split it into one trait per property"
            )
            raise ValueError(msg)
        subject = None
        for name, categories in spec.on.items():
            subject = self._categorized_by(name, f"trait {trait!r}")
            unknown = sorted(categories - set(self._categories(subject, name)))
            if unknown:
                msg = (
                    f"trait {trait!r} is `on` {unknown}, which are not "
                    f"categories of {name!r}"
                )
                raise ValueError(msg)
        bundleable = {*self.attributes, *self.properties.get(subject or "", {})}
        unknown = sorted(spec.attributes - bundleable)
        if unknown:
            msg = (
                f"trait {trait!r} bundles undeclared attributes {unknown}; a "
                f"trait bundles declared attributes, and properties of the dim "
                f"its `on` key categorizes"
            )
            raise ValueError(msg)
        categorizing = sorted(spec.attributes & set(self.categorizing(subject or "")))
        if categorizing:
            msg = (
                f"trait {trait!r} bundles {categorizing}, which categorize "
                f"{subject!r}; a category scoped by a category is circular - a "
                f"categorizing property is carried by every label"
            )
            raise ValueError(msg)
        if spec.switch is None:
            return
        if subject is None:
            msg = (
                f"trait {trait!r} is switched on {spec.switch!r} but `on` no "
                f"category; a switch decides a trait per label of the dim its "
                f"`on` key categorizes"
            )
            raise ValueError(msg)
        switch_spec = self.attributes.get(spec.switch)
        if switch_spec is not None and switch_spec.dims != {subject}:
            msg = (
                f"trait {trait!r} is switched on {spec.switch!r}, which is "
                f"addressed by {sorted(switch_spec.dims)}; a switch decides a "
                f"trait per label of {subject!r}, the dim its `on` key "
                f"categorizes, so it is addressed by that dim alone"
            )
            raise ValueError(msg)

    def _check_properties(self) -> None:
        """Refuse a property on an undeclared subject, and a malformed `default_by`.

        Run after `_check_names`, so a property name is already known not to
        clash with an attribute's.
        """
        unknown = sorted(set(self.properties) - set(self.dimensions) - set(self.groups))
        if unknown:
            msg = (
                f"properties are declared on undeclared dims or groups {unknown}; "
                f"a property is a column of its subject's axis or group file"
            )
            raise ValueError(msg)
        for subject, by_name in self.properties.items():
            for name in self.categorizing(subject):
                if by_name[name].default_by:
                    msg = (
                        f"property {name!r} categorizes {subject!r} and has a "
                        f"`default_by`; a category defaulted by a category is "
                        f"circular - give it a plain `default`"
                    )
                    raise ValueError(msg)
        valued: list[tuple[str, _ValueSpec, frozenset[str]]] = [
            *(
                (f"property {n!r}", s, self._reached_by(subject))
                for subject, by_name in self.properties.items()
                for n, s in by_name.items()
            ),
            *(
                (
                    f"attribute {a!r}",
                    s,
                    frozenset(d for d in self.dimensions if self.addresses(a, d)),
                )
                for a, s in (*self.attributes.items(), *self.results.items())
            ),
        ]
        for what, spec, reached in valued:
            for key, by in spec.default_by.items():
                subject = self._categorized_by(key, f"{what}'s `default_by`")
                if subject not in reached:
                    msg = (
                        f"{what} has `default_by` {key!r} but does not reach "
                        f"its dim {subject!r}, so no label of it has a category "
                        f"to default by"
                    )
                    raise ValueError(msg)
                unknown = sorted(set(by) - set(self._categories(subject, key)))
                if unknown:
                    msg = (
                        f"{what} has `default_by` for {unknown}, which are not "
                        f"categories of {key!r}"
                    )
                    raise ValueError(msg)

    def _reached_by(self, subject: str) -> frozenset[str]:
        """The dims a property of `subject` reaches: the dim, or those its group draws on."""
        if subject in self.groups:
            return frozenset(self.groups[subject].over.values())
        return frozenset({subject})

    def _check_names(self) -> None:
        """Refuse every declared name that cannot be a column of its own.

        A group's name is a column too, its struct column, and so is a
        property's. Two spellings of one name differing only in case are
        refused, DuckDB resolving both to one column; one spelling declared
        twice, as a group's coordinate naming a dim, is left to the rules that
        govern it - except across attributes, results and properties, where one
        name is one spec, and a property named like a dim or group.
        """
        valued = [
            *(("attribute", a) for a in self.attributes),
            *(("result", r) for r in self.results),
            *(
                (f"property of {d!r}", p)
                for d, specs in self.properties.items()
                for p in specs
            ),
        ]
        declared = [
            *(("dim", d) for d in self.dimensions),
            *(("group", g) for g in self.groups),
            *(
                (f"coordinate of group {g!r}", c)
                for g, spec in self.groups.items()
                for c in spec.over
            ),
            *valued,
        ]
        problems = []
        for kind, name in declared:
            why = _misnamed(name)
            if why is not None:
                problems.append(f"{kind} {name!r} {why}")
        kinds: dict[str, list[str]] = {}
        for kind, name in valued:
            kinds.setdefault(name, []).append(kind)
        coordinates = [
            *(("dim", d) for d in self.dimensions),
            *(("group", g) for g in self.groups),
        ]
        for kind, name in coordinates:
            if any(k.startswith("property") for k in kinds.get(name, ())):
                msg = (
                    f"property {name!r} shares its name with the {kind} "
                    f"{name!r}, whose column it would collide with - rename "
                    f"the property"
                )
                raise ValueError(msg)
        for group, spec in self.groups.items():
            shared = sorted(set(spec.over) & set(self.properties.get(group, {})))
            if shared:
                msg = (
                    f"properties {shared} of group {group!r} share their names "
                    f"with its coordinates, which name a tuple's fields - "
                    f"rename the properties"
                )
                raise ValueError(msg)
        clashing = {n: k for n, k in kinds.items() if len(k) > 1}
        if clashing:
            detail = "; ".join(
                f"{n!r} as {' and '.join(k)}" for n, k in clashing.items()
            )
            msg = (
                f"one name is one spec, but these are declared more than once: {detail}"
            )
            raise ValueError(msg)
        spellings: dict[str, dict[str, str]] = {}
        for kind, name in declared:
            spellings.setdefault(name.lower(), {}).setdefault(name, kind)
        for named in spellings.values():
            if len(named) > 1:
                clash = ", ".join(f"{kind} {name!r}" for name, kind in named.items())
                problems.append(f"{clash} differ only in case, one column to DuckDB")
        if problems:
            msg = (
                f"a schema may not declare these names: {'; '.join(problems)}. "
                f"Rename each: a declared name becomes a column beside those "
                f"datarecord writes itself, {sorted(RESERVED)} and any starting "
                f"with `_` (https://energy-models.github.io/datarecord/design/schema/#names)"
            )
            raise ValueError(msg)

    # -- derived key sets (https://energy-models.github.io/datarecord/design/schema/#partial-the-granularity-of-an-override) --------------------------------------

    @property
    def dims(self) -> tuple[str, ...]:
        """Every declared dim, in declaration order - the long schema's dim columns.

        Notes
        -----
        - [the long schema](https://energy-models.github.io/datarecord/design/format/#the-long-schema)
        """
        return tuple(self.dimensions)

    @property
    def broadcast_dims(self) -> tuple[str, ...]:
        """The coordinates a NULL broadcasts over: every declared dim and every group column.

        A NULL here means "every value of this dim", which the fold expands
        against the axis; a NULL struct means every tuple of the resolved
        group.

        What the `varies`/`broadcast` structs have a field per, and what
        `expand_dims` joins.

        Notes
        -----
        - [the broadcast rule](https://energy-models.github.io/datarecord/design/record/#the-broadcast-rule)
        - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
        """
        return (*self.dims, *self.group_columns)

    def coordinates_of(self, attribute: str) -> tuple[str, ...]:
        """The coordinate columns one attribute's rows carry, groups first.

        A group in `dims` is carried as one struct column named for it
        (`group_type`), so `dims={"connection", "snapshot"}` gives
        `("connection", "snapshot")`.

        Per attribute rather than schema-wide: one file per attribute means one
        column set per attribute, and an all-NULL column of a dim the attribute
        is not addressed by would claim a coordinate the value has none of.

        Notes
        -----
        - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
        - [addressing](https://energy-models.github.io/datarecord/design/schema/#addressing-dims-x)
        - [the long schema](https://energy-models.github.io/datarecord/design/format/#the-long-schema)
        """
        spec = self.spec_for(attribute)
        if spec is None:
            return ()
        return (*self.groups_of(attribute), *(d for d in self.dims if d in spec.dims))

    @property
    def group_columns(self) -> tuple[str, ...]:
        """Every group, each carried in a row as one struct column named for it.

        Notes
        -----
        - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
        """
        return tuple(self.groups)

    def group_type(self, group: str) -> nw.dtypes.DType:
        """The struct a row carries `group` as: a field per key coordinate.

        Each field typed as the dim the coordinate draws on. `into` is no field:
        it follows from the key, so carrying it would key a row twice over.

        Notes
        -----
        - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
        """
        spec = self.groups[group]
        return nw.Struct({c: self.dimensions[spec.over[c]].dtype for c in spec.key})

    def check_group_columns(
        self,
        groups: Iterable[str],
        frame: nw.LazyFrame[Any],
        *,
        carrier: str,
    ) -> None:
        """Reject each of `groups` carried other than as one struct column of exactly its key, whole or NULL.

        A carrier without a group's column passes.

        Parameters
        ----------
        carrier
            What carries the columns, named in the message.

        Raises
        ------
        ValueError
            On a key coordinate as a column of its own, a group column not a
            struct of exactly the key, naming the struct to pass instead, or a
            struct with some fields NULL and not all.

        Notes
        -----
        - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
        - [the broadcast rule](https://energy-models.github.io/datarecord/design/record/#the-broadcast-rule)
        """
        columns = frame.collect_schema()
        for group in groups:
            key = self.group_key(group)
            flat = [c for c in key if c in columns]
            dtype = columns.get(group)
            fields = (
                key
                if dtype is None
                else [f.name for f in dtype.fields]
                if isinstance(dtype, nw.Struct)
                else None
            )
            if flat or fields is None or set(fields) != set(key):
                carried = f"{flat} flat" if flat else f"{group!r} as {dtype}"
                msg = (
                    f"{carrier} carries {carried}; pass {group!r} as one struct "
                    f"column with a field per key coordinate, {list(key)} (https://energy-models.github.io/datarecord/design/schema/#groups)"
                )
                raise ValueError(msg)
            if dtype is None:
                continue
            struct = nw.col(group)
            partly = ~struct.is_null() & nw.any_horizontal(
                *(struct.struct.field(c).is_null() for c in key), ignore_nulls=True
            )
            if not frame.filter(partly).head(1).collect().is_empty():
                msg = (
                    f"{carrier} carries a {group!r} with some fields NULL; a "
                    f"group value is a whole tuple, or NULL for every tuple (https://energy-models.github.io/datarecord/design/record/#the-broadcast-rule)"
                )
                raise ValueError(msg)

    def long_columns_for(self, attribute: str) -> tuple[str, ...]:
        """One attribute's full long column set, in order - input or result.

        An attribute carries the coordinates its `dims` name and no others, so a
        per-snapshot weighting has no column for any other dim.

        An attribute neither vocabulary declares is `long_columns` - every
        declared dim, the widest shape. That is a schema with no manifest yet,
        every declared attribute having its own coordinates.

        Notes
        -----
        - [the long schema](https://energy-models.github.io/datarecord/design/format/#the-long-schema)
        - [results](https://energy-models.github.io/datarecord/design/working-record/#results-through-kindoutputs)
        """
        if self.spec_for(attribute) is None:
            return self.long_columns
        return (*self.coordinates_of(attribute), *LONG_TAIL)

    def categorizing(self, dim: str) -> tuple[str, ...]:
        """The `Enum` properties of `dim`, if `partial` lists it: what a trait or `default_by` keys on.

        Notes
        -----
        - [traits](https://energy-models.github.io/datarecord/design/schema/#traits)
        """
        if dim not in self.dimensions or dim not in (self.partial or set()):
            return ()
        return tuple(
            name
            for name, spec in self.properties.get(dim, {}).items()
            if isinstance(spec.dtype, nw.Enum)
        )

    def _categories(self, dim: str, name: str) -> tuple[str, ...]:
        """The `Enum` categories of property `name` of `dim`; empty for any other dtype."""
        dtype = self.properties[dim][name].dtype
        return tuple(dtype.categories) if isinstance(dtype, nw.Enum) else ()

    def require_categorizing(self, subject: str, keys: Iterable[str]) -> None:
        """Refuse a key that is not a categorizing property of `subject`.

        Raises
        ------
        ValueError
            Naming the keys and `subject`'s categorizing properties.

        Notes
        -----
        - [traits](https://energy-models.github.io/datarecord/design/schema/#traits)
        """
        allowed = self.categorizing(subject)
        unknown = sorted(set(keys) - set(allowed))
        if unknown:
            msg = (
                f"{unknown} do not categorize {subject!r}; its categorizing "
                f"properties are {list(allowed)}"
            )
            raise ValueError(msg)

    def require_listed(
        self, subject: str, data: Mapping[str, Iterable[Any]], what: str
    ) -> None:
        """Refuse a value of an `Enum` property of `subject` its categories do not list.

        `data` maps names to values; a name that is no `Enum` property of
        `subject` is skipped, as is a NULL.

        Raises
        ------
        ValueError
            Naming `what`, the property, the unlisted values and its categories.
        """
        specs = self.properties.get(subject, {})
        for name, values in data.items():
            dtype = specs[name].dtype if name in specs else None
            if not isinstance(dtype, nw.Enum):
                continue
            unknown = sorted(
                {str(v) for v in values if v is not None} - {*dtype.categories}
            )
            if unknown:
                msg = (
                    f"{what} gives {name!r} values {unknown}, which are not "
                    f"categories of {name!r}; it declares {list(dtype.categories)}"
                )
                raise ValueError(msg)

    def default_for(self, name: str, **categories: str) -> Any:
        """The default of attribute, result or property `name` for a label of `categories`.

        The first `default_by` key listing the label's category decides, else
        `default`; a category left out matches none.

        Raises
        ------
        KeyError
            If no attribute, result or property is called `name`.

        Notes
        -----
        - [AttributeSpec](https://energy-models.github.io/datarecord/design/schema/#attributespec)
        """
        spec: _ValueSpec | None = self.spec_for(name) or self.property_spec(name)
        if spec is None:
            raise KeyError(name)
        for key, by in spec.default_by.items():
            category = categories.get(key)
            if category in by:
                return by[category]
        return spec.default

    def addresses(self, attribute: str, dim: str) -> bool:
        """Whether `attribute` reaches a label of `dim` at all.

        True where its `dims` name `dim`, or a group one of whose coordinates
        draws on `dim`.

        Notes
        -----
        - [where a value lives](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
        """
        spec = self.spec_for(attribute)
        return (spec is not None and dim in spec.dims) or any(
            dim in self.groups[g].over.values() for g in self.groups_of(attribute)
        )

    def attributes_for(self, dim: str, **categories: str) -> dict[str, AttributeSpec]:
        """The attributes addressing `dim` a label of it with `categories` carries, by name.

        A category left out matches no trait keyed on it; one its property does
        not list carries nothing.

        Raises
        ------
        ValueError
            If a keyword does not categorize `dim`.

        Notes
        -----
        - [traits](https://energy-models.github.io/datarecord/design/schema/#traits)
        """
        pool = [a for a in self.attributes if self.addresses(a, dim)]
        return {a: self.attributes[a] for a in self._carried(dim, pool, categories)}

    def properties_for(
        self, subject: str, **categories: str
    ) -> dict[str, PropertySpec]:
        """`attributes_for`, for the properties of dim or group `subject`.

        A group is never categorized, so its tuples carry all of its.

        Notes
        -----
        - [traits](https://energy-models.github.io/datarecord/design/schema/#traits)
        """
        specs = self.properties.get(subject, {})
        return {p: specs[p] for p in self._carried(subject, list(specs), categories)}

    def _carried(
        self, subject: str, pool: list[str], categories: dict[str, str]
    ) -> list[str]:
        """Those of `pool` a label of `subject` with `categories` carries, sorted.

        The one narrowing rule `attributes_for` and `properties_for` share, so
        a trait bundling an attribute and a property scopes both alike.
        """
        self.require_categorizing(subject, categories)
        keys = self.categorizing(subject)
        if any(c not in self._categories(subject, k) for k, c in categories.items()):
            return []
        narrowed: set[str] = set()
        names: set[str] = set()
        for trait in self.traits.values():
            for key, on in trait.on.items():
                if key not in keys or not on:
                    continue
                narrowed |= trait.attributes
                if categories.get(key) in on:
                    names |= trait.attributes
        return sorted(n for n in pool if n in names or n not in narrowed)

    def subject_of(self, name: str) -> str | None:
        """The dim or group `name` is a property of, if any."""
        return next((s for s, specs in self.properties.items() if name in specs), None)

    def field_over(self, group: str, dim: str) -> str | None:
        """The one field of `group` over `dim`, if any.

        Raises
        ------
        ValueError
            If several fields of `group` are over `dim`.
        """
        fields = [f for f, d in self.groups[group].over.items() if d == dim]
        if len(fields) > 1:
            msg = (
                f"group {group!r} is over {dim!r} through {fields}, so no one "
                f"label of it decides what a tuple carries"
            )
            raise ValueError(msg)
        return fields[0] if fields else None

    def property_spec(self, name: str) -> PropertySpec | None:
        """Property `name`'s spec, whatever its subject; `None` where it is none."""
        subject = self.subject_of(name)
        return None if subject is None else self.properties[subject][name]

    def owned_per(self, attribute: str) -> frozenset[str]:
        """Which dims a layer owns `attribute` per.

        Derived rather than declared: `AttributeSpec.dims` says which axes the
        attribute may vary over, `partial_dims` the fold key (group columns
        plus the `partial` dims), and ownership is their intersection. A
        dim in `dims` but not the fold key - a non-`partial` value axis like
        `timestep` - is owned whole, so a patch to one of its values restates the
        attribute's entire extent along it (`_owned_whole`).

        Notes
        -----
        - [partial](https://energy-models.github.io/datarecord/design/schema/#partial-the-granularity-of-an-override)
        - [one fold for every axis](https://energy-models.github.io/datarecord/design/read-path/#one-fold-for-every-axis)
        """
        spec = self.attributes.get(attribute)
        if spec is None:
            return frozenset()
        return spec.dims & set(self.partial_dims)

    @property
    def partial_dims(self) -> tuple[str, ...]:
        """The fold key's coordinates, in declaration order.

        The dims and groups a layer may patch per value (`partial`). The fold's
        key is one fixed tuple over all attributes, so it carries every axis *any* layer may patch by value or
        by row, not only those some currently declared attribute varies over. An
        attribute not owned per one of them writes NULL there, the "NULL means
        all values" rule - which also lets a schema declare an axis before any
        attribute uses it.

        Notes
        -----
        - [partial](https://energy-models.github.io/datarecord/design/schema/#partial-the-granularity-of-an-override)
        - [one fold for every axis](https://energy-models.github.io/datarecord/design/read-path/#one-fold-for-every-axis)
        - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
        """
        partial = self.partial or frozenset()
        return tuple(d for d in self.broadcast_dims if d in partial)

    def axis_key(self, dim: str) -> tuple[str, ...]:
        """A dim's axis-table key: `(*parents, dim)`, parents first.

        Parents in declaration order, and transitively - a dim `within` another
        that is itself `within` a third is keyed by all three.

        Notes
        -----
        - [within](https://energy-models.github.io/datarecord/design/schema/#within-an-axis-inside-an-axis)
        """
        seen = _ancestors(dim, {d: s.within for d, s in self.dimensions.items()})
        return (*(d for d in self.dims if d in seen), dim)

    # -- key and column sets (https://energy-models.github.io/datarecord/design/format/#the-long-schema, https://energy-models.github.io/datarecord/design/read-path/#owner-map) -----------------------------------

    @property
    def long_columns(self) -> tuple[str, ...]:
        """The long schema's full column set.

        The *map's* column set, which is uniform across attributes because the
        map is one relation over all of them. An individual file carries only
        its own attribute's columns (`long_columns_for`), and `union_by_name`
        supplies NULL for the rest when the fold unions them here.

        Notes
        -----
        - [the long schema](https://energy-models.github.io/datarecord/design/format/#the-long-schema)
        """
        return (*self.group_columns, *self.dims, *LONG_TAIL)

    @property
    def input_key(self) -> tuple[str, ...]:
        """Inputs-map key columns, compared NULL-safely when folding.

        `partial_dims`, plus `attribute`: a layer may patch one value along a
        `partial` dim or group without restating every other's.

        A coordinate an attribute's own file does not carry reads as NULL,
        which is what makes the key one fixed tuple over attributes whose
        columns differ.

        Notes
        -----
        - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
        - [partial](https://energy-models.github.io/datarecord/design/schema/#partial-the-granularity-of-an-override)
        - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
        """
        return (*self.partial_dims, "attribute")

    def groups_of(self, attribute: str) -> tuple[str, ...]:
        """Which declared groups address `attribute`, input or result, in declaration order.

        An attribute is a connection attribute because its `dims` name the
        `connection` group - not because a separate field says so. That is
        what lets a second group exist without a second field.

        Notes
        -----
        - [addressing](https://energy-models.github.io/datarecord/design/schema/#addressing-dims-x)
        """
        spec = self.spec_for(attribute)
        if spec is None:
            return ()
        return tuple(g for g in self.groups if g in spec.dims)

    def group_key(self, group: str) -> tuple[str, ...]:
        """One group's key coordinates - its struct column's fields - or `()` if undeclared.

        `into` is none of them: the tuple is the key, whatever label it carries.

        Notes
        -----
        - [into](https://energy-models.github.io/datarecord/design/schema/#into-a-group-that-classifies)
        - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
        """
        spec = self.groups.get(group)
        return () if spec is None else spec.key

    @property
    def input_columns(self) -> tuple[str, ...]:
        """The inputs map's full column set.

        Notes
        -----
        - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
        """
        return (*self.input_key, LAYER_COLUMN, *FLAG_COLUMNS)

    # -- typing (https://energy-models.github.io/datarecord/design/format/#the-long-schema, https://energy-models.github.io/datarecord/design/writing/) -------------------------------------------------

    def column_type(self, column: str) -> nw.dtypes.DType | None:
        """The declared type for one column, or None if the schema declares none.

        Covers the structural columns the format fixes, the declared dims and
        groups, every property - a column of its subject's axis or group file
        - and the owner map's two flag structs, whose fields follow the
        schema's dims. A narwhals dtype, translated to DuckDB
        (`duck.DuckTypes`) only where a caller builds a column of it.

        No dim is structural: each is declared, and typed from that
        declaration. So an `Enum` property pins its vocabulary everywhere the
        column is built. An attribute is no column but a long row's value,
        typed by `value_type`.

        A schema declaring no dims at all is "no manifest yet" rather
        than a record to fold, and DuckDB has no empty struct - so the flag
        columns are undeclared there, and a caller building an empty relation
        falls back to `VARCHAR` for a map that will never hold a row.

        Notes
        -----
        - [one schema per record](https://energy-models.github.io/datarecord/design/schema/#one-schema-per-record)
        - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
        """
        if column in STRUCTURAL_TYPES:
            return STRUCTURAL_TYPES[column]
        if column in self.dimensions:
            return self.dimensions[column].dtype
        if column in self.groups:
            return self.group_type(column)
        if column in ("varies", "broadcast"):
            return flag_type(self.broadcast_dims) if self.broadcast_dims else None
        spec = self.property_spec(column)
        return None if spec is None else spec.dtype

    def spec_for(self, attribute: str) -> AttributeSpec | None:
        """`attribute`'s spec, whether it is an input or a result.

        The one lookup that spans both vocabularies, for the questions the long
        schema asks of a stored attribute regardless of which file holds it -
        its dtype and its coordinates. Anything governing how an attribute may
        be *written* asks `attributes` or `results` directly, the two differing
        exactly there.

        Notes
        -----
        - [the long schema](https://energy-models.github.io/datarecord/design/format/#the-long-schema)
        - [outputs](https://energy-models.github.io/datarecord/design/read-path/#outputs)
        """
        return self.attributes.get(attribute) or self.results.get(attribute)

    def value_type(self, attribute: str) -> nw.dtypes.DType | None:
        """The `value` column's type for one attribute, input or result.

        No `ctype`: one attribute is one `<kind>/<attr>.parquet` with one
        `value` column, so the dtype is the attribute's alone. A narwhals
        dtype, translated to DuckDB (`duck.DuckTypes`) only where a caller builds
        a column of it.

        Notes
        -----
        - [the long schema](https://energy-models.github.io/datarecord/design/format/#the-long-schema)
        """
        spec = self.spec_for(attribute)
        return None if spec is None else spec.dtype

    # -- versioning (https://energy-models.github.io/datarecord/design/schema/#versioning) --------------------------------------------------

    def compatible_with(self, other: Schema) -> list[str]:
        """Why layers written under `other` would not read under `self`.

        Empty when the change is compatible: old layers stay readable and only
        `version` moves. The compatible changes are those where NULL already
        means what the new schema needs it to mean, so the broadcast rule absorbs
        them without touching a row.

        Returns
        -------
        list of str
            One reason per incompatibility, empty if there are none.

        Notes
        -----
        - [the broadcast rule](https://energy-models.github.io/datarecord/design/record/#the-broadcast-rule)
        - [versioning](https://energy-models.github.io/datarecord/design/schema/#versioning)
        """
        problems = []

        for dim, was in other.dimensions.items():
            now = self.dimensions.get(dim)
            if now is None:
                problems.append(f"dim {dim!r} removed")
                continue
            if now.dtype != was.dtype:
                problems.append(f"dim {dim!r} dtype {was.dtype} -> {now.dtype}")
            if now.within != was.within:
                problems.append(
                    f"dim {dim!r} nesting changed; the axis key changes shape"
                )

        # Results version like inputs: a layer's `outputs/<attr>.parquet` is
        # unreadable for the same reasons its `inputs/` counterpart would be.
        for kind, mine, theirs in (
            ("attribute", self.attributes, other.attributes),
            ("result", self.results, other.results),
        ):
            for attr, was_spec in theirs.items():
                now_spec = mine.get(attr)
                if now_spec is None:
                    problems.append(f"{kind} {attr!r} removed")
                    continue
                if now_spec.dtype != was_spec.dtype:
                    problems.append(
                        f"{kind} {attr!r} dtype {was_spec.dtype} -> {now_spec.dtype}"
                    )
                narrowed = was_spec.dims - now_spec.dims
                if narrowed:
                    problems.append(
                        f"{kind} {attr!r} no longer varies over {sorted(narrowed)}; "
                        f"rows setting those dims have no valid reading"
                    )

        for dim, specs in other.properties.items():
            for name, was_prop in specs.items():
                now_prop = self.properties.get(dim, {}).get(name)
                if now_prop is None:
                    problems.append(f"property {name!r} of {dim!r} removed")
                elif now_prop.dtype != was_prop.dtype:
                    problems.append(
                        f"property {name!r} of {dim!r} dtype {was_prop.dtype} "
                        f"-> {now_prop.dtype}"
                    )

        problems.extend(self._dropped_by_category(other))

        if other.partial is not None and self.partial is not None:
            lost = other.partial - self.partial
            if lost:
                problems.append(
                    f"{sorted(lost)} no longer `partial`; a layer that patched one "
                    f"value along such an axis is now a partial override of an axis "
                    f"owned whole"
                )
        return problems

    def _dropped_by_category(self, other: Schema) -> list[str]:
        """Each category of `other` whose labels no longer carry an attribute or property under `self`.

        Incompatible for the reason a narrowed `dims` is: the rows are still
        in the file, now unreadable for those labels. Each category is checked
        alone, every other categorizing property unset: traits combine as a
        union, so a combination losing an attribute has a category losing it
        alone. A property `self` no longer categorizes is skipped, its removal
        or retyping being reported on its own.
        """
        problems = []
        for dim in other.dimensions:
            mine = self.categorizing(dim)
            for key in other.categorizing(dim):
                if key not in mine:
                    continue
                for category in other._categories(dim, key):
                    at = {key: category}
                    was = {*other.attributes_for(dim, **at)}
                    was |= {*other.properties_for(dim, **at)}
                    now = {*self.attributes_for(dim, **at)}
                    now |= {*self.properties_for(dim, **at)}
                    dropped = sorted(was - now)
                    if dropped:
                        problems.append(
                            f"category {category!r} of {key!r} on {dim!r} no "
                            f"longer carries {dropped}; rows written for its "
                            f"labels have no valid reading"
                        )
        return problems


def _ancestors(dim: str, within: dict[str, frozenset[str]]) -> set[str]:
    """Every dim `dim` is transitively `within`."""
    seen: set[str] = set()
    stack = list(within.get(dim, ()))
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        stack.extend(within.get(node, ()))
    return seen
