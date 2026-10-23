# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""The PyPSA tool: record -> `pypsa.Network` -> results.

The only module that knows PyPSA's network shape - that its axes are
`snapshot`/`period`/`scenario`, that a stochastic network is indexed by
`(scenario, name)`, and how its static/series split maps onto the record's
`dims/entity` + `inputs/` split.

Notes
-----
- [where a value lives](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
- [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
"""

from __future__ import annotations

import math
import re
import warnings
from collections.abc import Container, Mapping, Sequence
from dataclasses import dataclass
from functools import cache, cached_property
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import narwhals as nw
import numpy as np
import pandas as pd
from duckdb import CoalesceOperator as coalesce
from duckdb import ColumnExpression as col
from duckdb import ConstantExpression as lit
from duckdb import (
    DuckDBPyConnection,
    DuckDBPyRelation,
    Expression,
    FunctionExpression,
)
from duckdb import StarExpression as star

from datarecord.duck import DuckTypes, ex_all, fn, struct_of
from datarecord.layered.categories import (
    carried_properties,
    matching,
    with_defaults,
)
from datarecord.record import Flags, Frames, LazyFrames, RecordLike
from datarecord.schema import (
    LONG_TAIL,
    AttributeSpec,
    Dimension,
    Group,
    PropertySpec,
    Trait,
)
from datarecord.schema import Schema as RecordSchema
from datarecord.tools.base import (
    Requirements,
    Schema,
    Tool,
    UnsupportedRecordError,
    to_relation,
)

if TYPE_CHECKING:
    import pypsa

# The axes a PyPSA network is built from; all three must be declared in the
# schema's `dimensions`, since a network shape is built from them (https://energy-models.github.io/datarecord/design/tools/).
# A declared axis with no rows is fine - that is just a deterministic or
# single-period network.
SNAPSHOT, PERIOD, SCENARIO = "snapshot", "period", "scenario"
# Not PyPSA's own `weight` - that name is a Generator attribute (its clustering
# weight), and a record has one attribute per name record-wide - so the scenario
# weighting is renamed on the way in and back to `weight` on build.
SCENARIO_WEIGHT = "scenario_weight"
ENTITY, BUS, CONNECTION = "entity", "bus", "connection"
ENTITY_TYPE = "entity_type"
#: The registry inputs declared as properties of `entity`, beside `entity_type`:
#: what describes a component rather than data a model optimises against.
ENTITY_PROPERTIES = ("carrier", "sign", "type")
#: A property of the `connection` group, its port vocabulary being this tool's.
ROLE = "role"
REQUIRED_DIMS = frozenset({SNAPSHOT, PERIOD, SCENARIO})

# PyPSA's `defaults["typ"]` (the attribute's Python type) mapped to the narwhals
# type the long schema stores, `String` for anything unlisted. Keyed on `typ` -
# what a value *is* - not `type`, whose `"static or series"`-style strings
# describe only where it lives and grow a new variant per PyPSA release.
_DTYPES = {
    bool: nw.Boolean(),
    int: nw.Int64(),
    float: nw.Float64(),
    str: nw.String(),
}


def _default(value: Any) -> Any:
    """One `defaults["default"]` cell as JSON-storable, NaN as absent.

    Notes
    -----
    - [AttributeSpec](https://energy-models.github.io/datarecord/design/schema/#attributespec)
    """
    if isinstance(value, float) and math.isnan(value):
        return None
    return value.item() if hasattr(value, "item") else value


def _same(a: Any, b: Any) -> bool:
    """Whether two `_default` values are one default, `True` and `1` being two."""
    return type(a) is type(b) and a == b


def _text(value: Any) -> str | None:
    """One `unit`/`description` cell as text, or None where PyPSA has none.

    Its registry leaves both NaN rather than empty, and `None` is the schema's
    "undeclared" - `""` would claim the attribute is documented as blank, or
    dimensionless, neither of which a missing cell says.

    Notes
    -----
    - [unit and description](https://energy-models.github.io/datarecord/design/schema/#unit-and-description)
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    return text or None


@dataclass(frozen=True)
class NetworkShape:
    """PyPSA's reading of a record's axis frames.

    The axis names and the index convention live here rather than on the
    record, which stays schema-generic: a record may declare any dims, and it is
    this tool that decides `snapshot` is the time axis and that a non-empty
    `scenario` axis means a stochastic network.

    Notes
    -----
    - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
    """

    dims: Frames

    def _axis(self, dim: str) -> pd.DataFrame:
        """`dim`'s axis as a DataFrame, empty if the record declares none.

        A dim with no rows anywhere is absent from the mapping rather than
        present-and-empty, and both read the same way here: an empty
        frame, which is a deterministic or single-period network.

        Notes
        -----
        - [the long schema](https://energy-models.github.io/datarecord/design/format/#the-long-schema)
        """
        frame = self.dims.get(dim)
        return (
            frame.to_native().df() if frame is not None else pd.DataFrame(columns=[dim])
        )

    @cached_property
    def snapshots(self) -> pd.DataFrame:
        return self._axis(SNAPSHOT)

    @cached_property
    def periods(self) -> pd.DataFrame:
        return self._axis(PERIOD)

    @cached_property
    def scenarios(self) -> pd.DataFrame:
        return self._axis(SCENARIO)

    @property
    def stochastic(self) -> bool:
        return not self.scenarios.empty

    @property
    def multiperiod(self) -> bool:
        return not self.periods.empty

    @property
    def index_names(self) -> list[str]:
        """The static frame's index: PyPSA carries `scenario` as a level.

        Notes
        -----
        - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
        """
        return [SCENARIO, "entity"] if self.stochastic else ["entity"]


def _connection(record: RecordLike) -> DuckDBPyConnection:
    """The DuckDB connection `record`'s frames belong to.

    Off the concrete backing, since the protocol stays backend-agnostic.
    Needed because a relation exposes no reachable reference to its connection,
    and this tool's `PIVOT` - which narwhals cannot express and
    `relation.query` refuses as a `MULTI` statement - needs one.

    Raises
    ------
    TypeError
        If `record` exposes no connection, i.e. is not DuckDB-backed.

    Notes
    -----
    - [the protocol names no engine](https://energy-models.github.io/datarecord/design/record/#the-protocol-names-no-engine)
    """
    con = getattr(record, "con", None)
    if not isinstance(con, DuckDBPyConnection):
        msg = (
            f"{type(record).__name__} exposes no DuckDB connection; "
            "the PyPSA tool builds with DuckDB SQL"
        )
        raise TypeError(msg)
    return con


# -- long -> wide -----------------------------------------------------------


@dataclass(frozen=True)
class Index:
    """A pandas Index paired with a matching DuckDB relation.

    `rel` carries `_pos`, the index's row position, so a join against it can
    be restored to `index`'s order (not necessarily sorted) by ordering on
    `_pos` rather than by value.
    """

    index: pd.Index
    rel: DuckDBPyRelation

    @classmethod
    def of(cls, index: pd.Index, con: DuckDBPyConnection) -> Index:
        df = index.to_frame(index=False)  # noqa: F841 - queried by name below
        return cls(index, con.sql("SELECT *, row_number() OVER () AS _pos FROM df"))

    def expand(self, rel: DuckDBPyRelation, column: str) -> DuckDBPyRelation:
        """Broadcast rows with a null `column` across this index, others as-is.

        `rel` must already carry the alias the caller wants to select its
        own columns by - `expand` doesn't impose one.
        """
        if len(self.index) == 0:
            return rel
        # `IS NULL = true` hashes; the one-sided `IS NULL` is a nested loop.
        axis = self.rel.project(col(column), lit(True).alias("_broadcast"))  # noqa: FBT003
        return rel.join(
            axis.set_alias("_ax"),
            col(rel.alias, column).isnull() == col("_ax", "_broadcast"),
            how="left",
        ).project(
            *(col(rel.alias, c) for c in rel.columns if c != column),
            coalesce(col(rel.alias, column), col("_ax", column)).alias(column),
        )

    def left_join(self, other: DuckDBPyRelation, on: Sequence[str]) -> DuckDBPyRelation:
        """LEFT JOIN `other` onto this index, restored to `index`'s row order."""
        return self.rel.join(
            other,
            ex_all(col(self.rel.alias, f) == col(other.alias, f) for f in on),
            how="left",
        ).order(f"{self.rel.alias}._pos")


def _assign_static(
    static: DuckDBPyRelation,
    attributes: dict[str, tuple[DuckDBPyRelation, Flags]],
    shape: NetworkShape,
    scenarios: Index,
    con: DuckDBPyConnection,
) -> pd.DataFrame:
    """Set each varying attribute's static-valued entries, resolved to a wide frame."""
    keys = shape.index_names

    # `static` already carries a `_pos` in member order, assigned before the
    # connection collapse could scramble it (`build`); the wide frame is ordered
    # by it below (https://energy-models.github.io/datarecord/design/read-path/#one-fold-for-every-axis).

    # An entity exists once, whatever the scenario, so the record's member
    # frame carries one row per entity - where PyPSA's static container is
    # `(scenario, name)`-indexed. Repeated here, and any attribute that really
    # differs between scenarios arrived as `inputs/` rows and is assigned over
    # the repeats below.
    if shape.stochastic and SCENARIO not in static.columns:
        static = scenarios.expand(
            static.project(f"*, NULL AS {SCENARIO}").set_alias("m"), SCENARIO
        )

    picked: dict[str, DuckDBPyRelation] = {}
    over_snapshots: set[str] = set()
    for attr, (long, flags) in attributes.items():
        # PyPSA's `static` container takes the rows that do not vary over
        # `snapshot`. Two ways an attribute has them, and the flags distinguish
        # the two because they are scoped to what it is addressed by (https://energy-models.github.io/datarecord/design/record/#flags):
        # a NULL-snapshot row on an attribute that *may* vary over it puts
        # `snapshot` in `broadcast`, while one not addressed by it at all has
        # `snapshot` in neither set and every row static.
        addressed = SNAPSHOT in (flags.varies | flags.broadcast)
        if addressed and SNAPSHOT not in flags.broadcast:
            continue
        rows = long
        if shape.stochastic:
            if SCENARIO not in rows.columns:
                rows = rows.project(f"*, CAST(NULL AS VARCHAR) AS {SCENARIO}")
            rows = scenarios.expand(rows, SCENARIO)
        picked[attr] = rows
        if addressed:
            over_snapshots.add(attr)

    frame = _left_join_values(static, picked, over_snapshots, keys, con)
    # Scenario-major: PyPSA's `(scenario, name)` index groups a scenario's
    # components together, and `_pos` gives the order within one - the
    # entity axis carrying one row per entity rather than one per scenario, so
    # it cannot order the outer level itself. A stable sort keeps that order.
    if shape.stochastic:
        frame = frame.sort_values(
            SCENARIO,
            kind="stable",
            key=lambda s: s.map({v: i for i, v in enumerate(scenarios.index)}),
        )
    return frame.set_index(keys)


def _left_join_values(
    static: DuckDBPyRelation,
    values: Mapping[str, DuckDBPyRelation],
    over_snapshots: Container[str],
    keys: Sequence[str],
    con: DuckDBPyConnection,
) -> pd.DataFrame:
    """`static` with each of `values` left-joined on `keys` as its named column, in `_pos` order.

    A value fills its column where `static` has none (`COALESCE`); `_pos` is
    dropped. A left join from `static` drops a value with no matching static
    row rather than adding one, which also scopes the rows to `static`'s
    members. The first row per key wins, as `values[~values.index.duplicated()]`
    does; any deterministic order is fine since a valid record never collides.

    Each relation is held in a table of its own before the joins, dropped
    after: the relation API binds the whole tree again at every step, and a
    resolved attribute's tree is deep, so chaining the joins over the lazy
    relations made one type's static frame quadratic in its attribute count.

    Parameters
    ----------
    values
        Long rows carrying `keys` and `value`, by the column they fill.
    over_snapshots
        Names in `values` addressed by `snapshot`, of whose rows only the
        NULL-snapshot ones are static.
    """
    tag = uuid4().hex
    tables = [f"_pypsa_static_{tag}"]
    static.create(tables[0])
    try:
        joined = con.table(tables[0]).set_alias("s")
        partition = ", ".join(keys)
        exprs = {}
        for i, (name, long) in enumerate(values.items()):
            rows = (
                long.filter(col(SNAPSHOT).isnull()) if name in over_snapshots else long
            )
            tables.append(f"_pypsa_value_{tag}_{i}")
            rows.project(*(col(k) for k in keys), col("value")).create(tables[-1])
            alias = f"a{i}"
            picked = (
                con.table(tables[-1])
                .project(f"*, row_number() OVER (PARTITION BY {partition}) AS _rn")
                .filter(col("_rn") == lit(1))
                .set_alias(alias)
            )
            joined = joined.join(
                picked, ex_all(col("s", k) == col(alias, k) for k in keys), how="left"
            )
            value = col(alias, "value")
            exprs[name] = (
                coalesce(value, col("s", name)) if name in static.columns else value
            ).alias(name)
        return (
            joined.order("s._pos")
            .project(
                *(
                    col("s", c)
                    for c in static.columns
                    if c not in exprs and c != "_pos"
                ),
                *exprs.values(),
            )
            .df()
        )
    finally:
        for table in tables:
            con.execute(f"DROP TABLE IF EXISTS {table}")


def _series_frame(
    rows: DuckDBPyRelation,
    shape: NetworkShape,
    periods: Index,
    scenarios: Index,
    snapshots: Index,
    static_index: pd.Index,
    con: DuckDBPyConnection,
) -> pd.DataFrame:
    """Pivot long series rows to the `n.snapshots x static_index` frame.

    `snapshots` (the row axis) is known before the pivot, so missing rows are
    filled by joining against it directly rather than reindexing pandas-side
    after. Columns stay restricted to what the data actually pivoted, only
    ordered to match `static_index`: `_import_series_from_df` takes
    `df.columns` as-is without merging against `static`, so a column added
    just to complete `static_index` would wrongly force that component into
    `dynamic` instead of leaving it static.

    The pivot is on each column's position in `static_index` rather than its
    name, so a name never becomes an SQL identifier: one equal to a group-by
    column would collide with it, and DuckDB folds identifiers' case.

    Notes
    -----
    - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
    """
    if shape.multiperiod:
        rows = periods.expand(rows, PERIOD)
    if shape.stochastic:
        rows = scenarios.expand(rows, SCENARIO)
    group_by = [PERIOD, SNAPSHOT] if shape.multiperiod else [SNAPSHOT]
    keys = shape.index_names
    columns = Index.of(static_index.set_names(keys), con).rel.set_alias("k")
    rows = rows.set_alias("r")
    positioned = rows.join(  # noqa: F841 - bound by name for the query below
        columns, ex_all(col("r", k) == col("k", k) for k in keys)
    ).project(
        *(col("r", g) for g in group_by),
        col("k", "_pos").alias("_col"),
        col("r", "value"),
    )
    piv = con.sql(
        f"PIVOT positioned ON _col USING first(value) GROUP BY {', '.join(group_by)}"
    )

    present = sorted(int(c) for c in set(piv.columns) - set(group_by))
    if not present:
        return pd.DataFrame(index=snapshots.index, columns=static_index[:0])

    wide = (
        snapshots.left_join(piv.set_alias("piv"), group_by)
        .project(*(col("piv", str(p)) for p in present))
        .df()
    )
    wide.index = snapshots.index
    wide.columns = static_index[[p - 1 for p in present]]
    return wide


# -- build (https://energy-models.github.io/datarecord/design/tools/) -------------------------------------------------------------


def _exported(c) -> bool:
    """Whether `c`'s members belong in a record at all.

    Empty types have nothing to write. Standard types (`LineType`,
    `TransformerType`) are excluded because PyPSA prepopulates them on every
    fresh `Network` and `_broadcast_standard_types` restores them on build -
    writing them would import each row a second time on the way back.
    """
    return not c.static.empty and c.name not in c.n.standard_type_components


_SUB_NETWORK = "SubNetwork"
#: After a SubNetwork's name in a record. PyPSA numbers them `0`, `1`, ... as it
#: numbers Lines, and a record's names are unique across types.
_SUB_NETWORK_SUFFIX = " SubNetwork"


def _record_name(ctype: str, name: str) -> str:
    """`name` as the record keys it: a SubNetwork's suffixed, any other as is."""
    return f"{name}{_SUB_NETWORK_SUFFIX}" if ctype == _SUB_NETWORK else name


def _sub_network_named(rel: DuckDBPyRelation, column: str) -> DuckDBPyRelation:
    """`rel` with `_SUB_NETWORK_SUFFIX` after every value of `column`."""
    return rel.select(
        *(
            FunctionExpression("concat", col(c), lit(_SUB_NETWORK_SUFFIX)).alias(c)
            if c == column
            else col(c)
            for c in rel.columns
        )
    )


def _sub_network_unnamed(rel: DuckDBPyRelation, column: str) -> DuckDBPyRelation:
    """`rel` with `_SUB_NETWORK_SUFFIX` taken off `column`, where it ends with it."""
    pattern = lit(f"{re.escape(_SUB_NETWORK_SUFFIX)}$")
    return rel.select(
        *(
            FunctionExpression("regexp_replace", col(c), pattern, lit("")).alias(c)
            if c == column
            else col(c)
            for c in rel.columns
        )
    )


def _colliding_names(n: pypsa.Network) -> frozenset[str]:
    """Names more than one exported component claims.

    Only exported types count, since only those become member rows. Read off the
    `name` level rather than the index: a stochastic network is keyed
    `(scenario, name)`, and comparing tuples would read one component in two
    scenarios as two names while missing a real collision.

    Notes
    -----
    - [entity is unique across types](https://energy-models.github.io/datarecord/design/format/#entity-is-unique-across-types)
    - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
    """
    seen: dict[str, str] = {}
    clashing: set[str] = set()
    for c in n.components:
        if not _exported(c):
            continue
        index = c.static.index
        names = (
            index.get_level_values("name") if "name" in (index.names or []) else index
        )
        for value in names:
            name = _record_name(c.name, str(value))
            if seen.setdefault(name, c.name) != c.name:
                clashing.add(name)
    return frozenset(clashing)


def _custom_columns(n: pypsa.Network) -> dict[str, dict[str, nw.dtypes.DType]]:
    """Exported type -> its static columns PyPSA's registry has no entry for, typed.

    A network may carry its own (`ac_dc_meshed`'s `Bus.country`). Each is an
    attribute the network's schema declares over
    `entity` and carries by that type alone (`_NetworkSource.schema`).
    """
    found: dict[str, dict[str, nw.dtypes.DType]] = {}
    for c in n.components:
        if not _exported(c):
            continue
        columns = {
            name: _column_dtype(c.static[name])
            for name in c.static.columns
            if name not in c.defaults.index
        }
        if columns:
            found[c.name] = columns
    return found


def _clashing_columns(n: pypsa.Network) -> frozenset[tuple[str, str]]:
    """`(type, column)` of `_custom_columns` the registry declares other than over `entity`.

    Such a column has nowhere to be stored: its name is already one spec,
    record-wide, of a shape no entity axis column has.
    """
    declared = _registry_schema()
    return frozenset(
        (ctype, name)
        for ctype, columns in _custom_columns(n).items()
        for name in columns
        if (spec := declared.spec_for(name)) is not None
        and spec.dims != frozenset({ENTITY})
    )


def _column_dtype(values: pd.Series) -> nw.dtypes.DType:
    """The narwhals type a custom static column is declared with, `String` for anything unlisted."""
    if pd.api.types.is_bool_dtype(values):
        return nw.Boolean()
    if pd.api.types.is_integer_dtype(values):
        return nw.Int64()
    if pd.api.types.is_float_dtype(values):
        return nw.Float64()
    return nw.String()


# TODO(pypsa): every function below, up to `_new_network`, ports a method that
# only exists on PyPSA's unreleased data-records branch (https://energy-models.github.io/datarecord/design/tools/). Delete the
# ported copy and call the real method once a PyPSA release carries it.


def _apply_snapshots_import(n: pypsa.Network, df: pd.DataFrame) -> None:
    """Set snapshots and snapshot weightings from an imported axis table.

    Ported from `pypsa.Network._apply_snapshots_import` (unreleased) -
    built entirely from public surface (`set_snapshots`, `snapshot_weightings`).

    Notes
    -----
    - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
    """
    snapshot_levels = {"period", "timestep", "snapshot"}.intersection(df.columns)
    if snapshot_levels:
        df = df.set_index(sorted(snapshot_levels))
    n.set_snapshots(df.index)

    cols = ["objective", "stores", "generators"]
    if not df.columns.intersection(cols).empty:
        existing_cols = [c for c in cols if c in df.columns]
        n.snapshot_weightings = df.reindex(index=n.snapshots, columns=existing_cols)
    elif "weightings" in df.columns:
        n.snapshot_weightings = df["weightings"].reindex(n.snapshots)


def _broadcast_standard_types(n: pypsa.Network) -> None:
    """Broadcast standard-type static tables across scenarios after import.

    Ported from `pypsa.Network._broadcast_standard_types` (unreleased).

    Notes
    -----
    - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
    """
    for component in n.standard_type_components:
        comp = n.components[component]
        if n.has_scenarios and not isinstance(comp.static.index, pd.MultiIndex):
            comp.static = pd.concat(
                dict.fromkeys(n.scenarios, comp.static), names=["scenario"]
            )


def _collect_network_attributes(n: pypsa.Network) -> dict[str, Any]:
    """The serializable scalar network attributes (incl. `name`, `pypsa_version`).

    Ported from `pypsa.Network._collect_network_attributes` (unreleased),
    trimmed of nothing - the reflection over `dir(n)` is exactly what decides
    which attributes are safe to round-trip, so there is no smaller version of
    this that still answers the same question.

    Notes
    -----
    - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
    """
    numpy_types = tuple(np.sctypeDict.values())
    allowed_types = (float, int, bool, str)
    skip_attrs = {
        "component_attrs",
        "df",
        "pnl",
        "static",
        "dynamic",
        "iterate_components",
        "_name",
        "_pypsa_version",
    }

    attrs: dict[str, Any] = {}
    for attr in dir(n):
        if attr.startswith("__") or attr in skip_attrs:
            continue
        # Skip read-only properties (except pypsa_version) without invoking
        # their getters, which may emit warnings (e.g. model, objective).
        prop = getattr(type(n), attr, None)
        if isinstance(prop, property) and prop.fset is None and attr != "pypsa_version":
            continue
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=r".*component_attrs is deprecated as of 1\.0.*",
                category=DeprecationWarning,
            )
            warnings.filterwarnings(
                "ignore",
                message=r".*the API for how to access components data has changed.*",
                category=DeprecationWarning,
            )
            value = getattr(n, attr)
        if isinstance(value, numpy_types):
            attrs[attr] = value.item()
        elif isinstance(value, allowed_types):
            attrs[attr] = value
    return attrs


def _apply_network_attributes(n: pypsa.Network, attrs: dict[str, Any]) -> None:
    """Apply scalar network attributes read back from a record.

    Ported from `pypsa.Network._apply_network_attributes` (unreleased),
    stripped of the version-compat warnings and PyPI update check the real
    method also does: those are for a human importing a file written by an
    older PyPSA, and have nothing to check here since `to_datarecord` and this
    function always agree on what `attrs` holds.

    Notes
    -----
    - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
    """
    attrs = dict(attrs)
    name = attrs.pop("name", None)
    if name is not None:
        n.name = name
    attrs.pop("pypsa_version", None)
    for attr, value in attrs.items():
        if attr in ("model", "objective", "objective_constant"):
            setattr(n, f"_{attr}", value)
        else:
            setattr(n, attr, value)


def _new_network(record: RecordLike, shape: NetworkShape) -> pypsa.Network:
    """An empty network with the record's axes already established."""
    import pypsa

    schema = record.schema
    n = pypsa.Network()
    _apply_network_attributes(n, schema.meta.get("attributes") or {})
    n.meta = schema.meta.get("meta") or {}

    _apply_snapshots_import(n, shape.snapshots)
    if shape.multiperiod:
        ip = shape.periods.set_index(PERIOD)
        n.periods = ip.index
        n._investment_periods_data = ip.reindex(n.investment_periods)
    if shape.stochastic:
        # `set_scenarios` rather than assigning `_scenarios_data`: it rebuilds
        # each component's empty `static`/`dynamic` frames with the `scenario`
        # level, so later imports union against a correctly named 2-level index
        # instead of the single-level one a fresh component carries.
        n.set_scenarios(_scenario_weights(record, shape))
    return n


def _scenario_weights(record: RecordLike, shape: NetworkShape) -> pd.Series:
    """Each scenario's `scenario_weight`, in axis order.

    A scenario's own row wins over a NULL-scenario row, which reaches every
    scenario; one reached by neither takes an equal share.
    """
    index = pd.Index(shape.scenarios[SCENARIO].astype(str), name=SCENARIO)
    frame = record.attributes.get(SCENARIO_WEIGHT)
    stored: dict[str, float] = {}
    broadcast: list[float] = []
    if frame is not None:
        rows = frame.select(SCENARIO, "value")
        unset = nw.col(SCENARIO).is_null()
        broadcast = rows.filter(unset).collect()["value"].to_list()
        own = rows.filter(~unset).collect().iter_rows()
        stored = {str(scenario): value for scenario, value in own}
    weights = pd.Series(stored, dtype=float).reindex(index)
    if broadcast:
        weights = weights.fillna(float(broadcast[0]))
    return weights.fillna(1 / len(index)).rename("weight")


def _add_component_type(
    n: pypsa.Network,
    ctype: str,
    static: DuckDBPyRelation,
    attributes: dict[str, tuple[DuckDBPyRelation, Flags]],
    shape: NetworkShape,
    con: DuckDBPyConnection,
) -> None:
    """Assign one type's static frame, then its series."""
    scenarios = Index.of(n.scenarios, con)
    static_df = _assign_static(static, attributes, shape, scenarios, con)
    n._import_components_from_df(static_df, ctype)

    periods = Index.of(n.investment_periods, con)
    snapshots = Index.of(n.snapshots, con)
    static_index = n.c[ctype].static.index
    for attr, (long, flags) in attributes.items():
        # ... and `dynamic` the per-snapshot ones.
        if SNAPSHOT not in flags.varies:
            continue
        ts_rows = long.filter("snapshot IS NOT NULL")
        # Partial columns keep non-series components static (https://energy-models.github.io/datarecord/design/tools/).
        wide = _series_frame(
            ts_rows, shape, periods, scenarios, snapshots, static_index, con
        )
        n._import_series_from_df(wide, ctype, attr)


# -- results (https://energy-models.github.io/datarecord/design/read-path/#outputs) ---------------------------------------------------------


def _output_attributes(c: pypsa.Components) -> frozenset[str]:
    """A component type's result attributes, from PyPSA's own registry.

    `defaults["status"]` marks them ("Output"), so a PyPSA upgrade that adds a
    result attribute is picked up rather than needing a list kept here. Read off
    `c` rather than the bare registry: a network's extra ports (`p2` on a Link
    with `bus2`) exist only in its own `defaults`.
    """
    defaults = c.defaults
    is_output = defaults["status"].astype(str).str.startswith("Output")
    return frozenset(defaults.index[is_output])


_DERIVED_RESULTS: dict[str, frozenset[str]] = {"Bus": frozenset({"p", "q"})}
"""Results not written, by type: each is derivable from the ones that are.

`Bus.p` and `Bus.q` are the signed sum of the `p`/`q` results on the
connections at that bus, and as an entity-level `p` they would collide with
the connection-level one.
"""

_INTERNAL_RESULTS: dict[str, str] = {"p": "p_internal"}
"""A result at no port, renamed off the per-port result whose name it shares.

`Link.p` and `Process.p` are the power inside the component rather than at a
bus, so they are an entity-level result beside the connection-level `p`, and
one name holds one spec record-wide.
"""


def _result_attributes(c: pypsa.Components, inputs: Container[str]) -> dict[str, str]:
    """`c`'s PyPSA outputs -> the result each lands in, the rule schema and frames share.

    A per-port output (`p0`, `p1`, `p2`, a one-port type's `p`) lands in its
    stem, one row per connection, exactly as a per-port input does; any other
    keeps PyPSA's name, but for `_INTERNAL_RESULTS`. Dropped: `name`, which is
    the member list rather than a value, `_DERIVED_RESULTS`, and any result
    named in `inputs`, the record's input declarations: one attribute holds
    one spec record-wide, and PyPSA registers some names (`Bus.control`,
    `SubNetwork.carrier`) as an output on one type and an input on another.

    Notes
    -----
    - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
    - [outputs](https://energy-models.github.io/datarecord/design/read-path/#outputs)
    - [results on connections](https://energy-models.github.io/datarecord/design/tools/#results-on-connections)
    """
    per_port = _port_stems(c)
    derived = _DERIVED_RESULTS.get(c.name, frozenset())
    results = {}
    for attr in _output_attributes(c):
        if attr == "name" or attr in derived:
            continue
        name = per_port.get(attr) or _INTERNAL_RESULTS.get(attr, attr)
        if name not in inputs:
            results[attr] = name
    return results


# -- network -> layer (https://energy-models.github.io/datarecord/design/format/) ------------------------------------------------

# Which end of the component a port is. PyPSA encodes this only by sign
# convention - `p0` flows in at `bus0`, `p1` out at `bus1` - so the mapping to
# a record's `role` lives here, the one place that convention is written down
# (https://energy-models.github.io/datarecord/design/record/#connections). Ports beyond the first two are outputs: a multi-port Link's `bus2`
# onward are additional sinks.
_INPUT_PORT, _OUTPUT_PORT, _SINGLE_PORT = "input", "output", "attached"
# Every value `_port_role` can return - the closed vocabulary of `role`, so the
# schema declares it as an enum rather than a bare string.
_ROLES = (_INPUT_PORT, _OUTPUT_PORT, _SINGLE_PORT)

_PORT_SUFFIX = re.compile(r"(.+?)(\d+)")


@cache
def _per_port_stems() -> frozenset[str]:
    """Every attribute stem some PyPSA type carries once per port, inputs and results alike.

    A record stores each as one bus-keyed attribute, so these are the names
    whose port suffix is undone on write. Read off the registry: a name ending
    in one of its type's port indices (`bus0`, `p1`, `rate0`, `delay1`), and
    the stems a multi-port type leaves unsuffixed at port `1` (a Link's
    `efficiency`, `delay`, `cyclic_delay`), which no suffix gives away.

    Notes
    -----
    - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
    """
    import pypsa

    n = pypsa.Network()
    stems: set[str] = set()
    for ctype in n.all_components:
        c = n.components[ctype]
        ports = set(c.ports) - {""}
        stems |= set(getattr(c, "_unsuffixed_attrs", ()))
        stems |= {
            match.group(1)
            for attr in c.defaults.index
            if (match := _PORT_SUFFIX.fullmatch(attr)) and match.group(2) in ports
        }
    return frozenset(stems)


def _port_role(port: str) -> str:
    """The `role` for a port index.

    A single-port component (`c.ports == [""]`, e.g. a Generator's one `bus`)
    is neither an input nor an output end - it has only one attachment - so it
    gets its own role rather than being forced into the two-ended convention.

    Notes
    -----
    - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
    """
    if port == "":
        return _SINGLE_PORT
    return _INPUT_PORT if port == "0" else _OUTPUT_PORT


def _port_attribute(stem: str, port: str, registered: Container[str]) -> str:
    """PyPSA's name for `stem` at `port`: `bus0`, `p1`, `efficiency`, `efficiency2`, ...

    A stem PyPSA registers at port `0` (`bus0`, `p0`, `q0`, `rate0`) is suffixed from
    `0`; one it does not (`efficiency`) leaves port `1` unsuffixed and is
    suffixed from `2`. A one-port type's port `""` is the bare stem. That quirk
    is why a record keys connections by bus instead.

    Parameters
    ----------
    registered
        The type's attribute names, `c.defaults.index`, which say whether
        `stem` starts at port `0`.

    Notes
    -----
    - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
    """
    if port == "1" and f"{stem}0" not in registered:
        return stem
    return f"{stem}{port}"


def _carries(stem: str, port: str, registered: Container[str]) -> bool:
    """Whether PyPSA has a `stem` column at `port`.

    A port the bare registry declares carries only the stems it registers
    there (a Link's bus0 has no `efficiency0`); one beyond it is an
    additional port, which PyPSA gives every per-port stem (`efficiency2`).
    """
    return (
        _port_attribute(stem, port, registered) in registered
        or _port_attribute(BUS, port, registered) not in registered
    )


@cache
def _registered(ctype: str) -> frozenset[str]:
    """`ctype`'s attribute names in PyPSA's bare registry, for `_port_attribute`."""
    from pypsa.components.types import get as get_component_type

    return frozenset(get_component_type(ctype).defaults.index)


def _connection_rows(c: pypsa.Components) -> pd.DataFrame:
    """One type's connections as `(name, bus, role)` rows, from its port columns.

    Undoes PyPSA's positional encoding: `c.ports` is the authoritative port
    list (`["0", "1"]` plus `additional_ports`), so the port count comes from
    the network rather than a guessed bound. `role` is the row's one
    property; every per-port input, `delay` included, is long rows of
    `inputs/` keyed by the connection.

    Notes
    -----
    - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
    """
    static = c.static
    frames = []
    for port in c.ports:
        column = _port_attribute("bus", port, c.defaults.index)
        if column not in static.columns:
            continue
        attached = static[static[column].astype(str) != ""]
        if attached.empty:
            continue
        rows = attached[[column]].rename(columns={column: "bus"})
        rows = rows.reset_index().rename(columns={"name": "entity"})
        rows["role"] = _port_role(port)
        rows["deleted"] = False
        frames.append(rows)
    if not frames:
        return pd.DataFrame(columns=["entity", "bus", "role", "deleted"])
    return pd.concat(frames, ignore_index=True)


# TODO(pypsa): `_is_output`, `_drop_default_rows` and `_scalar_rows` below port
# helpers that only exist on PyPSA's unreleased data-records branch (https://energy-models.github.io/datarecord/design/tools/).
# Delete the ported copy and call the real one once a PyPSA release carries it.


def _is_output(defaults: pd.DataFrame, attr: str) -> bool:
    """Whether `attr` is an output (custom attrs with no status are inputs).

    Ported from `pypsa.common._is_output` rather than depended on, since only
    a released PyPSA can be relied on here.

    Notes
    -----
    - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
    """
    if attr not in defaults.index:
        return False
    return str(defaults.at[attr, "status"]).startswith("Output")


def _drop_default_rows(rows: pd.DataFrame, default: Any) -> pd.DataFrame:
    """Remove scalar rows that just repeat the attribute's default value.

    Ported from `pypsa.components.array._drop_default_rows`.
    """
    if pd.isnull(default):
        return rows[rows["value"].notna()]
    return rows[rows["value"] != default]


def _scalar_rows(c: pypsa.Components, attr: str, exclude: pd.Index) -> pd.DataFrame:
    """Build null-snapshot long rows from the static scalars of `attr`.

    Ported from `pypsa.components.array.Components._scalar_rows`, with its
    columns in long order (`entity, snapshot, scenario, period, value`) and
    built in one constructor rather than by `reset_index` and column inserts:
    it runs once per attribute and type, where pandas' per-call overhead
    dominated an export.
    """
    static = c.static[attr]
    if len(exclude):
        static = static[~static.index.isin(exclude)]
    index = static.index
    stochastic = isinstance(index, pd.MultiIndex)
    return pd.DataFrame(
        {
            "entity": index.get_level_values("name") if stochastic else index,
            "snapshot": np.nan,
            "scenario": index.get_level_values(SCENARIO) if stochastic else np.nan,
            "period": np.nan,
            "value": static.array,
        }
    )


def _shared_across_scenarios(rows: pd.DataFrame) -> pd.DataFrame:
    """`rows` with an entity's per-scenario repeats of one value folded to a NULL scenario.

    A stochastic network repeats its static frame per scenario; a value the
    same in every scenario is one row broadcasting over `scenario`, which an
    attribute not addressed by it needs, while one differing keeps its rows.

    Notes
    -----
    - [the broadcast rule](https://energy-models.github.io/datarecord/design/record/#the-broadcast-rule)
    """
    if rows["scenario"].isna().all():
        return rows
    shared = rows.groupby("entity")["value"].transform(
        lambda values: values.nunique(dropna=False) == 1
    )
    folded = rows[shared.astype(bool)].drop_duplicates("entity").assign(scenario=None)
    return pd.concat([folded, rows[~shared.astype(bool)]], ignore_index=True)


# -- the tool ---------------------------------------------------------------


class PyPSATool(Tool):
    """Build a `pypsa.Network` from a record and read its results back."""

    name = "pypsa"

    # PyPSA defines the record vocabulary today, so every attribute maps to
    # itself and there is nothing to declare. The seam is here for the first
    # tool whose names differ, or whose value is computed from several of the
    # record's (`Attr.compute`).
    schema = Schema()

    def component_types(self) -> frozenset[str]:
        """The component types PyPSA knows, from its type registry.

        Taken from the component *type registry*, not a network instance:
        `pypsa.Network().components` iterates only the components attached to
        that network, which for an empty one is just the standard types.
        """
        from pypsa.components.types import all_components

        return frozenset(c.name for c in all_components.values())

    def requires(self, record: RecordLike) -> Requirements:
        """PyPSA's axes, the record's own component types, and their required attributes.

        The attribute half is record-dependent: only types the record
        actually defines members for are required, and which of their
        attributes are mandatory comes from PyPSA's registry
        (`defaults["status"] == "Input (required)"`), not a list kept here.
        Reported by source attribute (`Schema.sources`), so a renamed or
        computed one names what the record must actually supply.
        """
        known = self.component_types()
        ctypes = {ct for ct in _entity_types(record) if ct in known}
        return Requirements(
            dims=REQUIRED_DIMS,
            categories=frozenset(ctypes),
            attributes=frozenset(
                (ct, src)
                for ct in ctypes
                for attr in _required_attributes(ct)
                for src in self.schema.sources(ct, attr)
            ),
        )

    def verify(self, record: RecordLike) -> Requirements:
        """What this record fails to supply for a PyPSA build; falsy if it is usable.

        Checks what a build needs: the schema declares PyPSA's axes, its key dims are ones this tool can honour, every component
        type it names is one PyPSA knows, and each type's required attributes
        are resolvable - either owned by some layer (the owner map), a
        property of the entity axis, or carrying a declared default for that type. A
        renamed or computed attribute is checked against its sources
        (`Schema.sources`), which is also how it is reported.

        Row ownership and curves are read per type, from `flags(entity_type=...)`.

        The key checks come first and return early: the owner-map fold keys
        its relations by those dims, so reading the map at all could raise a
        binder error before anything below could report it.

        Notes
        -----
        - [AttributeSpec](https://energy-models.github.io/datarecord/design/schema/#attributespec)
        - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
        """
        return self._verify(record)[0]

    def _verify(
        self, record: RecordLike
    ) -> tuple[Requirements, dict[str, _TypeMembers]]:
        """`verify`, with the members it read for each known type.

        `build` builds from the same reads rather than repeating them: each is
        a fold over the record's layers. Empty where a key check returned early.
        """
        dims = REQUIRED_DIMS - set(record.schema.dims)
        unsupported_keys = self._unsupported_keys(record)
        if unsupported_keys:
            return Requirements(
                dims=frozenset(dims), unsupported_keys=frozenset(unsupported_keys)
            ), {}

        categories: set[str] = set()
        attributes: set[tuple[str, str]] = set()
        unsupported_values: set[tuple[str, str]] = set()

        known = self.component_types()
        declared = record.schema
        read: dict[str, _TypeMembers] = {}
        ctypes = _entity_types(record)
        connection_frame = _connection_frame(record) if known & set(ctypes) else None
        for ctype in ctypes:
            # A type PyPSA has no registry entry for, though the record's own
            # schema declares it. Reported rather than raised: the record layer
            # upholds its schema's vocabulary and knows no framework's, so this
            # reads back fine and it is this tool's business that it cannot be
            # built.
            if ctype not in known:
                categories.add(ctype)
                continue
            specs = declared.attributes_for(ENTITY, **{ENTITY_TYPE: ctype})
            resolved = record.flags(**{ENTITY_TYPE: ctype})
            # A curve, not a scalar (https://energy-models.github.io/datarecord/design/record/#wide-and-long-rows). PyPSA takes a scalar for every
            # attribute this build assigns, so the record is storing something
            # correct that this translation cannot express - reported here
            # rather than silently pivoting one arbitrary breakpoint.
            unsupported_values |= {
                (ctype, attr) for attr, flags in resolved.items() if flags.breakpoints
            }
            read[ctype] = _TypeMembers.of(record, ctype, connection_frame)
            static_cols = read[ctype].columns
            # A port attribute the record supplies as connection rows rather
            # than as a column: `bus0`/`bus1` are satisfied by a connection
            # per port, so the collapse in `build` can name them (https://energy-models.github.io/datarecord/design/record/#connections).
            from_connections = read[ctype].port_attributes(ctype)
            for attr in _required_attributes(ctype):
                for src in self.schema.sources(ctype, attr):
                    if src in resolved or src in static_cols or src in from_connections:
                        continue
                    # A declared default makes the attribute resolvable even
                    # with no row anywhere (the broadcast rule).
                    if (
                        src in specs
                        and declared.default_for(src, **{ENTITY_TYPE: ctype})
                        is not None
                    ):
                        continue
                    attributes.add((ctype, src))
        return Requirements(
            dims=frozenset(dims),
            categories=frozenset(categories),
            attributes=frozenset(attributes),
            unsupported_values=frozenset(unsupported_values),
        ), read

    def _unsupported_keys(self, record: RecordLike) -> set[tuple[str, str]]:
        """`(key, dim)` pairs this tool cannot honour: `snapshot`, as any key.

        PyPSA's static/series split needs a component's whole series to come
        from one layer, so a snapshot-keyed overlay could leave a broadcast row
        and a descendant's per-snapshot row with no single container to land in. A limit of the *representation*, not the format - which is why
        the record layer permits the declaration and this reports it.

        Notes
        -----
        - [partial](https://energy-models.github.io/datarecord/design/schema/#partial-the-granularity-of-an-override)
        - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
        """
        defs = record.schema
        return {("input_key", SNAPSHOT)} if SNAPSHOT in defs.partial_dims else set()

    def build(self, record: RecordLike) -> pypsa.Network:
        """The resolved network, one component type at a time.

        Raises
        ------
        UnsupportedRecordError
            If `verify` reports anything missing - a partial build would
            surface as a confusing PyPSA error several frames later.

        Notes
        -----
        - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
        """
        missing, read = self._verify(record)
        if missing:
            raise UnsupportedRecordError(self.name, missing)

        con = _connection(record)
        schema = record.schema
        shape = NetworkShape(record.dims)
        n = _new_network(record, shape)

        flagged = record.flags()
        for ctype, members in read.items():
            static = members.members
            if static is None:
                continue
            if ctype == _SUB_NETWORK:
                static = _sub_network_unnamed(static, ENTITY)
            if not shape.stochastic and SCENARIO in static.columns:
                static = static.project(star(exclude=[SCENARIO]))
            # `_pos` in member order before any join scrambles it: the member
            # frame arrives in member order (https://energy-models.github.io/datarecord/design/read-path/#one-fold-for-every-axis),
            # and `_assign_static` sorts the wide frame back by it at the end.
            static = static.project("*, row_number() OVER () AS _pos")
            # Connections back to the positional columns PyPSA expects (https://energy-models.github.io/datarecord/design/tools/).
            connections = members.connections
            static = _collapse_connections(static, connections, ctype, con)

            # Frames are built and released per type, so peak memory is one
            # type's wide frames rather than the whole network (https://energy-models.github.io/datarecord/design/tools/).
            attributes = {}
            carried = schema.attributes_for(ENTITY, **{ENTITY_TYPE: ctype})
            for attr, flags in flagged.items():
                if attr not in carried:
                    continue
                # Both sets empty no longer means "no rows": the flags are
                # scoped to what an attribute is addressed by (https://energy-models.github.io/datarecord/design/record/#flags), so an
                # attribute over `entity` alone has no broadcast dim to report
                # and still has values. An attribute with no rows at all is
                # absent from the map entirely, which is what this filtered.
                # Through the schema, so a renamed or computed attribute
                # reaches the pivot below as an ordinary long relation. Not
                # scoped to this type's members here: every consumer joins it
                # on `entity` against them (https://energy-models.github.io/datarecord/design/format/#entity-is-unique-across-types).
                long = _unpack_connection(self.schema.resolve(record, ctype, attr))
                if CONNECTION in carried[attr].dims:
                    for column, rows in _port_columns(
                        long, attr, connections, ctype, con
                    ).items():
                        attributes[column] = (rows, flags)
                else:
                    attributes[attr] = (long, flags)

            _add_component_type(n, ctype, static, attributes, shape, con)

        _broadcast_standard_types(n)
        return n

    def results(self, model: pypsa.Network, con: DuckDBPyConnection) -> Frames:
        """A solved network's result attributes in the record's long form.

        Keyed by attribute, matching `outputs/<attr>.parquet`: every component
        type's rows for one attribute are concatenated into one frame, exactly as
        `attributes` presents `inputs/`. The union needs no
        `entity_type` to tell the arms apart. Which attributes count as
        results comes from PyPSA's registry, so an upgrade that adds one is
        picked up, by the same rule the schema declares `results` by: a per-port
        result (`p0`, `p1`, a Generator's `p`) is one `p` row per connection,
        keyed by its `connection` struct, `Bus.p`/`q` are not written, `Link.p` is `p_internal`, and a
        name PyPSA also registers as an input (`Bus.control`) is none.

        Each frame is a lazy DuckDB relation on `con` over the network's
        containers, melted wide->long by `UNPIVOT`, so nothing is computed until
        collected.

        Rows still at the attribute's default are dropped: a static output like
        `Bus.control` carries its default whether or not the network was solved,
        and an absent output file means exactly "take the default".

        Notes
        -----
        - [the broadcast rule](https://energy-models.github.io/datarecord/design/record/#the-broadcast-rule)
        - [the long schema](https://energy-models.github.io/datarecord/design/format/#the-long-schema)
        - [entity is unique across types](https://energy-models.github.io/datarecord/design/format/#entity-is-unique-across-types)
        - [outputs](https://energy-models.github.io/datarecord/design/read-path/#outputs)
        - [results on connections](https://energy-models.github.io/datarecord/design/tools/#results-on-connections)
        """
        # The same wide->long melt `write_layer` uses, kept lazy. `outputs`
        # keys every registry result; a result absent on this network unions to
        # `None` and is dropped here rather than surfaced, since a reader takes
        # the default for it (the outputs default rule) - no key, no collect.
        source = _NetworkSource(model, con)
        frames = {
            attr: rel
            for attr, ctypes in source._output_names.items()
            if (rel := source._output_rel(attr, ctypes)) is not None
        }
        return {attr: nw.from_native(rel).lazy() for attr, rel in frames.items()}

    def to_datarecord(
        self, model: pypsa.Network, con: DuckDBPyConnection
    ) -> RecordLike:
        """Present a `Network` as the `Record` `write_layer` persists.

        The inverse of `build`, and the only place PyPSA's shape is undone:
        `c.static`/`c.dynamic` become long rows on `con`, and
        `bus0`/`bus1`/`efficiency2` become connection rows carrying a `role`.
        Key sets are read off the network, so listing unpivots nothing and a
        lookup only what is asked for.

        Raises
        ------
        UnsupportedRecordError
            If two component types share a name: PyPSA scopes names per type, a
            record record-wide, and this reports rather than renames. Likewise
            for a static column PyPSA's registry has no entry for on its type
            but declares elsewhere with another shape (`Carrier.efficiency`).

        Notes
        -----
        - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
        - [entity is unique across types](https://energy-models.github.io/datarecord/design/format/#entity-is-unique-across-types)
        - [writing a whole record](https://energy-models.github.io/datarecord/design/writing/)
        - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
        """
        clashing = _colliding_names(model)
        columns = _clashing_columns(model)
        if clashing or columns:
            raise UnsupportedRecordError(
                self.name, Requirements(names=clashing, columns=columns)
            )
        return _NetworkSource(model, con)


def _port_names(c: pypsa.Components) -> dict[str, tuple[str, str]]:
    """Per-port attribute name -> `(stem, port)`, for this type's actual ports."""
    registered = c.defaults.index
    return {
        name: (stem, port)
        for stem in sorted(_per_port_stems())
        for port in c.ports
        if (name := _port_attribute(stem, port, registered)) in registered
    }


def _port_stems(c: pypsa.Components) -> dict[str, str]:
    """Per-port attribute name -> its stem, for this type's actual ports."""
    return {name: stem for name, (stem, _) in _port_names(c).items()}


def _attribute_spec(row: pd.Series, *, per_port: bool) -> AttributeSpec:
    """One `c.defaults` row as the spec a record declares, input or result.

    `entity` is a dim like any other, so an entity attribute declares it, and
    a per-port one names the `connection` group instead, whose rows carry it
    as one `{entity, bus}` struct. A varying attribute varies over time and, in a stochastic
    network, scenario; both are declared always, a network without scenarios
    writing none.

    Notes
    -----
    - [AttributeSpec](https://energy-models.github.io/datarecord/design/schema/#attributespec)
    - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
    """
    dims = {SNAPSHOT, SCENARIO} if row["varying"] else set()
    dims.add(CONNECTION if per_port else ENTITY)
    return AttributeSpec(
        dtype=_DTYPES.get(row["typ"], nw.String()),
        dims=frozenset(dims),
        default=_default(row["default"]),
        unit=_text(row.get("unit")),
        description=_text(row.get("description")),
    )


def _port_spec(
    defaults: pd.DataFrame, stem: str, per_port: Mapping[str, str]
) -> AttributeSpec:
    """A per-port stem's spec, from its first port's row.

    The stem's port rows agree but for the default: a Process's `rate0` is
    `-1` and `rate1` `1`, the input and output ends. One stem-wide default
    would misstate a port, so where they differ none is declared, and `build`
    leaves an uncovered port to PyPSA's own.

    Parameters
    ----------
    defaults
        The type's `c.defaults`.
    per_port
        Per-port attribute name -> its stem, as `_port_stems` returns it.

    Notes
    -----
    - [AttributeSpec](https://energy-models.github.io/datarecord/design/schema/#attributespec)
    - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
    """
    columns = [name for name, of in per_port.items() if of == stem]
    spec = _attribute_spec(defaults.loc[columns[0]], per_port=True)
    if len({_default(defaults.at[name, "default"]) for name in columns}) > 1:
        return spec.model_copy(update={"default": None})
    return spec


def _with_default_by(
    attributes: dict[str, AttributeSpec], by_type: dict[str, dict[str, Any]]
) -> dict[str, AttributeSpec]:
    """`attributes`, each given `default_by` over `entity_type` where a type's default differs.

    Parameters
    ----------
    by_type
        Attribute name -> component type -> that type's registry default.

    Notes
    -----
    - [AttributeSpec](https://energy-models.github.io/datarecord/design/schema/#attributespec)
    """
    widened = dict(attributes)
    for name, defaults_of in by_type.items():
        spec = attributes[name]
        differing = {
            ct: v for ct, v in defaults_of.items() if not _same(v, spec.default)
        }
        if differing:
            widened[name] = spec.model_copy(
                update={"default_by": {ENTITY_TYPE: differing}}
            )
    return widened


@cache
def _registry_schema() -> RecordSchema:
    """The record schema PyPSA's whole component registry declares.

    Every network exports against this one schema: its dims, groups, attributes,
    results and traits describe every PyPSA component type and attribute, not
    only the ones a given network holds. Declaring a type or attribute a network
    lacks writes no file and is rejected by nothing - the enum only rejects an
    *unknown* type - so a network-independent schema is both correct and the
    stabler contract (two networks with different component sets no longer
    produce mutually incompatible schemas). Derived once, cached: the registry
    does not change within a process.

    `c.defaults` already declares what an `AttributeSpec` asks for, so this reads
    it rather than restating it. Results go to `results` rather than
    `attributes`, read off the same registry (`status` starting "Output"), so a
    PyPSA upgrade adding one is picked up rather than needing a list kept here;
    which names they are is `_result_attributes`, the rule `PyPSA.results`
    keys its frames by, a per-port one declared over the `connection` group
    like a per-port input. They carry no trait, a trait being the input
    vocabulary a type is validated and split against, which a result is not.

    One trait per type, narrowing every attribute to the types declaring it -
    the faithful translation of a per-type registry shipping no trait
    vocabulary of its own. One spec per name record-wide: the first type
    declaring a name gives its spec, and a default differing per type is
    `default_by` (`_with_default_by`). A per-port column collapses to its stem
    (`_port_spec`), and a port's bus is the `connection` tuple itself.

    The properties of `entity` are `entity_type`, an `Enum` over the
    registry's types so a type outside it is refused on write, and
    `ENTITY_PROPERTIES`; `role` is a property of `connection`. Every other
    input, `scenario_weight` over `scenario` included, is an attribute.

    Notes
    -----
    - [where a value lives](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
    - [the schema](https://energy-models.github.io/datarecord/design/schema/)
    - [AttributeSpec](https://energy-models.github.io/datarecord/design/schema/#attributespec)
    - [outputs](https://energy-models.github.io/datarecord/design/read-path/#outputs)
    - [results on connections](https://energy-models.github.io/datarecord/design/tools/#results-on-connections)
    """
    import pypsa

    n = pypsa.Network()
    attributes: dict[str, AttributeSpec] = {
        SCENARIO_WEIGHT: AttributeSpec(
            dtype=nw.Float64(),
            dims=frozenset({SCENARIO}),
            description="How much this scenario counts in the expectation.",
        ),
    }
    carries: dict[str, frozenset[str]] = {}
    by_type: dict[str, dict[str, Any]] = {}
    ctypes = sorted(n.all_components - n.standard_type_components)
    for ctype in ctypes:
        c = n.components[ctype]
        defaults = c.defaults
        per_port = _port_stems(c)
        is_output = _output_attributes(c)
        carried: set[str] = set()
        for attr in defaults.index:
            if attr == "name" or attr in is_output:
                continue
            stem = per_port.get(attr, attr)
            if stem in carried or stem == BUS:
                continue
            carried.add(stem)
            if attr not in per_port:
                by_type.setdefault(stem, {})[c.name] = _default(
                    defaults.at[attr, "default"]
                )
            attributes.setdefault(
                stem,
                _port_spec(defaults, stem, per_port)
                if attr in per_port
                else _attribute_spec(defaults.loc[attr], per_port=False),
            )
        if carried:
            carries[c.name] = frozenset(carried)
    attributes = _with_default_by(attributes, by_type)
    properties = {
        name: PropertySpec(**attributes.pop(name).model_dump(exclude={"dims"}))
        for name in ENTITY_PROPERTIES
    }
    results: dict[str, AttributeSpec] = {}
    for ctype in ctypes:
        c = n.components[ctype]
        per_port = _port_stems(c)
        for attr, name in sorted(
            _result_attributes(c, {*attributes, *properties}).items()
        ):
            results.setdefault(
                name, _attribute_spec(c.defaults.loc[attr], per_port=attr in per_port)
            )
    traits = {
        ctype: Trait(attributes=carried, on={ENTITY_TYPE: frozenset({ctype})})
        for ctype, carried in carries.items()
    }
    return RecordSchema(
        dimensions={
            SNAPSHOT: Dimension(
                dtype=nw.Datetime(),
                description="A point in the operational time series.",
            ),
            PERIOD: Dimension(
                dtype=nw.Int64(),
                unit="year",
                description="An investment period, labelled by its year.",
            ),
            SCENARIO: Dimension(
                dtype=nw.String(),
                description="One realisation of a stochastic problem.",
            ),
            ENTITY: Dimension(dtype=nw.String(), description="An entity."),
            BUS: Dimension(dtype=nw.String(), description="A node of the network."),
        },
        properties={
            ENTITY: {
                ENTITY_TYPE: PropertySpec(
                    dtype=nw.Enum(ctypes),
                    description="What kind of entity an entity is.",
                ),
                **properties,
            },
            CONNECTION: {
                ROLE: PropertySpec(
                    dtype=nw.Enum(_ROLES),
                    description="Which end of the component this attachment is.",
                )
            },
        },
        groups={
            CONNECTION: Group(
                over={"entity": ENTITY, "bus": BUS},
                description="An entity's attachment to one bus.",
            ),
        },
        attributes=attributes,
        results=results,
        traits=traits,
        partial=frozenset({ENTITY, SCENARIO, CONNECTION}),
    )


@cache
def _input_names() -> frozenset[str]:
    """Every input the registry schema declares, attribute or property of `entity`."""
    schema = _registry_schema()
    return frozenset(schema.attributes) | frozenset(schema.properties[ENTITY])


@dataclass(frozen=True)
class _NetworkSource:
    """A `pypsa.Network` presented as a `Record`.

    Every `LazyFrames` here is built from key sets read off the network and
    its registry, so nothing is unpivoted until a key is looked up.

    Notes
    -----
    - [the record format](https://energy-models.github.io/datarecord/design/format/)
    """

    n: pypsa.Network
    #: The connection the wide->long melt runs on.
    con: DuckDBPyConnection

    # The dims a PyPSA network has axes for; `Coords` stays generic, this tool
    # decides these three are what a network is shaped by (https://energy-models.github.io/datarecord/design/tools/).
    _DIMS = (SNAPSHOT, PERIOD, SCENARIO)

    @property
    def schema(self) -> RecordSchema:
        """The layer's schema: the registry-derived schema, widened to this network.

        The dims, groups, results and the registry's attributes are the same for
        every network - `_registry_schema` derives them once from PyPSA's whole
        component registry. What varies is `meta`, which carries this network's
        own attributes and `n.meta` for read-back, and its custom static columns
        (`_custom_columns`), each declared over `entity` and added to the trait
        of the type carrying it.

        Notes
        -----
        - [the schema](https://energy-models.github.io/datarecord/design/schema/)
        - [traits](https://energy-models.github.io/datarecord/design/schema/#traits)
        """
        base = _registry_schema()
        attributes = dict(base.attributes)
        traits = dict(base.traits)
        for ctype, columns in _custom_columns(self.n).items():
            for name, dtype in columns.items():
                attributes.setdefault(
                    name, AttributeSpec(dtype=dtype, dims=frozenset({ENTITY}))
                )
            trait = traits.get(ctype, Trait(on={ENTITY_TYPE: frozenset({ctype})}))
            traits[ctype] = trait.model_copy(
                update={"attributes": trait.attributes | frozenset(columns)}
            )
        return RecordSchema(
            **{
                **dict(base),
                "attributes": attributes,
                "traits": traits,
                "meta": {
                    "format": "pypsa-parquet",
                    "attributes": _collect_network_attributes(self.n),
                    "meta": dict(self.n.meta),
                },
            }
        )

    @property
    def dims(self) -> LazyFrames:
        """Every axis this network holds, `entity` among them, as keys.

        `entity` carries its tombstone column beside the key; its properties
        are in `properties`.

        Notes
        -----
        - [where a value lives](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
        """
        axes = {
            SNAPSHOT: lambda: self.n.snapshots.to_frame(index=False),
            PERIOD: lambda: self.n.investment_periods.to_frame(index=False),
            SCENARIO: lambda: self.n.scenario_weightings.index.to_frame(index=False),
        }
        present = tuple(d for d in self._DIMS if len(axes[d]()) > 0)
        axes[ENTITY] = lambda: self._entity_frame()[[ENTITY, "deleted"]]
        return LazyFrames(
            (*present, ENTITY), lambda dim: nw.from_native(axes[dim]()).lazy()
        )

    def _entity_frame(self) -> pd.DataFrame:
        """Every exported type's members and their properties.

        One row per entity, typed by the `entity_type` column; a property
        one type lacks is NULL on that type's rows.

        Notes
        -----
        - [entity is unique across types](https://energy-models.github.io/datarecord/design/format/#entity-is-unique-across-types)
        - [where a value lives](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
        """
        frames = [
            self._static_frame(c.name).assign(**{ENTITY_TYPE: c.name})
            for c in self.n.components
            if _exported(c)
        ]
        if not frames:
            return pd.DataFrame(columns=[ENTITY, ENTITY_TYPE, "deleted"])
        merged = pd.concat(frames, ignore_index=True)
        lead = [ENTITY, ENTITY_TYPE, "deleted"]
        return merged[[*lead, *(c for c in merged.columns if c not in lead)]]

    @property
    def groups(self) -> LazyFrames:
        """The `connection` group, one frame across every type.

        Every type with any port, single-attachment ones included: a
        Generator's one `bus` is as much a connection as a Link's `bus0`,
        and `c.ports == [""]` makes `_port_attribute` name it correctly.

        The entity-type group is not here, its rows being the entity axis's -
        `dims["entity"]`, which this record supplies like any other axis.

        Notes
        -----
        - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
        """
        return LazyFrames((CONNECTION,), lambda _: self._connection_frame())

    def _connection_frame(self) -> nw.LazyFrame:
        """Every type's connections in one frame, `(connection, role, deleted)`.

        Notes
        -----
        - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
        """
        types = [c.name for c in self.n.components if _exported(c) and c.ports]
        frames = [_connection_rows(self.n.c[ctype]) for ctype in types]
        rows = (
            pd.concat(frames, ignore_index=True)
            if frames
            else pd.DataFrame(columns=["entity", "bus", "role"])
        )
        # A stochastic network repeats its connections per scenario, which
        # collapse to one row: an attachment exists or it does not, so nothing
        # scopes it per value of an axis (`_tagged` says the same of members).
        if SCENARIO in rows.columns:
            rows = rows.drop(columns=[SCENARIO]).drop_duplicates(
                subset=["entity", "bus"]
            )
        flat = self.con.sql("FROM rows")
        return nw.from_native(
            flat.project(
                _connection_struct(flat, col(ENTITY), col(BUS)),
                star(exclude=[ENTITY, BUS]),
            )
        ).lazy()

    def _as_long_rel(
        self, c: pypsa.Components, attr: str, *, drop_defaults: bool = False
    ) -> DuckDBPyRelation | None:
        """`attr` as a long relation `(entity, snapshot, scenario, period, value)`.

        `None` where the attribute contributes no rows on this network, so a
        caller unions only the types that do rather than empty relations.

        The wide `snapshots x entities` (or
        `snapshots x (scenario, entity)`) dynamic frame is melted by `UNPIVOT`
        rather than `pandas.stack`, so the relation stays a lazy plan
        `write_layer` writes without a copy. Static scalars land as null-snapshot
        rows exactly as `_scalar_rows` builds them; `drop_defaults` omits a scalar
        that only repeats the attribute's default.

        Parameters
        ----------
        drop_defaults
            Omit static scalar rows whose value equals the attribute's default.

        Notes
        -----
        - [wide and long rows](https://energy-models.github.io/datarecord/design/record/#wide-and-long-rows)
        - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
        """
        con = self.con
        varying = attr in c.dynamic or (
            attr in c.defaults.index and bool(c.defaults.at[attr, "varying"])
        )
        if (
            not varying
            and not _is_output(c.defaults, attr)
            and attr not in c.static.columns
        ):
            msg = f"'{attr}' of '{c.name}' components has no long representation."
            raise AttributeError(msg)

        parts: list[DuckDBPyRelation] = []
        excluded: pd.Index = pd.Index([])
        if varying:
            melted = self._melt_dynamic(con, c, attr)
            if melted is not None:
                parts.append(melted)
            excluded = c.dynamic[attr].columns
        static_backed = attr in c.defaults.index and bool(c.defaults.at[attr, "static"])
        if not varying or static_backed:
            scalars = self._scalar_rel(
                con, c, attr, excluded, drop_defaults=drop_defaults
            )
            if scalars is not None:
                parts.append(scalars)
        if not parts:
            return None
        rel = parts[0]
        for other in parts[1:]:
            rel = rel.union(other)
        return rel

    def _melt_dynamic(
        self, con: DuckDBPyConnection, c: pypsa.Components, attr: str
    ) -> DuckDBPyRelation | None:
        """Melt one varying attribute's wide dynamic frame to long rows.

        `None` where the frame has no entity columns - a degenerate
        `UNPIVOT ... IN ()` and an empty relation the caller would only union
        away.

        The melted columns are named by position and aliased back to their
        names as string literals, so a name never becomes an SQL identifier:
        a quote in it would end the identifier, a name equal to an id column
        would duplicate it, and DuckDB folds identifiers' case.
        """
        wide = c.dynamic[attr]
        stochastic = isinstance(wide.columns, pd.MultiIndex)
        multi_snapshot = isinstance(c.snapshots, pd.MultiIndex)
        idcols = ["period", "snapshot"] if multi_snapshot else ["snapshot"]
        # One flat value column per melted column: `scenario\x1fentity` where a
        # scenario level exists, split back out after the UNPIVOT. `reset_index`
        # returns a fresh frame, so relabelling its columns never mutates the
        # dynamic frame PyPSA owns - no defensive copy needed.
        valcols = (
            [f"{s}\x1f{e}" for s, e in wide.columns]
            if stochastic
            else list(wide.columns)
        )
        if not valcols:
            return None
        positional = [f"v{i}" for i in range(len(valcols))]
        w = wide.set_axis(positional, axis=1).reset_index()
        w.columns = [*idcols, *positional]
        # `from_df` captures the frame into the relation's own plan, so a later
        # call reusing the frame variable cannot rebind this one (unlike a named
        # registered view).
        wide_rel = con.from_df(w)  # noqa: F841 - bound by name for the query below
        inlist = ", ".join(
            f"{p} AS {lit(str(name))}"
            for p, name in zip(positional, valcols, strict=True)
        )
        idsel = ", ".join(idcols)
        # Two steps rather than one nested query: the local-relation replacement
        # scan does not compose through a subquery, so melt first, then project.
        melted = con.sql(  # noqa: F841 - bound by name for the query below
            f"SELECT {idsel}, colname, value FROM wide_rel "
            f"UNPIVOT INCLUDE NULLS (value FOR colname IN ({inlist}))"
        )
        if stochastic:
            entity = "split_part(colname, chr(31), 2)"
            scenario = "split_part(colname, chr(31), 1)"
        else:
            entity, scenario = "colname", "CAST(NULL AS VARCHAR)"
        period = "period" if multi_snapshot else "CAST(NULL AS BIGINT)"
        return con.sql(
            f"SELECT {entity} AS entity, snapshot, {scenario} AS scenario, "
            f"{period} AS period, value FROM melted"
        )

    def _scalar_rel(
        self,
        con: DuckDBPyConnection,
        c: pypsa.Components,
        attr: str,
        exclude: pd.Index,
        *,
        drop_defaults: bool = False,
    ) -> DuckDBPyRelation | None:
        """Null-snapshot long rows from `attr`'s static scalars (`_scalar_rows`).

        `None` where no scalar rows remain - every entity excluded, an empty
        static frame, or (with `drop_defaults`) every scalar at its default - a
        relation the caller would only union away. The default drop happens here
        in pandas, where the emptiness is decidable without executing a relation.

        The reshape stays in pandas: it is one `reset_index` on a Series, cheaper
        than selecting a single column out of a wide registered relation per
        attribute (measured), and the frame lands in DuckDB the same way the melt
        does.
        """
        static = _shared_across_scenarios(_scalar_rows(c, attr, exclude))
        if drop_defaults and attr in c.defaults.index:
            static = _drop_default_rows(static, c.defaults.at[attr, "default"])
        if static.empty:
            return None
        return con.sql("SELECT * FROM static")

    @property
    def attributes(self) -> LazyFrames:
        """Every input that is no property, `scenario_weight` among them where scenarios exist."""
        names = self._attribute_names
        return LazyFrames(
            tuple(names), lambda attr: self._long_frame(attr, names[attr])
        )

    @cached_property
    def _attribute_names(self) -> dict[str, list[str]]:
        """Input attribute -> the exported types carrying it.

        Read once per source: `write_layer` asks for `attributes` once per key,
        and recomputing it walks every type's registry each time. The source is
        a view taken for one write, so the network does not change under it.
        """
        names: dict[str, list[str]] = {}
        for c in self.n.components:
            if not _exported(c):
                continue
            for attr in self._record_attributes(c):
                names.setdefault(attr, []).append(c.name)
        if len(self.n.scenario_weightings):
            names[SCENARIO_WEIGHT] = []
        return names

    def _scenario_weight_frame(self) -> nw.LazyFrame:
        """The scenario weightings as long rows of `scenario_weight`."""
        weights = (  # noqa: F841 - bound by name for the query below
            self.n.scenario_weightings["weight"]
            .rename("value")
            .rename_axis(SCENARIO)
            .reset_index()
        )
        rel = self.con.sql(
            f"SELECT CAST({SCENARIO} AS VARCHAR) AS {SCENARIO}, "
            f"{lit(SCENARIO_WEIGHT)} AS attribute, NULL AS breakpoint, "
            "CAST(value AS DOUBLE) AS value FROM weights"
        )
        return nw.from_native(rel).lazy()

    @property
    def outputs(self) -> LazyFrames:
        """Result attributes, keyed by name, from PyPSA's own registry.

        Keys are named per type by the registry and merged, matching the file
        layout - one `outputs/<attr>.parquet` across types, like `inputs/`.
        A network that was never solved still names them; the frame is then
        empty and `write_layer` writes an empty file rather than none, which
        reads back as "take the default" either way.

        Notes
        -----
        - [the broadcast rule](https://energy-models.github.io/datarecord/design/record/#the-broadcast-rule)
        - [outputs](https://energy-models.github.io/datarecord/design/read-path/#outputs)
        """
        names = self._output_names
        return LazyFrames(
            tuple(names), lambda attr: self._output_frame(attr, names[attr])
        )

    @cached_property
    def _output_names(self) -> dict[str, list[str]]:
        """Result attribute -> the exported types declaring it, as the schema does."""
        names: dict[str, list[str]] = {}
        for ctype, results in self._results.items():
            for attr in sorted(set(results.values())):
                names.setdefault(attr, []).append(ctype)
        return names

    @cached_property
    def _results(self) -> dict[str, dict[str, str]]:
        """Exported type -> its `_result_attributes`, read once per source.

        Every result's frame needs its types' mapping, and deriving it reads
        the type's whole registry.
        """
        inputs = _input_names()
        return {
            c.name: _result_attributes(c, inputs)
            for c in self.n.components
            if _exported(c)
        }

    @property
    def properties(self) -> LazyFrames:
        """The entities' and the connections' keys and property columns."""
        frames = {
            ENTITY: lambda: nw.from_native(self._entity_frame()).lazy(),
            CONNECTION: self._connection_frame,
        }

        def frame(subject: str) -> nw.LazyFrame:
            lazy = frames[subject]()
            declared = {subject, *_registry_schema().properties[subject]}
            return lazy.select(c for c in lazy.collect_schema() if c in declared)

        return LazyFrames(tuple(frames), frame)

    def flags(self, **categories: str | Sequence[str]) -> dict[str, Flags]:
        """Never consulted: `write_layer` persists frames, not flags.

        A network-backed source exists to be written, and the write path reads
        only the frame mappings. Answering properly is easy - `c.static` and
        `c.dynamic` are PyPSA's own split on the snapshot axis, so it needs no
        scan - but an implementation no caller reaches is one no test pins, so
        the honest answer is the empty one.

        Notes
        -----
        - [writing a whole record](https://energy-models.github.io/datarecord/design/writing/)
        """
        return {}

    # -- key sets -----------------------------------------------------------

    def _record_attributes(self, c: pypsa.Components) -> list[str]:
        """`c`'s input attributes, in the record's vocabulary: every input but a property.

        Each goes to `inputs/` whatever it varies over. Per-port attributes
        collapse to their stem (`efficiency2` -> `efficiency`), a record keying
        them by bus rather than position; `bus` is the connection itself, and
        outputs belong to `outputs/`. A custom column the registry has no
        entry for (`ac_dc_meshed`'s `Bus.country`) is an attribute too.

        Notes
        -----
        - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
        - [where a value lives](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
        - [outputs](https://energy-models.github.io/datarecord/design/read-path/#outputs)
        """
        defaults = c.defaults
        skipped = {"name", *_output_attributes(c), *ENTITY_PROPERTIES}
        per_port = self._port_stems(c)
        custom = [x for x in c.static.columns if x not in defaults.index]
        stems: list[str] = []
        for attr in [*defaults.index, *custom]:
            if attr in skipped:
                continue
            if attr in defaults.index and not (
                defaults.at[attr, "varying"] or attr in c.static.columns
            ):
                continue
            stem = per_port.get(attr, attr)
            if stem != BUS and stem not in stems:
                stems.append(stem)
        return stems

    def _port_stems(self, c: pypsa.Components) -> dict[str, str]:
        """Per-port attribute name -> its stem, for this type's actual ports."""
        return _port_stems(c)

    # -- frames -------------------------------------------------------------

    def _static_frame(self, ctype: str) -> pd.DataFrame:
        """Members of one type with the properties of `entity` it has columns for.

        Notes
        -----
        - [the Record protocol](https://energy-models.github.io/datarecord/design/record/)
        """
        c = self.n.c[ctype]
        columns = [p for p in ENTITY_PROPERTIES if p in c.static.columns]
        frame = c.static[columns].reset_index().rename(columns={"name": "entity"})
        frame["entity"] = [_record_name(ctype, str(x)) for x in frame["entity"]]
        return self._tagged(frame)

    @staticmethod
    def _tagged(frame: pd.DataFrame) -> pd.DataFrame:
        """A `dims/` frame with the tombstone column the fold scopes by.

        No `scenario`: an entity exists or it does not, so nothing scopes
        membership per value of an axis. A stochastic network repeats its
        static frame per scenario, which is a *value* being per-scenario
        rather than the component - so the repeats collapse to one row here
        rather than reaching the record as duplicate entities.

        Notes
        -----
        - [deletion](https://energy-models.github.io/datarecord/design/layers/#deletion)
        - [the record format](https://energy-models.github.io/datarecord/design/format/)
        """
        if SCENARIO in frame.columns:
            frame = frame.drop(columns=[SCENARIO]).drop_duplicates(subset=["entity"])
        if "deleted" not in frame.columns:
            frame["deleted"] = False
        return frame

    def _tagged_long_rel(
        self,
        c: pypsa.Components,
        attribute: str,
        source_attr: str,
        *,
        drop_defaults: bool,
    ) -> DuckDBPyRelation | None:
        """`source_attr`'s long relation, tagged with `attribute` and a NULL breakpoint.

        `attribute` is the record-facing name and `source_attr` PyPSA's - the two
        differ for a per-port attribute, whose ports (`p0`, `p1`, ...) each
        contribute under the one stem, and for a renamed result (`p_internal`).
        A NULL `breakpoint` marks the value a scalar (https://energy-models.github.io/datarecord/design/format/#the-long-schema).
        `None` where `source_attr` contributes no rows.
        """
        rel = self._as_long_rel(c, source_attr, drop_defaults=drop_defaults)
        if rel is None:
            return None
        return rel.select(
            star(),
            lit(attribute).alias("attribute"),
            lit(None).alias("breakpoint"),
        )

    def _long_frame(self, attribute: str, ctypes: list[str]) -> nw.LazyFrame:
        """One attribute's long rows, across every type that has it.

        A per-connection attribute contributes rows carrying the `connection`
        struct each port is, in place of `entity`; a component-level one carries
        `entity` alone. The rows are a DuckDB relation melted by `_as_long_rel`, so the
        frame stays a lazy plan `write_layer` writes without a copy.

        Notes
        -----
        - [the Record protocol](https://energy-models.github.io/datarecord/design/record/)
        - [wide and long rows](https://energy-models.github.io/datarecord/design/record/#wide-and-long-rows)
        """
        # This attribute's own columns, from its spec: one file is one attribute,
        # so it hands over no dim it is not addressed by (https://energy-models.github.io/datarecord/design/format/#the-long-schema).
        if attribute == SCENARIO_WEIGHT:
            return self._scenario_weight_frame()
        registry = _registry_schema()
        columns = list(
            registry.long_columns_for(attribute)
            if registry.spec_for(attribute)
            else (ENTITY, *LONG_TAIL)
        )
        rels = []
        for ctype in ctypes:
            c = self.n.c[ctype]
            if attribute in self._port_stems(c).values():
                rels.extend(self._per_port_long_rels(c, attribute))
            elif attribute in c.defaults.index or attribute in c.static.columns:
                rel = self._tagged_long_rel(c, attribute, attribute, drop_defaults=True)
                if rel is not None:
                    rels.append(rel)
        return self._union_select(rels, columns)

    def _per_port_long_rels(
        self, c: pypsa.Components, stem: str
    ) -> list[DuckDBPyRelation]:
        """A per-connection attribute's long relations, one per port.

        The inverse of the positional collapse: `efficiency`/`efficiency2` become
        one attribute whose rows carry the connection each port is.

        Notes
        -----
        - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
        """
        rels = []
        for column, (of, port) in _port_names(c).items():
            if of != stem:
                continue
            rel = self._port_long_rel(c, stem, column, port, drop_defaults=False)
            if rel is not None:
                rels.append(rel)
        return rels

    def _port_long_rel(
        self,
        c: pypsa.Components,
        attribute: str,
        column: str,
        port: str,
        *,
        drop_defaults: bool,
    ) -> DuckDBPyRelation | None:
        """`column`'s long relation at `port`, tagged `attribute`, keyed by connection.

        The `connection` struct packs the entity with the bus joined from the
        port's static bus column rather than mapped in pandas, so the rows stay a
        relation. `None` where the port has no bus column or `column`
        contributes no rows.

        Notes
        -----
        - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
        """
        con = self.con
        static = c.static
        bus_column = _port_attribute(BUS, port, c.defaults.index)
        if bus_column not in static.columns:
            return None
        # `static` is `(scenario, name)`-indexed on a stochastic network; a
        # component's bus does not vary by scenario, so the name level
        # deduplicates to one bus per component.
        buses = static[bus_column]
        if isinstance(buses.index, pd.MultiIndex):
            buses = buses.droplevel(SCENARIO)
            buses = buses[~buses.index.duplicated()]
        buses = buses[buses.astype(str) != ""]
        bus_df = buses.rename("bus").rename_axis("entity").reset_index()  # noqa: F841
        bus_rel = con.sql(  # noqa: F841 - bound by name for the join below
            "SELECT CAST(entity AS VARCHAR) entity, bus FROM bus_df"
        )
        v = self._tagged_long_rel(c, attribute, column, drop_defaults=drop_defaults)
        if v is None:
            return None
        return (
            v.set_alias("v")
            .join(bus_rel.set_alias("b"), col("v", ENTITY) == col("b", ENTITY))
            .project(
                *(col("v", name) for name in v.columns if name != ENTITY),
                _connection_struct(v, col("v", ENTITY), col("b", BUS)),
            )
        )

    def _output_frame(self, attribute: str, ctypes: list[str]) -> nw.LazyFrame:
        """One result attribute's long rows, across every type that has it.

        `drop_defaults` matters here as it does in `results`: a static output
        carries its default whether or not the network was solved, and an
        absent value means exactly "take the default" to a reader.

        Notes
        -----
        - [outputs](https://energy-models.github.io/datarecord/design/read-path/#outputs)
        """
        rels = self._output_rels(attribute, ctypes)
        return self._union_select(rels, self._output_columns(attribute))

    def _output_rel(self, attribute: str, ctypes: list[str]) -> DuckDBPyRelation | None:
        """`_output_frame` as a relation, `None` where no type contributes."""
        rels = self._output_rels(attribute, ctypes)
        return self._union_rel(rels, self._output_columns(attribute))

    def _output_columns(self, attribute: str) -> list[str]:
        """A result's long columns: `connection` where it is over that group.

        Every network axis whether or not the result varies over it, as the
        melt produces them.

        Notes
        -----
        - [results on connections](https://energy-models.github.io/datarecord/design/tools/#results-on-connections)
        """
        spec = _registry_schema().results[attribute]
        member = CONNECTION if CONNECTION in spec.dims else ENTITY
        return [member, *self._DIMS, "attribute", "breakpoint", "value"]

    def _output_rels(self, attribute: str, ctypes: list[str]) -> list[DuckDBPyRelation]:
        """One result attribute's per-type long relations, empties dropped.

        Each type contributes the PyPSA outputs `_result_attributes` lands in
        `attribute`: every port's `p0`, `p1`, ... under `p` with its bus, or a
        single entity-level one, possibly renamed (`Link.p` as `p_internal`).
        """
        rels = []
        for ctype in ctypes:
            c = self.n.c[ctype]
            ports = _port_names(c)
            for column, name in sorted(self._results[ctype].items()):
                if name != attribute:
                    continue
                try:
                    rel = (
                        self._port_long_rel(
                            c, name, column, ports[column][1], drop_defaults=True
                        )
                        if column in ports
                        else self._tagged_long_rel(c, name, column, drop_defaults=True)
                    )
                except (AttributeError, KeyError):
                    # Not every registry output has a container on every network.
                    continue
                if rel is None:
                    continue
                if ctype == _SUB_NETWORK:
                    rel = _sub_network_named(rel, ENTITY)
                if column == "sub_network":
                    rel = _sub_network_named(rel, "value")
                rels.append(rel)
        return rels

    def _union_rel(
        self, rels: list[DuckDBPyRelation], columns: list[str]
    ) -> DuckDBPyRelation | None:
        """Union `rels` and project `columns`; `None` where none contribute."""
        if not rels:
            return None
        rel = rels[0]
        for other in rels[1:]:
            rel = rel.union(other)
        return rel.select(*(col(name) for name in columns))

    def _union_select(
        self, rels: list[DuckDBPyRelation], columns: list[str]
    ) -> nw.LazyFrame:
        """Union `rels`, project `columns`, as a lazy narwhals frame.

        An empty list is an empty relation with the right columns, each of its
        declared type: `write_layer` checks a group column is a struct before it
        casts.
        """
        rel = self._union_rel(rels, columns)
        if rel is None:
            schema = _registry_schema()
            rel = DuckTypes(self.con).empty_relation(
                **{c: schema.column_type(c) or nw.String() for c in columns}
            )
        return nw.from_native(rel).lazy()


def _required_attributes(ctype: str) -> frozenset[str]:
    """`ctype`'s mandatory input attributes, from PyPSA's registry.

    `name` is the component's identity, always supplied by the record's member
    list rather than an attribute row, so it never counts as missing.
    """
    from pypsa.components.types import get as get_component_type

    defaults = get_component_type(ctype).defaults
    required = defaults.index[defaults["status"].astype(str) == "Input (required)"]
    return frozenset(required) - {"name"}


def _connection_frame(record: RecordLike) -> pd.DataFrame | None:
    """Every type's connections as flat `(entity, bus, ...)` rows, read once.

    `_ordered_connections` scopes it per type, so the group is not folded again
    for each.
    """
    frame = record.groups.get(CONNECTION)
    if frame is None:
        return None
    return _unpack_connection(to_relation(frame)).df()


def _ordered_connections(
    frame: pd.DataFrame | None, members: DuckDBPyRelation | None
) -> pd.DataFrame | None:
    """One type's connections with a port index assigned per component.

    The positional collapse: connections come in member order (an
    overlay's `order_key`: first-introduced) and are numbered within each
    component, so a port index follows the order connections were introduced
    and a patch that adds one appends rather than renumbering. Inputs are
    placed before outputs, so `bus0` is the input end PyPSA's sign convention
    expects.

    Scoped to one type by its `members`, `frame` (`_connection_frame`) holding
    every type's connections.

    Notes
    -----
    - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
    - [one record over one fold](https://energy-models.github.io/datarecord/design/read-path/#one-record-over-one-fold)
    - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
    """
    if frame is None or members is None:
        return None
    df = frame
    mine = {entity for (entity,) in members.project(col(ENTITY)).fetchall()}
    df = df[df["entity"].isin(mine)]
    if df.empty:
        return None
    # Per component: ports are numbered within the entity they belong to.
    within = ["entity"]
    if "role" in df.columns:
        df = df.assign(_role_rank=(df["role"] != _INPUT_PORT).astype(int)).sort_values(
            [*within, "_role_rank"], kind="stable"
        )
    # A single-attachment component keeps PyPSA's unsuffixed `bus`, so its port
    # is the empty index rather than `0` (`_port_attribute`).
    # `dropna=False`: a dim left NULL means "every value of it" (https://energy-models.github.io/datarecord/design/record/#the-broadcast-rule), which
    # is an ordinary group here, not a row to drop.
    grouped = df.groupby(within, dropna=False)
    single = grouped["bus"].transform("size").eq(1) & df["role"].eq(_SINGLE_PORT)
    df["port"] = grouped.cumcount().astype(str).where(~single, "")
    return df


@dataclass(frozen=True)
class _TypeMembers:
    """One type's members and numbered connections, as `verify` and `build` read them.

    Read once per type and shared by the two: each read is a fold over the
    record's layers.
    """

    #: `_members`: the static frame PyPSA's `n.<type>` starts from.
    members: DuckDBPyRelation | None
    #: `_ordered_connections`: the type's connections with their port index.
    connections: pd.DataFrame | None

    @classmethod
    def of(
        cls, record: RecordLike, ctype: str, connections: pd.DataFrame | None
    ) -> _TypeMembers:
        """`ctype`'s reads, scoping `connections` (`_connection_frame`) to it."""
        members = _members(record, ctype)
        return cls(members, _ordered_connections(connections, members))

    @property
    def columns(self) -> frozenset[str]:
        """The properties the members carry, defaults applied.

        A required input among them needs no `inputs/` row to be resolvable.

        Notes
        -----
        - [where a value lives](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
        """
        return (
            frozenset(self.members.columns) if self.members is not None else frozenset()
        )

    def port_attributes(self, ctype: str) -> frozenset[str]:
        """Port attribute names the connection rows can supply.

        `bus0`/`bus1`/... for the ports that actually exist, so `verify` knows a
        required `bus0` is satisfied by a connection rather than by a column.

        Notes
        -----
        - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
        """
        if self.connections is None:
            return frozenset()
        registered = _registered(ctype)
        return frozenset(
            _port_attribute("bus", port, registered)
            for port in self.connections["port"].unique()
        )


def _collapse_connections(
    static: DuckDBPyRelation,
    connections: pd.DataFrame | None,
    ctype: str,
    con: DuckDBPyConnection,
) -> DuckDBPyRelation:
    """Add `bus0`/`bus1`/... columns to a static frame from its connection rows.

    PyPSA wants a column per port; the record stores a row per connection. This is the seam between them, and the only direction that needs
    positions at all.

    Parameters
    ----------
    connections
        `ctype`'s connections as `_ordered_connections` numbers them, which
        `_port_columns` places per-connection values by.

    Notes
    -----
    - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
    """
    if connections is None:
        return static
    # Pivoted on the same key the ports were numbered within, so each
    # (component, scenario, ...) keeps its own port columns.
    index = ["entity"]
    # A dim left NULL means "every value of it" (https://energy-models.github.io/datarecord/design/record/#the-broadcast-rule), so it is a real key
    # here - but `pivot` drops NaN index levels, so such a dim is folded away
    # instead: every row shares its value, and the join below matches on the
    # dims that actually distinguish rows.
    varying = [d for d in index[1:] if connections[d].notna().any()]
    registered = _registered(ctype)
    stems = [BUS, *(s for s in sorted(_per_port_stems() - {BUS}) if s in connections)]
    pieces = []
    for stem in stems:
        piece = connections.pivot(
            index=["entity", *varying], columns="port", values=stem
        )
        piece = piece[[p for p in piece if _carries(stem, p, registered)]]
        piece.columns = [_port_attribute(stem, port, registered) for port in piece]
        pieces.append(piece if stem == BUS else piece.dropna(axis=1, how="all"))
    wide = pd.concat(pieces, axis=1).reset_index()  # noqa: F841 - queried by name below
    ports = con.sql("FROM wide").set_alias("ports")
    on = ["entity", *(d for d in varying if d in static.columns)]
    joined = static.set_alias("s").join(
        ports, ex_all(col("s", c) == col("ports", c) for c in on), how="left"
    )
    return joined.project(
        *(col("s", c) for c in static.columns),
        *(col("ports", c) for c in ports.columns if c not in ("entity", *varying)),
    )


def _connection_struct(
    rel: DuckDBPyRelation, entity: Expression, bus: Expression
) -> Expression:
    """The `connection` column packed from `entity` and `bus`, typed as declared.

    Notes
    -----
    - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
    """
    group_type = DuckTypes(rel)(_registry_schema().group_type(CONNECTION))
    return struct_of({ENTITY: entity, BUS: bus}).cast(group_type).alias(CONNECTION)


def _unpack_connection(long: DuckDBPyRelation) -> DuckDBPyRelation:
    """`long` with its `connection` struct spread to `entity` and `bus`, if it has one.

    The flat pair is what PyPSA's per-type, per-port frames are keyed by, so the
    struct is unpacked once, where an attribute is read for the build.

    Notes
    -----
    - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
    """
    if CONNECTION not in long.columns:
        return long
    return long.project(
        *(col(c) for c in long.columns if c != CONNECTION),
        *(
            fn.struct_extract(col(CONNECTION), lit(field)).alias(field)
            for field in (ENTITY, BUS)
        ),
    )


def _port_columns(
    long: DuckDBPyRelation,
    stem: str,
    connections: pd.DataFrame | None,
    ctype: str,
    con: DuckDBPyConnection,
) -> dict[str, DuckDBPyRelation]:
    """A per-connection attribute's rows split into PyPSA's port columns.

    The inverse of `_NetworkSource._per_port_long_rels`: `efficiency` on a
    Link's bus1 connection is `efficiency`, on its bus2 connection
    `efficiency2`. A row takes the port `_ordered_connections` numbered its
    `(entity, bus)` with, the numbering `_collapse_connections` names
    `bus0`/`bus1`/... by, so a value lands beside the bus it is keyed by. A
    row naming no connection of the entity is dropped, as a value for no
    member is.

    Only the ports that carry `stem` (`_carries`).

    Parameters
    ----------
    long
        The attribute's rows, carrying `entity` and `bus`.
    connections
        `ctype`'s connections as `_ordered_connections` numbers them.

    Notes
    -----
    - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
    """
    if connections is None:
        return {}
    keyed = connections[[ENTITY, BUS, "port"]]  # noqa: F841 - queried by name below
    ports = con.sql("FROM keyed").set_alias("ports")
    placed = (
        long.set_alias("v")
        .join(ports, ex_all(col("v", c) == col("ports", c) for c in (ENTITY, BUS)))
        .project(*(col("v", c) for c in long.columns if c != BUS), col("ports", "port"))
    )
    registered = _registered(ctype)
    columns = {
        _port_attribute(stem, port, registered): port
        for port in connections["port"].unique()
        if _carries(stem, port, registered)
    }
    return {
        column: placed.filter(col("port") == lit(port))
        .project(star(exclude=["port"]))
        .set_alias(column)
        for column, port in columns.items()
    }


def _entity_types(record: RecordLike) -> list[str]:
    """The `entity_type` labels `record`'s entity axis has members of, sorted."""
    frame = record.properties.get(ENTITY)
    if frame is None or ENTITY_TYPE not in frame.collect_schema().names():
        return []
    labels = to_relation(frame).project(col(ENTITY_TYPE)).distinct().fetchall()
    return sorted(str(label) for (label,) in labels if label is not None)


def _members(record: RecordLike, ctype: str) -> DuckDBPyRelation | None:
    """`ctype`'s members in axis order, with the properties it carries, defaults applied.

    The static frame PyPSA's `n.<type>` starts from, `entity_type` left out;
    `build` joins the entity-only attribute rows to it. `None` where the
    record has no `entity_type` property on its entity axis.

    Notes
    -----
    - [where a value lives](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
    - [axis order](https://energy-models.github.io/datarecord/design/record/#axis-order)
    """
    schema = record.schema
    if ENTITY_TYPE not in schema.categorizing(ENTITY):
        return None
    rel = matching(to_relation(record.properties[ENTITY]), {ENTITY_TYPE: (ctype,)})
    names = carried_properties(schema, ENTITY, rel)
    key = schema.axis_key(ENTITY)
    defaulted = with_defaults(schema, ENTITY, rel, key, names, _connection(record))
    return defaulted.project(star(exclude=[ENTITY_TYPE]))


# The tool is a module-level singleton, imported rather than looked up by
# name: `from datarecord.tools.pypsa import PyPSA` then `PyPSA.build(revision.record)`.
PyPSA = PyPSATool()
