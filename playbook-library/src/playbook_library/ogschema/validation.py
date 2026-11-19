# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Check an OGSchema record against the fields SiennaSchemas requires of each component type."""

from collections.abc import Mapping
from functools import reduce
from typing import Any

from datarecord import RecordLike
from duckdb import DuckDBPyRelation

from playbook_library.ogschema.manifest import COMPONENT_TYPE

COLUMNS = "NULL::VARCHAR AS component_type, NULL::VARCHAR AS label, NULL::VARCHAR AS name"
PROPERTIES = ("property", "reference")


def _text(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _held(record: RecordLike, dim: str, attributes: set[str]) -> DuckDBPyRelation:
    """Return each label of `dim` with the names of `attributes` it has a value for."""
    rows = [
        record.attributes[name]
        .filter("value IS NOT NULL")
        .project(f'"{dim}" AS label, {_text(name)} AS name')
        for name in sorted(attributes)
    ]
    if not rows:
        return record.con.sql("SELECT NULL::VARCHAR AS label, NULL::VARCHAR[] AS names WHERE false")
    return reduce(DuckDBPyRelation.union, rows).aggregate("label, list(DISTINCT name) AS names")


def _lacking(requirements: list[Mapping[str, Any]], valued: set[str], everywhere: set[str]) -> str:
    """Return SQL for the names among `requirements` that a row has no value for, as a list."""
    checks = []
    for requirement in requirements:
        name = requirement["name"]
        if requirement["kind"] in PROPERTIES:
            checks.append(f'CASE WHEN p."{name}" IS NULL THEN {_text(name)} END')
        elif name in everywhere:
            continue
        elif name in valued:
            checks.append(
                f"CASE WHEN NOT list_contains(COALESCE(h.names, []), {_text(name)})"
                f" THEN {_text(name)} END"
            )
        else:
            checks.append(_text(name))
    return f"list_filter([{', '.join(dict.fromkeys(checks))}]::VARCHAR[], lambda x: x IS NOT NULL)"


def _variant(when: tuple[tuple[str, str], ...], lacking: str) -> str:
    """Return SQL for `lacking`, the names a row lacks, if the row is of the variant `when`."""
    fits = [f'p."{name}" = {_text(value)}' for name, value in when]
    return f"CASE WHEN {' AND '.join(fits) or 'true'} THEN {lacking} ELSE [] END"


def violations(record: RecordLike) -> DuckDBPyRelation:
    """Return the names each component of `record` lacks that its OGSchema type requires.

    The relation has the columns `component_type`, `label` and `name`, a row per required
    name without a value. A field of one variant of a union is required only of the
    components whose discriminator properties name that variant.
    """
    types = record.schema.meta["types"]
    flags = record.flags()
    parts: list[DuckDBPyRelation] = []
    for dim in sorted({described["home"] for described in types.values()}):
        properties = record.properties[dim]
        named = properties.project(COMPONENT_TYPE).distinct().fetchall()
        valued = {name for name in flags if dim in record.schema.attributes[name].dims}
        everywhere = {name for name in valued if dim in flags[name].broadcast}
        held = _held(record, dim, valued - everywhere).set_alias("h")
        joined = properties.set_alias("p").join(held, f'p."{dim}" = h.label', how="left")
        for component_type in sorted(str(label) for (label,) in named if label is not None):
            variants: dict[tuple[tuple[str, str], ...], list[Mapping[str, Any]]] = {}
            for requirement in types[component_type]["required"]:
                variants.setdefault(tuple(requirement["when"].items()), []).append(requirement)
            lacking = [
                _variant(when, _lacking(requirements, valued, everywhere))
                for when, requirements in variants.items()
            ]
            names = f"list_distinct(flatten([{', '.join(lacking)}]::VARCHAR[][]))"
            columns = f'{_text(component_type)} AS component_type, p."{dim}" AS label'
            rows = joined.filter(f"p.{COMPONENT_TYPE} = {_text(component_type)}")
            parts.append(rows.project(f"{columns}, unnest({names}) AS name"))
    if not parts:
        return record.con.sql(f"SELECT {COLUMNS} WHERE false")
    return reduce(DuckDBPyRelation.union, parts).distinct()
