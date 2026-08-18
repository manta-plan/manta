from pydantic import BaseModel


class UploadS3FileResult(BaseModel):
    key: str
    size: int
