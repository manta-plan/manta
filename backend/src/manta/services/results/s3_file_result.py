from datetime import datetime

from pydantic import BaseModel


class UploadS3FileResult(BaseModel):
    key: str
    size: int


class GetS3FileResult(BaseModel):
    key: str
    size: int
    last_modified: datetime
