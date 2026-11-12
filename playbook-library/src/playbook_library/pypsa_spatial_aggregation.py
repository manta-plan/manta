# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Bus, entity and time aggregation of PyPSA networks built from a datarecord.

An aggregation names a property of a dim. `aggregate_network` merges buses, then assets,
then snapshots, and `expand_network` spreads the results of the merged buses and assets
back over every bus and asset.

Buses with the same value of a bus property merge into the first of them in axis order.
Lines between the same merged buses merge, span the distance between those buses and take
the impedances of their type. Land-use limits at buses that merge combine into one, and
every land-use limit is stated again from the merged candidates, as PyPSA-Eur states them.
The results of each bus are those of the bus it merged into.

Assets with the same value of an entity property merge into one, but only those of one
component, at the same buses and of the same resource class. Candidate assets, by the
entity property `asset_status`, merge only within one cohort of build year and lifetime.
Existing assets merge with those first and last active in the same investment periods, as
PyPSA-Eur merges power plants, so that the existing capacity in each period stays as it
was, and those active in none are dropped. Capacities and dispatch are split back over the
assets by their largest possible capacity if extendable candidates, or their capacity if
not, or equally where one of them has no limit.

An asset without a value of the entity property is solved apart, at its merged bus. With
`ungrouped: drop`, which needs an entity property, a generator, load, storage unit or store
without a value is left out of the solve instead: it keeps its capacity and carries no
flow, so a dropped load takes its demand out of the solve. Links and lines without a value
are always kept.

`clip_p_max_pu` sets time-varying availabilities at or below it to 0 after every other
aggregation, as PyPSA-Eur's `solving.options.clip_p_max_pu` does. It applies to the
`p_max_pu` and `p_min_pu` series of generators and links and the `inflow` series of storage
units, by their absolute value, and leaves static values as they are. Results split back
over the assets are judged against their unclipped values, so a dispatch may fall below an
unclipped `p_min_pu` by up to the threshold.

Snapshots merge by a time aggregation, as `pypsa_time_aggregation` does.
"""

import re
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd
import pypsa
from datarecord import RecordLike
from pandas.api.types import is_bool_dtype, is_numeric_dtype
from playbook.blocks.core import DataRecord
from pypsa.clustering.spatial import (
    DEFAULT_BUS_STRATEGIES,
    DEFAULT_LINE_STRATEGIES,
    DEFAULT_ONE_PORT_STRATEGIES,
    align_strategies,
    normed_or_uniform,
)
from pypsa.geo import haversine_pts
from pypsa.network.power_flow import apply_line_types

from playbook_library.datarecord_helpers import revision
from playbook_library.pypsa_configs import Aggregation
from playbook_library.pypsa_time_aggregation import cluster_network

ONE_PORTS = ["Generator", "Load", "StorageUnit", "Store"]
"""The components whose assets without a value an entity aggregation may leave out."""

ENTITY_COMPONENTS = [*ONE_PORTS, "Link"]
"""The components whose assets an entity aggregation merges, beside lines."""

COHORT = ["build_year", "lifetime"]
"""The attributes that set an asset's cohort, which an entity aggregation keeps apart."""

STATUS = "asset_status"
"""The entity property that marks an asset as a candidate or as existing."""

CANDIDATE = "candidate"
"""The value of `STATUS` of an asset whose cohort an entity aggregation keeps apart."""

RESOURCE_CLASS = "resource_class"
"""The attribute whose classes an entity aggregation keeps apart, where assets have one."""

NO_HORIZONS = pd.DataFrame(columns=["first", "last"], dtype=float)
"""No existing assets by their first and last active periods, as for lines, whose cohorts
stay apart."""

NO_ASSETS = NO_HORIZONS.index
"""The labels of `NO_HORIZONS`."""

ENTITY_STRATEGIES = {
    **{k: v for k, v in DEFAULT_ONE_PORT_STRATEGIES.items() if k not in COHORT},
    "ramp_limit_up": "max",
    "ramp_limit_down": "max",
    "committable": "any",
    "length": "capacity_weighted_average",
}
"""How the attributes of merged assets combine: as PyPSA-Eur merges power plants."""

LINE_STRATEGIES = {k: v for k, v in DEFAULT_LINE_STRATEGIES.items() if k not in COHORT}
"""How the attributes of parallel lines combine: as PyPSA merges lines, keeping cohorts.

Their length is the distance between their buses, as PyPSA sets it, which scales their
impedances and cost as PyPSA scales them, and a line type sets their impedances."""

TYPED = ["r", "x", "b"]
"""The line attributes PyPSA derives from a line type."""

NOMINAL = {"Store": "e_nom"}
"""The capacity attribute of an asset, `p_nom` where not named, by which results split back."""

HELD = ["status", "start_up", "shut_down"]
"""The commitment results each member of a merged asset takes from it, as it takes duals."""

BRANCHES = ["Line", "Transformer"]
"""The components whose members within a merged bus are dropped and keep their capacity."""

LINE_FLOWS = ["p0", "p1"]
"""The branch results a solve always sets, even where every branch lies within a merged bus."""

SOLVED = {
    "Link": LINE_FLOWS,
    "Store": ["p", "e"],
    "StorageUnit": ["p", "p_dispatch", "p_store", "state_of_charge"],
}
"""The asset results a solve always sets, `p` where not named, even where every asset is
left out."""

LAND_USE = "tech_capacity_expansion_limit"
"""The type of a global constraint that, at a bus and for a carrier, is a land-use limit.

PyPSA-Eur sets its constant to the smallest `p_nom_max` of the extendable generators of the
carrier at the bus built in its investment period. A bus aggregation refuses global
constraints at buses that are not land-use limits."""

LAND_USE_KEYS = ["carrier", "bus", "build_year"]
"""The generator attributes that name the land-use limit a candidate falls under."""

CLIPPED = {
    "Generator": ["p_max_pu", "p_min_pu"],
    "Link": ["p_max_pu", "p_min_pu"],
    "StorageUnit": ["inflow"],
}
"""The time-varying attributes whose small values `clip_p_max_pu` sets to 0, as PyPSA-Eur
clips them before solving."""

SWAPPED = {
    "p0": "p1",
    "p1": "p0",
    "q0": "q1",
    "q1": "q0",
    "mu_upper": "mu_lower",
    "mu_lower": "mu_upper",
}
"""The result of a merged line at a member that runs the other way."""


@dataclass(frozen=True)
class SpatialMaps:
    """How the buses, lines and assets of a network map to those they merge into."""

    buses: pd.Series
    """Each bus to its representative bus."""

    lines: pd.Series
    """Each line between buses that stay apart to its representative line.

    Without a bus aggregation, parallel lines merge by the entity aggregation.
    """

    flipped: pd.Series
    """Whether each line of `lines` runs against the line it merges into."""

    entities: pd.Series
    """Each asset of `ENTITY_COMPONENTS` to its representative asset, or itself."""

    transformers: pd.Series
    """Each transformer between buses that stay apart to itself."""

    horizons: pd.DataFrame
    """Each asset with a value of the entity property that is not a candidate, to the
    `first` and `last` investment periods it is active in, or NaN if none.

    They merge by those periods instead of their cohort and split results by capacity.
    """

    ungrouped: pd.Index
    """The one-port assets without a value of the entity property, if left out."""

    constraints: pd.Series
    """Each global constraint to the one it merges into, or itself.

    Land-use limits at buses that merge, alike but for their constant, merge into one.
    """

    @property
    def dropped(self) -> pd.Index:
        """The assets left out: those of `ungrouped`, and existing assets active in no
        investment period."""
        return self.horizons.index[self.horizons["last"].isna()].union(self.ungrouped)


def _identity(index: pd.Index) -> pd.Series:
    return pd.Series(index, index=index)


def _representatives(keys: pd.DataFrame) -> pd.Series:
    """Map each row label of `keys` to the first label, in row order, with equal keys."""
    labels = keys.index.to_series()
    by = [keys[column] for column in keys.columns]
    return labels.groupby(by, sort=False, dropna=False).transform("first")


def _property(base: RecordLike, dim: str, name: str, use: str = " to aggregate by") -> pd.Series:
    """Return `<dim>.<name>` of `base`, by label.

    Raises `ValueError` if `base` has no such property, saying what it is for by `use`.
    """
    frame = base.properties[dim].df()
    if name not in frame.columns:
        raise ValueError(f"The record has no {dim} property {name!r}{use}")
    return frame.set_index(dim)[name]


def _ports(c: pypsa.Components) -> list[str]:
    return [f"bus{port}" for port in c.ports]


def _mapped(static: pd.DataFrame, buses: pd.Series, ports: list[str]) -> pd.DataFrame:
    """Return `static` with each bus in `ports` replaced by its representative."""
    return static.assign(**{port: static[port].map(buses).fillna("") for port in ports})


def _line_map(n: pypsa.Network, buses: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Return the representative and direction of each line of `n` whose buses stay apart.

    Lines merge where their buses map to the same pair and they share a cohort, as
    `aggregate_buses` has PyPSA merge them.
    """
    static = _mapped(n.c.lines.static, buses, ["bus0", "bus1"])
    ends = static[["bus0", "bus1"]]
    pairs = pd.DataFrame(np.sort(ends.to_numpy(), axis=1), index=ends.index)
    keys = pd.concat([pairs, static[COHORT]], axis=1)
    apart = keys[pairs[0] != pairs[1]]
    return _representatives(apart), (ends["bus0"] > ends["bus1"])[apart.index]


def _apart(c: pypsa.Components, buses: pd.Series) -> pd.Series:
    """Map each branch of `c` whose buses stay apart to itself."""
    static = _mapped(c.static, buses, ["bus0", "bus1"])
    return _identity(static.index[static["bus0"] != static["bus1"]])


def _horizons(n: pypsa.Network, c: pypsa.Components) -> pd.DataFrame:
    """Return the `first` and `last` investment periods of `n` each asset of `c` is active in,
    or NaN if none.

    Without investment periods, an active asset is active in period 0.
    """
    periods = n.investment_periods
    if periods.empty:
        active = c.get_active_assets().to_frame(0)
    else:
        active = pd.DataFrame({period: c.get_active_assets(period) for period in periods})
    years = (active * active.columns.to_numpy()).where(active)
    return pd.DataFrame({"first": years.min(axis=1), "last": years.max(axis=1)})


def _grouped(
    c: pypsa.Components,
    values: pd.Series,
    buses: pd.Series,
    horizons: pd.DataFrame = NO_HORIZONS,
) -> pd.Series:
    """Map each asset of `c` to the first with its value, buses, resource class and vintage.

    The vintage of an asset in `horizons` is its periods there, and of any other its cohort.
    An asset without a value maps to itself.
    """
    static = _mapped(c.static, buses, _ports(c))
    vintage = static[static.columns.intersection(COHORT)].astype(float)
    vintage.loc[static.index.isin(horizons.index)] = np.nan
    keys = static[[*_ports(c), *static.columns.intersection([RESOURCE_CLASS])]].join(vintage)
    keys = keys.join(horizons.reindex(static.index)).assign(value=values.reindex(static.index))
    valued = keys.dropna(subset=["value"])
    return _representatives(valued).combine_first(_identity(static.index))


def _entity_map(
    n: pypsa.Network, values: pd.Series, buses: pd.Series, horizons: pd.DataFrame
) -> pd.Series:
    components = n.components[ENTITY_COMPONENTS]
    return pd.concat([_grouped(c, values, buses, horizons) for c in components])


def _renamed(name: str, bus: str, merged: str) -> str:
    """Return `name` with `bus`, where it stands apart from other words, replaced by `merged`."""
    return re.sub(rf"(?<!\S){re.escape(bus)}(?!\S)", lambda _: merged, name)


def _is_land_use(static: pd.DataFrame) -> pd.Series:
    """Return whether each global constraint of `static` is a land-use limit."""
    located = (static["bus"] != "") & (static["carrier_attribute"] != "")
    return located & (static["type"] == LAND_USE)


def _constraint_map(n: pypsa.Network, buses: pd.Series) -> pd.Series:
    """Map each global constraint of `n` at a bus to the first alike at the same merged bus.

    Alike means equal in every input but `constant`. The merged constraint is named as the
    first, with its bus replaced by the merged bus where the name holds it as a word, as
    PyPSA-Eur names the land-use limits `land_use <carrier> <bus> <period>` of a clustered
    network. Where that gives one name to constraints that do not merge, each keeps the
    name of its first. A constraint at no bus maps to itself. Raises `NotImplementedError`
    naming the constraints at buses that are not land-use limits, by type.
    """
    c = n.components["GlobalConstraint"]
    static = c.static[c.static["bus"] != ""]
    unknown = static.index[~_is_land_use(static)]
    if len(unknown):
        types = static.loc[unknown, "type"]
        kinds = {kind: names.tolist() for kind, names in unknown.groupby(types).items()}
        raise NotImplementedError(f"No rule merges global constraints at buses of types {kinds}")
    keys = _mapped(static, buses, ["bus"]).drop(columns=["constant", *_outputs(c)])
    first = _representatives(keys)
    at = static.loc[first.to_numpy(), "bus"]
    names = [_renamed(name, bus, buses[bus]) for name, bus in zip(first, at, strict=True)]
    renamed = pd.Series(names, first.index)
    shared = renamed.groupby(renamed).transform(lambda s: first[s.index].nunique() > 1)
    renamed = renamed.where(~shared, first)
    return renamed.combine_first(_identity(c.static.index)).reindex(c.static.index)


def spatial_maps(n: pypsa.Network, record: DataRecord, aggregation: Aggregation) -> SpatialMaps:
    """Return how `aggregation` merges the buses, lines and assets of `n`, built from `record`.

    Raises `ValueError` if `record` lacks a property `aggregation` names, or the entity
    property `asset_status` for an entity aggregation, or leaves the bus property unset
    for a bus of `n`, or `asset_status` unset for an asset other than a load with a value
    of the entity property. A load without it counts as existing. Assets and lines without
    a value of the entity property stay apart, except one-ports, which map to nothing if
    `aggregation.ungrouped` drops them. Existing assets merge only with those first and
    last active in the same investment periods, and those active in none map to nothing.
    Lines keep their cohorts apart whatever their status. Raises `NotImplementedError`
    for a bus aggregation that leaves a transformer between buses that stay apart, which
    PyPSA would drop, for a bus aggregation of global constraints at buses that are not
    land-use limits, and for an entity aggregation that sets a value for a transformer it
    keeps.
    """
    base = revision(record)[1].record
    entities = pd.Index([name for c in n.components[ENTITY_COMPONENTS] for name in c.static.index])
    buses = _identity(n.c.buses.static.index)
    lines = _identity(n.c.lines.static.index)
    flipped = pd.Series(False, index=lines.index)
    constraints = _identity(n.c.global_constraints.static.index)
    if aggregation.bus is not None:
        values = _property(base, "bus", aggregation.bus).reindex(buses.index)
        unset = values.index[values.isna()]
        if len(unset):
            raise ValueError(f"bus.{aggregation.bus} is not set for {unset.tolist()}")
        buses = _representatives(values.to_frame())
        lines, flipped = _line_map(n, buses)
        constraints = _constraint_map(n, buses)
    transformers = _apart(n.components["Transformer"], buses)
    if aggregation.bus is not None and not transformers.empty:
        names = transformers.index.tolist()
        raise NotImplementedError(f"Bus aggregation of transformers between merged buses: {names}")
    groups = _identity(entities)
    horizons = NO_HORIZONS
    ungrouped = NO_ASSETS
    if aggregation.entity is not None:
        values = _property(base, "entity", aggregation.entity)
        status = _property(base, "entity", STATUS, ", which entity aggregation needs")
        if values.reindex(transformers.index).notna().any():
            raise NotImplementedError("Entity aggregation of transformers")
        valued = values.reindex(entities).dropna().index
        statuses = status.reindex(valued)
        unset = valued[statuses.isna()].difference(n.c.loads.static.index)
        if len(unset):
            raise ValueError(f"entity.{STATUS} is not set for {unset.tolist()}")
        existing = valued[statuses != CANDIDATE]
        active = pd.concat([_horizons(n, c) for c in n.components[ENTITY_COMPONENTS]])
        horizons = active[active.index.isin(existing)]
        if aggregation.ungrouped == "drop":
            one_ports = pd.Index([name for c in n.components[ONE_PORTS] for name in c.static.index])
            ungrouped = one_ports.difference(valued)
        groups = _entity_map(n, values, buses, horizons)
        if aggregation.bus is None:
            lines = _grouped(n.components["Line"], values, buses)
    maps = SpatialMaps(
        buses, lines, flipped, groups, transformers, horizons, ungrouped, constraints
    )
    return replace(maps, entities=groups.drop(maps.dropped))


def dropped_assets(n: pypsa.Network, record: DataRecord, aggregation: Aggregation) -> pd.Index:
    """Return the assets of `n`, built from `record`, that `aggregation` leaves out of the solve."""
    if aggregation.bus is None and aggregation.entity is None:
        return NO_ASSETS
    return spatial_maps(n, record, aggregation).dropped


def _total(values: pd.Series) -> float:
    """Return the sum of `values`, or NaN where none is set."""
    return values.sum(min_count=1)


def _merged_text(values: pd.Series) -> object:
    """Return the value of a bus or line that merges with no other, or none if it merges."""
    return values.iat[0] if len(values) == 1 else None


def _unknown(static: pd.DataFrame, columns: pd.Index) -> dict[str, object]:
    """Return how each of `columns` of `static`, which PyPSA does not know, combines.

    Text and flags are unset where buses or lines merge, as PyPSA-Eur drops them before
    clustering, and any other value is the representative's.
    """
    unset = [c for c in columns if is_bool_dtype(static[c]) or not is_numeric_dtype(static[c])]
    return {**dict.fromkeys(columns, "first"), **dict.fromkeys(unset, _merged_text)}


def _check_types(lines: pd.DataFrame, groups: pd.Series) -> None:
    """Raise `ValueError` naming each line of `groups` that lines of different types merge into."""
    kinds = lines.loc[groups.index, "type"].groupby(groups).nunique()
    mixed = kinds.index[kinds > 1].tolist()
    if mixed:
        raise ValueError(f"Lines of different types merge into {mixed}")


def _apply_line_types(n: pypsa.Network) -> None:
    """Set the impedances of each line of `n` with a type by its type, length and parallels."""
    lines = n.c.lines.static
    lines.loc[lines["type"] != "", TYPED] = 0.0
    apply_line_types(n)


def _merged_constraints(n: pypsa.Network, maps: SpatialMaps) -> pd.DataFrame:
    """Return the global constraints of `n` merged as `maps` says, each as the first it
    merges, at its merged bus."""
    static = n.c.global_constraints.static
    merged = static.groupby(maps.constraints[static.index], sort=False).first()
    return _mapped(merged, maps.buses, ["bus"]).rename_axis(static.index.name)


def _s_nom_max(lines: pd.DataFrame, groups: pd.Series) -> pd.Series:
    """Return the `s_nom_max` of each line that lines of `groups` merge into.

    That is their summed `s_nom` and the largest extension, `s_nom_max` over `s_nom`, of
    those extendable, as PyPSA-Eur extends lines after it merges them. A line that is not
    extendable has no extension, as PyPSA bounds it by its `s_nom`. Raises `ValueError`
    naming each merged line whose summed `s_nom_min` exceeds its `s_nom_max`.
    """
    merging = _merging(groups)
    members = lines.loc[merging.index]
    extension = (members["s_nom_max"] - members["s_nom"]).where(members["s_nom_extendable"], 0.0)
    limits = members["s_nom"].groupby(merging).sum() + extension.groupby(merging).max()
    above = members["s_nom_min"].groupby(merging).sum() > limits
    names = above.index[above].tolist()
    if names:
        raise ValueError(f"Lines merge with `s_nom_min` above `s_nom_max` into {names}")
    return limits


def aggregate_buses(n: pypsa.Network, maps: SpatialMaps) -> pypsa.Network:
    """Return `n` with its buses merged as `maps` says, by PyPSA's clustering.

    Lines of one cohort merge between each pair of merged buses, under their representative
    line, as PyPSA merges them: they span the distance between the merged buses and add up
    their parallels and capacity, and lines of one type keep it and take their impedances
    from it. Their `s_nom_max` is as `_s_nom_max` says. Raises `ValueError` where lines of
    different types merge. Lines and transformers within a merged bus are dropped. Assets
    move to the merged buses, and links keep their length and cost. A link whose ends merge
    into one bus is kept. The limits PyPSA reads from `nom_min_...` and `nom_max_...` bus
    attributes add up. Land-use limits `maps.constraints` merges keep the constant of the
    first until `restate_land_use` states them again. Any other bus or line attribute PyPSA
    does not know is unset where buses or lines merge if text or a flag, and else the
    representative's, as is the location.
    """
    buses, lines = n.c.buses.static, n.c.lines.static
    known = n.components["Bus"].defaults.index.union(list(DEFAULT_BUS_STRATEGIES))
    columns = buses.columns.difference(known)
    limits = columns[columns.str.startswith(("nom_min_", "nom_max_"))]
    strategies = {**_unknown(buses, columns), **dict.fromkeys(limits, _total), "location": "first"}
    known_lines = n.components["Line"].defaults.index.union(list(DEFAULT_LINE_STRATEGIES))
    line_columns = lines.columns.difference(known_lines)
    line_strategies = {**_unknown(lines, line_columns), **dict.fromkeys(COHORT, "first")}
    _check_types(lines, maps.lines)
    s_nom_max = _s_nom_max(lines, maps.lines)
    clustering = n.cluster.spatial.get_clustering_from_busmap(
        maps.buses,
        aggregate_one_ports={},
        bus_strategies=strategies,
        line_strategies=line_strategies,
        custom_line_groupers=COHORT,
        scale_link_capital_costs=False,
    )
    clustered = clustering.n
    _apply_line_types(clustered)
    clustered.c.global_constraints.static = _merged_constraints(n, maps)
    clustered.c.links.static["length"] = n.c.links.static["length"]
    names = {str(g): maps.lines[line] for line, g in clustering.linemap.items()}
    clustered.c.lines.static.rename(index=names, inplace=True)
    for frame in clustered.c.lines.dynamic.values():
        frame.rename(columns=names, inplace=True)
    clustered.c.lines.static.loc[s_nom_max.index, "s_nom_max"] = s_nom_max
    links = n.c.links.static
    loops = links.index.difference(clustered.c.links.static.index)
    dynamic = {attr: df[df.columns.intersection(loops)] for attr, df in n.c.links.dynamic.items()}
    series = {attr: df for attr, df in dynamic.items() if not df.empty}
    looped = _mapped(links.loc[loops], maps.buses, _ports(n.components["Link"]))
    clustered.add("Link", loops, **{**looped, **series})
    return clustered


def _split(sizes: pd.Series) -> pd.Series:
    """Return each size's share of the group, or equal shares where one has no limit."""
    if np.isinf(sizes).any():
        return pd.Series(1.0 / len(sizes), sizes.index)
    return normed_or_uniform(sizes)


def _sizes(static: pd.DataFrame, ctype: str, existing: pd.Index) -> pd.Series:
    """Return each asset's largest capacity if an extendable candidate, else its capacity.

    The capacity is the attribute `NOMINAL` names, and the largest capacity its `_max`.
    """
    nominal = NOMINAL.get(ctype, "p_nom")
    if nominal not in static:
        return pd.Series(1.0, static.index)
    open_ended = static[f"{nominal}_extendable"] & ~static.index.isin(existing)
    return static[f"{nominal}_max"].where(open_ended, static[nominal])


def _shares(
    static: pd.DataFrame, ctype: str, groups: pd.Series, existing: pd.Index = NO_ASSETS
) -> pd.Series:
    """Return each asset's share of its group in `_sizes`.

    The shares are equal where one asset of the group has no limit, or the component has
    no capacity. A branch's share is that of `s_nom`, as PyPSA weighs lines.
    """
    if ctype in BRANCHES:
        return static["s_nom"].groupby(groups).transform(normed_or_uniform)
    return _sizes(static, ctype, existing).groupby(groups).transform(_split)


def _is_result(attr: str) -> bool:
    return attr.endswith("_opt") or attr.startswith("mu")


def _is_held(attr: str) -> bool:
    return attr.startswith("mu") or attr in HELD


def _outputs(c: pypsa.Components) -> pd.Index:
    return c.defaults.index[c.defaults.status.astype(str).str.startswith("Output")]


def _reciprocal_sum(values: pd.Series) -> float:
    return 1.0 / values.sum()


def _weighted(
    values: pd.Series | pd.DataFrame, strategy: object, weights: pd.Series, scale: pd.Series
) -> tuple[pd.Series | pd.DataFrame, object]:
    """Return `values` and `strategy` so that aggregating groups gives the merged values.

    Lengths scale by `scale`, as PyPSA scales merged lines by their new length.
    """
    if strategy == "capacity_weighted_average":
        return values * weights, "sum"
    if strategy == "length_capacity_weighted_average":
        return values * scale * weights, "sum"
    if strategy == "voltage_weighted_average":
        return values * scale, "sum"
    if strategy == "reciprocal_voltage_weighted_average":
        return 1.0 / (values * scale), _reciprocal_sum
    return values, strategy


def _span(n: pypsa.Network, static: pd.DataFrame) -> pd.Series:
    """Return the distance between the buses of each line of `static`."""
    coords = n.c.buses.static[["x", "y"]]
    ends = [coords.loc[static[end]] for end in ["bus0", "bus1"]]
    return pd.Series(haversine_pts(*ends), static.index)


def _aggregated(
    n: pypsa.Network, c: pypsa.Components, groups: pd.Series, existing: pd.Index
) -> dict[str, object]:
    """Return the attributes of the assets `groups` merges, as keyword arguments of `n.add`.

    Each attribute combines as `LINE_STRATEGIES` or `ENTITY_STRATEGIES` says, and one
    without a rule must agree within each group. An average is weighted by the shares
    `_shares` gives, by which the results are split back: by capacity, as PyPSA weighs
    one-ports, for existing assets and those not extendable. Parallel lines span the
    distance between their buses and combine their impedances and cost as PyPSA does,
    scaled by that over their own length. Where their buses have no distance between them,
    such as without coordinates, they keep their own length and impedances. A custom
    attribute is the representative's, but a line's is unset if text or a flag.
    """
    static = c.static.loc[groups.index]
    outputs = _outputs(c)
    custom = static.columns.difference(c.defaults.index)
    scale = pd.Series(1.0, static.index)
    if c.name == "Line":
        strategies = {**LINE_STRATEGIES, **_unknown(static, custom)}
        span = _span(n, static)
        scale = (span / static["length"]).where(static["length"] > 0, span)
        scale = scale.where(span > 0, 1.0)
        static["length"] = span.where(span > 0, static["length"])
    else:
        strategies = {**ENTITY_STRATEGIES, **dict.fromkeys(custom, "first")}
    weights = _shares(static, c.name, groups, existing)
    columns = static.columns.difference(outputs, sort=False)
    static_strategies = align_strategies(dict(strategies), columns, c.name)
    for column, strategy in static_strategies.items():
        weighted = _weighted(static[column], strategy, weights, scale)
        static[column], static_strategies[column] = weighted
    merged = static.groupby(groups, sort=False).agg(static_strategies)
    attributes = {column: merged[column] for column in merged.columns}
    series = [attr for attr, df in c.dynamic.items() if not df.empty and attr not in outputs]
    dynamic_strategies = align_strategies(dict(strategies), series, c.name)
    for attr, strategy in dynamic_strategies.items():
        dense = n.get_switchable_as_dense(c.name, attr, inds=groups.index)
        dense, strategy = _weighted(dense, strategy, weights, scale)
        grouped = dense.T.groupby(groups, sort=False)
        combined = grouped.agg(strategy) if isinstance(strategy, str) else grouped.apply(strategy)
        attributes[attr] = combined.T
    return attributes


def _merging(groups: pd.Series) -> pd.Series:
    """Return the members of `groups` that merge with another."""
    return groups[groups.groupby(groups).transform("size") > 1]


def _merge(
    n: pypsa.Network, c: pypsa.Components, groups: pd.Series, existing: pd.Index = NO_ASSETS
) -> None:
    """Merge the assets of `c` that `groups` maps to one, under their representative."""
    merged = _merging(groups)
    if merged.empty:
        return
    attributes = _aggregated(n, c, merged, existing)
    n.remove(c.name, merged.index)
    n.add(c.name, merged.unique(), **attributes)


def _merge_cohorts(static: pd.DataFrame, groups: pd.Series) -> None:
    """Set the cohort of each asset of `static` to its group's.

    The group is built in the last build year of its members and retires with the first
    of them, so it is active in each investment period all of them are active in, and
    never retires if none of them does, as PyPSA-Eur merges power plants.
    """
    built = static["build_year"].groupby(groups).transform("max")
    retired = (static["build_year"] + static["lifetime"]).groupby(groups).transform("min")
    static["build_year"] = built
    static["lifetime"] = retired - built


def aggregate_entities(n: pypsa.Network, maps: SpatialMaps) -> None:
    """Merge the assets of `n` that `maps.entities` maps to one, under their representative.

    The assets `maps.dropped` names are removed. Attributes combine as
    PyPSA-Eur merges power plants, and averages are weighted by the shares the results are
    split back by. Each merged asset is built in the last build year of its members and
    retires with the first of them, so a candidate keeps its cohort, and one that maps to
    itself alone is left as it is.
    """
    for c in n.components[ENTITY_COMPONENTS]:
        n.remove(c.name, c.static.index.intersection(maps.dropped))
        groups = maps.entities.reindex(c.static.index)
        if "build_year" in c.static:
            _merge_cohorts(c.static, groups)
        _merge(n, c, groups, maps.horizons.index)


def _land_use_limits(n: pypsa.Network) -> pd.DataFrame:
    """Return the `constant` of each land-use limit of `n` and the one PyPSA-Eur's
    `add_land_use_constraint` states for it, as `stated`.

    That is the smallest finite `p_nom_max` of the extendable generators of its carrier at
    its bus built in its investment period, or NaN where there is none. Raises `ValueError`
    naming the limits without an investment period, and `NotImplementedError` naming the
    generators of a limit that share their resource class, as PyPSA-Eur states its limits
    for one candidate per class.
    """
    static = n.c.global_constraints.static
    land_use = static[_is_land_use(static)]
    periods = land_use["investment_period"]
    if periods.isna().any():
        names = land_use.index[periods.isna()].tolist()
        raise ValueError(f"Land-use limits without an investment period: {names}")
    columns = [land_use["carrier_attribute"], land_use["bus"], periods.astype(int)]
    keys = pd.MultiIndex.from_arrays(columns, names=LAND_USE_KEYS)
    generators = n.c.generators.static
    extendable = generators[generators["p_nom_extendable"]]
    candidates = extendable[pd.MultiIndex.from_frame(extendable[LAND_USE_KEYS]).isin(keys)]
    classes = [*LAND_USE_KEYS, *candidates.columns.intersection([RESOURCE_CLASS])]
    shared = candidates.index[candidates.duplicated(classes, keep=False)]
    if len(shared):
        raise NotImplementedError(f"No rule states land-use limits of generators {shared.tolist()}")
    potentials = candidates.groupby(LAND_USE_KEYS)["p_nom_max"].min()
    stated = potentials[np.isfinite(potentials)].reindex(keys)
    return land_use[["constant"]].assign(stated=stated.to_numpy())


def check_land_use(n: pypsa.Network) -> None:
    """Raise `ValueError` naming the land-use limits of `n` whose constant differs from the
    one `_land_use_limits` states, which aggregation could not state again."""
    limits = _land_use_limits(n)
    differ = limits.index[~np.isclose(limits["constant"], limits["stated"])]
    if len(differ):
        raise ValueError(f"Land-use limits not set by PyPSA-Eur's rule: {differ.tolist()}")


def restate_land_use(n: pypsa.Network) -> None:
    """Set the constant of each land-use limit of `n` to the one `_land_use_limits` states.

    A limit without one is removed, as PyPSA-Eur states none.
    """
    limits = _land_use_limits(n)
    n.c.global_constraints.static.loc[limits.index, "constant"] = limits["stated"]
    n.remove("GlobalConstraint", limits.index[limits["stated"].isna()])


def aggregate_lines(n: pypsa.Network, line_map: pd.Series) -> None:
    """Merge the parallel lines of `n` that `line_map` maps to one, under their representative.

    A merged line spans the distance between its buses, and its impedances and cost
    combine, as PyPSA merges lines where buses merge. Lines of one type keep it and take
    their impedances from it. Raises `ValueError` where lines of different types merge.
    Parallels and capacities add up, `s_nom_max` is as `_s_nom_max` says, and averages are
    weighted by `s_nom`. Each merged line keeps the build year and lifetime of its members.
    """
    _check_types(n.c.lines.static, line_map)
    limits = _s_nom_max(n.c.lines.static, line_map)
    _merge(n, n.components["Line"], line_map)
    n.c.lines.static.loc[limits.index, "s_nom_max"] = limits
    _apply_line_types(n)


def clip_p_max_pu(n: pypsa.Network, threshold: float) -> None:
    """Set each value of `CLIPPED` in `n` at most `threshold` from 0 to 0, as PyPSA-Eur's
    `solving.options.clip_p_max_pu` does. Static values are left as they are."""
    for name, attrs in CLIPPED.items():
        dynamic = n.components[name].dynamic
        for attr in attrs:
            frame = dynamic[attr]
            dynamic[attr] = frame.where(frame.abs() > threshold, 0.0)


def aggregate_network(
    n: pypsa.Network, record: DataRecord, aggregation: Aggregation
) -> pypsa.Network:
    """Return `n`, built from `record`, merged by `aggregation`: buses, then assets, then time.

    Without a bus aggregation, parallel lines merge by the entity aggregation. Before,
    `check_land_use` checks that the land-use limits of `n` follow PyPSA-Eur's rule, and
    after the assets merge, `restate_land_use` states them from the merged candidates.
    Last, `clip_p_max_pu` clips the merged network by `aggregation.clip_p_max_pu`, if set,
    with or without any other aggregation. Without any of them, `n` is returned as it is.
    """
    clustered = n
    if aggregation.bus is not None or aggregation.entity is not None:
        check_land_use(n)
        maps = spatial_maps(n, record, aggregation)
        if aggregation.bus is not None:
            clustered = aggregate_buses(n, maps)
        else:
            clustered = n.copy()
            aggregate_lines(clustered, maps.lines)
        aggregate_entities(clustered, maps)
        restate_land_use(clustered)
    if aggregation.snapshot is not None:
        clustered = cluster_network(clustered, record, aggregation.snapshot)
    if aggregation.clip_p_max_pu is not None:
        clustered = n.copy() if clustered is n else clustered
        clip_p_max_pu(clustered, aggregation.clip_p_max_pu)
    return clustered


def _at(frame: pd.DataFrame | pd.Series, groups: pd.Series) -> pd.DataFrame | pd.Series:
    """Return the value of each member of `groups` in `frame`, at its representative.

    Members whose representative `frame` lacks a column for are left out.
    """
    if isinstance(frame, pd.Series):
        return frame.loc[groups.to_numpy()].set_axis(groups.index)
    present = groups[groups.isin(frame.columns)]
    return frame[present.to_numpy()].set_axis(present.index, axis=1)


def _fractions(
    n: pypsa.Network, c: pypsa.Components, groups: pd.Series, shares: pd.Series
) -> pd.DataFrame:
    """Return each member's share of its group's flow at each snapshot.

    A load takes its share of the group's demand, though `_expand_entities` gives its flow
    `p` its own demand. A generator takes its share in proportion to its share of capacity
    times its `p_max_pu`. Any other asset, or where that is 0 across the group, takes its
    share of capacity.
    """
    flat = pd.DataFrame(
        np.tile(shares.to_numpy(), (len(n.snapshots), 1)), n.snapshots, shares.index
    )
    if c.name == "Load":
        weights = n.get_switchable_as_dense("Load", "p_set", inds=groups.index)
    elif c.name == "Generator":
        weights = flat * n.get_switchable_as_dense("Generator", "p_max_pu", inds=groups.index)
    else:
        return flat
    totals = weights.T.groupby(groups).transform("sum").T
    return (weights / totals).where(totals != 0, flat)


def _expand_buses(n_c: pypsa.Network, n_t: pypsa.Network, maps: SpatialMaps) -> None:
    for attr, frame in n_c.c.buses.dynamic.items():
        if attr in _outputs(n_c.components["Bus"]) and not frame.empty:
            n_t.c.buses.dynamic[attr] = _at(frame, maps.buses)


def _expand_branches(
    n_c: pypsa.Network, n_t: pypsa.Network, ctype: str, branches: pd.Series, flipped: pd.Series
) -> None:
    source, target = n_c.components[ctype], n_t.components[ctype]
    shares = _shares(target.static.loc[branches.index], ctype, branches)
    target.static["s_nom_opt"] = target.static["s_nom"]
    for attr in source.static.columns.intersection(_outputs(source)):
        if _is_result(attr):
            target.static.loc[shares.index, attr] = _at(source.static[attr], branches) * shares
    for attr, frame in source.dynamic.items():
        if attr not in _outputs(source) or (frame.empty and attr not in LINE_FLOWS):
            continue
        ahead = _at(frame, branches)
        behind = _at(source.dynamic[SWAPPED[attr]], branches).reindex(columns=ahead.columns)
        swapped = flipped.reindex(ahead.columns).to_numpy()
        held = pd.DataFrame(np.where(swapped, behind, ahead), ahead.index, ahead.columns)
        value = held if attr.startswith("mu") else held * shares[held.columns]
        target.dynamic[attr] = value.reindex(columns=target.static.index, fill_value=0.0)


def _expand_entities(n_c: pypsa.Network, n_t: pypsa.Network, maps: SpatialMaps) -> None:
    for target in n_t.components:
        if (
            target.name in {"Bus", "SubNetwork", "GlobalConstraint", *BRANCHES}
            or target.static.empty
            or _outputs(target).empty
        ):
            continue
        source = n_c.components[target.name]
        index = target.static.index.drop(maps.dropped, errors="ignore")
        groups = maps.entities.reindex(index).combine_first(_identity(index))
        shares = _shares(target.static.loc[index], target.name, groups, maps.horizons.index)
        for attr in source.static.columns.intersection(_outputs(source)):
            if _is_result(attr):
                held = _at(source.static[attr], groups)
                target.static[attr] = held if _is_held(attr) else held * shares
        fractions = _fractions(n_t, target, groups, shares)
        for attr, frame in source.dynamic.items():
            if attr in _outputs(source) and not frame.empty:
                held = _at(frame, groups)
                if target.name == "Load" and attr == "p":
                    demand = n_t.get_switchable_as_dense("Load", "p_set", inds=held.columns)
                    target.dynamic[attr] = demand
                else:
                    shared = held if _is_held(attr) else held * fractions[held.columns]
                    target.dynamic[attr] = shared
        _expand_dropped(target, target.static.index.intersection(maps.dropped))


def _expand_constraints(n_c: pypsa.Network, n_t: pypsa.Network, maps: SpatialMaps) -> None:
    """Give each global constraint the duals of the one it merged into, or 0 where that was
    not stated again."""
    source, target = n_c.c.global_constraints, n_t.c.global_constraints
    for attr in source.static.columns.intersection(_outputs(source)):
        held = source.static[attr].reindex(maps.constraints.to_numpy(), fill_value=0.0)
        target.static[attr] = held.set_axis(maps.constraints.index)


def _expand_dropped(target: pypsa.Components, dropped: pd.Index) -> None:
    """Give each asset of `dropped` in `target` the results PyPSA gives a fixed asset that is
    never active: its capacity and no flow."""
    nominal = NOMINAL.get(target.name, "p_nom")
    if nominal in target.static:
        target.static.loc[dropped, f"{nominal}_opt"] = target.static.loc[dropped, nominal]
    solved = SOLVED.get(target.name, ["p"])
    for attr, frame in target.dynamic.items():
        if attr in _outputs(target) and (attr in solved or not frame.empty):
            frame[dropped] = 0.0


def _expanded(n_c: pypsa.Network, n_t: pypsa.Network, maps: SpatialMaps) -> pypsa.Network:
    n_t.calculate_dependent_values()
    n_t.determine_network_topology()
    _expand_buses(n_c, n_t, maps)
    _expand_branches(n_c, n_t, "Line", maps.lines, maps.flipped)
    unflipped = pd.Series(False, index=maps.transformers.index)
    _expand_branches(n_c, n_t, "Transformer", maps.transformers, unflipped)
    _expand_entities(n_c, n_t, maps)
    _expand_constraints(n_c, n_t, maps)
    return n_t


def expand_network(
    n_c: pypsa.Network, n: pypsa.Network, record: DataRecord, aggregation: Aggregation
) -> pypsa.Network:
    """Return `n`, built from `record`, with the results of `n_c`: `n` merged by `aggregation`.

    The returned network has every bus and asset of `n`, at the snapshots of `n_c`, so
    still merged by the time aggregation of `aggregation`, if any. Without a bus or entity
    aggregation, it is `n_c`. Results are spread over the members of each merged bus,
    line or asset by these rules:

    - A bus takes the results of its representative.
    - A line between merged buses, or merged in parallel, takes the flows and capacity of
      the merged line in proportion to its share of their `s_nom`, and its duals. A line
      or transformer within a merged bus keeps its capacity and carries no flow.
    - An asset takes the capacity and flows of the merged asset in proportion to its share
      of their largest capacity, `p_nom_max` or `e_nom_max`, if an extendable candidate,
      or of their capacity, `p_nom` or `e_nom`, if not. Where one has no limit, the
      shares are equal. A generator's flow follows its own
      `p_max_pu`, and a load draws its own demand, so the merged flow is kept at each
      snapshot. An asset takes the duals and commitment of the merged asset.
    - A global constraint takes the dual of the one it merged into. A land-use limit
      takes that of the limit stated again for its merged bus, carrier and period, or 0
      where none was.
    - An existing asset active in no investment period, or a one-port without a value
      that the entity aggregation drops, keeps its capacity and carries no flow.

    Links and other assets that moved to a merged bus keep their own results.
    """
    if aggregation.bus is None and aggregation.entity is None:
        return n_c
    snapshot = aggregation.snapshot
    template = n.copy() if snapshot is None else cluster_network(n, record, snapshot)
    return _expanded(n_c, template, spatial_maps(n, record, aggregation))
