from collections import defaultdict
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr
from hashlib import sha256
from secrets import randbelow
from threading import Lock
import json
import os
import re
import smtplib
import ssl
import time

import httpx
import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from .config import settings
from .database import Base, engine, get_db
from .models import AppSetting, CrashReport, CycleNotificationState, CycleSubscription, EmailLog, EmailOutbox, EmailVerificationCode, InviteCode, LoginAudit, PasswordResetCode, User
from .schemas import (
    AdminCreateUserRequest,
    AdminUpdatePasswordRequest,
    AdminUpdateUserRequest,
    LoginRequest,
    LoginResponse,
    MeResponse,
    PasswordResetCodeRequest,
    PasswordResetRequest,
    RegisterCodeRequest,
    RegisterRequest,
)
from .security import assert_password_strong, create_access_token, create_refresh_token, decode_access_token, decode_refresh_token, hash_password, verify_password


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

_turnstile_used_tokens: dict[str, float] = {}
_turnstile_token_lock = Lock()
TURNSTILE_TOKEN_TTL = 600

_code_send_ip_last: dict[str, float] = {}
_code_send_email_last: dict[str, float] = {}
_code_send_lock = Lock()
CODE_SEND_PER_IP_COOLDOWN = 60

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


RATE_LIMIT_KEY = "rate_limits"
DEFAULT_RATE_LIMITS: dict = {
    "login_window_seconds": 300,
    "login_fail_limit": 8,
    "register_attempt_limit": 10,
    "register_attempt_window_seconds": 300,
    "register_per_ip_limit": 1,
    "register_per_ip_window_seconds": 86400,
    "code_send_per_ip_cooldown": 60,
    "crash_rate_window_seconds": 60,
    "crash_rate_limit": 20,
}

REGISTER_POLICY_KEY = "register_policy"
DEFAULT_REGISTER_POLICY: dict = {
    "require_invite_code": False,
    "require_admin_approval": False,
}


def load_register_policy(db: Session) -> dict:
    return _load_json_setting(db, REGISTER_POLICY_KEY, DEFAULT_REGISTER_POLICY)


def load_rate_limits(db: Session) -> dict:
    """Read rate limits from app_settings, falling back to env vars then defaults.
    Lets the admin panel tune limits without restarting the service.
    """
    cfg = _load_json_setting(db, RATE_LIMIT_KEY, DEFAULT_RATE_LIMITS)
    cfg.setdefault("register_attempt_limit", int(getattr(settings, "register_attempt_limit", 10)))
    cfg.setdefault("register_attempt_window_seconds", int(getattr(settings, "register_attempt_window_seconds", 300)))
    cfg.setdefault("register_per_ip_limit", int(getattr(settings, "register_per_ip_limit", 1)))
    cfg.setdefault("register_per_ip_window_seconds", int(getattr(settings, "register_per_ip_window_seconds", 86400)))
    return cfg


def get_register_code_ttl(cfg: dict) -> int:
    try:
        return max(60, int(cfg.get("code_ttl_seconds") or 600))
    except Exception:
        return 600


def ensure_utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


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


def is_blocked(ip: str, db: Session | None = None) -> bool:
    now_ts = datetime.now(timezone.utc).timestamp()
    if db is not None:
        cfg = load_rate_limits(db)
        window = max(1, int(cfg.get("login_window_seconds") or WINDOW_SECONDS))
        limit = max(1, int(cfg.get("login_fail_limit") or MAX_FAIL))
    else:
        window, limit = WINDOW_SECONDS, MAX_FAIL
    with _fail_lock:
        bucket = _fail_bucket[ip]
        _fail_bucket[ip] = [ts for ts in bucket if now_ts - ts <= window]
        return len(_fail_bucket[ip]) >= limit


def record_fail(ip: str) -> None:
    now_ts = datetime.now(timezone.utc).timestamp()
    with _fail_lock:
        _fail_bucket[ip].append(now_ts)


def clear_fail(ip: str) -> None:
    with _fail_lock:
        _fail_bucket.pop(ip, None)


def allow_register_from_ip(ip: str, db: Session | None = None) -> None:
    now_ts = datetime.now(timezone.utc).timestamp()
    if db is not None:
        cfg = load_rate_limits(db)
        attempt_window = max(1, int(cfg.get("register_attempt_window_seconds") or 300))
        attempt_limit = max(1, int(cfg.get("register_attempt_limit") or 10))
        success_window = max(1, int(cfg.get("register_per_ip_window_seconds") or 86400))
        success_limit = max(1, int(cfg.get("register_per_ip_limit") or 1))
    else:
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
    token = (token or "").strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="turnstile token missing")
    now_ts = time.time()
    with _turnstile_token_lock:
        for k in [k for k, ts in _turnstile_used_tokens.items() if now_ts - ts > TURNSTILE_TOKEN_TTL]:
            _turnstile_used_tokens.pop(k, None)
        if token in _turnstile_used_tokens:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="turnstile token already used")
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
    with _turnstile_token_lock:
        _turnstile_used_tokens[token] = now_ts


def enforce_code_send_cooldown(ip: str, email: str, per_email_window: int, db: Session | None = None) -> None:
    now_ts = time.time()
    ip_cooldown = CODE_SEND_PER_IP_COOLDOWN
    if db is not None:
        try:
            ip_cooldown = max(1, int(load_rate_limits(db).get("code_send_per_ip_cooldown") or CODE_SEND_PER_IP_COOLDOWN))
        except Exception:
            pass
    with _code_send_lock:
        for k in [k for k, ts in _code_send_ip_last.items() if now_ts - ts > max(ip_cooldown, per_email_window) * 2]:
            _code_send_ip_last.pop(k, None)
        for k in [k for k, ts in _code_send_email_last.items() if now_ts - ts > max(ip_cooldown, per_email_window) * 2]:
            _code_send_email_last.pop(k, None)
        last_ip = _code_send_ip_last.get(ip, 0.0)
        if last_ip and now_ts - last_ip < ip_cooldown:
            wait = int(ip_cooldown - (now_ts - last_ip))
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=f"please wait {wait}s before requesting another code")
        last_email = _code_send_email_last.get(email, 0.0)
        if last_email and now_ts - last_email < per_email_window:
            wait = int(per_email_window - (now_ts - last_email))
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=f"please wait {wait}s before requesting another code for this email")


def record_code_send(ip: str, email: str) -> None:
    now_ts = time.time()
    with _code_send_lock:
        _code_send_ip_last[ip] = now_ts
        _code_send_email_last[email] = now_ts


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


def _smtp_send_now(cfg: dict, recipient: str, subject: str, body_text: str, body_html: str) -> None:
    """Synchronously send one email. Raises on any SMTP failure."""
    if not (cfg.get("host") and cfg.get("username") and cfg.get("password") and cfg.get("sender")):
        raise RuntimeError("smtp not configured")
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
    msg.set_content(body_text or "")
    if body_html:
        msg.add_alternative(body_html, subtype="html")
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


OUTBOX_BACKOFF_SECONDS = [30, 120, 600, 1800, 3600]  # 30s, 2m, 10m, 30m, 1h
OUTBOX_MAX_ATTEMPTS = len(OUTBOX_BACKOFF_SECONDS)


def queue_email(db: Session, *, recipient: str, subject: str, purpose: str, body_text: str, body_html: str) -> EmailOutbox:
    row = EmailOutbox(
        recipient=recipient,
        subject=subject,
        purpose=purpose,
        body_text=body_text,
        body_html=body_html,
        status="pending",
        attempts=0,
        next_attempt_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _outbox_log_attempt(db: Session, recipient: str, subject: str, purpose: str, success: bool, error: str) -> None:
    db.add(EmailLog(recipient=recipient, subject=subject, purpose=purpose, success=success, error=error[:1000], sent_by="outbox"))
    db.commit()


def process_outbox_once(max_items: int = 20) -> int:
    """Attempt to send up to N pending outbox rows whose next_attempt_at <= now.
    Returns count of rows attempted.
    """
    from .database import SessionLocal
    sent = 0
    with SessionLocal() as db:
        rows = db.scalars(
            select(EmailOutbox)
            .where(EmailOutbox.status == "pending", EmailOutbox.next_attempt_at <= datetime.utcnow())
            .order_by(EmailOutbox.next_attempt_at.asc())
            .limit(max_items)
        ).all()
        if not rows:
            return 0
        cfg = load_smtp_config(db)
        for row in rows:
            row.attempts += 1
            try:
                _smtp_send_now(cfg, row.recipient, row.subject, row.body_text, row.body_html)
                row.status = "sent"
                row.sent_at = datetime.utcnow()
                row.last_error = ""
                _outbox_log_attempt(db, row.recipient, row.subject, row.purpose, True, "")
            except Exception as exc:
                row.last_error = str(exc)[:2000]
                _outbox_log_attempt(db, row.recipient, row.subject, row.purpose, False, str(exc))
                if row.attempts >= OUTBOX_MAX_ATTEMPTS:
                    row.status = "failed"
                else:
                    backoff = OUTBOX_BACKOFF_SECONDS[min(row.attempts - 1, OUTBOX_MAX_ATTEMPTS - 1)]
                    row.next_attempt_at = datetime.utcnow() + timedelta(seconds=backoff)
            db.commit()
            sent += 1
    return sent


_outbox_worker_started = False
_outbox_worker_lock = Lock()

# --- worker health state (#56) ---
_worker_health: dict[str, dict] = {
    "outbox": {"last_run_at": "", "last_ok_at": "", "last_error": "", "iterations": 0, "errors": 0, "last_processed": 0},
    "cycle": {"last_run_at": "", "last_ok_at": "", "last_error": "", "iterations": 0, "errors": 0, "last_processed": 0},
}
_worker_health_lock = Lock()


def _record_worker_run(name: str, processed: int = 0, error: str = "") -> None:
    now = datetime.utcnow().isoformat()
    with _worker_health_lock:
        s = _worker_health.setdefault(name, {"last_run_at": "", "last_ok_at": "", "last_error": "", "iterations": 0, "errors": 0, "last_processed": 0})
        s["last_run_at"] = now
        s["iterations"] += 1
        s["last_processed"] = int(processed)
        if error:
            s["last_error"] = error[:500]
            s["errors"] += 1
        else:
            s["last_ok_at"] = now


def _outbox_worker_loop() -> None:
    while True:
        try:
            n = process_outbox_once()
            _record_worker_run("outbox", processed=n)
        except Exception as exc:
            _record_worker_run("outbox", error=f"{type(exc).__name__}: {exc}")
        time.sleep(15)


def start_outbox_worker() -> None:
    global _outbox_worker_started
    with _outbox_worker_lock:
        if _outbox_worker_started:
            return
        _outbox_worker_started = True
    import threading
    t = threading.Thread(target=_outbox_worker_loop, name="email-outbox-worker", daemon=True)
    t.start()


def send_verification_email(db: Session, recipient: str, code: str) -> None:
    """Queue a verification code email and attempt one immediate send.
    If immediate send fails, the row stays in the outbox and the worker retries.
    The caller is NOT informed about a transient SMTP failure (response still 200)
    so the user is not blocked — they will receive the mail when SMTP recovers.
    """
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
    row = queue_email(db, recipient=recipient, subject=subject, purpose=REGISTER_CODE_KEY, body_text=text, body_html=html)
    if not (cfg.get("host") and cfg.get("username") and cfg.get("password") and cfg.get("sender")):
        row.last_error = "smtp not configured"
        row.status = "pending"
        db.commit()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="smtp not configured")
    try:
        _smtp_send_now(cfg, recipient, subject, text, html)
        row.status = "sent"
        row.sent_at = datetime.utcnow()
        row.attempts = 1
        db.commit()
        _outbox_log_attempt(db, recipient, subject, REGISTER_CODE_KEY, True, "")
    except Exception as exc:
        row.attempts = 1
        row.last_error = str(exc)[:2000]
        backoff = OUTBOX_BACKOFF_SECONDS[0]
        row.next_attempt_at = datetime.utcnow() + timedelta(seconds=backoff)
        db.commit()
        _outbox_log_attempt(db, recipient, subject, REGISTER_CODE_KEY, False, str(exc))


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
    start_outbox_worker()
    start_cycle_worker()


@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "fms-backup-auth"}


@app.get("/api/public/turnstile_site_key")
def public_turnstile_site_key(db: Session = Depends(get_db)):
    cfg = load_turnstile_config(db)
    return {"site_key": (cfg.get("site_key") or "").strip()}


@app.get("/api/public/register_policy")
def public_register_policy(db: Session = Depends(get_db)):
    """The register page reads this to decide whether to show the invite-code field
    and to display an 'awaiting approval' message after submit."""
    return load_register_policy(db)



@app.post("/api/auth/register/code")
def register_code(body: RegisterCodeRequest, req: Request, db: Session = Depends(get_db)):
    ip = client_ip(req)
    allow_register_from_ip(ip, db)
    name = normalize_name(body.name)
    email = normalize_email(body.email)
    smtp_cfg = load_smtp_config(db)
    try:
        per_email_window = max(10, int(smtp_cfg.get("per_email_window_seconds") or 60))
    except Exception:
        per_email_window = 60
    enforce_code_send_cooldown(ip, email, per_email_window, db)
    verify_turnstile(body.turnstile_token, ip, db)
    if db.scalar(select(User).where(User.username == name)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="name already exists")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already exists")
    code = generate_code(6)
    store_verification_code(db, email, code, ip, get_register_code_ttl(smtp_cfg))
    send_verification_email(db, email, code)
    record_code_send(ip, email)
    return {"success": True, "message": "verification code sent"}



@app.post("/api/auth/login", response_model=LoginResponse)
def login(body: LoginRequest, req: Request, db: Session = Depends(get_db)):
    ip = client_ip(req)
    ua = req.headers.get("user-agent", "")
    if is_blocked(ip, db):
        audit_login(db, body.username, ip, ua, False, "rate limited")
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="too many login attempts")
    user = db.scalar(select(User).where(User.username == body.username))
    if user is None or not user.enabled or not verify_password(body.password, user.password_hash):
        record_fail(ip)
        audit_login(db, body.username, ip, ua, False, "invalid credentials")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    clear_fail(ip)
    token, expires_in = create_access_token(subject=user.username, role=user.role)
    refresh_token, refresh_expires_in = create_refresh_token(subject=user.username, role=user.role)
    audit_login(db, user.username, ip, ua, True, "login ok")
    return LoginResponse(
        success=True,
        message="ok",
        token=token,
        expires_in=expires_in,
        refresh_token=refresh_token,
        refresh_expires_in=refresh_expires_in,
        user={"username": user.username, "role": user.role, "email": user.email or ""},
    )


@app.post("/api/auth/refresh")
async def refresh_token_endpoint(req: Request, db: Session = Depends(get_db)):
    try:
        body = await req.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid json")
    refresh = str((body or {}).get("refresh_token", "")).strip()
    if not refresh:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="refresh_token required")
    try:
        payload = decode_refresh_token(refresh)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"invalid refresh token: {exc}") from exc
    username = str(payload.get("sub", "")).strip()
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not user.enabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found or disabled")
    token, expires_in = create_access_token(subject=user.username, role=user.role)
    return {
        "success": True,
        "token": token,
        "expires_in": expires_in,
        "user": {"username": user.username, "role": user.role, "email": user.email or ""},
    }


@app.post("/api/auth/register")
def register(body: RegisterRequest, req: Request, db: Session = Depends(get_db)):
    ip = client_ip(req)
    allow_register_from_ip(ip, db)
    name = normalize_name(body.name)
    email = normalize_email(body.email)
    try:
        assert_password_strong(body.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    verify_turnstile(body.turnstile_token, ip, db)
    policy = load_register_policy(db)

    invite_row: InviteCode | None = None
    if bool(policy.get("require_invite_code")):
        raw_code = str(body.invite_code or "").strip()
        if not raw_code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invite code required")
        invite_row = db.scalar(select(InviteCode).where(InviteCode.code == raw_code))
        if invite_row is None or not invite_row.enabled:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid invite code")
        exp = ensure_utc(invite_row.expires_at)
        if exp is not None and exp <= datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invite code expired")
        if invite_row.used_count >= invite_row.max_uses:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invite code exhausted")

    if db.scalar(select(User).where(User.username == name)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="name already exists")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already exists")
    code_row = db.get(EmailVerificationCode, email)
    if code_row is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="verification code not found")
    if code_row.used_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="verification code already used")
    expires_at = ensure_utc(code_row.expires_at)
    if expires_at is None or expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="verification code expired")
    if code_row.attempts >= 5:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="too many verification attempts")
    if code_row.code_hash != code_hash(body.email_code.strip()):
        code_row.attempts += 1
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid verification code")
    code_row.used_at = datetime.now(timezone.utc)
    enabled = not bool(policy.get("require_admin_approval"))
    db.add(User(username=name, email=email, password_hash=hash_password(body.password), role="user", enabled=enabled))
    if invite_row is not None:
        invite_row.used_count += 1
    db.commit()
    record_register_success(ip)
    return {
        "success": True,
        "message": "register ok" if enabled else "register pending admin approval",
        "enabled": enabled,
        "pending_approval": not enabled,
    }


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
                "created_at": ensure_utc(u.created_at).isoformat() if u.created_at else "",
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
    try:
        assert_password_strong(body.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
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
    try:
        assert_password_strong(body.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
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



_crash_bucket: dict[str, list[float]] = defaultdict(list)
_crash_bucket_lock = Lock()
CRASH_RATE_WINDOW_SEC = 60
CRASH_RATE_LIMIT = 20


def _crash_rate_ok(ip: str, db: Session | None = None) -> bool:
    now = time.time()
    window, limit = CRASH_RATE_WINDOW_SEC, CRASH_RATE_LIMIT
    if db is not None:
        try:
            cfg = load_rate_limits(db)
            window = max(1, int(cfg.get("crash_rate_window_seconds") or CRASH_RATE_WINDOW_SEC))
            limit = max(1, int(cfg.get("crash_rate_limit") or CRASH_RATE_LIMIT))
        except Exception:
            pass
    with _crash_bucket_lock:
        bucket = _crash_bucket[ip]
        bucket[:] = [t for t in bucket if now - t < window]
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True


@app.post("/api/crash")
async def api_crash_report(req: Request, db: Session = Depends(get_db)):
    ip = client_ip(req)
    if not _crash_rate_ok(ip, db):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limited")
    try:
        body = await req.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid json")
    if not isinstance(body, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid payload")
    def s(k: str, n: int) -> str:
        return str(body.get(k, ""))[:n]
    rec = CrashReport(
        install_id=s("install_id", 64),
        app=s("app", 64),
        version=s("version", 32),
        kind=s("kind", 32),
        exc_type=s("exc_type", 128),
        exc_msg=s("exc_msg", 8000),
        traceback=s("traceback", 60000),
        platform=s("platform", 255),
        python=s("python", 32),
        extra=json.dumps(body.get("extra") or {}, ensure_ascii=False)[:8000],
        client_ts=s("ts", 64),
        ip=ip,
    )
    db.add(rec)
    db.commit()
    return {"success": True, "id": rec.id}


@app.get("/api/admin/crashes")
def admin_list_crashes(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = 100,
    offset: int = 0,
    version: str | None = None,
    exc_type: str | None = None,
):
    q = select(CrashReport).order_by(CrashReport.id.desc())
    if version:
        q = q.where(CrashReport.version == version.strip())
    if exc_type:
        q = q.where(CrashReport.exc_type == exc_type.strip())
    q = q.limit(max(1, min(int(limit or 100), 500))).offset(max(0, int(offset or 0)))
    rows = db.scalars(q).all()
    return {
        "items": [
            {
                "id": r.id,
                "install_id": r.install_id,
                "app": r.app,
                "version": r.version,
                "kind": r.kind,
                "exc_type": r.exc_type,
                "exc_msg": r.exc_msg,
                "platform": r.platform,
                "python": r.python,
                "client_ts": r.client_ts,
                "ip": r.ip,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ]
    }


@app.get("/api/admin/crashes/{crash_id}")
def admin_get_crash(crash_id: int, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    r = db.get(CrashReport, crash_id)
    if r is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    return {
        "id": r.id,
        "install_id": r.install_id,
        "app": r.app,
        "version": r.version,
        "kind": r.kind,
        "exc_type": r.exc_type,
        "exc_msg": r.exc_msg,
        "traceback": r.traceback,
        "platform": r.platform,
        "python": r.python,
        "extra": r.extra,
        "client_ts": r.client_ts,
        "ip": r.ip,
        "created_at": r.created_at.isoformat() if r.created_at else "",
    }


@app.get("/api/admin/outbox")
def admin_list_outbox(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = 100,
    offset: int = 0,
    status_filter: str | None = None,
):
    q = select(EmailOutbox).order_by(EmailOutbox.id.desc())
    if status_filter and status_filter in {"pending", "sent", "failed"}:
        q = q.where(EmailOutbox.status == status_filter)
    q = q.limit(max(1, min(int(limit or 100), 500))).offset(max(0, int(offset or 0)))
    rows = db.scalars(q).all()
    return {
        "items": [
            {
                "id": r.id,
                "recipient": r.recipient,
                "subject": r.subject,
                "purpose": r.purpose,
                "status": r.status,
                "attempts": r.attempts,
                "next_attempt_at": r.next_attempt_at.isoformat() if r.next_attempt_at else "",
                "last_error": r.last_error,
                "created_at": r.created_at.isoformat() if r.created_at else "",
                "sent_at": r.sent_at.isoformat() if r.sent_at else "",
            }
            for r in rows
        ]
    }


@app.post("/api/admin/outbox/{outbox_id}/retry")
def admin_retry_outbox(outbox_id: int, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.get(EmailOutbox, outbox_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    if row.status == "sent":
        return {"success": True, "message": "already sent"}
    row.status = "pending"
    row.next_attempt_at = datetime.utcnow()
    db.commit()
    return {"success": True, "message": "queued for retry"}


@app.get("/api/admin/register_policy")
def admin_get_register_policy(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return {"success": True, "policy": load_register_policy(db)}


@app.put("/api/admin/register_policy")
async def admin_put_register_policy(req: Request, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        body = await req.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid json")
    if not isinstance(body, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid payload")
    cfg = {
        "require_invite_code": bool(body.get("require_invite_code", False)),
        "require_admin_approval": bool(body.get("require_admin_approval", False)),
    }
    row = db.get(AppSetting, REGISTER_POLICY_KEY)
    if row is None:
        db.add(AppSetting(key=REGISTER_POLICY_KEY, value=json.dumps(cfg, ensure_ascii=False)))
    else:
        row.value = json.dumps(cfg, ensure_ascii=False)
    db.commit()
    return {"success": True, "policy": cfg}


@app.get("/api/admin/invites")
def admin_list_invites(_admin: User = Depends(require_admin), db: Session = Depends(get_db), limit: int = 200):
    rows = db.scalars(select(InviteCode).order_by(InviteCode.id.desc()).limit(max(1, min(int(limit or 200), 500)))).all()
    return {
        "success": True,
        "items": [
            {
                "id": r.id,
                "code": r.code,
                "note": r.note,
                "max_uses": r.max_uses,
                "used_count": r.used_count,
                "enabled": r.enabled,
                "expires_at": ensure_utc(r.expires_at).isoformat() if r.expires_at else "",
                "created_by": r.created_by,
                "created_at": ensure_utc(r.created_at).isoformat() if r.created_at else "",
            }
            for r in rows
        ],
    }


@app.post("/api/admin/invites")
async def admin_create_invite(req: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        body = await req.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid json")
    if not isinstance(body, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid payload")
    code = str(body.get("code", "")).strip()
    if not code:
        import secrets as _secrets
        code = _secrets.token_urlsafe(9)
    if db.scalar(select(InviteCode).where(InviteCode.code == code)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="code already exists")
    note = str(body.get("note", ""))[:255]
    try:
        max_uses = max(1, int(body.get("max_uses") or 1))
    except Exception:
        max_uses = 1
    expires_at = None
    raw_exp = str(body.get("expires_at", "")).strip()
    if raw_exp:
        try:
            expires_at = datetime.fromisoformat(raw_exp.replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid expires_at (use ISO 8601)")
    row = InviteCode(code=code, note=note, max_uses=max_uses, expires_at=expires_at, created_by=admin.username)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"success": True, "item": {"id": row.id, "code": row.code}}


@app.patch("/api/admin/invites/{invite_id}")
async def admin_update_invite(invite_id: int, req: Request, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.get(InviteCode, invite_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    try:
        body = await req.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid json")
    if "enabled" in body:
        row.enabled = bool(body["enabled"])
    if "note" in body:
        row.note = str(body["note"])[:255]
    if "max_uses" in body:
        try:
            row.max_uses = max(1, int(body["max_uses"]))
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid max_uses")
    db.commit()
    return {"success": True}


@app.delete("/api/admin/invites/{invite_id}")
def admin_delete_invite(invite_id: int, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.get(InviteCode, invite_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    db.delete(row)
    db.commit()
    return {"success": True}


# --- AIRAC Cycle Subscriptions (#18) -----------------------------------------

from . import openlist_client as _openlist_client  # noqa: E402

CYCLE_NOTIFICATION_INTERVAL_SECONDS = int(os.getenv("APP_CYCLE_CHECK_INTERVAL_SECONDS", str(60 * 60)))


def _build_cycle_email(recipient: str, cycle: str) -> tuple[str, str, str]:
    subject = f"FMS NavData 新期数: AIRAC {cycle}"
    text = (
        f"OpenList 已发布新一期 AIRAC: {cycle}\n\n"
        f"打开 FMS Update Manager 即可下载并安装。\n"
    )
    html = f"""
<div style=\"font-family:Segoe UI,Arial,sans-serif;padding:24px;background:#f5f7fb;color:#13233b\">
  <div style=\"max-width:520px;margin:0 auto;background:#fff;border-radius:12px;padding:24px\">
    <h2 style=\"margin:0 0 12px;color:#1a73e8\">AIRAC {cycle} 已上架</h2>
    <p>OpenList 仓库已发布新一期 AIRAC 数据，打开 FMS Update Manager 即可下载并安装。</p>
    <p style=\"color:#6b7280;font-size:12px;margin-top:24px\">如需取消订阅，请在客户端「设置 → 期数订阅推送」关闭。</p>
  </div>
</div>
"""
    return subject, text, html


def fan_out_cycle_notifications(db: Session, cycle: str) -> int:
    """Queue one email per active subscriber whose last_notified_cycle != cycle.
    Returns the number of subscribers queued.
    """
    cycle = str(cycle or "").strip()
    if not cycle:
        return 0
    rows = db.scalars(
        select(CycleSubscription, User)
        .join(User, User.id == CycleSubscription.user_id)
        .where(CycleSubscription.enabled.is_(True), User.enabled.is_(True))
    ).all()
    queued = 0
    for sub_row in rows:
        sub = sub_row if isinstance(sub_row, CycleSubscription) else sub_row[0]
        user_obj = db.get(User, sub.user_id)
        if user_obj is None or not user_obj.email or not user_obj.enabled:
            continue
        if sub.last_notified_cycle == cycle:
            continue
        subject, text, html = _build_cycle_email(user_obj.email, cycle)
        queue_email(db, recipient=user_obj.email, subject=subject, purpose="cycle_notify", body_text=text, body_html=html)
        sub.last_notified_cycle = cycle
        queued += 1
    db.commit()
    return queued


def check_and_dispatch_cycle_once() -> dict:
    """Poll OpenList once and fan out notifications if a new cycle is found."""
    from .database import SessionLocal
    cycle = _openlist_client.latest_cycle()
    if not cycle:
        return {"checked": True, "cycle": "", "queued": 0, "reason": "openlist returned no cycle"}
    with SessionLocal() as db:
        state_row = db.get(CycleNotificationState, 1)
        if state_row is None:
            state_row = CycleNotificationState(id=1, last_seen_cycle="")
            db.add(state_row)
            db.commit()
        prev = state_row.last_seen_cycle or ""
        if cycle == prev:
            state_row.last_checked_at = datetime.utcnow()
            db.commit()
            return {"checked": True, "cycle": cycle, "queued": 0, "reason": "no new cycle"}
        queued = fan_out_cycle_notifications(db, cycle)
        state_row.last_seen_cycle = cycle
        state_row.last_checked_at = datetime.utcnow()
        db.commit()
        return {"checked": True, "cycle": cycle, "queued": queued, "previous": prev}


_cycle_worker_started = False
_cycle_worker_lock = Lock()


def _cycle_worker_loop() -> None:
    while True:
        try:
            result = check_and_dispatch_cycle_once()
            _record_worker_run("cycle", processed=int(result.get("queued", 0)))
        except Exception as exc:
            _record_worker_run("cycle", error=f"{type(exc).__name__}: {exc}")
        time.sleep(max(60, CYCLE_NOTIFICATION_INTERVAL_SECONDS))


def start_cycle_worker() -> None:
    global _cycle_worker_started
    with _cycle_worker_lock:
        if _cycle_worker_started:
            return
        _cycle_worker_started = True
    import threading
    t = threading.Thread(target=_cycle_worker_loop, name="cycle-notify-worker", daemon=True)
    t.start()


@app.get("/api/me/cycle_subscription")
def get_my_cycle_subscription(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sub = db.scalar(select(CycleSubscription).where(CycleSubscription.user_id == user.id))
    return {
        "success": True,
        "enabled": bool(sub.enabled) if sub is not None else False,
        "last_notified_cycle": (sub.last_notified_cycle if sub is not None else "") or "",
        "email": user.email or "",
    }


@app.put("/api/me/cycle_subscription")
async def put_my_cycle_subscription(req: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        body = await req.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid json")
    if not isinstance(body, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid payload")
    enabled = bool(body.get("enabled", False))
    if enabled and not user.email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="account has no email; cannot subscribe")
    sub = db.scalar(select(CycleSubscription).where(CycleSubscription.user_id == user.id))
    if sub is None:
        sub = CycleSubscription(user_id=user.id, enabled=enabled, last_notified_cycle="")
        db.add(sub)
    else:
        sub.enabled = enabled
    db.commit()
    return {"success": True, "enabled": enabled}


@app.post("/api/me/cycle_check_now")
async def post_my_cycle_check_now(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Client-pull path (#18): client calls this on startup; if OpenList has a
    new cycle vs. the global state row, we trigger fan-out (which dedups by
    `last_notified_cycle` per subscriber, so the *caller* only gets a mail if
    they themselves haven't been notified yet)."""
    sub = db.scalar(select(CycleSubscription).where(CycleSubscription.user_id == user.id))
    if sub is None or not sub.enabled or not user.email:
        return {"success": True, "skipped": True, "reason": "not subscribed"}
    result = check_and_dispatch_cycle_once()
    return {"success": True, **result}


# --- OpenList token mediation (#19) ------------------------------------------
# Clients should not ship hardcoded OpenList credentials. We expose a short-lived
# pass-through endpoint that returns the cached OpenList token. Authenticated
# users only.

@app.get("/api/me/openlist_token")
def get_openlist_token(user: User = Depends(get_current_user)):
    """Return a short-lived OpenList token. Avoids embedding OpenList creds in
    the desktop client. The OpenList token itself is opaque; the client should
    treat it as a bearer token with ~2h lifetime."""
    try:
        tok = _openlist_client._get_token()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"openlist login failed: {exc}")
    return {"success": True, "token": tok}


# --- Archive integrity registry (#20) ----------------------------------------
# admin_panel can POST a (cycle_id, archive_name, sha256) triple; the client
# fetches it before/after download to verify the file. The registry lives in
# app_settings under the "archive_hashes" key as a flat JSON object:
#   { "<cycle>/<archive_name>": "<sha256>", ... }

ARCHIVE_HASHES_KEY = "archive_hashes"


def _archive_hash_lookup(db: Session, cycle: str, archive: str) -> str:
    cycle = str(cycle or "").strip()
    archive = str(archive or "").strip()
    if not cycle or not archive:
        return ""
    table = _load_json_setting(db, ARCHIVE_HASHES_KEY, {})
    return str(table.get(f"{cycle}/{archive}", "")).lower().strip()


@app.get("/api/navdata/archive_hash")
def get_archive_hash(cycle: str, archive: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    h = _archive_hash_lookup(db, cycle, archive)
    return {"success": True, "cycle": cycle, "archive": archive, "sha256": h, "found": bool(h)}


@app.put("/api/admin/archive_hashes")
async def put_archive_hashes(req: Request, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        body = await req.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid json")
    if not isinstance(body, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid payload")
    cleaned: dict[str, str] = {}
    for k, v in body.items():
        if not isinstance(k, str) or "/" not in k:
            continue
        if not isinstance(v, str) or len(v) not in (64,):
            continue
        cleaned[k.strip()] = v.lower().strip()
    row = db.get(AppSetting, ARCHIVE_HASHES_KEY)
    if row is None:
        db.add(AppSetting(key=ARCHIVE_HASHES_KEY, value=json.dumps(cleaned, ensure_ascii=False)))
    else:
        row.value = json.dumps(cleaned, ensure_ascii=False)
    db.commit()
    return {"success": True, "count": len(cleaned)}


@app.get("/api/admin/archive_hashes")
def list_archive_hashes(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return {"success": True, "table": _load_json_setting(db, ARCHIVE_HASHES_KEY, {})}


# --- Password reset (#38) ----------------------------------------------------

PASSWORD_RESET_CODE_KEY = "password_reset"


def _build_password_reset_email(code: str, ttl_seconds: int) -> tuple[str, str, str]:
    subject = "FMS 密码重置验证码"
    text = f"你的密码重置验证码是 {code}，有效期 {ttl_seconds // 60} 分钟。如非本人操作请忽略此邮件。"
    html = f"""
<div style="font-family:Segoe UI,Arial,sans-serif;padding:24px;background:#f5f7fb;color:#13233b">
  <div style="max-width:520px;margin:0 auto;background:#fff;border-radius:12px;padding:24px">
    <h2 style="margin:0 0 12px;color:#1a73e8">FMS 密码重置</h2>
    <div style="font-size:32px;font-weight:700;letter-spacing:6px;background:#eef3fb;border-radius:10px;padding:14px 18px;text-align:center">{code}</div>
    <p>有效期 {ttl_seconds // 60} 分钟。如非本人操作请忽略此邮件。</p>
  </div>
</div>
"""
    return subject, text, html


def _store_password_reset_code(db: Session, email: str, code: str, ip: str, ttl_seconds: int) -> None:
    expires = datetime.utcnow() + timedelta(seconds=ttl_seconds)
    row = db.get(PasswordResetCode, email)
    if row is None:
        row = PasswordResetCode(email=email, code_hash=code_hash(code), expires_at=expires, attempts=0, sent_ip=ip[:64])
        db.add(row)
    else:
        row.code_hash = code_hash(code)
        row.expires_at = expires
        row.attempts = 0
        row.sent_ip = ip[:64]
        row.used_at = None
    db.commit()


@app.post("/api/auth/password_reset/code")
def password_reset_code(body: PasswordResetCodeRequest, req: Request, db: Session = Depends(get_db)):
    ip = client_ip(req)
    email = normalize_email(body.email)
    smtp_cfg = load_smtp_config(db)
    try:
        per_email_window = max(10, int(smtp_cfg.get("per_email_window_seconds") or 60))
    except Exception:
        per_email_window = 60
    enforce_code_send_cooldown(ip, email, per_email_window, db)
    verify_turnstile(body.turnstile_token, ip, db)
    user = db.scalar(select(User).where(User.email == email))
    # To avoid leaking which emails exist, we always return 200; only actually
    # send mail if the email matches an enabled user.
    if user is not None and user.enabled:
        ttl = get_register_code_ttl(smtp_cfg)
        code = generate_code(int(smtp_cfg.get("code_length") or 6))
        _store_password_reset_code(db, email, code, ip, ttl)
        subject, text, html = _build_password_reset_email(code, ttl)
        if not (smtp_cfg.get("host") and smtp_cfg.get("username") and smtp_cfg.get("password") and smtp_cfg.get("sender")):
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="smtp not configured")
        queue_email(db, recipient=email, subject=subject, purpose=PASSWORD_RESET_CODE_KEY, body_text=text, body_html=html)
        try:
            _smtp_send_now(smtp_cfg, email, subject, text, html)
            _outbox_log_attempt(db, email, subject, PASSWORD_RESET_CODE_KEY, True, "")
        except Exception as exc:
            _outbox_log_attempt(db, email, subject, PASSWORD_RESET_CODE_KEY, False, str(exc))
    record_code_send(ip, email)
    return {"success": True, "message": "if the email is registered, a code has been sent"}


@app.post("/api/auth/password_reset")
def password_reset(body: PasswordResetRequest, req: Request, db: Session = Depends(get_db)):
    ip = client_ip(req)
    email = normalize_email(body.email)
    verify_turnstile(body.turnstile_token, ip, db)
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid code")
    code_row = db.get(PasswordResetCode, email)
    if code_row is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="reset code not found")
    if code_row.used_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="reset code already used")
    expires_at = ensure_utc(code_row.expires_at)
    if expires_at is None or expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="reset code expired")
    if code_row.attempts >= 5:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="too many attempts")
    if code_row.code_hash != code_hash(body.email_code.strip()):
        code_row.attempts += 1
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid reset code")
    try:
        assert_password_strong(body.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    code_row.used_at = datetime.now(timezone.utc)
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"success": True, "message": "password reset ok"}


@app.get("/api/admin/health/workers")
def admin_worker_health(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Return per-worker liveness + queue depth metrics for monitoring."""
    pending = int(db.scalar(select(func.count()).select_from(EmailOutbox).where(EmailOutbox.status == "pending")) or 0)
    failed = int(db.scalar(select(func.count()).select_from(EmailOutbox).where(EmailOutbox.status == "failed")) or 0)
    cycle_state = db.get(CycleNotificationState, 1)
    with _worker_health_lock:
        snapshot = {k: dict(v) for k, v in _worker_health.items()}
    return {
        "success": True,
        "now": datetime.utcnow().isoformat(),
        "workers": snapshot,
        "outbox": {"pending": pending, "failed": failed},
        "cycle": {
            "last_seen_cycle": (cycle_state.last_seen_cycle if cycle_state else ""),
            "last_checked_at": (cycle_state.last_checked_at.isoformat() if cycle_state and cycle_state.last_checked_at else ""),
        },
    }


@app.get("/healthz/full")
def healthz_full(db: Session = Depends(get_db)):
    """Unauthenticated deep health check for monitoring.

    Reports DB / SMTP-config / OpenList reachability + worker freshness.
    Does NOT expose secrets. Always returns 200 — interpret the JSON.
    """
    out: dict = {"now": datetime.utcnow().isoformat(), "service": "fms-backup-auth"}
    try:
        db.scalar(select(func.count()).select_from(User))
        out["db"] = "ok"
    except Exception as exc:
        out["db"] = f"error: {exc}"

    try:
        smtp_cfg = load_smtp_config(db)
        out["smtp_configured"] = bool(smtp_cfg.get("host") and smtp_cfg.get("username") and smtp_cfg.get("password") and smtp_cfg.get("sender"))
    except Exception:
        out["smtp_configured"] = False

    try:
        out["openlist_latest_cycle"] = _openlist_client.latest_cycle() or "unknown"
    except Exception as exc:
        out["openlist_latest_cycle"] = f"error: {exc}"

    try:
        out["outbox_pending"] = int(db.scalar(select(func.count()).select_from(EmailOutbox).where(EmailOutbox.status == "pending")) or 0)
        out["outbox_failed"] = int(db.scalar(select(func.count()).select_from(EmailOutbox).where(EmailOutbox.status == "failed")) or 0)
    except Exception:
        out["outbox_pending"] = -1
        out["outbox_failed"] = -1

    with _worker_health_lock:
        out["workers"] = {k: {"last_run_at": v["last_run_at"], "last_ok_at": v["last_ok_at"], "errors": v["errors"]} for k, v in _worker_health.items()}

    return out
