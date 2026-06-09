import os


class Settings:
    db_url: str = os.getenv(
        "APP_DB_URL",
        "mysql+pymysql://fms_auth:fms_auth@db:3306/fms_auth?charset=utf8mb4",
    )
    jwt_secret: str = os.getenv("APP_JWT_SECRET", "change_me")
    jwt_expire_minutes: int = int(os.getenv("APP_JWT_EXPIRE_MINUTES", "120"))
    refresh_token_expire_days: int = int(os.getenv("APP_REFRESH_TOKEN_EXPIRE_DAYS", "30"))
    admin_username: str = os.getenv("APP_ADMIN_USERNAME", "").strip()
    admin_password: str = os.getenv("APP_ADMIN_PASSWORD", "").strip()
    allowed_origins: str = os.getenv("APP_ALLOWED_ORIGINS", "*").strip()
    bind_port: int = int(os.getenv("APP_ADMIN_PORT", "1145"))
    openlist_base_url: str = os.getenv("APP_OPENLIST_BASE_URL", "http://main.cnrpg.top:5245").strip().rstrip("/")
    openlist_username: str = os.getenv("APP_OPENLIST_USERNAME", "navdata").strip()
    openlist_password: str = os.getenv("APP_OPENLIST_PASSWORD", "navdata").strip()
    openlist_root_path: str = os.getenv("APP_OPENLIST_ROOT_PATH", "/").strip() or "/"


settings = Settings()
