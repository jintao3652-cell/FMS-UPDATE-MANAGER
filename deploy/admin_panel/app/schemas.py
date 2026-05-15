from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    success: bool
    token: str
    expires_in: int
    user: dict


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    email: str | None = Field(default=None, max_length=255)
    role: str = Field(default="user", max_length=32)
    enabled: bool = True


class UserUpdateRequest(BaseModel):
    email: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, max_length=32)
    enabled: bool | None = None


class PasswordUpdateRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class SmtpSettings(BaseModel):
    host: str = ""
    port: int = 465
    username: str = ""
    password: str = ""
    sender: str = ""
    sender_name: str = ""
    use_ssl: bool = True
    use_tls: bool = False
    code_ttl_seconds: int = 600
    code_length: int = 6
    per_email_window_seconds: int = 60
    per_email_daily_limit: int = 5


class SmtpTestRequest(BaseModel):
    recipient: str = Field(min_length=3, max_length=255)


class TurnstileSettings(BaseModel):
    site_key: str = ""
    secret_key: str = ""


class RateLimitSettings(BaseModel):
    login_window_seconds: int = 300
    login_fail_limit: int = 8
    register_attempt_limit: int = 10
    register_attempt_window_seconds: int = 300
    register_per_ip_limit: int = 1
    register_per_ip_window_seconds: int = 86400


class EmailDomainSettings(BaseModel):
    whitelist: list[str] = []
    blacklist: list[str] = []
