from pydantic import BaseModel


class RegisterRequest(BaseModel):
    username: str
    idp_subject: str
    idp_source: str
