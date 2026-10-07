from pydantic import BaseModel


class LoginResult(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 It's not a password
