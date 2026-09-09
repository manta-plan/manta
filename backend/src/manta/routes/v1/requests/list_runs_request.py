from typing import Annotated
from uuid import UUID

from fastapi import Query


class ListRunsRequest:
    def __init__(
        self,
        project_uuid: UUID,
        limit: Annotated[int, Query(ge=1, le=100)] = 10,
        offset: Annotated[int, Query(ge=0)] = 0,
        statuses: Annotated[list[str] | None, Query(alias="status")] = None,
    ) -> None:
        self.project_uuid = project_uuid
        self.limit = limit
        self.offset = offset
        self.statuses = statuses
