from datetime import datetime, timedelta, timezone
import hashlib

import jwt
from passlib.context import CryptContext

from .config import settings


_INSECURE_SECRETS = {"change_me", "changeme", "secret", ""}
if settings.jwt_secret.strip().lower() in _INSECURE_SECRETS or len(settings.jwt_secret) < 16:
    import sys as _sys
    print(
        f"[SECURITY] APP_JWT_SECRET is unset/default/too short (len={len(settings.jwt_secret)}). "
        f"Refusing to start. Set a strong APP_JWT_SECRET (>=32 random chars).",
        file=_sys.stderr,
    )
    raise SystemExit(2)


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _normalize_secret(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    return pwd_context.hash(_normalize_secret(password))


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return pwd_context.verify(_normalize_secret(password), password_hash)
    except Exception:
        return False


def create_access_token(subject: str, role: str) -> tuple[str, int]:
    expires_delta = timedelta(minutes=settings.jwt_expire_minutes)
    expire_at = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": subject,
        "role": role,
        "typ": "access",
        "exp": expire_at,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, int(expires_delta.total_seconds())


def create_refresh_token(subject: str, role: str) -> tuple[str, int]:
    days = max(1, int(getattr(settings, "refresh_token_expire_days", 30)))
    expires_delta = timedelta(days=days)
    expire_at = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": subject,
        "role": role,
        "typ": "refresh",
        "exp": expire_at,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, int(expires_delta.total_seconds())


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


def decode_refresh_token(token: str) -> dict:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    if str(payload.get("typ", "")) != "refresh":
        raise jwt.InvalidTokenError("not a refresh token")
    return payload


_COMMON_PASSWORDS = {
    "password", "passw0rd", "12345678", "123456789", "1234567890",
    "qwerty123", "abc12345", "111111111", "00000000", "letmein123",
    "password1", "admin1234", "iloveyou1",
}


def password_strength_problems(pw: str) -> list[str]:
    problems: list[str] = []
    pw = str(pw or "")
    if len(pw) < 8:
        problems.append("密码长度至少 8 位。")
    if len(pw) > 256:
        problems.append("密码长度过长。")
    classes = 0
    if any(c.islower() for c in pw):
        classes += 1
    if any(c.isupper() for c in pw):
        classes += 1
    if any(c.isdigit() for c in pw):
        classes += 1
    if any((not c.isalnum()) and (not c.isspace()) for c in pw):
        classes += 1
    if classes < 2:
        problems.append("密码须至少包含 2 类字符（大写字母 / 小写字母 / 数字 / 符号）。")
    if pw.lower() in _COMMON_PASSWORDS:
        problems.append("密码过于常见，请换一个。")
    return problems


def assert_password_strong(pw: str) -> None:
    problems = password_strength_problems(pw)
    if problems:
        raise ValueError(" ".join(problems))
