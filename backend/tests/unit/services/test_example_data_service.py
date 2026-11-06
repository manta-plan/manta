import json
from unittest.mock import MagicMock
from uuid import uuid4

import httpx2

from manta.services.example_data_service import PUBLIC_OBJECTS_URL, ExampleDataService
from manta.services.s3_file_storage_service import S3StorageError

INPUTS = "e5f2eacd-ba5c-463c-a663-3017ef904d1d"

FILES = {
    "small/manifest.json": b"{}",
    "small/revisions.json": json.dumps({"inputs": INPUTS}).encode(),
    "small/layers/a.parquet": b"data",
    "large/manifest.json": b"{}",
    "large/revisions.json": json.dumps({"inputs": INPUTS}).encode(),
}


def _public_bucket(request: httpx2.Request) -> httpx2.Response:
    if str(request.url).startswith(PUBLIC_OBJECTS_URL):
        params = request.url.params
        if params.get("delimiter") == "/":
            return httpx2.Response(200, json={"prefixes": ["small/", "large/"]})
        items = [
            {"name": name, "mediaLink": f"https://media/{name}"}
            for name in FILES
            if name.startswith(params["prefix"])
        ]
        return httpx2.Response(200, json={"items": items})
    return httpx2.Response(200, content=FILES[request.url.path.removeprefix("/")])


def _service(storage: MagicMock, handler=_public_bucket) -> ExampleDataService:
    return ExampleDataService(storage, httpx2.Client(transport=httpx2.MockTransport(handler)))


def _storage(existing: set[str] = frozenset()) -> MagicMock:
    storage = MagicMock()
    storage.bucket = "manta"
    storage.file_exists.side_effect = lambda _project_uuid, filename: filename in existing
    return storage


def _uploaded(storage: MagicMock) -> list[str]:
    return [call.args[1] for call in storage.upload_file.call_args_list]


def test_copy_store_uploads_every_file_under_the_project_and_returns_its_inputs() -> None:
    # Given
    storage = _storage()
    project_uuid = uuid4()

    # When
    record = _service(storage).copy_store("small", project_uuid)

    # Then
    assert sorted(_uploaded(storage)) == sorted(n for n in FILES if n.startswith("small/"))
    assert {call.args[0] for call in storage.upload_file.call_args_list} == {project_uuid}
    assert record.store_url == f"s3://manta/{project_uuid}/small"
    assert str(record.revision_uuid) == INPUTS


def test_copy_store_uploads_the_manifest_last() -> None:
    # Given
    storage = _storage()

    # When
    _service(storage).copy_store("small", uuid4())

    # Then
    assert _uploaded(storage)[-1] == "small/manifest.json"


def test_copy_store_follows_listing_pages() -> None:
    # Given
    storage = _storage()

    def paged(request: httpx2.Request) -> httpx2.Response:
        if "pageToken" in request.url.params:
            items = [
                {"name": "small/revisions.json", "mediaLink": "https://media/small/revisions.json"}
            ]
            return httpx2.Response(200, json={"items": items})
        if "prefix" in request.url.params:
            items = [
                {"name": "small/manifest.json", "mediaLink": "https://media/small/manifest.json"}
            ]
            return httpx2.Response(200, json={"items": items, "nextPageToken": "next"})
        return _public_bucket(request)

    # When
    _service(storage, paged).copy_store("small", uuid4())

    # Then
    assert sorted(_uploaded(storage)) == ["small/manifest.json", "small/revisions.json"]


def test_seed_copies_every_store_not_excluded() -> None:
    # Given
    storage = _storage()

    # When
    _service(storage).seed(uuid4(), excluded_stores={"large"})

    # Then
    assert all(name.startswith("small/") for name in _uploaded(storage))
    assert "small/manifest.json" in _uploaded(storage)


def test_seed_skips_stores_already_present() -> None:
    # Given
    storage = _storage(existing={"small/manifest.json"})

    # When
    _service(storage).seed(uuid4())

    # Then
    assert all(name.startswith("large/") for name in _uploaded(storage))


def test_seed_does_not_raise_when_the_public_bucket_is_unreachable() -> None:
    # Given
    storage = _storage()

    def unreachable(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("offline", request=request)

    # When
    _service(storage, unreachable).seed(uuid4())

    # Then
    storage.upload_file.assert_not_called()


def test_seed_does_not_raise_when_storage_fails() -> None:
    # Given
    storage = _storage()
    storage.upload_file.side_effect = S3StorageError("boom")

    # When / Then
    _service(storage).seed(uuid4())
