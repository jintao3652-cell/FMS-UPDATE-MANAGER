import time

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse

from .config import settings


app = FastAPI(title="FMS Password Reset UI", version="1.0.0")


_PROXY_HOP_HEADERS = {
    "host", "content-length", "connection", "keep-alive", "transfer-encoding",
    "upgrade", "proxy-authenticate", "proxy-authorization", "te", "trailers",
}
_PROXY_RESPONSE_STRIP_HEADERS = _PROXY_HOP_HEADERS | {"content-encoding"}


async def _proxy_to_auth(request: Request, path: str) -> Response:
    upstream = f"{settings.auth_api_url.rstrip('/')}/{path}"
    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _PROXY_HOP_HEADERS}
    client_ip = request.client.host if request.client else ""
    if client_ip:
        prior = headers.get("x-forwarded-for")
        headers["x-forwarded-for"] = f"{prior}, {client_ip}" if prior else client_ip
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.request(
                request.method, upstream, content=body, headers=headers,
                params=request.query_params,
            )
    except httpx.RequestError as exc:
        return Response(
            content=f'{{"detail":"upstream unreachable: {type(exc).__name__}: {exc}"}}',
            status_code=502,
            media_type="application/json",
        )
    resp_headers = {k: v for k, v in r.headers.items() if k.lower() not in _PROXY_RESPONSE_STRIP_HEADERS}
    return Response(content=r.content, status_code=r.status_code, headers=resp_headers)


@app.api_route("/api/auth/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_auth(path: str, request: Request):
    return await _proxy_to_auth(request, f"api/auth/{path}")


@app.api_route("/api/public/{path:path}", methods=["GET", "POST"])
async def proxy_public(path: str, request: Request):
    return await _proxy_to_auth(request, f"api/public/{path}")


_site_key_cache: dict = {"value": "", "ts": 0.0}
_CACHE_TTL = 60.0


def get_site_key() -> str:
    now = time.time()
    if now - _site_key_cache["ts"] < _CACHE_TTL and _site_key_cache["ts"] > 0:
        return _site_key_cache["value"]
    try:
        r = httpx.get(f"{settings.auth_api_url.rstrip('/')}/api/public/turnstile_site_key", timeout=5)
        if r.status_code == 200:
            _site_key_cache["value"] = (r.json().get("site_key") or "").strip()
        else:
            _site_key_cache["value"] = ""
    except Exception:
        _site_key_cache["value"] = ""
    _site_key_cache["ts"] = now
    return _site_key_cache["value"]


@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "fms-password-reset-ui"}


@app.get("/", response_class=HTMLResponse)
def reset_page():
    site_key = get_site_key()
    auth_base = settings.register_public_auth_url.rstrip("/")
    if site_key:
        turnstile_script = '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>'
        turnstile_widget = f'<div id="cf-turnstile-widget" class="cf-turnstile" data-sitekey="{site_key}" data-theme="dark"></div>'
    else:
        turnstile_script = ""
        turnstile_widget = ""
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FMS 重置密码</title>
{turnstile_script}
<style>
body{{margin:0;font-family:Segoe UI,Arial,sans-serif;background:radial-gradient(circle at top,#0f203c 0,#07111f 40%,#050b14 100%);color:#e6eefc;min-height:100vh}}
.wrap{{max-width:520px;margin:0 auto;padding:48px 20px}}
.card{{background:rgba(12,23,41,.92);border:1px solid #21324c;border-radius:16px;padding:28px;box-shadow:0 18px 46px rgba(0,0,0,.32);backdrop-filter:blur(14px)}}
h2{{margin:0 0 12px;letter-spacing:.4px}}
p{{color:#8ea3c7;line-height:1.6;font-size:14px}}
input,button{{width:100%;box-sizing:border-box;margin:8px 0;padding:12px 14px;border-radius:12px;border:1px solid #21324c;background:#09111d;color:#e6eefc;font-size:14px;font-family:inherit}}
input:focus{{outline:none;border-color:#29b6f6}}
button{{background:linear-gradient(180deg,#29b6f6,#1958c4);border:none;cursor:pointer;font-weight:600;color:#fff}}
button:hover{{filter:brightness(1.08)}}
button.secondary{{background:linear-gradient(180deg,#2a3a55,#1a2538)}}
.row{{display:flex;gap:10px;align-items:center}}
.row>*{{flex:1}}
.row>button{{max-width:170px}}
.msg{{white-space:pre-wrap;background:#09111d;border:1px solid #21324c;border-radius:12px;padding:12px;min-height:48px;margin-top:12px;color:#cdd9ef;font-size:13px}}
.tiny{{font-size:12px;color:#8ea3c7;margin-top:8px}}
.cf-turnstile-slot{{margin:12px 0}}
</style></head><body>
<div class="wrap"><div class="card">
<h2>FMS 重置密码</h2>
<p>请输入您的注册邮箱，发送验证码后设置新密码。</p>
<input id="email" placeholder="注册邮箱" autocomplete="email">
<div class="row">
  <input id="email_code" placeholder="邮箱验证码">
  <button onclick="sendResetCode()">发送验证码</button>
</div>
<input id="new_password" type="password" placeholder="新密码（至少 6 位）" autocomplete="new-password">
<div class="cf-turnstile-slot">{turnstile_widget}</div>
<button onclick="resetPassword()">重置密码</button>
<div id="out" class="msg">等待操作。</div>
<div class="tiny">如果收不到验证码，请检查垃圾箱或联系管理员检查 SMTP 配置。</div>
</div></div>
<script>
const AUTH_BASE = {auth_base!r};
const out = document.getElementById('out');
function getTurnstileToken(){{const el=document.querySelector('input[name="cf-turnstile-response"]');return el?el.value.trim():'';}}
function resetTurnstile(){{
  try{{
    if(window.turnstile){{
      const el=document.getElementById('cf-turnstile-widget');
      if(el) window.turnstile.reset(el);
    }}
  }}catch(e){{}}
}}
function endpoint(path){{ return AUTH_BASE ? AUTH_BASE + path : path; }}
async function sendResetCode(){{
  const token=getTurnstileToken();
  if(!token){{out.textContent='请先完成人机验证（Turnstile）';return;}}
  const payload={{email:document.getElementById('email').value.trim(),turnstile_token:token}};
  try{{
    const r=await fetch(endpoint('/api/auth/password_reset/code'),{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(payload)}});
    out.textContent=await r.text();
  }}catch(e){{out.textContent='请求失败：'+e;}}
  resetTurnstile();
}}
async function resetPassword(){{
  const token=getTurnstileToken();
  if(!token){{out.textContent='请先完成人机验证（Turnstile）';return;}}
  const payload={{
    email:document.getElementById('email').value.trim(),
    email_code:document.getElementById('email_code').value.trim(),
    new_password:document.getElementById('new_password').value,
    turnstile_token:token,
  }};
  try{{
    const r=await fetch(endpoint('/api/auth/password_reset'),{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(payload)}});
    out.textContent=await r.text();
  }}catch(e){{out.textContent='请求失败：'+e;}}
  resetTurnstile();
}}
</script></body></html>"""
