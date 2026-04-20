from collections import defaultdict
from datetime import datetime, timezone
from threading import Lock
import re

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from .config import settings
from .database import Base, engine, get_db
from .models import LoginAudit, User
from .schemas import (
    AdminCreateUserRequest,
    AdminUpdatePasswordRequest,
    AdminUpdateUserRequest,
    LoginRequest,
    LoginResponse,
    MeResponse,
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


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_schema_compat()
    if not settings.admin_username or not settings.admin_password:
        return
    with Session(engine) as db:
        exists = db.scalar(select(User).where(User.username == settings.admin_username))
        if exists:
            return
        db.add(
            User(
                username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
                role="admin",
                enabled=True,
            )
        )
        db.commit()


@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "fms-backup-auth"}


@app.get("/register", response_class=HTMLResponse)
def register_page():
    return """
<!doctype html><html><head><meta charset="utf-8"><title>Register</title>
<style>body{font-family:Segoe UI;padding:24px;max-width:560px}input,button{width:100%;margin:6px 0;padding:10px}pre{background:#f5f5f5;padding:10px}</style>
</head><body>
<h2>用户注册</h2>
<input id="username" placeholder="用户名">
<input id="password" placeholder="密码" type="password">
<button onclick="registerUser()">注册</button>
<pre id="out"></pre>
<script>
const out = document.getElementById('out');
async function registerUser(){
  const payload={
    username:document.getElementById('username').value.trim(),
    password:document.getElementById('password').value
  };
  const r=await fetch('/api/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  out.textContent=await r.text();
}
</script></body></html>
"""


@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    return """
<!doctype html><html><head><meta charset="utf-8"><title>Admin</title>
<style>body{font-family:Segoe UI;padding:24px;max-width:900px}input,button,select{margin:4px;padding:8px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:6px}pre{background:#f5f5f5;padding:10px}</style>
</head><body>
<h2>鍚庡彴绠＄悊</h2>
<p>鍏堢櫥褰曟嬁 token锛屽啀绮樿创鍒颁笅闈€?/p>
<input id="token" placeholder="Bearer token" style="width:100%">
<button onclick="loadUsers()">鍒锋柊鐢ㄦ埛鍒楄〃</button>
<h3>鏂板鐢ㄦ埛</h3>
<input id="new_user" placeholder="鐢ㄦ埛鍚?><input id="new_email" placeholder="閭"><input id="new_pwd" placeholder="瀵嗙爜">
<select id="new_role"><option value="user">user</option><option value="admin">admin</option></select>
<button onclick="createUser()">鏂板</button>
<h3>鐢ㄦ埛鍒楄〃</h3>
<table id="tbl"><thead><tr><th>ID</th><th>鐢ㄦ埛鍚?/th><th>閭</th><th>瑙掕壊</th><th>鍚敤</th><th>鎿嶄綔</th></tr></thead><tbody></tbody></table>
<pre id="out"></pre>
<script>
const out=document.getElementById('out');
const tb=document.querySelector('#tbl tbody');
function auth(){return {'Authorization':'Bearer '+document.getElementById('token').value.trim(),'Content-Type':'application/json'};}
async function loadUsers(){
  const r=await fetch('/api/admin/users',{headers:auth()}); const t=await r.text(); out.textContent=t;
  if(!r.ok)return; const j=JSON.parse(t); tb.innerHTML='';
  for(const u of j.users){
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${u.id}</td><td>${u.username}</td><td>${u.email||''}</td><td>${u.role}</td><td>${u.enabled}</td>
    <td><button onclick="delUser(${u.id})">鍒犻櫎</button><button onclick="chgPwd(${u.id})">鏀瑰瘑</button></td>`;
    tb.appendChild(tr);
  }
}
async function createUser(){
  const p={username:new_user.value.trim(),email:new_email.value.trim()||null,password:new_pwd.value,role:new_role.value,enabled:true};
  const r=await fetch('/api/admin/users',{method:'POST',headers:auth(),body:JSON.stringify(p)}); out.textContent=await r.text(); await loadUsers();
}
async function delUser(id){
  const r=await fetch('/api/admin/users/'+id,{method:'DELETE',headers:auth()}); out.textContent=await r.text(); await loadUsers();
}
async function chgPwd(id){
  const password=prompt('杈撳叆鏂板瘑鐮?); if(!password)return;
  const r=await fetch('/api/admin/users/'+id+'/password',{method:'PATCH',headers:auth(),body:JSON.stringify({password})});
  out.textContent=await r.text();
}
</script></body></html>
"""


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
    username = body.username.strip()
    if not username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid username")
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username already exists")
    db.add(User(username=username, email=None, password_hash=hash_password(body.password), role="user", enabled=True))
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
