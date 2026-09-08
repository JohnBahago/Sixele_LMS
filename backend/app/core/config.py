from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "Sixele LMS API"
    environment: str = "development"
    api_prefix: str = "/api"
    mongo_url: str = "mongodb://localhost:27017"
    db_name: str = "sixele_lms"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    cors_origins: str = "http://localhost:5173"
    upload_dir: str = "uploads"
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60
    max_request_body_bytes: int = 10 * 1024 * 1024
    trusted_proxy_headers: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True
    smtp_timeout_seconds: int = 20

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
