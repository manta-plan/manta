from collections.abc import Iterable
from datetime import datetime

from pydantic import BaseModel


class UploadS3FileResult(BaseModel):
    key: str
    size: int


class GetS3FileResult(BaseModel):
    key: str
    size: int
    last_modified: datetime


class GetS3FileContentResult(GetS3FileResult):
    content_type: str
    content: Iterable[bytes]
    """The file's bytes, streamed from S3 chunk by chunk as this is iterated — never
    read in whole. Iterate it once: it is consumed as it goes."""
