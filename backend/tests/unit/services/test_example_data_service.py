import io
import json
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import httpx2
import pytest
from botocore.exceptions import BotoCoreError

from manta.config.example_data_config import ADMIN_IDP_SUBJECT, ADMIN_USERNAME
from manta.entities import User
from manta.services import example_data_service
from manta.services.example_data_service import (
    PUBLIC_DATA_VERSION,
    PUBLIC_OBJECTS_URL,
    ExampleDataService,
)

ISSUER = "http://localhost:8080/realms/manta"
BASE = "00000000-0000-0000-0000-000000000000"
RUN = "11111111-1111-1111-1111-111111111111"
STRESS = "22222222-2222-2222-2222-222222222222"


def _manifest(revision: str, parent: str | None) -> bytes:
    return json.dumps({"id": revision, "parent": parent}).encode()


FILES = {
    "small/README.md": b"readme",
    f"small/layers/{BASE}/claim.json": b"{}",
    f"small/layers/{BASE}/attributes/a.parquet": b"data",
    f"small/layers/{BASE}/manifest.json": _manifest(BASE, None),
    f"small/layers/{RUN}/claim.json": b"{}",
    f"small/layers/{RUN}/attributes/a.parquet": b"data",
    f"small/layers/{RUN}/manifest.json": _manifest(RUN, BASE),
}
MANIFESTS = sorted(name for name in FILES if name.endswith("manifest.json"))
PUBLIC = FILES | {"plain/manifest.json": b"{}", "plain/attributes/a.parquet": b"data"}


def _public_bucket(request: httpx2.Request) -> httpx2.Response:
    if str(request.url).startswith(PUBLIC_OBJECTS_URL):
        if request.url.params.get("delimiter") == "/":
            stores = sorted({name.split("/", 1)[0] for name in PUBLIC})
            return httpx2.Response(
                200, json={"prefixes": [f"{PUBLIC_DATA_VERSION}/{store}/" for store in stores]}
            )
        items = [
            {"name": f"{PUBLIC_DATA_VERSION}/{name}", "mediaLink": f"https://media/{name}"}
            for name in PUBLIC
            if f"{PUBLIC_DATA_VERSION}/{name}".startswith(request.url.params["prefix"])
        ]
        return httpx2.Response(200, json={"items": items})
    return httpx2.Response(200, content=PUBLIC[request.url.path.removeprefix("/")])


@pytest.fixture
def bucket() -> dict[str, bytes]:
    """The S3 bucket's objects: the downloaded example store, and nothing else."""
    return {f"example-data/{name}": content for name, content in FILES.items()}


@pytest.fixture
def s3_client(bucket: dict[str, bytes]) -> MagicMock:
    """An S3 client listing and reading `bucket`."""
    client = MagicMock()
    client.get_paginator.return_value.paginate.side_effect = lambda **kwargs: [
        {"Contents": [{"Key": key} for key in bucket if key.startswith(kwargs["Prefix"])]}
    ]
    client.get_object.side_effect = lambda **kwargs: {"Body": io.BytesIO(bucket[kwargs["Key"]])}
    return client


def _service(mock_db, s3_client) -> ExampleDataService:
    return ExampleDataService(mock_db, s3_client, "manta")


def test_seed_downloads_every_layered_store_into_the_example_data(
    mock_db, bucket, s3_client, monkeypatch
) -> None:
    # Given
    bucket.clear()
    monkeypatch.setattr(
        example_data_service,
        "_http_client",
        lambda: httpx2.Client(transport=httpx2.MockTransport(_public_bucket)),
    )

    # When
    _service(mock_db, s3_client).seed()

    # Then
    uploads = [call.kwargs for call in s3_client.put_object.call_args_list]
    assert sorted(upload["Key"] for upload in uploads) == sorted(
        f"example-data/{name}" for name in FILES
    )
    assert sorted(upload["Key"] for upload in uploads[-len(MANIFESTS) :]) == [
        f"example-data/{name}" for name in MANIFESTS
    ]


@pytest.mark.parametrize(
    ("downloaded", "uploaded"),
    [
        pytest.param(set(FILES) - {MANIFESTS[0]}, set(FILES), id="cut-short"),
        pytest.param(set(FILES), set(), id="already-downloaded"),
    ],
)
def test_seed_downloads_only_stores_not_completely_downloaded(
    mock_db, bucket, s3_client, monkeypatch, downloaded: set[str], uploaded: set[str]
) -> None:
    # Given
    bucket.clear()
    bucket.update({f"example-data/{name}": FILES[name] for name in downloaded})
    monkeypatch.setattr(
        example_data_service,
        "_http_client",
        lambda: httpx2.Client(transport=httpx2.MockTransport(_public_bucket)),
    )

    # When
    _service(mock_db, s3_client).seed()

    # Then
    keys = {call.kwargs["Key"] for call in s3_client.put_object.call_args_list}
    assert keys == {f"example-data/{name}" for name in uploaded}


def test_seed_does_not_raise_when_the_public_bucket_is_unreachable(
    mock_db, s3_client, monkeypatch
) -> None:
    # Given
    def unreachable(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("offline", request=request)

    monkeypatch.setattr(
        example_data_service,
        "_http_client",
        lambda: httpx2.Client(transport=httpx2.MockTransport(unreachable)),
    )

    # When
    _service(mock_db, s3_client).seed()

    # Then
    s3_client.put_object.assert_not_called()


def test_ensure_admin_project_creates_the_admin_and_its_project_with_the_example_data(
    mock_db, s3_client
) -> None:
    # When
    _service(mock_db, s3_client).ensure_admin_project(idp_source=ISSUER)

    # Then
    user, project = [call.args[0] for call in mock_db.add.call_args_list]
    assert (user.username, user.idp_subject, user.idp_source) == (
        ADMIN_USERNAME,
        ADMIN_IDP_SUBJECT,
        ISSUER,
    )
    assert project.owner_id == user.id
    copies = [call.kwargs for call in s3_client.copy_object.call_args_list]
    assert sorted(copy["Key"] for copy in copies) == sorted(
        f"{project.uuid}/{name}" for name in FILES
    )
    assert sorted(copy["CopySource"]["Key"] for copy in copies[-len(MANIFESTS) :]) == [
        f"example-data/{name}" for name in MANIFESTS
    ]


@pytest.mark.parametrize(
    ("example_data", "project_data", "copied"),
    [
        pytest.param(set(FILES) - {MANIFESTS[0]}, {}, set(), id="layer-without-manifest"),
        pytest.param({"small/README.md"}, {}, set(), id="no-layers"),
        pytest.param(set(FILES), FILES, set(), id="already-copied"),
        pytest.param(
            set(FILES),
            FILES | {f"small/layers/{STRESS}/claim.json": b"{}"},
            set(),
            id="already-copied-with-unwritten-layer",
        ),
        pytest.param(
            set(FILES),
            {name: FILES[name] for name in set(FILES) - {MANIFESTS[0]}},
            set(FILES),
            id="copy-missing-a-manifest",
        ),
    ],
)
def test_copy_to_project_copies_only_complete_stores_not_already_copied(
    mock_db,
    bucket,
    s3_client,
    example_data: set[str],
    project_data: dict[str, bytes],
    copied: set[str],
) -> None:
    # Given
    bucket.clear()
    bucket.update({f"example-data/{name}": FILES[name] for name in example_data})
    project_uuid = _copied(bucket, project_data)

    # When
    _service(mock_db, s3_client).copy_to_project(project_uuid)

    # Then
    keys = {call.kwargs["Key"] for call in s3_client.copy_object.call_args_list}
    assert keys == {f"{project_uuid}/{name}" for name in copied}


def test_create_project_keeps_the_project_when_copying_the_example_data_fails(
    mock_db, s3_client
) -> None:
    # Given
    s3_client.copy_object.side_effect = BotoCoreError()

    # When
    _service(mock_db, s3_client).create_project(User(username="alice"))

    # Then
    mock_db.commit.assert_called_once()


def _copied(bucket: dict[str, bytes], files: dict[str, bytes]) -> UUID:
    project_uuid = uuid4()
    bucket.update({f"{project_uuid}/{name}": content for name, content in files.items()})
    return project_uuid


def test_data_record_is_the_base_scenarios_input_revision(mock_db, bucket, s3_client) -> None:
    # Given
    stress = {f"small/layers/{STRESS}/manifest.json": _manifest(STRESS, BASE)}
    project_uuid = _copied(bucket, FILES | stress)

    # When
    record = _service(mock_db, s3_client).data_record(project_uuid, "small")

    # Then
    assert record.store_url == f"s3://manta/{project_uuid}/small"
    assert str(record.revision_uuid) == BASE


@pytest.mark.parametrize(
    "files",
    [
        pytest.param({f"small/layers/{RUN}/manifest.json": _manifest(RUN, BASE)}, id="none"),
        pytest.param(
            FILES | {f"small/layers/{STRESS}/manifest.json": _manifest(STRESS, None)}, id="two"
        ),
    ],
)
def test_data_record_raises_without_exactly_one_base_input_revision(
    mock_db, bucket, s3_client, files: dict[str, bytes]
) -> None:
    # Given
    project_uuid = _copied(bucket, files)

    # When / Then
    with pytest.raises(ValueError):
        _service(mock_db, s3_client).data_record(project_uuid, "small")
