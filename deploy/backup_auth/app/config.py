import os


class Settings:
    db_url: str = os.getenv("APP_DB_URL", "mysql+pymysql://fms_auth:fms_auth@localhost:3306/fms_auth?charset=utf8mb4")
    jwt_secret: str = os.getenv("APP_JWT_SECRET", "change_me")
    jwt_expire_minutes: int = int(os.getenv("APP_JWT_EXPIRE_MINUTES", "60"))
    admin_username: str = os.getenv("APP_ADMIN_USERNAME", "").strip()
    admin_password: str = os.getenv("APP_ADMIN_PASSWORD", "").strip()
    allowed_origins: str = os.getenv("APP_ALLOWED_ORIGINS", "*").strip()
    smtp_host: str = os.getenv("APP_SMTP_HOST", "").strip()
    smtp_port: int = int(os.getenv("APP_SMTP_PORT", "465"))
    smtp_user: str = os.getenv("APP_SMTP_USER", "").strip()
    smtp_password: str = os.getenv("APP_SMTP_PASSWORD", "").strip()
    smtp_sender: str = os.getenv("APP_SMTP_SENDER", "").strip()
    smtp_use_ssl: bool = os.getenv("APP_SMTP_USE_SSL", "true").strip().lower() in {"1", "true", "yes", "on"}
    smtp_use_tls: bool = os.getenv("APP_SMTP_USE_TLS", "false").strip().lower() in {"1", "true", "yes", "on"}
    email_code_ttl_seconds: int = int(os.getenv("APP_EMAIL_CODE_TTL_SECONDS", "600"))
    register_attempt_limit: int = int(os.getenv("APP_REGISTER_ATTEMPT_LIMIT", "10"))
    register_attempt_window_seconds: int = int(os.getenv("APP_REGISTER_ATTEMPT_WINDOW_SECONDS", "300"))
    register_per_ip_limit: int = int(os.getenv("APP_REGISTER_PER_IP_LIMIT", "1"))
    register_per_ip_window_seconds: int = int(os.getenv("APP_REGISTER_PER_IP_WINDOW_SECONDS", "86400"))


settings = Settings()
