from pydantic import BaseModel


class LogoutRequest(BaseModel):
    refresh_token: str
