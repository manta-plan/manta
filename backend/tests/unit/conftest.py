from datetime import UTC, datetime
from uuid import uuid4

import pytest


class _StubAdd:
    def __init__(self) -> None:
        self.id = 1
        self.uuid = uuid4()
        self.created_at = datetime.now(UTC)

    def __call__(self, entity) -> None:
        entity.id = self.id
        entity.uuid = self.uuid
        entity.created_at = self.created_at


@pytest.fixture
def stub_add() -> _StubAdd:
    return _StubAdd()
