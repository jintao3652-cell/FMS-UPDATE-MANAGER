from datetime import datetime, timedelta, timezone
import json
from typing import Any

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from .config import settings
from .database import Base, engine, get_db
from .mailer import (
    DEFAULT_SMTP,
    get_setting_json,
    load_smtp,
    load_turnstile,
    render_verification_email,
    save_smtp,
    save_turnstile,
    send_email,
    set_setting_json,
    smtp_status,
    turnstile_status,
)
from .models import AdminAudit, AppSetting, CrashReport, EmailLog, LoginAudit, User
from .schemas import (
    EmailDomainSettings,
    LoginRequest,
    LoginResponse,
    PasswordUpdateRequest,
    RateLimitSettings,
    SmtpSettings,
    SmtpTestRequest,
    TurnstileSettings,
    UserCreateRequest,
    UserUpdateRequest,
)
from .security import assert_password_strong, create_access_token, create_refresh_token, decode_access_token, decode_refresh_token, hash_password, verify_password
from .ui import ADMIN_PAGE_HTML
from . import openlist_client


app = FastAPI(title="FMS Admin Panel", version="1.0.0")

origins = ["*"] if settings.allowed_origins == "*" else [x.strip() for x in settings.allowed_origins.split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


RATE_LIMIT_KEY = "rate_limits"
EMAIL_DOMAIN_KEY = "email_domains"
DEFAULT_RATE_LIMITS = RateLimitSettings().model_dump()
DEFAULT_EMAIL_DOMAINS = EmailDomainSettings().model_dump()


def client_ip(req: Request) -> str:
    xff = req.headers.get("x-forwarded-for", "").strip()
    if xff:
        return xff.split(",")[0].strip()
    return req.client.host if req.client else "unknown"


def parse_bearer(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing authorization header")
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid authorization header")
    token = authorization[len(prefix):].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    return token


def get_current_admin(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
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
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin required")
    return user


def audit(db: Session, admin: User, action: str, target: str, detail: str, ip: str) -> None:
    db.add(AdminAudit(admin_username=admin.username, action=action[:64], target=target[:255], detail=detail[:1200], ip=ip[:64]))
    db.commit()


def ensure_schema_compat() -> None:
    inspector = inspect(engine)
    if "users" in inspector.get_table_names():
        columns = {col["name"] for col in inspector.get_columns("users")}
        with engine.begin() as conn:
            if "email" not in columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(255) NULL"))
            try:
                conn.execute(text("CREATE UNIQUE INDEX uq_users_email ON users (email)"))
            except Exception:
                pass


def sync_config_admin(db: Session) -> None:
    username = settings.admin_username.strip()
    password = settings.admin_password
    if not username or not password:
        return
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        db.add(User(username=username, password_hash=hash_password(password), role="admin", enabled=True))
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
    return {"ok": True, "service": "fms-admin-panel"}


@app.get("/", response_class=HTMLResponse)
def root_page():
    return ADMIN_PAGE_HTML


@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    return ADMIN_PAGE_HTML


@app.post("/api/auth/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username))
    if user is None or not user.enabled or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin required")
    token, expires_in = create_access_token(subject=user.username, role=user.role)
    refresh_token, refresh_expires_in = create_refresh_token(subject=user.username, role=user.role)
    return LoginResponse(
        success=True,
        token=token,
        expires_in=expires_in,
        refresh_token=refresh_token,
        refresh_expires_in=refresh_expires_in,
        user={"username": user.username, "role": user.role, "email": user.email or ""},
    )


@app.post("/api/auth/refresh")
async def admin_refresh(req: Request, db: Session = Depends(get_db)):
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
    if user is None or not user.enabled or user.role != "admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found or not admin")
    token, expires_in = create_access_token(subject=user.username, role=user.role)
    return {
        "success": True,
        "token": token,
        "expires_in": expires_in,
        "user": {"username": user.username, "role": user.role, "email": user.email or ""},
    }


@app.get("/api/me")
def me(admin: User = Depends(get_current_admin)):
    return {"success": True, "user": {"username": admin.username, "role": admin.role, "email": admin.email or ""}}


@app.get("/api/dashboard")
def dashboard(_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    yesterday_start = today_start - timedelta(days=1)
    total_users = db.scalar(select(func.count()).select_from(User)) or 0
    enabled_users = db.scalar(select(func.count()).select_from(User).where(User.enabled.is_(True))) or 0
    admins = db.scalar(select(func.count()).select_from(User).where(User.role == "admin")) or 0
    today_logins = db.scalar(
        select(func.count()).select_from(LoginAudit).where(LoginAudit.created_at >= today_start)
    ) or 0
    today_login_fail = db.scalar(
        select(func.count()).select_from(LoginAudit).where(LoginAudit.created_at >= today_start, LoginAudit.success.is_(False))
    ) or 0
    today_emails = db.scalar(
        select(func.count()).select_from(EmailLog).where(EmailLog.created_at >= today_start)
    ) or 0
    today_email_fail = db.scalar(
        select(func.count()).select_from(EmailLog).where(EmailLog.created_at >= today_start, EmailLog.success.is_(False))
    ) or 0
    new_users_today = db.scalar(
        select(func.count()).select_from(User).where(User.created_at >= today_start)
    ) or 0
    new_users_yesterday = db.scalar(
        select(func.count()).select_from(User).where(User.created_at >= yesterday_start, User.created_at < today_start)
    ) or 0
    cfg = load_smtp(db)
    return {
        "success": True,
        "stats": {
            "total_users": int(total_users),
            "enabled_users": int(enabled_users),
            "admins": int(admins),
            "today_logins": int(today_logins),
            "today_login_fail": int(today_login_fail),
            "today_emails": int(today_emails),
            "today_email_fail": int(today_email_fail),
            "new_users_today": int(new_users_today),
            "new_users_yesterday": int(new_users_yesterday),
        },
        "smtp": smtp_status(cfg),
    }


def _user_payload(u: User) -> dict[str, Any]:
    return {
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "role": u.role,
        "enabled": u.enabled,
        "created_at": u.created_at.isoformat() if u.created_at else "",
    }


@app.get("/api/users")
def list_users(
    q: str | None = None,
    role: str | None = None,
    enabled: str | None = None,
    limit: int = 200,
    offset: int = 0,
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    stmt = select(User)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where((User.username.like(like)) | (User.email.like(like)))
    if role:
        stmt = stmt.where(User.role == role.strip())
    if enabled in {"true", "false"}:
        stmt = stmt.where(User.enabled.is_(enabled == "true"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(User.id.desc()).limit(max(1, min(limit, 500))).offset(max(0, offset))
    users = db.scalars(stmt).all()
    return {"success": True, "total": int(total), "users": [_user_payload(u) for u in users]}


@app.post("/api/users")
def create_user(body: UserCreateRequest, req: Request, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    username = body.username.strip()
    if not username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid username")
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username already exists")
    email = (body.email or "").strip().lower() or None
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
        role=(body.role.strip() or "user"),
        enabled=bool(body.enabled),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit(db, admin, "create_user", username, f"role={user.role} enabled={user.enabled} email={email or ''}", client_ip(req))
    return {"success": True, "id": user.id}


@app.patch("/api/users/{user_id}")
def update_user(user_id: int, body: UserUpdateRequest, req: Request, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    changes: list[str] = []
    if body.email is not None:
        email = body.email.strip().lower() or None
        if email and db.scalar(select(User).where(User.email == email, User.id != user_id)):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already exists")
        if user.email != email:
            changes.append(f"email:{user.email or ''}->{email or ''}")
            user.email = email
    if body.role is not None:
        role = body.role.strip() or user.role
        if user.role != role:
            changes.append(f"role:{user.role}->{role}")
            user.role = role
    if body.enabled is not None:
        flag = bool(body.enabled)
        if user.enabled != flag:
            changes.append(f"enabled:{user.enabled}->{flag}")
            user.enabled = flag
    db.commit()
    audit(db, admin, "update_user", user.username, "; ".join(changes) or "no change", client_ip(req))
    return {"success": True}


@app.patch("/api/users/{user_id}/password")
def update_password(user_id: int, body: PasswordUpdateRequest, req: Request, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    try:
        assert_password_strong(body.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    user.password_hash = hash_password(body.password)
    db.commit()
    audit(db, admin, "reset_password", user.username, "", client_ip(req))
    return {"success": True}


@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, req: Request, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    if user.username == admin.username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cannot delete current admin")
    username = user.username
    db.delete(user)
    db.commit()
    audit(db, admin, "delete_user", username, "", client_ip(req))
    return {"success": True}


@app.get("/api/settings/smtp")
def get_smtp(_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    cfg = load_smtp(db)
    data = cfg.model_dump()
    if data.get("password"):
        data["password"] = "********"
    return {"success": True, "smtp": data, "status": smtp_status(cfg)}


@app.put("/api/settings/smtp")
def put_smtp(body: SmtpSettings, req: Request, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    current = load_smtp(db)
    payload = body.model_dump()
    if not payload.get("password") or payload["password"] == "********":
        payload["password"] = current.password
    new_cfg = SmtpSettings(**payload)
    save_smtp(db, new_cfg)
    audit(db, admin, "update_smtp", new_cfg.host, f"port={new_cfg.port} sender={new_cfg.sender}", client_ip(req))
    masked = new_cfg.model_dump()
    if masked.get("password"):
        masked["password"] = "********"
    return {"success": True, "smtp": masked, "status": smtp_status(new_cfg)}


@app.post("/api/settings/smtp/test")
def smtp_test(body: SmtpTestRequest, req: Request, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    cfg = load_smtp(db)
    subject = "FMS Admin SMTP 测试邮件"
    text_body = "这是一封来自 FMS Admin 后台的 SMTP 测试邮件。如果您收到此邮件，说明 SMTP 配置已生效。"
    html = """<div style="font-family:Segoe UI,Arial,sans-serif;padding:18px;color:#13233b">
<h3 style="margin:0 0 10px;color:#1a73e8">FMS Admin · SMTP 测试</h3>
<p>这是一封来自后台的测试邮件。收到即表示 SMTP 配置成功。</p></div>"""
    ok, err = send_email(db, cfg, body.recipient.strip(), subject, text_body, html, purpose="smtp_test", sent_by=admin.username)
    audit(db, admin, "smtp_test", body.recipient.strip(), "ok" if ok else err, client_ip(req))
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err or "send failed")
    return {"success": True}


@app.get("/api/settings/turnstile")
def get_turnstile(_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    cfg = load_turnstile(db)
    data = cfg.model_dump()
    if data.get("secret_key"):
        data["secret_key"] = "********"
    return {"success": True, "turnstile": data, "status": turnstile_status(cfg)}


@app.put("/api/settings/turnstile")
def put_turnstile(body: TurnstileSettings, req: Request, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    current = load_turnstile(db)
    payload = body.model_dump()
    if not payload.get("secret_key") or payload["secret_key"] == "********":
        payload["secret_key"] = current.secret_key
    new_cfg = TurnstileSettings(**payload)
    save_turnstile(db, new_cfg)
    audit(db, admin, "update_turnstile", "", f"site_key_set={bool(new_cfg.site_key)} secret_key_set={bool(new_cfg.secret_key)}", client_ip(req))
    masked = new_cfg.model_dump()
    if masked.get("secret_key"):
        masked["secret_key"] = "********"
    return {"success": True, "turnstile": masked, "status": turnstile_status(new_cfg)}


@app.get("/api/settings/rate_limits")
def get_rate_limits(_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    data = get_setting_json(db, RATE_LIMIT_KEY, DEFAULT_RATE_LIMITS)
    return {"success": True, "rate_limits": data}


@app.put("/api/settings/rate_limits")
def put_rate_limits(body: RateLimitSettings, req: Request, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    set_setting_json(db, RATE_LIMIT_KEY, body.model_dump())
    audit(db, admin, "update_rate_limits", "", "", client_ip(req))
    return {"success": True, "rate_limits": body.model_dump()}


@app.get("/api/settings/email_domains")
def get_email_domains(_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    data = get_setting_json(db, EMAIL_DOMAIN_KEY, DEFAULT_EMAIL_DOMAINS)
    return {"success": True, "email_domains": data}


@app.put("/api/settings/email_domains")
def put_email_domains(body: EmailDomainSettings, req: Request, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    payload = {
        "whitelist": [d.strip().lower() for d in body.whitelist if d.strip()],
        "blacklist": [d.strip().lower() for d in body.blacklist if d.strip()],
    }
    set_setting_json(db, EMAIL_DOMAIN_KEY, payload)
    audit(db, admin, "update_email_domains", "", f"wl={len(payload['whitelist'])} bl={len(payload['blacklist'])}", client_ip(req))
    return {"success": True, "email_domains": payload}


@app.get("/api/logs/login")
def login_logs(
    limit: int = 100,
    offset: int = 0,
    success: str | None = None,
    q: str | None = None,
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    stmt = select(LoginAudit)
    if success in {"true", "false"}:
        stmt = stmt.where(LoginAudit.success.is_(success == "true"))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where((LoginAudit.username.like(like)) | (LoginAudit.ip.like(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(LoginAudit.id.desc()).limit(max(1, min(limit, 500))).offset(max(0, offset))
    rows = db.scalars(stmt).all()
    return {
        "success": True,
        "total": int(total),
        "items": [
            {
                "id": r.id,
                "username": r.username,
                "ip": r.ip,
                "user_agent": r.user_agent,
                "success": r.success,
                "detail": r.detail,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ],
    }


@app.get("/api/logs/email")
def email_logs(
    limit: int = 100,
    offset: int = 0,
    success: str | None = None,
    q: str | None = None,
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    stmt = select(EmailLog)
    if success in {"true", "false"}:
        stmt = stmt.where(EmailLog.success.is_(success == "true"))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where((EmailLog.recipient.like(like)) | (EmailLog.purpose.like(like)) | (EmailLog.subject.like(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(EmailLog.id.desc()).limit(max(1, min(limit, 500))).offset(max(0, offset))
    rows = db.scalars(stmt).all()
    return {
        "success": True,
        "total": int(total),
        "items": [
            {
                "id": r.id,
                "recipient": r.recipient,
                "subject": r.subject,
                "purpose": r.purpose,
                "success": r.success,
                "error": r.error,
                "sent_by": r.sent_by,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ],
    }


@app.get("/api/logs/admin")
def admin_logs(
    limit: int = 100,
    offset: int = 0,
    q: str | None = None,
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    stmt = select(AdminAudit)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            (AdminAudit.admin_username.like(like))
            | (AdminAudit.action.like(like))
            | (AdminAudit.target.like(like))
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(AdminAudit.id.desc()).limit(max(1, min(limit, 500))).offset(max(0, offset))
    rows = db.scalars(stmt).all()
    return {
        "success": True,
        "total": int(total),
        "items": [
            {
                "id": r.id,
                "admin_username": r.admin_username,
                "action": r.action,
                "target": r.target,
                "detail": r.detail,
                "ip": r.ip,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ],
    }


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)


@app.get("/api/logs/crash")
def crash_logs(
    limit: int = 100,
    offset: int = 0,
    version: str | None = None,
    exc_type: str | None = None,
    install_id: str | None = None,
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    stmt = select(CrashReport)
    if version:
        stmt = stmt.where(CrashReport.version == version.strip())
    if exc_type:
        stmt = stmt.where(CrashReport.exc_type == exc_type.strip())
    if install_id:
        stmt = stmt.where(CrashReport.install_id == install_id.strip())
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(CrashReport.id.desc()).limit(max(1, min(limit, 500))).offset(max(0, offset))
    rows = db.scalars(stmt).all()
    return {
        "success": True,
        "total": int(total),
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
        ],
    }


@app.get("/api/logs/crash/{crash_id}")
def crash_log_detail(
    crash_id: int,
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    r = db.get(CrashReport, crash_id)
    if r is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    return {
        "success": True,
        "item": {
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
        },
    }


@app.get("/api/openlist/cycles")
def openlist_cycles(_admin: User = Depends(get_current_admin)):
    try:
        cycles = openlist_client.list_cycles()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"openlist error: {exc}")
    return {"success": True, "items": cycles, "latest": cycles[0]["cycle_id"] if cycles else ""}


@app.get("/api/openlist/cycles/{cycle_id}/msfs")
def openlist_cycle_msfs(cycle_id: str, _admin: User = Depends(get_current_admin)):
    try:
        files = openlist_client.list_msfs_packages(cycle_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"openlist error: {exc}")
    return {"success": True, "cycle_id": cycle_id, "items": files, "count": len(files)}


from .models import EmailOutbox  # noqa: E402


@app.get("/api/admin/outbox")
def admin_outbox_list(
    _admin: User = Depends(get_current_admin),
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
        "success": True,
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
        ],
    }


@app.post("/api/admin/outbox/{outbox_id}/retry")
def admin_outbox_retry(outbox_id: int, req: Request, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    row = db.get(EmailOutbox, outbox_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    if row.status == "sent":
        return {"success": True, "message": "already sent"}
    row.status = "pending"
    row.next_attempt_at = datetime.utcnow()
    db.commit()
    audit(db, admin, "outbox_retry", str(outbox_id), "", client_ip(req))
    return {"success": True, "message": "queued for retry"}


REGISTER_POLICY_KEY = "register_policy"
DEFAULT_REGISTER_POLICY = {"require_invite_code": False, "require_admin_approval": False}


@app.get("/api/settings/register_policy")
def get_register_policy(_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return {"success": True, "policy": get_setting_json(db, REGISTER_POLICY_KEY, DEFAULT_REGISTER_POLICY)}


@app.put("/api/settings/register_policy")
async def put_register_policy(req: Request, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
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
    set_setting_json(db, REGISTER_POLICY_KEY, cfg)
    audit(db, admin, "update_register_policy", "", json.dumps(cfg, ensure_ascii=False), client_ip(req))
    return {"success": True, "policy": cfg}


from .models import InviteCode  # noqa: E402


@app.get("/api/admin/invites")
def invites_list(_admin: User = Depends(get_current_admin), db: Session = Depends(get_db), limit: int = 200):
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
                "expires_at": r.expires_at.isoformat() if r.expires_at else "",
                "created_by": r.created_by,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ],
    }


@app.post("/api/admin/invites")
async def invites_create(req: Request, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid expires_at")
    row = InviteCode(code=code, note=note, max_uses=max_uses, expires_at=expires_at, created_by=admin.username)
    db.add(row)
    db.commit()
    db.refresh(row)
    audit(db, admin, "invite_create", row.code, json.dumps({"max_uses": max_uses, "note": note}, ensure_ascii=False), client_ip(req))
    return {"success": True, "id": row.id, "code": row.code}


@app.patch("/api/admin/invites/{invite_id}")
async def invites_update(invite_id: int, req: Request, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
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
    audit(db, admin, "invite_update", row.code, "", client_ip(req))
    return {"success": True}


@app.delete("/api/admin/invites/{invite_id}")
def invites_delete(invite_id: int, admin: User = Depends(get_current_admin), db: Session = Depends(get_db), req: Request = None):
    row = db.get(InviteCode, invite_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    code = row.code
    db.delete(row)
    db.commit()
    audit(db, admin, "invite_delete", code, "", "")
    return {"success": True}


@app.get("/api/admin/pending_users")
def pending_users(_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(User).where(User.enabled.is_(False)).order_by(User.id.asc())).all()
    return {
        "success": True,
        "items": [
            {"id": u.id, "username": u.username, "email": u.email or "", "created_at": u.created_at.isoformat() if u.created_at else ""}
            for u in rows
        ],
    }
