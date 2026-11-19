# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Block settings that name a property or coordinate of the record a block runs on.

E.g., `Annotated[str, RecordProperty("bus")]` names a bus property (`zone`) and
`Annotated[str, RecordDimCoord("carrier")]` names a carrier (`H2`).
These are checked against a record when it is passed as validation context:
`context={"record": RecordContents(...)}`.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import ClassVar, Literal

from annotated_types import GroupedMetadata
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationInfo
from pydantic.fields import FieldInfo

RECORD_MARKER = "x-manta-record"
"""Marks a setting that names a property or coordinate of a record's dimension."""

RecordRefKind = Literal["property", "coordinate", "creates"]
"""What a record reference names: an existing property, a coordinate, or a new property."""


class RecordContents(BaseModel):
    """Names in a record that settings can refer to, per dimension.

    Built by a block library that can read records
    (e.g., `playbook_library.datarecord_helpers.record_contents`),
    so that the playbook package can check settings without reading a record itself.
    """

    model_config = ConfigDict(frozen=True)

    coordinates: dict[str, frozenset[str]] = {}
    """Coordinates of each dimension, e.g. `{"carrier": {"AC", "H2"}}`.
    A dimension missing here has no coordinates, so any setting naming one is refused.
    """

    properties: dict[str, frozenset[str]] = {}
    """Property names of each dimension, e.g. `{"bus": {"zone", "x", "y"}}`.
    A dimension missing here has no properties, so any setting naming one is refused.
    """

    def options(self, kind: RecordRefKind, dim: str) -> frozenset[str]:
        """Get the names a setting of `kind` may take for dimension `dim`.

        Args:
            kind (RecordRefKind):
                what the setting names. `property` and `creates` both draw on property names.
            dim (str): dimension the setting refers to (e.g., `bus`).

        Returns:
            frozenset[str]: allowed names. Empty if the record does not describe `dim`.
        """
        names = self.coordinates if kind == "coordinate" else self.properties
        return names.get(dim, frozenset())

    def with_property(self, dim: str, name: str) -> "RecordContents":
        """Add a property to a copy of these contents.

        Used to pass a property created by one playbook step (see `CreatesProperty`)
        on to later steps.

        Args:
            dim (str): dimension that gains the property (e.g., `snapshot`).
            name (str): name of the new property (e.g., `seg_730`).

        Returns:
            RecordContents: copy including the new property.
        """
        properties = {**self.properties, dim: self.options("property", dim) | {name}}
        return self.model_copy(update={"properties": properties})


@dataclass(frozen=True)
class _RecordRef(GroupedMetadata):
    """Shared record check and schema marker of the record reference types."""

    dim: str
    KIND: ClassVar[RecordRefKind]

    def __iter__(self) -> Iterator[object]:
        """Yield the validator and schema marker for pydantic to apply to the setting."""
        yield AfterValidator(self._check)
        yield self._marker()

    def _marker(self) -> FieldInfo:
        """Get the JSON schema marker naming this reference's kind and dimension."""
        return Field(json_schema_extra={RECORD_MARKER: {"kind": self.KIND, "dim": self.dim}})

    def _check(self, value: str, info: ValidationInfo) -> str:
        """Check `value` against the record in the validation context, if there is one."""
        if not info.context or "record" not in info.context:
            return value
        options = info.context["record"].options(self.KIND, self.dim)
        if value not in options:
            raise ValueError(
                f"{value!r} is not a {self.KIND} of {self.dim!r} in the record; "
                f"choose from {sorted(options)}"
            )
        return value


class RecordProperty(_RecordRef):
    """Mark a setting as naming a property of dimension `dim` (e.g., `zone` of `bus`).

    Use as `Annotated[str, RecordProperty("bus")]`.
    Without a record in the validation context, any string is accepted.
    """

    KIND = "property"


class RecordDimCoord(_RecordRef):
    """Mark a setting as naming a coordinate of dimension `dim` (e.g., `H2` of `carrier`).

    Use as `Annotated[str, RecordDimCoord("carrier")]`; in a list, each item is checked.
    Without a record in the validation context, any string is accepted.
    """

    KIND = "coordinate"


class CreatesProperty(_RecordRef):
    """Mark a setting as naming a new property that the block adds to dimension `dim`.

    E.g., a time partition block's `name: seg_730` adds the snapshot property `seg_730`,
    which later playbook steps can then refer to with `RecordProperty("snapshot")`.
    The setting itself is not checked against the record, since the name is new.
    """

    KIND = "creates"

    def __iter__(self) -> Iterator[object]:
        """Yield only the schema marker, since a new name has nothing to be checked against."""
        yield self._marker()


def record_schema(schema: dict, contents: RecordContents) -> dict:
    """Replace record references in a block's settings schema with the values a record allows.

    Each `RecordProperty` / `RecordDimCoord` setting becomes `{"type": "string", "enum": [...]}`
    (on `items` for a list), so a form can offer the values without knowing about Manta's markers.
    `CreatesProperty` settings stay free text.

    Args:
        schema (dict): block settings JSON schema, as described in a catalogue. Not modified.
        contents (RecordContents): names available to the playbook step that the schema belongs to.

    Returns:
        dict: copy of `schema` with no `x-manta-record` markers.
    """
    return _with_options(schema, contents)


def _with_options(node: object, contents: RecordContents) -> object:
    """Replace the record reference markers in a JSON schema node and all nodes below it."""
    if isinstance(node, list):
        return [_with_options(item, contents) for item in node]
    if not isinstance(node, dict):
        return node
    if RECORD_MARKER not in node:
        return {key: _with_options(value, contents) for key, value in node.items()}
    marker = node[RECORD_MARKER]
    plain = {key: value for key, value in node.items() if key != RECORD_MARKER}
    if marker["kind"] == "creates":
        return plain
    options = sorted(contents.options(marker["kind"], marker["dim"]))
    return {**plain, "type": "string", "enum": options}


def referenced_dims(schema: object, kind: RecordRefKind) -> frozenset[str]:
    """Find the dimensions that record references of a given kind refer to.

    Used to limit record reads to what the settings need,
    since a dimension can have many thousands of coordinates.

    Args:
        schema (object): block settings JSON schema, or any part of one.
        kind (RecordRefKind): record reference kind to collect.

    Returns:
        frozenset[str]: dimension names. Empty if no setting of `kind` exists.
    """
    if isinstance(schema, list):
        return frozenset().union(*(referenced_dims(item, kind) for item in schema))
    if not isinstance(schema, dict):
        return frozenset()
    marker = schema.get(RECORD_MARKER)
    found = {marker["dim"]} if marker is not None and marker["kind"] == kind else set()
    return frozenset(found).union(*(referenced_dims(value, kind) for value in schema.values()))


def created_properties(schema: dict, values: object) -> Iterator[tuple[str, str]]:
    """Find the properties that a block adds to the record when run with the given settings.

    Only `CreatesProperty` settings given in `values` count; defaults are not read.

    Args:
        schema (dict): block settings JSON schema, as described in a catalogue.
        values (object): block settings, as given in a playbook config.

    Yields:
        tuple[str, str]: dimension and name of each new property (e.g., `("snapshot", "seg_730")`).
    """
    definitions = schema.get("$defs", {})

    def walk(node: dict, value: object) -> Iterator[tuple[str, str]]:
        """Walk `value` down `node`, following `$ref`, `anyOf`, object properties and list items."""
        if "$ref" in node:
            node = definitions[node["$ref"].rpartition("/")[2]]
        marker = node.get(RECORD_MARKER)
        if marker is not None and marker["kind"] == "creates" and isinstance(value, str):
            yield marker["dim"], value
        for branch in node.get("anyOf", []):
            yield from walk(branch, value)
        if isinstance(value, dict):
            for key, child in node.get("properties", {}).items():
                if key in value:
                    yield from walk(child, value[key])
        if isinstance(value, list) and "items" in node:
            for item in value:
                yield from walk(node["items"], item)

    return walk(schema, values)
