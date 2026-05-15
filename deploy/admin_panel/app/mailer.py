import json
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AppSetting, EmailLog
from .schemas import SmtpSettings, TurnstileSettings


SMTP_KEY = "smtp"
TURNSTILE_KEY = "turnstile"


DEFAULT_SMTP = SmtpSettings().model_dump()
DEFAULT_TURNSTILE = TurnstileSettings().model_dump()


def load_smtp(db: Session) -> SmtpSettings:
    row = db.get(AppSetting, SMTP_KEY)
    if row is None or not row.value:
        return SmtpSettings()
    try:
        data = json.loads(row.value)
    except Exception:
        return SmtpSettings()
    merged = {**DEFAULT_SMTP, **(data if isinstance(data, dict) else {})}
    return SmtpSettings(**merged)


def save_smtp(db: Session, value: SmtpSettings) -> None:
    payload = json.dumps(value.model_dump(), ensure_ascii=False)
    row = db.get(AppSetting, SMTP_KEY)
    if row is None:
        db.add(AppSetting(key=SMTP_KEY, value=payload))
    else:
        row.value = payload
    db.commit()


def smtp_status(cfg: SmtpSettings) -> dict:
    return {
        "configured": bool(cfg.host and cfg.username and cfg.sender),
        "host": cfg.host,
        "port": cfg.port,
        "sender": cfg.sender,
        "use_ssl": cfg.use_ssl,
        "use_tls": cfg.use_tls,
    }


def load_turnstile(db: Session) -> TurnstileSettings:
    row = db.get(AppSetting, TURNSTILE_KEY)
    if row is None or not row.value:
        return TurnstileSettings()
    try:
        data = json.loads(row.value)
    except Exception:
        return TurnstileSettings()
    merged = {**DEFAULT_TURNSTILE, **(data if isinstance(data, dict) else {})}
    return TurnstileSettings(**merged)


def save_turnstile(db: Session, value: TurnstileSettings) -> None:
    payload = json.dumps(value.model_dump(), ensure_ascii=False)
    row = db.get(AppSetting, TURNSTILE_KEY)
    if row is None:
        db.add(AppSetting(key=TURNSTILE_KEY, value=payload))
    else:
        row.value = payload
    db.commit()


def turnstile_status(cfg: TurnstileSettings) -> dict:
    return {
        "configured": bool(cfg.site_key and cfg.secret_key),
        "site_key_set": bool(cfg.site_key),
        "secret_key_set": bool(cfg.secret_key),
    }


def _build_message(cfg: SmtpSettings, recipient: str, subject: str, body_text: str, body_html: str | None) -> EmailMessage:
    msg = EmailMessage()
    sender_addr = cfg.sender or cfg.username
    from_value = formataddr((cfg.sender_name or "", sender_addr)) if cfg.sender_name else sender_addr
    msg["From"] = from_value
    msg["To"] = recipient
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid()
    msg.set_content(body_text or "")
    if body_html:
        msg.add_alternative(body_html, subtype="html")
    return msg


def send_email(
    db: Session,
    cfg: SmtpSettings,
    recipient: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    *,
    purpose: str = "",
    sent_by: str = "",
) -> tuple[bool, str]:
    if not cfg.host or not cfg.username or not cfg.sender:
        log = EmailLog(recipient=recipient, subject=subject, purpose=purpose, success=False, error="smtp not configured", sent_by=sent_by)
        db.add(log)
        db.commit()
        return False, "smtp not configured"
    msg = _build_message(cfg, recipient, subject, body_text, body_html)
    error_text = ""
    try:
        if cfg.use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=15, context=context) as client:
                client.login(cfg.username, cfg.password)
                client.send_message(msg)
        else:
            with smtplib.SMTP(cfg.host, cfg.port, timeout=15) as client:
                client.ehlo()
                if cfg.use_tls:
                    context = ssl.create_default_context()
                    client.starttls(context=context)
                    client.ehlo()
                client.login(cfg.username, cfg.password)
                client.send_message(msg)
        success = True
    except Exception as exc:
        success = False
        error_text = str(exc)[:1000]
    log = EmailLog(
        recipient=recipient,
        subject=subject,
        purpose=purpose,
        success=success,
        error=error_text,
        sent_by=sent_by,
    )
    db.add(log)
    db.commit()
    return success, error_text


def render_verification_email(code: str, ttl_minutes: int) -> tuple[str, str, str]:
    subject = "FMS UPDATE MANAGER 注册验证码"
    text = f"您的注册验证码是：{code}\n有效时间：{ttl_minutes} 分钟。\n如非本人操作请忽略本邮件。"
    html = f"""
<!doctype html>
<html><body style="font-family:Segoe UI,Arial,sans-serif;background:#f4f7fb;padding:24px;color:#13233b">
  <div style="max-width:520px;margin:0 auto;background:#fff;border-radius:12px;padding:28px;box-shadow:0 8px 24px rgba(0,0,0,0.06)">
    <h2 style="margin:0 0 12px;color:#1a73e8">FMS UPDATE MANAGER</h2>
    <p>您正在注册账号，请使用以下验证码完成验证：</p>
    <div style="font-size:32px;font-weight:700;letter-spacing:8px;background:#eef3fb;border-radius:8px;padding:14px 18px;text-align:center;margin:16px 0">{code}</div>
    <p style="color:#5b6f8a;font-size:13px">有效时间：{ttl_minutes} 分钟。如非本人操作请忽略本邮件。</p>
  </div>
</body></html>
"""
    return subject, text, html


def list_settings(db: Session) -> dict:
    rows = db.scalars(select(AppSetting)).all()
    return {row.key: row.value for row in rows}


def upsert_setting(db: Session, key: str, value: str) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    db.commit()


def get_setting_json(db: Session, key: str, default: dict) -> dict:
    row = db.get(AppSetting, key)
    if row is None or not row.value:
        return dict(default)
    try:
        data = json.loads(row.value)
        if isinstance(data, dict):
            merged = dict(default)
            merged.update(data)
            return merged
    except Exception:
        pass
    return dict(default)


def set_setting_json(db: Session, key: str, value: dict) -> None:
    upsert_setting(db, key, json.dumps(value, ensure_ascii=False))
