# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""Writing a whole record as a layer.

A `LayerData` hands over relations and this module turns them into parquet;
producing one from a framework's own object is a tool's job.

Notes
-----
- [writing a whole record](https://energy-models.github.io/datarecord/design/writing/)
- [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
- [module layout](https://energy-models.github.io/datarecord/design/module-layout/)
"""

from __future__ import annotations

import copy
import random
import shutil
from pathlib import Path
from time import sleep
from typing import TYPE_CHECKING
from uuid import uuid4

import narwhals as nw
from duckdb import CoalesceOperator as coalesce
from duckdb import ColumnExpression as col
from duckdb import ConstantExpression as lit
from duckdb import SQLExpression as sql
from duckdb import StarExpression as star

from datarecord.duck import as_relation, fn, null_safe
from datarecord.files import Absent, PreconditionFailedError, Version
from datarecord.layered.record import Record
from datarecord.layered.resolve import PinnedResolver, cast_declared, resolve_coords
from datarecord.layered.sources import DirectorySource
from datarecord.record import Frames, LayerData, RecordLike
from datarecord.schema import DERIVED, Schema

if TYPE_CHECKING:
    from collections.abc import Sequence

    from duckdb import DuckDBPyConnection, DuckDBPyRelation

    from datarecord.layered.sources import LayerSource
    from datarecord.store import Store, Workspace


def layer_data(source: LayerData | RecordLike, con: DuckDBPyConnection) -> LayerData:
    """`source` as the `LayerData` the writer reads, planned on `con`.

    A framework's `RecordLike` is wrapped in a thin adapter reading its `Frames`
    through the same enumerate-and-read pairs.

    Notes
    -----
    - [LayerData](https://energy-models.github.io/datarecord/design/record/#layerdata)
    """
    if isinstance(source, LayerData):
        return source
    return _RecordLikeAsLayerData(_pinned(source), con)


def _pinned(source: RecordLike) -> RecordLike:
    """`source`, or where it is a `Record` past a staging area, a copy over a `PinnedResolver`.

    The copy keeps every member of `source`'s class - a `WorkingRecord`'s own
    `outputs` among them - and swaps only the resolver, so it reads what
    `source` reads with the fold done once. Held only for one write, during
    which nothing stages.
    """
    if not isinstance(source, Record) or source.resolver.frozen:
        return source
    pinned = copy.copy(source)
    object.__setattr__(pinned, "resolver", PinnedResolver.of(source.resolver))
    return pinned


def write_layer(
    data: LayerData,
    base: str,
    workspace: Workspace,
    *,
    manifest: str | None = None,
    parents: Sequence[LayerSource] = (),
) -> None:
    """Write `data` as the layer directory `base`, which must not exist yet.

    An existing layer directory is an error rather than an overwrite or a merge,
    so a whole-record write can never half-replace what a record holds. Keys are
    looked up one at a time and each file written before the next is built, so a
    lazily-building source does one read per file rather than one per key up
    front. Locally the layer is staged into a sibling and renamed, so a failed
    write leaves nothing; remotely it can leave part of a layer, which nothing
    reaches without the file written after it.

    Parameters
    ----------
    data
        The layer's contents, validated against its own schema as each frame is
        built.
    manifest
        A standalone record's `manifest.json` text, written into the
        directory last; a tree layer holds only data.
    parents
        The sources the layer folds over, root first; none for a root or a
        standalone record.

    Raises
    ------
    FileExistsError
        If the layer directory already exists locally.
    ValueError
        If a long frame is missing a long-schema column, or the schema declares a key
        dim no frame carries - either would make the fold misresolve the layer.
        If a group tuple alive after the layer names a label dead after it.

    Notes
    -----
    - [the long schema](https://energy-models.github.io/datarecord/design/format/#the-long-schema)
    - [writing a whole record](https://energy-models.github.io/datarecord/design/writing/)
    - [a revision exists only by its file](https://energy-models.github.io/datarecord/design/writing/#a-revision-exists-only-by-its-file)
    """
    local = "://" not in base
    if local and Path(base).exists():
        msg = f"layer {base} already exists; a write creates a new layer (https://energy-models.github.io/datarecord/design/writing/)"
        raise FileExistsError(msg)
    schema = data.schema

    # Staged then renamed, so a frame that fails validation part-way through
    # leaves no layer rather than half of one (https://energy-models.github.io/datarecord/design/writing/). Validation happens as each
    # frame is built, since building it twice would defeat the laziness.
    staging = f"{base.rstrip('/')}.staging/" if local else base
    if local:
        Path(staging).mkdir(parents=True)
    try:
        kinds = [
            ("dims", data.axes(), data.axis, "dims"),
            ("groups", data.groups(), data.group, "groups"),
            ("attributes", data.attributes(), data.attribute, "inputs"),
        ]
        # `outputs/` only for a source carrying results, so a record with none
        # produces a layer without the directory rather than an empty one (https://energy-models.github.io/datarecord/design/writing/).
        output_names = data.attributes("outputs")
        if output_names:
            kinds.append(
                (
                    "outputs",
                    output_names,
                    lambda name: data.attribute(name, "outputs"),
                    "outputs",
                )
            )
        for kind, keys, read, subdir in kinds:
            for key in keys:
                rel = read(
                    key
                )  # looked up exactly once (https://energy-models.github.io/datarecord/design/writing/)
                if rel is None:
                    continue
                _validate_frame(rel, kind, key, schema)
                _write_frame(rel, f"{staging}{subdir}/{key}.parquet", schema)
        if data.groups() or data.axes():
            layer = DirectorySource(staging, schema, workspace, uuid4())
            _require_living_tuples(parents, layer, workspace.con, schema)
        # A standalone directory *is* one record, so its schema is in it, and
        # written last: a directory without one reads as no record.
        if manifest is not None:
            workspace.files(staging).write_text(
                staging + "manifest.json", manifest, expect=Absent()
            )
    except BaseException:
        if local:
            shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        if isinstance(data, _RecordLikeAsLayerData):
            data.release()
    if local:
        Path(staging).rename(base.rstrip("/"))


def reconcile_schema(schema: Schema, store: Store) -> None:
    """Declare the record's schema, or check this layer agrees with it.

    A schema is not layered data, so there is nothing to fold: the first writer
    states it and the rest must be `compatible_with` it. Read and written beside
    `store`'s own layers, so one record never consults another's manifest.

    A compare-and-swap: the manifest is written only if unchanged since it was
    read, and a writer that lost re-reads and checks again, so two writers
    widening at once end with both widenings or an incompatibility reported,
    never one silently lost. A lost write backs off with jitter and is retried
    up to `_ATTEMPTS` times.

    Raises
    ------
    ValueError
        If this layer's schema would make the record's existing layers
        unreadable.
    RuntimeError
        If every attempt lost: the manifest kept changing, or it cannot be read
        and a 403 was taken for a missing key.

    Notes
    -----
    - [one schema per record](https://energy-models.github.io/datarecord/design/schema/#one-schema-per-record)
    - [versioning](https://energy-models.github.io/datarecord/design/schema/#versioning)
    - [the manifest's compare-and-swap](https://energy-models.github.io/datarecord/design/writing/#the-manifests-compare-and-swap)
    """
    files = store.files
    for attempt in range(_ATTEMPTS):
        found = files.read_text(store.manifest_uri)
        expect: Version | Absent = Absent() if found is None else found[1]
        existing = Schema() if found is None else Schema.model_validate_json(found[0])
        if existing.dimensions or existing.attributes:
            if schema == existing:
                return
            problems = schema.compatible_with(existing)
            if problems:
                msg = (
                    f"this layer's schema is incompatible with the record's: "
                    f"{'; '.join(problems)} (https://energy-models.github.io/datarecord/design/schema/#versioning)"
                )
                raise ValueError(msg)
        try:
            files.write_text(
                store.manifest_uri, schema.model_dump_json(), expect=expect
            )
        except PreconditionFailedError:
            sleep(random.uniform(0, 0.05 * 2**attempt))
            continue
        return
    msg = (
        f"{store.manifest_uri} changed under each of {_ATTEMPTS} writes, or cannot "
        f"be read: a 403 on read counts as missing, so check s3:GetObject "
        f"(https://energy-models.github.io/datarecord/design/writing/#the-manifests-compare-and-swap)"
    )
    raise RuntimeError(msg)


_ATTEMPTS = 10
"""How many times `reconcile_schema` writes the manifest before giving up."""


def _write_frame(rel: DuckDBPyRelation, uri: str, schema: Schema) -> None:
    """Persist one relation as parquet, unmaterialised.

    Columns are cast to their declared types on the way out, so a reader can
    trust them rather than re-casting an all-NULL column pandas typed as float.

    `DERIVED` is dropped here rather than in the callers, so a column a source
    happens to carry cannot reach a file by a path that forgot to strip it.

    Notes
    -----
    - [Frames](https://energy-models.github.io/datarecord/design/record/#frames)
    - [writing a whole record](https://energy-models.github.io/datarecord/design/writing/)
    """
    if "://" not in uri:
        Path(uri).parent.mkdir(parents=True, exist_ok=True)
    unwritable = [c for c in DERIVED if c in rel.columns]
    if unwritable:
        rel = rel.project(star(exclude=unwritable))
    cast_declared(schema, rel).to_parquet(uri)


def _require_living_tuples(
    parents: Sequence[LayerSource],
    layer: LayerSource,
    con: DuckDBPyConnection,
    schema: Schema,
) -> None:
    """Reject a layer adding a group tuple that names a dead label, or killing one a tuple names.

    Removing a label tombstones the tuples naming it in the same layer, which
    `WorkingRecord.remove` writes; a layer written otherwise carries its own.
    Only what `layer` does is checked - the tuples it writes, and the tuples
    still naming a label it tombstones - so a tuple an ancestor left dangling
    fails no later write. Only a field over a dim keyed by its label alone is
    checked: a nested dim's label names no point without its parents, which a
    tuple does not carry. A layer adding no tuple and killing no such label
    resolves nothing.

    Raises
    ------
    ValueError
        Naming up to three such tuples per group field.

    Notes
    -----
    - [deletion](https://energy-models.github.io/datarecord/design/layers/#deletion)
    """
    drawn = {
        d
        for g in schema.group_columns
        for d in schema.groups[g].over.values()
        if len(schema.axis_key(d)) == 1
    }
    killed = {
        d: tomb
        for d in layer.axes()
        if d in drawn
        and (rel := layer.axis(d)) is not None
        and "deleted" in rel.columns
        and (tomb := rel.filter(col("deleted"))).limit(1).fetchone() is not None
    }
    added_by_group = {
        g: rel
        for g in schema.group_columns
        if (rel := _living(layer.group(g))) is not None
        and rel.limit(1).fetchone() is not None
    }
    if not killed and not added_by_group:
        return
    coords = resolve_coords(schema, [*parents, layer], con)
    problems = []
    for g in schema.group_columns:
        added = added_by_group.get(g)
        for field, dim in schema.groups[g].over.items():
            dead = coords.dead.get(dim)
            if dead is None or len(schema.axis_key(dim)) > 1:
                continue
            suspects = [] if added is None else [(added, dead)]
            if dim in killed and g in coords.groups:
                mine = dead.set_alias("d").join(
                    killed[dim].set_alias("k"),
                    col("d", dim) == col("k", dim),
                    how="semi",
                )
                suspects.append((coords.groups[g], mine))
            on = fn.struct_extract(col("t", g), lit(field)) == col("x", dim)
            hits = [
                h
                for tuples, labels in suspects
                for (h,) in tuples.set_alias("t")
                .join(labels.set_alias("x"), on, how="semi")
                .project(col(g))
                .limit(3)
                .fetchall()
            ]
            if hits:
                problems.append(f"{g} {hits[:3]} name a removed {dim} in {field!r}")
    if problems:
        msg = (
            f"{'; '.join(problems)}; removing a label removes the tuples naming "
            f"it, so tombstone them in the same layer (https://energy-models.github.io/datarecord/design/layers/#deletion)"
        )
        raise ValueError(msg)


def _living(rel: DuckDBPyRelation | None) -> DuckDBPyRelation | None:
    """`rel`'s rows that are no tombstone."""
    if rel is None or "deleted" not in rel.columns:
        return rel
    return rel.filter(~coalesce(col("deleted"), lit(False)))  # noqa: FBT003


def _validate_frame(rel: DuckDBPyRelation, kind: str, key: str, schema: Schema) -> None:
    """Check one frame is shaped for the fold to resolve it.

    Structural only: a long frame carries its own attribute's coordinates, and a
    `dims/` frame carries every dim the schema declares it keyed by. Values
    are not checked - which labels and attribute names are valid
    belongs to whatever vocabulary the schema declares, and the record layer
    knows none.

    An attribute's coordinates are what its `dims` declare, so one file's column
    set is not another's and neither is every declared dim. A result the schema
    does not declare has no coordinates to derive, so it falls back to the fixed
    columns every long row has.

    Reads the schema rather than the rows, so validating an unmaterialised
    relation costs nothing.

    Notes
    -----
    - [the Record protocol](https://energy-models.github.io/datarecord/design/record/)
    - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
    - [the schema](https://energy-models.github.io/datarecord/design/schema/)
    - [partial](https://energy-models.github.io/datarecord/design/schema/#partial-the-granularity-of-an-override)
    """
    columns = set(rel.columns)

    # `outputs/` uses the same long schema as `inputs/`; it just does not
    # overlay (https://energy-models.github.io/datarecord/design/read-path/#outputs), which is a read-path property rather than a shape one.
    if kind in ("attributes", "outputs"):
        subdir = "inputs" if kind == "attributes" else "outputs"
        # An input's shape comes from its spec, so one the schema does not
        # declare has no shape to check it against - and writing it would put a
        # file in `inputs/` that no read path knows the columns of. A *result*
        # is never declared, a tool deriving those from its own registry.
        if kind == "attributes" and key not in schema.attributes:
            msg = (
                f"inputs/{key}.parquet is not a declared attribute; its `dims` "
                f"are what say which columns the file carries (https://energy-models.github.io/datarecord/design/schema/#attributespec)"
            )
            raise ValueError(msg)
        # A result's shape is not the schema's to fix, even where its name
        # matches a declared attribute: `outputs/control.parquet` may vary over
        # axes the *input* `control` does not. So only the fixed columns every
        # long row has are required of one (https://energy-models.github.io/datarecord/design/read-path/#outputs).
        required = (
            set(schema.long_columns_for(key))
            if kind == "attributes"
            else {"attribute", "breakpoint", "value"}
        )
        missing = sorted(required - columns)
        if missing:
            msg = (
                f"{subdir}/{key}.parquet is missing long-schema columns {missing}; "
                f"the resolved relation needs {sorted(required)} (https://energy-models.github.io/datarecord/design/format/#the-long-schema)"
            )
            raise ValueError(msg)
        # And an *input* carries nothing else: a coordinate the attribute is
        # not addressed by would be a column the read path never projects,
        # written as a fact about a value that does not have one. Reported
        # rather than dropped, since a source emitting one disagrees with the
        # schema about what the attribute is - the source's bug to fix.
        #
        # A result is exempt for the same reason it need not be declared: its
        # shape is a framework's business, and a name it shares with an input
        # says nothing about which coordinates the *result* varies over.
        extra = sorted(columns - required) if kind == "attributes" else []
        if extra:
            msg = (
                f"{subdir}/{key}.parquet carries columns {extra} the attribute is "
                f"not addressed by; its `dims` say {sorted(required)} (https://energy-models.github.io/datarecord/design/format/#the-long-schema)"
            )
            raise ValueError(msg)
        if kind == "attributes":
            schema.check_group_columns(
                schema.groups_of(key),
                nw.from_native(rel),
                carrier=f"inputs/{key}.parquet",
            )
        return

    if kind == "dims":
        # A nested axis is keyed by `(*parents, dim)` (https://energy-models.github.io/datarecord/design/schema/#within-an-axis-inside-an-axis), so its file needs
        # a column per parent - without one the fold would key by a column that
        # is not there, and two periods' identically-labelled timesteps would
        # resolve as one row. An undeclared dim has no nesting to check: the
        # schema's vocabulary is what `axis_key` reads, and a source may hand
        # over an axis the schema does not name.
        if key not in schema.dimensions:
            return
        missing = sorted(set(schema.axis_key(key)) - columns)
        if missing:
            msg = (
                f"dims/{key}.parquet is missing axis key columns {missing}; "
                f"{key!r} is `within` {sorted(schema.dimensions[key].within)} so "
                f"its labels identify a point only within them (https://energy-models.github.io/datarecord/design/schema/#within-an-axis-inside-an-axis)"
            )
            raise ValueError(msg)
        _refuse_extra(
            columns,
            {*schema.axis_key(key), "deleted", "order_key"},
            schema,
            key,
            f"dims/{key}.parquet",
        )
        return

    if kind != "groups" or key not in schema.groups:
        return
    into = schema.groups[key].into
    missing = sorted({key, *([into] if into else [])} - columns)
    if missing:
        msg = (
            f"groups/{key}.parquet is missing {missing}; a group file is keyed "
            f"by one struct column named for the group, its `into` label beside "
            f"it (https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)"
        )
        raise ValueError(msg)
    _refuse_extra(
        columns,
        {key, *([into] if into else []), "deleted", "order_key"},
        schema,
        key,
        f"groups/{key}.parquet",
    )
    schema.check_group_columns(
        [key], nw.from_native(rel), carrier=f"groups/{key}.parquet"
    )


def _refuse_extra(
    columns: set[str], structural: set[str], schema: Schema, subject: str, file: str
) -> None:
    """Refuse a column of an axis or group file beyond `structural` and `subject`'s properties.

    `structural` is the key, the tombstone and an explicit order key.

    Notes
    -----
    - [where a value lives](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
    """
    extra = sorted(columns - structural - set(schema.properties.get(subject, {})))
    if not extra:
        return
    attributes = [c for c in extra if c in schema.attributes]
    named = "they" if attributes == extra else str(attributes)
    hint = (
        f"; {named} are attributes, whose values are long rows of "
        f"inputs/<attr>.parquet whatever their `dims`"
        if attributes
        else ""
    )
    msg = (
        f"{file} carries columns {extra} the schema does not declare as "
        f"properties of {subject!r}; the file holds its key, tombstones and "
        f"{subject!r}'s properties{hint} (https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)"
    )
    raise ValueError(msg)


class _RecordLikeAsLayerData:
    """A `RecordLike` read through `LayerData`'s enumerate-and-read pairs.

    The adapter that lets `write_layer` stay one code path over raw
    relations: a framework's `to_datarecord()` hands over narwhals `Frames`,
    one lookup per key exactly as `write_layer` already does, so this wraps
    each mapping rather than eagerly converting it. `con` is needed only to
    land a non-DuckDB frame as a relation (`as_relation`).

    Notes
    -----
    - [LayerData](https://energy-models.github.io/datarecord/design/record/#layerdata)
    """

    def __init__(self, source: RecordLike, con: DuckDBPyConnection) -> None:
        self._source = source
        self._con = con
        self._mappings: dict[str, Frames] = {}

    @property
    def schema(self) -> Schema:
        return self._source.schema

    @property
    def frozen(self) -> bool:
        # A framework object is read once to produce a layer, never folded
        # under a reader, so there is nothing for staleness to mean here.
        return True

    def release(self) -> None:
        """Drop what a pinned source holds for this write."""
        if isinstance(self._source, Record) and isinstance(
            self._source.resolver, PinnedResolver
        ):
            self._source.resolver.release()

    def _frames(self, kind: str) -> Frames:
        """The source's `Frames` mapping named `kind`, enumerated once per adapter.

        A `RecordLike`'s mappings may be properties that re-enumerate the whole
        source on each access, which per key would be quadratic in the keys.
        """
        if kind not in self._mappings:
            self._mappings[kind] = getattr(self._source, kind)
        return self._mappings[kind]

    def _read(self, frames: Frames, key: str) -> DuckDBPyRelation | None:
        if key not in frames:
            return None
        return as_relation(frames[key], self._con)

    def axes(self) -> set[str]:
        return set(self._frames("dims"))

    def axis(self, dim: str) -> DuckDBPyRelation | None:
        """`dims[dim]` with `properties[dim]` joined on the axis key, in `dims[dim]`'s row order.

        The row is numbered on `dims[dim]` alone, as `fold_axis` numbers a
        layer's, and the `ORDER BY` on it is the outermost clause, since a
        join defines no order.
        """
        axis = self._read(self._frames("dims"), dim)
        if axis is None or dim not in self._frames("properties"):
            return axis
        props = self._read(self._frames("properties"), dim)
        if props is None:
            return axis
        values = [c for c in props.columns if c not in axis.columns]
        if not values:
            return axis
        joined = (
            axis.project(star(), sql("row_number() OVER ()").alias("_row"))
            .set_alias("a")
            .join(
                props.set_alias("p"),
                null_safe("a", "p", self.schema.axis_key(dim)),
                how="left",
            )
            .project(
                col("a", "_row"),
                *(col("a", c) for c in axis.columns),
                *(col("p", c) for c in values),
            )
        )
        return joined.query("j", "SELECT * EXCLUDE (_row) FROM j ORDER BY _row")

    def groups(self) -> set[str]:
        return set(self._frames("groups"))

    def group(self, name: str) -> DuckDBPyRelation | None:
        return self._read(self._frames("groups"), name)

    def attributes(self, kind: str = "inputs") -> set[str]:
        frames = self._frames("attributes" if kind == "inputs" else "outputs")
        return set(frames)

    def attribute(self, name: str, kind: str = "inputs") -> DuckDBPyRelation | None:
        frames = self._frames("attributes" if kind == "inputs" else "outputs")
        return self._read(frames, name)
