import os


class Settings:
    db_url: str = os.getenv(
        "APP_DB_URL",
        "mysql+pymysql://fms_auth:fms_auth@db:3306/fms_auth?charset=utf8mb4",
    )
    jwt_secret: str = os.getenv("APP_JWT_SECRET", "change_me")
    jwt_expire_minutes: int = int(os.getenv("APP_JWT_EXPIRE_MINUTES", "120"))
    admin_username: str = os.getenv("APP_ADMIN_USERNAME", "").strip()
    admin_password: str = os.getenv("APP_ADMIN_PASSWORD", "").strip()
    allowed_origins: str = os.getenv("APP_ALLOWED_ORIGINS", "*").strip()
    bind_port: int = int(os.getenv("APP_ADMIN_PORT", "1145"))


settings = Settings()
