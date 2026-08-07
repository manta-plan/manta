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
