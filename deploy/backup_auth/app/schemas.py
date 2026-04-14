from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    client: str | None = None
    timestamp: str | None = None


class LoginResponse(BaseModel):
    success: bool
    message: str
    token: str
    expires_in: int
    user: dict


class MeResponse(BaseModel):
    success: bool
    user: dict


class SendEmailCodeRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    email: str = Field(min_length=5, max_length=255)
    code: str = Field(min_length=4, max_length=8)


class AdminCreateUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    email: str | None = Field(default=None, max_length=255)
    role: str = Field(default="user", max_length=32)
    enabled: bool = True


class AdminUpdatePasswordRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class AdminUpdateUserRequest(BaseModel):
    email: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, max_length=32)
    enabled: bool | None = None
