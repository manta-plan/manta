from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from keycloak import KeycloakOpenID


class _FakeQuery:
    """Returns canned results and records the clauses it was given, so tests can
    check which filters/ordering a service built (it does not execute them)."""

    def __init__(self, result) -> None:
        self._result = result
        self.filters: list = []
        self.order_by_args: tuple = ()
        self.offset_value: int | None = None
        self.limit_value: int | None = None

    def filter(self, *args, **_kwargs):
        self.filters.extend(args)
        return self

    def order_by(self, *args, **_kwargs):
        self.order_by_args = args
        return self

    def offset(self, value, *_args, **_kwargs):
        self.offset_value = value
        return self

    def limit(self, value, *_args, **_kwargs):
        self.limit_value = value
        return self

    def one_or_none(self):
        return self._result

    def all(self):
        if isinstance(self._result, list):
            return self._result
        return []

    def count(self):
        if isinstance(self._result, list):
            return len(self._result)
        return 0


class _MockSession:
    def __init__(self, query_results: dict[type, object] | None = None) -> None:
        self.id = 1
        self.uuid = uuid4()
        self.created_at = datetime.now(UTC)
        self._query_results = query_results or {}
        self.add = MagicMock(side_effect=self._assign_generated_fields)
        self.commit = MagicMock()
        self.flush = MagicMock()
        self.delete = MagicMock()

    def query(self, model: type) -> _FakeQuery:
        self.last_query = _FakeQuery(self._query_results.get(model))
        return self.last_query

    def _assign_generated_fields(self, entity) -> None:
        entity.id = self.id
        entity.uuid = self.uuid
        entity.created_at = self.created_at
        entity.updated_at = self.created_at


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
        self.get_object = MagicMock()
        self.head_object = MagicMock(
            return_value={"ContentLength": 0, "LastModified": datetime.now(UTC)}
        )
        self.head_bucket = MagicMock()
        self.create_bucket = MagicMock()
        self.delete_object = MagicMock()
        self.delete_objects = MagicMock(return_value={})
        self.get_paginator = MagicMock(return_value=MagicMock(paginate=MagicMock(return_value=[])))


@pytest.fixture
def mock_s3_client() -> _MockS3Client:
    return _MockS3Client()


@pytest.fixture
def mock_kc_client() -> MagicMock:
    return MagicMock(spec=KeycloakOpenID)
