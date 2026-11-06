import io
import json
import logging
from collections.abc import Collection
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import httpx2

from manta.services.results.run_result import DataRecordResult
from manta.services.s3_file_storage_service import S3FileStorageService, S3StorageError

logger = logging.getLogger(__name__)

PUBLIC_OBJECTS_URL = "https://storage.googleapis.com/storage/v1/b/manta-public-test-data/o"
"""The public bucket of example datarecord stores (the same ones playbook-library's
own tests run on), listed through Google Cloud Storage's JSON API."""

_MANIFEST = "manifest.json"
_CONCURRENT_COPIES = 16


class ExampleDataService:
    """Copies example datarecord stores from the public bucket into a project's own
    storage, each under `<project uuid>/<store name>`."""

    def __init__(self, storage: S3FileStorageService, http: httpx2.Client) -> None:
        self.storage = storage
        self.http = http

    def list_stores(self) -> list[str]:
        listing = self.http.get(PUBLIC_OBJECTS_URL, params={"delimiter": "/"})
        return [
            prefix.removesuffix("/") for prefix in listing.raise_for_status().json()["prefixes"]
        ]

    def copy_store(self, store: str, project_uuid: UUID) -> DataRecordResult:
        """Copies one store and returns its `inputs` revision, the one a run starts from."""
        manifest = f"{store}/{_MANIFEST}"
        objects = self._list_objects(f"{store}/")
        revisions = {}
        with ThreadPoolExecutor(_CONCURRENT_COPIES) as pool:
            copies = pool.map(
                lambda item: self._copy_object(item, project_uuid),
                [item for item in objects if item["name"] != manifest],
            )
            for name, content in copies:
                if name == f"{store}/revisions.json":
                    revisions = json.loads(content)
        # Only once everything else is in, so a store with a manifest is complete (see seed()).
        for item in objects:
            if item["name"] == manifest:
                self._copy_object(item, project_uuid)

        return DataRecordResult(
            store_url=f"s3://{self.storage.bucket}/{project_uuid}/{store}",
            revision_uuid=revisions["inputs"],
        )

    def seed(self, project_uuid: UUID, excluded_stores: Collection[str] = ()) -> None:
        """Copies every store not already in the project's storage. Failing to reach the
        public bucket only logs a warning, so the app still starts offline."""
        try:
            for store in self.list_stores():
                if store in excluded_stores:
                    continue
                if self.storage.file_exists(project_uuid, f"{store}/{_MANIFEST}"):
                    logger.info("Example store %r already present, skipping", store)
                    continue
                logger.info("Copying example store %r...", store)
                self.copy_store(store, project_uuid)
        except httpx2.HTTPError, S3StorageError:
            logger.warning("Failed to seed example data, continuing without it", exc_info=True)

    def _copy_object(self, item: dict, project_uuid: UUID) -> tuple[str, bytes]:
        content = self.http.get(item["mediaLink"]).raise_for_status().content
        self.storage.upload_file(project_uuid, item["name"], io.BytesIO(content))
        return item["name"], content

    def _list_objects(self, prefix: str) -> list[dict]:
        objects: list[dict] = []
        params = {"prefix": prefix}
        while True:
            page = self.http.get(PUBLIC_OBJECTS_URL, params=params).raise_for_status().json()
            objects.extend(page.get("items", []))
            if "nextPageToken" not in page:
                return objects
            params["pageToken"] = page["nextPageToken"]
