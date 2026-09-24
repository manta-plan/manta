from typing import Literal

from pydantic import BaseModel

PlaybookStatus = Literal["available", "coming_soon"]


class PlaybookNodeConfigField(BaseModel):
    key: str
    label: str
    type: Literal["integer"]
    required: bool
    min: int | None = None
    default: int | None = None


class PlaybookNode(BaseModel):
    id: str
    type: str
    label: str
    config: list[PlaybookNodeConfigField]


class PlaybookSummaryResult(BaseModel):
    id: str
    name: str
    description: str
    status: PlaybookStatus


class PlaybookDetailResult(PlaybookSummaryResult):
    nodes: list[PlaybookNode]


class ListPlaybooksResult(BaseModel):
    items: list[PlaybookSummaryResult]
