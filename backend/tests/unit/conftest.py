from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest


class _FakeQuery:
    def __init__(self, result) -> None:
        self._result = result

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._result


class _MockSession:
    def __init__(self, query_results: dict[type, object] | None = None) -> None:
        self.id = 1
        self.uuid = uuid4()
        self.created_at = datetime.now(UTC)
        self._query_results = query_results or {}
        self.add = MagicMock(side_effect=self._assign_generated_fields)
        self.commit = MagicMock()

    def query(self, model: type):
        return _FakeQuery(self._query_results.get(model))

    def _assign_generated_fields(self, entity) -> None:
        entity.id = self.id
        entity.uuid = self.uuid
        entity.created_at = self.created_at


@pytest.fixture
def mock_db() -> _MockSession:
    return _MockSession()


@pytest.fixture
def mock_db_class():
    """Fixture that provides the _MockSession class for creating custom mock instances."""
    return _MockSession


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
        self.get_paginator = MagicMock(return_value=MagicMock(paginate=MagicMock(return_value=[])))


@pytest.fixture
def mock_s3_client() -> _MockS3Client:
    return _MockS3Client()
