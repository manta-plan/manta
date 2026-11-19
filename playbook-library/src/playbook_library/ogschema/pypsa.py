# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The OGSchema tool: a PyPSA network as an OGSchema record, and the network of such a record.

Both directions walk the table in `mapping` and run as SQL on the record's connection. A
network is read from its own frames, registered there, and a record from one wide table per
home dim. What PyPSA holds and OGSchema has no field for is kept under `ext__pypsa__`, and a
solve's results under `ext__pypsa_result__`, so a network comes back as it went in.

One PyPSA component is not always one OGSchema component. A store, the bus it is on and the
two links that charge and discharge it are one storage technology, and a load-shedding
generator is the cost of interrupting the load on its bus. `classify` marks such parts, and
`build` makes the PyPSA components from them again.

A network with scenarios keeps them. Its static values are those of every scenario, and a
series that differs between scenarios has rows per scenario over the dim `scenario`, whose
labels are the names of the scenarios. Their weights are `scenario__ext__pypsa__weighting_weight`.

A network with investment periods keeps them. Its `snapshot` is a timestep in a period. The
extendable components that are built in a period each and named for it, the cohorts, are one
technology in the record: the multi-dim `cohort` lists its build years, and the values that
differ by build year are attributes over it. `build` makes a component per build year again.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict
from functools import cache, cached_property, reduce
from typing import Any, NamedTuple
from uuid import uuid4

import numpy as np
import pandas as pd
import pyarrow as pa
import pypsa
import shapely
from datarecord import (
    AttributeSpec,
    Dimension,
    Flags,
    LazyRelations,
    PropertySpec,
    RecordLike,
    Schema,
)
from datarecord.resolve.fold import Fold
from datarecord.schema.schema import unpacked
from datarecord.tools.base import Requirements, UnsupportedRecordError
from duckdb import DuckDBPyConnection, DuckDBPyRelation
from pandas.api.types import is_bool_dtype, is_float_dtype, is_integer_dtype

from playbook_library.ogschema.manifest import (
    COHORT,
    ENTITY,
    FORMAT,
    PERIOD,
    SCENARIO,
    SEP,
    SNAPSHOT,
    SUPPLEMENTAL,
    TIME_SERIES_PREFIX,
    TIMESTEP,
    extended,
    home,
    manifest,
    qualified,
)
from playbook_library.ogschema.mapping import (
    BRANCHES,
    BUSES,
    CAPACITY_LIMIT,
    CARRIED,
    CO2_PER_MWH,
    COHORTS,
    DEVICE_FRAMES,
    ENTRIES,
    EXT_DTYPES,
    EXTENDABLE,
    JOINS,
    KEPT,
    LABEL_DTYPES,
    LIMITED,
    NO_COHORTS,
    NOMINAL,
    POINT,
    READ_REFUSALS,
    ROLES,
    SHAPES,
    SOURCES,
    WRITE_REFUSALS,
    Entry,
    Technology,
)

NAME = "OGSchema"
GROUP = "ext" + SEP + "technology_group"
INVENTED = "ext" + SEP + "invented_candidate"
TYPED = {
    "og_type": "COALESCE(power_systems_type, component_type)",
    "og_prime_mover_type": "prime_mover_type",
    "og_fuel": "fuel",
    "og_storage_tech": "storage_tech",
    "og_technology_group": GROUP,
    "og_part": "NULL",
    "og_entity": "NULL",
}
OG_COLUMNS = tuple(TYPED)
FIELDS = {
    "og_type": "og_type",
    "prime_mover_type": "og_prime_mover_type",
    "fuel": "og_fuel",
    "storage_tech": "og_storage_tech",
    "group": "og_technology_group",
}
EXT = "ext" + SEP + "pypsa" + SEP
RESULT = "ext" + SEP + "pypsa_result" + SEP
SERIES = TIME_SERIES_PREFIX + EXT
WEIGHTING = EXT + "weighting_"
WEIGHTINGS = ("objective", "stores", "generators")
PERIOD_WEIGHTINGS = ("objective", "years")
SCENARIO_WEIGHT = qualified(SCENARIO, WEIGHTING + "weight")
TIMES = {False: "TIMESTAMP", True: f"STRUCT({PERIOD} BIGINT, {TIMESTEP} TIMESTAMP)"}
META = "pypsa"
COMPONENTS = "components"
IGNORED = frozenset({"Carrier", "LineType", "TransformerType", "SubNetwork"})
LABELS = {"og_technology_group": GROUP}
DERIVED = frozenset({"name", "_pos", "carrier", *OG_COLUMNS}) - LABELS.keys()
EXTRA_PORT = r"^bus([2-9]|\d\d+)$"
SHEDDING = "InterruptiblePowerLoad"
EMPTY_SERIES = "SELECT NULL::VARCHAR AS name, NULL::DOUBLE AS value WHERE false"
EXPANSION_LIMIT = "tech_capacity_expansion_limit"
VINTAGE = r"^(?P<label>.*)-(?P<year>\d+)$"
COHORT_LABEL = "struct_pack(entity := {entity}, build_year := CAST(_built AS BIGINT))"
BY_YEAR = """(
SELECT c.*, k.build_year AS _built, k.{column} AS _by_year
FROM {source}_cohorts k JOIN {source} c ON c.name = k.label
)"""
ROW_GROUP = 122_880
MELTED = """(
SELECT * EXCLUDE (_values, _labels), unnest(_values) AS value, unnest(_labels) AS snapshot
FROM (
    SELECT c.*, d."values" AS _values, l._labels
    FROM {series} d JOIN {source} c ON c.name = d.name,
        (SELECT list(snapshot ORDER BY _pos) AS _labels FROM snapshots) l
)
)"""
NO_EXTENDABLES = (
    "SELECT NULL::VARCHAR AS name, NULL::VARCHAR AS carrier, NULL::VARCHAR AS bus,"
    " 0 AS build_year, 0.0 AS lifetime, NULL::VARCHAR AS og_carrier, false AS part WHERE false"
)
PROFILE = qualified(ENTITY, TIME_SERIES_PREFIX + "max_active_power")
ASSOCIATIONS = (
    "region",
    "bus_supplemental_attribute",
    "entity_supplemental_attribute",
    "downstream_turbines",
    "requirement_association",
)
UNTYPED = ("power_systems_type", "prime_mover_type", "fuel", "storage_tech")
PARTS_OF_A_CARRIER = ("og_prime_mover_type", "og_fuel", "og_storage_tech", "og_technology_group")
SUPPLEMENTAL_TABLE = """
SELECT w.*, {co2} AS _co2, b.bus AS _bus, {untyped}
FROM ({wide}) w
LEFT JOIN (
    SELECT m.bus_supplemental_attribute.supplemental_attribute AS label,
        any_value(m.bus_supplemental_attribute.bus) AS bus
    FROM {t}_bus_supplemental_attribute m GROUP BY 1
) b ON b.label = w.supplemental_attribute
"""
BUS_TABLE = """
SELECT w.*, g.geo_json AS _geo_json, {untyped}
FROM ({wide}) w
LEFT JOIN (
    SELECT m.bus_supplemental_attribute.bus AS bus, any_value(s.geo_json) AS geo_json
    FROM {t}_bus_supplemental_attribute m
    JOIN {t}_supplemental_attribute s
        ON s.supplemental_attribute = m.bus_supplemental_attribute.supplemental_attribute
    WHERE s.component_type = 'GeographicInfo' AND {point}
    GROUP BY 1
) g ON g.bus = w.bus
"""
ENTITY_TABLE = """
WITH wide AS ({wide}),
described AS MATERIALIZED ({described})
SELECT d.*, lim.carrier AS _limited_carrier, COALESCE(lim.carriers, 0) AS _limited_carriers,
    lim.bus AS _limited_bus, COALESCE(lim.buses, 0) AS _limited_buses
FROM described d
LEFT JOIN (
    SELECT m.requirement_association.requirement AS requirement,
        any_value(e._carrier) AS carrier, count(DISTINCT e._carrier) AS carriers,
        any_value(COALESCE(e._region_bus, e.start_node)) AS bus,
        count(DISTINCT COALESCE(e._region_bus, e.start_node)) AS buses
    FROM {t}_requirement_association m
    JOIN described e ON e.entity = m.requirement_association.entity
    GROUP BY 1
) lim ON lim.requirement = d.entity
"""
DESCRIBED = """
SELECT w.*, r.bus AS _region_bus, COALESCE(r.n, 0) AS _regions,
    row_number() OVER (
        PARTITION BY COALESCE(w.{chain_bus}, w.entity || ' bus') ORDER BY w.entity
    ) = 1 AS _first_on_bus,
    arc.from_id AS _arc_from, arc.to_id AS _arc_to,
    CASE WHEN w.power_units = 'COMPONENT_BASE' THEN w.base_power ELSE 1 END AS _scale,
    ts.label IS NOT NULL AS _has_ts,
    concat_ws(' - ', w.component_type, w.prime_mover_type, w.fuel, w.storage_tech, w.{group})
        AS _carrier,
    em.co2 AS _co2, COALESCE(em.n, 0) AS _emissions,
    dt.reservoir AS _reservoir, COALESCE(dt.n, 0) AS _reservoirs,
    res.storage_level_limits__max AS _level_max, res.initial_level AS _initial_level,
    res.inflow AS _inflow, res.evaporative_loss AS _evaporative_loss,
    res.operation_cost__spillage_cost AS _spillage_cost,
    res.level_data_type AS _level_data_type,
    built.year AS _build_year, retired.year AS _retirement_year,
    COALESCE(lasting.years, 1) AS _target_years
FROM wide w
LEFT JOIN (
    SELECT m.region.entity AS entity, any_value(m.region.bus) AS bus, count(*) AS n
    FROM {t}_region m GROUP BY 1
) r ON r.entity = w.entity
LEFT JOIN {t}_props_arc arc ON arc.arc = w.arc
LEFT JOIN (SELECT DISTINCT name AS label FROM ({profiles})) ts ON ts.label = w.entity
LEFT JOIN (
    SELECT m.entity_supplemental_attribute.entity AS entity, any_value(s._co2) AS co2,
        count(*) AS n
    FROM {t}_entity_supplemental_attribute m
    JOIN {t}_supplemental_attribute s
        ON s.supplemental_attribute = m.entity_supplemental_attribute.supplemental_attribute
    WHERE s.component_type = 'EmissionsData'
    GROUP BY 1
) em ON em.entity = w.entity
LEFT JOIN (
    SELECT m.downstream_turbines.turbine AS turbine,
        any_value(m.downstream_turbines.reservoir) AS reservoir, count(*) AS n
    FROM {t}_downstream_turbines m GROUP BY 1
) dt ON dt.turbine = w.entity
LEFT JOIN wide res ON res.entity = dt.reservoir
LEFT JOIN ({built}) built ON built.name = w.entity
LEFT JOIN ({retired}) retired ON retired.name = w.entity
LEFT JOIN ({lasting}) lasting ON lasting.period = w.target_year
"""
NO_PERIODS = "SELECT NULL::BIGINT AS period, NULL::DOUBLE AS years WHERE false"
NO_BUILD_YEARS = "SELECT NULL::VARCHAR AS entity, NULL::BIGINT AS _built WHERE false"
EVERY_PERIOD = """
SELECT * FROM ({built})
UNION ALL
SELECT e.entity, p.period AS _built FROM {t}_entity e, {periods} p
WHERE e.power_systems_type IS NOT NULL AND e.{invented} IS NOT TRUE
    AND e.entity NOT IN (SELECT entity FROM ({built}))
"""
EXPANDED = """
SELECT e.*, k._built,
    row_number() OVER (PARTITION BY e.entity ORDER BY k._built) = 1 AS _first_cohort{columns}
FROM {t}_entity e
LEFT JOIN ({built}) k ON k.entity = e.entity
{valued}
"""
BY_YEAR_VALUES = """
LEFT JOIN (
    SELECT cohort.entity AS entity, cohort.build_year AS _built, {pivoted}
    FROM {values} GROUP BY cohort
) v ON v.entity = k.entity AND v._built = k._built
"""
APART = """
WITH rows AS (SELECT * FROM {rows}),
apart AS (
    SELECT {dim} FROM rows GROUP BY {dim}, snapshot
    HAVING count(DISTINCT value) > 1 OR count(*) != {count}
)
SELECT * REPLACE (NULL::VARCHAR AS scenario) FROM rows
WHERE scenario = {first} AND {dim} NOT IN (SELECT {dim} FROM apart)
UNION ALL
SELECT * FROM rows WHERE {dim} IN (SELECT {dim} FROM apart)
"""
YEARS = """
SELECT j.key AS name, any_value(CAST(j.value AS BIGINT)) AS year
FROM {t}_supplemental_attribute s, json_each(s.{years}) j
WHERE s.component_type = 'RetirementPotential' GROUP BY 1
"""


def text(value: str) -> str:
    """Return `value` as a SQL string."""
    return "'" + value.replace("'", "''") + "'"


def quoted(name: str) -> str:
    """Return `name` as a SQL identifier."""
    return '"' + name.replace('"', '""') + '"'


def literal(value: Any, dtype: Any) -> str:
    """Return `value` as a SQL value of the type DuckDB reads a pandas `dtype` as."""
    if is_bool_dtype(dtype):
        return "true" if value else "false"
    if is_integer_dtype(dtype):
        return f"{int(value)}::BIGINT"
    if is_float_dtype(dtype):
        return "NULL::DOUBLE" if pd.isna(value) else f"'{float(value)!r}'::DOUBLE"
    return text(value if isinstance(value, str) else "")


def kind(dtype: Any) -> str:
    """Return the datarecord dtype of a pandas `dtype`."""
    if is_bool_dtype(dtype):
        return "bool"
    if is_integer_dtype(dtype):
        return "int"
    return "float" if is_float_dtype(dtype) else "str"


def refused(category: str, why: str, labels: Iterable[Any] = ()) -> UnsupportedRecordError:
    """Return the error for `category`, which the mapping does not cover because of `why`."""
    named = list(labels)
    what = f"{why}: {named}" if named else why
    return UnsupportedRecordError(
        NAME, Requirements(unsupported_values=frozenset({(category, what)}))
    )


def _timesteps(n: pypsa.Network) -> pd.Index:
    """Return the time of each snapshot of `n`, within its investment period if it has one."""
    return n.snapshots.get_level_values(TIMESTEP) if n.has_periods else n.snapshots


def _indexed(schema: Schema, snapshots: DuckDBPyRelation) -> pd.Index:
    """Return the labels of `snapshots`, rows of the dim, as PyPSA indexes them, in their order."""
    frame = unpacked(schema, SNAPSHOT, snapshots).df()
    unit = schema.meta.get(META, {}).get("snapshot_unit", "ns")
    if PERIOD not in frame:
        return pd.DatetimeIndex(frame[SNAPSHOT]).as_unit(unit)
    steps = pd.DatetimeIndex(frame[TIMESTEP]).as_unit(unit)
    return pd.MultiIndex.from_arrays([frame[PERIOD], steps], names=[PERIOD, TIMESTEP])


def _marked(n: pypsa.Network, cls: str, marks: pd.DataFrame) -> None:
    """Set the `og_` columns of the components of `cls` that `marks` has, by component."""
    static = n.components[cls].static
    held = static.reindex(columns=list(OG_COLUMNS)).astype(object)
    held.update(marks.astype(object))
    static[list(OG_COLUMNS)] = held.where(held.notna(), np.nan)


def _typed_carriers(n: pypsa.Network, carriers: Mapping[str, Technology]) -> pd.DataFrame:
    """Return the `og_` columns of each carrier in `carriers`, after checking they differ."""
    typed = pd.DataFrame(map(asdict, carriers.values()), index=list(carriers))
    typed = typed.reindex(columns=list(FIELDS)).rename(columns=FIELDS)
    classes = ("Generator", "StorageUnit", "Store")
    used = pd.concat([n.components[cls].static.carrier for cls in classes])
    held = typed[typed.index.isin(used)]
    alike = sorted(held.index[held.duplicated(keep=False)])
    if alike:
        raise ValueError(
            f"Carriers {alike} have the same OGSchema type, prime mover, fuel and group, so "
            "their components would share one carrier. Set a distinct `group` on the "
            "`Technology` of one of them."
        )
    return typed


def _on_bus(static: pd.DataFrame, port: str = "bus") -> pd.DataFrame:
    """Return, per bus, the first of the components of `static` on it and how many there are."""
    named = static.rename_axis("name").reset_index()
    return named.groupby(port)["name"].agg(["first", "size"])


def _shedding(n: pypsa.Network) -> None:
    """Mark each load-shedding generator as a part of the one load on its bus."""
    generators = n.components["Generator"].static
    loads = n.components["Load"].static
    shedding = generators[generators.og_type == SHEDDING]
    served = _on_bus(loads).reindex(shedding.bus)
    alone = (served["size"].to_numpy() == 1) & ~shedding.bus.duplicated(keep=False).to_numpy()
    if not alone.all():
        raise ValueError(
            f"Load-shedding generators {list(shedding.index[~alone])} are not each the only "
            "one on a bus with one load. Give each such bus one load and one generator."
        )
    part = pd.DataFrame({"og_part": "shedding", "og_entity": served["first"].to_numpy()})
    _marked(n, "Generator", part.set_index(shedding.index))
    interruptible = pd.DataFrame({"og_type": SHEDDING}, index=served["first"].to_numpy())
    _marked(n, "Load", interruptible)


def _cohorts(static: pd.DataFrame, port: str = "bus") -> pd.DataFrame:
    """Return, per bus and year built in, the first component of `static` and their count."""
    named = static.rename_axis("name").reset_index()
    grouped = named.groupby([port, "build_year"])["name"].agg(["first", "size"])
    return grouped.rename_axis(["bus", "build_year"])


def _chains(n: pypsa.Network) -> None:
    """Mark each store with its bus and the two links that charge and discharge it.

    A bus of a carrier with no OGSchema type must hold such chains alone: for each year its
    stores are built in, one store, one link into it from an electric bus and one link back
    to that bus. The bus is marked with the first of its stores by name.
    """
    buses = n.components["Bus"].static
    links = n.components["Link"].static
    free = buses.index[buses.og_type.isna()]
    if free.empty:
        return
    electric = buses.og_type.notna()
    into = links[links.bus1.isin(free) & links.bus0.map(electric).fillna(False).astype(bool)]
    out = links[links.bus0.isin(free) & links.bus1.map(electric).fillna(False).astype(bool)]
    stores = n.components["Store"].static
    store = _cohorts(stores[stores.bus.isin(free)])
    charge = _cohorts(into, "bus1")
    discharge = _cohorts(out, "bus0")
    cohorts = store.index.union(charge.index).union(discharge.index)
    parts = [frame.reindex(cohorts) for frame in (store, charge, discharge)]
    sizes = pd.concat([frame["size"] for frame in parts], axis=1)
    grid = links.bus0.reindex(parts[1]["first"]).to_numpy()
    back = links.bus1.reindex(parts[2]["first"]).to_numpy()
    whole = pd.Series((sizes == 1).all(axis=1).to_numpy() & (grid == back), index=cohorts)
    held = whole.groupby(level="bus").agg(["all", "size"]).reindex(free)
    others = pd.concat(
        [
            n.components[cls].static[port]
            for cls, ports in (
                ("Generator", ["bus"]),
                ("Load", ["bus"]),
                ("StorageUnit", ["bus"]),
                ("Line", ["bus0", "bus1"]),
                ("Link", ["bus0", "bus1"]),
            )
            for port in ports
        ]
    )
    attached = others.value_counts().reindex(free, fill_value=0).to_numpy()
    chained = held["all"].eq(True).to_numpy() & (attached == 2 * held["size"].to_numpy())
    if not chained.all():
        raise ValueError(
            f"Buses {list(free[~chained])} have a carrier without an OGSchema type and are no "
            "storage chain: for each year a store is built in, one store, one link from an "
            "electric bus, one link back to it, and nothing else. Type the carrier in "
            "`buses`, or change what is on the bus."
        )
    first = store["first"].groupby(level="bus").min().reindex(free)
    marks = {
        "Bus": pd.DataFrame({"og_part": "bus", "og_entity": first.to_numpy()}, index=free),
        "Store": pd.DataFrame({"og_part": "store", "og_entity": store["first"].to_numpy()}),
        "Link": pd.concat(
            [
                pd.DataFrame(
                    {"og_part": role, "og_entity": parts[0]["first"].to_numpy()}
                ).set_index(frame["first"].to_numpy())
                for role, frame in (("charge", parts[1]), ("discharge", parts[2]))
            ]
        ),
    }
    marks["Store"] = marks["Store"].set_index(store["first"].to_numpy())
    for cls, marked in marks.items():
        _marked(n, cls, marked)


def classify(
    n: pypsa.Network,
    carriers: Mapping[str, Technology],
    buses: Mapping[str, str] | None = None,
) -> None:
    """Mark every component of `n` with the OGSchema operations type it is written as.

    `carriers` types the generators, storage units and stores of each PyPSA carrier, and
    `buses` the buses of each bus carrier, AC and DC unless given. Loads, lines and links
    are typed by what they connect, an upper limit on CO2 or on the capacity of a carrier by
    what it limits, and a shape as geographic information. A component that is written as a
    part of another is marked with that component: a generator typed
    `InterruptiblePowerLoad` with the load on its bus, and a store on a bus without a type
    with that bus and the two links built in the same year as the store.

    The marks are the `og_` columns of each static frame, which `OGSchema.to_datarecord`
    reads. Raises `ValueError` for a component that gets no type, and for two carriers of
    the components of `n` that are typed alike.
    """
    typed = _typed_carriers(n, carriers)
    bus_types = n.components["Bus"].static.carrier.map(BUSES if buses is None else buses)
    for cls in SOURCES:
        static = n.components[cls].static
        static[list(OG_COLUMNS)] = pd.DataFrame(np.nan, static.index, list(OG_COLUMNS), object)
    _marked(n, "Bus", bus_types.to_frame("og_type"))
    for cls in ("Generator", "StorageUnit", "Store"):
        static = n.components[cls].static
        _marked(n, cls, typed.reindex(static.carrier).set_index(static.index))
    loads = n.components["Load"].static
    _marked(n, "Load", pd.DataFrame({"og_type": "PowerLoad"}, index=loads.index))
    for cls, kinds in BRANCHES.items():
        static = n.components[cls].static
        ends = static.bus0.map(bus_types) + "-" + static.bus1.map(bus_types)
        _marked(n, cls, ends.map(kinds).to_frame("og_type"))
    caps = n.components["GlobalConstraint"].static
    capped = (caps.type == "primary_energy") & (caps.carrier_attribute == "co2_emissions")
    limits = {"CarbonCaps": capped, CAPACITY_LIMIT: caps.type == EXPANSION_LIMIT}
    upper = (caps.sense == "<=").to_numpy()
    fitting = [upper & limit.to_numpy() for limit in limits.values()]
    cap = pd.Series(np.select(fitting, list(limits), None), caps.index)
    _marked(n, "GlobalConstraint", cap.to_frame("og_type"))
    shapes = n.components["Shape"].static
    _marked(n, "Shape", pd.DataFrame({"og_type": "GeographicInfo"}, index=shapes.index))
    _shedding(n)
    _chains(n)
    for cls in SOURCES:
        static = n.components[cls].static
        untyped = static.index[static.og_type.isna() & static.og_part.isna()]
        if len(untyped) > 0 and cls not in KEPT:
            raise ValueError(
                f"{cls} {list(untyped)} have no OGSchema type. Pass a `Technology` for each "
                "carrier of a generator, storage unit or store, and connect lines and links "
                "to buses of a carrier that `buses` types."
            )


def _cases(conditions: Iterable[str], values: Iterable[str]) -> str:
    """Return SQL that gives each row the value beside the first condition it fits."""
    cases = [f"WHEN {c} THEN {v}" for c, v in zip(conditions, values, strict=True)]
    return f"CASE {' '.join(cases)} END" if cases else "NULL"


def _of(cls: str) -> list[tuple[int, Entry]]:
    """Return the entries that rebuild PyPSA class `cls`, each with its place in the table."""
    return [(i, entry) for i, entry in enumerate(ENTRIES) if entry.cls == cls]


def _reading(source: str) -> list[tuple[int, Entry]]:
    """Return the entries that read the frame `source`, each with its place in the table."""
    return [(i, entry) for i, entry in enumerate(ENTRIES) if entry.source == source]


def _prefix(entry: Entry) -> str:
    """Return what the names of an entry's part start with, after `ext__pypsa__`."""
    return entry.role + SEP if entry.role else ""


def _kept(entry: Entry, column: str, prefix: str = EXT) -> str:
    """Return the name a record keeps a PyPSA attribute under that OGSchema has no field for.

    `prefix` is that of a static value, unless given.
    """
    if not entry.role and column in LABELS:
        return LABELS[column]
    return prefix + _prefix(entry) + column


def _default(defaults: pd.DataFrame, attr: str) -> str:
    """Return PyPSA's default of `attr` as SQL."""
    return literal(defaults.at[attr, "default"], defaults.at[attr, "dtype"])


def _resolved(n: pypsa.Network) -> pd.DataFrame:
    """Return the lines of `n`, with the impedances their standard types give them.

    The values are those PyPSA computes from `type`, `length` and `num_parallel` when it
    solves. A line without a type keeps its own.
    """
    lines = n.components["Line"].static
    typed = lines.index[lines.type != ""]
    if typed.empty:
        return lines
    kinds = n.components["LineType"].static.loc[lines.type[typed]].set_index(typed)
    length, parallel = lines.length[typed], lines.num_parallel[typed]
    per_length = {
        "r": kinds.r_per_length / parallel,
        "x": kinds.x_per_length / parallel,
        "b": 2 * np.pi * 1e-9 * kinds.f_nom * kinds.c_per_length * parallel,
    }
    resolved = lines.copy()
    for attr, value in per_length.items():
        resolved.loc[typed, attr] = value * length
    return resolved


def _vintages(static: pd.DataFrame, nom: str, periods: pd.Index) -> pd.DataFrame:
    """Return the label and build year of each cohort among the components of `static`.

    A cohort is an extendable component that is built in an investment period and named
    for it: the label of its technology, a hyphen and the year.
    """
    named = static.index.to_series().str.extract(VINTAGE)
    built = static.build_year.astype(str)
    fits = static[f"{nom}_extendable"] & static.build_year.isin(periods) & (named.year == built)
    return pd.DataFrame({"label": named.label[fits], "build_year": static.build_year[fits]})


def _of_a_year(label: str) -> str:
    """Return SQL for the name of the cohort a row is, of the technology that `label` names."""
    return f"CASE WHEN _built IS NULL THEN {label} ELSE {label} || '-' || _built END"


def _attribute(entry: Entry, kept: str) -> str | None:
    """Return the PyPSA attribute that the name `kept` holds of the part of `entry`, if any."""
    role, _, attr = kept.partition(SEP)
    if entry.role:
        return attr if role == entry.role and attr else None
    return None if role in ROLES and attr else kept


class _Result(NamedTuple):
    """One result of a network: the attribute that holds it, and where its values are read."""

    name: str
    spec: AttributeSpec
    dim: str
    source: str
    value: str
    where: str
    label: str


class _Layer:
    """The rows of a network, as SQL over its registered frames, read as a record."""

    def __init__(
        self,
        schema: Schema,
        con: DuckDBPyConnection,
        prelude: str,
        axes: Mapping[str, tuple[str, str]],
        values: Mapping[str, str],
    ) -> None:
        self.schema = schema
        self.con = con
        self._prelude = prelude
        self._axes = axes
        self._values = values

    def _read(self, sql: str) -> DuckDBPyRelation:
        return self.con.sql(self._prelude + sql)

    def _axis(self, dim: str, columns: str) -> DuckDBPyRelation:
        body, order = self._axes[dim]
        return self._read(f"SELECT {columns} FROM ({body}) {order}")

    @property
    def dims(self) -> LazyRelations:
        return LazyRelations(tuple(self._axes), lambda dim: self._axis(dim, quoted(dim)))

    @property
    def properties(self) -> LazyRelations:
        described = tuple(dim for dim in self._axes if dim in self.schema.properties)
        return LazyRelations(described, lambda dim: self._axis(dim, "* EXCLUDE (_order, _pos)"))

    @property
    def attributes(self) -> LazyRelations:
        return LazyRelations(tuple(self._values), lambda name: self._read(self._values[name]))

    def flags(self, **categories: str | Sequence[str]) -> dict[str, Flags]:
        return Fold.as_one_layer(self).flags(**categories)


class _Export:
    """A network on a connection, and the SQL that reads its frames as OGSchema rows."""

    def __init__(self, n: pypsa.Network, con: DuckDBPyConnection) -> None:
        self.n = n
        self.con = con
        self.t = "og_" + uuid4().hex[:12]
        self._require_scope()
        self.time = TIMES[n.has_periods]
        self.statics = {cls: self._static(cls) for cls in SOURCES}
        self.kept = {cls: self._unmapped(cls) for cls in KEPT}
        self.classes = [cls for cls in SOURCES if not self.statics[cls].empty]
        self.cohorts = self._collapse()
        self.dynamics = {cls: self._dynamic(cls) for cls in SOURCES}
        self.series = self._register()
        self.ctes = self._frames()
        self._type()

    def _require_scope(self) -> None:
        n = self.n
        held = {c.name for c in n.components if not c.static.empty}
        uncovered = held - set(SOURCES) - IGNORED
        if uncovered:
            raise UnsupportedRecordError(NAME, Requirements(categories=frozenset(uncovered)))
        if not isinstance(_timesteps(n), pd.DatetimeIndex):
            raise refused(SNAPSHOT, "snapshots that are no timestamps")
        ports = n.components["Link"].static.filter(regex=EXTRA_PORT)
        multi_port = ports.index[ports.fillna("").ne("").any(axis=1)]
        if len(multi_port) > 0:
            raise refused("Link", "more than two ports", multi_port)
        for cls in SOURCES:
            static = n.components[cls].static
            if not static.empty and not set(OG_COLUMNS) <= set(static.columns):
                raise refused(cls, "no `og_type`: `classify` the network first")

    def _typeless(self, cls: str) -> pd.Series:
        """Return which components of `cls` are kept whole, for want of an OGSchema type."""
        static = self.n.components[cls].static
        if cls not in KEPT or static.empty:
            return pd.Series(False, index=static.index)
        return static.og_type.isna() & static.og_part.isna()

    def _static(self, cls: str) -> pd.DataFrame:
        """Return the components of `cls` that the entries read.

        Lines have the impedances of their standard types, and shapes are GeoJSON text.
        """
        static = _resolved(self.n) if cls == "Line" else self.n.components[cls].static
        if cls == "Shape":
            outlines = shapely.to_geojson(static.geometry.to_numpy())
            static = pd.DataFrame(static).assign(geometry=outlines)
        return static[~self._typeless(cls)]

    def _collapse(self) -> dict[str, pd.DataFrame]:
        """Make one technology of the cohorts of each, and return the cohorts by class.

        The components that are built in an investment period and named for it are the
        cohorts of the technology their names share. The technology has the values of the
        cohort built first. A storage chain is collapsed if every part of it is a cohort.
        """
        n = self.n
        if not n.has_periods:
            return {cls: pd.DataFrame() for cls in NOMINAL}
        periods = n.investment_periods
        fitting = {
            cls: _vintages(self.statics[cls], nom, periods)
            for cls, (nom, _) in NOMINAL.items()
            if cls in self.classes
        }
        self._keep_chains_whole(fitting)
        if "Store" in fitting:
            stores = fitting["Store"].label
            for cls in {"Bus", "Store", "Link"} & set(self.classes):
                marked = self.statics[cls].og_entity
                relabelled = marked.map(stores).fillna(marked)
                self.statics[cls] = self.statics[cls].assign(og_entity=relabelled)
        cohorts = {cls: self._merged(cls, fit) for cls, fit in fitting.items()}
        if n.is_solved and any(not held.empty for held in cohorts.values()):
            raise refused(PERIOD, "the results of assets built in several investment periods")
        return {cls: cohorts.get(cls, pd.DataFrame()) for cls in NOMINAL}

    def _keep_chains_whole(self, fitting: dict[str, pd.DataFrame]) -> None:
        """Drop from `fitting` the parts of a storage chain that are not all cohorts of one."""
        if not {"Store", "Link"} <= fitting.keys():
            return
        stores, links = self.statics["Store"], self.statics["Link"]
        stores, links = stores[stores.og_part.notna()], links[links.og_part.notna()]
        buses = {
            "Store": stores.bus,
            "Link": links.bus1.where(links.og_part == "charge", links.bus0),
        }
        parts = pd.DataFrame(
            {
                "chain": pd.concat(buses),
                "role": pd.concat({"Store": stores.og_part, "Link": links.og_part}),
                "label": pd.concat({cls: fitting[cls].label for cls in buses}),
            }
        )
        parts = parts[parts.chain.notna()]
        labels = parts.groupby(["chain", "role"]).label.nunique().groupby("chain").max()
        whole = parts.label.notna().groupby(parts.chain).all() & (labels == 1)
        broken = parts.index[~parts.chain.map(whole).to_numpy()]
        for cls in buses:
            names = broken.get_level_values(1)[broken.get_level_values(0) == cls]
            fitting[cls] = fitting[cls].drop(index=names, errors="ignore")

    def _merged(self, cls: str, fit: pd.DataFrame) -> pd.DataFrame:
        """Replace the cohorts `fit` of `cls` by a technology each, and return the cohorts.

        A cohort has its label, its build year, the cohort of its label built first, its
        limits, and each number that differs between the cohorts of its label.
        """
        if fit.empty:
            return fit
        static = self.statics[cls]
        c = self.n.components[cls]
        nom, _ = NOMINAL[cls]
        limits = [f"{nom}_min", f"{nom}_max"]
        fit = fit.sort_values("build_year", kind="stable")
        first = fit.index.to_series().groupby(fit.label).first()
        values = static.loc[fit.index]
        outputs = c.defaults.index[c.defaults.status == "Output"]
        columns = values.columns.difference(["build_year", *limits, *outputs])
        differs = values[columns].groupby(fit.label).nunique(dropna=False).gt(1)
        texts = [column for column in columns if kind(values[column].dtype) == "str"]
        unplaced = differs[texts].any(axis=1)
        if unplaced.any():
            named = differs[texts].columns[differs[texts].any()].tolist()
            raise refused(cls, f"cohorts of one technology that differ in {named}", first[unplaced])
        varying = [column for column in columns.difference(texts) if differs[column].any()]
        apart = differs.loc[fit.label, varying].set_axis(fit.index)
        lacking = (values[varying].isna() & apart).any(axis=1)
        if lacking.any():
            raise refused(
                cls, "a value for one build year and none for another", fit.index[lacking]
            )
        limited = values[limits].groupby(fit.label).nunique().gt(1).any(axis=1)
        described = {"first": fit.label.map(first), "limited": fit.label.map(limited)}
        bounds = {"_min": values[limits[0]], "_max": values[limits[1]]}
        cohorts = fit.assign(**described, **bounds).join(values[varying].where(apart))
        merged = static.drop(index=fit.index.difference(first))
        merged = merged.rename(index=dict(zip(first.to_numpy(), first.index, strict=True)))
        merged.loc[first.index, "build_year"] = c.defaults.at["build_year", "default"]
        self.statics[cls] = merged
        return cohorts

    def _dynamic(self, cls: str) -> dict[str, pd.DataFrame]:
        """Return the series of `cls` by attribute, one for all the cohorts of a technology."""
        dynamic = self.n.components[cls].dynamic
        frames = {attr: frame for attr, frame in dynamic.items() if not frame.empty}
        if self.cohorts.get(cls, pd.DataFrame()).empty:
            return frames
        return {attr: self._one_series(cls, attr, frame) for attr, frame in frames.items()}

    def _one_series(self, cls: str, attr: str, wide: pd.DataFrame) -> pd.DataFrame:
        """Return `wide` with the series of the cohort built first for each technology.

        Each cohort must have that series from its build year on and PyPSA's default before,
        which is what `build` gives it again.
        """
        cohorts = self.cohorts[cls]
        held = cohorts.loc[cohorts.index.intersection(wide.columns)]
        if held.empty:
            return wide
        partly = cohorts.label.isin(held.label).sum() != len(held)
        if partly:
            raise refused(cls, f"a series `{attr}` for some cohorts of a technology", held.label)
        default = self.n.components[cls].defaults.at[attr, "default"]
        periods = self.n.snapshots.get_level_values(PERIOD).to_numpy()
        active = periods[:, None] >= held.build_year.to_numpy()
        expected = np.where(active, wide[held["first"]].to_numpy(), default)
        found = wide[held.index].to_numpy()
        same = ((found == expected) | (pd.isna(found) & pd.isna(expected))).all(axis=0)
        if not same.all():
            why = (
                f"a series `{attr}` that is not that of the cohort built first, from its build year"
            )
            raise refused(cls, why, held.index[~same])
        later = held.index[held.index != held["first"]]
        return wide.drop(columns=later).rename(columns=held.label)

    def _unmapped(self, cls: str) -> list[dict[str, Any]]:
        """Return the inputs of the components of `cls` without an OGSchema type, by row."""
        c = self.n.components[cls]
        outputs = c.defaults.index[c.defaults.status == "Output"]
        rows = c.static[self._typeless(cls)].drop(columns=[*outputs, *OG_COLUMNS], errors="ignore")
        named = rows.rename_axis("name").reset_index().astype(object)
        return named.where(named.notna(), None).to_dict("records")

    def _frame(self, name: str, frame: pd.DataFrame) -> None:
        """Register `frame` as Arrow, whose column types DuckDB reads without scanning rows."""
        self.con.register(f"{self.t}_{name}", pa.Table.from_pandas(frame, preserve_index=False))

    def _series_frame(self, name: str, wide: pd.DataFrame) -> None:
        """Register the series `wide` as a row per component, with the list of its values.

        The rows come in batches of about a row group of values. A batch is melted as one,
        so the values of a component stay together in time, the order in which a file of
        them is smallest.
        """
        steps, components = wide.shape
        values = pa.array(wide.to_numpy().ravel(order="F"), from_pandas=True)
        offsets = pa.array(np.arange(components + 1) * steps)
        listed = pa.LargeListArray.from_arrays(offsets, values)
        table = pa.table({"name": pa.array(wide.columns), "values": listed})
        batches = table.to_batches(max_chunksize=max(1, ROW_GROUP // max(steps, 1)))
        self.con.register(f"{self.t}_{name}", pa.Table.from_batches(batches, table.schema))

    def _labels_of_snapshots(self) -> pa.Array:
        """Return the label of each snapshot: its time, with its period if the network has any."""
        n = self.n
        steps = pa.array(_timesteps(n))
        if not n.has_periods:
            return steps
        periods = pa.array(n.snapshots.get_level_values(PERIOD).to_numpy(), pa.int64())
        return pa.StructArray.from_arrays([periods, steps], names=[PERIOD, TIMESTEP])

    def _register(self) -> dict[str, list[str]]:
        """Register the frames of the network, and return the series each class holds."""
        n = self.n
        self._frame("carriers", n.components["Carrier"].static.rename_axis("name").reset_index())
        weightings = n.snapshot_weightings.reset_index(drop=True)
        timed = weightings.assign(_pos=np.arange(len(n.snapshots)))
        snapshots = pa.Table.from_pandas(timed, preserve_index=False)
        labelled = snapshots.add_column(0, SNAPSHOT, self._labels_of_snapshots())
        self.con.register(f"{self.t}_snapshots", labelled)
        periods = n.investment_period_weightings.rename_axis(PERIOD).reset_index()
        self._frame("periods", periods.assign(_pos=np.arange(len(periods))))
        series: dict[str, list[str]] = {}
        for cls in dict.fromkeys(["Bus", *self.classes]):
            static = self.statics[cls].rename_axis("name").reset_index()
            self._frame(SOURCES[cls], static.assign(_pos=np.arange(1, len(static) + 1)))
            series[cls] = list(self.dynamics[cls])
            for attr, frame in self.dynamics[cls].items():
                self._series_frame(f"{SOURCES[cls]}__{attr}", frame)
        for cls, cohorts in self.cohorts.items():
            if not cohorts.empty:
                self._frame(f"{SOURCES[cls]}_cohorts", cohorts.rename_axis("name").reset_index())
        return series

    def _frames(self) -> dict[str, str]:
        """Return SQL for the frames that need no types, by the name the entries read each by."""
        t = self.t
        timed = f"* REPLACE (CAST(snapshot AS {self.time}) AS snapshot)"
        ctes = {
            "carriers": f"SELECT name, co2_emissions FROM {t}_carriers",
            "snapshots": f"SELECT {timed} FROM {t}_snapshots",
            "periods": f"SELECT * FROM {t}_periods",
            "buses_frame": f"SELECT * FROM {t}_buses",
        }
        if "GlobalConstraint" in self.classes:
            ctes["constraints_frame"] = f"SELECT * FROM {t}_global_constraints"
        for cls, cohorts in self.cohorts.items():
            held = f"SELECT * FROM {t}_{SOURCES[cls]}_cohorts"
            ctes[f"{SOURCES[cls]}_cohorts"] = NO_COHORTS if cohorts.empty else held
        for cls in self.classes:
            mapped = {attr for _, entry in _reading(SOURCES[cls]) for attr in entry.series}
            for attr in dict.fromkeys([*self.series[cls], *sorted(mapped)]):
                melted = f'SELECT name, unnest("values") AS value FROM {t}_{SOURCES[cls]}__{attr}'
                held = attr in self.series[cls]
                ctes[f"{SOURCES[cls]}__{attr}"] = melted if held else EMPTY_SERIES
        return ctes

    @property
    def prelude(self) -> str:
        """The `WITH` clause that names every frame the entries read."""
        return "WITH " + ", ".join(f"{name} AS ({body})" for name, body in self.ctes.items()) + " "

    def _type(self) -> None:
        """Store the frame of each class with the entries each row fits, for them to read."""
        carried = [SOURCES[cls] for cls in self.classes if cls in CARRIED]
        emitting = " UNION ALL ".join(
            f"SELECT name, og_carrier, co2 FROM {s} WHERE _component_type IS NOT NULL"
            for s in carried
        )
        empty = "SELECT NULL::VARCHAR AS name, NULL::VARCHAR AS og_carrier, 0 AS co2 WHERE false"
        typed = {SOURCES[cls]: self._typed(cls) for cls in self.classes if cls in ["Bus", *CARRIED]}
        typed["emitting"] = emitting or empty
        typed["emitters"] = (
            "SELECT og_carrier AS name, any_value(co2) AS co2_emissions,"
            " row_number() OVER (ORDER BY og_carrier) AS _pos"
            " FROM emitting WHERE co2 != 0 GROUP BY og_carrier"
        )
        sized = " UNION ALL ".join(
            EXTENDABLE.format(source=SOURCES[cls], nom=nom, bus=bus)
            for cls, (nom, bus) in NOMINAL.items()
            if cls in self.classes
        )
        if "GlobalConstraint" in self.classes:
            typed["extendables"] = sized or NO_EXTENDABLES
            typed["limited"] = LIMITED
        typed |= {
            SOURCES[cls]: self._typed(cls) for cls in self.classes if SOURCES[cls] not in typed
        }
        if "generators" in typed:
            typed |= DEVICE_FRAMES
        arcs = [(i, e) for i, e in enumerate(ENTRIES) if "arc" in e.write and e.source in typed]
        pairs = " UNION ".join(f"SELECT bus0, bus1 FROM {e.source} WHERE _e{i}" for i, e in arcs)
        if arcs:
            typed["arcs"] = (
                "SELECT bus0 || ' -> ' || bus1 AS name, bus0, bus1,"
                f" row_number() OVER (ORDER BY bus0, bus1) AS _pos FROM ({pairs})"
            )
        for name, body in typed.items():
            table = f"{self.t}_typed_{name}"
            self.con.execute(f"CREATE TEMP TABLE {table} AS {self.prelude}SELECT * FROM ({body})")
            self.ctes[name] = f"SELECT * FROM {table}"

    def _typed(self, cls: str) -> str:
        """Return SQL for the frame of `cls`, each row flagged with the entries it fits."""
        entries = _reading(SOURCES[cls])
        extra, joins = JOINS.get(cls, ("", ""))
        if cls in NOMINAL:
            extra += ", built.cohorts, built.limits_by_year"
            joins += (
                f" LEFT JOIN ({COHORTS.format(source=SOURCES[cls])}) built ON built.label = c.name"
            )
        frame = f"SELECT c.*{extra} FROM {self.t}_{SOURCES[cls]} c {joins}"
        flags = ", ".join(f"COALESCE({e.where}, false) AS _e{i}" for i, e in entries)
        whole = [(i, e) for i, e in entries if e.axis]
        typed = _cases((f"_e{i}" for i, _ in whole), (text(e.component_type) for _, e in whole))
        frame = f"SELECT *, {typed} AS _component_type FROM (SELECT *, {flags} FROM ({frame}))"
        if cls not in CARRIED:
            return frame
        named = ", ".join(f"CAST({column} AS VARCHAR)" for column in PARTS_OF_A_CARRIER)
        frame = f"SELECT *, concat_ws(' - ', _component_type, {named}) AS og_carrier FROM ({frame})"
        return (
            "SELECT t.*, COALESCE(k.co2_emissions, 0) AS co2,"
            " CASE WHEN k.co2_emissions != 0 THEN 'CO2 ' || t.og_carrier END AS og_emissions"
            f" FROM ({frame}) t LEFT JOIN carriers k ON k.name = t.carrier"
        )

    def sql(self, query: str) -> DuckDBPyRelation:
        return self.con.sql(self.prelude + query)

    def _labels(self, query: str) -> list[Any]:
        return [label for (label,) in self.sql(query).fetchall()]

    def condition(self, i: int) -> str:
        """Return the condition that selects the rows of entry `i` in its frame."""
        return f"_e{i}" if ENTRIES[i].source in SOURCES.values() else ENTRIES[i].where

    def require_mapped(self) -> None:
        """Raise for a component the table has no entry for, or that cannot be told apart."""
        for cls in self.classes:
            fits = " OR ".join(f"_e{i}" for i, _ in _of(cls))
            untyped = self._labels(f"SELECT name FROM {SOURCES[cls]} WHERE NOT ({fits}) LIMIT 5")
            if untyped:
                raise refused(cls, "an `og_type` or buses no OGSchema type takes", untyped)
            if cls in CARRIED:
                emits = "_component_type IS NULL AND co2 != 0"
                parts = self._labels(f"SELECT name FROM {SOURCES[cls]} WHERE {emits} LIMIT 5")
                if parts:
                    raise refused(cls, "a carrier with CO2 on a part of another component", parts)
        for source, condition, why in WRITE_REFUSALS:
            if source not in self.ctes:
                continue
            labels = self._labels(f"SELECT name FROM {source} WHERE {condition} LIMIT 5")
            if labels:
                raise refused(source, why, labels)
        entities = " UNION ALL ".join(
            f"SELECT {ENTRIES[i].label} AS name FROM {ENTRIES[i].source} WHERE {self.condition(i)}"
            for i in self.active
            if home(ENTRIES[i].component_type) == ENTITY and ENTRIES[i].axis
        )
        named = f"SELECT name FROM ({entities}) GROUP BY name HAVING count(*) > 1"
        twice = self._labels(named) if entities else []
        if twice:
            raise UnsupportedRecordError(NAME, Requirements(names=frozenset(twice)))
        rates = "SELECT og_carrier FROM emitting GROUP BY 1 HAVING count(DISTINCT co2) > 1"
        apart = self._labels(rates)
        if apart:
            raise refused("Carrier", "one OGSchema type with several CO2 rates", apart)

    @cached_property
    def active(self) -> list[int]:
        """The entries that have rows in this network, by their place in the table."""
        entries = [i for i, e in enumerate(ENTRIES) if e.source in self.ctes]
        counts = ", ".join(
            f"(SELECT count(*) FROM {ENTRIES[i].source} WHERE {self.condition(i)})" for i in entries
        )
        rows = self.sql(f"SELECT {counts}").fetchall()[0]
        return [i for i, count in zip(entries, rows, strict=True) if count > 0]

    @cached_property
    def owners(self) -> list[int]:
        """The active entries that rebuild a PyPSA component, which keep what has no field."""
        return [i for i in self.active if ENTRIES[i].cls is not None]

    def _differs(self, i: int, column: str) -> str:
        """Return the condition for a value of `column` that entry `i` does not place."""
        c = self.n.components[ENTRIES[i].cls]
        name = quoted(column)
        if kind(c.static[column].dtype) == "str":
            default = literal(c.defaults.default.get(column, ""), object)
            return f"COALESCE(CAST({name} AS VARCHAR), '') != {default} AND _e{i}"
        if column not in c.defaults.index:
            return f"{name} IS NOT NULL AND _e{i}"
        return f"{name} IS DISTINCT FROM {_default(c.defaults, column)} AND _e{i}"

    def _candidates(self, i: int) -> list[str]:
        """Return the static columns of the class of entry `i` that the entry does not place."""
        entry = ENTRIES[i]
        c = self.n.components[entry.cls]
        placed = DERIVED | set(c.defaults.index[c.defaults.status == "Output"]) | set(entry.read)
        return [column for column in c.static.columns if column not in placed]

    @cached_property
    def static_ext(self) -> dict[int, list[str]]:
        """The static columns that hold a value no entry places, by the entry that keeps them."""
        found: dict[int, list[str]] = {i: [] for i in self.owners}
        for cls in self.classes:
            pairs = [(i, column) for i in self.owners for column in self._candidates(i)]
            pairs = [(i, column) for i, column in pairs if ENTRIES[i].cls == cls]
            if not pairs:
                continue
            counts = ", ".join(
                f"count(*) FILTER (WHERE {self._differs(i, column)})" for i, column in pairs
            )
            rows = self.sql(f"SELECT {counts} FROM {SOURCES[cls]}").fetchall()[0]
            for (i, column), count in zip(pairs, rows, strict=True):
                if count > 0:
                    found[i].append(column)
        return found

    @cached_property
    def cohort_ext(self) -> dict[int, list[str]]:
        """The numbers that differ by build year, by the entry of the components that have them."""
        found: dict[int, list[str]] = {}
        for i in self.owners:
            cls = ENTRIES[i].cls
            source = SOURCES[cls]
            fixed = ["label", "build_year", "first", "limited", "_min", "_max"]
            columns = list(self.cohorts.get(cls, pd.DataFrame()).columns.difference(fixed))
            if not columns:
                continue
            counts = ", ".join(f"count(k.{quoted(column)})" for column in columns)
            joined = f"{source}_cohorts k JOIN {source} c ON c.name = k.label"
            rows = self.sql(f"SELECT {counts} FROM {joined} WHERE c._e{i}").fetchall()[0]
            found[i] = [column for column, count in zip(columns, rows, strict=True) if count > 0]
        return found

    def _unplaced(self, i: int, attr: str) -> str:
        """Return the condition for the rows of entry `i` whose series `attr` no entry places."""
        placing = [f"_e{j}" for j, e in _reading(ENTRIES[i].source) if attr in e.series]
        return f"_e{i} AND NOT ({' OR '.join(placing) or 'false'})"

    def _melted(self, cls: str, attr: str) -> str:
        """Return SQL for the series `attr` of `cls`, a row per value beside its component.

        The values of a component are melted after it is found, so they stay together.
        """
        source = SOURCES[cls]
        return MELTED.format(series=f"{self.t}_{source}__{attr}", source=source)

    def _any(self, source: str, where: str) -> bool:
        return bool(self.sql(f"SELECT 1 FROM {source} WHERE {where} LIMIT 1").fetchall())

    @cached_property
    def series_ext(self) -> dict[int, list[str]]:
        """The input series that hold a component no entry places them for, by entry."""
        found: dict[int, list[str]] = {}
        for i in self.owners:
            cls = ENTRIES[i].cls
            defaults = self.n.components[cls].defaults
            inputs = [a for a in self.series[cls] if defaults.at[a, "status"] != "Output"]
            found[i] = [
                attr
                for attr in inputs
                if self._any(self._melted(cls, attr), self._unplaced(i, attr))
            ]
        return found

    def _ext_specs(self) -> tuple[dict[str, AttributeSpec], dict[str, dict[str, PropertySpec]]]:
        """Return the `ext__` attributes and properties this network needs."""
        kinds: dict[str, set[str]] = {}
        dims: dict[str, set[str]] = {}
        properties: dict[str, dict[str, PropertySpec]] = {}
        for i in self.active:
            entry = ENTRIES[i]
            dim = home(entry.component_type)
            written = {
                name: EXT_DTYPES[name.removeprefix(EXT)]
                for name in entry.write
                if name.startswith(EXT)
            }
            written |= {name: LABEL_DTYPES[name] for name in self._labelled(i)}
            if entry.cls is not None:
                static = self.n.components[entry.cls].static
                kept = {_kept(entry, c): kind(static[c].dtype) for c in self.static_ext[i]}
                written |= kept
                for attr in self.series_ext[i]:
                    name = qualified(dim, _kept(entry, attr, SERIES))
                    kinds.setdefault(name, set()).add("float")
                    dims.setdefault(name, set()).update({dim, SNAPSHOT})
            for name, dtype in written.items():
                if dtype == "str":
                    properties.setdefault(dim, {})[name] = PropertySpec(dtype="str")
                    continue
                kinds.setdefault(qualified(dim, name), set()).add(dtype)
                dims.setdefault(qualified(dim, name), set()).add(dim)
        for i, columns in self.cohort_ext.items():
            static = self.n.components[ENTRIES[i].cls].static
            for column in columns:
                name = qualified(COHORT, _kept(ENTRIES[i], column))
                kinds.setdefault(name, set()).add(kind(static[column].dtype))
                dims[name] = {COHORT}
        for column in WEIGHTINGS:
            if (self.n.snapshot_weightings[column] != 1).any():
                kinds[qualified(SNAPSHOT, WEIGHTING + column)] = {"float"}
                dims[qualified(SNAPSHOT, WEIGHTING + column)] = {SNAPSHOT}
        if self.n.has_periods:
            for column in PERIOD_WEIGHTINGS:
                kinds[qualified(PERIOD, WEIGHTING + column)] = {"float"}
                dims[qualified(PERIOD, WEIGHTING + column)] = {PERIOD}
        attributes: dict[str, AttributeSpec] = {}
        texts = [qualified(dim, name) for dim, named in properties.items() for name in named]
        twice = sorted(kinds.keys() & texts)
        if twice:
            raise ValueError(
                f"{twice} hold text for some components and numbers for others. Give each "
                "column one dtype in every component class."
            )
        for name, held in kinds.items():
            numeric = held <= {"int", "float"}
            if len(held) > 1 and not numeric:
                raise ValueError(
                    f"{name} is {sorted(held)} in different component classes. Give the "
                    "column one dtype in every class."
                )
            dtype = "float" if len(held) > 1 else next(iter(held))
            attributes[name] = AttributeSpec(dtype=dtype, dims=dims[name])
        return attributes, properties

    def _labelled(self, i: int) -> list[str]:
        """Return the labels of this library that entry `i` gives at least one component."""
        entry = ENTRIES[i]
        where = self.condition(i)
        return [
            name
            for name in entry.write
            if name in LABEL_DTYPES
            and self._any(entry.source, f"({where}) AND ({entry.write[name]}) IS NOT NULL")
        ]

    def _results(self) -> list[_Result]:
        """Return every result the network holds."""
        results: list[_Result] = []
        for i in self.owners:
            entry = ENTRIES[i]
            cls = entry.cls
            c = self.n.components[cls]
            dim = home(entry.component_type)
            for attr in c.defaults.index[c.defaults.status == "Output"]:
                name = qualified(dim, RESULT + _prefix(entry) + attr)
                if attr in self.series[cls]:
                    spec = AttributeSpec(dtype="float", dims={dim, SNAPSHOT})
                    source = self._melted(cls, attr)
                    results.append(_Result(name, spec, dim, source, "value", f"_e{i}", entry.label))
                elif attr in c.static and kind(c.static[attr].dtype) != "str":
                    spec = AttributeSpec(dtype="float", dims={dim})
                    column = quoted(attr)
                    results.append(
                        _Result(name, spec, dim, SOURCES[cls], column, f"_e{i}", entry.label)
                    )
        return results

    def _rows(
        self,
        schema: Schema,
        name: str,
        dim: str,
        source: str,
        value: str,
        where: str = "true",
        label: str = "name",
        timed: bool = False,
    ) -> str:
        """Return SQL for the long rows of attribute `name` that `value` gives over `source`."""
        dtype = schema.duck_type(schema.attributes[name])
        time = ""
        if SNAPSHOT in schema.attributes[name].dims and dim != SNAPSHOT:
            time = f"CAST({'snapshot' if timed else 'NULL'} AS {self.time}) AS snapshot, "
        return (
            f"SELECT {label} AS {quoted(dim)}, {time}{text(name)} AS attribute,"
            f" NULL::DOUBLE AS breakpoint, CAST({value} AS {dtype}) AS value"
            f" FROM {source} WHERE ({where}) AND ({value}) IS NOT NULL"
        )

    def _result_rows(self, schema: Schema, results: Iterable[_Result]) -> dict[str, str]:
        """Return SQL for the long rows of each of `results`, by the name of its attribute."""
        selects: dict[str, list[str]] = {}
        for result in results:
            timed = SNAPSHOT in result.spec.dims
            rows = self._rows(
                schema,
                result.name,
                result.dim,
                result.source,
                result.value,
                result.where,
                result.label,
                timed,
            )
            selects.setdefault(result.name, []).append(rows)
        return {name: " UNION ALL ".join(rows) for name, rows in selects.items()}

    def results(self, base: RecordLike) -> _Layer:
        """Return the results of the network alone, as a layer over `base`."""
        n = self.n
        if not _indexed(base.schema, base.dims[SNAPSHOT]).equals(n.snapshots):
            raise ValueError(
                "The snapshots of `n` differ from those of `base`. Write the results of a "
                "network that has every snapshot of `base`."
            )
        results = self._results()
        solved = {"objective": n.objective, "objective_constant": n.objective_constant}
        meta = {META: {**base.schema.meta.get(META, {}), **solved}}
        schema = extended(base.schema, {r.name: r.spec for r in results}, meta=meta)
        return _Layer(schema, self.con, self.prelude, {}, self._result_rows(schema, results))

    def record(self, base: RecordLike | None) -> _Layer:
        """Return the whole network as a record, over `base` if given."""
        self.require_mapped()
        n = self.n
        types = {ENTRIES[i].component_type for i in self.active}
        held = set() if base is None else set(base.schema.meta["types"])
        schema = manifest(sorted(types | held), periods=n.has_periods)
        if base is not None:
            held_meta = {k: v for k, v in base.schema.meta.items() if k not in schema.meta}
            described = {d: named for d, named in base.schema.properties.items() if d != SNAPSHOT}
            schema = extended(schema, base.schema.attributes, described, held_meta)
        attributes, properties = self._ext_specs()
        results = self._results() if n.is_solved else []
        attributes |= {result.name: result.spec for result in results}
        meta: dict[str, Any] = {"name": n.name, "crs": n.crs.to_string(), "meta": n.meta}
        meta["snapshot_unit"] = _timesteps(n).unit
        meta[COMPONENTS] = {cls: rows for cls, rows in self.kept.items() if rows}
        if n.is_solved:
            meta |= {"objective": n.objective, "objective_constant": n.objective_constant}
        schema = extended(schema, attributes, properties, {META: meta})
        values = self._values(schema) | self._result_rows(schema, results)
        axes = self._axes(schema)
        whole, _ = axes.get(ENTITY, ("SELECT NULL AS entity, 1 AS component_type", ""))
        orphans = self._labels(f"SELECT entity FROM ({whole}) WHERE component_type IS NULL")
        if orphans:
            raise refused(ENTITY, "parts of a component the network does not hold", orphans)
        return _Layer(schema, self.con, self.prelude, axes, values)

    def _described(self, schema: Schema, i: int) -> dict[str, str]:
        """Return SQL for each property entry `i` gives its component, by property."""
        entry = ENTRIES[i]
        dim = home(entry.component_type)
        columns = {
            name: f"CAST({expr} AS VARCHAR)"
            for name, expr in entry.write.items()
            if name in schema.properties[dim]
        }
        if entry.cls is None:
            return columns
        static = self.n.components[entry.cls].static
        for column in self.static_ext[i]:
            if kind(static[column].dtype) == "str":
                value = f"CAST({quoted(column)} AS VARCHAR)"
                columns[_kept(entry, column)] = (
                    f"CASE WHEN {self._differs(i, column)} THEN {value} END"
                )
        return columns

    def _axes(self, schema: Schema) -> dict[str, tuple[str, str]]:
        """Return SQL for the labels and properties of each dim, with the order to read it in."""
        sources = list(dict.fromkeys(entry.source for entry in ENTRIES))
        parts: dict[str, list[str]] = {}
        named: dict[str, dict[str, None]] = {}
        tuples: dict[str, list[str]] = {}
        for i in self.active:
            entry = ENTRIES[i]
            dim = home(entry.component_type)
            columns = self._described(schema, i)
            named.setdefault(dim, {}).update(dict.fromkeys(columns))
            order = f"{sources.index(entry.source)} AS _order, _pos"
            typed = f"{text(entry.component_type)} AS component_type"
            if not entry.axis:
                order = "NULL::INTEGER AS _order, NULL::BIGINT AS _pos"
                typed = "NULL::VARCHAR AS component_type"
            held = [f"{expr} AS {quoted(name)}" for name, expr in columns.items()]
            select = ", ".join([f"{entry.label} AS {quoted(dim)}", order, typed, *held])
            parts.setdefault(dim, []).append(
                f"SELECT {select} FROM {entry.source} WHERE {self.condition(i)}"
            )
            for multi, coordinates in entry.tuples.items():
                if multi not in schema.dimensions:
                    continue
                fields = list(schema.over(multi))
                inner = ", ".join(f"{coordinates[f]} AS {quoted(f)}" for f in fields)
                packed = ", ".join(f"{quoted(f)} := {quoted(f)}" for f in fields)
                whole = " AND ".join(f"{quoted(f)} IS NOT NULL" for f in fields)
                rows = f"SELECT {inner} FROM {entry.source} WHERE {self.condition(i)}"
                tuples.setdefault(multi, []).append(
                    f"SELECT struct_pack({packed}) AS {quoted(multi)} FROM ({rows}) WHERE {whole}"
                )
        axes: dict[str, tuple[str, str]] = {}
        for dim, rows in parts.items():
            merged = ", ".join(
                f"any_value({quoted(name)}) AS {quoted(name)}"
                for name in ["component_type", *named[dim]]
            )
            body = " UNION ALL BY NAME ".join(rows)
            axes[dim] = (
                f"SELECT {quoted(dim)}, min(_order) AS _order, min(_pos) AS _pos, {merged}"
                f" FROM ({body}) GROUP BY {quoted(dim)}",
                "ORDER BY _order, _pos",
            )
        axes |= {multi: (" UNION ALL ".join(rows), "") for multi, rows in tuples.items()}
        axes[SNAPSHOT] = ("SELECT snapshot, _pos FROM snapshots", "ORDER BY _pos")
        if self.n.has_periods:
            steps = f"SELECT snapshot.{TIMESTEP} AS {TIMESTEP}, min(_pos) AS _pos FROM snapshots"
            axes[TIMESTEP] = (f"{steps} GROUP BY 1", "ORDER BY _pos")
            axes[PERIOD] = (f"SELECT {PERIOD}, _pos FROM periods", "ORDER BY _pos")
        return axes

    def _values(self, schema: Schema) -> dict[str, str]:
        """Return SQL for the long rows of every input attribute."""
        selects: dict[str, list[str]] = {}
        for i in self.active:
            entry = ENTRIES[i]
            dim = home(entry.component_type)
            where = self.condition(i)
            for field, value in entry.write.items():
                if field in schema.properties[dim] or LABEL_DTYPES.get(field) == "str":
                    continue
                name = qualified(dim, field)
                rows = self._rows(schema, name, dim, entry.source, value, where, entry.label)
                selects.setdefault(name, []).append(rows)
            for attr, series in entry.series.items():
                cls = next(cls for cls, source in SOURCES.items() if source == entry.source)
                if series.write is None or attr not in self.series[cls]:
                    continue
                name = qualified(dim, TIME_SERIES_PREFIX + series.name)
                source = self._melted(cls, attr)
                rows = self._rows(
                    schema, name, dim, source, series.write, where, entry.label, timed=True
                )
                selects.setdefault(name, []).append(rows)
        for i in self.owners:
            entry = ENTRIES[i]
            dim = home(entry.component_type)
            static = self.n.components[entry.cls].static
            for column in self.static_ext[i]:
                if kind(static[column].dtype) == "str":
                    continue
                name = qualified(dim, _kept(entry, column))
                where = self._differs(i, column)
                rows = self._rows(
                    schema, name, dim, entry.source, quoted(column), where, entry.label
                )
                selects.setdefault(name, []).append(rows)
            for attr in self.series_ext[i]:
                name = qualified(dim, _kept(entry, attr, SERIES))
                where = self._unplaced(i, attr)
                source = self._melted(entry.cls, attr)
                rows = self._rows(schema, name, dim, source, "value", where, entry.label, True)
                selects.setdefault(name, []).append(rows)
        for i, columns in self.cohort_ext.items():
            entry = ENTRIES[i]
            label = COHORT_LABEL.format(entity=entry.label)
            for column in columns:
                name = qualified(COHORT, _kept(entry, column))
                source = BY_YEAR.format(source=entry.source, column=quoted(column))
                rows = self._rows(schema, name, COHORT, source, "_by_year", f"_e{i}", label)
                selects.setdefault(name, []).append(rows)
        for column in WEIGHTINGS:
            name = qualified(SNAPSHOT, WEIGHTING + column)
            if name in schema.attributes and (self.n.snapshot_weightings[column] != 1).any():
                rows = self._rows(
                    schema, name, SNAPSHOT, "snapshots", column, f"{column} != 1", "snapshot"
                )
                selects[name] = [rows]
        if self.n.has_periods:
            for column in PERIOD_WEIGHTINGS:
                name = qualified(PERIOD, WEIGHTING + column)
                selects[name] = [self._rows(schema, name, PERIOD, "periods", column, label=PERIOD)]
        return {name: " UNION ALL ".join(rows) for name, rows in selects.items()}


def _scenario(n: pypsa.Network, scenario: str) -> pypsa.Network:
    """Return the network of one scenario of `n`, under the name of `n`."""
    one = n.get_scenario(scenario)
    one.name = n.name
    return one


def _require_invariant(n: pypsa.Network) -> None:
    """Raise for a static value of `n` that differs between its scenarios."""
    first, *others = n.scenarios
    apart: dict[str, None] = {}
    for c in n.components:
        if c.static.empty:
            continue
        held = c.static.xs(first, level=SCENARIO)
        for scenario in others:
            other = c.static.xs(scenario, level=SCENARIO)
            differs = other.ne(held) & ~(other.isna() & held.isna())
            stacked = differs.stack()
            apart |= dict.fromkeys(
                f"{c.name} {name}: {attr}" for name, attr in stacked.index[stacked]
            )
    if apart:
        raise refused(SCENARIO, "a static value that differs between scenarios", apart)


class _Stochastic:
    """A network with scenarios: the record of each scenario, as one record over `scenario`."""

    def __init__(self, n: pypsa.Network, con: DuckDBPyConnection) -> None:
        _require_invariant(n)
        self.con = con
        self.t = "og_" + uuid4().hex[:12]
        self.scenarios = list(n.scenarios)
        self.exports = [_Export(_scenario(n, scenario), con) for scenario in self.scenarios]
        weights = n.scenario_weightings["weight"]
        labelled = {SCENARIO: pa.array(self.scenarios, pa.string())}
        weighted = {"weight": weights.to_numpy(), "_pos": np.arange(len(weights))}
        con.register(f"{self.t}_scenarios", pa.table(labelled | weighted))

    def _spread(self, name: str, spec: AttributeSpec, layers: list[_Layer]) -> str | None:
        """Store the rows of series `name`, per scenario where they differ, if any do.

        Returns the table, or None if every scenario has the same rows.
        """
        (dim,) = spec.dims - {SNAPSHOT}
        views = []
        for scenario, layer in zip(self.scenarios, layers, strict=True):
            view = f"{self.t}_{len(views)}_{uuid4().hex[:8]}"
            self.con.register(view, layer.attributes[name])
            views.append(f"SELECT *, {text(scenario)} AS scenario FROM {view}")
        rows = "(" + " UNION ALL ".join(views) + ")"
        table = f"{self.t}_spread_{uuid4().hex[:8]}"
        count, first = len(self.scenarios), text(self.scenarios[0])
        spread = APART.format(rows=rows, dim=quoted(dim), count=count, first=first)
        self.con.execute(f"CREATE TEMP TABLE {table} AS {spread}")
        held = self.con.sql(f"SELECT 1 FROM {table} WHERE scenario IS NOT NULL LIMIT 1")
        return table if held.fetchall() else None

    def _layer(self, layers: list[_Layer]) -> _Layer:
        """Return the layers of the scenarios as one, each series once or per scenario."""
        first = layers[0]
        values = dict(first._values)
        attributes = {SCENARIO_WEIGHT: AttributeSpec(dtype="float", dims={SCENARIO})}
        for name, spec in first.schema.attributes.items():
            if name not in values or SNAPSHOT not in spec.dims or spec.dims == {SNAPSHOT}:
                continue
            table = self._spread(name, spec, layers)
            if table is not None:
                values[name] = f"SELECT * FROM {table}"
                attributes[name] = spec.model_copy(update={"dims": spec.dims | {SCENARIO}})
        scenarios = f"{self.t}_scenarios"
        values[SCENARIO_WEIGHT] = (
            f"SELECT scenario, {text(SCENARIO_WEIGHT)} AS attribute,"
            f" NULL::DOUBLE AS breakpoint, weight AS value FROM {scenarios}"
        )
        axes = {
            **first._axes,
            SCENARIO: (f"SELECT scenario, _pos FROM {scenarios}", "ORDER BY _pos"),
        }
        schema = extended(first.schema, attributes, dimensions={SCENARIO: Dimension()})
        return _Layer(schema, self.con, first._prelude, axes, values)

    def record(self, base: RecordLike | None) -> _Layer:
        """Return the whole network as a record, over `base` if given."""
        return self._layer([export.record(base) for export in self.exports])

    def results(self, base: RecordLike) -> _Layer:
        """Return the results of the network alone, as a layer over `base`."""
        return self._layer([export.results(base) for export in self.exports])


@cache
def reference() -> Schema:
    """The schema of every type the table maps, whose names the SQL of an entry may read."""
    schema = manifest(sorted({entry.component_type for entry in ENTRIES}))
    numbers = {name: dtype for name, dtype in EXT_DTYPES.items() if dtype != "str"}
    ext = {EXT + name: AttributeSpec(dtype=dtype, dims={ENTITY}) for name, dtype in numbers.items()}
    texts = {EXT + name: PropertySpec(dtype="str") for name in EXT_DTYPES.keys() - numbers.keys()}
    labels = {GROUP: PropertySpec(dtype="str")}
    ext |= {
        name: AttributeSpec(dtype=dtype, dims={ENTITY})
        for name, dtype in LABEL_DTYPES.items()
        if dtype != "str"
    }
    return extended(
        schema, ext, {"bus": labels, ENTITY: labels | texts, SUPPLEMENTAL: labels | texts}
    )


class _Import:
    """A record on its connection, as one wide table per home dim that the entries read."""

    def __init__(self, record: RecordLike) -> None:
        self.record = record
        self.con = record.con
        self.schema = record.schema
        self.t = "og_" + uuid4().hex[:12]
        self._require_scope()
        self.flags = record.flags()
        self.views: list[str] = []
        self.tables: list[str] = []
        self.snapshots = self._snapshots()
        self.series = self._register_series()
        self.columns = self._tables()
        self.by_year = self._expand()
        self._require_mapped()

    def _require_scope(self) -> None:
        declared = self.schema.dimensions.get(SNAPSHOT)
        timed = declared is not None and declared.dtype == "datetime"
        if not timed and (declared is None or set(declared.over or ()) != {PERIOD, TIMESTEP}):
            raise UnsupportedRecordError(NAME, Requirements(dims=frozenset({SNAPSHOT})))

    def _view(self, name: str, rel: DuckDBPyRelation) -> str:
        view = f"{self.t}_{name}"
        self.con.register(view, rel)
        self.views.append(view)
        return view

    def _snapshots(self) -> str:
        """Store the snapshots of the record with the place of each, and return the table."""
        table = f"{self.t}_snapshots"
        labels = self._view("snapshot_labels", self.record.dims[SNAPSHOT])
        numbered = f"SELECT snapshot, row_number() OVER () - 1 AS _pos FROM {labels}"
        self.con.execute(f"CREATE TEMP TABLE {table} AS {numbered}")
        self.tables.append(table)
        return table

    def _register_series(self) -> dict[str, str]:
        """Register every attribute with rows along `snapshot`, and return its view by name."""
        timed = sorted(name for name, flag in self.flags.items() if SNAPSHOT in flag.varies)
        views: dict[str, str] = {}
        for i, name in enumerate(timed):
            rows = self.record.attributes[name].filter("snapshot IS NOT NULL")
            views[name] = self._view(f"series_{i}", rows)
        return views

    def _names(self, dim: str) -> tuple[list[str], dict[str, AttributeSpec]]:
        """Return the properties of `dim` and its attributes over no other dim but `snapshot`."""
        schemas = (reference(), self.schema)
        properties = [name for schema in schemas for name in schema.properties.get(dim, {})]
        attributes = {
            name: spec
            for schema in schemas
            for name, spec in schema.attributes.items()
            if dim in spec.dims and spec.dims <= {dim, SNAPSHOT}
        }
        return list(dict.fromkeys(properties)), attributes

    def _properties(self, dim: str) -> str:
        """Register the labels of `dim` with every property an entry may read, as text."""
        names = [dim, *self._names(dim)[0]]
        if dim not in self.record.properties:
            nulls = ", ".join(f"NULL::VARCHAR AS {quoted(name)}" for name in names)
            empty = self.con.sql(f"SELECT {nulls}, 0 AS _pos WHERE false")
            return self._view(f"props_{dim}", empty)
        rel = self.record.properties[dim]
        held = {name: quoted(name) if name in rel.columns else "NULL" for name in names}
        columns = ", ".join(
            f"CAST({value} AS VARCHAR) AS {quoted(name)}" for name, value in held.items()
        )
        return self._view(f"props_{dim}", rel.project(f"{columns}, row_number() OVER () AS _pos"))

    def _wide(self, dim: str) -> str:
        """Return SQL for a row per label of `dim`, with a column per property and attribute."""
        _, attributes = self._names(dim)
        long: list[DuckDBPyRelation] = []
        columns: list[str] = []
        for name, spec in attributes.items():
            dtype = self.schema.duck_type(spec)
            flag = self.flags.get(name)
            if flag is None or (SNAPSHOT in spec.dims and SNAPSHOT not in flag.broadcast):
                columns.append(f"NULL::{dtype} AS {quoted(name)}")
                continue
            if dim in flag.broadcast or flag.breakpoints:
                raise refused(dim, f"{name} as a curve of points or for every label at once")
            rows = self.record.attributes[name]
            rows = rows.filter("snapshot IS NULL") if SNAPSHOT in spec.dims else rows
            select = f"CAST({quoted(dim)} AS VARCHAR) AS label, {text(name)} AS attribute"
            long.append(rows.project(f"{select}, CAST(value AS DOUBLE) AS value"))
            pivoted = f"max(value) FILTER (WHERE attribute = {text(name)})"
            columns.append(f"CAST({pivoted} AS {dtype}) AS {quoted(name)}")
        properties = self._properties(dim)
        if not long:
            nulls = ", ".join(columns)
            return f"SELECT p.*{', ' if nulls else ''}{nulls} FROM {properties} p"
        values = self._view(f"long_{dim}", reduce(DuckDBPyRelation.union, long))
        pivot = f"SELECT label, {', '.join(columns)} FROM {values} GROUP BY label"
        joined = f"{properties} p LEFT JOIN ({pivot}) a ON a.label = p.{quoted(dim)}"
        return f"SELECT p.*, a.* EXCLUDE (label) FROM {joined}"

    def _table(self, dim: str, sql: str) -> list[str]:
        """Store the rows of `sql` as the table of `dim`, each flagged if an entry reads it."""
        entries = [entry for entry in ENTRIES if home(entry.component_type) == dim]
        covered = " OR ".join(f"COALESCE({entry.stored}, false)" for entry in entries)
        table = f"{self.t}_{dim}"
        self.con.execute(
            f"CREATE TEMP TABLE {table} AS SELECT *, {covered} AS _covered FROM ({sql})"
        )
        self.tables.append(table)
        return self.con.table(table).columns

    def _tables(self) -> dict[str, list[str]]:
        """Build the wide table of each home dim, and return the columns of each."""
        t = self.t
        for multi in ASSOCIATIONS:
            if multi in self.schema.dimensions and multi in self.record.dims:
                self._view(multi, self.record.dims[multi])
                continue
            fields = ", ".join(f"{quoted(f)} VARCHAR" for f in reference().over(multi))
            empty = f"SELECT NULL::STRUCT({fields}) AS {quoted(multi)} WHERE false"
            self._view(multi, self.con.sql(empty))
        self._properties("arc")
        profiles = EMPTY_SERIES
        if PROFILE in self.series:
            profiles = f"SELECT entity AS name FROM {self.series[PROFILE]}"
        untyped = ", ".join(f"NULL::VARCHAR AS {name}" for name in UNTYPED)
        supplemental = SUPPLEMENTAL_TABLE.format(
            t=t, co2=CO2_PER_MWH, wide=self._wide(SUPPLEMENTAL), untyped=untyped
        )
        point = POINT.format(geo_json="s.geo_json")
        bus = BUS_TABLE.format(t=t, wide=self._wide("bus"), untyped=untyped, point=point)
        years = {
            "built": YEARS.format(t=t, years="build_year"),
            "retired": YEARS.format(t=t, years="planned_retirement_year"),
        }
        chain_bus = EXT + "bus" + SEP + "name"
        lasting = NO_PERIODS
        if qualified(PERIOD, WEIGHTING + "years") in self.flags:
            weighted = self._view(
                "years", self.record.attributes[qualified(PERIOD, WEIGHTING + "years")]
            )
            lasting = f"SELECT period, value AS years FROM {weighted}"
        described = DESCRIBED.format(
            t=t, profiles=profiles, group=GROUP, chain_bus=chain_bus, lasting=lasting, **years
        )
        entity = ENTITY_TABLE.format(t=t, wide=self._wide(ENTITY), described=described)
        tables = {SUPPLEMENTAL: supplemental, "bus": bus, ENTITY: entity}
        return {dim: self._table(dim, sql) for dim, sql in tables.items()}

    def _expand(self) -> list[str]:
        """Store a row per entity and build year, and return the names of the values by year.

        An entity without build years has one row. In a record with investment periods that
        is not made from PyPSA, a technology without build years is built in every period.
        """
        t = self.t
        built = NO_BUILD_YEARS
        if COHORT in self.schema.dimensions and COHORT in self.record.dims:
            tuples = self._view(COHORT, self.record.dims[COHORT])
            built = f"SELECT cohort.entity AS entity, cohort.build_year AS _built FROM {tuples}"
        if PERIOD in self.schema.dimensions and META not in self.schema.meta:
            periods = self._view(PERIOD, self.record.dims[PERIOD])
            built = EVERY_PERIOD.format(built=built, t=t, periods=periods, invented=INVENTED)
        specs = {
            name: spec
            for name, spec in sorted(self.schema.attributes.items())
            if spec.dims == {COHORT} and name in self.flags
        }
        valued = columns = ""
        if specs:
            long = [
                self.record.attributes[name].project(
                    f"cohort, {text(name)} AS attribute, CAST(value AS DOUBLE) AS value"
                )
                for name in specs
            ]
            values = self._view("by_year", reduce(DuckDBPyRelation.union, long))
            pivoted = ", ".join(
                f"CAST(max(value) FILTER (WHERE attribute = {text(name)})"
                f" AS {self.schema.duck_type(spec)}) AS {quoted(name)}"
                for name, spec in specs.items()
            )
            valued = BY_YEAR_VALUES.format(pivoted=pivoted, values=values)
            columns = ", v.* EXCLUDE (entity, _built)"
        table = f"{t}_expanded"
        expanded = EXPANDED.format(t=t, built=built, valued=valued, columns=columns)
        self.con.execute(f"CREATE TEMP TABLE {table} AS {expanded}")
        self.tables.append(table)
        return list(specs)

    def _table_of(self, dim: str) -> str:
        """Return the table that the entries of `dim` rebuild components from."""
        return f"{self.t}_expanded" if dim == ENTITY else f"{self.t}_{dim}"

    def _name(self, entry: Entry) -> str:
        """Return SQL for the PyPSA name of the component that an entry rebuilds from a row."""
        dim = home(entry.component_type)
        name = entry.name or quoted(dim)
        return _of_a_year(name) if dim == ENTITY and entry.expands else name

    def _by_year(self, entry: Entry) -> dict[str, str]:
        """Return the columns that hold a PyPSA attribute of an entry's part by build year."""
        if home(entry.component_type) != ENTITY:
            return {}
        prefix = qualified(COHORT, EXT)
        held = {_attribute(entry, column.removeprefix(prefix)): column for column in self.by_year}
        return {attr: column for attr, column in held.items() if attr is not None}

    def _labels(self, dim: str, condition: str) -> list[Any]:
        rows = self.con.sql(f"SELECT {quoted(dim)} FROM {self.t}_{dim} WHERE {condition} LIMIT 5")
        return [label for (label,) in rows.fetchall()]

    def _require_mapped(self) -> None:
        """Raise for a label of the record that the table has no entry or no reading for."""
        refusals = list(READ_REFUSALS)
        for dim, shapes in SHAPES.items():
            for suffix, taken in shapes.items():
                shaped = [c for c in self.columns[dim] if c.endswith(suffix)]
                unread = " OR ".join(f"{quoted(c)} != {text(taken)}" for c in shaped)
                refusals.append((dim, unread or "false", f"a {suffix} other than {taken}"))
        for dim, condition, why in refusals:
            labels = self._labels(dim, condition)
            if labels:
                raise refused(dim, why, labels)
        rates = f"SELECT _carrier, count(DISTINCT COALESCE(_co2, 0)) AS n FROM {self.t}_entity"
        rates = f"{rates} WHERE {INVENTED} IS NOT TRUE GROUP BY 1"
        apart = self.con.sql(f"SELECT _carrier FROM ({rates}) WHERE n > 1").fetchall()
        if apart:
            raise refused("Carrier", "one type and fuel with several CO2 rates", sum(apart, ()))

    def _restored(self, entry: Entry) -> dict[str, str]:
        """Return the columns that hold a PyPSA attribute of an entry's part, by attribute."""
        dim = home(entry.component_type)
        held: dict[str, str] = {}
        for prefix in dict.fromkeys([qualified(dim, EXT), qualified(dim, RESULT), EXT]):
            for column in self.columns[dim]:
                kept = column.removeprefix(prefix)
                if not column.startswith(prefix) or kept in EXT_DTYPES:
                    continue
                attr = _attribute(entry, kept)
                if attr is not None:
                    held[attr] = column
        return held

    def _component(self, i: int, defaults: pd.DataFrame, attrs: Iterable[str]) -> str:
        """Return SQL for the components that entry `i` rebuilds, a column per name in `attrs`.

        A technology that is built in several years is a component per year, with the values
        the record has for that year.
        """
        entry = ENTRIES[i]
        dim = home(entry.component_type)
        restored = self._restored(entry)
        by_year = self._by_year(entry)
        marks = TYPED | entry.marks
        if dim == ENTITY and marks["og_entity"] == ENTITY:
            marks["og_entity"] = _of_a_year(ENTITY)
        columns = [f"{self._name(entry)} AS name", f"{i} AS _order", "_pos"]
        columns += [f"CAST({marks[mark]} AS VARCHAR) AS {mark}" for mark in OG_COLUMNS]
        for attr in attrs:
            static = attr not in defaults.index or defaults.at[attr, "static"]
            if attr in entry.read:
                value = entry.read[attr]
            elif attr == "carrier" and dim == ENTITY:
                value = "_carrier"
            elif attr in restored and attr in defaults.index and static:
                value = f"COALESCE({quoted(restored[attr])}, {_default(defaults, attr)})"
            elif attr in restored and static:
                value = quoted(restored[attr])
            elif attr in defaults.index:
                value = _default(defaults, attr)
            else:
                value = "NULL"
            if attr in by_year:
                value = f"COALESCE({quoted(by_year[attr])}, {value})"
            if attr == "build_year" and dim == ENTITY:
                value = f"COALESCE(_built, {value})"
            columns.append(f"{value} AS {quoted(attr)}")
        once = "" if entry.expands or dim != ENTITY else " AND _first_cohort"
        return f"SELECT {', '.join(columns)} FROM {self._table_of(dim)} WHERE {entry.stored}{once}"

    def _static(self, cls: str, defaults: pd.DataFrame) -> pd.DataFrame:
        """Return the static frame of PyPSA class `cls`, a row per component of the record."""
        entries = _of(cls)
        held = [
            attr
            for _, entry in entries
            for attr in [*entry.read, *self._restored(entry), *self._by_year(entry)]
        ]
        described = [attr for attr in ("carrier", "build_year") if attr in defaults.index]
        attrs = [
            attr
            for attr in dict.fromkeys([*described, *held])
            if attr not in defaults.index or defaults.at[attr, "static"]
        ]
        selects = [self._component(i, defaults, attrs) for i, _ in entries]
        frame = self.con.sql(" UNION ALL ".join(selects) + " ORDER BY _order, _pos, name").df()
        frame = frame.set_index("name").drop(columns=["_order", "_pos"])
        custom = [c for c in frame.columns if c not in defaults.index and c not in OG_COLUMNS]
        frame = frame.drop(columns=[c for c in custom if frame[c].isna().all()])
        texts = [c for c in custom if c in frame and kind(frame[c].dtype) == "str"]
        frame[texts] = frame[texts].fillna("")
        typed = frame.columns.intersection(defaults.index).difference(["geometry"])
        return frame.astype(defaults.dtype[typed].to_dict())

    def _series(self, i: int, attr: str, default: str) -> list[str]:
        """Return SQL for the rows of series `attr` of the components of entry `i`, per source.

        A component built in a later period has `default`, PyPSA's, in the periods before.
        """
        entry = ENTRIES[i]
        dim = home(entry.component_type)
        table = self._table_of(dim)
        name = self._name(entry)
        built = (
            "CASE WHEN _built IS NULL OR snapshot.period >= _built THEN {value} ELSE {default} END"
        )
        if dim != ENTITY or PERIOD not in self.schema.dimensions:
            built = "{value}"
        parts = []
        stored = entry.series.get(attr)
        placed = None if stored is None else qualified(dim, TIME_SERIES_PREFIX + stored.name)
        if stored is not None and stored.read is not None and placed in self.series:
            key = stored.key or quoted(dim)
            joined = f"{self.series[placed]} s JOIN {table} w ON w.{key} = s.{quoted(dim)}"
            rows = f"SELECT s.snapshot, s.value, w.* FROM {joined}"
            value = built.format(value=stored.read, default=default)
            select = f"SELECT snapshot, {name} AS name, {value} AS value FROM ({rows})"
            parts.append(f"{select} WHERE {entry.stored}")
        for prefix in (SERIES, RESULT):
            view = self.series.get(qualified(dim, prefix + _prefix(entry) + attr))
            if view is None:
                continue
            joined = f"{view} s JOIN {table} w ON w.{quoted(dim)} = s.{quoted(dim)}"
            rows = f"SELECT s.snapshot, s.value, w.* FROM {joined}"
            value = built.format(value="value", default=default)
            select = f"SELECT snapshot, {name} AS name, {value} AS value FROM ({rows})"
            parts.append(f"{select} WHERE {entry.stored}")
        return parts

    def _dynamic(self, c: Any, snapshots: pd.Index) -> dict[str, pd.DataFrame]:
        """Return the series of the PyPSA components `c` that the record holds, by attribute."""
        frames: dict[str, pd.DataFrame] = {}
        names = c.static.index
        numbered = pa.table({"name": pa.array(names), "_code": np.arange(len(names))})
        codes = self._view(f"names_{c.name}", self.con.from_arrow(numbered))
        for attr in c.defaults.index[c.defaults.varying]:
            default = _default(c.defaults, attr)
            parts = [part for i, _ in _of(c.name) for part in self._series(i, attr, default)]
            if not parts:
                continue
            placed = f"({' UNION ALL '.join(parts)}) s JOIN {codes} k ON k.name = s.name"
            placed = f"{placed} JOIN {self.snapshots} p ON p.snapshot = s.snapshot"
            held = self.con.sql(
                f"SELECT p._pos, k._code, s.value FROM {placed} WHERE s.value IS NOT NULL"
            ).fetchnumpy()
            columns, column = np.unique(held["_code"], return_inverse=True)
            if len(columns) == 0:
                continue
            wide = np.full((len(snapshots), len(columns)), np.nan)
            wide[held["_pos"], column] = held["value"]
            frames[attr] = pd.DataFrame(wide, index=snapshots, columns=names[columns])
        return frames

    def _weightings(self, n: pypsa.Network) -> None:
        """Set the weightings of snapshots and investment periods that the record holds."""
        for column in WEIGHTINGS:
            name = qualified(SNAPSHOT, WEIGHTING + column)
            if name not in self.flags:
                continue
            rows = self._view(f"weighting_{column}", self.record.attributes[name])
            placed = f"{rows} w JOIN {self.snapshots} p ON p.snapshot = w.snapshot"
            held = self.con.sql(f"SELECT p._pos, w.value FROM {placed}").fetchnumpy()
            weights = n.snapshot_weightings[column].to_numpy(copy=True)
            weights[held["_pos"]] = held["value"]
            n.snapshot_weightings[column] = weights
        for column in PERIOD_WEIGHTINGS:
            name = qualified(PERIOD, WEIGHTING + column)
            if name not in self.flags:
                continue
            rows = self.record.attributes[name].df()
            n.investment_period_weightings.loc[rows[PERIOD], column] = rows["value"].to_numpy()

    def _add(self, n: pypsa.Network, cls: str, static: pd.DataFrame) -> None:
        """Add the components of `static` to `n`, with their `og_` columns."""
        c = n.components[cls]
        marks = static.reindex(columns=list(OG_COLUMNS)).astype(object)
        inputs = static.drop(columns=list(OG_COLUMNS), errors="ignore")
        n.add(cls, inputs.index, **{column: inputs[column].to_numpy() for column in inputs})
        held = c.static.reindex(columns=list(OG_COLUMNS)).astype(object)
        held.update(marks.where(marks.notna(), np.nan))
        c.static[list(OG_COLUMNS)] = held.where(held.notna(), np.nan)

    def _whole(self, cls: str, rows: list[dict[str, Any]], defaults: pd.DataFrame) -> pd.DataFrame:
        """Return the components of `cls` that the record keeps whole, as a static frame."""
        frame = pd.DataFrame.from_records(rows).set_index("name")
        for column in frame.columns.intersection(defaults.index):
            default = defaults.at[column, "default"]
            filled = frame[column] if pd.isna(default) else frame[column].fillna(default)
            frame[column] = filled.astype(defaults.at[column, "dtype"])
        return frame

    def network(self) -> pypsa.Network:
        """Return the network the record describes."""
        meta = self.schema.meta.get(META, {})
        n = pypsa.Network(name=meta.get("name", ""))
        n.meta = meta.get("meta", {})
        if "crs" in meta:
            n.to_crs(meta["crs"])
        ordered = self.con.sql(f"SELECT snapshot FROM {self.snapshots} ORDER BY _pos")
        snapshots = _indexed(self.schema, ordered)
        if len(snapshots) > 0:
            n.set_snapshots(snapshots)
        self._weightings(n)
        carriers: list[pd.Series] = []
        for cls in SOURCES:
            c = n.components[cls]
            static = self._static(cls, c.defaults)
            if static.empty:
                c.static[list(OG_COLUMNS)] = pd.DataFrame(columns=list(OG_COLUMNS), dtype=object)
                continue
            if cls == "Shape":
                static["geometry"] = shapely.from_geojson(static.geometry.to_numpy())
            self._add(n, cls, static)
            if "carrier" in static:
                carriers.append(static["carrier"])
            for attr, frame in self._dynamic(c, n.snapshots).items():
                c.dynamic[attr] = frame.rename_axis(columns="name")
        for cls, rows in meta.get(COMPONENTS, {}).items():
            self._add(n, cls, self._whole(cls, rows, n.components[cls].defaults))
        rates = f"SELECT _carrier AS name, max(_co2) AS co2 FROM {self.t}_entity"
        co2 = self.con.sql(f"{rates} WHERE _co2 IS NOT NULL GROUP BY 1").df().set_index("name")
        if carriers:
            names = pd.Index(pd.concat(carriers).unique())
            n.add("Carrier", names, co2_emissions=co2["co2"].reindex(names).fillna(0).to_numpy())
        if "objective" in meta:
            n._objective = meta["objective"]
            n._objective_constant = meta["objective_constant"]
        self._release()
        return n

    def _release(self) -> None:
        for table in self.tables:
            self.con.execute(f"DROP TABLE {table}")
        for view in self.views:
            self.con.unregister(view)


class _Scenario:
    """A record with scenarios as the record of one: each series of it, or of every scenario."""

    def __init__(self, record: RecordLike, scenario: str) -> None:
        self.con = record.con
        self._record = record
        self._scenario = scenario
        dumped = record.schema.model_dump()
        spread = {name for name, spec in record.schema.attributes.items() if SCENARIO in spec.dims}
        static = sorted(
            name
            for name in spread - {SCENARIO_WEIGHT}
            if SNAPSHOT not in record.schema.attributes[name].dims
        )
        if static:
            raise refused(
                SCENARIO, "a value that is no time series and differs by scenario", static
            )
        self._spread = spread - {SCENARIO_WEIGHT}
        del dumped["dimensions"][SCENARIO]
        dumped["attributes"].pop(SCENARIO_WEIGHT, None)
        for name in self._spread:
            dumped["attributes"][name]["dims"] = set(dumped["attributes"][name]["dims"]) - {
                SCENARIO
            }
        self.schema = Schema.model_validate(dumped)

    def _attribute(self, name: str) -> DuckDBPyRelation:
        rows = self._record.attributes[name]
        if name not in self._spread:
            return rows
        held = rows.filter(f"scenario IS NULL OR scenario = {text(self._scenario)}")
        return held.project("* EXCLUDE (scenario)")

    @property
    def dims(self) -> LazyRelations:
        named = tuple(dim for dim in self._record.dims if dim != SCENARIO)
        return LazyRelations(named, lambda dim: self._record.dims[dim])

    @property
    def properties(self) -> LazyRelations:
        named = tuple(self._record.properties)
        return LazyRelations(named, lambda dim: self._record.properties[dim])

    @property
    def attributes(self) -> LazyRelations:
        named = tuple(name for name in self._record.attributes if name != SCENARIO_WEIGHT)
        return LazyRelations(named, self._attribute)

    def flags(self, **categories: str | Sequence[str]) -> dict[str, Flags]:
        held = self._record.flags(**categories)
        return {
            name: Flags(flag.varies - {SCENARIO}, flag.broadcast - {SCENARIO}, flag.breakpoints)
            for name, flag in held.items()
            if name != SCENARIO_WEIGHT
        }


def _stochastic(record: RecordLike) -> pypsa.Network:
    """Return the network of a record with scenarios: one network per scenario, as one."""
    scenarios = [label for (label,) in record.dims[SCENARIO].fetchall()]
    networks = {scenario: _Import(_Scenario(record, scenario)).network() for scenario in scenarios}
    weights = pd.Series(1 / len(scenarios), index=scenarios)
    if SCENARIO_WEIGHT in record.attributes:
        held = record.attributes[SCENARIO_WEIGHT].df().set_index(SCENARIO)["value"]
        weights = held.reindex(scenarios)
    dynamics = {
        (c.name, attr): pd.concat(
            {scenario: m.components[c.name].dynamic[attr] for scenario, m in networks.items()},
            axis=1,
            names=[SCENARIO, "name"],
        )
        for c in networks[scenarios[0]].components
        for attr, frame in c.dynamic.items()
        if not frame.empty
    }
    n = networks[scenarios[0]]
    objective = (n._objective, n._objective_constant) if n.is_solved else None
    n.set_scenarios(weights.to_dict())
    for (cls, attr), frame in dynamics.items():
        n.components[cls].dynamic[attr] = frame
    if objective is not None:
        n._objective, n._objective_constant = objective
    return n


class OGSchemaTool:
    """PyPSA's view of a record whose schema follows OGSchema.

    A PyPSA component class, or a topology, that the table in `mapping` has no entry for
    raises `UnsupportedRecordError`.
    """

    name = NAME

    def build(self, record: RecordLike) -> pypsa.Network:
        """Build the network an OGSchema record describes.

        Every component gets its carrier, named for its type, prime mover, fuel, storage
        technology and technology group, and the `og_` columns that `to_datarecord` reads.
        Values per unit of the device base are scaled by `base_power`.
        """
        if record.schema.meta.get("format") != FORMAT:
            named = record.schema.meta.get("format")
            raise ValueError(f"The record's `schema.meta['format']` is {named!r}, not {FORMAT!r}.")
        if SCENARIO in record.schema.dimensions:
            return _stochastic(record)
        return _Import(record).network()

    def to_datarecord(
        self,
        n: pypsa.Network,
        con: DuckDBPyConnection,
        *,
        results_only: bool = False,
        base: RecordLike | None = None,
    ) -> RecordLike:
        """Present a classified network as the OGSchema record that `store.commit` writes.

        The schema is the manifest of the component types the network holds, with the
        `ext__pypsa__` names it needs and `ext__technology_group` where a component has one.
        A network with investment periods has the dims `period` and `timestep`, and the
        weightings of its periods as `period__ext__pypsa__weighting_*`. With `results_only`
        the record is a layer over `base` that holds the results alone, at every snapshot
        of `base`. A network with scenarios has the dim `scenario`, with a static value
        that differs between scenarios refused.
        """
        if results_only and base is None:
            raise ValueError("`results_only=True` needs `base`, the record the results go over.")
        export = _Stochastic(n, con) if n.has_scenarios else _Export(n, con)
        if results_only:
            return export.results(base)
        return export.record(base)


OGSchema = OGSchemaTool()

__all__ = ["OGSchema", "OGSchemaTool", "Technology", "classify"]
