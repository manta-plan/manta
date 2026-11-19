# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The OGSchema manifest: a datarecord `Schema` derived from one SiennaSchemas release.

The pydantic models of `power_openapi_models` are the source, so the manifest follows the
release that package was generated from. Each component type has a home dim. A scalar field
becomes a property of that dim if it is text and an attribute over it if it is a number. A
nested object becomes one name per leaf, its path joined with `__`, and a union contributes
the leaves of every variant, told apart by its discriminator property.
"""

import enum
import re
import types
import typing
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from importlib.resources import files
from json import loads
from typing import Any

import power_openapi_models as pom
from datarecord import AttributeSpec, Dimension, PropertySpec, Schema
from power_openapi_models import core, infrastructure_core, investments, operations
from pydantic import BaseModel, RootModel
from pydantic.fields import FieldInfo

SEP = "__"
FORMAT = "ogschema"
VERSION = pom.__schema_version__.removeprefix("v")
DOCUMENTS = ("SystemDocument", "PortfolioDocument")
MODULES = (operations.models, investments.models, core.models, infrastructure_core.models)

ENTITY = "entity"
SUPPLEMENTAL = "supplemental_attribute"
COMPONENT_TYPE = "component_type"
SNAPSHOT = "snapshot"
PERIOD = "period"
TIMESTEP = "timestep"
SCENARIO = "scenario"
COHORT = "cohort"
TOPOLOGY_HOMES = {
    "ACBus": "bus",
    "DCBus": "bus",
    "Arc": "arc",
    "Area": "area",
    "LoadZone": "load_zone",
}
IDENTITY = frozenset({"id", "name"})
REFERENCES = {
    "bus": "bus",
    "dc_bus": "bus",
    "remote_regulated_bus": "bus",
    "remote_regulated_bus_from": "bus",
    "remote_regulated_bus_to": "bus",
    "regulated_bus": "bus",
    "star_bus": "bus",
    "start_node": "bus",
    "end_node": "bus",
    "Arc.from_id": "bus",
    "Arc.to_id": "bus",
    "arc": "arc",
    "area": "area",
    "from_area": "area",
    "to_area": "area",
    "load_zone": "load_zone",
}
LIST_REFERENCES = {
    "region": {ENTITY: ENTITY, "bus": "bus"},
    "downstream_turbines": {"reservoir": ENTITY, "turbine": ENTITY},
}
ASSOCIATIONS = {
    "entity_supplemental_attribute": {ENTITY: ENTITY, SUPPLEMENTAL: SUPPLEMENTAL},
    "bus_supplemental_attribute": {"bus": "bus", SUPPLEMENTAL: SUPPLEMENTAL},
    "requirement_association": {"requirement": ENTITY, ENTITY: ENTITY},
}
CURVE_SLOPE = "variable_operation_cost__value_curve__function_data__proportional_term"
TIME_SERIES = {
    "max_active_power": ENTITY,
    "inflow": ENTITY,
    f"operation_cost{SEP}{CURVE_SLOPE}": ENTITY,
    f"operation_costs{SEP}{CURVE_SLOPE}": ENTITY,
}
TIME_SERIES_PREFIX = "ts" + SEP
TIME_SERIES_REFERENCE = re.compile(r"(association_id|_time_series)$")
UNIT = re.compile(r"Units: (.+?)\.?$")
SCALARS = {float: "float", int: "int", bool: "bool"}


@dataclass(frozen=True)
class Leaf:
    """One scalar a component type holds, at the end of a path of nested fields."""

    name: str
    kind: str
    dtype: str | None = None
    enum: type[enum.Enum] | None = None
    target: str | None = None
    required: bool = False
    when: tuple[tuple[str, str], ...] = ()
    unit: str | None = None
    reason: str | None = None


@cache
def bundle(document: str) -> dict[str, Any]:
    """The strict JSON Schema bundle of one document, as the release ships it."""
    path = files(pom) / "bundles" / VERSION / f"{document}.json"
    return loads(path.read_text())


@cache
def supplemental_types() -> frozenset[str]:
    """Every supplemental attribute type of the release."""
    names: set[str] = set()
    for document in DOCUMENTS:
        items = bundle(document)["properties"]["supplemental_attributes"]["items"]
        names.update(ref["$ref"].rsplit("/", 1)[-1] for ref in items["anyOf"])
    return frozenset(names)


def model(component_type: str) -> type[BaseModel] | None:
    """The pydantic model of a component type, or None for a type outside `MODULES`."""
    for module in MODULES:
        if component_type in vars(module):
            return vars(module)[component_type]
    return None


@cache
def all_types() -> tuple[str, ...]:
    """Every component and supplemental attribute type of the release, bar Dynamics."""
    names = set(supplemental_types())
    for document in DOCUMENTS:
        names.update(bundle(document)["properties"]["components"]["properties"])
    return tuple(sorted(name for name in names if model(name) is not None))


def home(component_type: str) -> str:
    """The dim whose labels are the components of this type."""
    if component_type in supplemental_types():
        return SUPPLEMENTAL
    return TOPOLOGY_HOMES.get(component_type, ENTITY)


def qualified(dim: str, name: str) -> str:
    """The record-wide name of an attribute: bare over `entity`, prefixed by any other dim."""
    return name if dim == ENTITY else dim + SEP + name


def enum_dim(cls: type[enum.Enum]) -> str:
    """The name of the `one_of` dim that lists an enum's values."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", cls.__name__).lower()


def _union(annotation: Any) -> tuple[list[Any], bool, str | None]:
    origin = typing.get_origin(annotation)
    if origin is typing.Annotated:
        return _union(typing.get_args(annotation)[0])
    if origin in (typing.Union, types.UnionType):
        alternatives: list[Any] = []
        optional = False
        for arg in typing.get_args(annotation):
            if arg is type(None):
                optional = True
                continue
            inner, inner_optional, _ = _union(arg)
            alternatives += inner
            optional |= inner_optional
        return alternatives, optional, None
    if isinstance(annotation, type) and issubclass(annotation, RootModel):
        root = annotation.model_fields["root"]
        alternatives, optional, _ = _union(root.annotation)
        return alternatives, optional, _discriminator(root)
    return [annotation], False, None


def _discriminator(info: FieldInfo) -> str | None:
    return info.discriminator if isinstance(info.discriminator, str) else None


def _is_model(annotation: Any) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


def _unit(info: FieldInfo) -> str | None:
    match = UNIT.search(info.description or "")
    return match.group(1).strip() if match else None


def _scalar(component_type: str, field: str, name: str, annotation: Any) -> Leaf:
    origin = typing.get_origin(annotation)
    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        if all(isinstance(member.value, str) for member in annotation):
            return Leaf(name, "property", "str", enum=annotation)
        return Leaf(name, "attribute", "int")
    if origin is typing.Literal or annotation in (str, datetime):
        return Leaf(name, "property", "str")
    if origin is dict or annotation is typing.Any:
        return Leaf(name, "property", "str")
    if annotation is int:
        target = REFERENCES.get(f"{component_type}.{field}", REFERENCES.get(field))
        if target is not None and SEP not in name:
            return Leaf(name, "reference", target=target)
        if TIME_SERIES_REFERENCE.search(field):
            return Leaf(name, "unmapped", reason="reference to a time series")
    if annotation in SCALARS:
        return Leaf(name, "attribute", SCALARS[annotation])
    if origin is list:
        (inner,), _, _ = _union(typing.get_args(annotation)[0])
        if _is_model(inner) and set(inner.model_fields) == {"x", "y"}:
            return Leaf(name, "curve", "float")
        if inner is int and field in LIST_REFERENCES and SEP not in name:
            return Leaf(name, "list_reference")
        if inner is str or (isinstance(inner, type) and issubclass(inner, enum.Enum)):
            return Leaf(name, "property", "str")
        return Leaf(name, "unmapped", reason=f"list of {getattr(inner, '__name__', inner)}")
    return Leaf(name, "unmapped", reason=f"type {annotation}")


def leaves(
    component_type: str,
    cls: type[BaseModel] | None = None,
    prefix: str = "",
    required: bool = True,
    when: tuple[tuple[str, str], ...] = (),
    unit: str | None = None,
) -> Iterator[Leaf]:
    """Every leaf of a component type, with the union variants it needs to be required."""
    cls = cls or model(component_type)
    for field, info in cls.model_fields.items():
        if not prefix and field in IDENTITY:
            continue
        name = prefix + (info.alias or field)
        alternatives, optional, discriminator = _union(info.annotation)
        discriminator = _discriminator(info) or discriminator
        needed = required and not optional and info.is_required()
        tagged = discriminator is not None and all(_is_model(alt) for alt in alternatives)
        field_unit = _unit(info) or unit
        for alternative in alternatives:
            if not _is_model(alternative):
                leaf = _scalar(component_type, field, name, alternative)
                lone = len(alternatives) == 1
                yield Leaf(
                    **{**vars(leaf), "required": needed and lone, "when": when, "unit": field_unit}
                )
                continue
            tag = name + SEP + discriminator if tagged else None
            if tag is not None:
                (value,) = typing.get_args(alternative.model_fields[discriminator].annotation)
                yield Leaf(tag, "property", "str", required=needed, when=when)
                inner_when = (*when, (tag, value))
            else:
                inner_when = when
            inner_required = needed and (tagged or len(alternatives) == 1)
            inner = leaves(
                component_type, alternative, name + SEP, inner_required, inner_when, field_unit
            )
            yield from (leaf for leaf in inner if leaf.name != tag)


def _property(specs: set[Leaf]) -> PropertySpec:
    targets = {leaf.target for leaf in specs}
    enums = {leaf.enum for leaf in specs}
    if len(targets) == 1 and None not in targets:
        return PropertySpec(one_of=targets.pop())
    if len(enums) == 1 and None not in enums and targets == {None}:
        return PropertySpec(one_of=enum_dim(enums.pop()))
    return PropertySpec(dtype="str")


def _attribute(dim: str, specs: set[Leaf]) -> AttributeSpec:
    dtypes = {leaf.dtype for leaf in specs}
    if dtypes <= {"float", "int"}:
        dtype = "int" if dtypes == {"int"} else "float"
    elif len(dtypes) == 1:
        (dtype,) = dtypes
    else:
        raise ValueError(f"attribute {next(iter(specs)).name!r} mixes the dtypes {sorted(dtypes)}")
    units = {leaf.unit for leaf in specs}
    curve = any(leaf.kind == "curve" for leaf in specs)
    unit = units.pop() if len(units) == 1 else None
    return AttributeSpec(dtype=dtype, dims={dim}, breakpoints=curve, unit=unit)


def manifest(
    component_types: Iterable[str] | None = None,
    time_series: Mapping[str, str] = TIME_SERIES,
    periods: bool = False,
) -> Schema:
    """The datarecord schema of the given component types, every type of the release by default.

    `time_series` maps the name of each time series to the dim that owns it. A series is the
    attribute `ts__<name>` over that dim and `snapshot`, in the units SiennaSchemas stores it.
    A name with a path is the time-varying form of the field at that path. With `periods`, a
    snapshot is a timestep in an investment period: `snapshot` is a multi-dim over the dims
    `period` and `timestep`. The multi-dim `cohort` then lists the periods each technology is
    built in, as an entity and a build year, for the values that differ by build year.
    `Schema.meta` lists, per type, its home dim, the names it
    requires and the fields left out.
    """
    selected = tuple(sorted(component_types or all_types()))
    unknown = [name for name in selected if model(name) is None]
    if unknown:
        raise ValueError(f"SiennaSchemas {VERSION} has no component type named {unknown}")
    homes = (ENTITY, SUPPLEMENTAL, *dict.fromkeys(TOPOLOGY_HOMES.values()))
    properties: dict[str, dict[str, set[Leaf]]] = {dim: {} for dim in homes}
    attributes: dict[str, tuple[str, set[Leaf]]] = {}
    list_references: set[str] = set()
    enums: dict[str, type[enum.Enum]] = {}
    meta_types: dict[str, dict[str, Any]] = {}
    for component_type in selected:
        dim = home(component_type)
        required: list[dict[str, Any]] = []
        unmapped: dict[str, str] = {}
        for leaf in dict.fromkeys(leaves(component_type)):
            if leaf.kind == "unmapped":
                unmapped[leaf.name] = leaf.reason
                continue
            if leaf.kind == "list_reference":
                list_references.add(leaf.name)
                continue
            if leaf.kind in ("property", "reference"):
                properties[dim].setdefault(leaf.name, set()).add(leaf)
                name = leaf.name
            else:
                name = qualified(dim, leaf.name)
                attributes.setdefault(name, (dim, set()))[1].add(leaf)
            if leaf.required:
                required.append({"name": name, "kind": leaf.kind, "when": dict(leaf.when)})
        meta_types[component_type] = {"home": dim, "required": required, "unmapped": unmapped}
    property_specs = {
        dim: {name: _property(specs) for name, specs in sorted(named.items())}
        for dim, named in properties.items()
    }
    for dim in property_specs:
        property_specs[dim][COMPONENT_TYPE] = PropertySpec(one_of=COMPONENT_TYPE)
    for named in properties.values():
        for specs in named.values():
            for leaf in specs:
                if leaf.enum is not None:
                    enums[enum_dim(leaf.enum)] = leaf.enum
    used_enums = {
        spec.one_of for named in property_specs.values() for spec in named.values() if spec.one_of
    }
    dimensions = {dim: Dimension() for dim in property_specs}
    dimensions[SNAPSHOT] = Dimension(dtype="datetime")
    if periods:
        dimensions[PERIOD] = Dimension(dtype="int", unit="year")
        dimensions[TIMESTEP] = Dimension(dtype="datetime")
        dimensions[SNAPSHOT] = Dimension(over=[PERIOD, TIMESTEP])
        dimensions[COHORT] = Dimension(over={ENTITY: ENTITY, "build_year": PERIOD})
    dimensions[COMPONENT_TYPE] = Dimension(one_of=list(selected))
    for name, cls in sorted(enums.items()):
        if name in used_enums:
            dimensions[name] = Dimension(one_of=[member.value for member in cls])
    for name in sorted(list_references):
        if set(LIST_REFERENCES[name].values()) <= set(dimensions):
            dimensions[name] = Dimension(over=LIST_REFERENCES[name])
    for name, over in ASSOCIATIONS.items():
        if set(over.values()) <= set(dimensions):
            dimensions[name] = Dimension(over=over)
    attribute_specs = {name: _attribute(dim, specs) for name, (dim, specs) in attributes.items()}
    for name, dim in time_series.items():
        if dim in dimensions and (SEP not in name or qualified(dim, name) in attribute_specs):
            series = qualified(dim, TIME_SERIES_PREFIX + name)
            attribute_specs[series] = AttributeSpec(dtype="float", dims={dim, SNAPSHOT})
    time = {SNAPSHOT, PERIOD, TIMESTEP}
    partial = {name for name, dim in dimensions.items() if dim.one_of is None} - time
    return Schema(
        dimensions=dimensions,
        properties=property_specs,
        attributes=dict(sorted(attribute_specs.items())),
        partial=partial,
        meta={"format": FORMAT, "ogschema_version": VERSION, "types": meta_types},
    )


def extended(
    schema: Schema,
    attributes: Mapping[str, AttributeSpec] | None = None,
    properties: Mapping[str, Mapping[str, PropertySpec]] | None = None,
    meta: Mapping[str, Any] | None = None,
    dimensions: Mapping[str, Dimension] | None = None,
) -> Schema:
    """A copy of `schema` that also declares `attributes`, `properties` and `dimensions`.

    `meta` is merged in. It is how a record gains the `ext__` names a framework needs beside
    the OGSchema ones. A name `schema` declares already keeps its spec, unless an attribute
    gains a dim.
    """
    merged = {dim: dict(named) for dim, named in schema.properties.items()}
    for dim, named in (properties or {}).items():
        merged[dim] = {**named, **merged.get(dim, {})}
    widened = dict(schema.attributes)
    for name, spec in (attributes or {}).items():
        held = widened.get(name)
        dims = spec.dims if held is None else held.dims | spec.dims
        widened[name] = (held or spec).model_copy(update={"dims": dims})
    fields = {
        "dimensions": {**schema.model_dump()["dimensions"], **(dimensions or {})},
        "attributes": widened,
        "properties": merged,
        "meta": {**schema.meta, **(meta or {})},
    }
    return schema.model_validate({**schema.model_dump(), **fields})
