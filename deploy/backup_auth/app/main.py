from collections import defaultdict
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr
from hashlib import sha256
from secrets import randbelow
from threading import Lock
import json
import re
import smtplib
import ssl

import httpx
import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from .config import settings
from .database import Base, engine, get_db
from .models import AppSetting, EmailLog, EmailVerificationCode, LoginAudit, User
from .schemas import (
    AdminCreateUserRequest,
    AdminUpdatePasswordRequest,
    AdminUpdateUserRequest,
    LoginRequest,
    LoginResponse,
    MeResponse,
    RegisterCodeRequest,
    RegisterRequest,
)
from .security import create_access_token, decode_access_token, hash_password, verify_password


app = FastAPI(title="FMS Backup Power Auth", version="1.1.0")

origins = ["*"] if settings.allowed_origins == "*" else [x.strip() for x in settings.allowed_origins.split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_fail_bucket: dict[str, list[float]] = defaultdict(list)
_fail_lock = Lock()
MAX_FAIL = 8
WINDOW_SECONDS = 300
_register_attempt_bucket: dict[str, list[float]] = defaultdict(list)
_register_success_bucket: dict[str, list[float]] = defaultdict(list)
_register_lock = Lock()

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
REGISTER_CODE_KEY = "register_code"
SMTP_SETTING_KEY = "smtp"
TURNSTILE_SETTING_KEY = "turnstile"

DEFAULT_SMTP_CONFIG: dict = {
    "host": "",
    "port": 465,
    "username": "",
    "password": "",
    "sender": "",
    "sender_name": "",
    "use_ssl": True,
    "use_tls": False,
    "code_ttl_seconds": 600,
    "code_length": 6,
    "per_email_window_seconds": 60,
    "per_email_daily_limit": 5,
}

DEFAULT_TURNSTILE_CONFIG: dict = {
    "site_key": "",
    "secret_key": "",
}


def _load_json_setting(db: Session, key: str, default: dict) -> dict:
    row = db.get(AppSetting, key)
    if row is None or not row.value:
        return dict(default)
    try:
        data = json.loads(row.value)
    except Exception:
        return dict(default)
    if not isinstance(data, dict):
        return dict(default)
    merged = dict(default)
    merged.update(data)
    return merged


def load_smtp_config(db: Session) -> dict:
    return _load_json_setting(db, SMTP_SETTING_KEY, DEFAULT_SMTP_CONFIG)


def load_turnstile_config(db: Session) -> dict:
    return _load_json_setting(db, TURNSTILE_SETTING_KEY, DEFAULT_TURNSTILE_CONFIG)


def get_register_code_ttl(cfg: dict) -> int:
    try:
        return max(60, int(cfg.get("code_ttl_seconds") or 600))
    except Exception:
        return 600


def normalize_name(name: str) -> str:
    value = str(name or "").strip()
    if not value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid name")
    return value[:64]


def client_ip(req: Request) -> str:
    xff = req.headers.get("x-forwarded-for", "").strip()
    if xff:
        return xff.split(",")[0].strip()
    return req.client.host if req.client else "unknown"


def audit_login(db: Session, username: str, ip: str, user_agent: str, success: bool, detail: str) -> None:
    row = LoginAudit(username=username, ip=ip, user_agent=user_agent[:800], success=success, detail=detail[:1200])
    db.add(row)
    db.commit()


def is_blocked(ip: str) -> bool:
    now_ts = datetime.now(timezone.utc).timestamp()
    with _fail_lock:
        bucket = _fail_bucket[ip]
        _fail_bucket[ip] = [ts for ts in bucket if now_ts - ts <= WINDOW_SECONDS]
        return len(_fail_bucket[ip]) >= MAX_FAIL


def record_fail(ip: str) -> None:
    now_ts = datetime.now(timezone.utc).timestamp()
    with _fail_lock:
        _fail_bucket[ip].append(now_ts)


def clear_fail(ip: str) -> None:
    with _fail_lock:
        _fail_bucket.pop(ip, None)


def allow_register_from_ip(ip: str) -> None:
    now_ts = datetime.now(timezone.utc).timestamp()
    attempt_window = max(1, int(settings.register_attempt_window_seconds))
    attempt_limit = max(1, int(settings.register_attempt_limit))
    success_window = max(1, int(settings.register_per_ip_window_seconds))
    success_limit = max(1, int(settings.register_per_ip_limit))
    with _register_lock:
        _register_attempt_bucket[ip] = [ts for ts in _register_attempt_bucket[ip] if now_ts - ts <= attempt_window]
        _register_success_bucket[ip] = [ts for ts in _register_success_bucket[ip] if now_ts - ts <= success_window]

        if len(_register_success_bucket[ip]) >= success_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="too many registrations from this ip",
            )
        if len(_register_attempt_bucket[ip]) >= attempt_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="too many register attempts",
            )
        _register_attempt_bucket[ip].append(now_ts)


def record_register_success(ip: str) -> None:
    now_ts = datetime.now(timezone.utc).timestamp()
    with _register_lock:
        _register_success_bucket[ip].append(now_ts)


def parse_bearer(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing authorization header")
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid authorization header")
    token = authorization[len(prefix) :].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    return token


def normalize_email(email: str) -> str:
    value = str(email or "").strip().lower()
    if not value or not EMAIL_REGEX.fullmatch(value):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid email")
    return value


def code_hash(code: str) -> str:
    return sha256(f"fms-register:{code}".encode("utf-8")).hexdigest()


def generate_code(length: int = 6) -> str:
    return "".join(str(randbelow(10)) for _ in range(max(4, min(length, 8))))


def verify_turnstile(token: str, ip: str, db: Session) -> None:
    cfg = load_turnstile_config(db)
    secret_key = (cfg.get("secret_key") or "").strip()
    if not secret_key:
        return
    try:
        resp = httpx.post(
            TURNSTILE_VERIFY_URL,
            data={
                "secret": secret_key,
                "response": token,
                "remoteip": ip,
            },
            timeout=15,
        )
        payload = resp.json()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"turnstile verify failed: {exc}") from exc
    if not payload.get("success"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="turnstile verification failed")


def smtp_ready(db: Session) -> bool:
    cfg = load_smtp_config(db)
    return bool(cfg.get("host") and cfg.get("username") and cfg.get("password") and cfg.get("sender"))


def upsert_app_setting(db: Session, key: str, value: str) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    db.commit()


def get_app_setting(db: Session, key: str) -> str:
    row = db.get(AppSetting, key)
    return row.value if row and row.value else ""


def store_verification_code(db: Session, email: str, code: str, ip: str, ttl_seconds: int) -> None:
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    row = db.get(EmailVerificationCode, email)
    if row is None:
        db.add(
            EmailVerificationCode(
                email=email,
                code_hash=code_hash(code),
                expires_at=expires_at,
                attempts=0,
                sent_ip=ip,
            )
        )
    else:
        row.code_hash = code_hash(code)
        row.expires_at = expires_at
        row.attempts = 0
        row.sent_ip = ip
        row.used_at = None
    db.commit()


def send_verification_email(db: Session, recipient: str, code: str) -> None:
    cfg = load_smtp_config(db)
    ttl_seconds = get_register_code_ttl(cfg)
    subject = "FMS 注册验证码"
    text = f"你的注册验证码是 {code}，有效期 {ttl_seconds // 60} 分钟。"
    html = f"""
<div style="font-family:Segoe UI,Arial,sans-serif;padding:24px;background:#f5f7fb;color:#13233b">
  <div style="max-width:520px;margin:0 auto;background:#fff;border-radius:12px;padding:24px">
    <h2 style="margin:0 0 12px;color:#1a73e8">FMS 注册验证码</h2>
    <div style="font-size:32px;font-weight:700;letter-spacing:6px;background:#eef3fb;border-radius:10px;padding:14px 18px;text-align:center">{code}</div>
    <p>有效期 {ttl_seconds // 60} 分钟。</p>
  </div>
</div>
"""
    log = EmailLog(recipient=recipient, subject=subject, purpose=REGISTER_CODE_KEY, success=False, error="", sent_by="system")
    db.add(log)
    db.commit()
    if not (cfg.get("host") and cfg.get("username") and cfg.get("password") and cfg.get("sender")):
        log.error = "smtp not configured"
        db.commit()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="smtp not configured")
    host = cfg["host"]
    port = int(cfg.get("port") or 465)
    username = cfg["username"]
    password = cfg["password"]
    sender = cfg["sender"]
    sender_name = cfg.get("sender_name") or ""
    use_ssl = bool(cfg.get("use_ssl"))
    use_tls = bool(cfg.get("use_tls"))
    msg = EmailMessage()
    msg["From"] = formataddr((sender_name, sender)) if sender else username
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    try:
        if use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, timeout=15, context=context) as client:
                client.login(username, password)
                client.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=15) as client:
                client.ehlo()
                if use_tls:
                    context = ssl.create_default_context()
                    client.starttls(context=context)
                    client.ehlo()
                client.login(username, password)
                client.send_message(msg)
        log.success = True
        db.commit()
    except Exception as exc:
        log.error = str(exc)[:1000]
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="email send failed") from exc


def ensure_schema_compat() -> None:
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("users")}
    with engine.begin() as conn:
        if "email" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(255) NULL"))
        try:
            conn.execute(text("CREATE UNIQUE INDEX uq_users_email ON users (email)"))
        except Exception:
            pass
        if "app_settings" not in inspector.get_table_names():
            conn.execute(text("CREATE TABLE IF NOT EXISTS app_settings (key VARCHAR(64) PRIMARY KEY, value TEXT NOT NULL, updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP)"))
        if "email_log" not in inspector.get_table_names():
            conn.execute(text("CREATE TABLE IF NOT EXISTS email_log (id INT PRIMARY KEY AUTO_INCREMENT, recipient VARCHAR(255) NOT NULL, subject VARCHAR(255) NOT NULL DEFAULT '', purpose VARCHAR(64) NOT NULL DEFAULT '', success BOOLEAN NOT NULL, error TEXT NOT NULL, sent_by VARCHAR(64) NOT NULL DEFAULT '', created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"))
        if "email_verification_codes" not in inspector.get_table_names():
            conn.execute(text("CREATE TABLE IF NOT EXISTS email_verification_codes (email VARCHAR(255) PRIMARY KEY, code_hash VARCHAR(128) NOT NULL, expires_at DATETIME NOT NULL, attempts INT NOT NULL DEFAULT 0, sent_ip VARCHAR(64) NOT NULL DEFAULT '', created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, used_at DATETIME NULL)"))


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    token = parse_bearer(authorization)
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"invalid token: {exc}") from exc
    username = str(payload.get("sub", "")).strip()
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token payload")
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not user.enabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin required")
    return user


def sync_config_admin(db: Session) -> None:
    username = settings.admin_username.strip()
    password = settings.admin_password
    if not username or not password:
        return
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        db.add(
            User(
                username=username,
                password_hash=hash_password(password),
                role="admin",
                enabled=True,
            )
        )
        db.commit()
        return
    changed = False
    if user.role != "admin":
        user.role = "admin"
        changed = True
    if not user.enabled:
        user.enabled = True
        changed = True
    if not verify_password(password, user.password_hash):
        user.password_hash = hash_password(password)
        changed = True
    if changed:
        db.commit()


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_schema_compat()
    with Session(engine) as db:
        sync_config_admin(db)


@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "fms-backup-auth"}


@app.get("/api/public/turnstile_site_key")
def public_turnstile_site_key(db: Session = Depends(get_db)):
    cfg = load_turnstile_config(db)
    return {"site_key": (cfg.get("site_key") or "").strip()}



@app.post("/api/auth/register/code")
def register_code(body: RegisterCodeRequest, req: Request, db: Session = Depends(get_db)):
    ip = client_ip(req)
    allow_register_from_ip(ip)
    name = normalize_name(body.name)
    email = normalize_email(body.email)
    verify_turnstile(body.turnstile_token, ip, db)
    if db.scalar(select(User).where(User.username == name)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="name already exists")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already exists")
    code = generate_code(6)
    smtp_cfg = load_smtp_config(db)
    store_verification_code(db, email, code, ip, get_register_code_ttl(smtp_cfg))
    send_verification_email(db, email, code)
    return {"success": True, "message": "verification code sent"}



@app.post("/api/auth/login", response_model=LoginResponse)
def login(body: LoginRequest, req: Request, db: Session = Depends(get_db)):
    ip = client_ip(req)
    ua = req.headers.get("user-agent", "")
    if is_blocked(ip):
        audit_login(db, body.username, ip, ua, False, "rate limited")
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="too many login attempts")
    user = db.scalar(select(User).where(User.username == body.username))
    if user is None or not user.enabled or not verify_password(body.password, user.password_hash):
        record_fail(ip)
        audit_login(db, body.username, ip, ua, False, "invalid credentials")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    clear_fail(ip)
    token, expires_in = create_access_token(subject=user.username, role=user.role)
    audit_login(db, user.username, ip, ua, True, "login ok")
    return LoginResponse(
        success=True,
        message="ok",
        token=token,
        expires_in=expires_in,
        user={"username": user.username, "role": user.role, "email": user.email or ""},
    )


@app.post("/api/auth/register")
def register(body: RegisterRequest, req: Request, db: Session = Depends(get_db)):
    ip = client_ip(req)
    allow_register_from_ip(ip)
    name = normalize_name(body.name)
    email = normalize_email(body.email)
    verify_turnstile(body.turnstile_token, ip, db)
    if db.scalar(select(User).where(User.username == name)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="name already exists")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already exists")
    code_row = db.get(EmailVerificationCode, email)
    if code_row is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="verification code not found")
    if code_row.used_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="verification code already used")
    if code_row.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="verification code expired")
    if code_row.attempts >= 5:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="too many verification attempts")
    if code_row.code_hash != code_hash(body.email_code.strip()):
        code_row.attempts += 1
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid verification code")
    code_row.used_at = datetime.now(timezone.utc)
    db.add(User(username=name, email=email, password_hash=hash_password(body.password), role="user", enabled=True))
    db.commit()
    record_register_success(ip)
    return {"success": True, "message": "register ok"}


@app.get("/api/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user)):
    return MeResponse(success=True, user={"username": user.username, "role": user.role, "email": user.email or ""})


@app.get("/api/admin/users")
def admin_list_users(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.scalars(select(User).order_by(User.id.asc())).all()
    return {
        "success": True,
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "role": u.role,
                "enabled": u.enabled,
                "created_at": u.created_at.isoformat(),
            }
            for u in users
        ],
    }


@app.post("/api/admin/users")
def admin_create_user(body: AdminCreateUserRequest, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    username = body.username.strip()
    if not username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid username")
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username already exists")
    email = normalize_email(body.email) if body.email else None
    if email and db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already exists")
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(body.password),
        role=body.role.strip() or "user",
        enabled=bool(body.enabled),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"success": True, "message": "user created", "id": user.id}


@app.patch("/api/admin/users/{user_id}")
def admin_update_user(user_id: int, body: AdminUpdateUserRequest, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    if body.email is not None:
        email = normalize_email(body.email) if body.email else None
        if email and db.scalar(select(User).where(User.email == email, User.id != user_id)):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already exists")
        user.email = email
    if body.role is not None:
        user.role = body.role.strip() or user.role
    if body.enabled is not None:
        user.enabled = bool(body.enabled)
    db.commit()
    return {"success": True, "message": "user updated"}


@app.patch("/api/admin/users/{user_id}/password")
def admin_update_password(user_id: int, body: AdminUpdatePasswordRequest, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    user.password_hash = hash_password(body.password)
    db.commit()
    return {"success": True, "message": "password updated"}


@app.delete("/api/admin/users/{user_id}")
def admin_delete_user(user_id: int, admin_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    if user.username == admin_user.username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cannot delete current admin")
    db.delete(user)
    db.commit()
    return {"success": True, "message": "user deleted"}
