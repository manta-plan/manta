import json
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from datarecord import Workspace
from fastapi import HTTPException
from pydantic import ValidationError

from manta.entities import Project, User
from manta.services.datarecord_store_service import DatarecordStoreService
from manta.services.errors import AuthorizationError, BackendError
from manta.services.results.datarecord_store_result import DatarecordStoreResult
from manta.services.user_service import UserService


@pytest.fixture
def workspace() -> Iterator[Workspace]:
    workspace = Workspace()
    yield workspace
    workspace.close()


@pytest.fixture
def project() -> Project:
    project = Project(name="North Sea Wind", owner_id=1)
    project.id = 10
    project.uuid = uuid4()
    return project


def _user(user_id: int = 1) -> User:
    user = User(username="alice")
    user.id = user_id
    return user


def _service(
    workspace: Workspace, root: Path, project: Project | None, mock_db_class
) -> DatarecordStoreService:
    db = mock_db_class({Project: project})
    return DatarecordStoreService(workspace=workspace, root=str(root), user_service=UserService(db))


def test_list_stores_returns_the_folders_with_a_store_file(
    workspace, project, tmp_path, mock_db_class, build_datarecord_store
) -> None:
    # Given
    build_datarecord_store(workspace, f"{tmp_path}/{project.uuid}/b-store")
    workspace.store(f"{tmp_path}/{project.uuid}/incomplete").claim(parent=None)
    for name in ["a-store", ".hidden"]:
        (tmp_path / str(project.uuid) / name).mkdir()
        (tmp_path / str(project.uuid) / name / "store.json").write_text(
            json.dumps({"label": "A", "references": {}})
        )
    service = _service(workspace, tmp_path, project, mock_db_class)

    # When
    result = service.list_stores(project.uuid, user=_user())

    # Then
    assert result.items == [
        DatarecordStoreResult(name="a-store", label="A", description=None),
        DatarecordStoreResult(
            name="b-store", label="Test store", description="A base scenario and one result."
        ),
    ]


def test_list_stores_of_a_project_without_files_is_empty(
    workspace, project, tmp_path, mock_db_class
) -> None:
    # Given
    service = _service(workspace, tmp_path, project, mock_db_class)

    # When
    result = service.list_stores(project.uuid, user=_user())

    # Then
    assert result.items == []


def test_list_revisions_returns_revisions_and_references(
    workspace, project, tmp_path, mock_db_class, build_datarecord_store
) -> None:
    # Given
    expected = build_datarecord_store(workspace, f"{tmp_path}/{project.uuid}/store")
    service = _service(workspace, tmp_path, project, mock_db_class)

    # When
    result = service.list_revisions(project.uuid, "store", user=_user())

    # Then
    assert result == expected


def test_list_revisions_shows_a_new_revision_at_the_next_listing(
    workspace, project, tmp_path, mock_db_class, build_datarecord_store
) -> None:
    # Given
    store = workspace.store(f"{tmp_path}/{project.uuid}/store")
    build_datarecord_store(workspace, store.uri)
    service = _service(workspace, tmp_path, project, mock_db_class)
    before = service.list_revisions(project.uuid, "store", user=_user())
    [claim] = store.claims()
    claim.commit(store.revision(claim.parent).record)

    # When
    after = service.list_revisions(project.uuid, "store", user=_user())

    # Then
    committed = before.revisions[-1].model_copy(update={"status": "committed"})
    assert after.revisions == [*before.revisions[:-1], committed]


def test_list_revisions_of_an_unknown_store_is_not_found(
    workspace, project, tmp_path, mock_db_class
) -> None:
    # Given
    service = _service(workspace, tmp_path, project, mock_db_class)

    # When / Then
    with pytest.raises(HTTPException) as excinfo:
        service.list_revisions(project.uuid, "missing", user=_user())
    assert excinfo.value.status_code == 404


LISTINGS = [
    lambda service, project_uuid, user: service.list_stores(project_uuid, user=user),
    lambda service, project_uuid, user: service.list_revisions(project_uuid, "store", user=user),
]
STORES, REVISIONS = LISTINGS


@pytest.mark.parametrize(
    ("listing", "store_file", "meta", "error", "match"),
    [
        (STORES, {"label": "A"}, {}, ValidationError, "references"),
        (REVISIONS, {"label": "A"}, {}, ValidationError, "references"),
        (
            REVISIONS,
            {"label": "A", "references": {}},
            {"manta.run": "run-1"},
            ValidationError,
            "run",
        ),
        (
            REVISIONS,
            {"label": "A", "references": {"gone": {"revision": str(uuid4()), "label": "Gone"}}},
            {},
            BackendError,
            "'store'.*'gone'",
        ),
    ],
    ids=["stores_malformed_file", "revisions_malformed_file", "non_uuid_run", "dangling_reference"],
)
def test_listing_fails_on_malformed_store_data(
    listing, store_file, meta, error, match, workspace, project, tmp_path, mock_db_class
) -> None:
    # Given
    workspace.store(f"{tmp_path}/{project.uuid}/store").claim(parent=None, meta=meta)
    (tmp_path / str(project.uuid) / "store" / "store.json").write_text(json.dumps(store_file))
    service = _service(workspace, tmp_path, project, mock_db_class)

    # When / Then
    with pytest.raises(error, match=match):
        listing(service, project.uuid, _user())


@pytest.mark.parametrize("listing", LISTINGS, ids=["stores", "revisions"])
@pytest.mark.parametrize(
    ("exists", "error", "status_code"),
    [(True, AuthorizationError, 403), (False, HTTPException, 404)],
    ids=["foreign_project", "unknown_project"],
)
def test_listing_needs_an_owned_project(
    listing, exists, error, status_code, workspace, project, tmp_path, mock_db_class
) -> None:
    # Given
    service = _service(workspace, tmp_path, project if exists else None, mock_db_class)

    # When / Then
    with pytest.raises(error) as excinfo:
        listing(service, project.uuid, _user(user_id=2))
    assert excinfo.value.status_code == status_code
