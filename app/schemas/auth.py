from pydantic import BaseModel, EmailStr, Field
from typing import Optional

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None


class PasswordRecoveryRequest(BaseModel):
    email: EmailStr


class PasswordRecoveryRequestResult(BaseModel):
    accepted: bool = True
    message: str


class PasswordRecoveryConfirm(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    password: str = Field(min_length=8, max_length=128)


class PasswordRecoveryConfirmResult(BaseModel):
    changed: bool = True
    message: str
