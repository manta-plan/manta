"""Example data for local development and the integration tests.

TODO: temporary, until projects can get real data in some other way. It is deliberately
self-contained, so removing it means deleting this module, its config and its callers
(create_app() and AuthService.register()). That is also why it talks to S3 directly
rather than through S3FileStorageService: the originals live outside every project,
which that service rightly refuses to address, and growing it for this alone isn't
worth it. The resulting duplication of key building and error handling is accepted.
"""

import json
import logging
from collections.abc import Callable, Collection
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import httpx2
from boto3.exceptions import S3UploadFailedError
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Depends
from mypy_boto3_s3.client import S3Client
from sqlalchemy.orm import Session

from manta.config.database_config import get_db_session
from manta.config.example_data_config import (
    ADMIN_EXAMPLE_PROJECT_UUID,
    ADMIN_IDP_SUBJECT,
    ADMIN_USERNAME,
    EXAMPLE_DATA_PREFIX,
    EXAMPLE_PROJECT_NAME,
)
from manta.config.s3_config import get_s3_client, s3_bucket_name
from manta.entities import Project, User
from manta.services.results.run_result import DataRecordResult

logger = logging.getLogger(__name__)

PUBLIC_OBJECTS_URL = "https://storage.googleapis.com/storage/v1/b/manta-public-test-data/o"
"""The public bucket of example datarecord stores (the same ones playbook-library's
own tests run on), listed through Google Cloud Storage's JSON API."""

_MANIFEST = "manifest.json"
_CONCURRENT_COPIES = 16
_DESCRIPTION = "Example datarecord stores to start runs from."
_S3_ERRORS = (ClientError, BotoCoreError, S3UploadFailedError)


def _http_client() -> httpx2.Client:
    return httpx2.Client()


def _copy_store(store: str, names: Collection[str], copy: Callable[[str], object]) -> None:
    """Copies a store's files concurrently, the manifest only once everything else is in,
    so a store with a manifest is complete."""
    manifest = f"{store}/{_MANIFEST}"
    with ThreadPoolExecutor(_CONCURRENT_COPIES) as pool:
        list(pool.map(copy, [name for name in names if name != manifest]))
    if manifest in names:
        copy(manifest)


class ExampleDataService:
    """Example datarecord stores, and projects that start out with a copy of them.

    The stores are downloaded once from the public bucket to `<EXAMPLE_DATA_PREFIX>/<store>`,
    outside every project so no run ever writes to them, and copied from there into a
    project's own storage, `<project uuid>/<store>`, within S3 itself.
    """

    def __init__(
        self,
        db: Session = Depends(get_db_session),
        client: S3Client = Depends(get_s3_client),
        bucket: str = Depends(s3_bucket_name),
    ) -> None:
        self.db = db
        self.client = client
        self.bucket = bucket

    def seed(self, stores: Collection[str] = ()) -> None:
        """Downloads the given stores (all of them when none are given), skipping those
        already downloaded. Failing to reach the public bucket only logs a warning, so the
        app still starts offline."""
        try:
            with _http_client() as http:
                for store in stores or self._public_stores(http):
                    if self._exists(f"{EXAMPLE_DATA_PREFIX}/{store}/{_MANIFEST}"):
                        logger.info("Example store %r already downloaded, skipping", store)
                        continue
                    logger.info("Downloading example store %r...", store)
                    self._download_store(http, store)
        except (httpx2.HTTPError, *_S3_ERRORS):
            logger.warning("Failed to download example data, continuing without it", exc_info=True)

    def ensure_admin_project(self, idp_source: str) -> None:
        """Creates manta-admin and its example project (with a fixed uuid) unless they
        exist, and copies in any example store it doesn't have yet. `idp_source` is the
        issuer manta-admin's tokens will carry."""
        owner = (
            self.db.query(User)
            .filter(User.idp_subject == ADMIN_IDP_SUBJECT, User.idp_source == idp_source)
            .one_or_none()
        )
        if owner is None:
            owner = User(
                username=ADMIN_USERNAME, idp_subject=ADMIN_IDP_SUBJECT, idp_source=idp_source
            )
            self.db.add(owner)
            self.db.commit()
            logger.info("Created user %r (uuid=%s)", owner.username, owner.uuid)

        project = (
            self.db.query(Project).filter(Project.uuid == ADMIN_EXAMPLE_PROJECT_UUID).one_or_none()
        )
        if project is None:
            project = Project(
                uuid=ADMIN_EXAMPLE_PROJECT_UUID,
                name=EXAMPLE_PROJECT_NAME,
                description=_DESCRIPTION,
                owner_id=owner.id,
            )
            self.db.add(project)
            self.db.commit()
            logger.info("Created project %r (uuid=%s)", project.name, project.uuid)

        self._fill_project(project.uuid)

    def create_project(self, owner: User) -> None:
        project = Project(name=EXAMPLE_PROJECT_NAME, description=_DESCRIPTION, owner_id=owner.id)
        self.db.add(project)
        self.db.commit()
        logger.info("Created project %r (uuid=%s)", project.name, project.uuid)

        self._fill_project(project.uuid)

    def copy_to_project(self, project_uuid: UUID, stores: Collection[str] = ()) -> None:
        """Copies the given stores (all downloaded ones when none are given), skipping those
        already in the project."""
        for store, names in self._downloaded_stores().items():
            if stores and store not in stores:
                continue
            if self._exists(f"{project_uuid}/{store}/{_MANIFEST}"):
                continue
            logger.info("Copying example store %r into project %s...", store, project_uuid)
            _copy_store(
                store,
                names,
                lambda name: self.client.copy_object(
                    Bucket=self.bucket,
                    Key=f"{project_uuid}/{name}",
                    CopySource={"Bucket": self.bucket, "Key": f"{EXAMPLE_DATA_PREFIX}/{name}"},
                ),
            )

    def data_record(self, project_uuid: UUID, store: str) -> DataRecordResult:
        """The record a run on one of the project's copied stores starts from: its
        `inputs` revision."""
        prefix = f"{project_uuid}/{store}"
        revisions = self.client.get_object(Bucket=self.bucket, Key=f"{prefix}/revisions.json")
        return DataRecordResult(
            store_url=f"s3://{self.bucket}/{prefix}",
            revision_uuid=json.loads(revisions["Body"].read())["inputs"],
        )

    def _fill_project(self, project_uuid: UUID) -> None:
        # The project is usable without it, just empty, so this must not fail its creation.
        try:
            self.copy_to_project(project_uuid)
        except _S3_ERRORS:
            logger.warning(
                "Failed to copy example data into project %s", project_uuid, exc_info=True
            )

    def _exists(self, key: str) -> bool:
        return self.client.list_objects_v2(Bucket=self.bucket, Prefix=key)["KeyCount"] > 0

    def _downloaded_stores(self) -> dict[str, list[str]]:
        """Each downloaded store's file names, relative to EXAMPLE_DATA_PREFIX."""
        stores: dict[str, list[str]] = {}
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=f"{EXAMPLE_DATA_PREFIX}/"):
            for obj in page.get("Contents", []):
                name = obj["Key"].removeprefix(f"{EXAMPLE_DATA_PREFIX}/")
                stores.setdefault(name.split("/", 1)[0], []).append(name)
        return stores

    def _public_stores(self, http: httpx2.Client) -> list[str]:
        listing = http.get(PUBLIC_OBJECTS_URL, params={"delimiter": "/"})
        return [
            prefix.removesuffix("/") for prefix in listing.raise_for_status().json()["prefixes"]
        ]

    def _download_store(self, http: httpx2.Client, store: str) -> None:
        links = {item["name"]: item["mediaLink"] for item in self._public_objects(http, store)}

        def download(name: str) -> None:
            content = http.get(links[name]).raise_for_status().content
            self.client.put_object(
                Bucket=self.bucket, Key=f"{EXAMPLE_DATA_PREFIX}/{name}", Body=content
            )

        _copy_store(store, links, download)

    def _public_objects(self, http: httpx2.Client, store: str) -> list[dict]:
        objects: list[dict] = []
        params = {"prefix": f"{store}/"}
        while True:
            page = http.get(PUBLIC_OBJECTS_URL, params=params).raise_for_status().json()
            objects.extend(page.get("items", []))
            if "nextPageToken" not in page:
                return objects
            params["pageToken"] = page["nextPageToken"]
