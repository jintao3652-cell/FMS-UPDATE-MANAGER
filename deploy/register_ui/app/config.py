from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", case_sensitive=False)

    auth_api_url: str = "http://auth_api:17306"
    register_port: int = 3090
    register_public_auth_url: str = ""


settings = Settings()
