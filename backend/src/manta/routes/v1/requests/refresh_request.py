from pydantic import BaseModel


class RefreshRequest(BaseModel):
    refresh_token: str
