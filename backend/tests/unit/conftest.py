from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest


class _MockSession:
    def __init__(self) -> None:
        self.id = 1
        self.uuid = uuid4()
        self.created_at = datetime.now(UTC)
        self.add = MagicMock(side_effect=self._assign_generated_fields)
        self.commit = MagicMock()

    def _assign_generated_fields(self, entity) -> None:
        entity.id = self.id
        entity.uuid = self.uuid
        entity.created_at = self.created_at


@pytest.fixture
def mock_db() -> _MockSession:
    return _MockSession()


class _MockS3Client:
    def __init__(self) -> None:
        self.upload_fileobj = MagicMock()
        self.download_fileobj = MagicMock()
        self.head_object = MagicMock(
            return_value={"ContentLength": 0, "LastModified": datetime.now(UTC)}
        )
        self.head_bucket = MagicMock()
        self.create_bucket = MagicMock()
        self.delete_object = MagicMock()


@pytest.fixture
def mock_s3_client() -> _MockS3Client:
    return _MockS3Client()
