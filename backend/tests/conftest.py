import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

import pytest
from datarecord import AttributeSpec, Dimension, Revision, Schema, Store, Workspace
from duckdb import DuckDBPyConnection

from manta.services.results.datarecord_store_result import (
    DatarecordReferenceResult,
    DatarecordRevisionResult,
    ListDatarecordRevisionsResult,
)

_SCHEMA = Schema(
    dimensions={"entity": Dimension(dtype="str")},
    attributes={"p_nom": AttributeSpec(dtype="float", dims={"entity"}, default=0.0)},
)


@dataclass(frozen=True)
class _Empty:
    schema: Schema
    con: DuckDBPyConnection
    dimensions: dict = field(default_factory=dict)
    properties: dict = field(default_factory=dict)
    attributes: dict = field(default_factory=dict)

    def flags(self, **_categories: Any) -> dict:
        return {}


DatarecordStoreBuilder = Callable[[Workspace, str], ListDatarecordRevisionsResult]


def _commit(
    store: Store, parent: Revision | None, meta: dict[str, str]
) -> tuple[Revision, datetime]:
    claim = store.claim(parent=parent, meta=meta)
    return claim.commit(_Empty(_SCHEMA, store.workspace.con)), claim.created


def _expected_revision(
    revision_id: UUID,
    parent: UUID | None,
    status: Literal["claimed", "committed"],
    created_at: datetime,
    **fields: Any,
) -> DatarecordRevisionResult:
    defaults = {
        "kind": "scenario",
        "created_by": None,
        "run": None,
        "step": None,
        "committed_at": None,
        "meta": {},
    }
    return DatarecordRevisionResult(
        id=revision_id,
        parent=parent,
        status=status,
        created_at=created_at,
        **{**defaults, **fields},
    )


@pytest.fixture(scope="session")
def build_datarecord_store() -> DatarecordStoreBuilder:
    def build(workspace: Workspace, uri: str) -> ListDatarecordRevisionsResult:
        store = workspace.store(uri)
        run = uuid4()
        base, base_at = _commit(store, None, {"manta.kind": "scenario", "source": "test"})
        result, result_at = _commit(
            store,
            base,
            {
                "manta.kind": "result",
                "manta.created_by": "solve-network",
                "manta.run": str(run),
                "manta.step": "solve",
                "manta.committed_at": "2026-11-13T18:02:11Z",
            },
        )
        claim = store.claim(parent=base, meta={"manta.kind": "scenario"})
        store_file = {
            "label": "Test store",
            "description": "A base scenario and one result.",
            "references": {
                "base": {"revision": str(base.id), "label": "Base case"},
                "solved": {
                    "revision": str(result.id),
                    "base": "base",
                    "label": "Solved",
                    "description": "The base case, solved.",
                },
            },
        }
        workspace.files(uri).create(f"{uri}/store.json", json.dumps(store_file))
        return ListDatarecordRevisionsResult(
            store=uri.rsplit("/", 1)[1],
            revisions=[
                _expected_revision(base.id, None, "committed", base_at, meta={"source": "test"}),
                _expected_revision(
                    result.id,
                    base.id,
                    "committed",
                    result_at,
                    committed_at=datetime(2026, 11, 13, 18, 2, 11, tzinfo=UTC),
                    kind="result",
                    created_by="solve-network",
                    run=run,
                    step="solve",
                ),
                _expected_revision(claim.id, base.id, "claimed", claim.created),
            ],
            references=[
                DatarecordReferenceResult(
                    name="base",
                    kind="scenario",
                    revision=base.id,
                    base=None,
                    label="Base case",
                    description=None,
                ),
                DatarecordReferenceResult(
                    name="solved",
                    kind="result",
                    revision=result.id,
                    base="base",
                    label="Solved",
                    description="The base case, solved.",
                ),
            ],
        )

    return build
