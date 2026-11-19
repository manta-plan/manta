# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The table that maps PyPSA components to OGSchema component types, in both directions.

Each `Entry` pairs the components of one PyPSA class that fit a condition with one OGSchema
type. It holds a SQL expression per OGSchema name, read from the PyPSA frame, and one per
PyPSA attribute, read from the record. The tool in `pypsa` only walks this table, so a new
type is a new entry.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from playbook_library.ogschema.manifest import COHORT

NATURAL = "'NATURAL_UNITS'"
INF = "'inf'::DOUBLE"
FUNCTION = "__function_data__function_type"
SLOPE = "__function_data__proportional_term"
INTERCEPT = "__function_data__constant_term"

SOURCES = {
    "Bus": "buses",
    "Generator": "generators",
    "Load": "loads",
    "StorageUnit": "storage_units",
    "Store": "stores",
    "Line": "lines",
    "Link": "links",
    "GlobalConstraint": "global_constraints",
    "Shape": "shapes",
}
"""The PyPSA classes the table covers, each with the name of its frame in the SQL of an entry."""

CARRIED = ("Generator", "Load", "StorageUnit", "Store", "Line", "Link")
"""The classes whose components have a carrier, and so may emit."""

KEPT = ("GlobalConstraint",)
"""The classes whose components without an OGSchema type are kept whole beside the record."""

ON_BUS = (", b.og_part AS bus_part", "LEFT JOIN buses_frame b ON b.name = c.bus")
BRANCH_ENDS = (
    ", b0.og_type AS type0, b1.og_type AS type1, b0.v_nom AS v_nom0,"
    " b0.og_part AS part0, b1.og_part AS part1",
    "LEFT JOIN buses_frame b0 ON b0.name = c.bus0 LEFT JOIN buses_frame b1 ON b1.name = c.bus1",
)
PEAKS = "(SELECT name, max(value) AS peak FROM loads__p_set GROUP BY name) peaks"
JOINS = {
    "Generator": ON_BUS,
    "StorageUnit": ON_BUS,
    "Store": ON_BUS,
    "Load": (
        f"{ON_BUS[0]}, COALESCE(peaks.peak, c.p_set) AS peak",
        f"{ON_BUS[1]} LEFT JOIN {PEAKS} ON peaks.name = c.name",
    ),
    "Line": BRANCH_ENDS,
    "Link": BRANCH_ENDS,
    "GlobalConstraint": (
        ", (SELECT list(name) FROM emitting WHERE co2 != 0) AS emitters,"
        " limited.covered, limited.covered_buses, limited.kinds, limited.parts,"
        " COALESCE(CAST(lasting.years AS DOUBLE), 1) AS years",
        "LEFT JOIN limited ON limited.name = c.name"
        " LEFT JOIN periods lasting ON CAST(lasting.period AS BIGINT) = c.investment_period",
    ),
}
"""Per PyPSA class, the columns its frame gains for the entries, and the joins that give them."""

BUSES = {"AC": "ACBus", "DC": "DCBus"}
"""The OGSchema type of a bus by its PyPSA carrier, unless `classify` is given another."""

BRANCHES = {
    "Line": {"ACBus-ACBus": "Line", "DCBus-DCBus": "TModelHVDCLine"},
    "Link": {
        "ACBus-DCBus": "InterconnectingConverter",
        "DCBus-ACBus": "InterconnectingConverter",
        "ACBus-ACBus": "TwoTerminalGenericHVDCLine",
    },
}
"""The operations type of a branch by the types of its two buses."""

NOMINAL = {
    "Generator": ("p_nom", "bus"),
    "StorageUnit": ("p_nom", "bus"),
    "Store": ("e_nom", "bus"),
    "Line": ("s_nom", "bus0"),
    "Link": ("p_nom", "bus0"),
}
"""The capacity PyPSA sizes of each class, and the bus a limit on that capacity counts it at."""

EXTENDABLE = (
    "SELECT name, carrier, {bus} AS bus, unnest(COALESCE(cohorts, [build_year])) AS build_year,"
    " lifetime, og_carrier, _component_type IS NULL OR '{nom}' = 'e_nom' AS part"
    " FROM {source} WHERE {nom}_extendable"
)
LIMITED = """
SELECT g.name, list(DISTINCT x.name ORDER BY x.name) AS covered,
    count(DISTINCT x.bus) AS covered_buses,
    count(DISTINCT x.og_carrier) AS kinds, count(*) FILTER (WHERE x.part) AS parts
FROM constraints_frame g JOIN extendables x
    ON x.carrier = g.carrier_attribute AND g.bus IN ('', x.bus) AND (
        g.investment_period IS NULL OR (
            x.build_year <= g.investment_period
            AND g.investment_period < x.build_year + x.lifetime
        )
    )
WHERE g.type = 'tech_capacity_expansion_limit'
GROUP BY g.name
"""
"""The extendable components each limit on the capacity of a carrier covers, as PyPSA counts.

PyPSA sums the capacity of the extendable components of the carrier, at the bus of the limit
if it names one, that are active in its investment period. A technology is covered if one of
the years it is built in is. A store, whose capacity is energy, counts as a part: OGSchema
limits power.
"""

COHORTS = """
SELECT label, list(build_year ORDER BY build_year) AS cohorts,
    CASE WHEN bool_or(limited) THEN CAST(to_json(map(
        list(CAST(CAST(build_year AS DOUBLE) AS VARCHAR) ORDER BY build_year),
        list(struct_pack(min := _min, max := NULLIF(_max, 'inf'::DOUBLE)) ORDER BY build_year)
    )) AS VARCHAR) END AS limits_by_year
FROM {source}_cohorts GROUP BY label
"""
"""Per technology of a frame, the years it is built in, and its limits by year if they differ.

The limits are the JSON text of a `MinMaxByKey`, whose key we read as the build year.
"""

NO_COHORTS = (
    "SELECT NULL::VARCHAR AS label, NULL::BIGINT AS build_year, NULL::DOUBLE AS _min,"
    " NULL::DOUBLE AS _max, false AS limited WHERE false"
)
BY_YEAR = "'$.\"' || CAST(CAST(_built AS DOUBLE) AS VARCHAR) || '\"'"

EXT_DTYPES = {
    "from_dc": "bool",
    "no_bus": "bool",
    "component": "str",
    "idx": "str",
    "standard_type": "str",
    "bus__name": "str",
    "charge__name": "str",
    "charge__discount_rate": "float",
    "discharge__name": "str",
    "discharge__discount_rate": "float",
    "shedding__name": "str",
    "shedding__p_nom": "float",
    "shedding__sign": "float",
}
"""The `ext__pypsa__` names the entries write themselves, with their dtype."""

LABEL_DTYPES = {"ext__technology_group": "str", "ext__invented_candidate": "bool"}
"""The `ext__` names that are no PyPSA value but a label of this library, with their dtype."""

KIND = (
    "concat_ws(' - ', CAST(og_type AS VARCHAR), CAST(og_prime_mover_type AS VARCHAR),"
    " CAST(og_fuel AS VARCHAR), CAST(og_technology_group AS VARCHAR))"
)
DEVICES = f"""
WITH kinds AS (SELECT *, {KIND} AS kind FROM generators WHERE og_part IS NULL),
candidates AS (
    SELECT bus, kind, min(name) AS technology FROM kinds WHERE p_nom_extendable GROUP BY bus, kind
),
fixed AS (
    SELECT k.name, k.kind, c.technology, CAST(k.og_type AS VARCHAR) AS og_type,
        CAST(k.og_prime_mover_type AS VARCHAR) AS og_prime_mover_type,
        CAST(k.og_fuel AS VARCHAR) AS og_fuel,
        CAST(k.og_technology_group AS VARCHAR) AS og_technology_group,
        NULLIF(k.build_year, 0) AS built,
        CASE WHEN isfinite(k.lifetime)
            THEN CAST(k.build_year + round(k.lifetime) AS BIGINT) END AS retired
    FROM kinds k LEFT JOIN candidates c ON c.bus = k.bus AND c.kind = k.kind
    WHERE NOT k.p_nom_extendable
        AND k.og_type IN ('ThermalStandard', 'RenewableDispatch', 'HydroDispatch')
),
dated AS (
    SELECT DISTINCT kind FROM fixed
    WHERE technology IS NULL AND (built IS NOT NULL OR retired IS NOT NULL)
)
SELECT f.* REPLACE (COALESCE(f.technology, 'invented ' || d.kind) AS technology),
    f.technology IS NULL AS invented
FROM fixed f LEFT JOIN dated d ON d.kind = f.kind
WHERE f.technology IS NOT NULL OR d.kind IS NOT NULL
"""
YEARS = (
    "CAST(to_json(map(list(name ORDER BY name) FILTER (WHERE {year} IS NOT NULL),"
    " list({year} ORDER BY name) FILTER (WHERE {year} IS NOT NULL))) AS VARCHAR)"
)
DEVICE_FRAMES = {
    "devices": DEVICES,
    "invented": "SELECT technology AS name, any_value(og_type) AS og_type,"
    " any_value(og_prime_mover_type) AS og_prime_mover_type, any_value(og_fuel) AS og_fuel,"
    " any_value(og_technology_group) AS og_technology_group,"
    " row_number() OVER (ORDER BY technology) AS _pos"
    " FROM devices WHERE invented GROUP BY technology",
    "technologies": "SELECT technology AS name, string_agg(name, '|' ORDER BY name) AS devices,"
    f" {YEARS.format(year='built')} AS build_years,"
    f" {YEARS.format(year='retired')} AS retirement_years,"
    " row_number() OVER (ORDER BY technology) AS _pos FROM devices GROUP BY technology",
}
"""The frames that say which technology each generator of fixed capacity is a device of.

A generator is a device of the extendable generator of its type, prime mover, fuel and
group at its bus. Without one, it is a device of a technology invented for those four, if
any generator of them has a year it was built in or a finite lifetime.
"""

Fields = tuple[Mapping[str, str], Mapping[str, str]]
"""The SQL that writes OGSchema names from a PyPSA frame, and PyPSA attributes from a record."""


@dataclass(frozen=True)
class Technology:
    """How the components of one PyPSA carrier are typed in OGSchema.

    `group` tells apart two carriers of one type, prime mover and fuel, such as fixed and
    tracking solar. `storage_tech` is the storage technology of a storage unit or a store.
    """

    og_type: str
    prime_mover_type: str | None = None
    fuel: str | None = None
    group: str | None = None
    storage_tech: str | None = None


@dataclass(frozen=True)
class Series:
    """A PyPSA series kept as the OGSchema time series `name`.

    `write` gives the stored value from `value`, the PyPSA one, and the columns of the PyPSA
    frame. `read` reverses it from `value`, the stored one, and the columns of the record.
    An entry with one of them None leaves that direction to another entry. `key` names the
    column of the record that has the label the series is stored at, if not the entity's own.
    """

    name: str
    write: str | None = "value"
    read: str | None = "value"
    key: str | None = None


@dataclass(frozen=True)
class Entry:
    """The rows of one frame that become, or add to, components of one OGSchema type.

    `source` names the frame and `where` selects its rows. `label` gives the component each
    row describes. An entry with `axis` adds that component, and one without adds fields to
    a component of another entry: the PyPSA component is then a part of it, and `role` names
    the part in the `ext__pypsa__<role>__` names that keep what OGSchema has no field for.
    `write` maps a field of the type, by its name in the manifest less the prefix of its dim,
    to SQL over the frame. `tuples` maps a multi-dim to SQL per coordinate.

    `cls` is the PyPSA class that `read` rebuilds, a PyPSA attribute to SQL over the record's
    columns each, for the components that `fits` holds for. `name` gives the PyPSA name, the
    label unless given. `marks` gives the `og_` columns that differ from those of the type.
    `og_type` is the operations type, where `component_type` is a technology. A technology
    built in several years is rebuilt as a component per year, unless the entry does not
    `expand`: the part is then one for all its years.
    """

    source: str
    component_type: str
    where: str = "true"
    label: str = "name"
    role: str = ""
    axis: bool = True
    cls: str | None = None
    og_type: str | None = None
    fits: str = "true"
    name: str | None = None
    expands: bool = True
    marks: Mapping[str, str] = field(default_factory=dict)
    write: Mapping[str, str] = field(default_factory=dict)
    read: Mapping[str, str] = field(default_factory=dict)
    series: Mapping[str, Series] = field(default_factory=dict)
    tuples: Mapping[str, Mapping[str, str]] = field(default_factory=dict)

    @property
    def stored(self) -> str:
        """The condition that selects this entry's components among those of a record."""
        condition = f"component_type = '{self.component_type}' AND {self.fits}"
        if self.og_type is None:
            return condition
        return f"{condition} AND power_systems_type = '{self.og_type}'"


def component(cls: str, component_type: str, where: str, *fields: Fields, **given: Any) -> Entry:
    """Return the entry of the components of PyPSA class `cls` that fit `where`.

    `given` sets any other field of the entry.
    """
    write: dict[str, str] = {}
    read: dict[str, str] = {}
    for written, restored in fields:
        write |= written
        read |= restored
    tuples = dict(given.pop("tuples", {}))
    if cls in CARRIED and "role" not in given:
        tuples["entity_supplemental_attribute"] = {
            "entity": "name",
            "supplemental_attribute": "og_emissions",
        }
    if cls in NOMINAL and "role" not in given:
        tuples[COHORT] = {"entity": "name", "build_year": "unnest(cohorts)"}
    return Entry(
        source=SOURCES[cls],
        component_type=component_type,
        where=where,
        cls=cls,
        write=write,
        read=read,
        tuples=tuples,
        **given,
    )


def part(role: str) -> dict[str, str]:
    """Return the `og_` columns of a PyPSA component that is the part `role` of another."""
    marks = dict.fromkeys(["og_type", "og_prime_mover_type", "og_fuel", "og_storage_tech"], "NULL")
    return {**marks, "og_technology_group": "NULL", "og_part": f"'{role}'", "og_entity": "entity"}


def linear(prefix: str, slope: str, when: str = "true") -> dict[str, str]:
    """Return the fields of the curve at `prefix`, linear in its input, where `when` holds."""
    fields = {
        f"{prefix}__curve_type": "'INPUT_OUTPUT'",
        prefix + FUNCTION: "'LINEAR'",
        prefix + SLOPE: slope,
        prefix + INTERCEPT: "0",
    }
    return {name: f"CASE WHEN {when} THEN {expr} END" for name, expr in fields.items()}


def cost_curve(prefix: str, slope: str) -> Fields:
    """Return a CostCurve at `prefix`: `slope` per MWh, without VOM, read as `marginal_cost`."""
    write = {
        f"{prefix}__variable_cost_type": "'COST'",
        f"{prefix}__power_units": NATURAL,
        **linear(f"{prefix}__value_curve", slope),
        **linear(f"{prefix}__vom_cost", "0"),
    }
    cost = f"COALESCE({prefix}__value_curve{SLOPE}, 0)"
    read = {"marginal_cost": f"{cost} + COALESCE({prefix}__vom_cost{SLOPE}, 0)"}
    return write, read


def thermal_cost(prefix: str) -> Fields:
    """Return a ThermalGenerationCost at `prefix`: a heat rate, with every cost as VOM."""
    variable = f"{prefix}__variable_operation_cost"
    heat_rate = f"{variable}__value_curve{SLOPE}"
    write = {
        f"{prefix}__cost_type": "'THERMAL'",
        f"{variable}__variable_cost_type": "'FUEL'",
        f"{variable}__fuel_units": "'GJ'",
        f"{variable}__power_units": NATURAL,
        **linear(f"{variable}__value_curve", "3.6 / efficiency"),
        f"{variable}__fuel_cost": "0",
        **linear(f"{variable}__vom_cost", "marginal_cost"),
        f"{prefix}__fixed": "0",
        f"{prefix}__start_up": "start_up_cost",
        f"{prefix}__shut_down": "shut_down_cost",
    }
    per_mwh = f"CASE {variable}__fuel_units WHEN 'MMBTU' THEN 3.412 ELSE 3.6 END"
    vom = f"COALESCE({variable}__vom_cost{SLOPE}, 0)"
    fuel = f"COALESCE({variable}__fuel_cost, 0) * {heat_rate}"
    read = {
        "efficiency": f"{per_mwh} / {heat_rate}",
        "marginal_cost": f"{vom} + {fuel}",
        "start_up_cost": f"COALESCE({prefix}__start_up, 0)",
        "shut_down_cost": f"COALESCE({prefix}__shut_down, 0)",
    }
    return write, read


def heat_rate(prefix: str) -> dict[str, Series]:
    """Return the series of the heat rate of the fuel curve at `prefix`, read as `efficiency`."""
    variable = f"{prefix}__variable_operation_cost"
    per_mwh = f"CASE {variable}__fuel_units WHEN 'MMBTU' THEN 3.412 ELSE 3.6 END"
    stored = Series(
        f"{variable}__value_curve{SLOPE}", write="3.6 / value", read=f"{per_mwh} / value"
    )
    return {"efficiency": stored}


def priced(prefix: str) -> dict[str, Series]:
    """Return the series of the slope of the cost curve at `prefix`, read as `marginal_cost`."""
    variable = f"{prefix}__variable_operation_cost"
    cost = f"value + COALESCE({variable}__vom_cost{SLOPE}, 0)"
    return {"marginal_cost": Series(f"{variable}__value_curve{SLOPE}", read=cost)}


def production_cost(prefix: str, cost_type: str, slope: str = "marginal_cost") -> Fields:
    """Return the cost of type `cost_type` at `prefix`, whose variable part is one CostCurve."""
    write, read = cost_curve(f"{prefix}__variable_operation_cost", slope)
    return {f"{prefix}__cost_type": f"'{cost_type}'", **write}, read


def storage_cost(prefix: str) -> Fields:
    """Return a StorageCost at `prefix`, with the marginal cost on what is discharged."""
    write, read = cost_curve(f"{prefix}__discharge_variable_cost", "marginal_cost")
    fixed = {f"{prefix}__{name}": "0" for name in ("fixed", "start_up", "shut_down")}
    return {f"{prefix}__cost_type": "'STORAGE'", **fixed, **write}, read


def exchange_cost(prefix: str) -> Fields:
    """Return an ImportExportCost at `prefix`, with the marginal cost on what is imported."""
    write, read = cost_curve(f"{prefix}__import_offer_curves", "marginal_cost")
    free, _ = cost_curve(f"{prefix}__export_offer_curves", "0")
    limits = {f"{prefix}__energy_{way}_weekly_limit": "1e6" for way in ("import", "export")}
    return {f"{prefix}__cost_type": "'IMPORTEXPORT'", **write, **free, **limits}, read


def sizing(
    nom: str,
    limits: str,
    size: str,
    capital: str,
    per: str = "1",
    stored: str = "1",
    keyed: bool = False,
) -> Fields:
    """Return the limits, unit size and overnight cost of an extendable capacity named `nom`.

    `per` is the capacity OGSchema counts for each unit that PyPSA counts, as SQL over the
    PyPSA frame, and `stored` the same as SQL over the record. `keyed` limits may differ by
    build year: they are then one `MinMaxByKey` in place of the two bounds.
    """
    priced = "overnight_cost IS NOT NULL"
    plain = "limits_by_year IS NULL" if keyed else "true"
    write = {
        f"{limits}__min": f"CASE WHEN {plain} THEN {nom}_min * {per} END",
        f"{limits}__max": f"CASE WHEN {plain} THEN NULLIF({nom}_max, {INF}) * {per} END",
        size: f"NULLIF({nom}_mod * {per}, 0)",
        **linear(capital, f"overnight_cost / {per}", when=priced),
    }
    bounds = {"min": f"COALESCE({limits}__min, 0)", "max": f"COALESCE({limits}__max, {INF})"}
    if keyed:
        write[limits] = "limits_by_year"
        by_year = f"CAST(json_extract_string({limits}, {BY_YEAR} || '.{{bound}}') AS DOUBLE)"
        defaults = {"min": "0", "max": INF}
        bounds = {
            bound: f"CASE WHEN {limits} IS NULL THEN {value}"
            f" ELSE COALESCE({by_year.format(bound=bound)}, {defaults[bound]}) END"
            for bound, value in bounds.items()
        }
    read = {
        f"{nom}_extendable": "true",
        f"{nom}_min": f"{bounds['min']} / {stored}",
        f"{nom}_max": f"{bounds['max']} / {stored}",
        f"{nom}_mod": f"COALESCE({size}, 0) / {stored}",
        "overnight_cost": f"{capital}{SLOPE} * {stored}",
    }
    return write, read


def technology(
    nom: str,
    limits: str = "capacity_limits",
    size: str = "unit_size",
    capital: str = "capital_costs__capital_cost",
    keyed: bool = False,
) -> Fields:
    """Return the fields every Investments technology has, for a capacity named `nom`.

    `keyed` limits may differ by build year.
    """
    write, read = sizing(nom, limits, size, capital, keyed=keyed)
    written = {
        "power_systems_type": "og_type",
        "available": "active",
        "financial_data__discount_rate": "discount_rate",
    }
    restored = {
        "active": "COALESCE(available, true)",
        "discount_rate": "financial_data__discount_rate",
    }
    return {**written, **write}, {**restored, **read}


def chain_link(role: str, side: str, at_grid: bool) -> Fields:
    """Return the fields a link adds to the storage it charges or discharges, as part `role`.

    `side` is `in` or `out`, the efficiency of the storage that is the link's. A link that is
    not sized `at_grid` has its capacity at the storage, so OGSchema counts it less its loss.
    """
    efficiency = f"COALESCE(efficiency__{side}, 1)"
    limits = f"capacity_limits_{role}"
    capital = f"capital_costs__{role}_capital_cost"
    per = ("1", "1") if at_grid else ("efficiency", efficiency)
    write, read = sizing("p_nom", limits, f"unit_size_{role}", capital, *per, keyed=at_grid)
    written = {
        f"ext__pypsa__{role}__name": "name",
        f"ext__pypsa__{role}__discount_rate": "discount_rate",
        f"efficiency__{side}": "efficiency",
    }
    rate = f"COALESCE(ext__pypsa__{role}__discount_rate, financial_data__discount_rate)"
    restored = {"efficiency": efficiency, "discount_rate": rate}
    carrier = {"carrier": f"_carrier || ' - {role}'"}
    return {**written, **write}, {**restored, **carrier, **read}


def device(nom: str) -> Fields:
    """Return the fields of an Operations device rated at its fixed capacity `nom`."""
    write = {"available": "active", "rating": nom, "base_power": nom, "power_units": NATURAL}
    read = {
        "active": "COALESCE(available, true)",
        nom: "rating * _scale",
        f"{nom}_extendable": "false",
    }
    return write, read


SUPPLY: Fields = (
    {
        "prime_mover_type": "og_prime_mover_type",
        "fuel": "og_fuel",
        "min_generation_fraction": "p_min_pu",
        "lifetime": f"round(NULLIF(lifetime, {INF}))",
    },
    {
        "bus": "_region_bus",
        "p_min_pu": "COALESCE(min_generation_fraction, 0)",
        "lifetime": f"COALESCE(lifetime, {INF})",
    },
)
STORAGE: Fields = (
    {
        "prime_mover_type": "og_prime_mover_type",
        "storage_tech": "og_storage_tech",
        "losses": "standing_loss",
        "lifetime": f"NULLIF(lifetime, {INF})",
    },
    {"standing_loss": "COALESCE(losses, 0)", "lifetime": f"COALESCE(lifetime, {INF})"},
)
BATTERY: Fields = (
    {
        "efficiency__in": "efficiency_store",
        "efficiency__out": "efficiency_dispatch",
        "duration_limits__min": "max_hours * 60",
        "duration_limits__max": "max_hours * 60",
    },
    {
        "bus": "_region_bus",
        "efficiency_store": "COALESCE(efficiency__in, 1)",
        "efficiency_dispatch": "COALESCE(efficiency__out, 1)",
        "max_hours": "duration_limits__max / 60",
    },
)
INJECTOR: Fields = (
    {"bus": "bus", "active_power": "COALESCE(p_set, 0)", "reactive_power": "0"},
    {
        "bus": "bus",
        "build_year": "COALESCE(_build_year, 0)",
        "lifetime": f"COALESCE(_retirement_year - COALESCE(_build_year, 0), {INF})",
    },
)
LIMITS: Fields = (
    {
        "active_power_limits__min": "p_nom * p_min_pu",
        "active_power_limits__max": "p_nom * p_max_pu",
    },
    {
        "p_min_pu": "COALESCE(active_power_limits__min / NULLIF(rating, 0), 0)",
        "p_max_pu": "COALESCE(active_power_limits__max / NULLIF(rating, 0), 1)",
    },
)
NODES: Fields = (
    {"start_node": "bus0", "end_node": "bus1"},
    {"bus0": "start_node", "bus1": "end_node"},
)
ARC: Fields = ({"arc": "bus0 || ' -> ' || bus1"}, {"bus0": "_arc_from", "bus1": "_arc_to"})
UNTYPED_LINE: Fields = ({"ext__pypsa__standard_type": "NULLIF(type, '')"}, {"type": "''"})
LOSSY: Fields = (
    linear("line_loss", "1 - efficiency"),
    {"efficiency": f"1 - COALESCE(line_loss{SLOPE}, 0)"},
)
BUS: Fields = (
    {"base_voltage": "v_nom", "number": "_pos", "available": "true"},
    {
        "v_nom": "COALESCE(bus__base_voltage, 1)",
        "x": "COALESCE(CAST(json_extract(_geo_json, '$.coordinates[0]') AS DOUBLE), 0)",
        "y": "COALESCE(CAST(json_extract(_geo_json, '$.coordinates[1]') AS DOUBLE), 0)",
    },
)
LOAD: Fields = (
    {
        "bus": "bus",
        "available": "active",
        "max_active_power": "peak",
        "active_power": "p_set",
        "reactive_power": "q_set",
        "max_reactive_power": "0",
        "base_power": "peak",
        "power_units": NATURAL,
    },
    {
        "bus": "bus",
        "active": "COALESCE(available, true)",
        "p_set": "CASE WHEN _has_ts THEN active_power ELSE max_active_power END * _scale",
        "q_set": "COALESCE(reactive_power * _scale, 0)",
    },
)
SHEDDING: Fields = (
    {
        "ext__pypsa__shedding__name": "name",
        "ext__pypsa__shedding__p_nom": "p_nom",
        "ext__pypsa__shedding__sign": "NULLIF(sign, 1)",
    },
    {
        "bus": "bus",
        "p_nom": "COALESCE(ext__pypsa__shedding__p_nom, max_active_power * _scale)",
        "p_nom_extendable": "false",
        "sign": "COALESCE(ext__pypsa__shedding__sign, 1)",
        "carrier": "_carrier || ' - shedding'",
    },
)
SHEDDING_COST = production_cost("operation_cost", "LOAD", "marginal_cost / sign")
VALUE_OF_LOST_LOAD: Fields = (
    SHEDDING_COST[0],
    {"marginal_cost": f"({SHEDDING_COST[1]['marginal_cost']}) * {SHEDDING[1]['sign']}"},
)
CHAIN_BUS = "COALESCE(ext__pypsa__bus__name, entity || ' bus')"
RESERVOIR = "name || ' reservoir'"
HYDRO: Fields = (
    {
        "bus": "bus",
        "active_power": "0",
        "reactive_power": "0",
        "efficiency": "efficiency_dispatch",
        "prime_mover_type": "og_prime_mover_type",
    },
    {
        "bus": "bus",
        "efficiency_dispatch": "COALESCE(efficiency, 1)",
        "efficiency_store": "0",
        "max_hours": "COALESCE(_level_max / NULLIF(rating * _scale, 0), 1)",
        "state_of_charge_initial": "COALESCE(_initial_level, 0)",
        "inflow": "COALESCE(_inflow, 0)",
        "standing_loss": "COALESCE(_evaporative_loss, 0)",
        "spill_cost": "COALESCE(_spillage_cost, 0)",
    },
)
AVAILABILITY = {"p_max_pu": Series("max_active_power")}
DEMAND = {
    "p_set": Series(
        "max_active_power",
        write="CASE WHEN peak = 0 THEN 0 ELSE value / peak END",
        read="value * max_active_power * _scale",
    )
}
REGION = {"region": {"entity": "name", "bus": "bus"}}
FLOW = "operational_flow_limit"
AC = "type0 = 'ACBus' AND type1 = 'ACBus'"
DC = "type0 = 'DCBus' AND type1 = 'DCBus'"
AC_DC = "type0 != type1"
FREE = "duration_limits__min IS NULL"
CANDIDATE = "ext__invented_candidate IS NOT TRUE"
ATTACHED = "entity_supplemental_attribute"
STORED = "EnergyReservoirStorage"
CAPACITY_LIMIT = "MaximumCapacityRequirements"
TARGET_YEAR = "CAST(investment_period AS BIGINT)"
POINT = "json_extract_string({geo_json}, '$.type') = 'Point'"
OUTLINE = f"NOT COALESCE({POINT.format(geo_json='geo_json')}, false)"
RESERVOIR_HYDRO = (
    "og_type = 'HydroTurbine' AND NOT p_nom_extendable AND efficiency_store = 0 AND p_min_pu >= 0"
)


def extendable(nom: str, og_type: str, ends: str = "true") -> str:
    """Return the condition for an extendable component of operations type `og_type`."""
    return f"{nom}_extendable AND og_type = '{og_type}' AND {ends}"


def fixed(nom: str, og_type: str, ends: str = "true") -> str:
    """Return the condition for a component of fixed capacity and operations type `og_type`."""
    return f"NOT {nom}_extendable AND og_type = '{og_type}' AND {ends}"


ENTRIES: tuple[Entry, ...] = (
    component("Bus", "ACBus", "og_type = 'ACBus'", BUS, ({}, {"carrier": "'AC'"})),
    component("Bus", "DCBus", "og_type = 'DCBus'", BUS, ({}, {"carrier": "'DC'"})),
    Entry(
        source="buses",
        component_type="GeographicInfo",
        where="(x != 0 OR y != 0) AND og_part IS NULL",
        label="name || ' GeographicInfo'",
        write={"geo_json": "json_object('type', 'Point', 'coordinates', [x, y])"},
        tuples={
            "bus_supplemental_attribute": {
                "bus": "name",
                "supplemental_attribute": "name || ' GeographicInfo'",
            }
        },
    ),
    Entry(source="arcs", component_type="Arc", write={"from_id": "bus0", "to_id": "bus1"}),
    Entry(
        source="emitters",
        component_type="EmissionsData",
        label="'CO2 ' || name",
        write={
            "pollutant": "'CO2'",
            "basis": "'FUEL_INPUT'",
            "energy_unit": "'GJ'",
            "mass_unit": "'METRIC_TON'",
            "emission_rate__curve_type": "'INCREMENTAL'",
            "emission_rate" + FUNCTION: "'LINEAR'",
            "emission_rate" + INTERCEPT: "co2_emissions / 3.6",
            "emission_rate" + SLOPE: "0",
        },
    ),
    component(
        "Generator",
        "SupplyTechnology",
        extendable("p_nom", "ThermalStandard"),
        technology("p_nom", keyed=True),
        SUPPLY,
        thermal_cost("operation_costs"),
        og_type="ThermalStandard",
        fits=CANDIDATE,
        series=AVAILABILITY | heat_rate("operation_costs"),
        tuples=REGION,
    ),
    component(
        "Generator",
        "SupplyTechnology",
        extendable("p_nom", "RenewableDispatch"),
        technology("p_nom", keyed=True),
        SUPPLY,
        production_cost("operation_costs", "RENEWABLE"),
        og_type="RenewableDispatch",
        fits=CANDIDATE,
        series=AVAILABILITY | priced("operation_costs"),
        tuples=REGION,
    ),
    component(
        "Generator",
        "SupplyTechnology",
        extendable("p_nom", "HydroDispatch"),
        technology("p_nom", keyed=True),
        SUPPLY,
        production_cost("operation_costs", "RENEWABLE"),
        og_type="HydroDispatch",
        fits=CANDIDATE,
        series=AVAILABILITY | priced("operation_costs"),
        tuples=REGION,
    ),
    Entry(
        source="invented",
        component_type="SupplyTechnology",
        fits="ext__invented_candidate",
        write={
            "power_systems_type": "og_type",
            "prime_mover_type": "og_prime_mover_type",
            "fuel": "og_fuel",
            "ext__technology_group": "og_technology_group",
            "available": "true",
            "capacity_limits__min": "0",
            "capacity_limits__max": "0",
            "ext__invented_candidate": "true",
        },
    ),
    Entry(
        source="technologies",
        component_type="ExistingDevices",
        label="name || ' ExistingDevices'",
        write={"existing_devices": "devices"},
        tuples={
            ATTACHED: {"entity": "name", "supplemental_attribute": "name || ' ExistingDevices'"}
        },
    ),
    Entry(
        source="technologies",
        component_type="RetirementPotential",
        label="name || ' RetirementPotential'",
        write={
            "eligible_generators": "''",
            "build_year": "build_years",
            "planned_retirement_year": "retirement_years",
            **linear("retirement_cost", "0"),
        },
        tuples={
            ATTACHED: {"entity": "name", "supplemental_attribute": "name || ' RetirementPotential'"}
        },
    ),
    component(
        "Generator",
        "ThermalStandard",
        fixed("p_nom", "ThermalStandard"),
        device("p_nom"),
        INJECTOR,
        LIMITS,
        thermal_cost("operation_cost"),
        (
            {"status": "'ONLINE'", "prime_mover_type": "og_prime_mover_type", "fuel": "og_fuel"},
            {},
        ),
        series=heat_rate("operation_cost"),
    ),
    component(
        "Generator",
        "RenewableDispatch",
        fixed("p_nom", "RenewableDispatch"),
        device("p_nom"),
        INJECTOR,
        production_cost("operation_cost", "RENEWABLE"),
        ({"prime_mover_type": "og_prime_mover_type", "power_factor": "1"}, {}),
        series=AVAILABILITY | priced("operation_cost"),
    ),
    component(
        "Generator",
        "HydroDispatch",
        fixed("p_nom", "HydroDispatch"),
        device("p_nom"),
        INJECTOR,
        LIMITS,
        production_cost("operation_cost", "HYDRO_GEN"),
        ({"prime_mover_type": "og_prime_mover_type", "operation_cost__fixed": "0"}, {}),
        series=AVAILABILITY | priced("operation_cost"),
    ),
    component(
        "Generator",
        "Source",
        fixed("p_nom", "Source"),
        exchange_cost("operation_cost"),
        (
            {
                "bus": "bus",
                "available": "active",
                "power_units": NATURAL,
                "active_power_limits__min": "p_nom * p_min_pu",
                "active_power_limits__max": "p_nom",
            },
            {
                "bus": "bus",
                "active": "COALESCE(available, true)",
                "p_nom": "COALESCE(active_power_limits__max * _scale, 0)",
                "p_nom_extendable": "false",
                "p_min_pu": "COALESCE(active_power_limits__min"
                " / NULLIF(active_power_limits__max, 0), 0)",
            },
        ),
    ),
    component(
        "Generator",
        "InterruptiblePowerLoad",
        "og_part = 'shedding' AND NOT p_nom_extendable",
        SHEDDING,
        VALUE_OF_LOST_LOAD,
        role="shedding",
        label="og_entity",
        axis=False,
        name="COALESCE(ext__pypsa__shedding__name, entity || ' shedding')",
        marks={**part("shedding"), "og_type": "'InterruptiblePowerLoad'"},
    ),
    component("Load", "PowerLoad", "og_type = 'PowerLoad'", LOAD, series=DEMAND),
    component(
        "Load", "InterruptiblePowerLoad", "og_type = 'InterruptiblePowerLoad'", LOAD, series=DEMAND
    ),
    component(
        "StorageUnit",
        "StorageTechnology",
        extendable("p_nom", STORED),
        technology(
            "p_nom",
            "capacity_limits_discharge",
            "unit_size_discharge",
            "capital_costs__discharge_capital_cost",
            keyed=True,
        ),
        STORAGE,
        BATTERY,
        storage_cost("operation_costs"),
        og_type=STORED,
        fits=f"NOT ({FREE})",
        tuples=REGION,
    ),
    component(
        "StorageUnit",
        "HydroTurbine",
        RESERVOIR_HYDRO,
        device("p_nom"),
        LIMITS,
        HYDRO,
        production_cost("operation_cost", "HYDRO_GEN"),
        ({"operation_cost__fixed": "0"}, {}),
        series={"inflow": Series("inflow", write=None, key="_reservoir")},
    ),
    Entry(
        source="storage_units",
        component_type="HydroReservoir",
        where=RESERVOIR_HYDRO,
        label=RESERVOIR,
        write={
            "available": "active",
            "level_data_type": "'ENERGY'",
            "storage_level_limits__min": "0",
            "storage_level_limits__max": "p_nom * max_hours",
            "initial_level": "state_of_charge_initial",
            "inflow": "inflow",
            "outflow": "0",
            "intake_elevation": "0",
            "head_to_volume_factor__function_type": "'LINEAR'",
            "head_to_volume_factor__constant_term": "0",
            "head_to_volume_factor__proportional_term": "1",
            "operation_cost__cost_type": "'HYDRO_RES'",
            "operation_cost__spillage_cost": "spill_cost",
            "evaporative_loss": "standing_loss",
        },
        series={"inflow": Series("inflow", read=None)},
        tuples={"downstream_turbines": {"reservoir": RESERVOIR, "turbine": "name"}},
    ),
    component(
        "Store",
        "StorageTechnology",
        extendable("e_nom", STORED, "og_part = 'store'"),
        technology(
            "e_nom",
            "capacity_limits_energy",
            "unit_size_energy",
            "capital_costs__energy_capital_cost",
            keyed=True,
        ),
        STORAGE,
        ({"ext__pypsa__bus__name": "bus"}, {"bus": CHAIN_BUS}),
        og_type=STORED,
        fits=FREE,
        marks={"og_part": "'store'", "og_entity": "entity"},
    ),
    component(
        "Bus",
        "StorageTechnology",
        "og_part = 'bus'",
        ({}, {"carrier": "_carrier"}),
        role="bus",
        label="og_entity",
        axis=False,
        og_type=STORED,
        fits=f"{FREE} AND _first_on_bus",
        name=CHAIN_BUS,
        expands=False,
        marks=part("bus"),
    ),
    component(
        "Link",
        "StorageTechnology",
        "og_part = 'charge' AND p_nom_extendable",
        chain_link("charge", "in", at_grid=True),
        ({}, {"bus0": "_region_bus", "bus1": CHAIN_BUS}),
        role="charge",
        label="og_entity",
        axis=False,
        og_type=STORED,
        fits=FREE,
        name="COALESCE(ext__pypsa__charge__name, entity || ' charger')",
        marks=part("charge"),
        tuples={"region": {"entity": "og_entity", "bus": "bus0"}},
    ),
    component(
        "Link",
        "StorageTechnology",
        "og_part = 'discharge' AND p_nom_extendable",
        chain_link("discharge", "out", at_grid=False),
        ({}, {"bus0": CHAIN_BUS, "bus1": "_region_bus"}),
        role="discharge",
        label="og_entity",
        axis=False,
        og_type=STORED,
        fits=FREE,
        name="COALESCE(ext__pypsa__discharge__name, entity || ' discharger')",
        marks=part("discharge"),
    ),
    component(
        "Line",
        "NodalACTransportTechnology",
        extendable("s_nom", "Line", AC),
        technology("s_nom"),
        NODES,
        UNTYPED_LINE,
        (
            {"reactance": "x", "resistance": "r", "voltage": "v_nom0"},
            {"x": "COALESCE(reactance, 0)", "r": "COALESCE(resistance, 0)"},
        ),
        og_type="Line",
    ),
    component(
        "Line",
        "Line",
        fixed("s_nom", "Line", AC),
        device("s_nom"),
        ARC,
        UNTYPED_LINE,
        (
            {
                "r": "r",
                "x": "x",
                "parameter_units": NATURAL,
                "b__from": "b / 2",
                "b__to": "b / 2",
                "g__from": "g / 2",
                "g__to": "g / 2",
                "active_power_flow": "0",
                "reactive_power_flow": "0",
                "angle_limits__min": f"radians(NULLIF(v_ang_min, -{INF}))",
                "angle_limits__max": f"radians(NULLIF(v_ang_max, {INF}))",
            },
            {
                "r": "COALESCE(r, 0)",
                "x": "COALESCE(x, 0)",
                "b": "COALESCE(b__from, 0) + COALESCE(b__to, 0)",
                "g": "COALESCE(g__from, 0) + COALESCE(g__to, 0)",
                "v_ang_min": f"COALESCE(degrees(angle_limits__min), -{INF})",
                "v_ang_max": f"COALESCE(degrees(angle_limits__max), {INF})",
            },
        ),
    ),
    component(
        "Line",
        "NodalHVDCTransportTechnology",
        extendable("s_nom", "TModelHVDCLine", DC),
        technology("s_nom"),
        NODES,
        UNTYPED_LINE,
        og_type="TModelHVDCLine",
    ),
    component(
        "Line",
        "TModelHVDCLine",
        fixed("s_nom", "TModelHVDCLine", DC),
        ARC,
        UNTYPED_LINE,
        (
            {
                "available": "active",
                "r": "r",
                "l": "0",
                "c": "0",
                "base_current": "s_nom / v_nom0",
                "active_power_flow": "0",
                f"{FLOW}__from_to_max": "s_nom",
                f"{FLOW}__to_from_max": "s_nom",
                f"{FLOW}__from_to_min": "0",
                f"{FLOW}__to_from_min": "0",
            },
            {
                "active": "COALESCE(available, true)",
                "s_nom_extendable": "false",
                "s_nom": f"{FLOW}__from_to_max",
                "r": "COALESCE(r, 0)",
            },
        ),
    ),
    component(
        "Link",
        "NodalHVDCTransportTechnology",
        extendable("p_nom", "InterconnectingConverter", AC_DC),
        technology("p_nom"),
        NODES,
        LOSSY,
        og_type="InterconnectingConverter",
    ),
    component(
        "Link",
        "InterconnectingConverter",
        fixed("p_nom", "InterconnectingConverter", AC_DC),
        device("p_nom"),
        LIMITS,
        (
            {
                "bus": "CASE WHEN type0 = 'ACBus' THEN bus0 ELSE bus1 END",
                "dc_bus": "CASE WHEN type0 = 'DCBus' THEN bus0 ELSE bus1 END",
                "active_power": "0",
                "ext__pypsa__from_dc": "NULLIF(type0 = 'DCBus', false)",
            },
            {
                "bus0": "CASE WHEN ext__pypsa__from_dc THEN dc_bus ELSE bus END",
                "bus1": "CASE WHEN ext__pypsa__from_dc THEN bus ELSE dc_bus END",
            },
        ),
    ),
    component(
        "Link",
        "NodalHVDCTransportTechnology",
        extendable("p_nom", "TwoTerminalGenericHVDCLine", AC),
        technology("p_nom"),
        NODES,
        LOSSY,
        og_type="TwoTerminalGenericHVDCLine",
    ),
    component(
        "Link",
        "TwoTerminalGenericHVDCLine",
        fixed("p_nom", "TwoTerminalGenericHVDCLine", AC),
        device("p_nom"),
        ARC,
        (
            {
                "active_power_flow": "0",
                f"{FLOW}__from_to_max": "p_nom * p_max_pu",
                f"{FLOW}__to_from_max": "p_nom * greatest(-p_min_pu, 0)",
                f"{FLOW}__from_to_min": "p_nom * greatest(p_min_pu, 0)",
                f"{FLOW}__to_from_min": "0",
                "loss__power_units": NATURAL,
                **linear("loss__value_curve", "1 - efficiency"),
                "reactive_power_limits_from__min": "0",
                "reactive_power_limits_from__max": "0",
                "reactive_power_limits_to__min": "0",
                "reactive_power_limits_to__max": "0",
            },
            {
                "p_max_pu": f"COALESCE({FLOW}__from_to_max / NULLIF(rating, 0), 1)",
                "p_min_pu": f"COALESCE(CASE WHEN {FLOW}__to_from_max > 0"
                f" THEN -{FLOW}__to_from_max ELSE {FLOW}__from_to_min END / NULLIF(rating, 0), 0)",
                "efficiency": f"1 - COALESCE(loss__value_curve{SLOPE}, 0)",
            },
        ),
    ),
    component(
        "GlobalConstraint",
        "CarbonCaps",
        "og_type = 'CarbonCaps' AND type = 'primary_energy'"
        " AND carrier_attribute = 'co2_emissions' AND sense = '<='",
        (
            {
                "max_mtons": "constant / 1e6 / years",
                "available": "true",
                "target_year": TARGET_YEAR,
            },
            {
                "type": "'primary_energy'",
                "carrier_attribute": "'co2_emissions'",
                "sense": "'<='",
                "constant": "max_mtons * 1e6 * _target_years",
                "investment_period": "target_year",
            },
        ),
        tuples={"requirement_association": {"requirement": "name", "entity": "unnest(emitters)"}},
    ),
    component(
        "GlobalConstraint",
        "MaximumCapacityRequirements",
        f"og_type = '{CAPACITY_LIMIT}' AND type = 'tech_capacity_expansion_limit' AND sense = '<='",
        (
            {
                "max_capacity_mw": f"NULLIF(constant, {INF})",
                "available": "true",
                "target_year": TARGET_YEAR,
                "ext__pypsa__no_bus": "NULLIF(bus = '' AND covered_buses = 1, false)",
            },
            {
                "type": "'tech_capacity_expansion_limit'",
                "carrier_attribute": "_limited_carrier",
                "bus": "CASE WHEN _limited_buses = 1 AND ext__pypsa__no_bus IS NOT TRUE"
                " THEN _limited_bus ELSE '' END",
                "sense": "'<='",
                "constant": f"COALESCE(max_capacity_mw, {INF})",
                "investment_period": "target_year",
            },
        ),
        tuples={"requirement_association": {"requirement": "name", "entity": "unnest(covered)"}},
    ),
    component(
        "Shape",
        "GeographicInfo",
        "og_type = 'GeographicInfo'",
        (
            {
                "geo_json": "geometry",
                "ext__pypsa__component": "NULLIF(NULLIF(component, 'Bus'), '')",
                "ext__pypsa__idx": "CASE WHEN component != 'Bus' THEN NULLIF(idx, '') END",
            },
            {
                "geometry": "geo_json",
                "component": "COALESCE(ext__pypsa__component, CASE WHEN _bus IS NOT NULL"
                " THEN 'Bus' END, '')",
                "idx": "COALESCE(ext__pypsa__idx, _bus, '')",
            },
        ),
        fits=OUTLINE,
        tuples={
            "bus_supplemental_attribute": {
                "bus": "CASE WHEN component = 'Bus' THEN idx END",
                "supplemental_attribute": "name",
            }
        },
    ),
)

ROLES = frozenset(entry.role for entry in ENTRIES if entry.role)
"""The parts a PyPSA component may be of an OGSchema component."""

FRACTIONAL = "isfinite(lifetime) AND lifetime != floor(lifetime)"
LIFETIME = "a lifetime that is no whole number of years"
ON_PART = "a component other than its parts on the bus of a storage chain"
UNKEYED = "limits of a capacity that differ by build year, where OGSchema has one limit"
LIMITING = f"og_type = '{CAPACITY_LIMIT}'"
UNFIT = "a capacity limit on {}, which is kept beside the record once its `og_type` is cleared"
WRITE_REFUSALS = (
    ("devices", "contains(name, '|')", "a `|` in the name of a generator of fixed capacity"),
    ("storage_units", f"p_nom_extendable AND {FRACTIONAL}", LIFETIME),
    ("stores", f"e_nom_extendable AND {FRACTIONAL}", LIFETIME),
    ("generators", "bus_part IS NOT NULL", ON_PART),
    ("loads", "bus_part IS NOT NULL", ON_PART),
    ("storage_units", "bus_part IS NOT NULL", ON_PART),
    ("lines", "part0 IS NOT NULL OR part1 IS NOT NULL", ON_PART),
    ("links", "(part0 IS NOT NULL OR part1 IS NOT NULL) AND og_part IS NULL", ON_PART),
    ("global_constraints", f"{LIMITING} AND covered IS NULL", UNFIT.format("no extendable asset")),
    (
        "global_constraints",
        f"{LIMITING} AND parts > 0",
        UNFIT.format("a store or a part of a component"),
    ),
    ("global_constraints", f"{LIMITING} AND kinds > 1", UNFIT.format("several OGSchema types")),
    ("shapes", POINT.format(geo_json="geometry"), "a shape that is a point"),
    ("lines", "limits_by_year IS NOT NULL", UNKEYED),
    ("links", "limits_by_year IS NOT NULL AND og_part IS DISTINCT FROM 'charge'", UNKEYED),
)
"""The rows of a frame that fit an entry but hold a value OGSchema cannot: frame, rows, why."""

COST_TYPE = "COALESCE(operation_cost__cost_type, operation_costs__cost_type)"
VARIABLE = (
    "COALESCE(operation_cost__variable_operation_cost__variable_cost_type,"
    " operation_costs__variable_operation_cost__variable_cost_type)"
)
READ_REFUSALS = (
    ("entity", "NOT _covered", "a component type the mapping does not cover"),
    ("bus", "NOT _covered", "a component type the mapping does not cover"),
    ("entity", "parameter_units = 'COMPONENT_BASE' AND arc IS NOT NULL", "impedances per unit"),
    (
        "entity",
        "component_type IN ('SupplyTechnology', 'StorageTechnology') AND _regions != 1"
        " AND ext__invented_candidate IS NOT TRUE",
        "no single region",
    ),
    ("entity", "component_type = 'HydroTurbine' AND _reservoirs != 1", "no single reservoir"),
    (
        "entity",
        f"component_type = '{CAPACITY_LIMIT}' AND COALESCE(_limited_carriers, 0) != 1",
        "no single kind of technology to limit",
    ),
    (
        "entity",
        "component_type = 'HydroTurbine' AND COALESCE(_level_data_type, '') != 'ENERGY'",
        "a reservoir whose level is no energy",
    ),
    (
        "entity",
        f"{COST_TYPE} NOT IN"
        " ('THERMAL', 'RENEWABLE', 'HYDRO_GEN', 'HYDRO_RES', 'STORAGE', 'LOAD', 'IMPORTEXPORT')",
        "an operation cost the mapping does not cover",
    ),
    (
        "entity",
        f"{COST_TYPE} = 'THERMAL' AND {VARIABLE} != 'FUEL'",
        "a thermal cost that is no fuel curve",
    ),
    ("entity", "_emissions > 1", "more than one EmissionsData"),
    (
        "supplemental_attribute",
        "component_type = 'EmissionsData' AND (pollutant != 'CO2' OR basis != 'FUEL_INPUT'"
        " OR emission_rate__curve_type != 'INCREMENTAL')",
        "emissions other than a CO2 rate per fuel input",
    ),
    (
        "supplemental_attribute",
        "NOT _covered",
        "a supplemental attribute type the mapping does not cover",
    ),
)
"""The labels of a record's dim that PyPSA cannot take: dim, rows, why."""

SHAPES = {
    "entity": {"function_type": "LINEAR", "curve_type": "INPUT_OUTPUT"},
    "supplemental_attribute": {"function_type": "LINEAR"},
}
"""Per dim, the one value the entries read of every property whose name ends as given."""

CO2_PER_MWH = (
    "supplemental_attribute__emission_rate__function_data__constant_term"
    " * CASE energy_unit WHEN 'GJ' THEN 3.6 WHEN 'MMBTU' THEN 3.412 ELSE 1 END"
    " * CASE COALESCE(mass_unit, 'KG') WHEN 'KG' THEN 1e-3 WHEN 'LB' THEN 4.5359237e-4"
    " WHEN 'SHORT_TON' THEN 0.90718474 ELSE 1 END"
)
"""The CO2 an EmissionsData states, in tonnes per MWh of fuel as PyPSA's carriers have it."""
